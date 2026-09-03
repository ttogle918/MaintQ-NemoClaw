# -*- coding: utf-8 -*-
"""수리 증빙 흐름 회귀 (MQ-913, S29 (구 S19) — `create_repair_record` §16 · MQ-908 5경로 · MQ-909 REST 왕복).

## 이 스위트가 보는 것

1. `create_repair_record` MCP 도구를 **직접 호출**해서 draft 가 실제로 만들어지는 것과,
   `db.repair_writer()` 가 만드는 행이 **오직 `state='draft'`** 뿐이며 서명·신원 필드가
   전부 NULL 인 것을 증명한다 (draft INSERT 만, D10·D98).
2. **MQ-908 의 5경로**(`GET /metrics`·`POST /repair-value`·`GET /criticality`·
   `POST /expenditure/classify`·`GET /evidence-bundle`)를 **`core` 프로파일**(기본값,
   `MAINTQ_TOOLS_PROFILE` 미설정)에서 실제로 호출해 200 을 확인한다(D73 증명).
3. **`POST/GET /api/repairs/*` REST 왕복**(MQ-909, Stage 5) — draft → submit(403 양방향)
   → sign(`self_sign` 409) → 해시 재계산 대조 → `signed` 재서명 409 → `reject` 사유 필수 →
   서명 후 `n_repairs_signed` +1. 명세 원문(`docs/sprints/sprint-9.md` MQ-913)이 요구한
   그대로다 — 이전 초안은 "MQ-909가 이월됐다"고 잘못 적고 이 축을 스킵했으나, 그 전제
   자체가 거짓이었다(§9-5 이월 목록에 MQ-909는 없다·§7이 오히려 보호 대상으로 못박음).
   MQ-909가 Stage 5에서 실제로 구현된 뒤 이 축을 채워 넣었다.

⛔ `po_drafts`·`decisions` 전용 쓰기 커넥션은 쓰지 않는다 — `repair_records` 전용 커넥션
  (`mcp_server/db.py` 의 세 번째 writer, D98)만 쓴다. 다른 두 테이블 전용 writer 함수명이
  이 파일에 한 글자도 나오지 않아야 한다(DoD — 두 함수명을 합친 정규식으로 grep).

실 DB 는 건드리지 않는다 — 임시 사본 + `MAINTQ_DB` 주입(기존 스파이크 규약 그대로).

실행:  uv run python spikes/repair_flow_contract.py
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = ROOT / "data" / "maintq.db"
sys.path.insert(0, str(ROOT))
from data import dbcompat, pg_isolation  # noqa: E402


def _open(db):
    """`db` 는 SQLite 사본 Path 이거나 Postgres 격리 스키마 DSN 문자열이다."""
    if dbcompat.USE_POSTGRES:
        return dbcompat.connect_dsn(db)
    return sqlite3.connect(db)


# 백엔드 기동 시 MCP 서브프로세스를 띄우지 않는다 — 이 스위트는 REST 5경로만 보고
# (D73 이 증명하려는 바가 바로 "MCP 없이도 200") `create_repair_record` 는 함수로 직접 부른다.
os.environ["MAINTQ_MCP_AUTOSTART"] = "0"

# D73 의 핵심 — 확장 도구가 등록조차 안 되는 core 프로파일에서 5경로가 살아 있어야 한다.
# 명시적으로 지운다: 개발 셸에 MAINTQ_TOOLS_PROFILE=full 이 남아 있으면 "core 에서 통과"라는
# 이 스위트의 주장 자체가 거짓 전제 위에 서게 된다.
os.environ.pop("MAINTQ_TOOLS_PROFILE", None)

EQUIPMENT_ID = "INV-L3-01"   # iG5A, AST-L3-CONV 호스트
PART_NO = "FAN-IG5-01"       # CRITICAL, iG5A 호환
ASSET_ID = "AST-L3-CONV"
DISPOSAL_DATE = "2026-09-01"

MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    mark = MARKS[len(results)] if len(results) < len(MARKS) else f"[{len(results) + 1}]"
    results.append((f"{mark} {name}", ok, detail))


def repair_count(db: Path) -> int:
    con = _open(db)
    try:
        return int(con.execute("SELECT count(*) FROM repair_records").fetchone()[0])
    finally:
        con.close()


def run_tool_axis(db: Path) -> str:
    """`create_repair_record` 직접 호출 — draft INSERT 만 · `repair_writer()` 잠금 확인."""
    import mcp_server.db as mcp_db  # noqa: PLC0415

    saved = mcp_db.DB_PATH
    mcp_db.DB_PATH = db
    try:
        from mcp_server.tools.create_repair_record import create_repair_record  # noqa: PLC0415

        before = repair_count(db)
        res = create_repair_record(
            equipment_id=EQUIPMENT_ID,
            work_type="UNPLANNED",
            repair_scope="RESTORE",
            cost=850000,
            parts=[{"part_no": PART_NO, "serial": "SN-SPIKE-01", "qty": 1}],
            downtime_hours=6.5,
            model="iG5A",
            error_code="OHT",
            note="스파이크 회귀 — 냉각팬 교체",
        )
        after = repair_count(db)
        check(
            "create_repair_record 정상 호출 → status=ok · state=draft · expenditure_class 산출",
            res.get("status") == "ok"
            and res.get("state") == "draft"
            and res.get("expenditure_class") in ("CAPITAL", "REVENUE", "HOLD")
            and res.get("record_hash") is None,
            f"status={res.get('status')} state={res.get('state')} "
            f"expenditure_class={res.get('expenditure_class')} repair_id={res.get('repair_id')}",
        )
        check(
            "repair_records 행 수 +1 (INSERT 만, 기존 12행 안 건드림)",
            after == before + 1,
            f"{before}건 → {after}건",
        )

        repair_id = res.get("repair_id")
        con = _open(db)
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT * FROM repair_records WHERE repair_id=?", (repair_id,)
        ).fetchone()
        con.close()
        fields = (
            "state", "performed_by", "verified_by", "signed_at", "record_hash",
            "requested_by", "session_id",
        )
        row_detail = {f: row[f] for f in fields} if row is not None else None
        check(
            "DB 행 실측 — state='draft' · 서명·신원 필드 전부 NULL (repair_writer() 는 draft 만 만든다)",
            row is not None
            and row["state"] == "draft"
            and row["performed_by"] is None
            and row["verified_by"] is None
            and row["signed_at"] is None
            and row["record_hash"] is None
            and row["requested_by"] is None
            and row["session_id"] is None,
            f"row={row_detail}",
        )
        check(
            "expenditure_class — 도구 응답값이 DB 저장값과 일치 (D101)",
            row is not None and row["expenditure_class"] == res.get("expenditure_class"),
            f"응답={res.get('expenditure_class')} · DB={row['expenditure_class'] if row else None}",
        )

        # ── 채번 규약 — 두 번째 호출은 순번이 이어진다 (RPR-%04d, 동시성 방어 없음이 정상, P19)
        res2 = create_repair_record(
            equipment_id=EQUIPMENT_ID,
            work_type="PLANNED",
            repair_scope="RESTORE",
            cost=100000,
            parts=[{"part_no": PART_NO}],
        )
        n1 = int(repair_id.split("-")[1]) if repair_id else None
        n2 = int(res2["repair_id"].split("-")[1]) if res2.get("repair_id") else None
        check(
            "채번 — 두 번째 호출이 RPR-%04d 순번을 이어간다",
            n1 is not None and n2 == n1 + 1,
            f"{repair_id} → {res2.get('repair_id')}",
        )

        # ── 미존재 부품 → unknown_part, 행 수는 그대로 (아무것도 쓰지 않았음을 직접 센다)
        before_bad = repair_count(db)
        bad = create_repair_record(
            equipment_id=EQUIPMENT_ID,
            work_type="UNPLANNED",
            repair_scope="RESTORE",
            cost=10000,
            parts=[{"part_no": "NOT-A-REAL-PART"}],
        )
        after_bad = repair_count(db)
        check(
            "미존재 부품 → not_found/unknown_part · 행 수 불변 (아무것도 안 씀을 직접 센다)",
            bad.get("status") == "not_found"
            and bad.get("reason") == "unknown_part"
            and after_bad == before_bad,
            f"status={bad.get('status')} reason={bad.get('reason')} "
            f"missing={bad.get('missing')} · {before_bad}건 → {after_bad}건",
        )

        return repair_id
    finally:
        mcp_db.DB_PATH = saved


def run_rest_axis(db: Path) -> None:
    """MQ-908 5경로 — `core` 프로파일(기본값)에서 실제로 200 을 확인 (D73)."""
    if dbcompat.USE_POSTGRES:
        import backend.db as backend_db  # noqa: PLC0415
        backend_db.DB_PATH = db
    else:
        os.environ["MAINTQ_DB"] = str(db)

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from backend.main import app  # noqa: PLC0415

    headers = {"X-Role": "technician", "X-User": "tech-01"}
    with TestClient(app) as client:
        r_metrics = client.get(
            f"/api/assets/{ASSET_ID}/metrics", params={"window_months": 12}, headers=headers
        )
        r_repair_value = client.post(
            f"/api/equipment/{EQUIPMENT_ID}/repair-value",
            json={"failed_part": PART_NO, "repair_cost": 500000},
            headers=headers,
        )
        r_criticality = client.get(f"/api/parts/{PART_NO}/criticality", headers=headers)
        r_expenditure = client.post(
            "/api/expenditure/classify",
            json={"part_no": PART_NO, "repair_scope": "RESTORE", "amount": 500000},
            headers=headers,
        )
        r_bundle = client.get(
            f"/api/assets/{ASSET_ID}/evidence-bundle",
            params={"disposal_mode": "SALE", "disposal_date": DISPOSAL_DATE},
            headers=headers,
        )

    codes = {
        "GET /assets/{id}/metrics": r_metrics.status_code,
        "POST /equipment/{id}/repair-value": r_repair_value.status_code,
        "GET /parts/{no}/criticality": r_criticality.status_code,
        "POST /expenditure/classify": r_expenditure.status_code,
        "GET /assets/{id}/evidence-bundle": r_bundle.status_code,
    }
    check(
        "MQ-908 5경로 전부 200 — core 프로파일(MAINTQ_TOOLS_PROFILE 미설정)에서도 살아 있다 (D73)",
        all(v == 200 for v in codes.values())
        and os.environ.get("MAINTQ_TOOLS_PROFILE") is None,
        f"tools_profile env={os.environ.get('MAINTQ_TOOLS_PROFILE')!r} · " + " · ".join(
            f"{k}={v}" for k, v in codes.items()
        ),
    )
    check(
        "metrics 응답에 n_repairs_signed·n_repairs_unsigned 존재 (서명분만 반영, 12 §11)",
        r_metrics.status_code == 200
        and "n_repairs_signed" in r_metrics.json()
        and "n_repairs_unsigned" in r_metrics.json(),
        f"n_repairs_signed={r_metrics.json().get('n_repairs_signed')} "
        f"n_repairs_unsigned={r_metrics.json().get('n_repairs_unsigned')}",
    )
    check(
        "expenditure/classify 응답 verdict 3종 중 하나 (CAPITAL|REVENUE|HOLD)",
        r_expenditure.status_code == 200
        and r_expenditure.json().get("verdict") in ("CAPITAL", "REVENUE", "HOLD"),
        f"verdict={r_expenditure.json().get('verdict')}",
    )


def run_repair_flow_rest_axis(db: Path) -> None:
    """`/api/repairs/*` REST 왕복 (MQ-909) — draft→submit→sign, self_sign 409, 재서명 409,
    reject 사유 필수, 서명 후 `n_repairs_signed` +1."""
    if dbcompat.USE_POSTGRES:
        import backend.db as backend_db  # noqa: PLC0415
        backend_db.DB_PATH = db
    else:
        os.environ["MAINTQ_DB"] = str(db)

    import mcp_server.db as mcp_db  # noqa: PLC0415

    saved = mcp_db.DB_PATH
    mcp_db.DB_PATH = db
    try:
        from mcp_server.tools.create_repair_record import create_repair_record  # noqa: PLC0415

        draft_a = create_repair_record(
            equipment_id=EQUIPMENT_ID,
            work_type="UNPLANNED",
            repair_scope="RESTORE",
            cost=300000,
            parts=[{"part_no": PART_NO}],
            note="repair_flow_contract REST 왕복 — 서명 경로",
        )
        draft_b = create_repair_record(
            equipment_id=EQUIPMENT_ID,
            work_type="UNPLANNED",
            repair_scope="RESTORE",
            cost=150000,
            parts=[{"part_no": PART_NO}],
            note="repair_flow_contract REST 왕복 — 반려 경로",
        )
    finally:
        mcp_db.DB_PATH = saved

    repair_id_a = draft_a["repair_id"]
    repair_id_b = draft_b["repair_id"]

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from backend.main import app  # noqa: PLC0415

    tech = {"X-Role": "technician", "X-User": "tech-01"}
    mgr = {"X-Role": "manager", "X-User": "mgr-01"}
    self_signer = {"X-Role": "manager", "X-User": "tech-01"}  # 제출자 본인이 팀장 역할로 서명 시도

    with TestClient(app) as client:
        n_signed_before = client.get(
            f"/api/assets/{ASSET_ID}/metrics", params={"window_months": 12}, headers=tech
        ).json().get("n_repairs_signed")

        r_mgr_submit = client.post(f"/api/repairs/{repair_id_a}/submit", headers=mgr)
        check(
            "팀장이 submit → 403",
            r_mgr_submit.status_code == 403,
            f"status={r_mgr_submit.status_code}",
        )

        r_submit = client.post(f"/api/repairs/{repair_id_a}/submit", headers=tech)
        check(
            "정비사가 submit → 200, state=pending",
            r_submit.status_code == 200 and r_submit.json().get("state") == "pending",
            f"status={r_submit.status_code} state={r_submit.json().get('state')}",
        )

        r_tech_sign = client.post(f"/api/repairs/{repair_id_a}/sign", headers=tech)
        check(
            "정비사가 sign → 403",
            r_tech_sign.status_code == 403,
            f"status={r_tech_sign.status_code}",
        )

        r_self = client.post(f"/api/repairs/{repair_id_a}/sign", headers=self_signer)
        check(
            "본인 제출건 본인 서명(self_sign) → 409",
            r_self.status_code == 409 and r_self.json().get("reason") == "self_sign",
            f"status={r_self.status_code} reason={r_self.json().get('reason')}",
        )

        r_sign = client.post(f"/api/repairs/{repair_id_a}/sign", headers=mgr)
        signed_body = r_sign.json()
        r_get = client.get(f"/api/repairs/{repair_id_a}", headers=mgr)
        check(
            "팀장이 sign → 200, state=signed, record_hash=sha256:*, hash_verified=true",
            r_sign.status_code == 200
            and signed_body.get("state") == "signed"
            and str(signed_body.get("record_hash", "")).startswith("sha256:")
            and r_get.status_code == 200
            and r_get.json().get("hash_verified") is True,
            f"status={r_sign.status_code} state={signed_body.get('state')} "
            f"hash={signed_body.get('record_hash')} hash_verified={r_get.json().get('hash_verified')}",
        )

        r_resign = client.post(f"/api/repairs/{repair_id_a}/sign", headers=mgr)
        check(
            "signed 재서명 → 409 invalid_transition",
            r_resign.status_code == 409 and r_resign.json().get("reason") == "invalid_transition",
            f"status={r_resign.status_code} reason={r_resign.json().get('reason')}",
        )

        client.post(f"/api/repairs/{repair_id_b}/submit", headers=tech)
        r_reject_no_reason = client.post(
            f"/api/repairs/{repair_id_b}/reject", headers=mgr, json={"reason": ""}
        )
        check(
            "reject 사유 공백 → 422",
            r_reject_no_reason.status_code == 422,
            f"status={r_reject_no_reason.status_code}",
        )

        r_reject = client.post(
            f"/api/repairs/{repair_id_b}/reject", headers=mgr, json={"reason": "예산 초과"}
        )
        check(
            "reject 사유 있음 → 200, state=rejected",
            r_reject.status_code == 200 and r_reject.json().get("state") == "rejected",
            f"status={r_reject.status_code} state={r_reject.json().get('state')}",
        )

        n_signed_after = client.get(
            f"/api/assets/{ASSET_ID}/metrics", params={"window_months": 12}, headers=tech
        ).json().get("n_repairs_signed")
        check(
            "서명 후 get_maintenance_metrics 의 n_repairs_signed +1 (12 §11)",
            isinstance(n_signed_before, int)
            and isinstance(n_signed_after, int)
            and n_signed_after == n_signed_before + 1,
            f"{n_signed_before} → {n_signed_after}",
        )



def run_screen_create_axis(db: Path) -> None:
    """P39 — 화면이 수리 증빙 초안을 **직접 생성·수정**한다 (`POST/PATCH /api/repairs`).

    D111(발주서)이 연 경로를 수리 증빙에 확장한 것이다. 채팅(MCP 도구)을 거치지 않고
    화면이 직접 만든다 — ⛔ 이건 D10 대상이 아니다: MCP 도구가 아니라 **백엔드 쓰기**라
    처음부터 UPDATE 권한이 있다(D111 이 정리한 경계).

    `expenditure_class` 가 D31 의 `unit_price` 와 같은 자리다 — **입력에 없으므로**
    사용자가 못 건드리고, 입력이 바뀌면 서버가 재산출한다.
    """
    if dbcompat.USE_POSTGRES:
        import backend.db as backend_db  # noqa: PLC0415
        backend_db.DB_PATH = db
    else:
        os.environ["MAINTQ_DB"] = str(db)

    from fastapi.testclient import TestClient  # noqa: PLC0415

    from backend.main import app  # noqa: PLC0415

    tech = {"X-Role": "technician", "X-User": "tech-01"}
    mgr = {"X-Role": "manager", "X-User": "mgr-01"}
    body = {
        "equipment_id": EQUIPMENT_ID,
        "work_type": "UNPLANNED",
        "repair_scope": "RESTORE",
        "cost": 250000,
        "parts": [{"part_no": PART_NO, "qty": 1}],
        "note": "화면 직접 생성 (P39)",
    }

    with TestClient(app) as client:
        r_create = client.post("/api/repairs", json=body, headers=tech)
        created = r_create.json() if r_create.status_code == 200 else {}
        check(
            "㉠ 정비사 화면 직접 생성 → 200 · draft · performed_by 즉시 stamp (D37)",
            r_create.status_code == 200
            and created.get("state") == "draft"
            and created.get("performed_by") == "tech-01",
            f"{r_create.status_code} · state={created.get('state')} · "
            f"performed_by={created.get('performed_by')}",
        )

        check(
            "㉡ expenditure_class 는 서버 산출 — 입력에 없고 응답에 실린다 (D101·D31 자리)",
            "expenditure_class" not in body and created.get("expenditure_class") is not None,
            f"입력에 없음={'expenditure_class' not in body} · "
            f"응답={created.get('expenditure_class')}",
        )

        r_mgr = client.post("/api/repairs", json=body, headers=mgr)
        check(
            "㉢ 팀장이 화면 생성 호출 → 403 (역할 분리)",
            r_mgr.status_code == 403,
            f"{r_mgr.status_code}",
        )

        rid = created.get("repair_id", "RPR-NONE")
        r_patch = client.patch(
            f"/api/repairs/{rid}", json={**body, "cost": 410000, "note": "수량 정정"}, headers=tech
        )
        patched = r_patch.json() if r_patch.status_code == 200 else {}
        check(
            "㉣ draft 수정 → 200 · cost 반영 · expenditure_class 재산출",
            r_patch.status_code == 200 and patched.get("cost") == 410000,
            f"{r_patch.status_code} · cost={patched.get('cost')} · "
            f"expenditure_class={patched.get('expenditure_class')}",
        )

        r_patch_mgr = client.patch(f"/api/repairs/{rid}", json=body, headers=mgr)
        check(
            "㉤ 팀장이 PATCH 호출 → 403",
            r_patch_mgr.status_code == 403,
            f"{r_patch_mgr.status_code}",
        )

        r_bad_part = client.post(
            "/api/repairs", json={**body, "parts": [{"part_no": "NOPE-999"}]}, headers=tech
        )
        check(
            "㉥ 등록되지 않은 부품 → 404 (지어낸 품번이 이력에 남지 않는다)",
            r_bad_part.status_code == 404,
            f"{r_bad_part.status_code}",
        )

        r_bad_scope = client.post(
            "/api/repairs", json={**body, "repair_scope": "NOPE"}, headers=tech
        )
        check(
            "㉦ repair_scope enum 밖 → 422 (폴백 금지)",
            r_bad_scope.status_code == 422,
            f"{r_bad_scope.status_code}",
        )

        client.post(f"/api/repairs/{rid}/submit", headers=tech)
        r_after = client.patch(f"/api/repairs/{rid}", json=body, headers=tech)
        check(
            "㉧ 제출 후 PATCH → 409 (draft 아님)",
            r_after.status_code == 409,
            f"{r_after.status_code}",
        )

        r_404 = client.patch("/api/repairs/RPR-9999", json=body, headers=tech)
        check("㉨ 없는 수리 증빙 PATCH → 404", r_404.status_code == 404, f"{r_404.status_code}")


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print(
        "수리 증빙 흐름 (MQ-913) — create_repair_record 직접 검증 + MQ-908 5경로(core) "
        "+ MQ-909 REST 왕복(submit→sign→reject)\n"
    )
    if not dbcompat.USE_POSTGRES and not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    if dbcompat.USE_POSTGRES:
        before = dbcompat.connect_dsn(pg_isolation.BASE_DATABASE_URL).execute(
            "SELECT count(*) FROM repair_records"
        ).fetchone()[0]
    else:
        before = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)

    schema = None
    with tempfile.TemporaryDirectory() as td:
        if dbcompat.USE_POSTGRES:
            schema, db = pg_isolation.create_isolated_schema("repair_flow")
        else:
            db = Path(td) / "repair_flow.db"
            shutil.copy2(SOURCE_DB, db)
            for side in ("-wal", "-shm"):
                src = SOURCE_DB.with_name(SOURCE_DB.name + side)
                if src.exists():
                    shutil.copy2(src, db.with_name(db.name + side))

        try:
            run_tool_axis(db)
            run_rest_axis(db)
            run_repair_flow_rest_axis(db)
            run_screen_create_axis(db)
        finally:
            if schema:
                pg_isolation.drop_isolated_schema(schema)

    if dbcompat.USE_POSTGRES:
        after = dbcompat.connect_dsn(pg_isolation.BASE_DATABASE_URL).execute(
            "SELECT count(*) FROM repair_records"
        ).fetchone()[0]
        check(
            "실 DB(공유 Postgres) repair_records 행 수 불변 (사본만 썼다는 증거)",
            before == after,
            f"{before} → {after}",
        )
    else:
        after = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)
        check(
            "실 DB mtime·size 불변 (사본만 썼다는 증거)",
            before == after,
            f"{'불변' if before == after else f'{before} → {after}'}",
        )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 44))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 44))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — create_repair_record 는 draft INSERT 만 하고(D10·D98), "
        "MQ-908 5경로는 core 프로파일에서도 200 이며(D73), MQ-909 REST 왕복이 "
        "403/409/422 경계를 실제로 지킨다"
    )


if __name__ == "__main__":
    main()
