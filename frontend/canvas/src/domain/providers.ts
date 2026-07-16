import { canvasUserMessage } from "./user-message";

/** Shared public model catalog contract mirrored from the Canvas API. */
export type ProviderAvailability =
  | "available"
  | "disabled"
  | "missing_credential"
  | "invalid_configuration"
  | "unsupported_local_reference";

/** Deliberately closed: no ComfyUI or arbitrary local-weight execution. */
export type CanvasProviderAdapterType = "seedream" | "openai_images" | "declarative_http";

export interface ProviderAdapterChoice {
  type: CanvasProviderAdapterType;
  label: string;
  description: string;
  builtIn: boolean;
}

export const PROVIDER_ADAPTER_CHOICES: readonly ProviderAdapterChoice[] = [
  { type: "seedream", label: "Seedream 5.0 Pro", description: "服务器内置受管模型", builtIn: true },
  { type: "openai_images", label: "OpenAI Images 兼容", description: "受控 OpenAI Images API", builtIn: false },
  { type: "declarative_http", label: "通用 HTTP 图像 API", description: "受限 JSON 或 Multipart 协议", builtIn: false },
];

export interface ModelCapabilities {
  textToImage: boolean;
  imageToImage: boolean;
  maskEdit: boolean;
  allowedRatios: string[];
  allowedSizes: string[];
  minWidth: number | null;
  maxWidth: number | null;
  minHeight: number | null;
  maxHeight: number | null;
  maxQuantity: number;
  maxReferenceImages: number;
  referenceTransfer: "none" | "bytes" | "base64" | "public_url";
  protocol: "sync" | "async" | "both";
  supportsCancel: boolean;
  supportsIdempotency: boolean;
  supportsIdempotencyLookup: boolean;
  concurrencyLimit: number;
  priceMetadata: Record<string, unknown> | null;
}

export interface ModelProfile {
  id: string;
  providerId: string;
  modelId: string;
  displayName: string;
  enabled: boolean;
  availability: ProviderAvailability;
  availabilityReason: string | null;
  configVersion: number;
  capabilities: ModelCapabilities;
  priceMetadata: Record<string, unknown> | null;
}

export interface ProviderProfile {
  id: string;
  name: string;
  enabled: boolean;
  availability: ProviderAvailability;
  availabilityReason: string | null;
  configVersion: number;
}

export interface ModelCapabilityRequirements {
  width?: number | null;
  height?: number | null;
  quantity?: number | null;
  referenceCount?: number;
  requiresMask?: boolean;
}

function ratio(width: number, height: number): string {
  const gcd = (left: number, right: number): number => right === 0 ? left : gcd(right, left % right);
  const divisor = gcd(width, height);
  return `${width / divisor}:${height / divisor}`;
}

/** Report conflicts without clearing the user's stored output configuration. */
export function modelCapabilityConflicts(
  model: ModelProfile,
  requirements: ModelCapabilityRequirements,
): string[] {
  const issues: string[] = [];
  const cap = model.capabilities;
  if (!model.enabled || model.availability !== "available") {
    issues.push(canvasUserMessage(model.availabilityReason, "模型当前不可用"));
    return issues;
  }
  const quantity = requirements.quantity;
  if (quantity !== null && quantity !== undefined && quantity > cap.maxQuantity) {
    issues.push(`单次最多支持 ${cap.maxQuantity} 张`);
  }
  const references = requirements.referenceCount ?? 0;
  if (references > 0 && (!cap.imageToImage || cap.maxReferenceImages < references || cap.referenceTransfer === "none")) {
    issues.push("不支持当前产品参考图");
  }
  if (requirements.requiresMask && !cap.maskEdit) {
    issues.push("不支持蒙版编辑");
  }
  const width = requirements.width;
  const height = requirements.height;
  if (width !== null && width !== undefined && height !== null && height !== undefined) {
    const size = `${width}x${height}`;
    if (
      (cap.allowedSizes.length > 0 && !cap.allowedSizes.includes(size)) ||
      (cap.allowedRatios.length > 0 && !cap.allowedRatios.includes(ratio(width, height))) ||
      (cap.minWidth !== null && width < cap.minWidth) ||
      (cap.maxWidth !== null && width > cap.maxWidth) ||
      (cap.minHeight !== null && height < cap.minHeight) ||
      (cap.maxHeight !== null && height > cap.maxHeight)
    ) {
      issues.push("不支持当前尺寸或比例");
    }
  }
  return issues;
}
