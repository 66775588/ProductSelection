# 选品调研 Agent — 前端页面设计

- 日期: 2026-07-11
- 范围: 为现有 CLI-only 选品调研 Agent 新增 Web 前端 + FastAPI 服务层
- 方案: A — LangGraph 流式进度 + 内存任务 + 运行时覆盖（含评审强制的 4 项安全修复）

## 1. 目标与场景

日常工具型：选品人员每天使用。核心闭环 = 输入品类 → 9 节点进度 → 结果总览 → 下载报告；外加历史记录、报告详情、运行时设置。

非目标 (YAGNI): 无鉴权、无多用户、无 SSE、无跨重启任务持久化的完整恢复（已完成结果已落 SQLite + 报告文件）、无 PDF（依赖声明但从未实现）。

## 2. 架构

新增 `src/dianshang/server/` 包，包裹现有 agent，**不改动 9 个节点逻辑**。

```
src/dianshang/server/
├── app.py          # FastAPI app: 路由 + 挂载 static
├── jobs.py         # 内存任务存储 (线程安全 dict) + SQLite 镜像
├── runner.py       # 流式跑图 → 更新任务状态；完成时落 SQLite
├── paths.py        # 共享路径安全工具 (Path.resolve 锁定 data/reports)
├── config_store.py # runtime_overrides.json 的文件锁 + 增量合并 + 校验
└── static/
    ├── index.html  # 单页, tab 切换 (无路由库)
    ├── app.js      # 原生 JS: fetch + 轮询 + 渲染
    └── style.css
```

现有代码改动（向后兼容）:
- `agent/graph.py:run()` 增加可选 `overrides: dict | None = None` 参数。
- `config.py` 暴露 `get_settings()` 返回可变运行时实例；三个消费方 (`analysis/scoring.py`、`analysis/profit.py`、`datasources/base.py`) 将 `from .config import settings` 改为 `get_settings()`。
- `memory/long_term.py` 新增两张表: `running_jobs`、`job_progress`（见 §8）。

运行时覆盖同时持久化到 `data/runtime_overrides.json`，启动时加载。

## 3. API 设计 (FastAPI)

| Method | Path | 说明 |
|---|---|---|
| `POST` | `/api/research` | body `{category, platform, overrides?}`；`platform` 枚举校验 (pdd/taobao/tmall/jd)。返回 `{job_id}`。已有任务运行中返回 `409`。 |
| `GET` | `/api/jobs/{id}` | `{status, current_node, completed_nodes[], result?, error?, errors?, warnings?}` |
| `DELETE` | `/api/jobs/{id}` | 取消/清理卡死任务，释放锁 |
| `GET` | `/api/history?limit=50&offset=0` | 分页列表（`memory.list_history` 增加分页参数） |
| `GET` | `/api/history/{id}` | 单条 `state_json` 全量（详情页） |
| `GET` | `/api/reports/{filename}` | 下载 `.md`/`.xlsx`/`.docx`；路径经 `paths.sanitize()` 校验，违规返回 `400` |
| `GET` | `/api/config` | 当前权重 + 利润参数 + force_mock |
| `PUT` | `/api/config` | 增量合并更新运行时覆盖；预校验；写 `runtime_overrides.json` |
| `GET` | `/api/health` | 存活探测 |

所有错误响应统一 JSON schema: `{"error": {"code": str, "message": str}}`。

## 4. 执行与进度数据流

`runner.run_job()` 用 `selection_graph.stream(initial, stream_mode="updates")` 替代 `.invoke()`。LangGraph 在每个节点完成后产出一个 chunk。对每个 chunk:
1. 追加节点 key 到内存 `completed_nodes`，设 `current_node`。
2. **同步写入 SQLite `job_progress` 表**（见 §8 强制项 3），避免崩溃丢失进度。
3. 节点 9 `memory_save` 在图内自然执行，落 `selections` 表。

`END` 时: 设 `status=done`，`result` = 摘要切片: `recommendation`、`total_score`、`scores`(5 维)、`profit`(毛利率/回本周期/盈亏平衡)、`pain_points[:5]`、`risk_items` 数量、`red_line_hit`、`report_paths`、`data_provenance`、`errors`、`warnings`。

前端每 1s 轮询 `GET /api/jobs/{id}`，由 9 步 stepper 渲染 `completed_nodes`；`status` 为 `done`/`error` 后**自动停止轮询**。

## 5. 强制安全修复（评审 mandatory）

### 5.1 单任务并发锁持久化 + 卡死恢复
- 内存 dict 的锁仅单进程有效。新增 SQLite `running_jobs` 表作为锁存储：`job_id, started_at, status`。`POST /api/research` 通过原子插入抢占锁；已有 `running` 行则 `409`。
- 新增 `DELETE /api/jobs/{id}` 端点：取消任务（线程尽力停止）+ 删除 `running_jobs`/`job_progress` 行，释放锁，用于清理卡死任务。
- 后台清理协程：服务启动 + 每 5 分钟扫描，删除 `started_at` 超 30 分钟的 `running_jobs` 行，消除永久阻塞。

### 5.2 runtime_overrides.json 竞态
- `config_store.py` 使用进程级文件锁 (`portalocker` 或 `fcntl`/`msvcrt` 跨平台封装) 包裹所有 JSON 读写。
- `PUT /api/config` **增量合并**入参到现有配置，而非整文件覆写。
- 预校验（不通过返回 `400`）:
  - 5 个权重之和 = 100（浮点容差 0.01）。
  - 所有百分比字段 ∈ [0, 100]。
  - 金额字段（packaging ¥、threshold）> 0。
  - 未知字段拒绝。

### 5.3 进度持久化 + 崩溃恢复
- 新增 SQLite `job_progress` 表：`job_id, node_key, completed_at`。每次 stream update 追加一行。
- 服务启动时: 读 `running_jobs` 中 `running` 且未超时的行 → 从 `job_progress` 重建 `completed_nodes` 入内存任务存储，标记 `status=running` 但 `stale=true`（前端提示"任务可能已中断，可取消重跑"）；超时行由清理协程处理。

### 5.4 路径穿越防护
- `paths.sanitize(filename)`: `resolved = (REPORTS_DIR / filename).resolve()`；若 `resolved != REPORTS_DIR.resolve()` 且不在其下，或 filename 含 `..`、`\`、绝对路径，返回 `None` → 端点 `400`。
- `/api/reports/{filename}` 与未来任何文件访问统一走该工具。

## 6. 前端页面（单 HTML, 4 tab）

1. **新建调研** — 品类输入 + 平台下拉 + 高级折叠（force_mock 开关、5 权重滑块，实时显示权重和并校验=100）。提交 → 9 节点 stepper（节点名 + 已用时长）→ 完成后结果总览: 推荐等级色标徽章、总分、5 维评分条、利润摘要、TOP5 痛点、风险数 + 红线标志、三格式下载按钮。
2. **历史记录** — 分页表格 (品类/平台/推荐/总分/毛利率/日期)；行点击 → tab 3。
3. **报告详情** — 同结果总览布局，数据来自 `/api/history/{id}` 的 `state_json`；下载按钮。
4. **设置** — 5 权重滑块（强制和=100，实时校验）、利润参数、force_mock 开关；保存 → `PUT /api/config`。
- 高级配置滑块值额外持久化到 `localStorage`，刷新不丢。
- 任务 `done`/`error` 自动停轮询。

## 7. 错误处理

- 节点失败已自隔离（各自 append `state.errors` 并继续）。runner 在 result 中回传 `errors`/`warnings`，UI 非阻塞提示"数据来源: 模拟/部分失败"。
- 图整体抛异常 → `status=error` + message，UI 内联展示。
- 单任务并发 → `409`。
- 下载路径违规 → `400`。
- 所有错误响应统一 schema（§3）。

## 8. SQLite schema 变更 (`memory/long_term.py`)

现有 `selections` 表不变。新增:

```sql
CREATE TABLE IF NOT EXISTS running_jobs (
    job_id     TEXT PRIMARY KEY,
    category   TEXT NOT NULL,
    platform   TEXT,
    started_at TEXT NOT NULL,
    status     TEXT NOT NULL          -- running|done|error|cancelled
);

CREATE TABLE IF NOT EXISTS job_progress (
    job_id      TEXT NOT NULL,
    node_key    TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (job_id, node_key)
);
```

新增函数: `claim_job(job_id, category, platform)` (原子抢占, 返回是否成功)、`release_job(job_id)`、`stale_jobs(older_than_minutes)`、`append_progress(job_id, node_key)`、`load_progress(job_id)`。

## 9. 测试 (`tests/server/`)

`test_api.py` (FastAPI `TestClient`, mock-backed):
- research → poll → done 全流程。
- 历史列表分页、详情。
- config GET/PUT 往返 + 权重和≠100 被拒 + 百分比越界被拒 + **并发 PUT 不丢数据**。
- 并发 research → 第二个 `409`。
- `DELETE /api/jobs/{id}` 释放锁。
- 卡死任务清理（构造 30+ 分钟前 `running_jobs` 行 → 清理后可新建）。
- 路径穿越攻击向量 (`../etc/passwd`、绝对路径、反斜杠) → `400`。
- 启动恢复: 构造 `running_jobs`+`job_progress` → 重启后内存任务存储含 `stale=true`。
- 现有 18 项测试保持绿（`run()` 签名向后兼容，`overrides` 默认 `None`）。

## 10. 风险与权衡

- 运行时覆盖通过 `get_settings()` 可变实例 + 单任务并发锁保证无竞态；权衡: 严格单任务串行，但日常单用户场景可接受。
- `job_progress` 每节点一次 SQLite 写入，开销可忽略（9 次写）。
- 卡死清理 30 分钟阈值可后续按 LLM 实际耗时调整。
