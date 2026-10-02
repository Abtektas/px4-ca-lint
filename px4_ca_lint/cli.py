"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .engine import ENGINE_ENV, EngineError, find_engine, run_engine
from .params import FORMATS, ParamFileError, parse_file
from .report import build_report, render_json, render_text

EXIT_OK = 0
EXIT_ERROR = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="px4-ca-lint",
        description="Run PX4's control allocation code on a parameter file and report the "
        "resulting matrices. A review aid, not an airworthiness approval; use at your own risk.",
    )
    parser.add_argument("file", help="parameter file (plain, PX4 airframe script or QGroundControl export)")
    parser.add_argument(
        "--input-format",
        choices=("auto", *FORMATS),
        default="auto",
        help="format of the parameter file (default: auto)",
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="report format (default: text)"
    )
    parser.add_argument("--output", metavar="FILE", help="write the report to FILE instead of stdout")
    parser.add_argument(
        "--engine", metavar="PATH", help=f"path to px4_ca_engine (default: ${ENGINE_ENV}, then build/engine)"
    )
    parser.add_argument("--version", action="version", version=f"px4-ca-lint {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        param_file = parse_file(args.file, None if args.input_format == "auto" else args.input_format)
        engine_result = run_engine(find_engine(args.engine), param_file.params)

    except (ParamFileError, EngineError) as error:
        print(f"px4-ca-lint: error: {error}", file=sys.stderr)
        return EXIT_ERROR

    report = build_report(param_file, engine_result)
    text = render_json(report) if args.format == "json" else render_text(report)

    if args.output:
        try:
            Path(args.output).write_text(text, encoding="utf-8")

        except OSError as error:
            print(f"px4-ca-lint: error: {args.output}: {error.strerror}", file=sys.stderr)
            return EXIT_ERROR

    else:
        sys.stdout.write(text)

    return EXIT_OK
