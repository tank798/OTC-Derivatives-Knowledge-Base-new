# 检索评测集

`queries.jsonl` 是当前的人工标注评测集。每条记录包含用户原问、相关 Chunk、BM25/混合检索最大可接受排名和回答行为期望。

运行：

```bash
pnpm eval:retrieval
```

产物：

- `results.json`：机器可读的逐题排名和总体统计。
- `results.md`：人工检查用的简表。

检索评测检查 BM25、向量和等权 RRF。回答行为期望由 `tests/qa_pipeline.test.cjs` 中的引用校验测试执行，防止“召回了相关文件”被误当成“已有直接规定”。
