"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ConsoleFrame,
  ConsoleHeader,
  ScreenStack,
  Spacer,
} from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { EmptyQueue } from "@/components/queue/EmptyQueue";
import { PoDetail } from "@/components/queue/PoDetail";
import { QueueList } from "@/components/queue/QueueList";
import { StatusLegend } from "@/components/queue/StatusLegend";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { ApiError, approvePo, getPo, getPoQueue, rejectPo, type ApiPo } from "@/lib/api";
import { toEvidenceEntries, toQueueEntry, toQuotes } from "@/lib/mappers";
import { EVIDENCE_PO_0117, PENDING, QUOTES_PO_0117, RECENT } from "@/lib/mock/queue";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";

type Source = "loading" | "live" | "mock";

/**
 * 화면 B — 승인 큐 (팀장).
 * 승인은 채팅 밖 전용 화면에서 한다 — 채팅에선 결재가 흘러가버린다 (D18).
 *
 * 백엔드가 꺼져 있으면 목업으로 떨어지되 **배너로 명시**한다.
 * 조용히 목업을 보여주면 데모에서 "동작한다"는 오해를 만든다.
 */
export function ApprovalQueueScreen({ selectedPoId }: { selectedPoId?: string }) {
  const [source, setSource] = useState<Source>("loading");
  const [queue, setQueue] = useState<ApiPo[]>([]);
  const [recent, setRecent] = useState<ApiPo[]>([]);
  const [detail, setDetail] = useState<ApiPo | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [pending, approved, rejected] = await Promise.all([
        getPoQueue("manager", "pending"),
        getPoQueue("manager", "approved"),
        getPoQueue("manager", "rejected"),
      ]);
      setQueue(pending);
      setRecent([...approved, ...rejected].slice(0, 4));

      const target = selectedPoId ?? pending[0]?.po_id;
      setDetail(target ? await getPo("manager", target) : null);
      setSource("live");
    } catch {
      setSource("mock");
    }
  }, [selectedPoId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(action: "approve" | "reject", reason?: string) {
    if (!detail) return;
    try {
      const updated =
        action === "approve"
          ? await approvePo(detail.po_id)
          : await rejectPo(detail.po_id, reason ?? "");
      setNotice(
        `${updated.po_id} ${action === "approve" ? "승인" : "반려"} 완료 — ${updated.state}`
      );
      await load();
    } catch (e) {
      // 403(권한)·409(순서)·422(사유 누락)를 구분해 보여준다 — 이게 D38 의 요점
      setNotice(e instanceof ApiError ? `${e.status} — ${extractDetail(e.body)}` : String(e));
    }
  }

  const live = source === "live";
  const pendingEntries = live ? queue.map(toQueueEntry) : PENDING;
  const recentEntries = live ? recent.map(toQueueEntry) : RECENT;
  const selected =
    pendingEntries.find((e) => e.poId === selectedPoId) ?? pendingEntries[0] ?? null;

  return (
    <ScreenStack>
      {source === "mock" && (
        <StatusBanner tone="warn">
          ⚠ 백엔드에 연결하지 못했습니다 — <b>목업 데이터</b>를 표시 중입니다. 승인·반려는 저장되지
          않습니다. (<code>uv run uvicorn backend.main:app --port 8000</code>)
        </StatusBanner>
      )}
      {notice && <StatusBanner tone="info">{notice}</StatusBanner>}

      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>
            승인 대기 <span style={sx("color:var(--orange-tx)")}>({pendingEntries.length})</span>
          </span>
          <Spacer />
          <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
            팀장 {ROLE_USER_NAME.manager}
          </span>
          <Avatar />
        </ConsoleHeader>

        {selected ? (
          <div style={sx("display:grid;grid-template-columns:280px 1fr;min-height:560px")}>
            <QueueList
              pending={pendingEntries}
              recent={recentEntries}
              selectedPoId={selected.poId}
            />
            <PoDetail
              entry={selected}
              evidence={live && detail ? toEvidenceEntries(detail) : EVIDENCE_PO_0117}
              quotes={live && detail ? toQuotes(detail) : QUOTES_PO_0117}
              onApprove={live ? () => void decide("approve") : undefined}
              onReject={live ? (reason) => void decide("reject", reason) : undefined}
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

function extractDetail(body: string): string {
  try {
    const j = JSON.parse(body);
    return typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
  } catch {
    return body.slice(0, 120);
  }
}
