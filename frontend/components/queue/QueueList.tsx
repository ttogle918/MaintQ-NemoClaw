"use client";

import Link from "next/link";
import { StateBadge, UrgencyBadge } from "@/components/ui/Badge";
import { Mono } from "@/components/ui/Mono";
import { sx } from "@/lib/sx";
import type { QueueEntry } from "@/lib/types";

export function QueueList({
  pending,
  recent,
  selectedPoId,
}: {
  pending: QueueEntry[];
  recent: QueueEntry[];
  selectedPoId: string;
}) {
  return (
    <div
      style={sx(
        "border-right:1px solid var(--line);display:flex;flex-direction:column;background:var(--panel)"
      )}
    >
      <SectionLabel>승인 대기 · {pending.length}</SectionLabel>
      <div style={sx("padding:0 12px;display:flex;flex-direction:column;gap:8px")}>
        {pending.map((e) => (
          <QueueItem key={e.poId} entry={e} selected={e.poId === selectedPoId} />
        ))}
      </div>

      <div style={sx("height:1px;background:var(--line);margin:14px 12px 0")} />
      <SectionLabel>최근 처리</SectionLabel>
      <div style={sx("padding:0 12px 14px;display:flex;flex-direction:column;gap:8px")}>
        {recent.map((e) => (
          <QueueItem key={e.poId} entry={e} muted />
        ))}
      </div>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={sx(
        "padding:13px 14px 8px;font:700 11px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--dim2)"
      )}
    >
      {children}
    </div>
  );
}

/** 큐 아이템 — 클릭하면 /manager/po/{poId} 딥링크로 이동한다. */
function QueueItem({
  entry,
  selected = false,
  muted = false,
}: {
  entry: QueueEntry;
  selected?: boolean;
  muted?: boolean;
}) {
  const frame = selected
    ? "border:2px solid var(--blue);background:var(--sel)"
    : muted
      ? "border:1px solid var(--line);background:var(--surface);opacity:.72"
      : "border:1px solid var(--line2);background:var(--surface)";

  return (
    <Link
      href={`/manager/po/${entry.poId}`}
      style={sx(
        `display:block;text-decoration:none;border-radius:7px;padding:${muted ? "9px 11px" : "10px 11px"};cursor:pointer;${frame}`
      )}
    >
      <div style={sx("display:flex;gap:5px;margin-bottom:6px")}>
        {!muted && <UrgencyBadge urgency={entry.urgency} />}
        <StateBadge state={entry.state} />
      </div>
      <div
        style={sx(
          `font:${muted ? "600 12.5px" : "700 13px"} 'Pretendard';color:${muted ? "var(--ink2)" : "var(--ink)"}`
        )}
      >
        <Mono size={muted ? 11 : 12}>#{entry.poId}</Mono> {entry.title}
        {entry.note && (
          <span style={sx("font-size:11px;color:var(--dim)")}> {entry.note}</span>
        )}
      </div>
      {entry.meta && (
        <div
          style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2);margin-top:3px")}
        >
          {entry.meta}
        </div>
      )}
    </Link>
  );
}
