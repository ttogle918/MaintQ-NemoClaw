import { Mono } from "@/components/ui/Mono";
import type { ApiApproval, ApiPo } from "./api";
import type { Citation } from "./citation";
import { detailHref } from "./queueState";
import type { QueueLabel, QueueTone } from "./queueState";
import type { ApprovalKind, QueueEntry, EvidenceEntry, SupplierQuote, Urgency } from "./types";

/**
 * 백엔드 응답 → 화면 B 컴포넌트 props.
 *
 * 매핑을 한 곳에 모아 두는 이유: 컴포넌트가 API 모양을 직접 알면
 * 계약이 바뀔 때마다 UI 전체를 훑어야 한다.
 */

/**
 * 통합 큐 항목(D85) → 큐 한 줄.
 *
 * ⚠ 여기서 값을 **메우지 않는다**:
 *   - `urgency` 가 `null` 이면 `null` 그대로 — `"normal"` 로 채우면 처분서에 없는 긴급도가 생긴다
 *   - `state` 는 원 어휘 그대로 — 표시는 `stateView(kind, state)` 가 정한다
 *   - 모르는 `kind` 는 버리지 않고 **그대로 실어 보낸다**. 배지가 `⚠ 원문` 으로 뜨고
 *     상세에는 착지점이 없다고 말한다. 목록에서 지우면 "그런 승인 건이 없다"는 거짓말이 된다.
 */
export function toQueueEntry(item: ApiApproval): QueueEntry {
  return {
    // 좁히는 게 아니라 **표기**다 — 값을 검사해서 거르지 않는다. 모르는 종류가 오면
    // 그대로 통과하고, 화면에서 `⚠ 원문` 배지 + 착지점 없음으로 드러난다 (D87).
    // 여기서 `if (!KINDS.includes) return null` 을 하면 그 순간 항목이 조용히 사라진다.
    kind: item.kind as ApprovalKind,
    id: item.id,
    title: item.title,
    urgency: item.urgency,
    state: item.state,
    meta: [item.requested_by_name, relativeTime(item.created_at ?? "")]
      .filter(Boolean)
      .join(" · "),
    detailHref: detailHref(item.kind, item.id),
    verdict: item.verdict,
    requiresOverride: item.requires_override,
  };
}

/**
 * `GET /api/po/{id}` 상세 → 큐 한 줄.
 *
 * 큐 4목록(pending·approved·signed·rejected) **밖에 있는** 발주를 딥링크로 열었을 때
 * (예: 아직 `draft`) 헤더를 만들기 위한 경로다. 이게 없으면 "목록에 없다"는 이유로
 * 다른 발주의 헤더 위에 이 발주의 근거가 렌더된다 — 승인 화면에서 가장 위험한 종류의 오표시다.
 */
export function toPoQueueEntry(po: ApiPo): QueueEntry {
  return {
    kind: "po",
    id: po.po_id,
    title: `${po.part_name} ×${po.qty}`,
    urgency: po.urgency as Urgency,
    state: po.state,
    meta: [po.requested_by_name, relativeTime(po.created_at)].filter(Boolean).join(" · "),
    detailHref: detailHref("po", po.po_id),
    verdict: null, // 발주에는 처분 판정이 없다 — false 가 아니라 null 이다
    requiresOverride: null,
  };
}

export function toQuotes(po: ApiPo): SupplierQuote[] {
  const quotes = po.quotes ?? [];
  return quotes.map((q) => ({
    supplierId: q.supplier_id,
    name: q.name,
    leadDays: q.lead_days,
    unitPrice: q.unit_price,
    moq: q.moq,
    // 이 발주가 고른 공급사를 강조한다. 자동 추천 로직 자체는 백로그 P2
    recommended: q.supplier_id === po.supplier_id,
    note: quoteNote(q, po.qty),
  }));
}

function quoteNote(
  q: { lead_days: number; moq: number },
  qty: number
): string {
  // MOQ 미달이면 발주가 거부된다 (D31) — 고르기 전에 알려야 한다
  if (q.moq > qty) return `MOQ ${q.moq} — 수량 ${qty}로는 발주 불가 (D31)`;
  return q.lead_days <= 3 ? "최단 납기" : `리드타임 ${q.lead_days}일`;
}

/**
 * 근거 요약 카드 행 (D34).
 * symptoms → SYMPTOMS, basis 의 manual_page → DIAGNOSIS 인용, notes → NOTES.
 * 값이 없는 행은 아예 만들지 않는다 — 빈 행이 늘어지면 "3초 안에 읽는" 목적이 깨진다.
 */
export function toEvidenceEntries(po: ApiPo): EvidenceEntry[] {
  const rows: EvidenceEntry[] = [];

  if (po.model && po.error_code) {
    rows.push({
      label: "ERROR",
      value: (
        <>
          {po.model} · <Mono>{po.error_code}</Mono>
        </>
      ),
    });
  }

  const symptoms = po.evidence?.symptoms ?? [];
  if (symptoms.length) {
    rows.push({ label: "SYMPTOMS", value: symptoms.join(" · ") });
  }

  rows.push({ label: "DIAGNOSIS", value: po.reason, citation: firstCitation(po) });

  if (po.inventory) {
    const short = po.inventory.safety_stock - po.inventory.qty;
    rows.push({
      label: "INVENTORY",
      value: (
        <>
          재고 {po.inventory.qty} / 안전재고 {po.inventory.safety_stock}
          {short > 0 && <b> — 부족분 {short}</b>} · {po.inventory.location}
        </>
      ),
    });
  }

  if (po.evidence?.notes) {
    rows.push({ label: "NOTES", value: po.evidence.notes });
  }

  // session_id 가 없는 발주(사람이 직접 올린 소모품 보충 등)는 TRACE 행을 **만들지 않는다**.
  // 없는 세션도 200 을 주므로(D43) 링크는 열리지만 `/manager/trace/null` 이라는 착지점은
  // 존재하지 않는 세션을 가리키는 죽은 링크다 — 애초에 만들지 않는 게 맞다.
  if (po.session_id) {
    rows.push({
      label: "TRACE",
      value: "에이전트 실행 로그 전체 보기 →",
      href: `/manager/trace/${encodeURIComponent(po.session_id)}`,
    });
  }

  if (po.decision_note) {
    rows.push({
      label: po.state === "rejected" ? "반려 사유" : "승인 코멘트",
      value: `${po.decision_note}${po.decided_by_name ? ` (${po.decided_by_name})` : ""}`,
    });
  }

  return rows;
}

/**
 * basis 안의 `manual_page` 를 인용 칩으로.
 *
 * **`printPage` 는 백엔드가 준 값을 그대로 옮길 뿐, 여기서 계산하지 않는다 (D26·D32·D57).**
 * `evidence.basis[].manual_page` 는 PDF **물리** 페이지다 (D26 — 저장·검증의 단일 기준).
 * `print_page` 는 `GET /api/po/{id}` 가 응답 조립 시점에 계산해 붙인 값(D57,
 * `backend.services.po._attach_print_pages` → `manifest.to_print_page`) — 오프셋
 * 변환은 여전히 그 한 곳에서만 하고, 프론트는 옮겨 적기만 한다 (D32 불변).
 *
 * `model` 이 미확정(에러코드 승인 전 등)이거나 `manual_page` 가 없으면 백엔드가 `print_page`
 * 를 아예 안 보낸다 — 이때 `printPage` 를 `page` 로 채우면 offset 이 0 이 아닌 S100(16)에서
 * **물리 p.416 을 인쇄 p.416 인 양** 표시하게 된다(D32 가 막으려던 문제). 그래서 `printPage`
 * 는 **없으면 undefined 로 둔다** — `citationLabel()` 이 그 경우 `"{manual} PDF p.{page}"`
 * 로 정직하게 병기한다 (W-6 표시측 해소, Stage 1).
 */
function firstCitation(po: ApiPo): Citation | undefined {
  const basis = po.evidence?.basis?.find((b) => typeof b.manual_page === "number");
  if (!basis || typeof basis.manual_page !== "number") return undefined;
  return {
    manual: `${po.model ?? ""} 매뉴얼`.trim(),
    page: basis.manual_page,
    printPage: typeof basis.print_page === "number" ? basis.print_page : undefined,
  };
}

/* -------------------------------------------------------------------------- */
/* 수리 증빙 어휘 (S19, MQ-912) — repair 전용 상태 표시                          */

/**
 * `repair_records.state` → 배지 (D87). 통합 큐(`queueState.STATE_LABEL.repair`)는
 * 착지점(라우트)이 아직 없어 비워 뒀지만(`queueState.ts` 주석), **상태 문자열이 어떻게
 * 보여야 하는가**는 이 도구가 배관되는 지금 먼저 정한다 — 컴포넌트가 `draft`·`pending`
 * 같은 원 어휘를 직접 갖지 않고 이 매퍼를 거치게 하기 위해서다(D87, 큐 화면의
 * `stateView(kind, state)` 와 같은 태도를 repair 전용으로 반복한다).
 *
 * ⛔ 모르는 값을 성공색(`ok`)으로 칠하지 않는다 — 새 어휘가 오면 원문 + `warn` 이다.
 */
export const REPAIR_STATE_LABEL: Record<string, { text: string; tone: QueueTone }> = {
  draft: { text: "draft", tone: "neutral" },
  pending: { text: "◔ pending", tone: "info" },
  // 발주의 `approved` 와 같은 칸이 아니다 — 서명은 별개의 사건이다 (queueState.ts 와 같은 이유)
  signed: { text: "✓ signed", tone: "ok" },
  rejected: { text: "✕ rejected", tone: "danger" },
};

export function repairStateView(state: string): QueueLabel {
  const known = REPAIR_STATE_LABEL[state];
  if (!known) return { text: state, tone: "warn", known: false };
  return { ...known, known: true };
}

/* -------------------------------------------------------------------------- */
/* 수리 가치 판단 어휘 (S1+, MQ-914) — RepairValuePanel · ExpenditureCard ·      */
/* CriticalityDrawer · MetricsAside 가 공유한다 (D87 — 전역 total 맵 1곳).       */
/*                                                                            */
/* ⛔ 이 절 밖(네 컴포넌트 파일)에는 `verdict`·`part_class` 문자열 리터럴이나 색   */
/*   토큰이 있으면 안 된다 — `spikes/ui_honesty_contract.py` L2 가 `components/  */
/*   asset/*.tsx` 를 자동 스캔한다(README §설계 계약). 맵 밖 값은 전부           */
/*   `known:false` + `unknown` 톤으로 떨어진다 — 성공(`positive`)으로 새지 않는다.*/

export type MaintTone = "positive" | "info" | "neutral" | "caution" | "unknown";

const MAINT_SKIN: Record<MaintTone, string> = {
  positive: "border:1px solid var(--ok-bd);background:var(--ok-bg);color:var(--ok-tx)",
  info: "border:1px solid var(--cite-bd);background:var(--cite-bg);color:var(--blue-tx)",
  neutral: "border:1px solid var(--line2);background:var(--raise);color:var(--ink2)",
  // 경고색이되 에러는 아니다 — 실선(확정 차단)과 구분되는 점선 (DisposalPanel 의 hold 와 같은 규약)
  caution: "border:1.5px dashed var(--error-tx);background:transparent;color:var(--error-tx)",
  unknown: "border:1.5px dashed var(--dim2);background:transparent;color:var(--ink2)",
};

export interface MaintVerdictLabel {
  text: string;
  note: string;
  tone: MaintTone;
  skin: string;
  known: boolean;
}

/** `assess_repair_value` 의 5종 판정 (`04 §13`). */
const REPAIR_VALUE_VERDICT: Record<string, Omit<MaintVerdictLabel, "known" | "skin">> = {
  REPAIR_RECOMMENDED: {
    text: "수리 권장",
    note: "수리 후 회복분이 수리비 이상으로 산출되었습니다 — 시장가는 추정치입니다 (D65·D74).",
    tone: "positive",
  },
  REPLACE_RECOMMENDED: {
    text: "교체 권장",
    note: "부품 단종이거나 누적 수리비 비율이 높습니다.",
    tone: "info",
  },
  SELL_AS_IS: {
    text: "현상 매각 권장",
    note: "지표가 악화 추세이며 수리비가 매각 후 시장가를 넘습니다.",
    tone: "info",
  },
  ROOT_CAUSE_FIRST: {
    text: "근본원인 점검 우선",
    note: "직전 30일 안에 같은 설비에서 반복 고장이 확인됐습니다 — 3지 선택지 자체를 내지 않습니다.",
    tone: "caution",
  },
  HOLD: {
    text: "판단 유보",
    note: "시장가를 산출할 원천이 없어 유보했습니다 — '문제 없음'이 아닙니다. 금액을 추정해 메우지 마십시오.",
    tone: "caution",
  },
};

export function repairValueVerdictView(verdict: string | null | undefined): MaintVerdictLabel {
  if (!verdict) {
    return {
      text: "판정 없음",
      note: "응답에 판정 값이 없습니다 — 계약 위반 신호일 수 있습니다.",
      tone: "unknown",
      skin: MAINT_SKIN.unknown,
      known: false,
    };
  }
  const known = REPAIR_VALUE_VERDICT[verdict];
  if (!known) {
    return {
      text: verdict,
      note: "이 화면이 모르는 판정 값입니다 — 원문 그대로 표시합니다.",
      tone: "unknown",
      skin: MAINT_SKIN.unknown,
      known: false,
    };
  }
  return { ...known, skin: MAINT_SKIN[known.tone], known: true };
}

/** `classify_expenditure` 의 3종 판정 (`04 §12`). */
const EXPENDITURE_VERDICT: Record<string, Omit<MaintVerdictLabel, "known" | "skin">> = {
  CAPITAL: { text: "자본적 지출", note: "취득원가에 반영되는 지출로 분류됩니다.", tone: "neutral" },
  REVENUE: { text: "수익적 지출", note: "당기 비용으로 처리되는 지출로 분류됩니다.", tone: "neutral" },
  HOLD: {
    text: "판단 유보",
    note: "경계 사안이라 단정하지 않았습니다 — 세무 전문가 확인이 필요합니다. 실패가 아닙니다.",
    tone: "caution",
  },
};

export function expenditureVerdictView(verdict: string | null | undefined): MaintVerdictLabel {
  if (!verdict) {
    return {
      text: "판정 없음",
      note: "응답에 판정 값이 없습니다.",
      tone: "unknown",
      skin: MAINT_SKIN.unknown,
      known: false,
    };
  }
  const known = EXPENDITURE_VERDICT[verdict];
  if (!known) {
    return {
      text: verdict,
      note: "이 화면이 모르는 판정 값입니다 — 원문 그대로 표시합니다.",
      tone: "unknown",
      skin: MAINT_SKIN.unknown,
      known: false,
    };
  }
  return { ...known, skin: MAINT_SKIN[known.tone], known: true };
}

/** `classify_part_criticality` 의 등급 2종 (`04 §10`). `reviewed:false` — 사람 검수 전 초안. */
const PART_CLASS_LABEL: Record<string, Omit<MaintVerdictLabel, "known" | "skin">> = {
  CONSUMABLE: { text: "소모품", note: "정기 교체 대상 부품입니다.", tone: "neutral" },
  CRITICAL: { text: "핵심 부품", note: "설비 가동에 직결되는 핵심 부품입니다.", tone: "info" },
};

export function partClassView(partClass: string | null | undefined): MaintVerdictLabel {
  if (!partClass) {
    return {
      text: "미상",
      note: "등급이 조회되지 않았습니다 — 등급을 추측하지 않습니다.",
      tone: "unknown",
      skin: MAINT_SKIN.unknown,
      known: false,
    };
  }
  const known = PART_CLASS_LABEL[partClass];
  if (!known) {
    return {
      text: partClass,
      note: "이 화면이 모르는 등급 값입니다 — 원문 그대로 표시합니다.",
      tone: "unknown",
      skin: MAINT_SKIN.unknown,
      known: false,
    };
  }
  return { ...known, skin: MAINT_SKIN[known.tone], known: true };
}

/**
 * 근거(조문 원문) 수집 상태 → 표시 문구.
 *
 * `lib/decisionView.evidenceCompletenessView` 와 같은 어휘(`COMPLETE`|`LAW_TEXT_PENDING`)를
 * 쓰지만 문안은 처분 서명 맥락("서명용 증빙 불가")과 달라야 하므로 새로 둔다 — 지출 분류
 * 화면에는 서명이라는 사건 자체가 없다.
 */
const EXPENDITURE_EVIDENCE_LABEL: Record<string, string> = {
  COMPLETE: "조문 원문 수집 완료",
  LAW_TEXT_PENDING: "조문 원문 수집 대기",
};

export function expenditureEvidenceView(value: unknown): { text: string; known: boolean } {
  if (typeof value !== "string") return { text: "근거 수집 상태 미제공", known: false };
  const known = EXPENDITURE_EVIDENCE_LABEL[value];
  return known ? { text: known, known: true } : { text: `⚠ ${value}`, known: false };
}

/**
 * `assess_repair_value` 입력의 `repair_scope` 4종. **입력 옵션 목록도 여기 한 곳에 둔다** —
 * 값 중 하나(`REPLACE_UNIT` 등)가 컴포넌트 파일에 리터럴로 남으면 D87 이 막으려는
 * "컴포넌트가 어휘를 직접 든다"가 입력 쪽에서 재현된다.
 */
export interface WorkScopeOption {
  value: string;
  label: string;
}

export const WORK_SCOPE_OPTIONS: WorkScopeOption[] = [
  { value: "RESTORE", label: "원상 복구 (기본값)" },
  { value: "UPGRADE", label: "성능 개선" },
  { value: "OVERHAUL", label: "오버홀" },
  { value: "REPLACE_UNIT", label: "설비 단위 교체" },
];

function relativeTime(iso: string): string {
  const then = new Date(iso.replace(" ", "T")).getTime();
  if (Number.isNaN(then)) return "";
  const min = Math.floor((Date.now() - then) / 60000);
  if (min < 1) return "방금";
  if (min < 60) return `${min}분 전`;
  if (min < 60 * 24) return `${Math.floor(min / 60)}시간 전`;
  return `${Math.floor(min / 1440)}일 전`;
}
