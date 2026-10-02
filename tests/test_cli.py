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
        self.assertIn("**warning CA020**", stdout)

    def test_unsupported_airframe(self):
        path = Path(os.environ.get("TMPDIR", "/tmp")) / "px4-ca-lint-test-unsupported.params"
        path.write_text("CA_AIRFRAME 3\n")
        self.addCleanup(path.unlink)
        code, _, stderr = run("--engine", ENGINE, str(path))
        self.assertEqual(code, 2)
        self.assertIn("not supported yet", stderr)


if __name__ == "__main__":
    unittest.main()
