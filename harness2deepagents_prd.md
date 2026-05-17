# PRD: `harness2deepagents`

**문서 상태:** Draft v0.1  
**작성일:** 2026-05-06  
**제품명:** `harness2deepagents`  
**제품 유형:** Claude Code Skill + Python code generation utility  
**소스 런타임:** RevFactory `/harness`가 생성한 Claude Code 하네스  
**타깃 런타임:** LangChain DeepAgents  
**비타깃:** Raw LangGraph emitter, 일반 LangChain `create_agent` emitter  

---

## 1. 요약

`harness2deepagents`는 RevFactory `/harness`로 생성된 Claude Code 하네스 산출물을 읽어, 실행 가능한 DeepAgents 프로젝트로 포팅하는 전용 스킬이다.

이 스킬은 다음 소스 산출물을 분석한다.

```text
.claude/agents/*.md
.claude/skills/*/SKILL.md
.claude/skills/*/references/*
.claude/skills/*/scripts/*
.claude/skills/*/assets/*
CLAUDE.md
.mcp.json
.claude/settings.json
_workspace/
```

그리고 다음 DeepAgents 산출물을 생성한다.

```text
ports/deepagents/
├── harness.deepagents.ir.yaml
├── conversion_report.md
├── app/
│   ├── agent.py
│   ├── tools.py
│   ├── mcp_tools.py
│   ├── config.py
│   ├── smoke_test.py
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── README.md
│   ├── skills/
│   │   └── <copied Harness skill folders>
│   └── .mcp.json
└── logs/
    └── validation.json
```

핵심 원칙은 단순하다.

```text
RevFactory Harness → DeepAgents only
LangGraph는 별도 출력물이 아니라 DeepAgents의 내부 런타임/escape hatch로만 취급한다.
```

---

## 2. 배경과 문제 정의

### 2.1 배경

RevFactory Harness는 Claude Code 환경에서 도메인 설명을 에이전트 팀과 스킬로 변환하는 팀 아키텍처 팩토리다. Harness가 생성하는 핵심 자산은 일반적으로 다음과 같다.

- `.claude/agents/` 아래의 전문 에이전트 정의
- `.claude/skills/` 아래의 스킬 정의
- 오케스트레이터 스킬
- 에이전트 팀 실행 모드 또는 서브에이전트 실행 모드
- Pipeline, Fan-out/Fan-in, Expert Pool, Producer-Reviewer, Supervisor, Hierarchical Delegation 같은 팀 아키텍처 패턴
- `TeamCreate`, `TaskCreate`, `SendMessage`, `Agent`, `run_in_background` 같은 Claude Code 팀 실행 지시

DeepAgents는 LangChain 생태계의 에이전트 하네스이며, planning, filesystem, subagents, skills, memory, context management를 지원한다. 따라서 Harness가 만든 “역할 분리 + 스킬 분리 + 오케스트레이션” 구조를 DeepAgents의 “main agent + subagents + skills + filesystem” 구조로 옮기는 것이 가장 손실이 적다.

### 2.2 문제

Harness 산출물은 Claude Code와 Claude Code Agent Teams 기능에 강하게 맞춰져 있다. 이 구조는 유용하지만 다음 제약이 있다.

1. Claude Code 바깥의 Python/LangChain 런타임에서 직접 실행하기 어렵다.
2. `.claude/agents/*.md`와 `.claude/skills/*`는 사람이 읽을 수 있지만, DeepAgents가 바로 실행할 수 있는 `agent.py` 형태가 아니다.
3. `TeamCreate`, `TaskCreate`, `SendMessage` 같은 팀 커뮤니케이션 지시는 DeepAgents에 1:1로 대응되지 않는다.
4. Harness가 만든 오케스트레이터 스킬은 워크플로우를 설명하지만, DeepAgents의 main agent prompt와 subagent registry로 재구성되어야 한다.
5. MCP, shell, web, repo, DB, API 등 도구 의존성은 안전하게 식별하고 adapter 또는 TODO stub로 변환해야 한다.
6. 스킬은 그대로 복사 가능한 경우가 많지만, DeepAgents skill loading 방식과 파일 크기/description 제한을 검증해야 한다.

### 2.3 해결 방향

`harness2deepagents`는 직접 코드 변환 전에 중간 표현인 `harness.deepagents.ir.yaml`을 만든다. 이 IR은 원본 Harness의 에이전트, 스킬, 오케스트레이터, 실행 모드, 의존성, 경고를 구조화한다. 이후 IR을 기준으로 DeepAgents 앱을 생성한다.

```text
Harness source files
        ↓ audit/extract
harness.deepagents.ir.yaml
        ↓ emit
DeepAgents app
        ↓ validate
conversion_report.md + smoke test
```

---

## 3. 제품 목표

### 3.1 1차 목표

1. RevFactory Harness 산출물을 안정적으로 감지한다.
2. `.claude/agents/*.md`를 DeepAgents subagents로 변환한다.
3. `.claude/skills/*`를 DeepAgents skills 디렉터리로 복사한다.
4. 오케스트레이터 스킬을 DeepAgents main agent `system_prompt`로 변환한다.
5. Claude Code 전용 팀 연산을 DeepAgents 실행 모델에 맞는 지시와 경고로 변환한다.
6. MCP/tool 의존성을 감지하고 안전한 adapter stub 또는 복사본을 생성한다.
7. 생성된 DeepAgents 앱이 최소한 import/compile/smoke-test 가능한 구조를 갖도록 한다.
8. 변환 손실, 수동 조치, 위험 요소를 `conversion_report.md`에 명확히 기록한다.

### 3.2 2차 목표

1. 반복 실행 시 이전 산출물을 덮어쓰지 않고 안전한 새 디렉터리를 생성한다.
2. 변환 품질 점수를 제공한다.
3. 원본 Harness와 생성된 DeepAgents 앱의 매핑을 사람이 검토하기 쉽게 만든다.
4. 단순한 하네스는 거의 수동 수정 없이 실행 가능하게 한다.
5. 복잡한 하네스는 TODO stub와 명확한 manual action list로 후속 구현을 쉽게 만든다.

### 3.3 비목표

이 제품은 다음을 하지 않는다.

1. Raw LangGraph 코드를 기본 생성하지 않는다.
2. LangChain `create_agent` 단일 에이전트 앱을 기본 생성하지 않는다.
3. Claude Code의 `TeamCreate`, `TaskCreate`, `SendMessage` 동작을 완벽히 재현한다고 주장하지 않는다.
4. 모든 MCP 서버를 자동으로 LangChain tool로 완전 구현하지 않는다.
5. API key, token, secret 값을 복사하거나 코드에 하드코딩하지 않는다.
6. 원본 `.claude/` 파일을 수정하지 않는다.
7. 사용자의 프로젝트 코드베이스를 임의로 재구성하지 않는다.
8. 외부 서비스에 자동 배포하지 않는다.

---

## 4. 제품 원칙

### 4.1 DeepAgents only

이 스킬은 DeepAgents 전용이다. LangGraph는 DeepAgents 내부 런타임이자 고급 사용자를 위한 escape hatch로만 언급한다.

```text
좋은 방향:
Harness orchestrator → DeepAgents main agent
Harness agents       → DeepAgents subagents
Harness skills       → DeepAgents skills
Harness workspace    → DeepAgents filesystem/artifact conventions

피해야 할 방향:
Harness workflow     → raw LangGraph graph.py
```

### 4.2 구조 보존

Harness의 가치는 프롬프트 자체가 아니라 구조에 있다. 변환은 다음 네 가지 분리를 유지해야 한다.

```text
Who       → agent / subagent
How       → skill
When      → orchestration / delegation policy
What left → artifact / filesystem / state
```

### 4.3 프롬프트 평탄화 금지

여러 agent와 skill을 하나의 거대한 system prompt로 합치지 않는다. 그렇게 하면 원본 Harness의 역할 분리, 컨텍스트 격리, 스킬 트리거가 손상된다.

### 4.4 IR 우선

항상 IR을 먼저 생성한다. IR 없이 바로 `agent.py`를 쓰지 않는다. IR은 변환의 감사 가능성, 테스트 가능성, 재실행 가능성을 보장한다.

### 4.5 안전한 변환

- 기존 산출물을 덮어쓰지 않는다.
- secret을 복사하지 않는다.
- 실행 가능한 외부 도구는 기본적으로 stub 처리한다.
- 실패하면 부분 산출물과 실패 원인을 남긴다.

### 4.6 Progressive Disclosure 보존

Harness skills의 `SKILL.md`, `references/`, `scripts/`, `assets/` 구조를 가능한 한 그대로 유지한다. 변환 과정에서 skill body를 main prompt에 무분별하게 삽입하지 않는다.

---

## 5. 사용자와 사용 시나리오

### 5.1 대상 사용자

| 사용자 | 설명 | 주요 니즈 |
|---|---|---|
| AI 에이전트 개발자 | Claude Code에서 만든 Harness를 LangChain/DeepAgents 앱으로 옮기려는 개발자 | 빠른 포팅, 코드 생성, 실행 가능성 |
| 플랫폼 엔지니어 | 여러 프로젝트의 Harness를 표준 Python agent runtime으로 통합하려는 사용자 | 일관된 출력 구조, 검증, CI 연동 |
| 연구/자동화 엔지니어 | Harness의 팀 구조를 재사용해 실험 가능한 DeepAgents 앱을 만들려는 사용자 | IR, 반복 실험, 비교 가능성 |
| Claude Code 파워유저 | Claude Code 하네스를 다른 런타임에서도 실행하고 싶은 사용자 | 쉬운 명령, README, smoke test |

### 5.2 핵심 사용자 스토리

#### US-001: 기본 포팅

사용자는 Claude Code에서 `/harness`로 만든 프로젝트를 가지고 있다. 사용자가 `/harness2deepagents`를 실행하면, 스킬은 `.claude/agents`와 `.claude/skills`를 읽고 `ports/deepagents/app/agent.py`를 생성한다.

**완료 조건**

- `harness.deepagents.ir.yaml` 생성
- `agent.py` 생성
- `skills/` 복사
- `conversion_report.md` 생성
- `python -m compileall app` 통과

#### US-002: 감사만 수행

사용자는 아직 DeepAgents 앱을 만들지 않고 변환 가능성만 보고 싶다. `/harness2deepagents audit only`와 같은 요청을 하면 IR과 report만 생성한다.

**완료 조건**

- source files 목록 생성
- agents/skills/orchestrator 감지 결과 표시
- 변환 가능성 점수 제공
- app 코드 생성 생략

#### US-003: MCP 설정 유지

사용자 프로젝트에 `.mcp.json`이 있다. 스킬은 이 파일을 감지하고 DeepAgents 앱 아래에 복사하되, secret 값은 복사하지 않는다.

**완료 조건**

- `.mcp.json` 존재 감지
- env var 참조 유지
- raw secret 의심 문자열 경고
- `mcp_tools.py`에 adapter TODO 생성

#### US-004: 복잡한 팀 패턴 변환

원본 Harness가 Supervisor 또는 Producer-Reviewer 구조다. 스킬은 이를 raw LangGraph가 아니라 DeepAgents main agent의 delegation policy와 subagent descriptions로 옮긴다.

**완료 조건**

- architecture pattern 감지
- main system prompt에 delegation policy 반영
- reviewer subagent가 별도 subagent로 유지
- retry/review 규칙이 prompt 또는 report에 반영

#### US-005: 반복 실행 안전성

사용자가 같은 프로젝트에서 스킬을 여러 번 실행한다. 기존 `ports/deepagents`가 있으면 덮어쓰지 않고 새 디렉터리를 만든다.

**완료 조건**

- 기존 산출물 보존
- 새 경로 예: `ports/deepagents_20260506_153045`
- report에 실제 출력 경로 기록

---

## 6. 범위

### 6.1 In scope

- Harness 산출물 감지
- Agent markdown parsing
- Skill metadata parsing
- Orchestrator detection
- Architecture pattern detection
- DeepAgents IR 생성
- DeepAgents `agent.py` 생성
- Skill directory copy
- MCP 설정 복사/분석
- Tool stub 생성
- README 생성
- Smoke test 생성
- Conversion report 생성
- Basic Python syntax validation
- Manual action list 생성

### 6.2 Out of scope

- Raw LangGraph graph generation
- DeepAgents 배포 자동화
- LangSmith 프로젝트 자동 생성
- MCP 서버별 완전한 tool implementation
- 원본 Harness 품질 개선
- 원본 `.claude/agents` 또는 `.claude/skills` 수정
- 멀티모델 성능 평가 자동화
- 온라인 패키지 버전 자동 pinning
- 실 API 호출을 포함한 통합 테스트

---

## 7. 입력 산출물 상세

### 7.1 필수 입력

스킬은 최소한 다음 중 하나를 발견해야 한다.

```text
.claude/agents/*.md
.claude/skills/*/SKILL.md
```

둘 다 없으면 Harness 산출물이 없다고 판단한다.

### 7.2 선택 입력

| 경로 | 용도 |
|---|---|
| `CLAUDE.md` | 프로젝트 규칙, 하네스 사용 지침, 실행 컨텍스트 추출 |
| `.mcp.json` | MCP 서버와 tool 의존성 감지 |
| `.claude/settings.json` | Claude Code 설정, MCP/env 힌트 감지 |
| `_workspace/` | Harness 산출물/중간 파일 convention 감지 |
| `README.md` | 프로젝트 이름과 도메인 요약 추출 |
| `pyproject.toml` | Python 프로젝트 여부 및 의존성 감지 |
| `package.json` | JS/TS 프로젝트 여부 및 tool stub 힌트 감지 |

### 7.3 Agent 파일 입력 예시

```markdown
---
name: security-reviewer
description: Reviews code for security vulnerabilities and risky API usage.
model: opus
---

# Security Reviewer

You review code for authentication, authorization, injection, secret exposure, and data handling risks.
Use the security-audit skill when reviewing backend code or deployment configuration.
```

### 7.4 Skill 파일 입력 예시

```markdown
---
name: security-audit
description: Use for backend security review, authentication, authorization, injection, secrets, dependency risks, and deployment hardening.
---

# Security Audit

## Workflow

1. Identify trust boundaries.
2. Review authentication and authorization.
3. Check input validation.
4. Inspect secret handling.
5. Produce a risk-ranked report.
```

---

## 8. 출력 산출물 상세

### 8.1 기본 출력 디렉터리

```text
ports/deepagents/
```

이미 존재하면 다음 규칙으로 새 디렉터리를 쓴다.

```text
ports/deepagents_YYYYMMDD_HHMMSS/
```

### 8.2 출력 트리

```text
ports/deepagents/
├── harness.deepagents.ir.yaml
├── conversion_report.md
├── app/
│   ├── agent.py
│   ├── config.py
│   ├── tools.py
│   ├── mcp_tools.py
│   ├── smoke_test.py
│   ├── requirements.txt
│   ├── pyproject.toml
│   ├── README.md
│   ├── skills/
│   │   ├── <skill-a>/
│   │   │   ├── SKILL.md
│   │   │   ├── references/
│   │   │   ├── scripts/
│   │   │   └── assets/
│   │   └── <skill-b>/
│   └── .mcp.json
└── logs/
    └── validation.json
```

### 8.3 필수 생성 파일

| 파일 | 필수 여부 | 설명 |
|---|---:|---|
| `harness.deepagents.ir.yaml` | 필수 | 변환 중간 표현 |
| `conversion_report.md` | 필수 | 변환 요약, 경고, 수동 조치 |
| `app/agent.py` | 기본 포팅 시 필수 | DeepAgents main app |
| `app/config.py` | 필수 | 모델/env/runtime 설정 |
| `app/tools.py` | 필수 | local tools 또는 TODO stub |
| `app/mcp_tools.py` | MCP 감지 시 필수 | MCP adapter/stub |
| `app/smoke_test.py` | 필수 | import/invoke smoke test |
| `app/requirements.txt` | 필수 | 최소 의존성 |
| `app/README.md` | 필수 | 실행 방법 |
| `app/skills/` | skill 존재 시 필수 | 복사된 skill folders |

---

## 9. 제품 UX

### 9.1 기본 호출

```text
/harness2deepagents
```

기본 동작:

1. 현재 프로젝트 루트에서 Harness 산출물 감지
2. IR 생성
3. DeepAgents 앱 생성
4. 검증
5. report 생성

### 9.2 명시적 호출 예시

```text
/harness2deepagents
이 프로젝트의 RevFactory Harness 산출물을 DeepAgents로 포팅해줘. MCP 설정은 유지하고, 원본 .claude 파일은 건드리지 마.
```

```text
/harness2deepagents audit only
DeepAgents 앱 생성 전에 하네스 구조와 변환 가능성만 점검해줘.
```

```text
/harness2deepagents
기존 ports/deepagents가 있으면 덮어쓰지 말고 새 폴더에 생성해줘. Claude 모델은 env로 설정되게 해줘.
```

### 9.3 사용자에게 보여줄 진행 업데이트

작업이 오래 걸릴 수 있으므로 다음 milestone마다 짧게 업데이트한다.

1. Harness source 감지 완료
2. agents/skills/orchestrator 분석 완료
3. IR 생성 완료
4. DeepAgents app 생성 완료
5. 검증 및 report 생성 완료

### 9.4 실패 UX

Harness 산출물이 없으면 다음처럼 응답한다.

```text
현재 프로젝트에서 RevFactory Harness 산출물로 볼 수 있는 .claude/agents 또는 .claude/skills를 찾지 못했습니다.
생성된 파일은 없습니다.
```

부분 실패 시에는 가능한 산출물을 남기고 `conversion_report.md`에 실패 원인을 쓴다.

---

## 10. 기능 요구사항

### FR-001: 프로젝트 루트 감지

**우선순위:** P0  
**설명:** 현재 작업 디렉터리를 기본 root로 사용하되, 사용자가 root path를 지정하면 해당 경로를 사용한다.

**수용 기준**

- root가 존재하지 않으면 명확한 오류를 반환한다.
- root 아래 `.claude/agents`, `.claude/skills`를 탐색한다.
- symlink는 기본적으로 따라가지 않는다.

---

### FR-002: Harness source discovery

**우선순위:** P0  
**설명:** Harness로 생성된 가능성이 있는 파일들을 감지한다.

**감지 대상**

```text
.claude/agents/*.md
.claude/skills/*/SKILL.md
CLAUDE.md
.mcp.json
.claude/settings.json
_workspace/
```

**수용 기준**

- 발견된 파일 목록을 IR `source.detected_files`에 기록한다.
- agents/skills가 모두 없으면 app 생성 중단.
- skills만 있고 agents가 없으면 `skills_only` 경고.
- agents만 있고 skills가 없으면 `agents_without_skills` 경고.

---

### FR-003: Agent markdown parser

**우선순위:** P0  
**설명:** `.claude/agents/*.md` 파일에서 frontmatter와 body를 추출한다.

**추출 필드**

- `id`
- `name`
- `source_file`
- `description`
- `system_prompt`
- `model_hint`
- `tools`
- `skills`
- `inputs`
- `outputs`
- `communication_notes`

**수용 기준**

- YAML frontmatter가 있으면 parsing한다.
- frontmatter가 없으면 파일명 기반 id/name을 생성한다.
- description이 없으면 첫 heading 또는 첫 paragraph에서 요약을 생성한다.
- skill 이름이 agent body에 언급되면 후보 dependency로 기록한다.
- parsing 실패 시 해당 agent를 누락하지 말고 raw body와 warning을 기록한다.

---

### FR-004: Skill parser

**우선순위:** P0  
**설명:** `.claude/skills/*/SKILL.md`를 분석한다.

**추출 필드**

- `id`
- `name`
- `source_dir`
- `description`
- `body_summary`
- `references`
- `scripts`
- `assets`
- `portable_to_deepagents`
- `warnings`

**수용 기준**

- `name`과 `description` 누락 시 warning.
- `description`이 1024자를 초과하면 warning.
- `SKILL.md`가 10MB 이상이면 DeepAgents loading risk warning.
- references/scripts/assets를 recursive하게 기록한다.
- binary assets는 복사하되 본문 분석은 하지 않는다.

---

### FR-005: Orchestrator detection

**우선순위:** P0  
**설명:** 어떤 skill 또는 문서가 오케스트레이터 역할을 하는지 감지한다.

**감지 힌트**

- 파일명 또는 skill name에 다음 포함:
  - `orchestrator`
  - `workflow`
  - `runner`
  - `coordinator`
  - `supervisor`
  - `하네스`
  - `오케스트레이터`
  - `워크플로우`
  - `조율`
- body에 여러 agent name 등장
- `TeamCreate`, `TaskCreate`, `SendMessage`, `TeamDelete`, `Agent` 등장
- phase, dependency, output, workspace convention 등장

**수용 기준**

- 후보 점수 기반으로 primary orchestrator를 선택한다.
- 후보가 여러 개면 report에 모두 기록한다.
- 후보가 없으면 synthetic orchestrator prompt를 생성하고 warning.

---

### FR-006: Architecture pattern detection

**우선순위:** P1  
**설명:** Harness 팀 아키텍처 패턴을 추정한다.

**지원 패턴**

```text
pipeline
fanout_fanin
expert_pool
producer_reviewer
supervisor
hierarchical
hybrid
unknown
```

**휴리스틱**

| 패턴 | 감지 신호 |
|---|---|
| `pipeline` | phase 1 → phase 2 → phase 3, sequential, depends_on |
| `fanout_fanin` | parallel, independent agents, merge/synthesis/aggregate |
| `expert_pool` | choose/select expert, route by domain, pool |
| `producer_reviewer` | draft/review/revise/approve, QA loop |
| `supervisor` | supervisor/coordinator assigns tasks dynamically |
| `hierarchical` | parent/child delegation, nested teams |
| `hybrid` | 여러 실행 모드 또는 phase별 다른 패턴 |

**수용 기준**

- 감지 패턴과 confidence를 IR에 기록한다.
- confidence가 낮으면 `unknown` 또는 `hybrid`로 기록하고 warning.
- 패턴 감지는 DeepAgents prompt 생성에만 사용하며 raw LangGraph 생성으로 이어지지 않는다.

---

### FR-007: Claude-only operation detection

**우선순위:** P0  
**설명:** Claude Code 전용 팀 연산을 감지한다.

**대상**

```text
TeamCreate
TeamDelete
TaskCreate
SendMessage
Agent
run_in_background
```

**수용 기준**

- 발견 위치와 문맥을 IR `claude_only_operations`에 기록한다.
- 각 operation에 DeepAgents mapping을 제공한다.
- 완전 대응이 어려운 경우 report에 manual action을 쓴다.

**기본 매핑**

| Claude operation | DeepAgents mapping |
|---|---|
| `TeamCreate` | `subagents` registry |
| `TaskCreate` | planning/todo delegation instruction |
| `SendMessage` | main agent mediated handoff/result summary |
| `TeamDelete` | no-op 또는 phase boundary note |
| `Agent` | subagent task delegation |
| `run_in_background` | parallel delegation instruction 또는 TODO |

---

### FR-008: IR generation

**우선순위:** P0  
**설명:** 모든 분석 결과를 `harness.deepagents.ir.yaml`에 저장한다.

**수용 기준**

- YAML parse 가능한 파일이어야 한다.
- source, target, harness, agents, skills, workflow, tools, artifacts, warnings를 포함한다.
- 모든 원본 파일 경로는 project root 기준 relative path로 기록한다.
- 생성 시각과 source fingerprint를 기록한다.

---

### FR-009: DeepAgents app generation

**우선순위:** P0  
**설명:** IR을 기반으로 DeepAgents 앱을 생성한다.

**수용 기준**

- `app/agent.py`가 생성된다.
- `create_deep_agent`를 사용한다.
- main `system_prompt`에 orchestrator prompt가 들어간다.
- Harness agents가 subagents로 변환된다.
- Harness skills가 `skills/`에 복사된다.
- import syntax error가 없어야 한다.

---

### FR-010: Skill directory copy

**우선순위:** P0  
**설명:** `.claude/skills/*`를 `app/skills/*`로 복사한다.

**수용 기준**

- `SKILL.md`, `references/`, `scripts/`, `assets/`가 유지된다.
- 숨김 파일은 기본 복사하되, `.git`, `.venv`, `__pycache__`는 제외한다.
- 파일명 충돌 시 deterministic rename 또는 fail-safe warning.
- 원본 파일은 수정하지 않는다.

---

### FR-011: Model configuration

**우선순위:** P0  
**설명:** 생성 앱은 모델을 env var로 설정할 수 있어야 한다.

**기본 설계**

```python
MODEL = os.getenv("DEEPAGENTS_MODEL", "anthropic:claude-sonnet-4-6")
```

**수용 기준**

- 모델명은 코드 한 곳에서만 정의한다.
- agent별 model hint가 있으면 report에 기록한다.
- secret/API key는 env var만 사용한다.
- README에 필요한 env var를 명시한다.

---

### FR-012: Tool stub generation

**우선순위:** P1  
**설명:** 원본 Harness가 shell, web, repo, DB, API 도구를 가정하면 `tools.py`에 stub를 생성한다.

**수용 기준**

- unknown tool은 TODO stub 생성.
- 위험한 tool은 기본 disabled.
- stub docstring에 원본 출처를 기록한다.
- 사용자가 쉽게 구현할 수 있도록 signature와 설명을 제공한다.

---

### FR-013: MCP handling

**우선순위:** P1  
**설명:** `.mcp.json`과 Claude settings의 MCP 설정을 감지한다.

**수용 기준**

- `.mcp.json`이 있으면 `app/.mcp.json`으로 복사한다.
- secret-like 값은 mask 또는 warning 처리한다.
- `mcp_tools.py`에 adapter TODO를 생성한다.
- README에 MCP 후속 연결 방법을 쓴다.

---

### FR-014: Conversion report

**우선순위:** P0  
**설명:** 변환 결과를 사람이 이해할 수 있게 정리한다.

**포함 항목**

- source root
- detected agents
- detected skills
- detected orchestrator
- detected architecture pattern
- execution mode
- copied skill folders
- emitted files
- Claude-only operations and mappings
- MCP/tool assumptions
- warnings
- manual actions
- run commands
- validation results
- conversion quality score

**수용 기준**

- `conversion_report.md`가 항상 생성된다.
- 실패한 경우에도 가능한 범위의 report를 남긴다.

---

### FR-015: Validation

**우선순위:** P0  
**설명:** 생성물이 최소한의 품질 검사를 통과해야 한다.

**검사 항목**

- YAML parse 가능성
- Python syntax compile
- required file existence
- skill folder copy completeness
- secret leak scan
- import check
- smoke test dry-run 가능성

**수용 기준**

- `logs/validation.json`에 결과 기록.
- 심각한 실패는 report 최상단에 표시.
- API 호출이 필요한 live invocation은 기본 수행하지 않는다.

---

### FR-016: Safe write behavior

**우선순위:** P0  
**설명:** 기존 파일을 안전하게 보호한다.

**수용 기준**

- 기존 `ports/deepagents`가 있으면 새 timestamp directory 사용.
- 원본 `.claude`는 읽기 전용으로 취급한다.
- output path는 project root 아래로 제한한다.
- path traversal 시도를 차단한다.

---

### FR-017: README generation

**우선순위:** P1  
**설명:** 생성된 DeepAgents 앱의 실행 방법을 문서화한다.

**수용 기준**

README에는 다음이 포함되어야 한다.

- 생성 목적
- 원본 Harness source 요약
- 설치 방법
- env var 설정
- 실행 명령
- smoke test 명령
- skills 구조
- MCP 후속 작업
- limitations

---

### FR-018: Audit-only mode

**우선순위:** P2  
**설명:** 앱 생성 없이 IR/report만 만든다.

**수용 기준**

- 사용자 요청에 `audit only`, `분석만`, `점검만` 등이 포함되면 app 생성 생략.
- report에 `mode: audit_only` 표시.

---

### FR-019: Incremental rerun support

**우선순위:** P2  
**설명:** 같은 Harness source에서 반복 실행할 때 diff를 제공한다.

**수용 기준**

- 이전 IR이 있으면 source fingerprint를 비교한다.
- agents/skills 추가/삭제/변경을 report에 기록한다.
- v0.1에서는 optional로 둔다.

---

## 11. 비기능 요구사항

### NFR-001: 신뢰성

- 입력 파일 일부가 깨져도 전체 변환이 중단되지 않아야 한다.
- 가능한 산출물을 남기고, 실패 파일을 warnings에 기록한다.

### NFR-002: 감사 가능성

- 변환 결정의 근거를 IR과 report에 기록한다.
- 자동 추론한 내용은 `confidence`와 함께 표시한다.

### NFR-003: 재현 가능성

- 동일 입력과 동일 버전의 스킬은 동일한 IR과 유사한 app 구조를 생성해야 한다.
- timestamp는 output directory와 metadata에만 영향을 준다.

### NFR-004: 보안

- secret value를 코드나 report에 노출하지 않는다.
- `.env`, private key, token pattern은 복사하지 않거나 mask한다.
- 실행 가능한 scripts는 복사하되 자동 실행하지 않는다.

### NFR-005: 유지보수성

- 변환 로직은 `extract`, `emit`, `validate`로 분리한다.
- mapping rules는 reference markdown에 문서화한다.
- code templates는 `assets/` 아래에 둔다.

### NFR-006: 사용자 수정 용이성

- 생성 코드는 사람이 읽기 쉬워야 한다.
- TODO stub는 위치와 이유를 명확히 표시한다.
- prompt는 multiline string으로 유지하되 너무 큰 경우 별도 파일로 분리한다.

### NFR-007: DeepAgents API 변화 대응

- `create_deep_agent` 사용부를 `agent.py` 한 곳에 집중시킨다.
- 버전 pinning은 보수적으로 하되, README에 업데이트 지침을 둔다.
- import 실패 시 report에 설치/버전 문제를 명확히 쓴다.

---

## 12. IR 스키마

### 12.1 파일명

```text
harness.deepagents.ir.yaml
```

### 12.2 스키마

```yaml
schema_version: "harness2deepagents/v1"

metadata:
  generated_at: "2026-05-06T00:00:00+09:00"
  generator: "harness2deepagents"
  generator_version: "0.1.0"
  mode: "full|audit_only"

source:
  root: "."
  source_fingerprint: "sha256:<hash>"
  assumed_generator: "revfactory/harness"
  claude_base: true
  detected_files:
    claude_md: "CLAUDE.md"
    agents:
      - ".claude/agents/analyst.md"
    skills:
      - ".claude/skills/research/SKILL.md"
    orchestrators:
      - ".claude/skills/research-orchestrator/SKILL.md"
    mcp:
      - ".mcp.json"
    settings:
      - ".claude/settings.json"
    workspace:
      - "_workspace/"

harness:
  name: "converted_harness"
  summary: "One paragraph summary of the detected Harness."
  architecture_pattern:
    value: "supervisor"
    confidence: 0.82
    evidence:
      - "orchestrator mentions supervisor"
      - "multiple agents assigned dynamically"
  execution_mode:
    value: "agent_team|subagents|hybrid|unknown"
    confidence: 0.75
  workspace_dir: "_workspace"
  artifact_conventions:
    - "phase_agent_artifact.md"

target:
  runtime: "deepagents"
  emit_raw_langgraph: false
  output_dir: "ports/deepagents/app"
  model:
    env_var: "DEEPAGENTS_MODEL"
    default: "anthropic:claude-sonnet-4-6"
  package_manager: "uv|pip|unknown"

agents:
  - id: "analyst"
    name: "analyst"
    source_file: ".claude/agents/analyst.md"
    description: "Analyzes requirements and produces structured findings."
    system_prompt: "..."
    model_hint: "opus"
    deepagents:
      subagent_name: "analyst"
      description: "Use for requirements analysis and structured findings."
      skills:
        - "research"
      tools:
        - "web_search_stub"
    skills_detected:
      explicit:
        - "research"
      inferred:
        - "analysis-method"
    tools_detected:
      explicit: []
      inferred:
        - "web"
    inputs:
      - "user_request"
    outputs:
      - "analysis_report"
    communication:
      receives_from: []
      sends_to:
        - "reviewer"
      notes: "Sends analysis report to reviewer."
    warnings: []

skills:
  - id: "research"
    name: "research"
    source_dir: ".claude/skills/research"
    target_dir: "app/skills/research"
    description: "Use for research tasks..."
    description_length: 120
    skill_md_size_bytes: 4500
    portable_to_deepagents: true
    references:
      - "references/method.md"
    scripts:
      - "scripts/extract.py"
    assets: []
    used_by_agents:
      - "analyst"
    warnings: []

orchestrator:
  found: true
  source_file: ".claude/skills/research-orchestrator/SKILL.md"
  name: "research-orchestrator"
  description: "Coordinates the research team..."
  prompt: "..."
  detected_operations:
    - operation: "TeamCreate"
      count: 1
      mapping: "subagents registry"
    - operation: "TaskCreate"
      count: 3
      mapping: "planning/delegation instructions"
    - operation: "SendMessage"
      count: 2
      mapping: "main-agent-mediated result handoff"
  warnings: []

workflow:
  phases:
    - id: "phase_1"
      name: "Research"
      agents:
        - "analyst"
      depends_on: []
      mode: "subagent"
      expected_outputs:
        - "research_notes.md"
  delegation_policy:
    summary: "Main agent plans first, delegates to specialized subagents, then synthesizes."
    rules:
      - "Use analyst for initial research."
      - "Use reviewer before final answer."
  review_policy:
    enabled: true
    reviewer_agents:
      - "reviewer"
    retry_limit: 1

tools:
  mcp_servers:
    - name: "filesystem"
      source: ".mcp.json"
      env_vars:
        - "FILESYSTEM_ROOT"
      copied: true
      warnings: []
  langchain_tools: []
  stubs_required:
    - name: "web_search_stub"
      reason: "Agent prompt references web research but no concrete tool is configured."
  environment_variables:
    - name: "ANTHROPIC_API_KEY"
      required: true
      source: "model provider"
    - name: "DEEPAGENTS_MODEL"
      required: false
      default: "anthropic:claude-sonnet-4-6"

artifacts:
  workspace_dir: "_workspace"
  output_files: []
  generated_files:
    - "app/agent.py"
    - "app/config.py"
    - "app/README.md"

quality:
  conversion_score: 0.78
  blockers: []
  warnings:
    - "SendMessage semantics are approximated through main-agent-mediated handoff."
  manual_actions:
    - "Implement web_search_stub in app/tools.py."

validation:
  yaml_parse: "pass"
  python_compile: "pass|fail|not_run"
  skill_copy: "pass|fail"
  secret_scan: "pass|warn|fail"
  smoke_test: "pass|fail|not_run"
```

### 12.3 IR 설계 원칙

1. IR은 사람이 읽을 수 있어야 한다.
2. IR은 codegen의 단일 source of truth다.
3. 원본 prompt는 가능하면 보존한다.
4. 자동 요약은 원본 prompt를 대체하지 않는다.
5. 모든 warning은 원인과 후속 조치를 포함한다.

---

## 13. 변환 알고리즘

### 13.1 전체 흐름

```text
1. Resolve root
2. Discover source files
3. Parse agents
4. Parse skills
5. Detect orchestrator
6. Detect architecture pattern
7. Detect Claude-only operations
8. Detect tools/MCP/secrets
9. Build IR
10. Emit DeepAgents app
11. Copy skills
12. Generate README/report
13. Validate
```

### 13.2 Agent parsing 절차

1. `.claude/agents/*.md` glob.
2. 파일명에서 기본 id 생성.
3. YAML frontmatter 추출.
4. `name`, `description`, `model`, `tools` 등 known fields parsing.
5. Markdown body 전체를 `system_prompt`로 보존.
6. body에서 skill 이름 mention search.
7. body에서 output artifact convention 추출.
8. body에서 다른 agent name mention search.
9. warnings 생성.

### 13.3 Skill parsing 절차

1. `.claude/skills/*/SKILL.md` glob.
2. skill directory name을 기본 id로 사용.
3. frontmatter parsing.
4. `name`, `description` 필수성 검사.
5. `description` length 검사.
6. file size 검사.
7. references/scripts/assets inventory 생성.
8. body에서 Claude-specific tool mention 감지.
9. portability 판단.

### 13.4 Orchestrator scoring

각 skill/document에 점수를 부여한다.

| 신호 | 점수 |
|---|---:|
| name에 `orchestrator` 포함 | +5 |
| name에 `workflow`, `runner`, `coordinator`, `supervisor` 포함 | +4 |
| 한국어 `오케스트레이터`, `워크플로우`, `조율` 포함 | +4 |
| `TeamCreate` 포함 | +5 |
| `TaskCreate` 포함 | +4 |
| `SendMessage` 포함 | +4 |
| 2개 이상 agent name mention | +3 |
| phase/dependency/output section 포함 | +3 |
| `_workspace` mention | +2 |
| description에 후속 작업 trigger 포함 | +1 |

최고 점수 파일을 primary orchestrator로 선택한다. 점수가 threshold 미만이면 synthetic orchestrator를 생성한다.

### 13.5 Architecture pattern scoring

각 패턴에 점수를 부여하고 가장 높은 값을 선택한다.

```python
pattern_scores = {
    "pipeline": 0,
    "fanout_fanin": 0,
    "expert_pool": 0,
    "producer_reviewer": 0,
    "supervisor": 0,
    "hierarchical": 0,
}
```

예시 규칙:

- `phase 1`, `phase 2`, `depends_on`, `sequential` → pipeline +2
- `parallel`, `fan-out`, `independent`, `merge`, `aggregate` → fanout_fanin +3
- `expert`, `pool`, `route`, `select` → expert_pool +2
- `review`, `revise`, `approve`, `QA`, `retry` → producer_reviewer +3
- `supervisor`, `coordinator`, `assign` → supervisor +3
- `hierarchical`, `parent`, `child`, `delegate recursively` → hierarchical +3

### 13.6 Skill-to-agent matching

우선순위:

1. Agent frontmatter에 명시된 skills
2. Agent body에 skill name 직접 mention
3. Agent body에 skill description keyword overlap
4. Orchestrator가 명시한 agent-skill mapping
5. Fallback: main agent에 all skills directory 등록, subagent에는 skill 없음 또는 low-confidence inferred mapping

### 13.7 DeepAgents prompt synthesis

Main system prompt는 다음 블록으로 구성한다.

```text
# Converted Harness Orchestrator
<원본 orchestrator prompt 또는 synthetic prompt>

# Conversion Notes
- This app was converted from RevFactory Harness output.
- Use DeepAgents subagents instead of Claude Code Agent Teams.
- Treat TeamCreate as the available subagent registry.
- Treat TaskCreate as planning and delegation.
- Treat SendMessage as result handoff mediated by the main agent.

# Delegation Policy
<IR workflow.delegation_policy>

# Artifact Policy
<workspace/artifact conventions>

# Safety and Validation Policy
<tool warnings, MCP warnings, TODO stubs>
```

Subagent prompt는 원본 agent body를 보존하되, DeepAgents 실행 문맥을 추가한다.

```text
# Converted Harness Agent
<원본 agent prompt>

# DeepAgents Runtime Notes
You are running as a DeepAgents subagent.
Return concise, structured results to the main agent.
Write large intermediate outputs to the filesystem when appropriate.
Do not assume direct peer-to-peer SendMessage; communicate through task results.
```

---

## 14. DeepAgents 출력 설계

### 14.1 `agent.py` 생성 원칙

- 가능한 최소 실행 앱을 생성한다.
- `create_deep_agent` 호출부를 명확히 한다.
- subagents 배열을 사람이 수정하기 쉽게 둔다.
- prompt가 너무 길면 `prompts/` 디렉터리로 분리할 수 있게 설계한다.
- raw LangGraph import는 사용하지 않는다.

### 14.2 `agent.py` 기본 템플릿

```python
"""DeepAgents app generated by harness2deepagents.

This file was generated from RevFactory Harness output.
Do not edit generated sections unless you understand the mapping in conversion_report.md.
"""

from __future__ import annotations

from deepagents import create_deep_agent

from config import SETTINGS
from tools import TOOLS


MAIN_SYSTEM_PROMPT = r'''<GENERATED_ORCHESTRATOR_PROMPT>'''

SUBAGENTS = [
    {
        "name": "<agent_name>",
        "description": "<routing_description>",
        "system_prompt": r'''<agent_system_prompt>''',
        "skills": ["/skills/<skill_name>/"],
    },
]


agent = create_deep_agent(
    model=SETTINGS.model,
    tools=TOOLS,
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=SUBAGENTS,
    skills=["/skills/"],
    name=SETTINGS.app_name,
)


def invoke(user_message: str):
    """Invoke the converted DeepAgents app."""
    return agent.invoke({
        "messages": [
            {"role": "user", "content": user_message}
        ]
    })


if __name__ == "__main__":
    result = invoke("Run the converted Harness workflow on this request: summarize the available capabilities.")
    print(result["messages"][-1].content)
```

### 14.3 `config.py` 템플릿

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("DEEPAGENTS_APP_NAME", "converted_harness")
    model: str = os.getenv("DEEPAGENTS_MODEL", "anthropic:claude-sonnet-4-6")
    enable_mcp: bool = os.getenv("DEEPAGENTS_ENABLE_MCP", "false").lower() == "true"
    dry_run: bool = os.getenv("DEEPAGENTS_DRY_RUN", "false").lower() == "true"


SETTINGS = Settings()
```

### 14.4 `tools.py` 템플릿

```python
"""Tool stubs generated by harness2deepagents.

Implement these functions when the original Harness expected external tools.
"""

from __future__ import annotations


def web_search_stub(query: str) -> str:
    """TODO: Implement web search.

    Source: inferred from Harness agent or skill instructions.
    Safety: do not call external APIs until credentials and policy are configured.
    """
    raise NotImplementedError("web_search_stub is not implemented yet.")


TOOLS = [
    # Add implemented tools here.
    # web_search_stub,
]
```

### 14.5 `mcp_tools.py` 템플릿

```python
"""MCP adapter placeholder generated by harness2deepagents.

This module is intentionally conservative. It does not automatically start MCP servers
or expose tools until the developer reviews .mcp.json and environment variables.
"""

from __future__ import annotations


def load_mcp_tools():
    """TODO: Load MCP tools through the appropriate LangChain MCP adapter.

    Review app/.mcp.json before enabling this function.
    """
    return []
```

### 14.6 `smoke_test.py` 템플릿

```python
from __future__ import annotations

import importlib


def test_import_agent():
    module = importlib.import_module("agent")
    assert hasattr(module, "agent")


if __name__ == "__main__":
    test_import_agent()
    print("Smoke test passed: agent import succeeded.")
```

### 14.7 `requirements.txt`

```text
deepagents
langchain
langchain-anthropic
python-dotenv
pyyaml
```

### 14.8 `pyproject.toml`

```toml
[project]
name = "converted-harness-deepagents"
version = "0.1.0"
description = "DeepAgents app generated from RevFactory Harness output"
requires-python = ">=3.11"
dependencies = [
  "deepagents",
  "langchain",
  "langchain-anthropic",
  "python-dotenv",
  "pyyaml",
]

[tool.harness2deepagents]
generated = true
source = "revfactory/harness"
target = "deepagents"
```

---

## 15. Skill 자체 구현 구조

### 15.1 Claude Code skill directory

```text
.claude/skills/harness2deepagents/
├── SKILL.md
├── references/
│   ├── ir-schema.md
│   ├── mapping-rules.md
│   ├── deepagents-emitter.md
│   ├── mcp-handling.md
│   ├── validation-checklist.md
│   └── edge-cases.md
├── scripts/
│   ├── extract_harness.py
│   ├── emit_deepagents.py
│   ├── validate_port.py
│   └── secret_scan.py
└── assets/
    ├── agent.py.j2
    ├── config.py.j2
    ├── tools.py.j2
    ├── mcp_tools.py.j2
    ├── smoke_test.py.j2
    ├── README.md.j2
    ├── requirements.txt.j2
    └── pyproject.toml.j2
```

### 15.2 `SKILL.md` frontmatter

```markdown
---
name: harness2deepagents
description: Convert RevFactory /harness-generated Claude Code agent teams and skills into a runnable DeepAgents app. Use when the user asks to port, migrate, convert, translate, export, or transform Harness, .claude/agents, .claude/skills, orchestrator skills, Claude Code agent teams, or RevFactory Harness output to DeepAgents, LangChain DeepAgents, or a Python agent harness. Does not emit raw LangGraph by default.
compatibility: Claude Code skill. Requires project read/write access and Python 3.11+ for validation scripts. Designed for RevFactory Harness output.
metadata:
  version: "0.1.0"
  source: "revfactory/harness"
  target: "deepagents"
  aliases:
    - harness-to-deepagents
    - h2d
---
```

### 15.3 `SKILL.md` 본문 요구사항

`SKILL.md` 본문은 500줄 이내를 목표로 한다. 상세 스키마와 edge case는 `references/`로 분리한다.

본문에는 다음만 둔다.

1. 스킬 목적
2. 입력 탐색 경로
3. 출력 계약
4. 7단계 변환 절차
5. DeepAgents-only 원칙
6. 안전 규칙
7. 검증 규칙
8. 언제 reference를 읽을지에 대한 포인터

---

## 16. Mapping rules

### 16.1 핵심 매핑

| Harness | DeepAgents |
|---|---|
| `.claude/agents/*.md` | `SUBAGENTS` entries |
| agent name | subagent `name` |
| agent description | subagent `description` |
| agent body | subagent `system_prompt` |
| `.claude/skills/*` | `app/skills/*` |
| orchestrator skill | main `system_prompt` |
| `CLAUDE.md` | README/runtime notes |
| `_workspace/` | filesystem/artifact policy |
| `.mcp.json` | copied config + `mcp_tools.py` TODO |

### 16.2 Claude team operation mapping

| Claude Code team concept | DeepAgents port behavior | Lossiness |
|---|---|---:|
| `TeamCreate` | Define available `SUBAGENTS` | Low |
| `TaskCreate` | Main agent planning/delegation instructions | Medium |
| `SendMessage` | Result passing through main agent/task result | Medium |
| Peer-to-peer team chat | Not directly preserved | High |
| `TeamDelete` | Phase boundary/no-op | Low |
| `Agent(..., run_in_background=true)` | Async/parallel delegation instruction or TODO | Medium |
| Phase dependency | Prompt-level workflow policy | Medium |

### 16.3 Architecture pattern mapping

| Harness pattern | DeepAgents prompt strategy |
|---|---|
| Pipeline | Main agent follows ordered phase checklist |
| Fan-out/Fan-in | Main agent delegates independent subtasks then synthesizes |
| Expert Pool | Main agent selects subagent by description and task type |
| Producer-Reviewer | Main agent delegates draft then review; optionally revise once |
| Supervisor | Main agent acts as supervisor and assigns work dynamically |
| Hierarchical Delegation | Main agent delegates to broad subagents; subagents may summarize needs back |
| Hybrid | Main agent uses phase-specific policy blocks |

### 16.4 Skill assignment rules

1. Explicit mapping beats inferred mapping.
2. A skill mentioned in agent frontmatter is attached to that subagent.
3. A skill mentioned by exact name in agent body is attached with high confidence.
4. A skill whose description overlaps strongly with agent role is attached with medium confidence.
5. Shared skills can be registered at main agent level.
6. Unknown/low-confidence skills are copied but not forced into every subagent prompt.

---

## 17. MCP와 외부 도구 처리

### 17.1 MCP detection

스킬은 다음 파일에서 MCP 힌트를 찾는다.

```text
.mcp.json
.claude/settings.json
CLAUDE.md
.claude/skills/*/SKILL.md
.claude/agents/*.md
```

### 17.2 MCP output behavior

| 상황 | 동작 |
|---|---|
| `.mcp.json` 존재 | `app/.mcp.json`으로 복사 |
| secret-like literal 존재 | mask 또는 warning |
| env var 참조 존재 | README에 required env var 기록 |
| MCP server command 존재 | 자동 실행하지 않음 |
| tool name 추론 가능 | `mcp_tools.py`에 TODO adapter 생성 |

### 17.3 Secret scan patterns

다음 pattern은 warning 또는 block 대상이다.

```text
sk-
AKIA
-----BEGIN PRIVATE KEY-----
ghp_
gho_
ghu_
ghs_
xoxb-
api_key = "..."
token = "..."
password = "..."
```

### 17.4 Tool stub policy

외부 tool은 자동으로 실제 구현하지 않는다. 대신 다음 정보를 포함한 stub를 생성한다.

- tool name
- inferred purpose
- source evidence
- expected input/output
- security note
- TODO implementation placeholder

---

## 18. 검증 설계

### 18.1 Validation stages

```text
Stage 1: Source validation
Stage 2: IR validation
Stage 3: Output file validation
Stage 4: Python syntax validation
Stage 5: Skill copy validation
Stage 6: Secret scan
Stage 7: Smoke import test
```

### 18.2 `validate_port.py` 기능

입력:

```bash
python scripts/validate_port.py --output ports/deepagents
```

출력:

```text
ports/deepagents/logs/validation.json
ports/deepagents/conversion_report.md 업데이트
```

검사 항목:

- required files exist
- IR YAML parse
- generated Python compile
- no raw secret leaks
- skill folder count matches expected
- `agent.py` imports `create_deep_agent`
- no raw LangGraph emitter files generated

### 18.3 Validation JSON 예시

```json
{
  "status": "pass_with_warnings",
  "checks": [
    {"name": "ir_yaml_parse", "status": "pass"},
    {"name": "required_files", "status": "pass"},
    {"name": "python_compile", "status": "pass"},
    {"name": "skill_copy", "status": "pass"},
    {"name": "secret_scan", "status": "warn", "details": ["Potential token pattern in .mcp.json was masked."]},
    {"name": "raw_langgraph_emitter", "status": "pass"}
  ]
}
```

---

## 19. Conversion report 상세

### 19.1 Report structure

```markdown
# harness2deepagents Conversion Report

## Summary

## Source Discovery

## Detected Harness Architecture

## Agents

## Skills

## Orchestrator

## DeepAgents Mapping

## Claude-only Operations

## Tools and MCP

## Generated Files

## Validation Results

## Warnings

## Manual Actions

## Run Commands

## Limitations
```

### 19.2 품질 점수

품질 점수는 0.0~1.0으로 산출한다.

가중치:

| 항목 | 가중치 |
|---|---:|
| agents parsed | 0.20 |
| skills parsed/copied | 0.20 |
| orchestrator detected | 0.15 |
| pattern detected | 0.10 |
| Claude operations mapped | 0.10 |
| tools/MCP handled | 0.10 |
| validation pass | 0.15 |

점수 해석:

| 점수 | 의미 |
|---:|---|
| 0.90~1.00 | 거의 바로 실행 가능 |
| 0.75~0.89 | 소규모 수동 수정 필요 |
| 0.50~0.74 | 구조는 보존됐지만 tool/prompt 수정 필요 |
| 0.00~0.49 | 감사용 산출물로만 신뢰 |

---

## 20. Edge cases

### EC-001: agents 없음, skills 있음

동작:

- IR 생성
- app 생성은 가능하나 subagents 없음
- synthetic main agent 생성
- warning: `skills_only_harness`

### EC-002: skills 없음, agents 있음

동작:

- subagents 생성
- skills directory 없음
- warning: `agents_without_skills`

### EC-003: orchestrator 없음

동작:

- synthetic orchestrator prompt 생성
- agents와 skills를 기반으로 delegation policy 생성
- warning: `orchestrator_not_found`

### EC-004: duplicate agent names

동작:

- 파일 경로 기반으로 deterministic id 생성
- subagent name은 slug + numeric suffix
- report에 collision 기록

### EC-005: invalid YAML frontmatter

동작:

- raw body fallback
- frontmatter parse warning
- 파일은 누락하지 않음

### EC-006: huge SKILL.md

동작:

- size warning
- copy는 수행
- DeepAgents loading risk report

### EC-007: secret in config

동작:

- output에는 mask
- report에는 secret type만 기록
- manual action: env var로 이전

### EC-008: binary assets

동작:

- copy
- analysis skip
- report에 size/type 기록

### EC-009: existing output directory

동작:

- 새 timestamp directory 사용
- old output untouched

### EC-010: Claude-only peer messaging heavy workflow

동작:

- DeepAgents main-agent-mediated handoff로 변환
- lossiness warning high
- manual action: 필요 시 custom shared filesystem protocol 구현

---

## 21. 테스트 계획

### 21.1 Unit tests

| Test | 설명 |
|---|---|
| `test_parse_agent_frontmatter` | agent frontmatter/body parsing |
| `test_parse_skill_frontmatter` | skill metadata parsing |
| `test_orchestrator_scoring` | orchestrator 후보 선택 |
| `test_pattern_detection_pipeline` | pipeline 감지 |
| `test_pattern_detection_supervisor` | supervisor 감지 |
| `test_claude_operation_detection` | TeamCreate/SendMessage 감지 |
| `test_ir_schema_minimal` | 최소 IR 생성 |
| `test_secret_scan` | secret masking/warning |
| `test_safe_output_dir` | 기존 output 보호 |

### 21.2 Golden fixture tests

Fixture 디렉터리:

```text
tests/fixtures/
├── simple_pipeline/
├── supervisor_with_skills/
├── producer_reviewer/
├── mcp_enabled/
├── no_orchestrator/
├── invalid_frontmatter/
└── duplicate_names/
```

각 fixture는 다음을 가진다.

```text
input/
  .claude/agents/...
  .claude/skills/...
expected/
  harness.deepagents.ir.yaml
  conversion_report.snapshot.md
```

### 21.3 Integration tests

- fixture를 변환한다.
- 생성된 `agent.py`를 compile한다.
- `smoke_test.py`를 실행한다.
- skills copy count를 비교한다.

### 21.4 Manual QA checklist

- 생성된 main prompt가 원본 orchestrator 의미를 유지하는가?
- agent별 역할이 subagent로 유지되는가?
- skill이 프롬프트에 무분별하게 합쳐지지 않았는가?
- Claude-only operation 경고가 충분히 명확한가?
- README만 보고 실행할 수 있는가?
- secret이 노출되지 않았는가?
- raw LangGraph emitter가 생성되지 않았는가?

---

## 22. 구현 마일스톤

### v0.1: Audit + IR

목표:

- Harness source discovery
- agent/skill parsing
- orchestrator detection
- pattern detection
- IR 생성
- report 생성

산출물:

```text
scripts/extract_harness.py
references/ir-schema.md
harness.deepagents.ir.yaml
conversion_report.md
```

완료 기준:

- 3개 fixture에서 IR 생성 성공
- invalid frontmatter에서도 전체 실패하지 않음
- report에 warnings/manual actions 포함

### v0.2: DeepAgents emitter

목표:

- `agent.py` 생성
- `config.py`, `tools.py`, `smoke_test.py` 생성
- skills 복사
- README/requirements/pyproject 생성

완료 기준:

- `python -m compileall app` 통과
- `smoke_test.py` import 통과
- skills copy completeness 검증

### v0.3: MCP/tool handling

목표:

- `.mcp.json` 감지/복사
- secret scan
- `mcp_tools.py` 생성
- external tool stubs 생성

완료 기준:

- secret fixture에서 raw secret 미노출
- MCP fixture에서 adapter TODO 생성

### v0.4: Quality scoring + rerun safety

목표:

- conversion score 계산
- output directory collision handling
- validation JSON 생성
- diff 기반 rerun report 초안

완료 기준:

- 기존 output을 덮어쓰지 않음
- validation report 안정 생성

### v1.0: Production-ready skill

목표:

- 문서 정리
- fixtures 확장
- CI 테스트
- known limitations 명확화
- 사용자 피드백 반영

완료 기준:

- 대표 Harness 패턴 6종 fixture 통과
- PRD의 P0/P1 요구사항 충족
- 실제 Harness 프로젝트 2개 이상에서 manual QA 통과

---

## 23. 개발 작업 분해

### Epic A: Skill shell

- A1. `.claude/skills/harness2deepagents/SKILL.md` 작성
- A2. reference 문서 scaffold 작성
- A3. assets template 작성
- A4. scripts entrypoint 설계

### Epic B: Extractor

- B1. file discovery
- B2. markdown frontmatter parser
- B3. agent parser
- B4. skill parser
- B5. orchestrator scorer
- B6. pattern detector
- B7. Claude operation detector
- B8. MCP/settings detector
- B9. IR writer

### Epic C: Emitter

- C1. output dir resolver
- C2. skill copy function
- C3. prompt synthesis
- C4. subagent config generator
- C5. `agent.py` renderer
- C6. `config.py` renderer
- C7. `tools.py` renderer
- C8. `mcp_tools.py` renderer
- C9. README/requirements/pyproject renderer

### Epic D: Validation

- D1. IR YAML validator
- D2. generated files checker
- D3. Python compile checker
- D4. skill copy checker
- D5. secret scanner
- D6. validation JSON writer
- D7. report writer

### Epic E: Tests and fixtures

- E1. simple pipeline fixture
- E2. supervisor fixture
- E3. producer-reviewer fixture
- E4. MCP fixture
- E5. invalid frontmatter fixture
- E6. duplicate name fixture
- E7. golden snapshot tests

---

## 24. 수용 기준 요약

v1.0 기준으로 다음을 만족해야 한다.

1. `.claude/agents`와 `.claude/skills`를 가진 프로젝트에서 `/harness2deepagents` 실행 시 `ports/deepagents`가 생성된다.
2. IR은 YAML parser로 읽을 수 있다.
3. 모든 agent 파일이 IR에 반영된다.
4. 모든 skill directory가 `app/skills`에 복사된다.
5. 오케스트레이터가 있으면 main prompt에 반영된다.
6. 오케스트레이터가 없어도 synthetic prompt가 생성된다.
7. DeepAgents `create_deep_agent` 기반 `agent.py`가 생성된다.
8. raw LangGraph emitter는 생성되지 않는다.
9. Claude-only operation은 report에 mapping/warning으로 기록된다.
10. `.mcp.json`은 안전하게 복사 또는 경고 처리된다.
11. secret-like literal은 report/code에 노출되지 않는다.
12. `python -m compileall app`이 통과한다.
13. `smoke_test.py`가 import 수준에서 통과한다.
14. README에는 실행 방법과 env var가 포함된다.
15. conversion report에는 manual actions가 포함된다.
16. 기존 output은 덮어쓰지 않는다.

---

## 25. 예시: 간단한 변환 결과

### 25.1 원본 Harness 구조

```text
.claude/
├── agents/
│   ├── researcher.md
│   ├── writer.md
│   └── reviewer.md
└── skills/
    ├── research-method/
    │   └── SKILL.md
    ├── report-writing/
    │   └── SKILL.md
    └── research-orchestrator/
        └── SKILL.md
```

### 25.2 생성된 DeepAgents 구조

```text
ports/deepagents/app/
├── agent.py
├── config.py
├── tools.py
├── smoke_test.py
├── skills/
│   ├── research-method/
│   ├── report-writing/
│   └── research-orchestrator/
└── README.md
```

### 25.3 생성된 subagents 예시

```python
SUBAGENTS = [
    {
        "name": "researcher",
        "description": "Use for topic investigation, source gathering, and evidence mapping.",
        "system_prompt": r'''...original researcher prompt...''',
        "skills": ["/skills/research-method/"],
    },
    {
        "name": "writer",
        "description": "Use for turning research findings into structured reports.",
        "system_prompt": r'''...original writer prompt...''',
        "skills": ["/skills/report-writing/"],
    },
    {
        "name": "reviewer",
        "description": "Use for checking factual consistency, gaps, and final quality.",
        "system_prompt": r'''...original reviewer prompt...''',
        "skills": [],
    },
]
```

---

## 26. 위험과 대응

### Risk-001: DeepAgents API 변경

**위험:** `create_deep_agent` signature 또는 skill/subagent 설정 방식이 바뀔 수 있다.  
**대응:** API 의존 코드를 `agent.py` template에 집중시키고, PRD/README에 버전 확인 지침을 둔다.

### Risk-002: TeamCreate/SendMessage 의미 손실

**위험:** Claude Code Agent Teams의 peer-to-peer 커뮤니케이션은 DeepAgents에서 완벽히 동일하지 않을 수 있다.  
**대응:** main-agent-mediated delegation으로 변환하고, high-lossiness warning을 제공한다.

### Risk-003: Skill trigger 차이

**위험:** Claude Code Skill과 DeepAgents Skill의 loading/trigger behavior가 다를 수 있다.  
**대응:** skill description을 보존하고, main prompt에 skill usage policy를 추가한다.

### Risk-004: MCP 연결 불완전

**위험:** MCP 서버 설정은 복사되어도 LangChain tool로 바로 사용되지 않을 수 있다.  
**대응:** `mcp_tools.py` TODO와 README manual action 제공.

### Risk-005: Secret leakage

**위험:** `.mcp.json` 또는 settings에 secret이 포함될 수 있다.  
**대응:** secret scan, masking, env var 요구.

### Risk-006: 너무 큰 prompt

**위험:** agent/system prompt가 매우 크면 유지보수성과 context 효율이 나빠진다.  
**대응:** v0.2에서는 보존 우선, v0.3 이후 prompt files 분리 및 compression 지원.

---

## 27. 운영 지표

### 27.1 개발 품질 지표

- Fixture pass rate
- IR parse success rate
- Python compile success rate
- Secret scan false negative count
- Manual action count 평균
- Conversion score 평균

### 27.2 사용자 가치 지표

- 변환 후 첫 실행까지 걸리는 수동 수정 시간
- 생성된 app을 그대로 유지한 비율
- 사용자 재실행 횟수
- report의 manual action 완료율
- 실제 DeepAgents invocation 성공률

---

## 28. 향후 확장

### 28.1 Optional: prompt externalization

큰 prompt를 `prompts/main.md`, `prompts/subagents/*.md`로 분리한다.

### 28.2 Optional: real MCP adapter

LangChain MCP adapter를 사용해 `.mcp.json` 기반 tool loading을 실제 구현한다.

### 28.3 Optional: permission policy

DeepAgents filesystem permission rules를 생성한다.

### 28.4 Optional: LangSmith tracing

README와 config에 LangSmith tracing env var를 추가한다.

### 28.5 Optional: evaluation harness

원본 Harness test prompt와 DeepAgents app 결과를 비교하는 evaluation script를 만든다.

### 28.6 Not planned: raw LangGraph emitter

이 제품의 이름과 범위는 `harness2deepagents`다. Raw LangGraph emitter는 별도 제품으로 분리해야 한다.

---

## 29. Definition of Done

`harness2deepagents` v1.0은 다음을 만족할 때 완료된다.

- P0/P1 기능 요구사항 구현 완료
- 대표 fixture 6종 이상 통과
- 실제 RevFactory Harness 프로젝트에서 end-to-end 변환 성공
- 생성된 DeepAgents 앱이 import/compile/smoke test 통과
- skill copy completeness 100%
- raw secret leakage 0건
- raw LangGraph output 0건
- README와 conversion report가 사람이 이해할 수 있음
- known limitations 명시
- 반복 실행 시 기존 산출물 보존

---

## 30. 부록 A: 용어

| 용어 | 의미 |
|---|---|
| Harness | RevFactory `/harness`가 생성한 Claude Code용 팀/스킬 구조 |
| Agent | `.claude/agents/*.md`에 정의된 역할 중심 전문 에이전트 |
| Skill | `.claude/skills/*/SKILL.md`에 정의된 방법/절차 중심 지식 패키지 |
| Orchestrator | agent와 skill을 workflow로 엮는 특수 skill 또는 문서 |
| DeepAgents | LangChain 생태계의 agent harness |
| Subagent | DeepAgents main agent가 위임할 수 있는 전문 하위 agent |
| IR | 변환 중간 표현, `harness.deepagents.ir.yaml` |
| Lossiness | 원본 의미가 타깃 런타임에서 완전히 보존되지 않는 정도 |

---

## 31. 부록 B: 참조 자료

- RevFactory Harness GitHub: `https://github.com/revfactory/harness`
- RevFactory Harness Korean README: `https://github.com/revfactory/harness/blob/main/README_KO.md`
- RevFactory Harness SKILL.md: `https://github.com/revfactory/harness/blob/main/skills/harness/SKILL.md`
- DeepAgents overview: `https://docs.langchain.com/oss/python/deepagents/overview`
- DeepAgents skills: `https://docs.langchain.com/oss/python/deepagents/skills`
- DeepAgents GitHub: `https://github.com/langchain-ai/deepagents`
- Claude Agent Skills overview: `https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview`

---

## 32. 최종 제품 한 줄 정의

```text
harness2deepagents는 RevFactory Harness의 agent/team/skill/orchestrator 구조를 보존하면서 DeepAgents main agent + subagents + skills 앱으로 포팅하는 Claude Code Skill이다.
```
