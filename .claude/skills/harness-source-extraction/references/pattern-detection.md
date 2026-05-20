# Pattern Detection Heuristics

각 architecture pattern에 대한 감지 신호와 점수.

## Scoring rules

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

### Pipeline (+2 per signal)
- "phase 1", "phase 2", "phase 3"
- "depends_on", "sequential"
- 명시적 phase 순서 (1 → 2 → 3)
- "이전 단계", "다음 단계"

### Fan-out/Fan-in (+3 per signal)
- "parallel", "fan-out", "병렬"
- "independent", "독립"
- "merge", "aggregate", "synthesis", "통합", "종합"
- 단일 메시지에서 여러 Agent 동시 호출 패턴

### Expert Pool (+2 per signal)
- "expert", "pool", "전문가"
- "route", "select", "선택"
- 도메인 분기 패턴

### Producer-Reviewer (+3 per signal)
- "review", "revise", "approve", "리뷰", "승인"
- "QA", "retry", "재시도"
- "draft → review" 패턴
- reviewer agent 명시

### Supervisor (+3 per signal)
- "supervisor", "coordinator", "감독자"
- "assign dynamically", "동적 할당"
- 런타임 작업 분배

### Hierarchical (+3 per signal)
- "parent", "child", "상위", "하위"
- "delegate recursively", "재귀적 위임"
- 중첩 팀

## Confidence

```
confidence = top_score / max_possible_score
```

`max_possible_score`는 패턴별 최대 신호 수 × 가중치.

confidence < 0.5 → `unknown` 또는 `hybrid`로 표시 + warning.

## Hybrid 판단

상위 2개 패턴의 점수 차이가 작으면 (< 20%) hybrid:

```yaml
architecture_pattern:
  value: "hybrid"
  confidence: 0.6
  evidence:
    - "pipeline signals strong (phases)"
    - "producer_reviewer signals also present (QA loop)"
  components: ["pipeline", "producer_reviewer"]
```
