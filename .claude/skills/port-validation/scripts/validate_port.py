#!/usr/bin/env python3
"""DeepAgents port validator.

Runs the 7-stage validation pipeline and writes logs/validation.json.
Designed to be invoked by the port-validator agent. Live invocation of
the model is never performed.

Usage:
  python validate_port.py --output <output_dir>

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REQUIRED_FILES = [
    "app/agent.py",
    "app/config.py",
    "app/tools.py",
    "app/smoke_test.py",
    "app/requirements.txt",
    "app/pyproject.toml",
    "app/README.md",
]

ANTI_PATTERN_RE = [
    (re.compile(r"^\s*from\s+langgraph\.graph\s+import", re.MULTILINE), "raw_langgraph_import"),
    (re.compile(r"^\s*import\s+langgraph\.graph", re.MULTILINE), "raw_langgraph_import"),
    (re.compile(r"^\s*from\s+langgraph\b", re.MULTILINE), "langgraph_import"),
    (re.compile(r"langgraph\.graph\.StateGraph\s*\("), "langgraph_state_graph_call"),
    (re.compile(r"^\s*from\s+langchain\.agents\s+import\s+create_agent", re.MULTILINE), "single_create_agent"),
]

SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "openai_or_anthropic_key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "aws_access_key"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "github_pat"),
    (re.compile(r"gho_[A-Za-z0-9]{36}"), "github_oauth"),
    (re.compile(r"xoxb-[A-Za-z0-9-]+"), "slack_bot"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private_key"),
]

REDACTED_MARKER = "***REDACTED***"


def make_check(name: str, status: str, details: list[str] | None = None) -> dict:
    return {"name": name, "status": status, "details": details or []}


def stage_ir_yaml_parse(output_dir: Path) -> dict:
    ir_path = output_dir / "harness.deepagents.ir.yaml"
    if not ir_path.is_file():
        return make_check("ir_yaml_parse", "fail", [f"IR not found at {ir_path}"])
    try:
        import yaml
    except ImportError:
        return make_check("ir_yaml_parse", "warn", ["PyYAML not installed; skipping deep parse"])
    try:
        with ir_path.open(encoding="utf-8") as f:
            yaml.safe_load(f)
        return make_check("ir_yaml_parse", "pass")
    except Exception as e:
        return make_check("ir_yaml_parse", "fail", [str(e)])


def stage_ir_required_fields(output_dir: Path) -> dict:
    ir_path = output_dir / "harness.deepagents.ir.yaml"
    if not ir_path.is_file():
        return make_check("ir_required_fields", "not_run", ["IR file missing"])
    try:
        import yaml
    except ImportError:
        return make_check("ir_required_fields", "not_run", ["PyYAML not installed"])
    with ir_path.open(encoding="utf-8") as f:
        ir = yaml.safe_load(f)
    if not isinstance(ir, dict):
        return make_check("ir_required_fields", "fail", ["IR is not a mapping"])
    issues: list[str] = []
    if ir.get("schema_version") != "harness2deepagents/v1":
        issues.append(f"unexpected schema_version: {ir.get('schema_version')}")
    if ir.get("target", {}).get("runtime") != "deepagents":
        issues.append("target.runtime must be 'deepagents'")
    if ir.get("target", {}).get("emit_raw_langgraph") is True:
        issues.append("target.emit_raw_langgraph must be false")
    for key in ("source", "harness", "agents", "skills"):
        if key not in ir:
            issues.append(f"missing top-level key '{key}'")
    if issues:
        return make_check("ir_required_fields", "fail", issues)
    return make_check("ir_required_fields", "pass")


def stage_required_files(output_dir: Path, ir: dict | None) -> dict:
    missing: list[str] = []
    for rel in REQUIRED_FILES:
        if not (output_dir / rel).is_file():
            missing.append(rel)
    if ir and ir.get("skills"):
        if not (output_dir / "app" / "skills").is_dir():
            missing.append("app/skills/")
    if ir and ir.get("tools", {}).get("mcp_servers"):
        if not (output_dir / "app" / "mcp_tools.py").is_file():
            missing.append("app/mcp_tools.py")
    if missing:
        return make_check("required_files", "fail", [f"missing: {p}" for p in missing])
    return make_check("required_files", "pass")


def stage_python_compile(output_dir: Path) -> dict:
    app_dir = output_dir / "app"
    if not app_dir.is_dir():
        return make_check("python_compile", "fail", ["app/ directory missing"])
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(app_dir)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return make_check("python_compile", "pass")
    err = (result.stderr or result.stdout).strip()
    return make_check("python_compile", "fail", err.splitlines()[:10])


def stage_skill_copy(output_dir: Path, ir: dict | None) -> dict:
    if not ir:
        return make_check("skill_copy", "not_run", ["IR unavailable"])
    expected = [s.get("id") for s in (ir.get("skills") or []) if s.get("id")]
    skills_dir = output_dir / "app" / "skills"
    if not expected:
        return make_check("skill_copy", "pass", ["no skills expected"])
    if not skills_dir.is_dir():
        return make_check("skill_copy", "fail", ["app/skills/ missing"])
    actual = {p.name for p in skills_dir.iterdir() if p.is_dir()}
    missing = [e for e in expected if e not in actual and f"{e}__1" not in actual]
    issues: list[str] = []
    if missing:
        issues.append(f"missing skill folders: {missing}")
    for skill_dir in skills_dir.iterdir():
        if skill_dir.is_dir():
            has_skill_md = any((skill_dir / n).is_file() for n in ("SKILL.md", "skill.md"))
            if not has_skill_md:
                issues.append(f"{skill_dir.name}: SKILL.md missing")
    if issues:
        return make_check("skill_copy", "fail", issues)
    return make_check("skill_copy", "pass")


SECRET_SCAN_SUFFIXES = {".py", ".json", ".toml", ".yaml", ".yml", ".env", ".cfg", ".ini", ".sh"}


def stage_secret_scan(output_dir: Path) -> dict:
    """Scan code/config files for raw secrets.

    Skips Markdown/text/binary files. Real secrets live in code and config;
    Markdown is documentation that often mentions secret patterns by name
    (e.g. 'BEGIN PRIVATE KEY' in a detection rules table).
    """
    findings: list[str] = []
    masked_count = 0
    for path in output_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in SECRET_SCAN_SUFFIXES:
            continue
        if any(part in {".git", "__pycache__", ".venv"} for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for pattern, label in SECRET_PATTERNS:
            for _match in pattern.finditer(text):
                rel = path.relative_to(output_dir)
                findings.append(f"{rel}: pattern={label} (raw secret detected)")
        masked_count += text.count(REDACTED_MARKER)
    if findings:
        return make_check("secret_scan", "fail", findings)
    if masked_count:
        return make_check("secret_scan", "warn", [f"{masked_count} masked literal(s) found"])
    return make_check("secret_scan", "pass")


def stage_smoke_test(output_dir: Path) -> dict:
    app_dir = output_dir / "app"
    if not (app_dir / "agent.py").is_file():
        return make_check("smoke_test", "fail", ["agent.py missing"])
    cmd = [
        sys.executable, "-c",
        "import sys; sys.path.insert(0, '.'); "
        "import agent; "
        "assert hasattr(agent, 'agent'), 'agent object missing'; "
        "assert hasattr(agent, 'invoke'), 'invoke function missing'; "
        "print('OK')",
    ]
    result = subprocess.run(cmd, cwd=app_dir, capture_output=True, text=True)
    if result.returncode == 0:
        return make_check("smoke_test", "pass")
    err = (result.stderr or result.stdout).strip()
    if "ModuleNotFoundError" in err and "deepagents" in err:
        return make_check("smoke_test", "warn",
                          ["deepagents not installed — run `pip install -r requirements.txt`",
                           err.splitlines()[-1] if err else ""])
    return make_check("smoke_test", "fail", err.splitlines()[:10])


def stage_anti_patterns(output_dir: Path) -> dict:
    findings: list[str] = []
    app_dir = output_dir / "app"
    if not app_dir.is_dir():
        return make_check("raw_langgraph_emitter", "not_run", ["app/ missing"])
    for path in app_dir.rglob("*.py"):
        if any(part in {"__pycache__", "skills"} for part in path.relative_to(app_dir).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for pattern, label in ANTI_PATTERN_RE:
            for m in pattern.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                findings.append(f"{path.relative_to(output_dir)}:{line_no}: {label}")
    if findings:
        return make_check("raw_langgraph_emitter", "fail", findings)
    return make_check("raw_langgraph_emitter", "pass")


def aggregate_status(checks: list[dict]) -> str:
    statuses = {c["status"] for c in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "pass_with_warnings"
    if "not_run" in statuses and "pass" not in statuses:
        return "not_run"
    return "pass"


def run_all(output_dir: Path, mode: str = "full") -> dict:
    output_dir = output_dir.resolve()
    checks: list[dict] = []

    c1 = stage_ir_yaml_parse(output_dir); checks.append(c1)
    c2 = stage_ir_required_fields(output_dir); checks.append(c2)

    ir: dict | None = None
    ir_path = output_dir / "harness.deepagents.ir.yaml"
    if c1["status"] == "pass" and ir_path.is_file():
        try:
            import yaml
            ir = yaml.safe_load(ir_path.read_text(encoding="utf-8"))
        except Exception:
            ir = None

    if mode == "audit_only":
        for name in ("required_files", "python_compile", "skill_copy",
                     "secret_scan", "smoke_test", "raw_langgraph_emitter"):
            checks.append(make_check(name, "not_run", ["audit_only mode"]))
    else:
        checks.append(stage_required_files(output_dir, ir))
        checks.append(stage_python_compile(output_dir))
        checks.append(stage_skill_copy(output_dir, ir))
        checks.append(stage_secret_scan(output_dir))
        checks.append(stage_smoke_test(output_dir))
        checks.append(stage_anti_patterns(output_dir))

    return {
        "status": aggregate_status(checks),
        "mode": mode,
        "checks": checks,
        "fix_requests_sent": 0,
        "fix_loop_exhausted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DeepAgents port validator")
    parser.add_argument("--output", required=True, help="output_dir (e.g. ports/deepagents/)")
    parser.add_argument("--mode", default="full", choices=["full", "audit_only"])
    parser.add_argument("--write-log", default=None,
                        help="path for validation.json (default: <output>/logs/validation.json)")
    args = parser.parse_args()

    output_dir = Path(args.output).resolve()
    if not output_dir.is_dir():
        print(f"error: output dir '{output_dir}' not found", file=sys.stderr)
        return 2

    summary = run_all(output_dir, args.mode)

    log_path = Path(args.write_log) if args.write_log else (output_dir / "logs" / "validation.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["status"] != "fail" else 1


if __name__ == "__main__":
    sys.exit(main())
