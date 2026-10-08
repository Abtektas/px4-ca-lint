"""Build the report from the parsed parameters and the engine output."""

from __future__ import annotations

import json

from . import DISCLAIMER, __version__
from .params import ParamFile
from .rules import AXES, ERROR, RULES, WARNING, Result, rule_url

_MAX_LISTED_UNKNOWN = 10


def _label(actuator: dict) -> str:
    return f"{actuator['type']}{actuator['index']}"


def _axis_summary(matrix: dict) -> list[dict]:
    dropped = matrix.get("dropped_axes_bitmask")
    summary = []

    for bit, axis in enumerate(AXES):
        row = matrix["effectiveness"][axis]
        # null values mean PX4 produced NaN or infinity
        authority = sum(abs(value) for value in row if value is not None)

        if axis in matrix["weak_axes_zeroed"]:
            status = "weak, zeroed by PX4"

        elif dropped is not None and dropped & (1 << bit):
            status = "dropped by PX4"

        elif authority > 0:
            status = "controlled"

        else:
            status = "not controlled"

        summary.append({"axis": axis, "status": status, "authority": authority})

    return summary


def _unknown_parameter_notes(engine_result: dict) -> list[str]:
    unknown = engine_result.get("unknown_parameters", [])

    if not unknown:
        return []

    version = engine_result["px4_version"]
    # control allocation parameters matter most, list them first
    ordered = sorted(unknown, key=lambda name: (not name.startswith("CA_"), name))
    listed = ", ".join(ordered[:_MAX_LISTED_UNKNOWN])
    more = len(ordered) - _MAX_LISTED_UNKNOWN
    suffix = f" and {more} more" if more > 0 else ""
    return [f"{len(unknown)} parameter(s) do not exist in PX4 {version} and were ignored: {listed}{suffix}"]


def _airframe_notes(engine_result: dict) -> list[str]:
    # CA_AIRFRAME 3, tiltrotor VTOL: ActuatorEffectivenessTiltrotorVTOL::getEffectivenessMatrix()
    if engine_result.get("ca_airframe") == 3 and engine_result.get("matrices"):
        return [
            "tiltrotor: matrix 0 is the one PX4 computes after a parameter change, with the tilt "
            "servos at their minimum angle (CA_SV_TLn_MINA), which is the hover position; in flight PX4 "
            "recomputes it with the tilt angle, which this report does not cover"
        ]

    return []


def build_report(param_file: ParamFile, engine_result: dict, checked: Result) -> dict:
    matrices = []

    for matrix in engine_result.get("matrices", []):
        matrices.append(
            {
                "index": matrix["index"],
                "method": matrix["method"],
                "normalize_rpy": matrix["normalize_rpy"],
                "actuators": [_label(actuator) for actuator in matrix["actuators"]],
                "axes": _axis_summary(matrix),
                "effectiveness": matrix["effectiveness"],
                "mix": matrix["mix"],
            }
        )

    return {
        "tool_version": __version__,
        "input": {
            "path": param_file.path,
            "format": param_file.format,
            "num_parameters": len(param_file.params),
            "parameters": dict(param_file.params),
        },
        "px4": {
            "version": engine_result["px4_version"],
            "commit": engine_result["px4_commit"],
        },
        "airframe": {
            "ca_airframe": engine_result["ca_airframe"],
            "name": engine_result["effectiveness_source"],
            "num_motors": engine_result.get("num_motors", 0),
            "num_servos": engine_result.get("num_servos", 0),
        },
        "notes": param_file.notes + _unknown_parameter_notes(engine_result) + _airframe_notes(engine_result),
        "summary": {"errors": checked.count(ERROR), "warnings": checked.count(WARNING)},
        "findings": [{**finding.as_dict(), "url": rule_url(finding.rule)} for finding in checked.findings],
        "rules_not_checked": checked.not_checked,
        "matrices": matrices,
        "disclaimer": DISCLAIMER,
    }


def render_json(report: dict) -> str:
    return json.dumps(report, indent=2) + "\n"


def _number(value: float | None) -> str:
    if value is None:
        return "nan"

    # avoid "-0.000"
    return f"{value + 0.0:.3f}" if abs(value) >= 0.0005 else "0.000"


def _table(corner: str, columns: list[str], rows: list[tuple[str, list[float | None]]]) -> list[str]:
    first_width = max(len(corner), *(len(name) for name, _ in rows))
    width = max(8, *(len(column) for column in columns))
    lines = ["  " + corner.ljust(first_width) + "".join(column.rjust(width + 2) for column in columns)]

    for name, values in rows:
        lines.append(
            "  " + name.ljust(first_width) + "".join(_number(value).rjust(width + 2) for value in values)
        )

    return lines


def render_text(report: dict) -> str:
    source = report["input"]
    px4 = report["px4"]
    airframe = report["airframe"]
    lines = [
        f"px4-ca-lint {report['tool_version']}",
        "",
        f"Input:     {source['path']} ({source['format']} format, {source['num_parameters']} parameters)",
        f"PX4:       {px4['version']} ({px4['commit'][:10]})",
        f"Airframe:  CA_AIRFRAME {airframe['ca_airframe']} ({airframe['name']})",
        f"Actuators: {airframe['num_motors']} motors, {airframe['num_servos']} servos",
    ]

    if report["notes"]:
        lines += ["", "Notes"]
        lines += [f"  - {note}" for note in report["notes"]]

    for matrix in report["matrices"]:
        actuators = matrix["actuators"]
        normalised = ", roll/pitch/yaw normalised" if matrix["normalize_rpy"] else ""
        lines += ["", f"Matrix {matrix['index']} ({matrix['method']}{normalised})"]

        if not actuators:
            lines.append("  no actuators")
            continue

        lines += ["", "  Effectiveness: what each actuator produces on each axis"]
        lines += _table(
            "axis", actuators, [(axis, matrix["effectiveness"][axis]) for axis in AXES]
        )

        lines += ["", "  Mix: actuator command per unit of setpoint on each axis"]
        lines += _table(
            "actuator",
            list(AXES),
            [(name, [row[axis] for axis in AXES]) for name, row in zip(actuators, matrix["mix"])],
        )

        lines += ["", "  Axes"]
        name_width = max(len(axis) for axis in AXES)

        for axis in matrix["axes"]:
            lines.append(
                f"  {axis['axis'].ljust(name_width)}  {axis['status']}"
                + (f" (authority {_number(axis['authority'])})" if axis["authority"] > 0 else "")
            )

    lines += ["", "Findings"]

    for finding in report["findings"]:
        where = "" if finding["matrix"] is None else f" matrix {finding['matrix']}:"
        lines.append(f"  {finding['level']} {finding['rule']}{where} {finding['message']}")
        lines.append(f"      {RULES[finding['rule']].title}: {finding['url']}")

    for rule, reason in report["rules_not_checked"].items():
        lines.append(f"  {rule} was not checked: {reason}")

    summary = report["summary"]
    lines.append(f"  {summary['errors']} error(s), {summary['warnings']} warning(s)")

    lines += [
        "",
        "motorN is configured by CA_ROTORN_*. Servos are numbered as in PX4, starting at 0:",
        "control surfaces (CA_SV_CSn_*) first, then tilt servos (CA_SV_TLn_*).",
        "Authority is the sum of the absolute effectiveness values on that axis.",
        "",
        report["disclaimer"],
    ]
    return "\n".join(lines) + "\n"


def _markdown_table(corner: str, columns: list[str], rows: list[tuple[str, list[float | None]]]) -> list[str]:
    lines = [
        "| " + " | ".join([corner, *columns]) + " |",
        "|---|" + "---:|" * len(columns),
    ]
    lines += ["| " + " | ".join([name, *(_number(value) for value in values)]) + " |" for name, values in rows]
    return lines


def render_markdown(report: dict) -> str:
    """The report as GitHub-flavoured Markdown, for pasting into an issue or pull request."""
    source = report["input"]
    px4 = report["px4"]
    airframe = report["airframe"]
    summary = report["summary"]
    lines = [
        f"### px4-ca-lint report: {summary['errors']} error(s), {summary['warnings']} warning(s)",
        "",
        f"- Input: `{source['path']}` ({source['format']} format, {source['num_parameters']} parameters)",
        f"- PX4: `{px4['version']}` (`{px4['commit'][:10]}`)",
        f"- Airframe: `CA_AIRFRAME` {airframe['ca_airframe']} ({airframe['name']}), "
        f"{airframe['num_motors']} motors, {airframe['num_servos']} servos",
        f"- Tool: px4-ca-lint {report['tool_version']}",
        "",
        "#### Findings",
        "",
    ]

    for finding in report["findings"]:
        where = "" if finding["matrix"] is None else f" (matrix {finding['matrix']})"
        lines.append(
            f"- **{finding['level']} [{finding['rule']}]({finding['url']})**{where}: {finding['message']}"
        )

    for rule, reason in report["rules_not_checked"].items():
        lines.append(f"- {rule} was not checked: {reason}")

    if not report["findings"] and not report["rules_not_checked"]:
        lines.append("None.")

    if report["notes"]:
        lines += ["", "#### Notes", ""]
        lines += [f"- {note}" for note in report["notes"]]

    for matrix in report["matrices"]:
        actuators = matrix["actuators"]

        if not actuators:
            continue

        normalised = ", roll/pitch/yaw normalised" if matrix["normalize_rpy"] else ""
        lines += [
            "",
            f"<details><summary>Matrix {matrix['index']} ({matrix['method']}{normalised})</summary>",
            "",
            "Effectiveness: what each actuator produces on each axis",
            "",
        ]
        lines += _markdown_table("axis", actuators, [(axis, matrix["effectiveness"][axis]) for axis in AXES])
        lines += ["", "Mix: actuator command per unit of setpoint on each axis", ""]
        lines += _markdown_table(
            "actuator",
            list(AXES),
            [(name, [row[axis] for axis in AXES]) for name, row in zip(actuators, matrix["mix"])],
        )
        lines += ["", "</details>"]

    lines += ["", f"_{report['disclaimer']}_"]
    return "\n".join(lines) + "\n"


RENDERERS = {"text": render_text, "json": render_json, "markdown": render_markdown}
