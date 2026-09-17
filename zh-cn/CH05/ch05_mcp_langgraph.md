# Chapter 5：MCP + LangGraph 中文导读

对应原 Notebook：[`CH05/ch05_mcp_langgraph.ipynb`](../../CH05/ch05_mcp_langgraph.ipynb)

## 这个 Notebook 在解决什么问题？

假设你已经有一个 LangGraph Agent，现在想让它调用网页搜索、数据库、文件系统或外部 API。

最直接的做法，是把每一种工具都直接写进 Agent 代码里。但这样很快会遇到两个问题：

- Agent 与工具实现强耦合；
- 每新增一个外部能力，都要重新修改 Agent 本身。

**Model Context Protocol（MCP）**提供了一套标准接口，让工具与资源以统一方式暴露给 AI 应用。借助 `langchain-mcp-adapters`，LangGraph 可以直接接入 MCP Server，而不用把每一种外部服务的实现细节塞进 Agent 逻辑。

## Notebook 的 5 个重点

1. **MCP 基本原理**：MCP 是什么，以及为什么它值得存在；
2. **简单 MCP Server**：实现一个基础文件管理 Server；
3. **LangGraph 集成**：在 StateGraph Agent 中调用 MCP 工具；
4. **生产级案例**：使用 SQLite 库存管理器展示 Typed IO、安全与治理；
5. **第三方 MCP Server**：展示如何快速接入外部 MCP 服务。

## 最值得记住的 4 条实践原则

### 1. Transport 要按使用场景选择

- `stdio`：适合本地开发、单用户、本机工具；
- HTTP / Streamable HTTP：更适合 Web 服务、多用户与远程部署。

关键不是“哪个协议更高级”，而是工具运行在哪里、谁需要访问它。

### 2. 并发安全必须在工具层处理

当 Agent 可能并行调用工具时：

- 不要默认共享一个全局数据库连接；
- SQLite 可以启用 WAL 模式改善并发；
- 更新操作尽量使用原子操作，避免竞态条件。

模型本身无法替你解决数据库并发问题。

### 3. 治理应该放在 MCP Server 边界，而不是寄希望于模型自觉

如果某个操作“不应该被执行”，正确做法通常是：

> 在工具接口或 MCP Server 侧明确禁止，而不是在 Prompt 里告诉模型“请不要这样做”。

因此，MCP Server 不只是“工具适配层”，也可以成为多 Agent 系统里的**权限与治理边界**。

### 4. 输入输出都应 Typed

Notebook 推荐使用 Pydantic 对输入和输出建立明确 schema。

这样做的价值包括：

- 明确工具契约；
- 尽早发现字段错误；
- 避免静默失败；
- 让 Agent 更容易判断工具返回值是否有效；
- 方便测试与评估。

## 用一句话理解 MCP

可以把 MCP 理解成：

> **AI 世界里的“统一外设接口”——Agent 不需要知道工具内部怎么实现，只需要知道它遵循什么标准、提供什么能力。**

但要注意，MCP 解决的是**连接与标准化问题**，并不会自动解决权限、安全、业务正确性和工具可靠性，这些仍然需要系统设计者自己负责。
