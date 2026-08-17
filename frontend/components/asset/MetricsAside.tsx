"use client";

import { useEffect, useState } from "react";
import { ApiError, errorBody, extractDetail, getMetrics, type ApiMetrics } from "@/lib/api";
import { showMetric, showTrend, type Displayable } from "@/lib/maintValue";
import { sx } from "@/lib/sx";

/**
 * 보전지표 보조 패널 (`get_maintenance_metrics`, `04 §11`, MQ-914).
 *
 * **격자 대시보드가 아니다.** 값 6개를 근거 문장과 함께 세로로 쌓는다 — 점수·등급·색
 * 랭킹을 만들지 않는다(D64). OEE 는 도구가 계산도 출력도 하지 않으며, 이 화면도 만들지
 * 않는다. `null`·`insufficient_data` 는 `lib/maintValue.ts` 가 정한 대로 **"판단 근거
 * 부족"** 으로만 표기하고, 빈칸·`0`·"양호"로 접지 않는다.
 *
 * ⛔ 이 파일에는 상태 문자열 비교·색 토큰이 없다 — 표시 판단은 전부 `showMetric`·
 *   `showTrend`(둘 다 React 무의존, `lib/maintValue.ts`)가 한다.
 */
export function MetricsAside({ assetId }: { assetId: string }) {
  const [data, setData] = useState<ApiMetrics | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setFailure(null);
    setData(null);
    getMetrics("technician", assetId)
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
          setFailure("백엔드에 연결하지 못했습니다 — 지표를 불러오지 못했습니다.");
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [assetId]);

  return (
    <aside
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);" +
          "padding:12px 14px;display:flex;flex-direction:column;gap:11px;position:sticky;top:12px"
      )}
    >
      <div style={sx("display:flex;flex-direction:column;gap:2px")}>
        <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>보전지표 (보조)</span>
        <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
          ⚠ 대시보드가 아닙니다 — 점수·등급으로 줄 세우지 않습니다
        </span>
      </div>

      {loading && <div style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>불러오는 중…</div>}

      {failure && !loading && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:6px;padding:8px 10px;" +
              "font:11px/1.6 'Pretendard';color:var(--error-tx)"
          )}
        >
          <b>지표를 불러오지 못했습니다</b>
          <br />
          {failure}
        </div>
      )}

      {data && !loading && <MetricsBody data={data} />}
    </aside>
  );
}

function MetricsBody({ data }: { data: ApiMetrics }) {
  const excluded = Array.isArray(data.excluded) ? data.excluded : [];
  const notConsidered = Array.isArray(data.not_considered) ? data.not_considered : [];

  const mtbf = showMetric(data.mtbf_days ?? null, "일");
  const trend = showTrend(data.mtbf_trend ?? null);
  const mttr = showMetric(data.mttr_hours ?? null, "시간");
  // 비율 계열은 %로 보여준다 — null 판단(`showMetric`)은 그대로 두고 값만 100배한다
  const avail = showMetric(toPercent(data.availability), "%");
  const planned = showMetric(toPercent(data.planned_ratio), "%");
  const repairRatio = showMetric(toPercent(data.cumulative_repair_ratio), "%");

  return (
    <div style={sx("display:flex;flex-direction:column;gap:10px")}>
      <MetricRow label="MTBF (평균 고장 간격)" value={mtbf} basis="달력 기준(D70) — 가동시간이 아닙니다" />
      <MetricRow label="MTBF 추세" value={trend} basis="최근 12개월 대 직전 12개월 고정 비교" />
      <MetricRow label="MTTR (평균 수리시간)" value={mttr} basis="서명된 수리 레코드만 집계" />
      <MetricRow label="가용도" value={avail} basis="MTBF / (MTBF + MTTR/24) — 다른 설비와 비교 지표 아님" />
      <MetricRow label="예방보전 비율" value={planned} basis="계획(PLANNED) / 전체 — 서명분만" />
      <MetricRow label="누적 수리비 비율" value={repairRatio} basis="누적 수리비 / 취득원가" />

      {typeof data.n_repairs_signed === "number" && (
        <div style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
          서명된 수리 {data.n_repairs_signed}건 · 미서명 {data.n_repairs_unsigned ?? 0}건 — 미서명은
          위 지표 계산에서 전부 제외됩니다
        </div>
      )}

      {excluded.length > 0 && (
        <details>
          <summary style={sx("cursor:pointer;font:10.5px 'Pretendard';color:var(--dim2)")}>
            계산에서 뺀 것 {excluded.length}건
          </summary>
          <ul style={sx("margin:5px 0 0;padding-left:15px;font:10.5px/1.6 'Pretendard';color:var(--dim)")}>
            {excluded.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </details>
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
        <p
          style={sx(
            "margin:0;padding-top:8px;border-top:1px dashed var(--line2);" +
              "font:10.5px/1.6 'Pretendard';color:var(--dim2)"
          )}
        >
          {data.disclaimer}
        </p>
      )}
    </div>
  );
}

function toPercent(v: number | null | undefined): number | null {
  return typeof v === "number" ? v * 100 : null;
}

/** `kind` 별 글자색만 정한다 — `insufficient`/`unknown` 도 성공색(초록)이 아니다(D62·D87). */
const KIND_COLOR: Record<Displayable["kind"], string> = {
  value: "var(--ink)",
  insufficient: "var(--orange-tx)",
  unknown: "var(--dim)",
};

function MetricRow({ label, value, basis }: { label: string; value: Displayable; basis: string }) {
  return (
    <div style={sx("display:flex;flex-direction:column;gap:2px")}>
      <div style={sx("display:flex;align-items:baseline;gap:8px")}>
        <span style={sx("font:11.5px 'Pretendard';color:var(--dim2);flex:1")}>{label}</span>
        <span style={sx(`font:700 12.5px 'JetBrains Mono',monospace;color:${KIND_COLOR[value.kind]}`)}>
          {value.text}
        </span>
      </div>
      <span style={sx("font:10px/1.5 'Pretendard';color:var(--dim2)")}>{basis}</span>
    </div>
  );
}
