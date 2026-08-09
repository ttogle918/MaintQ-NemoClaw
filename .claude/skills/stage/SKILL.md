---
name: stage
description: 스프린트의 특정 스테이지를 실행한다. 병렬 구현 → 회귀 → 설계 검토 → 커밋 후 수동 체크리스트를 출력하고 멈춘다. 사용자가 /stage를 호출할 때 사용.
---

# /stage — 스테이지 실행

## 목적

`/sprint` 로 확정된 계획의 한 스테이지를 실행한다.
자동 파이프라인(구현 → 회귀 → 검토 → 커밋) 후 **수동 체크리스트를 출력하고 멈춘다.**

```
/stage N
  1. 태스크 확인       → docs/sprints/sprint-{N}.md
  2. tool-builder 병렬
  3. eval-runner (회귀)
  4. reviewer (게이트)
  5. git commit
  6. 수동 체크리스트 → 대기
```

---

## Step 1: 태스크 확인

`docs/sprints/sprint-{N}.md` 에서 해당 스테이지 태스크와 상세 명세를 읽는다.
이전 스테이지 미완료 상태로 건너뛰면 경고 후 사용자 확인.

---

## Step 2: tool-builder 병렬 실행

태스크 수만큼 **동시** 호출. 각 에이전트에 전달:

```
태스크: MQ-XXX
스프린트 N / 스테이지 M
명세: docs/sprints/sprint-{N}.md 의 MQ-XXX 절
범위: mcp_server/ | backend/ | frontend/ | data/
병렬 중인 다른 태스크: [목록] — 같은 파일 수정 주의
지켜야 할 결정: [관련 D번호]
```

> `tool-builder` 의 기본 설명은 `mcp_server/`·`backend/` 지만 프론트 태스크도 맡길 수 있다.
> 이때 **범위가 `frontend/` 임을 명시**하고, `frontend/README.md` 의 설계 계약 절을
> 함께 읽도록 전달한다.

---

## Step 3: eval-runner — 회귀 검증

MaintQ의 회귀 스위트는 고정이다. 전부 통과해야 한다.

```bash
uv run python data/seed.py --with-error-codes                     # 시드 자가검증 (건수는 러너 출력 기준)
                                                    # --with-error-codes 필수 (iG5A 매핑 승인 완료)
                                                    #   빼면 error_codes 가 0행으로 리셋되고
                                                    #   api_contract ②-b 가 PO-0117.model 을 못 읽어 FAIL
                                                    # ⛔ --today 로 고정 날짜를 핀하지 말 것 — 시드는 실행일
                                                    #   기준 상대일인데 검증 쿼리(seed.py:644)는 벽시계를 써서
                                                    #   검사 ⑤(반복 고장)가 위양성 FAIL 한다
uv run python spikes/sp2_mcp_roundtrip.py          # MCP 왕복 15건
uv run python spikes/write_tool_contract.py        # 쓰기 도구 경계 14건
uv run python spikes/api_contract.py               # 권한·전이·D57 28건
uv run python spikes/sp3_sse_events.py             # SSE 4종 22건
uv run ruff check data backend mcp_server spikes
```

`frontend/` 변경이 있으면 추가:

```bash
cd frontend && npx tsc --noEmit && npx next build
```

**FAIL 시:** 실패한 태스크의 tool-builder만 재실행 → 해당 부분만 재검증.
전체 스테이지 재실행은 불필요하다.

---

## Step 4: reviewer — 설계 준수 (게이트)

`.claude/agents/reviewer.md` 호출. 전달:

```
스테이지: N
변경 파일: [전체 목록]
적용 태스크: [MQ 목록]
```

**커밋 전 반드시 확인되는 것 (절대 규칙)**

| 규칙 | 확인 |
|---|---|
| D10 | MCP 도구에 `po_drafts` UPDATE/DELETE 가 없는가 |
| D9 | 도구가 예외를 던지지 않고 status로 반환하는가 |
| D1 | 코드 정의에 RAG, 절차에 룩업을 쓰지 않았는가 |
| 안전 | 안전 문구가 매뉴얼 근거(페이지) 없이 생성되지 않았는가 |
| 환각 | not_found에 유사 코드를 추측하지 않는가 |
| D26·D32 | 저장은 물리 페이지, 표시만 인쇄 페이지 병기인가 |
| D39 | 시각이 UTC 저장·전송인가 |
| — | `data/raw/` 를 수정하지 않았는가 |

**FAIL 시:** 필수 수정 → 해당 파일만 재구현 → reviewer만 재실행.
**보안·안전 규칙 위반은 수정 전 커밋 불가.**

---

## Step 5: 커밋

reviewer PASS 즉시.

```bash
git add [변경 파일]
git commit -m "$(cat <<'EOF'
[M{마일스톤}] {스테이지 내용 한 줄 요약}

- MQ-XXX: {핵심 구현}
- MQ-XXX: {핵심 구현}

Sprint {N} / Stage {M}
검증: seed 8 · SP2 15 · write_tool 14 · api 19 · SP3 11

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
)"
```

커밋 후 `docs/sprints/sprint-{N}.md` 에 완료 기록을 추가한다.

```markdown
### Stage {M} 완료 (YYYY-MM-DD)
**커밋**: `{hash}` — `{메시지 첫 줄}`

#### MQ-XXX
- 구현 파일 목록
- 회귀: {통과 건수}
```

---

## Step 6: 수동 체크리스트 출력 후 대기

**이 단계가 핵심이다.** 자동 검증이 못 잡는 걸 사용자에게 넘긴다.

MaintQ에서 자동 검증이 못 잡는 것들:
- 안전 문구의 **문안 적절성** (기준값 "10분 이상"은 자동 검사되지만 표현은 사람이)
- `related_parts` 매핑이 **실제로 맞는지**
- 화면의 시각적 정합 (오렌지 남용, trace 패널이 죽지 않았는지)
- 데모 흐름이 자연스러운지

```markdown
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Stage {M} 자동 파이프라인 완료
커밋: {해시}
회귀: seed 8 · SP2 15 · write_tool 14 · api 19 · SP3 11 전부 통과
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 수동 확인

### 기능
- [ ] {기능}: {확인 방법 — URL·명령어까지}

### 사람만 판단 가능한 것
- [ ] {안전 문구 / 매핑 정확성 / 시각 정합}

### 회귀 위험
- [ ] {이번 변경이 건드린 기존 기능}

다음: 문제 없으면 /stage {M+1} · 버그면 내용 알려주기 · 마지막이면 /done
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 재개

`/stage 2 resume` — `docs/sprints/sprint-{N}.md` 에서 완료 상태를 확인하고,
커밋이 이미 됐으면 Step 6부터 재개한다.

## 에러 처리

| 상황 | 처리 |
|------|------|
| tool-builder 실패 | 해당 태스크만 실패 처리, 나머지 병렬 태스크 계속 |
| 회귀 FAIL | 실패 태스크 tool-builder만 재실행 |
| reviewer FAIL | 커밋 보류, 수정 후 reviewer 재실행 |
| 병렬 파일 충돌 | 스테이지 재분리 필요 → `/sprint` 재실행 |
| 사람 승인 대기에 막힘 | 해당 태스크 보류하고 나머지 진행, 체크리스트에 명시 |
