/**
 * 법정 기한 추적(`GET /api/deadlines`) 표시 규칙 (MQ-1202, S9).
 *
 * `data/deadlines.py::track_deadlines` 가 주는 `state`("UPCOMING"|"IN_REVIEW_BAND"|"OVERDUE")·
 * `type`("TAX-CREDIT-2Y"|"SAFETY-INSPECTION") 원 어휘를 그대로 받아, 맵 밖 값은 지어내지
 * 않고 `unknown` 톤 + 원문으로 되돌린다(D87 태도 — `lib/maintValue.ts`·`lib/ownership.ts` 와
 * 동일한 제약).
 *
 * ⛔ React 를 import 하지 않는다 — `ui_honesty` L1 이 단독 `tsc` 로 이 파일을 검증한다.
 * ⛔ 경로 별칭(`@/…`)도 쓰지 않는다 — `paths` 설정 없이 단독 컴파일돼야 한다.
 */

export type Tone = "ok" | "warn" | "error" | "unknown";

export interface StateView {
  label: string;
  tone: Tone;
}

// 총 맵 1곳 — 맵 밖 값은 unknown + 원문 보존 (D87)
const STATE_VIEW: Record<string, StateView> = {
  UPCOMING: { label: "임박", tone: "warn" },
  IN_REVIEW_BAND: { label: "경계 구간 — 사람 검토 필요", tone: "warn" },
  OVERDUE: { label: "경과", tone: "error" },
};

/**
 * `deadlines.items[].state` → 표시. 맵 밖 값(계약 밖 새 어휘)은 `ok`·`warn`·`error` 어느
 * 정상 톤과도 겹치지 않는 전용 `unknown` 톤을 쓰고 원문을 보존한다.
 */
export function deadlineStateView(state: string): StateView {
  const known = STATE_VIEW[state];
  if (known) return known;
  return { label: `미상(${state})`, tone: "unknown" };
}

const TYPE_LABEL: Record<string, string> = {
  "TAX-CREDIT-2Y": "투자세액공제 사후관리",
  "SAFETY-INSPECTION": "안전검사",
};

/** `deadlines.items[].type` → 표시 라벨. 맵 밖 값은 "미상(type)" 형태로 원문을 보존한다. */
export function deadlineTypeLabel(type: string): string {
  const known = TYPE_LABEL[type];
  if (known) return known;
  return `미상(${type})`;
}
