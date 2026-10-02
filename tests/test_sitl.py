"""Cross-check against a running PX4 SITL instance.

PX4 SITL is started without a simulator window, with one of PX4's SIH airframes.
The CA_* parameters of the running instance are given to the engine, and the
engine's effectiveness matrices are compared with the ones printed by
`control_allocator status`. This shows that the engine reproduces what the
control_allocator module computes, including the zeroing of weak rows.

`control_allocator status` does not print the mix matrix, so the mix is not
compared here.

Needs a PX4 SITL build and an engine built from the same PX4 version:

    PX4_CA_SITL_BUILD=<build dir of px4_sitl_default> PX4_CA_ENGINE=<px4_ca_engine> \\
        python3 -m unittest tests.test_sitl
"""

import os
import re
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from px4_ca_lint.engine import find_engine, run_engine
from px4_ca_lint.rules import AXES

SITL_BUILD = os.environ.get("PX4_CA_SITL_BUILD")
INSTANCE = os.environ.get("PX4_CA_SITL_INSTANCE", "7")
START_TIMEOUT_S = 40
# `param show` prints four decimals and the matrix print five
TOLERANCE = 2e-3

_PARAM = re.compile(r"^\S\s+\S?\s*(CA_\w+) \[\d+,\d+\] : (\S+)")
_ROW = re.compile(r"^\s*\d+\|(.*)$")


def parse_matrices(text: str) -> list[list[list[float]]]:
    """Read the blocks printed by PX4's Matrix::print()."""
    matrices = []

    for line in text.splitlines():
        if line.startswith("  |"):
            matrices.append([])
            continue

        row = _ROW.match(line)

        if row and matrices:
            matrices[-1].append([float(value) for value in row.group(1).split()])

    return matrices


class Sitl:
    def __init__(self, build: Path, autostart: int):
        self.bin = build / "bin"
        self.directory = tempfile.TemporaryDirectory(prefix="px4-ca-lint-sitl-")
        self.log_path = Path(self.directory.name) / "px4.log"
        self.log = open(self.log_path, "w")
        self.process = subprocess.Popen(
            [str(self.bin / "px4"), "-i", INSTANCE, "-d", str(build / "etc")],
            cwd=self.directory.name,
            env={**os.environ, "PX4_SYS_AUTOSTART": str(autostart)},
            stdout=self.log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )

    def command(self, name: str, *arguments: str, timeout: float = 20) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(self.bin / f"px4-{name}"), "--instance", INSTANCE, *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def wait_until_running(self) -> None:
        deadline = time.monotonic() + START_TIMEOUT_S

        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"px4 exited early:\n{self.log_path.read_text()[-2000:]}")

            try:
                if "Running" in self.command("control_allocator", "status", timeout=3).stdout:
                    return

            except subprocess.TimeoutExpired:
                # a client that connects while px4 is still starting can hang
                pass

            time.sleep(0.5)

        raise RuntimeError("control_allocator did not start")

    def set_parameter(self, name: str, value: str) -> None:
        result = self.command("param", "set", name, value)

        if result.returncode != 0:
            raise RuntimeError(f"param set {name} failed: {result.stdout}{result.stderr}")

    def ca_parameters(self) -> dict[str, str]:
        parameters = {}

        for line in self.command("param", "show", "CA_*").stdout.splitlines():
            match = _PARAM.match(line)

            if match:
                parameters[match.group(1)] = match.group(2)

        return parameters

    def stop(self) -> None:
        if self.process.poll() is None:
            self.command("shutdown")

            try:
                self.process.wait(timeout=10)

            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

        self.log.close()

    def final_effectiveness(self, count: int) -> list[list[list[float]]]:
        """Stop PX4 and return the effectiveness matrices of its last status, as [actuator][axis].

        The matrices go to the stdout of the px4 process, which is only written
        to the log file completely when the process exits.
        """
        self.command("control_allocator", "status")
        self.stop()
        blocks = parse_matrices(self.log_path.read_text())
        # every allocation instance prints Effectiveness.T, minimum and maximum
        return blocks[len(blocks) - 3 * count :: 3] if len(blocks) >= 3 * count else []

    def cleanup(self) -> None:
        self.stop()
        self.directory.cleanup()


class ParseMatrices(unittest.TestCase):
    def test_blocks(self):
        text = (
            "INFO  [control_allocator]   Effectiveness.T =\n"
            "  | 0      | 1      \n"
            " 0|-1.30000  0       \n"
            " 1| 1.30000 -6.50000 \n"
            "  | 0      | 1      \n"
            " 0| 1.00000  1.00000 \n"
        )
        self.assertEqual(parse_matrices(text), [[[-1.3, 0.0], [1.3, -6.5]], [[1.0, 1.0]]])


@unittest.skipIf(SITL_BUILD is None, "PX4_CA_SITL_BUILD is not set")
class CrossCheck(unittest.TestCase):
    def compare(self, autostart: int, overrides: dict[str, str] | None = None) -> dict:
        sitl = Sitl(Path(SITL_BUILD).resolve(), autostart)
        self.addCleanup(sitl.cleanup)
        sitl.wait_until_running()

        for name, value in (overrides or {}).items():
            sitl.set_parameter(name, value)

        # the module handles the parameter update in its next cycle
        time.sleep(1.5)
        parameters = sitl.ca_parameters()
        self.assertIn("CA_AIRFRAME", parameters)

        for name, value in (overrides or {}).items():
            self.assertAlmostEqual(float(parameters[name]), float(value), places=4)

        from_engine = run_engine(find_engine(), parameters)
        from_sitl = sitl.final_effectiveness(len(from_engine["matrices"]))
        self.assertEqual(len(from_sitl), len(from_engine["matrices"]))

        for sitl_matrix, engine_matrix in zip(from_sitl, from_engine["matrices"]):
            count = engine_matrix["num_actuators"]

            for actuator, row in enumerate(sitl_matrix):
                for axis, value in zip(AXES, row):
                    expected = engine_matrix["effectiveness"][axis][actuator] if actuator < count else 0.0
                    self.assertAlmostEqual(
                        value,
                        expected,
                        delta=TOLERANCE,
                        msg=f"matrix {engine_matrix['index']} actuator {actuator} {axis}",
                    )

        return from_engine

    def test_quadrotor(self):
        result = self.compare(10040)
        self.assertEqual(result["num_motors"], 4)

    def test_hexarotor(self):
        result = self.compare(10044)
        self.assertEqual(result["num_motors"], 6)

    def test_standard_vtol(self):
        result = self.compare(10043)
        self.assertEqual(result["effectiveness_source"], "Standard VTOL")

    def test_standard_vtol_pusher_offset(self):
        result = self.compare(10043, {"CA_ROTOR4_PZ": "-0.05"})
        self.assertAlmostEqual(result["matrices"][0]["effectiveness"]["pitch"][4], -0.325, places=3)

    def test_weak_yaw_row_is_zeroed(self):
        weak = {f"CA_ROTOR{index}_KM": sign + "0.005" for index, sign in enumerate(("", "", "-", "-"))}
        result = self.compare(10040, weak)
        self.assertEqual(result["matrices"][0]["weak_axes_zeroed"], ["yaw"])


if __name__ == "__main__":
    unittest.main()
