# -*- coding: utf-8 -*-
"""backend/services/po.py 테스트 — evidence.basis 방어 파싱.

`evidence` 는 LLM 이 create_po_draft 호출 시 자유 형식으로 채운다(D34, 스키마 강제
없음) — `basis` 가 리스트-of-dict 라는 보장이 없다. 실측(PO-0121, 2026-08-24 브라우저
QA): LLM 이 `basis` 를 통짜 문자열로 채웠고, `_attach_print_pages` 가 그 문자열을
`for entry in ...` 로 순회해 문자 하나하나에 `.get()` 을 호출하다 AttributeError 로
터졌다 — create_po_draft 자체는 이미 성공한 뒤였는데도 채팅 응답이 "생성 실패"로
보이는 사용자 체감 버그였다.
"""

from __future__ import annotations

from backend.services.po import _attach_print_pages


def test_attach_print_pages_skips_string_basis():
    """basis 가 리스트가 아니라 문자열이면(PO-0121 실측 형태) 죽지 않는다."""
    po = {
        "model": "iG5A",
        "evidence": {"symptoms": "냉각팬 소음", "basis": "lookup_error_code: OHt ...", "notes": ""},
    }
    _attach_print_pages(po)  # 예외를 던지면 테스트 실패
    assert po["evidence"]["basis"] == "lookup_error_code: OHt ..."  # 원본 보존, 지어내지 않음


def test_attach_print_pages_skips_non_dict_entries_in_list():
    """basis 가 리스트여도 그 안에 dict 아닌 항목이 섞이면 그 항목만 건너뛴다."""
    po = {
        "model": "iG5A",
        "evidence": {
            "basis": [
                "그냥 문자열 항목",
                {"tool": "lookup_error_code", "manual_page": 202},
            ]
        },
    }
    _attach_print_pages(po)
    assert po["evidence"]["basis"][0] == "그냥 문자열 항목"
    assert "print_page" in po["evidence"]["basis"][1]  # 정상 dict 항목은 그대로 처리됨


def test_attach_print_pages_well_formed_basis_unchanged():
    """정상 형태(seed.py 시드 형태)는 기존 동작 그대로 print_page 를 붙인다."""
    po = {
        "model": "iG5A",
        "evidence": {
            "basis": [
                {"tool": "lookup_error_code", "code": "OHT", "manual_page": 202},
                {"tool": "search_inventory", "part_no": "FAN-IG5-01"},
            ]
        },
    }
    _attach_print_pages(po)
    assert po["evidence"]["basis"][0]["print_page"] >= 1
    assert "print_page" not in po["evidence"]["basis"][1]  # manual_page 없으면 안 붙임


def test_attach_print_pages_no_evidence_is_noop():
    po = {"model": "iG5A", "evidence": None}
    _attach_print_pages(po)  # 예외 없이 그냥 반환
    assert po["evidence"] is None


def test_attach_print_pages_unknown_model_is_noop():
    po = {"model": "UNKNOWN-MODEL", "evidence": {"basis": "whatever"}}
    _attach_print_pages(po)
    assert po["evidence"]["basis"] == "whatever"
