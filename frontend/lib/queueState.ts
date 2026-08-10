/**
 * 승인 큐 어휘 → 화면 표시. **모르는 값을 초록으로 떨어뜨리지 않는 곳** (D87).
 *
 * 백엔드는 `state` 를 종류별 **원 어휘 그대로** 싣는다 (D85 · `services/approvals.py`).
 * 발주의 `approved` 와 처분의 `signed` 는 다른 사건이므로 한 어휘로 정규화하지 않고,
 * "어떻게 보이게 할 것인가"만 여기 한 곳에서 정한다.
 *
 * ⛔ 이 파일의 조회는 **total 이 아니다** — 맵에 없는 값은 조용히 통과시키는 대신
 *   `known:false` + `warn` 으로 **모른다는 사실을 화면에 남긴다**. 새 어휘가 생겼을 때
 *   "성공처럼 보이는 초록 배지"가 뜨는 것이 이 프로젝트에서 가장 나쁜 실패다.
 *
 * React 를 import 하지 않는다 — 순수 함수만 둔다.
 */
import type { ApprovalKind } from "./types";

/** 배지 톤. `Badge.tsx` 가 실제 색으로 옮긴다 (색 결정은 프리미티브 한 곳에서). */
export type QueueTone = "neutral" | "info" | "ok" | "danger" | "warn";

export interface QueueLabel {
  /** 표시 문자열. 모르는 값일 때는 **원문 그대로** — 번역·추측하지 않는다 */
  text: string;
  tone: QueueTone;
  /** 맵에 있던 값인가. `false` 면 화면이 "모르는 값"임을 함께 보여야 한다 */
  known: boolean;
}

export const KIND_LABEL: Record<ApprovalKind, string> = {
  po: "발주",
  disposal: "처분",
  repair: "수리",
};

/**
 * 종류별 상태 어휘. **`repair` 는 비어 있다** — Sprint 8 이 무슨 어휘를 쓸지 아직 정해지지
 * 않았고, 짐작해서 채우면 그게 곧 지어낸 사실이 된다. 그때까지 repair 의 모든 state 는
 * `warn` 으로 뜬다(그리고 그게 정확한 표현이다).
 */
export const STATE_LABEL: Record<ApprovalKind, Record<string, { text: string; tone: QueueTone }>> =
  {
    po: {
      draft: { text: "draft", tone: "neutral" },
      pending: { text: "◔ pending", tone: "info" },
      approved: { text: "✓ approved", tone: "ok" },
      rejected: { text: "✕ rejected", tone: "danger" },
    },
    disposal: {
      draft: { text: "draft", tone: "neutral" },
      pending: { text: "◔ pending", tone: "info" },
      // 발주의 `approved` 와 같은 칸이 아니다 — 서명은 책임 귀속이 붙는 별개의 사건이다 (D63)
      signed: { text: "✓ signed", tone: "ok" },
      rejected: { text: "✕ rejected", tone: "danger" },
    },
    repair: {},
  };

/**
 * `(kind, state)` → 배지.
 *
 * `kind` 도 `state` 도 **런타임에는 무엇이든 올 수 있다**(백엔드가 어휘를 늘리면 먼저
 * 도착하는 쪽이 화면이다). 그래서 인자를 `string` 으로 받고, 모르면 원문 + `warn` 이다.
 */
export function stateView(kind: string, state: string): QueueLabel {
  const known = (STATE_LABEL as Record<string, Record<string, { text: string; tone: QueueTone }>>)[
    kind
  ]?.[state];
  if (!known) return { text: state, tone: "warn", known: false };
  return { ...known, known: true };
}

/** `kind` → 배지. 모르는 종류도 숨기지 않는다 — 원문 + `warn` 으로 목록에 남는다. */
export function kindView(kind: string): QueueLabel {
  const label = (KIND_LABEL as Record<string, string>)[kind];
  if (!label) return { text: kind, tone: "warn", known: false };
  // 종류 배지는 **중립색 고정**이다. 오렌지는 안전·긴급 전용이고(frontend/README §설계 계약),
  // 파랑·초록은 상태 배지가 쓰고 있다 — 종류에 색을 더 쓰면 상태 색이 안 읽힌다.
  return { text: label, tone: "neutral", known: true };
}

/** 상세 화면 경로. 착지점이 **없는** 종류는 `null` 이다 — 없는 라우트를 지어내지 않는다. */
export function detailHref(kind: string, id: string): string | null {
  const enc = encodeURIComponent(id);
  if (kind === "po") return `/manager/po/${enc}`;
  // Stage 6(MQ-709b)이 만드는 라우트. 계약(경로)은 지금 확정하고 화면만 뒤에 붙는다.
  if (kind === "disposal") return `/manager/decision/${enc}`;
  // repair — Sprint 8. 라우트가 존재하지 않는다.
  return null;
}
