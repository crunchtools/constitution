#!/usr/bin/env python3
"""Print a zizmor SARIF report as the job log (XV rule 8).

validate.yml runs zizmor once, for SARIF, so the online audits ask GitHub once;
this reads the same file back as one line per finding. Standard library only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def lines(report: dict) -> list[str]:
    """One `level[rule] path:line: message` per finding, then the count."""
    results = [r for run in report.get("runs", []) for r in run.get("results", [])]
    out = []
    for result in results:
        where = (result.get("locations") or [{}])[0].get("physicalLocation", {})
        path = where.get("artifactLocation", {}).get("uri", "?")
        line = where.get("region", {}).get("startLine", "?")
        level = result.get("level", "warning")
        out.append(f"{level}[{result.get('ruleId')}] {path}:{line}: {result['message']['text']}")
    out.append(f"zizmor: {len(results)} finding(s)")
    return out


def main(argv: list[str]) -> int:
    """Print the log for the SARIF file named by argv[1]; always 0, the job is advisory."""
    print("\n".join(lines(json.loads(Path(argv[1]).read_text()))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
