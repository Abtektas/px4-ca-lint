"""Golden tests over the airframe scripts shipped with PX4.

The reports for every airframe script of a PX4 release are stored in
tests/golden/<PX4 version>/ and compared on every run. This shows when a
change to the tool or the engine changes a result.

They need a PX4 checkout and an engine built against it:

    PX4_CA_PX4_DIR=<PX4-Autopilot> PX4_CA_ENGINE=<px4_ca_engine> python3 -m unittest tests.test_golden

Set PX4_CA_UPDATE_GOLDEN=1 to write the stored reports instead of comparing.
"""

import json
import math
import os
import unittest
from pathlib import Path

from px4_ca_lint.engine import EngineError, find_engine, run_engine
from px4_ca_lint.params import ParamFileError, parse_file
from px4_ca_lint.report import build_report
from px4_ca_lint.rules import check

GOLDEN = Path(__file__).parent / "golden"
PX4_DIR = os.environ.get("PX4_CA_PX4_DIR")
UPDATE = os.environ.get("PX4_CA_UPDATE_GOLDEN") == "1"
AIRFRAME_DIRECTORIES = ("init.d/airframes", "init.d-posix/airframes")
DIGITS = 4
TOLERANCE = 1e-3


def _round(value):
    if isinstance(value, float):
        return round(value, DIGITS) + 0.0

    if isinstance(value, list):
        return [_round(item) for item in value]

    if isinstance(value, dict):
        return {key: _round(item) for key, item in value.items()}

    return value


def summarise(script: Path, engine: Path) -> dict:
    """What is stored for one airframe script."""
    try:
        param_file = parse_file(script)

    except ParamFileError:
        return {"status": "no parameters"}

    if not any(name.startswith("CA_") for name in param_file.params):
        return {"status": "no CA parameters"}

    try:
        engine_result = run_engine(engine, param_file.params)

    except EngineError as error:
        if "not supported yet" not in str(error):
            raise

        return {"status": "unsupported", "ca_airframe": int(float(param_file.params["CA_AIRFRAME"]))}

    report = build_report(param_file, engine_result, check(engine_result, params=param_file.params))
    return _round(
        {
            "status": "checked",
            "airframe": report["airframe"],
            "findings": [
                {key: finding[key] for key in ("rule", "matrix", "axis", "actuators")}
                for finding in report["findings"]
            ],
            "matrices": report["matrices"],
        }
    )


def differences(expected, actual, where="") -> list[str]:
    """Compare two stored reports, numbers with a tolerance."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        result = []

        for key in sorted(expected.keys() | actual.keys()):
            if key not in expected or key not in actual:
                result.append(f"{where}/{key}: only in {'new' if key in actual else 'stored'} report")

            else:
                result += differences(expected[key], actual[key], f"{where}/{key}")

        return result

    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        return [
            line
            for index, (old, new) in enumerate(zip(expected, actual))
            for line in differences(old, new, f"{where}[{index}]")
        ]

    numbers = (int, float)

    if (
        isinstance(expected, numbers)
        and isinstance(actual, numbers)
        and not isinstance(expected, bool)
        and not isinstance(actual, bool)
    ):
        return [] if math.isclose(expected, actual, abs_tol=TOLERANCE) else [f"{where}: {expected} != {actual}"]

    return [] if expected == actual else [f"{where}: {expected!r} != {actual!r}"]


@unittest.skipIf(PX4_DIR is None, "PX4_CA_PX4_DIR is not set")
class Golden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = find_engine()
        probe = run_engine(cls.engine, {"CA_AIRFRAME": "0"})
        cls.version = probe["px4_version"]
        cls.directory = GOLDEN / cls.version
        cls.romfs = Path(PX4_DIR) / "ROMFS" / "px4fmu_common"

    def scripts(self):
        for directory in AIRFRAME_DIRECTORIES:
            for script in sorted((self.romfs / directory).iterdir()):
                if script.is_file() and script.name != "CMakeLists.txt":
                    yield f"{directory.split('/')[0]}/{script.name}", script

    def test_airframe_scripts(self):
        if not UPDATE and not self.directory.is_dir():
            self.skipTest(f"no stored reports for PX4 {self.version}")

        index = {}
        problems = []

        for name, script in self.scripts():
            summary = summarise(script, self.engine)
            index[name] = {key: summary[key] for key in ("status", "ca_airframe") if key in summary}

            if summary["status"] != "checked":
                continue

            index[name]["findings"] = sorted({finding["rule"] for finding in summary["findings"]})
            stored = self.directory / f"{name}.json"

            if UPDATE:
                stored.parent.mkdir(parents=True, exist_ok=True)
                stored.write_text(json.dumps(summary, indent=1) + "\n")

            elif not stored.is_file():
                problems.append(f"{name}: no stored report")

            else:
                problems += [f"{name}{line}" for line in differences(json.loads(stored.read_text()), summary)]

        index_file = self.directory / "index.json"

        if UPDATE:
            index_file.write_text(json.dumps(index, indent=1) + "\n")

        else:
            problems += [f"index{line}" for line in differences(json.loads(index_file.read_text()), index)]

        self.assertEqual(problems, [], "\n" + "\n".join(problems[:40]))


class Differences(unittest.TestCase):
    def test_numbers_within_tolerance_are_equal(self):
        self.assertEqual(differences({"a": [1.0, 2.0]}, {"a": [1.0004, 2]}), [])

    def test_differences_are_located(self):
        self.assertEqual(differences({"a": [1.0, 2.0]}, {"a": [1.0, 2.5]}), ["/a[1]: 2.0 != 2.5"])
        self.assertEqual(len(differences({"a": 1}, {"b": 1})), 2)
        self.assertEqual(len(differences({"a": "x"}, {"a": "y"})), 1)
        self.assertEqual(len(differences([1], [1, 2])), 1)


if __name__ == "__main__":
    unittest.main()
