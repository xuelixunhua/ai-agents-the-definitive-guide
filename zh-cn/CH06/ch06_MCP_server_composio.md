# Chapter 6：Composio MCP——让 Agent 在大规模工具生态中发现、认证并组合工具

> 对应 Notebook：`ch06/ch06_MCP_server_composio.ipynb`
>
> 本文是该 Notebook 的中文说明版。代码逻辑、API 名称、类名、函数名及运行输出保持以原 Notebook 为准。

## 1. 这个 Notebook 在解决什么问题

当 Agent 只有一个工具时，问题很简单：模型决定“要不要调用它”。

但当 Agent 面对几十、几百甚至更多异构工具时，问题会变成：

- 我到底有哪些工具可用？
- 哪个工具适合当前任务？
- 工具之间怎样组合？
- 哪些工具需要认证？
- 认证连接什么时候建立？
- 多轮任务里，下一步该调用什么？

这个 Notebook 讨论的正是 **large tool ecosystems（大规模工具生态）**。

它不再把每个集成硬编码进 Agent，而是通过 Composio 根据自然语言 use case（使用场景）动态搜索相关工具，再把筛选出的工具交给 Agent。

核心关注点不是单次调用速度，而是四件事：

1. Tool Discovery（工具发现）；
2. Planning（规划）；
3. Authentication / Connection Management（认证与连接管理）；
4. Orchestration（编排）。

---

## 2. 从“会调用工具”到“会管理工具空间”

传统 Tool Calling 常见结构是：

```text
Agent
  ↓
固定的 tools=[tool_a, tool_b, tool_c]
  ↓
选择并调用
```

这在工具很少时很好用。

但工具数量继续扩大后，把所有 schema 一次性塞给模型会带来：

- 上下文变大；
- 工具之间语义高度相似；
- 模型更容易选错；
- authentication 状态复杂；
- 每个集成单独维护成本变高。

因此 Notebook 改成两阶段甚至多阶段过程：

```text
自然语言任务
   ↓
搜索 / 发现可能的工具
   ↓
筛选候选 toolkit / action
   ↓
检查连接与认证
   ↓
形成执行计划
   ↓
向 Agent 暴露必要工具
   ↓
执行
```

这意味着 Agent 的能力从 **tool calling（工具调用）** 升级为 **tool discovery + composition（工具发现与组合）**。

---

## 3. Composio 在这里扮演什么角色

Composio 可以理解成一个横跨大量应用集成的工具基础设施层。

Notebook 的重点不是要求你记住 Composio 的每个 API，而是理解它解决的结构性问题：

> 不再让 Agent 开发者为每个 SaaS / API 单独写工具，而是通过一个统一的工具生态去发现和接入能力。

因此 Composio 主要提供：

- toolkit / action discovery；
- 工具 schema；
- 应用连接；
- authentication；
- 大量第三方集成的统一访问面。

对 Agent 来说，真正重要的是：**工具空间变成可查询、可搜索、可动态装配的资源。**

---

## 4. `generate_scenarios` 为什么重要

Notebook 明确指出，`generate_scenarios` 是一个桥梁：

```text
Composio meta-tool schemas
        ↓
generate_scenarios
        ↓
更接近真实业务的 Agent tasks
```

也就是说，原始工具 schema 只告诉你“工具可以做什么”，但 Agent 真正面对的是自然语言目标，例如：

- 查找某类信息；
- 获取某个应用里的对象；
- 完成一串跨工具操作；
- 先发现再连接，再执行。

场景生成的作用是把底层工具能力映射成可测试、可规划的任务。

这也是工具生态评估的重要方法：不要只测试“API 是否能调用”，而应该测试“Agent 能否针对真实目标找到并正确组合这些 API”。

---

## 5. Tool Discovery（工具发现）

大规模工具系统最先遇到的不是执行问题，而是搜索问题。

Agent 必须先回答：

> “在这么多工具里，哪些和当前目标有关？”

理想流程是：

```text
用户需求
  ↓
自然语言 use case
  ↓
Composio Search
  ↓
候选 toolkit / actions
  ↓
缩小工具集合
```

这和 RAG 很像：不是把整个知识库都塞进上下文，而是先检索相关内容。

因此，大规模工具调用可以看成一种 **Tool Retrieval（工具检索）** 问题。

---

## 6. Tool Selection（工具选择）

发现候选工具之后，Agent 还需要选择。

这一步通常需要考虑：

- 工具是否真的能完成目标；
- 输入 schema 是否匹配当前已有信息；
- 是否需要额外 authentication；
- 是否存在能力重复的工具；
- 是否应该先调用 discovery 工具再调用 execution 工具；
- 当前连接状态是否满足执行条件。

在小规模 Agent 中，Tool Selection 只是一次模型选择；在大规模工具生态中，它更接近一个独立 planning 阶段。

---

## 7. Workflow Planning（工作流规划）

Notebook 强调 **planning before execution（先规划，再执行）**。

因为复杂任务往往不是单工具问题，而是：

```text
工具 A 的输出
  ↓
成为工具 B 的输入
  ↓
工具 B 的结果决定是否调用工具 C
```

因此 Agent 需要在执行前形成一个至少粗粒度的 workflow。

例如可以理解成：

```text
Goal
 ↓
Discover tools
 ↓
Check required connections
 ↓
Plan sequence
 ↓
Execute step 1
 ↓
Observe
 ↓
Re-plan if needed
 ↓
Execute next step
```

这也是为什么 Notebook 关注 **multi-turn tool reasoning（多轮工具推理）**，而不是“一次 function call 就结束”。

---

## 8. Connection Management（连接管理）

第三方工具往往需要用户授权。

因此“这个工具存在”不等于“现在能用”。

一个生产 Agent 至少要区分：

```text
Tool exists
Tool selected
Tool connected
Tool authenticated
Tool callable
```

连接状态是工具规划的一部分。

如果一个任务需要某个用户尚未授权的应用，系统不能简单地让工具执行失败，而应该：

1. 识别缺少连接；
2. 触发认证流程；
3. 等待用户完成授权；
4. 恢复原任务；
5. 再执行工具。

这与普通“函数调用”已经是完全不同的系统复杂度。

---

## 9. Multi-turn Tool Reasoning（多轮工具推理）

Notebook 关注的另一个重点是：Agent 不应该假设第一次规划就是正确的。

现实中经常出现：

- 搜索结果不够；
- 第一个工具返回的信息缺失；
- 需要换另一个 toolkit；
- 用户未认证；
- 某个 action 参数不足；
- 工具输出暴露了新的下一步。

因此运行流程应支持：

```text
Plan → Act → Observe → Re-plan
```

这本质上和 ReAct 类似，但行动空间不再是几个固定工具，而是动态变化的大规模工具集合。

---

## 10. 为什么不能一次把所有工具都给模型

这是大规模工具系统里非常重要的一点。

当工具越来越多时，问题不只是 token 成本，而是 **decision quality（决策质量）**。

大量 schema 同时暴露会导致：

- 工具描述相互干扰；
- 模型难以区分近义 action；
- 选择概率被稀释；
- 上下文窗口被工具说明占据；
- 规划和业务信息可用空间变少。

因此更合理的结构是：

```text
完整工具宇宙
   ↓ Retrieval
候选工具子集
   ↓ Selection
任务相关工具
   ↓ Execution
```

这和搜索引擎、推荐系统、RAG 的“先召回，再排序”非常相似。

---

## 11. 大规模工具生态中的几个关键失败模式

### 11.1 Tool Confusion

两个工具语义非常接近，模型选错。

解决方向：更好的工具元数据、retrieval、reranking 和候选集压缩。

### 11.2 Authentication Dead End

Agent 规划了某个动作，但执行时才发现用户没有连接应用。

解决方向：把连接状态提前纳入 planner。

### 11.3 Over-planning

模型一次性设计很长链路，但前面一步的结果变化后，后续计划全部失效。

解决方向：短规划 + 多轮重规划。

### 11.4 Tool Explosion

候选工具太多，上下文和决策质量急剧下降。

解决方向：tool retrieval + top-k selection。

### 11.5 Hidden Side Effects

有些工具看起来只是“获取信息”，实际可能创建、修改或发送内容。

解决方向：给工具增加 capability / risk category，并和 Chapter 6 的 governed execution 结合。

---

## 12. 与 MCP 的关系

MCP（Model Context Protocol）解决的是模型应用如何以统一方式接入外部能力。

Composio 这类工具生态进一步解决：

> 当外部能力很多时，如何发现、连接和组织这些能力。

因此可以把两者理解成不同层级：

```text
Agent
  ↓
Tool Discovery / Selection / Auth
  ↓
Composio-style integration layer
  ↓
MCP / tool protocol
  ↓
External apps and APIs
```

真正生产化时，还要再加入 Chapter 6 另一 Notebook 中的治理层：

```text
Discovery
  ↓
Planning
  ↓
Authentication
  ↓
Governance
  ↓
Execution
```

---

## 13. 和“固定工具 Agent”的根本区别

固定工具 Agent 的核心问题是：

> “我现在应该调用哪个工具？”

大规模工具 Agent 的问题则变成：

> “我需要什么能力？这个能力在哪里？它是否已经授权？应该和哪些能力组合？执行顺序是什么？”

这实际上把 Agent 从一个 tool user（工具使用者）变成了一个 **tool ecosystem navigator（工具生态导航器）**。

---

## 14. 生产化时应该补哪些能力

如果把 Notebook 思路真正放入生产系统，通常还需要：

- 工具检索索引；
- semantic tool search；
- top-k / reranking；
- tool capability taxonomy；
- authentication state cache；
- per-user connection state；
- tool versioning；
- timeout / retry / circuit breaker；
- sensitive action approval；
- budget / quota；
- audit logging；
- tool result normalization；
- fallback tool selection。

尤其要注意：**工具发现解决的是“能调用什么”，治理层解决的是“允许调用什么”。** 两者不能混为一谈。

---

## 15. 最值得记住的结论

这个 Notebook 的核心可以压缩成一句话：

> **现代 Agent 不只是调用工具，而是动态地发现、选择、认证、规划并组合工具。**

当工具数量从 3 个增长到 300 个时，系统架构必须从：

```text
Prompt + tools
```

升级为：

```text
Tool Retrieval
+ Selection
+ Planning
+ Connection Management
+ Multi-turn Reasoning
+ Governance
```

大规模工具生态真正困难的地方，不是“接口多”，而是**如何在巨大行动空间里保持正确选择、正确权限和正确执行顺序**。
