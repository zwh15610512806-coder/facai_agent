import type { TextLayerPatch, TextSnapshot } from "./types";

export const PINNED_CANVAS_FONT = {
  family: "Noto Sans CJK SC",
  version: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
  sha256: "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
  url: "/static/canvas/fonts/NotoSansCJKsc-Regular.otf",
} as const;

interface FontResponse {
  ok: boolean;
  arrayBuffer(): Promise<ArrayBuffer>;
}

export interface LoadPinnedCanvasFontOptions {
  fetcher?: (url: string, init: RequestInit) => Promise<FontResponse>;
  digest?: (bytes: ArrayBuffer) => Promise<string>;
  register?: (bytes: ArrayBuffer) => Promise<void>;
}

function hex(bytes: ArrayBuffer): string {
  return [...new Uint8Array(bytes)]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("");
}

async function digestSha256(bytes: ArrayBuffer): Promise<string> {
  return hex(await crypto.subtle.digest("SHA-256", bytes));
}

async function registerFont(bytes: ArrayBuffer): Promise<void> {
  const face = new FontFace(PINNED_CANVAS_FONT.family, bytes);
  const loaded = await face.load();
  document.fonts.add(loaded);
}

export async function loadPinnedCanvasFont({
  fetcher = (url, init) => fetch(url, init),
  digest = digestSha256,
  register = registerFont,
}: LoadPinnedCanvasFontOptions = {}): Promise<void> {
  const response = await fetcher(PINNED_CANVAS_FONT.url, { cache: "force-cache" });
  if (!response.ok) {
    throw new Error("固定画布字体不可用");
  }
  const bytes = await response.arrayBuffer();
  if ((await digest(bytes)) !== PINNED_CANVAS_FONT.sha256) {
    throw new Error("固定画布字体校验失败");
  }
  await register(bytes);
}

const BASELINE_TOP_EM = {
  top: 0,
  middle: -0.5,
  bottom: -1,
  alphabetic: -0.8,
} as const;

export function lineTopFromAnchor(
  y: number,
  fontSize: number,
  baseline: TextSnapshot["baseline"],
): number {
  if (!Number.isInteger(fontSize) || fontSize <= 0) {
    throw new Error("画布字号必须为正整数");
  }
  return y + fontSize * BASELINE_TOP_EM[baseline];
}

export function isCodePointLetterSpacingSafe(text: string): boolean {
  for (const character of text) {
    const codepoint = character.codePointAt(0);
    if (
      codepoint === undefined
      || codepoint > 0xffff
      || codepoint === 0x200d
      || (codepoint >= 0xfe00 && codepoint <= 0xfe0f)
      || /\p{Mark}/u.test(character)
    ) return false;
  }
  return true;
}

export function patchTextLineHeight(
  snapshot: TextSnapshot,
  lineHeight: number,
): TextLayerPatch & { lines: TextSnapshot["lines"] } {
  if (!Number.isFinite(lineHeight) || lineHeight <= 0) {
    throw new Error("画布行距必须为正数");
  }
  const firstY = snapshot.lines[0]?.y;
  return {
    lineHeight,
    lines: snapshot.lines.map((line, index) => ({
      ...line,
      y: firstY === undefined
        ? line.y
        : firstY + index * snapshot.fontSize * lineHeight,
    })),
  };
}

export function patchTextContentWithoutReflow(
  snapshot: TextSnapshot,
  content: string,
): TextLayerPatch {
  if (snapshot.lines.length === 0) {
    if (content === "") return { content, lines: [] };
    throw new Error("文字行数变化需要逐行设置位置和宽度");
  }
  const texts = content.split(/\r?\n/);
  if (texts.length !== snapshot.lines.length) {
    throw new Error("文字行数变化需要逐行设置位置和宽度");
  }
  return {
    content,
    lines: snapshot.lines.map((line, index) => ({
      ...line,
      text: texts[index] ?? "",
    })),
  };
}
