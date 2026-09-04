# -*- coding: utf-8 -*-
"""쓰기 도구 **3종** 계약 검증 — `create_po_draft` · `generate_disposal_document` ·
`create_repair_record`.

검증 대상:
  create_po_draft (①~⑭)          D10(draft INSERT만) · D23·D37(신원은 스키마에 없음) ·
                                  D31(단가 스냅샷 / MOQ 거부) · D33(코드 FK) · D34(evidence)
  generate_disposal_document (⑮~⑲, MQ-706)
                                  D10(`decisions` draft INSERT만 · TEMP TRIGGER 2개) ·
                                  D81(`override`·`override_reason`·`reviewed_by` 가 **스키마에
                                  없다**) · D63(BLOCKED 여도 draft 는 만들어진다) ·
                                  D84(저장된 `evidence_bundle` 로 `bundle_hash` 재대조) ·
                                  D80(`reason` 필수) · "근거 없으면 아무것도 쓰지 않는다"
  create_repair_record (㉔~㉚, MQ-913·D98)
                                  D98(`repair_records` 전용 `repair_writer()` · draft INSERT만) ·
                                  ⓑ 서명·신원·`state` 가 스키마에 없다 · ⓒ 미존재 부품 →
                                  `unknown_part`, 행 수 불변(아무것도 안 씀을 직접 센다) ·
                                  ⓓ 응답의 `expenditure_class` 가 DB 저장값과 일치

★ **"막았다"를 선언하지 않고 증명한다.** 트리거는 각 테이블 전용 writer 커넥션으로 실제
  UPDATE·DELETE SQL 을 날려 ABORT 를 확인한다 — `decisions` 는 ⑯⑰(전용 커넥션), `repair_records`
  는 ㉙㉚(전용 커넥션). `law_text_unavailable` 은 "실패했다"가 아니라 **`decisions` 행 수가
  그대로다**(⑱)로 확인한다.
  ⛔ 어느 트리거 확인에도 **다른 테이블 전용 writer** 를 쓰지 않는다 — 예를 들어 `po_drafts`
    전용 트리거만 걸린 커넥션으로 `decisions` 를 만지거나, `decisions` 전용 커넥션으로
    `repair_records` 를 만지면 잠기지 않은 경로를 통과시키고도 통과가 된다.

실제 DB를 오염시키지 않도록 **임시 사본**을 만들고 MAINTQ_DB 로 주입한다.
error_codes 는 사람 승인 전이라 비어 있으므로, D33 FK 검증만은 사본에
검증용 코드 1건을 직접 넣어 확인한다 (원본 DB·추출 JSON 은 건드리지 않음).

⚠ **MQ-707 DDL 대기** — MQ-706 의 draft INSERT 계약은 `decisions.reason` 에 값을 넣는데,
  그 컬럼은 `data/seed.py` DDL 에 아직 없다(MQ-707 이 `reason`·`requested_by`·`session_id`
  3개를 동시에 추가하는 중). 그래서 **사본에만** 없으면 추가한다(`prepare_db`) —
  제품 코드·seed.py 에는 넣지 않는다. MQ-707 착지 후에는 이 보정이 저절로 무동작이 된다.

실행:  uv run python spikes/write_tool_contract.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT_FOR_IMPORT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_FOR_IMPORT))
from data import dbcompat, pg_isolation  # noqa: E402


def _open(db):
    """`db` 는 SQLite 타겟이면 사본 경로(Path), Postgres 타겟이면 격리 스키마의
    (schema, dsn) 튜플이다 — Postgres 는 공유 DB 를 오염시키지 않으려고 스키마 단위로
    격리한다(data/pg_isolation.py, Sprint 16 MQ-1614)."""
    if dbcompat.USE_POSTGRES:
        return dbcompat.connect_dsn(db[1])
    return sqlite3.connect(db)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SERVER = ROOT / "mcp_server" / "server.py"
SOURCE_DB = ROOT / "data" / "maintq.db"

# 처분 초안 케이스에 쓰는 자산. 실 DB 시드 기준 판정이 갈린다 —
#   AST-L3-LIFT  CONDITIONAL (선행 조건형)
#   AST-L3-CONV  BLOCKED     (담보 미동의 — D63 케이스: 막지 않고 기록한다)
ASSET_CONDITIONAL = "AST-L3-LIFT"
ASSET_BLOCKED = "AST-L3-CONV"
DISPOSAL_DATE = "2026-09-01"

# 이 조문을 미수집으로 되돌리면 `VAT-INVOICE` 가 인용하는 원문이 사라져
# `law_text_unavailable` 경로가 열린다 (SALE 처분이면 어느 자산이든 인용된다).
LAW_TO_BREAK = "KR-VAT-32"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


def payload(result) -> dict:
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(result.content[0].text)


DDL_NOTE = ""


def prepare_db(tmp: Path):
    """실제 DB 사본(SQLite) / 격리 스키마(Postgres) + D33 검증용 error_codes 1건
    (+ MQ-707 DDL 대기 보정)."""
    global DDL_NOTE
    if dbcompat.USE_POSTGRES:
        schema, dsn = pg_isolation.create_isolated_schema("write_tool")
        db = (schema, dsn)
    else:
        db = tmp / "contract.db"
        shutil.copy2(SOURCE_DB, db)
    con = _open(db)
    con.execute("PRAGMA foreign_keys=ON")

    # ── MQ-707 DDL 대기: `decisions.reason` 이 없으면 **사본에만** 만든다.
    #    스키마 정본은 data/seed.py 한 곳이다 — 여기 보정이 제품 스키마를 대신하지 않는다.
    cols = {r[1] for r in con.execute("PRAGMA table_info(decisions)")}
    if "reason" not in cols:
        con.execute("ALTER TABLE decisions ADD COLUMN reason TEXT")
        DDL_NOTE = "사본에 decisions.reason 임시 추가 (MQ-707 DDL 대기)"
    else:
        DDL_NOTE = "decisions.reason 이 이미 스키마에 있음 (MQ-707 착지 완료)"

    # OR REPLACE — iG5A 매핑 승인(2026-07-28) 후로는 복사한 실 DB 에 이미 (iG5A, OHT) 가
    # 있을 수 있다. 이 테스트의 고정 fixture 값(causes·actions 등)이 실 데이터와 무관하게
    # 항상 이겨야 뒤 검증이 결정적이다 — 순수 INSERT 면 UNIQUE 충돌로 죽는다.
    con.execute(
        "INSERT OR REPLACE INTO error_codes (model, code, display_code, error_name, severity,"
        " causes, actions, related_parts, manual_page)"
        " VALUES ('iG5A','OHT','OHt','인버터 과열','warning','[]','[]',NULL,202)"
    )
    con.commit()
    con.close()
    return db


EVIDENCE = {
    "symptoms": ["냉각팬 소음 증가"],
    "basis": [{"tool": "lookup_error_code", "code": "OHT", "manual_page": 202}],
    "notes": "야간조 육안 확인",
}


def decision_count(db: Path) -> int:
    con = _open(db)
    try:
        return int(con.execute("SELECT count(*) FROM decisions").fetchone()[0])
    finally:
        con.close()


def repair_count(db: Path) -> int:
    con = _open(db)
    try:
        return int(con.execute("SELECT count(*) FROM repair_records").fetchone()[0])
    finally:
        con.close()


def set_law_fetched(db: Path, law_ref_id: str, fetched: bool, snapshot: tuple | None) -> tuple:
    """조문 원문을 미수집으로 되돌리거나(FALSE) 원상 복구한다(TRUE). 이전 값을 돌려준다."""
    con = _open(db)
    try:
        before = con.execute(
            "SELECT fetch_status, text, text_hash FROM law_refs WHERE law_ref_id=?",
            (law_ref_id,),
        ).fetchone()
        if fetched:
            con.execute(
                "UPDATE law_refs SET fetch_status=?, text=?, text_hash=? WHERE law_ref_id=?",
                (*snapshot, law_ref_id),  # type: ignore[misc]
            )
        else:
            con.execute(
                "UPDATE law_refs SET fetch_status='PENDING', text=NULL, text_hash=NULL"
                " WHERE law_ref_id=?",
                (law_ref_id,),
            )
        con.commit()
        return before
    finally:
        con.close()


async def run(db) -> tuple[str, str, str]:
    # `generate_disposal_document` 는 확장 도구라 **full 프로파일에서만** 등록된다 (D69).
    # 코어 도구(create_po_draft)는 두 프로파일 모두에 있으므로 한 세션으로 2종을 다 본다.
    if dbcompat.USE_POSTGRES:
        # 서브프로세스가 os.environ 을 상속하므로, 그대로 두면 공유 DATABASE_URL 을 봐서
        # 격리 스키마가 아니라 공유 Postgres 에 써버린다 — 격리 스키마 DSN 으로 덮어쓴다.
        env = {**os.environ, "DATABASE_URL": db[1], "MAINTQ_TOOLS_PROFILE": "full"}
    else:
        env = {**os.environ, "MAINTQ_TOOLS_PROFILE": "full"}
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            listed = await session.list_tools()
            tool = next(t for t in listed.tools if t.name == "create_po_draft")
            props = set((tool.inputSchema or {}).get("properties", {}))

            # ── D23·D37: 신원·단가가 LLM 이 채울 수 있는 자리에 있으면 안 된다
            forbidden = {"requested_by", "decided_by", "session_id", "unit_price", "state"}
            check(
                "① 신원·단가·state 가 스키마에 없음 (D23·D31·D37)",
                not (props & forbidden),
                f"노출 파라미터: {sorted(props)}",
            )

            # ── 정상 발주 (MOQ 1 인 SUP-A)
            ok = payload(
                await session.call_tool(
                    "create_po_draft",
                    {
                        "part_no": "FAN-IG5-01",
                        "qty": 2,
                        "supplier_id": "SUP-A",
                        "reason": "iG5A OHt 과열 — 냉각팬 고장 유력 (매뉴얼 p.202)",
                        "urgency": "urgent",
                        "model": "iG5A",
                        "error_code": "OHt",
                        "evidence": EVIDENCE,
                    },
                )
            )
            check(
                "② 정상 발주 → draft 생성",
                ok["status"] == "ok" and ok["state"] == "draft",
                f"po_id={ok.get('po_id')}, state={ok.get('state')}",
            )
            check(
                "③ D31 단가 스냅샷 (입력 아님)",
                ok.get("unit_price") == 38000 and ok.get("total") == 76000,
                f"unit_price={ok.get('unit_price')}, total={ok.get('total')}",
            )
            po_id = ok["po_id"]

            # ── D31: MOQ 미달은 자동 상향이 아니라 거부
            moq = payload(
                await session.call_tool(
                    "create_po_draft",
                    {
                        "part_no": "FAN-IG5-01",
                        "qty": 2,
                        "supplier_id": "SUP-B",  # MOQ 10
                        "reason": "단가 저렴한 B사로",
                    },
                )
            )
            check(
                "④ D31 MOQ 미달 거부 (자동 상향 안 함)",
                moq["status"] == "error"
                and moq.get("reason") == "moq_not_met"
                and moq.get("moq") == 10,
                f"reason={moq.get('reason')}, moq={moq.get('moq')}",
            )

            # ── D33: 매뉴얼에 없는 코드는 거부
            bad = payload(
                await session.call_tool(
                    "create_po_draft",
                    {
                        "part_no": "FAN-IG5-01",
                        "qty": 1,
                        "supplier_id": "SUP-A",
                        "reason": "미지 코드로 발주 시도",
                        "model": "iG5A",
                        "error_code": "XY9",
                    },
                )
            )
            check(
                "⑤ D33 미지 코드 거부 (환각이 발주까지 못 감)",
                bad["status"] == "error" and bad.get("reason") == "unknown_error_code",
                f"reason={bad.get('reason')}",
            )

            # ── D33: model 만 주고 code 를 빼면 거부
            pair = payload(
                await session.call_tool(
                    "create_po_draft",
                    {
                        "part_no": "FAN-IG5-01",
                        "qty": 1,
                        "supplier_id": "SUP-A",
                        "reason": "짝 안 맞는 입력",
                        "model": "iG5A",
                    },
                )
            )
            check(
                "⑥ D33 model/code 짝 강제",
                pair["status"] == "error" and pair.get("reason") == "model_code_pair",
                f"reason={pair.get('reason')}",
            )

            # ── D5: reason 없이는 발주 못 만든다
            noreason = payload(
                await session.call_tool(
                    "create_po_draft",
                    {"part_no": "FAN-IG5-01", "qty": 1, "supplier_id": "SUP-A", "reason": "  "},
                )
            )
            check(
                "⑦ D5 reason 필수",
                noreason["status"] == "error" and noreason.get("reason") == "reason_required",
                f"reason={noreason.get('reason')}",
            )

            # ── 공급 안 하는 조합
            nq = payload(
                await session.call_tool(
                    "create_po_draft",
                    {
                        "part_no": "FAN-IG5-01",
                        "qty": 1,
                        "supplier_id": "SUP-D",
                        "reason": "공급 안 하는 조합",
                    },
                )
            )
            check(
                "⑧ 견적 없는 공급사 → not_found",
                nq["status"] == "not_found" and nq.get("reason") == "no_quote",
                f"status={nq['status']}, reason={nq.get('reason')}",
            )

            # ─────────────────────────────────────────────────────────────────
            # generate_disposal_document (MQ-706) — 두 번째 쓰기 도구
            # ─────────────────────────────────────────────────────────────────
            doc_tool = next(t for t in listed.tools if t.name == "generate_disposal_document")
            doc_schema = doc_tool.inputSchema or {}
            doc_props = set(doc_schema.get("properties", {}))
            doc_required = set(doc_schema.get("required") or [])

            # ── D81 — LLM 이 BLOCKING 을 뚫는 호출 자체가 **구조적으로 불가능**해야 한다.
            #    "쓰지 마라"를 description 에 적는 것으로는 부족하다. 키가 없어야 한다.
            override_keys = {"override", "override_reason", "reviewed_by"}
            identity_keys = {
                "requested_by",
                "session_id",
                "state",
                "signed_at",
                "verdict_at_signing",
            }
            check(
                "⑮ D81 스키마에 override·override_reason·reviewed_by 키 없음 (+D23 신원·상태 없음)",
                not (doc_props & override_keys)
                and not (doc_props & identity_keys)
                and doc_required == {"reason"},
                f"노출 파라미터={sorted(doc_props)} · required={sorted(doc_required)}",
            )

            # ── D80·D5 — reason 공백이면 draft 를 만들지 않는다
            before_blank = decision_count(db)
            blank = payload(
                await session.call_tool(
                    "generate_disposal_document",
                    {"reason": "   ", "asset_id": ASSET_CONDITIONAL},
                )
            )
            check(
                "⑯ reason 공백 → reason_required · 행 수 불변",
                blank["status"] == "error"
                and blank.get("reason") == "reason_required"
                and decision_count(db) == before_blank,
                f"reason={blank.get('reason')} · decisions={before_blank}→{decision_count(db)}",
            )

            # ── 정상 초안 (CONDITIONAL 자산)
            cond = payload(
                await session.call_tool(
                    "generate_disposal_document",
                    {
                        "reason": "노후 리프터 매각 — 대체 설비 도입으로 유휴",
                        "asset_id": ASSET_CONDITIONAL,
                        "disposal_mode": "SALE",
                        "disposal_date": DISPOSAL_DATE,
                    },
                )
            )
            preview = cond.get("documents_preview") or {}
            check(
                "⑰ 처분 초안 생성 → state=draft · override=false · 미검수 고지 · 문서 2종",
                cond["status"] == "ok"
                and cond["state"] == "draft"
                and cond["decision_type"] == "DISPOSAL"
                and cond["override"] is False
                and cond["asset_id"] == ASSET_CONDITIONAL
                and set(preview) == {"approval", "representation_warranty"}
                and all(cond["template_review_notice"] in v for v in preview.values()),
                f"decision_id={cond.get('decision_id')} verdict_at_signing="
                f"{cond.get('verdict_at_signing')} · 문서={sorted(preview)}",
            )
            # 실패해도 여기서 죽지 않는다 — 뒤 검증이 **깨끗한 FAIL** 로 보고돼야
            # "무엇이 어긋났는지"가 표에 남는다 (트레이스백은 그걸 지운다).
            cond_id = cond.get("decision_id")

            # ── D63 — BLOCKED 여도 막지 않는다. "차단된 채로 결재에 올라간다"
            blocked = payload(
                await session.call_tool(
                    "generate_disposal_document",
                    {
                        "reason": "담보 설정 상태이나 라인 폐쇄로 매각 검토",
                        "asset_id": ASSET_BLOCKED,
                        "disposal_mode": "SALE",
                        "disposal_date": DISPOSAL_DATE,
                    },
                )
            )
            check(
                "⑱ D63 BLOCKED 자산도 draft 생성 (막지 않고 기록한다) · override 는 여전히 false",
                blocked["status"] == "ok"
                and blocked["verdict_at_signing"] == "BLOCKED"
                and blocked["state"] == "draft"
                and blocked["override"] is False,
                f"verdict_at_signing={blocked.get('verdict_at_signing')} "
                f"decision_id={blocked.get('decision_id')}",
            )
            blocked_id = blocked.get("decision_id")

            # ── 근거 원문이 없으면 **아무것도 쓰지 않는다** — 실패 선언이 아니라 행 수로 증명
            before_missing = decision_count(db)
            snapshot = set_law_fetched(db, LAW_TO_BREAK, fetched=False, snapshot=None)
            try:
                missing = payload(
                    await session.call_tool(
                        "generate_disposal_document",
                        {
                            "reason": "조문 미수집 상태에서 초안 시도",
                            "asset_id": ASSET_CONDITIONAL,
                            "disposal_mode": "SALE",
                            "disposal_date": DISPOSAL_DATE,
                        },
                    )
                )
            finally:
                set_law_fetched(db, LAW_TO_BREAK, fetched=True, snapshot=snapshot)
            after_missing = decision_count(db)
            check(
                "⑲ law_text_unavailable 전파 → draft 미생성 (decisions 행 수 불변)",
                missing["status"] == "error"
                and missing.get("reason") == "law_text_unavailable"
                and LAW_TO_BREAK in (missing.get("missing_law_refs") or [])
                and after_missing == before_missing,
                f"reason={missing.get('reason')} · missing={missing.get('missing_law_refs')} "
                f"· decisions={before_missing}→{after_missing}",
            )

            # ─────────────────────────────────────────────────────────────────
            # create_repair_record (MQ-913, D98) — 세 번째 쓰기 도구
            # ─────────────────────────────────────────────────────────────────
            repair_tool = next(t for t in listed.tools if t.name == "create_repair_record")
            repair_props = set((repair_tool.inputSchema or {}).get("properties", {}))

            # ⓑ D98 — 서명·신원·state 필드가 스키마에 없다. 키가 없으므로 LLM 이 서명·확정을
            #    지어내 호출하는 경로 자체가 구조적으로 불가능하다 (D81 태도의 복제).
            repair_forbidden = {
                "override",
                "signed_at",
                "record_hash",
                "performed_by",
                "verified_by",
                "state",
            }
            check(
                "㉔ D98 서명·신원·state 가 create_repair_record 스키마에 없음",
                not (repair_props & repair_forbidden),
                f"노출 파라미터: {sorted(repair_props)}",
            )

            # 정상 수리 증빙 초안
            rep_ok = payload(
                await session.call_tool(
                    "create_repair_record",
                    {
                        "equipment_id": "INV-L3-01",
                        "work_type": "UNPLANNED",
                        "repair_scope": "RESTORE",
                        "cost": 850000,
                        "parts": [{"part_no": "FAN-IG5-01", "serial": "SN-WT-01", "qty": 1}],
                        "downtime_hours": 6.5,
                        "model": "iG5A",
                        "error_code": "OHt",
                        "note": "write_tool_contract 회귀",
                    },
                )
            )
            check(
                "㉕ 정상 수리 증빙 → draft 생성",
                rep_ok["status"] == "ok" and rep_ok["state"] == "draft",
                f"repair_id={rep_ok.get('repair_id')}, state={rep_ok.get('state')}",
            )
            repair_id = rep_ok.get("repair_id")
            repair_expenditure_class = rep_ok.get("expenditure_class")

            # ⓒ 미존재 부품 → unknown_part. "실패했다"고 말하는 것이 아니라 행 수가
            #    그대로임을 직접 세서 **아무것도 쓰지 않았음**을 증명한다.
            before_missing_part = repair_count(db)
            rep_missing = payload(
                await session.call_tool(
                    "create_repair_record",
                    {
                        "equipment_id": "INV-L3-01",
                        "work_type": "UNPLANNED",
                        "repair_scope": "RESTORE",
                        "cost": 10000,
                        "parts": [{"part_no": "NOT-A-REAL-PART"}],
                    },
                )
            )
            after_missing_part = repair_count(db)
            check(
                "㉖ ⓒ 미존재 부품 → not_found/unknown_part · repair_records 행 수 불변",
                rep_missing["status"] == "not_found"
                and rep_missing.get("reason") == "unknown_part"
                and after_missing_part == before_missing_part,
                f"status={rep_missing['status']} reason={rep_missing.get('reason')} "
                f"· repair_records={before_missing_part}→{after_missing_part}",
            )

            return po_id, cond_id, blocked_id, repair_id, repair_expenditure_class


def verify_row(db: Path, po_id: str) -> None:
    con = _open(db)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM po_drafts WHERE po_id=?", (po_id,)).fetchone()

    check(
        "⑨ D10 state 는 draft 고정",
        r["state"] == "draft",
        f"state={r['state']}",
    )
    check(
        "⑩ D23 신원은 도구가 못 채움 (INSERT 시 NULL)",
        r["requested_by"] is None and r["session_id"] is None,
        f"requested_by={r['requested_by']}, session_id={r['session_id']}",
    )
    ev = json.loads(r["evidence"])
    check(
        "⑪ D34 evidence 저장",
        set(ev) == {"symptoms", "basis", "notes"} and ev["symptoms"],
        f"keys={sorted(ev)}",
    )
    check(
        "⑫ D25 코드는 대문자 canonical 저장 ('OHt'→'OHT')",
        r["error_code"] == "OHT" and r["model"] == "iG5A",
        f"model={r['model']}, error_code={r['error_code']}",
    )
    con.close()

    # ── D37: 백엔드가 신원을 stamp 한다
    sys.path.insert(0, str(ROOT))
    import backend.db as backend_db  # noqa: PLC0415
    from backend.services.po import display_name, stamp_identity  # noqa: PLC0415

    if dbcompat.USE_POSTGRES:
        # backend/db.py 도 Postgres 전용이라 db_path 인자를 더 안 본다(DATABASE_URL 전역
        # 고정) — 공유 DB 대신 이 테스트의 격리 스키마를 상대로 stamp 하도록 바꿔야 한다.
        backend_db.DATABASE_URL = db[1]
    # ⚠ `db` 는 Postgres 타겟이면 **(schema, dsn) 튜플**이다(`_open` 참조) — 백엔드로
    #   넘길 때는 DSN 문자열만 준다. 튜플을 그대로 넘기면 `backend/db.py::connect()` 가
    #   **조용히 무시하고 공유 DB 를 stamp** 했다(2026-08-29 가드 도입으로 발각).
    stamp_target = db[1] if dbcompat.USE_POSTGRES else None
    ok1 = stamp_identity(po_id, "tech-01", "S1", db_path=stamp_target)
    ok2 = stamp_identity(po_id, "mgr-01", "S9", db_path=stamp_target)  # 재stamp 시도
    con = _open(db)
    con.row_factory = sqlite3.Row
    r2 = con.execute("SELECT * FROM po_drafts WHERE po_id=?", (po_id,)).fetchone()
    con.close()
    check(
        "⑬ D37 백엔드 stamp (1회만, 덮어쓰기 불가)",
        ok1 and not ok2 and r2["requested_by"] == "tech-01" and r2["session_id"] == "S1",
        f"1차={ok1}, 2차={ok2}, requested_by={r2['requested_by']}",
    )
    check(
        "⑭ D36 표시명은 서버 매핑",
        display_name("tech-01") == "김OO",
        f"tech-01 → {display_name('tech-01')}",
    )


def verify_decision_rows(db: Path, cond_id: str | None, blocked_id: str | None) -> None:
    """`decisions` 저장분 검증 — MQ-707 이 전제하는 draft INSERT 계약 그대로인가."""
    if cond_id is None or blocked_id is None:
        for mark in ("⑳", "㉑", "㉒", "㉓"):
            check(f"{mark} decisions 저장분 검증", False, "선행 draft 생성이 실패해 검증 불가")
        return

    import mcp_server.db as mcp_db  # noqa: PLC0415

    from mcp_server.tools.build_evidence_bundle import (  # noqa: PLC0415
        canonical_json,
        compute_bundle_hash,
    )

    con = _open(db)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM decisions WHERE decision_id=?", (cond_id,)).fetchone()
    b = con.execute("SELECT * FROM decisions WHERE decision_id=?", (blocked_id,)).fetchone()
    con.close()

    check(
        "⑳ D10·D81 저장 계약 — state='draft' · override=0 · override_reason/reviewed_by/signed_at NULL",
        r["state"] == "draft"
        and r["override"] == 0
        and r["override_reason"] is None
        and r["reviewed_by"] is None
        and r["signed_at"] is None
        and r["decision_type"] == "DISPOSAL"
        and r["asset_id"] == ASSET_CONDITIONAL
        and (r["reason"] or "").strip() != ""
        and b["verdict_at_signing"] == "BLOCKED",
        f"{cond_id}: state={r['state']} override={r['override']} "
        f"verdict_at_signing={r['verdict_at_signing']} reason={(r['reason'] or '')[:14]}…",
    )

    # ── D84 — 저장된 번들을 다시 파싱해 해시를 재산출한다. 서명 시 백엔드가 하는 그 대조다.
    #    직렬화 규약(sort_keys·separators·ensure_ascii)이 어긋나면 여기서 먼저 깨진다.
    stored = r["evidence_bundle"]
    parsed = json.loads(stored)
    check(
        "㉑ D84 저장된 evidence_bundle 재파싱 → bundle_hash 일치 · 정준 직렬화 바이트 동일",
        compute_bundle_hash(parsed) == r["bundle_hash"] and canonical_json(parsed) == stored,
        f"재산출={compute_bundle_hash(parsed)[:24]}… 저장={str(r['bundle_hash'])[:24]}… "
        f"· 재직렬화 동일={canonical_json(parsed) == stored}",
    )

    # ── D10 — TEMP TRIGGER 가 **실제로** ABORT 하는지 SQL 을 직접 날려 본다.
    #   ⛔ draft_writer 를 쓰지 않는다 (po_drafts 전용 트리거만 걸린 커넥션이라 안 잠긴다).
    #
    #   ★ UPDATE 문을 고를 때 주의 — `SET state='signed'` 로 시험하면 **트리거를 지워도
    #     통과한다.** MQ-707 이 넣은 CHECK("signed 인데 서명자·서명시각이 비면 거부")가
    #     대신 IntegrityError 를 내기 때문이다(뮤턴트로 실측). 그래서 스키마가 **허용하는**
    #     전이(draft→pending, 사람 API 가 실제로 하는 그 전이)로 시험하고, 예외 메시지에
    #     **트리거 문구**가 있는지까지 본다. 그러지 않으면 "잠갔다"가 아니라 "다른 것이
    #     우연히 막아 줬다"를 통과로 기록하게 된다.
    mcp_db.DB_PATH = db
    if dbcompat.USE_POSTGRES:
        # mcp_server/db.py 는 Postgres 전용이라 DB_PATH 를 더 안 본다 — draft_writer 류가
        # 실제로 읽는 DATABASE_URL 을 격리 스키마 DSN 으로 바꿔야 이 프로브가 공유 DB
        # 대신 이 테스트가 방금 쓴 격리 스키마를 상대로 UPDATE/DELETE 를 시도한다.
        mcp_db.DATABASE_URL = db[1]
    trigger_msg = "MCP 도구는 decisions 를"
    for mark, label, sql in (
        ("㉒", "UPDATE", "UPDATE decisions SET state='pending' WHERE decision_id=?"),
        ("㉓", "DELETE", "DELETE FROM decisions WHERE decision_id=?"),
    ):
        try:
            with mcp_db.decision_writer() as w:
                w.execute(sql, (cond_id,))
            aborted, detail = False, "ABORT 되지 않았다 (잠금 없음)"
        except sqlite3.IntegrityError as e:
            aborted, detail = trigger_msg in str(e), str(e)
        con = _open(db)
        con.row_factory = sqlite3.Row
        still = con.execute(
            "SELECT state FROM decisions WHERE decision_id=?", (cond_id,)
        ).fetchone()
        con.close()
        check(
            f"{mark} D10 decisions {label} 시도 → TEMP TRIGGER ABORT · 행 그대로",
            aborted and still is not None and still["state"] == "draft",
            f"{detail} · 행 상태={still['state'] if still else '삭제됨'}",
        )


def verify_repair_row(
    db: Path, repair_id: str | None, tool_expenditure_class: str | None
) -> None:
    """`repair_records` 저장분 검증 (MQ-913, D98) — 세 번째 쓰기 도구의 draft INSERT 계약."""
    if repair_id is None:
        for mark in ("㉗", "㉘", "㉙", "㉚"):
            check(f"{mark} repair_records 저장분 검증", False, "선행 draft 생성이 실패해 검증 불가")
        return

    import mcp_server.db as mcp_db  # noqa: PLC0415

    con = _open(db)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM repair_records WHERE repair_id=?", (repair_id,)).fetchone()
    con.close()

    check(
        "㉗ D10·D98 저장 계약 — state='draft' · 서명·신원 필드 전부 NULL",
        r["state"] == "draft"
        and r["performed_by"] is None
        and r["verified_by"] is None
        and r["signed_at"] is None
        and r["record_hash"] is None
        and r["requested_by"] is None
        and r["session_id"] is None
        and r["equipment_id"] == "INV-L3-01",
        f"{repair_id}: state={r['state']} equipment_id={r['equipment_id']}",
    )

    # ⓓ — 도구 응답의 expenditure_class 가 DB 저장값과 일치 (회계 판정이 조회와 저장 사이에
    #    갈리지 않는다는 증거. HOLD 도 정상 판정이므로 값 자체를 비교한다).
    check(
        "㉘ ⓓ expenditure_class — 도구 응답값이 repair_records 저장값과 일치",
        r["expenditure_class"] == tool_expenditure_class,
        f"응답={tool_expenditure_class} · DB={r['expenditure_class']}",
    )

    # ⓐ — D10 TEMP TRIGGER 가 **실제로** ABORT 하는지 SQL 을 직접 날려 본다.
    #   ⛔ po_drafts·decisions 전용 커넥션(다른 두 writer)으로 확인하지 않는다 — 그건
    #     repair_records 트리거가 걸려 있지 않은 커넥션이라, 잠기지 않은 경로를 통과시키고도
    #     "막혔다"고 오판하게 된다. repair_records 전용 커넥션(세 번째 writer)만 쓴다.
    mcp_db.DB_PATH = db
    if dbcompat.USE_POSTGRES:
        # mcp_server/db.py 는 Postgres 전용이라 DB_PATH 를 더 안 본다 — draft_writer 류가
        # 실제로 읽는 DATABASE_URL 을 격리 스키마 DSN 으로 바꿔야 이 프로브가 공유 DB
        # 대신 이 테스트가 방금 쓴 격리 스키마를 상대로 UPDATE/DELETE 를 시도한다.
        mcp_db.DATABASE_URL = db[1]
    trigger_msg = "MCP 도구는 repair_records 를"
    for mark, label, sql in (
        ("㉙", "UPDATE", "UPDATE repair_records SET state='pending' WHERE repair_id=?"),
        ("㉚", "DELETE", "DELETE FROM repair_records WHERE repair_id=?"),
    ):
        try:
            with mcp_db.repair_writer() as w:
                w.execute(sql, (repair_id,))
            aborted, detail = False, "ABORT 되지 않았다 (잠금 없음)"
        except sqlite3.IntegrityError as e:
            aborted, detail = trigger_msg in str(e), str(e)
        con = _open(db)
        con.row_factory = sqlite3.Row
        still = con.execute(
            "SELECT state FROM repair_records WHERE repair_id=?", (repair_id,)
        ).fetchone()
        con.close()
        check(
            f"{mark} ⓐ D10 repair_records {label} 시도 → TEMP TRIGGER ABORT · 행 그대로",
            aborted and still is not None and still["state"] == "draft",
            f"{detail} · 행 상태={still['state'] if still else '삭제됨'}",
        )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print(
        "쓰기 도구 3종 계약 검증 — create_po_draft · generate_disposal_document · "
        "create_repair_record (임시 DB 사본)\n"
    )
    if not dbcompat.USE_POSTGRES and not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    db_schema = None
    try:
        with tempfile.TemporaryDirectory() as td:
            db = prepare_db(Path(td))
            if dbcompat.USE_POSTGRES:
                db_schema = db[0]
            print(f"[스키마] {DDL_NOTE}\n")
            po_id, cond_id, blocked_id, repair_id, repair_expenditure_class = asyncio.run(run(db))
            verify_row(db, po_id)
            verify_decision_rows(db, cond_id, blocked_id)
            verify_repair_row(db, repair_id, repair_expenditure_class)
    finally:
        if db_schema:
            pg_isolation.drop_isolated_schema(db_schema)

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 44))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 44))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — 쓰기 도구 3종이 "
        "D10·D23·D31·D33·D34·D37·D63·D80·D81·D84·D98 경계를 지킨다"
    )


if __name__ == "__main__":
    main()
