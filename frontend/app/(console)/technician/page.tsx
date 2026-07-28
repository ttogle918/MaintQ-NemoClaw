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
 * 라우트 분기 (MQ-405):
 *   ?scenario=s1|s3  → 목업 화면 보존 (데모 촬영·error_codes 승인 전 S3 그림)
 *   ?replay=s1       → 라이브 + 재생 데모 자동 흐름 (키 없이 동작, D55)
 *   (쿼리 없음)       → 라이브 실 루프
 * `?replay=S1` 같은 오타는 라이브 기본으로 떨어진다 (백엔드 400 을 유발하지 않는다).
 */
export default function TechnicianPage({
  searchParams,
}: {
  searchParams?: { scenario?: string; replay?: string };
}) {
  const [toast, setToast] = useState<React.ReactNode>(null);

  const scenarioParam = searchParams?.scenario;
  const scenario: Scenario | null =
    scenarioParam === "s1" || scenarioParam === "s3" ? scenarioParam : null;
  const replay = searchParams?.replay === "s1" ? "s1" : undefined;

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
      if (e instanceof ApiError && e.status === 409) {
        // 재생 데모의 PO-0117 은 DB 상 이미 pending → 409 가 정상이다 (403 과 구분, D38).
        show("이미 요청된 발주입니다 — 재생 데모 데이터");
      } else if (e instanceof ApiError) {
        show(`승인 요청 실패 (${e.status})`);
      } else {
        show("백엔드에 연결하지 못했습니다 — 요청이 전달되지 않았습니다");
      }
    }
  }

  const onRequestApproval = (poId: string) => void requestApproval(poId);

  return (
    <>
      {scenario ? (
        <DiagnosticConsole mode="mock" scenario={scenario} onRequestApproval={onRequestApproval} />
      ) : (
        <DiagnosticConsole mode="live" replay={replay} onRequestApproval={onRequestApproval} />
      )}
      {toast && <Toast>{toast}</Toast>}
    </>
  );
}
