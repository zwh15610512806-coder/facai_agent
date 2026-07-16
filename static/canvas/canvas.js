//#region frontend/canvas/src/domain/composition.ts
var e = {
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
function t(e) {
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
function n(e) {
	if (e === null || typeof e == "boolean" || typeof e == "string") return e;
	if (typeof e == "number") return t(e);
	if (Array.isArray(e)) return e.map(n);
	if (typeof e != "object" || !e) throw Error("composition layout contains a non-JSON value");
	return Object.fromEntries(Object.entries(e).sort(([e], [t]) => e.localeCompare(t)).map(([e, t]) => [e, n(t)]));
}
function r(e) {
	return JSON.stringify(n(e));
}
function i(e, t) {
	return e >>> t | e << 32 - t;
}
function a(e) {
	let t = new TextEncoder().encode(e), n = t.length * 8, r = Math.ceil((t.length + 9) / 64) * 64, a = new Uint8Array(r);
	a.set(t), a[t.length] = 128;
	let o = new DataView(a.buffer);
	o.setUint32(r - 8, Math.floor(n / 4294967296), !1), o.setUint32(r - 4, n >>> 0, !1);
	let s = new Uint32Array([
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
	]), c = new Uint32Array([
		1779033703,
		3144134277,
		1013904242,
		2773480762,
		1359893119,
		2600822924,
		528734635,
		1541459225
	]), l = /* @__PURE__ */ new Uint32Array(64);
	for (let e = 0; e < r; e += 64) {
		for (let t = 0; t < 16; t += 1) l[t] = o.getUint32(e + t * 4, !1);
		for (let e = 16; e < 64; e += 1) {
			let t = l[e - 15], n = l[e - 2], r = i(t, 7) ^ i(t, 18) ^ t >>> 3, a = i(n, 17) ^ i(n, 19) ^ n >>> 10;
			l[e] = l[e - 16] + r + l[e - 7] + a >>> 0;
		}
		let [t, n, r, a, u, d, f, p] = c;
		for (let e = 0; e < 64; e += 1) {
			let o = i(u, 6) ^ i(u, 11) ^ i(u, 25), c = u & d ^ ~u & f, m = p + o + c + s[e] + l[e] >>> 0, h = (i(t, 2) ^ i(t, 13) ^ i(t, 22)) + (t & n ^ t & r ^ n & r) >>> 0;
			p = f, f = d, d = u, u = a + m >>> 0, a = r, r = n, n = t, t = m + h >>> 0;
		}
		c[0] = c[0] + t >>> 0, c[1] = c[1] + n >>> 0, c[2] = c[2] + r >>> 0, c[3] = c[3] + a >>> 0, c[4] = c[4] + u >>> 0, c[5] = c[5] + d >>> 0, c[6] = c[6] + f >>> 0, c[7] = c[7] + p >>> 0;
	}
	return Array.from(c, (e) => e.toString(16).padStart(8, "0")).join("");
}
function o(e) {
	return `sha256:${a(r(e))}`;
}
function s(e) {
	return {
		x: e.slot.x + e.slot.width * e.anchor.x,
		y: e.baseline,
		scale: e.relativeProductFraction,
		rotation: t(e.rotation)
	};
}
//#endregion
//#region frontend/canvas/src/domain/text-layout.ts
var c = {
	family: "Noto Sans CJK SC",
	version: "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
	sha256: "2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b",
	url: "/static/canvas/fonts/NotoSansCJKsc-Regular.otf"
};
function l(e) {
	return [...new Uint8Array(e)].map((e) => e.toString(16).padStart(2, "0")).join("");
}
async function u(e) {
	return l(await crypto.subtle.digest("SHA-256", e));
}
async function d(e) {
	let t = await new FontFace(c.family, e).load();
	document.fonts.add(t);
}
async function f({ fetcher: e = (e, t) => fetch(e, t), digest: t = u, register: n = d } = {}) {
	let r = await e(c.url, { cache: "force-cache" });
	if (!r.ok) throw Error("固定画布字体不可用");
	let i = await r.arrayBuffer();
	if (await t(i) !== c.sha256) throw Error("固定画布字体校验失败");
	await n(i);
}
var p = {
	top: 0,
	middle: -.5,
	bottom: -1,
	alphabetic: -.8
};
function m(e, t, n) {
	if (!Number.isInteger(t) || t <= 0) throw Error("画布字号必须为正整数");
	return e + t * p[n];
}
function h(e) {
	for (let t of e) {
		let e = t.codePointAt(0);
		if (e === void 0 || e > 65535 || e === 8205 || e >= 65024 && e <= 65039 || /\p{Mark}/u.test(t)) return !1;
	}
	return !0;
}
function g(e, t) {
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
function _(e, t) {
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
var v = /* @__PURE__ */ new Set([
	"main_output",
	"sku_output",
	"detail_output"
]), y = [
	"product_asset",
	"cutout_asset",
	"prompt",
	"composition",
	"text_layer",
	"output_image"
];
function b(e, t, n) {
	switch (n) {
		case "product_asset": return (e === "product_source" || e === "sku_reference") && t === "auto_cutout";
		case "cutout_asset": return e === "auto_cutout" && t === "model_generation";
		case "prompt": return e === "prompt" && t === "model_generation";
		case "background_image": return !1;
		case "composition": return e === "composition_group" && v.has(t);
		case "text_layer": return e === "text_layer" && v.has(t);
		case "output_image": return e === "model_generation" && v.has(t);
	}
}
function x(e, t) {
	return y.filter((n) => b(e, t, n));
}
function S(e, t, n, r) {
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
var C = 500, w = 1e3, T = 4e3, E = 1e5, ee = [
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
], D = [
	"main",
	"sku",
	"detail"
], O = {
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
}, te = /* @__PURE__ */ new Set([
	"generationhistory",
	"history",
	"objects",
	"resultassetids",
	"resultversions",
	"version",
	"versionhistory",
	"versions"
]), ne = /\b[A-Za-z][A-Za-z0-9+.-]*:\/\//, re = /^[A-Za-z]:[\\/]/, ie = class extends Error {
	constructor(e) {
		super(e), this.name = "ProjectValidationError";
	}
};
function k(e, t) {
	throw new ie(`${t} at ${e}`);
}
function A(e, t) {
	if (!(e === null || typeof e == "boolean")) {
		if (typeof e == "number") {
			Number.isFinite(e) || k(t, "JSON numbers must be finite");
			return;
		}
		if (typeof e == "string") {
			let n = e.trim(), r = n.toLowerCase();
			r.startsWith("data:") && k(t, "data URLs are forbidden"), (ne.test(n) || r.startsWith("//") || r.startsWith("blob:") || r.startsWith("file:")) && k(t, "remote URLs are forbidden"), (n.startsWith("/") || n.startsWith("\\") || re.test(n)) && k(t, "absolute paths are forbidden");
			return;
		}
		if (Array.isArray(e)) {
			e.forEach((e, n) => A(e, `${t}[${n}]`));
			return;
		}
		(typeof e != "object" || e === void 0) && k(t, "non-JSON value is forbidden");
		for (let [n, r] of Object.entries(e)) te.has(n.toLowerCase()) && k(t, `Fabric marker ${JSON.stringify(n)} is forbidden`), A(r, `${t}.${n}`);
	}
}
function j(e, t) {
	return (typeof e != "object" || !e || Array.isArray(e)) && k(t, "expected an object"), e;
}
function M(e, t, n) {
	let r = new Set(t);
	for (let t of Object.keys(e)) r.has(t) || k(n, `unknown key ${JSON.stringify(t)}`);
	for (let r of t) Object.hasOwn(e, r) || k(n, `missing key ${JSON.stringify(r)}`);
}
function ae(e, t, n) {
	typeof e != "string" && k(t, "expected a string");
	let r = n.trim === !0 ? e.trim() : e;
	return n.allowEmpty !== !0 && r.length === 0 && k(t, "string must not be empty"), r.length > n.maxLength && k(t, `string exceeds ${n.maxLength} characters`), r;
}
function N(e, t) {
	return ae(e, t, {
		maxLength: 200,
		trim: !0
	});
}
function P(e, t) {
	return e === null ? null : N(e, t);
}
function F(e, t) {
	return typeof e != "boolean" && k(t, "expected a boolean"), e;
}
function I(e, t, n = {}) {
	return (typeof e != "number" || !Number.isFinite(e)) && k(t, "expected a finite number"), n.min !== void 0 && e < n.min && k(t, `number must be at least ${n.min}`), n.exclusiveMin !== void 0 && e <= n.exclusiveMin && k(t, `number must be greater than ${n.exclusiveMin}`), n.max !== void 0 && e > n.max && k(t, `number must be at most ${n.max}`), e;
}
function L(e, t, n = {}) {
	let r = I(e, t, n);
	return Number.isInteger(r) || k(t, "expected an integer"), r;
}
function oe(e, t, n = {}) {
	return e === null ? null : L(e, t, n);
}
function se(e, t, n) {
	return (typeof e != "string" || !t.includes(e)) && k(n, `expected one of ${t.join(", ")}`), e;
}
function R(e, t, n, r) {
	return Array.isArray(e) || k(t, "expected an array"), e.length > r && k(t, `array exceeds ${r} items`), e.map((e, r) => n(e, `${t}[${r}]`));
}
function ce(e, t, n) {
	let r = /* @__PURE__ */ new Set();
	for (let i of e) r.has(i.id) && k(n, `duplicate ${t} id ${JSON.stringify(i.id)}`), r.add(i.id);
}
function le(e, t) {
	if (e === null || typeof e == "boolean" || typeof e == "string") return e;
	if (typeof e == "number") return Number.isFinite(e) || k(t, "JSON numbers must be finite"), e;
	if (Array.isArray(e)) return e.map((e, n) => le(e, `${t}[${n}]`));
	let n = j(e, t), r = {};
	for (let [e, i] of Object.entries(n)) r[e] = le(i, `${t}.${e}`);
	return r;
}
function ue(e, t) {
	let n = le(e, t);
	return (n === null || Array.isArray(n) || typeof n != "object") && k(t, "expected a JSON object"), n;
}
function de(e, t) {
	let n = j(e, t);
	M(n, [
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
	let r = se(n.kind, ee, `${t}.kind`), i = n.managedBy === null ? null : se(n.managedBy, ["complete-set"], `${t}.managedBy`), a = n.prompt === null ? null : ae(n.prompt, `${t}.prompt`, {
		maxLength: T,
		allowEmpty: !0
	});
	return {
		id: N(n.id, `${t}.id`),
		kind: r,
		managedBy: i,
		skuId: P(n.skuId, `${t}.skuId`),
		assetId: P(n.assetId, `${t}.assetId`),
		modelProfileId: P(n.modelProfileId, `${t}.modelProfileId`),
		prompt: a,
		compositionGroupId: P(n.compositionGroupId, `${t}.compositionGroupId`),
		textSnapshotId: P(n.textSnapshotId, `${t}.textSnapshotId`),
		outputBoardId: P(n.outputBoardId, `${t}.outputBoardId`),
		parameters: ue(n.parameters, `${t}.parameters`)
	};
}
function fe(e, t = "edge") {
	let n = j(e, t);
	M(n, [
		"id",
		"kind",
		"sourceNodeId",
		"sourcePort",
		"targetNodeId",
		"targetPort",
		"skuId"
	], t);
	let r = se(n.kind, Object.keys(O), `${t}.kind`), i = O[r];
	return (n.sourcePort !== i.sourcePort || n.targetPort !== i.targetPort) && k(t, `invalid ports for ${r}: ${String(n.sourcePort)} -> ${String(n.targetPort)}`), {
		id: N(n.id, `${t}.id`),
		kind: r,
		sourceNodeId: N(n.sourceNodeId, `${t}.sourceNodeId`),
		sourcePort: i.sourcePort,
		targetNodeId: N(n.targetNodeId, `${t}.targetNodeId`),
		targetPort: i.targetPort,
		skuId: P(n.skuId, `${t}.skuId`)
	};
}
function pe(e, t) {
	return se(e, D, t);
}
function me(e, t) {
	let n = j(e, t);
	return M(n, [
		"id",
		"outputNodeId",
		"outputType",
		"skuId",
		"sortOrder",
		"selectedResultAssetId"
	], t), {
		id: N(n.id, `${t}.id`),
		outputNodeId: N(n.outputNodeId, `${t}.outputNodeId`),
		outputType: pe(n.outputType, `${t}.outputType`),
		skuId: P(n.skuId, `${t}.skuId`),
		sortOrder: L(n.sortOrder, `${t}.sortOrder`, { min: 0 }),
		selectedResultAssetId: P(n.selectedResultAssetId, `${t}.selectedResultAssetId`)
	};
}
function he(e, t) {
	let n = j(e, t);
	return M(n, [
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
		outputType: pe(n.outputType, `${t}.outputType`),
		skuId: P(n.skuId, `${t}.skuId`),
		quantity: oe(n.quantity, `${t}.quantity`, {
			min: 1,
			max: 500
		}),
		aspectRatio: n.aspectRatio === null ? null : ae(n.aspectRatio, `${t}.aspectRatio`, {
			maxLength: 40,
			trim: !0
		}),
		width: oe(n.width, `${t}.width`, {
			min: 1,
			max: 32768
		}),
		height: oe(n.height, `${t}.height`, {
			min: 1,
			max: 32768
		}),
		prompt: ae(n.prompt, `${t}.prompt`, {
			maxLength: T,
			allowEmpty: !0
		}),
		modelProfileId: P(n.modelProfileId, `${t}.modelProfileId`),
		modelParameters: ue(n.modelParameters, `${t}.modelParameters`),
		referenceAssetId: P(n.referenceAssetId, `${t}.referenceAssetId`),
		compositionGroupId: P(n.compositionGroupId, `${t}.compositionGroupId`)
	};
}
function ge(e, t) {
	let n = j(e, t);
	M(n, ["selectedOutputTypes", "outputs"], t);
	let r = R(n.selectedOutputTypes, `${t}.selectedOutputTypes`, pe, 3);
	return new Set(r).size !== r.length && k(`${t}.selectedOutputTypes`, "selected output types must be unique"), {
		selectedOutputTypes: r,
		outputs: R(n.outputs, `${t}.outputs`, he, 500)
	};
}
function _e(e, t) {
	let n = j(e, t);
	M(n, [
		"slot",
		"anchor",
		"baseline",
		"relativeProductFraction",
		"contain",
		"safeArea",
		"rotation"
	], t);
	let r = j(n.slot, `${t}.slot`);
	M(r, [
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
	(i.x + i.width > 1 || i.y + i.height > 1) && k(`${t}.slot`, "normalized slot must remain inside the board");
	let a = j(n.anchor, `${t}.anchor`);
	M(a, ["x", "y"], `${t}.anchor`);
	let o = j(n.safeArea, `${t}.safeArea`);
	M(o, [
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
	return (s.left + s.right >= 1 || s.top + s.bottom >= 1) && k(`${t}.safeArea`, "safe area insets must leave a visible board region"), n.contain !== !0 && k(`${t}.contain`, "contain must be true"), {
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
function ve(t, n) {
	let r = j(t, n), i = r.layout === void 0, a = {
		...r,
		layout: r.layout ?? structuredClone(e)
	};
	M(a, [
		"id",
		"skuIds",
		"productLayerIds",
		"layoutHash",
		"layout"
	], n);
	let s = _e(a.layout, `${n}.layout`), c = i ? o(s) : ae(a.layoutHash, `${n}.layoutHash`, { maxLength: 200 });
	return {
		id: N(a.id, `${n}.id`),
		skuIds: R(a.skuIds, `${n}.skuIds`, N, 500),
		productLayerIds: R(a.productLayerIds, `${n}.productLayerIds`, N, 500),
		layoutHash: c,
		layout: s
	};
}
function ye(e, t) {
	let n = j(e, t);
	M(n, [
		"nodes",
		"edges",
		"outputBoards",
		"mode",
		"advancedCustomized",
		"completeSet",
		"compositionGroups"
	], t);
	let r = R(n.nodes, `${t}.nodes`, de, C), i = R(n.edges, `${t}.edges`, fe, w), a = R(n.outputBoards, `${t}.outputBoards`, me, 500), o = R(n.compositionGroups, `${t}.compositionGroups`, ve, 500);
	return ce(r, "node", `${t}.nodes`), ce(i, "edge", `${t}.edges`), ce(a, "output board", `${t}.outputBoards`), ce(o, "composition group", `${t}.compositionGroups`), {
		nodes: r,
		edges: i,
		outputBoards: a,
		mode: se(n.mode, ["complete-set", "advanced"], `${t}.mode`),
		advancedCustomized: F(n.advancedCustomized, `${t}.advancedCustomized`),
		completeSet: ge(n.completeSet, `${t}.completeSet`),
		compositionGroups: o
	};
}
function be(e, t) {
	let n = j(e, t);
	return M(n, ["x", "y"], t), {
		x: I(n.x, `${t}.x`),
		y: I(n.y, `${t}.y`)
	};
}
function xe(e, t) {
	let n = j(e, t);
	return M(n, [
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
function Se(e, t) {
	let n = {
		...j(e, t),
		allowOpaqueFallback: j(e, t).allowOpaqueFallback ?? !1
	};
	return M(n, [
		"id",
		"sourceAssetId",
		"renderAssetId",
		"allowOpaqueFallback",
		"skuId",
		"compositionGroupId",
		"transformId",
		"locked"
	], t), {
		id: N(n.id, `${t}.id`),
		sourceAssetId: N(n.sourceAssetId, `${t}.sourceAssetId`),
		renderAssetId: N(n.renderAssetId, `${t}.renderAssetId`),
		allowOpaqueFallback: F(n.allowOpaqueFallback, `${t}.allowOpaqueFallback`),
		skuId: P(n.skuId, `${t}.skuId`),
		compositionGroupId: P(n.compositionGroupId, `${t}.compositionGroupId`),
		transformId: N(n.transformId, `${t}.transformId`),
		locked: F(n.locked, `${t}.locked`)
	};
}
function Ce(e, t) {
	let n = j(e, t);
	M(n, [
		"text",
		"x",
		"y",
		"width"
	], t);
	let r = ae(n.text, `${t}.text`, {
		maxLength: E,
		allowEmpty: !0
	});
	return (r.includes("\r") || r.includes("\n")) && k(`${t}.text`, "must not contain CR or LF"), {
		text: r,
		x: I(n.x, `${t}.x`),
		y: I(n.y, `${t}.y`),
		width: I(n.width, `${t}.width`, { min: 0 })
	};
}
function we(e, t) {
	let n = j(e, t);
	M(n, [
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
	let r = R(n.lines, `${t}.lines`, Ce, 1e4);
	r.reduce((e, t) => e + t.text.length, 0) > E && k(`${t}.lines`, `text lines exceed ${E} characters`);
	let i = ae(n.content, `${t}.content`, {
		maxLength: E,
		allowEmpty: !0
	}), a = L(n.fontSize, `${t}.fontSize`, {
		min: 1,
		max: 1e4
	}), o = I(n.letterSpacing, `${t}.letterSpacing`, {
		min: -1e4,
		max: 1e4
	});
	return (i !== r.map((e) => e.text).join("\n") || i.length === 0 && r.length > 0) && k(`${t}.content`, "must match canonical explicit lines"), o !== 0 && r.some((e) => !h(e.text)) && k(`${t}.letterSpacing`, "supports only independent BMP code points"), {
		id: N(n.id, `${t}.id`),
		nodeId: N(n.nodeId, `${t}.nodeId`),
		content: i,
		fontAssetId: n.fontAssetId === null ? null : k(`${t}.fontAssetId`, "must be null for the pinned font"),
		fontFamily: n.fontFamily === "Noto Sans CJK SC" ? n.fontFamily : k(`${t}.fontFamily`, "must use the pinned Canvas font"),
		fontVersion: n.fontVersion === "sha256:2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b" ? n.fontVersion : k(`${t}.fontVersion`, "must match the pinned Canvas font"),
		boxWidth: I(n.boxWidth, `${t}.boxWidth`, { min: 0 }),
		lines: r,
		fontSize: a,
		color: (() => {
			let e = ae(n.color, `${t}.color`, {
				maxLength: 7,
				allowEmpty: !1
			});
			return /^#[0-9a-fA-F]{6}$/.test(e) ? e : k(`${t}.color`, "must be a six-digit hex color");
		})(),
		letterSpacing: o,
		lineHeight: I(n.lineHeight, `${t}.lineHeight`, {
			exclusiveMin: 0,
			max: 1e3
		}),
		align: se(n.align, [
			"left",
			"center",
			"right"
		], `${t}.align`),
		baseline: se(n.baseline, [
			"alphabetic",
			"top",
			"middle",
			"bottom"
		], `${t}.baseline`),
		zBand: se(n.zBand, ["below-product", "above-product"], `${t}.zBand`),
		sortOrder: L(n.sortOrder, `${t}.sortOrder`, {
			min: 0,
			max: 1e4
		})
	};
}
function Te(e, t) {
	let n = j(e, t);
	M(n, [
		"nodePositions",
		"objectTransforms",
		"viewport",
		"productLayers",
		"textSnapshots"
	], t);
	let r = j(n.nodePositions, `${t}.nodePositions`), i = {};
	for (let [e, n] of Object.entries(r)) i[N(e, `${t}.nodePositions key`)] = be(n, `${t}.nodePositions.${e}`);
	let a = j(n.objectTransforms, `${t}.objectTransforms`), o = {};
	for (let [e, n] of Object.entries(a)) o[N(e, `${t}.objectTransforms key`)] = xe(n, `${t}.objectTransforms.${e}`);
	let s = j(n.viewport, `${t}.viewport`);
	M(s, [
		"x",
		"y",
		"zoom"
	], `${t}.viewport`);
	let c = R(n.productLayers, `${t}.productLayers`, Se, 500), l = R(n.textSnapshots, `${t}.textSnapshots`, we, 500);
	return ce(c, "product layer", `${t}.productLayers`), ce(l, "text snapshot", `${t}.textSnapshots`), {
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
function Ee(e, t, n, r) {
	e !== null && !t.has(e) && k(n, `references unknown ${r} ${JSON.stringify(e)}`);
}
function De(e) {
	let t = new Set(e.semanticState.nodes.map((e) => e.id)), n = new Set(e.semanticState.outputBoards.map((e) => e.id)), r = new Set(e.semanticState.compositionGroups.map((e) => e.id)), i = new Set(e.layoutState.productLayers.map((e) => e.id)), a = new Set(e.layoutState.textSnapshots.map((e) => e.id)), c = new Set(Object.keys(e.layoutState.objectTransforms));
	e.semanticState.nodes.forEach((e, t) => {
		let i = `project.semanticState.nodes[${t}]`;
		Ee(e.compositionGroupId, r, `${i}.compositionGroupId`, "composition group"), Ee(e.textSnapshotId, a, `${i}.textSnapshotId`, "text snapshot"), Ee(e.outputBoardId, n, `${i}.outputBoardId`, "output board");
	}), e.semanticState.edges.forEach((n, r) => {
		let i = `project.semanticState.edges[${r}]`;
		Ee(n.sourceNodeId, t, `${i}.sourceNodeId`, "node"), Ee(n.targetNodeId, t, `${i}.targetNodeId`, "node");
		let a = e.semanticState.nodes.find((e) => e.id === n.sourceNodeId), o = e.semanticState.nodes.find((e) => e.id === n.targetNodeId);
		(a === void 0 || o === void 0 || !b(a.kind, o.kind, n.kind)) && k(i, "incompatible node connection");
	}), e.semanticState.nodes.forEach((t, n) => {
		if (t.kind !== "auto_cutout") return;
		let r = e.semanticState.edges.filter((e) => e.kind === "product_asset" && e.targetNodeId === t.id);
		r.length !== 1 && k(`project.semanticState.nodes[${n}]`, "auto cutout must retain its product route");
		let i = r[0], a = e.semanticState.nodes.find((e) => e.id === i.sourceNodeId);
		(t.id !== "main-product-cutout" || t.skuId !== null || t.assetId === null || a?.id !== "main-product-source" || a.kind !== "product_source" || a.skuId !== null || a.assetId === null) && k(`project.semanticState.nodes[${n}]`, "auto cutout must use the canonical system product pipeline");
		let o = e.layoutState.productLayers.filter((e) => e.skuId === null && e.locked);
		(o.length !== 1 || a.assetId !== o[0]?.sourceAssetId || t.assetId !== o[0]?.renderAssetId) && k(`project.semanticState.nodes[${n}]`, "auto cutout asset binding must match the locked product layer");
	}), e.semanticState.outputBoards.forEach((e, n) => {
		Ee(e.outputNodeId, t, `project.semanticState.outputBoards[${n}].outputNodeId`, "node");
	}), e.semanticState.completeSet.outputs.forEach((e, t) => {
		Ee(e.compositionGroupId, r, `project.semanticState.completeSet.outputs[${t}].compositionGroupId`, "composition group");
	}), e.semanticState.compositionGroups.forEach((t, n) => {
		/^sha256:[0-9a-f]{64}$/.test(t.layoutHash) || k(`project.semanticState.compositionGroups[${n}].layoutHash`, "expected sha256:<lowercase hex>"), t.layoutHash !== o(t.layout) && k(`project.semanticState.compositionGroups[${n}].layoutHash`, "layout hash does not match shared composition layout"), new Set(t.skuIds).size !== t.skuIds.length && k(`project.semanticState.compositionGroups[${n}].skuIds`, "duplicate SKU id"), new Set(t.productLayerIds).size !== t.productLayerIds.length && k(`project.semanticState.compositionGroups[${n}].productLayerIds`, "duplicate product layer id"), t.productLayerIds.forEach((e, t) => {
			Ee(e, i, `project.semanticState.compositionGroups[${n}].productLayerIds[${t}]`, "product layer");
		});
		let r = e.layoutState.productLayers.filter((e) => e.compositionGroupId === t.id);
		(r.length !== t.productLayerIds.length || r.some((e) => !t.productLayerIds.includes(e.id))) && k(`project.semanticState.compositionGroups[${n}]`, "composition group product membership is inconsistent or references unknown group");
		let a = r.flatMap((e) => e.skuId === null ? [] : [e.skuId]).sort();
		JSON.stringify(a) !== JSON.stringify([...t.skuIds].sort()) && k(`project.semanticState.compositionGroups[${n}].skuIds`, "composition group SKU membership is inconsistent");
		let c = s(t.layout);
		for (let t of r) {
			t.locked || k(`project.layoutState.productLayers.${t.id}.locked`, "composition product must remain locked"), t.allowOpaqueFallback && t.renderAssetId !== t.sourceAssetId && k(`project.layoutState.productLayers.${t.id}.allowOpaqueFallback`, "opaque fallback must render its working source");
			let n = e.layoutState.objectTransforms[t.transformId];
			(n === void 0 || Math.abs(n.x - c.x) > 1e-6 || Math.abs(n.y - c.y) > 1e-6 || Math.abs(n.scale - c.scale) > 1e-6 || Math.abs(n.rotation - c.rotation) > 1e-6) && k(`project.layoutState.productLayers.${t.id}.transformId`, "composition projection does not match its shared layout or references unknown transform");
		}
	}), e.layoutState.productLayers.forEach((e, t) => {
		let n = `project.layoutState.productLayers[${t}]`;
		Ee(e.compositionGroupId, r, `${n}.compositionGroupId`, "composition group"), Ee(e.transformId, c, `${n}.transformId`, "transform");
	}), e.layoutState.textSnapshots.forEach((e, n) => {
		Ee(e.nodeId, t, `project.layoutState.textSnapshots[${n}].nodeId`, "node");
	});
	for (let n of Object.keys(e.layoutState.nodePositions)) Ee(n, t, `project.layoutState.nodePositions.${n}`, "node");
}
function Oe(t, n) {
	for (let r of t.semanticState.compositionGroups) {
		if (!n.has(r.id)) continue;
		let i = t.layoutState.productLayers.find((e) => r.productLayerIds.includes(e.id)), a = i === void 0 ? void 0 : t.layoutState.objectTransforms[i.transformId], s = structuredClone(e);
		if (a !== void 0) {
			if (a.x > 0 && a.x < 1) {
				let e = Math.min(.8, 2 * a.x, 2 * (1 - a.x));
				s.slot.width = e, s.slot.x = a.x - e * .5;
			}
			s.baseline = a.y, s.relativeProductFraction = a.scale, s.rotation = a.rotation;
		}
		r.layout = s, r.layoutHash = o(s);
	}
}
function ke(e) {
	A(e, "project");
	let t = j(e, "project");
	M(t, [
		"schemaVersion",
		"semanticState",
		"layoutState"
	], "project");
	let n = L(t.schemaVersion, "project.schemaVersion");
	n !== 1 && k("project.schemaVersion", `unsupported schema version ${n}`);
	let r = j(t.semanticState, "project.semanticState"), i = Array.isArray(r.compositionGroups) ? r.compositionGroups : [], a = new Set(i.flatMap((e) => {
		if (typeof e != "object" || !e || Array.isArray(e)) return [];
		let t = e;
		return t.layout === void 0 && typeof t.id == "string" ? [t.id] : [];
	})), o = {
		schemaVersion: 1,
		semanticState: ye(t.semanticState, "project.semanticState"),
		layoutState: Te(t.layoutState, "project.layoutState")
	};
	Oe(o, a);
	let s = /* @__PURE__ */ new Set();
	for (let e of o.semanticState.nodes) e.kind === "product_source" && e.assetId !== null && e.parameters.allowOpaqueFallback === !0 && (s.add(e.assetId), delete e.parameters.allowOpaqueFallback);
	for (let e of o.layoutState.productLayers) e.skuId === null && s.has(e.sourceAssetId) && (e.allowOpaqueFallback = !0);
	return De(o), o;
}
function Ae(e, t) {
	if (e === null || typeof e == "boolean" || typeof e == "string") return JSON.stringify(e);
	if (typeof e == "number") return Number.isFinite(e) || k(t, "JSON numbers must be finite"), JSON.stringify(e);
	if (Array.isArray(e)) return `[${e.map((e, n) => Ae(e, `${t}[${n}]`)).join(",")}]`;
	let n = j(e, t);
	return `{${Object.keys(n).sort().map((e) => `${JSON.stringify(e)}:${Ae(n[e], `${t}.${e}`)}`).join(",")}}`;
}
function je(e) {
	return Ae(ke(e), "project");
}
//#endregion
//#region frontend/canvas/src/api/client.ts
function Me(e, t) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error(`${t} must be an object`);
	return e;
}
function Ne(e, t, n) {
	let r = [...t].sort(), i = Object.keys(e).sort();
	if (i.length !== r.length || i.some((e, t) => e !== r[t])) throw Error(`${n} fields do not match the Canvas contract`);
}
function Pe(e, t, n = !1) {
	if (typeof e != "string" || !n && e.length === 0) throw Error(`${t} must be ${n ? "a string" : "a non-empty string"}`);
	return e;
}
function Fe(e, t) {
	return e === null ? null : Pe(e, t, !0);
}
function Ie(e, t, n) {
	if (typeof e != "number" || !Number.isInteger(e) || e < n) throw Error(`${t} must be an integer >= ${n}`);
	return e;
}
function Le(e, t) {
	if (e !== "active" && e !== "archived" && e !== "deleting") throw Error(`${t} is not a supported project status`);
	return e;
}
function Re(e, t) {
	if (e === null || typeof e == "string" || typeof e == "boolean") return;
	if (typeof e == "number") {
		if (!Number.isFinite(e)) throw Error(`${t} must contain finite JSON numbers`);
		return;
	}
	if (Array.isArray(e)) {
		e.forEach((e, n) => Re(e, `${t}[${n}]`));
		return;
	}
	let n = Me(e, t);
	for (let [e, r] of Object.entries(n)) Re(r, `${t}.${e}`);
}
var ze = [
	"id",
	"name",
	"status",
	"schemaVersion",
	"revision",
	"createdAt",
	"updatedAt",
	"archivedAt"
];
function Be(e, t) {
	if (Ie(e.schemaVersion, `${t}.schemaVersion`, 1) !== 1) throw Error(`${t}.schemaVersion must be 1`);
	return {
		id: Pe(e.id, `${t}.id`),
		name: Pe(e.name, `${t}.name`),
		status: Le(e.status, `${t}.status`),
		schemaVersion: 1,
		revision: Ie(e.revision, `${t}.revision`, 1),
		createdAt: Fe(e.createdAt, `${t}.createdAt`),
		updatedAt: Fe(e.updatedAt, `${t}.updatedAt`),
		archivedAt: Fe(e.archivedAt, `${t}.archivedAt`)
	};
}
function Ve(e) {
	let t = Me(e, "project");
	return Ne(t, ze, "project"), Be(t, "project");
}
function He(e, t) {
	let n = Me(e, t);
	Ne(n, [
		"id",
		"projectId",
		"name",
		"sortOrder",
		"referenceAssetId",
		"prompt",
		"config"
	], t);
	let r = Me(n.config, `${t}.config`);
	return Re(r, `${t}.config`), {
		id: Pe(n.id, `${t}.id`),
		projectId: Pe(n.projectId, `${t}.projectId`),
		name: Pe(n.name, `${t}.name`),
		sortOrder: Ie(n.sortOrder, `${t}.sortOrder`, 0),
		referenceAssetId: n.referenceAssetId === null ? null : Pe(n.referenceAssetId, `${t}.referenceAssetId`),
		prompt: Pe(n.prompt, `${t}.prompt`, !0),
		config: r
	};
}
function Ue(e) {
	let t = Me(e, "snapshot");
	Ne(t, [
		"project",
		"skus",
		"revision"
	], "snapshot");
	let n = Me(t.project, "snapshot.project");
	Ne(n, [
		...ze,
		"semanticState",
		"layoutState"
	], "snapshot.project");
	let r = Be(n, "snapshot.project"), i = ke({
		schemaVersion: r.schemaVersion,
		semanticState: n.semanticState,
		layoutState: n.layoutState
	}), a = Ie(t.revision, "snapshot.revision", 1);
	if (a !== r.revision) throw Error("snapshot.revision must equal snapshot.project.revision");
	if (!Array.isArray(t.skus)) throw Error("snapshot.skus must be an array");
	let o = t.skus.map((e, t) => He(e, `snapshot.skus[${t}]`));
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
function We(e, t) {
	let n = Ue(e);
	if (n.project.id !== t) throw Error("snapshot belongs to another project");
	return n;
}
function Ge(e) {
	return {
		ok: !1,
		kind: "server",
		message: e instanceof Error ? `Invalid Canvas response: ${e.message}` : "Invalid Canvas response"
	};
}
function Ke(e) {
	return e instanceof DOMException && e.name === "AbortError" || typeof e == "object" && !!e && "name" in e && e.name === "AbortError";
}
function qe(e) {
	return {
		ok: !1,
		kind: "offline",
		message: e instanceof Error ? e.message : "Network unavailable"
	};
}
async function Je(e) {
	try {
		return await e.json();
	} catch {
		return null;
	}
}
function Ye(e, t) {
	return typeof t == "object" && t && "detail" in t && typeof t.detail == "string" ? t.detail : `Canvas request failed (${e.status})`;
}
function Xe(e, t) {
	return e.status === 409 && typeof t == "object" && t && "code" in t && t.code === "canvas_revision_conflict" && "currentRevision" in t && typeof t.currentRevision == "number" && Number.isInteger(t.currentRevision) ? {
		ok: !1,
		kind: "conflict",
		currentRevision: t.currentRevision
	} : null;
}
function Ze({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
	let n = e.replace(/\/+$/, ""), r = (e) => `${n}/projects/${encodeURIComponent(e)}`, i = async (e, n = {}) => {
		try {
			let r = await t(e, n);
			return {
				ok: !0,
				response: r,
				body: await Je(r)
			};
		} catch (e) {
			if (Ke(e)) throw e;
			return qe(e);
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
			message: Ye(n.response, n.body)
		} : n;
	}, s = async (e, t, n) => {
		let r = await i(e, t);
		if (!r.ok) return r;
		if (!r.response.ok) return Xe(r.response, r.body) ?? {
			ok: !1,
			kind: "server",
			message: Ye(r.response, r.body)
		};
		try {
			return {
				ok: !0,
				snapshot: We(r.body, n)
			};
		} catch (e) {
			return Ge(e);
		}
	};
	return {
		listProjects: async (e = {}) => {
			let t = new URLSearchParams();
			e.query !== void 0 && e.query !== "" && t.set("q", e.query), e.includeArchived !== void 0 && t.set("includeArchived", String(e.includeArchived));
			let r = t.size === 0 ? "" : `?${t.toString()}`, i = await o(`${n}/projects${r}`, { signal: e.signal });
			if (!i.ok) return i;
			try {
				let e = Me(i.value, "list response");
				if (Ne(e, ["projects"], "list response"), !Array.isArray(e.projects)) throw Error("list response.projects must be an array");
				return {
					ok: !0,
					value: e.projects.map(Ve)
				};
			} catch (e) {
				return Ge(e);
			}
		},
		createProject: async (e) => {
			let t = await o(`${n}/projects`, a("POST", { name: e }));
			if (!t.ok) return t;
			try {
				return {
					ok: !0,
					value: Ue(t.value)
				};
			} catch (e) {
				return Ge(e);
			}
		},
		getProject: async (e, t) => {
			let n = await o(r(e), { signal: t });
			if (!n.ok) return n;
			try {
				return {
					ok: !0,
					value: We(n.value, e)
				};
			} catch (e) {
				return Ge(e);
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
function Qe(e) {
	if (e === "") return null;
	try {
		return JSON.parse(e);
	} catch {
		return null;
	}
}
function $e() {
	return new DOMException("Canvas upload aborted", "AbortError");
}
function et(e = () => new XMLHttpRequest()) {
	return ({ url: t, file: n, signal: r, onProgress: i }) => new Promise((a, o) => {
		if (r?.aborted) {
			o($e());
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
				body: Qe(s.responseText)
			});
		}), s.addEventListener("error", () => {
			c(), o(/* @__PURE__ */ Error("Canvas upload network unavailable"));
		}), s.addEventListener("abort", () => {
			c(), o($e());
		}), r?.addEventListener("abort", l, { once: !0 });
		let u = new FormData();
		u.append("file", n, n.name), s.open("POST", t), s.send(u);
	});
}
function tt(e, t) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error(`${t} must be an object`);
	return e;
}
function nt(e, t, n = !1) {
	if (typeof e != "string" || !n && e.length === 0) throw Error(`${t} must be a string`);
	return e;
}
function rt(e, t) {
	return e === null ? null : nt(e, t, !0);
}
function it(e, t) {
	if (typeof e != "number" || !Number.isInteger(e) || e < 0) throw Error(`${t} must be a non-negative integer`);
	return e;
}
function at(e, t, n) {
	if (typeof e != "string" || !t.includes(e)) throw Error(`${n} is unsupported`);
	return e;
}
var ot = [
	"source",
	"working",
	"preview",
	"cutout",
	"generated_background",
	"composed",
	"export"
], st = [
	"unknown",
	"opaque",
	"transparent"
], ct = [
	"cancel_requested",
	"cancelled",
	"failed",
	"interrupted",
	"queued",
	"running",
	"succeeded"
], lt = [
	"compose",
	"cutout",
	"export"
];
function ut(e, t = "asset") {
	let n = tt(e, t);
	return {
		id: nt(n.id, `${t}.id`),
		projectId: nt(n.projectId, `${t}.projectId`),
		assetType: at(n.assetType, ot, `${t}.assetType`),
		originalFilename: nt(n.originalFilename, `${t}.originalFilename`, !0),
		mimeType: nt(n.mimeType, `${t}.mimeType`),
		byteCount: it(n.byteCount, `${t}.byteCount`),
		width: it(n.width, `${t}.width`),
		height: it(n.height, `${t}.height`),
		sha256: nt(n.sha256, `${t}.sha256`),
		sourceAssetId: rt(n.sourceAssetId, `${t}.sourceAssetId`),
		transparencyStatus: at(n.transparencyStatus, st, `${t}.transparencyStatus`),
		processorVersion: rt(n.processorVersion, `${t}.processorVersion`),
		metadata: tt(n.metadata, `${t}.metadata`)
	};
}
function dt(e, t) {
	if (e == null) return null;
	let n = tt(e, t);
	if (typeof n.retryable != "boolean") throw Error(`${t}.retryable must be a boolean`);
	return {
		code: nt(n.code, `${t}.code`),
		message: nt(n.message, `${t}.message`),
		retryable: n.retryable
	};
}
function ft(e, t = "operation") {
	let n = tt(e, t), r = n.operationType ?? n.type, i = n.safeError ?? n.error ?? null;
	return {
		id: nt(n.id, `${t}.id`),
		projectId: nt(n.projectId, `${t}.projectId`),
		operationType: at(r, lt, `${t}.operationType`),
		status: at(n.status, ct, `${t}.status`),
		attemptCount: it(n.attemptCount, `${t}.attemptCount`),
		inputAssetId: nt(n.inputAssetId, `${t}.inputAssetId`),
		outputAssetId: rt(n.outputAssetId, `${t}.outputAssetId`),
		safeError: dt(i, `${t}.safeError`)
	};
}
function pt(e, t) {
	let n = tt(e, "upload response"), r = ut(n.source, "upload response.source"), i = ut(n.working, "upload response.working"), a = ut(n.preview, "upload response.preview"), o = n.operation === null ? null : ft(n.operation, "upload response.operation");
	if (r.projectId !== t || i.projectId !== t || a.projectId !== t || o !== null && o.projectId !== t) throw Error("Canvas upload response belongs to another project");
	return {
		source: r,
		working: i,
		preview: a,
		operation: o
	};
}
function mt(e) {
	return e instanceof DOMException && e.name === "AbortError" || typeof e == "object" && !!e && "name" in e && e.name === "AbortError";
}
function ht(e) {
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
function gt(e) {
	return {
		ok: !1,
		kind: "server",
		status: e,
		message: "素材服务暂时不可用，请稍后重试"
	};
}
function _t({ apiBase: e, fetcher: t = (e, t) => fetch(e, t), uploadTransport: n = et() }) {
	let r = e.replace(/\/+$/, ""), i = async (e, n, r) => {
		let i;
		try {
			i = await t(e, n);
		} catch (e) {
			if (mt(e)) throw e;
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
		if (!i.ok) return gt(i.status);
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
				if (mt(e)) throw e;
				return {
					ok: !1,
					kind: "offline",
					message: "网络不可用，请检查连接后重试"
				};
			}
			if (o.status < 200 || o.status >= 300) return ht(o.status);
			try {
				return {
					ok: !0,
					value: pt(o.body, e)
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
			let n = tt(t, "asset list response");
			if (!Array.isArray(n.assets)) throw Error("asset list response.assets must be an array");
			let r = n.assets.map((e, t) => ut(e, `assets[${t}]`));
			if (r.some((t) => t.projectId !== e)) throw Error("asset list response belongs to another project");
			return r;
		}),
		listOperations: (e, t) => i(`${r}/projects/${encodeURIComponent(e)}/operations`, { signal: t }, (t) => {
			let n = tt(t, "operation list response");
			if (!Array.isArray(n.operations)) throw Error("operation list response.operations must be an array");
			let r = n.operations.map((e, t) => ft(e, `operations[${t}]`)).reverse();
			if (r.some((t) => t.projectId !== e)) throw Error("operation list response belongs to another project");
			return r;
		}),
		retryCutout: (e, t, n) => i(`${r}/assets/${encodeURIComponent(e)}/cutout/retry`, a("POST", { clientRequestId: t }, n), ft),
		retryOperation: (e, t) => i(`${r}/operations/${encodeURIComponent(e)}/retry`, a("POST", {}, t), ft),
		deleteAsset: (e, t) => i(`${r}/assets/${encodeURIComponent(e)}`, {
			method: "DELETE",
			signal: t
		}, (e) => {
			let t = tt(e, "delete asset response");
			if (t.status !== "deleted") throw Error("delete asset response status is invalid");
			return nt(t.assetId, "delete asset response.assetId");
		})
	};
}
//#endregion
//#region frontend/canvas/src/api/compositions.ts
function vt(e) {
	return typeof e != "object" || !e || Array.isArray(e) ? {} : e;
}
function yt(e) {
	return e instanceof DOMException && e.name === "AbortError";
}
function bt({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
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
			if (yt(e)) throw e;
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
			let e = vt(l);
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
			let t = ft(l);
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
//#region frontend/canvas/src/api/generations.ts
async function xt(e, t) {
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
function St(e, t) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error(`${t} must be an object`);
	return e;
}
function Ct(e, t, n) {
	let r = Object.keys(e).sort(), i = [...t].sort();
	if (r.length !== i.length || r.some((e, t) => e !== i[t])) throw Error(`${n} fields do not match the Canvas contract`);
}
function wt(e, t) {
	if (typeof e != "string" || e.length === 0) throw Error(`${t} must be a string`);
	return e;
}
function Tt(e, t, n = 0) {
	if (typeof e != "number" || !Number.isInteger(e) || e < n) throw Error(`${t} must be an integer`);
	return e;
}
function Et(e, t) {
	return e === null ? null : wt(e, t);
}
function Dt(e, t) {
	return typeof e == "object" && e && "detail" in e && typeof e.detail == "string" ? e.detail : t;
}
function Ot(e, t) {
	return e === 401 ? {
		ok: !1,
		kind: "unauthorized",
		message: "需要解锁付费生成功能"
	} : e === 409 || e === 503 || e === 507 ? {
		ok: !1,
		kind: "busy",
		message: Dt(t, "生成服务暂时不可用")
	} : {
		ok: !1,
		kind: "server",
		message: Dt(t, `生成请求失败 (${e})`)
	};
}
function kt(e) {
	let t = St(e, "access status");
	if (Ct(t, ["configured", "locked"], "access status"), typeof t.configured != "boolean" || typeof t.locked != "boolean") throw Error("access status fields must be boolean");
	return {
		configured: t.configured,
		locked: t.locked
	};
}
function At(e) {
	let t = St(e, "result version");
	if (Ct(t, [
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
	], "result version"), t.outputType !== "main" && t.outputType !== "sku" && t.outputType !== "detail") throw Error("result version.outputType is unsupported");
	return {
		versionId: wt(t.versionId, "result version.versionId"),
		generationId: wt(t.generationId, "result version.generationId"),
		itemId: wt(t.itemId, "result version.itemId"),
		attemptId: wt(t.attemptId, "result version.attemptId"),
		boardId: wt(t.boardId, "result version.boardId"),
		outputType: t.outputType,
		skuId: Et(t.skuId, "result version.skuId"),
		backgroundAssetId: wt(t.backgroundAssetId, "result version.backgroundAssetId"),
		backgroundPreviewAssetId: wt(t.backgroundPreviewAssetId, "result version.backgroundPreviewAssetId"),
		composedAssetId: wt(t.composedAssetId, "result version.composedAssetId"),
		composedPreviewAssetId: wt(t.composedPreviewAssetId, "result version.composedPreviewAssetId"),
		width: Tt(t.width, "result version.width", 1),
		height: Tt(t.height, "result version.height", 1),
		modelProfileId: wt(t.modelProfileId, "result version.modelProfileId"),
		modelDisplayName: wt(t.modelDisplayName, "result version.modelDisplayName"),
		modelConfigVersion: Tt(t.modelConfigVersion, "result version.modelConfigVersion", 1),
		createdAt: wt(t.createdAt, "result version.createdAt")
	};
}
function jt({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
	let n = e.replace(/\/+$/, ""), r = async (e, n) => {
		let r;
		try {
			r = await t(e, n);
		} catch (e) {
			if (e instanceof DOMException && e.name === "AbortError") throw e;
			return {
				ok: !1,
				kind: "offline",
				message: "网络不可用，请检查连接后重试"
			};
		}
		let i = null;
		try {
			i = await r.json();
		} catch {}
		return r.ok ? {
			response: r,
			body: i
		} : Ot(r.status, i);
	};
	return {
		create: async (e, t, i) => {
			let a = await r(`${n}/projects/${encodeURIComponent(e)}/generations`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					"Idempotency-Key": i
				},
				body: JSON.stringify(t)
			});
			if ("ok" in a) return a;
			try {
				return {
					ok: !0,
					value: { id: wt(St(a.body, "generation").id, "generation.id") }
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
			let e = await r(`${n}/access/status`, { method: "GET" });
			if ("ok" in e) return e;
			try {
				return {
					ok: !0,
					value: kt(e.body)
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
			let t = await r(`${n}/access/unlock`, {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ token: e })
			});
			if ("ok" in t) return t;
			try {
				return {
					ok: !0,
					value: kt(t.body)
				};
			} catch {
				return {
					ok: !1,
					kind: "server",
					message: "解锁服务返回了无效响应"
				};
			}
		},
		listResultVersions: async (e, t, i) => {
			let a = new URLSearchParams();
			t !== void 0 && a.set("boardId", t), i != null && a.set("cursor", i);
			let o = a.size === 0 ? "" : `?${a.toString()}`, s = await r(`${n}/projects/${encodeURIComponent(e)}/result-versions${o}`, { method: "GET" });
			if ("ok" in s) return s;
			try {
				let e = St(s.body, "result versions");
				if (Ct(e, ["items", "nextCursor"], "result versions"), !Array.isArray(e.items)) throw Error("result versions.items must be an array");
				return {
					ok: !0,
					value: {
						items: e.items.map(At),
						nextCursor: Et(e.nextCursor, "result versions.nextCursor")
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
//#region frontend/canvas/src/api/exports.ts
function Mt(e) {
	return typeof e == "object" && e && !Array.isArray(e) ? e : {};
}
function Nt(e) {
	let t = Mt(e).detail;
	return typeof t == "string" && t.length > 0 && t.length <= 500 ? t : "导出选项无效，请检查后重试";
}
function Pt(e) {
	return e instanceof DOMException && e.name === "AbortError";
}
function Ft({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
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
				if (Pt(e)) throw e;
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
				message: Nt(s)
			};
			if (o.status === 409) {
				let e = Mt(s).currentRevision;
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
				let t = ft(s, "export operation");
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
var It = [
	"project.created",
	"project.updated",
	"project.state_saved",
	"project.archived",
	"project.restored",
	"project.deleting",
	"sku.created",
	"sku.updated",
	"sku.deleted"
], Lt = ["asset.uploaded", "asset.deleted"], Rt = [
	"operation.queued",
	"operation.retried",
	"operation.running",
	"operation.recovered",
	"operation.released",
	"operation.succeeded",
	"operation.failed",
	"operation.interrupted"
], zt = [
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
	...It,
	...Lt,
	...Rt,
	...zt
];
function Bt(e) {
	return e.type === "snapshot" || "revision" in e;
}
function Vt(e, t) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error(`${t} must be an object`);
	return e;
}
function Ht(e, t, n) {
	let r = Object.keys(e).sort(), i = [...t].sort();
	if (r.length !== i.length || r.some((e, t) => e !== i[t])) throw Error(`${n} fields do not match the Canvas event contract`);
}
function Ut(e, t, n, r) {
	if (t.some((t) => !(t in e)) || Object.keys(e).some((e) => !n.includes(e))) throw Error(`${r} fields do not match the Canvas event contract`);
}
function z(e, t) {
	if (typeof e != "string" || e.length === 0) throw Error(`${t} must be a non-empty string`);
	return e;
}
function Wt(e, t) {
	return e === null ? null : z(e, t);
}
function Gt(e) {
	if (typeof e != "number" || !Number.isInteger(e) || e < 1) throw Error("Canvas event revision must be a positive integer");
	return e;
}
function B(e, t) {
	if (typeof e != "number" || !Number.isInteger(e) || e < 0) throw Error(`${t} must be a non-negative integer`);
	return e;
}
function Kt(e) {
	switch (e) {
		case "project.archived": return "archived";
		case "project.deleting": return "deleting";
		case "sku.deleted": return "deleted";
		default: return "active";
	}
}
function qt(e, t, n) {
	let r = Vt(t, `event ${e}`), i = e.startsWith("sku."), a = e === "project.state_saved";
	if (Ht(r, [
		"projectId",
		"revision",
		"status",
		...i ? ["skuId"] : [],
		...a ? ["summary"] : []
	], `event ${e}`), r.projectId !== n) throw Error(`event ${e} belongs to another project`);
	let o = Kt(e);
	if (r.status !== o) throw Error(`event ${e} has an invalid status`);
	let s = {
		type: e,
		projectId: n,
		revision: Gt(r.revision),
		status: o
	};
	if (i && (s.skuId = z(r.skuId, `event ${e}.skuId`)), a) {
		let t = Vt(r.summary, `event ${e}.summary`);
		Ht(t, [
			"nodeCount",
			"edgeCount",
			"outputBoardCount"
		], `event ${e}.summary`), s.summary = {
			nodeCount: B(t.nodeCount, `event ${e}.summary.nodeCount`),
			edgeCount: B(t.edgeCount, `event ${e}.summary.edgeCount`),
			outputBoardCount: B(t.outputBoardCount, `event ${e}.summary.outputBoardCount`)
		};
	}
	return s;
}
function Jt(e, t, n) {
	let r = Vt(t, `event ${e}`);
	if (e === "asset.uploaded") {
		if (Ht(r, [
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
			sourceAssetId: z(r.sourceAssetId, `event ${e}.sourceAssetId`),
			workingAssetId: z(r.workingAssetId, `event ${e}.workingAssetId`),
			previewAssetId: z(r.previewAssetId, `event ${e}.previewAssetId`),
			transparencyStatus: r.transparencyStatus
		};
	}
	if (Ht(r, [
		"projectId",
		"assetId",
		"status"
	], `event ${e}`), r.projectId !== n || r.status !== "deleted") throw Error(`event ${e} has an invalid owner or status`);
	return {
		type: e,
		projectId: n,
		assetId: z(r.assetId, `event ${e}.assetId`),
		status: "deleted"
	};
}
var Yt = [
	"compose",
	"cutout",
	"export"
], Xt = [
	"cancel_requested",
	"cancelled",
	"failed",
	"interrupted",
	"queued",
	"running",
	"succeeded"
];
function Zt(e) {
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
function Qt(e, t) {
	let n = Vt(e, t);
	if (Ht(n, [
		"code",
		"message",
		"retryable"
	], t), typeof n.retryable != "boolean") throw Error(`${t}.retryable must be a boolean`);
	return {
		code: z(n.code, `${t}.code`),
		message: z(n.message, `${t}.message`),
		retryable: n.retryable
	};
}
function $t(e, t, n) {
	let r = Vt(t, `event ${e}`), i = [
		"operationId",
		"operationType",
		"status"
	];
	Ut(r, i, [
		...i,
		"attemptCount",
		"inputAssetId",
		"outputAssetId",
		"safeError",
		"clientRequestFingerprint",
		"reason"
	], `event ${e}`);
	let a = Zt(e);
	if (r.status !== a) throw Error(`event ${e}.status is invalid`);
	if (typeof r.operationType != "string" || !Yt.includes(r.operationType)) throw Error(`event ${e}.operationType is invalid`);
	if (typeof r.status != "string" || !Xt.includes(r.status)) throw Error(`event ${e}.status is invalid`);
	let o = {
		id: z(r.operationId, `event ${e}.operationId`),
		projectId: n,
		operationType: r.operationType,
		status: r.status
	};
	return r.attemptCount !== void 0 && (o.attemptCount = B(r.attemptCount, `event ${e}.attemptCount`)), r.inputAssetId !== void 0 && (o.inputAssetId = z(r.inputAssetId, `event ${e}.inputAssetId`)), r.outputAssetId !== void 0 && (o.outputAssetId = z(r.outputAssetId, `event ${e}.outputAssetId`)), r.safeError !== void 0 && (o.safeError = Qt(r.safeError, `event ${e}.safeError`)), {
		type: e,
		projectId: n,
		operation: o
	};
}
function en(e, t, n) {
	let r = Vt(t, `event ${e}`), i = [
		"generationId",
		"generationStatus",
		"totalItems",
		"succeededItems",
		"failedItems",
		"cancelledItems",
		"unknownItems",
		"safeStorageBlockReason"
	];
	Ut(r, i, [
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
	let a = (e, t) => e === null ? null : z(e, t), o = {
		id: z(r.generationId, `event ${e}.generationId`),
		status: z(r.generationStatus, `event ${e}.generationStatus`),
		totalItems: B(r.totalItems, `event ${e}.totalItems`),
		succeededItems: B(r.succeededItems, `event ${e}.succeededItems`),
		failedItems: B(r.failedItems, `event ${e}.failedItems`),
		cancelledItems: B(r.cancelledItems, `event ${e}.cancelledItems`),
		unknownItems: B(r.unknownItems, `event ${e}.unknownItems`),
		safeStorageBlockReason: a(r.safeStorageBlockReason, `event ${e}.safeStorageBlockReason`)
	};
	return r.itemId !== void 0 && (o.itemId = z(r.itemId, `event ${e}.itemId`)), r.itemStatus !== void 0 && (o.itemStatus = z(r.itemStatus, `event ${e}.itemStatus`)), r.attemptId !== void 0 && (o.attemptId = z(r.attemptId, `event ${e}.attemptId`)), r.safeErrorSummary !== void 0 && (o.safeErrorSummary = a(r.safeErrorSummary, `event ${e}.safeErrorSummary`)), {
		type: e,
		projectId: n,
		generation: o
	};
}
function tn(e, t) {
	return e === null ? null : z(e, t);
}
function nn(e) {
	let t = Vt(e, "snapshot generation");
	if (Ht(t, [
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
		let t = Vt(e, "snapshot generation item");
		Ht(t, [
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
		], "snapshot generation item"), z(t.id, "snapshot generation item.id"), B(t.ordinal, "snapshot generation item.ordinal"), z(t.outputType, "snapshot generation item.outputType"), z(t.boardId, "snapshot generation item.boardId"), z(t.nodeId, "snapshot generation item.nodeId"), z(t.status, "snapshot generation item.status"), B(t.attemptCount, "snapshot generation item.attemptCount"), Wt(t.latestBackgroundAssetId, "snapshot generation item.latestBackgroundAssetId"), Wt(t.latestComposedAssetId, "snapshot generation item.latestComposedAssetId"), Wt(t.safeErrorCode, "snapshot generation item.safeErrorCode"), Wt(t.safeErrorSummary, "snapshot generation item.safeErrorSummary"), t.latestAttempt !== null && Vt(t.latestAttempt, "snapshot generation item.latestAttempt");
	}
	return tn(t.createdAt, "snapshot generation.createdAt"), tn(t.updatedAt, "snapshot generation.updatedAt"), tn(t.completedAt, "snapshot generation.completedAt"), {
		id: z(t.id, "snapshot generation.id"),
		status: z(t.status, "snapshot generation.status"),
		totalItems: B(t.totalItems, "snapshot generation.totalItems"),
		succeededItems: B(t.succeededItems, "snapshot generation.succeededItems"),
		failedItems: B(t.failedItems, "snapshot generation.failedItems"),
		cancelledItems: B(t.cancelledItems, "snapshot generation.cancelledItems"),
		unknownItems: B(t.unknownItems, "snapshot generation.unknownItems"),
		safeStorageBlockReason: Wt(t.safeStorageBlockReason, "snapshot generation.safeStorageBlockReason")
	};
}
function rn(e, t) {
	let n = Vt(e, "snapshot event"), r = n.operations ?? [], i = n.generations;
	Ut(n, [
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
	let a = Ue({
		project: n.project,
		skus: n.skus,
		revision: n.revision
	});
	if (a.project.id !== t) throw Error("snapshot event belongs to another project");
	if (!Array.isArray(r)) throw Error("snapshot event.operations must be an array");
	let o = r.map((e, t) => ft(e, `snapshot event.operations[${t}]`));
	if (o.some((e) => e.projectId !== t)) throw Error("snapshot operation belongs to another project");
	if (i !== void 0 && !Array.isArray(i)) throw Error("snapshot event.generations must be an array");
	let s = i === void 0 ? void 0 : i.map(nn);
	return {
		type: "snapshot",
		snapshot: a,
		operations: o,
		...s === void 0 ? {} : { generations: s }
	};
}
function an({ apiBase: e, projectId: t, onEvent: n, onError: r, eventSourceFactory: i = (e) => new EventSource(e) }) {
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
	for (let e of It) c(e, (n) => qt(e, n, t));
	for (let e of Lt) c(e, (n) => Jt(e, n, t));
	for (let e of Rt) c(e, (n) => $t(e, n, t));
	for (let e of zt) c(e, (n) => en(e, n, t));
	c("snapshot", (e) => rn(e, t));
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
function on(e) {
	return e instanceof DOMException && e.name === "AbortError" || typeof e == "object" && !!e && "name" in e && e.name === "AbortError";
}
function sn(e) {
	return typeof e == "object" && e && "code" in e && e.code === "canvas_revision_conflict" && "currentRevision" in e && typeof e.currentRevision == "number" && Number.isInteger(e.currentRevision) ? {
		ok: !1,
		kind: "conflict",
		currentRevision: e.currentRevision
	} : null;
}
function cn({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
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
			if (on(e)) throw e;
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
		if (!a.ok) return sn(o) ?? {
			ok: !1,
			kind: "server",
			message: `SKU 请求失败 (${a.status})`
		};
		let s;
		try {
			if (s = Ue(o), s.project.id !== i) throw Error("SKU response belongs to another project");
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
//#region frontend/canvas/src/api/providers.ts
function ln(e, t) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error(`${t} must be an object`);
	return e;
}
function un(e, t, n) {
	let r = Object.keys(e).sort(), i = [...t].sort();
	if (r.length !== i.length || r.some((e, t) => e !== i[t])) throw Error(`${n} fields do not match the Canvas contract`);
}
function V(e, t) {
	if (typeof e != "string" || e.length === 0) throw Error(`${t} must be a string`);
	return e;
}
function dn(e, t) {
	return e === null ? null : V(e, t);
}
function fn(e, t, n = 0) {
	if (typeof e != "number" || !Number.isInteger(e) || e < n) throw Error(`${t} must be an integer >= ${n}`);
	return e;
}
function pn(e, t) {
	return e === null ? null : fn(e, t);
}
function mn(e, t) {
	if (e === "available" || e === "disabled" || e === "missing_credential" || e === "invalid_configuration" || e === "unsupported_local_reference") return e;
	throw Error(`${t} is unsupported`);
}
function hn(e, t) {
	if (!Array.isArray(e) || e.some((e) => typeof e != "string" || e.length === 0)) throw Error(`${t} must be a string array`);
	return [...e];
}
function gn(e, t) {
	return e === null ? null : ln(e, t);
}
function _n(e, t) {
	let n = ln(e, "model.capabilities");
	un(n, [
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
		allowedRatios: hn(n.allowed_ratios, "model.capabilities.allowed_ratios"),
		allowedSizes: hn(n.allowed_sizes, "model.capabilities.allowed_sizes"),
		minWidth: pn(n.min_width, "model.capabilities.min_width"),
		maxWidth: pn(n.max_width, "model.capabilities.max_width"),
		minHeight: pn(n.min_height, "model.capabilities.min_height"),
		maxHeight: pn(n.max_height, "model.capabilities.max_height"),
		maxQuantity: fn(n.max_quantity, "model.capabilities.max_quantity", 1),
		maxReferenceImages: fn(n.max_reference_images, "model.capabilities.max_reference_images", 0),
		referenceTransfer: i,
		protocol: a,
		supportsCancel: r(n.supports_cancel, "model.capabilities.supports_cancel"),
		supportsIdempotency: r(n.supports_idempotency, "model.capabilities.supports_idempotency"),
		supportsIdempotencyLookup: r(n.supports_idempotency_lookup, "model.capabilities.supports_idempotency_lookup"),
		concurrencyLimit: fn(n.concurrency_limit, "model.capabilities.concurrency_limit", 1),
		priceMetadata: t
	};
}
function vn(e) {
	let t = ln(e, "provider");
	if (un(t, [
		"id",
		"name",
		"enabled",
		"availability",
		"availabilityReason",
		"configVersion"
	], "provider"), typeof t.enabled != "boolean") throw Error("provider.enabled must be boolean");
	return {
		id: V(t.id, "provider.id"),
		name: V(t.name, "provider.name"),
		enabled: t.enabled,
		availability: mn(t.availability, "provider.availability"),
		availabilityReason: dn(t.availabilityReason, "provider.availabilityReason"),
		configVersion: fn(t.configVersion, "provider.configVersion", 1)
	};
}
function yn(e) {
	let t = ln(e, "model");
	if (un(t, [
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
	let n = gn(t.priceMetadata, "model.priceMetadata");
	return {
		id: V(t.id, "model.id"),
		providerId: V(t.providerId, "model.providerId"),
		modelId: V(t.modelId, "model.modelId"),
		displayName: V(t.displayName, "model.displayName"),
		enabled: t.enabled,
		availability: mn(t.availability, "model.availability"),
		availabilityReason: dn(t.availabilityReason, "model.availabilityReason"),
		configVersion: fn(t.configVersion, "model.configVersion", 1),
		capabilities: _n(t.capabilities, n),
		priceMetadata: n
	};
}
function bn(e) {
	return {
		ok: !1,
		kind: "server",
		message: `模型目录请求失败 (${e})`
	};
}
function xn(e) {
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
function Sn(e) {
	let t = ln(e, "provider write response");
	if (un(t, [
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
		id: V(t.id, "provider write response.id"),
		adapterType: V(t.adapterType, "provider write response.adapterType"),
		name: V(t.name, "provider write response.name"),
		baseUrl: V(t.baseUrl, "provider write response.baseUrl"),
		authType: V(t.authType, "provider write response.authType"),
		enabled: t.enabled,
		configVersion: fn(t.configVersion, "provider write response.configVersion", 1),
		credentialConfigured: t.credentialConfigured,
		credentialHint: dn(t.credentialHint, "provider write response.credentialHint")
	};
}
function Cn(e) {
	let t = ln(e, "model profile write response");
	if (un(t, [
		"id",
		"providerId",
		"modelId",
		"displayName",
		"enabled",
		"configVersion"
	], "model profile write response"), typeof t.enabled != "boolean") throw Error("model profile write response has invalid enabled flag");
	return {
		id: V(t.id, "model profile write response.id"),
		providerId: V(t.providerId, "model profile write response.providerId"),
		modelId: V(t.modelId, "model profile write response.modelId"),
		displayName: V(t.displayName, "model profile write response.displayName"),
		enabled: t.enabled,
		configVersion: fn(t.configVersion, "model profile write response.configVersion", 1)
	};
}
function wn(e) {
	let t = ln(e, "provider probe response");
	if (un(t, ["status", "paidProbeRequired"], "provider probe response"), t.status !== "configuration_ready" && t.status !== "disabled" && t.status !== "missing_credential") throw Error("provider probe response status is invalid");
	if (typeof t.paidProbeRequired != "boolean") throw Error("provider probe response paidProbeRequired is invalid");
	return {
		status: t.status,
		paidProbeRequired: t.paidProbeRequired
	};
}
function Tn({ apiBase: e, fetcher: t = (e, t) => fetch(e, t) }) {
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
		} : bn(r.status);
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
		if (!i.ok) return xn(i.status);
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
					value: t.value.map(vn)
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
				let i = t.value.map(vn), a = await Promise.all(i.map(async (t) => {
					let i = await r(`${n}/model-providers/${encodeURIComponent(t.id)}/models`, e);
					if (!i.ok) return i;
					if (!Array.isArray(i.value)) throw Error("model catalog must be an array");
					let a = i.value.map(yn);
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
		createProvider: (e) => i(`${n}/model-providers`, e, Sn),
		createModelProfile: (e, t) => i(`${n}/model-providers/${encodeURIComponent(e)}/models`, t, Cn),
		probeProvider: (e, t) => i(`${n}/model-providers/${encodeURIComponent(e)}/test`, { allowPaidProbe: t }, wn)
	};
}
//#endregion
//#region node_modules/fabric/dist/index.min.mjs
var En = Object.defineProperty, Dn = (e, t) => {
	let n = {};
	for (var r in e) En(n, r, {
		get: e[r],
		enumerable: !0
	});
	return t || En(n, Symbol.toStringTag, { value: "Module" }), n;
};
function On(e) {
	return On = typeof Symbol == "function" && typeof Symbol.iterator == "symbol" ? function(e) {
		return typeof e;
	} : function(e) {
		return e && typeof Symbol == "function" && e.constructor === Symbol && e !== Symbol.prototype ? "symbol" : typeof e;
	}, On(e);
}
function kn(e) {
	var t = function(e, t) {
		if (On(e) != "object" || !e) return e;
		var n = e[Symbol.toPrimitive];
		if (n !== void 0) {
			var r = n.call(e, t || "default");
			if (On(r) != "object") return r;
			throw TypeError("@@toPrimitive must return a primitive value.");
		}
		return (t === "string" ? String : Number)(e);
	}(e, "string");
	return On(t) == "symbol" ? t : t + "";
}
function H(e, t, n) {
	return (t = kn(t)) in e ? Object.defineProperty(e, t, {
		value: n,
		enumerable: !0,
		configurable: !0,
		writable: !0
	}) : e[t] = n, e;
}
var An = class {
	constructor() {
		H(this, "browserShadowBlurConstant", 1), H(this, "DPI", 96), H(this, "devicePixelRatio", typeof window < "u" ? window.devicePixelRatio : 1), H(this, "perfLimitSizeTotal", 2097152), H(this, "maxCacheSideLimit", 4096), H(this, "minCacheSideLimit", 256), H(this, "disableStyleCopyPaste", !1), H(this, "enableGLFiltering", !0), H(this, "textureSize", 4096), H(this, "forceGLPutImageData", !1), H(this, "cachesBoundsOfCurve", !1), H(this, "fontPaths", {}), H(this, "NUM_FRACTION_DIGITS", 4);
	}
}, U = new class extends An {
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
		let t = new An(), n = e?.reduce((e, n) => (e[n] = t[n], e), {}) || t;
		this.configure(n);
	}
}(), jn = (e, ...t) => console[e]("fabric", ...t), Mn = class extends Error {
	constructor(e, t) {
		super(`fabric: ${e}`, t);
	}
}, Nn = class extends Mn {
	constructor(e) {
		super(`${e} 'options.signal' is in 'aborted' state`);
	}
}, Pn = class {}, Fn = class extends Pn {
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
		].find((e) => this.testPrecision(t, e)), t.getExtension("WEBGL_lose_context").loseContext(), jn("log", `WebGL: max texture size ${this.maxTextureSize}`));
	}
	isSupported(e) {
		return !!this.maxTextureSize && this.maxTextureSize >= e;
	}
}, In = {}, Ln, Rn = () => Ln ||= {
	document,
	window,
	isTouchSupported: "ontouchstart" in window || "ontouchstart" in document || window && window.navigator && window.navigator.maxTouchPoints > 0,
	WebGLProbe: new Fn(),
	dispose() {},
	copyPasteData: In
}, zn = () => Rn().document, Bn = () => Rn().window, Vn = () => Math.max(U.devicePixelRatio ?? Bn().devicePixelRatio, 1), Hn = new class {
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
}(), Un = "7.4.0";
function Wn() {}
var Gn = Math.PI / 2, Kn = Math.PI / 4, qn = 2 * Math.PI, Jn = Math.PI / 180, Yn = Object.freeze([
	1,
	0,
	0,
	1,
	0,
	0
]), W = "center", G = "left", Xn = "bottom", Zn = "right", Qn = "none", $n = /\r?\n/, er = "moving", tr = "scaling", nr = "rotating", rr = "rotate", ir = "skewing", ar = "resizing", or = "modifyPoly", sr = "changed", cr = "scale", lr = "scaleX", ur = "scaleY", dr = "skewX", fr = "skewY", pr = "fill", mr = "stroke", hr = "modified", gr = "normal", _r = "json", K = new class {
	constructor() {
		this[_r] = /* @__PURE__ */ new Map(), this.svg = /* @__PURE__ */ new Map();
	}
	has(e) {
		return this[_r].has(e);
	}
	getClass(e) {
		let t = this[_r].get(e);
		if (!t) throw new Mn(`No class registered for ${e}`);
		return t;
	}
	setClass(e, t) {
		t ? this[_r].set(t, e) : (this[_r].set(e.type, e), this[_r].set(e.type.toLowerCase(), e));
	}
	getSVGClass(e) {
		return this.svg.get(e);
	}
	setSVGClass(e, t) {
		this.svg.set(t ?? e.type.toLowerCase(), e);
	}
}(), vr = new class extends Array {
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
}(), yr = class {
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
}, br = (e, t) => {
	let n = e.indexOf(t);
	return n !== -1 && e.splice(n, 1), e;
}, xr = (e) => {
	if (e === 0) return 1;
	switch (Math.abs(e) / Gn) {
		case 1:
		case 3: return 0;
		case 2: return -1;
	}
	return Math.cos(e);
}, Sr = (e) => {
	if (e === 0) return 0;
	let t = e / Gn, n = Math.sign(e);
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
	rotate(t, n = Cr) {
		let r = Sr(t), i = xr(t), a = this.subtract(n);
		return new e(a.x * i - a.y * r, a.x * r + a.y * i).add(n);
	}
	transform(t, n = !1) {
		return new e(t[0] * this.x + t[2] * this.y + (n ? 0 : t[4]), t[1] * this.x + t[3] * this.y + (n ? 0 : t[5]));
	}
}, Cr = new q(0, 0), wr = (e) => !!e && Array.isArray(e._objects);
function Tr(e) {
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
			return !(!e || e === this._objects[0]) && (br(this._objects, e), this._objects.unshift(e), this._onStackOrderChanged(e), !0);
		}
		bringObjectToFront(e) {
			return !(!e || e === this._objects[this._objects.length - 1]) && (br(this._objects, e), this._objects.push(e), this._onStackOrderChanged(e), !0);
		}
		sendObjectBackwards(e, t) {
			if (!e) return !1;
			let n = this._objects.indexOf(e);
			if (n !== 0) {
				let r = this.findNewLowerIndex(e, n, t);
				return br(this._objects, e), this._objects.splice(r, 0, e), this._onStackOrderChanged(e), !0;
			}
			return !1;
		}
		bringObjectForward(e, t) {
			if (!e) return !1;
			let n = this._objects.indexOf(e);
			if (n !== this._objects.length - 1) {
				let r = this.findNewUpperIndex(e, n, t);
				return br(this._objects, e), this._objects.splice(r, 0, e), this._onStackOrderChanged(e), !0;
			}
			return !1;
		}
		moveObjectTo(e, t) {
			return e !== this._objects[t] && (br(this._objects, e), this._objects.splice(t, 0, e), this._onStackOrderChanged(e), !0);
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
var Er = class extends yr {
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
function Dr(e) {
	return Bn().requestAnimationFrame(e);
}
function Or(e) {
	return Bn().cancelAnimationFrame(e);
}
var kr = 0, Ar = () => kr++, jr = () => {
	let e = zn().createElement("canvas");
	if (!e || e.getContext === void 0) throw new Mn("Failed to create `canvas` element");
	return e;
}, Mr = () => zn().createElement("img"), Nr = (e) => {
	var t;
	let n = Pr(e);
	return (t = n.getContext("2d")) == null || t.drawImage(e, 0, 0), n;
}, Pr = (e) => {
	let t = jr();
	return t.width = e.width, t.height = e.height, t;
}, Fr = (e, t, n) => e.toDataURL(`image/${t}`, n), Ir = (e, t, n) => new Promise((r, i) => {
	e.toBlob(r, `image/${t}`, n);
}), J = (e) => e * Jn, Lr = (e) => e / Jn, Rr = (e) => e.every((e, t) => e === Yn[t]), zr = (e, t, n) => new q(e).transform(t, n), Br = (e) => {
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
], Vr = (e, t) => e.reduceRight((e, n) => n && e ? Y(n, e, t) : n || e, void 0) || Yn.concat(), Hr = ([e, t]) => Math.atan2(t, e), Ur = ([e, t]) => Math.sqrt(e * e + t * t), Wr = ([, , e, t]) => Math.sqrt(e * e + t * t), Gr = (e) => {
	let t = Hr(e), n = e[0] ** 2 + e[1] ** 2, r = Math.sqrt(n), i = (e[0] * e[3] - e[2] * e[1]) / r, a = Math.atan2(e[0] * e[2] + e[1] * e[3], n);
	return {
		angle: Lr(t),
		scaleX: r,
		scaleY: i,
		skewX: Lr(a),
		skewY: 0,
		translateX: e[4] || 0,
		translateY: e[5] || 0
	};
}, Kr = (e, t = 0) => [
	1,
	0,
	0,
	1,
	e,
	t
];
function qr({ angle: e = 0 } = {}, { x: t = 0, y: n = 0 } = {}) {
	let r = J(e), i = xr(r), a = Sr(r);
	return [
		i,
		a,
		-a,
		i,
		t ? t - (i * t - a * n) : 0,
		n ? n - (a * t + i * n) : 0
	];
}
var Jr = (e, t = e) => [
	e,
	0,
	0,
	t,
	0,
	0
], Yr = (e) => Math.tan(J(e)), Xr = (e) => [
	1,
	0,
	Yr(e),
	1,
	0,
	0
], Zr = (e) => [
	1,
	Yr(e),
	0,
	1,
	0,
	0
], Qr = ({ scaleX: e = 1, scaleY: t = 1, flipX: n = !1, flipY: r = !1, skewX: i = 0, skewY: a = 0 }) => {
	let o = Jr(n ? -e : e, r ? -t : t);
	return i && (o = Y(o, Xr(i), !0)), a && (o = Y(o, Zr(a), !0)), o;
}, $r = (e) => {
	let { translateX: t = 0, translateY: n = 0, angle: r = 0 } = e, i = Kr(t, n);
	r && (i = Y(i, qr({ angle: r })));
	let a = Qr(e);
	return Rr(a) || (i = Y(i, a)), i;
}, ei = (e, { signal: t, crossOrigin: n = null } = {}) => new Promise(function(r, i) {
	if (t && t.aborted) return i(new Nn("loadImage"));
	let a = Mr(), o;
	t && (o = function(e) {
		a.src = "", i(e);
	}, t.addEventListener("abort", o, { once: !0 }));
	let s = function() {
		a.onload = a.onerror = null, o && t?.removeEventListener("abort", o), r(a);
	};
	e ? (a.onload = s, a.onerror = function() {
		o && t?.removeEventListener("abort", o), i(new Mn(`Error loading ${a.src}`));
	}, n && (a.crossOrigin = n), a.src = e) : s();
}), ti = (e, { signal: t, reviver: n = Wn } = {}) => new Promise((r, i) => {
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
}), ni = (e, { signal: t } = {}) => new Promise((n, r) => {
	let i = [];
	t && t.addEventListener("abort", r, { once: !0 });
	let a = Object.values(e).map((e) => e && e.type && K.has(e.type) ? ti([e], { signal: t }).then(([e]) => (i.push(e), e)) : e), o = Object.keys(e);
	Promise.all(a).then((e) => e.reduce((e, t, n) => (e[o[n]] = t, e), {})).then(n).catch((e) => {
		i.forEach((e) => {
			e.dispose && e.dispose();
		}), r(e);
	}).finally(() => {
		t && t.removeEventListener("abort", r);
	});
}), ri = (e, t = []) => t.reduce((t, n) => (n in e && (t[n] = e[n]), t), {}), ii = (e, t) => Object.keys(e).reduce((n, r) => (t(e[r], r, e) && (n[r] = e[r]), n), {}), X = (e, t) => parseFloat(Number(e).toFixed(t)), ai = (e) => "matrix(" + e.map((e) => X(e, U.NUM_FRACTION_DIGITS)).join(" ") + ")", oi = (e) => !!e && e.toLive !== void 0, si = (e) => !!e && typeof e.toObject == "function", ci = (e) => !!e && e.offsetX !== void 0 && "source" in e, li = (e) => !!e && "multiSelectionStacking" in e;
function ui(e) {
	let t = e && di(e), n = 0, r = 0;
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
var di = (e) => e.ownerDocument || null, fi = (e) => e.ownerDocument?.defaultView || null, pi = (e, t, { width: n, height: r }, i = 1) => {
	e.width = n, e.height = r, i > 1 && (e.setAttribute("width", (n * i).toString()), e.setAttribute("height", (r * i).toString()), t.scale(i, i));
}, mi = (e, { width: t, height: n }) => {
	t && (e.style.width = typeof t == "number" ? `${t}px` : t), n && (e.style.height = typeof n == "number" ? `${n}px` : n);
};
function hi(e) {
	return e.onselectstart !== void 0 && (e.onselectstart = () => !1), e.style.userSelect = Qn, e;
}
var gi = class {
	constructor(e) {
		H(this, "_originalCanvasStyle", void 0), H(this, "lower", void 0);
		let t = this.createLowerCanvas(e);
		this.lower = {
			el: t,
			ctx: t.getContext("2d")
		};
	}
	createLowerCanvas(e) {
		let t = (n = e) && n.getContext !== void 0 ? e : e && zn().getElementById(e) || jr();
		var n;
		if (t.hasAttribute("data-fabric")) throw new Mn("Trying to initialize a canvas that has already been initialized. Did you forget to dispose the canvas?");
		return this._originalCanvasStyle = t.style.cssText, t.setAttribute("data-fabric", "main"), t.classList.add("lower-canvas"), t;
	}
	cleanupDOM({ width: e, height: t }) {
		let { el: n } = this.lower;
		n.classList.remove("lower-canvas"), n.removeAttribute("data-fabric"), n.setAttribute("width", `${e}`), n.setAttribute("height", `${t}`), n.style.cssText = this._originalCanvasStyle || "", this._originalCanvasStyle = void 0;
	}
	setDimensions(e, t) {
		let { el: n, ctx: r } = this.lower;
		pi(n, r, e, t);
	}
	setCSSDimensions(e) {
		mi(this.lower.el, e);
	}
	calcOffset() {
		return function(e) {
			let t = e && di(e), n = {
				left: 0,
				top: 0
			};
			if (!t) return n;
			let r = fi(e)?.getComputedStyle(e, null) || {};
			n.left += parseInt(r.borderLeftWidth, 10) || 0, n.top += parseInt(r.borderTopWidth, 10) || 0, n.left += parseInt(r.paddingLeft, 10) || 0, n.top += parseInt(r.paddingTop, 10) || 0;
			let i = {
				left: 0,
				top: 0
			}, a = t.documentElement;
			e.getBoundingClientRect !== void 0 && (i = e.getBoundingClientRect());
			let o = ui(e);
			return {
				left: i.left + o.left - (a.clientLeft || 0) + n.left,
				top: i.top + o.top - (a.clientTop || 0) + n.top
			};
		}(this.lower.el);
	}
	dispose() {
		Rn().dispose(this.lower.el), delete this.lower;
	}
}, _i = {
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
	viewportTransform: [...Yn],
	patternQuality: "best"
}, vi = Dn({
	capitalize: () => yi,
	escapeXml: () => Z,
	graphemeSplit: () => xi
}), yi = (e, t = !1) => `${e.charAt(0).toUpperCase()}${t ? e.slice(1) : e.slice(1).toLowerCase()}`, Z = (e) => e.toString().replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&apos;").replace(/</g, "&lt;").replace(/>/g, "&gt;"), bi, xi = (e) => {
	if (bi || bi || (bi = "Intl" in Bn() && "Segmenter" in Intl && new Intl.Segmenter(void 0, { granularity: "grapheme" })), bi) {
		let t = bi.segment(e);
		return Array.from(t).map(({ segment: e }) => e);
	}
	return Si(e);
}, Si = (e) => {
	let t = [];
	for (let n, r = 0; r < e.length; r++) !1 !== (n = Ci(e, r)) && t.push(n);
	return t;
}, Ci = (e, t) => {
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
}, wi = class e extends Tr(Er) {
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
		this.elements = new gi(e);
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
		e.canvas && e.canvas !== this && (jn("warn", "Canvas is trying to add an object that belongs to a different canvas.\nResulting to default behavior: removing object from previous canvas and adding to new canvas"), e.canvas.remove(e)), e._set("canvas", this), e.setCoords(), this.fire("object:added", { target: e }), e.fire("added", { target: this });
	}
	_onObjectRemoved(e) {
		e._set("canvas", void 0), this.fire("object:removed", { target: e }), e.fire("removed", { target: this });
	}
	_onStackOrderChanged() {
		this.renderOnAddRemove && this.requestRenderAll();
	}
	getRetinaScaling() {
		return this.enableRetinaScaling ? Vn() : 1;
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
		return Ur(this.viewportTransform);
	}
	setViewportTransform(e) {
		this.viewportTransform = e, this.calcViewportBoundaries(), this.renderOnAddRemove && this.requestRenderAll();
	}
	zoomToPoint(e, t) {
		let n = e, r = [...this.viewportTransform], i = zr(e, Br(r));
		r[0] = t, r[3] = t;
		let a = zr(i, r);
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
		this.nextRenderHandle || this.disposed || this.destroyed || (this.nextRenderHandle = Dr(() => this.renderAndReset()));
	}
	calcViewportBoundaries() {
		let e = this.width, t = this.height, n = Br(this.viewportTransform), r = zr({
			x: 0,
			y: 0
		}, n), i = zr({
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
		this.nextRenderHandle &&= (Or(this.nextRenderHandle), 0);
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
		let o = oi(n);
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
		return zr(this.getCenterPoint(), Br(this.viewportTransform));
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
			version: Un,
			...ri(this, t),
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
		return oi(a) ? a.excludeFromExport || (n.background = a.toObject(t)) : a && (n.background = a), oi(o) ? o.excludeFromExport || (n.overlay = o.toObject(t)) : o && (n.overlay = o), r && !r.excludeFromExport && (n.backgroundImage = this._toObject(r, e, t)), i && !i.excludeFromExport && (n.overlayImage = this._toObject(i, e, t)), n;
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
		e.push("<svg ", "xmlns=\"http://www.w3.org/2000/svg\" ", "xmlns:xlink=\"http://www.w3.org/1999/xlink\" ", "version=\"1.1\" ", "width=\"", n, "\" ", "height=\"", r, "\" ", o, "xml:space=\"preserve\">\n", "<desc>Created with Fabric.js ", Un, "</desc>\n", "<defs>\n", this.createSVGFontFacesMarkup(), this.createSVGRefElementsMarkup(), this.createSVGClipPathMarkup(t), "</defs>\n");
	}
	createSVGClipPathMarkup(e) {
		let t = this.clipPath;
		return t ? (t.clipPathId = `CLIPPATH_${Ar()}`, `<clipPath id="${t.clipPathId}" >\n${t.toClipPathSVG(e.reviver)}</clipPath>\n`) : "";
	}
	createSVGRefElementsMarkup() {
		return ["background", "overlay"].map((e) => {
			let t = this[`${e}Color`];
			if (oi(t)) {
				let n = this[`${e}Vpt`], r = this.viewportTransform, i = {
					isType: () => !1,
					width: this.width / (n ? r[0] : 1),
					height: this.height / (n ? r[3] : 1)
				};
				return t.toSVG(i, { additionalTransform: n ? ai(r) : "" });
			}
		}).join("");
	}
	createSVGFontFacesMarkup() {
		let e = [], t = {}, n = U.fontPaths;
		this._objects.forEach(function t(n) {
			e.push(n), wr(n) && n._objects.forEach(t);
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
		if (n) if (oi(n)) {
			let r = n.repeat || "", i = this.width, a = this.height, o = this[`${t}Vpt`] ? ai(Br(this.viewportTransform)) : "";
			e.push(`<rect transform="${o} translate(${i / 2},${a / 2})" x="${n.offsetX - i / 2}" y="${n.offsetY - a / 2}" width="${r !== "repeat-y" && r !== "no-repeat" || !ci(n) ? i : n.source.width}" height="${r !== "repeat-x" && r !== "no-repeat" || !ci(n) ? a : n.source.height}" fill="url(#SVGID_${n.id})"></rect>\n`);
		} else e.push("<rect x=\"0\" y=\"0\" width=\"100%\" height=\"100%\" ", "fill=\"", n, "\"", "></rect>\n");
	}
	loadFromJSON(e, t, { signal: n } = {}) {
		if (!e) return Promise.reject(new Mn("`json` is undefined"));
		let { objects: r = [], ...i } = typeof e == "string" ? JSON.parse(e) : e, { backgroundImage: a, background: o, overlayImage: s, overlay: c, clipPath: l } = i, u = this.renderOnAddRemove;
		return this.renderOnAddRemove = !1, Promise.all([ti(r, {
			reviver: t,
			signal: n
		}), ni({
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
		let e = Pr(this);
		return new this.constructor(e);
	}
	toDataURL(e = {}) {
		let { format: t = "png", quality: n = 1, multiplier: r = 1, enableRetinaScaling: i = !1 } = e, a = r * (i ? this.getRetinaScaling() : 1);
		return Fr(this.toCanvasElement(a, e), t, n);
	}
	toBlob(e = {}) {
		let { format: t = "png", quality: n = 1, multiplier: r = 1, enableRetinaScaling: i = !1 } = e, a = r * (i ? this.getRetinaScaling() : 1);
		return Ir(this.toCanvasElement(a, e), t, n);
	}
	toCanvasElement(e = 1, { width: t, height: n, left: r, top: i, filter: a } = {}) {
		let o = (t || this.width) * e, s = (n || this.height) * e, c = this.getZoom(), l = this.width, u = this.height, d = this.skipControlsDrawing, f = c * e, p = this.viewportTransform, m = [
			f,
			0,
			0,
			f,
			(p[4] - (r || 0)) * e,
			(p[5] - (i || 0)) * e
		], h = this.enableRetinaScaling, g = Pr({
			width: o,
			height: s
		}), _ = a ? this._objects.filter((e) => a(e)) : this._objects;
		return this.enableRetinaScaling = !1, this.viewportTransform = m, this.width = o, this.height = s, this.skipControlsDrawing = !0, this.calcViewportBoundaries(), this.renderCanvas(g.getContext("2d"), _), this.viewportTransform = p, this.width = l, this.height = u, this.calcViewportBoundaries(), this.enableRetinaScaling = h, this.skipControlsDrawing = d, g;
	}
	dispose() {
		return !this.disposed && this.elements.cleanupDOM({
			width: this.width,
			height: this.height
		}), vr.cancelByCanvas(this), this.disposed = !0, new Promise((e, t) => {
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
H(wi, "ownDefaults", _i);
var Ti = [
	"touchstart",
	"touchmove",
	"touchend"
], Ei = (e) => {
	let t = ui(e.target), n = function(e) {
		let t = e.changedTouches;
		return t && t[0] ? t[0] : e;
	}(e);
	return new q(n.clientX + t.left, n.clientY + t.top);
}, Di = (e) => Ti.includes(e.type) || e.pointerType === "touch", Oi = (e) => {
	e.preventDefault(), e.stopPropagation();
}, ki = (e) => {
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
}, Ai = (e, t) => {
	Mi(e, Y(Br(t), e.calcOwnMatrix()));
}, ji = (e, t) => Mi(e, Y(t, e.calcOwnMatrix())), Mi = (e, t) => {
	let { translateX: n, translateY: r, scaleX: i, scaleY: a, ...o } = Gr(t), s = new q(n, r);
	e.flipX = !1, e.flipY = !1, Object.assign(e, o), e.set({
		scaleX: i,
		scaleY: a
	}), e.setPositionByOrigin(s, W, W);
}, Ni = (e) => {
	e.scaleX = 1, e.scaleY = 1, e.skewX = 0, e.skewY = 0, e.flipX = !1, e.flipY = !1, e.rotate(0);
}, Pi = (e) => ({
	scaleX: e.scaleX,
	scaleY: e.scaleY,
	skewX: e.skewX,
	skewY: e.skewY,
	angle: e.angle,
	left: e.left,
	flipX: e.flipX,
	flipY: e.flipY,
	top: e.top
}), Fi = (e, t, n) => {
	let r = e / 2, i = t / 2, a = ki([
		new q(-r, -i),
		new q(r, -i),
		new q(-r, i),
		new q(r, i)
	].map((e) => e.transform(n)));
	return new q(a.width, a.height);
}, Ii = (e = Yn, t = Yn) => Y(Br(t), e), Li = (e, t = Yn, n = Yn) => e.transform(Ii(t, n)), Ri = (e, t = Yn, n = Yn) => e.transform(Ii(t, n), !0), zi = (e, t, n) => {
	let r = Ii(t, n);
	return Mi(e, Y(r, e.calcOwnMatrix())), r;
}, Bi = {
	left: -.5,
	top: -.5,
	center: 0,
	bottom: .5,
	right: .5
}, Vi = (e) => typeof e == "string" ? Bi[e] : e - .5, Hi = new q(1, 0), Ui = new q(), Wi = (e, t) => e.rotate(t), Gi = (e, t) => new q(t).subtract(e), Ki = (e) => e.distanceFrom(Ui), qi = (e, t) => Math.atan2(Zi(e, t), Qi(e, t)), Ji = (e) => qi(Hi, e), Yi = (e) => e.eq(Ui) ? e : e.scalarDivide(Ki(e)), Xi = (e, t = !0) => Yi(new q(-e.y, e.x).scalarMultiply(t ? 1 : -1)), Zi = (e, t) => e.x * t.y - e.y * t.x, Qi = (e, t) => e.x * t.x + e.y * t.y, $i = (e, t, n) => {
	if (e.eq(t) || e.eq(n)) return !0;
	let r = Zi(t, n), i = Zi(t, e), a = Zi(n, e);
	return r >= 0 ? i >= 0 && a <= 0 : !(i <= 0 && a >= 0);
}, ea = "not-allowed";
function ta(e) {
	return Vi(e.originX) === Vi("center") && Vi(e.originY) === Vi("center");
}
function na(e) {
	return .5 - Vi(e);
}
var ra = (e, t) => e[t], ia = (e, t, n, r) => ({
	e,
	transform: t,
	pointer: new q(n, r)
});
function aa(e, t, n) {
	let r = n, i = Ji(Gi(Li(e.getCenterPoint(), e.canvas.viewportTransform, void 0), r)) + qn;
	return Math.round(i % qn / Kn);
}
function oa({ target: e, corner: t }, n, r, i, a) {
	let o = e.controls[t], s = e.canvas?.getZoom() || 1, c = e.padding / s, l = function(e, t, n, r) {
		let i = e.getRelativeCenterPoint(), a = n !== void 0 && r !== void 0 ? e.translateToGivenOrigin(i, W, W, n, r) : new q(e.left, e.top);
		return (e.angle ? t.rotate(-J(e.angle), i) : t).subtract(a);
	}(e, new q(i, a), n, r);
	return l.x >= c && (l.x -= c), l.x <= -c && (l.x += c), l.y >= c && (l.y -= c), l.y <= c && (l.y += c), l.x -= o.offsetX, l.y -= o.offsetY, l;
}
var sa = new RegExp(String.raw`[\0-\x1F\x7F;<>\\]|\/\*|\*\/|url\s*\(|expression\s*\(|(?:java|vb)script\s*:|data\s*:|@import\b`, "iu"), ca = (e) => typeof e == "string" && e.trim().length > 0 && !sa.test(e), la = (e, t = "") => {
	let n = Number(e);
	return Number.isFinite(n) ? `${n}` : t;
}, ua = (e, t = "") => typeof e == "string" && ca(e) ? e : t, da = (e) => e.replace(/\s+/g, " "), fa = {
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
}, pa = (e, t, n) => (n < 0 && (n += 1), n > 1 && --n, n < 1 / 6 ? e + 6 * (t - e) * n : n < .5 ? t : n < 2 / 3 ? e + (t - e) * (2 / 3 - n) * 6 : e), ma = (e, t, n, r) => {
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
}, ha = (e = "1") => parseFloat(e) / (e.endsWith("%") ? 100 : 1), ga = (e) => Math.min(Math.round(e), 255).toString(16).toUpperCase().padStart(2, "0"), _a = ([e, t, n, r = 1]) => {
	let i = Math.round(.3 * e + .59 * t + .11 * n);
	return [
		i,
		i,
		i,
		r
	];
}, va = class e {
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
		return (t = t.toLowerCase()) in fa && (t = fa[t]), t === "transparent" ? [
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
		let [e, t, n] = ma(...this.getSource());
		return `hsl(${e},${t}%,${n}%)`;
	}
	toHsla() {
		let [e, t, n, r] = ma(...this.getSource());
		return `hsla(${e},${t}%,${n}%,${r})`;
	}
	toHex() {
		return this.toHexa().slice(0, 6);
	}
	toHexa() {
		let [e, t, n, r] = this.getSource();
		return `${ga(e)}${ga(t)}${ga(n)}${ga(Math.round(255 * r))}`;
	}
	getAlpha() {
		return this.getSource()[3];
	}
	setAlpha(e) {
		return this._source[3] = e, this;
	}
	toGrayscale() {
		return this.setSource(_a(this.getSource())), this;
	}
	toBlackWhite(e) {
		let [t, , , n] = _a(this.getSource()), r = t < (e || 127) ? 0 : 255;
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
		let t = da(e).match(/^rgba?\(\s?(\d{0,3}(?:\.\d+)?%?)\s?[\s|,]\s?(\d{0,3}(?:\.\d+)?%?)\s?[\s|,]\s?(\d{0,3}(?:\.\d+)?%?)\s?(?:\s?[,/]\s?(\d{0,3}(?:\.\d+)?%?)\s?)?\)$/i);
		if (t) {
			let [e, n, r] = t.slice(1, 4).map((e) => {
				let t = parseFloat(e);
				return e.endsWith("%") ? Math.round(2.55 * t) : t;
			});
			return [
				e,
				n,
				r,
				ha(t[4])
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
		let n = da(t).match(/^hsla?\(\s?([+-]?\d{0,3}(?:\.\d+)?(?:deg|turn|rad)?)\s?[\s|,]\s?(\d{0,3}(?:\.\d+)?%?)\s?[\s|,]\s?(\d{0,3}(?:\.\d+)?%?)\s?(?:\s?[,/]\s?(\d*(?:\.\d+)?%?)\s?)?\)$/i);
		if (!n) return;
		let r = (e.parseAngletoDegrees(n[1]) % 360 + 360) % 360 / 360, i = parseFloat(n[2]) / 100, a = parseFloat(n[3]) / 100, o, s, c;
		if (i === 0) o = s = c = a;
		else {
			let e = a <= .5 ? a * (i + 1) : a + i - a * i, t = 2 * a - e;
			o = pa(t, e, r + 1 / 3), s = pa(t, e, r), c = pa(t, e, r - 1 / 3);
		}
		return [
			Math.round(255 * o),
			Math.round(255 * s),
			Math.round(255 * c),
			ha(n[4])
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
		return t.includes("rad") ? Lr(n) : t.includes("turn") ? 360 * n : n;
	}
}, ya = (e) => {
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
}, ba = (e, t = 16) => {
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
}, xa = (e) => {
	let [t, n] = e.trim().split(" "), [r, i] = (a = t) && a !== "none" ? [a.slice(1, 4), a.slice(5, 8)] : a === "none" ? [a, a] : ["Mid", "Mid"];
	var a;
	return {
		meetOrSlice: n || "meet",
		alignX: r,
		alignY: i
	};
}, Sa = (e, t, n = !0) => {
	let r, i;
	if (t) if (t.toLive) r = `url(#SVGID_${Z(t.id)})`;
	else {
		let e = String(t);
		if (ca(e)) {
			let t = new va(e), n = t.getAlpha();
			r = t.toRgb(), n !== 1 && (i = n.toString());
		} else r = new va("black").toRgb();
	}
	else r = "none";
	return n ? `${e}: ${r}; ${i ? `${e}-opacity: ${i}; ` : ""}` : `${e}="${r}" ${i ? `${e}-opacity="${i}" ` : ""}`;
}, Ca = class {
	getSvgStyles(e) {
		let t = this.fillRule == null ? "nonzero" : ua(this.fillRule), n = this.strokeWidth == null ? "0" : la(this.strokeWidth), r = this.strokeDashArray == null ? Qn : this.strokeDashArray.every((e) => Number.isFinite(Number(e))) ? this.strokeDashArray.join(" ") : "", i = this.strokeDashOffset == null ? "0" : la(this.strokeDashOffset), a = this.strokeLineCap == null ? "butt" : ua(this.strokeLineCap), o = this.strokeLineJoin == null ? "miter" : ua(this.strokeLineJoin), s = this.strokeMiterLimit == null ? "4" : la(this.strokeMiterLimit), c = this.opacity == null ? "1" : la(this.opacity), l = this.visible ? "" : " visibility: hidden;", u = e ? "" : this.getSvgFilter(), d = Sa(pr, this.fill);
		return [
			Sa(mr, this.stroke),
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
		return `transform="${ai(e ? this.calcTransformMatrix() : this.calcOwnMatrix())}${t}" `;
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
		return s && (s.clipPathId = `CLIPPATH_${Ar()}`, h = `<clipPath id="${s.clipPathId}" >\n${s.toClipPathSVG(n)}</clipPath>\n`), l && p.push("<g ", o, this.getSvgCommons(), " >\n"), p.push("<g ", this.getSvgTransform(!1), l ? "" : o + this.getSvgCommons(), " >\n"), e[m] = [
			a,
			c,
			t ? "" : this.addPaintOrder(),
			" ",
			i ? `transform="${i}" ` : ""
		].join(""), oi(d) && p.push(d.toSVG(this)), oi(u) && p.push(u.toSVG(this)), f && p.push(f.toSVG(this)), s && p.push(h), p.push(e.join("")), p.push("</g>\n"), l && p.push("</g>\n"), n ? n(p.join("")) : p.join("");
	}
	addPaintOrder() {
		return this.paintFirst === "fill" ? "" : ` paint-order="${Z(this.paintFirst)}" `;
	}
};
function wa(e) {
	return RegExp("^(" + e.join("|") + ")\\b", "i");
}
var Ta = "textDecorationThickness", Ea = "textDecorationColor", Da = [
	"fontSize",
	"fontWeight",
	"fontFamily",
	"fontStyle"
], Oa = [
	"underline",
	"overline",
	"linethrough"
], ka = [
	...Da,
	"lineHeight",
	"text",
	"charSpacing",
	"textAlign",
	"styles",
	"path",
	"pathStartOffset",
	"pathSide",
	"pathAlign"
], Aa = [
	...ka,
	...Oa,
	"textBackgroundColor",
	"direction",
	Ta,
	Ea
], ja = [
	...Da,
	...Oa,
	mr,
	"strokeWidth",
	pr,
	"deltaY",
	"textBackgroundColor",
	Ta,
	Ea
], Ma = {
	_reNewline: $n,
	_reSpacesAndTabs: /[ \t\r]/g,
	_reSpaceAndTab: /[ \t\r]/,
	_reWords: /\S+/g,
	fontSize: 40,
	fontWeight: gr,
	fontFamily: "Times New Roman",
	underline: !1,
	overline: !1,
	linethrough: !1,
	textAlign: G,
	fontStyle: gr,
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
	[Ta]: 66.667
}, Na = "justify", Pa = String.raw`[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?`, Fa = String.raw`(?:\s*,?\s+|\s*,\s*)`, Ia = RegExp("(normal|italic)?\\s*(normal|small-caps)?\\s*(normal|bold|bolder|lighter|100|200|300|400|500|600|700|800|900)?\\s*(" + Pa + "(?:px|cm|mm|em|pt|pc|in)*)(?:\\/(normal|" + Pa + "))?\\s+(.*)"), La = {
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
	"text-decoration-thickness": Ta,
	"text-decoration-color": Ea
}, Ra = "font-size", za = "clip-path";
wa([
	"path",
	"circle",
	"polygon",
	"polyline",
	"ellipse",
	"rect",
	"line",
	"image",
	"text"
]), wa([
	"symbol",
	"image",
	"marker",
	"pattern",
	"view",
	"svg"
]);
var Ba = wa([
	"symbol",
	"g",
	"a",
	"svg",
	"clipPath",
	"defs"
]);
new RegExp(String.raw`^\s*(${Pa})${Fa}(${Pa})${Fa}(${Pa})${Fa}(${Pa})\s*$`);
var Va = "(-?\\d+(?:\\.\\d*)?(?:px)?(?:\\s?|$))?", Ha = RegExp("(?:\\s|^)" + Va + Va + "(" + Pa + "?(?:px)?)?(?:\\s?|$)(?:$|\\s)"), Ua = class e {
	constructor(t = {}) {
		let n = typeof t == "string" ? e.parseShadow(t) : t;
		Object.assign(this, e.ownDefaults, n), this.id = Ar();
	}
	static parseShadow(e) {
		let t = e.trim(), [, n = 0, r = 0, i = 0] = (Ha.exec(t) || []).map((e) => parseFloat(e) || 0);
		return {
			color: (t.replace(Ha, "") || "rgb(0,0,0)").trim(),
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
		let t = Wi(new q(this.offsetX, this.offsetY), J(-e.angle)), n = U.NUM_FRACTION_DIGITS, r = new va(this.color), i = 40, a = 40;
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
		return this.includeDefaultValues ? t : ii(t, (e, t) => e !== n[t]);
	}
	static async fromObject(e) {
		return new this(e);
	}
};
H(Ua, "ownDefaults", {
	color: "rgb(0,0,0)",
	blur: 0,
	offsetX: 0,
	offsetY: 0,
	affectStroke: !1,
	includeDefaultValues: !0,
	nonScaling: !1
}), H(Ua, "type", "shadow"), K.setClass(Ua, "shadow");
var Wa = (e, t, n) => Math.max(e, Math.min(t, n)), Ga = [
	"top",
	G,
	lr,
	ur,
	"flipX",
	"flipY",
	"originX",
	"originY",
	"angle",
	"opacity",
	"globalCompositeOperation",
	"shadow",
	"visible",
	dr,
	fr
], Ka = [
	pr,
	mr,
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
], qa = {
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
	paintFirst: pr,
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
}, Ja = Dn({
	defaultEasing: () => Za,
	easeInBack: () => bo,
	easeInBounce: () => wo,
	easeInCirc: () => mo,
	easeInCubic: () => Qa,
	easeInElastic: () => _o,
	easeInExpo: () => uo,
	easeInOutBack: () => So,
	easeInOutBounce: () => To,
	easeInOutCirc: () => go,
	easeInOutCubic: () => eo,
	easeInOutElastic: () => yo,
	easeInOutExpo: () => po,
	easeInOutQuad: () => Oo,
	easeInOutQuart: () => ro,
	easeInOutQuint: () => oo,
	easeInOutSine: () => lo,
	easeInQuad: () => Eo,
	easeInQuart: () => to,
	easeInQuint: () => io,
	easeInSine: () => so,
	easeOutBack: () => xo,
	easeOutBounce: () => Co,
	easeOutCirc: () => ho,
	easeOutCubic: () => $a,
	easeOutElastic: () => vo,
	easeOutExpo: () => fo,
	easeOutQuad: () => Do,
	easeOutQuart: () => no,
	easeOutQuint: () => ao,
	easeOutSine: () => co
}), Ya = (e, t, n, r) => (e < Math.abs(t) ? (e = t, r = n / 4) : r = t === 0 && e === 0 ? n / qn * Math.asin(1) : n / qn * Math.asin(t / e), {
	a: e,
	c: t,
	p: n,
	s: r
}), Xa = (e, t, n, r, i) => e * 2 ** (10 * --r) * Math.sin((r * i - t) * qn / n), Za = (e, t, n, r) => -n * Math.cos(e / r * Gn) + n + t, Qa = (e, t, n, r) => n * (e / r) ** 3 + t, $a = (e, t, n, r) => n * ((e / r - 1) ** 3 + 1) + t, eo = (e, t, n, r) => (e /= r / 2) < 1 ? n / 2 * e ** 3 + t : n / 2 * ((e - 2) ** 3 + 2) + t, to = (e, t, n, r) => n * (e /= r) * e ** 3 + t, no = (e, t, n, r) => -n * ((e = e / r - 1) * e ** 3 - 1) + t, ro = (e, t, n, r) => (e /= r / 2) < 1 ? n / 2 * e ** 4 + t : -n / 2 * ((e -= 2) * e ** 3 - 2) + t, io = (e, t, n, r) => n * (e / r) ** 5 + t, ao = (e, t, n, r) => n * ((e / r - 1) ** 5 + 1) + t, oo = (e, t, n, r) => (e /= r / 2) < 1 ? n / 2 * e ** 5 + t : n / 2 * ((e - 2) ** 5 + 2) + t, so = (e, t, n, r) => -n * Math.cos(e / r * Gn) + n + t, co = (e, t, n, r) => n * Math.sin(e / r * Gn) + t, lo = (e, t, n, r) => -n / 2 * (Math.cos(Math.PI * e / r) - 1) + t, uo = (e, t, n, r) => e === 0 ? t : n * 2 ** (10 * (e / r - 1)) + t, fo = (e, t, n, r) => e === r ? t + n : n * -(2 ** (-10 * e / r) + 1) + t, po = (e, t, n, r) => e === 0 ? t : e === r ? t + n : (e /= r / 2) < 1 ? n / 2 * 2 ** (10 * (e - 1)) + t : n / 2 * -(2 ** (-10 * (e - 1)) + 2) + t, mo = (e, t, n, r) => -n * (Math.sqrt(1 - (e /= r) * e) - 1) + t, ho = (e, t, n, r) => n * Math.sqrt(1 - (e = e / r - 1) * e) + t, go = (e, t, n, r) => (e /= r / 2) < 1 ? -n / 2 * (Math.sqrt(1 - e ** 2) - 1) + t : n / 2 * (Math.sqrt(1 - (e -= 2) * e) + 1) + t, _o = (e, t, n, r) => {
	let i = n, a = 0;
	if (e === 0) return t;
	if ((e /= r) === 1) return t + n;
	a ||= .3 * r;
	let { a: o, s, p: c } = Ya(i, n, a, 1.70158);
	return -Xa(o, s, c, e, r) + t;
}, vo = (e, t, n, r) => {
	let i = n, a = 0;
	if (e === 0) return t;
	if ((e /= r) === 1) return t + n;
	a ||= .3 * r;
	let { a: o, s, p: c, c: l } = Ya(i, n, a, 1.70158);
	return o * 2 ** (-10 * e) * Math.sin((e * r - s) * qn / c) + l + t;
}, yo = (e, t, n, r) => {
	let i = n, a = 0;
	if (e === 0) return t;
	if ((e /= r / 2) == 2) return t + n;
	a ||= .3 * 1.5 * r;
	let { a: o, s, p: c, c: l } = Ya(i, n, a, 1.70158);
	return e < 1 ? -.5 * Xa(o, s, c, e, r) + t : o * 2 ** (-10 * --e) * Math.sin((e * r - s) * qn / c) * .5 + l + t;
}, bo = (e, t, n, r, i = 1.70158) => n * (e /= r) * e * ((i + 1) * e - i) + t, xo = (e, t, n, r, i = 1.70158) => n * ((e = e / r - 1) * e * ((i + 1) * e + i) + 1) + t, So = (e, t, n, r, i = 1.70158) => (e /= r / 2) < 1 ? n / 2 * (e * e * ((1 + (i *= 1.525)) * e - i)) + t : n / 2 * ((e -= 2) * e * ((1 + (i *= 1.525)) * e + i) + 2) + t, Co = (e, t, n, r) => (e /= r) < 1 / 2.75 ? n * (7.5625 * e * e) + t : e < 2 / 2.75 ? n * (7.5625 * (e -= 1.5 / 2.75) * e + .75) + t : e < 2.5 / 2.75 ? n * (7.5625 * (e -= 2.25 / 2.75) * e + .9375) + t : n * (7.5625 * (e -= 2.625 / 2.75) * e + .984375) + t, wo = (e, t, n, r) => n - Co(r - e, 0, n, r) + t, To = (e, t, n, r) => e < r / 2 ? .5 * wo(2 * e, 0, n, r) + t : .5 * Co(2 * e - r, 0, n, r) + .5 * n + t, Eo = (e, t, n, r) => n * (e /= r) * e + t, Do = (e, t, n, r) => -n * (e /= r) * (e - 2) + t, Oo = (e, t, n, r) => (e /= r / 2) < 1 ? n / 2 * e ** 2 + t : -n / 2 * (--e * (e - 2) - 1) + t, ko = () => !1, Ao = class {
	constructor({ startValue: e, byValue: t, duration: n = 500, delay: r = 0, easing: i = Za, onStart: a = Wn, onChange: o = Wn, onComplete: s = Wn, abort: c = ko, target: l }) {
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
		this.register(), this.delay > 0 ? this.timeout = Bn().setTimeout(() => Dr(e), this.delay) : Dr(e);
	}
	tick(e) {
		let t = (e || +/* @__PURE__ */ new Date()) - this.startTime, n = Math.min(t, this.duration);
		this.durationProgress = n / this.duration;
		let { value: r, valueProgress: i } = this.calculate(n);
		this.value = Object.freeze(r), this.valueProgress = i, this._state !== "aborted" && (this._abort(this.value, this.valueProgress, this.durationProgress) ? (this._state = "aborted", this.unregister()) : t >= this.duration ? (this.durationProgress = this.valueProgress = 1, this._onChange(this.endValue, this.valueProgress, this.durationProgress), this._state = "completed", this._onComplete(this.endValue, this.valueProgress, this.durationProgress), this.unregister(), this.timeout = null) : (this._onChange(this.value, this.valueProgress, this.durationProgress), Dr(this.tick)));
	}
	register() {
		vr.push(this);
	}
	unregister() {
		vr.remove(this);
	}
	abort() {
		this._state = "aborted", this.unregister(), this.timeout && Bn().clearTimeout(this.timeout);
	}
}, jo = class extends Ao {
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
}, Mo = class extends Ao {
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
}, No = (e, t, n, r) => t + n * (1 - Math.cos(e / r * Gn)), Po = (e) => e && ((t, n, r) => e(new va(t).toRgba(), n, r)), Fo = class extends Ao {
	constructor({ startValue: e, endValue: t, easing: n = No, onChange: r, onComplete: i, abort: a, ...o }) {
		let s = new va(e).getSource(), c = new va(t).getSource();
		super({
			...o,
			startValue: s,
			byValue: c.map((e, t) => e - s[t]),
			easing: n,
			onChange: Po(r),
			onComplete: Po(i),
			abort: Po(a)
		});
	}
	calculate(e) {
		let [t, n, r, i] = this.startValue.map((t, n) => this.easing(e, t, this.byValue[n], this.duration, n)), a = [...[
			t,
			n,
			r
		].map(Math.round), Wa(0, i, 1)];
		return {
			value: a,
			valueProgress: a.map((e, t) => this.byValue[t] === 0 ? 0 : Math.abs((e - this.startValue[t]) / this.byValue[t])).find((e) => e !== 0) || 0
		};
	}
};
function Io(e) {
	let t = ((e) => Array.isArray(e.startValue) || Array.isArray(e.endValue))(e) ? new Mo(e) : new jo(e);
	return t.start(), t;
}
function Lo(e) {
	let t = new Fo(e);
	return t.start(), t;
}
var Ro = class e {
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
			let i = Gi(t, n), a = Gi(t, e).divide(i);
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
}, zo = class extends Er {
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
		return this.group ? zr(e, this.group.calcTransformMatrix()) : e;
	}
	setXY(e, t, n) {
		this.group && (e = zr(e, Br(this.group.calcTransformMatrix()))), this.setRelativeXY(e, t, n);
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
			return i.map((t) => zr(t, e));
		}
		return i;
	}
	intersectsWithRect(e, t) {
		return Ro.intersectPolygonRectangle(this.getCoords(), e, t).status === "Intersection";
	}
	intersectsWithObject(e) {
		let t = Ro.intersectPolygonPolygon(this.getCoords(), e.getCoords());
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
		return Ro.isPointInPolygon(e, this.getCoords());
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
		return ki(this.getCoords());
	}
	getScaledWidth() {
		return this._getTransformedDimensions().x;
	}
	getScaledHeight() {
		return this._getTransformedDimensions().y;
	}
	scale(e) {
		this._set(lr, e), this._set(ur, e), this.setCoords();
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
		return this.group ? Lr(Hr(this.calcTransformMatrix())) : this.angle;
	}
	getViewportTransform() {
		return this.canvas?.viewportTransform || Yn.concat();
	}
	calcACoords() {
		let e = qr({ angle: this.angle }), { x: t, y: n } = this.getRelativeCenterPoint(), r = Y(Kr(t, n), e), i = this._getTransformedDimensions(), a = i.x / 2, o = i.y / 2;
		return {
			tl: zr({
				x: -a,
				y: -o
			}, r),
			tr: zr({
				x: a,
				y: -o
			}, r),
			bl: zr({
				x: -a,
				y: o
			}, r),
			br: zr({
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
		return !e && this.group && (t = this.group.transformMatrixKey(e)), t.push(this.top, this.left, this.width, this.height, this.scaleX, this.scaleY, this.angle, this.strokeWidth, this.skewX, this.skewY, +this.flipX, +this.flipY, Vi(this.originX), Vi(this.originY)), t;
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
		let n = this.getRelativeCenterPoint(), r = $r({
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
		return t ? n.multiply(new q(Ur(t), Wr(t))).scalarAdd(2 * this.padding) : n.scalarAdd(2 * this.padding);
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
		return s = t.skewX === 0 && t.skewY === 0 ? new q(a * t.scaleX, o * t.scaleY) : Fi(a, o, Qr(t)), s.scalarAdd(i);
	}
	translateToGivenOrigin(e, t, n, r, i) {
		let a = e.x, o = e.y, s = Vi(r) - Vi(t), c = Vi(i) - Vi(n);
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
		return this.group ? zr(e, this.group.calcTransformMatrix()) : e;
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
}, Bo = class e extends zo {
	static getDefaults() {
		return e.ownDefaults;
	}
	get type() {
		let e = this.constructor.type;
		return e === "FabricObject" ? "object" : e.toLowerCase();
	}
	set type(e) {
		jn("warn", "Setting type has no effect", e);
	}
	constructor(t) {
		super(), H(this, "_cacheContext", null), Object.assign(this, e.ownDefaults), this.setOptions(t);
	}
	_createCacheCanvas() {
		this._cacheCanvas = jr(), this._cacheContext = this._cacheCanvas.getContext("2d"), this._updateCacheCanvas(), this.dirty = !0;
	}
	_limitCacheSize(e) {
		let t = e.width, n = e.height, r = U.maxCacheSideLimit, i = U.minCacheSideLimit;
		if (t <= r && n <= r && t * n <= U.perfLimitSizeTotal) return t < i && (e.width = i), n < i && (e.height = i), e;
		let a = t / n, [o, s] = Hn.limitDimsByArea(a), c = Wa(i, o, r), l = Wa(i, s, r);
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
		let e = Gr(this.calcTransformMatrix());
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
		e !== "scaleX" && e !== "scaleY" || (t = this._constrainScale(t)), e === "scaleX" && t < 0 ? (this.flipX = !this.flipX, t *= -1) : e === "scaleY" && t < 0 ? (this.flipY = !this.flipY, t *= -1) : e !== "shadow" || !t || t instanceof Ua || (t = new Ua(t));
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
		let n = Pr(t), r = n.getContext("2d");
		if (r.translate(t.cacheTranslationX, t.cacheTranslationY), r.scale(t.zoomX, t.zoomY), e._cacheCanvas = n, t.parentClipPaths.forEach((e) => {
			e.transform(r);
		}), t.parentClipPaths.push(e), e.absolutePositioned) {
			let e = Br(this.calcTransformMatrix());
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
		n && (e.lineWidth = t.strokeWidth, e.lineCap = t.strokeLineCap, e.lineDashOffset = t.strokeDashOffset, e.lineJoin = t.strokeLineJoin, e.miterLimit = t.strokeMiterLimit, oi(n) ? n.gradientUnits === "percentage" || n.gradientTransform || n.patternTransform ? this._applyPatternForTransformedGradient(e, n) : (e.strokeStyle = n.toLive(e), this._applyPatternGradientTransform(e, n)) : e.strokeStyle = t.stroke);
	}
	_setFillStyles(e, { fill: t }) {
		t && (oi(t) ? (e.fillStyle = t.toLive(e), this._applyPatternGradientTransform(e, t)) : e.fillStyle = t);
	}
	_setClippingProperties(e) {
		e.globalAlpha = 1, e.strokeStyle = "transparent", e.fillStyle = "#000000";
	}
	_setLineDash(e, t) {
		t && t.length !== 0 && e.setLineDash(t);
	}
	_setShadow(e) {
		if (!this.shadow) return;
		let t = this.shadow, n = this.canvas, r = this.getCanvasRetinaScaling(), [i, , , a] = n?.viewportTransform || Yn, o = i * r, s = a * r, c = t.nonScaling ? new q(1, 1) : this.getObjectScaling();
		e.shadowColor = t.color, e.shadowBlur = t.blur * U.browserShadowBlurConstant * (o + s) * (c.x + c.y) / 4, e.shadowOffsetX = t.offsetX * o * c.x, e.shadowOffsetY = t.offsetY * s * c.y;
	}
	_removeShadow(e) {
		this.shadow && (e.shadowColor = "", e.shadowBlur = e.shadowOffsetX = e.shadowOffsetY = 0);
	}
	_applyPatternGradientTransform(e, t) {
		if (!oi(t)) return {
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
		let n = this._limitCacheSize(this._getCacheCanvasDimensions()), r = this.getCanvasRetinaScaling(), i = n.x / this.scaleX / r, a = n.y / this.scaleY / r, o = Pr({
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
		let t = Pi(this), n = this.group, r = this.shadow, i = Math.abs, a = e.enableRetinaScaling ? Vn() : 1, o = (e.multiplier || 1) * a, s = e.canvasProvider || ((e) => new wi(e, {
			enableRetinaScaling: !1,
			renderOnAddRemove: !1,
			skipOffscreen: !1
		}));
		delete this.group, e.withoutTransform && Ni(this), e.withoutShadow && (this.shadow = null), e.viewportTransform && zi(this, this.getViewportTransform()), this.setCoords();
		let c = jr(), l = this.getBoundingRect(), u = this.shadow, d = new q();
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
		return Fr(this.toCanvasElement(e), e.format || "png", e.quality || 1);
	}
	toBlob(e = {}) {
		return Ir(this.toCanvasElement(e), e.format || "png", e.quality || 1);
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
		vr.cancelByTarget(this), this.off(), this._set("canvas", void 0), this._cacheCanvas && Rn().dispose(this._cacheCanvas), this._cacheCanvas = void 0, this._cacheContext = null;
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
		return i ? Lo(l) : Io(l);
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
		let n = t.concat(e.customProperties, this.constructor.customProperties || []), r, i = U.NUM_FRACTION_DIGITS, { clipPath: a, fill: o, stroke: s, shadow: c, strokeDashArray: l, left: u, top: d, originX: f, originY: p, width: m, height: h, strokeWidth: g, strokeLineCap: _, strokeDashOffset: v, strokeLineJoin: y, strokeUniform: b, strokeMiterLimit: x, scaleX: S, scaleY: C, angle: w, flipX: T, flipY: E, opacity: ee, visible: D, backgroundColor: O, fillRule: te, paintFirst: ne, globalCompositeOperation: re, skewX: ie, skewY: k } = this;
		a && !a.excludeFromExport && (r = a.toObject(n.concat("inverted", "absolutePositioned")));
		let A = (e) => X(e, i), j = {
			...ri(this, n),
			type: this.constructor.type,
			version: Un,
			originX: f,
			originY: p,
			left: A(u),
			top: A(d),
			width: A(m),
			height: A(h),
			fill: si(o) ? o.toObject() : o,
			stroke: si(s) ? s.toObject() : s,
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
			opacity: A(ee),
			shadow: c && c.toObject(),
			visible: D,
			backgroundColor: O,
			fillRule: te,
			paintFirst: ne,
			globalCompositeOperation: re,
			skewX: A(ie),
			skewY: A(k),
			...r ? { clipPath: r } : null
		};
		return this.includeDefaultValues ? j : this._removeDefaultValues(j);
	}
	toDatalessObject(e) {
		return this.toObject(e);
	}
	_removeDefaultValues(e) {
		let t = this.constructor.getDefaults(), n = Object.keys(t).length > 0 ? t : Object.getPrototypeOf(this);
		return ii(e, (e, t) => {
			if (t === "left" || t === "top" || t === "type") return !0;
			let r = n[t];
			return e !== r && !(Array.isArray(e) && Array.isArray(r) && e.length === 0 && r.length === 0);
		});
	}
	toString() {
		return `#<${this.constructor.type}>`;
	}
	static _fromObject({ type: e, ...t }, { extraParam: n, ...r } = {}) {
		return ni(t, r).then((e) => n ? (delete e[n], new this(t[n], e)) : new this(e));
	}
	static fromObject(e, t) {
		return this._fromObject(e, t);
	}
};
H(Bo, "stateProperties", Ga), H(Bo, "cacheProperties", Ka), H(Bo, "ownDefaults", qa), H(Bo, "type", "FabricObject"), H(Bo, "colorProperties", [
	pr,
	mr,
	"backgroundColor"
]), H(Bo, "customProperties", []), K.setClass(Bo), K.setClass(Bo, "object");
var Vo = (e, t) => {
	var n;
	let { transform: { target: r } } = t;
	(n = r.canvas) == null || n.fire(`object:${e}`, {
		...t,
		target: r
	}), r.fire(e, t);
}, Ho = (e, t, n) => (r, i, a, o) => {
	let s = t(r, i, a, o);
	return s && Vo(e, {
		...ia(r, i, a, o),
		...n
	}), s;
};
function Uo(e) {
	return (t, n, r, i) => {
		let { target: a, originX: o, originY: s } = n, c = a.getPositionByOrigin(o, s), l = e(t, n, r, i);
		return a.setPositionByOrigin(c, n.originX, n.originY), l;
	};
}
var Wo = (e, t, n, r) => (i, a, o, s) => {
	let c = oa(a, a.originX, a.originY, o, s)[n], l = Vi(a[t]);
	if (l === 0 || l > 0 && c < 0 || l < 0 && c > 0) {
		let { target: t } = a, n = t.strokeWidth / (t.strokeUniform ? t[r] : 1), i = ta(a) ? 2 : 1, o = t[e], s = Math.abs(c * i / t[r]) - n;
		return t.set(e, Math.max(s, 1)), o !== t[e];
	}
	return !1;
}, Go = Wo("width", "originX", "x", "scaleX"), Ko = Wo("height", "originY", "y", "scaleY"), qo = Ho(ar, Uo(Go)), Jo = Ho(ar, Uo(Ko));
function Yo(e, t, n, r, i) {
	e.save();
	let { stroke: a, xSize: o, ySize: s, opName: c } = this.commonRenderProps(e, t, n, i, r), l = o;
	o > s ? e.scale(1, s / o) : s > o && (l = s, e.scale(o / s, 1)), e.beginPath(), e.arc(0, 0, l / 2, 0, qn, !1), e[c](), a && e.stroke(), e.restore();
}
function Xo(e, t, n, r, i) {
	e.save();
	let { stroke: a, xSize: o, ySize: s, opName: c } = this.commonRenderProps(e, t, n, i, r), l = o / 2, u = s / 2;
	e[`${c}Rect`](-l, -u, o, s), a && e.strokeRect(-l, -u, o, s), e.restore();
}
var Zo = class {
	constructor(e) {
		H(this, "visible", !0), H(this, "actionName", cr), H(this, "angle", 0), H(this, "x", 0), H(this, "y", 0), H(this, "offsetX", 0), H(this, "offsetY", 0), H(this, "sizeX", 0), H(this, "sizeY", 0), H(this, "touchSizeX", 0), H(this, "touchSizeY", 0), H(this, "cursorStyle", "crosshair"), H(this, "withConnection", !1), Object.assign(this, e);
	}
	getTransformAnchorPoint() {
		return this.transformAnchorPoint ?? new q(.5 - this.x, .5 - this.y);
	}
	shouldActivate(e, t, n, { tl: r, tr: i, br: a, bl: o }) {
		return t.canvas?.getActiveObject() === t && t.isControlVisible(e) && Ro.isPointInPolygon(n, [
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
		let o = Vr([
			Kr(n, r),
			qr({ angle: e }),
			Jr((i ? this.touchSizeX : this.sizeX) || t, (i ? this.touchSizeY : this.sizeY) || t)
		]);
		return {
			tl: new q(-.5, -.5).transform(o),
			tr: new q(.5, -.5).transform(o),
			br: new q(.5, .5).transform(o),
			bl: new q(-.5, .5).transform(o)
		};
	}
	commonRenderProps(e, t, n, r, i = {}) {
		let { cornerSize: a, cornerColor: o, transparentCorners: s, cornerStrokeColor: c } = i, l = a || r.cornerSize, u = this.sizeX || l, d = this.sizeY || l, f = s === void 0 ? r.transparentCorners : s, p = f ? mr : pr, m = c || r.cornerStrokeColor, h = !f && !!m;
		return e.fillStyle = o || r.cornerColor || "", e.strokeStyle = m || "", e.translate(t, n), e.rotate(J(r.getTotalAngle())), {
			stroke: h,
			xSize: u,
			ySize: d,
			transparentCorners: f,
			opName: p
		};
	}
	render(e, t, n, r, i) {
		((r ||= {}).cornerStyle || i.cornerStyle) === "circle" ? Yo.call(this, e, t, n, r, i) : Xo.call(this, e, t, n, r, i);
	}
}, Qo = (e, t, n) => n.lockRotation ? ea : t.cursorStyle, $o = Ho(nr, Uo((e, { target: t, ex: n, ey: r, theta: i, originX: a, originY: o }, s, c) => {
	let l = t.getPositionByOrigin(a, o);
	if (ra(t, "lockRotation")) return !1;
	let u = Math.atan2(r - l.y, n - l.x), d = Lr(Math.atan2(c - l.y, s - l.x) - u + i);
	if (t.snapAngle && t.snapAngle > 0) {
		let e = t.snapAngle, n = t.snapThreshold || e, r = Math.ceil(d / e) * e, i = Math.floor(d / e) * e;
		Math.abs(d - i) < n ? d = i : Math.abs(d - r) < n && (d = r);
	}
	d < 0 && (d = 360 + d), d %= 360;
	let f = t.angle !== d;
	return t.angle = d, f;
}));
function es(e, t) {
	let n = t.canvas, r = e[n.uniScaleKey];
	return n.uniformScaling && !r || !n.uniformScaling && r;
}
function ts(e, t, n) {
	let r = ra(e, "lockScalingX"), i = ra(e, "lockScalingY");
	if (r && i || !t && (r || i) && n || r && t === "x" || i && t === "y") return !0;
	let { width: a, height: o, strokeWidth: s } = e;
	return a === 0 && s === 0 && t !== "y" || o === 0 && s === 0 && t !== "x";
}
var ns = [
	"e",
	"se",
	"s",
	"sw",
	"w",
	"nw",
	"n",
	"ne",
	"e"
], rs = (e, t, n, r) => {
	let i = es(e, n);
	return ts(n, t.x !== 0 && t.y === 0 ? "x" : t.x === 0 && t.y !== 0 ? "y" : "", i) ? ea : `${ns[aa(n, 0, r)]}-resize`;
};
function is(e, t, n, r, i = {}) {
	let a = t.target, o = i.by, s = es(e, a), c, l, u, d, f, p;
	if (ts(a, o, s)) return !1;
	if (t.gestureScale) l = t.scaleX * t.gestureScale, u = t.scaleY * t.gestureScale;
	else {
		if (c = oa(t, t.originX, t.originY, n, r), f = o === "y" ? 1 : Math.sign(c.x || t.signX || 1), p = o === "x" ? 1 : Math.sign(c.y || t.signY || 1), t.signX ||= f, t.signY ||= p, ra(a, "lockScalingFlip") && (t.signX !== f || t.signY !== p)) return !1;
		if (d = a._getTransformedDimensions(), s && !o) {
			let e = Math.abs(c.x) + Math.abs(c.y), { original: n } = t, r = e / (Math.abs(d.x * n.scaleX / a.scaleX) + Math.abs(d.y * n.scaleY / a.scaleY));
			l = n.scaleX * r, u = n.scaleY * r;
		} else l = Math.abs(c.x * a.scaleX / d.x), u = Math.abs(c.y * a.scaleY / d.y);
		ta(t) && (l *= 2, u *= 2), t.signX !== f && o !== "y" && (t.originX = na(t.originX), l *= -1, t.signX = f), t.signY !== p && o !== "x" && (t.originY = na(t.originY), u *= -1, t.signY = p);
	}
	let m = a.scaleX, h = a.scaleY;
	return o ? (o === "x" && a.set("scaleX", l), o === "y" && a.set("scaleY", u)) : (!ra(a, "lockScalingX") && a.set("scaleX", l), !ra(a, "lockScalingY") && a.set("scaleY", u)), m !== a.scaleX || h !== a.scaleY;
}
var as = Ho(tr, Uo((e, t, n, r) => is(e, t, n, r))), os = Ho(tr, Uo((e, t, n, r) => is(e, t, n, r, { by: "x" }))), ss = Ho(tr, Uo((e, t, n, r) => is(e, t, n, r, { by: "y" }))), cs = {
	x: {
		counterAxis: "y",
		scale: lr,
		skew: dr,
		lockSkewing: "lockSkewingX",
		origin: "originX",
		flip: "flipX"
	},
	y: {
		counterAxis: "x",
		scale: ur,
		skew: fr,
		lockSkewing: "lockSkewingY",
		origin: "originY",
		flip: "flipY"
	}
}, ls = [
	"ns",
	"nesw",
	"ew",
	"nwse"
], us = (e, t, n, r) => t.x !== 0 && ra(n, "lockSkewingY") || t.y !== 0 && ra(n, "lockSkewingX") ? ea : `${ls[aa(n, 0, r) % 4]}-resize`;
function ds(e, t, n, r, i) {
	let { target: a } = n, { counterAxis: o, origin: s, lockSkewing: c, skew: l, flip: u } = cs[e];
	if (ra(a, c)) return !1;
	let { origin: d, flip: f } = cs[o], p = Vi(n[d]) * (a[f] ? -1 : 1), m = -Math.sign(p) * (a[u] ? -1 : 1), h = -(a[l] === 0 && oa(n, "center", "center", r, i)[e] > 0 || a[l] > 0 ? 1 : -1) * m * .5 + .5;
	return Ho(ir, Uo((t, n, r, i) => function(e, { target: t, ex: n, ey: r, skewingSide: i, ...a }, o) {
		let { skew: s } = cs[e], c = o.subtract(new q(n, r)).divide(new q(t.scaleX, t.scaleY))[e], l = t[s], u = a[s], d = Math.tan(J(u)), f = e === "y" ? t._getTransformedDimensions({
			scaleX: 1,
			scaleY: 1,
			skewX: 0
		}).x : t._getTransformedDimensions({
			scaleX: 1,
			scaleY: 1
		}).y, p = 2 * c * i / Math.max(f, 1) + d, m = Lr(Math.atan(p));
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
var fs = (e, t, n, r) => ds("x", e, t, n, r), ps = (e, t, n, r) => ds("y", e, t, n, r);
function ms(e, t) {
	return e[t.canvas.altActionKey];
}
var hs = (e, t, n) => {
	let r = ms(e, n);
	return t.x === 0 ? r ? dr : ur : t.y === 0 ? r ? fr : lr : "";
}, gs = (e, t, n, r) => ms(e, n) ? us(0, t, n, r) : rs(e, t, n, r), _s = (e, t, n, r) => ms(e, t.target) ? ps(e, t, n, r) : os(e, t, n, r), vs = (e, t, n, r) => ms(e, t.target) ? fs(e, t, n, r) : ss(e, t, n, r), ys = () => ({
	ml: new Zo({
		x: -.5,
		y: 0,
		cursorStyleHandler: gs,
		actionHandler: _s,
		getActionName: hs
	}),
	mr: new Zo({
		x: .5,
		y: 0,
		cursorStyleHandler: gs,
		actionHandler: _s,
		getActionName: hs
	}),
	mb: new Zo({
		x: 0,
		y: .5,
		cursorStyleHandler: gs,
		actionHandler: vs,
		getActionName: hs
	}),
	mt: new Zo({
		x: 0,
		y: -.5,
		cursorStyleHandler: gs,
		actionHandler: vs,
		getActionName: hs
	}),
	tl: new Zo({
		x: -.5,
		y: -.5,
		cursorStyleHandler: rs,
		actionHandler: as
	}),
	tr: new Zo({
		x: .5,
		y: -.5,
		cursorStyleHandler: rs,
		actionHandler: as
	}),
	bl: new Zo({
		x: -.5,
		y: .5,
		cursorStyleHandler: rs,
		actionHandler: as
	}),
	br: new Zo({
		x: .5,
		y: .5,
		cursorStyleHandler: rs,
		actionHandler: as
	}),
	mtr: new Zo({
		x: 0,
		y: -.5,
		actionHandler: $o,
		cursorStyleHandler: Qo,
		offsetY: -40,
		withConnection: !0,
		actionName: rr
	})
}), bs = () => ({
	mr: new Zo({
		x: .5,
		y: 0,
		actionHandler: qo,
		cursorStyleHandler: gs,
		actionName: ar
	}),
	ml: new Zo({
		x: -.5,
		y: 0,
		actionHandler: qo,
		cursorStyleHandler: gs,
		actionName: ar
	})
}), xs = () => ({
	...ys(),
	...bs()
}), Ss = class e extends Bo {
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
		return { controls: ys() };
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
		let e = this.getViewportTransform(), t = Ur(e), n = Wr(e), r = this.getCenterPoint(), i = Y(Y(e, Y(Kr(r.x, r.y), qr({ angle: this.getTotalAngle() - (this.group && this.flipX ? 180 : 0) }))), [
			1 / t,
			0,
			0,
			1 / n,
			0,
			0
		]), a = this.group ? Gr(this.calcTransformMatrix()) : void 0;
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
		}, a = this.getViewportTransform(), o = i.hasBorders, s = i.hasControls, c = Gr(Y(a, this.calcTransformMatrix()));
		e.save(), e.translate(c.translateX, c.translateY), e.lineWidth = this.borderScaleFactor, this.group === this.parent && (e.globalAlpha = this.isMoving ? this.borderOpacityWhenMoving : 1), this.flipX && (c.angle -= 180);
		let l = Hr(a);
		e.rotate(this.group ? J(c.angle) : J(this.angle) + l), o && this.drawBorders(e, c, t), s && this.drawControls(e, t), e.restore();
	}
	drawBorders(e, t, n) {
		let r;
		if (n && n.forActiveSelection || this.group) {
			let e = Fi(this.width, this.height, Qr(t)), n = this.isStrokeAccountedForInDimensions() ? Cr : (this.strokeUniform ? new q().scalarAdd(this.canvas ? this.canvas.getZoom() : 1) : new q(t.scaleX, t.scaleY)).scalarMultiply(this.strokeWidth);
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
function Cs(e, t) {
	return t.forEach((t) => {
		Object.getOwnPropertyNames(t.prototype).forEach((n) => {
			n !== "constructor" && Object.defineProperty(e.prototype, n, Object.getOwnPropertyDescriptor(t.prototype, n) || Object.create(null));
		});
	}), e;
}
H(Ss, "ownDefaults", {
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
var ws = class extends Ss {};
Cs(ws, [Ca]), K.setClass(ws), K.setClass(ws, "object");
var Ts = (e, t, n, r) => {
	let i = 2 * (r = Math.round(r)) + 1, { data: a } = e.getImageData(t - r, n - r, i, i);
	for (let e = 3; e < a.length; e += 4) if (a[e] > 0) return !1;
	return !0;
}, Es = class {
	constructor(e) {
		this.options = e, this.strokeProjectionMagnitude = this.options.strokeWidth / 2, this.scale = new q(this.options.scaleX, this.options.scaleY), this.strokeUniformScalar = this.options.strokeUniform ? new q(1 / this.options.scaleX, 1 / this.options.scaleY) : new q(1, 1);
	}
	createSideVector(e, t) {
		let n = Gi(e, t);
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
}, Ds = new q(), Os = class e extends Es {
	static getOrthogonalRotationFactor(e, t) {
		let n = t ? qi(e, t) : Ji(e);
		return Math.abs(n) < Gn ? -1 : 1;
	}
	constructor(e, t, n, r) {
		super(r), H(this, "AB", void 0), H(this, "AC", void 0), H(this, "alpha", void 0), H(this, "bisector", void 0), this.A = new q(e), this.B = new q(t), this.C = new q(n), this.AB = this.createSideVector(this.A, this.B), this.AC = this.createSideVector(this.A, this.C), this.alpha = qi(this.AB, this.AC), this.bisector = Yi(Wi(this.AB.eq(Ds) ? this.AC : this.AB, this.alpha / 2));
	}
	calcOrthogonalProjection(t, n, r = this.strokeProjectionMagnitude) {
		let i = Xi(this.createSideVector(t, n)), a = e.getOrthogonalRotationFactor(i, this.bisector);
		return this.scaleUnitVector(i, r * a);
	}
	projectBevel() {
		let e = [];
		return (this.alpha % qn === 0 ? [this.B] : [this.B, this.C]).forEach((t) => {
			e.push(this.projectOrthogonally(this.A, t)), e.push(this.projectOrthogonally(this.A, t, -this.strokeProjectionMagnitude));
		}), e;
	}
	projectMiter() {
		let e = [], t = Math.abs(this.alpha), n = 1 / Math.sin(t / 2), r = this.scaleUnitVector(this.bisector, -this.strokeProjectionMagnitude * n), i = this.options.strokeUniform ? Ki(this.scaleUnitVector(this.bisector, this.options.strokeMiterLimit)) : this.options.strokeMiterLimit;
		return Ki(r) / this.strokeProjectionMagnitude <= i && e.push(this.applySkew(this.A.add(r))), e.push(...this.projectBevel()), e;
	}
	projectRoundNoSkew(t, n) {
		let r = [], i = new q(e.getOrthogonalRotationFactor(this.bisector), e.getOrthogonalRotationFactor(new q(this.bisector.y, this.bisector.x)));
		return [new q(1, 0).scalarMultiply(this.strokeProjectionMagnitude).multiply(this.strokeUniformScalar).multiply(i), new q(0, 1).scalarMultiply(this.strokeProjectionMagnitude).multiply(this.strokeUniformScalar).multiply(i)].forEach((e) => {
			$i(e, t, n) && r.push(this.A.add(e));
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
			$i(r, e, t) && n.push(this.applySkew(this.A).add(r));
		}), n;
	}
	projectRound() {
		let e = [];
		e.push(...this.projectBevel());
		let t = this.alpha % qn === 0, n = this.applySkew(this.A), r = e[t ? 0 : 2].subtract(n), i = e[+!!t].subtract(n), a = Zi(r, t ? this.applySkew(this.AB.scalarMultiply(-1)) : this.applySkew(this.bisector.multiply(this.strokeUniformScalar).scalarMultiply(-1))) > 0, o = a ? r : i, s = a ? i : r;
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
}, ks = class extends Es {
	constructor(e, t, n) {
		super(n), this.A = new q(e), this.T = new q(t);
	}
	calcOrthogonalProjection(e, t, n = this.strokeProjectionMagnitude) {
		let r = this.createSideVector(e, t);
		return this.scaleUnitVector(Xi(r), n);
	}
	projectButt() {
		return [this.projectOrthogonally(this.A, this.T, this.strokeProjectionMagnitude), this.projectOrthogonally(this.A, this.T, -this.strokeProjectionMagnitude)];
	}
	projectRound() {
		let e = [];
		if (!this.isSkewed() && this.A.eq(this.T)) {
			let t = new q(1, 1).scalarMultiply(this.strokeProjectionMagnitude).multiply(this.strokeUniformScalar);
			e.push(this.applySkew(this.A.add(t)), this.applySkew(this.A.subtract(t)));
		} else e.push(...new Os(this.A, this.T, this.T, this.options).projectRound());
		return e;
	}
	projectSquare() {
		let e = [];
		if (this.A.eq(this.T)) {
			let t = new q(1, 1).scalarMultiply(this.strokeProjectionMagnitude).multiply(this.strokeUniformScalar);
			e.push(this.A.add(t), this.A.subtract(t));
		} else {
			let t = this.calcOrthogonalProjection(this.A, this.T, this.strokeProjectionMagnitude), n = this.scaleUnitVector(Yi(this.createSideVector(this.A, this.T)), -this.strokeProjectionMagnitude), r = this.A.add(n);
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
}, As = (e, t, n = !1) => {
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
		i === 0 ? (s = a[1], o = n ? e : a[a.length - 1]) : i === a.length - 1 ? (o = a[i - 1], s = n ? e : a[0]) : (o = a[i - 1], s = a[i + 1]), n && a.length === 1 ? r.push(...new ks(e, e, t).project()) : !n || i !== 0 && i !== a.length - 1 ? r.push(...new Os(e, o, s, t).project()) : r.push(...new ks(e, i === 0 ? s : o, t).project());
	}), r;
}, js = (e) => {
	let t = {};
	return Object.keys(e).forEach((n) => {
		t[n] = {}, Object.keys(e[n]).forEach((r) => {
			t[n][r] = { ...e[n][r] };
		});
	}), t;
}, Ms = (e, t, n = !1) => e.fill !== t.fill || e.stroke !== t.stroke || e.strokeWidth !== t.strokeWidth || e.fontSize !== t.fontSize || e.fontFamily !== t.fontFamily || e.fontWeight !== t.fontWeight || e.fontStyle !== t.fontStyle || e.textDecorationThickness !== t.textDecorationThickness || e.textDecorationColor !== t.textDecorationColor || e.textBackgroundColor !== t.textBackgroundColor || e.deltaY !== t.deltaY || n && (e.overline !== t.overline || e.underline !== t.underline || e.linethrough !== t.linethrough), Ns = (e, t) => {
	let n = t.split("\n"), r = [], i = -1, a = {};
	e = js(e);
	for (let t = 0; t < n.length; t++) {
		let o = xi(n[t]);
		if (e[t]) for (let n = 0; n < o.length; n++) {
			i++;
			let o = e[t][n];
			o && Object.keys(o).length > 0 && (Ms(a, o, !0) ? r.push({
				start: i,
				end: i + 1,
				style: o
			}) : r[r.length - 1].end++), a = o || {};
		}
		else i += o.length, a = {};
	}
	return r;
}, Ps = (e, t) => {
	if (!Array.isArray(e)) return js(e);
	let n = t.split($n), r = {}, i = -1, a = 0;
	for (let t = 0; t < n.length; t++) {
		let o = xi(n[t]);
		for (let n = 0; n < o.length; n++) i++, e[a] && e[a].start <= i && i < e[a].end && (r[t] = r[t] || {}, r[t][n] = { ...e[a].style }, i === e[a].end - 1 && a++);
	}
	return r;
}, Fs = [
	"display",
	"transform",
	pr,
	"fill-opacity",
	"fill-rule",
	"opacity",
	mr,
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
function Is(e, t) {
	let n = e.nodeName, r = e.getAttribute("class"), i = e.getAttribute("id"), a = "(?![a-zA-Z\\-]+)", o;
	if (o = RegExp("^" + n, "i"), t = t.replace(o, ""), i && t.length && (o = RegExp("#" + i + a, "i"), t = t.replace(o, "")), r && t.length) {
		let e = r.split(" ");
		for (let n = e.length; n--;) o = RegExp("\\." + e[n] + a, "i"), t = t.replace(o, "");
	}
	return t.length === 0;
}
function Ls(e, t) {
	let n = !0, r = Is(e, t.pop());
	return r && t.length && (n = function(e, t) {
		let n, r = !0;
		for (; e.parentElement && e.parentElement.nodeType === 1 && t.length;) r && (n = t.pop()), r = Is(e = e.parentElement, n);
		return t.length === 0;
	}(e, t)), r && n && t.length === 0;
}
function Rs(e, t = {}) {
	let n = {};
	for (let r in t) Ls(e, r.split(" ")) && (n = {
		...n,
		...t[r]
	});
	return n;
}
var zs = (e) => La[e] ?? e, Bs = RegExp(`(${Pa})`, "gi"), Vs = `(${Pa})`, Hs = String.raw`(skewX)\(${Vs}\)`, Us = String.raw`(skewY)\(${Vs}\)`, Ws = String.raw`(rotate)\(${Vs}(?: ${Vs} ${Vs})?\)`, Gs = String.raw`(scale)\(${Vs}(?: ${Vs})?\)`, Ks = String.raw`(translate)\(${Vs}(?: ${Vs})?\)`, qs = `(?:${String.raw`(matrix)\(${Vs} ${Vs} ${Vs} ${Vs} ${Vs} ${Vs}\)`}|${Ks}|${Ws}|${Gs}|${Hs}|${Us})`, Js = `(?:${qs}*)`, Ys = String.raw`^\s*(?:${Js}?)\s*$`, Xs = new RegExp(Ys), Zs = new RegExp(qs), Qs = new RegExp(qs, "g");
function $s(e) {
	let t = [];
	if (!(e = ((e) => da(e.replace(Bs, " $1 ").replace(/,/gi, " ")))(e).replace(/\s*([()])\s*/gi, "$1")) || e && !Xs.test(e)) return [...Yn];
	for (let n of e.matchAll(Qs)) {
		let e = Zs.exec(n[0]);
		if (!e) continue;
		let r = Yn, [, i, ...a] = e.filter((e) => !!e), [o, s, c, l, u, d] = a.map((e) => parseFloat(e));
		switch (i) {
			case "translate":
				r = Kr(o, s);
				break;
			case rr:
				r = qr({ angle: o }, {
					x: s,
					y: c
				});
				break;
			case cr:
				r = Jr(o, s);
				break;
			case dr:
				r = Xr(o);
				break;
			case fr:
				r = Zr(o);
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
	return Vr(t);
}
function ec(e, t, n, r) {
	let i = Array.isArray(t), a, o = t;
	if (e !== "fill" && e !== "stroke" || t !== "none") {
		if (e === "strokeUniform") return t === "non-scaling-stroke";
		if (e === "strokeDashArray") o = t === "none" ? null : t.replace(/,/g, " ").split(/\s+/).map(parseFloat);
		else if (e === "transformMatrix") o = n && n.transformMatrix ? Y(n.transformMatrix, $s(t)) : $s(t);
		else if (e === "visible") o = t !== "none" && t !== "hidden", n && !1 === n.visible && (o = !1);
		else if (e === "opacity") o = parseFloat(t), n && n.opacity !== void 0 && (o *= n.opacity);
		else if (e === "textAnchor") o = t === "start" ? G : t === "end" ? Zn : W;
		else if (e === "charSpacing" || e === "textDecorationThickness") a = ba(t, r) / r * 1e3;
		else if (e === "paintFirst") {
			let e = t.indexOf(pr), n = t.indexOf(mr);
			o = pr, (e > -1 && n > -1 && n < e || e === -1 && n > -1) && (o = mr);
		} else {
			if (e === "href" || e === "xlink:href" || e === "font" || e === "id") return t;
			if (e === "imageSmoothing") return t === "optimizeQuality";
			a = i ? t.map(ba) : ba(t, r);
		}
	} else o = "";
	return !i && isNaN(a) ? o : a;
}
function tc(e, t) {
	e.replace(/;\s*$/, "").split(";").forEach((e) => {
		if (!e) return;
		let [n, r] = e.split(":");
		t[n.trim().toLowerCase()] = r.trim();
	});
}
function nc(e) {
	let t = {}, n = e.getAttribute("style");
	return n && (typeof n == "string" ? tc(n, t) : function(e, t) {
		Object.entries(e).forEach(([e, n]) => {
			n !== void 0 && (t[e.toLowerCase()] = n);
		});
	}(n, t)), t;
}
var rc = {
	stroke: "strokeOpacity",
	fill: "fillOpacity"
};
function ic(e, t, n) {
	if (!e) return {};
	let r, i = {}, a = 16;
	e.parentNode && Ba.test(e.parentNode.nodeName) && (i = ic(e.parentElement, t, n), i.fontSize && (r = a = ba(i.fontSize)));
	let o = {
		...t.reduce((t, n) => {
			let r = e.getAttribute(n);
			return r && (t[n] = r), t;
		}, {}),
		...Rs(e, n),
		...nc(e)
	};
	o["clip-path"] && e.setAttribute(za, o[za]), o["font-size"] && (r = ba(o[Ra], a), o[Ra] = `${r}`);
	let s = {};
	for (let e in o) {
		let t = zs(e);
		s[t] = ec(t, o[e], i, r);
	}
	s && s.font && function(e, t) {
		let n = e.match(Ia);
		if (!n) return;
		let r = n[1], i = n[3], a = n[4], o = n[5], s = n[6];
		r && (t.fontStyle = r), i && (t.fontWeight = isNaN(parseFloat(i)) ? i : parseFloat(i)), a && (t.fontSize = ba(a)), s && (t.fontFamily = s), o && (t.lineHeight = o === "normal" ? 1 : o);
	}(s.font, s);
	let c = {
		...i,
		...s
	};
	return Ba.test(e.nodeName) ? c : function(e) {
		let t = ws.getDefaults();
		return Object.entries(rc).forEach(([n, r]) => {
			if (e[r] === void 0 || e[n] === "") return;
			if (e[n] === void 0) {
				if (!t[n]) return;
				e[n] = t[n];
			}
			if (e[n].indexOf("url(") === 0) return;
			let i = new va(e[n]);
			e[n] = i.setAlpha(X(i.getAlpha() * e[r], 2)).toRgba();
		}), e;
	}(c);
}
var ac = ["rx", "ry"], oc = class e extends ws {
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
		return super.toObject([...ac, ...e]);
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
		let { left: r = 0, top: i = 0, width: a = 0, height: o = 0, visible: s = !0, ...c } = ic(e, this.ATTRIBUTE_NAMES, n);
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
H(oc, "type", "Rect"), H(oc, "cacheProperties", [...Ka, ...ac]), H(oc, "ownDefaults", {
	rx: 0,
	ry: 0
}), H(oc, "ATTRIBUTE_NAMES", [
	...Fs,
	"x",
	"y",
	"rx",
	"ry",
	"width",
	"height"
]), K.setClass(oc), K.setSVGClass(oc);
var sc = "initialization", cc = "added", lc = (e, t) => {
	let { strokeUniform: n, strokeWidth: r, width: i, height: a, group: o } = t, s = o && o !== e ? Ii(o.calcTransformMatrix(), e.calcTransformMatrix()) : null, c = s ? t.getRelativeCenterPoint().transform(s) : t.getRelativeCenterPoint(), l = !t.isStrokeAccountedForInDimensions(), u = n && l ? Ri(new q(r, r), void 0, e.calcTransformMatrix()) : Cr, d = !n && l ? r : 0, f = Fi(i + d, a + d, Vr([s, t.calcOwnMatrix()], !0)).add(u).scalarDivide(2);
	return [c.subtract(f), c.add(f)];
}, uc = class {
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
		let { left: i, top: a, width: o, height: s } = ki(e.map((e) => lc(r, e)).reduce((e, t) => e.concat(t), [])), c = new q(o, s), l = new q(i, a).add(c.scalarDivide(2));
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
H(uc, "type", "strategy");
var dc = class extends uc {
	shouldPerformLayout(e) {
		return !0;
	}
};
H(dc, "type", "fit-content"), K.setClass(dc);
var fc = "layoutManager", pc = class {
	constructor(e = new dc()) {
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
			hr,
			er,
			ar,
			nr,
			tr,
			ir,
			sr,
			or,
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
			offset: a.subtract(o).add(s).transform(r === "initialization" ? Yn : Br(t.calcOwnMatrix()), !0).add(c)
		};
	}
	commitLayout(e, t) {
		let { target: n } = e, { result: { size: r }, nextCenter: i } = t;
		n.set({
			width: r.x,
			height: r.y
		}), this.layoutObjects(e, t), e.type === "initialization" ? n.set({
			left: e.x ?? i.x + r.x * Vi(n.originX),
			top: e.y ?? i.y + r.y * Vi(n.originY)
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
			type: fc,
			strategy: this.strategy.constructor.type
		};
	}
	toJSON() {
		return this.toObject();
	}
};
K.setClass(pc, fc);
var mc = class extends pc {
	performLayout() {}
}, hc = class e extends Tr(ws) {
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
		}), this.layoutManager = t.layoutManager ?? new pc(), this.layoutManager.performLayout({
			type: sc,
			target: this,
			targets: [...e],
			x: t.left,
			y: t.top
		});
	}
	canEnterGroup(e) {
		return e === this || this.isDescendantOf(e) ? (jn("error", "Group: circular object trees are not supported, this call has no effect"), !1) : this._objects.indexOf(e) === -1 || (jn("error", "Group: duplicate objects are not supported inside group, this call has no effect"), !1);
	}
	_filterObjectsBeforeEnteringGroup(e) {
		return e.filter((e, t, n) => this.canEnterGroup(e) && n.indexOf(e) === t);
	}
	add(...e) {
		let t = this._filterObjectsBeforeEnteringGroup(e), n = super.add(...t);
		return this._onAfterObjectsChange(cc, t), n;
	}
	insertAt(e, ...t) {
		let n = this._filterObjectsBeforeEnteringGroup(t), r = super.insertAt(e, ...n);
		return this._onAfterObjectsChange(cc, n), r;
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
		t && Mi(e, Y(Br(this.calcTransformMatrix()), e.calcTransformMatrix())), this._shouldSetNestedCoords() && e.setCoords(), e._set("group", this), e._set("canvas", this.canvas), this._watchObject(!0, e);
		let n = this.canvas && this.canvas.getActiveObject && this.canvas.getActiveObject();
		n && (n === e || e.isDescendantOf(n)) && this._activeObjects.push(e);
	}
	exitGroup(e, t) {
		this._exitGroup(e, t), e._set("parent", void 0), e._set("canvas", void 0);
	}
	_exitGroup(e, t) {
		e._set("group", void 0), t || (Mi(e, Y(this.calcTransformMatrix(), e.calcTransformMatrix())), e.setCoords()), this._watchObject(!1, e);
		let n = this._activeObjects.length > 0 ? this._activeObjects.indexOf(e) : -1;
		n > -1 && this._activeObjects.splice(n, 1);
	}
	shouldCache() {
		let e = ws.prototype.shouldCache.call(this);
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
			(r = this.canvas) != null && r.preserveObjectStacking && n.group !== this ? (e.save(), e.transform(...Br(this.calcTransformMatrix())), n.render(e), e.restore()) : n.group === this && n.render(e);
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
		let t = oc.prototype._toSVG.call(this), n = t.indexOf("COMMON_PARTS");
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
		return Promise.all([ti(t, i), ni(r, i)]).then(([e, t]) => {
			let i = new this(e, {
				...r,
				...t,
				layoutManager: new mc()
			});
			return i.layoutManager = n ? new (K.getClass(n.type))(new (K.getClass(n.strategy))()) : new pc(), i.layoutManager.subscribeTargets({
				type: sc,
				target: i,
				targets: i.getObjects()
			}), i.setCoords(), i;
		});
	}
};
H(hc, "type", "Group"), H(hc, "ownDefaults", {
	strokeWidth: 0,
	subTargetCheck: !1,
	interactive: !1
}), K.setClass(hc);
var gc = (e, t) => e && e.length === 1 ? e[0] : new hc(e, t), _c = (e, t) => Math.min(t.width / e.width, t.height / e.height), vc = (e, t) => Math.max(t.width / e.width, t.height / e.height), yc = "\\s*,?\\s*", bc = `${yc}(${Pa})`, xc = `${bc}${bc}${bc}${yc}([01])${yc}([01])${bc}${bc}`, Sc = {
	m: "l",
	M: "L"
}, Cc = (e, t, n, r, i, a, o, s, c, l, u) => {
	let d = xr(e), f = Sr(e), p = xr(t), m = Sr(t), h = n * i * p - r * a * m + o, g = r * i * p + n * a * m + s;
	return [
		"C",
		l + c * (-n * i * f - r * a * d),
		u + c * (-r * i * f + n * a * d),
		h + c * (n * i * m + r * a * p),
		g + c * (r * i * m - n * a * p),
		h,
		g
	];
}, wc = (e, t, n, r) => {
	let i = Math.atan2(t, e), a = Math.atan2(r, n);
	return a >= i ? a - i : 2 * Math.PI - (i - a);
};
function Tc(e, t, n, r, i, a, o, s) {
	let c;
	if (U.cachesBoundsOfCurve && (c = [...arguments].join(), Hn.boundsOfCurveCache[c])) return Hn.boundsOfCurveCache[c];
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
	let g = d.length, _ = g, v = kc(e, t, n, r, i, a, o, s);
	for (; g--;) {
		let { x: e, y: t } = v(d[g]);
		f[0][g] = e, f[1][g] = t;
	}
	f[0][_] = e, f[1][_] = t, f[0][_ + 1] = o, f[1][_ + 1] = s;
	let y = [new q(Math.min(...f[0]), Math.min(...f[1])), new q(Math.max(...f[0]), Math.max(...f[1]))];
	return U.cachesBoundsOfCurve && (Hn.boundsOfCurveCache[c] = y), y;
}
var Ec = (e, t, [n, r, i, a, o, s, c, l]) => {
	let u = ((e, t, n, r, i, a, o) => {
		if (n === 0 || r === 0) return [];
		let s = 0, c = 0, l = 0, u = Math.PI, d = o * Jn, f = Sr(d), p = xr(d), m = .5 * (-p * e - f * t), h = .5 * (-p * t + f * e), g = n ** 2, _ = r ** 2, v = h ** 2, y = m ** 2, b = g * _ - g * v - _ * y, x = Math.abs(n), S = Math.abs(r);
		if (b < 0) {
			let e = Math.sqrt(1 - b / (g * _));
			x *= e, S *= e;
		} else l = (i === a ? -1 : 1) * Math.sqrt(b / (g * v + _ * y));
		let C = l * x * h / S, w = -l * S * m / x, T = p * C - f * w + .5 * e, E = f * C + p * w + .5 * t, ee = wc(1, 0, (m - C) / x, (h - w) / S), D = wc((m - C) / x, (h - w) / S, (-m - C) / x, (-h - w) / S);
		a === 0 && D > 0 ? D -= 2 * u : a === 1 && D < 0 && (D += 2 * u);
		let O = Math.ceil(Math.abs(D / u * 2)), te = [], ne = D / O, re = 8 / 3 * Math.sin(ne / 4) * Math.sin(ne / 4) / Math.sin(ne / 2), ie = ee + ne;
		for (let e = 0; e < O; e++) te[e] = Cc(ee, ie, p, f, x, S, T, E, re, s, c), s = te[e][5], c = te[e][6], ee = ie, ie += ne;
		return te;
	})(c - e, l - t, r, i, o, s, a);
	for (let n = 0, r = u.length; n < r; n++) u[n][1] += e, u[n][2] += t, u[n][3] += e, u[n][4] += t, u[n][5] += e, u[n][6] += t;
	return u;
}, Dc = (e) => {
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
				Ec(t, n, e).forEach((e) => a.push(e)), t = e[6], n = e[7];
				break;
			case "z":
			case "Z": t = r, n = i, u = ["Z"];
		}
		u ? (a.push(u), o = u[0]) : o = "";
	}
	return a;
}, Oc = (e, t, n, r) => Math.sqrt((n - e) ** 2 + (r - t) ** 2), kc = (e, t, n, r, i, a, o, s) => (c) => {
	let l = c ** 3, u = ((e) => 3 * e ** 2 * (1 - e))(c), d = ((e) => 3 * e * (1 - e) ** 2)(c), f = ((e) => (1 - e) ** 3)(c);
	return new q(o * l + i * u + n * d + e * f, s * l + a * u + r * d + t * f);
}, Ac = (e) => e ** 2, jc = (e) => 2 * e * (1 - e), Mc = (e) => (1 - e) ** 2, Nc = (e, t, n, r, i, a, o, s) => (c) => {
	let l = Ac(c), u = jc(c), d = Mc(c), f = 3 * (d * (n - e) + u * (i - n) + l * (o - i)), p = 3 * (d * (r - t) + u * (a - r) + l * (s - a));
	return Math.atan2(p, f);
}, Pc = (e, t, n, r, i, a) => (o) => {
	let s = Ac(o), c = jc(o), l = Mc(o);
	return new q(i * s + n * c + e * l, a * s + r * c + t * l);
}, Fc = (e, t, n, r, i, a) => (o) => {
	let s = 1 - o, c = 2 * (s * (n - e) + o * (i - n)), l = 2 * (s * (r - t) + o * (a - r));
	return Math.atan2(l, c);
}, Ic = (e, t, n) => {
	let r = new q(t, n), i = 0;
	for (let t = 1; t <= 100; t += 1) {
		let n = e(t / 100);
		i += Oc(r.x, r.y, n.x, n.y), r = n;
	}
	return i;
}, Lc = (e, t) => {
	let n, r = 0, i = 0, a = {
		x: e.x,
		y: e.y
	}, o = { ...a }, s = .01, c = 0, l = e.iterator, u = e.angleFinder;
	for (; i < t && s > 1e-4;) o = l(r), c = r, n = Oc(a.x, a.y, o.x, o.y), n + i > t ? (r -= s, s /= 2) : (a = o, r += s, i += n);
	return {
		...o,
		angle: u(c)
	};
}, Rc = (e) => {
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
				n = e, n.length = Oc(i, a, l[1], l[2]), i = l[1], a = l[2];
				break;
			case "C":
				t = kc(i, a, l[1], l[2], l[3], l[4], l[5], l[6]), n = e, n.iterator = t, n.angleFinder = Nc(i, a, l[1], l[2], l[3], l[4], l[5], l[6]), n.length = Ic(t, i, a), i = l[5], a = l[6];
				break;
			case "Q":
				t = Pc(i, a, l[1], l[2], l[3], l[4]), n = e, n.iterator = t, n.angleFinder = Fc(i, a, l[1], l[2], l[3], l[4]), n.length = Ic(t, i, a), i = l[3], a = l[4];
				break;
			case "Z": n = e, n.destX = o, n.destY = s, n.length = Oc(i, a, o, s), i = o, a = s;
		}
		r += n.length, c.push(n);
	}
	return c.push({
		length: r,
		x: i,
		y: a
	}), c;
}, zc = (e, t, n = Rc(e)) => {
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
		case "Q": return Lc(i, t);
	}
}, Bc = RegExp("[mzlhvcsqta][^mzlhvcsqta]*", "gi"), Vc = new RegExp(xc, "g"), Hc = new RegExp(Pa, "gi"), Uc = {
	m: 2,
	l: 2,
	h: 1,
	v: 1,
	c: 6,
	s: 4,
	q: 4,
	t: 2,
	a: 7
}, Wc = (e) => {
	let t = [], n = e.match(Bc) ?? [];
	for (let e of n) {
		let n = e[0];
		if (n === "z" || n === "Z") {
			t.push([n]);
			continue;
		}
		let r = Uc[n.toLowerCase()], i = [];
		if (n === "a" || n === "A") {
			let t;
			for (Vc.lastIndex = 0; t = Vc.exec(e);) i.push(...t.slice(1));
		} else i = e.match(Hc) || [];
		for (let e = 0; e < i.length; e += r) {
			let a = Array(r), o = Sc[n];
			a[0] = e > 0 && o ? o : n;
			for (let t = 0; t < r; t++) a[t + 1] = parseFloat(i[e + t]);
			t.push(a);
		}
	}
	return t;
}, Gc = (e, t = 0) => {
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
}, Kc = (e, t, n) => (n && (t = Y(t, [
	1,
	0,
	0,
	1,
	-n.x,
	-n.y
])), e.map((e) => {
	let n = [...e];
	for (let r = 1; r < e.length - 1; r += 2) {
		let { x: i, y: a } = zr({
			x: e[r],
			y: e[r + 1]
		}, t);
		n[r] = i, n[r + 1] = a;
	}
	return n;
})), qc = (e, t) => {
	let n = 2 * Math.PI / e, r = -Gn;
	e % 2 == 0 && (r += n / 2);
	let i = Array(e + 1);
	for (let a = 0; a < e; a++) {
		let e = a * n + r, { x: o, y: s } = new q(xr(e), Sr(e)).scalarMultiply(t);
		i[a] = [
			a === 0 ? "M" : "L",
			o,
			s
		];
	}
	return i[e] = ["Z"], i;
}, Jc = (e, t) => e.map((e) => e.map((e, n) => n === 0 || t === void 0 ? e : X(e, t)).join(" ")).join(" "), Yc = (e, t) => {
	let n = e, r = t;
	n.inverted && !r.inverted && (n = t, r = e), zi(r, r.group?.calcTransformMatrix(), n.calcTransformMatrix());
	let i = n.inverted && r.inverted;
	return i && (n.inverted = r.inverted = !1), new hc([n], {
		clipPath: r,
		inverted: i
	});
}, Xc = (e, t) => Math.floor(Math.random() * (t - e + 1)) + e, Zc = (e, t) => {
	let n = e._findCenterFromElement();
	e.transformMatrix && (((e) => {
		if (e.transformMatrix) {
			let { scaleX: t, scaleY: n, angle: r, skewX: i } = Gr(e.transformMatrix);
			e.flipX = !1, e.flipY = !1, e.set(lr, t), e.set(ur, n), e.angle = r, e.skewX = i, e.skewY = 0;
		}
	})(e), n = n.transform(e.transformMatrix)), delete e.transformMatrix, t && (e.scaleX *= t.scaleX, e.scaleY *= t.scaleY, e.cropX = t.cropX, e.cropY = t.cropY, n.x += t.offsetLeft, n.y += t.offsetTop, e.width = t.width, e.height = t.height), e.setPositionByOrigin(n, W, W);
};
Dn({
	addTransformToObject: () => ji,
	animate: () => Io,
	animateColor: () => Lo,
	applyTransformToObject: () => Mi,
	calcAngleBetweenVectors: () => qi,
	calcDimensionsMatrix: () => Qr,
	calcPlaneChangeMatrix: () => Ii,
	calcVectorRotation: () => Ji,
	cancelAnimFrame: () => Or,
	capValue: () => Wa,
	composeMatrix: () => $r,
	copyCanvasElement: () => Nr,
	cos: () => xr,
	createCanvasElement: () => jr,
	createImage: () => Mr,
	createRotateMatrix: () => qr,
	createScaleMatrix: () => Jr,
	createSkewXMatrix: () => Xr,
	createSkewYMatrix: () => Zr,
	createTranslateMatrix: () => Kr,
	createVector: () => Gi,
	crossProduct: () => Zi,
	degreesToRadians: () => J,
	dotProduct: () => Qi,
	ease: () => Ja,
	enlivenObjectEnlivables: () => ni,
	enlivenObjects: () => ti,
	findScaleToCover: () => vc,
	findScaleToFit: () => _c,
	getBoundsOfCurve: () => Tc,
	getOrthonormalVector: () => Xi,
	getPathSegmentsInfo: () => Rc,
	getPointOnPath: () => zc,
	getPointer: () => Ei,
	getRandomInt: () => Xc,
	getRegularPolygonPath: () => qc,
	getSmoothPathFromPoints: () => Gc,
	getSvgAttributes: () => ya,
	getUnitVector: () => Yi,
	groupSVGElements: () => gc,
	hasStyleChanged: () => Ms,
	invertTransform: () => Br,
	isBetweenVectors: () => $i,
	isIdentityMatrix: () => Rr,
	isTouchEvent: () => Di,
	isTransparent: () => Ts,
	joinPath: () => Jc,
	loadImage: () => ei,
	magnitude: () => Ki,
	makeBoundingBoxFromPoints: () => ki,
	makePathSimpler: () => Dc,
	matrixToSVG: () => ai,
	mergeClipPaths: () => Yc,
	multiplyTransformMatrices: () => Y,
	multiplyTransformMatrixArray: () => Vr,
	parsePath: () => Wc,
	parsePreserveAspectRatioAttribute: () => xa,
	parseUnit: () => ba,
	pick: () => ri,
	projectStrokeOnPoints: () => As,
	qrDecompose: () => Gr,
	radiansToDegrees: () => Lr,
	removeFromArray: () => br,
	removeTransformFromObject: () => Ai,
	removeTransformMatrixForSvgParsing: () => Zc,
	requestAnimFrame: () => Dr,
	resetObjectTransform: () => Ni,
	rotateVector: () => Wi,
	saveObjectTransform: () => Pi,
	sendObjectToPlane: () => zi,
	sendPointToPlane: () => Li,
	sendVectorToPlane: () => Ri,
	sin: () => Sr,
	sizeAfterTransform: () => Fi,
	string: () => vi,
	stylesFromArray: () => Ps,
	stylesToArray: () => Ns,
	toBlob: () => Ir,
	toDataURL: () => Fr,
	toFixed: () => X,
	transformPath: () => Kc,
	transformPoint: () => zr
});
function Qc(e, t) {
	let n = e.style;
	n && Object.entries(t).forEach(([e, t]) => n.setProperty(e, t));
}
var $c = class extends gi {
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
		let { el: e } = this.lower, t = jr();
		return t.className = e.className, t.classList.remove("lower-canvas"), t.classList.add("upper-canvas"), t.setAttribute("data-fabric", "top"), t.style.cssText = e.style.cssText, t.setAttribute("draggable", "true"), t;
	}
	createContainerElement() {
		let e = zn().createElement("div");
		return e.setAttribute("data-fabric", "wrapper"), Qc(e, { position: "relative" }), hi(e), e;
	}
	applyCanvasStyle(e, t) {
		let { styles: n, allowTouchScrolling: r } = t;
		Qc(e, {
			...n,
			"touch-action": r ? "manipulation" : Qn
		}), hi(e);
	}
	setDimensions(e, t) {
		super.setDimensions(e, t);
		let { el: n, ctx: r } = this.upper;
		pi(n, r, e, t);
	}
	setCSSDimensions(e) {
		super.setCSSDimensions(e), mi(this.upper.el, e), mi(this.container, e);
	}
	cleanupDOM(e) {
		let t = this.container, { el: n } = this.lower, { el: r } = this.upper;
		super.cleanupDOM(e), t.removeChild(r), t.removeChild(n), t.parentNode && t.parentNode.replaceChild(n, t);
	}
	dispose() {
		super.dispose(), Rn().dispose(this.upper.el), delete this.upper, delete this.container;
	}
}, el = (e, t, n, r) => {
	let { target: i, offsetX: a, offsetY: o } = t, s = n - a, c = r - o, l = !ra(i, "lockMovementX") && i.left !== s, u = !ra(i, "lockMovementY") && i.top !== c;
	return l && i.set("left", s), u && i.set("top", c), (l || u) && Vo(er, ia(e, t, n, r)), l || u;
}, tl = or, nl = (e) => function(t, n, r) {
	let { points: i, pathOffset: a } = r;
	return new q(i[e]).subtract(a).transform(Y(r.getViewportTransform(), r.calcTransformMatrix()));
}, rl = (e, t, n, r) => {
	let { target: i, pointIndex: a } = t, o = i, s = Li(new q(n, r), void 0, o.calcOwnMatrix());
	return o.points[a] = s.add(o.pathOffset), o.setDimensions(), o.set("dirty", !0), !0;
}, il = (e, t) => function(n, r, i, a) {
	let o = r.target, s = new q(o.points[(e > 0 ? e : o.points.length) - 1]), c = s.subtract(o.pathOffset).transform(o.calcOwnMatrix()), l = t(n, {
		...r,
		pointIndex: e
	}, i, a), u = s.subtract(o.pathOffset).transform(o.calcOwnMatrix()).subtract(c);
	return o.left -= u.x, o.top -= u.y, l;
}, al = (e) => Ho(tl, il(e, rl));
function ol(e, t = {}) {
	let n = {};
	for (let r = 0; r < (typeof e == "number" ? e : e.points.length); r++) n[`p${r}`] = new Zo({
		actionName: tl,
		positionHandler: nl(r),
		actionHandler: al(r),
		...t
	});
	return n;
}
var sl = (e, t, n) => {
	let { path: r, pathOffset: i } = e, a = r[t];
	return new q(a[n] - i.x, a[n + 1] - i.y).transform(Y(e.getViewportTransform(), e.calcTransformMatrix()));
};
function cl(e, t, n) {
	let { commandIndex: r, pointIndex: i } = this;
	return sl(n, r, i);
}
function ll(e, t, n, r) {
	let { target: i } = t, { commandIndex: a, pointIndex: o } = this, s = ((e, t, n, r, i) => {
		let { path: a, pathOffset: o } = e, s = a[(r > 0 ? r : a.length) - 1], c = new q(s[i], s[i + 1]), l = c.subtract(o).transform(e.calcOwnMatrix()), u = Li(new q(t, n), void 0, e.calcOwnMatrix());
		a[r][i] = u.x + o.x, a[r][i + 1] = u.y + o.y, e.setDimensions();
		let d = c.subtract(e.pathOffset).transform(e.calcOwnMatrix()).subtract(l);
		return e.left -= d.x, e.top -= d.y, e.set("dirty", !0), !0;
	})(i, n, r, a, o);
	return s && Vo(this.actionName, {
		...ia(e, t, n, r),
		commandIndex: a,
		pointIndex: o
	}), s;
}
var ul = class extends Zo {
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
}, dl = class extends ul {
	constructor(e) {
		super(e);
	}
	render(e, t, n, r, i) {
		let { path: a } = i, { commandIndex: o, pointIndex: s, connectToCommandIndex: c, connectToPointIndex: l } = this;
		e.save(), e.strokeStyle = this.controlStroke, this.connectionDashArray && e.setLineDash(this.connectionDashArray);
		let [u] = a[o], d = sl(i, c, l);
		if (u === "Q") {
			let r = sl(i, o, s + 2);
			e.moveTo(r.x, r.y), e.lineTo(t, n);
		} else e.moveTo(t, n);
		e.lineTo(d.x, d.y), e.stroke(), e.restore(), super.render(e, t, n, r, i);
	}
}, fl = (e, t, n, r, i, a) => new (n ? dl : ul)({
	commandIndex: e,
	pointIndex: t,
	actionName: "modifyPath",
	positionHandler: cl,
	actionHandler: ll,
	connectToCommandIndex: i,
	connectToPointIndex: a,
	...r,
	...n ? r.controlPointStyle : r.pointStyle
});
function pl(e, t = {}) {
	let n = {}, r = "M";
	return e.path.forEach((e, i) => {
		let a = e[0];
		switch (a !== "Z" && (n[`c_${i}_${a}`] = fl(i, e.length - 2, !1, t)), a) {
			case "C":
				n[`c_${i}_C_CP_1`] = fl(i, 1, !0, t, i - 1, ((e) => e === "C" ? 5 : e === "Q" ? 3 : 1)(r)), n[`c_${i}_C_CP_2`] = fl(i, 3, !0, t, i, 5);
				break;
			case "Q": n[`c_${i}_Q_CP_1`] = fl(i, 1, !0, t, i, 3);
		}
		r = a;
	}), n;
}
Dn({
	changeHeight: () => Jo,
	changeObjectHeight: () => Ko,
	changeObjectWidth: () => Go,
	changeWidth: () => qo,
	createObjectDefaultControls: () => ys,
	createPathControls: () => pl,
	createPolyActionHandler: () => al,
	createPolyControls: () => ol,
	createPolyPositionHandler: () => nl,
	createResizeControls: () => bs,
	createTextboxDefaultControls: () => xs,
	dragHandler: () => el,
	factoryPolyActionHandler: () => il,
	getLocalPoint: () => oa,
	polyActionHandler: () => rl,
	renderCircleControl: () => Yo,
	renderSquareControl: () => Xo,
	rotationStyleHandler: () => Qo,
	rotationWithSnapping: () => $o,
	scaleCursorStyleHandler: () => rs,
	scaleOrSkewActionName: () => hs,
	scaleSkewCursorStyleHandler: () => gs,
	scalingEqually: () => as,
	scalingX: () => os,
	scalingXOrSkewingY: () => _s,
	scalingY: () => ss,
	scalingYOrSkewingX: () => vs,
	skewCursorStyleHandler: () => us,
	skewHandlerX: () => fs,
	skewHandlerY: () => ps,
	wrapWithFireEvent: () => Ho,
	wrapWithFixedAnchor: () => Uo
});
var ml = class e extends wi {
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
		this.elements = new $c(e, {
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
		return Ts(i, o, o, o);
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
		].includes(t) ? n.x = Zn : [
			"mr",
			"tr",
			"br"
		].includes(t) && (n.x = G), [
			"tl",
			"mt",
			"tr"
		].includes(t) ? n.y = Xn : [
			"bl",
			"mb",
			"br"
		].includes(t) && (n.y = "top"), n) : n;
	}
	_setupCurrentTransform(e, t, n) {
		let r = t.group ? Li(this.getScenePoint(e), void 0, t.group.calcTransformMatrix()) : this.getScenePoint(e), { key: i = "", control: a } = t.getActiveControl() || {}, o = n && a ? a.getActionHandler(e, t, a)?.bind(a) : el, s = ((e, t, n, r) => {
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
				...Pi(t),
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
		this.selectionColor && (e.fillStyle = this.selectionColor, e.fillRect(c, l, u - c, d - l)), this.selectionLineWidth && this.selectionBorderColor && (e.lineWidth = this.selectionLineWidth, e.strokeStyle = this.selectionBorderColor, c += s, l += s, u -= s, d -= s, ws.prototype._setLineDash.call(this, e, this.selectionDashArray), e.strokeRect(c, l, u - c, d - l));
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
		return n.findControl(this.getViewportPoint(e), Di(e)) ? {
			...l,
			target: n
		} : l.target && (r.length > 1 || !this.preserveObjectStacking || this.preserveObjectStacking && e[this.altSelectionKey]) ? l : c;
	}
	_pointIsInObjectSelectionArea(e, t) {
		let n = e.getCoords(), r = this.getZoom(), i = e.padding / r;
		if (i) {
			let [e, t, r, a] = n, o = Math.atan2(t.y - e.y, t.x - e.x), s = xr(o) * i, c = Sr(o) * i, l = s + c, u = s - c;
			n = [
				new q(e.x - u, e.y - l),
				new q(t.x + l, t.y - u),
				new q(r.x + u, r.y + l),
				new q(a.x - l, a.y + u)
			];
		}
		return Ro.isPointInPolygon(t, n);
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
				if (wr(i) && i.subTargetCheck) {
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
		if (r && wr(r) && r.interactive && i[0]) {
			for (let e = i.length - 1; e > 0; e--) {
				let t = i[e];
				if (!wr(t) || !t.interactive) return n.target = t, n;
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
		let n = this.upperCanvasEl, r = n.getBoundingClientRect(), i = Ei(e), a = r.width || 0, o = r.height || 0;
		a && o || ("top" in r && "bottom" in r && (o = Math.abs(r.top - r.bottom)), "right" in r && "left" in r && (a = Math.abs(r.right - r.left))), this.calcOffset(), i.x -= this._offset.left, i.y -= this._offset.top, t || (i = Li(i, void 0, this.viewportTransform));
		let s = this.getRetinaScaling();
		s !== 1 && (i.x /= s, i.y /= s);
		let c = a === 0 || o === 0 ? new q(1, 1) : new q(n.width / a, n.height / o);
		return i.multiply(c);
	}
	_setDimensionsImpl(e, t) {
		this._resetTransformEventData(), super._setDimensionsImpl(e, t), this._isCurrentlyDrawing && this.freeDrawingBrush && this.freeDrawingBrush._setBrushStyles(this.contextTop);
	}
	_createCacheCanvas() {
		this.pixelFindCanvasEl = jr(), this.pixelFindContext = this.pixelFindCanvasEl.getContext("2d", { willReadFrequently: !0 }), this.setTargetFindTolerance(this.targetFindTolerance);
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
		return li(e) ? e.getObjects() : e ? [e] : [];
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
		return n !== e && !(!this._discardActiveObject(t, e) && this._activeObject) && !e.onSelect({ e: t }) && (this._activeObject = e, li(e) && n !== e && e.set("canvas", this), e.setCoords(), !0);
	}
	_discardActiveObject(e, t) {
		let n = this._activeObject;
		return !!n && !n.onDeselect({
			e,
			object: t
		}) && (this._currentTransform && this._currentTransform.target === n && this.endCurrentTransform(e), li(n) && n === this._hoveredTarget && (this._hoveredTarget = void 0), this._activeObject = void 0, !0);
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
		n._scaling &&= !1, n.setCoords(), t.actionPerformed && (this.fire("object:modified", r), n.fire(hr, r));
	}
	setViewportTransform(e) {
		super.setViewportTransform(e);
		let t = this._activeObject;
		t && t.setCoords();
	}
	destroy() {
		let e = this._activeObject;
		li(e) && (e.removeAll(), e.dispose()), delete this._activeObject, super.destroy(), this.pixelFindContext = null, this.pixelFindCanvasEl = void 0;
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
		if (t && li(t) && this._activeObject === t) {
			let n = ri(e, [
				"angle",
				"flipX",
				"flipY",
				G,
				lr,
				ur,
				dr,
				fr,
				"top"
			]);
			return ji(e, t.calcOwnMatrix()), n;
		}
		return {};
	}
	_setSVGObject(e, t, n) {
		let r = this._realizeGroupTransformOnObject(t);
		super._setSVGObject(e, t, n), t.set(r);
	}
};
H(ml, "ownDefaults", {
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
var hl = class {
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
		this.unregister(e), br(this.targets, e);
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
}, gl = { passive: !1 }, _l = (e, t) => ({
	viewportPoint: e.getViewportPoint(t),
	scenePoint: e.getScenePoint(t)
}), vl = (e, ...t) => e.addEventListener(...t), yl = (e, ...t) => e.removeEventListener(...t), bl = {
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
}, xl = class extends ml {
	constructor(e, t = {}) {
		super(e, t), H(this, "_isClick", void 0), H(this, "textEditingManager", new hl(this)), [
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
		}), this.addOrRemove(vl);
	}
	_getEventPrefix() {
		return this.enablePointerEvents ? "pointer" : "mouse";
	}
	addOrRemove(e, t = !1) {
		let n = this.upperCanvasEl, r = this._getEventPrefix();
		e(fi(n), "resize", this._onResize), e(n, r + "down", this._onMouseDown), e(n, `${r}move`, this._onMouseMove, gl), e(n, `${r}out`, this._onMouseOut), e(n, `${r}enter`, this._onMouseEnter), e(n, "wheel", this._onMouseWheel, { passive: !1 }), e(n, "contextmenu", this._onContextMenu), t || (e(n, "click", this._onClick), e(n, "dblclick", this._onClick)), e(n, "dragstart", this._onDragStart), e(n, "dragend", this._onDragEnd), e(n, "dragover", this._onDragOver), e(n, "dragenter", this._onDragEnter), e(n, "dragleave", this._onDragLeave), e(n, "drop", this._onDrop), this.enablePointerEvents || e(n, "touchstart", this._onTouchStart, gl);
	}
	removeListeners() {
		this.addOrRemove(yl);
		let e = this._getEventPrefix(), t = di(this.upperCanvasEl);
		yl(t, `${e}up`, this._onMouseUp), yl(t, "touchend", this._onTouchEnd, gl), yl(t, `${e}move`, this._onMouseMove, gl), yl(t, "touchmove", this._onMouseMove, gl), clearTimeout(this._willAddMouseDown);
	}
	_onMouseWheel(e) {
		this._cacheTransformEventData(e), this._handleEvent(e, "wheel"), this._resetTransformEventData();
	}
	_onMouseOut(e) {
		let t = this._hoveredTarget, n = {
			e,
			..._l(this, e)
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
			..._l(this, e)
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
			this.fire("dragstart", n), t.fire("dragstart", n), vl(this.upperCanvasEl, "drag", this._onDragProgress);
			return;
		}
		Oi(e);
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
		yl(this.upperCanvasEl, "drag", this._onDragProgress), this.fire("dragend", i), this._dragSource && this._dragSource.fire("dragend", i), delete this._dragSource, this._onMouseUp(e);
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
			..._l(this, e)
		});
		r.didDrop = !1, r.dropTarget = void 0, this._basicEventHandler("drop", r), this.fire("drop:after", r);
	}
	_onContextMenu(e) {
		let { target: t, subTargets: n } = this.findTarget(e), r = this._basicEventHandler("contextmenu:before", {
			e,
			target: t,
			subTargets: n
		});
		return this.stopContextMenu && Oi(e), this._basicEventHandler("contextmenu", r), !1;
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
			..._l(this, e),
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
		let i = this.upperCanvasEl, a = this._getEventPrefix(), o = di(i);
		vl(o, "touchend", this._onTouchEnd, gl), t && vl(o, "touchmove", this._onMouseMove, gl), yl(i, `${a}down`, this._onMouseDown), this._resetTransformEventData();
	}
	_onMouseDown(e) {
		this._cacheTransformEventData(e), this.__onMouseDown(e);
		let t = this.upperCanvasEl, n = this._getEventPrefix();
		yl(t, `${n}move`, this._onMouseMove, gl);
		let r = di(t);
		vl(r, `${n}up`, this._onMouseUp), vl(r, `${n}move`, this._onMouseMove, gl), this._resetTransformEventData();
	}
	_onTouchEnd(e) {
		if (e.touches.length > 0) return;
		this._cacheTransformEventData(e), this.__onMouseUp(e), this._resetTransformEventData(), delete this.mainTouchId;
		let t = this._getEventPrefix(), n = di(this.upperCanvasEl);
		yl(n, "touchend", this._onTouchEnd, gl), yl(n, "touchmove", this._onMouseMove, gl), this._willAddMouseDown && clearTimeout(this._willAddMouseDown), this._willAddMouseDown = setTimeout(() => {
			vl(this.upperCanvasEl, `${t}down`, this._onMouseDown), this._willAddMouseDown = 0;
		}, 400);
	}
	_onMouseUp(e) {
		this._cacheTransformEventData(e), this.__onMouseUp(e);
		let t = this.upperCanvasEl, n = this._getEventPrefix();
		if (this._isMainEvent(e)) {
			let e = di(this.upperCanvasEl);
			yl(e, `${n}up`, this._onMouseUp), yl(e, `${n}move`, this._onMouseMove, gl), vl(t, `${n}move`, this._onMouseMove, gl);
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
			let { key: t, control: r } = i.findControl(this.getViewportPoint(e), Di(e)) || {};
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
			..._l(this, e),
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
			let r = t.findControl(this.getViewportPoint(e), Di(e));
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
		this._resetTransformEventData(), this._viewportPoint = this.getViewportPoint(e), this._scenePoint = Li(this._viewportPoint, void 0, this.viewportTransform), this._targetInfo = this.findTarget(e), this._currentTransform && (this._targetInfo.target = this._currentTransform.target);
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
		let { targetIn: c, targetOut: l, canvasIn: u, canvasOut: d } = bl[e], f = n !== t, p = i !== r, m = t && f, h = r && p, g = n && f, _ = i && p, v = {
			...s,
			e: o,
			..._l(this, o)
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
		let t = this.getScenePoint(e), n = this._currentTransform, r = n.target, i = r.group ? Li(t, void 0, r.group.calcTransformMatrix()) : t;
		n.shiftKey = e.shiftKey, n.altKey = !!this.centeredKey && e[this.centeredKey], this._performTransformAction(e, n, i), n.actionPerformed && this.requestRenderAll();
	}
	_performTransformAction(e, t, n) {
		let { action: r, actionHandler: i, target: a } = t, o = !!i && i(e, t, n.x, n.y);
		o && a.setCoords(), r === "drag" && o && (t.target.isMoving = !0, this.setCursor(t.target.moveCursor || this.moveCursor)), t.actionPerformed = t.actionPerformed || o;
	}
	_setCursorFromEvent(e, t) {
		if (!t) return void this.setCursor(this.defaultCursor);
		let n = t.hoverCursor || this.hoverCursor, r = li(this._activeObject) ? this._activeObject : null, i = (!r || t.group !== r) && t.findControl(this.getViewportPoint(e));
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
		let n = this._activeObject, r = li(n);
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
}, Sl = {
	x1: 0,
	y1: 0,
	x2: 0,
	y2: 0
}, Cl = {
	...Sl,
	r1: 0,
	r2: 0
}, wl = (e, t) => isNaN(e) && typeof t == "number" ? t : e;
function Tl(e) {
	return e && /%$/.test(e) && Number.isFinite(parseFloat(e));
}
function El(e, t) {
	return Wa(0, wl(typeof e == "number" ? e : typeof e == "string" ? parseFloat(e) / (Tl(e) ? 100 : 1) : NaN, t), 1);
}
var Dl = /\s*;\s*/, Ol = /\s*:\s*/;
function kl(e, t) {
	let n, r, i = e.getAttribute("style");
	if (i) {
		let e = i.split(Dl);
		e[e.length - 1] === "" && e.pop();
		for (let t = e.length; t--;) {
			let [i, a] = e[t].split(Ol).map((e) => e.trim());
			i === "stop-color" ? n = a : i === "stop-opacity" && (r = a);
		}
	}
	n = n || e.getAttribute("stop-color") || "rgb(0,0,0)", r = wl(parseFloat(r || e.getAttribute("stop-opacity") || ""), 1);
	let a = new va(n);
	return a.setAlpha(a.getAlpha() * r * t), {
		offset: El(e.getAttribute("offset"), 0),
		color: a.toRgba()
	};
}
function Al(e, t) {
	let n = [], r = e.getElementsByTagName("stop"), i = El(t, 1);
	for (let e = r.length; e--;) n.push(kl(r[e], i));
	return n;
}
function jl(e) {
	return e.nodeName === "linearGradient" || e.nodeName === "LINEARGRADIENT" ? "linear" : "radial";
}
function Ml(e) {
	return e.getAttribute("gradientUnits") === "userSpaceOnUse" ? "pixels" : "percentage";
}
function Nl(e, t) {
	return e.getAttribute(t);
}
function Pl(e, t) {
	return function(e, { width: t, height: n, gradientUnits: r }) {
		let i;
		return Object.entries(e).reduce((e, [a, o]) => {
			if (o === "Infinity") i = 1;
			else if (o === "-Infinity") i = 0;
			else {
				let e = typeof o == "string";
				i = e ? parseFloat(o) : o, e && Tl(o) && (i *= .01, r === "pixels" && (a !== "x1" && a !== "x2" && a !== "r2" || (i *= t), a !== "y1" && a !== "y2" || (i *= n)));
			}
			return e[a] = i, e;
		}, {});
	}(jl(e) === "linear" ? function(e) {
		return {
			x1: Nl(e, "x1") || 0,
			y1: Nl(e, "y1") || 0,
			x2: Nl(e, "x2") || "100%",
			y2: Nl(e, "y2") || 0
		};
	}(e) : function(e) {
		return {
			x1: Nl(e, "fx") || Nl(e, "cx") || "50%",
			y1: Nl(e, "fy") || Nl(e, "cy") || "50%",
			r1: 0,
			x2: Nl(e, "cx") || "50%",
			y2: Nl(e, "cy") || "50%",
			r2: Nl(e, "r") || "50%"
		};
	}(e), {
		...t,
		gradientUnits: Ml(e)
	});
}
var Fl = class {
	constructor(e) {
		let { type: t = "linear", gradientUnits: n = "pixels", coords: r = {}, colorStops: i = [], offsetX: a = 0, offsetY: o = 0, gradientTransform: s, id: c } = e || {};
		Object.assign(this, {
			type: t,
			gradientUnits: n,
			coords: {
				...t === "radial" ? Cl : Sl,
				...r
			},
			colorStops: i,
			offsetX: a,
			offsetY: o,
			gradientTransform: s,
			id: c ? `${c}_${Ar()}` : Ar()
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
			...ri(this, e),
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
		let n = [], r = this.gradientTransform ? this.gradientTransform.concat() : Yn.concat(), i = this.gradientUnits === "pixels" ? "userSpaceOnUse" : "objectBoundingBox", a = this.colorStops.map((e) => ({ ...e })).sort((e, t) => e.offset - t.offset), o = -this.offsetX, s = -this.offsetY;
		var c;
		i === "objectBoundingBox" ? (o /= e.width, s /= e.height) : (o += e.width / 2, s += e.height / 2), (c = e) && typeof c._renderPathCommands == "function" && this.gradientUnits !== "percentage" && (o -= e.pathOffset.x, s -= e.pathOffset.y), r[4] -= o, r[5] -= s;
		let l = [
			`id="SVGID_${Z(String(this.id))}"`,
			`gradientUnits="${i}"`,
			`gradientTransform="${t ? t + " " : ""}${ai(r)}"`,
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
			let r = String(e), i = ca(r) ? r : new va(r).toRgba();
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
		let r = Ml(e), i = t._findCenterFromElement();
		return new this({
			id: e.getAttribute("id") || void 0,
			type: jl(e),
			coords: Pl(e, {
				width: n.viewBoxWidth || n.width,
				height: n.viewBoxHeight || n.height
			}),
			colorStops: Al(e, n.opacity),
			gradientUnits: r,
			gradientTransform: $s(e.getAttribute("gradientTransform") || ""),
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
H(Fl, "type", "Gradient"), K.setClass(Fl, "gradient"), K.setClass(Fl, "linear"), K.setClass(Fl, "radial");
var Il = class {
	get type() {
		return "pattern";
	}
	set type(e) {
		jn("warn", "Setting type has no effect", e);
	}
	constructor(e) {
		H(this, "repeat", "repeat"), H(this, "offsetX", 0), H(this, "offsetY", 0), H(this, "crossOrigin", ""), this.id = Ar(), Object.assign(this, e);
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
			...ri(this, e),
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
		let { source: n, repeat: r, id: i } = this, a = wl(this.offsetX / e, 0), o = wl(this.offsetY / t, 0), s = r === "repeat-y" || r === "no-repeat" ? 1 + Math.abs(a || 0) : wl(n.width / e, 0), c = r === "repeat-x" || r === "no-repeat" ? 1 + Math.abs(o || 0) : wl(n.height / t, 0);
		return [
			`<pattern id="SVGID_${Z(i)}" x="${a}" y="${o}" width="${s}" height="${c}">`,
			`<image x="0" y="0" width="${n.width}" height="${n.height}" xlink:href="${Z(this.sourceToString())}"></image>`,
			"</pattern>",
			""
		].join("\n");
	}
	static async fromObject({ type: e, source: t, patternTransform: n, ...r }, i) {
		let a = await ei(t, {
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
H(Il, "type", "Pattern"), K.setClass(Il), K.setClass(Il, "pattern");
var Ll = class e extends ws {
	constructor(t, { path: n, left: r, top: i, ...a } = {}) {
		super(), Object.assign(this, e.ownDefaults), this.setOptions(a), this._setPath(t || [], !0), typeof r == "number" && this.set("left", r), typeof i == "number" && this.set("top", i);
	}
	_setPath(e, t) {
		this.path = Dc(Array.isArray(e) ? e : Wc(e)), this.setBoundingBox(t);
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
			`d="${Jc(this.path, U.NUM_FRACTION_DIGITS)}" stroke-linecap="round" />\n`
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
				e.push(...Tc(r, i, a[1], a[2], a[3], a[4], a[5], a[6])), r = a[5], i = a[6];
				break;
			case "Q":
				e.push(...Tc(r, i, a[1], a[2], a[1], a[2], a[3], a[4])), r = a[3], i = a[4];
				break;
			case "Z": r = t, i = n;
		}
		return ki(e);
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
		let { d: r, ...i } = ic(e, this.ATTRIBUTE_NAMES, n);
		return new this(r, {
			...i,
			...t,
			left: void 0,
			top: void 0
		});
	}
};
H(Ll, "type", "Path"), H(Ll, "cacheProperties", [
	...Ka,
	"path",
	"fillRule"
]), H(Ll, "ATTRIBUTE_NAMES", [...Fs, "d"]), K.setClass(Ll), K.setSVGClass(Ll);
var Rl = [
	"radius",
	"startAngle",
	"endAngle",
	"counterClockwise"
], zl = class e extends ws {
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
		return this.get("radius") * this.get(lr);
	}
	getRadiusY() {
		return this.get("radius") * this.get(ur);
	}
	setRadius(e) {
		this.radius = e, this.set({
			width: 2 * e,
			height: 2 * e
		});
	}
	toObject(e = []) {
		return super.toObject([...Rl, ...e]);
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
			let i = J(t), a = J(n), o = xr(i) * e, s = Sr(i) * e, c = xr(a) * e, l = Sr(a) * e;
			return [
				`<path d="M ${o} ${s} A ${e} ${e} 0 ${+(r > 180)} ${+!this.counterClockwise} ${c} ${l}" `,
				"COMMON_PARTS",
				" />\n"
			];
		}
	}
	static async fromElement(e, t, n) {
		let { left: r = 0, top: i = 0, radius: a = 0, ...o } = ic(e, this.ATTRIBUTE_NAMES, n);
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
H(zl, "type", "Circle"), H(zl, "cacheProperties", [...Ka, ...Rl]), H(zl, "ownDefaults", {
	radius: 0,
	startAngle: 0,
	endAngle: 360,
	counterClockwise: !1
}), H(zl, "ATTRIBUTE_NAMES", [
	"cx",
	"cy",
	"r",
	...Fs
]), K.setClass(zl), K.setSVGClass(zl);
var Bl = [
	"x1",
	"x2",
	"y1",
	"y2"
], Vl = class e extends ws {
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
		let { left: i, top: a, width: o, height: s } = ki([{
			x: e,
			y: t
		}, {
			x: n,
			y: r
		}]), c = new q(i + o / 2, a + s / 2);
		this.setPositionByOrigin(c, W, W);
	}
	_set(e, t) {
		return super._set(e, t), Bl.includes(e) && this._setWidthHeight(), this;
	}
	_render(e) {
		e.beginPath();
		let t = this.calcLinePoints();
		e.moveTo(t.x1, t.y1), e.lineTo(t.x2, t.y2), e.lineWidth = this.strokeWidth;
		let n = e.strokeStyle;
		oi(this.stroke) ? e.strokeStyle = this.stroke.toLive(e) : e.strokeStyle = this.stroke ?? e.fillStyle, this.stroke && this._renderStroke(e), e.strokeStyle = n;
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
		let { x1: r = 0, y1: i = 0, x2: a = 0, y2: o = 0, ...s } = ic(e, this.ATTRIBUTE_NAMES, n);
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
H(Vl, "type", "Line"), H(Vl, "cacheProperties", [...Ka, ...Bl]), H(Vl, "ATTRIBUTE_NAMES", Fs.concat(Bl)), K.setClass(Vl), K.setSVGClass(Vl);
var Hl = class e extends ws {
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
H(Hl, "type", "Triangle"), H(Hl, "ownDefaults", {
	width: 100,
	height: 100
}), K.setClass(Hl), K.setSVGClass(Hl);
var Ul = ["rx", "ry"], Wl = class e extends ws {
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
		return this.get("rx") * this.get(lr);
	}
	getRy() {
		return this.get("ry") * this.get(ur);
	}
	toObject(e = []) {
		return super.toObject([...Ul, ...e]);
	}
	_toSVG() {
		return [
			"<ellipse ",
			"COMMON_PARTS",
			`cx="0" cy="0" rx="${Z(this.rx)}" ry="${Z(this.ry)}" />\n`
		];
	}
	_render(e) {
		e.beginPath(), e.save(), e.transform(1, 0, 0, this.ry / this.rx, 0, 0), e.arc(0, 0, this.rx, 0, qn, !1), e.restore(), this._renderPaintInOrder(e);
	}
	static async fromElement(e, t, n) {
		let r = ic(e, this.ATTRIBUTE_NAMES, n);
		return r.left = (r.left || 0) - r.rx, r.top = (r.top || 0) - r.ry, new this(r);
	}
};
H(Wl, "type", "Ellipse"), H(Wl, "cacheProperties", [...Ka, ...Ul]), H(Wl, "ownDefaults", {
	rx: 0,
	ry: 0
}), H(Wl, "ATTRIBUTE_NAMES", [
	...Fs,
	"cx",
	"cy",
	"rx",
	"ry"
]), K.setClass(Wl), K.setSVGClass(Wl);
var Gl = { exactBoundingBox: !1 }, Kl = class e extends ws {
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
		return As(this.points, e, this.isOpen());
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
		let n = ki(t), r = Qr({
			...e,
			scaleX: 1,
			scaleY: 1
		}), i = ki(this.points.map((e) => zr(e, r, !0))), a = new q(this.scaleX, this.scaleY), o = n.left + n.width / 2, s = n.top + n.height / 2;
		return this.exactBoundingBox && (o -= s * Math.tan(J(this.skewX)), s -= o * Math.tan(J(this.skewY))), {
			...n,
			pathOffset: new q(o, s),
			strokeOffset: new q(i.left, i.top).subtract(new q(n.left, n.top)).multiply(a),
			strokeDiff: new q(n.width, n.height).subtract(new q(i.width, i.height)).multiply(a)
		};
	}
	_findCenterFromElement() {
		let e = ki(this.points);
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
		}(e.getAttribute("points")), { left: i, top: a, ...o } = ic(e, this.ATTRIBUTE_NAMES, n);
		return new this(r, {
			...o,
			...t
		});
	}
	static fromObject(e) {
		return this._fromObject(e, { extraParam: "points" });
	}
};
H(Kl, "ownDefaults", Gl), H(Kl, "type", "Polyline"), H(Kl, "layoutProperties", [
	dr,
	fr,
	"strokeLineCap",
	"strokeLineJoin",
	"strokeMiterLimit",
	"strokeWidth",
	"strokeUniform",
	"points"
]), H(Kl, "cacheProperties", [...Ka, "points"]), H(Kl, "ATTRIBUTE_NAMES", [...Fs]), K.setClass(Kl), K.setSVGClass(Kl);
var ql = class extends Kl {
	isOpen() {
		return !1;
	}
};
H(ql, "ownDefaults", Gl), H(ql, "type", "Polygon"), K.setClass(ql), K.setSVGClass(ql);
var Jl = class extends ws {
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
		let i = ii({
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
			...ri(this, this.constructor._styleProperties),
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
H(Jl, "_styleProperties", ja);
var Yl = /  +/g, Xl = /"/g;
function Zl(e, t, n, r, i) {
	return `\t\t${((e, { left: t, top: n, width: r, height: i }, a = U.NUM_FRACTION_DIGITS) => {
		let o = Sa(pr, e, !1), [s, c, l, u] = [
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
var Ql, $l = class e extends Jl {
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
		e && (e.segmentsInfo = Rc(e.path));
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
			case "descender": e.textBaseline = Xn;
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
		let i = Hn.getFontCache(t), a = this._getFontDeclaration(t), o = n ? n + e : e, s = n && a === this._getFontDeclaration(r), c = t.fontSize / this.CACHE_FONT_SIZE, l, u, d, f;
		if (n && i.has(n) && (d = i.get(n)), i.has(e) && (f = l = i.get(e)), s && i.has(o) && (u = i.get(o), f = u - d), l === void 0 || d === void 0 || u === void 0) {
			let r = (Ql ||= Pr({
				width: 0,
				height: 0
			}).getContext("2d"), Ql);
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
		let t, n, r = 0, i = this.pathSide === Zn, a = this.path, o = this._textLines[e], s = o.length, c = Array(s);
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
				case Zn: e = i ? 0 : t - r;
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
		let n = e + t.kernedWidth / 2, r = this.path, i = zc(r.path, n, r.segmentsInfo);
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
		let o = this.textAlign.includes(Na), s = this.path, c = !o && this.charSpacing === 0 && this.isEmptyStyles(a) && !s, l = this.direction === "ltr", u = this.direction === "ltr" ? 1 : -1, d = t.direction, f, p, m, h, g, _ = "", v = 0;
		if (t.save(), d !== this.direction && (t.canvas.setAttribute("dir", l ? "ltr" : "rtl"), t.direction = l ? "ltr" : "rtl", t.textAlign = l ? G : Zn), i -= this.getHeightOfLineImpl(a) * this._fontSizeFraction, c) return this._renderChar(e, t, a, 0, n.join(""), r, i), void t.restore();
		for (let c = 0, l = n.length - 1; c <= l; c++) h = c === l || this.charSpacing || s, _ += n[c], m = this.__charBounds[a][c], v === 0 ? (r += u * (m.kernedWidth - m.width), v += m.width) : v += m.kernedWidth, o && !h && this._reSpaceAndTab.test(n[c]) && (h = !0), h ||= (f ||= this.getCompleteStyleDeclaration(a, c), p = this.getCompleteStyleDeclaration(a, c + 1), Ms(f, p, !1)), h && (s ? (t.save(), t.translate(m.renderLeft, m.renderTop), t.rotate(m.angle), this._renderChar(e, t, a, c, _, -v / 2, 0), t.restore()) : (g = r, this._renderChar(e, t, a, c, _, g, i)), _ = "", f = p, r += u * v, v = 0);
		t.restore();
	}
	_applyPatternGradientTransformText(e) {
		let t = this.width + this.strokeWidth, n = this.height + this.strokeWidth, r = Pr({
			width: t,
			height: n
		}), i = r.getContext("2d");
		return r.width = t, r.height = n, i.beginPath(), i.moveTo(0, 0), i.lineTo(t, 0), i.lineTo(t, n), i.lineTo(0, n), i.closePath(), i.translate(t / 2, n / 2), i.fillStyle = e.toLive(i), this._applyPatternGradientTransform(i, e), i.fill(), i.createPattern(r, "no-repeat");
	}
	handleFiller(e, t, n) {
		let r, i;
		return oi(n) ? n.gradientUnits === "percentage" || n.gradientTransform || n.patternTransform ? (r = -this.width / 2, i = -this.height / 2, e.translate(r, i), e[t] = this._applyPatternGradientTransformText(n), {
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
			let u = this._textLines[c], d = l / this.lineHeight, f = this._getLineLeftOffset(c), p, m = 0, h = 0, g = this.getValueOfPropertyAt(c, 0, t), _ = this.getValueOfPropertyAt(c, 0, pr), v = this.getValueOfPropertyAt(c, 0, "textDecorationColor") || _, y = this.getValueOfPropertyAt(c, 0, Ta), b = g, x = v, S = y, C = n + d * (1 - this._fontSizeFraction), w = this.getHeightOfChar(c, 0), T = this.getValueOfPropertyAt(c, 0, "deltaY");
			for (let n = 0, a = u.length; n < a; n++) {
				let a = this.__charBounds[c][n];
				b = this.getValueOfPropertyAt(c, n, t), p = this.getValueOfPropertyAt(c, n, pr), x = this.getValueOfPropertyAt(c, n, "textDecorationColor") || p, S = this.getValueOfPropertyAt(c, n, Ta);
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
			let ee = this.fontSize * S / 1e3;
			b && x && S && e.fillRect(E, C + s * w + T - o * ee, h - a, ee), n += l;
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
		return xi(e);
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
			...super.toObject([...Aa, ...e]),
			styles: Ns(this.styles, this.text),
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
		let i = ic(t, e.ATTRIBUTE_NAMES, r), { textAnchor: a = G, textDecoration: o = "", dx: s = 0, dy: c = 0, top: l = 0, left: u = 0, fontSize: d = 16, strokeWidth: f = 1, ...p } = {
			...n,
			...i
		}, m = new this(da(t.textContent || "").trim(), {
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
			styles: Ps(e.styles || {}, e.text)
		}, { extraParam: "text" });
	}
};
H($l, "textLayoutProperties", ka), H($l, "cacheProperties", [...Ka, ...Aa]), H($l, "ownDefaults", Ma), H($l, "type", "Text"), H($l, "genericFonts", [
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
]), H($l, "ATTRIBUTE_NAMES", Fs.concat("x", "y", "dx", "dy", "font-family", "font-style", "font-weight", "font-size", "letter-spacing", "text-decoration", "text-decoration-thickness", "text-decoration-color", "text-anchor")), Cs($l, [class extends Ca {
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
			additionalTransform: ai(this.calcOwnMatrix())
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
			`font-family="${Z(this.fontFamily.replace(Xl, "'"))}" `,
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
		this.backgroundColor && r.push(Zl(this.backgroundColor, -this.width / 2, -this.height / 2, this.width, this.height));
		for (let e = 0, o = this._textLines.length; e < o; e++) i = this._getLineLeftOffset(e), this.direction === "rtl" && (i += this.width), (this.textBackgroundColor || this.styleHas("textBackgroundColor", e)) && this._setSVGTextLineBg(r, e, t + i, a), this._setSVGTextLineText(n, e, t + i, a), a += this.getHeightOfLine(e);
		return {
			textSpans: n,
			textBgRects: r
		};
	}
	_createTextCharSpan(e, t, n, r, i) {
		let a = U.NUM_FRACTION_DIGITS, o = this.getSvgSpanStyles(t, e !== e.trim() || !!e.match(Yl)), s = o ? `style="${o}"` : "", c = t.deltaY, l = c ? ` dy="${X(c, a)}" ` : "", { angle: u, renderLeft: d, renderTop: f, width: p } = i, m = "";
		if (d !== void 0) {
			let e = p / 2;
			u && (m = ` rotate="${X(Lr(u), a)}"`);
			let t = qr({ angle: Lr(u) });
			t[4] = d, t[5] = f;
			let i = new q(-e, 0).transform(t);
			n = i.x, r = i.y;
		}
		return `<tspan x="${X(n, a)}" y="${X(r, a)}" ${l}${m}${s}>${Z(e)}</tspan>`;
	}
	_setSVGTextLineText(e, t, n, r) {
		let i = this.getHeightOfLine(t), a = this.textAlign.includes(Na), o = this._textLines[t], s, c, l, u, d, f = "", p = 0;
		r += i * (1 - this._fontSizeFraction) / this.lineHeight;
		for (let i = 0, m = o.length - 1; i <= m; i++) d = i === m || this.charSpacing || this.path, f += o[i], l = this.__charBounds[t][i], p === 0 ? (n += l.kernedWidth - l.width, p += l.width) : p += l.kernedWidth, a && !d && this._reSpaceAndTab.test(o[i]) && (d = !0), d ||= (s ||= this.getCompleteStyleDeclaration(t, i), c = this.getCompleteStyleDeclaration(t, i + 1), Ms(s, c, !0)), d && (u = this._getStyleDeclaration(t, i), e.push(this._createTextCharSpan(f, u, n, r, l)), f = "", s = c, this.direction === "rtl" ? n -= p : n += p, p = 0);
	}
	_setSVGTextLineBg(e, t, n, r) {
		let i = this._textLines[t], a = this.getHeightOfLine(t) / this.lineHeight, o, s = 0, c = 0, l = this.getValueOfPropertyAt(t, 0, "textBackgroundColor");
		for (let u = 0; u < i.length; u++) {
			let { left: i, width: d, kernedWidth: f } = this.__charBounds[t][u];
			o = this.getValueOfPropertyAt(t, u, "textBackgroundColor"), o === l ? s += f : (l && e.push(Zl(l, n + c, r, s, a)), c = i, s = d, l = o);
		}
		o && e.push(Zl(l, n + c, r, s, a));
	}
	getSvgStyles(e) {
		let t = ca(this.textDecorationColor) ? ` text-decoration-color: ${Z(this[Ea])};` : "";
		return `${super.getSvgStyles(e)} text-decoration-thickness: ${X(this.textDecorationThickness * this.getObjectScaling().y / 10, U.NUM_FRACTION_DIGITS)}%;${t} white-space: pre;`;
	}
	getSvgSpanStyles(e, t) {
		let { fontFamily: n, strokeWidth: r, stroke: i, fill: a, fontSize: o, fontStyle: s, fontWeight: c, textDecorationThickness: l, textDecorationColor: u, linethrough: d, overline: f, underline: p } = e, m = this.getSvgTextDecoration({
			underline: p ?? this.underline,
			overline: f ?? this.overline,
			linethrough: d ?? this.linethrough
		}), h = l || this.textDecorationThickness, g = u || this.textDecorationColor, _ = la(r), v = ua(n), y = la(o), b = ua(s), x = la(c) || ua(c), S = ua(g);
		return [
			i ? Sa(mr, i) : "",
			_ ? `stroke-width: ${Z(_)}; ` : "",
			v ? `font-family: ${v.includes("'") || v.includes("\"") ? Z(v) : `'${Z(v)}'`}; ` : "",
			y ? `font-size: ${Z(y)}px; ` : "",
			b ? `font-style: ${Z(b)}; ` : "",
			x ? `font-weight: ${Z(x)}; ` : "",
			m ? `text-decoration: ${m}; text-decoration-thickness: ${X(h * this.getObjectScaling().y / 10, U.NUM_FRACTION_DIGITS)}%;${S ? ` text-decoration-color: ${Z(S)};` : ""} ` : "",
			a ? Sa(pr, a) : "",
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
}]), K.setClass($l), K.setSVGClass($l);
var eu = class {
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
		let i = this.target, a = i.canvas, o = new q(i.flipX ? -1 : 1, i.flipY ? -1 : 1), s = i._getCursorBoundaries(t), c = new q(s.left + s.leftOffset, s.top + s.topOffset).multiply(o).transform(i.calcTransformMatrix()), l = a.getScenePoint(e).subtract(c), u = i.getCanvasRetinaScaling(), d = i.getBoundingRect(), f = c.subtract(new q(d.left, d.top)), p = a.viewportTransform, m = f.add(l).transform(p, !0), h = i.backgroundColor, g = js(i.styles);
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
		i.backgroundColor = h, i.styles = g, i.dirty = !0, Qc(v, {
			position: "fixed",
			left: -v.width + "px",
			border: Qn,
			width: v.width / u + "px",
			height: v.height / u + "px"
		}), this.__dragImageDisposer && this.__dragImageDisposer(), this.__dragImageDisposer = () => {
			v.remove();
		}, di(e.target || this.target.hiddenTextarea).body.appendChild(v), (r = e.dataTransfer) == null || r.setDragImage(v, m.x, m.y);
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
			n._reNewline.test(s) && (n._reNewline.test(n._text[a]) || a === n._text.length) && (r = r.trimEnd()), e.didDrop = !0, e.dropTarget = n, n.insertChars(r, o, a), i.setActiveObject(n), n.enterEditing(t), n.selectionStart = Math.min(a + 0, n._text.length), n.selectionEnd = Math.min(n.selectionStart + r.length, n._text.length), n.hiddenTextarea.value = n.text, n._updateTextarea(), n.hiddenTextarea.focus(), n.fire(sr, {
				index: a + 0,
				action: "drop"
			}), i.fire("text:changed", { target: n }), i.contextTopDirty = !0, i.requestRenderAll();
		}
	}
	dragEndHandler({ e }) {
		if (this.isActive() && this.__dragStartFired && this.__dragStartSelection) {
			let t = this.target, n = this.target.canvas, { selectionStart: r, selectionEnd: i } = this.__dragStartSelection, a = e.dataTransfer?.dropEffect || "none";
			a === "none" ? (t.selectionStart = r, t.selectionEnd = i, t._updateTextarea(), t.hiddenTextarea.focus()) : (t.clearContextTop(), a === "move" && (t.removeChars(r, i), t.selectionStart = t.selectionEnd = r, t.hiddenTextarea && (t.hiddenTextarea.value = t.text), t._updateTextarea(), t.fire(sr, {
				index: r,
				action: "dragend"
			}), n.fire("text:changed", { target: t }), n.requestRenderAll()), t.exitEditing());
		}
		this.__dragImageDisposer && this.__dragImageDisposer(), delete this.__dragImageDisposer, delete this.__dragStartSelection, this.__isDraggingOver = !1;
	}
	dispose() {
		this._dispose && this._dispose();
	}
}, tu = /[ \n\.,;!\?\-]/, nu = class extends $l {
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
		return Io({
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
		let n = this._text, r = e > 0 && this._reSpace.test(n[e]) && (t === -1 || !$n.test(n[e - 1])) ? e - 1 : e, i = n[r];
		for (; r > 0 && r < n.length && !tu.test(i);) r += t, i = n[r];
		return t === -1 && tu.test(i) && r++, r;
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
		di(t).activeElement !== t && t.focus();
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
		let i = n === "justify" ? t === "ltr" ? G : Zn : n.replace("justify-", ""), a = this.getPositionByOrigin(i, "top");
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
		n <= e ? (t === e ? this._selectionDirection = G : this._selectionDirection === "right" && (this._selectionDirection = G, this.selectionEnd = e), this.selectionStart = n) : n > e && n < t ? this._selectionDirection === "right" ? this.selectionEnd = n : this.selectionStart = n : (t === e ? this._selectionDirection = Zn : this._selectionDirection === "left" && (this._selectionDirection = Zn, this.selectionStart = t), this.selectionEnd = n);
	}
}, ru = class extends nu {
	initHiddenTextarea() {
		let e = this.canvas && di(this.canvas.getElement()) || zn(), t = e.createElement("textarea");
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
			this.updateFromTextArea(), this.fire(sr), this.canvas && (this.canvas.fire("text:changed", { target: this }), this.canvas.requestRenderAll());
		};
		if (this.hiddenTextarea.value === "") return this.styles = {}, void a();
		let o = this._splitTextIntoLines(n).graphemeText, s = this._text.length, c = o.length, l = this.selectionStart, u = this.selectionEnd, d = l !== u, f, p, m, h, g = c - s, _ = this.fromStringToGraphemeSelection(r, i, n), v = l > _.selectionStart;
		d ? (p = this._text.slice(l, u), g += u - l) : c < s && (p = v ? this._text.slice(u + g, u) : this._text.slice(l, l - g));
		let y = o.slice(_.selectionEnd - g, _.selectionEnd);
		if (p && p.length && (y.length && (f = this.getSelectionStyles(l, l + 1, !1), f = y.map(() => f[0])), d ? (m = l, h = u) : v ? (m = u - p.length, h = u) : (m = u, h = u + p.length), this.removeStyleFromTo(m, h)), y.length) {
			let { copyPasteData: e } = Rn();
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
		let { copyPasteData: e } = Rn();
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
		let n = this[`get${e}CursorOffset`](t, this._selectionDirection === Zn);
		if (t.shiftKey ? this.moveCursorWithShift(n) : this.moveCursorWithoutShift(n), n !== 0) {
			let e = this.text.length;
			this.selectionStart = Wa(0, this.selectionStart, e), this.selectionEnd = Wa(0, this.selectionEnd, e), this.abortCursorAnimation(), this.initDelayedCursor(), this._fireSelectionChanged(), this._updateTextarea();
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
		return this._selectionDirection === "left" && this.selectionStart !== this.selectionEnd ? this._moveRight(e, "selectionStart") : this.selectionEnd === this._text.length ? void 0 : (this._selectionDirection = Zn, this._moveRight(e, "selectionEnd"));
	}
	moveCursorRightWithoutShift(e) {
		let t = !0;
		return this._selectionDirection = Zn, this.selectionStart === this.selectionEnd ? (t = this._moveRight(e, "selectionStart"), this.selectionEnd = this.selectionStart) : this.selectionStart = this.selectionEnd, t;
	}
}, iu = (e) => !!e.button, au = class extends ru {
	constructor(...e) {
		super(...e), H(this, "draggableTextDelegate", void 0);
	}
	initBehavior() {
		this.on("mousedown", this._mouseDownHandler), this.on("mouseup", this.mouseUpHandler), this.on("mousedblclick", this.doubleClickHandler), this.on("mousetripleclick", this.tripleClickHandler), this.draggableTextDelegate = new eu(this), super.initBehavior();
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
		this.canvas && this.editable && !iu(e) && !this.getActiveControl() && (this.draggableTextDelegate.start(e) || (this.canvas.textEditingManager.register(this), t && (this.inCompositionMode = !1, this.setCursorByClick(e)), this.isEditing && (this.__selectionStartOnMouseDown = this.selectionStart, this.selectionStart === this.selectionEnd && this.abortCursorAnimation(), this.renderCursorOrSelection()), this.selected ||= t || this.isEditing));
	}
	mouseUpHandler({ e, transform: t }) {
		let n = this.draggableTextDelegate.end(e);
		if (this.canvas) {
			this.canvas.textEditingManager.unregister(this);
			let e = this.canvas._activeObject;
			if (e && e !== this) return;
		}
		!this.editable || this.group && !this.group.interactive || t && t.actionPerformed || iu(e) || n || this.selected && !this.getActiveControl() && (this.enterEditing(e), this.selectionStart === this.selectionEnd ? this.initDelayedCursor(!0) : this.renderCursorOrSelection());
	}
	setCursorByClick(e) {
		let t = this.getSelectionStartFromPointer(e), n = this.selectionStart, r = this.selectionEnd;
		e.shiftKey ? this.setSelectionStartEndWithShift(n, r, t) : (this.selectionStart = t, this.selectionEnd = t), this.isEditing && (this._fireSelectionChanged(), this._updateTextarea());
	}
	getSelectionStartFromPointer(e) {
		let t = this.canvas.getScenePoint(e).transform(Br(this.calcTransformMatrix())).add(new q(-this._getLeftOffset(), -this._getTopOffset())), n = 0, r = 0, i = 0;
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
}, ou = "moveCursorUp", su = "moveCursorDown", cu = "moveCursorLeft", lu = "moveCursorRight", uu = "exitEditing", du = (e, t) => {
	let n = t.getRetinaScaling();
	e.setTransform(n, 0, 0, n, 0, 0);
	let r = t.viewportTransform;
	e.transform(r[0], r[1], r[2], r[3], r[4], r[5]);
}, fu = {
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
		9: uu,
		27: uu,
		33: ou,
		34: su,
		35: lu,
		36: cu,
		37: cu,
		38: ou,
		39: lu,
		40: su
	},
	keysMapRtl: {
		9: uu,
		27: uu,
		33: ou,
		34: su,
		35: cu,
		36: lu,
		37: lu,
		38: ou,
		39: cu,
		40: su
	},
	ctrlKeysMapDown: { 65: "cmdAll" },
	ctrlKeysMapUp: {
		67: "copy",
		88: "cut"
	},
	_selectionDirection: null,
	_reSpace: /\s|\r?\n/,
	inCompositionMode: !1
}, pu = class e extends au {
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
		return this.isEditing && this._savedProps && e in this._savedProps ? (this._savedProps[e] = t, this) : (e === "canvas" && (this.canvas instanceof xl && this.canvas.textEditingManager.remove(this), t instanceof xl && t.textEditingManager.add(this)), super._set(e, t));
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
			i = Pr(e.canvas), a = i.getContext("2d"), du(a, this.canvas);
			let t = this.calcTransformMatrix();
			a.transform(t[0], t[1], t[2], t[3], t[4], t[5]);
		}
		if (this.selectionStart !== this.selectionEnd || this.inCompositionMode ? this.renderSelection(a, t) : this.renderCursor(a, t), r) for (let t of n) {
			let n = t.clipPath, r = Pr(e.canvas), i = r.getContext("2d");
			if (du(i, this.canvas), !n.absolutePositioned) {
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
		let { textAlign: r, direction: i } = this, a = t.selectionStart, o = t.selectionEnd, s = r.includes(Na), c = this.get2DCursorLocation(a), l = this.get2DCursorLocation(o), u = c.lineIndex, d = l.lineIndex, f = c.charIndex < 0 ? 0 : c.charIndex, p = l.charIndex < 0 ? 0 : l.charIndex;
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
		return this.getValueOfPropertyAt(e.l, e.c, pr);
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
H(pu, "ownDefaults", fu), H(pu, "type", "IText"), K.setClass(pu), K.setClass(pu, "i-text");
var mu = class e extends pu {
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
		return { controls: xs() };
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
H(mu, "type", "Textbox"), H(mu, "textLayoutProperties", [...pu.textLayoutProperties, "width"]), H(mu, "ownDefaults", {
	minWidth: 20,
	dynamicMinWidth: 2,
	lockScalingFlip: !0,
	noScaleCache: !1,
	_wordJoiners: /[ \t\r]/,
	splitByGrapheme: !1
}), K.setClass(mu);
var hu = class extends uc {
	shouldPerformLayout(e) {
		return !!e.target.clipPath && super.shouldPerformLayout(e);
	}
	shouldLayoutClipPath() {
		return !1;
	}
	calcLayoutResult(e, t) {
		let { target: n } = e, { clipPath: r, group: i } = n;
		if (!r || !this.shouldPerformLayout(e)) return;
		let { width: a, height: o } = ki(lc(n, r)), s = new q(a, o);
		if (r.absolutePositioned) return {
			center: Li(r.getRelativeCenterPoint(), void 0, i ? i.calcTransformMatrix() : void 0),
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
H(hu, "type", "clip-path"), K.setClass(hu);
var gu = class extends uc {
	getInitialSize({ target: e }, { size: t }) {
		return new q(e.width || t.x, e.height || t.y);
	}
};
H(gu, "type", "fixed"), K.setClass(gu);
var _u = class extends pc {
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
}, vu = class e extends hc {
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
			layoutManager: a ?? new _u()
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
		return this.getObjects().some((t) => t.isDescendantOf(e) || e.isDescendantOf(t)) ? (jn("error", "ActiveSelection: circular object trees are not supported, this call has no effect"), !1) : super.canEnterGroup(e);
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
			e._onAfterObjectsChange(cc, t);
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
H(vu, "type", "ActiveSelection"), H(vu, "ownDefaults", { multiSelectionStacking: "canvas-stacking" }), K.setClass(vu), K.setClass(vu, "activeSelection");
var yu = class {
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
}, bu = class {
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
		let n = Pr({
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
}, xu;
function Su() {
	let { WebGLProbe: e } = Rn();
	return e.queryWebGL(jr()), U.enableGLFiltering && e.isSupported(U.textureSize) ? new bu({ tileSize: U.textureSize }) : new yu();
}
function Cu(e = !0) {
	return !xu && e && (xu = Su()), xu;
}
var wu = ["cropX", "cropY"], Tu = class e extends ws {
	static getDefaults() {
		return {
			...super.getDefaults(),
			...e.ownDefaults
		};
	}
	constructor(t, n) {
		super(), H(this, "_lastScaleX", 1), H(this, "_lastScaleY", 1), H(this, "_filterScalingX", 1), H(this, "_filterScalingY", 1), this.filters = [], Object.assign(this, e.ownDefaults), this.setOptions(n), this.cacheKey = `texture${Ar()}`, this.setElement(typeof t == "string" ? (this.canvas && di(this.canvas.getElement()) || zn()).getElementById(t) : t, n);
	}
	getElement() {
		return this._element;
	}
	setElement(e, t = {}) {
		this.removeTexture(this.cacheKey), this.removeTexture(`${this.cacheKey}_filtered`), this._element = e, this._originalElement = e, this._setWidthHeight(t), this.filters.length !== 0 && this.applyFilters(), this.resizeFilter && this.applyResizeFilters();
	}
	removeTexture(e) {
		let t = Cu(!1);
		t instanceof bu && t.evictCachesForKey(e);
	}
	dispose() {
		super.dispose(), this.removeTexture(this.cacheKey), this.removeTexture(`${this.cacheKey}_filtered`), this._cacheContext = null, [
			"_originalElement",
			"_element",
			"_filteredEl",
			"_cacheCanvas"
		].forEach((e) => {
			let t = this[e];
			t && Rn().dispose(t), this[e] = void 0;
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
			...super.toObject([...wu, ...e]),
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
			let e = Ar();
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
		return ei(e, {
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
		let o = Pr(a), { width: s, height: c } = a;
		this._element = o, this._lastScaleX = e.scaleX = r, this._lastScaleY = e.scaleY = i, Cu().applyFilters([e], a, s, c, this._element), this._filterScalingX = o.width / this._originalElement.width, this._filterScalingY = o.height / this._originalElement.height;
	}
	applyFilters(e = this.filters || []) {
		if (e = e.filter((e) => e && !e.isNeutralState()), this.set("dirty", !0), this.removeTexture(`${this.cacheKey}_filtered`), e.length === 0) return this._element = this._originalElement, this._filteredEl = void 0, this._filterScalingX = 1, void (this._filterScalingY = 1);
		let t = this._originalElement, n = t.naturalWidth || t.width, r = t.naturalHeight || t.height;
		if (this._element === this._originalElement) {
			let e = Pr({
				width: n,
				height: r
			});
			this._element = e, this._filteredEl = e;
		} else this._filteredEl && (this._element = this._filteredEl, this._filteredEl.getContext("2d").clearRect(0, 0, n, r), this._lastScaleX = 1, this._lastScaleY = 1);
		Cu().applyFilters(e, this._originalElement, n, r, this._element, this.cacheKey), this._originalElement.width === this._element.width && this._originalElement.height === this._element.height || (this._filterScalingX = this._element.width / this._originalElement.width, this._filterScalingY = this._element.height / this._originalElement.height);
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
		let e = xa(this.preserveAspectRatio || ""), t = this.width, n = this.height, r = {
			width: t,
			height: n
		}, i, a = this._element.width, o = this._element.height, s = 1, c = 1, l = 0, u = 0, d = 0, f = 0;
		return !e || e.alignX === "none" && e.alignY === "none" ? (s = t / a, c = n / o) : (e.meetOrSlice === "meet" && (s = c = _c(this._element, r), i = (t - a * s) / 2, e.alignX === "Min" && (l = -i), e.alignX === "Max" && (l = i), i = (n - o * c) / 2, e.alignY === "Min" && (u = -i), e.alignY === "Max" && (u = i)), e.meetOrSlice === "slice" && (s = c = vc(this._element, r), i = a - t / s, e.alignX === "Mid" && (d = i / 2), e.alignX === "Max" && (d = i), i = o - n / c, e.alignY === "Mid" && (f = i / 2), e.alignY === "Max" && (f = i), a = t / s, o = n / c)), {
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
			ei(n, {
				...o,
				crossOrigin: r
			}),
			e && ti(e, o),
			t ? ti([t], o) : [],
			ni(a, o)
		]).then(([e, t = [], [r], i = {}]) => new this(e, {
			...a,
			src: n,
			filters: t,
			resizeFilter: r,
			...i
		}));
	}
	static fromURL(e, { crossOrigin: t = null, signal: n } = {}, r) {
		return ei(e, {
			crossOrigin: t,
			signal: n
		}).then((e) => new this(e, r));
	}
	static async fromElement(e, t = {}, n) {
		let r = ic(e, this.ATTRIBUTE_NAMES, n);
		return this.fromURL(r["xlink:href"] || r.href, t, r).catch((e) => (jn("log", "Unable to parse Image", e), null));
	}
};
H(Tu, "type", "Image"), H(Tu, "cacheProperties", [...Ka, ...wu]), H(Tu, "ownDefaults", {
	strokeWidth: 0,
	srcFromAttribute: !1,
	minimumScaleTrigger: .5,
	cropX: 0,
	cropY: 0,
	imageSmoothing: !0
}), H(Tu, "ATTRIBUTE_NAMES", [
	...Fs,
	"x",
	"y",
	"width",
	"height",
	"preserveAspectRatio",
	"xlink:href",
	"href",
	"crossOrigin",
	"image-rendering"
]), K.setClass(Tu), K.setSVGClass(Tu), wa([
	"pattern",
	"defs",
	"symbol",
	"metadata",
	"clipPath",
	"mask",
	"desc"
]);
var Eu = (e) => e.webgl !== void 0, Du = "precision highp float", Ou = `\n    ${Du};\n    varying vec2 vTexCoord;\n    uniform sampler2D uTexture;\n    void main() {\n      gl_FragColor = texture2D(uTexture, vTexCoord);\n    }`, ku = new RegExp(Du, "g"), Q = class {
	get type() {
		return this.constructor.type;
	}
	constructor({ type: e, ...t } = {}) {
		Object.assign(this, this.constructor.defaults, t);
	}
	getFragmentSource() {
		return Ou;
	}
	getVertexSource() {
		return "\n    attribute vec2 aPosition;\n    varying vec2 vTexCoord;\n    void main() {\n      vTexCoord = aPosition;\n      gl_Position = vec4(aPosition * 2.0 - 1.0, 0.0, 1.0);\n    }";
	}
	createProgram(e, t = this.getFragmentSource(), n = this.getVertexSource()) {
		let { WebGLProbe: { GLPrecision: r = "highp" } } = Rn();
		r !== "highp" && (t = t.replace(ku, Du.replace("highp", r)));
		let i = e.createShader(e.VERTEX_SHADER), a = e.createShader(e.FRAGMENT_SHADER), o = e.createProgram();
		if (!i || !a || !o) throw new Mn("Vertex, fragment shader or program creation error");
		if (e.shaderSource(i, n), e.compileShader(i), !e.getShaderParameter(i, e.COMPILE_STATUS)) throw new Mn(`Vertex shader compile error for ${this.type}: ${e.getShaderInfoLog(i)}`);
		if (e.shaderSource(a, t), e.compileShader(a), !e.getShaderParameter(a, e.COMPILE_STATUS)) throw new Mn(`Fragment shader compile error for ${this.type}: ${e.getShaderInfoLog(a)}`);
		if (e.attachShader(o, i), e.attachShader(o, a), e.linkProgram(o), !e.getProgramParameter(o, e.LINK_STATUS)) throw new Mn(`Shader link error for "${this.type}" ${e.getProgramInfoLog(o)}`);
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
		Eu(e) ? (this._setupFrameBuffer(e), this.applyToWebGL(e), this._swapTextures(e)) : this.applyTo2d(e);
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
			e.helpLayer = Pr({
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
var Au = {
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
}, ju = class extends Q {
	getCacheKey() {
		return `${this.type}_${this.mode}`;
	}
	getFragmentSource() {
		return `\n      precision highp float;\n      uniform sampler2D uTexture;\n      uniform vec4 uColor;\n      varying vec2 vTexCoord;\n      void main() {\n        vec4 color = texture2D(uTexture, vTexCoord);\n        gl_FragColor = color;\n        if (color.a > 0.0) {\n          ${Au[this.mode]}\n        }\n      }\n      `;
	}
	applyTo2d({ imageData: { data: e } }) {
		let t = new va(this.color).getSource(), n = this.alpha, r = t[0] * n, i = t[1] * n, a = t[2] * n, o = 1 - n;
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
		let n = new va(this.color).getSource();
		n[0] = this.alpha * n[0] / 255, n[1] = this.alpha * n[1] / 255, n[2] = this.alpha * n[2] / 255, n[3] = this.alpha, e.uniform4fv(t.uColor, n);
	}
};
H(ju, "defaults", {
	color: "#F95C63",
	mode: "multiply",
	alpha: 1
}), H(ju, "type", "BlendColor"), H(ju, "uniformLocations", ["uColor"]), K.setClass(ju);
var Mu = {
	multiply: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform sampler2D uImage;\n    uniform vec4 uColor;\n    varying vec2 vTexCoord;\n    varying vec2 vTexCoord2;\n    void main() {\n      vec4 color = texture2D(uTexture, vTexCoord);\n      vec4 color2 = texture2D(uImage, vTexCoord2);\n      color.rgba *= color2.rgba;\n      gl_FragColor = color;\n    }\n    ",
	mask: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform sampler2D uImage;\n    uniform vec4 uColor;\n    varying vec2 vTexCoord;\n    varying vec2 vTexCoord2;\n    void main() {\n      vec4 color = texture2D(uTexture, vTexCoord);\n      vec4 color2 = texture2D(uImage, vTexCoord2);\n      color.a = color2.a;\n      gl_FragColor = color;\n    }\n    "
}, Nu = class extends Q {
	getCacheKey() {
		return `${this.type}_${this.mode}`;
	}
	getFragmentSource() {
		return Mu[this.mode];
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
		r.blendImage ||= jr();
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
		return Tu.fromObject(t, r).then((e) => new this({
			...n,
			image: e
		}));
	}
};
H(Nu, "type", "BlendImage"), H(Nu, "defaults", {
	mode: "multiply",
	alpha: 1
}), H(Nu, "uniformLocations", ["uTransformMatrix", "uImage"]), K.setClass(Nu);
var Pu = class extends Q {
	getFragmentSource() {
		return "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform vec2 uDelta;\n    varying vec2 vTexCoord;\n    const float nSamples = 15.0;\n    vec3 v3offset = vec3(12.9898, 78.233, 151.7182);\n    float random(vec3 scale) {\n      /* use the fragment position for a different seed per-pixel */\n      return fract(sin(dot(gl_FragCoord.xyz, scale)) * 43758.5453);\n    }\n    void main() {\n      vec4 color = vec4(0.0);\n      float totalC = 0.0;\n      float totalA = 0.0;\n      float offset = random(v3offset);\n      for (float t = -nSamples; t <= nSamples; t++) {\n        float percent = (t + offset - 0.5) / nSamples;\n        vec4 sample = texture2D(uTexture, vTexCoord + uDelta * percent);\n        float weight = 1.0 - abs(percent);\n        float alpha = weight * sample.a;\n        color.rgb += sample.rgb * alpha;\n        color.a += alpha;\n        totalA += weight;\n        totalC += alpha;\n      }\n      gl_FragColor.rgb = color.rgb / totalC;\n      gl_FragColor.a = color.a / totalA;\n    }\n  ";
	}
	applyTo(e) {
		Eu(e) ? (this.aspectRatio = e.sourceWidth / e.sourceHeight, e.passes++, this._setupFrameBuffer(e), this.horizontal = !0, this.applyToWebGL(e), this._swapTextures(e), this._setupFrameBuffer(e), this.horizontal = !1, this.applyToWebGL(e), this._swapTextures(e)) : this.applyTo2d(e);
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
H(Pu, "type", "Blur"), H(Pu, "defaults", { blur: 0 }), H(Pu, "uniformLocations", ["uDelta"]), K.setClass(Pu);
var Fu = class extends Q {
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
H(Fu, "type", "Brightness"), H(Fu, "defaults", { brightness: 0 }), H(Fu, "uniformLocations", ["uBrightness"]), K.setClass(Fu);
var Iu = {
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
}, Lu = class extends Q {
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
function Ru(e, t) {
	var n;
	let r = (H(n = class extends Lu {
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
H(Lu, "type", "ColorMatrix"), H(Lu, "defaults", Iu), H(Lu, "uniformLocations", ["uColorMatrix", "uConstants"]), K.setClass(Lu);
var zu = Ru("Brownie", [
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
]), Bu = Ru("Vintage", [
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
]), Vu = Ru("Kodachrome", [
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
]), Hu = Ru("Technicolor", [
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
]), Uu = Ru("Polaroid", [
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
]), Wu = Ru("Sepia", [
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
]), Gu = Ru("BlackWhite", [
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
]), Ku = class extends Q {
	constructor(e = {}) {
		super(e), this.subFilters = e.subFilters || [];
	}
	applyTo(e) {
		Eu(e) && (e.passes += this.subFilters.length - 1), this.subFilters.forEach((t) => {
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
H(Ku, "type", "Composed"), K.setClass(Ku);
var qu = class extends Q {
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
H(qu, "type", "Contrast"), H(qu, "defaults", { contrast: 0 }), H(qu, "uniformLocations", ["uContrast"]), K.setClass(qu);
var Ju = {
	Convolute_3_1: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[9];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 0);\n      for (float h = 0.0; h < 3.0; h+=1.0) {\n        for (float w = 0.0; w < 3.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 1), uStepH * (h - 1));\n          color += texture2D(uTexture, vTexCoord + matrixPos) * uMatrix[int(h * 3.0 + w)];\n        }\n      }\n      gl_FragColor = color;\n    }\n    ",
	Convolute_3_0: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[9];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 1);\n      for (float h = 0.0; h < 3.0; h+=1.0) {\n        for (float w = 0.0; w < 3.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 1.0), uStepH * (h - 1.0));\n          color.rgb += texture2D(uTexture, vTexCoord + matrixPos).rgb * uMatrix[int(h * 3.0 + w)];\n        }\n      }\n      float alpha = texture2D(uTexture, vTexCoord).a;\n      gl_FragColor = color;\n      gl_FragColor.a = alpha;\n    }\n    ",
	Convolute_5_1: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[25];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 0);\n      for (float h = 0.0; h < 5.0; h+=1.0) {\n        for (float w = 0.0; w < 5.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 2.0), uStepH * (h - 2.0));\n          color += texture2D(uTexture, vTexCoord + matrixPos) * uMatrix[int(h * 5.0 + w)];\n        }\n      }\n      gl_FragColor = color;\n    }\n    ",
	Convolute_5_0: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[25];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 1);\n      for (float h = 0.0; h < 5.0; h+=1.0) {\n        for (float w = 0.0; w < 5.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 2.0), uStepH * (h - 2.0));\n          color.rgb += texture2D(uTexture, vTexCoord + matrixPos).rgb * uMatrix[int(h * 5.0 + w)];\n        }\n      }\n      float alpha = texture2D(uTexture, vTexCoord).a;\n      gl_FragColor = color;\n      gl_FragColor.a = alpha;\n    }\n    ",
	Convolute_7_1: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[49];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 0);\n      for (float h = 0.0; h < 7.0; h+=1.0) {\n        for (float w = 0.0; w < 7.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 3.0), uStepH * (h - 3.0));\n          color += texture2D(uTexture, vTexCoord + matrixPos) * uMatrix[int(h * 7.0 + w)];\n        }\n      }\n      gl_FragColor = color;\n    }\n    ",
	Convolute_7_0: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[49];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 1);\n      for (float h = 0.0; h < 7.0; h+=1.0) {\n        for (float w = 0.0; w < 7.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 3.0), uStepH * (h - 3.0));\n          color.rgb += texture2D(uTexture, vTexCoord + matrixPos).rgb * uMatrix[int(h * 7.0 + w)];\n        }\n      }\n      float alpha = texture2D(uTexture, vTexCoord).a;\n      gl_FragColor = color;\n      gl_FragColor.a = alpha;\n    }\n    ",
	Convolute_9_1: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[81];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 0);\n      for (float h = 0.0; h < 9.0; h+=1.0) {\n        for (float w = 0.0; w < 9.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 4.0), uStepH * (h - 4.0));\n          color += texture2D(uTexture, vTexCoord + matrixPos) * uMatrix[int(h * 9.0 + w)];\n        }\n      }\n      gl_FragColor = color;\n    }\n    ",
	Convolute_9_0: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform float uMatrix[81];\n    uniform float uStepW;\n    uniform float uStepH;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = vec4(0, 0, 0, 1);\n      for (float h = 0.0; h < 9.0; h+=1.0) {\n        for (float w = 0.0; w < 9.0; w+=1.0) {\n          vec2 matrixPos = vec2(uStepW * (w - 4.0), uStepH * (h - 4.0));\n          color.rgb += texture2D(uTexture, vTexCoord + matrixPos).rgb * uMatrix[int(h * 9.0 + w)];\n        }\n      }\n      float alpha = texture2D(uTexture, vTexCoord).a;\n      gl_FragColor = color;\n      gl_FragColor.a = alpha;\n    }\n    "
}, Yu = class extends Q {
	getCacheKey() {
		return `${this.type}_${Math.sqrt(this.matrix.length)}_${+!!this.opaque}`;
	}
	getFragmentSource() {
		return Ju[this.getCacheKey()];
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
H(Yu, "type", "Convolute"), H(Yu, "defaults", {
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
}), H(Yu, "uniformLocations", [
	"uMatrix",
	"uOpaque",
	"uHalfSize",
	"uSize"
]), K.setClass(Yu);
var Xu = "Gamma", Zu = class extends Q {
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
			type: Xu,
			gamma: this.gamma.concat()
		};
	}
};
H(Zu, "type", Xu), H(Zu, "defaults", { gamma: [
	1,
	1,
	1
] }), H(Zu, "uniformLocations", ["uGamma"]), K.setClass(Zu);
var Qu = {
	average: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 color = texture2D(uTexture, vTexCoord);\n      float average = (color.r + color.b + color.g) / 3.0;\n      gl_FragColor = vec4(average, average, average, color.a);\n    }\n    ",
	lightness: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform int uMode;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 col = texture2D(uTexture, vTexCoord);\n      float average = (max(max(col.r, col.g),col.b) + min(min(col.r, col.g),col.b)) / 2.0;\n      gl_FragColor = vec4(average, average, average, col.a);\n    }\n    ",
	luminosity: "\n    precision highp float;\n    uniform sampler2D uTexture;\n    uniform int uMode;\n    varying vec2 vTexCoord;\n    void main() {\n      vec4 col = texture2D(uTexture, vTexCoord);\n      float average = 0.21 * col.r + 0.72 * col.g + 0.07 * col.b;\n      gl_FragColor = vec4(average, average, average, col.a);\n    }\n    "
}, $u = class extends Q {
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
		return Qu[this.mode];
	}
	sendUniformData(e, t) {
		e.uniform1i(t.uMode, 1);
	}
	isNeutralState() {
		return !1;
	}
};
H($u, "type", "Grayscale"), H($u, "defaults", { mode: "average" }), H($u, "uniformLocations", ["uMode"]), K.setClass($u);
var ed = {
	...Iu,
	rotation: 0
}, td = class extends Lu {
	calculateMatrix() {
		let e = this.rotation * Math.PI, t = xr(e), n = Sr(e), r = 1 / 3, i = Math.sqrt(r) * n, a = 1 - t;
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
H(td, "type", "HueRotation"), H(td, "defaults", ed), K.setClass(td);
var nd = class extends Q {
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
H(nd, "type", "Invert"), H(nd, "defaults", {
	alpha: !1,
	invert: !0
}), H(nd, "uniformLocations", ["uInvert", "uAlpha"]), K.setClass(nd);
var rd = class extends Q {
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
H(rd, "type", "Noise"), H(rd, "defaults", { noise: 0 }), H(rd, "uniformLocations", ["uNoise", "uSeed"]), K.setClass(rd);
var id = class extends Q {
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
H(id, "type", "Pixelate"), H(id, "defaults", { blocksize: 4 }), H(id, "uniformLocations", ["uBlocksize"]), K.setClass(id);
var ad = class extends Q {
	getFragmentSource() {
		return "\nprecision highp float;\nuniform sampler2D uTexture;\nuniform vec4 uLow;\nuniform vec4 uHigh;\nvarying vec2 vTexCoord;\nvoid main() {\n  gl_FragColor = texture2D(uTexture, vTexCoord);\n  if(all(greaterThan(gl_FragColor.rgb,uLow.rgb)) && all(greaterThan(uHigh.rgb,gl_FragColor.rgb))) {\n    gl_FragColor.a = 0.0;\n  }\n}\n";
	}
	applyTo2d({ imageData: { data: e } }) {
		let t = 255 * this.distance, n = new va(this.color).getSource(), r = [
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
		let n = new va(this.color).getSource(), r = this.distance, i = [
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
H(ad, "type", "RemoveColor"), H(ad, "defaults", {
	color: "#FFFFFF",
	distance: .02,
	useAlpha: !1
}), H(ad, "uniformLocations", ["uLow", "uHigh"]), K.setClass(ad);
var od = class extends Q {
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
		Eu(e) ? this.applyToForWebgl(e) : this.applyTo2d(e);
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
		d.sliceByTwo ||= jr();
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
			let y, b, x, S, C, w, T, E, ee, D, O;
			for (g.x = (v + .5) * l, _.x = Math.floor(g.x), y = 0; y < i; y++) {
				for (g.y = (y + .5) * u, _.y = Math.floor(g.y), C = 0, w = 0, T = 0, E = 0, ee = 0, b = _.x - p; b <= _.x + p; b++) if (!(b < 0 || b >= t)) {
					D = Math.floor(1e3 * Math.abs(b - g.x)), h[D] || (h[D] = {});
					for (let e = _.y - m; e <= _.y + m; e++) e < 0 || e >= n || (O = Math.floor(1e3 * Math.abs(e - g.y)), h[D][O] || (h[D][O] = c(Math.sqrt((D * d) ** 2 + (O * f) ** 2) / 1e3)), x = h[D][O], x > 0 && (S = 4 * (e * t + b), C += x, w += x * a[S], T += x * a[S + 1], E += x * a[S + 2], ee += x * a[S + 3]));
				}
				S = 4 * (y * r + v), s[S] = w / C, s[S + 1] = T / C, s[S + 2] = E / C, s[S + 3] = ee / C;
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
H(od, "type", "Resize"), H(od, "defaults", {
	resizeType: "hermite",
	scaleX: 1,
	scaleY: 1,
	lanczosLobes: 3
}), H(od, "uniformLocations", ["uDelta", "uTaps"]), K.setClass(od);
var sd = class extends Q {
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
H(sd, "type", "Saturation"), H(sd, "defaults", { saturation: 0 }), H(sd, "uniformLocations", ["uSaturation"]), K.setClass(sd);
var cd = class extends Q {
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
H(cd, "type", "Vibrance"), H(cd, "defaults", { vibrance: 0 }), H(cd, "uniformLocations", ["uVibrance"]), K.setClass(cd), Dn({
	BaseFilter: () => Q,
	BlackWhite: () => Gu,
	BlendColor: () => ju,
	BlendImage: () => Nu,
	Blur: () => Pu,
	Brightness: () => Fu,
	Brownie: () => zu,
	ColorMatrix: () => Lu,
	Composed: () => Ku,
	Contrast: () => qu,
	Convolute: () => Yu,
	Gamma: () => Zu,
	Grayscale: () => $u,
	HueRotation: () => td,
	Invert: () => nd,
	Kodachrome: () => Vu,
	Noise: () => rd,
	Pixelate: () => id,
	Polaroid: () => Uu,
	RemoveColor: () => ad,
	Resize: () => od,
	Saturation: () => sd,
	Sepia: () => Wu,
	Technicolor: () => Hu,
	Vibrance: () => cd,
	Vintage: () => Bu
});
//#endregion
//#region frontend/canvas/src/canvas/object-factory.ts
var ld = "__canvasPresentation", ud = {
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
function dd(e, t, n, r = {}) {
	return { [ld]: {
		key: e,
		role: t,
		domainId: n,
		...r
	} };
}
function fd(e, t) {
	return e.set(t), e.setCoords(), e;
}
function pd(e, t, n) {
	return e.layoutState.nodePositions[t] ?? {
		x: n * 220,
		y: Math.floor(n / 4) * 140
	};
}
function md(e) {
	let t = e.prompt?.trim();
	return t === void 0 || t.length === 0 ? e.kind : `${e.kind}: ${t}`;
}
function hd(e, t) {
	let n = `node:${e.id}`, r = e.kind === "product_source" || e.kind === "auto_cutout", i = {
		left: t.x,
		top: t.y,
		width: 180,
		height: 96,
		rx: 12,
		ry: 12,
		originX: "center",
		originY: "center",
		fill: ud[e.kind],
		stroke: "#334155",
		strokeWidth: 1.5,
		label: md(e),
		visible: !0,
		selectable: !r,
		evented: !r,
		...dd(n, "node", e.id, {
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
		create: () => fd(new oc(), i)
	};
}
function gd(e, t, n, r) {
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
		...dd(i, "edge", e.id)
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
		create: () => fd(new Vl([
			t.x,
			t.y,
			n.x,
			n.y
		]), o)
	};
}
function _d(e, t, n, r) {
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
		...dd(o, "port", `${i}:${a}`)
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
		create: () => fd(new zl(), c)
	};
}
function vd(e, t) {
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
		...dd(r, "product", t.id)
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
		load: async (e) => fd(await Tu.fromURL(`/api/canvas/assets/${encodeURIComponent(t.renderAssetId)}/content?variant=preview`, {
			crossOrigin: "anonymous",
			signal: e
		}), i)
	};
}
function yd(e) {
	let t = "background:selected-result-preview", n = {
		left: 0,
		top: 0,
		originX: "left",
		originY: "top",
		selectable: !1,
		evented: !1,
		visible: !0,
		...dd(t, "background", e)
	};
	return {
		kind: "image",
		key: t,
		role: "background",
		domainId: e,
		fingerprint: JSON.stringify({ assetId: e }),
		properties: n,
		load: async (t) => fd(await Tu.fromURL(`/api/canvas/assets/${encodeURIComponent(e)}/content?variant=preview`, {
			crossOrigin: "anonymous",
			signal: t
		}), n)
	};
}
function bd(e, t, n, r) {
	let i = t > 0 ? t : n;
	return r === "center" ? e + i / 2 : r === "right" ? e + i : e;
}
function xd(e) {
	return e.lines.map((t, n) => {
		let r = `text:${e.id}:line:${n}`, i = t.width > 0 ? t.width : e.boxWidth, a = {
			text: t.text,
			left: bd(t.x, t.width, e.boxWidth, e.align),
			top: m(t.y, e.fontSize, e.baseline),
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
			...dd(r, "text", e.id)
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
			create: () => fd(new $l(t.text), a)
		};
	});
}
function Sd(e, t = e.semanticState.mode, n = null) {
	let r = ke(e), i = /* @__PURE__ */ new Map();
	r.semanticState.nodes.forEach((e, t) => {
		i.set(e.id, pd(r, e.id, t));
	});
	let a = n === null ? [] : [yd(n)];
	a.push(...r.semanticState.nodes.map((e, t) => hd(e, i.get(e.id) ?? pd(r, e.id, t))));
	for (let e of r.semanticState.edges) {
		let n = i.get(e.sourceNodeId), r = i.get(e.targetNodeId);
		if (n === void 0 || r === void 0) throw Error(`validated edge ${e.id} has no presentation endpoint`);
		a.push(gd(e, n, r, t), _d(e, "source", n, t), _d(e, "target", r, t));
	}
	let o = [...r.layoutState.textSnapshots].sort((e, t) => e.sortOrder - t.sortOrder || e.id.localeCompare(t.id));
	return a.push(...o.filter((e) => e.zBand === "below-product").flatMap(xd), ...r.layoutState.productLayers.map((e) => vd(r, e)), ...o.filter((e) => e.zBand === "above-product").flatMap(xd)), {
		project: r,
		descriptors: a,
		boardToNodeId: new Map(r.semanticState.outputBoards.map((e) => [e.id, e.outputNodeId]))
	};
}
//#endregion
//#region frontend/canvas/src/canvas/viewport.ts
var Cd = Object.freeze({
	minPan: -1e6,
	maxPan: 1e6,
	minZoom: .01,
	maxZoom: 1e3
});
function wd(e, t) {
	if (!Number.isFinite(e)) throw Error(`${t} must be finite`);
	return e;
}
function Td(e) {
	let t = {
		minPan: wd(e.minPan, "minPan"),
		maxPan: wd(e.maxPan, "maxPan"),
		minZoom: wd(e.minZoom, "minZoom"),
		maxZoom: wd(e.maxZoom, "maxZoom")
	};
	if (t.minPan > t.maxPan) throw Error("minPan must not exceed maxPan");
	if (t.minZoom <= 0 || t.minZoom > t.maxZoom) throw Error("zoom safety limits must be positive and ordered");
	return t;
}
function Ed(e, t, n) {
	return Math.min(n, Math.max(t, e));
}
function Dd(e) {
	return {
		x: wd(e.x, "viewport.x"),
		y: wd(e.y, "viewport.y"),
		zoom: wd(e.zoom, "viewport.zoom")
	};
}
function Od(e, t, n = Cd) {
	let r = Dd(e), i = Td(n), a = wd(t.x, "pan.x"), o = wd(t.y, "pan.y");
	return {
		x: Ed(r.x + a, i.minPan, i.maxPan),
		y: Ed(r.y + o, i.minPan, i.maxPan),
		zoom: Ed(r.zoom, i.minZoom, i.maxZoom)
	};
}
function kd(e, t, n = Cd) {
	let r = Dd(e), i = Td(n);
	return {
		x: Ed(r.x, i.minPan, i.maxPan),
		y: Ed(r.y, i.minPan, i.maxPan),
		zoom: Ed(wd(t, "zoom"), i.minZoom, i.maxZoom)
	};
}
//#endregion
//#region frontend/canvas/src/canvas/canvas-adapter.ts
function Ad(e) {
	if (e.outputType !== void 0) return e.outputType;
	switch (e.node?.kind) {
		case "main_output": return "main";
		case "sku_output": return "sku";
		case "detail_output": return "detail";
		default: return;
	}
}
function jd(e) {
	if (e === void 0) return;
	let t = e.get(ld);
	if (typeof t != "object" || !t) return;
	let n = t;
	if (!(typeof n.key != "string" || typeof n.domainId != "string" || typeof n.role != "string")) return n;
}
function Md(e) {
	return e === "product_source" || e === "auto_cutout";
}
function Nd(e, t) {
	return JSON.stringify(e) === JSON.stringify(t);
}
function Pd() {
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
			let [n, r] = t, i = Sd(s), a = i.descriptors.find((e) => e.key === n && e.role === r.role);
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
			}), D(e), e.requestRenderAll();
		}, i = ({ target: e }) => {
			let t = jd(e);
			t?.role === "node" && t.node !== void 0 && y({
				type: "node/add",
				node: structuredClone(t.node)
			});
		}, o = ({ target: e }) => {
			if (a !== 0) return;
			let r = jd(e), i = t(e);
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
			if (n?.descriptor.role === "node" && Md(n.nodeKind)) {
				r(e, n.descriptor);
				return;
			}
			let i = jd(e);
			if (i?.role !== "node" || i.node?.managedBy !== "complete-set") return;
			let o = Ad(i);
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
				let r = Od(l, {
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
				let r = Math.min(20, Math.max(-20, -n * .001)), i = kd(l, l.zoom * Math.exp(r));
				T(e, i), e.requestRenderAll(), y({
					type: "viewport/set",
					viewport: i
				});
			})
		];
	}, x = () => {
		if (e === null) throw Error("CanvasAdapter mount element is unavailable");
		let t = new xl(e, {
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
		l = kd(t, t.zoom), v(() => {
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
	}, ee = (e, t) => {
		let n = new Set(t.map((e) => e.key));
		for (let [e, r] of h) {
			let i = t.find((t) => t.key === e);
			(!n.has(e) || i?.fingerprint !== r.descriptor.fingerprint) && (r.controller.abort(), h.delete(e));
		}
		let r = [];
		for (let [e, t] of m) n.has(e) || (r.push(t.object), m.delete(e));
		r.length > 0 && v(() => e.remove(...r));
	}, D = (e) => {
		let t = 0;
		v(() => {
			for (let n of p) {
				let r = m.get(n);
				r !== void 0 && (e.moveObjectTo(r.object, t), t += 1);
			}
		});
	}, O = (e, t) => {
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
			}), v(() => e.add(s)), D(e), e.requestRenderAll();
		}).catch(() => {
			h.get(t.key) === a && h.delete(t.key);
		});
	}, te = (e, t) => {
		for (let n of t) {
			let t = m.get(n.key);
			if (t !== void 0) {
				if (t.fingerprint !== n.fingerprint) {
					if (n.kind === "image") {
						m.delete(n.key), v(() => e.remove(t.object)), t.object.dispose(), O(e, n);
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
				O(e, n);
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
		let n = _(), r = Sd(t, t.semanticState.mode, u);
		s !== null && (e === null || !Nd(e, s)) && (n = w()), p = r.descriptors.map((e) => e.key), c = r.project.semanticState.mode, ee(n, r.descriptors), te(n, r.descriptors), D(n), f = new Map(r.boardToNodeId), E(n), T(n, r.project.layoutState.viewport), s = r.project, n.requestRenderAll();
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
			let i = r.object.getCenterPoint(), a = l.zoom, o = kd({
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
var Fd = 12 * 1024 * 1024, Id = [
	"image/jpeg",
	"image/png",
	"image/webp"
], Ld = "main-product", Rd = "main-product-source", zd = "main-product-cutout", Bd = "main-product-source-cutout";
function Vd(e, t = Fd) {
	return Id.includes(e.type) ? e.size > t ? {
		ok: !1,
		message: "图片不能超过 12 MB"
	} : { ok: !0 } : {
		ok: !1,
		message: "请选择 JPG、PNG 或 WebP 图片"
	};
}
function Hd(e, t, n) {
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
function Ud(e, t) {
	let n = e.semanticState.nodes.findIndex((e) => e.id === t.id);
	n === -1 ? e.semanticState.nodes.push(t) : e.semanticState.nodes[n] = t;
}
function Wd(e) {
	let t = {
		id: Bd,
		kind: "product_asset",
		sourceNodeId: Rd,
		sourcePort: "product",
		targetNodeId: zd,
		targetPort: "reference",
		skuId: null
	}, n = e.semanticState.edges.findIndex((e) => e.id === Bd);
	n === -1 ? e.semanticState.edges.push(t) : e.semanticState.edges[n] = t;
}
function Gd(e, t) {
	let n = e.layoutState.productLayers.find((e) => e.id === Ld && e.skuId === null);
	if (n === void 0) throw Error("Canvas main product layer is missing");
	if (n.allowOpaqueFallback = t, n.compositionGroupId !== null) for (let r of e.layoutState.productLayers) r.compositionGroupId === n.compositionGroupId && r.sourceAssetId === n.sourceAssetId && r.renderAssetId === n.renderAssetId && (r.allowOpaqueFallback = t);
}
function Kd(e, t, n) {
	let r = e.layoutState.productLayers.find((e) => e.id === Ld), i = {
		id: Ld,
		sourceAssetId: t,
		renderAssetId: n,
		allowOpaqueFallback: !1,
		skuId: null,
		compositionGroupId: r?.compositionGroupId ?? null,
		transformId: r?.transformId ?? Ld,
		locked: !0
	}, a = e.layoutState.productLayers.findIndex((e) => e.id === Ld);
	if (a === -1 ? e.layoutState.productLayers.push(i) : e.layoutState.productLayers[a] = i, r?.compositionGroupId !== null && r?.compositionGroupId !== void 0) for (let a of e.layoutState.productLayers) a.id !== i.id && a.compositionGroupId === r.compositionGroupId && a.sourceAssetId === r.sourceAssetId && (a.sourceAssetId = t, a.renderAssetId = n, a.allowOpaqueFallback = !1);
	e.layoutState.objectTransforms[Ld] ??= {
		x: .5,
		y: .5,
		scale: 1,
		rotation: 0
	};
}
function qd(e) {
	let t = e.source.projectId;
	if (e.source.assetType !== "source" || e.working.assetType !== "working" || e.preview.assetType !== "preview" || e.working.projectId !== t || e.preview.projectId !== t || e.working.sourceAssetId !== e.source.id || e.preview.sourceAssetId !== e.working.id) throw Error("Canvas upload response has invalid asset derivation");
	if (e.operation !== null && (e.operation.projectId !== t || e.operation.operationType !== "cutout" || e.operation.inputAssetId !== e.working.id)) throw Error("Canvas upload response has invalid cutout operation");
}
function Jd(e) {
	if (e.working.transparencyStatus === "transparent") {
		if (e.operation !== null) throw Error("Transparent Canvas assets cannot enqueue automatic cutout");
		return "ready";
	}
	if (e.operation === null) throw Error("Opaque Canvas assets require an automatic cutout operation");
	return e.operation.status === "running" ? "running" : "queued";
}
function Yd(e, t) {
	qd(t);
	let n = structuredClone(e), r = Jd(t);
	return Ud(n, Hd(Rd, "product_source", t.working.id)), Ud(n, Hd(zd, "auto_cutout", t.working.id)), Wd(n), Kd(n, t.working.id, t.working.id), {
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
function Xd(e) {
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
function Zd(e, t) {
	if (t.id !== e.asset.operationId || t.projectId !== e.asset.projectId || t.inputAssetId !== void 0 && t.inputAssetId !== e.asset.workingAssetId || t.operationType !== "cutout") return e;
	let n = structuredClone(e.project), r = t.status === "succeeded";
	if (r && t.outputAssetId === null) throw Error("Succeeded Canvas cutout has no output asset");
	let i = r && !e.asset.allowOpaqueFallback, a = i ? t.outputAssetId : e.asset.renderAssetId;
	return i && (Kd(n, e.asset.workingAssetId, a), Ud(n, Hd(zd, "auto_cutout", a)), Gd(n, !1)), {
		project: n,
		asset: {
			...e.asset,
			renderAssetId: a,
			cutoutAssetId: r ? t.outputAssetId : e.asset.cutoutAssetId,
			cutoutStatus: Xd(t.status),
			allowOpaqueFallback: !i && e.asset.allowOpaqueFallback,
			error: t.status === "queued" || t.status === "running" || t.status === "succeeded" ? null : t.safeError ?? e.asset.error
		}
	};
}
function Qd(e, t, n) {
	let r = e.layoutState.productLayers.find((e) => e.skuId === null && e.locked);
	if (r === void 0) return null;
	let i = t.find((e) => e.id === r.sourceAssetId && e.assetType === "working");
	if (i === void 0 || i.sourceAssetId === null) return null;
	let a = t.find((e) => e.id === i.sourceAssetId && e.assetType === "source"), o = t.find((e) => e.assetType === "preview" && e.sourceAssetId === i.id);
	if (a === void 0 || o === void 0) return null;
	let s = [...n].filter((e) => e.projectId === i.projectId && e.operationType === "cutout" && e.inputAssetId === i.id).at(-1) ?? null, c = t.find((e) => e.id === r.renderAssetId), l = c?.assetType === "cutout" ? c.id : s?.status === "succeeded" ? s.outputAssetId : null, u = i.transparencyStatus === "transparent" ? "ready" : s === null ? l === null ? "queued" : "ready" : Xd(s.status), d = $d(e), f = {
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
	return s?.status === "succeeded" && s.outputAssetId !== null && !d ? Zd(f, s) : f;
}
function $d(e) {
	return e.layoutState.productLayers.find((e) => e.id === Ld && e.skuId === null)?.allowOpaqueFallback === !0;
}
//#endregion
//#region frontend/canvas/src/components/project-sidebar.ts
function ef(e, t, n) {
	let r = document.createElement("button");
	return r.type = "button", r.textContent = e, n !== void 0 && (r.dataset.testid = n), r.addEventListener("click", t), r;
}
function tf(e) {
	let t = document.createElement("aside");
	t.className = "canvas-project-sidebar", t.dataset.testid = "canvas-project-sidebar", t.setAttribute("aria-label", "项目列表");
	let n = document.createElement("h1");
	n.textContent = "产品视觉画布";
	let r = document.createElement("form");
	r.className = "canvas-create-project";
	let i = document.createElement("input");
	i.type = "text", i.required = !0, i.maxLength = 200, i.setAttribute("aria-label", "新建项目名称"), i.dataset.testid = "canvas-project-create-name", i.placeholder = "项目名称";
	let a = document.createElement("button");
	a.type = "submit", a.textContent = "新建", a.dataset.testid = "canvas-project-create", r.append(i, a), r.addEventListener("submit", (t) => {
		t.preventDefault();
		let n = i.value.trim();
		n !== "" && e.createProject(n);
	});
	let o = document.createElement("input");
	o.type = "search", o.setAttribute("aria-label", "搜索项目"), o.dataset.testid = "canvas-project-search", o.placeholder = "搜索项目";
	let s = document.createElement("label"), c = document.createElement("input");
	c.type = "checkbox", s.append(c, "显示已归档"), o.addEventListener("input", () => {
		e.searchProjects(o.value, c.checked);
	}), c.addEventListener("change", () => {
		e.searchProjects(o.value, c.checked);
	});
	let l = document.createElement("ul");
	l.className = "canvas-project-list", l.dataset.testid = "canvas-project-list";
	let u = document.createElement("p");
	u.className = "canvas-project-feedback", u.setAttribute("aria-live", "polite");
	let d = document.createElement("div");
	return d.className = "canvas-project-dialogs", t.append(n, r, o, s, u, l, d), {
		element: t,
		update: (t) => {
			document.activeElement !== o && (o.value = t.query), c.checked = t.includeArchived, u.textContent = t.loading ? "正在加载项目…" : t.error ?? "", l.replaceChildren();
			for (let n of t.projects) {
				let r = document.createElement("li");
				r.className = "canvas-project-row", r.dataset.testid = "canvas-project-row", r.dataset.projectId = n.id, n.id === t.activeProjectId && r.classList.add("is-active");
				let i = ef(n.name, () => {
					e.switchProject(n.id);
				}, "canvas-project-switch");
				if (i.className = "canvas-project-select", i.disabled = n.id === t.activeProjectId, r.append(i), n.id === t.activeProjectId) {
					let t = document.createElement("input");
					t.type = "text", t.value = n.name, t.maxLength = 200, t.setAttribute("aria-label", `重命名 ${n.name}`), t.dataset.testid = "canvas-project-rename", r.append(t, ef("保存名称", () => {
						let n = t.value.trim();
						n !== "" && e.renameActiveProject(n);
					}, "canvas-project-rename-save"));
				}
				n.status === "archived" ? r.append(ef("恢复", () => void e.restoreProject(n.id), "canvas-project-restore")) : n.status === "active" && r.append(ef("归档", () => void e.archiveProject(n.id), "canvas-project-archive")), r.append(ef("删除", () => e.requestDeleteProject(n.id), "canvas-project-delete")), l.append(r);
			}
			if (d.replaceChildren(), t.deleteCandidateId !== null) {
				let t = document.createElement("section");
				t.setAttribute("role", "dialog"), t.setAttribute("aria-modal", "true"), t.setAttribute("aria-label", "确认删除项目"), t.dataset.testid = "canvas-delete-confirm";
				let n = document.createElement("p");
				n.textContent = "删除后项目与其画布数据将被永久移除。", t.append(n, ef("确认删除", () => void e.confirmDeleteProject(), "canvas-delete-confirm-submit"), ef("取消", () => e.cancelDeleteProject(), "canvas-delete-confirm-cancel")), d.append(t);
			}
			if (t.pendingSwitch !== null) {
				let t = document.createElement("section");
				t.setAttribute("role", "dialog"), t.setAttribute("aria-modal", "true"), t.setAttribute("aria-label", "未保存项目切换"), t.dataset.testid = "canvas-switch-decision";
				let n = document.createElement("p");
				n.textContent = "当前项目保存失败。请选择重试、留在当前项目或放弃更改。", t.append(n, ef("重试", () => void e.retrySwitch(), "canvas-switch-retry"), ef("留在当前项目", () => e.stayOnProject(), "canvas-switch-stay"), ef("放弃更改并切换", () => void e.discardAndSwitch(), "canvas-switch-discard")), d.append(t);
			}
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/asset-inspector.ts
var nf = {
	ready: "素材已就绪",
	queued: "自动抠图已排队",
	running: "正在自动抠图",
	failed: "自动抠图失败",
	interrupted: "自动抠图已中断"
};
function rf() {
	return typeof crypto.randomUUID == "function" ? crypto.randomUUID() : `cutout-retry-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function af({ api: e, onOperation: t, onFallback: n, createRequestId: r = rf }) {
	let i = null, a = !1, o = !1, s = 0, c = document.createElement("section");
	c.className = "canvas-asset-inspector", c.dataset.testid = "canvas-asset-inspector";
	let l = () => {
		if (o) return;
		let l = document.createElement("h3");
		if (l.textContent = "素材与抠图", i === null) {
			let e = document.createElement("p");
			e.textContent = "上传主商品图片后可在此对比抠图。", c.replaceChildren(l, e);
			return;
		}
		let u = document.createElement("div");
		u.className = "canvas-asset-comparison";
		let d = i.cutoutStatus === "ready" && i.operationId === null && i.cutoutAssetId === null, f = (t, n, r) => {
			let i = document.createElement("figure");
			i.className = "canvas-checkerboard";
			let a = document.createElement("figcaption");
			if (a.textContent = t, i.append(a), r === null) {
				let e = document.createElement("span");
				e.textContent = d ? "原图已含透明通道，无需抠图" : "等待抠图结果", i.append(e);
			} else {
				let t = document.createElement("img");
				t.alt = n, t.src = e.previewUrl(r), i.append(t);
			}
			return i;
		};
		u.append(f("原图", "原图预览", i.workingAssetId), f("抠图", "抠图预览", i.cutoutAssetId));
		let p = document.createElement("p");
		p.className = `canvas-cutout-status is-${i.cutoutStatus}`, p.dataset.testid = "canvas-cutout-status", p.textContent = nf[i.cutoutStatus], i.error !== null && (p.textContent += `：${i.error.message}`);
		let m = document.createElement("div");
		if (m.className = "canvas-asset-actions", i.cutoutStatus === "failed" || i.cutoutStatus === "interrupted") {
			let n = document.createElement("button");
			n.type = "button", n.textContent = "重新抠图", n.disabled = a, n.addEventListener("click", () => {
				if (a || i === null) return;
				let c = i, l = ++s;
				n.disabled = !0, e.retryCutout(c.workingAssetId, r()).then((e) => {
					o || l !== s || (e.ok ? (t(e.value), p.textContent = "自动抠图已重新排队") : (p.textContent = e.message, n.disabled = a));
				});
			}), m.append(n);
		}
		if (!d && !i.allowOpaqueFallback) {
			let e = document.createElement("button");
			e.type = "button", e.textContent = "使用原图矩形继续", e.disabled = a, e.addEventListener("click", () => {
				!a && i !== null && n(i);
			}), m.append(e);
		}
		c.replaceChildren(l, u, p, m);
	};
	return l(), {
		element: c,
		update: (e) => {
			i = e === null ? null : structuredClone(e), s += 1, l();
		},
		setDisabled: (e) => {
			a = e, l();
		},
		dispose: () => {
			o || (o = !0, s += 1, c.remove());
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/asset-uploader.ts
function of(e) {
	return e instanceof DOMException && e.name === "AbortError" || typeof e == "object" && !!e && "name" in e && e.name === "AbortError";
}
function sf({ api: e, onUploaded: t }) {
	let n = null, r = !1, i = !1, a = null, o = document.createElement("section");
	o.className = "canvas-asset-uploader", o.dataset.testid = "canvas-asset-uploader";
	let s = document.createElement("h3");
	s.textContent = "主商品素材";
	let c = document.createElement("label");
	c.className = "canvas-asset-dropzone", c.dataset.testid = "canvas-asset-dropzone", c.textContent = "拖放图片，或选择文件";
	let l = document.createElement("input");
	l.type = "file", l.accept = "image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp", l.setAttribute("aria-label", "上传主商品图片"), c.append(l);
	let u = document.createElement("p");
	u.className = "canvas-asset-feedback", u.setAttribute("role", "status"), u.setAttribute("aria-live", "polite"), o.append(s, c, u);
	let d = () => {
		l.disabled = r || n === null || i, c.dataset.disabled = String(l.disabled);
	}, f = async (o) => {
		if (i || r || n === null) return;
		let s = Vd(o);
		if (!s.ok) {
			u.textContent = s.message, u.dataset.state = "validation";
			return;
		}
		a?.abort();
		let c = new AbortController();
		a = c;
		let l = n;
		u.dataset.state = "uploading", u.textContent = "正在上传…";
		try {
			let r = await e.uploadAsset({
				projectId: l,
				file: o,
				signal: c.signal,
				onProgress: ({ percent: e, loaded: t, total: n }) => {
					a !== c || c.signal.aborted || (u.textContent = e === null ? `正在上传 ${t} 字节…` : `正在上传 ${e}%${n === null ? "" : `（${t}/${n}）`}`);
				}
			});
			if (i || c.signal.aborted || a !== c || n !== l) return;
			if (!r.ok) {
				u.dataset.state = r.kind, u.textContent = r.message;
				return;
			}
			u.dataset.state = "complete", u.textContent = `上传完成：${r.value.source.id} / ${r.value.working.id} / ${r.value.preview.id}`, t(r.value);
		} catch (e) {
			!of(e) && a === c && !i && (u.dataset.state = "offline", u.textContent = "上传失败，请检查网络后重试");
		} finally {
			a === c && (a = null);
		}
	};
	return l.addEventListener("change", () => {
		let e = l.files?.[0];
		e !== void 0 && f(e);
	}), c.addEventListener("dragover", (e) => {
		e.preventDefault();
	}), c.addEventListener("drop", (e) => {
		e.preventDefault();
		let t = e.dataTransfer?.files[0];
		t !== void 0 && f(t);
	}), d(), {
		element: o,
		setProject: (e) => {
			n !== e && (a?.abort(), a = null, l.value = "", u.textContent = "", delete u.dataset.state), n = e, d();
		},
		setDisabled: (e) => {
			r = e, r && (a?.abort(), a = null), d();
		},
		dispose: () => {
			i || (i = !0, a?.abort(), a = null, d(), o.remove());
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/sku-editor.ts
function cf({ api: e, onSnapshot: t }) {
	let n = null, r = !1, i = !1, a = !1, o = 0, s = document.createElement("section");
	s.className = "canvas-sku-editor", s.dataset.testid = "canvas-sku-editor";
	let c = document.createElement("p");
	c.className = "canvas-sku-feedback", c.setAttribute("role", "status"), c.setAttribute("aria-live", "polite");
	let l = () => i || n === null || n.disabled || r, u = () => {
		for (let e of s.querySelectorAll("button,input,select,textarea")) e.disabled = l();
	}, d = (e) => {
		n === null || e.project.id !== n.projectId || (n = {
			...n,
			revision: e.revision,
			skus: e.skus.map((e) => structuredClone(e))
		}, t(e));
	}, f = () => {
		if (r) return;
		let t = document.createElement("h3");
		if (t.textContent = "SKU", n === null) {
			let e = document.createElement("p");
			e.textContent = "选择项目后编辑 SKU。", s.replaceChildren(t, e, c);
			return;
		}
		let i = document.createElement("div");
		i.className = "canvas-sku-create";
		let a = document.createElement("input");
		a.type = "text", a.maxLength = 200, a.setAttribute("aria-label", "新 SKU 名称");
		let o = document.createElement("button");
		o.type = "button", o.textContent = "新增 SKU", o.setAttribute("aria-label", "新增 SKU"), o.addEventListener("click", () => {
			let t = a.value.trim();
			if (t === "") {
				c.textContent = "请输入 SKU 名称";
				return;
			}
			p((n) => e.createSku(n.projectId, n.revision, { name: t }));
		}), i.append(a, o);
		let l = document.createElement("div");
		l.className = "canvas-sku-list";
		let d = [...n.skus].sort((e, t) => e.sortOrder - t.sortOrder || e.id.localeCompare(t.id));
		d.forEach((t, r) => {
			let i = document.createElement("fieldset");
			i.className = "canvas-sku-row", i.dataset.skuId = t.id;
			let a = document.createElement("legend");
			a.textContent = t.name;
			let o = document.createElement("label");
			o.textContent = "名称";
			let s = document.createElement("input");
			s.type = "text", s.maxLength = 200, s.value = t.name, s.setAttribute("aria-label", `SKU ${t.name} 名称`), s.addEventListener("change", () => {
				let n = s.value.trim();
				n !== "" && n !== t.name && p((r) => e.updateSku(r.projectId, t.id, r.revision, { name: n }));
			}), o.append(s);
			let c = document.createElement("label");
			c.textContent = "提示词";
			let u = document.createElement("textarea");
			u.maxLength = 4e3, u.value = t.prompt, u.setAttribute("aria-label", `SKU ${t.name} 提示词`), u.addEventListener("change", () => {
				u.value !== t.prompt && p((n) => e.updateSku(n.projectId, t.id, n.revision, { prompt: u.value }));
			}), c.append(u);
			let f = document.createElement("label");
			f.textContent = "参考素材";
			let h = document.createElement("select");
			h.setAttribute("aria-label", `SKU ${t.name} 参考素材`);
			let g = document.createElement("option");
			g.value = "", g.textContent = "沿用主商品素材", h.append(g);
			for (let e of n?.referenceAssets ?? []) {
				let t = document.createElement("option");
				t.value = e.id, t.textContent = e.label, h.append(t);
			}
			h.value = t.referenceAssetId ?? "", h.addEventListener("change", () => {
				let n = h.value === "" ? null : h.value;
				n !== t.referenceAssetId && p((r) => e.updateSku(r.projectId, t.id, r.revision, { referenceAssetId: n }));
			}), f.append(h);
			let _ = document.createElement("p");
			_.className = "canvas-sku-reference-resolution", _.textContent = t.referenceAssetId === null ? n?.mainProductAssetId === null ? "缺少主商品素材；SKU 名称不会生成包装图" : `沿用主商品素材 ${n?.mainProductAssetId}` : `使用 SKU 参考素材 ${t.referenceAssetId}`;
			let v = document.createElement("div");
			v.className = "canvas-sku-actions";
			let y = document.createElement("button");
			y.type = "button", y.textContent = "上移", y.setAttribute("aria-label", `上移 SKU ${t.name}`), y.disabled = r === 0, y.addEventListener("click", () => {
				r > 0 && m(t.id, { sortOrder: d[r - 1].sortOrder });
			});
			let b = document.createElement("button");
			b.type = "button", b.textContent = "下移", b.setAttribute("aria-label", `下移 SKU ${t.name}`), b.disabled = r === d.length - 1, b.addEventListener("click", () => {
				r < d.length - 1 && m(t.id, { sortOrder: d[r + 1].sortOrder });
			});
			let x = document.createElement("button");
			x.type = "button", x.textContent = "删除", x.setAttribute("aria-label", `删除 SKU ${t.name}`), x.addEventListener("click", () => {
				p((n) => e.deleteSku(n.projectId, t.id, n.revision));
			}), v.append(y, b, x), i.append(a, o, c, f, _, v), l.append(i);
		}), s.replaceChildren(t, i, l, c), u();
	}, p = async (e) => {
		if (n === null || l()) return;
		let t = ++o;
		i = !0, a = !0, c.textContent = "正在保存 SKU…", u();
		let s = await e(n);
		if (!(r || t !== o)) {
			if (i = !1, s.ok) {
				a = !1, c.textContent = "SKU 已保存", d(s.snapshot), f();
				return;
			}
			s.kind === "conflict" ? c.textContent = `版本冲突（服务器版本 ${s.currentRevision}），未覆盖本地编辑` : c.textContent = s.message, u();
		}
	}, m = (t, n) => p((r) => e.updateSku(r.projectId, t, r.revision, n));
	return f(), {
		element: s,
		update: (e) => {
			let t = n !== null && e !== null && n.projectId === e.projectId, r = e === null ? null : {
				...e,
				skus: e.skus.map((e) => structuredClone(e)),
				referenceAssets: e.referenceAssets.map((e) => ({ ...e }))
			};
			if (t && (i || a)) {
				n = r, u();
				return;
			}
			t || (o += 1, i = !1, a = !1), n = r, c.textContent = "", f();
		},
		dispose: () => {
			r || (r = !0, o += 1, s.remove());
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/composition-inspector.ts
var lf = [
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
function uf(e, t) {
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
function df(e, t, n) {
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
function ff({ onUpdate: e }) {
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
		for (let [r, i, o, s, c] of lf) {
			let l = document.createElement("label");
			l.textContent = i;
			let u = document.createElement("input");
			u.type = "number", u.min = String(o), u.max = String(s), u.step = String(c), u.value = String(uf(t.layout, r)), u.disabled = t.disabled, u.dataset.field = r === "baseline" ? "baseline" : r, u.addEventListener("change", () => {
				if (n || t === null || t.disabled) return;
				let i = Number(u.value);
				if (!Number.isFinite(i)) return;
				let a = structuredClone(t.layout);
				df(a, r, i), e(t.groupId, a);
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
function pf(e, t, n, r, i = "text") {
	let a = document.createElement("input");
	return a.type = i, a.value = t, a.disabled = n, a.dataset.testid = e, a.addEventListener("change", () => r(a.value)), a;
}
function mf({ onSelect: e, onUpdate: t }) {
	let n = {
		layers: [],
		selectedLayerId: null,
		disabled: !0
	}, r = !1, i = document.createElement("section");
	i.className = "canvas-text-inspector", i.dataset.testid = "canvas-text-inspector";
	let a = () => {
		let r = document.createElement("h3");
		r.textContent = "文字图层";
		let a = document.createElement("select");
		a.dataset.testid = "canvas-text-layer-select", a.disabled = n.disabled || n.layers.length === 0, a.append(...n.layers.map((e, t) => Object.assign(document.createElement("option"), {
			value: e.id,
			textContent: `${t + 1}. ${e.content || e.id}`
		})));
		let o = n.layers.find((e) => e.id === n.selectedLayerId) ?? n.layers[0] ?? null;
		if (a.value = o?.id ?? "", a.addEventListener("change", () => e?.(a.value || null)), o === null) {
			let e = document.createElement("p");
			e.textContent = "暂无文字图层", i.replaceChildren(r, a, e);
			return;
		}
		let s = document.createElement("div");
		s.className = "canvas-text-fields";
		let c = (e, t) => {
			let n = document.createElement("label");
			n.append(e, t), s.append(n);
		}, l = document.createElement("textarea");
		l.value = o.content, l.disabled = n.disabled, l.dataset.testid = "canvas-text-content";
		let u = document.createElement("p");
		u.className = "canvas-text-feedback", u.dataset.testid = "canvas-text-content-feedback", u.setAttribute("role", "alert"), l.addEventListener("change", () => {
			try {
				t(o.id, _(o, l.value)), u.textContent = "";
			} catch (e) {
				l.value = o.content, u.textContent = e instanceof Error ? e.message : "文字内容更新失败";
			}
		}), c("内容", l), s.append(u);
		let d = (e, r, i, a) => c(e, pf(r, String(i), n.disabled, (e) => {
			let n = Number(e);
			Number.isFinite(n) && t(o.id, { [a]: n });
		}, "number"));
		d("文本框宽度", "canvas-text-box-width", o.boxWidth, "boxWidth");
		let f = pf("canvas-text-font-size", String(o.fontSize), n.disabled, (e) => {
			let n = Number(e);
			Number.isInteger(n) && n > 0 && t(o.id, { fontSize: n });
		}, "number");
		f.min = "1", f.max = "10000", f.step = "1", c("字号", f), c("颜色", pf("canvas-text-color", o.color, n.disabled, (e) => {
			t(o.id, { color: e });
		}, "color")), d("字间距", "canvas-text-letter-spacing", o.letterSpacing, "letterSpacing"), c("行距", pf("canvas-text-line-height", String(o.lineHeight), n.disabled, (e) => {
			let n = Number(e);
			Number.isFinite(n) && n > 0 && t(o.id, g(o, n));
		}, "number"));
		let p = (e, r, i, a, s) => {
			let l = document.createElement("select");
			l.dataset.testid = r, l.disabled = n.disabled, l.append(...a.map((e) => Object.assign(document.createElement("option"), {
				value: e,
				textContent: e
			}))), l.value = i, l.addEventListener("change", () => t(o.id, s(l.value))), c(e, l);
		};
		p("对齐", "canvas-text-align", o.align, [
			"left",
			"center",
			"right"
		], (e) => ({ align: e })), p("基线", "canvas-text-baseline", o.baseline, [
			"alphabetic",
			"top",
			"middle",
			"bottom"
		], (e) => ({ baseline: e })), p("层级", "canvas-text-z-band", o.zBand, ["below-product", "above-product"], (e) => ({ zBand: e }));
		let m = document.createElement("div");
		m.className = "canvas-text-lines", o.lines.forEach((e, r) => {
			let i = document.createElement("fieldset"), a = (e) => {
				let n = o.lines.map((t, n) => n === r ? {
					...t,
					...e
				} : { ...t });
				t(o.id, { lines: n });
			};
			i.append(pf(`canvas-text-line-text-${r}`, e.text, n.disabled, (e) => a({ text: e })), pf(`canvas-text-line-x-${r}`, String(e.x), n.disabled, (e) => {
				let t = Number(e);
				Number.isFinite(t) && a({ x: t });
			}, "number"), pf(`canvas-text-line-y-${r}`, String(e.y), n.disabled, (e) => {
				let t = Number(e);
				Number.isFinite(t) && a({ y: t });
			}, "number"), pf(`canvas-text-line-width-${r}`, String(e.width), n.disabled, (e) => {
				let t = Number(e);
				Number.isFinite(t) && a({ width: t });
			}, "number")), m.append(i);
		}), s.append(m), i.replaceChildren(r, a, s);
	};
	return a(), {
		element: i,
		update: (e) => {
			r || (n = structuredClone(e), a());
		},
		dispose: () => {
			r = !0, i.replaceChildren();
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/status-bar.ts
var hf = {
	dirty: "有未保存更改",
	saving: "正在保存…",
	saved: "已保存",
	offline: "离线，等待重试",
	failed: "保存失败",
	conflict: "检测到版本冲突"
}, gf = {
	ready: "抠图：素材已就绪",
	queued: "抠图：已排队",
	running: "抠图：处理中",
	failed: "抠图：失败",
	interrupted: "抠图：已中断"
};
function _f(e, t) {
	let n = document.createElement("footer");
	return n.className = "canvas-status-bar", n.dataset.testid = "canvas-save-status", n.setAttribute("role", "status"), n.setAttribute("aria-live", "polite"), {
		element: n,
		update: (r, i, a = null) => {
			let o = () => {
				if (a === null) return;
				let e = document.createElement("span");
				e.className = `canvas-cutout-summary is-${a}`, e.dataset.testid = "canvas-cutout-summary", e.textContent = gf[a], n.append(e);
			};
			if (i.status !== "idle") {
				n.dataset.state = `remote-${i.status}`;
				let e = document.createElement("span");
				e.className = `canvas-save-state is-remote-${i.status}`, e.textContent = i.status === "syncing" ? "正在同步远端更改…" : "远端同步失败";
				let r = document.createElement("span");
				if (r.className = "canvas-save-message", r.textContent = i.message ?? "", n.replaceChildren(e, r), i.status === "failed") {
					let e = document.createElement("button");
					e.type = "button", e.textContent = "重试同步", e.dataset.testid = "canvas-remote-sync-retry", e.addEventListener("click", t), n.append(e);
				}
				o();
				return;
			}
			n.dataset.state = r.status;
			let s = document.createElement("span");
			s.className = `canvas-save-state is-${r.status}`, s.textContent = hf[r.status];
			let c = document.createElement("span");
			if (c.className = "canvas-save-message", c.textContent = r.message ?? "", n.replaceChildren(s, c), r.status === "offline" || r.status === "failed") {
				let t = document.createElement("button");
				t.type = "button", t.textContent = "重试保存", t.addEventListener("click", e), n.append(t);
			}
			o();
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/top-toolbar.ts
function vf(e, t, n, r, i) {
	let a = !1, o = document.createElement("header");
	o.className = "canvas-top-toolbar", o.dataset.testid = "canvas-top-toolbar";
	let s = document.createElement("a");
	s.href = "/app", s.className = "canvas-toolbar-back", s.textContent = "返回 AI 工作";
	let c = document.createElement("label");
	c.textContent = "模式";
	let l = document.createElement("select");
	l.setAttribute("aria-label", "画布模式"), l.dataset.testid = "canvas-mode", l.innerHTML = "<option value=\"complete-set\">完整套图</option><option value=\"advanced\">高级模式</option>", l.addEventListener("change", () => {
		(l.value === "complete-set" || l.value === "advanced") && t({
			type: "mode/set",
			mode: l.value
		});
	}), c.append(l);
	let u = document.createElement("button");
	u.type = "button", u.textContent = "撤销", u.dataset.testid = "canvas-undo", u.addEventListener("click", n);
	let d = document.createElement("button");
	d.type = "button", d.textContent = "重做", d.dataset.testid = "canvas-redo", d.addEventListener("click", r);
	let f = (e) => {
		t({
			type: "viewport/set",
			viewport: e
		});
	}, p = (t) => {
		let n = e.getState().project.layoutState.viewport;
		f({
			...n,
			zoom: Math.min(1e3, Math.max(.01, n.zoom * t))
		});
	}, m = document.createElement("button");
	m.type = "button", m.textContent = "缩小", m.dataset.testid = "canvas-zoom-out", m.addEventListener("click", () => p(.8));
	let h = document.createElement("button");
	h.type = "button", h.textContent = "放大", h.dataset.testid = "canvas-zoom-in", h.addEventListener("click", () => p(1.25));
	let g = document.createElement("button");
	g.type = "button", g.textContent = "重置视图", g.dataset.testid = "canvas-zoom-reset", g.addEventListener("click", () => f({
		x: 0,
		y: 0,
		zoom: 1
	}));
	let _ = document.createElement("output");
	_.dataset.testid = "canvas-zoom-readout", _.setAttribute("aria-label", "当前缩放");
	let v = (e, t) => {
		let n = document.createElement("button");
		return n.type = "button", n.textContent = e, n.disabled = !0, n.title = t, n;
	}, y = document.createElement("button");
	y.type = "button", y.textContent = "导出", y.dataset.testid = "canvas-toolbar-export", y.title = "打开导出产品图选项", y.addEventListener("click", () => {
		i?.();
	}), o.append(s, c, u, d, m, h, g, _, v("模型设置", "模型设置将在生成能力接入后开放"), y);
	let b = () => {
		let t = e.getState();
		l.value = t.project.semanticState.mode, l.disabled = !a, u.disabled = !a || !e.canUndo(), d.disabled = !a || !e.canRedo(), m.disabled = !a, h.disabled = !a, g.disabled = !a, y.disabled = !a || i === void 0, _.value = `${Math.round(t.project.layoutState.viewport.zoom * 100)}%`;
	};
	return b(), {
		element: o,
		update: b,
		setEditable: (e) => {
			a = e, b();
		}
	};
}
//#endregion
//#region frontend/canvas/src/domain/generation.ts
var yf = {
	main: "main_output",
	sku: "sku_output",
	detail: "detail_output"
}, bf = {
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
function xf(e, t) {
	let n = (e, t) => t === 0 ? e : n(t, e % t), r = n(e, t);
	return `${e / r}:${t / r}`;
}
function Sf(e) {
	return `${e.outputType}:${e.skuId ?? "main"}`;
}
function Cf(e) {
	return e.quantity ?? 0;
}
function wf(e, t) {
	if (t === null) return null;
	let n = e.find((e) => e.id === t);
	return n !== void 0 && n.enabled && n.availability === "available" ? n : null;
}
function Tf(e, t, n, r, i, a) {
	let o = e.capabilities;
	if (!o.textToImage || o.maxQuantity < 1) return $("model_capability_invalid", `${i}所选模型不能生成单张图`, a);
	if (r > 0 && (!o.imageToImage || o.maxReferenceImages < r || o.referenceTransfer === "none")) return $("model_capability_invalid", `${i}所选模型不支持产品参考图`, a);
	let s = xf(t, n);
	return o.allowedRatios.length > 0 && !o.allowedRatios.includes(s) || o.allowedSizes.length > 0 && !o.allowedSizes.includes(`${t}x${n}`) || o.minWidth !== null && t < o.minWidth || o.maxWidth !== null && t > o.maxWidth || o.minHeight !== null && n < o.minHeight || o.maxHeight !== null && n > o.maxHeight ? $("model_capability_invalid", `${i}尺寸不受所选模型支持`, a) : null;
}
function Ef(e) {
	return e.layoutState.productLayers.find((e) => e.skuId === null && e.locked)?.sourceAssetId ?? null;
}
function Df(e, t) {
	let n = e.layoutState.productLayers.find((e) => e.skuId === t.skuId && e.locked);
	if (t.outputType !== "sku") return t.referenceAssetId ?? n?.sourceAssetId ?? null;
	let r = Ef(e);
	return n === void 0 ? t.referenceAssetId !== null && t.referenceAssetId === r ? r : null : t.referenceAssetId === null || t.referenceAssetId === n.sourceAssetId ? n.sourceAssetId : t.referenceAssetId === r ? r : null;
}
function Of(e, t, n) {
	let r = e.layoutState.productLayers.find((e) => e.skuId === null && e.locked);
	if (r === void 0) return null;
	let i = e.semanticState.nodes.find((e) => e.id === "main-product-source"), a = e.semanticState.nodes.find((e) => e.id === "main-product-cutout");
	if (i?.kind !== "product_source" || i.skuId !== null || i.assetId !== r.sourceAssetId || a?.kind !== "auto_cutout" || a.skuId !== null || a.assetId !== r.renderAssetId) return null;
	let o = e.semanticState.edges.filter((e) => e.kind === "product_asset" && e.targetNodeId === a.id);
	if (o.length !== 1 || o[0]?.sourceNodeId !== i.id) return null;
	let s = e.semanticState.edges.filter((e) => e.kind === "cutout_asset" && e.targetNodeId === t);
	return s.length === 1 && s[0]?.sourceNodeId === a.id ? a.assetId : null;
}
function kf(e, t) {
	return $("advanced_graph_invalid", e, t);
}
function Af(e) {
	let t = e.parameters.width, n = e.parameters.height;
	return typeof t != "number" || !Number.isInteger(t) || t < 1 || typeof n != "number" || !Number.isInteger(n) || n < 1 ? null : {
		width: t,
		height: n,
		ratio: xf(t, n)
	};
}
function jf(e, t, n) {
	let r = e.semanticState.edges.filter((e) => e.kind === t && e.targetNodeId === n);
	return r.length === 1 ? r[0] : null;
}
function Mf(e, t) {
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
function Nf(e, t, n) {
	let r = [];
	for (let n of e.semanticState.outputBoards) {
		let i = e.semanticState.nodes.find((e) => e.id === n.outputNodeId);
		if (i === void 0 || i.outputBoardId !== n.id || i.kind !== yf[n.outputType]) return kf("高级模式输出画板缺少绑定节点", n.outputType);
		if (i.modelProfileId !== null || i.prompt !== null || i.compositionGroupId !== null) return kf("高级模式输出绑定必须通过连线表达", n.outputType);
		if (e.semanticState.edges.some((e) => e.kind === "background_image" && e.targetNodeId === i.id)) return kf("高级模式暂不支持背景图连线", n.outputType);
		let a = jf(e, "output_image", i.id), o = a === null ? void 0 : e.semanticState.nodes.find((e) => e.id === a.sourceNodeId);
		if (o?.kind !== "model_generation") return kf("高级模式输出必须连接生成节点", n.outputType);
		let s = jf(e, "prompt", o.id), c = s === null ? "" : e.semanticState.nodes.find((e) => e.id === s.sourceNodeId)?.prompt ?? "";
		if (c.trim() === "") return kf("高级模式生成节点缺少提示词", n.outputType);
		let l = wf(t, o.modelProfileId);
		if (l === null) return $("model_unavailable", "高级模式需要选择可用模型", n.outputType);
		let u = Af(o);
		if (u === null) return $("invalid_dimensions", "高级模式生成节点需要有效宽高", n.outputType);
		let d = Of(e, o.id, n.skuId);
		if (d === null) return $("product_missing", "高级模式生成节点缺少产品参考图", n.outputType);
		let f = jf(e, "composition", i.id), p = (f === null ? void 0 : e.semanticState.nodes.find((e) => e.id === f.sourceNodeId))?.compositionGroupId ?? null, m = p === null ? void 0 : e.semanticState.compositionGroups.find((e) => e.id === p);
		if (m === void 0) return $("composition_missing", "高级模式输出缺少构图组", n.outputType);
		let h = Mf(e, i.id);
		if (h === null) return kf("高级模式文字必须通过文字图层连线到输出画板", n.outputType);
		let g = Tf(l, u.width, u.height, 1, bf[n.outputType], n.outputType);
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
	return r.length === 0 ? kf("高级模式没有连接的输出画板") : r.length > 50 ? $("too_many_items", "本次生成最多支持 50 张图") : {
		ok: !0,
		request: {
			revision: n,
			mode: "advanced",
			items: r
		}
	};
}
function Pf(e, t, n) {
	if (!Number.isInteger(n) || n < 1) throw Error("generation revision must be a positive integer");
	if (e.semanticState.mode === "advanced") return Nf(e, t, n);
	let r = e.semanticState.completeSet.selectedOutputTypes;
	if (r.length === 0) return $("no_output_selected", "至少选择一种输出类型");
	let i = new Set(r), a = e.semanticState.completeSet.outputs.filter((e) => i.has(e.outputType)), o = new Set(r.flatMap((e) => e === "sku" ? a.filter((e) => e.outputType === "sku").map(Sf) : [Sf({
		outputType: e,
		skuId: null
	})]));
	if (a.length === 0 || o.size !== a.length) {
		let e = r.find((e) => e === "sku" ? !a.some((e) => e.outputType === "sku") : !a.some((t) => t.outputType === e && t.skuId === null));
		return $("output_configuration_missing", `${bf[e ?? r[0]]}缺少生成配置`, e ?? r[0]);
	}
	let s = [];
	for (let n of a) {
		let r = bf[n.outputType], i = Cf(n);
		if (!Number.isInteger(i) || i < 1 || i > 20) return $("invalid_quantity", `${r}数量必须为 1 到 20`, n.outputType);
		if (!Number.isInteger(n.width) || !Number.isInteger(n.height) || n.width === null || n.height === null || n.width < 1 || n.height < 1 || n.aspectRatio === null || n.aspectRatio !== xf(n.width, n.height)) return $("invalid_dimensions", `${r}需要匹配的比例与尺寸`, n.outputType);
		let a = wf(t, n.modelProfileId);
		if (a === null) return $("model_unavailable", `${r}需要选择可用模型`, n.outputType);
		let o = e.layoutState.productLayers.find((e) => e.skuId === n.skuId && e.locked), c = Df(e, n);
		if (c === null) return $("product_missing", n.outputType === "sku" ? "SKU图缺少自身产品参考图或明确的主产品复用" : `${r}缺少产品参考图`, n.outputType);
		let l = n.compositionGroupId ?? o?.compositionGroupId ?? null, u = l === null ? null : e.semanticState.compositionGroups.find((e) => e.id === l);
		if (u == null) return $("composition_missing", `${r}缺少构图组`, n.outputType);
		let d = Tf(a, n.width, n.height, 1, r, n.outputType);
		if (d !== null) return d;
		let f = e.semanticState.outputBoards.filter((e) => e.outputType === n.outputType && e.skuId === n.skuId).sort((e, t) => e.sortOrder - t.sortOrder || e.id.localeCompare(t.id));
		if (f.length !== i) return $("board_count_mismatch", `${r}的画板数量与输出数量不一致`, n.outputType);
		for (let t of f) {
			let i = e.semanticState.nodes.find((e) => e.id === t.outputNodeId);
			if (i === void 0 || i.kind !== yf[n.outputType] || i.outputBoardId !== t.id) return $("output_binding_missing", `${r}缺少独立输出节点`, n.outputType);
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
function Ff(e, t, n) {
	return !Number.isInteger(n) || n < 1 ? $("revision_pending", "项目尚未保存，暂不能生成") : Pf(e, t, n);
}
//#endregion
//#region frontend/canvas/src/domain/providers.ts
var If = [
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
function Lf(e, t) {
	let n = (e, t) => t === 0 ? e : n(t, e % t), r = n(e, t);
	return `${e / r}:${t / r}`;
}
function Rf(e, t) {
	let n = [], r = e.capabilities;
	if (!e.enabled || e.availability !== "available") return n.push(e.availabilityReason ?? "模型当前不可用"), n;
	let i = t.quantity;
	i != null && i > r.maxQuantity && n.push(`单次最多支持 ${r.maxQuantity} 张`);
	let a = t.referenceCount ?? 0;
	a > 0 && (!r.imageToImage || r.maxReferenceImages < a || r.referenceTransfer === "none") && n.push("不支持当前产品参考图"), t.requiresMask && !r.maskEdit && n.push("不支持蒙版编辑");
	let o = t.width, s = t.height;
	if (o != null && s != null) {
		let e = `${o}x${s}`;
		(r.allowedSizes.length > 0 && !r.allowedSizes.includes(e) || r.allowedRatios.length > 0 && !r.allowedRatios.includes(Lf(o, s)) || r.minWidth !== null && o < r.minWidth || r.maxWidth !== null && o > r.maxWidth || r.minHeight !== null && s < r.minHeight || r.maxHeight !== null && s > r.maxHeight) && n.push("不支持当前尺寸或比例");
	}
	return n;
}
//#endregion
//#region frontend/canvas/src/components/model-selector.ts
function zf({ label: e, value: t, models: n, disabled: r, requirements: i, onChange: a }) {
	let o = document.createElement("label");
	o.className = "canvas-model-selector", o.textContent = e;
	let s = document.createElement("select");
	s.setAttribute("aria-label", e), s.disabled = r, s.append(Object.assign(document.createElement("option"), {
		value: "",
		textContent: "请选择模型"
	}));
	for (let e of n) {
		let t = document.createElement("option");
		t.value = e.id, t.textContent = e.availability === "available" && e.enabled ? e.displayName : `${e.displayName}（不可用）`, t.disabled = !e.enabled || e.availability !== "available", s.append(t);
	}
	s.value = t ?? "", s.addEventListener("change", () => a(s.value === "" ? null : s.value)), o.append(s);
	let c = t === null ? void 0 : n.find((e) => e.id === t);
	if (c !== void 0 && i !== void 0) {
		let e = Rf(c, i);
		if (e.length > 0) {
			let t = document.createElement("small");
			t.className = "canvas-model-selector-reason", t.dataset.testid = "canvas-model-capability-reason", t.textContent = e.join("；"), o.append(t);
		}
	}
	return o;
}
//#endregion
//#region frontend/canvas/src/components/complete-set-panel.ts
var Bf = [
	"main",
	"sku",
	"detail"
], Vf = {
	main: "主图",
	sku: "SKU 图",
	detail: "详情图"
};
function Hf(e, t) {
	if (e === null || t === null || e < 1 || t < 1) return null;
	let n = (e, t) => t === 0 ? e : n(t, e % t), r = n(e, t);
	return `${e / r}:${t / r}`;
}
function Uf(e, t, n) {
	return e.semanticState.completeSet.outputs.find((e) => e.outputType === t && e.skuId === n) ?? null;
}
function Wf(e, t, n, r, i) {
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
function Gf(e) {
	let t = document.createElement("section");
	t.className = "canvas-complete-set-panel", t.dataset.testid = "canvas-complete-set-panel";
	let n = (t, n, r, i) => {
		let a = document.createElement("fieldset");
		a.className = "canvas-output-control";
		let o = document.createElement("legend");
		o.textContent = r === null ? Vf[n] : `${Vf[n]} · ${e.getSkus().find((e) => e.id === r)?.name ?? r}`, a.append(o);
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
		a.append(zf({
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
					aspectRatio: Hf(n, a)
				});
			}), n.append(r), n;
		};
		a.append(m("width", "宽"), m("height", "高"));
		let h = t.semanticState.compositionGroups.map((e) => ({
			id: e.id,
			label: e.id
		})), g = c !== void 0 && (!c.capabilities.imageToImage || c.capabilities.maxReferenceImages < 1 || c.capabilities.referenceTransfer === "none");
		return a.append(Wf("产品参考图", i.referenceAssetId, e.getReferenceAssets(), s || g, (e) => d({ referenceAssetId: e })), Wf("构图组", i.compositionGroupId, h, s, (e) => d({ compositionGroupId: e }))), a;
	}, r = () => {
		let r = e.getProject(), i = new Set(r.semanticState.completeSet.selectedOutputTypes), a = document.createElement("h2");
		a.textContent = "套图生成";
		let o = document.createElement("p");
		o.textContent = "按需选择主图、SKU 图和详情图；未选择时不会生成。";
		let s = document.createElement("div");
		s.className = "canvas-output-type-selector";
		for (let t of Bf) {
			let n = document.createElement("input");
			n.type = "checkbox", n.checked = i.has(t), n.setAttribute("aria-label", `启用${Vf[t]}`), n.disabled = !e.isEditable(), n.addEventListener("change", () => e.dispatch({
				type: n.checked ? "output/enable" : "output/disable",
				outputType: t
			}));
			let r = document.createElement("button");
			r.type = "button", r.dataset.testid = `canvas-output-${t}`, r.dataset.selected = String(i.has(t)), r.setAttribute("aria-pressed", String(i.has(t))), r.disabled = !e.isEditable(), r.textContent = i.has(t) ? `已选${Vf[t]}` : `选择${Vf[t]}`, r.addEventListener("click", () => {
				n.checked = !n.checked, n.dispatchEvent(new Event("change", { bubbles: !0 }));
			});
			let a = document.createElement("label");
			a.className = "canvas-output-choice", a.append(n, r), s.append(a);
		}
		let c = document.createElement("div");
		c.className = "canvas-complete-set-form";
		for (let e of ["main", "detail"]) i.has(e) && c.append(n(r, e, null, Uf(r, e, null)));
		if (i.has("sku")) {
			let t = e.getSkus();
			t.length === 0 && c.append(Object.assign(document.createElement("p"), { textContent: "请先新增 SKU，再设置 SKU 图数量。" }));
			for (let e of t) c.append(n(r, "sku", e.id, Uf(r, "sku", e.id)));
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
		let _ = Ff(r, [...e.getModels()], e.getRevision()), v = document.createElement("p");
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
function Kf() {
	let e = document.createElement("p");
	return e.className = "canvas-generation-status", e.dataset.testid = "canvas-generation-status", e.setAttribute("role", "status"), {
		element: e,
		update: (t, n = "idle") => {
			e.dataset.tone = n, e.textContent = t;
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/access-dialog.ts
function qf() {
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
//#region frontend/canvas/src/components/node-inspector.ts
function Jf() {
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
			let n = d[0], r = n === void 0 ? void 0 : d.find((e) => e.id !== n.id && x(n.kind, e.kind).length > 0);
			e.value = n?.id ?? "", t.value = r?.id ?? n?.id ?? "";
			let i = document.createElement("button");
			i.type = "button", i.textContent = "连接节点";
			let o = () => {
				let n = d.find((t) => t.id === e.value), r = d.find((e) => e.id === t.value);
				i.disabled = a || n === void 0 || r === void 0 || n.id === r.id || x(n.kind, r.kind).length === 0;
			};
			e.addEventListener("change", o), t.addEventListener("change", o), i.addEventListener("click", () => {
				let n = d.find((t) => t.id === e.value), r = d.find((e) => e.id === t.value);
				n !== void 0 && r !== void 0 && n.id !== r.id && x(n.kind, r.kind).length > 0 && s(e.value, t.value);
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
var Yf = [
	"prompt",
	"model_generation",
	"composition_group",
	"text_layer"
];
function Xf(e, t) {
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
function Zf({ disabled: e, onAdd: t, nextId: n }) {
	let r = document.createElement("section");
	r.className = "canvas-node-toolbar", r.append(Object.assign(document.createElement("h3"), { textContent: "高级节点" }));
	for (let i of Yf) {
		let a = document.createElement("button");
		a.type = "button", a.disabled = e, a.textContent = `添加 ${i}`, a.addEventListener("click", () => {
			t(Xf(i, n(i)));
		}), r.append(a);
	}
	return r;
}
//#endregion
//#region frontend/canvas/src/components/result-board.ts
function Qf() {
	let e = document.createElement("section");
	return e.className = "canvas-result-board", {
		element: e,
		update: (t, n, r, i) => {
			let a = document.createElement("h3");
			if (a.textContent = "结果版本", t === null) {
				e.replaceChildren(a, Object.assign(document.createElement("p"), { textContent: "暂无输出画板" }));
				return;
			}
			let o = document.createElement("select");
			o.disabled = r, o.setAttribute("aria-label", "选择结果版本"), o.append(Object.assign(document.createElement("option"), {
				value: "",
				textContent: "请选择版本"
			}));
			for (let e of n.filter((e) => e.boardId === t.id)) o.append(Object.assign(document.createElement("option"), {
				value: e.composedAssetId,
				textContent: `${e.modelDisplayName} · ${e.createdAt}`
			}));
			o.value = t.selectedResultAssetId ?? "", o.addEventListener("change", () => {
				i(o.value || null);
			}), e.replaceChildren(a, o);
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/model-profile-editor.ts
var $f = {
	text_to_image: !0,
	image_to_image: !0,
	mask_edit: !1,
	allowed_ratios: [],
	allowed_sizes: [],
	min_width: null,
	max_width: null,
	min_height: null,
	max_height: null,
	max_quantity: 1,
	max_reference_images: 1,
	reference_transfer: "bytes",
	protocol: "sync",
	supports_cancel: !1,
	supports_idempotency: !0,
	supports_idempotency_lookup: !1,
	concurrency_limit: 1,
	price_metadata: null
};
function ep(e) {
	let t = document.createElement("section");
	t.className = "canvas-model-profile-editor", t.dataset.testid = "canvas-model-profile-editor";
	let n = document.createElement("h3");
	n.textContent = "添加模型能力配置";
	let r = document.createElement("form"), i = (e) => {
		let t = document.createElement("label");
		t.textContent = e;
		let n = document.createElement("input");
		return n.required = !0, n.setAttribute("aria-label", e), t.append(n), r.append(t), n;
	}, a = i("模型 ID"), o = i("模型显示名称"), s = (e, t) => {
		let n = document.createElement("label");
		n.textContent = e;
		let i = document.createElement("textarea");
		return i.setAttribute("aria-label", e), i.value = JSON.stringify(t, null, 2), n.append(i), r.append(n), i;
	}, c = s("模型能力 JSON", $f), l = s("协议配置 JSON", {}), u = document.createElement("p");
	u.dataset.testid = "canvas-model-profile-feedback";
	let d = document.createElement("button");
	d.type = "submit", d.textContent = "保存模型配置", r.append(u, d), t.append(n, r);
	let f = () => {
		let t = e.providerId();
		if (t === null) {
			u.textContent = "请先选择一个第三方提供方";
			return;
		}
		let n;
		try {
			let e = JSON.parse(c.value), t = JSON.parse(l.value);
			if (typeof e != "object" || !e || Array.isArray(e) || typeof t != "object" || !t || Array.isArray(t)) throw Error();
			n = {
				modelId: a.value.trim(),
				displayName: o.value.trim(),
				capabilities: e,
				config: t
			};
		} catch {
			u.textContent = "模型能力和协议配置必须是 JSON 对象";
			return;
		}
		r.reportValidity() && (d.disabled = !0, e.api.createModelProfile(t, n).then((t) => {
			if (d.disabled = !1, t.ok) {
				r.reset(), c.value = JSON.stringify($f, null, 2), l.value = "{}", u.textContent = "", e.onSaved();
				return;
			}
			if (t.kind === "unauthorized") {
				u.textContent = "请解锁后立即重试", e.onUnauthorized(f);
				return;
			}
			if (t.kind === "unconfigured") {
				u.textContent = t.message, e.onUnconfigured();
				return;
			}
			u.textContent = t.message;
		}).catch(() => {
			d.disabled = !1, u.textContent = "保存请求失败，请重试";
		}));
	};
	return r.addEventListener("submit", (e) => {
		e.preventDefault(), f();
	}), { element: t };
}
//#endregion
//#region frontend/canvas/src/components/provider-editor.ts
function tp(e) {
	let t = document.createElement("section");
	t.className = "canvas-provider-editor", t.dataset.testid = "canvas-provider-editor";
	let n = document.createElement("h3");
	n.textContent = "添加第三方图像提供方";
	let r = document.createElement("form"), i = document.createElement("select");
	i.setAttribute("aria-label", "提供方协议");
	for (let e of If.filter((e) => !e.builtIn)) i.append(Object.assign(document.createElement("option"), {
		value: e.type,
		textContent: e.label
	}));
	let a = (e, t = "text") => {
		let n = document.createElement("label");
		n.textContent = e;
		let i = document.createElement("input");
		return i.type = t, i.required = t !== "password", i.setAttribute("aria-label", e), n.append(i), r.append(n), i;
	}, o = document.createElement("label");
	o.textContent = "提供方协议", o.append(i), r.append(o);
	let s = a("提供方名称"), c = a("服务地址", "url"), l = document.createElement("select");
	l.setAttribute("aria-label", "鉴权方式");
	for (let [e, t] of [
		["bearer", "Bearer"],
		["api_key", "API Key"],
		["none", "无需鉴权"]
	]) l.append(Object.assign(document.createElement("option"), {
		value: e,
		textContent: t
	}));
	let u = document.createElement("label");
	u.textContent = "鉴权方式", u.append(l), r.append(u);
	let d = a("API 密钥", "password");
	d.autocomplete = "off";
	let f = a("密钥说明");
	f.required = !1;
	let p = document.createElement("p");
	p.dataset.testid = "canvas-provider-editor-feedback";
	let m = document.createElement("button");
	m.type = "submit", m.textContent = "安全保存提供方";
	let h = document.createElement("button");
	h.type = "button", h.textContent = "取消", r.append(p, m, h), t.append(n, r);
	let g = () => {
		r.reset(), d.value = "", p.textContent = "";
	}, _ = () => {
		let t = l.value;
		if (!r.reportValidity()) return;
		if (t !== "none" && d.value === "") {
			p.textContent = "请填写仅用于本次保存的 API 密钥";
			return;
		}
		m.disabled = !0;
		let n = {
			adapterType: i.value,
			name: s.value.trim(),
			baseUrl: c.value.trim(),
			authType: t,
			...t === "none" ? {} : { credential: { apiKey: d.value } },
			...f.value.trim() === "" ? {} : { credentialHint: f.value.trim() }
		};
		e.api.createProvider(n).then((t) => {
			if (m.disabled = !1, t.ok) {
				g(), e.onSaved();
				return;
			}
			if (t.kind === "unauthorized") {
				p.textContent = "请解锁后立即重试；密钥只保留在当前表单内存中", e.onUnauthorized(_);
				return;
			}
			if (t.kind === "unconfigured") {
				p.textContent = t.message, e.onUnconfigured();
				return;
			}
			p.textContent = t.message, t.kind === "validation" && (d.value = "");
		}).catch(() => {
			m.disabled = !1, p.textContent = "保存请求失败，请重试";
		});
	};
	return r.addEventListener("submit", (e) => {
		e.preventDefault(), _();
	}), h.addEventListener("click", g), l.addEventListener("change", () => {
		d.disabled = l.value === "none", d.required = l.value !== "none", d.disabled && (d.value = "");
	}), {
		element: t,
		clear: g
	};
}
//#endregion
//#region frontend/canvas/src/components/model-manager.ts
function np(e) {
	let t = document.createElement("section");
	t.className = "canvas-model-manager", t.dataset.testid = "canvas-model-manager";
	let n = document.createElement("h2");
	n.textContent = "第三方模型管理";
	let r = document.createElement("p");
	r.textContent = "密钥仅写入受保护接口，不会从目录返回或显示。ComfyUI 与本地权重不在此版本支持范围内。";
	let i = document.createElement("p");
	i.dataset.testid = "canvas-model-manager-feedback";
	let a = document.createElement("div"), o = document.createElement("select");
	o.setAttribute("aria-label", "模型所属提供方");
	let s = document.createElement("div"), c = [], l = [], u = () => {
		Promise.all([e.managementApi.loadProviders(), e.catalogApi.loadCatalog()]).then(([t, n]) => {
			if (!t.ok) {
				i.textContent = t.message;
				return;
			}
			if (!n.ok) {
				i.textContent = n.message;
				return;
			}
			c = t.value, l = n.value, o.replaceChildren(Object.assign(document.createElement("option"), {
				value: "",
				textContent: "选择提供方以添加模型"
			}), ...c.map((e) => Object.assign(document.createElement("option"), {
				value: e.id,
				textContent: e.name
			}))), a.replaceChildren(...c.map((t) => {
				let n = document.createElement("p"), r = l.filter((e) => e.providerId === t.id).length;
				n.textContent = `${t.name}：${r} 个模型`;
				let a = document.createElement("button");
				return a.type = "button", a.textContent = "检测连接", a.addEventListener("click", () => {
					window.confirm("本次检测将发送 1 次可能计费的提供方请求；具体费用由供应商计费规则决定。是否继续？") && e.managementApi.probeProvider(t.id, !0).then((t) => {
						if (t.ok) {
							i.textContent = t.value.status === "configuration_ready" ? "连接配置已就绪" : "连接当前不可用";
							return;
						}
						if (t.kind === "unauthorized") {
							e.onUnauthorized(() => a.click());
							return;
						}
						t.kind === "unconfigured" && e.onUnconfigured(), i.textContent = t.message;
					});
				}), n.append(" ", a), n;
			})), s.replaceChildren(...l.map((e) => Object.assign(document.createElement("p"), { textContent: `${e.displayName} · ${e.availability === "available" && e.enabled ? "可用" : e.availabilityReason ?? "不可用"}` }))), e.onCatalog(l);
		}).catch(() => {
			i.textContent = "模型目录加载失败";
		});
	}, d = tp({
		api: e.managementApi,
		onSaved: u,
		onUnauthorized: e.onUnauthorized,
		onUnconfigured: e.onUnconfigured
	}), f = ep({
		api: e.managementApi,
		providerId: () => o.value || null,
		onSaved: u,
		onUnauthorized: e.onUnauthorized,
		onUnconfigured: e.onUnconfigured
	});
	return t.append(n, r, d.element, o, f.element, i, a, s), u(), {
		element: t,
		refresh: u,
		clearSensitive: d.clear
	};
}
//#endregion
//#region frontend/canvas/src/components/export-panel.ts
var rp = [
	["single", "单张图片"],
	["category_zip", "分类 ZIP"],
	["detail_slices_zip", "详情切片 ZIP"],
	["detail_long", "详情长图"]
], ip = [
	["png", "PNG"],
	["jpeg", "JPEG"],
	["webp", "WebP"]
], ap = {
	main: "主图",
	sku: "SKU 图",
	detail: "详情页"
};
function op() {
	return typeof crypto.randomUUID == "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function sp(e) {
	let t = document.createElement("section");
	t.className = "canvas-export-panel", t.dataset.testid = "canvas-export-panel";
	let n = [], r = null, i = null, a = "#ffffff", o = !1, s = null, c = "", l = 0, u = null, d = !1, f = () => {
		let t = e.getVersions();
		return e.getProject().semanticState.outputBoards.slice().sort((e, t) => e.sortOrder - t.sortOrder || e.id.localeCompare(t.id)).flatMap((e) => {
			if (e.selectedResultAssetId === null) return [];
			let n = t.find((t) => t.boardId === e.id && t.composedAssetId === e.selectedResultAssetId);
			return n === void 0 ? [] : [{
				board: e,
				version: n
			}];
		});
	}, p = (e) => {
		if (n.length === 0) return "请选择至少一个已保存结果";
		if (r === null) return "请选择导出方式";
		if (i === null) return "请选择图片格式";
		if (r === "single" && n.length !== 1) return "单张图片只能选择一个画板";
		let t = n.map((t) => e.find((e) => e.board.id === t));
		return t.some((e) => e === void 0) ? "所选结果已变化，请重新选择" : (r === "detail_slices_zip" || r === "detail_long") && t.some((e) => e?.board.outputType !== "detail") ? "详情导出只能选择详情页画板" : null;
	}, m = (e) => {
		switch (e.status) {
			case "queued": return "导出任务已进入队列";
			case "running": return "正在生成导出文件…";
			case "succeeded": return "导出完成";
			case "cancel_requested": return "正在取消导出任务…";
			case "cancelled": return "导出任务已取消";
			case "failed":
			case "interrupted": return e.safeError?.message ?? "导出失败，请重试";
		}
	}, h = () => {
		if (d) return;
		let l = f(), u = new Set(l.map((e) => e.board.id));
		n = n.filter((e) => u.has(e));
		let m = Object.assign(document.createElement("h3"), { textContent: "导出产品图" }), _ = Object.assign(document.createElement("p"), {
			className: "canvas-export-description",
			textContent: "选择已保存的结果、导出方式和格式。所有选项均由你决定。"
		}), v = document.createElement("div");
		v.className = "canvas-export-boards", l.length === 0 && v.append(Object.assign(document.createElement("p"), { textContent: "请先在结果版本中保存至少一个画板结果。" }));
		for (let { board: t, version: r } of l) {
			let i = document.createElement("div");
			i.className = "canvas-export-board-row";
			let a = document.createElement("label"), s = document.createElement("input");
			s.type = "checkbox", s.checked = n.includes(t.id), s.disabled = o || !e.isEditable(), s.dataset.boardId = t.id, s.addEventListener("change", () => {
				s.checked ? n.includes(t.id) || n.push(t.id) : n = n.filter((e) => e !== t.id), c = "", h();
			});
			let l = t.outputType === "sku" && t.skuId !== null ? `${ap[t.outputType]} · ${t.skuId}` : ap[t.outputType], u = document.createElement("span");
			if (u.innerHTML = "<strong></strong><small></small>", u.querySelector("strong").textContent = l, u.querySelector("small").textContent = `${r.modelDisplayName} · ${r.width}×${r.height}`, a.append(s, u), i.append(a), s.checked) {
				let e = n.indexOf(t.id), r = Object.assign(document.createElement("button"), {
					type: "button",
					textContent: "上移",
					disabled: o || e === 0
				});
				r.setAttribute("aria-label", `上移${l}`), r.addEventListener("click", () => {
					[n[e - 1], n[e]] = [n[e], n[e - 1]], h();
				});
				let a = Object.assign(document.createElement("button"), {
					type: "button",
					textContent: "下移",
					disabled: o || e === n.length - 1
				});
				a.setAttribute("aria-label", `下移${l}`), a.addEventListener("click", () => {
					[n[e], n[e + 1]] = [n[e + 1], n[e]], h();
				}), i.append(r, a);
			}
			v.append(i);
		}
		let y = document.createElement("fieldset");
		y.className = "canvas-export-choice-group", y.append(Object.assign(document.createElement("legend"), { textContent: "导出方式" }));
		for (let [t, n] of rp) {
			let i = Object.assign(document.createElement("button"), {
				type: "button",
				textContent: n,
				disabled: o || !e.isEditable()
			});
			i.dataset.exportMode = t, i.setAttribute("aria-pressed", String(r === t)), i.addEventListener("click", () => {
				r = t, c = "", h();
			}), y.append(i);
		}
		let b = document.createElement("fieldset");
		b.className = "canvas-export-choice-group", b.append(Object.assign(document.createElement("legend"), { textContent: "图片格式" }));
		for (let [t, n] of ip) {
			let r = Object.assign(document.createElement("button"), {
				type: "button",
				textContent: n,
				disabled: o || !e.isEditable()
			});
			r.dataset.exportFormat = t, r.setAttribute("aria-pressed", String(i === t)), r.addEventListener("click", () => {
				i = t, c = "", h();
			}), b.append(r);
		}
		let x = [
			m,
			_,
			v,
			y,
			b
		];
		if (i === "jpeg") {
			let e = document.createElement("label");
			e.className = "canvas-export-jpeg-background", e.textContent = "JPEG 透明区域背景";
			let t = document.createElement("input");
			t.type = "color", t.value = a, t.disabled = o, t.addEventListener("input", () => {
				a = t.value;
			}), e.append(t), x.push(e);
		}
		let S = p(l), C = Object.assign(document.createElement("button"), {
			type: "button",
			className: "canvas-export-submit",
			textContent: o ? "正在提交…" : "开始导出",
			disabled: o || !e.isEditable() || S !== null
		});
		C.dataset.testid = "canvas-export-submit", C.addEventListener("click", () => {
			g();
		});
		let w = document.createElement("p");
		if (w.className = "canvas-export-feedback", w.dataset.tone = s?.status === "succeeded" ? "success" : s !== null && [
			"failed",
			"interrupted",
			"cancelled"
		].includes(s.status) ? "error" : o || s !== null ? "working" : "idle", w.textContent = c || S || "", x.push(C, w), s?.status === "succeeded" && s.outputAssetId !== null && s.outputAssetId !== void 0) {
			let t = Object.assign(document.createElement("a"), {
				className: "canvas-export-download",
				textContent: "下载导出文件",
				href: e.api.downloadUrl(s.outputAssetId)
			});
			t.dataset.testid = "canvas-export-download", x.push(t);
		}
		t.replaceChildren(...x);
	}, g = async () => {
		let t = e.getProjectId(), _ = f(), v = p(_);
		if (o || t === null || v !== null || r === null || i === null) {
			c = v ?? "当前没有可导出的项目", h();
			return;
		}
		let y = ++l;
		o = !0, c = "正在保存项目…", h();
		let b = await e.flushSave();
		if (d || y !== l || e.getProjectId() !== t) return;
		if (!b.ok) {
			o = !1, c = b.kind === "conflict" ? "项目版本有冲突，请刷新后重试" : b.message, h();
			return;
		}
		let x = f(), S = p(x);
		if (S !== null) {
			o = !1, c = S, h();
			return;
		}
		let C = n.map((e, t) => {
			let n = x.find((t) => t.board.id === e);
			return {
				boardId: e,
				versionId: n.version.versionId,
				composedAssetId: n.version.composedAssetId,
				order: t
			};
		}), w = {
			projectRevision: e.getRevision(),
			mode: r,
			format: i,
			selectedBoards: C,
			jpegBackground: i === "jpeg" ? a : null
		}, T = new AbortController();
		u?.abort(), u = T, c = "正在提交导出任务…", h();
		let E = await e.api.create(t, w, `export:${op()}`, T.signal);
		if (!(d || y !== l || u !== T || e.getProjectId() !== t)) {
			if (u = null, o = !1, !E.ok) {
				c = E.message, h(), E.kind === "unauthorized" && e.onUnauthorized(() => {
					g();
				});
				return;
			}
			s = E.value, c = m(E.value), e.onOperation?.(E.value), h();
		}
	}, _ = {
		element: t,
		update: h,
		applyOperation: (t) => {
			t.operationType !== "export" || t.projectId !== e.getProjectId() || s !== null && t.id !== s.id || (s = t, c = m(t), o = !1, h());
		},
		reset: () => {
			l += 1, u?.abort(), u = null, n = [], r = null, i = null, o = !1, s = null, c = "", h();
		},
		dispose: () => {
			d || (d = !0, l += 1, u?.abort(), u = null, t.replaceChildren());
		}
	};
	return h(), _;
}
//#endregion
//#region frontend/canvas/src/controllers/generation-controller.ts
var cp = "canvas:generation-pending:v1";
function lp(e) {
	if (e === null) return /* @__PURE__ */ new Map();
	try {
		let t = e.getItem(cp);
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
function up(e, t) {
	if (e !== null) try {
		t.size === 0 ? e.removeItem(cp) : e.setItem(cp, JSON.stringify([...t.values()]));
	} catch {}
}
function dp(e) {
	if (e === null || typeof e == "boolean" || typeof e == "string" || typeof e == "number") return JSON.stringify(e);
	if (Array.isArray(e)) return `[${e.map(dp).join(",")}]`;
	if (typeof e != "object") throw Error("generation request must be JSON");
	let t = e;
	return `{${Object.keys(t).sort().map((e) => `${JSON.stringify(e)}:${dp(t[e])}`).join(",")}}`;
}
function fp() {
	return typeof crypto < "u" && typeof crypto.randomUUID == "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function pp(e) {
	return {
		ok: !1,
		kind: "save_failed",
		message: e.kind === "conflict" ? "项目版本冲突，请刷新后重试" : e.message
	};
}
function mp({ store: e, autosave: t, api: n, catalog: r = () => [], build: i = Pf, randomId: a = fp, now: o = () => /* @__PURE__ */ new Date(), storage: s = typeof sessionStorage > "u" ? null : sessionStorage, pendingTtlMs: c = 1800 * 1e3 }) {
	let l = lp(s), u = null;
	return {
		submit: () => {
			if (u !== null) return u;
			let d = (async () => {
				let u = await t.flush();
				if (!u.ok) return pp(u);
				let d = e.getState(), f = i(d.project, r(), d.runtime.revision);
				if (!f.ok) return {
					ok: !1,
					kind: "validation",
					message: f.reasons[0]?.message ?? "生成配置无效"
				};
				let p = dp(f.request), m = l.get(d.runtime.projectId), h = m === void 0 ? NaN : Date.parse(m.createdAt);
				m !== void 0 && m.fingerprint === p && Number.isFinite(h) && o().getTime() - h <= c || (l.set(d.runtime.projectId, {
					projectId: d.runtime.projectId,
					fingerprint: p,
					idempotencyKey: `canvas:${a()}`,
					createdAt: o().toISOString()
				}), up(s, l));
				let g = l.get(d.runtime.projectId);
				if (g === void 0) throw Error("generation pending submission is unavailable");
				let _ = await n.create(d.runtime.projectId, f.request, g.idempotencyKey);
				return _.ok ? (l.delete(d.runtime.projectId), up(s, l), {
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
			l.delete(e.getState().runtime.projectId), up(s, l);
		}
	};
}
//#endregion
//#region frontend/canvas/src/components/workspace.ts
function hp(e) {
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
function gp(e) {
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
function _p(e, t) {
	let n = e.attemptCount ?? -1, r = t.attemptCount ?? -1;
	return n === r ? gp(e.status) >= gp(t.status) ? e : t : n > r ? e : t;
}
function vp(e) {
	if (e === void 0) return null;
	let t = e;
	return typeof t.loadProviders == "function" && typeof t.createProvider == "function" && typeof t.createModelProfile == "function" && typeof t.probeProvider == "function" ? t : null;
}
function yp({ root: e, controller: t, store: n, adapter: r, assetsApi: i, compositionsApi: a, skusApi: o, providersApi: s, generationsApi: c, exportsApi: l, subscribeEvents: u }) {
	let d = !1, f = 0, p = !1, m = !1, h = document.createElement("main");
	h.className = "canvas-workspace", h.dataset.testid = "canvas-workspace";
	let g = tf(t), _ = document.createElement("section");
	_.className = "canvas-workspace-center";
	let v = document.createElement("div");
	v.className = "canvas-stage", v.dataset.testid = "canvas-stage";
	let y = document.createElement("canvas");
	y.width = 1600, y.height = 1e3, y.dataset.testid = "canvas-surface", y.dataset.canvasSurface = "product-canvas", v.append(y);
	let b = document.createElement("aside");
	b.className = "canvas-properties", b.dataset.testid = "canvas-properties", b.setAttribute("aria-label", "属性设置");
	let C = document.createElement("div");
	C.className = "canvas-properties-controls";
	let w = () => n.getState().project, T = (e) => {
		let t = w();
		r.project(e, t), e.semanticState.mode !== t.semanticState.mode && r.setMode(t.semanticState.mode);
	}, E = (e) => {
		if (!p) return;
		let t = w(), r = m;
		m ||= hp(e);
		let i;
		try {
			i = n.dispatch(e), i.confirmation !== void 0 && window.confirm("此操作会解除已有结果关联，是否继续？") && (i = n.dispatch({
				...e,
				acceptedDiffId: i.confirmation.token
			}));
		} finally {
			m = r;
		}
		i.applied && T(t);
	}, ee = () => {
		if (!p) return;
		let e = w();
		n.undo() && T(e);
	}, D = () => {
		if (!p) return;
		let e = w();
		n.redo() && T(e);
	}, O = null, te = vf(n, E, ee, D, l === void 0 ? void 0 : () => {
		O?.element.scrollIntoView({
			block: "start",
			behavior: "smooth"
		});
	}), ne = null, re = document.createElement("label");
	re.className = "canvas-composition-group-field", re.textContent = "活动构图组";
	let ie = document.createElement("select");
	ie.dataset.testid = "canvas-composition-group-select";
	let k = document.createElement("button");
	k.type = "button", k.dataset.testid = "canvas-composition-group-create", k.textContent = "新建构图组", ie.setAttribute("aria-label", "选择构图组"), re.append(ie, k);
	let A = ff({ onUpdate: (e, t) => {
		E({
			type: "composition/update",
			groupId: e,
			layout: t
		});
	} }), j = null, M = Jf(), ae = mf({
		onSelect: (e) => {
			j = e, Ye();
		},
		onUpdate: (e, t) => {
			E({
				type: "text/update",
				layerId: e,
				patch: t
			});
		}
	}), N = _f(() => {
		t.retrySave();
	}, () => {
		t.retryRemoteSync();
	}), P = null, F = null, I = [], L = [], oe = /* @__PURE__ */ new Map(), se = [], R = null, ce = t.getState(), le = null, ue = null, de = null, fe = null, pe = !1, me = 0, he = null, ge = null, _e = null, ve = null, ye = [], be = Qf(), xe = [], Se = Kf(), Ce = qf(), we = c === void 0 ? null : mp({
		store: n,
		autosave: { flush: () => t.flushSave() },
		api: c,
		catalog: () => xe
	}), Te = async () => {
		if (we === null || c === void 0) {
			Se.update("生成服务尚未配置", "error");
			return;
		}
		let e = async () => {
			Se.update("正在保存并提交生成…", "working");
			let e = await we.submit();
			Se.update(e.ok ? `已创建生成任务 ${e.generationId}` : e.message, e.ok ? "success" : "error");
		}, t = await c.accessStatus();
		if (!t.ok) {
			Se.update(t.message, "error");
			return;
		}
		if (t.value.configured && t.value.locked) {
			Ce.open(async (t) => {
				let n = await c.unlock(t);
				return n.ok ? (e(), null) : n.message;
			});
			return;
		}
		await e();
	}, Ee = Gf({
		getProject: w,
		getRevision: () => n.getState().runtime.revision,
		getModels: () => xe,
		getSkus: () => se,
		getReferenceAssets: () => I.filter((e) => e.assetType === "working" || e.assetType === "cutout").map((e) => ({
			id: e.id,
			label: e.originalFilename || e.id
		})),
		isEditable: () => p,
		dispatch: E,
		onGenerate: () => {
			Te();
		}
	}), De = (e) => {
		if (c === void 0) {
			Se.update("付费访问服务尚未配置", "error");
			return;
		}
		Ce.open(async (t) => {
			let n = await c.unlock(t);
			return n.ok ? (e(), null) : n.message;
		});
	};
	l !== void 0 && (O = sp({
		api: l,
		getProject: w,
		getProjectId: () => P,
		getRevision: () => n.getState().runtime.revision,
		getVersions: () => ye,
		isEditable: () => p,
		flushSave: () => t.flushSave(),
		onUnauthorized: De,
		onOperation: (e) => {
			L = [...L.filter((t) => t.id !== e.id), e], oe.set(e.id, e);
		}
	}));
	let Oe = vp(s), ke = null;
	s !== void 0 && Oe !== null && (ke = np({
		catalogApi: s,
		managementApi: Oe,
		onUnauthorized: De,
		onUnconfigured: () => Se.update("服务器未配置 Canvas 访问令牌，第三方模型管理已关闭", "error"),
		onCatalog: (e) => {
			xe = e, Ee.update(), Ve();
		}
	}));
	let Ae = document.createElement("section");
	Ae.className = "canvas-compose-controls", Ae.dataset.testid = "canvas-compose-controls";
	let je = document.createElement("select");
	je.dataset.testid = "canvas-compose-board";
	let Me = document.createElement("select");
	Me.dataset.testid = "canvas-compose-background";
	let Ne = document.createElement("button");
	Ne.type = "button", Ne.dataset.testid = "canvas-compose-submit", Ne.textContent = "合成产品图";
	let Pe = document.createElement("p");
	Pe.dataset.testid = "canvas-compose-feedback";
	let Fe = (e) => e.status === "succeeded" ? "合成完成" : e.status === "failed" ? "合成失败，可从任务状态重试" : e.status === "queued" ? "合成任务已进入队列" : "合成处理中", Ie = () => {
		let e = w().semanticState.outputBoards, t = I.filter((e) => e.assetType === "generated_background" || e.assetType === "working");
		e.some((e) => e.id === ge) || (ge = e[0]?.id ?? null), t.some((e) => e.id === _e) || (_e = t[0]?.id ?? null), je.replaceChildren(...e.map((e) => Object.assign(document.createElement("option"), {
			value: e.id,
			textContent: `${e.outputType} · ${e.id}`
		}))), je.value = ge ?? "", Me.replaceChildren(...t.map((e) => Object.assign(document.createElement("option"), {
			value: e.id,
			textContent: e.originalFilename || e.id
		}))), Me.value = _e ?? "";
		let n = !p || pe || a === void 0 || ge === null || _e === null;
		je.disabled = n, Me.disabled = n, Ne.disabled = n;
		let r = [
			Object.assign(document.createElement("h3"), { textContent: "权威合成" }),
			je,
			Me,
			Ne,
			Pe
		];
		if (ve?.status === "succeeded" && ve.outputAssetId != null && i !== void 0) {
			let e = document.createElement("img");
			e.className = "canvas-compose-preview", e.dataset.testid = "canvas-compose-preview", e.alt = "合成结果预览", e.src = i.previewUrl(ve.outputAssetId), r.push(e);
		}
		Ae.replaceChildren(...r);
	};
	je.addEventListener("change", () => {
		ge = je.value || null;
	}), Me.addEventListener("change", () => {
		_e = Me.value || null;
	}), Ne.addEventListener("click", () => {
		if (pe || a === void 0 || P === null || ge === null || _e === null) return;
		let e = P, r = ++me, i = ge, o = _e;
		pe = !0, Pe.textContent = "正在保存并提交合成…", Ie(), (async () => {
			let s = await t.flushSave();
			if (!s.ok || d || r !== me || P !== e) {
				Pe.textContent = s.ok ? "项目已切换，未提交合成" : "请先解决保存问题", pe = !1, Ie();
				return;
			}
			let c = new AbortController();
			fe?.abort(), fe = c, he = null, ve = null;
			let l = typeof crypto.randomUUID == "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`, u = await a.enqueueCompose({
				projectId: e,
				revision: n.getState().runtime.revision,
				boardId: i,
				backgroundAssetId: o,
				clientRequestId: `compose:${l}`,
				signal: c.signal
			});
			if (d || r !== me || P !== e || fe !== c) return;
			if (fe = null, pe = !1, !u.ok) {
				Pe.textContent = u.kind === "conflict" ? `项目版本已更新到 ${u.currentRevision}，请刷新后重试` : u.message, Ie();
				return;
			}
			he = u.value.id;
			let f = oe.get(u.value.id);
			ve = f === void 0 ? u.value : _p(u.value, f), Pe.textContent = Fe(ve), Ie();
		})().catch(() => {
			!d && r === me && P === e && (fe = null, pe = !1, Pe.textContent = "合成请求失败，请重试", Ie());
		});
	});
	let Le = () => {
		N.update(ce.save, ce.remoteSync, F?.asset.cutoutStatus ?? null);
	}, Re = () => {
		if (de === null || P === null) {
			de?.update(null);
			return;
		}
		let e = w().layoutState.productLayers.find((e) => e.skuId === null && e.locked);
		de.update({
			projectId: P,
			revision: n.getState().runtime.revision,
			skus: se,
			mainProductAssetId: e?.renderAssetId ?? null,
			referenceAssets: I.filter((e) => e.assetType === "working").map((e) => ({
				id: e.id,
				label: e.originalFilename || e.id
			})),
			disabled: !p
		});
	}, ze = (e) => {
		let t = w();
		if (JSON.stringify(t) !== JSON.stringify(e.project)) {
			let i = n.getState().runtime;
			n.replaceProject(e.project, {
				projectId: i.projectId,
				revision: i.revision
			}), r.project(t, e.project), t.semanticState.mode !== e.project.semanticState.mode && r.setMode(e.project.semanticState.mode);
		}
		F = {
			project: w(),
			asset: structuredClone(e.asset)
		}, ue?.update(F.asset), Re(), Le();
	}, Be = (e) => {
		if (F === null || w().layoutState.productLayers.find((e) => e.skuId === null && e.locked)?.sourceAssetId !== F.asset.workingAssetId) return;
		let t = {
			project: w(),
			asset: F.asset
		}, n = Zd(t, e);
		n !== t && ze(n);
	};
	i !== void 0 && (le = sf({
		api: i,
		onUploaded: (e) => {
			if (P === null || e.source.projectId !== P) return;
			let t = /* @__PURE__ */ new Set([
				e.source.id,
				e.working.id,
				e.preview.id
			]);
			if (I = [
				...I.filter((e) => !t.has(e.id)),
				e.source,
				e.working,
				e.preview
			], e.operation !== null && (L.some((t) => t.id === e.operation?.id) || (L = [...L, e.operation])), ze(Yd(w(), e)), e.operation !== null) {
				let t = L.find((t) => t.id === e.operation?.id) ?? e.operation, n = oe.get(e.operation.id);
				Be(n === void 0 ? t : _p(t, n));
			}
		}
	}), ue = af({
		api: i,
		onOperation: (e) => {
			L = [...L.filter((t) => t.id !== e.id), e], oe.set(e.id, e), Be(e);
		},
		onFallback: () => {
			F !== null && (E({
				type: "asset/useRectangularSource",
				workingAssetId: F.asset.workingAssetId
			}), F = {
				project: w(),
				asset: {
					...F.asset,
					renderAssetId: F.asset.workingAssetId,
					allowOpaqueFallback: !0
				}
			}, ue?.update(F.asset), Le());
		}
	})), o !== void 0 && (de = cf({
		api: o,
		onSnapshot: (e) => {
			e.project.id === P && (se = e.skus, t.adoptMutationSnapshot(e), Re());
		}
	})), b.append(C, Se.element, Ce.element, re, A.element, ae.element, be.element, ...O === null ? [] : [O.element], Ae), le !== null && ue !== null && b.append(le.element, ue.element), de !== null && b.append(de.element), ke !== null && b.append(ke.element), _.append(te.element, v, N.element), h.append(g.element, _, b), e.replaceChildren(h), s !== void 0 && s.loadCatalog().then((e) => {
		if (!d) {
			if (!e.ok) {
				Se.update(e.message, "error");
				return;
			}
			xe = e.value, Ee.update(), Ve();
		}
	}).catch(() => {
		d || Se.update("模型目录加载失败", "error");
	});
	let Ve = () => {
		let e = w(), t = document.createElement("h2");
		t.textContent = "属性设置";
		let r = document.createElement("p");
		if (r.textContent = e.semanticState.mode === "complete-set" ? "选择套图输出并设置数量与提示词。" : "高级模式保留同一画布与项目状态。", C.replaceChildren(t, r), e.semanticState.mode === "advanced") {
			let t = Zf({
				disabled: !p,
				nextId: (t) => {
					let n;
					do
						f += 1, n = `advanced:${t}:${f}`;
					while (e.semanticState.nodes.some((e) => e.id === n));
					return n;
				},
				onAdd: (e) => {
					E({
						type: "node/add",
						node: e
					}), E({
						type: "node/move",
						nodeId: e.id,
						position: {
							x: 120 + f * 24,
							y: 120
						}
					});
				}
			});
			M.update(e.semanticState.nodes, xe, !p, (e, t) => {
				E({
					type: "node/update",
					nodeId: e,
					patch: t
				});
			}, (t, n) => {
				let r = e.semanticState.nodes.find((e) => e.id === t), i = e.semanticState.nodes.find((e) => e.id === n);
				if (r === void 0 || i === void 0) return;
				let a = x(r.kind, i.kind)[0];
				if (a === void 0) return;
				let o = 1, s = `advanced:edge:${t}:${n}:${a}:${o}`;
				for (; e.semanticState.edges.some((e) => e.id === s);) o += 1, s = `advanced:edge:${t}:${n}:${a}:${o}`;
				E({
					type: "edge/connect",
					edge: S(s, a, t, n)
				});
			});
			let r = Ff(e, xe, n.getState().runtime.revision), i = document.createElement("button");
			if (i.type = "button", i.dataset.testid = "canvas-generate-advanced", i.textContent = r.ok ? "生成高级画布" : r.reasons.map((e) => e.message).join("；"), i.disabled = !p || !r.ok, i.addEventListener("click", () => {
				Te();
			}), C.append(t, M.element, i), e.semanticState.outputBoards.length === 0) {
				let e = document.createElement("button");
				e.type = "button", e.textContent = "返回套图模式选择输出", e.disabled = !p, e.addEventListener("click", () => E({
					type: "mode/set",
					mode: "complete-set"
				})), C.append(Object.assign(document.createElement("p"), { textContent: "高级图谱需要至少一个输出画板。请先在套图模式选择主图、SKU 图或详情图；已有节点不会丢失。" }), e);
			}
			return;
		}
		Ee.update(), C.append(Ee.element);
	}, He = () => {
		let e = w().semanticState.outputBoards, t = e.find((e) => e.id === ge) ?? e[0] ?? null;
		be.update(t, ye, !p, (e) => {
			if (t !== null) {
				E({
					type: "board/selectResult",
					boardId: t.id,
					assetId: e
				});
				let n = e === null ? null : ye.find((n) => n.boardId === t.id && n.composedAssetId === e) ?? null;
				r.setResultBackgroundPreview?.(n?.backgroundPreviewAssetId ?? null);
			}
		});
		let n = t?.selectedResultAssetId === null || t === null ? null : ye.find((e) => e.boardId === t.id && e.composedAssetId === t.selectedResultAssetId) ?? null;
		r.setResultBackgroundPreview?.(n?.backgroundPreviewAssetId ?? null), O?.update();
	}, Ue = async (e) => {
		if (c === void 0) return;
		let t = await xt(c, e);
		if (d || P !== e || !t.ok) return;
		ye = t.value;
		let r = /* @__PURE__ */ new Map();
		for (let e of ye) {
			let t = r.get(e.boardId) ?? [];
			t.push(e.composedAssetId), r.set(e.boardId, t);
		}
		for (let e of w().semanticState.outputBoards) n.dispatch({
			type: "runtime/setAllowedResultAssets",
			boardId: e.id,
			assetIds: r.get(e.id) ?? []
		});
		He();
	}, We = async (e) => {
		if (i === void 0) return;
		R?.abort();
		let t = new AbortController();
		R = t;
		let n, r;
		try {
			[n, r] = await Promise.all([i.listAssets(e, t.signal), i.listOperations(e, t.signal)]);
		} catch {
			R === t && (R = null);
			return;
		}
		if (d || t.signal.aborted || R !== t || P !== e || (R = null, !n.ok || !r.ok)) return;
		I = n.value, L = r.value;
		let a = L.find((e) => e.operationType === "export");
		a !== void 0 && O?.applyOperation(a), Ie(), He();
		let o = Qd(w(), I, L);
		if (o === null) {
			F = null, ue?.update(null), Re(), Le();
			return;
		}
		ze(o);
		let s = oe.get(o.asset.operationId ?? ""), c = L.find((e) => e.id === o.asset.operationId);
		s !== void 0 && Be(c === void 0 ? s : _p(c, s));
	}, Ge = (e) => {
		let t = e.safeErrorSummary ?? e.safeStorageBlockReason, n = /* @__PURE__ */ new Set([
			"failed",
			"partially_failed",
			"cancelled",
			"unknown"
		]);
		Se.update(t ?? `生成 ${e.id}：${e.status}（成功 ${e.succeededItems}/${e.totalItems}）`, t === null ? e.status === "succeeded" ? "success" : n.has(e.status) ? "error" : "working" : "error"), e.succeededItems > 0 && P !== null && Ue(P);
	}, Ke = u?.((e) => {
		if (!(d || P === null)) {
			if (e.type === "snapshot") {
				if (e.snapshot.project.id !== P) return;
				se = e.snapshot.skus, L = e.operations, oe.clear(), ye = [];
				let t = L.find((e) => e.operationType === "export");
				t !== void 0 && O?.applyOperation(t);
				let n = e.generations?.[0];
				n !== void 0 && Ge(n), Re(), We(P);
				return;
			}
			if (e.projectId === P) {
				if ("generation" in e) {
					Ge(e.generation);
					return;
				}
				if (e.type === "asset.uploaded" || e.type === "asset.deleted") {
					We(P);
					return;
				}
				if ("operation" in e) {
					if (oe.set(e.operation.id, e.operation), e.operation.operationType === "export") {
						O?.applyOperation(e.operation);
						return;
					}
					if (e.operation.operationType === "compose") {
						if (e.operation.id !== he) return;
						ve = ve === null ? e.operation : _p(ve, e.operation), Pe.textContent = Fe(ve), Ie();
						return;
					}
					Be(e.operation);
				}
			}
		}
	}) ?? (() => {});
	r.mount(y, E);
	let qe = w();
	r.project(null, qe), r.setMode(qe.semanticState.mode);
	let Je = () => {
		let e = w().semanticState.compositionGroups, t = e.find((e) => e.id === ne) ?? e[0];
		ne = t?.id ?? null, ie.replaceChildren(...e.length === 0 ? [Object.assign(document.createElement("option"), {
			value: "",
			textContent: "暂无构图组"
		})] : e.map((e, t) => Object.assign(document.createElement("option"), {
			value: e.id,
			textContent: `构图组 ${t + 1} · ${e.id}`
		}))), ie.value = ne ?? "", ie.disabled = !p || e.length === 0, k.disabled = !p || !w().layoutState.productLayers.some((e) => e.skuId === null && e.locked && e.compositionGroupId === null), A.update(t === void 0 ? null : {
			groupId: t.id,
			layout: t.layout,
			disabled: !p
		});
	};
	function Ye() {
		let e = w().layoutState.textSnapshots;
		e.some((e) => e.id === j) || (j = e[0]?.id ?? null), ae.update({
			layers: e,
			selectedLayerId: j,
			disabled: !p
		});
	}
	ie.addEventListener("change", () => {
		if (!p) return;
		let e = ie.value;
		w().semanticState.compositionGroups.some((t) => t.id === e) && (ne = e, Je(), Ye(), Ie(), O?.update());
	}), k.addEventListener("click", () => {
		if (!p) return;
		let e = w().semanticState.compositionGroups.length, t = w().layoutState.productLayers.find((e) => e.skuId === null && e.locked);
		if (t === void 0) return;
		E({
			type: "composition/create",
			skuProducts: se.map((e) => {
				let n = e.referenceAssetId === null, r = e.referenceAssetId ?? t.sourceAssetId;
				return {
					skuId: e.id,
					sourceAssetId: r,
					renderAssetId: n ? t.renderAssetId : r,
					allowOpaqueFallback: n ? t.allowOpaqueFallback : !1
				};
			})
		});
		let n = w().semanticState.compositionGroups[e];
		n !== void 0 && (ne = n.id, Je());
	});
	let Xe = () => {
		te.update(), m || Ve(), Je(), Ye(), Ie();
	};
	Xe();
	let Ze = n.subscribe(Xe), Qe = (e) => {
		let n = P !== e.activeProjectId;
		ce = e, p = e.activeProjectId !== null, P = e.activeProjectId, n && (ke?.clearSensitive(), me += 1, pe = !1, he = null, ne = null, j = null, ge = null, _e = null, ve = null, O?.reset()), g.update(e), te.setEditable(p), h.dataset.editable = String(p), v.inert = !p, b.inert = !p, v.setAttribute("aria-disabled", String(!p)), b.setAttribute("aria-disabled", String(!p)), Je(), h.dataset.activeProjectId = e.activeProjectId ?? "", le?.setDisabled(!p), le?.setProject(P), ue?.setDisabled(!p);
		let r = t.getActiveSnapshot?.call(t) ?? null;
		r !== null && r.project.id === P && (se = r.skus);
		let i = w().layoutState.productLayers.find((e) => e.skuId === null && e.locked), a = F !== null && i?.sourceAssetId !== F.asset.workingAssetId;
		(n || a) && (R?.abort(), R = null, fe?.abort(), fe = null, F = null, I = [], L = [], oe.clear(), ue?.update(null), P !== null && (We(P), Ue(P))), Re(), Le(), Ye(), Ie(), He();
	};
	Qe(t.getState());
	let $e = t.subscribe(Qe);
	return { dispose: () => {
		d || (d = !0, R?.abort(), R = null, fe?.abort(), fe = null, Ze(), $e(), Ke(), le?.dispose(), ue?.dispose(), de?.dispose(), O?.dispose(), ke?.clearSensitive(), A.dispose(), ae.dispose(), t.dispose(), r.dispose(), e.replaceChildren());
	} };
}
//#endregion
//#region frontend/canvas/src/controllers/autosave-controller.ts
function bp(e) {
	return JSON.stringify(je(e.getState().project));
}
function xp({ store: e, save: t, debounceMs: n = 1e3, documentTarget: r = typeof document > "u" ? void 0 : document, windowTarget: i = typeof window > "u" ? void 0 : window }) {
	let a = 0, o = 0, s = bp(e), c = {
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
		let t = bp(e);
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
function Sp(e = {
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
function Cp() {
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
function wp(e) {
	return {
		schemaVersion: e.project.schemaVersion,
		semanticState: e.project.semanticState,
		layoutState: e.project.layoutState
	};
}
function Tp(e) {
	let { semanticState: t, layoutState: n, ...r } = e.project;
	return r;
}
function Ep({ api: e, store: t, adapter: n, createAutosave: r, openEvents: i }) {
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
			return s.ok && !p && (i !== null && i === l && m?.project.id === e && (t.acknowledgeRevision(s.snapshot.revision), m = s.snapshot), w(Tp(s.snapshot))), s;
		});
		return h = r.then(() => void 0, () => void 0), r.finally(() => {
			--g, g === 0 && _ !== null && te();
		});
	}, E, ee = () => {
		_ = null, C({ remoteSync: {
			status: "idle",
			pendingRevision: null,
			message: null
		} });
	}, D = (e) => {
		let t = _;
		t === null || t.session !== l || t.projectId !== m?.project.id || C({ remoteSync: {
			status: "failed",
			pendingRevision: t.revision,
			message: e
		} });
	}, O = () => {
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
					D(r.message);
					return;
				}
				let i = _;
				if (i === null || i.session !== c || i.projectId !== o) return;
				if (r.value.revision < i.revision) {
					D("Remote project revision is not available yet");
					return;
				}
				if (r.value.revision <= t.getState().runtime.revision) {
					ee();
					return;
				}
				if (g > 0) return;
				if (a?.hasUnconfirmedChanges()) {
					a.markConflict(i.revision), ee();
					return;
				}
				a?.dispose(), s?.close(), n.cancelPendingLoads(), E(r.value);
			} catch (e) {
				!(typeof e == "object" && e && "name" in e && e.name === "AbortError") && !p && c === l && D(e instanceof Error ? e.message : "Remote project refresh failed");
			}
		})();
		return f = h, h.finally(() => {
			f === h && (f = null, d = null);
		}), h;
	}, te = () => {
		let e = _;
		if (!(e === null || e.session !== l || e.projectId !== m?.project.id)) {
			if (e.revision <= t.getState().runtime.revision) {
				ee();
				return;
			}
			if (!(g > 0)) {
				if (a?.hasUnconfirmedChanges()) {
					a.markConflict(e.revision), ee();
					return;
				}
				O();
			}
		}
	}, ne = (e, n) => {
		if (p || n !== l || m === null || !Bt(e)) return;
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
		let u = wp(c);
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
		}), w(Tp(c)), C({
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
	}, ie = async (e) => {
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
	}, k = async (e, t) => {
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
	}, j = async (t) => {
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
		} : r !== c || i !== l ? (w(Tp(f.value)), {
			ok: !0,
			snapshot: f.value
		}) : (c += 1, u?.abort(), d?.abort(), a?.dispose(), s?.close(), n.cancelPendingLoads(), E(f.value), {
			ok: !0,
			snapshot: f.value
		}) : f;
	}, M = () => {
		c += 1, l += 1, _ = null, u?.abort(), d?.abort(), d = null, f = null, a?.dispose(), a = null, o?.(), o = null, s?.close(), s = null, n.cancelPendingLoads(), m = null;
		let e = Cp();
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
			}, t.acknowledgeRevision(e.revision), w(Tp(m)), !0;
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
		switchProject: ie,
		retrySwitch: () => {
			let e = b.pendingSwitch;
			return e === null ? Promise.resolve({
				ok: !1,
				kind: "stale"
			}) : ie(e.projectId);
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
			} : k(n.project.id, (r) => e.renameProject(n.project.id, r, t));
		},
		searchProjects: A,
		createProject: j,
		archiveProject: async (t) => {
			let n = m?.project.id === t, r = await k(t, (n) => e.archiveProject(t, n));
			return r.ok && n && m?.project.id === t && r.snapshot.project.status === "archived" && M(), r;
		},
		restoreProject: (t) => k(t, (n) => e.restoreProject(t, n)),
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
			let n = await k(t, (n) => e.deleteProject(t, n));
			return n.ok && (m?.project.id === t && M(), C({
				projects: b.projects.filter((e) => e.id !== t),
				deleteCandidateId: null
			})), n;
		},
		flushSave: () => a?.flush() ?? Promise.resolve({ ok: !0 }),
		retrySave: () => a?.retry() ?? Promise.resolve({ ok: !0 }),
		retryRemoteSync: () => O(),
		dispose: () => {
			p || (p = !0, c += 1, l += 1, _ = null, u?.abort(), u = null, d?.abort(), d = null, f = null, y?.abort(), y = null, a?.dispose(), a = null, o?.(), o = null, s?.close(), s = null, x.clear());
		}
	};
}
//#endregion
//#region frontend/canvas/src/state/complete-set-projection.ts
var Dp = {
	main: "main_output",
	sku: "sku_output",
	detail: "detail_output"
};
function Op(e, t) {
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
function kp(e, t) {
	return t === void 0 ? `complete-set:${e}:output` : `complete-set:${e}:output:${t}`;
}
function Ap(e, t, n) {
	return n === null ? `complete-set:board:${e}:${t}` : `complete-set:board:${e}:${n}:${t}`;
}
function jp(e) {
	let t = `complete-set:${e}`, n = `${t}:prompt`, r = `${t}:generation`, i = kp(e);
	return {
		nodes: [
			Op(n, "prompt"),
			Op(r, "model_generation"),
			Op(i, Dp[e])
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
function Mp(e, t) {
	return JSON.stringify(e) === JSON.stringify(t);
}
function Np(e, t, n) {
	return e.skuId === n.skuId && e.assetId === null && e.compositionGroupId === n.compositionGroupId && e.textSnapshotId === null ? e.outputBoardId === null ? t !== void 0 && t !== "sku" && e.id === kp(t) || e.prompt === null && e.modelProfileId === null && Mp(e.parameters, {}) : t !== void 0 && e.kind === Dp[t] && e.id === kp(t, e.outputBoardId) && e.prompt === null && e.modelProfileId === null && Mp(e.parameters, {}) : !1;
}
function Pp(e) {
	let t = /* @__PURE__ */ new Map();
	for (let n of e.semanticState.completeSet.selectedOutputTypes) {
		let r = e.semanticState.completeSet.outputs.filter((e) => e.outputType === n);
		for (let e of r) for (let n = 1; n <= (e.quantity ?? 0); n += 1) {
			let r = Ap(e.outputType, n, e.skuId);
			t.set(r, {
				id: r,
				outputNodeId: kp(e.outputType, r),
				outputType: e.outputType,
				skuId: e.skuId,
				sortOrder: t.size,
				selectedResultAssetId: null
			});
		}
	}
	return t;
}
function Fp(e) {
	let t = e.semanticState.completeSet.selectedOutputTypes.map(jp), n = t.flatMap((e) => e.nodes), r = t.flatMap((e) => e.edges), i = Pp(e);
	for (let t of i.values()) {
		let i = Op(t.outputNodeId, Dp[t.outputType]);
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
function Ip(e) {
	let t = Fp(e), n = t.nodes, r = new Map(n.map((e) => [e.id, e])), i = e.semanticState.nodes.filter((e) => e.managedBy === "complete-set");
	if (i.length !== n.length) return !1;
	for (let t of i) {
		let n = r.get(t.id);
		if (n === void 0 || n.kind !== t.kind || !Np(t, e.semanticState.completeSet.selectedOutputTypes.find((e) => t.id.startsWith(`complete-set:${e}:`)), n)) return !1;
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
function Lp(e) {
	for (let t of e.semanticState.completeSet.selectedOutputTypes) {
		if (t === "sku") continue;
		let n = e.semanticState.nodes.find((e) => e.id === kp(t));
		if (n !== void 0) for (let r of e.semanticState.completeSet.outputs) r.outputType === t && (r.prompt = n.prompt ?? "", r.modelProfileId = n.modelProfileId, r.modelParameters = structuredClone(n.parameters));
	}
	for (let t of e.semanticState.outputBoards) {
		let n = e.semanticState.completeSet.outputs.find((e) => e.outputType === t.outputType && e.skuId === t.skuId), r = e.semanticState.nodes.find((e) => e.id === t.outputNodeId);
		n !== void 0 && r !== void 0 && (r.compositionGroupId = n.compositionGroupId);
	}
}
function Rp(e) {
	Lp(e), e.semanticState.advancedCustomized = !Ip(e);
}
//#endregion
//#region frontend/canvas/src/state/history.ts
function zp() {
	return {
		past: [],
		future: []
	};
}
function Bp(e, t) {
	return {
		past: [...e.past, t],
		future: []
	};
}
function Vp(e, t) {
	let n = e.past.at(-1);
	return n === void 0 ? null : {
		snapshot: n,
		history: {
			past: e.past.slice(0, -1),
			future: [t, ...e.future]
		}
	};
}
function Hp(e, t) {
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
var Up = /* @__PURE__ */ new Set(["main-product-source", "main-product-cutout"]), Wp = /* @__PURE__ */ new Set([
	"product_asset",
	"cutout_asset",
	"prompt",
	"background_image",
	"composition",
	"output_image"
]);
function Gp(e) {
	throw Error(`unsupported project action: ${String(e)}`);
}
function Kp(e, t) {
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
function qp(e, t) {
	let n = e.semanticState.completeSet;
	if (n.selectedOutputTypes.includes(t)) return !1;
	n.selectedOutputTypes.push(t), t !== "sku" && n.outputs.push(Kp(t, null));
	let r = jp(t);
	return e.semanticState.nodes.push(...r.nodes), e.semanticState.edges.push(...r.edges), !0;
}
function Jp(e) {
	if (e !== null && (!Number.isInteger(e) || e < 1 || e > 500)) throw Error("output quantity must be null or an integer between 1 and 500");
}
function Yp(e, t, n, r) {
	let i = new Map(e.semanticState.outputBoards.map((e) => [e.id, e]));
	for (let a = 1; a <= r; a += 1) {
		let r = Ap(t, a, n), o = i.get(r);
		if (o !== void 0) {
			let i = e.semanticState.nodes.find((e) => e.id === o.outputNodeId);
			if (o.outputNodeId !== kp(t, r) || o.outputType !== t || o.skuId !== n || i?.managedBy !== "complete-set" || i.outputBoardId !== r) throw Error(`managed board id collision: ${r}`);
		} else {
			let a = kp(t, r);
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
function Xp(e, t, n) {
	let r = /* @__PURE__ */ new Set();
	for (let i = 1; i <= (n ?? 0); i += 1) r.add(Ap(e, i, t));
	return r;
}
function Zp(e, t, n, r) {
	let i = Xp(t, n, r), a = Xp(t, n, 500);
	return e.semanticState.outputBoards.filter((e) => e.outputNodeId === kp(t, e.id) && e.outputType === t && e.skuId === n && a.has(e.id) && !i.has(e.id));
}
function Qp(e, t) {
	let n = new Set(t.map((e) => e.id)), r = new Set(t.map((e) => e.outputNodeId));
	e.semanticState.outputBoards = e.semanticState.outputBoards.filter((e) => !n.has(e.id)), e.semanticState.nodes = e.semanticState.nodes.filter((e) => !r.has(e.id)), e.semanticState.edges = e.semanticState.edges.filter((e) => !r.has(e.sourceNodeId) && !r.has(e.targetNodeId));
	for (let t of r) delete e.layoutState.nodePositions[t];
}
function $p(e, t = "identity") {
	if (e === null || typeof e == "boolean" || typeof e == "string") return JSON.stringify(e);
	if (typeof e == "number") {
		if (!Number.isFinite(e)) throw Error(`confirmation identity contains a non-finite number at ${t}`);
		return JSON.stringify(e);
	}
	if (Array.isArray(e)) return `[${e.map((e, n) => $p(e, `${t}[${n}]`)).join(",")}]`;
	if (typeof e != "object" || e === void 0) throw Error(`confirmation identity contains a non-JSON value at ${t}`);
	let n = e;
	return `{${Object.keys(n).sort().map((e) => `${JSON.stringify(e)}:${$p(n[e], `${t}.${e}`)}`).join(",")}}`;
}
function em(e, t) {
	let n = new TextEncoder().encode(t);
	return `${e}:${Array.from(n, (e) => e.toString(16).padStart(2, "0")).join("")}`;
}
function tm(e, t, n, r = [], i = [], a = [], o = [], s = [], c = []) {
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
		id: em("canvas-diff", $p(p, "diff")),
		...p
	};
}
function nm(e) {
	return e.selectedResultAssetIds.length > 0 || e.taskIds.length > 0 || e.historyResultIds.length > 0;
}
function rm(e) {
	switch (e.type) {
		case "output/disable": return $p({
			type: e.type,
			outputType: e.outputType
		}, "action");
		case "output/setQuantity": return $p({
			type: e.type,
			outputType: e.outputType,
			quantity: e.quantity
		}, "action");
		case "sku/setOutputQuantity": return $p({
			type: e.type,
			skuId: e.skuId,
			quantity: e.quantity
		}, "action");
		case "completeSet/rebuild": return $p({ type: e.type }, "action");
	}
	return Gp(e);
}
function im(e) {
	let t = Object.entries(e.runtime.taskSnapshots).sort(([e], [t]) => e.localeCompare(t)).map(([e, t]) => ({
		taskId: e,
		task: t
	}));
	return $p({
		project: je(e.project),
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
function am(e, t, n) {
	let r = rm(t), i = im(e), a = $p(n, "diffIdentity");
	return {
		token: em("canvas-confirmation", $p({
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
function om(e, t, n) {
	let r = am(e, t, n);
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
function sm(e) {
	e.semanticState.outputBoards.forEach((e, t) => {
		e.sortOrder = t;
	});
}
function cm(e, t) {
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
function lm(e, t, n) {
	let r = new Set(n.semanticState.outputBoards.map((e) => e.id));
	e.unlinkedBoards = e.unlinkedBoards.filter((e) => !r.has(e.boardId)), cm(e, t.semanticState.outputBoards.filter((e) => !r.has(e.id)));
}
function um(e, t) {
	let n = e.taskSnapshots[t.id], r = n !== void 0 && JSON.stringify(n) === JSON.stringify(t), i = /* @__PURE__ */ new Map();
	for (let n of t.results) {
		let t = $p(n, `task.results.${n.id}`), r = i.get(n.id), a = e.resultHistory.find((e) => e.id === n.id);
		if (r !== void 0 && r !== t || a !== void 0 && $p(a, `resultHistory.${n.id}`) !== t) throw Error(`immutable result id conflict ${n.id}`);
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
function dm(e) {
	let t = [], n = [];
	for (let r of e.semanticState.completeSet.selectedOutputTypes) {
		let i = jp(r);
		if (r !== "sku") {
			let t = e.semanticState.completeSet.outputs.find((e) => e.outputType === r && e.skuId === null), n = i.nodes.find((e) => e.id === kp(r));
			t !== void 0 && n !== void 0 && (n.prompt = t.prompt === "" ? null : t.prompt, n.modelProfileId = t.modelProfileId, n.parameters = structuredClone(t.modelParameters));
		}
		t.push(...i.nodes), n.push(...i.edges);
	}
	let r = [];
	for (let i of e.semanticState.completeSet.selectedOutputTypes) {
		let a = e.semanticState.completeSet.outputs.filter((e) => e.outputType === i);
		for (let e of a) for (let i = 1; i <= (e.quantity ?? 0); i += 1) {
			let a = Ap(e.outputType, i, e.skuId), o = kp(e.outputType, a);
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
function fm(e, t) {
	return e.id === t.id && e.kind === t.kind && e.sourceNodeId === t.sourceNodeId && e.sourcePort === t.sourcePort && e.targetNodeId === t.targetNodeId && e.targetPort === t.targetPort && e.skuId === t.skuId;
}
function pm(e, t) {
	let n = dm(e).edges.filter((e) => t.some((t) => e.id.startsWith(`complete-set:${t}:`))), r = new Set(e.semanticState.nodes.filter((e) => e.managedBy === "complete-set").map((e) => e.id));
	return e.semanticState.edges.filter((e) => r.has(e.sourceNodeId) && r.has(e.targetNodeId) && n.some((t) => fm(e, t)));
}
function mm(e, t) {
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
function hm(e) {
	let t = e.project.semanticState.nodes.filter((e) => e.managedBy === "complete-set").map((e) => e.id), n = new Set(t), r = pm(e.project, [
		"main",
		"sku",
		"detail"
	]), i = e.project.semanticState.outputBoards.filter((e) => n.has(e.outputNodeId)), a = dm(e.project);
	mm(e.project, a);
	let o = e.project.semanticState.nodes.filter((e) => e.managedBy !== "complete-set").map((e) => e.id);
	return tm(e, "completeSet/rebuild", i, t, r.map((e) => e.id), a.nodes.map((e) => e.id), a.edges.map((e) => e.id), a.boards.map((e) => e.id), o);
}
function gm(e, t) {
	let n = structuredClone(e), r = new Set(t.removedNodeIds), i = new Set(t.removedEdgeIds), a = new Set(t.removedBoardIds), o = n.project.semanticState.outputBoards.filter((e) => a.has(e.id));
	n.project.semanticState.nodes = n.project.semanticState.nodes.filter((e) => !r.has(e.id)), n.project.semanticState.edges = n.project.semanticState.edges.filter((e) => !i.has(e.id)), n.project.semanticState.outputBoards = n.project.semanticState.outputBoards.filter((e) => !a.has(e.id)), cm(n.runtime, o);
	let s = dm(n.project);
	return n.project.semanticState.nodes.push(...s.nodes), n.project.semanticState.edges.push(...s.edges), n.project.semanticState.outputBoards.push(...s.boards), sm(n.project), Rp(n.project), n;
}
function _m(t, n) {
	switch (n.type) {
		case "output/enable": {
			let e = structuredClone(t), r = qp(e.project, n.outputType);
			return r && Rp(e.project), {
				state: r ? e : t,
				result: { applied: r }
			};
		}
		case "output/setQuantity": {
			if (Jp(n.quantity), (t.project.semanticState.completeSet.outputs.find((e) => e.outputType === n.outputType && e.skuId === null)?.quantity ?? null) === n.quantity) return {
				state: t,
				result: { applied: !1 }
			};
			let e = Zp(t.project, n.outputType, null, n.quantity);
			if (e.length > 0) {
				let r = tm(t, n.type, e);
				if (nm(r)) {
					let e = om(t, n, r);
					if (e !== null) return e;
				}
			}
			let r = structuredClone(t);
			qp(r.project, n.outputType);
			let i = r.project.semanticState.completeSet.outputs.find((e) => e.outputType === n.outputType && e.skuId === null);
			if (i === void 0) throw Error(`missing complete-set output ${n.outputType}`);
			return i.quantity = n.quantity, e.length > 0 && (Qp(r.project, e), cm(r.runtime, e), sm(r.project)), n.quantity !== null && Yp(r.project, n.outputType, null, n.quantity), Rp(r.project), {
				state: r,
				result: { applied: !0 }
			};
		}
		case "sku/setOutputQuantity": {
			Jp(n.quantity);
			let e = t.project.semanticState.completeSet.outputs.find((e) => e.outputType === "sku" && e.skuId === n.skuId), r = e?.quantity ?? null;
			if (e !== void 0 && r === n.quantity) return {
				state: t,
				result: { applied: !1 }
			};
			let i = Zp(t.project, "sku", n.skuId, n.quantity);
			if (i.length > 0) {
				let e = tm(t, n.type, i);
				if (nm(e)) {
					let r = om(t, n, e);
					if (r !== null) return r;
				}
			}
			let a = structuredClone(t);
			qp(a.project, "sku");
			let o = a.project.semanticState.completeSet.outputs.find((e) => e.outputType === "sku" && e.skuId === n.skuId);
			return o === void 0 && (o = Kp("sku", n.skuId), a.project.semanticState.completeSet.outputs.push(o)), o.quantity = n.quantity, i.length > 0 && (Qp(a.project, i), cm(a.runtime, i), sm(a.project)), n.quantity !== null && Yp(a.project, "sku", n.skuId, n.quantity), Rp(a.project), {
				state: a,
				result: { applied: !0 }
			};
		}
		case "output/configure": {
			if (n.outputType === "sku" != (n.skuId !== null)) throw Error("SKU output configuration requires exactly one SKU");
			let e = t.project.semanticState.completeSet.outputs.find((e) => e.outputType === n.outputType && e.skuId === n.skuId);
			if (e === void 0) throw Error("configure an output only after selecting it");
			if (JSON.stringify(e) === JSON.stringify({
				...e,
				...n.patch
			})) return {
				state: t,
				result: { applied: !1 }
			};
			let r = structuredClone(t), i = r.project.semanticState.completeSet.outputs.find((e) => e.outputType === n.outputType && e.skuId === n.skuId);
			if (i === void 0) throw Error("complete-set output disappeared while configuring");
			if (Object.assign(i, structuredClone(n.patch)), n.outputType !== "sku") {
				let e = r.project.semanticState.nodes.find((e) => e.id === kp(n.outputType));
				e !== void 0 && (e.prompt = i.prompt === "" ? null : i.prompt, e.modelProfileId = i.modelProfileId, e.parameters = structuredClone(i.modelParameters));
			}
			return Rp(r.project), {
				state: r,
				result: { applied: !0 }
			};
		}
		case "output/disable": {
			if (!t.project.semanticState.completeSet.selectedOutputTypes.includes(n.outputType)) return {
				state: t,
				result: { applied: !1 }
			};
			let e = `complete-set:${n.outputType}:`, r = t.project.semanticState.nodes.filter((t) => t.managedBy === "complete-set" && t.id.startsWith(e)).map((e) => e.id), i = new Set(r), a = pm(t.project, [n.outputType]), o = new Set(a.map((e) => e.id)), s = t.project.semanticState.edges.filter((e) => i.has(e.sourceNodeId) || i.has(e.targetNodeId)), c = s.some((e) => !o.has(e.id)), l = t.project.semanticState.outputBoards.filter((e) => i.has(e.outputNodeId)), u = tm(t, n.type, l, r, s.map((e) => e.id));
			if (nm(u) || c) {
				let e = om(t, n, u);
				if (e !== null) return e;
			}
			let d = structuredClone(t), f = new Set(s.map((e) => e.id)), p = new Set(l.map((e) => e.id));
			d.project.semanticState.completeSet.selectedOutputTypes = d.project.semanticState.completeSet.selectedOutputTypes.filter((e) => e !== n.outputType), d.project.semanticState.completeSet.outputs = d.project.semanticState.completeSet.outputs.filter((e) => e.outputType !== n.outputType), d.project.semanticState.nodes = d.project.semanticState.nodes.filter((e) => !i.has(e.id));
			for (let e of i) delete d.project.layoutState.nodePositions[e];
			return d.project.semanticState.edges = d.project.semanticState.edges.filter((e) => !f.has(e.id)), d.project.semanticState.outputBoards = d.project.semanticState.outputBoards.filter((e) => !p.has(e.id)), cm(d.runtime, l), sm(d.project), Rp(d.project), {
				state: d,
				result: { applied: !0 }
			};
		}
		case "board/selectResult": {
			let e = t.project.semanticState.outputBoards.find((e) => e.id === n.boardId);
			if (e === void 0) throw Error(`unknown output board ${n.boardId}`);
			let r = t.runtime.allowedResultAssetIds[n.boardId];
			if (n.assetId !== null && (r === void 0 || !r.includes(n.assetId))) throw Error("selected asset is not a permitted result version");
			if (e.selectedResultAssetId === n.assetId) return {
				state: t,
				result: { applied: !1 }
			};
			let i = structuredClone(t), a = i.project.semanticState.outputBoards.find((e) => e.id === n.boardId);
			if (a === void 0) throw Error(`unknown output board ${n.boardId}`);
			return a.selectedResultAssetId = n.assetId, {
				state: i,
				result: { applied: !0 }
			};
		}
		case "task/statusReceived": {
			let e = structuredClone(t), r = um(e.runtime, n.task);
			return {
				state: r ? e : t,
				result: { applied: r }
			};
		}
		case "runtime/setAllowedResultAssets": {
			let e = [...new Set(n.assetIds)].sort(), r = t.runtime.allowedResultAssetIds[n.boardId];
			if (JSON.stringify(r ?? []) === JSON.stringify(e)) return {
				state: t,
				result: { applied: !1 }
			};
			let i = structuredClone(t);
			return i.runtime.allowedResultAssetIds[n.boardId] = e, {
				state: i,
				result: { applied: !0 }
			};
		}
		case "asset/useRectangularSource": {
			let e = t.project.layoutState.productLayers.find((e) => e.skuId === null && e.locked && e.sourceAssetId === n.workingAssetId);
			if (e === void 0) throw Error("rectangular fallback requires the locked main working asset");
			if (e.renderAssetId === n.workingAssetId && e.allowOpaqueFallback) return {
				state: t,
				result: { applied: !1 }
			};
			let r = structuredClone(t), i = r.project.layoutState.productLayers.find((t) => t.id === e.id);
			if (i === void 0) throw Error("rectangular fallback projection is unavailable");
			if (i.renderAssetId = n.workingAssetId, i.allowOpaqueFallback = !0, i.compositionGroupId !== null) for (let e of r.project.layoutState.productLayers) e.compositionGroupId === i.compositionGroupId && e.sourceAssetId === n.workingAssetId && (e.renderAssetId = n.workingAssetId, e.allowOpaqueFallback = !0);
			return {
				state: r,
				result: { applied: !0 }
			};
		}
		case "mode/set": {
			if (t.project.semanticState.mode === n.mode) return {
				state: t,
				result: { applied: !1 }
			};
			let e = structuredClone(t);
			return e.project.semanticState.mode = n.mode, {
				state: e,
				result: { applied: !0 }
			};
		}
		case "viewport/set": {
			let e = structuredClone(n.viewport);
			if (!Number.isFinite(e.x) || !Number.isFinite(e.y) || !Number.isFinite(e.zoom) || e.zoom <= 0 || e.zoom > 1e3) throw Error("canvas viewport must contain finite coordinates and a positive zoom");
			let r = t.project.layoutState.viewport;
			if (r.x === e.x && r.y === e.y && r.zoom === e.zoom) return {
				state: t,
				result: { applied: !1 }
			};
			let i = structuredClone(t);
			return i.project.layoutState.viewport = e, {
				state: i,
				result: { applied: !0 }
			};
		}
		case "node/add": {
			if (n.node.kind === "auto_cutout") throw Error("auto cutout nodes are projected by the system");
			if (n.node.id === "main-product-source" || n.node.id === "main-product-cutout") throw Error("system product pipeline nodes are projected by the system");
			if (t.project.semanticState.nodes.some((e) => e.id === n.node.id)) throw Error(`duplicate canvas node ${n.node.id}`);
			let e = structuredClone(t);
			return e.project.semanticState.nodes.push(structuredClone(n.node)), Rp(e.project), {
				state: e,
				result: { applied: !0 }
			};
		}
		case "node/update": {
			let e = t.project.semanticState.nodes.find((e) => e.id === n.nodeId);
			if (e === void 0) throw Error(`unknown canvas node ${n.nodeId}`);
			if (e.id === "main-product-source" || e.id === "main-product-cutout") throw Error("system product pipeline nodes are immutable");
			let r = structuredClone(t), i = r.project.semanticState.nodes.find((e) => e.id === n.nodeId);
			if (i === void 0) throw Error(`unknown canvas node ${n.nodeId}`);
			return "prompt" in n.patch && (i.prompt = n.patch.prompt ?? null), "modelProfileId" in n.patch && (i.modelProfileId = n.patch.modelProfileId ?? null), "parameters" in n.patch && (i.parameters = {
				...i.parameters,
				...structuredClone(n.patch.parameters ?? {})
			}), "assetId" in n.patch && (i.assetId = n.patch.assetId ?? null), "skuId" in n.patch && (i.skuId = n.patch.skuId ?? null), "compositionGroupId" in n.patch && (i.compositionGroupId = n.patch.compositionGroupId ?? null), Rp(r.project), {
				state: r,
				result: { applied: !0 }
			};
		}
		case "node/move": {
			if (!t.project.semanticState.nodes.some((e) => e.id === n.nodeId)) throw Error(`unknown canvas node ${n.nodeId}`);
			if (Up.has(n.nodeId)) throw Error("system product pipeline nodes are immutable");
			let e = structuredClone(t);
			return e.project.layoutState.nodePositions[n.nodeId] = structuredClone(n.position), {
				state: e,
				result: { applied: !0 }
			};
		}
		case "edge/connect": {
			let e = fe(n.edge);
			if (t.project.semanticState.edges.some((t) => t.id === e.id)) throw Error(`duplicate canvas edge ${e.id}`);
			let r = new Set(t.project.semanticState.nodes.map((e) => e.id));
			if (!r.has(e.sourceNodeId) || !r.has(e.targetNodeId)) throw Error("canvas edge endpoints must exist before connect");
			let i = t.project.semanticState.nodes.find((t) => t.id === e.sourceNodeId), a = t.project.semanticState.nodes.find((t) => t.id === e.targetNodeId);
			if (i === void 0 || a === void 0 || !b(i.kind, a.kind, e.kind)) throw Error("incompatible node connection");
			let o = e.kind === "cutout_asset" && e.sourceNodeId === "main-product-cutout" && i.id === "main-product-cutout" && i.kind === "auto_cutout" && a.kind === "model_generation";
			if ((Up.has(e.sourceNodeId) || Up.has(e.targetNodeId)) && !o) throw Error("system product pipeline edges are projected by the system");
			if (Wp.has(e.kind) && t.project.semanticState.edges.some((t) => t.kind === e.kind && t.targetNodeId === e.targetNodeId)) throw Error("duplicate singleton input is not allowed");
			let s = structuredClone(t);
			return s.project.semanticState.edges.push(e), Rp(s.project), {
				state: s,
				result: { applied: !0 }
			};
		}
		case "text/update": {
			let e = t.project.layoutState.textSnapshots.find((e) => e.id === n.layerId);
			if (e === void 0) throw Error(`unknown text layer ${n.layerId}`);
			let r = structuredClone(t), i = r.project.layoutState.textSnapshots.find((e) => e.id === n.layerId);
			if (i === void 0) throw Error(`unknown text layer ${n.layerId}`);
			let a = structuredClone(n.patch);
			if (a.lineHeight !== void 0) {
				let t = g({
					...e,
					fontSize: a.fontSize ?? e.fontSize
				}, a.lineHeight);
				if (a.lines !== void 0 && JSON.stringify(a.lines) !== JSON.stringify(t.lines)) throw Error("行距更新必须使用确定性的显式行坐标");
				a.lines = t.lines;
			}
			if (a.lines !== void 0) {
				let e = a.lines.map((e) => e.text).join("\n");
				if (a.content !== void 0 && a.content !== e) throw Error("文字内容必须与显式行文本一致");
				a.content = e;
			} else a.content !== void 0 && Object.assign(a, _(e, a.content));
			return Object.assign(i, a), {
				state: r,
				result: { applied: !0 }
			};
		}
		case "composition/update": {
			let e = t.project.semanticState.compositionGroups.find((e) => e.id === n.groupId);
			if (e === void 0) throw Error(`unknown composition group ${n.groupId}`);
			if (JSON.stringify(e.layout) === JSON.stringify(n.layout)) return {
				state: t,
				result: { applied: !1 }
			};
			let r = structuredClone(t), i = r.project.semanticState.compositionGroups.find((e) => e.id === n.groupId);
			if (i === void 0) throw Error(`unknown composition group ${n.groupId}`);
			i.layout = structuredClone(n.layout), i.layoutHash = o(i.layout);
			let a = s(i.layout);
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
			let r = t.project.layoutState.productLayers.find((e) => e.skuId === null && e.locked);
			if (r === void 0 || r.compositionGroupId !== null) return {
				state: t,
				result: { applied: !1 }
			};
			let i = new Set(t.project.semanticState.compositionGroups.map((e) => e.id)), a = 1;
			for (; i.has(`composition-group-${a}`);) a += 1;
			let c = `composition-group-${a}`, l = structuredClone(e), u = structuredClone(t), d = u.project.layoutState.productLayers.find((e) => e.id === r.id);
			if (d === void 0) throw Error("main product layer disappeared while creating composition group");
			d.compositionGroupId = c, u.project.layoutState.objectTransforms[d.transformId] = s(l);
			let f = /* @__PURE__ */ new Map();
			for (let e of n.skuProducts) e.skuId !== null && !f.has(e.skuId) && f.set(e.skuId, e);
			let p = [];
			for (let [e, t] of f) {
				let n = u.project.layoutState.productLayers.find((n) => n.skuId === e && n.compositionGroupId === null && n.locked && n.sourceAssetId === t.sourceAssetId && n.renderAssetId === t.renderAssetId), r = n ?? {
					id: `${c}:sku:${e}`,
					sourceAssetId: t.sourceAssetId,
					renderAssetId: t.renderAssetId,
					allowOpaqueFallback: t.allowOpaqueFallback,
					skuId: e,
					compositionGroupId: null,
					transformId: `${c}:sku:${e}:transform`,
					locked: !0
				};
				if (n === void 0) {
					if (u.project.layoutState.productLayers.some((e) => e.id === r.id)) throw Error(`composition SKU layer id collision: ${r.id}`);
					u.project.layoutState.productLayers.push(r);
				}
				r.compositionGroupId = c, u.project.layoutState.objectTransforms[r.transformId] = s(l), p.push(r.id);
			}
			return u.project.semanticState.compositionGroups.push({
				id: c,
				skuIds: [...f.keys()],
				productLayerIds: [d.id, ...p],
				layout: l,
				layoutHash: o(l)
			}), {
				state: u,
				result: { applied: !0 }
			};
		}
		case "runtime/select": {
			let e = structuredClone(t), r = e.runtime.selectedNodeId !== n.nodeId || e.runtime.selectedBoardId !== n.boardId;
			return e.runtime.selectedNodeId = n.nodeId, e.runtime.selectedBoardId = n.boardId, {
				state: r ? e : t,
				result: { applied: r }
			};
		}
		case "upload/record": {
			if (t.runtime.uploadIds.includes(n.uploadId)) return {
				state: t,
				result: { applied: !1 }
			};
			let e = structuredClone(t);
			return e.runtime.uploadIds.push(n.uploadId), {
				state: e,
				result: { applied: !0 }
			};
		}
		case "generation/paidRequested": {
			if (t.runtime.paidGenerationRequestIds.includes(n.requestId)) return {
				state: t,
				result: { applied: !1 }
			};
			let e = structuredClone(t);
			return e.runtime.paidGenerationRequestIds.push(n.requestId), {
				state: e,
				result: { applied: !0 }
			};
		}
		case "completeSet/rebuild": {
			let e = hm(t), r = om(t, n, e);
			return r === null ? {
				state: gm(t, e),
				result: { applied: !0 }
			} : r;
		}
	}
	return Gp(n);
}
function vm(e, t) {
	let n = _m(e, t);
	return n.result.applied ? {
		...n,
		state: {
			...n.state,
			project: ke(n.state.project),
			runtime: {
				...n.state.runtime,
				pendingConfirmation: null
			}
		}
	} : n;
}
function ym(e) {
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
	return Gp(e);
}
function bm(e = Cp(), t = {
	projectId: "local-project",
	revision: 0
}) {
	let n = {
		project: ke(e),
		runtime: Sp(t)
	}, r = zp(), i = /* @__PURE__ */ new Set(), a = () => {
		for (let e of [...i]) e();
	};
	return {
		getState: () => structuredClone(n),
		dispatch: (e) => {
			let t = n, i = n.project, o = vm(n, e);
			return o.result.applied && ym(e) && (r = Bp(r, structuredClone(i))), n = o.state, n !== t && a(), structuredClone(o.result);
		},
		canUndo: () => r.past.length > 0,
		canRedo: () => r.future.length > 0,
		undo: () => {
			let e = n.project, t = Vp(r, structuredClone(e));
			if (t === null) return !1;
			r = t.history;
			let i = structuredClone(n.runtime);
			return i.pendingConfirmation = null, lm(i, e, t.snapshot), n = {
				...n,
				project: structuredClone(t.snapshot),
				runtime: i
			}, a(), !0;
		},
		redo: () => {
			let e = n.project, t = Hp(r, structuredClone(e));
			if (t === null) return !1;
			r = t.history;
			let i = structuredClone(n.runtime);
			return i.pendingConfirmation = null, lm(i, e, t.snapshot), n = {
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
				project: ke(e),
				runtime: Sp(t ?? {
					projectId: n.runtime.projectId,
					revision: n.runtime.revision
				})
			}, r = zp(), a();
		}
	};
}
//#endregion
//#region frontend/canvas/src/main.ts
var xm = "<main class=\"canvas-shell\" data-canvas-state=\"loading\" aria-busy=\"true\"><p>Loading Product Canvas...</p></main>", Sm = /* @__PURE__ */ new WeakSet();
function Cm(e = bm(), t) {
	let n = document.querySelector("#canvas-app");
	if (n === null) throw Error("Product Canvas mount point \"#canvas-app\" was not found.");
	if (Sm.has(n)) throw Error("Product Canvas is already mounted in #canvas-app.");
	if (t !== void 0) {
		let r = t.element ?? document.createElement("canvas");
		r.dataset.canvasSurface = "product-canvas", n.replaceChildren(r), t.adapter.mount(r, (n) => {
			let r = e.getState().project;
			e.dispatch(n).applied && t.adapter.project(r, e.getState().project);
		});
		let i = e.getState().project;
		return t.adapter.project(null, i), t.adapter.setMode(i.semanticState.mode), Sm.add(n), e;
	}
	return n.innerHTML = xm, Sm.add(n), e;
}
function wm(e) {
	let t = e === null ? "/app/canvas" : `/app/canvas/${encodeURIComponent(e)}`;
	window.location.pathname !== t && window.history.replaceState(null, "", t);
}
function Tm({ bootstrap: e, root: t = document.querySelector("#canvas-app") ?? void 0, api: n = Ze({ apiBase: e.apiBase }), assetsApi: r = _t({ apiBase: e.apiBase }), compositionsApi: i = bt({ apiBase: e.apiBase }), skusApi: a = cn({ apiBase: e.apiBase }), providersApi: o = Tn({ apiBase: e.apiBase }), generationsApi: s = jt({ apiBase: e.apiBase }), exportsApi: c = Ft({ apiBase: e.apiBase }), adapter: l = Pd(), openEvents: u = (t, n) => an({
	apiBase: e.apiBase,
	projectId: t,
	onEvent: n
}), syncUrl: d = wm, loadFont: p = f }) {
	if (t === void 0) throw Error("Product Canvas mount point \"#canvas-app\" was not found.");
	if (Sm.has(t)) throw Error("Product Canvas is already mounted in #canvas-app.");
	Sm.add(t), t.innerHTML = xm;
	let m = bm(), h = /* @__PURE__ */ new Set(), g = Ep({
		api: n,
		store: m,
		adapter: l,
		createAutosave: (e, t) => xp({
			store: e,
			save: t
		}),
		openEvents: (e, t) => u(e, (e) => {
			t(e);
			for (let t of [...h]) t(e);
		})
	}), _ = null, v = !1, y = null, b = g.subscribe((e) => {
		e.activeProjectId !== y && (y = e.activeProjectId, d(y));
	}), x = new AbortController();
	return {
		ready: (async () => {
			try {
				if (await p(), v) return;
				if (_ = yp({
					root: t,
					controller: g,
					store: m,
					adapter: l,
					assetsApi: r,
					compositionsApi: i,
					skusApi: a,
					providersApi: o,
					generationsApi: s,
					exportsApi: c,
					subscribeEvents: (e) => (h.add(e), () => {
						h.delete(e);
					})
				}), e.projectId !== null) {
					let t = await n.getProject(e.projectId, x.signal);
					if (v) return;
					if (!t.ok) throw Error(t.message);
					g.initialize(t.value);
				}
				v || await g.searchProjects("", !1);
			} catch (e) {
				if (!v) {
					let n = document.createElement("p");
					n.className = "canvas-fatal-error", n.setAttribute("role", "alert"), n.textContent = e instanceof Error ? e.message : "画布加载失败", t.replaceChildren(n);
				}
				throw e;
			}
		})(),
		store: m,
		controller: g,
		dispose: () => {
			v || (v = !0, x.abort(), b(), _ === null ? (g.dispose(), l.dispose(), t.replaceChildren()) : _.dispose(), h.clear(), Sm.delete(t));
		}
	};
}
function Em(e) {
	if (typeof e != "object" || !e || Array.isArray(e)) throw Error("Canvas bootstrap must be an object");
	let t = e;
	if (Object.keys(t).sort().join(",") !== "apiBase,projectId" || typeof t.apiBase != "string" || !t.apiBase.startsWith("/") || t.projectId !== null && typeof t.projectId != "string") throw Error("Canvas bootstrap does not match the expected contract");
	return {
		apiBase: t.apiBase,
		projectId: t.projectId
	};
}
function Dm() {
	let e = document.querySelector("#canvas-app"), t = document.querySelector("#canvas-bootstrap");
	if (!(e === null || t === null)) try {
		let n = Tm({
			root: e,
			bootstrap: Em(JSON.parse(t.textContent ?? "null"))
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
Dm();
//#endregion
export { Pd as createCanvasAdapter, Cm as mountCanvas, Em as parseCanvasBootstrap, Tm as startCanvasApplication };
