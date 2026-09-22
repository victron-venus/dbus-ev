package main

import (
	"context"
	"errors"
	"io"
	"net/url"
	"strings"
	"testing"

	"github.com/evcc-io/evcc/api"
	"golang.org/x/oauth2"
)

type fakeAuthorization struct {
	api.AuthProvider
	state         string
	callback      url.Values
	device        *oauth2.DeviceAuthResponse
	authenticated bool
}

func (p *fakeAuthorization) Login(state string) (string, *oauth2.DeviceAuthResponse, error) {
	p.state = state
	return "https://example.invalid/authorize", p.device, nil
}

func (p *fakeAuthorization) HandleCallback(params url.Values) error {
	p.callback = params
	return nil
}

func (p *fakeAuthorization) Authenticated() bool { return p.authenticated }

func TestRedirectAuthorizationChecksStateBeforeCallback(t *testing.T) {
	for _, tc := range []struct {
		name, input string
		valid       bool
	}{
		{"matching", "https://example.invalid/callback?state=expected&code=example", true},
		{"mismatch", "https://example.invalid/callback?state=other&code=example", false},
		{"missing", "https://example.invalid/callback?code=example", false},
		{"malformed", "https://%", false},
		{"empty", "", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			p := &fakeAuthorization{}
			err := completeAuthorization(context.Background(), p, "expected", strings.NewReader(tc.input), io.Discard)
			if (err == nil) != tc.valid {
				t.Fatalf("unexpected authorization result: %v", err)
			}
			if (p.callback != nil) != tc.valid {
				t.Fatal("callback ran without a valid state")
			}
			if p.state != "expected" {
				t.Fatal("login did not receive the expected state")
			}
		})
	}
}

func TestDeviceAuthorizationHonorsCancellation(t *testing.T) {
	for _, tc := range []struct {
		name          string
		authenticated bool
		want          error
	}{
		{"completed", true, nil},
		{"cancelled", false, context.Canceled},
	} {
		t.Run(tc.name, func(t *testing.T) {
			ctx, cancel := context.WithCancel(context.Background())
			cancel()
			p := &fakeAuthorization{device: &oauth2.DeviceAuthResponse{}, authenticated: tc.authenticated}
			err := completeAuthorization(ctx, p, "state", strings.NewReader(""), io.Discard)
			if !errors.Is(err, tc.want) {
				t.Fatalf("got %v, want %v", err, tc.want)
			}
			if p.callback != nil {
				t.Fatal("device authorization used a redirect callback")
			}
		})
	}
}
