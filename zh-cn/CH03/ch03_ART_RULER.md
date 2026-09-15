# Chapter 3：使用 ART + RULER 训练数学 Agent

> 对应原 Notebook：[`CH03/ch03_ART_RULER.ipynb`](../../CH03/ch03_ART_RULER.ipynb)

## 这一节解决什么问题

这一 Notebook 展示如何把一个“会调用工具的 Agent”进一步训练成“更会完成任务的 Agent”。案例是 Countdown 风格的算术题：给定若干数字和一个目标值，Agent 需要只使用允许的数字与 `+ - × ÷` 构造出精确命中目标的表达式。

整个流程把 **LangGraph** 用作 Agent 执行框架，把 **OpenPipe ART（Agent Reinforcement Trainer）** 用作训练与轨迹管理框架，再用 **RULER** 提供软质量评分。

核心思想不是“直接监督最终答案”，而是：

> 让 Agent 多次实际完成任务，记录完整 rollout（轨迹），再根据结果和过程给 reward（奖励），用这些 reward 反向改善模型。

---

## 1. 数据集与任务结构

Notebook 使用 Countdown 数据集，并划分为：

- 约 5,000 条训练样本；
- 100 条测试样本。

每条任务包含：

- 一组可使用的数字；
- 一个目标值；
- Agent 需要构造出的合法算术表达式。

任务看似简单，但非常适合作为 Agent 训练案例，因为它同时具备：

1. **结果可以确定性验证**；
2. **中间过程允许多种策略**；
3. **工具调用可以真实参与推理**；
4. **可以明显区分“答对了”和“过程质量好不好”**。

这正好对应后面的 hard reward + soft reward。

---

## 2. Agent 获得哪些工具

Notebook 给 Agent 准备了若干专用工具，而不是让它只靠纯文本猜答案。

典型职责包括：

- 读取当前题目的数字与目标；
- 搜索或辅助构造可能的解；
- 提交最终表达式。

最终答案通过一个结构化对象保存，例如：

```python
class FinalAnswer(BaseModel):
    answer: str
    source_ids: List[str]
```

其中：

- `answer` 保存最终表达式；
- `source_ids` 用于记录来源和轨迹关联。

这种设计的意义是把“模型说了什么”与“系统认可的最终答案”分开。只有显式调用最终答案工具，结果才进入后续 judge 和 reward 计算。

---

## 3. 确定性 Judge：先判断有没有真正答对

这一案例最重要的基础设施不是 LLM Judge，而是 deterministic judge（确定性判定器）。

Judge 会检查：

- 表达式能否正常解析；
- 是否只使用允许的运算；
- 是否精确等于目标值；
- 给定数字是否被合法使用；
- 每个数字是否没有被超次数使用；
- 是否存在除零等非法操作；
- 是否试图通过不受允许的 Python 语法“作弊”。

这里的原则非常重要：

> **凡是可以通过程序确定验证的指标，就优先不要交给 LLM 判断。**

对于数学正确性，程序 Judge 比 LLM Judge 更便宜、更稳定、更可复现。

---

## 4. Rollout：训练的基本单位不是答案，而是一次完整经历

ART 中的 **rollout（轨迹 / 回合）** 可以理解为 Agent 从拿到题目到最终结束的一次完整运行。

一次 rollout 通常包含：

```text
任务输入
  ↓
模型思考 / 决策
  ↓
工具调用
  ↓
工具返回
  ↓
继续推理
  ↓
提交最终答案
  ↓
Judge / Reward
```

因此，训练数据不只是：

```text
question -> answer
```

而更接近：

```text
state -> action -> observation -> action -> ... -> reward
```

这使训练能够针对 Agent 的实际行为，而不是只针对静态文本输出。

Notebook 用 LangGraph 构建 Agent，并通过 ART 的包装层记录这些执行轨迹。

---

## 5. Hard Reward：正确性是第一道门

每个 rollout 首先通过前面的确定性 Judge。

如果最终表达式非法或结果错误，就不能因为“推理写得漂亮”而获得高分。

因此这里有一层 hard correctness signal（硬正确性信号）：

```text
correct / incorrect
```

它负责回答：

> 这次任务到底有没有完成？

Hard reward 提供训练的底线约束。如果没有这一层，只依靠 LLM Judge，模型可能学会生成看起来很有道理、但实际上算错的过程。

---

## 6. RULER：为什么已经有正确性，还需要软评分

仅判断“答对 / 答错”仍然不够。

两个 Agent 都答对时，它们的轨迹质量可能完全不同：

- 一个过程简洁、工具调用合理、很快找到正确答案；
- 另一个反复试错、产生大量无效步骤，最后偶然答对。

因此 Notebook 引入 **RULER** 作为 learned evaluator（学习型评估器），对一组 rollout 做更细粒度的质量排序和评分。

代码中通过类似：

```python
ruler_score_group(group, ruler_model_id, debug=True)
```

对同组轨迹进行评价。

RULER 主要回答的是：

> 在都完成或都部分完成任务的情况下，哪条轨迹更值得模型学习？

因此可以把两个 reward 信号理解为：

- **Hard Judge**：有没有做对；
- **RULER**：做得好不好。

---

## 7. 为什么要 Group Scoring，而不是单条独立打分

RULER 的一个重要思想是 group scoring（组内评分）。

与让 Judge 对每条轨迹单独给“7.4 分”相比，把多个候选轨迹放在同一个上下文中做比较通常更稳定。

原因是模型更擅长回答：

> “A、B、C 三个方案里哪个更好？”

而不一定擅长回答：

> “A 的绝对质量到底应该是 7.1 还是 7.8？”

因此，RULER 更适合生成 relative preference（相对偏好）和排序信号。

这种信号之后可以用于强化学习、偏好优化或其他 trajectory-level training。

---

## 8. Reward 不是单一分数，而是多层质量信号

Notebook 的训练逻辑可以概括为：

```text
完成一批 rollouts
       ↓
确定性 Judge
       ↓
生成 correctness / metrics
       ↓
按组送给 RULER
       ↓
获得软质量评分
       ↓
组合 reward
       ↓
更新模型
```

这比简单地“LLM Judge 给一个总分”更可靠，因为不同评价职责被拆开了。

推荐的设计原则是：

1. **能确定计算的，做 deterministic metric**；
2. **需要语义判断的，再交给 learned evaluator**；
3. **不要让软评分推翻硬约束**；
4. **保留分项指标，而不仅保存最终 reward**。

这样训练失败时才知道问题出在正确性、效率、工具使用还是 Judge 本身。

---

## 9. ART 在这里承担什么角色

ART 可以理解为训练 Agent 的一层 orchestration framework（编排框架）。

它主要把下面几件事串起来：

- 运行 Agent rollout；
- 保存 trajectory；
- 对轨迹挂载 reward 与 metrics；
- 按 batch 组织训练数据；
- 调用本地可训练模型；
- 执行后续训练 / 优化；
- 记录实验过程。

Notebook 示例使用本地 backend 和可训练的 Qwen2.5-7B-Instruct。

这说明 ART 的关注重点不是重新发明 Agent runtime，而是连接：

```text
Agent runtime <-> trajectory <-> reward <-> training
```

LangGraph 负责“Agent 怎么运行”，ART 负责“这些运行结果怎么变成训练信号”。

---

## 10. 为什么测试集必须和训练过程分开

训练结束后，Notebook 会在未见过的测试题上重新运行 Agent。

这是为了防止把“记住训练题”误认为“Agent 能力提升”。

至少应该分开观察：

- train reward；
- train accuracy；
- test accuracy；
- rollout 长度；
- 工具调用次数；
- RULER score 分布。

如果 reward 持续上涨，但测试正确率没有同步提升，就说明模型可能在优化 Judge 偏好，而不是真正学会解决任务。

这也是 reward hacking（奖励投机）最常见的预警信号之一。

---

## 11. 生产与研究中的适用边界

ART + RULER 最适合：

- Agent 能够重复执行大量任务；
- 可以记录完整 trajectory；
- 存在明确或半明确的评价标准；
- 希望优化的不只是最终文本，而是工具使用与多步行为。

不一定适合：

- 数据量极少；
- 没有稳定 evaluator；
- 每次任务都完全不同且不可比较；
- 任务风险很高但 reward 无法准确表达业务目标。

尤其要警惕：**训练最终优化的是 reward function，而不是你脑中真正想要的目标。**

因此 reward 设计本身就是 Agent training 中最核心的产品与工程问题之一。

---

## 12. 可以迁移到其他 Agent 项目的方法

这个 Countdown 案例虽然是数学题，但方法可以直接迁移到搜索、研究、代码、数据分析和业务流程 Agent：

1. 把任务拆成可以重复运行的 rollout；
2. 对能程序化判断的结果建立 hard checks；
3. 对主观质量建立 RULER / LLM Judge；
4. 保存完整 trace，而不只保存 final answer；
5. 对多条候选轨迹做相对排序；
6. 将 reward、metrics 和 trajectory 一起进入训练；
7. 始终用独立测试集验证能力是否真正提升。

---

## 核心结论

这一 Notebook 最值得掌握的不是 Countdown 算术本身，而是一条完整的 Agent 学习闭环：

**执行（rollout） → 可验证结果（hard judge） → 软质量比较（RULER） → reward → 训练 → 独立测试。**

LangGraph 提供可执行的 Agent，ART 把执行轨迹变成可训练数据，RULER 则补充那些无法只靠确定性规则表达的质量差异。三者结合后，Agent 才从“写 Prompt 调模型”进一步进入“基于真实行为持续优化”的阶段。