package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"

	"github.com/evcc-io/evcc/util"
	"github.com/evcc-io/evcc/vehicle/bluelink"
)

// A new account namespace per invocation also survives -count and port reuse.
var identityCacheFixtureSequence atomic.Uint64

// These two credential tuples have identical dot-joined representations.
// Exercise the patched public factory through owned synthetic auth/device APIs.
func TestBlueLinkIdentityCacheKeepsCredentialFieldsSeparate(t *testing.T) {
	var logins atomic.Int32
	mux := http.NewServeMux()
	mux.HandleFunc("/auth/api/v2/user/oauth2/token", func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil {
			t.Error("invalid synthetic token request")
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		logins.Add(1)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"access_token":  "fixture-access-" + r.Form.Get("refresh_token"),
			"refresh_token": "fixture-next-token", "expires_in": 3600,
		})
	})
	mux.HandleFunc("/api/v1/spa/notifications/register", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = fmt.Fprint(w, `{"RetCode":"S","ResMsg":{"DeviceID":"fixture-device"}}`)
	})
	server := httptest.NewServer(mux)
	t.Cleanup(server.Close)
	config := bluelink.Config{
		Brand: "identity-cache-fixture", URI: server.URL, LoginFormHost: server.URL,
		CCSPServiceID: "fixture-service", CCSPServiceSecret: "fixture-secret",
		// Public OEM stamp parameters already used by the upstream login tests.
		CCSPApplicationID: "a2b8469b-30a3-4361-8e13-6fceea8fbe74",
		Cfb:               "wLTVxwidmH8CfJYBWSnHD6E0huk0ozdiuygB4hLkM5XCgzAL1Dk5sE36d/bx5PFMbZs=",
		PushType:          "APNS",
	}
	firstUser := fmt.Sprintf("alice-%d@fixture.test", identityCacheFixtureSequence.Add(1))
	secondUser := firstUser + ".bar"
	const firstPassword, secondPassword = "bar.baz", "baz"
	if strings.Join([]string{config.URI, "kia", firstUser, firstPassword}, ".") !=
		strings.Join([]string{config.URI, "kia", secondUser, secondPassword}, ".") {
		t.Fatal("synthetic credential tuples must reproduce the original joined-key collision")
	}
	logger := util.NewLogger("identity-cache-fixture")
	first, err := bluelink.LoginIdentity(logger, config, firstUser, firstPassword, "en", "kia")
	if err != nil {
		t.Fatal("first synthetic identity login failed")
	}
	second, err := bluelink.LoginIdentity(logger, config, secondUser, secondPassword, "en", "kia")
	if err != nil {
		t.Fatal("second synthetic identity login failed")
	}
	if first == second || logins.Load() != 2 {
		t.Fatal("different credential fields reused one account identity")
	}
	firstToken, err := first.Token()
	if err != nil {
		t.Fatal("first synthetic token unavailable")
	}
	secondToken, err := second.Token()
	if err != nil || firstToken.AccessToken == secondToken.AccessToken {
		t.Fatal("synthetic account tokens were mixed")
	}

	// Reuse of the same account remains mandatory for single-use refresh tokens.
	var pending sync.WaitGroup
	failures := make(chan struct{}, 64)
	for range 64 {
		pending.Add(1)
		go func() {
			defer pending.Done()
			shared, err := bluelink.LoginIdentity(logger, config, firstUser, firstPassword, "en", "kia")
			if err != nil || shared != first {
				failures <- struct{}{}
			}
		}()
	}
	pending.Wait()
	close(failures)
	if len(failures) != 0 || logins.Load() != 2 {
		t.Fatal("concurrent same-account requests did not share the existing identity")
	}
}
