import { DeadlinesPanel } from "@/components/asset/DeadlinesPanel";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { Divider, Logo } from "@/components/ui/Chip";
import { sx } from "@/lib/sx";

/**
 * `/manager/deadlines` — 법정 기한 추적 독립 페이지 (`track_deadlines`, `04 §17`, MQ-1204/S9).
 *
 * `manager/expenditure/page.tsx` 와 동일한 `ConsoleFrame`/`ConsoleHeader` 셸을 재사용한다.
 * `technician/equipment-status/[assetId]/page.tsx` 의 "기한 확인 →" 크로스링크가 `?asset_id=`
 * 로 도달하는 착지점이지만, 파라미터 없이 직접 방문해도 전체 범위로 동작한다(선택적).
 *
 * **아무것도 저장하지 않는다** (D71) — `track_deadlines` 는 무저장 조회다.
 */
export default function ManagerDeadlinesPage({
  searchParams,
}: {
  searchParams?: { asset_id?: string };
}) {
  const assetId = searchParams?.asset_id || undefined;

  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink2)")}>법정 기한 추적</span>
          <Spacer />
          <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
            무저장 조회 화면 — 아무것도 기록하지 않습니다 (D71)
          </span>
        </ConsoleHeader>

        <div style={sx("padding:16px 18px")}>
          <DeadlinesPanel assetId={assetId} />
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
