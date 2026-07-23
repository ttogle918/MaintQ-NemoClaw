"use client";

import {
  ConsoleFrame,
  ConsoleHeader,
  ScreenStack,
  Spacer,
} from "@/components/layout/ConsoleFrame";
import { EmptyQueue } from "@/components/queue/EmptyQueue";
import { PoDetail } from "@/components/queue/PoDetail";
import { QueueList } from "@/components/queue/QueueList";
import { StatusLegend } from "@/components/queue/StatusLegend";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { EVIDENCE_PO_0117, PENDING, QUOTES_PO_0117, RECENT } from "@/lib/mock/queue";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";

/**
 * 화면 B — 승인 큐 (팀장).
 * 승인은 채팅 밖 전용 화면에서 한다 — 채팅에선 결재가 흘러가버린다 (D18).
 */
export function ApprovalQueueScreen({ selectedPoId }: { selectedPoId?: string }) {
  const pending = PENDING;
  const selected = pending.find((e) => e.poId === selectedPoId) ?? pending[0];

  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>
            승인 대기 <span style={sx("color:var(--orange-tx)")}>({pending.length})</span>
          </span>
          <Spacer />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
            팀장 {ROLE_USER_NAME.manager}
          </span>
          <Avatar />
        </ConsoleHeader>

        {selected ? (
          <div style={sx("display:grid;grid-template-columns:280px 1fr;min-height:560px")}>
            <QueueList pending={pending} recent={RECENT} selectedPoId={selected.poId} />
            <PoDetail
              entry={selected}
              evidence={EVIDENCE_PO_0117}
              quotes={QUOTES_PO_0117}
            />
          </div>
        ) : (
          <EmptyQueue />
        )}
      </ConsoleFrame>

      <StatusLegend />
    </ScreenStack>
  );
}
