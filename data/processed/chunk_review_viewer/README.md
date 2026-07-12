# Chunk 复核结果浏览器

`chunk_review.html` 是中国场外衍生品法规知识库的独立、只读复核结果页面。页面内嵌 108 份正式法规和 1219 个 Chunk，可直接在浏览器中打开，无需后端服务。

## 页面内容

- 法规标题、文号、发文机关、效力状态和官方来源
- 按法规浏览的 Chunk 正文和结构标签
- 法规检索、当前法规正文检索、正文复制和 Chunk 定位链接
- 独立复核结论与总体覆盖情况

公开页面不包含本机绝对路径、`source_block_ids`、overlap 来源、字符数、自动风险启发式等构建过程信息。

## 重新生成

在完成结构化文本、Chunk 和独立复核后运行：

```bash
python3 knowledge_base/build_chunk_review_viewer.py
```

生成器会从 `all_chunks.jsonl` 和独立复核结果中取数，只将展示所需字段写入最终 HTML。
