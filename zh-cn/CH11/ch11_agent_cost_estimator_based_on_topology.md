# Chapter 11：基于 Agent 拓扑的成本估算器

> 对应原 Notebook：[`ch11/ch11_agent_cost_estimator_based_on_topology.ipynb`](../../ch11/ch11_agent_cost_estimator_based_on_topology.ipynb)
>
> 本文是中文说明版。保留原 Notebook 的代码逻辑、API 名称、类名、函数名与运行输出；专业术语首次出现时保留英文，便于与源码、文档和论文对照。

## 1. 这个 Notebook 解决什么问题

当我们讨论 Agent 系统成本时，只看“某个模型每百万 token 多少钱”是不够的。真正决定成本的是 **Agent 拓扑（agent topology） × 每个节点的调用次数 × 输入/输出 token × 缓存命中率 × 节点所用模型**。

同一个任务可以用 Single-shot、ReAct、Supervisor multi-agent 等不同架构完成。它们的差异不是单纯“多调用几次模型”，而是：

- 哪些步骤一定执行，哪些步骤条件执行；
- 每个步骤会执行多少次；
- 哪些步骤使用轻量模型，哪些步骤需要重型推理模型；
- 重复前缀是否能通过 Prompt / Prefix Caching 降低输入成本；
- 调用次数本身是否存在很大的波动区间。

因此，这个 Notebook 的核心目标是：**把 Agent 架构从抽象流程图转换成可计算的单位请求成本模型。**

---

## 2. 核心思路：把“架构”和“模型部署”拆开

Notebook 最重要的设计之一，是把两个问题分离：

1. **Architecture definitions：架构行为**
2. **Deployment profiles：模型部署方案**

这样做的好处是，你可以在不修改 Agent 流程本身的情况下，更换不同节点使用的模型，并直接比较成本变化。

### 2.1 Architecture definitions：只描述行为

`ARCHITECTURES` 中定义了三个示例：

- `Single-shot`
- `ReAct`
- `Supervisor multi-agent`

每个架构由若干 step 组成，每个 step 主要描述：

- `step`：步骤名称；
- `role`：该步骤所需的模型能力角色；
- `calls_per_request`：单次业务请求平均调用多少次；
- `calls_per_request_low / high`：调用次数的低/高区间；
- `input_tokens`：单次调用输入 token；
- `output_tokens`：单次调用输出 token；
- `cache_hit_rate`：输入 token 中预计由缓存命中的比例。

这里刻意不直接写死模型 ID，而是把模型抽象成 `routing_light`、`reasoning_medium`、`reasoning_heavy` 等角色。

这使架构定义回答的是：

> “这个系统怎样运行？”

而不是：

> “这个系统必须用哪个具体模型运行？”

### 2.2 Deployment profiles：角色映射到具体模型

`DEPLOYMENT_PROFILES` 再把角色映射到真实 provider / model。

Notebook 示例里包含两组 OpenAI 部署配置：

- `openai_default`
- `openai_cost_optimized`

默认配置中，`reasoning_heavy` 使用更强的模型；成本优化配置则把这一角色下调到更便宜的模型。

因此可以直接回答一个很现实的问题：

> 如果 Agent 拓扑不变，只把某个昂贵节点替换成更便宜的模型，整个系统每请求成本能下降多少？

---

## 3. 为什么调用次数是最重要的成本旋钮之一

对于 Agent 系统，`calls_per_request` 往往比单次 token 数更不稳定。

### Single-shot

Single-shot 基本固定为一次调用：

```text
user request → model → answer
```

所以成本比较稳定。

### ReAct

ReAct（Reason + Act）通常包含：

```text
planner
   ↓
tool reasoning loop × N
   ↓
final answer
```

其中 `tool_reasoning_loop` 的次数可能因任务难度而变化。Notebook 用 low / point / high 三档估计，把这种不确定性显式纳入成本模型。

例如：

- 简单任务可能只调用工具 1 次；
- 典型任务可能调用 3 次；
- 困难任务可能达到 8 次甚至更多。

因此只使用一个平均值，会掩盖高复杂度请求对预算的冲击。

### Supervisor multi-agent

Supervisor 架构中还存在条件执行节点，例如 specialist 或 critic。它们不一定每个请求都会运行，所以 `calls_per_request` 可以是 0.6、0.5 这样的期望值。

这本质上是在计算：

```text
期望调用次数 = 节点被触发的概率 × 被触发后的调用次数
```

因此拓扑中的“条件分支”最终也会转换为一个成本参数。

---

## 4. Prefix Caching 为什么必须进入成本模型

Agent 往往在连续多轮模型调用中重复发送大量相同内容，例如：

- system prompt；
- tool descriptions；
- schema；
- 安全规则；
- 前文上下文。

这些重复前缀可能被模型服务商的 **Prefix Caching（前缀缓存）** 命中。

Notebook 用 `cache_hit_rate` 表示输入 token 中可按缓存价格计算的比例。

因此一个 step 的输入成本并不等于：

```text
input_tokens × normal_input_price
```

而更接近：

```text
uncached_tokens × normal_input_price
+ cached_tokens × cached_input_price
```

其中：

```text
cached_tokens = input_tokens × cache_hit_rate
uncached_tokens = input_tokens × (1 - cache_hit_rate)
```

这意味着两个 token 总量相同的 Agent，其实际成本仍可能显著不同。

---

## 5. `genai-prices`：把价格表从业务逻辑中抽离

Notebook 使用 `genai-prices` 的 `calc_price()` 来完成价格计算。

代码还定义了最小的 `PricingUsage` 数据结构，把输入与输出 token 传递给价格计算模块。

这样做有两个价值：

1. 架构成本逻辑不需要硬编码具体价格；
2. 模型价格变化时，可以尽量让价格库负责更新，而不是到处修改业务公式。

从工程角度看，这是一种很重要的分层：

```text
Agent topology
    ↓
Token usage model
    ↓
Provider/model mapping
    ↓
Pricing engine
    ↓
Cost report
```

---

## 6. `estimate_architecture_costs()` 在做什么

Notebook 中的核心函数是：

```python
estimate_architecture_costs(
    architectures,
    deployment_profiles,
)
```

它可以理解为一个批量展开器。

对每个：

```text
deployment profile
    × architecture
        × step
```

逐层计算：

1. 调用次数；
2. 输入 token；
3. 输出 token；
4. 缓存后的有效价格；
5. step cost；
6. low / point / high 成本区间。

最后输出两层结果：

- **step-level**：查看每个步骤到底花了多少钱；
- **architecture-level**：汇总整个 Agent 的单位请求成本。

这两层必须同时保留。

如果只有总成本，你只能知道“贵”；有 step-level 才能知道“贵在哪里”。

---

## 7. Notebook 的示例结果应该怎样读

示例输出中，Single-shot 被设置为成本基准。

结果展示了两个非常典型的现象。

### 7.1 Agent 架构会放大 token 使用量

示例里：

- Single-shot 总 token 约为 4,200；
- Supervisor multi-agent 约为 13,185；
- ReAct 约为 13,850。

所以更复杂的 Agent 拓扑，在该假设下大约会消耗 Single-shot 的 3 倍左右 token。

但这并不等价于“成本一定是 3 倍”。

### 7.2 模型分配决定 token 与美元成本之间的映射

示例中 Supervisor multi-agent 在 `openai_default` 与 `openai_cost_optimized` 两种部署下，token 数完全相同，但成本明显不同。

原因是：昂贵的 `specialist_reasoner` 节点在成本优化方案中被映射到了更便宜的模型。

因此，一个关键结论是：

> **优化 Agent 成本不一定要改变 Agent 拓扑；先识别昂贵节点，再做 model routing，往往就能获得很大的收益。**

---

## 8. 三种架构的成本特征

| 架构 | 成本结构 | 主要不确定性 | 最值得优化的位置 |
|---|---|---|---|
| Single-shot | 单次模型调用 | 输入/输出长度 | 模型选择、Prompt 长度 |
| ReAct | planner + 多轮工具推理 + final | tool loop 次数 | 循环上限、缓存、终止条件 |
| Supervisor multi-agent | router + 多 Agent + synthesize | 条件节点触发率 | specialist/critic 的路由与模型选择 |

这张表比单纯比较“哪个 Agent 更贵”更有意义，因为三种架构的成本驱动因素不同。

---

## 9. 如何把这个估算器用于真实系统

Notebook 中使用的是人为设定的 token 与调用次数。真正上线后，应该用 traces 逐步替换这些假设。

推荐按以下顺序做：

### 第一阶段：设计期估算

在 Agent 还没上线时，填写：

- 预估 calls/request；
- 预估 input/output tokens；
- 条件节点触发概率；
- 预估 cache hit rate。

用于架构比较和预算评审。

### 第二阶段：灰度期校准

从真实 trace 中统计：

```text
P50 / P90 / P95 calls_per_request
P50 / P90 input_tokens
P50 / P90 output_tokens
真实 cache hit rate
节点触发率
```

将人工参数替换为真实分布。

### 第三阶段：持续成本治理

持续跟踪：

```text
$/request
$/successful task
$/user
$/workflow
$/agent node
```

尤其应该优先观察：

```text
cost per successful task
```

因为最便宜但经常失败的 Agent，并不是真正低成本。

---

## 10. 成本优化不能只看 token

这个 Notebook 是“成本估算器”，不是“架构优劣评估器”。

最终应该把成本与质量一起评估：

```text
quality
latency
reliability
cost
```

例如把一个 specialist 从强模型降级到 mini 后，每请求成本下降 50%，但如果准确率下降 15%，它可能不是好优化。

更合理的指标是：

```text
cost per successful task
cost per accepted answer
cost per resolved ticket
```

所以成本估算器最好与 Chapter 8 / Chapter 9 的 evaluation pipeline 联动。

---

## 11. 容易产生的误解

### 误解一：Agent 调用多，所以成本一定按调用次数线性增加

不一定。不同节点使用的模型不同，缓存比例也不同。

### 误解二：token 少的架构一定便宜

不一定。少量 expensive-model token 可能比大量 cheap-model token 更贵。

### 误解三：把平均 calls/request 填进去就足够

不够。Agent 的尾部任务可能有很深的循环，因此 low / point / high 或 P50 / P95 区间非常重要。

### 误解四：降低模型规格一定是最好的优化

模型降级可能导致错误率上升、重试增加，最终反而抬高成功任务成本。

### 误解五：缓存只是推理平台层的小优化

对于长 system prompt、复杂 tool schema、多轮 ReAct 来说，缓存命中率可能直接改变整个架构的经济性。

---

## 12. 可迁移到生产系统的五条原则

1. **Architecture 与 Deployment 解耦**：流程决定需要什么能力，部署配置决定用什么模型实现。
2. **成本计算必须做到 step-level**：先找到最贵节点，再优化整个系统。
3. **调用次数使用分布而不是单点平均值**：尤其关注循环型 Agent 的高分位成本。
4. **把 cache hit rate 作为一级参数**：长上下文 Agent 的成本不能忽略缓存。
5. **最终优化目标应是 cost per successful task**：不能只追求最低 token 或最低单次请求价格。

---

## 13. 与本章其他内容的关系

Chapter 11 的几个 Notebook 可以连成一条完整链路：

```text
Agent 拓扑
   ↓
每节点 token / 调用次数
   ↓
API 成本估算
   ↓
显存、KV Cache、吞吐量估算
   ↓
缓存 / memoization
   ↓
单位任务经济性
```

本 Notebook 重点回答的是：

> **如果使用 API 模型，这个 Agent 架构大约多少钱？**

而 `ch11_memory_footprint_throughput_and_GPU_requirements.ipynb` 更偏向回答：

> **如果自己部署模型，需要多少 GPU、显存和吞吐能力？**

两者合起来，才能比较 API inference 与 self-hosted inference 的真实经济性。
