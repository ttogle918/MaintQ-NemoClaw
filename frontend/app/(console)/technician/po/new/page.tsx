"use client";

import { useRouter } from "next/navigation";
import { PoForm } from "@/components/asset/PoForm";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { Divider, Logo } from "@/components/ui/Chip";
import { createPo, type ApiPo } from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * `/technician/po/new` — 발주 초안 화면 직접 생성 (D111, P39 축소판·P41 ② 선결과제).
 *
 * 채팅을 거치지 않는 첫 발주 생성 경로다. `InventoryDrawer`의 "발주하러 가기"가
 * 여기로 온다(부품은 프리필하지 않는다 — `PoForm`이 부품 검색부터 시작하는 게 기본
 * 흐름이라, 완전 자동 선택은 사용자가 확인 없이 부품이 골라지는 것이라 D31 의
 * "사람이 확인 후 호출" 정신과 어긋난다).
 *
 * 생성 성공 시 `/technician/po/{po_id}`로 이동한다 — 그 화면이 상세+수정을 맡는다.
 */
export default function NewPoPage() {
  const router = useRouter();

  function onSuccess(po: ApiPo) {
    router.push(`/technician/po/${encodeURIComponent(po.po_id)}`);
  }

  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink2)")}>발주 초안 생성</span>
          <Spacer />
          <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
            생성 후에도 승인 요청 전까지는 수정할 수 있습니다
          </span>
        </ConsoleHeader>

        <div style={sx("padding:16px 18px")}>
          <PoForm mode="create" onSubmit={createPo} onSuccess={onSuccess} />
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
