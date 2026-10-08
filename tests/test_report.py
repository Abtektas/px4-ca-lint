import json
import unittest

from px4_ca_lint import DISCLAIMER
from px4_ca_lint.params import ParamFile
from px4_ca_lint.report import render_json, render_markdown, render_text
from px4_ca_lint.report import build_report as _build_report
from px4_ca_lint.rules import check

ZERO = [0, 0]


def engine_result(**matrix_overrides):
    matrix = {
        "index": 0,
        "num_actuators": 2,
        "method": "pseudo_inverse",
        "normalize_rpy": False,
        "dropped_axes_bitmask": 0,
        "actuators": [{"type": "motor", "index": 0}, {"type": "servo", "index": 0}],
        "weak_axes_zeroed": [],
        "effectiveness": {
            "roll": [1.5, -0.5], "pitch": ZERO, "yaw": ZERO,
            "thrust_x": ZERO, "thrust_y": ZERO, "thrust_z": [-6.5, 0],
        },
        "mix": [
            {"roll": 1, "pitch": 0, "yaw": 0, "thrust_x": 0, "thrust_y": 0, "thrust_z": -1},
            {"roll": -0.0001, "pitch": 0, "yaw": 0, "thrust_x": 0, "thrust_y": 0, "thrust_z": 0},
        ],
    }
    matrix.update(matrix_overrides)
    return {
        "engine_schema": 1,
        "px4_version": "v1.17.0",
        "px4_commit": "d6f12ad1c4f70ad3230afd7d86e971421e02fef4",
        "unknown_parameters": [],
        "parameters_set": 2,
        "ca_airframe": 0,
        "effectiveness_source": "Multirotor",
        "num_motors": 1,
        "num_servos": 1,
        "matrices": [matrix],
    }


def build_report(parsed, result):
    return _build_report(parsed, result, check(result, params=parsed.params))


def param_file():
    return ParamFile(path="x.params", format="plain", params={"CA_AIRFRAME": "0", "CA_ROTOR_COUNT": "1"})


def axes(report):
    return {axis["axis"]: axis for axis in report["matrices"][0]["axes"]}


class Report(unittest.TestCase):
    def test_axis_status_and_authority(self):
        summary = axes(build_report(param_file(), engine_result()))
        self.assertEqual(summary["roll"]["status"], "controlled")
        self.assertAlmostEqual(summary["roll"]["authority"], 2.0)
        self.assertEqual(summary["pitch"]["status"], "not controlled")

    def test_weak_and_dropped_axes(self):
        # bit 2 is yaw
        result = engine_result(weak_axes_zeroed=["pitch"], dropped_axes_bitmask=1 << 2)
        summary = axes(build_report(param_file(), result))
        self.assertEqual(summary["pitch"]["status"], "weak, zeroed by PX4")
        self.assertEqual(summary["yaw"]["status"], "dropped by PX4")

    def test_px4_without_dropped_axes(self):
        summary = axes(build_report(param_file(), engine_result(dropped_axes_bitmask=None)))
        self.assertEqual(summary["roll"]["status"], "controlled")

    def test_unknown_parameters_list_ca_first(self):
        result = engine_result()
        result["unknown_parameters"] = ["AAA_OLD", "CA_GONE"]
        notes = build_report(param_file(), result)["notes"]
        self.assertEqual(len(notes), 1)
        self.assertIn("CA_GONE, AAA_OLD", notes[0])

    def test_tiltrotor_note(self):
        result = engine_result()
        self.assertEqual(build_report(param_file(), result)["notes"], [])
        result["ca_airframe"] = 3
        notes = build_report(param_file(), result)["notes"]
        self.assertEqual(len(notes), 1)
        self.assertIn("CA_SV_TLn_MINA", notes[0])

    def test_findings_are_in_both_formats(self):
        report = build_report(param_file(), engine_result(weak_axes_zeroed=["yaw"]))
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 1})
        self.assertEqual(report["findings"][0]["rule"], "CA004")
        text = render_text(report)
        self.assertIn("warning CA004 matrix 0:", text)
        self.assertIn("0 error(s), 1 warning(s)", text)

    def test_rules_that_could_not_run_are_listed(self):
        report = build_report(param_file(), engine_result(dropped_axes_bitmask=None))
        self.assertIn("CA002", report["rules_not_checked"])
        self.assertIn("CA002 was not checked", render_text(report))

    def test_json_is_valid_and_has_the_disclaimer(self):
        report = json.loads(render_json(build_report(param_file(), engine_result())))
        self.assertEqual(report["disclaimer"], DISCLAIMER)
        self.assertEqual(report["matrices"][0]["actuators"], ["motor0", "servo0"])
        self.assertEqual(report["px4"]["version"], "v1.17.0")

    def test_text(self):
        text = render_text(build_report(param_file(), engine_result()))
        self.assertIn("PX4:       v1.17.0 (d6f12ad1c4)", text)
        self.assertIn("motor0", text)
        self.assertNotIn("-0.000", text)
        self.assertTrue(text.rstrip().endswith(DISCLAIMER))

    def test_markdown(self):
        text = render_markdown(build_report(param_file(), engine_result(weak_axes_zeroed=["yaw"])))
        self.assertIn("### px4-ca-lint report: 0 error(s), 1 warning(s)", text)
        self.assertIn("- **warning [CA004](https://github.com/Abtektas/px4-ca-lint/blob/", text)
        self.assertIn("| axis | motor0 | servo0 |", text)
        self.assertIn("| roll | 1.500 | -0.500 |", text)
        self.assertIn(f"_{DISCLAIMER}_", text)

    def test_markdown_without_findings(self):
        self.assertIn("None.", render_markdown(build_report(param_file(), engine_result())))

    def test_json_lists_the_given_parameters(self):
        report = build_report(param_file(), engine_result())
        self.assertEqual(report["input"]["parameters"], {"CA_AIRFRAME": "0", "CA_ROTOR_COUNT": "1"})


if __name__ == "__main__":
    unittest.main()
