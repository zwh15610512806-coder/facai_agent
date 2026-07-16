import { a as e, i as t, o as n, r, s as i, t as a } from "./access-dialog-BOxkqzcQ.mjs";
//#region frontend/canvas/src/domain/composition.ts
var o = {
	slot: {
		x: .1,
		y: .1,
		width: .8,
		height: .8
	},
	anchor: {
		x: .5,
		y: .5
	},
	baseline: .9,
	relativeProductFraction: .8,
	contain: !0,
	safeArea: {
		top: .05,
		right: .05,
		bottom: .05,
		left: .05
	},
	rotation: 0
};
function s(e) {
	if (!Number.isFinite(e)) throw Error("composition numbers must be finite");
	let t = e < 0 ? -1 : 1, [n, r] = Math.abs(e).toString().toLowerCase().split("e"), [i, a = ""] = n.split("."), o = BigInt(`${i}${a}`), s = a.length - Number(r ?? 0), c;
	if (s <= 6) c = o * 10n ** BigInt(6 - s);
	else {
		let e = 10n ** BigInt(s - 6);
		c = o / e, o % e * 2n >= e && (c += 1n);
	}
	let l = t * Number(c) / 1e6;
	return Object.is(l, -0) ? 0 : l;
}
function c(e) {
	if (e === null || typeof e == "boolean" || typeof e == "string") return e;
	if (typeof e == "number") return s(e);
	if (Array.isArray(e)) return e.map(c);
	if (typeof e != "object" || !e) throw Error("composition layout contains a non-JSON value");
	return Object.fromEntries(Object.entries(e).sort(([e], [t]) => e.localeCompare(t)).map(([e, t]) => [e, c(t)]));
}
function l(e) {
	return JSON.stringify(c(e));
}
function u(e, t) {
	return e >>> t | e << 32 - t;
}
function d(e) {
	let t = e.length * 8, n = Math.ceil((e.length + 9) / 64) * 64, r = new Uint8Array(n);
	r.set(e), r[e.length] = 128;
	let i = new DataView(r.buffer);
	i.setUint32(n - 8, Math.floor(t / 4294967296), !1), i.setUint32(n - 4, t >>> 0, !1);
	let a = new Uint32Array([
		1116352408,
		1899447441,
		3049323471,
		3921009573,
		961987163,
		1508970993,
		2453635748,
		2870763221,
		3624381080,
		310598401,
		607225278,
		1426881987,
		1925078388,
		2162078206,
		2614888103,
		3248222580,
		3835390401,
		4022224774,
		264347078,
		604807628,
		770255983,
		1249150122,
		1555081692,
		1996064986,
		2554220882,
		2821834349,
		2952996808,
		3210313671,
		3336571891,
		3584528711,
		113926993,
		338241895,
		666307205,
		773529912,
		1294757372,
		1396182291,
		1695183700,
		1986661051,
		2177026350,
		2456956037,
		2730485921,
		2820302411,
		3259730800,
		3345764771,
		3516065817,
		3600352804,
		4094571909,
		275423344,
		430227734,
		506948616,
		659060556,
		883997877,
		958139571,
		1322822218,
		1537002063,
		1747873779,
		1955562222,
		2024104815,
		2227730452,
		2361852424,
		2428436474,
		2756734187,
		3204031479,
		3329325298
	]), o = new Uint32Array([
		1779033703,
		3144134277,
		1013904242,
		2773480762,
		1359893119,
		2600822924,
		528734635,
		1541459225
	]), s = /* @__PURE__ */ new Uint32Array(64);
	for (let e = 0; e < n; e += 64) {
		for (let t = 0; t < 16; t += 1) s[t] = i.getUint32(e + t * 4, !1);
		for (let e = 16; e < 64; e += 1) {
			let t = s[e - 15], n = s[e - 2], r = u(t, 7) ^ u(t, 18) ^ t >>> 3, i = u(n, 17) ^ u(n, 19) ^ n >>> 10;
			s[e] = s[e - 16] + r + s[e - 7] + i >>> 0;
		}
		let [t, n, r, c, l, d, f, p] = o;
		for (let e = 0; e < 64; e += 1) {
			let i = u(l, 6) ^ u(l, 11) ^ u(l, 25), o = l & d ^ ~l & f, m = p + i + o + a[e] + s[e] >>> 0, h = (u(t, 2) ^ u(t, 13) ^ u(t, 22)) + (t & n ^ t & r ^ n & r) >>> 0;
			p = f, f = d, d = l, l = c + m >>> 0, c = r, r = n, n = t, t = m + h >>> 0;
		}
		o[0] = o[0] + t >>> 0, o[1] = o[1] + n >>> 0, o[2] = o[2] + r >>> 0, o[3] = o[3] + c >>> 0, o[4] = o[4] + l >>> 0, o[5] = o[5] + d >>> 0, o[6] = o[6] + f >>> 0, o[7] = o[7] + p >>> 0;
	}
	return Array.from(o, (e) => e.toString(16).padStart(8, "0")).join("");
}
function f(e) {
	return d(new TextEncoder().encode(e));
}
function p(e) {
	return `sha256:${f(l(e))}`;
}
function m(e) {
	return {
		x: e.slot.x + e.slot.width * e.anchor.x,
		y: e.baseline,
		scale: e.relativeProductFraction,
		rotation: s(e.rotation)
	};
}
//#endregion
//#region frontend/canvas/src/domain/text-layout.ts
var h = {
	family: "Noto Sans CJK SC",
	version: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
	sha256: "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
	url: "/static/canvas/fonts/NotoSansCJKsc-Regular.otf"
};
function g(e) {
	return [...new Uint8Array(e)].map((e) => e.toString(16).padStart(2, "0")).join("");
}
async function _(e) {
	let t = globalThis.crypto?.subtle;
	return t ? g(await t.digest("SHA-256", e)) : d(new Uint8Array(e));
}
async function v(e) {
	let t = await new FontFace(h.family, e).load();
	document.fonts.add(t);
}
async function y({ fetcher: e = (e, t) => fetch(e, t), digest: t = _, register: n = v } = {}) {
	let r = await e(h.url, { cache: "force-cache" });
	if (!r.ok) throw Error("固定画布字体不可用");
	let i = await r.arrayBuffer();
	if (await t(i) !== h.sha256) throw Error("固定画布字体校验失败");
	await n(i);
}
var b = {
	top: 0,
	middle: -.5,
	bottom: -1,
	alphabetic: -.8
};
function x(e, t, n) {
	if (!Number.isInteger(t) || t <= 0) throw Error("画布字号必须为正整数");
	return e + t * b[n];
}
function S(e) {
	for (let t of e) {
		let e = t.codePointAt(0);
		if (e === void 0 || e > 65535 || e === 8205 || e >= 65024 && e <= 65039 || /\p{Mark}/u.test(t)) return !1;
	}
	return !0;
}
function C(e, t) {
	if (!Number.isFinite(t) || t <= 0) throw Error("画布行距必须为正数");
	let n = e.lines[0]?.y;
	return {
		lineHeight: t,
		lines: e.lines.map((r, i) => ({
			...r,
			y: n === void 0 ? r.y : n + i * e.fontSize * t
		}))
	};
}
function w(e, t) {
	if (e.lines.length === 0) {
		if (t === "") return {
			content: t,
			lines: []
		};
		throw Error("文字行数变化需要逐行设置位置和宽度");
	}
	let n = t.split(/\r?\n/);
	if (n.length !== e.lines.length) throw Error("文字行数变化需要逐行设置位置和宽度");
	return {
		content: t,
		lines: e.lines.map((e, t) => ({
			...e,
			text: n[t] ?? ""
		}))
	};
}
//#endregion
//#region frontend/canvas/src/domain/node-ports.ts
var T = /* @__PURE__ */ new Set([
	"main_output",
	"sku_output",
	"detail_output"
]), E = [
	"product_asset",
	"cutout_asset",
	"prompt",
	"composition",
	"text_layer",
	"output_image"
];
function D(e, t, n) {
	switch (n) {
		case "product_asset": return (e === "product_source" || e === "sku_reference") && t === "auto_cutout";
		case "cutout_asset": return e === "auto_cutout" && t === "model_generation";
		case "prompt": return e === "prompt" && t === "model_generation";
		case "background_image": return !1;
		case "composition": return e === "composition_group" && T.has(t);
		case "text_layer": return e === "text_layer" && T.has(t);
		case "output_image": return e === "model_generation" && T.has(t);
	}
}
function O(e, t) {
	return E.filter((n) => D(e, t, n));
}
function ee(e, t, n, r) {
	let i = {
		id: e,
		sourceNodeId: n,
		targetNodeId: r,
		skuId: null
	};
	switch (t) {
		case "product_asset": return {
			...i,
			kind: t,
			sourcePort: "product",
			targetPort: "reference"
		};
		case "cutout_asset": return {
			...i,
			kind: t,
			sourcePort: "cutout",
			targetPort: "reference"
		};
		case "prompt": return {
			...i,
			kind: t,
			sourcePort: "prompt",
			targetPort: "prompt"
		};
		case "background_image": return {
			...i,
			kind: t,
			sourcePort: "image",
			targetPort: "background"
		};
		case "composition": return {
			...i,
			kind: t,
			sourcePort: "composition",
			targetPort: "composition"
		};
		case "text_layer": return {
			...i,
			kind: t,
			sourcePort: "text",
			targetPort: "text"
		};
		case "output_image": return {
			...i,
			kind: t,
			sourcePort: "output",
			targetPort: "input"
		};
	}
}
//#endregion
//#region frontend/canvas/src/domain/validation.ts
var te = 500, ne = 1e3, re = 4e3, k = 1e5, ie = [
	"product_source",
	"sku_reference",
	"auto_cutout",
	"prompt",
	"model_generation",
	"main_output",
	"sku_output",
	"detail_output",
	"text_layer",
	"composition_group",
	"export"
], A = [
	"main",
	"sku",
	"detail"
], ae = {
	product_asset: {
		sourcePort: "product",
		targetPort: "reference"
	},
	cutout_asset: {
		sourcePort: "cutout",
		targetPort: "reference"
	},
	prompt: {
		sourcePort: "prompt",
		targetPort: "prompt"
	},
	background_image: {
		sourcePort: "image",
		targetPort: "background"
	},
	composition: {
		sourcePort: "composition",
		targetPort: "composition"
	},
	text_layer: {
		sourcePort: "text",
		targetPort: "text"
	},
	output_image: {
		sourcePort: "output",
		targetPort: "input"
	}
}, oe = /* @__PURE__ */ new Set([
	"generationhistory",
	"history",
	"objects",
	"resultassetids",
	"resultversions",
	"version",
	"versionhistory",
	"versions"
]), se = /\b[A-Za-z][A-Za-z0-9+.-]*:\/\//, ce = /^[A-Za-z]:[\\/]/, le = class extends Error {
	constructor(e) {
		super(e), this.name = "ProjectValidationError";
	}
};
function j(e, t) {
	throw new le(`${t} at ${e}`);
}
function ue(e, t) {
	if (!(e === null || typeof e == "boolean")) {
		if (typeof e == "number") {
			Number.isFinite(e) || j(t, "JSON numbers must be finite");
			return;
		}
		if (typeof e == "string") {
			let n = e.trim(), r = n.toLowerCase();
			r.startsWith("data:") && j(t, "data URLs are forbidden"), (se.test(n) || r.startsWith("//") || r.startsWith("blob:") || r.startsWith("file:")) && j(t, "remote URLs are forbidden"), (n.startsWith("/") || n.startsWith("\\") || ce.test(n)) && j(t, "absolute paths are forbidden");
			return;
		}
		if (Array.isArray(e)) {
			e.forEach((e, n) => ue(e, `${t}[${n}]`));
			return;
		}
		(typeof e != "object" || e === void 0) && j(t, "non-JSON value is forbidden");
		for (let [n, r] of Object.entries(e)) oe.has(n.toLowerCase()) && j(t, `Fabric marker ${JSON.stringify(n)} is forbidden`), ue(r, `${t}.${n}`);
	}
}
function M(e, t) {
	return (typeof e != "object" || !e || Array.isArray(e)) && j(t, "expected an object"), e;
}
function N(e, t, n) {
	let r = new Set(t);
	for (let t of Object.keys(e)) r.has(t) || j(n, `unknown key ${JSON.stringify(t)}`);
	for (let r of t) Object.hasOwn(e, r) || j(n, `missing key ${JSON.stringify(r)}`);
}
function de(e, t, n) {
	typeof e != "string" && j(t, "expected a string");
	let r = n.trim === !0 ? e.trim() : e;
	return n.allowEmpty !== !0 && r.length === 0 && j(t, "string must not be empty"), r.length > n.maxLength && j(t, `string exceeds ${n.maxLength} characters`), r;
}
function P(e, t) {
	return de(e, t, {
		maxLength: 200,
		trim: !0
	});
}
function F(e, t) {
	return e === null ? null : P(e, t);
}
function fe(e, t) {
	return typeof e != "boolean" && j(t, "expected a boolean"), e;
}
function I(e, t, n = {}) {
	return (typeof e != "number" || !Number.isFinite(e)) && j(t, "expected a finite number"), n.min !== void 0 && e < n.min && j(t, `number must be at least ${n.min}`), n.exclusiveMin !== void 0 && e <= n.exclusiveMin && j(t, `number must be greater than ${n.exclusiveMin}`), n.max !== void 0 && e > n.max && j(t, `number must be at most ${n.max}`), e;
}
function pe(e, t, n = {}) {
	let r = I(e, t, n);
	return Number.isInteger(r) || j(t, "expected an integer"), r;
}
function me(e, t, n = {}) {
	return e === null ? null : pe(e, t, n);
}
function he(e, t, n) {
	return (typeof e != "string" || !t.includes(e)) && j(n, `expected one of ${t.join(", ")}`), e;
}
function ge(e, t, n, r) {
	return Array.isArray(e) || j(t, "expected an array"), e.length > r && j(t, `array exceeds ${r} items`), e.map((e, r) => n(e, `${t}[${r}]`));
}
function _e(e, t, n) {
	let r = /* @__PURE__ */ new Set();
	for (let i of e) r.has(i.id) && j(n, `duplicate ${t} id ${JSON.stringify(i.id)}`), r.add(i.id);
}
function ve(e, t) {
	if (e === null || typeof e == "boolean" || typeof e == "string") return e;
	if (typeof e == "number") return Number.isFinite(e) || j(t, "JSON numbers must be finite"), e;
	if (Array.isArray(e)) return e.map((e, n) => ve(e, `${t}[${n}]`));
	let n = M(e, t), r = {};
	for (let [e, i] of Object.entries(n)) r[e] = ve(i, `${t}.${e}`);
	return r;
}
function ye(e, t) {
	let n = ve(e, t);
	return (n === null || Array.isArray(n) || typeof n != "object") && j(t, "expected a JSON object"), n;
}
function be(e, t) {
	let n = M(e, t);
	N(n, [
		"id",
		"kind",
		"managedBy",
		"skuId",
		"assetId",
		"modelProfileId",
		"prompt",
		"compositionGroupId",
		"textSnapshotId",
		"outputBoardId",
		"parameters"
	], t);
	let r = he(n.kind, ie, `${t}.kind`), i = n.managedBy === null ? null : he(n.managedBy, ["complete-set"], `${t}.managedBy`), a = n.prompt === null ? null : de(n.prompt, `${t}.prompt`, {
		maxLength: re,
		allowEmpty: !0
	});
	return {
		id: P(n.id, `${t}.id`),
		kind: r,
		managedBy: i,
		skuId: F(n.skuId, `${t}.skuId`),
		assetId: F(n.assetId, `${t}.assetId`),
		modelProfileId: F(n.modelProfileId, `${t}.modelProfileId`),
		prompt: a,
		compositionGroupId: F(n.compositionGroupId, `${t}.compositionGroupId`),
		textSnapshotId: F(n.textSnapshotId, `${t}.textSnapshotId`),
		outputBoardId: F(n.outputBoardId, `${t}.outputBoardId`),
		parameters: ye(n.parameters, `${t}.parameters`)
	};
}
function xe(e, t = "edge") {
	let n = M(e, t);
	N(n, [
		"id",
		"kind",
		"sourceNodeId",
		"sourcePort",
		"targetNodeId",
		"targetPort",
		"skuId"
	], t);
	let r = he(n.kind, Object.keys(ae), `${t}.kind`), i = ae[r];
	return (n.sourcePort !== i.sourcePort || n.targetPort !== i.targetPort) && j(t, `invalid ports for ${r}: ${String(n.sourcePort)} -> ${String(n.targetPort)}`), {
		id: P(n.id, `${t}.id`),
		kind: r,
		sourceNodeId: P(n.sourceNodeId, `${t}.sourceNodeId`),
		sourcePort: i.sourcePort,
		targetNodeId: P(n.targetNodeId, `${t}.targetNodeId`),
		targetPort: i.targetPort,
		skuId: F(n.skuId, `${t}.skuId`)
	};
}
function Se(e, t) {
	return he(e, A, t);
}
function Ce(e, t) {
	let n = M(e, t);
	return N(n, [
		"id",
		"outputNodeId",
		"outputType",
		"skuId",
		"sortOrder",
		"selectedResultAssetId"
	], t), {
		id: P(n.id, `${t}.id`),
		outputNodeId: P(n.outputNodeId, `${t}.outputNodeId`),
		outputType: Se(n.outputType, `${t}.outputType`),
		skuId: F(n.skuId, `${t}.skuId`),
		sortOrder: pe(n.sortOrder, `${t}.sortOrder`, { min: 0 }),
		selectedResultAssetId: F(n.selectedResultAssetId, `${t}.selectedResultAssetId`)
	};
}
function we(e, t) {
	let n = M(e, t);
	return N(n, [
		"outputType",
		"skuId",
		"quantity",
		"aspectRatio",
		"width",
		"height",
		"prompt",
		"modelProfileId",
		"modelParameters",
		"referenceAssetId",
		"compositionGroupId"
	], t), {
		outputType: Se(n.outputType, `${t}.outputType`),
		skuId: F(n.skuId, `${t}.skuId`),
		quantity: me(n.quantity, `${t}.quantity`, {
			min: 1,
			max: 500
		}),
		aspectRatio: n.aspectRatio === null ? null : de(n.aspectRatio, `${t}.aspectRatio`, {
			maxLength: 40,
			trim: !0
		}),
		width: me(n.width, `${t}.width`, {
			min: 1,
			max: 32768
		}),
		height: me(n.height, `${t}.height`, {
			min: 1,
			max: 32768
		}),
		prompt: de(n.prompt, `${t}.prompt`, {
			maxLength: re,
			allowEmpty: !0
		}),
		modelProfileId: F(n.modelProfileId, `${t}.modelProfileId`),
		modelParameters: ye(n.modelParameters, `${t}.modelParameters`),
		referenceAssetId: F(n.referenceAssetId, `${t}.referenceAssetId`),
		compositionGroupId: F(n.compositionGroupId, `${t}.compositionGroupId`)
	};
}
function Te(e, t) {
	let n = M(e, t);
	N(n, ["selectedOutputTypes", "outputs"], t);
	let r = ge(n.selectedOutputTypes, `${t}.selectedOutputTypes`, Se, 3);
	return new Set(r).size !== r.length && j(`${t}.selectedOutputTypes`, "selected output types must be unique"), {
		selectedOutputTypes: r,
		outputs: ge(n.outputs, `${t}.outputs`, we, 500)
	};
}
function Ee(e, t) {
	let n = M(e, t);
	N(n, [
		"slot",
		"anchor",
		"baseline",
		"relativeProductFraction",
		"contain",
		"safeArea",
		"rotation"
	], t);
	let r = M(n.slot, `${t}.slot`);
	N(r, [
		"x",
		"y",
		"width",
		"height"
	], `${t}.slot`);
	let i = {
		x: I(r.x, `${t}.slot.x`, {
			min: 0,
			max: 1
		}),
		y: I(r.y, `${t}.slot.y`, {
			min: 0,
			max: 1
		}),
		width: I(r.width, `${t}.slot.width`, {
			exclusiveMin: 0,
			max: 1
		}),
		height: I(r.height, `${t}.slot.height`, {
			exclusiveMin: 0,
			max: 1
		})
	};
	(i.x + i.width > 1 || i.y + i.height > 1) && j(`${t}.slot`, "normalized slot must remain inside the board");
	let a = M(n.anchor, `${t}.anchor`);
	N(a, ["x", "y"], `${t}.anchor`);
	let o = M(n.safeArea, `${t}.safeArea`);
	N(o, [
		"top",
		"right",
		"bottom",
		"left"
	], `${t}.safeArea`);
	let s = {
		top: I(o.top, `${t}.safeArea.top`, {
			min: 0,
			max: 1
		}),
		right: I(o.right, `${t}.safeArea.right`, {
			min: 0,
			max: 1
		}),
		bottom: I(o.bottom, `${t}.safeArea.bottom`, {
			min: 0,
			max: 1
		}),
		left: I(o.left, `${t}.safeArea.left`, {
			min: 0,
			max: 1
		})
	};
	return (s.left + s.right >= 1 || s.top + s.bottom >= 1) && j(`${t}.safeArea`, "safe area insets must leave a visible board region"), n.contain !== !0 && j(`${t}.contain`, "contain must be true"), {
		slot: i,
		anchor: {
			x: I(a.x, `${t}.anchor.x`, {
				min: 0,
				max: 1
			}),
			y: I(a.y, `${t}.anchor.y`, {
				min: 0,
				max: 1
			})
		},
		baseline: I(n.baseline, `${t}.baseline`, {
			min: 0,
			max: 1
		}),
		relativeProductFraction: I(n.relativeProductFraction, `${t}.relativeProductFraction`, {
			exclusiveMin: 0,
			max: 1
		}),
		contain: !0,
		safeArea: s,
		rotation: I(n.rotation, `${t}.rotation`, {
			min: -180,
			max: 180
		})
	};
}
function De(e, t) {
	let n = M(e, t), r = n.layout === void 0, i = {
		...n,
		layout: n.layout ?? structuredClone(o)
	};
	N(i, [
		"id",
		"skuIds",
		"productLayerIds",
		"layoutHash",
		"layout"
	], t);
	let a = Ee(i.layout, `${t}.layout`), s = r ? p(a) : de(i.layoutHash, `${t}.layoutHash`, { maxLength: 200 });
	return {
		id: P(i.id, `${t}.id`),
		skuIds: ge(i.skuIds, `${t}.skuIds`, P, 500),
		productLayerIds: ge(i.productLayerIds, `${t}.productLayerIds`, P, 500),
		layoutHash: s,
		layout: a
	};
}
function L(e, t) {
	let n = M(e, t);
	N(n, [
		"nodes",
		"edges",
		"outputBoards",
		"mode",
		"advancedCustomized",
		"completeSet",
		"compositionGroups"
	], t);
	let r = ge(n.nodes, `${t}.nodes`, be, te), i = ge(n.edges, `${t}.edges`, xe, ne), a = ge(n.outputBoards, `${t}.outputBoards`, Ce, 500), o = ge(n.compositionGroups, `${t}.compositionGroups`, De, 500);
	return _e(r, "node", `${t}.nodes`), _e(i, "edge", `${t}.edges`), _e(a, "output board", `${t}.outputBoards`), _e(o, "composition group", `${t}.compositionGroups`), {
		nodes: r,
		edges: i,
		outputBoards: a,
		mode: he(n.mode, ["complete-set", "advanced"], `${t}.mode`),
		advancedCustomized: fe(n.advancedCustomized, `${t}.advancedCustomized`),
		completeSet: Te(n.completeSet, `${t}.completeSet`),
		compositionGroups: o
	};
}
function R(e, t) {
	let n = M(e, t);
	return N(n, ["x", "y"], t), {
		x: I(n.x, `${t}.x`),
		y: I(n.y, `${t}.y`)
	};
}
function Oe(e, t) {
	let n = M(e, t);
	return N(n, [
		"x",
		"y",
		"scale",
		"rotation"
	], t), {
		x: I(n.x, `${t}.x`),
		y: I(n.y, `${t}.y`),
		scale: I(n.scale, `${t}.scale`, {
			exclusiveMin: 0,
			max: 1e3
		}),
		rotation: I(n.rotation, `${t}.rotation`, {
			min: -36e4,
			max: 36e4
		})
	};
}
function ke(e, t) {
	let n = {
		...M(e, t),
		allowOpaqueFallback: M(e, t).allowOpaqueFallback ?? !1
	};
	return N(n, [
		"id",
		"sourceAssetId",
		"renderAssetId",
		"allowOpaqueFallback",
		"skuId",
		"compositionGroupId",
		"transformId",
		"locked"
	], t), {
		id: P(n.id, `${t}.id`),
		sourceAssetId: P(n.sourceAssetId, `${t}.sourceAssetId`),
		renderAssetId: P(n.renderAssetId, `${t}.renderAssetId`),
		allowOpaqueFallback: fe(n.allowOpaqueFallback, `${t}.allowOpaqueFallback`),
		skuId: F(n.skuId, `${t}.skuId`),
		compositionGroupId: F(n.compositionGroupId, `${t}.compositionGroupId`),
		transformId: P(n.transformId, `${t}.transformId`),
		locked: fe(n.locked, `${t}.locked`)
	};
}
function Ae(e, t) {
	let n = M(e, t);
	N(n, [
		"text",
		"x",
		"y",
		"width"
	], t);
	let r = de(n.text, `${t}.text`, {
		maxLength: k,
		allowEmpty: !0
	});
	return (r.includes("\r") || r.includes("\n")) && j(`${t}.text`, "must not contain CR or LF"), {
		text: r,
		x: I(n.x, `${t}.x`),
		y: I(n.y, `${t}.y`),
		width: I(n.width, `${t}.width`, { min: 0 })
	};
}
function je(e, t) {
	let n = M(e, t);
	N(n, [
		"id",
		"nodeId",
		"content",
		"fontAssetId",
		"fontFamily",
		"fontVersion",
		"boxWidth",
		"lines",
		"fontSize",
		"color",
		"letterSpacing",
		"lineHeight",
		"align",
		"baseline",
		"zBand",
		"sortOrder"
	], t);
	let r = ge(n.lines, `${t}.lines`, Ae, 1e4);
	r.reduce((e, t) => e + t.text.length, 0) > k && j(`${t}.lines`, `text lines exceed ${k} characters`);
	let i = de(n.content, `${t}.content`, {
		maxLength: k,
		allowEmpty: !0
	}), a = pe(n.fontSize, `${t}.fontSize`, {
		min: 1,
		max: 1e4
	}), o = I(n.letterSpacing, `${t}.letterSpacing`, {
		min: -1e4,
		max: 1e4
	});
	return (i !== r.map((e) => e.text).join("\n") || i.length === 0 && r.length > 0) && j(`${t}.content`, "must match canonical explicit lines"), o !== 0 && r.some((e) => !S(e.text)) && j(`${t}.letterSpacing`, "supports only independent BMP code points"), {
		id: P(n.id, `${t}.id`),
		nodeId: P(n.nodeId, `${t}.nodeId`),
		content: i,
		fontAssetId: n.fontAssetId === null ? null : j(`${t}.fontAssetId`, "must be null for the pinned font"),
		fontFamily: n.fontFamily === "Noto Sans CJK SC" ? n.fontFamily : j(`${t}.fontFamily`, "must use the pinned Canvas font"),
		fontVersion: n.fontVersion === "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b" ? n.fontVersion : j(`${t}.fontVersion`, "must match the pinned Canvas font"),
		boxWidth: I(n.boxWidth, `${t}.boxWidth`, { min: 0 }),
		lines: r,
		fontSize: a,
		color: (() => {
			let e = de(n.color, `${t}.color`, {
				maxLength: 7,
				allowEmpty: !1
			});
			return /^#[0-9a-fA-F]{6}$/.test(e) ? e : j(`${t}.color`, "must be a six-digit hex color");
		})(),
		letterSpacing: o,
		lineHeight: I(n.lineHeight, `${t}.lineHeight`, {
			exclusiveMin: 0,
			max: 1e3
		}),
		align: he(n.align, [
			"left",
			"center",
			"right"
		], `${t}.align`),
		baseline: he(n.baseline, [
			"alphabetic",
			"top",
			"middle",
			"bottom"
		], `${t}.baseline`),
		zBand: he(n.zBand, ["below-product", "above-product"], `${t}.zBand`),
		sortOrder: pe(n.sortOrder, `${t}.sortOrder`, {
			min: 0,
			max: 1e4
		})
	};
}
function Me(e, t) {
	let n = M(e, t);
	N(n, [
		"nodePositions",
		"objectTransforms",
		"viewport",
		"productLayers",
		"textSnapshots"
	], t);
	let r = M(n.nodePositions, `${t}.nodePositions`), i = {};
	for (let [e, n] of Object.entries(r)) i[P(e, `${t}.nodePositions key`)] = R(n, `${t}.nodePositions.${e}`);
	let a = M(n.objectTransforms, `${t}.objectTransforms`), o = {};
	for (let [e, n] of Object.entries(a)) o[P(e, `${t}.objectTransforms key`)] = Oe(n, `${t}.objectTransforms.${e}`);
	let s = M(n.viewport, `${t}.viewport`);
	N(s, [
		"x",
		"y",
		"zoom"
	], `${t}.viewport`);
	let c = ge(n.productLayers, `${t}.productLayers`, ke, 500), l = ge(n.textSnapshots, `${t}.textSnapshots`, je, 500);
	return _e(c, "product layer", `${t}.productLayers`), _e(l, "text snapshot", `${t}.textSnapshots`), {
		nodePositions: i,
		objectTransforms: o,
		viewport: {
			x: I(s.x, `${t}.viewport.x`),
			y: I(s.y, `${t}.viewport.y`),
			zoom: I(s.zoom, `${t}.viewport.zoom`, {
				exclusiveMin: 0,
				max: 1e3
			})
		},
		productLayers: c,
		textSnapshots: l
	};
}
function Ne(e, t, n, r) {
	e !== null && !t.has(e) && j(n, `references unknown ${r} ${JSON.stringify(e)}`);
}
function Pe(e) {
	let t = new Set(e.semanticState.nodes.map((e) => e.id)), n = new Set(e.semanticState.outputBoards.map((e) => e.id)), r = new Set(e.semanticState.compositionGroups.map((e) => e.id)), i = new Set(e.layoutState.productLayers.map((e) => e.id)), a = new Set(e.layoutState.textSnapshots.map((e) => e.id)), o = new Set(Object.keys(e.layoutState.objectTransforms));
	e.semanticState.nodes.forEach((e, t) => {
		let i = `project.semanticState.nodes[${t}]`;
		Ne(e.compositionGroupId, r, `${i}.compositionGroupId`, "composition group"), Ne(e.textSnapshotId, a, `${i}.textSnapshotId`, "text snapshot"), Ne(e.outputBoardId, n, `${i}.outputBoardId`, "output board");
	}), e.semanticState.edges.forEach((n, r) => {
		let i = `project.semanticState.edges[${r}]`;
		Ne(n.sourceNodeId, t, `${i}.sourceNodeId`, "node"), Ne(n.targetNodeId, t, `${i}.targetNodeId`, "node");
		let a = e.semanticState.nodes.find((e) => e.id === n.sourceNodeId), o = e.semanticState.nodes.find((e) => e.id === n.targetNodeId);
		(a === void 0 || o === void 0 || !D(a.kind, o.kind, n.kind)) && j(i, "incompatible node connection");
	}), e.semanticState.nodes.forEach((t, n) => {
		if (t.kind !== "auto_cutout") return;
		let r = e.semanticState.edges.filter((e) => e.kind === "product_asset" && e.targetNodeId === t.id);
		r.length !== 1 && j(`project.semanticState.nodes[${n}]`, "auto cutout must retain its product route");
		let i = r[0], a = e.semanticState.nodes.find((e) => e.id === i.sourceNodeId);
		(t.id !== "main-product-cutout" || t.skuId !== null || t.assetId === null || a?.id !== "main-product-source" || a.kind !== "product_source" || a.skuId !== null || a.assetId === null) && j(`project.semanticState.nodes[${n}]`, "auto cutout must use the canonical system product pipeline");
		let o = e.layoutState.productLayers.filter((e) => e.skuId === null && e.locked);
		(o.length !== 1 || a.assetId !== o[0]?.sourceAssetId || t.assetId !== o[0]?.renderAssetId) && j(`project.semanticState.nodes[${n}]`, "auto cutout asset binding must match the locked product layer");
	}), e.semanticState.outputBoards.forEach((e, n) => {
		Ne(e.outputNodeId, t, `project.semanticState.outputBoards[${n}].outputNodeId`, "node");
	}), e.semanticState.completeSet.outputs.forEach((e, t) => {
		Ne(e.compositionGroupId, r, `project.semanticState.completeSet.outputs[${t}].compositionGroupId`, "composition group");
	}), e.semanticState.compositionGroups.forEach((t, n) => {
		/^sha256:[0-9a-f]{64}$/.test(t.layoutHash) || j(`project.semanticState.compositionGroups[${n}].layoutHash`, "expected sha256:<lowercase hex>"), t.layoutHash !== p(t.layout) && j(`project.semanticState.compositionGroups[${n}].layoutHash`, "layout hash does not match shared composition layout"), new Set(t.skuIds).size !== t.skuIds.length && j(`project.semanticState.compositionGroups[${n}].skuIds`, "duplicate SKU id"), new Set(t.productLayerIds).size !== t.productLayerIds.length && j(`project.semanticState.compositionGroups[${n}].productLayerIds`, "duplicate product layer id"), t.productLayerIds.forEach((e, t) => {
			Ne(e, i, `project.semanticState.compositionGroups[${n}].productLayerIds[${t}]`, "product layer");
		});
		let r = e.layoutState.productLayers.filter((e) => e.compositionGroupId === t.id);
		(r.length !== t.productLayerIds.length || r.some((e) => !t.productLayerIds.includes(e.id))) && j(`project.semanticState.compositionGroups[${n}]`, "composition group product membership is inconsistent or references unknown group");
		let a = r.flatMap((e) => e.skuId === null ? [] : [e.skuId]).sort();
		JSON.stringify(a) !== JSON.stringify([...t.skuIds].sort()) && j(`project.semanticState.compositionGroups[${n}].skuIds`, "composition group SKU membership is inconsistent");
		let o = m(t.layout);
		for (let t of r) {
			t.locked || j(`project.layoutState.productLayers.${t.id}.locked`, "composition product must remain locked"), t.allowOpaqueFallback && t.renderAssetId !== t.sourceAssetId && j(`project.layoutState.productLayers.${t.id}.allowOpaqueFallback`, "opaque fallback must render its working source");
			let n = e.layoutState.objectTransforms[t.transformId];
			(n === void 0 || Math.abs(n.x - o.x) > 1e-6 || Math.abs(n.y - o.y) > 1e-6 || Math.abs(n.scale - o.scale) > 1e-6 || Math.abs(n.rotation - o.rotation) > 1e-6) && j(`project.layoutState.productLayers.${t.id}.transformId`, "composition projection does not match its shared layout or references unknown transform");
		}
	}), e.layoutState.productLayers.forEach((e, t) => {
		let n = `project.layoutState.productLayers[${t}]`;
		Ne(e.compositionGroupId, r, `${n}.compositionGroupId`, "composition group"), Ne(e.transformId, o, `${n}.transformId`, "transform");
	}), e.layoutState.textSnapshots.forEach((e, n) => {
		Ne(e.nodeId, t, `project.layoutState.textSnapshots[${n}].nodeId`, "node");
	});
	for (let n of Object.keys(e.layoutState.nodePositions)) Ne(n, t, `project.layoutState.nodePositions.${n}`, "node");
}
function Fe(e, t) {
	for (let n of e.semanticState.compositionGroups) {
		if (!t.has(n.id)) continue;
		let r = e.layoutState.productLayers.find((e) => n.productLayerIds.includes(e.id)), i = r === void 0 ? void 0 : e.layoutState.objectTransforms[r.transformId], a = structuredClone(o);
		if (i !== void 0) {
			if (i.x > 0 && i.x < 1) {
				let e = Math.min(.8, 2 * i.x, 2 * (1 - i.x));
				a.slot.width = e, a.slot.x = i.x - e * .5;
			}
			a.baseline = i.y, a.relativeProductFraction = i.scale, a.rotation = i.rotation;
		}
		n.layout = a, n.layoutHash = p(a);
	}
}
function Ie(e) {
	ue(e, "project");
	let t = M(e, "project");
	N(t, [
		"schemaVersion",
		"semanticState",
		"layoutState"
	], "project");
	let n = pe(t.schemaVersion, "project.schemaVersion");
	n !== 1 && j("project.schemaVersion", `unsupported schema version ${n}`);
	let r = M(t.semanticState, "project.semanticState"), i = Array.isArray(r.compositionGroups) ? r.compositionGroups : [], a = new Set(i.flatMap((e) => {
		if (typeof e != "object" || !e || Array.isArray(e)) return [];
		let t = e;
		return t.layout === void 0 && typeof t.id == "string" ? [t.id] : [];
	})), o = {
		schemaVersion: 1,
		semanticState: L(t.semanticState, "project.semanticState"),
		layoutState: Me(t.layoutState, "project.layoutState")
	};
	Fe(o, a);
	let s = /* @__PURE__ */ new Set();
	for (let e of o.semanticState.nodes) e.kind === "product_source" && e.assetId !== null && e.parameters.allowOpaqueFallback === !0 && (s.add(e.assetId), delete e.parameters.allowOpaqueFallback);
	for (let e of o.layoutState.productLayers) e.skuId === null && s.has(e.sourceAssetId) && (e.allowOpaqueFallback = !0);
	return Pe(o), o;
}
function Le(e, t) {
	if (e === null || typeof e == "boolean" || typeof e == "string") return JSON.stringify(e);
	if (typeof e == "number") return Number.isFinite(e) || j(t, "JSON numbers must be finite"), JSON.stringify(e);
	if (Array.isArray(e)) return `[${e.map((e, n) => Le(e, `${t}[${n}]`)).join(",")}]`;
	let n = M(e, t);
	return `{${Object.keys(n).sort().map((e) => `${JSON.stringify(e)}:${Le(n[e], `${t}.${e}`)}`).join(",")}}`;
}
function Re(e) {
	return Le(Ie(e), "project");
}
//#endregion
//#region frontend/canvas/src/api/client.ts
function ze(e, t) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error(`${t} must be an object`);
	return e;
}
function z(e, t, n) {
	let r = [...t].sort(), i = Object.keys(e).sort();
	if (i.length !== r.length || i.some((e, t) => e !== r[t])) throw Error(`${n} fields do not match the Canvas contract`);
}
function Be(e, t, n = !1) {
	if (typeof e != "string" || !n && e.length === 0) throw Error(`${t} must be ${n ? "a string" : "a non-empty string"}`);
	return e;
}
function Ve(e, t) {
	return e === null ? null : Be(e, t, !0);
}
function He(e, t, n) {
	if (typeof e != "number" || !Number.isInteger(e) || e < n) throw Error(`${t} must be an integer >= ${n}`);
	return e;
}
function Ue(e, t) {
	if (e !== "active" && e !== "archived" && e !== "deleting") throw Error(`${t} is not a supported project status`);
	return e;
}
function We(e, t) {
	if (e === null || typeof e == "string" || typeof e == "boolean") return;
	if (typeof e == "number") {
		if (!Number.isFinite(e)) throw Error(`${t} must contain finite JSON numbers`);
		return;
	}
	if (Array.isArray(e)) {
		e.forEach((e, n) => We(e, `${t}[${n}]`));
		return;
	}
	let n = ze(e, t);
	for (let [e, r] of Object.entries(n)) We(r, `${t}.${e}`);
}
var Ge = [
	"id",
	"name",
	"status",
	"schemaVersion",
	"revision",
	"createdAt",
	"updatedAt",
	"archivedAt"
];
function Ke(e, t) {
	if (He(e.schemaVersion, `${t}.schemaVersion`, 1) !== 1) throw Error(`${t}.schemaVersion must be 1`);
	return {
		id: Be(e.id, `${t}.id`),
		name: Be(e.name, `${t}.name`),
		status: Ue(e.status, `${t}.status`),
		schemaVersion: 1,
		revision: He(e.revision, `${t}.revision`, 1),
		createdAt: Ve(e.createdAt, `${t}.createdAt`),
		updatedAt: Ve(e.updatedAt, `${t}.updatedAt`),
		archivedAt: Ve(e.archivedAt, `${t}.archivedAt`)
	};
}
function qe(e) {
	let t = ze(e, "project");
	return z(t, Ge, "project"), Ke(t, "project");
}
function Je(e, t) {
	let n = ze(e, t);
	z(n, [
		"id",
		"projectId",
		"name",
		"sortOrder",
		"referenceAssetId",
		"prompt",
		"config"
	], t);
	let r = ze(n.config, `${t}.config`);
	return We(r, `${t}.config`), {
		id: Be(n.id, `${t}.id`),
		projectId: Be(n.projectId, `${t}.projectId`),
		name: Be(n.name, `${t}.name`),
		sortOrder: He(n.sortOrder, `${t}.sortOrder`, 0),
		referenceAssetId: n.referenceAssetId === null ? null : Be(n.referenceAssetId, `${t}.referenceAssetId`),
		prompt: Be(n.prompt, `${t}.prompt`, !0),
		config: r
	};
}
function Ye(e) {
	let t = ze(e, "snapshot");
	z(t, [
		"project",
		"skus",
		"revision"
	], "snapshot");
	let n = ze(t.project, "snapshot.project");
	z(n, [
		...Ge,
		"semanticState",
		"layoutState"
	], "snapshot.project");
	let r = Ke(n, "snapshot.project"), i = Ie({
		schemaVersion: r.schemaVersion,
		semanticState: n.semanticState,
		layoutState: n.layoutState
	}), a = He(t.revision, "snapshot.revision", 1);
	if (a !== r.revision) throw Error("snapshot.revision must equal snapshot.project.revision");
	if (!Array.isArray(t.skus)) throw Error("snapshot.skus must be an array");
	let o = t.skus.map((e, t) => Je(e, `snapshot.skus[${t}]`));
	if (o.some((e) => e.projectId !== r.id)) throw Error("snapshot SKU belongs to another project");
	return {
		project: {
			...r,
			semanticState: i.semanticState,
			layoutState: i.layoutState
		},
		skus: o,
		revision: a
	};
}
function Xe(e, t) {
	let n = Ye(e);
	if (n.project.id !== t) throw Error("snapshot belongs to another project");
	return n;
}
function Ze(e) {
	return {
		ok: !1,
		kind: "server",
		message: e instanceof Error ? `Invalid Canvas response: ${e.message}` : "Invalid Canvas response"
	};
}
function Qe(e) {
	return e instanceof DOMException && e.name === "AbortError" || typeof e == "object" && !!e && "name" in e && e.name === "AbortError";
}
function $e(e) {
	return {
		ok: !1,
		kind: "offline",
		message: e instanceof Error ? e.message : "Network unavailable"
	};
}
async function et(e) {
	try {
		return await e.json();
	} catch {
		return null;
	}
}
function tt(e, t) {
	return typeof t == "object" && t && "detail" in t && typeof t.detail == "string" ? t.detail : `Canvas request failed (${e.status})`;
}
function nt(e, t) {
	return e.status === 409 && typeof t == "object" && t && "code" in t && t.code === "canvas_revision_conflict" && "currentRevision" in t && typeof t.currentRevision == "number" && Number.isInteger(t.currentRevision) ? {
		ok: !1,
		kind: "conflict",
		currentRevision: t.currentRevision
	} : null;
}
function rt({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
	let n = e.replace(/\/+$/, ""), r = (e) => `${n}/projects/${encodeURIComponent(e)}`, i = async (e, n = {}) => {
		try {
			let r = await t(e, n);
			return {
				ok: !0,
				response: r,
				body: await et(r)
			};
		} catch (e) {
			if (Qe(e)) throw e;
			return $e(e);
		}
	}, a = (e, t, n) => ({
		method: e,
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(t),
		signal: n
	}), o = async (e, t) => {
		let n = await i(e, t);
		return n.ok ? n.response.ok ? {
			ok: !0,
			value: n.body
		} : {
			ok: !1,
			kind: "server",
			message: tt(n.response, n.body)
		} : n;
	}, s = async (e, t, n) => {
		let r = await i(e, t);
		if (!r.ok) return r;
		if (!r.response.ok) return nt(r.response, r.body) ?? {
			ok: !1,
			kind: "server",
			message: tt(r.response, r.body)
		};
		try {
			return {
				ok: !0,
				snapshot: Xe(r.body, n)
			};
		} catch (e) {
			return Ze(e);
		}
	};
	return {
		listProjects: async (e = {}) => {
			let t = new URLSearchParams();
			e.query !== void 0 && e.query !== "" && t.set("q", e.query), e.includeArchived !== void 0 && t.set("includeArchived", String(e.includeArchived));
			let r = t.size === 0 ? "" : `?${t.toString()}`, i = await o(`${n}/projects${r}`, { signal: e.signal });
			if (!i.ok) return i;
			try {
				let e = ze(i.value, "list response");
				if (z(e, ["projects"], "list response"), !Array.isArray(e.projects)) throw Error("list response.projects must be an array");
				return {
					ok: !0,
					value: e.projects.map(qe)
				};
			} catch (e) {
				return Ze(e);
			}
		},
		createProject: async (e) => {
			let t = await o(`${n}/projects`, a("POST", { name: e }));
			if (!t.ok) return t;
			try {
				return {
					ok: !0,
					value: Ye(t.value)
				};
			} catch (e) {
				return Ze(e);
			}
		},
		getProject: async (e, t) => {
			let n = await o(r(e), { signal: t });
			if (!n.ok) return n;
			try {
				return {
					ok: !0,
					value: Xe(n.value, e)
				};
			} catch (e) {
				return Ze(e);
			}
		},
		saveProjectState: ({ projectId: e, revision: t, semanticState: n, layoutState: i }) => s(`${r(e)}/state`, a("PUT", {
			revision: t,
			semanticState: n,
			layoutState: i
		}), e),
		renameProject: (e, t, n) => s(r(e), a("PATCH", {
			revision: t,
			name: n
		}), e),
		archiveProject: (e, t) => s(`${r(e)}/archive`, a("POST", { revision: t }), e),
		restoreProject: (e, t) => s(`${r(e)}/restore`, a("POST", { revision: t }), e),
		deleteProject: (e, t) => s(r(e), a("DELETE", { revision: t }), e)
	};
}
//#endregion
//#region frontend/canvas/src/api/assets.ts
function it(e) {
	if (e === "") return null;
	try {
		return JSON.parse(e);
	} catch {
		return null;
	}
}
function at() {
	return new DOMException("Canvas upload aborted", "AbortError");
}
function ot(e = () => new XMLHttpRequest()) {
	return ({ url: t, file: n, signal: r, onProgress: i }) => new Promise((a, o) => {
		if (r?.aborted) {
			o(at());
			return;
		}
		let s = e(), c = () => {
			r?.removeEventListener("abort", l);
		}, l = () => {
			s.abort();
		};
		s.upload.addEventListener("progress", (e) => {
			let t = e.lengthComputable ? e.total : null;
			i?.({
				loaded: e.loaded,
				total: t,
				percent: t !== null && t > 0 ? Math.round(e.loaded / t * 100) : null
			});
		}), s.addEventListener("load", () => {
			c(), a({
				status: s.status,
				body: it(s.responseText)
			});
		}), s.addEventListener("error", () => {
			c(), o(/* @__PURE__ */ Error("Canvas upload network unavailable"));
		}), s.addEventListener("abort", () => {
			c(), o(at());
		}), r?.addEventListener("abort", l, { once: !0 });
		let u = new FormData();
		u.append("file", n, n.name), s.open("POST", t), s.send(u);
	});
}
function st(e, t) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error(`${t} must be an object`);
	return e;
}
function ct(e, t, n = !1) {
	if (typeof e != "string" || !n && e.length === 0) throw Error(`${t} must be a string`);
	return e;
}
function lt(e, t) {
	return e === null ? null : ct(e, t, !0);
}
function ut(e, t) {
	if (typeof e != "number" || !Number.isInteger(e) || e < 0) throw Error(`${t} must be a non-negative integer`);
	return e;
}
function dt(e, t, n) {
	if (typeof e != "string" || !t.includes(e)) throw Error(`${n} is unsupported`);
	return e;
}
var ft = [
	"source",
	"working",
	"preview",
	"cutout",
	"generated_background",
	"composed",
	"export"
], pt = [
	"unknown",
	"opaque",
	"transparent"
], mt = [
	"cancel_requested",
	"cancelled",
	"failed",
	"interrupted",
	"queued",
	"running",
	"succeeded"
], ht = [
	"compose",
	"cutout",
	"export"
];
function gt(e, t = "asset") {
	let n = st(e, t);
	return {
		id: ct(n.id, `${t}.id`),
		projectId: ct(n.projectId, `${t}.projectId`),
		assetType: dt(n.assetType, ft, `${t}.assetType`),
		originalFilename: ct(n.originalFilename, `${t}.originalFilename`, !0),
		mimeType: ct(n.mimeType, `${t}.mimeType`),
		byteCount: ut(n.byteCount, `${t}.byteCount`),
		width: ut(n.width, `${t}.width`),
		height: ut(n.height, `${t}.height`),
		sha256: ct(n.sha256, `${t}.sha256`),
		sourceAssetId: lt(n.sourceAssetId, `${t}.sourceAssetId`),
		transparencyStatus: dt(n.transparencyStatus, pt, `${t}.transparencyStatus`),
		processorVersion: lt(n.processorVersion, `${t}.processorVersion`),
		metadata: st(n.metadata, `${t}.metadata`)
	};
}
function _t(e, t) {
	if (e == null) return null;
	let n = st(e, t);
	if (typeof n.retryable != "boolean") throw Error(`${t}.retryable must be a boolean`);
	return {
		code: ct(n.code, `${t}.code`),
		message: ct(n.message, `${t}.message`),
		retryable: n.retryable
	};
}
function vt(e, t = "operation") {
	let n = st(e, t), r = n.operationType ?? n.type, i = n.safeError ?? n.error ?? null;
	return {
		id: ct(n.id, `${t}.id`),
		projectId: ct(n.projectId, `${t}.projectId`),
		operationType: dt(r, ht, `${t}.operationType`),
		status: dt(n.status, mt, `${t}.status`),
		attemptCount: ut(n.attemptCount, `${t}.attemptCount`),
		inputAssetId: ct(n.inputAssetId, `${t}.inputAssetId`),
		outputAssetId: lt(n.outputAssetId, `${t}.outputAssetId`),
		safeError: _t(i, `${t}.safeError`)
	};
}
function yt(e, t) {
	let n = st(e, "upload response"), r = gt(n.source, "upload response.source"), i = gt(n.working, "upload response.working"), a = gt(n.preview, "upload response.preview"), o = n.operation === null ? null : vt(n.operation, "upload response.operation");
	if (r.projectId !== t || i.projectId !== t || a.projectId !== t || o !== null && o.projectId !== t) throw Error("Canvas upload response belongs to another project");
	return {
		source: r,
		working: i,
		preview: a,
		operation: o
	};
}
function bt(e) {
	return e instanceof DOMException && e.name === "AbortError" || typeof e == "object" && !!e && "name" in e && e.name === "AbortError";
}
function xt(e) {
	return e === 413 ? {
		ok: !1,
		kind: "validation",
		status: e,
		message: "图片不能超过 12 MB"
	} : e === 415 ? {
		ok: !1,
		kind: "validation",
		status: e,
		message: "仅支持 JPG、PNG 或 WebP 图片"
	} : e === 422 ? {
		ok: !1,
		kind: "validation",
		status: e,
		message: "图片未通过服务器校验，请检查文件后重试"
	} : {
		ok: !1,
		kind: "server",
		status: e,
		message: "素材服务暂时不可用，请稍后重试"
	};
}
function St(e) {
	return {
		ok: !1,
		kind: "server",
		status: e,
		message: "素材服务暂时不可用，请稍后重试"
	};
}
function Ct({ apiBase: e, fetcher: t = (e, t) => fetch(e, t), uploadTransport: n = ot() }) {
	let r = e.replace(/\/+$/, ""), i = async (e, n, r) => {
		let i;
		try {
			i = await t(e, n);
		} catch (e) {
			if (bt(e)) throw e;
			return {
				ok: !1,
				kind: "offline",
				message: "网络不可用，请检查连接后重试"
			};
		}
		let a = null;
		try {
			a = await i.json();
		} catch {}
		if (!i.ok) return St(i.status);
		try {
			return {
				ok: !0,
				value: r(a)
			};
		} catch {
			return {
				ok: !1,
				kind: "server",
				status: i.status,
				message: "素材服务返回了无效响应"
			};
		}
	}, a = (e, t, n) => ({
		method: e,
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify(t),
		signal: n
	});
	return {
		previewUrl: (e) => `${r}/assets/${encodeURIComponent(e)}/content?variant=preview`,
		uploadAsset: async ({ projectId: e, file: t, signal: i, onProgress: a }) => {
			let o;
			try {
				o = await n({
					url: `${r}/projects/${encodeURIComponent(e)}/assets`,
					file: t,
					signal: i,
					onProgress: a
				});
			} catch (e) {
				if (bt(e)) throw e;
				return {
					ok: !1,
					kind: "offline",
					message: "网络不可用，请检查连接后重试"
				};
			}
			if (o.status < 200 || o.status >= 300) return xt(o.status);
			try {
				return {
					ok: !0,
					value: yt(o.body, e)
				};
			} catch {
				return {
					ok: !1,
					kind: "server",
					status: o.status,
					message: "素材服务返回了无效响应"
				};
			}
		},
		listAssets: (e, t) => i(`${r}/projects/${encodeURIComponent(e)}/assets`, { signal: t }, (t) => {
			let n = st(t, "asset list response");
			if (!Array.isArray(n.assets)) throw Error("asset list response.assets must be an array");
			let r = n.assets.map((e, t) => gt(e, `assets[${t}]`));
			if (r.some((t) => t.projectId !== e)) throw Error("asset list response belongs to another project");
			return r;
		}),
		listOperations: (e, t) => i(`${r}/projects/${encodeURIComponent(e)}/operations`, { signal: t }, (t) => {
			let n = st(t, "operation list response");
			if (!Array.isArray(n.operations)) throw Error("operation list response.operations must be an array");
			let r = n.operations.map((e, t) => vt(e, `operations[${t}]`)).reverse();
			if (r.some((t) => t.projectId !== e)) throw Error("operation list response belongs to another project");
			return r;
		}),
		retryCutout: (e, t, n) => i(`${r}/assets/${encodeURIComponent(e)}/cutout/retry`, a("POST", { clientRequestId: t }, n), vt),
		retryOperation: (e, t) => i(`${r}/operations/${encodeURIComponent(e)}/retry`, a("POST", {}, t), vt),
		deleteAsset: (e, t) => i(`${r}/assets/${encodeURIComponent(e)}`, {
			method: "DELETE",
			signal: t
		}, (e) => {
			let t = st(e, "delete asset response");
			if (t.status !== "deleted") throw Error("delete asset response status is invalid");
			return ct(t.assetId, "delete asset response.assetId");
		})
	};
}
//#endregion
//#region frontend/canvas/src/api/compositions.ts
function wt(e) {
	return typeof e != "object" || !e || Array.isArray(e) ? {} : e;
}
function Tt(e) {
	return e instanceof DOMException && e.name === "AbortError";
}
function Et({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
	let n = e.replace(/\/+$/, "");
	return { enqueueCompose: async ({ projectId: e, revision: r, boardId: i, backgroundAssetId: a, clientRequestId: o, signal: s }) => {
		let c;
		try {
			c = await t(`${n}/projects/${encodeURIComponent(e)}/compose`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({
					revision: r,
					boardId: i,
					backgroundAssetId: a,
					idempotencyKey: o
				}),
				signal: s
			});
		} catch (e) {
			if (Tt(e)) throw e;
			return {
				ok: !1,
				kind: "offline",
				message: "网络不可用，请检查连接后重试"
			};
		}
		let l = null;
		try {
			l = await c.json();
		} catch {}
		if (c.status === 409) {
			let e = wt(l);
			return {
				ok: !1,
				kind: "conflict",
				currentRevision: typeof e.currentRevision == "number" && Number.isInteger(e.currentRevision) ? e.currentRevision : r
			};
		}
		if (c.status === 422) return {
			ok: !1,
			kind: "validation",
			status: c.status,
			message: "当前构图或素材不满足合成条件"
		};
		if (!c.ok) return {
			ok: !1,
			kind: "server",
			status: c.status,
			message: "合成服务暂时不可用，请稍后重试"
		};
		try {
			let t = vt(l);
			if (t.projectId !== e || t.operationType !== "compose") throw Error("composition response ownership mismatch");
			return {
				ok: !0,
				value: t
			};
		} catch {
			return {
				ok: !1,
				kind: "server",
				status: c.status,
				message: "合成服务返回了无效响应"
			};
		}
	} };
}
//#endregion
//#region frontend/canvas/src/api/exports.ts
function Dt(e) {
	return typeof e == "object" && e && !Array.isArray(e) ? e : {};
}
function Ot(e) {
	let t = Dt(e).detail;
	return typeof t == "string" && t.length > 0 && t.length <= 500 ? t : "导出选项无效，请检查后重试";
}
function kt(e) {
	return e instanceof DOMException && e.name === "AbortError";
}
function At({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
	let n = e.replace(/\/+$/, "");
	return {
		create: async (e, r, i, a) => {
			let o;
			try {
				o = await t(`${n}/projects/${encodeURIComponent(e)}/exports`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						"Idempotency-Key": i
					},
					body: JSON.stringify(r),
					signal: a
				});
			} catch (e) {
				if (kt(e)) throw e;
				return {
					ok: !1,
					kind: "offline",
					message: "网络不可用，请检查连接后重试"
				};
			}
			let s = null;
			try {
				s = await o.json();
			} catch {}
			if (o.status === 401) return {
				ok: !1,
				kind: "unauthorized",
				message: "需要解锁付费导出功能"
			};
			if (o.status === 422) return {
				ok: !1,
				kind: "validation",
				message: Ot(s)
			};
			if (o.status === 409) {
				let e = Dt(s).currentRevision;
				return {
					ok: !1,
					kind: "conflict",
					message: "项目或幂等请求已发生冲突，请刷新后重试",
					...typeof e == "number" && Number.isInteger(e) ? { currentRevision: e } : {}
				};
			}
			if (!o.ok) return {
				ok: !1,
				kind: "server",
				message: "导出服务暂时不可用，请稍后重试"
			};
			try {
				let t = vt(s, "export operation");
				if (t.projectId !== e || t.operationType !== "export") throw Error("export operation ownership mismatch");
				return {
					ok: !0,
					value: t
				};
			} catch {
				return {
					ok: !1,
					kind: "server",
					message: "导出服务返回了无效响应"
				};
			}
		},
		downloadUrl: (e) => `${n}/assets/${encodeURIComponent(e)}/download`
	};
}
//#endregion
//#region frontend/canvas/src/api/events.ts
var jt = [
	"project.created",
	"project.updated",
	"project.state_saved",
	"project.archived",
	"project.restored",
	"project.deleting",
	"sku.created",
	"sku.updated",
	"sku.deleted"
], Mt = ["asset.uploaded", "asset.deleted"], Nt = [
	"operation.queued",
	"operation.retried",
	"operation.running",
	"operation.recovered",
	"operation.released",
	"operation.succeeded",
	"operation.failed",
	"operation.interrupted"
], Pt = [
	"generation.item.running",
	"generation.attempt.submitting",
	"generation.attempt.polling",
	"generation.item.cancel_requested",
	"generation.item.cancelled",
	"generation.item.failed",
	"generation.item.unknown",
	"generation.item.composing",
	"generation.item.succeeded",
	"generation.item.compose_failed",
	"generation.item.retrying",
	"generation.item.abandoned"
];
[
	...jt,
	...Mt,
	...Nt,
	...Pt
];
function Ft(e) {
	return e.type === "snapshot" || "revision" in e;
}
function It(e, t) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error(`${t} must be an object`);
	return e;
}
function Lt(e, t, n) {
	let r = Object.keys(e).sort(), i = [...t].sort();
	if (r.length !== i.length || r.some((e, t) => e !== i[t])) throw Error(`${n} fields do not match the Canvas event contract`);
}
function Rt(e, t, n, r) {
	if (t.some((t) => !(t in e)) || Object.keys(e).some((e) => !n.includes(e))) throw Error(`${r} fields do not match the Canvas event contract`);
}
function B(e, t) {
	if (typeof e != "string" || e.length === 0) throw Error(`${t} must be a non-empty string`);
	return e;
}
function zt(e, t) {
	return e === null ? null : B(e, t);
}
function Bt(e) {
	if (typeof e != "number" || !Number.isInteger(e) || e < 1) throw Error("Canvas event revision must be a positive integer");
	return e;
}
function V(e, t) {
	if (typeof e != "number" || !Number.isInteger(e) || e < 0) throw Error(`${t} must be a non-negative integer`);
	return e;
}
function Vt(e) {
	switch (e) {
		case "project.archived": return "archived";
		case "project.deleting": return "deleting";
		case "sku.deleted": return "deleted";
		default: return "active";
	}
}
function Ht(e, t, n) {
	let r = It(t, `event ${e}`), i = e.startsWith("sku."), a = e === "project.state_saved";
	if (Lt(r, [
		"projectId",
		"revision",
		"status",
		...i ? ["skuId"] : [],
		...a ? ["summary"] : []
	], `event ${e}`), r.projectId !== n) throw Error(`event ${e} belongs to another project`);
	let o = Vt(e);
	if (r.status !== o) throw Error(`event ${e} has an invalid status`);
	let s = {
		type: e,
		projectId: n,
		revision: Bt(r.revision),
		status: o
	};
	if (i && (s.skuId = B(r.skuId, `event ${e}.skuId`)), a) {
		let t = It(r.summary, `event ${e}.summary`);
		Lt(t, [
			"nodeCount",
			"edgeCount",
			"outputBoardCount"
		], `event ${e}.summary`), s.summary = {
			nodeCount: V(t.nodeCount, `event ${e}.summary.nodeCount`),
			edgeCount: V(t.edgeCount, `event ${e}.summary.edgeCount`),
			outputBoardCount: V(t.outputBoardCount, `event ${e}.summary.outputBoardCount`)
		};
	}
	return s;
}
function Ut(e, t, n) {
	let r = It(t, `event ${e}`);
	if (e === "asset.uploaded") {
		if (Lt(r, [
			"projectId",
			"sourceAssetId",
			"workingAssetId",
			"previewAssetId",
			"transparencyStatus"
		], `event ${e}`), r.projectId !== n) throw Error(`event ${e} belongs to another project`);
		if (r.transparencyStatus !== "opaque" && r.transparencyStatus !== "transparent") throw Error(`event ${e}.transparencyStatus is invalid`);
		return {
			type: e,
			projectId: n,
			sourceAssetId: B(r.sourceAssetId, `event ${e}.sourceAssetId`),
			workingAssetId: B(r.workingAssetId, `event ${e}.workingAssetId`),
			previewAssetId: B(r.previewAssetId, `event ${e}.previewAssetId`),
			transparencyStatus: r.transparencyStatus
		};
	}
	if (Lt(r, [
		"projectId",
		"assetId",
		"status"
	], `event ${e}`), r.projectId !== n || r.status !== "deleted") throw Error(`event ${e} has an invalid owner or status`);
	return {
		type: e,
		projectId: n,
		assetId: B(r.assetId, `event ${e}.assetId`),
		status: "deleted"
	};
}
var Wt = [
	"compose",
	"cutout",
	"export"
], Gt = [
	"cancel_requested",
	"cancelled",
	"failed",
	"interrupted",
	"queued",
	"running",
	"succeeded"
];
function Kt(e) {
	switch (e) {
		case "operation.queued":
		case "operation.retried":
		case "operation.recovered":
		case "operation.released": return "queued";
		case "operation.running": return "running";
		case "operation.succeeded": return "succeeded";
		case "operation.failed": return "failed";
		case "operation.interrupted": return "interrupted";
	}
}
function qt(e, t) {
	let n = It(e, t);
	if (Lt(n, [
		"code",
		"message",
		"retryable"
	], t), typeof n.retryable != "boolean") throw Error(`${t}.retryable must be a boolean`);
	return {
		code: B(n.code, `${t}.code`),
		message: B(n.message, `${t}.message`),
		retryable: n.retryable
	};
}
function Jt(e, t, n) {
	let r = It(t, `event ${e}`), i = [
		"operationId",
		"operationType",
		"status"
	];
	Rt(r, i, [
		...i,
		"attemptCount",
		"inputAssetId",
		"outputAssetId",
		"safeError",
		"clientRequestFingerprint",
		"reason"
	], `event ${e}`);
	let a = Kt(e);
	if (r.status !== a) throw Error(`event ${e}.status is invalid`);
	if (typeof r.operationType != "string" || !Wt.includes(r.operationType)) throw Error(`event ${e}.operationType is invalid`);
	if (typeof r.status != "string" || !Gt.includes(r.status)) throw Error(`event ${e}.status is invalid`);
	let o = {
		id: B(r.operationId, `event ${e}.operationId`),
		projectId: n,
		operationType: r.operationType,
		status: r.status
	};
	return r.attemptCount !== void 0 && (o.attemptCount = V(r.attemptCount, `event ${e}.attemptCount`)), r.inputAssetId !== void 0 && (o.inputAssetId = B(r.inputAssetId, `event ${e}.inputAssetId`)), r.outputAssetId !== void 0 && (o.outputAssetId = B(r.outputAssetId, `event ${e}.outputAssetId`)), r.safeError !== void 0 && (o.safeError = qt(r.safeError, `event ${e}.safeError`)), {
		type: e,
		projectId: n,
		operation: o
	};
}
function Yt(e, t, n) {
	let r = It(t, `event ${e}`), i = [
		"generationId",
		"generationStatus",
		"totalItems",
		"succeededItems",
		"failedItems",
		"cancelledItems",
		"unknownItems",
		"safeStorageBlockReason"
	];
	Rt(r, i, [
		...i,
		"itemId",
		"itemStatus",
		"outputType",
		"attemptId",
		"attemptNo",
		"attemptStatus",
		"providerResultStage",
		"safeErrorCode",
		"safeErrorSummary"
	], `event ${e}`);
	let a = (e, t) => e === null ? null : B(e, t), o = {
		id: B(r.generationId, `event ${e}.generationId`),
		status: B(r.generationStatus, `event ${e}.generationStatus`),
		totalItems: V(r.totalItems, `event ${e}.totalItems`),
		succeededItems: V(r.succeededItems, `event ${e}.succeededItems`),
		failedItems: V(r.failedItems, `event ${e}.failedItems`),
		cancelledItems: V(r.cancelledItems, `event ${e}.cancelledItems`),
		unknownItems: V(r.unknownItems, `event ${e}.unknownItems`),
		safeStorageBlockReason: a(r.safeStorageBlockReason, `event ${e}.safeStorageBlockReason`)
	};
	return r.itemId !== void 0 && (o.itemId = B(r.itemId, `event ${e}.itemId`)), r.itemStatus !== void 0 && (o.itemStatus = B(r.itemStatus, `event ${e}.itemStatus`)), r.attemptId !== void 0 && (o.attemptId = B(r.attemptId, `event ${e}.attemptId`)), r.safeErrorSummary !== void 0 && (o.safeErrorSummary = a(r.safeErrorSummary, `event ${e}.safeErrorSummary`)), {
		type: e,
		projectId: n,
		generation: o
	};
}
function Xt(e, t) {
	return e === null ? null : B(e, t);
}
function Zt(e) {
	let t = It(e, "snapshot generation");
	if (Lt(t, [
		"id",
		"status",
		"mode",
		"totalItems",
		"succeededItems",
		"failedItems",
		"cancelledItems",
		"unknownItems",
		"safeStorageBlockReason",
		"createdAt",
		"updatedAt",
		"completedAt",
		"items"
	], "snapshot generation"), t.mode !== "complete_set" && t.mode !== "advanced") throw Error("snapshot generation.mode is invalid");
	if (!Array.isArray(t.items)) throw Error("snapshot generation.items must be an array");
	for (let e of t.items) {
		let t = It(e, "snapshot generation item");
		Lt(t, [
			"id",
			"ordinal",
			"outputType",
			"boardId",
			"nodeId",
			"status",
			"attemptCount",
			"latestBackgroundAssetId",
			"latestComposedAssetId",
			"safeErrorCode",
			"safeErrorSummary",
			"latestAttempt"
		], "snapshot generation item"), B(t.id, "snapshot generation item.id"), V(t.ordinal, "snapshot generation item.ordinal"), B(t.outputType, "snapshot generation item.outputType"), B(t.boardId, "snapshot generation item.boardId"), B(t.nodeId, "snapshot generation item.nodeId"), B(t.status, "snapshot generation item.status"), V(t.attemptCount, "snapshot generation item.attemptCount"), zt(t.latestBackgroundAssetId, "snapshot generation item.latestBackgroundAssetId"), zt(t.latestComposedAssetId, "snapshot generation item.latestComposedAssetId"), zt(t.safeErrorCode, "snapshot generation item.safeErrorCode"), zt(t.safeErrorSummary, "snapshot generation item.safeErrorSummary"), t.latestAttempt !== null && It(t.latestAttempt, "snapshot generation item.latestAttempt");
	}
	return Xt(t.createdAt, "snapshot generation.createdAt"), Xt(t.updatedAt, "snapshot generation.updatedAt"), Xt(t.completedAt, "snapshot generation.completedAt"), {
		id: B(t.id, "snapshot generation.id"),
		status: B(t.status, "snapshot generation.status"),
		totalItems: V(t.totalItems, "snapshot generation.totalItems"),
		succeededItems: V(t.succeededItems, "snapshot generation.succeededItems"),
		failedItems: V(t.failedItems, "snapshot generation.failedItems"),
		cancelledItems: V(t.cancelledItems, "snapshot generation.cancelledItems"),
		unknownItems: V(t.unknownItems, "snapshot generation.unknownItems"),
		safeStorageBlockReason: zt(t.safeStorageBlockReason, "snapshot generation.safeStorageBlockReason")
	};
}
function Qt(e, t) {
	let n = It(e, "snapshot event"), r = n.operations ?? [], i = n.generations;
	Rt(n, [
		"project",
		"skus",
		"revision"
	], [
		"project",
		"skus",
		"revision",
		"operations",
		"generations",
		"highWaterEventId"
	], "snapshot event");
	let a = Ye({
		project: n.project,
		skus: n.skus,
		revision: n.revision
	});
	if (a.project.id !== t) throw Error("snapshot event belongs to another project");
	if (!Array.isArray(r)) throw Error("snapshot event.operations must be an array");
	let o = r.map((e, t) => vt(e, `snapshot event.operations[${t}]`));
	if (o.some((e) => e.projectId !== t)) throw Error("snapshot operation belongs to another project");
	if (i !== void 0 && !Array.isArray(i)) throw Error("snapshot event.generations must be an array");
	let s = i === void 0 ? void 0 : i.map(Zt);
	return {
		type: "snapshot",
		snapshot: a,
		operations: o,
		...s === void 0 ? {} : { generations: s }
	};
}
function $t({ apiBase: e, projectId: t, onEvent: n, onError: r, eventSourceFactory: i = (e) => new EventSource(e) }) {
	let a = i(`${e.replace(/\/+$/, "")}/projects/${encodeURIComponent(t)}/events`), o = !0, s = /* @__PURE__ */ new Map(), c = (e, t) => {
		let i = (e) => {
			if (!(!o || !(e instanceof MessageEvent))) try {
				let r = JSON.parse(String(e.data));
				o && n(t(r));
			} catch (e) {
				o && r?.(e);
			}
		};
		s.set(e, i), a.addEventListener(e, i);
	};
	for (let e of jt) c(e, (n) => Ht(e, n, t));
	for (let e of Mt) c(e, (n) => Ut(e, n, t));
	for (let e of Nt) c(e, (n) => Jt(e, n, t));
	for (let e of Pt) c(e, (n) => Yt(e, n, t));
	c("snapshot", (e) => Qt(e, t));
	let l = (e) => {
		o && r?.(e);
	};
	return s.set("error", l), a.addEventListener("error", l), { close: () => {
		if (o) {
			o = !1;
			for (let [e, t] of s) a.removeEventListener(e, t);
			s.clear(), a.close();
		}
	} };
}
//#endregion
//#region frontend/canvas/src/api/skus.ts
function en(e) {
	return e instanceof DOMException && e.name === "AbortError" || typeof e == "object" && !!e && "name" in e && e.name === "AbortError";
}
function tn(e) {
	return typeof e == "object" && e && "code" in e && e.code === "canvas_revision_conflict" && "currentRevision" in e && typeof e.currentRevision == "number" && Number.isInteger(e.currentRevision) ? {
		ok: !1,
		kind: "conflict",
		currentRevision: e.currentRevision
	} : null;
}
function nn({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
	let n = e.replace(/\/+$/, ""), r = (e, t) => {
		let r = `${n}/projects/${encodeURIComponent(e)}/skus`;
		return t === void 0 ? r : `${r}/${encodeURIComponent(t)}`;
	}, i = async (e, n, r, i) => {
		let a;
		try {
			a = await t(e, {
				method: n,
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify(r)
			});
		} catch (e) {
			if (en(e)) throw e;
			return {
				ok: !1,
				kind: "offline",
				message: "网络不可用，请检查连接后重试"
			};
		}
		let o = null;
		try {
			o = await a.json();
		} catch {}
		if (!a.ok) return tn(o) ?? {
			ok: !1,
			kind: "server",
			message: `SKU 请求失败 (${a.status})`
		};
		let s;
		try {
			if (s = Ye(o), s.project.id !== i) throw Error("SKU response belongs to another project");
		} catch {
			return {
				ok: !1,
				kind: "server",
				message: "SKU 服务返回了无效响应"
			};
		}
		return {
			ok: !0,
			snapshot: s
		};
	};
	return {
		createSku: (e, t, n) => i(r(e), "POST", {
			revision: t,
			name: n.name,
			referenceAssetId: n.referenceAssetId ?? null,
			prompt: n.prompt ?? "",
			config: n.config ?? {}
		}, e),
		updateSku: (e, t, n, a) => i(r(e, t), "PATCH", {
			revision: n,
			...a
		}, e),
		deleteSku: (e, t, n) => i(r(e, t), "DELETE", { revision: n }, e)
	};
}
//#endregion
//#region node_modules/fabric/dist/index.min.mjs
var rn = Object.defineProperty, an = (e, t) => {
	let n = {};
	for (var r in e) rn(n, r, {
		get: e[r],
		enumerable: !0
	});
	return t || rn(n, Symbol.toStringTag, { value: "Module" }), n;
};
function on(e) {
	return on = typeof Symbol == "function" && typeof Symbol.iterator == "symbol" ? function(e) {
		return typeof e;
	} : function(e) {
		return e && typeof Symbol == "function" && e.constructor === Symbol && e !== Symbol.prototype ? "symbol" : typeof e;
	}, on(e);
}
function sn(e) {
	var t = function(e, t) {
		if (on(e) != "object" || !e) return e;
		var n = e[Symbol.toPrimitive];
		if (n !== void 0) {
			var r = n.call(e, t || "default");
			if (on(r) != "object") return r;
			throw TypeError("@@toPrimitive must return a primitive value.");
		}
		return (t === "string" ? String : Number)(e);
	}(e, "string");
	return on(t) == "symbol" ? t : t + "";
}
function H(e, t, n) {
	return (t = sn(t)) in e ? Object.defineProperty(e, t, {
		value: n,
		enumerable: !0,
		configurable: !0,
		writable: !0
	}) : e[t] = n, e;
}
var cn = class {
	constructor() {
		H(this, "browserShadowBlurConstant", 1), H(this, "DPI", 96), H(this, "devicePixelRatio", typeof window < "u" ? window.devicePixelRatio : 1), H(this, "perfLimitSizeTotal", 2097152), H(this, "maxCacheSideLimit", 4096), H(this, "minCacheSideLimit", 256), H(this, "disableStyleCopyPaste", !1), H(this, "enableGLFiltering", !0), H(this, "textureSize", 4096), H(this, "forceGLPutImageData", !1), H(this, "cachesBoundsOfCurve", !1), H(this, "fontPaths", {}), H(this, "NUM_FRACTION_DIGITS", 4);
	}
}, U = new class extends cn {
	constructor(e) {
		super(), this.configure(e);
	}
	configure(e = {}) {
		Object.assign(this, e);
	}
	addFonts(e = {}) {
		this.fontPaths = {
			...this.fontPaths,
			...e
		};
	}
	removeFonts(e = []) {
		e.forEach((e) => {
			delete this.fontPaths[e];
		});
	}
	clearFonts() {
		this.fontPaths = {};
	}
	restoreDefaults(e) {
		let t = new cn(), n = e?.reduce((e, n) => (e[n] = t[n], e), {}) || t;
		this.configure(n);
	}
}(), ln = (e, ...t) => console[e]("fabric", ...t), un = class extends Error {
	constructor(e, t) {
		super(`fabric: ${e}`, t);
	}
}, dn = class extends un {
	constructor(e) {
		super(`${e} 'options.signal' is in 'aborted' state`);
	}
}, fn = class {}, pn = class extends fn {
	testPrecision(e, t) {
		let n = `precision ${t} float;\nvoid main(){}`, r = e.createShader(e.FRAGMENT_SHADER);
		return !!r && (e.shaderSource(r, n), e.compileShader(r), !!e.getShaderParameter(r, e.COMPILE_STATUS));
	}
	queryWebGL(e) {
		let t = e.getContext("webgl");
		t && (this.maxTextureSize = t.getParameter(t.MAX_TEXTURE_SIZE), this.GLPrecision = [
			"highp",
			"mediump",
			"lowp"
		].find((e) => this.testPrecision(t, e)), t.getExtension("WEBGL_lose_context").loseContext(), ln("log", `WebGL: max texture size ${this.maxTextureSize}`));
	}
	isSupported(e) {
		return !!this.maxTextureSize && this.maxTextureSize >= e;
	}
}, mn = {}, hn, gn = () => hn ||= {
	document,
	window,
	isTouchSupported: "ontouchstart" in window || "ontouchstart" in document || window && window.navigator && window.navigator.maxTouchPoints > 0,
	WebGLProbe: new pn(),
	dispose() {},
	copyPasteData: mn
}, _n = () => gn().document, vn = () => gn().window, yn = () => Math.max(U.devicePixelRatio ?? vn().devicePixelRatio, 1), bn = new class {
	constructor() {
		H(this, "boundsOfCurveCache", {}), this.charWidthsCache = /* @__PURE__ */ new Map();
	}
	getFontCache({ fontFamily: e, fontStyle: t, fontWeight: n }) {
		e = e.toLowerCase();
		let r = this.charWidthsCache;
		r.has(e) || r.set(e, /* @__PURE__ */ new Map());
		let i = r.get(e), a = `${t.toLowerCase()}_${(n + "").toLowerCase()}`;
		return i.has(a) || i.set(a, /* @__PURE__ */ new Map()), i.get(a);
	}
	clearFontCache(e) {
		e ? this.charWidthsCache.delete((e || "").toLowerCase()) : this.charWidthsCache = /* @__PURE__ */ new Map();
	}
	limitDimsByArea(e) {
		let { perfLimitSizeTotal: t } = U, n = Math.sqrt(t * e);
		return [Math.floor(n), Math.floor(t / n)];
	}
}(), xn = "7.4.0";
function Sn() {}
var Cn = Math.PI / 2, wn = Math.PI / 4, Tn = 2 * Math.PI, En = Math.PI / 180, Dn = Object.freeze([
	1,
	0,
	0,
	1,
	0,
	0
]), W = "center", G = "left", On = "bottom", kn = "right", An = "none", jn = /\r?\n/, Mn = "moving", Nn = "scaling", Pn = "rotating", Fn = "rotate", In = "skewing", Ln = "resizing", Rn = "modifyPoly", zn = "changed", Bn = "scale", Vn = "scaleX", Hn = "scaleY", Un = "skewX", Wn = "skewY", Gn = "fill", Kn = "stroke", qn = "modified", Jn = "normal", Yn = "json", K = new class {
	constructor() {
		this[Yn] = /* @__PURE__ */ new Map(), this.svg = /* @__PURE__ */ new Map();
	}
	has(e) {
		return this[Yn].has(e);
	}
	getClass(e) {
		let t = this[Yn].get(e);
		if (!t) throw new un(`No class registered for ${e}`);
		return t;
	}
	setClass(e, t) {
		t ? this[Yn].set(t, e) : (this[Yn].set(e.type, e), this[Yn].set(e.type.toLowerCase(), e));
	}
	getSVGClass(e) {
		return this.svg.get(e);
	}
	setSVGClass(e, t) {
		this.svg.set(t ?? e.type.toLowerCase(), e);
	}
}(), Xn = new class extends Array {
	remove(e) {
		let t = this.indexOf(e);
		t > -1 && this.splice(t, 1);
	}
	cancelAll() {
		let e = this.splice(0);
		return e.forEach((e) => e.abort()), e;
	}
	cancelByCanvas(e) {
		if (!e) return [];
		let t = this.filter((t) => t.target === e || typeof t.target == "object" && t.target?.canvas === e);
		return t.forEach((e) => e.abort()), t;
	}
	cancelByTarget(e) {
		if (!e) return [];
		let t = this.filter((t) => t.target === e);
		return t.forEach((e) => e.abort()), t;
	}
}(), Zn = class {
	constructor() {
		H(this, "__eventListeners", {});
	}
	on(e, t) {
		if (this.__eventListeners ||= {}, typeof e == "object") return Object.entries(e).forEach(([e, t]) => {
			this.on(e, t);
		}), () => this.off(e);
		if (t) {
			let n = e;
			return this.__eventListeners[n] || (this.__eventListeners[n] = []), this.__eventListeners[n].push(t), () => this.off(n, t);
		}
		return () => !1;
	}
	once(e, t) {
		if (typeof e == "object") {
			let t = [];
			return Object.entries(e).forEach(([e, n]) => {
				t.push(this.once(e, n));
			}), () => t.forEach((e) => e());
		}
		if (t) {
			let n = this.on(e, function(...e) {
				t.call(this, ...e), n();
			});
			return n;
		}
		return () => !1;
	}
	_removeEventListener(e, t) {
		if (this.__eventListeners[e]) if (t) {
			let n = this.__eventListeners[e], r = n.indexOf(t);
			r > -1 && n.splice(r, 1);
		} else this.__eventListeners[e] = [];
	}
	off(e, t) {
		if (this.__eventListeners) if (e === void 0) for (let e in this.__eventListeners) this._removeEventListener(e);
		else typeof e == "object" ? Object.entries(e).forEach(([e, t]) => {
			this._removeEventListener(e, t);
		}) : this._removeEventListener(e, t);
	}
	fire(e, t) {
		if (!this.__eventListeners) return;
		let n = this.__eventListeners[e]?.concat();
		if (n) for (let e = 0; e < n.length; e++) n[e].call(this, t || {});
	}
}, Qn = (e, t) => {
	let n = e.indexOf(t);
	return n !== -1 && e.splice(n, 1), e;
}, $n = (e) => {
	if (e === 0) return 1;
	switch (Math.abs(e) / Cn) {
		case 1:
		case 3: return 0;
		case 2: return -1;
	}
	return Math.cos(e);
}, er = (e) => {
	if (e === 0) return 0;
	let t = e / Cn, n = Math.sign(e);
	switch (t) {
		case 1: return n;
		case 2: return 0;
		case 3: return -n;
	}
	return Math.sin(e);
}, q = class e {
	constructor(e = 0, t = 0) {
		typeof e == "object" ? (this.x = e.x, this.y = e.y) : (this.x = e, this.y = t);
	}
	add(t) {
		return new e(this.x + t.x, this.y + t.y);
	}
	addEquals(e) {
		return this.x += e.x, this.y += e.y, this;
	}
	scalarAdd(t) {
		return new e(this.x + t, this.y + t);
	}
	scalarAddEquals(e) {
		return this.x += e, this.y += e, this;
	}
	subtract(t) {
		return new e(this.x - t.x, this.y - t.y);
	}
	subtractEquals(e) {
		return this.x -= e.x, this.y -= e.y, this;
	}
	scalarSubtract(t) {
		return new e(this.x - t, this.y - t);
	}
	scalarSubtractEquals(e) {
		return this.x -= e, this.y -= e, this;
	}
	multiply(t) {
		return new e(this.x * t.x, this.y * t.y);
	}
	scalarMultiply(t) {
		return new e(this.x * t, this.y * t);
	}
	scalarMultiplyEquals(e) {
		return this.x *= e, this.y *= e, this;
	}
	divide(t) {
		return new e(this.x / t.x, this.y / t.y);
	}
	scalarDivide(t) {
		return new e(this.x / t, this.y / t);
	}
	scalarDivideEquals(e) {
		return this.x /= e, this.y /= e, this;
	}
	eq(e) {
		return this.x === e.x && this.y === e.y;
	}
	lt(e) {
		return this.x < e.x && this.y < e.y;
	}
	lte(e) {
		return this.x <= e.x && this.y <= e.y;
	}
	gt(e) {
		return this.x > e.x && this.y > e.y;
	}
	gte(e) {
		return this.x >= e.x && this.y >= e.y;
	}
	lerp(t, n = .5) {
		return n = Math.max(Math.min(1, n), 0), new e(this.x + (t.x - this.x) * n, this.y + (t.y - this.y) * n);
	}
	distanceFrom(e) {
		let t = this.x - e.x, n = this.y - e.y;
		return Math.sqrt(t * t + n * n);
	}
	midPointFrom(e) {
		return this.lerp(e);
	}
	min(t) {
		return new e(Math.min(this.x, t.x), Math.min(this.y, t.y));
	}
	max(t) {
		return new e(Math.max(this.x, t.x), Math.max(this.y, t.y));
	}
	toString() {
		return `${this.x},${this.y}`;
	}
	setXY(e, t) {
		return this.x = e, this.y = t, this;
	}
	setX(e) {
		return this.x = e, this;
	}
	setY(e) {
		return this.y = e, this;
	}
	setFromPoint(e) {
		return this.x = e.x, this.y = e.y, this;
	}
	swap(e) {
		let t = this.x, n = this.y;
		this.x = e.x, this.y = e.y, e.x = t, e.y = n;
	}
	clone() {
		return new e(this.x, this.y);
	}
	rotate(t, n = tr) {
		let r = er(t), i = $n(t), a = this.subtract(n);
		return new e(a.x * i - a.y * r, a.x * r + a.y * i).add(n);
	}
	transform(t, n = !1) {
		return new e(t[0] * this.x + t[2] * this.y + (n ? 0 : t[4]), t[1] * this.x + t[3] * this.y + (n ? 0 : t[5]));
	}
}, tr = new q(0, 0), nr = (e) => !!e && Array.isArray(e._objects);
function rr(e) {
	class t extends e {
		constructor(...e) {
			super(...e), H(this, "_objects", []);
		}
		_onObjectAdded(e) {}
		_onObjectRemoved(e) {}
		_onStackOrderChanged(e) {}
		add(...e) {
			let t = this._objects.push(...e);
			return e.forEach((e) => this._onObjectAdded(e)), t;
		}
		insertAt(e, ...t) {
			return this._objects.splice(e, 0, ...t), t.forEach((e) => this._onObjectAdded(e)), this._objects.length;
		}
		remove(...e) {
			let t = this._objects, n = [];
			return e.forEach((e) => {
				let r = t.indexOf(e);
				r !== -1 && (t.splice(r, 1), n.push(e), this._onObjectRemoved(e));
			}), n;
		}
		forEachObject(e) {
			this.getObjects().forEach((t, n, r) => e(t, n, r));
		}
		getObjects(...e) {
			return e.length === 0 ? [...this._objects] : this._objects.filter((t) => t.isType(...e));
		}
		item(e) {
			return this._objects[e];
		}
		isEmpty() {
			return this._objects.length === 0;
		}
		size() {
			return this._objects.length;
		}
		contains(e, n) {
			return !!this._objects.includes(e) || !!n && this._objects.some((n) => n instanceof t && n.contains(e, !0));
		}
		complexity() {
			return this._objects.reduce((e, t) => e += t.complexity ? t.complexity() : 0, 0);
		}
		sendObjectToBack(e) {
			return !(!e || e === this._objects[0]) && (Qn(this._objects, e), this._objects.unshift(e), this._onStackOrderChanged(e), !0);
		}
		bringObjectToFront(e) {
			return !(!e || e === this._objects[this._objects.length - 1]) && (Qn(this._objects, e), this._objects.push(e), this._onStackOrderChanged(e), !0);
		}
		sendObjectBackwards(e, t) {
			if (!e) return !1;
			let n = this._objects.indexOf(e);
			if (n !== 0) {
				let r = this.findNewLowerIndex(e, n, t);
				return Qn(this._objects, e), this._objects.splice(r, 0, e), this._onStackOrderChanged(e), !0;
			}
			return !1;
		}
		bringObjectForward(e, t) {
			if (!e) return !1;
			let n = this._objects.indexOf(e);
			if (n !== this._objects.length - 1) {
				let r = this.findNewUpperIndex(e, n, t);
				return Qn(this._objects, e), this._objects.splice(r, 0, e), this._onStackOrderChanged(e), !0;
			}
			return !1;
		}
		moveObjectTo(e, t) {
			return e !== this._objects[t] && (Qn(this._objects, e), this._objects.splice(t, 0, e), this._onStackOrderChanged(e), !0);
		}
		findNewLowerIndex(e, t, n) {
			let r;
			if (n) {
				r = t;
				for (let n = t - 1; n >= 0; --n) if (e.isOverlapping(this._objects[n])) {
					r = n;
					break;
				}
			} else r = t - 1;
			return r;
		}
		findNewUpperIndex(e, t, n) {
			let r;
			if (n) {
				r = t;
				for (let n = t + 1; n < this._objects.length; ++n) if (e.isOverlapping(this._objects[n])) {
					r = n;
					break;
				}
			} else r = t + 1;
			return r;
		}
		collectObjects({ left: e, top: t, width: n, height: r }, { includeIntersecting: i = !0 } = {}) {
			let a = [], o = new q(e, t), s = o.add(new q(n, r));
			for (let e = this._objects.length - 1; e >= 0; e--) {
				let t = this._objects[e];
				t.selectable && t.visible && (i && t.intersectsWithRect(o, s) || t.isContainedWithinRect(o, s) || i && t.containsPoint(o) || i && t.containsPoint(s)) && a.push(t);
			}
			return a;
		}
	}
	return t;
}
var ir = class extends Zn {
	_setOptions(e = {}) {
		for (let t in e) this.set(t, e[t]);
	}
	_setObject(e) {
		for (let t in e) this._set(t, e[t]);
	}
	set(e, t) {
		return typeof e == "object" ? this._setObject(e) : this._set(e, t), this;
	}
	_set(e, t) {
		this[e] = t;
	}
	toggle(e) {
		let t = this.get(e);
		return typeof t == "boolean" && this.set(e, !t), this;
	}
	get(e) {
		return this[e];
	}
};
function ar(e) {
	return vn().requestAnimationFrame(e);
}
function or(e) {
	return vn().cancelAnimationFrame(e);
}
var sr = 0, cr = () => sr++, lr = () => {
	let e = _n().createElement("canvas");
	if (!e || e.getContext === void 0) throw new un("Failed to create `canvas` element");
	return e;
}, ur = () => _n().createElement("img"), dr = (e) => {
	var t;
	let n = fr(e);
	return (t = n.getContext("2d")) == null || t.drawImage(e, 0, 0), n;
}, fr = (e) => {
	let t = lr();
	return t.width = e.width, t.height = e.height, t;
}, pr = (e, t, n) => e.toDataURL(`image/${t}`, n), mr = (e, t, n) => new Promise((r, i) => {
	e.toBlob(r, `image/${t}`, n);
}), J = (e) => e * En, hr = (e) => e / En, gr = (e) => e.every((e, t) => e === Dn[t]), _r = (e, t, n) => new q(e).transform(t, n), vr = (e) => {
	let t = 1 / (e[0] * e[3] - e[1] * e[2]), n = [
		t * e[3],
		-t * e[1],
		-t * e[2],
		t * e[0],
		0,
		0
	], { x: r, y: i } = new q(e[4], e[5]).transform(n, !0);
	return n[4] = -r, n[5] = -i, n;
}, Y = (e, t, n) => [
	e[0] * t[0] + e[2] * t[1],
	e[1] * t[0] + e[3] * t[1],
	e[0] * t[2] + e[2] * t[3],
	e[1] * t[2] + e[3] * t[3],
	n ? 0 : e[0] * t[4] + e[2] * t[5] + e[4],
	n ? 0 : e[1] * t[4] + e[3] * t[5] + e[5]
], yr = (e, t) => e.reduceRight((e, n) => n && e ? Y(n, e, t) : n || e, void 0) || Dn.concat(), br = ([e, t]) => Math.atan2(t, e), xr = ([e, t]) => Math.sqrt(e * e + t * t), Sr = ([, , e, t]) => Math.sqrt(e * e + t * t), Cr = (e) => {
	let t = br(e), n = e[0] ** 2 + e[1] ** 2, r = Math.sqrt(n), i = (e[0] * e[3] - e[2] * e[1]) / r, a = Math.atan2(e[0] * e[2] + e[1] * e[3], n);
	return {
		angle: hr(t),
		scaleX: r,
		scaleY: i,
		skewX: hr(a),
		skewY: 0,
		translateX: e[4] || 0,
		translateY: e[5] || 0
	};
}, wr = (e, t = 0) => [
	1,
	0,
	0,
	1,
	e,
	t
];
function Tr({ angle: e = 0 } = {}, { x: t = 0, y: n = 0 } = {}) {
	let r = J(e), i = $n(r), a = er(r);
	return [
		i,
		a,
		-a,
		i,
		t ? t - (i * t - a * n) : 0,
		n ? n - (a * t + i * n) : 0
	];
}
var Er = (e, t = e) => [
	e,
	0,
	0,
	t,
	0,
	0
], Dr = (e) => Math.tan(J(e)), Or = (e) => [
	1,
	0,
	Dr(e),
	1,
	0,
	0
], kr = (e) => [
	1,
	Dr(e),
	0,
	1,
	0,
	0
], Ar = ({ scaleX: e = 1, scaleY: t = 1, flipX: n = !1, flipY: r = !1, skewX: i = 0, skewY: a = 0 }) => {
	let o = Er(n ? -e : e, r ? -t : t);
	return i && (o = Y(o, Or(i), !0)), a && (o = Y(o, kr(a), !0)), o;
}, jr = (e) => {
	let { translateX: t = 0, translateY: n = 0, angle: r = 0 } = e, i = wr(t, n);
	r && (i = Y(i, Tr({ angle: r })));
	let a = Ar(e);
	return gr(a) || (i = Y(i, a)), i;
}, Mr = (e, { signal: t, crossOrigin: n = null } = {}) => new Promise(function(r, i) {
	if (t && t.aborted) return i(new dn("loadImage"));
	let a = ur(), o;
	t && (o = function(e) {
		a.src = "", i(e);
	}, t.addEventListener("abort", o, { once: !0 }));
	let s = function() {
		a.onload = a.onerror = null, o && t?.removeEventListener("abort", o), r(a);
	};
	e ? (a.onload = s, a.onerror = function() {
		o && t?.removeEventListener("abort", o), i(new un(`Error loading ${a.src}`));
	}, n && (a.crossOrigin = n), a.src = e) : s();
}), Nr = (e, { signal: t, reviver: n = Sn } = {}) => new Promise((r, i) => {
	let a = [];
	t && t.addEventListener("abort", i, { once: !0 }), Promise.allSettled(e.map((e) => K.getClass(e.type).fromObject(e, { signal: t }))).then(async (t) => {
		for (let [r, i] of t.entries()) if (i.status === "fulfilled" && (await n(e[r], i.value), a.push(i.value)), i.status === "rejected") {
			let t = await n(e[r], void 0, i.reason);
			t && a.push(t);
		}
		r(a);
	}).catch((e) => {
		a.forEach((e) => {
			e.dispose && e.dispose();
		}), i(e);
	}).finally(() => {
		t && t.removeEventListener("abort", i);
	});
}), Pr = (e, { signal: t } = {}) => new Promise((n, r) => {
	let i = [];
	t && t.addEventListener("abort", r, { once: !0 });
	let a = Object.values(e).map((e) => e && e.type && K.has(e.type) ? Nr([e], { signal: t }).then(([e]) => (i.push(e), e)) : e), o = Object.keys(e);
	Promise.all(a).then((e) => e.reduce((e, t, n) => (e[o[n]] = t, e), {})).then(n).catch((e) => {
		i.forEach((e) => {
			e.dispose && e.dispose();
		}), r(e);
	}).finally(() => {
		t && t.removeEventListener("abort", r);
	});
}), Fr = (e, t = []) => t.reduce((t, n) => (n in e && (t[n] = e[n]), t), {}), Ir = (e, t) => Object.keys(e).reduce((n, r) => (t(e[r], r, e) && (n[r] = e[r]), n), {}), X = (e, t) => parseFloat(Number(e).toFixed(t)), Lr = (e) => "matrix(" + e.map((e) => X(e, U.NUM_FRACTION_DIGITS)).join(" ") + ")", Rr = (e) => !!e && e.toLive !== void 0, zr = (e) => !!e && typeof e.toObject == "function", Br = (e) => !!e && e.offsetX !== void 0 && "source" in e, Vr = (e) => !!e && "multiSelectionStacking" in e;
function Hr(e) {
	let t = e && Ur(e), n = 0, r = 0;
	if (!e || !t) return {
		left: n,
		top: r
	};
	let i = e, a = t.documentElement, o = t.body || {
		scrollLeft: 0,
		scrollTop: 0
	};
	for (; i && (i.parentNode || i.host) && (i = i.parentNode || i.host, i === t ? (n = o.scrollLeft || a.scrollLeft || 0, r = o.scrollTop || a.scrollTop || 0) : (n += i.scrollLeft || 0, r += i.scrollTop || 0), i.nodeType !== 1 || i.style.position !== "fixed"););
	return {
		left: n,
		top: r
	};
}
var Ur = (e) => e.ownerDocument || null, Wr = (e) => e.ownerDocument?.defaultView || null, Gr = (e, t, { width: n, height: r }, i = 1) => {
	e.width = n, e.height = r, i > 1 && (e.setAttribute("width", (n * i).toString()), e.setAttribute("height", (r * i).toString()), t.scale(i, i));
}, Kr = (e, { width: t, height: n }) => {
	t && (e.style.width = typeof t == "number" ? `${t}px` : t), n && (e.style.height = typeof n == "number" ? `${n}px` : n);
};
function qr(e) {
	return e.onselectstart !== void 0 && (e.onselectstart = () => !1), e.style.userSelect = An, e;
}
var Jr = class {
	constructor(e) {
		H(this, "_originalCanvasStyle", void 0), H(this, "lower", void 0);
		let t = this.createLowerCanvas(e);
		this.lower = {
			el: t,
			ctx: t.getContext("2d")
		};
	}
	createLowerCanvas(e) {
		let t = (n = e) && n.getContext !== void 0 ? e : e && _n().getElementById(e) || lr();
		var n;
		if (t.hasAttribute("data-fabric")) throw new un("Trying to initialize a canvas that has already been initialized. Did you forget to dispose the canvas?");
		return this._originalCanvasStyle = t.style.cssText, t.setAttribute("data-fabric", "main"), t.classList.add("lower-canvas"), t;
	}
	cleanupDOM({ width: e, height: t }) {
		let { el: n } = this.lower;
		n.classList.remove("lower-canvas"), n.removeAttribute("data-fabric"), n.setAttribute("width", `${e}`), n.setAttribute("height", `${t}`), n.style.cssText = this._originalCanvasStyle || "", this._originalCanvasStyle = void 0;
	}
	setDimensions(e, t) {
		let { el: n, ctx: r } = this.lower;
		Gr(n, r, e, t);
	}
	setCSSDimensions(e) {
		Kr(this.lower.el, e);
	}
	calcOffset() {
		return function(e) {
			let t = e && Ur(e), n = {
				left: 0,
				top: 0
			};
			if (!t) return n;
			let r = Wr(e)?.getComputedStyle(e, null) || {};
			n.left += parseInt(r.borderLeftWidth, 10) || 0, n.top += parseInt(r.borderTopWidth, 10) || 0, n.left += parseInt(r.paddingLeft, 10) || 0, n.top += parseInt(r.paddingTop, 10) || 0;
			let i = {
				left: 0,
				top: 0
			}, a = t.documentElement;
			e.getBoundingClientRect !== void 0 && (i = e.getBoundingClientRect());
			let o = Hr(e);
			return {
				left: i.left + o.left - (a.clientLeft || 0) + n.left,
				top: i.top + o.top - (a.clientTop || 0) + n.top
			};
		}(this.lower.el);
	}
	dispose() {
		gn().dispose(this.lower.el), delete this.lower;
	}
}, Yr = {
	backgroundVpt: !0,
	backgroundColor: "",
	overlayVpt: !0,
	overlayColor: "",
	includeDefaultValues: !0,
	svgViewportTransformation: !0,
	renderOnAddRemove: !0,
	skipOffscreen: !0,
	enableRetinaScaling: !0,
	imageSmoothingEnabled: !0,
	controlsAboveOverlay: !1,
	allowTouchScrolling: !1,
	viewportTransform: [...Dn],
	patternQuality: "best"
}, Xr = an({
	capitalize: () => Zr,
	escapeXml: () => Z,
	graphemeSplit: () => $r
}), Zr = (e, t = !1) => `${e.charAt(0).toUpperCase()}${t ? e.slice(1) : e.slice(1).toLowerCase()}`, Z = (e) => e.toString().replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&apos;").replace(/</g, "&lt;").replace(/>/g, "&gt;"), Qr, $r = (e) => {
	if (Qr || Qr || (Qr = "Intl" in vn() && "Segmenter" in Intl && new Intl.Segmenter(void 0, { granularity: "grapheme" })), Qr) {
		let t = Qr.segment(e);
		return Array.from(t).map(({ segment: e }) => e);
	}
	return ei(e);
}, ei = (e) => {
	let t = [];
	for (let n, r = 0; r < e.length; r++) !1 !== (n = ti(e, r)) && t.push(n);
	return t;
}, ti = (e, t) => {
	let n = e.charCodeAt(t);
	if (isNaN(n)) return "";
	if (n < 55296 || n > 57343) return e.charAt(t);
	if (55296 <= n && n <= 56319) {
		if (e.length <= t + 1) throw "High surrogate without following low surrogate";
		let n = e.charCodeAt(t + 1);
		if (56320 > n || n > 57343) throw "High surrogate without following low surrogate";
		return e.charAt(t) + e.charAt(t + 1);
	}
	if (t === 0) throw "Low surrogate without preceding high surrogate";
	let r = e.charCodeAt(t - 1);
	if (55296 > r || r > 56319) throw "Low surrogate without preceding high surrogate";
	return !1;
}, ni = class e extends rr(ir) {
	get lowerCanvasEl() {
		return this.elements.lower?.el;
	}
	get contextContainer() {
		return this.elements.lower?.ctx;
	}
	static getDefaults() {
		return e.ownDefaults;
	}
	constructor(e, t = {}) {
		super(), Object.assign(this, this.constructor.getDefaults()), this.set(t), this.initElements(e), this._setDimensionsImpl({
			width: this.width || this.elements.lower.el.width || 0,
			height: this.height || this.elements.lower.el.height || 0
		}), this.skipControlsDrawing = !1, this.viewportTransform = [...this.viewportTransform], this.calcViewportBoundaries();
	}
	initElements(e) {
		this.elements = new Jr(e);
	}
	add(...e) {
		let t = super.add(...e);
		return e.length > 0 && this.renderOnAddRemove && this.requestRenderAll(), t;
	}
	insertAt(e, ...t) {
		let n = super.insertAt(e, ...t);
		return t.length > 0 && this.renderOnAddRemove && this.requestRenderAll(), n;
	}
	remove(...e) {
		let t = super.remove(...e);
		return t.length > 0 && this.renderOnAddRemove && this.requestRenderAll(), t;
	}
	_onObjectAdded(e) {
		e.canvas && e.canvas !== this && (ln("warn", "Canvas is trying to add an object that belongs to a different canvas.\nResulting to default behavior: removing object from previous canvas and adding to new canvas"), e.canvas.remove(e)), e._set("canvas", this), e.setCoords(), this.fire("object:added", { target: e }), e.fire("added", { target: this });
	}
	_onObjectRemoved(e) {
		e._set("canvas", void 0), this.fire("object:removed", { target: e }), e.fire("removed", { target: this });
	}
	_onStackOrderChanged() {
		this.renderOnAddRemove && this.requestRenderAll();
	}
	getRetinaScaling() {
		return this.enableRetinaScaling ? yn() : 1;
	}
	calcOffset() {
		return this._offset = this.elements.calcOffset();
	}
	getWidth() {
		return this.width;
	}
	getHeight() {
		return this.height;
	}
	_setDimensionsImpl(e, { cssOnly: t = !1, backstoreOnly: n = !1 } = {}) {
		if (!t) {
			let t = {
				width: this.width,
				height: this.height,
				...e
			};
			this.elements.setDimensions(t, this.getRetinaScaling()), this.hasLostContext = !0, this.width = t.width, this.height = t.height;
		}
		n || this.elements.setCSSDimensions(e), this.calcOffset();
	}
	setDimensions(e, t) {
		this._setDimensionsImpl(e, t), t && t.cssOnly || this.requestRenderAll();
	}
	getZoom() {
		return xr(this.viewportTransform);
	}
	setViewportTransform(e) {
		this.viewportTransform = e, this.calcViewportBoundaries(), this.renderOnAddRemove && this.requestRenderAll();
	}
	zoomToPoint(e, t) {
		let n = e, r = [...this.viewportTransform], i = _r(e, vr(r));
		r[0] = t, r[3] = t;
		let a = _r(i, r);
		r[4] += n.x - a.x, r[5] += n.y - a.y, this.setViewportTransform(r);
	}
	setZoom(e) {
		this.zoomToPoint(new q(0, 0), e);
	}
	absolutePan(e) {
		let t = [...this.viewportTransform];
		return t[4] = -e.x, t[5] = -e.y, this.setViewportTransform(t);
	}
	relativePan(e) {
		return this.absolutePan(new q(-e.x - this.viewportTransform[4], -e.y - this.viewportTransform[5]));
	}
	getElement() {
		return this.elements.lower.el;
	}
	clearContext(e) {
		e.clearRect(0, 0, this.width, this.height);
	}
	getContext() {
		return this.elements.lower.ctx;
	}
	clear() {
		this.remove(...this.getObjects()), this.backgroundImage = void 0, this.overlayImage = void 0, this.backgroundColor = "", this.overlayColor = "", this.clearContext(this.getContext()), this.fire("canvas:cleared"), this.renderOnAddRemove && this.requestRenderAll();
	}
	renderAll() {
		this.cancelRequestedRender(), this.destroyed || this.renderCanvas(this.getContext(), this._objects);
	}
	renderAndReset() {
		this.nextRenderHandle = 0, this.renderAll();
	}
	requestRenderAll() {
		this.nextRenderHandle || this.disposed || this.destroyed || (this.nextRenderHandle = ar(() => this.renderAndReset()));
	}
	calcViewportBoundaries() {
		let e = this.width, t = this.height, n = vr(this.viewportTransform), r = _r({
			x: 0,
			y: 0
		}, n), i = _r({
			x: e,
			y: t
		}, n), a = r.min(i), o = r.max(i);
		return this.vptCoords = {
			tl: a,
			tr: new q(o.x, a.y),
			bl: new q(a.x, o.y),
			br: o
		};
	}
	cancelRequestedRender() {
		this.nextRenderHandle &&= (or(this.nextRenderHandle), 0);
	}
	drawControls(e) {}
	renderCanvas(e, t) {
		if (this.destroyed) return;
		let n = this.viewportTransform, r = this.clipPath;
		this.calcViewportBoundaries(), this.clearContext(e), e.imageSmoothingEnabled = this.imageSmoothingEnabled, e.patternQuality = this.patternQuality, this.fire("before:render", { ctx: e }), this._renderBackground(e), e.save(), e.transform(n[0], n[1], n[2], n[3], n[4], n[5]), this._renderObjects(e, t), e.restore(), this.controlsAboveOverlay || this.skipControlsDrawing || this.drawControls(e), r && (r._set("canvas", this), r.shouldCache(), r._transformDone = !0, r.renderCache({ forClipping: !0 }), this.drawClipPathOnCanvas(e, r)), this._renderOverlay(e), this.controlsAboveOverlay && !this.skipControlsDrawing && this.drawControls(e), this.fire("after:render", { ctx: e }), this.__cleanupTask &&= (this.__cleanupTask(), void 0);
	}
	drawClipPathOnCanvas(e, t) {
		let n = this.viewportTransform;
		e.save(), e.transform(...n), e.globalCompositeOperation = "destination-in", t.transform(e), e.scale(1 / t.zoomX, 1 / t.zoomY), e.drawImage(t._cacheCanvas, -t.cacheTranslationX, -t.cacheTranslationY), e.restore();
	}
	_renderObjects(e, t) {
		for (let n = 0, r = t.length; n < r; ++n) t[n] && t[n].render(e);
	}
	_renderBackgroundOrOverlay(e, t) {
		let n = this[`${t}Color`], r = this[`${t}Image`], i = this.viewportTransform, a = this[`${t}Vpt`];
		if (!n && !r) return;
		let o = Rr(n);
		if (n) {
			if (e.save(), e.beginPath(), e.moveTo(0, 0), e.lineTo(this.width, 0), e.lineTo(this.width, this.height), e.lineTo(0, this.height), e.closePath(), e.fillStyle = o ? n.toLive(e) : n, a && e.transform(...i), o) {
				e.transform(1, 0, 0, 1, n.offsetX || 0, n.offsetY || 0);
				let t = n.gradientTransform || n.patternTransform;
				t && e.transform(...t);
			}
			e.fill(), e.restore();
		}
		if (r) {
			e.save();
			let { skipOffscreen: t } = this;
			this.skipOffscreen = a, a && e.transform(...i), r.render(e), this.skipOffscreen = t, e.restore();
		}
	}
	_renderBackground(e) {
		this._renderBackgroundOrOverlay(e, "background");
	}
	_renderOverlay(e) {
		this._renderBackgroundOrOverlay(e, "overlay");
	}
	getCenterPoint() {
		return new q(this.width / 2, this.height / 2);
	}
	centerObjectH(e) {
		return this._centerObject(e, new q(this.getCenterPoint().x, e.getCenterPoint().y));
	}
	centerObjectV(e) {
		return this._centerObject(e, new q(e.getCenterPoint().x, this.getCenterPoint().y));
	}
	centerObject(e) {
		return this._centerObject(e, this.getCenterPoint());
	}
	viewportCenterObject(e) {
		return this._centerObject(e, this.getVpCenter());
	}
	viewportCenterObjectH(e) {
		return this._centerObject(e, new q(this.getVpCenter().x, e.getCenterPoint().y));
	}
	viewportCenterObjectV(e) {
		return this._centerObject(e, new q(e.getCenterPoint().x, this.getVpCenter().y));
	}
	getVpCenter() {
		return _r(this.getCenterPoint(), vr(this.viewportTransform));
	}
	_centerObject(e, t) {
		e.setXY(t, W, W), e.setCoords(), this.renderOnAddRemove && this.requestRenderAll();
	}
	toDatalessJSON(e) {
		return this.toDatalessObject(e);
	}
	toObject(e) {
		return this._toObjectMethod("toObject", e);
	}
	toJSON() {
		return this.toObject();
	}
	toDatalessObject(e) {
		return this._toObjectMethod("toDatalessObject", e);
	}
	_toObjectMethod(e, t) {
		let n = this.clipPath, r = n && !n.excludeFromExport ? this._toObject(n, e, t) : null;
		return {
			version: xn,
			...Fr(this, t),
			objects: this._objects.filter((e) => !e.excludeFromExport).map((n) => this._toObject(n, e, t)),
			...this.__serializeBgOverlay(e, t),
			...r ? { clipPath: r } : null
		};
	}
	_toObject(e, t, n) {
		let r;
		this.includeDefaultValues || (r = e.includeDefaultValues, e.includeDefaultValues = !1);
		let i = e[t](n);
		return this.includeDefaultValues || (e.includeDefaultValues = !!r), i;
	}
	__serializeBgOverlay(e, t) {
		let n = {}, r = this.backgroundImage, i = this.overlayImage, a = this.backgroundColor, o = this.overlayColor;
		return Rr(a) ? a.excludeFromExport || (n.background = a.toObject(t)) : a && (n.background = a), Rr(o) ? o.excludeFromExport || (n.overlay = o.toObject(t)) : o && (n.overlay = o), r && !r.excludeFromExport && (n.backgroundImage = this._toObject(r, e, t)), i && !i.excludeFromExport && (n.overlayImage = this._toObject(i, e, t)), n;
	}
	toSVG(e = {}, t) {
		e.reviver = t;
		let n = [];
		return (this._setSVGPreamble(n, e), this._setSVGHeader(n, e), this.clipPath) && n.push(`<g clip-path="url(#${Z(this.clipPath.clipPathId ?? "")})" >\n`), this._setSVGBgOverlayColor(n, "background"), this._setSVGBgOverlayImage(n, "backgroundImage", t), this._setSVGObjects(n, t), this.clipPath && n.push("</g>\n"), this._setSVGBgOverlayColor(n, "overlay"), this._setSVGBgOverlayImage(n, "overlayImage", t), n.push("</svg>"), n.join("");
	}
	_setSVGPreamble(e, t) {
		t.suppressPreamble || e.push("<?xml version=\"1.0\" encoding=\"", t.encoding || "UTF-8", "\" standalone=\"no\" ?>\n", "<!DOCTYPE svg PUBLIC \"-//W3C//DTD SVG 1.1//EN\" ", "\"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd\">\n");
	}
	_setSVGHeader(e, t) {
		let n = t.width || `${this.width}`, r = t.height || `${this.height}`, i = U.NUM_FRACTION_DIGITS, a = t.viewBox, o;
		if (a) o = `viewBox="${a.x} ${a.y} ${a.width} ${a.height}" `;
		else if (this.svgViewportTransformation) {
			let e = this.viewportTransform;
			o = `viewBox="${X(-e[4] / e[0], i)} ${X(-e[5] / e[3], i)} ${X(this.width / e[0], i)} ${X(this.height / e[3], i)}" `;
		} else o = `viewBox="0 0 ${this.width} ${this.height}" `;
		e.push("<svg ", "xmlns=\"http://www.w3.org/2000/svg\" ", "xmlns:xlink=\"http://www.w3.org/1999/xlink\" ", "version=\"1.1\" ", "width=\"", n, "\" ", "height=\"", r, "\" ", o, "xml:space=\"preserve\">\n", "<desc>Created with Fabric.js ", xn, "</desc>\n", "<defs>\n", this.createSVGFontFacesMarkup(), this.createSVGRefElementsMarkup(), this.createSVGClipPathMarkup(t), "</defs>\n");
	}
	createSVGClipPathMarkup(e) {
		let t = this.clipPath;
		return t ? (t.clipPathId = `CLIPPATH_${cr()}`, `<clipPath id="${t.clipPathId}" >\n${t.toClipPathSVG(e.reviver)}</clipPath>\n`) : "";
	}
	createSVGRefElementsMarkup() {
		return ["background", "overlay"].map((e) => {
			let t = this[`${e}Color`];
			if (Rr(t)) {
				let n = this[`${e}Vpt`], r = this.viewportTransform, i = {
					isType: () => !1,
					width: this.width / (n ? r[0] : 1),
					height: this.height / (n ? r[3] : 1)
				};
				return t.toSVG(i, { additionalTransform: n ? Lr(r) : "" });
			}
		}).join("");
	}
	createSVGFontFacesMarkup() {
		let e = [], t = {}, n = U.fontPaths;
		this._objects.forEach(function t(n) {
			e.push(n), nr(n) && n._objects.forEach(t);
		}), e.forEach((e) => {
			if (!(r = e) || typeof r._renderText != "function") return;
			var r;
			let { styles: i, fontFamily: a } = e;
			!t[a] && n[a] && (t[a] = !0, i && Object.values(i).forEach((e) => {
				Object.values(e).forEach(({ fontFamily: e = "" }) => {
					!t[e] && n[e] && (t[e] = !0);
				});
			}));
		});
		let r = Object.keys(t).map((e) => `\t\t@font-face {\n\t\t\tfont-family: '${e}';\n\t\t\tsrc: url('${n[e]}');\n\t\t}\n`).join("");
		return r ? `\t<style type="text/css"><![CDATA[\n${r}]]></style>\n` : "";
	}
	_setSVGObjects(e, t) {
		this.forEachObject((n) => {
			n.excludeFromExport || this._setSVGObject(e, n, t);
		});
	}
	_setSVGObject(e, t, n) {
		e.push(t.toSVG(n));
	}
	_setSVGBgOverlayImage(e, t, n) {
		let r = this[t];
		r && !r.excludeFromExport && r.toSVG && e.push(r.toSVG(n));
	}
	_setSVGBgOverlayColor(e, t) {
		let n = this[`${t}Color`];
		if (n) if (Rr(n)) {
			let r = n.repeat || "", i = this.width, a = this.height, o = this[`${t}Vpt`] ? Lr(vr(this.viewportTransform)) : "";
			e.push(`<rect transform="${o} translate(${i / 2},${a / 2})" x="${n.offsetX - i / 2}" y="${n.offsetY - a / 2}" width="${r !== "repeat-y" && r !== "no-repeat" || !Br(n) ? i : n.source.width}" height="${r !== "repeat-x" && r !== "no-repeat" || !Br(n) ? a : n.source.height}" fill="url(#SVGID_${n.id})"></rect>\n`);
		} else e.push("<rect x=\"0\" y=\"0\" width=\"100%\" height=\"100%\" ", "fill=\"", n, "\"", "></rect>\n");
	}
	loadFromJSON(e, t, { signal: n } = {}) {
		if (!e) return Promise.reject(new un("`json` is undefined"));
		let { objects: r = [], ...i } = typeof e == "string" ? JSON.parse(e) : e, { backgroundImage: a, background: o, overlayImage: s, overlay: c, clipPath: l } = i, u = this.renderOnAddRemove;
		return this.renderOnAddRemove = !1, Promise.all([Nr(r, {
			reviver: t,
			signal: n
		}), Pr({
			backgroundImage: a,
			backgroundColor: o,
			overlayImage: s,
			overlayColor: c,
			clipPath: l
		}, { signal: n })]).then(([e, t]) => (this.clear(), this.add(...e), this.set(i), this.set(t), this.renderOnAddRemove = u, this));
	}
	clone(e) {
		let t = this.toObject(e);
		return this.cloneWithoutData().loadFromJSON(t);
	}
	cloneWithoutData() {
		let e = fr(this);
		return new this.constructor(e);
	}
	toDataURL(e = {}) {
		let { format: t = "png", quality: n = 1, multiplier: r = 1, enableRetinaScaling: i = !1 } = e, a = r * (i ? this.getRetinaScaling() : 1);
		return pr(this.toCanvasElement(a, e), t, n);
	}
	toBlob(e = {}) {
		let { format: t = "png", quality: n = 1, multiplier: r = 1, enableRetinaScaling: i = !1 } = e, a = r * (i ? this.getRetinaScaling() : 1);
		return mr(this.toCanvasElement(a, e), t, n);
	}
	toCanvasElement(e = 1, { width: t, height: n, left: r, top: i, filter: a } = {}) {
		let o = (t || this.width) * e, s = (n || this.height) * e, c = this.getZoom(), l = this.width, u = this.height, d = this.skipControlsDrawing, f = c * e, p = this.viewportTransform, m = [
			f,
			0,
			0,
			f,
			(p[4] - (r || 0)) * e,
			(p[5] - (i || 0)) * e
		], h = this.enableRetinaScaling, g = fr({
			width: o,
			height: s
		}), _ = a ? this._objects.filter((e) => a(e)) : this._objects;
		return this.enableRetinaScaling = !1, this.viewportTransform = m, this.width = o, this.height = s, this.skipControlsDrawing = !0, this.calcViewportBoundaries(), this.renderCanvas(g.getContext("2d"), _), this.viewportTransform = p, this.width = l, this.height = u, this.calcViewportBoundaries(), this.enableRetinaScaling = h, this.skipControlsDrawing = d, g;
	}
	dispose() {
		return !this.disposed && this.elements.cleanupDOM({
			width: this.width,
			height: this.height
		}), Xn.cancelByCanvas(this), this.disposed = !0, new Promise((e, t) => {
			let n = () => {
				this.destroy(), e(!0);
			};
			n.kill = t, this.__cleanupTask && this.__cleanupTask.kill("aborted"), this.destroyed ? e(!1) : this.nextRenderHandle ? this.__cleanupTask = n : n();
		});
	}
	destroy() {
		this.destroyed = !0, this.cancelRequestedRender(), this.forEachObject((e) => e.dispose()), this._objects = [], this.backgroundImage && this.backgroundImage.dispose(), this.backgroundImage = void 0, this.overlayImage && this.overlayImage.dispose(), this.overlayImage = void 0, this.elements.dispose();
	}
	toString() {
		return `#<Canvas (${this.complexity()}): { objects: ${this._objects.length} }>`;
	}
};
H(ni, "ownDefaults", Yr);
var ri = [
	"touchstart",
	"touchmove",
	"touchend"
], ii = (e) => {
	let t = Hr(e.target), n = function(e) {
		let t = e.changedTouches;
		return t && t[0] ? t[0] : e;
	}(e);
	return new q(n.clientX + t.left, n.clientY + t.top);
}, ai = (e) => ri.includes(e.type) || e.pointerType === "touch", oi = (e) => {
	e.preventDefault(), e.stopPropagation();
}, si = (e) => {
	let t = 0, n = 0, r = 0, i = 0;
	for (let a = 0, o = e.length; a < o; a++) {
		let { x: o, y: s } = e[a];
		(o > r || !a) && (r = o), (o < t || !a) && (t = o), (s > i || !a) && (i = s), (s < n || !a) && (n = s);
	}
	return {
		left: t,
		top: n,
		width: r - t,
		height: i - n
	};
}, ci = (e, t) => {
	ui(e, Y(vr(t), e.calcOwnMatrix()));
}, li = (e, t) => ui(e, Y(t, e.calcOwnMatrix())), ui = (e, t) => {
	let { translateX: n, translateY: r, scaleX: i, scaleY: a, ...o } = Cr(t), s = new q(n, r);
	e.flipX = !1, e.flipY = !1, Object.assign(e, o), e.set({
		scaleX: i,
		scaleY: a
	}), e.setPositionByOrigin(s, W, W);
}, di = (e) => {
	e.scaleX = 1, e.scaleY = 1, e.skewX = 0, e.skewY = 0, e.flipX = !1, e.flipY = !1, e.rotate(0);
}, fi = (e) => ({
	scaleX: e.scaleX,
	scaleY: e.scaleY,
	skewX: e.skewX,
	skewY: e.skewY,
	angle: e.angle,
	left: e.left,
	flipX: e.flipX,
	flipY: e.flipY,
	top: e.top
}), pi = (e, t, n) => {
	let r = e / 2, i = t / 2, a = si([
		new q(-r, -i),
		new q(r, -i),
		new q(-r, i),
		new q(r, i)
	].map((e) => e.transform(n)));
	return new q(a.width, a.height);
}, mi = (e = Dn, t = Dn) => Y(vr(t), e), hi = (e, t = Dn, n = Dn) => e.transform(mi(t, n)), gi = (e, t = Dn, n = Dn) => e.transform(mi(t, n), !0), _i = (e, t, n) => {
	let r = mi(t, n);
	return ui(e, Y(r, e.calcOwnMatrix())), r;
}, vi = {
	left: -.5,
	top: -.5,
	center: 0,
	bottom: .5,
	right: .5
}, yi = (e) => typeof e == "string" ? vi[e] : e - .5, bi = new q(1, 0), xi = new q(), Si = (e, t) => e.rotate(t), Ci = (e, t) => new q(t).subtract(e), wi = (e) => e.distanceFrom(xi), Ti = (e, t) => Math.atan2(ki(e, t), Ai(e, t)), Ei = (e) => Ti(bi, e), Di = (e) => e.eq(xi) ? e : e.scalarDivide(wi(e)), Oi = (e, t = !0) => Di(new q(-e.y, e.x).scalarMultiply(t ? 1 : -1)), ki = (e, t) => e.x * t.y - e.y * t.x, Ai = (e, t) => e.x * t.x + e.y * t.y, ji = (e, t, n) => {
	if (e.eq(t) || e.eq(n)) return !0;
	let r = ki(t, n), i = ki(t, e), a = ki(n, e);
	return r >= 0 ? i >= 0 && a <= 0 : !(i <= 0 && a >= 0);
}, Mi = "not-allowed";
function Ni(e) {
	return yi(e.originX) === yi("center") && yi(e.originY) === yi("center");
}
function Pi(e) {
	return .5 - yi(e);
}
var Fi = (e, t) => e[t], Ii = (e, t, n, r) => ({
	e,
	transform: t,
	pointer: new q(n, r)
});
function Li(e, t, n) {
	let r = n, i = Ei(Ci(hi(e.getCenterPoint(), e.canvas.viewportTransform, void 0), r)) + Tn;
	return Math.round(i % Tn / wn);
}
function Ri({ target: e, corner: t }, n, r, i, a) {
	let o = e.controls[t], s = e.canvas?.getZoom() || 1, c = e.padding / s, l = function(e, t, n, r) {
		let i = e.getRelativeCenterPoint(), a = n !== void 0 && r !== void 0 ? e.translateToGivenOrigin(i, W, W, n, r) : new q(e.left, e.top);
		return (e.angle ? t.rotate(-J(e.angle), i) : t).subtract(a);
	}(e, new q(i, a), n, r);
	return l.x >= c && (l.x -= c), l.x <= -c && (l.x += c), l.y >= c && (l.y -= c), l.y <= c && (l.y += c), l.x -= o.offsetX, l.y -= o.offsetY, l;
}
var zi = new RegExp(String.raw`[\0-\x1F\x7F;<>\\]|\/\*|\*\/|url\s*\(|expression\s*\(|(?:java|vb)script\s*:|data\s*:|@import\b`, "iu"), Bi = (e) => typeof e == "string" && e.trim().length > 0 && !zi.test(e), Vi = (e, t = "") => {
	let n = Number(e);
	return Number.isFinite(n) ? `${n}` : t;
}, Hi = (e, t = "") => typeof e == "string" && Bi(e) ? e : t, Ui = (e) => e.replace(/\s+/g, " "), Wi = {
	aliceblue: "#F0F8FF",
	antiquewhite: "#FAEBD7",
	aqua: "#0FF",
	aquamarine: "#7FFFD4",
	azure: "#F0FFFF",
	beige: "#F5F5DC",
	bisque: "#FFE4C4",
	black: "#000",
	blanchedalmond: "#FFEBCD",
	blue: "#00F",
	blueviolet: "#8A2BE2",
	brown: "#A52A2A",
	burlywood: "#DEB887",
	cadetblue: "#5F9EA0",
	chartreuse: "#7FFF00",
	chocolate: "#D2691E",
	coral: "#FF7F50",
	cornflowerblue: "#6495ED",
	cornsilk: "#FFF8DC",
	crimson: "#DC143C",
	cyan: "#0FF",
	darkblue: "#00008B",
	darkcyan: "#008B8B",
	darkgoldenrod: "#B8860B",
	darkgray: "#A9A9A9",
	darkgrey: "#A9A9A9",
	darkgreen: "#006400",
	darkkhaki: "#BDB76B",
	darkmagenta: "#8B008B",
	darkolivegreen: "#556B2F",
	darkorange: "#FF8C00",
	darkorchid: "#9932CC",
	darkred: "#8B0000",
	darksalmon: "#E9967A",
	darkseagreen: "#8FBC8F",
	darkslateblue: "#483D8B",
	darkslategray: "#2F4F4F",
	darkslategrey: "#2F4F4F",
	darkturquoise: "#00CED1",
	darkviolet: "#9400D3",
	deeppink: "#FF1493",
	deepskyblue: "#00BFFF",
	dimgray: "#696969",
	dimgrey: "#696969",
	dodgerblue: "#1E90FF",
	firebrick: "#B22222",
	floralwhite: "#FFFAF0",
	forestgreen: "#228B22",
	fuchsia: "#F0F",
	gainsboro: "#DCDCDC",
	ghostwhite: "#F8F8FF",
	gold: "#FFD700",
	goldenrod: "#DAA520",
	gray: "#808080",
	grey: "#808080",
	green: "#008000",
	greenyellow: "#ADFF2F",
	honeydew: "#F0FFF0",
	hotpink: "#FF69B4",
	indianred: "#CD5C5C",
	indigo: "#4B0082",
	ivory: "#FFFFF0",
	khaki: "#F0E68C",
	lavender: "#E6E6FA",
	lavenderblush: "#FFF0F5",
	lawngreen: "#7CFC00",
	lemonchiffon: "#FFFACD",
	lightblue: "#ADD8E6",
	lightcoral: "#F08080",
	lightcyan: "#E0FFFF",
	lightgoldenrodyellow: "#FAFAD2",
	lightgray: "#D3D3D3",
	lightgrey: "#D3D3D3",
	lightgreen: "#90EE90",
	lightpink: "#FFB6C1",
	lightsalmon: "#FFA07A",
	lightseagreen: "#20B2AA",
	lightskyblue: "#87CEFA",
	lightslategray: "#789",
	lightslategrey: "#789",
	lightsteelblue: "#B0C4DE",
	lightyellow: "#FFFFE0",
	lime: "#0F0",
	limegreen: "#32CD32",
	linen: "#FAF0E6",
	magenta: "#F0F",
	maroon: "#800000",
	mediumaquamarine: "#66CDAA",
	mediumblue: "#0000CD",
	mediumorchid: "#BA55D3",
	mediumpurple: "#9370DB",
	mediumseagreen: "#3CB371",
	mediumslateblue: "#7B68EE",
	mediumspringgreen: "#00FA9A",
	mediumturquoise: "#48D1CC",
	mediumvioletred: "#C71585",
	midnightblue: "#191970",
	mintcream: "#F5FFFA",
	mistyrose: "#FFE4E1",
	moccasin: "#FFE4B5",
	navajowhite: "#FFDEAD",
	navy: "#000080",
	oldlace: "#FDF5E6",
	olive: "#808000",
	olivedrab: "#6B8E23",
	orange: "#FFA500",
	orangered: "#FF4500",
	orchid: "#DA70D6",
	palegoldenrod: "#EEE8AA",
	palegreen: "#98FB98",
	paleturquoise: "#AFEEEE",
	palevioletred: "#DB7093",
	papayawhip: "#FFEFD5",
	peachpuff: "#FFDAB9",
	peru: "#CD853F",
	pink: "#FFC0CB",
	plum: "#DDA0DD",
	powderblue: "#B0E0E6",
	purple: "#800080",
	rebeccapurple: "#639",
	red: "#F00",
	rosybrown: "#BC8F8F",
	royalblue: "#4169E1",
	saddlebrown: "#8B4513",
	salmon: "#FA8072",
	sandybrown: "#F4A460",
	seagreen: "#2E8B57",
	seashell: "#FFF5EE",
	sienna: "#A0522D",
	silver: "#C0C0C0",
	skyblue: "#87CEEB",
	slateblue: "#6A5ACD",
	slategray: "#708090",
	slategrey: "#708090",
	snow: "#FFFAFA",
	springgreen: "#00FF7F",
	steelblue: "#4682B4",
	tan: "#D2B48C",
	teal: "#008080",
	thistle: "#D8BFD8",
	tomato: "#FF6347",
	turquoise: "#40E0D0",
	violet: "#EE82EE",
	wheat: "#F5DEB3",
	white: "#FFF",
	whitesmoke: "#F5F5F5",
	yellow: "#FF0",
	yellowgreen: "#9ACD32"
}, Gi = (e, t, n) => (n < 0 && (n += 1), n > 1 && --n, n < 1 / 6 ? e + 6 * (t - e) * n : n < .5 ? t : n < 2 / 3 ? e + (t - e) * (2 / 3 - n) * 6 : e), Ki = (e, t, n, r) => {
	e /= 255, t /= 255, n /= 255;
	let i = Math.max(e, t, n), a = Math.min(e, t, n), o, s, c = (i + a) / 2;
	if (i === a) o = s = 0;
	else {
		let r = i - a;
		switch (s = c > .5 ? r / (2 - i - a) : r / (i + a), i) {
			case e:
				o = (t - n) / r + (t < n ? 6 : 0);
				break;
			case t:
				o = (n - e) / r + 2;
				break;
			case n: o = (e - t) / r + 4;
		}
		o /= 6;
	}
	return [
		Math.round(360 * o),
		Math.round(100 * s),
		Math.round(100 * c),
		r
	];
}, qi = (e = "1") => parseFloat(e) / (e.endsWith("%") ? 100 : 1), Ji = (e) => Math.min(Math.round(e), 255).toString(16).toUpperCase().padStart(2, "0"), Yi = ([e, t, n, r = 1]) => {
	let i = Math.round(.3 * e + .59 * t + .11 * n);
	return [
		i,
		i,
		i,
		r
	];
}, Xi = class e {
	constructor(t) {
		if (H(this, "isUnrecognised", !1), t) if (t instanceof e) this.setSource([...t._source]);
		else if (Array.isArray(t)) {
			let [e, n, r, i = 1] = t;
			this.setSource([
				e,
				n,
				r,
				i
			]);
		} else this.setSource(this._tryParsingColor(t));
		else this.setSource([
			0,
			0,
			0,
			1
		]);
	}
	_tryParsingColor(t) {
		return (t = t.toLowerCase()) in Wi && (t = Wi[t]), t === "transparent" ? [
			255,
			255,
			255,
			0
		] : e.sourceFromHex(t) || e.sourceFromRgb(t) || e.sourceFromHsl(t) || (this.isUnrecognised = !0) && [
			0,
			0,
			0,
			1
		];
	}
	getSource() {
		return this._source;
	}
	setSource(e) {
		this._source = e;
	}
	toRgb() {
		let [e, t, n] = this.getSource();
		return `rgb(${e},${t},${n})`;
	}
	toRgba() {
		return `rgba(${this.getSource().join(",")})`;
	}
	toHsl() {
		let [e, t, n] = Ki(...this.getSource());
		return `hsl(${e},${t}%,${n}%)`;
	}
	toHsla() {
		let [e, t, n, r] = Ki(...this.getSource());
		return `hsla(${e},${t}%,${n}%,${r})`;
	}
	toHex() {
		return this.toHexa().slice(0, 6);
	}
	toHexa() {
		let [e, t, n, r] = this.getSource();
		return `${Ji(e)}${Ji(t)}${Ji(n)}${Ji(Math.round(255 * r))}`;
	}
	getAlpha() {
		return this.getSource()[3];
	}
	setAlpha(e) {
		return this._source[3] = e, this;
	}
	toGrayscale() {
		return this.setSource(Yi(this.getSource())), this;
	}
	toBlackWhite(e) {
		let [t, , , n] = Yi(this.getSource()), r = t < (e || 127) ? 0 : 255;
		return this.setSource([
			r,
			r,
			r,
			n
		]), this;
	}
	overlayWith(t) {
		t instanceof e || (t = new e(t));
		let n = this.getSource(), r = t.getSource(), [i, a, o] = n.map((e, t) => Math.round(.5 * e + .5 * r[t]));
		return this.setSource([
			i,
			a,
			o,
			n[3]
		]), this;
	}
	static fromRgb(t) {
		return e.fromRgba(t);
	}
	static fromRgba(t) {
		return new e(e.sourceFromRgb(t));
	}
	static sourceFromRgb(e) {
		let t = Ui(e).match(/^rgba?\(\s?(\d{0,3}(?:\.\d+)?%?)\s?[\s|,]\s?(\d{0,3}(?:\.\d+)?%?)\s?[\s|,]\s?(\d{0,3}(?:\.\d+)?%?)\s?(?:\s?[,/]\s?(\d{0,3}(?:\.\d+)?%?)\s?)?\)$/i);
		if (t) {
			let [e, n, r] = t.slice(1, 4).map((e) => {
				let t = parseFloat(e);
				return e.endsWith("%") ? Math.round(2.55 * t) : t;
			});
			return [
				e,
				n,
				r,
				qi(t[4])
			];
		}
	}
	static fromHsl(t) {
		return e.fromHsla(t);
	}
	static fromHsla(t) {
		return new e(e.sourceFromHsl(t));
	}
	static sourceFromHsl(t) {
		let n = Ui(t).match(/^hsla?\(\s?([+-]?\d{0,3}(?:\.\d+)?(?:deg|turn|rad)?)\s?[\s|,]\s?(\d{0,3}(?:\.\d+)?%?)\s?[\s|,]\s?(\d{0,3}(?:\.\d+)?%?)\s?(?:\s?[,/]\s?(\d*(?:\.\d+)?%?)\s?)?\)$/i);
		if (!n) return;
		let r = (e.parseAngletoDegrees(n[1]) % 360 + 360) % 360 / 360, i = parseFloat(n[2]) / 100, a = parseFloat(n[3]) / 100, o, s, c;
		if (i === 0) o = s = c = a;
		else {
			let e = a <= .5 ? a * (i + 1) : a + i - a * i, t = 2 * a - e;
			o = Gi(t, e, r + 1 / 3), s = Gi(t, e, r), c = Gi(t, e, r - 1 / 3);
		}
		return [
			Math.round(255 * o),
			Math.round(255 * s),
			Math.round(255 * c),
			qi(n[4])
		];
	}
	static fromHex(t) {
		return new e(e.sourceFromHex(t));
	}
	static sourceFromHex(e) {
		if (e.match(/^#?(([0-9a-f]){3,4}|([0-9a-f]{2}){3,4})$/i)) {
			let t = e.slice(e.indexOf("#") + 1), n;
			n = t.length <= 4 ? t.split("").map((e) => e + e) : t.match(/.{2}/g);
			let [r, i, a, o = 255] = n.map((e) => parseInt(e, 16));
			return [
				r,
				i,
				a,
				o / 255
			];
		}
	}
	static parseAngletoDegrees(e) {
		let t = e.toLowerCase(), n = parseFloat(t);
		return t.includes("rad") ? hr(n) : t.includes("turn") ? 360 * n : n;
	}
}, Zi = (e) => {
	let t = [
		"instantiated_by_use",
		"style",
		"id",
		"class"
	];
	switch (e) {
		case "linearGradient": return t.concat([
			"x1",
			"y1",
			"x2",
			"y2",
			"gradientUnits",
			"gradientTransform"
		]);
		case "radialGradient": return t.concat([
			"gradientUnits",
			"gradientTransform",
			"cx",
			"cy",
			"r",
			"fx",
			"fy",
			"fr"
		]);
		case "stop": return t.concat([
			"offset",
			"stop-color",
			"stop-opacity"
		]);
	}
	return t;
}, Qi = (e, t = 16) => {
	let n = /\D{0,2}$/.exec(e), r = parseFloat(e), i = U.DPI;
	switch (n?.[0]) {
		case "mm": return r * i / 25.4;
		case "cm": return r * i / 2.54;
		case "in": return r * i;
		case "pt": return r * i / 72;
		case "pc": return r * i / 72 * 12;
		case "em": return r * t;
		default: return r;
	}
}, $i = (e) => {
	let [t, n] = e.trim().split(" "), [r, i] = (a = t) && a !== "none" ? [a.slice(1, 4), a.slice(5, 8)] : a === "none" ? [a, a] : ["Mid", "Mid"];
	var a;
	return {
		meetOrSlice: n || "meet",
		alignX: r,
		alignY: i
	};
}, ea = (e, t, n = !0) => {
	let r, i;
	if (t) if (t.toLive) r = `url(#SVGID_${Z(t.id)})`;
	else {
		let e = String(t);
		if (Bi(e)) {
			let t = new Xi(e), n = t.getAlpha();
			r = t.toRgb(), n !== 1 && (i = n.toString());
		} else r = new Xi("black").toRgb();
	}
	else r = "none";
	return n ? `${e}: ${r}; ${i ? `${e}-opacity: ${i}; ` : ""}` : `${e}="${r}" ${i ? `${e}-opacity="${i}" ` : ""}`;
}, ta = class {
	getSvgStyles(e) {
		let t = this.fillRule == null ? "nonzero" : Hi(this.fillRule), n = this.strokeWidth == null ? "0" : Vi(this.strokeWidth), r = this.strokeDashArray == null ? An : this.strokeDashArray.every((e) => Number.isFinite(Number(e))) ? this.strokeDashArray.join(" ") : "", i = this.strokeDashOffset == null ? "0" : Vi(this.strokeDashOffset), a = this.strokeLineCap == null ? "butt" : Hi(this.strokeLineCap), o = this.strokeLineJoin == null ? "miter" : Hi(this.strokeLineJoin), s = this.strokeMiterLimit == null ? "4" : Vi(this.strokeMiterLimit), c = this.opacity == null ? "1" : Vi(this.opacity), l = this.visible ? "" : " visibility: hidden;", u = e ? "" : this.getSvgFilter(), d = ea(Gn, this.fill);
		return [
			ea(Kn, this.stroke),
			n ? `stroke-width: ${n}; ` : "",
			r ? `stroke-dasharray: ${r}; ` : "",
			a ? `stroke-linecap: ${a}; ` : "",
			i ? `stroke-dashoffset: ${i}; ` : "",
			o ? `stroke-linejoin: ${o}; ` : "",
			s ? `stroke-miterlimit: ${s}; ` : "",
			d,
			t ? `fill-rule: ${t}; ` : "",
			c ? `opacity: ${c};` : "",
			u,
			l
		].map((e) => Z(e)).join("");
	}
	getSvgFilter() {
		return this.shadow ? `filter: url(#SVGID_${Z(this.shadow.id)});` : "";
	}
	getSvgCommons() {
		return [this.id ? `id="${Z(String(this.id))}" ` : "", this.clipPath ? `clip-path="url(#${Z(this.clipPath.clipPathId)})" ` : ""].join("");
	}
	getSvgTransform(e, t = "") {
		return `transform="${Lr(e ? this.calcTransformMatrix() : this.calcOwnMatrix())}${t}" `;
	}
	_toSVG(e) {
		return [""];
	}
	toSVG(e) {
		return this._createBaseSVGMarkup(this._toSVG(e), { reviver: e });
	}
	toClipPathSVG(e) {
		return "	" + this._createBaseClipPathSVGMarkup(this._toSVG(e), { reviver: e });
	}
	_createBaseClipPathSVGMarkup(e, { reviver: t, additionalTransform: n = "" } = {}) {
		let r = [this.getSvgTransform(!0, n), this.getSvgCommons()].join(""), i = e.indexOf("COMMON_PARTS");
		return e[i] = r, t ? t(e.join("")) : e.join("");
	}
	_createBaseSVGMarkup(e, { noStyle: t, reviver: n, withShadow: r, additionalTransform: i } = {}) {
		let a = t ? "" : `style="${this.getSvgStyles()}" `, o = r ? `style="${this.getSvgFilter()}" ` : "", s = this.clipPath, c = this.strokeUniform ? "vector-effect=\"non-scaling-stroke\" " : "", l = s && s.absolutePositioned, u = this.stroke, d = this.fill, f = this.shadow, p = [], m = e.indexOf("COMMON_PARTS"), h;
		return s && (s.clipPathId = `CLIPPATH_${cr()}`, h = `<clipPath id="${s.clipPathId}" >\n${s.toClipPathSVG(n)}</clipPath>\n`), l && p.push("<g ", o, this.getSvgCommons(), " >\n"), p.push("<g ", this.getSvgTransform(!1), l ? "" : o + this.getSvgCommons(), " >\n"), e[m] = [
			a,
			c,
			t ? "" : this.addPaintOrder(),
			" ",
			i ? `transform="${i}" ` : ""
		].join(""), Rr(d) && p.push(d.toSVG(this)), Rr(u) && p.push(u.toSVG(this)), f && p.push(f.toSVG(this)), s && p.push(h), p.push(e.join("")), p.push("</g>\n"), l && p.push("</g>\n"), n ? n(p.join("")) : p.join("");
	}
	addPaintOrder() {
		return this.paintFirst === "fill" ? "" : ` paint-order="${Z(this.paintFirst)}" `;
	}
};
function na(e) {
	return RegExp("^(" + e.join("|") + ")\\b", "i");
}
var ra = "textDecorationThickness", ia = "textDecorationColor", aa = [
	"fontSize",
	"fontWeight",
	"fontFamily",
	"fontStyle"
], oa = [
	"underline",
	"overline",
	"linethrough"
], sa = [
	...aa,
	"lineHeight",
	"text",
	"charSpacing",
	"textAlign",
	"styles",
	"path",
	"pathStartOffset",
	"pathSide",
	"pathAlign"
], ca = [
	...sa,
	...oa,
	"textBackgroundColor",
	"direction",
	ra,
	ia
], la = [
	...aa,
	...oa,
	Kn,
	"strokeWidth",
	Gn,
	"deltaY",
	"textBackgroundColor",
	ra,
	ia
], ua = {
	_reNewline: jn,
	_reSpacesAndTabs: /[ \t\r]/g,
	_reSpaceAndTab: /[ \t\r]/,
	_reWords: /\S+/g,
	fontSize: 40,
	fontWeight: Jn,
	fontFamily: "Times New Roman",
	underline: !1,
	overline: !1,
	linethrough: !1,
	textAlign: G,
	fontStyle: Jn,
	lineHeight: 1.16,
	textBackgroundColor: "",
	stroke: null,
	shadow: null,
	path: void 0,
	pathStartOffset: 0,
	pathSide: G,
	pathAlign: "baseline",
	charSpacing: 0,
	deltaY: 0,
	direction: "ltr",
	CACHE_FONT_SIZE: 400,
	MIN_TEXT_WIDTH: 2,
	superscript: {
		size: .6,
		baseline: -.35
	},
	subscript: {
		size: .6,
		baseline: .11
	},
	_fontSizeFraction: .222,
	offsets: {
		underline: .1,
		linethrough: -.28167,
		overline: -.81333
	},
	_fontSizeMult: 1.13,
	[ra]: 66.667
}, da = "justify", fa = String.raw`[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?`, pa = String.raw`(?:\s*,?\s+|\s*,\s*)`, ma = RegExp("(normal|italic)?\\s*(normal|small-caps)?\\s*(normal|bold|bolder|lighter|100|200|300|400|500|600|700|800|900)?\\s*(" + fa + "(?:px|cm|mm|em|pt|pc|in)*)(?:\\/(normal|" + fa + "))?\\s+(.*)"), ha = {
	cx: G,
	x: G,
	r: "radius",
	cy: "top",
	y: "top",
	display: "visible",
	visibility: "visible",
	transform: "transformMatrix",
	"fill-opacity": "fillOpacity",
	"fill-rule": "fillRule",
	"font-family": "fontFamily",
	"font-size": "fontSize",
	"font-style": "fontStyle",
	"font-weight": "fontWeight",
	"letter-spacing": "charSpacing",
	"paint-order": "paintFirst",
	"stroke-dasharray": "strokeDashArray",
	"stroke-dashoffset": "strokeDashOffset",
	"stroke-linecap": "strokeLineCap",
	"stroke-linejoin": "strokeLineJoin",
	"stroke-miterlimit": "strokeMiterLimit",
	"stroke-opacity": "strokeOpacity",
	"stroke-width": "strokeWidth",
	"text-decoration": "textDecoration",
	"text-anchor": "textAnchor",
	opacity: "opacity",
	"clip-path": "clipPath",
	"clip-rule": "clipRule",
	"vector-effect": "strokeUniform",
	"image-rendering": "imageSmoothing",
	"text-decoration-thickness": ra,
	"text-decoration-color": ia
}, ga = "font-size", _a = "clip-path";
na([
	"path",
	"circle",
	"polygon",
	"polyline",
	"ellipse",
	"rect",
	"line",
	"image",
	"text"
]), na([
	"symbol",
	"image",
	"marker",
	"pattern",
	"view",
	"svg"
]);
var va = na([
	"symbol",
	"g",
	"a",
	"svg",
	"clipPath",
	"defs"
]);
new RegExp(String.raw`^\s*(${fa})${pa}(${fa})${pa}(${fa})${pa}(${fa})\s*$`);
var ya = "(-?\\d+(?:\\.\\d*)?(?:px)?(?:\\s?|$))?", ba = RegExp("(?:\\s|^)" + ya + ya + "(" + fa + "?(?:px)?)?(?:\\s?|$)(?:$|\\s)"), xa = class e {
	constructor(t = {}) {
		let n = typeof t == "string" ? e.parseShadow(t) : t;
		Object.assign(this, e.ownDefaults, n), this.id = cr();
	}
	static parseShadow(e) {
		let t = e.trim(), [, n = 0, r = 0, i = 0] = (ba.exec(t) || []).map((e) => parseFloat(e) || 0);
		return {
			color: (t.replace(ba, "") || "rgb(0,0,0)").trim(),
			offsetX: n,
			offsetY: r,
			blur: i
		};
	}
	toString() {
		return [
			this.offsetX,
			this.offsetY,
			this.blur,
			this.color
		].join("px ");
	}
	toSVG(e) {
		let t = Si(new q(this.offsetX, this.offsetY), J(-e.angle)), n = U.NUM_FRACTION_DIGITS, r = new Xi(this.color), i = 40, a = 40;
		return e.width && e.height && (i = 100 * X((Math.abs(t.x) + this.blur) / e.width, n) + 20, a = 100 * X((Math.abs(t.y) + this.blur) / e.height, n) + 20), e.flipX && (t.x *= -1), e.flipY && (t.y *= -1), `<filter id="SVGID_${Z(this.id)}" y="-${a}%" height="${100 + 2 * a}%" x="-${i}%" width="${100 + 2 * i}%" >\n\t<feGaussianBlur in="SourceAlpha" stdDeviation="${X(this.blur ? this.blur / 2 : 0, n)}"></feGaussianBlur>\n\t<feOffset dx="${X(t.x, n)}" dy="${X(t.y, n)}" result="oBlur" ></feOffset>\n\t<feFlood flood-color="${r.toRgb()}" flood-opacity="${r.getAlpha()}"/>\n\t<feComposite in2="oBlur" operator="in" />\n\t<feMerge>\n\t\t<feMergeNode></feMergeNode>\n\t\t<feMergeNode in="SourceGraphic"></feMergeNode>\n\t</feMerge>\n</filter>\n`;
	}
	toObject() {
		let t = {
			color: this.color,
			blur: this.blur,
			offsetX: this.offsetX,
			offsetY: this.offsetY,
			affectStroke: this.affectStroke,
			nonScaling: this.nonScaling,
			type: this.constructor.type
		}, n = e.ownDefaults;
		return this.includeDefaultValues ? t : Ir(t, (e, t) => e !== n[t]);
	}
	static async fromObject(e) {
		return new this(e);
	}
};
H(xa, "ownDefaults", {
	color: "rgb(0,0,0)",
	blur: 0,
	offsetX: 0,
	offsetY: 0,
	affectStroke: !1,
	includeDefaultValues: !0,
	nonScaling: !1
}), H(xa, "type", "shadow"), K.setClass(xa, "shadow");
var Sa = (e, t, n) => Math.max(e, Math.min(t, n)), Ca = [
	"top",
	G,
	Vn,
	Hn,
	"flipX",
	"flipY",
	"originX",
	"originY",
	"angle",
	"opacity",
	"globalCompositeOperation",
	"shadow",
	"visible",
	Un,
	Wn
], wa = [
	Gn,
	Kn,
	"strokeWidth",
	"strokeDashArray",
	"width",
	"height",
	"paintFirst",
	"strokeUniform",
	"strokeLineCap",
	"strokeDashOffset",
	"strokeLineJoin",
	"strokeMiterLimit",
	"backgroundColor",
	"clipPath"
], Ta = {
	top: 0,
	left: 0,
	width: 0,
	height: 0,
	angle: 0,
	flipX: !1,
	flipY: !1,
	scaleX: 1,
	scaleY: 1,
	minScaleLimit: 0,
	skewX: 0,
	skewY: 0,
	originX: W,
	originY: W,
	strokeWidth: 1,
	strokeUniform: !1,
	padding: 0,
	opacity: 1,
	paintFirst: Gn,
	fill: "rgb(0,0,0)",
	fillRule: "nonzero",
	stroke: null,
	strokeDashArray: null,
	strokeDashOffset: 0,
	strokeLineCap: "butt",
	strokeLineJoin: "miter",
	strokeMiterLimit: 4,
	globalCompositeOperation: "source-over",
	backgroundColor: "",
	shadow: null,
	visible: !0,
	includeDefaultValues: !0,
	excludeFromExport: !1,
	objectCaching: !0,
	clipPath: void 0,
	inverted: !1,
	absolutePositioned: !1,
	centeredRotation: !0,
	centeredScaling: !1,
	dirty: !0
}, Ea = an({
	defaultEasing: () => ka,
	easeInBack: () => Za,
	easeInBounce: () => to,
	easeInCirc: () => Ga,
	easeInCubic: () => Aa,
	easeInElastic: () => Ja,
	easeInExpo: () => Ha,
	easeInOutBack: () => $a,
	easeInOutBounce: () => no,
	easeInOutCirc: () => qa,
	easeInOutCubic: () => Ma,
	easeInOutElastic: () => Xa,
	easeInOutExpo: () => Wa,
	easeInOutQuad: () => ao,
	easeInOutQuart: () => Fa,
	easeInOutQuint: () => Ra,
	easeInOutSine: () => Va,
	easeInQuad: () => ro,
	easeInQuart: () => Na,
	easeInQuint: () => Ia,
	easeInSine: () => za,
	easeOutBack: () => Qa,
	easeOutBounce: () => eo,
	easeOutCirc: () => Ka,
	easeOutCubic: () => ja,
	easeOutElastic: () => Ya,
	easeOutExpo: () => Ua,
	easeOutQuad: () => io,
	easeOutQuart: () => Pa,
	easeOutQuint: () => La,
	easeOutSine: () => Ba
}), Da = (e, t, n, r) => (e < Math.abs(t) ? (e = t, r = n / 4) : r = t === 0 && e === 0 ? n / Tn * Math.asin(1) : n / Tn * Math.asin(t / e), {
	a: e,
	c: t,
	p: n,
	s: r
}), Oa = (e, t, n, r, i) => e * 2 ** (10 * --r) * Math.sin((r * i - t) * Tn / n), ka = (e, t, n, r) => -n * Math.cos(e / r * Cn) + n + t, Aa = (e, t, n, r) => n * (e / r) ** 3 + t, ja = (e, t, n, r) => n * ((e / r - 1) ** 3 + 1) + t, Ma = (e, t, n, r) => (e /= r / 2) < 1 ? n / 2 * e ** 3 + t : n / 2 * ((e - 2) ** 3 + 2) + t, Na = (e, t, n, r) => n * (e /= r) * e ** 3 + t, Pa = (e, t, n, r) => -n * ((e = e / r - 1) * e ** 3 - 1) + t, Fa = (e, t, n, r) => (e /= r / 2) < 1 ? n / 2 * e ** 4 + t : -n / 2 * ((e -= 2) * e ** 3 - 2) + t, Ia = (e, t, n, r) => n * (e / r) ** 5 + t, La = (e, t, n, r) => n * ((e / r - 1) ** 5 + 1) + t, Ra = (e, t, n, r) => (e /= r / 2) < 1 ? n / 2 * e ** 5 + t : n / 2 * ((e - 2) ** 5 + 2) + t, za = (e, t, n, r) => -n * Math.cos(e / r * Cn) + n + t, Ba = (e, t, n, r) => n * Math.sin(e / r * Cn) + t, Va = (e, t, n, r) => -n / 2 * (Math.cos(Math.PI * e / r) - 1) + t, Ha = (e, t, n, r) => e === 0 ? t : n * 2 ** (10 * (e / r - 1)) + t, Ua = (e, t, n, r) => e === r ? t + n : n * -(2 ** (-10 * e / r) + 1) + t, Wa = (e, t, n, r) => e === 0 ? t : e === r ? t + n : (e /= r / 2) < 1 ? n / 2 * 2 ** (10 * (e - 1)) + t : n / 2 * -(2 ** (-10 * (e - 1)) + 2) + t, Ga = (e, t, n, r) => -n * (Math.sqrt(1 - (e /= r) * e) - 1) + t, Ka = (e, t, n, r) => n * Math.sqrt(1 - (e = e / r - 1) * e) + t, qa = (e, t, n, r) => (e /= r / 2) < 1 ? -n / 2 * (Math.sqrt(1 - e ** 2) - 1) + t : n / 2 * (Math.sqrt(1 - (e -= 2) * e) + 1) + t, Ja = (e, t, n, r) => {
	let i = n, a = 0;
	if (e === 0) return t;
	if ((e /= r) === 1) return t + n;
	a ||= .3 * r;
	let { a: o, s, p: c } = Da(i, n, a, 1.70158);
	return -Oa(o, s, c, e, r) + t;
}, Ya = (e, t, n, r) => {
	let i = n, a = 0;
	if (e === 0) return t;
	if ((e /= r) === 1) return t + n;
	a ||= .3 * r;
	let { a: o, s, p: c, c: l } = Da(i, n, a, 1.70158);
	return o * 2 ** (-10 * e) * Math.sin((e * r - s) * Tn / c) + l + t;
}, Xa = (e, t, n, r) => {
	let i = n, a = 0;
	if (e === 0) return t;
	if ((e /= r / 2) == 2) return t + n;
	a ||= .3 * 1.5 * r;
	let { a: o, s, p: c, c: l } = Da(i, n, a, 1.70158);
	return e < 1 ? -.5 * Oa(o, s, c, e, r) + t : o * 2 ** (-10 * --e) * Math.sin((e * r - s) * Tn / c) * .5 + l + t;
}, Za = (e, t, n, r, i = 1.70158) => n * (e /= r) * e * ((i + 1) * e - i) + t, Qa = (e, t, n, r, i = 1.70158) => n * ((e = e / r - 1) * e * ((i + 1) * e + i) + 1) + t, $a = (e, t, n, r, i = 1.70158) => (e /= r / 2) < 1 ? n / 2 * (e * e * ((1 + (i *= 1.525)) * e - i)) + t : n / 2 * ((e -= 2) * e * ((1 + (i *= 1.525)) * e + i) + 2) + t, eo = (e, t, n, r) => (e /= r) < 1 / 2.75 ? n * (7.5625 * e * e) + t : e < 2 / 2.75 ? n * (7.5625 * (e -= 1.5 / 2.75) * e + .75) + t : e < 2.5 / 2.75 ? n * (7.5625 * (e -= 2.25 / 2.75) * e + .9375) + t : n * (7.5625 * (e -= 2.625 / 2.75) * e + .984375) + t, to = (e, t, n, r) => n - eo(r - e, 0, n, r) + t, no = (e, t, n, r) => e < r / 2 ? .5 * to(2 * e, 0, n, r) + t : .5 * eo(2 * e - r, 0, n, r) + .5 * n + t, ro = (e, t, n, r) => n * (e /= r) * e + t, io = (e, t, n, r) => -n * (e /= r) * (e - 2) + t, ao = (e, t, n, r) => (e /= r / 2) < 1 ? n / 2 * e ** 2 + t : -n / 2 * (--e * (e - 2) - 1) + t, oo = () => !1, so = class {
	constructor({ startValue: e, byValue: t, duration: n = 500, delay: r = 0, easing: i = ka, onStart: a = Sn, onChange: o = Sn, onComplete: s = Sn, abort: c = oo, target: l }) {
		H(this, "_state", "pending"), H(this, "durationProgress", 0), H(this, "valueProgress", 0), this.tick = this.tick.bind(this), this.duration = n, this.delay = r, this.easing = i, this._onStart = a, this._onChange = o, this._onComplete = s, this._abort = c, this.target = l, this.startValue = e, this.byValue = t, this.value = this.startValue, this.endValue = Object.freeze(this.calculate(this.duration).value);
	}
	get state() {
		return this._state;
	}
	isDone() {
		return this._state === "aborted" || this._state === "completed";
	}
	start() {
		let e = (e) => {
			this._state === "pending" && (this.startTime = e || +/* @__PURE__ */ new Date(), this._state = "running", this._onStart(), this.tick(this.startTime));
		};
		this.register(), this.delay > 0 ? this.timeout = vn().setTimeout(() => ar(e), this.delay) : ar(e);
	}
	tick(e) {
		let t = (e || +/* @__PURE__ */ new Date()) - this.startTime, n = Math.min(t, this.duration);
		this.durationProgress = n / this.duration;
		let { value: r, valueProgress: i } = this.calculate(n);
		this.value = Object.freeze(r), this.valueProgress = i, this._state !== "aborted" && (this._abort(this.value, this.valueProgress, this.durationProgress) ? (this._state = "aborted", this.unregister()) : t >= this.duration ? (this.durationProgress = this.valueProgress = 1, this._onChange(this.endValue, this.valueProgress, this.durationProgress), this._state = "completed", this._onComplete(this.endValue, this.valueProgress, this.durationProgress), this.unregister(), this.timeout = null) : (this._onChange(this.value, this.valueProgress, this.durationProgress), ar(this.tick)));
	}
	register() {
		Xn.push(this);
	}
	unregister() {
		Xn.remove(this);
	}
	abort() {
		this._state = "aborted", this.unregister(), this.timeout && vn().clearTimeout(this.timeout);
	}
}, co = class extends so {
	constructor({ startValue: e = 0, endValue: t = 100, ...n }) {
		super({
			...n,
			startValue: e,
			byValue: t - e
		});
	}
	calculate(e) {
		let t = this.easing(e, this.startValue, this.byValue, this.duration);
		return {
			value: t,
			valueProgress: Math.abs((t - this.startValue) / this.byValue)
		};
	}
}, lo = class extends so {
	constructor({ startValue: e = [0], endValue: t = [100], ...n }) {
		super({
			...n,
			startValue: e,
			byValue: t.map((t, n) => t - e[n])
		});
	}
	calculate(e) {
		let t = this.startValue.map((t, n) => this.easing(e, t, this.byValue[n], this.duration, n));
		return {
			value: t,
			valueProgress: Math.abs((t[0] - this.startValue[0]) / this.byValue[0])
		};
	}
}, uo = (e, t, n, r) => t + n * (1 - Math.cos(e / r * Cn)), fo = (e) => e && ((t, n, r) => e(new Xi(t).toRgba(), n, r)), po = class extends so {
	constructor({ startValue: e, endValue: t, easing: n = uo, onChange: r, onComplete: i, abort: a, ...o }) {
		let s = new Xi(e).getSource(), c = new Xi(t).getSource();
		super({
			...o,
			startValue: s,
			byValue: c.map((e, t) => e - s[t]),
			easing: n,
			onChange: fo(r),
			onComplete: fo(i),
			abort: fo(a)
		});
	}
	calculate(e) {
		let [t, n, r, i] = this.startValue.map((t, n) => this.easing(e, t, this.byValue[n], this.duration, n)), a = [...[
			t,
			n,
			r
		].map(Math.round), Sa(0, i, 1)];
		return {
			value: a,
			valueProgress: a.map((e, t) => this.byValue[t] === 0 ? 0 : Math.abs((e - this.startValue[t]) / this.byValue[t])).find((e) => e !== 0) || 0
		};
	}
};
function mo(e) {
	let t = ((e) => Array.isArray(e.startValue) || Array.isArray(e.endValue))(e) ? new lo(e) : new co(e);
	return t.start(), t;
}
function ho(e) {
	let t = new po(e);
	return t.start(), t;
}
var go = class e {
	constructor(e) {
		this.status = e, this.points = [];
	}
	includes(e) {
		return this.points.some((t) => t.eq(e));
	}
	append(...e) {
		return this.points = this.points.concat(e.filter((e) => !this.includes(e))), this;
	}
	static isPointContained(e, t, n, r = !1) {
		if (t.eq(n)) return e.eq(t);
		if (t.x === n.x) return e.x === t.x && (r || e.y >= Math.min(t.y, n.y) && e.y <= Math.max(t.y, n.y));
		if (t.y === n.y) return e.y === t.y && (r || e.x >= Math.min(t.x, n.x) && e.x <= Math.max(t.x, n.x));
		{
			let i = Ci(t, n), a = Ci(t, e).divide(i);
			return r ? Math.abs(a.x) === Math.abs(a.y) : a.x === a.y && a.x >= 0 && a.x <= 1;
		}
	}
	static isPointInPolygon(e, t) {
		let n = new q(e).setX(Math.min(e.x - 1, ...t.map((e) => e.x))), r = 0;
		for (let i = 0; i < t.length; i++) {
			let a = this.intersectSegmentSegment(t[i], t[(i + 1) % t.length], e, n);
			if (a.includes(e)) return !0;
			r += Number(a.status === "Intersection");
		}
		return r % 2 == 1;
	}
	static intersectLineLine(t, n, r, i, a = !0, o = !0) {
		let s = n.x - t.x, c = n.y - t.y, l = i.x - r.x, u = i.y - r.y, d = t.x - r.x, f = t.y - r.y, p = l * f - u * d, m = s * f - c * d, h = u * s - l * c;
		if (h !== 0) {
			let n = p / h, r = m / h;
			return (a || 0 <= n && n <= 1) && (o || 0 <= r && r <= 1) ? new e("Intersection").append(new q(t.x + n * s, t.y + n * c)) : new e();
		}
		return new e(p === 0 || m === 0 ? a || o || e.isPointContained(t, r, i) || e.isPointContained(n, r, i) || e.isPointContained(r, t, n) || e.isPointContained(i, t, n) ? "Coincident" : void 0 : "Parallel");
	}
	static intersectSegmentLine(t, n, r, i) {
		return e.intersectLineLine(t, n, r, i, !1, !0);
	}
	static intersectSegmentSegment(t, n, r, i) {
		return e.intersectLineLine(t, n, r, i, !1, !1);
	}
	static intersectLinePolygon(t, n, r, i = !0) {
		let a = new e(), o = r.length;
		for (let s, c, l, u = 0; u < o; u++) {
			if (s = r[u], c = r[(u + 1) % o], l = e.intersectLineLine(t, n, s, c, i, !1), l.status === "Coincident") return l;
			a.append(...l.points);
		}
		return a.points.length > 0 && (a.status = "Intersection"), a;
	}
	static intersectSegmentPolygon(t, n, r) {
		return e.intersectLinePolygon(t, n, r, !1);
	}
	static intersectPolygonPolygon(t, n) {
		let r = new e(), i = t.length, a = [];
		for (let o = 0; o < i; o++) {
			let s = t[o], c = t[(o + 1) % i], l = e.intersectSegmentPolygon(s, c, n);
			l.status === "Coincident" ? (a.push(l), r.append(s, c)) : r.append(...l.points);
		}
		return a.length > 0 && a.length === t.length ? new e("Coincident") : (r.points.length > 0 && (r.status = "Intersection"), r);
	}
	static intersectPolygonRectangle(t, n, r) {
		let i = n.min(r), a = n.max(r), o = new q(a.x, i.y), s = new q(i.x, a.y);
		return e.intersectPolygonPolygon(t, [
			i,
			o,
			a,
			s
		]);
	}
}, _o = class extends ir {
	getX() {
		return this.getXY().x;
	}
	setX(e) {
		this.setXY(this.getXY().setX(e));
	}
	getY() {
		return this.getXY().y;
	}
	setY(e) {
		this.setXY(this.getXY().setY(e));
	}
	getRelativeX() {
		return this.left;
	}
	setRelativeX(e) {
		this.left = e;
	}
	getRelativeY() {
		return this.top;
	}
	setRelativeY(e) {
		this.top = e;
	}
	getXY() {
		let e = this.getRelativeXY();
		return this.group ? _r(e, this.group.calcTransformMatrix()) : e;
	}
	setXY(e, t, n) {
		this.group && (e = _r(e, vr(this.group.calcTransformMatrix()))), this.setRelativeXY(e, t, n);
	}
	getRelativeXY() {
		return new q(this.left, this.top);
	}
	setRelativeXY(e, t = this.originX, n = this.originY) {
		this.setPositionByOrigin(e, t, n);
	}
	isStrokeAccountedForInDimensions() {
		return !1;
	}
	getCoords() {
		let { tl: e, tr: t, br: n, bl: r } = this.aCoords ||= this.calcACoords(), i = [
			e,
			t,
			n,
			r
		];
		if (this.group) {
			let e = this.group.calcTransformMatrix();
			return i.map((t) => _r(t, e));
		}
		return i;
	}
	intersectsWithRect(e, t) {
		return go.intersectPolygonRectangle(this.getCoords(), e, t).status === "Intersection";
	}
	intersectsWithObject(e) {
		let t = go.intersectPolygonPolygon(this.getCoords(), e.getCoords());
		return t.status === "Intersection" || t.status === "Coincident" || e.isContainedWithinObject(this) || this.isContainedWithinObject(e);
	}
	isContainedWithinObject(e) {
		return this.getCoords().every((t) => e.containsPoint(t));
	}
	isContainedWithinRect(e, t) {
		let { left: n, top: r, width: i, height: a } = this.getBoundingRect();
		return n >= e.x && n + i <= t.x && r >= e.y && r + a <= t.y;
	}
	isOverlapping(e) {
		return this.intersectsWithObject(e) || this.isContainedWithinObject(e) || e.isContainedWithinObject(this);
	}
	containsPoint(e) {
		return go.isPointInPolygon(e, this.getCoords());
	}
	isOnScreen() {
		if (!this.canvas) return !1;
		let { tl: e, br: t } = this.canvas.vptCoords;
		return !!this.getCoords().some((n) => n.x <= t.x && n.x >= e.x && n.y <= t.y && n.y >= e.y) || !!this.intersectsWithRect(e, t) || this.containsPoint(e.midPointFrom(t));
	}
	isPartiallyOnScreen() {
		if (!this.canvas) return !1;
		let { tl: e, br: t } = this.canvas.vptCoords;
		return !!this.intersectsWithRect(e, t) || this.getCoords().every((n) => (n.x >= t.x || n.x <= e.x) && (n.y >= t.y || n.y <= e.y)) && this.containsPoint(e.midPointFrom(t));
	}
	getBoundingRect() {
		return si(this.getCoords());
	}
	getScaledWidth() {
		return this._getTransformedDimensions().x;
	}
	getScaledHeight() {
		return this._getTransformedDimensions().y;
	}
	scale(e) {
		this._set(Vn, e), this._set(Hn, e), this.setCoords();
	}
	scaleToWidth(e) {
		let t = this.getBoundingRect().width / this.getScaledWidth();
		return this.scale(e / this.width / t);
	}
	scaleToHeight(e) {
		let t = this.getBoundingRect().height / this.getScaledHeight();
		return this.scale(e / this.height / t);
	}
	getCanvasRetinaScaling() {
		return this.canvas?.getRetinaScaling() || 1;
	}
	getTotalAngle() {
		return this.group ? hr(br(this.calcTransformMatrix())) : this.angle;
	}
	getViewportTransform() {
		return this.canvas?.viewportTransform || Dn.concat();
	}
	calcACoords() {
		let e = Tr({ angle: this.angle }), { x: t, y: n } = this.getRelativeCenterPoint(), r = Y(wr(t, n), e), i = this._getTransformedDimensions(), a = i.x / 2, o = i.y / 2;
		return {
			tl: _r({
				x: -a,
				y: -o
			}, r),
			tr: _r({
				x: a,
				y: -o
			}, r),
			bl: _r({
				x: -a,
				y: o
			}, r),
			br: _r({
				x: a,
				y: o
			}, r)
		};
	}
	setCoords() {
		this.aCoords = this.calcACoords();
	}
	transformMatrixKey(e = !1) {
		let t = [];
		return !e && this.group && (t = this.group.transformMatrixKey(e)), t.push(this.top, this.left, this.width, this.height, this.scaleX, this.scaleY, this.angle, this.strokeWidth, this.skewX, this.skewY, +this.flipX, +this.flipY, yi(this.originX), yi(this.originY)), t;
	}
	calcTransformMatrix(e = !1) {
		let t = this.calcOwnMatrix();
		if (e || !this.group) return t;
		let n = this.transformMatrixKey(e), r = this.matrixCache;
		return r && r.key.every((e, t) => e === n[t]) ? r.value : (this.group && (t = Y(this.group.calcTransformMatrix(!1), t)), this.matrixCache = {
			key: n,
			value: t
		}, t);
	}
	calcOwnMatrix() {
		let e = this.transformMatrixKey(!0), t = this.ownMatrixCache;
		if (t && t.key.every((t, n) => t === e[n])) return t.value;
		let n = this.getRelativeCenterPoint(), r = jr({
			angle: this.angle,
			translateX: n.x,
			translateY: n.y,
			scaleX: this.scaleX,
			scaleY: this.scaleY,
			skewX: this.skewX,
			skewY: this.skewY,
			flipX: this.flipX,
			flipY: this.flipY
		});
		return this.ownMatrixCache = {
			key: e,
			value: r
		}, r;
	}
	_getNonTransformedDimensions() {
		return new q(this.width, this.height).scalarAdd(this.strokeWidth);
	}
	_calculateCurrentDimensions(e) {
		let t = this.canvas?.viewportTransform, n = this._getTransformedDimensions(e);
		return t ? n.multiply(new q(xr(t), Sr(t))).scalarAdd(2 * this.padding) : n.scalarAdd(2 * this.padding);
	}
	_getTransformedDimensions(e = {}) {
		let t = {
			scaleX: this.scaleX,
			scaleY: this.scaleY,
			skewX: this.skewX,
			skewY: this.skewY,
			width: this.width,
			height: this.height,
			strokeWidth: this.strokeWidth,
			...e
		}, n = t.strokeWidth, r = n, i = 0;
		this.strokeUniform && (r = 0, i = n);
		let a = t.width + r, o = t.height + r, s;
		return s = t.skewX === 0 && t.skewY === 0 ? new q(a * t.scaleX, o * t.scaleY) : pi(a, o, Ar(t)), s.scalarAdd(i);
	}
	translateToGivenOrigin(e, t, n, r, i) {
		let a = e.x, o = e.y, s = yi(r) - yi(t), c = yi(i) - yi(n);
		if (s || c) {
			let e = this._getTransformedDimensions();
			a += s * e.x, o += c * e.y;
		}
		return new q(a, o);
	}
	translateToCenterPoint(e, t, n) {
		if (t === "center" && n === "center") return e;
		let r = this.translateToGivenOrigin(e, t, n, W, W);
		return this.angle ? r.rotate(J(this.angle), e) : r;
	}
	translateToOriginPoint(e, t, n) {
		let r = this.translateToGivenOrigin(e, W, W, t, n);
		return this.angle ? r.rotate(J(this.angle), e) : r;
	}
	getCenterPoint() {
		let e = this.getRelativeCenterPoint();
		return this.group ? _r(e, this.group.calcTransformMatrix()) : e;
	}
	getRelativeCenterPoint() {
		return this.translateToCenterPoint(new q(this.left, this.top), this.originX, this.originY);
	}
	getPointByOrigin(e, t) {
		return this.getPositionByOrigin(e, t);
	}
	getPositionByOrigin(e, t) {
		return this.translateToOriginPoint(this.getRelativeCenterPoint(), e, t);
	}
	setPositionByOrigin(e, t, n) {
		let r = this.translateToCenterPoint(e, t, n), i = this.translateToOriginPoint(r, this.originX, this.originY);
		this.set({
			left: i.x,
			top: i.y
		});
	}
	_getLeftTopCoords() {
		return this.getPositionByOrigin(G, "top");
	}
	positionByLeftTop(e) {
		return this.setPositionByOrigin(e, G, "top");
	}
}, vo = class e extends _o {
	static getDefaults() {
		return e.ownDefaults;
	}
	get type() {
		let e = this.constructor.type;
		return e === "FabricObject" ? "object" : e.toLowerCase();
	}
	set type(e) {
		ln("warn", "Setting type has no effect", e);
	}
	constructor(t) {
		super(), H(this, "_cacheContext", null), Object.assign(this, e.ownDefaults), this.setOptions(t);
	}
	_createCacheCanvas() {
		this._cacheCanvas = lr(), this._cacheContext = this._cacheCanvas.getContext("2d"), this._updateCacheCanvas(), this.dirty = !0;
	}
	_limitCacheSize(e) {
		let t = e.width, n = e.height, r = U.maxCacheSideLimit, i = U.minCacheSideLimit;
		if (t <= r && n <= r && t * n <= U.perfLimitSizeTotal) return t < i && (e.width = i), n < i && (e.height = i), e;
		let a = t / n, [o, s] = bn.limitDimsByArea(a), c = Sa(i, o, r), l = Sa(i, s, r);
		return t > c && (e.zoomX /= t / c, e.width = c, e.capped = !0), n > l && (e.zoomY /= n / l, e.height = l, e.capped = !0), e;
	}
	_getCacheCanvasDimensions() {
		let e = this.getTotalObjectScaling(), t = this._getTransformedDimensions({
			skewX: 0,
			skewY: 0
		}), n = t.x * e.x / this.scaleX, r = t.y * e.y / this.scaleY;
		return {
			width: Math.ceil(n + 2),
			height: Math.ceil(r + 2),
			zoomX: e.x,
			zoomY: e.y,
			x: n,
			y: r
		};
	}
	_updateCacheCanvas() {
		let e = this._cacheCanvas, t = this._cacheContext, { width: n, height: r, zoomX: i, zoomY: a, x: o, y: s } = this._limitCacheSize(this._getCacheCanvasDimensions()), c = n !== e.width || r !== e.height, l = this.zoomX !== i || this.zoomY !== a;
		if (!e || !t) return !1;
		if (c || l) {
			n !== e.width || r !== e.height ? (e.width = n, e.height = r) : (t.setTransform(1, 0, 0, 1, 0, 0), t.clearRect(0, 0, e.width, e.height));
			let c = o / 2, l = s / 2;
			return this.cacheTranslationX = Math.round(e.width / 2 - c) + c, this.cacheTranslationY = Math.round(e.height / 2 - l) + l, t.translate(this.cacheTranslationX, this.cacheTranslationY), t.scale(i, a), this.zoomX = i, this.zoomY = a, !0;
		}
		return !1;
	}
	setOptions(e = {}) {
		this._setOptions(e);
	}
	transform(e) {
		let t = this.group && !this.group._transformDone || this.group && this.canvas && e === this.canvas.contextTop, n = this.calcTransformMatrix(!t);
		e.transform(n[0], n[1], n[2], n[3], n[4], n[5]);
	}
	getObjectScaling() {
		if (!this.group) return new q(Math.abs(this.scaleX), Math.abs(this.scaleY));
		let e = Cr(this.calcTransformMatrix());
		return new q(Math.abs(e.scaleX), Math.abs(e.scaleY));
	}
	getTotalObjectScaling() {
		let e = this.getObjectScaling();
		if (this.canvas) {
			let t = this.canvas.getZoom(), n = this.getCanvasRetinaScaling();
			return e.scalarMultiply(t * n);
		}
		return e;
	}
	getObjectOpacity() {
		let e = this.opacity;
		return this.group && (e *= this.group.getObjectOpacity()), e;
	}
	_constrainScale(e) {
		return Math.abs(e) < this.minScaleLimit ? e < 0 ? -this.minScaleLimit : this.minScaleLimit : e === 0 ? 1e-4 : e;
	}
	_set(e, t) {
		e !== "scaleX" && e !== "scaleY" || (t = this._constrainScale(t)), e === "scaleX" && t < 0 ? (this.flipX = !this.flipX, t *= -1) : e === "scaleY" && t < 0 ? (this.flipY = !this.flipY, t *= -1) : e !== "shadow" || !t || t instanceof xa || (t = new xa(t));
		let n = this[e] !== t;
		return this[e] = t, n && this.constructor.cacheProperties.includes(e) && (this.dirty = !0), this.parent && (this.dirty || n && this.constructor.stateProperties.includes(e)) && this.parent._set("dirty", !0), this;
	}
	isNotVisible() {
		return this.opacity === 0 || !this.width && !this.height && this.strokeWidth === 0 || !this.visible;
	}
	render(e) {
		this.isNotVisible() || this.canvas && this.canvas.skipOffscreen && !this.group && !this.isOnScreen() || (e.save(), this._setupCompositeOperation(e), this.drawSelectionBackground(e), this.transform(e), this._setOpacity(e), this._setShadow(e), this.shouldCache() ? (this.renderCache(), this.drawCacheOnCanvas(e)) : (this._removeCacheCanvas(), this.drawObject(e, !1, {}), this.dirty = !1), e.restore());
	}
	drawSelectionBackground(e) {}
	renderCache(e) {
		if (e ||= {}, this._cacheCanvas && this._cacheContext || this._createCacheCanvas(), this.isCacheDirty() && this._cacheContext) {
			let { zoomX: t, zoomY: n, cacheTranslationX: r, cacheTranslationY: i } = this, { width: a, height: o } = this._cacheCanvas;
			this.drawObject(this._cacheContext, e.forClipping, {
				zoomX: t,
				zoomY: n,
				cacheTranslationX: r,
				cacheTranslationY: i,
				width: a,
				height: o,
				parentClipPaths: []
			}), this.dirty = !1;
		}
	}
	_removeCacheCanvas() {
		this._cacheCanvas = void 0, this._cacheContext = null;
	}
	hasStroke() {
		return !!this.stroke && this.stroke !== "transparent" && this.strokeWidth !== 0;
	}
	hasFill() {
		return !!this.fill && this.fill !== "transparent";
	}
	needsItsOwnCache() {
		return !!(this.paintFirst === "stroke" && this.hasFill() && this.hasStroke() && this.shadow) || !!this.clipPath;
	}
	shouldCache() {
		return this.ownCaching = this.objectCaching && (!this.parent || !this.parent.isOnACache()) || this.needsItsOwnCache(), this.ownCaching;
	}
	willDrawShadow() {
		return !!this.shadow && (this.shadow.offsetX !== 0 || this.shadow.offsetY !== 0);
	}
	drawClipPathOnCache(e, t, n) {
		e.save(), t.inverted ? e.globalCompositeOperation = "destination-out" : e.globalCompositeOperation = "destination-in", e.setTransform(1, 0, 0, 1, 0, 0), e.drawImage(n, 0, 0), e.restore();
	}
	drawObject(e, t, n) {
		let r = this.fill, i = this.stroke;
		t ? (this.fill = "black", this.stroke = "", this._setClippingProperties(e)) : this._renderBackground(e), this.fire("before:render", { ctx: e }), this._render(e), this._drawClipPath(e, this.clipPath, n), this.fill = r, this.stroke = i;
	}
	createClipPathLayer(e, t) {
		let n = fr(t), r = n.getContext("2d");
		if (r.translate(t.cacheTranslationX, t.cacheTranslationY), r.scale(t.zoomX, t.zoomY), e._cacheCanvas = n, t.parentClipPaths.forEach((e) => {
			e.transform(r);
		}), t.parentClipPaths.push(e), e.absolutePositioned) {
			let e = vr(this.calcTransformMatrix());
			r.transform(e[0], e[1], e[2], e[3], e[4], e[5]);
		}
		return e.transform(r), e.drawObject(r, !0, t), n;
	}
	_drawClipPath(e, t, n) {
		if (!t) return;
		t._transformDone = !0;
		let r = this.createClipPathLayer(t, n);
		this.drawClipPathOnCache(e, t, r);
	}
	drawCacheOnCanvas(e) {
		e.scale(1 / this.zoomX, 1 / this.zoomY), e.drawImage(this._cacheCanvas, -this.cacheTranslationX, -this.cacheTranslationY);
	}
	isCacheDirty(e = !1) {
		if (this.isNotVisible()) return !1;
		let t = this._cacheCanvas, n = this._cacheContext;
		return !(!t || !n || e || !this._updateCacheCanvas()) || !!(this.dirty || this.clipPath && this.clipPath.absolutePositioned) && (t && n && !e && (n.save(), n.setTransform(1, 0, 0, 1, 0, 0), n.clearRect(0, 0, t.width, t.height), n.restore()), !0);
	}
	_renderBackground(e) {
		if (!this.backgroundColor) return;
		let t = this._getNonTransformedDimensions();
		e.fillStyle = this.backgroundColor, e.fillRect(-t.x / 2, -t.y / 2, t.x, t.y), this._removeShadow(e);
	}
	_setOpacity(e) {
		this.group && !this.group._transformDone ? e.globalAlpha = this.getObjectOpacity() : e.globalAlpha *= this.opacity;
	}
	_setStrokeStyles(e, t) {
		let n = t.stroke;
		n && (e.lineWidth = t.strokeWidth, e.lineCap = t.strokeLineCap, e.lineDashOffset = t.strokeDashOffset, e.lineJoin = t.strokeLineJoin, e.miterLimit = t.strokeMiterLimit, Rr(n) ? n.gradientUnits === "percentage" || n.gradientTransform || n.patternTransform ? this._applyPatternForTransformedGradient(e, n) : (e.strokeStyle = n.toLive(e), this._applyPatternGradientTransform(e, n)) : e.strokeStyle = t.stroke);
	}
	_setFillStyles(e, { fill: t }) {
		t && (Rr(t) ? (e.fillStyle = t.toLive(e), this._applyPatternGradientTransform(e, t)) : e.fillStyle = t);
	}
	_setClippingProperties(e) {
		e.globalAlpha = 1, e.strokeStyle = "transparent", e.fillStyle = "#000000";
	}
	_setLineDash(e, t) {
		t && t.length !== 0 && e.setLineDash(t);
	}
	_setShadow(e) {
		if (!this.shadow) return;
		let t = this.shadow, n = this.canvas, r = this.getCanvasRetinaScaling(), [i, , , a] = n?.viewportTransform || Dn, o = i * r, s = a * r, c = t.nonScaling ? new q(1, 1) : this.getObjectScaling();
		e.shadowColor = t.color, e.shadowBlur = t.blur * U.browserShadowBlurConstant * (o + s) * (c.x + c.y) / 4, e.shadowOffsetX = t.offsetX * o * c.x, e.shadowOffsetY = t.offsetY * s * c.y;
	}
	_removeShadow(e) {
		this.shadow && (e.shadowColor = "", e.shadowBlur = e.shadowOffsetX = e.shadowOffsetY = 0);
	}
	_applyPatternGradientTransform(e, t) {
		if (!Rr(t)) return {
			offsetX: 0,
			offsetY: 0
		};
		let n = t.gradientTransform || t.patternTransform, r = -this.width / 2 + t.offsetX || 0, i = -this.height / 2 + t.offsetY || 0;
		return t.gradientUnits === "percentage" ? e.transform(this.width, 0, 0, this.height, r, i) : e.transform(1, 0, 0, 1, r, i), n && e.transform(n[0], n[1], n[2], n[3], n[4], n[5]), {
			offsetX: r,
			offsetY: i
		};
	}
	_renderPaintInOrder(e) {
		this.paintFirst === "stroke" ? (this._renderStroke(e), this._renderFill(e)) : (this._renderFill(e), this._renderStroke(e));
	}
	_render(e) {}
	_renderFill(e) {
		this.fill && (e.save(), this._setFillStyles(e, this), this.fillRule === "evenodd" ? e.fill("evenodd") : e.fill(), e.restore());
	}
	_renderStroke(e) {
		if (this.stroke && this.strokeWidth !== 0) {
			if (this.shadow && !this.shadow.affectStroke && this._removeShadow(e), e.save(), this.strokeUniform) {
				let t = this.getObjectScaling();
				e.scale(1 / t.x, 1 / t.y);
			}
			this._setLineDash(e, this.strokeDashArray), this._setStrokeStyles(e, this), e.stroke(), e.restore();
		}
	}
	_applyPatternForTransformedGradient(e, t) {
		let n = this._limitCacheSize(this._getCacheCanvasDimensions()), r = this.getCanvasRetinaScaling(), i = n.x / this.scaleX / r, a = n.y / this.scaleY / r, o = fr({
			width: Math.ceil(i),
			height: Math.ceil(a)
		}), s = o.getContext("2d");
		s && (s.beginPath(), s.moveTo(0, 0), s.lineTo(i, 0), s.lineTo(i, a), s.lineTo(0, a), s.closePath(), s.translate(i / 2, a / 2), s.scale(n.zoomX / this.scaleX / r, n.zoomY / this.scaleY / r), this._applyPatternGradientTransform(s, t), s.fillStyle = t.toLive(e), s.fill(), e.translate(-this.width / 2 - this.strokeWidth / 2, -this.height / 2 - this.strokeWidth / 2), e.scale(r * this.scaleX / n.zoomX, r * this.scaleY / n.zoomY), e.strokeStyle = s.createPattern(o, "no-repeat") ?? "");
	}
	_findCenterFromElement() {
		return new q(this.left + this.width / 2, this.top + this.height / 2);
	}
	clone(e) {
		let t = this.toObject(e);
		return this.constructor.fromObject(t);
	}
	cloneAsImage(e) {
		let t = this.toCanvasElement(e);
		return new (K.getClass("image"))(t);
	}
	toCanvasElement(e = {}) {
		let t = fi(this), n = this.group, r = this.shadow, i = Math.abs, a = e.enableRetinaScaling ? yn() : 1, o = (e.multiplier || 1) * a, s = e.canvasProvider || ((e) => new ni(e, {
			enableRetinaScaling: !1,
			renderOnAddRemove: !1,
			skipOffscreen: !1
		}));
		delete this.group, e.withoutTransform && di(this), e.withoutShadow && (this.shadow = null), e.viewportTransform && _i(this, this.getViewportTransform()), this.setCoords();
		let c = lr(), l = this.getBoundingRect(), u = this.shadow, d = new q();
		if (u) {
			let e = u.blur, t = u.nonScaling ? new q(1, 1) : this.getObjectScaling();
			d.x = 2 * Math.round(i(u.offsetX) + e) * i(t.x), d.y = 2 * Math.round(i(u.offsetY) + e) * i(t.y);
		}
		let f = l.width + d.x, p = l.height + d.y;
		c.width = Math.ceil(f), c.height = Math.ceil(p);
		let m = s(c);
		e.format === "jpeg" && (m.backgroundColor = "#fff"), this.setPositionByOrigin(new q(m.width / 2, m.height / 2), W, W);
		let h = this.canvas;
		m._objects = [this], this.set("canvas", m), this.setCoords();
		let g = m.toCanvasElement(o || 1, e);
		return this.set("canvas", h), this.shadow = r, n && (this.group = n), this.set(t), this.setCoords(), m._objects = [], m.destroy(), g;
	}
	toDataURL(e = {}) {
		return pr(this.toCanvasElement(e), e.format || "png", e.quality || 1);
	}
	toBlob(e = {}) {
		return mr(this.toCanvasElement(e), e.format || "png", e.quality || 1);
	}
	isType(...e) {
		return e.includes(this.constructor.type) || e.includes(this.type);
	}
	complexity() {
		return 1;
	}
	toJSON() {
		return this.toObject();
	}
	rotate(e) {
		let { centeredRotation: t, originX: n, originY: r } = this;
		if (t) {
			let { x: e, y: t } = this.getRelativeCenterPoint();
			this.originX = W, this.originY = W, this.left = e, this.top = t;
		}
		if (this.set("angle", e), t) {
			let { x: e, y: t } = this.getPositionByOrigin(n, r);
			this.left = e, this.top = t, this.originX = n, this.originY = r;
		}
	}
	setOnGroup() {}
	_setupCompositeOperation(e) {
		this.globalCompositeOperation && (e.globalCompositeOperation = this.globalCompositeOperation);
	}
	dispose() {
		Xn.cancelByTarget(this), this.off(), this._set("canvas", void 0), this._cacheCanvas && gn().dispose(this._cacheCanvas), this._cacheCanvas = void 0, this._cacheContext = null;
	}
	animate(e, t) {
		return Object.entries(e).reduce((e, [n, r]) => (e[n] = this._animate(n, r, t), e), {});
	}
	_animate(e, t, n = {}) {
		let r = e.split("."), i = this.constructor.colorProperties.includes(r[r.length - 1]), { abort: a, startValue: o, onChange: s, onComplete: c } = n, l = {
			...n,
			target: this,
			startValue: o ?? r.reduce((e, t) => e[t], this),
			endValue: t,
			abort: a?.bind(this),
			onChange: (e, t, n) => {
				r.reduce((t, n, i) => (i === r.length - 1 && (t[n] = e), t[n]), this), s && s(e, t, n);
			},
			onComplete: (e, t, n) => {
				this.setCoords(), c && c(e, t, n);
			}
		};
		return i ? ho(l) : mo(l);
	}
	isDescendantOf(e) {
		let { parent: t, group: n } = this;
		return t === e || n === e || !!t && t.isDescendantOf(e) || !!n && n !== t && n.isDescendantOf(e);
	}
	getAncestors() {
		let e = [], t = this;
		do
			t = t.parent, t && e.push(t);
		while (t);
		return e;
	}
	findCommonAncestors(e) {
		if (this === e) return {
			fork: [],
			otherFork: [],
			common: [this, ...this.getAncestors()]
		};
		let t = this.getAncestors(), n = e.getAncestors();
		if (t.length === 0 && n.length > 0 && this === n[n.length - 1]) return {
			fork: [],
			otherFork: [e, ...n.slice(0, n.length - 1)],
			common: [this]
		};
		for (let r, i = 0; i < t.length; i++) {
			if (r = t[i], r === e) return {
				fork: [this, ...t.slice(0, i)],
				otherFork: [],
				common: t.slice(i)
			};
			for (let a = 0; a < n.length; a++) {
				if (this === n[a]) return {
					fork: [],
					otherFork: [e, ...n.slice(0, a)],
					common: [this, ...t]
				};
				if (r === n[a]) return {
					fork: [this, ...t.slice(0, i)],
					otherFork: [e, ...n.slice(0, a)],
					common: t.slice(i)
				};
			}
		}
		return {
			fork: [this, ...t],
			otherFork: [e, ...n],
			common: []
		};
	}
	hasCommonAncestors(e) {
		let t = this.findCommonAncestors(e);
		return t && !!t.common.length;
	}
	isInFrontOf(e) {
		if (this === e) return;
		let t = this.findCommonAncestors(e);
		if (t.fork.includes(e)) return !0;
		if (t.otherFork.includes(this)) return !1;
		let n = t.common[0] || this.canvas;
		if (!n) return;
		let r = t.fork.pop(), i = t.otherFork.pop(), a = n._objects.indexOf(r), o = n._objects.indexOf(i);
		return a > -1 && a > o;
	}
	toObject(t = []) {
		let n = t.concat(e.customProperties, this.constructor.customProperties || []), r, i = U.NUM_FRACTION_DIGITS, { clipPath: a, fill: o, stroke: s, shadow: c, strokeDashArray: l, left: u, top: d, originX: f, originY: p, width: m, height: h, strokeWidth: g, strokeLineCap: _, strokeDashOffset: v, strokeLineJoin: y, strokeUniform: b, strokeMiterLimit: x, scaleX: S, scaleY: C, angle: w, flipX: T, flipY: E, opacity: D, visible: O, backgroundColor: ee, fillRule: te, paintFirst: ne, globalCompositeOperation: re, skewX: k, skewY: ie } = this;
		a && !a.excludeFromExport && (r = a.toObject(n.concat("inverted", "absolutePositioned")));
		let A = (e) => X(e, i), ae = {
			...Fr(this, n),
			type: this.constructor.type,
			version: xn,
			originX: f,
			originY: p,
			left: A(u),
			top: A(d),
			width: A(m),
			height: A(h),
			fill: zr(o) ? o.toObject() : o,
			stroke: zr(s) ? s.toObject() : s,
			strokeWidth: A(g),
			strokeDashArray: l && l.concat(),
			strokeLineCap: _,
			strokeDashOffset: v,
			strokeLineJoin: y,
			strokeUniform: b,
			strokeMiterLimit: A(x),
			scaleX: A(S),
			scaleY: A(C),
			angle: A(w),
			flipX: T,
			flipY: E,
			opacity: A(D),
			shadow: c && c.toObject(),
			visible: O,
			backgroundColor: ee,
			fillRule: te,
			paintFirst: ne,
			globalCompositeOperation: re,
			skewX: A(k),
			skewY: A(ie),
			...r ? { clipPath: r } : null
		};
		return this.includeDefaultValues ? ae : this._removeDefaultValues(ae);
	}
	toDatalessObject(e) {
		return this.toObject(e);
	}
	_removeDefaultValues(e) {
		let t = this.constructor.getDefaults(), n = Object.keys(t).length > 0 ? t : Object.getPrototypeOf(this);
		return Ir(e, (e, t) => {
			if (t === "left" || t === "top" || t === "type") return !0;
			let r = n[t];
			return e !== r && !(Array.isArray(e) && Array.isArray(r) && e.length === 0 && r.length === 0);
		});
	}
	toString() {
		return `#<${this.constructor.type}>`;
	}
	static _fromObject({ type: e, ...t }, { extraParam: n, ...r } = {}) {
		return Pr(t, r).then((e) => n ? (delete e[n], new this(t[n], e)) : new this(e));
	}
	static fromObject(e, t) {
		return this._fromObject(e, t);
	}
};
H(vo, "stateProperties", Ca), H(vo, "cacheProperties", wa), H(vo, "ownDefaults", Ta), H(vo, "type", "FabricObject"), H(vo, "colorProperties", [
	Gn,
	Kn,
	"backgroundColor"
]), H(vo, "customProperties", []), K.setClass(vo), K.setClass(vo, "object");
var yo = (e, t) => {
	var n;
	let { transform: { target: r } } = t;
	(n = r.canvas) == null || n.fire(`object:${e}`, {
		...t,
		target: r
	}), r.fire(e, t);
}, bo = (e, t, n) => (r, i, a, o) => {
	let s = t(r, i, a, o);
	return s && yo(e, {
		...Ii(r, i, a, o),
		...n
	}), s;
};
function xo(e) {
	return (t, n, r, i) => {
		let { target: a, originX: o, originY: s } = n, c = a.getPositionByOrigin(o, s), l = e(t, n, r, i);
		return a.setPositionByOrigin(c, n.originX, n.originY), l;
	};
}
var So = (e, t, n, r) => (i, a, o, s) => {
	let c = Ri(a, a.originX, a.originY, o, s)[n], l = yi(a[t]);
	if (l === 0 || l > 0 && c < 0 || l < 0 && c > 0) {
		let { target: t } = a, n = t.strokeWidth / (t.strokeUniform ? t[r] : 1), i = Ni(a) ? 2 : 1, o = t[e], s = Math.abs(c * i / t[r]) - n;
		return t.set(e, Math.max(s, 1)), o !== t[e];
	}
	return !1;
}, Co = So("width", "originX", "x", "scaleX"), wo = So("height", "originY", "y", "scaleY"), To = bo(Ln, xo(Co)), Eo = bo(Ln, xo(wo));
function Do(e, t, n, r, i) {
	e.save();
	let { stroke: a, xSize: o, ySize: s, opName: c } = this.commonRenderProps(e, t, n, i, r), l = o;
	o > s ? e.scale(1, s / o) : s > o && (l = s, e.scale(o / s, 1)), e.beginPath(), e.arc(0, 0, l / 2, 0, Tn, !1), e[c](), a && e.stroke(), e.restore();
}
function Oo(e, t, n, r, i) {
	e.save();
	let { stroke: a, xSize: o, ySize: s, opName: c } = this.commonRenderProps(e, t, n, i, r), l = o / 2, u = s / 2;
	e[`${c}Rect`](-l, -u, o, s), a && e.strokeRect(-l, -u, o, s), e.restore();
}
var ko = class {
	constructor(e) {
		H(this, "visible", !0), H(this, "actionName", Bn), H(this, "angle", 0), H(this, "x", 0), H(this, "y", 0), H(this, "offsetX", 0), H(this, "offsetY", 0), H(this, "sizeX", 0), H(this, "sizeY", 0), H(this, "touchSizeX", 0), H(this, "touchSizeY", 0), H(this, "cursorStyle", "crosshair"), H(this, "withConnection", !1), Object.assign(this, e);
	}
	getTransformAnchorPoint() {
		return this.transformAnchorPoint ?? new q(.5 - this.x, .5 - this.y);
	}
	shouldActivate(e, t, n, { tl: r, tr: i, br: a, bl: o }) {
		return t.canvas?.getActiveObject() === t && t.isControlVisible(e) && go.isPointInPolygon(n, [
			r,
			i,
			a,
			o
		]);
	}
	getActionHandler(e, t, n) {
		return this.actionHandler;
	}
	getMouseDownHandler(e, t, n) {
		return this.mouseDownHandler;
	}
	getMouseUpHandler(e, t, n) {
		return this.mouseUpHandler;
	}
	cursorStyleHandler(e, t, n, r) {
		return t.cursorStyle;
	}
	getActionName(e, t, n) {
		return t.actionName;
	}
	getVisibility(e, t) {
		return e._controlsVisibility?.[t] ?? this.visible;
	}
	setVisibility(e, t, n) {
		this.visible = e;
	}
	positionHandler(e, t, n, r) {
		return new q(this.x * e.x + this.offsetX, this.y * e.y + this.offsetY).transform(t);
	}
	calcCornerCoords(e, t, n, r, i, a) {
		let o = yr([
			wr(n, r),
			Tr({ angle: e }),
			Er((i ? this.touchSizeX : this.sizeX) || t, (i ? this.touchSizeY : this.sizeY) || t)
		]);
		return {
			tl: new q(-.5, -.5).transform(o),
			tr: new q(.5, -.5).transform(o),
			br: new q(.5, .5).transform(o),
			bl: new q(-.5, .5).transform(o)
		};
	}
	commonRenderProps(e, t, n, r, i = {}) {
		let { cornerSize: a, cornerColor: o, transparentCorners: s, cornerStrokeColor: c } = i, l = a || r.cornerSize, u = this.sizeX || l, d = this.sizeY || l, f = s === void 0 ? r.transparentCorners : s, p = f ? Kn : Gn, m = c || r.cornerStrokeColor, h = !f && !!m;
		return e.fillStyle = o || r.cornerColor || "", e.strokeStyle = m || "", e.translate(t, n), e.rotate(J(r.getTotalAngle())), {
			stroke: h,
			xSize: u,
			ySize: d,
			transparentCorners: f,
			opName: p
		};
	}
	render(e, t, n, r, i) {
		((r ||= {}).cornerStyle || i.cornerStyle) === "circle" ? Do.call(this, e, t, n, r, i) : Oo.call(this, e, t, n, r, i);
	}
}, Ao = (e, t, n) => n.lockRotation ? Mi : t.cursorStyle, jo = bo(Pn, xo((e, { target: t, ex: n, ey: r, theta: i, originX: a, originY: o }, s, c) => {
	let l = t.getPositionByOrigin(a, o);
	if (Fi(t, "lockRotation")) return !1;
	let u = Math.atan2(r - l.y, n - l.x), d = hr(Math.atan2(c - l.y, s - l.x) - u + i);
	if (t.snapAngle && t.snapAngle > 0) {
		let e = t.snapAngle, n = t.snapThreshold || e, r = Math.ceil(d / e) * e, i = Math.floor(d / e) * e;
		Math.abs(d - i) < n ? d = i : Math.abs(d - r) < n && (d = r);
	}
	d < 0 && (d = 360 + d), d %= 360;
	let f = t.angle !== d;
	return t.angle = d, f;
}));
function Mo(e, t) {
	let n = t.canvas, r = e[n.uniScaleKey];
	return n.uniformScaling && !r || !n.uniformScaling && r;
}
function No(e, t, n) {
	let r = Fi(e, "lockScalingX"), i = Fi(e, "lockScalingY");
	if (r && i || !t && (r || i) && n || r && t === "x" || i && t === "y") return !0;
	let { width: a, height: o, strokeWidth: s } = e;
	return a === 0 && s === 0 && t !== "y" || o === 0 && s === 0 && t !== "x";
}
var Po = [
	"e",
	"se",
	"s",
	"sw",
	"w",
	"nw",
	"n",
	"ne",
	"e"
], Fo = (e, t, n, r) => {
	let i = Mo(e, n);
	return No(n, t.x !== 0 && t.y === 0 ? "x" : t.x === 0 && t.y !== 0 ? "y" : "", i) ? Mi : `${Po[Li(n, 0, r)]}-resize`;
};
function Io(e, t, n, r, i = {}) {
	let a = t.target, o = i.by, s = Mo(e, a), c, l, u, d, f, p;
	if (No(a, o, s)) return !1;
	if (t.gestureScale) l = t.scaleX * t.gestureScale, u = t.scaleY * t.gestureScale;
	else {
		if (c = Ri(t, t.originX, t.originY, n, r), f = o === "y" ? 1 : Math.sign(c.x || t.signX || 1), p = o === "x" ? 1 : Math.sign(c.y || t.signY || 1), t.signX ||= f, t.signY ||= p, Fi(a, "lockScalingFlip") && (t.signX !== f || t.signY !== p)) return !1;
		if (d = a._getTransformedDimensions(), s && !o) {
			let e = Math.abs(c.x) + Math.abs(c.y), { original: n } = t, r = e / (Math.abs(d.x * n.scaleX / a.scaleX) + Math.abs(d.y * n.scaleY / a.scaleY));
			l = n.scaleX * r, u = n.scaleY * r;
		} else l = Math.abs(c.x * a.scaleX / d.x), u = Math.abs(c.y * a.scaleY / d.y);
		Ni(t) && (l *= 2, u *= 2), t.signX !== f && o !== "y" && (t.originX = Pi(t.originX), l *= -1, t.signX = f), t.signY !== p && o !== "x" && (t.originY = Pi(t.originY), u *= -1, t.signY = p);
	}
	let m = a.scaleX, h = a.scaleY;
	return o ? (o === "x" && a.set("scaleX", l), o === "y" && a.set("scaleY", u)) : (!Fi(a, "lockScalingX") && a.set("scaleX", l), !Fi(a, "lockScalingY") && a.set("scaleY", u)), m !== a.scaleX || h !== a.scaleY;
}
var Lo = bo(Nn, xo((e, t, n, r) => Io(e, t, n, r))), Ro = bo(Nn, xo((e, t, n, r) => Io(e, t, n, r, { by: "x" }))), zo = bo(Nn, xo((e, t, n, r) => Io(e, t, n, r, { by: "y" }))), Bo = {
	x: {
		counterAxis: "y",
		scale: Vn,
		skew: Un,
		lockSkewing: "lockSkewingX",
		origin: "originX",
		flip: "flipX"
	},
	y: {
		counterAxis: "x",
		scale: Hn,
		skew: Wn,
		lockSkewing: "lockSkewingY",
		origin: "originY",
		flip: "flipY"
	}
}, Vo = [
	"ns",
	"nesw",
	"ew",
	"nwse"
], Ho = (e, t, n, r) => t.x !== 0 && Fi(n, "lockSkewingY") || t.y !== 0 && Fi(n, "lockSkewingX") ? Mi : `${Vo[Li(n, 0, r) % 4]}-resize`;
function Uo(e, t, n, r, i) {
	let { target: a } = n, { counterAxis: o, origin: s, lockSkewing: c, skew: l, flip: u } = Bo[e];
	if (Fi(a, c)) return !1;
	let { origin: d, flip: f } = Bo[o], p = yi(n[d]) * (a[f] ? -1 : 1), m = -Math.sign(p) * (a[u] ? -1 : 1), h = -(a[l] === 0 && Ri(n, "center", "center", r, i)[e] > 0 || a[l] > 0 ? 1 : -1) * m * .5 + .5;
	return bo(In, xo((t, n, r, i) => function(e, { target: t, ex: n, ey: r, skewingSide: i, ...a }, o) {
		let { skew: s } = Bo[e], c = o.subtract(new q(n, r)).divide(new q(t.scaleX, t.scaleY))[e], l = t[s], u = a[s], d = Math.tan(J(u)), f = e === "y" ? t._getTransformedDimensions({
			scaleX: 1,
			scaleY: 1,
			skewX: 0
		}).x : t._getTransformedDimensions({
			scaleX: 1,
			scaleY: 1
		}).y, p = 2 * c * i / Math.max(f, 1) + d, m = hr(Math.atan(p));
		t.set(s, m);
		let h = l !== t[s];
		if (h && e === "y") {
			let { skewX: e, scaleX: n } = t, r = t._getTransformedDimensions({ skewY: l }), i = t._getTransformedDimensions(), a = e === 0 ? 1 : r.x / i.x;
			a !== 1 && t.set("scaleX", a * n);
		}
		return h;
	}(e, n, new q(r, i))))(t, {
		...n,
		[s]: h,
		skewingSide: m
	}, r, i);
}
var Wo = (e, t, n, r) => Uo("x", e, t, n, r), Go = (e, t, n, r) => Uo("y", e, t, n, r);
function Ko(e, t) {
	return e[t.canvas.altActionKey];
}
var qo = (e, t, n) => {
	let r = Ko(e, n);
	return t.x === 0 ? r ? Un : Hn : t.y === 0 ? r ? Wn : Vn : "";
}, Jo = (e, t, n, r) => Ko(e, n) ? Ho(0, t, n, r) : Fo(e, t, n, r), Yo = (e, t, n, r) => Ko(e, t.target) ? Go(e, t, n, r) : Ro(e, t, n, r), Xo = (e, t, n, r) => Ko(e, t.target) ? Wo(e, t, n, r) : zo(e, t, n, r), Zo = () => ({
	ml: new ko({
		x: -.5,
		y: 0,
		cursorStyleHandler: Jo,
		actionHandler: Yo,
		getActionName: qo
	}),
	mr: new ko({
		x: .5,
		y: 0,
		cursorStyleHandler: Jo,
		actionHandler: Yo,
		getActionName: qo
	}),
	mb: new ko({
		x: 0,
		y: .5,
		cursorStyleHandler: Jo,
		actionHandler: Xo,
		getActionName: qo
	}),
	mt: new ko({
		x: 0,
		y: -.5,
		cursorStyleHandler: Jo,
		actionHandler: Xo,
		getActionName: qo
	}),
	tl: new ko({
		x: -.5,
		y: -.5,
		cursorStyleHandler: Fo,
		actionHandler: Lo
	}),
	tr: new ko({
		x: .5,
		y: -.5,
		cursorStyleHandler: Fo,
		actionHandler: Lo
	}),
	bl: new ko({
		x: -.5,
		y: .5,
		cursorStyleHandler: Fo,
		actionHandler: Lo
	}),
	br: new ko({
		x: .5,
		y: .5,
		cursorStyleHandler: Fo,
		actionHandler: Lo
	}),
	mtr: new ko({
		x: 0,
		y: -.5,
		actionHandler: jo,
		cursorStyleHandler: Ao,
		offsetY: -40,
		withConnection: !0,
		actionName: Fn
	})
}), Qo = () => ({
	mr: new ko({
		x: .5,
		y: 0,
		actionHandler: To,
		cursorStyleHandler: Jo,
		actionName: Ln
	}),
	ml: new ko({
		x: -.5,
		y: 0,
		actionHandler: To,
		cursorStyleHandler: Jo,
		actionName: Ln
	})
}), $o = () => ({
	...Zo(),
	...Qo()
}), es = class e extends vo {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t) {
		super(), Object.assign(this, this.constructor.createControls(), e.ownDefaults), this.setOptions(t);
	}
	static createControls() {
		return { controls: Zo() };
	}
	_updateCacheCanvas() {
		let e = this.canvas;
		if (this.noScaleCache && e && e._currentTransform) {
			let t = e._currentTransform, n = t.target, r = t.action;
			if (this === n && r && r.startsWith("scale")) return !1;
		}
		return super._updateCacheCanvas();
	}
	getActiveControl() {
		let e = this.__corner;
		return e ? {
			key: e,
			control: this.controls[e],
			coord: this.oCoords[e]
		} : void 0;
	}
	findControl(e, t = !1) {
		if (!this.hasControls || !this.canvas) return;
		this.__corner = void 0;
		let n = Object.entries(this.oCoords);
		for (let r = n.length - 1; r >= 0; r--) {
			let [i, a] = n[r], o = this.controls[i];
			if (o.shouldActivate(i, this, e, t ? a.touchCorner : a.corner)) return this.__corner = i, {
				key: i,
				control: o,
				coord: this.oCoords[i]
			};
		}
	}
	calcOCoords() {
		let e = this.getViewportTransform(), t = xr(e), n = Sr(e), r = this.getCenterPoint(), i = Y(Y(e, Y(wr(r.x, r.y), Tr({ angle: this.getTotalAngle() - (this.group && this.flipX ? 180 : 0) }))), [
			1 / t,
			0,
			0,
			1 / n,
			0,
			0
		]), a = this.group ? Cr(this.calcTransformMatrix()) : void 0;
		a && (a.scaleX = Math.abs(a.scaleX), a.scaleY = Math.abs(a.scaleY));
		let o = this._calculateCurrentDimensions(a), s = {};
		return this.forEachControl((e, t) => {
			let n = e.positionHandler(o, i, this, e);
			s[t] = Object.assign(n, this._calcCornerCoords(e, n));
		}), s;
	}
	_calcCornerCoords(e, t) {
		let n = this.getTotalAngle();
		return {
			corner: e.calcCornerCoords(n, this.cornerSize, t.x, t.y, !1, this),
			touchCorner: e.calcCornerCoords(n, this.touchCornerSize, t.x, t.y, !0, this)
		};
	}
	setCoords() {
		super.setCoords(), this.canvas && (this.oCoords = this.calcOCoords());
	}
	forEachControl(e) {
		for (let t in this.controls) e(this.controls[t], t, this);
	}
	drawSelectionBackground(e) {
		if (!this.selectionBackgroundColor || this.canvas && this.canvas._activeObject !== this) return;
		e.save();
		let t = this.getRelativeCenterPoint(), n = this._calculateCurrentDimensions(), r = this.getViewportTransform();
		e.translate(t.x, t.y), e.scale(1 / r[0], 1 / r[3]), e.rotate(J(this.angle)), e.fillStyle = this.selectionBackgroundColor, e.fillRect(-n.x / 2, -n.y / 2, n.x, n.y), e.restore();
	}
	strokeBorders(e, t) {
		e.strokeRect(-t.x / 2, -t.y / 2, t.x, t.y);
	}
	_drawBorders(e, t, n = {}) {
		let r = {
			hasControls: this.hasControls,
			borderColor: this.borderColor,
			borderDashArray: this.borderDashArray,
			...n
		};
		e.save(), e.strokeStyle = r.borderColor, this._setLineDash(e, r.borderDashArray), this.strokeBorders(e, t), r.hasControls && this.drawControlsConnectingLines(e, t), e.restore();
	}
	_renderControls(e, t = {}) {
		let { hasBorders: n, hasControls: r } = this, i = {
			hasBorders: n,
			hasControls: r,
			...t
		}, a = this.getViewportTransform(), o = i.hasBorders, s = i.hasControls, c = Cr(Y(a, this.calcTransformMatrix()));
		e.save(), e.translate(c.translateX, c.translateY), e.lineWidth = this.borderScaleFactor, this.group === this.parent && (e.globalAlpha = this.isMoving ? this.borderOpacityWhenMoving : 1), this.flipX && (c.angle -= 180);
		let l = br(a);
		e.rotate(this.group ? J(c.angle) : J(this.angle) + l), o && this.drawBorders(e, c, t), s && this.drawControls(e, t), e.restore();
	}
	drawBorders(e, t, n) {
		let r;
		if (n && n.forActiveSelection || this.group) {
			let e = pi(this.width, this.height, Ar(t)), n = this.isStrokeAccountedForInDimensions() ? tr : (this.strokeUniform ? new q().scalarAdd(this.canvas ? this.canvas.getZoom() : 1) : new q(t.scaleX, t.scaleY)).scalarMultiply(this.strokeWidth);
			r = e.add(n).scalarAdd(this.borderScaleFactor).scalarAdd(2 * this.padding);
		} else r = this._calculateCurrentDimensions().scalarAdd(this.borderScaleFactor);
		this._drawBorders(e, r, n);
	}
	drawControlsConnectingLines(e, t) {
		let n = !1;
		e.beginPath(), this.forEachControl((r, i) => {
			r.withConnection && r.getVisibility(this, i) && (n = !0, e.moveTo(r.x * t.x, r.y * t.y), e.lineTo(r.x * t.x + r.offsetX, r.y * t.y + r.offsetY));
		}), n && e.stroke();
	}
	drawControls(e, t = {}) {
		e.save();
		let n = this.getCanvasRetinaScaling(), { cornerStrokeColor: r, cornerDashArray: i, cornerColor: a } = this, o = {
			cornerStrokeColor: r,
			cornerDashArray: i,
			cornerColor: a,
			...t
		};
		e.setTransform(n, 0, 0, n, 0, 0), e.strokeStyle = e.fillStyle = o.cornerColor, this.transparentCorners || (e.strokeStyle = o.cornerStrokeColor), this._setLineDash(e, o.cornerDashArray), this.forEachControl((t, n) => {
			if (t.getVisibility(this, n)) {
				let r = this.oCoords[n];
				t.render(e, r.x, r.y, o, this);
			}
		}), e.restore();
	}
	isControlVisible(e) {
		return this.controls[e] && this.controls[e].getVisibility(this, e);
	}
	setControlVisible(e, t) {
		this._controlsVisibility ||= {}, this._controlsVisibility[e] = t;
	}
	setControlsVisibility(e = {}) {
		Object.entries(e).forEach(([e, t]) => this.setControlVisible(e, t));
	}
	clearContextTop(e) {
		if (!this.canvas) return;
		let t = this.canvas.contextTop;
		if (!t) return;
		let n = this.canvas.viewportTransform;
		t.save(), t.transform(n[0], n[1], n[2], n[3], n[4], n[5]), this.transform(t);
		let r = this.width + 4, i = this.height + 4;
		return t.clearRect(-r / 2, -i / 2, r, i), e || t.restore(), t;
	}
	onDeselect(e) {
		return !1;
	}
	onSelect(e) {
		return !1;
	}
	shouldStartDragging(e) {
		return !1;
	}
	onDragStart(e) {
		return !1;
	}
	canDrop(e) {
		return !1;
	}
	renderDragSourceEffect(e) {}
	renderDropTargetEffect(e) {}
};
function ts(e, t) {
	return t.forEach((t) => {
		Object.getOwnPropertyNames(t.prototype).forEach((n) => {
			n !== "constructor" && Object.defineProperty(e.prototype, n, Object.getOwnPropertyDescriptor(t.prototype, n) || Object.create(null));
		});
	}), e;
}
H(es, "ownDefaults", {
	noScaleCache: !0,
	lockMovementX: !1,
	lockMovementY: !1,
	lockRotation: !1,
	lockScalingX: !1,
	lockScalingY: !1,
	lockSkewingX: !1,
	lockSkewingY: !1,
	lockScalingFlip: !1,
	cornerSize: 13,
	touchCornerSize: 24,
	transparentCorners: !0,
	cornerColor: "rgb(178,204,255)",
	cornerStrokeColor: "",
	cornerStyle: "rect",
	cornerDashArray: null,
	hasControls: !0,
	borderColor: "rgb(178,204,255)",
	borderDashArray: null,
	borderOpacityWhenMoving: .4,
	borderScaleFactor: 1,
	hasBorders: !0,
	selectionBackgroundColor: "",
	selectable: !0,
	evented: !0,
	perPixelTargetFind: !1,
	activeOn: "down",
	hoverCursor: null,
	moveCursor: null
});
var ns = class extends es {};
ts(ns, [ta]), K.setClass(ns), K.setClass(ns, "object");
var rs = (e, t, n, r) => {
	let i = 2 * (r = Math.round(r)) + 1, { data: a } = e.getImageData(t - r, n - r, i, i);
	for (let e = 3; e < a.length; e += 4) if (a[e] > 0) return !1;
	return !0;
}, is = class {
	constructor(e) {
		this.options = e, this.strokeProjectionMagnitude = this.options.strokeWidth / 2, this.scale = new q(this.options.scaleX, this.options.scaleY), this.strokeUniformScalar = this.options.strokeUniform ? new q(1 / this.options.scaleX, 1 / this.options.scaleY) : new q(1, 1);
	}
	createSideVector(e, t) {
		let n = Ci(e, t);
		return this.options.strokeUniform ? n.multiply(this.scale) : n;
	}
	projectOrthogonally(e, t, n) {
		return this.applySkew(e.add(this.calcOrthogonalProjection(e, t, n)));
	}
	isSkewed() {
		return this.options.skewX !== 0 || this.options.skewY !== 0;
	}
	applySkew(e) {
		let t = new q(e);
		return t.y += t.x * Math.tan(J(this.options.skewY)), t.x += t.y * Math.tan(J(this.options.skewX)), t;
	}
	scaleUnitVector(e, t) {
		return e.multiply(this.strokeUniformScalar).scalarMultiply(t);
	}
}, as = new q(), os = class e extends is {
	static getOrthogonalRotationFactor(e, t) {
		let n = t ? Ti(e, t) : Ei(e);
		return Math.abs(n) < Cn ? -1 : 1;
	}
	constructor(e, t, n, r) {
		super(r), H(this, "AB", void 0), H(this, "AC", void 0), H(this, "alpha", void 0), H(this, "bisector", void 0), this.A = new q(e), this.B = new q(t), this.C = new q(n), this.AB = this.createSideVector(this.A, this.B), this.AC = this.createSideVector(this.A, this.C), this.alpha = Ti(this.AB, this.AC), this.bisector = Di(Si(this.AB.eq(as) ? this.AC : this.AB, this.alpha / 2));
	}
	calcOrthogonalProjection(t, n, r = this.strokeProjectionMagnitude) {
		let i = Oi(this.createSideVector(t, n)), a = e.getOrthogonalRotationFactor(i, this.bisector);
		return this.scaleUnitVector(i, r * a);
	}
	projectBevel() {
		let e = [];
		return (this.alpha % Tn === 0 ? [this.B] : [this.B, this.C]).forEach((t) => {
			e.push(this.projectOrthogonally(this.A, t)), e.push(this.projectOrthogonally(this.A, t, -this.strokeProjectionMagnitude));
		}), e;
	}
	projectMiter() {
		let e = [], t = Math.abs(this.alpha), n = 1 / Math.sin(t / 2), r = this.scaleUnitVector(this.bisector, -this.strokeProjectionMagnitude * n), i = this.options.strokeUniform ? wi(this.scaleUnitVector(this.bisector, this.options.strokeMiterLimit)) : this.options.strokeMiterLimit;
		return wi(r) / this.strokeProjectionMagnitude <= i && e.push(this.applySkew(this.A.add(r))), e.push(...this.projectBevel()), e;
	}
	projectRoundNoSkew(t, n) {
		let r = [], i = new q(e.getOrthogonalRotationFactor(this.bisector), e.getOrthogonalRotationFactor(new q(this.bisector.y, this.bisector.x)));
		return [new q(1, 0).scalarMultiply(this.strokeProjectionMagnitude).multiply(this.strokeUniformScalar).multiply(i), new q(0, 1).scalarMultiply(this.strokeProjectionMagnitude).multiply(this.strokeUniformScalar).multiply(i)].forEach((e) => {
			ji(e, t, n) && r.push(this.A.add(e));
		}), r;
	}
	projectRoundWithSkew(e, t) {
		let n = [], { skewX: r, skewY: i, scaleX: a, scaleY: o, strokeUniform: s } = this.options, c = new q(Math.tan(J(r)), Math.tan(J(i))), l = this.strokeProjectionMagnitude, u = s ? l / o / Math.sqrt(1 / o ** 2 + 1 / a ** 2 * c.y ** 2) : l / Math.sqrt(1 + c.y ** 2), d = new q(Math.sqrt(Math.max(l ** 2 - u ** 2, 0)), u), f = s ? l / Math.sqrt(1 + c.x ** 2 * (1 / o) ** 2 / (1 / a + 1 / a * c.x * c.y) ** 2) : l / Math.sqrt(1 + c.x ** 2 / (1 + c.x * c.y) ** 2), p = new q(f, Math.sqrt(Math.max(l ** 2 - f ** 2, 0)));
		return [
			p,
			p.scalarMultiply(-1),
			d,
			d.scalarMultiply(-1)
		].map((e) => this.applySkew(s ? e.multiply(this.strokeUniformScalar) : e)).forEach((r) => {
			ji(r, e, t) && n.push(this.applySkew(this.A).add(r));
		}), n;
	}
	projectRound() {
		let e = [];
		e.push(...this.projectBevel());
		let t = this.alpha % Tn === 0, n = this.applySkew(this.A), r = e[t ? 0 : 2].subtract(n), i = e[+!!t].subtract(n), a = ki(r, t ? this.applySkew(this.AB.scalarMultiply(-1)) : this.applySkew(this.bisector.multiply(this.strokeUniformScalar).scalarMultiply(-1))) > 0, o = a ? r : i, s = a ? i : r;
		return this.isSkewed() ? e.push(...this.projectRoundWithSkew(o, s)) : e.push(...this.projectRoundNoSkew(o, s)), e;
	}
	projectPoints() {
		switch (this.options.strokeLineJoin) {
			case "miter": return this.projectMiter();
			case "round": return this.projectRound();
			default: return this.projectBevel();
		}
	}
	project() {
		return this.projectPoints().map((e) => ({
			originPoint: this.A,
			projectedPoint: e,
			angle: this.alpha,
			bisector: this.bisector
		}));
	}
}, ss = class extends is {
	constructor(e, t, n) {
		super(n), this.A = new q(e), this.T = new q(t);
	}
	calcOrthogonalProjection(e, t, n = this.strokeProjectionMagnitude) {
		let r = this.createSideVector(e, t);
		return this.scaleUnitVector(Oi(r), n);
	}
	projectButt() {
		return [this.projectOrthogonally(this.A, this.T, this.strokeProjectionMagnitude), this.projectOrthogonally(this.A, this.T, -this.strokeProjectionMagnitude)];
	}
	projectRound() {
		let e = [];
		if (!this.isSkewed() && this.A.eq(this.T)) {
			let t = new q(1, 1).scalarMultiply(this.strokeProjectionMagnitude).multiply(this.strokeUniformScalar);
			e.push(this.applySkew(this.A.add(t)), this.applySkew(this.A.subtract(t)));
		} else e.push(...new os(this.A, this.T, this.T, this.options).projectRound());
		return e;
	}
	projectSquare() {
		let e = [];
		if (this.A.eq(this.T)) {
			let t = new q(1, 1).scalarMultiply(this.strokeProjectionMagnitude).multiply(this.strokeUniformScalar);
			e.push(this.A.add(t), this.A.subtract(t));
		} else {
			let t = this.calcOrthogonalProjection(this.A, this.T, this.strokeProjectionMagnitude), n = this.scaleUnitVector(Di(this.createSideVector(this.A, this.T)), -this.strokeProjectionMagnitude), r = this.A.add(n);
			e.push(r.add(t), r.subtract(t));
		}
		return e.map((e) => this.applySkew(e));
	}
	projectPoints() {
		switch (this.options.strokeLineCap) {
			case "round": return this.projectRound();
			case "square": return this.projectSquare();
			default: return this.projectButt();
		}
	}
	project() {
		return this.projectPoints().map((e) => ({
			originPoint: this.A,
			projectedPoint: e
		}));
	}
}, cs = (e, t, n = !1) => {
	let r = [];
	if (e.length === 0) return r;
	let i = e.reduce((e, t) => (e[e.length - 1].eq(t) || e.push(new q(t)), e), [new q(e[0])]);
	if (i.length === 1) n = !0;
	else if (!n) {
		let e = i[0], t = ((e, t) => {
			for (let n = e.length - 1; n >= 0; n--) if (t(e[n], n, e)) return n;
			return -1;
		})(i, (t) => !t.eq(e));
		i.splice(t + 1);
	}
	return i.forEach((e, i, a) => {
		let o, s;
		i === 0 ? (s = a[1], o = n ? e : a[a.length - 1]) : i === a.length - 1 ? (o = a[i - 1], s = n ? e : a[0]) : (o = a[i - 1], s = a[i + 1]), n && a.length === 1 ? r.push(...new ss(e, e, t).project()) : !n || i !== 0 && i !== a.length - 1 ? r.push(...new os(e, o, s, t).project()) : r.push(...new ss(e, i === 0 ? s : o, t).project());
	}), r;
}, ls = (e) => {
	let t = {};
	return Object.keys(e).forEach((n) => {
		t[n] = {}, Object.keys(e[n]).forEach((r) => {
			t[n][r] = { ...e[n][r] };
		});
	}), t;
}, us = (e, t, n = !1) => e.fill !== t.fill || e.stroke !== t.stroke || e.strokeWidth !== t.strokeWidth || e.fontSize !== t.fontSize || e.fontFamily !== t.fontFamily || e.fontWeight !== t.fontWeight || e.fontStyle !== t.fontStyle || e.textDecorationThickness !== t.textDecorationThickness || e.textDecorationColor !== t.textDecorationColor || e.textBackgroundColor !== t.textBackgroundColor || e.deltaY !== t.deltaY || n && (e.overline !== t.overline || e.underline !== t.underline || e.linethrough !== t.linethrough), ds = (e, t) => {
	let n = t.split("\n"), r = [], i = -1, a = {};
	e = ls(e);
	for (let t = 0; t < n.length; t++) {
		let o = $r(n[t]);
		if (e[t]) for (let n = 0; n < o.length; n++) {
			i++;
			let o = e[t][n];
			o && Object.keys(o).length > 0 && (us(a, o, !0) ? r.push({
				start: i,
				end: i + 1,
				style: o
			}) : r[r.length - 1].end++), a = o || {};
		}
		else i += o.length, a = {};
	}
	return r;
}, fs = (e, t) => {
	if (!Array.isArray(e)) return ls(e);
	let n = t.split(jn), r = {}, i = -1, a = 0;
	for (let t = 0; t < n.length; t++) {
		let o = $r(n[t]);
		for (let n = 0; n < o.length; n++) i++, e[a] && e[a].start <= i && i < e[a].end && (r[t] = r[t] || {}, r[t][n] = { ...e[a].style }, i === e[a].end - 1 && a++);
	}
	return r;
}, ps = [
	"display",
	"transform",
	Gn,
	"fill-opacity",
	"fill-rule",
	"opacity",
	Kn,
	"stroke-dasharray",
	"stroke-linecap",
	"stroke-dashoffset",
	"stroke-linejoin",
	"stroke-miterlimit",
	"stroke-opacity",
	"stroke-width",
	"id",
	"paint-order",
	"vector-effect",
	"instantiated_by_use",
	"clip-path"
];
function ms(e, t) {
	let n = e.nodeName, r = e.getAttribute("class"), i = e.getAttribute("id"), a = "(?![a-zA-Z\\-]+)", o;
	if (o = RegExp("^" + n, "i"), t = t.replace(o, ""), i && t.length && (o = RegExp("#" + i + a, "i"), t = t.replace(o, "")), r && t.length) {
		let e = r.split(" ");
		for (let n = e.length; n--;) o = RegExp("\\." + e[n] + a, "i"), t = t.replace(o, "");
	}
	return t.length === 0;
}
function hs(e, t) {
	let n = !0, r = ms(e, t.pop());
	return r && t.length && (n = function(e, t) {
		let n, r = !0;
		for (; e.parentElement && e.parentElement.nodeType === 1 && t.length;) r && (n = t.pop()), r = ms(e = e.parentElement, n);
		return t.length === 0;
	}(e, t)), r && n && t.length === 0;
}
function gs(e, t = {}) {
	let n = {};
	for (let r in t) hs(e, r.split(" ")) && (n = {
		...n,
		...t[r]
	});
	return n;
}
var _s = (e) => ha[e] ?? e, vs = RegExp(`(${fa})`, "gi"), ys = `(${fa})`, bs = String.raw`(skewX)\(${ys}\)`, xs = String.raw`(skewY)\(${ys}\)`, Ss = String.raw`(rotate)\(${ys}(?: ${ys} ${ys})?\)`, Cs = String.raw`(scale)\(${ys}(?: ${ys})?\)`, ws = String.raw`(translate)\(${ys}(?: ${ys})?\)`, Ts = `(?:${String.raw`(matrix)\(${ys} ${ys} ${ys} ${ys} ${ys} ${ys}\)`}|${ws}|${Ss}|${Cs}|${bs}|${xs})`, Es = `(?:${Ts}*)`, Ds = String.raw`^\s*(?:${Es}?)\s*$`, Os = new RegExp(Ds), ks = new RegExp(Ts), As = new RegExp(Ts, "g");
function js(e) {
	let t = [];
	if (!(e = ((e) => Ui(e.replace(vs, " $1 ").replace(/,/gi, " ")))(e).replace(/\s*([()])\s*/gi, "$1")) || e && !Os.test(e)) return [...Dn];
	for (let n of e.matchAll(As)) {
		let e = ks.exec(n[0]);
		if (!e) continue;
		let r = Dn, [, i, ...a] = e.filter((e) => !!e), [o, s, c, l, u, d] = a.map((e) => parseFloat(e));
		switch (i) {
			case "translate":
				r = wr(o, s);
				break;
			case Fn:
				r = Tr({ angle: o }, {
					x: s,
					y: c
				});
				break;
			case Bn:
				r = Er(o, s);
				break;
			case Un:
				r = Or(o);
				break;
			case Wn:
				r = kr(o);
				break;
			case "matrix": r = [
				o,
				s,
				c,
				l,
				u,
				d
			];
		}
		t.push(r);
	}
	return yr(t);
}
function Ms(e, t, n, r) {
	let i = Array.isArray(t), a, o = t;
	if (e !== "fill" && e !== "stroke" || t !== "none") {
		if (e === "strokeUniform") return t === "non-scaling-stroke";
		if (e === "strokeDashArray") o = t === "none" ? null : t.replace(/,/g, " ").split(/\s+/).map(parseFloat);
		else if (e === "transformMatrix") o = n && n.transformMatrix ? Y(n.transformMatrix, js(t)) : js(t);
		else if (e === "visible") o = t !== "none" && t !== "hidden", n && !1 === n.visible && (o = !1);
		else if (e === "opacity") o = parseFloat(t), n && n.opacity !== void 0 && (o *= n.opacity);
		else if (e === "textAnchor") o = t === "start" ? G : t === "end" ? kn : W;
		else if (e === "charSpacing" || e === "textDecorationThickness") a = Qi(t, r) / r * 1e3;
		else if (e === "paintFirst") {
			let e = t.indexOf(Gn), n = t.indexOf(Kn);
			o = Gn, (e > -1 && n > -1 && n < e || e === -1 && n > -1) && (o = Kn);
		} else {
			if (e === "href" || e === "xlink:href" || e === "font" || e === "id") return t;
			if (e === "imageSmoothing") return t === "optimizeQuality";
			a = i ? t.map(Qi) : Qi(t, r);
		}
	} else o = "";
	return !i && isNaN(a) ? o : a;
}
function Ns(e, t) {
	e.replace(/;\s*$/, "").split(";").forEach((e) => {
		if (!e) return;
		let [n, r] = e.split(":");
		t[n.trim().toLowerCase()] = r.trim();
	});
}
function Ps(e) {
	let t = {}, n = e.getAttribute("style");
	return n && (typeof n == "string" ? Ns(n, t) : function(e, t) {
		Object.entries(e).forEach(([e, n]) => {
			n !== void 0 && (t[e.toLowerCase()] = n);
		});
	}(n, t)), t;
}
var Fs = {
	stroke: "strokeOpacity",
	fill: "fillOpacity"
};
function Is(e, t, n) {
	if (!e) return {};
	let r, i = {}, a = 16;
	e.parentNode && va.test(e.parentNode.nodeName) && (i = Is(e.parentElement, t, n), i.fontSize && (r = a = Qi(i.fontSize)));
	let o = {
		...t.reduce((t, n) => {
			let r = e.getAttribute(n);
			return r && (t[n] = r), t;
		}, {}),
		...gs(e, n),
		...Ps(e)
	};
	o["clip-path"] && e.setAttribute(_a, o[_a]), o["font-size"] && (r = Qi(o[ga], a), o[ga] = `${r}`);
	let s = {};
	for (let e in o) {
		let t = _s(e);
		s[t] = Ms(t, o[e], i, r);
	}
	s && s.font && function(e, t) {
		let n = e.match(ma);
		if (!n) return;
		let r = n[1], i = n[3], a = n[4], o = n[5], s = n[6];
		r && (t.fontStyle = r), i && (t.fontWeight = isNaN(parseFloat(i)) ? i : parseFloat(i)), a && (t.fontSize = Qi(a)), s && (t.fontFamily = s), o && (t.lineHeight = o === "normal" ? 1 : o);
	}(s.font, s);
	let c = {
		...i,
		...s
	};
	return va.test(e.nodeName) ? c : function(e) {
		let t = ns.getDefaults();
		return Object.entries(Fs).forEach(([n, r]) => {
			if (e[r] === void 0 || e[n] === "") return;
			if (e[n] === void 0) {
				if (!t[n]) return;
				e[n] = t[n];
			}
			if (e[n].indexOf("url(") === 0) return;
			let i = new Xi(e[n]);
			e[n] = i.setAlpha(X(i.getAlpha() * e[r], 2)).toRgba();
		}), e;
	}(c);
}
var Ls = ["rx", "ry"], Rs = class e extends ns {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t) {
		super(), Object.assign(this, e.ownDefaults), this.setOptions(t), this._initRxRy();
	}
	_initRxRy() {
		let { rx: e, ry: t } = this;
		e && !t ? this.ry = e : t && !e && (this.rx = t);
	}
	_render(e) {
		let { width: t, height: n } = this, r = -t / 2, i = -n / 2, a = this.rx ? Math.min(this.rx, t / 2) : 0, o = this.ry ? Math.min(this.ry, n / 2) : 0, s = a !== 0 || o !== 0;
		e.beginPath(), e.moveTo(r + a, i), e.lineTo(r + t - a, i), s && e.bezierCurveTo(r + t - .4477152502 * a, i, r + t, i + .4477152502 * o, r + t, i + o), e.lineTo(r + t, i + n - o), s && e.bezierCurveTo(r + t, i + n - .4477152502 * o, r + t - .4477152502 * a, i + n, r + t - a, i + n), e.lineTo(r + a, i + n), s && e.bezierCurveTo(r + .4477152502 * a, i + n, r, i + n - .4477152502 * o, r, i + n - o), e.lineTo(r, i + o), s && e.bezierCurveTo(r, i + .4477152502 * o, r + .4477152502 * a, i, r + a, i), e.closePath(), this._renderPaintInOrder(e);
	}
	toObject(e = []) {
		return super.toObject([...Ls, ...e]);
	}
	_toSVG() {
		let { width: e, height: t, rx: n, ry: r } = this;
		return [
			"<rect ",
			"COMMON_PARTS",
			`x="${-e / 2}" y="${-t / 2}" rx="${Z(n)}" ry="${Z(r)}" width="${Z(e)}" height="${Z(t)}" />\n`
		];
	}
	static async fromElement(e, t, n) {
		let { left: r = 0, top: i = 0, width: a = 0, height: o = 0, visible: s = !0, ...c } = Is(e, this.ATTRIBUTE_NAMES, n);
		return new this({
			...t,
			...c,
			left: r,
			top: i,
			width: a,
			height: o,
			visible: !!(s && a && o)
		});
	}
};
H(Rs, "type", "Rect"), H(Rs, "cacheProperties", [...wa, ...Ls]), H(Rs, "ownDefaults", {
	rx: 0,
	ry: 0
}), H(Rs, "ATTRIBUTE_NAMES", [
	...ps,
	"x",
	"y",
	"rx",
	"ry",
	"width",
	"height"
]), K.setClass(Rs), K.setSVGClass(Rs);
var zs = "initialization", Bs = "added", Vs = (e, t) => {
	let { strokeUniform: n, strokeWidth: r, width: i, height: a, group: o } = t, s = o && o !== e ? mi(o.calcTransformMatrix(), e.calcTransformMatrix()) : null, c = s ? t.getRelativeCenterPoint().transform(s) : t.getRelativeCenterPoint(), l = !t.isStrokeAccountedForInDimensions(), u = n && l ? gi(new q(r, r), void 0, e.calcTransformMatrix()) : tr, d = !n && l ? r : 0, f = pi(i + d, a + d, yr([s, t.calcOwnMatrix()], !0)).add(u).scalarDivide(2);
	return [c.subtract(f), c.add(f)];
}, Hs = class {
	calcLayoutResult(e, t) {
		if (this.shouldPerformLayout(e)) return this.calcBoundingBox(t, e);
	}
	shouldPerformLayout({ type: e, prevStrategy: t, strategy: n }) {
		return e === "initialization" || e === "imperative" || !!t && n !== t;
	}
	shouldLayoutClipPath({ type: e, target: { clipPath: t } }) {
		return e !== "initialization" && t && !t.absolutePositioned;
	}
	getInitialSize(e, t) {
		return t.size;
	}
	calcBoundingBox(e, t) {
		let { type: n, target: r } = t;
		if (n === "imperative" && t.overrides) return t.overrides;
		if (e.length === 0) return;
		let { left: i, top: a, width: o, height: s } = si(e.map((e) => Vs(r, e)).reduce((e, t) => e.concat(t), [])), c = new q(o, s), l = new q(i, a).add(c.scalarDivide(2));
		if (n === "initialization") {
			let e = this.getInitialSize(t, {
				size: c,
				center: l
			});
			return {
				center: l,
				relativeCorrection: new q(0, 0),
				size: e
			};
		}
		return {
			center: l.transform(r.calcOwnMatrix()),
			size: c
		};
	}
};
H(Hs, "type", "strategy");
var Us = class extends Hs {
	shouldPerformLayout(e) {
		return !0;
	}
};
H(Us, "type", "fit-content"), K.setClass(Us);
var Ws = "layoutManager", Gs = class {
	constructor(e = new Us()) {
		H(this, "strategy", void 0), this.strategy = e, this._subscriptions = /* @__PURE__ */ new Map();
	}
	performLayout(e) {
		let t = {
			bubbles: !0,
			strategy: this.strategy,
			...e,
			prevStrategy: this._prevLayoutStrategy,
			stopPropagation() {
				this.bubbles = !1;
			}
		};
		this.onBeforeLayout(t);
		let n = this.getLayoutResult(t);
		n && this.commitLayout(t, n), this.onAfterLayout(t, n), this._prevLayoutStrategy = t.strategy;
	}
	attachHandlers(e, t) {
		let { target: n } = t;
		return [
			qn,
			Mn,
			Ln,
			Pn,
			Nn,
			In,
			zn,
			Rn,
			"modifyPath"
		].map((t) => e.on(t, (e) => this.performLayout(t === "modified" ? {
			type: "object_modified",
			trigger: t,
			e,
			target: n
		} : {
			type: "object_modifying",
			trigger: t,
			e,
			target: n
		})));
	}
	subscribe(e, t) {
		this.unsubscribe(e, t);
		let n = this.attachHandlers(e, t);
		this._subscriptions.set(e, n);
	}
	unsubscribe(e, t) {
		(this._subscriptions.get(e) || []).forEach((e) => e()), this._subscriptions.delete(e);
	}
	unsubscribeTargets(e) {
		e.targets.forEach((t) => this.unsubscribe(t, e));
	}
	subscribeTargets(e) {
		e.targets.forEach((t) => this.subscribe(t, e));
	}
	onBeforeLayout(e) {
		let { target: t, type: n } = e, { canvas: r } = t;
		if (n === "initialization" || n === "added" ? this.subscribeTargets(e) : n === "removed" && this.unsubscribeTargets(e), t.fire("layout:before", { context: e }), r && r.fire("object:layout:before", {
			target: t,
			context: e
		}), n === "imperative" && e.deep) {
			let { strategy: n, ...r } = e;
			t.forEachObject((e) => e.layoutManager && e.layoutManager.performLayout({
				...r,
				bubbles: !1,
				target: e
			}));
		}
	}
	getLayoutResult(e) {
		let { target: t, strategy: n, type: r } = e, i = n.calcLayoutResult(e, t.getObjects());
		if (!i) return;
		let a = r === "initialization" ? new q() : t.getRelativeCenterPoint(), { center: o, correction: s = new q(), relativeCorrection: c = new q() } = i;
		return {
			result: i,
			prevCenter: a,
			nextCenter: o,
			offset: a.subtract(o).add(s).transform(r === "initialization" ? Dn : vr(t.calcOwnMatrix()), !0).add(c)
		};
	}
	commitLayout(e, t) {
		let { target: n } = e, { result: { size: r }, nextCenter: i } = t;
		n.set({
			width: r.x,
			height: r.y
		}), this.layoutObjects(e, t), e.type === "initialization" ? n.set({
			left: e.x ?? i.x + r.x * yi(n.originX),
			top: e.y ?? i.y + r.y * yi(n.originY)
		}) : (n.setPositionByOrigin(i, W, W), n.setCoords(), n.set("dirty", !0));
	}
	layoutObjects(e, t) {
		let { target: n } = e;
		n.forEachObject((r) => {
			r.group === n && this.layoutObject(e, t, r);
		}), e.strategy.shouldLayoutClipPath(e) && this.layoutObject(e, t, n.clipPath);
	}
	layoutObject(e, { offset: t }, n) {
		n.set({
			left: n.left + t.x,
			top: n.top + t.y
		});
	}
	onAfterLayout(e, t) {
		let { target: n, strategy: r, bubbles: i, prevStrategy: a, ...o } = e, { canvas: s } = n;
		n.fire("layout:after", {
			context: e,
			result: t
		}), s && s.fire("object:layout:after", {
			context: e,
			result: t,
			target: n
		});
		let c = n.parent;
		i && c != null && c.layoutManager && ((o.path ||= []).push(n), c.layoutManager.performLayout({
			...o,
			target: c
		})), n.set("dirty", !0);
	}
	dispose() {
		let { _subscriptions: e } = this;
		e.forEach((e) => e.forEach((e) => e())), e.clear();
	}
	toObject() {
		return {
			type: Ws,
			strategy: this.strategy.constructor.type
		};
	}
	toJSON() {
		return this.toObject();
	}
};
K.setClass(Gs, Ws);
var Ks = class extends Gs {
	performLayout() {}
}, qs = class e extends rr(ns) {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t = [], n = {}) {
		super(), H(this, "_activeObjects", []), H(this, "__objectSelectionTracker", void 0), H(this, "__objectSelectionDisposer", void 0), Object.assign(this, e.ownDefaults), this.setOptions(n), this.groupInit(t, n);
	}
	groupInit(e, t) {
		this._objects = [...e], this.__objectSelectionTracker = this.__objectSelectionMonitor.bind(this, !0), this.__objectSelectionDisposer = this.__objectSelectionMonitor.bind(this, !1), this.forEachObject((e) => {
			this.enterGroup(e, !1);
		}), this.layoutManager = t.layoutManager ?? new Gs(), this.layoutManager.performLayout({
			type: zs,
			target: this,
			targets: [...e],
			x: t.left,
			y: t.top
		});
	}
	canEnterGroup(e) {
		return e === this || this.isDescendantOf(e) ? (ln("error", "Group: circular object trees are not supported, this call has no effect"), !1) : this._objects.indexOf(e) === -1 || (ln("error", "Group: duplicate objects are not supported inside group, this call has no effect"), !1);
	}
	_filterObjectsBeforeEnteringGroup(e) {
		return e.filter((e, t, n) => this.canEnterGroup(e) && n.indexOf(e) === t);
	}
	add(...e) {
		let t = this._filterObjectsBeforeEnteringGroup(e), n = super.add(...t);
		return this._onAfterObjectsChange(Bs, t), n;
	}
	insertAt(e, ...t) {
		let n = this._filterObjectsBeforeEnteringGroup(t), r = super.insertAt(e, ...n);
		return this._onAfterObjectsChange(Bs, n), r;
	}
	remove(...e) {
		let t = super.remove(...e);
		return this._onAfterObjectsChange("removed", t), t;
	}
	_onObjectAdded(e) {
		this.enterGroup(e, !0), this.fire("object:added", { target: e }), e.fire("added", { target: this });
	}
	_onObjectRemoved(e, t) {
		this.exitGroup(e, t), this.fire("object:removed", { target: e }), e.fire("removed", { target: this });
	}
	_onAfterObjectsChange(e, t) {
		this.layoutManager.performLayout({
			type: e,
			targets: t,
			target: this
		});
	}
	_onStackOrderChanged() {
		this._set("dirty", !0);
	}
	_set(e, t) {
		let n = this[e];
		return super._set(e, t), e === "canvas" && n !== t && (this._objects || []).forEach((n) => {
			n._set(e, t);
		}), this;
	}
	_shouldSetNestedCoords() {
		return this.subTargetCheck;
	}
	removeAll() {
		return this._activeObjects = [], this.remove(...this._objects);
	}
	__objectSelectionMonitor(e, { target: t }) {
		let n = this._activeObjects;
		if (e) n.push(t), this._set("dirty", !0);
		else if (n.length > 0) {
			let e = n.indexOf(t);
			e > -1 && (n.splice(e, 1), this._set("dirty", !0));
		}
	}
	_watchObject(e, t) {
		e && this._watchObject(!1, t), e ? (t.on("selected", this.__objectSelectionTracker), t.on("deselected", this.__objectSelectionDisposer)) : (t.off("selected", this.__objectSelectionTracker), t.off("deselected", this.__objectSelectionDisposer));
	}
	enterGroup(e, t) {
		e.group && e.group.remove(e), e._set("parent", this), this._enterGroup(e, t);
	}
	_enterGroup(e, t) {
		t && ui(e, Y(vr(this.calcTransformMatrix()), e.calcTransformMatrix())), this._shouldSetNestedCoords() && e.setCoords(), e._set("group", this), e._set("canvas", this.canvas), this._watchObject(!0, e);
		let n = this.canvas && this.canvas.getActiveObject && this.canvas.getActiveObject();
		n && (n === e || e.isDescendantOf(n)) && this._activeObjects.push(e);
	}
	exitGroup(e, t) {
		this._exitGroup(e, t), e._set("parent", void 0), e._set("canvas", void 0);
	}
	_exitGroup(e, t) {
		e._set("group", void 0), t || (ui(e, Y(this.calcTransformMatrix(), e.calcTransformMatrix())), e.setCoords()), this._watchObject(!1, e);
		let n = this._activeObjects.length > 0 ? this._activeObjects.indexOf(e) : -1;
		n > -1 && this._activeObjects.splice(n, 1);
	}
	shouldCache() {
		let e = ns.prototype.shouldCache.call(this);
		if (e) {
			for (let e = 0; e < this._objects.length; e++) if (this._objects[e].willDrawShadow()) return this.ownCaching = !1, !1;
		}
		return e;
	}
	willDrawShadow() {
		if (super.willDrawShadow()) return !0;
		for (let e = 0; e < this._objects.length; e++) if (this._objects[e].willDrawShadow()) return !0;
		return !1;
	}
	isOnACache() {
		return this.ownCaching || !!this.parent && this.parent.isOnACache();
	}
	drawObject(e, t, n) {
		this._renderBackground(e);
		for (let t = 0; t < this._objects.length; t++) {
			var r;
			let n = this._objects[t];
			(r = this.canvas) != null && r.preserveObjectStacking && n.group !== this ? (e.save(), e.transform(...vr(this.calcTransformMatrix())), n.render(e), e.restore()) : n.group === this && n.render(e);
		}
		this._drawClipPath(e, this.clipPath, n);
	}
	setCoords() {
		super.setCoords(), this._shouldSetNestedCoords() && this.forEachObject((e) => e.setCoords());
	}
	triggerLayout(e = {}) {
		this.layoutManager.performLayout({
			target: this,
			type: "imperative",
			...e
		});
	}
	render(e) {
		this._transformDone = !0, super.render(e), this._transformDone = !1;
	}
	__serializeObjects(e, t) {
		let n = this.includeDefaultValues;
		return this._objects.filter(function(e) {
			return !e.excludeFromExport;
		}).map(function(r) {
			let i = r.includeDefaultValues;
			r.includeDefaultValues = n;
			let a = r[e || "toObject"](t);
			return r.includeDefaultValues = i, a;
		});
	}
	toObject(e = []) {
		let t = this.layoutManager.toObject();
		return {
			...super.toObject([
				"subTargetCheck",
				"interactive",
				...e
			]),
			...t.strategy !== "fit-content" || this.includeDefaultValues ? { layoutManager: t } : {},
			objects: this.__serializeObjects("toObject", e)
		};
	}
	toString() {
		return `#<Group: (${this.complexity()})>`;
	}
	dispose() {
		this.layoutManager.unsubscribeTargets({
			targets: this.getObjects(),
			target: this
		}), this._activeObjects = [], this.forEachObject((e) => {
			this._watchObject(!1, e), e.dispose();
		}), super.dispose();
	}
	_createSVGBgRect(e) {
		if (!this.backgroundColor) return "";
		let t = Rs.prototype._toSVG.call(this), n = t.indexOf("COMMON_PARTS");
		t[n] = "for=\"group\" ";
		let r = t.join("");
		return e ? e(r) : r;
	}
	_toSVG(e) {
		let t = [
			"<g ",
			"COMMON_PARTS",
			" >\n"
		], n = this._createSVGBgRect(e);
		n && t.push("		", n);
		for (let n = 0; n < this._objects.length; n++) t.push("		", this._objects[n].toSVG(e));
		return t.push("</g>\n"), t;
	}
	getSvgStyles() {
		let e = this.opacity !== void 0 && this.opacity !== 1 ? `opacity: ${Z(this.opacity)};` : "", t = this.visible ? "" : " visibility: hidden;";
		return [
			e,
			this.getSvgFilter(),
			t
		].join("");
	}
	toClipPathSVG(e) {
		let t = [], n = this._createSVGBgRect(e);
		n && t.push("	", n);
		for (let n = 0; n < this._objects.length; n++) t.push("	", this._objects[n].toClipPathSVG(e));
		return this._createBaseClipPathSVGMarkup(t, { reviver: e });
	}
	static fromObject({ type: e, objects: t = [], layoutManager: n, ...r }, i) {
		return Promise.all([Nr(t, i), Pr(r, i)]).then(([e, t]) => {
			let i = new this(e, {
				...r,
				...t,
				layoutManager: new Ks()
			});
			return i.layoutManager = n ? new (K.getClass(n.type))(new (K.getClass(n.strategy))()) : new Gs(), i.layoutManager.subscribeTargets({
				type: zs,
				target: i,
				targets: i.getObjects()
			}), i.setCoords(), i;
		});
	}
};
H(qs, "type", "Group"), H(qs, "ownDefaults", {
	strokeWidth: 0,
	subTargetCheck: !1,
	interactive: !1
}), K.setClass(qs);
var Js = (e, t) => e && e.length === 1 ? e[0] : new qs(e, t), Ys = (e, t) => Math.min(t.width / e.width, t.height / e.height), Xs = (e, t) => Math.max(t.width / e.width, t.height / e.height), Zs = "\\s*,?\\s*", Qs = `${Zs}(${fa})`, $s = `${Qs}${Qs}${Qs}${Zs}([01])${Zs}([01])${Qs}${Qs}`, ec = {
	m: "l",
	M: "L"
}, tc = (e, t, n, r, i, a, o, s, c, l, u) => {
	let d = $n(e), f = er(e), p = $n(t), m = er(t), h = n * i * p - r * a * m + o, g = r * i * p + n * a * m + s;
	return [
		"C",
		l + c * (-n * i * f - r * a * d),
		u + c * (-r * i * f + n * a * d),
		h + c * (n * i * m + r * a * p),
		g + c * (r * i * m - n * a * p),
		h,
		g
	];
}, nc = (e, t, n, r) => {
	let i = Math.atan2(t, e), a = Math.atan2(r, n);
	return a >= i ? a - i : 2 * Math.PI - (i - a);
};
function rc(e, t, n, r, i, a, o, s) {
	let c;
	if (U.cachesBoundsOfCurve && (c = [...arguments].join(), bn.boundsOfCurveCache[c])) return bn.boundsOfCurveCache[c];
	let l = Math.sqrt, u = Math.abs, d = [], f = [[0, 0], [0, 0]], p = 6 * e - 12 * n + 6 * i, m = -3 * e + 9 * n - 9 * i + 3 * o, h = 3 * n - 3 * e;
	for (let e = 0; e < 2; ++e) {
		if (e > 0 && (p = 6 * t - 12 * r + 6 * a, m = -3 * t + 9 * r - 9 * a + 3 * s, h = 3 * r - 3 * t), u(m) < 1e-12) {
			if (u(p) < 1e-12) continue;
			let e = -h / p;
			0 < e && e < 1 && d.push(e);
			continue;
		}
		let n = p * p - 4 * h * m;
		if (n < 0) continue;
		let i = l(n), o = (-p + i) / (2 * m);
		0 < o && o < 1 && d.push(o);
		let c = (-p - i) / (2 * m);
		0 < c && c < 1 && d.push(c);
	}
	let g = d.length, _ = g, v = sc(e, t, n, r, i, a, o, s);
	for (; g--;) {
		let { x: e, y: t } = v(d[g]);
		f[0][g] = e, f[1][g] = t;
	}
	f[0][_] = e, f[1][_] = t, f[0][_ + 1] = o, f[1][_ + 1] = s;
	let y = [new q(Math.min(...f[0]), Math.min(...f[1])), new q(Math.max(...f[0]), Math.max(...f[1]))];
	return U.cachesBoundsOfCurve && (bn.boundsOfCurveCache[c] = y), y;
}
var ic = (e, t, [n, r, i, a, o, s, c, l]) => {
	let u = ((e, t, n, r, i, a, o) => {
		if (n === 0 || r === 0) return [];
		let s = 0, c = 0, l = 0, u = Math.PI, d = o * En, f = er(d), p = $n(d), m = .5 * (-p * e - f * t), h = .5 * (-p * t + f * e), g = n ** 2, _ = r ** 2, v = h ** 2, y = m ** 2, b = g * _ - g * v - _ * y, x = Math.abs(n), S = Math.abs(r);
		if (b < 0) {
			let e = Math.sqrt(1 - b / (g * _));
			x *= e, S *= e;
		} else l = (i === a ? -1 : 1) * Math.sqrt(b / (g * v + _ * y));
		let C = l * x * h / S, w = -l * S * m / x, T = p * C - f * w + .5 * e, E = f * C + p * w + .5 * t, D = nc(1, 0, (m - C) / x, (h - w) / S), O = nc((m - C) / x, (h - w) / S, (-m - C) / x, (-h - w) / S);
		a === 0 && O > 0 ? O -= 2 * u : a === 1 && O < 0 && (O += 2 * u);
		let ee = Math.ceil(Math.abs(O / u * 2)), te = [], ne = O / ee, re = 8 / 3 * Math.sin(ne / 4) * Math.sin(ne / 4) / Math.sin(ne / 2), k = D + ne;
		for (let e = 0; e < ee; e++) te[e] = tc(D, k, p, f, x, S, T, E, re, s, c), s = te[e][5], c = te[e][6], D = k, k += ne;
		return te;
	})(c - e, l - t, r, i, o, s, a);
	for (let n = 0, r = u.length; n < r; n++) u[n][1] += e, u[n][2] += t, u[n][3] += e, u[n][4] += t, u[n][5] += e, u[n][6] += t;
	return u;
}, ac = (e) => {
	let t = 0, n = 0, r = 0, i = 0, a = [], o, s = 0, c = 0;
	for (let l of e) {
		let e = [...l], u;
		switch (e[0]) {
			case "l": e[1] += t, e[2] += n;
			case "L":
				t = e[1], n = e[2], u = [
					"L",
					t,
					n
				];
				break;
			case "h": e[1] += t;
			case "H":
				t = e[1], u = [
					"L",
					t,
					n
				];
				break;
			case "v": e[1] += n;
			case "V":
				n = e[1], u = [
					"L",
					t,
					n
				];
				break;
			case "m": e[1] += t, e[2] += n;
			case "M":
				t = e[1], n = e[2], r = e[1], i = e[2], u = [
					"M",
					t,
					n
				];
				break;
			case "c": e[1] += t, e[2] += n, e[3] += t, e[4] += n, e[5] += t, e[6] += n;
			case "C":
				s = e[3], c = e[4], t = e[5], n = e[6], u = [
					"C",
					e[1],
					e[2],
					s,
					c,
					t,
					n
				];
				break;
			case "s": e[1] += t, e[2] += n, e[3] += t, e[4] += n;
			case "S":
				o === "C" ? (s = 2 * t - s, c = 2 * n - c) : (s = t, c = n), t = e[3], n = e[4], u = [
					"C",
					s,
					c,
					e[1],
					e[2],
					t,
					n
				], s = u[3], c = u[4];
				break;
			case "q": e[1] += t, e[2] += n, e[3] += t, e[4] += n;
			case "Q":
				s = e[1], c = e[2], t = e[3], n = e[4], u = [
					"Q",
					s,
					c,
					t,
					n
				];
				break;
			case "t": e[1] += t, e[2] += n;
			case "T":
				o === "Q" ? (s = 2 * t - s, c = 2 * n - c) : (s = t, c = n), t = e[1], n = e[2], u = [
					"Q",
					s,
					c,
					t,
					n
				];
				break;
			case "a": e[6] += t, e[7] += n;
			case "A":
				ic(t, n, e).forEach((e) => a.push(e)), t = e[6], n = e[7];
				break;
			case "z":
			case "Z": t = r, n = i, u = ["Z"];
		}
		u ? (a.push(u), o = u[0]) : o = "";
	}
	return a;
}, oc = (e, t, n, r) => Math.sqrt((n - e) ** 2 + (r - t) ** 2), sc = (e, t, n, r, i, a, o, s) => (c) => {
	let l = c ** 3, u = ((e) => 3 * e ** 2 * (1 - e))(c), d = ((e) => 3 * e * (1 - e) ** 2)(c), f = ((e) => (1 - e) ** 3)(c);
	return new q(o * l + i * u + n * d + e * f, s * l + a * u + r * d + t * f);
}, cc = (e) => e ** 2, lc = (e) => 2 * e * (1 - e), uc = (e) => (1 - e) ** 2, dc = (e, t, n, r, i, a, o, s) => (c) => {
	let l = cc(c), u = lc(c), d = uc(c), f = 3 * (d * (n - e) + u * (i - n) + l * (o - i)), p = 3 * (d * (r - t) + u * (a - r) + l * (s - a));
	return Math.atan2(p, f);
}, fc = (e, t, n, r, i, a) => (o) => {
	let s = cc(o), c = lc(o), l = uc(o);
	return new q(i * s + n * c + e * l, a * s + r * c + t * l);
}, pc = (e, t, n, r, i, a) => (o) => {
	let s = 1 - o, c = 2 * (s * (n - e) + o * (i - n)), l = 2 * (s * (r - t) + o * (a - r));
	return Math.atan2(l, c);
}, mc = (e, t, n) => {
	let r = new q(t, n), i = 0;
	for (let t = 1; t <= 100; t += 1) {
		let n = e(t / 100);
		i += oc(r.x, r.y, n.x, n.y), r = n;
	}
	return i;
}, hc = (e, t) => {
	let n, r = 0, i = 0, a = {
		x: e.x,
		y: e.y
	}, o = { ...a }, s = .01, c = 0, l = e.iterator, u = e.angleFinder;
	for (; i < t && s > 1e-4;) o = l(r), c = r, n = oc(a.x, a.y, o.x, o.y), n + i > t ? (r -= s, s /= 2) : (a = o, r += s, i += n);
	return {
		...o,
		angle: u(c)
	};
}, gc = (e) => {
	let t, n, r = 0, i = 0, a = 0, o = 0, s = 0, c = [];
	for (let l of e) {
		let e = {
			x: i,
			y: a,
			command: l[0],
			length: 0
		};
		switch (l[0]) {
			case "M":
				n = e, n.x = o = i = l[1], n.y = s = a = l[2];
				break;
			case "L":
				n = e, n.length = oc(i, a, l[1], l[2]), i = l[1], a = l[2];
				break;
			case "C":
				t = sc(i, a, l[1], l[2], l[3], l[4], l[5], l[6]), n = e, n.iterator = t, n.angleFinder = dc(i, a, l[1], l[2], l[3], l[4], l[5], l[6]), n.length = mc(t, i, a), i = l[5], a = l[6];
				break;
			case "Q":
				t = fc(i, a, l[1], l[2], l[3], l[4]), n = e, n.iterator = t, n.angleFinder = pc(i, a, l[1], l[2], l[3], l[4]), n.length = mc(t, i, a), i = l[3], a = l[4];
				break;
			case "Z": n = e, n.destX = o, n.destY = s, n.length = oc(i, a, o, s), i = o, a = s;
		}
		r += n.length, c.push(n);
	}
	return c.push({
		length: r,
		x: i,
		y: a
	}), c;
}, _c = (e, t, n = gc(e)) => {
	let r = 0;
	for (; t - n[r].length > 0 && r < n.length - 2;) t -= n[r].length, r++;
	let i = n[r], a = t / i.length, o = e[r];
	switch (i.command) {
		case "M": return {
			x: i.x,
			y: i.y,
			angle: 0
		};
		case "Z": return {
			...new q(i.x, i.y).lerp(new q(i.destX, i.destY), a),
			angle: Math.atan2(i.destY - i.y, i.destX - i.x)
		};
		case "L": return {
			...new q(i.x, i.y).lerp(new q(o[1], o[2]), a),
			angle: Math.atan2(o[2] - i.y, o[1] - i.x)
		};
		case "C":
		case "Q": return hc(i, t);
	}
}, vc = RegExp("[mzlhvcsqta][^mzlhvcsqta]*", "gi"), yc = new RegExp($s, "g"), bc = new RegExp(fa, "gi"), xc = {
	m: 2,
	l: 2,
	h: 1,
	v: 1,
	c: 6,
	s: 4,
	q: 4,
	t: 2,
	a: 7
}, Sc = (e) => {
	let t = [], n = e.match(vc) ?? [];
	for (let e of n) {
		let n = e[0];
		if (n === "z" || n === "Z") {
			t.push([n]);
			continue;
		}
		let r = xc[n.toLowerCase()], i = [];
		if (n === "a" || n === "A") {
			let t;
			for (yc.lastIndex = 0; t = yc.exec(e);) i.push(...t.slice(1));
		} else i = e.match(bc) || [];
		for (let e = 0; e < i.length; e += r) {
			let a = Array(r), o = ec[n];
			a[0] = e > 0 && o ? o : n;
			for (let t = 0; t < r; t++) a[t + 1] = parseFloat(i[e + t]);
			t.push(a);
		}
	}
	return t;
}, Cc = (e, t = 0) => {
	let n = new q(e[0]), r = new q(e[1]), i = 1, a = 0, o = [], s = e.length, c = s > 2, l;
	for (c && (i = e[2].x < r.x ? -1 : e[2].x === r.x ? 0 : 1, a = e[2].y < r.y ? -1 : e[2].y === r.y ? 0 : 1), o.push([
		"M",
		n.x - i * t,
		n.y - a * t
	]), l = 1; l < s; l++) {
		if (!n.eq(r)) {
			let e = n.midPointFrom(r);
			o.push([
				"Q",
				n.x,
				n.y,
				e.x,
				e.y
			]);
		}
		n = e[l], l + 1 < e.length && (r = e[l + 1]);
	}
	return c && (i = n.x > e[l - 2].x ? 1 : n.x === e[l - 2].x ? 0 : -1, a = n.y > e[l - 2].y ? 1 : n.y === e[l - 2].y ? 0 : -1), o.push([
		"L",
		n.x + i * t,
		n.y + a * t
	]), o;
}, wc = (e, t, n) => (n && (t = Y(t, [
	1,
	0,
	0,
	1,
	-n.x,
	-n.y
])), e.map((e) => {
	let n = [...e];
	for (let r = 1; r < e.length - 1; r += 2) {
		let { x: i, y: a } = _r({
			x: e[r],
			y: e[r + 1]
		}, t);
		n[r] = i, n[r + 1] = a;
	}
	return n;
})), Tc = (e, t) => {
	let n = 2 * Math.PI / e, r = -Cn;
	e % 2 == 0 && (r += n / 2);
	let i = Array(e + 1);
	for (let a = 0; a < e; a++) {
		let e = a * n + r, { x: o, y: s } = new q($n(e), er(e)).scalarMultiply(t);
		i[a] = [
			a === 0 ? "M" : "L",
			o,
			s
		];
	}
	return i[e] = ["Z"], i;
}, Ec = (e, t) => e.map((e) => e.map((e, n) => n === 0 || t === void 0 ? e : X(e, t)).join(" ")).join(" "), Dc = (e, t) => {
	let n = e, r = t;
	n.inverted && !r.inverted && (n = t, r = e), _i(r, r.group?.calcTransformMatrix(), n.calcTransformMatrix());
	let i = n.inverted && r.inverted;
	return i && (n.inverted = r.inverted = !1), new qs([n], {
		clipPath: r,
		inverted: i
	});
}, Oc = (e, t) => Math.floor(Math.random() * (t - e + 1)) + e, kc = (e, t) => {
	let n = e._findCenterFromElement();
	e.transformMatrix && (((e) => {
		if (e.transformMatrix) {
			let { scaleX: t, scaleY: n, angle: r, skewX: i } = Cr(e.transformMatrix);
			e.flipX = !1, e.flipY = !1, e.set(Vn, t), e.set(Hn, n), e.angle = r, e.skewX = i, e.skewY = 0;
		}
	})(e), n = n.transform(e.transformMatrix)), delete e.transformMatrix, t && (e.scaleX *= t.scaleX, e.scaleY *= t.scaleY, e.cropX = t.cropX, e.cropY = t.cropY, n.x += t.offsetLeft, n.y += t.offsetTop, e.width = t.width, e.height = t.height), e.setPositionByOrigin(n, W, W);
};
an({
	addTransformToObject: () => li,
	animate: () => mo,
	animateColor: () => ho,
	applyTransformToObject: () => ui,
	calcAngleBetweenVectors: () => Ti,
	calcDimensionsMatrix: () => Ar,
	calcPlaneChangeMatrix: () => mi,
	calcVectorRotation: () => Ei,
	cancelAnimFrame: () => or,
	capValue: () => Sa,
	composeMatrix: () => jr,
	copyCanvasElement: () => dr,
	cos: () => $n,
	createCanvasElement: () => lr,
	createImage: () => ur,
	createRotateMatrix: () => Tr,
	createScaleMatrix: () => Er,
	createSkewXMatrix: () => Or,
	createSkewYMatrix: () => kr,
	createTranslateMatrix: () => wr,
	createVector: () => Ci,
	crossProduct: () => ki,
	degreesToRadians: () => J,
	dotProduct: () => Ai,
	ease: () => Ea,
	enlivenObjectEnlivables: () => Pr,
	enlivenObjects: () => Nr,
	findScaleToCover: () => Xs,
	findScaleToFit: () => Ys,
	getBoundsOfCurve: () => rc,
	getOrthonormalVector: () => Oi,
	getPathSegmentsInfo: () => gc,
	getPointOnPath: () => _c,
	getPointer: () => ii,
	getRandomInt: () => Oc,
	getRegularPolygonPath: () => Tc,
	getSmoothPathFromPoints: () => Cc,
	getSvgAttributes: () => Zi,
	getUnitVector: () => Di,
	groupSVGElements: () => Js,
	hasStyleChanged: () => us,
	invertTransform: () => vr,
	isBetweenVectors: () => ji,
	isIdentityMatrix: () => gr,
	isTouchEvent: () => ai,
	isTransparent: () => rs,
	joinPath: () => Ec,
	loadImage: () => Mr,
	magnitude: () => wi,
	makeBoundingBoxFromPoints: () => si,
	makePathSimpler: () => ac,
	matrixToSVG: () => Lr,
	mergeClipPaths: () => Dc,
	multiplyTransformMatrices: () => Y,
	multiplyTransformMatrixArray: () => yr,
	parsePath: () => Sc,
	parsePreserveAspectRatioAttribute: () => $i,
	parseUnit: () => Qi,
	pick: () => Fr,
	projectStrokeOnPoints: () => cs,
	qrDecompose: () => Cr,
	radiansToDegrees: () => hr,
	removeFromArray: () => Qn,
	removeTransformFromObject: () => ci,
	removeTransformMatrixForSvgParsing: () => kc,
	requestAnimFrame: () => ar,
	resetObjectTransform: () => di,
	rotateVector: () => Si,
	saveObjectTransform: () => fi,
	sendObjectToPlane: () => _i,
	sendPointToPlane: () => hi,
	sendVectorToPlane: () => gi,
	sin: () => er,
	sizeAfterTransform: () => pi,
	string: () => Xr,
	stylesFromArray: () => fs,
	stylesToArray: () => ds,
	toBlob: () => mr,
	toDataURL: () => pr,
	toFixed: () => X,
	transformPath: () => wc,
	transformPoint: () => _r
});
function Ac(e, t) {
	let n = e.style;
	n && Object.entries(t).forEach(([e, t]) => n.setProperty(e, t));
}
var jc = class extends Jr {
	constructor(e, { allowTouchScrolling: t = !1, containerClass: n = "" } = {}) {
		super(e), H(this, "upper", void 0), H(this, "container", void 0);
		let { el: r } = this.lower, i = this.createUpperCanvas();
		this.upper = {
			el: i,
			ctx: i.getContext("2d")
		}, this.applyCanvasStyle(r, { allowTouchScrolling: t }), this.applyCanvasStyle(i, {
			allowTouchScrolling: t,
			styles: {
				position: "absolute",
				left: "0",
				top: "0"
			}
		});
		let a = this.createContainerElement();
		a.classList.add(n), r.parentNode && r.parentNode.replaceChild(a, r), a.append(r, i), this.container = a;
	}
	createUpperCanvas() {
		let { el: e } = this.lower, t = lr();
		return t.className = e.className, t.classList.remove("lower-canvas"), t.classList.add("upper-canvas"), t.setAttribute("data-fabric", "top"), t.style.cssText = e.style.cssText, t.setAttribute("draggable", "true"), t;
	}
	createContainerElement() {
		let e = _n().createElement("div");
		return e.setAttribute("data-fabric", "wrapper"), Ac(e, { position: "relative" }), qr(e), e;
	}
	applyCanvasStyle(e, t) {
		let { styles: n, allowTouchScrolling: r } = t;
		Ac(e, {
			...n,
			"touch-action": r ? "manipulation" : An
		}), qr(e);
	}
	setDimensions(e, t) {
		super.setDimensions(e, t);
		let { el: n, ctx: r } = this.upper;
		Gr(n, r, e, t);
	}
	setCSSDimensions(e) {
		super.setCSSDimensions(e), Kr(this.upper.el, e), Kr(this.container, e);
	}
	cleanupDOM(e) {
		let t = this.container, { el: n } = this.lower, { el: r } = this.upper;
		super.cleanupDOM(e), t.removeChild(r), t.removeChild(n), t.parentNode && t.parentNode.replaceChild(n, t);
	}
	dispose() {
		super.dispose(), gn().dispose(this.upper.el), delete this.upper, delete this.container;
	}
}, Mc = (e, t, n, r) => {
	let { target: i, offsetX: a, offsetY: o } = t, s = n - a, c = r - o, l = !Fi(i, "lockMovementX") && i.left !== s, u = !Fi(i, "lockMovementY") && i.top !== c;
	return l && i.set("left", s), u && i.set("top", c), (l || u) && yo(Mn, Ii(e, t, n, r)), l || u;
}, Nc = Rn, Pc = (e) => function(t, n, r) {
	let { points: i, pathOffset: a } = r;
	return new q(i[e]).subtract(a).transform(Y(r.getViewportTransform(), r.calcTransformMatrix()));
}, Fc = (e, t, n, r) => {
	let { target: i, pointIndex: a } = t, o = i, s = hi(new q(n, r), void 0, o.calcOwnMatrix());
	return o.points[a] = s.add(o.pathOffset), o.setDimensions(), o.set("dirty", !0), !0;
}, Ic = (e, t) => function(n, r, i, a) {
	let o = r.target, s = new q(o.points[(e > 0 ? e : o.points.length) - 1]), c = s.subtract(o.pathOffset).transform(o.calcOwnMatrix()), l = t(n, {
		...r,
		pointIndex: e
	}, i, a), u = s.subtract(o.pathOffset).transform(o.calcOwnMatrix()).subtract(c);
	return o.left -= u.x, o.top -= u.y, l;
}, Lc = (e) => bo(Nc, Ic(e, Fc));
function Rc(e, t = {}) {
	let n = {};
	for (let r = 0; r < (typeof e == "number" ? e : e.points.length); r++) n[`p${r}`] = new ko({
		actionName: Nc,
		positionHandler: Pc(r),
		actionHandler: Lc(r),
		...t
	});
	return n;
}
var zc = (e, t, n) => {
	let { path: r, pathOffset: i } = e, a = r[t];
	return new q(a[n] - i.x, a[n + 1] - i.y).transform(Y(e.getViewportTransform(), e.calcTransformMatrix()));
};
function Bc(e, t, n) {
	let { commandIndex: r, pointIndex: i } = this;
	return zc(n, r, i);
}
function Vc(e, t, n, r) {
	let { target: i } = t, { commandIndex: a, pointIndex: o } = this, s = ((e, t, n, r, i) => {
		let { path: a, pathOffset: o } = e, s = a[(r > 0 ? r : a.length) - 1], c = new q(s[i], s[i + 1]), l = c.subtract(o).transform(e.calcOwnMatrix()), u = hi(new q(t, n), void 0, e.calcOwnMatrix());
		a[r][i] = u.x + o.x, a[r][i + 1] = u.y + o.y, e.setDimensions();
		let d = c.subtract(e.pathOffset).transform(e.calcOwnMatrix()).subtract(l);
		return e.left -= d.x, e.top -= d.y, e.set("dirty", !0), !0;
	})(i, n, r, a, o);
	return s && yo(this.actionName, {
		...Ii(e, t, n, r),
		commandIndex: a,
		pointIndex: o
	}), s;
}
var Hc = class extends ko {
	constructor(e) {
		super(e);
	}
	render(e, t, n, r, i) {
		let a = {
			...r,
			cornerColor: this.controlFill,
			cornerStrokeColor: this.controlStroke,
			transparentCorners: !this.controlFill
		};
		super.render(e, t, n, a, i);
	}
}, Uc = class extends Hc {
	constructor(e) {
		super(e);
	}
	render(e, t, n, r, i) {
		let { path: a } = i, { commandIndex: o, pointIndex: s, connectToCommandIndex: c, connectToPointIndex: l } = this;
		e.save(), e.strokeStyle = this.controlStroke, this.connectionDashArray && e.setLineDash(this.connectionDashArray);
		let [u] = a[o], d = zc(i, c, l);
		if (u === "Q") {
			let r = zc(i, o, s + 2);
			e.moveTo(r.x, r.y), e.lineTo(t, n);
		} else e.moveTo(t, n);
		e.lineTo(d.x, d.y), e.stroke(), e.restore(), super.render(e, t, n, r, i);
	}
}, Wc = (e, t, n, r, i, a) => new (n ? Uc : Hc)({
	commandIndex: e,
	pointIndex: t,
	actionName: "modifyPath",
	positionHandler: Bc,
	actionHandler: Vc,
	connectToCommandIndex: i,
	connectToPointIndex: a,
	...r,
	...n ? r.controlPointStyle : r.pointStyle
});
function Gc(e, t = {}) {
	let n = {}, r = "M";
	return e.path.forEach((e, i) => {
		let a = e[0];
		switch (a !== "Z" && (n[`c_${i}_${a}`] = Wc(i, e.length - 2, !1, t)), a) {
			case "C":
				n[`c_${i}_C_CP_1`] = Wc(i, 1, !0, t, i - 1, ((e) => e === "C" ? 5 : e === "Q" ? 3 : 1)(r)), n[`c_${i}_C_CP_2`] = Wc(i, 3, !0, t, i, 5);
				break;
			case "Q": n[`c_${i}_Q_CP_1`] = Wc(i, 1, !0, t, i, 3);
		}
		r = a;
	}), n;
}
an({
	changeHeight: () => Eo,
	changeObjectHeight: () => wo,
	changeObjectWidth: () => Co,
	changeWidth: () => To,
	createObjectDefaultControls: () => Zo,
	createPathControls: () => Gc,
	createPolyActionHandler: () => Lc,
	createPolyControls: () => Rc,
	createPolyPositionHandler: () => Pc,
	createResizeControls: () => Qo,
	createTextboxDefaultControls: () => $o,
	dragHandler: () => Mc,
	factoryPolyActionHandler: () => Ic,
	getLocalPoint: () => Ri,
	polyActionHandler: () => Fc,
	renderCircleControl: () => Do,
	renderSquareControl: () => Oo,
	rotationStyleHandler: () => Ao,
	rotationWithSnapping: () => jo,
	scaleCursorStyleHandler: () => Fo,
	scaleOrSkewActionName: () => qo,
	scaleSkewCursorStyleHandler: () => Jo,
	scalingEqually: () => Lo,
	scalingX: () => Ro,
	scalingXOrSkewingY: () => Yo,
	scalingY: () => zo,
	scalingYOrSkewingX: () => Xo,
	skewCursorStyleHandler: () => Ho,
	skewHandlerX: () => Wo,
	skewHandlerY: () => Go,
	wrapWithFireEvent: () => bo,
	wrapWithFixedAnchor: () => xo
});
var Kc = class e extends ni {
	constructor(...e) {
		super(...e), H(this, "_hoveredTargets", []), H(this, "_currentTransform", null), H(this, "_groupSelector", null), H(this, "contextTopDirty", !1);
	}
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	get upperCanvasEl() {
		return this.elements.upper?.el;
	}
	get contextTop() {
		return this.elements.upper?.ctx;
	}
	get wrapperEl() {
		return this.elements.container;
	}
	initElements(e) {
		this.elements = new jc(e, {
			allowTouchScrolling: this.allowTouchScrolling,
			containerClass: this.containerClass
		}), this._createCacheCanvas();
	}
	_onObjectAdded(e) {
		this._objectsToRender = void 0, super._onObjectAdded(e);
	}
	_onObjectRemoved(e) {
		this._objectsToRender = void 0, e === this._activeObject && (this.fire("before:selection:cleared", { deselected: [e] }), this._discardActiveObject(), this.fire("selection:cleared", { deselected: [e] }), e.fire("deselected", { target: e })), e === this._hoveredTarget && (this._hoveredTarget = void 0, this._hoveredTargets = []), super._onObjectRemoved(e);
	}
	_onStackOrderChanged() {
		this._objectsToRender = void 0, super._onStackOrderChanged();
	}
	_chooseObjectsToRender() {
		let e = this._activeObject;
		return !this.preserveObjectStacking && e ? this._objects.filter((t) => !t.group && t !== e).concat(e) : this._objects;
	}
	renderAll() {
		this.cancelRequestedRender(), this.destroyed || (!this.contextTopDirty || this._groupSelector || this.isDrawingMode || (this.clearContext(this.contextTop), this.contextTopDirty = !1), this.hasLostContext &&= (this.renderTopLayer(this.contextTop), !1), !this._objectsToRender && (this._objectsToRender = this._chooseObjectsToRender()), this.renderCanvas(this.getContext(), this._objectsToRender));
	}
	renderTopLayer(e) {
		e.save(), this.isDrawingMode && this._isCurrentlyDrawing && (this.freeDrawingBrush && this.freeDrawingBrush._render(), this.contextTopDirty = !0), this.selection && this._groupSelector && (this._drawSelection(e), this.contextTopDirty = !0), e.restore();
	}
	renderTop() {
		let e = this.contextTop;
		this.clearContext(e), this.renderTopLayer(e), this.fire("after:render", { ctx: e });
	}
	setTargetFindTolerance(e) {
		e = Math.round(e), this.targetFindTolerance = e;
		let t = this.getRetinaScaling(), n = Math.ceil((2 * e + 1) * t);
		this.pixelFindCanvasEl.width = this.pixelFindCanvasEl.height = n, this.pixelFindContext.scale(t, t);
	}
	isTargetTransparent(e, t, n) {
		let r = this.targetFindTolerance, i = this.pixelFindContext;
		this.clearContext(i), i.save(), i.translate(-t + r, -n + r), i.transform(...this.viewportTransform);
		let a = e.selectionBackgroundColor;
		e.selectionBackgroundColor = "", e.render(i), e.selectionBackgroundColor = a, i.restore();
		let o = Math.round(r * this.getRetinaScaling());
		return rs(i, o, o, o);
	}
	_isSelectionKeyPressed(e) {
		let t = this.selectionKey;
		return !!t && (Array.isArray(t) ? !!t.find((t) => !!t && !0 === e[t]) : e[t]);
	}
	_shouldClearSelection(e, t) {
		let n = this.getActiveObjects(), r = this._activeObject;
		return !!(!t || t && r && n.length > 1 && n.indexOf(t) === -1 && r !== t && !this._isSelectionKeyPressed(e) || t && !t.evented || t && !t.selectable && r && r !== t);
	}
	_shouldCenterTransform(e, t, n) {
		if (!e) return;
		let r;
		return t === "scale" || t === "scaleX" || t === "scaleY" || t === "resizing" ? r = this.centeredScaling || e.centeredScaling : t === "rotate" && (r = this.centeredRotation || e.centeredRotation), r ? !n : n;
	}
	_getOriginFromCorner(e, t) {
		let n = t ? e.controls[t].getTransformAnchorPoint() : {
			x: e.originX,
			y: e.originY
		};
		return t ? ([
			"ml",
			"tl",
			"bl"
		].includes(t) ? n.x = kn : [
			"mr",
			"tr",
			"br"
		].includes(t) && (n.x = G), [
			"tl",
			"mt",
			"tr"
		].includes(t) ? n.y = On : [
			"bl",
			"mb",
			"br"
		].includes(t) && (n.y = "top"), n) : n;
	}
	_setupCurrentTransform(e, t, n) {
		let r = t.group ? hi(this.getScenePoint(e), void 0, t.group.calcTransformMatrix()) : this.getScenePoint(e), { key: i = "", control: a } = t.getActiveControl() || {}, o = n && a ? a.getActionHandler(e, t, a)?.bind(a) : Mc, s = ((e, t, n, r) => {
			if (!t || !e) return "drag";
			let i = r.controls[t];
			return i.getActionName(n, i, r);
		})(n, i, e, t), c = e[this.centeredKey], l = this._shouldCenterTransform(t, s, c) ? {
			x: W,
			y: W
		} : this._getOriginFromCorner(t, i), { scaleX: u, scaleY: d, skewX: f, skewY: p, left: m, top: h, angle: g, width: _, height: v, cropX: y, cropY: b } = t, x = {
			target: t,
			action: s,
			actionHandler: o,
			actionPerformed: !1,
			corner: i,
			scaleX: u,
			scaleY: d,
			skewX: f,
			skewY: p,
			offsetX: r.x - m,
			offsetY: r.y - h,
			originX: l.x,
			originY: l.y,
			ex: r.x,
			ey: r.y,
			lastX: r.x,
			lastY: r.y,
			theta: J(g),
			width: _,
			height: v,
			shiftKey: e.shiftKey,
			altKey: c,
			original: {
				...fi(t),
				originX: l.x,
				originY: l.y,
				cropX: y,
				cropY: b
			}
		};
		this._currentTransform = x, this.fire("before:transform", {
			e,
			transform: x
		});
	}
	setCursor(e) {
		this.upperCanvasEl.style.cursor = e;
	}
	_drawSelection(e) {
		let { x: t, y: n, deltaX: r, deltaY: i } = this._groupSelector, a = new q(t, n).transform(this.viewportTransform), o = new q(t + r, n + i).transform(this.viewportTransform), s = this.selectionLineWidth / 2, c = Math.min(a.x, o.x), l = Math.min(a.y, o.y), u = Math.max(a.x, o.x), d = Math.max(a.y, o.y);
		this.selectionColor && (e.fillStyle = this.selectionColor, e.fillRect(c, l, u - c, d - l)), this.selectionLineWidth && this.selectionBorderColor && (e.lineWidth = this.selectionLineWidth, e.strokeStyle = this.selectionBorderColor, c += s, l += s, u -= s, d -= s, ns.prototype._setLineDash.call(this, e, this.selectionDashArray), e.strokeRect(c, l, u - c, d - l));
	}
	findTarget(e) {
		if (this._targetInfo) return this._targetInfo;
		if (this.skipTargetFind) return {
			subTargets: [],
			currentSubTargets: []
		};
		let t = this.getScenePoint(e), n = this._activeObject, r = this.getActiveObjects(), i = this.searchPossibleTargets(this._objects, t), { subTargets: a, container: o, target: s } = i, c = {
			...i,
			currentSubTargets: a,
			currentContainer: o,
			currentTarget: s
		};
		if (!n) return c;
		let l = {
			...this.searchPossibleTargets([n], t),
			currentSubTargets: a,
			currentContainer: o,
			currentTarget: s
		};
		return n.findControl(this.getViewportPoint(e), ai(e)) ? {
			...l,
			target: n
		} : l.target && (r.length > 1 || !this.preserveObjectStacking || this.preserveObjectStacking && e[this.altSelectionKey]) ? l : c;
	}
	_pointIsInObjectSelectionArea(e, t) {
		let n = e.getCoords(), r = this.getZoom(), i = e.padding / r;
		if (i) {
			let [e, t, r, a] = n, o = Math.atan2(t.y - e.y, t.x - e.x), s = $n(o) * i, c = er(o) * i, l = s + c, u = s - c;
			n = [
				new q(e.x - u, e.y - l),
				new q(t.x + l, t.y - u),
				new q(r.x + u, r.y + l),
				new q(a.x - l, a.y + u)
			];
		}
		return go.isPointInPolygon(t, n);
	}
	_checkTarget(e, t) {
		if (e && e.visible && e.evented && this._pointIsInObjectSelectionArea(e, t)) {
			if (!this.perPixelTargetFind && !e.perPixelTargetFind || e.isEditing) return !0;
			{
				let n = t.transform(this.viewportTransform);
				if (!this.isTargetTransparent(e, n.x, n.y)) return !0;
			}
		}
		return !1;
	}
	_searchPossibleTargets(e, t, n) {
		let r = e.length;
		for (; r--;) {
			let i = e[r];
			if (this._checkTarget(i, t)) {
				if (nr(i) && i.subTargetCheck) {
					let { target: e } = this._searchPossibleTargets(i._objects, t, n);
					e && n.push(e);
				}
				return {
					target: i,
					subTargets: n
				};
			}
		}
		return { subTargets: [] };
	}
	searchPossibleTargets(e, t) {
		let n = this._searchPossibleTargets(e, t, []);
		n.container = n.target;
		let { container: r, subTargets: i } = n;
		if (r && nr(r) && r.interactive && i[0]) {
			for (let e = i.length - 1; e > 0; e--) {
				let t = i[e];
				if (!nr(t) || !t.interactive) return n.target = t, n;
			}
			return n.target = i[0], n;
		}
		return n;
	}
	getViewportPoint(e) {
		return this._viewportPoint ? this._viewportPoint : this._getPointerImpl(e, !0);
	}
	getScenePoint(e) {
		return this._scenePoint ? this._scenePoint : this._getPointerImpl(e);
	}
	_getPointerImpl(e, t = !1) {
		let n = this.upperCanvasEl, r = n.getBoundingClientRect(), i = ii(e), a = r.width || 0, o = r.height || 0;
		a && o || ("top" in r && "bottom" in r && (o = Math.abs(r.top - r.bottom)), "right" in r && "left" in r && (a = Math.abs(r.right - r.left))), this.calcOffset(), i.x -= this._offset.left, i.y -= this._offset.top, t || (i = hi(i, void 0, this.viewportTransform));
		let s = this.getRetinaScaling();
		s !== 1 && (i.x /= s, i.y /= s);
		let c = a === 0 || o === 0 ? new q(1, 1) : new q(n.width / a, n.height / o);
		return i.multiply(c);
	}
	_setDimensionsImpl(e, t) {
		this._resetTransformEventData(), super._setDimensionsImpl(e, t), this._isCurrentlyDrawing && this.freeDrawingBrush && this.freeDrawingBrush._setBrushStyles(this.contextTop);
	}
	_createCacheCanvas() {
		this.pixelFindCanvasEl = lr(), this.pixelFindContext = this.pixelFindCanvasEl.getContext("2d", { willReadFrequently: !0 }), this.setTargetFindTolerance(this.targetFindTolerance);
	}
	getTopContext() {
		return this.elements.upper.ctx;
	}
	getSelectionContext() {
		return this.elements.upper.ctx;
	}
	getSelectionElement() {
		return this.elements.upper.el;
	}
	getActiveObject() {
		return this._activeObject;
	}
	getActiveObjects() {
		let e = this._activeObject;
		return Vr(e) ? e.getObjects() : e ? [e] : [];
	}
	_fireSelectionEvents(e, t) {
		let n = !1, r = !1, i = this.getActiveObjects(), a = [], o = [];
		e.forEach((e) => {
			i.includes(e) || (n = !0, e.fire("deselected", {
				e: t,
				target: e
			}), o.push(e));
		}), i.forEach((r) => {
			e.includes(r) || (n = !0, r.fire("selected", {
				e: t,
				target: r
			}), a.push(r));
		}), e.length > 0 && i.length > 0 ? (r = !0, n && this.fire("selection:updated", {
			e: t,
			selected: a,
			deselected: o
		})) : i.length > 0 ? (r = !0, this.fire("selection:created", {
			e: t,
			selected: a
		})) : e.length > 0 && (r = !0, this.fire("selection:cleared", {
			e: t,
			deselected: o
		})), r && (this._objectsToRender = void 0);
	}
	setActiveObject(e, t) {
		let n = this.getActiveObjects(), r = this._setActiveObject(e, t);
		return this._fireSelectionEvents(n, t), r;
	}
	_setActiveObject(e, t) {
		let n = this._activeObject;
		return n !== e && !(!this._discardActiveObject(t, e) && this._activeObject) && !e.onSelect({ e: t }) && (this._activeObject = e, Vr(e) && n !== e && e.set("canvas", this), e.setCoords(), !0);
	}
	_discardActiveObject(e, t) {
		let n = this._activeObject;
		return !!n && !n.onDeselect({
			e,
			object: t
		}) && (this._currentTransform && this._currentTransform.target === n && this.endCurrentTransform(e), Vr(n) && n === this._hoveredTarget && (this._hoveredTarget = void 0), this._activeObject = void 0, !0);
	}
	discardActiveObject(e) {
		let t = this.getActiveObjects(), n = this.getActiveObject();
		t.length && this.fire("before:selection:cleared", {
			e,
			deselected: [n]
		});
		let r = this._discardActiveObject(e);
		return this._fireSelectionEvents(t, e), r;
	}
	endCurrentTransform(e) {
		let t = this._currentTransform;
		this._finalizeCurrentTransform(e), t && t.target && (t.target.isMoving = !1), this._currentTransform = null;
	}
	_finalizeCurrentTransform(e) {
		let t = this._currentTransform, n = t.target, r = {
			e,
			target: n,
			transform: t,
			action: t.action
		};
		n._scaling &&= !1, n.setCoords(), t.actionPerformed && (this.fire("object:modified", r), n.fire(qn, r));
	}
	setViewportTransform(e) {
		super.setViewportTransform(e);
		let t = this._activeObject;
		t && t.setCoords();
	}
	destroy() {
		let e = this._activeObject;
		Vr(e) && (e.removeAll(), e.dispose()), delete this._activeObject, super.destroy(), this.pixelFindContext = null, this.pixelFindCanvasEl = void 0;
	}
	clear() {
		this.discardActiveObject(), this._activeObject = void 0, this.clearContext(this.contextTop), super.clear();
	}
	drawControls(e) {
		let t = this._activeObject;
		t && t._renderControls(e);
	}
	_toObject(e, t, n) {
		let r = this._realizeGroupTransformOnObject(e), i = super._toObject(e, t, n);
		return e.set(r), i;
	}
	_realizeGroupTransformOnObject(e) {
		let { group: t } = e;
		if (t && Vr(t) && this._activeObject === t) {
			let n = Fr(e, [
				"angle",
				"flipX",
				"flipY",
				G,
				Vn,
				Hn,
				Un,
				Wn,
				"top"
			]);
			return li(e, t.calcOwnMatrix()), n;
		}
		return {};
	}
	_setSVGObject(e, t, n) {
		let r = this._realizeGroupTransformOnObject(t);
		super._setSVGObject(e, t, n), t.set(r);
	}
};
H(Kc, "ownDefaults", {
	uniformScaling: !0,
	uniScaleKey: "shiftKey",
	centeredScaling: !1,
	centeredRotation: !1,
	centeredKey: "altKey",
	altActionKey: "shiftKey",
	selection: !0,
	selectionKey: "shiftKey",
	selectionColor: "rgba(100, 100, 255, 0.3)",
	selectionDashArray: [],
	selectionBorderColor: "rgba(255, 255, 255, 0.3)",
	selectionLineWidth: 1,
	selectionFullyContained: !1,
	hoverCursor: "move",
	moveCursor: "move",
	defaultCursor: "default",
	freeDrawingCursor: "crosshair",
	notAllowedCursor: "not-allowed",
	perPixelTargetFind: !1,
	targetFindTolerance: 0,
	skipTargetFind: !1,
	stopContextMenu: !0,
	fireRightClick: !0,
	fireMiddleClick: !0,
	enablePointerEvents: !1,
	containerClass: "canvas-container",
	preserveObjectStacking: !0
});
var qc = class {
	constructor(e) {
		H(this, "targets", []), H(this, "__disposer", void 0);
		let t = () => {
			let { hiddenTextarea: t } = e.getActiveObject() || {};
			t && t.focus();
		}, n = e.upperCanvasEl;
		n.addEventListener("click", t), this.__disposer = () => n.removeEventListener("click", t);
	}
	exitTextEditing() {
		this.target = void 0, this.targets.forEach((e) => {
			e.isEditing && e.exitEditing();
		});
	}
	add(e) {
		this.targets.push(e);
	}
	remove(e) {
		this.unregister(e), Qn(this.targets, e);
	}
	register(e) {
		this.target = e;
	}
	unregister(e) {
		e === this.target && (this.target = void 0);
	}
	onMouseMove(e) {
		var t;
		(t = this.target) != null && t.isEditing && this.target.updateSelectionOnMouseMove(e);
	}
	clear() {
		this.targets = [], this.target = void 0;
	}
	dispose() {
		this.clear(), this.__disposer(), delete this.__disposer;
	}
}, Jc = { passive: !1 }, Yc = (e, t) => ({
	viewportPoint: e.getViewportPoint(t),
	scenePoint: e.getScenePoint(t)
}), Xc = (e, ...t) => e.addEventListener(...t), Zc = (e, ...t) => e.removeEventListener(...t), Qc = {
	mouse: {
		in: "over",
		out: "out",
		targetIn: "mouseover",
		targetOut: "mouseout",
		canvasIn: "mouse:over",
		canvasOut: "mouse:out"
	},
	drag: {
		in: "enter",
		out: "leave",
		targetIn: "dragenter",
		targetOut: "dragleave",
		canvasIn: "drag:enter",
		canvasOut: "drag:leave"
	}
}, $c = class extends Kc {
	constructor(e, t = {}) {
		super(e, t), H(this, "_isClick", void 0), H(this, "textEditingManager", new qc(this)), [
			"_onMouseDown",
			"_onTouchStart",
			"_onMouseMove",
			"_onMouseUp",
			"_onTouchEnd",
			"_onResize",
			"_onMouseWheel",
			"_onMouseOut",
			"_onMouseEnter",
			"_onContextMenu",
			"_onClick",
			"_onDragStart",
			"_onDragEnd",
			"_onDragProgress",
			"_onDragOver",
			"_onDragEnter",
			"_onDragLeave",
			"_onDrop"
		].forEach((e) => {
			this[e] = this[e].bind(this);
		}), this.addOrRemove(Xc);
	}
	_getEventPrefix() {
		return this.enablePointerEvents ? "pointer" : "mouse";
	}
	addOrRemove(e, t = !1) {
		let n = this.upperCanvasEl, r = this._getEventPrefix();
		e(Wr(n), "resize", this._onResize), e(n, r + "down", this._onMouseDown), e(n, `${r}move`, this._onMouseMove, Jc), e(n, `${r}out`, this._onMouseOut), e(n, `${r}enter`, this._onMouseEnter), e(n, "wheel", this._onMouseWheel, { passive: !1 }), e(n, "contextmenu", this._onContextMenu), t || (e(n, "click", this._onClick), e(n, "dblclick", this._onClick)), e(n, "dragstart", this._onDragStart), e(n, "dragend", this._onDragEnd), e(n, "dragover", this._onDragOver), e(n, "dragenter", this._onDragEnter), e(n, "dragleave", this._onDragLeave), e(n, "drop", this._onDrop), this.enablePointerEvents || e(n, "touchstart", this._onTouchStart, Jc);
	}
	removeListeners() {
		this.addOrRemove(Zc);
		let e = this._getEventPrefix(), t = Ur(this.upperCanvasEl);
		Zc(t, `${e}up`, this._onMouseUp), Zc(t, "touchend", this._onTouchEnd, Jc), Zc(t, `${e}move`, this._onMouseMove, Jc), Zc(t, "touchmove", this._onMouseMove, Jc), clearTimeout(this._willAddMouseDown);
	}
	_onMouseWheel(e) {
		this._cacheTransformEventData(e), this._handleEvent(e, "wheel"), this._resetTransformEventData();
	}
	_onMouseOut(e) {
		let t = this._hoveredTarget, n = {
			e,
			...Yc(this, e)
		};
		this.fire("mouse:out", {
			...n,
			target: t
		}), this._hoveredTarget = void 0, t && t.fire("mouseout", { ...n }), this._hoveredTargets.forEach((e) => {
			this.fire("mouse:out", {
				...n,
				target: e
			}), e && e.fire("mouseout", { ...n });
		}), this._hoveredTargets = [];
	}
	_onMouseEnter(e) {
		let { target: t } = this.findTarget(e);
		this._currentTransform || t || (this.fire("mouse:over", {
			e,
			...Yc(this, e)
		}), this._hoveredTarget = void 0, this._hoveredTargets = []);
	}
	_onDragStart(e) {
		this._isClick = !1;
		let t = this.getActiveObject();
		if (t && t.onDragStart(e)) {
			this._dragSource = t;
			let n = {
				e,
				target: t
			};
			this.fire("dragstart", n), t.fire("dragstart", n), Xc(this.upperCanvasEl, "drag", this._onDragProgress);
			return;
		}
		oi(e);
	}
	_renderDragEffects(e, t, n) {
		let r = !1, i = this._dropTarget;
		i && i !== t && i !== n && (i.clearContextTop(), r = !0), t?.clearContextTop(), n !== t && n?.clearContextTop();
		let a = this.contextTop;
		a.save(), a.transform(...this.viewportTransform), t && (a.save(), t.transform(a), t.renderDragSourceEffect(e), a.restore(), r = !0), n && (a.save(), n.transform(a), n.renderDropTargetEffect(e), a.restore(), r = !0), a.restore(), r && (this.contextTopDirty = !0);
	}
	_onDragEnd(e) {
		let { currentSubTargets: t } = this.findTarget(e), n = !!e.dataTransfer && e.dataTransfer.dropEffect !== "none", r = n ? this._activeObject : void 0, i = {
			e,
			target: this._dragSource,
			subTargets: t,
			dragSource: this._dragSource,
			didDrop: n,
			dropTarget: r
		};
		Zc(this.upperCanvasEl, "drag", this._onDragProgress), this.fire("dragend", i), this._dragSource && this._dragSource.fire("dragend", i), delete this._dragSource, this._onMouseUp(e);
	}
	_onDragProgress(e) {
		let t = {
			e,
			target: this._dragSource,
			dragSource: this._dragSource,
			dropTarget: this._draggedoverTarget
		};
		this.fire("drag", t), this._dragSource && this._dragSource.fire("drag", t);
	}
	_onDragOver(e) {
		let t = "dragover", { currentContainer: n, currentSubTargets: r } = this.findTarget(e), i = this._dragSource, a = {
			e,
			target: n,
			subTargets: r,
			dragSource: i,
			canDrop: !1,
			dropTarget: void 0
		}, o;
		this.fire(t, a), this._fireEnterLeaveEvents(e, n, a), n && (n.canDrop(e) && (o = n), n.fire(t, a));
		for (let n = 0; n < r.length; n++) {
			let i = r[n];
			i.canDrop(e) && (o = i), i.fire(t, a);
		}
		this._renderDragEffects(e, i, o), this._dropTarget = o;
	}
	_onDragEnter(e) {
		let { currentContainer: t, currentSubTargets: n } = this.findTarget(e), r = {
			e,
			target: t,
			subTargets: n,
			dragSource: this._dragSource
		};
		this.fire("dragenter", r), this._fireEnterLeaveEvents(e, t, r);
	}
	_onDragLeave(e) {
		let { currentSubTargets: t } = this.findTarget(e), n = {
			e,
			target: this._draggedoverTarget,
			subTargets: t,
			dragSource: this._dragSource
		};
		this.fire("dragleave", n), this._fireEnterLeaveEvents(e, void 0, n), this._renderDragEffects(e, this._dragSource), this._dropTarget = void 0, this._hoveredTargets = [];
	}
	_onDrop(e) {
		let { currentContainer: t, currentSubTargets: n } = this.findTarget(e), r = this._basicEventHandler("drop:before", {
			e,
			target: t,
			subTargets: n,
			dragSource: this._dragSource,
			...Yc(this, e)
		});
		r.didDrop = !1, r.dropTarget = void 0, this._basicEventHandler("drop", r), this.fire("drop:after", r);
	}
	_onContextMenu(e) {
		let { target: t, subTargets: n } = this.findTarget(e), r = this._basicEventHandler("contextmenu:before", {
			e,
			target: t,
			subTargets: n
		});
		return this.stopContextMenu && oi(e), this._basicEventHandler("contextmenu", r), !1;
	}
	_onClick(e) {
		let t = e.detail;
		t > 3 || t < 2 || (this._cacheTransformEventData(e), t == 2 && e.type === "dblclick" && this._handleEvent(e, "dblclick"), t == 3 && this._handleEvent(e, "tripleclick"), this._resetTransformEventData());
	}
	fireEventFromPointerEvent(e, t, n, r = {}) {
		this._cacheTransformEventData(e);
		let { target: i, subTargets: a } = this.findTarget(e), o = {
			e,
			target: i,
			subTargets: a,
			...Yc(this, e),
			transform: this._currentTransform,
			...r
		};
		this.fire(t, o), i && i.fire(n, o);
		for (let e = 0; e < a.length; e++) a[e] !== i && a[e].fire(n, o);
		this._resetTransformEventData();
	}
	getPointerId(e) {
		let t = e.changedTouches;
		return t ? t[0] && t[0].identifier : this.enablePointerEvents ? e.pointerId : -1;
	}
	_isMainEvent(e) {
		return !0 === e.isPrimary || !1 !== e.isPrimary && (e.type === "touchend" && e.touches.length === 0 || !e.changedTouches || e.changedTouches[0].identifier === this.mainTouchId);
	}
	_onTouchStart(e) {
		this._cacheTransformEventData(e);
		let t = !this.allowTouchScrolling, n = this._activeObject;
		this.mainTouchId === void 0 && (this.mainTouchId = this.getPointerId(e)), this.__onMouseDown(e);
		let { target: r } = this.findTarget(e);
		(this.isDrawingMode || n && r === n) && (t = !0), t && e.preventDefault();
		let i = this.upperCanvasEl, a = this._getEventPrefix(), o = Ur(i);
		Xc(o, "touchend", this._onTouchEnd, Jc), t && Xc(o, "touchmove", this._onMouseMove, Jc), Zc(i, `${a}down`, this._onMouseDown), this._resetTransformEventData();
	}
	_onMouseDown(e) {
		this._cacheTransformEventData(e), this.__onMouseDown(e);
		let t = this.upperCanvasEl, n = this._getEventPrefix();
		Zc(t, `${n}move`, this._onMouseMove, Jc);
		let r = Ur(t);
		Xc(r, `${n}up`, this._onMouseUp), Xc(r, `${n}move`, this._onMouseMove, Jc), this._resetTransformEventData();
	}
	_onTouchEnd(e) {
		if (e.touches.length > 0) return;
		this._cacheTransformEventData(e), this.__onMouseUp(e), this._resetTransformEventData(), delete this.mainTouchId;
		let t = this._getEventPrefix(), n = Ur(this.upperCanvasEl);
		Zc(n, "touchend", this._onTouchEnd, Jc), Zc(n, "touchmove", this._onMouseMove, Jc), this._willAddMouseDown && clearTimeout(this._willAddMouseDown), this._willAddMouseDown = setTimeout(() => {
			Xc(this.upperCanvasEl, `${t}down`, this._onMouseDown), this._willAddMouseDown = 0;
		}, 400);
	}
	_onMouseUp(e) {
		this._cacheTransformEventData(e), this.__onMouseUp(e);
		let t = this.upperCanvasEl, n = this._getEventPrefix();
		if (this._isMainEvent(e)) {
			let e = Ur(this.upperCanvasEl);
			Zc(e, `${n}up`, this._onMouseUp), Zc(e, `${n}move`, this._onMouseMove, Jc), Xc(t, `${n}move`, this._onMouseMove, Jc);
		}
		this._resetTransformEventData();
	}
	_onMouseMove(e) {
		this._cacheTransformEventData(e);
		let t = this.getActiveObject();
		!this.allowTouchScrolling && (!t || !t.shouldStartDragging(e)) && e.preventDefault && e.preventDefault(), this.__onMouseMove(e), this._resetTransformEventData();
	}
	_onResize() {
		this.calcOffset(), this._resetTransformEventData();
	}
	_shouldRender(e) {
		let t = this.getActiveObject();
		return !!t != !!e || t && e && t !== e;
	}
	__onMouseUp(e) {
		var t;
		this._handleEvent(e, "up:before");
		let n = this._currentTransform, r = this._isClick, { target: i } = this.findTarget(e), { button: a } = e;
		if (a) return void ((this.fireMiddleClick && a === 1 || this.fireRightClick && a === 2) && this._handleEvent(e, "up"));
		if (this.isDrawingMode && this._isCurrentlyDrawing) return void this._onMouseUpInDrawingMode(e);
		if (!this._isMainEvent(e)) return;
		let o, s, c = !1;
		if (n && (this._finalizeCurrentTransform(e), c = n.actionPerformed), !r) {
			let t = i === this._activeObject;
			this.handleSelection(e), c ||= this._shouldRender(i) || !t && i === this._activeObject;
		}
		if (i) {
			let { key: t, control: r } = i.findControl(this.getViewportPoint(e), ai(e)) || {};
			if (s = t, i.selectable && i !== this._activeObject && i.activeOn === "up") this.setActiveObject(i, e), c = !0;
			else if (r) {
				let t = r.getMouseUpHandler(e, i, r);
				t && (o = this.getScenePoint(e), t.call(r, e, n, o.x, o.y));
			}
			i.isMoving = !1;
		}
		if (n && (n.target !== i || n.corner !== s)) {
			let t = n.target && n.target.controls[n.corner], r = t && t.getMouseUpHandler(e, n.target, t);
			o ||= this.getScenePoint(e), r && r.call(t, e, n, o.x, o.y);
		}
		this._setCursorFromEvent(e, i), this._handleEvent(e, "up"), this._groupSelector = null, this._currentTransform = null, i && (i.__corner = void 0), c ? this.requestRenderAll() : r || (t = this._activeObject) != null && t.isEditing || this.renderTop();
	}
	_basicEventHandler(e, t) {
		let { target: n, subTargets: r = [] } = t;
		this.fire(e, t), n && n.fire(e, t);
		for (let i = 0; i < r.length; i++) r[i] !== n && r[i].fire(e, t);
		return t;
	}
	_handleEvent(e, t, n) {
		let { target: r, subTargets: i } = this.findTarget(e), a = {
			e,
			target: r,
			subTargets: i,
			...Yc(this, e),
			transform: this._currentTransform,
			...t === "down:before" || t === "down" ? n : {}
		};
		t !== "up:before" && t !== "up" || (a.isClick = this._isClick), this.fire(`mouse:${t}`, a), r && r.fire(`mouse${t}`, a);
		for (let e = 0; e < i.length; e++) i[e] !== r && i[e].fire(`mouse${t}`, a);
	}
	_onMouseDownInDrawingMode(e) {
		this._isCurrentlyDrawing = !0, this.getActiveObject() && (this.discardActiveObject(e), this.requestRenderAll());
		let t = this.getScenePoint(e);
		this.freeDrawingBrush && this.freeDrawingBrush.onMouseDown(t, {
			e,
			pointer: t
		}), this._handleEvent(e, "down", { alreadySelected: !1 });
	}
	_onMouseMoveInDrawingMode(e) {
		if (this._isCurrentlyDrawing) {
			let t = this.getScenePoint(e);
			this.freeDrawingBrush && this.freeDrawingBrush.onMouseMove(t, {
				e,
				pointer: t
			});
		}
		this.setCursor(this.freeDrawingCursor), this._handleEvent(e, "move");
	}
	_onMouseUpInDrawingMode(e) {
		let t = this.getScenePoint(e);
		this.freeDrawingBrush ? this._isCurrentlyDrawing = !!this.freeDrawingBrush.onMouseUp({
			e,
			pointer: t
		}) : this._isCurrentlyDrawing = !1, this._handleEvent(e, "up");
	}
	__onMouseDown(e) {
		this._isClick = !0, this._handleEvent(e, "down:before");
		let { target: t } = this.findTarget(e), n = !!t && t === this._activeObject, { button: r } = e;
		if (r) return void ((this.fireMiddleClick && r === 1 || this.fireRightClick && r === 2) && this._handleEvent(e, "down", { alreadySelected: n }));
		if (this.isDrawingMode) return void this._onMouseDownInDrawingMode(e);
		if (!this._isMainEvent(e) || this._currentTransform) return;
		let i = this._shouldRender(t), a = !1;
		if (this.handleMultiSelection(e, t) ? (t = this._activeObject, a = !0, i = !0) : this._shouldClearSelection(e, t) && this.discardActiveObject(e), this.selection && (!t || !t.selectable && !t.isEditing && t !== this._activeObject)) {
			let t = this.getScenePoint(e);
			this._groupSelector = {
				x: t.x,
				y: t.y,
				deltaY: 0,
				deltaX: 0
			};
		}
		if (n = !!t && t === this._activeObject, t) {
			t.selectable && t.activeOn === "down" && this.setActiveObject(t, e);
			let r = t.findControl(this.getViewportPoint(e), ai(e));
			if (t === this._activeObject && (r || !a)) {
				this._setupCurrentTransform(e, t, n);
				let i = r ? r.control : void 0, a = this.getScenePoint(e), o = i && i.getMouseDownHandler(e, t, i);
				o && o.call(i, e, this._currentTransform, a.x, a.y);
			}
		}
		i && (this._objectsToRender = void 0), this._handleEvent(e, "down", { alreadySelected: n }), i && this.requestRenderAll();
	}
	_resetTransformEventData() {
		this._targetInfo = this._viewportPoint = this._scenePoint = void 0;
	}
	_cacheTransformEventData(e) {
		this._resetTransformEventData(), this._viewportPoint = this.getViewportPoint(e), this._scenePoint = hi(this._viewportPoint, void 0, this.viewportTransform), this._targetInfo = this.findTarget(e), this._currentTransform && (this._targetInfo.target = this._currentTransform.target);
	}
	__onMouseMove(e) {
		if (this._isClick = !1, this._handleEvent(e, "move:before"), this.isDrawingMode) return void this._onMouseMoveInDrawingMode(e);
		if (!this._isMainEvent(e)) return;
		let t = this._groupSelector;
		if (t) {
			let n = this.getScenePoint(e);
			t.deltaX = n.x - t.x, t.deltaY = n.y - t.y, this.renderTop();
		} else if (this._currentTransform) this._transformObject(e);
		else {
			let { target: t } = this.findTarget(e);
			this._setCursorFromEvent(e, t), this._fireOverOutEvents(e, t);
		}
		this.textEditingManager.onMouseMove(e), this._handleEvent(e, "move");
	}
	_fireOverOutEvents(e, t) {
		let { _hoveredTarget: n, _hoveredTargets: r } = this, { subTargets: i, currentTarget: a } = this.findTarget(e), o = Math.max(r.length, i.length);
		this.fireSyntheticInOutEvents("mouse", {
			e,
			target: t,
			oldTarget: n,
			actualTarget: a,
			oldActualTarget: this._hoveredActualTarget,
			fireCanvas: !0
		});
		for (let a = 0; a < o; a++) i[a] === t || r[a] && r[a] === n || this.fireSyntheticInOutEvents("mouse", {
			e,
			target: i[a],
			oldTarget: r[a]
		});
		this._hoveredActualTarget = a, this._hoveredTarget = t, this._hoveredTargets = i;
	}
	_fireEnterLeaveEvents(e, t, n) {
		let r = this._draggedoverTarget, i = this._hoveredTargets, { subTargets: a } = this.findTarget(e), o = Math.max(i.length, a.length);
		this.fireSyntheticInOutEvents("drag", {
			...n,
			target: t,
			oldTarget: r,
			fireCanvas: !0
		});
		for (let e = 0; e < o; e++) this.fireSyntheticInOutEvents("drag", {
			...n,
			target: a[e],
			oldTarget: i[e]
		});
		this._draggedoverTarget = t;
	}
	fireSyntheticInOutEvents(e, { target: t, oldTarget: n, actualTarget: r, oldActualTarget: i, fireCanvas: a, e: o, ...s }) {
		let { targetIn: c, targetOut: l, canvasIn: u, canvasOut: d } = Qc[e], f = n !== t, p = i !== r, m = t && f, h = r && p, g = n && f, _ = i && p, v = {
			...s,
			e: o,
			...Yc(this, o)
		}, y = {
			...v,
			target: n,
			nextTarget: t,
			actualTarget: i,
			nextActualTarget: r
		};
		(g || _) && a && this.fire(d, y), g && n.fire(l, y), _ && n !== i && i.fire(l, y);
		let b = {
			...v,
			target: t,
			previousTarget: n,
			actualTarget: r,
			previousActualTarget: i
		};
		(m || h) && a && this.fire(u, b), m && t.fire(c, b), h && r !== t && r.fire(c, b);
	}
	_transformObject(e) {
		let t = this.getScenePoint(e), n = this._currentTransform, r = n.target, i = r.group ? hi(t, void 0, r.group.calcTransformMatrix()) : t;
		n.shiftKey = e.shiftKey, n.altKey = !!this.centeredKey && e[this.centeredKey], this._performTransformAction(e, n, i), n.actionPerformed && this.requestRenderAll();
	}
	_performTransformAction(e, t, n) {
		let { action: r, actionHandler: i, target: a } = t, o = !!i && i(e, t, n.x, n.y);
		o && a.setCoords(), r === "drag" && o && (t.target.isMoving = !0, this.setCursor(t.target.moveCursor || this.moveCursor)), t.actionPerformed = t.actionPerformed || o;
	}
	_setCursorFromEvent(e, t) {
		if (!t) return void this.setCursor(this.defaultCursor);
		let n = t.hoverCursor || this.hoverCursor, r = Vr(this._activeObject) ? this._activeObject : null, i = (!r || t.group !== r) && t.findControl(this.getViewportPoint(e));
		if (i) {
			let { control: n, coord: r } = i;
			this.setCursor(n.cursorStyleHandler(e, n, t, r));
		} else {
			if (t.subTargetCheck) {
				let { subTargets: t } = this.findTarget(e);
				t.concat().reverse().forEach((e) => {
					n = e.hoverCursor || n;
				});
			}
			this.setCursor(n);
		}
	}
	handleMultiSelection(e, t) {
		let n = this._activeObject, r = Vr(n);
		if (n && this._isSelectionKeyPressed(e) && this.selection && t && t.selectable && (n !== t || r) && (r || !t.isDescendantOf(n) && !n.isDescendantOf(t)) && !t.onSelect({ e }) && !n.getActiveControl()) {
			if (r) {
				let r = n.getObjects(), i = [];
				if (t === n) {
					let n = this.getScenePoint(e), a = this.searchPossibleTargets(r, n);
					if (a.target ? (t = a.target, i = a.subTargets) : (a = this.searchPossibleTargets(this._objects, n), t = a.target, i = a.subTargets), !t || !t.selectable) return !1;
				}
				t.group === n ? (n.remove(t), this._hoveredTarget = t, this._hoveredTargets = i, n.size() === 1 && this._setActiveObject(n.item(0), e)) : (n.multiSelectAdd(t), this._hoveredTarget = n, this._hoveredTargets = i), this._fireSelectionEvents(r, e);
			} else {
				n.isEditing && n.exitEditing();
				let r = new (K.getClass("ActiveSelection"))([], { canvas: this });
				r.multiSelectAdd(n, t), this._hoveredTarget = r, this._setActiveObject(r, e), this._fireSelectionEvents([n], e);
			}
			return !0;
		}
		return !1;
	}
	handleSelection(e) {
		if (!this.selection || !this._groupSelector) return !1;
		let { x: t, y: n, deltaX: r, deltaY: i } = this._groupSelector, a = new q(t, n), o = a.add(new q(r, i)), s = a.min(o), c = a.max(o).subtract(s), l = this.collectObjects({
			left: s.x,
			top: s.y,
			width: c.x,
			height: c.y
		}, { includeIntersecting: !this.selectionFullyContained }), u = a.eq(o) ? l[0] ? [l[0]] : [] : l.length > 1 ? l.filter((t) => !t.onSelect({ e })).reverse() : l;
		if (u.length === 1) this.setActiveObject(u[0], e);
		else if (u.length > 1) {
			let t = K.getClass("ActiveSelection");
			this.setActiveObject(new t(u, { canvas: this }), e);
		}
		return this._groupSelector = null, !0;
	}
	toCanvasElement(e = 1, t) {
		let { upper: n } = this.elements;
		n.ctx = void 0;
		let r = super.toCanvasElement(e, t);
		return n.ctx = n.el.getContext("2d"), r;
	}
	clear() {
		this.textEditingManager.clear(), super.clear();
	}
	destroy() {
		this.removeListeners(), this.textEditingManager.dispose(), super.destroy();
	}
}, el = {
	x1: 0,
	y1: 0,
	x2: 0,
	y2: 0
}, tl = {
	...el,
	r1: 0,
	r2: 0
}, nl = (e, t) => isNaN(e) && typeof t == "number" ? t : e;
function rl(e) {
	return e && /%$/.test(e) && Number.isFinite(parseFloat(e));
}
function il(e, t) {
	return Sa(0, nl(typeof e == "number" ? e : typeof e == "string" ? parseFloat(e) / (rl(e) ? 100 : 1) : NaN, t), 1);
}
var al = /\s*;\s*/, ol = /\s*:\s*/;
function sl(e, t) {
	let n, r, i = e.getAttribute("style");
	if (i) {
		let e = i.split(al);
		e[e.length - 1] === "" && e.pop();
		for (let t = e.length; t--;) {
			let [i, a] = e[t].split(ol).map((e) => e.trim());
			i === "stop-color" ? n = a : i === "stop-opacity" && (r = a);
		}
	}
	n = n || e.getAttribute("stop-color") || "rgb(0,0,0)", r = nl(parseFloat(r || e.getAttribute("stop-opacity") || ""), 1);
	let a = new Xi(n);
	return a.setAlpha(a.getAlpha() * r * t), {
		offset: il(e.getAttribute("offset"), 0),
		color: a.toRgba()
	};
}
function cl(e, t) {
	let n = [], r = e.getElementsByTagName("stop"), i = il(t, 1);
	for (let e = r.length; e--;) n.push(sl(r[e], i));
	return n;
}
function ll(e) {
	return e.nodeName === "linearGradient" || e.nodeName === "LINEARGRADIENT" ? "linear" : "radial";
}
function ul(e) {
	return e.getAttribute("gradientUnits") === "userSpaceOnUse" ? "pixels" : "percentage";
}
function dl(e, t) {
	return e.getAttribute(t);
}
function fl(e, t) {
	return function(e, { width: t, height: n, gradientUnits: r }) {
		let i;
		return Object.entries(e).reduce((e, [a, o]) => {
			if (o === "Infinity") i = 1;
			else if (o === "-Infinity") i = 0;
			else {
				let e = typeof o == "string";
				i = e ? parseFloat(o) : o, e && rl(o) && (i *= .01, r === "pixels" && (a !== "x1" && a !== "x2" && a !== "r2" || (i *= t), a !== "y1" && a !== "y2" || (i *= n)));
			}
			return e[a] = i, e;
		}, {});
	}(ll(e) === "linear" ? function(e) {
		return {
			x1: dl(e, "x1") || 0,
			y1: dl(e, "y1") || 0,
			x2: dl(e, "x2") || "100%",
			y2: dl(e, "y2") || 0
		};
	}(e) : function(e) {
		return {
			x1: dl(e, "fx") || dl(e, "cx") || "50%",
			y1: dl(e, "fy") || dl(e, "cy") || "50%",
			r1: 0,
			x2: dl(e, "cx") || "50%",
			y2: dl(e, "cy") || "50%",
			r2: dl(e, "r") || "50%"
		};
	}(e), {
		...t,
		gradientUnits: ul(e)
	});
}
var pl = class {
	constructor(e) {
		let { type: t = "linear", gradientUnits: n = "pixels", coords: r = {}, colorStops: i = [], offsetX: a = 0, offsetY: o = 0, gradientTransform: s, id: c } = e || {};
		Object.assign(this, {
			type: t,
			gradientUnits: n,
			coords: {
				...t === "radial" ? tl : el,
				...r
			},
			colorStops: i,
			offsetX: a,
			offsetY: o,
			gradientTransform: s,
			id: c ? `${c}_${cr()}` : cr()
		});
	}
	addColorStop(e) {
		for (let t in e) this.colorStops.push({
			offset: parseFloat(t),
			color: e[t]
		});
		return this;
	}
	toObject(e) {
		return {
			...Fr(this, e),
			type: this.type,
			coords: { ...this.coords },
			colorStops: this.colorStops.map((e) => ({ ...e })),
			offsetX: this.offsetX,
			offsetY: this.offsetY,
			gradientUnits: this.gradientUnits,
			gradientTransform: this.gradientTransform ? [...this.gradientTransform] : void 0
		};
	}
	toSVG(e, { additionalTransform: t } = {}) {
		let n = [], r = this.gradientTransform ? this.gradientTransform.concat() : Dn.concat(), i = this.gradientUnits === "pixels" ? "userSpaceOnUse" : "objectBoundingBox", a = this.colorStops.map((e) => ({ ...e })).sort((e, t) => e.offset - t.offset), o = -this.offsetX, s = -this.offsetY;
		var c;
		i === "objectBoundingBox" ? (o /= e.width, s /= e.height) : (o += e.width / 2, s += e.height / 2), (c = e) && typeof c._renderPathCommands == "function" && this.gradientUnits !== "percentage" && (o -= e.pathOffset.x, s -= e.pathOffset.y), r[4] -= o, r[5] -= s;
		let l = [
			`id="SVGID_${Z(String(this.id))}"`,
			`gradientUnits="${i}"`,
			`gradientTransform="${t ? t + " " : ""}${Lr(r)}"`,
			""
		].join(" "), u = (e) => parseFloat(String(e));
		if (this.type === "linear") {
			let { x1: e, y1: t, x2: r, y2: i } = this.coords, a = u(e), o = u(t), s = u(r), c = u(i);
			n.push("<linearGradient ", l, " x1=\"", a, "\" y1=\"", o, "\" x2=\"", s, "\" y2=\"", c, "\">\n");
		} else if (this.type === "radial") {
			let { x1: e, y1: t, x2: r, y2: i, r1: o, r2: s } = this.coords, c = u(e), d = u(t), f = u(r), p = u(i), m = u(o), h = u(s), g = m > h;
			n.push("<radialGradient ", l, " cx=\"", g ? c : f, "\" cy=\"", g ? d : p, "\" r=\"", g ? m : h, "\" fx=\"", g ? f : c, "\" fy=\"", g ? p : d, "\">\n"), g && (a.reverse(), a.forEach((e) => {
				e.offset = 1 - e.offset;
			}));
			let _ = Math.min(m, h);
			if (_ > 0) {
				let e = _ / Math.max(m, h);
				a.forEach((t) => {
					t.offset += e * (1 - t.offset);
				});
			}
		}
		return a.forEach(({ color: e, offset: t }) => {
			let r = String(e), i = Bi(r) ? r : new Xi(r).toRgba();
			n.push(`<stop offset="${100 * t}%" style="stop-color:${Z(i)};"/>\n`);
		}), n.push(this.type === "linear" ? "</linearGradient>" : "</radialGradient>", "\n"), n.join("");
	}
	toLive(e) {
		let { x1: t, y1: n, x2: r, y2: i, r1: a, r2: o } = this.coords, s = this.type === "linear" ? e.createLinearGradient(t, n, r, i) : e.createRadialGradient(t, n, a, r, i, o);
		return this.colorStops.forEach(({ color: e, offset: t }) => {
			s.addColorStop(t, e);
		}), s;
	}
	static async fromObject(e) {
		let { colorStops: t, gradientTransform: n } = e;
		return new this({
			...e,
			colorStops: t ? t.map((e) => ({ ...e })) : void 0,
			gradientTransform: n ? [...n] : void 0
		});
	}
	static fromElement(e, t, n) {
		let r = ul(e), i = t._findCenterFromElement();
		return new this({
			id: e.getAttribute("id") || void 0,
			type: ll(e),
			coords: fl(e, {
				width: n.viewBoxWidth || n.width,
				height: n.viewBoxHeight || n.height
			}),
			colorStops: cl(e, n.opacity),
			gradientUnits: r,
			gradientTransform: js(e.getAttribute("gradientTransform") || ""),
			...r === "pixels" ? {
				offsetX: t.width / 2 - i.x,
				offsetY: t.height / 2 - i.y
			} : {
				offsetX: 0,
				offsetY: 0
			}
		});
	}
};
H(pl, "type", "Gradient"), K.setClass(pl, "gradient"), K.setClass(pl, "linear"), K.setClass(pl, "radial");
var ml = class {
	get type() {
		return "pattern";
	}
	set type(e) {
		ln("warn", "Setting type has no effect", e);
	}
	constructor(e) {
		H(this, "repeat", "repeat"), H(this, "offsetX", 0), H(this, "offsetY", 0), H(this, "crossOrigin", ""), this.id = cr(), Object.assign(this, e);
	}
	isImageSource() {
		return !!this.source && typeof this.source.src == "string";
	}
	isCanvasSource() {
		return !!this.source && !!this.source.toDataURL;
	}
	sourceToString() {
		return this.isImageSource() ? this.source.src : this.isCanvasSource() ? this.source.toDataURL() : "";
	}
	toLive(e) {
		return this.source && (!this.isImageSource() || this.source.complete && this.source.naturalWidth !== 0 && this.source.naturalHeight !== 0) ? e.createPattern(this.source, this.repeat) : null;
	}
	toObject(e = []) {
		let { repeat: t, crossOrigin: n } = this;
		return {
			...Fr(this, e),
			type: "pattern",
			source: this.sourceToString(),
			repeat: t,
			crossOrigin: n,
			offsetX: X(this.offsetX, U.NUM_FRACTION_DIGITS),
			offsetY: X(this.offsetY, U.NUM_FRACTION_DIGITS),
			patternTransform: this.patternTransform ? [...this.patternTransform] : null
		};
	}
	toSVG({ width: e, height: t }) {
		let { source: n, repeat: r, id: i } = this, a = nl(this.offsetX / e, 0), o = nl(this.offsetY / t, 0), s = r === "repeat-y" || r === "no-repeat" ? 1 + Math.abs(a || 0) : nl(n.width / e, 0), c = r === "repeat-x" || r === "no-repeat" ? 1 + Math.abs(o || 0) : nl(n.height / t, 0);
		return [
			`<pattern id="SVGID_${Z(i)}" x="${a}" y="${o}" width="${s}" height="${c}">`,
			`<image x="0" y="0" width="${n.width}" height="${n.height}" xlink:href="${Z(this.sourceToString())}"></image>`,
			"</pattern>",
			""
		].join("\n");
	}
	static async fromObject({ type: e, source: t, patternTransform: n, ...r }, i) {
		let a = await Mr(t, {
			...i,
			crossOrigin: r.crossOrigin
		});
		return new this({
			...r,
			patternTransform: n && n.slice(0),
			source: a
		});
	}
};
H(ml, "type", "Pattern"), K.setClass(ml), K.setClass(ml, "pattern");
var hl = class e extends ns {
	constructor(t, { path: n, left: r, top: i, ...a } = {}) {
		super(), Object.assign(this, e.ownDefaults), this.setOptions(a), this._setPath(t || [], !0), typeof r == "number" && this.set("left", r), typeof i == "number" && this.set("top", i);
	}
	_setPath(e, t) {
		this.path = ac(Array.isArray(e) ? e : Sc(e)), this.setBoundingBox(t);
	}
	_findCenterFromElement() {
		let e = this._calcBoundsFromPath();
		return new q(e.left + e.width / 2, e.top + e.height / 2);
	}
	_renderPathCommands(e) {
		let t = -this.pathOffset.x, n = -this.pathOffset.y;
		e.beginPath();
		for (let r of this.path) switch (r[0]) {
			case "L":
				e.lineTo(r[1] + t, r[2] + n);
				break;
			case "M":
				e.moveTo(r[1] + t, r[2] + n);
				break;
			case "C":
				e.bezierCurveTo(r[1] + t, r[2] + n, r[3] + t, r[4] + n, r[5] + t, r[6] + n);
				break;
			case "Q":
				e.quadraticCurveTo(r[1] + t, r[2] + n, r[3] + t, r[4] + n);
				break;
			case "Z": e.closePath();
		}
	}
	_render(e) {
		this._renderPathCommands(e), this._renderPaintInOrder(e);
	}
	toString() {
		return `#<Path (${this.complexity()}): { "top": ${this.top}, "left": ${this.left} }>`;
	}
	toObject(e = []) {
		return {
			...super.toObject(e),
			path: this.path.map((e) => e.slice())
		};
	}
	toDatalessObject(e = []) {
		let t = this.toObject(e);
		return this.sourcePath && (delete t.path, t.sourcePath = this.sourcePath), t;
	}
	_toSVG() {
		return [
			"<path ",
			"COMMON_PARTS",
			`d="${Ec(this.path, U.NUM_FRACTION_DIGITS)}" stroke-linecap="round" />\n`
		];
	}
	_getOffsetTransform() {
		let e = U.NUM_FRACTION_DIGITS;
		return ` translate(${X(-this.pathOffset.x, e)}, ${X(-this.pathOffset.y, e)})`;
	}
	toClipPathSVG(e) {
		let t = this._getOffsetTransform();
		return "	" + this._createBaseClipPathSVGMarkup(this._toSVG(), {
			reviver: e,
			additionalTransform: t
		});
	}
	toSVG(e) {
		let t = this._getOffsetTransform();
		return this._createBaseSVGMarkup(this._toSVG(), {
			reviver: e,
			additionalTransform: t
		});
	}
	complexity() {
		return this.path.length;
	}
	setDimensions() {
		this.setBoundingBox();
	}
	setBoundingBox(e) {
		let { width: t, height: n, pathOffset: r } = this._calcDimensions();
		this.set({
			width: t,
			height: n,
			pathOffset: r
		}), e && this.setPositionByOrigin(r, "center", "center");
	}
	_calcBoundsFromPath() {
		let e = [], t = 0, n = 0, r = 0, i = 0;
		for (let a of this.path) switch (a[0]) {
			case "L":
				r = a[1], i = a[2], e.push({
					x: t,
					y: n
				}, {
					x: r,
					y: i
				});
				break;
			case "M":
				r = a[1], i = a[2], t = r, n = i;
				break;
			case "C":
				e.push(...rc(r, i, a[1], a[2], a[3], a[4], a[5], a[6])), r = a[5], i = a[6];
				break;
			case "Q":
				e.push(...rc(r, i, a[1], a[2], a[1], a[2], a[3], a[4])), r = a[3], i = a[4];
				break;
			case "Z": r = t, i = n;
		}
		return si(e);
	}
	_calcDimensions() {
		let e = this._calcBoundsFromPath();
		return {
			...e,
			pathOffset: new q(e.left + e.width / 2, e.top + e.height / 2)
		};
	}
	static fromObject(e) {
		return this._fromObject(e, { extraParam: "path" });
	}
	static async fromElement(e, t, n) {
		let { d: r, ...i } = Is(e, this.ATTRIBUTE_NAMES, n);
		return new this(r, {
			...i,
			...t,
			left: void 0,
			top: void 0
		});
	}
};
H(hl, "type", "Path"), H(hl, "cacheProperties", [
	...wa,
	"path",
	"fillRule"
]), H(hl, "ATTRIBUTE_NAMES", [...ps, "d"]), K.setClass(hl), K.setSVGClass(hl);
var gl = [
	"radius",
	"startAngle",
	"endAngle",
	"counterClockwise"
], _l = class e extends ns {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t) {
		super(), Object.assign(this, e.ownDefaults), this.setOptions(t);
	}
	_set(e, t) {
		return super._set(e, t), e === "radius" && this.setRadius(t), this;
	}
	_render(e) {
		e.beginPath(), e.arc(0, 0, this.radius, J(this.startAngle), J(this.endAngle), this.counterClockwise), this._renderPaintInOrder(e);
	}
	getRadiusX() {
		return this.get("radius") * this.get(Vn);
	}
	getRadiusY() {
		return this.get("radius") * this.get(Hn);
	}
	setRadius(e) {
		this.radius = e, this.set({
			width: 2 * e,
			height: 2 * e
		});
	}
	toObject(e = []) {
		return super.toObject([...gl, ...e]);
	}
	_toSVG() {
		let { radius: e, startAngle: t, endAngle: n } = this, r = (n - t) % 360;
		if (r === 0) return [
			"<circle ",
			"COMMON_PARTS",
			"cx=\"0\" cy=\"0\" ",
			"r=\"",
			`${Z(e)}`,
			"\" />\n"
		];
		{
			let i = J(t), a = J(n), o = $n(i) * e, s = er(i) * e, c = $n(a) * e, l = er(a) * e;
			return [
				`<path d="M ${o} ${s} A ${e} ${e} 0 ${+(r > 180)} ${+!this.counterClockwise} ${c} ${l}" `,
				"COMMON_PARTS",
				" />\n"
			];
		}
	}
	static async fromElement(e, t, n) {
		let { left: r = 0, top: i = 0, radius: a = 0, ...o } = Is(e, this.ATTRIBUTE_NAMES, n);
		return new this({
			...o,
			radius: a,
			left: r - a,
			top: i - a
		});
	}
	static fromObject(e) {
		return super._fromObject(e);
	}
};
H(_l, "type", "Circle"), H(_l, "cacheProperties", [...wa, ...gl]), H(_l, "ownDefaults", {
	radius: 0,
	startAngle: 0,
	endAngle: 360,
	counterClockwise: !1
}), H(_l, "ATTRIBUTE_NAMES", [
	"cx",
	"cy",
	"r",
	...ps
]), K.setClass(_l), K.setSVGClass(_l);
var vl = [
	"x1",
	"x2",
	"y1",
	"y2"
], yl = class e extends ns {
	constructor([t, n, r, i] = [
		0,
		0,
		0,
		0
	], a = {}) {
		super(), Object.assign(this, e.ownDefaults), this.setOptions(a), this.x1 = t, this.x2 = r, this.y1 = n, this.y2 = i, this._setWidthHeight();
		let { left: o, top: s } = a;
		typeof o == "number" && this.set("left", o), typeof s == "number" && this.set("top", s);
	}
	_setWidthHeight() {
		let { x1: e, y1: t, x2: n, y2: r } = this;
		this.width = Math.abs(n - e), this.height = Math.abs(r - t);
		let { left: i, top: a, width: o, height: s } = si([{
			x: e,
			y: t
		}, {
			x: n,
			y: r
		}]), c = new q(i + o / 2, a + s / 2);
		this.setPositionByOrigin(c, W, W);
	}
	_set(e, t) {
		return super._set(e, t), vl.includes(e) && this._setWidthHeight(), this;
	}
	_render(e) {
		e.beginPath();
		let t = this.calcLinePoints();
		e.moveTo(t.x1, t.y1), e.lineTo(t.x2, t.y2), e.lineWidth = this.strokeWidth;
		let n = e.strokeStyle;
		Rr(this.stroke) ? e.strokeStyle = this.stroke.toLive(e) : e.strokeStyle = this.stroke ?? e.fillStyle, this.stroke && this._renderStroke(e), e.strokeStyle = n;
	}
	_findCenterFromElement() {
		return new q((this.x1 + this.x2) / 2, (this.y1 + this.y2) / 2);
	}
	toObject(e = []) {
		return {
			...super.toObject(e),
			...this.calcLinePoints()
		};
	}
	_getNonTransformedDimensions() {
		let e = super._getNonTransformedDimensions();
		return this.strokeLineCap === "butt" && (this.width === 0 && (e.y -= this.strokeWidth), this.height === 0 && (e.x -= this.strokeWidth)), e;
	}
	calcLinePoints() {
		let { x1: e, x2: t, y1: n, y2: r, width: i, height: a } = this, o = e <= t ? -.5 : .5, s = n <= r ? -.5 : .5;
		return {
			x1: o * i,
			x2: o * -i,
			y1: s * a,
			y2: s * -a
		};
	}
	_toSVG() {
		let { x1: e, x2: t, y1: n, y2: r } = this.calcLinePoints();
		return [
			"<line ",
			"COMMON_PARTS",
			`x1="${e}" y1="${n}" x2="${t}" y2="${r}" />\n`
		];
	}
	static async fromElement(e, t, n) {
		let { x1: r = 0, y1: i = 0, x2: a = 0, y2: o = 0, ...s } = Is(e, this.ATTRIBUTE_NAMES, n);
		return new this([
			r,
			i,
			a,
			o
		], s);
	}
	static fromObject({ x1: e, y1: t, x2: n, y2: r, ...i }) {
		return this._fromObject({
			...i,
			points: [
				e,
				t,
				n,
				r
			]
		}, { extraParam: "points" });
	}
};
H(yl, "type", "Line"), H(yl, "cacheProperties", [...wa, ...vl]), H(yl, "ATTRIBUTE_NAMES", ps.concat(vl)), K.setClass(yl), K.setSVGClass(yl);
var bl = class e extends ns {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t) {
		super(), Object.assign(this, e.ownDefaults), this.setOptions(t);
	}
	_render(e) {
		let t = this.width / 2, n = this.height / 2;
		e.beginPath(), e.moveTo(-t, n), e.lineTo(0, -n), e.lineTo(t, n), e.closePath(), this._renderPaintInOrder(e);
	}
	_toSVG() {
		let e = this.width / 2, t = this.height / 2;
		return [
			"<polygon ",
			"COMMON_PARTS",
			"points=\"",
			`${-e} ${t},0 ${-t},${e} ${t}`,
			"\" />"
		];
	}
};
H(bl, "type", "Triangle"), H(bl, "ownDefaults", {
	width: 100,
	height: 100
}), K.setClass(bl), K.setSVGClass(bl);
var xl = ["rx", "ry"], Sl = class e extends ns {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t) {
		super(), Object.assign(this, e.ownDefaults), this.setOptions(t);
	}
	_set(e, t) {
		switch (super._set(e, t), e) {
			case "rx":
				this.rx = t, this.set("width", 2 * t);
				break;
			case "ry": this.ry = t, this.set("height", 2 * t);
		}
		return this;
	}
	getRx() {
		return this.get("rx") * this.get(Vn);
	}
	getRy() {
		return this.get("ry") * this.get(Hn);
	}
	toObject(e = []) {
		return super.toObject([...xl, ...e]);
	}
	_toSVG() {
		return [
			"<ellipse ",
			"COMMON_PARTS",
			`cx="0" cy="0" rx="${Z(this.rx)}" ry="${Z(this.ry)}" />\n`
		];
	}
	_render(e) {
		e.beginPath(), e.save(), e.transform(1, 0, 0, this.ry / this.rx, 0, 0), e.arc(0, 0, this.rx, 0, Tn, !1), e.restore(), this._renderPaintInOrder(e);
	}
	static async fromElement(e, t, n) {
		let r = Is(e, this.ATTRIBUTE_NAMES, n);
		return r.left = (r.left || 0) - r.rx, r.top = (r.top || 0) - r.ry, new this(r);
	}
};
H(Sl, "type", "Ellipse"), H(Sl, "cacheProperties", [...wa, ...xl]), H(Sl, "ownDefaults", {
	rx: 0,
	ry: 0
}), H(Sl, "ATTRIBUTE_NAMES", [
	...ps,
	"cx",
	"cy",
	"rx",
	"ry"
]), K.setClass(Sl), K.setSVGClass(Sl);
var Cl = { exactBoundingBox: !1 }, wl = class e extends ns {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t = [], n = {}) {
		super(), H(this, "strokeDiff", void 0), Object.assign(this, e.ownDefaults), this.setOptions(n), this.points = t;
		let { left: r, top: i } = n;
		this.initialized = !0, this.setBoundingBox(!0), typeof r == "number" && this.set("left", r), typeof i == "number" && this.set("top", i);
	}
	isOpen() {
		return !0;
	}
	_projectStrokeOnPoints(e) {
		return cs(this.points, e, this.isOpen());
	}
	_calcDimensions(e) {
		e = {
			scaleX: this.scaleX,
			scaleY: this.scaleY,
			skewX: this.skewX,
			skewY: this.skewY,
			strokeLineCap: this.strokeLineCap,
			strokeLineJoin: this.strokeLineJoin,
			strokeMiterLimit: this.strokeMiterLimit,
			strokeUniform: this.strokeUniform,
			strokeWidth: this.strokeWidth,
			...e || {}
		};
		let t = this.exactBoundingBox ? this._projectStrokeOnPoints(e).map((e) => e.projectedPoint) : this.points;
		if (t.length === 0) return {
			left: 0,
			top: 0,
			width: 0,
			height: 0,
			pathOffset: new q(),
			strokeOffset: new q(),
			strokeDiff: new q()
		};
		let n = si(t), r = Ar({
			...e,
			scaleX: 1,
			scaleY: 1
		}), i = si(this.points.map((e) => _r(e, r, !0))), a = new q(this.scaleX, this.scaleY), o = n.left + n.width / 2, s = n.top + n.height / 2;
		return this.exactBoundingBox && (o -= s * Math.tan(J(this.skewX)), s -= o * Math.tan(J(this.skewY))), {
			...n,
			pathOffset: new q(o, s),
			strokeOffset: new q(i.left, i.top).subtract(new q(n.left, n.top)).multiply(a),
			strokeDiff: new q(n.width, n.height).subtract(new q(i.width, i.height)).multiply(a)
		};
	}
	_findCenterFromElement() {
		let e = si(this.points);
		return new q(e.left + e.width / 2, e.top + e.height / 2);
	}
	setDimensions() {
		this.setBoundingBox();
	}
	setBoundingBox(e) {
		let { left: t, top: n, width: r, height: i, pathOffset: a, strokeOffset: o, strokeDiff: s } = this._calcDimensions();
		this.set({
			width: r,
			height: i,
			pathOffset: a,
			strokeOffset: o,
			strokeDiff: s
		}), e && this.setPositionByOrigin(new q(t + r / 2, n + i / 2), "center", "center");
	}
	isStrokeAccountedForInDimensions() {
		return this.exactBoundingBox;
	}
	_getNonTransformedDimensions() {
		return this.exactBoundingBox ? new q(this.width, this.height) : super._getNonTransformedDimensions();
	}
	_getTransformedDimensions(e = {}) {
		if (this.exactBoundingBox) {
			let t;
			if (Object.keys(e).some((e) => this.strokeUniform || this.constructor.layoutProperties.includes(e))) {
				let { width: n, height: r } = this._calcDimensions(e);
				t = new q(e.width ?? n, e.height ?? r);
			} else t = new q(e.width ?? this.width, e.height ?? this.height);
			return t.multiply(new q(e.scaleX || this.scaleX, e.scaleY || this.scaleY));
		}
		return super._getTransformedDimensions(e);
	}
	_set(e, t) {
		let n = this.initialized && this[e] !== t, r = super._set(e, t);
		return this.exactBoundingBox && n && ((e === "scaleX" || e === "scaleY") && this.strokeUniform && this.constructor.layoutProperties.includes("strokeUniform") || this.constructor.layoutProperties.includes(e)) && this.setDimensions(), r;
	}
	toObject(e = []) {
		return {
			...super.toObject(e),
			points: this.points.map(({ x: e, y: t }) => ({
				x: e,
				y: t
			}))
		};
	}
	_toSVG() {
		let e = this.pathOffset.x, t = this.pathOffset.y, n = U.NUM_FRACTION_DIGITS, r = this.points.map(({ x: r, y: i }) => `${X(r - e, n)},${X(i - t, n)}`).join(" ");
		return [
			`<${Z(this.constructor.type).toLowerCase()} `,
			"COMMON_PARTS",
			`points="${r}" />\n`
		];
	}
	_render(e) {
		let t = this.points.length, n = this.pathOffset.x, r = this.pathOffset.y;
		if (t && !isNaN(this.points[t - 1].y)) {
			e.beginPath(), e.moveTo(this.points[0].x - n, this.points[0].y - r);
			for (let i = 0; i < t; i++) {
				let t = this.points[i];
				e.lineTo(t.x - n, t.y - r);
			}
			!this.isOpen() && e.closePath(), this._renderPaintInOrder(e);
		}
	}
	complexity() {
		return this.points.length;
	}
	static async fromElement(e, t, n) {
		let r = function(e) {
			if (!e) return [];
			let t = e.replace(/,/g, " ").trim().split(/\s+/), n = [];
			for (let e = 0; e < t.length; e += 2) n.push({
				x: parseFloat(t[e]),
				y: parseFloat(t[e + 1])
			});
			return n;
		}(e.getAttribute("points")), { left: i, top: a, ...o } = Is(e, this.ATTRIBUTE_NAMES, n);
		return new this(r, {
			...o,
			...t
		});
	}
	static fromObject(e) {
		return this._fromObject(e, { extraParam: "points" });
	}
};
H(wl, "ownDefaults", Cl), H(wl, "type", "Polyline"), H(wl, "layoutProperties", [
	Un,
	Wn,
	"strokeLineCap",
	"strokeLineJoin",
	"strokeMiterLimit",
	"strokeWidth",
	"strokeUniform",
	"points"
]), H(wl, "cacheProperties", [...wa, "points"]), H(wl, "ATTRIBUTE_NAMES", [...ps]), K.setClass(wl), K.setSVGClass(wl);
var Tl = class extends wl {
	isOpen() {
		return !1;
	}
};
H(Tl, "ownDefaults", Cl), H(Tl, "type", "Polygon"), K.setClass(Tl), K.setSVGClass(Tl);
var El = class extends ns {
	isEmptyStyles(e) {
		if (!this.styles || e !== void 0 && !this.styles[e]) return !0;
		let t = e === void 0 ? this.styles : { line: this.styles[e] };
		for (let e in t) for (let n in t[e]) for (let r in t[e][n]) return !1;
		return !0;
	}
	styleHas(e, t) {
		if (!this.styles || t !== void 0 && !this.styles[t]) return !1;
		let n = t === void 0 ? this.styles : { 0: this.styles[t] };
		for (let t in n) for (let r in n[t]) if (n[t][r][e] !== void 0) return !0;
		return !1;
	}
	cleanStyle(e) {
		if (!this.styles) return !1;
		let t = this.styles, n, r, i = 0, a = !0, o = 0;
		for (let o in t) {
			n = 0;
			for (let s in t[o]) {
				let c = t[o][s] || {};
				i++, c[e] === void 0 ? a = !1 : (r ? c[e] !== r && (a = !1) : r = c[e], c[e] === this[e] && delete c[e]), Object.keys(c).length === 0 ? delete t[o][s] : n++;
			}
			n === 0 && delete t[o];
		}
		for (let e = 0; e < this._textLines.length; e++) o += this._textLines[e].length;
		a && i === o && (this[e] = r, this.removeStyle(e));
	}
	removeStyle(e) {
		if (!this.styles) return;
		let t = this.styles, n, r, i;
		for (r in t) {
			for (i in n = t[r], n) delete n[i][e], Object.keys(n[i]).length === 0 && delete n[i];
			Object.keys(n).length === 0 && delete t[r];
		}
	}
	_extendStyles(e, t) {
		let { lineIndex: n, charIndex: r } = this.get2DCursorLocation(e);
		this._getLineStyle(n) || this._setLineStyle(n);
		let i = Ir({
			...this._getStyleDeclaration(n, r),
			...t
		}, (e) => e !== void 0);
		this._setStyleDeclaration(n, r, i);
	}
	getSelectionStyles(e, t, n) {
		let r = [];
		for (let i = e; i < (t || e); i++) r.push(this.getStyleAtPosition(i, n));
		return r;
	}
	getStyleAtPosition(e, t) {
		let { lineIndex: n, charIndex: r } = this.get2DCursorLocation(e);
		return t ? this.getCompleteStyleDeclaration(n, r) : this._getStyleDeclaration(n, r);
	}
	setSelectionStyles(e, t, n) {
		for (let r = t; r < (n || t); r++) this._extendStyles(r, e);
		this._forceClearCache = !0;
	}
	_getStyleDeclaration(e, t) {
		var n;
		let r = this.styles && this.styles[e];
		return r && (n = r[t]) != null ? n : {};
	}
	getCompleteStyleDeclaration(e, t) {
		return {
			...Fr(this, this.constructor._styleProperties),
			...this._getStyleDeclaration(e, t)
		};
	}
	_setStyleDeclaration(e, t, n) {
		this.styles[e][t] = n;
	}
	_deleteStyleDeclaration(e, t) {
		delete this.styles[e][t];
	}
	_getLineStyle(e) {
		return !!this.styles[e];
	}
	_setLineStyle(e) {
		this.styles[e] = {};
	}
	_deleteLineStyle(e) {
		delete this.styles[e];
	}
};
H(El, "_styleProperties", la);
var Dl = /  +/g, Ol = /"/g;
function kl(e, t, n, r, i) {
	return `\t\t${((e, { left: t, top: n, width: r, height: i }, a = U.NUM_FRACTION_DIGITS) => {
		let o = ea(Gn, e, !1), [s, c, l, u] = [
			t,
			n,
			r,
			i
		].map((e) => X(e, a));
		return `<rect ${o} x="${s}" y="${c}" width="${l}" height="${u}"></rect>`;
	})(e, {
		left: t,
		top: n,
		width: r,
		height: i
	})}\n`;
}
var Al, jl = class e extends El {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t, n) {
		super(), H(this, "__charBounds", []), Object.assign(this, e.ownDefaults), this.setOptions(n), this.styles ||= {}, this.text = t, this.initialized = !0, this.path && this.setPathInfo(), this.initDimensions(), this.setCoords();
	}
	setPathInfo() {
		let e = this.path;
		e && (e.segmentsInfo = gc(e.path));
	}
	_splitText() {
		let e = this._splitTextIntoLines(this.text);
		return this.textLines = e.lines, this._textLines = e.graphemeLines, this._unwrappedTextLines = e._unwrappedLines, this._text = e.graphemeText, e;
	}
	initDimensions() {
		this._splitText(), this._clearCache(), this.dirty = !0, this.path ? (this.width = this.path.width, this.height = this.path.height) : (this.width = this.calcTextWidth() || this.cursorWidth || this.MIN_TEXT_WIDTH, this.height = this.calcTextHeight()), this.textAlign.includes("justify") && this.enlargeSpaces();
	}
	enlargeSpaces() {
		let e, t, n, r, i, a, o;
		for (let s = 0, c = this._textLines.length; s < c; s++) if ((this.textAlign === "justify" || s !== c - 1 && !this.isEndOfWrapping(s)) && (r = 0, i = this._textLines[s], t = this.getLineWidth(s), t < this.width && (o = this.textLines[s].match(this._reSpacesAndTabs)))) {
			n = o.length, e = (this.width - t) / n;
			for (let t = 0; t <= i.length; t++) a = this.__charBounds[s][t], this._reSpaceAndTab.test(i[t]) ? (a.width += e, a.kernedWidth += e, a.left += r, r += e) : a.left += r;
		}
	}
	isEndOfWrapping(e) {
		return e === this._textLines.length - 1;
	}
	missingNewlineOffset(e) {
		return 1;
	}
	get2DCursorLocation(e, t) {
		let n = t ? this._unwrappedTextLines : this._textLines, r;
		for (r = 0; r < n.length; r++) {
			if (e <= n[r].length) return {
				lineIndex: r,
				charIndex: e
			};
			e -= n[r].length + this.missingNewlineOffset(r, t);
		}
		return {
			lineIndex: r - 1,
			charIndex: n[r - 1].length < e ? n[r - 1].length : e
		};
	}
	toString() {
		return `#<Text (${this.complexity()}): { "text": "${this.text}", "fontFamily": "${this.fontFamily}" }>`;
	}
	_getCacheCanvasDimensions() {
		let e = super._getCacheCanvasDimensions(), t = this.fontSize;
		return e.width += t * e.zoomX, e.height += t * e.zoomY, e;
	}
	_render(e) {
		let t = this.path;
		t && !t.isNotVisible() && t._render(e), this._setTextStyles(e), this._renderTextLinesBackground(e), this._renderTextDecoration(e, "underline"), this._renderText(e), this._renderTextDecoration(e, "overline"), this._renderTextDecoration(e, "linethrough");
	}
	_renderText(e) {
		this.paintFirst === "stroke" ? (this._renderTextStroke(e), this._renderTextFill(e)) : (this._renderTextFill(e), this._renderTextStroke(e));
	}
	_setTextStyles(e, t, n) {
		if (e.textBaseline = "alphabetic", this.path) switch (this.pathAlign) {
			case W:
				e.textBaseline = "middle";
				break;
			case "ascender":
				e.textBaseline = "top";
				break;
			case "descender": e.textBaseline = On;
		}
		e.font = this._getFontDeclaration(t, n);
	}
	calcTextWidth() {
		let e = this.getLineWidth(0);
		for (let t = 1, n = this._textLines.length; t < n; t++) {
			let n = this.getLineWidth(t);
			n > e && (e = n);
		}
		return e;
	}
	_renderTextLine(e, t, n, r, i, a) {
		this._renderChars(e, t, n, r, i, a);
	}
	_renderTextLinesBackground(e) {
		if (!this.textBackgroundColor && !this.styleHas("textBackgroundColor")) return;
		let t = e.fillStyle, n = this._getLeftOffset(), r = this._getTopOffset();
		for (let t = 0, i = this._textLines.length; t < i; t++) {
			let i = this.getHeightOfLine(t);
			if (!this.textBackgroundColor && !this.styleHas("textBackgroundColor", t)) {
				r += i;
				continue;
			}
			let a = this._textLines[t].length, o = this._getLineLeftOffset(t), s, c, l = 0, u = 0, d = this.getValueOfPropertyAt(t, 0, "textBackgroundColor"), f = this.getHeightOfLineImpl(t);
			for (let i = 0; i < a; i++) {
				let a = this.__charBounds[t][i];
				c = this.getValueOfPropertyAt(t, i, "textBackgroundColor"), this.path ? (e.save(), e.translate(a.renderLeft, a.renderTop), e.rotate(a.angle), e.fillStyle = c, c && e.fillRect(-a.width / 2, -f * (1 - this._fontSizeFraction), a.width, f), e.restore()) : c === d ? l += a.kernedWidth : (s = n + o + u, this.direction === "rtl" && (s = this.width - s - l), e.fillStyle = d, d && e.fillRect(s, r, l, f), u = a.left, l = a.width, d = c);
			}
			c && !this.path && (s = n + o + u, this.direction === "rtl" && (s = this.width - s - l), e.fillStyle = c, e.fillRect(s, r, l, f)), r += i;
		}
		e.fillStyle = t, this._removeShadow(e);
	}
	_measureChar(e, t, n, r) {
		let i = bn.getFontCache(t), a = this._getFontDeclaration(t), o = n ? n + e : e, s = n && a === this._getFontDeclaration(r), c = t.fontSize / this.CACHE_FONT_SIZE, l, u, d, f;
		if (n && i.has(n) && (d = i.get(n)), i.has(e) && (f = l = i.get(e)), s && i.has(o) && (u = i.get(o), f = u - d), l === void 0 || d === void 0 || u === void 0) {
			let r = (Al ||= fr({
				width: 0,
				height: 0
			}).getContext("2d"), Al);
			this._setTextStyles(r, t, !0), l === void 0 && (f = l = r.measureText(e).width, i.set(e, l)), d === void 0 && s && n && (d = r.measureText(n).width, i.set(n, d)), s && u === void 0 && (u = r.measureText(o).width, i.set(o, u), f = u - d);
		}
		return {
			width: l * c,
			kernedWidth: f * c
		};
	}
	getHeightOfChar(e, t) {
		return this.getValueOfPropertyAt(e, t, "fontSize");
	}
	measureLine(e) {
		let t = this._measureLine(e);
		return this.charSpacing !== 0 && (t.width -= this._getWidthOfCharSpacing()), t.width < 0 && (t.width = 0), t;
	}
	_measureLine(e) {
		let t, n, r = 0, i = this.pathSide === kn, a = this.path, o = this._textLines[e], s = o.length, c = Array(s);
		this.__charBounds[e] = c;
		for (let i = 0; i < s; i++) {
			let a = o[i];
			n = this._getGraphemeBox(a, e, i, t), c[i] = n, r += n.kernedWidth, t = a;
		}
		if (c[s] = {
			left: n ? n.left + n.width : 0,
			width: 0,
			kernedWidth: 0,
			height: this.fontSize,
			deltaY: 0
		}, a && a.segmentsInfo) {
			let e = 0, t = a.segmentsInfo[a.segmentsInfo.length - 1].length;
			switch (this.textAlign) {
				case G:
					e = i ? t - r : 0;
					break;
				case W:
					e = (t - r) / 2;
					break;
				case kn: e = i ? 0 : t - r;
			}
			e += this.pathStartOffset * (i ? -1 : 1);
			for (let r = i ? s - 1 : 0; i ? r >= 0 : r < s; i ? r-- : r++) n = c[r], e > t ? e %= t : e < 0 && (e += t), this._setGraphemeOnPath(e, n), e += n.kernedWidth;
		}
		return {
			width: r,
			numOfSpaces: 0
		};
	}
	_setGraphemeOnPath(e, t) {
		let n = e + t.kernedWidth / 2, r = this.path, i = _c(r.path, n, r.segmentsInfo);
		t.renderLeft = i.x - r.pathOffset.x, t.renderTop = i.y - r.pathOffset.y, t.angle = i.angle + (this.pathSide === "right" ? Math.PI : 0);
	}
	_getGraphemeBox(e, t, n, r, i) {
		let a = this.getCompleteStyleDeclaration(t, n), o = r ? this.getCompleteStyleDeclaration(t, n - 1) : {}, s = this._measureChar(e, a, r, o), c, l = s.kernedWidth, u = s.width;
		this.charSpacing !== 0 && (c = this._getWidthOfCharSpacing(), u += c, l += c);
		let d = {
			width: u,
			left: 0,
			height: a.fontSize,
			kernedWidth: l,
			deltaY: a.deltaY
		};
		if (n > 0 && !i) {
			let e = this.__charBounds[t][n - 1];
			d.left = e.left + e.width + s.kernedWidth - s.width;
		}
		return d;
	}
	getHeightOfLineImpl(e) {
		let t = this.__lineHeights;
		if (t[e]) return t[e];
		let n = this.getHeightOfChar(e, 0);
		for (let t = 1, r = this._textLines[e].length; t < r; t++) n = Math.max(this.getHeightOfChar(e, t), n);
		return t[e] = n * this._fontSizeMult;
	}
	getHeightOfLine(e) {
		return this.getHeightOfLineImpl(e) * this.lineHeight;
	}
	calcTextHeight() {
		let e = 0;
		for (let t = 0, n = this._textLines.length; t < n; t++) e += t === n - 1 ? this.getHeightOfLineImpl(t) : this.getHeightOfLine(t);
		return e;
	}
	_getLeftOffset() {
		return this.direction === "ltr" ? -this.width / 2 : this.width / 2;
	}
	_getTopOffset() {
		return -this.height / 2;
	}
	_renderTextCommon(e, t) {
		e.save();
		let n = 0, r = this._getLeftOffset(), i = this._getTopOffset();
		for (let a = 0, o = this._textLines.length; a < o; a++) this._renderTextLine(t, e, this._textLines[a], r + this._getLineLeftOffset(a), i + n + this.getHeightOfLineImpl(a), a), n += this.getHeightOfLine(a);
		e.restore();
	}
	_renderTextFill(e) {
		(this.fill || this.styleHas("fill")) && this._renderTextCommon(e, "fillText");
	}
	_renderTextStroke(e) {
		(this.stroke && this.strokeWidth !== 0 || !this.isEmptyStyles()) && (this.shadow && !this.shadow.affectStroke && this._removeShadow(e), e.save(), this._setLineDash(e, this.strokeDashArray), e.beginPath(), this._renderTextCommon(e, "strokeText"), e.closePath(), e.restore());
	}
	_renderChars(e, t, n, r, i, a) {
		let o = this.textAlign.includes(da), s = this.path, c = !o && this.charSpacing === 0 && this.isEmptyStyles(a) && !s, l = this.direction === "ltr", u = this.direction === "ltr" ? 1 : -1, d = t.direction, f, p, m, h, g, _ = "", v = 0;
		if (t.save(), d !== this.direction && (t.canvas.setAttribute("dir", l ? "ltr" : "rtl"), t.direction = l ? "ltr" : "rtl", t.textAlign = l ? G : kn), i -= this.getHeightOfLineImpl(a) * this._fontSizeFraction, c) return this._renderChar(e, t, a, 0, n.join(""), r, i), void t.restore();
		for (let c = 0, l = n.length - 1; c <= l; c++) h = c === l || this.charSpacing || s, _ += n[c], m = this.__charBounds[a][c], v === 0 ? (r += u * (m.kernedWidth - m.width), v += m.width) : v += m.kernedWidth, o && !h && this._reSpaceAndTab.test(n[c]) && (h = !0), h ||= (f ||= this.getCompleteStyleDeclaration(a, c), p = this.getCompleteStyleDeclaration(a, c + 1), us(f, p, !1)), h && (s ? (t.save(), t.translate(m.renderLeft, m.renderTop), t.rotate(m.angle), this._renderChar(e, t, a, c, _, -v / 2, 0), t.restore()) : (g = r, this._renderChar(e, t, a, c, _, g, i)), _ = "", f = p, r += u * v, v = 0);
		t.restore();
	}
	_applyPatternGradientTransformText(e) {
		let t = this.width + this.strokeWidth, n = this.height + this.strokeWidth, r = fr({
			width: t,
			height: n
		}), i = r.getContext("2d");
		return r.width = t, r.height = n, i.beginPath(), i.moveTo(0, 0), i.lineTo(t, 0), i.lineTo(t, n), i.lineTo(0, n), i.closePath(), i.translate(t / 2, n / 2), i.fillStyle = e.toLive(i), this._applyPatternGradientTransform(i, e), i.fill(), i.createPattern(r, "no-repeat");
	}
	handleFiller(e, t, n) {
		let r, i;
		return Rr(n) ? n.gradientUnits === "percentage" || n.gradientTransform || n.patternTransform ? (r = -this.width / 2, i = -this.height / 2, e.translate(r, i), e[t] = this._applyPatternGradientTransformText(n), {
			offsetX: r,
			offsetY: i
		}) : (e[t] = n.toLive(e), this._applyPatternGradientTransform(e, n)) : (e[t] = n, {
			offsetX: 0,
			offsetY: 0
		});
	}
	_setStrokeStyles(e, { stroke: t, strokeWidth: n }) {
		return e.lineWidth = n, e.lineCap = this.strokeLineCap, e.lineDashOffset = this.strokeDashOffset, e.lineJoin = this.strokeLineJoin, e.miterLimit = this.strokeMiterLimit, this.handleFiller(e, "strokeStyle", t);
	}
	_setFillStyles(e, { fill: t }) {
		return this.handleFiller(e, "fillStyle", t);
	}
	_renderChar(e, t, n, r, i, a, o) {
		let s = this._getStyleDeclaration(n, r), c = this.getCompleteStyleDeclaration(n, r), l = e === "fillText" && c.fill, u = e === "strokeText" && c.stroke && c.strokeWidth;
		if (u || l) {
			if (t.save(), t.font = this._getFontDeclaration(c), s.textBackgroundColor && this._removeShadow(t), s.deltaY && (o += s.deltaY), l) {
				let e = this._setFillStyles(t, c);
				t.fillText(i, a - e.offsetX, o - e.offsetY);
			}
			if (u) {
				let e = this._setStrokeStyles(t, c);
				t.strokeText(i, a - e.offsetX, o - e.offsetY);
			}
			t.restore();
		}
	}
	setSuperscript(e, t) {
		this._setScript(e, t, this.superscript);
	}
	setSubscript(e, t) {
		this._setScript(e, t, this.subscript);
	}
	_setScript(e, t, n) {
		let r = this.get2DCursorLocation(e, !0), i = this.getValueOfPropertyAt(r.lineIndex, r.charIndex, "fontSize"), a = this.getValueOfPropertyAt(r.lineIndex, r.charIndex, "deltaY"), o = {
			fontSize: i * n.size,
			deltaY: a + i * n.baseline
		};
		this.setSelectionStyles(o, e, t);
	}
	_getLineLeftOffset(e) {
		let t = this.getLineWidth(e), n = this.width - t, r = this.textAlign, i = this.direction, a = this.isEndOfWrapping(e), o = 0;
		return r === "justify" || r === "justify-center" && !a || r === "justify-right" && !a || r === "justify-left" && !a ? 0 : (r === "center" && (o = n / 2), r === "right" && (o = n), r === "justify-center" && (o = n / 2), r === "justify-right" && (o = n), i === "rtl" && (r === "right" || r === "justify-right" ? o = 0 : r === "left" || r === "justify-left" ? o = -n : r !== "center" && r !== "justify-center" || (o = -n / 2)), o);
	}
	_clearCache() {
		this._forceClearCache = !1, this.__lineWidths = [], this.__lineHeights = [], this.__charBounds = [];
	}
	getLineWidth(e) {
		if (this.__lineWidths[e] !== void 0) return this.__lineWidths[e];
		let { width: t } = this.measureLine(e);
		return this.__lineWidths[e] = t, t;
	}
	_getWidthOfCharSpacing() {
		return this.charSpacing === 0 ? 0 : this.fontSize * this.charSpacing / 1e3;
	}
	getValueOfPropertyAt(e, t, n) {
		return this._getStyleDeclaration(e, t)[n] ?? this[n];
	}
	_renderTextDecoration(e, t) {
		if (!this[t] && !this.styleHas(t)) return;
		let n = this._getTopOffset(), r = this._getLeftOffset(), i = this.path, a = this._getWidthOfCharSpacing(), o = t === "linethrough" ? .5 : +(t === "overline"), s = this.offsets[t];
		for (let c = 0, l = this._textLines.length; c < l; c++) {
			let l = this.getHeightOfLine(c);
			if (!this[t] && !this.styleHas(t, c)) {
				n += l;
				continue;
			}
			let u = this._textLines[c], d = l / this.lineHeight, f = this._getLineLeftOffset(c), p, m = 0, h = 0, g = this.getValueOfPropertyAt(c, 0, t), _ = this.getValueOfPropertyAt(c, 0, Gn), v = this.getValueOfPropertyAt(c, 0, "textDecorationColor") || _, y = this.getValueOfPropertyAt(c, 0, ra), b = g, x = v, S = y, C = n + d * (1 - this._fontSizeFraction), w = this.getHeightOfChar(c, 0), T = this.getValueOfPropertyAt(c, 0, "deltaY");
			for (let n = 0, a = u.length; n < a; n++) {
				let a = this.__charBounds[c][n];
				b = this.getValueOfPropertyAt(c, n, t), p = this.getValueOfPropertyAt(c, n, Gn), x = this.getValueOfPropertyAt(c, n, "textDecorationColor") || p, S = this.getValueOfPropertyAt(c, n, ra);
				let l = this.getHeightOfChar(c, n), u = this.getValueOfPropertyAt(c, n, "deltaY");
				if (i && b && p) {
					let t = this.fontSize * S / 1e3;
					e.save(), e.fillStyle = x, e.translate(a.renderLeft, a.renderTop), e.rotate(a.angle), e.fillRect(-a.kernedWidth / 2, s * l + u - o * t, a.kernedWidth, t), e.restore();
				} else if ((b !== g || p !== _ || x !== v || l !== w || S !== y || u !== T) && h > 0) {
					let t = this.fontSize * y / 1e3, n = r + f + m;
					this.direction === "rtl" && (n = this.width - n - h), g && v && y && (e.fillStyle = v, e.fillRect(n, C + s * w + T - o * t, h, t)), m = a.left, h = a.width, g = b, v = x, y = S, _ = p, w = l, T = u;
				} else h += a.kernedWidth;
			}
			let E = r + f + m;
			this.direction === "rtl" && (E = this.width - E - h), e.fillStyle = x;
			let D = this.fontSize * S / 1e3;
			b && x && S && e.fillRect(E, C + s * w + T - o * D, h - a, D), n += l;
		}
		this._removeShadow(e);
	}
	_getFontDeclaration({ fontFamily: t = this.fontFamily, fontStyle: n = this.fontStyle, fontWeight: r = this.fontWeight, fontSize: i = this.fontSize } = {}, a) {
		let o = t.includes("'") || t.includes("\"") || t.includes(",") || e.genericFonts.includes(t.toLowerCase()) ? t : `"${t}"`;
		return [
			n,
			r,
			`${a ? this.CACHE_FONT_SIZE : i}px`,
			o
		].join(" ");
	}
	render(e) {
		this.visible && (this.canvas && this.canvas.skipOffscreen && !this.group && !this.isOnScreen() || (this._forceClearCache && this.initDimensions(), super.render(e)));
	}
	graphemeSplit(e) {
		return $r(e);
	}
	_splitTextIntoLines(e) {
		let t = e.split(this._reNewline), n = Array(t.length), r = ["\n"], i = [];
		for (let e = 0; e < t.length; e++) n[e] = this.graphemeSplit(t[e]), i = i.concat(n[e], r);
		return i.pop(), {
			_unwrappedLines: n,
			lines: t,
			graphemeText: i,
			graphemeLines: n
		};
	}
	toObject(e = []) {
		return {
			...super.toObject([...ca, ...e]),
			styles: ds(this.styles, this.text),
			...this.path ? { path: this.path.toObject() } : {}
		};
	}
	set(e, t) {
		let { textLayoutProperties: n } = this.constructor;
		super.set(e, t);
		let r = !1, i = !1;
		if (typeof e == "object") for (let t in e) t === "path" && this.setPathInfo(), r ||= n.includes(t), i ||= t === "path";
		else r = n.includes(e), i = e === "path";
		return i && this.setPathInfo(), r && this.initialized && (this.initDimensions(), this.setCoords()), this;
	}
	complexity() {
		return 1;
	}
	static async fromElement(t, n, r) {
		let i = Is(t, e.ATTRIBUTE_NAMES, r), { textAnchor: a = G, textDecoration: o = "", dx: s = 0, dy: c = 0, top: l = 0, left: u = 0, fontSize: d = 16, strokeWidth: f = 1, ...p } = {
			...n,
			...i
		}, m = new this(Ui(t.textContent || "").trim(), {
			left: u + s,
			top: l + c,
			underline: o.includes("underline"),
			overline: o.includes("overline"),
			linethrough: o.includes("line-through"),
			strokeWidth: 0,
			fontSize: d,
			...p
		}), h = m.getScaledHeight() / m.height, g = ((m.height + m.strokeWidth) * m.lineHeight - m.height) * h, _ = m.getScaledHeight() + g, v = 0;
		return a === "center" && (v = m.getScaledWidth() / 2), a === "right" && (v = m.getScaledWidth()), m.set({
			left: m.left - v,
			top: m.top - (_ - m.fontSize * (.07 + m._fontSizeFraction)) / m.lineHeight,
			strokeWidth: f
		}), m;
	}
	static fromObject(e) {
		return this._fromObject({
			...e,
			styles: fs(e.styles || {}, e.text)
		}, { extraParam: "text" });
	}
};
H(jl, "textLayoutProperties", sa), H(jl, "cacheProperties", [...wa, ...ca]), H(jl, "ownDefaults", ua), H(jl, "type", "Text"), H(jl, "genericFonts", [
	"serif",
	"sans-serif",
	"monospace",
	"cursive",
	"fantasy",
	"system-ui",
	"ui-serif",
	"ui-sans-serif",
	"ui-monospace",
	"ui-rounded",
	"math",
	"emoji",
	"fangsong"
]), H(jl, "ATTRIBUTE_NAMES", ps.concat("x", "y", "dx", "dy", "font-family", "font-style", "font-weight", "font-size", "letter-spacing", "text-decoration", "text-decoration-thickness", "text-decoration-color", "text-anchor")), ts(jl, [class extends ta {
	_toSVG() {
		let e = this._getSVGLeftTopOffsets(), t = this._getSVGTextAndBg(e.textTop, e.textLeft);
		return this._wrapSVGTextAndBg(t);
	}
	toSVG(e) {
		let t = this._createBaseSVGMarkup(this._toSVG(), {
			reviver: e,
			noStyle: !0,
			withShadow: !0
		}), n = this.path;
		return n ? t + n._createBaseSVGMarkup(n._toSVG(), {
			reviver: e,
			withShadow: !0,
			additionalTransform: Lr(this.calcOwnMatrix())
		}) : t;
	}
	_getSVGLeftTopOffsets() {
		return {
			textLeft: -this.width / 2,
			textTop: -this.height / 2,
			lineTop: this.getHeightOfLine(0)
		};
	}
	_wrapSVGTextAndBg({ textBgRects: e, textSpans: t }) {
		let n = this.getSvgTextDecoration(this);
		return [
			e.join(""),
			"		<text xml:space=\"preserve\" ",
			`font-family="${Z(this.fontFamily.replace(Ol, "'"))}" `,
			`font-size="${Z(this.fontSize)}" `,
			this.fontStyle ? `font-style="${Z(this.fontStyle)}" ` : "",
			this.fontWeight ? `font-weight="${Z(this.fontWeight)}" ` : "",
			n ? `text-decoration="${n}" ` : "",
			this.direction === "rtl" ? "direction=\"rtl\" " : "",
			"style=\"",
			this.getSvgStyles(!0),
			"\"",
			this.addPaintOrder(),
			" >",
			t.join(""),
			"</text>\n"
		];
	}
	_getSVGTextAndBg(e, t) {
		let n = [], r = [], i, a = e;
		this.backgroundColor && r.push(kl(this.backgroundColor, -this.width / 2, -this.height / 2, this.width, this.height));
		for (let e = 0, o = this._textLines.length; e < o; e++) i = this._getLineLeftOffset(e), this.direction === "rtl" && (i += this.width), (this.textBackgroundColor || this.styleHas("textBackgroundColor", e)) && this._setSVGTextLineBg(r, e, t + i, a), this._setSVGTextLineText(n, e, t + i, a), a += this.getHeightOfLine(e);
		return {
			textSpans: n,
			textBgRects: r
		};
	}
	_createTextCharSpan(e, t, n, r, i) {
		let a = U.NUM_FRACTION_DIGITS, o = this.getSvgSpanStyles(t, e !== e.trim() || !!e.match(Dl)), s = o ? `style="${o}"` : "", c = t.deltaY, l = c ? ` dy="${X(c, a)}" ` : "", { angle: u, renderLeft: d, renderTop: f, width: p } = i, m = "";
		if (d !== void 0) {
			let e = p / 2;
			u && (m = ` rotate="${X(hr(u), a)}"`);
			let t = Tr({ angle: hr(u) });
			t[4] = d, t[5] = f;
			let i = new q(-e, 0).transform(t);
			n = i.x, r = i.y;
		}
		return `<tspan x="${X(n, a)}" y="${X(r, a)}" ${l}${m}${s}>${Z(e)}</tspan>`;
	}
	_setSVGTextLineText(e, t, n, r) {
		let i = this.getHeightOfLine(t), a = this.textAlign.includes(da), o = this._textLines[t], s, c, l, u, d, f = "", p = 0;
		r += i * (1 - this._fontSizeFraction) / this.lineHeight;
		for (let i = 0, m = o.length - 1; i <= m; i++) d = i === m || this.charSpacing || this.path, f += o[i], l = this.__charBounds[t][i], p === 0 ? (n += l.kernedWidth - l.width, p += l.width) : p += l.kernedWidth, a && !d && this._reSpaceAndTab.test(o[i]) && (d = !0), d ||= (s ||= this.getCompleteStyleDeclaration(t, i), c = this.getCompleteStyleDeclaration(t, i + 1), us(s, c, !0)), d && (u = this._getStyleDeclaration(t, i), e.push(this._createTextCharSpan(f, u, n, r, l)), f = "", s = c, this.direction === "rtl" ? n -= p : n += p, p = 0);
	}
	_setSVGTextLineBg(e, t, n, r) {
		let i = this._textLines[t], a = this.getHeightOfLine(t) / this.lineHeight, o, s = 0, c = 0, l = this.getValueOfPropertyAt(t, 0, "textBackgroundColor");
		for (let u = 0; u < i.length; u++) {
			let { left: i, width: d, kernedWidth: f } = this.__charBounds[t][u];
			o = this.getValueOfPropertyAt(t, u, "textBackgroundColor"), o === l ? s += f : (l && e.push(kl(l, n + c, r, s, a)), c = i, s = d, l = o);
		}
		o && e.push(kl(l, n + c, r, s, a));
	}
	getSvgStyles(e) {
		let t = Bi(this.textDecorationColor) ? ` text-decoration-color: ${Z(this[ia])};` : "";
		return `${super.getSvgStyles(e)} text-decoration-thickness: ${X(this.textDecorationThickness * this.getObjectScaling().y / 10, U.NUM_FRACTION_DIGITS)}%;${t} white-space: pre;`;
	}
	getSvgSpanStyles(e, t) {
		let { fontFamily: n, strokeWidth: r, stroke: i, fill: a, fontSize: o, fontStyle: s, fontWeight: c, textDecorationThickness: l, textDecorationColor: u, linethrough: d, overline: f, underline: p } = e, m = this.getSvgTextDecoration({
			underline: p ?? this.underline,
			overline: f ?? this.overline,
			linethrough: d ?? this.linethrough
		}), h = l || this.textDecorationThickness, g = u || this.textDecorationColor, _ = Vi(r), v = Hi(n), y = Vi(o), b = Hi(s), x = Vi(c) || Hi(c), S = Hi(g);
		return [
			i ? ea(Kn, i) : "",
			_ ? `stroke-width: ${Z(_)}; ` : "",
			v ? `font-family: ${v.includes("'") || v.includes("\"") ? Z(v) : `'${Z(v)}'`}; ` : "",
			y ? `font-size: ${Z(y)}px; ` : "",
			b ? `font-style: ${Z(b)}; ` : "",
			x ? `font-weight: ${Z(x)}; ` : "",
			m ? `text-decoration: ${m}; text-decoration-thickness: ${X(h * this.getObjectScaling().y / 10, U.NUM_FRACTION_DIGITS)}%;${S ? ` text-decoration-color: ${Z(S)};` : ""} ` : "",
			a ? ea(Gn, a) : "",
			t ? "white-space: pre; " : ""
		].join("");
	}
	getSvgTextDecoration(e) {
		return [
			"overline",
			"underline",
			"line-through"
		].filter((t) => e[t.replace("-", "")]).join(" ");
	}
}]), K.setClass(jl), K.setSVGClass(jl);
var Ml = class {
	constructor(e) {
		H(this, "target", void 0), H(this, "__mouseDownInPlace", !1), H(this, "__dragStartFired", !1), H(this, "__isDraggingOver", !1), H(this, "__dragStartSelection", void 0), H(this, "__dragImageDisposer", void 0), H(this, "_dispose", void 0), this.target = e;
		let t = [
			this.target.on("dragenter", this.dragEnterHandler.bind(this)),
			this.target.on("dragover", this.dragOverHandler.bind(this)),
			this.target.on("dragleave", this.dragLeaveHandler.bind(this)),
			this.target.on("dragend", this.dragEndHandler.bind(this)),
			this.target.on("drop", this.dropHandler.bind(this))
		];
		this._dispose = () => {
			t.forEach((e) => e()), this._dispose = void 0;
		};
	}
	isPointerOverSelection(e) {
		let t = this.target, n = t.getSelectionStartFromPointer(e);
		return t.isEditing && n >= t.selectionStart && n <= t.selectionEnd && t.selectionStart < t.selectionEnd;
	}
	start(e) {
		return this.__mouseDownInPlace = this.isPointerOverSelection(e);
	}
	isActive() {
		return this.__mouseDownInPlace;
	}
	end(e) {
		let t = this.isActive();
		return t && !this.__dragStartFired && (this.target.setCursorByClick(e), this.target.initDelayedCursor(!0)), this.__mouseDownInPlace = !1, this.__dragStartFired = !1, this.__isDraggingOver = !1, t;
	}
	getDragStartSelection() {
		return this.__dragStartSelection;
	}
	setDragImage(e, { selectionStart: t, selectionEnd: n }) {
		var r;
		let i = this.target, a = i.canvas, o = new q(i.flipX ? -1 : 1, i.flipY ? -1 : 1), s = i._getCursorBoundaries(t), c = new q(s.left + s.leftOffset, s.top + s.topOffset).multiply(o).transform(i.calcTransformMatrix()), l = a.getScenePoint(e).subtract(c), u = i.getCanvasRetinaScaling(), d = i.getBoundingRect(), f = c.subtract(new q(d.left, d.top)), p = a.viewportTransform, m = f.add(l).transform(p, !0), h = i.backgroundColor, g = ls(i.styles);
		i.backgroundColor = "";
		let _ = {
			stroke: "transparent",
			fill: "transparent",
			textBackgroundColor: "transparent"
		};
		i.setSelectionStyles(_, 0, t), i.setSelectionStyles(_, n, i.text.length), i.dirty = !0;
		let v = i.toCanvasElement({
			enableRetinaScaling: a.enableRetinaScaling,
			viewportTransform: !0
		});
		i.backgroundColor = h, i.styles = g, i.dirty = !0, Ac(v, {
			position: "fixed",
			left: -v.width + "px",
			border: An,
			width: v.width / u + "px",
			height: v.height / u + "px"
		}), this.__dragImageDisposer && this.__dragImageDisposer(), this.__dragImageDisposer = () => {
			v.remove();
		}, Ur(e.target || this.target.hiddenTextarea).body.appendChild(v), (r = e.dataTransfer) == null || r.setDragImage(v, m.x, m.y);
	}
	onDragStart(e) {
		this.__dragStartFired = !0;
		let t = this.target, n = this.isActive();
		if (n && e.dataTransfer) {
			let n = this.__dragStartSelection = {
				selectionStart: t.selectionStart,
				selectionEnd: t.selectionEnd
			}, r = t._text.slice(n.selectionStart, n.selectionEnd).join(""), i = {
				text: t.text,
				value: r,
				...n
			};
			e.dataTransfer.setData("text/plain", r), e.dataTransfer.setData("application/fabric", JSON.stringify({
				value: r,
				styles: t.getSelectionStyles(n.selectionStart, n.selectionEnd, !0)
			})), e.dataTransfer.effectAllowed = "copyMove", this.setDragImage(e, i);
		}
		return t.abortCursorAnimation(), n;
	}
	canDrop(e) {
		if (this.target.editable && !this.target.getActiveControl() && !e.defaultPrevented) {
			if (this.isActive() && this.__dragStartSelection) {
				let t = this.target.getSelectionStartFromPointer(e), n = this.__dragStartSelection;
				return t < n.selectionStart || t > n.selectionEnd;
			}
			return !0;
		}
		return !1;
	}
	targetCanDrop(e) {
		return this.target.canDrop(e);
	}
	dragEnterHandler({ e }) {
		let t = this.targetCanDrop(e);
		!this.__isDraggingOver && t && (this.__isDraggingOver = !0);
	}
	dragOverHandler(e) {
		let { e: t } = e, n = this.targetCanDrop(t);
		!this.__isDraggingOver && n ? this.__isDraggingOver = !0 : this.__isDraggingOver && !n && (this.__isDraggingOver = !1), this.__isDraggingOver && (t.preventDefault(), e.canDrop = !0, e.dropTarget = this.target);
	}
	dragLeaveHandler() {
		(this.__isDraggingOver || this.isActive()) && (this.__isDraggingOver = !1);
	}
	dropHandler(e) {
		let { e: t } = e, n = t.defaultPrevented;
		this.__isDraggingOver = !1, t.preventDefault();
		let r = t.dataTransfer?.getData("text/plain");
		if (r && !n) {
			let n = this.target, i = n.canvas, a = n.getSelectionStartFromPointer(t), { styles: o } = t.dataTransfer.types.includes("application/fabric") ? JSON.parse(t.dataTransfer.getData("application/fabric")) : {}, s = r[Math.max(0, r.length - 1)];
			if (this.__dragStartSelection) {
				let e = this.__dragStartSelection.selectionStart, t = this.__dragStartSelection.selectionEnd;
				a > e && a <= t ? a = e : a > t && (a -= t - e), n.removeChars(e, t), delete this.__dragStartSelection;
			}
			n._reNewline.test(s) && (n._reNewline.test(n._text[a]) || a === n._text.length) && (r = r.trimEnd()), e.didDrop = !0, e.dropTarget = n, n.insertChars(r, o, a), i.setActiveObject(n), n.enterEditing(t), n.selectionStart = Math.min(a + 0, n._text.length), n.selectionEnd = Math.min(n.selectionStart + r.length, n._text.length), n.hiddenTextarea.value = n.text, n._updateTextarea(), n.hiddenTextarea.focus(), n.fire(zn, {
				index: a + 0,
				action: "drop"
			}), i.fire("text:changed", { target: n }), i.contextTopDirty = !0, i.requestRenderAll();
		}
	}
	dragEndHandler({ e }) {
		if (this.isActive() && this.__dragStartFired && this.__dragStartSelection) {
			let t = this.target, n = this.target.canvas, { selectionStart: r, selectionEnd: i } = this.__dragStartSelection, a = e.dataTransfer?.dropEffect || "none";
			a === "none" ? (t.selectionStart = r, t.selectionEnd = i, t._updateTextarea(), t.hiddenTextarea.focus()) : (t.clearContextTop(), a === "move" && (t.removeChars(r, i), t.selectionStart = t.selectionEnd = r, t.hiddenTextarea && (t.hiddenTextarea.value = t.text), t._updateTextarea(), t.fire(zn, {
				index: r,
				action: "dragend"
			}), n.fire("text:changed", { target: t }), n.requestRenderAll()), t.exitEditing());
		}
		this.__dragImageDisposer && this.__dragImageDisposer(), delete this.__dragImageDisposer, delete this.__dragStartSelection, this.__isDraggingOver = !1;
	}
	dispose() {
		this._dispose && this._dispose();
	}
}, Nl = /[ \n\.,;!\?\-]/, Pl = class extends jl {
	constructor(...e) {
		super(...e), H(this, "_currentCursorOpacity", 1);
	}
	initBehavior() {
		this._tick = this._tick.bind(this), this._onTickComplete = this._onTickComplete.bind(this), this.updateSelectionOnMouseMove = this.updateSelectionOnMouseMove.bind(this);
	}
	onDeselect(e) {
		return this.isEditing && this.exitEditing(), this.selected = !1, super.onDeselect(e);
	}
	_animateCursor({ toValue: e, duration: t, delay: n, onComplete: r }) {
		return mo({
			startValue: this._currentCursorOpacity,
			endValue: e,
			duration: t,
			delay: n,
			onComplete: r,
			abort: () => !this.canvas || this.selectionStart !== this.selectionEnd,
			onChange: (e) => {
				this._currentCursorOpacity = e, this.renderCursorOrSelection();
			}
		});
	}
	_tick(e) {
		this._currentTickState = this._animateCursor({
			toValue: 0,
			duration: this.cursorDuration / 2,
			delay: Math.max(e || 0, 100),
			onComplete: this._onTickComplete
		});
	}
	_onTickComplete() {
		var e;
		(e = this._currentTickCompleteState) == null || e.abort(), this._currentTickCompleteState = this._animateCursor({
			toValue: 1,
			duration: this.cursorDuration,
			onComplete: this._tick
		});
	}
	initDelayedCursor(e) {
		this.abortCursorAnimation(), this._tick(e ? 0 : this.cursorDelay);
	}
	abortCursorAnimation() {
		let e = !1;
		[this._currentTickState, this._currentTickCompleteState].forEach((t) => {
			t && !t.isDone() && (e = !0, t.abort());
		}), this._currentCursorOpacity = 1, e && this.clearContextTop();
	}
	restartCursorIfNeeded() {
		[this._currentTickState, this._currentTickCompleteState].some((e) => !e || e.isDone()) && this.initDelayedCursor();
	}
	selectAll() {
		return this.selectionStart = 0, this.selectionEnd = this._text.length, this._fireSelectionChanged(), this._updateTextarea(), this;
	}
	cmdAll() {
		this.selectAll(), this.renderCursorOrSelection();
	}
	getSelectedText() {
		return this._text.slice(this.selectionStart, this.selectionEnd).join("");
	}
	findWordBoundaryLeft(e) {
		let t = 0, n = e - 1;
		if (this._reSpace.test(this._text[n])) for (; this._reSpace.test(this._text[n]);) t++, n--;
		for (; /\S/.test(this._text[n]) && n > -1;) t++, n--;
		return e - t;
	}
	findWordBoundaryRight(e) {
		let t = 0, n = e;
		if (this._reSpace.test(this._text[n])) for (; this._reSpace.test(this._text[n]);) t++, n++;
		for (; /\S/.test(this._text[n]) && n < this._text.length;) t++, n++;
		return e + t;
	}
	findLineBoundaryLeft(e) {
		let t = 0, n = e - 1;
		for (; !/\n/.test(this._text[n]) && n > -1;) t++, n--;
		return e - t;
	}
	findLineBoundaryRight(e) {
		let t = 0, n = e;
		for (; !/\n/.test(this._text[n]) && n < this._text.length;) t++, n++;
		return e + t;
	}
	searchWordBoundary(e, t) {
		let n = this._text, r = e > 0 && this._reSpace.test(n[e]) && (t === -1 || !jn.test(n[e - 1])) ? e - 1 : e, i = n[r];
		for (; r > 0 && r < n.length && !Nl.test(i);) r += t, i = n[r];
		return t === -1 && Nl.test(i) && r++, r;
	}
	selectWord(e) {
		e ??= this.selectionStart;
		let t = this.searchWordBoundary(e, -1), n = Math.max(t, this.searchWordBoundary(e, 1));
		this.selectionStart = t, this.selectionEnd = n, this._fireSelectionChanged(), this._updateTextarea(), this.renderCursorOrSelection();
	}
	selectLine(e) {
		e ??= this.selectionStart;
		let t = this.findLineBoundaryLeft(e), n = this.findLineBoundaryRight(e);
		this.selectionStart = t, this.selectionEnd = n, this._fireSelectionChanged(), this._updateTextarea();
	}
	enterEditing(e) {
		!this.isEditing && this.editable && (this.enterEditingImpl(), this.fire("editing:entered", e ? { e } : void 0), this._fireSelectionChanged(), this.canvas && (this.canvas.fire("text:editing:entered", {
			target: this,
			e
		}), this.canvas.requestRenderAll()));
	}
	enterEditingImpl() {
		this.canvas && (this.canvas.calcOffset(), this.canvas.textEditingManager.exitTextEditing()), this.isEditing = !0, this.initHiddenTextarea(), this.hiddenTextarea.focus(), this.hiddenTextarea.value = this.text, this._updateTextarea(), this._saveEditingProps(), this._setEditingProps(), this._textBeforeEdit = this.text, this._tick();
	}
	updateSelectionOnMouseMove(e) {
		if (this.getActiveControl()) return;
		let t = this.hiddenTextarea;
		Ur(t).activeElement !== t && t.focus();
		let n = this.getSelectionStartFromPointer(e), r = this.selectionStart, i = this.selectionEnd;
		(n === this.__selectionStartOnMouseDown && r !== i || r !== n && i !== n) && (n > this.__selectionStartOnMouseDown ? (this.selectionStart = this.__selectionStartOnMouseDown, this.selectionEnd = n) : (this.selectionStart = n, this.selectionEnd = this.__selectionStartOnMouseDown), this.selectionStart === r && this.selectionEnd === i || (this._fireSelectionChanged(), this._updateTextarea(), this.renderCursorOrSelection()));
	}
	_setEditingProps() {
		this.hoverCursor = "text", this.canvas && (this.canvas.defaultCursor = this.canvas.moveCursor = "text"), this.borderColor = this.editingBorderColor, this.hasControls = this.selectable = !1, this.lockMovementX = this.lockMovementY = !0;
	}
	fromStringToGraphemeSelection(e, t, n) {
		let r = n.slice(0, e), i = this.graphemeSplit(r).length;
		if (e === t) return {
			selectionStart: i,
			selectionEnd: i
		};
		let a = n.slice(e, t);
		return {
			selectionStart: i,
			selectionEnd: i + this.graphemeSplit(a).length
		};
	}
	fromGraphemeToStringSelection(e, t, n) {
		let r = n.slice(0, e).join("").length;
		return e === t ? {
			selectionStart: r,
			selectionEnd: r
		} : {
			selectionStart: r,
			selectionEnd: r + n.slice(e, t).join("").length
		};
	}
	_updateTextarea() {
		if (this.cursorOffsetCache = {}, this.hiddenTextarea) {
			if (!this.inCompositionMode) {
				let e = this.fromGraphemeToStringSelection(this.selectionStart, this.selectionEnd, this._text);
				this.hiddenTextarea.selectionStart = e.selectionStart, this.hiddenTextarea.selectionEnd = e.selectionEnd;
			}
			this.updateTextareaPosition();
		}
	}
	updateFromTextArea() {
		let { hiddenTextarea: e, direction: t, textAlign: n, inCompositionMode: r } = this;
		if (!e) return;
		let i = n === "justify" ? t === "ltr" ? G : kn : n.replace("justify-", ""), a = this.getPositionByOrigin(i, "top");
		this.cursorOffsetCache = {}, this.text = e.value, this.set("dirty", !0), this.initDimensions(), this.setPositionByOrigin(a, i, "top"), this.setCoords();
		let o = this.fromStringToGraphemeSelection(e.selectionStart, e.selectionEnd, e.value);
		this.selectionEnd = this.selectionStart = o.selectionEnd, r || (this.selectionStart = o.selectionStart), this.updateTextareaPosition();
	}
	updateTextareaPosition() {
		if (this.selectionStart === this.selectionEnd) {
			let e = this._calcTextareaPosition();
			this.hiddenTextarea.style.left = e.left, this.hiddenTextarea.style.top = e.top;
		}
	}
	_calcTextareaPosition() {
		if (!this.canvas) return {
			left: "1px",
			top: "1px"
		};
		let e = this.inCompositionMode ? this.compositionStart : this.selectionStart, t = this._getCursorBoundaries(e), n = this.get2DCursorLocation(e), r = n.lineIndex, i = n.charIndex, a = this.getValueOfPropertyAt(r, i, "fontSize") * this.lineHeight, o = t.leftOffset, s = this.getCanvasRetinaScaling(), c = this.canvas.upperCanvasEl, l = c.width / s, u = c.height / s, d = l - a, f = u - a, p = new q(t.left + o, t.top + t.topOffset + a).transform(this.calcTransformMatrix()).transform(this.canvas.viewportTransform).multiply(new q(c.clientWidth / l, c.clientHeight / u));
		return p.x < 0 && (p.x = 0), p.x > d && (p.x = d), p.y < 0 && (p.y = 0), p.y > f && (p.y = f), p.x += this.canvas._offset.left, p.y += this.canvas._offset.top, {
			left: `${p.x}px`,
			top: `${p.y}px`,
			fontSize: `${a}px`,
			charHeight: a
		};
	}
	_saveEditingProps() {
		this._savedProps = {
			hasControls: this.hasControls,
			borderColor: this.borderColor,
			lockMovementX: this.lockMovementX,
			lockMovementY: this.lockMovementY,
			hoverCursor: this.hoverCursor,
			selectable: this.selectable,
			defaultCursor: this.canvas && this.canvas.defaultCursor,
			moveCursor: this.canvas && this.canvas.moveCursor
		};
	}
	_restoreEditingProps() {
		this._savedProps && (this.hoverCursor = this._savedProps.hoverCursor, this.hasControls = this._savedProps.hasControls, this.borderColor = this._savedProps.borderColor, this.selectable = this._savedProps.selectable, this.lockMovementX = this._savedProps.lockMovementX, this.lockMovementY = this._savedProps.lockMovementY, this.canvas && (this.canvas.defaultCursor = this._savedProps.defaultCursor || this.canvas.defaultCursor, this.canvas.moveCursor = this._savedProps.moveCursor || this.canvas.moveCursor), delete this._savedProps);
	}
	exitEditingImpl() {
		let e = this.hiddenTextarea;
		this.selected = !1, this.isEditing = !1, e && (e.blur && e.blur(), e.parentNode && e.parentNode.removeChild(e)), this.hiddenTextarea = null, this.abortCursorAnimation(), this.selectionStart !== this.selectionEnd && this.clearContextTop(), this.selectionEnd = this.selectionStart, this._restoreEditingProps(), this._forceClearCache && (this.initDimensions(), this.setCoords());
	}
	exitEditing() {
		let e = this._textBeforeEdit !== this.text;
		return this.exitEditingImpl(), this.fire("editing:exited"), e && this.fire("modified"), this.canvas && (this.canvas.fire("text:editing:exited", { target: this }), e && this.canvas.fire("object:modified", { target: this })), this;
	}
	_removeExtraneousStyles() {
		for (let e in this.styles) this._textLines[e] || delete this.styles[e];
	}
	removeStyleFromTo(e, t) {
		let { lineIndex: n, charIndex: r } = this.get2DCursorLocation(e, !0), { lineIndex: i, charIndex: a } = this.get2DCursorLocation(t, !0);
		if (n !== i) {
			if (this.styles[n]) for (let e = r; e < this._unwrappedTextLines[n].length; e++) delete this.styles[n][e];
			if (this.styles[i]) for (let e = a; e < this._unwrappedTextLines[i].length; e++) {
				let t = this.styles[i][e];
				t && (this.styles[n] || (this.styles[n] = {}), this.styles[n][r + e - a] = t);
			}
			for (let e = n + 1; e <= i; e++) delete this.styles[e];
			this.shiftLineStyles(i, n - i);
		} else if (this.styles[n]) {
			let e = this.styles[n], t = a - r;
			for (let t = r; t < a; t++) delete e[t];
			for (let r in this.styles[n]) {
				let n = parseInt(r, 10);
				n >= a && (e[n - t] = e[r], delete e[r]);
			}
		}
	}
	shiftLineStyles(e, t) {
		let n = Object.assign({}, this.styles);
		for (let r in this.styles) {
			let i = parseInt(r, 10);
			i > e && (this.styles[i + t] = n[i], n[i - t] || delete this.styles[i]);
		}
	}
	insertNewlineStyleObject(e, t, n, r) {
		let i = {}, a = this._unwrappedTextLines[e].length, o = a === t, s = !1;
		n ||= 1, this.shiftLineStyles(e, n);
		let c = this.styles[e] ? this.styles[e][t === 0 ? t : t - 1] : void 0;
		for (let n in this.styles[e]) {
			let r = parseInt(n, 10);
			r >= t && (s = !0, i[r - t] = this.styles[e][n], o && t === 0 || delete this.styles[e][n]);
		}
		let l = !1;
		for (s && !o && (this.styles[e + n] = i, l = !0), (l || a > t) && n--; n > 0;) r && r[n - 1] ? this.styles[e + n] = { 0: { ...r[n - 1] } } : c ? this.styles[e + n] = { 0: { ...c } } : delete this.styles[e + n], n--;
		this._forceClearCache = !0;
	}
	insertCharStyleObject(e, t, n, r) {
		this.styles ||= {};
		let i = this.styles[e], a = i ? { ...i } : {};
		n ||= 1;
		for (let e in a) {
			let r = parseInt(e, 10);
			r >= t && (i[r + n] = a[r], a[r - n] || delete i[r]);
		}
		if (this._forceClearCache = !0, r) {
			for (; n--;) Object.keys(r[n]).length && (this.styles[e] || (this.styles[e] = {}), this.styles[e][t + n] = { ...r[n] });
			return;
		}
		if (!i) return;
		let o = i[t ? t - 1 : 1];
		for (; o && n--;) this.styles[e][t + n] = { ...o };
	}
	insertNewStyleBlock(e, t, n) {
		let r = this.get2DCursorLocation(t, !0), i = [0], a, o = 0;
		for (let t = 0; t < e.length; t++) e[t] === "\n" ? (o++, i[o] = 0) : i[o]++;
		for (i[0] > 0 && (this.insertCharStyleObject(r.lineIndex, r.charIndex, i[0], n), n &&= n.slice(i[0] + 1)), o && this.insertNewlineStyleObject(r.lineIndex, r.charIndex + i[0], o), a = 1; a < o; a++) i[a] > 0 ? this.insertCharStyleObject(r.lineIndex + a, 0, i[a], n) : n && this.styles[r.lineIndex + a] && n[0] && (this.styles[r.lineIndex + a][0] = n[0]), n &&= n.slice(i[a] + 1);
		i[a] > 0 && this.insertCharStyleObject(r.lineIndex + a, 0, i[a], n);
	}
	removeChars(e, t = e + 1) {
		this.removeStyleFromTo(e, t), this._text.splice(e, t - e), this.text = this._text.join(""), this.set("dirty", !0), this.initDimensions(), this.setCoords(), this._removeExtraneousStyles();
	}
	insertChars(e, t, n, r = n) {
		r > n && this.removeStyleFromTo(n, r);
		let i = this.graphemeSplit(e);
		this.insertNewStyleBlock(i, n, t), this._text = [
			...this._text.slice(0, n),
			...i,
			...this._text.slice(r)
		], this.text = this._text.join(""), this.set("dirty", !0), this.initDimensions(), this.setCoords(), this._removeExtraneousStyles();
	}
	setSelectionStartEndWithShift(e, t, n) {
		n <= e ? (t === e ? this._selectionDirection = G : this._selectionDirection === "right" && (this._selectionDirection = G, this.selectionEnd = e), this.selectionStart = n) : n > e && n < t ? this._selectionDirection === "right" ? this.selectionEnd = n : this.selectionStart = n : (t === e ? this._selectionDirection = kn : this._selectionDirection === "left" && (this._selectionDirection = kn, this.selectionStart = t), this.selectionEnd = n);
	}
}, Fl = class extends Pl {
	initHiddenTextarea() {
		let e = this.canvas && Ur(this.canvas.getElement()) || _n(), t = e.createElement("textarea");
		Object.entries({
			autocapitalize: "off",
			autocorrect: "off",
			autocomplete: "off",
			spellcheck: "false",
			"data-fabric": "textarea",
			wrap: "off",
			name: "fabricTextarea"
		}).map(([e, n]) => t.setAttribute(e, n));
		let { top: n, left: r, fontSize: i } = this._calcTextareaPosition();
		t.style.cssText = `position: absolute; top: ${n}; left: ${r}; z-index: -999; opacity: 0; width: 1px; height: 1px; font-size: 1px; padding-top: ${i};`, (this.hiddenTextareaContainer || e.body).appendChild(t), Object.entries({
			blur: "blur",
			keydown: "onKeyDown",
			keyup: "onKeyUp",
			input: "onInput",
			copy: "copy",
			cut: "copy",
			paste: "paste",
			compositionstart: "onCompositionStart",
			compositionupdate: "onCompositionUpdate",
			compositionend: "onCompositionEnd"
		}).map(([e, n]) => t.addEventListener(e, this[n].bind(this))), this.hiddenTextarea = t;
	}
	blur() {
		this.abortCursorAnimation();
	}
	onKeyDown(e) {
		if (!this.isEditing) return;
		let t = this.direction === "rtl" ? this.keysMapRtl : this.keysMap;
		if (e.keyCode in t) this[t[e.keyCode]](e);
		else {
			if (!(e.keyCode in this.ctrlKeysMapDown) || !e.ctrlKey && !e.metaKey) return;
			this[this.ctrlKeysMapDown[e.keyCode]](e);
		}
		e.stopImmediatePropagation(), e.preventDefault(), e.keyCode >= 33 && e.keyCode <= 40 ? (this.inCompositionMode = !1, this.clearContextTop(), this.renderCursorOrSelection()) : this.canvas && this.canvas.requestRenderAll();
	}
	onKeyUp(e) {
		!this.isEditing || this._copyDone || this.inCompositionMode ? this._copyDone = !1 : e.keyCode in this.ctrlKeysMapUp && (e.ctrlKey || e.metaKey) && (this[this.ctrlKeysMapUp[e.keyCode]](e), e.stopImmediatePropagation(), e.preventDefault(), this.canvas && this.canvas.requestRenderAll());
	}
	onInput(e) {
		let t = this.fromPaste, { value: n, selectionStart: r, selectionEnd: i } = this.hiddenTextarea;
		if (this.fromPaste = !1, e && e.stopPropagation(), !this.isEditing) return;
		let a = () => {
			this.updateFromTextArea(), this.fire(zn), this.canvas && (this.canvas.fire("text:changed", { target: this }), this.canvas.requestRenderAll());
		};
		if (this.hiddenTextarea.value === "") return this.styles = {}, void a();
		let o = this._splitTextIntoLines(n).graphemeText, s = this._text.length, c = o.length, l = this.selectionStart, u = this.selectionEnd, d = l !== u, f, p, m, h, g = c - s, _ = this.fromStringToGraphemeSelection(r, i, n), v = l > _.selectionStart;
		d ? (p = this._text.slice(l, u), g += u - l) : c < s && (p = v ? this._text.slice(u + g, u) : this._text.slice(l, l - g));
		let y = o.slice(_.selectionEnd - g, _.selectionEnd);
		if (p && p.length && (y.length && (f = this.getSelectionStyles(l, l + 1, !1), f = y.map(() => f[0])), d ? (m = l, h = u) : v ? (m = u - p.length, h = u) : (m = u, h = u + p.length), this.removeStyleFromTo(m, h)), y.length) {
			let { copyPasteData: e } = gn();
			t && y.join("") === e.copiedText && !U.disableStyleCopyPaste && (f = e.copiedTextStyle), this.insertNewStyleBlock(y, l, f);
		}
		a();
	}
	onCompositionStart() {
		this.inCompositionMode = !0;
	}
	onCompositionEnd() {
		this.inCompositionMode = !1;
	}
	onCompositionUpdate({ target: e }) {
		let { selectionStart: t, selectionEnd: n } = e;
		this.compositionStart = t, this.compositionEnd = n, this.updateTextareaPosition();
	}
	copy() {
		if (this.selectionStart === this.selectionEnd) return;
		let { copyPasteData: e } = gn();
		e.copiedText = this.getSelectedText(), U.disableStyleCopyPaste ? e.copiedTextStyle = void 0 : e.copiedTextStyle = this.getSelectionStyles(this.selectionStart, this.selectionEnd, !0), this._copyDone = !0;
	}
	paste() {
		this.fromPaste = !0;
	}
	_getWidthBeforeCursor(e, t) {
		let n, r = this._getLineLeftOffset(e);
		return t > 0 && (n = this.__charBounds[e][t - 1], r += n.left + n.width), r;
	}
	getDownCursorOffset(e, t) {
		let n = this._getSelectionForOffset(e, t), r = this.get2DCursorLocation(n), i = r.lineIndex;
		if (i === this._textLines.length - 1 || e.metaKey || e.keyCode === 34) return this._text.length - n;
		let a = r.charIndex, o = this._getWidthBeforeCursor(i, a), s = this._getIndexOnLine(i + 1, o);
		return this._textLines[i].slice(a).length + s + 1 + this.missingNewlineOffset(i);
	}
	_getSelectionForOffset(e, t) {
		return e.shiftKey && this.selectionStart !== this.selectionEnd && t ? this.selectionEnd : this.selectionStart;
	}
	getUpCursorOffset(e, t) {
		let n = this._getSelectionForOffset(e, t), r = this.get2DCursorLocation(n), i = r.lineIndex;
		if (i === 0 || e.metaKey || e.keyCode === 33) return -n;
		let a = r.charIndex, o = this._getWidthBeforeCursor(i, a), s = this._getIndexOnLine(i - 1, o), c = this._textLines[i].slice(0, a), l = this.missingNewlineOffset(i - 1);
		return -this._textLines[i - 1].length + s - c.length + (1 - l);
	}
	_getIndexOnLine(e, t) {
		let n = this._textLines[e], r, i, a = this._getLineLeftOffset(e), o = 0;
		for (let s = 0, c = n.length; s < c; s++) if (r = this.__charBounds[e][s].width, a += r, a > t) {
			i = !0;
			let e = a - r, n = a, c = Math.abs(e - t);
			o = Math.abs(n - t) < c ? s : s - 1;
			break;
		}
		return i || (o = n.length - 1), o;
	}
	moveCursorDown(e) {
		this.selectionStart >= this._text.length && this.selectionEnd >= this._text.length || this._moveCursorUpOrDown("Down", e);
	}
	moveCursorUp(e) {
		this.selectionStart === 0 && this.selectionEnd === 0 || this._moveCursorUpOrDown("Up", e);
	}
	_moveCursorUpOrDown(e, t) {
		let n = this[`get${e}CursorOffset`](t, this._selectionDirection === kn);
		if (t.shiftKey ? this.moveCursorWithShift(n) : this.moveCursorWithoutShift(n), n !== 0) {
			let e = this.text.length;
			this.selectionStart = Sa(0, this.selectionStart, e), this.selectionEnd = Sa(0, this.selectionEnd, e), this.abortCursorAnimation(), this.initDelayedCursor(), this._fireSelectionChanged(), this._updateTextarea();
		}
	}
	moveCursorWithShift(e) {
		let t = this._selectionDirection === "left" ? this.selectionStart + e : this.selectionEnd + e;
		return this.setSelectionStartEndWithShift(this.selectionStart, this.selectionEnd, t), e !== 0;
	}
	moveCursorWithoutShift(e) {
		return e < 0 ? (this.selectionStart += e, this.selectionEnd = this.selectionStart) : (this.selectionEnd += e, this.selectionStart = this.selectionEnd), e !== 0;
	}
	moveCursorLeft(e) {
		this.selectionStart === 0 && this.selectionEnd === 0 || this._moveCursorLeftOrRight("Left", e);
	}
	_move(e, t, n) {
		let r;
		if (e.altKey) r = this[`findWordBoundary${n}`](this[t]);
		else {
			if (!e.metaKey && e.keyCode !== 35 && e.keyCode !== 36) return this[t] += n === "Left" ? -1 : 1, !0;
			r = this[`findLineBoundary${n}`](this[t]);
		}
		return r !== void 0 && this[t] !== r && (this[t] = r, !0);
	}
	_moveLeft(e, t) {
		return this._move(e, t, "Left");
	}
	_moveRight(e, t) {
		return this._move(e, t, "Right");
	}
	moveCursorLeftWithoutShift(e) {
		let t = !0;
		return this._selectionDirection = G, this.selectionEnd === this.selectionStart && this.selectionStart !== 0 && (t = this._moveLeft(e, "selectionStart")), this.selectionEnd = this.selectionStart, t;
	}
	moveCursorLeftWithShift(e) {
		return this._selectionDirection === "right" && this.selectionStart !== this.selectionEnd ? this._moveLeft(e, "selectionEnd") : this.selectionStart === 0 ? void 0 : (this._selectionDirection = G, this._moveLeft(e, "selectionStart"));
	}
	moveCursorRight(e) {
		this.selectionStart >= this._text.length && this.selectionEnd >= this._text.length || this._moveCursorLeftOrRight("Right", e);
	}
	_moveCursorLeftOrRight(e, t) {
		let n = `moveCursor${e}${t.shiftKey ? "WithShift" : "WithoutShift"}`;
		this._currentCursorOpacity = 1, this[n](t) && (this.abortCursorAnimation(), this.initDelayedCursor(), this._fireSelectionChanged(), this._updateTextarea());
	}
	moveCursorRightWithShift(e) {
		return this._selectionDirection === "left" && this.selectionStart !== this.selectionEnd ? this._moveRight(e, "selectionStart") : this.selectionEnd === this._text.length ? void 0 : (this._selectionDirection = kn, this._moveRight(e, "selectionEnd"));
	}
	moveCursorRightWithoutShift(e) {
		let t = !0;
		return this._selectionDirection = kn, this.selectionStart === this.selectionEnd ? (t = this._moveRight(e, "selectionStart"), this.selectionEnd = this.selectionStart) : this.selectionStart = this.selectionEnd, t;
	}
}, Il = (e) => !!e.button, Ll = class extends Fl {
	constructor(...e) {
		super(...e), H(this, "draggableTextDelegate", void 0);
	}
	initBehavior() {
		this.on("mousedown", this._mouseDownHandler), this.on("mouseup", this.mouseUpHandler), this.on("mousedblclick", this.doubleClickHandler), this.on("mousetripleclick", this.tripleClickHandler), this.draggableTextDelegate = new Ml(this), super.initBehavior();
	}
	shouldStartDragging() {
		return this.draggableTextDelegate.isActive();
	}
	onDragStart(e) {
		return this.draggableTextDelegate.onDragStart(e);
	}
	canDrop(e) {
		return this.draggableTextDelegate.canDrop(e);
	}
	doubleClickHandler(e) {
		this.isEditing && (this.selectWord(this.getSelectionStartFromPointer(e.e)), this.renderCursorOrSelection());
	}
	tripleClickHandler(e) {
		this.isEditing && (this.selectLine(this.getSelectionStartFromPointer(e.e)), this.renderCursorOrSelection());
	}
	_mouseDownHandler({ e, alreadySelected: t }) {
		this.canvas && this.editable && !Il(e) && !this.getActiveControl() && (this.draggableTextDelegate.start(e) || (this.canvas.textEditingManager.register(this), t && (this.inCompositionMode = !1, this.setCursorByClick(e)), this.isEditing && (this.__selectionStartOnMouseDown = this.selectionStart, this.selectionStart === this.selectionEnd && this.abortCursorAnimation(), this.renderCursorOrSelection()), this.selected ||= t || this.isEditing));
	}
	mouseUpHandler({ e, transform: t }) {
		let n = this.draggableTextDelegate.end(e);
		if (this.canvas) {
			this.canvas.textEditingManager.unregister(this);
			let e = this.canvas._activeObject;
			if (e && e !== this) return;
		}
		!this.editable || this.group && !this.group.interactive || t && t.actionPerformed || Il(e) || n || this.selected && !this.getActiveControl() && (this.enterEditing(e), this.selectionStart === this.selectionEnd ? this.initDelayedCursor(!0) : this.renderCursorOrSelection());
	}
	setCursorByClick(e) {
		let t = this.getSelectionStartFromPointer(e), n = this.selectionStart, r = this.selectionEnd;
		e.shiftKey ? this.setSelectionStartEndWithShift(n, r, t) : (this.selectionStart = t, this.selectionEnd = t), this.isEditing && (this._fireSelectionChanged(), this._updateTextarea());
	}
	getSelectionStartFromPointer(e) {
		let t = this.canvas.getScenePoint(e).transform(vr(this.calcTransformMatrix())).add(new q(-this._getLeftOffset(), -this._getTopOffset())), n = 0, r = 0, i = 0;
		for (let e = 0; e < this._textLines.length && n <= t.y; e++) n += this.getHeightOfLine(e), i = e, e > 0 && (r += this._textLines[e - 1].length + this.missingNewlineOffset(e - 1));
		let a = Math.abs(this._getLineLeftOffset(i)), o = this._textLines[i].length, s = this.__charBounds[i];
		for (let e = 0; e < o; e++) {
			let n = a + s[e].kernedWidth;
			if (t.x <= n) {
				Math.abs(t.x - n) <= Math.abs(t.x - a) && r++;
				break;
			}
			a = n, r++;
		}
		return Math.min(this.flipX ? o - r : r, this._text.length);
	}
}, Rl = "moveCursorUp", zl = "moveCursorDown", Bl = "moveCursorLeft", Vl = "moveCursorRight", Hl = "exitEditing", Ul = (e, t) => {
	let n = t.getRetinaScaling();
	e.setTransform(n, 0, 0, n, 0, 0);
	let r = t.viewportTransform;
	e.transform(r[0], r[1], r[2], r[3], r[4], r[5]);
}, Wl = {
	selectionStart: 0,
	selectionEnd: 0,
	selectionColor: "rgba(17,119,255,0.3)",
	isEditing: !1,
	editable: !0,
	editingBorderColor: "rgba(102,153,255,0.25)",
	cursorWidth: 2,
	cursorColor: "",
	cursorDelay: 1e3,
	cursorDuration: 600,
	caching: !0,
	hiddenTextareaContainer: null,
	keysMap: {
		9: Hl,
		27: Hl,
		33: Rl,
		34: zl,
		35: Vl,
		36: Bl,
		37: Bl,
		38: Rl,
		39: Vl,
		40: zl
	},
	keysMapRtl: {
		9: Hl,
		27: Hl,
		33: Rl,
		34: zl,
		35: Bl,
		36: Vl,
		37: Vl,
		38: Rl,
		39: Bl,
		40: zl
	},
	ctrlKeysMapDown: { 65: "cmdAll" },
	ctrlKeysMapUp: {
		67: "copy",
		88: "cut"
	},
	_selectionDirection: null,
	_reSpace: /\s|\r?\n/,
	inCompositionMode: !1
}, Gl = class e extends Ll {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	get type() {
		let e = super.type;
		return e === "itext" ? "i-text" : e;
	}
	constructor(t, n) {
		super(t, {
			...e.ownDefaults,
			...n
		}), this.initBehavior();
	}
	_set(e, t) {
		return this.isEditing && this._savedProps && e in this._savedProps ? (this._savedProps[e] = t, this) : (e === "canvas" && (this.canvas instanceof $c && this.canvas.textEditingManager.remove(this), t instanceof $c && t.textEditingManager.add(this)), super._set(e, t));
	}
	setSelectionStart(e) {
		e = Math.max(e, 0), this._updateAndFire("selectionStart", e);
	}
	setSelectionEnd(e) {
		e = Math.min(e, this.text.length), this._updateAndFire("selectionEnd", e);
	}
	_updateAndFire(e, t) {
		this[e] !== t && (this._fireSelectionChanged(), this[e] = t), this._updateTextarea();
	}
	_fireSelectionChanged() {
		this.fire("selection:changed"), this.canvas && this.canvas.fire("text:selection:changed", { target: this });
	}
	initDimensions() {
		this.isEditing && this.initDelayedCursor(), super.initDimensions();
	}
	getSelectionStyles(e = this.selectionStart || 0, t = this.selectionEnd, n) {
		return super.getSelectionStyles(e, t, n);
	}
	setSelectionStyles(e, t = this.selectionStart || 0, n = this.selectionEnd) {
		return super.setSelectionStyles(e, t, n);
	}
	get2DCursorLocation(e = this.selectionStart, t) {
		return super.get2DCursorLocation(e, t);
	}
	render(e) {
		super.render(e), this.cursorOffsetCache = {}, this.renderCursorOrSelection();
	}
	toCanvasElement(e) {
		let t = this.isEditing;
		this.isEditing = !1;
		let n = super.toCanvasElement(e);
		return this.isEditing = t, n;
	}
	renderCursorOrSelection() {
		if (!this.isEditing || !this.canvas) return;
		let e = this.clearContextTop(!0);
		if (!e) return;
		let t = this._getCursorBoundaries(), n = this.findAncestorsWithClipPath(), r = n.length > 0, i, a = e;
		if (r) {
			i = fr(e.canvas), a = i.getContext("2d"), Ul(a, this.canvas);
			let t = this.calcTransformMatrix();
			a.transform(t[0], t[1], t[2], t[3], t[4], t[5]);
		}
		if (this.selectionStart !== this.selectionEnd || this.inCompositionMode ? this.renderSelection(a, t) : this.renderCursor(a, t), r) for (let t of n) {
			let n = t.clipPath, r = fr(e.canvas), i = r.getContext("2d");
			if (Ul(i, this.canvas), !n.absolutePositioned) {
				let e = t.calcTransformMatrix();
				i.transform(e[0], e[1], e[2], e[3], e[4], e[5]);
			}
			n.transform(i), n.drawObject(i, !0, {}), this.drawClipPathOnCache(a, n, r);
		}
		r && (e.setTransform(1, 0, 0, 1, 0, 0), e.drawImage(i, 0, 0)), this.canvas.contextTopDirty = !0, e.restore();
	}
	findAncestorsWithClipPath() {
		let e = [], t = this;
		for (; t;) t.clipPath && e.push(t), t = t.parent;
		return e;
	}
	_getCursorBoundaries(e = this.selectionStart, t) {
		let n = this._getLeftOffset(), r = this._getTopOffset(), i = this._getCursorBoundariesOffsets(e, t);
		return {
			left: n,
			top: r,
			leftOffset: i.left,
			topOffset: i.top
		};
	}
	_getCursorBoundariesOffsets(e, t) {
		return t ? this.__getCursorBoundariesOffsets(e) : this.cursorOffsetCache && "top" in this.cursorOffsetCache ? this.cursorOffsetCache : this.cursorOffsetCache = this.__getCursorBoundariesOffsets(e);
	}
	__getCursorBoundariesOffsets(e) {
		let t = 0, n = 0, { charIndex: r, lineIndex: i } = this.get2DCursorLocation(e), { textAlign: a, direction: o } = this;
		for (let e = 0; e < i; e++) t += this.getHeightOfLine(e);
		let s = this._getLineLeftOffset(i), c = this.__charBounds[i][r];
		c && (n = c.left), this.charSpacing !== 0 && r === this._textLines[i].length && (n -= this._getWidthOfCharSpacing());
		let l = s + (n > 0 ? n : 0);
		return o === "rtl" && (a === "right" || a === "justify" || a === "justify-right" ? l *= -1 : a === "left" || a === "justify-left" ? l = s - (n > 0 ? n : 0) : a !== "center" && a !== "justify-center" || (l = s - (n > 0 ? n : 0))), {
			top: t,
			left: l
		};
	}
	renderCursorAt(e) {
		this._renderCursor(this.canvas.contextTop, this._getCursorBoundaries(e, !0), e);
	}
	renderCursor(e, t) {
		this._renderCursor(e, t, this.selectionStart);
	}
	getCursorRenderingData(e = this.selectionStart, t = this._getCursorBoundaries(e)) {
		let n = this.get2DCursorLocation(e), r = n.lineIndex, i = n.charIndex > 0 ? n.charIndex - 1 : 0, a = this.getValueOfPropertyAt(r, i, "fontSize"), o = this.getObjectScaling().x * this.canvas.getZoom(), s = this.cursorWidth / o, c = this.getValueOfPropertyAt(r, i, "deltaY"), l = t.topOffset + (1 - this._fontSizeFraction) * this.getHeightOfLine(r) / this.lineHeight - a * (1 - this._fontSizeFraction);
		return {
			color: this.cursorColor || this.getValueOfPropertyAt(r, i, "fill"),
			opacity: this._currentCursorOpacity,
			left: t.left + t.leftOffset - s / 2,
			top: l + t.top + c,
			width: s,
			height: a
		};
	}
	_renderCursor(e, t, n) {
		let { color: r, opacity: i, left: a, top: o, width: s, height: c } = this.getCursorRenderingData(n, t);
		e.fillStyle = r, e.globalAlpha = i, e.fillRect(a, o, s, c);
	}
	renderSelection(e, t) {
		let n = {
			selectionStart: this.inCompositionMode ? this.hiddenTextarea.selectionStart : this.selectionStart,
			selectionEnd: this.inCompositionMode ? this.hiddenTextarea.selectionEnd : this.selectionEnd
		};
		this._renderSelection(e, n, t);
	}
	renderDragSourceEffect() {
		let e = this.draggableTextDelegate.getDragStartSelection();
		this._renderSelection(this.canvas.contextTop, e, this._getCursorBoundaries(e.selectionStart, !0));
	}
	renderDropTargetEffect(e) {
		let t = this.getSelectionStartFromPointer(e);
		this.renderCursorAt(t);
	}
	_renderSelection(e, t, n) {
		let { textAlign: r, direction: i } = this, a = t.selectionStart, o = t.selectionEnd, s = r.includes(da), c = this.get2DCursorLocation(a), l = this.get2DCursorLocation(o), u = c.lineIndex, d = l.lineIndex, f = c.charIndex < 0 ? 0 : c.charIndex, p = l.charIndex < 0 ? 0 : l.charIndex;
		for (let t = u; t <= d; t++) {
			let a = this._getLineLeftOffset(t) || 0, o = this.getHeightOfLine(t), c = 0, l = 0;
			if (t === u && (c = this.__charBounds[u][f].left), t >= u && t < d) l = s && !this.isEndOfWrapping(t) ? this.width : this.getLineWidth(t) || 5;
			else if (t === d) if (p === 0) l = this.__charBounds[d][p].left;
			else {
				let e = this._getWidthOfCharSpacing();
				l = this.__charBounds[d][p - 1].left + this.__charBounds[d][p - 1].width - e;
			}
			let m = o;
			(this.lineHeight < 1 || t === d && this.lineHeight > 1) && (o /= this.lineHeight);
			let h = n.left + a + c, g = o, _ = 0, v = l - c;
			this.inCompositionMode ? (e.fillStyle = this.compositionColor || "black", g = 1, _ = o) : e.fillStyle = this.selectionColor, i === "rtl" && (r === "right" || r === "justify" || r === "justify-right" ? h = this.width - h - v : r === "left" || r === "justify-left" ? h = n.left + a - l : r !== "center" && r !== "justify-center" || (h = n.left + a - l)), e.fillRect(h, n.top + n.topOffset + _, v, g), n.topOffset += m;
		}
	}
	getCurrentCharFontSize() {
		let e = this._getCurrentCharIndex();
		return this.getValueOfPropertyAt(e.l, e.c, "fontSize");
	}
	getCurrentCharColor() {
		let e = this._getCurrentCharIndex();
		return this.getValueOfPropertyAt(e.l, e.c, Gn);
	}
	_getCurrentCharIndex() {
		let e = this.get2DCursorLocation(this.selectionStart, !0), t = e.charIndex > 0 ? e.charIndex - 1 : 0;
		return {
			l: e.lineIndex,
			c: t
		};
	}
	dispose() {
		this.exitEditingImpl(), this.draggableTextDelegate.dispose(), super.dispose();
	}
};
H(Gl, "ownDefaults", Wl), H(Gl, "type", "IText"), K.setClass(Gl), K.setClass(Gl, "i-text");
var Kl = class e extends Gl {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t, n) {
		super(t, {
			...e.ownDefaults,
			...n
		});
	}
	static createControls() {
		return { controls: $o() };
	}
	initDimensions() {
		this.initialized && (this.isEditing && this.initDelayedCursor(), this._clearCache(), this.dynamicMinWidth = 0, this._styleMap = this._generateStyleMap(this._splitText()), this.dynamicMinWidth > this.width && this._set("width", this.dynamicMinWidth), this.textAlign.includes("justify") && this.enlargeSpaces(), this.height = this.calcTextHeight());
	}
	_generateStyleMap(e) {
		let t = 0, n = 0, r = 0, i = {};
		for (let a = 0; a < e.graphemeLines.length; a++) e.graphemeText[r] === "\n" && a > 0 ? (n = 0, r++, t++) : !this.splitByGrapheme && this._reSpaceAndTab.test(e.graphemeText[r]) && a > 0 && (n++, r++), i[a] = {
			line: t,
			offset: n
		}, r += e.graphemeLines[a].length, n += e.graphemeLines[a].length;
		return i;
	}
	styleHas(e, t) {
		if (this._styleMap && !this.isWrapping) {
			let e = this._styleMap[t];
			e && (t = e.line);
		}
		return super.styleHas(e, t);
	}
	isEmptyStyles(e) {
		if (!this.styles) return !0;
		let t, n, r = 0, i = !1, a = this._styleMap[e], o = this._styleMap[e + 1];
		a && (e = a.line, r = a.offset), o && (t = o.line, i = t === e, n = o.offset);
		let s = e === void 0 ? this.styles : { line: this.styles[e] };
		for (let e in s) for (let t in s[e]) {
			let a = parseInt(t, 10);
			if (a >= r && (!i || a < n)) for (let n in s[e][t]) return !1;
		}
		return !0;
	}
	_getStyleDeclaration(e, t) {
		if (this._styleMap && !this.isWrapping) {
			let n = this._styleMap[e];
			if (!n) return {};
			e = n.line, t = n.offset + t;
		}
		return super._getStyleDeclaration(e, t);
	}
	_setStyleDeclaration(e, t, n) {
		let r = this._styleMap[e];
		super._setStyleDeclaration(r.line, r.offset + t, n);
	}
	_deleteStyleDeclaration(e, t) {
		let n = this._styleMap[e];
		super._deleteStyleDeclaration(n.line, n.offset + t);
	}
	_getLineStyle(e) {
		let t = this._styleMap[e];
		return !!this.styles[t.line];
	}
	_setLineStyle(e) {
		let t = this._styleMap[e];
		super._setLineStyle(t.line);
	}
	_wrapText(e, t) {
		this.isWrapping = !0;
		let n = this.getGraphemeDataForRender(e), r = [];
		for (let e = 0; e < n.wordsData.length; e++) r.push(...this._wrapLine(e, t, n));
		return this.isWrapping = !1, r;
	}
	getGraphemeDataForRender(e) {
		let t = this.splitByGrapheme, n = t ? "" : " ", r = 0;
		return {
			wordsData: e.map((e, i) => {
				let a = 0, o = t ? this.graphemeSplit(e) : this.wordSplit(e);
				return o.length === 0 ? [{
					word: [],
					width: 0
				}] : o.map((e) => {
					let o = t ? [e] : this.graphemeSplit(e), s = this._measureWord(o, i, a);
					return r = Math.max(s, r), a += o.length + n.length, {
						word: o,
						width: s
					};
				});
			}),
			largestWordWidth: r
		};
	}
	_measureWord(e, t, n = 0) {
		let r, i = 0;
		for (let a = 0, o = e.length; a < o; a++) i += this._getGraphemeBox(e[a], t, a + n, r, !0).kernedWidth, r = e[a];
		return i;
	}
	wordSplit(e) {
		return e.split(this._wordJoiners);
	}
	_wrapLine(e, t, { largestWordWidth: n, wordsData: r }, i = 0) {
		let a = this._getWidthOfCharSpacing(), o = this.splitByGrapheme, s = [], c = o ? "" : " ", l = 0, u = [], d = 0, f = 0, p = !0;
		t -= i;
		let m = Math.max(t, n, this.dynamicMinWidth), h = r[e], g;
		for (g = 0; g < h.length; g++) {
			let { word: t, width: n } = h[g];
			d += t.length, l += f + n - a, l > m && !p ? (s.push(u), u = [], l = n, p = !0) : l += a, p || o || u.push(c), u = u.concat(t), f = o ? 0 : this._measureWord([c], e, d), d++, p = !1;
		}
		return g && s.push(u), n + i > this.dynamicMinWidth && (this.dynamicMinWidth = n - a + i), s;
	}
	isEndOfWrapping(e) {
		return !this._styleMap[e + 1] || this._styleMap[e + 1].line !== this._styleMap[e].line;
	}
	missingNewlineOffset(e, t) {
		return this.splitByGrapheme && !t ? +!!this.isEndOfWrapping(e) : 1;
	}
	_splitTextIntoLines(e) {
		let t = super._splitTextIntoLines(e), n = this._wrapText(t.lines, this.width), r = Array(n.length);
		for (let e = 0; e < n.length; e++) r[e] = n[e].join("");
		return t.lines = r, t.graphemeLines = n, t;
	}
	getMinWidth() {
		return Math.max(this.minWidth, this.dynamicMinWidth);
	}
	_removeExtraneousStyles() {
		let e = /* @__PURE__ */ new Map();
		for (let t in this._styleMap) {
			let n = parseInt(t, 10);
			if (this._textLines[n]) {
				let n = this._styleMap[t].line;
				e.set(`${n}`, !0);
			}
		}
		for (let t in this.styles) e.has(t) || delete this.styles[t];
	}
	toObject(e = []) {
		return super.toObject([
			"minWidth",
			"splitByGrapheme",
			...e
		]);
	}
};
H(Kl, "type", "Textbox"), H(Kl, "textLayoutProperties", [...Gl.textLayoutProperties, "width"]), H(Kl, "ownDefaults", {
	minWidth: 20,
	dynamicMinWidth: 2,
	lockScalingFlip: !0,
	noScaleCache: !1,
	_wordJoiners: /[ \t\r]/,
	splitByGrapheme: !1
}), K.setClass(Kl);
var ql = class extends Hs {
	shouldPerformLayout(e) {
		return !!e.target.clipPath && super.shouldPerformLayout(e);
	}
	shouldLayoutClipPath() {
		return !1;
	}
	calcLayoutResult(e, t) {
		let { target: n } = e, { clipPath: r, group: i } = n;
		if (!r || !this.shouldPerformLayout(e)) return;
		let { width: a, height: o } = si(Vs(n, r)), s = new q(a, o);
		if (r.absolutePositioned) return {
			center: hi(r.getRelativeCenterPoint(), void 0, i ? i.calcTransformMatrix() : void 0),
			size: s
		};
		{
			let i = r.getRelativeCenterPoint().transform(n.calcOwnMatrix(), !0);
			if (this.shouldPerformLayout(e)) {
				let { center: n = new q(), correction: r = new q() } = this.calcBoundingBox(t, e) || {};
				return {
					center: n.add(i),
					correction: r.subtract(i),
					size: s
				};
			}
			return {
				center: n.getRelativeCenterPoint().add(i),
				size: s
			};
		}
	}
};
H(ql, "type", "clip-path"), K.setClass(ql);
var Jl = class extends Hs {
	getInitialSize({ target: e }, { size: t }) {
		return new q(e.width || t.x, e.height || t.y);
	}
};
H(Jl, "type", "fixed"), K.setClass(Jl);
var Yl = class extends Gs {
	subscribeTargets(e) {
		let t = e.target;
		e.targets.reduce((e, t) => (t.parent && e.add(t.parent), e), /* @__PURE__ */ new Set()).forEach((e) => {
			e.layoutManager.subscribeTargets({
				target: e,
				targets: [t]
			});
		});
	}
	unsubscribeTargets(e) {
		let t = e.target, n = t.getObjects();
		e.targets.reduce((e, t) => (t.parent && e.add(t.parent), e), /* @__PURE__ */ new Set()).forEach((e) => {
			!n.some((t) => t.parent === e) && e.layoutManager.unsubscribeTargets({
				target: e,
				targets: [t]
			});
		});
	}
}, Xl = class e extends qs {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t = [], n = {}) {
		super(), Object.assign(this, e.ownDefaults), this.setOptions(n);
		let { left: r, top: i, layoutManager: a } = n;
		this.groupInit(t, {
			left: r,
			top: i,
			layoutManager: a ?? new Yl()
		});
	}
	_shouldSetNestedCoords() {
		return !0;
	}
	__objectSelectionMonitor() {}
	multiSelectAdd(...e) {
		this.multiSelectionStacking === "selection-order" ? this.add(...e) : e.forEach((e) => {
			let t = this._objects.findIndex((t) => t.isInFrontOf(e)), n = t === -1 ? this.size() : t;
			this.insertAt(n, e);
		});
	}
	canEnterGroup(e) {
		return this.getObjects().some((t) => t.isDescendantOf(e) || e.isDescendantOf(t)) ? (ln("error", "ActiveSelection: circular object trees are not supported, this call has no effect"), !1) : super.canEnterGroup(e);
	}
	enterGroup(e, t) {
		e.parent && e.parent === e.group ? e.parent._exitGroup(e) : e.group && e.parent !== e.group && e.group.remove(e), this._enterGroup(e, t);
	}
	exitGroup(e, t) {
		this._exitGroup(e, t), e.parent && e.parent._enterGroup(e, !0);
	}
	_onAfterObjectsChange(e, t) {
		super._onAfterObjectsChange(e, t);
		let n = /* @__PURE__ */ new Set();
		t.forEach((e) => {
			let { parent: t } = e;
			t && n.add(t);
		}), e === "removed" ? n.forEach((e) => {
			e._onAfterObjectsChange(Bs, t);
		}) : n.forEach((e) => {
			e._set("dirty", !0);
		});
	}
	onDeselect() {
		return this.removeAll(), !1;
	}
	toString() {
		return `#<ActiveSelection: (${this.complexity()})>`;
	}
	shouldCache() {
		return !1;
	}
	isOnACache() {
		return !1;
	}
	_renderControls(e, t, n) {
		e.save(), e.globalAlpha = this.isMoving ? this.borderOpacityWhenMoving : 1;
		let r = {
			hasControls: !1,
			...n,
			forActiveSelection: !0
		};
		for (let t = 0; t < this._objects.length; t++) this._objects[t]._renderControls(e, r);
		super._renderControls(e, t), e.restore();
	}
};
H(Xl, "type", "ActiveSelection"), H(Xl, "ownDefaults", { multiSelectionStacking: "canvas-stacking" }), K.setClass(Xl), K.setClass(Xl, "activeSelection");
var Zl = class {
	constructor() {
		H(this, "resources", {});
	}
	applyFilters(e, t, n, r, i) {
		let a = i.getContext("2d", {
			willReadFrequently: !0,
			desynchronized: !0
		});
		if (!a) return;
		a.drawImage(t, 0, 0, n, r);
		let o = {
			sourceWidth: n,
			sourceHeight: r,
			imageData: a.getImageData(0, 0, n, r),
			originalEl: t,
			originalImageData: a.getImageData(0, 0, n, r),
			canvasEl: i,
			ctx: a,
			filterBackend: this
		};
		e.forEach((e) => {
			e.applyTo(o);
		});
		let { imageData: s } = o;
		return s.width === n && s.height === r || (i.width = s.width, i.height = s.height), a.putImageData(s, 0, 0), o;
	}
}, Ql = class {
	constructor({ tileSize: e = U.textureSize } = {}) {
		H(this, "aPosition", new Float32Array([
			0,
			0,
			0,
			1,
			1,
			0,
			1,
			1
		])), H(this, "resources", {}), this.tileSize = e, this.setupGLContext(e, e), this.captureGPUInfo();
	}
	setupGLContext(e, t) {
		this.dispose(), this.createWebGLCanvas(e, t);
	}
	createWebGLCanvas(e, t) {
		let n = fr({
			width: e,
			height: t
		}), r = n.getContext("webgl", {
			alpha: !0,
			premultipliedAlpha: !1,
			depth: !1,
			stencil: !1,
			antialias: !1
		});
		r && (r.clearColor(0, 0, 0, 0), this.canvas = n, this.gl = r);
	}
	applyFilters(e, t, n, r, i, a) {
		let o = this.gl, s = i.getContext("2d");
		if (!o || !s) return;
		let c;
		a && (c = this.getCachedTexture(a, t));
		let l = {
			originalWidth: t.width || t.naturalWidth || 0,
			originalHeight: t.height || t.naturalHeight || 0,
			sourceWidth: n,
			sourceHeight: r,
			destinationWidth: n,
			destinationHeight: r,
			context: o,
			sourceTexture: this.createTexture(o, n, r, c ? void 0 : t),
			targetTexture: this.createTexture(o, n, r),
			originalTexture: c || this.createTexture(o, n, r, c ? void 0 : t),
			passes: e.length,
			webgl: !0,
			aPosition: this.aPosition,
			programCache: this.programCache,
			pass: 0,
			filterBackend: this,
			targetCanvas: i
		}, u = o.createFramebuffer();
		return o.bindFramebuffer(o.FRAMEBUFFER, u), e.forEach((e) => {
			e && e.applyTo(l);
		}), function(e) {
			let t = e.targetCanvas, n = t.width, r = t.height, i = e.destinationWidth, a = e.destinationHeight;
			n === i && r === a || (t.width = i, t.height = a);
		}(l), this.copyGLTo2D(o, l), o.bindTexture(o.TEXTURE_2D, null), o.deleteTexture(l.sourceTexture), o.deleteTexture(l.targetTexture), o.deleteFramebuffer(u), s.setTransform(1, 0, 0, 1, 0, 0), l;
	}
	dispose() {
		this.canvas && (this.canvas = null, this.gl = null), this.clearWebGLCaches();
	}
	clearWebGLCaches() {
		this.programCache = {}, this.textureCache = {};
	}
	createTexture(e, t, n, r, i) {
		let { NEAREST: a, TEXTURE_2D: o, RGBA: s, UNSIGNED_BYTE: c, CLAMP_TO_EDGE: l, TEXTURE_MAG_FILTER: u, TEXTURE_MIN_FILTER: d, TEXTURE_WRAP_S: f, TEXTURE_WRAP_T: p } = e, m = e.createTexture();
		return e.bindTexture(o, m), e.texParameteri(o, u, i || a), e.texParameteri(o, d, i || a), e.texParameteri(o, f, l), e.texParameteri(o, p, l), r ? e.texImage2D(o, 0, s, s, c, r) : e.texImage2D(o, 0, s, t, n, 0, s, c, null), m;
	}
	getCachedTexture(e, t, n) {
		let { textureCache: r } = this;
		if (r[e]) return r[e];
		{
			let i = this.createTexture(this.gl, t.width, t.height, t, n);
			return i && (r[e] = i), i;
		}
	}
	evictCachesForKey(e) {
		this.textureCache[e] && (this.gl.deleteTexture(this.textureCache[e]), delete this.textureCache[e]);
	}
	copyGLTo2D(e, t) {
		let n = e.canvas, r = t.targetCanvas, i = r.getContext("2d");
		if (!i) return;
		i.translate(0, r.height), i.scale(1, -1);
		let a = n.height - r.height;
		i.drawImage(n, 0, a, r.width, r.height, 0, 0, r.width, r.height);
	}
	copyGLTo2DPutImageData(e, t) {
		let n = t.targetCanvas.getContext("2d"), r = t.destinationWidth, i = t.destinationHeight, a = r * i * 4;
		if (!n) return;
		let o = new Uint8Array(this.imageBuffer, 0, a), s = new Uint8ClampedArray(this.imageBuffer, 0, a);
		e.readPixels(0, 0, r, i, e.RGBA, e.UNSIGNED_BYTE, o);
		let c = new ImageData(s, r, i);
		n.putImageData(c, 0, 0);
	}
	captureGPUInfo() {
		if (this.gpuInfo) return this.gpuInfo;
		let e = this.gl, t = {
			renderer: "",
			vendor: ""
		};
		if (!e) return t;
		let n = e.getExtension("WEBGL_debug_renderer_info");
		if (n) {
			let r = e.getParameter(n.UNMASKED_RENDERER_WEBGL), i = e.getParameter(n.UNMASKED_VENDOR_WEBGL);
			r && (t.renderer = r.toLowerCase()), i && (t.vendor = i.toLowerCase());
		}
		return this.gpuInfo = t, t;
	}
}, $l;
function eu() {
	let { WebGLProbe: e } = gn();
	return e.queryWebGL(lr()), U.enableGLFiltering && e.isSupported(U.textureSize) ? new Ql({ tileSize: U.textureSize }) : new Zl();
}
function tu(e = !0) {
	return !$l && e && ($l = eu()), $l;
}
var nu = ["cropX", "cropY"], ru = class e extends ns {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t, n) {
		super(), H(this, "_lastScaleX", 1), H(this, "_lastScaleY", 1), H(this, "_filterScalingX", 1), H(this, "_filterScalingY", 1), this.filters = [], Object.assign(this, e.ownDefaults), this.setOptions(n), this.cacheKey = `texture${cr()}`, this.setElement(typeof t == "string" ? (this.canvas && Ur(this.canvas.getElement()) || _n()).getElementById(t) : t, n);
	}
	getElement() {
		return this._element;
	}
	setElement(e, t = {}) {
		this.removeTexture(this.cacheKey), this.removeTexture(`${this.cacheKey}_filtered`), this._element = e, this._originalElement = e, this._setWidthHeight(t), this.filters.length !== 0 && this.applyFilters(), this.resizeFilter && this.applyResizeFilters();
	}
	removeTexture(e) {
		let t = tu(!1);
		t instanceof Ql && t.evictCachesForKey(e);
	}
	dispose() {
		super.dispose(), this.removeTexture(this.cacheKey), this.removeTexture(`${this.cacheKey}_filtered`), this._cacheContext = null, [
			"_originalElement",
			"_element",
			"_filteredEl",
			"_cacheCanvas"
		].forEach((e) => {
			let t = this[e];
			t && gn().dispose(t), this[e] = void 0;
		});
	}
	getCrossOrigin() {
		return this._originalElement && (this._originalElement.crossOrigin || null);
	}
	getOriginalSize() {
		let e = this.getElement();
		return e ? {
			width: e.naturalWidth || e.width,
			height: e.naturalHeight || e.height
		} : {
			width: 0,
			height: 0
		};
	}
	_stroke(e) {
		if (!this.stroke || this.strokeWidth === 0) return;
		let t = this.width / 2, n = this.height / 2;
		e.beginPath(), e.moveTo(-t, -n), e.lineTo(t, -n), e.lineTo(t, n), e.lineTo(-t, n), e.lineTo(-t, -n), e.closePath();
	}
	toObject(e = []) {
		let t = [];
		return this.filters.forEach((e) => {
			e && t.push(e.toObject());
		}), {
			...super.toObject([...nu, ...e]),
			src: this.getSrc(),
			crossOrigin: this.getCrossOrigin(),
			filters: t,
			...this.resizeFilter ? { resizeFilter: this.resizeFilter.toObject() } : {}
		};
	}
	hasCrop() {
		return !!this.cropX || !!this.cropY || this.width < this._element.width || this.height < this._element.height;
	}
	_toSVG() {
		let e = [], t = this._element, n = -this.width / 2, r = -this.height / 2, i = [], a = [], o = "", s = "";
		if (!t) return [];
		if (this.hasCrop()) {
			let e = cr();
			i.push("<clipPath id=\"imageCrop_" + e + "\">\n", "	<rect x=\"" + n + "\" y=\"" + r + "\" width=\"" + Z(this.width) + "\" height=\"" + Z(this.height) + "\" />\n", "</clipPath>\n"), o = " clip-path=\"url(#imageCrop_" + e + ")\" ";
		}
		if (this.imageSmoothing || (s = " image-rendering=\"optimizeSpeed\""), e.push("	<image ", "COMMON_PARTS", `xlink:href="${Z(this.getSrc(!0))}" x="${n - this.cropX}" y="${r - this.cropY}" width="${t.width || t.naturalWidth}" height="${t.height || t.naturalHeight}"${s}${o}></image>\n`), this.stroke || this.strokeDashArray) {
			let e = this.fill;
			this.fill = null, a = [`\t<rect x="${n}" y="${r}" width="${Z(this.width)}" height="${Z(this.height)}" style="${this.getSvgStyles()}" />\n`], this.fill = e;
		}
		return i = this.paintFirst === "fill" ? i.concat(e, a) : i.concat(a, e), i;
	}
	getSrc(e) {
		let t = e ? this._element : this._originalElement;
		return t ? t.toDataURL ? t.toDataURL() : this.srcFromAttribute ? t.getAttribute("src") || "" : t.src : this.src || "";
	}
	getSvgSrc(e) {
		return this.getSrc(e);
	}
	setSrc(e, { crossOrigin: t, signal: n } = {}) {
		return Mr(e, {
			crossOrigin: t,
			signal: n
		}).then((e) => {
			t !== void 0 && this.set({ crossOrigin: t }), this.setElement(e);
		});
	}
	toString() {
		return `#<Image: { src: "${this.getSrc()}" }>`;
	}
	applyResizeFilters() {
		let e = this.resizeFilter, t = this.minimumScaleTrigger, n = this.getTotalObjectScaling(), r = n.x, i = n.y, a = this._filteredEl || this._originalElement;
		if (this.group && this.set("dirty", !0), !e || r > t && i > t) return this._element = a, this._filterScalingX = 1, this._filterScalingY = 1, this._lastScaleX = r, void (this._lastScaleY = i);
		let o = fr(a), { width: s, height: c } = a;
		this._element = o, this._lastScaleX = e.scaleX = r, this._lastScaleY = e.scaleY = i, tu().applyFilters([e], a, s, c, this._element), this._filterScalingX = o.width / this._originalElement.width, this._filterScalingY = o.height / this._originalElement.height;
	}
	applyFilters(e = this.filters || []) {
		if (e = e.filter((e) => e && !e.isNeutralState()), this.set("dirty", !0), this.removeTexture(`${this.cacheKey}_filtered`), e.length === 0) return this._element = this._originalElement, this._filteredEl = void 0, this._filterScalingX = 1, void (this._filterScalingY = 1);
		let t = this._originalElement, n = t.naturalWidth || t.width, r = t.naturalHeight || t.height;
		if (this._element === this._originalElement) {
			let e = fr({
				width: n,
				height: r
			});
			this._element = e, this._filteredEl = e;
		} else this._filteredEl && (this._element = this._filteredEl, this._filteredEl.getContext("2d").clearRect(0, 0, n, r), this._lastScaleX = 1, this._lastScaleY = 1);
		tu().applyFilters(e, this._originalElement, n, r, this._element, this.cacheKey), this._originalElement.width === this._element.width && this._originalElement.height === this._element.height || (this._filterScalingX = this._element.width / this._originalElement.width, this._filterScalingY = this._element.height / this._originalElement.height);
	}
	_render(e) {
		e.imageSmoothingEnabled = this.imageSmoothing, !0 !== this.isMoving && this.resizeFilter && this._needsResize() && this.applyResizeFilters(), this._stroke(e), this._renderPaintInOrder(e);
	}
	drawCacheOnCanvas(e) {
		e.imageSmoothingEnabled = this.imageSmoothing, super.drawCacheOnCanvas(e);
	}
	shouldCache() {
		return this.needsItsOwnCache();
	}
	_renderFill(e) {
		let t = this._element;
		if (!t) return;
		let n = this._filterScalingX, r = this._filterScalingY, i = this.width, a = this.height, o = Math.max(this.cropX, 0), s = Math.max(this.cropY, 0), c = t.naturalWidth || t.width, l = t.naturalHeight || t.height, u = o * n, d = s * r, f = Math.min(i * n, c - u), p = Math.min(a * r, l - d), m = -i / 2, h = -a / 2, g = Math.min(i, c / n - o), _ = Math.min(a, l / r - s);
		t && e.drawImage(t, u, d, f, p, m, h, g, _);
	}
	_needsResize() {
		let e = this.getTotalObjectScaling();
		return e.x !== this._lastScaleX || e.y !== this._lastScaleY;
	}
	_resetWidthHeight() {
		this.set(this.getOriginalSize());
	}
	_setWidthHeight({ width: e, height: t } = {}) {
		let n = this.getOriginalSize();
		this.width = e || n.width, this.height = t || n.height;
	}
	parsePreserveAspectRatioAttribute() {
		let e = $i(this.preserveAspectRatio || ""), t = this.width, n = this.height, r = {
			width: t,
			height: n
		}, i, a = this._element.width, o = this._element.height, s = 1, c = 1, l = 0, u = 0, d = 0, f = 0;
		return !e || e.alignX === "none" && e.alignY === "none" ? (s = t / a, c = n / o) : (e.meetOrSlice === "meet" && (s = c = Ys(this._element, r), i = (t - a * s) / 2, e.alignX === "Min" && (l = -i), e.alignX === "Max" && (l = i), i = (n - o * c) / 2, e.alignY === "Min" && (u = -i), e.alignY === "Max" && (u = i)), e.meetOrSlice === "slice" && (s = c = Xs(this._element, r), i = a - t / s, e.alignX === "Mid" && (d = i / 2), e.alignX === "Max" && (d = i), i = o - n / c, e.alignY === "Mid" && (f = i / 2), e.alignY === "Max" && (f = i), a = t / s, o = n / c)), {
			width: a,
			height: o,
			scaleX: s,
			scaleY: c,
			offsetLeft: l,
			offsetTop: u,
			cropX: d,
			cropY: f
		};
	}
	static fromObject({ filters: e, resizeFilter: t, src: n, crossOrigin: r, type: i, ...a }, o) {
		return Promise.all([
			Mr(n, {
				...o,
				crossOrigin: r
			}),
			e && Nr(e, o),
			t ? Nr([t], o) : [],
			Pr(a, o)
		]).then(([e, t = [], [r], i = {}]) => new this(e, {
			...a,
			src: n,
			filters: t,
			resizeFilter: r,
			...i
		}));
	}
	static fromURL(e, { crossOrigin: t = null, signal: n } = {}, r) {
		return Mr(e, {
			crossOrigin: t,
			signal: n
		}).then((e) => new this(e, r));
	}
	static async fromElement(e, t = {}, n) {
		let r = Is(e, this.ATTRIBUTE_NAMES, n);
		return this.fromURL(r["xlink:href"] || r.href, t, r).catch((e) => (ln("log", "Unable to parse Image", e), null));
	}
};
H(ru, "type", "Image"), H(ru, "cacheProperties", [...wa, ...nu]), H(ru, "ownDefaults", {
	strokeWidth: 0,
	srcFromAttribute: !1,
	minimumScaleTrigger: .5,
	cropX: 0,
	cropY: 0,
	imageSmoothing: !0
}), H(ru, "ATTRIBUTE_NAMES", [
	...ps,
	"x",
	"y",
	"width",
	"height",
	"preserveAspectRatio",
	"xlink:href",
	"href",
	"crossOrigin",
	"image-rendering"
]), K.setClass(ru), K.setSVGClass(ru), na([
	"pattern",
	"defs",
	"symbol",
	"metadata",
	"clipPath",
	"mask",
	"desc"
]);
var iu = (e) => e.webgl !== void 0, au = "precision highp float", ou = `\n    ${au};\n    varying vec2 vTexCoord;\n    uniform sampler2D uTexture;\n    void main() {\n      gl_FragColor = texture2D(uTexture, vTexCoord);\n    }`, su = new RegExp(au, "g"), Q = class {
	get type() {
		return this.constructor.type;
	}
	constructor({ type: e, ...t } = {}) {
		Object.assign(this, this.constructor.defaults, t);
	}
	getFragmentSource() {
		return ou;
	}
	getVertexSource() {
		return "\n    attribute vec2 aPosition;\n    varying vec2 vTexCoord;\n    void main() {\n      vTexCoord = aPosition;\n      gl_Position = vec4(aPosition * 2.0 - 1.0, 0.0, 1.0);\n    }";
	}
	createProgram(e, t = this.getFragmentSource(), n = this.getVertexSource()) {
		let { WebGLProbe: { GLPrecision: r = "highp" } } = gn();
		r !== "highp" && (t = t.replace(su, au.replace("highp", r)));
		let i = e.createShader(e.VERTEX_SHADER), a = e.createShader(e.FRAGMENT_SHADER), o = e.createProgram();
		if (!i || !a || !o) throw new un("Vertex, fragment shader or program creation error");
		if (e.shaderSource(i, n), e.compileShader(i), !e.getShaderParameter(i, e.COMPILE_STATUS)) throw new un(`Vertex shader compile error for ${this.type}: ${e.getShaderInfoLog(i)}`);
		if (e.shaderSource(a, t), e.compileShader(a), !e.getShaderParameter(a, e.COMPILE_STATUS)) throw new un(`Fragment shader compile error for ${this.type}: ${e.getShaderInfoLog(a)}`);
		if (e.attachShader(o, i), e.attachShader(o, a), e.linkProgram(o), !e.getProgramParameter(o, e.LINK_STATUS)) throw new un(`Shader link error for "${this.type}" ${e.getProgramInfoLog(o)}`);
		let s = this.getUniformLocations(e, o) || {};
		return s.uStepW = e.getUniformLocation(o, "uStepW"), s.uStepH = e.getUniformLocation(o, "uStepH"), {
			program: o,
			attributeLocations: this.getAttributeLocations(e, o),
			uniformLocations: s
		};
	}
	getAttributeLocations(e, t) {
		return { aPosition: e.getAttribLocation(t, "aPosition") };
	}
	getUniformLocations(e, t) {
		let n = this.constructor.uniformLocations, r = {};
		for (let i = 0; i < n.length; i++) r[n[i]] = e.getUniformLocation(t, n[i]);
		return r;
	}
	sendAttributeData(e, t, n) {
		let r = t.aPosition, i = e.createBuffer();
		e.bindBuffer(e.ARRAY_BUFFER, i), e.enableVertexAttribArray(r), e.vertexAttribPointer(r, 2, e.FLOAT, !1, 0, 0), e.bufferData(e.ARRAY_BUFFER, n, e.STATIC_DRAW);
	}
	_setupFrameBuffer(e) {
		let t = e.context;
		if (e.passes > 1) {
			let n = e.destinationWidth, r = e.destinationHeight;
			e.sourceWidth === n && e.sourceHeight === r || (t.deleteTexture(e.targetTexture), e.targetTexture = e.filterBackend.createTexture(t, n, r)), t.framebufferTexture2D(t.FRAMEBUFFER, t.COLOR_ATTACHMENT0, t.TEXTURE_2D, e.targetTexture, 0);
		} else t.bindFramebuffer(t.FRAMEBUFFER, null), t.finish();
	}
	_swapTextures(e) {
		e.passes--, e.pass++;
		let t = e.targetTexture;
		e.targetTexture = e.sourceTexture, e.sourceTexture = t;
	}
	isNeutralState(e) {
		return !1;
	}
	applyTo(e) {
		iu(e) ? (this._setupFrameBuffer(e), this.applyToWebGL(e), this._swapTextures(e)) : this.applyTo2d(e);
	}
	applyTo2d(e) {}
	getCacheKey() {
		return this.type;
	}
	retrieveShader(e) {
		let t = this.getCacheKey();
		return e.programCache[t] || (e.programCache[t] = this.createProgram(e.context)), e.programCache[t];
	}
	applyToWebGL(e) {
		let t = e.context, n = this.retrieveShader(e);
		e.pass === 0 && e.originalTexture ? t.bindTexture(t.TEXTURE_2D, e.originalTexture) : t.bindTexture(t.TEXTURE_2D, e.sourceTexture), t.useProgram(n.program), this.sendAttributeData(t, n.attributeLocations, e.aPosition), t.uniform1f(n.uniformLocations.uStepW, 1 / e.sourceWidth), t.uniform1f(n.uniformLocations.uStepH, 1 / e.sourceHeight), this.sendUniformData(t, n.uniformLocations), t.viewport(0, 0, e.destinationWidth, e.destinationHeight), t.drawArrays(t.TRIANGLE_STRIP, 0, 4);
	}
	bindAdditionalTexture(e, t, n) {
		e.activeTexture(n), e.bindTexture(e.TEXTURE_2D, t), e.activeTexture(e.TEXTURE0);
	}
	unbindAdditionalTexture(e, t) {
		e.activeTexture(t), e.bindTexture(e.TEXTURE_2D, null), e.activeTexture(e.TEXTURE0);
	}
	sendUniformData(e, t) {}
	createHelpLayer(e) {
		if (!e.helpLayer) {
			let { sourceWidth: t, sourceHeight: n } = e;
			e.helpLayer = fr({
				width: t,
				height: n
			});
		}
	}
	toObject() {
		let e = Object.keys(this.constructor.defaults || {});
		return {
			type: this.type,
			...e.reduce((e, t) => (e[t] = this[t], e), {})
		};
	}
	toJSON() {
		return this.toObject();
	}
	static async fromObject({ type: e, ...t }, n) {
		return new this(t);
	}
};
H(Q, "type", "BaseFilter"), H(Q, "uniformLocations", []);
var cu = {
	multiply: "gl_FragColor.rgb *= uColor.rgb;\n",
	screen: "gl_FragColor.rgb = 1.0 - (1.0 - gl_FragColor.rgb) * (1.0 - uColor.rgb);\n",
	add: "gl_FragColor.rgb += uColor.rgb;\n",
	difference: "gl_FragColor.rgb = abs(gl_FragColor.rgb - uColor.rgb);\n",
	subtract: "gl_FragColor.rgb -= uColor.rgb;\n",
	lighten: "gl_FragColor.rgb = max(gl_FragColor.rgb, uColor.rgb);\n",
	darken: "gl_FragColor.rgb = min(gl_FragColor.rgb, uColor.rgb);\n",
	exclusion: "gl_FragColor.rgb += uColor.rgb - 2.0 * (uColor.rgb * gl_FragColor.rgb);\n",
	overlay: "\n    if (uColor.r < 0.5) {\n      gl_FragColor.r *= 2.0 * uColor.r;\n    } else {\n      gl_FragColor.r = 1.0 - 2.0 * (1.0 - gl_FragColor.r) * (1.0 - uColor.r);\n    }\n    if (uColor.g < 0.5) {\n      gl_FragColor.g *= 2.0 * uColor.g;\n    } else {\n      gl_FragColor.g = 1.0 - 2.0 * (1.0 - gl_FragColor.g) * (1.0 - uColor.g);\n    }\n    if (uColor.b < 0.5) {\n      gl_FragColor.b *= 2.0 * uColor.b;\n    } else {\n      gl_FragColor.b = 1.0 - 2.0 * (1.0 - gl_FragColor.b) * (1.0 - uColor.b);\n    }\n    ",
	tint: "\n    gl_FragColor.rgb *= (1.0 - uColor.a);\n    gl_FragColor.rgb += uColor.rgb;\n    "
}, lu = class extends Q {
	getCacheKey() {
		return `${this.type}_${this.mode}`;
	}
	getFragmentSource() {
		return `\n      precision highp float;\n      uniform sampler2D uTexture;\n      uniform vec4 uColor;\n      varying vec2 vTexCoord;\n      void main() {\n        vec4 color = texture2D(uTexture, vTexCoord);\n        gl_FragColor = color;\n        if (color.a > 0.0) {\n          ${cu[this.mode]}\n        }\n      }\n      `;
	}
	applyTo2d({ imageData: { data: e } }) {
		let t = new Xi(this.color).getSource(), n = this.alpha, r = t[0] * n, i = t[1] * n, a = t[2] * n, o = 1 - n;
		for (let t = 0; t < e.length; t += 4) {
			let n = e[t], s = e[t + 1], c = e[t + 2], l, u, d;
			switch (this.mode) {
				case "multiply":
					l = n * r / 255, u = s * i / 255, d = c * a / 255;
					break;
				case "screen":
					l = 255 - (255 - n) * (255 - r) / 255, u = 255 - (255 - s) * (255 - i) / 255, d = 255 - (255 - c) * (255 - a) / 255;
					break;
				case "add":
					l = n + r, u = s + i, d = c + a;
					break;
				case "difference":
					l = Math.abs(n - r), u = Math.abs(s - i), d = Math.abs(c - a);
					break;
				case "subtract":
					l = n - r, u = s - i, d = c - a;
					break;
				case "darken":
					l = Math.min(n, r), u = Math.min(s, i), d = Math.min(c, a);
					break;
				case "lighten":
					l = Math.max(n, r), u = Math.max(s, i), d = Math.max(c, a);
					break;
				case "overlay":
					l = r < 128 ? 2 * n * r / 255 : 255 - 2 * (255 - n) * (255 - r) / 255, u = i < 128 ? 2 * s * i / 255 : 255 - 2 * (255 - s) * (255 - i) / 255, d = a < 128 ? 2 * c * a / 255 : 255 - 2 * (255 - c) * (255 - a) / 255;
					break;
				case "exclusion":
					l = r + n - 2 * r * n / 255, u = i + s - 2 * i * s / 255, d = a + c - 2 * a * c / 255;
					break;
				case "tint": l = r + n * o, u = i + s * o, d = a + c * o;
			}
			e[t] = l, e[t + 1] = u, e[t + 2] = d;
		}
	}
	sendUniformData(e, t) {
		let n = new Xi(this.color).getSource();
		n[0] = this.alpha * n[0] / 255, n[1] = this.alpha * n[1] / 255, n[2] = this.alpha * n[2] / 255, n[3] = this.alpha, e.uniform4fv(t.uColor, n);
	}
};
H(lu, "defaults", {
	color: "#F95C63",
	mode: "multiply",
	alpha: 1
}), H(lu, "type", "BlendColor"), H(lu, "uniformLocations", ["uColor"]), K.setClass(lu);
var uu = {
	multiply: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform sampler2D uImage;\n    uniform vec4 uColor;\n    varying vec2 vTexCoord;\n    varying vec2 vTexCoord2;\n    void main() {\n      vec4 color = texture2D(uTexture, vTexCoord);\n      vec4 color2 = texture2D(uImage, vTexCoord2);\n      color.rgba *= color2.rgba;\n      gl_FragColor = color;\n    }\n    ",
	mask: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform sampler2D uImage;\n    uniform vec4 uColor;\n    varying vec2 vTexCoord;\n    varying vec2 vTexCoord2;\n    void main() {\n      vec4 color = texture2D(uTexture, vTexCoord);\n      vec4 color2 = texture2D(uImage, vTexCoord2);\n      color.a = color2.a;\n      gl_FragColor = color;\n    }\n    "
}, du = class extends Q {
	getCacheKey() {
		return `${this.type}_${this.mode}`;
	}
	getFragmentSource() {
		return uu[this.mode];
	}
	getVertexSource() {
		return "\n    attribute vec2 aPosition;\n    varying vec2 vTexCoord;\n    varying vec2 vTexCoord2;\n    uniform mat3 uTransformMatrix;\n    void main() {\n      vTexCoord = aPosition;\n      vTexCoord2 = (uTransformMatrix * vec3(aPosition, 1.0)).xy;\n      gl_Position = vec4(aPosition * 2.0 - 1.0, 0.0, 1.0);\n    }\n    ";
	}
	applyToWebGL(e) {
		let t = e.context, n = this.createTexture(e.filterBackend, this.image);
		this.bindAdditionalTexture(t, n, t.TEXTURE1), super.applyToWebGL(e), this.unbindAdditionalTexture(t, t.TEXTURE1);
	}
	createTexture(e, t) {
		return e.getCachedTexture(t.cacheKey, t.getElement());
	}
	calculateMatrix() {
		let e = this.image, { width: t, height: n } = e.getElement();
		return [
			1 / e.scaleX,
			0,
			0,
			0,
			1 / e.scaleY,
			0,
			-e.left / t,
			-e.top / n,
			1
		];
	}
	applyTo2d({ imageData: { data: e, width: t, height: n }, filterBackend: { resources: r } }) {
		let i = this.image;
		r.blendImage ||= lr();
		let a = r.blendImage, o = a.getContext("2d");
		a.width !== t || a.height !== n ? (a.width = t, a.height = n) : o.clearRect(0, 0, t, n), o.setTransform(i.scaleX, 0, 0, i.scaleY, i.left, i.top), o.drawImage(i.getElement(), 0, 0, t, n);
		let s = o.getImageData(0, 0, t, n).data;
		for (let t = 0; t < e.length; t += 4) {
			let n = e[t], r = e[t + 1], i = e[t + 2], a = e[t + 3], o = s[t], c = s[t + 1], l = s[t + 2], u = s[t + 3];
			switch (this.mode) {
				case "multiply":
					e[t] = n * o / 255, e[t + 1] = r * c / 255, e[t + 2] = i * l / 255, e[t + 3] = a * u / 255;
					break;
				case "mask": e[t + 3] = u;
			}
		}
	}
	sendUniformData(e, t) {
		let n = this.calculateMatrix();
		e.uniform1i(t.uImage, 1), e.uniformMatrix3fv(t.uTransformMatrix, !1, n);
	}
	toObject() {
		return {
			...super.toObject(),
			image: this.image && this.image.toObject()
		};
	}
	static async fromObject({ type: e, image: t, ...n }, r) {
		return ru.fromObject(t, r).then((e) => new this({
			...n,
			image: e
		}));
	}
};
H(du, "type", "BlendImage"), H(du, "defaults", {
	mode: "multiply",
	alpha: 1
}), H(du, "uniformLocations", ["uTransformMatrix", "uImage"]), K.setClass(du);
var fu = class extends Q {
	getFragmentSource() {
		return "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform vec2 uDelta;\n    varying vec2 vTexCoord;\n    const float nSamples = 15.0;\n    vec3 v3offset = vec3(12.9898, 78.233, 151.7182);\n    float random(vec3 scale) {\n      /* use the fragment position for a different seed per-pixel */\n      return fract(sin(dot(gl_FragCoord.xyz, scale)) * 43758.5453);\n    }\n    void main() {\n      vec4 color = vec4(0.0);\n      float totalC = 0.0;\n      float totalA = 0.0;\n      float offset = random(v3offset);\n      for (float t = -nSamples; t <= nSamples; t++) {\n        float percent = (t + offset - 0.5) / nSamples;\n        vec4 sample = texture2D(uTexture, vTexCoord + uDelta * percent);\n        float weight = 1.0 - abs(percent);\n        float alpha = weight * sample.a;\n        color.rgb += sample.rgb * alpha;\n        color.a += alpha;\n        totalA += weight;\n        totalC += alpha;\n      }\n      gl_FragColor.rgb = color.rgb / totalC;\n      gl_FragColor.a = color.a / totalA;\n    }\n  ";
	}
	applyTo(e) {
		iu(e) ? (this.aspectRatio = e.sourceWidth / e.sourceHeight, e.passes++, this._setupFrameBuffer(e), this.horizontal = !0, this.applyToWebGL(e), this._swapTextures(e), this._setupFrameBuffer(e), this.horizontal = !1, this.applyToWebGL(e), this._swapTextures(e)) : this.applyTo2d(e);
	}
	applyTo2d({ imageData: { data: e, width: t, height: n } }) {
		this.aspectRatio = t / n, this.horizontal = !0;
		let r = this.getBlurValue() * t, i = new Uint8ClampedArray(e), a = 4 * t;
		for (let t = 0; t < e.length; t += 4) {
			let n = 0, o = 0, s = 0, c = 0, l = 0, u = t - t % a, d = u + a;
			for (let i = -14; i < 15; i++) {
				let a = i / 15, f = 4 * Math.floor(r * a), p = 1 - Math.abs(a), m = t + f;
				m < u ? m = u : m > d && (m = d);
				let h = e[m + 3] * p;
				n += e[m] * h, o += e[m + 1] * h, s += e[m + 2] * h, c += h, l += p;
			}
			i[t] = n / c, i[t + 1] = o / c, i[t + 2] = s / c, i[t + 3] = c / l;
		}
		this.horizontal = !1, r = this.getBlurValue() * n;
		for (let t = 0; t < i.length; t += 4) {
			let n = 0, o = 0, s = 0, c = 0, l = 0, u = t % a, d = i.length - a + u;
			for (let e = -14; e < 15; e++) {
				let f = e / 15, p = Math.floor(r * f) * a, m = 1 - Math.abs(f), h = t + p;
				h < u ? h = u : h > d && (h = d);
				let g = i[h + 3] * m;
				n += i[h] * g, o += i[h + 1] * g, s += i[h + 2] * g, c += g, l += m;
			}
			e[t] = n / c, e[t + 1] = o / c, e[t + 2] = s / c, e[t + 3] = c / l;
		}
	}
	sendUniformData(e, t) {
		let n = this.chooseRightDelta();
		e.uniform2fv(t.uDelta, n);
	}
	isNeutralState() {
		return this.blur === 0;
	}
	getBlurValue() {
		let e = 1, { horizontal: t, aspectRatio: n } = this;
		return t ? n > 1 && (e = 1 / n) : n < 1 && (e = n), e * this.blur * .12;
	}
	chooseRightDelta() {
		let e = this.getBlurValue();
		return this.horizontal ? [e, 0] : [0, e];
	}
};
H(fu, "type", "Blur"), H(fu, "defaults", { blur: 0 }), H(fu, "uniformLocations", ["uDelta"]), K.setClass(fu);
var pu = class extends Q {
	getFragmentSource() {
		return "\n  precision highp float;\n  uniform sampler2D uTexture;\n  uniform float uBrightness;\n  varying vec2 vTexCoord;\n  void main() {\n    vec4 color = texture2D(uTexture, vTexCoord);\n    color.rgb += uBrightness;\n    gl_FragColor = color;\n  }\n";
	}
	applyTo2d({ imageData: { data: e } }) {
		let t = Math.round(255 * this.brightness);
		for (let n = 0; n < e.length; n += 4) e[n] += t, e[n + 1] += t, e[n + 2] += t;
	}
	isNeutralState() {
		return this.brightness === 0;
	}
	sendUniformData(e, t) {
		e.uniform1f(t.uBrightness, this.brightness);
	}
};
H(pu, "type", "Brightness"), H(pu, "defaults", { brightness: 0 }), H(pu, "uniformLocations", ["uBrightness"]), K.setClass(pu);
var mu = {
	matrix: [
		1,
		0,
		0,
		0,
		0,
		0,
		1,
		0,
		0,
		0,
		0,
		0,
		1,
		0,
		0,
		0,
		0,
		0,
		1,
		0
	],
	colorsOnly: !0
}, hu = class extends Q {
	getFragmentSource() {
		return "\n  precision highp float;\n  uniform sampler2D uTexture;\n  varying vec2 vTexCoord;\n  uniform mat4 uColorMatrix;\n  uniform vec4 uConstants;\n  void main() {\n    vec4 color = texture2D(uTexture, vTexCoord);\n    color *= uColorMatrix;\n    color += uConstants;\n    gl_FragColor = color;\n  }";
	}
	applyTo2d(e) {
		let t = e.imageData.data, n = this.matrix, r = this.colorsOnly;
		for (let e = 0; e < t.length; e += 4) {
			let i = t[e], a = t[e + 1], o = t[e + 2];
			if (t[e] = i * n[0] + a * n[1] + o * n[2] + 255 * n[4], t[e + 1] = i * n[5] + a * n[6] + o * n[7] + 255 * n[9], t[e + 2] = i * n[10] + a * n[11] + o * n[12] + 255 * n[14], !r) {
				let r = t[e + 3];
				t[e] += r * n[3], t[e + 1] += r * n[8], t[e + 2] += r * n[13], t[e + 3] = i * n[15] + a * n[16] + o * n[17] + r * n[18] + 255 * n[19];
			}
		}
	}
	sendUniformData(e, t) {
		let n = this.matrix, r = [
			n[0],
			n[1],
			n[2],
			n[3],
			n[5],
			n[6],
			n[7],
			n[8],
			n[10],
			n[11],
			n[12],
			n[13],
			n[15],
			n[16],
			n[17],
			n[18]
		], i = [
			n[4],
			n[9],
			n[14],
			n[19]
		];
		e.uniformMatrix4fv(t.uColorMatrix, !1, r), e.uniform4fv(t.uConstants, i);
	}
	toObject() {
		return {
			...super.toObject(),
			matrix: [...this.matrix]
		};
	}
};
function gu(e, t) {
	var n;
	let r = (H(n = class extends hu {
		toObject() {
			return {
				type: this.type,
				colorsOnly: this.colorsOnly
			};
		}
	}, "type", e), H(n, "defaults", {
		colorsOnly: !1,
		matrix: t
	}), n);
	return K.setClass(r, e), r;
}
H(hu, "type", "ColorMatrix"), H(hu, "defaults", mu), H(hu, "uniformLocations", ["uColorMatrix", "uConstants"]), K.setClass(hu);
var _u = gu("Brownie", [
	.5997,
	.34553,
	-.27082,
	0,
	.186,
	-.0377,
	.86095,
	.15059,
	0,
	-.1449,
	.24113,
	-.07441,
	.44972,
	0,
	-.02965,
	0,
	0,
	0,
	1,
	0
]), vu = gu("Vintage", [
	.62793,
	.32021,
	-.03965,
	0,
	.03784,
	.02578,
	.64411,
	.03259,
	0,
	.02926,
	.0466,
	-.08512,
	.52416,
	0,
	.02023,
	0,
	0,
	0,
	1,
	0
]), yu = gu("Kodachrome", [
	1.12855,
	-.39673,
	-.03992,
	0,
	.24991,
	-.16404,
	1.08352,
	-.05498,
	0,
	.09698,
	-.16786,
	-.56034,
	1.60148,
	0,
	.13972,
	0,
	0,
	0,
	1,
	0
]), bu = gu("Technicolor", [
	1.91252,
	-.85453,
	-.09155,
	0,
	.04624,
	-.30878,
	1.76589,
	-.10601,
	0,
	-.27589,
	-.2311,
	-.75018,
	1.84759,
	0,
	.12137,
	0,
	0,
	0,
	1,
	0
]), xu = gu("Polaroid", [
	1.438,
	-.062,
	-.062,
	0,
	0,
	-.122,
	1.378,
	-.122,
	0,
	0,
	-.016,
	-.016,
	1.483,
	0,
	0,
	0,
	0,
	0,
	1,
	0
]), Su = gu("Sepia", [
	.393,
	.769,
	.189,
	0,
	0,
	.349,
	.686,
	.168,
	0,
	0,
	.272,
	.534,
	.131,
	0,
	0,
	0,
	0,
	0,
	1,
	0
]), Cu = gu("BlackWhite", [
	1.5,
	1.5,
	1.5,
	0,
	-1,
	1.5,
	1.5,
	1.5,
	0,
	-1,
	1.5,
	1.5,
	1.5,
	0,
	-1,
	0,
	0,
	0,
	1,
	0
]), wu = class extends Q {
	constructor(e = {}) {
		super(e), this.subFilters = e.subFilters || [];
	}
	applyTo(e) {
		iu(e) && (e.passes += this.subFilters.length - 1), this.subFilters.forEach((t) => {
			t.applyTo(e);
		});
	}
	toObject() {
		return {
			type: this.type,
			subFilters: this.subFilters.map((e) => e.toObject())
		};
	}
	isNeutralState() {
		return !this.subFilters.some((e) => !e.isNeutralState());
	}
	static fromObject(e, t) {
		return Promise.all((e.subFilters || []).map((e) => K.getClass(e.type).fromObject(e, t))).then((e) => new this({ subFilters: e }));
	}
};
H(wu, "type", "Composed"), K.setClass(wu);
var Tu = class extends Q {
	getFragmentSource() {
		return "\n  precision highp float;\n  uniform sampler2D uTexture;\n  uniform float uContrast;\n  varying vec2 vTexCoord;\n  void main() {\n    vec4 color = texture2D(uTexture, vTexCoord);\n    float contrastF = 1.015 * (uContrast + 1.0) / (1.0 * (1.015 - uContrast));\n    color.rgb = contrastF * (color.rgb - 0.5) + 0.5;\n    gl_FragColor = color;\n  }";
	}
	isNeutralState() {
		return this.contrast === 0;
	}
	applyTo2d({ imageData: { data: e } }) {
		let t = Math.floor(255 * this.contrast), n = 259 * (t + 255) / (255 * (259 - t));
		for (let t = 0; t < e.length; t += 4) e[t] = n * (e[t] - 128) + 128, e[t + 1] = n * (e[t + 1] - 128) + 128, e[t + 2] = n * (e[t + 2] - 128) + 128;
	}
	sendUniformData(e, t) {
		e.uniform1f(t.uContrast, this.contrast);
	}
};
H(Tu, "type", "Contrast"), H(Tu, "defaults", { contrast: 0 }), H(Tu, "uniformLocations", ["uContrast"]), K.setClass(Tu);
var Eu = {
	Convolute_3_1: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[9];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 0);\n      for (float h = 0.0; h < 3.0; h+=1.0) {\n        for (float w = 0.0; w < 3.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 1), uStepH * (h - 1));\n          color += texture2D(uTexture, vTexCoord + matrixPos) * uMatrix[int(h * 3.0 + w)];\n        }\n      }\n      gl_FragColor = color;\n    }\n    ",
	Convolute_3_0: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[9];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 1);\n      for (float h = 0.0; h < 3.0; h+=1.0) {\n        for (float w = 0.0; w < 3.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 1.0), uStepH * (h - 1.0));\n          color.rgb += texture2D(uTexture, vTexCoord + matrixPos).rgb * uMatrix[int(h * 3.0 + w)];\n        }\n      }\n      float alpha = texture2D(uTexture, vTexCoord).a;\n      gl_FragColor = color;\n      gl_FragColor.a = alpha;\n    }\n    ",
	Convolute_5_1: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[25];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 0);\n      for (float h = 0.0; h < 5.0; h+=1.0) {\n        for (float w = 0.0; w < 5.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 2.0), uStepH * (h - 2.0));\n          color += texture2D(uTexture, vTexCoord + matrixPos) * uMatrix[int(h * 5.0 + w)];\n        }\n      }\n      gl_FragColor = color;\n    }\n    ",
	Convolute_5_0: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[25];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 1);\n      for (float h = 0.0; h < 5.0; h+=1.0) {\n        for (float w = 0.0; w < 5.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 2.0), uStepH * (h - 2.0));\n          color.rgb += texture2D(uTexture, vTexCoord + matrixPos).rgb * uMatrix[int(h * 5.0 + w)];\n        }\n      }\n      float alpha = texture2D(uTexture, vTexCoord).a;\n      gl_FragColor = color;\n      gl_FragColor.a = alpha;\n    }\n    ",
	Convolute_7_1: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[49];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 0);\n      for (float h = 0.0; h < 7.0; h+=1.0) {\n        for (float w = 0.0; w < 7.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 3.0), uStepH * (h - 3.0));\n          color += texture2D(uTexture, vTexCoord + matrixPos) * uMatrix[int(h * 7.0 + w)];\n        }\n      }\n      gl_FragColor = color;\n    }\n    ",
	Convolute_7_0: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[49];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 1);\n      for (float h = 0.0; h < 7.0; h+=1.0) {\n        for (float w = 0.0; w < 7.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 3.0), uStepH * (h - 3.0));\n          color.rgb += texture2D(uTexture, vTexCoord + matrixPos).rgb * uMatrix[int(h * 7.0 + w)];\n        }\n      }\n      float alpha = texture2D(uTexture, vTexCoord).a;\n      gl_FragColor = color;\n      gl_FragColor.a = alpha;\n    }\n    ",
	Convolute_9_1: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[81];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 0);\n      for (float h = 0.0; h < 9.0; h+=1.0) {\n        for (float w = 0.0; w < 9.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 4.0), uStepH * (h - 4.0));\n          color += texture2D(uTexture, vTexCoord + matrixPos) * uMatrix[int(h * 9.0 + w)];\n        }\n      }\n      gl_FragColor = color;\n    }\n    ",
	Convolute_9_0: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[81];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 1);\n      for (float h = 0.0; h < 9.0; h+=1.0) {\n        for (float w = 0.0; w < 9.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 4.0), uStepH * (h - 4.0));\n          color.rgb += texture2D(uTexture, vTexCoord + matrixPos).rgb * uMatrix[int(h * 9.0 + w)];\n        }\n      }\n      float alpha = texture2D(uTexture, vTexCoord).a;\n      gl_FragColor = color;\n      gl_FragColor.a = alpha;\n    }\n    "
}, Du = class extends Q {
	getCacheKey() {
		return `${this.type}_${Math.sqrt(this.matrix.length)}_${+!!this.opaque}`;
	}
	getFragmentSource() {
		return Eu[this.getCacheKey()];
	}
	applyTo2d(e) {
		let t = e.imageData, n = t.data, r = this.matrix, i = Math.round(Math.sqrt(r.length)), a = Math.floor(i / 2), o = t.width, s = t.height, c = e.ctx.createImageData(o, s), l = c.data, u = +!!this.opaque, d, f, p, m, h, g, _, v, y, b, x, S, C;
		for (x = 0; x < s; x++) for (b = 0; b < o; b++) {
			for (h = 4 * (x * o + b), d = 0, f = 0, p = 0, m = 0, C = 0; C < i; C++) for (S = 0; S < i; S++) _ = x + C - a, g = b + S - a, _ < 0 || _ >= s || g < 0 || g >= o || (v = 4 * (_ * o + g), y = r[C * i + S], d += n[v] * y, f += n[v + 1] * y, p += n[v + 2] * y, u || (m += n[v + 3] * y));
			l[h] = d, l[h + 1] = f, l[h + 2] = p, l[h + 3] = u ? n[h + 3] : m;
		}
		e.imageData = c;
	}
	sendUniformData(e, t) {
		e.uniform1fv(t.uMatrix, this.matrix);
	}
	toObject() {
		return {
			...super.toObject(),
			opaque: this.opaque,
			matrix: [...this.matrix]
		};
	}
};
H(Du, "type", "Convolute"), H(Du, "defaults", {
	opaque: !1,
	matrix: [
		0,
		0,
		0,
		0,
		1,
		0,
		0,
		0,
		0
	]
}), H(Du, "uniformLocations", [
	"uMatrix",
	"uOpaque",
	"uHalfSize",
	"uSize"
]), K.setClass(Du);
var Ou = "Gamma", ku = class extends Q {
	getFragmentSource() {
		return "\n  precision highp float;\n  uniform sampler2D uTexture;\n  uniform vec3 uGamma;\n  varying vec2 vTexCoord;\n  void main() {\n    vec4 color = texture2D(uTexture, vTexCoord);\n    vec3 correction = (1.0 / uGamma);\n    color.r = pow(color.r, correction.r);\n    color.g = pow(color.g, correction.g);\n    color.b = pow(color.b, correction.b);\n    gl_FragColor = color;\n    gl_FragColor.rgb *= color.a;\n  }\n";
	}
	constructor(e = {}) {
		super(e), this.gamma = e.gamma || this.constructor.defaults.gamma.concat();
	}
	applyTo2d({ imageData: { data: e } }) {
		let t = this.gamma, n = 1 / t[0], r = 1 / t[1], i = 1 / t[2];
		this.rgbValues ||= {
			r: /* @__PURE__ */ new Uint8Array(256),
			g: /* @__PURE__ */ new Uint8Array(256),
			b: /* @__PURE__ */ new Uint8Array(256)
		};
		let a = this.rgbValues;
		for (let e = 0; e < 256; e++) a.r[e] = 255 * (e / 255) ** n, a.g[e] = 255 * (e / 255) ** r, a.b[e] = 255 * (e / 255) ** i;
		for (let t = 0; t < e.length; t += 4) e[t] = a.r[e[t]], e[t + 1] = a.g[e[t + 1]], e[t + 2] = a.b[e[t + 2]];
	}
	sendUniformData(e, t) {
		e.uniform3fv(t.uGamma, this.gamma);
	}
	isNeutralState() {
		let { gamma: e } = this;
		return e[0] === 1 && e[1] === 1 && e[2] === 1;
	}
	toObject() {
		return {
			type: Ou,
			gamma: this.gamma.concat()
		};
	}
};
H(ku, "type", Ou), H(ku, "defaults", { gamma: [
	1,
	1,
	1
] }), H(ku, "uniformLocations", ["uGamma"]), K.setClass(ku);
var Au = {
	average: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = texture2D(uTexture, vTexCoord);\n      float average = (color.r + color.b + color.g) / 3.0;\n      gl_FragColor = vec4(average, average, average, color.a);\n    }\n    ",
	lightness: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform int uMode;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 col = texture2D(uTexture, vTexCoord);\n      float average = (max(max(col.r, col.g),col.b) + min(min(col.r, col.g),col.b)) / 2.0;\n      gl_FragColor = vec4(average, average, average, col.a);\n    }\n    ",
	luminosity: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform int uMode;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 col = texture2D(uTexture, vTexCoord);\n      float average = 0.21 * col.r + 0.72 * col.g + 0.07 * col.b;\n      gl_FragColor = vec4(average, average, average, col.a);\n    }\n    "
}, ju = class extends Q {
	applyTo2d({ imageData: { data: e } }) {
		for (let t, n = 0; n < e.length; n += 4) {
			let r = e[n], i = e[n + 1], a = e[n + 2];
			switch (this.mode) {
				case "average":
					t = (r + i + a) / 3;
					break;
				case "lightness":
					t = (Math.min(r, i, a) + Math.max(r, i, a)) / 2;
					break;
				case "luminosity": t = .21 * r + .72 * i + .07 * a;
			}
			e[n + 2] = e[n + 1] = e[n] = t;
		}
	}
	getCacheKey() {
		return `${this.type}_${this.mode}`;
	}
	getFragmentSource() {
		return Au[this.mode];
	}
	sendUniformData(e, t) {
		e.uniform1i(t.uMode, 1);
	}
	isNeutralState() {
		return !1;
	}
};
H(ju, "type", "Grayscale"), H(ju, "defaults", { mode: "average" }), H(ju, "uniformLocations", ["uMode"]), K.setClass(ju);
var Mu = {
	...mu,
	rotation: 0
}, Nu = class extends hu {
	calculateMatrix() {
		let e = this.rotation * Math.PI, t = $n(e), n = er(e), r = 1 / 3, i = Math.sqrt(r) * n, a = 1 - t;
		this.matrix = [
			t + a / 3,
			r * a - i,
			r * a + i,
			0,
			0,
			r * a + i,
			t + r * a,
			r * a - i,
			0,
			0,
			r * a - i,
			r * a + i,
			t + r * a,
			0,
			0,
			0,
			0,
			0,
			1,
			0
		];
	}
	isNeutralState() {
		return this.rotation === 0;
	}
	applyTo(e) {
		this.calculateMatrix(), super.applyTo(e);
	}
	toObject() {
		return {
			type: this.type,
			rotation: this.rotation
		};
	}
};
H(Nu, "type", "HueRotation"), H(Nu, "defaults", Mu), K.setClass(Nu);
var Pu = class extends Q {
	applyTo2d({ imageData: { data: e } }) {
		for (let t = 0; t < e.length; t += 4) e[t] = 255 - e[t], e[t + 1] = 255 - e[t + 1], e[t + 2] = 255 - e[t + 2], this.alpha && (e[t + 3] = 255 - e[t + 3]);
	}
	getFragmentSource() {
		return "\n  precision highp float;\n  uniform sampler2D uTexture;\n  uniform int uInvert;\n  uniform int uAlpha;\n  varying vec2 vTexCoord;\n  void main() {\n    vec4 color = texture2D(uTexture, vTexCoord);\n    if (uInvert == 1) {\n      if (uAlpha == 1) {\n        gl_FragColor = vec4(1.0 - color.r,1.0 -color.g,1.0 -color.b,1.0 -color.a);\n      } else {\n        gl_FragColor = vec4(1.0 - color.r,1.0 -color.g,1.0 -color.b,color.a);\n      }\n    } else {\n      gl_FragColor = color;\n    }\n  }\n";
	}
	isNeutralState() {
		return !this.invert;
	}
	sendUniformData(e, t) {
		e.uniform1i(t.uInvert, Number(this.invert)), e.uniform1i(t.uAlpha, Number(this.alpha));
	}
};
H(Pu, "type", "Invert"), H(Pu, "defaults", {
	alpha: !1,
	invert: !0
}), H(Pu, "uniformLocations", ["uInvert", "uAlpha"]), K.setClass(Pu);
var Fu = class extends Q {
	getFragmentSource() {
		return "\n  precision highp float;\n  uniform sampler2D uTexture;\n  uniform float uStepH;\n  uniform float uNoise;\n  uniform float uSeed;\n  varying vec2 vTexCoord;\n  float rand(vec2 co, float seed, float vScale) {\n    return fract(sin(dot(co.xy * vScale ,vec2(12.9898 , 78.233))) * 43758.5453 * (seed + 0.01) / 2.0);\n  }\n  void main() {\n    vec4 color = texture2D(uTexture, vTexCoord);\n    color.rgb += (0.5 - rand(vTexCoord, uSeed, 0.1 / uStepH)) * uNoise;\n    gl_FragColor = color;\n  }\n";
	}
	applyTo2d({ imageData: { data: e } }) {
		let t = this.noise;
		for (let n = 0; n < e.length; n += 4) {
			let r = (.5 - Math.random()) * t;
			e[n] += r, e[n + 1] += r, e[n + 2] += r;
		}
	}
	sendUniformData(e, t) {
		e.uniform1f(t.uNoise, this.noise / 255), e.uniform1f(t.uSeed, Math.random());
	}
	isNeutralState() {
		return this.noise === 0;
	}
};
H(Fu, "type", "Noise"), H(Fu, "defaults", { noise: 0 }), H(Fu, "uniformLocations", ["uNoise", "uSeed"]), K.setClass(Fu);
var Iu = class extends Q {
	applyTo2d({ imageData: { data: e, width: t, height: n } }) {
		for (let r = 0; r < n; r += this.blocksize) for (let i = 0; i < t; i += this.blocksize) {
			let a = 4 * r * t + 4 * i, o = e[a], s = e[a + 1], c = e[a + 2], l = e[a + 3];
			for (let a = r; a < Math.min(r + this.blocksize, n); a++) for (let n = i; n < Math.min(i + this.blocksize, t); n++) {
				let r = 4 * a * t + 4 * n;
				e[r] = o, e[r + 1] = s, e[r + 2] = c, e[r + 3] = l;
			}
		}
	}
	isNeutralState() {
		return this.blocksize === 1;
	}
	getFragmentSource() {
		return "\n  precision highp float;\n  uniform sampler2D uTexture;\n  uniform float uBlocksize;\n  uniform float uStepW;\n  uniform float uStepH;\n  varying vec2 vTexCoord;\n  void main() {\n    float blockW = uBlocksize * uStepW;\n    float blockH = uBlocksize * uStepH;\n    int posX = int(vTexCoord.x / blockW);\n    int posY = int(vTexCoord.y / blockH);\n    float fposX = float(posX);\n    float fposY = float(posY);\n    vec2 squareCoords = vec2(fposX * blockW, fposY * blockH);\n    vec4 color = texture2D(uTexture, squareCoords);\n    gl_FragColor = color;\n  }\n";
	}
	sendUniformData(e, t) {
		e.uniform1f(t.uBlocksize, this.blocksize);
	}
};
H(Iu, "type", "Pixelate"), H(Iu, "defaults", { blocksize: 4 }), H(Iu, "uniformLocations", ["uBlocksize"]), K.setClass(Iu);
var Lu = class extends Q {
	getFragmentSource() {
		return "\nprecision highp float;\nuniform sampler2D uTexture;\nuniform vec4 uLow;\nuniform vec4 uHigh;\nvarying vec2 vTexCoord;\nvoid main() {\n  gl_FragColor = texture2D(uTexture, vTexCoord);\n  if(all(greaterThan(gl_FragColor.rgb,uLow.rgb)) && all(greaterThan(uHigh.rgb,gl_FragColor.rgb))) {\n    gl_FragColor.a = 0.0;\n  }\n}\n";
	}
	applyTo2d({ imageData: { data: e } }) {
		let t = 255 * this.distance, n = new Xi(this.color).getSource(), r = [
			n[0] - t,
			n[1] - t,
			n[2] - t
		], i = [
			n[0] + t,
			n[1] + t,
			n[2] + t
		];
		for (let t = 0; t < e.length; t += 4) {
			let n = e[t], a = e[t + 1], o = e[t + 2];
			n > r[0] && a > r[1] && o > r[2] && n < i[0] && a < i[1] && o < i[2] && (e[t + 3] = 0);
		}
	}
	sendUniformData(e, t) {
		let n = new Xi(this.color).getSource(), r = this.distance, i = [
			0 + n[0] / 255 - r,
			0 + n[1] / 255 - r,
			0 + n[2] / 255 - r,
			1
		], a = [
			n[0] / 255 + r,
			n[1] / 255 + r,
			n[2] / 255 + r,
			1
		];
		e.uniform4fv(t.uLow, i), e.uniform4fv(t.uHigh, a);
	}
};
H(Lu, "type", "RemoveColor"), H(Lu, "defaults", {
	color: "#FFFFFF",
	distance: .02,
	useAlpha: !1
}), H(Lu, "uniformLocations", ["uLow", "uHigh"]), K.setClass(Lu);
var Ru = class extends Q {
	sendUniformData(e, t) {
		e.uniform2fv(t.uDelta, this.horizontal ? [1 / this.width, 0] : [0, 1 / this.height]), e.uniform1fv(t.uTaps, this.taps);
	}
	getFilterWindow() {
		let e = this.tempScale;
		return Math.ceil(this.lanczosLobes / e);
	}
	getCacheKey() {
		let e = this.getFilterWindow();
		return `${this.type}_${e}`;
	}
	getFragmentSource() {
		let e = this.getFilterWindow();
		return this.generateShader(e);
	}
	getTaps() {
		let e = this.lanczosCreate(this.lanczosLobes), t = this.tempScale, n = this.getFilterWindow(), r = Array(n);
		for (let i = 1; i <= n; i++) r[i - 1] = e(i * t);
		return r;
	}
	generateShader(e) {
		let t = Array(e);
		for (let n = 1; n <= e; n++) t[n - 1] = `${n}.0 * uDelta`;
		return `\n      precision highp float;\n      uniform sampler2D uTexture;\n      uniform vec2 uDelta;\n      varying vec2 vTexCoord;\n      uniform float uTaps[${e}];\n      void main() {\n        vec4 color = texture2D(uTexture, vTexCoord);\n        float sum = 1.0;\n        ${t.map((e, t) => `\n              color += texture2D(uTexture, vTexCoord + ${e}) * uTaps[${t}] + texture2D(uTexture, vTexCoord - ${e}) * uTaps[${t}];\n              sum += 2.0 * uTaps[${t}];\n            `).join("\n")}\n        gl_FragColor = color / sum;\n      }\n    `;
	}
	applyToForWebgl(e) {
		e.passes++, this.width = e.sourceWidth, this.horizontal = !0, this.dW = Math.round(this.width * this.scaleX), this.dH = e.sourceHeight, this.tempScale = this.dW / this.width, this.taps = this.getTaps(), e.destinationWidth = this.dW, super.applyTo(e), e.sourceWidth = e.destinationWidth, this.height = e.sourceHeight, this.horizontal = !1, this.dH = Math.round(this.height * this.scaleY), this.tempScale = this.dH / this.height, this.taps = this.getTaps(), e.destinationHeight = this.dH, super.applyTo(e), e.sourceHeight = e.destinationHeight;
	}
	applyTo(e) {
		iu(e) ? this.applyToForWebgl(e) : this.applyTo2d(e);
	}
	isNeutralState() {
		return this.scaleX === 1 && this.scaleY === 1;
	}
	lanczosCreate(e) {
		return (t) => {
			if (t >= e || t <= -e) return 0;
			if (t < 1.1920929e-7 && t > -1.1920929e-7) return 1;
			let n = (t *= Math.PI) / e;
			return Math.sin(t) / t * Math.sin(n) / n;
		};
	}
	applyTo2d(e) {
		let t = e.imageData, n = this.scaleX, r = this.scaleY;
		this.rcpScaleX = 1 / n, this.rcpScaleY = 1 / r;
		let i = t.width, a = t.height, o = Math.round(i * n), s = Math.round(a * r), c;
		c = this.resizeType === "sliceHack" ? this.sliceByTwo(e, i, a, o, s) : this.resizeType === "hermite" ? this.hermiteFastResize(e, i, a, o, s) : this.resizeType === "bilinear" ? this.bilinearFiltering(e, i, a, o, s) : this.resizeType === "lanczos" ? this.lanczosResize(e, i, a, o, s) : new ImageData(o, s), e.imageData = c;
	}
	sliceByTwo(e, t, n, r, i) {
		let a = e.imageData, o = .5, s = !1, c = !1, l = t * o, u = n * o, d = e.filterBackend.resources, f = 0, p = 0, m = t, h = 0;
		d.sliceByTwo ||= lr();
		let g = d.sliceByTwo;
		(g.width < 1.5 * t || g.height < n) && (g.width = 1.5 * t, g.height = n);
		let _ = g.getContext("2d");
		for (_.clearRect(0, 0, 1.5 * t, n), _.putImageData(a, 0, 0), r = Math.floor(r), i = Math.floor(i); !s || !c;) t = l, n = u, r < Math.floor(l * o) ? l = Math.floor(l * o) : (l = r, s = !0), i < Math.floor(u * o) ? u = Math.floor(u * o) : (u = i, c = !0), _.drawImage(g, f, p, t, n, m, h, l, u), f = m, p = h, h += u;
		return _.getImageData(f, p, r, i);
	}
	lanczosResize(e, t, n, r, i) {
		let a = e.imageData.data, o = e.ctx.createImageData(r, i), s = o.data, c = this.lanczosCreate(this.lanczosLobes), l = this.rcpScaleX, u = this.rcpScaleY, d = 2 / this.rcpScaleX, f = 2 / this.rcpScaleY, p = Math.ceil(l * this.lanczosLobes / 2), m = Math.ceil(u * this.lanczosLobes / 2), h = {}, g = {
			x: 0,
			y: 0
		}, _ = {
			x: 0,
			y: 0
		};
		return function e(v) {
			let y, b, x, S, C, w, T, E, D, O, ee;
			for (g.x = (v + .5) * l, _.x = Math.floor(g.x), y = 0; y < i; y++) {
				for (g.y = (y + .5) * u, _.y = Math.floor(g.y), C = 0, w = 0, T = 0, E = 0, D = 0, b = _.x - p; b <= _.x + p; b++) if (!(b < 0 || b >= t)) {
					O = Math.floor(1e3 * Math.abs(b - g.x)), h[O] || (h[O] = {});
					for (let e = _.y - m; e <= _.y + m; e++) e < 0 || e >= n || (ee = Math.floor(1e3 * Math.abs(e - g.y)), h[O][ee] || (h[O][ee] = c(Math.sqrt((O * d) ** 2 + (ee * f) ** 2) / 1e3)), x = h[O][ee], x > 0 && (S = 4 * (e * t + b), C += x, w += x * a[S], T += x * a[S + 1], E += x * a[S + 2], D += x * a[S + 3]));
				}
				S = 4 * (y * r + v), s[S] = w / C, s[S + 1] = T / C, s[S + 2] = E / C, s[S + 3] = D / C;
			}
			return ++v < r ? e(v) : o;
		}(0);
	}
	bilinearFiltering(e, t, n, r, i) {
		let a, o, s, c, l, u, d, f, p, m, h, g, _, v = 0, y = this.rcpScaleX, b = this.rcpScaleY, x = 4 * (t - 1), S = e.imageData.data, C = e.ctx.createImageData(r, i), w = C.data;
		for (d = 0; d < i; d++) for (f = 0; f < r; f++) for (l = Math.floor(y * f), u = Math.floor(b * d), p = y * f - l, m = b * d - u, _ = 4 * (u * t + l), h = 0; h < 4; h++) a = S[_ + h], o = S[_ + 4 + h], s = S[_ + x + h], c = S[_ + x + 4 + h], g = a * (1 - p) * (1 - m) + o * p * (1 - m) + s * m * (1 - p) + c * p * m, w[v++] = g;
		return C;
	}
	hermiteFastResize(e, t, n, r, i) {
		let a = this.rcpScaleX, o = this.rcpScaleY, s = Math.ceil(a / 2), c = Math.ceil(o / 2), l = e.imageData.data, u = e.ctx.createImageData(r, i), d = u.data;
		for (let e = 0; e < i; e++) for (let n = 0; n < r; n++) {
			let i = 4 * (n + e * r), u, f = 0, p = 0, m = 0, h = 0, g = 0, _ = 0, v = (e + .5) * o;
			for (let r = Math.floor(e * o); r < (e + 1) * o; r++) {
				let e = Math.abs(v - (r + .5)) / c, i = (n + .5) * a, o = e * e;
				for (let e = Math.floor(n * a); e < (n + 1) * a; e++) {
					let n = Math.abs(i - (e + .5)) / s, a = Math.sqrt(o + n * n);
					a > 1 && a < -1 || (u = 2 * a * a * a - 3 * a * a + 1, u > 0 && (n = 4 * (e + r * t), _ += u * l[n + 3], p += u, l[n + 3] < 255 && (u = u * l[n + 3] / 250), m += u * l[n], h += u * l[n + 1], g += u * l[n + 2], f += u));
				}
			}
			d[i] = m / f, d[i + 1] = h / f, d[i + 2] = g / f, d[i + 3] = _ / p;
		}
		return u;
	}
};
H(Ru, "type", "Resize"), H(Ru, "defaults", {
	resizeType: "hermite",
	scaleX: 1,
	scaleY: 1,
	lanczosLobes: 3
}), H(Ru, "uniformLocations", ["uDelta", "uTaps"]), K.setClass(Ru);
var zu = class extends Q {
	getFragmentSource() {
		return "\n  precision highp float;\n  uniform sampler2D uTexture;\n  uniform float uSaturation;\n  varying vec2 vTexCoord;\n  void main() {\n    vec4 color = texture2D(uTexture, vTexCoord);\n    float rgMax = max(color.r, color.g);\n    float rgbMax = max(rgMax, color.b);\n    color.r += rgbMax != color.r ? (rgbMax - color.r) * uSaturation : 0.00;\n    color.g += rgbMax != color.g ? (rgbMax - color.g) * uSaturation : 0.00;\n    color.b += rgbMax != color.b ? (rgbMax - color.b) * uSaturation : 0.00;\n    gl_FragColor = color;\n  }\n";
	}
	applyTo2d({ imageData: { data: e } }) {
		let t = -this.saturation;
		for (let n = 0; n < e.length; n += 4) {
			let r = e[n], i = e[n + 1], a = e[n + 2], o = Math.max(r, i, a);
			e[n] += o === r ? 0 : (o - r) * t, e[n + 1] += o === i ? 0 : (o - i) * t, e[n + 2] += o === a ? 0 : (o - a) * t;
		}
	}
	sendUniformData(e, t) {
		e.uniform1f(t.uSaturation, -this.saturation);
	}
	isNeutralState() {
		return this.saturation === 0;
	}
};
H(zu, "type", "Saturation"), H(zu, "defaults", { saturation: 0 }), H(zu, "uniformLocations", ["uSaturation"]), K.setClass(zu);
var Bu = class extends Q {
	getFragmentSource() {
		return "\n  precision highp float;\n  uniform sampler2D uTexture;\n  uniform float uVibrance;\n  varying vec2 vTexCoord;\n  void main() {\n    vec4 color = texture2D(uTexture, vTexCoord);\n    float max = max(color.r, max(color.g, color.b));\n    float avg = (color.r + color.g + color.b) / 3.0;\n    float amt = (abs(max - avg) * 2.0) * uVibrance;\n    color.r += max != color.r ? (max - color.r) * amt : 0.00;\n    color.g += max != color.g ? (max - color.g) * amt : 0.00;\n    color.b += max != color.b ? (max - color.b) * amt : 0.00;\n    gl_FragColor = color;\n  }\n";
	}
	applyTo2d({ imageData: { data: e } }) {
		let t = -this.vibrance;
		for (let n = 0; n < e.length; n += 4) {
			let r = e[n], i = e[n + 1], a = e[n + 2], o = Math.max(r, i, a), s = (r + i + a) / 3, c = 2 * Math.abs(o - s) / 255 * t;
			e[n] += o === r ? 0 : (o - r) * c, e[n + 1] += o === i ? 0 : (o - i) * c, e[n + 2] += o === a ? 0 : (o - a) * c;
		}
	}
	sendUniformData(e, t) {
		e.uniform1f(t.uVibrance, -this.vibrance);
	}
	isNeutralState() {
		return this.vibrance === 0;
	}
};
H(Bu, "type", "Vibrance"), H(Bu, "defaults", { vibrance: 0 }), H(Bu, "uniformLocations", ["uVibrance"]), K.setClass(Bu), an({
	BaseFilter: () => Q,
	BlackWhite: () => Cu,
	BlendColor: () => lu,
	BlendImage: () => du,
	Blur: () => fu,
	Brightness: () => pu,
	Brownie: () => _u,
	ColorMatrix: () => hu,
	Composed: () => wu,
	Contrast: () => Tu,
	Convolute: () => Du,
	Gamma: () => ku,
	Grayscale: () => ju,
	HueRotation: () => Nu,
	Invert: () => Pu,
	Kodachrome: () => yu,
	Noise: () => Fu,
	Pixelate: () => Iu,
	Polaroid: () => xu,
	RemoveColor: () => Lu,
	Resize: () => Ru,
	Saturation: () => zu,
	Sepia: () => Su,
	Technicolor: () => bu,
	Vibrance: () => Bu,
	Vintage: () => vu
});
//#endregion
//#region frontend/canvas/src/canvas/object-factory.ts
var Vu = "__canvasPresentation", Hu = {
	product_source: "#fef3c7",
	sku_reference: "#ffedd5",
	auto_cutout: "#ecfccb",
	prompt: "#e0e7ff",
	model_generation: "#dbeafe",
	main_output: "#dcfce7",
	sku_output: "#ccfbf1",
	detail_output: "#cffafe",
	text_layer: "#fae8ff",
	composition_group: "#f3e8ff",
	export: "#f1f5f9"
};
function Uu(e, t, n, r = {}) {
	return { [Vu]: {
		key: e,
		role: t,
		domainId: n,
		...r
	} };
}
function Wu(e, t) {
	return e.set(t), e.setCoords(), e;
}
function Gu(e, t, n) {
	return e.layoutState.nodePositions[t] ?? {
		x: n * 220,
		y: Math.floor(n / 4) * 140
	};
}
function Ku(e) {
	let t = e.prompt?.trim();
	return t === void 0 || t.length === 0 ? e.kind : `${e.kind}: ${t}`;
}
function qu(e, t) {
	let n = `node:${e.id}`, r = e.kind === "product_source" || e.kind === "auto_cutout", i = {
		left: t.x,
		top: t.y,
		width: 180,
		height: 96,
		rx: 12,
		ry: 12,
		originX: "center",
		originY: "center",
		fill: Hu[e.kind],
		stroke: "#334155",
		strokeWidth: 1.5,
		label: Ku(e),
		visible: !0,
		selectable: !r,
		evented: !r,
		...Uu(n, "node", e.id, {
			node: structuredClone(e),
			outputType: e.kind === "main_output" ? "main" : e.kind === "sku_output" ? "sku" : e.kind === "detail_output" ? "detail" : void 0
		})
	};
	return {
		kind: "sync",
		key: n,
		role: "node",
		domainId: e.id,
		fingerprint: JSON.stringify({
			node: e,
			position: t
		}),
		properties: i,
		create: () => Wu(new Rs(), i)
	};
}
function Ju(e, t, n, r) {
	let i = `edge:${e.id}`, a = r === "advanced", o = {
		x1: t.x,
		y1: t.y,
		x2: n.x,
		y2: n.y,
		stroke: "#64748b",
		strokeWidth: 2,
		selectable: !1,
		evented: !1,
		visible: a,
		...Uu(i, "edge", e.id)
	};
	return {
		kind: "sync",
		key: i,
		role: "edge",
		domainId: e.id,
		fingerprint: JSON.stringify({
			edge: e,
			source: t,
			target: n,
			visible: a
		}),
		properties: o,
		create: () => Wu(new yl([
			t.x,
			t.y,
			n.x,
			n.y
		]), o)
	};
}
function Yu(e, t, n, r) {
	let i = t === "source" ? e.sourceNodeId : e.targetNodeId, a = t === "source" ? e.sourcePort : e.targetPort, o = `port:${e.id}:${t}`, s = r === "advanced", c = {
		left: n.x,
		top: n.y,
		radius: 6,
		originX: "center",
		originY: "center",
		fill: t === "source" ? "#2563eb" : "#7c3aed",
		stroke: "#ffffff",
		strokeWidth: 1,
		selectable: !1,
		evented: !1,
		visible: s,
		...Uu(o, "port", `${i}:${a}`)
	};
	return {
		kind: "sync",
		key: o,
		role: "port",
		domainId: `${i}:${a}`,
		fingerprint: JSON.stringify({
			edgeId: e.id,
			end: t,
			position: n,
			visible: s
		}),
		properties: c,
		create: () => Wu(new _l(), c)
	};
}
function Xu(e, t) {
	let n = e.layoutState.objectTransforms[t.transformId];
	if (n === void 0) throw Error(`missing validated transform ${t.transformId}`);
	let r = `product:${t.id}`, i = {
		left: n.x,
		top: n.y,
		scaleX: n.scale,
		scaleY: n.scale,
		angle: n.rotation,
		cropX: 0,
		cropY: 0,
		skewX: 0,
		skewY: 0,
		flipX: !1,
		flipY: !1,
		filters: [],
		opacity: 1,
		globalCompositeOperation: "source-over",
		originX: "center",
		originY: "center",
		selectable: !t.locked,
		evented: !t.locked,
		visible: !0,
		...Uu(r, "product", t.id)
	};
	return {
		kind: "image",
		key: r,
		role: "product",
		domainId: t.id,
		fingerprint: JSON.stringify({
			layer: t,
			transform: n
		}),
		properties: i,
		load: async (e) => Wu(await ru.fromURL(`/api/canvas/assets/${encodeURIComponent(t.renderAssetId)}/content?variant=preview`, {
			crossOrigin: "anonymous",
			signal: e
		}), i)
	};
}
function Zu(e) {
	let t = "background:selected-result-preview", n = {
		left: 0,
		top: 0,
		originX: "left",
		originY: "top",
		selectable: !1,
		evented: !1,
		visible: !0,
		...Uu(t, "background", e)
	};
	return {
		kind: "image",
		key: t,
		role: "background",
		domainId: e,
		fingerprint: JSON.stringify({ assetId: e }),
		properties: n,
		load: async (t) => Wu(await ru.fromURL(`/api/canvas/assets/${encodeURIComponent(e)}/content?variant=preview`, {
			crossOrigin: "anonymous",
			signal: t
		}), n)
	};
}
function Qu(e, t, n, r) {
	let i = t > 0 ? t : n;
	return r === "center" ? e + i / 2 : r === "right" ? e + i : e;
}
function $u(e) {
	return e.lines.map((t, n) => {
		let r = `text:${e.id}:line:${n}`, i = t.width > 0 ? t.width : e.boxWidth, a = {
			text: t.text,
			left: Qu(t.x, t.width, e.boxWidth, e.align),
			top: x(t.y, e.fontSize, e.baseline),
			lineFrameLeft: t.x,
			lineFrameWidth: i,
			fontFamily: e.fontFamily,
			fontSize: e.fontSize,
			charSpacing: e.fontSize === 0 ? 0 : e.letterSpacing * 1e3 / e.fontSize,
			letterSpacingPixels: e.letterSpacing,
			lineHeight: e.lineHeight,
			textAlign: e.align,
			originX: e.align,
			originY: "top",
			fill: e.color,
			visible: !0,
			selectable: !1,
			evented: !1,
			...Uu(r, "text", e.id)
		};
		return {
			kind: "sync",
			key: r,
			role: "text",
			domainId: e.id,
			fingerprint: JSON.stringify({
				snapshot: e,
				line: t,
				lineIndex: n
			}),
			properties: a,
			create: () => Wu(new jl(t.text), a)
		};
	});
}
function ed(e, t = e.semanticState.mode, n = null) {
	let r = Ie(e), i = /* @__PURE__ */ new Map();
	r.semanticState.nodes.forEach((e, t) => {
		i.set(e.id, Gu(r, e.id, t));
	});
	let a = n === null ? [] : [Zu(n)];
	a.push(...r.semanticState.nodes.map((e, t) => qu(e, i.get(e.id) ?? Gu(r, e.id, t))));
	for (let e of r.semanticState.edges) {
		let n = i.get(e.sourceNodeId), r = i.get(e.targetNodeId);
		if (n === void 0 || r === void 0) throw Error(`validated edge ${e.id} has no presentation endpoint`);
		a.push(Ju(e, n, r, t), Yu(e, "source", n, t), Yu(e, "target", r, t));
	}
	let o = [...r.layoutState.textSnapshots].sort((e, t) => e.sortOrder - t.sortOrder || e.id.localeCompare(t.id));
	return a.push(...o.filter((e) => e.zBand === "below-product").flatMap($u), ...r.layoutState.productLayers.map((e) => Xu(r, e)), ...o.filter((e) => e.zBand === "above-product").flatMap($u)), {
		project: r,
		descriptors: a,
		boardToNodeId: new Map(r.semanticState.outputBoards.map((e) => [e.id, e.outputNodeId]))
	};
}
//#endregion
//#region frontend/canvas/src/canvas/viewport.ts
var td = Object.freeze({
	minPan: -1e6,
	maxPan: 1e6,
	minZoom: .01,
	maxZoom: 1e3
});
function nd(e, t) {
	if (!Number.isFinite(e)) throw Error(`${t} must be finite`);
	return e;
}
function rd(e) {
	let t = {
		minPan: nd(e.minPan, "minPan"),
		maxPan: nd(e.maxPan, "maxPan"),
		minZoom: nd(e.minZoom, "minZoom"),
		maxZoom: nd(e.maxZoom, "maxZoom")
	};
	if (t.minPan > t.maxPan) throw Error("minPan must not exceed maxPan");
	if (t.minZoom <= 0 || t.minZoom > t.maxZoom) throw Error("zoom safety limits must be positive and ordered");
	return t;
}
function id(e, t, n) {
	return Math.min(n, Math.max(t, e));
}
function ad(e) {
	return {
		x: nd(e.x, "viewport.x"),
		y: nd(e.y, "viewport.y"),
		zoom: nd(e.zoom, "viewport.zoom")
	};
}
function od(e, t, n = td) {
	let r = ad(e), i = rd(n), a = nd(t.x, "pan.x"), o = nd(t.y, "pan.y");
	return {
		x: id(r.x + a, i.minPan, i.maxPan),
		y: id(r.y + o, i.minPan, i.maxPan),
		zoom: id(r.zoom, i.minZoom, i.maxZoom)
	};
}
function sd(e, t, n = td) {
	let r = ad(e), i = rd(n);
	return {
		x: id(r.x, i.minPan, i.maxPan),
		y: id(r.y, i.minPan, i.maxPan),
		zoom: id(nd(t, "zoom"), i.minZoom, i.maxZoom)
	};
}
//#endregion
//#region frontend/canvas/src/canvas/canvas-adapter.ts
function cd(e) {
	if (e.outputType !== void 0) return e.outputType;
	switch (e.node?.kind) {
		case "main_output": return "main";
		case "sku_output": return "sku";
		case "detail_output": return "detail";
		default: return;
	}
}
function ld(e) {
	if (e === void 0) return;
	let t = e.get(Vu);
	if (typeof t != "object" || !t) return;
	let n = t;
	if (!(typeof n.key != "string" || typeof n.domainId != "string" || typeof n.role != "string")) return n;
}
function ud(e) {
	return e === "product_source" || e === "auto_cutout";
}
function dd(e, t) {
	return JSON.stringify(e) === JSON.stringify(t);
}
function fd() {
	let e = null, t = null, n = null, r = !1, i = !1, a = 0, o = 0, s = null, c = "complete-set", l = {
		x: 0,
		y: 0,
		zoom: 1
	}, u = null, d = null, f = /* @__PURE__ */ new Map(), p = [], m = /* @__PURE__ */ new Map(), h = /* @__PURE__ */ new Map(), g = [], _ = () => {
		if (!r || n === null) throw Error("CanvasAdapter must be mounted before use");
		if (i) throw Error("CanvasAdapter has been disposed");
		return n;
	}, v = (e) => {
		a += 1;
		try {
			return e();
		} finally {
			--a;
		}
	}, y = (e) => {
		a !== 0 || i || t?.(structuredClone(e));
	}, b = (e) => {
		let t = (e) => {
			if (s === null) return;
			let t = [...m.entries()].find(([, t]) => t.object === e);
			if (t === void 0) return;
			let [n, r] = t, i = ed(s), a = i.descriptors.find((e) => e.key === n && e.role === r.role);
			if (a !== void 0) return {
				descriptor: a,
				nodeKind: (a.role === "node" ? i.project.semanticState.nodes.find((e) => e.id === a.domainId) : void 0)?.kind
			};
		}, n = (t, n) => {
			v(() => {
				t.set(n.properties), t.setCoords(), e.requestRenderAll();
			});
		}, r = (t, r) => {
			n(t, r), v(() => {
				e.contains(t) || e.add(t);
			}), O(e), e.requestRenderAll();
		}, i = ({ target: e }) => {
			let t = ld(e);
			t?.role === "node" && t.node !== void 0 && y({
				type: "node/add",
				node: structuredClone(t.node)
			});
		}, o = ({ target: e }) => {
			if (a !== 0) return;
			let r = ld(e), i = t(e);
			if (i?.descriptor.role === "product") {
				n(e, i.descriptor);
				return;
			}
			if (r?.role !== "node") return;
			let o = e.left, s = e.top;
			!Number.isFinite(o) || !Number.isFinite(s) || y({
				type: "node/move",
				nodeId: r.domainId,
				position: {
					x: o,
					y: s
				}
			});
		}, c = ({ target: e }) => {
			if (a !== 0) return;
			let n = t(e);
			if (n?.descriptor.role === "product") {
				r(e, n.descriptor);
				return;
			}
			if (n?.descriptor.role === "node" && ud(n.nodeKind)) {
				r(e, n.descriptor);
				return;
			}
			let i = ld(e);
			if (i?.role !== "node" || i.node?.managedBy !== "complete-set") return;
			let o = cd(i);
			o !== void 0 && y({
				type: "output/disable",
				outputType: o
			});
		}, u = (e) => {
			if (typeof e != "object" || !e) return null;
			let t = e;
			if (typeof t.clientX == "number" && typeof t.clientY == "number") return {
				x: t.clientX,
				y: t.clientY
			};
			let n = t.touches;
			if (!Array.isArray(n) || n.length === 0) return null;
			let r = n[0];
			if (typeof r != "object" || !r) return null;
			let i = r;
			return typeof i.clientX == "number" && typeof i.clientY == "number" ? {
				x: i.clientX,
				y: i.clientY
			} : null;
		};
		g = [
			e.on("object:added", i),
			e.on("object:modified", o),
			e.on("object:removed", c),
			e.on("mouse:down", (e) => {
				let t = e.e;
				t.altKey !== !0 && t.button !== 1 || (d = u(e.e));
			}),
			e.on("mouse:move", (t) => {
				if (d === null) return;
				let n = u(t.e);
				if (n === null) return;
				let r = od(l, {
					x: n.x - d.x,
					y: n.y - d.y
				});
				d = n, T(e, r), e.requestRenderAll(), y({
					type: "viewport/set",
					viewport: r
				});
			}),
			e.on("mouse:up", () => {
				d = null;
			}),
			e.on("mouse:wheel", (t) => {
				let n = t.e.deltaY;
				if (!Number.isFinite(n)) throw Error("wheel delta must be finite");
				t.e.preventDefault();
				let r = Math.min(20, Math.max(-20, -n * .001)), i = sd(l, l.zoom * Math.exp(r));
				T(e, i), e.requestRenderAll(), y({
					type: "viewport/set",
					viewport: i
				});
			})
		];
	}, x = () => {
		if (e === null) throw Error("CanvasAdapter mount element is unavailable");
		let t = new $c(e, {
			preserveObjectStacking: !0,
			selection: !0
		});
		n = t, b(t);
	}, S = () => {
		o += 1;
		for (let e of h.values()) e.controller.abort();
		h.clear();
	}, C = () => {
		S(), d = null;
		for (let e of g) e();
		g = [];
		let e = n;
		n = null, m.clear(), p = [], f.clear(), e !== null && e.dispose().catch(() => void 0);
	}, w = () => (C(), x(), s = null, _()), T = (e, t) => {
		l = sd(t, t.zoom), v(() => {
			e.setViewportTransform([
				l.zoom,
				0,
				0,
				l.zoom,
				l.x,
				l.y
			]);
		});
	}, E = (e) => {
		let t = c === "advanced";
		v(() => {
			for (let e of m.values()) (e.role === "edge" || e.role === "port") && (e.object.set("visible", t), e.object.setCoords());
		}), e.requestRenderAll();
	}, D = (e, t) => {
		let n = new Set(t.map((e) => e.key));
		for (let [e, r] of h) {
			let i = t.find((t) => t.key === e);
			(!n.has(e) || i?.fingerprint !== r.descriptor.fingerprint) && (r.controller.abort(), h.delete(e));
		}
		let r = [];
		for (let [e, t] of m) n.has(e) || (r.push(t.object), m.delete(e));
		r.length > 0 && v(() => e.remove(...r));
	}, O = (e) => {
		let t = 0;
		v(() => {
			for (let n of p) {
				let r = m.get(n);
				r !== void 0 && (e.moveObjectTo(r.object, t), t += 1);
			}
		});
	}, ee = (e, t) => {
		let r = new AbortController(), a = {
			controller: r,
			descriptor: t,
			epoch: o,
			surface: e
		};
		h.set(t.key, a), t.load(r.signal).then((s) => {
			let l = h.get(t.key);
			if (i || r.signal.aborted || l !== a || a.epoch !== o || n !== a.surface) {
				s.dispose();
				return;
			}
			h.delete(t.key), s.set("visible", t.role === "edge" || t.role === "port" ? c === "advanced" : t.properties.visible ?? !0), s.setCoords(), m.set(t.key, {
				object: s,
				fingerprint: t.fingerprint,
				role: t.role
			}), v(() => e.add(s)), O(e), e.requestRenderAll();
		}).catch(() => {
			h.get(t.key) === a && h.delete(t.key);
		});
	}, te = (e, t) => {
		for (let n of t) {
			let t = m.get(n.key);
			if (t !== void 0) {
				if (t.fingerprint !== n.fingerprint) {
					if (n.kind === "image") {
						m.delete(n.key), v(() => e.remove(t.object)), t.object.dispose(), ee(e, n);
						continue;
					}
					v(() => {
						t.object.set(n.properties), t.object.setCoords();
					}), t.fingerprint = n.fingerprint, t.role = n.role;
				}
				continue;
			}
			let r = h.get(n.key);
			if (r !== void 0) {
				if (r.descriptor.fingerprint === n.fingerprint) continue;
				r.controller.abort(), h.delete(n.key);
			}
			if (n.kind === "image") {
				ee(e, n);
				continue;
			}
			let i = n.create();
			m.set(n.key, {
				object: i,
				fingerprint: n.fingerprint,
				role: n.role
			}), v(() => e.add(i));
		}
	}, ne = (n, a) => {
		if (i) throw Error("CanvasAdapter has been disposed");
		if (r) throw Error("CanvasAdapter is already mounted");
		e = n, t = a, r = !0, x();
	}, re = (e, t) => {
		let n = _(), r = ed(t, t.semanticState.mode, u);
		s !== null && (e === null || !dd(e, s)) && (n = w()), p = r.descriptors.map((e) => e.key), c = r.project.semanticState.mode, D(n, r.descriptors), te(n, r.descriptors), O(n), f = new Map(r.boardToNodeId), E(n), T(n, r.project.layoutState.viewport), s = r.project, n.requestRenderAll();
	};
	return {
		mount: ne,
		project: re,
		setMode: (e) => {
			let t = _();
			if (e !== "complete-set" && e !== "advanced") throw Error(`unsupported workspace mode ${String(e)}`);
			c = e, E(t);
		},
		focusBoard: (e) => {
			let t = _(), n = f.get(e);
			if (n === void 0) throw Error(`unknown output board ${e}`);
			let r = m.get(`node:${n}`);
			if (r === void 0) throw Error(`output board ${e} has no domain presentation`);
			let i = r.object.getCenterPoint(), a = l.zoom, o = sd({
				x: t.getWidth() / 2 - i.x * a,
				y: t.getHeight() / 2 - i.y * a,
				zoom: a
			}, a);
			T(t, o), t.requestRenderAll();
		},
		setResultBackgroundPreview: (e) => {
			u !== e && (u = e, s !== null && re(s, s));
		},
		cancelPendingLoads: () => {
			S();
		},
		dispose: () => {
			i || (i = !0, C(), s = null, t = null, e = null);
		}
	};
}
//#endregion
//#region frontend/canvas/src/domain/assets.ts
var pd = 12 * 1024 * 1024, md = [
	"image/jpeg",
	"image/png",
	"image/webp"
], hd = "main-product", gd = "main-product-source", _d = "main-product-cutout", vd = "main-product-source-cutout";
function yd(e, t = pd) {
	return md.includes(e.type) ? e.size > t ? {
		ok: !1,
		message: "图片不能超过 12 MB"
	} : { ok: !0 } : {
		ok: !1,
		message: "请选择 JPG、PNG 或 WebP 图片"
	};
}
function bd(e, t, n) {
	return {
		id: e,
		kind: t,
		managedBy: null,
		skuId: null,
		assetId: n,
		modelProfileId: null,
		prompt: null,
		compositionGroupId: null,
		textSnapshotId: null,
		outputBoardId: null,
		parameters: {}
	};
}
function xd(e, t) {
	let n = e.semanticState.nodes.findIndex((e) => e.id === t.id);
	n === -1 ? e.semanticState.nodes.push(t) : e.semanticState.nodes[n] = t;
}
function Sd(e) {
	let t = {
		id: vd,
		kind: "product_asset",
		sourceNodeId: gd,
		sourcePort: "product",
		targetNodeId: _d,
		targetPort: "reference",
		skuId: null
	}, n = e.semanticState.edges.findIndex((e) => e.id === vd);
	n === -1 ? e.semanticState.edges.push(t) : e.semanticState.edges[n] = t;
}
function Cd(e, t) {
	let n = e.layoutState.productLayers.find((e) => e.id === hd && e.skuId === null);
	if (n === void 0) throw Error("Canvas main product layer is missing");
	if (n.allowOpaqueFallback = t, n.compositionGroupId !== null) for (let r of e.layoutState.productLayers) r.compositionGroupId === n.compositionGroupId && r.sourceAssetId === n.sourceAssetId && r.renderAssetId === n.renderAssetId && (r.allowOpaqueFallback = t);
}
function wd(e, t, n) {
	let r = e.layoutState.productLayers.find((e) => e.id === hd), i = {
		id: hd,
		sourceAssetId: t,
		renderAssetId: n,
		allowOpaqueFallback: !1,
		skuId: null,
		compositionGroupId: r?.compositionGroupId ?? null,
		transformId: r?.transformId ?? hd,
		locked: !0
	}, a = e.layoutState.productLayers.findIndex((e) => e.id === hd);
	if (a === -1 ? e.layoutState.productLayers.push(i) : e.layoutState.productLayers[a] = i, r?.compositionGroupId !== null && r?.compositionGroupId !== void 0) for (let a of e.layoutState.productLayers) a.id !== i.id && a.compositionGroupId === r.compositionGroupId && a.sourceAssetId === r.sourceAssetId && (a.sourceAssetId = t, a.renderAssetId = n, a.allowOpaqueFallback = !1);
	e.layoutState.objectTransforms[hd] ??= {
		x: .5,
		y: .5,
		scale: 1,
		rotation: 0
	};
}
function Td(e) {
	let t = e.source.projectId;
	if (e.source.assetType !== "source" || e.working.assetType !== "working" || e.preview.assetType !== "preview" || e.working.projectId !== t || e.preview.projectId !== t || e.working.sourceAssetId !== e.source.id || e.preview.sourceAssetId !== e.working.id) throw Error("Canvas upload response has invalid asset derivation");
	if (e.operation !== null && (e.operation.projectId !== t || e.operation.operationType !== "cutout" || e.operation.inputAssetId !== e.working.id)) throw Error("Canvas upload response has invalid cutout operation");
}
function Ed(e) {
	if (e.working.transparencyStatus === "transparent") {
		if (e.operation !== null) throw Error("Transparent Canvas assets cannot enqueue automatic cutout");
		return "ready";
	}
	if (e.operation === null) throw Error("Opaque Canvas assets require an automatic cutout operation");
	return e.operation.status === "running" ? "running" : "queued";
}
function Dd(e, t) {
	Td(t);
	let n = structuredClone(e), r = Ed(t);
	return xd(n, bd(gd, "product_source", t.working.id)), xd(n, bd(_d, "auto_cutout", t.working.id)), Sd(n), wd(n, t.working.id, t.working.id), {
		project: n,
		asset: {
			projectId: t.source.projectId,
			sourceAssetId: t.source.id,
			workingAssetId: t.working.id,
			previewAssetId: t.preview.id,
			renderAssetId: t.working.id,
			cutoutAssetId: null,
			operationId: t.operation?.id ?? null,
			cutoutStatus: r,
			allowOpaqueFallback: !1,
			error: null
		}
	};
}
function Od(e) {
	switch (e) {
		case "queued":
		case "cancel_requested": return "queued";
		case "running": return "running";
		case "failed": return "failed";
		case "interrupted":
		case "cancelled": return "interrupted";
		case "succeeded": return "ready";
	}
}
function kd(e, t) {
	if (t.id !== e.asset.operationId || t.projectId !== e.asset.projectId || t.inputAssetId !== void 0 && t.inputAssetId !== e.asset.workingAssetId || t.operationType !== "cutout") return e;
	let n = structuredClone(e.project), r = t.status === "succeeded";
	if (r && t.outputAssetId === null) throw Error("Succeeded Canvas cutout has no output asset");
	let i = r && !e.asset.allowOpaqueFallback, a = i ? t.outputAssetId : e.asset.renderAssetId;
	return i && (wd(n, e.asset.workingAssetId, a), xd(n, bd(_d, "auto_cutout", a)), Cd(n, !1)), {
		project: n,
		asset: {
			...e.asset,
			renderAssetId: a,
			cutoutAssetId: r ? t.outputAssetId : e.asset.cutoutAssetId,
			cutoutStatus: Od(t.status),
			allowOpaqueFallback: !i && e.asset.allowOpaqueFallback,
			error: t.status === "queued" || t.status === "running" || t.status === "succeeded" ? null : t.safeError ?? e.asset.error
		}
	};
}
function Ad(e, t, n) {
	let r = e.layoutState.productLayers.find((e) => e.skuId === null && e.locked);
	if (r === void 0) return null;
	let i = t.find((e) => e.id === r.sourceAssetId && e.assetType === "working");
	if (i === void 0 || i.sourceAssetId === null) return null;
	let a = t.find((e) => e.id === i.sourceAssetId && e.assetType === "source"), o = t.find((e) => e.assetType === "preview" && e.sourceAssetId === i.id);
	if (a === void 0 || o === void 0) return null;
	let s = [...n].filter((e) => e.projectId === i.projectId && e.operationType === "cutout" && e.inputAssetId === i.id).at(-1) ?? null, c = t.find((e) => e.id === r.renderAssetId), l = c?.assetType === "cutout" ? c.id : s?.status === "succeeded" ? s.outputAssetId : null, u = i.transparencyStatus === "transparent" ? "ready" : s === null ? l === null ? "queued" : "ready" : Od(s.status), d = jd(e), f = {
		project: structuredClone(e),
		asset: {
			projectId: i.projectId,
			sourceAssetId: a.id,
			workingAssetId: i.id,
			previewAssetId: o.id,
			renderAssetId: r.renderAssetId,
			cutoutAssetId: l,
			operationId: s?.id ?? null,
			cutoutStatus: u,
			allowOpaqueFallback: d,
			error: s?.safeError ?? null
		}
	};
	return s?.status === "succeeded" && s.outputAssetId !== null && !d ? kd(f, s) : f;
}
function jd(e) {
	return e.layoutState.productLayers.find((e) => e.id === hd && e.skuId === null)?.allowOpaqueFallback === !0;
}
//#endregion
//#region frontend/canvas/src/components/project-sidebar.ts
function Md(e, t, n) {
	let r = document.createElement("button");
	return r.type = "button", r.textContent = e, n !== void 0 && (r.dataset.testid = n), r.addEventListener("click", t), r;
}
function Nd(e) {
	let n = null, r = e.getState(), i = document.createElement("aside");
	i.className = "canvas-project-sidebar", i.dataset.testid = "canvas-project-sidebar", i.setAttribute("aria-label", "项目列表");
	let a = document.createElement("h1");
	a.textContent = "产品视觉画布";
	let o = document.createElement("form");
	o.className = "canvas-create-project";
	let s = document.createElement("input");
	s.type = "text", s.required = !0, s.maxLength = 200, s.setAttribute("aria-label", "新建项目名称"), s.dataset.testid = "canvas-project-create-name", s.placeholder = "项目名称";
	let c = document.createElement("button");
	c.type = "submit", c.textContent = "新建", c.dataset.testid = "canvas-project-create", o.append(s, c), o.addEventListener("submit", (t) => {
		t.preventDefault();
		let n = s.value.trim();
		n !== "" && e.createProject(n).then((e) => {
			e.ok && (s.value = "");
		});
	});
	let l = document.createElement("input");
	l.type = "search", l.setAttribute("aria-label", "搜索项目"), l.dataset.testid = "canvas-project-search", l.placeholder = "搜索项目";
	let u = document.createElement("label"), d = document.createElement("input");
	d.type = "checkbox", u.append(d, "显示已归档"), l.addEventListener("input", () => {
		e.searchProjects(l.value, d.checked);
	}), d.addEventListener("change", () => {
		e.searchProjects(l.value, d.checked);
	});
	let f = document.createElement("ul");
	f.className = "canvas-project-list", f.dataset.testid = "canvas-project-list";
	let p = document.createElement("p");
	p.className = "canvas-project-feedback", p.setAttribute("aria-live", "polite");
	let m = document.createElement("div");
	m.className = "canvas-project-dialogs", i.append(a, o, l, u, p, f, m);
	let h = (i) => {
		r = i, document.activeElement !== l && (l.value = i.query), d.checked = i.includeArchived, p.textContent = i.loading ? "正在加载项目…" : i.error === null ? "" : t(i.error, "项目加载失败，请重试"), f.replaceChildren();
		for (let t of i.projects) {
			let a = document.createElement("li");
			a.className = "canvas-project-row", a.dataset.testid = "canvas-project-row", a.dataset.projectId = t.id, t.id === i.activeProjectId && a.classList.add("is-active");
			let o = Md(t.name, () => {
				t.id !== i.activeProjectId && e.switchProject(t.id);
			}, "canvas-project-switch");
			o.className = "canvas-project-select", t.id === i.activeProjectId && o.setAttribute("aria-current", "true");
			let s = document.createElement("span");
			if (s.className = "canvas-project-meta", s.textContent = t.status === "archived" ? "已归档" : "自动保存", a.append(o, s), t.id === i.activeProjectId && n === t.id) {
				let i = document.createElement("form");
				i.className = "canvas-project-rename-form";
				let o = document.createElement("input");
				o.type = "text", o.value = t.name, o.maxLength = 200, o.setAttribute("aria-label", `重命名 ${t.name}`), o.dataset.testid = "canvas-project-rename";
				let s = Md("保存", () => {
					let t = o.value.trim();
					t !== "" && e.renameActiveProject(t).then((e) => {
						e.ok && (n = null, h(r));
					});
				}, "canvas-project-rename-save"), c = Md("取消", () => {
					n = null, h(r);
				});
				i.append(o, s, c), i.addEventListener("submit", (e) => {
					e.preventDefault(), s.click();
				}), a.append(i), queueMicrotask(() => o.select());
			}
			let c = document.createElement("details");
			c.className = "canvas-project-menu";
			let l = document.createElement("summary");
			l.textContent = "更多", l.setAttribute("aria-label", `${t.name}项目操作`);
			let u = document.createElement("div");
			u.className = "canvas-project-menu-popover", u.setAttribute("role", "menu"), t.id === i.activeProjectId && n !== t.id && u.append(Md("重命名", () => {
				n = t.id, c.open = !1, h(r);
			}, "canvas-project-rename-start")), t.status === "archived" ? u.append(Md("恢复项目", () => void e.restoreProject(t.id), "canvas-project-restore")) : t.status === "active" && u.append(Md("归档项目", () => void e.archiveProject(t.id), "canvas-project-archive"));
			let d = Md("删除项目", () => e.requestDeleteProject(t.id), "canvas-project-delete");
			d.className = "is-danger", u.append(d), c.append(l, u), a.append(c), f.append(a);
		}
		if (m.replaceChildren(), i.deleteCandidateId !== null) {
			let t = document.createElement("section");
			t.setAttribute("role", "dialog"), t.setAttribute("aria-modal", "true"), t.setAttribute("aria-label", "确认删除项目"), t.dataset.testid = "canvas-delete-confirm";
			let n = document.createElement("p");
			n.textContent = "删除后项目与其画布数据将被永久移除。", t.append(n, Md("确认删除", () => void e.confirmDeleteProject(), "canvas-delete-confirm-submit"), Md("取消", () => e.cancelDeleteProject(), "canvas-delete-confirm-cancel")), m.append(t);
		}
		if (i.pendingSwitch !== null) {
			let t = document.createElement("section");
			t.setAttribute("role", "dialog"), t.setAttribute("aria-modal", "true"), t.setAttribute("aria-label", "未保存项目切换"), t.dataset.testid = "canvas-switch-decision";
			let n = document.createElement("p");
			n.textContent = "当前项目保存失败。请选择重试、留在当前项目或放弃更改。", t.append(n, Md("重试", () => void e.retrySwitch(), "canvas-switch-retry"), Md("留在当前项目", () => e.stayOnProject(), "canvas-switch-stay"), Md("放弃更改并切换", () => void e.discardAndSwitch(), "canvas-switch-discard")), m.append(t);
		}
	};
	return {
		element: i,
		update: h
	};
}
//#endregion
//#region frontend/canvas/src/components/asset-inspector.ts
var Pd = {
	ready: "素材已就绪",
	queued: "自动抠图已排队",
	running: "正在自动抠图",
	failed: "自动抠图失败",
	interrupted: "自动抠图已中断"
};
function Fd() {
	return typeof crypto.randomUUID == "function" ? crypto.randomUUID() : `cutout-retry-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function Id({ api: e, onOperation: n, onFallback: r, createRequestId: i = Fd }) {
	let a = null, o = !1, s = !1, c = 0, l = document.createElement("section");
	l.className = "canvas-asset-inspector", l.dataset.testid = "canvas-asset-inspector";
	let u = () => {
		if (s) return;
		let u = document.createElement("h3");
		if (u.textContent = "素材与抠图", a === null) {
			let e = document.createElement("p");
			e.textContent = "上传主商品图片后可在此对比抠图。", l.replaceChildren(u, e);
			return;
		}
		let d = document.createElement("div");
		d.className = "canvas-asset-comparison";
		let f = a.cutoutStatus === "ready" && a.operationId === null && a.cutoutAssetId === null, p = (t, n, r) => {
			let i = document.createElement("figure");
			i.className = "canvas-checkerboard";
			let a = document.createElement("figcaption");
			if (a.textContent = t, i.append(a), r === null) {
				let e = document.createElement("span");
				e.textContent = f ? "原图已含透明通道，无需抠图" : "等待抠图结果", i.append(e);
			} else {
				let t = document.createElement("img");
				t.alt = n, t.src = e.previewUrl(r), i.append(t);
			}
			return i;
		};
		d.append(p("原图", "原图预览", a.workingAssetId), p("抠图", "抠图预览", a.cutoutAssetId));
		let m = document.createElement("p");
		m.className = `canvas-cutout-status is-${a.cutoutStatus}`, m.dataset.testid = "canvas-cutout-status", m.textContent = Pd[a.cutoutStatus], a.error !== null && (m.textContent += `：${t(a.error.message, "素材处理失败，请重试")}`);
		let h = document.createElement("div");
		if (h.className = "canvas-asset-actions", a.cutoutStatus === "failed" || a.cutoutStatus === "interrupted") {
			let r = document.createElement("button");
			r.type = "button", r.textContent = "重新抠图", r.disabled = o, r.addEventListener("click", () => {
				if (o || a === null) return;
				let l = a, u = ++c;
				r.disabled = !0, e.retryCutout(l.workingAssetId, i()).then((e) => {
					s || u !== c || (e.ok ? (n(e.value), m.textContent = "自动抠图已重新排队") : (m.textContent = t(e.message, "素材处理失败，请重试"), r.disabled = o));
				});
			}), h.append(r);
		}
		if (!f && !a.allowOpaqueFallback) {
			let e = document.createElement("button");
			e.type = "button", e.textContent = "使用原图矩形继续", e.disabled = o, e.addEventListener("click", () => {
				!o && a !== null && r(a);
			}), h.append(e);
		}
		l.replaceChildren(u, d, m, h);
	};
	return u(), {
		element: l,
		update: (e) => {
			a = e === null ? null : structuredClone(e), c += 1, u();
		},
		setDisabled: (e) => {
			o = e, u();
		},
		dispose: () => {
			s || (s = !0, c += 1, l.remove());
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/asset-uploader.ts
function Ld(e) {
	return e instanceof DOMException && e.name === "AbortError" || typeof e == "object" && !!e && "name" in e && e.name === "AbortError";
}
function Rd({ api: e, onUploaded: n }) {
	let r = null, i = !1, a = !1, o = null, s = document.createElement("section");
	s.className = "canvas-asset-uploader", s.dataset.testid = "canvas-asset-uploader";
	let c = document.createElement("h3");
	c.textContent = "主商品素材";
	let l = document.createElement("label");
	l.className = "canvas-asset-dropzone", l.dataset.testid = "canvas-asset-dropzone", l.textContent = "拖放图片，或选择文件";
	let u = document.createElement("input");
	u.type = "file", u.accept = "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp", u.setAttribute("aria-label", "上传主商品图片"), l.append(u);
	let d = document.createElement("p");
	d.className = "canvas-asset-feedback", d.setAttribute("role", "status"), d.setAttribute("aria-live", "polite"), s.append(c, l, d);
	let f = () => {
		u.disabled = i || r === null || a, l.dataset.disabled = String(u.disabled);
	}, p = async (s) => {
		if (a || i || r === null) return;
		let c = yd(s);
		if (!c.ok) {
			d.textContent = c.message, d.dataset.state = "validation";
			return;
		}
		o?.abort();
		let l = new AbortController();
		o = l;
		let u = r;
		d.dataset.state = "uploading", d.textContent = "正在上传…";
		try {
			let i = await e.uploadAsset({
				projectId: u,
				file: s,
				signal: l.signal,
				onProgress: ({ percent: e, loaded: t, total: n }) => {
					o !== l || l.signal.aborted || (d.textContent = e === null ? `正在上传 ${t} 字节…` : `正在上传 ${e}%${n === null ? "" : `（${t}/${n}）`}`);
				}
			});
			if (a || l.signal.aborted || o !== l || r !== u) return;
			if (!i.ok) {
				d.dataset.state = i.kind, d.textContent = t(i.message, "图片上传失败，请重试");
				return;
			}
			d.dataset.state = "complete", d.textContent = "上传完成，正在检测背景并准备产品素材…", n(i.value);
		} catch (e) {
			!Ld(e) && o === l && !a && (d.dataset.state = "offline", d.textContent = "上传失败，请检查网络后重试");
		} finally {
			o === l && (o = null);
		}
	};
	return u.addEventListener("change", () => {
		let e = u.files?.[0];
		e !== void 0 && p(e);
	}), l.addEventListener("dragover", (e) => {
		e.preventDefault();
	}), l.addEventListener("drop", (e) => {
		e.preventDefault();
		let t = e.dataTransfer?.files[0];
		t !== void 0 && p(t);
	}), f(), {
		element: s,
		setProject: (e) => {
			r !== e && (o?.abort(), o = null, u.value = "", d.textContent = "", delete d.dataset.state), r = e, f();
		},
		setDisabled: (e) => {
			i = e, i && (o?.abort(), o = null), f();
		},
		openPicker: () => {
			u.disabled || u.click();
		},
		uploadFile: (e) => {
			p(e);
		},
		dispose: () => {
			a || (a = !0, o?.abort(), o = null, f(), s.remove());
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/sku-editor.ts
function zd({ api: e, onSnapshot: n }) {
	let r = null, i = !1, a = !1, o = !1, s = 0, c = document.createElement("section");
	c.className = "canvas-sku-editor", c.dataset.testid = "canvas-sku-editor";
	let l = document.createElement("p");
	l.className = "canvas-sku-feedback", l.setAttribute("role", "status"), l.setAttribute("aria-live", "polite");
	let u = () => a || r === null || r.disabled || i, d = () => {
		for (let e of c.querySelectorAll("button,input,select,textarea")) e.disabled = u();
	}, f = (e) => {
		r === null || e.project.id !== r.projectId || (r = {
			...r,
			revision: e.revision,
			skus: e.skus.map((e) => structuredClone(e))
		}, n(e));
	}, p = () => {
		if (i) return;
		let t = document.createElement("h3");
		if (t.textContent = "SKU", r === null) {
			let e = document.createElement("p");
			e.textContent = "选择项目后编辑 SKU。", c.replaceChildren(t, e, l);
			return;
		}
		let n = document.createElement("div");
		n.className = "canvas-sku-create";
		let a = document.createElement("input");
		a.type = "text", a.maxLength = 200, a.setAttribute("aria-label", "新 SKU 名称");
		let o = document.createElement("button");
		o.type = "button", o.textContent = "新增 SKU", o.setAttribute("aria-label", "新增 SKU"), o.addEventListener("click", () => {
			let t = a.value.trim();
			if (t === "") {
				l.textContent = "请输入 SKU 名称";
				return;
			}
			m((n) => e.createSku(n.projectId, n.revision, { name: t }));
		}), n.append(a, o);
		let s = document.createElement("div");
		s.className = "canvas-sku-list";
		let u = [...r.skus].sort((e, t) => e.sortOrder - t.sortOrder || e.id.localeCompare(t.id));
		u.forEach((t, n) => {
			let i = document.createElement("fieldset");
			i.className = "canvas-sku-row", i.dataset.skuId = t.id;
			let a = document.createElement("legend");
			a.textContent = t.name;
			let o = document.createElement("label");
			o.textContent = "名称";
			let c = document.createElement("input");
			c.type = "text", c.maxLength = 200, c.value = t.name, c.setAttribute("aria-label", `SKU ${t.name} 名称`), c.addEventListener("change", () => {
				let n = c.value.trim();
				n !== "" && n !== t.name && m((r) => e.updateSku(r.projectId, t.id, r.revision, { name: n }));
			}), o.append(c);
			let l = document.createElement("label");
			l.textContent = "提示词";
			let d = document.createElement("textarea");
			d.maxLength = 4e3, d.value = t.prompt, d.setAttribute("aria-label", `SKU ${t.name} 提示词`), d.addEventListener("change", () => {
				d.value !== t.prompt && m((n) => e.updateSku(n.projectId, t.id, n.revision, { prompt: d.value }));
			}), l.append(d);
			let f = document.createElement("label");
			f.textContent = "参考素材";
			let p = document.createElement("select");
			p.setAttribute("aria-label", `SKU ${t.name} 参考素材`);
			let g = document.createElement("option");
			g.value = "", g.textContent = "沿用主商品素材", p.append(g);
			for (let e of r?.referenceAssets ?? []) {
				let t = document.createElement("option");
				t.value = e.id, t.textContent = e.label, p.append(t);
			}
			p.value = t.referenceAssetId ?? "", p.addEventListener("change", () => {
				let n = p.value === "" ? null : p.value;
				n !== t.referenceAssetId && m((r) => e.updateSku(r.projectId, t.id, r.revision, { referenceAssetId: n }));
			}), f.append(p);
			let _ = document.createElement("p");
			_.className = "canvas-sku-reference-resolution", _.textContent = t.referenceAssetId === null ? r?.mainProductAssetId === null ? "缺少主商品素材；SKU 名称不会生成包装图" : `沿用主商品素材 ${r?.mainProductAssetId}` : `使用 SKU 参考素材 ${t.referenceAssetId}`;
			let v = document.createElement("div");
			v.className = "canvas-sku-actions";
			let y = document.createElement("button");
			y.type = "button", y.textContent = "上移", y.setAttribute("aria-label", `上移 SKU ${t.name}`), y.disabled = n === 0, y.addEventListener("click", () => {
				n > 0 && h(t.id, { sortOrder: u[n - 1].sortOrder });
			});
			let b = document.createElement("button");
			b.type = "button", b.textContent = "下移", b.setAttribute("aria-label", `下移 SKU ${t.name}`), b.disabled = n === u.length - 1, b.addEventListener("click", () => {
				n < u.length - 1 && h(t.id, { sortOrder: u[n + 1].sortOrder });
			});
			let x = document.createElement("button");
			x.type = "button", x.textContent = "删除", x.setAttribute("aria-label", `删除 SKU ${t.name}`), x.addEventListener("click", () => {
				m((n) => e.deleteSku(n.projectId, t.id, n.revision));
			}), v.append(y, b, x), i.append(a, o, l, f, _, v), s.append(i);
		}), c.replaceChildren(t, n, s, l), d();
	}, m = async (e) => {
		if (r === null || u()) return;
		let n = ++s;
		a = !0, o = !0, l.textContent = "正在保存 SKU…", d();
		let c = await e(r);
		if (!(i || n !== s)) {
			if (a = !1, c.ok) {
				o = !1, l.textContent = "SKU 已保存", f(c.snapshot), p();
				return;
			}
			c.kind === "conflict" ? l.textContent = `版本冲突（服务器版本 ${c.currentRevision}），未覆盖本地编辑` : l.textContent = t(c.message, "SKU 操作失败，请重试"), d();
		}
	}, h = (t, n) => m((r) => e.updateSku(r.projectId, t, r.revision, n));
	return p(), {
		element: c,
		update: (e) => {
			let t = r !== null && e !== null && r.projectId === e.projectId, n = e === null ? null : {
				...e,
				skus: e.skus.map((e) => structuredClone(e)),
				referenceAssets: e.referenceAssets.map((e) => ({ ...e }))
			};
			if (t && (a || o)) {
				r = n, d();
				return;
			}
			t || (s += 1, a = !1, o = !1), r = n, l.textContent = "", p();
		},
		dispose: () => {
			i || (i = !0, s += 1, c.remove());
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/composition-inspector.ts
var Bd = [
	[
		"slot.x",
		"槽位 X",
		0,
		1,
		.01
	],
	[
		"slot.y",
		"槽位 Y",
		0,
		1,
		.01
	],
	[
		"slot.width",
		"槽位宽度",
		.01,
		1,
		.01
	],
	[
		"slot.height",
		"槽位高度",
		.01,
		1,
		.01
	],
	[
		"anchor.x",
		"锚点 X",
		0,
		1,
		.01
	],
	[
		"anchor.y",
		"锚点 Y",
		0,
		1,
		.01
	],
	[
		"baseline",
		"基线",
		0,
		1,
		.01
	],
	[
		"relativeProductFraction",
		"商品相对占比",
		.01,
		1,
		.01
	],
	[
		"safeArea.top",
		"安全区上",
		0,
		.99,
		.01
	],
	[
		"safeArea.right",
		"安全区右",
		0,
		.99,
		.01
	],
	[
		"safeArea.bottom",
		"安全区下",
		0,
		.99,
		.01
	],
	[
		"safeArea.left",
		"安全区左",
		0,
		.99,
		.01
	],
	[
		"rotation",
		"允许旋转",
		-180,
		180,
		1
	]
];
function Vd(e, t) {
	switch (t) {
		case "slot.x": return e.slot.x;
		case "slot.y": return e.slot.y;
		case "slot.width": return e.slot.width;
		case "slot.height": return e.slot.height;
		case "anchor.x": return e.anchor.x;
		case "anchor.y": return e.anchor.y;
		case "baseline": return e.baseline;
		case "relativeProductFraction": return e.relativeProductFraction;
		case "safeArea.top": return e.safeArea.top;
		case "safeArea.right": return e.safeArea.right;
		case "safeArea.bottom": return e.safeArea.bottom;
		case "safeArea.left": return e.safeArea.left;
		case "rotation": return e.rotation;
	}
}
function Hd(e, t, n) {
	switch (t) {
		case "slot.x":
			e.slot.x = n;
			break;
		case "slot.y":
			e.slot.y = n;
			break;
		case "slot.width":
			e.slot.width = n;
			break;
		case "slot.height":
			e.slot.height = n;
			break;
		case "anchor.x":
			e.anchor.x = n;
			break;
		case "anchor.y":
			e.anchor.y = n;
			break;
		case "baseline":
			e.baseline = n;
			break;
		case "relativeProductFraction":
			e.relativeProductFraction = n;
			break;
		case "safeArea.top":
			e.safeArea.top = n;
			break;
		case "safeArea.right":
			e.safeArea.right = n;
			break;
		case "safeArea.bottom":
			e.safeArea.bottom = n;
			break;
		case "safeArea.left":
			e.safeArea.left = n;
			break;
		case "rotation":
			e.rotation = n;
			break;
	}
}
function Ud({ onUpdate: e }) {
	let t = null, n = !1, r = document.createElement("section");
	r.className = "canvas-composition-inspector", r.dataset.testid = "canvas-composition-inspector";
	let i = () => {
		let i = document.createElement("h3");
		if (i.textContent = "共享构图", t === null) {
			let e = document.createElement("p");
			e.textContent = "选择构图组后调整 SKU 统一构图。", r.replaceChildren(i, e);
			return;
		}
		let a = document.createElement("div");
		a.className = "canvas-composition-grid";
		for (let [r, i, o, s, c] of Bd) {
			let l = document.createElement("label");
			l.textContent = i;
			let u = document.createElement("input");
			u.type = "number", u.min = String(o), u.max = String(s), u.step = String(c), u.value = String(Vd(t.layout, r)), u.disabled = t.disabled, u.dataset.field = r === "baseline" ? "baseline" : r, u.addEventListener("change", () => {
				if (n || t === null || t.disabled) return;
				let i = Number(u.value);
				if (!Number.isFinite(i)) return;
				let a = structuredClone(t.layout);
				Hd(a, r, i), e(t.groupId, a);
			}), l.append(u), a.append(l);
		}
		let o = document.createElement("label");
		o.textContent = "保持比例（contain）";
		let s = document.createElement("input");
		s.type = "checkbox", s.checked = !0, s.disabled = !0, o.append(s), r.replaceChildren(i, a, o);
	};
	return i(), {
		element: r,
		update: (e) => {
			n || (t = e === null ? null : {
				...e,
				layout: structuredClone(e.layout)
			}, i());
		},
		dispose: () => {
			n = !0, t = null, r.replaceChildren();
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/text-inspector.ts
function Wd(e, t, n, r, i = "text") {
	let a = document.createElement("input");
	return a.type = i, a.value = t, a.disabled = n, a.dataset.testid = e, a.addEventListener("change", () => r(a.value)), a;
}
function Gd({ onSelect: e, onUpdate: n }) {
	let r = {
		layers: [],
		selectedLayerId: null,
		disabled: !0
	}, i = !1, a = document.createElement("section");
	a.className = "canvas-text-inspector", a.dataset.testid = "canvas-text-inspector";
	let o = () => {
		let i = document.createElement("h3");
		i.textContent = "文字图层";
		let o = document.createElement("select");
		o.dataset.testid = "canvas-text-layer-select", o.disabled = r.disabled || r.layers.length === 0, o.append(...r.layers.map((e, t) => Object.assign(document.createElement("option"), {
			value: e.id,
			textContent: `${t + 1}. ${e.content || e.id}`
		})));
		let s = r.layers.find((e) => e.id === r.selectedLayerId) ?? r.layers[0] ?? null;
		if (o.value = s?.id ?? "", o.addEventListener("change", () => e?.(o.value || null)), s === null) {
			let e = document.createElement("p");
			e.textContent = "暂无文字图层", a.replaceChildren(i, o, e);
			return;
		}
		let c = document.createElement("div");
		c.className = "canvas-text-fields";
		let l = (e, t) => {
			let n = document.createElement("label");
			n.append(e, t), c.append(n);
		}, u = document.createElement("textarea");
		u.value = s.content, u.disabled = r.disabled, u.dataset.testid = "canvas-text-content";
		let d = document.createElement("p");
		d.className = "canvas-text-feedback", d.dataset.testid = "canvas-text-content-feedback", d.setAttribute("role", "alert"), u.addEventListener("change", () => {
			try {
				n(s.id, w(s, u.value)), d.textContent = "";
			} catch (e) {
				u.value = s.content, d.textContent = t(e instanceof Error ? e.message : null, "文字内容更新失败");
			}
		}), l("内容", u), c.append(d);
		let f = (e, t, i, a) => l(e, Wd(t, String(i), r.disabled, (e) => {
			let t = Number(e);
			Number.isFinite(t) && n(s.id, { [a]: t });
		}, "number"));
		f("文本框宽度", "canvas-text-box-width", s.boxWidth, "boxWidth");
		let p = Wd("canvas-text-font-size", String(s.fontSize), r.disabled, (e) => {
			let t = Number(e);
			Number.isInteger(t) && t > 0 && n(s.id, { fontSize: t });
		}, "number");
		p.min = "1", p.max = "10000", p.step = "1", l("字号", p), l("颜色", Wd("canvas-text-color", s.color, r.disabled, (e) => {
			n(s.id, { color: e });
		}, "color")), f("字间距", "canvas-text-letter-spacing", s.letterSpacing, "letterSpacing"), l("行距", Wd("canvas-text-line-height", String(s.lineHeight), r.disabled, (e) => {
			let t = Number(e);
			Number.isFinite(t) && t > 0 && n(s.id, C(s, t));
		}, "number"));
		let m = (e, t, i, a, o) => {
			let c = document.createElement("select");
			c.dataset.testid = t, c.disabled = r.disabled, c.append(...a.map((e) => Object.assign(document.createElement("option"), {
				value: e,
				textContent: e
			}))), c.value = i, c.addEventListener("change", () => n(s.id, o(c.value))), l(e, c);
		};
		m("对齐", "canvas-text-align", s.align, [
			"left",
			"center",
			"right"
		], (e) => ({ align: e })), m("基线", "canvas-text-baseline", s.baseline, [
			"alphabetic",
			"top",
			"middle",
			"bottom"
		], (e) => ({ baseline: e })), m("层级", "canvas-text-z-band", s.zBand, ["below-product", "above-product"], (e) => ({ zBand: e }));
		let h = document.createElement("div");
		h.className = "canvas-text-lines", s.lines.forEach((e, t) => {
			let i = document.createElement("fieldset"), a = (e) => {
				let r = s.lines.map((n, r) => r === t ? {
					...n,
					...e
				} : { ...n });
				n(s.id, { lines: r });
			};
			i.append(Wd(`canvas-text-line-text-${t}`, e.text, r.disabled, (e) => a({ text: e })), Wd(`canvas-text-line-x-${t}`, String(e.x), r.disabled, (e) => {
				let t = Number(e);
				Number.isFinite(t) && a({ x: t });
			}, "number"), Wd(`canvas-text-line-y-${t}`, String(e.y), r.disabled, (e) => {
				let t = Number(e);
				Number.isFinite(t) && a({ y: t });
			}, "number"), Wd(`canvas-text-line-width-${t}`, String(e.width), r.disabled, (e) => {
				let t = Number(e);
				Number.isFinite(t) && a({ width: t });
			}, "number")), h.append(i);
		}), c.append(h), a.replaceChildren(i, o, c);
	};
	return o(), {
		element: a,
		update: (e) => {
			i || (r = structuredClone(e), o());
		},
		dispose: () => {
			i = !0, a.replaceChildren();
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/status-bar.ts
var Kd = {
	dirty: "有未保存更改",
	saving: "正在保存…",
	saved: "已保存",
	offline: "离线，等待重试",
	failed: "保存失败",
	conflict: "检测到版本冲突"
}, qd = {
	ready: "抠图：素材已就绪",
	queued: "抠图：已排队",
	running: "抠图：处理中",
	failed: "抠图：失败",
	interrupted: "抠图：已中断"
};
function Jd(e, n) {
	let r = document.createElement("footer");
	return r.className = "canvas-status-bar", r.dataset.testid = "canvas-save-status", r.setAttribute("role", "status"), r.setAttribute("aria-live", "polite"), {
		element: r,
		update: (i, a, o = null) => {
			let s = () => {
				if (o === null) return;
				let e = document.createElement("span");
				e.className = `canvas-cutout-summary is-${o}`, e.dataset.testid = "canvas-cutout-summary", e.textContent = qd[o], r.append(e);
			};
			if (a.status !== "idle") {
				r.dataset.state = `remote-${a.status}`;
				let e = document.createElement("span");
				e.className = `canvas-save-state is-remote-${a.status}`, e.textContent = a.status === "syncing" ? "正在同步远端更改…" : "远端同步失败";
				let i = document.createElement("span");
				if (i.className = "canvas-save-message", i.textContent = a.message === null ? "" : t(a.message, "远端同步失败，请重试"), r.replaceChildren(e, i), a.status === "failed") {
					let e = document.createElement("button");
					e.type = "button", e.textContent = "重试同步", e.dataset.testid = "canvas-remote-sync-retry", e.addEventListener("click", n), r.append(e);
				}
				s();
				return;
			}
			r.dataset.state = i.status;
			let c = document.createElement("span");
			c.className = `canvas-save-state is-${i.status}`, c.textContent = Kd[i.status];
			let l = document.createElement("span");
			if (l.className = "canvas-save-message", l.textContent = i.message === null ? "" : t(i.message, "保存失败，请重试"), r.replaceChildren(c, l), i.status === "offline" || i.status === "failed") {
				let t = document.createElement("button");
				t.type = "button", t.textContent = "重试保存", t.addEventListener("click", e), r.append(t);
			}
			s();
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/top-toolbar.ts
function Yd(e, t, n, r, i, a = {}) {
	let o = !1, s = document.createElement("header");
	s.className = "canvas-top-toolbar", s.dataset.testid = "canvas-top-toolbar";
	let c = document.createElement("button");
	c.type = "button", c.className = "canvas-drawer-toggle canvas-projects-toggle", c.dataset.testid = "canvas-toggle-projects", c.textContent = "项目", c.setAttribute("aria-label", "打开项目列表"), c.addEventListener("click", () => a.onToggleProjects?.());
	let l = document.createElement("div");
	l.className = "canvas-toolbar-title";
	let u = document.createElement("strong"), d = document.createElement("span");
	d.textContent = "产品视觉画布", l.append(u, d);
	let f = document.createElement("label");
	f.textContent = "模式";
	let p = document.createElement("select");
	p.setAttribute("aria-label", "画布模式"), p.dataset.testid = "canvas-mode", p.innerHTML = "<option value=\"complete-set\">完整套图</option><option value=\"advanced\">高级模式</option>", p.addEventListener("change", () => {
		(p.value === "complete-set" || p.value === "advanced") && t({
			type: "mode/set",
			mode: p.value
		});
	}), f.append(p);
	let m = document.createElement("button");
	m.type = "button", m.textContent = "撤销", m.dataset.testid = "canvas-undo", m.addEventListener("click", n);
	let h = document.createElement("button");
	h.type = "button", h.textContent = "重做", h.dataset.testid = "canvas-redo", h.addEventListener("click", r);
	let g = (e) => {
		t({
			type: "viewport/set",
			viewport: e
		});
	}, _ = (t) => {
		let n = e.getState().project.layoutState.viewport;
		g({
			...n,
			zoom: Math.min(1e3, Math.max(.01, n.zoom * t))
		});
	}, v = document.createElement("button");
	v.type = "button", v.textContent = "缩小", v.dataset.testid = "canvas-zoom-out", v.addEventListener("click", () => _(.8));
	let y = document.createElement("button");
	y.type = "button", y.textContent = "放大", y.dataset.testid = "canvas-zoom-in", y.addEventListener("click", () => _(1.25));
	let b = document.createElement("button");
	b.type = "button", b.textContent = "重置视图", b.dataset.testid = "canvas-zoom-reset", b.addEventListener("click", () => g({
		x: 0,
		y: 0,
		zoom: 1
	}));
	let x = document.createElement("output");
	x.dataset.testid = "canvas-zoom-readout", x.setAttribute("aria-label", "当前缩放");
	let S = document.createElement("button");
	S.type = "button", S.textContent = "导出", S.dataset.testid = "canvas-toolbar-export", S.title = "打开导出产品图选项", S.addEventListener("click", () => {
		i?.();
	});
	let C = document.createElement("button");
	C.type = "button", C.className = "canvas-drawer-toggle canvas-inspector-toggle", C.dataset.testid = "canvas-toggle-inspector", C.textContent = "设置", C.setAttribute("aria-label", "打开画布设置"), C.addEventListener("click", () => a.onToggleInspector?.()), s.append(c, l, f, m, h, v, y, b, x, S, C);
	let w = () => {
		let t = e.getState();
		p.value = t.project.semanticState.mode, u.textContent = a.getProjectName?.() ?? "未选择项目", p.disabled = !o, m.disabled = !o || !e.canUndo(), h.disabled = !o || !e.canRedo(), v.disabled = !o, y.disabled = !o, b.disabled = !o;
		let n = a.canExport?.() ?? i !== void 0;
		S.hidden = !n, S.disabled = !o || i === void 0 || !n, c.disabled = a.onToggleProjects === void 0, C.disabled = !o || a.onToggleInspector === void 0, x.value = `${Math.round(t.project.layoutState.viewport.zoom * 100)}%`;
	};
	return w(), {
		element: s,
		update: w,
		setEditable: (e) => {
			o = e, w();
		}
	};
}
//#endregion
//#region frontend/canvas/src/domain/generation.ts
var Xd = {
	main: "main_output",
	sku: "sku_output",
	detail: "detail_output"
}, Zd = {
	main: "主图",
	sku: "SKU图",
	detail: "详情图"
};
function $(e, t, n) {
	return {
		ok: !1,
		reasons: [{
			code: e,
			message: t,
			...n === void 0 ? {} : { outputType: n }
		}]
	};
}
function Qd(e, t) {
	let n = (e, t) => t === 0 ? e : n(t, e % t), r = n(e, t);
	return `${e / r}:${t / r}`;
}
function $d(e) {
	return `${e.outputType}:${e.skuId ?? "main"}`;
}
function ef(e) {
	return e.quantity ?? 0;
}
function tf(e, t) {
	if (t === null) return null;
	let n = e.find((e) => e.id === t);
	return n !== void 0 && n.enabled && n.availability === "available" ? n : null;
}
function nf(e, t, n, r, i, a) {
	let o = e.capabilities;
	if (!o.textToImage || o.maxQuantity < 1) return $("model_capability_invalid", `${i}所选模型不能生成单张图`, a);
	if (r > 0 && (!o.imageToImage || o.maxReferenceImages < r || o.referenceTransfer === "none")) return $("model_capability_invalid", `${i}所选模型不支持产品参考图`, a);
	let s = Qd(t, n);
	return o.allowedRatios.length > 0 && !o.allowedRatios.includes(s) || o.allowedSizes.length > 0 && !o.allowedSizes.includes(`${t}x${n}`) || o.minWidth !== null && t < o.minWidth || o.maxWidth !== null && t > o.maxWidth || o.minHeight !== null && n < o.minHeight || o.maxHeight !== null && n > o.maxHeight ? $("model_capability_invalid", `${i}尺寸不受所选模型支持`, a) : null;
}
function rf(e) {
	return e.layoutState.productLayers.find((e) => e.skuId === null && e.locked)?.sourceAssetId ?? null;
}
function af(e, t) {
	let n = e.layoutState.productLayers.find((e) => e.skuId === t.skuId && e.locked);
	if (t.outputType !== "sku") return t.referenceAssetId ?? n?.sourceAssetId ?? null;
	let r = rf(e);
	return n === void 0 ? t.referenceAssetId !== null && t.referenceAssetId === r ? r : null : t.referenceAssetId === null || t.referenceAssetId === n.sourceAssetId ? n.sourceAssetId : t.referenceAssetId === r ? r : null;
}
function of(e, t, n) {
	let r = e.layoutState.productLayers.find((e) => e.skuId === null && e.locked);
	if (r === void 0) return null;
	let i = e.semanticState.nodes.find((e) => e.id === "main-product-source"), a = e.semanticState.nodes.find((e) => e.id === "main-product-cutout");
	if (i?.kind !== "product_source" || i.skuId !== null || i.assetId !== r.sourceAssetId || a?.kind !== "auto_cutout" || a.skuId !== null || a.assetId !== r.renderAssetId) return null;
	let o = e.semanticState.edges.filter((e) => e.kind === "product_asset" && e.targetNodeId === a.id);
	if (o.length !== 1 || o[0]?.sourceNodeId !== i.id) return null;
	let s = e.semanticState.edges.filter((e) => e.kind === "cutout_asset" && e.targetNodeId === t);
	return s.length === 1 && s[0]?.sourceNodeId === a.id ? a.assetId : null;
}
function sf(e, t) {
	return $("advanced_graph_invalid", e, t);
}
function cf(e) {
	let t = e.parameters.width, n = e.parameters.height;
	return typeof t != "number" || !Number.isInteger(t) || t < 1 || typeof n != "number" || !Number.isInteger(n) || n < 1 ? null : {
		width: t,
		height: n,
		ratio: Qd(t, n)
	};
}
function lf(e, t, n) {
	let r = e.semanticState.edges.filter((e) => e.kind === t && e.targetNodeId === n);
	return r.length === 1 ? r[0] : null;
}
function uf(e, t) {
	let n = [];
	for (let r of e.semanticState.edges) {
		if (r.kind !== "text_layer" || r.targetNodeId !== t) continue;
		let i = e.semanticState.nodes.find((e) => e.id === r.sourceNodeId);
		if (i?.kind !== "text_layer" || i.textSnapshotId === null) return null;
		n.push(i.textSnapshotId);
	}
	if (new Set(n).size !== n.length) return null;
	let r = n.map((t) => e.layoutState.textSnapshots.find((e) => e.id === t));
	return r.some((e) => e === void 0) ? null : r.sort((e, t) => e.sortOrder - t.sortOrder || e.id.localeCompare(t.id)).map((e) => e.id);
}
function df(e, t, n) {
	let r = [];
	for (let n of e.semanticState.outputBoards) {
		let i = e.semanticState.nodes.find((e) => e.id === n.outputNodeId);
		if (i === void 0 || i.outputBoardId !== n.id || i.kind !== Xd[n.outputType]) return sf("高级模式输出画板缺少绑定节点", n.outputType);
		if (i.modelProfileId !== null || i.prompt !== null || i.compositionGroupId !== null) return sf("高级模式输出绑定必须通过连线表达", n.outputType);
		if (e.semanticState.edges.some((e) => e.kind === "background_image" && e.targetNodeId === i.id)) return sf("高级模式暂不支持背景图连线", n.outputType);
		let a = lf(e, "output_image", i.id), o = a === null ? void 0 : e.semanticState.nodes.find((e) => e.id === a.sourceNodeId);
		if (o?.kind !== "model_generation") return sf("高级模式输出必须连接生成节点", n.outputType);
		let s = lf(e, "prompt", o.id), c = s === null ? "" : e.semanticState.nodes.find((e) => e.id === s.sourceNodeId)?.prompt ?? "";
		if (c.trim() === "") return sf("高级模式生成节点缺少提示词", n.outputType);
		let l = tf(t, o.modelProfileId);
		if (l === null) return $("model_unavailable", "高级模式需要选择可用模型", n.outputType);
		let u = cf(o);
		if (u === null) return $("invalid_dimensions", "高级模式生成节点需要有效宽高", n.outputType);
		let d = of(e, o.id, n.skuId);
		if (d === null) return $("product_missing", "高级模式生成节点缺少产品参考图", n.outputType);
		let f = lf(e, "composition", i.id), p = (f === null ? void 0 : e.semanticState.nodes.find((e) => e.id === f.sourceNodeId))?.compositionGroupId ?? null, m = p === null ? void 0 : e.semanticState.compositionGroups.find((e) => e.id === p);
		if (m === void 0) return $("composition_missing", "高级模式输出缺少构图组", n.outputType);
		let h = uf(e, i.id);
		if (h === null) return sf("高级模式文字必须通过文字图层连线到输出画板", n.outputType);
		let g = nf(l, u.width, u.height, 1, Zd[n.outputType], n.outputType);
		if (g !== null) return g;
		r.push({
			outputType: n.outputType,
			skuId: n.skuId,
			boardId: n.id,
			nodeId: i.id,
			boardOrder: n.sortOrder,
			modelProfileId: o.modelProfileId,
			prompt: c.trim(),
			width: u.width,
			height: u.height,
			ratio: u.ratio,
			compositionGroupId: m.id,
			layoutHash: m.layoutHash,
			inputs: [{
				assetId: d,
				inputRole: "product",
				ordinal: 0
			}],
			textSnapshotIds: h
		});
	}
	return r.length === 0 ? sf("高级模式没有连接的输出画板") : r.length > 50 ? $("too_many_items", "本次生成最多支持 50 张图") : {
		ok: !0,
		request: {
			revision: n,
			mode: "advanced",
			items: r
		}
	};
}
function ff(e, t, n) {
	if (!Number.isInteger(n) || n < 1) throw Error("generation revision must be a positive integer");
	if (e.semanticState.mode === "advanced") return df(e, t, n);
	let r = e.semanticState.completeSet.selectedOutputTypes;
	if (r.length === 0) return $("no_output_selected", "至少选择一种输出类型");
	let i = new Set(r), a = e.semanticState.completeSet.outputs.filter((e) => i.has(e.outputType)), o = new Set(r.flatMap((e) => e === "sku" ? a.filter((e) => e.outputType === "sku").map($d) : [$d({
		outputType: e,
		skuId: null
	})]));
	if (a.length === 0 || o.size !== a.length) {
		let e = r.find((e) => e === "sku" ? !a.some((e) => e.outputType === "sku") : !a.some((t) => t.outputType === e && t.skuId === null));
		return $("output_configuration_missing", `${Zd[e ?? r[0]]}缺少生成配置`, e ?? r[0]);
	}
	let s = [];
	for (let n of a) {
		let r = Zd[n.outputType], i = ef(n);
		if (!Number.isInteger(i) || i < 1 || i > 20) return $("invalid_quantity", `${r}数量必须为 1 到 20`, n.outputType);
		if (!Number.isInteger(n.width) || !Number.isInteger(n.height) || n.width === null || n.height === null || n.width < 1 || n.height < 1 || n.aspectRatio === null || n.aspectRatio !== Qd(n.width, n.height)) return $("invalid_dimensions", `${r}需要匹配的比例与尺寸`, n.outputType);
		let a = tf(t, n.modelProfileId);
		if (a === null) return $("model_unavailable", `${r}需要选择可用模型`, n.outputType);
		let o = e.layoutState.productLayers.find((e) => e.skuId === n.skuId && e.locked), c = af(e, n);
		if (c === null) return $("product_missing", n.outputType === "sku" ? "SKU图缺少自身产品参考图或明确的主产品复用" : `${r}缺少产品参考图`, n.outputType);
		let l = n.compositionGroupId ?? o?.compositionGroupId ?? null, u = l === null ? null : e.semanticState.compositionGroups.find((e) => e.id === l);
		if (u == null) return $("composition_missing", `${r}缺少构图组`, n.outputType);
		let d = nf(a, n.width, n.height, 1, r, n.outputType);
		if (d !== null) return d;
		let f = e.semanticState.outputBoards.filter((e) => e.outputType === n.outputType && e.skuId === n.skuId).sort((e, t) => e.sortOrder - t.sortOrder || e.id.localeCompare(t.id));
		if (f.length !== i) return $("board_count_mismatch", `${r}的画板数量与输出数量不一致`, n.outputType);
		for (let t of f) {
			let i = e.semanticState.nodes.find((e) => e.id === t.outputNodeId);
			if (i === void 0 || i.kind !== Xd[n.outputType] || i.outputBoardId !== t.id) return $("output_binding_missing", `${r}缺少独立输出节点`, n.outputType);
			s.push({
				outputType: n.outputType,
				skuId: n.skuId,
				boardId: t.id,
				nodeId: i.id,
				boardOrder: t.sortOrder,
				modelProfileId: n.modelProfileId,
				prompt: n.prompt.trim(),
				width: n.width,
				height: n.height,
				ratio: n.aspectRatio,
				compositionGroupId: u.id,
				layoutHash: u.layoutHash,
				inputs: [{
					assetId: c,
					inputRole: "product",
					ordinal: 0
				}],
				textSnapshotIds: e.layoutState.textSnapshots.map((e) => e.id)
			});
		}
	}
	if (s.length > 50) return $("too_many_items", "本次生成最多支持 50 张图");
	let c = new Set(s.map((e) => e.boardId)), l = new Set(s.map((e) => e.nodeId));
	return c.size !== s.length || l.size !== s.length ? $("output_binding_missing", "每张生成图必须绑定独立画板和输出节点") : {
		ok: !0,
		request: {
			revision: n,
			mode: e.semanticState.mode,
			items: s
		}
	};
}
function pf(e, t, n) {
	return !Number.isInteger(n) || n < 1 ? $("revision_pending", "项目尚未保存，暂不能生成") : ff(e, t, n);
}
//#endregion
//#region frontend/canvas/src/components/model-selector.ts
function mf({ label: e, value: t, models: n, disabled: i, requirements: a, onChange: o }) {
	let s = document.createElement("label");
	s.className = "canvas-model-selector", s.textContent = e;
	let c = document.createElement("select");
	c.setAttribute("aria-label", e), c.disabled = i, c.append(Object.assign(document.createElement("option"), {
		value: "",
		textContent: "请选择模型"
	}));
	for (let e of n) {
		let t = document.createElement("option");
		t.value = e.id, t.textContent = e.availability === "available" && e.enabled ? e.displayName : `${e.displayName}（不可用）`, t.disabled = !e.enabled || e.availability !== "available", c.append(t);
	}
	c.value = t ?? "", c.addEventListener("change", () => o(c.value === "" ? null : c.value)), s.append(c);
	let l = t === null ? void 0 : n.find((e) => e.id === t);
	if (l !== void 0 && a !== void 0) {
		let e = r(l, a);
		if (e.length > 0) {
			let t = document.createElement("small");
			t.className = "canvas-model-selector-reason", t.dataset.testid = "canvas-model-capability-reason", t.textContent = e.join("；"), s.append(t);
		}
	}
	return s;
}
//#endregion
//#region frontend/canvas/src/components/complete-set-panel.ts
var hf = [
	"main",
	"sku",
	"detail"
], gf = {
	main: "主图",
	sku: "SKU 图",
	detail: "详情图"
};
function _f(e, t) {
	if (e === null || t === null || e < 1 || t < 1) return null;
	let n = (e, t) => t === 0 ? e : n(t, e % t), r = n(e, t);
	return `${e / r}:${t / r}`;
}
function vf(e, t, n) {
	return e.semanticState.completeSet.outputs.find((e) => e.outputType === t && e.skuId === n) ?? null;
}
function yf(e, t, n, r, i) {
	let a = document.createElement("label");
	a.textContent = e;
	let o = document.createElement("select");
	o.setAttribute("aria-label", e), o.disabled = r, o.append(Object.assign(document.createElement("option"), {
		value: "",
		textContent: "自动使用产品图"
	}));
	for (let e of n) o.append(Object.assign(document.createElement("option"), {
		value: e.id,
		textContent: e.label
	}));
	return o.value = t ?? "", o.addEventListener("change", () => i(o.value || null)), a.append(o), a;
}
function bf(e) {
	let t = document.createElement("section");
	t.className = "canvas-complete-set-panel", t.dataset.testid = "canvas-complete-set-panel";
	let n = (t, n, r, i) => {
		let a = document.createElement("fieldset");
		a.className = "canvas-output-control";
		let o = document.createElement("legend");
		o.textContent = r === null ? gf[n] : `${gf[n]} · ${e.getSkus().find((e) => e.id === r)?.name ?? r}`, a.append(o);
		let s = !e.isEditable(), c = i?.modelProfileId === null || i?.modelProfileId === void 0 ? void 0 : e.getModels().find((e) => e.id === i.modelProfileId), l = document.createElement("input");
		l.type = "number", l.min = "1", l.max = String(Math.min(20, c?.capabilities.maxQuantity ?? 20)), l.value = i?.quantity === null || i?.quantity === void 0 ? "" : String(i.quantity), l.disabled = s, l.setAttribute("aria-label", `${o.textContent}数量`), l.addEventListener("change", () => {
			let t = l.value === "" ? null : Number(l.value);
			t !== null && (!Number.isInteger(t) || t < 1 || t > 20) || e.dispatch(n === "sku" ? {
				type: "sku/setOutputQuantity",
				skuId: r,
				quantity: t
			} : {
				type: "output/setQuantity",
				outputType: n,
				quantity: t
			});
		});
		let u = document.createElement("label");
		if (u.textContent = "数量", u.append(l), a.append(u), i === null) return a;
		let d = (t) => {
			e.dispatch({
				type: "output/configure",
				outputType: n,
				skuId: r,
				patch: t
			});
		};
		a.append(mf({
			label: `${o.textContent}模型`,
			value: i.modelProfileId,
			models: e.getModels(),
			disabled: s,
			requirements: {
				width: i.width,
				height: i.height,
				quantity: i.quantity,
				referenceCount: 1,
				requiresMask: !1
			},
			onChange: (e) => d({ modelProfileId: e })
		}));
		let f = document.createElement("textarea");
		f.value = i.prompt, f.disabled = s, f.setAttribute("aria-label", `${o.textContent}提示词`), f.addEventListener("input", () => d({ prompt: f.value }));
		let p = document.createElement("label");
		p.textContent = "提示词", p.append(f), a.append(p);
		let m = (e, t) => {
			let n = document.createElement("label");
			n.textContent = t;
			let r = document.createElement("input");
			r.type = "number";
			let a = e === "width" ? c?.capabilities.minWidth : c?.capabilities.minHeight, o = e === "width" ? c?.capabilities.maxWidth : c?.capabilities.maxHeight;
			return r.min = String(a ?? 1), o != null && (r.max = String(o)), r.value = i[e] === null ? "" : String(i[e]), r.disabled = s, r.addEventListener("change", () => {
				let t = r.value === "" ? null : Number(r.value), n = e === "width" ? t : i.width, a = e === "height" ? t : i.height;
				d({
					width: n,
					height: a,
					aspectRatio: _f(n, a)
				});
			}), n.append(r), n;
		};
		a.append(m("width", "宽"), m("height", "高"));
		let h = t.semanticState.compositionGroups.map((e) => ({
			id: e.id,
			label: e.id
		})), g = c !== void 0 && (!c.capabilities.imageToImage || c.capabilities.maxReferenceImages < 1 || c.capabilities.referenceTransfer === "none");
		return a.append(yf("产品参考图", i.referenceAssetId, e.getReferenceAssets(), s || g, (e) => d({ referenceAssetId: e })), yf("构图组", i.compositionGroupId, h, s, (e) => d({ compositionGroupId: e }))), a;
	}, r = () => {
		let r = e.getProject(), i = new Set(r.semanticState.completeSet.selectedOutputTypes), a = document.createElement("h2");
		a.textContent = "套图生成";
		let o = document.createElement("p");
		o.textContent = "按需选择主图、SKU 图和详情图；未选择时不会生成。";
		let s = document.createElement("div");
		s.className = "canvas-output-type-selector";
		for (let t of hf) {
			let n = document.createElement("input");
			n.type = "checkbox", n.checked = i.has(t), n.setAttribute("aria-label", `启用${gf[t]}`), n.disabled = !e.isEditable(), n.addEventListener("change", () => e.dispatch({
				type: n.checked ? "output/enable" : "output/disable",
				outputType: t
			}));
			let r = document.createElement("button");
			r.type = "button", r.dataset.testid = `canvas-output-${t}`, r.dataset.selected = String(i.has(t)), r.setAttribute("aria-pressed", String(i.has(t))), r.disabled = !e.isEditable(), r.textContent = i.has(t) ? `已选${gf[t]}` : `选择${gf[t]}`, r.addEventListener("click", () => {
				n.checked = !n.checked, n.dispatchEvent(new Event("change", { bubbles: !0 }));
			});
			let a = document.createElement("label");
			a.className = "canvas-output-choice", a.append(n, r), s.append(a);
		}
		let c = document.createElement("div");
		c.className = "canvas-complete-set-form";
		for (let e of ["main", "detail"]) i.has(e) && c.append(n(r, e, null, vf(r, e, null)));
		if (i.has("sku")) {
			let t = e.getSkus();
			t.length === 0 && c.append(Object.assign(document.createElement("p"), { textContent: "请先新增 SKU，再设置 SKU 图数量。" }));
			for (let e of t) c.append(n(r, "sku", e.id, vf(r, "sku", e.id)));
		}
		let l = e.getModels().filter((e) => e.enabled && e.availability === "available"), u = document.createElement("div"), d = document.createElement("select");
		d.append(Object.assign(document.createElement("option"), {
			value: "",
			textContent: "应用同一模型到全部已选类型"
		}));
		for (let e of l) d.append(Object.assign(document.createElement("option"), {
			value: e.id,
			textContent: e.displayName
		}));
		let f = document.createElement("button");
		f.type = "button", f.textContent = "确认应用", f.disabled = !e.isEditable(), f.addEventListener("click", () => {
			if (!(d.value === "" || !window.confirm("将覆盖已选输出的模型选择，是否继续？"))) for (let t of r.semanticState.completeSet.outputs) i.has(t.outputType) && e.dispatch({
				type: "output/configure",
				outputType: t.outputType,
				skuId: t.skuId,
				patch: { modelProfileId: d.value }
			});
		}), u.append(d, f);
		let p = r.semanticState.completeSet.outputs.filter((e) => i.has(e.outputType)), m = p.reduce((e, t) => e + (t.quantity ?? 0), 0), h = document.createElement("p");
		h.dataset.testid = "canvas-generation-item-count", h.textContent = `实际生成数量：${m}`;
		let g = p.map((t) => e.getModels().find((e) => e.id === t.modelProfileId)?.priceMetadata?.amount);
		if (g.length > 0 && g.every((e) => typeof e == "number")) {
			let e = g.reduce((e, t, n) => e + t * (p[n]?.quantity ?? 0), 0);
			h.textContent += `；预估价格：${e}`;
		}
		let _ = pf(r, [...e.getModels()], e.getRevision()), v = document.createElement("p");
		v.dataset.testid = "canvas-generation-validation", v.textContent = _.ok ? "生成配置已就绪" : _.reasons.map((e) => e.message).join("；");
		let y = document.createElement("button");
		y.type = "button", y.dataset.testid = "canvas-generate", y.textContent = "生成已选套图", y.disabled = !e.isEditable() || !_.ok, y.addEventListener("click", () => e.onGenerate()), t.replaceChildren(a, o, s, c, u, h, v, y);
	};
	return r(), {
		element: t,
		update: r
	};
}
//#endregion
//#region frontend/canvas/src/components/generation-status.ts
function xf() {
	let e = document.createElement("p");
	return e.className = "canvas-generation-status", e.dataset.testid = "canvas-generation-status", e.setAttribute("role", "status"), {
		element: e,
		update: (t, n = "idle") => {
			e.dataset.tone = n, e.textContent = t;
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/node-inspector.ts
function Sf() {
	let e = document.createElement("section");
	e.className = "canvas-node-inspector";
	let t = null, n = (r, i, a, o, s) => {
		let c = document.createElement("h3");
		c.textContent = "节点检查器";
		let l = document.createElement("select");
		l.setAttribute("aria-label", "选择高级节点");
		let u = (e) => e.managedBy !== null || e.id === "main-product-source" || e.id === "main-product-cutout", d = [...r];
		d.filter((e) => !u(e));
		for (let e of d) l.append(Object.assign(document.createElement("option"), {
			value: e.id,
			textContent: `${e.kind} · ${e.id}`
		}));
		d.some((e) => e.id === t) || (t = d[0]?.id ?? null), l.value = t ?? "";
		let f = d.find((e) => e.id === t) ?? null, p = f !== null && u(f), m = document.createElement("textarea");
		m.value = f?.prompt ?? "", m.disabled = a || f === null || p, m.setAttribute("aria-label", "节点提示词"), m.addEventListener("input", () => {
			f !== null && !p && o(f.id, { prompt: m.value });
		});
		let h = [
			c,
			l,
			m
		];
		if (f?.kind === "model_generation") {
			let e = document.createElement("select");
			e.setAttribute("aria-label", "节点模型"), e.disabled = a || p, e.append(Object.assign(document.createElement("option"), {
				value: "",
				textContent: "选择模型"
			}));
			for (let t of i.filter((e) => e.enabled && e.availability === "available")) e.append(Object.assign(document.createElement("option"), {
				value: t.id,
				textContent: t.displayName
			}));
			e.value = f.modelProfileId ?? "", e.addEventListener("change", () => {
				o(f.id, { modelProfileId: e.value || null });
			});
			let t = (e, t) => {
				let n = document.createElement("input");
				return n.type = "number", n.min = "1", n.step = "1", n.value = typeof t == "number" ? String(t) : "", n.disabled = a || p, n.setAttribute("aria-label", e), n;
			}, n = t("生成宽度", f.parameters.width), r = t("生成高度", f.parameters.height), s = () => {
				let e = Number(n.value), t = Number(r.value);
				o(f.id, { parameters: {
					...Number.isInteger(e) && e > 0 ? { width: e } : {},
					...Number.isInteger(t) && t > 0 ? { height: t } : {}
				} });
			};
			n.addEventListener("change", s), r.addEventListener("change", s), h.push(e, n, r);
		}
		if (f?.kind === "sku_reference" || f?.kind === "auto_cutout" || f?.kind === "product_source") {
			let e = document.createElement("input");
			e.type = "text", e.value = f.assetId ?? "", e.disabled = a || p, e.setAttribute("aria-label", "节点资源 ID"), e.addEventListener("change", () => o(f.id, { assetId: e.value.trim() || null })), h.push(e);
		}
		if (f?.kind === "sku_reference" || f?.kind === "auto_cutout") {
			let e = document.createElement("input");
			e.type = "text", e.value = f.skuId ?? "", e.disabled = a || p, e.setAttribute("aria-label", "节点 SKU ID"), e.addEventListener("change", () => o(f.id, { skuId: e.value.trim() || null })), h.push(e);
		}
		if (f?.kind === "composition_group") {
			let e = document.createElement("input");
			e.type = "text", e.value = f.compositionGroupId ?? "", e.disabled = a || p, e.setAttribute("aria-label", "节点构图组 ID"), e.addEventListener("change", () => o(f.id, { compositionGroupId: e.value.trim() || null })), h.push(e);
		}
		if (l.addEventListener("change", () => {
			t = l.value || null, n(r, i, a, o, s);
		}), s !== void 0) {
			let e = document.createElement("select"), t = document.createElement("select");
			e.setAttribute("aria-label", "连线来源"), t.setAttribute("aria-label", "连线目标");
			for (let n of d) e.append(Object.assign(document.createElement("option"), {
				value: n.id,
				textContent: `${n.kind} · ${n.id}`
			})), t.append(Object.assign(document.createElement("option"), {
				value: n.id,
				textContent: `${n.kind} · ${n.id}`
			}));
			let n = d[0], r = n === void 0 ? void 0 : d.find((e) => e.id !== n.id && O(n.kind, e.kind).length > 0);
			e.value = n?.id ?? "", t.value = r?.id ?? n?.id ?? "";
			let i = document.createElement("button");
			i.type = "button", i.textContent = "连接节点";
			let o = () => {
				let n = d.find((t) => t.id === e.value), r = d.find((e) => e.id === t.value);
				i.disabled = a || n === void 0 || r === void 0 || n.id === r.id || O(n.kind, r.kind).length === 0;
			};
			e.addEventListener("change", o), t.addEventListener("change", o), i.addEventListener("click", () => {
				let n = d.find((t) => t.id === e.value), r = d.find((e) => e.id === t.value);
				n !== void 0 && r !== void 0 && n.id !== r.id && O(n.kind, r.kind).length > 0 && s(e.value, t.value);
			}), o(), h.push(e, t, i);
		}
		e.replaceChildren(...h);
	};
	return {
		element: e,
		update: n
	};
}
//#endregion
//#region frontend/canvas/src/components/node-toolbar.ts
var Cf = [
	"prompt",
	"model_generation",
	"composition_group",
	"text_layer"
];
function wf(e, t) {
	return {
		id: t,
		kind: e,
		managedBy: null,
		skuId: null,
		assetId: null,
		modelProfileId: null,
		prompt: e === "prompt" ? "" : null,
		compositionGroupId: null,
		textSnapshotId: null,
		outputBoardId: null,
		parameters: {}
	};
}
function Tf({ disabled: e, onAdd: t, nextId: n }) {
	let r = document.createElement("section");
	r.className = "canvas-node-toolbar", r.append(Object.assign(document.createElement("h3"), { textContent: "高级节点" }));
	for (let i of Cf) {
		let a = document.createElement("button");
		a.type = "button", a.disabled = e, a.textContent = `添加 ${i}`, a.addEventListener("click", () => {
			t(wf(i, n(i)));
		}), r.append(a);
	}
	return r;
}
//#endregion
//#region frontend/canvas/src/components/result-board.ts
function Ef(e) {
	let t = document.createElement("section");
	return t.className = "canvas-result-board", {
		element: t,
		update: (n, r, i, a) => {
			let o = document.createElement("h3");
			if (o.textContent = "结果版本", n === null) {
				t.replaceChildren(o, Object.assign(document.createElement("p"), { textContent: "暂无输出画板" }));
				return;
			}
			let s = r.filter((e) => e.boardId === n.id), c = document.createElement("p");
			c.className = "canvas-result-board-hint", c.textContent = s.length === 0 ? "生成完成后，成功版本会出现在这里。" : "对比版本并显式选择一个成功结果，才能继续导出。";
			let l = document.createElement("div");
			l.className = "canvas-result-version-grid", l.setAttribute("role", "listbox"), l.setAttribute("aria-label", "选择结果版本");
			for (let t of s) {
				let r = document.createElement("button");
				if (r.type = "button", r.className = "canvas-result-version", r.disabled = i, r.dataset.assetId = t.composedAssetId, r.setAttribute("role", "option"), r.setAttribute("aria-selected", t.composedAssetId === n.selectedResultAssetId ? "true" : "false"), t.composedAssetId === n.selectedResultAssetId && r.classList.add("is-selected"), e !== void 0) {
					let n = document.createElement("img");
					n.src = e(t.composedPreviewAssetId || t.composedAssetId), n.alt = `${t.modelDisplayName} 生成版本预览`, n.loading = "lazy", r.append(n);
				}
				let o = document.createElement("strong");
				o.textContent = t.modelDisplayName;
				let s = document.createElement("span");
				s.textContent = `${t.width} × ${t.height} · ${new Date(t.createdAt).toLocaleString("zh-CN", { hour12: !1 })}`;
				let c = document.createElement("span");
				c.className = "canvas-result-selected-label", c.textContent = t.composedAssetId === n.selectedResultAssetId ? "已选版本" : "选择此版本", r.append(o, s, c), r.addEventListener("click", () => a(t.composedAssetId)), l.append(r);
			}
			let u = document.createElement("button");
			u.type = "button", u.className = "canvas-result-clear", u.textContent = "取消当前选择", u.hidden = n.selectedResultAssetId === null, u.disabled = i, u.addEventListener("click", () => a(null)), t.replaceChildren(o, c, l, u);
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/export-panel.ts
var Df = [
	["single", "单张图片"],
	["category_zip", "分类 ZIP"],
	["detail_slices_zip", "详情切片 ZIP"],
	["detail_long", "详情长图"]
], Of = [
	["png", "PNG"],
	["jpeg", "JPEG"],
	["webp", "WebP"]
], kf = {
	main: "主图",
	sku: "SKU 图",
	detail: "详情页"
};
function Af() {
	return typeof crypto.randomUUID == "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function jf(e) {
	let n = document.createElement("section");
	n.className = "canvas-export-panel", n.dataset.testid = "canvas-export-panel";
	let r = [], i = null, a = null, o = "#ffffff", s = !1, c = null, l = "", u = 0, d = null, f = !1, p = () => {
		let t = e.getVersions();
		return e.getProject().semanticState.outputBoards.slice().sort((e, t) => e.sortOrder - t.sortOrder || e.id.localeCompare(t.id)).flatMap((e) => {
			if (e.selectedResultAssetId === null) return [];
			let n = t.find((t) => t.boardId === e.id && t.composedAssetId === e.selectedResultAssetId);
			return n === void 0 ? [] : [{
				board: e,
				version: n
			}];
		});
	}, m = (e) => {
		if (r.length === 0) return "请选择至少一个已保存结果";
		if (i === null) return "请选择导出方式";
		if (a === null) return "请选择图片格式";
		if (i === "single" && r.length !== 1) return "单张图片只能选择一个画板";
		let t = r.map((t) => e.find((e) => e.board.id === t));
		return t.some((e) => e === void 0) ? "所选结果已变化，请重新选择" : (i === "detail_slices_zip" || i === "detail_long") && t.some((e) => e?.board.outputType !== "detail") ? "详情导出只能选择详情页画板" : null;
	}, h = (e) => {
		switch (e.status) {
			case "queued": return "导出任务已进入队列";
			case "running": return "正在生成导出文件…";
			case "succeeded": return "导出完成";
			case "cancel_requested": return "正在取消导出任务…";
			case "cancelled": return "导出任务已取消";
			case "failed":
			case "interrupted": return t(e.safeError?.message, "导出失败，请重试");
		}
	}, g = () => {
		if (f) return;
		let t = p(), u = new Set(t.map((e) => e.board.id));
		r = r.filter((e) => u.has(e));
		let d = Object.assign(document.createElement("h3"), { textContent: "导出产品图" }), h = Object.assign(document.createElement("p"), {
			className: "canvas-export-description",
			textContent: "选择已保存的结果、导出方式和格式。所有选项均由你决定。"
		}), v = document.createElement("div");
		v.className = "canvas-export-boards", t.length === 0 && v.append(Object.assign(document.createElement("p"), { textContent: "请先在结果版本中保存至少一个画板结果。" }));
		for (let { board: n, version: i } of t) {
			let t = document.createElement("div");
			t.className = "canvas-export-board-row";
			let a = document.createElement("label"), o = document.createElement("input");
			o.type = "checkbox", o.checked = r.includes(n.id), o.disabled = s || !e.isEditable(), o.dataset.boardId = n.id, o.addEventListener("change", () => {
				o.checked ? r.includes(n.id) || r.push(n.id) : r = r.filter((e) => e !== n.id), l = "", g();
			});
			let c = n.outputType === "sku" && n.skuId !== null ? `${kf[n.outputType]} · ${n.skuId}` : kf[n.outputType], u = document.createElement("span");
			if (u.innerHTML = "<strong></strong><small></small>", u.querySelector("strong").textContent = c, u.querySelector("small").textContent = `${i.modelDisplayName} · ${i.width}×${i.height}`, a.append(o, u), t.append(a), o.checked) {
				let e = r.indexOf(n.id), i = Object.assign(document.createElement("button"), {
					type: "button",
					textContent: "上移",
					disabled: s || e === 0
				});
				i.setAttribute("aria-label", `上移${c}`), i.addEventListener("click", () => {
					[r[e - 1], r[e]] = [r[e], r[e - 1]], g();
				});
				let a = Object.assign(document.createElement("button"), {
					type: "button",
					textContent: "下移",
					disabled: s || e === r.length - 1
				});
				a.setAttribute("aria-label", `下移${c}`), a.addEventListener("click", () => {
					[r[e], r[e + 1]] = [r[e + 1], r[e]], g();
				}), t.append(i, a);
			}
			v.append(t);
		}
		let y = document.createElement("fieldset");
		y.className = "canvas-export-choice-group", y.append(Object.assign(document.createElement("legend"), { textContent: "导出方式" }));
		for (let [t, n] of Df) {
			let r = Object.assign(document.createElement("button"), {
				type: "button",
				textContent: n,
				disabled: s || !e.isEditable()
			});
			r.dataset.exportMode = t, r.setAttribute("aria-pressed", String(i === t)), r.addEventListener("click", () => {
				i = t, l = "", g();
			}), y.append(r);
		}
		let b = document.createElement("fieldset");
		b.className = "canvas-export-choice-group", b.append(Object.assign(document.createElement("legend"), { textContent: "图片格式" }));
		for (let [t, n] of Of) {
			let r = Object.assign(document.createElement("button"), {
				type: "button",
				textContent: n,
				disabled: s || !e.isEditable()
			});
			r.dataset.exportFormat = t, r.setAttribute("aria-pressed", String(a === t)), r.addEventListener("click", () => {
				a = t, l = "", g();
			}), b.append(r);
		}
		let x = [
			d,
			h,
			v,
			y,
			b
		];
		if (a === "jpeg") {
			let e = document.createElement("label");
			e.className = "canvas-export-jpeg-background", e.textContent = "JPEG 透明区域背景";
			let t = document.createElement("input");
			t.type = "color", t.value = o, t.disabled = s, t.addEventListener("input", () => {
				o = t.value;
			}), e.append(t), x.push(e);
		}
		let S = m(t), C = Object.assign(document.createElement("button"), {
			type: "button",
			className: "canvas-export-submit",
			textContent: s ? "正在提交…" : "开始导出",
			disabled: s || !e.isEditable() || S !== null
		});
		C.dataset.testid = "canvas-export-submit", C.addEventListener("click", () => {
			_();
		});
		let w = document.createElement("p");
		if (w.className = "canvas-export-feedback", w.dataset.tone = c?.status === "succeeded" ? "success" : c !== null && [
			"failed",
			"interrupted",
			"cancelled"
		].includes(c.status) ? "error" : s || c !== null ? "working" : "idle", w.textContent = l || S || "", x.push(C, w), c?.status === "succeeded" && c.outputAssetId !== null && c.outputAssetId !== void 0) {
			let t = Object.assign(document.createElement("a"), {
				className: "canvas-export-download",
				textContent: "下载导出文件",
				href: e.api.downloadUrl(c.outputAssetId)
			});
			t.dataset.testid = "canvas-export-download", x.push(t);
		}
		n.replaceChildren(...x);
	}, _ = async () => {
		let n = e.getProjectId(), v = p(), y = m(v);
		if (s || n === null || y !== null || i === null || a === null) {
			l = y ?? "当前没有可导出的项目", g();
			return;
		}
		let b = ++u;
		s = !0, l = "正在保存项目…", g();
		let x = await e.flushSave();
		if (f || b !== u || e.getProjectId() !== n) return;
		if (!x.ok) {
			s = !1, l = x.kind === "conflict" ? "项目版本有冲突，请刷新后重试" : t(x.message, "项目保存失败，请重试"), g();
			return;
		}
		let S = p(), C = m(S);
		if (C !== null) {
			s = !1, l = C, g();
			return;
		}
		let w = r.map((e, t) => {
			let n = S.find((t) => t.board.id === e);
			return {
				boardId: e,
				versionId: n.version.versionId,
				composedAssetId: n.version.composedAssetId,
				order: t
			};
		}), T = {
			projectRevision: e.getRevision(),
			mode: i,
			format: a,
			selectedBoards: w,
			jpegBackground: a === "jpeg" ? o : null
		}, E = new AbortController();
		d?.abort(), d = E, l = "正在提交导出任务…", g();
		let D = await e.api.create(n, T, `export:${Af()}`, E.signal);
		if (!(f || b !== u || d !== E || e.getProjectId() !== n)) {
			if (d = null, s = !1, !D.ok) {
				l = t(D.message, "导出请求失败，请重试"), g(), D.kind === "unauthorized" && e.onUnauthorized(() => {
					_();
				});
				return;
			}
			c = D.value, l = h(D.value), e.onOperation?.(D.value), g();
		}
	}, v = {
		element: n,
		update: g,
		applyOperation: (t) => {
			t.operationType !== "export" || t.projectId !== e.getProjectId() || c !== null && t.id !== c.id || (c = t, l = h(t), s = !1, g());
		},
		reset: () => {
			u += 1, d?.abort(), d = null, r = [], i = null, a = null, s = !1, c = null, l = "", g();
		},
		dispose: () => {
			f || (f = !0, u += 1, d?.abort(), d = null, n.replaceChildren());
		}
	};
	return g(), v;
}
//#endregion
//#region frontend/canvas/src/controllers/generation-controller.ts
var Mf = "canvas:generation-pending:v1";
function Nf(e) {
	if (e === null) return /* @__PURE__ */ new Map();
	try {
		let t = e.getItem(Mf);
		if (t === null) return /* @__PURE__ */ new Map();
		let n = JSON.parse(t);
		return Array.isArray(n) ? new Map(n.flatMap((e) => typeof e != "object" || !e || Array.isArray(e) || typeof e.projectId != "string" || typeof e.fingerprint != "string" || typeof e.idempotencyKey != "string" || typeof e.createdAt != "string" ? [] : [[e.projectId, {
			projectId: e.projectId,
			fingerprint: e.fingerprint,
			idempotencyKey: e.idempotencyKey,
			createdAt: e.createdAt
		}]])) : /* @__PURE__ */ new Map();
	} catch {
		return /* @__PURE__ */ new Map();
	}
}
function Pf(e, t) {
	if (e !== null) try {
		t.size === 0 ? e.removeItem(Mf) : e.setItem(Mf, JSON.stringify([...t.values()]));
	} catch {}
}
function Ff(e) {
	if (e === null || typeof e == "boolean" || typeof e == "string" || typeof e == "number") return JSON.stringify(e);
	if (Array.isArray(e)) return `[${e.map(Ff).join(",")}]`;
	if (typeof e != "object") throw Error("generation request must be JSON");
	let t = e;
	return `{${Object.keys(t).sort().map((e) => `${JSON.stringify(e)}:${Ff(t[e])}`).join(",")}}`;
}
function If() {
	return typeof crypto < "u" && typeof crypto.randomUUID == "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function Lf(e) {
	return {
		ok: !1,
		kind: "save_failed",
		message: e.kind === "conflict" ? "项目版本冲突，请刷新后重试" : e.message
	};
}
function Rf({ store: e, autosave: t, api: n, catalog: r = () => [], build: i = ff, randomId: a = If, now: o = () => /* @__PURE__ */ new Date(), storage: s = typeof sessionStorage > "u" ? null : sessionStorage, pendingTtlMs: c = 1800 * 1e3 }) {
	let l = Nf(s), u = null;
	return {
		submit: () => {
			if (u !== null) return u;
			let d = (async () => {
				let u = await t.flush();
				if (!u.ok) return Lf(u);
				let d = e.getState(), f = i(d.project, r(), d.runtime.revision);
				if (!f.ok) return {
					ok: !1,
					kind: "validation",
					message: f.reasons[0]?.message ?? "生成配置无效"
				};
				let p = Ff(f.request), m = l.get(d.runtime.projectId), h = m === void 0 ? NaN : Date.parse(m.createdAt);
				m !== void 0 && m.fingerprint === p && Number.isFinite(h) && o().getTime() - h <= c || (l.set(d.runtime.projectId, {
					projectId: d.runtime.projectId,
					fingerprint: p,
					idempotencyKey: `canvas:${a()}`,
					createdAt: o().toISOString()
				}), Pf(s, l));
				let g = l.get(d.runtime.projectId);
				if (g === void 0) throw Error("generation pending submission is unavailable");
				let _ = await n.create(d.runtime.projectId, f.request, g.idempotencyKey);
				return _.ok ? (l.delete(d.runtime.projectId), Pf(s, l), {
					ok: !0,
					generationId: _.value.id
				}) : {
					ok: !1,
					kind: "request_failed",
					message: _.message
				};
			})().finally(() => {
				u = null;
			});
			return u = d, d;
		},
		getPending: () => {
			let t = e.getState().runtime.projectId, n = l.get(t);
			return n === void 0 ? null : { ...n };
		},
		retirePending: () => {
			l.delete(e.getState().runtime.projectId), Pf(s, l);
		}
	};
}
//#endregion
//#region frontend/canvas/src/domain/workflow.ts
function zf(e) {
	return e.hasProject ? e.hasSource ? e.processing ? "processing" : e.generating ? "generating" : e.exportRequested && e.hasSelectedResult ? "export" : e.hasResults ? "results" : "configure" : "source" : "project";
}
function Bf(e) {
	switch (e) {
		case "project":
		case "source":
		case "processing": return "source";
		case "configure": return "generate";
		case "generating":
		case "results": return "results";
		case "export": return "export";
	}
}
function Vf(e, t) {
	switch (e) {
		case "source": return t.hasProject;
		case "generate": return t.hasProject && t.hasSource && !t.processing;
		case "results": return t.hasProject && (t.generating || t.hasResults);
		case "export": return t.hasProject && t.hasSelectedResult;
	}
}
//#endregion
//#region frontend/canvas/src/components/workspace.ts
function Hf(e) {
	switch (e.type) {
		case "output/setQuantity":
		case "sku/setOutputQuantity":
		case "output/configure":
		case "board/selectResult":
		case "viewport/set":
		case "node/update":
		case "node/move":
		case "text/update":
		case "composition/update":
		case "asset/useRectangularSource": return !0;
		default: return !1;
	}
}
var Uf = {
	queued: "排队中",
	running: "生成中",
	retrying: "正在重试",
	succeeded: "已完成",
	failed: "失败",
	partially_failed: "部分完成",
	cancel_requested: "正在取消",
	cancelled: "已取消",
	unknown: "状态待确认"
};
function Wf(e) {
	return Uf[e] ?? "处理中";
}
function Gf(e) {
	switch (e) {
		case "queued":
		case "cancel_requested": return 0;
		case "running": return 1;
		case "cancelled":
		case "failed":
		case "interrupted":
		case "succeeded": return 2;
	}
}
function Kf(e, t) {
	let n = e.attemptCount ?? -1, r = t.attemptCount ?? -1;
	return n === r ? Gf(e.status) >= Gf(t.status) ? e : t : n > r ? e : t;
}
function qf({ root: e, controller: n, store: r, adapter: o, assetsApi: s, compositionsApi: c, skusApi: l, providersApi: u, generationsApi: d, exportsApi: f, subscribeEvents: p }) {
	let m = !1, h = 0, g = !1, _ = !1, v = null, y = document.createElement("main");
	y.className = "canvas-workspace", y.dataset.testid = "canvas-workspace", y.dataset.projectsOpen = "false", y.dataset.inspectorOpen = "false";
	let b = "source", x = !1, S = null, C = null, w = document.createElement("button");
	w.type = "button", w.className = "canvas-drawer-backdrop", w.setAttribute("aria-label", "关闭侧栏");
	let T = (e) => {
		y.dataset.projectsOpen = String(e), e && queueMicrotask(() => ne.element.querySelector("button, input, summary")?.focus()), !e && C?.isConnected && C.focus();
	}, E = (e) => {
		y.dataset.inspectorOpen = String(e), e && queueMicrotask(() => j.querySelector("button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled])")?.focus()), !e && C?.isConnected && C.focus();
	}, D = () => {
		T(!1), E(!1);
	};
	w.addEventListener("click", D);
	let te = (e) => {
		if (e.key === "Escape") {
			D();
			return;
		}
		if (e.key !== "Tab") return;
		let t = y.dataset.inspectorOpen === "true" ? j : y.dataset.projectsOpen === "true" ? ne.element : null;
		if (t === null) return;
		let n = Array.from(t.querySelectorAll("button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [href], [tabindex]:not([tabindex=\"-1\"])")).filter((e) => !e.hidden && e.getAttribute("aria-hidden") !== "true");
		if (n.length === 0) return;
		let r = n[0], i = n[n.length - 1];
		e.shiftKey && document.activeElement === r ? (e.preventDefault(), i.focus()) : !e.shiftKey && document.activeElement === i && (e.preventDefault(), r.focus());
	};
	document.addEventListener("keydown", te);
	let ne = Nd(n), re = document.createElement("section");
	re.className = "canvas-workspace-center", re.setAttribute("aria-label", "产品视觉画布工作区");
	let k = document.createElement("div");
	k.className = "canvas-stage", k.dataset.testid = "canvas-stage", k.setAttribute("role", "region"), k.setAttribute("aria-label", "无限画布视口");
	let ie = document.createElement("canvas");
	ie.width = 1600, ie.height = 1e3, ie.dataset.testid = "canvas-surface", ie.dataset.canvasSurface = "product-canvas";
	let A = document.createElement("section");
	A.className = "canvas-stage-empty", A.dataset.testid = "canvas-stage-empty";
	let ae = document.createElement("span");
	ae.className = "canvas-stage-empty-icon", ae.textContent = "+", ae.setAttribute("aria-hidden", "true");
	let oe = document.createElement("h2"), se = document.createElement("p"), ce = document.createElement("button");
	ce.type = "button", ce.className = "canvas-primary-action", ce.dataset.testid = "canvas-stage-upload", ce.textContent = "上传主商品图片", ce.addEventListener("click", () => v?.openPicker());
	let le = document.createElement("ol");
	for (let e of [
		"上传并自动准备产品素材",
		"选择主图、SKU 图或详情图",
		"生成、挑选版本并导出"
	]) le.append(Object.assign(document.createElement("li"), { textContent: e }));
	A.append(ae, oe, se, ce, le), A.addEventListener("dragover", (e) => {
		g && e.preventDefault();
	}), A.addEventListener("drop", (e) => {
		if (!g) return;
		e.preventDefault();
		let t = e.dataTransfer?.files[0];
		t !== void 0 && v?.uploadFile(t);
	}), k.append(ie, A);
	let j = document.createElement("aside");
	j.className = "canvas-properties", j.dataset.testid = "canvas-properties", j.setAttribute("aria-label", "属性设置");
	let ue = document.createElement("header");
	ue.className = "canvas-properties-header";
	let M = document.createElement("div");
	M.innerHTML = "<strong>创作流程</strong><span>按步骤完成产品套图</span>";
	let N = document.createElement("button");
	N.type = "button", N.className = "canvas-properties-close", N.textContent = "关闭", N.setAttribute("aria-label", "关闭画布设置"), N.addEventListener("click", () => E(!1)), ue.append(M, N);
	let de = document.createElement("div");
	de.className = "canvas-properties-tabs", de.setAttribute("role", "tablist"), de.setAttribute("aria-label", "画布创作步骤");
	let P = /* @__PURE__ */ new Map(), F = /* @__PURE__ */ new Map();
	for (let [e, t] of [
		["source", "素材"],
		["generate", "生成"],
		["results", "结果"],
		["export", "导出"]
	]) {
		let n = document.createElement("button");
		n.type = "button", n.role = "tab", n.textContent = t, n.dataset.inspectorTab = e, n.id = `canvas-tab-${e}`, n.setAttribute("aria-controls", `canvas-panel-${e}`), n.addEventListener("click", () => {
			let t = mt();
			Vf(e, t) && (b = e, x = e === "export", S = zf(mt()), ht());
		});
		let r = document.createElement("div");
		r.className = "canvas-properties-panel", r.dataset.inspectorPanel = e, r.id = `canvas-panel-${e}`, r.role = "tabpanel", r.setAttribute("aria-labelledby", n.id), de.append(n), F.set(e, n), P.set(e, r);
	}
	let fe = document.createElement("div");
	fe.className = "canvas-properties-controls";
	let I = () => r.getState().project, pe = (e) => {
		let t = I();
		o.project(e, t), e.semanticState.mode !== t.semanticState.mode && o.setMode(t.semanticState.mode);
	}, me = (e) => {
		if (!g) return;
		let t = I(), n = _;
		_ ||= Hf(e);
		let i;
		try {
			i = r.dispatch(e), i.confirmation !== void 0 && window.confirm("此操作会解除已有结果关联，是否继续？") && (i = r.dispatch({
				...e,
				acceptedDiffId: i.confirmation.token
			}));
		} finally {
			_ = n;
		}
		i.applied && pe(t);
	}, he = () => {
		if (!g) return;
		let e = I();
		r.undo() && pe(e);
	}, ge = () => {
		if (!g) return;
		let e = I();
		r.redo() && pe(e);
	}, _e = null, ve = Yd(r, me, he, ge, f === void 0 ? void 0 : () => {
		b = "export", x = !0, ht(), C = document.activeElement instanceof HTMLElement ? document.activeElement : null, E(!0);
	}, {
		getProjectName: () => n.getState().projects.find((e) => e.id === n.getState().activeProjectId)?.name ?? null,
		canExport: () => I().semanticState.outputBoards.some((e) => e.selectedResultAssetId !== null),
		onToggleProjects: () => {
			C = document.activeElement instanceof HTMLElement ? document.activeElement : null, T(y.dataset.projectsOpen !== "true");
		},
		onToggleInspector: () => {
			C = document.activeElement instanceof HTMLElement ? document.activeElement : null, E(y.dataset.inspectorOpen !== "true");
		}
	}), ye = null, be = document.createElement("label");
	be.className = "canvas-composition-group-field", be.textContent = "活动构图组";
	let xe = document.createElement("select");
	xe.dataset.testid = "canvas-composition-group-select";
	let Se = document.createElement("button");
	Se.type = "button", Se.dataset.testid = "canvas-composition-group-create", Se.textContent = "新建构图组", xe.setAttribute("aria-label", "选择构图组"), be.append(xe, Se);
	let Ce = Ud({ onUpdate: (e, t) => {
		me({
			type: "composition/update",
			groupId: e,
			layout: t
		});
	} }), we = null, Te = Sf(), Ee = Gd({
		onSelect: (e) => {
			we = e, wt();
		},
		onUpdate: (e, t) => {
			me({
				type: "text/update",
				layerId: e,
				patch: t
			});
		}
	}), De = Jd(() => {
		n.retrySave();
	}, () => {
		n.retryRemoteSync();
	}), L = null, R = null, Oe = [], ke = [], Ae = /* @__PURE__ */ new Map(), je = [], Me = null, Ne = n.getState(), Pe = null, Fe = null, Ie = null, Le = !1, Re = 0, ze = null, z = null, Be = null, Ve = null, He = [], Ue = null, We = Ef(s === void 0 ? void 0 : (e) => s.previewUrl(e)), Ge = document.createElement("label");
	Ge.className = "canvas-result-board-picker", Ge.textContent = "审阅画板";
	let Ke = document.createElement("select");
	Ke.setAttribute("aria-label", "选择要审阅的结果画板"), Ke.dataset.testid = "canvas-result-board-picker", Ge.append(Ke), Ke.addEventListener("change", () => {
		z = Ke.value || null, _t();
	});
	let qe = [], Je = xf(), Ye = a(), Xe = d === void 0 ? null : Rf({
		store: r,
		autosave: { flush: () => n.flushSave() },
		api: d,
		catalog: () => qe
	}), Ze = async () => {
		if (Xe === null || d === void 0) {
			Je.update("生成服务尚未配置", "error");
			return;
		}
		let e = async () => {
			Ue = "submitting", b = "results", ht(), Je.update("正在保存并提交生成…", "working");
			let e = await Xe.submit();
			Ue = e.ok ? "queued" : null, Je.update(e.ok ? `已创建生成任务 ${e.generationId}` : t(e.message, "生成任务提交失败，请重试"), e.ok ? "success" : "error"), ht();
		}, n = await d.accessStatus();
		if (!n.ok) {
			Je.update(t(n.message, "生成访问状态检查失败，请重试"), "error");
			return;
		}
		if (n.value.configured && n.value.locked) {
			Ye.open(async (n) => {
				let r = await d.unlock(n);
				return r.ok ? (e(), null) : t(r.message, "解锁失败，请检查访问令牌");
			});
			return;
		}
		await e();
	}, Qe = bf({
		getProject: I,
		getRevision: () => r.getState().runtime.revision,
		getModels: () => qe,
		getSkus: () => je,
		getReferenceAssets: () => Oe.filter((e) => e.assetType === "working" || e.assetType === "cutout").map((e) => ({
			id: e.id,
			label: e.originalFilename || e.id
		})),
		isEditable: () => g,
		dispatch: me,
		onGenerate: () => {
			Ze();
		}
	});
	f !== void 0 && (_e = jf({
		api: f,
		getProject: I,
		getProjectId: () => L,
		getRevision: () => r.getState().runtime.revision,
		getVersions: () => He,
		isEditable: () => g,
		flushSave: () => n.flushSave(),
		onUnauthorized: (e) => {
			if (d === void 0) {
				Je.update("付费访问服务尚未配置", "error");
				return;
			}
			Ye.open(async (n) => {
				let r = await d.unlock(n);
				return r.ok ? (e(), null) : t(r.message, "解锁失败，请检查访问令牌");
			});
		},
		onOperation: (e) => {
			ke = [...ke.filter((t) => t.id !== e.id), e], Ae.set(e.id, e);
		}
	}));
	let $e = document.createElement("section");
	$e.className = "canvas-compose-controls", $e.dataset.testid = "canvas-compose-controls";
	let et = document.createElement("select");
	et.dataset.testid = "canvas-compose-board";
	let tt = document.createElement("select");
	tt.dataset.testid = "canvas-compose-background";
	let nt = document.createElement("button");
	nt.type = "button", nt.dataset.testid = "canvas-compose-submit", nt.textContent = "合成产品图";
	let rt = document.createElement("p");
	rt.dataset.testid = "canvas-compose-feedback";
	let it = (e) => e.status === "succeeded" ? "合成完成" : e.status === "failed" ? "合成失败，可从任务状态重试" : e.status === "queued" ? "合成任务已进入队列" : "合成处理中", at = () => {
		let e = I().semanticState.outputBoards, t = Oe.filter((e) => e.assetType === "generated_background" || e.assetType === "working");
		e.some((e) => e.id === z) || (z = e[0]?.id ?? null), t.some((e) => e.id === Be) || (Be = t[0]?.id ?? null), et.replaceChildren(...e.map((e) => Object.assign(document.createElement("option"), {
			value: e.id,
			textContent: `${e.outputType} · ${e.id}`
		}))), et.value = z ?? "", tt.replaceChildren(...t.map((e) => Object.assign(document.createElement("option"), {
			value: e.id,
			textContent: e.originalFilename || e.id
		}))), tt.value = Be ?? "";
		let n = !g || Le || c === void 0 || z === null || Be === null;
		et.disabled = n, tt.disabled = n, nt.disabled = n;
		let r = [
			Object.assign(document.createElement("h3"), { textContent: "权威合成" }),
			et,
			tt,
			nt,
			rt
		];
		if (Ve?.status === "succeeded" && Ve.outputAssetId != null && s !== void 0) {
			let e = document.createElement("img");
			e.className = "canvas-compose-preview", e.dataset.testid = "canvas-compose-preview", e.alt = "合成结果预览", e.src = s.previewUrl(Ve.outputAssetId), r.push(e);
		}
		$e.replaceChildren(...r);
	};
	et.addEventListener("change", () => {
		z = et.value || null;
	}), tt.addEventListener("change", () => {
		Be = tt.value || null;
	}), nt.addEventListener("click", () => {
		if (Le || c === void 0 || L === null || z === null || Be === null) return;
		let e = L, i = ++Re, a = z, o = Be;
		Le = !0, rt.textContent = "正在保存并提交合成…", at(), (async () => {
			let s = await n.flushSave();
			if (!s.ok || m || i !== Re || L !== e) {
				rt.textContent = s.ok ? "项目已切换，未提交合成" : "请先解决保存问题", Le = !1, at();
				return;
			}
			let l = new AbortController();
			Ie?.abort(), Ie = l, ze = null, Ve = null;
			let u = typeof crypto.randomUUID == "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`, d = await c.enqueueCompose({
				projectId: e,
				revision: r.getState().runtime.revision,
				boardId: a,
				backgroundAssetId: o,
				clientRequestId: `compose:${u}`,
				signal: l.signal
			});
			if (m || i !== Re || L !== e || Ie !== l) return;
			if (Ie = null, Le = !1, !d.ok) {
				rt.textContent = d.kind === "conflict" ? `项目版本已更新到 ${d.currentRevision}，请刷新后重试` : t(d.message, "合成请求失败，请重试"), at();
				return;
			}
			ze = d.value.id;
			let f = Ae.get(d.value.id);
			Ve = f === void 0 ? d.value : Kf(d.value, f), rt.textContent = it(Ve), at();
		})().catch(() => {
			!m && i === Re && L === e && (Ie = null, Le = !1, rt.textContent = "合成请求失败，请重试", at());
		});
	});
	let ot = () => {
		De.update(Ne.save, Ne.remoteSync, R?.asset.cutoutStatus ?? null);
	}, st = () => {
		if (Fe === null || L === null) {
			Fe?.update(null);
			return;
		}
		let e = I().layoutState.productLayers.find((e) => e.skuId === null && e.locked);
		Fe.update({
			projectId: L,
			revision: r.getState().runtime.revision,
			skus: je,
			mainProductAssetId: e?.renderAssetId ?? null,
			referenceAssets: Oe.filter((e) => e.assetType === "working").map((e) => ({
				id: e.id,
				label: e.originalFilename || e.id
			})),
			disabled: !g
		});
	}, ct = (e) => {
		let t = I();
		if (JSON.stringify(t) !== JSON.stringify(e.project)) {
			let n = r.getState().runtime;
			r.replaceProject(e.project, {
				projectId: n.projectId,
				revision: n.revision
			}), o.project(t, e.project), t.semanticState.mode !== e.project.semanticState.mode && o.setMode(e.project.semanticState.mode);
		}
		R = {
			project: I(),
			asset: structuredClone(e.asset)
		}, Pe?.update(R.asset), st(), ot(), ht();
	}, lt = (e) => {
		if (R === null || I().layoutState.productLayers.find((e) => e.skuId === null && e.locked)?.sourceAssetId !== R.asset.workingAssetId) return;
		let t = {
			project: I(),
			asset: R.asset
		}, n = kd(t, e);
		n !== t && ct(n);
	};
	s !== void 0 && (v = Rd({
		api: s,
		onUploaded: (e) => {
			if (L === null || e.source.projectId !== L) return;
			let t = /* @__PURE__ */ new Set([
				e.source.id,
				e.working.id,
				e.preview.id
			]);
			if (Oe = [
				...Oe.filter((e) => !t.has(e.id)),
				e.source,
				e.working,
				e.preview
			], e.operation !== null && (ke.some((t) => t.id === e.operation?.id) || (ke = [...ke, e.operation])), ct(Dd(I(), e)), e.operation !== null) {
				let t = ke.find((t) => t.id === e.operation?.id) ?? e.operation, n = Ae.get(e.operation.id);
				lt(n === void 0 ? t : Kf(t, n));
			}
		}
	}), Pe = Id({
		api: s,
		onOperation: (e) => {
			ke = [...ke.filter((t) => t.id !== e.id), e], Ae.set(e.id, e), lt(e);
		},
		onFallback: () => {
			R !== null && (me({
				type: "asset/useRectangularSource",
				workingAssetId: R.asset.workingAssetId
			}), R = {
				project: I(),
				asset: {
					...R.asset,
					renderAssetId: R.asset.workingAssetId,
					allowOpaqueFallback: !0
				}
			}, Pe?.update(R.asset), ot(), ht());
		}
	})), l !== void 0 && (Fe = zd({
		api: l,
		onSnapshot: (e) => {
			e.project.id === L && (je = e.skus, n.adoptMutationSnapshot(e), st());
		}
	}));
	let ut = P.get("source"), dt = P.get("generate"), ft = P.get("results"), pt = P.get("export");
	dt.append(fe, be, Ce.element, Ee.element, $e), ft.append(Je.element, Ge, We.element), _e !== null && pt.append(_e.element), v !== null && Pe !== null && ut.append(v.element, Pe.element), Fe !== null && ut.append(Fe.element), j.append(ue, de, ...P.values(), Ye.element), re.append(ve.element, k, De.element), y.append(ne.element, re, j, w), e.replaceChildren(y);
	function mt() {
		let e = I().semanticState.outputBoards.some((e) => e.selectedResultAssetId !== null && He.some((t) => t.boardId === e.id && t.composedAssetId === e.selectedResultAssetId));
		return {
			hasProject: L !== null,
			hasSource: R !== null,
			processing: R?.asset.cutoutStatus === "queued" || R?.asset.cutoutStatus === "running",
			generating: Ue !== null && ![
				"succeeded",
				"failed",
				"partially_failed",
				"cancelled",
				"unknown"
			].includes(Ue),
			hasResults: He.length > 0,
			hasSelectedResult: e,
			exportRequested: x
		};
	}
	function ht() {
		let e = mt(), t = R?.asset.cutoutStatus === "failed";
		e.hasSelectedResult || (x = !1);
		let n = zf({
			...e,
			exportRequested: x
		});
		y.dataset.workflowStage = n, n !== S && (b = t ? "source" : Bf(n), S = n), t && (b = "source"), Vf(b, e) || (b = Bf(n));
		let [r, i] = t ? ["产品素材处理失败", "查看失败原因并重新抠图，或明确选择使用原图矩形继续。"] : {
			project: ["先创建一个产品项目", "每个项目会独立保存素材、提示词、结果和导出设置。"],
			source: ["上传主商品图片", "支持 JPG、PNG、WebP。上传后会自动检测并准备可用于生成的产品素材。"],
			processing: ["正在准备产品素材", "系统正在检测背景并处理产品图，完成后会自动进入生成设置。"],
			configure: ["设置要生成的产品套图", "在右侧选择主图、SKU 图或详情图，并分别设置模型与提示词。"],
			generating: ["正在生成产品套图", "任务在后台运行，可以留在当前页面查看进度。"],
			results: ["审阅生成结果", "从每个画板的成功版本中选择最终结果，再进入导出。"],
			export: ["导出已选产品图", "选择画板、导出方式与格式后生成下载文件。"]
		}[n];
		M.querySelector("strong").textContent = r, M.querySelector("span").textContent = i, oe.textContent = r, se.textContent = i, A.hidden = e.hasSource && !e.processing, A.dataset.state = n, ce.disabled = !e.hasProject || e.processing, ce.hidden = e.processing, le.hidden = e.processing;
		for (let [t, n] of F) {
			let r = Vf(t, e);
			n.hidden = t !== "source" && !r, n.disabled = !r, n.setAttribute("aria-selected", String(b === t)), n.tabIndex = b === t ? 0 : -1;
			let i = P.get(t);
			i.hidden = b !== t;
		}
		ve.update();
	}
	u !== void 0 && u.loadCatalog().then((e) => {
		if (!m) {
			if (!e.ok) {
				Je.update(t(e.message, "图像模型目录加载失败，请重试"), "error");
				return;
			}
			qe = e.value, Qe.update(), gt();
		}
	}).catch(() => {
		m || Je.update("模型目录加载失败", "error");
	});
	let gt = () => {
		let e = I(), t = document.createElement("h2");
		t.textContent = "属性设置";
		let n = document.createElement("p");
		if (n.textContent = e.semanticState.mode === "complete-set" ? "选择套图输出并设置数量与提示词。" : "高级模式保留同一画布与项目状态。", fe.replaceChildren(t, n), e.semanticState.mode === "advanced") {
			let t = Tf({
				disabled: !g,
				nextId: (t) => {
					let n;
					do
						h += 1, n = `advanced:${t}:${h}`;
					while (e.semanticState.nodes.some((e) => e.id === n));
					return n;
				},
				onAdd: (e) => {
					me({
						type: "node/add",
						node: e
					}), me({
						type: "node/move",
						nodeId: e.id,
						position: {
							x: 120 + h * 24,
							y: 120
						}
					});
				}
			});
			Te.update(e.semanticState.nodes, qe, !g, (e, t) => {
				me({
					type: "node/update",
					nodeId: e,
					patch: t
				});
			}, (t, n) => {
				let r = e.semanticState.nodes.find((e) => e.id === t), i = e.semanticState.nodes.find((e) => e.id === n);
				if (r === void 0 || i === void 0) return;
				let a = O(r.kind, i.kind)[0];
				if (a === void 0) return;
				let o = 1, s = `advanced:edge:${t}:${n}:${a}:${o}`;
				for (; e.semanticState.edges.some((e) => e.id === s);) o += 1, s = `advanced:edge:${t}:${n}:${a}:${o}`;
				me({
					type: "edge/connect",
					edge: ee(s, a, t, n)
				});
			});
			let n = pf(e, qe, r.getState().runtime.revision), i = document.createElement("button");
			if (i.type = "button", i.dataset.testid = "canvas-generate-advanced", i.textContent = n.ok ? "生成高级画布" : n.reasons.map((e) => e.message).join("；"), i.disabled = !g || !n.ok, i.addEventListener("click", () => {
				Ze();
			}), fe.append(t, Te.element, i), e.semanticState.outputBoards.length === 0) {
				let e = document.createElement("button");
				e.type = "button", e.textContent = "返回套图模式选择输出", e.disabled = !g, e.addEventListener("click", () => me({
					type: "mode/set",
					mode: "complete-set"
				})), fe.append(Object.assign(document.createElement("p"), { textContent: "高级图谱需要至少一个输出画板。请先在套图模式选择主图、SKU 图或详情图；已有节点不会丢失。" }), e);
			}
			return;
		}
		Qe.update(), fe.append(Qe.element);
	}, _t = () => {
		let e = I().semanticState.outputBoards, t = (t) => `${t.outputType === "main" ? "主图" : t.outputType === "sku" ? "SKU 图" : "详情图"} ${e.filter((e) => e.outputType === t.outputType && e.sortOrder <= t.sortOrder).length}`;
		e.some((e) => e.id === z) || (z = e[0]?.id ?? null), Ke.replaceChildren(...e.map((e) => Object.assign(document.createElement("option"), {
			value: e.id,
			textContent: t(e)
		}))), Ke.value = z ?? "", Ge.hidden = e.length <= 1;
		let n = e.find((e) => e.id === z) ?? e[0] ?? null;
		We.update(n, He, !g, (e) => {
			if (n !== null) {
				me({
					type: "board/selectResult",
					boardId: n.id,
					assetId: e
				});
				let t = e === null ? null : He.find((t) => t.boardId === n.id && t.composedAssetId === e) ?? null;
				o.setResultBackgroundPreview?.(t?.backgroundPreviewAssetId ?? null);
			}
		});
		let r = n?.selectedResultAssetId === null || n === null ? null : He.find((e) => e.boardId === n.id && e.composedAssetId === n.selectedResultAssetId) ?? null;
		o.setResultBackgroundPreview?.(r?.backgroundPreviewAssetId ?? null), _e?.update();
	}, vt = async (e) => {
		if (d === void 0) return;
		let t = await i(d, e);
		if (m || L !== e || !t.ok) return;
		He = t.value;
		let n = /* @__PURE__ */ new Map();
		for (let e of He) {
			let t = n.get(e.boardId) ?? [];
			t.push(e.composedAssetId), n.set(e.boardId, t);
		}
		for (let e of I().semanticState.outputBoards) r.dispatch({
			type: "runtime/setAllowedResultAssets",
			boardId: e.id,
			assetIds: n.get(e.id) ?? []
		});
		_t(), ht();
	}, yt = async (e) => {
		if (s === void 0) return;
		Me?.abort();
		let t = new AbortController();
		Me = t;
		let n, r;
		try {
			[n, r] = await Promise.all([s.listAssets(e, t.signal), s.listOperations(e, t.signal)]);
		} catch {
			Me === t && (Me = null);
			return;
		}
		if (m || t.signal.aborted || Me !== t || L !== e || (Me = null, !n.ok || !r.ok)) return;
		Oe = n.value, ke = r.value;
		let i = ke.find((e) => e.operationType === "export");
		i !== void 0 && _e?.applyOperation(i), at(), _t();
		let a = Ad(I(), Oe, ke);
		if (a === null) {
			R = null, Pe?.update(null), st(), ot(), ht();
			return;
		}
		ct(a);
		let o = Ae.get(a.asset.operationId ?? ""), c = ke.find((e) => e.id === a.asset.operationId);
		o !== void 0 && lt(c === void 0 ? o : Kf(c, o));
	}, bt = (e) => {
		Ue = e.status;
		let n = e.safeErrorSummary ?? e.safeStorageBlockReason, r = n === null ? null : t(n, "生成失败，请检查模型配置后重试"), i = /* @__PURE__ */ new Set([
			"failed",
			"partially_failed",
			"cancelled",
			"unknown"
		]);
		Je.update(r ?? `任务 ${Wf(e.status)}（成功 ${e.succeededItems}/${e.totalItems}）`, r === null ? e.status === "succeeded" ? "success" : i.has(e.status) ? "error" : "working" : "error"), e.succeededItems > 0 && L !== null && vt(L), ht();
	}, xt = p?.((e) => {
		if (!(m || L === null)) {
			if (e.type === "snapshot") {
				if (e.snapshot.project.id !== L) return;
				je = e.snapshot.skus, ke = e.operations, Ae.clear(), He = [];
				let t = ke.find((e) => e.operationType === "export");
				t !== void 0 && _e?.applyOperation(t);
				let n = e.generations?.[0];
				n !== void 0 && bt(n), st(), yt(L);
				return;
			}
			if (e.projectId === L) {
				if ("generation" in e) {
					bt(e.generation);
					return;
				}
				if (e.type === "asset.uploaded" || e.type === "asset.deleted") {
					yt(L);
					return;
				}
				if ("operation" in e) {
					if (Ae.set(e.operation.id, e.operation), e.operation.operationType === "export") {
						_e?.applyOperation(e.operation);
						return;
					}
					if (e.operation.operationType === "compose") {
						if (e.operation.id !== ze) return;
						Ve = Ve === null ? e.operation : Kf(Ve, e.operation), rt.textContent = it(Ve), at();
						return;
					}
					lt(e.operation);
				}
			}
		}
	}) ?? (() => {});
	o.mount(ie, me);
	let St = I();
	o.project(null, St), o.setMode(St.semanticState.mode);
	let Ct = () => {
		let e = I().semanticState.compositionGroups, t = e.find((e) => e.id === ye) ?? e[0];
		ye = t?.id ?? null, xe.replaceChildren(...e.length === 0 ? [Object.assign(document.createElement("option"), {
			value: "",
			textContent: "暂无构图组"
		})] : e.map((e, t) => Object.assign(document.createElement("option"), {
			value: e.id,
			textContent: `构图组 ${t + 1} · ${e.id}`
		}))), xe.value = ye ?? "", xe.disabled = !g || e.length === 0, Se.disabled = !g || !I().layoutState.productLayers.some((e) => e.skuId === null && e.locked && e.compositionGroupId === null), Ce.update(t === void 0 ? null : {
			groupId: t.id,
			layout: t.layout,
			disabled: !g
		});
	};
	function wt() {
		let e = I().layoutState.textSnapshots;
		e.some((e) => e.id === we) || (we = e[0]?.id ?? null), Ee.update({
			layers: e,
			selectedLayerId: we,
			disabled: !g
		});
	}
	xe.addEventListener("change", () => {
		if (!g) return;
		let e = xe.value;
		I().semanticState.compositionGroups.some((t) => t.id === e) && (ye = e, Ct(), wt(), at(), _e?.update());
	}), Se.addEventListener("click", () => {
		if (!g) return;
		let e = I().semanticState.compositionGroups.length, t = I().layoutState.productLayers.find((e) => e.skuId === null && e.locked);
		if (t === void 0) return;
		me({
			type: "composition/create",
			skuProducts: je.map((e) => {
				let n = e.referenceAssetId === null, r = e.referenceAssetId ?? t.sourceAssetId;
				return {
					skuId: e.id,
					sourceAssetId: r,
					renderAssetId: n ? t.renderAssetId : r,
					allowOpaqueFallback: n ? t.allowOpaqueFallback : !1
				};
			})
		});
		let n = I().semanticState.compositionGroups[e];
		n !== void 0 && (ye = n.id, Ct());
	});
	let Tt = () => {
		ve.update(), _ || gt(), Ct(), wt(), at(), ht();
	};
	Tt();
	let Et = r.subscribe(Tt), Dt = (e) => {
		let t = L !== e.activeProjectId;
		Ne = e, g = e.activeProjectId !== null, L = e.activeProjectId, t && (Ue = null, x = !1, b = "source", S = null, Re += 1, Le = !1, ze = null, ye = null, we = null, z = null, Be = null, Ve = null, _e?.reset()), ne.update(e), ve.setEditable(g), y.dataset.editable = String(g), k.inert = !g, j.inert = !g, k.setAttribute("aria-disabled", String(!g)), j.setAttribute("aria-disabled", String(!g)), Ct(), y.dataset.activeProjectId = e.activeProjectId ?? "", v?.setDisabled(!g), v?.setProject(L), Pe?.setDisabled(!g);
		let r = n.getActiveSnapshot?.call(n) ?? null;
		r !== null && r.project.id === L && (je = r.skus);
		let i = I().layoutState.productLayers.find((e) => e.skuId === null && e.locked), a = R !== null && i?.sourceAssetId !== R.asset.workingAssetId;
		(t || a) && (Me?.abort(), Me = null, Ie?.abort(), Ie = null, R = null, Oe = [], ke = [], Ae.clear(), Pe?.update(null), L !== null && (yt(L), vt(L))), st(), ot(), wt(), at(), _t(), ht();
	};
	Dt(n.getState());
	let Ot = n.subscribe(Dt);
	return { dispose: () => {
		m || (m = !0, Me?.abort(), Me = null, Ie?.abort(), Ie = null, Et(), Ot(), xt(), v?.dispose(), Pe?.dispose(), Fe?.dispose(), _e?.dispose(), document.removeEventListener("keydown", te), Ce.dispose(), Ee.dispose(), n.dispose(), o.dispose(), e.replaceChildren());
	} };
}
//#endregion
//#region frontend/canvas/src/controllers/autosave-controller.ts
function Jf(e) {
	return JSON.stringify(Re(e.getState().project));
}
function Yf({ store: e, save: t, debounceMs: n = 1e3, documentTarget: r = typeof document > "u" ? void 0 : document, windowTarget: i = typeof window > "u" ? void 0 : window }) {
	let a = 0, o = 0, s = Jf(e), c = {
		status: "saved",
		dirty: !1,
		message: null,
		currentRevision: null
	}, l = null, u = null, d = !1, f = !1, p = /* @__PURE__ */ new Set(), m = () => f || o < a, h = (e) => {
		c = e;
		for (let e of [...p]) e({ ...c });
	}, g = () => {
		l !== null && (clearTimeout(l), l = null);
	}, _ = () => {
		g(), l = setTimeout(() => {
			l = null, b();
		}, n);
	}, v = e.subscribe(() => {
		let t = Jf(e);
		if (t !== s) {
			if (s = t, a += 1, f) {
				h({
					...c,
					dirty: !0
				});
				return;
			}
			h({
				status: "dirty",
				dirty: !0,
				message: null,
				currentRevision: null
			}), _();
		}
	}), y = async () => {
		for (g(); !d && o < a;) {
			let n = a, r = e.getState();
			h({
				status: "saving",
				dirty: !0,
				message: null,
				currentRevision: null
			});
			let i;
			try {
				i = await t({
					projectId: r.runtime.projectId,
					revision: r.runtime.revision,
					semanticState: r.project.semanticState,
					layoutState: r.project.layoutState
				});
			} catch (e) {
				i = {
					ok: !1,
					kind: "server",
					message: e instanceof Error ? e.message : "Save failed"
				};
			}
			if (d) return {
				ok: !1,
				kind: "server",
				message: "Autosave disposed"
			};
			if (!i.ok) return i.kind === "conflict" ? (f = !0, h({
				status: "conflict",
				dirty: !0,
				message: "Project changed elsewhere",
				currentRevision: i.currentRevision
			}), i) : (h({
				status: i.kind === "offline" ? "offline" : "failed",
				dirty: !0,
				message: i.message,
				currentRevision: null
			}), i);
			if (e.acknowledgeRevision(i.snapshot.revision), o = n, f) return {
				ok: !1,
				kind: "conflict",
				currentRevision: c.currentRevision ?? e.getState().runtime.revision
			};
		}
		return d || h({
			status: "saved",
			dirty: !1,
			message: null,
			currentRevision: null
		}), { ok: !0 };
	}, b = () => (g(), f ? Promise.resolve({
		ok: !1,
		kind: "conflict",
		currentRevision: c.currentRevision ?? e.getState().runtime.revision
	}) : u === null ? o >= a ? Promise.resolve({ ok: !0 }) : (u = y().finally(() => {
		u = null;
	}), u) : u), x = () => {
		r?.visibilityState === "hidden" && b();
	}, S = () => {
		b();
	}, C = (e) => {
		m() && (e.preventDefault(), e.returnValue = "");
	};
	return r?.addEventListener("visibilitychange", x), i?.addEventListener("pagehide", S), i?.addEventListener("beforeunload", C), {
		getState: () => ({ ...c }),
		subscribe: (e) => (p.add(e), () => {
			p.delete(e);
		}),
		flush: b,
		retry: b,
		whenIdle: async () => {
			await u;
		},
		hasUnconfirmedChanges: m,
		markConflict: (e) => {
			if (!Number.isInteger(e) || e < 1) throw Error("conflict revision must be a positive integer");
			g(), f = !0, h({
				status: "conflict",
				dirty: !0,
				message: "Project changed elsewhere",
				currentRevision: e
			});
		},
		dispose: () => {
			d || (d = !0, g(), v(), r?.removeEventListener("visibilitychange", x), i?.removeEventListener("pagehide", S), i?.removeEventListener("beforeunload", C), p.clear());
		}
	};
}
//#endregion
//#region frontend/canvas/src/domain/types.ts
function Xf(e = {
	projectId: "local-project",
	revision: 0
}) {
	return {
		projectId: e.projectId,
		revision: e.revision,
		selectedNodeId: null,
		selectedBoardId: null,
		taskSnapshots: {},
		resultHistory: [],
		allowedResultAssetIds: {},
		unlinkedBoards: [],
		uploadIds: [],
		paidGenerationRequestIds: [],
		pendingConfirmation: null
	};
}
function Zf() {
	return {
		schemaVersion: 1,
		semanticState: {
			nodes: [],
			edges: [],
			outputBoards: [],
			mode: "complete-set",
			advancedCustomized: !1,
			completeSet: {
				selectedOutputTypes: [],
				outputs: []
			},
			compositionGroups: []
		},
		layoutState: {
			nodePositions: {},
			objectTransforms: {},
			viewport: {
				x: 0,
				y: 0,
				zoom: 1
			},
			productLayers: [],
			textSnapshots: []
		}
	};
}
//#endregion
//#region frontend/canvas/src/controllers/project-controller.ts
function Qf(e) {
	return {
		schemaVersion: e.project.schemaVersion,
		semanticState: e.project.semanticState,
		layoutState: e.project.layoutState
	};
}
function $f(e) {
	let { semanticState: t, layoutState: n, ...r } = e.project;
	return r;
}
function ep({ api: e, store: t, adapter: n, createAutosave: r, openEvents: i }) {
	let a = null, o = null, s = null, c = 0, l = 0, u = null, d = null, f = null, p = !1, m = null, h = Promise.resolve(), g = 0, _ = null, v = 0, y = null, b = {
		pendingSwitch: null,
		projects: [],
		query: "",
		includeArchived: !1,
		activeProjectId: null,
		deleteCandidateId: null,
		loading: !1,
		error: null,
		save: {
			status: "saved",
			dirty: !1,
			message: null,
			currentRevision: null
		},
		remoteSync: {
			status: "idle",
			pendingRevision: null,
			message: null
		}
	}, x = /* @__PURE__ */ new Set(), S = (e) => {
		b = e;
		for (let e of [...x]) e({ ...b });
	}, C = (e) => {
		S({
			...b,
			...e
		});
	}, w = (e) => {
		let t = b.projects.filter((t) => t.id !== e.id), n = b.query.trim().toLocaleLowerCase(), r = e.status === "active" || b.includeArchived && e.status === "archived", i = n === "" || e.name.toLocaleLowerCase().includes(n);
		r && i && t.unshift(e), C({ projects: t });
	}, T = (e, n) => {
		g += 1;
		let r = h.then(async () => {
			let r = m?.project.id === e, i = r ? l : null, a = b.projects.find((t) => t.id === e);
			if (p || !r && a === void 0) return {
				ok: !1,
				kind: "server",
				message: "Project changed before write"
			};
			let o = r ? t.getState().runtime.revision : a?.revision;
			if (o === void 0) return {
				ok: !1,
				kind: "server",
				message: "Project revision is unavailable"
			};
			let s = await n(o);
			return s.ok && !p && (i !== null && i === l && m?.project.id === e && (t.acknowledgeRevision(s.snapshot.revision), m = s.snapshot), w($f(s.snapshot))), s;
		});
		return h = r.then(() => void 0, () => void 0), r.finally(() => {
			--g, g === 0 && _ !== null && te();
		});
	}, E, D = () => {
		_ = null, C({ remoteSync: {
			status: "idle",
			pendingRevision: null,
			message: null
		} });
	}, O = (e) => {
		let t = _;
		t === null || t.session !== l || t.projectId !== m?.project.id || C({ remoteSync: {
			status: "failed",
			pendingRevision: t.revision,
			message: e
		} });
	}, ee = () => {
		if (f !== null) return f;
		let r = m, i = _;
		if (r === null || i === null || p || i.session !== l || i.projectId !== r.project.id) return Promise.resolve();
		let o = r.project.id, c = l, u = new AbortController();
		d = u, C({ remoteSync: {
			status: "syncing",
			pendingRevision: i.revision,
			message: null
		} });
		let h = (async () => {
			try {
				let r = await e.getProject(o, u.signal);
				if (p || c !== l || m?.project.id !== o) return;
				if (!r.ok) {
					O(r.message);
					return;
				}
				let i = _;
				if (i === null || i.session !== c || i.projectId !== o) return;
				if (r.value.revision < i.revision) {
					O("Remote project revision is not available yet");
					return;
				}
				if (r.value.revision <= t.getState().runtime.revision) {
					D();
					return;
				}
				if (g > 0) return;
				if (a?.hasUnconfirmedChanges()) {
					a.markConflict(i.revision), D();
					return;
				}
				a?.dispose(), s?.close(), n.cancelPendingLoads(), E(r.value);
			} catch (e) {
				!(typeof e == "object" && e && "name" in e && e.name === "AbortError") && !p && c === l && O(e instanceof Error ? e.message : "Remote project refresh failed");
			}
		})();
		return f = h, h.finally(() => {
			f === h && (f = null, d = null);
		}), h;
	}, te = () => {
		let e = _;
		if (!(e === null || e.session !== l || e.projectId !== m?.project.id)) {
			if (e.revision <= t.getState().runtime.revision) {
				D();
				return;
			}
			if (!(g > 0)) {
				if (a?.hasUnconfirmedChanges()) {
					a.markConflict(e.revision), D();
					return;
				}
				ee();
			}
		}
	}, ne = (e, n) => {
		if (p || n !== l || m === null || !Ft(e)) return;
		let r = e.type === "snapshot" ? e.snapshot.revision : e.revision, i = e.type === "snapshot" ? e.snapshot.project.id : e.projectId;
		i !== m.project.id || r <= t.getState().runtime.revision || ((_ === null || _.session !== n || r > _.revision) && (_ = {
			projectId: i,
			revision: r,
			session: n
		}, C({ remoteSync: {
			status: "syncing",
			pendingRevision: r,
			message: null
		} })), te());
	};
	E = (c) => {
		d?.abort(), d = null, f = null, l += 1, _ = null, m = c;
		let u = Qf(c);
		t.replaceProject(u, {
			projectId: c.project.id,
			revision: c.revision
		}), n.project(null, u), o?.(), a = r(t, (t) => T(t.projectId, (n) => e.saveProjectState({
			...t,
			revision: n
		}))), C({
			save: a.getState(),
			remoteSync: {
				status: "idle",
				pendingRevision: null,
				message: null
			}
		}), o = a.subscribe((e) => {
			C({ save: e });
		});
		let p = l;
		s = i(c.project.id, (e) => {
			ne(e, p);
		}), w($f(c)), C({
			activeProjectId: c.project.id,
			error: null
		});
	};
	let re = async (t, r) => {
		let i = new AbortController();
		u = i;
		let o;
		try {
			o = await e.getProject(t, i.signal);
		} catch (e) {
			return p || r !== c || e instanceof DOMException && e.name === "AbortError" ? {
				ok: !1,
				kind: "stale"
			} : {
				ok: !1,
				kind: "load",
				message: e instanceof Error ? e.message : "Project load failed"
			};
		}
		if (p || r !== c) return {
			ok: !1,
			kind: "stale"
		};
		if (!o.ok) return {
			ok: !1,
			kind: "load",
			message: o.message
		};
		let l = a, d = s;
		return l?.dispose(), d?.close(), n.cancelPendingLoads(), E(o.value), C({ pendingSwitch: null }), { ok: !0 };
	}, k = async (e) => {
		if (p) return {
			ok: !1,
			kind: "stale"
		};
		c += 1;
		let t = c;
		u?.abort(), C({ pendingSwitch: null });
		let n = await (a?.flush() ?? Promise.resolve({ ok: !0 }));
		return p || t !== c ? {
			ok: !1,
			kind: "stale"
		} : n.ok ? re(e, t) : (C({ pendingSwitch: {
			projectId: e,
			failure: n
		} }), {
			ok: !1,
			kind: "decision",
			failure: n
		});
	}, ie = async (e, t) => {
		if (m?.project.id === e) {
			let e = await (a?.flush() ?? Promise.resolve({ ok: !0 }));
			if (!e.ok) return e;
		}
		return T(e, t);
	}, A = async (t, n) => {
		v += 1;
		let r = v;
		y?.abort();
		let i = new AbortController();
		y = i, C({
			query: t,
			includeArchived: n,
			loading: !0,
			error: null
		});
		try {
			let a = await e.listProjects({
				query: t,
				includeArchived: n,
				signal: i.signal
			});
			if (p || r !== v) return;
			if (!a.ok) {
				C({
					loading: !1,
					error: a.message
				});
				return;
			}
			C({
				projects: a.value,
				loading: !1,
				error: null
			});
		} catch (e) {
			if (p || r !== v || e instanceof DOMException && e.name === "AbortError") return;
			C({
				loading: !1,
				error: e instanceof Error ? e.message : "Project search failed"
			});
		}
	}, ae = async (t) => {
		let r = c, i = l, o = await (a?.flush() ?? Promise.resolve({ ok: !0 }));
		if (!o.ok) return o;
		if (p || r !== c || i !== l) return {
			ok: !1,
			kind: "server",
			message: "Project selection changed before creation"
		};
		let f = await e.createProject(t);
		return f.ok ? p ? {
			ok: !0,
			snapshot: f.value
		} : r !== c || i !== l ? (w($f(f.value)), {
			ok: !0,
			snapshot: f.value
		}) : (c += 1, u?.abort(), d?.abort(), a?.dispose(), s?.close(), n.cancelPendingLoads(), E(f.value), {
			ok: !0,
			snapshot: f.value
		}) : f;
	}, oe = () => {
		c += 1, l += 1, _ = null, u?.abort(), d?.abort(), d = null, f = null, a?.dispose(), a = null, o?.(), o = null, s?.close(), s = null, n.cancelPendingLoads(), m = null;
		let e = Zf();
		t.replaceProject(e, {
			projectId: "local-project",
			revision: 0
		}), n.project(null, e), C({
			activeProjectId: null,
			pendingSwitch: null,
			save: {
				status: "saved",
				dirty: !1,
				message: null,
				currentRevision: null
			},
			remoteSync: {
				status: "idle",
				pendingRevision: null,
				message: null
			}
		});
	};
	return {
		initialize: (e) => {
			if (p) throw Error("ProjectController has been disposed");
			E(e);
		},
		getActiveSnapshot: () => m === null ? null : structuredClone(m),
		adoptMutationSnapshot: (e) => {
			if (p || m === null || e.project.id !== m.project.id || e.revision < t.getState().runtime.revision) return !1;
			let n = t.getState().project;
			return m = {
				...structuredClone(e),
				project: {
					...structuredClone(e.project),
					semanticState: n.semanticState,
					layoutState: n.layoutState
				}
			}, t.acknowledgeRevision(e.revision), w($f(m)), !0;
		},
		getState: () => ({
			...b,
			projects: b.projects.map((e) => ({ ...e })),
			pendingSwitch: b.pendingSwitch === null ? null : { ...b.pendingSwitch },
			remoteSync: { ...b.remoteSync }
		}),
		subscribe: (e) => (x.add(e), () => {
			x.delete(e);
		}),
		switchProject: k,
		retrySwitch: () => {
			let e = b.pendingSwitch;
			return e === null ? Promise.resolve({
				ok: !1,
				kind: "stale"
			}) : k(e.projectId);
		},
		stayOnProject: () => {
			c += 1, u?.abort(), C({ pendingSwitch: null });
		},
		discardAndSwitch: () => {
			let e = b.pendingSwitch;
			if (e === null || p) return Promise.resolve({
				ok: !1,
				kind: "stale"
			});
			c += 1;
			let t = c;
			return u?.abort(), C({ pendingSwitch: null }), re(e.projectId, t);
		},
		renameActiveProject: async (t) => {
			let n = m;
			return n === null ? {
				ok: !1,
				kind: "server",
				message: "No active project"
			} : ie(n.project.id, (r) => e.renameProject(n.project.id, r, t));
		},
		searchProjects: A,
		createProject: ae,
		archiveProject: async (t) => {
			let n = m?.project.id === t, r = await ie(t, (n) => e.archiveProject(t, n));
			return r.ok && n && m?.project.id === t && r.snapshot.project.status === "archived" && oe(), r;
		},
		restoreProject: (t) => ie(t, (n) => e.restoreProject(t, n)),
		requestDeleteProject: (e) => {
			(m?.project.id === e || b.projects.some((t) => t.id === e)) && C({ deleteCandidateId: e });
		},
		cancelDeleteProject: () => {
			C({ deleteCandidateId: null });
		},
		confirmDeleteProject: async () => {
			let t = b.deleteCandidateId;
			if (t === null) return {
				ok: !1,
				kind: "server",
				message: "No project selected for deletion"
			};
			let n = await ie(t, (n) => e.deleteProject(t, n));
			return n.ok && (m?.project.id === t && oe(), C({
				projects: b.projects.filter((e) => e.id !== t),
				deleteCandidateId: null
			})), n;
		},
		flushSave: () => a?.flush() ?? Promise.resolve({ ok: !0 }),
		retrySave: () => a?.retry() ?? Promise.resolve({ ok: !0 }),
		retryRemoteSync: () => ee(),
		dispose: () => {
			p || (p = !0, c += 1, l += 1, _ = null, u?.abort(), u = null, d?.abort(), d = null, f = null, y?.abort(), y = null, a?.dispose(), a = null, o?.(), o = null, s?.close(), s = null, x.clear());
		}
	};
}
//#endregion
//#region frontend/canvas/src/state/complete-set-projection.ts
var tp = {
	main: "main_output",
	sku: "sku_output",
	detail: "detail_output"
};
function np(e, t) {
	return {
		id: e,
		kind: t,
		managedBy: "complete-set",
		skuId: null,
		assetId: null,
		modelProfileId: null,
		prompt: null,
		compositionGroupId: null,
		textSnapshotId: null,
		outputBoardId: null,
		parameters: {}
	};
}
function rp(e, t) {
	return t === void 0 ? `complete-set:${e}:output` : `complete-set:${e}:output:${t}`;
}
function ip(e, t, n) {
	return n === null ? `complete-set:board:${e}:${t}` : `complete-set:board:${e}:${n}:${t}`;
}
function ap(e) {
	let t = `complete-set:${e}`, n = `${t}:prompt`, r = `${t}:generation`, i = rp(e);
	return {
		nodes: [
			np(n, "prompt"),
			np(r, "model_generation"),
			np(i, tp[e])
		],
		edges: [{
			id: `${t}:edge:prompt`,
			kind: "prompt",
			sourceNodeId: n,
			sourcePort: "prompt",
			targetNodeId: r,
			targetPort: "prompt",
			skuId: null
		}, {
			id: `${t}:edge:output`,
			kind: "output_image",
			sourceNodeId: r,
			sourcePort: "output",
			targetNodeId: i,
			targetPort: "input",
			skuId: null
		}]
	};
}
function op(e, t) {
	return JSON.stringify(e) === JSON.stringify(t);
}
function sp(e, t, n) {
	return e.skuId === n.skuId && e.assetId === null && e.compositionGroupId === n.compositionGroupId && e.textSnapshotId === null ? e.outputBoardId === null ? t !== void 0 && t !== "sku" && e.id === rp(t) || e.prompt === null && e.modelProfileId === null && op(e.parameters, {}) : t !== void 0 && e.kind === tp[t] && e.id === rp(t, e.outputBoardId) && e.prompt === null && e.modelProfileId === null && op(e.parameters, {}) : !1;
}
function cp(e) {
	let t = /* @__PURE__ */ new Map();
	for (let n of e.semanticState.completeSet.selectedOutputTypes) {
		let r = e.semanticState.completeSet.outputs.filter((e) => e.outputType === n);
		for (let e of r) for (let n = 1; n <= (e.quantity ?? 0); n += 1) {
			let r = ip(e.outputType, n, e.skuId);
			t.set(r, {
				id: r,
				outputNodeId: rp(e.outputType, r),
				outputType: e.outputType,
				skuId: e.skuId,
				sortOrder: t.size,
				selectedResultAssetId: null
			});
		}
	}
	return t;
}
function lp(e) {
	let t = e.semanticState.completeSet.selectedOutputTypes.map(ap), n = t.flatMap((e) => e.nodes), r = t.flatMap((e) => e.edges), i = cp(e);
	for (let t of i.values()) {
		let i = np(t.outputNodeId, tp[t.outputType]);
		i.outputBoardId = t.id, i.skuId = t.skuId, i.compositionGroupId = e.semanticState.completeSet.outputs.find((e) => e.outputType === t.outputType && e.skuId === t.skuId)?.compositionGroupId ?? null, n.push(i), r.push({
			id: `complete-set:${t.outputType}:edge:output:${t.id}`,
			kind: "output_image",
			sourceNodeId: `complete-set:${t.outputType}:generation`,
			sourcePort: "output",
			targetNodeId: i.id,
			targetPort: "input",
			skuId: null
		});
	}
	return {
		nodes: n,
		edges: r,
		boards: i
	};
}
function up(e) {
	let t = lp(e), n = t.nodes, r = new Map(n.map((e) => [e.id, e])), i = e.semanticState.nodes.filter((e) => e.managedBy === "complete-set");
	if (i.length !== n.length) return !1;
	for (let t of i) {
		let n = r.get(t.id);
		if (n === void 0 || n.kind !== t.kind || !sp(t, e.semanticState.completeSet.selectedOutputTypes.find((e) => t.id.startsWith(`complete-set:${e}:`)), n)) return !1;
	}
	let a = new Set(i.map((e) => e.id)), o = t.edges, s = new Map(o.map((e) => [e.id, e])), c = e.semanticState.edges.filter((e) => e.id.startsWith("complete-set:") || a.has(e.sourceNodeId) || a.has(e.targetNodeId));
	if (c.length !== o.length) return !1;
	for (let e of c) {
		let t = s.get(e.id);
		if (t === void 0 || e.kind !== t.kind || e.sourceNodeId !== t.sourceNodeId || e.sourcePort !== t.sourcePort || e.targetNodeId !== t.targetNodeId || e.targetPort !== t.targetPort || e.skuId !== t.skuId) return !1;
	}
	let l = t.boards, u = new Set([...l.values()].map((e) => e.outputNodeId)), d = e.semanticState.outputBoards.filter((e) => u.has(e.outputNodeId));
	return d.length === l.size && d.every((t) => {
		let n = l.get(t.id);
		return n !== void 0 && t.outputNodeId === n.outputNodeId && t.outputType === n.outputType && t.skuId === n.skuId && t.sortOrder === n.sortOrder && e.semanticState.nodes.some((e) => e.id === t.outputNodeId && e.outputBoardId === t.id);
	});
}
function dp(e) {
	for (let t of e.semanticState.completeSet.selectedOutputTypes) {
		if (t === "sku") continue;
		let n = e.semanticState.nodes.find((e) => e.id === rp(t));
		if (n !== void 0) for (let r of e.semanticState.completeSet.outputs) r.outputType === t && (r.prompt = n.prompt ?? "", r.modelProfileId = n.modelProfileId, r.modelParameters = structuredClone(n.parameters));
	}
	for (let t of e.semanticState.outputBoards) {
		let n = e.semanticState.completeSet.outputs.find((e) => e.outputType === t.outputType && e.skuId === t.skuId), r = e.semanticState.nodes.find((e) => e.id === t.outputNodeId);
		n !== void 0 && r !== void 0 && (r.compositionGroupId = n.compositionGroupId);
	}
}
function fp(e) {
	dp(e), e.semanticState.advancedCustomized = !up(e);
}
//#endregion
//#region frontend/canvas/src/state/history.ts
function pp() {
	return {
		past: [],
		future: []
	};
}
function mp(e, t) {
	return {
		past: [...e.past, t],
		future: []
	};
}
function hp(e, t) {
	let n = e.past.at(-1);
	return n === void 0 ? null : {
		snapshot: n,
		history: {
			past: e.past.slice(0, -1),
			future: [t, ...e.future]
		}
	};
}
function gp(e, t) {
	let [n, ...r] = e.future;
	return n === void 0 ? null : {
		snapshot: n,
		history: {
			past: [...e.past, t],
			future: r
		}
	};
}
//#endregion
//#region frontend/canvas/src/state/project-store.ts
var _p = /* @__PURE__ */ new Set(["main-product-source", "main-product-cutout"]), vp = /* @__PURE__ */ new Set([
	"product_asset",
	"cutout_asset",
	"prompt",
	"background_image",
	"composition",
	"output_image"
]);
function yp(e) {
	throw Error(`unsupported project action: ${String(e)}`);
}
function bp(e, t) {
	return {
		outputType: e,
		skuId: t,
		quantity: null,
		aspectRatio: null,
		width: null,
		height: null,
		prompt: "",
		modelProfileId: null,
		modelParameters: {},
		referenceAssetId: null,
		compositionGroupId: null
	};
}
function xp(e, t) {
	let n = e.semanticState.completeSet;
	if (n.selectedOutputTypes.includes(t)) return !1;
	n.selectedOutputTypes.push(t), t !== "sku" && n.outputs.push(bp(t, null));
	let r = ap(t);
	return e.semanticState.nodes.push(...r.nodes), e.semanticState.edges.push(...r.edges), !0;
}
function Sp(e) {
	if (e !== null && (!Number.isInteger(e) || e < 1 || e > 500)) throw Error("output quantity must be null or an integer between 1 and 500");
}
function Cp(e, t, n, r) {
	let i = new Map(e.semanticState.outputBoards.map((e) => [e.id, e]));
	for (let a = 1; a <= r; a += 1) {
		let r = ip(t, a, n), o = i.get(r);
		if (o !== void 0) {
			let i = e.semanticState.nodes.find((e) => e.id === o.outputNodeId);
			if (o.outputNodeId !== rp(t, r) || o.outputType !== t || o.skuId !== n || i?.managedBy !== "complete-set" || i.outputBoardId !== r) throw Error(`managed board id collision: ${r}`);
		} else {
			let a = rp(t, r);
			e.semanticState.outputBoards.push({
				id: r,
				outputNodeId: a,
				outputType: t,
				skuId: n,
				sortOrder: e.semanticState.outputBoards.length,
				selectedResultAssetId: null
			}), e.semanticState.nodes.push({
				id: a,
				kind: `${t}_output`,
				managedBy: "complete-set",
				skuId: n,
				assetId: null,
				modelProfileId: null,
				prompt: null,
				compositionGroupId: null,
				textSnapshotId: null,
				outputBoardId: r,
				parameters: {}
			}), e.semanticState.edges.push({
				id: `complete-set:${t}:edge:output:${r}`,
				kind: "output_image",
				sourceNodeId: `complete-set:${t}:generation`,
				sourcePort: "output",
				targetNodeId: a,
				targetPort: "input",
				skuId: null
			});
			let o = e.semanticState.outputBoards.at(-1);
			o !== void 0 && i.set(r, o);
		}
	}
}
function wp(e, t, n) {
	let r = /* @__PURE__ */ new Set();
	for (let i = 1; i <= (n ?? 0); i += 1) r.add(ip(e, i, t));
	return r;
}
function Tp(e, t, n, r) {
	let i = wp(t, n, r), a = wp(t, n, 500);
	return e.semanticState.outputBoards.filter((e) => e.outputNodeId === rp(t, e.id) && e.outputType === t && e.skuId === n && a.has(e.id) && !i.has(e.id));
}
function Ep(e, t) {
	let n = new Set(t.map((e) => e.id)), r = new Set(t.map((e) => e.outputNodeId));
	e.semanticState.outputBoards = e.semanticState.outputBoards.filter((e) => !n.has(e.id)), e.semanticState.nodes = e.semanticState.nodes.filter((e) => !r.has(e.id)), e.semanticState.edges = e.semanticState.edges.filter((e) => !r.has(e.sourceNodeId) && !r.has(e.targetNodeId));
	for (let t of r) delete e.layoutState.nodePositions[t];
}
function Dp(e, t = "identity") {
	if (e === null || typeof e == "boolean" || typeof e == "string") return JSON.stringify(e);
	if (typeof e == "number") {
		if (!Number.isFinite(e)) throw Error(`confirmation identity contains a non-finite number at ${t}`);
		return JSON.stringify(e);
	}
	if (Array.isArray(e)) return `[${e.map((e, n) => Dp(e, `${t}[${n}]`)).join(",")}]`;
	if (typeof e != "object" || e === void 0) throw Error(`confirmation identity contains a non-JSON value at ${t}`);
	let n = e;
	return `{${Object.keys(n).sort().map((e) => `${JSON.stringify(e)}:${Dp(n[e], `${t}.${e}`)}`).join(",")}}`;
}
function Op(e, t) {
	let n = new TextEncoder().encode(t);
	return `${e}:${Array.from(n, (e) => e.toString(16).padStart(2, "0")).join("")}`;
}
function kp(e, t, n, r = [], i = [], a = [], o = [], s = [], c = []) {
	let l = new Set(n.map((e) => e.id)), u = Object.values(e.runtime.taskSnapshots).filter((e) => e.boardId !== null && l.has(e.boardId)).map((e) => e.id).sort(), d = e.runtime.resultHistory.filter((e) => e.boardId !== null && l.has(e.boardId)).map((e) => e.id).sort(), f = n.flatMap((e) => e.selectedResultAssetId === null ? [] : [e.selectedResultAssetId]).sort(), p = {
		actionType: t,
		removedBoardIds: n.map((e) => e.id),
		removedNodeIds: r,
		removedEdgeIds: i,
		addedNodeIds: a,
		addedEdgeIds: o,
		addedBoardIds: s,
		selectedResultAssetIds: f,
		taskIds: u,
		historyResultIds: d,
		preservedCustomNodeIds: c
	};
	return {
		id: Op("canvas-diff", Dp(p, "diff")),
		...p
	};
}
function Ap(e) {
	return e.selectedResultAssetIds.length > 0 || e.taskIds.length > 0 || e.historyResultIds.length > 0;
}
function jp(e) {
	switch (e.type) {
		case "output/disable": return Dp({
			type: e.type,
			outputType: e.outputType
		}, "action");
		case "output/setQuantity": return Dp({
			type: e.type,
			outputType: e.outputType,
			quantity: e.quantity
		}, "action");
		case "sku/setOutputQuantity": return Dp({
			type: e.type,
			skuId: e.skuId,
			quantity: e.quantity
		}, "action");
		case "completeSet/rebuild": return Dp({ type: e.type }, "action");
	}
	return yp(e);
}
function Mp(e) {
	let t = Object.entries(e.runtime.taskSnapshots).sort(([e], [t]) => e.localeCompare(t)).map(([e, t]) => ({
		taskId: e,
		task: t
	}));
	return Dp({
		project: Re(e.project),
		runtime: {
			projectId: e.runtime.projectId,
			revision: e.runtime.revision,
			selectedNodeId: e.runtime.selectedNodeId,
			selectedBoardId: e.runtime.selectedBoardId,
			taskSnapshots: t,
			resultHistory: e.runtime.resultHistory,
			unlinkedBoards: e.runtime.unlinkedBoards,
			uploadIds: e.runtime.uploadIds,
			paidGenerationRequestIds: e.runtime.paidGenerationRequestIds
		}
	}, "baseState");
}
function Np(e, t, n) {
	let r = jp(t), i = Mp(e), a = Dp(n, "diffIdentity");
	return {
		token: Op("canvas-confirmation", Dp({
			version: 1,
			projectId: e.runtime.projectId,
			revision: e.runtime.revision,
			actionIdentity: r,
			baseStateFingerprint: i,
			diffIdentity: a
		}, "challenge")),
		actionIdentity: r,
		baseStateFingerprint: i,
		diffIdentity: a,
		projectId: e.runtime.projectId,
		revision: e.runtime.revision,
		diff: structuredClone(n)
	};
}
function Pp(e, t, n) {
	let r = Np(e, t, n);
	if (t.acceptedDiffId === void 0) return {
		state: e.runtime.pendingConfirmation?.token === r.token ? e : {
			...e,
			runtime: {
				...e.runtime,
				pendingConfirmation: r
			}
		},
		result: {
			applied: !1,
			confirmation: {
				token: r.token,
				diff: r.diff
			}
		}
	};
	let i = e.runtime.pendingConfirmation;
	return i === null || t.acceptedDiffId !== i.token || i.token !== r.token || i.actionIdentity !== r.actionIdentity || i.baseStateFingerprint !== r.baseStateFingerprint || i.diffIdentity !== r.diffIdentity || i.projectId !== r.projectId || i.revision !== r.revision ? {
		state: e,
		result: { applied: !1 }
	} : null;
}
function Fp(e) {
	e.semanticState.outputBoards.forEach((e, t) => {
		e.sortOrder = t;
	});
}
function Ip(e, t) {
	for (let n of t) {
		let t = Object.values(e.taskSnapshots).filter((e) => e.boardId === n.id).map((e) => e.id).sort(), r = e.resultHistory.filter((e) => e.boardId === n.id).map((e) => e.id).sort();
		if (n.selectedResultAssetId === null && t.length === 0 && r.length === 0) continue;
		let i = {
			boardId: n.id,
			selectedResultAssetId: n.selectedResultAssetId,
			taskIds: t,
			resultIds: r
		}, a = e.unlinkedBoards.findIndex((e) => e.boardId === n.id);
		a === -1 ? e.unlinkedBoards.push(i) : e.unlinkedBoards[a] = i;
	}
}
function Lp(e, t, n) {
	let r = new Set(n.semanticState.outputBoards.map((e) => e.id));
	e.unlinkedBoards = e.unlinkedBoards.filter((e) => !r.has(e.boardId)), Ip(e, t.semanticState.outputBoards.filter((e) => !r.has(e.id)));
}
function Rp(e, t) {
	let n = e.taskSnapshots[t.id], r = n !== void 0 && JSON.stringify(n) === JSON.stringify(t), i = /* @__PURE__ */ new Map();
	for (let n of t.results) {
		let t = Dp(n, `task.results.${n.id}`), r = i.get(n.id), a = e.resultHistory.find((e) => e.id === n.id);
		if (r !== void 0 && r !== t || a !== void 0 && Dp(a, `resultHistory.${n.id}`) !== t) throw Error(`immutable result id conflict ${n.id}`);
		i.set(n.id, t);
	}
	e.taskSnapshots[t.id] = structuredClone(t);
	let a = !1;
	for (let n of t.results) if (e.resultHistory.findIndex((e) => e.id === n.id) === -1 && (e.resultHistory.push(structuredClone(n)), a = !0), n.boardId !== null) {
		let t = new Set(e.allowedResultAssetIds[n.boardId] ?? []);
		t.add(n.assetId), e.allowedResultAssetIds[n.boardId] = [...t].sort();
	}
	return !r || a;
}
function zp(e) {
	let t = [], n = [];
	for (let r of e.semanticState.completeSet.selectedOutputTypes) {
		let i = ap(r);
		if (r !== "sku") {
			let t = e.semanticState.completeSet.outputs.find((e) => e.outputType === r && e.skuId === null), n = i.nodes.find((e) => e.id === rp(r));
			t !== void 0 && n !== void 0 && (n.prompt = t.prompt === "" ? null : t.prompt, n.modelProfileId = t.modelProfileId, n.parameters = structuredClone(t.modelParameters));
		}
		t.push(...i.nodes), n.push(...i.edges);
	}
	let r = [];
	for (let i of e.semanticState.completeSet.selectedOutputTypes) {
		let a = e.semanticState.completeSet.outputs.filter((e) => e.outputType === i);
		for (let e of a) for (let i = 1; i <= (e.quantity ?? 0); i += 1) {
			let a = ip(e.outputType, i, e.skuId), o = rp(e.outputType, a);
			r.push({
				id: a,
				outputNodeId: o,
				outputType: e.outputType,
				skuId: e.skuId,
				sortOrder: r.length,
				selectedResultAssetId: null
			}), t.push({
				id: o,
				kind: `${e.outputType}_output`,
				managedBy: "complete-set",
				skuId: e.skuId,
				assetId: null,
				modelProfileId: null,
				prompt: null,
				compositionGroupId: null,
				textSnapshotId: null,
				outputBoardId: a,
				parameters: {}
			}), n.push({
				id: `complete-set:${e.outputType}:edge:output:${a}`,
				kind: "output_image",
				sourceNodeId: `complete-set:${e.outputType}:generation`,
				sourcePort: "output",
				targetNodeId: o,
				targetPort: "input",
				skuId: null
			});
		}
	}
	return {
		nodes: t,
		edges: n,
		boards: r
	};
}
function Bp(e, t) {
	return e.id === t.id && e.kind === t.kind && e.sourceNodeId === t.sourceNodeId && e.sourcePort === t.sourcePort && e.targetNodeId === t.targetNodeId && e.targetPort === t.targetPort && e.skuId === t.skuId;
}
function Vp(e, t) {
	let n = zp(e).edges.filter((e) => t.some((t) => e.id.startsWith(`complete-set:${t}:`))), r = new Set(e.semanticState.nodes.filter((e) => e.managedBy === "complete-set").map((e) => e.id));
	return e.semanticState.edges.filter((e) => r.has(e.sourceNodeId) && r.has(e.targetNodeId) && n.some((t) => Bp(e, t)));
}
function Hp(e, t) {
	for (let n of t.nodes) {
		let t = e.semanticState.nodes.find((e) => e.id === n.id);
		if (t !== void 0 && t.managedBy !== "complete-set") throw Error(`canonical managed node id collision: ${n.id}`);
	}
	for (let n of t.edges) {
		let t = e.semanticState.edges.find((e) => e.id === n.id);
		if (t === void 0) continue;
		let r = e.semanticState.nodes.find((e) => e.id === t.sourceNodeId), i = e.semanticState.nodes.find((e) => e.id === t.targetNodeId);
		if (r?.managedBy !== "complete-set" || i?.managedBy !== "complete-set" || t.kind !== n.kind || t.sourceNodeId !== n.sourceNodeId || t.sourcePort !== n.sourcePort || t.targetNodeId !== n.targetNodeId || t.targetPort !== n.targetPort || t.skuId !== n.skuId) throw Error(`canonical managed edge id collision: ${n.id}`);
	}
	for (let n of t.boards) {
		let t = e.semanticState.outputBoards.find((e) => e.id === n.id);
		if (t !== void 0 && (e.semanticState.nodes.find((e) => e.id === t.outputNodeId)?.managedBy !== "complete-set" || t.outputNodeId !== n.outputNodeId || t.outputType !== n.outputType || t.skuId !== n.skuId)) throw Error(`canonical managed board id collision: ${n.id}`);
	}
}
function Up(e) {
	let t = e.project.semanticState.nodes.filter((e) => e.managedBy === "complete-set").map((e) => e.id), n = new Set(t), r = Vp(e.project, [
		"main",
		"sku",
		"detail"
	]), i = e.project.semanticState.outputBoards.filter((e) => n.has(e.outputNodeId)), a = zp(e.project);
	Hp(e.project, a);
	let o = e.project.semanticState.nodes.filter((e) => e.managedBy !== "complete-set").map((e) => e.id);
	return kp(e, "completeSet/rebuild", i, t, r.map((e) => e.id), a.nodes.map((e) => e.id), a.edges.map((e) => e.id), a.boards.map((e) => e.id), o);
}
function Wp(e, t) {
	let n = structuredClone(e), r = new Set(t.removedNodeIds), i = new Set(t.removedEdgeIds), a = new Set(t.removedBoardIds), o = n.project.semanticState.outputBoards.filter((e) => a.has(e.id));
	n.project.semanticState.nodes = n.project.semanticState.nodes.filter((e) => !r.has(e.id)), n.project.semanticState.edges = n.project.semanticState.edges.filter((e) => !i.has(e.id)), n.project.semanticState.outputBoards = n.project.semanticState.outputBoards.filter((e) => !a.has(e.id)), Ip(n.runtime, o);
	let s = zp(n.project);
	return n.project.semanticState.nodes.push(...s.nodes), n.project.semanticState.edges.push(...s.edges), n.project.semanticState.outputBoards.push(...s.boards), Fp(n.project), fp(n.project), n;
}
function Gp(e, t) {
	switch (t.type) {
		case "output/enable": {
			let n = structuredClone(e), r = xp(n.project, t.outputType);
			return r && fp(n.project), {
				state: r ? n : e,
				result: { applied: r }
			};
		}
		case "output/setQuantity": {
			if (Sp(t.quantity), (e.project.semanticState.completeSet.outputs.find((e) => e.outputType === t.outputType && e.skuId === null)?.quantity ?? null) === t.quantity) return {
				state: e,
				result: { applied: !1 }
			};
			let n = Tp(e.project, t.outputType, null, t.quantity);
			if (n.length > 0) {
				let r = kp(e, t.type, n);
				if (Ap(r)) {
					let n = Pp(e, t, r);
					if (n !== null) return n;
				}
			}
			let r = structuredClone(e);
			xp(r.project, t.outputType);
			let i = r.project.semanticState.completeSet.outputs.find((e) => e.outputType === t.outputType && e.skuId === null);
			if (i === void 0) throw Error(`missing complete-set output ${t.outputType}`);
			return i.quantity = t.quantity, n.length > 0 && (Ep(r.project, n), Ip(r.runtime, n), Fp(r.project)), t.quantity !== null && Cp(r.project, t.outputType, null, t.quantity), fp(r.project), {
				state: r,
				result: { applied: !0 }
			};
		}
		case "sku/setOutputQuantity": {
			Sp(t.quantity);
			let n = e.project.semanticState.completeSet.outputs.find((e) => e.outputType === "sku" && e.skuId === t.skuId), r = n?.quantity ?? null;
			if (n !== void 0 && r === t.quantity) return {
				state: e,
				result: { applied: !1 }
			};
			let i = Tp(e.project, "sku", t.skuId, t.quantity);
			if (i.length > 0) {
				let n = kp(e, t.type, i);
				if (Ap(n)) {
					let r = Pp(e, t, n);
					if (r !== null) return r;
				}
			}
			let a = structuredClone(e);
			xp(a.project, "sku");
			let o = a.project.semanticState.completeSet.outputs.find((e) => e.outputType === "sku" && e.skuId === t.skuId);
			return o === void 0 && (o = bp("sku", t.skuId), a.project.semanticState.completeSet.outputs.push(o)), o.quantity = t.quantity, i.length > 0 && (Ep(a.project, i), Ip(a.runtime, i), Fp(a.project)), t.quantity !== null && Cp(a.project, "sku", t.skuId, t.quantity), fp(a.project), {
				state: a,
				result: { applied: !0 }
			};
		}
		case "output/configure": {
			if (t.outputType === "sku" != (t.skuId !== null)) throw Error("SKU output configuration requires exactly one SKU");
			let n = e.project.semanticState.completeSet.outputs.find((e) => e.outputType === t.outputType && e.skuId === t.skuId);
			if (n === void 0) throw Error("configure an output only after selecting it");
			if (JSON.stringify(n) === JSON.stringify({
				...n,
				...t.patch
			})) return {
				state: e,
				result: { applied: !1 }
			};
			let r = structuredClone(e), i = r.project.semanticState.completeSet.outputs.find((e) => e.outputType === t.outputType && e.skuId === t.skuId);
			if (i === void 0) throw Error("complete-set output disappeared while configuring");
			if (Object.assign(i, structuredClone(t.patch)), t.outputType !== "sku") {
				let e = r.project.semanticState.nodes.find((e) => e.id === rp(t.outputType));
				e !== void 0 && (e.prompt = i.prompt === "" ? null : i.prompt, e.modelProfileId = i.modelProfileId, e.parameters = structuredClone(i.modelParameters));
			}
			return fp(r.project), {
				state: r,
				result: { applied: !0 }
			};
		}
		case "output/disable": {
			if (!e.project.semanticState.completeSet.selectedOutputTypes.includes(t.outputType)) return {
				state: e,
				result: { applied: !1 }
			};
			let n = `complete-set:${t.outputType}:`, r = e.project.semanticState.nodes.filter((e) => e.managedBy === "complete-set" && e.id.startsWith(n)).map((e) => e.id), i = new Set(r), a = Vp(e.project, [t.outputType]), o = new Set(a.map((e) => e.id)), s = e.project.semanticState.edges.filter((e) => i.has(e.sourceNodeId) || i.has(e.targetNodeId)), c = s.some((e) => !o.has(e.id)), l = e.project.semanticState.outputBoards.filter((e) => i.has(e.outputNodeId)), u = kp(e, t.type, l, r, s.map((e) => e.id));
			if (Ap(u) || c) {
				let n = Pp(e, t, u);
				if (n !== null) return n;
			}
			let d = structuredClone(e), f = new Set(s.map((e) => e.id)), p = new Set(l.map((e) => e.id));
			d.project.semanticState.completeSet.selectedOutputTypes = d.project.semanticState.completeSet.selectedOutputTypes.filter((e) => e !== t.outputType), d.project.semanticState.completeSet.outputs = d.project.semanticState.completeSet.outputs.filter((e) => e.outputType !== t.outputType), d.project.semanticState.nodes = d.project.semanticState.nodes.filter((e) => !i.has(e.id));
			for (let e of i) delete d.project.layoutState.nodePositions[e];
			return d.project.semanticState.edges = d.project.semanticState.edges.filter((e) => !f.has(e.id)), d.project.semanticState.outputBoards = d.project.semanticState.outputBoards.filter((e) => !p.has(e.id)), Ip(d.runtime, l), Fp(d.project), fp(d.project), {
				state: d,
				result: { applied: !0 }
			};
		}
		case "board/selectResult": {
			let n = e.project.semanticState.outputBoards.find((e) => e.id === t.boardId);
			if (n === void 0) throw Error(`unknown output board ${t.boardId}`);
			let r = e.runtime.allowedResultAssetIds[t.boardId];
			if (t.assetId !== null && (r === void 0 || !r.includes(t.assetId))) throw Error("selected asset is not a permitted result version");
			if (n.selectedResultAssetId === t.assetId) return {
				state: e,
				result: { applied: !1 }
			};
			let i = structuredClone(e), a = i.project.semanticState.outputBoards.find((e) => e.id === t.boardId);
			if (a === void 0) throw Error(`unknown output board ${t.boardId}`);
			return a.selectedResultAssetId = t.assetId, {
				state: i,
				result: { applied: !0 }
			};
		}
		case "task/statusReceived": {
			let n = structuredClone(e), r = Rp(n.runtime, t.task);
			return {
				state: r ? n : e,
				result: { applied: r }
			};
		}
		case "runtime/setAllowedResultAssets": {
			let n = [...new Set(t.assetIds)].sort(), r = e.runtime.allowedResultAssetIds[t.boardId];
			if (JSON.stringify(r ?? []) === JSON.stringify(n)) return {
				state: e,
				result: { applied: !1 }
			};
			let i = structuredClone(e);
			return i.runtime.allowedResultAssetIds[t.boardId] = n, {
				state: i,
				result: { applied: !0 }
			};
		}
		case "asset/useRectangularSource": {
			let n = e.project.layoutState.productLayers.find((e) => e.skuId === null && e.locked && e.sourceAssetId === t.workingAssetId);
			if (n === void 0) throw Error("rectangular fallback requires the locked main working asset");
			if (n.renderAssetId === t.workingAssetId && n.allowOpaqueFallback) return {
				state: e,
				result: { applied: !1 }
			};
			let r = structuredClone(e), i = r.project.layoutState.productLayers.find((e) => e.id === n.id);
			if (i === void 0) throw Error("rectangular fallback projection is unavailable");
			if (i.renderAssetId = t.workingAssetId, i.allowOpaqueFallback = !0, i.compositionGroupId !== null) for (let e of r.project.layoutState.productLayers) e.compositionGroupId === i.compositionGroupId && e.sourceAssetId === t.workingAssetId && (e.renderAssetId = t.workingAssetId, e.allowOpaqueFallback = !0);
			return {
				state: r,
				result: { applied: !0 }
			};
		}
		case "mode/set": {
			if (e.project.semanticState.mode === t.mode) return {
				state: e,
				result: { applied: !1 }
			};
			let n = structuredClone(e);
			return n.project.semanticState.mode = t.mode, {
				state: n,
				result: { applied: !0 }
			};
		}
		case "viewport/set": {
			let n = structuredClone(t.viewport);
			if (!Number.isFinite(n.x) || !Number.isFinite(n.y) || !Number.isFinite(n.zoom) || n.zoom <= 0 || n.zoom > 1e3) throw Error("canvas viewport must contain finite coordinates and a positive zoom");
			let r = e.project.layoutState.viewport;
			if (r.x === n.x && r.y === n.y && r.zoom === n.zoom) return {
				state: e,
				result: { applied: !1 }
			};
			let i = structuredClone(e);
			return i.project.layoutState.viewport = n, {
				state: i,
				result: { applied: !0 }
			};
		}
		case "node/add": {
			if (t.node.kind === "auto_cutout") throw Error("auto cutout nodes are projected by the system");
			if (t.node.id === "main-product-source" || t.node.id === "main-product-cutout") throw Error("system product pipeline nodes are projected by the system");
			if (e.project.semanticState.nodes.some((e) => e.id === t.node.id)) throw Error(`duplicate canvas node ${t.node.id}`);
			let n = structuredClone(e);
			return n.project.semanticState.nodes.push(structuredClone(t.node)), fp(n.project), {
				state: n,
				result: { applied: !0 }
			};
		}
		case "node/update": {
			let n = e.project.semanticState.nodes.find((e) => e.id === t.nodeId);
			if (n === void 0) throw Error(`unknown canvas node ${t.nodeId}`);
			if (n.id === "main-product-source" || n.id === "main-product-cutout") throw Error("system product pipeline nodes are immutable");
			let r = structuredClone(e), i = r.project.semanticState.nodes.find((e) => e.id === t.nodeId);
			if (i === void 0) throw Error(`unknown canvas node ${t.nodeId}`);
			return "prompt" in t.patch && (i.prompt = t.patch.prompt ?? null), "modelProfileId" in t.patch && (i.modelProfileId = t.patch.modelProfileId ?? null), "parameters" in t.patch && (i.parameters = {
				...i.parameters,
				...structuredClone(t.patch.parameters ?? {})
			}), "assetId" in t.patch && (i.assetId = t.patch.assetId ?? null), "skuId" in t.patch && (i.skuId = t.patch.skuId ?? null), "compositionGroupId" in t.patch && (i.compositionGroupId = t.patch.compositionGroupId ?? null), fp(r.project), {
				state: r,
				result: { applied: !0 }
			};
		}
		case "node/move": {
			if (!e.project.semanticState.nodes.some((e) => e.id === t.nodeId)) throw Error(`unknown canvas node ${t.nodeId}`);
			if (_p.has(t.nodeId)) throw Error("system product pipeline nodes are immutable");
			let n = structuredClone(e);
			return n.project.layoutState.nodePositions[t.nodeId] = structuredClone(t.position), {
				state: n,
				result: { applied: !0 }
			};
		}
		case "edge/connect": {
			let n = xe(t.edge);
			if (e.project.semanticState.edges.some((e) => e.id === n.id)) throw Error(`duplicate canvas edge ${n.id}`);
			let r = new Set(e.project.semanticState.nodes.map((e) => e.id));
			if (!r.has(n.sourceNodeId) || !r.has(n.targetNodeId)) throw Error("canvas edge endpoints must exist before connect");
			let i = e.project.semanticState.nodes.find((e) => e.id === n.sourceNodeId), a = e.project.semanticState.nodes.find((e) => e.id === n.targetNodeId);
			if (i === void 0 || a === void 0 || !D(i.kind, a.kind, n.kind)) throw Error("incompatible node connection");
			let o = n.kind === "cutout_asset" && n.sourceNodeId === "main-product-cutout" && i.id === "main-product-cutout" && i.kind === "auto_cutout" && a.kind === "model_generation";
			if ((_p.has(n.sourceNodeId) || _p.has(n.targetNodeId)) && !o) throw Error("system product pipeline edges are projected by the system");
			if (vp.has(n.kind) && e.project.semanticState.edges.some((e) => e.kind === n.kind && e.targetNodeId === n.targetNodeId)) throw Error("duplicate singleton input is not allowed");
			let s = structuredClone(e);
			return s.project.semanticState.edges.push(n), fp(s.project), {
				state: s,
				result: { applied: !0 }
			};
		}
		case "text/update": {
			let n = e.project.layoutState.textSnapshots.find((e) => e.id === t.layerId);
			if (n === void 0) throw Error(`unknown text layer ${t.layerId}`);
			let r = structuredClone(e), i = r.project.layoutState.textSnapshots.find((e) => e.id === t.layerId);
			if (i === void 0) throw Error(`unknown text layer ${t.layerId}`);
			let a = structuredClone(t.patch);
			if (a.lineHeight !== void 0) {
				let e = C({
					...n,
					fontSize: a.fontSize ?? n.fontSize
				}, a.lineHeight);
				if (a.lines !== void 0 && JSON.stringify(a.lines) !== JSON.stringify(e.lines)) throw Error("行距更新必须使用确定性的显式行坐标");
				a.lines = e.lines;
			}
			if (a.lines !== void 0) {
				let e = a.lines.map((e) => e.text).join("\n");
				if (a.content !== void 0 && a.content !== e) throw Error("文字内容必须与显式行文本一致");
				a.content = e;
			} else a.content !== void 0 && Object.assign(a, w(n, a.content));
			return Object.assign(i, a), {
				state: r,
				result: { applied: !0 }
			};
		}
		case "composition/update": {
			let n = e.project.semanticState.compositionGroups.find((e) => e.id === t.groupId);
			if (n === void 0) throw Error(`unknown composition group ${t.groupId}`);
			if (JSON.stringify(n.layout) === JSON.stringify(t.layout)) return {
				state: e,
				result: { applied: !1 }
			};
			let r = structuredClone(e), i = r.project.semanticState.compositionGroups.find((e) => e.id === t.groupId);
			if (i === void 0) throw Error(`unknown composition group ${t.groupId}`);
			i.layout = structuredClone(t.layout), i.layoutHash = p(i.layout);
			let a = m(i.layout);
			for (let e of i.productLayerIds) {
				let t = r.project.layoutState.productLayers.find((t) => t.id === e);
				if (t === void 0 || t.compositionGroupId !== i.id) throw Error(`composition group ${i.id} has an invalid product member`);
				r.project.layoutState.objectTransforms[t.transformId] = { ...a };
			}
			return {
				state: r,
				result: { applied: !0 }
			};
		}
		case "composition/create": {
			let n = e.project.layoutState.productLayers.find((e) => e.skuId === null && e.locked);
			if (n === void 0 || n.compositionGroupId !== null) return {
				state: e,
				result: { applied: !1 }
			};
			let r = new Set(e.project.semanticState.compositionGroups.map((e) => e.id)), i = 1;
			for (; r.has(`composition-group-${i}`);) i += 1;
			let a = `composition-group-${i}`, s = structuredClone(o), c = structuredClone(e), l = c.project.layoutState.productLayers.find((e) => e.id === n.id);
			if (l === void 0) throw Error("main product layer disappeared while creating composition group");
			l.compositionGroupId = a, c.project.layoutState.objectTransforms[l.transformId] = m(s);
			let u = /* @__PURE__ */ new Map();
			for (let e of t.skuProducts) e.skuId !== null && !u.has(e.skuId) && u.set(e.skuId, e);
			let d = [];
			for (let [e, t] of u) {
				let n = c.project.layoutState.productLayers.find((n) => n.skuId === e && n.compositionGroupId === null && n.locked && n.sourceAssetId === t.sourceAssetId && n.renderAssetId === t.renderAssetId), r = n ?? {
					id: `${a}:sku:${e}`,
					sourceAssetId: t.sourceAssetId,
					renderAssetId: t.renderAssetId,
					allowOpaqueFallback: t.allowOpaqueFallback,
					skuId: e,
					compositionGroupId: null,
					transformId: `${a}:sku:${e}:transform`,
					locked: !0
				};
				if (n === void 0) {
					if (c.project.layoutState.productLayers.some((e) => e.id === r.id)) throw Error(`composition SKU layer id collision: ${r.id}`);
					c.project.layoutState.productLayers.push(r);
				}
				r.compositionGroupId = a, c.project.layoutState.objectTransforms[r.transformId] = m(s), d.push(r.id);
			}
			return c.project.semanticState.compositionGroups.push({
				id: a,
				skuIds: [...u.keys()],
				productLayerIds: [l.id, ...d],
				layout: s,
				layoutHash: p(s)
			}), {
				state: c,
				result: { applied: !0 }
			};
		}
		case "runtime/select": {
			let n = structuredClone(e), r = n.runtime.selectedNodeId !== t.nodeId || n.runtime.selectedBoardId !== t.boardId;
			return n.runtime.selectedNodeId = t.nodeId, n.runtime.selectedBoardId = t.boardId, {
				state: r ? n : e,
				result: { applied: r }
			};
		}
		case "upload/record": {
			if (e.runtime.uploadIds.includes(t.uploadId)) return {
				state: e,
				result: { applied: !1 }
			};
			let n = structuredClone(e);
			return n.runtime.uploadIds.push(t.uploadId), {
				state: n,
				result: { applied: !0 }
			};
		}
		case "generation/paidRequested": {
			if (e.runtime.paidGenerationRequestIds.includes(t.requestId)) return {
				state: e,
				result: { applied: !1 }
			};
			let n = structuredClone(e);
			return n.runtime.paidGenerationRequestIds.push(t.requestId), {
				state: n,
				result: { applied: !0 }
			};
		}
		case "completeSet/rebuild": {
			let n = Up(e), r = Pp(e, t, n);
			return r === null ? {
				state: Wp(e, n),
				result: { applied: !0 }
			} : r;
		}
	}
	return yp(t);
}
function Kp(e, t) {
	let n = Gp(e, t);
	return n.result.applied ? {
		...n,
		state: {
			...n.state,
			project: Ie(n.state.project),
			runtime: {
				...n.state.runtime,
				pendingConfirmation: null
			}
		}
	} : n;
}
function qp(e) {
	switch (e.type) {
		case "output/enable":
		case "output/disable":
		case "output/setQuantity":
		case "sku/setOutputQuantity":
		case "output/configure":
		case "board/selectResult":
		case "asset/useRectangularSource":
		case "mode/set":
		case "node/add":
		case "node/update":
		case "node/move":
		case "edge/connect":
		case "text/update":
		case "composition/update":
		case "composition/create":
		case "completeSet/rebuild": return !0;
		case "runtime/select":
		case "runtime/setAllowedResultAssets":
		case "upload/record":
		case "generation/paidRequested":
		case "task/statusReceived":
		case "viewport/set": return !1;
	}
	return yp(e);
}
function Jp(e = Zf(), t = {
	projectId: "local-project",
	revision: 0
}) {
	let n = {
		project: Ie(e),
		runtime: Xf(t)
	}, r = pp(), i = /* @__PURE__ */ new Set(), a = () => {
		for (let e of [...i]) e();
	};
	return {
		getState: () => structuredClone(n),
		dispatch: (e) => {
			let t = n, i = n.project, o = Kp(n, e);
			return o.result.applied && qp(e) && (r = mp(r, structuredClone(i))), n = o.state, n !== t && a(), structuredClone(o.result);
		},
		canUndo: () => r.past.length > 0,
		canRedo: () => r.future.length > 0,
		undo: () => {
			let e = n.project, t = hp(r, structuredClone(e));
			if (t === null) return !1;
			r = t.history;
			let i = structuredClone(n.runtime);
			return i.pendingConfirmation = null, Lp(i, e, t.snapshot), n = {
				...n,
				project: structuredClone(t.snapshot),
				runtime: i
			}, a(), !0;
		},
		redo: () => {
			let e = n.project, t = gp(r, structuredClone(e));
			if (t === null) return !1;
			r = t.history;
			let i = structuredClone(n.runtime);
			return i.pendingConfirmation = null, Lp(i, e, t.snapshot), n = {
				...n,
				project: structuredClone(t.snapshot),
				runtime: i
			}, a(), !0;
		},
		subscribe: (e) => (i.add(e), () => {
			i.delete(e);
		}),
		acknowledgeRevision: (e) => {
			if (!Number.isInteger(e) || e < 0) throw Error("project revision must be a non-negative integer");
			e <= n.runtime.revision || (n = {
				...n,
				runtime: {
					...n.runtime,
					revision: e
				}
			}, a());
		},
		replaceProject: (e, t) => {
			n = {
				project: Ie(e),
				runtime: Xf(t ?? {
					projectId: n.runtime.projectId,
					revision: n.runtime.revision
				})
			}, r = pp(), a();
		}
	};
}
//#endregion
//#region frontend/canvas/src/main.ts
var Yp = "<main class=\"canvas-shell\" data-canvas-state=\"loading\" aria-busy=\"true\"><p>Loading Product Canvas...</p></main>", Xp = /* @__PURE__ */ new WeakSet();
function Zp(e = Jp(), t) {
	let n = document.querySelector("#canvas-app");
	if (n === null) throw Error("Product Canvas mount point \"#canvas-app\" was not found.");
	if (Xp.has(n)) throw Error("Product Canvas is already mounted in #canvas-app.");
	if (t !== void 0) {
		let r = t.element ?? document.createElement("canvas");
		r.dataset.canvasSurface = "product-canvas", n.replaceChildren(r), t.adapter.mount(r, (n) => {
			let r = e.getState().project;
			e.dispatch(n).applied && t.adapter.project(r, e.getState().project);
		});
		let i = e.getState().project;
		return t.adapter.project(null, i), t.adapter.setMode(i.semanticState.mode), Xp.add(n), e;
	}
	return n.innerHTML = Yp, Xp.add(n), e;
}
function Qp(e) {
	let t = e === null ? "/app/canvas" : `/app/canvas/${encodeURIComponent(e)}`;
	window.location.pathname !== t && window.history.replaceState(null, "", t);
}
function $p({ bootstrap: t, root: r = document.querySelector("#canvas-app") ?? void 0, api: i = rt({ apiBase: t.apiBase }), assetsApi: a = Ct({ apiBase: t.apiBase }), compositionsApi: o = Et({ apiBase: t.apiBase }), skusApi: s = nn({ apiBase: t.apiBase }), providersApi: c = e({ apiBase: t.apiBase }), generationsApi: l = n({ apiBase: t.apiBase }), exportsApi: u = At({ apiBase: t.apiBase }), adapter: d = fd(), openEvents: f = (e, n) => $t({
	apiBase: t.apiBase,
	projectId: e,
	onEvent: n
}), syncUrl: p = Qp, loadFont: m = y }) {
	if (r === void 0) throw Error("Product Canvas mount point \"#canvas-app\" was not found.");
	if (Xp.has(r)) throw Error("Product Canvas is already mounted in #canvas-app.");
	Xp.add(r), r.innerHTML = Yp;
	let h = Jp(), g = /* @__PURE__ */ new Set(), _ = ep({
		api: i,
		store: h,
		adapter: d,
		createAutosave: (e, t) => Yf({
			store: e,
			save: t
		}),
		openEvents: (e, t) => f(e, (e) => {
			t(e);
			for (let t of [...g]) t(e);
		})
	}), v = null, b = !1, x = null, S = _.subscribe((e) => {
		e.activeProjectId !== x && (x = e.activeProjectId, p(x));
	}), C = new AbortController();
	return {
		ready: (async () => {
			try {
				if (await m(), b) return;
				if (v = qf({
					root: r,
					controller: _,
					store: h,
					adapter: d,
					assetsApi: a,
					compositionsApi: o,
					skusApi: s,
					providersApi: c,
					generationsApi: l,
					exportsApi: u,
					subscribeEvents: (e) => (g.add(e), () => {
						g.delete(e);
					})
				}), t.projectId !== null) {
					let e = await i.getProject(t.projectId, C.signal);
					if (b) return;
					if (!e.ok) throw Error(e.message);
					_.initialize(e.value);
				}
				b || await _.searchProjects("", !1);
			} catch (e) {
				if (!b) {
					let t = document.createElement("p");
					t.className = "canvas-fatal-error", t.setAttribute("role", "alert"), t.textContent = e instanceof Error ? e.message : "画布加载失败", r.replaceChildren(t);
				}
				throw e;
			}
		})(),
		store: h,
		controller: _,
		dispose: () => {
			b || (b = !0, C.abort(), S(), v === null ? (_.dispose(), d.dispose(), r.replaceChildren()) : v.dispose(), g.clear(), Xp.delete(r));
		}
	};
}
function em(e) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error("Canvas bootstrap must be an object");
	let t = e;
	if (Object.keys(t).sort().join(",") !== "apiBase,projectId" || typeof t.apiBase != "string" || !t.apiBase.startsWith("/") || t.projectId !== null && typeof t.projectId != "string") throw Error("Canvas bootstrap does not match the expected contract");
	return {
		apiBase: t.apiBase,
		projectId: t.projectId
	};
}
function tm() {
	let e = document.querySelector("#canvas-app"), t = document.querySelector("#canvas-bootstrap");
	if (!(e === null || t === null)) try {
		let n = $p({
			root: e,
			bootstrap: em(JSON.parse(t.textContent ?? "null"))
		});
		n.ready.catch((t) => {
			n.dispose();
			let r = document.createElement("p");
			r.className = "canvas-fatal-error", r.setAttribute("role", "alert"), r.textContent = t instanceof Error ? t.message : "画布加载失败", e.replaceChildren(r);
		});
	} catch (t) {
		let n = document.createElement("p");
		n.className = "canvas-fatal-error", n.setAttribute("role", "alert"), n.textContent = t instanceof Error ? t.message : "画布加载失败", e.replaceChildren(n);
	}
}
tm();
//#endregion
export { fd as createCanvasAdapter, Zp as mountCanvas, em as parseCanvasBootstrap, $p as startCanvasApplication };
