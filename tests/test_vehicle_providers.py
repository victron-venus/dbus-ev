"""Hardware-free provider, pacing, freshness, process and MQTT regressions."""

import json
import math
import os
import sys
from unittest.mock import MagicMock

import pytest

from dbus_ev import main
from dbus_ev.cerbo_mqtt import CerboMqtt
from dbus_ev.charger import Charger
from dbus_ev.providers import evcc
from dbus_ev.providers.evcc import Engine, EvccClient
from dbus_ev.vehicle import at_site, normalize

VIN = "WDD00000000000001"


class FakeEngine:
    """A persistent provider double records all upstream poll requests."""

    def __init__(self, *_args):
        self.calls = 0
        self.closed = False
        self.reply = {"schema": 1, "ok": True, "data": {"soc": 0, "status": "C", "power": 7200}}

    def poll(self):
        self.calls += 1
        return self.reply

    def close(self):
        self.closed = True


@pytest.fixture(name="clock")
def fake_clock(monkeypatch):
    current = [100000.0]
    monkeypatch.setattr("dbus_ev.providers.evcc.time.time", lambda: current[0])
    monkeypatch.setattr("dbus_ev.providers.evcc.time.monotonic", lambda: current[0])
    return current


def make_client(tmp_path, **kwargs):
    config = tmp_path / "vehicle.json"
    config.write_text(json.dumps({"template": "hyundai", "vin": VIN}))
    config.chmod(0o600)
    return EvccClient(
        binary=sys.executable,
        config_file=config,
        state_file=tmp_path / "state.json",
        engine_factory=FakeEngine,
        **kwargs,
    )


def test_one_owner_and_one_upstream_cycle_for_repeated_local_reads(tmp_path, clock):
    client = make_client(tmp_path)
    first = client.poll()
    engine = client.engine
    for _ in range(100):
        clock[0] += 1
        snapshot = client.poll()
        assert snapshot["soc"] == 0
        assert snapshot["_source_sample_started_at"] == first["_source_sample_started_at"]
        assert snapshot["sampled_at"] == first["sampled_at"]
    assert engine.calls == 1
    second = make_client(tmp_path)
    with pytest.raises(RuntimeError, match="Another vehicle engine"):
        second.start()
    clock[0] = 103600
    assert client.poll()["ok"]
    assert engine.calls == 2
    assert client.engine is engine
    client.close()
    assert engine.closed


def test_restart_does_not_bypass_login_or_poll_reservations(tmp_path, clock):
    client = make_client(tmp_path)
    client.poll()
    client.close()
    restarted = make_client(tmp_path)
    assert restarted.poll()["ok"] is False
    clock[0] += 3601
    restarted.poll()
    assert restarted.engine is None  # six-hour login reservation survives restart
    clock[0] += 21600
    assert restarted.poll()["ok"]
    restarted.close()
    assert os.stat(tmp_path / "state.json").st_mode & 0o777 == 0o600


def test_rate_limit_stops_engine_and_honors_long_retry_after(tmp_path, clock):
    client = make_client(tmp_path)
    client.poll()
    old = client.engine
    old.reply = {"ok": False, "error": "rate_limit", "retry_after": 86400}
    clock[0] += 3600
    client.poll()
    assert old.closed
    clock[0] += 21600
    assert not client.poll()["ok"]
    assert client.engine is None
    client.close()
    client = make_client(tmp_path)
    client.poll()
    assert client.engine is None
    clock[0] += 86400
    assert client.poll()["ok"]
    client.close()


@pytest.mark.parametrize("error", ["auth", "configuration", "storage"])
def test_auth_failure_requires_manual_recovery_even_after_restart(tmp_path, clock, error):
    client = make_client(tmp_path)
    client.poll()
    client.engine.reply = {"ok": False, "error": error}
    clock[0] += 3600
    client.poll()
    client.close()
    clock[0] += 86400 * 10
    client = make_client(tmp_path)
    assert not client.poll()["ok"]
    assert client.engine is None
    client.close()


def test_transient_errors_expire_cached_snapshot_without_refreshing_age(tmp_path, clock):
    client = make_client(tmp_path)
    original = client.poll()
    client.engine.reply = {"ok": False, "error": "provider"}
    clock[0] += 3600
    assert client.poll()["ok"]
    clock[0] += 4000
    latest = client.poll()
    assert not latest["ok"]
    assert latest["_source_sample_started_at"] == original["_source_sample_started_at"]
    client.close()


def test_broken_engine_is_closed_without_immediate_relogin(tmp_path, clock):
    client = make_client(tmp_path)
    client.poll()
    engine = client.engine
    engine.poll = MagicMock(side_effect=TimeoutError)
    clock[0] += 3600
    client.poll()
    assert engine.closed
    assert client.engine is None
    clock[0] += 3600
    client.poll()
    assert client.engine is None
    client.close()


@pytest.mark.parametrize("value", [None, True, "50", math.nan, math.inf, -1, 101])
def test_bad_soc_cannot_publish_fresh_snapshot(tmp_path, clock, value):
    client = make_client(tmp_path)
    client.factory = lambda *_: FakeEngine()
    client.start()
    client.engine = FakeEngine()
    client.engine.reply = {"ok": True, "data": {"soc": value}}
    assert client.poll()["ok"] is False
    client.close()


def test_private_config_and_finite_intervals_required(tmp_path):
    client = make_client(tmp_path, interval=1)
    assert client.interval == 1800
    client.config_file.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        EvccClient(
            binary=sys.executable, config_file=client.config_file, state_file=tmp_path / "state"
        )
    with pytest.raises(ValueError, match="finite"):
        make_client(tmp_path, stale_timeout=math.nan)
    with pytest.raises(ValueError, match="exceed"):
        make_client(tmp_path, stale_timeout=100)


@pytest.mark.parametrize(
    "state,ev,charger", [("A", 0, 0), ("B", 0, 1), ("C", 3, 2), ("?", None, None)]
)
def test_common_units_unknowns_and_charger_mapping(state, ev, charger):
    snapshot = normalize({"soc": 0, "target_soc": 100, "status": state, "odometer": 150.5}, vin=VIN)
    assert snapshot["soc"] == 0
    assert snapshot["odometer"] == 150.5
    assert snapshot["charging_state"] == ev
    assert snapshot["charger_status"] == charger
    assert snapshot["power"] is None
    assert snapshot["at_site"] is None
    assert at_site({"latitude": 40, "longitude": 50}, (40, 50, 150)) is True
    assert at_site({"latitude": 41, "longitude": 50}, (40, 50, 150)) is False


def test_shared_charger_uses_generic_status_and_local_meter():
    charger = Charger(instance=40, version="test", bus_suffix="charger")
    snapshot = normalize({"soc": 60, "status": "C"}, vin=VIN)
    snapshot.update(ok=True, at_site=True)
    charger.update(snapshot, {"/Ac/Power": 7400}, require_meter=True)
    assert charger.service.svc["/Connected"] == 1
    assert charger.service.svc["/Status"] == 2
    assert charger.service.svc["/Ac/Power"] == 7400


def test_mqtt_raw_only_never_discovery_no_duplicates_and_staleness():
    wire = MagicMock()
    wire.publish.return_value.rc = 0
    mqtt = CerboMqtt(
        host="localhost",
        port=1883,
        portal="portal",
        source="evcc",
        vehicle_id="car",
        publish_ha=True,
        client=wire,
    )
    mqtt._on_connect(wire, None, None, 0)  # pylint: disable=protected-access
    snapshot = normalize({"soc": 0, "status": "C"}, vin=VIN)
    snapshot.update(ok=True, sampled_at=100, source="evcc:hyundai")
    mqtt.tick(snapshot)
    calls = wire.publish.call_args_list
    assert [c.args[0] for c in calls] == ["ev/portal/car/state", "ev/portal/car/availability"]
    data = json.loads(calls[0].args[1])
    assert data["soc"] == 0 and data["power"] is None
    mqtt.tick(snapshot)
    assert wire.publish.call_count == 2
    mqtt.tick(dict(snapshot, ok=False))
    assert wire.publish.call_args.args == ("ev/portal/car/availability", "offline")
    assert all(not c.args[0].startswith("homeassistant/") for c in wire.publish.call_args_list)


def test_mqtt_generic_opt_out_does_not_publish():
    wire = MagicMock()
    mqtt = CerboMqtt(
        host="localhost",
        port=1883,
        portal="portal",
        source="evcc",
        vehicle_id="car",
        publish_ha=False,
        client=wire,
    )
    mqtt._on_connect(wire, None, None, 0)  # pylint: disable=protected-access
    mqtt.tick({"ok": True, "soc": 50, "sampled_at": 100})
    wire.publish.assert_not_called()


def test_real_pipe_protocol_reuses_process_and_rejects_bad_schema(tmp_path):
    script = tmp_path / "engine"
    script.write_text(
        f"#!{sys.executable}\nimport sys,json\n"
        "for line in sys.stdin:\n print(json.dumps({'schema':1,'ok':True,'data':{'soc':0}}),flush=True)\n"
    )
    script.chmod(0o700)
    engine = Engine(str(script), tmp_path / "config", tmp_path / "db", timeout=2)
    pid = engine.process.pid
    assert engine.poll()["data"]["soc"] == 0
    assert engine.poll()["data"]["soc"] == 0
    assert engine.process.pid == pid
    engine.close()
    assert engine.process.returncode == 0


def test_pipe_timeout_is_bounded_and_process_reaped(tmp_path):
    script = tmp_path / "engine"
    script.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(100)\n")
    script.chmod(0o700)
    engine = Engine(str(script), tmp_path / "config", tmp_path / "db", timeout=0.01)
    with pytest.raises(TimeoutError):
        engine.poll()
    engine.close()
    assert engine.process.returncode is not None


def test_main_wires_generic_provider_without_loading_mercedes(monkeypatch):
    client = FakeEngine()
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(evcc, "EvccClient", factory)
    monkeypatch.setattr(main.config, "DATA_SOURCE", "evcc")
    monkeypatch.setattr(main.config, "CHARGER_ENABLED", True)
    monkeypatch.setattr(main.config, "HA_MQTT_ENABLED", False)
    monkeypatch.setattr(main.config, "CERBO_METER_INSTANCE", None)
    app = main.build_app()
    assert app.client is client
    assert app.stale_timeout == main.config.EVCC_STALE_TIMEOUT
    assert app.loop_interval_ms == 1000
    assert app.charger is not None
    app.shutdown()
    assert client.closed


def test_manual_recovery_preserves_latch_on_failed_authorization(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"blocked": True}))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "authorize",
            "--binary",
            "/fake/engine",
            "--config",
            "/fake/private.json",
            "--state-file",
            str(path),
        ],
    )
    run = MagicMock()
    run.return_value.returncode = 1
    monkeypatch.setattr(evcc.subprocess, "run", run)
    assert evcc.main() == 1
    assert json.loads(path.read_text())["blocked"] is True
    run.return_value.returncode = 0
    assert evcc.main() == 0
    assert json.loads(path.read_text())["blocked"] is False


def test_manual_authorization_preserves_literal_cli_paths(tmp_path, monkeypatch):
    captured = tmp_path / "arguments.json"
    script = tmp_path / "engine ; literal"
    script.write_text(
        f"#!{sys.executable}\nimport json,sys\n"
        f"with open({str(captured)!r}, 'w') as out: json.dump(sys.argv[1:], out)\n"
    )
    script.chmod(0o700)
    # Leading option syntax and shell metacharacters must remain a single value.
    config = "--authorize ; $(touch injected)"
    state = tmp_path / "state with spaces.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["authorize", "--binary", str(script), f"--config={config}", "--state-file", str(state)],
    )
    assert evcc.main() == 0
    assert json.loads(captured.read_text()) == [
        f"--config={config}",
        f"--database={state}.db",
        "--authorize",
    ]
    assert not (tmp_path / "injected").exists()


@pytest.mark.parametrize("output", ['{"schema":2}', "[]", "not json", '"' + "x" * 70000 + '"'])
def test_invalid_pipe_reply_is_rejected(tmp_path, output):
    script = tmp_path / "engine"
    script.write_text(
        f"#!{sys.executable}\nimport sys\nsys.stdin.readline()\nprint({output!r},flush=True)\n"
    )
    script.chmod(0o700)
    engine = Engine(str(script), tmp_path / "config", tmp_path / "db", timeout=2)
    try:
        with pytest.raises(ValueError):
            engine.poll()
    finally:
        engine.close()
