# -*- coding: utf-8 -*-
"""MCP 서버 엔트리포인트 (D15 — 백엔드와 프로세스 분리).

목업 DB를 실제 ERP로 갈아끼울 때 이 서버만 교체하면 되는 구조가 핵심이다.

현재 등록된 도구 (**7/7 완성**):
  - lookup_error_code         에러코드 정의·원인·조치 (exact match)
  - rag_search_manual         매뉴얼 본문 서술형 검색 (하이브리드, D47)
  - search_inventory          재고·안전재고·단종
  - find_alternative_parts    호환 대체품
  - get_supplier_quotes       리드타임·단가·MOQ
  - get_error_history         반복 고장 판정
  - create_po_draft           발주 초안 (유일한 쓰기 도구)

주의: `error_codes` 는 사람 승인 전이라 아직 0행이다. 그래서 lookup_error_code 는
실데이터에서 `status:"error"` + `reason:"catalog_not_loaded"` 를 돌려준다 (D50) —
not_found 가 아니라 미적재라고 정직하게 실패하는 게 의도된 동작이다.

실행:  uv run python mcp_server/server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# 스크립트로 직접 실행될 때도 `mcp_server` 패키지로 임포트되게 한다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_server.tools.create_po_draft import (  # noqa: E402
    DESCRIPTION as PO_DESC,
    create_po_draft as _create_po_draft,
)
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
from mcp_server.tools.lookup_error_code import (  # noqa: E402
    DESCRIPTION as LOOKUP_DESC,
    lookup_error_code as _lookup_error_code,
)
from mcp_server.tools.rag_search_manual import (  # noqa: E402
    DESCRIPTION as RAG_DESC,
    rag_search_manual as _rag_search_manual,
)
from mcp_server.tools.search_inventory import (  # noqa: E402
    DESCRIPTION as INV_DESC,
    search_inventory as _search_inventory,
)

mcp = FastMCP("maintq")


@mcp.tool(description=LOOKUP_DESC)
def lookup_error_code(model: str, code: str) -> dict:
    """model 은 enum('iG5A','S100') 강제 (D6·D13). 표에 없으면 not_found —
    유사 코드를 추측해 돌려주지 않는다. 0행이면 not_found 가 아니라 error/catalog_not_loaded (D50)."""
    return _lookup_error_code(model=model, code=code)


@mcp.tool(description=RAG_DESC)
def rag_search_manual(model: str, query: str, top_k: int = 3) -> dict:
    """절차·배경 등 서술형 정보만. 에러코드 정의는 lookup_error_code 다 (D1).
    결과가 없으면 empty — 이때 절차를 지어내지 않는다."""
    return _rag_search_manual(model=model, query=query, top_k=top_k)


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


@mcp.tool(description=PO_DESC)
def create_po_draft(
    part_no: str,
    qty: int,
    supplier_id: str,
    reason: str,
    urgency: str = "normal",
    model: str | None = None,
    error_code: str | None = None,
    evidence: dict | None = None,
) -> dict:
    """⚠️ 유일한 쓰기 도구. 신원(requested_by)·session_id 는 **파라미터에 없다** —
    스키마에 없으므로 LLM 이 위조할 수 없고, 백엔드가 INSERT 직후 stamp 한다 (D23·D37)."""
    return _create_po_draft(
        part_no=part_no,
        qty=qty,
        supplier_id=supplier_id,
        reason=reason,
        urgency=urgency,
        model=model,
        error_code=error_code,
        evidence=evidence,
    )


if __name__ == "__main__":
    mcp.run()
