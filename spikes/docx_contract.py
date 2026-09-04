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


def main() -> None:
    if os.environ.get("DOCX_CONTRACT_REGOLD"):
        regold()
        return

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    run_golden()
    run_fields()
    run_fill()

    # D~F 는 실 DB 가 필요하다. 격리 스키마에서만 돈다 — 공유 public 을 건드리면
    # 다른 스위트의 회귀가 통째로 무의미해진다.
    from data import dbcompat, pg_isolation

    schema = None
    try:
        schema, dsn = pg_isolation.create_isolated_schema("docx_contract")
        con = dbcompat.connect_dsn(dsn)
        try:
            decision_id = _seed_decision(con)
            run_context(con, decision_id)
        finally:
            con.close()
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
        f"필드맵 {len(_field_cases())}문서 · 채우기 {len(_field_cases())}종 · DB 컨텍스트"
    )


if __name__ == "__main__":
    main()
