# -*- coding: utf-8 -*-
"""docx 생성 + facts 읽기 도구 계약 검증 (D124·D125).

## 무엇을 보는가

  A. **골든 대조** — `render_*_document()`·`render_documents()` 의 평문 출력이 필드맵
     리팩터 전후로 **바이트 동일**한가. 이 문자열은 `api_contract` 52건과 화면
     (`DocumentPreview.tsx`)이 함께 본다.
  B. 필드맵 — `data/doc_fields.py` 가 템플릿 자리를 **빠짐없이** 만드는가,
     `WITHHELD_KEYS` 를 **하나도** 만들지 않는가
  C. 채우기 — 5종이 실제로 미치환 자리 없이 채워지는가
  D. DB 컨텍스트 — `po_context`·`disposal_context`
  E. 읽기 도구 — 조회만 · withheld/unavailable 분리 · 실패는 status
  F. 다운로드 엔드포인트 — MIME · Content-Disposition · 가용성 규칙

## ⚠ A 는 부재검사다 — liveness 앵커를 함께 건다

"차이가 없다"는 주장은 원리적으로 *사실이 참* 과 *스캐너가 눈이 멀었다* 를 구분하지
못한다. 골든 파일이 비거나 경로가 바뀌면 `all([])` 이 True 라 **조용히 통과**한다.
CLAUDE.md 가 못박은 규칙을 따른다:

  · 판정식에 **양성 축**을 넣는다 — `골든 개수 == 기대치 and 전건 일치`
  · detail 에 **결론이 아니라 실측값**을 찍는다 (`"출력 불변 확인"` 같은 하드코딩 문구는
    FAIL 일 때도 그대로 인쇄돼 표를 읽는 사람이 정반대로 이해한다)
  · 뮤턴트로 실증한다 — 렌더 문구 한 글자를 바꾸면 A 만 FAIL 해야 한다

## DB 를 쓰지 않는 부분이 있다

A~C 는 픽스처 dict 만으로 돈다 — `render_*` 는 DB 를 읽지 않기 때문이다
(`po_documents.py` 상단 docstring: *"여기서 DB 를 다시 읽지 않는다"*). D~F 만
격리 스키마 Postgres 를 쓴다.

실행:
    DATABASE_URL=... uv run python spikes/docx_contract.py
    DOCX_CONTRACT_REGOLD=1 uv run python spikes/docx_contract.py   # 골든 재생성

⛔ `DOCX_CONTRACT_REGOLD` 는 **리팩터 전에만** 쓴다. 리팩터 후에 돌리면 바뀐 출력을
   정답으로 굳혀 이 스위트의 존재 이유가 사라진다.
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


def guard(label: str, fn, *args) -> None:
    """축 하나를 돌리되 예외를 **FAIL 행으로** 바꾼다.

    ⚠ 이게 없으면 뒤쪽 축의 예외가 앞쪽 축의 결과를 통째로 삼킨다. 실측으로 확인했다 —
    뮤턴트(WITHHELD_KEYS 에서 SIGNED_BY 제거)를 넣으니 B① 이 FAIL 을 이미 기록했는데도
    C 축의 TemplateFieldMismatch 가 먼저 프로세스를 죽여 **표가 한 줄도 안 나왔다.**
    표를 읽는 사람에게는 traceback 만 남고 어느 검사가 깨졌는지 알 수 없다.
    """
    try:
        fn(*args)
    except Exception as e:  # noqa: BLE001 — 축이 죽어도 나머지 표는 인쇄한다
        check(f"{label} 축이 예외로 중단됨", False, f"{type(e).__name__}: {e}")


# ── 픽스처 ─────────────────────────────────────────────────────────────────────
# DB 를 읽지 않는다. 값은 시드(PO-0117 계열)를 본떴지만 **고정 리터럴**이다 —
# 시드가 바뀌어도 골든이 흔들리지 않아야 "리팩터가 출력을 바꿨는가" 를 볼 수 있다.
# (다른 스파이크들이 기대값을 DB 실측에서 파생시키는 것과 반대 방향인데, 여기서
#  보려는 것이 "시드가 맞는가" 가 아니라 "코드가 출력을 바꿨는가" 이기 때문이다.)

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
            {
                "tool": "search_inventory",
                "manual_page": None,
                "part_no": "LS-IG5A-FAN-01",
                "qty": 1,
                "safety_stock": 2,
            },
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
    "contracts": [
        {"contract_ref": "여신거래약정서 제12조", "text_hash": None, "hash_fixed": False}
    ],
}

FIXTURE_DISPOSAL_KW: dict = {
    "verdict": "PRECONDITION",
    "bundle_hash": "sha256:ee55ff66",
    "reason": "노후 컨베이어 매각 검토 — 라인 재배치",
    "decision_id": "DEC-0007",
}


# ── A. 골든 대조 ───────────────────────────────────────────────────────────────
EXPECTED_GOLDEN_COUNT = 5


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


def regold() -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)
    previews = _previews()
    for name, text in previews.items():
        (GOLDEN_DIR / f"{name}.txt").write_text(text, encoding="utf-8")
    total = sum(len(t.encode("utf-8")) for t in previews.values())
    print(f"골든 {len(previews)}건 재생성 → {GOLDEN_DIR}  (총 {total:,}바이트)")


def run_golden() -> None:
    current = _previews()
    stored = {p.stem: p.read_text(encoding="utf-8") for p in sorted(GOLDEN_DIR.glob("*.txt"))}

    # ★ 양성 축 — 골든이 실제로 존재하고 개수가 맞아야 "일치"가 의미를 갖는다.
    #   이게 없으면 골든 디렉터리가 비었을 때 `not differing` 이 True 라 조용히 통과한다.
    total_bytes = sum(len(v.encode("utf-8")) for v in stored.values())
    check(
        "A① 골든 스냅샷 존재 (liveness 앵커)",
        len(stored) == EXPECTED_GOLDEN_COUNT and total_bytes > 0,
        f"골든 {len(stored)}/{EXPECTED_GOLDEN_COUNT}건 · 총 {total_bytes:,}바이트",
    )

    matched = [n for n in stored if stored[n] == current.get(n)]
    differing = sorted(set(stored) - set(matched))
    # ⚠ detail 에 `"불일치 없음"` 만 찍으면 골든이 0건일 때도 그 문구가 나가 FAIL 을
    #   정반대로 읽게 된다. 두 축(대조한 개수 · 불일치 목록)을 **둘 다** 실측값으로 찍는다.
    check(
        "A② 미리보기 출력 불변 (바이트 동일)",
        len(stored) == EXPECTED_GOLDEN_COUNT and not differing,
        f"대조 {len(stored)}/{EXPECTED_GOLDEN_COUNT}건 · 일치 {len(matched)}건 · "
        + (f"불일치 {differing}" if differing else "불일치 0건"),
    )

    for name in sorted(current):
        cur, old = current[name], stored.get(name)
        check(
            f"A③ {name}",
            old is not None and cur == old,
            f"현재 {len(cur.encode('utf-8')):,}바이트 / 골든 "
            + (f"{len(old.encode('utf-8')):,}바이트" if old is not None else "없음"),
        )


# ── B. 필드맵 ──────────────────────────────────────────────────────────────────
def _field_cases() -> list[tuple[str, str, dict, set[str]]]:
    """(태그, 템플릿 파일명, 필드맵, drop_rows). 태스크가 진행되며 5종으로 늘어난다."""
    from data import doc_fields as df

    return [
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


def run_fields() -> None:
    from backend.services.docx_render import template_placeholders
    from data import doc_fields as df

    for tag, template, fields, dropped in _field_cases():
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
        # ⚠ 부재검사 — `fields` 가 비면 유출도 0이라 조용히 통과한다. 양성 축을 함께 건다.
        leaked = sorted(set(fields) & df.WITHHELD_KEYS)
        check(
            f"B② {tag} 신원·서명 필드를 만들지 않는다 (D23)",
            not leaked and bool(fields),
            f"필드 {len(fields)}개 중 유출 {len(leaked)}개"
            + (f" {leaked}" if leaked else "")
            + f" · 이 템플릿의 withheld 자리 {len(slots & df.WITHHELD_KEYS)}개",
        )
        non_str = sorted(k for k, v in fields.items() if not isinstance(v, str))
        check(
            f"B③ {tag} 모든 값이 문자열이다",
            bool(fields) and not non_str,
            f"문자열 {len(fields) - len(non_str)}/{len(fields)}"
            + (f" · 비문자열 {non_str}" if non_str else ""),
        )


# ── C. 채우기 ──────────────────────────────────────────────────────────────────
def run_fill() -> None:
    import io
    import zipfile

    from backend.services.docx_render import fill_template, template_placeholders
    from data import doc_fields as df

    for tag, template, fields, dropped in _field_cases():
        # 신원 자리는 이 계층이 만들지 않으므로 다운로드 엔드포인트를 흉내 내 채운다.
        withheld_here = template_placeholders(template) & df.WITHHELD_KEYS
        data = fill_template(
            template, dict(fields) | {k: "(미기재)" for k in withheld_here}, drop_rows=dropped
        )
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        left = xml.count("{{")
        check(
            f"C① {tag} 채운 docx 에 미치환 자리가 없다",
            data[:2] == b"PK" and left == 0,
            f"{len(data):,}바이트 · 치환 {len(fields) + len(withheld_here)}자리"
            f" · 삭제행 {len(dropped)}자리 · 잔존 {left}개",
        )


# ── D. DB 컨텍스트 ─────────────────────────────────────────────────────────────
# 여기부터는 실 DB 가 필요하다. **격리 스키마**를 쓴다 — 공유 public 에 쓰면 다른
# 스위트의 회귀가 통째로 무의미해진다(Sprint 16 s10_smoke·sp3_sse_events 실사고).
PO_WITH_ERROR_CODE = "PO-0117"
PO_MISSING = "PO-9999"


def _seed_decision(con) -> str:
    """05·06 검증용 처분 결정 1건. 시드에는 decisions 가 0행이라 여기서 만든다.

    ⛔ MCP 쓰기 도구를 경유하지 않는다 — 이 스위트가 보려는 건 도구의 INSERT 계약이
      아니라 필드맵 조회다. 그건 `write_tool_contract` 30건의 몫이다.
    """
    import json

    asset_id = con.execute("SELECT asset_id FROM assets ORDER BY asset_id LIMIT 1").fetchone()[0]
    bundle = dict(FIXTURE_BUNDLE)
    bundle["facts"] = dict(bundle["facts"], asset_id=asset_id)
    con.execute(
        "INSERT INTO decisions (decision_id, asset_id, decision_type, evidence_bundle,"
        " bundle_hash, verdict_at_signing, state, reason)"
        " VALUES (?, ?, 'DISPOSAL', ?, ?, ?, 'draft', ?)",
        (
            "DEC-9001",
            asset_id,
            json.dumps(bundle, ensure_ascii=False),
            FIXTURE_DISPOSAL_KW["bundle_hash"],
            FIXTURE_DISPOSAL_KW["verdict"],
            FIXTURE_DISPOSAL_KW["reason"],
        ),
    )
    con.commit()
    return "DEC-9001"


def run_context(con, decision_id: str) -> None:
    from data import doc_fields as df

    ctx = df.po_context(con, PO_WITH_ERROR_CODE)
    check(
        "D① po_context 가 발주 컨텍스트를 조립한다",
        ctx is not None
        and ctx["po_id"] == PO_WITH_ERROR_CODE
        and "quotes" in ctx
        and "inventory" in ctx
        and "alternatives" in ctx
        and "error_code_def" in ctx,
        f"po_id={ctx and ctx.get('po_id')} · 견적 {len(ctx.get('quotes') or []) if ctx else 0}건"
        f" · 재고 {'있음' if ctx and ctx.get('inventory') else '없음'}"
        f" · error_code_def {'있음' if ctx and ctx.get('error_code_def') else '없음'}",
    )
    check(
        "D② 없는 발주는 None (예외 아님)",
        df.po_context(con, PO_MISSING) is None,
        f"{PO_MISSING} → None",
    )

    dctx = df.disposal_context(con, decision_id)
    check(
        "D③ disposal_context 가 처분 컨텍스트를 조립한다",
        dctx is not None and dctx["decision_id"] == decision_id and "facts" in (dctx["bundle"] or {}),
        f"decision_id={dctx and dctx.get('decision_id')} · state={dctx and dctx.get('state')}"
        f" · bundle 키 {sorted((dctx or {}).get('bundle') or {})}",
    )
    check(
        "D④ 없는 결정은 None (예외 아님)",
        df.disposal_context(con, "DEC-0000") is None,
        "DEC-0000 → None",
    )
    # ⚠ 부재검사 — 서명 필드가 컨텍스트에 실려 오면 안 된다. 양성 축(컨텍스트가 비지
    #   않았는가)을 함께 건다.
    signature_keys = {"signed_by", "signed_at", "override", "override_reason", "reviewed_by"}
    leaked = sorted(set(dctx or {}) & signature_keys)
    check(
        "D⑤ disposal_context 가 서명 필드를 읽지 않는다 (D23·D81)",
        bool(dctx) and not leaked,
        f"컨텍스트 키 {len(dctx or {})}개 · 서명 유출 {len(leaked)}개"
        + (f" {leaked}" if leaked else ""),
    )

    # 실 DB 컨텍스트로도 필드맵이 완결되는가 (픽스처가 아니라 진짜 행으로)
    from backend.services.docx_render import template_placeholders

    for tag, template, fields, dropped in (
        ("01", "01_설비이상진단보고서.docx", df.fields_01(ctx), df.drop_rows_01(ctx)),
        ("02", "02_정비부품발주요청서.docx", df.fields_02(ctx), df.drop_rows_02(ctx)),
    ):
        expected = template_placeholders(template) - df.WITHHELD_KEYS - dropped
        missing = expected - set(fields)
        check(
            f"D⑥ {tag} 실 DB 행으로도 필드맵이 완결된다",
            not missing and bool(fields),
            f"기대 {len(expected)} / 실제 {len(fields)}"
            + (f" · 부족 {sorted(missing)}" if missing else " · 부족 0"),
        )


# ── E. 읽기 도구 ───────────────────────────────────────────────────────────────
def run_read_tool(decision_id: str) -> None:
    """⚠ 이 도구는 `read_only()` 로 **자기 커넥션을 연다** — 격리 스키마 DSN 은
    `DATABASE_URL` 로 전달돼 있어야 한다. main() 이 그 env 를 세팅한 뒤 부른다."""
    from data import doc_fields as df
    from mcp_server.tools.get_document_facts import get_document_facts

    r = get_document_facts(doc_type="po", ref_id=PO_WITH_ERROR_CODE)
    fields = r.get("fields") or {}
    check(
        "E① po 조회 — 01·02 필드맵",
        r.get("status") == "ok" and set(fields) == {"01", "02"},
        f"status={r.get('status')} · 문서 {sorted(fields)}"
        f" · 01 {len(fields.get('01', {}))}자리 · 02 {len(fields.get('02', {}))}자리",
    )
    # ⚠ 부재검사 — fields 가 비면 유출도 0이라 조용히 통과한다. 양성 축을 함께 건다.
    leaked = sorted(k for doc in fields.values() for k in doc if k in df.WITHHELD_KEYS)
    check(
        "E② 신원·서명 필드를 노출하지 않는다 (D23)",
        not leaked and bool(fields),
        f"문서 {len(fields)}종 · 자리 {sum(len(d) for d in fields.values())}개"
        f" · 유출 {len(leaked)}개" + (f" {leaked}" if leaked else "")
        + f" · withheld 목록 {len(r.get('withheld') or [])}개",
    )
    check(
        "E③ withheld 와 unavailable 이 분리돼 있다 (D62)",
        len(r.get("withheld") or []) == len(df.WITHHELD_KEYS)
        and "03" in (r.get("unavailable") or {}),
        f"withheld {len(r.get('withheld') or [])}/{len(df.WITHHELD_KEYS)}개"
        f" · unavailable {sorted(r.get('unavailable') or {})}",
    )
    check(
        "E④ 교정 경로를 안내한다 (UPDATE 아님, D10)",
        "create_po_draft" in (r.get("correction_hint") or ""),
        repr((r.get("correction_hint") or "")[:56]),
    )

    d = get_document_facts(doc_type="disposal", ref_id=decision_id)
    dfields = d.get("fields") or {}
    check(
        "E⑤ disposal 조회 — 05·06 필드맵",
        d.get("status") == "ok" and set(dfields) == {"05", "06"},
        f"status={d.get('status')} · 문서 {sorted(dfields)}"
        f" · 05 {len(dfields.get('05', {}))}자리 · 06 {len(dfields.get('06', {}))}자리",
    )
    check(
        "E⑥ 처분 필드맵에도 서명 자리가 없다 (D81)",
        not [k for doc in dfields.values() for k in doc if k in df.WITHHELD_KEYS]
        and bool(dfields),
        f"자리 {sum(len(x) for x in dfields.values())}개 중 SIGNED_BY/OVERRIDE 유출 "
        f"{len([k for doc in dfields.values() for k in doc if k in df.WITHHELD_KEYS])}개",
    )

    bad = get_document_facts(doc_type="asset", ref_id="X")
    check(
        "E⑦ enum 밖 doc_type → status=error (예외 아님, D9)",
        bad.get("status") == "error" and bad.get("reason") == "invalid_input",
        f"{bad.get('status')}/{bad.get('reason')}",
    )
    blank = get_document_facts(doc_type="po", ref_id="   ")
    check(
        "E⑧ 빈 ref_id → invalid_input",
        blank.get("status") == "error" and blank.get("reason") == "invalid_input",
        f"{blank.get('status')}/{blank.get('reason')}",
    )
    nf = get_document_facts(doc_type="po", ref_id=PO_MISSING)
    check(
        "E⑨ 없는 ref_id → not_found",
        nf.get("status") == "error" and nf.get("reason") == "not_found",
        f"{nf.get('status')}/{nf.get('reason')}",
    )

    # ⚠ 부재검사 — 소스에 쓰기 경로가 없다. 양성 축(read_only 사용 · 소스가 실제로
    #   읽혔는가)을 판정과 detail 에 함께 넣는다.
    src = (ROOT / "mcp_server" / "tools" / "get_document_facts.py").read_text(encoding="utf-8")
    # ⚠ 주석·docstring 을 먼저 걷어낸다 — 이 파일의 docstring 에는 "draft_writer 를
    #   부르지 않는다", "MCP UPDATE 로 얻는 건" 처럼 **금지 토큰이 설명으로** 들어 있다.
    #   첫 구현에서 그대로 스캔해 E⑩ 이 FAIL 했다 — 코드가 아니라 스캐너가 틀렸던 것이다.
    #   AST 로 **실행되는 코드**만 본다(문자열 리터럴 제외).
    import ast

    tree = ast.parse(src)
    body = "\n".join(
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Call, ast.Attribute, ast.Name))
    )
    uses_readonly = "read_only()" in body
    writers = [w for w in ("draft_writer", "decision_writer", "repair_writer") if w in body]
    dml = [k for k in ("INSERT ", "UPDATE ", "DELETE ") if k in body.upper()]
    check(
        "E⑩ 읽기 전용 — 쓰기 커넥션·DML 이 없다 (D10)",
        uses_readonly and not writers and not dml,
        f"소스 {len(src):,}바이트 · read_only()={uses_readonly}"
        f" · writer {writers or '없음'} · DML {dml or '없음'}",
    )


# ── F. 다운로드 엔드포인트 ─────────────────────────────────────────────────────
def _docx_xml(body: bytes) -> str:
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(body)) as z:
        return z.read("word/document.xml").decode("utf-8")


def run_download(client, decision_id: str) -> None:
    from backend.services.docx_render import DOCX_MIME

    h = {"X-User": "tech-01"}
    r = client.get(f"/api/po/{PO_WITH_ERROR_CODE}/documents/po_request.docx", headers=h)
    body = r.content
    check(
        "F① 02 발주요청서 다운로드 — 200 · docx MIME",
        r.status_code == 200 and r.headers.get("content-type", "").startswith(DOCX_MIME),
        f"{r.status_code} · {r.headers.get('content-type', '')[:46]}… · {len(body):,}바이트",
    )
    cd = r.headers.get("content-disposition", "")
    check(
        "F② Content-Disposition — attachment + RFC 5987 한글 파일명",
        "attachment" in cd and "filename*=UTF-8''" in cd and 'filename="' in cd,
        cd[:96],
    )
    xml = _docx_xml(body) if body[:2] == b"PK" else ""
    check(
        "F③ 미치환 자리가 없다",
        body[:2] == b"PK" and xml.count("{{") == 0,
        f"zip={body[:2] == b'PK'} · xml {len(xml):,}자 · '{{{{' 잔존 {xml.count('{{')}개",
    )
    # ⚠ 부재검사가 아니라 **양성** 검사다 — 신원이 실제로 얹혔는지 본다.
    #   doc_fields 는 이 자리를 만들지 않으므로, 비어 있으면 엔드포인트가 안 얹은 것이다.
    #   기대값은 **DB 실측에서 파생**한다 — 처음엔 픽스처 값("김정비")을 하드코딩했다가
    #   FAIL 했다. 실제 시드는 "김OO"(D36 — 표시명은 서버가 매핑)라, 검사가 아니라
    #   기대값이 틀렸던 것이다. 시드가 바뀌면 기대값도 같이 움직여야 한다.
    from backend.services.po import get_po  # noqa: PLC0415

    live = get_po(PO_WITH_ERROR_CODE) or {}
    requester = live.get("requested_by_name") or ""
    dept = live.get("requested_by_department") or ""
    check(
        "F④ 신원이 실제로 채워진다 (엔드포인트만 얹는다, D23)",
        bool(requester) and requester in xml and bool(dept) and dept in xml,
        f"요청자 {requester!r} 발견={requester in xml}"
        f" · 소속 {dept!r} 발견={dept in xml} · xml {len(xml):,}자",
    )
    d = client.get(f"/api/po/{PO_WITH_ERROR_CODE}/documents/diagnosis.docx", headers=h)
    check(
        "F⑤ 01 진단보고서 — error_code_def 있으면 200",
        d.status_code == 200 and d.content[:2] == b"PK",
        f"{d.status_code} · {len(d.content):,}바이트",
    )
    f3 = client.get(f"/api/po/{PO_WITH_ERROR_CODE}/documents/fund_execution.docx", headers=h)
    check(
        "F⑥ 03 자금집행요청서 — 재무 결정 전이면 404 (미리보기와 같은 조건)",
        f3.status_code == 404,
        f"{f3.status_code} · documents_preview.fund_execution 이 None 인 상태와 같다",
    )
    check(
        "F⑦ 없는 문서 키 → 404",
        client.get(f"/api/po/{PO_WITH_ERROR_CODE}/documents/xxx.docx", headers=h).status_code == 404,
        "doc 화이트리스트 밖",
    )
    check(
        "F⑧ 없는 발주 → 404",
        client.get(f"/api/po/{PO_MISSING}/documents/po_request.docx", headers=h).status_code == 404,
        PO_MISSING,
    )

    a = client.get(f"/api/decisions/{decision_id}/documents/approval.docx", headers=h)
    axml = _docx_xml(a.content) if a.content[:2] == b"PK" else ""
    check(
        "F⑨ 05 처분승인서 다운로드 — 200 · 미치환 0",
        a.status_code == 200 and axml.count("{{") == 0,
        f"{a.status_code} · {len(a.content):,}바이트 · 잔존 {axml.count('{{')}개",
    )
    check(
        "F⑩ 서명 전에는 '(미기재 — 서명 시 기록된다)' (D81)",
        "미기재" in axml and "적용" in axml,
        f"미기재 표기={'있음' if '미기재' in axml else '없음'}"
        f" · OVERRIDE 표기={'있음' if '적용' in axml else '없음'}",
    )
    w = client.get(f"/api/decisions/{decision_id}/documents/representation_warranty.docx", headers=h)
    wxml = _docx_xml(w.content) if w.content[:2] == b"PK" else ""
    check(
        "F⑪ 06 진술및보장서 다운로드 — 200 · 미치환 0",
        w.status_code == 200 and wxml.count("{{") == 0,
        f"{w.status_code} · {len(w.content):,}바이트 · 잔존 {wxml.count('{{')}개",
    )
    check(
        "F⑫ 없는 결정 → 404",
        client.get("/api/decisions/DEC-0000/documents/approval.docx", headers=h).status_code == 404,
        "DEC-0000",
    )

    # ★ D86 — 생성물이 어디에도 저장되지 않았는가. 다운로드 **후** 파일 시스템을 본다.
    before = {p.name for p in (ROOT / "data" / "templates").iterdir()}
    check(
        "F⑬ 무저장 — 템플릿 폴더에 산출물이 생기지 않는다 (D86)",
        before == EXPECTED_TEMPLATE_FILES,
        f"파일 {len(before)}개 · 예상 밖 {sorted(before - EXPECTED_TEMPLATE_FILES) or '없음'}",
    )


EXPECTED_TEMPLATE_FILES = {
    "01_설비이상진단보고서.docx",
    "02_정비부품발주요청서.docx",
    "03_자금집행요청서.docx",
    "04_담보대출심사회신서.docx",  # D118 — 렌더 대상은 아니지만 파일은 있다
    "05_설비처분승인서.docx",
    "06_진술및보장서.docx",
    "README.md",
}


def main() -> None:
    if os.environ.get("DOCX_CONTRACT_REGOLD"):
        regold()
        return

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    guard("A", run_golden)
    guard("B", run_fields)
    guard("C", run_fill)

    # D~F 는 실 DB 가 필요하다. 격리 스키마에서만 돈다 — 공유 public 을 건드리면
    # 다른 스위트의 회귀가 통째로 무의미해진다.
    from data import dbcompat, pg_isolation

    schema = None
    try:
        schema, dsn = pg_isolation.create_isolated_schema("docx_contract")
        con = dbcompat.connect_dsn(dsn)
        try:
            decision_id = _seed_decision(con)
            guard("D", run_context, con, decision_id)
        finally:
            con.close()
        # 읽기 도구는 `read_only()` 로 **자기 커넥션을 연다.**
        #
        # ⚠ `os.environ["DATABASE_URL"]` 만 바꾸면 격리되지 않는다 — `mcp_server/db.py:22`
        #   가 그 값을 **import 시점에** 모듈 상수로 굳히는데, 이 스파이크는 run_golden()
        #   에서 이미 그 모듈을 import 한 뒤다. 실측으로 확인했다: env 만 바꿨을 때 도구가
        #   공유 public 을 읽어 E⑤(처분 조회)가 FAIL 했고, E①(발주 조회)은 PO-0117 이
        #   public 에도 있어서 **가짜로 통과**했다. Sprint 16 의 s10_smoke·sp3_sse_events
        #   실사고와 같은 계열이다.
        #   → 모듈 상수를 함께 갈아끼운다. E⑤ 가 격리 앵커 역할을 한다 — DEC-9001 은
        #     격리 스키마에만 있으므로, 도구가 public 을 읽으면 그 검사가 FAIL 한다.
        import mcp_server.db as _mcp_db

        prev_env = os.environ.get("DATABASE_URL")
        prev_const = _mcp_db.DATABASE_URL
        os.environ["DATABASE_URL"] = dsn
        _mcp_db.DATABASE_URL = dsn
        import backend.db as _bk_db

        prev_bk = _bk_db.DATABASE_URL
        _bk_db.DATABASE_URL = dsn
        try:
            guard("E", run_read_tool, decision_id)

            os.environ["MAINTQ_MCP_AUTOSTART"] = "0"  # 다운로드는 MCP 와 무관하다
            from fastapi.testclient import TestClient  # noqa: PLC0415

            from backend.main import app  # noqa: PLC0415

            with TestClient(app) as client:
                guard("F", run_download, client, decision_id)
        finally:
            _bk_db.DATABASE_URL = prev_bk
            _mcp_db.DATABASE_URL = prev_const
            if prev_env is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = prev_env
    finally:
        if schema:
            pg_isolation.drop_isolated_schema(schema)
            # ⚠ "정리됐다" 를 문구로 주장하지 않는다 — Postgres 에 **직접 물어본다**.
            #   drop 호출을 지웠을 때 이 검사가 FAIL 해야 검사로서 의미가 있다.
            probe = dbcompat.connect_dsn(pg_isolation.BASE_DATABASE_URL)
            try:
                left = probe.execute(
                    "SELECT count(*) FROM information_schema.schemata"
                    " WHERE schema_name = ?",
                    (schema,),
                ).fetchone()[0]
                total = probe.execute(
                    "SELECT count(*) FROM information_schema.schemata"
                    " WHERE schema_name LIKE 'docx_contract%'"
                ).fetchone()[0]
            finally:
                probe.close()
            check(
                "D⑦ 격리 스키마 잔존 확인",
                left == 0,
                f"{schema} 잔존 {left}개 · docx_contract* 전체 잔존 {total}개",
            )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 34))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 34))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건:\n  - " + "\n  - ".join(failed))
    print(
        f"\n통과 ({len(results)}건) — 골든 {EXPECTED_GOLDEN_COUNT}종 · "
        f"필드맵 {len(_field_cases())}문서 · 채우기 {len(_field_cases())}종 · "
        f"DB 컨텍스트 · 읽기 도구 · 다운로드"
    )


if __name__ == "__main__":
    main()
