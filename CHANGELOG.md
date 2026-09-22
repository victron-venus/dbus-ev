# Changelog

## Unreleased

- Add an opt-in multi-brand provider engine using pinned evcc vehicle libraries (35 templates / 33 brands), with common D-Bus vehicle/charger projection. New providers are experimental and have no live vehicle validation.
- Add persistent pacing, HTTP retry budgets and conservative upstream patches; expose no vehicle-control commands.
- Allow source selection through local configuration and SetupHelper. Optional MQTT publication for new brands sends raw state only, without HA discovery or automatic sensors.
- Keep the existing Mercedes client, HA payload and default installation behavior.

All notable changes to this project will be documented in this file.

## 0.1.2

- Preserve request-start monotonic freshness so delayed replies cannot renew expired telemetry.

- Keep D-Bus and heartbeat callbacks responsive while one bounded HA worker polls.
- Include unit metadata in the existing template request, preserving power and distance conversions without extra HTTP reads.
- Reject non-finite measurements, invalidate missing power, and map unknown charging states to the unavailable enum.
- Preserve the existing monotonic stale-data timeout, device configuration, and read-only EV behavior.
- Cover blocked requests, recovery, shutdown ordering, numerical validity, and installer tests from arbitrarily named worktrees.

## [Unreleased]

### Changed
- Default POLL_INTERVAL unified to 15.0s (was 2.0 in package, 5.0 in example)

### Added
- `TANK_CAPACITY_LITERS` config → `/Capacity` on the tank service; GUIv2 now
  renders the gauge in liters.
- Remaining liters computed locally from the raw water-column sensor
  (`TANK_WATER_CM_ENTITY`) using configured tank geometry (`TANK_OFFSET_CM`,
  `TANK_RADIUS_CM`) — no HA-side template sensor; falls back to
  `Capacity × Level` when the raw sensor is unavailable.

## [Unreleased]

### Documentation
- README: full water data-flow diagram (HA sensors → dbus-pump → D-Bus → Cerbo
  MQTT topics → consumers) and valve hysteresis sequence diagram; consumer table.

## [0.1.0] - 2026-08-23

### Added
- HA-backed water tank/pump/valve D-Bus bridge for Venus OS.
- Three services: `com.victronenergy.tank.ha_tank<N>`, two `pump.startstop`
  instances (pump + city-water valve) with writable `/Mode`.
- Hysteresis valve automation (open ≤ START, close ≥ STOP), stale-sensor
  fail-safe (force CLOSED), manual `/Mode` override, anti-chatter interval,
  valve force-closed on SIGTERM/SIGINT.
- HA REST client with circuit breaker (5 failures → 60 s open), last-known
  values while unreachable, once/min error throttle.
- deploy.sh / update.sh / restart.sh trio; daemontools unit with multilog.
- CI via venus-os-ci-toolkit python workflow + secrets-template validation.

### Verified on device (Cerbo GX, Venus v3.75)
- All three services register; tank level live on MQTT
  (`N/<portal>/tank/21/Level`).
- Failure drill: HA unreachable → circuit breaker opens, `/Status` fault,
  `/Connected` 0; auto-recovery after restore.
- Keep-alive dump from laptop broker works (9255 msgs).

### Known limitations
- Round-trip control drill pending `switch.shutoff_valve` hardware back
  online (entity currently unavailable in HA; automation correctly refuses
  to command an unknown state).
