# 사용 예시

## 기본 호출

```
/harness2deepagents
```

기본 동작: 현재 cwd를 root로, full 모드, `ports/deepagents/` 출력.

## 명시적 호출

```
/harness2deepagents
이 프로젝트의 RevFactory Harness 산출물을 DeepAgents로 포팅해줘. MCP 설정은 유지하고, 원본 .claude 파일은 건드리지 마.
```

## Audit-only

```
/harness2deepagents audit only
DeepAgents 앱 생성 전에 하네스 구조와 변환 가능성만 점검해줘.
```

→ IR + conversion_report.md만 생성 (`_workspace/`에). app 코드 미생성.

## 반복 실행 안전성

```
/harness2deepagents
기존 ports/deepagents가 있으면 덮어쓰지 말고 새 폴더에 생성해줘.
```

→ `ports/deepagents_20260506_153045/` 같은 timestamp 디렉토리 사용.

## 트리거 키워드 (should-trigger)

- "이 .claude를 DeepAgents로 변환해줘"
- "harness2deepagents 실행"
- "/h2d"
- "Claude Code 에이전트 팀을 LangChain으로 포팅"
- "RevFactory Harness 산출물 마이그레이션"
- "agents와 skills를 Python deepagents 앱으로"
- "이 프로젝트의 하네스 감사만 해줘"

## 트리거하지 말아야 할 케이스 (should-NOT-trigger)

- "harness 만들어줘" → `/harness` 스킬 (생성용, 변환 아님)
- "deepagents 라이브러리 설치 방법" → 일반 질문
- "LangGraph로 graph 만들어줘" → out of scope (raw LangGraph emitter 별도 제품)
- ".claude/agents 형식 알려줘" → 문서 질문

## 변환 후 실행 (생성물의 기본 동작)

생성된 `ports/deepagents/app/`은 항상 `langchain-ai/deep-agents-ui`를 기본 UI로 가진다.

```bash
cd ports/deepagents/app

# 1) 의존성 설치
pip install -r requirements.txt

# 2) provider 선택 — Anthropic / OpenAI / Azure OpenAI / Bedrock / Vertex 중 하나
cp .env.example .env
# .env 편집: 사용할 provider 블록 uncomment + 키 채우기
#   Anthropic    : DEEPAGENTS_MODEL=anthropic:claude-sonnet-4-6 + ANTHROPIC_API_KEY
#   OpenAI       : DEEPAGENTS_MODEL=openai:gpt-4o + OPENAI_API_KEY
#   Azure OpenAI : DEEPAGENTS_MODEL=azure_openai:<deployment-name>
#                  + AZURE_OPENAI_API_KEY / AZURE_OPENAI_ENDPOINT
#                  / OPENAI_API_VERSION / AZURE_OPENAI_DEPLOYMENT_NAME

# 3) UI 부트스트랩 (한 번만 — ./ui/에 deep-agents-ui clone, ui/.env.local 생성)
bash bootstrap_ui.sh

# 4) 백엔드 (LangGraph dev server :2024)
langgraph dev

# 5) 다른 터미널에서 UI 실행 (:3000)
cd ui && pnpm install && pnpm dev
```

## Headless 실행 (UI 없이)

```bash
cd ports/deepagents/app
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # 또는 다른 provider 키
python smoke_test.py                # import sanity check
python agent.py                     # 단일 invocation
```
