"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { getOnboardingStatusCached } from "@/lib/api";
import { onboardingBadgeView, type OnboardingLabel, type OnboardingTone } from "@/lib/onboarding";
import { roleFromPath } from "@/lib/role";
import { sx } from "@/lib/sx";

/**
 * 기종 온보딩 상태 뱃지 (MQ-1911, D146 — 「진단 가능」은 DB 승격 상태로 게이트한다).
 *
 * `GET /api/onboarding/status?model=` → `onboardingBadgeView(state)` 가 정한 라벨·톤만 그린다.
 * **`none`(iG5A·S100 등 배치 0 기종)은 아무것도 렌더하지 않는다** — 기존 화면 무변화.
 * 결재 상태가 아니라 **기종**의 상태다(발주·처분 큐 어휘와 섞지 않는다).
 *
 * - 조회 중: 아무것도 그리지 않는다(뱃지를 지어내지 않는다).
 * - 조회 실패: `showFailure` 면 `⚠ 온보딩 상태 조회 실패`(unknown 톤), 아니면 숨김 —
 *   설비 카드 그리드에서는 보조 정보라 숨기고, 온보딩 화면 헤더는 드러낸다.
 * - 색: 「진단 가능」만 `ok`(사람 승격 + 안전 문구 승인이 끝난 사실). 「안전 문구 대기」는
 *   정보색 점선, 「온보딩 중」은 중립. 오렌지는 쓰지 않는다(안전·긴급 전용).
 */
export function OnboardingBadge({
  model,
  size = 9,
  showFailure = false,
  refreshKey = 0,
}: {
  model: string;
  size?: number;
  showFailure?: boolean;
  /** 값이 바뀌면 캐시를 무시하고 다시 묻는다 (승격·승인 직후) */
  refreshKey?: number;
}) {
  // 읽기는 역할 무관이지만, 헤더는 화면 라우트의 역할 그대로 싣는다(`lib/api` 관행).
  const role = roleFromPath(usePathname() ?? "");
  const [view, setView] = useState<OnboardingLabel | null | "loading" | "failed">("loading");

  useEffect(() => {
    let alive = true;
    setView("loading");
    getOnboardingStatusCached(role, model, refreshKey > 0)
      .then((res) => {
        if (alive) setView(onboardingBadgeView(res.state));
      })
      .catch(() => {
        if (alive) setView("failed");
      });
    return () => {
      alive = false;
    };
  }, [role, model, refreshKey]);

  if (view === "loading" || view === null) return null;
  if (view === "failed") {
    return showFailure ? (
      <Badge tone="unknown" size={size} title={`GET /api/onboarding/status?model=${model} 실패`}>
        ⚠ 온보딩 상태 조회 실패
      </Badge>
    ) : null;
  }
  return <OnboardingBadgeLabel view={view} size={size} />;
}

const BADGE_TONE: Record<OnboardingTone, BadgeTone> = {
  ok: "ok",
  info: "blue",
  neutral: "neutral",
  caution: "neutral",
  security: "neutral",
  unknown: "unknown",
};

const ICON: Record<OnboardingTone, string> = {
  ok: "✓",
  info: "◑",
  neutral: "○",
  caution: "○",
  security: "○",
  unknown: "",
};

/** 라벨만 그리는 프레젠테이션 조각 — 상태 판정은 이미 `onboardingBadgeView` 가 끝냈다. */
export function OnboardingBadgeLabel({ view, size = 9 }: { view: OnboardingLabel; size?: number }) {
  if (view.tone === "info") {
    // 「안전 문구 대기」 — 디자인(OnboardingBadges): 정보색 **점선**. 진단은 되지만 절차 안내는 차단.
    return (
      <span
        title="에러코드 진단은 가능 · 점검·교체 절차 안내는 안전 문구 승인 전까지 차단"
        style={sx(
          `display:inline-flex;align-items:center;gap:3px;font:700 ${size}px 'JetBrains Mono',monospace;` +
            "border-radius:3px;padding:2px 6px;white-space:nowrap;color:var(--blue-tx);" +
            "border:1px dashed var(--cite-bd);background:var(--cite-bg)"
        )}
      >
        {ICON.info} {view.label}
      </span>
    );
  }
  return (
    <Badge tone={BADGE_TONE[view.tone]} size={size} title={view.known ? undefined : "모르는 온보딩 상태 값"}>
      {ICON[view.tone] ? `${ICON[view.tone]} ` : ""}
      {view.label}
    </Badge>
  );
}
