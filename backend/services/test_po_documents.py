# -*- coding: utf-8 -*-
"""backend/services/po_documents.py 테스트 — evidence.basis 방어 파싱.

`backend/services/test_po.py`의 `_attach_print_pages` 케이스와 같은 근본 원인
(evidence 는 LLM 이 자유 형식으로 채운다, D34) — 여기서는 문서 렌더 경로
(`_evidence_lines`, `GET /api/po/{id}` 의 `documents_preview.diagnosis`)가 같은
방식으로 깨져 있었다(PO-0121 실측: basis 가 통짜 문자열).
"""

from __future__ import annotations

from backend.services.po_documents import _evidence_lines

_ECD = {"manual_page": 202}


def test_evidence_lines_skips_string_basis():
    po = {"model": "iG5A", "evidence": {"basis": "lookup_error_code: OHt ..."}}
    result = _evidence_lines(po, _ECD)  # 예외를 던지면 테스트 실패
    assert "매뉴얼(에러코드 정의)" in result  # 첫 줄(고정 문구)은 그대로 나온다


def test_evidence_lines_skips_non_dict_entries_in_list():
    po = {
        "model": "iG5A",
        "evidence": {
            "basis": [
                "그냥 문자열",
                {"tool": "search_inventory", "part_no": "FAN-IG5-01", "qty": 1, "safety_stock": 3},
            ]
        },
    }
    result = _evidence_lines(po, _ECD)
    assert "search_inventory" in result
    assert "FAN-IG5-01" in result


def test_evidence_lines_well_formed_basis_unchanged():
    po = {
        "model": "iG5A",
        "evidence": {
            "basis": [
                {"tool": "lookup_error_code", "manual_page": 202},  # 매뉴얼 인용과 중복이라 스킵
                {"tool": "search_inventory", "part_no": "FAN-IG5-01", "qty": 1, "safety_stock": 3},
            ]
        },
    }
    result = _evidence_lines(po, _ECD)
    assert result.count("lookup_error_code") == 0  # 중복 스킵 유지
    assert "search_inventory" in result
