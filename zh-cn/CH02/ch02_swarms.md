# Chapter 2：Swarm —— 通过 Handoff 让多个 Agent 接力协作

> 对应原 Notebook：`CH02/ch02_swarms.ipynb`
>
> 本文件是该 Notebook 的中文说明版。代码逻辑、API 名称、类名、函数名和运行输出保持原样；专业术语首次出现时保留英文。

## 这个 Notebook 解决什么问题

它演示如何使用 `langgraph-swarm` 中的 `create_swarm`，把多个独立 Agent 组成一个可以互相**移交控制权（handoff）**的协作系统。

Notebook 只使用两个 Agent：

- `research_assistant`：负责搜索和抓取资料；
- `writer_assistant`：负责把已有材料整理成简洁答案；

默认由研究 Agent 开始。如果它已经收集到足够信息，就调用 handoff 工具把控制权交给写作 Agent；如果写作 Agent 发现材料不足，也可以把任务交还研究 Agent。

整体流程可以表示为：

```text
用户问题
  ↓
research_assistant（默认激活）
  ├── 搜索 / 抓取
  └── handoff → writer_assistant
                    ↓
              整理和写作
                    │
             资料不足？
               ├── 是 → handoff → research_assistant
               └── 否 → 最终答案
```

这和上一节的 Supervisor 架构不同：Swarm 不需要一个中央 Supervisor 每次决定“下一步谁来做”，而是由当前活跃 Agent 主动把任务交给最合适的下一个 Agent。

## Notebook 展示了什么

### 1. Agent Collaboration（Agent 协作）

两个 Agent 都通过 `create_react_agent` 构建，但各自有独立角色和工具：

```python
research_assistant
writer_assistant
```

研究 Agent 负责获取证据，写作 Agent 负责整理证据。两者不是共享同一套工具，而是按职责配置。

### 2. Default Active Agent（默认活跃 Agent）

创建 Swarm 时明确指定：

```python
default_active_agent="research_assistant"
```

因此每个新任务不会随机选择 Agent，而是先从研究 Agent 开始。

这相当于定义整个协作流程的默认入口。

### 3. Handoff Tools（移交工具）

Notebook 使用：

```python
create_handoff_tool(...)
```

分别创建：

```python
to_writer
to_research
```

它们不是普通业务工具，而是**控制权转移工具**。

例如：

```python
to_writer = create_handoff_tool(
    agent_name="writer_assistant",
    description="Transfer to the writing assistant to synthesize sources into an answer.",
)
```

含义是：

> 当前 Agent 如果判断研究材料已经足够，就可以主动把接下来的任务交给 `writer_assistant`。

### 4. Compile（编译）

Swarm 定义完成后调用：

```python
swarm = create_swarm(
    agents=[research_assistant, writer_assistant],
    default_active_agent="research_assistant",
).compile()
```

`.compile()` 会把 Agent、共享状态和 handoff 路由组合成一个可执行的 LangGraph 应用。

最终用户面对的是一个 `swarm`，而不是分别手动调用两个 Agent。

## 两个 Agent 的具体职责

### Research Assistant

研究 Agent 拥有：

- `tavily_tool`：Tavily 网页搜索；
- `scrape_webpages`：抓取网页正文；
- `to_writer`：把任务交给写作 Agent。

Prompt 要求它：

1. 先搜索网页；
2. 找到 3–5 个较可靠来源；
3. 抓取关键页面获得细节；
4. 材料足够后交给 Writer。

这说明 handoff 并不是固定流程，而是 Agent 根据自己的完成状态决定何时触发。

### Writer Assistant

写作 Agent 只有一个控制类工具：

```python
to_research
```

它不能继续自己上网搜索，而是应该：

- 阅读已有 Documents 和消息；
- 合成简洁答案；
- 用站点名称做引用；
- 如果证据薄弱或不清楚，则把任务退回 Research。

这实现了一个很重要的权限原则：

> Writer 可以判断“证据不够”，但补证据的动作必须回到 Research Agent 完成。

## Swarm 与 Supervisor 的区别

这两个模式都可以做多 Agent 协作，但控制结构不同。

### Supervisor 模式

```text
Worker A
   ↑
Supervisor → Worker B
   ↓
Worker C
```

所有下一步选择都回到中心 Supervisor。

### Swarm 模式

```text
Agent A ──handoff──→ Agent B
  ↑                    │
  └──────handoff───────┘
```

当前 Agent 可以直接把控制权交给另一个 Agent。

因此：

- Supervisor 更像“中央调度”；
- Swarm 更像“专业人员之间直接转交工单”。

Swarm 的控制路径更短，但也更依赖每个 Agent Prompt 中对“什么时候应该移交”的定义。

## 工具设计

### Tavily Search

```python
tavily_tool = TavilySearch(max_results=5).as_tool()
```

提供最新网页搜索结果。

### `scrape_webpages`

该工具接受一个 URL 列表：

```python
def scrape_webpages(urls: List[str]) -> str:
```

通过 `WebBaseLoader` 加载网页，然后把多个页面组织成：

```text
<Document name="...">
页面正文
</Document>
```

这种标签式包装可以帮助下游 Agent 区分不同来源。

### Handoff Tool

Handoff 工具最关键的不是返回业务数据，而是改变当前活跃 Agent。

因此应该把它理解成 orchestration primitive（编排原语），而不是普通 function calling。

## 实际运行案例

Notebook 的示例问题要求系统：

> 查找瑞士小型初创企业当前可用的 fintech 许可选项，收集权威来源，并给出三条简短总结和参考资料。

正常路径是：

```text
1. Research Assistant 接收问题
2. Tavily 搜索相关监管/许可资料
3. 抓取关键页面
4. 判断材料已经足够
5. handoff 给 Writer Assistant
6. Writer 汇总成最终答案
```

如果 Writer 发现来源不足，也可以触发：

```text
writer_assistant → to_research → research_assistant
```

形成多轮接力。

## 为什么这种模式有用

### 1. Agent 角色天然模块化

每个 Agent 都有独立的：

- Prompt；
- Tools；
- 角色；
- 交接条件。

以后可以增加：

- Reviewer；
- Validator；
- Editor；
- Compliance Agent；

而不必重写所有 Agent 的内部逻辑。

### 2. 不需要中央 Router

当任务比较像“专业工种之间接力”时，handoff 往往比中央 Supervisor 更自然。

例如：

```text
研究 → 写作 → 审核 → 发布
```

每个阶段最清楚自己什么时候完成，因此可以自己决定下一步移交。

### 3. 工具权限更容易隔离

研究 Agent 有搜索工具，写作 Agent 没有；写作 Agent 如果需要更多资料，只能回到研究 Agent。

这既减少误用，也让 trace 更容易解释。

### 4. 协作逻辑可以通过 Prompt 调整

例如可以规定：

- Research 至少拿到 3 个来源才能 handoff；
- Writer 发现引用不完整时必须退回；
- Validator 未通过时重新交给 Writer。

这种规则可以逐步形成更复杂的协作协议。

## 关键代码注释翻译

### API Key 设置

原注释的含义是：

- 推荐在 `.env` 中设置 `OPENAI_API_KEY` 和 `TAVILY_API_KEY`；
- 也可以直接在 Notebook 中用 `%env`；
- 如果仍然缺失，就提示用户手工输入。

### Tavily

原注释：

> Tavily web search

可理解为：

> 使用 Tavily 提供网页搜索能力。

### LLM 配置

原注释：

> Uses OpenAI through LangChain. Set OPENAI_API_KEY in your environment.

中文含义：

> 通过 LangChain 调用 OpenAI 模型，需要先在环境变量中设置 `OPENAI_API_KEY`。

## 生产化时要注意什么

### 1. Handoff 可能来回循环

如果 Research 总觉得“还不够”，Writer 也一直觉得“材料不够”，系统可能在两者之间不断往返。

生产系统应该考虑：

- 最大 handoff 次数；
- 最大总调用次数；
- 超时；
- 人工介入；
- 明确结束条件。

### 2. Prompt 就是路由策略的一部分

Swarm 没有单独 Supervisor，因此：

> “什么时候交给谁”很大程度写在 Agent Prompt 和 handoff tool description 中。

如果描述模糊，Agent 会出现过早 handoff、迟迟不 handoff 或错误交接。

### 3. Swarm 不是天然并行系统

虽然叫 Swarm（群体），Notebook 里的核心机制仍是**一个 Agent 当前活跃，必要时把控制权交给另一个 Agent**。

它不是“所有 Agent 同时独立运行再投票”。

### 4. 共享消息会不断增长

多个 Agent 都读取和写入同一任务历史时，上下文可能越来越长。长任务需要考虑摘要、裁剪或持久化记忆策略。

### 5. 外部网页内容仍然是不可信输入

Research Agent 会抓取网页，因此网页文本可能包含错误信息、诱导信息甚至 prompt injection。生产环境应增加来源白名单、内容过滤和工具调用策略。

## 最容易理解错的地方

### 1. `create_swarm` 不是自动“智能协作”

真正决定协作质量的仍然是：

- Agent 的职责定义；
- Tool 权限；
- Handoff 描述；
- 完成条件。

`create_swarm` 只是提供了把这些 Agent 组织起来的机制。

### 2. Handoff 和 Tool Call 不是完全一回事

实现形式看起来都像工具调用，但普通 Tool 处理业务动作，Handoff Tool 主要改变**谁拥有下一轮控制权**。

### 3. Swarm 不一定比 Supervisor 更高级

它们解决的是不同组织问题：

- 需要集中调度、明确全局计划时，Supervisor 更合适；
- 角色之间可以按完成状态直接移交时，Swarm 更自然。

### 4. 默认 Agent 只是入口，不是永久负责人

`default_active_agent` 只决定任务从谁开始，并不意味着它控制整段执行。

## 什么时候适合使用 Swarm

更适合：

- 角色之间存在清晰“交接点”的工作流；
- 不想为每一步都设置中央 Supervisor；
- 每个 Agent 都能判断自己什么时候完成；
- 需要按角色隔离工具权限；
- 希望系统容易增加新角色。

不太适合：

- 必须有一个全局规划者持续掌控全流程；
- 需要复杂优先级调度；
- Agent 之间职责高度重叠；
- handoff 条件很难定义；
- 对成本和延迟要求极低的简单任务。

## 一句话总结

**Swarm 的核心不是“很多 Agent 同时工作”，而是让当前 Agent 在合适的时机通过 Handoff 把控制权交给另一个专业 Agent，从而形成模块化的接力式协作。**
