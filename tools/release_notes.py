#!/usr/bin/env python3
"""Print the release notes for a version: its CHANGELOG.md section and the install notes."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INSTALL = """
## Install

See the [README](https://github.com/Abtektas/px4-ca-lint/blob/v{version}/README.md#install).
`SHA256SUMS` lists the checksum of every file of this release.

## Safety and liability

This software is a review aid, not an airworthiness approval. It is provided
"as is", without warranty of any kind. A report without findings does not mean
that a configuration is safe. Use at your own risk.
"""


def changelog_section(version: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^## {re.escape(version)} .*?\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)

    if not match:
        raise SystemExit(f"CHANGELOG.md has no section for {version}")

    return match.group(1).strip()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: release_notes.py <version>")

    version = sys.argv[1]
    print(changelog_section(version))
    print(INSTALL.format(version=version))


if __name__ == "__main__":
    main()
