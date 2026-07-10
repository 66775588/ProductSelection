"""报告模板：Markdown（jinja2 渲染）。

Excel / Word 在 exporters.py 中程序化构建。
"""

MARKDOWN_TEMPLATE = """# 《{{ category }}》选品调研报告

> 平台：{{ platform }} ｜ 生成时间：{{ generated_at }}
> 数据来源：{% for k, v in provenance.items() %}{{ k }}={{ v }}{% if not loop.last %}，{% endif %}{% endfor %}
{% if warnings %}> ⚠️ 提示：{{ warnings | join("；") }}{% endif %}

---

## 一、选品结论总览

| 项目 | 结论 |
|---|---|
| **推荐等级** | **{{ recommendation }}** |
| **综合得分** | {{ total_score }} / 100 |
| **判定依据** | {{ reason }} |

**核心优势：**
{% for s in core_strengths %}- {{ s }}
{% endfor %}
**核心风险：**
{% for r in core_risks %}- {{ r }}
{% endfor %}

### 五维评分明细
| 维度 | 权重 | 得分 |
|---|---|---|
| 市场潜力 | 30% | {{ scores.market_potential }} |
| 竞争程度 | 20% | {{ scores.competition }} |
| 盈利空间 | 25% | {{ scores.profit }} |
| 用户痛点 | 15% | {{ scores.pain_points }} |
| 风险等级 | 10% | {{ scores.risk }} |

---

## 二、市场数据分析
{% if market %}
- 近30天搜索量：**{{ market.search_volume }}**（{{ market.market_type }}，{{ market.seasonality }}）
- 点击率：{{ market.click_rate }} ｜ 转化率：{{ market.conversion_rate }}
- 供需比：**{{ market.supply_demand_ratio }}**（>2 蓝海，<0.3 衰退）
- 30天搜索趋势（首→末指数）：{{ market.trend_30d[0].search_index if market.trend_30d else '-' }} → {{ market.trend_30d[-1].search_index if market.trend_30d else '-' }}

**长尾关键词：**
| 关键词 | 搜索量 |
|---|---|
{% for kw, vol in market.long_tail_keywords %}| {{ kw }} | {{ vol }} |
{% endfor %}
{% else %}
数据不足，无法分析市场热度。
{% endif %}

---

## 三、竞品对标分析
{% if competitor_analysis %}
- 竞品数量：{{ competitor_analysis.count }}
- 价格带：{{ competitor_analysis.price_band[0] }}~{{ competitor_analysis.price_band[1] }} 元（均价 {{ competitor_analysis.avg_price }}，中位价 {{ competitor_analysis.median_price }}）
- 平均月销：{{ competitor_analysis.avg_sales }}
- 头部 TOP3 垄断率：**{{ (competitor_analysis.top3_monopoly_rate * 100) | round(1) }}%**
{% endif %}

**TOP10 竞品对比：**
| 排名 | 商品 | 价格(元) | 月销 | 店铺等级 | 标签 |
|---|---|---|---|---|---|
{% for c in competitors %}| {{ c.rank }} | {{ c.title }} | {{ c.price }} | {{ c.sales }} | {{ c.shop_level }} | {{ c.tags | join("/") }} |
{% endfor %}

**竞品卖点拆解：**
{% for s in selling_points %}- {{ s.point }}（出现 {{ s.frequency }} 次）
{% endfor %}

---

## 四、用户痛点分析
{% if pain_points %}
**TOP 痛点清单：**
| 痛点 | 频次 | 严重度 | 代表评论 |
|---|---|---|---|
{% for p in pain_points %}| {{ p.keyword }} | {{ p.frequency }} | {{ p.severity }} | {{ p.sample }} |
{% endfor %}

**差异化切入方向（TOP3）：**
{% for d in differentiation %}- {{ d }}
{% endfor %}
{% else %}
评论数据不足，无法聚类痛点。
{% endif %}

---

## 五、成本利润测算
{% if profit and profit.cost_breakdown %}
- 目标售价：**{{ profit.selling_price }} 元** ｜ 供货价：{{ profit.supply_price }} 元
- 预估月销：{{ profit.est_monthly_sales }} 件 ｜ 月利润：{{ profit.monthly_profit }} 元

**单客成本明细：**
| 成本项 | 金额(元) |
|---|---|
{% for k, v in profit.cost_breakdown.items() %}| {{ k }} | {{ v }} |
{% endfor %}

| 指标 | 数值 |
|---|---|
| 毛利 | {{ profit.gross_profit }} 元 |
| **毛利率** | **{{ profit.gross_margin }}%** {% if profit.below_threshold %}（⚠️ 低于阈值 {{ profit.threshold }}%）{% endif %} |
| 首批备货成本 | {{ profit.initial_stock_cost }} 元 |
| 回本周期 | {{ profit.payback_months if profit.payback_months is not none else "—" }} 个月 |
| 盈亏平衡月销 | {{ profit.break_even_units if profit.break_even_units is not none else "—" }} 件 |
{% else %}
供应链/竞品数据不足，无法测算利润。
{% endif %}

---

## 六、风险排查清单
{% if risk_items %}
| 类型 | 等级 | 风险描述 | 规避方案 |
|---|---|---|---|
{% for r in risk_items %}| {{ r.type }} | {{ r.level }} | {{ r.desc }} | {{ r.mitigation }} |
{% endfor %}
{% else %}
暂未识别到明显风险。
{% endif %}

---

## 七、落地建议
- **切入价格带**：{{ landing.price_band }}，建议目标售价 {{ landing.target_price }} 元
- **核心卖点**：
{% for s in landing.core_selling_points %}  - {{ s }}
{% endfor %}
- **首发 SKU 配置**：
{% for s in landing.first_skus %}  - {{ s }}
{% endfor %}

---
{% if errors %}## ⚙️ 流程异常记录
{% for e in errors %}- {{ e }}
{% endfor %}
{% endif %}
*本报告由「电商选品调研 Agent」自动生成。标注「模拟数据」的指标为基于品类估算，非真实抓取，请结合实际经营校准。*
"""
