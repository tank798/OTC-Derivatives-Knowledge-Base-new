# 场外衍生品法规知识库问答系统

本项目把本地监管原件加工为结构化 Chunk，再由一个连续对话的 Agent 先向用户确认问题、读取相关专家 Wiki、调用 BM25 与本地中文向量组成的混合检索工具、自主判断是否需要第二轮检索，并基于原文回答。证据不足是允许的正常结果；系统会说明现有法规规定到哪里，而不是用模型记忆补出确定法律结论。

## 当前数据

- 114 份正式监管原件，位于 `data/raw/监管文件/`。
- 114 份结构化正文，位于 `data/processed/documents/json/`。
- 1,700 个正式 Chunk，位于 `data/processed/chunks/jsonl/all_chunks.jsonl`。
- Chunk 复核结论见 `docs/reviews/Chunk复核报告.md`。
- BM25 和本地 BGE 向量索引已基于 1,700 个 Chunk 重建，索引清单记录 114 份法规、54,868 个 BM25 词项和 1,700 个 768 维向量。
- 问答层使用同一套通用 Agent Prompt；轻任务使用 Flash、证据判断与回答使用 Pro，没有为三道示例问题预置相关 Chunk 或专项补丁。

## 目录

```text
apps/api/                   NestJS 问答 API
apps/web/                   Next.js 问答界面
packages/shared/            API 类型和 Zod schema
packages/prompts/           对话式法规 Agent 的 System Prompt
knowledge_base/             文档解析、清洗、结构化切分
data/raw/监管文件/          唯一法规原件目录
data/processed/chunks/      最终 Chunk
data/processed/documents/   结构化法规正文
data/metadata/              法规元数据源
data/index/                 BM25、向量和检索语料
scripts/                    索引、检索、URL 同步维护脚本
wiki/                       经用户确认的业务 Know-how（不替代法规）
docs/                       常用入口、查看器、迭代记录和架构说明
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

已有索引与当前向量模型均可用时，可只为新增或正文变化的Chunk计算向量；BM25仍会按完整语料重建：

```bash
pnpm build:retrieval:incremental
```

结构化JSON的`cleaning`字段记录清洗规则版本、原文与清洗后哈希、字符数变化、被移出正文的block及规则命中。原文件和清洗后正文哈希都未变化时，继续复用既有Chunk；向量输入哈希未变化时，继续复用原向量。

切分器默认使用本地规则。只有明确配置 `DEEPSEEK_API_KEY_FILE` 并启用相应配置时，才会发送文本片段给外部模型做语义边界复核。

本地向量模型固定为 `Xenova/bge-base-zh-v1.5` ONNX q8：

```bash
pnpm download:retrieval-model
```

模型下载到 `.cache/huggingface/`，不会提交 Git。

## 手动问答核验

当前保留三道真实问题作为手动核验示例：

- 上市公司能否开展挂钩自身股票的场外衍生品；
- 证券公司收益凭证能否设计为雪球结构；
- 私募产品投资雪球的比例限制。

启动本地 API 和前端后，直接在聊天页面按真实用户流程测试：先看 Agent 对问题的改写，确认或修正后再观察检索与回答。运行日志写入被 Git 忽略的 `data/index/eval/logs/`。

## 官网 URL

当前 114 份正式法规均已有官网 URL。后续新增法规需要人工补充 URL 时，可准备包含“法规名称”和“URL”的 Excel，再运行：

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
- `POST /api/compliance/query`，首轮请求体 `{"message":"..."}`，后续对话带上 `sessionId`
- `POST /api/compliance/query/stream`，SSE

前端、非流式 API 和流式 API 都调用同一套 `ComplianceService`。

前端采用连续对话布局：左侧保存当前标签页会话中的历史对话，可新建、切换和删除；不同对话可以独立运行，当前对话回答时仍可编辑草稿；中间展示问答与处理进度；右侧参考依据栏分为法规原文和专家 Wiki。刷新页面后历史仍会保留；关闭标签页后浏览器会清理该会话，避免合规问题长期明文留存在本地。

## 问答链路

```text
用户提问
 -> Agent 使用 Flash 轻量改写问题并等待用户确认
 -> 读取与问题相关的专家 Wiki，仅用于校准术语和业务场景
 -> Agent 用一个完整问题调用 hybrid_regulation_search（BM25 + BGE + RRF）
 -> Agent 阅读最多 10 个 Chunk，自主判断是否需要第二轮检索
 -> 两轮时保留第一轮相关证据，合并后上下文仍最多 10 个 Chunk
 -> 同一个 Agent 基于原文撰写回答
 -> 程序只校验 evidence ID 和逐字引文是否真实
 -> 系统回填法规名称、文号、条号和官网链接
 -> 输出回答，或如实说明证据不足和待人工判断的边界
```

BM25 对标题、章节、条号和正文等权索引，没有监管元数据加权。BM25 与向量均以 Chunk 为召回单位；同一法规最多提供3个 Chunk，避免单一长文占满10条回答上下文。详细设计见 `docs/architecture/问答与检索架构.md`。

## 静态检查

```bash
pnpm test
pnpm build
python3 -m unittest discover -s knowledge_base/tests -v
```

`pnpm test` 检查 Chunk 级混合检索、Wiki 写入门禁、引用真实性、并发状态和 TypeScript。生产构建检查 NestJS 与 Next.js。真实模型链路可在 API 启动后运行 `pnpm test:live-agent`；其自动通过只表示流程和引用完整性通过，回答结论仍需人工盲评，不为三道示例题维护运行时专项判定器。

## 限制

- 当前索引与评测基于 114 份法规、1,700 个 Chunk；新增或修改 Chunk 后必须重建 BM25，并为新增或正文变化的 Chunk 更新向量。
- 三道评测题只是首版回归集，不代表已覆盖所有产品、主体、时间和效力冲突情形。
- Agent 运行日志默认使用 `metadata` 模式，不记录问题、回答和逐字引文正文，并自动清理超过 7 天的日志；仅在受控排障环境中显式设置 `AGENT_LOG_MODE=full`。
- 法规效力状态为空或未知时，不能据此回答确定的现行效力结论。
- 当前向量检索为本地模型；模型缓存缺失时 API 会明确降级为 BM25。
- 本系统提供法规检索与证据整理，不替代法律意见或机构内部合规审批。
