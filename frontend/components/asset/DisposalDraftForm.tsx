"use client";

import { useState } from "react";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Button } from "@/components/ui/Button";
import {
  ApiError,
  createDecision,
  extractDetail,
  updateDecision,
  type ApiDecision,
  type DisposalDraftInput,
} from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * 처분 초안 생성/수정 폼 (P39 — D111 이 발주서에 연 경로의 마지막 확장).
 *
 * `PoForm`·`RepairForm` 과 같은 구조지만 **처분에만 있는 성질**이 하나 있다:
 * `disposal_mode`·`disposal_date` 는 **룰 입력**이라 바꾸면 판정이 달라진다. 그래서
 * 저장하면 서버가 재판정하고 `verdict`·`bundle_hash` 가 함께 바뀐다 — 그 사실을
 * 사용자에게 미리 알린다(저장 후 판정이 바뀌는 것을 "왜 바뀌었지"로 만나지 않게).
 *
 * ⛔ **예외 적용(override) 입력란이 없다** (D81). 차단 판정이 나와도 이 폼은 그것을
 *   우회할 수단을 주지 않는다 — 예외는 승인자가 **서명 화면에서** 사유와 함께 기록한다.
 * ⛔ 판정 결과를 색으로 재해석하지 않는다 — 서버가 준 값을 그대로 보여준다(D87·D64).
 */

/** 계약이 정한 값만 쓴다 — 폴백으로 하나를 고르지 않는다. */
const DISPOSAL_MODES = [
  { value: "SALE", label: "매각" },
  { value: "SCRAP", label: "폐기" },
  { value: "TRANSFER", label: "이전" },
];

export function DisposalDraftForm({
  assetId,
  initial,
  onDone,
}: {
  assetId: string;
  /** 수정 모드일 때 기존 초안. 없으면 신규 생성. */
  initial?: ApiDecision | null;
  onDone: (decision: ApiDecision) => void;
}) {
  const [mode, setMode] = useState(initial?.disposal_mode ?? "SALE");
  const [date, setDate] = useState(initial?.disposal_date ?? "");
  const [reason, setReason] = useState(initial?.reason ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const ready = reason.trim() !== "";

  async function submit() {
    if (!ready || submitting) return;
    setSubmitting(true);
    setFailure(null);
    // 빈 날짜는 키를 빼지 않고 null 로 보낸다 — 계약이 nullable 이고, 서버가 "미정"을
    // 룰 입력으로 그대로 받아 INSUFFICIENT_FACTS 판정을 낸다(D62 — 모름을 없음으로 만들지 않는다).
    const body: DisposalDraftInput = {
      asset_id: assetId,
      disposal_mode: mode,
      disposal_date: date.trim() || null,
      reason: reason.trim(),
    };
    try {
      onDone(
        initial?.decision_id
          ? await updateDecision(initial.decision_id, body)
          : await createDecision(body)
      );
    } catch (e) {
      setFailure(
        e instanceof ApiError
          ? extractDetail(e.body) || "저장하지 못했습니다."
          : "백엔드에 연결하지 못했습니다."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={sx("display:flex;flex-direction:column;gap:12px")}>
      {failure && <StatusBanner tone="error">{failure}</StatusBanner>}

      <div style={sx("display:flex;gap:10px")}>
        <Field label="처분 방식">
          <select value={mode} onChange={(e) => setMode(e.target.value)} style={inputStyle}>
            {DISPOSAL_MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="처분 예정일 (미정이면 비워 둡니다)">
          <input
            value={date}
            onChange={(e) => setDate(e.target.value)}
            placeholder="YYYY-MM-DD"
            style={inputStyle}
          />
        </Field>
      </div>

      <Field label="처분 사유 (필수)">
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="예: 노후 컨베이어 매각 — 대체 설비 도입"
          style={inputStyle}
        />
      </Field>

      <span style={sx("font:11px/1.6 'Pretendard';color:var(--dim2)")}>
        처분 방식·예정일은 판정 입력입니다 — 저장하면 시스템이 다시 판정하고 근거 번들도
        새로 만듭니다. 차단 판정이 나와도 초안은 만들어지며, 예외 적용은 승인자가 서명
        화면에서 사유와 함께 기록합니다.
      </span>

      <Button
        onClick={ready && !submitting ? () => void submit() : undefined}
        style={ready && !submitting ? "" : "opacity:.5;cursor:not-allowed"}
      >
        {submitting ? "저장 중…" : initial?.decision_id ? "수정 저장" : "처분서 초안 만들기"}
      </Button>
    </div>
  );
}

const inputStyle = sx(
  "flex:1;height:34px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
    "padding:0 11px;font:12.5px 'Pretendard';color:var(--ink);outline:none"
);

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={sx("display:flex;flex-direction:column;gap:5px;flex:1")}>
      <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>{label}</span>
      {children}
    </label>
  );
}
