(function () {
  'use strict';

  var center = document.getElementById('operationsCenter');
  if (!center) return;

  var tabs = Array.prototype.slice.call(document.querySelectorAll('[role="tab"][data-tab]'));
  var allowedTabs = tabs.map(function (tab) { return tab.dataset.tab; });
  var activeTab = allowedTabs.indexOf(document.body.dataset.activeTab) >= 0 ? document.body.dataset.activeTab : 'overview';
  var filterOptions = {providers: [], connections: []};
  var pageState = {};
  var activeController = null;
  var activeExport = null;
  var endpoints = {
    overview: '/api/operations/overview',
    orders: '/api/operations/orders',
    products: '/api/operations/products',
    refunds: '/api/operations/refunds',
    adsEntities: '/api/operations/ad-entities',
    adsMetrics: '/api/operations/ad-metrics',
    'sync-runs': '/api/operations/sync-runs'
  };

  function systemLoginUrl() {
    return '/app/login?next=' + encodeURIComponent('/app/operations?tab=' + activeTab);
  }

  function notify(message, type) {
    if (window.FacaiUI && typeof window.FacaiUI.toast === 'function') {
      window.FacaiUI.toast(message, type || 'error');
    }
  }

  function setButtonBusy(button, busy) {
    if (!button) return;
    if (busy) {
      button.dataset.previousDisabled = button.disabled ? 'true' : 'false';
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
    } else {
      button.removeAttribute('aria-busy');
      button.disabled = button.dataset.previousDisabled === 'true';
      delete button.dataset.previousDisabled;
    }
  }

  async function apiErrorMessage(response, fallback) {
    if (window.FacaiUI && typeof window.FacaiUI.getApiErrorMessage === 'function') {
      return window.FacaiUI.getApiErrorMessage(response, fallback);
    }
    return fallback;
  }

  async function apiFetch(url, options, fallback) {
    options = options || {};
    var headers = options.headers || {};
    if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    options.headers = headers;
    options.credentials = 'same-origin';
    var response = await fetch(url, options);
    if (response.status === 401) {
      window.location.assign(systemLoginUrl());
      var authError = new Error('system_session_required');
      authError.isAuthRedirect = true;
      throw authError;
    }
    if (!response.ok) {
      var fallbackMessage = response.status === 403 ? '当前账号没有执行此操作的权限。' : (fallback || '请求失败，请稍后重试。');
      var error = new Error(await apiErrorMessage(response, fallbackMessage));
      error.status = response.status;
      throw error;
    }
    return response;
  }

  async function requestJson(url, options, fallback) {
    var response = await apiFetch(url, options, fallback);
    if (response.status === 204) return {};
    return response.json();
  }

  function panelFor(name) {
    return document.getElementById('panel-' + name);
  }

  function abortActiveRequest() {
    if (activeController) activeController.abort();
    activeController = null;
  }

  function clearExportPolling(task) {
    var selected = task || activeExport;
    if (!selected) return;
    selected.cancelled = true;
    if (selected.timer !== null) window.clearTimeout(selected.timer);
    if (selected.controller) selected.controller.abort();
    setButtonBusy(selected.button, false);
    if (activeExport === selected) activeExport = null;
  }

  function showPanelState(panel, state, message) {
    var status = panel.querySelector('[data-panel-state]');
    status.hidden = false;
    status.dataset.state = state;
    status.textContent = message;
    panel.querySelectorAll('.integration-table-wrap').forEach(function (wrap) { wrap.hidden = true; });
    var pagination = panel.querySelector('[data-pagination]');
    if (pagination) pagination.hidden = true;
  }

  function hidePanelState(panel) {
    var status = panel.querySelector('[data-panel-state]');
    status.hidden = true;
    status.textContent = '';
  }

  function activateTab(name, options) {
    options = options || {};
    if (allowedTabs.indexOf(name) < 0) name = 'overview';
    if (activeTab !== name) {
      abortActiveRequest();
      clearExportPolling();
    }
    activeTab = name;
    tabs.forEach(function (tab) {
      var selected = tab.dataset.tab === name;
      tab.setAttribute('aria-selected', selected ? 'true' : 'false');
      tab.tabIndex = selected ? 0 : -1;
      panelFor(tab.dataset.tab).hidden = !selected;
      if (selected && options.focus) tab.focus();
    });
    if (options.history !== false) {
      var url = new URL(window.location.href);
      url.searchParams.set('tab', name);
      window.history.replaceState({}, '', url.pathname + url.search);
    }
    if (options.load !== false) loadDataTab(name);
  }

  tabs.forEach(function (tab, index) {
    tab.addEventListener('click', function () { activateTab(tab.dataset.tab); });
    tab.addEventListener('keydown', function (event) {
      var target = index;
      if (event.key === 'ArrowRight') target = (index + 1) % tabs.length;
      else if (event.key === 'ArrowLeft') target = (index - 1 + tabs.length) % tabs.length;
      else if (event.key === 'Home') target = 0;
      else if (event.key === 'End') target = tabs.length - 1;
      else return;
      event.preventDefault();
      activateTab(tabs[target].dataset.tab, {focus: true});
    });
  });

  function providerKey(item) {
    return String(item.key || item.provider || item.value || '');
  }

  function providerLabel(item) {
    return item.label || item.name || providerKey(item);
  }

  function connectionName(item) {
    return item.name || item.display_name || String(item.id || '');
  }

  function populateSelects(form) {
    var providerSelect = form.elements.provider;
    var connectionSelect = form.elements.connection_id;
    var selectedProvider = providerSelect.value;
    var selectedConnection = connectionSelect.value;
    providerSelect.replaceChildren();
    var allProviders = document.createElement('option');
    allProviders.value = '';
    allProviders.textContent = '全部平台';
    providerSelect.appendChild(allProviders);
    filterOptions.providers.forEach(function (provider) {
      var option = document.createElement('option');
      option.value = providerKey(provider);
      option.textContent = providerLabel(provider);
      providerSelect.appendChild(option);
    });
    providerSelect.value = Array.prototype.some.call(providerSelect.options, function (option) { return option.value === selectedProvider; }) ? selectedProvider : '';

    connectionSelect.replaceChildren();
    var allConnections = document.createElement('option');
    allConnections.value = '';
    allConnections.textContent = '全部连接';
    connectionSelect.appendChild(allConnections);
    filterOptions.connections.filter(function (connection) {
      return !providerSelect.value || connection.provider === providerSelect.value;
    }).forEach(function (connection) {
      var option = document.createElement('option');
      option.value = String(connection.id);
      option.textContent = connectionName(connection);
      connectionSelect.appendChild(option);
    });
    if (Array.prototype.some.call(connectionSelect.options, function (option) { return option.value === selectedConnection; })) connectionSelect.value = selectedConnection;
  }

  async function refreshFilterOptions() {
    var data = await requestJson('/api/operations/filter-options', {}, '筛选项暂时无法读取。');
    filterOptions = {providers: data.providers || [], connections: data.connections || []};
    document.querySelectorAll('[data-filter-form]').forEach(populateSelects);
  }

  function formatValue(value) {
    if (value === null || value === undefined || value === '') return '—';
    if (Array.isArray(value)) return value.length ? value.join('、') : '—';
    return String(value);
  }

  function formatTime(value) {
    if (!value) return '—';
    var date = new Date(value);
    if (Number.isNaN(date.getTime())) return formatValue(value);
    return new Intl.DateTimeFormat('zh-CN', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'}).format(date);
  }

  function createRow(values) {
    var row = document.createElement('tr');
    values.forEach(function (value) {
      var cell = document.createElement('td');
      if (value instanceof Node) cell.appendChild(value);
      else cell.textContent = formatValue(value);
      row.appendChild(cell);
    });
    return row;
  }

  function itemValue(item, names) {
    for (var index = 0; index < names.length; index += 1) {
      var value = item[names[index]];
      if (value !== undefined && value !== null && value !== '') return value;
    }
    return null;
  }

  function queryForPanel(name) {
    var form = panelFor(name).querySelector('[data-filter-form]');
    var params = new URLSearchParams();
    Array.from(new FormData(form).entries()).forEach(function (entry) {
      var value = String(entry[1]).trim();
      if (value) params.set(entry[0], value);
    });
    if (name !== 'overview') {
      params.set('page', String((pageState[name] && pageState[name].page) || 1));
      if (!params.has('per_page')) params.set('per_page', '50');
    }
    return params;
  }

  function updatePagination(panel, name, data) {
    if (name === 'overview') return;
    var pagination = panel.querySelector('[data-pagination]');
    var page = Number(data.page || 1);
    var totalPages = Math.max(1, Number(data.total_pages || 1));
    pageState[name] = {page: page, totalPages: totalPages};
    pagination.hidden = false;
    pagination.querySelector('[data-page-status]').textContent = '第 ' + page + ' / ' + totalPages + ' 页，共 ' + Number(data.total || 0) + ' 条';
    pagination.querySelector('[data-page="prev"]').disabled = page <= 1;
    pagination.querySelector('[data-page="next"]').disabled = page >= totalPages;
  }

  function renderOverview(panel, data) {
    ['actual_sales', 'order_count', 'refund_amount', 'average_order_value', 'ad_attributed_sales', 'ad_spend'].forEach(function (key) {
      panel.querySelector('[data-kpi="' + key + '"]').textContent = formatValue(data[key]);
    });
    var items = data.daily || [];
    var body = panel.querySelector('[data-table-body]');
    body.replaceChildren();
    if (!items.length) {
      showPanelState(panel, 'empty', '概览已更新，当前日期范围暂无每日明细。');
      return;
    }
    items.forEach(function (item) { body.appendChild(createRow([itemValue(item, ['date', 'display_date']), item.actual_sales, item.order_count, item.ad_attributed_sales, item.ad_spend])); });
    hidePanelState(panel);
    panel.querySelector('[data-table-wrap]').hidden = false;
  }

  function actionButton(label, product) {
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-soft btn-sm';
    button.dataset.productLink = 'true';
    button.dataset.productId = String(itemValue(product, ['id', 'commerce_product_id']) || '');
    button.dataset.productName = String(itemValue(product, ['title', 'product_title', 'name', 'external_product_id']) || '未命名平台商品');
    var link = product.product_link || {};
    button.dataset.linkedProductId = String(itemValue(product, ['product_id', 'linked_product_id']) || link.product_id || '');
    button.textContent = button.dataset.linkedProductId ? '更改关联' : label;
    button.setAttribute('aria-label', button.textContent + ' ' + button.dataset.productName);
    return button;
  }

  function formatProgress(value) {
    var selected = Number(value);
    if (!Number.isFinite(selected)) return '—';
    var percent = Math.max(0, Math.min(100, selected * 100));
    return (Number.isInteger(percent) ? String(percent) : percent.toFixed(1)) + '%';
  }

  function renderList(panel, name, data) {
    var items = data.items || [];
    var body = panel.querySelector('[data-table-body]');
    body.replaceChildren();
    if (!items.length) {
      showPanelState(panel, 'empty', '当前筛选条件下暂无数据。');
      updatePagination(panel, name, data);
      return;
    }
    items.forEach(function (item) {
      var values;
      if (name === 'orders') {
        values = [itemValue(item, ['external_order_id', 'order_id', 'external_id']), item.provider, itemValue(item, ['normalized_status', 'status']), itemValue(item, ['paid_amount', 'amount']), formatTime(itemValue(item, ['business_time', 'paid_at', 'created_at']))];
      } else if (name === 'products') {
        var productLink = item.product_link || {};
        values = [itemValue(item, ['external_product_id', 'external_id']), itemValue(item, ['title', 'product_title', 'name']), itemValue(item, ['normalized_status', 'status']), itemValue(item, ['linked_product_name', 'product_name']) || productLink.product_name, actionButton('关联产品', item)];
      } else if (name === 'refunds') {
        values = [itemValue(item, ['external_refund_id', 'refund_id', 'external_id']), itemValue(item, ['external_order_id', 'order_id']), itemValue(item, ['normalized_status', 'status']), itemValue(item, ['refund_amount', 'amount']), formatTime(itemValue(item, ['business_time', 'completed_at', 'created_at']))];
      } else {
        values = [itemValue(item, ['public_id', 'run_id', 'id']), itemValue(item, ['connection_name', 'connection_id']), item.resource_type, item.source, item.status, formatProgress(item.progress), '读 ' + Number(item.records_read || 0) + ' / 写 ' + Number(item.records_written || 0) + ' / 跳过 ' + Number(item.records_skipped || 0) + ' / 隔离 ' + Number(item.records_quarantined || 0), item.failure_summary, formatTime(item.window_start) + ' – ' + formatTime(item.window_end)];
      }
      body.appendChild(createRow(values));
    });
    hidePanelState(panel);
    panel.querySelector('[data-table-wrap]').hidden = false;
    updatePagination(panel, name, data);
  }

  function renderAds(panel, entitiesData, metricsData) {
    var entities = entitiesData.items || [];
    var metrics = metricsData.items || [];
    var entityBody = panel.querySelector('[data-ad-entities-body]');
    var metricsBody = panel.querySelector('[data-ad-metrics-body]');
    entityBody.replaceChildren();
    metricsBody.replaceChildren();
    entities.forEach(function (item) { entityBody.appendChild(createRow([itemValue(item, ['external_entity_id', 'external_id']), item.entity_type, itemValue(item, ['name', 'entity_name']), itemValue(item, ['normalized_status', 'status'])])); });
    metrics.forEach(function (item) { metricsBody.appendChild(createRow([itemValue(item, ['display_date', 'stat_date', 'business_time']), itemValue(item, ['external_entity_id', 'entity_id']), itemValue(item, ['ad_spend', 'spend']), itemValue(item, ['ad_attributed_sales', 'attributed_sales']), itemValue(item, ['conversion_count', 'conversions', 'orders'])])); });
    if (!entities.length && !metrics.length) showPanelState(panel, 'empty', '当前筛选条件下暂无广告实体或指标。');
    else {
      hidePanelState(panel);
      panel.querySelector('[data-ad-entities-wrap]').hidden = !entities.length;
      panel.querySelector('[data-ad-metrics-wrap]').hidden = !metrics.length;
    }
    updatePagination(panel, 'ads', {page: Number(entitiesData.page || metricsData.page || 1), total_pages: Math.max(Number(entitiesData.total_pages || 1), Number(metricsData.total_pages || 1)), total: Number(entitiesData.total || 0) + Number(metricsData.total || 0)});
  }

  async function loadDataTab(name) {
    if (name !== activeTab) return;
    abortActiveRequest();
    var controller = new AbortController();
    activeController = controller;
    var panel = panelFor(name);
    var params = queryForPanel(name);
    panel.setAttribute('aria-busy', 'true');
    showPanelState(panel, 'loading', '正在从 API 读取数据…');
    try {
      if (name === 'ads') {
        var entityParams = new URLSearchParams(params.toString());
        var metricParams = new URLSearchParams(params.toString());
        entityParams.delete('granularity');
        metricParams.delete('search');
        var results = await Promise.all([
          requestJson(endpoints.adsEntities + '?' + entityParams.toString(), {signal: controller.signal}, '广告实体暂时无法读取。'),
          requestJson(endpoints.adsMetrics + '?' + metricParams.toString(), {signal: controller.signal}, '广告指标暂时无法读取。')
        ]);
        if (activeController === controller && activeTab === name) renderAds(panel, results[0], results[1]);
      } else {
        var query = params.toString();
        var data = await requestJson(endpoints[name] + (query ? '?' + query : ''), {signal: controller.signal}, '数据暂时无法读取。');
        if (activeController !== controller || activeTab !== name) return;
        if (name === 'overview') renderOverview(panel, data);
        else renderList(panel, name, data);
      }
    } catch (error) {
      if (error.name !== 'AbortError' && !error.isAuthRedirect && activeTab === name) showPanelState(panel, 'error', error.message || '数据读取失败。');
    } finally {
      if (activeController === controller) {
        activeController = null;
        panel.setAttribute('aria-busy', 'false');
      }
    }
  }

  function filtersForExport(name, resourceType) {
    var params = queryForPanel(name);
    params.delete('page');
    params.delete('per_page');
    var resourceFilters = {orders: ['status', 'search'], products: ['status', 'search', 'link_status'], refunds: ['status', 'search'], ad_entities: ['entity_type', 'search'], ad_daily_metrics: ['entity_type', 'granularity']};
    var allowed = ['provider', 'connection_id', 'date_from', 'date_to'].concat(resourceFilters[resourceType] || []);
    var filters = {};
    params.forEach(function (value, key) { if (allowed.indexOf(key) >= 0) filters[key] = key === 'connection_id' ? Number(value) : value; });
    return filters;
  }

  function exportIsActive(task) {
    return activeExport === task && !task.cancelled && activeTab === task.panel.id.replace('panel-', '');
  }

  function scheduleExportPoll(task) {
    if (!exportIsActive(task)) return;
    task.timer = window.setTimeout(function () { task.timer = null; pollExport(task); }, 2000);
  }

  async function pollExport(task) {
    if (!exportIsActive(task) || task.inFlight) return;
    task.inFlight = true;
    try {
      var data = await requestJson('/api/operations/exports/' + encodeURIComponent(task.id), {signal: task.controller.signal}, '导出状态暂时无法读取。');
      if (!exportIsActive(task)) return;
      var status = task.panel.querySelector('[data-panel-state]');
      status.hidden = false;
      if (data.status === 'ready' || data.status === 'succeeded') {
        status.dataset.state = 'ready';
        status.textContent = '导出已完成，可下载。';
        var link = task.panel.querySelector('[data-export-download]');
        link.href = data.download_url || ('/api/operations/exports/' + encodeURIComponent(task.id) + '/download');
        link.hidden = false;
        clearExportPolling(task);
      } else if (['failed', 'expired'].indexOf(data.status) >= 0) {
        status.dataset.state = 'error';
        status.textContent = data.error_summary || (data.status === 'expired' ? '导出已过期，请重新创建。' : '导出失败，请重新创建。');
        clearExportPolling(task);
      } else {
        status.dataset.state = 'loading';
        status.textContent = '导出正在生成，可继续查看本页。';
        scheduleExportPoll(task);
      }
    } catch (error) {
      if (exportIsActive(task) && !error.isAuthRedirect) showPanelState(task.panel, 'error', error.message);
      clearExportPolling(task);
    } finally {
      task.inFlight = false;
    }
  }

  async function startExport(name, button) {
    clearExportPolling();
    var panel = panelFor(name);
    var link = panel.querySelector('[data-export-download]');
    link.hidden = true;
    link.removeAttribute('href');
    var task = {panel: panel, button: button, id: null, timer: null, inFlight: false, cancelled: false, controller: new AbortController()};
    activeExport = task;
    setButtonBusy(button, true);
    try {
      var data = await requestJson('/api/operations/exports', {method: 'POST', signal: task.controller.signal, body: JSON.stringify({resource_type: button.dataset.exportResource, format: 'csv', filters: filtersForExport(name, button.dataset.exportResource)})}, '导出任务创建失败。');
      if (!exportIsActive(task)) return;
      task.id = data.id || data.export_id;
      if (!task.id) throw new Error('导出任务响应无效。');
      await pollExport(task);
    } catch (error) {
      if (exportIsActive(task) && !error.isAuthRedirect) showPanelState(panel, 'error', error.message);
      clearExportPolling(task);
    }
  }

  async function downloadExport(event) {
    event.preventDefault();
    var link = event.currentTarget;
    var href = link.getAttribute('href');
    if (!href) return;
    link.setAttribute('aria-busy', 'true');
    try {
      var response = await apiFetch(href, {}, '导出文件暂时无法下载。');
      var blob = await response.blob();
      var objectUrl = URL.createObjectURL(blob);
      var anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = 'operations-export.csv';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(function () { URL.revokeObjectURL(objectUrl); }, 0);
    } catch (error) {
      if (!error.isAuthRedirect) showPanelState(link.closest('[role="tabpanel"]'), 'error', error.message);
    } finally {
      link.removeAttribute('aria-busy');
    }
  }

  var productDialog = document.getElementById('productLinkDialog');
  var productForm = productDialog.querySelector('[data-product-link-form]');

  function openProductDialog(button) {
    productForm.reset();
    productForm.elements.commerce_product_id.value = button.dataset.productId;
    productDialog.querySelector('[data-product-link-name]').textContent = button.dataset.productName;
    productDialog.querySelector('[data-product-dialog-status]').textContent = '';
    var unlink = productDialog.querySelector('[data-product-unlink]');
    unlink.hidden = !button.dataset.linkedProductId;
    unlink.dataset.productId = button.dataset.productId;
    productDialog.showModal();
  }

  async function searchInternalProducts(button) {
    var status = productDialog.querySelector('[data-product-dialog-status]');
    var select = productForm.elements.product_id;
    setButtonBusy(button, true);
    try {
      var data = await requestJson('/api/products/?search=' + encodeURIComponent(productForm.elements.product_search.value.trim()), {}, '内部产品暂时无法搜索。');
      var items = Array.isArray(data) ? data : (data.items || []);
      select.replaceChildren();
      var placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = items.length ? '请选择产品' : '没有匹配产品';
      select.appendChild(placeholder);
      items.forEach(function (item) {
        var option = document.createElement('option');
        option.value = String(item.id);
        option.textContent = formatValue(item.name) + (item.category ? ' · ' + item.category : '');
        select.appendChild(option);
      });
      status.textContent = items.length ? '找到 ' + items.length + ' 个产品。' : '没有匹配产品。';
    } catch (error) {
      if (!error.isAuthRedirect) status.textContent = error.message;
    } finally {
      setButtonBusy(button, false);
    }
  }

  async function submitProductLink(event) {
    event.preventDefault();
    var commerceId = productForm.elements.commerce_product_id.value;
    var productId = Number(productForm.elements.product_id.value);
    var submit = productForm.querySelector('[type="submit"]');
    if (!commerceId || !Number.isInteger(productId) || productId <= 0) return;
    setButtonBusy(submit, true);
    try {
      await requestJson('/api/operations/products/' + encodeURIComponent(commerceId) + '/link', {method: 'PUT', body: JSON.stringify({product_id: productId})}, '商品关联失败。');
      productDialog.close();
      notify('商品关联已保存。', 'success');
      loadDataTab('products');
    } catch (error) {
      if (!error.isAuthRedirect) productDialog.querySelector('[data-product-dialog-status]').textContent = error.message;
    } finally {
      setButtonBusy(submit, false);
    }
  }

  async function unlinkProduct(button) {
    setButtonBusy(button, true);
    try {
      await requestJson('/api/operations/products/' + encodeURIComponent(button.dataset.productId) + '/link', {method: 'DELETE'}, '解除商品关联失败。');
      productDialog.close();
      notify('商品关联已解除。', 'success');
      loadDataTab('products');
    } catch (error) {
      if (!error.isAuthRedirect) productDialog.querySelector('[data-product-dialog-status]').textContent = error.message;
    } finally {
      setButtonBusy(button, false);
    }
  }

  function bindFilters() {
    document.querySelectorAll('[data-filter-form]').forEach(function (form) {
      var name = form.dataset.panel;
      pageState[name] = {page: 1, totalPages: 1};
      form.addEventListener('submit', function (event) { event.preventDefault(); });
      form.addEventListener('change', function (event) {
        pageState[name].page = 1;
        if (event.target.name === 'provider') populateSelects(form);
        if (activeTab === name) loadDataTab(name);
      });
      form.addEventListener('reset', function () {
        window.setTimeout(function () {
          pageState[name].page = 1;
          populateSelects(form);
          if (activeTab === name) loadDataTab(name);
        }, 0);
      });
      form.querySelectorAll('[data-export]').forEach(function (button) { button.addEventListener('click', function () { startExport(name, button); }); });
    });
  }

  center.addEventListener('click', function (event) {
    var pageButton = event.target.closest('[data-page]');
    if (pageButton) {
      var name = pageButton.closest('[role="tabpanel"]').id.replace('panel-', '');
      pageState[name].page += pageButton.dataset.page === 'next' ? 1 : -1;
      loadDataTab(name);
      return;
    }
    var productButton = event.target.closest('[data-product-link]');
    if (productButton) openProductDialog(productButton);
  });

  async function refreshAll() {
    var button = document.getElementById('operationsRefresh');
    setButtonBusy(button, true);
    try {
      await refreshFilterOptions();
      await loadDataTab(activeTab);
    } catch (error) {
      if (!error.isAuthRedirect) {
        showPanelState(panelFor(activeTab), 'error', error.message);
        notify(error.message);
      }
    } finally {
      setButtonBusy(button, false);
      if (window.lucide) window.lucide.createIcons();
    }
  }

  bindFilters();
  document.getElementById('operationsRefresh').addEventListener('click', refreshAll);
  document.querySelectorAll('[data-export-download]').forEach(function (link) { link.addEventListener('click', downloadExport); });
  productDialog.querySelector('[data-product-search]').addEventListener('click', function (event) { searchInternalProducts(event.currentTarget); });
  productDialog.querySelector('[data-product-unlink]').addEventListener('click', function (event) { unlinkProduct(event.currentTarget); });
  productForm.addEventListener('submit', submitProductLink);
  productDialog.querySelectorAll('[data-dialog-close]').forEach(function (button) { button.addEventListener('click', function () { productDialog.close(); }); });
  window.addEventListener('beforeunload', function () { abortActiveRequest(); clearExportPolling(); });

  activateTab(activeTab, {history: false, load: false});
  refreshAll();
  if (window.lucide) window.lucide.createIcons();
})();
