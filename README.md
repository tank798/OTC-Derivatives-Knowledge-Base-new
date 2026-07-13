# 场外衍生品法规知识库问答系统

本项目把本地监管原件加工为结构化 Chunk，通过 BM25 与本地中文向量模型混合检索，再由大模型严格依据本次检索证据生成带法规引用的回答。证据不足时不使用模型记忆补全法律结论。

## 当前数据

- 108 份正式监管原件，位于 `data/raw/监管文件/`。
- 108 份结构化正文，位于 `data/processed/documents/json/`。
- 1,221 个已完成独立复核的 Chunk，位于 `data/processed/chunks/jsonl/all_chunks.jsonl`。
- Chunk 复核记录为 1,221/1,221，当前 MINOR、MAJOR、CRITICAL 均为 0。
- BM25 和本地 BGE 向量索引已基于 1,221 个新 Chunk 重建，索引清单记录 108 份法规、50,667 个 BM25 词项和 1,221 个 768 维向量。
- 首版 3 道真实问题均通过与正式产品完全相同的 DeepSeek Pro 端到端问答评测（3/3）。

## 目录

```text
apps/api/                   NestJS 问答 API
apps/web/                   Next.js 问答界面
packages/shared/            API 类型和 Zod schema
packages/prompts/           证据约束 Prompt
knowledge_base/             文档解析、清洗、结构化切分
data/raw/监管文件/          唯一法规原件目录
data/processed/chunks/      最终 Chunk
data/processed/documents/   结构化法规正文
data/processed/chunk_review_independent/  Chunk 独立复核结果
data/metadata/              法规元数据源
data/index/                 BM25、向量和检索语料
scripts/                    索引、检索、URL 同步维护脚本
tests/                      问答链路测试
outputs/                    运行时人工处理输出（不提交临时文件）
docs/                       问答与检索架构说明
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
python knowledge_base/main.py --input-dir data/raw/监管文件 --output-dir data/processed/chunks
pnpm build:retrieval
```

切分器默认使用本地规则。只有明确配置 `DEEPSEEK_API_KEY_FILE` 并启用相应配置时，才会发送文本片段给外部模型做语义边界复核。

本地向量模型固定为 `Xenova/bge-base-zh-v1.5` ONNX q8：

```bash
pnpm download:retrieval-model
```

模型下载到 `.cache/huggingface/`，不会提交 Git。

## 端到端问答评测

当前评测集位于 `data/index/eval/queries.jsonl`，包含：

- 上市公司能否开展挂钩自身股票的场外衍生品；
- 证券公司收益凭证能否设计为雪球结构；
- 私募产品投资雪球的比例限制。

```bash
pnpm eval:qa
```

评测直接调用正式 `ComplianceService`，完整经过问题分析、混合检索、上下文组装、DeepSeek 回答和引用校验，不预置所谓“人工相关 Chunk”。模型从实际进入上下文的 Chunk 中自行选择引用；评测检查最终判断、必要法规、关键限定及官网链接。

## 官网 URL

当前 108 份正式法规均已有官网 URL。后续新增法规需要人工补充 URL 时，可准备包含“法规名称”和“URL”的 Excel，再运行：

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
 -> 校验失败时使用同一批证据修订一次
 -> 最终输出
```

BM25 对标题、章节、条号和正文等权索引，没有监管元数据加权。详细设计见 `docs/qa_retrieval_architecture.md`。

## 测试

```bash
pnpm test
python -m pytest knowledge_base/tests
```

Node 测试覆盖索引一致性、中文 BM25、向量行号、RRF、Chunk 去重、雪球扩展、幻觉引用拒绝、效力未知降级、URL 防伪造、重复引用合并和引用失败修订。

## 限制

- 当前索引与评测基于 108 份法规、1,221 个 Chunk；新增或修改 Chunk 后必须重建 BM25 和向量并重跑评测。
- 三道评测题只是首版回归集，不代表已覆盖所有产品、主体、时间和效力冲突情形。
- 法规效力状态为空或未知时，不能据此回答确定的现行效力结论。
- 当前向量检索为本地模型；模型缓存缺失时 API 会明确降级为 BM25。
- 本系统提供法规检索与证据整理，不替代法律意见或机构内部合规审批。
