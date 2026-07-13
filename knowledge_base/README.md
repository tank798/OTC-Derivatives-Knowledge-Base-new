# 中国金融监管法规切分程序

本程序只读扫描项目内唯一原件目录 `data/raw/监管文件`，不修改、删除或覆盖原文件。结构化正文写入 `data/processed/documents`，检索 Chunk 写入 `data/processed/chunks`。

## 切分逻辑

1. 递归识别文件、编/篇/部分、章、节、条、款、项、目、段和完整句子。
2. 上级结构不超过 1200 个正文字符时整体保留；超过后才向下拆分。
3. 连续短条款尽量组合到 600-1200 字符；主题变化时优先换块。
4. 出现“前款”“前条”“上述”等依赖时，只重叠完整结构单元。
5. DeepSeek 仅复核相邻结构单元的语义边界和重叠需求，不接触原文改写；决策写入本地缓存。
6. 文档标题只接受开头可信标题，无法确认时使用经过来源前缀清洗的本地文件名，不再把正文引用法规识别为本文标题。
7. PDF和Word目录不进入Chunk；PDF Symbol字体公式字符按Adobe编码规范化，无法映射的字符会显式标记。

## 支持格式

`.docx`、`.doc`、`.pdf`、`.xlsx`、`.txt`、`.md`、`.html`。旧 `.doc` 优先在临时目录通过 LibreOffice 转换，失败时使用清理域代码后的 `textutil` 结果，原文件不变。扫描型 PDF 优先读取 `data/raw/official_text_cache/<同名文件>.html` 中已核验的官方网页正文；没有官方缓存时才调用本机 OCR。缓存来源和回退情况会写入结构化文档及本地诊断报告，不会伪装成 PDF 文本层。

## 稳定ID与增量构建

- `document_id` 由法规正式名称、文号、发文机关和版本生成，不依赖文件路径、扩展名或正文哈希。
- `chunk_id` 由稳定文档ID、章/节/条定位和正文哈希生成，不依赖本次顺序号。
- `data/processed/build_manifest.json` 分别记录原件哈希、正文哈希、元数据哈希、解析器版本、切分器版本和每份文件的产物路径。
- 原件未变时复用结构化正文；正文及切分器未变时复用 Chunk；只修改 URL 等元数据时仅刷新 Chunk 元数据。

## 运行

```bash
python3 knowledge_base/main.py --force
```

不使用外部模型：

```bash
python3 knowledge_base/main.py --force --disable-llm
```

只处理指定文件：

```bash
python3 knowledge_base/main.py --force --file "期货和衍生品法"
```

默认支持增量处理：文件哈希、程序版本、语义复核模式和已生成 JSONL 均未变化时直接复用。从 `--disable-llm` 切换到默认 DeepSeek 模式时会自动重建，不会误用上一种模式的块。

## 测试

```bash
python3 -m unittest discover -s knowledge_base/tests -v
```

## Chunk全量复核

在构建完成后，逐个 Chunk 核对源块、结构、元数据、原件路径、PDF页覆盖、DOCX smartTag、噪声、长度、重复正文和列举承接：

```bash
python3 knowledge_base/review_chunks.py
```

复核结果写入 `data/processed/chunk_review`；脚本只读原件，不修改 `data/raw/监管文件`。

已完成的全量复核只保留压缩结论 `docs/chunk_review_final_report.md`。逐 Chunk 记录、覆盖明细和中间 CSV 不进入仓库。

## 正式输出

- `data/processed/chunks/jsonl/all_chunks.jsonl`
- `data/processed/documents/json/*.json`
- `data/processed/build_manifest.json`

逐文档 JSONL、Markdown、CSV 索引、扫描清单、质量诊断和全量复核明细仍可由脚本在本地生成，但不提交 Git。
