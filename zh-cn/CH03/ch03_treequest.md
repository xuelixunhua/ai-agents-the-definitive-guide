# Chapter 3：TreeQuest（AB-MCTS）中文说明

> 对应原 Notebook：[`CH03/ch03_TreeQuest.ipynb`](../../CH03/ch03_TreeQuest.ipynb)
>
> 本页翻译并整理原 Notebook 中的 Markdown、解释性文字与关键代码注释。代码本体、API 名称、函数名与运行输出保持英文，以便与原示例逐行对应。

## 这个 Notebook 在做什么

这个示例演示如何使用 [**TreeQuest**](https://github.com/SakanaAI/treequest) 配合 **AB-MCTS 风格搜索（Monte Carlo Tree Search，蒙特卡洛树搜索）**，迭代改进一个由 LLM 生成的答案。

整个循环非常清楚：先生成初稿，再对答案进行改写；每个候选答案都交给一个结构化 Judge 打分；TreeQuest 在有限的搜索预算内不断扩展候选，并保留当前找到的最好结果。

它展示了四个核心点：

1. **树引导的答案改进（tree-guided refinement）**：动作空间很简单，先生成初稿，然后继续 refine。
2. **结构化评审（structured judging）**：让 LLM 以 JSON 结构返回 `[0, 1]` 之间的数值质量分数。
3. **有状态搜索（stateful search）**：使用 `treequest.ABMCTSA` 保存与扩展搜索状态，周期性查看当前最优答案，并在最后做 `top-k` 选择。
4. **角色分离**：生成器（generator）、改写器（refiner）、评审器（judge）和搜索控制器（search controller）相互独立。

## 运行流程

Notebook 的执行步骤是：

1. 安装 `treequest[abmcts-m]`，并配置一个兼容 OpenAI API 的 `OpenAI` client。
2. 为 MCTS 节点定义最小 `State`，只保存当前 `llm_answer` 和 `score`。
3. 实现四个函数：
   - `initial_generation()`：生成第一版答案并评分；
   - `refine_answer()`：基于已有答案继续改进，并重新评分；
   - `evaluate_answer()`：使用结构化响应评估答案质量；
   - `generate()`：作为 TreeQuest 扩展节点时调用的动作。
4. 创建 `algo = tq.ABMCTSA()`，运行一个较短的搜索循环，并在过程中输出当前最优候选。
5. 使用 `tq.top_k` 选出最终最佳答案。

## 核心机制

### 1. State：搜索树里到底保存什么

每个节点只保存两项内容：`llm_answer` 和 `score`。MCTS 使用分数完成节点选择和价值回传（backpropagation）。

这个设计很重要：搜索算法并不需要理解答案文本本身，它只需要知道“这个状态是什么”以及“这个状态值多少分”。因此 LLM 负责产生候选，搜索算法负责分配预算。

### 2. 初始生成与 Refine

`initial_generation()` 负责给任务产生第一版答案；`refine_answer()` 则要求模型在保留原任务的前提下，提高答案的清晰度和准确性。

因此这里的搜索空间不是“任意行动”，而是一个受限的 refinement space。它更像不断沿着“改写—评分—保留更优候选”的方向搜索。

### 3. Scoring：把 Judge 和 Generator 分开

`evaluate_answer()` 要求模型输出类似下面的结构：

```json
{"score": 0.92}
```

然后使用 Pydantic schema 解析结构化响应。

把 Judge 与生成模型的职责分开，可以减少“模型一边生成、一边给自己找理由”的耦合，也能让评分逻辑更容易独立替换、校准与审计。

### 4. TreeQuest / ABMCTSA

`ABMCTSA` 负责搜索控制，包括节点选择（selection）、通过 `generate()` 扩展节点（expansion）、可选的 rollout，以及数值回传。

`generate()` 返回两样东西：

- 新的 `State`；
- 父边对应的数值 value。

这个 Notebook 使用父节点已有的 score 作为边价值。对于仅做 refinement 的小型示例，这是一个足够简单且可工作的选择；但在复杂任务中，可以进一步设计更合适的 value 定义。

### 5. Top-k

搜索过程中周期性调用 `tq.top_k`，可以观察目前发现的最好候选；搜索结束后再调用一次，以得到最终赢家。

这与只保留单一“当前答案”不同：树搜索可以同时保留多个分支，避免过早把搜索锁死在一个局部方向上。

## 可以怎么扩展

原 Notebook 给出了几条很有价值的扩展方向：

- 加入 **self-consistency judge（自一致性评审）**，用测试用例或风格规范验证候选；
- 使用 **pairwise judge（两两比较评审）**，让 Judge 比较两个答案哪个更好，再把偏好转换为 MCTS 所需的分数；
- 增加 **rollout**，在真正评分之前连续做多次小步改写；
- 加入 **domain tests（领域测试）**，例如真正执行代码并核对输出；
- 持久化搜索树与 trace，便于复盘搜索预算到底花在了哪里。

## 关键代码注释中文对应

- `State`: MCTS 节点所保存的最小状态。
- `initial_generation`: 生成初始候选并立即评分。
- `refine_answer`: 基于已有候选继续改进，而不是从零重写。
- `evaluate_answer`: 只负责质量评估，不参与内容生成。
- `generate`: TreeQuest 的节点扩展动作。
- `top_k`: 从已发现的状态中选出分数最高的一组候选。

## 使用边界

这个示例的搜索深度和总步数都较小。扩大搜索预算时，API 调用成本会近似随节点扩展次数增加，因此不能只看“搜索效果”，还要同时看 token 成本和延迟。

生成阶段可以保持一定 temperature 来提供候选多样性，而 Judge 通常更适合较低 temperature，以提升评分稳定性。Judge 还必须真正支持结构化输出，否则 JSON/Pydantic 解析本身会成为新的失败点。

## 一句话理解

TreeQuest 在这里并不是“让模型想得更久”，而是把 **候选生成、外部评分和搜索预算分配** 组合起来，让模型在一个显式的搜索树中逐步找到更好的答案。