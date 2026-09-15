# Chapter 2：分层 Agent 团队（Hierarchical Agent Teams）

> 对应原 Notebook：`CH02/ch02_hierarchical_agent_teams.ipynb`
>
> 本文件是该 Notebook 的中文说明版。代码逻辑、API 名称、类名、函数名和运行输出保持原样；专业术语首次出现时保留英文。

## 这个 Notebook 解决什么问题

它演示如何用 **LangGraph** 和 **LangChain** 把多个专长不同的 Agent 组织成一个分层团队：下层 Agent 负责具体任务，中层 Supervisor 负责给团队成员分工，最上层 Supervisor 再负责在不同团队之间协调。

Notebook 的完整案例把系统拆成两个团队：

- **Research Team（研究团队）**：搜索网页、抓取网页、做 Exa 语义搜索、搜索 Google Patents；
- **Document Writing Team（文档写作团队）**：生成提纲、读取/写入/编辑文件、运行 Python 做简单图表；
- **Top-level Supervisor（顶层主管）**：决定什么时候把任务交给研究团队，什么时候交给写作团队，以及什么时候结束。

可以把它理解成一个“经理—组长—专业员工”的组织：

```text
用户任务
   ↓
Top-level Supervisor
   ├── Research Team Supervisor
   │      ├── Search Agent
   │      └── Web Scraper Agent
   │
   └── Writing Team Supervisor
          ├── Doc Writer
          ├── Note Taker
          └── Chart Generator
```

核心目的不是“Agent 越多越好”，而是把复杂任务拆成**边界清晰、工具受限、可独立测试**的职责单元。

## Notebook 展示了什么

### 1. 两个专业化团队

研究团队拥有的工具包括：

- `tavily_tool`：网页搜索；
- `scrape_webpages`：读取网页正文；
- `patent_search`：通过 SerpAPI 的 Google Patents 搜索专利；
- `exa_search_tool`：通过 Exa 做 neural search（神经语义搜索）并返回高亮片段。

写作团队拥有的工具包括：

- `create_outline`：生成并保存提纲；
- `read_document`：读取文档指定行；
- `write_document`：写入完整文档；
- `edit_document`：按行号插入内容；
- `python_repl_tool`：执行 Python，用于计算或简单图表。

这种设计强调 **Tool Scoping（工具作用域限制）**：每个 Agent 只拥有完成自己职责所必需的工具，而不是把所有工具一次性暴露给所有 Agent。

### 2. Supervisor 不是普通聊天 Agent，而是 Router

`make_supervisor_node` 的核心职责是做结构化路由。它拿到：

```text
当前消息历史 + 固定的成员列表
```

然后输出：

```text
下一个 worker 的名字
或 FINISH
```

代码中通过动态定义的 `Router(TypedDict)` 约束输出：

```python
class Router(TypedDict):
    next: Literal[*options]
```

随后：

```python
response = llm.with_structured_output(Router).invoke(messages)
```

这比让模型自由生成“我觉得应该找研究员”更可靠，因为控制流需要的是一个明确枚举值，而不是自然语言。

### 3. Worker 使用 ReAct，但只负责一个窄任务

Notebook 通过 `make_react_worker_node` 创建 Worker。每个 Worker 都是一个 `create_react_agent`，但会被限制在：

- 固定名称；
- 固定工具集；
- 固定 Prompt；
- 固定返回路径。

Worker 完成自己的工作后，不直接决定整个系统下一步，而是把一个简洁结果写回 `messages`，再把控制权交回 Supervisor。

因此结构是：

```text
Supervisor
   ↓ 选择 worker
Worker
   ↓ 执行工具、生成结果
Supervisor
   ↓ 再次判断
...
```

这与单一 ReAct Agent 的差异在于：**局部推理交给 Worker，全局调度交给 Supervisor**。

## 三层图是怎么组合的

Notebook 最终会编译三个图：

### 1. `research_graph`

负责研究任务，包括搜索、网页抓取和专利搜索。

它内部有自己的 Supervisor，所以研究团队本身就是一个完整子图（subgraph）。

### 2. `paper_writing_graph`

负责写作、提纲、编辑和可选图表生成。

它同样是一个独立子图，并通过共享工作目录持久化文档。

### 3. `super_graph`

最外层图把前两个子图当作更高层的“团队节点”使用：

```text
START
  ↓
Top Supervisor
  ├── research_team
  ├── writing_team
  └── END
```

顶层 Supervisor 不需要知道研究团队内部用了 Tavily 还是 Exa，也不需要知道写作团队内部有几个 Agent。它只关心：

> 这个阶段应该让哪个团队处理？

这就是 **Hierarchical Composition（分层组合）** 最有价值的地方：上层只依赖下层团队的能力边界，不耦合内部实现。

## 状态和路由机制

### State

Notebook 在 `MessagesState` 基础上增加一个 `next` 字段：

```python
class State(MessagesState):
    next: str
```

`messages` 负责保存跨节点沟通内容，`next` 记录下一跳。

### Command

节点通过 `Command` 同时完成两件事：

```python
Command(
    goto=...,   # 下一步去哪
    update=...  # 同时写回哪些状态
)
```

这样“状态更新”和“控制流跳转”被放在同一个显式对象里，更容易审计和调试。

### 跨团队信息传递

Worker 会把自己的最终结果包装为一条消息写入共享状态，然后上层 Supervisor 再读取这些消息做下一轮判断。

因此这里不是 Agent 直接互相调用，而是：

```text
Agent 输出
   ↓
共享 State
   ↓
Supervisor 读取
   ↓
决定下一个 Agent/Team
```

## 文件持久化（Persistence）

写作工具统一操作 `WORKING_DIRECTORY`。例如：

- 提纲保存为文件；
- 最终报告写入磁盘；
- 后续 Agent 可以读取前一个 Agent 生成的文件继续编辑。

这解决了一个常见问题：长任务如果所有中间结果都只塞在 Prompt/消息历史里，既浪费上下文，也不利于复用。

Notebook 的最终案例会让系统生成一篇约 800 字的半导体白皮书，加入专利和来源，并保存为：

```text
semiconductor_whitepaper.txt
```

## 为什么这种模式有效

### 1. 责任分离（Separation of Concerns）

研究 Agent 不负责写作，写作 Agent 不负责搜索。职责越清楚，Prompt 和工具集越小，行为通常越可预测。

### 2. 局部复杂度被封装

顶层图不需要知道每个团队内部的细节。研究团队以后即使从 2 个 Agent 扩成 5 个 Agent，上层接口也可以不变。

### 3. 调度过程可观察

每次 Supervisor 都产生一个明确路由决定，因此可以在 trace 中看到：

```text
为什么去了 research_team
→ research_team 做了什么
→ 为什么又去了 writing_team
→ 为什么结束
```

### 4. 工具权限可以按角色控制

这比“一个超级 Agent 拥有所有工具”更容易做权限治理。例如写作 Agent 没必要拥有专利搜索 API，研究 Agent 也没必要拥有本地文件编辑能力。

## 安全和生产化边界

Notebook 本身明确提醒了两类风险。

### 文件系统风险

`read_document`、`write_document`、`edit_document` 能访问文件系统。示例通过 `WORKING_DIRECTORY` 限定工作目录，但生产环境仍应进一步使用容器或真正的沙箱。

### Python REPL 风险

`python_repl_tool` 会执行模型生成的 Python。原代码注释明确提醒：

> 在没有沙箱的情况下本地执行代码是不安全的。

生产环境不应该直接把任意模型代码交给宿主机 Python，而应使用受限执行器、容器或 sandbox。

### 外部结果的不确定性

搜索结果、网页内容、专利列表会随时间变化，因此 Notebook 的运行结果不保证每次一致。这类工具调用应该被当作外部不确定输入，而不是确定性函数。

## 关键代码注释翻译

### `WORKING_DIRECTORY`

原注释含义：

> 定义一个持久工作目录，并确保目录在执行前存在。

### `scrape_webpages`

职责：

> 抓取给定网页并把多个页面的正文拼接为一个字符串，供 Agent 后续阅读。

### `make_supervisor_node`

职责：

> 创建一个基于 LLM 的 Router，在固定 Worker 集合和 `FINISH` 中选择下一步。

### `make_react_worker_node`

职责：

> 创建一个带有限定工具和 Prompt 的 ReAct Worker；Worker 完成后把最终结果写回共享消息，并返回 Supervisor。

### LangSmith 提示

Notebook 建议使用 LangSmith 收集 trace，用于：

- 调试；
- 测试；
- 监控；
- 观察 LangGraph 的路由与工具调用。

## 最容易理解错的地方

### 1. Supervisor 不是“老板 Agent”那么简单

真正关键的是它把**路由决策结构化**。如果只是写一个 Prompt 让模型随便聊，仍然得不到可控的工作流。

### 2. 分层并不自动提高质量

增加层级会增加调用次数、延迟、成本和错误传播路径。只有当任务本身可以自然分解、角色边界明确时，分层才值得。

### 3. 子图不是另起一个完全独立系统

子图可以封装内部流程，但仍然需要设计清楚进入子图的输入、返回上层的输出以及跨层状态如何传递。

### 4. 多 Agent 不等于并行

这个 Notebook 的核心模式是 Supervisor 顺序路由。多个 Agent 代表职责拆分，并不意味着它们会同时运行。

## 什么时候适合使用这个模式

更适合：

- 深度研究 + 写报告；
- 数据获取 + 分析 + 审核；
- 多种工具权限需要隔离；
- 一个任务天然可以拆成多个专业团队；
- 需要清晰 trace 和审计链路的复杂工作流。

不太适合：

- 一两个工具就能完成的简单任务；
- 强实时、极低延迟场景；
- 任务无法明确拆分职责；
- 调用成本比模块化收益更重要的场景。

## 一句话总结

**Hierarchical Agent Teams 的核心不是“堆很多 Agent”，而是把复杂任务按职责拆成可独立运行的子图，再用结构化 Supervisor 在不同层级显式调度。**
