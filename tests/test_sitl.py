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

import contextlib
import os
import re
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from px4_ca_lint.engine import find_engine, run_engine
from px4_ca_lint.params import parse_file
from px4_ca_lint.rules import AXES

SITL_BUILD = os.environ.get("PX4_CA_SITL_BUILD")
INSTANCE = os.environ.get("PX4_CA_SITL_INSTANCE", "7")
START_TIMEOUT_S = 40
# a PX4 client command normally returns within milliseconds
CLIENT_TIMEOUT_S = 5
CLIENT_ATTEMPTS = 3
# `param show` prints four decimals and the matrix print five
TOLERANCE = 2e-3

_PARAM = re.compile(r"^\S\s+\S?\s*(CA_\w+) \[\d+,\d+\] : (\S+)")
_ROW = re.compile(r"^\s*\d+\|(.*)$")
_SOURCE = re.compile(r"Effectiveness Source: (.+)$", re.MULTILINE)


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
        self.status = ""
        self.process = subprocess.Popen(
            [str(self.bin / "px4"), "-i", INSTANCE, "-d", str(build / "etc")],
            cwd=self.directory.name,
            env={**os.environ, "PX4_SYS_AUTOSTART": str(autostart)},
            stdout=self.log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            # its own process group, so that stop() reaches everything px4 started
            start_new_session=True,
        )

    def command(
        self, name: str, *arguments: str, timeout: float = CLIENT_TIMEOUT_S, attempts: int = CLIENT_ATTEMPTS
    ) -> subprocess.CompletedProcess:
        """Run a PX4 client command.

        Now and then a client hangs although px4 is running and answers the next one, so a
        command that times out is sent again. Every command used here can be repeated.
        """
        for attempt in range(1, attempts + 1):
            try:
                return subprocess.run(
                    [str(self.bin / f"px4-{name}"), "--instance", INSTANCE, *arguments],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    check=False,
                )

            except subprocess.TimeoutExpired:
                if attempt == attempts:
                    raise

    def wait_until_running(self) -> None:
        deadline = time.monotonic() + START_TIMEOUT_S

        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"px4 exited early:\n{self.log_path.read_text()[-2000:]}")

            try:
                if "Running" in self.command("control_allocator", "status", timeout=3, attempts=1).stdout:
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
        if self.log.closed:
            return

        try:
            if self.process.poll() is None:
                self.command("shutdown")

                try:
                    self.process.wait(timeout=10)

                except subprocess.TimeoutExpired:
                    # killed with its group below
                    pass

        finally:
            # px4 runs the startup script in a shell; the shell and a client that hangs in it outlive px4
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.process.pid, signal.SIGKILL)

            self.process.wait()
            self.log.close()

    def final_effectiveness(self, count: int) -> list[list[list[float]]]:
        """Stop PX4 and return the effectiveness matrices of its last status, as [actuator][axis].

        The matrices go to the stdout of the px4 process, which is only written
        to the log file completely when the process exits.
        """
        self.status = self.command("control_allocator", "status").stdout
        self.stop()
        blocks = parse_matrices(self.log_path.read_text())
        # every allocation instance prints Effectiveness.T, minimum and maximum
        return blocks[len(blocks) - 3 * count :: 3] if len(blocks) >= 3 * count else []

    def effectiveness_source(self) -> str | None:
        """The name of the effectiveness class in the status read by final_effectiveness().

        Unlike the matrices, this line goes to the client that asked for the status.
        """
        match = _SOURCE.search(self.status)
        return match.group(1).strip() if match else None

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


def has_writer(fifo: int) -> bool:
    """Whether a process holds the other end of the FIFO, to which nothing is ever written."""
    try:
        return os.read(fifo, 1) != b""

    except BlockingIOError:
        return True


def wait_for(condition, timeout: float = 5) -> bool:
    deadline = time.monotonic() + timeout

    while not condition() and time.monotonic() < deadline:
        time.sleep(0.05)

    return condition()


class Stop(unittest.TestCase):
    def test_processes_started_by_px4_are_stopped(self):
        # A script in place of px4: its child outlives it, like a client that hangs in the startup script.
        # The child holds a FIFO open, which shows whether it is alive. Its PID does not: where nothing
        # reaps orphans, as in a container, a killed process keeps its PID.
        build = Path(self.enterContext(tempfile.TemporaryDirectory()))
        (build / "bin").mkdir()
        os.mkfifo(build / "alive")
        fifo = os.open(build / "alive", os.O_RDONLY | os.O_NONBLOCK)
        self.addCleanup(os.close, fifo)
        px4 = build / "bin" / "px4"
        px4.write_text(f'#!/bin/sh\nsleep 300 > "{build}/alive" &\necho $! > child.pid\n')
        px4.chmod(0o755)

        sitl = Sitl(build, 0)
        self.addCleanup(sitl.cleanup)
        sitl.process.wait(timeout=10)
        self.assertTrue(wait_for(lambda: has_writer(fifo)))
        child = int((Path(sitl.directory.name) / "child.pid").read_text())
        self.addCleanup(lambda: has_writer(fifo) and os.kill(child, signal.SIGKILL))

        sitl.stop()
        self.assertTrue(wait_for(lambda: not has_writer(fifo)))


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
        self.assertEqual(sitl.effectiveness_source(), from_engine["effectiveness_source"])
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

    def test_fixed_wing(self):
        result = self.compare(10041)
        self.assertEqual(result["effectiveness_source"], "Fixed Wing")
        self.assertEqual((result["num_motors"], result["num_servos"]), (1, 3))

    def test_standard_vtol(self):
        result = self.compare(10043)
        self.assertEqual(result["effectiveness_source"], "Standard VTOL")

    def test_standard_vtol_pusher_offset(self):
        result = self.compare(10043, {"CA_ROTOR4_PZ": "-0.05"})
        self.assertAlmostEqual(result["matrices"][0]["effectiveness"]["pitch"][4], -0.325, places=3)

    def test_tailsitter(self):
        result = self.compare(10042)
        self.assertEqual(result["effectiveness_source"], "VTOL Tailsitter")
        self.assertEqual((result["num_motors"], result["num_servos"]), (2, 2))

    # PX4 has no SIH airframe with tilt servos. PX4 changes the effectiveness class when
    # CA_AIRFRAME changes, so the parameters of an example are set on the SIH quadrotor.

    def test_tiltrotor(self):
        result = self.compare(10040, parse_file("examples/tiltrotor.params").params)
        self.assertEqual(result["effectiveness_source"], "VTOL Tiltrotor")
        self.assertEqual((result["num_motors"], result["num_servos"]), (4, 6))

    def test_multirotor_with_tilt(self):
        result = self.compare(10040, parse_file("examples/tricopter_tilt.params").params)
        self.assertEqual(result["effectiveness_source"], "MC Tilt")
        self.assertEqual((result["num_motors"], result["num_servos"]), (3, 1))

    def test_weak_yaw_row_is_zeroed(self):
        weak = {f"CA_ROTOR{index}_KM": sign + "0.005" for index, sign in enumerate(("", "", "-", "-"))}
        result = self.compare(10040, weak)
        self.assertEqual(result["matrices"][0]["weak_axes_zeroed"], ["yaw"])


if __name__ == "__main__":
    unittest.main()
