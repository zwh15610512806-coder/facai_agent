import { i as e, r as t, t as n } from "./providers-B_cwmKFI.mjs";
//#region frontend/canvas/src/components/model-profile-editor.ts
var r = {
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
function i(e) {
	let n = document.createElement("section");
	n.className = "canvas-model-profile-editor", n.dataset.testid = "canvas-model-profile-editor";
	let i = document.createElement("h3");
	i.textContent = "添加图像模型";
	let a = document.createElement("form"), o = document.createElement("div");
	o.className = "canvas-model-basic-fields";
	let s = (e, t, n = o) => {
		let r = document.createElement("label");
		r.textContent = e, r.append(t), n.append(r);
	}, c = (e) => {
		let t = document.createElement("input");
		return t.required = !0, t.setAttribute("aria-label", e), s(e, t), t;
	}, l = c("模型 ID / Endpoint ID"), u = c("模型显示名称"), d = document.createElement("fieldset");
	d.className = "canvas-model-capability-fields", d.append(Object.assign(document.createElement("legend"), { textContent: "常用模型能力" }));
	let f = (e, t) => {
		let n = document.createElement("label"), r = document.createElement("input");
		return r.type = "checkbox", r.checked = t, n.append(r, e), d.append(n), r;
	}, p = f("支持文生图", !0), m = f("支持参考图生成", !0), h = f("支持蒙版编辑", !1), g = f("支持取消任务", !1), _ = f("支持幂等请求", !0), v = f("支持幂等查询", !1), y = document.createElement("div");
	y.className = "canvas-model-capability-grid";
	let b = (e, t, n) => {
		let r = document.createElement("input");
		return r.type = "number", r.min = String(n), r.value = String(t), s(e, r, y), r;
	}, x = b("单次最大数量", 1, 1), S = b("最大参考图数量", 1, 0), C = b("并发限制", 1, 1), w = document.createElement("input");
	w.placeholder = "例如 1:1, 3:4, 16:9", s("支持比例（逗号分隔）", w, y);
	let T = document.createElement("input");
	T.placeholder = "例如 1024x1024, 1440x1920", s("支持尺寸（逗号分隔）", T, y);
	let E = document.createElement("select");
	for (let [e, t] of [
		["bytes", "文件字节"],
		["base64", "Base64"],
		["public_url", "公网 URL"],
		["none", "不支持参考图"]
	]) E.append(Object.assign(document.createElement("option"), {
		value: e,
		textContent: t
	}));
	s("参考图传输方式", E, y);
	let D = document.createElement("select");
	for (let [e, t] of [
		["sync", "同步"],
		["async", "异步"],
		["both", "同步与异步"]
	]) D.append(Object.assign(document.createElement("option"), {
		value: e,
		textContent: t
	}));
	s("任务协议", D, y);
	let O = document.createElement("details");
	O.className = "canvas-model-advanced", O.append(Object.assign(document.createElement("summary"), { textContent: "高级 JSON 配置" }));
	let k = document.createElement("p");
	k.textContent = "仅在供应商需要特殊能力或协议字段时展开。启用能力覆盖后，将使用下方完整 JSON。";
	let A = document.createElement("input");
	A.type = "checkbox";
	let j = document.createElement("label");
	j.append(A, "使用高级能力 JSON 覆盖上方字段");
	let M = document.createElement("textarea");
	M.setAttribute("aria-label", "高级模型能力 JSON"), M.value = JSON.stringify(r, null, 2);
	let N = document.createElement("label");
	N.textContent = "完整能力 JSON", N.append(M);
	let P = document.createElement("textarea");
	P.setAttribute("aria-label", "协议配置 JSON"), P.value = "{}";
	let F = document.createElement("label");
	F.textContent = "协议配置 JSON", F.append(P), O.append(k, j, N, F);
	let I = document.createElement("p");
	I.dataset.testid = "canvas-model-profile-feedback", I.setAttribute("role", "status");
	let L = document.createElement("button");
	L.type = "submit", L.textContent = "保存模型配置", a.append(o, d, y, O, I, L), n.append(i, a);
	let R = (e) => e.split(",").map((e) => e.trim()).filter(Boolean), z = () => ({
		...r,
		text_to_image: p.checked,
		image_to_image: m.checked,
		mask_edit: h.checked,
		allowed_ratios: R(w.value),
		allowed_sizes: R(T.value),
		max_quantity: Number(x.value),
		max_reference_images: Number(S.value),
		reference_transfer: E.value,
		protocol: D.value,
		supports_cancel: g.checked,
		supports_idempotency: _.checked,
		supports_idempotency_lookup: v.checked,
		concurrency_limit: Number(C.value)
	}), B = () => {
		let n = e.providerId();
		if (n === null) {
			I.textContent = "请先选择一个第三方提供方";
			return;
		}
		let i;
		try {
			let e = A.checked ? JSON.parse(M.value) : z(), t = JSON.parse(P.value);
			if (typeof e != "object" || !e || Array.isArray(e) || typeof t != "object" || !t || Array.isArray(t)) throw Error();
			i = {
				modelId: l.value.trim(),
				displayName: u.value.trim(),
				capabilities: e,
				config: t
			};
		} catch {
			I.textContent = "高级模型能力和协议配置必须是 JSON 对象";
			return;
		}
		a.reportValidity() && (L.disabled = !0, e.api.createModelProfile(n, i).then((n) => {
			if (L.disabled = !1, n.ok) {
				a.reset(), p.checked = !0, m.checked = !0, _.checked = !0, x.value = "1", S.value = "1", C.value = "1", M.value = JSON.stringify(r, null, 2), P.value = "{}", I.textContent = "", e.onSaved();
				return;
			}
			if (n.kind === "unauthorized") {
				I.textContent = "请解锁后立即重试", e.onUnauthorized(B);
				return;
			}
			if (n.kind === "unconfigured") {
				I.textContent = t(n.message, "请先解锁图像模型管理"), e.onUnconfigured();
				return;
			}
			I.textContent = t(n.message, "模型档案保存失败，请重试");
		}).catch(() => {
			L.disabled = !1, I.textContent = "保存请求失败，请重试";
		}));
	};
	return a.addEventListener("submit", (e) => {
		e.preventDefault(), B();
	}), { element: n };
}
//#endregion
//#region frontend/canvas/src/components/provider-editor.ts
function a(e) {
	let r = document.createElement("section");
	r.className = "canvas-provider-editor", r.dataset.testid = "canvas-provider-editor";
	let i = document.createElement("h3");
	i.textContent = "添加第三方图像提供方";
	let a = document.createElement("form"), o = document.createElement("select");
	o.setAttribute("aria-label", "提供方协议");
	for (let e of n.filter((e) => !e.builtIn)) o.append(Object.assign(document.createElement("option"), {
		value: e.type,
		textContent: e.label
	}));
	let s = (e, t = "text") => {
		let n = document.createElement("label");
		n.textContent = e;
		let r = document.createElement("input");
		return r.type = t, r.required = t !== "password", r.setAttribute("aria-label", e), n.append(r), a.append(n), r;
	}, c = document.createElement("label");
	c.textContent = "提供方协议", c.append(o), a.append(c);
	let l = s("提供方名称"), u = s("服务地址", "url"), d = document.createElement("select");
	d.setAttribute("aria-label", "鉴权方式");
	for (let [e, t] of [
		["bearer", "Bearer"],
		["api_key", "API Key"],
		["none", "无需鉴权"]
	]) d.append(Object.assign(document.createElement("option"), {
		value: e,
		textContent: t
	}));
	let f = document.createElement("label");
	f.textContent = "鉴权方式", f.append(d), a.append(f);
	let p = s("API 密钥", "password");
	p.autocomplete = "off";
	let m = s("密钥说明");
	m.required = !1;
	let h = document.createElement("p");
	h.dataset.testid = "canvas-provider-editor-feedback";
	let g = document.createElement("button");
	g.type = "submit", g.textContent = "安全保存提供方";
	let _ = document.createElement("button");
	_.type = "button", _.textContent = "取消", a.append(h, g, _), r.append(i, a);
	let v = () => {
		a.reset(), p.value = "", h.textContent = "";
	}, y = () => {
		let n = d.value;
		if (!a.reportValidity()) return;
		if (n !== "none" && p.value === "") {
			h.textContent = "请填写仅用于本次保存的 API 密钥";
			return;
		}
		g.disabled = !0;
		let r = {
			adapterType: o.value,
			name: l.value.trim(),
			baseUrl: u.value.trim(),
			authType: n,
			...n === "none" ? {} : { credential: { apiKey: p.value } },
			...m.value.trim() === "" ? {} : { credentialHint: m.value.trim() }
		};
		e.api.createProvider(r).then((n) => {
			if (g.disabled = !1, n.ok) {
				v(), e.onSaved();
				return;
			}
			if (n.kind === "unauthorized") {
				h.textContent = "请解锁后立即重试；密钥只保留在当前表单内存中", e.onUnauthorized(y);
				return;
			}
			if (n.kind === "unconfigured") {
				h.textContent = t(n.message, "供应商保存失败，请重试"), e.onUnconfigured();
				return;
			}
			h.textContent = t(n.message, "供应商保存失败，请重试"), n.kind === "validation" && (p.value = "");
		}).catch(() => {
			g.disabled = !1, h.textContent = "保存请求失败，请重试";
		});
	};
	return a.addEventListener("submit", (e) => {
		e.preventDefault(), y();
	}), _.addEventListener("click", v), d.addEventListener("change", () => {
		p.disabled = d.value === "none", p.required = d.value !== "none", p.disabled && (p.value = "");
	}), {
		element: r,
		clear: v
	};
}
//#endregion
//#region frontend/canvas/src/components/model-manager.ts
function o(e) {
	let n = document.createElement("section");
	n.className = "canvas-model-manager", n.dataset.testid = "canvas-model-manager";
	let r = document.createElement("h2");
	r.textContent = "图像生成模型";
	let o = document.createElement("p");
	o.className = "canvas-model-manager-notice", o.textContent = "在这里统一管理 Seedream 与第三方图像模型。密钥只会写入受保护接口，不会从目录返回或显示。";
	let s = document.createElement("p");
	s.dataset.testid = "canvas-model-manager-feedback", s.setAttribute("role", "status"), s.setAttribute("aria-live", "polite");
	let c = document.createElement("div");
	c.className = "canvas-provider-list";
	let l = document.createElement("select");
	l.setAttribute("aria-label", "模型所属提供方");
	let u = document.createElement("label");
	u.className = "canvas-provider-choice", u.textContent = "添加模型到提供方", u.append(l);
	let d = document.createElement("div");
	d.className = "canvas-model-list";
	let f = [], p = [], m = () => {
		Promise.all([e.managementApi.loadProviders(), e.catalogApi.loadCatalog()]).then(([n, r]) => {
			if (!n.ok) {
				s.textContent = t(n.message, "图像供应商加载失败，请重试");
				return;
			}
			if (!r.ok) {
				s.textContent = t(r.message, "图像模型加载失败，请重试");
				return;
			}
			f = n.value, p = r.value, l.replaceChildren(Object.assign(document.createElement("option"), {
				value: "",
				textContent: "选择提供方以添加模型"
			}), ...f.map((e) => Object.assign(document.createElement("option"), {
				value: e.id,
				textContent: e.name
			}))), c.replaceChildren(...f.map((n) => {
				let r = document.createElement("article");
				r.className = "canvas-provider-row";
				let i = p.filter((e) => e.providerId === n.id).length, a = document.createElement("div");
				a.innerHTML = "<strong></strong><span></span>", a.querySelector("strong").textContent = n.name, a.querySelector("span").textContent = `${i} 个模型 · ${n.enabled ? "已启用" : "已停用"}`;
				let o = document.createElement("button");
				return o.type = "button", o.textContent = "检测连接", o.addEventListener("click", () => {
					window.confirm("本次检测将发送 1 次可能计费的提供方请求；具体费用由供应商计费规则决定。是否继续？") && e.managementApi.probeProvider(n.id, !0).then((n) => {
						if (n.ok) {
							s.textContent = n.value.status === "configuration_ready" ? "连接配置已就绪" : "连接当前不可用";
							return;
						}
						if (n.kind === "unauthorized") {
							e.onUnauthorized(() => o.click());
							return;
						}
						n.kind === "unconfigured" && e.onUnconfigured(), s.textContent = t(n.message, "连通性测试失败，请检查配置");
					});
				}), r.append(a, o), r;
			})), d.replaceChildren(...p.map((e) => {
				let n = document.createElement("article");
				n.className = "canvas-model-row", n.innerHTML = "<strong></strong><span></span>", n.querySelector("strong").textContent = e.displayName;
				let r = e.availability === "available" && e.enabled ? "可用" : t(e.availabilityReason, "不可用");
				return n.querySelector("span").textContent = `${e.modelId} · ${r}`, n;
			})), e.onCatalog(p);
		}).catch(() => {
			s.textContent = "模型目录加载失败";
		});
	}, h = a({
		api: e.managementApi,
		onSaved: m,
		onUnauthorized: e.onUnauthorized,
		onUnconfigured: e.onUnconfigured
	}), g = i({
		api: e.managementApi,
		providerId: () => l.value || null,
		onSaved: m,
		onUnauthorized: e.onUnauthorized,
		onUnconfigured: e.onUnconfigured
	});
	return n.append(r, o, c, h.element, u, g.element, s, d), m(), {
		element: n,
		refresh: m,
		clearSensitive: h.clear
	};
}
//#endregion
//#region frontend/canvas/src/admin.ts
function s({ root: t, apiBase: n }) {
	let r = e({ apiBase: n }), i = document.createElement("p");
	i.className = "canvas-model-admin-status", i.setAttribute("role", "status"), i.setAttribute("aria-live", "polite");
	let a = o({
		catalogApi: r,
		managementApi: r,
		onUnauthorized: (e) => {
			i.textContent = "请求被服务拒绝，请刷新页面后重试。";
		},
		onUnconfigured: () => {
			i.textContent = "服务器尚未配置第三方图像模型密钥，模型管理暂不可用。";
		},
		onCatalog: () => {
			i.textContent = "图像生成模型目录已更新。";
		}
	});
	return t.replaceChildren(a.element, i), { dispose: () => {
		a.clearSensitive(), t.replaceChildren();
	} };
}
var c = document.querySelector("#canvas-model-admin");
if (c !== null) {
	let e = s({
		root: c,
		apiBase: c.dataset.apiBase ?? "/api/canvas"
	});
	window.addEventListener("pagehide", () => e.dispose(), { once: !0 });
}
//#endregion
export { s as mountCanvasModelManager };
