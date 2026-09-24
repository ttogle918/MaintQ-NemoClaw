# -*- coding: utf-8 -*-
"""온보딩 기종 안전 게이트 런타임 원천 검증 (MQ-1910 · D157 · D147 · 절대규칙 3).

`backend/agent/safety_source.resolve()` 가 안전 문구의 **유일한 런타임 원천**이다.
iG5A·S100 은 `prompts.SAFETY_BASELINE` 정적 상수(바이트 무변경), 그 밖의 `prompts.MODELS`
기종(HV600)은 `onboarding_safety_candidates` 의 `discharge_wait` 승인 행이 **정확히 1건**일
때만 값이 있다. 0건·2건+·DB 예외는 `None` 이고, 그때 `loop.py` 는 새 분기 없이 기존 차단
(안전 블록도 절차 서술도 없이 「근거 문서를 확인하지 못해 …」)으로 떨어져야 한다.

**API 키 불필요** — `agent_loop_contract` 의 가짜 LLM(`ScriptedClient`)·가짜 MCP 패턴을 따른다
(그 파일은 수정하지 않고 필요한 헬퍼를 여기 복제했다).

**격리 스키마에서만 돈다** (`data/pg_isolation`) — 승인 행을 공유 DB 에 만들지 않는다.
`backend.db.DB_PATH` 를 격리 DSN 으로 갈아끼워 `resolve()`·`TraceWriter`·`_model_for` 가
전부 그 스키마를 본다.

실행:  DATABASE_URL=... uv run python spikes/onboarding_safety_gate.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from data import dbcompat, pg_isolation  # noqa: E402

results: list[tuple[str, bool, str]] = []

BLOCK_TOKEN = "근거 문서를 확인하지 못해"
DANGER_TEXT = "커버를 열고 냉각팬을 분리하십시오."
DANGER_MARK = "커버를 열"
#: 승인 문구 — 원문 대기시간(10분)을 그대로 담는다(safety-guardrail 규칙 3 형태). 합성 픽스처.
APPROVED_TEXT = (
    "전원을 차단한 뒤 10분 이상 기다리고, 테스터로 직류 전압이 방전됐는지 확인한 후 "
    "커버를 여십시오. (HV600 매뉴얼 기준)"
)
APPROVED_PAGE = 17


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


# ── 가짜 MCP / 이벤트 헬퍼 (agent_loop_contract 와 같은 모양) ─────────────────────────────


class FakeMcp:
    def __init__(self, responses: dict[str, dict]) -> None:
        self.responses = responses
        self.call_log: list[str] = []

    async def list_tools(self) -> list[dict]:
        return [{"name": n, "description": n, "inputSchema": {}} for n in self.responses]

    async def call(self, tool: str, args: dict | None = None, *, timeout=None) -> dict:
        self.call_log.append(tool)
        return self.responses.get(tool, {"status": "error", "reason": "unknown_tool"})


def blocks(events, btype: str) -> list[dict]:
    return [e.data["data"] for e in events if e.event == "block" and e.data.get("type") == btype]


def token_text(events) -> str:
    return "".join(str(e.data.get("text", "")) for e in events if e.event == "token")


def idx(events, pred) -> int:
    return next((i for i, e in enumerate(events) if pred(e)), -1)


def rag_ok(page: int) -> dict:
    return {
        "status": "ok",
        "chunks": [{"text": "냉각팬 점검 절차", "page": page, "section": "Troubleshooting · Fault"}],
    }


class ResolveCounter:
    """`safety_source.resolve` 를 감싸 호출 수를 센다 — 앵커(게이트가 실제로 원천을 봤는가)."""

    def __init__(self) -> None:
        from backend.agent import safety_source

        self.mod = safety_source
        self.orig = safety_source.resolve
        self.calls: list[str | None] = []

        def wrapped(model):
            self.calls.append(model)
            return self.orig(model)

        safety_source.resolve = wrapped

    def reset(self) -> None:
        self.calls.clear()

    def restore(self) -> None:
        self.mod.resolve = self.orig


async def drive(script, responses, *, db: str, session: str, equipment=None):
    from backend.agent.llm import ScriptedClient
    from backend.agent.loop import SessionStore, run_turn
    from backend.agent.trace import TraceWriter

    fake = FakeMcp(responses)
    llm = ScriptedClient(script)
    events = []
    async for ev in run_turn(
        session_id=session,
        message="HV600 냉각팬 점검 방법",
        equipment_id=equipment,
        user_id="tech-01",
        llm=llm,
        client=fake,  # type: ignore[arg-type]
        trace=TraceWriter(session, db_path=db),
        store=SessionStore(),
    ):
        events.append(ev)
    return events, fake, llm


def _tu(name, **kw):
    from backend.agent.llm import ToolUse

    return ("tool_use", ToolUse(id="t1", name=name, input=kw))


def hv600_script():
    return [[_tu("rag_search_manual", model="HV600", query="냉각팬")], [("text", DANGER_TEXT)]]


# ── DB 픽스처 (격리 스키마 전용) ────────────────────────────────────────────────────────


def _raw(dsn: str):
    import psycopg

    return psycopg.connect(dsn)


def seed_batch(dsn: str) -> int:
    with _raw(dsn) as con:
        row = con.execute(
            "INSERT INTO onboarding_batches (model, manual_id, pdf_sha256, candidates_sha256, loaded_by)"
            " VALUES ('HV600', 'hv600-iopm', 'spike-pdf', 'spike-cand', 'spike')"
            " RETURNING batch_id"
        ).fetchone()
        # 승인 전 상태를 현실적으로: staged discharge_wait 후보 1건(승인 아님 → 게이트에 안 잡혀야)
        con.execute(
            "INSERT INTO onboarding_safety_candidates (batch_id, ordinal, model, page, kind, quote_en,"
            " wait_minutes_in_text) VALUES (%s, 1, 'HV600', %s, 'discharge_wait',"
            " 'Wait at least 10 minutes after power off.', 10)",
            (row[0], APPROVED_PAGE),
        )
        con.commit()
    return row[0]


def approve(dsn: str, batch_id: int, ordinal: int, text: str, page: int) -> None:
    """승인 행 직접 INSERT — CHECK(네 컬럼 모두) 를 만족하는 형태."""
    with _raw(dsn) as con:
        con.execute(
            "INSERT INTO onboarding_safety_candidates (batch_id, ordinal, model, page, kind, quote_en,"
            " wait_minutes_in_text, state, approved_text, approved_by, approved_at, text_reviewed_at)"
            " VALUES (%s, %s, 'HV600', %s, 'discharge_wait', 'Wait at least 10 minutes.', 10,"
            " 'approved', %s, 'mgr-01', now(), now())",
            (batch_id, ordinal, page, text),
        )
        con.commit()


# ── 케이스 ────────────────────────────────────────────────────────────────────────────


def assert_blocked(tag: str, ev, llm, counter: ResolveCounter) -> None:
    """ⓐ·ⓒ 공통 — 셋 중 하나라도 어긋나면 FAIL(「둘 중 하나만 나오면 실패」)."""
    toks = token_text(ev)
    saf = blocks(ev, "safety")
    has_block_token = BLOCK_TOKEN in toks
    no_block = not saf
    no_procedure = DANGER_MARK not in toks
    check(
        f"{tag} 차단 토큰 있음 · safety 블록 없음 · 절차 문장 없음 (3축 동시)",
        has_block_token and no_block and no_procedure,
        f"차단토큰={has_block_token} · safety={len(saf)}건 · 절차노출={not no_procedure}",
    )
    check(
        f"{tag} 앵커 — resolve 호출≥1(HV600) · 가짜 LLM 소비",
        "HV600" in counter.calls and llm.calls >= 2,
        f"resolve 호출={counter.calls} · llm.calls={llm.calls}",
    )


async def run_all(dsn: str) -> None:
    from backend import manifest
    from backend.agent import prompts, safety_source

    counter = ResolveCounter()
    try:
        batch_id = seed_batch(dsn)

        # ── ⓐ 승인 전 (D147 핵심) — staged 후보는 있지만 승인 0건
        counter.reset()
        direct = safety_source.resolve("HV600")
        check("ⓐ-0 resolve('HV600') 승인 0건 → None", direct is None, f"{direct!r}")
        counter.reset()
        ev, fake, llm = await drive(hv600_script(), {"rag_search_manual": rag_ok(45)}, db=dsn, session="SG-A")
        check("ⓐ-1 전제 — 도구 결과에 페이지 있음(rag 호출됨)", fake.call_log == ["rag_search_manual"],
              f"calls={fake.call_log}")
        assert_blocked("ⓐ", ev, llm, counter)

        # ── ⓑ 승인 후 — CHECK 만족 승인 행 1건
        approve(dsn, batch_id, 2, APPROVED_TEXT, APPROVED_PAGE)
        entry = safety_source.resolve("HV600")
        check(
            "ⓑ-0 resolve('HV600') → source=onboarding · text·page·두 날짜",
            entry is not None and entry.source == "onboarding" and entry.text == APPROVED_TEXT
            and entry.page == APPROVED_PAGE and bool(entry.approved_at) and bool(entry.text_reviewed_at)
            and entry.title == prompts.SAFETY_BASELINE["title"],
            f"{entry!r}"[:160],
        )
        counter.reset()
        ev, fake, llm = await drive(hv600_script(), {"rag_search_manual": rag_ok(45)}, db=dsn, session="SG-B")
        saf = blocks(ev, "safety")
        cit = saf[0].get("citation", {}) if saf else {}
        check("ⓑ-1 safety 블록 text == approved_text (바이트 동일)",
              len(saf) == 1 and saf[0].get("text") == APPROVED_TEXT, f"safety={len(saf)}건")
        check(
            "ⓑ-2 citation 모델 HV600 · page == cand.page (도구 페이지 45 아님)",
            cit.get("page") == APPROVED_PAGE
            and str(cit.get("label", "")).startswith(manifest.manual_label("HV600") + " "),
            f"citation={cit}",
        )
        i_saf = idx(ev, lambda e: e.event == "block" and e.data.get("type") == "safety")
        i_danger = idx(ev, lambda e: e.event == "token" and DANGER_MARK in str(e.data.get("text", "")))
        check("ⓑ-3 절차 문장이 safety 블록 뒤에 따라 나옴 · 차단 토큰 없음",
              0 <= i_saf < i_danger and BLOCK_TOKEN not in token_text(ev),
              f"safety@{i_saf} · 절차@{i_danger}")
        check("ⓑ 앵커 — resolve 호출≥1 · 가짜 LLM 소비",
              "HV600" in counter.calls and llm.calls >= 2, f"resolve={counter.calls} · llm.calls={llm.calls}")

        # ── ⓒ 승인 2건(직접 SQL) → 모호 → fail closed, ⓐ 와 같은 차단
        approve(dsn, batch_id, 3, APPROVED_TEXT.replace("10분", "15분"), APPROVED_PAGE + 1)
        direct = safety_source.resolve("HV600")
        check("ⓒ-0 resolve('HV600') 승인 2건 → None (최신 자동 채택 없음, D157 ⓑ 기각)",
              direct is None, f"{direct!r}")
        counter.reset()
        ev, fake, llm = await drive(hv600_script(), {"rag_search_manual": rag_ok(45)}, db=dsn, session="SG-C")
        assert_blocked("ⓒ", ev, llm, counter)

        # ── ⓓ iG5A — 정적 상수 경로, 출력 바이트 무변경
        counter.reset()
        ev, fake, llm = await drive(
            [[_tu("rag_search_manual", model="iG5A", query="냉각팬")], [("text", DANGER_TEXT)]],
            {"rag_search_manual": rag_ok(204)},
            db=dsn,
            session="SG-D",
            equipment="INV-L1-01",
        )
        saf = blocks(ev, "safety")
        cit = saf[0].get("citation", {}) if saf else {}
        check(
            "ⓓ-1 iG5A 블록 text 가 SAFETY_BASELINE['text'] 와 바이트 동일 · title 동일",
            len(saf) == 1
            and saf[0].get("text", "").encode("utf-8") == prompts.SAFETY_BASELINE["text"].encode("utf-8")
            and saf[0].get("title") == prompts.SAFETY_BASELINE["title"],
            f"safety={len(saf)}건",
        )
        check("ⓓ-2 iG5A citation page 4 (도구 페이지 204 아님)",
              cit.get("page") == 4 == prompts.SAFETY_BASELINE["pages"]["iG5A"], f"citation={cit}")
        check("ⓓ 앵커 — resolve 호출≥1(iG5A) · 가짜 LLM 소비",
              "iG5A" in counter.calls and llm.calls >= 2, f"resolve={counter.calls} · llm.calls={llm.calls}")
        s100 = safety_source.resolve("S100")
        check("ⓓ-3 S100 → static · page 2 · text 동일",
              s100 is not None and s100.source == "static" and s100.page == 2
              and s100.text == prompts.SAFETY_BASELINE["text"], f"{s100!r}"[:120])

        # ── ⓔ DB 층 — state='approved' 인데 text_reviewed_at NULL → CheckViolation
        import psycopg

        raised = None
        with _raw(dsn) as con:
            try:
                con.execute(
                    "INSERT INTO onboarding_safety_candidates (batch_id, ordinal, model, page, kind,"
                    " quote_en, state, approved_text, approved_by, approved_at, text_reviewed_at)"
                    " VALUES (%s, 99, 'HV600', 3, 'discharge_wait', 'q', 'approved', 'x', 'mgr-01',"
                    " now(), NULL)",
                    (batch_id,),
                )
                con.commit()
            except psycopg.errors.CheckViolation as e:
                raised = e
                con.rollback()
        with _raw(dsn) as con:
            n99 = con.execute(
                "SELECT count(*) FROM onboarding_safety_candidates WHERE batch_id=%s AND ordinal=99",
                (batch_id,),
            ).fetchone()[0]
        check("ⓔ approved + text_reviewed_at NULL INSERT → CheckViolation · 행 0",
              raised is not None and n99 == 0, f"예외={type(raised).__name__ if raised else None} · 행={n99}")

        # ── 보조: fail-closed 경계
        check("ⓕ-1 IE5 → None (정적에도 DB 에도 없음, D109 ⓐ)", safety_source.resolve("IE5") is None, "")
        check("ⓕ-2 빈 모델·None·미등록 기종 → None",
              safety_source.resolve("") is None and safety_source.resolve(None) is None
              and safety_source.resolve("XYZ") is None, "")
        orig_connect = safety_source.db.connect

        def boom(*a, **kw):
            raise RuntimeError("spike: DB down")

        safety_source.db.connect = boom
        try:
            down = safety_source.resolve("HV600")
            ig5a_down = safety_source.resolve("iG5A")
        finally:
            safety_source.db.connect = orig_connect
        check("ⓕ-3 DB 예외 → HV600 None (fail closed) · iG5A 정적 경로는 DB 무관",
              down is None and ig5a_down is not None and ig5a_down.source == "static",
              f"HV600={down!r} · iG5A={getattr(ig5a_down, 'source', None)}")

        # ── ⓕ-4 방어 이중화 (D109 ⓐ) — 어떤 경로로든 IE5 승인 행이 DB 에 생겨도(승인 API 는
        #    422 로 막는다) resolve 는 DB 를 조회하지 않고 None. 서비스 우회 직접 INSERT 로 심는다.
        with _raw(dsn) as con:
            ie5_batch = con.execute(
                "INSERT INTO onboarding_batches (model, manual_id, pdf_sha256, candidates_sha256, loaded_by)"
                " VALUES ('IE5', 'ie5-spike', 'spike-pdf', 'spike-cand-ie5', 'spike') RETURNING batch_id"
            ).fetchone()[0]
            con.execute(
                "INSERT INTO onboarding_safety_candidates (batch_id, ordinal, model, page, kind, quote_en,"
                " wait_minutes_in_text, state, approved_text, approved_by, approved_at, text_reviewed_at)"
                " VALUES (%s, 0, 'IE5', 9, 'discharge_wait', 'Wait at least 10 minutes.', 10,"
                " 'approved', '가상 IE5 문안 — 10분 이상 대기', 'mgr-01', now(), now())",
                (ie5_batch,),
            )
            con.commit()
            n_ie5 = con.execute(
                "SELECT count(*) FROM onboarding_safety_candidates"
                " WHERE model='IE5' AND kind='discharge_wait' AND state='approved'"
            ).fetchone()[0]
        db_calls: list[str] = []

        def counting_connect(*a, **kw):
            db_calls.append("connect")
            return orig_connect(*a, **kw)

        safety_source.db.connect = counting_connect
        try:
            ie5 = safety_source.resolve("IE5")
            ie5_calls = len(db_calls)
            safety_source.resolve("HV600")  # 양성 앵커 — 같은 계측기로 HV600 은 DB 를 본다
            hv_calls = len(db_calls) - ie5_calls
        finally:
            safety_source.db.connect = orig_connect
        check("ⓕ-4 IE5 승인 행이 DB 에 1건 있어도 resolve('IE5') → None · DB 조회 0회"
              " (앵커: IE5 승인 행 1 · 같은 계측기로 HV600 조회 ≥1회)",
              ie5 is None and ie5_calls == 0 and n_ie5 == 1 and hv_calls >= 1,
              f"IE5={ie5!r} · IE5 조회={ie5_calls}회 · IE5 승인 행={n_ie5} · HV600 조회={hv_calls}회")

        # ── ⓖ 캐시 회귀 — 모델을 모를 때의 None 을 턴 끝까지 붙들지 않는다.
        #    장비 컨텍스트 없이 도구 전에 위험 서술이 먼저 나오면 그 문장은 차단되고,
        #    도구 호출로 model(iG5A)이 관측된 뒤의 위험 서술에는 안전 블록이 붙어야 한다
        #    (D157 이전 `safety_page()` 는 매번 새로 계산했다 — 그 동작 보존).
        counter.reset()
        ev, fake, llm = await drive(
            [
                [("text", "커버를 열어 보겠습니다."), _tu("rag_search_manual", model="iG5A", query="팬")],
                [("text", DANGER_TEXT)],
            ],
            {"rag_search_manual": rag_ok(204)},
            db=dsn,
            session="SG-G",
        )
        saf = blocks(ev, "safety")
        check("ⓖ 모델 관측 전 차단 → 관측 후 iG5A 안전 블록 1건 (빈 모델 None 캐시 안 함)",
              len(saf) == 1 and saf[0].get("citation", {}).get("page") == 4 and llm.calls >= 2,
              f"safety={len(saf)}건 · resolve={counter.calls} · 차단토큰={BLOCK_TOKEN in token_text(ev)}")
    finally:
        counter.restore()


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    print("온보딩 안전 게이트 런타임 원천 검증 (MQ-1910 · D157) — API 키 불필요\n")
    if not dbcompat.USE_POSTGRES:
        raise SystemExit("[중단] DATABASE_URL(Postgres) 필요 — 격리 스키마에서만 돈다")

    import backend.db as backend_db  # noqa: PLC0415

    schema, dsn = pg_isolation.create_isolated_schema("safety_gate")
    prev = backend_db.DB_PATH
    backend_db.DB_PATH = dsn  # resolve()·_model_for() 는 인자 없이 connect() 한다
    try:
        asyncio.run(run_all(dsn))
    finally:
        backend_db.DB_PATH = prev
        pg_isolation.drop_isolated_schema(schema)

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 44))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 44))
    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\n통과 ({len(results)}건) — D157 · D147 · 절대규칙 3")


if __name__ == "__main__":
    main()
