# Chapter 2：CoT 风格数据分析 Agent

> 对应原 Notebook：`CH02/ch02_CoT.ipynb`

## 这份 Notebook 在解决什么问题

这份 Notebook 展示了一个小而完整的数据分析 Agent 模板：让模型通过工具调用驱动一个隔离的 Python REPL，读取 CSV、计算统计指标、生成图表，并把最终答案、图表和中间工具轨迹统一写回 LangGraph 状态。

这里的“CoT 风格（Chain-of-Thought style）”重点不是把模型内部推理过程暴露出来，而是**用系统提示明确约束分析步骤**，例如先描述数据、再找规律、最后总结，并把真正需要精确计算的部分交给可验证的 Python 工具。

## 核心架构

整个流程可以理解为四层：

1. **提示层**：系统提示规定分析结构，例如“描述 → 模式识别 → 总结”。
2. **Agent 层**：使用支持 Tool Calling 的 ReAct Agent，由模型决定什么时候调用 Python 工具。
3. **执行层**：`PyodideSandboxTool` 在 Pyodide/WASM 隔离环境里运行模型生成的 Python 代码。
4. **工作流层**：一个最小 LangGraph 节点负责调用 Agent，并把输出、工具轨迹和图表写入 state。

最终 state 里会保留：

- `messages`：消息历史；
- `output`：最终回答；
- `chart_path` / `chart_svg`：恢复出的图表；
- `intermediate_steps`：工具调用与 Observation。

## 为什么要用沙箱 Python REPL

数据分析 Agent 的关键风险在于：模型不仅生成文字，还可能生成并执行代码。如果直接在宿主机执行任意 Python，风险很高。

Notebook 因此使用 `PyodideSandboxTool`，把代码运行在隔离的 Pyodide/WASM 环境中。这个沙箱有自己的一次性文件系统，Notebook 主进程看不到沙箱内部直接写出的文件。

所以图表没有采用“在沙箱里保存 PNG，再让宿主读取”的方式，而是：

1. 在沙箱中生成 SVG 字符串；
2. 把 SVG 做 base64 编码；
3. 用约定好的 marker 包住后打印到 stdout；
4. 宿主进程从工具输出中提取并解码；
5. 再通过 `IPython.display` 在 Notebook 内联渲染。

这个细节很重要：它展示了**隔离执行环境与主流程之间如何安全传递结构化产物**。

## 运行步骤

### 1. 配置 API Key

优先通过 `.env` 或环境变量加载 `OPENAI_API_KEY`。若不存在，再交互式输入。

### 2. 安装兼容依赖

原 Notebook 会先卸载部分 LangChain / LangGraph 包，再安装固定版本，主要是为了避免 `langchain-sandbox` 与新版依赖之间的冲突。

当前代码仍使用 `create_react_agent`。在较新的 LangGraph / LangChain 版本中，官方已经更推荐 `from langchain.agents import create_agent`，因此运行时可能看到弃用警告，但不影响示例本身的逻辑。

### 3. 定义沙箱工具

`PyodideSandboxTool` 接收模型生成的 Python 代码，在隔离环境执行并捕获 stdout；出现异常时，把 traceback 作为 Observation 返回给 Agent。

### 4. 构建 Tool Calling Agent

Agent 的系统提示会要求它：

- 描述数据集；
- 找出明显模式；
- 计算必要统计量；
- 在指定 target column 存在时生成一张柱状图；
- 最后给出简短总结。

真正的数值计算和绘图由工具完成，而不是靠模型“心算”。

### 5. 包装为 LangGraph

Notebook 使用一个非常轻量的一节点图。节点内部：

- 调用 Agent；
- 提取最终消息；
- 收集工具调用与工具 Observation；
- 从 stdout 中恢复 SVG；
- 把所有结果重新写回 Graph State。

## 这个模式为什么有效

### 工具调用让计算可验证

LLM 很擅长组织语言和决定分析方向，但不适合承担精确计算。把统计和绘图交给 Python 后，每个数值都可以追溯到实际执行代码。

### LangGraph 负责“状态”，而不是替代 Agent

这个例子没有为了使用 LangGraph 而构造复杂图。图只有一个节点，作用只是把一次 Agent Run 变成可组合、可持久化、可扩展的工作流节点。

### 沙箱把能力和权限分开

模型可以“拥有写代码的能力”，但不意味着它应该直接拥有宿主机权限。Pyodide 让模型具备数据分析执行能力，同时缩小安全边界。

## 容易理解错的地方

### 1. CoT 不等于“把模型的内部思考过程打印出来”

这里的 CoT 更准确地说是**显式分析结构（reasoning scaffold）**：提示模型按步骤组织任务，并把可验证部分交给工具执行。

### 2. ReAct 与 CoT 不是二选一

这个 Notebook 实际上同时使用了两者：

- CoT 风格提示负责规定分析结构；
- ReAct / Tool Calling 负责“什么时候调用工具、拿到 Observation 后怎么继续”。

### 3. LangGraph 不是越复杂越好

只有一个节点仍然有价值，因为它为未来添加校验、格式化、审批、持久化等节点留下了标准接口。

## 生产化时应该怎么扩展

可以沿着以下方向扩展：

- 增加 SQL、文件上传、对象存储、Web 获取等工具；
- 在执行节点后增加结果校验节点；
- 对生成代码设置 CPU、内存、时间、网络和文件系统限制；
- 用容器或远程 Sandbox 替代 Pyodide；
- 对输出报告增加固定 Schema；
- 对工具调用和代码执行保留完整审计日志。

## 对原 Notebook 的代码阅读提示

阅读时重点看三处：

1. `PyodideSandboxTool` 如何把代码、stdout 和异常包装成工具接口；
2. 系统提示如何把“分析目标”与“沙箱交互协议”分开；
3. Graph Node 如何从 Agent 返回值里恢复 `output`、`intermediate_steps` 与 SVG。

这三处分别对应一个生产 Agent 最核心的三层：**能力定义、行为约束、状态编排**。
