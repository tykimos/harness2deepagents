#!/usr/bin/env python3
"""Standalone secret scanner.

Usable independently of validate_port.py. Scans a directory for secret-like
literals and either reports findings (default) or rewrites files with
matches replaced by ***REDACTED*** (--redact).

Usage:
  python secret_scan.py --output <dir> [--report] [--redact]

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


PATTERNS = [
    (r"sk-[A-Za-z0-9_\-]{16,}", "openai_or_anthropic_key"),
    (r"AKIA[0-9A-Z]{16}", "aws_access_key"),
    (r"ghp_[A-Za-z0-9]{36}", "github_pat"),
    (r"gho_[A-Za-z0-9]{36}", "github_oauth"),
    (r"ghu_[A-Za-z0-9]{36}", "github_user"),
    (r"ghs_[A-Za-z0-9]{36}", "github_server"),
    (r"xoxb-[A-Za-z0-9-]+", "slack_bot"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private_key"),
]

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".DS_Store"}
SCAN_SUFFIXES = {".py", ".json", ".toml", ".yaml", ".yml", ".env", ".cfg", ".ini", ".sh"}

COMPILED = [(re.compile(p), label) for p, label in PATTERNS]


def scan_file(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [{"error": str(e)}]
    findings: list[dict] = []
    for regex, label in COMPILED:
        for match in regex.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            findings.append({
                "type": label,
                "line": line_no,
                "length": len(match.group(0)),
            })
    return findings


def redact_file(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0
    original = text
    count = 0
    for regex, _ in COMPILED:
        text, n = regex.subn("***REDACTED***", text)
        count += n
    if text != original:
        path.write_text(text, encoding="utf-8")
    return count


def walk(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in SCAN_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan directory for secret patterns")
    parser.add_argument("--output", required=True, help="directory to scan")
    parser.add_argument("--report", action="store_true", help="print JSON findings (default)")
    parser.add_argument("--redact", action="store_true", help="rewrite files with redactions")
    args = parser.parse_args()

    root = Path(args.output).resolve()
    if not root.is_dir():
        print(f"error: '{root}' is not a directory", file=sys.stderr)
        return 2

    summary: dict = {"root": str(root), "files_with_findings": 0, "total_findings": 0, "files": []}
    redacted_total = 0

    for path in walk(root):
        if args.redact:
            n = redact_file(path)
            if n:
                redacted_total += n
                summary["files"].append({
                    "path": str(path.relative_to(root)),
                    "redactions": n,
                })
        else:
            findings = scan_file(path)
            if findings:
                summary["files_with_findings"] += 1
                summary["total_findings"] += len(findings)
                summary["files"].append({
                    "path": str(path.relative_to(root)),
                    "findings": findings,
                })

    if args.redact:
        summary["redacted_total"] = redacted_total

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if (not args.redact and summary["total_findings"] > 0) else 0


if __name__ == "__main__":
    sys.exit(main())
