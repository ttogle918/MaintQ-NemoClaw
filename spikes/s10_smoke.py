# -*- coding: utf-8 -*-
"""MQ-708 — S9 → S10 관통 스모크 (**실 uvicorn 서버 · 실 MCP stdio 서버**).

`spikes/s4_smoke.py` 의 격리 패턴 + `spikes/sp3_sse_events.py` 의 실서버 기동 패턴을 합쳤다.
in-process TestClient 가 아니라 **프로세스 2개**(uvicorn · MCP stdio)를 실제로 띄운다 —
`disposal_sign_contract.py` 가 계약을 전수로 잠갔다면, 여기서는 그 계약이 **배선된 채로
돌아가는지**를 본다. 둘은 서로를 대신하지 못한다: in-process 는 프로파일·env 상속·라우터
등록 같은 *배선* 사고를 못 잡고, 스모크는 전수를 못 센다.

────────────────────────────────────────────────────────────────────────────────
★ 관통 경로 (sprint-7 MQ-708 §핵심 로직)
────────────────────────────────────────────────────────────────────────────────
    POST /api/assets/{id}/disposal/precheck   → 200|409 + verdict        (S9)
    MCP  generate_disposal_document           → decision_id, state=draft (D10)
    POST /api/decisions/{id}/submit   (tech)  → 200, state=pending
    GET  /api/approvals?state=pending         → kind=disposal 로 보인다   (D85)
    GET  /api/decisions/{id}                  → 문서 3종 + missing_sections(D86)
    POST /api/decisions/{id}/sign     (mgr)   → 200 | 409 override_required
    검증: state='signed' · bundle_hash 불변 · signed_at·reviewed_by non-null

**두 경로를 다 완주시킨다** — 비차단(CLEAR/CONDITIONAL)과 차단(BLOCKED). 한쪽만 돌리면
"전부 통과시키는 배선"이나 "전부 막는 배선"이 그대로 초록으로 보인다.

────────────────────────────────────────────────────────────────────────────────
★ 격리와 정직성 (Stage 1~3 에서 실제로 겪은 것들)
────────────────────────────────────────────────────────────────────────────────
  · 임시 DB 사본 + `MAINTQ_DB`. 자식 프로세스에는 **`env={**os.environ, ...}` 로 명시 상속**
    한다 — `env=None` 이면 MCP SDK 의 화이트리스트가 `MAINTQ_DB` 를 잘라내 자식이 조용히
    **실 DB 를 연다** (sp2 가 실제로 그랬다). uvicorn 자식도 같은 이유로 env 를 명시한다.
  · `MAINTQ_TOOLS_PROFILE=full` 로 띄운다. 안 켜졌으면 도구 부재를 **FAIL 로 보고**한다 —
    스킵하지 않는다. 스킵은 "확인하지 않았다"를 초록으로 칠하는 일이다.
  · 서버 기동 실패도 **명시적 FAIL**.
  · 마지막 게이트는 사본이 아니라 실 `data/maintq.db` 를 본다 — mtime·size·`decisions`
    행 수 불변이 **계수되는 검사**로 남는다 (비계수 게이트는 러너 출력에 안 보인다).
  · 임시 폴더 정리 실패는 경고로 끝난다 (`ignore_cleanup_errors=True`) — Windows 는 자식
    핸들 해제가 비동기라, 정리 실패가 예외로 터지면 끝난 검증 결과를 가린다.

실행:  uv run python spikes/s10_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DB = ROOT / "data" / "maintq.db"
sys.path.insert(0, str(ROOT))

PORT = 8087
BASE = f"http://127.0.0.1:{PORT}"

TECH = {"X-Role": "technician", "X-User": "tech-01"}
MGR = {"X-Role": "manager", "X-User": "mgr-01"}

# 처분일 고정 — 오늘 날짜를 쓰면 세액공제 잔존기간이 매일 달라져 verdict 가 흔들린다
PROBE_DATE = "2026-09-01"

# 비차단 경로 / 차단 경로. `disposal_sign_contract` 의 전수 매트릭스가 이 판정을 확인한다.
CLEAR_ASSET, CLEAR_MODE = "AST-L3-LIFT", "SCRAP"      # → CLEAR
BLOCKED_ASSET, BLOCKED_MODE = "AST-L3-CONV", "SALE"   # → BLOCKED (담보권 미해소)

# 도구 총수 = 코어 7 + 확장 9 (D69·D98). `full` 이 안 켜지면 7 이 나온다.
EXPECTED_TOOLS_FULL = 16
OVERRIDE_REASON = "법무 검토 완료 — 담보권자 동의 별건 확보 (스모크 기록)"

MARKS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    mark = MARKS[len(results)] if len(results) < len(MARKS) else f"[{len(results) + 1}]"
    results.append((f"{mark} {name}", ok, detail))


def db_rows(db: Path, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    """행 조회. **실 DB(`SOURCE_DB`)는 반드시 읽기 전용 URI 로 연다.**

    쓰기 가능 커넥션을 열었다 닫으면 SQLite 가 WAL 체크포인트를 수행해 **본 파일의 mtime·size 가
    바뀐다** — 이 스위트의 마지막 검사가 바로 그 불변을 단언하므로, 자기 행위로 자기 게이트를
    깨뜨리는 플래키 레드가 된다(reviewer 경고 1). 임시 사본은 쓰기 가능해도 무해하다.
    """
    uri = db.resolve() == SOURCE_DB.resolve()
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) if uri else sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


async def wait_ready(timeout: float = 40.0) -> bool:
    """서버 준비 대기.

    **짧은 타임아웃으로 빠르게 폴링하지 않는다** (sp3 의 실측 교훈): uvicorn 은 lifespan
    startup 이 끝나기 전에 이미 소켓을 바인딩하므로, 그 창에 연결을 만들었다 끊으면
    Windows Proactor 의 accept 루프가 `OSError [WinError 64]` 로 깨진다. 여기 lifespan 은
    MCP stdio 자식까지 스폰하므로 창이 더 길다 — 요청은 적게, 타임아웃은 넉넉히.
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            async with httpx.AsyncClient(timeout=timeout / 3) as c:
                if (await c.get(f"{BASE}/health")).status_code == 200:
                    return True
        except Exception:  # noqa: BLE001 — 바인딩 전이면 연결 자체가 거부된다
            await asyncio.sleep(min(1.0 * attempt, 3.0))
    return False


# ── 관통 ────────────────────────────────────────────────────────────────────────
async def run_all(db: Path) -> None:
    from backend.agent.mcp_client import McpClient  # noqa: PLC0415

    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as c:
        health = (await c.get("/health")).json()
        # ① 실 서버가 떴고 MCP 세션까지 준비됐다
        check(
            "실 uvicorn 서버 기동 · /health 200 · MCP 세션 ready",
            health.get("status") == "ok" and health.get("mcp") is True,
            f"health={health}",
        )
        # ② `full` 프로파일 — 안 켜졌으면 **FAIL**. 스킵하지 않는다 (D69)
        check(
            "서버 MCP 가 full 프로파일로 떴다 — 확장 9종 포함 16종 (D69·D98)",
            health.get("tools") == EXPECTED_TOOLS_FULL and health.get("tools_profile") == "full",
            f"tools={health.get('tools')} (기대 {EXPECTED_TOOLS_FULL}) · "
            f"tools_profile={health.get('tools_profile')!r}",
        )

        # ③ 스모크 자신의 MCP stdio 세션 — env 명시 상속(D42)으로 **임시 DB** 를 보게 한다
        client = McpClient(
            env={"MAINTQ_DB": str(db), "MAINTQ_TOOLS_PROFILE": "full", "MAINTQ_MCP_AUTOSTART": "1"}
        )
        started = await client.start()
        tools = {t["name"] for t in await client.list_tools()}
        check(
            "실 MCP stdio 서버 기동 · generate_disposal_document·check_disposal_blockers 등록",
            started and {"generate_disposal_document", "check_disposal_blockers"} <= tools,
            f"start={started}({client.start_error or '-'}) · 도구 {len(tools)}종 · "
            f"처분 도구 존재={'generate_disposal_document' in tools}",
        )
        if not started:
            return

        try:
            await _clear_path(c, client, db)
            await _blocked_path(c, client, db)
        finally:
            await client.stop()


async def _precheck(c: httpx.AsyncClient, asset: str, mode: str) -> httpx.Response:
    return await c.post(
        f"/api/assets/{asset}/disposal/precheck",
        json={"disposal_mode": mode, "disposal_date": PROBE_DATE},
        headers=TECH,
    )


async def _make_draft(client, asset: str, mode: str, reason: str) -> dict:
    return await client.call(
        "generate_disposal_document",
        {
            "reason": reason,
            "asset_id": asset,
            "disposal_mode": mode,
            "disposal_date": PROBE_DATE,
        },
    )


async def _clear_path(c: httpx.AsyncClient, client, db: Path) -> None:
    """비차단 경로 — precheck 200 → draft → submit → 큐 → 상세 → 서명 200."""
    pre = await _precheck(c, CLEAR_ASSET, CLEAR_MODE)
    body = pre.json()
    # ④ S9 — 비차단 판정은 200 (D71)
    check(
        f"[비차단] precheck {CLEAR_ASSET}/{CLEAR_MODE} → 200 · verdict CLEAR|CONDITIONAL (D71)",
        pre.status_code == 200 and body.get("verdict") in ("CLEAR", "CONDITIONAL"),
        f"{pre.status_code} verdict={body.get('verdict')} · "
        f"선결 {len(body.get('preconditions') or [])}건",
    )

    doc = await _make_draft(client, CLEAR_ASSET, CLEAR_MODE, "노후 설비 폐기 (S10 스모크)")
    did = doc.get("decision_id")
    # ⑤ MCP 쓰기 도구는 draft 만 만든다 (D10·D81)
    check(
        "[비차단] MCP generate_disposal_document → status ok · state=draft · override=false",
        doc.get("status") == "ok" and doc.get("state") == "draft" and doc.get("override") is False,
        f"status={doc.get('status')}/{doc.get('reason', '-')} decision_id={did} "
        f"state={doc.get('state')} override={doc.get('override')}",
    )
    if not did:
        check("[비차단] 이후 관통 (draft 없음)", False, "decision_id 가 없어 경로를 이어갈 수 없다")
        return
    hash_at_draft = doc.get("bundle_hash")

    sub = await c.post(f"/api/decisions/{did}/submit", headers=TECH)
    sub_body = sub.json()
    # ⑥ 정비사 제출 — 신원 stamp 는 백엔드가 한다 (D23·D37)
    check(
        "[비차단] submit(technician) → 200 · state=pending · requested_by stamp",
        sub.status_code == 200
        and sub_body.get("state") == "pending"
        and sub_body.get("requested_by") == "tech-01",
        f"{sub.status_code} state={sub_body.get('state')} "
        f"requested_by={sub_body.get('requested_by')}",
    )

    q = (await c.get("/api/approvals", params={"state": "pending"}, headers=MGR)).json()
    mine = next((i for i in q.get("items", []) if i.get("id") == did), None)
    detail_code = (
        (await c.get(mine["detail_path"], headers=MGR)).status_code if mine else None
    )
    # ⑦ 통합 승인 큐에 처분서로 보인다 (D85)
    check(
        "[비차단] /api/approvals?state=pending 에 kind=disposal 로 보이고 detail_path 가 200",
        mine is not None and mine.get("kind") == "disposal" and detail_code == 200,
        f"큐 {len(q.get('items', []))}건 · 내 건={'있음' if mine else '없음'} "
        f"kind={mine.get('kind') if mine else '-'} · detail={detail_code}",
    )

    d = (await c.get(f"/api/decisions/{did}", headers=TECH)).json()
    docs = d.get("documents") or {}
    # ⑧ D86 — 문서는 저장하지 않고 조립 시점 렌더 + 없는 절은 없다고 말한다
    check(
        "[비차단] GET /api/decisions/{id} — 문서 3종 · missing_sections · hash_fixed:false (D86)",
        {"approval", "representation_warranty", "evidence_package"} <= set(docs)
        and docs.get("hash_fixed") is False
        and bool(docs.get("missing_sections")),
        f"문서 키={sorted(set(docs) & {'approval', 'representation_warranty', 'evidence_package'})}"
        f" · hash_fixed={docs.get('hash_fixed')} · missing={docs.get('missing_sections')}",
    )

    sign = await c.post(f"/api/decisions/{did}/sign", json={"note": "스모크 정상 서명"}, headers=MGR)
    row = db_rows(db, "SELECT * FROM decisions WHERE decision_id=?", (did,))
    r = row[0] if row else None
    # ⑨ 확정 — 서명 3요소가 실제로 DB 에 남는다 (응답만 보면 UPDATE 를 못 본다)
    check(
        "[비차단] sign(manager) → 200 · state=signed · signed_at·reviewed_by non-null · 해시 불변",
        sign.status_code == 200
        and r is not None
        and r["state"] == "signed"
        and bool(r["signed_at"])
        and r["reviewed_by"] == "mgr-01"
        and r["override"] == 0
        and r["bundle_hash"] == hash_at_draft,
        f"{sign.status_code} state={r['state'] if r else '-'} "
        f"signed_at={bool(r['signed_at']) if r else '-'} reviewed_by={r['reviewed_by'] if r else '-'} "
        f"override={r['override'] if r else '-'} 해시불변={r['bundle_hash'] == hash_at_draft if r else '-'}",
    )


async def _blocked_path(c: httpx.AsyncClient, client, db: Path) -> None:
    """차단 경로 — precheck 409 → **draft 는 생성된다**(D63) → 서명 409 → override 서명 200."""
    pre = await _precheck(c, BLOCKED_ASSET, BLOCKED_MODE)
    body = pre.json()
    # ⑩ S9 — 차단 판정은 409 이되 본문에 재료를 싣는다 (S4 태도)
    check(
        f"[차단] precheck {BLOCKED_ASSET}/{BLOCKED_MODE} → 409 · verdict=BLOCKED · blockers 동봉",
        pre.status_code == 409
        and body.get("verdict") == "BLOCKED"
        and len(body.get("blockers") or []) >= 1,
        f"{pre.status_code} verdict={body.get('verdict')} "
        f"blockers={[b.get('rule_id') for b in body.get('blockers') or []]}",
    )

    doc = await _make_draft(client, BLOCKED_ASSET, BLOCKED_MODE, "노후 설비 매각 (S10 스모크)")
    did = doc.get("decision_id")
    # ⑪ D63 — 막지 않는다. 막으면 사용자는 시스템 밖에서 처분하고 **기록만 사라진다**
    check(
        "[차단] BLOCKED 여도 draft 는 생성된다 (D63 — 막지 않고 차단 사실을 기록한다) · override=false",
        doc.get("status") == "ok"
        and doc.get("state") == "draft"
        and doc.get("verdict_at_signing") == "BLOCKED"
        and doc.get("override") is False,
        f"status={doc.get('status')}/{doc.get('reason', '-')} decision_id={did} "
        f"verdict={doc.get('verdict_at_signing')} override={doc.get('override')}",
    )
    if not did:
        check("[차단] 이후 관통 (draft 없음)", False, "decision_id 가 없어 경로를 이어갈 수 없다")
        return

    await c.post(f"/api/decisions/{did}/submit", headers=TECH)
    plain = await c.post(f"/api/decisions/{did}/sign", json={}, headers=MGR)
    pb = plain.json()
    # ⑫ **BLOCKING 우회 0건** — 실 서버에서도 override 없는 서명은 409
    check(
        "[차단] sign(override 없음) → 409 override_required + blockers·resolve_options (D63·D38)",
        plain.status_code == 409
        and pb.get("reason") == "override_required"
        and pb.get("verdict") == "BLOCKED"
        and len(pb.get("blockers") or []) >= 1
        and len(pb.get("resolve_options") or []) >= 1,
        f"{plain.status_code} reason={pb.get('reason')} verdict={pb.get('verdict')} "
        f"blockers={len(pb.get('blockers') or [])}건 resolve={len(pb.get('resolve_options') or [])}건",
    )

    # ⑬ 정비사는 서명할 수 없다 — 실 서버에서도 역할 게이트가 산다 (D38 403)
    tech_sign = await c.post(f"/api/decisions/{did}/sign", json={}, headers=TECH)
    mgr_submit = await c.post(f"/api/decisions/{did}/submit", headers=MGR)
    check(
        "[차단] 403 양방향 — technician sign 403 · manager submit 403 (권한과 상태를 섞지 않는다)",
        tech_sign.status_code == 403 and mgr_submit.status_code == 403,
        f"technician sign={tech_sign.status_code} · manager submit={mgr_submit.status_code}",
    )

    ovr = await c.post(
        f"/api/decisions/{did}/sign",
        json={"override": True, "override_reason": OVERRIDE_REASON},
        headers=MGR,
    )
    row = db_rows(db, "SELECT * FROM decisions WHERE decision_id=?", (did,))
    r = row[0] if row else None
    # ⑭ 예외 적용은 **가능하되 전부 기록된다** — 뚫은 사람·사유·판정이 남는다
    check(
        "[차단] sign(override=true + 사유) → 200 · override=1 · 사유·서명자·BLOCKED 판정 기록",
        ovr.status_code == 200
        and r is not None
        and r["state"] == "signed"
        and r["override"] == 1
        and (r["override_reason"] or "").strip() == OVERRIDE_REASON
        and r["reviewed_by"] == "mgr-01"
        and bool(r["signed_at"])
        and r["verdict_at_signing"] == "BLOCKED",
        f"{ovr.status_code} state={r['state'] if r else '-'} override={r['override'] if r else '-'} "
        f"verdict={r['verdict_at_signing'] if r else '-'} "
        f"reason={((r['override_reason'] or '')[:24] if r else '-')!r}",
    )

    # ⑮ 임시 DB 쪽 불변식 — 이 스모크가 남긴 서명 행도 규약을 지킨다
    bad = db_rows(
        db,
        "SELECT decision_id FROM decisions WHERE state='signed' AND ("
        " signed_at IS NULL OR reviewed_by IS NULL"
        " OR reviewed_by NOT IN (SELECT user_id FROM users)"
        " OR (verdict_at_signing NOT IN ('CONDITIONAL','CLEAR') AND override <> 1))",
    )
    signed_n = db_rows(db, "SELECT count(*) FROM decisions WHERE state='signed'")[0][0]
    check(
        "스모크가 남긴 signed 행 불변식 — 서명 3요소 존재 · 차단 판정은 override=1 (공허하지 않음)",
        not bad and signed_n >= 2,
        f"signed {signed_n}행 · 위반 {len(bad)}행" + (f" {[x[0] for x in bad]}" if bad else ""),
    )


# ── 실행 ────────────────────────────────────────────────────────────────────────
def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("MQ-708 — S9→S10 관통 스모크 (실 uvicorn + 실 MCP stdio · full 프로파일)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    before = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)
    before_rows = db_rows(SOURCE_DB, "SELECT count(*) FROM decisions")[0][0]
    print(f"[실 DB] size={before[1]} · decisions={before_rows}행 (읽기만 한다)")

    err_bytes = b""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = Path(td) / "s10.db"
        shutil.copy2(SOURCE_DB, db)
        for side in ("-wal", "-shm"):
            src = SOURCE_DB.with_name(SOURCE_DB.name + side)
            if src.exists():
                shutil.copy2(src, db.with_name(db.name + side))

        # ⚠ `env={**os.environ, ...}` — 명시 상속이다. env=None 이면 자식이 실 DB 를 연다.
        env = {
            **os.environ,
            "MAINTQ_DB": str(db),
            "MAINTQ_TOOLS_PROFILE": "full",
            "MAINTQ_MCP_AUTOSTART": "1",
        }
        os.environ["MAINTQ_DB"] = str(db)  # in-process 쪽 안전망 (McpClient 는 명시 전달)
        print(f"[격리] MAINTQ_DB = {db}")
        print(f"[격리] MAINTQ_TOOLS_PROFILE = full · 포트 {PORT}\n")

        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.main:app",
                "--port",
                str(PORT),
                "--log-level",
                "warning",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            if not asyncio.run(wait_ready()):
                # 스킵하지 않는다 — 기동 실패는 **명시적 FAIL** 이다
                tail = ""
                if proc.stderr:
                    proc.terminate()
                    _, e = proc.communicate(timeout=10)
                    tail = (e or b"").decode("utf-8", "replace")[-600:]
                check("실 uvicorn 서버 기동 · /health 200 · MCP 세션 ready", False, f"기동 실패 {tail}")
            else:
                asyncio.run(run_all(db))
        finally:
            if proc.poll() is None:
                proc.terminate()
            try:
                # sleep 으로 때우지 않는다 — 자식 종료를 기다린다 (Windows 는 핸들 해제가 비동기)
                _, err_bytes = proc.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                _, err_bytes = proc.communicate()

    stderr_text = (err_bytes or b"").decode("utf-8", "replace")
    marks = [m for m in ("cancel scope", "CancelledError", "Traceback") if m in stderr_text]
    check(
        "서버 로그에 cancel scope·Traceback 없음 (D42 — 조기 종료가 세션을 오염시키지 않는다)",
        not marks,
        f"검출 {marks}" if marks else "깨끗함",
    )

    after = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)
    after_rows = db_rows(SOURCE_DB, "SELECT count(*) FROM decisions")[0][0]
    check(
        "실 DB 오염 0 — data/maintq.db mtime·size·decisions 행 수 불변",
        before == after and before_rows == after_rows,
        f"mtime·size {'불변' if before == after else f'{before} → {after}'} · "
        f"decisions {before_rows} → {after_rows}행",
    )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 44))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 44))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        if stderr_text.strip():
            print(f"\n[서버 stderr 끝부분]\n{stderr_text[-1200:]}")
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(
        f"\n통과 ({len(results)}건) — 실 서버·실 MCP 로 비차단·차단 두 경로를 완주했고, "
        "차단 경로는 override 없이는 확정되지 않았다"
    )


if __name__ == "__main__":
    main()