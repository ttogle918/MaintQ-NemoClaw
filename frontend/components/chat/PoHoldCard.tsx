"use client";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { sx } from "@/lib/sx";
import type { PoHold } from "@/lib/types";
import { CardShell, CardHead, CardFoot } from "./CardShell";

/**
 * S3 발주 보류 블록 — 발주 카드가 **아니다**.
 * 반복 고장에서는 원인이 확정될 때까지 발주서를 만들지 않는다 (02_SCENARIOS S3).
 *
 * 계약상 `po_card` block 의 variant 로 도착한다 (SSE 이벤트 4종 고정, D14·D22).
 */
export function PoHoldCard({ hold }: { hold: PoHold }) {
  return (
    <CardShell accent="orange">
      <CardHead
        title={
          <>
            <span style={sx("font-size:13px")}>⏸</span> 발주 보류 — 원인 확정 후 진행
          </>
        }
        right={
          <Badge tone="orange" size={9.5}>
            HOLD
          </Badge>
        }
      />

      <div style={sx("padding:11px 13px;font:12px/1.6 'Pretendard';color:var(--ink2)")}>
        {hold.reason}
        <div style={sx("margin-top:10px;display:flex;flex-direction:column;gap:7px")}>
          {hold.checklist.map((item) => (
            <ChecklistItem
              key={item.label}
              label={item.label}
              page={item.citation.printPage ?? item.citation.page}
            />
          ))}
        </div>
      </div>

      <CardFoot>
        <Button>점검 결과 입력</Button>
        <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
          원인 확정 시 발주서 초안 생성이 재개됩니다
        </span>
      </CardFoot>
    </CardShell>
  );
}

function ChecklistItem({ label, page }: { label: string; page: number }) {
  return (
    <label
      style={sx(
        "display:flex;align-items:center;gap:8px;font:12px 'Pretendard';color:var(--ink2);cursor:pointer"
      )}
    >
      <span
        style={sx(
          "width:15px;height:15px;border:1.5px solid var(--dim3);border-radius:3px;flex-shrink:0"
        )}
      />
      {label} <span style={sx("font:10px 'JetBrains Mono';color:var(--dim2)")}>· p.{page}</span>
    </label>
  );
}
