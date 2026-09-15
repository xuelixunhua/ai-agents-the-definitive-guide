# Chapter 6：LangGraph + E2B——把代码执行放进隔离沙箱

> 对应 Notebook：`ch06/ch06_langgraph_E2B.ipynb`
>
> 本文是该 Notebook 的中文说明版。代码逻辑、API 名称、类名、函数名及运行输出保持以原 Notebook 为准。

## 1. 这个 Notebook 在做什么

这个 Notebook 展示了三种层次逐步增强的 Agent 代码执行模式：

1. 一个单 Agent：先从 Web 获取数据，再用 Python 做分析和画图；
2. 一个多 Agent 工作流：Researcher 负责研究，Coder 负责写代码与执行；
3. 多个 E2B sandbox（沙箱）并行运行：为不同用户、会话或 Agent 上下文提供隔离环境。

这里最重要的主题不是“让模型写 Python”，而是：

> **当 Agent 需要真正执行代码时，如何把执行环境从主进程中隔离出去。**

E2B Code Interpreter SDK 提供带 Jupyter runtime 的安全云沙箱，Agent 可以在其中执行 Python、生成图表，同时避免代码直接运行在你的应用服务器进程里。

---

## 2. 为什么代码执行必须隔离

LLM 生成代码与普通文本生成有一个根本区别：文本错了通常只是答案错了，代码错了可能带来真实副作用。

如果直接使用本地 `exec()`、Python REPL 或宿主机 shell，那么 Agent 可能：

- 访问本地文件系统；
- 读取环境变量；
- 安装或执行任意包；
- 消耗大量 CPU / 内存；
- 创建无限循环；
- 对同一台服务器上的其他用户造成影响。

因此生产级 Agent 应尽量把“模型生成代码”和“代码真正执行”分成两个安全域。

Notebook 中采用的结构可以理解成：

```text
LLM / LangGraph
       ↓
生成 Python code
       ↓
e2b_code_interpreter(code)
       ↓
E2B Cloud Sandbox
       ↓
stdout / stderr / error / rich results
```

---

## 3. E2B Sandbox 的作用

Notebook 通过：

```python
sandbox = Sandbox.create()
```

创建一个长生命周期的沙箱，并在 Notebook 运行期间保持存活。

这带来一个很重要的能力：**执行上下文可以持续存在。**

例如 Agent 可以：

1. 第一次执行代码加载数据；
2. 第二次继续使用前面创建的变量；
3. 第三次修改图表；
4. 最后输出结果。

这比每次调用都新建临时 Python 进程更接近真正的“Code Interpreter”。

---

## 4. `e2b_code_interpreter` 工具

Notebook 把 E2B 封装成 LangChain Tool：

```python
@tool
def e2b_code_interpreter(code: str) -> str:
    global _last_execution
    _last_execution = sandbox.run_code(code)
    summary = {
        "stdout": _last_execution.logs.stdout,
        "stderr": _last_execution.logs.stderr,
        "error": str(_last_execution.error) if _last_execution.error else None,
    }
    return json.dumps(summary, indent=2)
```

这里有两个关键设计点。

### 4.1 返回结构化执行摘要

模型拿到的是：

- `stdout`；
- `stderr`；
- `error`。

这比把整个 Jupyter 对象直接塞回上下文稳定得多，也更容易让模型判断“代码是否成功”。

### 4.2 富媒体结果单独展示

图表、表格等 rich result 通过 `_last_execution.results` 单独渲染。

这等于把：

- **给模型看的机器可读结果**；
- **给用户看的富媒体结果**

分成两个通道。

这是 Agent 工程里很值得复用的设计。

---

## 5. Web Search + Code Interpreter

Notebook 同时接入 Web Search 工具，例如 Tavily：

```python
tavily_tool = TavilySearchResults(max_results=5)
```

也可以替换为 Exa 或 SerpAPI。

这形成了非常典型的“研究 + 计算”组合：

```text
用户问题
  ↓
Web Search 获取外部资料
  ↓
LLM 整理数据
  ↓
E2B 执行 Python
  ↓
统计 / 转换 / 可视化
  ↓
最终答案
```

这种能力比单纯 Retrieval 更强，因为模型不仅“找到了信息”，还能够继续计算、合并和生成图表。

---

## 6. 单 Agent 模式

单 Agent 方案里，同一个 Agent 同时拥有：

- 搜索工具；
- E2B Code Interpreter。

它可以自己决定：

1. 什么时候搜索；
2. 搜索多少次；
3. 什么时候开始写代码；
4. 代码报错后如何修改；
5. 什么时候停止执行并给出答案。

优点是结构简单，适合：

- 原型；
- 单一研究任务；
- 工具数量较少；
- 工作流边界不复杂。

缺点是所有职责集中在一个 Agent，随着任务复杂度增加，规划容易混在一起。

---

## 7. Multi-Agent：Researcher + Coder

Notebook 进一步展示多 Agent 协作：

```text
Researcher
   ↓
收集 / 整理事实与数据
   ↓
Coder
   ↓
编写并执行 Python
   ↓
结果
```

这种角色划分的意义不是让系统“看起来更 Agentic”，而是进行 **responsibility separation（职责分离）**。

Researcher 更关注：

- 信息是否完整；
- 来源是否足够；
- 数据是否适合分析。

Coder 更关注：

- 数据结构；
- Python 代码；
- 执行错误；
- 图表和计算结果。

当任务链变长时，这种分工通常比一个 Agent 同时承担所有责任更容易控制和调试。

---

## 8. 为什么要“一用户 / 一会话 / 一 Agent 一个 Sandbox”

Notebook 特别强调 **multiple sandboxes running in parallel（多个沙箱并行）**。

生产环境不能简单让所有用户共享同一个解释器状态。

否则可能出现：

- 用户 A 的变量被用户 B 看到；
- 文件在会话之间泄漏；
- 某个 Agent 修改了另一个 Agent 的环境；
- 一个长任务占满资源，影响所有请求。

因此常见的隔离粒度是：

```text
User / Session / Agent Context
           ↓
      独立 Sandbox
```

不同请求并发执行时，可以由不同 E2B Sandbox 提供隔离。

这本质上是在做 **execution tenancy（执行租户隔离）**。

---

## 9. Sandbox 生命周期是重要的系统设计问题

沙箱不是越长寿越好，也不是每次都重新创建最好。

### 长生命周期

优点：

- 保留变量和文件；
- 适合多轮分析；
- 减少冷启动。

缺点：

- 占用资源；
- 状态污染风险增加；
- 生命周期管理更复杂。

### 短生命周期

优点：

- 隔离边界更干净；
- 任务结束即可销毁；
- 更容易限制资源。

缺点：

- 每次都要重新初始化；
- 无法自然保留多轮上下文。

生产系统往往需要按 session 生命周期管理 sandbox，并设置 TTL、资源上限和显式销毁机制。

---

## 10. Web 数据进入代码执行前要考虑什么

Web Search 返回的是不受信任的外部内容。

如果直接让模型把网页文字转换成代码并执行，需要注意两类风险：

### 数据风险

网页数据可能：

- 缺失；
- 格式不统一；
- 单位不同；
- 时间口径不一致。

因此模型在分析前应该先规范化数据。

### Prompt Injection 风险

网页内容可能包含对 Agent 的恶意指令。

所以应该把“搜索结果作为数据”与“系统指令”严格区分，不能因为文本来自搜索工具，就默认可信。

Sandbox 可以降低代码副作用，却不能自动解决 prompt injection。

---

## 11. 结果通道的设计

Notebook 的 `_last_execution` 模式展示了一种简单但很实用的结果分层：

### 给 Agent 的结果

JSON summary：

```json
{
  "stdout": [],
  "stderr": [],
  "error": null
}
```

模型使用它判断下一步。

### 给用户的结果

通过 `display_last_e2b_execution()` 渲染：

- 图像；
- 表格；
- rich display；
- stdout / stderr。

生产系统通常也应该采用类似思想，把内部执行状态、Agent observation 和前端 artifact 分开管理。

---

## 12. 从 Demo 到生产需要增加哪些控制

E2B 提供了比本地直接执行更强的隔离，但 production-grade（生产级）Agent 仍需要额外治理：

- sandbox TTL；
- CPU / memory / runtime quotas；
- 最大代码执行次数；
- 网络访问策略；
- 文件大小限制；
- package 安装限制；
- secret 与 sandbox 隔离；
- 用户 / tenant 映射；
- 执行审计日志；
- artifact 持久化策略；
- 超时和失败后的强制销毁。

因此“用了 sandbox”不等于“安全问题解决了”，它只是把最危险的代码执行从主应用进程迁移到一个可控边界中。

---

## 13. 与本章其他 Notebook 的关系

Chapter 6 的几个 Notebook 实际上在共同回答一个问题：

> **Agent 获得外部工具和代码执行能力后，怎样让能力足够强，同时保持边界可控？**

可以这样理解：

- `ch06_programmatic_tool_calling_monty`：受控代码解释器如何编排工具；
- `ch06_langgraph_E2B`：代码执行如何放进外部隔离 sandbox；
- `ch06_A2A_MCP_Governed`：工具执行前如何加入治理层；
- `ch06_MCP_server_composio`：面对大规模工具生态，Agent 如何发现和组合工具。

四者合起来分别覆盖：**执行、隔离、治理、发现。**

---

## 14. 最值得记住的结论

这个 Notebook 最关键的工程思想可以压缩成一句话：

> **模型可以自由生成代码，但代码不应该自由地在宿主系统里执行。**

更完整地说，生产 Agent 应该把：

```text
Reasoning
Tool Selection
Code Generation
Code Execution
Artifacts
```

拆成不同边界，并对真正产生副作用的 **Code Execution** 施加独立隔离和资源治理。

E2B 在这里承担的，就是这条执行边界。
