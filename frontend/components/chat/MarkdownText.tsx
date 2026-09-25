import { Fragment } from "react";
import { Mono } from "@/components/ui/Mono";
import { parseMarkdown, type MdBlock, type MdInline } from "@/lib/markdown";
import { sx } from "@/lib/sx";

/**
 * 에이전트 답변 텍스트(SSE `token` 누적분)를 최소 마크다운으로 그린다.
 *
 * 파싱은 `lib/markdown.ts`(순수 함수)가 하고 여기서는 **React 요소로만** 조립한다 —
 * `dangerouslySetInnerHTML` 을 쓰지 않으므로 답변에 섞인 `<script>` 등은 글자 그대로 보인다.
 * 안전 블록·인용 칩·발주 카드 같은 block 이벤트는 이 컴포넌트를 거치지 않는다(텍스트 토큰 전용).
 */
export function MarkdownText({ text }: { text: string }) {
  const blocks = parseMarkdown(text);
  return (
    <div style={sx("display:flex;flex-direction:column;gap:6px")}>
      {blocks.map((b, i) => (
        <Block key={i} block={b} />
      ))}
    </div>
  );
}

function Block({ block }: { block: MdBlock }) {
  switch (block.t) {
    case "p":
      return (
        <div>
          {block.lines.map((line, i) => (
            <Fragment key={i}>
              {i > 0 && <br />}
              <Inlines nodes={line} />
            </Fragment>
          ))}
        </div>
      );
    case "h":
      return (
        <div style={sx("font-weight:700;color:var(--ink)")}>
          <Inlines nodes={block.inlines} />
        </div>
      );
    case "ul":
      return (
        <ul style={sx("margin:0;padding-left:18px")}>
          {block.items.map((item, i) => (
            <li key={i}>
              <Inlines nodes={item} />
            </li>
          ))}
        </ul>
      );
    case "ol":
      return (
        <ol start={block.start} style={sx("margin:0;padding-left:20px")}>
          {block.items.map((item, i) => (
            <li key={i}>
              <Inlines nodes={item} />
            </li>
          ))}
        </ol>
      );
  }
}

function Inlines({ nodes }: { nodes: MdInline[] }) {
  return (
    <>
      {nodes.map((n, i) => {
        switch (n.t) {
          case "text":
            return <Fragment key={i}>{n.text}</Fragment>;
          case "code":
            return <Mono key={i}>{n.text}</Mono>;
          case "strong":
            return (
              <strong key={i} style={sx("font-weight:700;color:var(--ink)")}>
                <Inlines nodes={n.children} />
              </strong>
            );
        }
      })}
    </>
  );
}
