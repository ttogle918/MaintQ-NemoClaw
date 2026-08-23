"use client";

import { useEffect, useState } from "react";
import { ApiError, errorBody, extractDetail, getA2aHistory, type ApiA2aHistoryItem } from "@/lib/api";
import { a2aStatusTone, type Tone } from "@/lib/a2a";
import { sx } from "@/lib/sx";

/**
 * 담보대출 상담 이력 패널 (`GET /api/a2a/history?skill=assess-loan`, D114, MQ-1609, S8/S4).
 *
 * 건물별 N+1 조회 대신 `assess-loan` 스킬로 **한 번에** 조회한다 — 건물 개수만큼 왕복하지 않는다.
 * `request`(FinAllQ 로 보낸 원 요청)에서 `collateral_building_id`·`loan_amount` 를 꺼내 표시하되,
 * 필드가 없거나 `request` 자체가 `null` 이면 해당 셀만 "—" 로 둔다 — 지어내지 않는다(D87).
 *
 * ⛔ 점수·금액을 별도 랭킹·진행바로 가공하지 않는다 — `RiskGradeGrid` 선례와 같은 톤으로 단순
 *   테이블만 그린다(D64).
 */
export function LoanAssessmentHistory() {
  const [items, setItems] = useState<ApiA2aHistoryItem[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setFailure(null);
    setItems(null);
    getA2aHistory("manager", { skill: "assess-loan", limit: 20 })
      .then((res) => {
        if (!alive) return;
        setItems(Array.isArray(res.items) ? res.items : []);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError) {
          const body = errorBody(e);
          const reason = typeof body?.reason === "string" ? body.reason : "";
          const message = extractDetail(e.body);
          setFailure(reason ? `${reason} — ${message}` : message);
        } else {
          setFailure("백엔드에 연결하지 못했습니다 — 상담 이력을 불러오지 못했습니다.");
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);" +
          "padding:12px 14px;display:flex;flex-direction:column;gap:10px"
      )}
    >
      <div style={sx("display:flex;flex-direction:column;gap:2px")}>
        <span style={sx("font:700 12.5px 'Pretendard';color:var(--ink)")}>
          담보대출 상담 이력
        </span>
        <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
          FinAllQ · assess-loan — 최근 20건
        </span>
      </div>

      {failure && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:6px;padding:8px 10px;" +
              "font:11px/1.6 'Pretendard';color:var(--error-tx)"
          )}
        >
          <b>상담 이력을 불러오지 못했습니다</b>
          <br />
          {failure}
        </div>
      )}

      {items === null && !failure && (
        <div style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>불러오는 중…</div>
      )}

      {items !== null && !failure && items.length === 0 && (
        <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--dim)")}>
          아직 상담 이력이 없습니다.
        </div>
      )}

      {items !== null && !failure && items.length > 0 && <LoanHistoryTable items={items} />}
    </section>
  );
}

const TONE_COLOR: Record<Tone, string> = {
  ok: "var(--blue-tx)",
  warn: "var(--orange-tx)",
  error: "var(--error-tx)",
  unknown: "var(--dim)",
};

function cellText(v: unknown): string {
  return typeof v === "string" || typeof v === "number" ? String(v) : "—";
}

function LoanHistoryTable({ items }: { items: ApiA2aHistoryItem[] }) {
  return (
    <table style={sx("border-collapse:collapse;width:100%")}>
      <thead>
        <tr>
          {["건물", "대출 희망액", "상태", "일시"].map((h) => (
            <th
              key={h}
              style={sx(
                "text-align:left;padding:5px 8px;border-bottom:1px solid var(--line2);" +
                  "font:700 10.5px 'Pretendard';color:var(--dim2)"
              )}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <LoanHistoryRow key={item.request_chain_id} item={item} />
        ))}
      </tbody>
    </table>
  );
}

function LoanHistoryRow({ item }: { item: ApiA2aHistoryItem }) {
  const req = item.request;
  const buildingId = req ? cellText(req["collateral_building_id"]) : "—";
  const loanAmountRaw = req ? req["loan_amount"] : undefined;
  const loanAmount =
    typeof loanAmountRaw === "number" ? `${loanAmountRaw.toLocaleString()}원` : cellText(loanAmountRaw);
  const tone = a2aStatusTone(item.status);

  return (
    <tr>
      <td
        style={sx(
          "padding:6px 8px;border-bottom:1px solid var(--line2);" +
            "font:11.5px 'JetBrains Mono',monospace;color:var(--ink)"
        )}
      >
        {buildingId}
      </td>
      <td
        style={sx(
          "padding:6px 8px;border-bottom:1px solid var(--line2);" +
            "font:11.5px 'JetBrains Mono',monospace;color:var(--ink2)"
        )}
      >
        {loanAmount}
      </td>
      <td style={sx("padding:6px 8px;border-bottom:1px solid var(--line2)")}>
        <span style={sx(`font:700 11px 'Pretendard';color:${TONE_COLOR[tone]}`)}>
          {item.status ?? "unknown"}
        </span>
      </td>
      <td
        style={sx(
          "padding:6px 8px;border-bottom:1px solid var(--line2);" +
            "font:10.5px 'Pretendard';color:var(--dim2)"
        )}
      >
        {item.ts}
      </td>
    </tr>
  );
}
