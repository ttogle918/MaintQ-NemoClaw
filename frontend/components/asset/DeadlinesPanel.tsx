"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  errorBody,
  extractDetail,
  getDeadlines,
  type ApiDeadlineItem,
  type ApiDeadlines,
} from "@/lib/api";
import { deadlineStateView, deadlineTypeLabel, type Tone } from "@/lib/deadlines";
import { sx } from "@/lib/sx";

const WINDOW_PRESETS = [180, 365, 500, 730] as const;

/**
 * 법정 기한 추적 패널 (`GET /api/deadlines`, `04 §17`, MQ-1203, S9).
 *
 * `data/deadlines.py::track_deadlines` 가 준 원 어휘(`type`·`state`)는 `lib/deadlines.ts` 를
 * 거쳐서만 표시한다 — 이 파일에는 상태 문자열 비교·색 토큰 리터럴이 없다(D87). 0건은 실패가
 * 아니라 "이 범위엔 없다"는 사실이므로, 성공색·체크마크 없이 중립 톤으로 명시한다(D62).
 *
 * ⛔ 자유 숫자 입력은 없다 — 프리셋 4개(180·365·500·730)뿐이다(스코프 최소화).
 */
export function DeadlinesPanel({ assetId }: { assetId?: string }) {
  const [windowDays, setWindowDays] = useState<number>(180);
  const [data, setData] = useState<ApiDeadlines | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setFailure(null);
    setData(null);
    getDeadlines("manager", { assetId, windowDays })
      .then((res) => {
        if (!alive) return;
        if (res.status === "ok") setData(res);
        else setFailure(res.message ?? res.reason ?? "(사유 없음)");
      })
      .catch((e: unknown) => {
        if (!alive) return;
        if (e instanceof ApiError) {
          const body = errorBody(e);
          const reason = typeof body?.reason === "string" ? body.reason : "";
          const message = extractDetail(e.body);
          setFailure(reason ? `${reason} — ${message}` : message);
        } else {
          setFailure("백엔드에 연결하지 못했습니다 — 법정 기한을 불러오지 못했습니다.");
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [assetId, windowDays]);

  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);" +
          "padding:12px 14px;display:flex;flex-direction:column;gap:11px"
      )}
    >
      <div style={sx("display:flex;flex-direction:column;gap:2px")}>
        <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>법정 기한 추적</span>
        <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
          투자세액공제 사후관리 · 안전검사 — 선택한 범위 내 도래 기한만 보여줍니다
        </span>
      </div>

      <div style={sx("display:flex;gap:6px;flex-wrap:wrap")}>
        {WINDOW_PRESETS.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setWindowDays(d)}
            style={sx(
              "border-radius:14px;padding:4px 11px;font:12px 'Pretendard';cursor:pointer;" +
                (d === windowDays
                  ? "border:1px solid var(--cite-bd);background:var(--cite-bg);color:var(--blue-tx)"
                  : "border:1px solid var(--line2);background:var(--raise);color:var(--ink2)")
            )}
          >
            {d}일
          </button>
        ))}
      </div>

      {loading && <div style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>불러오는 중…</div>}

      {failure && !loading && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:6px;padding:8px 10px;" +
              "font:11px/1.6 'Pretendard';color:var(--error-tx)"
          )}
        >
          <b>법정 기한을 불러오지 못했습니다</b>
          <br />
          {failure}
        </div>
      )}

      {data && !loading && <DeadlinesBody data={data} windowDays={windowDays} />}
    </section>
  );
}

function DeadlinesBody({ data, windowDays }: { data: ApiDeadlines; windowDays: number }) {
  const items = Array.isArray(data.items) ? data.items : [];
  const notConsidered = Array.isArray(data.not_considered) ? data.not_considered : [];

  return (
    <div style={sx("display:flex;flex-direction:column;gap:10px")}>
      {items.length === 0 ? (
        <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--dim)")}>
          선택한 범위({windowDays}일) 내 임박한 법정 기한이 없습니다. 범위를 넓혀 확인할 수
          있습니다.
        </div>
      ) : (
        items.map((item, i) => (
          <DeadlineRow key={`${item.asset_id}-${item.type}-${i}`} item={item} />
        ))
      )}

      {notConsidered.length > 0 && (
        <details>
          <summary style={sx("cursor:pointer;font:10.5px 'Pretendard';color:var(--dim2)")}>
            고려하지 않은 것 {notConsidered.length}건
          </summary>
          <ul
            style={sx(
              "margin:5px 0 0;padding-left:15px;font:10.5px/1.6 'Pretendard';color:var(--dim)"
            )}
          >
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

/**
 * 톤 → 글자색. `deadlineStateView` 가 정한 톤만 색으로 옮긴다 — 이 파일은 `state` 문자열을
 * 직접 비교하지 않는다(D87). `ok` 톤은 `deadlineStateView` 가 현재 만들어 내지 않지만
 * `Record<Tone,…>` 는 total 이어야 하므로 항목을 둔다 — 초록(`--ok-*`)이 아니라 정보색
 * (`--blue-tx`)을 쓴다(`RepairDetail.tsx` 의 `HashVerified` 선례와 동일한 이유, D87 — L2 가
 * 컴포넌트의 `--green`·`--ok` 색 토큰을 전부 금지한다).
 */
const TONE_COLOR: Record<Tone, string> = {
  ok: "var(--blue-tx)",
  warn: "var(--orange-tx)",
  error: "var(--error-tx)",
  unknown: "var(--dim)",
};

function DeadlineRow({ item }: { item: ApiDeadlineItem }) {
  const state = deadlineStateView(item.state);
  const overdue = item.days_remaining < 0;
  return (
    <div
      style={sx(
        "display:flex;flex-direction:column;gap:3px;border-bottom:1px solid var(--line2);" +
          "padding-bottom:8px"
      )}
    >
      <div style={sx("display:flex;align-items:baseline;gap:8px;flex-wrap:wrap")}>
        <span style={sx("font:700 12px 'JetBrains Mono',monospace;color:var(--ink)")}>
          {item.asset_id}
        </span>
        <span style={sx("font:11.5px 'Pretendard';color:var(--ink2)")}>
          {deadlineTypeLabel(item.type)}
        </span>
        <div style={sx("flex:1")} />
        <span style={sx(`font:700 11.5px 'Pretendard';color:${TONE_COLOR[state.tone]}`)}>
          {state.label}
        </span>
      </div>
      <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
        기한 {item.due_date} · {overdue ? "경과" : "잔여"} {Math.abs(item.days_remaining)}일
      </span>
      <span style={sx("font:11px/1.5 'Pretendard';color:var(--dim)")}>{item.message}</span>
    </div>
  );
}
