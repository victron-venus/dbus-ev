# Experimental multi-brand vehicle providers

`DATA_SOURCE = "evcc"` selects an optional persistent vehicle engine built from
[evcc](https://github.com/evcc-io/evcc) commit
`0bd94d01de8d4d5702a8727a6ec3144313d7a246` (2026-09-20).
The engine uses the vehicle libraries directly; it does not run the evcc site,
loadpoint controller, web server or Home Assistant integration. Mercedes keeps
its existing client, MQTT schema and authorization independently of this option.
Only the configured provider is instantiated. Unselected providers make no calls.

All new providers are **experimental**. Compilation, configuration rendering,
unit tests and protocol tests are hardware-free. No account, region, model year
or actual vehicle other than the existing Mercedes installation has been tested.
A template is an available implementation, not a promise that every model of a
brand works. Retired upstream templates are deliberately excluded.

## Available implementations

The executable's `--catalog` and [catalog.json](../vehicle-engine/catalog.json)
list exact template names, parameters and whether interactive OAuth is available.
The current catalog contains 35 templates covering 33 brands:

- Hyundai (`hyundai`, `hyundai-us`), Kia (`kia`), Genesis (`genesis`). Region
  support differs between providers; the US template is Hyundai-specific.
- BMW and Mini (`cardata`); CarData enrollment and regional eligibility required.
- Volkswagen (`vw`), Audi (`audi`), Seat (`seat`), Cupra (`cupra`),
  Škoda (`skoda`, `myskoda`). The templates select the current upstream API;
  public API / EU Data Act accounts are not equivalent to old WeConnect logins.
- Renault (`renault`), Dacia (`dacia`), Alpine (`myalpine`).
- Nissan (`carwings`, `nissan`, `nissan-ariya`). Select the matching generation;
  the Ariya template also lists Micra upstream. Old disconnected services cannot
  be restored by adding an adapter.
- Toyota (`toyota`), Lexus (`lexus`), Subaru (`subaru`).
- Fiat and Jeep (`fiat`), Citroën (`citroen`), DS (`ds`), Opel (`opel`),
  Peugeot (`peugeot`).
- Tesla (`tesla`), Ford (`ford-connect-query`), Volvo (`volvo-connected`),
  Polestar (`polestar-data-portal`). Developer applications, tokens, scopes,
  subscriptions or API keys can be required. This Tesla adapter reads Fleet API;
  it does not implement a public Fleet Telemetry receiver.
- MG (`mg`), Smart (`smart-hello`), Aiways (`aiways`).
- LiveWire (`livewire`), NIU (`niu-e-scooter`), Zero Motorcycles (`zero`).

Consult the [upstream vehicle documentation](https://docs.evcc.io/en/vehicles/)
for current requirements and registration instructions. Browser OAuth must use
exactly the redirect URI registered with the manufacturer. MQTT-only bridges,
HA readers, intermediary services and deprecated integrations are not advertised
as direct manufacturer providers by this engine.

## Build and install the optional engine

The normal Python package and Mercedes installation do not require Go. Build the
additional executable on a workstation using Go 1.27.x, Python 3 and Git:

```sh
# Native build for inspecting the catalog and tests:
sh scripts/build-vehicle-engine.sh /tmp/vehicle-engine
/tmp/vehicle-engine --catalog

# Cerbo GX with 32-bit ARM Venus OS; verify the target CPU/OS before copying:
GOOS=linux GOARCH=arm GOARM=7 sh scripts/build-vehicle-engine.sh /tmp/vehicle-engine-armv7
# Other Linux targets can use GOARCH=arm64 or amd64 as appropriate.
```

Install the matching binary as
`/data/setupOptions/dbus-ev/bin/vehicle-engine` with executable mode 0755.
The binary is optional, persists across ordinary package updates, and is not
built or downloaded during a SetupHelper update. Rebuild it from the new pinned
source when updating this engine. The release source archive includes its source,
module lock/checksums and conservative patches. Do not use a plain `go build`:
the mandatory patch hook intentionally makes unpatched builds fail compilation.

The build uses a temporary copy of the verified upstream module, applies the
reviewable patches and leaves the Go module cache untouched. Its module
replacements match the pinned upstream dependency replacements. The MIT notice
is retained in `vehicle-engine/patches/LICENSE.evcc`; Go dependency licenses and
notices remain applicable when distributing the executable.

Write a private JSON file (0600) at
`/data/setupOptions/dbus-ev/vehicle.json`. Example for the European Hyundai
provider (replace placeholders locally; never commit real credentials):

```json
{
  "template": "hyundai",
  "vin": "YOUR_17_CHAR_VIN__",
  "user": "your_account",
  "password": "your_password",
  "region": "Europe",
  "capacity": 77.4
}
```

An explicit VIN is mandatory (NIU uses its required `serial` instead): the package
never guesses which vehicle to use. Do not add `vin` to the NIU configuration.
`capacity` is optional and must describe this vehicle. Available fields and units
come from the provider. Do not copy optional example capacity to unrelated cars.
Set in `local_config.py`:

```python
DATA_SOURCE = "evcc"
EVCC_BINARY = "/data/setupOptions/dbus-ev/bin/vehicle-engine"
EVCC_CONFIG_FILE = "/data/setupOptions/dbus-ev/vehicle.json"
EVCC_STATE_FILE = "/data/setupOptions/dbus-ev/vehicle-state.json"
EVCC_POLL_INTERVAL = 3600.0
EVCC_STALE_TIMEOUT = 7500.0
HA_MQTT_ENABLED = False
```

Or select the source through SetupHelper after configuring and installing the
optional engine: `./setup install --source=evcc --ha-mqtt=off`.
`python3 configure.py --source evcc` persists the same source choice. Saved
SetupHelper options override `local_config.py`; changing back requires
`--source=mercedes` or `--source=ha`. Installation validates the selected local
configuration/dependencies before stopping the running service; it never logs in.

Use one state file/owner per account. A process lock prevents a second dbus-ev
worker from using that state and token database. This release still represents
one explicitly selected vehicle per installation; it is not multi-car scheduling.
Stop other cloud integrations for this account before enabling the provider.
The optional local charger remains a single independent D-Bus entity.

## Authorization and recovery

For BMW/Mini, Ford and Volvo templates with an OAuth flow, stop the daemon and run:

```sh
python3 -m dbus_ev.providers.evcc \
  --binary /data/setupOptions/dbus-ev/bin/vehicle-engine \
  --config /data/setupOptions/dbus-ev/vehicle.json \
  --state-file /data/setupOptions/dbus-ev/vehicle-state.json
```

This is an explicit interactive action. It prints a manufacturer login URL/code,
validates OAuth state for redirect flows, and stores tokens in a private SQLite
file beside the state file. It never prints tokens or sends vehicle commands.
For templates without interactive OAuth, place the required credentials/API keys
or access/refresh tokens in the JSON using the upstream instructions. The same
command acknowledges corrected configuration and releases a failed-login latch.
Persisted manufacturer HTTP cooldowns remain in effect even after this command.
Do not copy a token database while another process is writing it.

## Traffic and freshness

- Default read cycle: once per hour, with a 30-minute floor (BMW: one hour).
  D-Bus/Desktop/MQTT reads use the local cache. One cycle may need several HTTP
  requests for different fields; it is not equivalent to one request.
- One persistent engine/provider, not a new CLI invocation/login per reading.
  Starting a provider reserves the next automatic initialization for six hours.
  Failed authorization/configuration needs the explicit recovery command.
- HTTP calls made through evcc's request transport are serialized, spaced by at
  least two seconds and capped at 60 attempts per one-hour budget window. The
  counters and cooldowns are saved before network I/O. HTTP 429 pauses subsequent
  calls for 30 minutes, increasing to six hours; longer `Retry-After` is respected.
  HTTP 401/403 pauses calls for at least six hours. Third-party SDKs with their
  own transports may not pass through this hook; the outer cycle and login
  reservations still apply. These are experimental adapters, not measured API
  traffic guarantees for every brand.
- Mandatory patches remove automatic refresh from Nissan/CarWings,
  Toyota/Lexus and Fiat/Jeep reads. BMW stream reconnection starts at five minutes,
  backs off to six hours, and disables Paho's independent automatic reconnect.
  MG deferred-result retries are reduced to three attempts 20 seconds apart.
  The package never invokes vehicle wake, charging, climate or lock commands.
  BMW can create the telemetry container required by CarData, but does not delete
  existing containers belonging to other installations.
- Last successful collection time is retained across local cache reads. Provider
  failures do not renew it. After `EVCC_STALE_TIMEOUT`, availability goes offline.
  evcc does not expose a common manufacturer measurement timestamp: collection
  time is **not** proof that the manufacturer cache contains a recent measurement.
- SoC/limits are percent, power is W, energy capacity kWh, distances km. Unsupported
  or invalid values remain unknown, not zero. Most evcc vehicle providers expose
  SoC/status but no instantaneous charging power. A local charger meter supplies
  charger power only; it is not relabeled as measured vehicle/battery power.

## MQTT without automatic HA entities

`HA_MQTT_ENABLED = True` optionally publishes raw JSON for other brands to
`ev/<CERBO_PORTAL_ID>/<BUS_SUFFIX>/state`, with retained
`ev/<CERBO_PORTAL_ID>/<BUS_SUFFIX>/availability` (`online` / `offline`).
No `homeassistant/.../config` discovery messages or automatic HA sensors are
created. HA consumers can be configured manually if desired. Mercedes retains
its existing `mercedes/...` topics and accompanying receiver.

The state contains `schema`, `source`, `sampled_at` (collection Unix timestamp),
`soc`, `target_soc`, `power`, `battery_capacity`, `range_to_go`, `odometer`,
`charging_status`, `latitude`, `longitude`, and `at_site`. Missing fields are
JSON `null`. State is republished only after a successful new collection or MQTT
reconnection. Consumers must respect availability and their own timestamp expiry,
including when reading retained messages after broker restart. Location is
included only when provided; enable publication only to the intended local broker.

## Offline checks

```sh
python3 vehicle-engine/build.py test -race ./...
python3 vehicle-engine/build.py vet ./...
.venv-ci/bin/python -m pytest tests/
```

Tests cover all catalog template rendering, units/unknown values, read-only
capability selection, HTTP budgets, 429 and restart persistence, process ownership,
pipe timeouts, snapshot expiry, generic charger projection and raw MQTT without
HA discovery. Hardware validation remains outstanding for every new provider.
