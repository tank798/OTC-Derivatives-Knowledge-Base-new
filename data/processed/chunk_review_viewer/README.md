# 法规目录与 Chunk 查看器

本目录包含两个可直接在浏览器中打开的静态页面，无需后端服务：

- `regulation_catalog.html`：基于当前 108 份正式法规生成的监管文件总目录；
- `chunk_review.html`：内嵌 108 份法规和 1,221 个 Chunk 的切分查看页面。

## 页面内容

- 法规标题、文号、发文机关、效力状态和官方来源
- 按法规浏览的 Chunk 正文和结构标签
- 法规检索、当前法规正文检索、正文复制和 Chunk 定位链接
- 独立复核结论与总体覆盖情况

公开页面不包含本机绝对路径、`source_block_ids`、overlap 来源、字符数、自动风险启发式等构建过程信息。

## 重新生成

在完成结构化文本、Chunk 和独立复核后运行：

```bash
python3 knowledge_base/build_regulation_catalog_viewer.py
python3 knowledge_base/build_chunk_review_viewer.py
```

总目录生成器从 `data/index/document_metadata.jsonl` 取数；Chunk 查看器从 `all_chunks.jsonl` 和独立复核结果取数。两者都只将展示所需字段写入最终 HTML。
