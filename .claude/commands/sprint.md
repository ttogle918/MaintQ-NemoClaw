---
description: 스프린트 계획을 수립합니다. PM이 스테이지를 설계하고 tool-builder가 현실성을 평가합니다. 사용법 /sprint [번호]
---

Sprint $ARGUMENTS 의 **계획만** 수립합니다. 코드 구현은 하지 않습니다 (실행은 `/stage N`).

## 사전 준비 (계획 수립 전 항상)

MaintQ에는 TASK-XXX 형식의 태스크 백로그가 없다. 계획의 재료는 아래 셋이다:

1. `docs/00_MVP_SCOPE.md` — **반드시 만들 것**. 여기 없는 건 스프린트에 넣지 않는다
2. `docs/07_BACKLOG.md` — **지금 만들지 않을 것**(P1~P20). 여기 있는 걸 태스크로 만들면 범위 이탈
3. 현재 상태 — `docs/sprints/` 의 이전 로그, `git log --oneline -15`, 실제 코드 존재 여부

`docs/01_OVERVIEW.md` 의 마일스톤(M1~M4)이 스프린트의 상위 단위다.

## Step 1 — PM 에이전트: 스테이지 계획 수립

`.claude/agents/pm.md` 를 호출해 스테이지 배치 + **태스크별 상세 구현 명세**를 생성한다.
tool-builder 가 추가 추론 없이 그대로 실행할 수 있을 만큼 구체적으로 적는다.

태스크 ID는 `MQ-{스프린트}{순번}` (예: MQ-201, MQ-202).

## Step 2 — tool-builder: 현실성 평가

`.claude/agents/tool-builder.md` 를 호출해 기술적 현실성을 평가한다
(스펙 충분성 · 파일 충돌 · 숨은 순서 의존성 · **사람 승인 대기 항목에 막히는지**).

MaintQ 특유의 블로커를 반드시 확인:
- `error_codes` 사람 승인 (`lookup_error_code`·`rag_search_manual` 이 여기 묶여 있음)
- `related_parts` 검수 (부품 특정 정확률의 뿌리)
- `ANTHROPIC_API_KEY` (에이전트 루프)
- 임베딩 모델/벡터스토어 결정

## Step 3 — 계획 확정

수정이 필요하면 PM에 재계획 요청 후 최종 계획을 출력한다.
최종 계획과 PM·tool-builder 평가를 모두 포함해 `docs/sprints/sprint-{N}.md` 에 기록한다.

## Step 4 — 사용자 확인

`/stage 1` 을 안내하고 대기한다.

워크플로우·출력 형식 상세: `.claude/skills/sprint/SKILL.md`
