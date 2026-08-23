# 발주서 화면 직접 생성·수정 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 정비사가 채팅을 거치지 않고 화면에서 발주 초안(`po_drafts`)을 직접 만들고, `draft` 상태인 동안 수정할 수 있게 한다.

**Architecture:** 단가·MOQ·에러코드 검증 로직을 `data/po_draft.py`(신규, `mcp_server`·`backend` 어느 쪽도 import하지 않는 공유 계층)로 옮긴다. MCP 도구 `create_po_draft`는 이 로직을 감싸는 얇은 래퍼로 축소되고(D10 커넥션 경계는 그대로), `backend`는 같은 로직을 새 `POST /api/po`·`PATCH /api/po/{po_id}`에서 부른다. 프론트는 `/technician/po/new`(생성)·`/technician/po/[poId]`(상세+수정)를 새로 얻는다.

**Tech Stack:** Python 3.11 (FastAPI, sqlite3), TypeScript/React (Next.js App Router, 기존 프론트 컨벤션 — MUI·Tailwind 아님, `sx()` 인라인 스타일 헬퍼)

## ⚠ 착수 전 확인 (필독)

이 계획은 **2026-08-21 브레인스토밍 세션의 승인된 설계**(`docs/superpowers/specs/2026-08-21-po-draft-screen-creation-design.md`)를 구현 단위로 쪼갠 것이다. 계획 작성 시점(2026-08-23)에 `backend/services/po.py`·`backend/routers/po.py`가 **커밋 안 된 A2A 아웃바운드 작업**(S5, FinAllQ 출금 요청)으로 이미 수정돼 있었다 — `dispatch_a2a_withdrawal_request()`가 `transition()` 뒤에, `approve()` 라우터가 그 함수를 호출하는 형태로 붙어 있었다.

**이 계획의 모든 코드 스니펫은 A2A 변경 이전(2026-08-21 시점) 파일 내용을 기준으로 작성됐다.** Task 3·4를 시작하기 전에 **반드시**:
1. `git log --oneline -5 -- backend/services/po.py backend/routers/po.py` 로 A2A 작업이 커밋됐는지 확인
2. 커밋 안 됐으면 — A2A 작업이 끝날 때까지 대기(사용자 지시)
3. 커밋됐으면 — 아래 각 태스크의 "삽입 위치" 지시(앵커 텍스트 기준)를 **그 커밋 이후의 실제 파일**에서 다시 확인하고 진행. 앵커로 쓴 함수(`stamp_identity`·`get_po`·`_transition` 정의부 앞)는 A2A 변경(`transition()` 뒤에 `dispatch_a2a_withdrawal_request` 추가, `approve()` 본문 수정)과 겹치지 않으므로 위치 자체는 유효할 가능성이 높다 — 그래도 **Read로 실제 파일을 확인한 뒤** Edit할 것.

## Global Constraints

- **범위는 발주서(`po_drafts`)만** — 처분서·수리증빙은 이 계획 밖 (스펙 §0-1)
- **`unit_price`는 항상 서버가 `supplier_parts`에서 조회한 스냅샷** — 어떤 API 파라미터로도 받지 않는다 (D31)
- **`model`·`error_code`는 둘 다 있거나 둘 다 없어야 한다** (D33), `model`은 `iG5A`|`S100`|`IE5` 중 하나 (D109)
- **실패는 예외가 아니라 `status`/`reason` 필드로 반환한다** (D9) — `data/po_draft.py`·MCP 도구·`backend/services/po.py`의 `create`/`update` 전부
- **`data/po_draft.py`는 `mcp_server`도 `backend`도 import하지 않는다** (D15) — 커넥션은 호출자가 열어서 넘긴다
- **`POST /api/po`·`PATCH /api/po/{po_id}`는 `technician` 역할 전용** — `PATCH`는 요청자 본인이 아니어도 technician이면 누구나 가능
- **`PATCH`는 `state == 'draft'`일 때만 허용, 아니면 409**
- **MCP 도구 `create_po_draft`의 출력 dict는 리팩터 전후로 한 글자도 안 바뀐다** — `spikes/write_tool_contract.py` 전건이 무변경으로 통과해야 리팩터가 성공한 것이다
- 커밋 메시지 접두어 `[M2]`(백엔드)·`[M3]`(프론트)·`[M4]`(문서), 한국어 커밋 메시지 OK
- 회귀는 `data/seed.py --with-error-codes` 재시드 후 spikes 전건 + 3개 pytest 파일로 확인(CLAUDE.md 회귀 스위트 절)

---

## Task 1: `data/po_draft.py` — 공유 산출 로직 계층

**Files:**
- Create: `data/po_draft.py`
- Test: `spikes/write_tool_contract.py` (Task 2에서 재실행 — 이 태스크 자체는 신규 파일이라 단독 실행 대상이 없다)

**Interfaces:**
- Produces:
  - `VALID_MODELS: tuple[str, ...]` — 사용 안 함(스키마 경계 검증은 각 진입점에 남는다), 삭제 대상 아님, 다만 이 모듈에는 두지 않는다
  - `next_po_id(con: sqlite3.Connection) -> str`
  - `validate_and_price(con, *, part_no: str, qty: int, supplier_id: str, model: str | None, error_code: str | None) -> dict` — 반환 `{"status":"ok","unit_price":int,"moq":int}` 또는 `{"status":"not_found"|"error", "reason":..., "message":...}`
  - `insert_draft(con, *, po_id, part_no, qty, supplier_id, model, error_code, evidence_json, unit_price, reason, urgency, requested_by=None, session_id=None) -> None`
  - `update_draft(con, *, po_id, part_no, qty, supplier_id, model, error_code, evidence_json, unit_price, reason, urgency) -> None`
  - `list_quotes(con, *, part_no: str) -> list[dict]` — `[{"supplier_id","name","lead_days","unit_price","moq"}, ...]`

- [ ] **Step 1: 파일 작성**

```python
# -*- coding: utf-8 -*-
"""po_draft — 발주 초안 산출 로직 공유 계층 (D73·D101 패턴, P39 축소판 — 발주서만).

`mcp_server/tools/create_po_draft.py`·`backend/services/po.py`가 이 모듈로 위임한다 —
`data/maint_value.py`와 같은 구조다. 소비자가 늘어도(채팅 MCP 도구 + 화면 REST) 판정
로직을 두 곳에 복제하지 않기 위해 여기 한 곳에 둔다.

⛔ 이 모듈은 `mcp_server`도 `backend`도 import하지 않는다(D15 — 두 런타임 프로세스의
상호 import 금지). 커넥션은 호출자가 열어서 넘긴다 — 이 모듈은 DB 경로를 모른다
(`data/maint_value.py`와 같은 규약).

★ `data/` 아래 첫 INSERT 수행 모듈이다 — 기존 `data/maint_value.py`류는 전부 읽기 전용
판정이었다. 이 모듈 자체는 "쓰기 권한"을 갖지 않는다 — 권한은 호출자가 여는 **커넥션의
종류**로 결정된다(MCP는 `mcp_server/db.py`의 TEMP TRIGGER로 INSERT만 허용된
`draft_writer()`, 백엔드는 이미 UPDATE 권한이 있는 일반 커넥션). 이 모듈은 그 커넥션에
SQL을 실행할 뿐이다.

스키마 경계 검증(필수값 존재·urgency enum·model/error_code 쌍·model enum)은 이 모듈에
없다 — `mcp_server/tools/create_po_draft.py`와 `backend/services/po.py`가 각자
진입점에서 한다(둘 다 같은 체크를 하지만 "산출 로직"이 아니라 "이 진입점이 받은 입력이
말이 되는가"라 의도적으로 두 곳에 둔다 — 2026-08-21 설계 §3).

실패는 예외가 아니라 status 필드로 반환한다(D9).
"""

from __future__ import annotations

import sqlite3


def next_po_id(con: sqlite3.Connection) -> str:
    row = con.execute(
        "SELECT po_id FROM po_drafts WHERE po_id LIKE 'PO-%' ORDER BY po_id DESC LIMIT 1"
    ).fetchone()
    n = int(row["po_id"].split("-")[1]) + 1 if row else 1
    return f"PO-{n:04d}"


def validate_and_price(
    con: sqlite3.Connection,
    *,
    part_no: str,
    qty: int,
    supplier_id: str,
    model: str | None,
    error_code: str | None,
) -> dict:
    """단가·MOQ 조회(D31) + 에러코드 FK 검증(D33). `error_code`는 이미 대문자 canonical(D25)
    이라고 가정한다 — 호출자가 대문자화한다."""
    quote = con.execute(
        "SELECT unit_price, moq FROM supplier_parts WHERE supplier_id=? AND part_no=?",
        (supplier_id, part_no),
    ).fetchone()
    if quote is None:
        return {
            "status": "not_found",
            "reason": "no_quote",
            "message": f"{supplier_id} 는 {part_no} 를 공급하지 않습니다",
        }

    if error_code is not None:
        known = con.execute(
            "SELECT 1 FROM error_codes WHERE model=? AND code=?", (model, error_code)
        ).fetchone()
        if known is None:
            return {
                "status": "error",
                "reason": "unknown_error_code",
                "message": (
                    f"{model} 매뉴얼에서 확인되지 않는 코드입니다 ({error_code}). "
                    "코드 없이 발주하거나 표시부를 재확인하세요."
                ),
            }

    moq = quote["moq"] or 1
    if qty < moq:
        return {
            "status": "error",
            "reason": "moq_not_met",
            "message": (
                f"{supplier_id} 의 최소 발주 수량은 {moq}개입니다 (요청 {qty}개). "
                "수량을 조정하거나 다른 공급사를 선택하세요."
            ),
            "moq": moq,
            "requested_qty": qty,
        }

    return {"status": "ok", "unit_price": quote["unit_price"], "moq": moq}


def insert_draft(
    con: sqlite3.Connection,
    *,
    po_id: str,
    part_no: str,
    qty: int,
    supplier_id: str,
    model: str | None,
    error_code: str | None,
    evidence_json: str | None,
    unit_price: int,
    reason: str,
    urgency: str,
    requested_by: str | None = None,
    session_id: str | None = None,
) -> None:
    """`po_drafts`에 draft 한 건을 INSERT. `requested_by`/`session_id`를 None으로 부르면
    기존 MCP 경로(사후 stamp, D37)와 동일하게 NULL로 들어간다 — 백엔드 경로는 생성
    즉시 `requested_by`를 채워 넘긴다(2026-08-21 설계 §4)."""
    con.execute(
        "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, model, error_code,"
        " evidence, unit_price, reason, urgency, state, requested_by, session_id)"
        " VALUES (?,?,?,?,?,?,?,?,?,?, 'draft', ?, ?)",
        (
            po_id, part_no, qty, supplier_id, model, error_code,
            evidence_json, unit_price, reason, urgency, requested_by, session_id,
        ),
    )


def update_draft(
    con: sqlite3.Connection,
    *,
    po_id: str,
    part_no: str,
    qty: int,
    supplier_id: str,
    model: str | None,
    error_code: str | None,
    evidence_json: str | None,
    unit_price: int,
    reason: str,
    urgency: str,
) -> None:
    """draft 상태 발주 한 건을 UPDATE. 호출자가 `state == 'draft'`를 이미 확인했다고
    가정한다 — `WHERE ... AND state='draft'`는 방어적 이중 잠금이지 이 함수의 유일한
    가드는 아니다(호출자가 별도로 404/409를 판단해야 한다)."""
    con.execute(
        "UPDATE po_drafts SET part_no=?, qty=?, supplier_id=?, model=?, error_code=?,"
        " evidence=?, unit_price=?, reason=?, urgency=? WHERE po_id=? AND state='draft'",
        (
            part_no, qty, supplier_id, model, error_code,
            evidence_json, unit_price, reason, urgency, po_id,
        ),
    )


def list_quotes(con: sqlite3.Connection, *, part_no: str) -> list[dict]:
    """부품의 공급사별 견적(리드타임·단가·MOQ). `backend/services/po.py`의 `get_po()`
    (상세의 `quotes` 필드)와 `quotes_for_part()`(화면이 발주 전 공급사를 고르기 위한
    사전 조회, `GET /api/po/quotes/{part_no}`)가 같은 쿼리를 쓴다 — 세 번째 사본을
    만들지 않는다."""
    rows = con.execute(
        "SELECT sp.supplier_id, s.name, sp.lead_days, sp.unit_price, sp.moq"
        " FROM supplier_parts sp JOIN suppliers s ON s.supplier_id = sp.supplier_id"
        " WHERE sp.part_no = ? ORDER BY sp.lead_days",
        (part_no,),
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 2: import 확인**

```bash
uv run python -c "from data import po_draft; print(po_draft.next_po_id, po_draft.validate_and_price, po_draft.insert_draft, po_draft.update_draft, po_draft.list_quotes)"
```
Expected: 5개 함수 객체가 에러 없이 출력됨 (아직 아무도 이 모듈을 쓰지 않으므로 동작 검증은 Task 2·3에서)

- [ ] **Step 3: Commit**

```bash
git add data/po_draft.py
git commit -m "$(cat <<'EOF'
[M2] feat: data/po_draft.py 신설 — 발주 초안 산출 로직 공유 계층 (D73·D101 패턴)

단가/MOQ 검증(D31)·에러코드 FK 검증(D33)·INSERT/UPDATE/견적조회를 mcp_server·backend
어느 쪽도 import하지 않는 공유 모듈로 뺀다. 아직 아무도 쓰지 않는 순수 추가 커밋 —
Task 2·3에서 MCP 도구·백엔드가 위임하도록 연결한다.
EOF
)"
```

---

## Task 2: `mcp_server/tools/create_po_draft.py` — 얇은 래퍼로 축소

**Files:**
- Modify: `mcp_server/tools/create_po_draft.py` (전체 교체)
- Test: `spikes/write_tool_contract.py` (기존 파일, 무변경 — 이 태스크는 오직 이 스위트가 리팩터 전후 동일하게 통과함을 확인하는 것으로 검증한다)

**Interfaces:**
- Consumes: `data.po_draft.{validate_and_price, insert_draft, next_po_id}` (Task 1)
- Produces: `create_po_draft(part_no, qty, supplier_id, reason, urgency="normal", model=None, error_code=None, evidence=None) -> dict` — **출력 shape 불변**(리팩터 전후 동일)

- [ ] **Step 1: 리팩터 전 베이스라인을 기록**

```bash
uv run python spikes/write_tool_contract.py > /tmp/write_tool_baseline.txt 2>&1; tail -5 /tmp/write_tool_baseline.txt
```
Expected: `통과 (NN건)` 형태의 마지막 줄 — 이 건수를 적어 둔다(현재 30건대 초반, `①~⑭`가 `create_po_draft` 담당). Windows에서는 `C:\Users\ttogl\AppData\Local\Temp\claude\...\scratchpad\write_tool_baseline.txt` 처럼 스크래치패드 경로를 써도 된다.

- [ ] **Step 2: `create_po_draft.py` 전체 교체**

```python
# -*- coding: utf-8 -*-
"""create_po_draft — 발주서 초안 생성 ⚠️ **유일한 쓰기 도구** (docs/04_MCP_TOOLS.md §7).

**이 파일은 얇은 래퍼다.** 단가 조회·MOQ 검증·에러코드 FK 검증·INSERT는 전부
`data/po_draft.py`에 있다(P39 축소판, D73·D101 패턴). 화면 쪽 `POST /api/po`
(`backend/services/po.py`)가 같은 함수를 부른다 — 복제본을 두면 채팅과 화면에서
같은 입력이 다르게 거부될 수 있다.

이 파일에 남는 것:
  D10  read_only()로 조회 → draft_writer()로 INSERT. 두 커넥션을 분리해 MCP 프로세스가
       INSERT 밖의 어떤 것도 못 하게 만든다(트리거는 `mcp_server/db.py`).
  D23  requested_by·session_id 는 파라미터가 아니다 — 스키마에 없으므로 LLM 이 위조할 수
       없다. INSERT 시점엔 항상 None(백엔드가 사후 stamp, D37).
  D80  필수 파라미터에 기본값을 두지 않는다 — 인자 누락은 MCP 스키마가 앞단에서 막는다.
       urgency만 optional(기본 "normal").
  스키마 경계 검증(필수값·enum·model/error_code 쌍)은 "산출 로직"이 아니라 이 진입점의
  몫이라 여기 남는다(`data/po_draft.py`에 옮기지 않는다).
"""

from __future__ import annotations

import json
import sqlite3

from data import po_draft

from ..db import draft_writer, read_only

DESCRIPTION = (
    "발주서 '초안'을 생성한다. 확정이 아니다. 반드시 사용자가 부품·공급사를 확인한 후에만 "
    "호출할 것. reason에는 진단 근거를 한 줄로 요약하고, evidence에는 어떤 현상을 보고 "
    "고장으로 판단했는지(symptoms)와 근거가 된 도구 결과(basis), 기타 비고(notes)를 "
    "구조화해 남길 것. 에러코드로부터 시작된 진단이면 model·error_code를 함께 넣을 것 — "
    "매뉴얼에 없는 코드는 거부된다. 단가는 파라미터가 아니다(서버가 조회해 채움). "
    "수량이 공급사 MOQ에 미달하면 거부되므로 미달이면 먼저 사용자에게 수량 조정을 확인할 것."
)

VALID_MODELS = ("iG5A", "S100", "IE5")


def create_po_draft(
    part_no: str,
    qty: int,
    supplier_id: str,
    reason: str,
    urgency: str = "normal",
    model: str | None = None,
    error_code: str | None = None,
    evidence: dict | None = None,
) -> dict:
    # ── 입력 검증 (실패는 전부 status 로, D9) — 스키마 경계이지 산출 로직이 아니다
    if not part_no or not supplier_id:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": "part_no·supplier_id 는 필수입니다",
        }
    if not reason or not reason.strip():
        return {
            "status": "error",
            "reason": "reason_required",
            "message": "reason 은 필수입니다 — 승인자가 판단 근거를 추적할 수 있어야 합니다 (D5)",
        }
    if qty < 1:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": f"qty 는 1 이상이어야 합니다: {qty}",
        }
    if urgency not in ("urgent", "normal"):
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": f"urgency 는 urgent|normal 이어야 합니다: {urgency!r}",
        }
    if (model is None) != (error_code is None):
        return {
            "status": "error",
            "reason": "model_code_pair",
            "message": "model 과 error_code 는 둘 다 있거나 둘 다 없어야 합니다 (D33)",
        }
    if model is not None and model not in VALID_MODELS:
        return {
            "status": "error",
            "reason": "invalid_model",
            "message": f"model 은 {' | '.join(VALID_MODELS)} 이어야 합니다: {model!r}",
        }

    code = error_code.upper() if error_code else None  # 저장은 대문자 canonical (D25)

    try:
        with read_only() as con:
            result = po_draft.validate_and_price(
                con, part_no=part_no, qty=qty, supplier_id=supplier_id, model=model, error_code=code,
            )
        if result["status"] != "ok":
            return result

        with draft_writer() as con:
            po_id = po_draft.next_po_id(con)
            po_draft.insert_draft(
                con,
                po_id=po_id,
                part_no=part_no,
                qty=qty,
                supplier_id=supplier_id,
                model=model,
                error_code=code,
                evidence_json=json.dumps(evidence, ensure_ascii=False) if evidence else None,
                unit_price=result["unit_price"],
                reason=reason.strip(),
                urgency=urgency,
            )
    except sqlite3.IntegrityError as e:
        # FK·CHECK 위반은 계약 위반이므로 그대로 드러낸다 (조용히 넘기지 않는다)
        return {"status": "error", "reason": "integrity", "message": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "reason": "db_error", "message": str(e)}

    return {
        "status": "ok",
        "po_id": po_id,
        "state": "draft",
        "unit_price": result["unit_price"],
        "total": result["unit_price"] * qty,
    }
```

- [ ] **Step 3: 회귀 재실행 — 출력 불변 확인**

```bash
uv run python spikes/write_tool_contract.py
```
Expected: Step 1에서 기록한 것과 **동일한 건수**로 `통과 (NN건)`. 한 글자라도 출력 dict가 달라지면 `①~⑭` 중 하나가 FAIL한다 — 그 경우 실패한 체크 이름을 보고 원본 `create_po_draft.py`(git으로 이전 버전 복원해 diff)와 대조한다.

- [ ] **Step 4: Commit**

```bash
git add mcp_server/tools/create_po_draft.py
git commit -m "$(cat <<'EOF'
[M2] refactor: create_po_draft 를 data/po_draft.py 위임 래퍼로 축소 (D73·D101 패턴)

산출 로직(단가/MOQ/에러코드 검증·INSERT)은 전부 이관, 출력 shape 무변경
(spikes/write_tool_contract.py ①~⑭ 전건 동일 통과로 확인). 화면 경로(Task 3·4)가
같은 로직을 재사용할 토대.
EOF
)"
```

---

## Task 3: `backend/services/po.py` — `create()`·`update()`·`quotes_for_part()` 추가

**⚠ Task 3·4 착수 전 "착수 전 확인" 절 실행 — A2A 커밋 여부 확인 후 진행.**

**Files:**
- Modify: `backend/services/po.py` (세 함수 + 예외 클래스 추가, 기존 함수는 `get_po()`의 `quotes` 조립 한 줄만 리팩터)

**Interfaces:**
- Consumes: `data.po_draft.{validate_and_price, insert_draft, update_draft, list_quotes, next_po_id}` (Task 1), `backend.db.connect`
- Produces:
  - `class NotEditableError(Exception)` — `.po_id`, `.current` 속성
  - `create(*, part_no, qty, supplier_id, reason, urgency="normal", model=None, error_code=None, evidence=None, requested_by, db_path=None) -> dict`
  - `update(po_id, *, part_no, qty, supplier_id, reason, urgency="normal", model=None, error_code=None, evidence=None, db_path=None) -> dict` — `KeyError`(없음)·`NotEditableError`(draft 아님) 던질 수 있음
  - `quotes_for_part(part_no, db_path=None) -> list[dict]`

- [ ] **Step 1: 실제 현재 파일을 Read로 확인**

`backend/services/po.py`를 Read 도구로 열어 A2A 커밋 이후 실제 내용을 확인한다. 아래 앵커(`stamp_identity()` 함수 끝, `get_po()`의 `quotes` 조립 블록, `_PO_SELECT` 상수 뒤)가 그대로 있는지 확인 — 있으면 아래 Edit을 그대로 적용, 없으면(A2A가 이 구간을 건드렸다면) 실제 코드에 맞춰 삽입 지점을 조정한다.

- [ ] **Step 2: import 추가**

`backend/services/po.py` 상단 `from backend.db import connect` 아래에 추가:

```python
import json
import sqlite3

from data import po_draft
```

(`json`·`sqlite3`가 이미 top-level import에 있는지 먼저 확인 — 원본 파일은 이미 `import json`·`import sqlite3`를 갖고 있다. 있으면 `from data import po_draft` 한 줄만 추가.)

- [ ] **Step 3: `get_po()`의 `quotes` 조립을 `list_quotes()` 위임으로 교체**

Find (in `get_po()`):
```python
        po["quotes"] = [
            dict(q)
            for q in con.execute(
                "SELECT sp.supplier_id, s.name, sp.lead_days, sp.unit_price, sp.moq"
                " FROM supplier_parts sp JOIN suppliers s ON s.supplier_id = sp.supplier_id"
                " WHERE sp.part_no = ? ORDER BY sp.lead_days",
                (po["part_no"],),
            ).fetchall()
        ]
```

Replace with:
```python
        po["quotes"] = po_draft.list_quotes(con, part_no=po["part_no"])
```

- [ ] **Step 4: `stamp_identity()` 함수 뒤(`list_pos()` 앞)에 새 코드 삽입**

```python
class NotEditableError(Exception):
    """draft 상태가 아닌 발주 초안을 수정하려는 시도 (`PATCH /api/po/{po_id}`)."""

    def __init__(self, po_id: str, current: str) -> None:
        self.po_id, self.current = po_id, current
        super().__init__(
            f"{po_id} 는 지금 '{current}' 상태라 수정할 수 없습니다 ('draft' 에서만 가능)"
        )


_VALID_MODELS = ("iG5A", "S100", "IE5")


def _validate_input(
    *, part_no: str, qty: int, supplier_id: str, reason: str, urgency: str,
    model: str | None, error_code: str | None,
) -> dict | None:
    """스키마 경계 검증 — `mcp_server/tools/create_po_draft.py`와 의도적으로 같은 체크를
    반복한다(공유 계층으로 옮기지 않는 이유는 `data/po_draft.py` 모듈 docstring 참고)."""
    if not part_no or not supplier_id:
        return {"status": "error", "reason": "invalid_input", "message": "part_no·supplier_id 는 필수입니다"}
    if not reason or not reason.strip():
        return {
            "status": "error", "reason": "reason_required",
            "message": "reason 은 필수입니다 — 승인자가 판단 근거를 추적할 수 있어야 합니다 (D5)",
        }
    if qty < 1:
        return {"status": "error", "reason": "invalid_input", "message": f"qty 는 1 이상이어야 합니다: {qty}"}
    if urgency not in ("urgent", "normal"):
        return {"status": "error", "reason": "invalid_input", "message": f"urgency 는 urgent|normal 이어야 합니다: {urgency!r}"}
    if (model is None) != (error_code is None):
        return {"status": "error", "reason": "model_code_pair", "message": "model 과 error_code 는 둘 다 있거나 둘 다 없어야 합니다 (D33)"}
    if model is not None and model not in _VALID_MODELS:
        return {
            "status": "error", "reason": "invalid_model",
            "message": f"model 은 {' | '.join(_VALID_MODELS)} 이어야 합니다: {model!r}",
        }
    return None


def quotes_for_part(part_no: str, db_path: Path | None = None) -> list[dict]:
    """`GET /api/po/quotes/{part_no}` — 발주 초안을 만들기 전 공급사를 고르기 위한 조회.
    부품·공급사가 없으면 빈 리스트(404 아님 — "없다"는 유효한 조회 결과다, D62)."""
    with connect(db_path) as con:
        return po_draft.list_quotes(con, part_no=part_no)


def create(
    *,
    part_no: str,
    qty: int,
    supplier_id: str,
    reason: str,
    urgency: str = "normal",
    model: str | None = None,
    error_code: str | None = None,
    evidence: dict | None = None,
    requested_by: str,
    db_path: Path | None = None,
) -> dict:
    """`POST /api/po` — 화면이 발주 초안을 직접 생성한다(P39 축소판).

    `requested_by`를 생성 즉시 stamp한다 — 채팅 경로(`stamp_identity`)와 달리 2단계가
    필요 없다. 이 함수를 부르는 요청 자체가 이미 `X-User`를 통과한 신뢰된 백엔드 경로다
    (D52 태도). 산출 로직은 `data/po_draft.py`에 있다 — MCP 도구(`create_po_draft`)와
    같은 함수를 쓴다(D73·D101 패턴).
    """
    invalid = _validate_input(
        part_no=part_no, qty=qty, supplier_id=supplier_id, reason=reason,
        urgency=urgency, model=model, error_code=error_code,
    )
    if invalid is not None:
        return invalid

    code = error_code.upper() if error_code else None
    try:
        with connect(db_path) as con:
            result = po_draft.validate_and_price(
                con, part_no=part_no, qty=qty, supplier_id=supplier_id, model=model, error_code=code,
            )
            if result["status"] != "ok":
                return result

            po_id = po_draft.next_po_id(con)
            po_draft.insert_draft(
                con,
                po_id=po_id, part_no=part_no, qty=qty, supplier_id=supplier_id,
                model=model, error_code=code,
                evidence_json=json.dumps(evidence, ensure_ascii=False) if evidence else None,
                unit_price=result["unit_price"], reason=reason.strip(), urgency=urgency,
                requested_by=requested_by,
            )
    except sqlite3.IntegrityError as e:
        return {"status": "error", "reason": "integrity", "message": str(e)}

    return get_po(po_id, db_path) or {}


def update(
    po_id: str,
    *,
    part_no: str,
    qty: int,
    supplier_id: str,
    reason: str,
    urgency: str = "normal",
    model: str | None = None,
    error_code: str | None = None,
    evidence: dict | None = None,
    db_path: Path | None = None,
) -> dict:
    """`PATCH /api/po/{po_id}` — draft 상태에서만 수정. 없으면 KeyError, draft 가
    아니면 NotEditableError(라우터가 각각 404·409로 매핑). supplier/qty/model/
    error_code 변경 시 단가·MOQ·에러코드를 재검증해 새 스냅샷을 찍는다(D31 정신 —
    오래된 단가를 그대로 두지 않는다).
    """
    invalid = _validate_input(
        part_no=part_no, qty=qty, supplier_id=supplier_id, reason=reason,
        urgency=urgency, model=model, error_code=error_code,
    )
    if invalid is not None:
        return invalid

    code = error_code.upper() if error_code else None
    with connect(db_path) as con:
        row = con.execute("SELECT state FROM po_drafts WHERE po_id=?", (po_id,)).fetchone()
        if row is None:
            raise KeyError(po_id)
        if row["state"] != "draft":
            raise NotEditableError(po_id, row["state"])

        result = po_draft.validate_and_price(
            con, part_no=part_no, qty=qty, supplier_id=supplier_id, model=model, error_code=code,
        )
        if result["status"] != "ok":
            return result

        po_draft.update_draft(
            con,
            po_id=po_id, part_no=part_no, qty=qty, supplier_id=supplier_id,
            model=model, error_code=code,
            evidence_json=json.dumps(evidence, ensure_ascii=False) if evidence else None,
            unit_price=result["unit_price"], reason=reason.strip(), urgency=urgency,
        )
    return get_po(po_id, db_path) or {}
```

- [ ] **Step 5: import 스모크 테스트**

```bash
uv run python -c "from backend.services import po; print(po.create, po.update, po.quotes_for_part, po.NotEditableError)"
```
Expected: 에러 없이 4개 심볼 출력

- [ ] **Step 6: Commit**

```bash
git add backend/services/po.py
git commit -m "$(cat <<'EOF'
[M2] feat: backend/services/po.py — create()·update()·quotes_for_part() 추가

data/po_draft.py 위임(D73·D101 패턴). requested_by 는 생성 즉시 stamp(신뢰된 백엔드
경로, D52). get_po() 의 quotes 조립도 같은 함수로 통일(list_quotes, 세 번째 사본 방지).
아직 라우터가 없어 REST 로 노출되지 않는다 — Task 4.
EOF
)"
```

---

## Task 4: `backend/routers/po.py` — `GET .../quotes/{part_no}`·`POST`·`PATCH` + 계약 회귀

**Files:**
- Modify: `backend/routers/po.py`
- Modify: `spikes/api_contract.py` (신규 체크 ㉑~㉚대)

**Interfaces:**
- Consumes: `backend.services.po.{create, update, quotes_for_part, NotEditableError}` (Task 3)
- Produces: HTTP `GET /api/po/quotes/{part_no}`, `POST /api/po`, `PATCH /api/po/{po_id}` — 응답 shape은 `svc.create`/`svc.update`가 돌려주는 `get_po()`와 동일(즉 기존 `PO_DETAIL_KEYS`와 같은 키집합)

- [ ] **Step 1: 실패하는 계약 체크를 먼저 작성** — `spikes/api_contract.py`의 `run()` 함수 맨 끝(마지막 `check(...)` 다음, `def main()` 앞)에 추가:

```python
    # ── ㉑ P39 축소판 — 화면 직접 생성 (POST /api/po)
    r = client.get("/api/po/quotes/CB-04", headers=TECH)
    quotes = r.json()["quotes"] if r.status_code == 200 else None
    check(
        "㉑ 부품 견적 사전 조회 (발주 화면이 공급사를 고르기 전)",
        r.status_code == 200 and isinstance(quotes, list) and len(quotes) >= 1,
        f"{r.status_code}, {len(quotes) if quotes is not None else 'N/A'}건",
    )

    supplier_id = quotes[0]["supplier_id"] if quotes else None
    r = client.post(
        "/api/po",
        json={"part_no": "CB-04", "qty": quotes[0]["moq"] if quotes else 1,
              "supplier_id": supplier_id, "reason": "화면 직접 생성 테스트"},
        headers=TECH,
    )
    body = r.json()
    check(
        "㉒ 정비사 화면 직접 생성 → 201 아니라 200 + draft + requested_by 즉시 stamp",
        r.status_code == 200 and body.get("state") == "draft"
        and body.get("requested_by") == "tech-01" and body.get("session_id") is None
        and set(body) == PO_DETAIL_KEYS,
        f"{r.status_code}, state={body.get('state')}, requested_by={body.get('requested_by')}"
        f", 키차이={set(body) ^ PO_DETAIL_KEYS or '없음'}",
    )
    new_po_id = body.get("po_id")

    r = client.post(
        "/api/po",
        json={"part_no": "CB-04", "qty": 1, "supplier_id": supplier_id, "reason": "x"},
        headers=MGR,
    )
    check("㉓ 팀장이 화면 생성 호출 → 403", r.status_code == 403, f"{r.status_code}")

    r = client.post(
        "/api/po",
        json={"part_no": "CB-04", "qty": 999999, "supplier_id": supplier_id, "reason": "x"},
        headers=TECH,
    )
    check(
        "㉔ MOQ 미달 아니라 초과 극단값도 D31 동일 경로(성공) — MOQ '미달'만 거부됨을 재확인",
        r.status_code == 200,
        f"{r.status_code}",
    )
    r = client.post(
        "/api/po",
        json={"part_no": "CB-04", "qty": 1, "supplier_id": "NO-SUCH-SUP", "reason": "x"},
        headers=TECH,
    )
    check("㉕ 없는 공급사 → 404(no_quote)", r.status_code == 404, f"{r.status_code}")

    # ── ㉖ PATCH — draft 수정
    r = client.patch(
        f"/api/po/{new_po_id}",
        json={"part_no": "CB-04", "qty": (quotes[0]["moq"] if quotes else 1) + 1,
              "supplier_id": supplier_id, "reason": "수량 정정"},
        headers=TECH,
    )
    body2 = r.json()
    check(
        "㉖ draft 수정 → 200 + qty·reason 반영",
        r.status_code == 200 and body2.get("qty") == (quotes[0]["moq"] if quotes else 1) + 1
        and body2.get("reason") == "수량 정정",
        f"{r.status_code}, qty={body2.get('qty')}, reason={body2.get('reason')!r}",
    )
    r = client.patch(
        f"/api/po/{new_po_id}",
        json={"part_no": "CB-04", "qty": 1, "supplier_id": supplier_id, "reason": "x"},
        headers=MGR,
    )
    check("㉗ 팀장이 PATCH 호출 → 403", r.status_code == 403, f"{r.status_code}")

    r = client.post(f"/api/po/{new_po_id}/submit", headers=TECH)
    check("㉘ 제출(submit) 성공 — 이후 PATCH 는 409 여야 한다", r.status_code == 200, f"{r.status_code}")
    r = client.patch(
        f"/api/po/{new_po_id}",
        json={"part_no": "CB-04", "qty": 1, "supplier_id": supplier_id, "reason": "x"},
        headers=TECH,
    )
    check("㉙ pending 상태를 PATCH → 409(draft 아님)", r.status_code == 409, f"{r.status_code}")

    r = client.patch(
        "/api/po/PO-9999",
        json={"part_no": "CB-04", "qty": 1, "supplier_id": supplier_id, "reason": "x"},
        headers=TECH,
    )
    check("㉚ 없는 발주 PATCH → 404", r.status_code == 404, f"{r.status_code}")
```

⚠ `part_no="CB-04"`는 예시다 — `Step 2`에서 실제로 시드 DB에 `supplier_parts` 행이 있는 부품 번호로 교체해야 한다(아래 Step 2 참고).

- [ ] **Step 2: 실패 확인 (라우터가 아직 없으므로 여기서 FAIL해야 정상)**

먼저 시드 DB에서 견적이 있는 실제 `part_no`를 하나 확인:
```bash
uv run python -c "
import sqlite3
con = sqlite3.connect('data/maintq.db')
con.row_factory = sqlite3.Row
print(con.execute('SELECT part_no, supplier_id, moq FROM supplier_parts LIMIT 3').fetchall())
"
```
Step 1의 `"CB-04"`를 여기서 나온 실제 `part_no`로 치환한 뒤:
```bash
uv run python spikes/api_contract.py
```
Expected: `[실패] N건: ..., ㉑ ..., ㉒ ...` — `GET /api/po/quotes/{part_no}`·`POST /api/po`·`PATCH /api/po/{po_id}`가 아직 없어 404(FastAPI 기본 404, `{"detail":"Not Found"}`)로 떨어지며 FAIL. **이 실패를 직접 확인할 것** — 여기서 이미 통과하면 앵커/치환이 잘못된 것이다.

- [ ] **Step 3: `backend/routers/po.py`에 라우트 추가**

파일 상단 import에 추가:
```python
from fastapi.responses import JSONResponse
```

`get_po()` 핸들러 정의 끝, `_transition()` 정의 시작 사이에 삽입:

```python
class CreatePoBody(BaseModel):
    part_no: str
    qty: int
    supplier_id: str
    reason: str
    urgency: str = "normal"
    model: str | None = None
    error_code: str | None = None
    evidence: dict | None = None


class UpdatePoBody(BaseModel):
    part_no: str
    qty: int
    supplier_id: str
    reason: str
    urgency: str = "normal"
    model: str | None = None
    error_code: str | None = None
    evidence: dict | None = None


# status/reason → HTTP. svc.create/update 가 data.po_draft.validate_and_price·
# 자체 _validate_input 이 돌려주는 reason 전부를 여기 매핑한다 — 목록 밖은 500.
_REASON_HTTP: dict[str, int] = {
    "invalid_input": 422,
    "reason_required": 422,
    "model_code_pair": 422,
    "invalid_model": 422,
    "unknown_error_code": 422,
    "moq_not_met": 422,
    "integrity": 422,
}


def _status_code(result: dict) -> int:
    status = result.get("status")
    if status == "ok":
        return 200
    if status == "not_found":
        return 404
    return _REASON_HTTP.get(result.get("reason"), 500)


@router.get("/quotes/{part_no}")
def get_quotes(part_no: str, c: Caller = Depends(caller)) -> dict:
    """부품의 공급사별 견적. `/technician/po/new` 화면이 공급사를 고르기 전에 부른다.

    이 경로가 `/api/po` 아래 있는 건 po_id 스코프가 아니라 "발주 초안을 만들기 위한
    사전 조회"라는 성격 때문이다 — 부품 조회 REST(`routers/maint_value.py`)와는
    목적이 다르다. 부품·공급사가 없으면 빈 리스트(404 아님, D62).
    """
    return {"part_no": part_no, "quotes": svc.quotes_for_part(part_no)}


@router.post("")
def create_po(body: CreatePoBody, c: Caller = Depends(caller)) -> JSONResponse:
    """화면에서 발주 초안을 직접 생성한다 (P39 축소판). 정비사 전용.

    응답은 GET /api/po/{po_id} 와 같은 상세 셰이프다(quotes·inventory·trace_url 포함,
    trace_url 은 session_id 가 없으므로 항상 null) — 화면이 생성 직후 바로 상세를
    그릴 수 있게 별도 조회 없이 준다.
    """
    require(c, "technician", "발주 초안 생성")
    result = svc.create(
        part_no=body.part_no, qty=body.qty, supplier_id=body.supplier_id,
        reason=body.reason, urgency=body.urgency, model=body.model,
        error_code=body.error_code, evidence=body.evidence, requested_by=c.user_id,
    )
    return JSONResponse(status_code=_status_code(result), content=result)


@router.patch("/{po_id}")
def update_po(po_id: str, body: UpdatePoBody, c: Caller = Depends(caller)) -> JSONResponse:
    """draft 상태 발주 초안을 수정한다. draft 가 아니면 409. 정비사 전용
    (요청자 본인이 아니어도 technician 이면 누구나 — 2026-08-21 설계 §4)."""
    require(c, "technician", "발주 초안 수정")
    try:
        result = svc.update(
            po_id, part_no=body.part_no, qty=body.qty, supplier_id=body.supplier_id,
            reason=body.reason, urgency=body.urgency, model=body.model,
            error_code=body.error_code, evidence=body.evidence,
        )
    except KeyError as e:
        raise HTTPException(404, f"발주서를 찾을 수 없습니다: {po_id}") from e
    except svc.NotEditableError as e:
        raise HTTPException(409, str(e)) from e
    return JSONResponse(status_code=_status_code(result), content=result)
```

- [ ] **Step 4: 계약 재실행 — 통과 확인**

```bash
uv run python spikes/api_contract.py
```
Expected: `통과 (NN건)` — 기존 건수 + 10(㉑~㉚). FAIL이 있으면 각 체크의 `detail` 출력을 읽고 원인을 찾는다(특히 ㉑의 `part_no` 치환이 맞는지부터 의심).

- [ ] **Step 5: `write_tool_contract.py`도 재확인 (사이드이펙트 없음 확인)**

```bash
uv run python spikes/write_tool_contract.py
```
Expected: Task 2와 동일 건수로 통과 — 백엔드 라우터 추가가 MCP 경로에 영향 없음을 재확인.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/po.py spikes/api_contract.py
git commit -m "$(cat <<'EOF'
[M2] feat: POST /api/po · PATCH /api/po/{po_id} · GET /api/po/quotes/{part_no} 신설 (P39 축소판)

화면이 발주 초안을 직접 생성·수정(draft 상태에서만)할 수 있는 첫 REST 경로.
data/po_draft.py 위임 로직 재사용 — 채팅(create_po_draft)과 결과물이 동일하다.
spikes/api_contract.py ㉑~㉚ 10건 추가(권한 403·MOQ/공급사 실패·전이 409·404).
EOF
)"
```

---

## Task 5: D-결정 등재 + 문서 갱신

**Files:**
- Modify: `docs/10_DECISIONS.md`
- Modify: `docs/07_BACKLOG.md`
- Modify: `docs/04_MCP_TOOLS.md`
- Modify: `docs/05_DB_SCHEMA.md`(변경 없으면 스킵 — 스키마 변경 없음, 아래 참고)
- Modify: `docs/06_REPO_API.md`
- Modify: `CLAUDE.md` (기준선 갱신)

**Interfaces:** 없음 (문서 전용 태스크)

- [ ] **Step 1: 다음 D 번호 확인**

```bash
grep -oE "D[0-9]+" docs/10_DECISIONS.md | sort -t D -k2 -n -u | tail -3
```
가장 큰 번호 + 1을 이 태스크의 D 번호로 쓴다(설계 시점 D110까지 있었음 — A2A 작업이 그 사이 새 D를 등재했을 수 있으니 **반드시 재확인**). 아래 예시는 `D111`로 쓴다 — 실제 번호가 다르면 전부 치환한다.

- [ ] **Step 2: `docs/10_DECISIONS.md`에 행 추가**

표 마지막 행 뒤에 추가(기존 행과 같은 `| Dxxx | 결정 | 기각안 | 근거 |` 형식):

```markdown
| D111 | 화면이 `po_drafts`를 **직접 생성**하는 첫 REST 경로(`POST /api/po`)를 연다. D18·D29의 "레코드 상태 변경은 사람 전용 API를 지난다"는 지키되, "생성" 자체가 MCP 도구(채팅) 전용이던 선례를 처음 깬다. 산출 로직은 `data/po_draft.py` 공유 계층(D73·D101 패턴)에 있어 채팅·화면 두 경로가 동일한 검증(D31·D33)을 거친다. 채팅 경로(`create_po_draft`)는 폐지하지 않고 병행 | 화면은 여전히 채팅 prefill로 우회(처분서 선례) / 화면 생성을 매니저도 허용 | P39 요청 원문 — "AI가 먼저 대령하는 건 부가 기능일 뿐"이라 주 경로는 사람이 화면에서 직접 만드는 것. 매니저 허용은 "정비사가 만들고 팀장이 승인" 시나리오와 안 맞고 권한 모델을 불필요하게 넓힌다 |
```

- [ ] **Step 3: `docs/07_BACKLOG.md`의 P39·P41 행 갱신**

`P39` 행: 상태를 "**발주서 부분 완료 (D111, 2026-08-XX)** — 처분서·수리증빙은 미착수"로 시작하는 각주를 앞에 붙인다(기존 서술은 지우지 않고 위에 추가 — 이 파일의 다른 정정 각주들과 같은 방식).

`P41` 행의 "② 화면에서 직접 생성·수정 — 이건 P39 그 자체다" 문장 뒤에 각주 추가:
```
✅ **발주서 한정으로 완료 (D111)** — `POST /api/po`·`PATCH /api/po/{po_id}`·
`/technician/po/new`·`/technician/po/[poId]`. P41 나머지(①③④)의 ②로서는 이걸로 닫힌다.
```

- [ ] **Step 4: `docs/04_MCP_TOOLS.md` §7 (`create_po_draft`) 갱신**

"이 도구 계약은 무변경이나 이제 화면 경로(`POST /api/po`)도 같은 검증을 거친다"는 각주 1줄 추가. 계약 표(입출력) 자체는 무변경이므로 그 외 수정 없음.

- [ ] **Step 5: `docs/06_REPO_API.md` §2.2 갱신**

`POST /api/po`·`PATCH /api/po/{po_id}`·`GET /api/po/quotes/{part_no}` 3줄을 기존 엔드포인트 목록(`POST /api/po/{po_id}/submit` 등이 나열된 블록)에 추가.

- [ ] **Step 6: `CLAUDE.md` 회귀 기준선 갱신**

- spikes 건수: `api_contract 31` → `api_contract 41`(㉑~㉚ 10건), 헤드라인 총합도 +10
- 새 델타 문단 추가(기존 문단들과 같은 형식): "**978→988**: D111(P39 축소판, 화면 직접 발주 생성)이 `api_contract`에 10건을 더했다(978+10=988) — 나머지 31스위트는 무변경." (⚠ 이 시점까지 A2A·다른 작업이 헤드라인을 이미 옮겼을 수 있으니 **실제 최신 숫자 위에 +10** 할 것, 978을 맹신하지 말고 이 태스크 실행 시점의 `docs/README.md`·`CLAUDE.md` 최신 값을 먼저 확인)
- 절대 규칙 1(쓰기 도구 3종) 밑에 각주: "화면 직접 생성(`POST /api/po`)은 MCP 도구가 아니라 백엔드 쓰기이므로 이 규칙(D10) 대상이 아니다 — `data/po_draft.py`를 백엔드가 UPDATE 권한이 있는 일반 커넥션으로 부른다(D111)"

- [ ] **Step 7: Commit**

```bash
git add docs/10_DECISIONS.md docs/07_BACKLOG.md docs/04_MCP_TOOLS.md docs/06_REPO_API.md CLAUDE.md
git commit -m "$(cat <<'EOF'
[M4] docs: D111 등재 — 화면 직접 발주 생성 (P39 축소판·P41 ② 발주서분 완료)

정본 갱신(10_DECISIONS·04_MCP_TOOLS·06_REPO_API·07_BACKLOG) + CLAUDE.md 기준선
(api_contract 31→41, +10건).
EOF
)"
```

---

## Task 6: `frontend/lib/api.ts` — `createPo`·`updatePo`·`getPartQuotes`

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Consumes: `apiFetch`, `ApiPo`(기존)
- Produces: `interface CreatePoBody`, `interface ApiQuote`, `getPartQuotes(role, partNo) -> Promise<{part_no, quotes: ApiQuote[]}>`, `createPo(body: CreatePoBody) -> Promise<ApiPo>`, `updatePo(poId, body: CreatePoBody) -> Promise<ApiPo>`

- [ ] **Step 1: `rejectPo` 정의 바로 뒤에 추가**

```typescript
/** 부품의 공급사별 견적 — `/technician/po/new` 화면이 공급사를 고르기 전 조회 (D111). */
export interface ApiQuote {
  supplier_id: string;
  name: string;
  lead_days: number;
  unit_price: number;
  moq: number;
}

export const getPartQuotes = (role: Role, partNo: string) =>
  apiFetch<{ part_no: string; quotes: ApiQuote[] }>(
    `/api/po/quotes/${encodeURIComponent(partNo)}`,
    role
  );

/** POST /api/po · PATCH /api/po/{poId} 공용 바디 (D111, P39 축소판 — 발주서만). */
export interface CreatePoBody {
  part_no: string;
  qty: number;
  supplier_id: string;
  reason: string;
  urgency?: "urgent" | "normal";
}

/**
 * 화면에서 발주 초안을 직접 생성한다. 정비사만 — 팀장이 부르면 403.
 * 단가·MOQ 미달·미지 공급사 등 검증 실패는 404/422 로 ApiError 를 던진다
 * (`errorBody()` 로 status/reason/message 를 꺼내 보일 것 — `extractDetail()` 은
 * `.detail` 이 없으면 `.message` 로 자동 폴백한다).
 */
export const createPo = (body: CreatePoBody) =>
  apiFetch<ApiPo>("/api/po", "technician", {
    method: "POST",
    body: JSON.stringify(body),
  });

/** draft 상태 발주 초안을 수정한다. draft 아니면 409, 검증 실패는 422/404. */
export const updatePo = (poId: string, body: CreatePoBody) =>
  apiFetch<ApiPo>(`/api/po/${poId}`, "technician", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
```

- [ ] **Step 2: 타입체크**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 에러 없음 (이 시점엔 아직 아무도 새 함수를 쓰지 않으므로 미사용 export는 TS 에러가 아니다)

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "$(cat <<'EOF'
[M3] feat: lib/api.ts — createPo·updatePo·getPartQuotes 추가 (D111)

POST/PATCH /api/po, GET /api/po/quotes/{part_no} 클라이언트. 아직 화면에서 안 쓴다 —
Task 7~9.
EOF
)"
```

---

## Task 7: `PoForm` 공유 폼 컴포넌트

**Files:**
- Create: `frontend/components/asset/PoForm.tsx`

**Interfaces:**
- Consumes: `getInventory`(기존, 부품 검색), `getPartQuotes`·`createPo`·`updatePo`·`CreatePoBody`·`ApiPo`(Task 6), `ApiError`·`errorBody`·`extractDetail`(기존)
- Produces: `export function PoForm(props: PoFormProps): JSX.Element` —
  ```typescript
  interface PoFormProps {
    mode: "create" | "edit";
    /** edit 모드에서만: 이미 고정된 부품 — 부품 검색 UI 를 스킵한다 */
    lockedPart?: { part_no: string; part_name: string };
    /** 두 모드 공통 초깃값 */
    initial?: { qty?: number; supplier_id?: string; reason?: string; urgency?: "urgent" | "normal" };
    /** create 모드: createPo, edit 모드: (body) => updatePo(poId, body) — 호출자가 바인딩해 넘긴다 */
    onSubmit: (body: import("@/lib/api").CreatePoBody) => Promise<import("@/lib/api").ApiPo>;
    onSuccess: (po: import("@/lib/api").ApiPo) => void;
  }
  ```

- [ ] **Step 1: 파일 작성**

```tsx
"use client";

import { useEffect, useState } from "react";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  errorBody,
  extractDetail,
  getInventory,
  getPartQuotes,
  type ApiInventoryItem,
  type ApiPo,
  type ApiQuote,
  type CreatePoBody,
} from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * 발주 초안 생성/수정 공용 폼 (D111, P39 축소판 — 발주서만).
 *
 * `ExpenditureForm.tsx`(부품 검색 → 입력 → 제출 → 실패 표시)와 같은 구조를 따른다.
 * 부품 검색 로직을 그 컴포넌트와 공유하지 않는다 — 이 저장소의 화면들은 각자 자기
 * 부품 검색 wiring 을 갖는다(UI wiring 이지 D73·D101 이 막는 "산출 로직"이 아니다).
 *
 * `model`·`error_code`·`evidence` 는 이 폼에 없다 — 그건 채팅 진단 컨텍스트에서만
 * 의미가 있는 필드라(어떤 에러코드를 보고 판단했는지), 화면에서 맨 처음부터 직접
 * 만드는 발주에는 자연히 없다(YAGNI, 2026-08-21 설계에서 의도적으로 뺀 범위).
 */
export function PoForm({
  mode,
  lockedPart,
  initial,
  onSubmit,
  onSuccess,
}: {
  mode: "create" | "edit";
  lockedPart?: { part_no: string; part_name: string };
  initial?: { qty?: number; supplier_id?: string; reason?: string; urgency?: "urgent" | "normal" };
  onSubmit: (body: CreatePoBody) => Promise<ApiPo>;
  onSuccess: (po: ApiPo) => void;
}) {
  // ── 부품 선택 (create 모드에서만 검색, edit 모드는 lockedPart 로 고정) ──
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchFailure, setSearchFailure] = useState<string | null>(null);
  const [items, setItems] = useState<ApiInventoryItem[] | null>(null);
  const [pickedPart, setPickedPart] = useState<{ part_no: string; part_name: string } | null>(
    lockedPart ?? null
  );

  async function search() {
    const q = query.trim();
    if (!q || searching) return;
    setSearching(true);
    setSearchFailure(null);
    setItems(null);
    try {
      const res = await getInventory("technician", { part_name: q });
      setItems(res.status === "ok" ? (res.items ?? []) : []);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setSearchFailure("일치하는 부품이 없습니다.");
      } else if (e instanceof ApiError) {
        setSearchFailure(extractDetail(e.body));
      } else {
        setSearchFailure("백엔드에 연결하지 못했습니다.");
      }
      setItems([]);
    } finally {
      setSearching(false);
    }
  }

  // ── 공급사 견적 (부품이 정해지면 조회) ──
  const [quotes, setQuotes] = useState<ApiQuote[] | null>(null);
  const [quotesFailure, setQuotesFailure] = useState<string | null>(null);
  const [supplierId, setSupplierId] = useState<string | null>(initial?.supplier_id ?? null);

  useEffect(() => {
    if (!pickedPart) return;
    let alive = true;
    setQuotes(null);
    setQuotesFailure(null);
    getPartQuotes("technician", pickedPart.part_no)
      .then((res) => {
        if (!alive) return;
        setQuotes(res.quotes);
        if (res.quotes.length === 0) setQuotesFailure("이 부품을 공급하는 업체가 없습니다.");
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setQuotes([]);
        setQuotesFailure(
          e instanceof ApiError ? extractDetail(e.body) : "견적을 불러오지 못했습니다."
        );
      });
    return () => {
      alive = false;
    };
  }, [pickedPart]);

  // ── 나머지 필드 ──
  const [qty, setQty] = useState(initial?.qty ? String(initial.qty) : "");
  const [reason, setReason] = useState(initial?.reason ?? "");
  const [urgency, setUrgency] = useState<"urgent" | "normal">(initial?.urgency ?? "normal");

  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const qtyNum = qty === "" ? null : Number(qty);
  const qtyValid = qtyNum !== null && Number.isInteger(qtyNum) && qtyNum >= 1;
  const canSubmit =
    Boolean(pickedPart) && Boolean(supplierId) && qtyValid && reason.trim().length > 0 && !submitting;

  async function submit() {
    if (!pickedPart || !supplierId || qtyNum === null || !qtyValid || !reason.trim() || submitting) {
      return;
    }
    setSubmitting(true);
    setFailure(null);
    try {
      const po = await onSubmit({
        part_no: pickedPart.part_no,
        qty: qtyNum,
        supplier_id: supplierId,
        reason: reason.trim(),
        urgency,
      });
      onSuccess(po);
    } catch (e) {
      if (e instanceof ApiError) {
        const body = errorBody(e);
        const reason2 = typeof body?.reason === "string" ? body.reason : "";
        const message = extractDetail(e.body);
        setFailure(reason2 ? `${reason2} — ${message}` : message);
      } else {
        setFailure("백엔드에 연결하지 못했습니다 — 초안이 만들어지지 않았습니다.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={sx("display:flex;flex-direction:column;gap:16px")}>
      {!lockedPart && (
        <section
          style={sx(
            "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:13px 15px;" +
              "display:flex;flex-direction:column;gap:10px"
          )}
        >
          <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>부품 선택</span>
          <div style={sx("display:flex;gap:8px;align-items:center")}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void search();
              }}
              placeholder="부품명으로 검색 (예: 냉각팬)"
              style={sx(
                "flex:1;height:34px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
                  "padding:0 11px;font:12.5px 'Pretendard';color:var(--ink);outline:none"
              )}
            />
            <Button
              onClick={query.trim() && !searching ? () => void search() : undefined}
              style={query.trim() && !searching ? "" : "opacity:.5;cursor:not-allowed"}
            >
              {searching ? "검색 중…" : "검색"}
            </Button>
          </div>

          {searchFailure && <StatusBanner tone="error">{searchFailure}</StatusBanner>}

          {items && items.length > 0 && (
            <div style={sx("display:flex;flex-direction:column;gap:6px")}>
              {items.map((it) => {
                const on = it.part_no === pickedPart?.part_no;
                return (
                  <button
                    key={it.part_no}
                    onClick={() => {
                      setPickedPart({ part_no: it.part_no, part_name: it.name });
                      setSupplierId(null);
                    }}
                    aria-pressed={on}
                    style={sx(
                      "text-align:left;border-radius:7px;padding:8px 11px;cursor:pointer;" +
                        (on
                          ? "border:1px solid var(--blue-br);background:var(--cite-bg)"
                          : "border:1px solid var(--line2);background:var(--raise)")
                    )}
                  >
                    <div style={sx("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
                      <Mono size={11.5}>{it.part_no}</Mono>
                      <span style={sx("font:12px 'Pretendard';color:var(--ink)")}>{it.name}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </section>
      )}

      {pickedPart && (
        <section
          style={sx(
            "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:13px 15px;" +
              "display:flex;flex-direction:column;gap:11px"
          )}
        >
          <div style={sx("display:flex;align-items:center;gap:8px")}>
            <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>선택된 부품</span>
            <Mono size={11.5}>{pickedPart.part_no}</Mono>
            <span style={sx("font:12px 'Pretendard';color:var(--ink)")}>{pickedPart.part_name}</span>
          </div>

          <div style={sx("display:flex;flex-direction:column;gap:6px")}>
            <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>공급사</span>
            {quotesFailure && <StatusBanner tone="error">{quotesFailure}</StatusBanner>}
            {quotes === null && !quotesFailure && (
              <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>견적 불러오는 중…</span>
            )}
            {quotes?.map((q) => {
              const on = q.supplier_id === supplierId;
              return (
                <button
                  key={q.supplier_id}
                  onClick={() => setSupplierId(q.supplier_id)}
                  aria-pressed={on}
                  style={sx(
                    "text-align:left;border-radius:7px;padding:8px 11px;cursor:pointer;" +
                      (on
                        ? "border:1px solid var(--blue-br);background:var(--cite-bg)"
                        : "border:1px solid var(--line2);background:var(--raise)")
                  )}
                >
                  <div style={sx("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
                    <Mono size={11.5}>{q.supplier_id}</Mono>
                    <span style={sx("font:12px 'Pretendard';color:var(--ink)")}>{q.name}</span>
                    <span style={sx("font:11.5px 'JetBrains Mono',monospace;color:var(--dim)")}>
                      {q.unit_price.toLocaleString()}원 · 리드타임 {q.lead_days}일 · MOQ {q.moq}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          <div style={sx("display:flex;align-items:center;gap:12px;flex-wrap:wrap")}>
            <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>수량</span>
            <input
              type="number"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              placeholder="1 이상"
              style={sx(
                "height:32px;width:110px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
                  "padding:0 10px;font:12px 'JetBrains Mono',monospace;color:var(--ink);outline:none"
              )}
            />
            {qty !== "" && !qtyValid && (
              <span style={sx("font:11.5px 'Pretendard';color:var(--error-tx)")}>
                1 이상의 정수를 입력하세요
              </span>
            )}

            <span style={sx("font:700 12px 'Pretendard';color:var(--ink2);margin-left:8px")}>긴급도</span>
            <select
              value={urgency}
              onChange={(e) => setUrgency(e.target.value as "urgent" | "normal")}
              style={sx(
                "height:32px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
                  "padding:0 8px;font:12px 'Pretendard';color:var(--ink);outline:none"
              )}
            >
              <option value="normal">보통</option>
              <option value="urgent">긴급</option>
            </select>
          </div>

          <div style={sx("display:flex;flex-direction:column;gap:6px")}>
            <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>발주 사유</span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="예: 냉각팬 소음·진동으로 인한 예방 교체, 재고 부족"
              rows={2}
              style={sx(
                "border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
                  "padding:8px 10px;font:12px/1.5 'Pretendard';color:var(--ink);outline:none;resize:vertical"
              )}
            />
          </div>

          <div style={sx("display:flex;align-items:center;gap:10px")}>
            <Button
              onClick={canSubmit ? () => void submit() : undefined}
              style={canSubmit ? "" : "opacity:.5;cursor:not-allowed"}
            >
              {submitting
                ? mode === "create"
                  ? "생성 중…"
                  : "저장 중…"
                : mode === "create"
                  ? "발주 초안 생성"
                  : "수정 저장"}
            </Button>
            {!canSubmit && !submitting && (
              <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>
                공급사·수량(1 이상)·사유를 모두 입력해야 {mode === "create" ? "생성" : "저장"}할 수 있습니다
              </span>
            )}
          </div>
        </section>
      )}

      {failure && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:6px;padding:8px 10px;" +
              "font:11.5px/1.6 'Pretendard';color:var(--error-tx)"
          )}
        >
          <b>{mode === "create" ? "생성 실패" : "저장 실패"}</b> — {failure}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: `StatusBanner`가 `tone="error"`를 지원하는지 확인**

```bash
grep -n "tone" frontend/components/layout/StatusBanner.tsx
```
Expected: `error`가 허용된 tone 목록에 있음(`disposal/page.tsx`에서 이미 `tone="error"` 사용 확인됨 — Task 7 착수 전 이미 검증됨). 없으면 `error` 대신 기존에 쓰던 인라인 `<div>` 패턴(ExpenditureForm의 `failure` 블록)으로 교체.

- [ ] **Step 3: 타입체크**

```bash
cd frontend && npx tsc --noEmit
```
Expected: 에러 없음. `PoForm`이 아직 어디서도 import되지 않으므로 미사용 경고만 있을 수 있음(에러 아님).

- [ ] **Step 4: Commit**

```bash
git add frontend/components/asset/PoForm.tsx
git commit -m "$(cat <<'EOF'
[M3] feat: PoForm 공유 컴포넌트 — 발주 생성/수정 폼 (D111)

부품 검색(create)/고정(edit) → 공급사 선택 → 수량·긴급도·사유 → 제출.
ExpenditureForm.tsx 와 같은 검색→선택→제출→실패표시 구조. 아직 어느 페이지도
안 쓴다 — Task 8·9.
EOF
)"
```

---

## Task 8: `/technician/po/new` 페이지

**Files:**
- Create: `frontend/app/(console)/technician/po/new/page.tsx`

**Interfaces:**
- Consumes: `PoForm`(Task 7), `createPo`(Task 6)

- [ ] **Step 1: 파일 작성**

```tsx
"use client";

import { useRouter } from "next/navigation";
import { PoForm } from "@/components/asset/PoForm";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { Divider, Logo } from "@/components/ui/Chip";
import { createPo, type ApiPo } from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * `/technician/po/new` — 발주 초안 화면 직접 생성 (D111, P39 축소판·P41 ② 선결과제).
 *
 * 채팅을 거치지 않는 첫 발주 생성 경로다. `InventoryDrawer`의 "발주하러 가기"가
 * 여기로 온다(`?part_no=`는 아직 자동 프리필하지 않는다 — `PoForm`이 부품 검색부터
 * 시작하는 게 기본 흐름이라, 쿼리 프리필은 검색창에 초깃값을 채우는 정도로만 쓴다.
 * 완전 자동 선택은 사용자가 확인 없이 부품이 골라지는 것이라 D31 의 "사람이 확인 후
 * 호출" 정신과 어긋난다).
 *
 * 생성 성공 시 `/technician/po/{po_id}`로 이동한다 — 그 화면이 상세+수정을 맡는다.
 */
export default function NewPoPage() {
  const router = useRouter();

  function onSuccess(po: ApiPo) {
    router.push(`/technician/po/${encodeURIComponent(po.po_id)}`);
  }

  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink2)")}>발주 초안 생성</span>
          <Spacer />
          <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
            생성 후에도 승인 요청 전까지는 수정할 수 있습니다
          </span>
        </ConsoleHeader>

        <div style={sx("padding:16px 18px")}>
          <PoForm mode="create" onSubmit={createPo} onSuccess={onSuccess} />
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
```

- [ ] **Step 2: 빌드 확인**

```bash
cd frontend && npx next build
```
Expected: 빌드 성공, 새 라우트 `/technician/po/new`가 라우트 목록에 나타남(프론트 라우트 기준선이 18→19로 늘어남 — Task 11에서 CLAUDE.md에 반영)

- [ ] **Step 3: 수동 확인 (dev 서버)**

```bash
cd frontend && npm run dev
```
브라우저로 `http://localhost:3000/technician/po/new` 접속 → 부품 검색 → 결과 클릭 → 공급사 선택 → 수량·사유 입력 → "발주 초안 생성" 클릭 → `/technician/po/PO-XXXX`로 리다이렉트되는지 확인 (Task 9 완료 전이면 404 — 정상, Task 9까지 마친 뒤 재확인).

- [ ] **Step 4: Commit**

```bash
git add frontend/app/\(console\)/technician/po/new/page.tsx
git commit -m "$(cat <<'EOF'
[M3] feat: /technician/po/new — 발주 초안 화면 직접 생성 페이지 (D111)

PoForm(create 모드) 래핑. 생성 성공 시 /technician/po/{po_id}로 이동(Task 9).
EOF
)"
```

---

## Task 9: `/technician/po/[poId]` 페이지 — 상세 + 수정(draft) + 제출

**Files:**
- Create: `frontend/app/(console)/technician/po/[poId]/page.tsx`

**Interfaces:**
- Consumes: `PoForm`(Task 7), `getPo`·`updatePo`·`submitPo`(기존+Task 6), `isDraftState`(기존 `lib/queueState.ts`)

- [ ] **Step 1: 파일 작성**

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { PoForm } from "@/components/asset/PoForm";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import { StateBadge } from "@/components/ui/Badge";
import { ApiError, extractDetail, getPo, submitPo, updatePo, type ApiPo } from "@/lib/api";
import { isDraftState } from "@/lib/queueState";
import { sx } from "@/lib/sx";

/**
 * `/technician/po/{poId}` — 발주 초안 상세 + 수정(draft 상태에서만) + 승인 요청.
 *
 * `state==='draft'` 면 `PoForm`(edit 모드, 부품 고정)을 보여주고, 그 이상 상태면
 * 읽기 전용 카드로 전환한다(`isDraftState()` 재사용 — D87, 새 로컬 상수를 만들지 않는다).
 * 매니저 상세 화면(`/manager/po/[poId]`, `ApprovalQueueScreen`)과 컴포넌트를 공유하지
 * 않는다 — 기술자 화면은 "내가 만든 초안을 고친다"는 톤이고 매니저 화면은 "승인 큐 항목을
 * 판단한다"는 톤이라 정보 밀도·액션이 다르다.
 */
export default function TechnicianPoDetailPage({ params }: { params: { poId: string } }) {
  const poId = decodeURIComponent(params.poId);

  const [po, setPo] = useState<ApiPo | null>(null);
  const [loadFailure, setLoadFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const p = await getPo("technician", poId);
      setPo(p);
      setLoadFailure(null);
    } catch (e) {
      setPo(null);
      setLoadFailure(
        e instanceof ApiError && e.status === 404
          ? `발주서를 찾을 수 없습니다 — ${poId}`
          : "백엔드에 연결하지 못했습니다."
      );
    }
  }, [poId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function requestApproval() {
    if (!po || submitting) return;
    setSubmitting(true);
    try {
      const updated = await submitPo(po.po_id);
      setNotice(`팀장 승인 큐로 전달되었습니다 — ${updated.state}`);
      await load();
    } catch (e) {
      setNotice(e instanceof ApiError ? `${e.status} — ${extractDetail(e.body)}` : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (loadFailure) {
    return (
      <ScreenStack>
        <StatusBanner tone="error">⚠ {loadFailure}</StatusBanner>
      </ScreenStack>
    );
  }

  if (!po) {
    return (
      <ScreenStack>
        <div style={sx("font:12.5px 'Pretendard';color:var(--dim);padding:24px")}>
          불러오는 중… <Mono>{poId}</Mono>
        </div>
      </ScreenStack>
    );
  }

  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <Mono size={12.5}>{po.po_id}</Mono>
          <StateBadge kind="po" state={po.state} size={10} />
          <Spacer />
          {isDraftState(po.state) && (
            <Button size="sm" onClick={submitting ? undefined : () => void requestApproval()}>
              {submitting ? "요청 중…" : "팀장 승인 요청"}
            </Button>
          )}
        </ConsoleHeader>

        {notice && (
          <div style={sx("padding:10px 18px 0")}>
            <StatusBanner tone="info">{notice}</StatusBanner>
          </div>
        )}

        <div style={sx("padding:16px 18px")}>
          {isDraftState(po.state) ? (
            <PoForm
              mode="edit"
              lockedPart={{ part_no: po.part_no, part_name: po.part_name }}
              initial={{ qty: po.qty, supplier_id: po.supplier_id, reason: po.reason, urgency: po.urgency }}
              onSubmit={(body) => updatePo(po.po_id, body)}
              onSuccess={(updated) => {
                setPo(updated);
                setNotice("수정을 저장했습니다.");
              }}
            />
          ) : (
            <ReadOnlyCard po={po} />
          )}
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}

/* -------------------------------------------------------------------------- */

function ReadOnlyCard({ po }: { po: ApiPo }) {
  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:13px 15px;" +
          "display:flex;flex-direction:column;gap:9px"
      )}
    >
      <div style={sx("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <Mono size={12}>{po.part_no}</Mono>
        <span style={sx("font:12.5px 'Pretendard';color:var(--ink)")}>{po.part_name}</span>
      </div>
      <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
        수량 {po.qty} · 공급사 {po.supplier_name} · 단가 {po.unit_price.toLocaleString()}원 · 총액{" "}
        {(po.unit_price * po.qty).toLocaleString()}원
      </span>
      <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>사유 — {po.reason}</span>
      <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>
        {po.state === "draft"
          ? "제출 전"
          : `${po.state === "pending" ? "승인 대기 중" : po.state === "approved" ? "승인됨" : "반려됨"} — draft 상태가 아니므로 이 화면에서 더 이상 수정할 수 없습니다`}
      </span>
    </section>
  );
}
```

- [ ] **Step 2: `StateBadge`가 `kind="po"`를 지원하는지 확인**

```bash
grep -n "KIND_LABEL\|STATE_LABEL" frontend/lib/queueState.ts | head -5
```
`ApprovalKind`에 `"po"`가 이미 있는지 확인(기존 `/manager/po/[poId]`가 이미 이 kind를 쓰고 있을 가능성이 높음 — `spikes/api_contract.py`의 `PO_LIST_ITEM_KEYS` 존재로 미루어 `po`는 기존에 다뤄지던 kind). 없으면 `StateBadge kind="po"` 대신 `po.state`를 직접 문자열로 표시하는 것으로 낮춘다(단, `isDraftState()`는 `state` 문자열만 보므로 이 확인과 무관하게 그대로 동작한다).

- [ ] **Step 3: 빌드 확인**

```bash
cd frontend && npx next build
```
Expected: 빌드 성공, `/technician/po/[poId]` 라우트 등장(프론트 라우트 18→20, Task 8의 `/technician/po/new`와 합쳐 +2)

- [ ] **Step 4: 수동 확인**

```bash
cd frontend && npm run dev
```
`/technician/po/new`에서 초안 생성 → 자동으로 `/technician/po/PO-XXXX`로 이동 → 수정 폼이 뜨는지, 수량 바꾸고 저장하면 반영되는지, "팀장 승인 요청" 클릭 후 새로고침하면 읽기 전용 카드로 바뀌는지 확인.

- [ ] **Step 5: Commit**

```bash
git add "frontend/app/(console)/technician/po/[poId]/page.tsx"
git commit -m "$(cat <<'EOF'
[M3] feat: /technician/po/[poId] — 발주 초안 상세 + 수정(draft) + 승인 요청 (D111)

draft 면 PoForm(edit), 아니면 읽기 전용 카드(isDraftState 재사용, D87).
"팀장 승인 요청" 은 기존 submitPo(POST .../submit) 그대로.
EOF
)"
```

---

## Task 10: `InventoryDrawer.tsx` — "발주하러 가기" 를 화면 직접 생성으로 교체

**Files:**
- Modify: `frontend/components/asset/InventoryDrawer.tsx`

**Interfaces:** 없음 (기존 컴포넌트의 링크 대상만 변경)

- [ ] **Step 1: 컴포넌트 상단 주석 교체**

Find:
```tsx
 * ⛔ 발주는 이 컴포넌트가 직접 만들지 않는다 — "발주하러 가기" 는 기존 채팅 prefill
 *   경로(`/technician?prefill=...`)로 이동만 한다. `create_po_draft` 호출은 여전히
 *   에이전트가 채팅에서 한다(P39 완성 전까지의 의도적 설계 — docs/07_BACKLOG.md P39).
```

Replace:
```tsx
 * "발주하러 가기"는 `/technician/po/new`(화면 직접 생성, D111)로 이동한다 — 이 컴포넌트가
 *   직접 발주 초안을 만들지는 않는다(재고 조회 드로어의 책임 밖). 채팅 경로
 *   (`create_po_draft`)는 부가 기능으로 계속 남아 있다 — 에이전트가 대화 중 알아서
 *   만들 수도 있지만, 이 버튼은 그 경로를 타지 않는다.
```

- [ ] **Step 2: prefill 링크 로직 교체**

Find:
```tsx
  const prefillText = `${equipmentId ?? "해당 설비"}의 ${partNo} 재고 부족, 발주해줘`;
  const prefillHref =
    `/technician?prefill=${encodeURIComponent(prefillText)}` +
    (equipmentId ? `&equipment=${encodeURIComponent(equipmentId)}` : "");
```

Replace:
```tsx
  // 부품은 화면에서 검색부터 다시 고른다(D31 "사람이 확인 후" 정신) — 쿼리로는
  // equipment 컨텍스트만 참고용으로 넘긴다. part_no 를 자동 프리필하지 않는 이유는
  // PoForm 의 partNo 프리필을 지원하기로 결정하면 그때 이 값을 읽으면 된다(YAGNI로
  // 지금은 만들지 않음 — Task 8 의 페이지 주석 참고).
  const poHref =
    `/technician/po/new` + (equipmentId ? `?equipment=${encodeURIComponent(equipmentId)}` : "");
```

- [ ] **Step 3: 링크 대상 교체**

Find:
```tsx
                <Link
                  href={prefillHref}
```

Replace:
```tsx
                <Link
                  href={poHref}
```

- [ ] **Step 4: 미사용 import 확인**

`partNo`·`equipmentId`가 여전히 `poHref` 계산에 쓰이므로 별도 import 제거는 필요 없음. `npx tsc --noEmit`로 확인:
```bash
cd frontend && npx tsc --noEmit
```
Expected: 에러 없음

- [ ] **Step 5: Commit**

```bash
git add frontend/components/asset/InventoryDrawer.tsx
git commit -m "$(cat <<'EOF'
[M3] refactor: InventoryDrawer "발주하러 가기" → /technician/po/new 로 교체 (D111)

채팅 prefill 우회 경로를 화면 직접 생성으로 대체. P39 축소판 완료로 문서가
예고했던 스왑(docs/07_BACKLOG.md P39 "이 버튼을 직접생성으로 바꿔 끼우면 된다").
EOF
)"
```

---

## Task 11: 전체 회귀 + `ui_honesty_contract` 카운트 확인 + 최종 커밋

**Files:**
- Modify: `CLAUDE.md` (ui_honesty·프론트 라우트 기준선 최종 갱신 — Task 5에서 미리 못 채운 정확한 숫자로 확정)

**Interfaces:** 없음

- [ ] **Step 1: DB 재시드**

```bash
uv run python data/seed.py --with-error-codes
```
Expected: 마지막 줄에 `error_codes` 행 수가 나옴 — **70**이어야 한다(재시드 후 사람 승인 반영분, `SELECT count(*) FROM error_codes`로 재확인 가능). ⛔ `--today` 플래그 쓰지 않는다(CLAUDE.md 경고).

- [ ] **Step 2: spikes 전건 실행**

```bash
for f in spikes/*.py; do
  echo "=== $f ==="
  uv run python "$f" || echo "[FAIL] $f"
done
```
Expected: 전부 `통과`. 실패가 있으면 **그 스위트만 단독 재실행**해서 소켓 고갈(Windows `WinError 10014`) 여부를 가른다(CLAUDE.md "러너 신뢰성" 절) — 단독 재실행도 실패하면 진짜 회귀다. 33개 스위트(기존 32 + 이 계획이 늘리는 건 `api_contract` 건수 증가뿐, 새 스위트 파일은 없음 — `ls spikes/*.py`로 파일 개수 32 그대로인지 확인)

- [ ] **Step 3: pytest 3파일**

```bash
uv run --with pytest python -m pytest data/rules/test_rules.py backend/agent/test_llm_cache.py data/external/test_elice_docvision.py -q
```
Expected: 83건 통과 그대로(이 계획은 이 3파일을 건드리지 않는다)

- [ ] **Step 4: 프론트 빌드 + ruff**

```bash
cd frontend && npx next build && cd ..
uv run ruff check
```
Expected: 빌드 성공(라우트 18→20), ruff clean

- [ ] **Step 5: `ui_honesty_contract` 실측 건수 확인**

```bash
uv run python spikes/ui_honesty_contract.py
```
출력 마지막 줄의 `PASS N/N` 건수를 기록한다 — 신규 파일 3개(`technician/po/new/page.tsx`·`technician/po/[poId]/page.tsx`·`components/asset/PoForm.tsx`)가 어느 글롭에 걸리는지에 따라 다음 중 하나:
- `app/(console)/**/*.tsx` 글롭이 `technician/po/**`도 잡으면 페이지 2개 × 6건 = +12
- `components/asset/*.tsx` 글롭이 `PoForm.tsx`도 잡으면 +6
- 합쳐서 최대 +18. **실측값을 그대로 쓴다** — 추정치로 CLAUDE.md를 갱신하지 않는다(이 문서가 반복 경고하는 실수).

- [ ] **Step 6: `CLAUDE.md` 최종 기준선 확정**

Task 5에서 미리 적어둔 `api_contract 41`은 유지. `ui_honesty_contract`는 Step 5 실측값으로, 프론트 라우트는 Step 4 빌드 로그의 실제 카운트로, 헤드라인 총합은 (Task 5 시점 헤드라인 + 10 + Step 5의 ui_honesty 증가분)으로 갱신. 새 델타 문단을 CLAUDE.md 기존 델타 문단들 맨 아래에 추가(형식은 기존 문단들과 동일 — "**NNN→MMM**: D111이 ... 나머지 스위트는 무변경").

- [ ] **Step 7: 최종 커밋**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
[M4] docs: D111 회귀 기준선 확정 — spikes/pytest/프론트 라우트/ui_honesty 실측 반영

Task 5의 예비 숫자를 전체 회귀 실행 후 실측값으로 교체. 새 스파이크 파일 없음
(api_contract 건수 증가만), 새 pytest 없음, 프론트 라우트 18→20.
EOF
)"
```

---

## Self-Review 체크리스트 (계획 작성자용 — 실행 전 참고)

- **스펙 커버리지**: §2(D-결정)→Task5, §3(data/po_draft.py)→Task1, §4(백엔드 API)→Task3·4, §5(프론트)→Task6~10, §6(회귀)→Task4·11. §7(열린 질문 — D번호 확정)은 Task5 Step1이 실행 시점에 해소한다.
- **누락 발견 및 보강**: 스펙 §4는 견적 사전 조회(`GET /api/po/quotes/{part_no}`)를 명시하지 않았다 — 브레인스토밍 시점엔 프론트 폼 설계까지 들어가지 않아 드러나지 않은 구멍이었다. 이 계획에서 Task 3·4·6·7에 추가해 메꿨다(공급사를 고르려면 견적을 먼저 봐야 하는데, 기존 REST엔 PO 상세 없이 견적만 보는 경로가 없었다).
- **타입 일관성**: `CreatePoBody`(lib/api.ts, Task 6) — `create_po_draft`/`svc.create`/`svc.update`(Python)의 필드명과 1:1 대응(part_no·qty·supplier_id·reason·urgency) 확인됨. `PoForm`의 `onSubmit` 시그니처가 Task 8·9 양쪽에서 동일하게 `(body: CreatePoBody) => Promise<ApiPo>`로 쓰임 확인됨.
