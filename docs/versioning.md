# Versioning

Three things have a version, and they change independently.

## 1. The tool

Semantic versioning, `MAJOR.MINOR.PATCH`. Before 1.0.0 a minor release may
change the output or the rules. No version has been released yet; the first
will be `0.1.0`.

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
| `v1.17.0` (latest stable release, 2026-05-13) | `d6f12ad1c4` | builds, tests pass; target of the first release | 2026-10-02 |
| `v1.18.0-beta1-934-g8c243a2cd6` (main) | `8c243a2cd6` | builds, tests pass | 2026-10-02 |

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
| Python | 3.14.8 | the only version tested so far; 3.11 to 3.13 will be covered by CI |
| hatchling (build backend) | `>=1.32` (1.32.4 was the latest on 2026-10-02) | only needed to install or package |
| Tests | standard library `unittest` | no test dependency |

## Build tools used so far

These are the versions the engine was built with, not minimum requirements.

| Tool | Version |
|---|---|
| macOS (arm64) | Darwin 27.0.0 |
| Apple clang | 21.0.0 |
| CMake | 4.4.3 |
| Ninja | 1.13.2 |
| uv | 0.12.22 |
| Python for PX4's build scripts | the `.venv` of a PX4 checkout (`PX4_CA_PYTHON`) |

PX4's `px4_sitl_test` configuration downloads abseil and fuzztest into the
build directory during configuration. The engine build skips the Gazebo lookup,
because it does not need Gazebo.
