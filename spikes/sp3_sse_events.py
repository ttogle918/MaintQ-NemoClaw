# -*- coding: utf-8 -*-
"""SP3 — FastAPI SSE 이벤트 4종 스트리밍 검증 (docs/09_RUNTIME.md §4).

검증 질문:
  token / tool_call / tool_result / block 이 프론트에서 구분 수신되고,
  block 이 token 스트림 "중간"에 삽입 가능한가? (D22)

실제 uvicorn 프로세스를 띄우고 HTTP 로 붙는다 — TestClient in-process 가 아니라,
네트워크를 타는 진짜 스트리밍인지(버퍼링에 갇히지 않는지) 봐야 하기 때문.

MQ-308 이후로 이 스파이크는 **`?replay=s1` 경로**를 본다. 재생본이지만 `TraceWriter` 를
거치므로 A5(발행=저장)가 런타임에서 성립하는지도 여기서 함께 검증된다 —
스트림이 끝난 뒤 `GET /api/chat/{id}/trace` 의 payload 가 SSE `data` 와 같아야 한다 (D30).

**임시 DB 사본에서 돌린다** — 재생이 `traces` 에 실제로 INSERT 하므로 `MAINTQ_DB` 를
자식 프로세스에 명시 전달해 원본을 오염시키지 않는다.

실행:  uv run python spikes/sp3_sse_events.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agent.prompts import SAFETY_BASELINE  # noqa: E402 — sys.path 설정 후여야 한다

SOURCE_DB = ROOT / "data" / "maintq.db"
PORT = 8083
BASE = f"http://127.0.0.1:{PORT}"

#: 재생 지연. 도구 "실행" 시간은 이 값의 3배(`chat.TOOL_DELAY_FACTOR`)다.
DELAY = 0.02
TOOL_EXEC = DELAY * 3
SESSION = "SP3"
# X-User 는 ASCII 사용자 ID — 한글 표시명은 HTTP 헤더에 못 넣는다 (D36)
TECH = {"X-Role": "technician", "X-User": "tech-01"}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))


async def wait_ready(timeout: float = 30.0) -> bool:
    """서버 준비 대기.

    **짧은 타임아웃으로 빠르게 폴링하지 않는다.** uvicorn 은 앱 startup 이 끝나기 전에
    이미 소켓을 바인딩하므로, 그 창에 연결을 만들었다가 중단하면 Windows Proactor 의
    accept 루프가 `OSError [WinError 64]` 로 깨지고 서버가 영영 응답하지 않는다
    (lifespan 이 추가돼 startup 창이 길어지면서 실제로 재현됐다).
    요청은 **적게, 타임아웃은 넉넉히** — startup 이 끝날 때까지 uvicorn 이 요청을 큐에 물고 있는다.
    """
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            async with httpx.AsyncClient(timeout=timeout / 3) as c:
                r = await c.get(f"{BASE}/health")
                if r.status_code == 200:
                    return True
        except Exception:  # noqa: BLE001 — 아직 바인딩 전이면 연결 자체가 거부된다
            await asyncio.sleep(min(1.0 * attempt, 3.0))
    return False


def _parse(buf: str, events: list, t0: float) -> str:
    """수신 버퍼에서 완성된 SSE 프레임을 뽑아 events 에 적재하고 잔여 버퍼를 돌려준다."""
    while "\n\n" in buf:
        frame, buf = buf.split("\n\n", 1)
        ev, data = None, None
        for line in frame.split("\n"):
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if ev:
            events.append((time.monotonic() - t0, ev, data or {}))
    return buf


async def collect(
    session: str = SESSION, *, verify_headers: bool = False
) -> list[tuple[float, str, dict]]:
    """SSE 프레임을 (수신시각, event, data) 로 모은다. 도착 순서·간격이 검증 대상이다."""
    events: list[tuple[float, str, dict]] = []
    buf = ""
    t0 = time.monotonic()

    async with httpx.AsyncClient(timeout=30.0) as c:
        async with c.stream(
            "POST",
            f"{BASE}/api/chat?replay=s1&delay={DELAY}",
            json={"session_id": session, "message": "iG5A 인버터에 OHt 에러 떴어"},
            headers=TECH,
        ) as resp:
            if verify_headers:  # 첫 호출에서만 계약 헤더를 본다
                check(
                    "① 200 + text/event-stream",
                    resp.status_code == 200
                    and resp.headers.get("content-type", "").startswith("text/event-stream"),
                    f"{resp.status_code} {resp.headers.get('content-type')}",
                )
            async for chunk in resp.aiter_text():
                buf = _parse(buf + chunk, events, t0)
    return events


async def get_trace(session: str = SESSION) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{BASE}/api/chat/{session}/trace", headers=TECH)
        return r.json()


async def run() -> None:
    events = await collect(verify_headers=True)
    kinds = [e for _, e, _ in events]

    check("② 이벤트 수신", len(events) > 0, f"{len(events)}개 프레임")

    check(
        "③ 4종 전부 구분 수신 (D14·D22)",
        {"token", "tool_call", "tool_result", "block"} <= set(kinds),
        f"{ {k: kinds.count(k) for k in dict.fromkeys(kinds)} }",
    )

    check(
        "④ 4종 외 이벤트 없음 (고정 규격)",
        set(kinds) <= {"token", "tool_call", "tool_result", "block"},
        f"수신 종류: {sorted(set(kinds))}",
    )

    # A1 — tool_call 이 같은 도구의 tool_result 보다 항상 먼저
    order_ok = True
    for i, (_, ev, data) in enumerate(events):
        if ev == "tool_result":
            prior = [d.get("tool") for _, e2, d in events[:i] if e2 == "tool_call"]
            if data.get("tool") not in prior:
                order_ok = False
    check("⑤ A1 tool_call 이 tool_result 보다 먼저", order_ok, "모든 쌍에서 성립")

    # ★ SP3 의 핵심 — block 이 token 스트림 "중간"에 들어오는가
    idx_block = [i for i, k in enumerate(kinds) if k == "block"]
    idx_token = [i for i, k in enumerate(kinds) if k == "token"]
    mid = [i for i in idx_block if any(t < i for t in idx_token) and any(t > i for t in idx_token)]
    check(
        "⑥ block 이 token 중간에 삽입 (D22 핵심)",
        bool(mid),
        f"token {min(idx_token)}~{max(idx_token)} 사이에 block {mid}",
    )

    # 안전 경고가 위험 절차 서술보다 먼저 도착하는가 (safety-guardrail 의 실질 요구)
    i_safety = next(
        (i for i, (_, e, d) in enumerate(events) if e == "block" and d.get("type") == "safety"),
        None,
    )
    danger_words = ("커버를 열", "분리")
    i_danger = next(
        (
            i
            for i, (_, e, d) in enumerate(events)
            if e == "token" and any(w in d.get("text", "") for w in danger_words)
        ),
        None,
    )
    check(
        "⑦ 안전 경고가 위험 절차 서술보다 먼저",
        i_safety is not None and i_danger is not None and i_safety < i_danger,
        f"safety={i_safety}, 위험 서술 시작={i_danger}",
    )

    # ── ⑦-b 안전 문구의 **근거 페이지**가 승인된 출처를 가리키는가 (절대규칙 3)
    #
    # ⑦ 은 순서만, ⑨ 는 블록 타입만, ⑪ 은 **독립 citation 블록**의 키만 본다.
    # 셋 다 통과하면서 safety 블록이 엉뚱한 페이지를 근거로 다는 일이 실제로 있었다
    # (Stage 2 BLOCKER 1 — rag 결과 p.202/204 를 승인 문구의 근거로 붙였다).
    # 승인된 출처는 `SAFETY_BASELINE["pages"]` 뿐이므로 **그 상수와 대조**한다 —
    # 도구 결과에서 페이지를 끌어오는 회귀가 나면 여기서 깨진다.
    safety_data = (events[i_safety][2] if i_safety is not None else {}).get("data", {})
    safety_cite = safety_data.get("citation") or {}
    expected_page = SAFETY_BASELINE["pages"]["iG5A"]
    check(
        "⑦-b 안전 문구 인용이 승인된 매뉴얼 페이지 (절대규칙 3)",
        safety_cite.get("page") == expected_page
        and {"page", "print_page", "label"} <= set(safety_cite),
        f"citation={safety_cite} (기대 page={expected_page})",
    )

    # 실시간성 — 버퍼링되면 전 프레임이 스트림 끝에 "한꺼번에" 도착한다.
    # 접속 지연(ts[0])은 머신 부하에 따라 흔들리므로 판정에 쓰지 않는다.
    # 대신 프레임들이 시간축에 흩어져 있는지를 직접 본다.
    ts = [t for t, _, _ in events]
    span = ts[-1] - ts[0]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    spread = sum(1 for g in gaps if g > 0.005)  # 유의미한 간격을 둔 프레임 수
    check(
        "⑧ 점진 전송 (버퍼링 아님)",
        span > 0.15 and spread >= len(gaps) // 3,
        f"프레임 분산 {span:.2f}s, 간격>5ms {spread}/{len(gaps)}",
    )

    # D22 block 타입 3종 + D35 variant
    btypes = {d.get("type") for _, e, d in events if e == "block"}
    check(
        "⑨ block 타입 (safety·citation·po_card)",
        {"safety", "citation", "po_card"} <= btypes,
        f"{sorted(btypes)}",
    )
    po = next(
        (d for _, e, d in events if e == "block" and d.get("type") == "po_card"),
        {},
    )
    check(
        "⑩ D35 po_card variant",
        po.get("data", {}).get("variant") == "draft",
        f"variant={po.get('data', {}).get('variant')!r}",
    )

    # D32 — citation 은 물리/인쇄 페이지를 함께 싣는다
    cite = next((d for _, e, d in events if e == "block" and d.get("type") == "citation"), {}).get(
        "data", {}
    )
    check(
        "⑪ D32 citation payload",
        {"page", "print_page", "label"} <= set(cite),
        f"{cite}",
    )

    # ── ⑫ A1 강화 (reviewer C-6) — **순서가 아니라 "도구 실행 시점"** 을 본다.
    #
    # ⑤ 는 프레임 순서만 보므로, 도구를 다 실행한 뒤 tool_call·tool_result 를 몰아서
    # 흘려도 통과한다. 그러면 trace 패널의 스피너(A1 의 존재 이유)가 성립하지 않는다.
    # 재생본의 도구 실행 시간은 TOOL_EXEC 이므로, tool_call 이 실행 **직전**에
    # 이미 나갔다면 두 프레임의 도착 간격이 그 실행 시간만큼 벌어져 있어야 한다.
    # 몰아서 보냈다면 간격이 0 에 수렴한다 — 이건 순서로는 구분할 수 없다.
    pending: dict[str, list[float]] = {}
    pairs: list[tuple[str, float]] = []
    for t, ev, d in events:
        tool = d.get("tool")
        if ev == "tool_call":
            pending.setdefault(tool, []).append(t)  # FIFO — 워커가 큐를 직렬 소비 (D42)
        elif ev == "tool_result" and pending.get(tool):
            pairs.append((tool, t - pending[tool].pop(0)))
    floor = TOOL_EXEC * 0.5
    slow = [(n, round(g, 3)) for n, g in pairs if g < floor]
    check(
        "⑫ A1 강화 — 도구 실행 전에 tool_call 이 이미 나갔다 (몰아쓰기 아님)",
        bool(pairs) and not slow,
        f"{len(pairs)}쌍, 최소 간격 {min((g for _, g in pairs), default=0):.3f}s ≥ {floor:.3f}s",
    )

    # ── ⑬ A5 런타임 성립 — replay 가 traces 에 남고, payload 가 SSE data 와 동일 (D21·D30)
    tr = await get_trace()
    persisted = [(e["event"], e["data"]) for e in tr["events"]]
    streamed = [(ev, d) for _, ev, d in events if ev != "token"]  # token 은 저장 안 함 (D41)
    types = {e["event"] for e in tr["events"]}
    check(
        "⑬ A5 replay 가 traces 에 저장 (payload == SSE data)",
        {"tool_call", "tool_result", "block"} <= types and persisted == streamed,
        f"traces {tr['count']}행 {sorted(types)} · SSE 비-token {len(streamed)}건",
    )

    # ── ⑭ 같은 session_id 로 두 번째 턴 → seq 가 이어진다 (D41 UNIQUE·화면 B 타임라인)
    first_seqs = [e["seq"] for e in tr["events"]]
    await collect()
    tr2 = await get_trace()
    seqs = [e["seq"] for e in tr2["events"]]
    check(
        "⑭ 같은 session_id 두 번째 호출 → seq 이어짐",
        len(tr2["events"]) == 2 * tr["count"]
        and seqs == list(range(1, len(seqs) + 1))
        and seqs[: len(first_seqs)] == first_seqs,
        f"1턴 {tr['count']}행 → 2턴 누적 {tr2['count']}행, seq {seqs[0]}~{seqs[-1]}",
    )

    # ── ⑮ D36 회귀 — 한글 표시명을 헤더에 넣으면 400 (stamp_identity 로 흘러가기 전에 막는다)
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            f"{BASE}/api/chat?replay=s1&delay=0",
            json={"session_id": "SP3-D36", "message": "x"},
            # 한글은 latin-1 이 아니라 헤더에 문자열로 못 싣는다 → 바이트로 직접 밀어 넣는다
            headers={"X-Role": "technician", "X-User": "김OO".encode()},
        )
    check(
        "⑮ D36 — X-User 에 한글 → 400 (DB 로 새지 않는다)",
        r.status_code == 400,
        f"{r.status_code} {str(r.json().get('detail'))[:40]}",
    )
    leaked = await get_trace("SP3-D36")
    check(
        "⑯ D36 위반 요청은 traces 에 한 행도 남기지 않는다",
        leaked["count"] == 0,
        f"count={leaked['count']}",
    )

    # ── ⑰ 스트리밍 조기 종료 회귀 — 중간에 끊고 곧바로 재요청해도 라우터가 살아 있는가
    #
    # **이 검사의 사정거리를 과장하지 말 것.** replay 경로만 타므로 MCP 를 건드리지 않고,
    # 따라서 "`_agent_stream` 안에서 stdio 세션을 다시 열었다"(D42 위반)는 여기서 잡히지
    # 않는다 — 그건 `agent_loop_contract` 의 취소 회귀가 담당한다.
    # 여기서 보는 건 SSE 제너레이터가 조기 종료를 삼키거나 서버를 망가뜨리지 않는가다.
    aborted = 0
    async with httpx.AsyncClient(timeout=30.0) as c:
        async with c.stream(
            "POST",
            f"{BASE}/api/chat?replay=s1&delay={DELAY}",
            json={"session_id": "SP3-ABORT", "message": "중간에 끊는다"},
            headers=TECH,
        ) as resp:
            async for _chunk in resp.aiter_raw():
                aborted += 1
                if aborted >= 2:
                    break  # 컨텍스트를 빠져나가며 연결을 닫는다 = 클라이언트 조기 종료

    after = await collect("SP3-AFTER-ABORT")
    check(
        "⑰ 조기 종료 직후 재요청도 200 + 정상 이벤트",
        len(after) == len(events)
        and {"token", "tool_call", "tool_result", "block"} <= {e for _, e, _ in after},
        f"끊기 전 {aborted}청크 수신 → 재요청 {len(after)}프레임",
    )

    # ── ⑲ 도구 서버가 죽었으면 **지식으로 메우지 않는다** (09_RUNTIME §3 · 절대규칙 6)
    #
    # 이 스파이크는 `MAINTQ_MCP_AUTOSTART=0` 으로 뜨므로 `app.state.mcp` 는 존재하되
    # `ready=False` 다 — 실제 "MCP 기동 실패" 와 같은 상태다. 여기서 `?replay` 없이
    # 요청하면 실 에이전트 경로로 들어간다.
    #
    # 가드가 `mcp is None` 만 보던 시절엔 이 조건이 **거짓**이라 그대로 `run_turn` 으로
    # 진입했고, `list_tools()` 가 `[]` 를 주는 채로 LLM 이 근거 없이 진단을 서술했다.
    # 되돌리면 첫 토큰이 LLM 설정 안내(키 없음)로 바뀌므로 아래 검사가 깨진다.
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            f"{BASE}/api/chat",
            json={"session_id": "SP3-NOMCP", "message": "iG5A 인버터에 OHt 에러 떴어"},
            headers=TECH,
        )
    body = r.text
    first_token = next(
        (
            json.loads(line[5:].strip()).get("text", "")
            for line in body.split("\n")
            if line.startswith("data:")
        ),
        "",
    )
    nomcp = await get_trace("SP3-NOMCP")
    check(
        "⑲ MCP ready=False → 도구 없이 진단하지 않는다 (09_RUNTIME §3)",
        r.status_code == 200 and "도구 서버에 연결할 수 없습니다" in first_token,
        f"{r.status_code} · 첫 토큰 {first_token[:40]!r}",
    )
    # ⑳ 은 **키가 있을 때만** 독립적인 검사력을 갖는다. 키가 없으면 가드를 되돌려도
    # 바로 다음 `get_client()` 가 막아서 어차피 도구 이벤트가 안 나온다(공허하게 통과).
    # 실제 검사력은 ⑲ 에 있다 — 되돌리면 첫 토큰이 LLM 설정 안내로 바뀌며 FAIL 한다(실측).
    check(
        "⑳ 그 턴은 도구 이벤트를 한 건도 남기지 않는다",
        nomcp["count"] == 0 and "tool_call" not in body,
        f"traces={nomcp['count']}행, tool_call 프레임 {body.count('event: tool_call')}건",
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("SP3 — FastAPI SSE 이벤트 4종 + block 중간 삽입 (실제 uvicorn 프로세스)\n")
    if not SOURCE_DB.exists():
        raise SystemExit(f"[중단] {SOURCE_DB} 가 없습니다 — data/seed.py 를 먼저 실행하세요")

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "sp3.db"
        shutil.copy2(SOURCE_DB, db)

        # SP3 는 replay 경로만 쓴다 — MCP 를 띄울 이유가 없다.
        # lifespan 이 매번 stdio 서버를 스폰하면 기동이 느려지고, 연속 실행 시
        # 포트·자식 프로세스가 물려 간헐 실패한다 (실제로 한 번 겪었다).
        # MAINTQ_DB 는 replay 의 traces INSERT 가 원본 DB 를 건드리지 않게 하기 위한 것.
        env = {**os.environ, "MAINTQ_MCP_AUTOSTART": "0", "MAINTQ_DB": str(db)}
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
                err = proc.stderr.read().decode("utf-8", "replace")[-800:] if proc.stderr else ""
                raise SystemExit(f"[중단] 서버가 뜨지 않았습니다\n{err}")
            asyncio.run(run())
        finally:
            proc.terminate()
            try:
                _, err_bytes = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                _, err_bytes = proc.communicate()

    stderr_text = (err_bytes or b"").decode("utf-8", "replace")
    # D42 의 실측 결함 문구. 조기 종료가 cancel scope 를 오염시키면 여기 흔적이 남는다.
    marks = [m for m in ("cancel scope", "CancelledError", "Traceback") if m in stderr_text]
    check(
        "⑱ 서버 로그에 cancel scope 예외 없음 (조기 종료 후)",
        not marks,
        f"검출 {marks}" if marks else "깨끗함",
    )

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        if stderr_text.strip():
            print(f"\n[서버 stderr 끝부분]\n{stderr_text[-1200:]}")
        raise SystemExit(f"\n[SP3 실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\nSP3 통과 ({len(results)}건) — 이벤트 4종 · block 중간 삽입 · A5 저장 · D36/D42 회귀")


if __name__ == "__main__":
    main()
