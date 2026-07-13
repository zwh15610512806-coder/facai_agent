(function () {
  "use strict";

  var API = "/api/creators";
  var esc = FacaiUI.escHtml;
  var state = {
    page: 1,
    perPage: 30,
    totalPages: 0,
    creators: [],
    selectedId: null,
    selected: null,
    members: [],
    products: [],
    followups: [],
    collaborations: [],
    sampleOrders: [],
    activityTab: "all",
    sampleIdempotencyKey: null,
    importToken: null,
    importPreview: null,
    filterTimer: null,
    listRequestId: 0,
    selectionRequestId: 0,
    privateContactRequestId: 0
  };

  var stageLabels = {
    lead: "待联系",
    contacted: "已建联",
    negotiating: "洽谈中",
    sampled: "已寄样",
    scheduled: "已排期",
    cooperating: "合作中",
    completed: "已完成",
    paused: "暂停"
  };
  var collaborationTypeLabels = {live: "直播", short_video: "短视频", graphic: "图文", other: "其他"};
  var collaborationStatusLabels = {planned: "待执行", in_progress: "执行中", completed: "已完成", cancelled: "已取消"};
  var amountStatusLabels = {pending: "待确认", confirmed: "已确认"};
  var followupMethodLabels = {douyin: "抖音私信", wechat: "微信", phone: "电话", offline: "线下", other: "其他"};
  var sampleStatusLabels = {pending_shipment: "待发货", shipped: "已发货", received: "已签收", cancelled: "已取消"};
  var creatorImportFields = [
    ["", "不导入"], ["platform", "平台"], ["platform_uid", "官方达人 ID"], ["douyin_handle", "抖音号"],
    ["nickname", "达人昵称"], ["homepage_url", "主页链接"], ["mcn_name", "MCN / 机构"], ["owner_name", "BD 负责人"],
    ["stage", "阶段"], ["tags", "标签"], ["contact_name", "联系人"], ["contact_phone", "联系电话"], ["wechat_id", "微信号"],
    ["primary_categories", "内容垂类"], ["content_formats", "内容形式"], ["follower_count", "粉丝数"], ["regions", "地区"],
    ["style_tags", "风格"], ["cooperation_preferences", "合作偏好"], ["price_range", "价格带"], ["fit_score", "匹配度"], ["risk_notes", "风险备注"],
    ["audience_profile", "受众画像"], ["recipient_name", "收件人"], ["recipient_phone", "收件电话"], ["province", "省"], ["city", "市"], ["district", "区县"], ["address_detail", "详细地址"]
  ];
  var collaborationImportFields = [
    ["", "不导入"], ["creator_platform_uid", "达人官方 ID"], ["creator_douyin_handle", "达人抖音号"],
    ["external_record_id", "平台记录 ID"], ["internal_code", "合作编号"], ["collaboration_type", "合作形式"], ["collaboration_date", "合作日期"],
    ["status", "合作状态"], ["actual_paid_yuan", "净实付金额（元）"], ["amount_status", "金额状态"], ["owner_name", "BD 负责人"],
    ["product_names", "产品名称"], ["notes", "备注"]
  ];

  function icon(name) {
    return '<i data-lucide="' + esc(name) + '"></i>';
  }

  function refreshIcons() {
    if (window.lucide) window.lucide.createIcons();
  }

  async function apiRequest(url, options) {
    options = Object.assign({}, options || {});
    options.headers = Object.assign({}, options.headers || {});
    if (options.body && !(options.body instanceof FormData)) {
      options.headers["Content-Type"] = "application/json";
      if (typeof options.body !== "string") options.body = JSON.stringify(options.body);
    }
    var response;
    try {
      response = await FacaiUI.fetchWithTimeout(url, options, 30000);
    } catch (error) {
      if (error && (error.name === "AbortError" || error.name === "TimeoutError")) throw new Error("请求超时，请稍后重试");
      throw new Error("网络连接失败，请检查服务是否运行");
    }
    if (!response.ok) throw new Error(await FacaiUI.getApiErrorMessage(response, "操作失败"));
    if (response.status === 204) return null;
    var contentType = response.headers.get("content-type") || "";
    return contentType.indexOf("application/json") >= 0 ? response.json() : response;
  }

  function toastError(error) {
    FacaiUI.toast(error && error.message ? error.message : "操作失败", "error");
  }

  function splitTags(value) {
    return String(value || "").split(/[，,\n]/).map(function (item) { return item.trim(); }).filter(Boolean);
  }

  function nullable(value) {
    value = String(value == null ? "" : value).trim();
    return value || null;
  }

  function numberOrNull(value) {
    if (value === "" || value == null) return null;
    var number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function formatMoney(cents) {
    return "¥" + (Number(cents || 0) / 100).toLocaleString("zh-CN", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  }

  function formatFollowers(value) {
    var count = Number(value || 0);
    if (!count) return "未录入";
    if (count >= 10000) return (count / 10000).toLocaleString("zh-CN", {maximumFractionDigits: 1}) + "万";
    return count.toLocaleString("zh-CN");
  }

  function formatDate(value, withTime) {
    if (!value) return "—";
    var source = String(value);
    if (!withTime && /^\d{4}-\d{2}-\d{2}/.test(source)) return source.slice(0, 10);
    var date = new Date(source);
    if (Number.isNaN(date.getTime())) return source;
    return date.toLocaleString("zh-CN", withTime ? {month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"} : {year: "numeric", month: "2-digit", day: "2-digit"});
  }

  function initial(name) {
    var value = String(name || "达").trim();
    return esc(value.slice(0, 1) || "达");
  }

  function avatarHtml(creator) {
    if (creator.avatar_url) return '<span class="creator-avatar"><img src="' + FacaiUI.escAttr(creator.avatar_url) + '" alt=""></span>';
    return '<span class="creator-avatar" aria-hidden="true">' + initial(creator.nickname) + "</span>";
  }

  function showDialog(id) {
    var dialog = document.getElementById(id);
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    refreshIcons();
  }

  function closeDialog(element) {
    var dialog = element && element.closest ? element.closest("dialog") : null;
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  function formValue(form, name) {
    var field = form.elements.namedItem(name);
    return field ? field.value : "";
  }

  function setFormValue(form, name, value) {
    var field = form.elements.namedItem(name);
    if (field) field.value = value == null ? "" : value;
  }

  function memberName(id) {
    var member = state.members.find(function (item) { return Number(item.id) === Number(id); });
    return member ? member.name : "未分配";
  }

  function updateMemberOptions() {
    var options = state.members.filter(function (item) { return item.active; }).map(function (item) {
      return '<option value="' + item.id + '">' + esc(item.name) + "</option>";
    }).join("");
    [["creatorOwnerFilter", "全部负责人"], ["creatorOwnerInput", "未分配"], ["followupOwnerInput", "沿用达人负责人"], ["collaborationOwnerInput", "沿用达人负责人"]].forEach(function (entry) {
      var select = document.getElementById(entry[0]);
      if (!select) return;
      var current = select.value;
      select.innerHTML = '<option value="">' + entry[1] + "</option>" + options;
      if (current && Array.from(select.options).some(function (option) { return option.value === current; })) select.value = current;
    });
  }

  async function loadMembers() {
    state.members = await apiRequest(API + "/bd-members");
    updateMemberOptions();
    renderMemberList();
  }

  async function loadProducts() {
    state.products = await apiRequest("/api/products/");
    renderCollaborationProducts();
  }

  function queryParameters() {
    var params = new URLSearchParams();
    var values = {
      search: document.getElementById("creatorSearch").value.trim(),
      stage: document.getElementById("creatorStageFilter").value,
      owner_id: document.getElementById("creatorOwnerFilter").value,
      category: document.getElementById("creatorCategoryFilter").value.trim(),
      follower_tier: document.getElementById("creatorFollowerFilter").value,
      sort: document.getElementById("creatorSort").value,
      page: state.page,
      per_page: state.perPage
    };
    Object.keys(values).forEach(function (key) { if (values[key] !== "") params.set(key, values[key]); });
    return params;
  }

  async function loadCreators(options) {
    options = options || {};
    var listRequestId = ++state.listRequestId;
    var list = document.getElementById("creatorList");
    list.innerHTML = '<div class="creator-loading"><span class="creator-spinner"></span>正在载入达人…</div>';
    try {
      var data = await apiRequest(API + "?" + queryParameters().toString());
      if (listRequestId !== state.listRequestId) return;
      state.creators = data.items;
      state.totalPages = data.total_pages;
      document.getElementById("creatorTotalBadge").textContent = data.total;
      renderCreatorList();
      renderCreatorPager(data);
      if (!data.items.length) {
        state.selectionRequestId += 1;
        state.selectedId = null;
        state.selected = null;
        renderEmptyDetail();
        renderActivity();
        return;
      }
      var selectedStillVisible = data.items.some(function (item) { return item.id === state.selectedId; });
      if (options.selectId) state.selectedId = Number(options.selectId);
      else if (!selectedStillVisible) state.selectedId = data.items[0].id;
      renderCreatorList();
      if (state.selectedId && (!state.selected || state.selected.id !== state.selectedId || options.reloadDetail)) {
        await selectCreator(state.selectedId, {keepMobileView: true});
      }
    } catch (error) {
      if (listRequestId !== state.listRequestId) return;
      list.innerHTML = '<div class="creator-empty-state creator-empty-state-compact"><p>' + esc(error.message) + '</p><button type="button" class="creator-btn creator-btn-secondary" data-action="reload-creators">重新加载</button></div>';
      refreshIcons();
    }
  }

  function renderCreatorList() {
    var list = document.getElementById("creatorList");
    if (!state.creators.length) {
      list.innerHTML = '<div class="creator-empty-state creator-empty-state-compact"><div class="creator-empty-icon">' + icon("search-x") + '</div><h2>没有匹配的达人</h2><p>调整搜索或筛选条件，也可以新建达人。</p></div>';
      refreshIcons();
      return;
    }
    list.innerHTML = state.creators.map(function (creator) {
      var selected = creator.id === state.selectedId ? " is-active" : "";
      var handle = creator.douyin_handle ? "@" + creator.douyin_handle : (creator.platform_uid || "未填写抖音号");
      return '<button type="button" class="creator-list-item' + selected + '" data-creator-id="' + creator.id + '">' +
        avatarHtml(creator) + '<span class="creator-list-copy"><span class="creator-list-title"><strong>' + esc(creator.nickname) + '</strong><span class="creator-stage-pill" data-stage="' + esc(creator.stage) + '">' + esc(stageLabels[creator.stage] || creator.stage) + '</span></span>' +
        '<span class="creator-list-subtitle"><span>' + esc(handle) + '</span><span>·</span><span>' + esc(creator.owner_name || "未分配") + '</span></span>' +
        '<span class="creator-list-metrics"><span>' + esc(formatFollowers(creator.follower_count)) + ' 粉丝</span><span>' + esc(formatMoney(creator.metrics.confirmed_paid_cents)) + " 实付</span></span></span></button>";
    }).join("");
    refreshIcons();
  }

  function renderCreatorPager(data) {
    var pager = document.getElementById("creatorPager");
    if (!data.total) { pager.innerHTML = ""; return; }
    pager.innerHTML = '<div class="creator-pager-row"><button type="button" data-page="' + (data.page - 1) + '"' + (data.page <= 1 ? " disabled" : "") + ' aria-label="上一页">' + icon("chevron-left") + '</button><span>第 ' + data.page + " / " + Math.max(1, data.total_pages) + ' 页</span><button type="button" data-page="' + (data.page + 1) + '"' + (data.page >= data.total_pages ? " disabled" : "") + ' aria-label="下一页">' + icon("chevron-right") + "</button></div>";
    refreshIcons();
  }

  function renderEmptyDetail() {
    document.getElementById("creatorDetailBody").innerHTML = '<div class="creator-empty-state"><div class="creator-empty-icon">' + icon("contact-round") + '</div><h2>选择一位达人开始工作</h2><p>从左侧资料库打开达人，即可查看画像、累计实付和下一步 BD 动作。</p><button class="creator-btn creator-btn-primary" type="button" data-action="new-creator">新建第一位达人</button></div>';
    refreshIcons();
  }

  async function selectCreator(creatorId, options) {
    options = options || {};
    var requestedCreatorId = Number(creatorId);
    var selectionRequestId = ++state.selectionRequestId;
    state.selectedId = requestedCreatorId;
    renderCreatorList();
    document.getElementById("creatorDetailBody").innerHTML = '<div class="creator-loading"><span class="creator-spinner"></span>正在载入达人详情…</div>';
    document.getElementById("creatorActivityList").innerHTML = '<div class="creator-loading"><span class="creator-spinner"></span>正在载入业务动态…</div>';
    try {
      var results = await Promise.all([
        apiRequest(API + "/" + requestedCreatorId),
        apiRequest(API + "/" + requestedCreatorId + "/followups"),
        apiRequest(API + "/" + requestedCreatorId + "/collaborations"),
        apiRequest(API + "/" + requestedCreatorId + "/sample-orders")
      ]);
      if (selectionRequestId !== state.selectionRequestId || requestedCreatorId !== state.selectedId) return;
      state.selected = results[0];
      state.followups = results[1];
      state.collaborations = results[2];
      state.sampleOrders = results[3];
      renderCreatorDetail();
      renderActivity();
      if (!options.keepMobileView && window.matchMedia("(max-width: 768px)").matches) setMobileCreatorView("detail");
    } catch (error) {
      if (selectionRequestId !== state.selectionRequestId || requestedCreatorId !== state.selectedId) return;
      document.getElementById("creatorDetailBody").innerHTML = '<div class="creator-empty-state"><div class="creator-empty-icon">' + icon("triangle-alert") + '</div><h2>达人详情加载失败</h2><p>' + esc(error.message) + '</p><button type="button" class="creator-btn creator-btn-secondary" data-action="reload-selected">重新加载</button></div>';
      toastError(error);
    }
    refreshIcons();
  }

  function portraitValue(portrait, key, fallback) {
    if (!portrait || portrait[key] == null || portrait[key] === "") return fallback || "—";
    return portrait[key];
  }

  function tagList(values, emptyText) {
    values = Array.isArray(values) ? values : [];
    if (!values.length) return '<span class="creator-tag">' + esc(emptyText || "暂未填写") + "</span>";
    return values.map(function (value) { return '<span class="creator-tag">' + esc(value) + "</span>"; }).join("");
  }

  function renderCreatorDetail() {
    var creator = state.selected;
    if (!creator) return renderEmptyDetail();
    var portrait = creator.portrait || {};
    var handle = creator.douyin_handle ? "@" + creator.douyin_handle : (creator.platform_uid || "未填写平台身份");
    var addresses = creator.addresses || [];
    var addressHtml = addresses.length ? addresses.map(function (address) {
      return '<div class="creator-address-preview" data-address-id="' + address.id + '"><div><strong>' + esc(address.recipient_name) + " · " + esc(address.phone) + (address.is_default ? ' <span class="creator-status-pill">默认</span>' : "") + '</strong><p>' + esc([address.province, address.city, address.district, address.detail].filter(Boolean).join(" ")) + '</p></div></div>';
    }).join("") : '<p class="creator-muted-copy">尚未添加寄样地址。</p>';
    document.getElementById("creatorDetailBody").innerHTML =
      '<article class="creator-profile-hero">' +
        '<div class="creator-profile-top">' + avatarHtml(creator) + '<div class="creator-profile-title"><h2>' + esc(creator.nickname) + '</h2><p>' + esc(handle) + " · " + esc(creator.mcn_name || "独立达人") + ' · <span class="creator-stage-pill" data-stage="' + esc(creator.stage) + '">' + esc(stageLabels[creator.stage] || creator.stage) + '</span></p></div>' +
        '<div class="creator-profile-actions"><button type="button" class="creator-icon-button" data-action="edit-creator" title="编辑主档" aria-label="编辑主档">' + icon("pencil") + '</button><button type="button" class="creator-icon-button" data-action="archive-creator" title="归档达人" aria-label="归档达人">' + icon("archive") + "</button></div></div>" +
        '<p class="creator-profile-summary">' + esc(creator.portrait_summary || "画像字段尚未完善，补充垂类、内容形式和粉丝数后会自动生成规则摘要。") + "</p></article>" +
      '<section class="creator-kpi-grid"><div class="creator-kpi"><span>累计实付</span><strong data-metric="confirmed-paid">' + esc(formatMoney(creator.metrics.confirmed_paid_cents)) + '</strong></div><div class="creator-kpi"><span>有效合作</span><strong>' + creator.metrics.confirmed_collaboration_count + '</strong></div><div class="creator-kpi"><span>最近合作</span><strong>' + esc(formatDate(creator.metrics.latest_collaboration_date)) + "</strong></div></section>" +
      '<section class="creator-detail-section"><div class="creator-section-heading"><div><h3>结构化画像</h3><p>只基于已录入业务事实生成摘要</p></div><button type="button" class="creator-text-button" data-action="edit-portrait">' + icon("sliders-horizontal") + '编辑画像</button></div><div class="creator-data-grid">' +
        '<div class="creator-data-item"><span>粉丝数</span><strong>' + esc(formatFollowers(portrait.follower_count)) + '</strong></div><div class="creator-data-item"><span>匹配度</span><strong>' + esc(portrait.fit_score ? portrait.fit_score + " / 5" : "未评估") + '</strong></div><div class="creator-data-item"><span>内容形式</span><strong>' + esc((portrait.content_formats || []).join("、") || "—") + '</strong></div><div class="creator-data-item"><span>价格带</span><strong>' + esc(portraitValue(portrait, "price_range")) + "</strong></div></div>" +
        '<div class="creator-section-heading creator-section-heading-spaced"><div><p>内容垂类</p></div></div><div class="creator-tags">' + tagList(portrait.primary_categories, "待补充垂类") + '</div><div class="creator-section-heading creator-section-heading-spaced"><div><p>风格与标签</p></div></div><div class="creator-tags">' + tagList((portrait.style_tags || []).concat(creator.tags || []), "待补充标签") + "</div></section>" +
      '<section class="creator-detail-section"><div class="creator-section-heading"><div><h3>联系与负责人</h3><p>默认只显示脱敏信息</p></div><button type="button" class="creator-text-button" data-action="private-contact">' + icon("eye") + '查看联系方式</button></div><div class="creator-data-grid"><div class="creator-data-item"><span>联系人</span><strong>' + esc(creator.contact_name || "—") + '</strong></div><div class="creator-data-item"><span>电话</span><strong>' + esc(creator.masked_contact_phone || "—") + '</strong></div><div class="creator-data-item"><span>微信</span><strong>' + esc(creator.masked_wechat_id || "—") + '</strong></div><div class="creator-data-item"><span>BD 负责人</span><strong>' + esc(creator.owner_name || "未分配") + "</strong></div></div></section>" +
      '<section class="creator-detail-section"><div class="creator-section-heading"><div><h3>寄样地址</h3><p>完整地址仅按需展开并用于履约</p></div><button type="button" class="creator-text-button" data-action="new-address">' + icon("map-pin-plus") + '添加地址</button></div>' + addressHtml + "</section>" +
      '<section class="creator-detail-section"><div class="creator-section-heading"><div><h3>数据带出</h3><p>按当前达人范围导出</p></div></div><div class="creator-toolbar"><button type="button" class="creator-btn creator-btn-secondary" data-export-entity="creators">达人资料</button><button type="button" class="creator-btn creator-btn-secondary" data-export-entity="collaborations">合作记录</button><button type="button" class="creator-btn creator-btn-secondary" data-export-entity="sample_orders" title="包含必要收件快照，请谨慎传阅">寄样履约</button></div></section>';
    refreshIcons();
  }

  function activityData() {
    var entries = [];
    if (state.activityTab === "all" || state.activityTab === "collaborations") {
      state.collaborations.forEach(function (item) { entries.push({kind: "collaboration", sortDate: item.collaboration_date || item.created_at, item: item}); });
    }
    if (state.activityTab === "all" || state.activityTab === "followups") {
      state.followups.forEach(function (item) { entries.push({kind: "followup", sortDate: item.followed_up_at || item.created_at, item: item}); });
    }
    if (state.activityTab === "all" || state.activityTab === "samples") {
      state.sampleOrders.forEach(function (item) { entries.push({kind: "sample", sortDate: item.updated_at || item.created_at, item: item}); });
    }
    return entries.sort(function (a, b) { return String(b.sortDate || "").localeCompare(String(a.sortDate || "")); });
  }

  function collaborationCard(item) {
    var products = (item.products || []).map(function (product) { return product.product_name_snapshot; }).join("、") || "未关联产品";
    var statusClass = item.status === "cancelled" ? " is-danger" : (item.status === "planned" ? " is-muted" : "");
    var amountClass = item.amount_status === "confirmed" ? "" : " is-warn";
    var actions = item.status === "cancelled" ? "" : '<button type="button" data-action="edit-collaboration" data-collaboration-id="' + item.id + '">编辑合作</button>';
    if (item.status === "planned" || item.status === "in_progress") actions += '<button type="button" data-action="cancel-collaboration" data-collaboration-id="' + item.id + '">取消合作</button>';
    return '<article class="creator-activity-card" data-record-type="collaboration" data-record-id="' + item.id + '"><div class="creator-activity-icon">' + icon(item.collaboration_type === "live" ? "radio-tower" : "clapperboard") + '</div><div class="creator-activity-copy"><div class="creator-activity-title"><strong>' + esc(item.internal_code) + " · " + esc(collaborationTypeLabels[item.collaboration_type] || item.collaboration_type) + '</strong><time>' + esc(formatDate(item.collaboration_date)) + '</time></div><p>' + esc(products) + (item.notes ? "\n" + esc(item.notes) : "") + '</p><div class="creator-activity-meta"><span class="creator-status-pill' + statusClass + '">' + esc(collaborationStatusLabels[item.status] || item.status) + '</span><span class="creator-status-pill' + amountClass + '">' + esc(amountStatusLabels[item.amount_status] || item.amount_status) + " · " + esc(formatMoney(item.actual_paid_cents)) + '</span></div><div class="creator-activity-actions">' + actions + "</div></div></article>";
  }

  function followupCard(item) {
    var next = item.next_followup_at ? '<span class="creator-status-pill is-warn">下次 ' + esc(formatDate(item.next_followup_at, true)) + "</span>" : "";
    return '<article class="creator-activity-card" data-record-type="followup" data-record-id="' + item.id + '"><div class="creator-activity-icon">' + icon("messages-square") + '</div><div class="creator-activity-copy"><div class="creator-activity-title"><strong>' + esc(followupMethodLabels[item.method] || item.method) + " · " + esc(memberName(item.owner_id)) + '</strong><time>' + esc(formatDate(item.followed_up_at, true)) + '</time></div><p>' + esc(item.content) + (item.result ? "\n结果：" + esc(item.result) : "") + '</p><div class="creator-activity-meta">' + next + (item.stage_after ? '<span class="creator-status-pill">阶段：' + esc(stageLabels[item.stage_after] || item.stage_after) + "</span>" : "") + "</div></div></article>";
  }

  function sampleCard(item) {
    var products = (item.items || []).map(function (row) { return row.product_name_snapshot + (row.specification ? "（" + row.specification + "）" : "") + " × " + row.quantity; }).join("、");
    var statusClass = item.status === "cancelled" ? " is-danger" : (item.status === "pending_shipment" ? " is-warn" : "");
    var actions = "";
    if (item.status === "pending_shipment") actions = '<button type="button" data-action="ship-sample-order" data-order-id="' + item.id + '">登记发货</button><button type="button" data-action="cancel-sample-order" data-order-id="' + item.id + '">取消寄样</button>';
    if (item.status === "shipped") actions = '<button type="button" data-action="receive-sample-order" data-order-id="' + item.id + '">确认签收</button>';
    var logistics = item.tracking_number ? "\n" + (item.shipping_company || "快递") + " · " + item.tracking_number : "";
    return '<article class="creator-activity-card" data-record-type="sample" data-order-id="' + item.id + '"><div class="creator-activity-icon">' + icon("package-check") + '</div><div class="creator-activity-copy"><div class="creator-activity-title"><strong>寄样单 #' + item.id + '</strong><time>' + esc(formatDate(item.created_at, true)) + '</time></div><p>' + esc(products || "未填写产品") + esc(logistics) + '</p><div class="creator-activity-meta"><span class="creator-status-pill' + statusClass + '">' + esc(sampleStatusLabels[item.status] || item.status) + '</span><span class="creator-status-pill is-muted">' + esc(item.recipient_name_snapshot) + " · " + esc(item.phone_snapshot) + '</span></div><div class="creator-activity-actions">' + actions + "</div></div></article>";
  }

  function renderActivity() {
    var list = document.getElementById("creatorActivityList");
    if (!state.selected) {
      list.innerHTML = '<div class="creator-empty-state creator-empty-state-compact"><p>选择达人后，这里会汇总合作、跟进和寄样进度。</p></div>';
      return;
    }
    var entries = activityData();
    if (!entries.length) {
      list.innerHTML = '<div class="creator-empty-state creator-empty-state-compact"><div class="creator-empty-icon">' + icon("clipboard-list") + '</div><h2>暂无业务记录</h2><p>从上方快捷动作开始第一次跟进、合作或寄样。</p></div>';
      refreshIcons();
      return;
    }
    list.innerHTML = entries.map(function (entry) {
      if (entry.kind === "collaboration") return collaborationCard(entry.item);
      if (entry.kind === "followup") return followupCard(entry.item);
      return sampleCard(entry.item);
    }).join("");
    refreshIcons();
  }

  function requireCreator() {
    if (state.selected) return true;
    FacaiUI.toast("请先选择一位达人", "error");
    if (window.matchMedia("(max-width: 768px)").matches) setMobileCreatorView("list");
    return false;
  }

  function openCreatorForm(editing) {
    var form = document.getElementById("creatorForm");
    form.reset();
    document.getElementById("creatorEditId").value = "";
    document.getElementById("creatorDialogTitle").textContent = editing ? "编辑达人主档" : "新建达人";
    if (editing && state.selected) {
      var creator = state.selected;
      document.getElementById("creatorEditId").value = creator.id;
      ["nickname", "platform_uid", "douyin_handle", "stage", "owner_id", "mcn_name", "homepage_url", "tags"].forEach(function (name) {
        var value = name === "tags" ? (creator.tags || []).join(", ") : creator[name];
        setFormValue(form, name, value);
      });
      setFormValue(form, "contact_name", "");
      setFormValue(form, "contact_phone", "");
      setFormValue(form, "wechat_id", "");
    }
    showDialog("creatorDialog");
  }

  async function saveCreator(event) {
    event.preventDefault();
    var form = event.currentTarget;
    var editId = document.getElementById("creatorEditId").value;
    var payload = {
      nickname: formValue(form, "nickname").trim(),
      platform_uid: nullable(formValue(form, "platform_uid")),
      douyin_handle: nullable(formValue(form, "douyin_handle")),
      stage: formValue(form, "stage"),
      owner_id: numberOrNull(formValue(form, "owner_id")),
      mcn_name: nullable(formValue(form, "mcn_name")),
      homepage_url: nullable(formValue(form, "homepage_url")),
      tags: splitTags(formValue(form, "tags"))
    };
    ["contact_name", "contact_phone", "wechat_id"].forEach(function (name) {
      var value = nullable(formValue(form, name));
      if (!editId || value !== null) payload[name] = value;
    });
    var submit = form.querySelector('[type="submit"]');
    try {
      var creator = await FacaiUI.withBusyButton(submit, "保存中…", function () {
        return apiRequest(editId ? API + "/" + editId : API, {method: editId ? "PUT" : "POST", body: payload});
      });
      closeDialog(submit);
      FacaiUI.toast(editId ? "达人主档已更新" : "达人已建档", "success");
      state.page = 1;
      await loadCreators({selectId: creator.id, reloadDetail: true});
    } catch (error) { toastError(error); }
  }

  function openPortraitForm() {
    if (!requireCreator()) return;
    var form = document.getElementById("portraitForm");
    form.reset();
    var portrait = state.selected.portrait || {};
    ["primary_categories", "content_formats", "regions", "style_tags", "cooperation_preferences"].forEach(function (name) { setFormValue(form, name, (portrait[name] || []).join(", ")); });
    ["follower_count", "fit_score", "price_range", "risk_notes"].forEach(function (name) { setFormValue(form, name, portrait[name]); });
    var audience = portrait.audience_profile || {};
    setFormValue(form, "audience_profile", audience.description || Object.keys(audience).map(function (key) { return key + "：" + audience[key]; }).join("；"));
    showDialog("portraitDialog");
  }

  async function savePortrait(event) {
    event.preventDefault();
    if (!requireCreator()) return;
    var form = event.currentTarget;
    var audience = nullable(formValue(form, "audience_profile"));
    var payload = {
      primary_categories: splitTags(formValue(form, "primary_categories")),
      content_formats: splitTags(formValue(form, "content_formats")),
      follower_count: numberOrNull(formValue(form, "follower_count")),
      audience_profile: audience ? {description: audience} : {},
      regions: splitTags(formValue(form, "regions")),
      style_tags: splitTags(formValue(form, "style_tags")),
      cooperation_preferences: splitTags(formValue(form, "cooperation_preferences")),
      price_range: nullable(formValue(form, "price_range")),
      fit_score: numberOrNull(formValue(form, "fit_score")),
      risk_notes: nullable(formValue(form, "risk_notes"))
    };
    var submit = form.querySelector('[type="submit"]');
    try {
      await FacaiUI.withBusyButton(submit, "保存中…", function () { return apiRequest(API + "/" + state.selectedId + "/portrait", {method: "PUT", body: payload}); });
      closeDialog(submit);
      FacaiUI.toast("达人画像已更新", "success");
      await loadCreators({selectId: state.selectedId, reloadDetail: true});
    } catch (error) { toastError(error); }
  }

  function openFollowupForm() {
    if (!requireCreator()) return;
    var form = document.getElementById("followupForm");
    form.reset();
    if (state.selected.owner_id) setFormValue(form, "owner_id", state.selected.owner_id);
    showDialog("followupDialog");
  }

  async function saveFollowup(event) {
    event.preventDefault();
    if (!requireCreator()) return;
    var form = event.currentTarget;
    var payload = {
      method: formValue(form, "method"),
      owner_id: numberOrNull(formValue(form, "owner_id")),
      content: formValue(form, "content").trim(),
      result: nullable(formValue(form, "result")),
      next_followup_at: nullable(formValue(form, "next_followup_at")),
      stage_after: nullable(formValue(form, "stage_after"))
    };
    var submit = form.querySelector('[type="submit"]');
    try {
      await FacaiUI.withBusyButton(submit, "保存中…", function () { return apiRequest(API + "/" + state.selectedId + "/followups", {method: "POST", body: payload}); });
      closeDialog(submit);
      FacaiUI.toast("跟进记录已添加", "success");
      await loadCreators({selectId: state.selectedId, reloadDetail: true});
    } catch (error) { toastError(error); }
  }

  function renderCollaborationProducts(selectedIds) {
    var box = document.getElementById("collaborationProducts");
    if (!box) return;
    selectedIds = (selectedIds || []).map(Number);
    box.innerHTML = state.products.length ? state.products.map(function (product) {
      return '<label class="creator-product-option"><input type="checkbox" name="product_ids" value="' + product.id + '"' + (selectedIds.indexOf(Number(product.id)) >= 0 ? " checked" : "") + '><span>' + esc(product.name) + "</span></label>";
    }).join("") : '<span class="creator-muted-copy">暂无可关联产品，请先在产品知识库建档。</span>';
  }

  function collaborationStatusOptions(currentStatus) {
    var allowed = {
      planned: ["planned", "in_progress", "completed", "cancelled"],
      in_progress: ["in_progress", "completed", "cancelled"],
      completed: ["completed"],
      cancelled: ["cancelled"]
    };
    var select = document.getElementById("collaborationForm").elements.namedItem("status");
    Array.from(select.options).forEach(function (option) { option.disabled = currentStatus ? allowed[currentStatus].indexOf(option.value) < 0 : false; });
  }

  function openCollaborationForm(collaboration) {
    if (!requireCreator()) return;
    var form = document.getElementById("collaborationForm");
    form.reset();
    document.getElementById("collaborationEditId").value = collaboration ? collaboration.id : "";
    document.getElementById("collaborationDialogTitle").textContent = collaboration ? "编辑合作与实付" : "记录合作";
    form.elements.namedItem("internal_code").readOnly = Boolean(collaboration);
    if (collaboration) {
      ["internal_code", "collaboration_type", "collaboration_date", "status", "amount_status", "owner_id", "notes"].forEach(function (name) { setFormValue(form, name, collaboration[name]); });
      setFormValue(form, "actual_paid_yuan", (Number(collaboration.actual_paid_cents || 0) / 100).toFixed(2));
      renderCollaborationProducts((collaboration.products || []).map(function (item) { return item.product_id; }));
      collaborationStatusOptions(collaboration.status);
    } else {
      setFormValue(form, "collaboration_date", new Date().toISOString().slice(0, 10));
      setFormValue(form, "internal_code", "BD-" + new Date().toISOString().slice(0, 10).replace(/-/g, "") + "-" + String(Date.now()).slice(-4));
      if (state.selected.owner_id) setFormValue(form, "owner_id", state.selected.owner_id);
      renderCollaborationProducts();
      collaborationStatusOptions(null);
    }
    showDialog("collaborationDialog");
  }

  async function saveCollaboration(event) {
    event.preventDefault();
    if (!requireCreator()) return;
    var form = event.currentTarget;
    var editId = document.getElementById("collaborationEditId").value;
    var products = Array.from(form.querySelectorAll('[name="product_ids"]:checked')).map(function (input) { return {product_id: Number(input.value)}; });
    var payload = {
      collaboration_type: formValue(form, "collaboration_type"),
      collaboration_date: formValue(form, "collaboration_date"),
      status: formValue(form, "status"),
      actual_paid_cents: Math.round(Number(formValue(form, "actual_paid_yuan") || 0) * 100),
      amount_status: formValue(form, "amount_status"),
      owner_id: numberOrNull(formValue(form, "owner_id")),
      notes: nullable(formValue(form, "notes")),
      products: products
    };
    if (!editId) payload.internal_code = formValue(form, "internal_code").trim();
    var submit = form.querySelector('[type="submit"]');
    try {
      await FacaiUI.withBusyButton(submit, "保存中…", function () { return apiRequest(API + "/" + state.selectedId + "/collaborations" + (editId ? "/" + editId : ""), {method: editId ? "PUT" : "POST", body: payload}); });
      closeDialog(submit);
      FacaiUI.toast(editId ? "合作状态与实付已更新" : "合作记录已保存", "success");
      await loadCreators({selectId: state.selectedId, reloadDetail: true});
    } catch (error) { toastError(error); }
  }

  async function cancelCollaboration(collaborationId) {
    if (!window.confirm("确认取消这条合作？取消后不再计入累计实付。")) return;
    try {
      await apiRequest(API + "/" + state.selectedId + "/collaborations/" + collaborationId, {method: "DELETE"});
      FacaiUI.toast("合作已取消", "success");
      await loadCreators({selectId: state.selectedId, reloadDetail: true});
    } catch (error) { toastError(error); }
  }

  function openAddressForm() {
    if (!requireCreator()) return;
    document.getElementById("addressForm").reset();
    showDialog("addressDialog");
  }

  async function saveAddress(event) {
    event.preventDefault();
    if (!requireCreator()) return;
    var form = event.currentTarget;
    var payload = {
      recipient_name: formValue(form, "recipient_name").trim(), phone: formValue(form, "phone").trim(),
      province: formValue(form, "province").trim(), city: formValue(form, "city").trim(), district: nullable(formValue(form, "district")),
      detail: formValue(form, "detail").trim(), is_default: form.elements.namedItem("is_default").checked
    };
    var submit = form.querySelector('[type="submit"]');
    try {
      await FacaiUI.withBusyButton(submit, "保存中…", function () { return apiRequest(API + "/" + state.selectedId + "/addresses", {method: "POST", body: payload}); });
      closeDialog(submit);
      FacaiUI.toast("寄样地址已保存", "success");
      await loadCreators({selectId: state.selectedId, reloadDetail: true});
    } catch (error) { toastError(error); }
  }

  function productOptions(selectedId) {
    return '<option value="">请选择产品</option>' + state.products.map(function (product) { return '<option value="' + product.id + '"' + (Number(selectedId) === Number(product.id) ? " selected" : "") + '>' + esc(product.name) + "</option>"; }).join("");
  }

  function addSampleRow() {
    var box = document.getElementById("sampleProductRows");
    var row = document.createElement("div");
    row.className = "creator-sample-row";
    row.setAttribute("data-sample-item", "");
    row.innerHTML = '<select name="product_id" required aria-label="寄样产品">' + productOptions() + '</select><input class="creator-sample-spec" name="specification" maxlength="300" placeholder="规格，如 500g"><input name="quantity" type="number" min="1" max="10000" value="1" required aria-label="数量"><button type="button" data-action="remove-sample-row" aria-label="删除产品">' + icon("trash-2") + "</button>";
    box.appendChild(row);
    refreshIcons();
  }

  function openSampleForm() {
    if (!requireCreator()) return;
    var form = document.getElementById("sampleOrderForm");
    form.reset();
    state.sampleIdempotencyKey = idempotencyKey();
    var addresses = state.selected.addresses || [];
    var select = document.getElementById("sampleAddressInput");
    select.innerHTML = '<option value="">' + (addresses.length ? "请选择寄样地址" : "请先添加地址") + "</option>" + addresses.map(function (address) {
      return '<option value="' + address.id + '"' + (address.is_default ? " selected" : "") + '>' + esc(address.recipient_name + " · " + address.phone + " · " + [address.province, address.city, address.district].filter(Boolean).join(" ")) + "</option>";
    }).join("");
    document.getElementById("sampleProductRows").innerHTML = "";
    addSampleRow();
    if (!addresses.length) FacaiUI.toast("请先添加寄样地址", "error");
    showDialog("sampleOrderDialog");
  }

  function idempotencyKey() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") return window.crypto.randomUUID();
    return "sample-" + Date.now() + "-" + Math.random().toString(16).slice(2);
  }

  async function saveSampleOrder(event) {
    event.preventDefault();
    if (!requireCreator()) return;
    var form = event.currentTarget;
    var items = Array.from(form.querySelectorAll("[data-sample-item]")).map(function (row) {
      return {product_id: Number(row.querySelector('[name="product_id"]').value), specification: nullable(row.querySelector('[name="specification"]').value), quantity: Number(row.querySelector('[name="quantity"]').value), note: null};
    });
    if (items.some(function (item) { return !item.product_id; })) { FacaiUI.toast("请选择所有寄样产品", "error"); return; }
    if (!state.sampleIdempotencyKey) state.sampleIdempotencyKey = idempotencyKey();
    var payload = {idempotency_key: state.sampleIdempotencyKey, address_id: Number(formValue(form, "address_id")), notes: nullable(formValue(form, "notes")), items: items};
    var submit = form.querySelector('[type="submit"]');
    try {
      await FacaiUI.withBusyButton(submit, "创建中…", function () { return apiRequest(API + "/" + state.selectedId + "/sample-orders", {method: "POST", body: payload}); });
      closeDialog(submit);
      state.sampleIdempotencyKey = null;
      FacaiUI.toast("寄样单已创建", "success");
      await loadCreators({selectId: state.selectedId, reloadDetail: true});
      state.activityTab = "samples";
      syncActivityTabs();
      renderActivity();
    } catch (error) { toastError(error); }
  }

  function openShippingForm(orderId) {
    var order = state.sampleOrders.find(function (item) { return item.id === Number(orderId); });
    if (!order) return;
    var form = document.getElementById("shippingForm");
    form.reset();
    setFormValue(form, "order_id", order.id);
    setFormValue(form, "target_status", "shipped");
    document.getElementById("shippingDialogTitle").textContent = "登记发货";
    document.getElementById("shippingFields").hidden = false;
    form.elements.namedItem("shipping_company").required = true;
    form.elements.namedItem("tracking_number").required = true;
    showDialog("shippingDialog");
  }

  async function saveShipping(event) {
    event.preventDefault();
    var form = event.currentTarget;
    var orderId = Number(formValue(form, "order_id"));
    var payload = {status: formValue(form, "target_status"), shipping_company: nullable(formValue(form, "shipping_company")), tracking_number: nullable(formValue(form, "tracking_number")), notes: nullable(formValue(form, "notes"))};
    var submit = form.querySelector('[type="submit"]');
    try {
      await FacaiUI.withBusyButton(submit, "更新中…", function () { return apiRequest(API + "/" + state.selectedId + "/sample-orders/" + orderId, {method: "PUT", body: payload}); });
      closeDialog(submit);
      FacaiUI.toast("寄样单已更新为已发货", "success");
      await selectCreator(state.selectedId, {keepMobileView: true});
    } catch (error) { toastError(error); }
  }

  async function updateSampleStatus(orderId, status) {
    var label = status === "received" ? "确认该寄样单已签收？" : "确认取消这张待发货寄样单？";
    if (!window.confirm(label)) return;
    try {
      await apiRequest(API + "/" + state.selectedId + "/sample-orders/" + orderId, {method: "PUT", body: {status: status}});
      FacaiUI.toast(status === "received" ? "寄样单已签收" : "寄样单已取消", "success");
      await selectCreator(state.selectedId, {keepMobileView: true});
    } catch (error) { toastError(error); }
  }

  async function openPrivateContact() {
    if (!requireCreator()) return;
    var requestedCreatorId = state.selectedId;
    var privateContactRequestId = ++state.privateContactRequestId;
    document.getElementById("privateContactBody").innerHTML = '<div class="creator-loading"><span class="creator-spinner"></span>正在读取…</div>';
    showDialog("privateContactDialog");
    try {
      var data = await apiRequest(API + "/" + requestedCreatorId + "/private-contact", {cache: "no-store"});
      if (privateContactRequestId !== state.privateContactRequestId || requestedCreatorId !== state.selectedId) return;
      var addresses = (data.addresses || []).map(function (address) {
        return '<div class="creator-contact-address"><strong>' + esc(address.recipient_name) + " · " + esc(address.phone) + '</strong><br>' + esc([address.province, address.city, address.district, address.detail].filter(Boolean).join(" ")) + "</div>";
      }).join("") || '<p class="creator-muted-copy">暂无地址</p>';
      document.getElementById("privateContactBody").innerHTML = '<div class="creator-contact-row"><span>联系人</span><strong>' + esc(data.contact_name || "—") + '</strong></div><div class="creator-contact-row"><span>联系电话</span><strong>' + esc(data.contact_phone || "—") + '</strong></div><div class="creator-contact-row"><span>微信号</span><strong>' + esc(data.wechat_id || "—") + '</strong></div><div class="creator-contact-addresses"><h3>寄样地址</h3>' + addresses + "</div>";
    } catch (error) {
      if (privateContactRequestId !== state.privateContactRequestId || requestedCreatorId !== state.selectedId) return;
      document.getElementById("privateContactBody").innerHTML = '<div class="creator-empty-state creator-empty-state-compact"><p>' + esc(error.message) + "</p></div>";
    }
  }

  async function archiveCreator() {
    if (!requireCreator() || !window.confirm("确认归档这位达人？历史合作和寄样记录会保留。")) return;
    try {
      await apiRequest(API + "/" + state.selectedId, {method: "DELETE"});
      FacaiUI.toast("达人已归档", "success");
      state.selectedId = null;
      state.selected = null;
      await loadCreators();
    } catch (error) { toastError(error); }
  }

  function exportEntity(entity, currentOnly) {
    var params = new URLSearchParams({entity: entity});
    if (currentOnly && state.selectedId) params.set("creator_id", state.selectedId);
    if (!currentOnly) {
      var stage = document.getElementById("creatorStageFilter").value;
      var owner = document.getElementById("creatorOwnerFilter").value;
      var search = document.getElementById("creatorSearch").value.trim();
      var category = document.getElementById("creatorCategoryFilter").value.trim();
      var followerTier = document.getElementById("creatorFollowerFilter").value;
      if (stage) params.set("stage", stage);
      if (owner) params.set("owner_id", owner);
      if (search) params.set("search", search);
      if (category) params.set("category", category);
      if (followerTier) params.set("follower_tier", followerTier);
    }
    var anchor = document.createElement("a");
    anchor.href = API + "/export?" + params.toString();
    anchor.download = "";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    if (entity === "sample_orders") FacaiUI.toast("寄样履约导出包含必要收件快照，请妥善保管", "success");
  }

  function renderMemberList() {
    var box = document.getElementById("bdMemberList");
    if (!box) return;
    box.innerHTML = state.members.length ? state.members.map(function (member) {
      return '<div class="creator-member-row" data-member-id="' + member.id + '"><span><strong>' + esc(member.name) + "</strong> · " + (member.active ? "在岗" : "停用") + '</span><button type="button" data-action="toggle-member" data-member-id="' + member.id + '" data-active="' + member.active + '">' + (member.active ? "停用" : "启用") + "</button></div>";
    }).join("") : '<div class="creator-empty-state creator-empty-state-compact"><p>暂无 BD 成员</p></div>';
  }

  async function saveMember(event) {
    event.preventDefault();
    var form = event.currentTarget;
    var name = formValue(form, "name").trim();
    if (!name) return;
    try {
      await apiRequest(API + "/bd-members", {method: "POST", body: {name: name}});
      form.reset();
      await loadMembers();
      FacaiUI.toast("BD 成员已添加", "success");
    } catch (error) { toastError(error); }
  }

  async function toggleMember(memberId, active) {
    try {
      await apiRequest(API + "/bd-members/" + memberId, {method: "PUT", body: {active: !active}});
      await loadMembers();
    } catch (error) { toastError(error); }
  }

  function openImportDialog() {
    var form = document.getElementById("creatorImportForm");
    form.reset();
    state.importToken = null;
    state.importPreview = null;
    document.getElementById("creatorImportWorkspace").hidden = true;
    document.getElementById("creatorImportValidateButton").hidden = true;
    document.getElementById("creatorImportCommitButton").hidden = true;
    document.getElementById("creatorImportPreviewButton").hidden = false;
    showDialog("creatorImportDialog");
  }

  function mappingFields(kind) {
    return kind === "creators" ? creatorImportFields : collaborationImportFields;
  }

  function renderImportPreview(data) {
    var workspace = document.getElementById("creatorImportWorkspace");
    workspace.hidden = false;
    document.getElementById("creatorImportSummary").innerHTML = '<strong>预检完成：' + data.row_count + ' 行</strong><p>请核对每个来源列对应的业务字段，再执行校验。</p>';
    var fields = mappingFields(data.kind);
    document.getElementById("creatorImportMapping").innerHTML = data.headers.map(function (header) {
      var suggested = data.suggested_mapping[header] || "";
      var options = fields.map(function (field) { return '<option value="' + esc(field[0]) + '"' + (field[0] === suggested ? " selected" : "") + '>' + esc(field[1]) + "</option>"; }).join("");
      return '<label><span>' + esc(header) + '</span><select data-source-header="' + FacaiUI.escAttr(header) + '">' + options + "</select></label>";
    }).join("");
    document.getElementById("creatorImportErrors").innerHTML = "";
    document.getElementById("creatorImportValidateButton").hidden = false;
    document.getElementById("creatorImportCommitButton").hidden = true;
    document.getElementById("creatorImportPreviewButton").hidden = true;
  }

  async function previewImport(event) {
    event.preventDefault();
    var form = event.currentTarget;
    var file = form.elements.namedItem("file").files[0];
    if (!file) { FacaiUI.toast("请选择 .xlsx 文件", "error"); return; }
    var body = new FormData();
    body.append("kind", formValue(form, "kind"));
    body.append("source_type", formValue(form, "source_type"));
    body.append("file", file);
    var button = document.getElementById("creatorImportPreviewButton");
    try {
      var data = await FacaiUI.withBusyButton(button, "正在预检…", function () { return apiRequest(API + "/import/preview", {method: "POST", body: body}); });
      state.importToken = data.token;
      state.importPreview = data;
      renderImportPreview(data);
    } catch (error) { toastError(error); }
  }

  function selectedMapping() {
    var mapping = {};
    document.querySelectorAll("#creatorImportMapping [data-source-header]").forEach(function (select) { if (select.value) mapping[select.getAttribute("data-source-header")] = select.value; });
    return mapping;
  }

  function renderImportResult(data) {
    var errors = data.errors || [];
    document.getElementById("creatorImportSummary").innerHTML = '<strong>校验结果：可提交 ' + data.imported_count + ' 行，错误 ' + data.error_count + ' 行</strong><p>提交时只写入有效行；错误行可下载报告后修正。</p>';
    document.getElementById("creatorImportErrors").innerHTML = errors.length ? errors.slice(0, 30).map(function (error) { return '<div>第 ' + esc(error.row || error.row_number || "?") + " 行：" + esc(error.message || error.error || "校验失败") + "</div>"; }).join("") + '<p><a href="' + API + "/import/" + encodeURIComponent(state.importToken) + '/errors">下载完整错误报告</a></p>' : '<div class="creator-status-pill">所有行校验通过</div>';
  }

  async function validateImport() {
    if (!state.importToken) return;
    var button = document.getElementById("creatorImportValidateButton");
    try {
      var data = await FacaiUI.withBusyButton(button, "校验中…", function () { return apiRequest(API + "/import/" + encodeURIComponent(state.importToken) + "/validate", {method: "POST", body: {mapping: selectedMapping()}}); });
      renderImportResult(data);
      document.getElementById("creatorImportCommitButton").hidden = data.imported_count <= 0;
    } catch (error) { toastError(error); }
  }

  async function commitImport() {
    if (!state.importToken || !window.confirm("确认提交校验通过的有效行？相同文件提交后不能再次导入。")) return;
    var button = document.getElementById("creatorImportCommitButton");
    try {
      var data = await FacaiUI.withBusyButton(button, "提交中…", function () { return apiRequest(API + "/import/" + encodeURIComponent(state.importToken) + "/commit", {method: "POST"}); });
      renderImportResult(data);
      button.hidden = true;
      FacaiUI.toast("导入完成：新增 " + data.imported_count + "，更新 " + data.updated_count, "success");
      await loadCreators({reloadDetail: true});
    } catch (error) { toastError(error); }
  }

  function setMobileCreatorView(view) {
    var workbench = document.getElementById("creatorWorkbench");
    workbench.setAttribute("data-mobile-view", view);
    document.querySelectorAll("[data-mobile-target]").forEach(function (button) {
      var active = button.getAttribute("data-mobile-target") === view;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  function syncActivityTabs() {
    document.querySelectorAll("[data-activity-tab]").forEach(function (button) { button.classList.toggle("is-active", button.getAttribute("data-activity-tab") === state.activityTab); });
  }

  function scheduleReload() {
    clearTimeout(state.filterTimer);
    state.filterTimer = setTimeout(function () { state.page = 1; loadCreators(); }, 260);
  }

  function bindEvents() {
    document.getElementById("creatorForm").addEventListener("submit", saveCreator);
    document.getElementById("portraitForm").addEventListener("submit", savePortrait);
    document.getElementById("followupForm").addEventListener("submit", saveFollowup);
    document.getElementById("collaborationForm").addEventListener("submit", saveCollaboration);
    document.getElementById("addressForm").addEventListener("submit", saveAddress);
    document.getElementById("sampleOrderForm").addEventListener("submit", saveSampleOrder);
    document.getElementById("shippingForm").addEventListener("submit", saveShipping);
    document.getElementById("creatorImportForm").addEventListener("submit", previewImport);
    document.getElementById("bdMemberForm").addEventListener("submit", saveMember);
    ["creatorSearch", "creatorCategoryFilter"].forEach(function (id) { document.getElementById(id).addEventListener("input", scheduleReload); });
    ["creatorStageFilter", "creatorOwnerFilter", "creatorFollowerFilter", "creatorSort"].forEach(function (id) { document.getElementById(id).addEventListener("change", function () { state.page = 1; loadCreators(); }); });

    document.addEventListener("click", function (event) {
      var close = event.target.closest("[data-close-dialog]");
      if (close) { closeDialog(close); return; }
      var mobile = event.target.closest("[data-mobile-target]");
      if (mobile) { setMobileCreatorView(mobile.getAttribute("data-mobile-target")); return; }
      var pageButton = event.target.closest("[data-page]");
      if (pageButton && !pageButton.disabled) { state.page = Number(pageButton.getAttribute("data-page")); loadCreators(); return; }
      var creatorButton = event.target.closest("[data-creator-id]");
      if (creatorButton && creatorButton.classList.contains("creator-list-item")) { selectCreator(creatorButton.getAttribute("data-creator-id")); return; }
      var tab = event.target.closest("[data-activity-tab]");
      if (tab) { state.activityTab = tab.getAttribute("data-activity-tab"); syncActivityTabs(); renderActivity(); return; }
      var exportButton = event.target.closest("[data-export-entity]");
      if (exportButton) { exportEntity(exportButton.getAttribute("data-export-entity"), true); return; }
      var filteredExportButton = event.target.closest("[data-export-filtered-entity]");
      if (filteredExportButton) { exportEntity(filteredExportButton.getAttribute("data-export-filtered-entity"), false); return; }
      var actionButton = event.target.closest("[data-action]");
      if (!actionButton) return;
      var action = actionButton.getAttribute("data-action");
      if (action === "new-creator") openCreatorForm(false);
      else if (action === "edit-creator") openCreatorForm(true);
      else if (action === "edit-portrait") openPortraitForm();
      else if (action === "new-followup") openFollowupForm();
      else if (action === "new-collaboration") openCollaborationForm(null);
      else if (action === "edit-collaboration") openCollaborationForm(state.collaborations.find(function (item) { return item.id === Number(actionButton.getAttribute("data-collaboration-id")); }));
      else if (action === "cancel-collaboration") cancelCollaboration(Number(actionButton.getAttribute("data-collaboration-id")));
      else if (action === "new-address") openAddressForm();
      else if (action === "new-sample") openSampleForm();
      else if (action === "private-contact") openPrivateContact();
      else if (action === "archive-creator") archiveCreator();
      else if (action === "reload-creators") loadCreators();
      else if (action === "reload-selected") selectCreator(state.selectedId);
      else if (action === "open-import") openImportDialog();
      else if (action === "validate-import") validateImport();
      else if (action === "commit-import") commitImport();
      else if (action === "manage-bd") { renderMemberList(); showDialog("bdMemberDialog"); }
      else if (action === "add-sample-row") addSampleRow();
      else if (action === "remove-sample-row") { if (document.querySelectorAll("[data-sample-item]").length > 1) actionButton.closest("[data-sample-item]").remove(); else FacaiUI.toast("至少保留一个寄样产品", "error"); }
      else if (action === "ship-sample-order") openShippingForm(actionButton.getAttribute("data-order-id"));
      else if (action === "receive-sample-order") updateSampleStatus(Number(actionButton.getAttribute("data-order-id")), "received");
      else if (action === "cancel-sample-order") updateSampleStatus(Number(actionButton.getAttribute("data-order-id")), "cancelled");
      else if (action === "toggle-member") toggleMember(Number(actionButton.getAttribute("data-member-id")), actionButton.getAttribute("data-active") === "true");
      else if (action === "export-current") exportEntity("creators", true);
    });

    document.querySelectorAll("dialog").forEach(function (dialog) {
      dialog.addEventListener("click", function (event) {
        if (event.target === dialog) closeDialog(dialog.querySelector("[data-close-dialog]") || dialog);
      });
    });
  }

  async function initialize() {
    bindEvents();
    refreshIcons();
    try {
      await Promise.all([loadMembers(), loadProducts()]);
    } catch (error) { toastError(error); }
    await loadCreators();
  }

  window.setMobileCreatorView = setMobileCreatorView;
  window.loadCreators = loadCreators;
  window.selectCreator = selectCreator;
  window.saveCreator = saveCreator;
  window.savePortrait = savePortrait;
  window.saveFollowup = saveFollowup;
  window.saveCollaboration = saveCollaboration;
  window.saveAddress = saveAddress;
  window.saveSampleOrder = saveSampleOrder;
  window.previewImport = previewImport;
  window.validateImport = validateImport;
  window.commitImport = commitImport;
  window.openPrivateContact = openPrivateContact;

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize);
  else initialize();
})();
