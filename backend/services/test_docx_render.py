# -*- coding: utf-8 -*-
"""docx_render 단위 테스트 — DB 를 쓰지 않는다 (템플릿 파일만 읽는다).

⚠ 이 파일은 `data/templates/*.docx` 를 **읽기만** 한다. 마지막 검사
(`test_template_is_not_modified`)가 그 사실을 바이트로 단언한다 — 템플릿은 양식의
정본이고, 생성 코드가 정본을 건드리면 서류가 조용히 달라진다.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from backend.services import docx_render as dr

T05 = "05_설비처분승인서.docx"
T02 = "02_정비부품발주요청서.docx"


def _complete(template: str) -> dict[str, str]:
    """템플릿의 모든 자리를 채운 최소 필드맵."""
    return {k: f"<{k}>" for k in dr.template_placeholders(template)}


def _document_xml(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return z.read("word/document.xml").decode("utf-8")


def test_placeholders_are_discovered():
    keys = dr.template_placeholders(T05)
    assert len(keys) == 30
    assert "BUNDLE_HASH" in keys and "VERDICT_LINE" in keys


def test_fill_returns_docx_bytes():
    data = dr.fill_template(T05, _complete(T05))
    assert isinstance(data, bytes) and data[:2] == b"PK"
    xml = _document_xml(data)
    assert "{{" not in xml
    # `<` `>` 는 XML 이스케이프되므로 &lt;…&gt; 로 들어간다
    assert "&lt;BUNDLE_HASH&gt;" in xml


def test_missing_field_raises():
    fields = _complete(T05)
    del fields["BUNDLE_HASH"]
    with pytest.raises(dr.TemplateFieldMismatch) as e:
        dr.fill_template(T05, fields)
    assert "BUNDLE_HASH" in str(e.value)


def test_extra_field_raises():
    fields = _complete(T05) | {"NOT_IN_TEMPLATE": "x"}
    with pytest.raises(dr.TemplateFieldMismatch) as e:
        dr.fill_template(T05, fields)
    assert "NOT_IN_TEMPLATE" in str(e.value)


def test_drop_rows_removes_the_row_and_its_keys():
    """표 2·3행을 통째로 지운다 — 빈 칸을 '해당 없음'으로 읽히게 두지 않는다 (D62)."""
    keys = dr.template_placeholders(T02)
    dropped = {k for k in keys if k.endswith(("_2", "_3"))}
    fields = {k: f"<{k}>" for k in keys - dropped}
    data = dr.fill_template(T02, fields, drop_rows=dropped)
    xml = _document_xml(data)
    assert "{{" not in xml
    assert "&lt;PART_NO_1&gt;" in xml
    assert "PART_NO_2" not in xml


def test_drop_rows_tolerates_fields_for_dropped_slots():
    """삭제된 행의 자리를 fields 가 갖고 있어도 '초과'로 보지 않는다.

    호출부가 조건부로 행을 지울 때 fields 쪽을 함께 좁히도록 강요하면, 두 곳을
    같이 고쳐야 하는 구조가 된다 — D90 이 겪은 실패 유형이다.
    """
    keys = dr.template_placeholders(T02)
    dropped = {k for k in keys if k.endswith(("_2", "_3"))}
    data = dr.fill_template(T02, _complete(T02), drop_rows=dropped)
    assert "{{" not in _document_xml(data)


def test_unknown_template_raises():
    with pytest.raises(FileNotFoundError):
        dr.fill_template("99_없는문서.docx", {})


def test_template_is_not_modified():
    """원본 파일은 손대지 않는다 — 템플릿은 양식의 정본이다."""
    path = dr.TEMPLATE_DIR / T05
    before = path.read_bytes()
    dr.fill_template(T05, _complete(T05))
    assert path.read_bytes() == before


def test_all_five_templates_fill_cleanly():
    """01·02·03·05·06 다섯 종 전부. 04 는 대상이 아니다 (D118 — FinAllQ 소관)."""
    for template in (
        "01_설비이상진단보고서.docx",
        "02_정비부품발주요청서.docx",
        "03_자금집행요청서.docx",
        "05_설비처분승인서.docx",
        "06_진술및보장서.docx",
    ):
        keys = dr.template_placeholders(template)
        dropped = {k for k in keys if k.endswith(("_2", "_3"))}
        data = dr.fill_template(
            template, {k: f"<{k}>" for k in keys - dropped}, drop_rows=dropped
        )
        assert data[:2] == b"PK", template
        assert "{{" not in _document_xml(data), template
