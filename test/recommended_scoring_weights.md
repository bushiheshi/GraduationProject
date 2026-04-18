# 相关项目调研与推荐评分权重

## 当前向量模型

当前 `test/` 中使用的向量模型是：

```text
BAAI/bge-small-zh-v1.5
```

依据位置：

- `test/kb_semantic_retriever.py`
- `test/textbook_kb/vector_index/index_meta.json`

当前索引信息：

```text
model_name: BAAI/bge-small-zh-v1.5
chunk_count: 145
embedding_dim: 512
```

这个模型是 BAAI 的中文文本向量模型，用于把教材片段、题目和学生答案转成向量。当前代码使用 Hugging Face `AutoTokenizer` 和 `AutoModel` 加载模型，用 mean pooling 得到句向量，再做 L2 归一化，最后用向量点积进行相似度排序。因为向量已经归一化，这里的点积可以近似理解为余弦相似度。

## 相关项目与可借鉴做法

1. **传统短答案自动评分 ASAG**
   - Mohler 等人在 ACL 2011 的短答案评分研究中使用语义相似度和依存图对齐来学习评分。
   - 可借鉴点：短答案评分不能只看关键词重合，还要看语义相似和结构对应。

2. **GradeRAG**
   - GradeRAG 将 RAG 用于短答案评分，把领域知识、评分指南、专家标注样例一起检索给评分模型。
   - 其检索重排序使用三个部分：语义相似度 40%、词面重合 30%、领域概念覆盖 30%。
   - 可借鉴点：你的模型目前有语义相似和词面重合，但缺少“评分标准/知识点覆盖”这个显式维度。

3. **RAGAS / ARES**
   - RAGAS 强调检索上下文是否相关、答案是否忠实于上下文、答案本身是否回答问题。
   - ARES 将 RAG 评估拆成 context relevance、answer faithfulness、answer relevance，并强调少量人工标注可用于校准。
   - 可借鉴点：你的指标中 `support_density` 接近 context relevance，`evidence_consistency` 接近 faithfulness，仍缺少更明确的 answer relevance / rubric match。

4. **编程作业自动评分**
   - 编程教育自动评分综述显示，代码题最常用、最可靠的依据是动态测试，尤其是单元测试；静态分析可补充代码质量、可读性和维护性。
   - 可借鉴点：如果学生提交的是代码，不能主要依赖教材相似度，必须加入运行测试和关键用例测试。

## 当前权重的问题

当前 `assess_answer_credibility.py` 的基础权重是：

```text
support_coverage      0.38
support_density       0.20
scope_alignment       0.18
answer_specificity    0.12
evidence_consistency  0.12
ai_penalty            0.18 * ai_rate
```

主要问题：

- `support_coverage` 权重偏高，容易把“和教材词汇重合多”误当成“答案质量高”。
- `evidence_consistency` 权重偏低，而 RAG 类评估更重视答案是否忠实于证据。
- `answer_specificity` 只能说明答案是否具体，不能说明答案是否正确，权重不宜过高。
- `ai_penalty` 直接扣分过重。AI 检测结果更适合作为风险提示，而不是内容质量的决定性扣分项。
- 缺少 `rubric_match` 或 `concept_coverage`，即答案是否覆盖题目要求的关键知识点。

## 推荐权重方案一：不改指标，只调整现有模型

如果暂时不新增指标，建议改为：

```text
support_coverage      0.30
evidence_consistency  0.24
support_density       0.18
scope_alignment       0.16
answer_specificity    0.12
```

AI 生成概率建议改为风险标签，而不是强扣 `0.18 * ai_rate`。如果必须扣分，建议最大扣分不超过 `0.08`：

```text
ai_penalty = 0.08 * ai_rate
```

理由：

- 教材覆盖仍然重要，但不能压过证据一致性。
- 证据一致性提高到 0.24，更符合 RAG 评估中 answer faithfulness 的思路。
- 学习进度对齐保留 0.16，适合本项目的教学场景。
- 答案具体性保留 0.12，只作为表达充分性的辅助指标。

## 推荐权重方案二：新增 rubric_match 后的更合理方案

更建议新增一个 `rubric_match` 指标，用来判断答案是否覆盖题目要求或评分细则。例如冒泡排序题可要求覆盖：

- 基本思想
- Python 代码
- 循环边界
- 交换条件
- 时间复杂度
- 空间复杂度
- 示例过程

推荐权重：

```text
rubric_match          0.26
support_coverage      0.22
evidence_consistency  0.20
support_density       0.14
scope_alignment       0.10
answer_specificity    0.08
```

AI 风险仍建议单独展示：

```text
ai_risk = ai_rate
```

如果学校或论文必须给出综合分，可使用轻量扣分：

```text
final_score = content_score - 0.05 * ai_rate
```

这比当前 `0.18 * ai_rate` 更稳妥，因为 AI 检测工具存在误判风险，不能把它等同于答案错误。

## 代码题推荐权重

如果题目要求提交代码，建议不要使用上面的纯文本可信度权重作为主评分。更合理的是：

```text
unit_tests            0.45
rubric_match          0.20
algorithm_reasoning   0.15
code_quality          0.10
evidence_alignment    0.10
```

说明：

- `unit_tests`：代码能否通过空输入、边界值、重复值、典型样例等测试。
- `rubric_match`：是否覆盖题目要求。
- `algorithm_reasoning`：是否能解释算法思想和复杂度。
- `code_quality`：命名、结构、可读性、异常处理。
- `evidence_alignment`：是否与教材当前知识点一致。

## 建议写进论文的表述

> 参考短答案自动评分、RAG 评估和编程作业自动评分相关研究，本研究将答案评价拆分为评分细则覆盖、教材证据支持、证据一致性、检索相关性、学习进度一致性和答案具体性等维度。由于当前阶段缺少大规模教师标注数据，权重采用基于文献启发和教学场景需求的原型权重，后续可通过教师人工评分样本进行校准。

## 推荐后续实现顺序

1. 先把 `ai_penalty` 从 `0.18` 降到 `0.05-0.08`，并在报告中强调它是风险提示。
2. 增加 `rubric_match`，从题目要求中提取关键评分点。
3. 对代码题增加测试用例执行结果。
4. 建立 `test/labeled_samples.jsonl`，用教师标注数据校准权重。

## 参考来源

- Mohler, Bunescu, Mihalcea. 2011. *Learning to Grade Short Answer Questions using Semantic Similarity Measures and Dependency Graph Alignments*. ACL. https://aclanthology.org/P11-1076/
- Chu et al. 2025. *Enhancing LLM-Based Short Answer Grading with Retrieval-Augmented Generation*. EDM. https://educationaldatamining.org/EDM2025/proceedings/2025.EDM.short-papers.81/index.html
- Es et al. 2024. *RAGAS: Automated Evaluation of Retrieval Augmented Generation*. EACL Demo. https://aclanthology.org/anthology-files/anthology-files/pdf/eacl/2024.eacl-demo.16.pdf
- Saad-Falcon et al. 2024. *ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems*. NAACL. https://aclanthology.org/2024.naacl-long.20/
- Hou et al. 2023. *Automated Grading and Feedback Tools for Programming Education: A Systematic Review*. https://arxiv.org/abs/2306.11722
- CodeGrade AutoTest V2 Blocks documentation. https://help.codegrade.com/automatic-grading-guides/autotest-v2-blocks
- BAAI/bge-small-zh-v1.5 model card. https://huggingface.co/BAAI/bge-small-zh-v1.5
