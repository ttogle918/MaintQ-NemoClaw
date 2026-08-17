"use client";

import { useEffect, useState } from "react";
import { Mono } from "@/components/ui/Mono";
import { ApiError, errorBody, extractDetail, postExpenditure, type ApiExpenditure } from "@/lib/api";
import { expenditureEvidenceView, expenditureVerdictView } from "@/lib/mappers";
import { sx } from "@/lib/sx";

/**
 * 지출 분류 작은 카드 (`classify_expenditure`, `04 §12`, MQ-914).
 *
 * **입력 없이 렌더된다.** `RepairValuePanel` 이 이미 3지 판단 응답에서 받은 등급·범위·금액을
 * 그대로 넘겨준다 — 도구 설명이 요구하는 "등급은 추측하지 말고 먼저 확인해 넣을 것"이
 * 구조적으로 충족된다(등급을 이 카드가 다시 묻거나 추측하지 않는다).
 *
 * ⛔ 판정 색·문구는 전부 `lib/mappers.expenditureVerdictView` 가 정한다 — 이 파일은 판정
 *   원문 값을 직접 비교하거나 리터럴로 들고 있지 않는다(D87). 경계 사안이라 단정하지 않은
 *   상태는 경고색이되 에러가 아니다 — 실패 배너로 바꿔치기하지 않는다.
 */
export function ExpenditureCard({
  partClass,
  repairScope,
  amount,
}: {
  partClass: string | null | undefined;
  repairScope: string | null | undefined;
  amount: number | null | undefined;
}) {
  const [data, setData] = useState<ApiExpenditure | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const ready = Boolean(partClass) && Boolean(repairScope) && typeof amount === "number" && amount > 0;

  useEffect(() => {
    if (!ready || !partClass || !repairScope || typeof amount !== "number") return;
    let alive = true;
    setLoading(true);
    setFailure(null);
    setData(null);
    postExpenditure("technician", { part_class: partClass, repair_scope: repairScope, amount })
      .then((res) => {
        if (!alive) return;
        if (res.status === "ok") setData(res);
        else setFailure(res.reason ?? "(사유 없음)");
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError) {
          const body = errorBody(e);
          const reason = typeof body?.reason === "string" ? body.reason : "";
          const message = extractDetail(e.body);
          setFailure(reason ? `${reason} — ${message}` : message);
        } else {
          setFailure("백엔드에 연결하지 못했습니다 — 조회가 실패한 것이지 판정이 없는 것이 아닙니다.");
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, partClass, repairScope, amount]);

  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:11px 13px;" +
          "display:flex;flex-direction:column;gap:8px"
      )}
    >
      <div style={sx("display:flex;align-items:baseline;gap:8px;flex-wrap:wrap")}>
        <span style={sx("font:700 11.5px 'Pretendard';color:var(--ink2)")}>지출 성격 분류</span>
        <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
          자본적 / 수익적 — 세무·회계 참고용, 신고를 대신하지 않습니다
        </span>
      </div>

      {!ready && (
        <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--dim)")}>
          등급 · 범위 · 수리비가 아직 확정되지 않았습니다 — 판단할 수 없습니다.
        </div>
      )}

      {loading && <div style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>판정 중…</div>}

      {failure && !loading && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:6px;padding:8px 10px;" +
              "font:11.5px/1.6 'Pretendard';color:var(--error-tx)"
          )}
        >
          <b>판정 실패</b> — {failure}
        </div>
      )}

      {data && !loading && <ExpenditureResult data={data} />}
    </section>
  );
}

function ExpenditureResult({ data }: { data: ApiExpenditure }) {
  const view = expenditureVerdictView(data.verdict);
  const evidence = expenditureEvidenceView(data.evidence_completeness);
  const lawRefs = Array.isArray(data.citations) ? data.citations : [];
  const notConsidered = Array.isArray(data.not_considered) ? data.not_considered : [];
  const materiality =
    data.materiality && typeof data.materiality === "object" ? data.materiality : null;

  return (
    <div style={sx("display:flex;flex-direction:column;gap:8px")}>
      <div style={sx(`${view.skin};border-radius:7px;padding:9px 11px;display:flex;flex-direction:column;gap:4px`)}>
        <div style={sx("display:flex;align-items:center;gap:8px")}>
          <span style={sx("font:700 12.5px 'Pretendard'")}>{view.known ? view.text : `⚠ ${view.text}`}</span>
          {data.requires_expert_review && (
            <span
              style={sx(
                "font:700 9px 'JetBrains Mono',monospace;border:1px dashed currentColor;" +
                  "border-radius:3px;padding:2px 6px"
              )}
            >
              전문가 검토 필요
            </span>
          )}
        </div>
        <span style={sx("font:11px/1.6 'Pretendard'")}>{view.note}</span>
      </div>

      {data.reasoning && (
        <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--ink2)")}>{data.reasoning}</div>
      )}

      {lawRefs.length > 0 && (
        <div style={sx("display:flex;gap:5px;flex-wrap:wrap")}>
          {lawRefs.map((c) => (
            <span
              key={c}
              style={sx(
                "font:500 10px 'JetBrains Mono',monospace;border:1px solid var(--cite-bd);" +
                  "border-radius:4px;padding:2px 6px;color:var(--blue-tx);background:var(--cite-bg)"
              )}
            >
              ▤ {c}
            </span>
          ))}
        </div>
      )}

      <div style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
        근거 수집 {evidence.known ? "" : "⚠ "}
        {evidence.text}
      </div>

      {materiality && (
        <div style={sx("font:10.5px/1.6 'JetBrains Mono',monospace;color:var(--dim)")}>
          중요도 <Mono size={10.5}>{String((materiality as Record<string, unknown>).state ?? "미상")}</Mono>
          {typeof (materiality as Record<string, unknown>).ratio === "number" && (
            <> · 비율 {String((materiality as Record<string, unknown>).ratio)}</>
          )}
        </div>
      )}

      {notConsidered.length > 0 && (
        <details>
          <summary style={sx("cursor:pointer;font:10.5px 'Pretendard';color:var(--dim2)")}>
            고려하지 않은 것 {notConsidered.length}건
          </summary>
          <ul style={sx("margin:5px 0 0;padding-left:15px;font:10.5px/1.6 'Pretendard';color:var(--dim)")}>
            {notConsidered.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </details>
      )}

      {data.disclaimer && (
        <p style={sx("margin:0;font:10px/1.6 'Pretendard';color:var(--dim2)")}>{data.disclaimer}</p>
      )}
    </div>
  );
}
