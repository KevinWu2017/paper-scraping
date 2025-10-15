# ArXiv Paper Digest

抓取 arXiv cs.DC、cs.OS、cs.AR 三个分类的最新论文，使用可选的 LLM 进行摘要生成，并提供一个简洁的网页界面便于浏览。

## 功能亮点

- 🚀 **定时抓取**：默认每天早上 08:00 自动从 arXiv RSS 获取并入库最新论文（可通过配置调整时间与时区）。
- 🧠 **摘要生成**：支持调用阿里云百炼 Qwen 系列模型（兼容 OpenAI SDK），会抓取 PDF 原文后执行全文摘要；无密钥时自动回退到规则摘要。
- 🗄️ **持久化存储**：使用 SQLite/SQLAlchemy 保存论文与摘要，避免重复抓取。
- 🖥️ **可视化前端**：内置 FastAPI+Jinja2 页面，快速筛选分类并查看摘要、原文链接和 PDF。
- 🔧 **命令行工具**：`python -m backend.cli refresh` 即刻刷新数据，便于与定时任务结合。

## 快速开始

### 1. 准备环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> 如果使用 Windows，请将 `source .venv/bin/activate` 改为 `.\.venv\Scripts\activate`。

### 2. 配置环境变量（可选）

在项目根目录创建 `.env` 文件，可覆盖默认设置：

```dotenv
PAPER_LLM_API_KEY=sk-...
PAPER_LLM_MODEL=qwen-plus
PAPER_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
PAPER_ARXIV_CATEGORIES=cs.DC,cs.OS,cs.AR
PAPER_REFRESH_HOUR=8
PAPER_REFRESH_MINUTE=0
PAPER_SCHEDULER_TIMEZONE=Asia/Shanghai
PAPER_REFRESH_INTERVAL_MINUTES=180
PAPER_SUMMARY_SENTENCE_COUNT=5
PAPER_SUMMARY_LANGUAGE=zh
PAPER_ADMIN_TOKEN=your-secret-token
PAPER_SQLITE_BUSY_TIMEOUT_SECONDS=30
PAPER_SQLITE_JOURNAL_MODE=WAL
PAPER_SCHEDULER_TIMEZONE=Asia/Shanghai
```

> 若未设置 `PAPER_LLM_API_KEY`，应用会使用简易摘要回退策略。

> `PAPER_REFRESH_INTERVAL_MINUTES` 为兼容旧版本的保留字段，当前调度使用小时/分钟与时区配置。

### 3. 启动服务

```bash
uvicorn backend.app:app --reload
```

服务默认监听 `http://127.0.0.1:8000`，浏览器打开即可查看最新的论文摘要列表（页面无需手动刷新）。

### 4. 手动刷新数据

```bash
python -m backend.cli refresh
```

若想只刷新某一分类，可追加 `-c` 参数多次，例如：

```bash
python -m backend.cli refresh -c cs.DC -c cs.OS
```

### 5. 运行测试

```bash
pytest
```

## Docker 部署

1. **构建镜像**

   ```bash
   docker build -t arxiv-paper-digest .
   ```

2. **（可选）预创建 SQLite 文件**

   ```bash
   python scripts/init_sqlite.py
   ```

   > 若计划通过 `-v $(pwd)/papers.sqlite3:/app/papers.sqlite3` 挂载宿主机文件，需先在宿主机创建该文件；运行此脚本会按照当前配置自动生成。

3. **运行容器**（可选地挂载宿主机数据库文件与 `.env` 配置）

   ```bash
   docker run -d \
     --name arxiv-paper-digest \
     --env-file .env \
     -p 8000:8000 \
     -v $(pwd)/papers.sqlite3:/app/papers.sqlite3 \
     arxiv-paper-digest
   ```

   > `--env-file` 可以换成单独的 `-e` 环境变量；如果希望容器退出后保留数据，请保持卷挂载。
   > 镜像默认时区为 `Asia/Shanghai`，可通过 `-e TZ=...` 覆盖。

4. **手动刷新/调试**

   ```bash
   docker exec -it arxiv-paper-digest python -m backend.cli refresh -c cs.DC
   ```

容器启动后会暴露 `http://localhost:8000`；内部 APScheduler 仍会按照配置的时区与时间自动刷新。

## 使用 LLM 生成摘要

1. **配置密钥**：在 `.env`（或部署环境变量）中设置 `PAPER_LLM_API_KEY`，必要时同步调整 `PAPER_LLM_MODEL` 与 `PAPER_LLM_BASE_URL`。默认已指向阿里云百炼的兼容模式端点，可直接使用 `qwen-plus`、`qwen-max` 等模型。
   - 默认会尝试从论文 PDF 提取文本并进行分段总结，可通过 `PAPER_FULL_TEXT_CHUNK_CHARS`、`PAPER_FULL_TEXT_CHUNK_OVERLAP`、`PAPER_FULL_TEXT_MAX_CHUNKS` 微调分段逻辑。
2. **触发抓取 + 摘要**：
   - 命令行方式：`python -m backend.cli refresh`（可追加 `-c cs.DC` 指定分类）。
   - HTTP 接口：向 `POST /api/refresh` 发送请求；如配置了 `PAPER_ADMIN_TOKEN`，需在 Header 中附带 `X-Admin-Token`。
3. **查看结果**：摘要会写入数据库，可在前端页面或调用 `GET /api/papers` 查看 `summary`、`summary_model` 字段。若密钥缺失或 LLM 请求失败，将自动回退到规则摘要。

> 提示：定时任务会在每天 08:00 自动执行一次刷新，确保密钥已生效即可获得新的 LLM 摘要。

## 架构概览

- **FastAPI**：提供 REST API (`/api/papers`、`/api/refresh`、`/api/categories`) 以及网页渲染。
- **APScheduler**：在应用启动时根据 `PAPER_REFRESH_HOUR` / `PAPER_REFRESH_MINUTE` 以及 `PAPER_SCHEDULER_TIMEZONE` 自动注册每日定时任务。
- **SQLAlchemy**：负责 SQLite 数据库建模及访问；默认数据库文件为 `./papers.sqlite3`。
- **前端**：使用 Jinja2 模板和原生 JS 进行渲染，样式位于 `backend/static/styles.css`。
- **测试**：基于 `pytest` + `respx`，涵盖爬虫解析、数据刷新和摘要回退逻辑。

## API 速览

- `GET /api/papers?category=cs.DC&limit=20`：分页获取论文列表。
- `GET /api/categories`：返回数据库中已存在的分类，若为空则回退配置中的默认分类。
- `POST /api/refresh`：触发一次抓取+摘要。设置了 `PAPER_ADMIN_TOKEN` 时需携带 `X-Admin-Token` 请求头。
- `GET /healthz`：健康检查。

## 部署建议

- 生产环境推荐使用 `gunicorn` + `uvicorn` worker 或者容器化部署，并配置定时任务或保持 APScheduler 运行。
- 若要手动刷新，可运行 `python -m backend.cli refresh`；平时保持应用运行即可依赖内置调度。
- 请妥善保管百炼/大模型 API Key，并按需设置 `PAPER_ADMIN_TOKEN` 防止匿名触发刷新。

## 常见问题

1. **摘要为空？**
   - 确认已设置 `PAPER_LLM_API_KEY`；若未配置将使用规则摘要，内容会较为简略。
2. **抓取失败？**
   - 默认带有重试策略，若仍失败请查看网络连接或调整 `PAPER_REQUEST_TIMEOUT_SECONDS`（在 `.env` 中设置）。
3. **想扩展更多分类？**
   - 修改 `.env` 的 `PAPER_ARXIV_CATEGORIES`，多个分类用逗号分隔即可。

欢迎根据需要扩展更多功能，例如用户账号、多语言摘要、历史版本对比等。
