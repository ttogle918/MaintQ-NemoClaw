"use client";

import { useState } from "react";
import { CriticalityDrawer } from "@/components/asset/CriticalityDrawer";
import { ExpenditureCard } from "@/components/asset/ExpenditureCard";
import { InventoryDrawer } from "@/components/asset/InventoryDrawer";
import { Button } from "@/components/ui/Button";
import { Mono } from "@/components/ui/Mono";
import {
  ApiError,
  errorBody,
  extractDetail,
  postRepairValue,
  type ApiAsset,
  type ApiRepairValue,
} from "@/lib/api";
import { estimateNotice, isHoldVerdict, showMetric, showTrend } from "@/lib/maintValue";
import { WORK_SCOPE_OPTIONS, repairValueVerdictView } from "@/lib/mappers";
import { sx } from "@/lib/sx";

/**
 * 수리 가치 판단 본체 (3지 판단, `04 §13`, S1+, MQ-914).
 *
 * 한 화면에 모으는 근거는 계약이다(`04 §13`): 이 도구가 호출하는 하위 두 도구(등급 조회·
 * 보전지표) 중 하나라도 성공하지 못하면 그 사유를 그대로 전파한다 — **이 패널도 삼키지
 * 않는다.** 실패하면 값을 비우고 응답이 준 사유를 그대로 보여준다("일시적 오류"로 바꿔
 * 쓰지 않는다).
 *
 * ⛔ 판정 문자열(수리/교체/매각/근본원인/유보에 해당하는 원문 값)을 이 파일이 직접 비교하지
 *   않는다 — 색·문구는 `lib/mappers.repairValueVerdictView` 가, 반복 고장 안내 순서는
 *   응답의 `repeat_failure` **불리언 사실**이 결정한다(판정 원문을 다시 해석하지 않는다).
 */
export function RepairValuePanel({ asset }: { asset: ApiAsset }) {
  const equipment = Array.isArray(asset.equipment) ? asset.equipment : [];
  const soleEquipmentId =
    equipment.length === 1 && typeof equipment[0]?.equipment_id === "string"
      ? (equipment[0].equipment_id as string)
      : null;

  const [equipmentId, setEquipmentId] = useState<string | null>(soleEquipmentId);
  const [failedPart, setFailedPart] = useState("");
  const [repairCost, setRepairCost] = useState("");
  const [repairScope, setRepairScope] = useState<string | null>(null);

  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ApiRepairValue | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const [drawerPartNo, setDrawerPartNo] = useState<string | null>(null);
  const [inventoryPartNo, setInventoryPartNo] = useState<string | null>(null);

  const costNumber = Number(repairCost);
  const canRun =
    !!equipmentId && failedPart.trim() !== "" && repairCost.trim() !== "" && costNumber > 0 && !busy;

  async function run() {
    if (!equipmentId || !canRun) return;
    setBusy(true);
    setFailure(null);
    try {
      const r = await postRepairValue("technician", equipmentId, {
        failed_part: failedPart.trim(),
        repair_cost: costNumber,
        repair_scope: repairScope ?? undefined,
      });
      if (r.status === "ok") {
        setResult(r);
      } else {
        // 200 인데 status 가 ok 가 아닌 방어. 응답이 준 사유를 그대로 보여준다.
        setResult(null);
        setFailure(r.reason ?? "(사유 없음)");
      }
    } catch (e) {
      setResult(null);
      if (e instanceof ApiError) {
        // §13 은 하위 도구(등급 조회 · 보전지표)의 status/reason 을 그대로 전파한다 —
        // 여기서 문구를 다시 쓰지 않고 본문의 reason·message 를 그대로 보여준다.
        const body = errorBody(e);
        const reason = typeof body?.reason === "string" ? body.reason : "";
        const message = extractDetail(e.body);
        setFailure(reason ? `${reason} — ${message}` : message);
      } else {
        setFailure(
          "백엔드에 연결하지 못했습니다 — 판단 요청이 전달되지 않았습니다. 결과가 없는 것이지 '판단 불가'가 아닙니다."
        );
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={sx("display:flex;flex-direction:column;gap:14px")}>
      <InputForm
        equipment={equipment}
        equipmentId={equipmentId}
        onEquipment={setEquipmentId}
        failedPart={failedPart}
        onFailedPart={setFailedPart}
        repairCost={repairCost}
        onRepairCost={setRepairCost}
        repairScope={repairScope}
        onRepairScope={setRepairScope}
        busy={busy}
        canRun={canRun}
        onRun={() => void run()}
      />

      {failure && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:7px;padding:11px 13px;" +
              "font:12px/1.7 'Pretendard';color:var(--error-tx)"
          )}
        >
          <b>판단할 수 없습니다</b>
          <br />
          {failure}
        </div>
      )}

      {!result && !failure && (
        <div
          style={sx(
            "border:1px dashed var(--line2);border-radius:7px;padding:13px 15px;" +
              "font:12px/1.7 'Pretendard';color:var(--dim)"
          )}
        >
          아직 판단하지 않았습니다. 설비·부품·수리비를 채우고 판단을 실행하세요.
        </div>
      )}

      {result && (
        <ResultView
          result={result}
          onOpenPart={(p) => setDrawerPartNo(p)}
          onOpenInventory={(p) => setInventoryPartNo(p)}
        />
      )}

      <CriticalityDrawer
        open={drawerPartNo !== null}
        partNo={drawerPartNo}
        onClose={() => setDrawerPartNo(null)}
      />
      <InventoryDrawer
        open={inventoryPartNo !== null}
        partNo={inventoryPartNo}
        equipmentId={equipmentId}
        onClose={() => setInventoryPartNo(null)}
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* 입력 폼                                                                     */

function InputForm({
  equipment,
  equipmentId,
  onEquipment,
  failedPart,
  onFailedPart,
  repairCost,
  onRepairCost,
  repairScope,
  onRepairScope,
  busy,
  canRun,
  onRun,
}: {
  equipment: Record<string, unknown>[];
  equipmentId: string | null;
  onEquipment: (id: string | null) => void;
  failedPart: string;
  onFailedPart: (v: string) => void;
  repairCost: string;
  onRepairCost: (v: string) => void;
  repairScope: string | null;
  onRepairScope: (v: string | null) => void;
  busy: boolean;
  canRun: boolean;
  onRun: () => void;
}) {
  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:13px 15px;" +
          "display:flex;flex-direction:column;gap:10px"
      )}
    >
      {equipment.length === 0 && (
        <div style={sx("font:12px/1.7 'Pretendard';color:var(--error-tx)")}>
          이 자산에 등록된 설비가 없습니다 — 판단을 시작할 수 없습니다.
        </div>
      )}

      {equipment.length > 1 && (
        <label style={sx("display:flex;align-items:center;gap:10px")}>
          <span style={sx("font:700 12px 'Pretendard';color:var(--ink2);min-width:78px")}>대상 설비</span>
          <select
            value={equipmentId ?? ""}
            onChange={(e) => onEquipment(e.target.value || null)}
            style={sx(
              "height:30px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
                "padding:0 8px;font:12px 'JetBrains Mono',monospace;color:var(--ink)"
            )}
          >
            <option value="">설비 선택…</option>
            {equipment.map((eq, i) => (
              <option key={`${String(eq.equipment_id)}-${i}`} value={String(eq.equipment_id ?? "")}>
                {String(eq.equipment_id ?? "")}
                {typeof eq.model === "string" ? ` · ${eq.model}` : ""}
              </option>
            ))}
          </select>
        </label>
      )}

      {equipment.length === 1 && equipmentId && (
        <div style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
          대상 설비 · <Mono size={11.5}>{equipmentId}</Mono>
        </div>
      )}

      <label style={sx("display:flex;align-items:center;gap:10px")}>
        <span style={sx("font:700 12px 'Pretendard';color:var(--ink2);min-width:78px")}>고장 부품</span>
        <input
          type="text"
          value={failedPart}
          onChange={(e) => onFailedPart(e.target.value)}
          placeholder="부품 번호 (예: FAN-IG5-01)"
          style={sx(
            "flex:1;height:30px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
              "padding:0 10px;font:12px 'JetBrains Mono',monospace;color:var(--ink);outline:none"
          )}
        />
      </label>

      <label style={sx("display:flex;align-items:center;gap:10px")}>
        <span style={sx("font:700 12px 'Pretendard';color:var(--ink2);min-width:78px")}>수리비(원)</span>
        <input
          type="number"
          min={1}
          value={repairCost}
          onChange={(e) => onRepairCost(e.target.value)}
          placeholder="8500000"
          style={sx(
            "flex:1;height:30px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
              "padding:0 10px;font:12px 'JetBrains Mono',monospace;color:var(--ink);outline:none"
          )}
        />
      </label>

      <label style={sx("display:flex;align-items:center;gap:10px")}>
        <span style={sx("font:700 12px 'Pretendard';color:var(--ink2);min-width:78px")}>수리 범위</span>
        <select
          value={repairScope ?? ""}
          onChange={(e) => onRepairScope(e.target.value || null)}
          style={sx(
            "height:30px;border:1px solid var(--line2);border-radius:7px;background:var(--field);" +
              "padding:0 8px;font:12px 'JetBrains Mono',monospace;color:var(--ink)"
          )}
        >
          <option value="">기본값 사용</option>
          {WORK_SCOPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <div style={sx("display:flex;align-items:center;gap:10px")}>
        <Button onClick={canRun ? onRun : undefined} style={canRun ? "" : "opacity:.5;cursor:not-allowed"}>
          {busy ? "판단 중…" : "수리 가치 판단"}
        </Button>
        <span style={sx("font:11px 'Pretendard';color:var(--dim2)")}>
          POST <Mono size={10.5}>/api/equipment/{"{id}"}/repair-value</Mono> — 무저장
        </span>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/* 결과                                                                        */

function ResultView({
  result,
  onOpenPart,
  onOpenInventory,
}: {
  result: ApiRepairValue;
  onOpenPart: (partNo: string) => void;
  onOpenInventory: (partNo: string) => void;
}) {
  const view = repairValueVerdictView(result.verdict);
  const estimates = Array.isArray(result.estimates) ? result.estimates : [];
  const assumptions = Array.isArray(result.assumptions) ? result.assumptions : [];
  const notConsidered = Array.isArray(result.not_considered) ? result.not_considered : [];
  const alternatives = Array.isArray(result.alternatives) ? result.alternatives : [];

  // 응답이 준 **사실**(반복 고장 여부)로 순서를 정한다 — 판정 원문을 다시 해석하지 않는다.
  const repeatFailure = result.repeat_failure === true;

  // 추정치 고지(D65·D74) — 접히지 않는 위치, 값이 하나라도 있을 때만 노출한다.
  const notice = estimateNotice({
    source: estimates.length > 0 ? "법정 기준내용연수 기반 목업 잔가곡선(D74)" : undefined,
  });

  const heldNotErrored = typeof result.verdict === "string" && isHoldVerdict(result.verdict);

  return (
    <div style={sx("display:flex;flex-direction:column;gap:14px")}>
      {repeatFailure && (
        <div
          style={sx(
            "border:1.5px dashed var(--error-tx);border-radius:8px;padding:11px 13px;" +
              "font:12.5px/1.7 'Pretendard';color:var(--error-tx)"
          )}
        >
          <b>⚠ 반복 고장 감지</b> — 직전 30일 안에 같은 설비에서 고장이 반복됐습니다. 부품 수명이
          아니라 다른 원인(냉각·부하·설치 조건 등)의 신호일 수 있습니다. 아래 판단보다{" "}
          <b>근본원인 점검</b>이 먼저입니다 — 발주는 보류하세요 (S3).
        </div>
      )}

      <div
        style={sx(
          `${view.skin};border-radius:8px;padding:13px 15px;display:flex;flex-direction:column;gap:8px`
        )}
      >
        <div style={sx("display:flex;align-items:center;gap:10px;flex-wrap:wrap")}>
          <span style={sx("font:700 16px 'Pretendard'")}>
            {view.known ? view.text : `⚠ ${view.text}`}
          </span>
          {result.evaluated_at && (
            <span style={sx("font:11px 'JetBrains Mono',monospace;opacity:.8")}>
              기준일 {result.evaluated_at}
            </span>
          )}
        </div>
        <div style={sx("font:12.5px/1.7 'Pretendard'")}>{view.note}</div>
        {result.reasoning && (
          <div style={sx("font:12px/1.6 'Pretendard';opacity:.9")}>{result.reasoning}</div>
        )}
      </div>

      {notice && (
        <div
          style={sx(
            "border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:7px;" +
              "padding:9px 12px;font:11.5px/1.7 'Pretendard';color:var(--blue-tx)"
          )}
        >
          ⚠ {notice}
        </div>
      )}

      {typeof result.failed_part === "string" && (
        <div style={sx("display:flex;align-items:center;gap:8px;flex-wrap:wrap")}>
          <span style={sx("font:11.5px 'Pretendard';color:var(--dim2)")}>고장 부품</span>
          <button
            onClick={() => onOpenPart(result.failed_part as string)}
            style={sx(
              "border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:14px;" +
                "padding:4px 11px;cursor:pointer;font:12px 'JetBrains Mono',monospace;color:var(--blue-tx)"
            )}
          >
            {result.failed_part} <span style={sx("opacity:.7")}>· 등급 보기 →</span>
          </button>
          <button
            onClick={() => onOpenInventory(result.failed_part as string)}
            style={sx(
              "border:1px solid var(--cite-bd);background:var(--cite-bg);border-radius:14px;" +
                "padding:4px 11px;cursor:pointer;font:12px 'JetBrains Mono',monospace;color:var(--blue-tx)"
            )}
          >
            재고 보기 →
          </button>
        </div>
      )}

      <ExpenditureCard
        partClass={result.part_class ?? null}
        repairScope={result.repair_scope ?? null}
        amount={result.repair_cost ?? null}
      />
      {heldNotErrored && (
        <div style={sx("font:10.5px 'Pretendard';color:var(--dim2);margin-top:-6px")}>
          위 수리가치 판단이 판단 유보 상태라도 지출 성격 분류는 별개로 진행됩니다.
        </div>
      )}

      <FactGrid result={result} />

      {alternatives.length > 0 && (
        <Panel title="참고 대안 (alternatives)">
          <ul style={sx("margin:0;padding-left:16px;font:12px/1.8 'Pretendard';color:var(--ink2)")}>
            {alternatives.map((a, i) => (
              <li key={i}>{JSON.stringify(a)}</li>
            ))}
          </ul>
        </Panel>
      )}

      {assumptions.length > 0 && (
        <Panel title="가정 (assumptions) — 아직 사람 동의 전인 값입니다">
          <ul style={sx("margin:0;padding-left:16px;font:12px/1.8 'Pretendard';color:var(--ink2)")}>
            {assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel title="보지 않은 것 (not_considered)">
        {notConsidered.length ? (
          <ul style={sx("margin:0;padding-left:16px;font:12px/1.8 'Pretendard';color:var(--dim)")}>
            {notConsidered.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        ) : (
          <span style={sx("font:12px 'Pretendard';color:var(--dim2)")}>
            응답에 항목이 없습니다 — 고려 범위가 넓다는 뜻이 아닙니다.
          </span>
        )}
        {result.disclaimer && (
          <div style={sx("margin-top:9px;font:11.5px/1.7 'Pretendard';color:var(--dim)")}>
            {result.disclaimer}
          </div>
        )}
      </Panel>
    </div>
  );
}

/** 판정에 쓰인 숫자 사실들. `showMetric`·`showTrend` 로 null·판단 근거 부족을 정직하게 표기한다. */
function FactGrid({ result }: { result: ApiRepairValue }) {
  const rows: { label: string; value: string }[] = [
    { label: "장부가액", value: showMetric(result.book_value ?? null, "원").text },
    { label: "MTBF 추세", value: showTrend(result.mtbf_trend ?? null).text },
    {
      label: "누적 수리비 비율",
      value: showMetric(
        typeof result.cumulative_repair_ratio === "number" ? result.cumulative_repair_ratio * 100 : null,
        "%"
      ).text,
    },
    { label: "시장가(수리 전)", value: showMetric(result.market_value_before ?? null, "원").text },
    { label: "시장가(수리 후)", value: showMetric(result.market_value_after ?? null, "원").text },
    { label: "회복분", value: showMetric(result.value_recovery ?? null, "원").text },
    {
      label: "회복 비율",
      value: showMetric(
        typeof result.recovery_ratio === "number" ? result.recovery_ratio * 100 : null,
        "%"
      ).text,
    },
  ];

  return (
    <div
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:11px 13px;" +
          "display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:9px"
      )}
    >
      {rows.map((r) => (
        <div key={r.label} style={sx("display:flex;flex-direction:column;gap:2px")}>
          <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>{r.label}</span>
          <span style={sx("font:700 12px 'JetBrains Mono',monospace;color:var(--ink2)")}>{r.value}</span>
        </div>
      ))}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:12px 14px;" +
          "display:flex;flex-direction:column;gap:7px"
      )}
    >
      <span style={sx("font:700 12px 'Pretendard';color:var(--ink2)")}>{title}</span>
      {children}
    </section>
  );
}
