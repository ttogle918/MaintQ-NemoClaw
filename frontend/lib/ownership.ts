/**
 * S18 실사 결과(`GET /api/assets/{id}/ownership`) → 화면 표시.
 *
 * 이 파일의 목적은 화면을 예쁘게 만드는 것이 아니라 **"확인 안 된 항목을 확인된 것처럼
 * 보여주는 경로"를 코드에서 없애는 것**이다 (D87). 그래서 상태→표시 변환은 여기 한 곳에만
 * 있고, 컴포넌트는 여기서 나온 `badge`·`tone` 을 **그대로** 렌더한다.
 *
 * ⛔ 이 파일 밖에 상태→색 사본을 만들지 않는다. 사본이 생기는 순간 한쪽만 고쳐지고,
 *   "미확인이 초록으로 보이는" 실패가 조용히 돌아온다.
 *
 * ⛔ 리액트 의존 금지 — 순수 TypeScript 만 둔다. 이 제약 덕분에 러너를 새로 들이지 않고
 *   `tsc` + `node` 만으로 단언을 돌릴 수 있다 (`lib/__checks__/ui_honesty.ts`).
 * ⛔ `@/` 경로 별칭도 쓰지 않는다 — tsconfig 의 `paths` 없이 단독 `tsc` 로 컴파일돼야 한다.
 *   (그래서 이 파일에는 어떤 import 문도 없다.)
 *
 * ⛔ **퍼센트·진행바를 만들지 않는다.** 요약은 "N/M 확인됨" 뿐이다.
 *   82% 진행바는 "거의 다 됐다"로 읽히는데 `PARTIAL` 의 뜻은 정반대다 —
 *   `PARTIAL` 은 어떤 추가 확인으로도 `VERIFIED` 로 승격되지 않는 판정이고(`11 §6`),
 *   남은 18% 는 "조금만 더 하면 되는 일"이 아니라 **원천이 존재하지 않아 영원히 안 채워지는
 *   칸**이다. 분자/분모를 그대로 보여 주는 것만이 그 사실을 왜곡하지 않는다 (D65·D87).
 */

/* -------------------------------------------------------------------------- */
/* 어휘                                                                        */

/** 항목 상태 2종. 백엔드(`data/ownership.py`)가 이 둘만 낸다 — 그래도 런타임은 믿지 않는다. */
export type ItemState = "VERIFIED" | "UNVERIFIED";

/** 전체 판정 3종 (`04 §9`). */
export type Verdict = "VERIFIED" | "PARTIAL" | "UNVERIFIED";

/** 표시 톤. 실제 색은 `TONE_STYLE` 한 곳에서만 정한다. */
export type Tone = "ok" | "warn" | "danger" | "muted" | "unknown";

const VERIFIED_STATE = "VERIFIED";
const UNVERIFIED_STATE = "UNVERIFIED";

/**
 * 실사 카테고리 9종 — **개수·순서가 계약이다** (`04 §9` · `data/ownership.py CATEGORIES`).
 * 항목이 0건이어도 카테고리는 화면에서 사라지지 않는다. 빼면 "확인 안 한 것"이 사라진다.
 */
export const CATEGORIES: readonly string[] = [
  "물리적 상태",
  "가동 이력",
  "정비 이력",
  "기술적 진부화",
  "권리관계",
  "법정 요건",
  "재무·회계",
  "시장·가격",
  "이전 비용",
];

/** `auditRows` 가 요구하는 카테고리 수. `CATEGORIES` 가 줄면 여기서 먼저 걸린다. */
export const CATEGORY_COUNT = 9;

/** 항목 0건 카테고리에 붙는 사유. 이유 없는 미확인은 만들지 않는다. */
export const EMPTY_LIMIT =
  "이 카테고리에 판정 항목이 0건입니다 — 확인된 것이 없다는 뜻이지 문제가 없다는 뜻이 아닙니다";

/* -------------------------------------------------------------------------- */
/* 상태 → 표시 (유일한 total 맵, D87)                                          */

/** ★ D87 — 상태→표시의 유일한 total 맵. 이 파일 밖에 사본을 만들지 않는다. */
export const ITEM_VIEW: Record<ItemState, { badge: string; tone: Tone }> = {
  VERIFIED: { badge: "확인됨", tone: "ok" },
  UNVERIFIED: { badge: "미확인", tone: "warn" },
};

export const VERDICT_VIEW: Record<Verdict, { headline: string; tone: Tone }> = {
  VERIFIED: {
    headline: "9개 카테고리의 모든 항목이 확인됐습니다",
    tone: "ok",
  },
  // ⛔ 이 문장을 부드럽게 고치지 말 것. PARTIAL 은 "대체로 안전"이 아니라 "미확인이 남았다"다.
  PARTIAL: {
    headline: "확인되지 않은 항목이 남아 있습니다 — 안전하다는 뜻이 아닙니다",
    tone: "warn",
  },
  UNVERIFIED: {
    headline: "확인된 항목이 없습니다 — 실사 근거가 없습니다",
    tone: "danger",
  },
};

/**
 * 항목 상태 → 배지.
 *
 * 인자가 `string` 인 이유: 백엔드가 어휘를 늘리면 **먼저 도착하는 쪽이 화면**이다.
 * `ItemState` 로 좁혀 두면 모르는 값이 타입상 존재할 수 없어 아래 폴백이 죽은 코드가 된다.
 *
 * ⛔ 맵 밖 값의 톤은 **절대 `"ok"` 가 아니다.** 모르는 상태를 초록으로 떨어뜨리는 것이
 *   이 프로젝트에서 가장 나쁜 실패다. 원문을 배지에 그대로 남겨 무엇이 왔는지 보이게 한다.
 */
export function itemView(state: string): { badge: string; tone: Tone } {
  const known = (ITEM_VIEW as Record<string, { badge: string; tone: Tone }>)[state];
  if (known) return known;
  // ⛔ 정상 어휘(`UNVERIFIED`)와 **같은 톤을 쓰지 않는다.** "확인 못 했다"와
  //    "이 값이 뭔지 모른다"는 다른 사실이고, 후자는 계약이 어긋났다는 신호다.
  //    오렌지를 빌려 쓰지 않는 이유는 `frontend/README §설계 계약` — 안전·긴급 전용이다.
  return { badge: `미확인 (${state})`, tone: "unknown" };
}

/** 전체 판정 → 배너. 모르는 판정도 초록이 되지 않는다 — **전용 `unknown` 톤** + 원문이다. */
export function verdictView(verdict: string): { headline: string; tone: Tone } {
  const known = (VERDICT_VIEW as Record<string, { headline: string; tone: Tone }>)[verdict];
  if (known) return known;
  return {
    headline: `판정 미상 (${verdict}) — 확인됐다는 뜻이 아닙니다`,
    // `PARTIAL`(정상 경고)과 같은 톤을 쓰지 않는다 — `itemView` 와 같은 이유.
    tone: "unknown",
  };
}

/**
 * 톤 → 인라인 CSS 선언. **`lib/ownership` 계층에서 색을 아는 곳은 여기 하나뿐**이다.
 *
 * ⚠ 다른 화면(`DecisionDetail`·`DisposalPanel`·ownership page 배너)은 자기 톤 표를 갖는다 —
 *   전부 `Record<Tone,…>` total 이라 미지 누수는 없지만 **저장소 전체에 하나뿐이라는 뜻은 아니다**.
 *
 * 컴포넌트가 자기 색 상수를 갖는 순간 매퍼를 우회할 수 있게 되므로(그리고 그게 정확히
 * 우리가 막으려는 실패다) 색까지 순수 계층에 둔다 — `spikes/ui_honesty_contract.py` 의
 * L2 가 컴포넌트 소스에 `--ok`·`--green` 이 0건임을 단언한다.
 */
export const TONE_STYLE: Record<Tone, string> = {
  ok: "color:var(--ok-tx);border-color:var(--ok-bd);background:var(--ok-bg)",
  warn: "color:var(--orange-tx);border-color:var(--saf-cite-bd);background:var(--saf-cite-bg)",
  // 모르는 어휘 전용 (D87). `components/ui/Badge.tsx` 의 `unknown` 과 같은 규약 —
  // 점선 적색이라 초록·오렌지 어느 쪽으로도 읽히지 않는다.
  unknown: "color:var(--error-tx);border-color:var(--error-tx);border-style:dashed;background:transparent",
  danger: "color:var(--error-tx);border-color:var(--error-tx);background:transparent",
  muted: "color:var(--dim);border-color:var(--line2);background:transparent",
};

/* -------------------------------------------------------------------------- */
/* API 응답 (느슨하게 받는다 — 좁히면 모르는 값이 타입상 사라진다)              */

export interface ApiItem {
  item?: unknown;
  state?: unknown;
  evidence?: unknown;
  limit?: unknown;
}

export interface ApiCategory {
  category?: unknown;
  items?: unknown;
}

export interface OwnershipApi {
  status?: string;
  asset_id?: string;
  verdict?: string;
  categories?: readonly ApiCategory[];
  verified?: unknown;
  unverified?: unknown;
  residual_risk?: unknown;
  mitigation?: unknown;
  not_considered?: unknown;
  disclaimer?: unknown;
  reason?: string;
}

/* -------------------------------------------------------------------------- */
/* 행                                                                          */

export interface Row {
  category: string;
  /** 항목 이름. 카테고리에 항목이 0건이면 자리 표시 행이다(`empty: true`) */
  item: string;
  /** **백엔드 원문 그대로.** 정규화하지 않는다 — 모르는 값이 화면에 남아야 한다 */
  state: string;
  /** `itemView` 산출. 컴포넌트는 이 값을 그대로 찍는다 */
  badge: string;
  tone: Tone;
  /** `VERIFIED` 일 때만 값이 있다 (`04 §9`) */
  evidence: string | null;
  /** `UNVERIFIED` 일 때만 값이 있다 — 이유 없는 미확인은 만들지 않는다 */
  limit: string | null;
  /** 항목이 0건인 카테고리를 대표하는 행인가 */
  empty: boolean;
}

export interface Summary {
  verified: number;
  total: number;
  /** ⛔ 퍼센트가 아니다. "N/M 확인됨" 뿐이다 (파일 헤더 주석의 근거 참조) */
  text: string;
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() !== "" ? v : null;
}

function itemRow(category: string, raw: ApiItem): Row {
  // 상태 키가 아예 없는 경우도 "없음"이라는 **모르는 값**으로 들어간다 → warn 폴백을 탄다.
  const state = str(raw?.state) ?? "없음";
  const view = itemView(state);
  return {
    category,
    item: str(raw?.item) ?? "(항목 이름 없음)",
    state,
    badge: view.badge,
    tone: view.tone,
    evidence: str(raw?.evidence),
    limit: str(raw?.limit),
    empty: false,
  };
}

function emptyRow(category: string): Row {
  const view = itemView(UNVERIFIED_STATE);
  return {
    category,
    item: "(항목 없음)",
    state: UNVERIFIED_STATE,
    badge: view.badge,
    tone: view.tone,
    evidence: null,
    limit: EMPTY_LIMIT,
    empty: true,
  };
}

/**
 * API 응답 → 표시 행.
 *
 * ★ **9카테고리를 전부 만든다.** 응답에 항목이 0건인 카테고리가 있어도 자리 표시 행을 남긴다 —
 *   스킵하면 "확인 안 한 것"이 화면에서 사라진다 (`04 §9` 명시).
 * ★ 응답에 계약 밖 카테고리가 섞여 오면 **버리지 않고 뒤에 붙인다.** 대신 `auditRows` 가
 *   카테고리 수 위반으로 잡는다 — 숨기는 것보다 드러내고 위반으로 기록하는 쪽이 정직하다.
 */
export function toRows(api: OwnershipApi): Row[] {
  const raw: readonly ApiCategory[] = Array.isArray(api?.categories) ? api.categories : [];

  const byName = new Map<string, ApiItem[]>();
  const extras: string[] = [];
  for (const c of raw) {
    const name = str(c?.category) ?? "(카테고리 이름 없음)";
    const items: ApiItem[] = Array.isArray(c?.items) ? (c.items as ApiItem[]) : [];
    const bucket = byName.get(name);
    if (bucket) {
      bucket.push(...items);
    } else {
      byName.set(name, [...items]);
      if (!CATEGORIES.includes(name)) extras.push(name);
    }
  }

  const rows: Row[] = [];
  for (const name of [...CATEGORIES, ...extras]) {
    const items = byName.get(name) ?? [];
    if (items.length === 0) {
      rows.push(emptyRow(name));
      continue;
    }
    for (const it of items) rows.push(itemRow(name, it));
  }
  return rows;
}

/** 요약. **퍼센트를 만들지 않는다** — 분자/분모를 그대로 보여 준다. */
export function summarize(rows: Row[]): Summary {
  const total = rows.length;
  const verified = rows.filter((r) => r.state === VERIFIED_STATE).length;
  return { verified, total, text: `${verified}/${total} 확인됨` };
}

/**
 * UI 정직성 불변식 검사. **반환값이 빈 배열이어야 정상**이다.
 *
 * 화면에 붙여 두는 이유: 매퍼가 아니라 **데이터**가 이상해도(백엔드가 어휘를 바꿨다든지)
 * 사용자에게 거짓 초록이 가는 것을 막아야 한다. 위반이 있으면 화면이 그 사실을 드러낸다.
 */
export function auditRows(rows: Row[]): string[] {
  const out: string[] = [];

  for (const r of rows) {
    const where = `${r.category} / ${r.item}`;
    // ① 확인되지 않은 것이 확인된 색(초록)으로 보이는가 — 이 화면의 존재 이유
    if (r.state !== VERIFIED_STATE && r.tone === "ok") {
      out.push(`[tone] ${where}: state=${r.state} 인데 tone="ok" 다 (미확인이 확인처럼 보인다)`);
    }
    // ② 이유 없는 미확인은 만들지 않는다
    if (r.state === UNVERIFIED_STATE && !r.limit) {
      out.push(`[limit] ${where}: UNVERIFIED 인데 사유(limit)가 비었다`);
    }
    // ③ 근거 없는 확인은 확인이 아니다
    if (r.state === VERIFIED_STATE && !r.evidence) {
      out.push(`[evidence] ${where}: VERIFIED 인데 근거(evidence)가 비었다`);
    }
  }

  // ④ 카테고리가 9개가 아니면 무언가 사라졌거나 계약 밖 값이 섞였다
  const cats = new Set(rows.map((r) => r.category));
  if (cats.size !== CATEGORY_COUNT) {
    out.push(
      `[categories] 카테고리 ${cats.size}종 (계약 ${CATEGORY_COUNT}종) — ` +
        `빠졌거나 계약 밖 카테고리가 섞였다: ${[...cats].join(", ")}`
    );
  }

  return out;
}

/* -------------------------------------------------------------------------- */
/* 실패 표시 — 어떤 실패도 "문제 없음"으로 번역되지 않는다                      */

/**
 * `status != "ok"` 의 `reason` → 사람이 읽을 문장 (`04 §9` status/reason 표).
 *
 * ⛔ `no_host_asset` 을 "문제 없음"으로 옮기지 말 것 — 분전반은 배전 위치이지 거래 단위가
 *   아니다. "판정 결과 문제 없음"이 아니라 "판정 대상이 아니다"다.
 */
export const REASON_TEXT: Record<string, string> = {
  no_host_asset: "호스트 자산 없음 — 판정 대상이 아닙니다 (배전 위치는 거래 단위가 아닙니다)",
  unknown_asset: "등록되지 않은 자산입니다 — 실사 결과가 없습니다",
  unknown_equipment: "등록되지 않은 설비입니다 — 실사 결과가 없습니다",
  invalid_input: "식별자가 올바르지 않습니다 — 실사 판정을 수행하지 않았습니다",
  db_missing: "데이터 저장소를 찾을 수 없습니다 — 실사 판정을 수행하지 못했습니다",
  db_error: "데이터 저장소 오류 — 실사 판정을 수행하지 못했습니다",
  internal_error: "실사 판정 중 내부 오류가 발생했습니다 — 결과가 없습니다",
};

export function reasonView(reason: string | null | undefined): { text: string; tone: Tone } {
  if (!reason) return { text: "사유 미상 — 실사 결과를 받지 못했습니다", tone: "danger" };
  const known = REASON_TEXT[reason];
  return { text: known ?? `알 수 없는 사유 (${reason}) — 확인되지 않았습니다`, tone: "danger" };
}
