# 电商选品调研 Agent

自动化全链路选品决策：**输入品类 → 自主抓取数据 → 分析竞品/痛点 → 测算盈利 → 排查风险 → 输出选品评估报告**。

基于 LangGraph 编排 9 节点工作流，智谱 GLM 驱动分析层，Playwright 爬取平台公开数据，Mock 适配器兜底保证流水线始终可跑通。

## 核心能力

| 模块 | 说明 |
|---|---|
| 市场热度调研 | 搜索量/转化率/趋势/供需比/长尾词，判断蓝海·红海·衰退 |
| 竞品对标分析 | TOP20 竞品销量/客单价/SKU/店铺等级/商品链接，头部垄断率 |
| 用户痛点挖掘 | GLM 语义聚类差评 → TOP10 痛点 → 差异化方向 |
| 盈利空间测算 | 全链路成本（供货/佣金/物流/推广/退款/税）→ 毛利率/回本/盈亏平衡 |
| 风险自动排查 | 禁售/侵权红线 + 合规 + 供应链质量风险 |

## 快速开始

```bash
# 1. 安装依赖
pip install -e ".[dev]"

# 2.（可选）配置智谱 GLM，启用 LLM 深度分析；不配置则走规则/统计降级
cp .env.example .env
# 编辑 .env 填入 ZHIPUAI_API_KEY

# 3.（可选）启用真实爬取需安装浏览器；不装则自动回退 Mock
playwright install chromium

# 4. 运行
python -m examples.run_demo "保温杯" --platform pdd
```

运行后在 `data/reports/` 生成 Markdown / Excel / Word 三份报告，控制台打印推荐等级与综合得分。

## Web 界面

```bash
pip install -e ".[web]"
python -m dianshang.server.app    # http://127.0.0.1:8000
```

或开发模式：`python -m uvicorn dianshang.server.app:create_app --factory --reload`

**深色仪表盘风格**，5 个 Tab：

| Tab | 功能 |
|---|---|
| 新建调研 | 品类 + 平台卡片选择 → 9 节点实时进度 → 五维评分/利润/痛点/风险 → 竞品链接列表 → 下载报告 |
| 仪表盘 | 6 个统计卡片（总数/强烈推荐/平均分/覆盖平台/红线命中/平均毛利率）+ 推荐分布 + API 凭证状态 |
| 历史记录 | 分页浏览 + 品类搜索 + 平台筛选，点击查看详情 |
| 报告详情 | 完整历史结果（含竞品 TOP 列表和商品链接） |
| 设置 | 评分权重滑块 + 利润参数 + 强制 Mock + **多平台 API 凭证管理** |

单任务串行：同一时刻只允许一个调研任务运行（SQLite 锁），超 30 分钟未完成的任务会被自动清理。

## 平台 API 凭证

Web 设置页可直接输入各电商平台 API 密钥，系统将优先使用真实 API 数据替代 Mock：

| 平台 | 凭证 | 用途 |
|---|---|---|
| 1688 开放平台 | AppKey + AppSecret | 供应链货源价格查询（分销关键词搜索，官方 MD5 签名） |
| 拼多多开放平台 | client_id + client_secret | 商品搜索/销量（pdd.ddk.goods.search，需多多客/营销类应用授权） |
| 生意参谋（淘宝/天猫） | Token + Cookie | ⚠️ 无公开开放 API（预留，配置无效，建议第三方数据服务） |
| 京东商智 | AppKey + AppSecret | ⚠️ 无公开开放 API（预留，配置无效） |

凭证持久化到 `data/runtime_overrides.json`（该文件已被 .gitignore 忽略，防止密钥误提交），前端显示脱敏（`****` + 后 4 位），API 调用失败自动回退 Mock。

## 竞品商品链接

竞品 TOP20 列表包含商品超链接：
- **真实爬取**：从平台搜索页提取 `<a href>`，补全相对路径
- **Mock 数据**：生成平台标准格式占位链接（如 `https://item.taobao.com/item.htm?id=xxx`）
- 调研结果页和详情页均可点击跳转

## 工作流

```
任务拆解 → 数据抓取(并行) → 数据清洗 → LLM分析(痛点/卖点) → 利润测算 → 风险排查 → 五维打分 → 报告生成 → 记忆入库
```

五维评分权重：市场潜力 30% · 竞争 20% · 盈利 25% · 痛点 15% · 风险 10%。
推荐等级：强烈推荐(≥80) · 可尝试(≥65) · 谨慎进入(≥50) · 不推荐(<50)；命中红线直接不推荐。

## 数据源策略（重要）

所有数据源均为**适配器**，Mock 是其中一种实现：

| 数据源 | 真实接入方式 | 凭证要求 |
|---|---|---|
| 竞品列表 | Playwright 爬取平台公开搜索页 + 提取商品链接 | 无需 |
| 评论 | Playwright 两步流程（预留，未启用） | 可登录态 Cookie |
| 市场热度 | 拼多多 pdd.ddk.goods.search（真实）；生意参谋/京东商智无公开 API，回退 Mock | 拼多多凭证 |
| 1688 供货价 | 1688 开放平台分销关键词搜索（官方 MD5 签名） | 1688 凭证 |

- **来源溯源**：每条数据带 `source` 字段（real_scrape / api / mock），报告中模拟数据明确标注「（模拟）」，杜绝将模拟数据当真实数据呈现。

> ⚠️ **数据真实性说明**：真实爬取受平台反爬与登录限制，成功率不保证。第一版以「能跑通 + 可演示」为目标，**不保证真实数据完整性**。
> 1688 与拼多多适配器已按官方签名规范（MD5）接入真实 API；接口响应字段做了兼容解析，首次使用请核对运行日志确认 `source=api` 生效。
> 生意参谋、京东商智为商家后台内部平台、无公开开放 API，需通过第三方数据服务（生意参谋/蝉妈妈等）补齐。

## 配置

关键环境变量（见 `.env.example`）：

| 变量 | 说明 | 默认 |
|---|---|---|
| `ZHIPUAI_API_KEY` | 智谱 API Key，启用 LLM 分析 | 空（走降级） |
| `GLM_MODEL` | 模型名 | glm-4.6 |
| `PROFIT_THRESHOLD` | 毛利率红线(%) | 30 |
| `FORCE_MOCK` | 强制全部走 Mock | false |
| `CRAWL_HEADLESS` | 浏览器无头模式 | true |

平台 API 凭证通过 Web 设置页输入，无需写入 `.env`。

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| POST | `/api/research` | 创建调研任务 |
| GET | `/api/jobs/{job_id}` | 查询任务状态/进度/结果 |
| DELETE | `/api/jobs/{job_id}` | 取消运行中任务 |
| GET | `/api/history?limit=&offset=` | 历史记录分页 |
| GET | `/api/history/{id}` | 历史详情（含竞品列表） |
| GET | `/api/reports/{filename}` | 下载报告文件 |
| GET | `/api/config` | 读取当前配置（含凭证状态） |
| PUT | `/api/config` | 保存评分+利润配置（增量合并） |
| GET | `/api/credentials` | 平台凭证状态（脱敏） |
| PUT | `/api/credentials` | 保存平台凭证（增量合并） |
| DELETE | `/api/credentials/{platform}` | 清除单平台凭证 |

## 测试

```bash
pytest              # 48 项单测：mock 确定性 / 利润公式 / 评分红线 / 清洗去重 / 端到端图 / 凭证 CRUD
```

## 项目结构

```
src/dianshang/
├── agent/        # LangGraph 图、节点、状态、提示词
├── datasources/  # 数据接入层（适配器 + Mock + Playwright + 1688/拼多多 API）
├── analysis/     # GLM 封装、痛点聚类、利润测算、评分模型
├── risk/         # 侵权/合规/供应链风险排查
├── memory/       # SQLite 长期记忆库（选品结果 + 竞品列表 + 销量反馈）
├── report/       # Markdown / Excel / Word 报告生成
├── server/       # FastAPI 服务 + Web 前端（深色仪表盘）+ 运行时配置
└── utils/        # HTTP / Playwright / 数据清洗
```

## 后续迭代

- 真实数据源已按官方规范接入 1688 分销搜索 / 拼多多商品搜索（官方 MD5 签名），待真实凭证实测校准；生意参谋、京东商智需接入第三方数据服务
- 前 100 个选品人工复核，微调评分权重与提示词
- 回传真实销量数据（`memory.add_feedback`），迭代选品模型
- 对接「商品上架文案 Agent」，选品通过后自动生成标题详情页
