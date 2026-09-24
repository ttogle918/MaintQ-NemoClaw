# -*- coding: utf-8 -*-
"""ⓘ 헤더 도달 확인 (MQ-1901, D153 미확인 ①).

`nat mcp client tool call` CLI 는 `custom_headers`(X-User 등 임의 헤더)를 받지
않는다(`--bearer-token` 만 있다) — 그래서 `nvidia-nat-mcp` 의
`WorkflowBuilder.add_function_group()` 로 `mcp_client`(streamable-http +
custom_headers) 함수 그룹을 **코드로 직접** 구성해 쓴다. 이것이 워크플로 YAML
(`config_http.yml`)이 내부적으로 하는 것과 같은 코드 경로다(`MCPClientConfig`
→ `MCPFunctionGroup` → `MCPStreamableHTTPClient`) — LLM 에이전트 단계 없이
그 경로만 왕복 확인한다.

두 단계:
  A. header_echo.py(127.0.0.1:8799) 로 헤더 도달만 본다 (MCP 초기화는 실패해도 됨)
  B. 실제 MCP(core 프로필, 127.0.0.1:8765)로 lookup_error_code(iG5A, OHt) 호출

실행:
    # A
    uv run python spike/header_echo.py 8799 &
    uv run python spike/mcp_client_check.py echo http://127.0.0.1:8799/mcp

    # B (호스트에서 별도로 스파이크용 MCP 를 8765 코어 프로필로 띄운 뒤)
    uv run python spike/mcp_client_check.py real http://127.0.0.1:8765/mcp <token>
"""

from __future__ import annotations

import asyncio
import sys


async def _run(url: str, headers: dict[str, str], call_tool: str | None, call_args: dict | None) -> int:
    # `nat` CLI 는 진입 시 플러그인 엔트리포인트를 discover 해 함수(그룹) 레지스트리를
    # 채운다(`nat.runtime.loader`). 이 스크립트는 CLI 를 거치지 않으므로 mcp 플러그인의
    # `register.py` 를 직접 import 해 같은 레지스트리 등록을 일으킨다.
    import nat.plugins.mcp.register  # noqa: F401
    from nat.builder.workflow_builder import WorkflowBuilder
    from nat.plugins.mcp.client.client_config import MCPClientConfig, MCPServerConfig

    config = MCPClientConfig(
        server=MCPServerConfig(
            transport="streamable-http",
            url=url,
            custom_headers=headers,
        ),
        # `get_included_functions()`(빌더가 함수 그룹 추가 시 전역 레지스트리에 편입하는 통로)는
        # `include` 목록이 있을 때만 채워진다 — 없으면 빈 dict. 실 워크플로 YAML 도 이 목록을
        # 명시해야 `staging__lookup_error_code` 로 호출 가능해진다.
        include=[call_tool] if call_tool else [],
    )

    async with WorkflowBuilder() as builder:
        try:
            await asyncio.wait_for(builder.add_function_group("staging", config), timeout=15)
        except TimeoutError:
            print("[add_function_group 시간초과] echo 서버는 정상 MCP 응답을 안 주므로 예상된 결과 — "
                  "echo.log 의 헤더만 보면 된다")
            return 0
        except Exception as exc:  # noqa: BLE001 - 스파이크: 실패 자체가 판정 정보
            print(f"[add_function_group 실패] {type(exc).__name__}: {exc}")
            return 1

        group = await builder.get_function_group("staging")
        included = await group.get_included_functions()
        print(f"[연결 성공] 노출된 도구: {sorted(included.keys())}")

        if call_tool:
            fn_name = f"staging__{call_tool}"
            fn = await builder.get_function(fn_name)
            result = await fn.acall_invoke(**(call_args or {}))
            print(f"[도구 호출 결과] {call_tool} -> {result!r}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    mode = argv[1]
    url = argv[2]

    if mode == "echo":
        headers = {"X-User": "nat-onboarding"}
        # Authorization 은 auth_provider 없이도 custom_headers 로 실어 보낼 수 있다
        # (httpx 기본 헤더로 병합된다) — echo 서버에서 둘 다 확인하기 위함.
        headers["Authorization"] = "Bearer nat-spike-token"
        return asyncio.run(_run(url, headers, None, None))

    if mode == "real":
        token = argv[3] if len(argv) > 3 else ""
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return asyncio.run(
            _run(url, headers, "lookup_error_code", {"model": "iG5A", "code": "OHt"})
        )

    print(f"알 수 없는 모드: {mode}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
