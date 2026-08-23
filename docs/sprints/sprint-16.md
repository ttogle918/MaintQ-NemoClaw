# Sprint 16 — A2A 3종 요청+응답 루프 완성 (D112 재개분 표시·통합)

> 범위는 이미 확정됐다(오늘 세션 브레인스토밍, D112). 이 문서는 **스테이지·태스크 배치만** 한다.
> 배경: request-withdrawal·lookup-clause·assess-loan 3종의 **발신**은 이미 구현·커밋·push
> 완료(`5895c2e`·`ec439f7`·`652618c`·`5fcfe86`). 이번 스프린트가 닫는 구멍은 **응답을 사람이
> 볼 방법이 코드에 없다**는 것 하나다 — trace 는 남지만 화면이 없고, lookup-clause·assess-loan
> 은 애초에 호출할 챗봇 도구가 없다.

## 사람이 해야 할 일

없음. `.env` 의 A2A 자격증명(`MAINTQ_A2A_*`)이 비어 있어도 이번 스프린트는 막히지 않는다 —
`assess-loan` 은 오늘도 실패 경로(502/504)로만 동작이 확인됐고(`status.html`), 그 실패를
정직하게 보여주는 것 자체가 이번 스프린트의 산출물이다.

---

## 의존성 그래프 (요약)

```
Stage 1 ─┬─ MQ-1601 (D113·D114 결정 + SSE/trace a2a_chain_id 필드)
         ├─ MQ-1602 (GET /api/a2a/history 신설 + chain_id 강제 주입)
         └─ MQ-1603 (MCP 도구 2종 + server.py 등록 + .env.example)
              │
Stage 2 ─┬─ MQ-1604 (loop.py·mcp_client.py·prompts.py 배선)      ← 1601, 1603
         ├─ MQ-1605 (frontend lib/api.ts·lib/a2a.ts)              ← 1602
         └─ MQ-1606 (frontend lib/types.ts·lib/chatStream.ts)     ← 1601
              │
Stage 3 ─┬─ MQ-1607 (채팅 A2A 결과 카드)                          ← 1605, 1606
         ├─ MQ-1608 (PO 상세 — 출금요청 상태 부착)                 ← 1605
         ├─ MQ-1609 (건물 위험등급 — 담보대출 이력 패널)            ← 1605
         └─ MQ-1610 (통합 A2A 이력 페이지 /manager/a2a)             ← 1605
              │
Stage 4 ─┬─ MQ-1611 (기존 스파이크 4종 카운트 갱신)                 ← 1604, 1607, 1608, 1609, 1610
         ├─ MQ-1612 (문서 갱신 — 04·06·13·00·README·07 카운트)      ← 1601~1610
         └─ MQ-1613 (신규 스파이크 a2a_partner_tools_contract)      ← 1601~1604
              │
Stage 5 ── MQ-1614 (전수 회귀 재실행 + CLAUDE.md 기준선 갱신)        ← 1611, 1612, 1613
```

---

## Stage 1

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1601 | D113·D114 결정 등재 + SSE `tool_result` 선택 필드 `a2a_chain_id` | `docs/10_DECISIONS.md`, `backend/sse.py`, `backend/agent/trace.py` | — |
| MQ-1602 | `GET /api/a2a/history` 신설 + chain_id 강제 주입 픽스 | `backend/services/a2a_history.py`(신규), `backend/routers/a2a.py`, `backend/services/test_a2a_history.py`(신규) | — |
| MQ-1603 | MCP 도구 2종(`search_insurance_clause`·`assess_equipment_loan`) + `server.py` 등록 | `mcp_server/tools/search_insurance_clause.py`(신규), `mcp_server/tools/assess_equipment_loan.py`(신규), `mcp_server/tools/test_search_insurance_clause.py`(신규), `mcp_server/tools/test_assess_equipment_loan.py`(신규), `mcp_server/server.py`, `.env.example` | — |

### 스테이지 구성 근거

세 태스크는 서로 다른 프로세스·계층을 만진다 — 백엔드 SSE 계약(1601), 백엔드 REST 신규 엔드포인트(1602), MCP 서버 도구(1603). 파일 교집합이 없고(각각 `backend/sse.py`+`backend/agent/trace.py` / `backend/services,routers/a2a.py` / `mcp_server/**`+`.env.example`), 서로의 코드를 import 하지 않아 독립적으로 완결·검증 가능하다. 이 셋이 Stage 2 전체의 기반이라 최우선 배치했다.

---

## Stage 2

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1604 | 에이전트 루프·프롬프트 배선 (도구 2종을 대화에 연결) | `backend/agent/loop.py`, `backend/agent/mcp_client.py`, `backend/agent/prompts.py` | MQ-1601, MQ-1603 |
| MQ-1605 | 프론트 API 계층 — `GET /api/a2a/history` 클라이언트 + 표시 규칙 | `frontend/lib/api.ts`, `frontend/lib/a2a.ts`(신규) | MQ-1602 |
| MQ-1606 | 프론트 채팅 타입·리듀서 — `a2a_chain_id` 를 새 ChatItem 으로 | `frontend/lib/types.ts`, `frontend/lib/chatStream.ts` | MQ-1601 |

### 스테이지 구성 근거

세 태스크는 Stage 1의 각기 다른 산출물에 의존하지만 서로는 겹치지 않는다 — 1604 는 `backend/agent/*` 만, 1605 는 `frontend/lib/api.ts`+`lib/a2a.ts` 만, 1606 은 `frontend/lib/types.ts`+`lib/chatStream.ts` 만 만진다. 1605 와 1606 이 같은 `frontend/lib/` 디렉터리에 있지만 **다른 파일**이라 병렬에 안전하다. Stage 3 의 5개 프론트 컴포넌트 태스크가 전부 이 스테이지의 산출물(계약)에 의존하므로 반드시 먼저 끝나야 한다.

---

## Stage 3

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1607 | 채팅 실시간 — A2A 결과 카드 | `frontend/components/chat/A2aResultCard.tsx`(신규), `frontend/components/chat/ChatThread.tsx` | MQ-1605, MQ-1606 |
| MQ-1608 | PO 상세 — 출금요청 상태 부착 | `frontend/components/queue/WithdrawalStatusPanel.tsx`(신규), `frontend/components/queue/PoDetail.tsx` | MQ-1605 |
| MQ-1609 | 건물 위험등급 화면 — 담보대출 상담 이력 패널 | `frontend/components/asset/LoanAssessmentHistory.tsx`(신규), `frontend/app/(console)/manager/risk-grade/page.tsx` | MQ-1605 |
| MQ-1610 | 통합 A2A 이력 페이지 `/manager/a2a` | `frontend/components/screens/A2aHistoryScreen.tsx`(신규), `frontend/app/(console)/manager/a2a/page.tsx`(신규) | MQ-1605 |

### 스테이지 구성 근거

네 태스크는 "맥락별 분산 배치 + 통합 이력 페이지"라는 요구를 파일 단위로 정확히 쪼갠 것이다 — 채팅(1607)·PO 상세(1608)·건물 위험등급(1609)·신규 통합 페이지(1610) 전부 서로 다른 화면·파일을 만들거나 고친다. 넷 다 `frontend/lib/a2a.ts`(1605)를 **읽기만** 하므로 데이터 계약이 고정된 뒤에는 완전히 독립적으로 병렬 진행할 수 있다. `ui_honesty_contract` 의 `L2_EXTRA`·`L2_FILES_FLOOR`·`L1` 갱신을 이 스테이지에 넣지 않는 이유는 아래 Stage 4 근거에 있다.

---

## Stage 4

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1611 | 기존 계약 스파이크 4종 카운트 갱신 | `spikes/prompt_rules.py`, `spikes/tools_profile_contract.py`, `spikes/s10_smoke.py`, `spikes/ui_honesty_contract.py` | MQ-1604, MQ-1607, MQ-1608, MQ-1609, MQ-1610 |
| MQ-1612 | 문서 갱신 — 도구 계약·REST·카운트 전수 | `docs/04_MCP_TOOLS.md`, `docs/06_REPO_API.md`, `docs/13_DEPLOYMENT.md`, `docs/00_MVP_SCOPE.md`, `docs/README.md`, `docs/07_BACKLOG.md`(카운트 문구만) | MQ-1601~MQ-1610 |
| MQ-1613 | 신규 스파이크 — `a2a_partner_tools_contract` | `spikes/a2a_partner_tools_contract.py`(신규) | MQ-1601~MQ-1604 |

### 스테이지 구성 근거

세 태스크는 전부 **회귀·문서 갱신**이라는 같은 성격이지만 파일이 겹치지 않는다 — 1611 은 기존 스파이크 4개(카운트 상수만 변경), 1612 는 `docs/*`, 1613 은 완전히 새 스파이크 파일(신규 생성이라 어차피 충돌 여지가 없다). `L2_EXTRA`(`WithdrawalStatusPanel.tsx` 등재)·`L2_FILES_FLOOR`·`L1`(`lib/a2a.ts` 등재) 갱신을 여기로 미룬 이유가 중요하다 — Stage 3 의 4개 태스크가 **병렬로** 새 파일을 만드는데, 그 파일 목록이 전부 확정돼야 정확한 floor 숫자를 계산할 수 있다. Stage 3 안에서 이 상수를 건드리면 4개 병렬 태스크가 전부 같은 줄을 놓고 충돌한다 — 그래서 "새 파일이 몇 개 생겼는지 다 알고 난 뒤" 로 미뤄 Stage 4 로 뺐다.

---

## Stage 5

| TASK | 제목 | 범위 | 선행 |
|------|------|------|------|
| MQ-1614 | 전수 회귀 재실행 + `CLAUDE.md` 기준선 갱신 | `CLAUDE.md` | MQ-1611, MQ-1612, MQ-1613 |

### 스테이지 구성 근거

Stage 4 세 태스크가 전부 끝나야 "몇 건이 실제로 바뀌었는지"를 **실행해서** 확인할 수 있다. 이 프로젝트는 손계산으로 회귀 기준선을 적었다가 최소 두 번(MQ-708·MQ-713a급 사고, `prompt_rules` 23→24 오기)을 겪었다 — 그래서 이 스테이지를 별도로 떼어 "실행 결과를 그대로 옮겨 적는다"는 단일 책임만 준다.

---

# 태스크별 상세 구현 명세

## Stage 1

#### MQ-1601 — D113·D114 결정 등재 + SSE `tool_result` 선택 필드 `a2a_chain_id`

- **복무 시나리오**: 확장(S1 계열 실시간 도구 오케스트레이션의 인프라) — S1~S4 자체를 바꾸지 않는다. 이 태스크는 뒤따르는 모든 프론트 표시 태스크의 **데이터 계약**을 고정하는 인프라 작업이다.
- **변경 파일**:
  - `docs/10_DECISIONS.md` (수정 — D113·D114 추가)
  - `backend/sse.py` (수정 — `tool_result()`)
  - `backend/agent/trace.py` (수정 — `TraceWriter.tool_result()`)

- **인터페이스**:

  `docs/10_DECISIONS.md` 표 맨 끝에 4열 형식(`| D### | 결정 | 대안 | 이유 |`)으로 두 줄 추가:

  ```
  | D113 | **`tool_result` SSE 이벤트에 선택 필드 `a2a_chain_id` 를 추가한다** (D54·D66 과 같은 패턴 —
  이벤트 **타입**은 4종 그대로 두고 `tool_result` 의 data dict 에 optional key 만 얹는다). 값은
  `search_insurance_clause`·`assess_equipment_loan` 결과에서만 채워지고, 나머지 도구의 payload 는
  무변경이다 | ① `block` 4번째 타입 추가 / ② `summary` 문자열에 구조를 욱여넣는다 / ③ 새 SSE 이벤트
  타입 5번째 추가 | **①은** `block` 이 `safety\|po_card\|citation` 3종 CHECK 로 고정돼(D14·D22) SQLite
  테이블 재작성 없이 못 늘리고, `citation` 의 `{page,print_page,label}` 계약(D26·D32)은 MaintQ 자체
  매뉴얼 PDF 물리 페이지 전용이라 InsuQ·FinAllQ 응답을 억지로 끼우면 그 계약이 거짓말을 하게 된다.
  **②는** 요약 한 줄에 약관 근거 목록·대출 조건을 다 넣으면 판독 불가능해지고 D44(자기설명적
  summary)의 취지와 어긋난다. **③은** D14 위반이다. 채택안은 실시간 스트림엔 상관관계 키만 흘리고
  원문은 D114 의 새 엔드포인트에서 연다 |
  | D114 | D94 ⓔ 의 미결("`tool_payload` 를 여는 사람 전용 조회 API 필요 여부")을 **필요로 확정**하고
  `GET /api/a2a/history` 를 신설한다. `tool LIKE 'a2a:%'` 인 `traces` 행만 대상으로, 기존
  `read_trace`(D76-2 ⓑ, `tool_payload` 의도적 미포함)는 그대로 둔 채 A2A 전용 새 읽기 경로를 연다.
  `request_chain_id`(D94 ⓐ)로 tool_call/tool_result 쌍을 묶고 `po_id`·`building_id`·`skill`·
  `chain_id` 로 필터링한다 | ① 기존 `read_trace` 에 `tool_payload` 를 포함하도록 개정 / ② 필요 없다고
  다시 미결로 남긴다 | **①은** `spikes/a2a_identity_contract.py ⑫-d`(`read_trace` 에 `tool_payload`
  미포함을 회귀로 고정)를 뒤집는다 — 일반 대화 trace 전체에 원문을 노출하는 것은 이번 요구(A2A
  응답만 구조화 표시)보다 훨씬 넓은 변경이라 기각. **②는** 이번 스프린트의 "구조화된 내용을 실제로
  보여줘야 한다" 요구를 풀 방법이 없어 기각 |
  ```

  `backend/sse.py::tool_result()` 시그니처:
  ```python
  def tool_result(
      tool: str,
      status: str,
      summary: str,
      elapsed: float,
      pages: list[int] | None = None,
      parts: list[str] | None = None,
      a2a_chain_id: str | None = None,
  ) -> SseEvent:
  ```
  기존 로직 뒤에 추가:
  ```python
  if a2a_chain_id is not None:
      data["a2a_chain_id"] = a2a_chain_id
  ```

  `backend/agent/trace.py::TraceWriter.tool_result()` 시그니처에 같은 이름·같은 위치로 파라미터 추가, `sse.tool_result(...)` 호출부에 그대로 전달:
  ```python
  def tool_result(
      self,
      tool: str,
      status: str,
      summary: str,
      elapsed: float,
      pages: list[int] | None = None,
      parts: list[str] | None = None,
      tool_payload: dict | None = None,
      a2a_chain_id: str | None = None,
  ) -> sse.SseEvent:
      return self._write(
          sse.tool_result(tool, status, summary, elapsed, pages, parts, a2a_chain_id),
          tool,
          tool_payload=tool_payload,
      )
  ```

- **핵심 로직**: 순수 배관(plumbing) 변경. `a2a_chain_id` 가 `None` 이면 (지금까지의 모든 호출부처럼) `data` 딕셔너리에 키 자체가 생기지 않는다 — 기존 16종 도구의 SSE payload·`traces.payload` 는 바이트 단위로 무변화(D30 유지).

- **엣지 케이스**:
  - 빈 문자열 `""` 을 넘기면? — `None` 이 아니므로 `data["a2a_chain_id"] = ""` 가 실린다. 호출부(MQ-1604)가 빈 문자열을 넘기지 않도록 책임진다 — 이 함수는 검증하지 않는다(기존 `pages`/`parts` 도 호출부 책임).

- **지켜야 할 결정**: D14·D22(이벤트 타입 4종 고정, 이번 변경은 타입이 아니라 필드) · D30(payload 바이트 동일 — `a2a_chain_id` 가 없는 기존 도구는 무변화) · D54·D66(선례 — optional 필드 추가 패턴)

- **DoD**:
  - `uv run --with pytest python -m pytest data/rules/test_rules.py backend/agent/test_llm_cache.py data/external/test_elice_docvision.py -q` 그대로 통과 (무관 회귀 확인)
  - `uv run python spikes/trace_persist.py` · `uv run python spikes/sp3_sse_events.py` 전건 통과 — 기존 도구 어디도 `a2a_chain_id` 키가 안 생겼는지 이 두 스위트가 바이트 대조로 확인한다
  - `python -c "from backend.sse import tool_result; e=tool_result('x','ok','s',0.1); assert 'a2a_chain_id' not in e.data; e2=tool_result('x','ok','s',0.1,a2a_chain_id='C1'); assert e2.data['a2a_chain_id']=='C1'"` 통과

---

#### MQ-1602 — `GET /api/a2a/history` 신설 + chain_id 강제 주입 픽스

- **복무 시나리오**: 확장(S1 트리거인 request-withdrawal, 신규 lookup-clause·assess-loan) — 이 3종의 응답을 사람이 보게 하는 읽기 경로.
- **변경 파일**:
  - `backend/services/a2a_history.py` (신규)
  - `backend/routers/a2a.py` (수정 — 새 라우트 + `lookup_clause_endpoint`·`assess_loan_endpoint` 에 chain_id 강제 주입 2줄)
  - `backend/services/test_a2a_history.py` (신규)

- **인터페이스**:

  `backend/services/a2a_history.py`:
  ```python
  def list_a2a_history(
      *,
      skill: str | None = None,
      po_id: str | None = None,
      building_id: str | None = None,
      chain_id: str | None = None,
      limit: int = 50,
      db_path: Path | None = None,
  ) -> dict:
      """A2A 호출 감사 이력. `tool LIKE 'a2a:%'` 인 traces 행을 request_chain_id 로 묶어 반환한다.

      반환: {"count": int, "items": [
        {"request_chain_id": str, "skill": str, "session_id": str,
         "status": str | None, "request": dict | None, "response": dict | None, "ts": str},
        ...
      ]}
      `status` 는 record_a2a_trace 가 기록한 값(ok|timeout|unavailable|error) — tool_result 행이
      아직 없으면 None. `response` 는 tool_result.tool_payload 원문, 파싱 실패 시 {"_parse_error": true}.
      정렬: ts desc. limit 은 필터링 후 적용.
      """
  ```

  `backend/routers/a2a.py` 새 라우트:
  ```python
  from backend.services.a2a_history import list_a2a_history

  @router.get("/history")
  def a2a_history_endpoint(
      skill: str | None = None,
      po_id: str | None = None,
      building_id: str | None = None,
      chain_id: str | None = None,
      limit: int = 50,
  ) -> dict:
      """A2A 호출 감사 이력 (D114) — `read_trace`(D76-2 ⓑ)와 달리 tool_payload 원문을 연다."""
      return list_a2a_history(skill=skill, po_id=po_id, building_id=building_id, chain_id=chain_id, limit=limit)
  ```
  역할 게이트 없음(기존 `lookup_clause_endpoint`·`assess_loan_endpoint` 관례를 따름 — `require()` 미호출). ⚠ 리뷰 항목으로 남긴다: 사업 내용(대출액·보험 답변)이 무인증 노출이라는 점은 기존 2개 엔드포인트가 이미 그런 전제였다는 점만 확인하고 넘어간다.

  기존 두 엔드포인트에 chain_id 강제 주입 (성공 분기에서 `record_a2a_trace` 호출 **직전**):
  ```python
  res["request_chain_id"] = chain_id  # 파트너가 echo 안 해도 MCP 도구가 항상 상관관계 키를 받게 한다
  ```

- **핵심 로직**:
  1. `traces` 에서 `tool LIKE 'a2a:%' AND request_chain_id IS NOT NULL` 전건을 `ts` 오름차순으로 읽는다.
  2. `request_chain_id` 로 그룹핑 — `tool_call` 행이면 `payload.input` 을 `request` 에, `tool_result` 행이면 `payload.status` 를 `status` 에, `tool_payload` 를 파싱해 `response` 에, `ts` 를 최종값으로 덮어쓴다(tool_result 시각이 최종 시각).
  3. `skill` 은 `tool` 컬럼에서 `"a2a:"` 접두어를 뗀 값.
  4. `skill`/`po_id`(request.po_id 일치)/`building_id`(request.collateral_building_id 일치)/`chain_id`(request_chain_id 일치) 필터를 순서대로 적용.
  5. `ts` 내림차순 정렬 후 `limit` 적용.

- **엣지 케이스**:
  - `tool_call` 행만 있고 `tool_result` 가 아직 없다(이론상 발생 안 함 — `record_a2a_trace` 는 둘을 한 함수 안에서 순차 INSERT) → `status: None`, `response: None`, `ts` 는 tool_call 시각. 방어적으로 처리하되 실제로 발화하지 않는다.
  - `tool_payload` 가 `NULL`(응답 파싱 실패 등 D76-2 케이스) → `response: None`.
  - `payload` JSON 파싱 실패(있을 수 없지만) → 해당 그룹은 건너뛰지 말고 `request`/`response` 를 `None` 으로 두고 계속 처리(전체 요청을 죽이지 않는다, D9 의 "부분 실패로 전체를 막지 않는다" 태도).
  - `po_id`/`building_id` 필터인데 `request` 가 `dict` 가 아니거나 해당 키가 없으면 매치 안 함으로 처리(예외 던지지 않음).
  - `limit <= 0` → 빈 리스트.

- **지켜야 할 결정**: D76-2(일반 `read_trace` 는 그대로 둔다, 이 엔드포인트만 원문을 연다) · D94 ⓐ·ⓔ(`request_chain_id` 소비 + 미결 해소) · D9(부분 파싱 실패로 전체 실패시키지 않음)

- **DoD**:
  - `uv run --with pytest python -m pytest backend/services/test_a2a_history.py backend/a2a -q` 전건 통과. 최소 케이스: (a) request-withdrawal 1쌍이 `po_id` 필터로 정확히 걸리는지, (b) `skill` 필터, (c) `chain_id` 정확 매칭, (d) `tool_payload` NULL 일 때 `response: None`, (e) 필터 없을 때 3종 스킬이 섞여 나오는지, (f) `limit` 적용
  - `uv run python spikes/a2a_identity_contract.py` 전건 통과 (기존 계약 무회귀 확인)
  - 수동: `uv run uvicorn backend.main:app --port 8000` 기동 후 `curl "http://localhost:8000/api/a2a/history"` 가 200 + `{"count":0,"items":[]}`(신선한 DB 기준) 반환 확인

---

#### MQ-1603 — MCP 도구 2종 + `server.py` 등록 + `.env.example`

- **복무 시나리오**: 신규(InsuQ 약관조회, MaintQ 자체 시나리오 번호 미부여 — A2A_Q 지도에 없던 신규 스킬, D112) · 확장 S8(FinAllQ 담보대출, A2A_Q 2026-08-14 스냅샷 번호. 2026-08-23 사용자 지도 기준으로는 S4 — 인용 시 반드시 시점을 함께 적을 것, D112 후반부 지시)
- **변경 파일**:
  - `mcp_server/tools/search_insurance_clause.py` (신규)
  - `mcp_server/tools/assess_equipment_loan.py` (신규)
  - `mcp_server/tools/test_search_insurance_clause.py` (신규)
  - `mcp_server/tools/test_assess_equipment_loan.py` (신규)
  - `mcp_server/server.py` (수정 — docstring 카운트 + `full` 블록에 등록)
  - `.env.example` (수정 — `MAINTQ_BACKEND_BASE_URL` 추가)

- **인터페이스**:

  ```python
  # mcp_server/tools/search_insurance_clause.py
  def search_insurance_clause(question: str) -> dict: ...
  # 성공: {"status": "ok", "skill_status": "completed", "verdict": ..., "answer": str,
  #        "evidence": list[str], "request_chain_id": str, ...(백엔드 응답의 나머지 키 보존)}
  # 실패: {"status": "error", "reason": "question_required"|"timeout"|"backend_unreachable"|
  #        "upstream_unavailable"|"no_answer"|"unexpected_status"|"invalid_response"|"a2a_error",
  #        "message": str, "skill_status"?: str}
  ```
  ```python
  # mcp_server/tools/assess_equipment_loan.py
  def assess_equipment_loan(loan_amount: float, purpose: str, collateral_building_id: str) -> dict: ...
  # 성공/실패 status·reason 어휘는 search_insurance_clause 와 동일 패턴("no_answer" 대신
  # FinAllQ 쪽은 실제로 거의 항상 upstream_unavailable — status.html 실측, 버그 아님)
  ```

- **핵심 로직** (두 파일 공통 패턴, `search_insurance_clause.py` 기준 — `assess_equipment_loan.py` 는 URL·입력 파라미터·payload 키만 다르다):

  1. 입력 검증 — `question` 이 빈 문자열/공백이면 `status:"error", reason:"question_required"` (D80: 기본값 없음, MCP 스키마가 누락 자체는 앞단에서 막지만 공백 문자열은 코드가 막아야 한다).
  2. `base_url = os.environ.get("MAINTQ_BACKEND_BASE_URL") or "http://localhost:8000"`.
  3. `httpx.post(f"{base_url.rstrip('/')}/api/a2a/lookup-clause", json={"question": question}, timeout=12.0)` — **동기** `httpx.post`(기존 MCP 도구 전부 동기 함수이므로 통일, `mcp_server` 안에 `async def` 도구가 없다).
  4. `httpx.TimeoutException` → `status:"error", reason:"timeout"`.
  5. 그 외 `httpx.HTTPError`(연결 거부 등, **백엔드 프로세스 자체**에 못 닿은 경우 — A2A 파트너가 아니라 MaintQ 백엔드에 못 닿은 경우) → `status:"error", reason:"backend_unreachable"`.
  6. `resp.status_code == 200`:
     - `data = resp.json()`; 실패하면 `reason:"invalid_response"`.
     - `skill_status = data.get("status")`(InsuQ/FinAllQ 프로토콜 자체의 어휘 — `completed`/`input-required`/`rejected`, `backend/a2a/client.py` 독스트링 참조). **`completed` 만 성공**으로 매핑한다 — `input-required`·`rejected`·그 외 값은 전부 `status:"error"`(reason `"no_answer"` 또는 `"unexpected_status"`)로 정직하게 실패시킨다. InsuQ/FinAllQ 가 확답을 안 줬는데 도구가 `ok` 로 위장하면 절대규칙 6("미지에 유사 코드 추측 금지")과 같은 종류의 환각이 된다.
     - 성공이면 `data` 전체를 복사해 `status`만 `"ok"` 로 덮어쓰고 원래 스킬 상태는 `skill_status` 키로 보존해 반환한다(D76 구조 보존 정신).
  7. `resp.status_code in (502, 503, 504)` → `status:"error", reason:"upstream_unavailable"` (파트너 어댑터 자체가 안 죽었다는 것과 응답을 못 받았다는 것을 구분하는 어휘 — 기존 D46 `reason` 세분화 패턴 재사용).
  8. 그 외 상태코드 → `status:"error", reason:"a2a_error"`, `message` 에 `resp.json().get("detail")` 또는 본문 앞 200자.

- **DESCRIPTION 문구** (필수 — 에이전트가 언제/어떻게 부를지 결정하는 유일한 근거):
  - `search_insurance_clause`: "화재보험 등 보험 약관의 보장 여부를 InsuQ(외부 보험 파트너)에 문의한다. 정비사가 설비 고장·손해의 보험 보장 여부를 명시적으로 물을 때만 호출할 것. MaintQ 매뉴얼 근거가 아니라 외부 파트너의 응답이므로 결과를 그대로 전달하고 추측을 덧붙이지 말 것. 실패 시 확답을 못 얻었다는 사실을 정직하게 알릴 것."
  - `assess_equipment_loan`: "설비를 담보로 한 대출 사전판정을 FinAllQ(외부 금융 파트너, 내부적으로 InsuQ 2차 조회 포함)에 문의한다. 사용자가 설비 담보 대출을 명시적으로 물을 때만 호출할 것. 현재 파트너 쪽 연동이 아직 준비되지 않아 실패 응답이 정상적으로 나올 수 있다 — 실패를 오류로 취급하지 말고 결과를 있는 그대로 전달할 것."

- **`server.py` 등록** (기존 `if TOOLS_PROFILE == "full":` 블록 안, 다른 확장 도구들과 같은 자리):
  ```python
  from mcp_server.tools.search_insurance_clause import (  # noqa: E402
      DESCRIPTION as INSURANCE_CLAUSE_DESC,
      search_insurance_clause as _search_insurance_clause,
  )
  from mcp_server.tools.assess_equipment_loan import (  # noqa: E402
      DESCRIPTION as EQUIPMENT_LOAN_DESC,
      assess_equipment_loan as _assess_equipment_loan,
  )
  ...
  @mcp.tool(description=INSURANCE_CLAUSE_DESC)
  def search_insurance_clause(question: str) -> dict:
      return _search_insurance_clause(question=question)

  @mcp.tool(description=EQUIPMENT_LOAN_DESC)
  def assess_equipment_loan(
      loan_amount: float, purpose: str, collateral_building_id: str
  ) -> dict:
      return _assess_equipment_loan(
          loan_amount=loan_amount, purpose=purpose, collateral_building_id=collateral_building_id
      )
  ```
  파일 상단 docstring(6~20행)의 "확장 11종" → "확장 13종", 목록에 두 줄 추가.

  `.env.example` 에 `MAINTQ_MCP` 절 근처 추가:
  ```
  # ── MCP → 백엔드 REST (A2A 도구 2종 전용, Sprint 16)
  # search_insurance_clause·assess_equipment_loan 이 mcp_server 프로세스에서 backend REST
  # (/api/a2a/lookup-clause·/api/a2a/assess-loan)를 HTTP 로 호출할 때 쓰는 주소.
  # backend.a2a 를 직접 import 하지 않는다(D15·D93) — 이게 그 대신 쓰는 네트워크 경로다.
  # 기본: http://localhost:8000
  MAINTQ_BACKEND_BASE_URL=
  ```

- **엣지 케이스**:
  - `MAINTQ_BACKEND_BASE_URL` 미설정 → `http://localhost:8000` 폴백(백엔드·MCP 서브프로세스가 로컬 co-location 이라는 기존 전제와 일치, `MAINTQ_MCP_AUTOSTART` 기본 동작과 동일한 가정).
  - `loan_amount <= 0` / `purpose` 공백 / `collateral_building_id` 공백 → `status:"error", reason:"invalid_input"`.
  - 백엔드가 502/504 를 돌려주는 경우가 **정상 경로**다(status.html 실측 — assess-loan 은 현재 로컬·배포 어디서도 200 을 못 본다). 테스트는 이 경로를 실패로 취급하지 않고 "정직하게 `status:error` 를 반환하는지"를 검증 대상으로 삼는다.

- **지켜야 할 결정**: D15·D93(mcp_server 는 `backend.a2a`·`MAINTQ_A2A_*` 를 참조하지 않는다 — 이번 도구는 `MAINTQ_BACKEND_BASE_URL` 이라는 **다른 이름**의 env 를 쓴다. `MAINTQ_A2A_` 접두어를 쓰면 `spikes/a2a_identity_contract.py ⑮` 가 FAIL 한다 — 반드시 이 이름 그대로 쓸 것) · D9(실패는 status) · D80(필수 파라미터 기본값 없음) · D69·D88(이 2종은 `full` 프로파일에만 등록 — `core` 에 넣지 않는다. **리스크**: `core` 로 넣으면 `eval/testset.json` 20문항 채점에 영향을 줄 수 있고 D88 의 게이트(`eval/run_eval.py`: `tools > CORE_TOOL_COUNT(=7)` 이거나 `tools_profile != "core"` 면 위반, tool-builder 실측 확인 — `tools==7` 이 아니라 `tools>7`)를 깨 평가 자체가 `SystemExit(2)` 로 죽는다. `full` 배치가 유일하게 안전한 선택이다)

- **DoD**:
  - `uv run --with pytest python -m pytest mcp_server/tools/test_search_insurance_clause.py mcp_server/tools/test_assess_equipment_loan.py -q` 전건 통과. `httpx.post` 를 `monkeypatch` 로 모킹해 200/502/타임아웃/`input-required`/`rejected` 5경로 전부 커버.
  - `MAINTQ_TOOLS_PROFILE=full uv run python mcp_server/server.py` 기동 시 예외 없음(수동 확인, Ctrl+C 로 종료)
  - `uv run python spikes/a2a_identity_contract.py` 의 ⑮(`mcp_server/**` 에 `backend.a2a`·`MAINTQ_A2A_*`·`partner_links` 참조 0건)가 **여전히 0건**으로 통과 — 새 파일 2개가 스캔 대상에 자동 포함된다(글롭 기반이므로 코드 변경 불필요, 실행만으로 검증)

---

## Stage 2

#### MQ-1604 — 에이전트 루프·프롬프트 배선

- **복무 시나리오**: MQ-1603 과 동일(신규 InsuQ 약관조회 / 확장 S8·2026-08-23 지도 기준 S4 FinAllQ 담보대출)
- **변경 파일**:
  - `backend/agent/loop.py` (수정)
  - `backend/agent/mcp_client.py` (수정 — `summarize_result`)
  - `backend/agent/prompts.py` (수정 — `_EXT_TOOL_LINES`·`EXT_RULES`·`_EXT_RULE_TOOLS`)

- **인터페이스**:

  `loop.py` 안, `for tu in pending:` 루프의 `trace.tool_result(...)` 호출 직전에 상수 + 추출 로직 추가:
  ```python
  _A2A_CHAIN_TOOLS = ("search_insurance_clause", "assess_equipment_loan")
  ...
  a2a_chain_id = (
      payload.get("request_chain_id") if tu.name in _A2A_CHAIN_TOOLS else None
  )
  if isinstance(a2a_chain_id, str) and not a2a_chain_id:
      a2a_chain_id = None  # 빈 문자열은 "없음"과 같게 다룬다 (MQ-1601 엣지케이스 방지)
  yield trace.tool_result(
      tu.name, status, summary, round(elapsed, 3),
      pages=pages, parts=parts, tool_payload=payload,
      a2a_chain_id=a2a_chain_id,
  )
  ```

  `mcp_client.py::summarize_result()` 에 두 분기 추가 (기존 `if tool == "create_po_draft":` 근처, 확장 도구 분기들 사이):
  ```python
  if tool == "search_insurance_clause":
      bits = []
      if result.get("verdict"):
          bits.append(f"판정 {result['verdict']}")
      evidence = result.get("evidence") or []
      if evidence:
          bits.append(f"근거 {len(evidence)}건")
      return "InsuQ 약관 조회 · " + " · ".join(bits) if bits else "InsuQ 약관 조회 완료"

  if tool == "assess_equipment_loan":
      verdict = result.get("verdict") or result.get("skill_status") or "?"
      return f"FinAllQ 대출 사전판정 · {verdict}"
  ```
  (status가 `error`/`not_found`/`empty` 인 경우는 함수 상단의 기존 공통 분기가 이미 처리 — 이 두 도구는 `not_found`/`empty` 를 반환하지 않으므로 실질적으로 `error`/성공 두 갈래만 탄다.)

  `prompts.py::_EXT_TOOL_LINES` 에 두 줄 추가:
  ```python
  "search_insurance_clause": "- `search_insurance_clause` — 보험 약관 보장 여부를 InsuQ(외부 파트너)에 문의 (MaintQ 매뉴얼이 아니다)",
  "assess_equipment_loan": "- `assess_equipment_loan` — 설비 담보 대출 사전판정을 FinAllQ(외부 파트너)에 문의 (2차홉 InsuQ 미비로 현재 실패가 정상)",
  ```

  `EXT_RULES` 튜플 끝에 규칙 18·19 추가, `_EXT_RULE_TOOLS` 에 대응 튜플 추가(순서 정렬 필수 — `assert len(EXT_RULES) == len(_EXT_RULE_TOOLS)` 가 이미 있다):
  ```python
  # 18 — 보험 약관 조회는 외부 응답 그대로 (신규, D112)
  "**보험 약관 조회는 사용자가 명시적으로 물을 때만, InsuQ 응답을 그대로 인용한다.**"
  " `search_insurance_clause` 는 MaintQ 매뉴얼이 아니라 외부 보험 파트너(InsuQ)의 A2A 응답이다 —"
  " `lookup_error_code`·`rag_search_manual` 의 매뉴얼 인용과 절대 섞지 마라. 결과의 `answer`·"
  "`evidence` 를 그대로 전달하고 네 해석을 덧붙이지 마라. `status:\"error\"` 면 InsuQ 로부터 확답을"
  " 얻지 못한 것이다 — 보장 여부를 추측해서 답하지 말고 확인이 안 됐다고 말한다.",
  # 19 — 설비 담보 대출 사전판정은 실패가 정상 경로 (S8, D112)
  "**설비 담보 대출 사전판정은 FinAllQ 응답 그대로, 실패를 정상 경로로 안내한다.**"
  " `assess_equipment_loan` 은 FinAllQ(→ 내부 2차홉 InsuQ) A2A 응답이다. 현재 이 연동은 파트너 쪽"
  " 2차홉이 아직 준비되지 않아 `status:\"error\"`(`upstream_unavailable` 등)로 끝나는 것이 정상이다"
  " — 실패를 네 판단으로 메우지 말고 결과의 `message` 를 그대로 전하며 지금은 확인할 수 없다고"
  " 안내한다. 성공 응답을 받으면 필드를 지어내지 말고 있는 값만 전한다.",
  ```
  ```python
  _EXT_RULE_TOOLS = (
      ...,  # 기존 6개
      ("search_insurance_clause",),
      ("assess_equipment_loan",),
  )
  ```

- **핵심 로직**: 순수 배관. `_pages_from`/`_parts_from` 은 **손대지 않는다** — 두 함수 다 매칭 안 되는 도구명에 대해 이미 `[]` 를 반환하므로 이 두 도구는 자동으로 근거 페이지 0건·특정 부품 0건으로 처리된다(의도된 동작 — 외부 파트너 응답에 MaintQ 매뉴얼 페이지가 있을 리 없다).

- **엣지 케이스**:
  - `_pages_from`/`_parts_from` 에 이 두 도구에 대한 분기를 **추가하지 말 것** — 추가하면 존재하지 않는 매뉴얼 페이지를 인용 후보로 만들어 D26·D32 계약(물리 페이지는 항상 MaintQ 매뉴얼 것)을 깨는 잠재적 환각 경로가 열린다. (명시적 금지 사항 — 리뷰 시 확인)
  - `loop.py::_emit_po_card`/citation 발행 분기(`if st.pages and st.model...`) 는 이 두 도구 호출만으로는 **절대 발화하지 않는다** — `pages` 가 항상 `[]` 이기 때문. 별도 방어 코드 불필요, 자연히 안전.

- **지켜야 할 결정**: D69(확장 규칙은 도구가 실제 등록됐을 때만 붙는다 — `EXT_RULES`/`_EXT_RULE_TOOLS` 패턴이 이미 이걸 보장, 새 코드 불필요) · D26·D32(물리 페이지 계약은 MaintQ 매뉴얼 전용 — 이 두 도구가 침범하지 않는다) · D76(구조 보존 — summarize 는 있는 값만 쓴다)

- **DoD**:
  - `uv run --with pytest python -m pytest data/rules/test_rules.py backend/agent/test_llm_cache.py data/external/test_elice_docvision.py -q` 무회귀
  - `python -c "from backend.agent.prompts import EXT_RULES, _EXT_RULE_TOOLS; assert len(EXT_RULES) == len(_EXT_RULE_TOOLS) == 8"` 통과
  - 수동: `MAINTQ_TOOLS_PROFILE=full` 로 백엔드+MCP 기동 후 `POST /api/chat` 에 "화재로 인한 인버터 손해가 보험으로 보장되나요?" 를 보내 `search_insurance_clause` 가 호출되고 SSE `tool_result` 에 `a2a_chain_id` 가 실리는지 확인 (MAINTQ_A2A_INSUQ_BASE_URL 이 미기동 로컬 어댑터를 가리켜 `upstream_unavailable` 로 끝나도 무방 — `a2a_chain_id` 유무만 확인하면 된다). **확정(tool-builder 현실성 평가로 재검토 불필요 — `routers/a2a.py` 의 실패 3분기는 전부 `HTTPException(detail=...)` 를 raise하고 FastAPI 의 `HTTPException.detail` 은 평문 문자열이라 애초에 구조화된 `request_chain_id` 필드를 실을 수 없다): 실패 시 `a2a_chain_id` 가 없는 것이 설계 의도다.** MQ-1602 의 chain_id 강제 주입은 성공 분기에만 있으면 충분하고 재작업하지 않는다. MQ-1606(`chainId: null` 처리)·MQ-1607(`status !== "ok" || chainId === null` 일 때 이력 fetch 없이 SSE 의 `message`/`reason` 만으로 렌더)이 이미 이 전제로 일관되게 설계돼 있다.

---

#### MQ-1605 — 프론트 API 계층

- **복무 시나리오**: 위와 동일 (프론트 데이터 계층)
- **변경 파일**:
  - `frontend/lib/api.ts` (수정 — `ApiA2aHistoryItem` 인터페이스 + `getA2aHistory()`)
  - `frontend/lib/a2a.ts` (신규 — 표시 규칙, `lib/riskGrade.ts` 와 동일 패턴)

- **인터페이스**:

  `lib/api.ts` 끝에 추가 (기존 `ApiRiskGrade`/`getBuildingRiskGrade` 바로 아래 섹션과 같은 스타일):
  ```ts
  /** `GET /api/a2a/history` 항목 하나 (D114). `request`/`response` 는 파트너 스킬마다 모양이
   * 달라 좁히지 않는다 — 소비자가 필요한 키만 골라 읽는다(`ApiMetrics` 와 같은 태도). */
  export interface ApiA2aHistoryItem {
    request_chain_id: string;
    skill: string;
    session_id: string;
    status: string | null;
    request: Record<string, unknown> | null;
    response: Record<string, unknown> | null;
    ts: string;
  }

  export interface ApiA2aHistory {
    count: number;
    items: ApiA2aHistoryItem[];
  }

  export const getA2aHistory = (
    role: Role,
    params?: { skill?: string; poId?: string; buildingId?: string; chainId?: string; limit?: number }
  ) => {
    const q = new URLSearchParams();
    if (params?.skill) q.set("skill", params.skill);
    if (params?.poId) q.set("po_id", params.poId);
    if (params?.buildingId) q.set("building_id", params.buildingId);
    if (params?.chainId) q.set("chain_id", params.chainId);
    if (params?.limit !== undefined) q.set("limit", String(params.limit));
    const qs = q.toString();
    return apiFetch<ApiA2aHistory>(`/api/a2a/history${qs ? `?${qs}` : ""}`, role);
  };
  ```

  `frontend/lib/a2a.ts` (전체 신규 파일):
  ```ts
  /**
   * A2A 이력(`GET /api/a2a/history`) 표시 규칙 (MQ-1605, D114).
   *
   * ⛔ React 를 import 하지 않는다 — `ui_honesty` L1 이 단독 tsc 로 이 파일을 검증한다.
   * ⛔ 경로 별칭(`@/…`)도 쓰지 않는다.
   */

  export type Tone = "ok" | "warn" | "error" | "unknown";

  export interface SkillView {
    label: string;
  }

  const SKILL_VIEW: Record<string, SkillView> = {
    "request-withdrawal": { label: "FinAllQ · 출금요청" },
    "lookup-clause": { label: "InsuQ · 약관조회" },
    "assess-loan": { label: "FinAllQ · 담보대출 사전판정" },
  };

  /** 맵 밖 스킬명도 원문을 보존한다 (D87 — 지어내지 않는다). */
  export function skillView(skill: string): SkillView {
    return SKILL_VIEW[skill] ?? { label: `미상(${skill})` };
  }

  /** `record_a2a_trace` 의 status 어휘(ok|timeout|unavailable|error) → 표시 톤. */
  export function a2aStatusTone(status: string | null | undefined): Tone {
    if (status === "ok") return "ok";
    if (status === "timeout" || status === "unavailable" || status === "error") return "error";
    return "unknown";
  }
  ```

- **핵심 로직**: 순수 데이터 계층 — 렌더링 로직 없음.

- **엣지 케이스**: `getA2aHistory` 파라미터 전부 생략 시 쿼리스트링 없이 `GET /api/a2a/history` 호출(전체 이력) — MQ-1610 이 이 형태로 쓴다.

- **지켜야 할 결정**: D87(상태 문자열 직접 비교 대신 뷰 헬퍼 경유 — `a2aStatusTone`/`skillView` 가 이후 모든 프론트 태스크의 **유일한** 색상·라벨 판단 지점이어야 한다) · L1 게이트(React·`@/` 미사용)

- **DoD**:
  - `npx tsc --noEmit` 통과
  - `npx tsc --noEmit frontend/lib/a2a.ts --strict --target es2020 --moduleResolution bundler` (또는 저장소의 L1 단독 컴파일 커맨드와 동일한 방식 — `spikes/ui_honesty_contract.py` 의 L1 실행 커맨드를 그대로 재사용해 확인) 가 별도 별칭·React 없이 단독 컴파일되는지 확인

---

#### MQ-1606 — 프론트 채팅 타입·리듀서

- **복무 시나리오**: 신규(InsuQ) / 확장 S8·S4(FinAllQ) — 채팅 실시간 표시의 데이터 배관
- **변경 파일**:
  - `frontend/lib/types.ts` (수정 — `ChatItem` 유니온에 `a2a_result` 추가)
  - `frontend/lib/chatStream.ts` (수정 — `onToolResult` 에 분기 추가)

- **인터페이스**:

  `types.ts::ChatItem` 유니온에 추가:
  ```ts
  | {
      kind: "a2a_result";
      id: string;
      skill: "search_insurance_clause" | "assess_equipment_loan";
      chainId: string | null;
      status: string;
    }
  ```
  (`chainId` 를 nullable 로 둔 이유는 아래 엣지 케이스 참조.)

  `chatStream.ts::onToolResult()` 안, 기존 `lookup_error_code` 분기 **바로 아래**에 추가:
  ```ts
  const A2A_TOOLS = ["search_insurance_clause", "assess_equipment_loan"] as const;
  if ((A2A_TOOLS as readonly string[]).includes(tool)) {
    const chainId = typeof data.a2a_chain_id === "string" ? data.a2a_chain_id : null;
    const status = typeof data.status === "string" ? data.status : "error";
    const id = nextId(_ctx);
    items = [
      ...items,
      {
        kind: "a2a_result",
        id,
        skill: tool as "search_insurance_clause" | "assess_equipment_loan",
        chainId,
        status,
      },
    ];
    _ctx = { ..._ctx, itemSeq: _ctx.itemSeq + 1 };
  }
  ```

- **핵심 로직**: `tool_result` 이벤트가 두 도구 이름 중 하나면 얇은(thin) `a2a_result` 아이템을 하나 push 한다 — 실제 구조화 내용(약관 근거·판정)은 여기서 담지 않는다. 렌더링 컴포넌트(MQ-1607)가 `chainId` 로 `GET /api/a2a/history` 를 별도로 fetch 해 채운다. **`reduceChatEvent` 는 순수 함수로 남는다** — 여기서 fetch 하지 않는다(파일 docstring 의 "React 를 import 하지 않는다" 제약과 같은 이유로, 비동기 부수효과는 렌더 컴포넌트 몫).

- **엣지 케이스**:
  - `data.a2a_chain_id` 가 없다(도구가 `status:"error"` 로 끝나 MQ-1604 가 `None` 을 넘긴 경우, 특히 `assess_equipment_loan` 은 이게 **기본 경로**다) → `chainId: null`. 렌더 컴포넌트는 이때 이력 fetch 를 **하지 않고** `status` 만으로 렌더한다(MQ-1607 의 명시 사항).
  - `types.ts` 의 `ChatItem` 은 discriminated union 이라 `ChatThread.tsx` 의 `switch` 문이 새 case 없이는 TS 컴파일 경고가 날 수 있다 — 이 파일 자체는 `case` 를 추가하지 않는다(그건 MQ-1607 소관), 컴파일 경고는 MQ-1607 완료 시점에 해소된다는 것을 알고 진행한다(이 태스크 단독으로는 `tsc --noEmit` 이 `ChatThread.tsx` 에서 "not all code paths return a value" 류 경고를 낼 수 있음 — TypeScript 의 기본 `switch` 완전성 검사는 `noImplicitReturns`/`strict` 설정에 따라 다르므로, 만약 즉시 컴파일 에러가 난다면 MQ-1606·MQ-1607 을 하나의 커밋으로 묶어도 무방하다는 점을 tool-builder 재량으로 남긴다).

- **지켜야 할 결정**: D22(block 이 아니라 기존 `tool_result` 이벤트를 그대로 씀 — 새 이벤트 타입 아님) · 파일 docstring 의 순수 리듀서 제약(React 미import, fetch 없음)

- **DoD**:
  - `npx tsc --noEmit` (경고 수준은 위 엣지 케이스 참고, MQ-1607 과 함께 봐도 됨)
  - 단위 확인: `reduceChatEvent` 에 `tool_result` 이벤트(`{tool:"search_insurance_clause", status:"ok", summary:"...", elapsed:0.4, a2a_chain_id:"CHAIN-X"}`) 를 흘렸을 때 `state.items` 마지막 원소가 `{kind:"a2a_result", chainId:"CHAIN-X", status:"ok", skill:"search_insurance_clause"}` 형태인지 콘솔 스니펫으로 수동 확인(정식 테스트 러너가 없는 프론트 — 기존 관례와 동일)

---

## Stage 3

#### MQ-1607 — 채팅 실시간 A2A 결과 카드

- **복무 시나리오**: 신규(InsuQ 약관조회, 정비사 채팅) / 확장 S8·S4(FinAllQ 담보대출)
- **변경 파일**:
  - `frontend/components/chat/A2aResultCard.tsx` (신규)
  - `frontend/components/chat/ChatThread.tsx` (수정 — `switch` 에 `case "a2a_result":` 추가)

- **인터페이스**:
  ```tsx
  // A2aResultCard.tsx
  "use client";
  export function A2aResultCard({
    skill,
    chainId,
    status,
  }: {
    skill: "search_insurance_clause" | "assess_equipment_loan";
    chainId: string | null;
    status: string;
  }): JSX.Element { ... }
  ```
  `ChatThread.tsx` 에 추가:
  ```tsx
  case "a2a_result":
    return (
      <A2aResultCard key={item.id} skill={item.skill} chainId={item.chainId} status={item.status} />
    );
  ```

- **핵심 로직**:
  1. `status !== "ok"` 또는 `chainId === null` → **이력 fetch 를 하지 않는다.** 대신 고정 문구 카드를 그린다: `skill === "search_insurance_clause"` 면 "InsuQ 로부터 확답을 받지 못했습니다", `assess_equipment_loan` 이면 "FinAllQ 사전판정을 지금은 확인할 수 없습니다 — 파트너 연동 준비 중" (status.html 실측 반영 — 이게 정상 경로임을 톤에서도 드러낸다. `error`/`warn` 톤이 아니라 `unknown`/중립 톤을 쓴다: 이건 MaintQ 의 결함이 아니라 파트너 쪽 상태이기 때문).
  2. `status === "ok" && chainId` → `useEffect` 로 `getA2aHistory("technician", { chainId })` 를 1회 호출. 로딩 중엔 "InsuQ 응답 확인 중…" (또는 FinAllQ). 응답 `items[0]` 이 없으면 "상세를 불러오지 못했습니다" 폴백.
  3. `items[0].skill === "lookup-clause"` → `response.answer`(문단), `response.verdict`(뱃지, `a2aStatusTone` 이 아니라 원문 그대로 텍스트 표시 — verdict 어휘("covered" 등)는 InsuQ 소관이라 MaintQ 가 색으로 판단하지 않는다), `response.evidence`(문자열 배열 → `<ul>`).
  4. `items[0].skill === "assess-loan"` → `response` 의 **알려진 메타 키(`status`,`request_chain_id`,`task_id`) 를 제외한 나머지 키**를 `label: value` 목록으로 렌더(구조는 모르지만 지어내지 않고 있는 값만 나열 — D76 정신). `response` 가 비어 있으면 "FinAllQ 응답 형식이 아직 확인되지 않았습니다" 안내.

- **엣지 케이스**:
  - fetch 실패(네트워크) → catch 해서 "상세를 불러오지 못했습니다 — 백엔드에 연결하지 못했습니다" (기존 `RiskGradeGrid` 의 `listFailure` 패턴과 동일 톤)
  - `evidence` 가 배열이 아니거나 없음 → 목록 섹션 자체를 렌더하지 않는다(빈 `<ul>` 대신 아예 생략)

- **지켜야 할 결정**: D87(색상은 `a2aStatusTone`/`skillView` 경유만 — `status`/`verdict` 문자열 직접 비교 금지) · D9(도구 실패를 있는 그대로 보여준다, 추측 금지)

- **DoD**:
  - `npx tsc --noEmit` 통과
  - `npx next build` 통과 (18→18 라우트 유지 — 이 태스크는 새 라우트를 안 만든다)
  - 수동: `?replay=` 없이 실 백엔드로 InsuQ 관련 질문을 채팅에 입력 → 카드가 로딩→(성공 또는 실패) 순서로 렌더되는지 확인

---

#### MQ-1608 — PO 상세 출금요청 상태 부착

- **복무 시나리오**: 확장 S5(2026-08-14 스냅샷)/S1(2026-08-23 지도) — request-withdrawal
- **변경 파일**:
  - `frontend/components/queue/WithdrawalStatusPanel.tsx` (신규)
  - `frontend/components/queue/PoDetail.tsx` (수정)

- **인터페이스**:
  ```tsx
  // WithdrawalStatusPanel.tsx
  "use client";
  export function WithdrawalStatusPanel({ poId }: { poId: string }): JSX.Element | null { ... }
  ```
  `PoDetail.tsx` 의 `<DecisionBar .../>` 바로 위(또는 아래, tool-builder 재량 — 승인/반려 버튼과 겹치지 않는 위치)에 추가:
  ```tsx
  <WithdrawalStatusPanel poId={entry.id} />
  ```

- **핵심 로직**:
  1. 마운트 시 `getA2aHistory("manager", { poId, skill: "request-withdrawal" })` 호출.
  2. `items.length === 0` → **아무것도 렌더하지 않는다**(`return null`) — 아직 승인 전이거나 `partner_links` 미연결이라 `dispatch_a2a_withdrawal_request` 가 아예 호출 안 된 정상 상태(services/po.py 의 `company_id` 없으면 `None` 반환하는 경로)를 실패처럼 보이게 하지 않는다.
  3. `items.length > 0` → 가장 최신(`items[0]`, 이미 ts desc 정렬) 항목의 `status`(`a2aStatusTone` 경유 색)·`response.detail`(있으면, request-withdrawal 응답의 사람이 읽는 안내문)·`response.task_id`(있으면) 를 작은 카드로 표시.

- **엣지 케이스**: `entry.kind !== "po"` 인 경로에서는 애초에 `PoDetail` 자체가 렌더 안 되므로(부모의 `kind` 분기, 기존 구조) 별도 방어 불필요.

- **지켜야 할 결정**: D87(`a2aStatusTone` 경유) · D18("승인은 채팅 밖 큐 화면" — 이 패널은 읽기 전용, 승인 로직에 개입하지 않는다)

- **DoD**:
  - `npx tsc --noEmit` · `npx next build` 통과
  - 수동: 재생 모드(`?replay=s1`)로 만들어진 `PO-0117` 처럼 `partner_links` 가 `NOT_LINKED`(`BLD-D` 대조군)인 자산 기반 PO 는 패널이 안 뜨는지, `LINKED` 자산 기반 approved PO 는 상태가 뜨는지 확인

---

#### MQ-1609 — 건물 위험등급 화면에 담보대출 상담 이력 패널

- **복무 시나리오**: 확장 S8(2026-08-14 스냅샷)/S4(2026-08-23 지도) — assess-loan
- **변경 파일**:
  - `frontend/components/asset/LoanAssessmentHistory.tsx` (신규)
  - `frontend/app/(console)/manager/risk-grade/page.tsx` (수정)

- **인터페이스**:
  ```tsx
  // LoanAssessmentHistory.tsx
  "use client";
  export function LoanAssessmentHistory(): JSX.Element { ... }
  ```
  `risk-grade/page.tsx` 의 `<RiskGradeGrid />` 아래에 추가:
  ```tsx
  <div style={sx("margin-top:20px")}>
    <LoanAssessmentHistory />
  </div>
  ```

- **핵심 로직**: 건물별 N+1 조회 대신 **한 번에** `getA2aHistory("manager", { skill: "assess-loan", limit: 20 })` 호출 후 테이블/리스트로 렌더 — 컬럼: `building_id`(request.collateral_building_id) · `loan_amount`(request.loan_amount, 있으면 천단위 콤마) · `status`(`a2aStatusTone`) · `ts`. `items.length === 0` 이면 "아직 상담 이력이 없습니다" 안내(에러 아님 — 현재 이 스킬은 성공 케이스가 없으므로 이게 기본 상태).

- **엣지 케이스**: `request` 가 `null`이거나 `loan_amount`/`collateral_building_id` 키가 없어도 행 자체는 그리되 해당 셀만 "—" 로 표시(지어내지 않는다).

- **지켜야 할 결정**: D87 · D64(점수·금액을 별도 랭킹/진행바로 가공하지 않는다 — `RiskGradeGrid` 선례와 같은 톤 유지, 단순 테이블)

- **DoD**:
  - `npx tsc --noEmit` · `npx next build` 통과 (라우트 수 무변화 — 기존 페이지 수정)
  - 수동: `/manager/risk-grade` 접속 시 그리드 아래 새 섹션이 로딩→(빈 상태 또는 목록) 렌더되는지 확인

---

#### MQ-1610 — 통합 A2A 이력 페이지 `/manager/a2a`

- **복무 시나리오**: 3종 전체(request-withdrawal·lookup-clause·assess-loan) — "통합 이력" 요구사항 자체
- **변경 파일**:
  - `frontend/components/screens/A2aHistoryScreen.tsx` (신규)
  - `frontend/app/(console)/manager/a2a/page.tsx` (신규)

- **인터페이스**:
  ```tsx
  // A2aHistoryScreen.tsx
  "use client";
  export function A2aHistoryScreen(): JSX.Element { ... }
  ```
  ```tsx
  // app/(console)/manager/a2a/page.tsx
  import { A2aHistoryScreen } from "@/components/screens/A2aHistoryScreen";
  export default function ManagerA2aPage() {
    return <A2aHistoryScreen />;
  }
  ```
  `manager/risk-grade/page.tsx` 와 동일한 `ConsoleFrame`/`ConsoleHeader` 셸 재사용(기존 관례).

- **핵심 로직**: `getA2aHistory("manager", { limit: 100 })`(필터 없음 — 3종 전부) 를 마운트 시 1회 호출, `skillView(item.skill).label` 로 스킬 뱃지, `a2aStatusTone(item.status)` 로 상태색, `ts` 내림차순(백엔드가 이미 정렬해서 주지만 방어적으로 클라도 재정렬하지 않는다 — 서버 정렬을 신뢰). 각 행은 `<details>`(기존 `RiskGradeGrid` 의 `notConsidered` 패턴)로 펼치면 `request`/`response` 원문을 `<pre>` 로 JSON 표시(감사 용도 — 구조화 렌더를 매 스킬마다 새로 만들지 않고, 통합 페이지는 "원문을 볼 수 있다"에 집중한다. 맥락별 예쁜 렌더는 MQ-1607/1608/1609 가 이미 담당).

- **엣지 케이스**: `count === 0` → "아직 A2A 호출 이력이 없습니다".

- **지켜야 할 결정**: D87 · D76-2(이 페이지가 여는 원문은 `read_trace` 가 아니라 D114 의 전용 엔드포인트를 통해서만 — 이 페이지 자체는 새 백엔드 로직을 추가하지 않는다, MQ-1602 산출물을 그대로 소비)

- **DoD**:
  - `npx tsc --noEmit` 통과
  - `npx next build` 통과 — **라우트 18→19 로 증가**(신규 페이지 1개, `find frontend/app -name page.tsx` 기준은 17→18). 이 숫자를 손으로 미리 적지 말고 빌드 출력에서 실측할 것(CLAUDE.md 의 반복 경고 — 17/18 두 셈법 혼동 주의)
  - 수동: `/manager/a2a` 접속 시 표 렌더 확인

---

## Stage 4

#### MQ-1611 — 기존 계약 스파이크 4종 카운트 갱신

- **복무 시나리오**: 인프라(회귀 무결성) — 특정 S 없음
- **변경 파일**: `spikes/prompt_rules.py`, `spikes/tools_profile_contract.py`, `spikes/s10_smoke.py`, `spikes/ui_honesty_contract.py`

- **핵심 로직 (파일별)**:

  1. **`spikes/prompt_rules.py`**:
     - `len(EXT_RULES) == 6` → `== 8`, `len(EXT_TOOLS) == 11` → `== 13` (두 곳, ⑰ 검사와 그 근처)
     - `"사용 가능한 도구 (18종)"` → `"사용 가능한 도구 (20종)"`
     - ⑲ 근처 `numbered = all(... for n in (12,13,14,15,16,17))` → `(12,13,14,15,16,17,18,19)` 로 확장, 해당 주석("규칙 12=D59… / 17=D101·D102")에 "18=신규(D112) / 19=S8·D112" 추가
     - ⑳(있다면 partial 목록) `present == {12: False, ..., 17: False}` 류 딕셔너리에 `18: False, 19: False` 추가
     - ㉔(`prompts.EXT_TOOLS == server.py full 블록 실등록`) 는 코드 변경 불필요 — `EXT_TOOLS` 가 자동으로 늘어난 값을 그대로 비교하므로 실행만 하면 통과

  2. **`spikes/tools_profile_contract.py`**:
     - `CORE_TOOLS`/`EXT_TOOLS` 하드코딩 set 에 `"search_insurance_clause"`, `"assess_equipment_loan"` 추가
     - `"18종"`(주석·assert 메시지 2곳) → `"20종"`

  3. **`spikes/s10_smoke.py`**:
     - `EXPECTED_TOOLS_FULL = 18` → `= 20`
     - 주석 "도구 총수 = 코어 7 + 확장 11" → "코어 7 + 확장 13"

  4. **`spikes/ui_honesty_contract.py`**:
     - `L2_EXTRA = ("components/queue/SignBar.tsx", "components/queue/RepairDetail.tsx")` → 튜플에 `"components/queue/WithdrawalStatusPanel.tsx"` 추가(`components/queue/*.tsx` 글롭이 `Decision*.tsx` 접두어만 잡아 자동 편입되지 않는다 — `RepairDetail.tsx` 선례와 정확히 같은 사유)
     - `L2_FILES_FLOOR = 36` → `39` (신규 파일 3개: `components/asset/LoanAssessmentHistory.tsx` — `components/asset/*.tsx` 글롭 자동 편입, `app/(console)/manager/a2a/page.tsx` — `app/(console)/**/*.tsx` 글롭 자동 편입, `components/queue/WithdrawalStatusPanel.tsx` — 위에서 `L2_EXTRA` 로 수동 편입. `components/chat/A2aResultCard.tsx` 는 `L2_GLOBS` 에 `components/chat/*.tsx` 자체가 없으므로 편입 안 됨 — 다른 chat 컴포넌트들과 동일)
     - **L1** 에 `lib/a2a.ts` 추가 — `riskGrade.ts`/`deadlines.ts` 선례를 그대로 복제: 파일 상단 상수부에 `A2A_TS = FRONTEND / "lib" / "a2a.ts"` 추가, `constraint_gate("C9", "C10", "a2a.ts", A2A_TS, " (MQ-1605)")` 호출 추가(기존 `constraint_gate("C7", "C8", "riskGrade.ts", ...)` 바로 아래)

- **엣지 케이스**: 이 태스크는 **카운트·목록 상수만** 바꾼다 — 검사 로직 자체(어떻게 세는지)는 건드리지 않는다. 만약 실행 결과가 기대와 다르면(예: L2 파일 수가 39 가 아니라 다른 값) 상수를 실측값으로 맞추고 그 차이를 MQ-1614 의 CLAUDE.md 기록에 설명과 함께 남긴다 — 이 스펙의 숫자는 **설계 시점 추정**이지 실행 결과가 아니다.

- **지켜야 할 결정**: CLAUDE.md 의 "부재 검사엔 반드시 liveness 앵커" 원칙 — 이 태스크는 앵커 로직을 새로 만들지 않고 기존 패턴(자동 글롭 + 수동 `L2_EXTRA`/`constraint_gate`)을 그대로 복제한다

- **DoD**:
  - `uv run python spikes/prompt_rules.py` · `uv run python spikes/tools_profile_contract.py` · `uv run python spikes/s10_smoke.py` · `uv run python spikes/ui_honesty_contract.py` **개별 실행 전건 통과**(`s10_smoke.py` 는 실 uvicorn+MCP 를 띄우므로 타 프로세스와 포트 충돌 없이 단독 실행)
  - 각 스위트의 최종 통과 건수를 **출력 그대로** 캡처해 MQ-1614 로 전달(손계산 금지)

---

#### MQ-1612 — 문서 갱신

- **복무 시나리오**: 인프라(문서 정합성)
- **변경 파일**: `docs/04_MCP_TOOLS.md`, `docs/06_REPO_API.md`, `docs/13_DEPLOYMENT.md`, `docs/00_MVP_SCOPE.md`, `docs/README.md`, `docs/07_BACKLOG.md`(카운트 문구 1줄만)

- **핵심 로직 (파일별 체크리스트)**:

  1. **`docs/04_MCP_TOOLS.md`**:
     - 헤더 프로파일 표(`| full | 코어 7 + 확장 11 = 18종 (§1~§18) |`) → `코어 7 + 확장 13 = 20종 (§1~§20)`
     - 새 절 추가: `## 19. search_insurance_clause — InsuQ 약관 보장 여부 조회 (신규, D112)`, `## 20. assess_equipment_loan — FinAllQ 설비 담보 대출 사전판정 (S8, D112)`. 각 절은 기존 §17·§18 형식(입력/출력/핵심 로직/엣지케이스)을 따르되, **이 2종은 mcp_server → backend REST 왕복이라는 새로운 구조**라는 점을 절 서두에 명시(D15 프로세스 분리가 유지되는 방식 — mcp_server 는 여전히 `backend.a2a` 를 모른다, HTTP 로만 이어진다)
     - "확장 11종 reason 색인" 표에 두 도구의 reason 어휘(`question_required`·`timeout`·`backend_unreachable`·`upstream_unavailable`·`no_answer`·`unexpected_status`·`invalid_response`·`a2a_error`·`invalid_input`) 행 추가
     - "설계 결정 기록" 표에 D113·D114 요약 1줄씩 추가(전문은 `10_DECISIONS.md` 참조로 링크)
     - "도구 ↔ 시나리오 매핑" 표에 신규 행 추가: `| 신규 InsuQ 상담 | search_insurance_clause(사용자 명시 질의 시에만) |`, `| S8/S4 FinAllQ 담보대출 | assess_equipment_loan(사용자 명시 질의 시에만, 현재 실패가 정상) |`

  2. **`docs/06_REPO_API.md`**:
     - 상단 disclaimer(3~4행, "A2A 연동은 A2A_CONTRACTS.md 를 보라") 바로 아래에 명확화 문장 추가: "단, `/api/a2a/*` 는 이 레포 **내부** REST 표면(라우터 `backend/routers/a2a.py`)이다 — 외부 스킬 스키마 자체는 여전히 `A2A_CONTRACTS.md`/A2A_Q 레포가 정본이다."
     - 새 §2.9(또는 다음 빈 번호) 로 `POST /api/a2a/lookup-clause` · `POST /api/a2a/assess-loan`(기존, 이번 스프린트 이전 미문서화분 소급 기재) · `GET /api/a2a/history`(신규) 3개 엔드포인트 표 추가
     - 트리 다이어그램 주석(77행) "확장 11종" → "확장 13종"

  3. **`docs/13_DEPLOYMENT.md`**: 158행 "확장 11종" → "확장 13종"

  4. **`docs/00_MVP_SCOPE.md`**: "MCP 도구 코어 7종 ... + 확장 11종(읽기 9 + 쓰기 2, §8~§18...)" → "확장 13종(§8~§20, 읽기 11 + 쓰기 2 — 신규 2종도 읽기 전용)"

  5. **`docs/README.md`**: 진행 상태 절의 "확장 도구 11종 (...11개 이름 나열...)" 표 행에 `search_insurance_clause`·`assess_equipment_loan` 추가하고 "11종" → "13종". "진행 상태" 맨 위 요약 문단에 Sprint 16 한 줄 추가(기존 관례 — Sprint 13·14·15 처럼 "Sprint 16이 D112 재개분의 응답 표시·통합을 닫았다" 형태).

  6. **`docs/07_BACKLOG.md`**: 171행 "코어 7종 / 확장 11종" → "코어 7종 / 확장 13종" (배경 서술 문장 정정일 뿐 — 백로그 항목을 승격하는 게 아니다. 이 줄 외에는 손대지 않는다)

- **엣지 케이스**: `docs/sprints/*.md`·`docs/sessions/*.md`·`docs/status/*.html` 은 **의도적으로 제외**한다 — 이들은 그 시점의 스냅샷을 기록하는 역사적 문서라 사후에 숫자를 소급 정정하지 않는 것이 이 저장소의 관례다(예: `docs/README.md` 안의 "Sprint 8 결과 — 호출부는 미착수" 같은 과거 기록도 그대로 남겨 두고 그 아래에 "현재는 …" 각주를 덧붙이는 방식을 계속 써 왔다).

- **지켜야 할 결정**: CLAUDE.md "MaintQ 문서 진행표기는 자주 낡는다" 메모리 — 손으로 옮겨 적지 말고 각 카운트를 실측(파일 내 절 번호 개수, `grep`) 후 반영

- **DoD**: 위 6개 파일 모두에서 `grep -rn "확장 11종" docs/04_MCP_TOOLS.md docs/06_REPO_API.md docs/13_DEPLOYMENT.md docs/00_MVP_SCOPE.md docs/README.md docs/07_BACKLOG.md` 결과 0건 (`docs/sprints/`·`docs/sessions/`·`docs/status/` 제외 확인 — 이 세 경로는 grep 대상에서 애초에 뺀다)

---

#### MQ-1613 — 신규 스파이크 `a2a_partner_tools_contract`

- **복무 시나리오**: 인프라(신규 계약 고정)
- **변경 파일**: `spikes/a2a_partner_tools_contract.py` (신규)

- **핵심 로직 — 검사 항목**:
  1. `mcp_server/tools/search_insurance_clause.py`·`assess_equipment_loan.py` 소스에 `backend.a2a`·`MAINTQ_A2A_` 문자열이 0건(양성 축: 두 파일이 실제로 `httpx`/`MAINTQ_BACKEND_BASE_URL` 를 참조하는지도 함께 확인 — "그냥 텅 빈 파일이라 0건"인 위양성을 CLAUDE.md 의 liveness 앵커 규칙대로 배제)
  2. `mcp_server/server.py` 의 `full` 블록 소스에 두 도구가 등록돼 있고, `core`(기본) 실행 시 도구 목록에 두 이름이 **없는지**(`MAINTQ_TOOLS_PROFILE` 을 지정하지 않고 실제로 `mcp_server` 를 기동해 `list_tools()` 결과를 확인 — `s10_smoke.py` 가 `full` 만 확인하므로 이 스파이크가 `core` 쪽 부재를 담당해 상호 보완)
  3. `httpx` 모킹으로 `search_insurance_clause("...")` 호출 시 5가지 응답(200/completed, 200/input-required, 502, timeout, 접속거부)에 대해 도구가 반환하는 `status`/`reason` 조합이 스펙과 일치하는지
  4. `backend/sse.py::tool_result()` 가 `a2a_chain_id=None` 일 때 기존 16종 도구와 바이트 동일한 키 집합을 내는지(`{tool,status,summary,elapsed}` 뿐, `pages`/`parts`/`a2a_chain_id` 전부 생략 — D30 회귀 방지)
  5. `GET /api/a2a/history` 왕복 — `record_a2a_trace` 로 3스킬 각 1건씩 심고 스킬·po_id·building_id·chain_id 필터가 각각 정확히 걸리는지(테스트 DB, `MAINTQ_DB` env 임시 지정)

- **엣지 케이스**: 항목 ②는 실제 프로세스 기동이 필요해 Windows 소켓 고갈 이슈(CLAUDE.md 경고)의 영향을 받을 수 있다 — 실패 시 단독 재실행 후 결과를 보고할 것.

- **지켜야 할 결정**: D15·D93(①) · D69·D88(②) · D9(③) · D30(④) · D114(⑤)

- **DoD**: `uv run python spikes/a2a_partner_tools_contract.py` 단독 실행 시 전건 통과(재시도 포함 무방, CLAUDE.md 러너 신뢰성 절차대로 기록)

---

## Stage 5

#### MQ-1614 — 전수 회귀 재실행 + `CLAUDE.md` 기준선 갱신

- **복무 시나리오**: 인프라
- **변경 파일**: `CLAUDE.md`

- **핵심 로직**:
  1. `ls spikes/*.py` 로 스위트 개수 실측(33개 예상 — 기존 32 + `a2a_partner_tools_contract` 1) 후 전수 실행(Windows 소켓 고갈 시 실패 스위트만 단독 재실행, CLAUDE.md 기존 절차 그대로)
  2. `uv run python data/seed.py --with-error-codes` 로 재시드 후 `error_codes` 65(또는 현재 정본 값) 확인 — 이 스프린트는 DB 스키마를 건드리지 않으므로 seed 자가검증 건수는 **무변화 예상**, 실제로 무변화인지 확인만
  3. `uv run --with pytest python -m pytest data/rules/test_rules.py backend/agent/test_llm_cache.py data/external/test_elice_docvision.py -q` 실행 — 이 3파일 합산 기준선도 **무변화 예상**(이 스프린트가 만든 신규 pytest 는 `backend/services/test_a2a_history.py`·`mcp_server/tools/test_*.py` 로 이 3파일 밖이다 — 별도로 기록)
  4. `npx next build` 로 프론트 라우트 수 실측(19 예상)
  5. 위 실측값을 **그대로** CLAUDE.md 의 "실측 기준선" 문단에 새 델타 문단으로 추가(기존 문단들을 지우지 않고 뒤에 이어 붙이는 이 문서의 관례를 따른다) — 형식은 기존 "978→N" 류 델타 서술을 그대로 복제하되 **이번 스프린트가 만든 정확한 차이**(신규 스파이크 1개, 각 기존 스파이크의 실측 증가분, 프론트 라우트 18→19, MCP 도구 18→20)를 근거와 함께 기술한다

- **엣지 케이스**: 실측값이 이 문서의 사전 추정과 다르면(예: `ui_honesty_contract` 최종 합계가 예상과 다름) **실측값을 채택**하고 그 차이를 한 줄로 설명한다 — 이 스프린트 문서(sprint-16.md)의 숫자는 계획 시점 추정이지 정본이 아니다.

- **지켜야 할 결정**: CLAUDE.md 자신의 "재시도가 필요할 수 있다" 절차, "부재 검사 liveness 앵커" 원칙(신규 스파이크가 이 원칙을 지켰는지 이 단계에서 다시 한번 확인)

- **DoD**:
  - 전수 스위트 FAIL 0건(재시도 포함)
  - `CLAUDE.md` 의 회귀 절이 이번 스프린트의 정확한 실측치로 갱신됨
  - `git log --oneline -5` 로 이 스프린트의 커밋들이 `[M4]` 접두어(또는 프로젝트가 실제 쓰는 접두어)로 정리돼 있는지 확인 — 커밋 자체는 `/stage` 워크플로우 소관이라 이 태스크는 검증만 한다

---

# 현실성 평가 (tool-builder, 2026-08-23)

실제 코드(`backend/sse.py`·`backend/agent/trace.py`·`backend/routers/a2a.py`·`backend/a2a/{client,trace,payloads}.py`·`mcp_server/server.py`·`mcp_server/tools/search_inventory.py`·`backend/agent/{loop,mcp_client,prompts}.py`·`spikes/{ui_honesty_contract,a2a_identity_contract}.py`·`eval/run_eval.py`·`docs/{10_DECISIONS,04_MCP_TOOLS,06_REPO_API,13_DEPLOYMENT,07_BACKLOG}.md`·`TODO_직접할일.md`)를 태스크별로 직접 대조했다.

| 스테이지 | TASK | 리스크 | 제안 |
|---------|------|--------|------|
| Stage 2 | MQ-1604 | 경미(문서 품질) — DoD 말미 "발견하면 MQ-1602 로 돌아가 재검토"가 실행 중 발견할 게 아니라 계획 단계에서 이미 답이 나 있었다(`HTTPException.detail` 은 평문 문자열이라 구조화 필드를 못 실음) | ✅ 반영 완료 — DoD를 확정 문장으로 교체, "재검토 불필요" 명시 |
| Stage 1 | MQ-1601·1602·1603 | 없음 — 함수 시그니처·컬럼 존재·env 키 선택(`MAINTQ_A2A_` 밴리스트 회피)·`full` 프로파일 등록 패턴 전부 실측 일치 | 없음 |
| Stage 1~3 전체 | 파일 충돌 | 없음 — 각 스테이지 태스크의 실제 변경 파일 경로 교집합 0건 확인 | 없음 |
| Stage 4 | MQ-1611 | 없음 — `L2_GLOBS`(chat 글롭 없음)·`L2_EXTRA` 수동 등재 관례·`L2_FILES_FLOOR` 산식이 실제 코드와 일치, Stage3 완료 후에만 정확한 숫자가 나온다는 순서 의존성도 타당 | 없음 |
| Stage 1 (D69·D88) | MQ-1603/1604 | 없음(표현만 근사) — 게이트는 `tools==7` 이 아니라 `tools>CORE_TOOL_COUNT(=7)` | ✅ 반영 완료 — 본문 표현 정정 |
| 전체 | D113/D114 번호 | 없음 — 직전 D112가 마지막 항목, 번호 충돌 없음 | 없음 |
| 인프라 | 사람 승인 대기 | 없음 — `TODO_직접할일.md`의 A2A 자격증명 미기재 항목은 D112 이전 스냅샷이고, 빈 자격증명은 502로 정상 실패(막는 블로커 아님) | 없음 |

### 평가 결론
- 계획 수정 필요: **N** (Y였던 MQ-1604 DoD 문구·D88 표현 2건 전부 위에서 즉시 반영 완료, 재평가 불필요)

---

# Sprint 16 최종 실행 계획

| 스테이지 | 태스크 | 병렬 | 예상 결과물 |
|---------|--------|-----|-----------|
| Stage 1 | MQ-1601, MQ-1602, MQ-1603 | ✅ | SSE `a2a_chain_id` 필드, `GET /api/a2a/history`, MCP 도구 2종(`search_insurance_clause`·`assess_equipment_loan`) |
| Stage 2 | MQ-1604, MQ-1605, MQ-1606 | ✅ | 에이전트 루프·프롬프트 배선, 프론트 API 계층(`lib/a2a.ts`), 채팅 타입·리듀서 |
| Stage 3 | MQ-1607, MQ-1608, MQ-1609, MQ-1610 | ✅ | 채팅 A2A 결과 카드, PO 상세 출금요청 패널, 건물 위험등급 대출이력 패널, 통합 `/manager/a2a` 페이지 |
| Stage 4 | MQ-1611, MQ-1612, MQ-1613 | ✅ | 기존 스파이크 4종 카운트 갱신, 문서 6종 갱신, 신규 스파이크 `a2a_partner_tools_contract` |
| Stage 5 | MQ-1614 | — | 전수 회귀 재실행 + `CLAUDE.md` 기준선 갱신 |

**하지 않는 것(D112 경계)**: 인바운드 A2A 웹훅/콜백 수신, assess-loan→request-withdrawal 자동 체이닝, InsuQ `notify-asset-change` 신설, 실 FinAllQ/InsuQ 코어와의 E2E 성공 경로 검증.

실행: `/stage 1`

---

### Stage 1 완료 (2026-08-23)
**커밋**: `3a6c558` — `[M4] feat: Sprint 16 Stage 1 — A2A history 읽기 경로 + MCP 도구 2종 신설`

#### MQ-1601 — SSE `a2a_chain_id` + D113·D114
- `docs/10_DECISIONS.md`(D113·D114 등재) · `backend/sse.py` · `backend/agent/trace.py`
- 회귀: pytest 83(공식 baseline) · `trace_persist` 17/17 · `sp3_sse_events` 22/22 — D30(바이트 무변화) 확인

#### MQ-1602 — `GET /api/a2a/history` 신설
- `backend/services/a2a_history.py`(신규) · `backend/routers/a2a.py` · `backend/services/test_a2a_history.py`(신규, 11건) · `backend/routers/test_a2a.py`(chain_id assertion 반영)
- 회귀: `a2a_identity_contract` 19/19(D76-2 `read_trace` 무변화 확인) · 신규 pytest 포함 98건 통과

#### MQ-1603 — MCP 도구 2종 신설
- `mcp_server/tools/search_insurance_clause.py`·`assess_equipment_loan.py`(+ 테스트 29건) · `mcp_server/server.py`(full 전용 등록) · `.env.example`
- 회귀: `mcp_client_contract` 15/15 · `sp2_mcp_roundtrip` 20/20 · `a2a_identity_contract` ⑮ 0건(D15·D93 위반 없음)

**eval-runner 종합**: seed 37 · `sp2_mcp_roundtrip` 20 · `write_tool_contract` 30 · `api_contract` 41 · `sp3_sse_events` 22 · `ruff check` clean. 새 회귀 0건. `tools_profile_contract` 1건 실패는 **예상된 것**(18→20종 카운트 하드코딩, Stage 4/MQ-1611 소관) — 확인 완료, 새 버그 아님.

**reviewer 게이트**: PASS(블로커 없음). 비블로커 노트 2건 — ① `GET /api/a2a/history`에 역할 게이트 없음(기존 두 엔드포인트 관례를 따름, 감사 이력을 무인증 노출한다는 점은 다음 스프린트에서 검토할 만함) ② `mcp_server/server.py:158` 섹션 배너 주석이 "확장 11종"으로 남음(Stage 4에서 함께 정리 예정, 실제 등록 로직엔 무영향).
