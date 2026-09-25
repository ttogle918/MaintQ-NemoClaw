/**
 * 사업장 평면도 점 표시 규칙 (D158, Sprint 19 MQ-1914 — D87).
 *
 * 평면도의 설비 점은 **두 축**을 함께 보여 준다 — 새 판정을 만들지 않고 기존 원천을 조합만 한다:
 *   - **채움색 = 설비 상태** — `GET /api/assets/{id}/hotspot-status` 의 `parts[].color`
 *     (설비 하이라이트 대시보드와 같은 원천). 가장 심한 색 하나로 요약한다: red > orange > blue.
 *     색·라벨 자체는 `lib/mappers.hotspotColorView` 가 정한다 — 여기는 **어느 색 키인가**만 고른다.
 *   - **테두리 = 기종 온보딩 상태** — `GET /api/onboarding/status` → `lib/onboarding.onboardingBadgeView`
 *     가 준 톤. iG5A·S100 은 `none` → 테두리 없음(기존 기종은 무표시, 뱃지와 같은 규칙).
 *
 * 없는 사실을 만들지 않는다 (D62·D87):
 *   - 호스트 자산이 없는 설비(`asset_id` null — 분전반·HV600 2행)는 하이라이트 원천 자체가 없다
 *     → 「정상」이 아니라 `no_host`(상태 원천 없음)다.
 *   - 조회 실패·모르는 status·모르는 색 → `unknown`. 절대 「정상」으로 떨어지지 않는다.
 *
 * ⛔ React 를 import 하지 않는다 · 경로 별칭(`@/…`)도 쓰지 않는다 — `ui_honesty` 제약 게이트
 *   (단독 tsc 로 L1 이 돈다)의 전제다.
 */

/** 하이라이트 응답에서 이 모듈이 읽는 최소 모양 (`lib/api.ApiHotspotStatus` 의 부분집합) */
export interface HotspotLike {
  status: string;
  parts?: { color?: string | null }[];
}

/**
 * 점 채움 요약 키.
 * - `red`·`orange`·`blue` — hotspot 색 키 그대로(`hotspotColorView(key)` 로 넘긴다)
 * - `normal` — 원천 조회 성공 · 색 있는 부품 0개
 * - `no_host` — 호스트 자산 미등록이라 원천이 없다
 * - `loading` — 아직 묻는 중
 * - `unknown` — 조회 실패 · 모르는 status · 모르는 색
 */
export type EquipmentStatusKey = "red" | "orange" | "blue" | "normal" | "no_host" | "loading" | "unknown";

const COLOR_RANK: Record<string, number> = { red: 3, orange: 2, blue: 1 };

function rankOf(color: unknown): number | null {
  if (color === null || color === undefined) return 0;
  if (typeof color === "string" && Object.prototype.hasOwnProperty.call(COLOR_RANK, color)) {
    return COLOR_RANK[color];
  }
  return null; // 모르는 색
}

/**
 * 설비 한 대의 상태 요약 키.
 * @param assetId 설비의 호스트 자산 id (없으면 null)
 * @param status  하이라이트 응답 · `undefined`=조회 중 · `null`=조회 실패
 */
export function equipmentStatusKey(
  assetId: string | null | undefined,
  status: HotspotLike | null | undefined
): EquipmentStatusKey {
  if (!assetId) return "no_host";
  if (status === undefined) return "loading";
  if (status === null || status.status !== "ok") return "unknown";
  let worst = 0;
  for (const p of status.parts ?? []) {
    const r = rankOf(p?.color);
    if (r === null) return "unknown"; // 모르는 색이 하나라도 있으면 요약을 지어내지 않는다
    if (r > worst) worst = r;
  }
  if (worst === 3) return "red";
  if (worst === 2) return "orange";
  if (worst === 1) return "blue";
  return "normal";
}

/** hotspot 색 키인가 — 참이면 색·라벨은 `hotspotColorView(key)` 가 정한다 */
export function isHotspotColorKey(key: EquipmentStatusKey): key is "red" | "orange" | "blue" {
  return key === "red" || key === "orange" || key === "blue";
}

export interface PlainStatusView {
  label: string;
  /** 점 채움 CSS 색 */
  fill: string;
  /** 속이 빈 점(원천 없음·미상)인가 — 「정상」과 모양으로도 구분한다 */
  hollow: boolean;
}

/** hotspot 색 키가 **아닌** 요약의 표시. (색 키는 `hotspotColorView` 한 곳이 정한다) */
const PLAIN_VIEW: Record<"normal" | "no_host" | "loading" | "unknown", PlainStatusView> = {
  normal: { label: "정상", fill: "var(--dim)", hollow: false },
  no_host: { label: "상태 원천 없음 (호스트 자산 미등록)", fill: "var(--dim2)", hollow: true },
  loading: { label: "확인 중", fill: "var(--line2)", hollow: true },
  unknown: { label: "상태 미상", fill: "var(--error-tx)", hollow: true },
};

export function plainStatusView(key: EquipmentStatusKey): PlainStatusView {
  if (isHotspotColorKey(key)) return PLAIN_VIEW.unknown; // 호출자 오용 — 정상으로 떨어뜨리지 않는다
  return PLAIN_VIEW[key];
}

/** 기종 온보딩 톤(`lib/onboarding.OnboardingTone`) → 점 테두리. 톤 문자열만 받는다(모듈 독립) */
export interface OnboardingRing {
  stroke: string;
  /** SVG stroke-dasharray — 빈 문자열이면 실선 */
  dash: string;
}

const RING: Record<string, OnboardingRing> = {
  ok: { stroke: "var(--ok-tx)", dash: "" }, // 진단 가능 — 사람 승격 + 안전 문구 승인 완료
  info: { stroke: "var(--blue-tx)", dash: "3 2" }, // 안전 문구 대기 — 뱃지의 정보색 점선과 같다
  neutral: { stroke: "var(--dim)", dash: "2 2" }, // 온보딩 중
};
const RING_UNKNOWN: OnboardingRing = { stroke: "var(--error-tx)", dash: "1 2" };

/**
 * `onboardingBadgeView(state)` 결과의 톤 → 테두리. `null`(= `none`, 기존 기종) 이면 테두리 없음.
 * 맵 밖 톤은 unknown 테두리 — **`ok` 로 떨어지지 않는다**.
 */
export function onboardingRing(tone: string | null | undefined): OnboardingRing | null {
  if (tone === null || tone === undefined) return null;
  return Object.prototype.hasOwnProperty.call(RING, tone) ? RING[tone] : RING_UNKNOWN;
}
