package main

import (
	"context"
	"encoding/json"
	"io"
	"math"
	"net/http"
	"net/url"
	"strings"
	"testing"

	"github.com/evcc-io/evcc/api"
	"github.com/evcc-io/evcc/util/request"
)

type fuzzVehicle struct {
	api.Vehicle
	soc, capacity, latitude, longitude, power float64
}

func (v *fuzzVehicle) Soc() (float64, error)          { return v.soc, nil }
func (v *fuzzVehicle) Capacity() float64              { return v.capacity }
func (v *fuzzVehicle) CurrentPower() (float64, error) { return v.power, nil }
func (v *fuzzVehicle) Position() (float64, float64, error) {
	return v.latitude, v.longitude, nil
}

func FuzzVehicleTelemetry(f *testing.F) {
	f.Add(50.0, 80.0, 45.0, -120.0, 7000.0)
	f.Add(math.NaN(), math.Inf(1), math.Inf(-1), 181.0, math.NaN())
	f.Add(0.0, 0.0, -90.0, 180.0, 0.0)
	f.Fuzz(func(t *testing.T, soc, capacity, latitude, longitude, power float64) {
		r := sample(&fuzzVehicle{soc: soc, capacity: capacity, latitude: latitude, longitude: longitude, power: power})
		if _, err := json.Marshal(r); err != nil {
			t.Fatalf("telemetry reply contains an unrepresentable number: %v", err)
		}
		validSOC := !math.IsNaN(soc) && !math.IsInf(soc, 0) && soc >= 0 && soc <= 100
		if r.OK != validSOC {
			t.Fatal("invalid SOC accepted, or a valid synthetic sample rejected")
		}
		if !r.OK {
			return
		}
		if r.Data["soc"] != soc {
			t.Fatal("measured SOC was changed")
		}
		_, hasPosition := r.Data["latitude"]
		if hasPosition != (math.Abs(latitude) <= 90 && math.Abs(longitude) <= 180) {
			t.Fatal("position bounds were not preserved")
		}
	})
}

func FuzzProviderRetryAfter(f *testing.F) {
	for _, value := range []string{"0", "120", "-1", "NaN", "+Inf", "1e300", "Wed, 21 Oct 2015 07:28:00 GMT", "private-token"} {
		f.Add(value, uint16(429))
	}
	f.Fuzz(func(t *testing.T, value string, code uint16) {
		if len(value) > 4096 {
			t.Skip()
		}
		response := &http.Response{StatusCode: int(code), Header: http.Header{"Retry-After": {value}}, Body: io.NopCloser(strings.NewReader("private-token"))}
		r := failure(request.NewStatusError(response))
		if math.IsNaN(r.RetryAfter) || math.IsInf(r.RetryAfter, 0) || r.RetryAfter < 0 {
			t.Fatal("invalid retry delay escaped provider normalization")
		}
		want := "provider"
		if code == 401 || code == 403 {
			want = "auth"
		} else if code == 429 {
			want = "rate_limit"
		}
		if r.OK || r.Error != want || r.Data != nil {
			t.Fatal("provider failure changed category or exposed provider data")
		}
	})
}

func FuzzOAuthStateBoundary(f *testing.F) {
	for _, value := range []string{"expected", "wrong", "", "expected&state=wrong", "expected\n", "雪"} {
		f.Add(value)
	}
	f.Fuzz(func(t *testing.T, state string) {
		if len(state) > 4096 {
			t.Skip()
		}
		provider := &fakeAuthorization{}
		redirect := "https://example.invalid/callback?code=synthetic&state=" + url.QueryEscape(state)
		err := completeAuthorization(context.Background(), provider, "expected", strings.NewReader(redirect), io.Discard)
		if (err == nil) != (state == "expected") || (provider.callback != nil) != (state == "expected") {
			t.Fatal("OAuth callback did not require the exact generated state")
		}
	})
}
