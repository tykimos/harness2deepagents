#!/usr/bin/env python3
"""DeepAgents emission script.

Deterministic operations for deepagents-emission skill:
  resolve-output — pick a non-conflicting output directory
  load-ir        — load and validate IR
  render         — render code templates from IR
  copy-skills    — copy .claude/skills/* to app/skills/*
  emit-all       — full pipeline (resolve + render + copy + IR copy + .mcp.json mask)

Usage:
  python emit_deepagents.py emit-all --root <root> --ir <ir.yaml>

Stdlib only — uses simple {{VAR}} placeholder substitution (no Jinja2).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9_\-]{16,}", "openai_or_anthropic_key"),
    (r"AKIA[0-9A-Z]{16}", "aws_access_key"),
    (r"ghp_[A-Za-z0-9]{36}", "github_pat"),
    (r"gho_[A-Za-z0-9]{36}", "github_oauth"),
    (r"xoxb-[A-Za-z0-9-]+", "slack_bot"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private_key"),
]

EXCLUDED_NAMES = {".git", ".venv", "__pycache__", ".DS_Store", "node_modules"}


def load_yaml_simple(path: Path) -> dict:
    """Load YAML using PyYAML if available, else best-effort fallback.

    The IR is produced by extract_harness.py with JSON-escaped strings, so
    PyYAML safe_load works. Fallback to json.loads after a minimal preprocess
    is intentionally not provided — installing PyYAML is part of v0.1.
    """
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError(
            "PyYAML is required for emit_deepagents.py. Install with: pip install pyyaml"
        ) from e
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_output(root: Path) -> Path:
    base = root / "ports" / "deepagents"
    if not base.exists():
        return base
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return root / "ports" / f"deepagents_{timestamp}"


def assert_within(path: Path, root: Path) -> None:
    """Raise if path is outside root (path traversal protection)."""
    rp = path.resolve()
    rr = root.resolve()
    try:
        rp.relative_to(rr)
    except ValueError:
        raise RuntimeError(f"path {rp} is outside root {rr} — refusing to write")


def render_template(template: str, vars: dict[str, str]) -> str:
    """Replace {{KEY}} placeholders. Missing keys become empty string."""
    def replace(match: re.Match) -> str:
        key = match.group(1).strip()
        return str(vars.get(key, ""))
    return re.sub(r"\{\{\s*([A-Z_][A-Z0-9_]*)\s*\}\}", replace, template)


def synthesize_main_prompt(ir: dict) -> str:
    """Compose the main system prompt per PRD §13.7."""
    orch = ir.get("orchestrator", {}) or {}
    pattern = ir.get("harness", {}).get("architecture_pattern", {}).get("value", "unknown")
    delegation_summary = ir.get("workflow", {}).get("delegation_policy", {}).get("summary", "")
    workspace_dir = ir.get("artifacts", {}).get("workspace_dir") or "_workspace"
    artifact_conventions = ir.get("harness", {}).get("artifact_conventions", []) or []
    warnings = ir.get("quality", {}).get("warnings", []) or []
    stubs = ir.get("tools", {}).get("stubs_required", []) or []

    if orch.get("found"):
        original_prompt = orch.get("prompt", "")
    else:
        original_prompt = synthesize_orchestrator_prompt(ir, pattern)

    parts = [
        "# Converted Harness Orchestrator",
        "",
        original_prompt.strip(),
        "",
        "# Conversion Notes",
        "- This app was converted from RevFactory Harness output.",
        "- Use DeepAgents subagents instead of Claude Code Agent Teams.",
        "- Treat TeamCreate as the available subagent registry.",
        "- Treat TaskCreate as planning and delegation.",
        "- Treat SendMessage as result handoff mediated by the main agent.",
        "",
        "# Delegation Policy",
        delegation_summary,
        "",
        "# Artifact Policy",
        f"Use `{workspace_dir}/` for intermediate artifacts.",
    ]
    if artifact_conventions:
        parts.append("Artifact conventions:")
        for ac in artifact_conventions:
            parts.append(f"- {ac}")
    parts.extend([
        "",
        "# Safety and Validation Policy",
    ])
    if warnings:
        parts.append("Conversion warnings (review the report before relying on this app):")
        for w in warnings:
            parts.append(f"- {w}")
    if stubs:
        parts.append("")
        parts.append("Tool stubs to be implemented before live use:")
        for s in stubs:
            parts.append(f"- {s.get('name')}: {s.get('reason')}")
    return "\n".join(parts)


def synthesize_orchestrator_prompt(ir: dict, pattern: str) -> str:
    """Generate a synthetic orchestrator prompt when none was detected."""
    agents = ir.get("agents", []) or []
    skills = ir.get("skills", []) or []
    pattern_strategies = {
        "pipeline": "Follow an ordered phase checklist. Complete each phase before starting the next.",
        "fanout_fanin": "Delegate independent subtasks to subagents in parallel, then synthesize the results.",
        "expert_pool": "Select the most relevant subagent based on its description and the task at hand.",
        "producer_reviewer": "Delegate a draft to a producer subagent, then a reviewer; revise once if needed.",
        "supervisor": "Act as a supervisor: assess state, assign work to subagents dynamically, and integrate results.",
        "hierarchical": "Delegate broadly to subagents, which may further delegate or summarize back.",
        "hybrid": "Use phase-specific policies. Inspect each phase before deciding which subagents to invoke.",
        "unknown": "Plan first, delegate to specialized subagents, synthesize results, return a clear answer.",
    }
    strategy = pattern_strategies.get(pattern, pattern_strategies["unknown"])
    lines = [
        "You are the main agent of a converted Harness team.",
        "",
        f"Strategy ({pattern}): {strategy}",
        "",
        "Available subagents:",
    ]
    for a in agents:
        d = a.get("deepagents", {}) or {}
        lines.append(f"- {d.get('subagent_name', a.get('name'))}: {d.get('description', '')}")
    if skills:
        lines.append("")
        lines.append("Available skills (invoke when relevant to the task):")
        for s in skills:
            lines.append(f"- {s.get('name')}: {s.get('description', '')[:200]}")
    return "\n".join(lines)


def build_subagents(ir: dict) -> list[dict]:
    """Build SUBAGENTS list literal (Python data, ready for repr())."""
    out = []
    for a in ir.get("agents", []) or []:
        d = a.get("deepagents", {}) or {}
        body = a.get("system_prompt", "") or ""
        runtime_notes = (
            "\n\n# DeepAgents Runtime Notes\n"
            "You are running as a DeepAgents subagent.\n"
            "Return concise, structured results to the main agent.\n"
            "Write large intermediate outputs to the filesystem when appropriate.\n"
            "Do not assume direct peer-to-peer SendMessage; communicate through task results."
        )
        skills_paths = [f"/skills/{sk}/" for sk in (d.get("skills") or [])]
        out.append({
            "name": d.get("subagent_name") or a.get("name"),
            "description": d.get("description") or f"Use for {a.get('name')} tasks.",
            "system_prompt": body + runtime_notes,
            "skills": skills_paths,
        })
    return out


def render_subagents_literal(subagents: list[dict]) -> str:
    """Render subagents as a Python list literal that's readable when written to agent.py."""
    if not subagents:
        return "[]"
    lines = ["["]
    for s in subagents:
        lines.append("    {")
        lines.append(f"        \"name\": {json.dumps(s['name'], ensure_ascii=False)},")
        lines.append(f"        \"description\": {json.dumps(s['description'], ensure_ascii=False)},")
        body_repr = repr(s["system_prompt"])
        if body_repr.startswith("'") and "\n" in s["system_prompt"]:
            body_repr = "r\"\"\"" + s["system_prompt"].replace("\"\"\"", "\\\"\\\"\\\"") + "\"\"\""
        else:
            body_repr = json.dumps(s["system_prompt"], ensure_ascii=False)
        lines.append(f"        \"system_prompt\": {body_repr},")
        lines.append(f"        \"skills\": {json.dumps(s['skills'], ensure_ascii=False)},")
        lines.append("    },")
    lines.append("]")
    return "\n".join(lines)


def render_tool_stubs(stubs: list[dict]) -> tuple[str, str]:
    """Return (stub_definitions, tools_list_comments)."""
    if not stubs:
        return "", ""
    defs = []
    list_items = []
    for s in stubs:
        name = s.get("name", "unknown_stub")
        reason = s.get("reason", "")
        source = s.get("source_agent", "unknown")
        defs.append(
            f"def {name}(*args, **kwargs):\n"
            f"    \"\"\"TODO: Implement.\n\n"
            f"    Source: {source}\n"
            f"    Reason: {reason}\n"
            f"    Safety: do not call external APIs until credentials and policy are configured.\n"
            f"    \"\"\"\n"
            f"    raise NotImplementedError({json.dumps(name)} + ' is not implemented yet.')\n"
        )
        list_items.append(f"    # {name},")
    return "\n\n".join(defs), "\n".join(list_items)


def mask_secret(text: str) -> str:
    for pattern, _ in SECRET_PATTERNS:
        text = re.sub(pattern, "***REDACTED***", text)
    return text


def copy_skills(root: Path, ir: dict, dest: Path) -> dict:
    """Copy .claude/skills/* to <dest>/<id>/. Returns summary."""
    copied: list[str] = []
    skipped: list[str] = []
    skills = ir.get("skills", []) or []
    dest.mkdir(parents=True, exist_ok=True)
    for sk in skills:
        src_dir = root / sk["source_dir"]
        if not src_dir.is_dir():
            skipped.append(sk["id"])
            continue
        target = dest / sk["id"]
        if target.exists():
            target = dest / f"{sk['id']}__1"
        shutil.copytree(
            src_dir, target,
            ignore=lambda d, names: [n for n in names if n in EXCLUDED_NAMES],
        )
        copied.append(sk["id"])
    return {"copied": copied, "skipped": skipped, "count": len(copied)}


def copy_mcp(root: Path, app_dir: Path) -> dict:
    """Copy .mcp.json with secret masking."""
    src = root / ".mcp.json"
    if not src.is_file():
        return {"present": False}
    raw = src.read_text(encoding="utf-8", errors="replace")
    masked = mask_secret(raw)
    target = app_dir / ".mcp.json"
    target.write_text(masked, encoding="utf-8")
    return {"present": True, "secrets_masked": masked != raw}


def emit_all(root: Path, ir_path: Path, output_dir: Path | None = None) -> dict:
    """Run the full emit pipeline. Returns summary dict."""
    ir = load_yaml_simple(ir_path)
    if not isinstance(ir, dict):
        raise RuntimeError("IR is not a YAML mapping at the top level")
    if ir.get("schema_version") != "harness2deepagents/v1":
        raise RuntimeError(f"unexpected schema_version: {ir.get('schema_version')}")
    if ir.get("target", {}).get("emit_raw_langgraph") is True:
        raise RuntimeError("IR has emit_raw_langgraph=true, which is not supported.")

    out_dir = output_dir or resolve_output(root)
    assert_within(out_dir, root)
    app_dir = out_dir / "app"
    skills_dir = app_dir / "skills"
    logs_dir = out_dir / "logs"
    app_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    assets_dir = Path(__file__).parent.parent / "assets"

    main_prompt = synthesize_main_prompt(ir)
    subagents = build_subagents(ir)
    subagents_literal = render_subagents_literal(subagents)
    stubs = ir.get("tools", {}).get("stubs_required", []) or []
    tool_stubs_code, tools_list_code = render_tool_stubs(stubs)
    pattern = ir.get("harness", {}).get("architecture_pattern", {})
    mcp_servers = ir.get("tools", {}).get("mcp_servers", []) or []
    mcp_env_vars: list[str] = []
    for server in mcp_servers:
        mcp_env_vars.extend(server.get("env_vars", []) or [])

    common_vars = {
        "SOURCE_ROOT": str(root),
        "GENERATED_AT": dt.datetime.now(dt.timezone.utc).isoformat(),
        "MAIN_SYSTEM_PROMPT": main_prompt.replace('"""', '\\"\\"\\"'),
        "SUBAGENTS_LITERAL": subagents_literal,
        "MODEL_DEFAULT": ir.get("target", {}).get("model", {}).get("default", "anthropic:claude-sonnet-4-6"),
        "APP_NAME_DEFAULT": "converted_harness",
        "PROJECT_NAME": "converted-harness-deepagents",
        "TOOL_STUBS": tool_stubs_code,
        "TOOLS_LIST": tools_list_code,
        "MCP_SERVERS": ", ".join(s.get("name", "") for s in mcp_servers) or "(none detected)",
        "MCP_ENV_VARS": ", ".join(mcp_env_vars) or "(none detected)",
        "MCP_STATUS": "detected and copied (secrets masked)" if mcp_servers else "not detected",
        "ARCHITECTURE_PATTERN": pattern.get("value", "unknown"),
        "PATTERN_CONFIDENCE": f"{pattern.get('confidence', 0.0):.2f}",
        "AGENT_COUNT": str(len(ir.get("agents", []) or [])),
        "SKILL_COUNT": str(len(ir.get("skills", []) or [])),
        "EXTRA_DEPS": "",
        "EXTRA_ENV_VARS_TABLE": "",
    }

    files_to_render = [
        ("agent.py.tmpl", app_dir / "agent.py"),
        ("config.py.tmpl", app_dir / "config.py"),
        ("tools.py.tmpl", app_dir / "tools.py"),
        ("smoke_test.py.tmpl", app_dir / "smoke_test.py"),
        ("requirements.txt.tmpl", app_dir / "requirements.txt"),
        ("pyproject.toml.tmpl", app_dir / "pyproject.toml"),
        ("README.md.tmpl", app_dir / "README.md"),
    ]

    has_mcp = bool(mcp_servers) or (root / ".mcp.json").is_file()
    if has_mcp:
        files_to_render.append(("mcp_tools.py.tmpl", app_dir / "mcp_tools.py"))

    for tmpl_name, target in files_to_render:
        tmpl_path = assets_dir / tmpl_name
        if not tmpl_path.is_file():
            continue
        rendered = render_template(tmpl_path.read_text(encoding="utf-8"), common_vars)
        target.write_text(rendered, encoding="utf-8")

    skill_summary = copy_skills(root, ir, skills_dir)
    mcp_summary = copy_mcp(root, app_dir)

    final_ir_path = out_dir / "harness.deepagents.ir.yaml"
    shutil.copy2(ir_path, final_ir_path)

    return {
        "output_dir": str(out_dir),
        "files_rendered": [str(t) for _, t in files_to_render],
        "skills": skill_summary,
        "mcp": mcp_summary,
        "ir_copied_to": str(final_ir_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="DeepAgents emitter")
    parser.add_argument("command", choices=[
        "resolve-output", "load-ir", "render", "copy-skills", "emit-all",
    ])
    parser.add_argument("--root", default=".", help="Project root")
    parser.add_argument("--ir", help="IR YAML path")
    parser.add_argument("--out", help="Output directory (override)")
    parser.add_argument("--summary-out", help="Write JSON summary here")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: root '{root}' is not a directory", file=sys.stderr)
        return 2

    if args.command == "resolve-output":
        out = resolve_output(root)
        print(out)
        return 0

    if args.command == "load-ir":
        if not args.ir:
            print("error: --ir is required", file=sys.stderr)
            return 2
        ir = load_yaml_simple(Path(args.ir))
        print(json.dumps({
            "schema_version": ir.get("schema_version"),
            "agents_count": len(ir.get("agents", []) or []),
            "skills_count": len(ir.get("skills", []) or []),
            "orchestrator_found": (ir.get("orchestrator") or {}).get("found"),
        }, indent=2))
        return 0

    if args.command == "emit-all":
        if not args.ir:
            print("error: --ir is required", file=sys.stderr)
            return 2
        ir_path = Path(args.ir).resolve()
        if not ir_path.is_file():
            print(f"error: IR not found at {ir_path}", file=sys.stderr)
            return 2
        out_dir = Path(args.out).resolve() if args.out else None
        summary = emit_all(root, ir_path, out_dir)
        if args.summary_out:
            Path(args.summary_out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0

    print(f"command '{args.command}' not yet implemented at top level (use emit-all)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
