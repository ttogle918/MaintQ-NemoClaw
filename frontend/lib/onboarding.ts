/**
 * 기종 온보딩 검수·안전 문구 승인 표시 규칙 (MQ-1911, D87·D145·D147·D156·D157).
 *
 * `/api/onboarding/*`(`backend/routers/onboarding.py`) 가 주는 **원 어휘**
 * (`state`·`flags`·`confidence`·`kind`)를 화면 표시로 바꾸는 단일 출처다. 화면 파일은
 * 상태 문자열을 직접 비교하지 않고 여기 함수만 부른다 (D87 — `ui_honesty_contract` L2).
 *
 * - 맵에 없는 어휘는 `⚠ 원문` + `unknown` 톤 — **절대 `ok` 로 떨어지지 않는다**.
 * - `ok` 톤은 「진단 가능」·「승격됨」·「승인됨」처럼 **사람이 확정한 사실**에만 쓴다.
 *   AI 초안(정규화문·confidence high)은 `ok` 를 받지 못한다 — 「AI 가 만든 것 / 사람이
 *   확정한 것」의 경계가 색으로 새지 않게 한다(D145).
 * - 오렌지(안전·긴급 전용)는 톤 어휘에 아예 없다 — 주입 의심은 `security`(잉크색) 톤이다.
 *
 * ⛔ React 를 import 하지 않는다 — `ui_honesty` 제약 게이트가 단독 tsc 전제를 검사한다.
 * ⛔ 경로 별칭(`@/…`)도 쓰지 않는다.
 */

export type OnboardingTone = "ok" | "info" | "neutral" | "caution" | "security" | "unknown";

/**
 * 맵에 **자기 키로** 있는가. `x in MAP` 은 프로토타입 키(`toString`·`constructor` 등)에도 참이라
 * 원 어휘 `"toString"` 이 라벨·톤으로 새어 나간다 — 그래서 `in` 을 쓰지 않는다.
 * (`Object.hasOwn` 은 ES2022 — L1 의 단독 tsc 가 `--target es2020` 이라 쓰지 않는다.)
 */
function hasKey(map: Record<string, unknown>, key: unknown): key is string {
  return typeof key === "string" && Object.prototype.hasOwnProperty.call(map, key);
}

export interface OnboardingLabel {
  label: string;
  tone: OnboardingTone;
  /** 맵에 있던 어휘인가. `false` 면 label 이 원문을 담고 있다 */
  known: boolean;
}

/* -------------------------------------------------------------------------- */
/* 기종 표시명 · 매뉴얼 문서번호                                                   */

/**
 * 기종 코드 → 화면 표시명(제조사 포함). manifest 에 제조사 필드가 없어(`license_note` 는
 * 자유 문자열이라 파싱하지 않는다) 화면 상수로만 둔다. **모르는 기종은 코드 그대로** — 지어내지 않는다.
 */
const MODEL_DISPLAY_NAME: Record<string, string> = {
  HV600: "Yaskawa HV600",
};

export function modelDisplayName(model: string): string {
  return hasKey(MODEL_DISPLAY_NAME, model) ? MODEL_DISPLAY_NAME[model] : model;
}

/**
 * 헤더의 원본 매뉴얼 표기. `manual_doc`(서버가 manifest `file` stem 으로 준 문서번호)이 있으면
 * 그것을 앞에, 없으면(null — manifest 에 없는 id) `manual_id` 만. 둘 다 서버 값 그대로다.
 */
export function manualDocLabel(batch: { manual_id: string; manual_doc?: string | null }): {
  primary: string;
  secondary: string | null;
} {
  const doc = typeof batch.manual_doc === "string" && batch.manual_doc.trim() ? batch.manual_doc : null;
  return doc ? { primary: doc, secondary: batch.manual_id } : { primary: batch.manual_id, secondary: null };
}

/* -------------------------------------------------------------------------- */
/* 기종 온보딩 뱃지 — `GET /api/onboarding/status?model=` → `{model, state}`        */

const BADGE_VIEW: Record<string, OnboardingLabel> = {
  onboarding: { label: "온보딩 중", tone: "neutral", known: true },
  safety_pending: { label: "안전 문구 대기", tone: "info", known: true },
  ready: { label: "진단 가능", tone: "ok", known: true },
};

/**
 * 뱃지 표시. **`none`(배치 0 — iG5A·S100 등 기존 기종)은 `null` = 뱃지 없음.**
 * 그 밖의 모르는 값은 뱃지를 숨기지 않고 `⚠ 원문` 으로 드러낸다 (D87).
 */
export function onboardingBadgeView(state: string | null | undefined): OnboardingLabel | null {
  if (state === "none") return null;
  if (hasKey(BADGE_VIEW, state)) return BADGE_VIEW[state];
  return { label: `⚠ ${state ?? "미상"}`, tone: "unknown", known: false };
}

/** 「진단 가능」 인가 — 아니면 절차 안내가 차단된 상태다(배너용). 모르는 값은 false. */
export function isOnboardingReady(state: string | null | undefined): boolean {
  return state === "ready";
}

/**
 * 서버가 **실제로** 「차단(온보딩 중·안전 문구 대기)」이라고 답했는가. 조회 실패·모르는 값은
 * false — 모르는 것을 「차단되어 있다」로 단정하지 않는다 (D87). 배너용.
 */
export function isOnboardingBlocked(state: string | null | undefined): boolean {
  return state === "onboarding" || state === "safety_pending";
}

/* -------------------------------------------------------------------------- */
/* 코드 행·그룹 상태                                                             */

const ROW_STATE_VIEW: Record<string, OnboardingLabel> = {
  staged: { label: "대기", tone: "info", known: true },
  approved: { label: "승격됨", tone: "ok", known: true },
  rejected: { label: "반려", tone: "neutral", known: true },
};

export function rowStateView(state: string | null | undefined): OnboardingLabel {
  if (hasKey(ROW_STATE_VIEW, state)) return ROW_STATE_VIEW[state];
  return { label: `⚠ ${state ?? "미상"}`, tone: "unknown", known: false };
}

/** 승격·반려 대상이 될 수 있는 행인가 (`state='staged'` 만). */
export function isRowStaged(state: string | null | undefined): boolean {
  return state === "staged";
}

/** 그룹 상태 판정에 필요한 최소 모양 (`GET /batches/{id}/groups` 응답의 부분 집합). */
export interface GroupLike {
  promoted: boolean;
  rows: { state: string; norms: { confidence: string; flags: string[] }[]; source_flags: string[] }[];
}

export type GroupStatusKey = "promoted" | "pending" | "no_norm" | "rejected" | "unknown";

export interface GroupStatusView extends OnboardingLabel {
  key: GroupStatusKey;
}

/**
 * 코드 그룹 상태.
 * - `promoted`(서버가 `error_codes` 에 같은 코드가 있다고 답함) → 「승격됨」
 * - staged 행이 없고 전부 반려 → 「반려」
 * - staged 행 중 한국어 정규화가 없는 행이 있음 → 「정규화 없음」(승격 불가)
 * - 그 밖의 staged → 「대기」
 * - 행 상태에 모르는 어휘가 섞임 → `⚠` (D87)
 */
export function groupStatusView(group: GroupLike): GroupStatusView {
  if (group.promoted) return { key: "promoted", label: "승격됨", tone: "ok", known: true };
  const unknownRow = group.rows.find((r) => !hasKey(ROW_STATE_VIEW, r.state));
  if (unknownRow) {
    return { key: "unknown", label: `⚠ ${unknownRow.state}`, tone: "unknown", known: false };
  }
  const staged = group.rows.filter((r) => isRowStaged(r.state));
  if (staged.length === 0) {
    const allRejected = group.rows.every((r) => r.state === "rejected");
    return allRejected
      ? { key: "rejected", label: "반려", tone: "neutral", known: true }
      : // 행이 승격(approved)됐는데 그룹 promoted=false — 서버 두 답이 어긋난 상태. 지어내지 않는다.
        { key: "unknown", label: "⚠ 불일치", tone: "unknown", known: false };
  }
  if (staged.some((r) => r.norms.length === 0)) {
    return { key: "no_norm", label: "정규화 없음", tone: "caution", known: true };
  }
  return { key: "pending", label: "대기", tone: "info", known: true };
}

/** 그룹에 저신뢰(최신 norm 의 confidence 가 high 가 아님) staged 행이 있는가. */
export function groupHasLowConfidence(group: GroupLike): boolean {
  return group.rows.some(
    (r) => isRowStaged(r.state) && r.norms.length > 0 && confidenceTone(r.norms[0].confidence) !== "ok"
  );
}

/** 그룹의 staged 행 원문·최신 정규화에 붙은 플래그 합집합(정렬). 목록 아이콘용. */
export function groupFlags(group: GroupLike): string[] {
  const out = new Set<string>();
  for (const r of group.rows) {
    if (!isRowStaged(r.state)) continue;
    r.source_flags.forEach((f) => out.add(f));
    if (r.norms.length > 0) r.norms[0].flags.forEach((f) => out.add(f));
  }
  return [...out].sort();
}

/** 목록 상태 필터 — 키는 `groupStatusView().key` 와 같은 어휘다. */
export const GROUP_STATUS_FILTERS: { key: GroupStatusKey | "all"; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "pending", label: "대기" },
  { key: "no_norm", label: "정규화 없음" },
  { key: "promoted", label: "승격됨" },
  { key: "rejected", label: "반려" },
];

export type GroupFlagFilter = "all" | "low" | "security" | "multi";

export const GROUP_FLAG_FILTERS: { key: GroupFlagFilter; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "low", label: "저신뢰" },
  { key: "security", label: "주입 의심" },
  { key: "multi", label: "여러 구역" },
];

export function groupMatchesFlagFilter(group: GroupLike, key: GroupFlagFilter): boolean {
  if (key === "low") return groupHasLowConfidence(group);
  if (key === "security") return groupFlags(group).some((f) => flagTone(f) === "security");
  if (key === "multi") return group.rows.length > 1;
  return true;
}

/* -------------------------------------------------------------------------- */
/* 정규화 신뢰도 · 플래그                                                         */

/**
 * `confidence` → 톤. `high` 만 `ok` 다 — 이 `ok` 는 「AI 가 스스로 확신한다」는 뜻일 뿐
 * 사람 확정이 아니므로, 화면은 이 톤을 초록 배지로 칠하지 않고 글자색 정도로만 쓴다.
 * `low`·모르는 값은 `warn`.
 */
export function confidenceTone(c: string | null | undefined): "ok" | "warn" {
  return c === "high" ? "ok" : "warn";
}

export function confidenceLabel(c: string | null | undefined): string {
  if (c === "high") return "신뢰도 high";
  if (c === "low") return "저신뢰";
  return `⚠ 신뢰도 ${c ?? "미상"}`;
}

const FLAG_LABEL: Record<string, string> = {
  injection_suspect: "주입 의심",
  output_suspect: "출력 주입 의심",
  token_dropped: "토큰 누락",
  untranslated_term: "미번역 용어",
  ambiguous_source: "원문 모호",
  agent_low_confidence: "에이전트 저신뢰",
  unknown_flag_dropped: "미상 플래그 폐기됨",
};

const FLAG_HINT: Record<string, string> = {
  injection_suspect: "원문에 AI 에게 지시하는 듯한 문장이 있었다 — 에이전트는 따르지 않고 표시만 했다",
  output_suspect: "정규화 결과에 지시·주입 패턴이 있다 — 번역문을 원문과 대조할 것",
  token_dropped: "원문의 파라미터 ID·숫자가 번역문에서 빠졌다 — 원문과 대조할 것",
  untranslated_term: "번역되지 않은 용어가 남아 있다",
  ambiguous_source: "원문(표 구조) 자체가 모호하다",
  agent_low_confidence: "에이전트가 스스로 확신하지 못한다고 표시했다",
  unknown_flag_dropped: "에이전트가 허용 목록 밖 플래그를 보내 서버가 버렸다",
};

/** 플래그 원 어휘 → 한국어 라벨. 모르는 값은 원문 보존(`미상(x)`). */
export function flagLabel(flag: string): string {
  return hasKey(FLAG_LABEL, flag) ? FLAG_LABEL[flag] : `미상(${flag})`;
}

export function flagHint(flag: string): string {
  return hasKey(FLAG_HINT, flag) ? FLAG_HINT[flag] : "서버가 알려 준 플래그지만 화면이 모르는 어휘다 — 원문과 대조할 것";
}

/**
 * 플래그 톤. 주입 계열은 `security`(보안 이벤트 — 잉크색 굵은 테두리, **오렌지 아님**),
 * 나머지는 `caution`(회색 점선). 모르는 값은 `unknown`.
 */
export function flagTone(flag: string): OnboardingTone {
  if (flag === "injection_suspect" || flag === "output_suspect") return "security";
  return hasKey(FLAG_LABEL, flag) ? "caution" : "unknown";
}

/* -------------------------------------------------------------------------- */
/* 승격 요청 조립 (D156 — 코드 그룹 단위)                                          */

export interface RowLike {
  row_id: number;
  state: string;
  source_flags: string[];
  norms: { norm_id: number; flags: string[] }[];
}

/** 행의 기본 선택 norm — 서버가 `norm_id` 내림차순으로 주므로 첫 항목이 최신. 없으면 null. */
export function defaultNormId(row: { norms: { norm_id: number }[] }): number | null {
  return row.norms.length > 0 ? row.norms[0].norm_id : null;
}

/** 승격 body 에 넣을 행 = 그룹의 staged 행 전부 (`group_incomplete` 를 피하려면 빠짐없이). */
export function promotableRows<T extends { state: string }>(rows: T[]): T[] {
  return rows.filter((r) => isRowStaged(r.state));
}

/**
 * 확인해야 할 플래그 = staged 행들의 `source_flags` ∪ 선택된 norm 들의 `flags` (서버 규칙과 동일).
 * `selection` 은 `{row_id: norm_id}`.
 */
export function requiredFlags(rows: RowLike[], selection: Record<number, number | null>): string[] {
  const out = new Set<string>();
  for (const r of promotableRows(rows)) {
    r.source_flags.forEach((f) => out.add(f));
    const nid = selection[r.row_id];
    const norm = r.norms.find((n) => n.norm_id === nid);
    if (norm) norm.flags.forEach((f) => out.add(f));
  }
  return [...out].sort();
}

/**
 * 실제로 보낼 `acknowledged_flags` = **현재 선택된 norm 들이 요구하는 플래그 ∩ 사람이 체크한 플래그**
 * (D156). norm 을 바꿔 요구 플래그가 달라져도 이전에 체크한 플래그가 새 선택에 새지 않는다.
 * 체크박스 표시도 이 결과로 한다. 순서는 `needed` 를 따른다.
 */
export function effectiveAcknowledged(needed: string[], checked: string[]): string[] {
  return needed.filter((f) => checked.includes(f));
}

/**
 * 클라이언트가 **미리 알 수 있는** 승격 불가 사유. 서버 판정을 대체하지 않는다 —
 * 여기가 비어도 서버는 403/409/422 를 줄 수 있고, 화면은 그 메시지를 그대로 보여 준다.
 */
export function promoteBlockers(
  rows: RowLike[],
  selection: Record<number, number | null>,
  primaryRowId: number | null,
  acknowledged: string[]
): string[] {
  const out: string[] = [];
  const staged = promotableRows(rows);
  if (staged.length === 0) out.push("대기(staged) 행이 없습니다");
  const noNorm = staged.filter((r) => r.norms.length === 0).map((r) => r.row_id);
  if (noNorm.length > 0) out.push(`한국어 정규화가 없는 행 ${noNorm.join(", ")} — 먼저 반려하거나 정규화를 받아야 합니다`);
  const unselected = staged.filter((r) => r.norms.length > 0 && selection[r.row_id] == null);
  if (unselected.length > 0) out.push(`정규화 미선택 행 ${unselected.map((r) => r.row_id).join(", ")}`);
  if (primaryRowId === null || !staged.some((r) => r.row_id === primaryRowId)) {
    out.push("대표(primary) 행을 대기 행 중에서 고르십시오");
  }
  const missing = requiredFlags(rows, selection).filter((f) => !acknowledged.includes(f));
  if (missing.length > 0) out.push(`플래그 확인 필요: ${missing.map(flagLabel).join(", ")}`);
  return out;
}

/* -------------------------------------------------------------------------- */
/* 원문 대조 보조 — 접힌 원인 · 긴 원문 · 반려 사유                                  */

/** 행 비교 표가 기본으로 보여 주는 원인 수. 넘으면 「원인 N건 더 보기」로 접힌다. */
export const CAUSE_FOLD_LIMIT = 3;

/** 이 행의 원인 칸 수 = max(원문 원인 수, 선택 정규화 원인 수). 선택 정규화가 없으면 원문만. */
export function causeRowCount(
  row: { causes_en: unknown[] },
  selectedNorm: { causes_ko: unknown[] } | null
): number {
  return Math.max(row.causes_en.length, selectedNorm ? selectedNorm.causes_ko.length : 0);
}

/** 접힌 원인이 있는 행인가 (원인 칸 수 > `CAUSE_FOLD_LIMIT`). */
export function hasFoldedCauses(count: number): boolean {
  return count > CAUSE_FOLD_LIMIT;
}

/**
 * 승격 전에 **아직 한 번도 펼치거나 원문 전체 보기로 열어 보지 않은** 접힌 행(대기 행만).
 * 안내용일 뿐이다 — 승격을 막지 않는다(막을지는 사람이 정할 몫).
 */
export function unseenFoldedRows<
  R extends { row_id: number; state: string; causes_en: unknown[]; norms: { norm_id: number; causes_ko: unknown[] }[] },
>(rows: R[], selection: Record<number, number | null>, seen: Record<number, boolean>): R[] {
  return promotableRows(rows).filter((r) => {
    const norm = r.norms.find((n) => n.norm_id === selection[r.row_id]) ?? null;
    return hasFoldedCauses(causeRowCount(r, norm)) && !seen[r.row_id];
  });
}

/**
 * 한 줄에 다 안 보일 만큼 긴 원문인가 — 「원문 전체 보기」 버튼을 붙일지.
 * 줄바꿈이 있거나 `maxChars` 를 넘으면 참. 표시 판단일 뿐 내용 판정이 아니다.
 */
export function isLongText(text: string | null | undefined, maxChars = 90): boolean {
  if (!text) return false;
  return text.length > maxChars || text.includes("\n");
}

/**
 * 반려 사유 입력 차단 사유. 비었거나 공백뿐이면 문구, 아니면 null.
 * 서버(`note_required` 422)와 같은 규칙을 **미리** 보여 줄 뿐 — 최종 판정은 서버다.
 */
export function rejectNoteBlocker(note: string): string | null {
  return note.trim() ? null : "반려 사유를 입력하십시오 (공백만으로는 반려할 수 없습니다)";
}

/* -------------------------------------------------------------------------- */
/* 안전 문구 후보 (D147·D157)                                                    */

const SAFETY_KIND_LABEL: Record<string, string> = {
  discharge_wait: "방전 대기",
  live_work: "활선 작업",
  qualified_worker: "자격자 작업",
  other: "기타",
};

export function safetyKindLabel(kind: string): string {
  return hasKey(SAFETY_KIND_LABEL, kind) ? SAFETY_KIND_LABEL[kind] : `미상(${kind})`;
}

export const SAFETY_KIND_FILTERS: { key: string; label: string }[] = [
  { key: "all", label: "전체" },
  ...Object.entries(SAFETY_KIND_LABEL).map(([key, label]) => ({ key, label })),
];

/** 후보 목록 종류 필터 — `"all"` 이면 전부, 아니면 원 어휘가 같은 것만. */
export function safetyKindMatches(kind: string, filter: string): boolean {
  return filter === "all" || kind === filter;
}

/** 기종당 승인 1건 규칙(D157) 대상 kind 인가. */
export function isDischargeWait(kind: string): boolean {
  return kind === "discharge_wait";
}

const SAFETY_STATE_VIEW: Record<string, OnboardingLabel> = {
  staged: { label: "대기", tone: "info", known: true },
  approved: { label: "승인됨 · 되돌리기 없음", tone: "ok", known: true },
  rejected: { label: "반려", tone: "neutral", known: true },
};

export function safetyStateView(state: string | null | undefined): OnboardingLabel {
  if (hasKey(SAFETY_STATE_VIEW, state)) return SAFETY_STATE_VIEW[state];
  return { label: `⚠ ${state ?? "미상"}`, tone: "unknown", known: false };
}

export function isCandidateStaged(state: string | null | undefined): boolean {
  return state === "staged";
}

/** 이 기종의 승인된 방전 대기 후보(첫 건). 없으면 null. */
export function findApprovedDischarge<T extends { kind: string; state: string }>(cands: T[]): T | null {
  return cands.find((c) => isDischargeWait(c.kind) && c.state === "approved") ?? null;
}

/** 방전 대기 kind 로 이미 승인된 후보 수 (정상은 0 또는 1 — 2 이상이면 D157 fail-closed). */
export function approvedDischargeCount(cands: { kind: string; state: string }[]): number {
  return cands.filter((c) => isDischargeWait(c.kind) && c.state === "approved").length;
}

/**
 * 방전 대기 승인이 2건 이상 — 서버 `resolve()` 가 None 을 돌려 절차 안내가 **차단**된
 * fail-closed 상태다(D157). 정상은 0 또는 1.
 */
export function isDischargeFailClosed(count: number): boolean {
  return count >= 2;
}

/** 문안 속 `N분` 숫자들. 서버 `_MINUTE_NUM_RE`(`(\d+)\s*분`)와 같은 패턴. */
export function minuteNumbers(text: string): number[] {
  return [...text.matchAll(/(\d+)\s*분/g)].map((m) => Number(m[1]));
}

/**
 * **참고용** 사전 경고 — 서버 `check_safety_text` 를 흉내 낼 뿐, 최종 판정은 서버다.
 * 경고가 있어도 제출은 막지 않는다(서버의 422 메시지를 그대로 보여 주는 것이 계약).
 */
export function safetyTextPrecheck(text: string, waitMinutes: number | null): string | null {
  const values = minuteNumbers(text);
  if (waitMinutes === null) {
    return values.length > 0
      ? `원문에 대기시간 숫자가 없는데 문안에 ${values.map((v) => `${v}분`).join(", ")} 이 있습니다`
      : null;
  }
  const exact = new RegExp(`(?<!\\d)${waitMinutes}분`).test(text);
  if (!exact) return `원문 명시값 ${waitMinutes}분 이 문안에 그대로 들어 있지 않습니다`;
  const other = values.filter((v) => v !== waitMinutes);
  if (other.length > 0) return `원문 명시값 ${waitMinutes}분 외의 값(${other.join(", ")}분)이 있습니다`;
  return null;
}

/* -------------------------------------------------------------------------- */
/* 공통                                                                          */

/**
 * 서버 오류 본문(`{reason, detail, ...extra}`) → 한 줄. 서버 메시지를 **바꾸지 않고** 그대로
 * 싣고, 무엇을 고치면 풀리는지 알려 주는 extra(`row_ids`·`flags`·`approved_cand_id`)만 덧붙인다.
 */
export function onboardingErrorText(status: number, body: Record<string, unknown> | null, raw: string): string {
  if (!body) return `HTTP ${status} — ${raw.slice(0, 200)}`;
  const reason = typeof body.reason === "string" ? body.reason : "";
  const detail = typeof body.detail === "string" ? body.detail : body.detail !== undefined ? JSON.stringify(body.detail) : "";
  const extras: string[] = [];
  if (Array.isArray(body.row_ids)) extras.push(`row_ids ${body.row_ids.join(", ")}`);
  if (Array.isArray(body.flags)) extras.push(`flags ${body.flags.join(", ")}`);
  if (typeof body.approved_cand_id === "number") extras.push(`승인된 후보 #${body.approved_cand_id}`);
  const head = [`HTTP ${status}`, reason].filter(Boolean).join(" ");
  return `${head} — ${detail || raw.slice(0, 200)}${extras.length ? ` (${extras.join(" · ")})` : ""}`;
}

/**
 * 서버가 준 UTC ISO(`...Z`)를 `YYYY-MM-DD HH:mm UTC` 로. 시간대를 추측해 바꾸지 않는다 (D39).
 * 파싱 불가면 원문 그대로.
 */
export function utcStamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}
