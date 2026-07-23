"use client";

import { ChatComposer } from "@/components/chat/ChatComposer";
import { ChatThread } from "@/components/chat/ChatThread";
import {
  ConsoleFrame,
  ConsoleHeader,
  ScreenStack,
  Spacer,
} from "@/components/layout/ConsoleFrame";
import { TracePanel } from "@/components/trace/TracePanel";
import { Avatar, Divider, Logo, SelectChip } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import { CHAT_BY_SCENARIO, type Scenario } from "@/lib/mock/scenarios";
import { TRACE_S1, TRACE_S3 } from "@/lib/mock/trace";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";

const TRACE_BY_SCENARIO = { s1: TRACE_S1, s3: TRACE_S3 };

/**
 * 화면 A — 진단 콘솔 (정비사).
 * 좌 채팅 · 우 실행 trace. trace 쪽이 이 제품의 주인공이라 시각적 무게를 뺏기지 않게 둔다.
 */
export function DiagnosticConsole({
  scenario = "s1",
  onRequestApproval,
}: {
  scenario?: Scenario;
  onRequestApproval?: (poId: string) => void;
}) {
  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <SelectChip>라인 · 1번 조립</SelectChip>
          <SelectChip>
            장비 · <Mono size={11}>LS iG5A</Mono>
          </SelectChip>
          <Spacer />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
            정비사 {ROLE_USER_NAME.technician}
          </span>
          <Avatar />
        </ConsoleHeader>

        <div style={sx("display:grid;grid-template-columns:1.25fr 1fr;min-height:580px")}>
          <div style={sx("display:flex;flex-direction:column;border-right:1px solid var(--line)")}>
            <div style={sx("flex:1;padding:16px;display:flex;flex-direction:column;gap:12px")}>
              <ChatThread
                items={CHAT_BY_SCENARIO[scenario]}
                onRequestApproval={onRequestApproval}
              />
            </div>
            <ChatComposer />
          </div>

          <TracePanel session={TRACE_BY_SCENARIO[scenario]} />
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
