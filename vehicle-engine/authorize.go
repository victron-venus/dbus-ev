package main

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/evcc-io/evcc/api"
	"github.com/evcc-io/evcc/db"
	"github.com/evcc-io/evcc/db/settings"
	"github.com/evcc-io/evcc/plugin/auth"
	"github.com/evcc-io/evcc/util/templates"
)

// Run only from the explicit authorization command, under the parent's owner
// lock. Login never runs implicitly in this helper's polling loop.
func authorizeVehicle(conf map[string]any, database string, input io.Reader, output io.Writer) error {
	name, _ := conf["template"].(string)
	tmpl, err := templates.ByName(templates.Vehicle, name)
	if err != nil {
		return err
	}
	typ, _ := tmpl.Auth["type"].(string)
	if typ == "" {
		fmt.Fprintln(output, "This template uses credentials/API keys/tokens from the private JSON; no interactive OAuth flow.")
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(database), 0700); err != nil {
		return err
	}
	f, err := os.OpenFile(database, os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return err
	}
	f.Chmod(0600)
	f.Close()
	if err := db.NewInstance("sqlite", database); err != nil {
		return err
	}
	defer db.Close()
	params := map[string]any{}
	for _, param := range tmpl.Auth["params"].([]any) {
		for key, value := range conf {
			if strings.EqualFold(key, param.(string)) {
				params[key] = value
			}
		}
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	ts, err := auth.NewFromConfig(ctx, typ, params)
	if err != nil {
		return err
	}
	provider, ok := ts.(api.AuthProvider)
	if !ok {
		return errors.New("no interactive authorization provider")
	}
	var random [32]byte
	if _, err := rand.Read(random[:]); err != nil {
		return err
	}
	state := hex.EncodeToString(random[:])
	link, device, err := provider.Login(state)
	if err != nil {
		return err
	}
	if device != nil {
		fmt.Fprintf(output, "Open %s and enter code %s\n", device.VerificationURI, device.UserCode)
		ticker := time.NewTicker(time.Second)
		defer ticker.Stop()
		for !provider.Authenticated() {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-ticker.C:
			}
		}
	} else {
		fmt.Fprintf(output, "Open this URL, then paste the full redirect URL here:\n%s\n", link)
		scanner := bufio.NewScanner(input)
		if !scanner.Scan() {
			return errors.New("redirect URL required")
		}
		callback, err := url.Parse(strings.TrimSpace(scanner.Text()))
		if err != nil || callback.Query().Get("state") != state {
			return errors.New("invalid OAuth state")
		}
		if err := provider.HandleCallback(callback.Query()); err != nil {
			return err
		}
	}
	if err := settings.Persist(); err != nil {
		return err
	}
	fmt.Fprintln(output, "Authorization saved. No vehicle command was sent.")
	return nil
}
