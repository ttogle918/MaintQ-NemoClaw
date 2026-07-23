"use client";

import { useState } from "react";
import { Toast } from "@/components/layout/Toast";
import { DiagnosticConsole } from "@/components/screens/DiagnosticConsole";
import { Mono } from "@/components/ui/Mono";
import { ApiError, submitPo } from "@/lib/api";
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
  const [toast, setToast] = useState<React.ReactNode>(null);
  const scenario: Scenario = searchParams?.scenario === "s3" ? "s3" : "s1";

  function show(node: React.ReactNode) {
    setToast(node);
    window.setTimeout(() => setToast(null), 3200);
  }

  /** draft → pending (A3 — 에이전트 루프 밖의 REST 전이) */
  async function requestApproval(poId: string) {
    try {
      const po = await submitPo(poId);
      show(
        <>
          <Mono>#{po.po_id}</Mono> 발주 요청이 팀장 승인 큐로 전달되었습니다
        </>
      );
    } catch (e) {
      show(
        e instanceof ApiError
          ? `승인 요청 실패 (${e.status})`
          : "백엔드에 연결하지 못했습니다 — 요청이 전달되지 않았습니다"
      );
    }
  }

  return (
    <>
      <DiagnosticConsole
        scenario={scenario}
        onRequestApproval={(poId) => void requestApproval(poId)}
      />
      {toast && <Toast>{toast}</Toast>}
    </>
  );
}
