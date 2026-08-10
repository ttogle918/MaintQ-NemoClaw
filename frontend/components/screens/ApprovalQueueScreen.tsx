"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ConsoleFrame,
  ConsoleHeader,
  ScreenStack,
  Spacer,
} from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { DecisionDetail } from "@/components/queue/DecisionDetail";
import { EmptyQueue } from "@/components/queue/EmptyQueue";
import { PoDetail } from "@/components/queue/PoDetail";
import { QueueList } from "@/components/queue/QueueList";
import { StatusLegend } from "@/components/queue/StatusLegend";
import { KindBadge, StateBadge } from "@/components/ui/Badge";
import { Avatar, Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  approvePo,
  extractDetail,
  getApprovals,
  getDecision,
  getPo,
  rejectPo,
  type ApiApproval,
  type ApiDecision,
  type ApiPo,
} from "@/lib/api";
import { toEvidenceEntries, toPoQueueEntry, toQueueEntry, toQuotes } from "@/lib/mappers";
import { EVIDENCE_PO_0117, PENDING, QUOTES_PO_0117, RECENT } from "@/lib/mock/queue";
import { ROLE_USER_NAME } from "@/lib/role";
import { sx } from "@/lib/sx";
import type { QueueEntry } from "@/lib/types";

type Source = "loading" | "live" | "mock";

/**
 * 화면 B — 통합 승인 큐 (팀장).
 * 승인은 채팅 밖 전용 화면에서 한다 — 채팅에선 결재가 흘러가버린다 (D18).
 *
 * 목록은 `GET /api/approvals` (D85) 로 **발주서·처분서를 한 큐**에 놓는다.
 * 상세는 `kind` 로 갈린다 — `po` → `PoDetail`(계약 무변경) · `disposal` → `DecisionDetail`.
 * 그 밖의 종류(`repair`, Sprint 8)는 **숨기지 않고** "상세가 없다"고 말한다.
 *
 * 백엔드가 꺼져 있으면 목업으로 떨어지되 **배너로 명시**한다.
 * 조용히 목업을 보여주면 데모에서 "동작한다"는 오해를 만든다.
 */
export function ApprovalQueueScreen({ selectedId }: { selectedId?: string }) {
  const [source, setSource] = useState<Source>("loading");
  const [pending, setPending] = useState<ApiApproval[]>([]);
  const [recent, setRecent] = useState<ApiApproval[]>([]);
  /** 선택된 항목 (라이브). 큐 목록 밖의 딥링크도 여기 들어온다 */
  const [selected, setSelected] = useState<QueueEntry | null>(null);
  /** 발주 상세 — `kind === "po"` 일 때만 채워진다 */
  const [detail, setDetail] = useState<ApiPo | null>(null);
  /** 처분 상세 — `kind === "disposal"` 일 때만 채워진다 (MQ-709b) */
  const [decision, setDecision] = useState<ApiDecision | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [missing, setMissing] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      // 종결 어휘가 종류마다 다르다 — 발주는 `approved`, 처분은 `signed` 다.
      // 한 어휘로 정규화하지 않기로 한 계약(D85)의 대가로 조회가 한 번 더 필요하다.
      // ⛔ 여기서 `approved` 를 처분에도 쓰지 말 것 — 서명은 다른 사건이다.
      const [p, approved, signed, rejected] = await Promise.all([
        getApprovals("manager", "pending"),
        getApprovals("manager", "approved"),
        getApprovals("manager", "signed"),
        getApprovals("manager", "rejected"),
      ]);
      const done = [...approved, ...signed, ...rejected].slice(0, 4);
      setPending(p);
      setRecent(done);

      const found = selectedId ? [...p, ...done].find((i) => i.id === selectedId) : null;

      if (selectedId && !found) {
        // 큐 4목록 밖의 발주(예: 아직 `draft`) 딥링크. `/api/po` 로 직접 확인한다 —
        // 여기서 그냥 첫 항목으로 미끄러지면 **다른 발주의 헤더 위에 이 발주의 근거**가
        // 렌더된다(승인 화면에서 가장 위험한 오표시다).
        try {
          const direct = await getPo("manager", selectedId);
          setSelected(toPoQueueEntry(direct));
          setDetail(direct);
          setDecision(null);
          setMissing(null);
          setSource("live");
          return;
        } catch {
          // 백엔드는 살아 있는데 그 ID 가 없는 것이다 — "목업 모드"라고 말하면 거짓말이다
          setMissing(`요청한 항목을 큐에서 찾을 수 없습니다 — ${selectedId}`);
        }
      }

      const target = found ?? p[0] ?? null;
      setSelected(target ? toQueueEntry(target) : null);
      // 종류별 상세는 각자의 경로에서 온다 — `/api/approvals` 는 목록 전용이다 (D85)
      setDetail(target?.kind === "po" ? await getPo("manager", target.id) : null);
      setDecision(
        target?.kind === "disposal" ? await getDecision("manager", target.id) : null
      );
      if (found || !selectedId) setMissing(null);
      setSource("live");
    } catch {
      setSource("mock");
    }
  }, [selectedId]);

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
  const pendingEntries = live ? pending.map(toQueueEntry) : PENDING;
  const recentEntries = live ? recent.map(toQueueEntry) : RECENT;
  const chosen = live
    ? selected
    : (pendingEntries.find((e) => e.id === selectedId) ?? pendingEntries[0] ?? null);

  return (
    <ScreenStack>
      {source === "mock" && (
        <StatusBanner tone="warn">
          ⚠ 백엔드에 연결하지 못했습니다 — <b>목업 데이터</b>를 표시 중입니다. 승인·반려는 저장되지
          않습니다. (<code>uv run uvicorn backend.main:app --port 8000</code>)
        </StatusBanner>
      )}
      {missing && <StatusBanner tone="warn">⚠ {missing}</StatusBanner>}
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

        {chosen ? (
          <div style={sx("display:grid;grid-template-columns:280px 1fr;min-height:560px")}>
            <QueueList
              pending={pendingEntries}
              recent={recentEntries}
              selectedId={chosen.id}
            />
            {chosen.kind === "po" ? (
              <PoDetail
                entry={chosen}
                evidence={live && detail ? toEvidenceEntries(detail) : EVIDENCE_PO_0117}
                quotes={live && detail ? toQuotes(detail) : QUOTES_PO_0117}
                onApprove={live ? () => void decide("approve") : undefined}
                onReject={live ? (reason) => void decide("reject", reason) : undefined}
              />
            ) : chosen.kind === "disposal" && live && decision ? (
              <DecisionDetail
                decision={decision}
                onUpdated={(updated) => {
                  setDecision(updated);
                  setNotice(`${updated.decision_id} — 상태 ${updated.state}`);
                  // 목록 재조회. 선택은 큐의 기존 규칙을 따른다(발주 승인 뒤와 같은 동작) —
                  // 서명한 건을 계속 보려면 `/manager/decision/{id}` 딥링크가 그 자리다.
                  void load();
                }}
                onReload={() => void load()}
              />
            ) : (
              <PendingImplementationDetail entry={chosen} />
            )}
          </div>
        ) : (
          <EmptyQueue />
        )}
      </ConsoleFrame>

      <StatusLegend />
    </ScreenStack>
  );
}

/**
 * 상세를 그릴 수 없는 자리.
 *
 * 남는 경우는 둘이다 — ⓐ 상세 화면이 아직 없는 종류(`repair`, Sprint 8) ⓑ 처분서인데
 * 백엔드에 연결되지 않아 `GET /api/decisions/{id}` 를 못 읽은 경우.
 * **숨기지 않고 "없다"고 말한다.** 큐에서 항목을 지우면 승인 대기 건수가 거짓이 되고,
 * 빈 화면을 주면 사용자는 로딩 실패로 읽는다.
 *
 * ⛔ 판정(`verdict`)을 여기서 해석하지 않는다 — 값이 있으면 원문 그대로 보여줄 뿐이다.
 *   "BLOCKED 는 이런 뜻입니다" 같은 요약은 `DecisionDetail` 의 해소 경로 목록이 할 일이다.
 */
function PendingImplementationDetail({ entry }: { entry: QueueEntry }) {
  const when =
    entry.kind === "disposal"
      ? "처분 상세는 백엔드(GET /api/decisions/{id})에서 옵니다 — 지금은 그 응답을 읽지 못했습니다."
      : "이 종류의 상세 화면은 다음 스프린트에서 붙습니다.";

  return (
    <div style={sx("display:flex;flex-direction:column;padding:18px 20px;gap:12px")}>
      <div style={sx("display:flex;align-items:center;gap:9px")}>
        <span style={sx("font:700 17px 'Pretendard';color:var(--ink)")}>
          <Mono size={15}>#{entry.id}</Mono> {entry.title}
        </span>
        <KindBadge kind={entry.kind} size={10} />
        <StateBadge kind={entry.kind} state={entry.state} size={10} />
        <div style={sx("flex:1")} />
        <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--dim2)")}>
          요청 · {entry.meta}
        </span>
      </div>

      {/* verdict 가 null 이면 이 영역은 아예 만들지 않는다 — 발주에는 판정이 없다 */}
      {entry.verdict && (
        <div
          style={sx(
            "border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);border-radius:7px;" +
              "padding:10px 12px;font:12px/1.6 'Pretendard';color:var(--saf-cite-tx)"
          )}
        >
          판정 <Mono size={12}>{entry.verdict}</Mono>
          {entry.requiresOverride === true &&
            " — 우회(override) 없이는 서명할 수 없습니다. 사유와 서명자가 기록됩니다."}
        </div>
      )}

      <div
        style={sx(
          "border:1px dashed var(--line2);border-radius:7px;padding:14px 16px;" +
            "font:12.5px/1.7 'Pretendard';color:var(--dim)"
        )}
      >
        <b style={sx("color:var(--ink2)")}>상세 화면이 아직 없습니다.</b>
        <br />
        {when} 지금 보이는 것은 큐 항목이 실어 온 값 그대로이며, 여기서 서명·반려할 수 없습니다.
      </div>
    </div>
  );
}
