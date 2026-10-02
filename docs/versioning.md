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

## 3. PX4

The engine is compiled against one PX4 commit and writes that commit into its
output (`px4_version`, `px4_commit`). A result is only valid for that PX4
version.

| PX4 | Status | Checked on |
|---|---|---|
| `v1.17.0` (latest stable release, 2026-05-13) | target for the first release, not built yet | - |
| `v1.18.0-beta1-934-g8c243a2cd6` (main, 2026-10-02) | builds, examples give the expected values | 2026-10-02 |

Supported `CA_AIRFRAME` values so far: 0 (multirotor), 2 (standard VTOL).

## Build tools used so far

These are the versions the engine was built with, not minimum requirements.

| Tool | Version |
|---|---|
| macOS (arm64) | Darwin 27.0.0 |
| Apple clang | 21.0.0 |
| CMake | 4.4.3 |
| Ninja | 1.13.2 |
| Python (PX4 build scripts) | PX4's own `.venv` |
