# 代码片段类答案评估模型方案

## 判断

当前评估对象不是完整可运行程序，而是类似“写出部分语句”“补全关键代码”“说明某段逻辑”“给出算法步骤”这类答案。因此不需要实现代码运行测试，也不应把“能否运行”作为主要评价依据。

更合理的评估目标是判断学生答案是否：

```text
理解题目要求
写出了关键语句或关键逻辑
使用了正确的程序结构
变量、条件、循环边界与题目上下文一致
能覆盖主要正常情况和必要边界情况
表达清楚、没有明显概念性错误
```

对于这类答案，评估模型应以“评分点匹配 + 语义等价判断 + 局部语法/结构检查 + 样例推演”为主。教材检索可以作为知识点依据和学习进度一致性辅助项，但不应作为主评分项。

## 推荐总权重

建议使用以下权重：

```text
rubric_match             0.30
semantic_correctness     0.25
syntax_structure         0.15
context_consistency      0.10
trace_correctness        0.10
complexity_or_efficiency 0.05
evidence_alignment       0.05
```

说明：

- `rubric_match`：是否覆盖题目要求的关键评分点。
- `semantic_correctness`：答案语义是否正确，是否能实现题目要求的核心逻辑。
- `syntax_structure`：语句、表达式、条件、循环、缩进或伪代码结构是否基本合理。
- `context_consistency`：变量名、函数名、数据结构、输入输出是否与题干上下文一致。
- `trace_correctness`：用给定样例或典型样例推演时，关键步骤是否正确。
- `complexity_or_efficiency`：是否存在明显低效、冗余或不符合课程要求的写法。
- `evidence_alignment`：答案涉及的知识点是否与当前教材和学习进度一致。

AI 检测不建议直接作为内容分的大幅扣分项。推荐单独输出风险：

```text
ai_risk = ai_rate
```

如果必须进入总分，建议只做轻量扣分：

```text
final_score = max(0, content_score - 0.05 * ai_rate)
```

如果没有 AI 检测结果：

```text
final_score = content_score
```

## 各指标说明

### 1. rubric_match，30%

`rubric_match` 检查学生答案是否覆盖题目预设评分点。它是片段类代码题最稳定、最可解释的主指标。

例如题目要求补写冒泡排序内层交换语句，rubric 可以包含：

```text
比较相邻元素
判断前一个元素是否大于后一个元素
使用临时变量或等价方式交换两个元素
更新的是列表中的相邻位置
没有改变无关变量
```

评分建议：

```text
rubric_match = matched_items / total_items
```

如果评分点重要性不同，可以给每个评分点设置权重：

```text
rubric_match = matched_weight / total_weight
```

建议每道题都维护结构化 rubric，例如：

```json
{
  "question_id": "bubble_sort_swap",
  "rubric_items": [
    {
      "id": "compare_adjacent",
      "description": "比较相邻元素",
      "weight": 0.25
    },
    {
      "id": "swap_when_needed",
      "description": "仅当前一个元素大于后一个元素时交换",
      "weight": 0.35
    },
    {
      "id": "use_correct_indices",
      "description": "使用正确的相邻下标",
      "weight": 0.25
    },
    {
      "id": "no_unrelated_logic",
      "description": "没有加入与题目无关的逻辑",
      "weight": 0.15
    }
  ]
}
```

### 2. semantic_correctness，25%

`semantic_correctness` 判断答案语义是否正确。它不要求代码完整运行，而是判断学生写出的语句或步骤在题干上下文中是否能表达正确逻辑。

建议检查：

```text
核心判断条件是否正确
核心赋值或更新对象是否正确
循环或分支的作用是否符合题意
是否存在方向相反、条件遗漏、变量写错等逻辑错误
是否存在只适用于特定样例的硬编码答案
```

例如“统计列表中偶数个数”的补写语句：

```python
if num % 2 == 0:
    count += 1
```

以下答案可以判为语义基本正确：

```python
if not num % 2:
    count = count + 1
```

以下答案应扣分：

```python
if num / 2 == 0:
    count += 1
```

因为它混淆了整除、取余和除法判断。

### 3. syntax_structure，15%

`syntax_structure` 检查答案是否具备基本语法和结构合理性。对于片段类答案，不建议因为缺少完整函数、导入语句或主程序入口而扣分。

建议重点检查：

```text
表达式是否基本合法
赋值方向是否正确
条件语句、循环语句是否有合理结构
缩进或伪代码层级是否清楚
括号、冒号、运算符使用是否明显错误
```

评分时应区分“局部语法错误”和“语义错误”：

```text
语义正确但少写冒号：轻度扣分
语法形式正确但判断条件完全错误：中重度扣分
```

这样更符合教学评价目的，因为这类题主要考查学生是否掌握关键逻辑。

### 4. context_consistency，10%

`context_consistency` 判断答案是否与题目给定上下文一致。

建议检查：

```text
是否使用题干给出的变量名
是否使用题干给出的列表、字典、函数或对象
是否与已有代码片段的缩进层级匹配
是否与题目要求的输入输出一致
是否没有引入未定义且无法从上下文推断的变量
```

例如题干已有：

```python
scores = [88, 92, 75]
total = 0
for score in scores:
    ________
```

合理答案：

```python
total += score
```

如果学生写：

```python
sum += x
```

即使“累加”的意图接近，也应在 `context_consistency` 中扣分，因为 `x` 和 `sum` 不符合题目上下文。

### 5. trace_correctness，10%

`trace_correctness` 用样例推演判断答案是否会得到合理结果。它不是运行代码，而是对学生答案做静态或半结构化推演。

适用场景：

```text
循环累加
条件判断
列表遍历
排序或查找的关键步骤
字符串处理
计数器更新
```

例如题目要求补写“统计大于 60 的成绩数量”，可用样例：

```text
scores = [80, 55, 60, 90]
正确计数结果应为 2
```

如果答案是：

```python
if score >= 60:
    count += 1
```

推演结果为 3，说明边界条件与“大于 60”不一致，应在 `trace_correctness` 和 `semantic_correctness` 中扣分。

### 6. complexity_or_efficiency，5%

片段类答案一般不需要复杂性能评估，但可以保留少量权重，用于识别明显不合理写法。

建议检查：

```text
是否使用符合课程阶段的常规方法
是否存在明显多余循环
是否把简单判断写成复杂低效过程
是否为了特定样例硬编码输出
```

如果题目本身不涉及算法效率，可以将该项固定为满分，或把 5% 权重并入 `semantic_correctness`。

### 7. evidence_alignment，5%

这是当前教材检索模型适合保留的位置。它用于判断答案涉及的概念是否与当前教材和学习进度一致。

可复用当前模型中的：

```text
support_coverage
support_density
scope_alignment
evidence_consistency
```

建议压缩为一个辅助分：

```text
evidence_alignment =
  0.35 * support_coverage
  + 0.25 * support_density
  + 0.25 * evidence_consistency
  + 0.15 * scope_alignment
```

注意：该项只用于辅助解释，不应因为教材相似度较低就否定一个明显正确的代码语句答案。

## 推荐最终公式

```text
content_score =
  0.30 * rubric_match
  + 0.25 * semantic_correctness
  + 0.15 * syntax_structure
  + 0.10 * context_consistency
  + 0.10 * trace_correctness
  + 0.05 * complexity_or_efficiency
  + 0.05 * evidence_alignment
```

如果启用 AI 风险轻量扣分：

```text
final_score = max(0, content_score - 0.05 * ai_rate)
```

如果不启用 AI 风险扣分：

```text
final_score = content_score
```

## 等级划分建议

```text
>= 0.85  优秀
>= 0.70  良好
>= 0.60  基本达标
>= 0.40  存疑
<  0.40  不达标
```

对这类题，“高可信 / 低可信”不如“优秀 / 良好 / 基本达标 / 存疑 / 不达标”更适合教学反馈。

## 检测流程

建议评估流程如下：

```text
1. 读取题目、题干上下文、学生答案、参考答案和评分 rubric
2. 判断答案类型：代码语句、代码片段、伪代码、自然语言说明、混合答案
3. 对答案做规范化处理：去除无关空白、统一中英文符号、识别代码块
4. 计算 rubric_match，判断关键评分点覆盖情况
5. 计算 semantic_correctness，判断语义是否等价或基本等价
6. 计算 syntax_structure，判断局部语法和结构是否合理
7. 计算 context_consistency，判断变量、对象、缩进层级是否匹配题干
8. 使用典型样例做 trace_correctness 静态推演
9. 计算 complexity_or_efficiency，识别明显低效或硬编码答案
10. 用现有教材检索模型计算 evidence_alignment
11. 读取 AI 检测结果作为 ai_risk，仅作为风险提示或轻量扣分
12. 输出总分、分项分、扣分原因、命中的评分点、教师建议
```

## 与当前模型的关系

当前 `assess_answer_credibility.py` 更适合保留为辅助模块：

```text
教材证据检索模块
学习进度一致性模块
报告证据展示模块
AI 风险提示模块
```

不建议继续作为代码片段类答案的主评分模型。主评分模型应围绕题目 rubric、语义正确性和上下文一致性设计。

## 落地建议

1. 在 `test/` 中新增 `code_statement_rubrics.json`，保存每道题的评分点、权重、参考答案和可接受等价表达。
2. 新增 `code_statement_trace_cases.json`，保存用于静态推演的典型样例和预期关键结果。
3. 新增 `assess_code_statement_answer.py`，负责识别答案类型、匹配 rubric、判断语义等价并汇总分数。
4. 保留 `assess_answer_credibility.py` 作为 `evidence_alignment` 子模块。
5. 先用“补写条件语句”“补写循环累加语句”“补写列表遍历语句”“补写交换语句”四类题验证评分稳定性。
6. 每次输出报告时同时给出 `score`、`level`、`subscores`、`matched_rubric_items`、`deduction_reasons` 和 `teacher_feedback`。

## 输出格式建议

建议模型输出结构如下：

```json
{
  "score": 0.82,
  "level": "良好",
  "subscores": {
    "rubric_match": 0.90,
    "semantic_correctness": 0.80,
    "syntax_structure": 0.85,
    "context_consistency": 0.75,
    "trace_correctness": 0.80,
    "complexity_or_efficiency": 1.00,
    "evidence_alignment": 0.70
  },
  "ai_risk": 0.20,
  "matched_rubric_items": [
    "使用了正确的判断条件",
    "正确更新了计数变量"
  ],
  "deduction_reasons": [
    "变量名与题干不完全一致",
    "边界条件解释不够清楚"
  ],
  "teacher_feedback": "答案整体思路正确，建议注意题干给出的变量名，并区分大于和大于等于的边界条件。"
}
```
