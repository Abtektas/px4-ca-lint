"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .engine import ENGINE_ENV, EngineError, find_engine, run_engine
from .params import FORMATS, ParamFileError, parse_file
from .report import build_report, render_json, render_text
from .rules import ERROR, LEVELS, RULES, WARNING, Options, check

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def _rule_list(text: str) -> frozenset[str]:
    rules = frozenset(part.strip().upper() for part in text.split(",") if part.strip())
    unknown = sorted(rules - RULES.keys())

    if unknown:
        raise argparse.ArgumentTypeError(f"unknown rule(s): {', '.join(unknown)}")

    return rules


def _positive(text: str) -> float:
    try:
        value = float(text)

    except ValueError:
        value = 0

    if not value > 0:
        raise argparse.ArgumentTypeError(f"'{text}' is not a positive number")

    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="px4-ca-lint",
        description="Run PX4's control allocation code on a parameter file and report the "
        "resulting matrices and findings. A review aid, not an airworthiness approval; use at your own risk.",
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
    parser.add_argument(
        "--fail-on",
        choices=(*LEVELS, "never"),
        default=ERROR,
        help="lowest finding level that gives exit code 1 (default: error)",
    )
    parser.add_argument(
        "--ignore", metavar="RULES", type=_rule_list, default=frozenset(), help="comma separated rules to skip, for example CA011,CA020"
    )
    parser.add_argument(
        "--max-thrust-gain",
        metavar="GAIN",
        type=_positive,
        default=Options.max_thrust_gain,
        help=f"limit for rule CA010 (default: {Options.max_thrust_gain})",
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

    checked = check(engine_result, Options(max_thrust_gain=args.max_thrust_gain, ignore=args.ignore))
    report = build_report(param_file, engine_result, checked)
    text = render_json(report) if args.format == "json" else render_text(report)

    if args.output:
        try:
            Path(args.output).write_text(text, encoding="utf-8")

        except OSError as error:
            print(f"px4-ca-lint: error: {args.output}: {error.strerror}", file=sys.stderr)
            return EXIT_ERROR

    else:
        sys.stdout.write(text)

    failing = {ERROR: (ERROR,), WARNING: (ERROR, WARNING), "never": ()}[args.fail_on]
    return EXIT_FINDINGS if any(checked.count(level) for level in failing) else EXIT_OK
