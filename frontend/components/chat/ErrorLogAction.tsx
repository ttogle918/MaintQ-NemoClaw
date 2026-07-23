"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Mono } from "@/components/ui/Mono";
import { sx } from "@/lib/sx";

/**
 * 에러 발생 이력 기록 — `POST /api/equipment/{id}/errors` (D29 · A7).
 *
 * 에이전트 루프가 자동으로 부르지 않는다. 채팅 진입만으로 기록하면
 * `get_error_history` 의 count 가 실제 고장 횟수가 아니라 **질문 횟수**가 되어,
 * 같은 에러를 세 번 물어본 것만으로 repeated=true(근본원인 모드)가 잘못 켜진다.
 * 그래서 정비사가 명시적으로 누르는 액션으로 둔다.
 */
export function ErrorLogAction({
  equipmentId,
  code,
  recordedAt,
}: {
  equipmentId: string;
  code: string;
  /** 이미 기록된 건이면 기록 시각 */
  recordedAt?: string;
}) {
  const [saved, setSaved] = useState<string | null>(recordedAt ?? null);

  return (
    <div
      style={sx(
        "align-self:flex-start;max-width:88%;display:flex;align-items:center;gap:10px;" +
          "border:1px dashed var(--line2);border-radius:7px;background:transparent;padding:9px 12px"
      )}
    >
      {saved ? (
        <>
          <span
            style={sx(
              "width:20px;height:20px;flex-shrink:0;border-radius:5px;background:var(--ok-bg);" +
                "border:1px solid var(--ok-bd);display:flex;align-items:center;justify-content:center;" +
                "font:700 11px 'JetBrains Mono';color:var(--ok-tx)"
            )}
          >
            ✓
          </span>
          <span style={sx("font:12px/1.5 'Pretendard';color:var(--ink2)")}>
            고장 이력에 기록됨 — <Mono size={11}>{equipmentId}</Mono> · <Mono size={11}>{code}</Mono>{" "}
            <span style={sx("color:var(--dim2)")}>{saved}</span>
          </span>
        </>
      ) : (
        <>
          <Button size="sm" variant="outline" onClick={() => setSaved("방금")}>
            🗓 이 고장 이력에 기록
          </Button>
          <span style={sx("font:11px/1.5 'Pretendard';color:var(--dim2)")}>
            기록해야 반복 고장 감지(30일 3회)에 반영됩니다 — 질문만으로는 집계되지 않습니다
          </span>
        </>
      )}
    </div>
  );
}
