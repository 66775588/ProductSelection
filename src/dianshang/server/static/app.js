/* ═══════════════════════════════════════════════════════════
   选品调研 Agent — 前端逻辑
   深色仪表盘 · 5 Tab · API 凭证管理
   ═══════════════════════════════════════════════════════════ */

// ── 常量 ──────────────────────────────────────────────────
const NODE_LABELS = {
  task_decompose: '任务拆解', data_fetch: '数据抓取', data_clean: '数据清洗',
  analyze: '痛点分析', profit_calc: '利润测算', risk_check: '风险排查',
  score: '综合评分', report: '报告生成', memory_save: '记忆存储',
};
const NODE_ORDER = Object.keys(NODE_LABELS);
const WEIGHT_KEYS = [
  ['market_potential', '市场潜力'], ['competition', '竞争程度'],
  ['profit', '盈利空间'], ['pain_points', '用户痛点'], ['risk', '风险等级'],
];
const PLATFORM_LABELS = { pdd: '拼多多', taobao: '淘宝', tmall: '天猫', jd: '京东' };
const REC_COLORS = { '强烈推荐': '#10b981', '可尝试': '#22d3ee', '谨慎进入': '#f59e0b', '不推荐': '#ef4444' };

function badgeClass(rec) {
  return { '强烈推荐': 'b-strong', '可尝试': 'b-try', '谨慎进入': 'b-cautious', '不推荐': 'b-no' }[rec] || 'b-no';
}
function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

// ── Tab 切换 ──────────────────────────────────────────────
const tabs = document.querySelectorAll('.tab');
const panels = document.querySelectorAll('.panel');
tabs.forEach(t => t.addEventListener('click', () => {
  tabs.forEach(x => x.classList.remove('active'));
  panels.forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('tab-' + t.dataset.tab).classList.add('active');
  if (t.dataset.tab === 'dashboard') loadDashboard();
  if (t.dataset.tab === 'history') loadHistory();
  if (t.dataset.tab === 'config') loadConfig();
}));

// ── 平台选择器 ────────────────────────────────────────────
document.querySelectorAll('.platform-card').forEach(card => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.platform-card').forEach(c => c.classList.remove('selected'));
    card.classList.add('selected');
    card.querySelector('input[type="radio"]').checked = true;
  });
});

// ── 高级权重滑块 ──────────────────────────────────────────
let weightState = { market_potential: 0.30, competition: 0.20, profit: 0.25, pain_points: 0.15, risk: 0.10 };

function renderSliders(container, state, sumEl) {
  container.innerHTML = '';
  WEIGHT_KEYS.forEach(([k, label]) => {
    const row = document.createElement('div');
    row.className = 'weight-slider-row';
    row.innerHTML = `<label>${label}</label>
      <input type="range" min="0" max="100" value="${(state[k]*100).toFixed(0)}" data-k="${k}">
      <span class="slider-val">${(state[k]*100).toFixed(0)}%</span>`;
    row.querySelector('input').addEventListener('input', e => {
      state[k] = +e.target.value / 100;
      row.querySelector('.slider-val').textContent = e.target.value + '%';
      sumEl.querySelector('b').textContent = (Object.values(state).reduce((a,b)=>a+b,0)*100).toFixed(0) + '%';
    });
    container.appendChild(row);
  });
  sumEl.querySelector('b').textContent = (Object.values(state).reduce((a,b)=>a+b,0)*100).toFixed(0) + '%';
}

renderSliders(document.getElementById('weight-sliders'), weightState, document.getElementById('weight-sum'));
const _saved = localStorage.getItem('adv-weights');
if (_saved) { try { Object.assign(weightState, JSON.parse(_saved)); renderSliders(document.getElementById('weight-sliders'), weightState, document.getElementById('weight-sum')); } catch {} }

// ── 新建调研 ──────────────────────────────────────────────
let pollTimer = null;

document.getElementById('research-form').addEventListener('submit', async e => {
  e.preventDefault();
  const category = document.getElementById('f-category').value.trim();
  const platform = document.querySelector('input[name="platform"]:checked').value;
  const forceMock = document.getElementById('f-force-mock').checked;
  const wsum = Object.values(weightState).reduce((a,b)=>a+b,0) * 100;
  if (wsum > 0 && Math.abs(wsum - 100) > 1) {
    alert('权重之和必须为 100%（当前 ' + wsum.toFixed(0) + '%）');
    return;
  }
  const overrides = { crawl: { force_mock: forceMock } };
  if (wsum > 0) overrides.scoring_weights = { ...weightState };

  const r = await fetch('/api/research', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, platform, overrides }),
  });
  if (r.status === 409) { alert('已有任务运行中，请先完成或取消'); return; }
  const { job_id } = await r.json();
  document.getElementById('progress-status-text').textContent = '正在运行…';
  document.getElementById('result').innerHTML = '';
  pollJob(job_id);
});

function renderStepper(completed, current, stale) {
  const el = document.getElementById('stepper');
  el.innerHTML = '<div class="stepper">' + NODE_ORDER.map(n => {
    const cls = completed.includes(n) ? 'done' : (n === current ? 'current' : 'pending');
    return `<div class="step ${cls}"><span class="dot"></span>${NODE_LABELS[n]}</div>`;
  }).join('') + '</div>' + (stale ? '<p class="warn">任务可能已中断（服务重启），可取消重跑。</p>' : '');
}

function pollJob(jobId) {
  if (pollTimer) clearInterval(pollTimer);
  const tick = async () => {
    const st = await (await fetch(`/api/jobs/${jobId}`)).json();
    renderStepper(st.completed_nodes || [], st.current_node, st.stale);
    if (st.status === 'done') {
      clearInterval(pollTimer); pollTimer = null;
      document.getElementById('progress-status-text').textContent = '已完成';
      renderResult(st.result);
    } else if (st.status === 'error') {
      clearInterval(pollTimer); pollTimer = null;
      document.getElementById('progress-status-text').textContent = '失败';
      document.getElementById('result').innerHTML = `<p class="warn">失败: ${esc(st.error)}</p>`;
    }
  };
  tick();
  pollTimer = setInterval(tick, 1000);
}

function renderResult(res) {
  if (!res) return;
  const dl = Object.entries(res.report_paths || {}).map(
    ([k, p]) => `<a href="/api/reports/${encodeURIComponent(p.split(/[/\\]/).pop())}" target="_blank"><button>下载 ${k.toUpperCase()}</button></a>`
  ).join(' ');
  const scores = Object.entries(res.scores || {}).map(([k, v]) => {
    const label = Object.fromEntries(WEIGHT_KEYS)[k] || k;
    return `<div>${label}: ${v}<div class="score-bar"><i style="width:${v}%"></i></div></div>`;
  }).join('');
  const pains = (res.pain_points || []).map(p => `<li>${esc(p.keyword||p.point||'')} (频次 ${p.frequency??'—'}, 严重度 ${p.severity??'—'})</li>`).join('');
  const risks = (res.risk_items || []).map(r => `<li>[${esc(r.level||'')}] ${esc(r.type||'')}: ${esc(r.desc||'')}</li>`).join('');
  const prov = Object.entries(res.data_provenance || {}).map(([k,v]) => `${esc(k)}: ${esc(v)}`).join('；');
  const competitors = (res.competitors || []).map(c =>
    `<tr>
      <td>${c.rank}</td>
      <td>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none">${esc(c.title)}</a>` : esc(c.title)}</td>
      <td>¥${c.price}</td>
      <td>${c.sales}</td>
      <td>${esc(c.shop_name)}</td>
    </tr>`
  ).join('');
  const compTable = competitors ? `
    <h3>TOP 竞品 <span style="font-weight:400;font-size:0.8rem;color:var(--text-dim)">(${(res.competitors||[]).length} 个)</span></h3>
    <div class="table-wrap"><table class="comp-table">
      <thead><tr><th>#</th><th>商品</th><th>价格</th><th>销量</th><th>店铺</th></tr></thead>
      <tbody>${competitors}</tbody>
    </table></div>` : '';
  document.getElementById('result').innerHTML = `
    <h2>${esc(res.category)} <span class="badge ${badgeClass(res.recommendation)}">${esc(res.recommendation)}</span></h2>
    <p>综合得分 <b style="color:var(--accent);font-size:1.2rem">${res.total_score}</b> — ${esc(res.recommendation_reason||'')}</p>
    ${res.red_line_hit ? '<p class="warn">⚠ 命中红线规则</p>' : ''}
    <h3>五维评分</h3>${scores}
    <h3>利润</h3><p>售价 ¥${res.profit?.selling_price??'—'} · 毛利率 ${res.profit?.gross_margin??'—'}% · 回本 ${res.profit?.payback_months??'—'} 月 · 盈亏平衡 ${res.profit?.break_even_units??'—'} 件/月</p>
    ${compTable}
    <h3>TOP5 痛点</h3><ul>${pains}</ul>
    <h3>风险 (${(res.risk_items||[]).length})</h3><ul>${risks}</ul>
    <p class="warn">数据来源: ${prov||'—'}</p>
    ${(res.errors||[]).length ? `<p class="warn">错误: ${res.errors.map(e=>esc(e)).join('; ')}</p>` : ''}
    <div>${dl}</div>`;
}

// ── 仪表盘 ────────────────────────────────────────────────
async function loadDashboard() {
  const r = await (await fetch('/api/history?limit=200&offset=0')).json();
  const items = r.items || [];
  // stats
  const total = items.length;
  const strong = items.filter(i => i.recommendation === '强烈推荐').length;
  const scores = items.map(i => i.total_score).filter(Boolean);
  const avgScore = scores.length ? (scores.reduce((a,b)=>a+b,0)/scores.length).toFixed(1) : '—';
  const platforms = new Set(items.map(i => i.platform)).size || '—';
  const redline = items.filter(i => i.red_line_hit).length;
  const margins = items.map(i => i.gross_margin).filter(Boolean);
  const avgMargin = margins.length ? (margins.reduce((a,b)=>a+b,0)/margins.length).toFixed(1) + '%' : '—';

  document.getElementById('stat-total').textContent = total;
  document.getElementById('stat-strong').textContent = strong;
  document.getElementById('stat-avg-score').textContent = avgScore;
  document.getElementById('stat-platforms').textContent = platforms;
  document.getElementById('stat-redline').textContent = redline;
  document.getElementById('stat-avg-margin').textContent = avgMargin;

  // recommendation distribution
  const recDist = {};
  ['强烈推荐','可尝试','谨慎进入','不推荐'].forEach(r => recDist[r] = 0);
  items.forEach(i => { if (recDist[i.recommendation] !== undefined) recDist[i.recommendation]++; });
  const maxRec = Math.max(1, ...Object.values(recDist));
  document.getElementById('dist-recommendation').innerHTML = Object.entries(recDist).map(([rec, cnt]) => `
    <div class="dist-row">
      <span class="dist-label">${rec}</span>
      <div class="dist-bar-wrap"><div class="dist-bar-fill" style="width:${(cnt/maxRec*100).toFixed(0)}%;background:${REC_COLORS[rec]}"></div></div>
      <span class="dist-count">${cnt}</span>
    </div>`).join('');

  // credential mini status
  try {
    const cred = await (await fetch('/api/credentials')).json();
    document.getElementById('cred-stats-mini').innerHTML = Object.entries(cred).map(([k, v]) => `
      <div class="cred-mini-row">
        <span>${esc(v.label)}</span>
        <span class="cred-dot ${v.configured ? 'on' : 'off'}"></span>
      </div>`).join('');
  } catch { document.getElementById('cred-stats-mini').innerHTML = '<span style="color:var(--text-dim)">加载失败</span>'; }
}

// ── 历史记录 ──────────────────────────────────────────────
let page = 0; const PAGE_SIZE = 20;

async function loadHistory() {
  const search = document.getElementById('history-search')?.value || '';
  const platformFilter = document.getElementById('history-platform-filter')?.value || '';
  const r = await (await fetch(`/api/history?limit=${PAGE_SIZE}&offset=${page*PAGE_SIZE}`)).json();
  let items = r.items || [];
  // client-side filter
  if (search) items = items.filter(i => i.category.toLowerCase().includes(search.toLowerCase()));
  if (platformFilter) items = items.filter(i => i.platform === platformFilter);
  const tb = document.querySelector('#history-table tbody');
  tb.innerHTML = items.map(it => `<tr>
    <td>${esc(it.category)}</td><td>${esc(PLATFORM_LABELS[it.platform] || it.platform)}</td>
    <td><span class="badge ${badgeClass(it.recommendation)}">${esc(it.recommendation||'')}</span></td>
    <td>${it.total_score??''}</td><td>${it.gross_margin??''}</td>
    <td>${it.red_line_hit ? '<span style="color:var(--red)">是</span>' : ''}</td>
    <td>${esc((it.created_at||'').slice(0,16))}</td>
    <td><button class="btn-ghost" onclick="showDetail(${it.id})" style="padding:4px 10px;font-size:0.75rem">查看</button></td>
  </tr>`).join('');
  document.getElementById('page-info').textContent = `第 ${page+1} 页 / 共 ${r.total} 条`;
  document.getElementById('prev-page').disabled = page === 0;
  document.getElementById('next-page').disabled = items.length < PAGE_SIZE;
}

document.getElementById('prev-page').onclick = () => { if (page>0){page--; loadHistory();} };
document.getElementById('next-page').onclick = () => { page++; loadHistory(); };

// 搜索/筛选绑定
document.getElementById('history-search').addEventListener('input', () => { page = 0; loadHistory(); });
document.getElementById('history-platform-filter').addEventListener('change', () => { page = 0; loadHistory(); });

// ── 详情 ──────────────────────────────────────────────────
window.showDetail = async function(id) {
  const d = await (await fetch(`/api/history/${id}`)).json();
  const sj = d.state_json || {};
  const dl = Object.entries(d.report_paths || {}).map(
    ([k, p]) => `<a href="/api/reports/${encodeURIComponent((p||'').split(/[/\\]/).pop())}" target="_blank"><button>下载 ${k.toUpperCase()}</button></a>`
  ).join(' ');
  const scores = Object.entries(sj.scores || {}).map(([k,v]) => {
    const label = Object.fromEntries(WEIGHT_KEYS)[k] || k;
    return `<div>${label}: ${v}<div class="score-bar"><i style="width:${v}%"></i></div></div>`;
  }).join('');
  const pains = (sj.pain_points||[]).map(p => `<li>${esc(p.keyword||p.point||'')}</li>`).join('');
  const risks = (sj.risk_items||[]).map(r => `<li>[${esc(r.level||'')}] ${esc(r.type||'')}: ${esc(r.desc||'')}</li>`).join('');
  const histComp = (sj.competitors || []).map(c =>
    `<tr>
      <td>${c.rank}</td>
      <td>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none">${esc(c.title)}</a>` : esc(c.title)}</td>
      <td>¥${c.price}</td>
      <td>${c.sales}</td>
      <td>${esc(c.shop_name)}</td>
    </tr>`
  ).join('');
  const histCompTable = histComp ? `
    <h3 style="color:var(--text-dim);margin:16px 0 8px">TOP 竞品 <span style="font-weight:400;font-size:0.8rem">(${(sj.competitors||[]).length} 个)</span></h3>
    <div class="table-wrap"><table class="comp-table">
      <thead><tr><th>#</th><th>商品</th><th>价格</th><th>销量</th><th>店铺</th></tr></thead>
      <tbody>${histComp}</tbody>
    </table></div>` : '';
  document.getElementById('detail-content').innerHTML = `
    <h2>${esc(d.category)} <span class="badge ${badgeClass(d.recommendation)}">${esc(d.recommendation)}</span></h2>
    <p style="font-size:1.1rem;margin:8px 0">综合得分 <b style="color:var(--accent);font-size:1.3rem">${d.total_score}</b> · 毛利率 ${d.gross_margin??'—'}%</p>
    <h3 style="color:var(--text-dim);margin:16px 0 8px">五维评分</h3>${scores}
    ${histCompTable}
    <h3 style="color:var(--text-dim);margin:16px 0 8px">TOP5 痛点</h3><ul>${pains||'<li style="color:var(--text-dim)">无数据</li>'}</ul>
    <h3 style="color:var(--text-dim);margin:16px 0 8px">风险</h3><ul>${risks||'<li style="color:var(--text-dim)">无数据</li>'}</ul>
    <div style="margin-top:16px">${dl}</div>`;
  document.querySelector('[data-tab="detail"]').click();
};

// ── 设置 ──────────────────────────────────────────────────
let cfgState = null;

async function loadConfig() {
  cfgState = await (await fetch('/api/config')).json();
  // weights
  const wEl = document.getElementById('cfg-weights');
  wEl.innerHTML = '';
  WEIGHT_KEYS.forEach(([k, label]) => {
    const row = document.createElement('div');
    row.className = 'weight-slider-row';
    row.innerHTML = `<label>${label}</label>
      <input type="range" min="0" max="100" value="${(cfgState.scoring_weights[k]*100).toFixed(0)}" data-k="${k}">
      <span class="slider-val">${(cfgState.scoring_weights[k]*100).toFixed(0)}%</span>`;
    row.querySelector('input').addEventListener('input', e => {
      cfgState.scoring_weights[k] = +e.target.value / 100;
      row.querySelector('.slider-val').textContent = e.target.value + '%';
      updateCfgSum();
    });
    wEl.appendChild(row);
  });
  updateCfgSum();

  // profit params
  const pEl = document.getElementById('cfg-profit');
  const P = [
    ['profit_threshold', '毛利率红线 %'], ['platform_commission_rate', '佣金率 (0-1)'],
    ['logistics_rate', '物流率 (0-1)'], ['promotion_rate', '推广率 (0-1)'],
    ['refund_loss_rate', '退款损耗率 (0-1)'], ['tax_rate', '税率 (0-1)'],
    ['packaging_cost', '包材 ¥'],
  ];
  pEl.innerHTML = P.map(([k, label]) =>
    `<label>${label} <input type="number" step="0.01" value="${cfgState.profit[k]}" data-k="${k}"></label>`
  ).join('');
  document.getElementById('cfg-force-mock').checked = cfgState.crawl.force_mock;

  // credentials
  await loadCredentialCards();
}

function updateCfgSum() {
  const sum = Object.values(cfgState.scoring_weights).reduce((a,b)=>a+b,0)*100;
  document.getElementById('cfg-weight-sum').querySelector('b').textContent = sum.toFixed(0) + '%';
}

// 保存评分+利润设置
document.getElementById('cfg-save-btn').addEventListener('click', async () => {
  const wsum = Object.values(cfgState.scoring_weights).reduce((a,b)=>a+b,0) * 100;
  if (Math.abs(wsum - 100) > 1) {
    document.getElementById('cfg-status').textContent = '权重之和必须为 100%（当前 ' + wsum.toFixed(0) + '%）';
    return;
  }
  const payload = {
    scoring_weights: cfgState.scoring_weights,
    profit: Object.fromEntries([...document.querySelectorAll('#cfg-profit input')].map(i => [i.dataset.k, +i.value])),
    crawl: { force_mock: document.getElementById('cfg-force-mock').checked },
  };
  localStorage.setItem('adv-weights', JSON.stringify(weightState));
  const r = await fetch('/api/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  document.getElementById('cfg-status').textContent = r.ok ? '已保存' : '保存失败: ' + (await r.json()).error.message;
});

// ── API 凭证卡片 ──────────────────────────────────────────
const PLATFORM_META = {
  '1688': { label: '1688 开放平台', doc_url: 'https://open.1688.com', usage: '供应链货源价格查询' },
  'shengyican': { label: '生意参谋（淘宝/天猫）', doc_url: 'https://sycm.taobao.com', usage: '市场热度、搜索趋势、转化率数据' },
  'jd': { label: '京东商智', doc_url: 'https://sz.jd.com', usage: '京东平台市场数据' },
  'pdd': { label: '拼多多开放平台', doc_url: 'https://open.pinduoduo.com', usage: '拼多多平台市场数据' },
};
const FIELD_LABELS = {
  'alibaba_1688_app_key': 'AppKey', 'alibaba_1688_app_secret': 'AppSecret',
  'sheng_yi_can_token': 'Token', 'sheng_yi_can_cookie': 'Cookie',
  'jd_shangzhi_app_key': 'AppKey', 'jd_shangzhi_app_secret': 'AppSecret',
  'pdd_client_id': 'client_id', 'pdd_client_secret': 'client_secret',
};

let credentialData = {};
let editingPlatform = null;

async function loadCredentialCards() {
  try {
    credentialData = await (await fetch('/api/credentials')).json();
  } catch { credentialData = {}; }
  renderCredentialCards();
}

function renderCredentialCards() {
  const container = document.getElementById('credential-cards');
  container.innerHTML = Object.entries(credentialData).map(([key, val]) => {
    const meta = PLATFORM_META[key] || {};
    const statusClass = val.configured ? 'configured' : 'not-configured';
    const statusText = val.configured ? '已配置 ✓' : '未配置';
    const isEditing = editingPlatform === key;
    const fields = val.fields || {};
    return `<div class="cred-card">
      <div class="cred-card-header">
        <h4>🔗 ${esc(meta.label || key)}</h4>
        <span class="cred-status ${statusClass}">${statusText}</span>
      </div>
      <div class="cred-fields">
        ${Object.entries(fields).map(([fname, masked]) =>
          `<div class="cred-field-row">
            <span class="cred-field-label">${esc(FIELD_LABELS[fname] || fname)}</span>
            <span class="cred-field-value">${masked ? esc(masked) : '<span style="color:var(--text-dim)">（未设置）</span>'}</span>
          </div>`
        ).join('')}
      </div>
      <div class="cred-meta">
        <span>用途：${esc(meta.usage || '')}</span>
        ${meta.doc_url ? `<a href="${esc(meta.doc_url)}" target="_blank" rel="noopener">获取凭证 →</a>` : ''}
      </div>
      <div style="margin-top:10px;display:flex;gap:8px">
        <button class="btn-ghost" style="padding:4px 12px;font-size:0.78rem" onclick="toggleEditCredential('${key}')">
          ${isEditing ? '取消' : '修改'}
        </button>
        ${val.configured ? `<button class="btn-ghost" style="padding:4px 12px;font-size:0.78rem;color:var(--red)" onclick="deleteCredential('${key}')">清除</button>` : ''}
      </div>
      ${isEditing ? renderEditForm(key, fields) : ''}
    </div>`;
  }).join('');
}

function renderEditForm(key, fields) {
  return `<div class="cred-edit-form">
    ${Object.keys(fields).map(fname =>
      `<div class="form-group" style="margin-bottom:8px">
        <label>${esc(FIELD_LABELS[fname] || fname)}</label>
        <div style="display:flex;gap:8px">
          <input type="password" id="cred-input-${fname}" placeholder="输入新值（留空不变）" style="flex:1" />
          <button type="button" class="btn-ghost" style="padding:4px 10px;font-size:0.75rem"
            onclick="togglePassword('cred-input-${fname}')">👁</button>
        </div>
      </div>`
    ).join('')}
    <button class="btn-primary" style="font-size:0.82rem" onclick="saveCredential('${key}')">保存凭证</button>
  </div>`;
}

window.toggleEditCredential = function(key) {
  editingPlatform = editingPlatform === key ? null : key;
  renderCredentialCards();
};

window.togglePassword = function(inputId) {
  const el = document.getElementById(inputId);
  el.type = el.type === 'password' ? 'text' : 'password';
};

window.saveCredential = async function(key) {
  const fieldNames = Object.keys(credentialData[key].fields);
  const payload = {};
  payload[key] = {};
  let hasInput = false;
  for (const fname of fieldNames) {
    const input = document.getElementById('cred-input-' + fname);
    if (input && input.value.trim()) {
      payload[key][fname] = input.value.trim();
      hasInput = true;
    }
  }
  if (!hasInput) { editingPlatform = null; renderCredentialCards(); return; }
  try {
    const r = await fetch('/api/credentials', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (r.ok) {
      credentialData = await r.json();
      editingPlatform = null;
      renderCredentialCards();
    } else {
      alert('保存失败: ' + ((await r.json()).error?.message || '未知错误'));
    }
  } catch (e) { alert('网络错误: ' + e.message); }
};

window.deleteCredential = async function(key) {
  if (!confirm('确认清除 ' + (PLATFORM_META[key]?.label || key) + ' 的所有凭证？')) return;
  try {
    const r = await fetch('/api/credentials/' + key, { method: 'DELETE' });
    if (r.ok) {
      credentialData = await (await fetch('/api/credentials')).json();
      renderCredentialCards();
    }
  } catch (e) { alert('网络错误: ' + e.message); }
};
