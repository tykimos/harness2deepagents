# Installation

이 repo는 5개 Claude Code skills + 4개 agents로 구성된 한 세트의 변환 파이프라인입니다. 모두 `~/.claude/` 아래에 설치되어야 동작합니다.

## 요구 사항

- [Claude Code](https://claude.com/claude-code) CLI (latest)
- Python 3.11+ (생성된 DeepAgents 앱 실행용 — 변환 자체는 Python 없이도 동작)
- Git (UI bootstrap이 `langchain-ai/deep-agents-ui` clone에 사용)

## 설치 (한 줄)

```bash
git clone https://github.com/tykimos/harness2deepagents.git /tmp/harness2deepagents \
  && cp -R /tmp/harness2deepagents/.claude/skills/* ~/.claude/skills/ \
  && cp -R /tmp/harness2deepagents/.claude/agents/* ~/.claude/agents/
```

> 이미 같은 이름의 skill/agent가 있다면 위 명령이 덮어씁니다. 안전하게 가려면 `~/.claude/skills/` 백업 후 진행하세요.

## 설치 확인

Claude Code를 새로 띄운 뒤:

```
/harness2deepagents
```

스킬 매칭이 트리거되면 정상입니다. 실제로 변환하려면 `.claude/agents/` + `.claude/skills/` 가 있는 RevFactory Harness 산출물 디렉토리에서 호출하세요.

## 설치되는 구성요소

```
~/.claude/skills/
├── harness2deepagents/           # 오케스트레이터 (사용자가 호출하는 진입점)
├── harness-source-extraction/    # extractor가 사용
├── deepagents-emission/          # emitter가 사용
├── port-validation/              # validator가 사용
└── conversion-reporting/         # reporter가 사용

~/.claude/agents/
├── harness-extractor.md
├── deepagents-emitter.md
├── port-validator.md
└── conversion-reporter.md
```

5개 skill / 4개 agent — 모두 함께 있어야 4-에이전트 팀 변환 파이프라인이 동작합니다.

## 제거

```bash
rm -rf ~/.claude/skills/{harness2deepagents,harness-source-extraction,deepagents-emission,port-validation,conversion-reporting}
rm -f ~/.claude/agents/{harness-extractor,deepagents-emitter,port-validator,conversion-reporter}.md
```

## 업데이트

```bash
cd /tmp/harness2deepagents && git pull \
  && cp -R .claude/skills/* ~/.claude/skills/ \
  && cp -R .claude/agents/* ~/.claude/agents/
```
