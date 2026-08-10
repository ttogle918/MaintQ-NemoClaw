import { kindView, stateView, type QueueTone } from "@/lib/queueState";
import { sx } from "@/lib/sx";
import type { Urgency } from "@/lib/types";

export type BadgeTone = "neutral" | "blue" | "orange" | "ok" | "solid-orange" | "unknown";

const TONE: Record<BadgeTone, string> = {
  neutral: "color:var(--dim);border:1px solid var(--line2);background:transparent",
  blue: "color:var(--blue-tx);border:1px solid var(--cite-bd);background:var(--cite-bg)",
  orange:
    "color:var(--orange-tx);border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg)",
  ok: "color:var(--ok-tx);border:1px solid var(--ok-bd);background:var(--ok-bg)",
  "solid-orange": "color:#fff;border:1px solid var(--orange);background:var(--orange)",
  // 모르는 어휘 전용 (D87). 초록(ok)·중립(neutral) 어느 쪽으로도 떨어지지 않게 **별도 색**이다.
  // 오렌지를 쓰지 않는 이유: 오렌지는 안전·긴급 전용이라 여기서 빌려 쓰면 경고가 무감각해진다.
  unknown: "color:var(--error-tx);border:1px dashed var(--error-tx);background:transparent",
};

/** 큐 어휘 톤(`lib/queueState`) → 배지 톤. 색 결정은 프리미티브 한 곳에 모아 둔다. */
const QUEUE_TONE: Record<QueueTone, BadgeTone> = {
  neutral: "neutral",
  info: "blue",
  ok: "ok",
  danger: "orange",
  warn: "unknown",
};

export function Badge({
  children,
  tone = "neutral",
  size = 9,
  title,
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
  size?: number;
  /** 마우스 오버 설명 — 모르는 어휘일 때 원문·종류를 그대로 보여 준다 */
  title?: string;
}) {
  return (
    <span
      title={title}
      style={sx(
        `display:inline-flex;align-items:center;gap:3px;font:700 ${size}px 'JetBrains Mono',monospace;` +
          `border-radius:3px;padding:2px 6px;white-space:nowrap;${TONE[tone]}`
      )}
    >
      {children}
    </span>
  );
}

/**
 * 상태 뱃지 — **종류별 어휘가 다르다.** 발주 `approved` 와 처분 `signed` 는 다른 사건이라
 * `kind` 없이는 상태를 해석할 수 없다 (D85). 라벨·톤은 `lib/queueState` 가 단일 출처다.
 *
 * 모르는 어휘는 `⚠ 원문` + 점선 배지로 나온다 — 초록으로 떨어지지 않는다 (D87).
 */
export function StateBadge({
  kind,
  state,
  size,
}: {
  kind: string;
  state: string;
  size?: number;
}) {
  const v = stateView(kind, state);
  return (
    <Badge tone={QUEUE_TONE[v.tone]} size={size} title={v.known ? undefined : `모르는 상태 값 — ${kind}/${state}`}>
      {v.known ? v.text : `⚠ ${v.text}`}
    </Badge>
  );
}

/** 승인 대상 종류 배지. **중립색 고정** — 색 예산은 상태·긴급도가 쓴다. */
export function KindBadge({ kind, size }: { kind: string; size?: number }) {
  const v = kindView(kind);
  return (
    <Badge tone={QUEUE_TONE[v.tone]} size={size} title={v.known ? undefined : `모르는 종류 — ${kind}`}>
      {v.known ? v.text : `⚠ ${v.text}`}
    </Badge>
  );
}

/**
 * 긴급도 배지. **`null` 이면 아무것도 렌더하지 않는다** — 처분서에는 긴급도 개념이 없고,
 * `"일반"` 으로 채우면 없는 사실이 화면에 생긴다 (D62·D87).
 */
export function UrgencyBadge({ urgency, size }: { urgency: Urgency | null; size?: number }) {
  if (urgency === null) return null;
  return urgency === "urgent" ? (
    <Badge tone="solid-orange" size={size}>
      ▲ 긴급
    </Badge>
  ) : (
    <Badge tone="neutral" size={size}>
      일반
    </Badge>
  );
}
