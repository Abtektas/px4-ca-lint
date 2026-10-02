# Contributing

Issues and pull requests are welcome. Everything in this repository is written
in English.

## Before you start

- Read the "Safety and liability" section of the [README](README.md). A rule
  that tells people their vehicle is fine when it is not is worse than no rule.
- For a new rule, open an issue first and describe the configuration mistake it
  finds, ideally with a parameter file that shows it.

## Running the tests

```
python3 -m unittest discover -s tests -t .
```

This needs Python 3.11 or newer and nothing else. Tests that need the engine, a
PX4 checkout or a PX4 SITL build are skipped unless the environment variables
described in `tests/test_golden.py` and `tests/test_sitl.py` are set. The CI
workflow runs all of them.

## What a change needs

- Tests. A rule needs one case that triggers it and one that does not.
- A document in `rules/` for every rule.
- No copy of PX4's source code or mathematics. The engine calls PX4's classes.
  Where it has to repeat PX4 logic, the code names the PX4 function it follows,
  and the SITL cross-check covers it.
- If a change alters stored golden reports, say why in the pull request.
- An entry in [CHANGELOG.md](CHANGELOG.md).

## Commits

- Sign off your commits (`git commit -s`). The sign-off certifies the
  [Developer Certificate of Origin](https://developercertificate.org/).
- If an AI assistant helped with a change, say so with an `Assisted-by:`
  trailer in the commit message. Do not add an AI as co-author. You are
  responsible for everything you submit.

## Versions

Read [docs/versioning.md](docs/versioning.md) before you change the engine
output, the supported PX4 version or a dependency. State the versions you
tested with.
