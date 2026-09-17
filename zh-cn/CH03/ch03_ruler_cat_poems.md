# Chapter 3：RULER 轨迹评分示例中文说明

> 对应原 Notebook：[`CH03/ch03_RULER_cat_poems.ipynb`](../../CH03/ch03_RULER_cat_poems.ipynb)
>
> 本页翻译并整理原 Notebook 中的 Markdown 与解释性内容。代码本体、API 名称、函数名和运行输出保持英文，方便与原示例对应。

## 这个 Notebook 在做什么

这个示例演示如何使用 [OpenPipe ART](https://art.openpipe.ai/getting-started/about)（Agentic Reinforcement Tuning，智能体强化调优）框架中的 [RULER](https://art.openpipe.ai/fundamentals/ruler) reward model，对语言模型输出进行自动评估与排序。

Notebook 选择了一个非常简单的任务：让模型写“以猫为主题的诗”。为了把评分逻辑讲清楚，它没有先训练模型，而是人工准备了三条不同质量的响应轨迹（trajectory）：

- **高质量回答**：符合主题，完成度高；
- **中等质量回答**：基本完成任务，但质量一般；
- **偏题回答**：与任务要求明显不一致。

随后把这几条轨迹组成一个 group，交给 RULER 自动评分，并按照 reward score 排序。

## 为什么这里强调 Trajectory

在 Agent 系统里，最终答案并不总能完整描述一次运行质量。一个 Agent 可能最终给出了勉强正确的答案，但中间调用了错误工具、绕了很多无效步骤，或者在关键节点做出了差的选择。

因此 ART 使用 `art.Trajectory` 表示一段完整的模型交互历史和 completion。它关注的不是孤立的一句话，而是一条“模型经历了什么、最后输出什么”的轨迹。

这也是 Agent 评估和普通文本分类之间的重要差异：前者往往需要评估**过程 + 结果**。

## Notebook 展示的三个核心能力

### 1. 定义和组织 Trajectory

每条 `art.Trajectory` 都可以保存模型消息历史和最终 completion。这样，后续 reward model 可以对多条完整运行路径进行统一比较。

这为后续强化学习或偏好优化提供了天然的数据结构：训练对象不再只是 prompt/answer pair，而可以是完整的 agent trace。

### 2. 使用 `ruler_score_group`

Notebook 使用 `art.rewards` 中的 `ruler_score_group` 对同一组候选轨迹进行自动评分。

这里的关键不是给每个回答单独打一个“绝对分”，而是把具有可比性的候选放进同一 group，让 evaluator 更容易判断谁更好、谁更差。

对于许多开放式任务，这种相对评价往往比要求 Judge 精确判断“这是 7.3 分还是 7.8 分”更稳。

### 3. 根据 Reward 排序

得到 reward score 后，就可以对候选进行排序。

排序结果可以直接服务于：

- reinforcement tuning（强化调优）；
- preference modeling（偏好建模）；
- best-of-N 选择；
- 回归测试中比较不同版本 Agent 的行为质量；
- 找出表现差的轨迹，进一步做错误分析。

## 为什么要准备“高、中、低”三档样本

这个示例刻意选取质量差异明显的三条轨迹，是为了验证 evaluator 是否具备最基本的排序能力。

如果一个 reward model 连“明显优质回答”和“明显偏题回答”都不能稳定拉开，那么直接把它用于更细粒度的生产评估风险很高。

所以这种简单示例其实可以看作一种 **sanity check（合理性检查）**：先证明评估器方向上是对的，再进入更难的边界案例。

## 与普通 LLM Judge 的区别

RULER 在这里承担的仍然是 evaluator / reward model 的角色，但它被放进 ART 的 trajectory 与 tuning 工作流中，因此结果天然可以继续进入训练环节。

可以把两者理解成：

- 普通 LLM Judge：重点是“这次回答好不好”；
- RULER + ART：不仅要判断好不好，还要把评分结果组织成可以用于 Agent 轨迹优化和强化调优的数据。

## 关键代码术语中文对应

- `art.Trajectory`：模型/Agent 的完整响应轨迹。
- `ruler_score_group`：对一组可比较的轨迹进行 RULER reward 评分。
- `reward` / `reward score`：用于排序和训练的质量信号。
- `group`：一组应该放在一起比较的候选轨迹。
- ranking：按照 reward 从优到劣排序。

## 适用边界

这个猫诗示例故意非常简单，因此它证明的是“评分管线能工作”，而不是证明某个 reward model 已经足以评估复杂 Agent。

真正进入复杂任务时，还需要继续回答几个问题：

1. 同一 group 里的候选是否真的可比；
2. reward 是否和真实业务目标一致；
3. evaluator 是否会偏好表面更长、更像标准答案的输出；
4. 对工具调用、事实正确性、安全性等维度，是否需要额外 deterministic checks；
5. reward 在不同任务分布上是否稳定。

## 一句话理解

这个 Notebook 的价值，是把“人工觉得哪个回答更好”转成了一个可编程的流程：**把 Agent 运行表示为 trajectory → 按组交给 RULER 评分 → 按 reward 排序 → 把结果继续用于选择、评估或强化调优。**