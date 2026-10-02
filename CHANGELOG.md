# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are explained in [docs/versioning.md](docs/versioning.md).

## Unreleased

Nothing has been released yet. The first release will be 0.1.0.

### Added

- Engine built against PX4 v1.17.0 that writes the effectiveness and mix
  matrices as JSON (`engine_schema` 1). Supported `CA_AIRFRAME` values: 0
  (multirotor) and 2 (standard VTOL).
- Command line tool with text and JSON reports. Input formats: plain, PX4
  airframe script, QGroundControl export.
- Rules CA001, CA002, CA003, CA004, CA010, CA011 and CA020.
- Golden tests over the airframe scripts shipped with PX4 v1.17.0 and a
  cross-check against PX4 SITL.
