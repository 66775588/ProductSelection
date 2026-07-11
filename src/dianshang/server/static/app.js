// tab 切换
const tabs = document.querySelectorAll('.tab');
const panels = document.querySelectorAll('.panel');
tabs.forEach(t => t.addEventListener('click', () => {
  tabs.forEach(x => x.classList.remove('active'));
  panels.forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('tab-' + t.dataset.tab).classList.add('active');
  if (t.dataset.tab === 'history') loadHistory();
  if (t.dataset.tab === 'config') loadConfig();
}));

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

function badgeClass(rec) {
  return { '强烈推荐': 'b-strong', '可尝试': 'b-try', '谨慎进入': 'b-cautious', '不推荐': 'b-no' }[rec] || 'b-no';
}

// —— 新建调研 ——
let weightState = { market_potential: 30, competition: 20, profit: 25, pain_points: 15, risk: 10 };
function renderSliders(container, state, sumEl) {
  container.innerHTML = '';
  WEIGHT_KEYS.forEach(([k, label]) => {
    const row = document.createElement('label');
    row.innerHTML = `${label} <input type="range" min="0" max="100" value="${state[k]*100}" data-k="${k}"> <span>${(state[k]*100).toFixed(0)}%</span>`;
    row.querySelector('input').addEventListener('input', e => {
      state[k] = +e.target.value / 100;
      row.querySelector('span').textContent = e.target.value + '%';
      sumEl.querySelector('b').textContent = (Object.values(state).reduce((a,b)=>a+b,0)*100).toFixed(0) + '%';
    });
    container.appendChild(row);
  });
  sumEl.querySelector('b').textContent = (Object.values(state).reduce((a,b)=>a+b,0)*100).toFixed(0) + '%';
}
renderSliders(document.getElementById('weight-sliders'), weightState, document.getElementById('weight-sum'));

let pollTimer = null;
document.getElementById('research-form').addEventListener('submit', async e => {
  e.preventDefault();
  const category = document.getElementById('f-category').value.trim();
  const platform = document.getElementById('f-platform').value;
  const forceMock = document.getElementById('f-force-mock').checked;
  const overrides = { crawl: { force_mock: forceMock } };
  if (Object.values(weightState).reduce((a,b)=>a+b,0) > 0) {
    overrides.scoring_weights = { ...weightState };
  }
  const r = await fetch('/api/research', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category, platform, overrides }),
  });
  if (r.status === 409) { alert('已有任务运行中，请先完成或取消'); return; }
  const { job_id } = await r.json();
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
    renderStepper(st.completed_nodes, st.current_node, st.stale);
    if (st.status === 'done') {
      clearInterval(pollTimer); pollTimer = null;
      renderResult(st.result);
    } else if (st.status === 'error') {
      clearInterval(pollTimer); pollTimer = null;
      document.getElementById('result').innerHTML = `<p class="warn">失败: ${st.error}</p>`;
    }
  };
  tick();
  pollTimer = setInterval(tick, 1000);
}

function renderResult(res) {
  if (!res) return;
  const dl = Object.entries(res.report_paths || {}).map(
    ([k, p]) => `<a href="/api/reports/${p.split('/').pop()}" target="_blank"><button>下载 ${k.toUpperCase()}</button></a>`
  ).join(' ');
  const scores = Object.entries(res.scores || {}).map(([k, v]) => {
    const label = Object.fromEntries(WEIGHT_KEYS)[k] || k;
    return `<div>${label}: ${v}<div class="score-bar"><i style="width:${v}%"></i></div></div>`;
  }).join('');
  const pains = (res.pain_points || []).map(p => `<li>${p.keyword||p.point||''} (频次 ${p.frequency??'—'}, 严重度 ${p.severity??'—'})</li>`).join('');
  const risks = (res.risk_items || []).map(r => `<li>[${r.level||''}] ${r.type||''}: ${r.desc||''}</li>`).join('');
  const prov = Object.entries(res.data_provenance || {}).map(([k,v]) => `${k}: ${v}`).join('；');
  document.getElementById('result').innerHTML = `
    <h2>${res.category} <span class="badge ${badgeClass(res.recommendation)}">${res.recommendation}</span></h2>
    <p>综合得分 <b>${res.total_score}</b> — ${res.recommendation_reason||''}</p>
    ${res.red_line_hit ? '<p class="warn">⚠ 命中红线规则</p>' : ''}
    <h3>五维评分</h3>${scores}
    <h3>利润</h3><p>售价 ¥${res.profit?.selling_price??'—'} · 毛利率 ${res.profit?.gross_margin??'—'}% · 回本 ${res.profit?.payback_months??'—'} 月 · 盈亏平衡 ${res.profit?.break_even_units??'—'} 件/月</p>
    <h3>TOP5 痛点</h3><ul>${pains}</ul>
    <h3>风险 (${(res.risk_items||[]).length})</h3><ul>${risks}</ul>
    <p class="warn">数据来源: ${prov||'—'}</p>
    ${(res.errors||[]).length ? `<p class="warn">错误: ${res.errors.join('; ')}</p>` : ''}
    <div>${dl}</div>`;
}

// —— 历史 ——
let page = 0; const PAGE_SIZE = 20;
async function loadHistory() {
  const r = await (await fetch(`/api/history?limit=${PAGE_SIZE}&offset=${page*PAGE_SIZE}`)).json();
  const tb = document.querySelector('#history-table tbody');
  tb.innerHTML = (r.items||[]).map(it => `<tr>
    <td>${it.category}</td><td>${it.platform}</td>
    <td><span class="badge ${badgeClass(it.recommendation)}">${it.recommendation||''}</span></td>
    <td>${it.total_score??''}</td><td>${it.gross_margin??''}</td>
    <td>${it.red_line_hit?'是':''}</td><td>${(it.created_at||'').slice(0,16)}</td>
    <td><button onclick="showDetail(${it.id})">查看</button></td>
  </tr>`).join('');
  document.getElementById('page-info').textContent = `第 ${page+1} 页 / 共 ${r.total} 条`;
}
document.getElementById('prev-page').onclick = () => { if (page>0){page--; loadHistory();} };
document.getElementById('next-page').onclick = () => { page++; loadHistory(); };

window.showDetail = async function(id) {
  const d = await (await fetch(`/api/history/${id}`)).json();
  const sj = d.state_json || {};
  const dl = Object.entries(d.report_paths || {}).map(
    ([k, p]) => `<a href="/api/reports/${(p||'').split('/').pop()}" target="_blank"><button>下载 ${k.toUpperCase()}</button></a>`
  ).join(' ');
  const scores = Object.entries(sj.scores || {}).map(([k,v]) => {
    const label = Object.fromEntries(WEIGHT_KEYS)[k] || k;
    return `<div>${label}: ${v}<div class="score-bar"><i style="width:${v}%"></i></div></div>`;
  }).join('');
  const pains = (sj.pain_points||[]).map(p => `<li>${p.keyword||p.point||''}</li>`).join('');
  const risks = (sj.risk_items||[]).map(r => `<li>[${r.level||''}] ${r.type||''}: ${r.desc||''}</li>`).join('');
  document.getElementById('detail-content').innerHTML = `
    <h2>${d.category} <span class="badge ${badgeClass(d.recommendation)}">${d.recommendation}</span></h2>
    <p>综合得分 <b>${d.total_score}</b> · 毛利率 ${d.gross_margin??'—'}%</p>
    <h3>五维评分</h3>${scores}
    <h3>TOP5 痛点</h3><ul>${pains}</ul>
    <h3>风险</h3><ul>${risks}</ul>
    <div>${dl}</div>`;
  document.querySelector('[data-tab="detail"]').click();
};

// —— 设置 ——
let cfgState = null;
async function loadConfig() {
  cfgState = await (await fetch('/api/config')).json();
  // 权重滑块（百分比显示）
  const wEl = document.getElementById('cfg-weights');
  wEl.innerHTML = '';
  WEIGHT_KEYS.forEach(([k, label]) => {
    const row = document.createElement('label');
    row.innerHTML = `${label} <input type="range" min="0" max="100" value="${(cfgState.scoring_weights[k]*100).toFixed(0)}" data-k="${k}"> <span>${(cfgState.scoring_weights[k]*100).toFixed(0)}%</span>`;
    row.querySelector('input').addEventListener('input', e => {
      cfgState.scoring_weights[k] = +e.target.value / 100;
      row.querySelector('span').textContent = e.target.value + '%';
      updateCfgSum();
    });
    wEl.appendChild(row);
  });
  updateCfgSum();
  // 利润参数
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
  // localStorage 恢复高级滑块
  const saved = localStorage.getItem('adv-weights');
  if (saved) { try { Object.assign(weightState, JSON.parse(saved)); renderSliders(document.getElementById('weight-sliders'), weightState, document.getElementById('weight-sum')); } catch {} }
}
function updateCfgSum() {
  const sum = Object.values(cfgState.scoring_weights).reduce((a,b)=>a+b,0)*100;
  document.getElementById('cfg-weight-sum').querySelector('b').textContent = sum.toFixed(0) + '%';
}
document.getElementById('config-form').addEventListener('submit', async e => {
  e.preventDefault();
  const payload = {
    scoring_weights: cfgState.scoring_weights,
    profit: Object.fromEntries([...document.querySelectorAll('#cfg-profit input')].map(i => [i.dataset.k, +i.value])),
    crawl: { force_mock: document.getElementById('cfg-force-mock').checked },
  };
  localStorage.setItem('adv-weights', JSON.stringify(weightState));
  const r = await fetch('/api/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  document.getElementById('cfg-status').textContent = r.ok ? '已保存' : '保存失败: ' + (await r.json()).error.message;
});
