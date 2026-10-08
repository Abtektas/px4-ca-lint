"""End-to-end tests. They need a built engine and are skipped without one."""

import contextlib
import io
import json
import os
import unittest
from pathlib import Path

from px4_ca_lint.cli import main
from px4_ca_lint.engine import ENGINE_ENV, EngineError, find_engine

try:
    ENGINE = str(find_engine())
except EngineError:
    ENGINE = None


def run(*arguments):
    stdout, stderr = io.StringIO(), io.StringIO()

    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(list(arguments))

    return code, stdout.getvalue(), stderr.getvalue()


class Errors(unittest.TestCase):
    def test_missing_file(self):
        code, _, stderr = run("does/not/exist.params")
        self.assertEqual(code, 2)
        self.assertIn("error", stderr)

    def test_missing_engine(self):
        code, _, stderr = run("--engine", "does/not/exist", "examples/standard_vtol.params")
        self.assertEqual(code, 2)
        self.assertIn("not an executable file", stderr)


@unittest.skipIf(ENGINE is None, f"no engine found (set {ENGINE_ENV})")
class WithEngine(unittest.TestCase):
    def report(self, path):
        code, stdout, _ = run("--engine", ENGINE, "--format", "json", path)
        self.assertEqual(code, 0)
        return json.loads(stdout)

    def pusher_gain(self, path):
        return self.report(path)["matrices"][0]["mix"][4]["thrust_x"]

    def test_pusher_gain(self):
        # PX4 issue #28829: a pusher offset in z raises the pusher's thrust gain
        self.assertAlmostEqual(self.pusher_gain("examples/standard_vtol.params"), 1.0, places=3)
        self.assertAlmostEqual(self.pusher_gain("examples/standard_vtol_pusher_offset.params"), 4.0, places=3)

    def test_qgc_export(self):
        report = self.report("examples/quad_qgc_export.params")
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})
        self.assertEqual(report["input"]["format"], "qgc")
        self.assertEqual(report["airframe"]["num_motors"], 4)
        self.assertEqual(report["matrices"][0]["actuators"], ["motor0", "motor1", "motor2", "motor3"])

    def test_text_report(self):
        code, stdout, _ = run("--engine", ENGINE, "examples/standard_vtol.params")
        self.assertEqual(code, 0)
        self.assertIn("Standard VTOL", stdout)
        self.assertIn("0 error(s), 0 warning(s)", stdout)

    def found(self, path):
        return sorted({finding["rule"] for finding in self.report(path)["findings"]})

    def test_known_problems_trigger_their_rules(self):
        self.assertEqual(self.found("examples/standard_vtol.params"), [])
        self.assertEqual(self.found("examples/quad_qgc_export.params"), [])
        self.assertEqual(self.found("examples/standard_vtol_pusher_offset.params"), ["CA010", "CA011"])
        self.assertEqual(self.found("examples/quad_wrong_spin.params"), ["CA020"])

    def test_missing_rotor_count(self):
        code, stdout, _ = run("--engine", ENGINE, "--format", "json", "examples/no_rotors.params")
        self.assertEqual(code, 1)
        findings = json.loads(stdout)["findings"]
        self.assertEqual([finding["rule"] for finding in findings], ["CA001", "CA021"])
        self.assertEqual(findings[1]["actuators"], ["motor0", "motor1"])

    def test_rotors_beyond_the_count(self):
        # PX4 versions that report dropped axes add CA002 here, which is an error
        example = "examples/hexa_rotor_count_4.params"
        code, stdout, _ = run("--engine", ENGINE, "--format", "json", "--fail-on", "never", example)
        self.assertEqual(code, 0)
        report = json.loads(stdout)
        self.assertEqual(report["airframe"]["num_motors"], 4)
        uncounted = [finding for finding in report["findings"] if finding["rule"] == "CA021"]
        self.assertEqual(len(uncounted), 1)
        self.assertEqual(uncounted[0]["actuators"], ["motor4", "motor5"])
        self.assertIsNone(uncounted[0]["matrix"])

    def test_fixed_wing(self):
        report = self.report("examples/fixed_wing.params")
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})
        self.assertEqual(report["airframe"]["name"], "Fixed Wing")
        self.assertEqual(len(report["matrices"]), 1)
        matrix = report["matrices"][0]
        self.assertEqual(matrix["method"], "pseudo_inverse")
        self.assertEqual(matrix["actuators"], ["motor0", "servo0", "servo1", "servo2", "servo3"])
        # the motor only gets the thrust setpoint, every control surface only its own axis
        commands = [
            {axis: round(value, 3) for axis, value in row.items() if abs(value) > 1e-3} for row in matrix["mix"]
        ]
        self.assertEqual(
            commands, [{"thrust_x": 1.0}, {"roll": -1.0}, {"roll": 1.0}, {"pitch": 1.0}, {"yaw": 1.0}]
        )

    def test_fixed_wing_thrust_offset(self):
        report = self.report("examples/fixed_wing_thrust_offset.params")
        self.assertEqual([finding["rule"] for finding in report["findings"]], ["CA011"])
        self.assertEqual(report["findings"][0]["actuators"], ["servo2"])
        mix = report["matrices"][0]["mix"]
        self.assertAlmostEqual(mix[0]["thrust_x"], 1.509, places=3)
        self.assertAlmostEqual(mix[3]["thrust_x"], 0.491, places=3)

    def test_tailsitter(self):
        report = self.report("examples/tailsitter.params")
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})
        self.assertEqual(report["airframe"]["name"], "VTOL Tailsitter")
        actuators = [matrix["actuators"] for matrix in report["matrices"]]
        self.assertEqual(actuators, [["motor0", "motor1"], ["servo0", "servo1"]])

    def test_tiltrotor(self):
        report = self.report("examples/tiltrotor.params")
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})
        self.assertEqual(report["airframe"]["name"], "VTOL Tiltrotor")
        # the tilt servos come after the control surfaces and are in the matrix of the motors
        self.assertEqual(report["matrices"][0]["actuators"][4:], ["servo4", "servo5"])
        self.assertEqual(report["matrices"][1]["actuators"], ["servo0", "servo1", "servo2", "servo3"])
        self.assertEqual([round(row["yaw"], 3) for row in report["matrices"][0]["mix"]], [0, 0, 0, 0, 1, -1])
        self.assertIn("tiltrotor: matrix 0", report["notes"][-1])

    def test_tiltrotor_tilt_servo_missing(self):
        report = self.report("examples/tiltrotor_tilt_servo_missing.params")
        self.assertEqual([finding["rule"] for finding in report["findings"]], ["CA022"])
        self.assertEqual(report["findings"][0]["actuators"], ["motor0"])
        self.assertEqual(report["airframe"]["num_servos"], 5)

    def test_multirotor_with_tilt(self):
        report = self.report("examples/tricopter_tilt.params")
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0})
        self.assertEqual(report["airframe"]["name"], "MC Tilt")
        matrix = report["matrices"][0]
        self.assertEqual(matrix["actuators"], ["motor0", "motor1", "motor2", "servo0"])
        # yaw comes from the tilt servo alone
        self.assertEqual([round(row["yaw"], 3) for row in matrix["mix"]], [0, 0, 0, -1])
        self.assertEqual(report["notes"], [])

    def test_exit_codes(self):
        warnings = "examples/standard_vtol_pusher_offset.params"
        self.assertEqual(run("--engine", ENGINE, warnings)[0], 0)
        self.assertEqual(run("--engine", ENGINE, "--fail-on", "warning", warnings)[0], 1)
        self.assertEqual(run("--engine", ENGINE, "--fail-on", "warning", "--ignore", "CA010,ca011", warnings)[0], 0)
        self.assertEqual(run("--engine", ENGINE, "examples/no_rotors.params")[0], 1)
        self.assertEqual(run("--engine", ENGINE, "--fail-on", "never", "examples/no_rotors.params")[0], 0)

    def test_diff(self):
        before, after = "examples/standard_vtol.params", "examples/standard_vtol_pusher_offset.params"
        code, stdout, _ = run("diff", "--engine", ENGINE, "--format", "json", before, after)
        self.assertEqual(code, 0)
        diff = json.loads(stdout)
        self.assertEqual(diff["parameters"], [{"name": "CA_ROTOR4_PZ", "before": None, "after": "-0.05"}])
        self.assertEqual(sorted(item["rule"] for item in diff["findings"]["new"]), ["CA010", "CA011"])
        self.assertEqual(len(diff["matrices"]), 6)

    def test_diff_exit_codes(self):
        before, after = "examples/standard_vtol.params", "examples/standard_vtol_pusher_offset.params"
        # only findings that are new in the second file count
        self.assertEqual(run("diff", "--engine", ENGINE, "--fail-on", "warning", before, after)[0], 1)
        self.assertEqual(run("diff", "--engine", ENGINE, "--fail-on", "warning", after, before)[0], 0)
        self.assertEqual(run("diff", "--engine", ENGINE, "--fail-on", "warning", after, after)[0], 0)
        self.assertEqual(run("diff", "--engine", ENGINE, before, "does/not/exist")[0], 2)

    def test_markdown_report(self):
        code, stdout, _ = run("--engine", ENGINE, "--format", "markdown", "examples/quad_wrong_spin.params")
        self.assertEqual(code, 0)
        self.assertIn("**warning [CA020](", stdout)

    def test_unsupported_airframe(self):
        path = Path(os.environ.get("TMPDIR", "/tmp")) / "px4-ca-lint-test-unsupported.params"
        path.write_text("CA_AIRFRAME 5\n")
        self.addCleanup(path.unlink)
        code, _, stderr = run("--engine", ENGINE, str(path))
        self.assertEqual(code, 2)
        self.assertIn("not supported yet", stderr)


if __name__ == "__main__":
    unittest.main()
