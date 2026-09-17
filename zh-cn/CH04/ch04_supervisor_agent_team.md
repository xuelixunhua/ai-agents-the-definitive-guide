# Chapter 4：Supervisor Agent Team（主管式多智能体团队）

> 对应原 Notebook：`CH04/ch04_supervisor_agent_team.ipynb`

## 这份 Notebook 在解决什么问题

当一个复杂任务同时包含“检索、网页抓取、专利搜索、写作、文件操作、代码执行”等能力时，把所有工具和职责都塞进一个 Agent，通常会带来提示词膨胀、工具选择混乱、状态难追踪和权限边界模糊的问题。

这份 Notebook 展示了一种 **Supervisor Agent Team（主管式多智能体团队）** 架构：把任务拆成多个专业团队，再由上层 Supervisor 统一路由和协调。

## 整体架构

系统包含三层：

1. **Research Team（研究团队）**
   - 搜索互联网信息；
   - 抓取网页正文；
   - 使用 Exa 做语义搜索；
   - 通过 SerpAPI 查询 Google Patents。

2. **Document Writing Team（文档写作团队）**
   - 创建大纲；
   - 读取、写入和编辑文档；
   - 使用 Python REPL 做简单计算或图表；
   - 把最终结果持久化到工作目录。

3. **Top-level Supervisor（顶层主管）**
   - 在不同团队之间分配任务；
   - 汇总子团队返回的结果；
   - 判断是否继续调用某个团队，或结束整个任务。

可以把它理解为：

```text
用户任务
   ↓
Top-level Supervisor
   ├── Research Team
   │      ├── Search
   │      ├── Scrape
   │      ├── Exa
   │      └── Patent Search
   │
   └── Writing Team
          ├── Outline
          ├── Read / Write / Edit
          └── Python REPL
```

## 关键机制

### 1. Supervisor 是“路由器”，不是“大而全 Agent”

Supervisor 本质上是一个使用结构化输出的 LLM 路由器。它只负责在固定候选节点中选择“下一步去哪”，或者返回 `FINISH`。

这样做的好处是：

- 控制流显式；
- 路由结果更容易记录和审计；
- 不需要让顶层 Agent 自己执行所有底层工具。

### 2. Worker Agent 采用 ReAct 风格

每个 Worker 通过 `create_react_agent` 构建，只绑定自己需要的工具集。

例如研究团队中的 Worker 不需要文件写入权限，而写作团队中的 Worker 也不需要专利搜索能力。

这种 **Tool Scoping（工具范围约束）** 能减少：

- 无关工具干扰；
- 提示词长度；
- 越权调用风险；
- 工具误选概率。

### 3. 使用 State 显式传递信息

Notebook 使用 `MessagesState` 保存消息，并增加一个简单的 `next` 字段表示下一步路由。

跨节点状态更新通过 `Command(goto=..., update=...)` 实现：

- `goto` 决定跳转到哪个节点；
- `update` 把新的消息或状态写回图中。

因此，多 Agent 协作并不是“Agent 之间神秘对话”，而是一个有状态的图执行过程。

### 4. 子图组合（Subgraph Composition）

研究团队和写作团队分别编译成独立子图：

- `research_graph`
- `paper_writing_graph`

然后再由 `super_graph` 把两个子图组合起来。

这种方式的价值在于：子团队内部如何实现，可以与顶层编排解耦。后续可以替换某个团队，而不必重写整个系统。

### 5. 文件持久化与执行边界

Notebook 中的写作工具会直接操作 `WORKING_DIRECTORY`，并允许 Python REPL 执行代码。

这很方便，但也是生产环境里必须重点治理的部分：

- 文件系统工具应限制根目录；
- 不可信输入不应直接获得宿主机写权限；
- Python REPL 最好替换为沙箱执行器；
- 文件写入、代码执行等高风险动作应增加审计或审批。

## Notebook 中演示的典型流程

Notebook 依次展示：

1. 定义研究类工具；
2. 定义文档类工具；
3. 构建研究团队 Worker 与 Supervisor；
4. 构建写作团队 Worker 与 Supervisor；
5. 编译两个团队子图；
6. 再构建顶层 Supervisor；
7. 通过流式执行（streaming）观察每一步路由；
8. 使用 Mermaid 图查看每个子图与总图；
9. 最终完成一个端到端任务，例如生成带来源和专利链接的半导体白皮书并保存到文件。

## 为什么这种模式有效

它有效的核心不是“Agent 数量更多”，而是把复杂度分层：

- **职责分离**：每个 Agent 只解决一类问题；
- **控制流分离**：Supervisor 负责“谁做”，Worker 负责“怎么做”；
- **工具分离**：每个 Worker 只看到必要工具；
- **状态显式化**：消息和路由结果都进入图状态；
- **子图模块化**：不同团队可以独立测试和替换。

## 生产环境中的改进方向

### 增加引用校验器

研究团队把资料交给写作团队之前，可以插入 citation validator，检查：

- 链接是否有效；
- 引用是否支持对应结论；
- 是否出现“有结论、无证据”的情况。

### 替换危险执行能力

Notebook 使用 Python REPL 便于教学，但生产环境更适合：

- 容器沙箱；
- E2B 一类隔离环境；
- 资源配额；
- 网络/文件系统白名单。

### 增加 Checkpoint 与 Trace

可以结合 LangGraph Checkpointer 和 LangSmith：

- 记录每一步状态；
- 恢复中断任务；
- 追踪 Supervisor 为什么选择某个 Worker；
- 对失败路径做复盘和评估。

## 最容易误解的地方

1. **Supervisor 不是团队经理式的“高级 Agent”**：它更像一个结构化路由器。
2. **多 Agent 不等于更聪明**：如果任务本身不复杂，拆分过多反而增加延迟和错误传播。
3. **工具隔离比 Agent 数量更重要**：真正提升可靠性的关键之一，是让不同 Worker 只持有必要权限。
4. **子图并不是黑盒**：团队内部仍然是普通 LangGraph 节点和状态，只是在更高层被当作一个节点组合。

## 什么时候适合使用

更适合：

- 一个任务跨多个明显不同的专业步骤；
- 不同步骤需要不同工具和权限；
- 需要审计、重试、替换某个子模块；
- 单 Agent 工具过多，开始出现误选和提示词膨胀。

不太适合：

- 任务很短；
- 工具数量很少；
- 所有步骤高度耦合；
- 延迟要求极高，无法接受多轮路由。

## 一句话总结

Supervisor Agent Team 的核心，是用 **“顶层路由 + 专业子团队 + 显式状态 + 工具隔离”** 的方式，把一个大而混乱的 Agent 拆成可测试、可审计、可替换的多智能体工作流。
