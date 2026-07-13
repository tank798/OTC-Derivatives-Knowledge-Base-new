# 法规与 Chunk 查看器

本目录包含一个可直接在浏览器中打开的静态页面，无需后端服务：

- `chunk_review.html`：直接从正式 `all_chunks.jsonl` 生成，统一提供法规筛选、法规目录和 1,221 个 Chunk 的正文查看。

## 页面内容

- 法规标题、文号、发文机关、效力状态和官方来源
- 按法规浏览的 Chunk 正文和结构标签
- 按关键词、发文主体、效力状态和文件格式统一筛选法规及 Chunk
- 正文复制和 Chunk 定位链接
- Chunk 正文、章节和条款范围

公开页面不包含本机绝对路径、`source_block_ids`、overlap 来源、字符数、自动风险启发式等构建过程信息。

## 重新生成

在完成结构化文本和 Chunk 后运行：

```bash
python3 knowledge_base/build_chunk_review_viewer.py
```

查看器从唯一正式 Chunk 集 `all_chunks.jsonl` 取数，只将展示所需字段写入最终 HTML。
