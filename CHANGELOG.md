# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are explained in [docs/versioning.md](docs/versioning.md).

## Unreleased

## 0.2.0 - 2026-10-07

Prebuilt engines contain the control allocation code of PX4 v1.17.0
(`engine_schema` 1), as in 0.1.0.

### Added

- Fixed-wing vehicles (`CA_AIRFRAME` 1). The golden tests now cover the 23
  plane airframe scripts of PX4 v1.17.0 and the SITL cross-check includes
  PX4's SIH plane. New examples `examples/fixed_wing.params` and
  `examples/fixed_wing_thrust_offset.params`. An engine built from this
  version is needed; the prebuilt engines of 0.1.0 report the airframe as not
  supported.
- Rule CA021: a rotor has geometry parameters but its index is
  `CA_ROTOR_COUNT` or higher, so PX4 ignores it. New example
  `examples/hexa_rotor_count_4.params`.
- `install check` workflow: follows the install steps, with uv and with a
  virtual environment, with the files of a published release on clean
  machines.

### Changed

- The install instructions recommend `uv tool install`, with pipx and a
  virtual environment as alternatives.

## 0.1.0 - 2026-10-02

First release. Prebuilt engines contain the control allocation code of PX4
v1.17.0 (`engine_schema` 1).

### Added

- Engine built against PX4 v1.17.0 that writes the effectiveness and mix
  matrices as JSON (`engine_schema` 1). Supported `CA_AIRFRAME` values: 0
  (multirotor) and 2 (standard VTOL).
- Command line tool with text and JSON reports. Input formats: plain, PX4
  airframe script, QGroundControl export.
- Rules CA001, CA002, CA003, CA004, CA010, CA011 and CA020.
- Golden tests over the airframe scripts shipped with PX4 v1.17.0 and a
  cross-check against PX4 SITL.
- `--format markdown` for reports that are pasted into issues and pull
  requests.
- `px4-ca-lint diff BEFORE AFTER` compares two parameter files: parameters,
  matrix values and findings.
- Prebuilt engines for Linux x86_64, Linux arm64 and macOS arm64, with
  checksums and build provenance.
- A downloaded engine is found in `~/.local/share/px4-ca-lint/`.
- Findings link to the document of their rule.
