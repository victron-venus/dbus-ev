#!/usr/bin/env python3
"""Persist installer options in SetupHelper's package options directory."""

import argparse
import json
import os
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ha-mqtt", choices=("on", "off"), required=True)
    parser.add_argument("--options-file", default="/data/setupOptions/dbus-ev/options.json")
    args = parser.parse_args()
    path = Path(args.options_file)
    # The local installer explicitly selects this file; no network data selects a path.
    options = (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    )  # NOSONAR(S8707)
    options["HA_MQTT_ENABLED"] = args.ha_mqtt == "on"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".options-", dir=path.parent)
    try:
        # mkstemp created this descriptor in the operator-selected options directory.
        with os.fdopen(fd, "w", encoding="utf-8") as stream:  # NOSONAR(S8707)
            json.dump(options, stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"Home Assistant MQTT publication: {args.ha_mqtt}")


if __name__ == "__main__":
    main()
