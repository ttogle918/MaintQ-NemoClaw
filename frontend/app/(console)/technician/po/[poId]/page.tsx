"use client";

import { useCallback, useEffect, useState } from "react";
import { PoForm } from "@/components/asset/PoForm";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import { StateBadge } from "@/components/ui/Badge";
import { ApiError, extractDetail, getPo, submitPo, updatePo, type ApiPo } from "@/lib/api";
import { isDraftState, stateView } from "@/lib/queueState";
import { sx } from "@/lib/sx";

/**
 * `/technician/po/{poId}` — 발주 초안 상세 + 수정(draft 상태에서만) + 승인 요청.
 *
 * `state==='draft'` 면 `PoForm`(edit 모드, 부품 고정)을 보여주고, 그 이상 상태면
 * 읽기 전용 카드로 전환한다(`isDraftState()` 재사용 — D87, 새 로컬 상수를 만들지 않는다).
 * 매니저 상세 화면(`/manager/po/[poId]`, `ApprovalQueueScreen`)과 컴포넌트를 공유하지
 * 않는다 — 기술자 화면은 "내가 만든 초안을 고친다"는 톤이고 매니저 화면은 "승인 큐 항목을
 * 판단한다"는 톤이라 정보 밀도·액션이 다르다.
 */
export default function TechnicianPoDetailPage({ params }: { params: { poId: string } }) {
  const poId = decodeURIComponent(params.poId);

  const [po, setPo] = useState<ApiPo | null>(null);
  const [loadFailure, setLoadFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(async () => {
    try {
      const p = await getPo("technician", poId);
      setPo(p);
      setLoadFailure(null);
    } catch (e) {
      setPo(null);
      setLoadFailure(
        e instanceof ApiError && e.status === 404
          ? `발주서를 찾을 수 없습니다 — ${poId}`
          : "백엔드에 연결하지 못했습니다."
      );
    }
  }, [poId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function requestApproval() {
    if (!po || submitting) return;
    setSubmitting(true);
    try {
      const updated = await submitPo(po.po_id);
      setNotice(`팀장 승인 큐로 전달되었습니다 — ${updated.state}`);
      await load();
    } catch (e) {
      setNotice(e instanceof ApiError ? `${e.status} — ${extractDetail(e.body)}` : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (loadFailure) {
    return (
      <ScreenStack>
        <StatusBanner tone="error">⚠ {loadFailure}</StatusBanner>
      </ScreenStack>
    );
  }

  if (!po) {
    return (
      <ScreenStack>
        <div style={sx("font:12.5px 'Pretendard';color:var(--dim);padding:24px")}>
          불러오는 중… <Mono>{poId}</Mono>
        </div>
      </ScreenStack>
    );
  }

  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <Mono size={12.5}>{po.po_id}</Mono>
          <StateBadge kind="po" state={po.state} size={10} />
          <Spacer />
          {isDraftState(po.state) && (
            <Button size="sm" onClick={submitting ? undefined : () => void requestApproval()}>
              {submitting ? "요청 중…" : "팀장 승인 요청"}
            </Button>
          )}
        </ConsoleHeader>

        {notice && (
          <div style={sx("padding:10px 18px 0")}>
            <StatusBanner tone="info">{notice}</StatusBanner>
          </div>
        )}

        <div style={sx("padding:16px 18px")}>
          {isDraftState(po.state) ? (
            <PoForm
              mode="edit"
              lockedPart={{ part_no: po.part_no, part_name: po.part_name }}
              initial={{ qty: po.qty, supplier_id: po.supplier_id, reason: po.reason, urgency: po.urgency }}
              onSubmit={(body) => updatePo(po.po_id, body)}
              onSuccess={(updated) => {
                setPo(updated);
                setNotice("수정을 저장했습니다.");
              }}
            />
          ) : (
            <ReadOnlyCard po={po} />
          )}
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}

/* -------------------------------------------------------------------------- */

function ReadOnlyCard({ po }: { po: ApiPo }) {
  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:13px 15px;" +
          "display:flex;flex-direction:column;gap:9px"
      )}
    >
      <div style={sx("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
        <Mono size={12}>{po.part_no}</Mono>
        <span style={sx("font:12.5px 'Pretendard';color:var(--ink)")}>{po.part_name}</span>
      </div>
      <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>
        수량 {po.qty} · 공급사 {po.supplier_name} · 단가 {po.unit_price.toLocaleString()}원 · 총액{" "}
        {(po.unit_price * po.qty).toLocaleString()}원
      </span>
      <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>사유 — {po.reason}</span>
      {/* 이 카드는 draft 가 아닐 때만 렌더된다(부모의 isDraftState 분기) — 상태 문구는
          state 리터럴을 직접 비교하지 않고 stateView() 맵 한 곳에서만 가져온다 (D87) */}
      <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>
        {stateView("po", po.state).text} — draft 상태가 아니므로 이 화면에서 더 이상 수정할 수 없습니다
      </span>
    </section>
  );
}
