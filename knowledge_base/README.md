# 中国金融监管法规切分程序

本程序只读扫描项目内的 `data/raw/regulations`，不修改、删除或覆盖原文件。结果统一写入 `data/processed/chunks`。

## 切分逻辑

1. 递归识别文件、编/篇/部分、章、节、条、款、项、目、段和完整句子。
2. 上级结构不超过 1200 个正文字符时整体保留；超过后才向下拆分。
3. 连续短条款尽量组合到 600-1200 字符；主题变化时优先换块。
4. 出现“前款”“前条”“上述”等依赖时，只重叠完整结构单元。
5. DeepSeek 仅复核相邻结构单元的语义边界和重叠需求，不接触原文改写；决策写入本地缓存。
6. 文档标题只接受开头可信标题，无法确认时使用经过来源前缀清洗的本地文件名，不再把正文引用法规识别为本文标题。
7. PDF和Word目录不进入Chunk；PDF Symbol字体公式字符按Adobe编码规范化，无法映射的字符会显式标记。

## 支持格式

`.docx`、`.doc`、`.pdf`、`.xlsx`、`.txt`、`.md`、`.html`。旧 `.doc` 优先在临时目录通过 LibreOffice 转换，失败时使用清理域代码后的 `textutil` 结果，原文件不变。扫描型 PDF 不会输出乱码，而是进入 OCR/人工复核清单。

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
python3 -m unittest discover -s tests -v
```

## 输出

- `data/processed/chunks/jsonl/*.jsonl`
- `data/processed/chunks/all_chunks.jsonl`
- `data/processed/chunks/markdown/*.md`
- `data/processed/chunks/chunk_index.csv`
- `data/processed/chunks/切分报告.md`
- `data/processed/chunks/自动校验结果.json`
- `data/processed/chunks/文件扫描清单.csv`
