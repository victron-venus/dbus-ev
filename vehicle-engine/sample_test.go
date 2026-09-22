package main

import (
	"errors"
	"slices"
	"testing"

	"github.com/evcc-io/evcc/api"
)

type telemetryVehicle struct {
	api.Vehicle
	calls []string
	fail  string
	err   error
}

func (v *telemetryVehicle) read(name string) error {
	v.calls = append(v.calls, name)
	if name == v.fail {
		return v.err
	}
	return nil
}

func (v *telemetryVehicle) Soc() (float64, error)       { return 50, v.read("soc") }
func (v *telemetryVehicle) Capacity() float64           { return 80 }
func (v *telemetryVehicle) GetLimitSoc() (int64, error) { return 80, v.read("target_soc") }
func (v *telemetryVehicle) Range() (int64, error)       { return 250, v.read("range_to_go") }
func (v *telemetryVehicle) Odometer() (float64, error)  { return 1000, v.read("odometer") }
func (v *telemetryVehicle) Position() (float64, float64, error) {
	return 40, 50, v.read("position")
}
func (v *telemetryVehicle) Status() (api.ChargeStatus, error) {
	return api.StatusC, v.read("status")
}
func (v *telemetryVehicle) CurrentPower() (float64, error) { return 7200, v.read("power") }

var telemetryOrder = []string{"soc", "status", "target_soc", "range_to_go", "odometer", "position", "power"}

func TestEveryCapabilityStopsAtFirstFailure(t *testing.T) {
	for index, name := range telemetryOrder {
		t.Run(name, func(t *testing.T) {
			v := &telemetryVehicle{fail: name, err: errors.New("upstream failure")}
			r := sample(v)
			if r.OK || r.Error != "provider" {
				t.Fatalf("failure ignored: %#v", r)
			}
			if !slices.Equal(v.calls, telemetryOrder[:index+1]) {
				t.Fatalf("extra or reordered upstream calls: %v", v.calls)
			}
		})
	}
}

func TestUnavailableOptionalCapabilityDoesNotBlockOthers(t *testing.T) {
	for _, name := range telemetryOrder[1:] {
		t.Run(name, func(t *testing.T) {
			v := &telemetryVehicle{fail: name, err: api.ErrNotAvailable}
			r := sample(v)
			if !r.OK || !slices.Equal(v.calls, telemetryOrder) {
				t.Fatalf("unavailable capability stopped collection: %#v, %v", r, v.calls)
			}
			key := name
			if name == "position" {
				key = "latitude"
			}
			if _, exists := r.Data[key]; exists {
				t.Fatalf("invented unavailable %s", key)
			}
		})
	}
}
