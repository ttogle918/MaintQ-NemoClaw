"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AssetHeader } from "@/components/asset/AssetHeader";
import { EvidenceBundlePanel } from "@/components/asset/EvidenceBundlePanel";
import { ConsoleFrame, ScreenStack } from "@/components/layout/ConsoleFrame";
import { StatusBanner } from "@/components/layout/StatusBanner";
import { Mono } from "@/components/ui/Mono";
import { ApiError, getAsset, type ApiAsset } from "@/lib/api";
import { sx } from "@/lib/sx";

/**
 * `/technician/asset/{assetId}/evidence` — 근거 번들 화면 (S10, MQ-1001/P37).
 *
 * `value/page.tsx`·`disposal/page.tsx` 와 동일한 fetch/loading/error 패턴이다 —
 * 자산 조회(`GET /api/assets/{id}`) → `AssetHeader` → 본체(`EvidenceBundlePanel`).
 *
 * 이 화면은 아무것도 저장하지 않는다 — `build_evidence_bundle` 은 읽기 전용이다(D71).
 */
export default function AssetEvidencePage({ params }: { params: { assetId: string } }) {
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
              ← 처분 사전판정으로
            </Link>
          }
        />

        <EvidenceBundlePanel assetId={asset.asset_id} />

        <div
          style={sx(
            "border-top:1px solid var(--line);background:var(--head);padding:12px 18px;" +
              "font:11.5px 'Pretendard';color:var(--dim2)"
          )}
        >
          <Link
            href="/manager/expenditure"
            style={sx("color:var(--blue-tx);text-decoration:none")}
          >
            지출 분류 페이지에서 별도로 확인 →
          </Link>
        </div>
      </ConsoleFrame>
    </ScreenStack>
  );
}
