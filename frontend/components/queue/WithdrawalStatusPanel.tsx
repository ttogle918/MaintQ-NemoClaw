"use client";

import { useEffect, useState } from "react";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { a2aStatusTone, type Tone } from "@/lib/a2a";
import { getA2aHistory, type ApiA2aHistoryItem } from "@/lib/api";
import { sx } from "@/lib/sx";

/** `a2aStatusTone` 의 톤 → 배지 프리미티브 톤 (D87). 실패·미상은 초록으로 떨어지지 않는다. */
const TONE_BADGE: Record<Tone, BadgeTone> = {
  ok: "ok",
  warn: "unknown",
  error: "unknown",
  unknown: "unknown",
};

/**
 * 발주 상세에 출금요청(FinAllQ, `request-withdrawal`) 처리 상태를 부착한다 (MQ-1608, D114).
 *
 * 읽기 전용 — 승인/반려 로직에 개입하지 않는다 (D18). 이력이 없으면(승인 전이거나
 * `partner_links` 미연결) 아무것도 렌더하지 않는다 — 정상 상태를 실패처럼 보이게 하지 않는다.
 */
export function WithdrawalStatusPanel({ poId }: { poId: string }) {
  const [item, setItem] = useState<ApiA2aHistoryItem | null>(null);

  useEffect(() => {
    let cancelled = false;
    setItem(null);
    getA2aHistory("manager", { poId, skill: "request-withdrawal" })
      .then((res) => {
        if (!cancelled) setItem(res.items[0] ?? null);
      })
      .catch(() => {
        if (!cancelled) setItem(null);
      });
    return () => {
      cancelled = true;
    };
  }, [poId]);

  if (item === null) return null;

  const detail = typeof item.response?.detail === "string" ? item.response.detail : null;
  const taskId = typeof item.response?.task_id === "string" ? item.response.task_id : null;

  return (
    <div
      style={sx(
        "display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:9px 12px;" +
          "margin-bottom:12px;border:1px solid var(--line2);border-radius:6px;background:var(--panel)"
      )}
    >
      <span
        style={sx(
          "font:700 10px 'JetBrains Mono',monospace;letter-spacing:.06em;color:var(--dim2)"
        )}
      >
        출금요청
      </span>
      <Badge tone={TONE_BADGE[a2aStatusTone(item.status)]} size={10}>
        {item.status ?? "unknown"}
      </Badge>
      {detail && (
        <span style={sx("font:12px 'Pretendard';color:var(--ink2)")}>{detail}</span>
      )}
      {taskId && (
        <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim3)")}>
          task:{taskId}
        </span>
      )}
    </div>
  );
}
