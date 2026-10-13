#!/bin/sh
# Provision verified wheels into package-local storage, never system Python.
set -eu
SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
if [ "$#" -gt 1 ]; then
    echo "Usage: $0 [verified-tls-bundle-directory]" >&2
    exit 2
fi
python3 -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12.x required"'
BUNDLE=${1:-}
if [ -n "$BUNDLE" ]; then
    test -d "$BUNDLE/wheels"
    python3 -m pip install --disable-pip-version-check --upgrade --no-index \
        --only-binary=:all: --require-hashes --find-links "$BUNDLE/wheels" \
        --target /data/setupOptions/dbus-ev/python -r "${SCRIPT_DIR}/requirements-tls-armv7.txt"
else
    case "$(uname -m)" in
        armv7*|armv8l)
            echo "ARMv7 requires the reviewed offline TLS bundle; see docs/tls-dependencies.md" >&2
            exit 2
            ;;
        *)
            # Other architectures use only matching hash-pinned binary wheels.
            :
            ;;
    esac
    python3 -m pip install --disable-pip-version-check --upgrade \
        --only-binary=:all: --require-hashes --target /data/setupOptions/dbus-ev/python \
        -r "${SCRIPT_DIR}/requirements-tls.txt"
fi
PYTHONPATH="/data/setupOptions/dbus-ev/python${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -c 'import cryptography, cffi; from cryptography import x509; print("TLS dependencies:", cryptography.__version__, cffi.__version__)'
