"""Rules that turn the engine output into findings.

Every rule has a document in rules/ that explains what it checks and why.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

AXES = ("roll", "pitch", "yaw", "thrust_x", "thrust_y", "thrust_z")
TORQUE_AXES = AXES[:3]
THRUST_AXES = AXES[3:]

ERROR = "error"
WARNING = "warning"
LEVELS = (WARNING, ERROR)

# PX4 sets mix entries below this to zero (ControlAllocationPseudoInverse)
_MIX_ZERO = 1e-3
_EFFECTIVENESS_ZERO = 1e-6


@dataclass(frozen=True)
class Rule:
    id: str
    level: str
    title: str


RULES = {
    rule.id: rule
    for rule in (
        Rule("CA001", ERROR, "PX4 produced no usable effectiveness matrix"),
        Rule("CA002", ERROR, "PX4 dropped a control axis"),
        Rule("CA003", ERROR, "a matrix contains NaN or infinity"),
        Rule("CA004", WARNING, "PX4 ignores an axis with weak authority"),
        Rule("CA010", WARNING, "thrust gain above the limit"),
        Rule("CA011", WARNING, "thrust command to an actuator that produces no thrust on that axis"),
        Rule("CA020", WARNING, "a motor is not used for roll or pitch"),
    )
}


def rule_url(rule_id: str) -> str:
    """Where the document of a rule is, for the version of the tool that is running."""
    from . import __version__

    ref = "main" if "dev" in __version__ else f"v{__version__}"
    return f"https://github.com/Abtektas/px4-ca-lint/blob/{ref}/rules/{rule_id}.md"


@dataclass(frozen=True)
class Options:
    # CA010: largest accepted |mix| on a thrust axis
    max_thrust_gain: float = 2.0
    # CA011: smallest |mix| that counts as a command
    min_cross_command: float = 0.05
    ignore: frozenset[str] = frozenset()


@dataclass
class Finding:
    rule: str
    level: str
    message: str
    matrix: int | None = None
    axis: str | None = None
    actuators: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    # rules that could not run, with the reason
    not_checked: dict[str, str] = field(default_factory=dict)

    def count(self, level: str) -> int:
        return sum(1 for finding in self.findings if finding.level == level)


def _finding(rule_id: str, message: str, **where) -> Finding:
    return Finding(rule=rule_id, level=RULES[rule_id].level, message=message, **where)


def _labels(matrix: dict) -> list[str]:
    return [f"{actuator['type']}{actuator['index']}" for actuator in matrix["actuators"]]


def _has_non_finite(matrix: dict) -> bool:
    # the engine writes null for NaN and infinity
    values = [value for axis in AXES for value in matrix["effectiveness"][axis]]
    values += [row[axis] for row in matrix["mix"] for axis in AXES]
    return any(value is None for value in values)


def _join(names: list[str]) -> str:
    return ", ".join(names)


def _check_dropped_axes(matrix: dict, result: Result) -> None:
    dropped = matrix["dropped_axes_bitmask"]

    if dropped is None:
        result.not_checked["CA002"] = "this PX4 version does not report dropped axes"
        return

    for bit, axis in enumerate(AXES):
        if dropped & (1 << bit):
            result.findings.append(
                _finding(
                    "CA002",
                    f"PX4 dropped {axis}: its effectiveness row depends on axes with a higher "
                    "priority, so it cannot be controlled independently",
                    matrix=matrix["index"],
                    axis=axis,
                )
            )


def _check_weak_axes(matrix: dict, result: Result) -> None:
    for axis in matrix["weak_axes_zeroed"]:
        result.findings.append(
            _finding(
                "CA004",
                f"every {axis} effectiveness value is 0.05 or smaller, so PX4 sets the row to "
                f"zero and does not control {axis} with this matrix",
                matrix=matrix["index"],
                axis=axis,
            )
        )


def _check_thrust_gain(matrix: dict, options: Options, result: Result) -> None:
    labels = _labels(matrix)

    for axis in THRUST_AXES:
        high = [
            (label, abs(row[axis]))
            for label, row in zip(labels, matrix["mix"])
            if abs(row[axis]) > options.max_thrust_gain
        ]

        if not high:
            continue

        gain = max(value for _, value in high)
        result.findings.append(
            _finding(
                "CA010",
                f"{_join([label for label, _ in high])}: {axis} gain up to {gain:.2f} "
                f"(limit {options.max_thrust_gain:g}); the output saturates at a {axis} "
                f"setpoint of {1 / gain:.2f}",
                matrix=matrix["index"],
                axis=axis,
                actuators=[label for label, _ in high],
            )
        )


def _check_cross_command(matrix: dict, options: Options, result: Result) -> None:
    labels = _labels(matrix)

    for axis in THRUST_AXES:
        effectiveness = matrix["effectiveness"][axis]
        affected = [
            label
            for label, produced, row in zip(labels, effectiveness, matrix["mix"])
            if abs(produced) < _EFFECTIVENESS_ZERO and abs(row[axis]) > options.min_cross_command
        ]

        if affected:
            result.findings.append(
                _finding(
                    "CA011",
                    f"{_join(affected)}: commanded by the {axis} setpoint without producing "
                    f"{axis} thrust; a {axis} setpoint changes their output",
                    matrix=matrix["index"],
                    axis=axis,
                    actuators=affected,
                )
            )


def _check_unused_motor(matrix: dict, result: Result) -> None:
    roll = matrix["effectiveness"]["roll"]
    pitch = matrix["effectiveness"]["pitch"]

    for actuator, label, roll_torque, pitch_torque, row in zip(
        matrix["actuators"], _labels(matrix), roll, pitch, matrix["mix"]
    ):
        if actuator["type"] != "motor":
            continue

        produces_both = abs(roll_torque) > _EFFECTIVENESS_ZERO and abs(pitch_torque) > _EFFECTIVENESS_ZERO
        unused = abs(row["roll"]) < _MIX_ZERO and abs(row["pitch"]) < _MIX_ZERO

        if produces_both and unused:
            result.findings.append(
                _finding(
                    "CA020",
                    f"{label} produces roll and pitch torque but gets no roll and no pitch "
                    "command. A frequent cause is a wrong spin direction "
                    "(sign of CA_ROTORn_KM) on this or another motor",
                    matrix=matrix["index"],
                    actuators=[label],
                )
            )


def check(engine_result: dict, options: Options = Options()) -> Result:
    result = Result()

    if "error" in engine_result:
        result.findings.append(_finding("CA001", f"{engine_result['error']}"))

    elif engine_result["num_motors"] + engine_result["num_servos"] == 0:
        result.findings.append(
            _finding("CA001", "the configuration has no actuators; check CA_ROTOR_COUNT")
        )

    for matrix in engine_result.get("matrices", []):
        if _has_non_finite(matrix):
            result.findings.append(
                _finding(
                    "CA003",
                    "the matrix contains NaN or infinity; the other rules were not run on it",
                    matrix=matrix["index"],
                )
            )
            continue

        _check_dropped_axes(matrix, result)
        _check_weak_axes(matrix, result)
        _check_thrust_gain(matrix, options, result)
        _check_cross_command(matrix, options, result)
        _check_unused_motor(matrix, result)

    result.findings = [finding for finding in result.findings if finding.rule not in options.ignore]
    result.not_checked = {
        rule: reason for rule, reason in result.not_checked.items() if rule not in options.ignore
    }
    return result
