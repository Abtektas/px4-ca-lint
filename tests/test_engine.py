import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from px4_ca_lint.engine import ENGINE_ENV, EngineError, find_engine, run_engine, user_engine_path


def fake_engine(directory: Path, script: str) -> Path:
    """An executable that stands in for px4_ca_engine. $1 is the parameter file, $2 the output."""
    path = directory / "px4_ca_engine"
    path.write_text("#!/bin/sh\n" + script)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class FindEngine(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        # no engine from the environment or the current directory
        self.enterContext(mock.patch.dict(os.environ, {"XDG_DATA_HOME": str(self.directory / "data")}))
        os.environ.pop(ENGINE_ENV, None)
        previous = os.getcwd()
        os.chdir(self.directory)
        self.addCleanup(os.chdir, previous)

    def test_user_data_directory(self):
        self.assertEqual(user_engine_path(), self.directory / "data" / "px4-ca-lint" / "px4_ca_engine")

        with self.assertRaises(EngineError) as raised:
            find_engine()

        self.assertIn(str(user_engine_path()), str(raised.exception))
        user_engine_path().parent.mkdir(parents=True)
        fake_engine(user_engine_path().parent, "exit 0\n")
        self.assertEqual(find_engine(), user_engine_path())

    def test_order(self):
        user_engine_path().parent.mkdir(parents=True)
        fake_engine(user_engine_path().parent, "exit 0\n")
        (self.directory / "build" / "engine").mkdir(parents=True)
        local = fake_engine(self.directory / "build" / "engine", "exit 0\n")
        self.assertEqual(find_engine().resolve(), local.resolve())

        (self.directory / "env").mkdir()
        from_environment = fake_engine(self.directory / "env", "exit 0\n")

        with mock.patch.dict(os.environ, {ENGINE_ENV: str(from_environment)}):
            self.assertEqual(find_engine(), from_environment)
            self.assertEqual(find_engine(str(local)), local)

    def test_a_file_that_is_not_executable_is_refused(self):
        plain = self.directory / "px4_ca_engine"
        plain.write_text("")

        with self.assertRaises(EngineError):
            find_engine(str(plain))


class RunEngine(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def run_fake(self, script: str) -> dict:
        return run_engine(fake_engine(self.directory, script), {"CA_AIRFRAME": "0"})

    def test_parameters_are_passed_and_output_is_read(self):
        result = self.run_fake(
            'grep -q "^CA_AIRFRAME 0$" "$1" || exit 1\n'
            'echo \'{"engine_schema": 1, "matrices": []}\' > "$2"\n'
        )
        self.assertEqual(result["matrices"], [])

    def test_unknown_schema_is_refused(self):
        with self.assertRaises(EngineError) as raised:
            self.run_fake('echo \'{"engine_schema": 99}\' > "$2"\n')

        self.assertIn("engine_schema 99", str(raised.exception))

    def test_failure_is_reported_with_the_last_error_line(self):
        with self.assertRaises(EngineError) as raised:
            self.run_fake("echo first >&2\necho broken >&2\nexit 3\n")

        self.assertIn("exit code 3", str(raised.exception))
        self.assertIn("broken", str(raised.exception))

    def test_invalid_json_is_a_failure(self):
        with self.assertRaises(EngineError):
            self.run_fake('echo "{" > "$2"\n')

    def test_px4_failure_is_passed_on_for_the_rules(self):
        result = self.run_fake(
            'echo \'{"engine_schema": 1, "error": "PX4 did not produce an effectiveness matrix"}\' > "$2"\nexit 67\n'
        )
        self.assertIn("error", result)

    def test_unsupported_airframe(self):
        with self.assertRaises(EngineError) as raised:
            self.run_fake(
                'echo \'{"engine_schema": 1, "ca_airframe": 3, "px4_version": "v1.17.0"}\' > "$2"\nexit 66\n'
            )

        self.assertIn("CA_AIRFRAME 3 is not supported yet", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
