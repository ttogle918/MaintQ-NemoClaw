# -*- coding: utf-8 -*-
"""A2A 파트너 도구 2종 계약 검증 — `search_insurance_clause`·`assess_equipment_loan`
(MQ-1613, Sprint 16 Stage 4).

Stage 1~2(`3a6c558`·`d77992f`)가 만든 산출물의 **신규 계약**을 고정한다:

  ① `mcp_server/tools/{search_insurance_clause,assess_equipment_loan}.py` 가
     `backend.a2a`·`MAINTQ_A2A_` 를 참조하지 않는가 (D15·D93 — mcp_server 프로세스는
     A2A 자격증명·파트너 대장을 모른다). **부재 검사**라 CLAUDE.md 의 liveness 앵커
     원칙대로 "그냥 텅 빈 파일이라 0건"인 위양성을 배제한다 — 두 파일이 실제로
     `httpx`/`MAINTQ_BACKEND_BASE_URL` 을 참조하는 것을 같은 검사 안에서 함께 본다.
  ② `mcp_server/server.py` 의 `full` 블록에 두 도구가 등록돼 있고, `core`(기본,
     `MAINTQ_TOOLS_PROFILE` 미지정) 기동 시 목록에 없는가 — **실제로 `mcp_server` 를
     기동**해 `list_tools()` 로 확인한다(`sp2_mcp_roundtrip.py`·`mcp_client_contract.py`
     의 stdio 기동 패턴을 재사용). `s10_smoke.py` 는 `full` 만 보므로 이 스위트가
     `core` 쪽 부재를 담당해 상호 보완한다 (D69·D88).
  ③ `httpx` 모킹으로 두 도구 각각 5가지 응답 경로(200/completed, 200/input-required
     또는 rejected, 502, timeout, 접속거부)에 대해 `status`/`reason` 조합이 스펙과
     일치하는가 (D9 — 실패는 예외가 아니라 status).
  ④ `backend/sse.py::tool_result()` 가 `a2a_chain_id=None` 일 때 기존 도구와 바이트
     동일한 키 집합(`{tool,status,summary,elapsed}`)을 내는가 (D30 회귀 방지). 값을
     주면 실제로 키가 실리는 것도 같이 확인한다 — ①과 같은 이유의 liveness 짝.
  ⑤ `GET /api/a2a/history`(`backend/services/a2a_history.py::list_a2a_history`) 왕복 —
     `record_a2a_trace` 로 3스킬 각 1건씩 심고 skill·po_id·building_id·chain_id 필터가
     각각 정확히 걸리는가 (D114). **테스트 DB** — `MAINTQ_DB` 를 임시 파일로 지정해
     실 `data/maintq.db` 를 절대 건드리지 않는다.

## 엣지 케이스

②는 실제 프로세스를 2번 기동한다 — Windows 소켓 고갈(`OSError: [WinError 10014]`)의
영향을 받을 수 있다(CLAUDE.md). 실패하면 이 스위트만 단독 재실행해서 확인할 것 —
코드 결함이 아니다.

실행:  uv run python spikes/a2a_partner_tools_contract.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.a2a.trace import record_a2a_trace  # noqa: E402
from backend.services.a2a_history import list_a2a_history  # noqa: E402
from backend.sse import tool_result  # noqa: E402
from mcp_server.tools.assess_equipment_loan import assess_equipment_loan  # noqa: E402
from mcp_server.tools.search_insurance_clause import search_insurance_clause  # noqa: E402

SERVER = ROOT / "mcp_server" / "server.py"
SOURCE_DB = ROOT / "data" / "maintq.db"

TOOL_FILES = {
    "search_insurance_clause": ROOT / "mcp_server" / "tools" / "search_insurance_clause.py",
    "assess_equipment_loan": ROOT / "mcp_server" / "tools" / "assess_equipment_loan.py",
}

NEW_TOOLS = {"search_insurance_clause", "assess_equipment_loan"}

# Sprint 16 Stage 1~3 이전의 "기존" 도구 18종(코어 7 + 확장 11) — ④ 의 회귀 기준선이다.
# tools_profile_contract.py 의 상수를 import 하지 않는다 — 그 파일은 Stage 4/MQ-1611 이
# 20종으로 갱신할 예정이라, 이 스위트가 거기 의존하면 남의 태스크가 이 스위트를 깨뜨린다.
EXISTING_TOOLS = {
    "lookup_error_code",
    "rag_search_manual",
    "search_inventory",
    "find_alternative_parts",
    "get_supplier_quotes",
    "get_error_history",
    "create_po_draft",
    "check_disposal_blockers",
    "verify_ownership",
    "classify_part_criticality",
    "get_maintenance_metrics",
    "classify_expenditure",
    "assess_repair_value",
    "build_evidence_bundle",
    "generate_disposal_document",
    "create_repair_record",
    "track_deadlines",
    "assess_risk_grade",
}

_TRACES_SCHEMA = """
CREATE TABLE traces (
  id           INTEGER PRIMARY KEY,
  session_id   TEXT NOT NULL,
  seq          INTEGER NOT NULL,
  event_type   TEXT NOT NULL,
  tool         TEXT,
  payload      TEXT NOT NULL,
  tool_payload TEXT,
  request_chain_id TEXT,
  ts           DATETIME DEFAULT CURRENT_TIMESTAMP,
  CHECK (event_type IN ('tool_call','tool_result','block')),
  UNIQUE (session_id, seq)
);
"""

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


# ── ① 소스 격리 + liveness 앵커 (D15·D93) ──────────────────────────────────────


def check_source_isolation() -> None:
    for tool_name, path in TOOL_FILES.items():
        src = path.read_text(encoding="utf-8")
        backend_a2a_hits = src.count("backend.a2a")
        maintq_a2a_hits = src.count("MAINTQ_A2A_")
        httpx_hits = src.count("httpx")
        base_url_hits = src.count("MAINTQ_BACKEND_BASE_URL")
        check(
            f"①-{tool_name} D15·D93 격리(backend.a2a/MAINTQ_A2A_ 0건) + liveness(httpx/BASE_URL 실사용)",
            backend_a2a_hits == 0 and maintq_a2a_hits == 0 and httpx_hits > 0 and base_url_hits > 0,
            f"backend.a2a={backend_a2a_hits}건 · MAINTQ_A2A_={maintq_a2a_hits}건 · "
            f"httpx={httpx_hits}건 · MAINTQ_BACKEND_BASE_URL={base_url_hits}건",
        )


# ── ② 프로파일 등록 — 실기동 (D69·D88) ─────────────────────────────────────────


async def list_tool_names(profile: str | None, db: Path) -> set[str]:
    """mcp_server 를 stdio 로 실기동해 도구 이름 집합을 받는다.

    `profile=None` 은 `MAINTQ_TOOLS_PROFILE` 을 **지정하지 않는** 것 — 기본값(core)
    경로가 실제로 그렇게 동작하는지를 보려면 강제로 "core" 문자열을 심으면 안 된다.
    """
    env = {k: v for k, v in os.environ.items() if v is not None}
    if profile is not None:
        env["MAINTQ_TOOLS_PROFILE"] = profile
    else:
        env.pop("MAINTQ_TOOLS_PROFILE", None)
    env["MAINTQ_DB"] = str(db)

    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            return {t.name for t in listed.tools}


async def check_profile_registration(db: Path) -> None:
    full_names = await list_tool_names("full", db)
    check(
        "②-a full 프로파일 실기동 → 두 도구 등록",
        NEW_TOOLS <= full_names,
        f"{len(full_names)}종 · 누락={sorted(NEW_TOOLS - full_names) or '없음'}",
    )

    core_names = await list_tool_names(None, db)
    check(
        "②-b core(기본, MAINTQ_TOOLS_PROFILE 미지정) 실기동 → 두 도구 부재",
        not (NEW_TOOLS & core_names),
        f"{len(core_names)}종 · 누출={sorted(NEW_TOOLS & core_names) or '없음'}",
    )


# ── ③ httpx 모킹 — 5경로 × 2도구 (D9) ─────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int, json_data: Any = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self) -> Any:
        if self._json_data is None:
            raise ValueError("no json body")
        return self._json_data


@contextmanager
def mock_post(*, response: _FakeResponse | None = None, exc: Exception | None = None):
    """`httpx.post` 를 전역으로 갈아끼운다 — 도구 모듈이 참조하는 `httpx` 는 이 파일이
    import 한 것과 같은 모듈 객체다 (기존 `test_search_insurance_clause.py` 의 monkeypatch
    와 같은 원리, 이 스위트는 pytest 가 아니라 직접 저장·복원한다)."""
    original = httpx.post

    def fake_post(url: str, json: Any = None, timeout: float | None = None) -> _FakeResponse:
        if exc is not None:
            raise exc
        assert response is not None
        return response

    httpx.post = fake_post
    try:
        yield
    finally:
        httpx.post = original


def check_http_paths(tool_name: str, tool_fn, call_kwargs: dict, non_completed_status: str) -> None:
    with mock_post(
        response=_FakeResponse(
            200,
            json_data={"status": "completed", "verdict": "V", "request_chain_id": "CHAIN-SPIKE-OK"},
        )
    ):
        r = tool_fn(**call_kwargs)
    check(
        f"③-{tool_name} 200/completed → status ok · skill_status completed",
        r.get("status") == "ok" and r.get("skill_status") == "completed",
        f"status={r.get('status')} skill_status={r.get('skill_status')}",
    )

    with mock_post(response=_FakeResponse(200, json_data={"status": non_completed_status})):
        r = tool_fn(**call_kwargs)
    check(
        f"③-{tool_name} 200/{non_completed_status} → status error · reason no_answer",
        r.get("status") == "error" and r.get("reason") == "no_answer",
        f"status={r.get('status')} reason={r.get('reason')} skill_status={r.get('skill_status')}",
    )

    with mock_post(response=_FakeResponse(502, text="adapter down")):
        r = tool_fn(**call_kwargs)
    check(
        f"③-{tool_name} 502 → status error · reason upstream_unavailable",
        r.get("status") == "error" and r.get("reason") == "upstream_unavailable",
        f"status={r.get('status')} reason={r.get('reason')}",
    )

    with mock_post(exc=httpx.TimeoutException("timed out")):
        r = tool_fn(**call_kwargs)
    check(
        f"③-{tool_name} timeout → status error · reason timeout",
        r.get("status") == "error" and r.get("reason") == "timeout",
        f"status={r.get('status')} reason={r.get('reason')}",
    )

    with mock_post(exc=httpx.ConnectError("refused")):
        r = tool_fn(**call_kwargs)
    check(
        f"③-{tool_name} 접속거부 → status error · reason backend_unreachable",
        r.get("status") == "error" and r.get("reason") == "backend_unreachable",
        f"status={r.get('status')} reason={r.get('reason')}",
    )


def check_http_mocking() -> None:
    check_http_paths(
        "search_insurance_clause",
        search_insurance_clause,
        {"question": "화재로 인한 인버터 손해가 보장되나요?"},
        "input-required",
    )
    check_http_paths(
        "assess_equipment_loan",
        assess_equipment_loan,
        {"loan_amount": 50000000, "purpose": "설비교체", "collateral_building_id": "BLD-SPIKE-1"},
        "rejected",
    )


# ── ④ SSE tool_result 바이트 동일 키 집합 (D30) ────────────────────────────────


def check_sse_byte_identical_keys() -> None:
    key_sets = set()
    for name in sorted(EXISTING_TOOLS):
        ev = tool_result(name, "ok", f"{name} 완료", 0.1)
        key_sets.add(frozenset(ev.data.keys()))
    check(
        "④-a 기존 도구 전부 a2a_chain_id=None → 키 집합 {tool,status,summary,elapsed} 바이트 동일",
        key_sets == {frozenset({"tool", "status", "summary", "elapsed"})},
        f"{len(EXISTING_TOOLS)}종 대상 · 관측된 키집합 {[sorted(s) for s in key_sets]}",
    )

    ev_with_chain = tool_result(
        "search_insurance_clause", "ok", "InsuQ 약관 조회 완료", 0.2, a2a_chain_id="CHAIN-SPIKE-SSE"
    )
    check(
        "④-b liveness — a2a_chain_id 값을 주면 실제로 키가 실린다(①-b 형 짝: 부재가 아니라 선택 필드)",
        set(ev_with_chain.data.keys()) == {"tool", "status", "summary", "elapsed", "a2a_chain_id"}
        and ev_with_chain.data["a2a_chain_id"] == "CHAIN-SPIKE-SSE",
        f"키={sorted(ev_with_chain.data.keys())}",
    )


# ── ⑤ GET /api/a2a/history 왕복 (D114) ────────────────────────────────────────


def check_a2a_history_roundtrip() -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = Path(td) / "a2a_history_spike.db"
        con = sqlite3.connect(db)
        con.executescript(_TRACES_SCHEMA)
        con.commit()
        con.close()

        prev = os.environ.get("MAINTQ_DB")
        os.environ["MAINTQ_DB"] = str(db)
        try:
            record_a2a_trace(
                session_id="sess-a2a-spike",
                skill_id="request-withdrawal",
                request_payload={"po_id": "PO-SPIKE-1", "amount": 12345},
                response_payload={"status": "completed", "req_id": "R1"},
                request_chain_id="CHAIN-SPIKE-PO",
                status="ok",
            )
            record_a2a_trace(
                session_id="sess-a2a-spike",
                skill_id="lookup-clause",
                request_payload={"question": "화재 특약 보장 범위는?"},
                response_payload={"status": "completed", "answer": "보장됩니다"},
                request_chain_id="CHAIN-SPIKE-CLAUSE",
                status="ok",
            )
            record_a2a_trace(
                session_id="sess-a2a-spike",
                skill_id="assess-loan",
                request_payload={"collateral_building_id": "BLD-SPIKE-1", "loan_amount": 5000},
                response_payload={"status": "completed"},
                request_chain_id="CHAIN-SPIKE-LOAN",
                status="ok",
            )

            all_hist = list_a2a_history()
            check(
                "⑤-a 필터 없음 → 3스킬 전부 회수(MAINTQ_DB 임시 지정 경유)",
                all_hist["count"] == 3
                and {it["skill"] for it in all_hist["items"]}
                == {"request-withdrawal", "lookup-clause", "assess-loan"},
                f"count={all_hist['count']} skills={sorted(it['skill'] for it in all_hist['items'])}",
            )

            by_skill = list_a2a_history(skill="lookup-clause")
            check(
                "⑤-b skill 필터 정확히 걸림",
                by_skill["count"] == 1
                and by_skill["items"][0]["request_chain_id"] == "CHAIN-SPIKE-CLAUSE",
                f"count={by_skill['count']} chain={[it['request_chain_id'] for it in by_skill['items']]}",
            )

            by_po = list_a2a_history(po_id="PO-SPIKE-1")
            check(
                "⑤-c po_id 필터 정확히 걸림",
                by_po["count"] == 1 and by_po["items"][0]["request_chain_id"] == "CHAIN-SPIKE-PO",
                f"count={by_po['count']} chain={[it['request_chain_id'] for it in by_po['items']]}",
            )

            by_building = list_a2a_history(building_id="BLD-SPIKE-1")
            check(
                "⑤-d building_id 필터 정확히 걸림",
                by_building["count"] == 1
                and by_building["items"][0]["request_chain_id"] == "CHAIN-SPIKE-LOAN",
                f"count={by_building['count']} "
                f"chain={[it['request_chain_id'] for it in by_building['items']]}",
            )

            by_chain = list_a2a_history(chain_id="CHAIN-SPIKE-CLAUSE")
            check(
                "⑤-e chain_id 정확 매칭(접두어 매칭 아님)",
                by_chain["count"] == 1
                and by_chain["items"][0]["request_chain_id"] == "CHAIN-SPIKE-CLAUSE",
                f"count={by_chain['count']}",
            )
        finally:
            if prev is None:
                os.environ.pop("MAINTQ_DB", None)
            else:
                os.environ["MAINTQ_DB"] = prev


# ── main ────────────────────────────────────────────────────────────────────


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("MQ-1613 — A2A 파트너 도구 2종 계약 (D15·D93·D69·D88·D9·D30·D114)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    before = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)
    print(f"[격리] 실 DB(before) mtime_ns={before[0]} size={before[1]}")

    check_source_isolation()

    # Windows 는 sqlite 커넥션이 하나라도 열려 있으면 파일을 못 지운다 —
    # 정리 실패로 계약 결과가 가려지지 않게 한다 (rules_db_load.py 선례).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db_copy = Path(td) / "profile.db"
        shutil.copy2(SOURCE_DB, db_copy)
        asyncio.run(check_profile_registration(db_copy))

    check_http_mocking()
    check_sse_byte_identical_keys()
    check_a2a_history_roundtrip()

    after = (SOURCE_DB.stat().st_mtime_ns, SOURCE_DB.stat().st_size)
    print(f"[격리] 실 DB(after)  mtime_ns={after[0]} size={after[1]}\n")

    # 격리를 계수되는 검사로 둔다 (sp2_mcp_roundtrip.py 선례) — 비계수 게이트로 두면
    # 러너 출력에 격리 생존 여부가 안 나타나 매 회귀마다 확인이 안 된다.
    check(
        "⑥ 격리 — 실 data/maintq.db mtime·size 불변",
        after == before,
        f"변경={after != before}",
    )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — A2A 파트너 도구 2종 격리·프로파일·5경로·SSE·이력 왕복 확인")


if __name__ == "__main__":
    main()
