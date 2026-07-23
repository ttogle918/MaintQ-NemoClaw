"use client";

import { useState } from "react";
import { Toast } from "@/components/layout/Toast";
import { DiagnosticConsole } from "@/components/screens/DiagnosticConsole";
import { Mono } from "@/components/ui/Mono";
import type { Scenario } from "@/lib/mock/scenarios";

/**
 * /technician — 진단 콘솔. 이 라우트의 모든 API 호출은 X-Role: technician 으로 나간다.
 *
 * `?scenario=s3` 으로 반복 고장(S3) 화면을 볼 수 있다 — 데모 촬영용.
 */
export default function TechnicianPage({
  searchParams,
}: {
  searchParams?: { scenario?: string };
}) {
  const [toast, setToast] = useState(false);
  const scenario: Scenario = searchParams?.scenario === "s3" ? "s3" : "s1";

  function requestApproval() {
    // M2: POST /api/po/{id}/submit (X-Role: technician) → draft→pending (A3)
    setToast(true);
    window.setTimeout(() => setToast(false), 2600);
  }

  return (
    <>
      <DiagnosticConsole scenario={scenario} onRequestApproval={requestApproval} />
      {toast && (
        <Toast>
          <Mono>#PO-0117</Mono> 발주 요청이 팀장 승인 큐로 전달되었습니다
        </Toast>
      )}
    </>
  );
}
