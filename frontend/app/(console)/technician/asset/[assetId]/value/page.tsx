"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AssetHeader } from "@/components/asset/AssetHeader";
import { MetricsAside } from "@/components/asset/MetricsAside";
import { RepairValuePanel } from "@/components/asset/RepairValuePanel";
import { ConsoleFrame, ScreenStack } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Mono } from "@/components/ui/Mono";
import { ApiError, getAsset, type ApiAsset } from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * `/technician/asset/{assetId}/value` — 수리 가치 판단 화면 (S1+, MQ-914).
 *
 * 우선순위 1(3지 판단 본체) + 3(부품 등급 드로어) + 4(지출 성격 작은 카드) +
 * 5(보전지표 보조 패널)가 한 화면에 모인다. 배치는 좌 `RepairValuePanel`(본체) ·
 * 우 `MetricsAside`(보조·근거 옆)다.
 *
 * 이 화면은 아무것도 저장하지 않는다 — `assess_repair_value`·`classify_expenditure` 둘 다
 * 무저장 판정이고(`04 §12`·`§13`), `classify_part_criticality`(등급 조회)·
 * `get_maintenance_metrics`(보전지표)도 읽기 전용이다. 쓰기 도구는 이 화면 어디에도 없다.
 */
export default function AssetValuePage({ params }: { params: { assetId: string } }) {
  const assetId = decodeURIComponent(params.assetId);

  const [asset, setAsset] = useState<ApiAsset | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getAsset("technician", assetId)
      .then((a) => {
        if (alive) {
          setAsset(a);
          setError(null);
        }
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setAsset(null);
        setError(
          e instanceof ApiError && e.status === 404
            ? `자산 등록부에 없는 식별자입니다 — ${assetId}`
            : "백엔드에 연결하지 못했습니다 — 자산을 불러오지 못했습니다. 목업으로 대체하지 않습니다."
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
          href="/technician/asset"
          style={sx("font:12px 'Pretendard';color:var(--blue-tx);text-decoration:none")}
        >
          ← 자산 목록으로
        </Link>
      </ScreenStack>
    );
  }

  if (!asset) {
    return (
      <ScreenStack>
        <div style={sx("font:12.5px 'Pretendard';color:var(--dim);padding:24px")}>
          자산을 불러오는 중… <Mono>{assetId}</Mono>
        </div>
      </ScreenStack>
    );
  }

  return (
    <ScreenStack>
      <ConsoleFrame>
        <AssetHeader
          asset={asset}
          right={
            <Link
              href={`/technician/asset/${encodeURIComponent(asset.asset_id)}/disposal`}
              style={sx(
                "font:12px 'Pretendard';color:var(--blue-tx);text-decoration:none;white-space:nowrap"
              )}
            >
              처분 사전판정 →
            </Link>
          }
        />

        <div style={sx("display:grid;grid-template-columns:1.35fr 1fr;align-items:start;gap:16px;padding:16px 18px")}>
          <RepairValuePanel asset={asset} />
          <MetricsAside assetId={asset.asset_id} />
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
