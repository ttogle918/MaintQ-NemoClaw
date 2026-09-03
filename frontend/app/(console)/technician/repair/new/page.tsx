"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { RepairForm } from "@/components/asset/RepairForm";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { Divider, Logo } from "@/components/ui/Chip";
import { type ApiRepair } from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * `/technician/repair/new` — 수리 증빙 초안 화면 직접 생성 (P39).
 *
 * `/technician/po/new`(D111)와 같은 구조다. 채팅을 거치지 않는 수리 증빙 생성 경로이며,
 * 설비 상세에서 `?equipment=INV-L3-01` 로 넘어오면 설비 ID 만 프리필한다 — 부품은
 * 프리필하지 않는다(`PoForm` 선례와 같은 이유: 사용자 확인 없이 부품이 골라지면
 * "무엇을 갈았는지"를 사람이 확인하지 않은 채 증빙이 만들어진다).
 *
 * 생성 성공 시 `/technician/repair/{repair_id}` 로 이동한다 — 그 화면이 상세+수정을 맡는다.
 */
export default function NewRepairPage() {
  return (
    <Suspense fallback={null}>
      <NewRepairInner />
    </Suspense>
  );
}

function NewRepairInner() {
  const router = useRouter();
  const params = useSearchParams();
  const equipmentId = params.get("equipment") ?? undefined;

  function onDone(repair: ApiRepair) {
    router.push(`/technician/repair/${encodeURIComponent(repair.repair_id)}`);
  }

  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink2)")}>
            수리 증빙 초안 생성
          </span>
          <Spacer />
          <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
            생성 후에도 서명 요청 전까지는 수정할 수 있습니다
          </span>
        </ConsoleHeader>

        <div style={sx("padding:16px 18px")}>
          <RepairForm equipmentId={equipmentId} onDone={onDone} />
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
