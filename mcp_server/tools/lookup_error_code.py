# -*- coding: utf-8 -*-
"""lookup_error_code — 에러코드 정확 조회 (docs/04_MCP_TOOLS.md §1).

exact match 룩업이다. 절차·배경 서술은 rag_search_manual 담당 — 이 경계를 흐리지 말 것 (D1).

핵심 규칙
  - `(model, code)` 복합키로 조회한다 (D13) — code 단독이면 "같은 코드, 다른 의미"가 무너진다
  - 입력 code 는 `strip().upper()` 로 정규화하고 매칭은 case-insensitive (D25).
    `display_code` 는 매뉴얼/키패드 원표기를 그대로 돌려준다 (사용자 입력 반향이 아니다)
  - `manual_page` 는 PDF 물리 페이지 그대로 반환한다 — 인쇄 페이지 환산 금지 (D26).
    환산은 백엔드 렌더 1곳(backend/manifest.py)만 담당한다 (D32)
  - `actions_source` 는 `actions` 목록의 출처를 `{manual_id, page}` 로 싣는다 (D100).
    `page` 는 D26 대로 PDF 물리 페이지다 — 인쇄용 페이지로의 환산은 여기서 하지 않는다.
    환산은 여전히 백엔드 렌더 1곳(`backend/sse.py:citation_for()`)만 담당한다 (D32) —
    이 도구는 manifest 를 읽지도 않는다. `null` 은 "출처가 기록되지 않았다"는 뜻이지
    "본문(manual_page)과 같은 페이지"라는 뜻이 아니다 — 현재는 병합 미완으로 전건 NULL 이다
  - `related_parts` 는 진단→부품 특정의 다리다 (D12·D20). 이 값으로 search_inventory 를 부른다
  - 표에 없는 코드는 `not_found` — 유사 코드를 추측해 돌려주지 않는다 (S4, 환각률 0% 목표)
  - **error_codes 가 0행이면 not_found 가 아니라 `status:"error"` + `reason:"catalog_not_loaded"`**
    (D50). 미적재를 not_found 로 주면 모든 코드가 S4 로 흘러 지표가 가짜 100% 가 된다

실패는 예외가 아니라 status 로 반환한다 (D9).
"""

from __future__ import annotations

import json

from ..db import read_only

MODELS = ("iG5A", "S100", "IE5", "HV600")

DESCRIPTION = (
    "인버터/PLC 에러코드의 공식 정의·원인·조치를 조회한다. 에러코드가 명확할 때 가장 먼저 "
    "사용. 코드가 표에 없으면 not_found를 반환하며, 이때 유사 코드를 추측하지 말 것. "
    "점검 절차·배선 등 서술형 설명은 이 도구가 아니라 rag_search_manual을 사용할 것."
)


def _json_list(raw: object) -> list:
    """causes·actions·related_parts 는 JSON array 컬럼. NULL 이면 빈 리스트."""
    if raw is None or raw == "":
        return []
    value = json.loads(raw)
    return value if isinstance(value, list) else []


def lookup_error_code(model: str, code: str) -> dict:
    if model not in MODELS:
        return {
            "status": "error",
            "reason": "invalid_model",
            "message": f"model은 {'|'.join(MODELS)} 이어야 합니다: {model!r}",
        }

    # D25 — 내부 canonical 은 대문자. 사용자 입력 표기는 혼재('OHt'·'oht'·'OHT')
    canonical = (code or "").strip().upper()
    if not canonical:
        return {
            "status": "error",
            "reason": "code_required",
            "message": "code는 필수입니다 (예: 'OHt')",
        }

    try:
        with read_only() as con:
            row = con.execute(
                "SELECT model, code, display_code, error_name, severity,"
                "       causes, actions, related_parts, manual_page,"
                "       actions_manual_id, actions_page"
                " FROM error_codes WHERE model = ? AND upper(code) = ?",
                (model, canonical),
            ).fetchone()
            # 미적재(0행)와 진짜 미지 코드를 갈라야 한다 (D50) — 못 찾았을 때만 세어 본다
            loaded = 1
            if row is None:
                loaded = con.execute("SELECT count(*) FROM error_codes").fetchone()[0]
    except Exception as e:  # noqa: BLE001 — 예외를 status 로 바꿔 반환 (D9)
        return {"status": "error", "reason": "db_error", "message": str(e)}

    if row is None:
        if loaded == 0:
            # 승인 게이트로 아직 비어 있는 상태. S4(미지 코드)와 절대 섞으면 안 된다
            return {
                "status": "error",
                "reason": "catalog_not_loaded",
                "message": (
                    "에러코드 표가 아직 적재되지 않았습니다 — 조회 결과 없음이 아니라 "
                    "데이터 미적재입니다. 코드가 매뉴얼에 있는지 여부를 판단하지 마세요."
                ),
            }
        # 표는 적재됐는데 이 코드가 없다 → S4. 유사 코드 제안을 넣지 않는다 (환각 방지)
        return {
            "status": "not_found",
            "model": model,
            "code": canonical,
            "message": f"{model} 매뉴얼에서 확인되지 않는 코드입니다 ({canonical}).",
        }

    try:
        causes = _json_list(row["causes"])
        actions = _json_list(row["actions"])
        related_parts = _json_list(row["related_parts"])
    except json.JSONDecodeError as e:
        return {
            "status": "error",
            "reason": "malformed_row",
            "message": f"{model}/{canonical} 행의 JSON 컬럼을 읽을 수 없습니다: {e}",
        }

    # D100 — DDL CHECK가 (actions_manual_id, actions_page) 짝을 강제하므로 둘 다 있거나
    # 둘 다 NULL. 한쪽만 있는 경우는 없다 (방어 코드 불필요, MQ-904).
    # 인쇄용 페이지는 절대 포함하지 않는다 — 그 환산은 backend/sse.py:citation_for() 1곳만 (D32).
    actions_source = None
    if row["actions_manual_id"] is not None and row["actions_page"] is not None:
        actions_source = {
            "manual_id": row["actions_manual_id"],
            "page": row["actions_page"],
        }

    return {
        "status": "ok",
        "code": row["code"],  # 대문자 canonical (D25)
        "display_code": row["display_code"] or row["code"],  # 원표기 보존. 입력 반향이 아님
        "error_name": row["error_name"],
        "severity": row["severity"],
        "causes": causes,
        "actions": actions,
        "actions_source": actions_source,  # {manual_id, page} | null (D100). null≠"본문과 같은 페이지"
        "related_parts": related_parts,  # D20 — 진단→부품 특정의 다리
        "manual_page": row["manual_page"],  # 물리 페이지 무가공 (D26)
    }
