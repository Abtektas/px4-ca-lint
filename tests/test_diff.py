import json
import unittest

from px4_ca_lint import DISCLAIMER
from px4_ca_lint.diff import ABSENT, build_diff, render_json, render_markdown, render_text

AXES = ("roll", "pitch", "yaw", "thrust_x", "thrust_y", "thrust_z")


def finding(rule, actuators=(), matrix=0, axis=None, level="warning"):
    return {
        "rule": rule,
        "level": level,
        "message": f"message of {rule}",
        "matrix": matrix,
        "axis": axis,
        "actuators": list(actuators),
    }


def report(parameters, thrust_x_gain=1.0, actuators=("motor0",), findings=(), commit="abc"):
    """A report as made by report.build_report(), reduced to what the diff reads."""
    count = len(actuators)
    return {
        "input": {"path": "x.params", "parameters": parameters},
        "px4": {"version": "v1.17.0", "commit": commit},
        "summary": {"errors": 0, "warnings": len(findings)},
        "findings": list(findings),
        "matrices": [
            {
                "index": 0,
                "actuators": list(actuators),
                "effectiveness": {axis: [0.0] * count for axis in AXES},
                "mix": [{axis: (thrust_x_gain if axis == "thrust_x" else 0.0) for axis in AXES}] * count,
            }
        ],
    }


class Diff(unittest.TestCase):
    def test_identical_reports(self):
        same = report({"CA_AIRFRAME": "2"}, findings=[finding("CA010")])
        diff = build_diff(same, same)
        self.assertEqual(diff["parameters"], [])
        self.assertEqual(diff["matrices"], [])
        self.assertEqual(diff["findings"], {"new": [], "gone": [], "unchanged": 1})
        self.assertIn("no differences", render_text(diff))

    def test_parameters(self):
        diff = build_diff(
            report({"A": "1", "B": "2.0", "C": "3"}), report({"A": "1.0", "B": "2.5", "D": "4"})
        )
        self.assertEqual(
            diff["parameters"],
            [
                {"name": "B", "before": "2.0", "after": "2.5"},
                {"name": "C", "before": "3", "after": None},
                {"name": "D", "before": None, "after": "4"},
            ],
        )

    def test_matrix_values(self):
        diff = build_diff(report({}, 1.0), report({}, 4.0))
        self.assertEqual(
            diff["matrices"],
            [{"matrix": 0, "kind": "mix", "actuator": "motor0", "axis": "thrust_x", "before": 1.0, "after": 4.0}],
        )
        self.assertIn("matrix 0 mix motor0 thrust_x: 1.000 -> 4.000", render_text(diff))

    def test_small_matrix_differences_are_ignored(self):
        self.assertEqual(build_diff(report({}, 1.0), report({}, 1.0004))["matrices"], [])

    def test_added_actuator(self):
        diff = build_diff(report({}), report({}, actuators=("motor0", "motor1")))
        self.assertEqual(len(diff["matrices"]), 12)
        self.assertTrue(all(change["before"] == ABSENT for change in diff["matrices"]))
        self.assertIn("absent -> 1.000", render_text(diff))

    def test_findings(self):
        diff = build_diff(
            report({}, findings=[finding("CA010", ["motor4"]), finding("CA020", ["motor2"])]),
            report({}, findings=[finding("CA010", ["motor4"]), finding("CA011", ["motor0"])]),
        )
        self.assertEqual([item["rule"] for item in diff["findings"]["new"]], ["CA011"])
        self.assertEqual([item["rule"] for item in diff["findings"]["gone"]], ["CA020"])
        self.assertEqual(diff["findings"]["unchanged"], 1)
        text = render_text(diff)
        self.assertIn("new: warning CA011", text)
        self.assertIn("1 new, 1 gone, 1 unchanged", text)

    def test_different_px4_versions_are_pointed_out(self):
        diff = build_diff(report({}, commit="abc"), report({}, commit="def"))
        self.assertFalse(diff["same_px4"])
        self.assertIn("different PX4 versions", render_text(diff))

    def test_all_formats_have_the_disclaimer(self):
        diff = build_diff(report({"A": "1"}), report({"A": "2"}))
        self.assertTrue(render_text(diff).rstrip().endswith(DISCLAIMER))
        self.assertIn(DISCLAIMER, render_markdown(diff))
        self.assertIn("- `A`: 1 -> 2", render_markdown(diff))
        self.assertEqual(json.loads(render_json(diff))["disclaimer"], DISCLAIMER)


if __name__ == "__main__":
    unittest.main()
