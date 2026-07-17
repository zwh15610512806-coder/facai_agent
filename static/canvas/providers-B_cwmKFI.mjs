//#region frontend/canvas/src/api/providers.ts
function e(e, t) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error(`${t} must be an object`);
	return e;
}
function t(e, t, n) {
	let r = Object.keys(e).sort(), i = [...t].sort();
	if (r.length !== i.length || r.some((e, t) => e !== i[t])) throw Error(`${n} fields do not match the Canvas contract`);
}
function n(e, t) {
	if (typeof e != "string" || e.length === 0) throw Error(`${t} must be a string`);
	return e;
}
function r(e, t) {
	return e === null ? null : n(e, t);
}
function i(e, t, n = 0) {
	if (typeof e != "number" || !Number.isInteger(e) || e < n) throw Error(`${t} must be an integer >= ${n}`);
	return e;
}
function a(e, t) {
	return e === null ? null : i(e, t);
}
function o(e, t) {
	if (e === "available" || e === "disabled" || e === "missing_credential" || e === "invalid_configuration" || e === "unsupported_local_reference") return e;
	throw Error(`${t} is unsupported`);
}
function s(e, t) {
	if (!Array.isArray(e) || e.some((e) => typeof e != "string" || e.length === 0)) throw Error(`${t} must be a string array`);
	return [...e];
}
function c(t, n) {
	return t === null ? null : e(t, n);
}
function l(n, r) {
	let o = e(n, "model.capabilities");
	t(o, [
		"text_to_image",
		"image_to_image",
		"mask_edit",
		"allowed_ratios",
		"allowed_sizes",
		"min_width",
		"max_width",
		"min_height",
		"max_height",
		"max_quantity",
		"max_reference_images",
		"reference_transfer",
		"protocol",
		"supports_cancel",
		"supports_idempotency",
		"supports_idempotency_lookup",
		"concurrency_limit"
	], "model.capabilities");
	let c = (e, t) => {
		if (typeof e != "boolean") throw Error(`${t} must be boolean`);
		return e;
	}, l = o.reference_transfer;
	if (l !== "none" && l !== "bytes" && l !== "base64" && l !== "public_url") throw Error("model.capabilities.reference_transfer is unsupported");
	let u = o.protocol;
	if (u !== "sync" && u !== "async" && u !== "both") throw Error("model.capabilities.protocol is unsupported");
	return {
		textToImage: c(o.text_to_image, "model.capabilities.text_to_image"),
		imageToImage: c(o.image_to_image, "model.capabilities.image_to_image"),
		maskEdit: c(o.mask_edit, "model.capabilities.mask_edit"),
		allowedRatios: s(o.allowed_ratios, "model.capabilities.allowed_ratios"),
		allowedSizes: s(o.allowed_sizes, "model.capabilities.allowed_sizes"),
		minWidth: a(o.min_width, "model.capabilities.min_width"),
		maxWidth: a(o.max_width, "model.capabilities.max_width"),
		minHeight: a(o.min_height, "model.capabilities.min_height"),
		maxHeight: a(o.max_height, "model.capabilities.max_height"),
		maxQuantity: i(o.max_quantity, "model.capabilities.max_quantity", 1),
		maxReferenceImages: i(o.max_reference_images, "model.capabilities.max_reference_images", 0),
		referenceTransfer: l,
		protocol: u,
		supportsCancel: c(o.supports_cancel, "model.capabilities.supports_cancel"),
		supportsIdempotency: c(o.supports_idempotency, "model.capabilities.supports_idempotency"),
		supportsIdempotencyLookup: c(o.supports_idempotency_lookup, "model.capabilities.supports_idempotency_lookup"),
		concurrencyLimit: i(o.concurrency_limit, "model.capabilities.concurrency_limit", 1),
		priceMetadata: r
	};
}
function u(a) {
	let s = e(a, "provider");
	if (t(s, [
		"id",
		"name",
		"enabled",
		"availability",
		"availabilityReason",
		"configVersion"
	], "provider"), typeof s.enabled != "boolean") throw Error("provider.enabled must be boolean");
	return {
		id: n(s.id, "provider.id"),
		name: n(s.name, "provider.name"),
		enabled: s.enabled,
		availability: o(s.availability, "provider.availability"),
		availabilityReason: r(s.availabilityReason, "provider.availabilityReason"),
		configVersion: i(s.configVersion, "provider.configVersion", 1)
	};
}
function d(a) {
	let s = e(a, "model");
	if (t(s, [
		"id",
		"providerId",
		"modelId",
		"displayName",
		"enabled",
		"availability",
		"availabilityReason",
		"configVersion",
		"capabilities",
		"priceMetadata"
	], "model"), typeof s.enabled != "boolean") throw Error("model.enabled must be boolean");
	let u = c(s.priceMetadata, "model.priceMetadata");
	return {
		id: n(s.id, "model.id"),
		providerId: n(s.providerId, "model.providerId"),
		modelId: n(s.modelId, "model.modelId"),
		displayName: n(s.displayName, "model.displayName"),
		enabled: s.enabled,
		availability: o(s.availability, "model.availability"),
		availabilityReason: r(s.availabilityReason, "model.availabilityReason"),
		configVersion: i(s.configVersion, "model.configVersion", 1),
		capabilities: l(s.capabilities, u),
		priceMetadata: u
	};
}
function f(e) {
	return {
		ok: !1,
		kind: "server",
		message: `模型目录请求失败 (${e})`
	};
}
function p(e) {
	return e === 401 ? {
		ok: !1,
		kind: "unauthorized",
		message: "需要解锁提供方管理功能"
	} : e === 503 ? {
		ok: !1,
		kind: "unconfigured",
		message: "服务器尚未配置图像模型服务"
	} : e === 422 ? {
		ok: !1,
		kind: "validation",
		message: "提供方配置未通过安全校验"
	} : {
		ok: !1,
		kind: "server",
		message: `提供方管理请求失败 (${e})`
	};
}
function m(a) {
	let o = e(a, "provider write response");
	if (t(o, [
		"id",
		"adapterType",
		"name",
		"baseUrl",
		"authType",
		"enabled",
		"configVersion",
		"credentialConfigured",
		"credentialHint"
	], "provider write response"), typeof o.enabled != "boolean" || typeof o.credentialConfigured != "boolean") throw Error("provider write response has invalid booleans");
	return {
		id: n(o.id, "provider write response.id"),
		adapterType: n(o.adapterType, "provider write response.adapterType"),
		name: n(o.name, "provider write response.name"),
		baseUrl: n(o.baseUrl, "provider write response.baseUrl"),
		authType: n(o.authType, "provider write response.authType"),
		enabled: o.enabled,
		configVersion: i(o.configVersion, "provider write response.configVersion", 1),
		credentialConfigured: o.credentialConfigured,
		credentialHint: r(o.credentialHint, "provider write response.credentialHint")
	};
}
function h(r) {
	let a = e(r, "model profile write response");
	if (t(a, [
		"id",
		"providerId",
		"modelId",
		"displayName",
		"enabled",
		"configVersion"
	], "model profile write response"), typeof a.enabled != "boolean") throw Error("model profile write response has invalid enabled flag");
	return {
		id: n(a.id, "model profile write response.id"),
		providerId: n(a.providerId, "model profile write response.providerId"),
		modelId: n(a.modelId, "model profile write response.modelId"),
		displayName: n(a.displayName, "model profile write response.displayName"),
		enabled: a.enabled,
		configVersion: i(a.configVersion, "model profile write response.configVersion", 1)
	};
}
function g(n) {
	let r = e(n, "provider probe response");
	if (t(r, ["status", "paidProbeRequired"], "provider probe response"), r.status !== "configuration_ready" && r.status !== "disabled" && r.status !== "missing_credential") throw Error("provider probe response status is invalid");
	if (typeof r.paidProbeRequired != "boolean") throw Error("provider probe response paidProbeRequired is invalid");
	return {
		status: r.status,
		paidProbeRequired: r.paidProbeRequired
	};
}
function _({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
	let n = e.replace(/\/+$/, ""), r = async (e, n) => {
		let r;
		try {
			r = await t(e, { signal: n });
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError") throw e;
			return {
				ok: !1,
				kind: "offline",
				message: "模型目录网络不可用"
			};
		}
		let i = null;
		try {
			i = await r.json();
		} catch {}
		return r.ok ? {
			ok: !0,
			value: i
		} : f(r.status);
	}, i = async (e, n, r) => {
		let i;
		try {
			i = await t(e, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(n)
			});
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError") throw e;
			return {
				ok: !1,
				kind: "offline",
				message: "提供方管理网络不可用"
			};
		}
		let a = null;
		try {
			a = await i.json();
		} catch {}
		if (!i.ok) return p(i.status);
		try {
			return {
				ok: !0,
				value: r(a)
			};
		} catch {
			return {
				ok: !1,
				kind: "server",
				message: "提供方管理响应无效"
			};
		}
	};
	return {
		loadProviders: async (e) => {
			let t = await r(`${n}/model-providers`, e);
			if (!t.ok) return t;
			try {
				if (!Array.isArray(t.value)) throw Error("provider catalog must be an array");
				return {
					ok: !0,
					value: t.value.map(u)
				};
			} catch (e) {
				return {
					ok: !1,
					kind: "server",
					message: e instanceof Error ? `无效提供方目录：${e.message}` : "无效提供方目录"
				};
			}
		},
		loadCatalog: async (e) => {
			let t = await r(`${n}/model-providers`, e);
			if (!t.ok) return t;
			try {
				if (!Array.isArray(t.value)) throw Error("provider catalog must be an array");
				let i = t.value.map(u), a = await Promise.all(i.map(async (t) => {
					let i = await r(`${n}/model-providers/${encodeURIComponent(t.id)}/models`, e);
					if (!i.ok) return i;
					if (!Array.isArray(i.value)) throw Error("model catalog must be an array");
					let a = i.value.map(d);
					if (a.some((e) => e.providerId !== t.id)) throw Error("model catalog belongs to another provider");
					return {
						ok: !0,
						value: a
					};
				})), o = a.find((e) => !e.ok);
				return o !== void 0 && !o.ok ? o : {
					ok: !0,
					value: a.flatMap((e) => e.ok ? e.value : [])
				};
			} catch (e) {
				return {
					ok: !1,
					kind: "server",
					message: e instanceof Error ? `无效模型目录：${e.message}` : "无效模型目录"
				};
			}
		},
		createProvider: (e) => i(`${n}/model-providers`, e, m),
		createModelProfile: (e, t) => i(`${n}/model-providers/${encodeURIComponent(e)}/models`, t, h),
		probeProvider: (e, t) => i(`${n}/model-providers/${encodeURIComponent(e)}/test`, { allowPaidProbe: t }, g)
	};
}
//#endregion
//#region frontend/canvas/src/domain/user-message.ts
var v = [
	[/network|fetch|connection|offline/i, "网络连接失败，请检查网络后重试"],
	[/timeout|timed out/i, "请求超时，请稍后重试"],
	[/credential|api[ -]?key|secret/i, "尚未配置服务器端模型凭据"],
	[/unauthori[sz]ed|forbidden/i, "请求被服务拒绝，请刷新页面后重试"],
	[/not found|404/i, "请求的资源不存在，请刷新后重试"],
	[/conflict|revision/i, "项目版本有冲突，请刷新后重试"],
	[/storage|capacity|disk|space/i, "存储空间不足，请清理空间后重试"],
	[/private network|loopback|localhost|ssrf/i, "当前地址不符合网络安全限制，请检查 Base URL"]
];
function y(e, t = "操作失败，请稍后重试") {
	let n = typeof e == "string" ? e.trim() : "";
	if (n === "") return t;
	if (/\p{Script=Han}/u.test(n)) return n;
	for (let [e, t] of v) if (e.test(n)) return t;
	return t;
}
//#endregion
//#region frontend/canvas/src/domain/providers.ts
var b = [
	{
		type: "seedream",
		label: "Seedream 5.0 Pro",
		description: "服务器内置受管模型",
		builtIn: !0
	},
	{
		type: "openai_images",
		label: "OpenAI Images 兼容",
		description: "受控 OpenAI Images API",
		builtIn: !1
	},
	{
		type: "declarative_http",
		label: "通用 HTTP 图像 API",
		description: "受限 JSON 或 Multipart 协议",
		builtIn: !1
	}
];
function x(e, t) {
	let n = (e, t) => t === 0 ? e : n(t, e % t), r = n(e, t);
	return `${e / r}:${t / r}`;
}
function S(e, t) {
	let n = [], r = e.capabilities;
	if (!e.enabled || e.availability !== "available") return n.push(y(e.availabilityReason, "模型当前不可用")), n;
	let i = t.quantity;
	i != null && i > r.maxQuantity && n.push(`单次最多支持 ${r.maxQuantity} 张`);
	let a = t.referenceCount ?? 0;
	a > 0 && (!r.imageToImage || r.maxReferenceImages < a || r.referenceTransfer === "none") && n.push("不支持当前产品参考图"), t.requiresMask && !r.maskEdit && n.push("不支持蒙版编辑");
	let o = t.width, s = t.height;
	if (o != null && s != null) {
		let e = `${o}x${s}`;
		(r.allowedSizes.length > 0 && !r.allowedSizes.includes(e) || r.allowedRatios.length > 0 && !r.allowedRatios.includes(x(o, s)) || r.minWidth !== null && o < r.minWidth || r.maxWidth !== null && o > r.maxWidth || r.minHeight !== null && s < r.minHeight || r.maxHeight !== null && s > r.maxHeight) && n.push("不支持当前尺寸或比例");
	}
	return n;
}
//#endregion
export { _ as i, S as n, y as r, b as t };
