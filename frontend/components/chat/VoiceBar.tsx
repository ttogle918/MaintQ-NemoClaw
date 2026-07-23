"use client";

import { Button, IconButton } from "@/components/ui/Button";
import { sx } from "@/lib/sx";

const WAVE_DELAYS = [0, 0.15, 0.3, 0.45, 0.6];

/** 음성 입력 상태 — 장갑 낀 현장 작업자 대상 (백로그 P8 의 UI 자리). */
export function VoiceBar({ onStop }: { onStop: () => void }) {
  return (
    <div style={sx("display:flex;gap:12px;align-items:center;height:40px")}>
      <IconButton active onClick={onStop} style="animation:mq-ring 1.4s infinite">
        ■
      </IconButton>

      <div
        style={sx(
          "flex:1;display:flex;align-items:center;gap:12px;height:40px;border:1px solid var(--saf-cite-bd);" +
            "border-radius:9px;background:var(--saf-cite-bg);padding:0 15px"
        )}
      >
        <div style={sx("display:flex;align-items:flex-end;gap:3px;height:20px")}>
          {WAVE_DELAYS.map((d) => (
            <span
              key={d}
              style={sx(
                "width:3px;height:100%;background:var(--orange);border-radius:2px;" +
                  `animation:mq-wave .9s ease-in-out infinite;animation-delay:${d}s`
              )}
            />
          ))}
        </div>
        <span style={sx("font:600 12.5px 'Pretendard';color:var(--saf-tx)")}>
          듣고 있어요 — 말씀하세요
        </span>
        <div style={sx("flex:1")} />
        <span style={sx("font:11px 'JetBrains Mono',monospace;color:var(--saf-cite-tx)")}>0:03</span>
      </div>

      <Button variant="outline" onClick={onStop} style="height:40px;border-radius:9px">
        완료
      </Button>
    </div>
  );
}
