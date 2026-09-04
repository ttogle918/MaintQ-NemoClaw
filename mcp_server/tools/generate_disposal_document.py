# -*- coding: utf-8 -*-
"""generate_disposal_document — 처분 승인서·진술보장서 **초안** 생성 (S10 계층 3의 입구).

`create_po_draft` 와 **완전히 같은 패턴**이다 (D67·`11 §5`): draft 만 INSERT 하고,
확정은 사람의 승인 큐에서만 일어나며, 신원은 백엔드가 stamp 한다.

────────────────────────────────────────────────────────────────────────────────
★ 이 도구가 지키는 경계
────────────────────────────────────────────────────────────────────────────────
  D10  `decisions` 에 `state='draft'` INSERT 만. UPDATE/DELETE 권한 자체가 없다 —
       규율이 아니라 `db.decision_writer()` 의 TEMP TRIGGER 2개로 잠근다.
       ⛔ `draft_writer()` 를 재사용하지 않는다. 그건 `po_drafts` 전용 트리거만 걸린
         커넥션이라, 그걸로 `decisions` 를 만지면 **잠금이 없는 채로 쓰는 것**이 된다.
  D81  `override`·`override_reason`·`reviewed_by` 는 **파라미터가 아니다.** 스키마에 키가
       없으므로 LLM 이 "추징을 감수하고 매각한다" 같은 사유를 지어내 BLOCKING 을 뚫는
       호출 자체가 불가능하다. 예외 적용은 서명 API 가 `X-User` 와 함께 받는다.
  D63  **verdict 가 BLOCKED 여도 draft 는 정상 생성된다.** 시스템은 막지 않는다 —
       막혔다는 사실과 뚫은 사람을 기록할 뿐이다. 막으면 사용자는 시스템 밖에서
       처분하고 **기록만 사라진다.** 그래서 "차단됐다"가 아니라 "차단된 채로 결재에
       올라간다"가 이 도구의 출력이다.
  D23·D37  `requested_by`·`session_id` 도 파라미터가 아니다. INSERT 직후 백엔드가 stamp 한다.
  D80  `reason` 에 기본값을 두지 않는다 — 승인자가 판단 근거를 추적할 수 있어야 한다.
  D86  `documents_preview` 는 **저장하지 않는다.** 정식 렌더는 `GET /api/decisions/{id}` 가
       응답 조립 시점에 번들에서 만든다. 저장하면 템플릿이 바뀔 때 저장본이 조용히 낡는다.
  D9   실패는 예외가 아니라 `status` 로 돌려준다.

────────────────────────────────────────────────────────────────────────────────
★ 근거 없는 서류는 만들지 않는다 — `build_evidence_bundle` 실패의 **그대로 전파**
────────────────────────────────────────────────────────────────────────────────
번들 생성은 `build_evidence_bundle` 을 **함수로 직접 호출**하고, 실패하면 그 `status`·
`reason` 을 손대지 않고 그대로 돌려준다. 특히:

  `law_text_unavailable` → **draft 를 만들지 않는다.** 해시할 조문 원문이 없는 서류는
    "이 결정이 참조한 근거가 이후 변조되지 않았음"을 증명하지 못한다 — 계층 3의 존재
    이유가 통째로 사라진다. 실패했다고 말하는 것으로 끝나면 안 되고 **아무것도 쓰지
    않아야** 하므로, INSERT 는 번들이 성공한 뒤에만 시작한다.
  `asset_modified`·`asset_disappeared` → 판정과 서류의 사실이 어긋난 상태다. 역시 미생성.

같은 이유로 판정·해시·자산 해석을 여기서 **다시 하지 않는다.** 두 벌이 생기면 서명 시
재대조가 어느 쪽과도 맞지 않게 된다 (W5 가 계층 1에서 겪은 이원화의 반복).

────────────────────────────────────────────────────────────────────────────────
★ 문안은 코드 상수다 — LLM 이 생성하지 않는다
────────────────────────────────────────────────────────────────────────────────
진술보장서는 법적 효력이 있는 문서다. 안전 문구(D2·safety-guardrail 규칙 1)와 같은
성격으로 **문장을 모델이 짓게 두지 않고** 템플릿에 번들의 값만 치환한다. 그리고 문안의
**검수 상태**를 `template_review_notice` 로 출력과 문서 본문 **양쪽에** 싣는다.

  ✅ **2026-08-13 사람 검수 완료** (수정 없이 승인 — `data/analysis/disposal_docs_review.md`).
  ⛔ 문구를 여기 하드코딩하지 않는다. 상태는 `data/doc_review.py` 가 갖고 `backend` 도 같은
    모듈을 읽는다(D73·**D90**) — 두 곳에 리터럴을 두면 도구 출력과 REST 응답이 갈린다.
    **검수가 끝나도 줄을 없애지 않는다** — 법적 문서에는 "언제 누가 검수했는가"가 남아야 한다.

  사실이 번들에 없으면 `확인되지 않음` 으로 적는다 — 빈칸으로 두면 "해당 없음"으로
  읽힌다. 모른다를 통과로 반올림하지 않는 D62 의 문서 판이다.

`mcp_server` 는 `backend` 를 import 하지 않는다 (D15).
"""

from __future__ import annotations

import sqlite3

import data.doc_fields as _df  # D124 — 문안·필드맵 정본. backend 를 import 하지 않는다
import data.doc_review as _doc_review  # D73 — 공유 데이터 계층. backend 를 import 하지 않는다
from data import txn  # D126 — 채번 경쟁 방지. backend 를 import 하지 않는다

from ..db import decision_writer
from ._asset_ref import NOT_TEXT, as_text, err as _err
from .build_evidence_bundle import build_evidence_bundle, canonical_json

DESCRIPTION = (
    "설비 자산의 처분 승인서·진술보장서 '초안'을 생성한다. 확정이 아니다. "
    "반드시 check_disposal_blockers 로 판정을 먼저 확인한 뒤 사용자가 처분을 결정한 후에만 호출할 것. "
    "판정이 BLOCKED·HOLD·INSUFFICIENT_FACTS 여도 초안은 만들어진다 — 그 사실이 초안에 기록되고, "
    "차단을 뚫을지는 팀장이 승인 화면에서 사유와 함께 결정한다. "
    "너는 override 를 요청하거나 사유를 대신 작성할 수 없다 — 그 파라미터가 없다. "
    "근거 조문 원문이 아직 수집되지 않았으면 초안 생성이 거부된다 — 해시할 근거가 없는 서류는 만들지 않는다."
)

# 출력 상수. 값이 계약이므로 호출부에서 조립하지 않는다 (`sprint-7 MQ-706` 출력 예시).
NEXT_STEP = "이 초안은 확정이 아니다. 팀장 승인 큐에서 서명해야 처분이 확정된다."

# ⛔ 문구를 여기 하드코딩하지 않는다 — `backend/services/decisions.py` 와 **같은 값**이어야 하고,
#    두 곳에 리터럴을 두면 한쪽만 바뀌어 도구 출력과 REST 응답이 갈린다 (D73 공유 계층, **D90**).
TEMPLATE_REVIEW_NOTICE = _doc_review.template_review_notice()

DECISION_TYPE = "DISPOSAL"

_UNKNOWN = "확인되지 않음"

# 문안 상수·근거 블록 헬퍼의 정본은 `data/doc_fields.py` 다 (D124) — 미리보기(이 도구)와
# docx(다운로드 엔드포인트)가 같은 문장을 써야 하므로 두 벌을 두지 않는다.
_VERDICT_LINES = _df.VERDICT_LINES
_VERDICT_UNKNOWN = _df.VERDICT_UNKNOWN
_NO_AUTO_BLOCK_LINE = _df.NO_AUTO_BLOCK_LINE
_UNKNOWN_LINE = _df.UNKNOWN_LINE
_val = _df.fact
_yn = _df.yn
_law_lines = _df.law_lines
_rule_lines = _df.rule_lines
_contract_lines = _df.contract_lines
_open_condition_lines = _df.open_condition_lines


def _next_decision_id(con: sqlite3.Connection) -> str:
    """`DEC-%04d`. 채번 규약을 갈라 두지 않는다 — `data/txn.py` 한 곳이 소유하고
    백엔드(`services/decisions._next_decision_id`)도 같은 함수를 쓴다 (D126)."""
    return txn.next_sequential_id(con, "decisions", "decision_id", "DEC")


def render_documents(
    bundle: dict, *, verdict: str, bundle_hash: str, reason: str, decision_id: str
) -> dict:
    """승인서·진술보장서 **미리보기** 문안. 저장하지 않는다 (D86).

    입력은 번들과 판정값뿐이다 — 여기서 DB 를 다시 읽지 않는다. 다시 읽으면 문서가
    번들과 다른 사실을 말할 수 있고, 그러면 해시가 가리키는 근거와 서류가 갈린다.
    """
    a = _df.fields_05(
        bundle,
        verdict=verdict,
        bundle_hash=bundle_hash,
        reason=reason,
        decision_id=decision_id,
    )
    w = _df.fields_06(
        bundle, verdict=verdict, bundle_hash=bundle_hash, decision_id=decision_id
    )

    approval = f"""[설비 처분 승인서 — 초안]
문서번호: {a["DECISION_ID"]} (초안 · 확정 아님)

1. 처분 대상
     · 자산 ID: {a["ASSET_ID"]}
     · 자산 상태: {a["ASSET_STATUS"]}
     · 취득일: {a["ACQUIRED_AT"]}
     · 설치 건물: {a["BUILDING_ID"]}

2. 처분 개요
     · 처분 방식: {a["DISPOSAL_MODE"]}
     · 처분 예정일: {a["DISPOSAL_DATE"]}
     · 요청 사유: {a["REASON"]}

3. 시스템 판정
     · 판정: {a["VERDICT"]} — {a["VERDICT_LINE"]}
     · {_NO_AUTO_BLOCK_LINE}
     · 평가한 룰 {a["RULES_EVALUATED"]}건 중 미해소 {a["RULES_OPEN"]}건
{a["OPEN_CONDITIONS"]}

4. 근거 (해시 고정)
     · 근거 번들 해시: {a["BUNDLE_HASH"]}
     · 법령 조문 {a["LAW_COUNT"]}건
{a["LAW_LINES"]}
     · 해석 룰 {a["RULE_COUNT"]}건
{a["RULE_LINES"]}
     · 계약 근거 {a["CONTRACT_COUNT"]}건 — 원문 원천이 저장소에 없어 해시로 고정되지 않음
{a["CONTRACT_LINES"]}

5. 결재
     · 상태: 초안(draft) — 확정 아님
     · 예외 적용(override): 미적용. 예외와 그 사유는 승인자가 서명 화면에서 기록한다.
     · 서명자 / 서명일시: (미기재 — 서명 시 기록된다)

{_UNKNOWN_LINE}
※ {TEMPLATE_REVIEW_NOTICE}"""

    warranty = f"""[진술 및 보장서 — 초안]
문서번호: {w["DECISION_ID"]} (초안 · 확정 아님)

매도인은 아래 자산의 처분({w["DISPOSAL_MODE"]},
예정일 {w["DISPOSAL_DATE"]})과 관련하여 다음 사실을 진술하고 보장한다.
아래 항목은 시스템이 보유한 자산 정보에서 그대로 옮긴 것이며, 매도인의 확인으로 확정된다.

1. 대상 자산
     · 자산 ID: {w["ASSET_ID"]}
     · 취득일: {w["ACQUIRED_AT"]}
     · 자산 상태: {w["ASSET_STATUS"]}

2. 권리관계
     · 담보권 설정: {w["HAS_LIEN"]}
     · 담보권자: {w["LIEN_CREDITOR"]}
     · 담보권자 동의서: {w["LIEN_CONSENT_REF"]}

3. 보험
     · 부보 여부: {w["INSURED"]}
     · 증권 식별자: {w["POLICY_ID"]}

4. 안전검사
     · 안전검사 대상: {w["SAFETY_INSPECTION_TARGET"]}
     · 최근 검사일: {w["LAST_INSPECTION_DATE"]}
     · 검사 유효기한: {w["INSPECTION_VALID_UNTIL"]}

5. 세제
     · 세액공제 적용: {w["TAX_CREDIT_APPLIED"]}
     · 취득 후 경과(개월): {w["MONTHS_SINCE_ACQUISITION"]}
     · 세금계산서 발급: {w["VAT_INVOICE_ISSUED"]} (거래 성립 전 시점 기준)

6. 미해소 조건 (시스템 판정 {w["VERDICT"]})
{w["OPEN_CONDITIONS"]}
     · {_NO_AUTO_BLOCK_LINE}

7. 근거 번들 해시: {w["BUNDLE_HASH"]}

{_UNKNOWN_LINE}
※ {TEMPLATE_REVIEW_NOTICE}"""

    return {"approval": approval, "representation_warranty": warranty}


def generate_disposal_document(
    reason: str,
    asset_id: str | None = None,
    equipment_id: str | None = None,
    disposal_mode: str = "SALE",
    disposal_date: str | None = None,
) -> dict:
    """처분 승인서·진술보장서 draft 를 `decisions` 에 한 건 INSERT 한다 (D10 — INSERT 만).

    `asset_id`·`equipment_id` 는 **둘 중 하나 필수**라 시그니처상 둘 다 optional 이다
    (D80 의 either-or 공백). 해석·검증은 `build_evidence_bundle` 이 `_asset_ref` 로 하며,
    여기서 네 번째 사본을 만들지 않는다.

    실패는 예외가 아니라 `status` 로 돌려준다 (D9).
    """
    try:
        # ── ① reason 게이트 (`create_po_draft:58` 과 같은 어휘). 번들보다 **먼저** 본다 —
        #    거부할 입력으로 DB 를 열 이유가 없다.
        parsed_reason = as_text(reason)
        if parsed_reason is None or parsed_reason is NOT_TEXT:
            return _err(
                "reason_required",
                "reason 은 필수입니다 — 승인자가 처분 판단의 근거를 추적할 수 있어야 합니다 "
                "(D5·D80). 사용자가 밝힌 사유를 그대로 넣고, 없으면 먼저 물어보세요.",
            )
        reason_text = str(parsed_reason)

        # ── ② 근거 번들. 실패는 **그대로 전파**하고 여기서 끝낸다 — draft 미생성.
        #    특히 `law_text_unavailable` 은 "해시할 근거가 없다"는 뜻이라, 이 경로에서
        #    서류를 만들면 계층 3이 빈 약속이 된다.
        built = build_evidence_bundle(
            asset_id=asset_id,
            equipment_id=equipment_id,
            disposal_mode=disposal_mode,
            disposal_date=disposal_date,
        )
        if built.get("status") != "ok":
            return built

        resolved_id = built["asset_id"]
        bundle = built["evidence_bundle"]
        bundle_hash = built["bundle_hash"]
        verdict = built["verdict"]

        # ── ③ 판정과 무관하게 draft 를 만든다 (D63·D81). BLOCKED 를 여기서 막지 않는다.
        #    ⛔ 이 자리에 `if verdict in (...): return ...` 을 추가하지 말 것.
        #    ★ 직렬화는 `canonical_json` **그대로** 저장한다. 다시 직렬화하면 키 순서·구분자가
        #      달라져 서명 시 해시 재대조(D84)가 깨진다.
        serialized = canonical_json(bundle)

        with decision_writer() as con:
            decision_id = _next_decision_id(con)
            con.execute(
                "INSERT INTO decisions (decision_id, asset_id, decision_type, evidence_bundle,"
                " bundle_hash, verdict_at_signing, override, override_reason, reviewed_by,"
                " signed_at, state, reason)"
                # override=0 · override_reason/reviewed_by/signed_at=NULL · state='draft' 는
                # **리터럴로 박는다** (D81). 파라미터로 두면 언젠가 값이 흘러들어온다.
                " VALUES (?,?,?,?,?,?, 0, NULL, NULL, NULL, 'draft', ?)",
                (
                    decision_id,
                    resolved_id,
                    DECISION_TYPE,
                    serialized,
                    bundle_hash,
                    # 이름은 `_at_signing` 이지만 여기 담기는 값은 **draft 시점 판정**이다.
                    # 서명 시 백엔드가 재산출해 이 값을 덮는다 (D84) — 컬럼이 거짓말하지 않도록.
                    verdict,
                    reason_text,
                ),
            )

        # ── ④ 미리보기 렌더. **INSERT 뒤**에 하고, 여기서 실패해도 예외를 던지지 않는다 —
        #    렌더는 try 블록 안이어야 D9 가 성립한다 (문안 조립 버그가 도구를 죽이지 않게).
        documents = render_documents(
            bundle,
            verdict=verdict,
            bundle_hash=bundle_hash,
            reason=reason_text,
            decision_id=decision_id,
        )
    except sqlite3.IntegrityError as e:
        # FK·CHECK·TEMP TRIGGER(D10) 위반. 계약 위반이므로 그대로 드러낸다.
        return _err("integrity", str(e))
    except sqlite3.Error as e:
        return _err("db_error", str(e))
    except FileNotFoundError as e:
        return _err("db_missing", str(e))
    except Exception as e:  # noqa: BLE001 — 예외를 밖으로 던지지 않는다 (D9)
        return _err("internal_error", f"{type(e).__name__}: {e}")

    return {
        "status": "ok",
        "decision_id": decision_id,
        "state": "draft",
        "decision_type": DECISION_TYPE,
        "asset_id": resolved_id,
        "verdict_at_signing": verdict,
        "bundle_hash": bundle_hash,
        # 항상 false. 도구에는 이 값을 바꿀 파라미터가 없다 (D81) — 출력에 싣는 이유는
        # "예외가 적용되지 않은 초안"임을 소비자가 확인할 수 있게 하기 위함이다.
        "override": False,
        "next_step": NEXT_STEP,
        # D86 — 미리보기다. 저장하지 않는다. 정식 렌더는 GET /api/decisions/{id}.
        "documents_preview": documents,
        "template_reviewed": _doc_review.TEMPLATE_REVIEWED,
        "template_review_notice": TEMPLATE_REVIEW_NOTICE,
    }
