# Offline TLS dependencies on ARMv7

The certificate-key policy needs `cryptography==50.0.2`, `cffi==2.1.1` and
`pycparser==3.11`. PyPI provides an ARMv7 cryptography wheel but no corresponding
CFFI wheel. Do not run an unbounded native dependency build on a working Cerbo.
The dedicated CI job builds and verifies a separate offline bundle.

## Supported ABI and acceptance

The bundle targets CPython 3.12, Linux ARMv7 hard-float, glibc 2.36 or newer and
`libffi.so.8`. Its CFFI build uses Debian Bookworm. A device model alone does not
establish this ABI; check the actual image and service interpreter:

```sh
python3 -c 'import sys, platform, ctypes; print(sys.version, platform.machine(), platform.libc_ver()); ctypes.CDLL("libffi.so.8")'
```

The build and native import/key-boundary probe are CI checks. They do not test
Mercedes accounts, vehicles, D-Bus hardware or firmware upgrade acceptance. Keep
the existing service running until the dependency preflight succeeds. No stable
release or target-device acceptance is claimed by adding this build definition.

## Build and verify

Use the successful **ARMv7 offline TLS dependency bundle** job for the exact
reviewed commit and its `tls-dependencies-cp312-armv7` artifact. To reproduce on a
Docker host with ARMv7 execution enabled:

```sh
docker buildx build --platform linux/arm/v7 \
  --file build-support/tls-armv7/Dockerfile \
  --build-arg SOURCE_REVISION="$(git rev-parse HEAD)" \
  --output type=local,dest=release-dist/tls-armv7 --progress plain .
```

The builder and verifier use immutable official Python 3.12.13 image digests.
Input archives/wheels and build tools have pinned SHA-256 hashes. The native
CFFI compilation runs offline, twice from clean object files; a mismatch fails
the build. A separate non-root verifier installs only the produced wheels with
networking disabled, runs `pip check`, imports their native extensions and
checks certificate-key boundaries. Read `provenance.json`, `repeatability.json`,
`verification.json`, `builder-packages.txt` and the input requirements. The
compiled wheel must match the independently reproduced SHA-256 pinned in the
source-controlled `requirements-tls-armv7.txt`. The finalizer rejects any produced
wheel that differs from this lock; a changed rebuild requires explicit review
and a lock update. The cryptography and pycparser entries also pin their reviewed
official wheel bytes. These records are not cryptographic release signatures.

## Installation

Transfer the complete verified artifact directory to the device, without site
credentials. From the source directory, provision only package-local storage:

```sh
./install-tls-deps.sh /path/to/tls-dependencies-cp312-armv7
# For a new Mercedes installation, this also provisions its optional packages:
./install-mercedes-deps.sh /path/to/tls-dependencies-cp312-armv7
```

The offline installer takes its trusted hashes from `requirements-tls-armv7.txt`
in the source checkout, never from the supplied bundle's `requirements.txt`.
Changing a wheel and regenerating the bundle metadata cannot authorize new bytes.
Obtain the source checkout through the reviewed GitHub HTTPS revision as well.

The scripts use wheel-only, hash-checked installation under
`/data/setupOptions/dbus-ev/python`, preserving system Python. `update.sh` checks
native imports and minimum versions before stopping the old service. The
source archive alone does not include these wheels. Other supported platforms
with the complete official wheel closure can run `install-tls-deps.sh` without
an artifact directory. ARMv7 deliberately requires the offline bundle.
