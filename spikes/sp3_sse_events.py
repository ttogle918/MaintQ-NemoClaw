# -*- coding: utf-8 -*-
"""SP3 — FastAPI SSE 이벤트 4종 스트리밍 검증 (docs/09_RUNTIME.md §4).

검증 질문:
  token / tool_call / tool_result / block 이 프론트에서 구분 수신되고,
  block 이 token 스트림 "중간"에 삽입 가능한가? (D22)

실제 uvicorn 프로세스를 띄우고 HTTP 로 붙는다 — TestClient in-process 가 아니라,
네트워크를 타는 진짜 스트리밍인지(버퍼링에 갇히지 않는지) 봐야 하기 때문.

실행:  uv run python spikes/sp3_sse_events.py
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PORT = 8083
BASE = f"http://127.0.0.1:{PORT}"

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


async def collect() -> list[tuple[float, str, dict]]:
    """SSE 프레임을 (수신시각, event, data) 로 모은다. 도착 순서가 검증 대상이다."""
    events: list[tuple[float, str, dict]] = []
    buf = ""
    t0 = time.monotonic()

    async with httpx.AsyncClient(timeout=30.0) as c:
        async with c.stream(
            "POST",
            f"{BASE}/api/chat?delay=0.02",
            json={"session_id": "SP3", "message": "iG5A 인버터에 OHt 에러 떴어"},
            # X-User 는 ASCII 사용자 ID — 한글 표시명은 HTTP 헤더에 못 넣는다 (D36)
            headers={"X-Role": "technician", "X-User": "tech-01"},
        ) as resp:
            check(
                "① 200 + text/event-stream",
                resp.status_code == 200
                and resp.headers.get("content-type", "").startswith("text/event-stream"),
                f"{resp.status_code} {resp.headers.get('content-type')}",
            )
            async for chunk in resp.aiter_text():
                buf += chunk
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
    return events


async def run() -> None:
    events = await collect()
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


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("SP3 — FastAPI SSE 이벤트 4종 + block 중간 삽입 (실제 uvicorn 프로세스)\n")
    # SP3 는 replay 경로만 쓴다 — MCP 를 띄울 이유가 없다.
    # lifespan 이 매번 stdio 서버를 스폰하면 기동이 느려지고, 연속 실행 시
    # 포트·자식 프로세스가 물려 간헐 실패한다 (실제로 한 번 겪었다).
    env = {**os.environ, "MAINTQ_MCP_AUTOSTART": "0"}
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
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    width = max(len(n) for n, _, _ in results)
    print("─" * (width + 46))
    for name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 46))

    failed = [n for n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[SP3 실패] {len(failed)}건: {', '.join(failed)}")
    print(f"\nSP3 통과 ({len(results)}건) — 이벤트 4종 구분 수신 + block 중간 삽입 확인")


if __name__ == "__main__":
    main()
