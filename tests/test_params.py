import unittest

from px4_ca_lint.params import ParamFileError, detect_format, parse_file, parse_text


class DetectFormat(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(detect_format("# comment\nCA_AIRFRAME 2\n"), "plain")

    def test_airframe(self):
        self.assertEqual(detect_format("#!/bin/sh\nparam set-default CA_AIRFRAME 2\n"), "airframe")

    def test_qgc(self):
        self.assertEqual(detect_format("# Onboard parameters\n1\t1\tCA_AIRFRAME\t2\t6\n"), "qgc")


class Plain(unittest.TestCase):
    def test_values_and_comments(self):
        result = parse_text("# header\nCA_AIRFRAME 2\n\nCA_ROTOR4_PZ -0.05  # offset\n")
        self.assertEqual(result.format, "plain")
        self.assertEqual(result.params, {"CA_AIRFRAME": "2", "CA_ROTOR4_PZ": "-0.05"})
        self.assertEqual(result.notes, [])

    def test_bad_lines_are_skipped_with_a_note(self):
        result = parse_text("CA_AIRFRAME 2\nca_lower 1\nCA_ROTOR0_PX abc\nCA_ROTOR0_PY nan\nONLYNAME\n")
        self.assertEqual(result.params, {"CA_AIRFRAME": "2"})
        self.assertEqual(len(result.notes), 4)
        self.assertIn("line 2", result.notes[0])

    def test_last_value_wins(self):
        result = parse_text("CA_ROTOR_COUNT 4\nCA_ROTOR_COUNT 5\n")
        self.assertEqual(result.params["CA_ROTOR_COUNT"], "5")
        self.assertIn("more than once", result.notes[0])

    def test_no_parameters_is_an_error(self):
        with self.assertRaises(ParamFileError):
            parse_text("# nothing here\n")


class Airframe(unittest.TestCase):
    SCRIPT = (
        "#!/bin/sh\n"
        ". ${R}etc/init.d/rc.vtol_defaults\n"
        "param set-default CA_AIRFRAME 2\n"
        "param set CA_ROTOR_COUNT 5 # pusher included\n"
        "# param set-default CA_ROTOR0_PX 9\n"
        "param set-default PWM_MAIN_FUNC1 ${FUNC}\n"
        "if [ $X = yes ]\nthen\n\tparam set-default CA_ROTOR4_AX 1\nfi\n"
    )

    def test_param_lines(self):
        result = parse_text(self.SCRIPT)
        self.assertEqual(result.format, "airframe")
        self.assertEqual(result.params, {"CA_AIRFRAME": "2", "CA_ROTOR_COUNT": "5", "CA_ROTOR4_AX": "1"})

    def test_limits_are_reported(self):
        notes = "\n".join(parse_text(self.SCRIPT).notes)
        self.assertIn("non-numeric", notes)
        self.assertIn("sources other files", notes)
        self.assertIn("conditional", notes)


class Qgc(unittest.TestCase):
    def test_export(self):
        result = parse_file("examples/quad_qgc_export.params")
        self.assertEqual(result.format, "qgc")
        self.assertEqual(len(result.params), 15)
        self.assertEqual(result.params["CA_ROTOR_COUNT"], "4")
        self.assertEqual(result.notes, [])

    def test_several_components(self):
        result = parse_text("1\t1\tCA_AIRFRAME\t0\t6\n1\t2\tCA_ROTOR_COUNT\t4\t6\n")
        self.assertIn("more than one", result.notes[0])


class Files(unittest.TestCase):
    def test_missing_file(self):
        with self.assertRaises(ParamFileError):
            parse_file("does/not/exist.params")

    def test_forced_format(self):
        with self.assertRaises(ParamFileError):
            parse_text("CA_AIRFRAME 2\n", file_format="airframe")


if __name__ == "__main__":
    unittest.main()
