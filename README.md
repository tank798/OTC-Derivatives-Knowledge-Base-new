# 场外衍生品法规知识库问答系统

本项目把本地监管原件加工为结构化 Chunk，通过 BM25 与本地中文向量模型混合检索，再由大模型严格依据本次检索证据生成带法规引用的回答。证据不足时不使用模型记忆补全法律结论。

## 当前数据

- 176 份本地监管原件，位于 `data/raw/regulations/`。
- 1,828 个已复核 Chunk，位于 `data/processed/chunks/all_chunks.jsonl`。
- BM25、BGE 向量和元数据索引，位于 `data/index/`。
- 83 份有官网 URL，93 份待人工补充。

## 目录

```text
apps/api/                   NestJS 问答 API
apps/web/                   Next.js 问答界面
packages/shared/            API 类型和 Zod schema
packages/prompts/           证据约束 Prompt
knowledge_base/             文档解析、清洗、结构化切分
data/raw/regulations/       法规原件
data/processed/chunks/      最终 Chunk
data/metadata/              法规元数据源
data/index/                 BM25、向量和检索语料
scripts/                    索引、检索、URL 同步维护脚本
tests/                      问答链路测试
outputs/                    人工补充清单
docs/                       架构、审计和迁移说明
```

## 安装

要求 Node.js 20+、pnpm 10+、Python 3.11+。

```bash
corepack enable
pnpm install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

填写 `.env` 中的 `LLM_API_KEY`。支持 OpenAI-compatible `/chat/completions` 接口，默认配置为 DeepSeek；密钥不会提交仓库。

## 构建知识库

新增法规原件后：

```bash
python knowledge_base/main.py --input-dir data/raw/regulations --output-dir data/processed/chunks
pnpm build:retrieval
```

切分器默认使用本地规则。只有明确配置 `DEEPSEEK_API_KEY_FILE` 并启用相应配置时，才会发送文本片段给外部模型做语义边界复核。

本地向量模型固定为 `Xenova/bge-base-zh-v1.5` ONNX q8：

```bash
pnpm download:retrieval-model
```

模型下载到 `.cache/huggingface/`，不会提交 Git。

## 官网 URL

待补清单：`outputs/missing_regulation_urls.xlsx`。填写 URL 后运行：

```bash
python scripts/update_regulation_urls.py
```

脚本优先按“法规名称＋文号”匹配，再按唯一法规名称匹配；无法唯一匹配或 URL 格式无效时写入 `outputs/url_update_conflicts.csv`，不会覆盖元数据。同步目标包括法规元数据、文档索引、Chunk 检索语料和索引哈希。

## 启动

```bash
pnpm dev:api   # http://127.0.0.1:4000/api
pnpm dev:web   # http://127.0.0.1:3000
```

API：

- `GET /api/compliance/health`
- `POST /api/compliance/query`，请求体 `{"query":"..."}`
- `POST /api/compliance/query/stream`，SSE

前端、非流式 API 和流式 API 都调用同一套 `ComplianceService`。

## 问答链路

```text
问题规范化与拆解
 -> 受控关键词/语义查询生成
 -> BM25 + BGE
 -> 等权 RRF、去重和上下文补齐
 -> 证据上下文组装
 -> LLM 结构化回答
 -> 引用与效力校验
 -> 最终输出
```

BM25 对标题、章节、条号和正文等权索引，没有监管元数据加权。详细设计见 `docs/qa_retrieval_architecture.md`。

## 测试

```bash
pnpm test
python -m pytest knowledge_base/tests
```

Node 测试覆盖索引一致性、中文 BM25、向量行号、RRF、Chunk 去重、雪球扩展、幻觉引用拒绝、效力未知降级、URL 防伪造和端到端服务链路。

## 限制

- 93 份法规尚缺官网 URL。
- 78 份法规效力状态为空或未知，不能据此回答确定的现行效力结论。
- 当前向量检索为本地模型；模型缓存缺失时 API 会明确降级为 BM25。
- 本系统提供法规检索与证据整理，不替代法律意见或机构内部合规审批。

数据问题和人工待办见 `docs/data_quality_audit.md`；旧项目清理范围见 `docs/migration_cleanup.md`。
