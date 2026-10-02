# Versioning

Three things have a version, and they change independently.

## 1. The tool

Semantic versioning, `MAJOR.MINOR.PATCH`. Before 1.0.0 a minor release may
change the output or the rules. Between releases the version on `main` ends in
`.dev0`.

A release is made by a tag `vX.Y.Z`. The release workflow runs every test,
builds the engines and creates a draft GitHub Release, which is published by
hand. Each release names the PX4 version of its prebuilt engines.

| Tool | Date | PX4 of the prebuilt engines | `engine_schema` |
|---|---|---|---|
| 0.1.0 | 2026-10-02 | v1.17.0 | 1 |

## 2. The engine output (`engine_schema`)

An integer in the engine's JSON output. It increases whenever a field is
removed or changes meaning. Adding a field does not increase it.

| `engine_schema` | Since | Notes |
|---|---|---|
| 1 | development | first format |

`dropped_axes_bitmask` is `null` when the PX4 version the engine was built
against does not report dropped axes (PX4 v1.17.0 does not).

The Python tool checks `engine_schema` and refuses output it does not know.

## 3. PX4

The engine is compiled against one PX4 commit and writes that commit into its
output (`px4_version`, `px4_commit`). A result is only valid for that PX4
version.

| PX4 | Commit | Status | Checked on |
|---|---|---|---|
| `v1.17.0` (latest stable release, 2026-05-13) | `d6f12ad1c4` | target of the first release; all tests pass, including golden tests and SITL cross-check, on macOS arm64 and Linux arm64 | 2026-10-02 |
| `v1.18.0-beta1-934-g8c243a2cd6` (main) | `8c243a2cd6` | builds, unit and end-to-end tests pass; no golden reports, no cross-check | 2026-10-02 |

Both builds give identical matrices for the files in `examples/`.

Known differences between PX4 versions that the engine handles:

- `ControlAllocation::getDroppedAxes()` does not exist in `v1.17.0`. The engine
  build detects this and writes `null`.

Supported `CA_AIRFRAME` values so far: 0 (multirotor), 2 (standard VTOL).

## Python

The tool needs Python 3.11 or newer and has no runtime dependencies. Python
3.10 reached end of life on 2026-10-01 and is not supported.

| Thing | Version | Notes |
|---|---|---|
| Python | 3.14.8 and 3.12.3 | tested locally; CI covers 3.11 to 3.14 |
| hatchling (build backend) | `>=1.32` (1.32.4 was the latest on 2026-10-02) | only needed to install or package |
| Tests | standard library `unittest` | no test dependency |

## Build environments checked

These are the versions the engine was built and tested with, not minimum
requirements.

| | macOS | Linux |
|---|---|---|
| System | Darwin 27.0.0, arm64 | Ubuntu 24.04 in PX4's `px4-dev` container (`v1.17.0-rc2` image), arm64 |
| Compiler | Apple clang 21.0.0 | GCC 13.3.0 |
| CMake | 4.4.3 | 3.28.3 |
| Ninja | 1.13.2 | from the container |
| Python | 3.14.8 | 3.12.3 |

Linux x86_64 is built and tested by the CI workflow.

Python for PX4's build scripts: the `.venv` of a PX4 checkout, or the one named
by `PX4_CA_PYTHON`.

The engine is built with PX4's `px4_sitl_default` configuration and only the
`px4_ca_engine` target is built. The build scripts skip the Gazebo and Protobuf
lookups, because the tool does not need them and PX4 v1.17.0 does not build
against every installed Gazebo and Protobuf version.

## Prebuilt engines

`engine/package.sh` puts a built engine, this project's license and PX4's
license into an archive named
`px4_ca_engine-px4-<PX4 version>-schema<engine_schema>-<platform>.tar.gz` with a
SHA-256 checksum. The CI workflow builds these for every push:

| Platform | Built on | Needs |
|---|---|---|
| `linux-x86_64` | Ubuntu 24.04 (PX4's `px4-dev` container), GCC | glibc 2.38 or newer (Ubuntu 24.04; not Ubuntu 22.04 or Debian 12); the C++ runtime is linked statically |
| `linux-arm64` | the same, on an arm64 runner | the same |
| `macos-arm64` | macOS 26 runner, Apple clang | macOS 14 or newer (`PX4_CA_MACOS_TARGET` when building) |

The script prints the exact glibc symbol version and the macOS minimum version
of each build. A package is refused when the PX4 tree it was built from had
local changes.

## Continuous integration

`.github/workflows/tests.yml`, versions checked on 2026-10-02:

| Thing | Version |
|---|---|
| Runner | `ubuntu-24.04` |
| `actions/checkout` | v7.0.1, pinned by commit |
| `actions/setup-python` | v7.0.0, pinned by commit |
| Python job | 3.11, 3.12, 3.13, 3.14 |
| `actions/upload-artifact` | v7.0.1, pinned by commit |
| `actions/download-artifact` | v8.0.1, pinned by commit |
| `actions/attest-build-provenance` | v4.2.2, pinned by commit |
| `build` (Python packaging) | 1.6.1 |
| Linux engine jobs | `ubuntu-24.04` and `ubuntu-24.04-arm`, container `px4io/px4-dev:v1.17.0` |
| macOS engine job | `macos-26`, Python 3.13 for PX4's build scripts |
