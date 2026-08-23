"use client";

import { useEffect, useState } from "react";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  errorBody,
  extractDetail,
  getInventory,
  getPartQuotes,
  type ApiInventoryItem,
  type ApiPo,
  type ApiQuote,
  type CreatePoBody,
} from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * 발주 초안 생성/수정 공용 폼 (D111, P39 축소판 — 발주서만).
 *
 * `ExpenditureForm.tsx`(부품 검색 → 입력 → 제출 → 실패 표시)와 같은 구조를 따른다.
 * 부품 검색 로직을 그 컴포넌트와 공유하지 않는다 — 이 저장소의 화면들은 각자 자기
 * 부품 검색 wiring 을 갖는다(UI wiring 이지 D73·D101 이 막는 "산출 로직"이 아니다).
 *
 * `model`·`error_code`·`evidence` 는 이 폼에 없다 — 그건 채팅 진단 컨텍스트에서만
 * 의미가 있는 필드라(어떤 에러코드를 보고 판단했는지), 화면에서 맨 처음부터 직접
 * 만드는 발주에는 자연히 없다(YAGNI, 2026-08-21 설계에서 의도적으로 뺀 범위).
 */
export function PoForm({
  mode,
  lockedPart,
  initial,
  onSubmit,
  onSuccess,
}: {
  mode: "create" | "edit";
  lockedPart?: { part_no: string; part_name: string };
  initial?: { qty?: number; supplier_id?: string; reason?: string; urgency?: "urgent" | "normal" };
  onSubmit: (body: CreatePoBody) => Promise<ApiPo>;
  onSuccess: (po: ApiPo) => void;
}) {
  // ── 부품 선택 (create 모드에서만 검색, edit 모드는 lockedPart 로 고정) ──
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchFailure, setSearchFailure] = useState<string | null>(null);
  const [items, setItems] = useState<ApiInventoryItem[] | null>(null);
  const [pickedPart, setPickedPart] = useState<{ part_no: string; part_name: string } | null>(
    lockedPart ?? null
  );

  async function search() {
    const q = query.trim();
    if (!q || searching) return;
    setSearching(true);
    setSearchFailure(null);
    setItems(null);
    try {
      const res = await getInventory("technician", { part_name: q });
      setItems(res.status === "ok" ? (res.items ?? []) : []);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setSearchFailure("일치하는 부품이 없습니다.");
      } else if (e instanceof ApiError) {
        setSearchFailure(extractDetail(e.body));
      } else {
        setSearchFailure("백엔드에 연결하지 못했습니다.");
      }
      setItems([]);
    } finally {
      setSearching(false);
    }
  }

  // ── 공급사 견적 (부품이 정해지면 조회) ──
  const [quotes, setQuotes] = useState<ApiQuote[] | null>(null);
  const [quotesFailure, setQuotesFailure] = useState<string | null>(null);
  const [supplierId, setSupplierId] = useState<string | null>(initial?.supplier_id ?? null);

  useEffect(() => {
    if (!pickedPart) return;
    let alive = true;
    setQuotes(null);
    setQuotesFailure(null);
    getPartQuotes("technician", pickedPart.part_no)
      .then((res) => {
        if (!alive) return;
        setQuotes(res.quotes);
        if (res.quotes.length === 0) setQuotesFailure("이 부품을 공급하는 업체가 없습니다.");
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setQuotes([]);
        setQuotesFailure(
          e instanceof ApiError ? extractDetail(e.body) : "견적을 불러오지 못했습니다."
        );
      });
    return () => {
      alive = false;
    };
  }, [pickedPart]);

  // ── 나머지 필드 ──
  const [qty, setQty] = useState(initial?.qty ? String(initial.qty) : "");
  const [reason, setReason] = useState(initial?.reason ?? "");
  const [urgency, setUrgency] = useState<"urgent" | "normal">(initial?.urgency ?? "normal");

  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const qtyNum = qty === "" ? null : Number(qty);
  const qtyValid = qtyNum !== null && Number.isInteger(qtyNum) && qtyNum >= 1;
  const canSubmit =
    Boolean(pickedPart) && Boolean(supplierId) && qtyValid && reason.trim().length > 0 && !submitting;

  async function submit() {
    if (!pickedPart || !supplierId || qtyNum === null || !qtyValid || !reason.trim() || submitting) {
      return;
    }
    setSubmitting(true);
    setFailure(null);
    try {
      const po = await onSubmit({
        part_no: pickedPart.part_no,
        qty: qtyNum,
        supplier_id: supplierId,
        reason: reason.trim(),
        urgency,
      });
      onSuccess(po);
    } catch (e) {
      if (e instanceof ApiError) {
        const body = errorBody(e);
        const reason2 = typeof body?.reason === "string" ? body.reason : "";
        const message = extractDetail(e.body);
        setFailure(reason2 ? `${reason2} — ${message}` : message);
      } else {
        setFailure("백엔드에 연결하지 못했습니다 — 초안이 만들어지지 않았습니다.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={sx("display:flex;flex-direction:column;gap:16px")}>
      {!lockedPart && (
        <section
          style={sx(
            "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:13px 15px;" +
              "display:flex;flex-direction:column;gap:10px"
          )}
        >
          <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>부품 선택</span>
          <div style={sx("display:flex;gap:8px;align-items:center")}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void search();
              }}
              placeholder="부품명으로 검색 (예: 냉각팬)"
              style={sx(
                "flex:1;height:34px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
                  "padding:0 11px;font:12.5px 'Pretendard';color:var(--ink);outline:none"
              )}
            />
            <Button
              onClick={query.trim() && !searching ? () => void search() : undefined}
              style={query.trim() && !searching ? "" : "opacity:.5;cursor:not-allowed"}
            >
              {searching ? "검색 중…" : "검색"}
            </Button>
          </div>

          {searchFailure && <StatusBanner tone="error">{searchFailure}</StatusBanner>}

          {items && items.length > 0 && (
            <div style={sx("display:flex;flex-direction:column;gap:6px")}>
              {items.map((it) => {
                const on = it.part_no === pickedPart?.part_no;
                return (
                  <button
                    key={it.part_no}
                    onClick={() => {
                      setPickedPart({ part_no: it.part_no, part_name: it.name });
                      setSupplierId(null);
                    }}
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
                  </button>
                );
              })}
            </div>
          )}
        </section>
      )}

      {pickedPart && (
        <section
          style={sx(
            "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:13px 15px;" +
              "display:flex;flex-direction:column;gap:11px"
          )}
        >
          <div style={sx("display:flex;align-items:center;gap:8px")}>
            <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>선택된 부품</span>
            <Mono size={11.5}>{pickedPart.part_no}</Mono>
            <span style={sx("font:12px 'Pretendard';color:var(--ink)")}>{pickedPart.part_name}</span>
          </div>

          <div style={sx("display:flex;flex-direction:column;gap:6px")}>
            <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>공급사</span>
            {quotesFailure && <StatusBanner tone="error">{quotesFailure}</StatusBanner>}
            {quotes === null && !quotesFailure && (
              <span style={sx("font:12px 'Pretendard';color:var(--dim)")}>견적 불러오는 중…</span>
            )}
            {quotes?.map((q) => {
              const on = q.supplier_id === supplierId;
              return (
                <button
                  key={q.supplier_id}
                  onClick={() => setSupplierId(q.supplier_id)}
                  aria-pressed={on}
                  style={sx(
                    "text-align:left;border-radius:7px;padding:8px 11px;cursor:pointer;" +
                      (on
                        ? "border:1px solid var(--blue-br);background:var(--cite-bg)"
                        : "border:1px solid var(--line2);background:var(--raise)")
                  )}
                >
                  <div style={sx("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
                    <Mono size={11.5}>{q.supplier_id}</Mono>
                    <span style={sx("font:12px 'Pretendard';color:var(--ink)")}>{q.name}</span>
                    <span style={sx("font:11.5px 'JetBrains Mono',monospace;color:var(--dim)")}>
                      {q.unit_price.toLocaleString()}원 · 리드타임 {q.lead_days}일 · MOQ {q.moq}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          <div style={sx("display:flex;align-items:center;gap:12px;flex-wrap:wrap")}>
            <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>수량</span>
            <input
              type="number"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              placeholder="1 이상"
              style={sx(
                "height:32px;width:110px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
                  "padding:0 10px;font:12px 'JetBrains Mono',monospace;color:var(--ink);outline:none"
              )}
            />
            {qty !== "" && !qtyValid && (
              <span style={sx("font:11.5px 'Pretendard';color:var(--error-tx)")}>
                1 이상의 정수를 입력하세요
              </span>
            )}

            <span style={sx("font:700 12px 'Pretendard';color:var(--ink2);margin-left:8px")}>긴급도</span>
            <select
              value={urgency}
              onChange={(e) => setUrgency(e.target.value as "urgent" | "normal")}
              style={sx(
                "height:32px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
                  "padding:0 8px;font:12px 'Pretendard';color:var(--ink);outline:none"
              )}
            >
              <option value="normal">보통</option>
              <option value="urgent">긴급</option>
            </select>
          </div>

          <div style={sx("display:flex;flex-direction:column;gap:6px")}>
            <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>발주 사유</span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="예: 냉각팬 소음·진동으로 인한 예방 교체, 재고 부족"
              rows={2}
              style={sx(
                "border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
                  "padding:8px 10px;font:12px/1.5 'Pretendard';color:var(--ink);outline:none;resize:vertical"
              )}
            />
          </div>

          <div style={sx("display:flex;align-items:center;gap:10px")}>
            <Button
              onClick={canSubmit ? () => void submit() : undefined}
              style={canSubmit ? "" : "opacity:.5;cursor:not-allowed"}
            >
              {submitting
                ? mode === "create"
                  ? "생성 중…"
                  : "저장 중…"
                : mode === "create"
                  ? "발주 초안 생성"
                  : "수정 저장"}
            </Button>
            {!canSubmit && !submitting && (
              <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>
                공급사·수량(1 이상)·사유를 모두 입력해야 {mode === "create" ? "생성" : "저장"}할 수 있습니다
              </span>
            )}
          </div>
        </section>
      )}

      {failure && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:6px;padding:8px 10px;" +
              "font:11.5px/1.6 'Pretendard';color:var(--error-tx)"
          )}
        >
          <b>{mode === "create" ? "생성 실패" : "저장 실패"}</b> — {failure}
        </div>
      )}
    </div>
  );
}
