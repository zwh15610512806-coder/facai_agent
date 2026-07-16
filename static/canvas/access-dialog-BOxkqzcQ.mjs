//#region frontend/canvas/src/api/generations.ts
async function e(e, t) {
	let n = [], r = /* @__PURE__ */ new Set(), i = null;
	do {
		let a = await e.listResultVersions(t, void 0, i);
		if (!a.ok) return a;
		if (n.push(...a.value.items), i = a.value.nextCursor, i !== null && (r.has(i) || r.size >= 1e3)) return {
			ok: !1,
			kind: "server",
			message: "结果版本分页响应无效"
		};
		i !== null && r.add(i);
	} while (i !== null);
	return {
		ok: !0,
		value: n
	};
}
function t(e, t) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error(`${t} must be an object`);
	return e;
}
function n(e, t, n) {
	let r = Object.keys(e).sort(), i = [...t].sort();
	if (r.length !== i.length || r.some((e, t) => e !== i[t])) throw Error(`${n} fields do not match the Canvas contract`);
}
function r(e, t) {
	if (typeof e != "string" || e.length === 0) throw Error(`${t} must be a string`);
	return e;
}
function i(e, t, n = 0) {
	if (typeof e != "number" || !Number.isInteger(e) || e < n) throw Error(`${t} must be an integer`);
	return e;
}
function a(e, t) {
	return e === null ? null : r(e, t);
}
function o(e, t) {
	return typeof e == "object" && e && "detail" in e && typeof e.detail == "string" ? e.detail : t;
}
function s(e, t) {
	return e === 401 ? {
		ok: !1,
		kind: "unauthorized",
		message: "需要解锁付费生成功能"
	} : e === 409 || e === 503 || e === 507 ? {
		ok: !1,
		kind: "busy",
		message: o(t, "生成服务暂时不可用")
	} : {
		ok: !1,
		kind: "server",
		message: o(t, `生成请求失败 (${e})`)
	};
}
function c(e) {
	let r = t(e, "access status");
	if (n(r, ["configured", "locked"], "access status"), typeof r.configured != "boolean" || typeof r.locked != "boolean") throw Error("access status fields must be boolean");
	return {
		configured: r.configured,
		locked: r.locked
	};
}
function l(e) {
	let o = t(e, "result version");
	if (n(o, [
		"versionId",
		"generationId",
		"itemId",
		"attemptId",
		"boardId",
		"outputType",
		"skuId",
		"backgroundAssetId",
		"backgroundPreviewAssetId",
		"composedAssetId",
		"composedPreviewAssetId",
		"width",
		"height",
		"modelProfileId",
		"modelDisplayName",
		"modelConfigVersion",
		"createdAt"
	], "result version"), o.outputType !== "main" && o.outputType !== "sku" && o.outputType !== "detail") throw Error("result version.outputType is unsupported");
	return {
		versionId: r(o.versionId, "result version.versionId"),
		generationId: r(o.generationId, "result version.generationId"),
		itemId: r(o.itemId, "result version.itemId"),
		attemptId: r(o.attemptId, "result version.attemptId"),
		boardId: r(o.boardId, "result version.boardId"),
		outputType: o.outputType,
		skuId: a(o.skuId, "result version.skuId"),
		backgroundAssetId: r(o.backgroundAssetId, "result version.backgroundAssetId"),
		backgroundPreviewAssetId: r(o.backgroundPreviewAssetId, "result version.backgroundPreviewAssetId"),
		composedAssetId: r(o.composedAssetId, "result version.composedAssetId"),
		composedPreviewAssetId: r(o.composedPreviewAssetId, "result version.composedPreviewAssetId"),
		width: i(o.width, "result version.width", 1),
		height: i(o.height, "result version.height", 1),
		modelProfileId: r(o.modelProfileId, "result version.modelProfileId"),
		modelDisplayName: r(o.modelDisplayName, "result version.modelDisplayName"),
		modelConfigVersion: i(o.modelConfigVersion, "result version.modelConfigVersion", 1),
		createdAt: r(o.createdAt, "result version.createdAt")
	};
}
function u({ apiBase: e, fetcher: i = (e, t) => fetch(e, t) }) {
	let o = e.replace(/\/+$/, ""), u = async (e, t) => {
		let n;
		try {
			n = await i(e, t);
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError") throw e;
			return {
				ok: !1,
				kind: "offline",
				message: "网络不可用，请检查连接后重试"
			};
		}
		let r = null;
		try {
			r = await n.json();
		} catch {}
		return n.ok ? {
			response: n,
			body: r
		} : s(n.status, r);
	};
	return {
		create: async (e, n, i) => {
			let a = await u(`${o}/projects/${encodeURIComponent(e)}/generations`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"Idempotency-Key": i
				},
				body: JSON.stringify(n)
			});
			if ("ok" in a) return a;
			try {
				return {
					ok: !0,
					value: { id: r(t(a.body, "generation").id, "generation.id") }
				};
			} catch {
				return {
					ok: !1,
					kind: "server",
					message: "生成服务返回了无效响应"
				};
			}
		},
		accessStatus: async () => {
			let e = await u(`${o}/access/status`, { method: "GET" });
			if ("ok" in e) return e;
			try {
				return {
					ok: !0,
					value: c(e.body)
				};
			} catch {
				return {
					ok: !1,
					kind: "server",
					message: "访问状态响应无效"
				};
			}
		},
		unlock: async (e) => {
			let t = await u(`${o}/access/unlock`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ token: e })
			});
			if ("ok" in t) return t;
			try {
				return {
					ok: !0,
					value: c(t.body)
				};
			} catch {
				return {
					ok: !1,
					kind: "server",
					message: "解锁服务返回了无效响应"
				};
			}
		},
		listResultVersions: async (e, r, i) => {
			let s = new URLSearchParams();
			r !== void 0 && s.set("boardId", r), i != null && s.set("cursor", i);
			let c = s.size === 0 ? "" : `?${s.toString()}`, d = await u(`${o}/projects/${encodeURIComponent(e)}/result-versions${c}`, { method: "GET" });
			if ("ok" in d) return d;
			try {
				let e = t(d.body, "result versions");
				if (n(e, ["items", "nextCursor"], "result versions"), !Array.isArray(e.items)) throw Error("result versions.items must be an array");
				return {
					ok: !0,
					value: {
						items: e.items.map(l),
						nextCursor: a(e.nextCursor, "result versions.nextCursor")
					}
				};
			} catch {
				return {
					ok: !1,
					kind: "server",
					message: "结果版本响应无效"
				};
			}
		}
	};
}
//#endregion
//#region frontend/canvas/src/api/providers.ts
function d(e, t) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error(`${t} must be an object`);
	return e;
}
function f(e, t, n) {
	let r = Object.keys(e).sort(), i = [...t].sort();
	if (r.length !== i.length || r.some((e, t) => e !== i[t])) throw Error(`${n} fields do not match the Canvas contract`);
}
function p(e, t) {
	if (typeof e != "string" || e.length === 0) throw Error(`${t} must be a string`);
	return e;
}
function m(e, t) {
	return e === null ? null : p(e, t);
}
function h(e, t, n = 0) {
	if (typeof e != "number" || !Number.isInteger(e) || e < n) throw Error(`${t} must be an integer >= ${n}`);
	return e;
}
function g(e, t) {
	return e === null ? null : h(e, t);
}
function _(e, t) {
	if (e === "available" || e === "disabled" || e === "missing_credential" || e === "invalid_configuration" || e === "unsupported_local_reference") return e;
	throw Error(`${t} is unsupported`);
}
function v(e, t) {
	if (!Array.isArray(e) || e.some((e) => typeof e != "string" || e.length === 0)) throw Error(`${t} must be a string array`);
	return [...e];
}
function y(e, t) {
	return e === null ? null : d(e, t);
}
function b(e, t) {
	let n = d(e, "model.capabilities");
	f(n, [
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
	let r = (e, t) => {
		if (typeof e != "boolean") throw Error(`${t} must be boolean`);
		return e;
	}, i = n.reference_transfer;
	if (i !== "none" && i !== "bytes" && i !== "base64" && i !== "public_url") throw Error("model.capabilities.reference_transfer is unsupported");
	let a = n.protocol;
	if (a !== "sync" && a !== "async" && a !== "both") throw Error("model.capabilities.protocol is unsupported");
	return {
		textToImage: r(n.text_to_image, "model.capabilities.text_to_image"),
		imageToImage: r(n.image_to_image, "model.capabilities.image_to_image"),
		maskEdit: r(n.mask_edit, "model.capabilities.mask_edit"),
		allowedRatios: v(n.allowed_ratios, "model.capabilities.allowed_ratios"),
		allowedSizes: v(n.allowed_sizes, "model.capabilities.allowed_sizes"),
		minWidth: g(n.min_width, "model.capabilities.min_width"),
		maxWidth: g(n.max_width, "model.capabilities.max_width"),
		minHeight: g(n.min_height, "model.capabilities.min_height"),
		maxHeight: g(n.max_height, "model.capabilities.max_height"),
		maxQuantity: h(n.max_quantity, "model.capabilities.max_quantity", 1),
		maxReferenceImages: h(n.max_reference_images, "model.capabilities.max_reference_images", 0),
		referenceTransfer: i,
		protocol: a,
		supportsCancel: r(n.supports_cancel, "model.capabilities.supports_cancel"),
		supportsIdempotency: r(n.supports_idempotency, "model.capabilities.supports_idempotency"),
		supportsIdempotencyLookup: r(n.supports_idempotency_lookup, "model.capabilities.supports_idempotency_lookup"),
		concurrencyLimit: h(n.concurrency_limit, "model.capabilities.concurrency_limit", 1),
		priceMetadata: t
	};
}
function x(e) {
	let t = d(e, "provider");
	if (f(t, [
		"id",
		"name",
		"enabled",
		"availability",
		"availabilityReason",
		"configVersion"
	], "provider"), typeof t.enabled != "boolean") throw Error("provider.enabled must be boolean");
	return {
		id: p(t.id, "provider.id"),
		name: p(t.name, "provider.name"),
		enabled: t.enabled,
		availability: _(t.availability, "provider.availability"),
		availabilityReason: m(t.availabilityReason, "provider.availabilityReason"),
		configVersion: h(t.configVersion, "provider.configVersion", 1)
	};
}
function S(e) {
	let t = d(e, "model");
	if (f(t, [
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
	], "model"), typeof t.enabled != "boolean") throw Error("model.enabled must be boolean");
	let n = y(t.priceMetadata, "model.priceMetadata");
	return {
		id: p(t.id, "model.id"),
		providerId: p(t.providerId, "model.providerId"),
		modelId: p(t.modelId, "model.modelId"),
		displayName: p(t.displayName, "model.displayName"),
		enabled: t.enabled,
		availability: _(t.availability, "model.availability"),
		availabilityReason: m(t.availabilityReason, "model.availabilityReason"),
		configVersion: h(t.configVersion, "model.configVersion", 1),
		capabilities: b(t.capabilities, n),
		priceMetadata: n
	};
}
function C(e) {
	return {
		ok: !1,
		kind: "server",
		message: `模型目录请求失败 (${e})`
	};
}
function w(e) {
	return e === 401 ? {
		ok: !1,
		kind: "unauthorized",
		message: "需要解锁提供方管理功能"
	} : e === 503 ? {
		ok: !1,
		kind: "unconfigured",
		message: "服务器未配置 Canvas 访问令牌"
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
function T(e) {
	let t = d(e, "provider write response");
	if (f(t, [
		"id",
		"adapterType",
		"name",
		"baseUrl",
		"authType",
		"enabled",
		"configVersion",
		"credentialConfigured",
		"credentialHint"
	], "provider write response"), typeof t.enabled != "boolean" || typeof t.credentialConfigured != "boolean") throw Error("provider write response has invalid booleans");
	return {
		id: p(t.id, "provider write response.id"),
		adapterType: p(t.adapterType, "provider write response.adapterType"),
		name: p(t.name, "provider write response.name"),
		baseUrl: p(t.baseUrl, "provider write response.baseUrl"),
		authType: p(t.authType, "provider write response.authType"),
		enabled: t.enabled,
		configVersion: h(t.configVersion, "provider write response.configVersion", 1),
		credentialConfigured: t.credentialConfigured,
		credentialHint: m(t.credentialHint, "provider write response.credentialHint")
	};
}
function E(e) {
	let t = d(e, "model profile write response");
	if (f(t, [
		"id",
		"providerId",
		"modelId",
		"displayName",
		"enabled",
		"configVersion"
	], "model profile write response"), typeof t.enabled != "boolean") throw Error("model profile write response has invalid enabled flag");
	return {
		id: p(t.id, "model profile write response.id"),
		providerId: p(t.providerId, "model profile write response.providerId"),
		modelId: p(t.modelId, "model profile write response.modelId"),
		displayName: p(t.displayName, "model profile write response.displayName"),
		enabled: t.enabled,
		configVersion: h(t.configVersion, "model profile write response.configVersion", 1)
	};
}
function D(e) {
	let t = d(e, "provider probe response");
	if (f(t, ["status", "paidProbeRequired"], "provider probe response"), t.status !== "configuration_ready" && t.status !== "disabled" && t.status !== "missing_credential") throw Error("provider probe response status is invalid");
	if (typeof t.paidProbeRequired != "boolean") throw Error("provider probe response paidProbeRequired is invalid");
	return {
		status: t.status,
		paidProbeRequired: t.paidProbeRequired
	};
}
function O({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
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
		} : C(r.status);
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
		if (!i.ok) return w(i.status);
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
					value: t.value.map(x)
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
				let i = t.value.map(x), a = await Promise.all(i.map(async (t) => {
					let i = await r(`${n}/model-providers/${encodeURIComponent(t.id)}/models`, e);
					if (!i.ok) return i;
					if (!Array.isArray(i.value)) throw Error("model catalog must be an array");
					let a = i.value.map(S);
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
		createProvider: (e) => i(`${n}/model-providers`, e, T),
		createModelProfile: (e, t) => i(`${n}/model-providers/${encodeURIComponent(e)}/models`, t, E),
		probeProvider: (e, t) => i(`${n}/model-providers/${encodeURIComponent(e)}/test`, { allowPaidProbe: t }, D)
	};
}
//#endregion
//#region frontend/canvas/src/domain/user-message.ts
var k = [
	[/network|fetch|connection|offline/i, "网络连接失败，请检查网络后重试"],
	[/timeout|timed out/i, "请求超时，请稍后重试"],
	[/credential|api[ -]?key|secret/i, "尚未配置服务器端模型凭据"],
	[/unauthori[sz]ed|forbidden|access token|locked/i, "访问凭证无效或已过期，请重新解锁"],
	[/not found|404/i, "请求的资源不存在，请刷新后重试"],
	[/conflict|revision/i, "项目版本有冲突，请刷新后重试"],
	[/storage|capacity|disk|space/i, "存储空间不足，请清理空间后重试"],
	[/private network|loopback|localhost|ssrf/i, "当前地址不符合网络安全限制，请检查 Base URL"]
];
function A(e, t = "操作失败，请稍后重试") {
	let n = typeof e == "string" ? e.trim() : "";
	if (n === "") return t;
	if (/\p{Script=Han}/u.test(n)) return n;
	for (let [e, t] of k) if (e.test(n)) return t;
	return t;
}
//#endregion
//#region frontend/canvas/src/domain/providers.ts
var j = [
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
function M(e, t) {
	let n = (e, t) => t === 0 ? e : n(t, e % t), r = n(e, t);
	return `${e / r}:${t / r}`;
}
function N(e, t) {
	let n = [], r = e.capabilities;
	if (!e.enabled || e.availability !== "available") return n.push(A(e.availabilityReason, "模型当前不可用")), n;
	let i = t.quantity;
	i != null && i > r.maxQuantity && n.push(`单次最多支持 ${r.maxQuantity} 张`);
	let a = t.referenceCount ?? 0;
	a > 0 && (!r.imageToImage || r.maxReferenceImages < a || r.referenceTransfer === "none") && n.push("不支持当前产品参考图"), t.requiresMask && !r.maskEdit && n.push("不支持蒙版编辑");
	let o = t.width, s = t.height;
	if (o != null && s != null) {
		let e = `${o}x${s}`;
		(r.allowedSizes.length > 0 && !r.allowedSizes.includes(e) || r.allowedRatios.length > 0 && !r.allowedRatios.includes(M(o, s)) || r.minWidth !== null && o < r.minWidth || r.maxWidth !== null && o > r.maxWidth || r.minHeight !== null && s < r.minHeight || r.maxHeight !== null && s > r.maxHeight) && n.push("不支持当前尺寸或比例");
	}
	return n;
}
//#endregion
//#region frontend/canvas/src/components/access-dialog.ts
function P() {
	let e = document.createElement("dialog");
	e.className = "canvas-access-dialog";
	let t = document.createElement("form"), n = document.createElement("h2");
	n.textContent = "解锁付费生成";
	let r = document.createElement("p");
	r.textContent = "令牌仅用于本次解锁付费操作；在非本机 HTTP 环境请使用可信局域网与 HTTPS 反向代理。";
	let i = document.createElement("input");
	i.type = "password", i.autocomplete = "off", i.setAttribute("aria-label", "访问令牌");
	let a = document.createElement("p"), o = document.createElement("button");
	o.type = "submit", o.textContent = "解锁并生成";
	let s = document.createElement("button");
	s.type = "button", s.textContent = "取消", t.append(n, r, i, a, o, s), e.append(t), s.addEventListener("click", () => e.close());
	let c = null;
	return t.addEventListener("submit", (t) => {
		t.preventDefault(), !(c === null || i.value === "") && (o.disabled = !0, c(i.value).then((t) => {
			o.disabled = !1, t === null ? e.close() : a.textContent = t;
		}).catch(() => {
			o.disabled = !1, a.textContent = "解锁失败，请重试";
		}));
	}), {
		element: e,
		open: (t) => {
			c = t, a.textContent = "", i.value = "", e.showModal(), i.focus();
		}
	};
}
//#endregion
export { O as a, A as i, j as n, u as o, N as r, e as s, P as t };
