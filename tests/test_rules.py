import unittest

from px4_ca_lint.rules import RULES, Options, check

AXES = ("roll", "pitch", "yaw", "thrust_x", "thrust_y", "thrust_z")


def matrix(effectiveness, mix, types=None, **overrides):
    """Build one engine matrix from rows given as {axis: [per actuator]} and [per actuator {axis: v}]."""
    count = len(mix)
    types = types or ["motor"] * count
    result = {
        "index": 0,
        "num_actuators": count,
        "method": "pseudo_inverse",
        "normalize_rpy": True,
        "dropped_axes_bitmask": 0,
        "actuators": [{"type": kind, "index": index} for index, kind in enumerate(types)],
        "weak_axes_zeroed": [],
        "effectiveness": {axis: effectiveness.get(axis, [0] * count) for axis in AXES},
        "mix": [{axis: row.get(axis, 0) for axis in AXES} for row in mix],
    }
    result.update(overrides)
    return result


def engine_result(*matrices, **overrides):
    result = {"num_motors": 2, "num_servos": 0, "matrices": list(matrices)}
    result.update(overrides)
    return result


def healthy():
    return matrix(
        {"roll": [-1, 1], "pitch": [1, 1], "thrust_z": [-6.5, -6.5]},
        [{"roll": -0.7, "pitch": 0.7, "thrust_z": -1}, {"roll": 0.7, "pitch": 0.7, "thrust_z": -1}],
    )


def rules(result):
    return [finding.rule for finding in result.findings]


class Rules(unittest.TestCase):
    def test_every_rule_has_a_document(self):
        from pathlib import Path

        for rule in RULES:
            self.assertTrue(Path("rules", f"{rule}.md").is_file(), rule)

    def test_rule_links_follow_the_version(self):
        from unittest import mock

        from px4_ca_lint.rules import rule_url

        with mock.patch("px4_ca_lint.__version__", "0.2.0.dev0"):
            self.assertIn("/blob/main/rules/CA010.md", rule_url("CA010"))

        with mock.patch("px4_ca_lint.__version__", "0.2.0"):
            self.assertIn("/blob/v0.2.0/rules/CA010.md", rule_url("CA010"))

    def test_healthy_matrix_has_no_findings(self):
        result = check(engine_result(healthy()))
        self.assertEqual(result.findings, [])
        self.assertEqual(result.not_checked, {})

    def test_ca001_px4_failed(self):
        result = check({"error": "PX4 did not produce an effectiveness matrix"})
        self.assertEqual(rules(result), ["CA001"])
        self.assertEqual(result.findings[0].level, "error")

    def test_ca001_no_actuators(self):
        empty = matrix({}, [])
        self.assertEqual(rules(check(engine_result(empty, num_motors=0))), ["CA001"])

    def test_ca002_dropped_axis(self):
        # bit 2 is yaw
        result = check(engine_result(matrix({}, [{}], dropped_axes_bitmask=1 << 2)))
        self.assertEqual(rules(result), ["CA002"])
        self.assertEqual(result.findings[0].axis, "yaw")

    def test_ca002_not_checked_without_px4_support(self):
        result = check(engine_result(matrix({}, [{}], dropped_axes_bitmask=None)))
        self.assertEqual(result.findings, [])
        self.assertIn("CA002", result.not_checked)

    def test_ca003_nan_stops_the_other_rules(self):
        broken = matrix({"thrust_x": [None]}, [{"thrust_x": 9}], weak_axes_zeroed=["yaw"])
        self.assertEqual(rules(check(engine_result(broken))), ["CA003"])

    def test_ca004_weak_axis(self):
        result = check(engine_result(matrix({}, [{}], weak_axes_zeroed=["yaw"])))
        self.assertEqual(rules(result), ["CA004"])
        self.assertEqual(result.findings[0].level, "warning")

    def test_ca010_thrust_gain(self):
        high = matrix({"thrust_x": [6.5, 6.5]}, [{"thrust_x": 4.0}, {"thrust_x": 1.0}])
        result = check(engine_result(high))
        self.assertEqual(rules(result), ["CA010"])
        self.assertEqual(result.findings[0].actuators, ["motor0"])
        self.assertIn("setpoint of 0.25", result.findings[0].message)

    def test_ca010_limit_is_an_option(self):
        high = matrix({"thrust_x": [6.5]}, [{"thrust_x": 4.0}])
        self.assertEqual(rules(check(engine_result(high), Options(max_thrust_gain=5))), [])

    def test_ca010_ignores_torque_axes(self):
        self.assertEqual(rules(check(engine_result(matrix({"yaw": [1]}, [{"yaw": 9}])))), [])

    def test_ca011_command_without_thrust(self):
        coupled = matrix(
            {"thrust_x": [0, 6.5], "thrust_z": [-6.5, 0]},
            [{"thrust_x": 0.25, "thrust_z": -1}, {"thrust_x": 1}],
        )
        result = check(engine_result(coupled))
        self.assertEqual(rules(result), ["CA011"])
        self.assertEqual(result.findings[0].actuators, ["motor0"])

    def test_ca020_unused_motor(self):
        unused = matrix(
            {"roll": [1, 1], "pitch": [1, -1]},
            [{"roll": 0.7, "pitch": 0.7}, {"roll": 0, "pitch": 0}],
        )
        result = check(engine_result(unused))
        self.assertEqual(rules(result), ["CA020"])
        self.assertEqual(result.findings[0].actuators, ["motor1"])

    def test_ca020_skips_motors_on_one_axis_and_servos(self):
        # a pusher above the centre of gravity only produces pitch torque
        pusher = matrix({"pitch": [-0.3], "thrust_x": [6.5]}, [{"thrust_x": 1}])
        servo = matrix({"roll": [1], "pitch": [1]}, [{}], types=["servo"])
        self.assertEqual(rules(check(engine_result(pusher, servo))), [])

    def test_ca021_rotors_beyond_the_count(self):
        params = {"CA_ROTOR_COUNT": "2", "CA_ROTOR1_PX": "0.2", "CA_ROTOR2_PX": "0.2", "CA_ROTOR5_AX": "1"}
        result = check(engine_result(healthy()), params=params)
        self.assertEqual(rules(result), ["CA021"])
        self.assertEqual(result.findings[0].level, "warning")
        self.assertEqual(result.findings[0].actuators, ["motor2", "motor5"])
        self.assertIn("CA_ROTOR_COUNT is 2; PX4 uses rotors 0 to 1 only", result.findings[0].message)

    def test_ca021_count_not_set(self):
        params = {"CA_ROTOR0_PX": "0.15", "CA_ROTOR0_PY": "0.15", "CA_ROTOR1_TILT": "1"}
        result = check(engine_result(matrix({}, []), num_motors=0), params=params)
        self.assertEqual(rules(result), ["CA001", "CA021"])
        self.assertEqual(result.findings[1].actuators, ["motor0", "motor1"])
        self.assertIn("CA_ROTOR_COUNT is 0 (not set in the input); PX4 uses no rotors", result.findings[1].message)

    def test_ca021_ignores_defaults_and_other_parameters(self):
        # a parameter export lists every rotor; unused ones keep PX4's defaults
        params = {
            "CA_ROTOR_COUNT": "2",
            "CA_ROTOR2_PX": "0.000000000000000000",
            "CA_ROTOR2_AZ": "-1.0",
            "CA_ROTOR2_CT": "6.5",
            "CA_ROTOR2_KM": "0.05",
            "CA_ROTOR_COUNTX": "9",
            "CA_ROTOR12_NEW": "3",
        }
        self.assertEqual(rules(check(engine_result(healthy()), params=params)), [])

    def test_ca021_uses_the_count_of_the_file_when_px4_gave_no_result(self):
        failed = {"error": "PX4 did not produce an effectiveness matrix"}
        self.assertEqual(
            rules(check(failed, params={"CA_ROTOR_COUNT": "4", "CA_ROTOR4_PX": "1"})), ["CA001", "CA021"]
        )
        self.assertEqual(rules(check(failed, params={"CA_ROTOR4_PX": "1"})), ["CA001"])

    def test_ca021_needs_the_input_parameters(self):
        self.assertEqual(rules(check(engine_result(matrix({}, []), num_motors=0))), ["CA001"])

    def test_ignore(self):
        result = check(
            engine_result(matrix({}, [{}], weak_axes_zeroed=["yaw"], dropped_axes_bitmask=None)),
            Options(ignore=frozenset({"CA004", "CA002"})),
        )
        self.assertEqual(result.findings, [])
        self.assertEqual(result.not_checked, {})


if __name__ == "__main__":
    unittest.main()
