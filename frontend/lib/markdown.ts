/**
 * 채팅 답변용 **최소** 마크다운 파서 — 문자열 → 블록/인라인 트리(순수 데이터).
 *
 * 왜 직접 짜나: 에이전트 `token` 스트림은 `**굵게**`·`- 목록`·`1. 번호` 를 섞어 보내는데
 * 버블은 그걸 평문으로 찍고 있었다. 마크다운 라이브러리는 `package.json` 에 없고, 필요한
 * 문법은 몇 가지뿐이라 의존성을 들이지 않는다.
 *
 * ## 안전 규칙 (XSS)
 * - 이 파서는 **HTML 을 만들지 않는다.** 결과는 `{t:"text", text}` 같은 데이터일 뿐이고,
 *   렌더러(`components/chat/MarkdownText.tsx`)가 React 요소로 조립한다 — React 가 텍스트를
 *   이스케이프하므로 `<script>` 는 글자 그대로 보인다. `dangerouslySetInnerHTML` 금지.
 * - 링크·이미지·raw HTML 문법은 **지원하지 않는다**(글자 그대로 남는다). URL 을 속성에 넣는
 *   경로 자체가 없다.
 *
 * ## 스트리밍 규칙
 * token 이 반쯤 도착한 상태(`**굵` · `` `co ``)에서도 매번 전체를 다시 파싱한다. **닫히지 않은
 * 마크는 평문으로 남긴다** — 표식을 삼키거나 뒤 전체를 굵게 만들지 않는다. 닫는 표식이
 * 도착하는 순간 굵게로 바뀐다.
 *
 * 지원 범위: `**굵게**` · `` `인라인 코드` `` · 줄머리 `- `/`* ` 목록 · `1. `/`1) ` 번호 목록 ·
 * `#`~`######` 제목(굵은 한 줄로만) · 빈 줄 = 문단 구분 · 문단 안 줄바꿈 유지.
 * 그 외(기울임·링크·표·중첩 목록 들여쓰기)는 글자 그대로 둔다.
 *
 * **React 를 import 하지 않고 `@/` 별칭도 쓰지 않는다** — `spikes/ui_honesty_contract.py`
 * 의 L1 이 이 파일을 단독 `tsc` 로 컴파일해 돌린다(제약 게이트 C15·C16).
 */

export type MdInline =
  | { t: "text"; text: string }
  | { t: "strong"; children: MdInline[] }
  | { t: "code"; text: string };

export type MdBlock =
  | { t: "p"; lines: MdInline[][] }
  | { t: "h"; inlines: MdInline[] }
  | { t: "ul"; items: MdInline[][] }
  | { t: "ol"; start: number; items: MdInline[][] };

const UL_ITEM = /^\s*[-*+]\s+(.*)$/;
const OL_ITEM = /^\s*(\d{1,4})[.)]\s+(.*)$/;
const HEADING = /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/;

function pushText(out: MdInline[], text: string): void {
  if (!text) return;
  const last = out[out.length - 1];
  if (last && last.t === "text") {
    out[out.length - 1] = { t: "text", text: last.text + text };
  } else {
    out.push({ t: "text", text });
  }
}

/** 코드 스팬만 처리한다(굵게 안쪽용). 닫히지 않은 백틱은 평문. */
function parseCode(s: string, out: MdInline[]): void {
  let i = 0;
  while (i < s.length) {
    const open = s.indexOf("`", i);
    if (open < 0) break;
    const close = s.indexOf("`", open + 1);
    if (close < 0) break;
    if (close === open + 1) {
      // 빈 코드 스팬(``)은 의미가 없다 — 글자 그대로
      pushText(out, s.slice(i, close + 1));
      i = close + 1;
      continue;
    }
    pushText(out, s.slice(i, open));
    out.push({ t: "code", text: s.slice(open + 1, close) });
    i = close + 1;
  }
  pushText(out, s.slice(i));
}

/**
 * 한 줄 인라인 파싱. 우선순위: 코드 스팬 > 굵게. 코드 안의 `**` 는 굵게가 아니다.
 * 닫히지 않은 `**`·`` ` `` 는 평문으로 남는다(스트리밍 중간 상태).
 */
export function parseInline(line: string): MdInline[] {
  const out: MdInline[] = [];
  let i = 0;
  let buf = "";
  while (i < line.length) {
    const ch = line[i];
    if (ch === "`") {
      const close = line.indexOf("`", i + 1);
      if (close > i + 1) {
        pushText(out, buf);
        buf = "";
        out.push({ t: "code", text: line.slice(i + 1, close) });
        i = close + 1;
        continue;
      }
      buf += ch;
      i += 1;
      continue;
    }
    if (ch === "*" && line[i + 1] === "*") {
      const close = line.indexOf("**", i + 2);
      const inner = close >= 0 ? line.slice(i + 2, close) : "";
      // 내용이 비었거나 공백뿐이면 굵게가 아니다(`****`·`** **`)
      if (close >= 0 && inner.trim() !== "") {
        pushText(out, buf);
        buf = "";
        const children: MdInline[] = [];
        parseCode(inner, children);
        out.push({ t: "strong", children });
        i = close + 2;
        continue;
      }
      // 닫히지 않은 `**` — 표식을 삼키지 않고 글자 그대로 둔다
      buf += "**";
      i += 2;
      continue;
    }
    buf += ch;
    i += 1;
  }
  pushText(out, buf);
  return out;
}

/** 전체 텍스트 → 블록 목록. `\r\n` 은 `\n` 으로 본다. */
export function parseMarkdown(src: string): MdBlock[] {
  const blocks: MdBlock[] = [];
  let para: MdInline[][] | null = null;
  let list: Extract<MdBlock, { t: "ul" } | { t: "ol" }> | null = null;

  const flush = (): void => {
    if (para) blocks.push({ t: "p", lines: para });
    if (list) blocks.push(list);
    para = null;
    list = null;
  };

  for (const raw of src.replace(/\r\n?/g, "\n").split("\n")) {
    if (raw.trim() === "") {
      flush();
      continue;
    }
    const ul = UL_ITEM.exec(raw);
    const ol = ul ? null : OL_ITEM.exec(raw);
    if (ul || ol) {
      const kind = ul ? "ul" : "ol";
      const body = ul ? ul[1] : (ol as RegExpExecArray)[2];
      if (!list || list.t !== kind) {
        flush();
        list = ul
          ? { t: "ul", items: [] }
          : { t: "ol", start: Number((ol as RegExpExecArray)[1]), items: [] };
      }
      list.items.push(parseInline(body));
      continue;
    }
    const h = HEADING.exec(raw);
    if (h && h[1] !== "") {
      flush();
      blocks.push({ t: "h", inlines: parseInline(h[1]) });
      continue;
    }
    if (list) flush();
    if (!para) para = [];
    para.push(parseInline(raw));
  }
  flush();
  return blocks;
}

/** 인라인 트리의 보이는 글자만 이어붙인다(검사·접근성 텍스트용). */
export function inlineText(nodes: MdInline[]): string {
  return nodes
    .map((n) => (n.t === "strong" ? inlineText(n.children) : n.text))
    .join("");
}
