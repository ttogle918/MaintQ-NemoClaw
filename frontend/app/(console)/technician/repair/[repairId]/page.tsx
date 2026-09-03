"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { RepairForm } from "@/components/asset/RepairForm";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Divider, Logo } from "@/components/ui/Chip";
import { Mono } from "@/components/ui/Mono";
import { StateBadge } from "@/components/ui/Badge";
import { ApiError, extractDetail, getRepair, submitRepair, type ApiRepair } from "@/lib/api";
import { isDraftState, stateView } from "@/lib/queueState";
import { sx } from "@/lib/sx";

/**
 * `/technician/repair/{repairId}` — 수리 증빙 상세 + draft 수정 (P39).
 *
 * `/technician/po/[poId]`(D111)와 같은 구조다. draft 면 수정 폼을, 아니면 읽기 전용
 * 카드로 전환한다(`isDraftState()` 재사용 — D87, 새 로컬 상수를 만들지 않는다).
 * 상태 어휘도 `stateView("repair", …)` 가 정한 것만 쓴다 — 화면이 상태를 직접 비교하지
 * 않는다(`/technician/po/[poId]` 가 그 위반으로 한 번 걸린 자리다).
 */
export default function RepairDetailPage() {
  const params = useParams<{ repairId: string }>();
  const repairId = params.repairId;

  const [repair, setRepair] = useState<ApiRepair | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(() => {
    setFailure(null);
    getRepair("technician", repairId)
      .then(setRepair)
      .catch((e: unknown) => {
        setFailure(
          e instanceof ApiError
            ? extractDetail(e.body) || "수리 증빙을 불러오지 못했습니다."
            : "백엔드에 연결하지 못했습니다."
        );
      });
  }, [repairId]);

  useEffect(load, [load]);

  async function onSubmit() {
    if (submitting || !repair) return;
    setSubmitting(true);
    setFailure(null);
    try {
      setRepair(await submitRepair(repair.repair_id));
    } catch (e) {
      setFailure(
        e instanceof ApiError
          ? extractDetail(e.body) || "제출하지 못했습니다."
          : "백엔드에 연결하지 못했습니다."
      );
    } finally {
      setSubmitting(false);
    }
  }


  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink2)")}>수리 증빙</span>
          <Mono size={11.5}>{repairId}</Mono>
          <Spacer />
          {repair && <StateBadge kind="repair" state={repair.state} />}
        </ConsoleHeader>

        <div style={sx("padding:16px 18px;display:flex;flex-direction:column;gap:14px")}>
          {failure && <StatusBanner tone="error">{failure}</StatusBanner>}

          {repair && isDraftState(repair.state) && (
            <>
              <RepairForm initial={repair} onDone={setRepair} />
              <Button
                onClick={!submitting ? () => void onSubmit() : undefined}
                style={submitting ? "opacity:.5;cursor:not-allowed" : ""}
              >
                {submitting ? "제출 중…" : "팀장 서명 요청"}
              </Button>
            </>
          )}

          {repair && !isDraftState(repair.state) && <ReadOnlyCard repair={repair} />}
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}

/** 제출 이후에는 수정할 수 없다 — 값만 보여준다. */
function ReadOnlyCard({ repair }: { repair: ApiRepair }) {
  const label = stateView("repair", repair.state);
  return (
    <div
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);" +
          "padding:12px 14px;display:flex;flex-direction:column;gap:8px"
      )}
    >
      <span style={sx("font:11px/1.6 'Pretendard';color:var(--dim2)")}>
        {label.text} 상태라 수정할 수 없습니다. 정정이 필요하면 새 증빙을 만들어야 합니다.
      </span>
      <Row k="설비" v={repair.equipment_id} />
      <Row k="작업 유형" v={repair.work_type ?? "—"} />
      <Row k="수리 범위" v={repair.repair_scope ?? "—"} />
      <Row k="비용" v={repair.cost != null ? `₩${repair.cost.toLocaleString()}` : "—"} />
      <Row
        k="교체 부품"
        v={(repair.parts ?? []).map((p) => p.part_no).join(", ") || "—"}
      />
      {/* 지출 성격은 서버 산출값이다 — 화면이 다시 계산하거나 색으로 판단하지 않는다(D64·D87) */}
      <Row k="지출 성격" v={repair.expenditure_class ?? "판정 없음"} />
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div style={sx("display:flex;justify-content:space-between;gap:10px")}>
      <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>{k}</span>
      <span style={sx("font:11.5px 'Pretendard';color:var(--ink2)")}>{v}</span>
    </div>
  );
}
