"use client";

import Link from "next/link";
import { KindBadge, StateBadge, UrgencyBadge } from "@/components/ui/Badge";
import { Mono } from "@/components/ui/Mono";
import { sx } from "@/lib/sx";
import type { QueueEntry } from "@/lib/types";

/**
 * 통합 승인 큐 목록 (D85) — 발주서·처분서·(수리)가 한 목록에 선다.
 * 항목 식별자는 `poId` 가 아니라 `id` 다. 종류는 `kind` 배지로 구분한다.
 */
export function QueueList({
  pending,
  recent,
  selectedId,
}: {
  pending: QueueEntry[];
  recent: QueueEntry[];
  selectedId: string;
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
          <QueueItem key={`${e.kind}:${e.id}`} entry={e} selected={e.id === selectedId} />
        ))}
      </div>

      <div style={sx("height:1px;background:var(--line);margin:14px 12px 0")} />
      <SectionLabel>최근 처리</SectionLabel>
      <div style={sx("padding:0 12px 14px;display:flex;flex-direction:column;gap:8px")}>
        {recent.map((e) => (
          <QueueItem key={`${e.kind}:${e.id}`} entry={e} muted />
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

/**
 * 큐 아이템 — 클릭하면 `entry.detailHref` 딥링크로 이동한다.
 *
 * **착지점이 없는 종류(`detailHref === null`, 현재 `repair`)는 링크가 아니라 안내다.**
 * 목록에서 지우지 않는 이유: 숨기면 "그런 승인 건이 없다"가 되고, 빈 링크를 주면
 * "눌렀는데 아무 일도 안 난다"가 된다. 둘 다 사실을 감춘다 (D87).
 */
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
  const box = `display:block;text-decoration:none;border-radius:7px;padding:${
    muted ? "9px 11px" : "10px 11px"
  };${frame}`;

  const body = (
    <>
      <div style={sx("display:flex;gap:5px;margin-bottom:6px;align-items:center")}>
        <KindBadge kind={entry.kind} />
        {/* urgency 가 null 이면 배지 자체가 렌더되지 않는다 — "일반"으로 채우지 않는다 */}
        {!muted && <UrgencyBadge urgency={entry.urgency} />}
        <StateBadge kind={entry.kind} state={entry.state} />
      </div>
      <div
        style={sx(
          `font:${muted ? "600 12.5px" : "700 13px"} 'Pretendard';color:${muted ? "var(--ink2)" : "var(--ink)"}`
        )}
      >
        <Mono size={muted ? 11 : 12}>#{entry.id}</Mono> {entry.title}
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
    </>
  );

  if (!entry.detailHref) {
    return (
      <div style={sx(`${box};cursor:default`)}>
        {body}
        <div
          style={sx("font:11px 'Pretendard';color:var(--dim2);margin-top:4px;font-style:italic")}
        >
          상세 화면이 아직 없습니다 — 이 종류는 다음 스프린트에서 붙습니다.
        </div>
      </div>
    );
  }

  return (
    <Link href={entry.detailHref} style={sx(`${box};cursor:pointer`)}>
      {body}
    </Link>
  );
}
