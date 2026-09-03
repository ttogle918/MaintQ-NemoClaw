"use client";

import { useState } from "react";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Button } from "@/components/ui/Button";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  errorBody,
  extractDetail,
  getInventory,
  type ApiInventoryItem,
  type ApiRepair,
  type RepairDraftInput,
} from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * 수리 증빙 초안 생성/수정 공용 폼 (P39 — D111 이 발주서에 연 경로의 확장).
 *
 * `PoForm.tsx` 와 같은 구조다(부품 검색 → 입력 → 제출 → 실패 표시). 발주서와 다른 점은
 * **부품이 여러 건**이라는 것 하나다 — 수리는 한 번에 여러 부품을 갈고, 계약이
 * `parts` 를 1건 이상의 배열로 요구한다(`data/repair_record.validate_parts`).
 *
 * ⛔ **`expenditure_class` 는 이 폼에 없다.** 서버가 산출한다(D101) — D31 이 `unit_price`
 *   를 발주 폼에서 뺀 것과 같은 이유다. 입력으로 받으면 사용자가 서버 계산을 덮어쓸 수
 *   있고, 그러면 그 계산의 존재 이유가 사라진다. 생성 응답에 실려 오므로 **결과로만**
 *   보여준다.
 * ⛔ 서명 필드(`verified_by`·`signed_at`·`record_hash`)도 없다 — 사람이 서명으로 채운다.
 */

const WORK_TYPES = [
  { value: "UNPLANNED", label: "비계획 (고장 대응)" },
  { value: "PLANNED", label: "계획 (예방 정비)" },
];

/** 계약이 정한 값만 쓴다 — 폴백으로 하나를 고르지 않는다(enum 밖은 서버가 422). */
const REPAIR_SCOPES = [
  { value: "RESTORE", label: "원상복구" },
  { value: "IMPROVE", label: "성능개선" },
  { value: "REPLACE_MAJOR", label: "주요부품 교체" },
];

type PartRow = { part_no: string; name: string; serial: string; qty: string };

export function RepairForm({
  equipmentId,
  initial,
  onDone,
}: {
  equipmentId?: string;
  /** 수정 모드일 때 기존 값. 없으면 신규 생성. */
  initial?: ApiRepair | null;
  onDone: (repair: ApiRepair) => void;
}) {
  const [equipment, setEquipment] = useState(initial?.equipment_id ?? equipmentId ?? "");
  const [workType, setWorkType] = useState(initial?.work_type ?? "UNPLANNED");
  const [scope, setScope] = useState(initial?.repair_scope ?? "RESTORE");
  const [cost, setCost] = useState(initial?.cost != null ? String(initial.cost) : "");
  const [downtime, setDowntime] = useState(
    initial?.downtime_hours != null ? String(initial.downtime_hours) : ""
  );
  const [note, setNote] = useState(initial?.note ?? "");
  const [picked, setPicked] = useState<PartRow[]>(
    (initial?.parts ?? []).map((p) => ({
      part_no: p.part_no,
      name: p.part_no,
      serial: p.serial ?? "",
      qty: p.qty != null ? String(p.qty) : "",
    }))
  );

  const [query, setQuery] = useState("");
  const [items, setItems] = useState<ApiInventoryItem[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchFailure, setSearchFailure] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

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
        setItems([]);
      } else {
        setSearchFailure("부품을 검색하지 못했습니다 — 잠시 후 다시 시도해 주세요.");
      }
    } finally {
      setSearching(false);
    }
  }

  function addPart(it: ApiInventoryItem) {
    if (picked.some((p) => p.part_no === it.part_no)) return; // 같은 품번 중복 금지
    setPicked((prev) => [...prev, { part_no: it.part_no, name: it.name, serial: "", qty: "1" }]);
  }

  function patchRow(partNo: string, patch: Partial<PartRow>) {
    setPicked((prev) => prev.map((p) => (p.part_no === partNo ? { ...p, ...patch } : p)));
  }

  const ready = equipment.trim() !== "" && cost.trim() !== "" && picked.length > 0;

  async function submit() {
    if (!ready || submitting) return;
    setSubmitting(true);
    setFailure(null);
    // 빈 값은 **키 자체를 빼서** 보낸다 — 빈 문자열·0 으로 채우면 "모름"이 "없음"으로
    // 둔갑한다(D62). 서버 공유 계층도 같은 규약이다.
    const body: RepairDraftInput = {
      equipment_id: equipment.trim(),
      work_type: workType,
      repair_scope: scope,
      cost: Number(cost),
      parts: picked.map((p) => ({
        part_no: p.part_no,
        ...(p.serial.trim() ? { serial: p.serial.trim() } : {}),
        ...(p.qty.trim() ? { qty: Number(p.qty) } : {}),
      })),
      ...(downtime.trim() ? { downtime_hours: Number(downtime) } : {}),
      ...(note.trim() ? { note: note.trim() } : {}),
    };
    try {
      const { createRepair, updateRepair } = await import("@/lib/api");
      const res = initial?.repair_id
        ? await updateRepair(initial.repair_id, body)
        : await createRepair(body);
      onDone(res);
    } catch (e) {
      // 서버가 준 사유를 그대로 보여준다 — 화면이 다시 쓰지 않는다(D87 태도).
      setFailure(
        e instanceof ApiError
          ? extractDetail(e.body) ||
              (typeof errorBody(e)?.message === "string" ? String(errorBody(e)?.message) : "") ||
              "저장하지 못했습니다."
          : "백엔드에 연결하지 못했습니다."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={sx("display:flex;flex-direction:column;gap:14px")}>
      {failure && <StatusBanner tone="error">{failure}</StatusBanner>}

      <Field label="설비 ID">
        <input
          value={equipment}
          onChange={(e) => setEquipment(e.target.value)}
          placeholder="예: INV-L3-01"
          style={inputStyle}
        />
      </Field>

      <div style={sx("display:flex;gap:10px")}>
        <Field label="작업 유형">
          <select value={workType} onChange={(e) => setWorkType(e.target.value)} style={inputStyle}>
            {WORK_TYPES.map((w) => (
              <option key={w.value} value={w.value}>
                {w.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="수리 범위">
          <select value={scope} onChange={(e) => setScope(e.target.value)} style={inputStyle}>
            {REPAIR_SCOPES.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <div style={sx("display:flex;gap:10px")}>
        <Field label="수리 비용 (원)">
          <input
            value={cost}
            onChange={(e) => setCost(e.target.value)}
            inputMode="numeric"
            placeholder="예: 250000"
            style={inputStyle}
          />
        </Field>
        <Field label="비가동 시간 (선택)">
          <input
            value={downtime}
            onChange={(e) => setDowntime(e.target.value)}
            inputMode="decimal"
            placeholder="예: 2.5"
            style={inputStyle}
          />
        </Field>
      </div>

      {/* ── 교체 부품 — 1건 이상 필수 (계약: data/repair_record.validate_parts) */}
      <Field label="교체 부품 (1건 이상 필수)">
        <div style={sx("display:flex;gap:7px")}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void search();
            }}
            placeholder="부품명으로 검색 (예: 냉각팬)"
            style={inputStyle}
          />
          <Button
            onClick={query.trim() && !searching ? () => void search() : undefined}
            style={query.trim() && !searching ? "" : "opacity:.5;cursor:not-allowed"}
          >
            {searching ? "검색 중…" : "검색"}
          </Button>
        </div>
      </Field>

      {searchFailure && <StatusBanner tone="error">{searchFailure}</StatusBanner>}

      {items !== null && items.length === 0 && (
        <span style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
          검색 결과가 없습니다 — 등록되지 않은 품번은 저장할 수 없습니다.
        </span>
      )}

      {items !== null && items.length > 0 && (
        <div style={sx("display:flex;flex-direction:column;gap:5px")}>
          {items.map((it) => {
            const already = picked.some((p) => p.part_no === it.part_no);
            return (
              <button
                key={it.part_no}
                onClick={() => addPart(it)}
                disabled={already}
                style={sx(
                  "display:flex;justify-content:space-between;align-items:center;gap:8px;" +
                    "border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
                    `padding:8px 11px;text-align:left;cursor:${already ? "default" : "pointer"};` +
                    `opacity:${already ? ".45" : "1"}`
                )}
              >
                <span style={sx("font:12px 'Pretendard';color:var(--ink)")}>{it.name}</span>
                <Mono size={11.5}>{already ? "추가됨" : it.part_no}</Mono>
              </button>
            );
          })}
        </div>
      )}

      {picked.length > 0 && (
        <div style={sx("display:flex;flex-direction:column;gap:6px")}>
          {picked.map((p) => (
            <div
              key={p.part_no}
              style={sx(
                "display:flex;align-items:center;gap:7px;border:1px solid var(--line);" +
                  "border-radius:7px;padding:7px 9px;background:var(--panel)"
              )}
            >
              <Mono size={11.5}>{p.part_no}</Mono>
              <input
                value={p.serial}
                onChange={(e) => patchRow(p.part_no, { serial: e.target.value })}
                placeholder="시리얼 (선택)"
                style={sx(smallInput)}
              />
              <input
                value={p.qty}
                onChange={(e) => patchRow(p.part_no, { qty: e.target.value })}
                inputMode="numeric"
                placeholder="수량"
                style={sx(`${smallInput};width:64px`)}
              />
              <button
                onClick={() => setPicked((prev) => prev.filter((x) => x.part_no !== p.part_no))}
                style={sx(
                  "border:none;background:none;cursor:pointer;font:13px 'Pretendard';" +
                    "color:var(--dim2);padding:0 4px"
                )}
                aria-label={`${p.part_no} 제거`}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      <Field label="비고 (선택)">
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="작업 내용을 간단히"
          style={inputStyle}
        />
      </Field>

      {/* 지출 성격은 서버가 산출한다 — 폼에 입력란을 두지 않는다는 사실을 사용자에게도 알린다 */}
      <span style={sx("font:11px/1.5 'Pretendard';color:var(--dim2)")}>
        지출 성격(자본적/수익적)은 저장 후 시스템이 산출합니다 — 회계·세무 판단의 참고값이며
        확정이 아닙니다.
      </span>

      <Button
        onClick={ready && !submitting ? () => void submit() : undefined}
        style={ready && !submitting ? "" : "opacity:.5;cursor:not-allowed"}
      >
        {submitting ? "저장 중…" : initial?.repair_id ? "수정 저장" : "초안 만들기"}
      </Button>
    </div>
  );
}

const inputStyle = sx(
  "flex:1;height:34px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
    "padding:0 11px;font:12.5px 'Pretendard';color:var(--ink);outline:none"
);

const smallInput =
  "flex:1;height:28px;border:1px solid var(--line2);border-radius:6px;background:var(--field);" +
  "padding:0 9px;font:11.5px 'Pretendard';color:var(--ink);outline:none";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={sx("display:flex;flex-direction:column;gap:5px;flex:1")}>
      <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>{label}</span>
      {children}
    </label>
  );
}
