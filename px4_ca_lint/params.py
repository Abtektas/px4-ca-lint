"""Read PX4 parameters from the supported file formats.

Three formats are recognised:

plain     ``NAME VALUE`` per line.
airframe  a PX4 airframe script: ``param set-default NAME VALUE`` or ``param set NAME VALUE``.
qgc       a QGroundControl parameter export: tab separated
          ``vehicle-id  component-id  name  value  type``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

FORMATS = ("plain", "airframe", "qgc")

# PX4 parameter names are at most 16 characters.
_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,15}$")
_PARAM_SET = re.compile(r"^\s*param\s+(?:set|set-default)\s+(\S+)\s+(\S+)")
_SOURCED = re.compile(r"^\s*(?:\.|source)\s+\S")
_CONDITIONAL = re.compile(r"^\s*(?:if|elif|else|case)\b")


class ParamFileError(Exception):
    """The file could not be read as a parameter file."""


@dataclass
class ParamFile:
    path: str
    format: str
    # name -> value as written in the file; the last assignment wins
    params: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def detect_format(text: str) -> str:
    for line in text.splitlines():
        if _PARAM_SET.match(line):
            return "airframe"

        if not line.startswith("#") and len(line.split("\t")) >= 5:
            return "qgc"

    return "plain"


def _is_number(value: str) -> bool:
    try:
        return math.isfinite(float(value))

    except ValueError:
        return False


def _store(result: ParamFile, line_number: int, name: str, value: str) -> None:
    if not _NAME.match(name):
        result.notes.append(f"line {line_number}: '{name}' is not a valid parameter name, skipped")
        return

    if not _is_number(value):
        result.notes.append(f"line {line_number}: {name} has the non-numeric value '{value}', skipped")
        return

    if name in result.params and result.params[name] != value:
        result.notes.append(
            f"line {line_number}: {name} is set more than once, using the last value ({value})"
        )

    result.params[name] = value


def _parse_plain(result: ParamFile, lines: list[str]) -> None:
    for number, line in enumerate(lines, start=1):
        fields = line.split("#", 1)[0].split()

        if not fields:
            continue

        if len(fields) != 2:
            result.notes.append(f"line {number}: expected 'NAME VALUE', skipped")
            continue

        _store(result, number, fields[0], fields[1])


def _parse_airframe(result: ParamFile, lines: list[str]) -> None:
    sourced = False
    conditional = False

    for number, line in enumerate(lines, start=1):
        code = line.split("#", 1)[0]
        match = _PARAM_SET.match(code)

        if match:
            _store(result, number, match.group(1), match.group(2))

        elif _SOURCED.match(code):
            sourced = True

        elif _CONDITIONAL.match(code):
            conditional = True

    if sourced:
        result.notes.append(
            "the script sources other files; parameters set there are not included"
        )

    if conditional:
        result.notes.append(
            "the script has conditional blocks; they are not evaluated, every 'param set' line is used"
        )


def _parse_qgc(result: ParamFile, lines: list[str]) -> None:
    components = set()

    for number, line in enumerate(lines, start=1):
        if not line.strip() or line.startswith("#"):
            continue

        fields = line.split("\t")

        if len(fields) < 5:
            result.notes.append(f"line {number}: expected 5 tab-separated fields, skipped")
            continue

        components.add((fields[0].strip(), fields[1].strip()))
        _store(result, number, fields[2].strip(), fields[3].strip())

    if len(components) > 1:
        result.notes.append(
            "the file has parameters of more than one vehicle or component; they are merged"
        )


_PARSERS = {"plain": _parse_plain, "airframe": _parse_airframe, "qgc": _parse_qgc}


def parse_text(text: str, path: str = "<text>", file_format: str | None = None) -> ParamFile:
    if file_format is None:
        file_format = detect_format(text)

    if file_format not in _PARSERS:
        raise ParamFileError(f"unknown format '{file_format}'")

    result = ParamFile(path=path, format=file_format)
    _PARSERS[file_format](result, text.splitlines())

    if not result.params:
        raise ParamFileError(f"{path}: no parameters found (read as '{file_format}' format)")

    return result


def parse_file(path: str | Path, file_format: str | None = None) -> ParamFile:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")

    except OSError as error:
        raise ParamFileError(f"{path}: {error.strerror}") from error

    return parse_text(text, str(path), file_format)
