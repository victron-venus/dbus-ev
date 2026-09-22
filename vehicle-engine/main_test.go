package main

import (
	"context"
	"encoding/json"
	"errors"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/evcc-io/evcc/api"
	"github.com/evcc-io/evcc/util/request"
	"github.com/evcc-io/evcc/util/templates"
)

type fakeVehicle struct {
	api.Vehicle
	soc     float64
	err     error
	calls   int
	wakeups int
}

func (v *fakeVehicle) Soc() (float64, error)             { v.calls++; return v.soc, v.err }
func (v *fakeVehicle) Capacity() float64                 { return 80 }
func (v *fakeVehicle) Status() (api.ChargeStatus, error) { v.calls++; return api.StatusC, nil }
func (v *fakeVehicle) CurrentPower() (float64, error)    { v.calls++; return 0, nil }
func (v *fakeVehicle) WakeUp() error                     { v.wakeups++; return nil }

func TestReadOnlySample(t *testing.T) {
	v := &fakeVehicle{soc: 0}
	r := sample(v)
	if !r.OK || r.Data["soc"] != float64(0) || r.Data["power"] != float64(0) || r.Data["status"] != "C" {
		t.Fatalf("bad normalized reading: %#v", r)
	}
	if _, ok := r.Data["odometer"]; ok {
		t.Fatal("invented unsupported field")
	}
	if v.wakeups != 0 {
		t.Fatal("read woke the car")
	}
}

func TestStopAfterFirstFailure(t *testing.T) {
	v := &fakeVehicle{soc: 50, err: errors.New("private response")}
	r := sample(v)
	if r.OK || v.calls != 1 || r.Error != "provider" {
		t.Fatal("continued after failure")
	}
	b, _ := json.Marshal(r)
	if strings.Contains(string(b), "private") {
		t.Fatal("error body leaked")
	}
	for _, n := range []float64{math.NaN(), math.Inf(1), -1, 101} {
		if sample(&fakeVehicle{soc: n}).OK {
			t.Fatal("invalid SoC accepted")
		}
	}
}

func TestRateLimitClassification(t *testing.T) {
	r := failure(request.NewStatusError(&http.Response{StatusCode: 429, Header: http.Header{"Retry-After": []string{"86400"}}}))
	if r.Error != "rate_limit" || r.RetryAfter != 86400 {
		t.Fatalf("%#v", r)
	}
	if failure(api.LoginRequiredError("private-id")).Error != "auth" {
		t.Fatal("missing auth classification")
	}
}

func TestCatalogMatchesPinnedUpstreamAndRenders(t *testing.T) {
	var c struct {
		Templates []struct {
			Template string
			Required []string `json:"required_parameters"`
		}
	}
	if err := json.Unmarshal(catalogJSON, &c); err != nil {
		t.Fatal(err)
	}
	if len(c.Templates) != 35 {
		t.Fatal("catalog changed without reviewing provider coverage")
	}
	for _, p := range c.Templates {
		t.Run(p.Template, func(t *testing.T) {
			assertCatalogTemplate(t, p.Template, p.Required)
		})
	}
}

func assertCatalogTemplate(t *testing.T, name string, required []string) {
	t.Helper()
	tmpl, err := templates.ByName(templates.Vehicle, name)
	if err != nil || tmpl.Deprecated {
		t.Fatalf("unusable template: %v", err)
	}
	conf := map[string]any{"template": name, "vin": "WDD00000000000001"}
	if name == "niu-e-scooter" {
		delete(conf, "vin")
	}
	for _, key := range required {
		if key != "vin" {
			conf[key] = "test-placeholder"
		}
	}
	// Render only: no constructor, network, account or vehicle needed.
	if _, err := templates.RenderInstance(templates.Vehicle, conf); err != nil {
		t.Fatal(err)
	}
}

func TestPrivateConfigAndSupportedTemplates(t *testing.T) {
	p := filepath.Join(t.TempDir(), "vehicle.json")
	if err := os.WriteFile(p, []byte(`{"template":"hyundai","vin":"WDD00000000000001","user":"example","password":"example"}`), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := loadConfig(p); err != nil {
		t.Fatal(err)
	}
	os.Chmod(p, 0644)
	if _, err := loadConfig(p); err == nil {
		t.Fatal("public credentials accepted")
	}
	if supported("homeassistant") || supported("mercedes") || supported("offline") {
		t.Fatal("non-direct provider advertised")
	}
}

type fakeTransport struct {
	calls  int
	status int
	now    *time.Time
}

func (t *fakeTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	t.calls++
	*t.now = t.now.Add(3 * time.Second)
	return &http.Response{StatusCode: t.status, Header: http.Header{"Retry-After": []string{"86400"}}, Body: http.NoBody, Request: req}, nil
}

func TestHTTP429BlocksHiddenRetriesAndSurvivesRestart(t *testing.T) {
	now := time.Now()
	p := filepath.Join(t.TempDir(), "traffic.json")
	g, err := newTraffic(p)
	if err != nil {
		t.Fatal(err)
	}
	g.now = func() time.Time { return now }
	base := &fakeTransport{status: 429, now: &now}
	tr := g.wrap(base)
	req, _ := http.NewRequestWithContext(context.Background(), "GET", "https://example.invalid", nil)
	if _, err := tr.RoundTrip(req); err != nil {
		t.Fatal(err)
	}
	if _, err := tr.RoundTrip(req); err == nil {
		t.Fatal("retried during cooldown")
	}
	if base.calls != 1 {
		t.Fatal("extra upstream request")
	}
	g, err = newTraffic(p)
	if err != nil {
		t.Fatal(err)
	}
	g.now = func() time.Time { return now }
	if _, err := g.wrap(base).RoundTrip(req); err == nil {
		t.Fatal("restart bypassed cooldown")
	}
	info, _ := os.Stat(p)
	if info.Mode().Perm() != 0600 {
		t.Fatal("public traffic state")
	}
}

func TestHTTPBudgetBoundsLibraryRetryLoops(t *testing.T) {
	now := time.Now()
	g, _ := newTraffic(filepath.Join(t.TempDir(), "traffic.json"))
	g.now = func() time.Time { return now }
	base := &fakeTransport{status: 200, now: &now}
	tr := g.wrap(base)
	req, _ := http.NewRequest("GET", "https://example.invalid", nil)
	for range 60 {
		if _, err := tr.RoundTrip(req); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := tr.RoundTrip(req); err == nil {
		t.Fatal("hourly budget bypassed")
	}
	if base.calls != 60 {
		t.Fatal("extra upstream calls")
	}
}
