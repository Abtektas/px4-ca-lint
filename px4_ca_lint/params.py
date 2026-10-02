"""Read PX4 parameters from the supported file formats.

Three formats are recognised:

plain     ``NAME VALUE`` per line.
airframe  a PX4 airframe script: ``param set-default NAME VALUE`` or ``param set NAME VALUE``.
          Files it sources (``. ${R}etc/init.d/rc.fw_defaults``) are read too when they can be
          found next to the script, as in PX4's ROMFS directory.
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
_SOURCED = re.compile(r"^\s*(?:\.|source)\s+(\S+)")
_MAX_SOURCE_DEPTH = 5
# how many directories above the script are searched for a sourced file
_MAX_ROOT_DISTANCE = 4
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
    # name -> sourced file that set it, "" for the file itself
    origins: dict[str, str] = field(default_factory=dict, repr=False)


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


def _store(result: ParamFile, line_number: int, name: str, value: str, origin: str = "") -> None:
    where = f"{origin} line {line_number}" if origin else f"line {line_number}"

    if not _NAME.match(name):
        result.notes.append(f"{where}: '{name}' is not a valid parameter name, skipped")
        return

    if not _is_number(value):
        result.notes.append(f"{where}: {name} has the non-numeric value '{value}', skipped")
        return

    # an airframe script overriding a sourced default is normal, the same file doing it is not
    same_file = result.origins.get(name, origin) == origin

    if same_file and name in result.params and result.params[name] != value:
        result.notes.append(f"{where}: {name} is set more than once, using the last value ({value})")

    result.params[name] = value
    result.origins[name] = origin


def _parse_plain(result: ParamFile, lines: list[str]) -> None:
    for number, line in enumerate(lines, start=1):
        fields = line.split("#", 1)[0].split()

        if not fields:
            continue

        if len(fields) != 2:
            result.notes.append(f"line {number}: expected 'NAME VALUE', skipped")
            continue

        _store(result, number, fields[0], fields[1])


def _resolve_sourced(script: Path, target: str) -> Path | None:
    """Find a sourced file such as ``${R}etc/init.d/rc.fw_defaults`` in a ROMFS directory.

    PX4 installs ROMFS/px4fmu_common as ``etc``, so the path is looked up relative to the
    directories above the script.
    """
    relative = target.replace("${R}", "").lstrip("/")

    if "$" in relative:
        return None

    relative = relative.removeprefix("etc/")

    for root in list(script.resolve().parents)[:_MAX_ROOT_DISTANCE]:
        candidate = root / relative

        if candidate.is_file():
            return candidate

    return None


def _parse_airframe(
    result: ParamFile, lines: list[str], script: Path | None = None, origin: str = "", depth: int = 0
) -> None:
    conditional = False

    for number, line in enumerate(lines, start=1):
        code = line.split("#", 1)[0]
        match = _PARAM_SET.match(code)
        sourced = _SOURCED.match(code)

        if match:
            _store(result, number, match.group(1), match.group(2), origin)

        elif sourced:
            target = sourced.group(1)
            found = _resolve_sourced(script, target) if script and depth < _MAX_SOURCE_DEPTH else None

            if found is None:
                result.notes.append(
                    f"the script sources '{target}', which was not found; parameters set there "
                    "are missing"
                )
                continue

            try:
                text = found.read_text(encoding="utf-8", errors="replace")

            except OSError:
                result.notes.append(f"the sourced file '{found}' could not be read")
                continue

            result.notes.append(f"included the sourced file {found.name}")
            _parse_airframe(result, text.splitlines(), found, found.name, depth + 1)

        elif _CONDITIONAL.match(code):
            conditional = True

    if conditional:
        name = origin or "the script"
        result.notes.append(
            f"{name} has conditional blocks; they are not evaluated, every 'param set' line is used"
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


def parse_text(
    text: str, path: str = "<text>", file_format: str | None = None, script: Path | None = None
) -> ParamFile:
    if file_format is None:
        file_format = detect_format(text)

    if file_format not in _PARSERS:
        raise ParamFileError(f"unknown format '{file_format}'")

    result = ParamFile(path=path, format=file_format)

    if file_format == "airframe":
        _parse_airframe(result, text.splitlines(), script)

    else:
        _PARSERS[file_format](result, text.splitlines())

    if not result.params:
        raise ParamFileError(f"{path}: no parameters found (read as '{file_format}' format)")

    if "CA_AIRFRAME" not in result.params:
        result.notes.append("CA_AIRFRAME is not set in the input; PX4's default is used")

    return result


def parse_file(path: str | Path, file_format: str | None = None) -> ParamFile:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")

    except OSError as error:
        raise ParamFileError(f"{path}: {error.strerror}") from error

    return parse_text(text, str(path), file_format, Path(path))
