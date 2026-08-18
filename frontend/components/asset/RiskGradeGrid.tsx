"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  errorBody,
  extractDetail,
  getAssets,
  getBuildingRiskGrade,
  type ApiRiskGrade,
} from "@/lib/api";
import { gradeView, type Tone } from "@/lib/riskGrade";
import { sx } from "@/lib/sx";

type CardState =
  | { status: "loading" }
  | { status: "ok"; data: ApiRiskGrade }
  | { status: "error"; message: string };

const ATTR_LABELS: Record<"fire_handling" | "hazmat_volume" | "power_capacity", string> = {
  // `data/risk_grade.py::_SCORED_ATTRS` 한글 라벨과 동일하게 하드코딩(정본은 그쪽, 여기는 사본).
  fire_handling: "화기 취급",
  hazmat_volume: "위험물 보관량",
  power_capacity: "수전용량",
};
const ATTR_KEYS = Object.keys(ATTR_LABELS) as (keyof typeof ATTR_LABELS)[];

/**
 * 건물 위험등급 그리드 (`GET /api/buildings/{id}/risk-grade`, `04 §18`, MQ-1203, S18).
 *
 * `getAssets` 로 `building_id` 고유값을 모으고, 건물별 위험등급을 병렬 조회한다(`Promise
 * .allSettled` — 개별 건물의 404 가 그리드 전체를 죽이지 않는다). `data/risk_grade.py::risk_grade`
 * 는 순수 조회+계산이라 쓰기 경로가 없다(D10) — 이 컴포넌트에 갱신 버튼을 절대 달지 않는다.
 *
 * ⛔ 이 파일에는 등급 문자열 비교·`--ok`/`--green` 색 토큰이 없다 — 표시 판단은 전부
 *   `gradeView`(`lib/riskGrade.ts`)를 거쳐 로컬 `TONE_COLOR` 맵으로만 색을 정한다(D87).
 * ⛔ 점수 숫자를 별도 진행바·랭킹으로 만들지 않는다 — 점수는 `rationale` 문장 안에서만
 *   드러난다(D64).
 */
export function RiskGradeGrid() {
  const [buildingIds, setBuildingIds] = useState<string[] | null>(null);
  const [cards, setCards] = useState<Map<string, CardState>>(new Map());
  const [listFailure, setListFailure] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getAssets("manager")
      .then(async (assets) => {
        if (!alive) return;
        const ids = Array.from(
          new Set(
            assets
              .map((a) => a.building_id)
              .filter((v): v is string => typeof v === "string" && v.length > 0)
          )
        ).sort();
        setBuildingIds(ids);
        if (ids.length === 0) return;
        setCards(new Map(ids.map((id) => [id, { status: "loading" } as CardState])));

        const results = await Promise.allSettled(
          ids.map((id) => getBuildingRiskGrade("manager", id))
        );
        if (!alive) return;

        const next = new Map<string, CardState>();
        results.forEach((r, i) => {
          const id = ids[i];
          if (r.status === "fulfilled") {
            const res = r.value;
            if (res.status === "ok") next.set(id, { status: "ok", data: res });
            else
              next.set(id, {
                status: "error",
                message: res.message ?? res.reason ?? "(사유 없음)",
              });
          } else {
            const e: unknown = r.reason;
            if (e instanceof ApiError) {
              const body = errorBody(e);
              const reason = typeof body?.reason === "string" ? body.reason : "";
              const message = extractDetail(e.body);
              next.set(id, { status: "error", message: reason ? `${reason} — ${message}` : message });
            } else {
              next.set(id, { status: "error", message: "위험등급을 불러오지 못했습니다." });
            }
          }
        });
        setCards(next);
      })
      .catch(() => {
        if (alive) {
          setBuildingIds([]);
          setListFailure("백엔드에 연결하지 못했습니다 — 자산 목록을 가져오지 못했습니다.");
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <section style={sx("display:flex;flex-direction:column;gap:11px")}>
      <div style={sx("display:flex;flex-direction:column;gap:2px")}>
        <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>건물 위험등급</span>
        <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
          화기 취급 · 위험물 보관량 · 수전용량 3속성으로 산출 — 자동 반영되지 않는 목업 산식입니다
        </span>
      </div>

      {listFailure && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:6px;padding:8px 10px;" +
              "font:11px/1.6 'Pretendard';color:var(--error-tx)"
          )}
        >
          <b>건물 목록을 불러오지 못했습니다</b>
          <br />
          {listFailure}
        </div>
      )}

      {buildingIds === null && !listFailure && (
        <div style={sx("font:12px 'Pretendard';color:var(--dim)")}>불러오는 중…</div>
      )}

      {buildingIds !== null && buildingIds.length === 0 && !listFailure && (
        <div style={sx("font:11.5px/1.6 'Pretendard';color:var(--dim)")}>
          건물이 배정된 자산이 없습니다 — 위험등급을 산출할 대상이 없습니다.
        </div>
      )}

      {buildingIds !== null && buildingIds.length > 0 && (
        <div
          style={sx(
            "display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:10px"
          )}
        >
          {buildingIds.map((id) => (
            <RiskGradeCard key={id} buildingId={id} card={cards.get(id)} />
          ))}
        </div>
      )}
    </section>
  );
}

/**
 * 톤 → 글자색. `gradeView` 가 정한 톤만 색으로 옮긴다 — 이 파일은 등급 문자열을 직접
 * 비교하지 않는다(D87). `ok`(LOW) 는 초록(`--ok-*`)이 아니라 정보색(`--blue-tx`)을 쓴다
 * (`RepairDetail.tsx` 의 `HashVerified` 선례 — L2 가 컴포넌트의 `--green`·`--ok` 색 토큰을
 * 전부 금지한다).
 */
const TONE_COLOR: Record<Tone, string> = {
  ok: "var(--blue-tx)",
  warn: "var(--orange-tx)",
  error: "var(--error-tx)",
  unknown: "var(--dim)",
};

function RiskGradeCard({ buildingId, card }: { buildingId: string; card: CardState | undefined }) {
  return (
    <div
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);" +
          "padding:11px 13px;display:flex;flex-direction:column;gap:8px"
      )}
    >
      <span style={sx("font:700 12.5px 'JetBrains Mono',monospace;color:var(--ink)")}>
        {buildingId}
      </span>

      {(!card || card.status === "loading") && (
        <span style={sx("font:11px 'Pretendard';color:var(--dim)")}>불러오는 중…</span>
      )}

      {card?.status === "error" && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:6px;padding:6px 9px;" +
              "font:10.5px/1.6 'Pretendard';color:var(--error-tx)"
          )}
        >
          {card.message}
        </div>
      )}

      {card?.status === "ok" && <RiskGradeCardBody data={card.data} />}
    </div>
  );
}

function RiskGradeCardBody({ data }: { data: ApiRiskGrade }) {
  const facts = data.facts;
  const current = gradeView(data.current_grade ?? null);
  const stored = gradeView(data.stored_grade ?? null);
  const notConsidered = Array.isArray(data.not_considered) ? data.not_considered : [];

  return (
    <div style={sx("display:flex;flex-direction:column;gap:7px")}>
      {facts && (
        <div style={sx("display:flex;flex-direction:column;gap:2px")}>
          {ATTR_KEYS.map((k) => (
            <div key={k} style={sx("display:flex;justify-content:space-between;gap:8px")}>
              <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>{ATTR_LABELS[k]}</span>
              <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--ink2)")}>
                {facts[k] ?? "미확인"}
              </span>
            </div>
          ))}
        </div>
      )}

      <div style={sx("display:flex;gap:16px")}>
        <div style={sx("display:flex;flex-direction:column;gap:1px")}>
          <span style={sx("font:10px 'Pretendard';color:var(--dim2)")}>산출 등급</span>
          <span style={sx(`font:700 12.5px 'Pretendard';color:${TONE_COLOR[current.tone]}`)}>
            {current.label}
          </span>
        </div>
        <div style={sx("display:flex;flex-direction:column;gap:1px")}>
          <span style={sx("font:10px 'Pretendard';color:var(--dim2)")}>저장된 등급</span>
          <span style={sx(`font:700 12.5px 'Pretendard';color:${TONE_COLOR[stored.tone]}`)}>
            {stored.label}
          </span>
        </div>
      </div>

      {data.rationale && (
        <p style={sx("margin:0;font:10.5px/1.5 'Pretendard';color:var(--dim)")}>{data.rationale}</p>
      )}

      {data.changed === true && (
        <div
          style={sx(
            "border:1px solid var(--saf-cite-bd);background:var(--saf-cite-bg);border-radius:6px;" +
              "padding:6px 9px;font:10.5px/1.6 'Pretendard';color:var(--orange-tx)"
          )}
        >
          산출 결과가 마지막 저장 등급과 다릅니다 — 자동 반영되지 않으며 갱신 여부는 사람이
          판단합니다.
        </div>
      )}

      {notConsidered.length > 0 && (
        <details>
          <summary style={sx("cursor:pointer;font:10.5px 'Pretendard';color:var(--dim2)")}>
            고려하지 않은 것 {notConsidered.length}건
          </summary>
          <ul
            style={sx(
              "margin:5px 0 0;padding-left:14px;font:10px/1.6 'Pretendard';color:var(--dim)"
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
            "margin:0;padding-top:6px;border-top:1px dashed var(--line2);" +
              "font:10px/1.6 'Pretendard';color:var(--dim2)"
          )}
        >
          {data.disclaimer}
        </p>
      )}
    </div>
  );
}
