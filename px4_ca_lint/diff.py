"""Compare the reports of two parameter files."""

from __future__ import annotations

import json

from . import DISCLAIMER, __version__
from .report import _number
from .rules import AXES

# matrix values that differ by less than this are treated as equal
_TOLERANCE = 1e-3
# value of a matrix entry whose actuator exists in only one of the two reports
ABSENT = "absent"


def _finding_key(finding: dict) -> tuple:
    return (finding["rule"], finding["matrix"], finding["axis"], tuple(finding["actuators"]))


def _parameter_changes(before: dict[str, str], after: dict[str, str]) -> list[dict]:
    changes = []

    for name in sorted(before.keys() | after.keys()):
        old, new = before.get(name), after.get(name)

        if old is None or new is None or float(old) != float(new):
            changes.append({"name": name, "before": old, "after": new})

    return changes


def _cells(matrix: dict) -> dict[tuple[str, str, str], float | None]:
    """Every matrix value, keyed by (kind, actuator, axis)."""
    cells = {}

    for position, actuator in enumerate(matrix["actuators"]):
        for axis in AXES:
            cells[("effectiveness", actuator, axis)] = matrix["effectiveness"][axis][position]
            cells[("mix", actuator, axis)] = matrix["mix"][position][axis]

    return cells


def _differs(old: float | None, new: float | None) -> bool:
    if old is None or new is None:
        return old is not new

    return abs(old - new) > _TOLERANCE


def _matrix_changes(before: list[dict], after: list[dict]) -> list[dict]:
    changes = []
    old_matrices = {matrix["index"]: matrix for matrix in before}
    new_matrices = {matrix["index"]: matrix for matrix in after}

    for index in sorted(old_matrices.keys() | new_matrices.keys()):
        old_cells = _cells(old_matrices[index]) if index in old_matrices else {}
        new_cells = _cells(new_matrices[index]) if index in new_matrices else {}

        for key in sorted(old_cells.keys() | new_cells.keys()):
            # an actuator that exists on one side only counts as a change
            present = key in old_cells and key in new_cells

            if not present or _differs(old_cells[key], new_cells[key]):
                kind, actuator, axis = key
                changes.append(
                    {
                        "matrix": index,
                        "kind": kind,
                        "actuator": actuator,
                        "axis": axis,
                        "before": old_cells.get(key, ABSENT),
                        "after": new_cells.get(key, ABSENT),
                    }
                )

    return changes


def build_diff(before: dict, after: dict) -> dict:
    """Compare two reports made by report.build_report()."""
    old_findings = {_finding_key(finding): finding for finding in before["findings"]}
    new_findings = {_finding_key(finding): finding for finding in after["findings"]}

    return {
        "tool_version": __version__,
        "before": {"path": before["input"]["path"], "px4": before["px4"], "summary": before["summary"]},
        "after": {"path": after["input"]["path"], "px4": after["px4"], "summary": after["summary"]},
        "same_px4": before["px4"]["commit"] == after["px4"]["commit"],
        "parameters": _parameter_changes(before["input"]["parameters"], after["input"]["parameters"]),
        "matrices": _matrix_changes(before["matrices"], after["matrices"]),
        "findings": {
            "new": [finding for key, finding in new_findings.items() if key not in old_findings],
            "gone": [finding for key, finding in old_findings.items() if key not in new_findings],
            "unchanged": sum(1 for key in new_findings if key in old_findings),
        },
        "disclaimer": DISCLAIMER,
    }


def render_json(diff: dict) -> str:
    return json.dumps(diff, indent=2) + "\n"


def _value(value) -> str:
    return "not set" if value is None else str(value)


def _cell(value) -> str:
    return ABSENT if value == ABSENT else _number(value)


def _lines(diff: dict, markdown: bool) -> list[str]:
    code = "`" if markdown else ""
    item = "- " if markdown else "  "

    def heading(text: str) -> list[str]:
        return ["", f"#### {text}", ""] if markdown else ["", text]

    lines = [
        "### px4-ca-lint diff" if markdown else f"px4-ca-lint {diff['tool_version']} diff",
        "",
        f"{item}before: {code}{diff['before']['path']}{code} (PX4 {diff['before']['px4']['version']})",
        f"{item}after:  {code}{diff['after']['path']}{code} (PX4 {diff['after']['px4']['version']})",
    ]

    if not diff["same_px4"]:
        lines.append(f"{item}the two reports come from different PX4 versions")

    lines += heading("Parameters")
    lines += [
        f"{item}{code}{change['name']}{code}: {_value(change['before'])} -> {_value(change['after'])}"
        for change in diff["parameters"]
    ] or [f"{item}no differences"]

    lines += heading("Matrices")
    lines += [
        f"{item}matrix {change['matrix']} {change['kind']} {change['actuator']} {change['axis']}: "
        f"{_cell(change['before'])} -> {_cell(change['after'])}"
        for change in diff["matrices"]
    ] or [f"{item}no differences above {_TOLERANCE}"]

    lines += heading("Findings")

    for label, findings in (("new", diff["findings"]["new"]), ("gone", diff["findings"]["gone"])):
        for finding in findings:
            where = "" if finding["matrix"] is None else f" matrix {finding['matrix']}:"
            lines.append(f"{item}{label}: {finding['level']} {finding['rule']}{where} {finding['message']}")

    lines.append(
        f"{item}{len(diff['findings']['new'])} new, {len(diff['findings']['gone'])} gone, "
        f"{diff['findings']['unchanged']} unchanged"
    )
    lines += ["", f"_{diff['disclaimer']}_" if markdown else diff["disclaimer"]]
    return lines


def render_text(diff: dict) -> str:
    return "\n".join(_lines(diff, markdown=False)) + "\n"


def render_markdown(diff: dict) -> str:
    return "\n".join(_lines(diff, markdown=True)) + "\n"


RENDERERS = {"text": render_text, "json": render_json, "markdown": render_markdown}
