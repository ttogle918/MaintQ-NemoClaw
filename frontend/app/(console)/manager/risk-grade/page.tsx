import { LoanAssessmentHistory } from "@/components/asset/LoanAssessmentHistory";
import { RiskGradeGrid } from "@/components/asset/RiskGradeGrid";
import { ConsoleFrame, ConsoleHeader, ScreenStack, Spacer } from "@/components/layout/ConsoleFrame";
import { Divider, Logo } from "@/components/ui/Chip";
import { sx } from "@/lib/sx";

/**
 * `/manager/risk-grade` — 건물 위험등급 독립 페이지 (`assess_risk_grade`, `04 §18`, MQ-1204/S18).
 *
 * `manager/expenditure/page.tsx` 와 동일한 `ConsoleFrame`/`ConsoleHeader` 셸을 재사용한다.
 * 파라미터가 없다 — 항상 전체 건물을 대상으로 그리드를 그린다(`RiskGradeGrid` 자체가 조회 대상을
 * 정한다).
 *
 * **아무것도 저장하지 않는다** (D71) — `assess_risk_grade` 는 무저장 조회+계산이다.
 */
export default function ManagerRiskGradePage() {
  return (
    <ScreenStack>
      <ConsoleFrame>
        <ConsoleHeader>
          <Logo />
          <span style={sx("font:600 13px 'Pretendard';color:var(--ink)")}>MaintQ</span>
          <Divider />
          <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink2)")}>건물 위험등급</span>
          <Spacer />
          <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
            무저장 조회 화면 — 아무것도 기록하지 않습니다 (D71)
          </span>
        </ConsoleHeader>

        <div style={sx("padding:16px 18px")}>
          <RiskGradeGrid />
          <div style={sx("margin-top:20px")}>
            <LoanAssessmentHistory />
          </div>
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
