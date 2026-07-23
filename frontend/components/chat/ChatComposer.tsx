"use client";

import { useState } from "react";
import { Button, IconButton } from "@/components/ui/Button";
import { sx } from "@/lib/sx";
import { VoiceBar } from "./VoiceBar";

/**
 * 입력 영역. 전송 시 POST /api/chat 으로 가고 응답은 SSE 로 되돌아온다.
 * 📷 버튼은 사진 진단(백로그 P1) 자리만 잡아둔 것.
 */
export function ChatComposer({ onSend }: { onSend?: (text: string) => void }) {
  const [listening, setListening] = useState(false);

  return (
    <div style={sx("border-top:1px solid var(--line);background:var(--head);padding:12px 14px")}>
      {listening ? (
        <VoiceBar onStop={() => setListening(false)} />
      ) : (
        <div style={sx("display:flex;gap:8px;align-items:center")}>
          <IconButton title="음성으로 말하기" onClick={() => setListening(true)}>
            🎤
          </IconButton>
          <div
            style={sx(
              "flex:1;height:40px;border:1px solid var(--line2);border-radius:9px;background:var(--field);" +
                "display:flex;align-items:center;padding:0 13px;font:12.5px 'Pretendard';color:var(--field-tx)"
            )}
          >
            메시지를 입력하거나, 마이크를 눌러 말하세요…
          </div>
          <IconButton title="사진으로 진단 (백로그 P1)">📷</IconButton>
          <Button size="lg" onClick={() => onSend?.("")} style="height:40px;border-radius:9px">
            전송
          </Button>
        </div>
      )}
    </div>
  );
}
