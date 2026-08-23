"use client";

import { sx } from "@/lib/sx";
import type { ChatItem } from "@/lib/types";
import { A2aResultCard } from "./A2aResultCard";
import { AgentBubble, UserBubble } from "./Bubble";
import { ErrorLogAction } from "./ErrorLogAction";
import { PoDraftCard } from "./PoDraftCard";
import { PoHoldCard } from "./PoHoldCard";
import { RepeatFaultBanner } from "./RepeatFaultBanner";
import { SafetyBlock } from "./SafetyBlock";

/**
 * 대화 아이템 배열 → 렌더. M2 에서 이 배열이 SSE 스트림으로 채워진다.
 * block 이벤트는 도착 즉시 배열에 push 되므로 token 사이에 끼어들 수 있다 (D22).
 */
export function ChatThread({
  items,
  onRequestApproval,
}: {
  items: ChatItem[];
  onRequestApproval?: (poId: string) => void;
}) {
  return (
    <div style={sx("display:flex;flex-direction:column;gap:12px")}>
      {items.map((item) => {
        switch (item.kind) {
          case "user":
            return <UserBubble key={item.id}>{item.content}</UserBubble>;
          case "agent":
            return (
              <AgentBubble key={item.id} citations={item.citations}>
                {item.content}
              </AgentBubble>
            );
          case "safety":
            return (
              <SafetyBlock key={item.id} title={item.title} citation={item.citation}>
                {item.body}
              </SafetyBlock>
            );
          case "repeat_banner":
            return (
              <RepeatFaultBanner key={item.id} badge={item.badge}>
                {item.content}
              </RepeatFaultBanner>
            );
          case "po_draft":
            return (
              <PoDraftCard key={item.id} po={item.po} onRequestApproval={onRequestApproval} />
            );
          case "po_hold":
            return <PoHoldCard key={item.id} hold={item.hold} />;
          case "error_log":
            return (
              <ErrorLogAction
                key={item.id}
                equipmentId={item.equipmentId}
                code={item.code}
                recordedAt={item.recordedAt}
              />
            );
          case "a2a_result":
            return (
              <A2aResultCard
                key={item.id}
                skill={item.skill}
                chainId={item.chainId}
                status={item.status}
              />
            );
        }
      })}
    </div>
  );
}
