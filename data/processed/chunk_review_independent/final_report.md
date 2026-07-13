# 中国场外衍生品法规知识库 Chunk 独立复核报告

生成时间：2026-07-13T01:47:02.417150+00:00

## 结论

- 是否复核全部Chunk：是（输入1219条，唯一ID 1219个，复核记录1219条）。
- 是否存在正文遗漏：未发现。source_block未覆盖0个；无Chunk正式文档0份。
- 是否存在转换错误：未发现明确转换错误。
- 是否存在切分错误：未发现。
- 错名PDF排除是否合理：合理（依据现存排除记录及正确DOCX；错名PDF当前不在raw目录，无法再次直接验页）。核对信息：{"file_name": "证券公司市场风险管理指引.pdf", "exists": false, "exclusion_record_present": true, "exclusion_reason": "PDF首页及正文实际为《证券公司全面风险管理规范》，与文件名和声明标题不一致，且与已有正确DOCX重复；错名副本已从唯一raw目录移除，不生成正式Chunk", "correct_docx_exists": true}
- 是否建议修复后重新构建：否；本轮已重建并通过复核。

## 覆盖统计

- 正式文档：108份；原件：108份；结构化JSON：108份。
- PASS：1219；MINOR：0；MAJOR：0；CRITICAL：0。
- source_block正文遗漏：0个；完全重复ID：0个；高度重复对：0对。

## 问题分布


## 专项核对

- Shibor 1M、3M、6M、9M：{"1M": true, "3M": true, "6M": true, "9M": true}。
- 商品衍生品定义文件前六条：{"第1条": true, "第2条": true, "第3条": true, "第4条": true, "第5条": true, "第6条": true}。
- 错名PDF：{"file_name": "证券公司市场风险管理指引.pdf", "exists": false, "exclusion_record_present": true, "exclusion_reason": "PDF首页及正文实际为《证券公司全面风险管理规范》，与文件名和声明标题不一致，且与已有正确DOCX重复；错名副本已从唯一raw目录移除，不生成正式Chunk", "correct_docx_exists": true}。

## 方法说明

脚本逐条检查Chunk覆盖、唯一性、索引连续性、source_block引用与正文一致性、长度、重复、乱码/私有区/Word域代码/孤立页码、核心元数据与边界启发式；并独立从PDF文本层及分页、DOCX OOXML（含表格、文本框、smartTag）和旧DOC转换文本读取原件，对条号与日期/金额/比例/期限等关键token进行差异核对。自动差异仅作为候选，报告结论以明确证据为准。
