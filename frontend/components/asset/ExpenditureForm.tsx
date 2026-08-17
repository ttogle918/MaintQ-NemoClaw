"use client";

import { useState } from "react";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Mono } from "@/components/ui/Mono";
import { ExpenditureResult } from "./ExpenditureCard";
import {
  ApiError,
  errorBody,
  extractDetail,
  getInventory,
  postExpenditure,
  type ApiExpenditure,
  type ApiInventoryItem,
} from "@/lib/api";
import { WORK_SCOPE_OPTIONS } from "@/lib/mappers";
import { sx } from "@/lib/sx";

/**
 * 지출 분류 독립 페이지 본체 (`classify_expenditure`, `04 §12`, MQ-1001/P37).
 *
 * `ExpenditureCard` 와 달리 **자산 컨텍스트가 없다** — 사용자가 부품을 직접 검색해 고른다.
 * `part_class` 를 직접 고르는 UI 는 만들지 않는다(도구 설명이 "추측 금지"를 명시) — 부품만
 * 고르면 백엔드가 `part_no` 로 등급을 채운다(`backend/routers/maint_value.py:135-136`).
 *
 * 결과 렌더는 `ExpenditureCard.tsx` 의 `ExpenditureResult` 를 그대로 재사용한다 — 카드와
 * 독립 페이지의 판정 문안·톤이 갈리지 않게 하기 위해서다(D87 "맵 1곳"과 같은 정신).
 *
 * **아무것도 저장하지 않는다** (D71) — `classify_expenditure` 는 무저장 판정이다.
 */
export function ExpenditureForm() {
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchFailure, setSearchFailure] = useState<string | null>(null);
  const [items, setItems] = useState<ApiInventoryItem[] | null>(null);
  const [selectedPartNo, setSelectedPartNo] = useState<string | null>(null);

  const [repairScope, setRepairScope] = useState<string | null>(null);
  /** ⛔ 0 을 기본값으로 넣지 않는다 (D62) — 빈 문자열 = 아직 입력하지 않았다 */
  const [amount, setAmount] = useState("");

  const [data, setData] = useState<ApiExpenditure | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function search() {
    const q = query.trim();
    if (!q || searching) return;
    setSearching(true);
    setSearchFailure(null);
    setItems(null);
    setSelectedPartNo(null);
    setData(null);
    setFailure(null);
    try {
      const res = await getInventory("manager", { part_name: q });
      // 200 인데 status 가 ok 가 아닌 방어 — 지어내지 않고 그대로 보여준다
      setItems(res.status === "ok" ? (res.items ?? []) : []);
    } catch (e) {
      // 검색 결과 0건은 200/빈배열이 아니라 404(ApiError) 로 온다(`data/inventory.py:81-83`) —
      // `.then()` 이 아니라 여기 `.catch()` 에서 잡는다. `InventoryDrawer.tsx` 의 `notFound`
      // 분기(200 방어)는 도달 불가능한 죽은 코드이므로 그 패턴을 베끼지 않는다.
      if (e instanceof ApiError && e.status === 404) {
        setSearchFailure("일치하는 부품이 없습니다.");
      } else if (e instanceof ApiError) {
        const body = errorBody(e);
        const reason = typeof body?.reason === "string" ? body.reason : "";
        const message = extractDetail(e.body);
        setSearchFailure(reason ? `${reason} — ${message}` : message);
      } else {
        setSearchFailure(
          "백엔드에 연결하지 못했습니다 — 조회가 실패한 것이지 부품이 없는 것이 아닙니다."
        );
      }
      setItems([]);
    } finally {
      setSearching(false);
    }
  }

  const amountNum = amount === "" ? null : Number(amount);
  const amountValid = amountNum !== null && Number.isFinite(amountNum) && amountNum > 0;
  const canSubmit = Boolean(selectedPartNo) && Boolean(repairScope) && amountValid && !submitting;

  async function submit() {
    if (!selectedPartNo || !repairScope || amountNum === null || !amountValid || submitting) {
      return;
    }
    setSubmitting(true);
    setFailure(null);
    setData(null);
    try {
      const res = await postExpenditure("manager", {
        part_no: selectedPartNo,
        repair_scope: repairScope,
        amount: amountNum,
      });
      if (res.status === "ok") setData(res);
      else setFailure(res.reason ?? "(사유 없음)");
    } catch (e) {
      // `part_class_not_set`(500)·`unknown_part`(404)·`part_class_invalid`(500) —
      // 전부 이 범용 reason+message catch 로 처리된다(`ExpenditureCard.tsx:47-56` 와 동일 패턴).
      if (e instanceof ApiError) {
        const body = errorBody(e);
        const reason = typeof body?.reason === "string" ? body.reason : "";
        const message = extractDetail(e.body);
        setFailure(reason ? `${reason} — ${message}` : message);
      } else {
        setFailure(
          "백엔드에 연결하지 못했습니다 — 조회가 실패한 것이지 판정이 없는 것이 아닙니다."
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={sx("display:flex;flex-direction:column;gap:16px")}>
      <PartSearch
        query={query}
        onQuery={setQuery}
        onSearch={() => void search()}
        searching={searching}
        failure={searchFailure}
        items={items}
        selectedPartNo={selectedPartNo}
        onSelect={setSelectedPartNo}
      />

      {selectedPartNo && (
        <ClassifyInputs
          selectedPartNo={selectedPartNo}
          repairScope={repairScope}
          onRepairScope={setRepairScope}
          amount={amount}
          onAmount={setAmount}
          amountValid={amountValid}
          canSubmit={canSubmit}
          submitting={submitting}
          onSubmit={() => void submit()}
        />
      )}

      {failure && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:6px;padding:8px 10px;" +
              "font:11.5px/1.6 'Pretendard';color:var(--error-tx)"
          )}
        >
          <b>판정 실패</b> — {failure}
        </div>
      )}

      {data && (
        <section
          style={sx(
            "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:11px 13px"
          )}
        >
          <ExpenditureResult data={data} />
        </section>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */

function PartSearch({
  query,
  onQuery,
  onSearch,
  searching,
  failure,
  items,
  selectedPartNo,
  onSelect,
}: {
  query: string;
  onQuery: (v: string) => void;
  onSearch: () => void;
  searching: boolean;
  failure: string | null;
  items: ApiInventoryItem[] | null;
  selectedPartNo: string | null;
  onSelect: (partNo: string) => void;
}) {
  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:13px 15px;" +
          "display:flex;flex-direction:column;gap:10px"
      )}
    >
      <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>부품 검색</span>
      <div style={sx("display:flex;gap:8px;align-items:center")}>
        <input
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") onSearch();
          }}
          placeholder="부품명으로 검색 (예: 냉각팬)"
          style={sx(
            "flex:1;height:34px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
              "padding:0 11px;font:12.5px 'Pretendard';color:var(--ink);outline:none"
          )}
        />
        <Button
          onClick={query.trim() && !searching ? onSearch : undefined}
          style={query.trim() && !searching ? "" : "opacity:.5;cursor:not-allowed"}
        >
          {searching ? "검색 중…" : "검색"}
        </Button>
      </div>

      {failure && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:6px;padding:8px 10px;" +
              "font:11.5px/1.6 'Pretendard';color:var(--error-tx)"
          )}
        >
          {failure}
        </div>
      )}

      {items && items.length > 0 && (
        <div style={sx("display:flex;flex-direction:column;gap:6px")}>
          {items.map((it) => {
            const on = it.part_no === selectedPartNo;
            return (
              <button
                key={it.part_no}
                onClick={() => onSelect(it.part_no)}
                aria-pressed={on}
                style={sx(
                  "text-align:left;border-radius:7px;padding:8px 11px;cursor:pointer;" +
                    (on
                      ? "border:1px solid var(--blue-br);background:var(--cite-bg)"
                      : "border:1px solid var(--line2);background:var(--raise)")
                )}
              >
                <div style={sx("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
                  <Mono size={11.5}>{it.part_no}</Mono>
                  <span style={sx("font:12px 'Pretendard';color:var(--ink)")}>{it.name}</span>
                </div>
                {it.compatible_models.length > 0 && (
                  <div style={sx("font:10.5px 'Pretendard';color:var(--dim2);margin-top:3px")}>
                    호환 기종 {it.compatible_models.join(", ")}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ClassifyInputs({
  selectedPartNo,
  repairScope,
  onRepairScope,
  amount,
  onAmount,
  amountValid,
  canSubmit,
  submitting,
  onSubmit,
}: {
  selectedPartNo: string;
  repairScope: string | null;
  onRepairScope: (v: string) => void;
  amount: string;
  onAmount: (v: string) => void;
  amountValid: boolean;
  canSubmit: boolean;
  submitting: boolean;
  onSubmit: () => void;
}) {
  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:13px 15px;" +
          "display:flex;flex-direction:column;gap:11px"
      )}
    >
      <div style={sx("display:flex;align-items:center;gap:8px")}>
        <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>선택된 부품</span>
        <Mono size={11.5}>{selectedPartNo}</Mono>
      </div>

      <div style={sx("display:flex;align-items:center;gap:12px;flex-wrap:wrap")}>
        <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>작업 범위</span>
        <select
          value={repairScope ?? ""}
          onChange={(e) => onRepairScope(e.target.value || "")}
          style={sx(
            "height:32px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
              "padding:0 8px;font:12px 'Pretendard';color:var(--ink);outline:none"
          )}
        >
          <option value="">선택 안 함</option>
          {WORK_SCOPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      <div style={sx("display:flex;align-items:center;gap:12px;flex-wrap:wrap")}>
        <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>수리비</span>
        <input
          type="number"
          value={amount}
          onChange={(e) => onAmount(e.target.value)}
          placeholder="0보다 큰 금액"
          style={sx(
            "height:32px;width:160px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
              "padding:0 10px;font:12px 'JetBrains Mono',monospace;color:var(--ink);outline:none"
          )}
        />
        {amount !== "" && !amountValid && (
          <span style={sx("font:11.5px 'Pretendard';color:var(--error-tx)")}>
            0보다 큰 금액을 입력하세요
          </span>
        )}
      </div>

      <div style={sx("display:flex;align-items:center;gap:10px")}>
        <Button
          onClick={canSubmit ? onSubmit : undefined}
          style={canSubmit ? "" : "opacity:.5;cursor:not-allowed"}
        >
          {submitting ? "판정 중…" : "지출 분류"}
        </Button>
        {!canSubmit && !submitting && (
          <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>
            작업 범위와 0보다 큰 수리비를 입력해야 판정할 수 있습니다
          </span>
        )}
      </div>
    </section>
  );
}
