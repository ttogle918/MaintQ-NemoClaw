# -*- coding: utf-8 -*-
"""MCP 서버 엔트리포인트 (D15 — 백엔드와 프로세스 분리).

목업 DB를 실제 ERP로 갈아끼울 때 이 서버만 교체하면 되는 구조가 핵심이다.

현재 등록된 도구 (M2 진행 중):
  - search_inventory          재고·안전재고·단종
  - find_alternative_parts    호환 대체품
  - get_supplier_quotes       리드타임·단가·MOQ
  - get_error_history         반복 고장 판정

아직 없음: lookup_error_code / rag_search_manual (error_codes 사람 승인 대기),
          create_po_draft (쓰기 도구 — 별도 검토 후)

실행:  uv run python mcp_server/server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# 스크립트로 직접 실행될 때도 `mcp_server` 패키지로 임포트되게 한다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_server.tools.find_alternative_parts import (  # noqa: E402
    DESCRIPTION as ALT_DESC,
    find_alternative_parts as _find_alternative_parts,
)
from mcp_server.tools.get_error_history import (  # noqa: E402
    DESCRIPTION as HIST_DESC,
    get_error_history as _get_error_history,
)
from mcp_server.tools.get_supplier_quotes import (  # noqa: E402
    DESCRIPTION as QUOTE_DESC,
    get_supplier_quotes as _get_supplier_quotes,
)
from mcp_server.tools.search_inventory import (  # noqa: E402
    DESCRIPTION as INV_DESC,
    search_inventory as _search_inventory,
)

mcp = FastMCP("maintq")


@mcp.tool(description=INV_DESC)
def search_inventory(
    part_no: str | None = None,
    part_name: str | None = None,
    model: str | None = None,
) -> dict:
    return _search_inventory(part_no=part_no, part_name=part_name, model=model)


@mcp.tool(description=ALT_DESC)
def find_alternative_parts(part_no: str) -> dict:
    return _find_alternative_parts(part_no=part_no)


@mcp.tool(description=QUOTE_DESC)
def get_supplier_quotes(part_no: str, qty: int = 1) -> dict:
    return _get_supplier_quotes(part_no=part_no, qty=qty)


@mcp.tool(description=HIST_DESC)
def get_error_history(
    equipment_id: str | None = None,
    line_id: int | None = None,
    code: str | None = None,
    days: int = 30,
) -> dict:
    return _get_error_history(equipment_id=equipment_id, line_id=line_id, code=code, days=days)


if __name__ == "__main__":
    mcp.run()
