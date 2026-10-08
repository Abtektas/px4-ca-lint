# px4-ca-lint

[![tests](https://github.com/Abtektas/px4-ca-lint/actions/workflows/tests.yml/badge.svg)](https://github.com/Abtektas/px4-ca-lint/actions/workflows/tests.yml)

Check a PX4 control allocation configuration before it flies.

`px4-ca-lint` reads the `CA_*` parameters of a vehicle from a file, runs PX4's
own actuator effectiveness and control allocation code on them, and reports the
resulting matrices and likely configuration mistakes. No vehicle and no
simulator are needed.

It is meant for people who set `CA_*` parameters by hand: custom multirotor
geometries, planes, and standard, tiltrotor and tailsitter VTOLs. This is an
early version; the rules and the output format can still change.

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

## Example

`examples/standard_vtol_pusher_offset.params` is PX4's SIH standard VTOL with
the pusher motor moved 5 cm above the centre of gravity (`CA_ROTOR4_PZ -0.05`).
This is the configuration of
[PX4 issue 28829](https://github.com/PX4/PX4-Autopilot/issues/28829).

```
$ px4-ca-lint examples/standard_vtol_pusher_offset.params
...
  Mix: actuator command per unit of setpoint on each axis
  actuator      roll     pitch       yaw  thrust_x  thrust_y  thrust_z
  motor0      -0.707     0.707     1.000     0.250     0.000    -1.000
  motor1       0.707    -0.707     1.000    -0.250     0.000    -1.000
  motor2       0.707     0.707    -1.000     0.250     0.000    -1.000
  motor3      -0.707    -0.707    -1.000    -0.250     0.000    -1.000
  motor4       0.000     0.000     0.000     4.000     0.000     0.000
...
Findings
  warning CA010 matrix 0: motor4: thrust_x gain up to 4.00 (limit 2); the output saturates at a thrust_x setpoint of 0.25
      thrust gain above the limit: https://github.com/Abtektas/px4-ca-lint/blob/v0.2.0/rules/CA010.md
  warning CA011 matrix 0: motor0, motor1, motor2, motor3: commanded by the thrust_x setpoint without producing thrust_x thrust; a thrust_x setpoint changes their output
      thrust command to an actuator that produces no thrust on that axis: https://github.com/Abtektas/px4-ca-lint/blob/v0.2.0/rules/CA011.md
  CA002 was not checked: this PX4 version does not report dropped axes
  0 error(s), 2 warning(s)
```

Without the offset the pusher has a thrust gain of 1.0 and there are no
findings.

## Install

You need the Python package and the engine for your platform. The tool needs
Python 3.11 or newer and has no Python dependencies. The commands below install
release 0.2.0.

1. The Python package. With [uv](https://docs.astral.sh/uv/), which also
   provides a suitable Python if the system one is too old:

   ```
   uv tool install https://github.com/Abtektas/px4-ca-lint/releases/download/v0.2.0/px4_ca_lint-0.2.0-py3-none-any.whl
   ```

   Without uv, use [pipx](https://pipx.pypa.io/) with the same URL
   (`pipx install <URL>`), or a virtual environment (most Linux distributions
   do not allow `pip install` outside of one):

   ```
   python3 -m venv ~/.venvs/px4-ca-lint
   ~/.venvs/px4-ca-lint/bin/pip install https://github.com/Abtektas/px4-ca-lint/releases/download/v0.2.0/px4_ca_lint-0.2.0-py3-none-any.whl
   export PATH="$HOME/.venvs/px4-ca-lint/bin:$PATH"
   ```

2. The engine. Choose `linux-x86_64`, `linux-arm64` or `macos-arm64`:

   ```
   PLATFORM=linux-x86_64
   NAME=px4_ca_engine-px4-v1.17.0-schema1-$PLATFORM
   BASE=https://github.com/Abtektas/px4-ca-lint/releases/download/v0.2.0
   curl -LO $BASE/$NAME.tar.gz
   curl -LO $BASE/SHA256SUMS
   shasum -a 256 --ignore-missing -c SHA256SUMS
   tar -xzf $NAME.tar.gz
   mkdir -p ~/.local/share/px4-ca-lint
   cp $NAME/px4_ca_engine ~/.local/share/px4-ca-lint/
   ```

   The checksum line must say `OK`. If `shasum` is missing on Linux, use
   `sha256sum --ignore-missing -c SHA256SUMS`. With the GitHub CLI you can also check that
   the file was built by this repository's release workflow:
   `gh attestation verify $NAME.tar.gz -R Abtektas/px4-ca-lint`.

3. Try it:

   ```
   px4-ca-lint --version
   px4-ca-lint your.params
   ```

Requirements of the prebuilt engines:

| Platform | Needs |
|---|---|
| `linux-x86_64`, `linux-arm64` | glibc 2.38 or newer, for example Ubuntu 24.04. Ubuntu 22.04 and Debian 12 are too old. |
| `macos-arm64` | macOS 14 or newer on Apple silicon. Download with `curl` as shown; a file downloaded with a browser is blocked by macOS until you remove its quarantine attribute. |

The prebuilt engines contain the control allocation code of **PX4 v1.17.0**. A
result is only valid for the PX4 version the engine was built against, which
every report names. For another PX4 version or platform, build the engine
yourself, see [Building the engine](#building-the-engine).

The engine is looked up in this order: `--engine PATH`, `$PX4_CA_ENGINE`,
`build/engine/px4_ca_engine` in the current directory,
`~/.local/share/px4-ca-lint/px4_ca_engine` (`$XDG_DATA_HOME` is honoured).

## Usage

```
px4-ca-lint your.params
px4-ca-lint --format json your.params
px4-ca-lint --format markdown your.params
```

The Markdown report is meant for pasting into an issue or pull request.

To see what a parameter change does, compare two files:

```
px4-ca-lint diff before.params after.params
```

This lists the parameters that differ, the matrix values that changed, and the
findings that are new or gone in the second file.

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

Supported `CA_AIRFRAME` values: 0 (multirotor), 1 (fixed-wing), 2 (standard
VTOL), 3 (tiltrotor VTOL), 4 (tailsitter VTOL) and 8 (multirotor with tilt).
Other values give an error, not a report.

For a tiltrotor the matrix of the motors depends on the tilt angle. The report
shows the one PX4 computes after a parameter change, with the tilt servos at
their minimum angle (`CA_SV_TLn_MINA`), the hover position. The matrices PX4
uses during the transition and in forward flight are not covered.

The report shows what goes through the matrices. Control surface trim, flaps
and spoilers (`CA_SV_CSn_TRIM`, `_FLAP`, `_SPOIL`) are applied by PX4 outside
the matrices and are not part of it.

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
| [CA021](rules/CA021.md) | warning | a rotor is configured but not counted by `CA_ROTOR_COUNT` |

CA002 needs a PX4 version newer than v1.17.0; with the prebuilt engines the
report says that it was not checked.

Options: `--ignore CA011,CA020` skips rules, `--max-thrust-gain` sets the limit
of CA010, `--fail-on warning|error|never` chooses what gives exit code 1 (the
default is `error`).

| Exit code | Meaning |
|---|---|
| 0 | report produced, nothing at or above the `--fail-on` level |
| 1 | report produced, findings at or above the `--fail-on` level; for `diff`, only findings that are new in the second file count |
| 2 | no report: bad arguments, unreadable file, engine missing or failed, unsupported airframe |

## How it works

The engine is a small program that is compiled against a PX4 source tree. It
uses PX4's parameter system and the same classes the `control_allocator` module
uses, so the matrices are the ones that PX4 version computes. The Python tool
reads the parameter file, runs the engine, applies the rules and writes the
report.

## How the tool itself is checked

| Check | What it shows | Needs |
|---|---|---|
| Unit tests | parsers, rules and reports behave as documented | Python only |
| End-to-end tests | the examples give the expected findings | the engine |
| Golden tests | the reports for all airframe scripts shipped with PX4 v1.17.0 have not changed | the engine and a PX4 checkout |
| SITL cross-check | the engine's effectiveness matrices equal the ones of a running PX4 (`control_allocator status`) | the engine and a PX4 SITL build |

```
python3 -m unittest discover -s tests -t .
```

Tests whose requirements are missing are skipped. See the comments at the top
of `tests/test_golden.py` and `tests/test_sitl.py` for the environment
variables. `control_allocator status` does not print the mix matrix, so the
cross-check compares the effectiveness matrices only; the mix matrix comes from
the same PX4 class in both cases. PX4 has no SIH airframe with tilt servos, so
for the tiltrotor and the multirotor with tilt the parameters of an example are
set on a running SIH quadrotor.

After every release, the `install check` workflow follows the install steps
above, with uv and with a virtual environment, on clean Linux x86_64, Linux
arm64 and macOS arm64 machines.

[docs/px4-airframes.md](docs/px4-airframes.md) lists the results for PX4's own
airframe scripts.

## Building the engine

This needs a PX4 checkout and the tools PX4 needs to build `px4_sitl_default`:

```
engine/build.sh <path to PX4-Autopilot>
```

The engine is built through PX4's external modules mechanism, into a build
directory outside the PX4 tree. No file tracked by PX4 is changed; PX4's own
build writes a few generated files into its tree, which PX4's `.gitignore`
covers. The PX4 versions that were tried are listed in
[docs/versioning.md](docs/versioning.md).

## Versions

The tool, the engine output and PX4 each have a version. See
[docs/versioning.md](docs/versioning.md) and [CHANGELOG.md](CHANGELOG.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Report security problems as described
in [SECURITY.md](SECURITY.md).

Parts of this project were written with the help of an AI assistant
(Claude). Commits that include such work carry an `Assisted-by:` trailer.

## License

BSD 3-Clause, see [LICENSE](LICENSE). PX4 is licensed separately by the PX4
Development Team under the BSD 3-Clause license. Its source code is not part
of this repository; the prebuilt engines contain compiled PX4 code.
