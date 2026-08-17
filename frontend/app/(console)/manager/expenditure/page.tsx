import { ExpenditureForm } from "@/components/asset/ExpenditureForm";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { Divider, Logo } from "@/components/ui/Chip";
import { sx } from "@/lib/sx";

/**
 * `/manager/expenditure` — 지출 분류 독립 페이지 (`classify_expenditure`, `04 §12`, MQ-1001/P37).
 *
 * 자산 컨텍스트 없이 부품을 직접 검색해 지출 성격(자본적/수익적)을 판정한다 —
 * `value/page.tsx` 의 `ExpenditureCard` 는 3지 판단(`assess_repair_value`)이 이미 넘겨준
 * 등급으로 자동 판정하는 반면, 이 화면은 사용자가 직접 부품을 고른다.
 *
 * **아무것도 저장하지 않는다** (D71) — `classify_expenditure` 는 무저장 판정이고, 이 화면은
 * 조회·판정만 한다. 신고를 대신하지 않는다(세무·회계 참고용).
 */
export default function ManagerExpenditurePage() {
  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink2)")}>지출 성격 분류</span>
          <Spacer />
          <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
            무저장 판정 화면 — 아무것도 기록하지 않습니다 (D71)
          </span>
        </ConsoleHeader>

        <div style={sx("padding:16px 18px")}>
          <ExpenditureForm />
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
