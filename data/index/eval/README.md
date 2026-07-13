# 端到端问答评测集

这里的三个问题走与正式产品完全相同的链路：问题分析、混合检索、上下文组装、DeepSeek 回答和引用校验。

`queries.jsonl` 不预置 Chunk ID。模型从本次实际检索上下文中自行选择引用，评测器只检查最终判断、必要法规、关键限定和官网链接。

配置 `LLM_API_KEY`、`LLM_MODEL=deepseek-v4-pro` 后运行：

```bash
pnpm eval:qa
```

产物：

- `results.json`：完整保存问题分析、实际模型上下文、最终回答、模型选择的引用和校验结果。
- `results.md`：按“先直接回答、后法规依据及官网链接”的格式生成简表。
