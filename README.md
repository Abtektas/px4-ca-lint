# px4-ca-lint

Check a PX4 control allocation configuration before it flies.

`px4-ca-lint` reads the `CA_*` parameters of a vehicle from a file, runs PX4's
own actuator effectiveness and control allocation code on them, and reports the
resulting matrices. No vehicle and no simulator are needed.

**Status: early development.** There is no release and the output format and
the rules can still change.

## Safety and liability

- This software is provided "as is", without warranty of any kind. See
  [LICENSE](LICENSE).
- It is a review aid. It does not approve a vehicle as safe or airworthy.
- A report without findings does not mean the configuration is safe. The tool
  only checks what it knows about.
- It does not replace bench tests, motor tests without propellers, or careful
  step-by-step flight testing.
- You decide whether to fly, and you are responsible for the result. The
  authors accept no liability for damage, injury or loss of any kind.
- This project is not affiliated with or endorsed by the PX4 project or the
  Dronecode Foundation.

## How it works

The engine is a small program that is compiled against a PX4 source tree. It
uses PX4's parameter system and the same classes the `control_allocator` module
uses, so the matrices are the ones that PX4 version computes. The PX4 tree is
not modified; the engine is built through PX4's external modules mechanism.

The output names the PX4 version and commit the engine was built against. A
result is only valid for that PX4 version.

## Usage

Build the engine once. This needs a PX4 checkout that can build
`px4_sitl_test`:

```
engine/build.sh <path to PX4-Autopilot>
```

Then run the tool on a parameter file (Python 3.11 or newer, no dependencies):

```
python3 -m px4_ca_lint examples/standard_vtol_pusher_offset.params
python3 -m px4_ca_lint --format json examples/standard_vtol_pusher_offset.params
```

The engine is looked up in `--engine PATH`, then `$PX4_CA_ENGINE`, then
`build/engine/px4_ca_engine`.

Accepted parameter files:

| Format | Looks like |
|---|---|
| plain | `CA_ROTOR_COUNT 5` |
| PX4 airframe script | `param set-default CA_ROTOR_COUNT 5` |
| QGroundControl export | tab separated, `1  1  CA_ROTOR_COUNT  5  6` |

Parameters that are not in the file keep PX4's default value. For an airframe
script, files it sources (such as `rc.fw_defaults`) are read when the script is
inside a PX4 `ROMFS` directory; `if` blocks are not evaluated. The report says
so when either applies.

Supported `CA_AIRFRAME` values so far: 0 (multirotor) and 2 (standard VTOL).

## Findings

| Rule | Level | Finds |
|---|---|---|
| [CA001](rules/CA001.md) | error | PX4 produced no usable effectiveness matrix |
| [CA002](rules/CA002.md) | error | PX4 dropped a control axis |
| [CA003](rules/CA003.md) | error | a matrix contains NaN or infinity |
| [CA004](rules/CA004.md) | warning | PX4 ignores an axis with weak authority |
| [CA010](rules/CA010.md) | warning | thrust gain above the limit |
| [CA011](rules/CA011.md) | warning | thrust command to an actuator that produces no thrust on that axis |
| [CA020](rules/CA020.md) | warning | a motor is not used for roll or pitch |

Options: `--ignore CA011,CA020` skips rules, `--max-thrust-gain` sets the limit
of CA010, `--fail-on warning|error|never` chooses what gives exit code 1 (the
default is `error`).

| Exit code | Meaning |
|---|---|
| 0 | report produced, nothing at or above the `--fail-on` level |
| 1 | report produced, findings at or above the `--fail-on` level |
| 2 | no report: bad arguments, unreadable file, engine missing or failed, unsupported airframe |

Tests: `python3 -m unittest discover -s tests -t .`

## Example

`examples/standard_vtol_pusher_offset.params` is PX4's SIH standard VTOL with
the pusher moved 5 cm above the center of gravity. The pusher gets a thrust
gain of 4.0 instead of 1.0, so it saturates at a thrust setpoint of 0.25
([PX4 issue 28829](https://github.com/PX4/PX4-Autopilot/issues/28829)).

## Versions

See [docs/versioning.md](docs/versioning.md).

## Development

Parts of this project were written with the help of an AI assistant
(Claude). Commits that include such work carry an `Assisted-by:` trailer.

## License

BSD 3-Clause, see [LICENSE](LICENSE). PX4 is licensed separately by the PX4
Development Team under the BSD 3-Clause license; its source code is not part
of this repository.
