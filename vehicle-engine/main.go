// The optional vehicle engine reuses evcc's providers, not its charging controller.
// SPDX-License-Identifier: MIT
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/evcc-io/evcc/api"
	"github.com/evcc-io/evcc/db"
	"github.com/evcc-io/evcc/db/settings"
	"github.com/evcc-io/evcc/util"
	"github.com/evcc-io/evcc/util/request"
	"github.com/evcc-io/evcc/util/templates"
	"github.com/evcc-io/evcc/vehicle"
)

const protocolVersion = 1

type reply struct {
	Schema     int            `json:"schema"`
	OK         bool           `json:"ok"`
	Data       map[string]any `json:"data,omitempty"`
	Error      string         `json:"error,omitempty"`
	RetryAfter float64        `json:"retry_after,omitempty"`
}

// Do not return provider error strings: URLs and bodies may contain credentials.
func failure(err error) reply {
	r := reply{Schema: protocolVersion, Error: "provider"}
	var policy *policyError
	if errors.As(err, &policy) {
		r.Error, r.RetryAfter = policy.Reason, policy.RetryAfter
		return r
	}
	var login *api.ErrLoginRequired
	if errors.As(err, &login) {
		r.Error = "auth"
		return r
	}
	var status *request.StatusError
	if errors.As(err, &status) {
		switch status.StatusCode() {
		case 401, 403:
			r.Error = "auth"
		case 429:
			r.Error = "rate_limit"
		}
		value := status.Response().Header.Get("Retry-After")
		if seconds, e := strconv.ParseFloat(value, 64); e == nil && seconds > 0 && !math.IsInf(seconds, 0) {
			r.RetryAfter = seconds
		} else if until, e := http.ParseTime(value); e == nil {
			r.RetryAfter = math.Max(0, time.Until(until).Seconds())
		}
	}
	return r
}

func putNumber(data map[string]any, key string, value float64, err error) error {
	if errors.Is(err, api.ErrNotAvailable) {
		return nil
	}
	if err != nil {
		return err
	}
	if !math.IsNaN(value) && !math.IsInf(value, 0) {
		data[key] = value
	}
	return nil
}

// Only read interfaces are called. Never invoke WakeUp, OnIdentified, charging,
// door/window, climate, current-setting or other command interfaces.
// Stop at the first upstream failure instead of retrying the same failed cache
// through every capability. Missing capabilities remain absent, not zero.
func sample(v api.Vehicle) reply {
	d := map[string]any{}
	soc, err := v.Soc()
	if err != nil {
		return failure(err)
	}
	if soc < 0 || soc > 100 || math.IsNaN(soc) || math.IsInf(soc, 0) {
		return failure(errors.New("invalid soc"))
	}
	d["soc"] = soc
	if capacity := v.Capacity(); capacity > 0 && !math.IsInf(capacity, 0) {
		d["battery_capacity"] = capacity
	}
	if err := sampleChargeState(v, d); err != nil {
		return failure(err)
	}
	if p, ok := api.Cap[api.SocLimiter](v); ok {
		value, e := p.GetLimitSoc()
		if err := putNumber(d, "target_soc", float64(value), e); err != nil {
			return failure(err)
		}
	}
	if err := sampleTravel(v, d); err != nil {
		return failure(err)
	}
	if p, ok := api.Cap[api.Meter](v); ok {
		value, e := p.CurrentPower()
		if err := putNumber(d, "power", value, e); err != nil {
			return failure(err)
		}
	}
	return reply{Schema: protocolVersion, OK: true, Data: d}
}

func sampleChargeState(v api.Vehicle, d map[string]any) error {
	if p, ok := api.Cap[api.ChargeState](v); ok {
		value, err := p.Status()
		if errors.Is(err, api.ErrNotAvailable) {
			return nil
		}
		if err != nil {
			return err
		}
		d["status"] = string(value)
	}
	return nil
}

func sampleTravel(v api.Vehicle, d map[string]any) error {
	if p, ok := api.Cap[api.VehicleRange](v); ok {
		value, e := p.Range()
		if err := putNumber(d, "range_to_go", float64(value), e); err != nil {
			return err
		}
	}
	if p, ok := api.Cap[api.VehicleOdometer](v); ok {
		value, e := p.Odometer()
		if err := putNumber(d, "odometer", value, e); err != nil {
			return err
		}
	}
	if p, ok := api.Cap[api.VehiclePosition](v); ok {
		lat, lon, e := p.Position()
		if e != nil && !errors.Is(e, api.ErrNotAvailable) {
			return e
		}
		if e == nil && math.Abs(lat) <= 90 && math.Abs(lon) <= 180 {
			d["latitude"], d["longitude"] = lat, lon
		}
	}
	return nil
}

func loadConfig(path string) (map[string]any, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 {
		return nil, errors.New("configuration must be a private regular file (0600)")
	}
	var conf map[string]any
	if err := json.NewDecoder(io.LimitReader(f, 65536)).Decode(&conf); err != nil {
		return nil, err
	}
	name, _ := conf["template"].(string)
	tmpl, err := templates.ByName(templates.Vehicle, name)
	if err != nil || tmpl.Deprecated || !supported(name) {
		return nil, errors.New("unknown or deprecated template")
	}
	// No user-supplied action hooks or cloud proxy override. The helper only
	// instantiates a vehicle and never starts the evcc site/loadpoint controller.
	delete(conf, "onIdentify")
	delete(conf, "cloud")
	return conf, nil
}

func run(input io.Reader, output io.Writer, conf map[string]any, database string) error {
	if err := os.MkdirAll(filepath.Dir(database), 0700); err != nil {
		return err
	}
	f, err := os.OpenFile(database, os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return err
	}
	if err := f.Chmod(0600); err != nil {
		f.Close()
		return err
	}
	f.Close()
	if err := db.NewInstance("sqlite", database); err != nil {
		return err
	}
	defer db.Close()
	defer settings.Persist()
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var v api.Vehicle
	scanner := bufio.NewScanner(input)
	encoder := json.NewEncoder(output)
	for scanner.Scan() {
		// An extremely small protocol intentionally has no command passthrough.
		if scanner.Text() != "poll" {
			return errors.New("only poll is accepted")
		}
		if v == nil {
			v, err = vehicle.NewFromTemplateConfig(ctx, conf)
			if err != nil {
				r := failure(err)
				r.Error = "auth" // construction can include login: never automatically loop it
				encoder.Encode(r)
				return nil
			}
		}
		r := sample(v)
		if err := settings.Persist(); err != nil {
			r = reply{Schema: protocolVersion, Error: "storage"}
		}
		if err := encoder.Encode(r); err != nil {
			return err
		}
	}
	return scanner.Err()
}

func main() {
	confPath := flag.String("config", "", "private evcc vehicle-template JSON")
	database := flag.String("database", "", "private persistent token database")
	catalog := flag.Bool("catalog", false, "list upstream vehicle templates without network access")
	authorize := flag.Bool("authorize", false, "interactive OAuth setup; never used by the daemon")
	flag.Parse()
	// Libraries sometimes print to stdout. Keep the protocol on the original
	// descriptor, redirect all provider output to stderr (discarded by the parent).
	output := os.Stdout
	os.Stdout = os.Stderr
	// Loggers created during package initialization captured the original stdout.
	util.Loggers(func(_ string, logger *util.Logger) {
		logger.TRACE.SetOutput(os.Stderr)
		logger.DEBUG.SetOutput(os.Stderr)
		logger.INFO.SetOutput(os.Stderr)
		logger.WARN.SetOutput(os.Stderr)
		logger.ERROR.SetOutput(os.Stderr)
		logger.FATAL.SetOutput(os.Stderr)
	})
	if *catalog {
		output.Write(catalogJSON)
		return
	}
	if *database == "" || *confPath == "" {
		fmt.Fprintln(os.Stderr, "--config and --database required")
		os.Exit(2)
	}
	conf, err := loadConfig(*confPath)
	if err == nil {
		var gate *traffic
		gate, err = newTraffic(*database + ".traffic.json")
		if err == nil {
			request.DBusEVTransport = gate.wrap
		}
	}
	if err == nil {
		if *authorize {
			err = authorizeVehicle(conf, *database, os.Stdin, output)
		} else {
			err = run(os.Stdin, output, conf, *database)
		}
	}
	if err != nil {
		json.NewEncoder(output).Encode(reply{Schema: protocolVersion, Error: "configuration"})
		os.Exit(1)
	}
}
