package main

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"

	"github.com/evcc-io/evcc/util/request"
)

type trafficState struct {
	Window   time.Time `json:"window"`
	Count    int       `json:"count"`
	Next     time.Time `json:"next"`
	Pause    time.Time `json:"pause"`
	Reason   string    `json:"reason"`
	Failures int       `json:"failures"`
}

type traffic struct {
	mu    sync.Mutex
	path  string
	state trafficState
	now   func() time.Time
}

type policyError struct {
	Reason     string
	RetryAfter float64
}

func (e *policyError) Error() string { return "vehicle request paused" }

func newTraffic(path string) (*traffic, error) {
	g := &traffic{path: path, now: time.Now}
	b, err := os.ReadFile(path)
	if err == nil {
		err = json.Unmarshal(b, &g.state)
	}
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return nil, err
	}
	return g, nil
}

func (g *traffic) save() error {
	if err := os.MkdirAll(filepath.Dir(g.path), 0700); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(g.path), ".traffic-")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	err = json.NewEncoder(f).Encode(g.state)
	if err == nil {
		err = f.Sync()
	}
	f.Close()
	if err != nil {
		return err
	}
	return os.Rename(f.Name(), g.path)
}

type gatedTransport struct {
	gate *traffic
	base http.RoundTripper
}

func (g *traffic) wrap(base http.RoundTripper) http.RoundTripper {
	return &gatedTransport{g, base}
}

func (t *gatedTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	g := t.gate
	g.mu.Lock()
	defer g.mu.Unlock()
	now := g.now()
	if now.Before(g.state.Pause) {
		return nil, &policyError{g.state.Reason, g.state.Pause.Sub(now).Seconds()}
	}
	if now.Sub(g.state.Window) >= time.Hour {
		g.state.Window, g.state.Count = now, 0
	}
	// The account-wide ceiling bounds hidden library retries and deferred reads.
	if g.state.Count >= 60 {
		return nil, &policyError{"rate_limit", g.state.Window.Add(time.Hour).Sub(now).Seconds()}
	}
	if wait := g.state.Next.Sub(now); wait > 0 {
		timer := time.NewTimer(wait)
		defer timer.Stop()
		select {
		case <-req.Context().Done():
			return nil, req.Context().Err()
		case <-timer.C:
		}
	}
	g.state.Count++
	g.state.Next = g.now().Add(2 * time.Second)
	if err := g.save(); err != nil {
		return nil, &policyError{Reason: "storage"}
	}
	resp, err := t.base.RoundTrip(req)
	if err == nil && (resp.StatusCode == 429 || resp.StatusCode == 401 || resp.StatusCode == 403) {
		r := failure(request.NewStatusError(resp))
		g.state.Failures = min(5, g.state.Failures+1)
		delay := max(min(21600, 1800*float64(int64(1)<<(g.state.Failures-1))), r.RetryAfter)
		if r.Error == "auth" {
			delay = max(delay, 21600)
		}
		// Bound conversion to Duration: a malicious/invalid Retry-After must not
		// overflow into a negative pause. A century is effectively disabled.
		delay = min(delay, 100*365*24*3600)
		g.state.Pause = g.now().Add(time.Duration(delay) * time.Second)
		g.state.Reason = r.Error
		if err := g.save(); err != nil {
			resp.Body.Close()
			return nil, &policyError{Reason: "storage"}
		}
	}
	return resp, err
}
