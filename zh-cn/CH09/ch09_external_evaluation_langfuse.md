# Chapter 9：使用 Langfuse 构建外部评估流水线

> 对应原 Notebook：`ch09/ch09_example_external_evaluation_pipelines_Langfuse.ipynb`
>
> 本文是该 Notebook 的中文说明版。代码逻辑、API 名称、类名、函数名和运行输出保持不变；专业术语首次出现时尽量保留中英文。

## 1. 这份 Notebook 在解决什么问题？

Langfuse 很擅长做 Observability（可观测性）：它能记录 Agent 的延迟、工具调用、重试、输出和完整 Trace（轨迹）。

但“看见发生了什么”并不等于“知道系统是否仍然足够好”。当你替换模型、修改 Prompt、改变路由逻辑或工具编排后，还需要回答另一个问题：

> 新版本是否仍然满足业务自己的质量标准？

这份 Notebook 给出的答案是：

```text
Langfuse 负责存 Trace 和筛选样本
        ↓
外部 Evaluator 负责真正的质量判断
        ↓
关键失败沉淀为可重放 Benchmark
        ↓
候选模型上线前统一回归测试
```

因此，这里最重要的思想是 **External Evaluation Pipeline（外部评估流水线）**：不要把全部评估逻辑锁死在观测平台内部，而是把 Trace 当作可复用的评测数据源。

---

## 2. 为什么只做 Tracing 不够？

Tracing 可以告诉你：

- 一次请求用了多久；
- 调用了哪些工具；
- 重试了多少次；
- Agent 最终输出了什么；
- 中间发生了哪些步骤。

但这些信息本身不能回答：

- 是否进行了正确的 Handoff（移交）；
- 是否完成了业务要求的关键步骤；
- 工具虽然被调用，但结果是否真的成功；
- 最终回答是否充分；
- 最终回答是否正确；
- 替换模型之后质量是提高还是下降。

所以 Observability 和 Evaluation 是两层能力：

```text
Observability：发生了什么？
Evaluation：发生得对不对、够不够好？
```

这也是整个 Chapter 9 的核心主线。

---

## 3. 一个好的评估系统，不应该只依赖 LLM Judge

Notebook 明确采用三类信号混合，而不是把所有判断都交给一个 Judge Model（裁判模型）。

### 3.1 Hard Checks：能写规则的，优先写规则

Hard Checks（确定性硬检查）适合直接验证：

- `retry_count <= max_retries`
- required tool calls succeeded
- escalation 需要发生时，必须出现正确 handoff label
- required workflow step 出现在 trajectory 中
- Schema 是否合法
- 数值是否落在允许 tolerance 中

这类判断的优点是：

- 可复现；
- 成本低；
- 不受 Judge 漂移影响；
- 错误原因明确。

原则可以概括成一句话：

> **凡是可以程序化验证的东西，就不要先交给 LLM。**

---

### 3.2 Structured Rubric：无法精确比较时，用结构化评分标准

对于“回答是否充分”“解释是否完整”这类问题，很难用 Exact Match（精确匹配）完成。

Notebook 因此引入 Rubric-based Check（基于评分标准的检查），例如：

- `final_answer_sufficient`
- `final_answer_correct`
- `task_completion`

Evaluator 返回的不应该只有一个数字，还应该保留 Reason（评分理由）。

这样后续看到 0.4 或 0.8 时，才能知道到底是：

- 信息缺失；
- 核心结论错误；
- 没有完成任务；
- 还是表达方式不同但本质正确。

---

### 3.3 Trace-level Judge：当“过程”本身决定成败时，再看完整轨迹

有些 Agent 失败无法从最终答案看出来。

例如：

```text
用户要求退款
→ Agent 没做权限检查
→ 直接调用退款工具
→ 最终告诉用户“退款已完成”
```

最终文本本身可能完全正确，但流程已经违反安全要求。

这时需要 Trace-level Judging（轨迹级评判），即把完整 trajectory 和明确的 Goal-achievement Rubric（目标达成评分标准）一起交给 Evaluator。

RULER 就属于这种思想的扩展：当单条绝对评分不足以区分多个候选轨迹时，可以进一步做 Relative Trajectory Ranking（相对轨迹排序）。

---

## 4. 准备可代表真实生产的 Trace

Notebook 用一个轻量 Support Agent（客服智能体）工作流生成示例 Trace。

每条 Trace 不只是包含输入输出，还包含足够支持评估的结构化字段，例如：

- retry count；
- handoff target；
- required steps；
- tool outcomes；
- final answer；
- reference answer；
- agent type；
- scenario group。

真正进入生产环境后，不需要人工重新造样本，而应该从 Langfuse 中拉取真实 Trace。

但“取最近 100 条”通常还不够，应该按发布决策需要做 Representative Sampling（代表性采样），例如按：

- 时间窗口；
- Tag；
- Workflow；
- Agent Type；
- 业务场景；
- 高风险用户群；
- 已知失败类型。

否则评测结果可能很好看，但根本没有覆盖最重要的线上场景。

---

## 5. 外部评分：把 Langfuse 当 Trace Store，而不是唯一 Judge

Notebook 的核心评估步骤可以概括为：

```text
fetch traces
    ↓
parse / normalize payload
    ↓
hard checks
    ↓
rubric / external judge
    ↓
aggregate scores + reasons
```

一个 Trace 最终会得到多维 Score，而不是只得到单一“总分”。例如：

```text
correct_handoff
required_step_completed
final_answer_sufficient
final_answer_correct
task_completion
```

这种多维结构比单一 Accuracy 更有价值，因为它可以告诉你：

> 新模型到底在哪一层变好了，又在哪一层退化了。

例如一个模型可能：

- Final Answer 更准确；
- 但 Handoff 错误率更高；
- Tool Call 次数更多；
- Task Completion 反而下降。

如果只看最终文本，很容易做出错误上线决策。

---

## 6. 为什么评分逻辑要放在 Langfuse 外面？

Notebook 并没有要求评估系统完全依赖 Langfuse 内置评分功能。

这样做有三个好处：

### 可迁移

Evaluator 可以独立运行，即使以后更换 Trace 平台，评分逻辑仍能保留。

### 可版本化

评估代码可以进入 Git，与业务代码一起进行版本控制和 Code Review。

### 可组合

你可以同时组合：

- Python deterministic checks；
- DeepEval；
- 自定义 LLM Judge；
- RULER；
- 业务数据库中的 Ground Truth。

Langfuse 更像数据和可视化层，而不是质量定义本身。

---

## 7. 可选步骤：把外部 Score 写回 Langfuse

外部评分完成后，可以选择把结果重新写回 Langfuse。

Notebook 强调：这一步是 Optional（可选）的。

如果希望评估系统保持完全独立，那么在本地或自己的数据仓库保存结果即可；如果希望运维、研发和产品能在同一个界面中同时看到：

- Trace；
- 失败原因；
- Numeric Score；
- Boolean Check；
- Evaluator Comment；

那么把 Score 回写 Langfuse 会非常方便。

因此 Langfuse 在这里扮演两个角色：

```text
Trace Store
+
Score Visualization / Filtering Layer
```

而不是必须承担所有评分计算。

---

## 8. 最关键的一步：把失败样本升级为 Benchmark

Notebook 把这一部分称为从 Tracing 到 Regression Testing（回归测试）的“缺失桥梁”。

一次失败 Trace 如果只是留在日志里，价值很有限；真正有价值的是把它转换成可以重复执行的 Benchmark Case（基准测试样本）。

Notebook 会将 Critical Failure（关键失败）写入 `benchmark_set.jsonl`，并保留：

- workflow metadata；
- payload；
- reference answer；
- prior scores；
- evaluator notes；
- scenario group；
- benchmark type。

逻辑变成：

```text
线上失败
  ↓
复盘
  ↓
确认是关键失败
  ↓
加入 benchmark_set.jsonl
  ↓
以后每次模型 / Prompt / Agent 改动都重新跑
```

这会形成一个非常重要的飞轮：

> **系统犯过一次的错误，尽量不要再犯第二次。**

---

## 9. 用 Benchmark 做模型替换前回归测试

有了可重放 Benchmark 后，新模型不能只靠少量 Spot Check（抽查）决定是否上线。

正确流程应该是：

```text
候选模型 A / B / C
        ↓
重新执行同一批 benchmark cases
        ↓
使用同一套 evaluator
        ↓
比较各维度指标
        ↓
决定是否替换生产模型
```

这里评估的不应该只有平均分，还应该至少关注：

- Critical Failure 是否重新出现；
- 高风险场景是否退化；
- Handoff 是否正确；
- Required Step 是否完成；
- Final Answer 正确率；
- Task Completion；
- 延迟与成本。

如果模型平均分提高，但关键业务流程出现 Regression（回归），仍然不应该直接上线。

---

## 10. DeepEval 与 RULER 分别适合什么？

Notebook 中隐含了两种不同评估思路。

### DeepEval：单条 Trace 的绝对评分

适合回答：

> “这一条回答是否足够、是否正确？”

它通常对每一条 Run 独立打分。

### RULER：多个 Trajectory 的相对排名

适合回答：

> “面对同一个任务，这几个候选 Agent 轨迹里谁更好？”

它尤其适用于多个结果都“看起来还可以”，但你希望从：

- Goal Achievement；
- Reasoning Path；
- Tool Efficiency；
- Output Quality；

等维度进行相对排序。

因此两者不是互相替代，而是不同层次：

```text
Hard Check
    ↓
Single-run absolute evaluation
    ↓
Multi-candidate relative ranking
```

---

## 11. 一个生产级外部评估系统应该长什么样？

可以把 Notebook 的思想扩展成下面这条完整链路：

```text
Production Agent
      ↓
Langfuse Trace
      ↓
Representative Sampling
      ↓
Deterministic Checks
      ↓
Rubric / LLM Evaluation
      ↓
Trajectory Evaluation
      ↓
Score Store + Langfuse Visualization
      ↓
Critical Failure Mining
      ↓
Regression Benchmark
      ↓
Candidate Model Replay
      ↓
Release Gate
```

其中 Release Gate（发布门禁）尤其重要：评估系统最终不应该只是生成一份报表，而应该能够真正阻止明显退化的版本进入生产环境。

---

## 12. 这一章最应该记住什么？

最重要的不是 Langfuse 某个 API，而是一条可迁移的方法论：

> **Trace 是评估的原材料，不是评估本身；确定性规则负责能精确判断的部分，Rubric/Judge 负责模糊语义，关键失败再沉淀为可重放 Benchmark，最终把模型替换从“主观感觉”变成可持续的回归测试流程。**

这也是 Chapter 9 中 LangSmith、Langfuse、RULER 与 AgentVista 几份 Notebook 最终汇合到一起的地方。
