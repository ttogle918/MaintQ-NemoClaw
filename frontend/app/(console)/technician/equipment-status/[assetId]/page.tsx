"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { EquipmentHotspotDiagram } from "@/components/asset/EquipmentHotspotDiagram";
import { ConsoleFrame, ScreenStack } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Mono } from "@/components/ui/Mono";
import { ApiError, getAsset, getHotspotStatus, type ApiAsset, type ApiHotspotStatus } from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * `/technician/equipment-status/{assetId}` — 설비 하이라이트 상세 (Sprint 10 브레인스토밍 C).
 *
 * 이 화면도 아무것도 저장하지 않는다 — `hotspot-status`는 읽기 전용 집계다.
 */
export default function EquipmentStatusDetailPage({
  params,
}: {
  params: { assetId: string };
}) {
  const assetId = decodeURIComponent(params.assetId);

  const [asset, setAsset] = useState<ApiAsset | null>(null);
  const [status, setStatus] = useState<ApiHotspotStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      getAsset("technician", assetId),
      // hotspot-status 의 404(no_equipment_for_asset)는 "등록 안 된 자산"이 아니라
      // "연결된 인버터가 없는, 정상 등록된 자산"이다 — getAsset 의 404 와 원인이 다르므로
      // 여기서 개별로 흡수해 하단 status.status==="not_found" 분기로 보낸다.
      getHotspotStatus("technician", assetId).catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 404) {
          return { status: "not_found" } as ApiHotspotStatus;
        }
        throw e;
      }),
    ])
      .then(([a, s]) => {
        if (!alive) return;
        setAsset(a);
        setStatus(s);
        setError(null);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setAsset(null);
        setError(
          e instanceof ApiError && e.status === 404
            ? `등록부에 없는 식별자입니다 — ${assetId}`
            : "백엔드에 연결하지 못했습니다 — 설비 정보를 가져오지 못했습니다."
        );
      });
    return () => {
      alive = false;
    };
  }, [assetId]);

  if (error) {
    return (
      <ScreenStack>
        <StatusBanner tone="error">⚠ {error}</StatusBanner>
        <Link
          href="/technician/equipment-status"
          style={sx("font:12px 'Pretendard';color:var(--blue-tx);text-decoration:none")}
        >
          ← 설비 하이라이트 목록으로
        </Link>
      </ScreenStack>
    );
  }

  if (!asset || !status) {
    return (
      <ScreenStack>
        <ConsoleFrame>
          <div style={sx("padding:24px;font:12.5px 'Pretendard';color:var(--dim)")}>
            불러오는 중…
          </div>
        </ConsoleFrame>
      </ScreenStack>
    );
  }

  return (
    <ScreenStack>
      <ConsoleFrame>
        <div style={sx("padding:14px 16px;display:flex;flex-direction:column;gap:14px")}>
          <div style={sx("display:flex;align-items:center;gap:10px")}>
            <Link
              href="/technician/equipment-status"
              style={sx("font:12px 'Pretendard';color:var(--blue-tx);text-decoration:none")}
            >
              ← 목록
            </Link>
            <span style={sx("font:700 14px 'Pretendard';color:var(--ink)")}>{asset.name}</span>
            <Mono size={11.5}>{asset.asset_id}</Mono>
            {status.status === "ok" && <Mono size={11.5}>{status.model}</Mono>}
          </div>

          {status.status !== "ok" ? (
            <div
              style={sx(
                "border:1px dashed var(--line2);border-radius:7px;padding:16px;" +
                  "font:12.5px/1.7 'Pretendard';color:var(--dim)"
              )}
            >
              이 설비의 하이라이트 상태를 확인할 수 없습니다
              {status.status === "not_found" ? " — 연결된 인버터가 없습니다." : "."}
            </div>
          ) : (
            <EquipmentHotspotDiagram model={status.model!} parts={status.parts ?? []} />
          )}
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
