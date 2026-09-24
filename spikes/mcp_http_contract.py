# -*- coding: utf-8 -*-
"""MCP HTTP 입구 계약 검증 — `mcp_server/http_entry.py` (D150).

## 왜 필요한가

NemoClaw 는 stdio MCP 를 받지 않아서(원문: *"Stdio-only MCP servers are not supported"*)
같은 서버를 `streamable-http` 로도 연다. 전송이 둘이 되는 순간 **두 입구가 갈라지는**
고장 유형이 새로 생긴다 — 한쪽에만 도구가 등록되거나, HTTP 쪽만 인증이 빠지거나,
바인딩이 `0.0.0.0` 으로 열려 게이트웨이를 우회하는 두 번째 입구가 되는 것.

## 무엇을 보는가

  ① 토큰 없으면 **기동 거부**(exit ≠ 0). 열린 채로 뜨는 것보다 안 뜨는 게 낫다
     ↔ **양성 축**: 토큰이 있으면 실제로 뜬다 (①만 보면 "늘 죽는다" 도 통과한다)
  ② `Authorization` 없음 → 401
  ③ 틀린 토큰 → 401 (접두어·대소문자·공백 변주 포함)
  ④ 정상 토큰의 `tools/list` 가 **stdio 와 집합 동일** — 부분집합이 아니다.
     ↔ 양성 축: 집합이 비어 있지 않다 (둘 다 0이면 "같다" 로 통과한다)
  ⑤ 바인딩이 loopback 이다 — 소스에 `0.0.0.0` 이 없고 `BIND_HOST` 가 127.0.0.1
  ⑥ 쓰기 도구는 여전히 **3종**뿐이다 (D10 — 전송이 늘어도 쓰기 표면은 그대로)
  ⑦ 401 본문에 원인을 적지 않는다 (D40·D131)
  ⑧ DNS 리바인딩 보호가 **켜져 있다** — 허용 Host 목록을 넓히기만 하고 끄지 않는다.
     ↔ 양성 축: 기본 목록에 loopback 이 들어 있다 (빈 목록이면 "안 껐다" 로 통과한다)
  ⑨ `MAINTQ_MCP_ALLOWED_HOSTS` 로 **더할 수는 있어도 기본값을 지울 수는 없다**
  ⑩ loopback 밖 바인딩은 TLS 없이 기동 거부 (D150 개정) ↔ 양성 축: TLS 를 주면 통과

실행:  uv run python spikes/mcp_http_contract.py
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import anyio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp_server import http_entry  # noqa: E402

TOKEN = "spike-token-4f2a9c"
#: D10 이 허용하는 쓰기 도구. 전송이 늘어도 이 집합은 변하지 않아야 한다.
WRITE_TOOLS = {"create_po_draft", "generate_disposal_document", "create_repair_record"}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, bool(ok), detail))


def strip_prose(src: str) -> str:
    """주석·문자열 리터럴을 걷어낸 **코드만** 돌려준다.

    부재 검사(`"0.0.0.0" not in ...`)를 원문에 걸면 *"0.0.0.0 으로 열지 마라"* 라는
    경고 주석이 위반으로 잡힌다. 판정은 코드에 대해서만 해야 한다.
    """
    import io
    import tokenize

    out: list[str] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        out.append(tok.string)
    return " ".join(out)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env(**extra: str) -> dict[str, str]:
    env = {**os.environ, **extra}
    env.pop("MAINTQ_MCP_TOKEN", None)
    env.update({k: v for k, v in extra.items()})
    return env


def start_server(port: int, token: str | None) -> subprocess.Popen:
    env = _env()
    if token is not None:
        env["MAINTQ_MCP_TOKEN"] = token
    env["MAINTQ_MCP_HTTP_PORT"] = str(port)
    return subprocess.Popen(
        [sys.executable, "-m", "mcp_server.http_entry"],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def wait_ready(port: int, proc: subprocess.Popen, timeout: float = 45.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


def http_status(port: int, header: str | None) -> tuple[int, str]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", method="POST", data=b"{}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json, text/event-stream")
    if header is not None:
        req.add_header("Authorization", header)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read(400).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read(400).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return -1, repr(e)


async def tools_over_http(port: int) -> list[str]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    url = f"http://127.0.0.1:{port}/mcp"
    async with streamablehttp_client(url, headers={"Authorization": f"Bearer {TOKEN}"}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return sorted(t.name for t in (await s.list_tools()).tools)


async def tools_over_stdio() -> list[str]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable, args=["-m", "mcp_server.server"], env={**os.environ}
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return sorted(t.name for t in (await s.list_tools()).tools)


def main() -> None:
    print("MCP HTTP 입구 계약 — D150 (토큰 가드 · 전송 간 도구 동일성 · loopback)\n")

    # ① 토큰 없이 기동 → 거부. 양성 축은 ①-b 가 맡는다.
    port_a = free_port()
    p = start_server(port_a, token=None)
    try:
        out = p.communicate(timeout=60)[0] or ""
    except subprocess.TimeoutExpired:
        p.kill()
        out = "(타임아웃 — 죽지 않았다)"
    check(
        "① 토큰 없으면 기동 거부",
        p.returncode not in (0, None) and "MAINTQ_MCP_TOKEN" in out,
        f"exit={p.returncode} · 메시지에 변수명 {'있음' if 'MAINTQ_MCP_TOKEN' in out else '없음'}",
    )

    # ①-b 양성 축 — 토큰이 있으면 실제로 뜬다
    port = free_port()
    proc = start_server(port, token=TOKEN)
    try:
        ready = wait_ready(port, proc)
        check("①-b 양성 축 — 토큰 있으면 기동", ready, f"port={port} · ready={ready}")
        if not ready:
            tail = (proc.stdout.read(800) if proc.stdout else "") or ""
            check("(기동 실패로 이하 생략)", False, tail.strip()[-200:])
            return

        code_none, body_none = http_status(port, None)
        check("② Authorization 없음 → 401", code_none == 401, f"HTTP {code_none}")

        bad = ["Bearer wrong-token", "bearer ", TOKEN, f"Basic {TOKEN}", f"Bearer {TOKEN}x"]
        codes = [http_status(port, h)[0] for h in bad]
        check(
            "③ 틀린 토큰 변주 5종 → 전부 401",
            all(c == 401 for c in codes),
            f"코드 {codes}",
        )

        http_names = anyio.run(tools_over_http, port)
        stdio_names = anyio.run(tools_over_stdio)
        check(
            "④ stdio 와 도구 집합 동일",
            http_names == stdio_names and len(http_names) > 0,
            f"http {len(http_names)}종 · stdio {len(stdio_names)}종 · "
            f"{'동일' if http_names == stdio_names else '불일치: ' + str(set(http_names) ^ set(stdio_names))}",
        )

        src = Path(http_entry.__file__).read_text(encoding="utf-8")
        code = strip_prose(src)
        # 부재 검사 + 양성 축 — 코드에 와일드카드가 없다 + 스트리퍼가 살아 있다.
        # ⚠ 주석·독스트링을 걷어내지 않으면 "0.0.0.0 으로 열지 마라" 는 **경고문**이
        #    위반으로 잡힌다(실제로 처음에 그렇게 FAIL 했다).
        no_wildcard = "0.0.0.0" not in code
        stripper_alive = "BIND_HOST" in code and len(code) > 300
        check(
            "⑤ loopback 바인딩 (주석 제외 코드 기준)",
            http_entry.BIND_HOST == "127.0.0.1" and no_wildcard and stripper_alive,
            f"BIND_HOST={http_entry.BIND_HOST} · 코드 {len(code)}자(원문 {len(src)}) · "
            f"와일드카드 {'없음' if no_wildcard else '있음'} · 스트리퍼 "
            f"{'생존' if stripper_alive else '죽음'}",
        )

        writes = WRITE_TOOLS & set(http_names)
        check(
            "⑥ 쓰기 도구는 core 프로파일에서 1종뿐 (D10 표면 불변)",
            writes == {"create_po_draft"},
            f"노출된 쓰기 도구 {sorted(writes)} (core 기준 · full 은 3종)",
        )

        check(
            "⑦ 401 본문에 원인 미기재 (D40·D131)",
            "token" not in body_none.lower() and "MAINTQ" not in body_none,
            f"본문={body_none[:60]!r}",
        )

        # ⑧⑨⑩ — 호스트 실행 배선(D150 개정)에서 새로 생긴 표면.
        ts = http_entry.transport_security()
        base = http_entry.allowed_hosts({})
        check(
            "⑧ DNS 리바인딩 보호 유지",
            ts.enable_dns_rebinding_protection is True and "127.0.0.1" in base,
            f"보호={ts.enable_dns_rebinding_protection} · 기본 허용 {len(base)}개(loopback 포함 "
            f"{'예' if '127.0.0.1' in base else '아니오'})",
        )

        widened = http_entry.allowed_hosts({http_entry.ALLOWED_HOSTS_ENV: "host.openshell.internal"})
        check(
            "⑨ 허용 Host 는 추가만 되고 기본값이 지워지지 않는다",
            set(base) <= set(widened) and "host.openshell.internal" in widened,
            f"기본 {len(base)} ⊆ 확장 {len(widened)} · 추가분 반영 "
            f"{'예' if 'host.openshell.internal' in widened else '아니오'}",
        )

        try:
            http_entry.resolve_bind({http_entry.BIND_ENV: "0.0.0.0"})
            no_tls_refused = False
        except http_entry.TlsRequired:
            no_tls_refused = True
        with_tls = http_entry.resolve_bind(
            {
                http_entry.BIND_ENV: "0.0.0.0",
                http_entry.TLS_CERT_ENV: "/tmp/x.crt",
                http_entry.TLS_KEY_ENV: "/tmp/x.key",
            }
        )
        check(
            "⑩ loopback 밖은 TLS 필수 (양성 축 포함)",
            no_tls_refused and with_tls == ("0.0.0.0", "/tmp/x.crt", "/tmp/x.key"),
            f"TLS 없음 거부={no_tls_refused} · TLS 있음 통과={with_tls[0]!r}",
        )
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
        raise SystemExit(f"\n[실패] {len(failed)}건:\n  - " + "\n  - ".join(failed))
    print(f"\n통과 ({len(results)}건) — 토큰 가드 양방향 · 전송 간 도구 집합 동일 · loopback · D10 표면 불변")


if __name__ == "__main__":
    main()
