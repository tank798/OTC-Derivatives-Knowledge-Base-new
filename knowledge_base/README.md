# 中国金融监管法规切分程序

本程序以项目内唯一原件目录 `data/raw/监管文件` 为只读输入，解析过程保持原件完整；结构化正文写入 `data/processed/documents`，检索 Chunk 写入 `data/processed/chunks`。

## 切分逻辑

1. 递归识别文件、编/篇/部分、章、节、条、款、项、目、段和完整句子。
2. 上级结构不超过 1200 个正文字符时整体保留；超过后才向下拆分。
3. 连续短条款尽量组合到 600-1200 字符；主题变化时优先换块。
4. 出现“前款”“前条”“上述”等依赖时，只重叠完整结构单元。
5. DeepSeek仅复核相邻结构单元的语义边界和重叠需求，原文保持原样；决策写入本地缓存。
6. 文档标题优先取开头可信标题，未能确认时使用经过来源前缀清洗的本地文件名；正文引用法规保留为正文内容。
7. PDF和Word目录作为结构噪声过滤；PDF Symbol字体公式字符按Adobe编码规范化，待映射字符会显式标记。

## 支持格式

`.docx`、`.doc`、`.pdf`、`.xlsx`、`.txt`、`.md`、`.html`。旧 `.doc` 优先在临时目录通过 LibreOffice 转换，必要时使用清理域代码后的 `textutil` 结果，原文件保持不变。扫描型PDF优先读取 `data/raw/official_text_cache/<同名文件>.html` 中已核验的官方网页正文，随后按需调用本机OCR。缓存来源和回退情况会写入结构化文档及本地诊断报告，并明确标注文本来源。

## 稳定ID与增量构建

- `document_id` 由法规正式名称、文号、发文机关和版本生成，在路径、扩展名和正文哈希变化时保持稳定。
- `chunk_id` 由稳定文档ID、章/节/条定位和正文哈希生成，在文档顺序调整时保持稳定。
- 每份结构化文档同时保存 `front_matter`、`body_blocks`、`appendices`、`clean_text` 和 `structured_blocks`。HTML“阅读原文”直接使用 `clean_text + structured_blocks`，检索 overlap 作为独立上下文维护。
- `structured_blocks` 区分标题、条款、普通段落、指南标题、表格、公式、附件和注释；表格展示使用二维网格，检索时另行生成带表头语义的文本。
- Chunk 的 `start_char/end_char` 指向 `clean_text` 中的主正文位置；`primary_block_ids/overlap_block_ids` 区分本块正文和为检索保留的上下文。`overlap_left/right` 描述检索重叠，阅读正文恢复使用主正文范围。
- `clean_text_hash` 决定是否需要重新切分，`chunk_hash` 与 embedding 输入哈希决定是否需要重新向量化。
- `data/processed/build_manifest.json` 分别记录原件哈希、正文哈希、元数据哈希、解析器版本、切分器版本和每份文件的产物路径。
- 原件未变时复用结构化正文；清洗后正文及切分器未变时复用 Chunk；只修改 URL 等元数据时仅刷新 Chunk 元数据。

正文开头的发布公告、独立文号、重复标题和版本说明会移入元数据或 `front_matter`；正式条款中的施行、废止、衔接内容以及实质性通知前言仍保留。PDF 页眉页脚、页码和目录在结构化前清理。

## 运行

```bash
python3 knowledge_base/main.py --force
```

本地规则模式：

```bash
python3 knowledge_base/main.py --force --disable-llm
```

只处理指定文件：

```bash
python3 knowledge_base/main.py --force --file "期货和衍生品法"
```

默认支持增量处理：文件哈希、程序版本、语义复核模式和已生成 JSONL 保持一致时直接复用；从 `--disable-llm` 切换到默认 DeepSeek 模式时自动重建对应 Chunk。

生成单文件法规查看器：

```bash
python3 knowledge_base/build_chunk_review_viewer.py
```

仅对变化的 Chunk 更新向量，并生成逐行复用审计：

```bash
npm run build:retrieval:incremental
```

审计文件为 `data/index/incremental_vector_audit.csv`；`status=reused` 且 `vector_bytes_identical=true` 表示旧向量按字节复用。

## 测试

```bash
python3 -m unittest discover -s knowledge_base/tests -v
```

## Chunk全量复核

在构建完成后，逐个 Chunk 核对源块、结构、元数据、原件路径、PDF页覆盖、DOCX smartTag、噪声、长度、重复正文和列举承接：

```bash
python3 knowledge_base/review_chunks.py
```

复核结果写入 `data/processed/chunk_review`；脚本以 `data/raw/监管文件` 为只读输入。

已完成的全量复核结论集中保留在 `docs/history/项目迭代记录.md` 和 `docs/history/新增法规与知识库十轮迭代记录_20260724.md`；逐 Chunk 记录、覆盖明细和中间 CSV按需写入本地复核目录。

## 正式输出

- `data/processed/chunks/jsonl/all_chunks.jsonl`
- `data/processed/documents/json/*.json`
- `data/processed/build_manifest.json`

逐文档 JSONL、Markdown、CSV索引、扫描清单、质量诊断和全量复核明细均可由脚本在本地生成；正式结构化正文、Chunk和索引保留在版本化产物中。
