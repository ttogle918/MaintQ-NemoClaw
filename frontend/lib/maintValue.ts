/**
 * 보전지표 · 수리가치 판단 화면의 표시 규칙 (MQ-912).
 *
 * 이 파일의 유일한 목적: **`null` · `"insufficient_data"` 를 빈칸 · `0` · "양호"로 접지
 * 않는다.** 코디네이터 실측 — 핵심 4지표(`mtbf_days`·`mttr_hours`·`availability`·
 * `planned_ratio`) null 15/36(42%) · `mtbf_trend` `insufficient_data` 7/9. 도구 계약
 * (`04 §11`)이 직접 경고한다 — "값이 null 이거나 mtbf_trend 가 insufficient_data 면
 * 데이터가 부족한 것이지 '문제 없음'이 아니다." Stage 4 에서 직접 호출한 `AST-L3-CONV`
 * 조차 `mtbf_trend: "insufficient_data"` 였다 — 드문 값이 아니라 흔한 값이다.
 *
 * ⛔ React 를 import 하지 않는다 — `ui_honesty` L1 이 단독 `tsc` 로 이 파일을 검증한다
 *   (`lib/ownership.ts` 가 같은 전제로 이미 서 있다).
 * ⛔ 경로 별칭(앳 기호 + 슬래시로 시작하는 tsconfig `paths` 매핑)도 쓰지 않는다 —
 *   `paths` 설정 없이 단독 컴파일돼야 한다(그래서 이 파일에는 어떤 import 문도 없다).
 */

/* -------------------------------------------------------------------------- */
/* 표시 단위                                                                   */

/**
 * 표시 종류 3가지.
 * - `value`       : 실제로 산출된 값
 * - `insufficient`: 산출을 시도했으나 근거가 부족하다는 판정 자체(`insufficient_data`)
 * - `unknown`     : 애초에 산출되지 않았거나(`null`), 계약 밖의 낯선 값이 왔다
 */
export type DisplayKind = "value" | "insufficient" | "unknown";

export interface Displayable {
  text: string;
  kind: DisplayKind;
}

function round2(v: number): number {
  return Math.round(v * 100) / 100;
}

/**
 * 지표 하나(`mtbf_days`·`mttr_hours`·`availability`·`planned_ratio`·
 * `cumulative_repair_ratio` 등) → 표시.
 *
 * `v === null` 이면 **"판단 근거 부족"** — 0 으로도 빈칸으로도 접지 않는다. `0` 은
 * "지표값이 0" 이라는 사실이고 `null` 은 "산출할 근거가 없다"는 사실이라 서로 다른
 * 문장으로 남아야 한다(D62).
 */
export function showMetric(v: number | null, unit: string): Displayable {
  if (v === null) return { text: "판단 근거 부족", kind: "insufficient" };
  if (!Number.isFinite(v)) {
    // 계약 밖 값(NaN·Infinity 등)이 온 경우 — "0" 이나 "양호"로 접지 않고 원문을 남긴다
    return { text: `미상(${String(v)})`, kind: "unknown" };
  }
  const shown = Number.isInteger(v) ? v : round2(v);
  return { text: `${shown}${unit}`, kind: "value" };
}

const TREND_LABEL: Record<string, string> = {
  improving: "개선 추세",
  stable: "안정",
  declining: "악화 추세",
};

/**
 * `mtbf_trend` → 표시. **`null` 과 `"insufficient_data"` 를 다르게 표시한다**
 * (`04 §11` · 엣지 케이스 표) — 전자는 애초에 산출되지 않은 것(미산출)이고, 후자는
 * 산출을 시도했지만 최근 12개월 vs 직전 12개월 중 어느 한쪽이라도 이벤트 2건 미만이라
 * 근거가 부족하다는 **판정 자체**다. 같은 문구로 뭉개면 두 사실이 구분되지 않는다.
 */
export function showTrend(t: string | null): Displayable {
  if (t === null) return { text: "미산출", kind: "unknown" };
  if (t === "insufficient_data") return { text: "판단 근거 부족", kind: "insufficient" };
  const known = TREND_LABEL[t];
  if (known) return { text: known, kind: "value" };
  // 모르는 어휘 — "안정"류로 오인되지 않게 원문을 남기고 unknown 을 쓴다 (D87 태도)
  return { text: `미상(${t})`, kind: "unknown" };
}

/**
 * 추정치 고지 문구 (D65·D74). `o.source` 가 있으면 — 즉 이 값이 실측이 아니라
 * 특정 산출 경로(예: 목업 잔가곡선)에서 왔다는 표식이 있으면 — 그 출처를 밝히는
 * 문장을 만든다. `source` 가 없으면 **문구를 지어내지 않는다** — `null` 그대로 둔다.
 */
export function estimateNotice(o: { source?: string }): string | null {
  const source = o?.source;
  if (!source) return null;
  return `이 값은 ${source} 기반 추정치이며 실거래가·실측값이 아닙니다 (D65·D74).`;
}

/**
 * `verdict === "HOLD"` 는 오류가 아니라 정상 판정이다(`04 §12`·`§13`) — 잔가 원천이
 * 없거나(수리가치 판단) 지출 성격이 경계선이라(지출 분류) 단정하지 않은 것이다.
 * 에러 경로로 보내지 말 것 — 이 함수는 그 판단을 컴포넌트가 다시 하지 않게 한다.
 */
export function isHoldVerdict(v: string): boolean {
  return v === "HOLD";
}
