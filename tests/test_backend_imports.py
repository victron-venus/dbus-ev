"""Unused network backends must not consume memory on the GX."""

import subprocess
import sys


def test_mercedes_and_evcc_do_not_load_ha_http_stack():
    # Run in isolation: other test modules intentionally import requests to
    # exercise the HA backend, which would hide an accidental eager import.
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, types; "
                "sys.modules['local_config'] = types.ModuleType('local_config'); "
                "import dbus_ev.main; "
                "import dbus_ev.mercedes.client; "
                "import dbus_ev.providers.evcc; "
                "assert 'requests' not in sys.modules; "
                "assert 'urllib3' not in sys.modules"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
