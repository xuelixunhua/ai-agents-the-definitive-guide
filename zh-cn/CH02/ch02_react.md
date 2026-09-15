# Chapter 2：ReAct —— 用 LangGraph 构建“思考—行动—观察”循环

> 对应原 Notebook：`CH02/ch02_react.ipynb`
>
> 本文件是该 Notebook 的中文说明版。代码逻辑、API 名称、类名、函数名和运行输出保持原样；专业术语首次出现时保留英文。

## 这个 Notebook 解决什么问题

它演示如何用 **LangGraph** 和 **LangChain OpenAI** 构建一个最小可运行的 ReAct 风格 Agent：模型可以根据问题决定是否调用工具，工具返回观察结果，模型再基于观察继续推理，直到给出最终答案。

这里的 ReAct 可以理解为一个显式循环：

```text
用户问题
  ↓
Agent 判断下一步
  ↓
需要工具？ ──否──→ 最终回答
  │
 是
  ↓
调用工具（Action）
  ↓
获得结果（Observation）
  ↓
回到 Agent
```

Notebook 还额外提供了一个可读的执行轨迹（trace），展示“工具选择 → 工具调用 → 工具结果 → 最终答案”，但不会暴露模型内部的私有思维链。

## Notebook 展示了什么

### 1. 带类型的 Agent 状态（Typed Agent State）

状态对象使用 `TypedDict` 定义，并通过 LangGraph 的 `add_messages` reducer 累积 `messages`：

```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
```

关键点不是 `TypedDict` 本身，而是：**每一轮模型消息和工具消息都会成为图状态的一部分**，后续节点可以继续读取。

### 2. 把工具绑定给模型（Tool Binding）

示例只定义了一个工具：

```python
internet_search(query: str) -> str
```

它通过 SerpAPI 搜索 Google，并把前几个结果整理成紧凑 JSON 返回。随后：

```python
TOOLS = [internet_search]
model = model.bind_tools(TOOLS)
```

绑定之后，模型并不是每次都必须调用工具，而是可以根据问题自行决定。

### 3. 一个只有两个节点的图

整个 LangGraph 只有两个核心节点：

1. `agent`：调用模型；
2. `tools`：执行模型发出的工具调用，并生成 `ToolMessage`。

这意味着 ReAct 并不一定需要复杂架构。最小结构就可以是：

```text
agent → tools → agent → tools → ... → END
```

### 4. 条件路由（Conditional Routing）

`should_continue` 检查最后一条 AI 消息是否包含 `tool_calls`：

```python
def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "continue"
    return "end"
```

如果模型想调用工具，就跳转到 `tools`；如果没有工具调用，就结束图。

这是整个 ReAct 循环里最核心的控制逻辑。

## 实际运行流程

Notebook 按下面顺序运行：

1. 安装 `langgraph`、`langchain-openai`、`python-dotenv` 和 `google-search-results`；
2. 从 `.env` 读取 `OPENAI_API_KEY` 和 `SERPAPI_API_KEY`；
3. 定义 `internet_search` 工具；
4. 构建 `StateGraph`；
5. 编译成可执行的 `graph`；
6. 调用：

```python
print_react_trace("What is the weather in Zurich today?")
```

这个问题需要最新天气，因此模型会选择调用搜索工具，而不是只依赖模型参数里的旧知识。

## 各节点在做什么

### Agent 节点

`call_model` 会把系统提示词和当前状态中的所有消息一起交给模型：

```python
response = model.invoke([SYSTEM_PROMPT] + state["messages"], config)
```

系统提示词主要要求：

- 必要时使用工具；
- 工具调用阶段保持简洁；
- 完成后给用户一个清晰的最终回答。

### Tools 节点

`tool_node` 会读取最后一条 AI 消息里的每个 `tool_call`：

```text
工具名
参数
调用 ID
```

然后按名称找到对应工具并执行，最终把结果包装成 `ToolMessage` 返回图中。

工具结果统一采用 JSON，是为了降低不同工具输出格式不一致带来的解析成本。

## ReAct 执行轨迹

`print_react_trace(question)` 会把图的执行过程打印成比较容易理解的形式：

```text
Question
↓
Reasoning Summary
↓
Action
↓
Observation
↓
Final Answer
```

这里的 `Reasoning Summary` 只是对外可展示的执行摘要，不等于模型隐藏的 Chain-of-Thought（CoT，思维链）。

这点很重要：

- **ReAct 的工程价值**在于把“调用什么工具、工具返回什么、最后怎么回答”变成可观察流程；
- 并不要求把模型内部详细思考过程暴露出来。

## 为什么这种模式有用

### 1. 控制流清晰

模型负责判断“下一步做什么”，LangGraph 负责决定“下一步去哪里”。两者职责分离：

```text
模型：提出动作
图：执行动作并控制流程
```

### 2. 工具调用可以测试

`internet_search` 是普通函数，`tool_node` 也是普通节点，因此可以单独测试，而不是把所有逻辑塞进一个巨大 Prompt。

### 3. 容易扩展

如果以后增加：

- 数据库查询；
- Python 计算；
- 文件搜索；
- 企业内部 API；
- 电力市场数据工具；

只需要把新工具加入 `TOOLS` 和 `TOOLS_BY_NAME`，ReAct 循环本身不需要重新设计。

## 代码中的关键注释翻译

### API Key 设置

原代码中的注释含义是：

- 推荐方式：在项目目录创建 `.env`；
- 也可以在 Notebook 中使用 `%env` 临时设置；
- 如果仍然找不到 Key，就交互式询问用户输入。

### `AgentState`

原注释：

> `add_messages is a reducer`

中文可以理解为：

> `add_messages` 是消息状态的归并器（reducer），用于把新消息追加/合并进已有消息序列。

### `internet_search`

该工具的职责是：

> 通过 SerpAPI 搜索 Google，获取最新信息，并返回紧凑 JSON 字符串。

### `tool_node`

该节点的职责是：

> 执行最后一条 AI 消息里产生的所有工具调用，并把结果包装成 `ToolMessage` 返回。

### 图像绘制异常

Mermaid 绘图是可选步骤；如果在线 PNG 渲染失败，可以使用：

```python
print(graph.get_graph().draw_ascii())
```

或：

```python
print(graph.get_graph().draw_mermaid())
```

然后把 Mermaid 文本粘贴到 [Mermaid Live Editor](https://mermaid.live/) 中查看。

## 适用边界

这个 Notebook 是一个**最小 ReAct 示例**，并不等于生产级 Agent。它没有重点处理：

- 长期记忆；
- 持久化 checkpoint；
- 工具权限治理；
- 工具调用重试；
- 超时与熔断；
- 多工具冲突；
- 评估与监控；
- Prompt Injection 防御。

因此它最适合用于理解 ReAct 的控制流，而不是直接照搬到生产环境。

## 可以怎样继续扩展

### 增加更多工具

把工具加入：

```python
TOOLS
TOOLS_BY_NAME
```

即可。

### 替换搜索后端

SerpAPI 可以换成任何能返回稳定结构化结果的搜索接口。

### 加入记忆

当前图没有持久化记忆。可以在 `compile()` 时加入 checkpointer，使不同 `thread_id` 拥有可恢复状态。

### 增加验证节点

如果最终答案需要更可靠，可以在模型结束之前加入：

```text
agent
↓
validator / verifier
↓
pass → END
fail → agent
```

这会把单纯的 ReAct 循环升级成更接近生产系统的“执行 + 验证”结构。

## 核心结论

这个 Notebook 最值得记住的不是某个具体 API，而是下面四件事：

1. **模型负责选择动作，图负责控制流程。**
2. **工具调用通过结构化消息进入状态，而不是靠字符串拼接。**
3. **ReAct 本质是一个循环，而 LangGraph 把这个循环显式化。**
4. **可观察的 Action / Observation 比暴露完整思维链更适合工程系统。**
