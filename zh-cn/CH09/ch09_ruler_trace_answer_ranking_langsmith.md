# Chapter 9：RULER Trace Answer Ranking（LangSmith）中文译文

> 对应原 Notebook：`ch09/ch09_ruler_trace_answer_ranking_langsmith.ipynb`
>
> 本文件用于中文阅读；代码、API、类名、函数名与原 Notebook 保持一致。

## 在 Colab 中打开

原 Notebook 提供 Colab 运行入口。运行时应使用原始 Notebook，以保证代码与依赖环境一致。

## RULER Trace Answer Ranking（LangSmith）

这个 Notebook 会读取与 `ch09_example_external_evaluation_pipelines_langsmith.ipynb` **相同的一组 LangSmith 根级运行（root runs）**：使用相同的 **project**、相同的 **tag**（`ext_eval_pipelines`）、相同的 **filters**，并采用相同的 payload 解析方式。

需要特别注意：`ch09_example_external_evaluation_pipelines_new_.ipynb` 是 **Langfuse** 版本的 cookbook；这里的 RULER 只能看到写入 **LangSmith** 的运行记录。因此，要让这个 Notebook 正常工作，需要先运行 LangSmith 版的外部评估 Notebook，或者同时把 trace 写入 LangSmith，确保数据进入同一个 project。

## 这个 Notebook 在做什么

整体流程可以拆成四步：

1. **从 LangSmith 拉取 trace**：按项目、时间窗口和 `ext_eval_pipelines` 标签获取 root runs。
2. **筛选可比较样本**：只保留支持类 trace，并按 `workflow`、`required_step`、`expected_handoff` 等字段筛选。
3. **按场景分组**：通过 `scenario_group_id` 把同一任务下的多个候选答案放到一起，只有至少 3 条 trace 的分组才进入排序。
4. **调用 RULER 排序**：把同组答案交给 judge model，按照同一套 rubric 做相对排序，而不是分别给每个答案独立打分。

## 关键配置

原 Notebook 使用以下核心配置：

- `BATCH_SIZE = 10`：单次参与处理的 trace 数量上限。
- `TOTAL_TRACES = 100`：查询 LangSmith 时最多考虑的 root runs 数量。
- `EVAL_TAG = "ext_eval_pipelines"`：评估 trace 的统一标签。
- `WORKFLOW_FILTERS`：只评估 billing、shipping、returns、account_access 等指定工作流。
- `AGENT_TYPE_FILTERS`：只评估 triage_agent、billing_agent、returns_agent 等指定 agent 类型。

## Trace 获取与兜底策略

`fetch_support_traces()` 并不是只做一次查询，而是带有逐级兜底逻辑：

1. 优先使用 `has(tags, "ext_eval_pipelines")` 在服务端过滤；
2. 如果没有结果，则取消服务端 tag filter，改为拉取后在 Python 中检查标签；
3. 如果指定时间窗口仍没有结果，则把查询窗口放宽到最近 7 天；
4. 再没有结果时，则直接获取最近的 root runs，并提示检查 project 配置。

这种设计的目的，是区分“确实没有 trace”和“查询条件过严 / 项目配置不一致”这两类问题，避免评估脚本因为一个筛选条件就直接失效。

## 为什么要做场景分组

RULER 不是典型的 pointwise evaluator。它更适合做 **group ranking（组内排序）**：同一场景下给出多个候选答案，再比较哪个更好。

Notebook 中的默认分组键为：

```python
workflow :: required_step :: expected_handoff
```

如果 payload 自带 `scenario_group_id`，则优先使用该字段。

只有同一组中至少有 3 条 trace 时，才会进入 RULER。原因是只有一个或两个候选时，相对排序的信息密度太低，不利于稳定判断“什么样的答案更优”。

## RULER 的评估标准

原 Notebook 的 rubric 要求 judge 按以下维度排序：

- **Empathy（同理心）**：是否理解并回应客户当前处境；
- **Technical relevance（技术相关性）**：答案是否真正针对问题，而不是泛泛而谈；
- **Policy correctness（策略/规则正确性）**：是否遵循支持流程与业务规则；
- **Actionability（可执行性）**：是否给出清晰的下一步。

同时明确：

- 优先选择下一步更清晰的答案；
- 惩罚模糊、空泛、缺少具体动作的回答。

## 输出结果

`run_ruler()` 会为每条 trace 生成：

- `group_id`：所属比较组；
- `trace_id`：LangSmith trace 标识；
- `case_id`：业务样本 ID；
- `final_answer`：最终答案；
- `ruler_score`：RULER 得分；
- `ruler_explanation`：排序解释；
- `rank_in_group`：组内名次；
- `weak_answer_flag`：是否为本组最弱答案。

其中 `weak_answer_flag` 特别适合继续进入人工复核、错误分析或 benchmark 扩充流程。

## 这套方法的适用边界

RULER 更适合以下场景：

- 输出本身存在多个“都能接受”的答案，无法只靠唯一标准答案判断；
- 你更关心“哪个答案更好”，而不是“单个答案是否超过固定阈值”；
- 需要从生产 trace 中识别同类任务里表现最弱或最强的候选。

它不应该取代确定性检查。像 schema 是否有效、工具调用是否成功、重试次数是否越界这类问题，仍应优先用 hard checks 判断。RULER 更适合补充开放式质量维度。

## 对生产评估体系的意义

这个 Notebook 展示的是一种重要补充关系：

- **单条 trace 评分**回答“这一条是否合格”；
- **RULER 组内排序**回答“同一任务的多个候选中，哪个更好、哪个最弱”。

两者结合，可以把评估从静态 pass/fail 推进到“持续寻找更优策略与更弱样本”的阶段。
