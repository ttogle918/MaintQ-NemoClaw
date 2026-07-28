"use client";

import { useState } from "react";
import { Button, IconButton } from "@/components/ui/Button";
import { sx } from "@/lib/sx";
import { VoiceBar } from "./VoiceBar";

const DEFAULT_PLACEHOLDER = "메시지를 입력하거나, 마이크를 눌러 말하세요…";

/**
 * 입력 영역. 전송 시 POST /api/chat 으로 가고 응답은 SSE 로 되돌아온다 (배선은 MQ-405).
 * - Enter · "전송" 버튼 두 경로. 공백만이면 전송하지 않고, 전송 후 입력을 비운다.
 * - 한글 IME 조합 중(isComposing / keyCode 229) Enter 는 무시 — 이중 전송 방지.
 * - `onSend` 미지정(mock 화면)이면 입력만 가능하고 전송은 무동작.
 * - 🎤(VoiceBar, 백로그 P8) · 📷(백로그 P1) 버튼은 자리만 잡아둔 것 — 기능 배선 금지.
 */
export function ChatComposer({
  onSend,
  disabled = false,
  placeholder = DEFAULT_PLACEHOLDER,
}: {
  onSend?: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  const [listening, setListening] = useState(false);
  const [text, setText] = useState("");

  function send() {
    if (disabled) return;
    const t = text.trim();
    if (!t) return; // 공백만 → 전송 안 함
    if (!onSend) return; // mock 화면 — 무동작 (입력은 유지)
    onSend(t);
    setText("");
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter") return;
    // 한글 IME 조합 확정 Enter 가드 (isComposing, 일부 브라우저는 keyCode 229)
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    send();
  }

  return (
    <div style={sx("border-top:1px solid var(--line);background:var(--head);padding:12px 14px")}>
      {listening ? (
        <VoiceBar onStop={() => setListening(false)} />
      ) : (
        <div style={sx("display:flex;gap:8px;align-items:center")}>
          <IconButton
            title="음성으로 말하기"
            onClick={disabled ? undefined : () => setListening(true)}
            style={disabled ? "opacity:.55;cursor:not-allowed" : ""}
          >
            🎤
          </IconButton>
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder={disabled ? "응답 생성 중…" : placeholder}
            aria-label="메시지 입력"
            style={sx(
              "flex:1;min-width:0;height:40px;border:1px solid var(--line2);border-radius:9px;background:var(--field);" +
                "padding:0 13px;font:12.5px 'Pretendard';color:var(--ink);outline:none" +
                (disabled ? ";opacity:.55;cursor:not-allowed" : "")
            )}
          />
          <IconButton title="사진으로 진단 (백로그 P1)">📷</IconButton>
          <Button
            size="lg"
            onClick={disabled ? undefined : send}
            style={
              "height:40px;border-radius:9px" + (disabled ? ";opacity:.55;cursor:not-allowed" : "")
            }
          >
            전송
          </Button>
        </div>
      )}
    </div>
  );
}
