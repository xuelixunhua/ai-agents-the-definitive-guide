# Chapter 11：带记忆缓存的 Swarm Research Engine

> 对应原 Notebook：[`ch11/ch11_memoizing_swarm_research_engine.ipynb`](../../ch11/ch11_memoizing_swarm_research_engine.ipynb)
>
> 本文是中文说明版。保留原 Notebook 中的代码逻辑、API 名称、类名、函数名和运行输出；专业术语首次出现时保留中英文，便于直接与源码对照。

## 1. 这个 Notebook 解决什么问题

很多多智能体系统看起来“很聪明”，但运行一段时间后会暴露三个现实问题：

1. 不断重复同样的工具调用；
2. 对已经获得的信息反复推理；
3. 最后虽然产生了很多 trajectory，却没有真正形成结论。

这个 Notebook 构建了一个 **Progress-Aware + Memoizing Swarm Research Engine（进度感知 + 记忆缓存的群体研究引擎）**，目标不是让 Agent “多走几步”，而是让每一步都尽可能带来新的信息，并最终收敛成可解释的研究结论。

它把几个关键机制组合在一起：

- Progress Guard：判断工具调用是否真的带来了新事实；
- Synthesis Node：把研究轨迹转成最终判断；
- Content-hashed Facts：基于内容哈希去重事实；
- Honest Cache Metrics：区分真正节省成本的缓存命中与循环造成的假命中；
- State-change-aware Routing：状态没变化时强制换工具或终止；
- Exact / normalized / semantic memoization：对 planner decision 做多层缓存。

---

## 2. 为什么普通 Agent Cache 不够

最简单的缓存通常是：

```text
相同输入 → 直接复用旧输出
```

但 Agent 系统中的“输入”不是一个简单 prompt，而是一个不断变化的世界状态：

```text
task
+ current facts
+ evidence
+ available tools
+ previous actions
+ stale tools
```

因此两个看起来类似的请求，可能已经掌握了不同事实；而两个字符串不同的请求，也可能在语义上处于同一个决策状态。

所以这个 Notebook 的 memoization 并不是给最终回答做简单 KV cache，而是给 **planner decision（规划决策）** 做状态级缓存。

---

## 3. Fact：把“研究结果”变成可管理的数据结构

Notebook 不是把所有观察结果都塞进聊天历史，而是定义 `Fact` 对象。

一个 Fact 至少关心：

- `key`
- `value`
- `source`
- `confidence`
- `timestamp`

同时实现了：

- `canonical_key()`
- `canonical_value()`
- `_stable_value()`
- `to_text()`
- `to_dict()`
- `__hash__()` / `__eq__()`

这意味着事实不是“一段自然语言”，而是可以被：

```text
去重
比较
哈希
聚合
追踪来源
处理冲突
```

的结构化状态。

这是整个系统能做 memoization 的基础。

如果世界状态只是不断增长的 message list，就很难判断：

> 这一轮到底获得了什么新信息？

---

## 4. Content-hashed Search Facts：为什么不用位置编号

搜索工具常见的一种写法是：

```text
search_result_1
search_result_2
search_result_3
```

问题是搜索顺序一变，同一条信息可能得到不同 ID；不同搜索中的 `result_1` 又可能完全不是同一内容。

Notebook 改为根据内容生成 hash，例如：

```text
Fact("search_<hash8>", snippet, ...)
```

于是：

- 相同内容即使排序改变，也会得到相同标识；
- 不同内容不会因为位置相同而碰撞；
- 重复搜索结果可以稳定 deduplicate。

这个设计看起来很小，但它直接影响“新事实数量”的准确性。

---

## 5. WorldView：当前系统认为世界是什么样

系统不会简单地认为“最新得到的 Fact 一定正确”。它保留事实历史，并构造 `WorldView`。

`WorldView` 的作用可以理解为：

> 从全部历史证据中，提取当前 planner 应该看到的状态快照。

Notebook 对事实进行了规范化，并跟踪 evidence。

当同一个 canonical key 出现不同 value 时，系统能够识别 conflict，而不是无声覆盖。

当前值选择策略中使用“较新的 timestamp 优先，时间相同时 confidence 更高者优先”的规则。

这让 Planner 看到的不是混乱历史，而是一张当前世界状态表。

---

## 6. Fact Store：新增、强化、冲突、重复不是一回事

Notebook 对写入事实进行了分类：

```text
added
reinforced
conflict
duplicate
```

这四类事件非常重要。

### `added`

出现此前没有的新事实。

### `reinforced`

已有事实被新的证据支持。

### `conflict`

同一 canonical key 出现不同 value。

### `duplicate`

完全没有增加新信息。

系统维护 `version`，并在真正会改变 Planner 判断的事件上推进版本。

这样可以从“工具调用次数”转向“状态改变次数”。

这是 Progress-Aware Agent 的核心思想之一：

> **一次工具调用本身没有价值，改变世界模型才有价值。**

---

## 7. Progress Guard：防止 Agent 原地循环

Notebook 在每次工具调用前后比较事实集合。

概念上可以写成：

```text
facts_before = state.facts
call(tool)
facts_after = state.facts

new_facts = facts_after - facts_before
```

如果新增事实为 0，就记为一次 `no_progress_step`。

随后系统会：

1. 降低再次选择同一工具的机会；
2. 把该工具加入 stale / penalized tools；
3. 连续多次无进展时，强制进入 DONE 或 SYNTHESIZE。

Notebook 的设计中特别强调：连续 2 次 no-progress 后就不允许继续无限游走。

这本质上是 Agent 的 **circuit breaker（熔断器）**。

---

## 8. State-change-aware Routing：不是“调用没报错”就算成功

传统工作流常见逻辑：

```text
工具执行成功 → 回 planner
```

这里增加了一个更严格的判断：

```text
工具执行成功
    ↓
状态发生变化了吗？
    ├─ 是 → 可以继续规划
    └─ 否 → 换工具 / 终止 / synthesis
```

所以“HTTP 200”不是 Agent 意义上的成功。

真正的成功标准是：

> 是否增加了系统对任务的有效认知。

---

## 9. PlannerContext：缓存的不是 Prompt，而是决策状态

为了 memoize Planner，Notebook 构造 `PlannerContext`。

它会把规划真正依赖的信息集中起来，例如：

- task；
- 当前 `WorldView`；
- 可用工具；
- stale tools；
- evidence / constraints。

这样，缓存 key 就不会被无关的聊天格式或消息顺序轻易干扰。

这是一个非常可迁移的设计原则：

> **缓存 Agent 决策时，应缓存 decision-relevant state，而不是 raw conversation。**

---

## 10. 三层 Memoization：Exact → Normalized → Semantic

Notebook 对 Planner Cache 做了多层匹配。

### 10.1 Exact Hash

`_exact_hash()` 对当前状态做严格哈希。

适合：

```text
完全相同 task
+ 完全相同 facts
+ 完全相同工具约束
```

优点是安全、确定性强；缺点是命中率低。

### 10.2 Normalized Hash

`_normalized_hash()` 使用 canonical key/value 生成更稳定的表示。

它可以吸收一些：

- 大小写差异；
- key 格式差异；
- 等价的结构化表达。

命中率高于 exact，同时仍较保守。

### 10.3 Semantic Match

Notebook 进一步使用 embeddings，通过 cosine similarity 判断两个 PlannerContext 是否语义等价。

概念上：

```text
context → embedding
       ↓
与历史状态计算 cosine similarity
       ↓
score >= threshold ?
```

默认设计采用较高 threshold，例如 0.90，避免过度复用。

这一步的意义是：

> 即使文本不完全相同，只要 Agent 面对的是“同一个决策问题”，也可能直接复用 Planner decision。

---

## 11. 为什么 Semantic Cache 风险很高

语义缓存不是“相似就一定可以复用”。

例如：

```text
“该服务器是否暴露 443 端口？”
```

和：

```text
“该服务器是否只暴露 443 端口？”
```

embedding 可能非常相似，但决策含义不完全相同。

因此 semantic memoization 必须把以下内容一起纳入上下文：

- task；
- facts；
- evidence；
- available tools；
- constraints；
- stale tools。

并保持较高 similarity threshold。

安全敏感场景中，更应只对低风险 planner decisions 开启 semantic cache。

---

## 12. 为什么不能缓存 Invalid Planner Decision

Notebook 还对 planner 输出进行 `_validate_planner_decision()`。

这一步很关键，因为缓存会把一次错误放大成很多次错误。

因此流程应该是：

```text
Planner result
    ↓
validate
    ├─ valid → 可以 cache
    └─ invalid → 禁止写入 cache
```

这是所有 AI Cache 系统都应该遵守的原则：

> **先验证，再缓存。**

否则 cache 会成为错误的持久化层。

---

## 13. Tool Cache 与 Planner Cache 是两件事

Notebook 同时包含工具结果缓存和 Planner decision memoization，但两者解决的问题不同。

### Tool Cache

解决：

> 相同工具 + 相同参数，是否需要重复执行？

典型 key：

```text
tool_name + kwargs
```

### Planner Cache

解决：

> 在当前世界状态下，我是否已经做过同样的下一步决策？

典型 key：

```text
task + worldview + tools + constraints
```

不能混为一谈。

---

## 14. Honest Metrics：缓存命中率也可能骗人

这是 Notebook 最值得注意的部分之一。

普通系统看到：

```text
cache hit rate = 80%
```

往往会认为效果很好。

但如果 Agent 一直在同一个状态里循环，当然会不断命中缓存。

因此 Notebook 将命中拆成：

### `productive_hits`

缓存命中时，Agent 相比上一步已经获得新信息，当前命中确实避免了重复计算。

### `stale_hits`

缓存命中发生在与上一轮相同的状态中。

这往往说明 Agent 在循环。

### `no_progress_steps`

工具调用后新增事实为 0。

于是报告不再只展示：

```text
cache hit rate
```

而是同时观察：

```text
productive_hits
stale_hits
no_progress_steps
```

这可以区分：

> **真正的效率提升** 与 **循环造成的伪效率**。

---

## 15. Synthesis Node：研究系统必须给出结论

很多 research agent 最终输出的只是：

- 一堆网页；
- 一堆 snippets；
- 一串 tool trace。

Notebook 专门加入 `SYNTHESIZE` 阶段。

当 Planner 主动选择 DONE，或被 Progress Guard 强制终止后，会再调用一次独立 LLM，将当前事实综合为最终 threat assessment。

输出包括：

- verdict：`low / medium / high / critical`；
- confidence score；
- supporting evidence；
- gaps：仍然不知道什么。

这一步把系统从：

```text
Navigation Agent
```

变成：

```text
Research Engine
```

因为完成标准不再是“走完流程”，而是“形成基于证据的判断”。

---

## 16. 为什么 Gaps 很重要

一个成熟研究 Agent 不应该只输出“我知道什么”，还应该明确：

```text
我还不知道什么
```

Gaps 有三个作用：

1. 防止把缺少证据误写成确定结论；
2. 帮助用户判断 confidence 是否合理；
3. 可以作为下一轮 research 的任务输入。

因此 `gaps` 实际上是连接单轮研究与 iterative research 的接口。

---

## 17. 整个系统的运行逻辑

可以把 Notebook 的主流程压缩为：

```text
Task
  ↓
Build PlannerContext
  ↓
Planner memoization lookup
  ├─ hit → validate cached decision
  └─ miss → call planner → validate → cache
  ↓
Choose Tool / DONE
  ↓
Tool cache lookup
  ├─ hit → reuse facts
  └─ miss → execute tool → store facts
  ↓
Fact Store
  ↓
WorldView update
  ↓
Progress Guard
  ├─ new facts → continue
  ├─ no progress → penalize tool
  └─ repeated no progress → force terminate
  ↓
SYNTHESIZE
  ↓
Verdict + confidence + evidence + gaps
```

这是一个完整的闭环，而不是简单的“LLM + tools”。

---

## 18. 这个架构为什么能省成本

成本下降主要来自四个来源：

### 1. Tool-result caching

避免相同工具参数重复访问外部系统。

### 2. Planner memoization

避免在等价状态下重复调用 LLM 做相同规划。

### 3. Progress Guard

减少没有新增信息的工具调用。

### 4. Early termination

发现系统不再进步时尽早进入 synthesis，而不是耗尽 `max_steps`。

因此节省的不只是 token，还包括：

- 搜索 API 费用；
- 数据库查询；
- 网络延迟；
- sandbox compute；
- 整个工作流 wall-clock time。

---

## 19. 常见误解

### 误解一：Cache hit 越高越好

不对。stale hit 很高可能说明 Agent 正在原地循环。

### 误解二：只缓存工具结果就够了

不够。Planner 可能仍然对同一个世界状态反复推理。

### 误解三：Semantic Cache threshold 越低越省钱

命中会变多，但错误复用的风险也会快速上升。

### 误解四：DONE 就说明研究完整

不一定。DONE 只是流程终止信号，仍需要 Synthesis 输出 verdict、evidence、confidence 和 gaps。

### 误解五：新网页就等于新事实

不等于。多个网页可能只是重复同一信息，所以进度应该按 Fact / evidence 变化判断，而不是按 URL 数量判断。

---

## 20. 生产环境中还应补什么

Notebook 已经给出了很好的骨架，但生产系统还需要进一步增加：

1. **Cache TTL / freshness**：事实多久后必须重新验证；
2. **Namespace isolation**：不同用户、组织、任务之间不能误共享敏感缓存；
3. **Source trust score**：Fact 的 confidence 不应只由 Agent 自己生成；
4. **Invalidation**：外部世界变化后如何主动失效缓存；
5. **Cache observability**：记录 hit 来源、similarity、复用 decision、最终结果质量。

尤其是外部世界快速变化的研究任务，缓存必须有时间语义。

---

## 21. 可迁移的五条设计原则

1. **把事实变成结构化状态，而不是不断增长的对话文本。**
2. **以“状态是否改变”作为 Agent progress 的判断标准。**
3. **把 tool cache 和 planner memoization 分开设计。**
4. **缓存指标必须区分 productive hit 与 stale hit。**
5. **研究 Agent 的完成标准应是结论 + 证据 + 不确定性，而不是工具调用结束。**

---

## 22. 与 Chapter 11 其他 Notebook 的关系

本章三个主题实际上分别回答不同的成本问题：

```text
ch11_agent_cost_estimator_based_on_topology
→ Agent 拓扑本身会产生多少 API 成本？

ch11_memory_footprint_throughput_and_GPU_requirements
→ 自托管模型需要多少 GPU / KV Cache / 吞吐？

ch11_memoizing_swarm_research_engine
→ 如何通过缓存、状态去重和提前终止减少重复计算？
```

三者组合起来，就是完整的 Agent Economics（Agent 经济性）视角：

```text
架构成本
+ 推理基础设施成本
+ 运行时效率优化
= 单位成功任务成本
```
