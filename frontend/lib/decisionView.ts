/**
 * 처분 결정 어휘 → 화면 표시. `lib/queueState.ts` 와 **같은 태도**의 total 맵이다 (D87).
 *
 * 여기 있는 맵은 전부 "모르면 warn, 모르면 잠근다"로 떨어진다:
 *   `verdictView`     판정 → 배너 톤·색·설명. 맵 밖 값은 `warn` + 원문 (절대 성공 톤 아님)
 *   `signability`     상태 → 서명 경로를 열 것인가. 맵 밖 값은 **열지 않는다**
 *   `signErrorView`   409/503 `reason` → 사람이 할 일. 맵 밖 값은 원문 + 재조회
 *   `evidenceCompletenessView`  근거 수집 상태 → 배지. 맵 밖 값은 warn + 원문
 *
 * ⛔ 이 파일은 **React 를 import 하지 않고 `@/` 별칭도 쓰지 않는다** (D87) —
 *   `tsc` 로 단독 컴파일해 검증할 수 있어야 하기 때문이다. 마크업은 컴포넌트가 정하지만
 *   **색(CSS 변수 문자열)은 여기서 정한다** — 컴포넌트에 성공색 토큰이 남으면 D87 의
 *   "맵 밖 값은 warn" 이 컴포넌트 분기 한 줄로 우회된다.
 *
 * ⚠ 왜 `lib/queueState.ts` 에 넣지 않았나: Stage 6 은 `queueState.ts` 를 **읽기 전용**으로
 *   묶어 3병렬 태스크의 충돌을 피한다(MQ-709a 가 놓은 장치). 판정 어휘가 큐 어휘와 함께
 *   살 곳은 결국 그 파일이므로, 병렬이 끝나면 합치는 것이 맞다.
 *
 * ★ Stage 6 W1 — 같은 어휘(`BLOCKED`/`HOLD`/`INSUFFICIENT_FACTS`/`CONDITIONAL`/`CLEAR`)의
 *   **두 번째 맵이 `components/asset/DisposalPanel.tsx` 안에 따로 있었다.** 두 맵은 지금은
 *   같은 방향(맵 밖 = warn)이었지만, 두 곳이면 한 곳만 틀려도 화면이 갈린다 — D87 이
 *   "전역 total 맵 1곳"이라고 못박은 이유가 그것이다. 그래서 **어휘·톤·색·차단 여부를 전부
 *   이 파일로 합치고**, 화면별로 다른 것은 **문안뿐**이라 한 엔트리 안에 두 필드로 둔다:
 *     `note`      결정 상세(서명 화면)에서 쓰는 한 줄
 *     `guidance`  사전판정 화면에서 쓰는 안내 (같은 판정을 "지금 무엇을 하라"로 말한다)
 *   문안을 하나로 합치지 않은 이유는 두 화면의 독자가 다르기 때문이고, 합치면 어느 한쪽의
 *   문안이 조용히 바뀐다. **어휘가 한 곳이면 D87 은 충족된다 — 필드가 하나여야 하는 게 아니다.**
 */
import type { QueueTone } from "./queueState";

/**
 * 판정 배너의 색 축. `QueueTone` 보다 잘게 나뉜다 — `BLOCKED`(실선 적색)·`HOLD`(점선 적색)·
 * `INSUFFICIENT_FACTS`(점선 회색)는 셋 다 `QueueTone` 으로는 `danger` 한 칸에 뭉치는데,
 * 사전판정 화면은 셋을 눈으로 구분해야 한다("확정 차단" vs "단정하지 않음" vs "판정 불성립").
 *
 * ⛔ 성공색(`--ok-*`)이 붙는 칸은 `clear` **하나뿐이다.** 나머지 5칸은 어떤 경로로도
 *   초록이 되지 않는다 — 맵 밖 값은 `unknown` 으로 떨어진다 (D87).
 */
export type VerdictSkinTone =
  | "clear"
  | "conditional"
  | "block"
  | "hold"
  | "insufficient"
  | "unknown";

const VERDICT_SKIN: Record<VerdictSkinTone, string> = {
  clear: "border:1px solid var(--ok-bd);background:var(--ok-bg);color:var(--ok-tx)",
  conditional: "border:1px solid var(--cite-bd);background:var(--cite-bg);color:var(--blue-tx)",
  block: "border:1.5px solid var(--error-tx);background:transparent;color:var(--error-tx)",
  hold: "border:1.5px dashed var(--error-tx);background:transparent;color:var(--error-tx)",
  insufficient: "border:1.5px dashed var(--dim2);background:transparent;color:var(--ink2)",
  unknown: "border:1.5px dashed var(--error-tx);background:transparent;color:var(--error-tx)",
};

export interface VerdictLabel {
  /** 표시 문자열. 모르는 값은 **원문 그대로** — 번역·추측하지 않는다 */
  text: string;
  /** 한 줄 설명(결정 상세). "안 된다"로 끝내지 않고 무엇을 뜻하는지 말한다 */
  note: string;
  /** 사전판정 화면 안내. 같은 판정을 "지금 무엇을 하라"로 말한다 */
  guidance: string;
  tone: QueueTone;
  skinTone: VerdictSkinTone;
  /** `skinTone` 이 가리키는 CSS 문자열. 컴포넌트가 색 토큰을 직접 들지 않게 여기서 푼다 */
  skin: string;
  known: boolean;
  /**
   * 해소 경로 목록을 함께 보여야 하는가.
   * **모르는 판정도 `true`** 다 — 모르는 값을 "볼 것 없음"으로 접으면 그게 곧 성공 톤이다.
   */
  resolveRequired: boolean;
  /**
   * `backend/services/decisions.BLOCKING_VERDICTS` 의 화면 쪽 사본 — override 없이는
   * 서명이 통과하지 못하는 어휘인가.
   * **모르는 판정도 `true`** 다 (아래 `isBlocking` 주석 참조).
   */
  blocking: boolean;
}

/**
 * `data/rules/engine.VERDICTS` 의 5종.
 * `BLOCKED`·`HOLD`·`INSUFFICIENT_FACTS` 는 **차단 어휘**(`backend/services/decisions.py`
 * `BLOCKING_VERDICTS`)이고, 서명 시점에 override 없이는 통과하지 못한다.
 *
 * ⛔ `INSUFFICIENT_FACTS` 를 중립으로 두지 않는다 — "근거가 부족하다"는 "문제 없다"가 아니다 (D65).
 */
type VerdictEntry = Omit<VerdictLabel, "known" | "skin">;

const VERDICT_LABEL: Record<string, VerdictEntry> = {
  CLEAR: {
    text: "CLEAR",
    note: "차단 사유가 발견되지 않았습니다. 서명 경로가 열려 있습니다.",
    guidance:
      "적재된 룰 중 걸린 것이 없습니다. 아래 '고려하지 않은 것'과 한계 고지를 함께 읽으세요.",
    tone: "ok",
    skinTone: "clear",
    resolveRequired: false,
    blocking: false,
  },
  CONDITIONAL: {
    text: "CONDITIONAL",
    note: "차단은 아니지만 선결 조건이 있습니다 — 이행 여부를 확인하고 서명하십시오.",
    guidance: "선행조건을 이행한 뒤 진행할 수 있습니다. 이행 여부는 이 화면이 기록하지 않습니다.",
    tone: "info",
    skinTone: "conditional",
    resolveRequired: false,
    blocking: false,
  },
  BLOCKED: {
    text: "BLOCKED",
    note: "처분을 막는 근거가 있습니다. 우회(override) 없이는 서명할 수 없습니다.",
    guidance:
      "지금 상태로는 처분할 수 없습니다. 아래 해소 경로를 밟거나, 서명 단계에서 우회(override)와 사유가 필요합니다.",
    tone: "danger",
    skinTone: "block",
    resolveRequired: true,
    blocking: true,
  },
  HOLD: {
    text: "HOLD",
    note: "판단을 멈출 사유가 있습니다. 해소 전에는 처분을 진행할 수 없습니다.",
    guidance:
      "경계 구간이라 단정하지 않았습니다 — 전문가 검토가 필요합니다. '문제 없음'이 아닙니다.",
    tone: "danger",
    skinTone: "hold",
    resolveRequired: true,
    blocking: true,
  },
  INSUFFICIENT_FACTS: {
    text: "INSUFFICIENT_FACTS",
    note: "판단에 필요한 사실이 부족합니다 — '문제 없음'이 아니라 '아직 모른다'입니다.",
    guidance:
      "사실이 없어 판정 자체가 성립하지 않았습니다 — '조건 미해당'이 아닙니다. 누락된 값을 채우면 다시 판정할 수 있습니다.",
    tone: "danger",
    skinTone: "insufficient",
    resolveRequired: true,
    blocking: true,
  },
};

export function verdictView(verdict: string | null | undefined): VerdictLabel {
  if (!verdict) {
    // 처분서에 판정이 없을 수는 없다 — 없다면 그 사실 자체가 경고다. 영역을 숨기지 않는다.
    return {
      text: "판정 없음",
      note: "백엔드가 판정(verdict)을 싣지 않았습니다. 확인 전까지 '통과'로 읽지 마십시오.",
      guidance:
        "판정 값이 응답에 없습니다. 해석하지 않고 그 사실만 알립니다 — 계약 위반 신호일 수 있습니다.",
      tone: "warn",
      skinTone: "unknown",
      skin: VERDICT_SKIN.unknown,
      known: false,
      resolveRequired: true,
      blocking: true,
    };
  }
  const known = VERDICT_LABEL[verdict];
  if (!known) {
    return {
      text: verdict,
      note: "이 화면이 모르는 판정 값입니다 — 원문 그대로 표시합니다. 담당자 확인이 필요합니다.",
      guidance:
        "계약(D79)에 없는 판정 어휘입니다. 해석하지 않고 원문 그대로 보여 줍니다 — 계약 위반 신호일 수 있습니다.",
      tone: "warn",
      skinTone: "unknown",
      skin: VERDICT_SKIN.unknown,
      known: false,
      resolveRequired: true,
      blocking: true,
    };
  }
  return { ...known, skin: VERDICT_SKIN[known.skinTone], known: true };
}

/**
 * 배너 제목. **모르는 값에는 `⚠` 를 붙인다** — 원문을 그대로 두면 미지 어휘가 정상 판정과
 * 같은 무게로 읽힌다. 두 화면(결정 상세·사전판정)이 각자 `known ? text : "⚠ " + text` 를
 * 쓰고 있었는데, 그런 삼항 하나가 곧 "컴포넌트가 상태를 해석하는 자리"다 (D87).
 */
export function verdictHeadline(verdict: string | null | undefined): string {
  const v = verdictView(verdict);
  return v.known ? v.text : `⚠ ${v.text}`;
}

/**
 * override 없이는 서명이 통과하지 못하는 판정인가 (`BLOCKING_VERDICTS` 사본).
 *
 * ⛔ **모르는 판정은 `true`** 다. 이전 구현(`DisposalPanel` 의 `verdict === "BLOCKED" || …`)은
 *   모르는 어휘를 자동으로 `false` 로 떨어뜨려 "초안이 만들어지면 승인 큐로 제출하세요" 라는
 *   **안심 문안**을 붙였다 — 미지 값이 성공 어포던스로 새는 D87 그 자체다. 총칭 술어로 바꾸면서
 *   미지 값의 기본을 차단 쪽으로 뒤집는다(알려진 5종의 동작은 이전과 동일하다).
 */
export function isBlocking(verdict: string | null | undefined): boolean {
  return verdictView(verdict).blocking;
}

/**
 * D78 부수 확정의 화면 쪽 감시 — `SALE` 은 `VAT-INVOICE` 선행조건이 **항상** 발화하므로
 * `CLEAR` 가 나올 수 없다. 나왔다면 룰 카탈로그·엔진 쪽 계약 위반 신호다.
 *
 * 컴포넌트가 `verdict === "CLEAR" && mode === "SALE"` 을 직접 쓰지 않게 총칭 술어로 낸다 —
 * 어휘 리터럴이 컴포넌트에 남으면 다음 사람이 그 옆에 색 분기를 붙인다 (D87).
 */
export function isClearOnSaleAnomaly(
  verdict: string | null | undefined,
  disposalMode: string | null | undefined
): boolean {
  return verdict === "CLEAR" && disposalMode === "SALE";
}

/* -------------------------------------------------------------------------- */

/**
 * `QueueTone` → 배너 색. `DecisionDetail` 안에 있던 `BANNER_TONE` 을 그대로 옮겨 온 것이다
 * (값 변경 없음). 컴포넌트에 `--ok-*` 가 남아 있으면 "색은 맵 한 곳"이라는 D87 문언이
 * 컴포넌트 쪽에서 반증된다.
 */
const BANNER_SKIN: Record<QueueTone, string> = {
  ok: "border:1px solid var(--ok-bd);background:var(--ok-bg);color:var(--ok-tx)",
  info: "border:1px solid var(--cite-bd);background:var(--cite-bg);color:var(--blue-tx)",
  neutral: "border:1px solid var(--line2);background:var(--raise);color:var(--ink2)",
  // 오렌지는 안전·경고 전용이다 — 차단 판정은 그 용도에 정확히 해당한다 (장식으로 쓰지 않는다)
  danger: "border:1px solid var(--saf-bd);background:var(--saf-bg);color:var(--saf-strong)",
  // 모르는 값 — 초록·중립 어느 쪽으로도 떨어지지 않는 전용 톤 (Badge 의 `unknown` 과 같은 색)
  warn: "border:1px dashed var(--error-tx);background:transparent;color:var(--error-tx)",
};

export function bannerSkin(tone: QueueTone): string {
  return BANNER_SKIN[tone];
}

/* -------------------------------------------------------------------------- */

export interface EvidenceCompletenessLabel {
  /** 배지 문구 */
  text: string;
  /** `title` 속성 (툴팁) */
  hint: string;
  /** 테두리·배경·글자색 CSS. 타이포는 컴포넌트가 붙인다 (상태와 무관하므로) */
  skin: string;
  known: boolean;
}

/**
 * 근거(조문 원문) 수집 상태 → 배지.
 *
 * ⚠ **REST 사전판정 응답에는 이 키가 없다** (실측 — `backend/services/disposal.precheck` 의
 * 반환 키에 `evidence_completeness` 가 없다. 이 값을 내는 것은 MCP 도구
 * `check_disposal_blockers` 뿐이다). 그래서 값이 없을 때 **조용히 넘기지 않고**
 * "제공되지 않았다"고 말한다 — 숨기면 사용자가 근거 상태를 모른 채 판정만 읽는다.
 * ⛔ 없는 값을 `COMPLETE` 로 채우지 않는다.
 *
 * `LAW_TEXT_PENDING` 경로는 남겨 둔다. MQ-701 실수집으로 현재 실 DB 정상값은 `COMPLETE`
 * 라서 발화하지 않지만, 조문 수집이 되돌아가면 다시 필요한 경로다.
 */
const EVIDENCE_COMPLETENESS: Record<string, Omit<EvidenceCompletenessLabel, "known">> = {
  COMPLETE: {
    text: "조문 원문 수집 완료",
    hint: "",
    skin: "border:1px solid var(--ok-bd);background:var(--ok-bg);color:var(--ok-tx)",
  },
  LAW_TEXT_PENDING: {
    text: "LAW_TEXT_PENDING — 서명용 증빙 불가",
    hint: "서명용 증빙은 아직 만들 수 없습니다",
    skin: "border:1px dashed var(--error-tx);color:var(--error-tx)",
  },
};

export function evidenceCompletenessView(value: unknown): EvidenceCompletenessLabel {
  if (typeof value !== "string") {
    return {
      text: "근거 수집 상태 미제공",
      hint: "REST 사전판정 응답에 evidence_completeness 키가 없습니다 — 값을 지어내지 않습니다",
      skin: "border:1px dashed var(--dim2);color:var(--dim)",
      known: false,
    };
  }
  const known = EVIDENCE_COMPLETENESS[value];
  if (!known) {
    return {
      text: `⚠ ${value}`,
      hint: `모르는 근거 상태 어휘 — ${value}`,
      skin: "border:1px dashed var(--error-tx);color:var(--error-tx)",
      known: false,
    };
  }
  return { ...known, known: true };
}

/* -------------------------------------------------------------------------- */

export interface Signability {
  /** 서명 컨트롤을 열 것인가 */
  signable: boolean;
  known: boolean;
  /** 열지 않는 이유 (열 때는 빈 문자열) */
  note: string;
}

/**
 * 상태 → 서명 경로 개방 여부. `ALLOWED_FROM["signed"] === "pending"`
 * (`backend/services/decisions.py`) 의 화면 쪽 사본이다.
 *
 * **맵 밖 값은 `false`** 다 — 모르는 상태에 쓰기 경로를 여는 것은 D87 이 막으려는 실패의
 * 가장 비싼 형태다(모르는 값이 초록으로 보이는 것보다 나쁘다). 컴포넌트가 `state === "pending"`
 * 같은 비교를 갖지 않게 하려고 함수로 낸다.
 */
const SIGNABLE_STATE: Record<string, Signability> = {
  draft: {
    signable: false,
    known: true,
    note: "아직 승인 요청 전(draft)입니다 — 정비사가 제출해야 서명할 수 있습니다.",
  },
  pending: { signable: true, known: true, note: "" },
  signed: { signable: false, known: true, note: "이미 서명으로 확정된 결정입니다." },
  rejected: { signable: false, known: true, note: "반려된 결정입니다." },
};

export function signability(state: string): Signability {
  return (
    SIGNABLE_STATE[state] ?? {
      signable: false,
      known: false,
      note: "이 화면이 모르는 상태 값입니다 — 서명 경로를 열지 않습니다.",
    }
  );
}

/* -------------------------------------------------------------------------- */

/**
 * 실패 뒤에 사람이 할 수 있는 일.
 *   `retry`     사유를 고쳐 다시 제출할 수 있다 (422 등)
 *   `override`  우회 게이트를 열어야 한다 (사유 필수 — 자동으로 채우지 않는다)
 *   `reload`    현재 상태를 다시 읽어야 한다. **서명 컨트롤은 닫는다**
 *   `none`      재시도로 풀리지 않는다. 사람이 재검토·복구해야 한다
 */
export type SignRecovery = "retry" | "override" | "reload" | "none";

export interface SignErrorLabel {
  title: string;
  recovery: SignRecovery;
  known: boolean;
}

/**
 * `POST /api/decisions/{id}/sign` 실패 어휘 (`backend/routers/decisions.py`).
 *
 * ⛔ `evidence_changed` 를 `retry` 로 두지 않는다 — 사람이 본 것과 다른 근거에 서명하게 된다.
 *   "무시하고 다시 누르기" 경로를 UI 에 만들지 않는 것이 이 맵의 존재 이유다 (D84).
 * ⛔ `cited_rule_missing` 을 `retry` 로 두지 않는다 — 백엔드가 503(재시도 가능)에서
 *   일부러 떼어 낸 상태다. 재시도하면 영원히 같은 답이 온다.
 */
const SIGN_ERROR: Record<string, Omit<SignErrorLabel, "known">> = {
  evidence_changed: {
    title: "근거가 변경되었습니다. 다시 검토해야 합니다.",
    recovery: "reload",
  },
  override_required: {
    title: "서명 시점 판정이 차단 어휘입니다 — 우회 체크와 사유 없이는 서명할 수 없습니다.",
    recovery: "override",
  },
  invalid_transition: {
    title: "지금은 서명할 수 있는 상태가 아닙니다 (다른 사람이 먼저 처리했을 수 있습니다).",
    recovery: "reload",
  },
  law_text_unavailable: {
    title:
      "인용 조문의 원문이 수집되지 않아 근거를 재산출할 수 없습니다 — 재시도로 풀리지 않습니다.",
    recovery: "none",
  },
  cited_rule_missing: {
    title:
      "판정이 인용한 룰이 카탈로그에 없습니다 — 재시도로 풀리지 않습니다. 사람이 다시 검토해야 합니다.",
    recovery: "none",
  },
  rule_catalog_not_loaded: {
    title: "룰 카탈로그가 적재되지 않았습니다 — 서버 준비 후 다시 시도하십시오.",
    recovery: "retry",
  },
  rule_catalog_invalid: {
    title: "룰 카탈로그의 무결성이 깨졌습니다 — 관리자 확인이 필요합니다.",
    recovery: "none",
  },
};

export function signErrorView(reason: string | null | undefined): SignErrorLabel {
  if (!reason) {
    // 403·422·500 처럼 `reason` 이 없는 실패. 본문 문장(extractDetail)이 유일한 설명이므로
    // 제목을 지어내지 않고 컨트롤을 열어 둔다 (422 는 사유를 고치면 풀린다).
    return { title: "", recovery: "retry", known: false };
  }
  const known = SIGN_ERROR[reason];
  if (!known) return { title: reason, recovery: "reload", known: false };
  return { ...known, known: true };
}
