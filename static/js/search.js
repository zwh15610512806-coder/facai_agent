// ====== State ======
let currentPage = 1, totalPages = 1, pageSize = 15, totalResults = 0, aiSearchQuery = '';
let currentFilters = { q:'', type:'', ext:'', date_from:'', date_to:'', folder_id:'' };
let _prevFilters = null, _prevAiQuery = '', _prevPage = 1;

const $ = id => document.getElementById(id);
const request = window.FacaiUI && window.FacaiUI.fetchWithTimeout
  ? window.FacaiUI.fetchWithTimeout
  : ((input, init) => fetch(input, init));

// ====== Toast ======
function toast(msg, ok) {
  const t = $('toast');
  t.className = 'toast show toast-' + (ok ? 'ok' : 'err');
  t.textContent = msg;
  setTimeout(() => t.classList.remove('show'), 2800);
}
function fallbackCopyText(text){return new Promise(function(resolve,reject){var ta=document.createElement('textarea');ta.value=String(text||'');ta.setAttribute('readonly','');ta.style.position='fixed';ta.style.left='-9999px';ta.style.top='0';document.body.appendChild(ta);ta.focus();ta.select();ta.setSelectionRange(0,ta.value.length);try{var ok=document.execCommand('copy');document.body.removeChild(ta);ok?resolve():reject(new Error('copy rejected'));}catch(e){document.body.removeChild(ta);reject(e);}});}
function copyText(text){text=String(text||'');if(!text)return Promise.reject(new Error('empty'));return fallbackCopyText(text).catch(function(err){if(navigator.clipboard&&window.isSecureContext){return navigator.clipboard.writeText(text);}throw err;});}
function renderIcons(){ if(window.lucide) lucide.createIcons(); }

// ====== Index ======
async function fetchIndexStatus() {
  try {
    const r = await request('/api/search-proxy/index/status');
    const d = await r.json();
    if (d.success) {
      if (d.is_indexing) {
        $('indexBadgeText').textContent = '索引中...';
        $('indexInfo').textContent = d.message || '正在更新文件索引';
        $('indexBadge').classList.add('updating');
        $('refreshIndexBtn').disabled = true;
        $('refreshIndexBtn').innerHTML = '<i data-lucide="loader-circle"></i>索引中...';
        $('totalFiles').textContent = d.total_files ? '已发现 ' + d.total_files.toLocaleString() + ' 文件' : '--';
        renderIcons();
        return;
      }
      $('refreshIndexBtn').disabled = false;
      $('refreshIndexBtn').innerHTML = '<i data-lucide="refresh-cw"></i>手动更新索引';
      const last = d.last_indexed;
      if (last) {
        const diff = (Date.now() - new Date(last).getTime()) / 36e5;
        let ago = diff < 1 ? Math.floor(diff * 60) + ' 分钟前'
                : diff < 24 ? Math.floor(diff) + ' 小时前'
                : new Date(last).toLocaleDateString('zh-CN');
        $('indexBadgeText').textContent = '已索引 ' + d.total_files.toLocaleString() + ' 个文件';
        $('indexInfo').textContent = '索引更新：' + ago;
        $('indexBadge').classList.remove('updating');
        $('totalFiles').textContent = '共 ' + d.total_files.toLocaleString() + ' 文件';
      } else {
        $('indexBadgeText').textContent = '尚未索引';
        $('indexInfo').textContent = '请先触发全量索引';
        $('indexBadge').classList.remove('updating');
      }
    }
  } catch(e) { console.error(e); }
}

async function triggerIndex() {
  const btn = $('refreshIndexBtn');
  btn.disabled = true; btn.innerHTML = '<i data-lucide="loader-circle"></i>索引中...'; renderIcons();
  $('indexBadge').classList.add('updating');
  $('indexBadgeText').textContent = '正在更新...';
  try {
    const r = await request('/api/search-proxy/index/start', { method: 'POST' });
    const d = await r.json();
    toast(d.success ? '索引已在后台启动' : (d.message || '启动失败'), d.success);
    setTimeout(() => { btn.disabled = false; btn.innerHTML = '<i data-lucide="refresh-cw"></i>手动更新索引'; renderIcons(); fetchIndexStatus(); }, 3000);
  } catch(e) { toast('网络错误', false); btn.disabled = false; btn.innerHTML = '<i data-lucide="refresh-cw"></i>手动更新索引'; renderIcons(); }
}

fetchIndexStatus();
setInterval(fetchIndexStatus, 5 * 60 * 1000);

// ====== Icons & Format ======
function fileIcon(ft) {
  const m = { document:'📄', image:'🖼️', video:'🎬', audio:'🎵', archive:'📦', folder:'📁', other:'📄' };
  return m[ft] || m.other;
}
function iconClass(ft) {
  const m = { document:'fi-doc', image:'fi-img', video:'fi-vid', audio:'fi-aud', archive:'fi-arc', folder:'fi-folder' };
  return m[ft] || 'fi-other';
}
function fmtSize(b) {
  if (!b) return '0 B';
  const u = ['B','KB','MB','GB']; let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return b.toFixed(1) + ' ' + u[i];
}
function fmtDate(d) { return d ? new Date(d).toLocaleDateString('zh-CN') : '-'; }
function escHtml(v) { return String(v == null ? '' : v).replace(/[&<>"']/g, function(ch) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]; }); }
function escAttr(v) { return escHtml(v).replace(/`/g, '&#96;'); }
function jsStringLiteral(v) { return "'" + String(v == null ? '' : v).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\x22').replace(/</g, '\\x3C').replace(/>/g, '\\x3E').replace(/&/g, '\\x26').replace(/\r/g, '\\r').replace(/\n/g, '\\n').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029') + "'"; }

// ====== Render ======
function renderFiles(files) {
  if (!files.length) {
    $('fileList').innerHTML = '<div class="empty-state"><div class="empty-icon">📭</div><div class="empty-title">未找到文件</div><div class="empty-text">尝试调整搜索条件或更换关键词</div></div>';
    $('summaryBtn').style.display = 'none';
    return;
  }
  $('fileList').innerHTML = files.map(f => {
    const isF = f.file_type === 'folder';
    const fileId = Number(f.id)||0;
    const folderNameArg = jsStringLiteral(f.file_name);
    const folderPathArg = jsStringLiteral(f.parent_folder||'');
    const typeArg = jsStringLiteral(f.file_type);
    const extArg = jsStringLiteral(f.file_extension||'');
    const ch = isF ? `onclick="filterByFolder(${fileId},${folderNameArg},${folderPathArg})" style="cursor:pointer"` : '';
    return `<div class="file-item${isF ? ' folder' : ''}" data-id="${fileId}" ${ch}>
      <div class="file-icon ${iconClass(f.file_type)}">${fileIcon(f.file_type)}</div>
      <div class="file-info">
        <div class="file-name" title="${escAttr(f.file_name)}">${escHtml(f.file_name)}</div>
        ${f.parent_folder ? `<div class="file-folder">📁 ${escHtml((f.parent_folder || '').replace(/,/g, ' › '))}</div>` : ''}
        <div class="file-meta">
          <span>📅 ${fmtDate(f.file_modified)}</span>
          ${isF ? '<span>📂 文件夹</span>' : `<span>💾 ${fmtSize(f.file_size)}</span><span>📎 ${escHtml((f.file_extension || '').toUpperCase())}</span>`}
        </div>
      </div>
      <div class="file-actions">
        ${isF
          ? `<button class="act-btn pri" onclick="event.stopPropagation();filterByFolder(${fileId},${folderNameArg},${folderPathArg})"><i data-lucide="folder-open"></i>查看</button>`
          : `<button class="act-btn pri" onclick="event.stopPropagation();previewFile(${fileId},${typeArg},${extArg})"><i data-lucide="eye"></i>预览</button>
             <button class="act-btn" onclick="event.stopPropagation();downloadFile(${fileId})"><i data-lucide="download"></i>下载</button>`}
      </div>
    </div>`;
  }).join('');
  $('summaryBtn').style.display = files.length > 0 ? 'flex' : 'none';
  renderIcons();
}

function renderPagination() {
  if (!totalResults) {
    $('bottomPagination').innerHTML = '';
    updateResultMeta(0, 0, 0);
    return;
  }
  totalPages = Math.max(1, totalPages);
  const start = (currentPage - 1) * pageSize + 1;
  const end = Math.min(totalResults, currentPage * pageSize);
  updateResultMeta(start, end, totalResults);

  let bottom = '';
  bottom += `<button class="pager-btn"${currentPage <= 1 ? ' disabled' : ''} onclick="goToPage(${currentPage - 1})">‹</button>`;
  let last = 0;
  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || Math.abs(i - currentPage) <= 1) {
      if (i - last > 1) bottom += '<span class="pager-ellipsis">...</span>';
      bottom += `<button class="pager-btn${i === currentPage ? ' on' : ''}" onclick="goToPage(${i})">${i}</button>`;
      last = i;
    }
  }
  bottom += `<button class="pager-btn"${currentPage >= totalPages ? ' disabled' : ''} onclick="goToPage(${currentPage + 1})">›</button>`;
  bottom += `<span class="list-range">第 ${currentPage} / ${totalPages} 页，共 ${totalResults.toLocaleString()} 条</span>`;
  bottom += `<select id="pageSize" class="input" style="width:auto;font-size:13px" onchange="changePageSize(this.value)"><option value="15" ${pageSize===15?'selected':''}>15 条/页</option><option value="30" ${pageSize===30?'selected':''}>30 条/页</option><option value="60" ${pageSize===60?'selected':''}>60 条/页</option></select>`;
  bottom += `<span class="pager-jump"><span>跳至</span><input id="pageJumpInput" type="number" min="1" max="${totalPages}" value="${currentPage}" class="input pager-input" onkeydown="if(event.key==='Enter')jumpToPage()"><span>页</span><button class="pager-btn" onclick="jumpToPage()">跳转</button></span>`;

  $('bottomPagination').innerHTML = bottom;
}

function updateResultMeta(start, end, total) {
  $('resultRangeHint').textContent = total ? `第 ${start}-${end} 条 / 共 ${total.toLocaleString()} 条` : '当前没有结果';
}

function changePageSize(value) {
  pageSize = parseInt(value, 10) || 15;
  currentPage = 1;
  aiSearchQuery ? aiSearchPage(1) : searchFiles();
}

function jumpToPage() {
  const input = $('pageJumpInput');
  if (!input) return;
  const target = parseInt(input.value, 10);
  if (!target) return;
  goToPage(target);
}

// ====== Search ======
async function searchFiles() {
  aiSearchQuery = ''; $('aiBanner').classList.remove('show');
  const p = new URLSearchParams({ page: currentPage, per_page: pageSize });
  for (const [k, v] of Object.entries(currentFilters)) { if (v) p.set(k, v); }
  $('fileList').innerHTML = '<div class="loading-wrap"><div class="spin"></div></div>';
  try {
    const r = await request('/api/search-proxy/search?' + p);
    const d = await r.json();
    if (d.success) {
      renderFiles(d.files); totalPages = d.total_pages; totalResults = d.total || 0;
      $('resultsCount').innerHTML = `找到 <strong>${d.total}</strong> 个文件`;
      renderPagination();
    } else { toast(d.message || '搜索失败', false); }
  } catch(e) { toast('网络错误，请检查服务', false); }
}

async function aiSearch() {
  const q = $('searchInput').value.trim();
  if (!q) { toast('请先输入搜索内容', false); return; }
  $('searchBtn').disabled = true; $('searchBtn').innerHTML = '<i data-lucide="loader-circle"></i>理解中...'; renderIcons();
  $('aiBanner').classList.remove('show');
  $('fileList').innerHTML = '<div class="loading-wrap"><div class="spin"></div></div>';
  try {
    const r = await request('/api/search-proxy/ai-search', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, page: 1, per_page: pageSize })
    });
    const d = await r.json();
    if (d.success) {
      aiSearchQuery = q;
      const ai = d.ai_understanding || {};
      $('aiBannerSummary').textContent = ai.summary || '搜索: ' + q;
      const tags = [];
      if (ai.keywords) tags.push('<span class="ai-tag">🔑 ' + escHtml(ai.keywords.join('、')) + '</span>');
      if (ai.file_type) tags.push('<span class="ai-tag">📂 ' + escHtml(ai.file_type) + '</span>');
      if (ai.extension) tags.push('<span class="ai-tag">📄 .' + escHtml(ai.extension) + '</span>');
      if (ai.date_from) tags.push('<span class="ai-tag">📅 ' + escHtml(ai.date_from) + ' ~ ' + escHtml(ai.date_to || '今天') + '</span>');
      $('aiBannerTags').innerHTML = tags.join(''); $('aiBanner').classList.add('show');
      renderFiles(d.files); totalPages = d.total_pages; totalResults = d.total || 0;
      $('resultsCount').innerHTML = 'AI 找到 <strong>' + d.total + '</strong> 个匹配文件';
      renderPagination();
    } else { toast(d.message || 'AI 搜索失败', false); }
  } catch(e) { toast('网络错误', false); }
  finally { $('searchBtn').disabled = false; $('searchBtn').innerHTML = '<i data-lucide="sparkles"></i>AI 搜索'; renderIcons(); }
}

async function aiSearchPage(page) {
  $('fileList').innerHTML = '<div class="loading-wrap"><div class="spin"></div></div>';
  try {
    const r = await request('/api/search-proxy/ai-search', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: aiSearchQuery, page, per_page: pageSize })
    });
    const d = await r.json();
    if (d.success) {
      const ai = d.ai_understanding || {};
      $('aiBannerSummary').textContent = ai.summary || '搜索: ' + aiSearchQuery;
      const tags = [];
      if (ai.keywords) tags.push('<span class="ai-tag">🔑 ' + escHtml(ai.keywords.join('、')) + '</span>');
      if (ai.file_type) tags.push('<span class="ai-tag">📂 ' + escHtml(ai.file_type) + '</span>');
      if (ai.extension) tags.push('<span class="ai-tag">📄 .' + escHtml(ai.extension) + '</span>');
      if (ai.date_from) tags.push('<span class="ai-tag">📅 ' + escHtml(ai.date_from) + ' ~ ' + escHtml(ai.date_to || '今天') + '</span>');
      $('aiBannerTags').innerHTML = tags.join(''); $('aiBanner').classList.add('show');
      renderFiles(d.files); totalPages = d.total_pages; totalResults = d.total || 0;
      $('resultsCount').innerHTML = 'AI 找到 <strong>' + d.total + '</strong> 个匹配文件';
      renderPagination();
    }
  } catch(e) { toast('网络错误', false); }
}

function goToPage(p) {
  if (p < 1 || p > totalPages) return;
  currentPage = p;
  aiSearchQuery ? aiSearchPage(p) : searchFiles();
  const board = document.querySelector('.search-board');
  if (board) window.scrollTo({ top: Math.max(0, board.offsetTop - 84), behavior: 'smooth' });
}

// ====== Folder nav ======
function filterByFolder(fileId, folderName, parentLabel) {
  _prevFilters = { ...currentFilters }; _prevAiQuery = aiSearchQuery; _prevPage = currentPage;
  currentFilters = { q:'', type:'', ext:'', date_from:'', date_to:'', folder_id:fileId };
  currentPage = 1; aiSearchQuery = ''; $('aiBanner').classList.remove('show');
  $('folderBreadcrumbPath').textContent = String(parentLabel||'').replace(/,/g,' › ');
  $('folderBreadcrumbName').textContent = folderName||'文件夹';
  $('folderBreadcrumb').classList.add('show');
  searchFiles();
}

function closeFolderView() {
  if (_prevFilters) {
    currentFilters = { ..._prevFilters }; aiSearchQuery = _prevAiQuery; currentPage = _prevPage;
  } else {
    currentFilters = { q:'', type:'', ext:'', date_from:'', date_to:'', folder_id:'' };
    aiSearchQuery = ''; currentPage = 1;
  }
  $('folderBreadcrumb').classList.remove('show');
  _prevFilters = null;
  if (aiSearchQuery) aiSearchPage(currentPage);
  else if (currentFilters.q || currentFilters.type || currentFilters.ext || currentFilters.date_from || currentFilters.date_to) searchFiles();
  else { $('fileList').innerHTML = '<div class="empty-state"><div class="empty-icon">🔍</div><div class="empty-title">开始搜索文件</div><div class="empty-text">在搜索框中输入关键词，即可查找局域网内的文件</div></div>'; $('resultsCount').innerHTML = '找到 <strong>0</strong> 个文件'; totalResults = 0; renderPagination(); $('summaryBtn').style.display = 'none'; }
}

// ====== Preview ======
async function previewFile(id, ft, ext) {
  try {
    const r = await request('/api/search-proxy/files/' + id);
    const d = await r.json();
    if (!d.success) { toast(d.message || '获取失败', false); return; }
    const f = d.file;
    $('modalTitle').textContent = f.file_name;
    const pu = '/api/search-proxy/files/' + id + '/preview';
    if (ft === 'image') $('modalBody').innerHTML = '<img src="' + pu + '" class="img-preview" alt="' + escAttr(f.file_name) + '">';
    else if (ft === 'video') $('modalBody').innerHTML = '<video class="vid-preview" controls preload="metadata"><source src="' + pu + '" type="video/mp4"></video>';
    else if (ft === 'audio') $('modalBody').innerHTML = '<audio controls preload="metadata" style="width:100%;margin:20px"><source src="' + pu + '" type="audio/mpeg"></audio>';
    else if (ft === 'document' && ext === 'pdf') $('modalBody').innerHTML = '<iframe src="' + pu + '" class="pdf-preview"></iframe>';
    else $('modalBody').innerHTML = '<div style="text-align:center;padding:40px"><p style="margin-bottom:12px;color:var(--text-2)">该文件类型不支持在线预览</p><button class="act-btn pri" onclick="downloadFile(' + id + ')"><i data-lucide="download"></i>下载文件</button></div>';
    $('previewModal').classList.add('show');
    const media = $('modalBody').querySelector('video,audio');
    if (media) media.load();
    renderIcons();
  } catch(e) { toast('预览失败', false); }
}

function downloadFile(id) { window.open('/api/search-proxy/files/' + id + '/download', '_blank'); }

// ====== Summary ======
async function generateSummary() {
  const btn = $('summaryBtn');
  btn.disabled = true; btn.innerHTML = '<i data-lucide="loader-circle"></i>正在整理...'; renderIcons();
  $('summaryModal').classList.add('show');
  $('summaryBody').innerHTML = '<div class="loading-wrap"><div class="spin"></div><p style="margin-top:8px;color:var(--text-3)">AI 正在分析搜索结果...</p></div>';
  try {
    const r = await request('/api/search-proxy/search-summary', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: currentFilters.q, file_type: currentFilters.type, extension: currentFilters.ext, date_from: currentFilters.date_from, date_to: currentFilters.date_to })
    });
    const d = await r.json();
    if (d.success) $('summaryBody').innerHTML = simpleMD(escHtml(d.summary));
    else $('summaryBody').innerHTML = '<div class="empty-state"><div class="empty-title">' + escHtml(d.message||'生成失败') + '</div></div>';
  } catch(e) { $('summaryBody').innerHTML = '<div class="empty-state"><div class="empty-title">网络错误</div></div>'; }
  finally { btn.disabled = false; btn.innerHTML = '<i data-lucide="bot"></i>AI 整理汇总'; renderIcons(); }
}

function closeSummary() { $('summaryModal').classList.remove('show'); }
function copySummary() {
  const t = $('summaryBody').innerText;
  copyText(t).then(() => toast('已成功复制到剪贴板', true)).catch(() => toast('复制失败，请手动选中文案复制', false));
}

function simpleMD(md) {
  let h = md;
  h = h.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  h = h.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  h = h.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  h = h.replace(/^- (.+)$/gm, '<li>$1</li>');
  h = h.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  h = h.replace(/`(.+?)`/g, '<code>$1</code>');
  h = h.replace(/\n\n/g, '</p><p>');
  h = h.replace(/\n/g, '<br>');
  h = '<p>' + h + '</p>';
  h = h.replace(/<p><\/p>/g, '').replace(/<p><br><\/p>/g, '');
  return h;
}

// ====== Events ======
$('searchBtn').addEventListener('click', () => { currentPage = 1; aiSearch(); });
$('keywordBtn').addEventListener('click', () => { currentFilters.q = $('searchInput').value.trim(); currentPage = 1; aiSearchQuery = ''; searchFiles(); });
$('searchInput').addEventListener('keypress', e => { if (e.key === 'Enter') $('searchBtn').click(); });
$('modalClose').addEventListener('click', () => $('previewModal').classList.remove('show'));
$('previewModal').addEventListener('click', e => { if (e.target === $('previewModal')) $('previewModal').classList.remove('show'); });
$('folderBackBtn').addEventListener('click', closeFolderView);

// 类型筛选
$('typeFilters').addEventListener('click', e => {
  const chip = e.target.closest('.fchip');
  if (!chip) return;
  $('typeFilters').querySelectorAll('.fchip').forEach(c => c.classList.remove('on'));
  chip.classList.add('on');
  currentFilters.type = chip.dataset.type;
  currentPage = 1; searchFiles();
});

// 扩展名
$('extensionFilter').addEventListener('change', e => { currentFilters.ext = e.target.value.trim(); currentPage = 1; searchFiles(); });
$('extensionFilter').addEventListener('keypress', e => { if (e.key === 'Enter') { currentFilters.ext = e.target.value.trim(); currentPage = 1; searchFiles(); } });

// 日期
$('dateFrom').addEventListener('change', e => { currentFilters.date_from = e.target.value; currentPage = 1; searchFiles(); });
$('dateTo').addEventListener('change', e => { currentFilters.date_to = e.target.value; currentPage = 1; searchFiles(); });

// 清除筛选
$('clearFiltersBtn').addEventListener('click', () => {
  $('searchInput').value = ''; $('extensionFilter').value = '';
  $('dateFrom').value = ''; $('dateTo').value = '';
  $('typeFilters').querySelectorAll('.fchip').forEach(c => c.classList.remove('on'));
  $('typeFilters').querySelector('.fchip[data-type=""]').classList.add('on');
  aiSearchQuery = ''; $('aiBanner').classList.remove('show');
  $('folderBreadcrumb').classList.remove('show');
  currentFilters = { q:'', type:'', ext:'', date_from:'', date_to:'', folder_id:'' };
  currentPage = 1;
  $('fileList').innerHTML = '<div class="empty-state"><div class="empty-icon">🔍</div><div class="empty-title">开始搜索文件</div><div class="empty-text">在搜索框中输入关键词，即可查找局域网内的文件</div></div>';
  $('resultsCount').innerHTML = '找到 <strong>0</strong> 个文件';
  totalResults = 0; renderPagination(); $('summaryBtn').style.display = 'none';
});

// 摘要模态背景点击关闭
$('summaryModal').addEventListener('click', e => { if (e.target === $('summaryModal')) closeSummary(); });
document.addEventListener('DOMContentLoaded', renderIcons);
