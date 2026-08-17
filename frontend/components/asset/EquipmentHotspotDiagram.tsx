"use client";

import { useState } from "react";
import { Mono } from "@/components/ui/Mono";
import type { ApiHotspotPart } from "@/lib/api";
import {
  FAN_DETAIL_CITATION,
  MODEL_BASE_IMAGE,
  MODEL_CITATION,
  MODEL_HOTSPOTS,
  type Hotspot,
} from "@/lib/hotspots";
import { hotspotColorView } from "@/lib/mappers";
import { sx } from "@/lib/sx";

/**
 * 설비 하이라이트 도면 (Sprint 10 브레인스토밍 C, spec §4-1·§4-4).
 *
 * 기본 뷰: 매뉴얼 도면 위 3개 하이라이트 원 + 옆 목록(색 있는 것만). 원과 목록 항목은
 * 같은 상세 패널을 연다(spec §4-1 "도면 위 원과 옆 목록 항목은 같은 상세 패널을 연다").
 *
 * 확대 뷰: 냉각팬은 매뉴얼 실제 근접 이미지로 전환(`detailImage`), 나머지는 기본 도면을
 * 그 좌표 중심으로 CSS `transform: scale()` 확대한다(spec §4-4 — 별도 이미지 없음).
 */
export function EquipmentHotspotDiagram({
  model,
  parts,
}: {
  model: string;
  parts: ApiHotspotPart[];
}) {
  const [selected, setSelected] = useState<string | null>(null);

  const hotspots = MODEL_HOTSPOTS[model];
  const baseImage = MODEL_BASE_IMAGE[model];
  const citation = MODEL_CITATION[model];

  if (!hotspots || !baseImage) {
    return (
      <div style={sx("font:12px 'Pretendard';color:var(--dim)")}>
        이 모델({model})의 도면이 등록돼 있지 않습니다.
      </div>
    );
  }

  const statusByPart = new Map(parts.map((p) => [p.part_no, p]));
  const selectedHotspot = hotspots.find((h) => h.partNo === selected) ?? null;
  const selectedStatus = selected ? statusByPart.get(selected) : undefined;

  return (
    <div style={sx("display:flex;flex-direction:column;gap:12px")}>
      <div style={sx("display:flex;gap:16px;flex-wrap:wrap")}>
        <div
          style={sx(
            "position:relative;width:min(560px,100%);border:1px solid var(--line);" +
              "border-radius:8px;overflow:hidden;background:var(--panel)"
          )}
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- 크롭된 정적 자산, 최적화 불필요 */}
          <img
            src={baseImage}
            alt={`${model} 도면`}
            style={sx("display:block;width:100%;height:auto")}
          />
          {hotspots.map((h) => {
            const status = statusByPart.get(h.partNo);
            const view = hotspotColorView(status?.color ?? null);
            return (
              <button
                key={h.partNo}
                onClick={() => setSelected(h.partNo)}
                aria-label={h.label}
                style={sx(
                  `position:absolute;left:${h.x}%;top:${h.y}%;transform:translate(-50%,-50%);` +
                    "width:28px;height:28px;border-radius:50%;cursor:pointer;" +
                    (view.dotColor
                      ? `border:2px solid ${view.dotColor};background:color-mix(in srgb, ${view.dotColor} 20%, transparent)`
                      : "border:1.5px dashed var(--line2);background:transparent")
                )}
              />
            );
          })}
        </div>

        <div style={sx("flex:1;min-width:200px;display:flex;flex-direction:column;gap:8px")}>
          <span style={sx("font:700 12px 'Pretendard';color:var(--ink)")}>하이라이트 항목</span>
          {hotspots
            .map((h) => ({ h, status: statusByPart.get(h.partNo) }))
            .filter(({ status }) => status?.color)
            .map(({ h, status }) => {
              const view = hotspotColorView(status!.color);
              return (
                <button
                  key={h.partNo}
                  onClick={() => setSelected(h.partNo)}
                  style={sx(
                    "display:flex;align-items:center;gap:8px;text-align:left;cursor:pointer;" +
                      "border:1px solid var(--line2);background:var(--raise);border-radius:7px;" +
                      "padding:7px 10px"
                  )}
                >
                  <span
                    style={sx(
                      `width:9px;height:9px;border-radius:50%;background:${view.dotColor}`
                    )}
                  />
                  <span style={sx("font:700 12px 'Pretendard';color:var(--ink)")}>{h.label}</span>
                  <span style={sx("font:11px 'Pretendard';color:var(--dim)")}>{view.text}</span>
                </button>
              );
            })}
          {hotspots.every((h) => !statusByPart.get(h.partNo)?.color) && (
            <span style={sx("font:11.5px 'Pretendard';color:var(--dim)")}>
              하이라이트된 부위가 없습니다.
            </span>
          )}
          <span style={sx("font:11px 'Pretendard';color:var(--dim2);margin-top:4px")}>
            {citation}
          </span>
        </div>
      </div>

      {selectedHotspot && (
        <DetailPanel
          model={model}
          hotspot={selectedHotspot}
          status={selectedStatus}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

function DetailPanel({
  model,
  hotspot,
  status,
  onClose,
}: {
  model: string;
  hotspot: Hotspot;
  status: ApiHotspotPart | undefined;
  onClose: () => void;
}) {
  const view = hotspotColorView(status?.color ?? null);
  const baseImage = MODEL_BASE_IMAGE[model];

  return (
    <div
      style={sx(
        "border:1px solid var(--line);border-radius:8px;background:var(--panel);padding:14px;" +
          "display:flex;gap:16px;flex-wrap:wrap"
      )}
    >
      <div
        style={sx(
          "position:relative;width:min(420px,100%);height:260px;border-radius:6px;" +
            "overflow:hidden;background:var(--raise)"
        )}
      >
        {hotspot.detailImage ? (
          // eslint-disable-next-line @next/next/no-img-element -- 크롭된 정적 자산
          <img
            src={hotspot.detailImage}
            alt={`${hotspot.label} 근접`}
            style={sx("display:block;width:100%;height:100%;object-fit:contain")}
          />
        ) : (
          <div
            style={sx(
              `position:absolute;inset:0;background-image:url(${baseImage});` +
                "background-repeat:no-repeat;background-size:280%;" +
                `background-position:${hotspot.x}% ${hotspot.y}%`
            )}
          />
        )}
      </div>

      <div style={sx("flex:1;min-width:220px;display:flex;flex-direction:column;gap:8px")}>
        <div style={sx("display:flex;align-items:center;gap:8px")}>
          <span style={sx("font:700 13px 'Pretendard';color:var(--ink)")}>{hotspot.label}</span>
          <Mono size={11}>{hotspot.partNo}</Mono>
          <span
            style={sx(
              `font:700 11px 'Pretendard';color:${view.dotColor ?? "var(--dim)"}`
            )}
          >
            {view.text}
          </span>
          <div style={sx("flex:1")} />
          <button
            onClick={onClose}
            style={sx(
              "border:1px solid var(--line2);background:transparent;border-radius:6px;" +
                "width:24px;height:24px;cursor:pointer;color:var(--dim)"
            )}
          >
            ✕
          </button>
        </div>

        {hotspot.approximate && (
          <div
            style={sx(
              "border:1.5px dashed var(--orange-tx);border-radius:6px;padding:6px 9px;" +
                "font:11px/1.6 'Pretendard';color:var(--orange-tx)"
            )}
          >
            ⚠ 매뉴얼에 정확한 라벨이 없어 대략적인 영역입니다 — 실제 부품 위치와 다를 수 있습니다.
          </div>
        )}

        <DetailBody color={status?.color ?? null} basis={status?.basis ?? {}} />

        {hotspot.detailImage && (
          <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
            {FAN_DETAIL_CITATION}
          </span>
        )}
      </div>
    </div>
  );
}

/** color 별 근거 텍스트 — 값을 검사해 분기하되, 색·문구는 hotspotColorView 가 이미 정했다. */
function DetailBody({
  color,
  basis,
}: {
  color: "red" | "blue" | "orange" | null;
  basis: Record<string, unknown>;
}) {
  if (color === "red") {
    const causes = Array.isArray(basis.causes) ? (basis.causes as string[]) : [];
    const actions = Array.isArray(basis.actions) ? (basis.actions as string[]) : [];
    return (
      <div style={sx("display:flex;flex-direction:column;gap:6px;font:12px/1.6 'Pretendard'")}>
        {typeof basis.code === "string" && (
          <span style={sx("color:var(--dim)")}>
            에러코드 <Mono size={11}>{basis.code}</Mono>
            {typeof basis.occurred_at === "string" && ` · ${basis.occurred_at}`}
          </span>
        )}
        {causes.length > 0 && (
          <div>
            <b style={sx("color:var(--ink)")}>원인</b>
            <ul style={sx("margin:4px 0 0 18px;padding:0;color:var(--ink2)")}>
              {causes.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </div>
        )}
        {actions.length > 0 && (
          <div>
            <b style={sx("color:var(--ink)")}>조치</b>
            <ul style={sx("margin:4px 0 0 18px;padding:0;color:var(--ink2)")}>
              {actions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>
        )}
        {typeof basis.manual_page === "number" && (
          <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
            근거:{" "}
            {typeof basis.print_page === "number"
              ? `인쇄 p.${basis.print_page} · PDF p.${basis.manual_page}`
              : `PDF p.${basis.manual_page}`}
          </span>
        )}
      </div>
    );
  }

  if (color === "blue") {
    return (
      <div style={sx("font:12px/1.6 'Pretendard';color:var(--ink2)")}>
        {typeof basis.signed_at === "string" && <div>수리 일자: {basis.signed_at}</div>}
        {typeof basis.performed_by_name === "string" && (
          <div>작업자: {basis.performed_by_name}</div>
        )}
        {typeof basis.repair_id === "string" && (
          <div style={sx("color:var(--dim)")}>
            증빙 <Mono size={11}>{basis.repair_id}</Mono>
          </div>
        )}
      </div>
    );
  }

  if (color === "orange") {
    return (
      <div style={sx("font:12px/1.6 'Pretendard';color:var(--ink2)")}>
        {typeof basis.next_maintenance_due === "string" && (
          <div>다음 점검 예정일: {basis.next_maintenance_due}</div>
        )}
        <span style={sx("font:10.5px 'Pretendard';color:var(--dim2)")}>
          ⚠ 생애주기 mock 데이터입니다 — 실제 정비 이력에서 유도한 값이 아닙니다.
        </span>
      </div>
    );
  }

  return (
    <div style={sx("font:12px 'Pretendard';color:var(--dim)")}>
      현재 하이라이트된 상태가 없습니다.
    </div>
  );
}
