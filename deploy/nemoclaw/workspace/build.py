"""OpenClaw workspace 파일(AGENTS.md 등)을 MaintQ 정본에서 생성한다.

왜 생성하나: 안전 확정 문구·근거 페이지의 정본은 `backend/agent/prompts.py` 의
`SAFETY_BASELINE`·`QUALIFIED_WORKER_NOTE` 다. AGENTS.md 에 손으로 복사하면 문구가
갈라진다(절대 규칙 3 — 안전 문구는 매뉴얼 근거 없이 생성 금지). 그래서 여기서 읽어 찍는다.

백엔드와 다른 점: MaintQ 백엔드는 안전 블록·인용 칩을 **시스템(loop.py)이** 붙인다
(prompts.py 규칙 10·11). OpenClaw 에는 그 계층이 없으므로 에이전트가 **확정 문구를
그대로** 붙이고, 페이지는 **도구 결과 값만** 인용하도록 규칙을 바꿔 적는다.

온보딩 기종(D157): HV600 등 새 기종의 안전 문구는 prompts.py 가 아니라 DB 승인 행에서 온다
(`backend/agent/safety_source.resolve()`). 그래서 이 스크립트는 **DB 를 읽는다** —
`DATABASE_URL` 이 필요하고, DB 를 못 읽으면 「승인 없음」으로 조용히 쓰지 않고 **실패 종료**한다
(부재가 사실인지 알 수 없다). `--check` 의 드리프트 판정도 DB 상태를 포함한다 — 사람이 안전
문구를 승인하면 코드 변경 없이도 `--check` 가 stale 을 낸다(재생성·재업로드 필요 신호).

사용 (DATABASE_URL 필수):
    DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" \
        uv run python deploy/nemoclaw/workspace/build.py          # out/ 에 생성
    DATABASE_URL="$(grep -m1 '^DATABASE_URL=' .env | cut -d= -f2-)" \
        uv run python deploy/nemoclaw/workspace/build.py --check  # out/ 이 정본(+DB)과 같은지 검사
배포:
    nemoclaw maintq-agent upload deploy/nemoclaw/workspace/out/AGENTS.md /sandbox/.openclaw/workspace/
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.agent import safety_source  # noqa: E402
from backend.agent.prompts import QUALIFIED_WORKER_NOTE, SAFETY_BASELINE  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

PAGES = SAFETY_BASELINE["pages"]
SAFETY_MODELS = " / ".join(PAGES)  # 확정 문구가 승인된 기종 (현재 iG5A / S100)

#: 온보딩으로 새로 들어온 기종 중 안전 절차를 다룰 대상 (D157). 현재는 HV600 하나뿐이다.
ONBOARDING_SAFETY_MODEL = "HV600"


def _refs(pages: dict) -> str:
    return " · ".join(f"{m} p.{p}" for m, p in pages.items())


class OnboardingDbUnreadable(RuntimeError):
    """온보딩 안전 문구 상태를 DB 에서 확정할 수 없다 — 생성을 중단한다."""


def _approved_count(model: str) -> int:
    """승인 행 수를 **직접** 센다 — 실패하면 예외를 그대로 올린다.

    `safety_source.resolve()` 는 런타임 안전(D157 fail-closed)을 위해 DB 예외(테이블 없음
    포함)까지 삼켜 `None` 을 돌려준다 — 그 함수만으로는 "승인 0건"과 "DB 를 못 읽었다"를
    구분할 수 없다. `SELECT 1` 만으로도 부족하다(접속은 되는데 테이블이 없으면 통과한다).
    그래서 resolve 와 **같은 조건**으로 표를 직접 읽어 부재를 양성으로 확인한다.
    """
    from backend import db  # noqa: PLC0415 — 임포트 시점 접속 시도를 피한다

    with db.connect() as con:
        row = con.execute(
            "SELECT count(*) AS n FROM onboarding_safety_candidates"
            " WHERE model = ? AND kind = 'discharge_wait' AND state = 'approved'",
            (model,),
        ).fetchone()
    return int(row["n"])


def onboarding_safety_section() -> str:
    """온보딩 승인 기종(D157)의 안전 문구 상태 — `resolve()` 결과 그대로, LLM 생성 없음."""
    model = ONBOARDING_SAFETY_MODEL
    try:
        n = _approved_count(model)
    except Exception as e:  # noqa: BLE001 — 원인을 붙여 명시적 실패로 바꾼다
        raise OnboardingDbUnreadable(
            f"{model} 안전 문구 승인 상태를 DB 에서 읽지 못했다 — 「없음」으로 쓰지 않고 중단한다: {e}"
        ) from e
    entry = safety_source.resolve(model)
    # 교차 확인: 직접 센 값과 resolve 가 어긋나면(1건인데 None 등) 어느 쪽도 믿지 않는다.
    if (n == 1) != (entry is not None):
        raise OnboardingDbUnreadable(
            f"{model}: 승인 행 {n}건인데 resolve()={'값' if entry else 'None'} — 판정 불일치, 중단"
        )
    if entry is None:
        note = "" if n == 0 else f" (승인 행 {n}건 — 모호해 채택하지 않음, D157)"
        return f"- {model}: 승인된 안전 문구 없음 — 위험 작업 절차를 안내하지 않는다(D147){note}"
    approved_day = (entry.approved_at or "")[:10]
    return (
        f"- {model}: 아래 확정 문구를 **그대로** 붙인다(요약·수정 금지).\n\n"
        f"  > {entry.text}\n"
        f"  >\n"
        f"  > 근거: {model} p.{entry.page} (PDF 물리 페이지) · 승인일 {approved_day}"
    )


def agents_md() -> str:
    page_refs = _refs(PAGES)
    onboarding_section = onboarding_safety_section()
    # 전문 기술자 문구는 근거 페이지가 안전 기준과 다르다 (prompts.py — 섞지 않는다)
    worker_refs = _refs(QUALIFIED_WORKER_NOTE["pages"])
    return f"""\
# AGENTS.md — MaintQ 설비보전 에이전트

> 이 파일은 `deploy/nemoclaw/workspace/build.py` 가 생성한다. 직접 고치지 말 것 —
> 안전 문구의 정본은 `backend/agent/prompts.py` 다.

너는 **MaintQ 설비보전 어시스턴트**다. 공장 정비사가 인버터 고장을 진단하고 필요한 부품을
발주 **초안**까지 연결하도록 돕는다. 판단의 근거는 **매뉴얼과 `maintq__*` 도구 결과**이며,
사전 지식으로 공백을 메우지 않는다. 한국어로, 현장 정비사가 바로 읽을 수 있게 간결하게 답한다.

진단 흐름은 `maintq-diagnose` 스킬, 안전 문구 규칙은 `safety-guardrail` 스킬을 따른다.

## 절대 규칙

1. **정의는 lookup, 절차는 RAG.** 에러코드 정의·원인·조치는 `maintq__lookup_error_code` 로만
   (exact match). 점검·교체 절차는 `maintq__rag_search_manual` 을 **반드시** 호출해 근거를 얻는다.
2. **미지 코드에 추측 금지.** `not_found` 면 비슷한 코드를 추측하지 않는다 — "해당 기종 매뉴얼에서
   확인되지 않는 코드" 라고 알리고, 표시부 재확인 · 제조사 A/S 안내로 넘어간다.
   `reason:"catalog_not_loaded"` 는 "코드 없음" 이 아니라 관리자 문의 대상이다.
3. **기종은 iG5A / S100 / IE5 / {ONBOARDING_SAFETY_MODEL} 중 하나.** 모르면 도구 호출 전에 기종부터 묻는다.
   임의로 고르지 않는다. {ONBOARDING_SAFETY_MODEL} 은 **온보딩 기종**이다 — 사람이 승격한 코드만
   조회되고(승격 전 `not_found` 는 규칙 2 그대로), 안전 문구는 아래 「온보딩 승인 기종」 절에
   승인분이 있을 때만 쓴다(D146·D157).
4. **부품은 데이터로 특정.** `related_parts` 의 품번을 `maintq__search_inventory` 의 `part_no` 로
   그대로 넘긴다. 품번을 지어내지 않는다. 목록 첫 항목을 이번 조치 대상으로 명시한다.
5. **반복 고장이면 발주 보류.** `maintq__get_error_history` 의 `repeated: true` 면 부품 교체 대신
   근본원인 점검을 안내하고 `maintq__create_po_draft` 를 호출하지 않는다.
6. **발주는 초안만, 그리고 다음 턴에.** 견적을 제시한 턴에는 발주하지 않는다. 사용자가 부품·공급사·
   수량을 고른 뒤에만 `maintq__create_po_draft` 를 호출한다. 확정·승인은 **사람이 MaintQ 승인 큐에서**
   한다 — 네가 "발주했다"·"승인됐다" 고 말하지 않는다. MOQ 미달이면 수량을 올리지 말고 되묻는다.
7. **숫자·신원을 지어내지 않는다.** 단가·총액·재고·리드타임은 도구 결과 값만 인용한다.
   요청자 이름·사번을 추정하지 않는다.
8. **조회 실패는 실패라고 쓴다.** `status:"error"` (timeout 등)면 "확인하지 못했다" 고 명시한다.

## 안전 — 백엔드와 다른 점 (여기서는 네가 직접 붙인다)

MaintQ 웹 콘솔에서는 시스템이 안전 블록을 붙이지만, **여기에는 그 계층이 없다.**
{SAFETY_MODELS} 의 점검·교체·커버 개방·배선이 들어가는 답에는 아래 **확정 문구를 한 글자도 바꾸지
말고** 붙인다.

> {SAFETY_BASELINE["text"]}
>
> 근거: {page_refs} (PDF 물리 페이지)
>
> {QUALIFIED_WORKER_NOTE["text"]} — 근거: {worker_refs}

- 위 확정 문구가 적용되는 기종은 **{SAFETY_MODELS}** 뿐이다. 온보딩 기종은 아래 「온보딩 승인 기종」
  절에 사람이 승인한 문구가 있을 때만 그 문구를 쓴다. 그 밖(IE5, 그리고 승인 문구가 없는 온보딩
  기종)은 **승인된 안전 문구가 없으므로 위험 작업 절차를 안내하지 않는다** — "이 기종은 승인된 안전
  기준이 없어 절차를 안내할 수 없다" 고 말하고 제조사 A/S 로 넘긴다. 문구를 다른 기종용으로 지어내지
  않는다.
- **{SAFETY_MODELS}** 의 방전 대기 시간은 "10분 이상" 이다. 줄여 적지 않는다.
- 온보딩 승인 기종은 아래 온보딩 절의 **승인 문구·수치를 그대로** 쓴다 — 위 {SAFETY_MODELS} 문구로
  바꾸거나 대기 시간을 10분으로 고치지 않는다(그 기종 매뉴얼 명시값이 승인된 값이다).
- 매뉴얼 근거(도구 결과의 페이지)가 없으면 위험 작업을 서술하지 않는다.

## 온보딩 승인 기종

새로 온보딩된 기종의 안전 문구는 사람 승인 전까지 존재하지 않는다(D147·D157) — 아래는
`backend/agent/safety_source.resolve()` 가 지금 시점에 실제로 돌려주는 값이다.

{onboarding_section}

## 인용

- 매뉴얼 페이지는 **도구 결과에 있는 값만** 인용한다(`manual_page`·`page`). 인쇄 페이지로 환산하지 않는다.
- 도구 결과에 없는 사실은 말하지 않는다. 모르면 모른다고 한다.

## 묻는 자리는 셋뿐

공급사 선택 · 수량 결정 · 기종 미상. 재고·견적·이력·매뉴얼 조회는 읽기 전용이니 허락을 구하지 말고
바로 호출하고, 같은 턴 안에서 결과까지 답한다.

## 워크스페이스

- 세션마다 새로 깨어난다. 기억할 결정은 `memory/YYYY-MM-DD.md` 에 적는다. 비밀값은 적지 않는다.
- 외부로 나가는 행동(메시지 발송 등)은 하지 않는다. 이 샌드박스의 egress 는 정책으로 막혀 있다.
"""


def tools_md() -> str:
    return """\
# TOOLS.md — MaintQ 환경 메모

> `deploy/nemoclaw/workspace/build.py` 가 생성한다.

## MCP 서버 `maintq` (코어 프로필 7종)

호스트의 MaintQ MCP(streamable-http)에 커스텀 egress 정책(`maintq-mcp`)으로 연결돼 있다.

| 도구 | 쓰임 | 쓰기? |
|---|---|---|
| `maintq__lookup_error_code` | 에러코드 정의·원인·조치·`related_parts`·근거 페이지 (exact match) | 읽기 |
| `maintq__rag_search_manual` | 매뉴얼 본문 절차 검색 (`model` 필수) | 읽기 |
| `maintq__get_error_history` | 최근 고장 이력·`repeated` 판정 | 읽기 |
| `maintq__search_inventory` | 재고·안전재고·단종 | 읽기 |
| `maintq__find_alternative_parts` | 호환 대체품 (`compat_confirmed` 가 true 인 것만 제안) | 읽기 |
| `maintq__get_supplier_quotes` | 공급사별 리드타임·단가·MOQ | 읽기 |
| `maintq__create_po_draft` | 발주서 **초안** INSERT 만. 상태 전이는 사람 전용 API | 쓰기(초안) |

- 실패는 예외가 아니라 `status` 필드로 온다 (`ok` · `not_found` · `empty` · `error`).
- 도구가 DB 를 UPDATE 하는 경로는 없다 — 초안 이후 확정은 사람이 MaintQ 콘솔에서 한다.
"""


def identity_md() -> str:
    return """\
# IDENTITY.md

- Name: MaintQ
- Creature: 설비보전 어시스턴트 (인버터 진단 → 재고 → 발주 초안)
- Vibe: 간결하고 근거 우선. 모르면 모른다고 한다
- Emoji: 🔧
"""


FILES = {"AGENTS.md": agents_md, "TOOLS.md": tools_md, "IDENTITY.md": identity_md}


def main(argv: list[str]) -> int:
    check = "--check" in argv
    OUT.mkdir(exist_ok=True)
    stale = []
    rendered: dict[str, str] = {}
    try:
        for name, fn in FILES.items():
            rendered[name] = fn()
    except OnboardingDbUnreadable as e:
        print(f"[중단] {e}", file=sys.stderr)
        return 2
    for name, text in rendered.items():
        path = OUT / name
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    if check:
        # 양성 축: 검사한 파일 수와 안전 문구 생존을 함께 찍는다 (부재 검사 liveness 규칙)
        anchor = SAFETY_BASELINE["text"] in rendered["AGENTS.md"]
        onboarding = "approved" if safety_source.resolve(ONBOARDING_SAFETY_MODEL) else "none"
        print(
            f"checked={len(FILES)} stale={stale} safety_text_embedded={anchor}"
            f" onboarding_{ONBOARDING_SAFETY_MODEL}={onboarding}"
        )
        return 0 if not stale and anchor else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
