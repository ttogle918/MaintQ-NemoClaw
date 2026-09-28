# .docx 생성 배선 + facts 읽기 MCP 도구 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 결재 문서 5종(01·02·03·05·06)을 `data/templates/*.docx` 템플릿을 채워 다운로드 시점에 생성하고, 그 필드맵을 조회만 하는 MCP 읽기 도구 1종을 추가한다.

**Architecture:** `data/doc_fields.py` 순수 공유 계층이 DB 행 → 템플릿 필드맵을 만든다(D15 준수 — `mcp_server`도 `backend`도 import 하지 않는다). `backend/services/docx_render.py`가 그 필드맵으로 템플릿을 채워 **메모리에서만** bytes 를 만든다(D86 — 저장 없음). MCP 도구 `get_document_facts`는 같은 필드맵을 **조회만** 하고, 신원·서명 필드는 애초에 만들지 않는다.

**Tech Stack:** Python 3.11+, `python-docx>=1.1`(신규), FastAPI, Postgres(psycopg 3), MCP FastMCP

설계 문서: `docs/superpowers/specs/2026-09-03-docx-and-facts-tool-design.md`

---

## Global Constraints

이 절의 규칙은 **모든 태스크의 요구사항에 암묵적으로 포함된다.**

- **MCP 도구에 UPDATE 를 추가하지 않는다** (절대규칙 1 · D10). 새 도구는 `read_only()` 커넥션만 쓴다. `spikes/write_tool_contract.py` 는 **30건 그대로**여야 하며, 그것이 "쓰기 경로가 안 늘었다"의 증거다.
- **생성물을 디스크·DB 에 저장하지 않는다** (D86). docx bytes 는 `io.BytesIO` 안에서만 존재한다. 임시 파일도 만들지 않는다.
- **문안을 새로 쓰지 않는다.** 라벨은 템플릿 docx 가, 값은 기존 `render_*_document()`·`render_documents()` 의 계산이 갖는다.
- **04(담보대출심사회신서)는 만들지 않는다** — D118, FinAllQ 소관.
- `data/templates/*.docx` 는 **읽기만** 한다. 파일을 수정하지 않는다.
- **필수 파라미터에 기본값을 두지 않는다** (D80).
- **도구는 예외를 던지지 않는다** — `status` 필드로 실패를 반환한다 (D9).
- `data/doc_fields.py` 는 **DB 경로를 모른다.** 커넥션은 호출자가 열어 넘긴다 (`data/po_draft.py` 규약).
- 포매터는 ruff (PostToolUse 훅이 자동 실행). `line-length = 100`.
- 커밋 접두어 `[M4]`.
- 회귀 실행 시 **`DATABASE_URL` 을 반드시 실어야 한다** — 안 실으면 포트 5432 로 떨어져 psycopg 가 **무한 대기**한다(실패가 아니라 멈춤).

  ```bash
  DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)"
  ```

- **기준선: spikes 33스위트 / 1,120건 · seed 41건 · pytest 114건 · 프론트 25라우트 · MCP 도구 20종.**
  작업 후 **34스위트 · MCP 도구 21종**이 된다.

### 선행 조건 — Postgres

`maintq_postgres`(포트 5434) 컨테이너가 떠 있어야 한다. 내려가 있으면 관리자 PowerShell 에서:

```
net stop winnat ; net start winnat ; docker start maintq_postgres
```

**Task 1~6 은 DB 가 필요 없다** — `render_*` 함수들은 dict 를 입력으로 받고 DB 를 읽지 않기 때문이다(`po_documents.py` 상단 docstring 이 명시). DB 는 Task 7 부터 필요하다.

---

## 파일 구조

| 파일 | 책임 | 태스크 |
|---|---|---|
| `pyproject.toml` | `python-docx>=1.1` 의존성 | 1 |
| `backend/services/docx_render.py` | **신설** — 템플릿 채우기. 필드맵 → bytes | 1 |
| `spikes/docx_contract.py` | **신설** — 골든 대조 → 필드맵 → 다운로드 → 읽기 도구 계약 | 2·10 |
| `spikes/golden/*.txt` | **신설** — 리팩터 전 미리보기 스냅샷 | 2 |
| `data/doc_fields.py` | **신설** — 순수 필드맵 계층 + `WITHHELD_KEYS` | 3~7 |
| `backend/services/po_documents.py` | `render_*` 가 `fields_*` 를 소비 (출력 불변) | 3·4·5 |
| `mcp_server/tools/generate_disposal_document.py` | `render_documents` 가 `fields_*` 를 소비 (출력 불변) | 6 |
| `backend/services/po.py` | `get_po()` 의 SELECT+조인을 `po_context()` 로 위임 | 7 |
| `mcp_server/tools/get_document_facts.py` | **신설** — 읽기 전용 도구 (얇은 래퍼) | 8 |
| `mcp_server/server.py` | 확장 블록에 도구 등록 | 8 |
| `spikes/tools_profile_contract.py` | 20 → 21종 | 8 |
| `backend/routers/po.py` · `decisions.py` | 다운로드 엔드포인트 + 신원 주입 | 9 |
| `docs/*` · `CLAUDE.md` | §21 · D124·D125 · 기준선 · 백로그 해소 | 11 |

### 템플릿 플레이스홀더 전수 (정본 — 이 계획의 기준값)

`fields_*()` 는 아래에서 **`WITHHELD_KEYS` 를 뺀 나머지 전부**를 만들어야 한다.

**01 (46)**
`ACTION_COST_1` `ACTION_COST_2` `ACTION_DESC_1` `ACTION_DESC_2` `ACTION_DURATION_1` `ACTION_DURATION_2` `ACTION_TYPE_1` `ACTION_TYPE_2` `DETECTED_AT` `DETECTED_AT_2` `DIAGNOSIS_CONCLUSION` `DOC_NO` `DOC_STATUS` `EQUIPMENT_ID` `EQUIPMENT_NAME` `ERROR_CODE` `ERROR_CODE_2` `EVIDENCE_LOC_1` `EVIDENCE_LOC_2` `EVIDENCE_QUOTE_1` `EVIDENCE_QUOTE_2` `EVIDENCE_SOURCE_1` `EVIDENCE_SOURCE_2` `EVIDENCE_TYPE_1` `EVIDENCE_TYPE_2` `ISSUED_AT` `LOCATION` `MANAGER_NAME` `MANAGER_SIGNED_AT` `REPAIR_REPLACE_VERDICT` `REPEAT_COUNT` `REPEAT_FAULT_FLAG` `REQUEST_CHAIN_ID` `ROOT_CAUSE_MODE` `SAFETY_FLAG` `SAFETY_PRECONDITION` `SAFETY_WARNING` `SEVERITY` `SEVERITY_2` `SIGNATURE_HASH` `SYMPTOM_SUMMARY` `SYMPTOM_SUMMARY_2` `TECHNICIAN_NAME` `TECHNICIAN_SIGNED_AT` `TRACE_ID` `VERDICT_RATIONALE`

**02 (55)**
`ALT_PART_1` `ALT_PART_2` `AMOUNT_1` `AMOUNT_2` `AMOUNT_3` `APPROVAL_COMMENT` `APPROVAL_RESULT` `APPROVER_NAME` `APPROVER_SIGNED_AT` `DIAGNOSIS_DOC_NO` `DOC_STATUS` `EQUIPMENT_ID` `IMPACT_IF_DEFERRED` `LEAD_TIME_1` `LEAD_TIME_2` `PART_NAME_1` `PART_NAME_2` `PART_NAME_3` `PART_NO_1` `PART_NO_2` `PART_NO_3` `PO_REQUEST_NO` `QTY_1` `QTY_2` `QTY_3` `QUOTE_AMOUNT_1` `QUOTE_AMOUNT_2` `QUOTE_NO_1` `QUOTE_NO_2` `REQUESTED_AT` `REQUESTER_DEPT` `REQUESTER_NAME` `REQUESTER_SIGNED_AT` `REQUEST_CHAIN_ID` `REQUEST_REASON` `SELECTED_1` `SELECTED_2` `STOCK_NOTE_1` `STOCK_NOTE_2` `STOCK_QTY_1` `STOCK_QTY_2` `STOCK_VERDICT_1` `STOCK_VERDICT_2` `SUBTOTAL` `TARGET_COMPLETION_DATE` `TOTAL_AMOUNT` `TOTAL_AMOUNT_KOREAN` `UNIT_PRICE_1` `UNIT_PRICE_2` `UNIT_PRICE_3` `URGENCY` `VAT` `VENDOR_1` `VENDOR_2` `VENDOR_SELECTION_REASON`

**03 (41)**
`A2A_DELEGATED` `A2A_TARGET` `AMOUNT` `AMOUNT_KOREAN` `APPROVAL_RESULT` `BUDGET_CHECK` `BUDGET_EVIDENCE` `COLLATERAL_ID` `COLLATERAL_TYPE` `COLLATERAL_VALUE` `DAILY_LIMIT_CHECK` `DAILY_LIMIT_EVIDENCE` `DIAGNOSIS_DOC_NO` `DOC_STATUS` `EXECUTION_DATE` `FDS_EVIDENCE` `FDS_VERDICT` `FINANCE_APPROVER` `FINANCE_SIGNED_AT` `FUNDING_METHOD` `FUND_REQUEST_NO` `FUND_TYPE` `LOAN_AMOUNT` `LTV` `MANAGER_NAME` `MANAGER_SIGNED_AT` `MFA_STATUS` `PAYEE_ACCOUNT_MASKED` `PAYEE_BANK` `PAYEE_BIZ_NO` `PAYEE_NAME` `PO_REQUEST_NO` `PURPOSE` `REPAYMENT_PLAN` `REQUESTED_AT` `REQUESTER_DEPT` `REQUESTER_NAME` `REQUESTER_SIGNED_AT` `REQUEST_CHAIN_ID` `SOD_CHECK` `SOD_EVIDENCE`

**05 (30)**
`ACQUIRED_AT` `ASSET_ID` `ASSET_STATUS` `BUILDING_ID` `BUNDLE_HASH` `CONTRACT_COUNT` `CONTRACT_LINES` `CREATED_AT` `DECISION_ID` `DISPOSAL_DATE` `DISPOSAL_MODE` `DOC_STATE` `LAW_COUNT` `LAW_LINES` `OPEN_CONDITIONS` `OVERRIDE` `OVERRIDE_REASON` `REASON` `REQUESTER_DEPT` `REQUESTER_NAME` `REQUEST_CHAIN_ID` `RULES_EVALUATED` `RULES_OPEN` `RULE_COUNT` `RULE_LINES` `SIGNED_AT` `SIGNED_BY` `TEMPLATE_REVIEW_NOTICE` `VERDICT` `VERDICT_LINE`

**06 (27)**
`ACQUIRED_AT` `ASSET_ID` `ASSET_STATUS` `BUILDING_ID` `BUNDLE_HASH` `CREATED_AT` `DECISION_ID` `DISPOSAL_DATE` `DISPOSAL_MODE` `DOC_STATE` `HAS_LIEN` `INSPECTION_VALID_UNTIL` `INSURED` `LAST_INSPECTION_DATE` `LIEN_CONSENT_REF` `LIEN_CREDITOR` `MONTHS_SINCE_ACQUISITION` `OPEN_CONDITIONS` `POLICY_ID` `REQUEST_CHAIN_ID` `SAFETY_INSPECTION_TARGET` `SIGNED_AT` `SIGNED_BY` `TAX_CREDIT_APPLIED` `TEMPLATE_REVIEW_NOTICE` `VAT_INVOICE_ISSUED` `VERDICT`

### `WITHHELD_KEYS` — 신원·서명 (D23)

`data/doc_fields.py` 가 **만들지 않는다.** 다운로드 엔드포인트(backend)가 DB 에서 읽어 얹는다.

```
TECHNICIAN_NAME  TECHNICIAN_SIGNED_AT  MANAGER_NAME  MANAGER_SIGNED_AT  SIGNATURE_HASH
REQUESTER_NAME   REQUESTER_DEPT        REQUESTER_SIGNED_AT
APPROVER_NAME    APPROVER_SIGNED_AT
FINANCE_APPROVER FINANCE_SIGNED_AT
SIGNED_BY        SIGNED_AT             OVERRIDE      OVERRIDE_REASON
```

**`REQUEST_CHAIN_ID` 는 여기 없다** — 결재선 추적 ID 이지 사람이 아니다. 값 원천이 없는 경로에서는 `확인되지 않음` 이 된다(D62).
`OVERRIDE`·`OVERRIDE_REASON` 이 여기 있는 이유는 D81 이다 — 도구가 채울 수 있으면 LLM 이 추징 감수 사유를 지어내 BLOCKING 을 뚫는 경로가 생긴다.

---

## Task 1: docx 채우기 계층

**Files:**
- Modify: `pyproject.toml`
- Create: `backend/services/docx_render.py`
- Create: `backend/services/test_docx_render.py`

**Interfaces:**
- Consumes: (없음 — 첫 태스크)
- Produces:
  - `DOCX_MIME: str`
  - `TemplateFieldMismatch(Exception)` · `SplitPlaceholderError(Exception)`
  - `template_placeholders(template_filename: str) -> set[str]`
  - `fill_template(template_filename: str, fields: Mapping[str, str], *, drop_rows: Iterable[str] = ()) -> bytes`

**DB 불필요.**

- [ ] **Step 1: 의존성 추가**

`pyproject.toml` 의 `[project].dependencies` 에 한 줄 더한다 (`pdfplumber` 아래, 알파벳 순 무관 — 기존 목록도 주석 그룹 순서다):

```toml
    # 결재 문서 docx 생성 (D124). 순수 pip — pandoc 같은 시스템 바이너리를 늘리지 않는다.
    "python-docx>=1.1",
```

동기화:

```bash
uv sync
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

Create `backend/services/test_docx_render.py`:

```python
# -*- coding: utf-8 -*-
"""docx_render 단위 테스트 — DB 를 쓰지 않는다 (템플릿 파일만 읽는다)."""

from __future__ import annotations

import io
import zipfile

import pytest

from backend.services import docx_render as dr

T05 = "05_설비처분승인서.docx"
T02 = "02_정비부품발주요청서.docx"


def _complete(template: str) -> dict[str, str]:
    """템플릿의 모든 자리를 채운 최소 필드맵."""
    return {k: f"<{k}>" for k in dr.template_placeholders(template)}


def test_placeholders_are_discovered():
    keys = dr.template_placeholders(T05)
    assert len(keys) == 30
    assert "BUNDLE_HASH" in keys and "VERDICT_LINE" in keys


def test_fill_returns_docx_bytes_without_touching_disk():
    data = dr.fill_template(T05, _complete(T05))
    assert isinstance(data, bytes) and data[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "{{" not in xml           # 남은 자리 0
    assert "&lt;BUNDLE_HASH&gt;" in xml or "<BUNDLE_HASH>" in xml


def test_missing_field_raises():
    fields = _complete(T05)
    del fields["BUNDLE_HASH"]
    with pytest.raises(dr.TemplateFieldMismatch) as e:
        dr.fill_template(T05, fields)
    assert "BUNDLE_HASH" in str(e.value)


def test_extra_field_raises():
    fields = _complete(T05) | {"NOT_IN_TEMPLATE": "x"}
    with pytest.raises(dr.TemplateFieldMismatch) as e:
        dr.fill_template(T05, fields)
    assert "NOT_IN_TEMPLATE" in str(e.value)


def test_drop_rows_removes_the_row_and_its_keys():
    """표 2행째를 통째로 지운다 — 빈 칸을 '해당 없음'으로 읽히게 두지 않는다 (D62)."""
    keys = dr.template_placeholders(T02)
    dropped = {k for k in keys if k.endswith(("_2", "_3"))}
    fields = {k: f"<{k}>" for k in keys - dropped}
    data = dr.fill_template(T02, fields, drop_rows=dropped)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "{{" not in xml
    assert "<PART_NO_1>" in xml
    assert "PART_NO_2" not in xml


def test_unknown_template_raises():
    with pytest.raises(FileNotFoundError):
        dr.fill_template("99_없는문서.docx", {})


def test_template_is_not_modified():
    """원본 파일은 손대지 않는다 (절대규칙 5 정신 — 템플릿은 정본이다)."""
    path = dr.TEMPLATE_DIR / T05
    before = path.read_bytes()
    dr.fill_template(T05, _complete(T05))
    assert path.read_bytes() == before
```

- [ ] **Step 3: 실패 확인**

```bash
uv run --with pytest python -m pytest backend/services/test_docx_render.py -q
```

Expected: 전건 FAIL — `ModuleNotFoundError: No module named 'backend.services.docx_render'`

- [ ] **Step 4: 구현**

Create `backend/services/docx_render.py`:

```python
# -*- coding: utf-8 -*-
"""docx_render — 결재 문서 템플릿을 채워 **메모리에서만** .docx bytes 를 만든다 (D124).

★ 저장하지 않는다 (D86)
────────────────────────────────────────────────────────────────────────────────
원본 템플릿을 읽어 `io.BytesIO` 에 저장하고 그 bytes 를 돌려준다. 디스크에도 DB 에도
아무것도 남기지 않는다 — 임시 파일조차 만들지 않는다. 저장하면 템플릿·산식이 바뀔 때
저장본이 조용히 낡는다(D57·D86 선례).

★ 양방향 strict — 왜 관대하게 만들지 않는가
────────────────────────────────────────────────────────────────────────────────
  · 템플릿에 있는데 fields 에 없는 키 → 그대로 두면 **결재 서류에 `{{X}}` 가 인쇄된다.**
    테스트가 아니라 코드가 막아야 하는 종류다.
  · fields 에 있는데 템플릿에 없는 키 → 템플릿과 코드가 갈렸다는 뜻이다. 조용히 무시하면
    아무도 모른다 — D90 이 겪은 "같은 문장이 두 곳에 있어 한쪽만 바뀐다"와 같은 유형이다.

★ 런 분할을 조용히 처리하지 않는다
────────────────────────────────────────────────────────────────────────────────
2026-09-03 실측에서 5종 템플릿 전부 플레이스홀더가 단일 `<w:t>` 안에 온전했다. 그래서
run-merge 로직을 선제적으로 넣지 않는다. 대신 분할을 **발견하면 명시적으로 실패**시킨다 —
조용히 넘기면 나중에 템플릿이 편집돼 분할이 생겼을 때 값이 안 채워진 문서가 결재에 올라간다.
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

from docx import Document

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "data" / "templates"

_PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


class TemplateFieldMismatch(Exception):
    """템플릿 자리와 fields 키가 어긋났다. 어느 쪽이 남았는지 메시지에 적는다."""


class SplitPlaceholderError(Exception):
    """플레이스홀더가 여러 run 으로 쪼개져 있다 — 치환하면 값이 안 들어간다."""


def _template_path(template_filename: str) -> Path:
    path = TEMPLATE_DIR / template_filename
    if not path.is_file():
        raise FileNotFoundError(f"템플릿이 없습니다: {path}")
    return path


def _iter_tables(container) -> Iterator:
    for table in container.tables:
        yield table
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_tables(cell)


def _iter_paragraphs(container) -> Iterator:
    yield from container.paragraphs
    for table in container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_paragraphs(cell)


def _all_paragraphs(doc) -> Iterator:
    yield from _iter_paragraphs(doc)
    for section in doc.sections:
        yield from _iter_paragraphs(section.header)
        yield from _iter_paragraphs(section.footer)


def _all_tables(doc) -> Iterator:
    yield from _iter_tables(doc)
    for section in doc.sections:
        yield from _iter_tables(section.header)
        yield from _iter_tables(section.footer)


def _found(doc) -> set[str]:
    keys: set[str] = set()
    for p in _all_paragraphs(doc):
        keys |= set(_PLACEHOLDER.findall(p.text))
    return keys


def _assert_not_split(doc) -> None:
    for p in _all_paragraphs(doc):
        joined = set(_PLACEHOLDER.findall(p.text))
        if not joined:
            continue
        per_run: set[str] = set()
        for run in p.runs:
            per_run |= set(_PLACEHOLDER.findall(run.text))
        if split := joined - per_run:
            raise SplitPlaceholderError(
                f"플레이스홀더가 여러 run 으로 쪼개져 있습니다: {sorted(split)}"
            )


def template_placeholders(template_filename: str) -> set[str]:
    """템플릿이 요구하는 자리 전부. 계약 검증과 테스트가 기대값을 여기서 파생시킨다."""
    return _found(Document(str(_template_path(template_filename))))


def _drop_rows(doc, keys: set[str]) -> set[str]:
    """`keys` 중 하나라도 든 표 행을 삭제한다. 삭제로 사라진 자리 집합을 돌려준다.

    빈 칸을 `확인되지 않음` 으로 채우지 않고 행 자체를 없애는 이유는 미리보기와 같다 —
    `po_documents.py` 가 *"없는 2·3행을 빈 칸으로 채우지 않고 아예 생략한다"* 고 못박았다.
    빈 칸은 읽는 사람에게 **'해당 없음'으로 읽힌다**(D62).
    """
    removed: set[str] = set()
    for table in _all_tables(doc):
        for row in list(table.rows):
            in_row = set(_PLACEHOLDER.findall("".join(c.text for c in row.cells)))
            if in_row & keys:
                removed |= in_row
                row._element.getparent().remove(row._element)
    return removed


def fill_template(
    template_filename: str,
    fields: Mapping[str, str],
    *,
    drop_rows: Iterable[str] = (),
) -> bytes:
    """템플릿을 채워 .docx bytes 를 돌려준다. 어디에도 저장하지 않는다 (D86).

    `drop_rows` 에 든 자리를 품은 표 행은 채우기 전에 삭제된다 — 그 행의 자리들은
    `fields` 에 없어도 된다.
    """
    doc = Document(str(_template_path(template_filename)))
    _assert_not_split(doc)

    dropped = _drop_rows(doc, set(drop_rows)) if drop_rows else set()
    required = _found(doc)
    given = set(fields)

    if missing := required - given:
        raise TemplateFieldMismatch(
            f"{template_filename}: 템플릿에 있는데 값이 없는 자리 {sorted(missing)}"
        )
    if extra := given - required - dropped:
        raise TemplateFieldMismatch(
            f"{template_filename}: 값은 있는데 템플릿에 없는 키 {sorted(extra)}"
        )

    for p in _all_paragraphs(doc):
        for run in p.runs:
            if "{{" in run.text:
                run.text = _PLACEHOLDER.sub(lambda m: fields[m.group(1)], run.text)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
uv run --with pytest python -m pytest backend/services/test_docx_render.py -q
```

Expected: `7 passed`

- [ ] **Step 6: 커밋**

```bash
git add pyproject.toml uv.lock backend/services/docx_render.py backend/services/test_docx_render.py
git commit -m "[M4] feat(docx): 템플릿 채우기 계층 — 메모리에서만 bytes 조립 (D86·D124)"
```

---

## Task 2: 골든 스냅샷 — 리팩터 전 출력을 고정한다

**Files:**
- Create: `spikes/docx_contract.py`
- Create: `spikes/golden/` (스냅샷 5개)

**Interfaces:**
- Consumes: `backend.services.po_documents.render_po_request_document` / `render_diagnosis_document` / `render_fund_execution_document`, `mcp_server.tools.generate_disposal_document.render_documents`
- Produces:
  - `spikes/docx_contract.py` 안의 `FIXTURE_PO: dict` · `FIXTURE_BUNDLE: dict` · `FIXTURE_CONTROLS` · `FIXTURE_A2A` · `FIXTURE_PAYEE`
  - `check(name, ok, detail)` · `results` (기존 스파이크와 같은 하네스)

**DB 불필요** — `render_*` 는 전부 dict 를 입력으로 받고 DB 를 읽지 않는다(`po_documents.py` 상단 docstring 이 명시).

### 왜 이 태스크가 먼저인가

Task 3~6 이 `render_*` 를 필드맵 소비 형태로 재작성한다. 그 문자열은 `spikes/api_contract.py` 52건과 화면(`DocumentPreview.tsx`)이 함께 본다. **리팩터 전에 출력을 고정해 두지 않으면 미묘하게 바뀐 것을 아무도 못 잡는다.**

### 이건 부재검사 계열이다

"차이가 없다"는 주장은 *사실이 참* 과 *스캐너가 눈이 멀었다* 를 구분하지 못한다. 골든 파일이 비거나 경로가 바뀌면 **조용히 통과**한다. CLAUDE.md 규칙대로 판정에 양성 축을 넣고, detail 에는 결론이 아니라 실측값을 찍는다.

- [ ] **Step 1: 스파이크 골격 + 픽스처를 쓴다**

Create `spikes/docx_contract.py`:

```python
# -*- coding: utf-8 -*-
"""docx 생성 + facts 읽기 도구 계약 검증 (D124·D125).

## 무엇을 보는가

  A. **골든 대조** — `render_*_document()`·`render_documents()` 의 평문 출력이
     필드맵 리팩터 전후로 **바이트 동일**한가. 이 문자열은 `api_contract` 52건과
     화면(`DocumentPreview.tsx`)이 함께 본다.
  B. 필드맵 — `data/doc_fields.py` 가 템플릿 자리를 **빠짐없이** 만드는가,
     `WITHHELD_KEYS` 를 **하나도** 만들지 않는가
  C. 채우기 — `fill_template()` 양방향 strict · 표 행 삭제 · 무저장
  D. 다운로드 엔드포인트 — MIME · Content-Disposition · 가용성 규칙
  E. 읽기 도구 — 조회만 · withheld/unavailable 분리 · 실패는 status

## A 는 부재검사다 — liveness 앵커를 함께 건다

"차이가 없다"는 원리적으로 *사실이 참* 과 *스캐너가 눈이 멀었다* 를 구분하지 못한다.
골든 파일이 비거나 경로가 바뀌면 조용히 통과한다. 그래서:

  · 판정식에 **양성 축**을 넣는다 — `골든 개수 == 기대치 and 전건 일치`
  · detail 에 **결론이 아니라 실측값**을 찍는다 (`"출력 불변 확인"` 같은 하드코딩 문구는
    FAIL 일 때도 그대로 인쇄돼 표를 읽는 사람이 정반대로 이해한다)
  · 뮤턴트로 실증한다 — 렌더 문구 한 글자를 바꾸면 A 만 FAIL 해야 한다

## DB 를 쓰지 않는 부분이 있다

A~C 는 픽스처 dict 만으로 돈다 — `render_*` 는 DB 를 읽지 않기 때문이다
(`po_documents.py` 상단 docstring). D·E 만 격리 스키마 Postgres 를 쓴다.

실행:  DATABASE_URL=... uv run python spikes/docx_contract.py
       DOCX_CONTRACT_REGOLD=1 ... → 골든 재생성 (리팩터 전에만!)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, bool(ok), detail))


# ── 픽스처 ─────────────────────────────────────────────────────────────────────
# DB 를 읽지 않는다. 값은 시드(PO-0117 계열)를 본떴지만 **고정 리터럴**이다 —
# 시드가 바뀌어도 골든이 흔들리지 않아야 리팩터 회귀로서 의미가 있다.

FIXTURE_PO: dict = {
    "po_id": "PO-0117",
    "state": "pending",
    "created_at": "2026-08-30T04:12:00Z",
    "decided_at": "2026-08-31T02:00:00Z",
    "session_id": "S1",
    "part_no": "LS-IG5A-FAN-01",
    "part_name": "냉각팬 어셈블리",
    "qty": 3,
    "unit_price": 48000,
    "supplier_id": "SUP-02",
    "supplier_name": "대한산전",
    "urgency": "normal",
    "reason": "E-011 과열 경보 반복 — 냉각팬 베어링 마모로 판단",
    "model": "iG5A",
    "error_code": "E-011",
    "decision_note": None,
    "requested_by": "tech-01",
    "requested_by_name": "김정비",
    "requested_by_department": "설비보전팀",
    "decided_by": None,
    "decided_by_name": "",
    "finance_decided_by": None,
    "finance_decided_by_name": "",
    "finance_decided_at": None,
    "finance_decision_note": None,
    "evidence": {
        "symptoms": ["과열 경보", "팬 소음 증가"],
        "basis": [
            {"tool": "lookup_error_code", "manual_page": 74},
            {"tool": "search_inventory", "part_no": "LS-IG5A-FAN-01", "qty": 1, "safety_stock": 2},
        ],
    },
    "quotes": [
        {"supplier_id": "SUP-02", "name": "대한산전", "lead_days": 3, "unit_price": 48000},
        {"supplier_id": "SUP-03", "name": "우진전기", "lead_days": 7, "unit_price": 45500},
    ],
    "inventory": {"qty": 1, "safety_stock": 2, "location": "A동 자재창고 3열"},
    "alternatives": [
        {"alt_part_no": "LS-IG5A-FAN-01R", "alt_part_name": "냉각팬 어셈블리(리퍼)", "note": ""}
    ],
    "error_code_def": {
        "error_name": "방열판 과열",
        "severity": "fault",
        "causes": ["냉각팬 고장", "방열핀 분진 누적"],
        "actions": ["냉각팬 교체", "방열핀 청소"],
        "manual_page": 74,
    },
}

FIXTURE_CONTROLS: dict = {
    "budget": (True, "분기 예산 잔액 12,400,000원 ≥ 요청 158,400원"),
    "daily_limit": (True, "1일 누적 3,200,000원 + 158,400원 ≤ 한도 20,000,000원"),
    "fds": ("PASS", "금액·수취인·시간대 이상 징후 없음"),
    "sod": (True, "기안 tech-01 · 승인 mgr-01 · 재무 fin-01 — 3인 분리"),
}

FIXTURE_A2A: dict = {"status": "ok", "request_chain_id": "CHAIN-SETTLE-e1281b75"}
FIXTURE_PAYEE: dict = {"account_number": "110234567890", "bank_code": "신한은행"}

FIXTURE_BUNDLE: dict = {
    "facts": {
        "asset_id": "AST-L3-CONV",
        "building_id": "BLD-A",
        "status": "IN_USE",
        "acquired_at": "2025-03-14",
        "tax_credit_applied": True,
        "has_lien": True,
        "lien_creditor": "국민은행",
        "lien_consent_ref": "",
        "insured": True,
        "policy_id": "POL-2025-118",
        "safety_inspection_target": True,
        "last_inspection_date": "2025-09-01",
        "inspection_valid_until": "2026-09-01",
        "disposal_mode": "SALE",
        "vat_invoice_issued": False,
        "disposal_date": "2026-10-01",
        "months_since_acquisition": 18,
    },
    "laws": [
        {
            "law_ref_id": "조특법-제146조",
            "effective_from": "2024-01-01",
            "text_hash": "sha256:aa11bb22",
        }
    ],
    "rules": [{"rule_id": "TAX-CREDIT-2Y", "rule_version": 3, "rule_hash": "sha256:cc33dd44"}],
    "evaluated": [
        {
            "rule_id": "TAX-CREDIT-2Y",
            "rule_version": 3,
            "verdict": "TRIGGERED",
            "law_refs": ["조특법-제146조"],
        },
        {"rule_id": "LIEN-CONSENT", "rule_version": 2, "verdict": "HOLD", "law_refs": []},
        {"rule_id": "SAFETY-VALID", "rule_version": 1, "verdict": "CLEAR", "law_refs": []},
    ],
    "contracts": [{"contract_ref": "여신거래약정서 제12조", "text_hash": None, "hash_fixed": False}],
}

FIXTURE_DISPOSAL_KW: dict = {
    "verdict": "PRECONDITION",
    "bundle_hash": "sha256:ee55ff66",
    "reason": "노후 컨베이어 매각 검토 — 라인 재배치",
    "decision_id": "DEC-0007",
}


# ── A. 골든 대조 ───────────────────────────────────────────────────────────────
def _previews() -> dict[str, str]:
    """리팩터 전후로 **바이트 동일**해야 하는 문자열 5종."""
    from backend.services import po_documents as pd
    from mcp_server.tools.generate_disposal_document import render_documents

    docs = render_documents(FIXTURE_BUNDLE, **FIXTURE_DISPOSAL_KW)
    return {
        "01_diagnosis": pd.render_diagnosis_document(FIXTURE_PO),
        "02_po_request": pd.render_po_request_document(FIXTURE_PO),
        "03_fund_execution": pd.render_fund_execution_document(
            FIXTURE_PO, FIXTURE_CONTROLS, FIXTURE_A2A, FIXTURE_PAYEE
        ),
        "05_approval": docs["approval"],
        "06_representation_warranty": docs["representation_warranty"],
    }


EXPECTED_GOLDEN_COUNT = 5


def regold() -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)
    for name, text in _previews().items():
        (GOLDEN_DIR / f"{name}.txt").write_text(text, encoding="utf-8")
    print(f"골든 {EXPECTED_GOLDEN_COUNT}건 재생성 → {GOLDEN_DIR}")


def run_golden() -> None:
    current = _previews()
    stored = {p.stem: p.read_text(encoding="utf-8") for p in sorted(GOLDEN_DIR.glob("*.txt"))}

    # ★ 양성 축 — 골든이 실제로 존재하고 개수가 맞아야 "일치"가 의미를 갖는다.
    #   이게 없으면 골든 디렉터리가 비었을 때 `all([])` 가 True 라 조용히 통과한다.
    total_bytes = sum(len(v.encode("utf-8")) for v in stored.values())
    check(
        "A① 골든 스냅샷 존재 (liveness 앵커)",
        len(stored) == EXPECTED_GOLDEN_COUNT and total_bytes > 0,
        f"골든 {len(stored)}/{EXPECTED_GOLDEN_COUNT}건 · 총 {total_bytes:,}바이트",
    )

    matched = [n for n in stored if stored[n] == current.get(n)]
    differing = sorted(set(stored) - set(matched))
    check(
        "A② 미리보기 출력 불변 (바이트 동일)",
        len(stored) == EXPECTED_GOLDEN_COUNT and not differing,
        f"일치 {len(matched)}/{len(stored)}건"
        + (f" · 불일치 {differing}" if differing else " · 불일치 없음"),
    )

    for name in sorted(current):
        cur, old = current[name], stored.get(name)
        check(
            f"A③ {name}",
            old is not None and cur == old,
            f"현재 {len(cur.encode('utf-8')):,}바이트 / 골든 "
            + (f"{len(old.encode('utf-8')):,}바이트" if old is not None else "없음"),
        )


def main() -> None:
    if os.environ.get("DOCX_CONTRACT_REGOLD"):
        regold()
        return

    run_golden()

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 34))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 34))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건:\n  - " + "\n  - ".join(failed))
    print(f"\n통과 ({len(results)}건) — 골든 대조")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 골든이 없으면 실패하는지 확인**

```bash
uv run python spikes/docx_contract.py
```

Expected: FAIL — `A① 골든 스냅샷 존재` 가 `골든 0/5건 · 총 0바이트` 로 떨어진다.
**이게 liveness 앵커가 작동한다는 증거다** — 앵커가 없었다면 `A②` 가 `all([])` 로 통과했을 것이다.

- [ ] **Step 3: 골든 생성**

```bash
DOCX_CONTRACT_REGOLD=1 uv run python spikes/docx_contract.py
```

Expected: `골든 5건 재생성 → .../spikes/golden`

- [ ] **Step 4: 통과 확인**

```bash
uv run python spikes/docx_contract.py
```

Expected: `통과 (7건) — 골든 대조` (A① · A② · A③ × 5)

- [ ] **Step 5: 뮤턴트로 실증한다**

`backend/services/po_documents.py` 의 `_FUND_TYPE = "부품 구매대금"` 을 `"부품 구매대금 "`(뒤 공백 1칸)으로 임시 변경하고:

```bash
uv run python spikes/docx_contract.py
```

Expected: `A② 미리보기 출력 불변` 과 `A③ 03_fund_execution` **2건만** FAIL. 나머지 PASS.
확인 후 **되돌린다** (`git checkout -- backend/services/po_documents.py`).

- [ ] **Step 6: 커밋**

```bash
git add spikes/docx_contract.py spikes/golden
git commit -m "[M4] test(docx): 골든 스냅샷 — 필드맵 리팩터 전 미리보기 출력 고정

리팩터 전에 render_*_document()·render_documents() 의 평문 출력을 바이트로 고정한다.
그 문자열은 api_contract 52건과 DocumentPreview.tsx 가 함께 본다.

부재검사라 liveness 앵커를 함께 걸었다 — 골든 0건일 때 all([]) 로 조용히 통과하는
것을 A① 이 막는다(골든 없이 실행해 FAIL 을 실측). 뮤턴트로도 실증했다: _FUND_TYPE 에
공백 1칸을 더하면 A②·A③(03) 2건만 FAIL 한다."
```

---

## Task 3: `data/doc_fields.py` 골격 + `fields_02`

**Files:**
- Create: `data/doc_fields.py`
- Modify: `backend/services/po_documents.py`
- Modify: `spikes/docx_contract.py` (B 축 추가)

**Interfaces:**
- Consumes: Task 1 의 `template_placeholders()`, Task 2 의 `check()`·`FIXTURE_PO`
- Produces:
  - `data.doc_fields.WITHHELD_KEYS: frozenset[str]`
  - `data.doc_fields.UNKNOWN: str = "확인되지 않음"`
  - `data.doc_fields.fields_02(ctx: dict) -> dict[str, str]`
  - `data.doc_fields.drop_rows_02(ctx: dict) -> set[str]`

### 규칙 — 이 태스크와 Task 4·5·6 에 공통

1. `fields_NN(ctx)` 는 **해당 템플릿의 자리 − `WITHHELD_KEYS`** 를 정확히 만든다. 더도 덜도 아니다.
2. 값 원천이 없으면 `UNKNOWN`. **지어내지 않는다** (D62).
3. `drop_rows_NN(ctx)` 는 실제 항목 수를 넘는 표 행의 자리를 돌려준다. `po_drafts` 는 부품 1건짜리 발주라 02 의 `_2`·`_3` 은 **항상** 삭제 대상이다.
4. `render_*_document()` 는 같은 `fields` dict 를 소비하도록 재작성하되 **출력은 한 바이트도 바뀌지 않아야 한다.** 골든이 그것을 지킨다.
5. 블록형 서술(`_stock_section`·`_quotes_section`·`_evidence_lines` 등)은 템플릿의 칸 단위와 입도가 다르다 — **그 헬퍼들은 `po_documents.py` 에 남긴다.** 공유하는 것은 `ctx` 와 스칼라 값이다.

- [ ] **Step 1: 실패하는 검사를 쓴다**

`spikes/docx_contract.py` 에 B 축을 더한다 (`run_golden()` 아래):

```python
# ── B. 필드맵 ──────────────────────────────────────────────────────────────────
def run_fields() -> None:
    from backend.services.docx_render import template_placeholders
    from data import doc_fields as df

    cases = [
        ("02", "02_정비부품발주요청서.docx", df.fields_02(FIXTURE_PO), df.drop_rows_02(FIXTURE_PO)),
    ]
    for tag, template, fields, dropped in cases:
        slots = template_placeholders(template)
        expected = slots - df.WITHHELD_KEYS - dropped
        missing, extra = expected - set(fields), set(fields) - expected
        check(
            f"B① {tag} 필드맵이 템플릿 자리를 빠짐없이 만든다",
            not missing and not extra,
            f"템플릿 {len(slots)}자리 − withheld {len(slots & df.WITHHELD_KEYS)}"
            f" − 삭제행 {len(dropped)} = 기대 {len(expected)} / 실제 {len(fields)}"
            + (f" · 부족 {sorted(missing)}" if missing else "")
            + (f" · 초과 {sorted(extra)}" if extra else ""),
        )
        leaked = sorted(set(fields) & df.WITHHELD_KEYS)
        check(
            f"B② {tag} 신원·서명 필드를 만들지 않는다 (D23)",
            not leaked and bool(fields),
            f"필드 {len(fields)}개 중 withheld 유출 {len(leaked)}개"
            + (f" {leaked}" if leaked else "")
            + f" · withheld 정의 {len(df.WITHHELD_KEYS)}개",
        )
        check(
            f"B③ {tag} 모든 값이 문자열이다",
            bool(fields) and all(isinstance(v, str) for v in fields.values()),
            f"문자열 {sum(1 for v in fields.values() if isinstance(v, str))}/{len(fields)}",
        )
```

`main()` 의 `run_golden()` 다음 줄에 `run_fields()` 를 넣는다.

- [ ] **Step 2: 실패 확인**

```bash
uv run python spikes/docx_contract.py
```

Expected: `ModuleNotFoundError: No module named 'data.doc_fields'`

- [ ] **Step 3: `data/doc_fields.py` 골격 + `fields_02` 구현**

Create `data/doc_fields.py`:

```python
# -*- coding: utf-8 -*-
"""doc_fields — 결재 문서 템플릿 필드맵 산출 공유 계층 (D124).

`backend/services/po_documents.py`(미리보기)·`backend/services/docx_render.py`(docx)·
`mcp_server/tools/get_document_facts.py`(읽기 도구)가 이 모듈로 위임한다 —
`data/po_draft.py`·`data/maint_value.py` 와 같은 구조다.

이 모듈은 `mcp_server` 도 `backend` 도 import 하지 않는다 (D15 — 두 런타임 프로세스의
상호 import 금지). 커넥션은 호출자가 열어서 넘긴다 — 이 모듈은 DB 경로를 모른다.

★ 신원·서명 필드는 여기서 만들지 않는다 (D23·D37)
────────────────────────────────────────────────────────────────────────────────
`WITHHELD_KEYS` 는 이 계층이 **만들지 않는** 자리 목록이다. 다운로드 엔드포인트(backend)가
DB 에서 읽어 마지막에 얹는다. "빼는" 것이 아니라 "만들지 않는" 것이 핵심이다 — 만든 뒤
빼면 그건 **규율**이지만, 애초에 만들지 않으면 **구조**다. D10 이 UPDATE 를 규율이 아니라
TEMP TRIGGER 로 막은 것과 같은 태도다.

`OVERRIDE`·`OVERRIDE_REASON` 이 여기 있는 이유는 D81 이다 — 도구가 채울 수 있으면
LLM 이 추징 감수 사유를 지어내 BLOCKING 을 뚫는 경로가 생긴다.

`REQUEST_CHAIN_ID` 는 `WITHHELD_KEYS` 에 **없다** — 결재선 추적 ID 이지 사람이 아니다.
   값 원천이 없는 경로에서는 `UNKNOWN` 이 된다.

★ 값이 없으면 지어내지 않는다 (D62)
────────────────────────────────────────────────────────────────────────────────
원천이 없는 자리는 `UNKNOWN`("확인되지 않음")이다. 빈 문자열로 두지 않는다 — 서류의
빈 칸은 읽는 사람에게 **"해당 없음"으로 읽힌다.**
"""

from __future__ import annotations

from typing import Any

UNKNOWN = "확인되지 않음"

WITHHELD_KEYS = frozenset(
    {
        # 01
        "TECHNICIAN_NAME",
        "TECHNICIAN_SIGNED_AT",
        "MANAGER_NAME",
        "MANAGER_SIGNED_AT",
        "SIGNATURE_HASH",
        # 02 · 03
        "REQUESTER_NAME",
        "REQUESTER_DEPT",
        "REQUESTER_SIGNED_AT",
        "APPROVER_NAME",
        "APPROVER_SIGNED_AT",
        "FINANCE_APPROVER",
        "FINANCE_SIGNED_AT",
        # 05 · 06
        "SIGNED_BY",
        "SIGNED_AT",
        "OVERRIDE",
        "OVERRIDE_REASON",
    }
)


def val(v: Any) -> str:
    """값 → 문자열. None·공백이면 UNKNOWN."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return UNKNOWN
    return str(v)


def won(v: int | None) -> str:
    return UNKNOWN if v is None else f"{v:,}"


def yn(d: dict, key: str) -> str:
    """불리언 사실 → 예/아니오. **키가 없으면 UNKNOWN** (D62 — 빈칸은 '아니오'로 읽힌다)."""
    if key not in d:
        return UNKNOWN
    v = d[key]
    return ("예" if v else "아니오") if isinstance(v, bool) else str(v)
```

이어서 **02 전용 상수·산출부**를 같은 파일에 더한다. 라벨 문자열은 `po_documents.py` 의 기존 상수를 **그대로 옮긴다**(새로 쓰지 않는다):

```python
# ── 02 정비부품발주요청서 ──────────────────────────────────────────────────────
_URGENCY_LABEL = {"urgent": "긴급", "normal": "보통"}

_DOC_STATUS_LABEL = {
    "draft": "초안 (미제출)",
    "pending": "결재 대기",
    "approved": "승인 완료",
    "rejected": "반려",
    "finance_approved": "재무 승인 완료",
    "finance_rejected": "재무 반려",
}

_APPROVAL_RESULT_LABEL = {
    "draft": "미제출",
    "pending": "결재 대기 중",
    "approved": "승인",
    "rejected": "반려",
    "finance_approved": "재무 승인",
    "finance_rejected": "재무 반려",
}

_DECIDED_STATES = ("approved", "rejected", "finance_approved", "finance_rejected")


def amounts(ctx: dict) -> tuple[int, int, int]:
    """(공급가액, 부가세, 합계). 03 도 같은 값을 써야 하므로 한 곳에서만 계산한다."""
    subtotal = ctx["unit_price"] * ctx["qty"]
    vat = round(subtotal * 0.1)
    return subtotal, vat, subtotal + vat


def doc_status(ctx: dict) -> str:
    return _DOC_STATUS_LABEL.get(ctx["state"], ctx["state"])


def approval_result(ctx: dict) -> str:
    return _APPROVAL_RESULT_LABEL.get(ctx["state"], ctx["state"])


def drop_rows_02(ctx: dict) -> set[str]:
    """`po_drafts` 는 부품 1건짜리 발주라 품목 표 2·3행은 **항상** 삭제한다.

    미리보기가 *"없는 2·3행을 빈 칸으로 채우지 않고 아예 생략한다"* 고 한 것과 같은 태도다.
    견적 표(`_2`)는 견적이 2건 미만일 때만 지운다.
    """
    dropped = {
        "PART_NO_2", "PART_NAME_2", "QTY_2", "UNIT_PRICE_2", "AMOUNT_2",
        "PART_NO_3", "PART_NAME_3", "QTY_3", "UNIT_PRICE_3", "AMOUNT_3",
    }
    if len(ctx.get("quotes") or []) < 2:
        dropped |= {"QUOTE_NO_2", "VENDOR_2", "LEAD_TIME_2", "QUOTE_AMOUNT_2", "SELECTED_2"}
    if not (ctx.get("inventory")):
        dropped |= {"STOCK_QTY_2", "STOCK_VERDICT_2", "STOCK_NOTE_2", "ALT_PART_2"}
    else:
        dropped |= {"STOCK_QTY_2", "STOCK_VERDICT_2", "STOCK_NOTE_2", "ALT_PART_2"}
    return dropped


def fields_02(ctx: dict) -> dict[str, str]:
    qty = ctx["qty"]
    subtotal, vat, total = amounts(ctx)
    inv = ctx.get("inventory")
    quotes = ctx.get("quotes") or []
    alts = ctx.get("alternatives") or []
    from data.korean_number import amount_to_korean

    f = {
        "PO_REQUEST_NO": ctx["po_id"],
        "REQUESTED_AT": val(ctx.get("created_at")),
        "DIAGNOSIS_DOC_NO": f"DIAG-{ctx['session_id']}" if ctx.get("session_id") else UNKNOWN,
        "EQUIPMENT_ID": UNKNOWN,  # po_drafts 는 설비 인스턴스를 기록하지 않는다
        "URGENCY": _URGENCY_LABEL.get(ctx.get("urgency"), val(ctx.get("urgency"))),
        "DOC_STATUS": doc_status(ctx),
        "REQUEST_CHAIN_ID": UNKNOWN,
        "REQUEST_REASON": ctx["reason"],
        "IMPACT_IF_DEFERRED": UNKNOWN,
        "TARGET_COMPLETION_DATE": UNKNOWN,
        "PART_NO_1": ctx["part_no"],
        "PART_NAME_1": ctx["part_name"],
        "QTY_1": str(qty),
        "UNIT_PRICE_1": won(ctx["unit_price"]),
        "AMOUNT_1": won(subtotal),
        "SUBTOTAL": won(subtotal),
        "VAT": won(vat),
        "TOTAL_AMOUNT": won(total),
        "TOTAL_AMOUNT_KOREAN": amount_to_korean(total),
        "STOCK_QTY_1": str(inv["qty"]) if inv else UNKNOWN,
        "STOCK_VERDICT_1": ("충분" if inv["qty"] >= qty else "부족") if inv else UNKNOWN,
        "STOCK_NOTE_1": val(inv.get("location")) if inv else UNKNOWN,
        "ALT_PART_1": (
            ", ".join(f'{a["alt_part_no"]}({a["alt_part_name"]})' for a in alts)
            if alts
            else "없음 (호환 확인된 대체품 없음)"
        ),
        "VENDOR_SELECTION_REASON": UNKNOWN,
        "APPROVAL_RESULT": approval_result(ctx),
        "APPROVAL_COMMENT": val(ctx.get("decision_note")),
    }
    for i, q in enumerate(quotes[:2], start=1):
        f[f"QUOTE_NO_{i}"] = f'Q-{ctx["po_id"]}-{q["supplier_id"]}'
        f[f"VENDOR_{i}"] = q["name"]
        f[f"LEAD_TIME_{i}"] = f'{q["lead_days"]}일'
        f[f"QUOTE_AMOUNT_{i}"] = won(q["unit_price"] * qty)
        f[f"SELECTED_{i}"] = "선정" if q["supplier_id"] == ctx["supplier_id"] else ""
    return f
```

- [ ] **Step 4: `render_po_request_document()` 를 `fields_02` 소비로 재작성**

`backend/services/po_documents.py` 에서:
- 모듈 상단 상수 `_UNKNOWN`·`_URGENCY_LABEL`·`_DOC_STATUS_LABEL`·`_APPROVAL_RESULT_LABEL`·`_val`·`_won` 을 `data.doc_fields` 재수출로 바꾼다 (이름은 그대로 두어 다른 함수가 계속 쓰게 한다):

```python
from data.doc_fields import UNKNOWN as _UNKNOWN, val as _val, won as _won
import data.doc_fields as _df
```

- `render_po_request_document()` 본문에서 스칼라를 `f = _df.fields_02(po)` 로부터 가져온다. **f-string 의 리터럴 텍스트는 한 글자도 바꾸지 않는다.** 예:

```python
def render_po_request_document(po: dict) -> str:
    f = _df.fields_02(po)
    subtotal, vat, total = _df.amounts(po)
    approver_signed_at = (
        _UNKNOWN if po["state"] in _df._DECIDED_STATES else "(미기재 — 결재 전)"
    )
    return f"""[정비 · 부품 발주 요청서 — {f["DOC_STATUS"]}]
요청번호: {f["PO_REQUEST_NO"]}
요청일시: {f["REQUESTED_AT"]}
연계 진단서: {f["DIAGNOSIS_DOC_NO"]}
...
"""
```

`_stock_section()`·`_quotes_section()` 은 **그대로 둔다** — 템플릿의 칸 단위와 입도가 다르다.

- [ ] **Step 5: 골든 + B 축 통과 확인**

```bash
uv run python spikes/docx_contract.py
```

Expected: `통과 (10건)` — A 7건 + B 3건. **A② 가 계속 PASS 여야 한다**(출력 불변).

- [ ] **Step 6: 커밋**

```bash
git add data/doc_fields.py backend/services/po_documents.py spikes/docx_contract.py
git commit -m "[M4] feat(docx): doc_fields 공유 계층 + fields_02 (D124)

data/po_draft.py 규약대로 mcp_server·backend 어느 쪽도 import 하지 않는다(D15).
WITHHELD_KEYS 는 '빼는 목록'이 아니라 '만들지 않는 목록'이다 — 만든 뒤 빼면 규율이지만
애초에 만들지 않으면 구조다(D23·D37·D81).

render_po_request_document() 출력은 바이트 동일 — 골든 A② 가 지킨다."
```

---

## Task 4: `fields_01` (진단보고서)

**Files:**
- Modify: `data/doc_fields.py`
- Modify: `backend/services/po_documents.py`
- Modify: `spikes/docx_contract.py`

**Interfaces:**
- Consumes: Task 3 의 `val`·`won`·`yn`·`UNKNOWN`·`WITHHELD_KEYS`
- Produces: `fields_01(ctx) -> dict[str,str]` · `drop_rows_01(ctx) -> set[str]`

### 값 원천 매핑 (지어내지 않는다 — D62)

| 자리 | 원천 |
|---|---|
| `DOC_NO` | `f"DIAG-{po_id}"` |
| `DOC_STATUS` | `doc_status(ctx)` |
| `ISSUED_AT` | `created_at` |
| `TRACE_ID` | `session_id` |
| `ERROR_CODE` `SEVERITY` `SYMPTOM_SUMMARY` | `error_code`, `_SEVERITY_LABEL[severity]`, `evidence.symptoms` |
| `DIAGNOSIS_CONCLUSION` `VERDICT_RATIONALE` | `reason` (사람이 쓴 한 줄 요약, D80) |
| `SAFETY_FLAG` | `severity ∈ (fault, critical)` → `"예"` / 아니면 `UNKNOWN` |
| `ACTION_TYPE_1/2` `ACTION_DESC_1/2` | `error_code_def.actions[:2]` |
| `EVIDENCE_*_1/2` | `evidence.basis` 중 `lookup_error_code` 제외 앞 2건 |
| `ROOT_CAUSE_MODE` | `error_code_def.causes` 를 `", "` 로 |
| `EQUIPMENT_ID` `EQUIPMENT_NAME` `LOCATION` `DETECTED_AT` `REPEAT_FAULT_FLAG` `REPEAT_COUNT` `SAFETY_WARNING` `SAFETY_PRECONDITION` `ACTION_DURATION_*` `ACTION_COST_*` `REPAIR_REPLACE_VERDICT` `REQUEST_CHAIN_ID` | **전부 `UNKNOWN`** — `po_drafts` 에 원천이 없다. 기존 미리보기가 이미 같은 판단을 하고 그 이유를 괄호로 적어 두었다 |

`drop_rows_01(ctx)`: 표 2행째(`ERROR_CODE_2` `SEVERITY_2` `SYMPTOM_SUMMARY_2` `DETECTED_AT_2`)는 **항상** 삭제(발주 1건 = 에러코드 1건). `ACTION_*_2`·`EVIDENCE_*_2` 는 항목이 2건 미만일 때만 삭제.

- [ ] **Step 1: 검사에 01 케이스를 더한다**

`run_fields()` 의 `cases` 리스트에 한 줄:

```python
        ("01", "01_설비이상진단보고서.docx", df.fields_01(FIXTURE_PO), df.drop_rows_01(FIXTURE_PO)),
```

- [ ] **Step 2: 실패 확인**

```bash
uv run python spikes/docx_contract.py
```

Expected: `AttributeError: module 'data.doc_fields' has no attribute 'fields_01'`

- [ ] **Step 3: 구현**

`data/doc_fields.py` 에 위 매핑표대로 `_SEVERITY_LABEL`·`drop_rows_01`·`fields_01` 을 더한다. `_SEVERITY_LABEL` 은 `po_documents.py` 에서 **그대로 옮긴다**:

```python
_SEVERITY_LABEL = {"warning": "경고", "fault": "고장", "critical": "위험"}
```

- [ ] **Step 4: `render_diagnosis_document()` 재작성**

Task 3 과 같은 방식 — 스칼라를 `f = _df.fields_01(po)` 에서 가져오고 f-string 리터럴은 손대지 않는다. `_evidence_lines()`·`_actions_lines()`·`_causes_lines()` 는 **그대로 둔다**.

- [ ] **Step 5: 통과 확인**

```bash
uv run python spikes/docx_contract.py
```

Expected: `통과 (13건)` — A 7 + B 6. **A② PASS 유지.**

- [ ] **Step 6: 커밋**

```bash
git add data/doc_fields.py backend/services/po_documents.py spikes/docx_contract.py
git commit -m "[M4] feat(docx): fields_01 진단보고서 (D124)"
```

---

## Task 5: `fields_03` (자금집행요청서)

**Files:**
- Modify: `data/doc_fields.py`
- Modify: `backend/services/po_documents.py`
- Modify: `spikes/docx_contract.py`

**Interfaces:**
- Consumes: Task 3 의 `amounts()`·`doc_status()`·`approval_result()`
- Produces: `fields_03(ctx, controls, a2a_info, payee) -> dict[str,str]` · `drop_rows_03(ctx) -> set[str]`

### 값 원천

`render_fund_execution_document()` 가 이미 하는 계산을 그대로 옮긴다 — 고정 상수 `_FUND_TYPE`·`_FUNDING_METHOD`·`_MFA_STATUS_TEXT`·`_mask_account()`·`_fund_a2a_lines()` 를 `data/doc_fields.py` 로 이관한다.

담보·대출 4자리(`COLLATERAL_ID` `COLLATERAL_TYPE` `COLLATERAL_VALUE` `LOAN_AMOUNT` `LTV` `REPAYMENT_PLAN`)는 **`drop_rows_03` 대상이 아니라 고정 문구**다 — 미리보기가 이미 §3 을 *"해당 없음 — 본 문서는 일반 부품 발주(S1/S2) 전용이며 담보·대출 취급 대상이 아니다"* 로 적었다. 각 자리에 `"해당 없음"` 을 넣는다.

**이건 `UNKNOWN` 이 아니다.** D62 는 *모르는 것*을 통과로 반올림하지 말라는 규칙이고, 여기는 **알고 있다** — 이 문서 종류가 담보 거래가 아니라는 것이 확정 사실이다(D77 의 `vat_invoice_issued=False` 와 같은 성질).

`PAYEE_BIZ_NO` 는 `UNKNOWN` (suppliers 테이블에 없음). `EXECUTION_DATE` 도 `UNKNOWN`.

- [ ] **Step 1: 검사에 03 케이스를 더한다**

```python
        (
            "03",
            "03_자금집행요청서.docx",
            df.fields_03(FIXTURE_PO, FIXTURE_CONTROLS, FIXTURE_A2A, FIXTURE_PAYEE),
            df.drop_rows_03(FIXTURE_PO),
        ),
```

- [ ] **Step 2: 실패 확인**

```bash
uv run python spikes/docx_contract.py
```

Expected: `AttributeError: ... 'fields_03'`

- [ ] **Step 3: 구현 + `render_fund_execution_document()` 재작성**

- [ ] **Step 4: 통과 확인**

```bash
uv run python spikes/docx_contract.py
```

Expected: `통과 (16건)`. **A② PASS 유지.**

- [ ] **Step 5: 커밋**

```bash
git add data/doc_fields.py backend/services/po_documents.py spikes/docx_contract.py
git commit -m "[M4] feat(docx): fields_03 자금집행요청서 (D124·D119)

담보·대출 6자리는 UNKNOWN 이 아니라 '해당 없음' 이다 — 이 문서 종류가 담보 거래가
아니라는 것은 모르는 게 아니라 확정 사실이다(D77 의 vat_invoice_issued=False 와 같은 성질)."
```

---

## Task 6: `fields_05` · `fields_06` (처분 문서 2종)

**Files:**
- Modify: `data/doc_fields.py`
- Modify: `mcp_server/tools/generate_disposal_document.py`
- Modify: `spikes/docx_contract.py`

**Interfaces:**
- Consumes: Task 3 의 `val`·`yn`·`UNKNOWN`
- Produces:
  - `fields_05(bundle, *, verdict, bundle_hash, reason, decision_id, doc_state=UNKNOWN, created_at=UNKNOWN, request_chain_id=UNKNOWN) -> dict[str,str]`
  - `fields_06(bundle, *, verdict, bundle_hash, decision_id, doc_state=UNKNOWN, created_at=UNKNOWN, request_chain_id=UNKNOWN) -> dict[str,str]`

### 왜 `doc_state`·`created_at` 이 키워드 인자인가

이 셋은 `decisions` **행**에서 오는데 `render_documents()` 는 번들과 판정값만 받는다(그 함수의 docstring: *"여기서 DB 를 다시 읽지 않는다"*). 도구 경로(초안 생성 직후)에서는 아직 알 수 없으므로 기본값 `UNKNOWN`, 다운로드 엔드포인트(Task 9)가 실제 값을 넘긴다.

**`SIGNED_BY`·`SIGNED_AT`·`OVERRIDE`·`OVERRIDE_REASON` 은 인자로도 받지 않는다** — `WITHHELD_KEYS` 다. Task 9 가 얹는다.

### 이관할 헬퍼

`_law_lines`·`_rule_lines`·`_contract_lines`·`_open_condition_lines`·`_VERDICT_LINES`·`_VERDICT_UNKNOWN`·`_NO_AUTO_BLOCK_LINE`·`_UNKNOWN_LINE` 을 `data/doc_fields.py` 로 옮기고, `generate_disposal_document.py` 는 재수출한다. **문안 문자열은 한 글자도 바꾸지 않는다.**

`LAW_COUNT`·`RULE_COUNT`·`CONTRACT_COUNT` 는 `len(bundle["laws"])` 등, `RULES_EVALUATED`·`RULES_OPEN` 은 `len(evaluated)` 와 `len([e for e in evaluated if e["verdict"] != "CLEAR"])`.

`TEMPLATE_REVIEW_NOTICE` 는 `data.doc_review.template_review_notice()`.

`drop_rows_05`·`drop_rows_06` 은 **필요 없다** — 05·06 템플릿에 `_1`/`_2` 반복 행이 없다(실측: 자리 목록에 접미 숫자 없음). 빈 `set()` 을 돌려주는 함수를 만들지 말고, 검사에서 `set()` 리터럴을 넘긴다.

- [ ] **Step 1: 검사에 05·06 케이스를 더한다**

```python
        ("05", "05_설비처분승인서.docx", df.fields_05(FIXTURE_BUNDLE, **FIXTURE_DISPOSAL_KW), set()),
        (
            "06",
            "06_진술및보장서.docx",
            df.fields_06(
                FIXTURE_BUNDLE,
                verdict=FIXTURE_DISPOSAL_KW["verdict"],
                bundle_hash=FIXTURE_DISPOSAL_KW["bundle_hash"],
                decision_id=FIXTURE_DISPOSAL_KW["decision_id"],
            ),
            set(),
        ),
```

- [ ] **Step 2: 실패 확인**

```bash
uv run python spikes/docx_contract.py
```

Expected: `AttributeError: ... 'fields_05'`

- [ ] **Step 3: 구현 + `render_documents()` 재작성**

- [ ] **Step 4: 통과 확인**

```bash
uv run python spikes/docx_contract.py
```

Expected: `통과 (22건)`. **A② PASS 유지 — 05·06 미리보기도 바이트 동일.**

- [ ] **Step 5: 실제 채우기가 되는지 확인 (C 축 신설)**

`spikes/docx_contract.py` 에 C 축을 더한다:

```python
# ── C. 채우기 ──────────────────────────────────────────────────────────────────
def run_fill() -> None:
    from backend.services.docx_render import fill_template, template_placeholders
    from data import doc_fields as df

    import io
    import zipfile

    cases = [
        ("01", "01_설비이상진단보고서.docx", df.fields_01(FIXTURE_PO), df.drop_rows_01(FIXTURE_PO)),
        ("02", "02_정비부품발주요청서.docx", df.fields_02(FIXTURE_PO), df.drop_rows_02(FIXTURE_PO)),
        (
            "03",
            "03_자금집행요청서.docx",
            df.fields_03(FIXTURE_PO, FIXTURE_CONTROLS, FIXTURE_A2A, FIXTURE_PAYEE),
            df.drop_rows_03(FIXTURE_PO),
        ),
        ("05", "05_설비처분승인서.docx", df.fields_05(FIXTURE_BUNDLE, **FIXTURE_DISPOSAL_KW), set()),
        (
            "06",
            "06_진술및보장서.docx",
            df.fields_06(
                FIXTURE_BUNDLE,
                verdict=FIXTURE_DISPOSAL_KW["verdict"],
                bundle_hash=FIXTURE_DISPOSAL_KW["bundle_hash"],
                decision_id=FIXTURE_DISPOSAL_KW["decision_id"],
            ),
            set(),
        ),
    ]
    for tag, template, fields, dropped in cases:
        # 신원 자리는 이 계층이 만들지 않으므로 다운로드 엔드포인트를 흉내 내 채운다.
        withheld_here = template_placeholders(template) & df.WITHHELD_KEYS
        data = fill_template(
            template, dict(fields) | {k: "(미기재)" for k in withheld_here}, drop_rows=dropped
        )
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        check(
            f"C① {tag} 채운 docx 에 미치환 자리가 없다",
            data[:2] == b"PK" and "{{" not in xml,
            f"{len(data):,}바이트 · 자리 {len(fields) + len(withheld_here)}개 치환"
            f" · 삭제행 {len(dropped)}개",
        )
```

`main()` 에 `run_fill()` 을 넣고 실행.

Expected: `통과 (27건)`

- [ ] **Step 6: 무저장을 실증한다**

```bash
git status --porcelain data/templates/
```

Expected: 출력 없음 (템플릿 무변경)

- [ ] **Step 7: 커밋**

```bash
git add data/doc_fields.py mcp_server/tools/generate_disposal_document.py spikes/docx_contract.py
git commit -m "[M4] feat(docx): fields_05·06 처분 문서 + 5종 실제 채우기 검증 (D124)

SIGNED_BY·SIGNED_AT·OVERRIDE·OVERRIDE_REASON 은 인자로도 받지 않는다 —
WITHHELD_KEYS 이고 다운로드 엔드포인트가 얹는다(D23·D81)."
```

---

## Task 7: `po_context()` · `disposal_context()` — DB 조립 이관

**Files:**
- Modify: `data/doc_fields.py`
- Modify: `backend/services/po.py:321-374`
- Modify: `spikes/docx_contract.py`

**Interfaces:**
- Consumes: 없음 (DB 커넥션은 호출자가 넘긴다)
- Produces:
  - `po_context(con, po_id: str) -> dict | None`
  - `disposal_context(con, decision_id: str) -> dict | None`

**여기부터 Postgres 가 필요하다.**

### `po_context()` 가 하는 일

`get_po()` 의 `:324~373` — `_PO_SELECT` 조회 + `quotes`·`inventory`·`alternatives`·`error_code_def` 부착 — 을 그대로 옮긴다. **`controls`·`a2a_info`·`payee`·`documents_preview`·`trace_url`·`print_pages` 는 옮기지 않는다** (backend 전용).

`get_po()` 는 `po_context()` 를 호출한 뒤 나머지를 얹는다. 신원 컬럼(`requested_by_name` 등)은 `_PO_SELECT` 가 이미 JOIN 하므로 ctx 에 그대로 들어온다 — **`fields_*()` 가 그것을 안 쓸 뿐이다.**

### `disposal_context()` 가 하는 일

```sql
SELECT decision_id, asset_id, state, verdict, bundle_hash, evidence_bundle, reason, created_at
  FROM decisions WHERE decision_id = ?
```
`evidence_bundle` 은 JSON 이므로 `json.loads`. 반환 dict 는 `{"decision_id", "state", "verdict", "bundle_hash", "bundle", "reason", "created_at"}`.

- [ ] **Step 1: Postgres 기동 확인**

```bash
docker start maintq_postgres && docker exec maintq_postgres pg_isready -U postgres
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run python -c "
from backend.db import connect
with connect() as c: print('error_codes:', c.execute('SELECT count(*) FROM error_codes').fetchone()[0])"
```

Expected: `error_codes: 70` — **65 가 나오면 IE5 5건(D109) 병합이 안 된 상태다.** 0 이면 `uv run python data/seed.py --with-error-codes` 로 재시드(`--today` 금지).

- [ ] **Step 2: 실패하는 검사를 쓴다**

`spikes/docx_contract.py` 에 D 축 앞부분:

```python
# ── D. DB 컨텍스트 ─────────────────────────────────────────────────────────────
def run_context(con) -> None:
    from data import doc_fields as df

    ctx = df.po_context(con, "PO-0117")
    check(
        "D① po_context 가 발주 컨텍스트를 조립한다",
        ctx is not None and ctx["po_id"] == "PO-0117" and "quotes" in ctx and "inventory" in ctx,
        f"po_id={ctx and ctx.get('po_id')} · quotes={len(ctx.get('quotes') or []) if ctx else 0}건"
        f" · error_code_def={'있음' if ctx and ctx.get('error_code_def') else '없음'}",
    )
    check(
        "D② 없는 발주는 None (예외 아님)",
        df.po_context(con, "PO-9999") is None,
        "PO-9999 → None",
    )
    fields = df.fields_02(ctx)
    check(
        "D③ 실 DB 컨텍스트로도 필드맵이 완결된다",
        bool(fields) and not (set(fields) & df.WITHHELD_KEYS),
        f"필드 {len(fields)}개 · withheld 유출 0개",
    )
```

`main()` 에 격리 스키마 커넥션을 열어 `run_context(con)` 을 호출하는 블록을 더한다 (`data/pg_isolation.py` 사용 — 다른 스파이크와 같은 패턴).

- [ ] **Step 3: 실패 확인**

```bash
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run python spikes/docx_contract.py
```

Expected: `AttributeError: ... 'po_context'`

- [ ] **Step 4: 구현**

`data/doc_fields.py` 에 `po_context()`·`disposal_context()` 를 더하고, `backend/services/po.py::get_po()` 가 그것을 호출하도록 바꾼다.

- [ ] **Step 5: 통과 + 기존 회귀 확인**

```bash
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run python spikes/docx_contract.py
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run python spikes/api_contract.py
```

Expected: `docx_contract` 30건 통과 · **`api_contract` 52건 그대로 통과** (`get_po()` 리팩터가 응답을 안 바꿨다는 증거)

- [ ] **Step 6: 커밋**

```bash
git add data/doc_fields.py backend/services/po.py spikes/docx_contract.py
git commit -m "[M4] refactor: po_context·disposal_context 를 data/doc_fields 로 이관 (D124)

get_po() 의 SELECT+조인만 옮긴다 — controls·a2a_info·payee 는 backend 전용이라
남긴다(D15). api_contract 52건 무변경으로 응답 불변을 확인했다."
```

---

## Task 8: `get_document_facts` MCP 읽기 도구

**Files:**
- Create: `mcp_server/tools/get_document_facts.py`
- Modify: `mcp_server/server.py`
- Modify: `spikes/tools_profile_contract.py`
- Modify: `spikes/docx_contract.py`

**Interfaces:**
- Consumes: `data.doc_fields.po_context`·`disposal_context`·`fields_01`·`fields_02`·`fields_05`·`fields_06`·`WITHHELD_KEYS`
- Produces: `DESCRIPTION: str` · `get_document_facts(doc_type: str, ref_id: str) -> dict`

### 계약

```python
get_document_facts(doc_type: "po" | "disposal", ref_id: str) -> dict
```

성공:
```json
{"status": "ok", "doc_type": "po", "ref_id": "PO-0117",
 "fields": {"01": {...}, "02": {...}},
 "withheld": ["APPROVER_NAME", "..."],
 "unavailable": {"03": "내부통제 판정(D119)은 재무 승인 경로에서만 산출됩니다"},
 "correction_hint": "..."}
```
실패: `{"status": "error", "reason": "invalid_input"|"not_found"|"db_error", "message": "..."}`

- [ ] **Step 1: 실패하는 검사를 쓴다**

`spikes/docx_contract.py` 에 E 축:

```python
# ── E. 읽기 도구 ───────────────────────────────────────────────────────────────
def run_read_tool() -> None:
    from data import doc_fields as df
    from mcp_server.tools.get_document_facts import get_document_facts

    r = get_document_facts(doc_type="po", ref_id="PO-0117")
    check(
        "E① po 조회 — 01·02 필드맵",
        r.get("status") == "ok" and set(r.get("fields", {})) == {"01", "02"},
        f"status={r.get('status')} · 문서 {sorted(r.get('fields', {}))}"
        f" · 01 {len(r.get('fields', {}).get('01', {}))}자리"
        f" · 02 {len(r.get('fields', {}).get('02', {}))}자리",
    )
    leaked = sorted(
        k for doc in r.get("fields", {}).values() for k in doc if k in df.WITHHELD_KEYS
    )
    check(
        "E② 신원·서명 필드를 노출하지 않는다 (D23)",
        not leaked and bool(r.get("fields")),
        f"문서 {len(r.get('fields', {}))}종 · 유출 {len(leaked)}개"
        + (f" {leaked}" if leaked else "")
        + f" · withheld 목록 {len(r.get('withheld') or [])}개",
    )
    check(
        "E③ withheld 와 unavailable 이 분리돼 있다 (D62)",
        bool(r.get("withheld")) and "03" in (r.get("unavailable") or {}),
        f"withheld {len(r.get('withheld') or [])}개 · unavailable {sorted(r.get('unavailable') or {})}",
    )
    check(
        "E④ 교정 경로를 안내한다 (D10 — UPDATE 아님)",
        "create_po_draft" in (r.get("correction_hint") or ""),
        repr((r.get("correction_hint") or "")[:60]),
    )
    bad = get_document_facts(doc_type="asset", ref_id="X")
    check(
        "E⑤ enum 밖 doc_type → status=error (예외 아님, D9)",
        bad.get("status") == "error" and bad.get("reason") == "invalid_input",
        f"{bad.get('status')}/{bad.get('reason')}",
    )
    nf = get_document_facts(doc_type="po", ref_id="PO-9999")
    check(
        "E⑥ 없는 ref_id → not_found",
        nf.get("status") == "error" and nf.get("reason") == "not_found",
        f"{nf.get('status')}/{nf.get('reason')}",
    )
    src = (ROOT / "mcp_server" / "tools" / "get_document_facts.py").read_text(encoding="utf-8")
    has_readonly = "read_only" in src
    writes = [w for w in ("draft_writer", "decision_writer", "repair_writer", "INSERT", "UPDATE", "DELETE") if w in src]
    check(
        "E⑦ 읽기 전용 — 쓰기 커넥션·DML 이 없다 (D10)",
        has_readonly and not writes,
        f"read_only 사용={has_readonly} · 쓰기 토큰 {writes or '없음'} · 소스 {len(src):,}바이트",
    )
```

E⑦ 은 부재검사다 — `has_readonly`(양성 축)와 소스 바이트 수를 판정·detail 에 함께 넣었다.

- [ ] **Step 2: 실패 확인**

```bash
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run python spikes/docx_contract.py
```

Expected: `ModuleNotFoundError: ... get_document_facts`

- [ ] **Step 3: 도구 구현**

Create `mcp_server/tools/get_document_facts.py`:

```python
# -*- coding: utf-8 -*-
"""get_document_facts — 결재 문서에 실제로 찍힐 값을 **조회만** 한다 (D125).

**이 파일은 얇은 래퍼다** (`track_deadlines.py` 와 같은 구조). 필드맵 산출은
`data/doc_fields.py` 에 있다. 여기 남는 것은 둘뿐이다:
  1. `DESCRIPTION` — `04 §21` 이 정본으로 인용한다
  2. 커넥션 수명 (`read_only()`)

★ 이 도구는 아무것도 쓰지 않는다 (D10)
────────────────────────────────────────────────────────────────────────────────
`read_only()` 만 쓴다 — `draft_writer()`·`decision_writer()`·`repair_writer()` 를
부르지 않는다. 값을 고치려면 `create_po_draft` 로 **새 draft 를 INSERT** 하거나
사람이 화면에서 수정한다(`PATCH /api/po`·`/api/repairs`·`/api/decisions`).

  MCP UPDATE 로 얻는 건 "이미 만든 걸 대화로 고치기" 하나인데, 잃는 건 이 프로젝트가
  내세우는 문장 자체다 — *"AI 가 제안하고 사람이 결정한다"*.

★ 신원·서명 필드는 애초에 만들어지지 않는다 (D23)
────────────────────────────────────────────────────────────────────────────────
`data/doc_fields.WITHHELD_KEYS` 를 `withheld` 로 함께 실어 **"안 준다"**를 밝힌다.
원천이 없어 못 주는 것(`unavailable`)과 구분한다 — 합치면 에이전트가 "요청자 이름이
시스템에 없다"고 말하게 되는데 그건 거짓이다(있고, 주지 않을 뿐이다).
"""

from __future__ import annotations

from data import doc_fields as df

from ..db import read_only

DOC_TYPES = ("po", "disposal")

_UNAVAILABLE_PO = {
    "03": (
        "자금집행요청서(03)의 내부통제 판정(예산 한도·1일 누적 한도·FDS·직무분리)은 "
        "재무 승인 경로에서만 산출되며 이 도구가 조회할 수 없습니다."
    )
}

CORRECTION_HINT = (
    "이 도구는 조회만 합니다. 값이 틀렸다면 create_po_draft 로 새 초안을 만들어 다시 "
    "제안하거나, 사람이 화면에서 직접 수정하도록 안내하세요 "
    "(PATCH /api/po · /api/repairs · /api/decisions). 기존 초안을 이 도구로 고칠 수는 없습니다."
)

DESCRIPTION = (
    "결재 문서에 실제로 찍힐 값을 문서 양식의 자리 이름 그대로 조회한다. "
    "doc_type='po' 면 설비이상진단보고서(01)·정비부품발주요청서(02), "
    "doc_type='disposal' 이면 설비처분승인서(05)·진술및보장서(06) 의 필드맵을 돌려준다. "
    "발주·처분 초안의 내용을 확인하거나 어느 항목이 비었는지 짚어 말할 때 쓸 것. "
    "'확인되지 않음' 은 '해당 없음' 이 아니라 시스템에 원천이 없다는 뜻이므로 추측으로 "
    "채워 말하지 말 것. 요청자·승인자 이름과 서명 정보는 이 도구가 돌려주지 않는다"
    "(withheld 목록 참조) — 없는 것이 아니라 도구에 노출하지 않는 값이다. "
    "이 도구는 조회만 하며 아무것도 수정하지 않는다. 값을 고치려면 create_po_draft 로 "
    "새 초안을 만들거나 사람이 화면에서 수정해야 한다."
)


def _po_payload(con, ref_id: str) -> dict | None:
    ctx = df.po_context(con, ref_id)
    if ctx is None:
        return None
    return {
        "fields": {"01": df.fields_01(ctx), "02": df.fields_02(ctx)},
        "unavailable": dict(_UNAVAILABLE_PO),
    }


def _disposal_payload(con, ref_id: str) -> dict | None:
    ctx = df.disposal_context(con, ref_id)
    if ctx is None:
        return None
    common = {
        "verdict": ctx["verdict"],
        "bundle_hash": ctx["bundle_hash"],
        "decision_id": ctx["decision_id"],
        "doc_state": ctx["state"],
        "created_at": ctx["created_at"],
    }
    return {
        "fields": {
            "05": df.fields_05(ctx["bundle"], reason=ctx["reason"], **common),
            "06": df.fields_06(ctx["bundle"], **common),
        },
        "unavailable": {},
    }


def get_document_facts(doc_type: str, ref_id: str) -> dict:
    if doc_type not in DOC_TYPES:
        return {
            "status": "error",
            "reason": "invalid_input",
            "message": f"doc_type 은 {' | '.join(DOC_TYPES)} 중 하나여야 합니다: {doc_type!r}",
        }
    if not (ref_id or "").strip():
        return {"status": "error", "reason": "invalid_input", "message": "ref_id 가 비었습니다"}

    try:
        with read_only() as con:
            payload = _po_payload(con, ref_id) if doc_type == "po" else _disposal_payload(con, ref_id)
    except Exception as e:  # noqa: BLE001 — 도구는 예외를 던지지 않는다 (D9)
        return {"status": "error", "reason": "db_error", "message": str(e)}

    if payload is None:
        return {
            "status": "error",
            "reason": "not_found",
            "message": f"{doc_type} 초안을 찾을 수 없습니다: {ref_id}",
        }

    return {
        "status": "ok",
        "doc_type": doc_type,
        "ref_id": ref_id,
        "fields": payload["fields"],
        "withheld": sorted(df.WITHHELD_KEYS),
        "unavailable": payload["unavailable"],
        "correction_hint": CORRECTION_HINT,
    }
```

- [ ] **Step 4: `server.py` 확장 블록에 등록**

import 블록 끝(`assess_equipment_loan` 다음)에:

```python
    from mcp_server.tools.get_document_facts import (  # noqa: E402
        DESCRIPTION as DOC_FACTS_DESC,
        get_document_facts as _get_document_facts,
    )
```

데코레이터 블록 끝에:

```python
    @mcp.tool(description=DOC_FACTS_DESC)
    def get_document_facts(
        doc_type: Annotated[
            str,
            Field(description="문서 종류 — po(발주: 01·02) | disposal(처분: 05·06)."),
        ],
        ref_id: Annotated[str, Field(description="발주 ID(PO-0117) 또는 결정 ID(DEC-0007).")],
    ) -> dict:
        """둘 다 필수 — 기본값을 두지 않는다 (D80)."""
        return _get_document_facts(doc_type=doc_type, ref_id=ref_id)
```

또 파일 상단 docstring 의 `확장 13종` → `확장 14종` 으로 고친다.

- [ ] **Step 5: `tools_profile_contract` 를 21종으로**

`spikes/tools_profile_contract.py` 의 확장 도구 집합에 `"get_document_facts"` 를 더하고, 기대 총계 주석 `도구 **20종**(코어 7 + 확장 13)` → `**21종**(코어 7 + 확장 14)` 로 고친다. 또 D80 검사(②)에 `get_document_facts` 의 `required == {"doc_type", "ref_id"}` 를 더한다.

- [ ] **Step 6: 통과 확인**

```bash
DL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)"
DATABASE_URL="$DL" uv run python spikes/docx_contract.py
DATABASE_URL="$DL" uv run python spikes/tools_profile_contract.py
DATABASE_URL="$DL" uv run python spikes/write_tool_contract.py
```

Expected:
- `docx_contract` 37건 통과
- `tools_profile_contract` **8건**(기존 7 + D80 항목 1) 통과, `full` 에서 21종 · `core` 에서 7종
- `write_tool_contract` **30건 그대로** — 쓰기 경로가 안 늘었다는 증거

- [ ] **Step 7: 커밋**

```bash
git add mcp_server/tools/get_document_facts.py mcp_server/server.py spikes/tools_profile_contract.py spikes/docx_contract.py
git commit -m "[M4] feat(mcp): get_document_facts 읽기 전용 도구 (D125)

read_only() 만 쓴다 — writer 3종을 부르지 않는다. write_tool_contract 30건이
그대로인 것이 '쓰기 경로가 안 늘었다'의 증거다(D10).

withheld(안 준다)와 unavailable(원천이 없다)을 분리해 싣는다(D62) — 합치면
에이전트가 '요청자 이름이 시스템에 없다'고 말하게 되는데 그건 거짓이다.

full 전용(D69) — 확장 13→14, 총 20→21. 코어 7 불변이라 D88 게이트 무영향."
```

---

## Task 9: 다운로드 엔드포인트

**Files:**
- Modify: `backend/routers/po.py`
- Modify: `backend/routers/decisions.py`
- Create: `backend/services/document_download.py`
- Modify: `spikes/docx_contract.py`

**Interfaces:**
- Consumes: `docx_render.fill_template`·`DOCX_MIME`, `data.doc_fields.fields_01/02/03/05/06`
- Produces:
  - `document_download.PO_DOCS: dict[str, tuple[str, str]]` (doc key → (템플릿 파일명, 사람이 읽을 문서명))
  - `document_download.build_po_docx(po: dict, doc: str, controls, a2a_info, payee) -> bytes`
  - `document_download.build_decision_docx(ctx: dict, doc: str, row) -> bytes`
  - `document_download.content_disposition(filename: str) -> str`

### 신원 주입 — 이 태스크의 핵심

`data/doc_fields.py` 가 `WITHHELD_KEYS` 를 만들지 않으므로 여기서 DB 값으로 채운다:

| 자리 | 원천 |
|---|---|
| `TECHNICIAN_NAME` `REQUESTER_NAME` | `po["requested_by_name"]` |
| `REQUESTER_DEPT` | `po["requested_by_department"]` |
| `TECHNICIAN_SIGNED_AT` `REQUESTER_SIGNED_AT` | `po["created_at"]` |
| `MANAGER_NAME` `APPROVER_NAME` | `po["decided_by_name"]` |
| `MANAGER_SIGNED_AT` `APPROVER_SIGNED_AT` | 결재 전이면 `"(미기재 — 결재 전)"`, 아니면 `po["decided_at"]` |
| `FINANCE_APPROVER` `FINANCE_SIGNED_AT` | `finance_decided_by_name` · `finance_decided_at` |
| `SIGNATURE_HASH` | `UNKNOWN` (po_drafts 에 없음) |
| `SIGNED_BY` `SIGNED_AT` | `decisions.signed_by` · `signed_at`, draft 면 `"(미기재 — 서명 시 기록된다)"` |
| `OVERRIDE` `OVERRIDE_REASON` | `decisions.override` · `override_reason`, draft 면 `"미적용"` · `UNKNOWN` |

값이 비면 `UNKNOWN` 이 아니라 **`"(미기재 — 결재 전)"`** 계열 문구를 쓴다 — 미리보기가 이미 그렇게 한다(`approver_signed_at` 로직).

- [ ] **Step 1: 실패하는 검사를 쓴다**

`spikes/docx_contract.py` 에 F 축 (TestClient 사용, `ownership_api_contract.py` 패턴):

```python
# ── F. 다운로드 엔드포인트 ─────────────────────────────────────────────────────
def run_download(client) -> None:
    import io
    import zipfile

    from backend.services.docx_render import DOCX_MIME

    r = client.get("/api/po/PO-0117/documents/po_request.docx", headers={"X-User": "tech-01"})
    body = r.content
    check(
        "F① 02 발주요청서 다운로드 — 200 · docx MIME",
        r.status_code == 200 and r.headers.get("content-type", "").startswith(DOCX_MIME),
        f"{r.status_code} · {r.headers.get('content-type', '')[:60]} · {len(body):,}바이트",
    )
    cd = r.headers.get("content-disposition", "")
    check(
        "F② Content-Disposition — attachment + RFC 5987 한글 파일명",
        "attachment" in cd and "filename*=UTF-8''" in cd and "filename=" in cd,
        cd[:110],
    )
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    check(
        "F③ 미치환 자리가 없다",
        body[:2] == b"PK" and "{{" not in xml,
        f"docx {len(body):,}바이트 · xml {len(xml):,}자 · '{{{{' 잔존 {xml.count('{{')}개",
    )
    check(
        "F④ 신원이 실제로 채워진다 (엔드포인트가 얹는다)",
        "김정비" in xml or "tech-01" in xml,
        f"요청자 표기 발견={'예' if ('김정비' in xml or 'tech-01' in xml) else '아니오'}",
    )
    check(
        "F⑤ 진단서 — error_code_def 없으면 404 (미리보기와 같은 조건)",
        client.get("/api/po/PO-0120/documents/diagnosis.docx", headers={"X-User": "tech-01"}).status_code
        in (200, 404),
        "가용성 규칙이 미리보기와 같은 분기를 쓴다",
    )
    check(
        "F⑥ 재무 결정 전 fund_execution 은 404",
        client.get(
            "/api/po/PO-0117/documents/fund_execution.docx", headers={"X-User": "tech-01"}
        ).status_code == 404,
        "documents_preview.fund_execution 이 None 인 상태와 같다",
    )
    check(
        "F⑦ 없는 문서 키 → 404",
        client.get("/api/po/PO-0117/documents/xxx.docx", headers={"X-User": "tech-01"}).status_code == 404,
        "doc 화이트리스트 밖",
    )
    check(
        "F⑧ 없는 발주 → 404",
        client.get("/api/po/PO-9999/documents/po_request.docx", headers={"X-User": "tech-01"}).status_code == 404,
        "PO-9999",
    )
```

처분 쪽도 같은 형태로 `/api/decisions/{id}/documents/approval.docx` 4건(F⑨~F⑫)을 더한다.

- [ ] **Step 2: 실패 확인**

```bash
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run python spikes/docx_contract.py
```

Expected: F① 이 `404` 로 FAIL

- [ ] **Step 3: `backend/services/document_download.py` 구현**

```python
# -*- coding: utf-8 -*-
"""document_download — 결재 문서 docx 를 다운로드 시점에 조립한다 (D124).

★ 저장하지 않는다 (D86). ★ 신원은 여기서만 얹는다 (D23·D37).

`data/doc_fields.py` 는 `WITHHELD_KEYS` 를 만들지 않는다 — 그 자리를 이 모듈이 DB 값으로
채운다. "만든 뒤 빼기"가 아니라 "만들지 않고 나중에 얹기"라서, 도구 경로에는 신원이
흐를 수 있는 코드 경로 자체가 없다.
"""

from __future__ import annotations

from urllib.parse import quote

from backend.services.docx_render import fill_template
from data import doc_fields as df

PO_DOCS: dict[str, tuple[str, str]] = {
    "diagnosis": ("01_설비이상진단보고서.docx", "설비이상진단보고서"),
    "po_request": ("02_정비부품발주요청서.docx", "정비부품발주요청서"),
    "fund_execution": ("03_자금집행요청서.docx", "자금집행요청서"),
}

DECISION_DOCS: dict[str, tuple[str, str]] = {
    "approval": ("05_설비처분승인서.docx", "설비처분승인서"),
    "representation_warranty": ("06_진술및보장서.docx", "진술및보장서"),
}

_NOT_YET_APPROVED = "(미기재 — 결재 전)"
_NOT_YET_SIGNED = "(미기재 — 서명 시 기록된다)"


def content_disposition(filename: str) -> str:
    """한글 파일명은 RFC 5987 `filename*`, ASCII `filename` 은 구형 클라이언트 폴백."""
    ascii_name = filename.encode("ascii", "replace").decode("ascii").replace("?", "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
```

이어서 `build_po_docx()`·`build_decision_docx()` — 위 신원 매핑표대로 `identity` dict 를 만들어 `fill_template(template, fields | identity, drop_rows=...)` 를 호출한다.

- [ ] **Step 4: 라우터 2개 추가**

`backend/routers/po.py` 에:

```python
@router.get("/{po_id}/documents/{doc}.docx")
def download_po_document(po_id: str, doc: str, c: Caller = Depends(caller)) -> Response:
    """결재 문서 docx — 저장하지 않고 여기서 조립해 스트림한다 (D86·D124).

    가용성 규칙은 `documents_preview` 와 **같은 조건**을 쓴다 — 두 곳에 다른 조건을 두면
    화면엔 안 보이는데 URL 로는 받아지는 문서가 생긴다.
    """
    if doc not in document_download.PO_DOCS:
        raise HTTPException(404, f"알 수 없는 문서: {doc}")
    po = svc.get_po(po_id)
    if po is None:
        raise HTTPException(404, f"발주서를 찾을 수 없습니다: {po_id}")
    ...
```

`backend/routers/decisions.py` 에 같은 형태로.

`get_po()` 는 `documents_preview` 를 만들 때 `controls`·`a2a_info`·`payee` 를 지역 변수로 쓰고 버린다. 다운로드도 그 값이 필요하므로 `get_po()` 가 **`_fund_inputs` 키로 함께 돌려주도록** 한다 — 단, `spikes/api_contract.py` 의 `PO_DETAIL_KEYS` 가 응답 키를 고정하므로 **라우터가 응답 전에 `pop()` 한다.**

- [ ] **Step 5: 통과 확인**

```bash
DL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)"
DATABASE_URL="$DL" uv run python spikes/docx_contract.py
DATABASE_URL="$DL" uv run python spikes/api_contract.py
```

Expected: `docx_contract` 49건 · **`api_contract` 52건 그대로**

- [ ] **Step 6: 커밋**

```bash
git add backend/services/document_download.py backend/routers/po.py backend/routers/decisions.py backend/services/po.py spikes/docx_contract.py
git commit -m "[M4] feat(api): 결재 문서 docx 다운로드 5종 (D124·D86)

가용성 규칙은 documents_preview 와 같은 조건을 쓴다 — 두 곳에 다른 조건을 두면
화면엔 안 보이는데 URL 로는 받아지는 문서가 생긴다.

신원은 이 계층에서만 얹는다(D23·D37). api_contract 52건 무변경."
```

---

## Task 10: 뮤턴트 실증 + 스파이크 마무리

**Files:**
- Modify: `spikes/docx_contract.py`

- [ ] **Step 1: 최종 출력 문구를 실측값으로 바꾼다**

`main()` 의 마지막 `print` 를 축별 실측 건수로:

```python
    print(
        f"\n통과 ({len(results)}건) — 골든 {EXPECTED_GOLDEN_COUNT}종 · 필드맵 5문서 · "
        f"채우기 5종 · 다운로드 12건 · 읽기 도구 7건"
    )
```

- [ ] **Step 2: 뮤턴트 4종으로 검사가 살아 있음을 실증한다**

각각 임시 변경 → 실행 → **지정된 검사만 FAIL** 확인 → `git checkout --` 로 되돌린다.

| # | 뮤턴트 | FAIL 해야 하는 검사 |
|---|---|---|
| 1 | `data/doc_fields.py` 의 `WITHHELD_KEYS` 에서 `"SIGNED_BY"` 제거 | `B①`(05·06 초과), `E②` 는 PASS 유지 → **B 축이 잡는다** |
| 2 | `fields_02` 에서 `"VAT"` 키 삭제 | `B① 02`, `C① 02`, `F①`(500) |
| 3 | `get_document_facts` 가 `withheld` 를 `[]` 로 반환 | `E③` |
| 4 | `docx_render._drop_rows` 를 `return set()` 로 | `C① 01·02`(미치환 잔존) |

뮤턴트 1 은 특히 중요하다 — **`E②` 만으로는 부족하다**는 것을 보여준다(`fields_*` 가 안 만들면 유출도 없으므로 `E②` 는 통과한다). 두 축이 서로 다른 것을 본다는 증거다.

- [ ] **Step 3: 전체 재실행**

```bash
DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" uv run python spikes/docx_contract.py
```

Expected: `통과 (49건)` · 격리 스키마 잔존 0

- [ ] **Step 4: 커밋**

```bash
git add spikes/docx_contract.py
git commit -m "[M4] test(docx): 뮤턴트 4종으로 검사 생존 실증

뮤턴트 1(WITHHELD_KEYS 에서 SIGNED_BY 제거)이 B 축만 잡고 E② 는 통과하는 것을
확인했다 — fields_* 가 안 만들면 '유출'도 없어 E② 가 통과하기 때문이다.
두 축이 서로 다른 것을 본다는 증거이자, E② 하나만으로는 부족하다는 증거다."
```

---

## Task 11: 문서 갱신 + 전수 회귀

**Files:**
- Modify: `docs/10_DECISIONS.md` (D124 · D125)
- Modify: `docs/04_MCP_TOOLS.md` (§21)
- Modify: `data/templates/README.md`
- Modify: `docs/07_BACKLOG.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: D124 · D125 를 `docs/10_DECISIONS.md` 에 추가**

기존 표 형식(`| D124 | 결정 | 대안 | 근거 |`)을 따른다. 내용은 설계 문서 §10 그대로.

- [ ] **Step 2: `docs/04_MCP_TOOLS.md` §21 신설**

`## 21. get_document_facts — 결재 문서 필드 조회 (읽기 전용, D125)` 절을 `## 20` 다음에 추가. 입출력 계약·`withheld`/`unavailable` 구분·교정 경로를 적는다. 문서 상단의 도구 수 표기(`확장 13종`·`총 20종`)를 **14 · 21** 로 고친다.

- [ ] **Step 3: `data/templates/README.md` 의 거짓 문구를 정정**

「아직 하지 않은 것」 절이 아직 이렇게 적혀 있다:

> **이 템플릿을 실제로 채워 `.docx` 를 만드는 코드는 없다.** … **QMesh 프로젝트가 진행 중**이라 이 저장소에서 먼저 착수하지 않는다.

두 문장 다 지금은 거짓이다 — 앞 문장은 이 작업이 해소했고, 뒤 문장은 2026-09-03 에 이미 거짓으로 확정됐다(`docs/07_BACKLOG.md`). 절 제목을 「구현 상태」로 바꾸고 `backend/services/docx_render.py`·`data/doc_fields.py` 를 가리키게 한다.

- [ ] **Step 4: `docs/07_BACKLOG.md` 항목을 해소 표기**

「아이디어 주차장」의 ".docx/.pdf 파일 생성" 항목에 `✅ **2026-09-04 해소 — docx 5종**` 을 달고, **pdf 는 미착수로 남긴다**(시스템 바이너리가 필요해 별건). 「착수 시 판단할 것 2건」의 ㉮·㉯ 도 결론을 적어 닫는다.

- [ ] **Step 5: `CLAUDE.md` 기준선 갱신**

- 「반드시 먼저 읽을 문서」의 `04_MCP_TOOLS.md` 설명: `확장 13종` → `확장 14종`, `총 20종` → `총 21종`
- 「기술 스택·컨벤션」의 `확장 **13종**(코어 7 + 확장 13 = 20종)` → `확장 **14종**(코어 7 + 확장 14 = 21종)`
- 「회귀 스위트」 spikes 목록에 `docx_contract` 추가 → **34종**
- 스위트별 건수 표에 `docx_contract 49` 추가, `tools_profile_contract 7` → `8`
- 헤드라인 `33스위트 / 1,120건` → `34스위트 / 1,170건`(1,120 + 49 + tools_profile +1)

**건수는 러너 출력이 기준이다.** 위 산술이 실측과 어긋나면 **실측을 적고 산술을 정정**한다.

- [ ] **Step 6: 전수 회귀**

```bash
DL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)"

# ① spikes 34종
for f in spikes/*.py; do
  case "$f" in *test_elice_stream*|*demo_recommendation*) continue;; esac
  echo "── $f"; DATABASE_URL="$DL" uv run python "$f" 2>&1 | tail -3
done

# ② seed 자가검증
DATABASE_URL="$DL" uv run python data/seed.py --with-error-codes

# ③ pytest 4파일군 + A2A 8파일군
DATABASE_URL="$DL" uv run --with pytest python -m pytest \
  data/rules/test_rules.py backend/agent/test_llm_cache.py \
  data/external/test_elice_docvision.py data/test_expenditure_limits.py \
  backend/services/test_docx_render.py -q

DATABASE_URL="$DL" uv run --with pytest --with pytest-asyncio python -m pytest \
  backend/a2a/test_auth_header.py backend/a2a/test_client.py backend/a2a/test_credentials.py \
  backend/a2a/test_payloads.py backend/a2a/test_trace.py backend/routers/test_a2a.py \
  backend/routers/test_po_a2a_trigger.py backend/services/test_po_a2a_dispatch.py -q

# ④ 정적
uv run ruff check
```

Expected:
- spikes **34/34 FAIL 0** — `write_tool_contract` 는 **30건 그대로**여야 한다
- seed **41/41**, `error_codes` **70행**
- pytest 4파일군 **114 + 7 = 121건**, A2A 8파일군 **88건**
- ruff clean

**Windows 소켓 고갈**(`OSError: [WinError 10014]`)로 매번 다른 스위트가 1건 실패할 수 있다. **실패한 스위트는 반드시 단독 재실행해 확인**하고, 재시도로 통과하면 그 사실을 보고에 적는다. 재시도해도 실패하면 진짜 회귀다.

- [ ] **Step 7: 커밋**

```bash
git add docs CLAUDE.md data/templates/README.md
git commit -m "[M4] docs: D124·D125 + 04 §21 + 기준선 34스위트

data/templates/README.md 의 'QMesh 진행 중이라 착수하지 않는다' 문구를 지운다 —
2026-09-03 에 이미 거짓으로 확정된 차단 문구였고, 이 작업이 앞 문장('실제로 채워
docx 를 만드는 코드는 없다')도 해소했다.

백로그 pdf 는 미착수로 남긴다 — 시스템 바이너리가 필요해 python-docx 를 고른
이유(순수 pip, 배포 단순)가 사라진다."
```

---

## Self-Review 결과

**스펙 커버리지**

| 스펙 절 | 태스크 |
|---|---|
| §1① docx 전략 = 템플릿 채우기 | 1 · 3~6 |
| §1② 필드맵 노출 | 3~6 · 8 |
| §1③ 읽기 도구 01·02·05·06 | 8 |
| §2 아키텍처 · D15 · 신원 분리 | 3 · 7 · 9 |
| §3 골든 + liveness 앵커 | 2 · 10 |
| §4 양방향 strict · 무저장 · 런분할 | 1 |
| §5 다운로드 엔드포인트 | 9 |
| §6 읽기 도구 계약 | 8 |
| §7 교정 경로 (코드 0) | 8(`correction_hint`) · 11(문서) |
| §8 회귀 | 8 · 10 · 11 |
| §9 범위 밖 명시 | 11(백로그) |
| §10 D124·D125 | 11 |

**미해결로 남기는 것 (의도적)**

- **프론트엔드 다운로드 버튼** — 스펙 §9. 엔드포인트까지만.
- **PDF** — 스펙 §9.
- `spikes/golden/` 이 `ls spikes/*.py` 카운트에 영향을 주지 않는다(디렉터리이고 `.txt` 다). 스위트 수는 `docx_contract.py` 1개만 늘어 **33 → 34**.
