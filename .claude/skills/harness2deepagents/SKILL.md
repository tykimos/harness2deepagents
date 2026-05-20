---
name: harness2deepagents
description: "RevFactory /harness가 생성한 Claude Code 산출물(.claude/agents, .claude/skills, .mcp.json, CLAUDE.md)을 실행 가능한 LangChain DeepAgents Python 앱으로 포팅, 변환, 마이그레이션, 변환, 감사할 때 사용. 'harness 변환', 'DeepAgents로 포팅', '하네스 마이그레이션', 'harness2deepagents', 'h2d', 'harness 감사', '.claude를 LangChain으로', 'agent 팀을 deepagents로' 등을 요청하면 반드시 이 스킬을 사용. raw LangGraph는 기본 생성하지 않음."
compatibility: Claude Code skill. RevFactory Harness 산출물을 가진 프로젝트에서 사용. Python 3.11+ 검증 권장.
metadata:
  version: "0.2.0"
  source: "revfactory/harness"
  target: "deepagents"
  aliases:
    - harness-to-deepagents
    - h2d
changelog:
  v0.2.0:
    - "tools.py 기본을 mock_fallback + 자동 TOOLS 등록으로 (이전엔 strict + 빈 TOOLS라 첫 호출에서 죽음)"
    - "@tool 데코레이터 의무화 — LLM에 args schema 노출"
    - "app/.gitignore 자동 생성 — .env 커밋 위험 차단"
    - ".env.example에 LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=600 추가 — reasoning 모델 stream timeout 방지"
    - "Azure OpenAI provider notes에 API_VERSION=2025-01-01-preview 권장"
    - "port-validation에 Stage 9~11 추가 (tool registration / stream timeout / gitignore)"
    - "README에 'cd app && langgraph dev', 'set -a; source .env; set +a' 등 정확한 명령 시퀀스 명시"
    - "conversion_report에 Service-ready handoff 체크리스트 섹션 추가"
---

# harness2deepagents — Harness → DeepAgents 포팅 오케스트레이터

RevFactory Harness 산출물을 실행 가능한 DeepAgents 앱으로 변환하는 통합 오케스트레이터. **DeepAgents 전용** — raw LangGraph 또는 단일 `create_agent` 앱은 생성하지 않는다.

## 실행 모드: 에이전트 팀

4명의 전문 팀원이 Pipeline + Producer-Reviewer 패턴으로 협업.

## 에이전트 구성

| 팀원 | 에이전트 타입 | 역할 | 주 스킬 | 출력 |
|------|---|---|---|---|
| harness-extractor | 커스텀 | Harness source 파싱, IR 빌드 | harness-source-extraction | `_workspace/01_extractor_ir.yaml` |
| deepagents-emitter | 커스텀 | DeepAgents 앱 코드 생성 | deepagents-emission | `output_dir/app/*` |
| port-validator | 커스텀 | compile/secret/smoke 검증 | port-validation | `output_dir/logs/validation.json` |
| conversion-reporter | 커스텀 | 보고서 + 품질 점수 | conversion-reporting | `output_dir/conversion_report.md` |

## 핵심 원칙

1. **DeepAgents only** — Harness orchestrator → DeepAgents main agent prompt, Harness agents → subagents, Harness skills → `app/skills/`. raw LangGraph는 절대 생성하지 않는다.
2. **IR 우선** — `harness.deepagents.ir.yaml`을 먼저 만든다. IR 없이 바로 `agent.py`를 쓰지 않는다.
3. **구조 보존** — Who(agent) / How(skill) / When(orchestration) / What left(artifact)의 4개 분리를 유지한다. prompt 평탄화 금지.
4. **안전한 변환** — 기존 `ports/deepagents/` 보존(timestamp 폴더 폴백), secret 마스킹, 원본 `.claude/` 수정 금지.
5. **Progressive Disclosure 보존** — Harness skills의 `SKILL.md` / `references/` / `scripts/` / `assets/` 구조를 그대로 복사한다.
6. **기본 UI = langchain-ai/deep-agents-ui** — 모든 생성물에 `langgraph.json` (graph id `deepagent`) + `bootstrap_ui.sh` (`./ui/`에 deep-agents-ui clone + wire) + `.env.example`(Anthropic/OpenAI/Azure OpenAI/Bedrock/Vertex 블록)이 기본 포함된다. 사용자는 `bash bootstrap_ui.sh && langgraph dev` 두 단계로 UI를 띄울 수 있다.
7. **Provider-agnostic 모델** — `DEEPAGENTS_MODEL`에 `anthropic:...` / `openai:...` / `azure_openai:<deployment>` / `bedrock_converse:...` / `google_vertexai:...` 형식 모두 허용. `langchain-anthropic` + `langchain-openai`는 기본 dependency.

## 워크플로우

### Phase 1: 사용자 입력 분석 및 모드 결정

1. 사용자 입력에서 다음 신호 감지:
   - `audit only`, `분석만`, `점검만`, `감사만` → audit_only 모드
   - 명시적 root 경로 → custom_root
   - 그 외 기본값 → full 모드, 현재 작업 디렉토리

2. 도구 stub 정책 결정 (`tools_mode` — v0.2 신규):
   - 기본값: **`mock_fallback`** — stub은 명확히 라벨된 MOCK 데이터를 반환하여 키 없이도 워크플로우가 끝까지 돈다. 데모/시연/CI/오프라인 환경에 적합.
   - 사용자가 `strict`, `엄격`, `raise on stub`, `mock 금지` 신호를 주면 → `strict_stub` 모드. stub 호출 시 `NotImplementedError` raise.
   - 두 모드 중 어느 쪽이든 emitter는 `@tool` 데코레이터로 wrap + `TOOLS` 리스트에 자동 등록한다 (이전 v0.1의 silent failure 방지).

3. 사용자에게 한 줄 알림: "Harness source 분석을 시작합니다 (모드: full|audit_only, tools_mode: mock_fallback|strict_stub)."

### Phase 2: 팀 구성 및 작업 등록

```
TeamCreate(
  team_name: "harness2deepagents-team",
  members: [
    { name: "extractor", agent_type: "harness-extractor", prompt: "프로젝트 root에서 .claude/agents, .claude/skills, .mcp.json, CLAUDE.md를 발견하고 IR을 _workspace/01_extractor_ir.yaml로 생성하세요. mode={mode}, root={root}" },
    { name: "emitter", agent_type: "deepagents-emitter", prompt: "extractor의 IR을 입력으로 ports/deepagents{_TS}/app/* 를 생성하세요. audit_only 모드에서는 트리거되지 않습니다." },
    { name: "validator", agent_type: "port-validator", prompt: "emitter의 출력 디렉토리에 대해 7단계 검증을 수행하고 logs/validation.json을 생성하세요." },
    { name: "reporter", agent_type: "conversion-reporter", prompt: "IR + emitter 결과 + validation.json을 통합하여 conversion_report.md를 생성하세요." }
  ]
)

TaskCreate(tasks: [
  { title: "Harness source 추출 및 IR 생성", assignee: "extractor" },
  { title: "DeepAgents 앱 방출", assignee: "emitter", depends_on: ["Harness source 추출 및 IR 생성"] },
  { title: "포트 검증", assignee: "validator", depends_on: ["DeepAgents 앱 방출"] },
  { title: "변환 보고서 작성", assignee: "reporter", depends_on: ["포트 검증"] }
])
```

audit_only 모드에서는 emitter, validator 작업을 등록하지 않고 reporter만 IR 기반으로 실행.

### Phase 3: 추출 (Extract)

**실행 주체:** harness-extractor

1. Root 결정 (기본: `cwd`)
2. `.claude/agents/*.md` glob → agent 파싱 (frontmatter + body)
3. `.claude/skills/*/SKILL.md` glob → skill 파싱
4. 오케스트레이터 점수화 → primary 선택 또는 synthetic 권고
5. 아키텍처 패턴 추정 (pipeline/fanout_fanin/expert_pool/producer_reviewer/supervisor/hierarchical/hybrid)
6. Claude-only 연산 (TeamCreate/TaskCreate/SendMessage 등) 위치 기록
7. MCP/settings/tool 의존성 식별 + secret 마스킹
8. IR YAML 빌드 → `_workspace/01_extractor_ir.yaml`

**Source 미발견 시:** `.claude/agents`도 `.claude/skills`도 없으면 즉시 실패: "현재 프로젝트에서 RevFactory Harness 산출물로 볼 수 있는 .claude/agents 또는 .claude/skills를 찾지 못했습니다. 생성된 파일은 없습니다." → 종료.

### Phase 4: 방출 (Emit) — full 모드만

**실행 주체:** deepagents-emitter

1. Output 디렉토리 결정: `ports/deepagents/`. 존재하면 `ports/deepagents_YYYYMMDD_HHMMSS/`
2. IR 로드 → main system prompt 합성 (orchestrator + Conversion Notes + Delegation Policy + Artifact Policy + Safety Policy)
3. SUBAGENTS 배열 합성 (각 agent를 dict로)
4. 코드 템플릿 렌더링: `agent.py`, `config.py`, `tools.py`, `mcp_tools.py`(MCP 시), `smoke_test.py`, `requirements.txt`, `pyproject.toml`, `README.md`
5. `.claude/skills/*/`를 `app/skills/*/`로 복사 (`.git`/`.venv`/`__pycache__` 제외)
6. `.mcp.json` 마스킹 후 `app/.mcp.json`으로 복사
7. IR 최종본을 `output_dir/harness.deepagents.ir.yaml`로 이동

### Phase 5: 검증 (Validate) — full 모드만

**실행 주체:** port-validator (총 11 stage, v0.2)

1. IR YAML parse 검증
2. 필수 파일 존재 확인 (`agent.py`, `config.py`, `tools.py`, `smoke_test.py`, `requirements.txt`, `pyproject.toml`, `README.md`, `langgraph.json`, `bootstrap_ui.sh`, `.env.example`, **`.gitignore`** — v0.2부터)
3. `python -m compileall app` 실행
4. Skill 폴더 수 일치 확인
5. Secret scan (sk-, AKIA, ghp_, BEGIN PRIVATE KEY 등 패턴)
6. `python -c "import agent; assert hasattr(agent, 'agent')"` smoke import
7. Anti-pattern check: `from langgraph.graph` 부재 확인
8. **Tool registration check (v0.2)** — `@tool` 데코레이터 + `TOOLS` 자동 등록 + IR stub과 일치 여부
9. **Stream timeout sanity (v0.2)** — `.env.example`에 `LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S` ≥ 300
10. **Gitignore presence (v0.2)** — `.gitignore`에 `.env`, `.env.*`, `!.env.example` 포함
11. → `output_dir/logs/validation.json` 작성

**Fail 처리:** validator가 fail 보고 → emitter에게 SendMessage로 fix 요청 (1회 재시도). 재실패 시 reporter에게 알리고 점수에 반영.

### Phase 6: 보고 (Report)

**실행 주체:** conversion-reporter

1. IR + (있으면) validation.json + emitter 결과 통합
2. PRD §19.1 13개 섹션으로 conversion_report.md 작성
3. 변환 품질 점수 산출 (0.0~1.0, PRD §19.2 가중치)
4. Manual actions / Run commands / Limitations 도출
5. → `output_dir/conversion_report.md`

### Phase 7: 정리 및 운영-준비 핸드오프 (v0.2 확장)

1. 팀원 종료 (TeamDelete)
2. `_workspace/` 보존 (감사 추적용)
3. **Service-ready handoff** — 사용자에게 다음 형식으로 보고:

   ```
   ✅ DeepAgents 앱 변환 완료
   - 출력: <output_dir>
   - 변환 점수: <score>/1.00
   - Manual actions: <n>건
   - tools_mode: <mock_fallback|strict_stub>

   📋 Service-ready checklist (이 순서대로 실행하면 UI까지 띄울 수 있음):

   1. cd <output_dir>/app
   2. python3 -m venv .venv && source .venv/bin/activate
   3. pip install -r requirements.txt
   4. cp .env.example .env  # 그리고 .env에 자기 provider 키 채우기
   5. set -a; source .env; set +a
   6. python smoke_test.py  # import 검증
   7. langgraph dev --port 2024 --no-browser  # 백엔드 가동
      → http://127.0.0.1:2024/ok 확인
   8. (옵션) bash bootstrap_ui.sh && cd ui && yarn install && yarn dev
      → http://localhost:3000 에서 UI

   🔴 Security:
   - .env는 자동 .gitignore로 보호됨 (절대 커밋 금지)
   - 이 세션에 공유한 API 키가 있다면 작업 후 즉시 회전 권장
   - MCP secret은 raw 문자열 금지, env-var 참조만 허용

   ⚠️  Common pitfalls (v0.2에서 자동 방지됨, 그래도 알아두세요):
   - reasoning 모델은 LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=600 이상 필수
   - Azure GPT-5.x는 OPENAI_API_VERSION=2025-01-01-preview 필요
   - 실제 워크플로우 invoke 시 recursion_limit=50 이상 권장
   - tools.py의 stub은 mock_fallback 기본. 운영용은 reference impl 주석 참고

   🛠️  Tools status:
   - <tool_name>: <mock|strict|implemented> — <reason if not yet wired>
   ```

4. 보고는 위 체크리스트를 그대로 출력 (사용자가 복붙해서 실행할 수 있도록).

## 데이터 흐름

```
[리더/오케스트레이터]
   │
   ├──→ [extractor]
   │       │ scripts/extract_harness.py
   │       ↓
   │    _workspace/01_extractor_ir.yaml
   │       │
   ├──→ [emitter] ◄────┐
   │       │ scripts/emit_deepagents.py + assets/*.j2
   │       ↓           │ fix loop (1회)
   │    output_dir/app/*│
   │       │           │
   ├──→ [validator] ───┘
   │       │ scripts/validate_port.py + secret_scan.py
   │       ↓
   │    output_dir/logs/validation.json
   │
   └──→ [reporter]
           │
           ↓
        output_dir/conversion_report.md
```

## 에러 핸들링

| 상황 | 전략 |
|------|------|
| Harness source 미발견 | 즉시 종료, 사용자에게 명확한 메시지. 파일 생성 없음 |
| extractor 실패 (parsing 일부 실패) | 가용 IR로 진행, warnings에 기록 |
| emitter 실패 (한 단계) | 1회 재시도. 재실패 시 부분 산출물 보존 + reporter에 표시 |
| validator fail (compile/secret) | emitter에 fix 요청 1회 → 재검증 → 여전히 fail이면 reporter가 명시 |
| 기존 output dir 존재 | 새 timestamp dir 사용. 기존 파일 절대 보존 |
| audit_only인데 emitter 트리거 시도 | 오케스트레이터가 차단 |
| 팀원 중지 | 리더가 감지 → 재시작 → 실패 시 부분 결과로 reporter 진행 |
| 사용자 요청 모호 | 기본값(full 모드, cwd)으로 진행하되 진행 알림에 모드 명시 |

## 안전 규칙

- 원본 `.claude/`는 **읽기 전용**. 절대 수정하지 않음
- 출력 경로는 project root 아래로 제한 (path traversal 차단)
- secret-like literal은 항상 마스킹. raw secret을 IR/report/code에 노출하지 않음
- 외부 API 호출 없음 (live invocation 금지)
- MCP 서버 자동 실행 안 함 (`mcp_tools.py` TODO만 생성)
- raw LangGraph emitter 생성 금지 — 검증 단계에서 차단

## 테스트 시나리오

### 정상 흐름 (full 모드)

1. 사용자: `/harness2deepagents` 호출, 프로젝트에 `.claude/agents/{a,b,c}.md` + `.claude/skills/{x,y}/SKILL.md` 존재
2. Phase 1: full 모드 결정
3. Phase 2: 4명 팀 구성 + 4개 작업 등록
4. Phase 3: extractor가 IR 생성 (3개 agent + 2개 skill 발견)
5. Phase 4: emitter가 `ports/deepagents/app/*` 생성, skills 복사
6. Phase 5: validator가 7단계 모두 pass
7. Phase 6: reporter가 conversion_report.md 작성, 점수 0.92
8. 사용자에게: "ports/deepagents/ 생성 완료. 점수 0.92. `cd ports/deepagents/app && pip install -r requirements.txt && python smoke_test.py` 실행 가능."

### Audit-only 흐름

1. 사용자: `/harness2deepagents audit only`
2. Phase 1: audit_only 결정
3. Phase 2: extractor + reporter만 등록
4. Phase 3: extractor가 IR 생성
5. Phase 6: reporter가 IR 기반으로 (validation 없이) 보고서 작성
6. 사용자에게: 변환 가능성 점수와 manual actions 알림

### 에러 흐름 (validator가 secret 발견)

1. Phase 5 진행 중 validator가 `app/.mcp.json`에서 raw `sk-...` 발견 → fail 분류
2. validator가 emitter에게 SendMessage("agent.py:.mcp.json 라인 N에 raw secret. 재마스킹 후 재방출 요청")
3. emitter가 `scripts/secret_scan.py --redact` 재실행 → 마스킹된 사본 재생성
4. validator가 재검증 → pass_with_warnings
5. reporter가 Warnings에 "secret 마스킹 적용" 기록

## 운영 함정 카탈로그 (v0.2 — 실제 배포에서 학습)

v0.1로 생성한 앱을 LangGraph 백엔드 + deep-agents-ui 프론트엔드까지 실제로 띄워 사용한 결과 발견된 함정들. v0.2에서 emitter/validator가 모두 자동 방지하며, 사용자 보고서에도 명시된다.

| # | 증상 | v0.1에서 발생한 이유 | v0.2 자동 방지 |
|---|---|---|---|
| F1 | 첫 도구 호출에서 `NotImplementedError` → 워크플로우 즉사 | emitter가 stub을 `raise`로만 emit + `TOOLS = []`로 비워둠 | mock_fallback 기본 + `TOOLS` 자동 등록. strict 원할 시 `tools_mode=strict_stub` 옵션 |
| F2 | LLM이 도구 자체를 인지 못 함 (plain function이라 args schema 노출 안 됨) | `@tool` 데코레이터 미사용 | emitter가 `@tool` 의무화 + validator Stage 9가 검증 |
| F3 | `.env` 커밋 위험 | `.gitignore` 부재 | emitter가 `app/.gitignore` 자동 생성 + validator Stage 11이 검증 |
| F4 | `StreamChunkTimeoutError: No streaming chunk received for 120s (chunks_received=583)` | langchain-openai 기본 120s가 reasoning 모델(gpt-5.x/o3/claude-opus-thinking)에 짧음 | `.env.example`에 `LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=600` + validator Stage 10 |
| F5 | Azure OpenAI GPT-5.x deployment가 응답 안 함 | `OPENAI_API_VERSION=2024-10-21` 같은 구버전 | README provider notes에 `2025-01-01-preview` 권장 명시 |
| F6 | UI 띄우는 게 복잡 (yarn install + Node 20 + 환경변수) | README가 `bash bootstrap_ui.sh`만 언급 | README "Run with the default UI" 섹션에 정확한 3줄 명령 시퀀스 + Node 버전 요구사항 |
| F7 | 메타 질문조차 `recursion_limit=3` 시 즉시 실패 | DeepAgents의 plan/todo 노드가 사이클 빠르게 소비 | README에 `recursion_limit=50` 이상 권장 명시 |
| F8 | `langgraph dev` 실행 위치 헷갈림 | langgraph.json 위치가 `app/`임이 명확히 안내 안 됨 | README에 `cd app && langgraph dev` 명시 |
| F9 | `.env` 변수가 안 먹힘 | `langgraph dev` 시작 전 `source .env` 누락 | README에 `set -a; source .env; set +a` 명시 |
| F10 | `from langchain_core.tools import tool` import 누락 | requirements.txt에 `langchain-core` 누락 | requirements.txt 최소에 명시 |

이 함정들은 모두 **단순한 문서화 누락이 아니라 emitter/validator의 결함**이었다. v0.2부터 코드 생성 시점에 자동 방지된다.

## 참고

- IR 스키마: `references/ir-schema-summary.md` (PRD §12.2 요약)
- 매핑 규칙 (Claude ops → DeepAgents): `references/mapping-rules.md`
- 사용 예시 / 호출 패턴: `references/usage-examples.md`
- Edge cases: `references/edge-cases.md`
- **도구 어댑터 reference 구현 모음 (v0.2 신규):** `references/tool-adapters.md` — web_search / fetch_url / image_generation 각각의 Z.AI / Tavily / FAL / httpx 구현 예시
