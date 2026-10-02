"""Find and run the px4_ca_engine executable."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

# engine_schema values this version of the tool can read, see docs/versioning.md
SUPPORTED_ENGINE_SCHEMAS = (1,)

ENGINE_ENV = "PX4_CA_ENGINE"
_DEFAULT_LOCATIONS = ("build/engine/px4_ca_engine",)
_TIMEOUT_S = 60

# exit codes of px4_ca_engine
_EXIT_INPUT = 65
_EXIT_UNSUPPORTED = 66
_EXIT_PX4_FAILED = 67


class EngineError(Exception):
    """The engine is missing, failed, or wrote output this tool cannot read."""


def find_engine(explicit: str | None = None) -> Path:
    if explicit:
        candidates = [Path(explicit)]
        source = "--engine"

    elif os.environ.get(ENGINE_ENV):
        candidates = [Path(os.environ[ENGINE_ENV])]
        source = ENGINE_ENV

    else:
        candidates = [Path(location) for location in _DEFAULT_LOCATIONS]
        source = None

    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate

    if source:
        raise EngineError(f"{source}: '{candidates[0]}' is not an executable file")

    raise EngineError(
        "px4_ca_engine not found. Build it with engine/build.sh, then pass --engine PATH "
        f"or set {ENGINE_ENV}."
    )


def run_engine(engine: Path, params: dict[str, str]) -> dict:
    """Run the engine on the given parameters and return its JSON output.

    When PX4 cannot produce a matrix the output has an "error" entry and no matrices.
    """
    with tempfile.TemporaryDirectory(prefix="px4-ca-lint-") as directory:
        params_path = Path(directory) / "input.params"
        output_path = Path(directory) / "output.json"
        params_path.write_text(
            "".join(f"{name} {value}\n" for name, value in params.items()), encoding="ascii"
        )

        try:
            # PX4 prints start-up messages to stdout, the result goes to the output file
            process = subprocess.run(
                [str(engine), str(params_path), str(output_path)],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=_TIMEOUT_S,
                check=False,
            )

        except subprocess.TimeoutExpired as error:
            raise EngineError(f"the engine did not finish within {_TIMEOUT_S} s") from error

        except OSError as error:
            raise EngineError(f"cannot run '{engine}': {error.strerror}") from error

        result = None

        if output_path.is_file():
            try:
                result = json.loads(output_path.read_text(encoding="utf-8"))

            except json.JSONDecodeError:
                result = None

    code = process.returncode

    if code == _EXIT_UNSUPPORTED and result is not None:
        raise EngineError(
            f"CA_AIRFRAME {result.get('ca_airframe')} is not supported yet "
            f"(engine built against PX4 {result.get('px4_version')})"
        )

    if code == _EXIT_PX4_FAILED and result is not None and "error" in result:
        # not a tool failure: the rules report it as a finding
        code = 0

    if code != 0 or result is None:
        detail = process.stderr.strip().splitlines()[-1:] or ["no error message"]
        raise EngineError(f"the engine failed (exit code {code}): {detail[0]}")

    schema = result.get("engine_schema")

    if schema not in SUPPORTED_ENGINE_SCHEMAS:
        raise EngineError(
            f"the engine writes engine_schema {schema}, this tool reads "
            f"{', '.join(str(s) for s in SUPPORTED_ENGINE_SCHEMAS)}. "
            "Use a matching engine and tool version."
        )

    return result
