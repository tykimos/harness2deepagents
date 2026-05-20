#!/usr/bin/env python3
"""Harness source extraction script.

Deterministic operations for harness-source-extraction skill:
  discover     — discover Harness source files
  parse-agents — parse .claude/agents/*.md
  parse-skills — parse .claude/skills/*/SKILL.md
  orchestrator-score — score orchestrator candidates
  pattern-detect — score architecture patterns
  claude-ops   — find Claude-only operations
  mcp-scan     — scan .mcp.json for env vars and secrets
  fingerprint  — compute source sha256
  build-ir     — assemble all of the above into harness.deepagents.ir.yaml

Usage:
  python extract_harness.py <command> [--root <path>] [--out <path>] [other flags]

Stdlib only — no third-party deps required for v0.1.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    (r"sk-[A-Za-z0-9_\-]{16,}", "openai_or_anthropic_key"),
    (r"AKIA[0-9A-Z]{16}", "aws_access_key"),
    (r"ghp_[A-Za-z0-9]{36}", "github_pat"),
    (r"gho_[A-Za-z0-9]{36}", "github_oauth"),
    (r"ghu_[A-Za-z0-9]{36}", "github_user"),
    (r"ghs_[A-Za-z0-9]{36}", "github_server"),
    (r"xoxb-[A-Za-z0-9-]+", "slack_bot"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private_key"),
]

CLAUDE_OPS = [
    "TeamCreate", "TeamDelete", "TaskCreate", "TaskUpdate", "TaskGet",
    "SendMessage", "run_in_background",
]

ORCH_NAME_HINTS = [
    ("orchestrator", 5), ("workflow", 4), ("runner", 4),
    ("coordinator", 4), ("supervisor", 4),
    ("오케스트레이터", 4), ("워크플로우", 4), ("조율", 4),
]

ORCH_BODY_HINTS = [
    ("TeamCreate", 5), ("TaskCreate", 4), ("SendMessage", 4),
    ("_workspace", 2),
]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter without requiring PyYAML.

    Returns (frontmatter_dict, body). If parse fails, returns ({}, text).
    """
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_raw, body = parts[1], parts[2]
    fm: dict[str, Any] = {}
    current_key = None
    list_buffer: list[str] | None = None
    for line in fm_raw.splitlines():
        if not line.strip():
            continue
        if list_buffer is not None and line.startswith(("  -", "\t-")):
            list_buffer.append(line.split("-", 1)[1].strip().strip("\"'"))
            continue
        if list_buffer is not None and not line.startswith(" "):
            fm[current_key] = list_buffer
            list_buffer = None
            current_key = None
        m = re.match(r"^([A-Za-z_][\w\-]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        key, value = m.group(1), m.group(2).strip()
        if value == "" or value == "|":
            list_buffer = []
            current_key = key
            continue
        value = value.strip("\"'")
        fm[key] = value
    if list_buffer is not None and current_key is not None:
        fm[current_key] = list_buffer
    return fm, body.lstrip("\n")


def normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        if "," in value:
            return [v.strip() for v in value.split(",") if v.strip()]
        return [value.strip()] if value.strip() else []
    return [str(value)]


def mask_secret(text: str) -> tuple[str, list[dict]]:
    """Replace secret-like literals with ***REDACTED*** marker."""
    findings: list[dict] = []
    for pattern, label in SECRET_PATTERNS:
        for match in re.finditer(pattern, text):
            findings.append({"type": label, "length": len(match.group(0))})
        text = re.sub(pattern, "***REDACTED***", text)
    return text, findings


def discover(root: Path) -> dict:
    detected: dict[str, list[str]] = {
        "claude_md": [], "agents": [], "skills": [], "orchestrators": [],
        "mcp": [], "settings": [], "workspace": [],
    }
    if (root / "CLAUDE.md").is_file():
        detected["claude_md"].append("CLAUDE.md")
    agents_dir = root / ".claude" / "agents"
    if agents_dir.is_dir():
        for p in sorted(agents_dir.glob("*.md")):
            detected["agents"].append(str(p.relative_to(root)))
    skills_dir = root / ".claude" / "skills"
    if skills_dir.is_dir():
        for sk in sorted(skills_dir.iterdir()):
            if not sk.is_dir():
                continue
            for fname in ("SKILL.md", "skill.md"):
                if (sk / fname).is_file():
                    detected["skills"].append(str((sk / fname).relative_to(root)))
                    break
    if (root / ".mcp.json").is_file():
        detected["mcp"].append(".mcp.json")
    if (root / ".claude" / "settings.json").is_file():
        detected["settings"].append(".claude/settings.json")
    if (root / "_workspace").is_dir():
        detected["workspace"].append("_workspace/")
    return detected


def parse_agent_file(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(text)
    warnings: list[str] = []
    if not fm:
        warnings.append("frontmatter_missing")
    file_id = path.stem
    name = fm.get("name") or file_id
    description = fm.get("description") or _first_paragraph(body)
    skills_explicit = normalize_list(fm.get("skills") or fm.get("skill"))
    tools_explicit = normalize_list(fm.get("tools"))
    return {
        "id": file_id,
        "name": name,
        "source_file": str(path.relative_to(root)),
        "description": description or "",
        "system_prompt": body,
        "model_hint": fm.get("model"),
        "frontmatter": fm,
        "skills_detected": {"explicit": skills_explicit, "inferred": []},
        "tools_detected": {"explicit": tools_explicit, "inferred": []},
        "warnings": warnings,
    }


def _first_paragraph(text: str) -> str:
    for block in text.split("\n\n"):
        block = block.strip()
        if not block or block.startswith("#"):
            continue
        return " ".join(block.splitlines())[:280]
    return ""


def parse_skill_file(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(text)
    warnings: list[str] = []
    if not fm:
        warnings.append("frontmatter_missing")
    skill_dir = path.parent
    sk_id = skill_dir.name
    name = fm.get("name") or sk_id
    description = fm.get("description") or ""
    if not description:
        warnings.append("description_missing")
    if len(description) > 1024:
        warnings.append("description_too_long")
    size = path.stat().st_size
    if size > 10 * 1024 * 1024:
        warnings.append("skill_md_too_large")
    references = _list_files(skill_dir / "references", root)
    scripts = _list_files(skill_dir / "scripts", root)
    assets = _list_files(skill_dir / "assets", root)
    return {
        "id": sk_id,
        "name": name,
        "source_dir": str(skill_dir.relative_to(root)),
        "target_dir": f"app/skills/{sk_id}",
        "description": description,
        "description_length": len(description),
        "skill_md_size_bytes": size,
        "portable_to_deepagents": size <= 10 * 1024 * 1024,
        "references": references,
        "scripts": scripts,
        "assets": assets,
        "body_summary": _first_paragraph(body),
        "warnings": warnings,
    }


def _list_files(directory: Path, root: Path) -> list[str]:
    if not directory.is_dir():
        return []
    out: list[str] = []
    for p in sorted(directory.rglob("*")):
        if p.is_file() and not _is_excluded(p):
            out.append(str(p.relative_to(root)))
    return out


def _is_excluded(p: Path) -> bool:
    parts = set(p.parts)
    return bool(parts & {".git", ".venv", "__pycache__", ".DS_Store"})


def score_orchestrator_candidates(skills: list[dict], agents: list[dict], root: Path) -> list[dict]:
    agent_names = [a["name"] for a in agents]
    candidates: list[dict] = []
    for sk in skills:
        score = 0
        evidence: list[str] = []
        name_lower = sk["name"].lower()
        for hint, points in ORCH_NAME_HINTS:
            if hint in name_lower or hint in sk["id"].lower():
                score += points
                evidence.append(f"name contains '{hint}' (+{points})")
        skill_md = root / sk["source_dir"] / "SKILL.md"
        if not skill_md.is_file():
            skill_md = root / sk["source_dir"] / "skill.md"
        body = skill_md.read_text(encoding="utf-8", errors="replace") if skill_md.is_file() else ""
        for hint, points in ORCH_BODY_HINTS:
            if hint in body:
                score += points
                evidence.append(f"body mentions '{hint}' (+{points})")
        agent_mentions = sum(1 for an in agent_names if an in body)
        if agent_mentions >= 2:
            score += 3
            evidence.append(f"{agent_mentions} agent name mentions (+3)")
        if re.search(r"phase\s*\d", body, re.IGNORECASE):
            score += 3
            evidence.append("phase markers (+3)")
        candidates.append({
            "skill_id": sk["id"],
            "source_file": sk["source_dir"] + "/SKILL.md",
            "score": score,
            "evidence": evidence,
        })
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def detect_pattern(text: str) -> dict:
    scores = {
        "pipeline": 0, "fanout_fanin": 0, "expert_pool": 0,
        "producer_reviewer": 0, "supervisor": 0, "hierarchical": 0,
    }
    evidence: dict[str, list[str]] = {k: [] for k in scores}
    rules = [
        ("pipeline", 2, [r"phase\s*\d", "depends_on", "sequential", "순차"]),
        ("fanout_fanin", 3, ["parallel", "fan-out", "병렬", "merge", "aggregate", "synthesis", "종합"]),
        ("expert_pool", 2, ["expert", "pool", "route by", "select expert", "전문가"]),
        ("producer_reviewer", 3, ["review", "revise", "approve", "QA", "retry", "리뷰", "승인"]),
        ("supervisor", 3, ["supervisor", "coordinator", "감독자", "assign dynamically"]),
        ("hierarchical", 3, ["parent", "child", "delegate recursively", "재귀적 위임"]),
    ]
    for pat, points, signals in rules:
        for sig in signals:
            if re.search(sig, text, re.IGNORECASE):
                scores[pat] += points
                evidence[pat].append(f"matched '{sig}' (+{points})")
    top = max(scores, key=lambda k: scores[k])
    top_score = scores[top]
    sorted_scores = sorted(scores.values(), reverse=True)
    is_hybrid = (
        len(sorted_scores) > 1
        and sorted_scores[0] > 0
        and sorted_scores[1] / max(sorted_scores[0], 1) > 0.8
    )
    max_possible = 30
    confidence = min(top_score / max_possible, 1.0)
    if confidence < 0.3:
        return {"value": "unknown", "confidence": confidence, "evidence": []}
    if is_hybrid:
        return {
            "value": "hybrid",
            "confidence": confidence,
            "evidence": evidence[top][:3],
            "components": [k for k, v in scores.items() if v > 0],
        }
    return {"value": top, "confidence": confidence, "evidence": evidence[top]}


def find_claude_ops(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for op in CLAUDE_OPS:
        n = len(re.findall(rf"\b{re.escape(op)}\b", text))
        if n:
            counts[op] = n
    return counts


def scan_mcp(root: Path) -> dict:
    mcp_path = root / ".mcp.json"
    if not mcp_path.is_file():
        return {"present": False}
    raw = mcp_path.read_text(encoding="utf-8", errors="replace")
    masked, secrets = mask_secret(raw)
    env_vars: list[str] = list(set(re.findall(r"\$\{?([A-Z][A-Z0-9_]+)\}?", raw)))
    try:
        data = json.loads(masked)
        servers = list(data.get("mcpServers", {}).keys())
    except json.JSONDecodeError:
        servers = []
    return {
        "present": True,
        "servers": servers,
        "env_vars": env_vars,
        "masked_secret_count": len(secrets),
        "secret_types": list({s["type"] for s in secrets}),
    }


def compute_fingerprint(root: Path, files: list[str]) -> str:
    h = hashlib.sha256()
    for rel in sorted(files):
        p = root / rel
        if not p.is_file():
            continue
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
    return f"sha256:{h.hexdigest()}"


def build_ir(root: Path, mode: str) -> dict:
    detected = discover(root)
    agents = [parse_agent_file(root / p, root) for p in detected["agents"]]
    skills = [parse_skill_file(root / p, root) for p in detected["skills"]]

    orch_candidates = score_orchestrator_candidates(skills, agents, root)
    primary_orch = orch_candidates[0] if orch_candidates and orch_candidates[0]["score"] >= 8 else None

    orchestrator: dict[str, Any]
    if primary_orch:
        sk = next(s for s in skills if s["id"] == primary_orch["skill_id"])
        skill_md = root / sk["source_dir"] / "SKILL.md"
        if not skill_md.is_file():
            skill_md = root / sk["source_dir"] / "skill.md"
        raw = skill_md.read_text(encoding="utf-8", errors="replace") if skill_md.is_file() else ""
        _, body_only = parse_frontmatter(raw)
        ops_counts = find_claude_ops(raw)
        orchestrator = {
            "found": True,
            "source_file": str(skill_md.relative_to(root)),
            "name": sk["name"],
            "description": sk["description"],
            "prompt": body_only.strip(),
            "detected_operations": [
                {"operation": op, "count": n, "mapping": _op_mapping(op)}
                for op, n in ops_counts.items()
            ],
            "warnings": [],
        }
    else:
        orchestrator = {
            "found": False,
            "synthetic_required": True,
            "warnings": ["orchestrator_not_found"],
        }

    pattern_text = "\n".join([s.get("body_summary", "") for s in skills]) + "\n" + \
                   "\n".join([a.get("description", "") for a in agents])
    if primary_orch:
        sk = next(s for s in skills if s["id"] == primary_orch["skill_id"])
        skill_md = root / sk["source_dir"] / "SKILL.md"
        if skill_md.is_file():
            pattern_text += "\n" + skill_md.read_text(encoding="utf-8", errors="replace")
    pattern = detect_pattern(pattern_text)

    mcp_info = scan_mcp(root)

    deepagents_agents = [_to_deepagents_agent(a, skills) for a in agents]

    all_files = (
        detected["agents"] + detected["skills"]
        + (detected["claude_md"] or [])
        + (detected["mcp"] or [])
        + (detected["settings"] or [])
    )
    fingerprint = compute_fingerprint(root, all_files)

    warnings: list[str] = []
    if not detected["agents"]:
        warnings.append("skills_only_harness")
    if not detected["skills"]:
        warnings.append("agents_without_skills")
    if not primary_orch:
        warnings.append("orchestrator_not_found")
    if pattern["value"] == "unknown":
        warnings.append("pattern_unknown")

    ir = {
        "schema_version": "harness2deepagents/v1",
        "metadata": {
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "generator": "harness2deepagents",
            "generator_version": "0.1.0",
            "mode": mode,
        },
        "source": {
            "root": str(root),
            "source_fingerprint": fingerprint,
            "assumed_generator": "revfactory/harness",
            "claude_base": True,
            "detected_files": detected,
        },
        "harness": {
            "name": "converted_harness",
            "summary": _summarize(agents, skills, primary_orch, pattern),
            "architecture_pattern": pattern,
            "execution_mode": _infer_execution_mode(agents, skills, primary_orch),
            "workspace_dir": "_workspace" if detected["workspace"] else None,
            "artifact_conventions": [],
        },
        "target": {
            "runtime": "deepagents",
            "emit_raw_langgraph": False,
            "output_dir": "ports/deepagents/app",
            "model": {
                "env_var": "DEEPAGENTS_MODEL",
                "default": "anthropic:claude-sonnet-4-6",
            },
            "package_manager": "unknown",
        },
        "agents": deepagents_agents,
        "skills": skills,
        "orchestrator": orchestrator,
        "workflow": {
            "phases": [],
            "delegation_policy": {
                "summary": _delegation_summary(pattern),
                "rules": [],
            },
            "review_policy": {
                "enabled": pattern["value"] == "producer_reviewer",
                "reviewer_agents": [],
                "retry_limit": 1,
            },
        },
        "tools": {
            "mcp_servers": _mcp_to_tools(mcp_info),
            "langchain_tools": [],
            "stubs_required": _infer_tool_stubs(agents),
            "environment_variables": [
                {"name": "ANTHROPIC_API_KEY", "required": True, "source": "model provider"},
                {"name": "DEEPAGENTS_MODEL", "required": False, "default": "anthropic:claude-sonnet-4-6"},
            ],
        },
        "artifacts": {
            "workspace_dir": "_workspace" if detected["workspace"] else None,
            "output_files": [],
            "generated_files": [],
        },
        "quality": {
            "conversion_score": None,
            "blockers": [],
            "warnings": warnings,
            "manual_actions": [],
        },
        "validation": {
            "yaml_parse": "not_run",
            "python_compile": "not_run",
            "skill_copy": "not_run",
            "secret_scan": "not_run",
            "smoke_test": "not_run",
        },
    }
    return ir


def _to_deepagents_agent(agent: dict, skills: list[dict]) -> dict:
    skill_names = {s["name"]: s["id"] for s in skills}
    explicit = agent["skills_detected"]["explicit"]
    matched_skills = [sn for sn in explicit if sn in skill_names]
    body = agent.get("system_prompt", "")
    inferred: list[str] = []
    for sk in skills:
        if sk["name"] in body and sk["name"] not in matched_skills:
            inferred.append(sk["name"])
    if inferred:
        agent["skills_detected"]["inferred"] = inferred
    return {
        **agent,
        "deepagents": {
            "subagent_name": agent["name"],
            "description": agent["description"][:280] if agent["description"] else f"Use for {agent['name']} tasks.",
            "skills": matched_skills + inferred,
            "tools": agent["tools_detected"]["explicit"],
        },
    }


def _summarize(agents: list[dict], skills: list[dict], orch: dict | None, pattern: dict) -> str:
    parts = [f"Detected {len(agents)} agent(s) and {len(skills)} skill(s)"]
    if orch:
        parts.append(f"orchestrator '{orch['skill_id']}'")
    parts.append(f"pattern={pattern['value']} (confidence={pattern['confidence']:.2f})")
    return ", ".join(parts) + "."


def _infer_execution_mode(agents: list[dict], skills: list[dict], orch: dict | None) -> dict:
    text = ""
    if orch:
        sk_id = orch["skill_id"]
        text = next((s.get("body_summary", "") for s in skills if s["id"] == sk_id), "")
    if "TeamCreate" in text or "agent team" in text.lower():
        return {"value": "agent_team", "confidence": 0.8}
    if "Agent(" in text and len(agents) >= 1:
        return {"value": "subagents", "confidence": 0.6}
    return {"value": "unknown", "confidence": 0.3}


def _delegation_summary(pattern: dict) -> str:
    p = pattern["value"]
    summaries = {
        "pipeline": "Main agent follows an ordered phase checklist.",
        "fanout_fanin": "Main agent delegates independent subtasks then synthesizes.",
        "expert_pool": "Main agent selects subagent by description and task type.",
        "producer_reviewer": "Main agent delegates draft, then review; revise once if needed.",
        "supervisor": "Main agent acts as supervisor, assigning work dynamically.",
        "hierarchical": "Main agent delegates broadly; subagents may summarize back.",
        "hybrid": "Main agent uses phase-specific policy blocks.",
        "unknown": "Main agent plans first, delegates to specialized subagents, synthesizes results.",
    }
    return summaries.get(p, summaries["unknown"])


def _mcp_to_tools(mcp_info: dict) -> list[dict]:
    if not mcp_info.get("present"):
        return []
    return [{
        "name": s,
        "source": ".mcp.json",
        "env_vars": mcp_info.get("env_vars", []),
        "copied": True,
        "warnings": ["secret_masked"] if mcp_info.get("masked_secret_count") else [],
    } for s in mcp_info.get("servers", [])]


def _infer_tool_stubs(agents: list[dict]) -> list[dict]:
    stubs: list[dict] = []
    seen: set[str] = set()
    keywords = {
        "web_search": ["web search", "search the web", "WebSearch", "검색"],
        "shell_exec": ["shell", "run command", "execute"],
        "fetch_url": ["fetch", "WebFetch", "url", "URL"],
        "file_read": ["read file", "load file"],
    }
    for agent in agents:
        body = agent.get("system_prompt", "") + " " + agent.get("description", "")
        for tool_name, kws in keywords.items():
            if any(k in body for k in kws) and tool_name not in seen:
                seen.add(tool_name)
                stubs.append({
                    "name": f"{tool_name}_stub",
                    "reason": f"Agent prompt references '{tool_name}' but no concrete tool is configured.",
                    "source_agent": agent["name"],
                })
    return stubs


def _op_mapping(op: str) -> str:
    return {
        "TeamCreate": "subagents registry",
        "TeamDelete": "phase boundary or no-op",
        "TaskCreate": "planning/delegation instructions",
        "TaskUpdate": "planning step",
        "TaskGet": "filesystem-based status query",
        "SendMessage": "main-agent-mediated result handoff",
        "run_in_background": "parallel delegation instruction",
    }.get(op, "manual mapping required")


def to_yaml(obj: Any, indent: int = 0) -> str:
    """Minimal YAML serializer (no PyYAML dependency).

    Strings are always JSON-escaped (double-quoted) to avoid block-scalar
    indentation pitfalls. Output is YAML-parsable by PyYAML safe_load.
    """
    if obj is None:
        return "null"
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, str):
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(obj, list):
        if not obj:
            return "[]"
        out: list[str] = []
        for item in obj:
            if isinstance(item, (dict, list)) and item:
                rendered = to_yaml(item, indent + 2)
                lines = rendered.split("\n")
                first = lines[0].lstrip()
                out.append(" " * indent + "- " + first)
                for line in lines[1:]:
                    out.append(line)
            else:
                out.append(" " * indent + "- " + to_yaml(item, 0))
        return "\n".join(out)
    if isinstance(obj, dict):
        if not obj:
            return "{}"
        out = []
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                out.append(" " * indent + f"{k}:")
                out.append(to_yaml(v, indent + 2))
            else:
                out.append(" " * indent + f"{k}: {to_yaml(v, 0)}")
        return "\n".join(out)
    return json.dumps(str(obj), ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Harness source extractor")
    parser.add_argument("command", choices=[
        "discover", "parse-agents", "parse-skills",
        "orchestrator-score", "pattern-detect", "claude-ops",
        "mcp-scan", "fingerprint", "build-ir",
    ])
    parser.add_argument("--root", default=".", help="Project root")
    parser.add_argument("--out", default="-", help="Output path or '-' for stdout")
    parser.add_argument("--mode", default="full", choices=["full", "audit_only"])
    parser.add_argument("--text", help="Text input for pattern-detect / claude-ops")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"error: root '{root}' is not a directory", file=sys.stderr)
        return 2

    result: Any
    if args.command == "discover":
        result = discover(root)
    elif args.command == "parse-agents":
        files = discover(root)["agents"]
        result = [parse_agent_file(root / p, root) for p in files]
    elif args.command == "parse-skills":
        files = discover(root)["skills"]
        result = [parse_skill_file(root / p, root) for p in files]
    elif args.command == "orchestrator-score":
        agents = [parse_agent_file(root / p, root) for p in discover(root)["agents"]]
        skills = [parse_skill_file(root / p, root) for p in discover(root)["skills"]]
        result = score_orchestrator_candidates(skills, agents, root)
    elif args.command == "pattern-detect":
        text = args.text or ""
        if not text:
            for sk in discover(root)["skills"]:
                text += (root / sk).read_text(encoding="utf-8", errors="replace") + "\n"
        result = detect_pattern(text)
    elif args.command == "claude-ops":
        text = args.text or ""
        if not text:
            for sk in discover(root)["skills"]:
                text += (root / sk).read_text(encoding="utf-8", errors="replace") + "\n"
        result = find_claude_ops(text)
    elif args.command == "mcp-scan":
        result = scan_mcp(root)
    elif args.command == "fingerprint":
        det = discover(root)
        all_files = det["agents"] + det["skills"] + det["claude_md"] + det["mcp"] + det["settings"]
        result = compute_fingerprint(root, all_files)
    elif args.command == "build-ir":
        ir = build_ir(root, args.mode)
        if args.out == "-":
            print(to_yaml(ir))
        else:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(to_yaml(ir), encoding="utf-8")
            print(f"IR written to {out_path}")
        return 0
    else:
        print(f"unknown command: {args.command}", file=sys.stderr)
        return 2

    if args.out == "-":
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
