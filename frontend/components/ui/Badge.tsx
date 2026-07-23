import { sx } from "@/lib/sx";
import type { PoState, Urgency } from "@/lib/types";

export type BadgeTone = "neutral" | "blue" | "orange" | "ok" | "solid-orange";

const TONE: Record<BadgeTone, string> = {
  neutral: "color:var(--dim);border:1px solid var(--line2);background:transparent",
  blue: "color:var(--blue-tx);border:1px solid var(--cite-bd);background:var(--cite-bg)",
  orange:
    "color:var(--orange-tx);border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg)",
  ok: "color:var(--ok-tx);border:1px solid var(--ok-bd);background:var(--ok-bg)",
  "solid-orange": "color:#fff;border:1px solid var(--orange);background:var(--orange)",
};

export function Badge({
  children,
  tone = "neutral",
  size = 9,
}: {
  children: React.ReactNode;
  tone?: BadgeTone;
  size?: number;
}) {
  return (
    <span
      style={sx(
        `display:inline-flex;align-items:center;gap:3px;font:700 ${size}px 'JetBrains Mono',monospace;` +
          `border-radius:3px;padding:2px 6px;white-space:nowrap;${TONE[tone]}`
      )}
    >
      {children}
    </span>
  );
}

/* 상태 뱃지 — 승인 워크플로우 4상태 (05_DB_SCHEMA po_drafts.state) */
const STATE_LABEL: Record<PoState, string> = {
  draft: "draft",
  pending: "◔ pending",
  approved: "✓ approved",
  rejected: "✕ rejected",
};

const STATE_TONE: Record<PoState, BadgeTone> = {
  draft: "neutral",
  pending: "blue",
  approved: "ok",
  rejected: "orange",
};

export function StateBadge({ state, size }: { state: PoState; size?: number }) {
  return (
    <Badge tone={STATE_TONE[state]} size={size}>
      {STATE_LABEL[state]}
    </Badge>
  );
}

export function UrgencyBadge({ urgency, size }: { urgency: Urgency; size?: number }) {
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
