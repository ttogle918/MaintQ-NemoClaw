# -*- coding: utf-8 -*-
"""에이전트 루프 계약 검증 (MQ-306) — docs/09_RUNTIME.md §2 의 A1~A8.

**API 키가 필요 없다** (D40). `ScriptedClient` 로 LLM 응답을 고정하고, MCP 는
가짜 클라이언트로 대체해 루프 자체의 정책만 본다. 루프가 지켜야 하는 것들은
전부 "LLM 이 무엇을 말했는가"와 무관한 규칙이라 이렇게 검증할 수 있다.

임시 DB 사본에서 돈다 — traces·po_drafts 에 실제로 쓰므로 원본을 오염시키면 안 된다.

실행:  uv run python spikes/agent_loop_contract.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
SOURCE_DB = ROOT / "data" / "maintq.db"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


class FakeMcp:
    """MCP 워커를 대신한다 — 루프는 `call()`/`list_tools()` 만 쓴다 (D42).

    `call_log` 로 **호출 시점**을 기록해 A1(tool_call 이 호출 직전)을 검증한다.
    """

    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.call_log: list[str] = []
        self.on_call = None  # 호출 순간 훅 (A1 검증용)

    async def list_tools(self) -> list[dict]:
        return [{"name": n, "description": n, "inputSchema": {}} for n in self.responses]

    async def call(self, tool: str, args: dict | None = None, *, timeout=None) -> dict:
        self.call_log.append(tool)
        if self.on_call:
            self.on_call(tool)
        return self.responses.get(tool, {"status": "error", "reason": "unknown_tool"})


def kinds(events) -> list[str]:
    return [e.event for e in events]


def blocks(events, btype: str) -> list[dict]:
    return [e.data["data"] for e in events if e.event == "block" and e.data.get("type") == btype]


async def drive(script, responses, *, db, session="T1", equipment="INV-L1-01", msg="테스트"):
    """루프를 한 턴 돌리고 (이벤트, fake, writer) 를 돌려준다."""
    from backend.agent.llm import ScriptedClient
    from backend.agent.loop import SessionStore, run_turn
    from backend.agent.trace import TraceWriter

    fake = FakeMcp(responses)
    writer = TraceWriter(session, db_path=db)
    events = []
    async for ev in run_turn(
        session_id=session,
        message=msg,
        equipment_id=equipment,
        user_id="tech-01",
        llm=ScriptedClient(script),
        client=fake,  # type: ignore[arg-type]
        trace=writer,
        store=SessionStore(),
    ):
        events.append(ev)
    return events, fake, writer


LOOKUP_OK = {
    "status": "ok",
    "code": "OHT",
    "display_code": "OHt",
    "error_name": "인버터 과열",
    "severity": "warning",
    "causes": [],
    "actions": [],
    "related_parts": ["FAN-IG5-01"],
    "manual_page": 202,
}
#: 같은 절이 **두 페이지에 걸친** 청크를 넣는다 — 청크는 페이지 경계를 안 넘으므로(MQ-305)
#: 흔한 상황이다. 1건짜리 픽스처면 label 중복 검사가 공회전한다(실제로 그래서 놓쳤다).
RAG_OK = {
    "status": "ok",
    "chunks": [
        {"text": "커버 개방 절차", "page": 204, "section": "12.2 고장 대책"},
        {"text": "이어지는 절차", "page": 205, "section": "12.2 고장 대책"},
        {"text": "절연 측정", "page": 206, "section": "12.3 절연 점검"},
    ],
}
HISTORY_REPEATED = {"status": "ok", "count": 3, "repeated": True, "events": []}


async def run_all(db: Path) -> None:
    from backend.agent.llm import ToolUse

    def tu(name, **kw):
        return ("tool_use", ToolUse(id="t1", name=name, input=kw))

    # ── ① A1: tool_call 이 실행 **직전** (호출 시점에 tool_call 이 이미 나가 있어야)
    ev, fake, _ = await drive(
        [[tu("lookup_error_code", model="iG5A", code="OHt")], [("text", "과열입니다.")]],
        {"lookup_error_code": LOOKUP_OK},
        db=db,
    )
    order = kinds(ev)
    i_call = order.index("tool_call")
    i_res = order.index("tool_result")
    check("① A1 tool_call → tool_result 순서", i_call < i_res, f"{order[:4]}")

    # ── ② 도구 없는 텍스트 → 턴 종료
    ev, fake, _ = await drive([[("text", "안녕하세요.")]], {}, db=db, session="T2")
    check(
        "② 도구 없는 응답 → 턴 종료",
        fake.call_log == [] and "token" in kinds(ev),
        f"calls={fake.call_log}",
    )

    # ── ③ 동일 도구·동일 입력 연속 → 두 번째는 실행 안 됨
    ev, fake, _ = await drive(
        [
            [tu("lookup_error_code", model="iG5A", code="OHt")],
            [tu("lookup_error_code", model="iG5A", code="OHt")],
            [("text", "끝")],
        ],
        {"lookup_error_code": LOOKUP_OK},
        db=db,
        session="T3",
    )
    check(
        "③ 루프 탈출 — 동일 호출 반복 차단",
        fake.call_log == ["lookup_error_code"],
        f"실행 {len(fake.call_log)}회",
    )

    # ── ④ 도구 호출 상한 8
    many = [[tu("search_inventory", part_no=f"P-{i}")] for i in range(12)] + [[("text", "끝")]]
    ev, fake, _ = await drive(
        many, {"search_inventory": {"status": "ok", "items": []}}, db=db, session="T4"
    )
    check("④ 턴당 도구 호출 상한 8", len(fake.call_log) <= 8, f"{len(fake.call_log)}회")

    # ── ⑤⑥ 안전 블록이 위험 서술 **앞**에, 문구는 상수
    from backend.agent import prompts

    ev, _, _ = await drive(
        [
            [tu("rag_search_manual", model="iG5A", query="절차")],
            [("text", "커버를 열고 냉각팬을 분리하십시오.")],
        ],
        {"rag_search_manual": RAG_OK},
        db=db,
        session="T5",
    )
    order = kinds(ev)
    saf = blocks(ev, "safety")
    i_saf = next(
        (i for i, e in enumerate(ev) if e.event == "block" and e.data.get("type") == "safety"), -1
    )
    i_danger = next(
        (
            i
            for i, e in enumerate(ev)
            if e.event == "token" and "커버를 열" in str(e.data.get("text", ""))
        ),
        -1,
    )
    check(
        "⑤ 안전 블록이 위험 서술보다 먼저",
        i_saf >= 0 and i_danger >= 0 and i_saf < i_danger,
        f"safety={i_saf}, 위험={i_danger}",
    )
    check(
        "⑥ 안전 문구는 SAFETY_BASELINE 상수 (LLM 생성 아님)",
        bool(saf)
        and saf[0]["text"] == prompts.SAFETY_BASELINE["text"]
        and "10분 이상" in saf[0]["text"],
        "상수 일치 + '10분 이상'",
    )
    # ★ 이 검사가 없어서 블로커를 놓쳤다 — ⑤⑥ 은 문구와 순서만 보고 **페이지를 안 봤다**.
    # 안전 문구의 근거는 SAFETY_BASELINE["pages"](iG5A 4)이지 그 턴의 rag 페이지(204)가 아니다.
    expected_page = prompts.SAFETY_BASELINE["pages"]["iG5A"]
    cit_in_safety = saf[0].get("citation", {}) if saf else {}
    check(
        "⑥-b ★ 안전 블록 인용이 SAFETY_BASELINE 페이지 (도구 페이지 아님)",
        cit_in_safety.get("page") == expected_page,
        f"page={cit_in_safety.get('page')} (기대 {expected_page}, 도구는 204)",
    )
    check(
        "⑥-c 안전 블록 인용이 계약 형태 {page,print_page,label}",
        set(cit_in_safety) >= {"page", "print_page", "label"}
        and "매뉴얼" in str(cit_in_safety.get("label", "")),
        f"{cit_in_safety}",
    )

    # ── ⑦ 근거 페이지가 없으면 안전 블록도 위험 서술도 내지 않는다
    ev, _, _ = await drive([[("text", "커버를 열고 작업하십시오.")]], {}, db=db, session="T6")
    texts = " ".join(str(e.data.get("text", "")) for e in ev if e.event == "token")
    check(
        "⑦ 근거 없으면 안전 블록·위험 서술 둘 다 안 냄",
        not blocks(ev, "safety") and "커버를 열" not in texts and "확인하지 못해" in texts,
        f"safety={len(blocks(ev, 'safety'))}건",
    )

    # ── ⑧ citation.page == 도구 결과의 page (D30)
    ev, _, _ = await drive(
        [[tu("lookup_error_code", model="iG5A", code="OHt")], [("text", "과열입니다.")]],
        {"lookup_error_code": LOOKUP_OK},
        db=db,
        session="T7",
    )
    cit = blocks(ev, "citation")
    check(
        "⑧ D30 citation.page == lookup 결과 page",
        bool(cit) and cit[0]["page"] == LOOKUP_OK["manual_page"],
        f"page={cit[0]['page'] if cit else None} (도구 202)",
    )

    # ── ⑨ D45 hold 블록 (repeated + po_draft 미호출)
    ev, _, _ = await drive(
        [
            [tu("get_error_history", equipment_id="INV-L3-01", days=7)],
            [tu("rag_search_manual", model="iG5A", query="근본원인")],
            [("text", "근본원인 점검이 필요합니다.")],
        ],
        {"get_error_history": HISTORY_REPEATED, "rag_search_manual": RAG_OK},
        db=db,
        session="T8",
    )
    hold = [b for b in blocks(ev, "po_card") if b.get("variant") == "hold"]
    check(
        "⑨ A8·D45 repeated → po_card variant:hold",
        bool(hold) and set(hold[0]) >= {"variant", "reason", "checklist", "repeated"},
        f"keys={sorted(hold[0]) if hold else None}",
    )
    rag_pages = {c["page"] for c in RAG_OK["chunks"]}
    check(
        "⑩ hold checklist 의 citation 은 rag page 에서만",
        bool(hold) and all(c["citation"]["page"] in rag_pages for c in hold[0]["checklist"]),
        f"{[c['citation']['page'] for c in hold[0]['checklist']] if hold else None}",
    )
    check(
        "⑩-b hold checklist citation 도 계약 형태 · label 중복 없음",
        bool(hold)
        and all(set(c["citation"]) >= {"page", "print_page", "label"} for c in hold[0]["checklist"])
        and len({c["label"] for c in hold[0]["checklist"]}) == len(hold[0]["checklist"]),
        f"{[c['citation'].get('label') for c in hold[0]['checklist']] if hold else None}",
    )

    check(
        "⑨-b N-1 window_days 가 호출에 쓴 days 를 따른다 (30 하드코딩 아님)",
        bool(hold) and hold[0]["repeated"]["window_days"] == 7,
        f"window_days={hold[0]['repeated']['window_days'] if hold else None} (호출 days=7)",
    )

    # ── ⑩-c N-4: S100 은 안전 페이지가 물리 p.2 이고 offset 16 이라 환산하면 p.-14 가 된다.
    # D49 경계가 하필 안전 지침 페이지라 루프 레벨에서도 봐야 한다.
    ev, _, _ = await drive(
        [
            [tu("rag_search_manual", model="S100", query="절차")],
            [("text", "커버를 열고 점검하십시오.")],
        ],
        {
            "rag_search_manual": {
                "status": "ok",
                "chunks": [{"text": "x", "page": 416, "section": "9.1"}],
            }
        },
        db=db,
        session="TS100",
        equipment="INV-L2-01",  # S100 장비
    )
    saf_s = blocks(ev, "safety")
    cit_s = saf_s[0].get("citation", {}) if saf_s else {}
    check(
        "⑩-c ★ S100 안전 인용에 음수 페이지가 안 뜬다 (D49 경계)",
        cit_s.get("page") == 2
        and cit_s.get("print_page") == 2
        and "-" not in str(cit_s.get("label", "")),
        f"{cit_s}",
    )

    # ── ⑪⑫ draft po_card + 신원 stamp
    con = sqlite3.connect(db)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute(
        "INSERT INTO po_drafts (po_id, part_no, qty, supplier_id, unit_price, reason, state)"
        " VALUES ('PO-9001','FAN-IG5-01',2,'SUP-A',38000,'테스트','draft')"
    )
    con.commit()
    con.close()

    ev, _, _ = await drive(
        [
            [tu("create_po_draft", part_no="FAN-IG5-01", qty=2, supplier_id="SUP-A", reason="x")],
            [("text", "발주 초안을 만들었습니다.")],
        ],
        {"create_po_draft": {"status": "ok", "po_id": "PO-9001", "state": "draft"}},
        db=db,
        session="T9",
    )
    draft = [b for b in blocks(ev, "po_card") if b.get("variant") == "draft"]
    check(
        "⑪ draft po_card 에 part_name·supplier_name·lead_days",
        bool(draft)
        and all(draft[0].get(k) is not None for k in ("part_name", "supplier_name", "lead_days")),
        f"{ {k: draft[0].get(k) for k in ('part_name', 'supplier_name', 'lead_days')} if draft else None }",
    )
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT requested_by, session_id FROM po_drafts WHERE po_id='PO-9001'"
    ).fetchone()
    con.close()
    check(
        "⑫ D37 신원 stamp (requested_by 채워짐)",
        row["requested_by"] == "tech-01" and row["session_id"] == "T9",
        f"requested_by={row['requested_by']}, session={row['session_id']}",
    )

    # ── ⑬ A5 — 모든 tool_call/tool_result/block 이 traces 에 남는다
    con = sqlite3.connect(db)
    n = con.execute("SELECT count(*) FROM traces WHERE session_id='T9'").fetchone()[0]
    types = {
        r[0] for r in con.execute("SELECT DISTINCT event_type FROM traces WHERE session_id='T9'")
    }
    con.close()
    persisted = sum(1 for e in ev if e.event in ("tool_call", "tool_result", "block"))
    check(
        "⑬ A5 발행 이벤트가 전부 traces 에 저장",
        n == persisted and "token" not in types,
        f"traces={n}, 발행={persisted}, types={sorted(types)}",
    )

    # ── ⑭ 도구 실패를 지식으로 메우지 않는다 (mcp 연결 실패)
    ev, _, _ = await drive(
        [
            [tu("lookup_error_code", model="iG5A", code="OHt")],
            [("text", "조회에 실패해 확인하지 못했습니다.")],
        ],
        {"lookup_error_code": {"status": "error", "reason": "unavailable", "message": "연결 실패"}},
        db=db,
        session="TA",
    )
    tr = [e.data for e in ev if e.event == "tool_result"]
    check(
        "⑭ 도구 실패 시 status:error 가 trace 에 그대로",
        bool(tr) and tr[0]["status"] == "error" and not blocks(ev, "citation"),
        f"status={tr[0]['status'] if tr else None}, citation={len(blocks(ev, 'citation'))}건",
    )

    # ── ⑭-b D54 — tool_result 에 근거 pages 를 항상 싣는다 (strict 인용 판정의 소스)
    # ok 결과는 lookup.manual_page ∪ rag.chunks[*].page, 실패 결과는 빈 리스트.
    # 키가 빠지면 평가가 degraded(발행=근거)로 내려가 "숫자를 지어낸" citation 을 못 잡는다.
    ev_pg, _, _ = await drive(
        [
            [tu("lookup_error_code", model="iG5A", code="OHt")],
            [tu("rag_search_manual", model="iG5A", query="점검")],
            [("text", "과열입니다.")],
        ],
        {"lookup_error_code": LOOKUP_OK, "rag_search_manual": RAG_OK},
        db=db,
        session="TPG",
    )
    tr_pg = [e.data for e in ev_pg if e.event == "tool_result"]
    check(
        "⑭-b D54 tool_result.pages — ok 는 근거 page, 실패는 빈 리스트",
        [d.get("pages") for d in tr_pg] == [[202], [204, 205, 206]]
        and tr[0].get("pages") == [],
        f"ok={[d.get('pages') for d in tr_pg]}, error={tr[0].get('pages')}",
    )

    # ── ⑮ 이력이 도구 결과의 **구조를 보존**하는가 (D76)
    #
    # 이전에는 프로즈 요약 + 화이트리스트(`PRESERVE_FIELDS`)였고, 목록에서 빠진 필드는
    # 그대로 사라졌다. 2026-08-05 평가에서 `related_parts` 가 그렇게 새어
    # 에이전트가 부품명을 지어냈고("S100 냉각팬" → not_found) 부품 특정 0/15 였다.
    # D76 이 블랙리스트로 뒤집었으므로, 이제는 **빠뜨려도 값이 사라지지 않는다**.
    from backend.agent.llm import anthropic_messages, gemini_contents
    from backend.agent.loop import HISTORY_MAX_ITEMS, _history_payload

    quotes = {
        "status": "ok",
        "suppliers": [
            {"supplier_id": "SUP-A", "lead_days": 3, "unit_price": 38000, "moq": 1},
            {"supplier_id": "SUP-B", "lead_days": 14, "unit_price": 29000, "moq": 10},
        ],
    }
    h = _history_payload("get_supplier_quotes", quotes)
    # 공급사 **2건** — [0] 만 건지던 버그를 잡는 픽스처 (S1 의 A사 vs B사 비교)
    check(
        "⑮ A2 발주 식별 필드가 구조 그대로 보존 (다건)",
        h["suppliers"] == quotes["suppliers"],
        f"suppliers={h['suppliers']}",
    )

    lk = {
        "status": "ok",
        "code": "OHT",
        "error_name": "냉각핀 과열",
        "severity": "fault",
        "related_parts": ["FAN-IG5-01"],
        "manual_page": 202,
    }
    check(
        "⑮-b D12 related_parts 품번이 이력에 보존됨",
        _history_payload("lookup_error_code", lk)["related_parts"] == ["FAN-IG5-01"],
        "리스트 원형 유지",
    )

    # 다건도 전부 살아야 한다 — GFT 처럼 케이블·모터 2건인 코드가 있다 (2026-08-05 검수)
    lk2 = {**lk, "code": "GFT", "related_parts": ["MTR-CBL-IG5", "MTR-3P-2K2"], "manual_page": 204}
    check(
        "⑮-c related_parts 다건 전부 보존",
        _history_payload("lookup_error_code", lk2)["related_parts"]
        == ["MTR-CBL-IG5", "MTR-3P-2K2"],
        "2건 유지",
    )

    # ── ⑮-d **화이트리스트에 없던 필드도 보존되는가** — D76 의 핵심
    #
    # 옛 구조에서 `meaning`·`actions` 는 PRESERVE_FIELDS 에 없어서 통째로 사라졌다.
    # 에러코드의 *의미*가 이력에서 없어지는 것이라 다음 턴의 판단이 근거를 잃는다.
    rich = {**lk, "meaning": "과열", "actions": ["냉각팬을 교체하십시오"], "제조사": "LS"}
    hr = _history_payload("lookup_error_code", rich)
    check(
        "⑮-d 목록에 없던 필드도 보존 (블랙리스트 뒤집기)",
        hr.get("meaning") == "과열"
        and hr.get("actions") == ["냉각팬을 교체하십시오"]
        and hr.get("제조사") == "LS",
        f"meaning={hr.get('meaning')} actions={hr.get('actions')} 제조사={hr.get('제조사')}",
    )

    # ── ⑮-e 블랙리스트는 **부피 큰 본문만** 자르고 식별자는 남긴다
    rag = {
        "status": "ok",
        "chunks": [{"page": 202, "section": "8.2", "text": "가" * 900}],
    }
    hc = _history_payload("rag_search_manual", rag)["chunks"][0]
    check(
        "⑮-e rag 본문만 절삭 · page·section 은 보존 · 절삭 사실 명시",
        hc["page"] == 202
        and hc["section"] == "8.2"
        and len(hc["text"]) < 900
        and "총 900자" in hc["text"],
        f"text={len(hc['text'])}자 tail={hc['text'][-12:]}",
    )

    # ── ⑮-f 리스트 상한 초과 시 **조용히 줄이지 않는다**
    many = {"status": "ok", "items": [{"part_no": f"P-{i}"} for i in range(HISTORY_MAX_ITEMS + 3)]}
    hm = _history_payload("search_inventory", many)["items"]
    check(
        "⑮-f 리스트 상한 초과분은 생략 표식을 남김",
        len(hm) == HISTORY_MAX_ITEMS + 1 and "생략" in str(hm[-1]),
        f"{len(hm)}개 · 마지막={hm[-1]}",
    )

    # ── ⑮-g 제공자 어댑터가 `role:"tool"` 을 네이티브 형식으로 변환하는가 (D76)
    msgs = [
        {"role": "user", "content": "OHt 에러"},
        {"role": "tool", "name": "lookup_error_code", "content": hr},
    ]
    g = gemini_contents(msgs)
    fr = g[1]["parts"][0].get("functionResponse", {})
    check(
        "⑮-g Gemini 는 functionResponse 파트로 변환 (평문 아님)",
        fr.get("name") == "lookup_error_code"
        and fr.get("response", {}).get("related_parts") == ["FAN-IG5-01"],
        f"name={fr.get('name')} keys={sorted(fr.get('response', {}))[:4]}",
    )
    a = anthropic_messages(msgs)
    check(
        "⑮-h Anthropic 은 JSON 텍스트로 변환 (tool_use 짝 없음 — 주석 참조)",
        a[1]["role"] == "user" and "FAN-IG5-01" in a[1]["content"],
        a[1]["content"][:60],
    )

    # ── ⑯-a D76-2 ⓑ — 도구 **원본** payload 가 traces.tool_payload 에 남는가
    #
    # SSE tool_result 는 요약본이라(D76 ⓓ) 그 안에 원본이 없다. 원본이 DB 에도 없으면
    # "도구가 정말 그 값을 줬는지"를 사후 검증할 방법이 사라진다 — 3차 평가가 그 상태였다.
    ev_tp, _, _ = await drive(
        [
            [tu("lookup_error_code", model="iG5A", code="OHt")],
            [("text", "과열입니다.")],
        ],
        {"lookup_error_code": LOOKUP_OK},
        db=db,
        session="TTP",
    )
    con = sqlite3.connect(db)
    tp = con.execute(
        "SELECT event_type, tool_payload FROM traces WHERE session_id='TTP' ORDER BY seq"
    ).fetchall()
    con.close()
    tp_map = {t: raw for t, raw in tp}
    saved_raw = json.loads(tp_map["tool_result"]) if tp_map.get("tool_result") else None
    sse_result = next(e.data for e in ev_tp if e.event == "tool_result")
    check(
        "⑯-a D76-2 도구 원본이 traces.tool_payload 에 저장 (SSE 는 요약본 그대로)",
        saved_raw == LOOKUP_OK
        and tp_map.get("tool_call") is None
        and "related_parts" not in sse_result,
        f"tool_payload keys={sorted(saved_raw) if saved_raw else None}, "
        f"sse keys={sorted(sse_result)}",
    )

    # ── ⑯-b ★ MQ-713a ③ — `("end", stop_reason)` 델타가 기록되는가
    #
    # 이 분기가 없어서 **MAX_TOKENS 로 잘린 응답과 스스로 끝낸 응답이 구분되지 않았다.**
    # 두 기전은 고칠 곳이 완전히 다르다(프롬프트 vs max_output_tokens) — 구분이 안 되면
    # 3차 분석처럼 "개선인지 요동인지 모른다"로 되돌아간다.
    #
    # ★ 음성 검증을 같이 건다: 정상 종료(STOP)는 truncated=0 이어야 한다. 잘림만 확인하면
    #   "무엇을 넣어도 잘림으로 세는" 계측을 통과시킨다.
    from backend.agent.loop import LLM_END_MARKER, is_truncated  # noqa: PLC0415

    async def end_lines(reason: object, session: str) -> list[str]:
        logger = logging.getLogger("backend.agent.loop")
        captured: list[str] = []

        class Grab(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                captured.append(record.getMessage())

        h = Grab()
        logger.addHandler(h)
        try:
            await drive(
                [[("text", "확인해 보겠습니다."), ("end", reason)]],
                {},
                db=db,
                session=session,
            )
        finally:
            logger.removeHandler(h)
        return [ln for ln in captured if ln.startswith(LLM_END_MARKER)]

    cut = await end_lines("FinishReason.MAX_TOKENS", "TEND1")
    ok_end = await end_lines("STOP", "TEND2")
    check(
        "⑯-b ★ end 델타의 stop reason 기록 (★ 음성: STOP → truncated=0)",
        len(cut) == 1
        and "reason=MAX_TOKENS truncated=1" in cut[0]
        and "session=TEND1" in cut[0]
        and len(ok_end) == 1
        and "reason=STOP truncated=0" in ok_end[0],
        f"잘림={cut}, 정상={ok_end}",
    )
    check(
        "⑯-c 제공자별 표기가 같은 판정으로 정규화 (Gemini enum · Anthropic · length)",
        [is_truncated(x) for x in ("FinishReason.MAX_TOKENS", "max_tokens", "length")] == [True] * 3
        and [is_truncated(x) for x in ("STOP", "end_turn", "tool_use", None)] == [False] * 4,
        "MAX_TOKENS/max_tokens/length → True · STOP/end_turn/tool_use/None → False",
    )

    # ── ⑯ A7 — 루프가 error_history 에 쓰지 않는다
    src = (ROOT / "backend" / "agent" / "loop.py").read_text(encoding="utf-8")
    check(
        "⑯ A7 루프가 error_history 에 쓰지 않음",
        "INSERT INTO error_history" not in src and "/errors" not in src,
        "쓰기 경로 없음",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("에이전트 루프 계약 검증 (ScriptedClient — API 키 불필요)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 없음 — data/seed.py 를 먼저 실행하세요")

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "loop.db"
        shutil.copy2(SOURCE_DB, db)
        os.environ["MAINTQ_DB"] = str(db)
        asyncio.run(run_all(db))

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 44))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 44))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — A1·A2·A5·A7·A8 · D30·D37·D45 확인")


if __name__ == "__main__":
    main()
