import type {
  CompositionLayout,
  NormalizedTransform,
} from "./types";

export interface PixelSize {
  width: number;
  height: number;
}

export interface PixelPlacement extends PixelSize {
  /** Unrotated integer pixel rectangle; rotation is around its center. */
  x: number;
  y: number;
  rotation: number;
}

export const DEFAULT_COMPOSITION_LAYOUT: CompositionLayout = {
  slot: { x: 0.1, y: 0.1, width: 0.8, height: 0.8 },
  anchor: { x: 0.5, y: 0.5 },
  baseline: 0.9,
  relativeProductFraction: 0.8,
  contain: true,
  safeArea: { top: 0.05, right: 0.05, bottom: 0.05, left: 0.05 },
  rotation: 0,
};

function roundSixHalfAwayFromZero(value: number): number {
  if (!Number.isFinite(value)) throw new Error("composition numbers must be finite");
  const sign = value < 0 ? -1 : 1;
  const [coefficient, exponentText] = Math.abs(value).toString().toLowerCase().split("e");
  const [whole, fraction = ""] = coefficient.split(".");
  const digits = BigInt(`${whole}${fraction}`);
  const decimalPlaces = fraction.length - Number(exponentText ?? 0);
  let scaled: bigint;
  if (decimalPlaces <= 6) {
    scaled = digits * (10n ** BigInt(6 - decimalPlaces));
  } else {
    const divisor = 10n ** BigInt(decimalPlaces - 6);
    scaled = digits / divisor;
    if ((digits % divisor) * 2n >= divisor) scaled += 1n;
  }
  const rounded = sign * Number(scaled) / 1_000_000;
  return Object.is(rounded, -0) ? 0 : rounded;
}

function canonicalValue(value: unknown): unknown {
  if (value === null || typeof value === "boolean" || typeof value === "string") {
    return value;
  }
  if (typeof value === "number") {
    return roundSixHalfAwayFromZero(value);
  }
  if (Array.isArray(value)) return value.map(canonicalValue);
  if (typeof value !== "object" || value === null) {
    throw new Error("composition layout contains a non-JSON value");
  }
  return Object.fromEntries(
    Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, canonicalValue(item)]),
  );
}

export function canonicalLayoutJson(layout: CompositionLayout): string {
  return JSON.stringify(canonicalValue(layout));
}

function rightRotate(value: number, amount: number): number {
  return (value >>> amount) | (value << (32 - amount));
}

export function sha256HexBytes(input: Uint8Array): string {
  const bitLength = input.length * 8;
  const paddedLength = Math.ceil((input.length + 9) / 64) * 64;
  const bytes = new Uint8Array(paddedLength);
  bytes.set(input);
  bytes[input.length] = 0x80;
  const view = new DataView(bytes.buffer);
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x1_0000_0000), false);
  view.setUint32(paddedLength - 4, bitLength >>> 0, false);

  const constants = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ]);
  const hash = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  const words = new Uint32Array(64);
  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      words[index] = view.getUint32(offset + index * 4, false);
    }
    for (let index = 16; index < 64; index += 1) {
      const previous = words[index - 15];
      const before = words[index - 2];
      const sigma0 = rightRotate(previous, 7) ^ rightRotate(previous, 18) ^ (previous >>> 3);
      const sigma1 = rightRotate(before, 17) ^ rightRotate(before, 19) ^ (before >>> 10);
      words[index] = (words[index - 16] + sigma0 + words[index - 7] + sigma1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index += 1) {
      const upper1 = rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25);
      const choice = (e & f) ^ (~e & g);
      const temp1 = (h + upper1 + choice + constants[index] + words[index]) >>> 0;
      const upper0 = rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22);
      const majority = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (upper0 + majority) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }
    hash[0] = (hash[0] + a) >>> 0;
    hash[1] = (hash[1] + b) >>> 0;
    hash[2] = (hash[2] + c) >>> 0;
    hash[3] = (hash[3] + d) >>> 0;
    hash[4] = (hash[4] + e) >>> 0;
    hash[5] = (hash[5] + f) >>> 0;
    hash[6] = (hash[6] + g) >>> 0;
    hash[7] = (hash[7] + h) >>> 0;
  }
  return Array.from(hash, (value) => value.toString(16).padStart(8, "0")).join("");
}

function sha256Hex(text: string): string {
  return sha256HexBytes(new TextEncoder().encode(text));
}

export function compositionLayoutHash(layout: CompositionLayout): string {
  return `sha256:${sha256Hex(canonicalLayoutJson(layout))}`;
}

function requirePositiveInteger(size: PixelSize, label: string): void {
  if (
    !Number.isInteger(size.width) ||
    !Number.isInteger(size.height) ||
    size.width <= 0 ||
    size.height <= 0
  ) {
    throw new Error(`${label} size must contain positive integers`);
  }
}

export function mapProductToBoard(
  layout: CompositionLayout,
  sizes: { sourceSize: PixelSize; outputSize: PixelSize },
): PixelPlacement {
  requirePositiveInteger(sizes.sourceSize, "source");
  requirePositiveInteger(sizes.outputSize, "output");
  const { width: sourceWidth, height: sourceHeight } = sizes.sourceSize;
  const { width: outputWidth, height: outputHeight } = sizes.outputSize;
  const slotLeft = layout.slot.x * outputWidth;
  const slotTop = layout.slot.y * outputHeight;
  const slotRight = (layout.slot.x + layout.slot.width) * outputWidth;
  const slotBottom = (layout.slot.y + layout.slot.height) * outputHeight;
  const left = Math.max(slotLeft, layout.safeArea.left * outputWidth);
  const top = Math.max(slotTop, layout.safeArea.top * outputHeight);
  const right = Math.min(slotRight, (1 - layout.safeArea.right) * outputWidth);
  const bottom = Math.min(slotBottom, (1 - layout.safeArea.bottom) * outputHeight);
  if (left >= right || top >= bottom) {
    throw new Error("composition slot does not intersect the safe area");
  }
  const rotation = roundSixHalfAwayFromZero(layout.rotation);
  const angle = (rotation * Math.PI) / 180;
  const cosine = Math.abs(Math.cos(angle));
  const sine = Math.abs(Math.sin(angle));
  const scale = Math.min(
    ((right - left) * layout.relativeProductFraction) /
      (sourceWidth * cosine + sourceHeight * sine),
    ((bottom - top) * layout.relativeProductFraction) /
      (sourceWidth * sine + sourceHeight * cosine),
  );
  const width = Math.max(1, Math.floor(sourceWidth * scale + 1e-9));
  const height = Math.max(1, Math.floor(sourceHeight * scale + 1e-9));
  const rotatedWidth = width * cosine + height * sine;
  const rotatedHeight = width * sine + height * cosine;
  const targetX = slotLeft + (slotRight - slotLeft) * layout.anchor.x;
  const targetY = layout.baseline * outputHeight;
  const centerX = targetX + (0.5 - layout.anchor.x) * width;
  const centerY = targetY + (0.5 - layout.anchor.y) * height;
  const minX = Math.ceil(left + rotatedWidth / 2 - width / 2);
  const maxX = Math.floor(right - rotatedWidth / 2 - width / 2);
  const minY = Math.ceil(top + rotatedHeight / 2 - height / 2);
  const maxY = Math.floor(bottom - rotatedHeight / 2 - height / 2);
  if (minX > maxX || minY > maxY) {
    throw new Error("rotated product cannot fit inside the composition slot");
  }
  return {
    x: Math.min(Math.max(Math.floor(centerX - width / 2 + 0.5), minX), maxX),
    y: Math.min(Math.max(Math.floor(centerY - height / 2 + 0.5), minY), maxY),
    width,
    height,
    rotation,
  };
}

export function compositionTransform(layout: CompositionLayout): NormalizedTransform {
  return {
    x: layout.slot.x + layout.slot.width * layout.anchor.x,
    y: layout.baseline,
    scale: layout.relativeProductFraction,
    rotation: roundSixHalfAwayFromZero(layout.rotation),
  };
}
