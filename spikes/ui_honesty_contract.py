# -*- coding: utf-8 -*-
"""UI 정직성 회귀 — "확인 안 된 항목을 확인된 것처럼 보여주는 UI" 를 코드 수준에서 막는다 (D87).

S18 실사 화면(`/technician/asset/{id}/ownership`)이 지키는 원칙은 하나다:
**미확인은 어떤 경로로도 확인처럼 보이지 않는다.** 이 스위트가 그 원칙의 방어선이다.

프론트에 테스트 러너가 없다(실측: `tsc --noEmit`·`next build` 뿐). 러너를 새로 들이지 않고
**이미 회귀에 있는 `tsc` + `node`** 만으로 2층 검사를 세운다 — 신규 의존성 0.

  제약 게이트 8건  `lib/ownership.ts`·`lib/maintValue.ts`·`lib/deadlines.ts`·`lib/riskGrade.ts` 가
                    React 를 쓰지 않고 `@/` 별칭도 쓰지 않는다(이 두 가지가 성립해야 L1 이 단독
                    `tsc` 로 돌아간다 — 계약이자 전제다)
  L1  순수 함수  15건  `lib/__checks__/ui_honesty.ts` 를 컴파일해 `node` 로 실행
                    (Stage 8/MQ-917 이 `lib/maintValue.ts` 의 4함수를 여기 추가했다.
                     Sprint 12(MQ-1202)가 `deadlines.ts`(2함수)·`riskGrade.ts`(1함수) 관련
                     L1-14·L1-15 를 더했다)
  L2  소스 정적      상태·판정 어휘를 다루는 **컴포넌트 전부**에 상태 문자열·색 토큰·
                    상태 비교가 0건 → **컴포넌트는 스스로 "확인/통과" 여부를 말할 수단이 없다**
  D64 성능 점수화 금지  스캔 대상 전체에 `OEE`·`종합효율`·`성능가동률` 0건 + 양성 축
                    (스캔 파일수 > 0 · 다른 지표 문자열이 실제로 발견됨)

  뮤턴트 8종  방어선이 실제로 깨지는지 매 실행 확인한다. 깨지지 않는 검사는 방어선이 아니다.
             원본 파일은 건드리지 않는다 — 임시 사본에 주입하고 사본만 컴파일한다.

★ Stage 6 W1 — L2 스캔 대상을 `VerificationMatrix.tsx` **한 파일**에서
  `components/asset/*.tsx` + `components/queue/Decision*.tsx` + `SignBar.tsx` 로 넓혔다.
  넓힌 이유는 리뷰어가 `DisposalPanel.tsx` 에서 **D87 위반 3종**(판정 어휘 지역 맵 · 성공색
  토큰 · `verdict === "CLEAR"` 비교)을 손으로 찾아냈기 때문이다 — D87 이 존재하는 이유가
  *"규약을 코드 리뷰로만 지키지 않는다"* 인데, 한 파일만 스캔하는 방어선은 그 이유를
  스스로 배신한다. 아울러 어휘 축 규칙 2종(어휘 직접 비교 · 어휘를 키로 쓰는 지역 맵)을
  추가했다 — 기존 4종만으로는 `verdict === "CLEAR"` 를 **잡지 못했다**(메타 검사로 고정).

★ Stage 8 (MQ-917) — L1 에 `lib/maintValue.ts` 4함수(`showMetric`·`showTrend`·
  `isHoldVerdict`·`estimateNotice`, D65·D74·D62)를 추가했다. L2 스캔 대상은
  `components/asset/*.tsx` 글롭이 Stage 7 신규 4파일(`MetricsAside`·`CriticalityDrawer`·
  `ExpenditureCard`·`RepairValuePanel`)을 이미 자동 포함해 12개로 늘었다 — 그래서 어휘 축에
  수리가치 판정 4종(`REPAIR_RECOMMENDED`·`REPLACE_RECOMMENDED`·`SELL_AS_IS`·
  `ROOT_CAUSE_FIRST`, `HOLD` 는 기존에 이미 있음)을 추가했다. D64(성능 점수화 금지) 축을
  신설했다 — `OEE` 라는 낱말은 이미 `MetricsAside.tsx` **주석**에 "계산하지 않는다"고
  적혀 있어 주석을 지우지 않고 스캔하면 위양성이 난다 — 그래서 이 축도 L2 와 같은
  `strip_comments` 오라클을 쓴다. (MQ-916 이 컷되며 원 명세가 요구했던 큐 상세 화면
  `L2_EXTRA` 추가는 하지 않는다 — `docs/sprints/sprint-9.md` §9-4 델타.)

★ MQ-1003 (Sprint 10) — MQ-1002 가 신설한 `components/queue/RepairDetail.tsx` 를 `L2_EXTRA`
  에 등재했다(`Decision*.tsx` 글롭이 접두어 불일치로 놓치는 파일). `L2_FILES_FLOOR` 를 실측
  32(하한, 이전 26)로 갱신했다. 이 스위트는 실측대로만 옮긴다 — 예상치를 미리 적지 않는다.

★ MQ-1202 (Sprint 12) — L1 에 `lib/deadlines.ts`(2함수)·`lib/riskGrade.ts`(1함수)를 추가해
  13건 → 15건이 됐다(L1-14·L1-15). 제약 게이트도 두 파일분(C5~C8)을 더해 4건 → 8건이 됐다 —
  L1 이 단독 `tsc` 컴파일로 돌려면 새 lib 파일도 C1~C4 와 같은 전제(React 미사용·`@/` 별칭
  미사용)를 지켜야 한다.

⚠ **L3(실 데이터 렌더)은 이 스위트가 검증하지 않는다.** 서버 기동·자산 순회는 이 태스크의
  검증 단위를 넘는다 — 출력 말미에 그 사실을 다시 고지한다. 초록 표를 보고 "전부 확인됐다"고
  읽는 것이야말로 이 스위트가 막으려는 그 오류다.

실행:  uv run python spikes/ui_honesty_contract.py
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
OWNERSHIP_TS = FRONTEND / "lib" / "ownership.ts"
MAINT_VALUE_TS = FRONTEND / "lib" / "maintValue.ts"
DEADLINES_TS = FRONTEND / "lib" / "deadlines.ts"
RISK_GRADE_TS = FRONTEND / "lib" / "riskGrade.ts"
A2A_TS = FRONTEND / "lib" / "a2a.ts"
CHECK_TS = FRONTEND / "lib" / "__checks__" / "ui_honesty.ts"
MATRIX_TSX = FRONTEND / "components" / "asset" / "VerificationMatrix.tsx"
DISPOSAL_TSX = FRONTEND / "components" / "asset" / "DisposalPanel.tsx"
FINDING_TSX = FRONTEND / "components" / "asset" / "FindingList.tsx"
REPAIR_VALUE_TSX = FRONTEND / "components" / "asset" / "RepairValuePanel.tsx"
MUTANT_DIR = FRONTEND / ".ui_honesty_mutant"

# L2 스캔 대상. **글롭으로 찾는다** — 파일을 새로 만들면 자동으로 스캔에 들어온다.
# 목록을 손으로 적으면 "새 컴포넌트가 조용히 빠지는" 경로가 생기고, 그게 W1 이 난 방식이다.
# MQ-1003(Sprint 10) — 원 명세가 요구한 큐 repair 상세 화면(`RepairDetail.tsx`)은 이제 실제로
#   존재한다. MQ-1002(Sprint 10)가 이 파일을 만들었으므로 `L2_EXTRA` 에 등재한다(`Decision*.tsx`
#   글롭은 접두어가 "Decision" 이 아니라서 잡지 못한다). 예전 주석("MQ-916 이 컷돼 파일 자체가
#   없다")은 Sprint 9 시점 기준이라 지금은 낡았다 — 지웠다.
# Sprint 10 이 `app/(console)/**/*.tsx`(라우트 페이지) 를 세 번째 글롭으로 더했다 — 이전에는
# `components/asset/`·`components/queue/` 만 보고 `app/` 라우트 파일은 전혀 스캔하지 않았다
# (예: 이번 브랜치의 `technician/equipment-status/[assetId]/page.tsx` 는 D87 감시 밖이었다).
# ⚠ 알려진 사각지대 — 색 토큰 규칙(`--green|--ok`)은 `--error-tx`·`--blue-tx`·`--orange-tx`
#   를 잡지 못한다. 이 토큰들은 판정색으로도 쓰이고 다른 곳에서 순수 UI 톤으로도 쓰여
#   전면 금지가 아직 구현돼 있지 않다 — 이번 수정 범위 밖(후속 과제로 이월).
L2_GLOBS = ("components/asset/*.tsx", "components/queue/Decision*.tsx", "app/(console)/**/*.tsx")
L2_EXTRA = (
    "components/queue/SignBar.tsx",
    "components/queue/RepairDetail.tsx",
    "components/queue/WithdrawalStatusPanel.tsx",
)
# 스캔 대상 하한. 줄면 파일이 빠진 것이다 (L1 건수 검사와 같은 취지)
# MQ-1003(Sprint 10) — `RepairDetail.tsx` 를 L2_EXTRA 에 추가하고, MQ-1001(같은 스프린트)이 만든
# `EvidenceBundlePanel.tsx`·`ExpenditureForm.tsx`(asset) + `evidence`·`expenditure` 라우트
# 페이지(app)가 기존 글롭에 이미 자동 포함돼 있어 실측치가 26 → 32 로 늘었다. 이 값은 실제 실행
# 결과("L2 스캔 대상 N개")를 그대로 옮긴 것이다 — 암산 아님.
# MQ-1205(Sprint 12) — MQ-1201~1204 가 신설한 4파일이 기존 글롭에 자동 편입됐다:
# `components/asset/DeadlinesPanel.tsx`·`RiskGradeGrid.tsx`(asset 글롭) +
# `app/(console)/manager/deadlines/page.tsx`·`manager/risk-grade/page.tsx`(app 글롭). 실측
# 32 → 36(+4파일, 파일당 6건이므로 L2 항목수는 192 → 216). 예상치(36)와 실측이 정확히 일치했다
# — `uv run python spikes/ui_honesty_contract.py` 출력의 "스캔 파일 36개"·"L2 216" 을 그대로 옮김.
# MQ-1611(Sprint 16) — Stage 3(MQ-1607~1610)가 신설한 파일 중 `components/asset/
# LoanAssessmentHistory.tsx`·`app/(console)/manager/a2a/page.tsx` 는 기존 글롭에 자동 편입,
# `components/queue/WithdrawalStatusPanel.tsx` 는 `Decision*.tsx` 접두어 불일치로 위에서
# `L2_EXTRA` 에 수동 등재했다. `components/chat/A2aResultCard.tsx` 는 `L2_GLOBS` 에
# `components/chat/*.tsx` 자체가 없어 편입 안 됨(다른 chat 컴포넌트와 동일).
# ⚠ sprint-16.md 계획서는 36 → 39(+3)로 추정했으나, **실측은 36 → 42(+6)** 다. Sprint 16 몫은
# 정확히 +3(`LoanAssessmentHistory.tsx`·`manager/a2a/page.tsx`·`WithdrawalStatusPanel.tsx`) —
# 나머지 +3(`components/asset/PoForm.tsx` + `app/(console)/technician/po/new/page.tsx` +
# `technician/po/[poId]/page.tsx`)는 Sprint 16 과 무관한 D111(발주 화면 직접 생성/수정,
# 커밋 `925184d`(PoForm.tsx)·`0bc342e`(technician/po/new)·`a5fa567`(technician/po/[poId])
# 가 이미 글롭에 편입시켜 놓은 것을 그동안 아무도
# `L2_FILES_FLOOR` 에 반영하지 않아 생긴 누적 차이다 — Sprint 16 이 만든 회귀가 아니다.
# 이 값은 실제 실행 결과("L2 스캔 대상 N개")를 그대로 옮긴 것이다 — 암산 아님.
L2_FILES_FLOOR = 42

TSC_ARGS = ["--module", "commonjs", "--target", "es2020", "--skipLibCheck"]

L3_NOTICE = (
    "L3(실 데이터 렌더)은 이 스위트가 검증하지 않는다 — 수동 체크리스트가 유일한 확인 수단이다"
)

# (섹션, 이름, 통과, 상세)
results: list[tuple[str, str, bool, str]] = []


def check(section: str, name: str, ok: bool, detail: str) -> None:
    results.append((section, name, bool(ok), str(detail).replace("\n", " ")[:200]))


# ---------------------------------------------------------------------------
# tsc / node 실행기


def _node() -> str:
    exe = shutil.which("node")
    if not exe:
        raise RuntimeError("node 를 찾을 수 없습니다 (PATH 확인)")
    return exe


def _tsc_cmd() -> list[str]:
    """로컬 typescript 를 직접 부른다. 없으면 `npx tsc` 로 떨어진다.

    `npx` 는 Windows 에서 `.cmd` 셸 래퍼라 shell=False 호출이 환경에 따라 갈린다 —
    `node node_modules/typescript/bin/tsc` 는 `npx tsc` 와 **같은 바이너리**이고 결과가 같다.
    """
    local = FRONTEND / "node_modules" / "typescript" / "bin" / "tsc"
    if local.exists():
        return [_node(), str(local)]
    npx = shutil.which("npx") or "npx"
    return [npx, "tsc"]


def compile_and_run(entry: Path, label: str) -> tuple[int, str, str]:
    """`entry` 를 컴파일해 실행한다 → (exit_code, stdout, note)."""
    with tempfile.TemporaryDirectory(prefix="ui_honesty_") as td:
        out = Path(td)
        rel = entry.relative_to(FRONTEND).as_posix()
        cp = subprocess.run(  # noqa: S603
            [*_tsc_cmd(), rel, "--outDir", str(out), *TSC_ARGS],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if cp.returncode != 0:
            return cp.returncode, "", f"[{label}] tsc 실패: {(cp.stdout or cp.stderr).strip()[:160]}"

        js = sorted(out.rglob("ui_honesty.js"))
        if not js:
            return 1, "", f"[{label}] 컴파일 산출물(ui_honesty.js)을 찾지 못했습니다"

        rp = subprocess.run(  # noqa: S603
            [_node(), str(js[0])],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        return rp.returncode, rp.stdout, (rp.stderr or "").strip()[:160]


L1_LINE = re.compile(r"^L1-(\d+)\|(PASS|FAIL)\|([^|]*)\|(.*)$")


def parse_l1(stdout: str) -> list[tuple[int, bool, str, str]]:
    out: list[tuple[int, bool, str, str]] = []
    for line in stdout.splitlines():
        m = L1_LINE.match(line.strip())
        if m:
            out.append((int(m.group(1)), m.group(2) == "PASS", m.group(3), m.group(4)))
    return out


# ---------------------------------------------------------------------------
# 제약 게이트 — import 문만 정확히 본다 (주석의 "React" 라는 낱말에 반응하지 않는다)

IMPORT_SPEC = re.compile(
    r"""(?:^|\n)\s*import\b[^\n;]*?from\s*['"]([^'"]+)['"]|"""
    r"""(?:^|\n)\s*import\s*['"]([^'"]+)['"]|"""
    r"""\brequire\s*\(\s*['"]([^'"]+)['"]\s*\)|"""
    r"""\bimport\s*\(\s*['"]([^'"]+)['"]\s*\)""",
)


def module_specifiers(src: str) -> list[str]:
    return [g for m in IMPORT_SPEC.finditer(src) for g in m.groups() if g]


# ---------------------------------------------------------------------------
# L2 — 소스 정적 검사. **오라클은 검증 대상에서 독립이다** (문자열을 여기 직접 적는다)

# 상태·판정 어휘. 백엔드 계약에서 그대로 옮겨 적은 것이지 프론트 코드에서 뽑지 않는다 —
# 검증 대상에서 기대치를 파생시키면 검사가 공허하게 통과한다(Sprint 5 Stage 4 전례).
#   판정 5종  `data/rules/engine.VERDICTS` (D79)
#   실사 3종  `04 §9` 소유권 실사 상태
#   근거 2종  `check_disposal_blockers.evidence_completeness`
#   큐 4종    `backend/services/decisions.ALLOWED_FROM`
#   수리가치 판정 4종(HOLD 는 위에 이미 있음)  `assess_repair_value`(`04 §13`) —
#     REPAIR_RECOMMENDED | REPLACE_RECOMMENDED | SELL_AS_IS | ROOT_CAUSE_FIRST (Stage 8/MQ-917)
STATE_WORDS = (
    "CLEAR",
    "CONDITIONAL",
    "BLOCKED",
    "HOLD",
    "INSUFFICIENT_FACTS",
    "VERIFIED",
    "UNVERIFIED",
    "PARTIAL",
    "COMPLETE",
    "LAW_TEXT_PENDING",
    "draft",
    "pending",
    "signed",
    "rejected",
    "REPAIR_RECOMMENDED",
    "REPLACE_RECOMMENDED",
    "SELL_AS_IS",
    "ROOT_CAUSE_FIRST",
)
_WORDS = "|".join(STATE_WORDS)

L2_RULES: list[tuple[str, str, str]] = [
    (
        '"확인됨" 문자열 리터럴 0건',
        r"확인됨",
        "컴포넌트가 스스로 확인 배지 문구를 만들 수 없다 — 문구는 ITEM_VIEW 한 곳에만 있다",
    ),
    (
        '"VERIFIED"·"UNVERIFIED" 문자열 리터럴 0건',
        r"VERIFIED",
        "컴포넌트가 상태 어휘를 직접 다룰 수 없다 (UNVERIFIED 포함)",
    ),
    (
        "`--green`·`--ok` 색 토큰 0건",
        r"--green|--ok",
        "색은 lib 의 맵 한 곳에서만 정해진다 — 컴포넌트에 자체 색 상수가 없다",
    ),
    (
        "`state ===` 상태 비교 0건",
        r"state\s*===",
        "컴포넌트가 상태로 분기하지 않는다 — 맵이 준 badge/tone 을 그대로 렌더한다",
    ),
    # ── W1 신설 2종 — 위 4종은 `verdict === "CLEAR"` 를 잡지 못했다 (메타 검사로 고정) ──
    (
        "상태·판정 어휘와의 직접 비교 0건 (`=== \"CLEAR\"` 류)",
        rf"""(?:[!=]==|\bcase)\s*["'](?:{_WORDS})["']|["'](?:{_WORDS})["']\s*[!=]==""",
        "어휘 해석은 lib 의 total 술어(isBlocking 등)가 한다 — 컴포넌트는 부르기만 한다",
    ),
    (
        "상태·판정 어휘를 키로 쓰는 지역 맵 0건",
        rf"""(?m)^\s*(?:{_WORDS})\s*:""",
        "같은 어휘의 두 번째 맵이 생기면 한 곳만 틀려도 화면이 갈린다 (D87 '맵 1곳')",
    ),
]

# ---------------------------------------------------------------------------
# 주석 제거 — **왜 필요한가**
#
# 스캔을 넓히자마자 `FindingList.tsx` 가 걸렸는데, 적발된 두 건이 전부
#   "`--ok-*` 토큰을 쓰지 않는다 (D87)"
# 라고 **적어 둔 주석**이었다. 주석의 낱말은 렌더되지 않으므로 위반이 아니고, 규칙을 무르게
# 하는 대신 **주석을 스캔에서 뺀다.** 이미 같은 판단의 선례가 이 파일 안에 있다 —
# 제약 게이트 C2 도 `'@/` 를 따옴표 뒤에서만 세고 주석의 언급은 세지 않는다.
#
# ⚠ 이 완화가 검사를 눈멀게 하지 않는다는 것은 뮤턴트 ⓔ 가 매 실행 증명한다
#   (주석이 아닌 **코드** 한 줄을 같은 파일에 넣으면 즉시 적발된다).
#
# 문자열/템플릿 안의 `//` 는 주석이 아니다(예: `"https://…"`) — 상태 기계로 구분한다.
# 템플릿 리터럴의 `${…}` 안쪽은 문자열로 취급한다(그 안의 주석은 실측상 없고, 잘못 잘라
# 내는 것보다 **덜 지우는 쪽**이 안전하다 — 덜 지우면 검사가 엄격해질 뿐이다).


def strip_comments(src: str) -> str:
    """주석을 공백으로 치환한다. 길이·줄 번호는 보존한다(문맥 출력이 어긋나지 않게)."""
    out = list(src)
    i, n = 0, len(src)
    state = "code"  # code | line | block | sq | dq | tpl
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if state == "code":
            if c == "/" and nxt == "/":
                state, out[i], out[i + 1] = "line", " ", " "
                i += 2
                continue
            if c == "/" and nxt == "*":
                state, out[i], out[i + 1] = "block", " ", " "
                i += 2
                continue
            if c == "'":
                state = "sq"
            elif c == '"':
                state = "dq"
            elif c == "`":
                state = "tpl"
        elif state == "line":
            if c == "\n":
                state = "code"
            else:
                out[i] = " "
        elif state == "block":
            if c == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                state = "code"
                i += 2
                continue
            if c != "\n":
                out[i] = " "
        elif state in ("sq", "dq", "tpl"):
            if c == "\\":
                i += 2
                continue
            # ⚠ `'`·`"` 는 **줄 끝에서 반드시 닫힌다** — JS 문자열은 줄을 넘지 못한다.
            #   이 한 줄이 없으면 JSX 본문의 아포스트로피(`don't`, `'문제 없음'`) 하나가
            #   파일 나머지를 통째로 "문자열"로 만들어 **검사가 눈이 먼다.** 피해를 한 줄로
            #   가둔다. (템플릿 리터럴은 정당하게 여러 줄이라 예외다)
            if c == "\n" and state in ("sq", "dq"):
                state = "code"
            elif (
                (state == "sq" and c == "'")
                or (state == "dq" and c == '"')
                or (state == "tpl" and c == "`")
            ):
                state = "code"
        i += 1
    return "".join(out)


def l2_scan(src: str) -> list[tuple[str, int, str, str]]:
    """→ [(규칙명, 적발 건수, 근거, 첫 적발 위치·문맥)]. 주석은 보지 않는다."""
    code = strip_comments(src)
    out: list[tuple[str, int, str, str]] = []
    for name, pattern, why in L2_RULES:
        hits = list(re.finditer(pattern, code))
        ctx = ""
        if hits:
            i = hits[0].start()
            # 문맥은 **원본**에서 뜬다 — 공백으로 치환된 사본을 보여 주면 사람이 못 읽는다
            ctx = f"L{code.count(chr(10), 0, i) + 1}: " + src[max(0, i - 30) : i + 40].replace(
                "\n", "⏎"
            )
        out.append((name, len(hits), why, ctx))
    return out


def l2_targets() -> list[Path]:
    """스캔 대상 파일. 정렬해 출력 순서를 고정한다."""
    found: set[Path] = set()
    for g in L2_GLOBS:
        found.update(FRONTEND.glob(g))
    for extra in L2_EXTRA:
        p = FRONTEND / extra
        if p.exists():
            found.add(p)
    return sorted(found, key=lambda p: p.relative_to(FRONTEND).as_posix())


# ---------------------------------------------------------------------------
# D64 — 성능 점수화 금지(D64). "없다"만 주장하지 않는다 — 양성 축(스캔 파일수 · 다른
# 지표 문자열이 실제로 발견됨)을 같은 판정에 묶는다(CLAUDE.md 부재검사 규칙). 주석은
# 위양성을 만든다(`MetricsAside.tsx` 가 "OEE 는 계산하지 않는다"고 **주석으로** 적어
# 두었다) — 그래서 L2 와 같은 `strip_comments` 오라클을 그대로 쓴다.

DENY_TOKENS = ("OEE", "종합효율", "성능가동률")
# 오라클은 검증 대상에서 독립이다 — `04 §11` 이 실제로 쓰는 지표 라벨을 손으로 옮겨 적었다
ANCHOR_TOKENS = ("MTBF", "MTTR", "가용도", "예방보전", "누적 수리비")


def d64_scan(targets: list[Path]) -> tuple[int, dict[str, int], int, list[str]]:
    """→ (금지어 총 적발수, 파일별 적발수, 양성 앵커 총 적중수, 앵커가 있는 파일명)."""
    deny_by_file: dict[str, int] = {}
    deny_total = 0
    anchor_total = 0
    anchor_files: list[str] = []
    for path in targets:
        code = strip_comments(path.read_text(encoding="utf-8"))
        n_deny = sum(code.count(tok) for tok in DENY_TOKENS)
        if n_deny:
            deny_by_file[path.name] = n_deny
        deny_total += n_deny
        n_anchor = sum(code.count(tok) for tok in ANCHOR_TOKENS)
        if n_anchor:
            anchor_files.append(path.name)
            anchor_total += n_anchor
    return deny_total, deny_by_file, anchor_total, anchor_files


# ---------------------------------------------------------------------------
# 뮤턴트 — 임시 사본에만 주입한다


def mutate_l1(marker: str, filename: str, old: str, new: str) -> tuple[bool, str]:
    """`lib` 사본에 뮤턴트를 주입해 L1 을 돌린다 → (기대대로 FAIL 했는가, 상세).

    `filename` 은 `lib/` 바로 아래 대상 파일명(`ownership.ts`·`maintValue.ts`).
    사본을 **frontend 안에** 두는 이유: `lib/types.ts` 가 `react` 타입을 참조하므로
    모듈 해석이 `frontend/node_modules` 로 올라갈 수 있어야 한다. 실행 후 지운다.
    """
    if MUTANT_DIR.exists():
        shutil.rmtree(MUTANT_DIR, ignore_errors=True)
    try:
        shutil.copytree(FRONTEND / "lib", MUTANT_DIR / "lib")
        target = MUTANT_DIR / "lib" / filename
        src = target.read_text(encoding="utf-8")
        if src.count(old) != 1:
            # ⛔ 여기서 조용히 넘어가면 "뮤턴트를 주입하지 못했는데 통과"가 된다 —
            #    Stage 4 에서 났던 '공허하게 통과하는 검사' 그 자체다.
            return False, f"뮤턴트 주입 실패 — 앵커 문자열 {src.count(old)}회 발견 (1회여야 함)"
        target.write_text(src.replace(old, new), encoding="utf-8")

        code, stdout, note = compile_and_run(MUTANT_DIR / "lib" / "__checks__" / "ui_honesty.ts", marker)
        rows = parse_l1(stdout)
        failed = [f"L1-{i}" for i, ok, _, _ in rows if not ok]
        ok = code != 0 and bool(failed)
        detail = f"L1 {len(rows)}건 중 FAIL {failed or '없음'}"
        if not rows:
            detail += f" · 출력 없음 ({note})"
        return ok, detail
    finally:
        shutil.rmtree(MUTANT_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
# 제약 게이트 — React 미사용·`@/` 별칭 미사용을 확인한다 (L1 이 단독 `tsc` 로 돌 수 있는 전제).
# C1~C4(ownership.ts·maintValue.ts) 가 쓰던 로직을 그대로 헬퍼로 뽑았다 — 새 lib 파일이
# 늘 때마다(C5~C8: deadlines.ts·riskGrade.ts, MQ-1202) 파라미터만 바꿔 재호출한다.


def constraint_gate(react_id: str, alias_id: str, filename: str, path: Path, note: str = "") -> None:
    src = path.read_text(encoding="utf-8")
    specs = module_specifiers(src)
    react_specs = [s for s in specs if s == "react" or s.startswith("react/") or s == "react-dom"]
    check(
        "제약",
        f"{react_id} lib/{filename} 가 React 를 들여오지 않는다{note}",
        not react_specs,
        f"import 대상 {len(specs)}개 {specs or '(없음)'} · react 계열 {react_specs or '0건'}",
    )
    alias_specs = [s for s in specs if s.startswith("@/")]
    # 따옴표 뒤의 `@/` 만 센다 — 주석에서 백틱으로 규칙을 설명하는 문장에 반응하면 안 된다
    quoted_alias = re.findall(r"""['"]@/""", src)
    check(
        "제약",
        f"{alias_id} lib/{filename} 가 `@/` 경로 별칭을 쓰지 않는다 (단독 tsc 컴파일 가능){note}",
        not alias_specs and not quoted_alias,
        f"별칭 import {alias_specs or '0건'} · 따옴표 뒤 '@/' {len(quoted_alias)}건 "
        f"(주석 언급은 세지 않는다)",
    )


def run() -> None:
    # ── 제약 게이트의 오라클 (P30) ─────────────────────────────────────────
    #
    # C1~C8 은 전부 **부재 검사**(`not react_specs` · `not alias_specs`)인데, 대상
    # `frontend/lib/*.ts` 4개는 **import 문이 0개인 것이 정상**이다(전부 `export`).
    # 즉 그 파일들 안에는 걸 앵커가 없고, `IMPORT_SPEC` 이 한 글자도 못 잡게 망가져도
    # C1~C8 은 전건 통과한다 — 실제로 지금까지 그 정규식은 **한 번도 매치한 적이 없다**.
    # 대상에 앵커를 못 만들므로 **오라클을 스파이크 안에 둔다**: 알려진 픽스처를 넣어
    # 추출기가 살아 있음을 단언한다 (L2 뮤턴트 메타검사와 같은 방식).
    fixture = """
    import React from 'react'
    import 'react/jsx-runtime'
    const rd = require("react-dom")
    const lazy = import('@/lib/ownership')
    // 주석의 react 와 '@/' 는 세지 않는다
    const s = "이 문장은 import 가 아니다"
    """
    got = sorted(set(module_specifiers(fixture)))
    want = sorted({"react", "react/jsx-runtime", "react-dom", "@/lib/ownership"})
    check(
        "메타",
        "IMPORT_SPEC 오라클 — 4개 문법(from·부수효과·require·동적 import)을 실제로 추출한다 "
        "(C1~C8 은 부재 검사라 이 오라클이 없으면 정규식이 죽어도 통과한다)",
        got == want,
        f"픽스처 추출 {len(got)}건 {got} · 기대 {want}",
    )

    # ── 제약 게이트 ────────────────────────────────────────────────────────
    constraint_gate("C1", "C2", "ownership.ts", OWNERSHIP_TS)
    constraint_gate("C3", "C4", "maintValue.ts", MAINT_VALUE_TS, " (MQ-917)")
    constraint_gate("C5", "C6", "deadlines.ts", DEADLINES_TS, " (MQ-1202)")
    constraint_gate("C7", "C8", "riskGrade.ts", RISK_GRADE_TS, " (MQ-1202)")
    constraint_gate("C9", "C10", "a2a.ts", A2A_TS, " (MQ-1605)")

    # ── L1 ────────────────────────────────────────────────────────────────
    code, stdout, note = compile_and_run(CHECK_TS, "L1")
    rows = parse_l1(stdout)
    if not rows:
        check("L1", f"L1 실행 실패 — {note or '출력 없음'}", False, f"exit={code}")
    for idx, ok, name, detail in rows:
        check("L1", f"L1-{idx} {name}", ok, detail)
    check(
        "L1",
        "L1 건수 15건 (줄었으면 단언이 사라진 것이다 — MQ-917 이 maintValue.ts 4건을 더했고, "
        "Sprint 12 MQ-1202 가 deadlines.ts·riskGrade.ts 2건을 더했다)",
        len(rows) == 15 and (code == 0) == all(o for _, o, _, _ in rows),
        f"{len(rows)}건 · node exit={code}",
    )
    # 위 '건수' 검사는 15건 밖의 메타 검사다 — 표에는 남기되 계약 15건에는 세지 않는다
    results[-1] = ("메타", results[-1][1], results[-1][2], results[-1][3])

    # ── L2 ────────────────────────────────────────────────────────────────
    targets = l2_targets()
    check(
        "메타",
        f"L2 스캔 대상 {len(targets)}개 (하한 {L2_FILES_FLOOR} — 줄면 파일이 빠진 것이다)",
        len(targets) >= L2_FILES_FLOOR,
        " · ".join(p.name for p in targets),
    )
    for f_i, path in enumerate(targets, start=1):
        src = path.read_text(encoding="utf-8")
        for r_i, (name, hits, why, ctx) in enumerate(l2_scan(src), start=1):
            check(
                "L2",
                f"L2-{f_i}.{r_i} {path.name} — {name}",
                hits == 0,
                f"적발 {hits}건" + (f" · …{ctx}…" if ctx else "") + f" · {why}",
            )

    # ── D64(성능 점수화 금지) ───────────────────────────────────────────────
    deny_total, deny_by_file, anchor_total, anchor_files = d64_scan(targets)
    check(
        "D64",
        "D64 — `OEE`·`종합효율`·`성능가동률` 0건 + 양성 축(스캔 파일>0 · 다른 지표 문자열 실재)",
        deny_total == 0 and len(targets) > 0 and anchor_total > 0,
        f"금지어 적발 {deny_total}건{f' {deny_by_file}' if deny_by_file else ''} · "
        f"스캔 파일 {len(targets)}개 · 지표 문자열 적중 {anchor_total}건 "
        f"({len(anchor_files)}개 파일: {', '.join(sorted(anchor_files)[:4])}"
        f"{'…' if len(anchor_files) > 4 else ''})",
    )

    # ── 주석 제거기 자가 검증 ──────────────────────────────────────────────
    # 오라클은 손으로 적은 픽스처다 (검증 대상 소스에서 파생시키지 않는다).
    fixture = "\n".join(
        [
            'const url = "https://ex.com";',           # 문자열 안 `//` 는 주석이 아니다
            "// --ok-bd 는 주석이므로 안 보인다",
            "/* state === \"pending\" 도 주석이다 */",
            "const live = \"var(--ok-bd)\";",          # 코드 — 반드시 보인다
            "const t = `x ${1} y`;",
            "<p>don't 라고 써도 다음 줄은 코드다</p>",
            "const also = state === \"pending\";",      # 위 아포스트로피 뒤에도 적발돼야 한다
        ]
    )
    stripped = strip_comments(fixture)
    fixture_ok = (
        "https://ex.com" in stripped  # 문자열은 남는다
        and stripped.count("--ok-bd") == 1  # 주석의 1건은 사라지고 코드의 1건만 남는다
        and stripped.count('state === "pending"') == 1  # 주석 1 · 코드 1 → 코드만
        and len(stripped) == len(fixture)  # 길이(=줄 번호) 보존
    )
    check(
        "메타",
        "주석 제거기 — 주석만 지우고 문자열·코드는 남긴다 (손으로 적은 픽스처)",
        fixture_ok,
        "--ok-bd {}건(기대 1) · state=== {}건(기대 1) · URL보존={} · 길이보존={}".format(
            stripped.count("--ok-bd"),
            stripped.count('state === "pending"'),
            "예" if "https://ex.com" in stripped else "아니오",
            "예" if len(stripped) == len(fixture) else "아니오",
        ),
    )

    # ── 뮤턴트 ─────────────────────────────────────────────────────────────
    ok_a, det_a = mutate_l1(
        "ⓐ",
        "ownership.ts",
        'UNVERIFIED: { badge: "미확인", tone: "warn" },',
        'UNVERIFIED: { badge: "미확인", tone: "ok" },',
    )
    check("뮤턴트", "ⓐ ITEM_VIEW.UNVERIFIED.tone → 'ok' 로 바꾸면 L1 이 FAIL 한다", ok_a, det_a)

    matrix_src = MATRIX_TSX.read_text(encoding="utf-8")
    mutant_b = matrix_src.replace(
        "      {rows.map((row, i) => (",
        '      {rows.map((row) => { if (row.state === "UNVERIFIED") return <Green/>; })}\n'
        "      {rows.map((row, i) => (",
        1,
    )
    scanned = l2_scan(mutant_b)
    caught = [n for n, h, _, _ in scanned if h > 0]
    check(
        "뮤턴트",
        "ⓑ VerificationMatrix 에 `if (row.state === \"UNVERIFIED\") return <Green/>` 주입 → L2 FAIL",
        mutant_b != matrix_src and len(caught) >= 2,
        f"주입={'성공' if mutant_b != matrix_src else '실패'} · 적발 규칙 {len(caught)}건 {caught}",
    )

    ok_c, det_c = mutate_l1(
        "ⓒ",
        "ownership.ts",
        "      rows.push(emptyRow(name));\n      continue;",
        "      continue;",
    )
    check("뮤턴트", "ⓒ toRows 가 항목 0건 카테고리를 스킵하면 L1 이 FAIL 한다", ok_c, det_c)

    # ── ⓓ 리뷰어(W1)가 손으로 찾아낸 그 위반을 기계가 잡는가 ──────────────────
    #   `DisposalPanel` 은 확대 전에는 **스캔 대상이 아니었다.** 그래서 아래 두 검사를 함께 둔다:
    #     ⓓ  확대 후: 잡는다
    #     ⓓ' 확대 전 규칙 4종 + 대상 1파일이었다면: **못 잡았다** — 확대가 실효한 근거
    disposal_src = DISPOSAL_TSX.read_text(encoding="utf-8")
    mutant_d = disposal_src.replace(
        "  const blockers = recArr(result.blockers).map(toFinding);",
        '  if (result.verdict === "CLEAR") return <Green/>;\n'
        "  const blockers = recArr(result.blockers).map(toFinding);",
        1,
    )
    caught_d = [n for n, h, _, _ in l2_scan(mutant_d) if h > 0]
    check(
        "뮤턴트",
        'ⓓ DisposalPanel 에 `if (result.verdict === "CLEAR") return <Green/>` 주입 → L2 FAIL',
        mutant_d != disposal_src and len(caught_d) >= 1,
        f"주입={'성공' if mutant_d != disposal_src else '실패'} · 적발 규칙 {len(caught_d)}건 {caught_d}",
    )
    # 확대 전 규칙 4종(어휘 축 2종 제외)으로 같은 뮤턴트를 재채점한다
    old_rules = L2_RULES[:4]
    stripped_d = strip_comments(mutant_d)
    caught_old = [nm for nm, pat, _ in old_rules if re.search(pat, stripped_d)]
    check(
        "메타",
        "ⓓ' 확대 전 규칙 4종으로는 같은 뮤턴트를 **못 잡는다** (확대가 실효한 이유)",
        not caught_old,
        f"구 규칙 적발 {len(caught_old)}건 {caught_old or '(없음 — 통과해 버린다)'}",
    )

    # ── ⓔ 주석 제거가 검사를 눈멀게 하지 않았는가 (파일마다 개별 증명) ────────
    #   주석만 지운 것이 맞다면, **코드** 한 줄을 붙였을 때 모든 파일에서 즉시 적발돼야 한다.
    #   어떤 파일이 문자열 상태로 잘못 끝나 있으면 여기서 그 파일만 FAIL 로 드러난다.
    leak = '\nconst __LEAK = state === "pending" ? "var(--ok-bd)" : "";\n'
    blind: list[str] = []
    for path in targets:
        src = path.read_text(encoding="utf-8")
        if len([n for n, h, _, _ in l2_scan(src + leak) if h > 0]) < 2:
            blind.append(path.name)
    check(
        "뮤턴트",
        "ⓔ 스캔 대상 전 파일에 코드 한 줄(`state === \"pending\"` + `--ok-bd`) 주입 → 전부 적발",
        not blind,
        f"대상 {len(targets)}개 · 눈먼 파일 {blind or '0건'} (주석 제거가 코드까지 지웠다면 여기서 드러난다)",
    )

    # ── ⓕⓖⓗ (Stage 8 / MQ-917) — maintValue.ts 4함수 · 수리가치 어휘 축 방어선 ───────────
    ok_f, det_f = mutate_l1(
        "ⓕ",
        "maintValue.ts",
        'if (v === null) return { text: "판단 근거 부족", kind: "insufficient" };',
        'if (v === null) return { text: "0", kind: "value" };',
    )
    check("뮤턴트", "ⓕ showMetric(null) → '0' 으로 바꾸면 L1 이 FAIL 한다 (MQ-917)", ok_f, det_f)

    repair_panel_src = REPAIR_VALUE_TSX.read_text(encoding="utf-8")
    anchor_g = "  const view = repairValueVerdictView(result.verdict);"
    mutant_g = repair_panel_src.replace(
        anchor_g,
        '  if (result.verdict === "REPAIR_RECOMMENDED") return null;\n' + anchor_g,
        1,
    )
    caught_g = [n for n, h, _, _ in l2_scan(mutant_g) if h > 0]
    check(
        "뮤턴트",
        'ⓖ RepairValuePanel(Stage 7 신규)에 `verdict === "REPAIR_RECOMMENDED"` 직접비교 주입 → L2 FAIL (MQ-917)',
        mutant_g != repair_panel_src and len(caught_g) >= 1,
        f"주입={'성공' if mutant_g != repair_panel_src else '실패'} · 적발 규칙 {len(caught_g)}건 {caught_g}",
    )

    ok_h, det_h = mutate_l1(
        "ⓗ",
        "maintValue.ts",
        "  return `이 값은 ${source} 기반 추정치이며 실거래가·실측값이 아닙니다 (D65·D74).`;",
        "  return null;",
    )
    check(
        "뮤턴트",
        "ⓗ estimateNotice 의 고지 문자열을 지우면(source 있어도 항상 null) L1 이 FAIL 한다 (MQ-917 · D65·D74)",
        ok_h,
        det_h,
    )


def main() -> None:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")

    print("UI 정직성 회귀 (D87) — 미확인이 확인처럼 보이는 경로가 코드에 없는지\n")

    for path in (
        OWNERSHIP_TS,
        MAINT_VALUE_TS,
        DEADLINES_TS,
        RISK_GRADE_TS,
        A2A_TS,
        CHECK_TS,
        MATRIX_TSX,
        DISPOSAL_TSX,
        FINDING_TSX,
        REPAIR_VALUE_TSX,
    ):
        if not path.exists():
            check("치명", f"필수 파일 없음 — {path.relative_to(ROOT).as_posix()}", False, "")

    if not any(sec == "치명" for sec, _, _, _ in results):
        try:
            run()
        except Exception:  # noqa: BLE001 — 표는 어떤 경우에도 살아남는다
            check("치명", "스위트 실행 중 예외", False, traceback.format_exc().strip().splitlines()[-1])
            print(traceback.format_exc(), file=sys.stderr)
        finally:
            shutil.rmtree(MUTANT_DIR, ignore_errors=True)

    width = max((len(n) for _, n, _, _ in results), default=20)
    print("─" * (width + 40))
    for _sec, name, ok, detail in results:
        print(f"  {'PASS' if ok else 'FAIL':<4}  {name:<{width}}  {detail}")
    print("─" * (width + 40))

    contract = [r for r in results if r[0] in ("L1", "L2", "D64")]
    others = [r for r in results if r[0] not in ("L1", "L2", "D64")]
    print(
        f"\n신규 계약 검사 {len(contract)}건 (L1 {sum(1 for r in contract if r[0] == 'L1')} · "
        f"L2 {sum(1 for r in contract if r[0] == 'L2')} · "
        f"D64 {sum(1 for r in contract if r[0] == 'D64')}) — "
        f"PASS {sum(1 for r in contract if r[2])} / FAIL {sum(1 for r in contract if not r[2])}"
    )
    constraints = sum(1 for r in results if r[0] == "제약")
    mut = sum(1 for r in results if r[0] == "뮤턴트")
    meta = sum(1 for r in results if r[0] == "메타")
    print(
        f"제약 게이트 {constraints}건 · 뮤턴트 {mut}종 · 메타 {meta}건 — "
        f"PASS {sum(1 for r in others if r[2])} / FAIL {sum(1 for r in others if not r[2])}"
    )

    # ⛔ 초록 위장 금지 — 마지막 줄은 언제나 "무엇을 보지 않았는가" 다
    print(f"\n⚠ {L3_NOTICE}")
    print(
        "   이 스위트가 보는 것: 순수 함수의 상태→표시 변환 · 컴포넌트 소스의 우회 수단 유무.\n"
        "   보지 않는 것: 브라우저 렌더 결과 · 실 자산 9건의 실제 응답 · 색상 대비 · 스크린샷."
    )

    failed = [n for _, n, ok, _ in results if not ok]
    if failed:
        raise SystemExit(f"\n[실패] {len(failed)}건:\n  - " + "\n  - ".join(failed))
    print(f"\n통과 — 계약 {len(contract)}건 + 제약 {constraints} + 뮤턴트 {mut} + 메타 {meta}")


if __name__ == "__main__":
    main()
