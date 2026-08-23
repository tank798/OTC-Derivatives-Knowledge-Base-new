# 评测材料

本目录集中保存问答系统的可重复评测材料：

- `questions/`：200题标准题库；
- `results/eval_200_questions/`：原始基线与根因分析；
- `results/eval_200_questions_rejudged_v5/`：缓存重判基线；
- `results/eval_200_questions_iter5_full/`：200题最终全量复测；
- `results/eval_q*`和`results/eval_common_precondition_iter5/`：通用Prompt规则的定向回归证据。

重跑默认评测：

```bash
node scripts/eval_200_questions.mjs --fresh \
  --output-dir evaluation/results/eval_200_questions_next
```

新的实验必须写入独立目录，不覆盖现有基线和最终复测证据。
