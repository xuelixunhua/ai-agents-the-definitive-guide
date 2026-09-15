# Chapter 9：AgentVista 多模型 Agent 评测

> 对应原 Notebook：`ch09/ch09_agentvista.ipynb`
>
> 本文是该 Notebook 的中文说明版。代码逻辑、API 名称、类名、函数名、模型标识和运行输出保持英文；专业术语首次出现时尽量保留中英文。

## 1. 这份 Notebook 在解决什么问题？

普通的大模型评测往往只比较“最终答案对不对”。但 Agent（智能体）任务通常还包含图像理解、Web Search、页面访问、代码执行、多轮推理等过程，因此只看最终答案会漏掉一个重要维度：**模型是怎样完成任务的**。

AgentVista 的重点，就是把这种更接近真实 Agent 工作流的评测做成可复现流程。Notebook 主要完成四件事：

1. 获取 AgentVista 数据集及其中的多模态样本；
2. 为不同模型配置相同的工具环境；
3. 在同一批分层抽样（stratified subset）上执行多模型评测；
4. 同时比较最终答案准确率（accuracy）与轨迹（trajectory），而不是只比较一条最终文本。

因此，它更像一个 **Agent benchmark harness（Agent 基准评测执行框架）**，而不是普通的问答测试脚本。

---

## 2. 环境准备：先固定评测框架，再换模型

Notebook 首先克隆 AgentVista 仓库并安装依赖。这里最重要的设计不是安装命令本身，而是把“评测逻辑”和“被评模型”分开。

评测框架负责：

- 读取数据；
- 提供工具；
- 驱动多轮 Agent 执行；
- 保存 `conversation_history`；
- 生成 `accuracy_score`；
- 记录并分析 `trajectory`。

模型只是被放入这套统一框架中接受测试。

这意味着在比较两个模型时，应该尽量只改变模型本身，而保持：

- 数据集相同；
- Prompt 相同；
- 工具权限相同；
- 最大轮数、重试等运行参数相同；
- Judge（裁判模型）与评分逻辑相同。

否则得到的差异无法确定到底来自模型，还是来自测试环境。

---

## 3. Judge：答案生成模型和评分模型要分开理解

Notebook 使用一个独立的 Harness LLM Judge（评测框架中的 LLM 裁判）来计算 `accuracy_score`：在 Agent 完成任务后，再将模型输出与 Ground Truth（标准答案）进行比较。

配置中区分了两类角色：

- `REASONING_*`：被评模型执行 Agent 任务时使用；
- `VERIFIER_*`：完成后用于验证答案的 Judge 使用。

例如 Notebook 会设置：

```python
os.environ["REASONING_END_POINT"] = OPENROUTER_CHAT
os.environ["VERIFIER_END_POINT"] = OPENROUTER_CHAT
os.environ["VERIFIER_MODEL_NAME"] = "gpt-5.4-mini"
```

这里要注意：**模型回答正确率并不是简单字符串匹配的同义词。** 对开放式答案、数字表达、多语言回答等任务，Judge 可以做一定语义判断。

但 Judge 也不是绝对真理。实际生产评测中最好把它与确定性规则结合，例如：

- 数字题使用 tolerance（容差）；
- 结构化输出验证 Schema；
- 可精确比较的任务优先 Exact Match；
- 只有开放式语义任务再交给 LLM Judge。

---

## 4. 工具环境：评的不是“裸模型”，而是 Agent

Notebook 为模型启用了统一的工具集合：

```text
web_search,image_search,visit,code_interpreter
```

这一步非常关键。AgentVista 的任务不是单纯测试参数记忆，而是测试模型能否：

1. 判断什么时候需要调用工具；
2. 选择正确工具；
3. 生成正确参数；
4. 理解工具返回结果；
5. 在多轮过程中把证据整合成最终答案。

因此，同一个模型可能“知识问答能力很好”，但在 AgentVista 中表现一般，原因可能不是知识不足，而是 Tool Use（工具使用）链条中的某一环出了问题。

这也是为什么后面必须保留 `conversation_history` 和 `trajectory_text`：只有这些过程数据才能帮助定位失败来自哪里。

---

## 5. 数据处理：不要随便抽样，要做分层抽样

Notebook 会下载 AgentVista 数据，并把 Parquet 中嵌入的图像安全导出为本地文件。之后构建一个用于横向比较的 stratified subset（分层子集）。

分层抽样的意义是：

> 不让模型成绩被某一个大量存在、但相对简单的任务类型“冲高”。

如果完整数据集包含 commerce、technology 等不同 Domain（领域）和 Subdomain（子领域），直接随机抽 15 条可能刚好大量集中在某一个类别。模型 A 和模型 B 的比较就会非常不稳定。

更合理的方式是尽量让测试子集覆盖多个任务类别，使不同模型面对同一套结构化分布。

Notebook 还会检查：

- 子集记录结构是否正确；
- 图像文件是否成功导出；
- 多模态输入能否正常加载。

这些 Validation（验证）步骤看起来琐碎，但对 benchmark 很重要：如果输入文件本身损坏，后面的“模型失败”就是假失败。

---

## 6. 先做 Sanity Run，再做完整模型比较

Notebook 没有直接把整个评测跑起来，而是先做小规模 Sanity Run（冒烟验证）。

它会先选择少量样本和第一个模型，验证：

- API 是否正常；
- Tool 是否能调用；
- Agent 是否能完成一整条轨迹；
- Judge 是否能够产生 `accuracy_score`；
- 结果是否能正确写盘。

结果中可以看到以下核心字段：

```text
question_id
prompt
final_answer
ground_truth
conversation_history
accuracy_score
trajectory_text
trajectory_score
trajectory_analysis
```

这一步非常值得保留。因为 Agent benchmark 往往包含多个外部服务，如果直接跑几十或几百条，最后才发现 API key、图像路径或工具配置有问题，会浪费大量时间和费用。

---

## 7. 多模型横向比较

Notebook 使用统一环境比较多个模型，当前示例配置包括：

```python
MODELS = [
    "openai/gpt-5.4",
    "qwen/qwen3.5-35b-a3b",
    "google/gemini-3.1-pro-preview",
]
```

这里的重点不是这些具体模型，而是比较方法：

```text
同一任务集合
    ↓
同一套工具权限
    ↓
同一运行参数
    ↓
模型 A / B / C 分别执行
    ↓
统一 Judge 与评分逻辑
    ↓
汇总 accuracy + trajectory
```

每个模型的结果单独写入自己的输出目录，之后再合并成 DataFrame 做统一比较。

Notebook 中的结果结构还会补充：

- `model`
- `domain`
- `subdomain`
- `pred_norm`
- `gold_norm`
- `accuracy_binary_exact`
- `accuracy_binary`
- `contains_match`

因此可以同时分析：

- 整体正确率；
- 各领域正确率；
- Exact Match 与宽松匹配的差异；
- Agent 最终答案与标准答案之间的系统性偏差。

---

## 8. 为什么要保留 Trajectory？

Trajectory（轨迹）记录 Agent 在完成任务时走过的过程，例如：

```text
用户问题
→ 搜索
→ 阅读页面
→ 继续搜索
→ 代码计算
→ 最终回答
```

两个模型即使最终答案都正确，轨迹质量也可能完全不同：

- 模型 A：2 次工具调用完成；
- 模型 B：反复搜索 10 次才完成；
- 模型 C：答案碰巧正确，但引用了错误证据。

因此 Notebook 同时保留：

- `trajectory_text`
- `trajectory_score`
- `trajectory_analysis`

这为后续进行 Agent 级评测提供了基础。

在生产环境中，还可以进一步扩展为：

- Tool Call Success Rate（工具调用成功率）；
- Average Turns（平均轮数）；
- Tokens / Cost（Token 与成本）；
- Time to Resolution（任务完成时延）；
- Unsupported Tool Call（无依据工具调用）；
- Evidence Quality（证据质量）。

---

## 9. 如何正确理解评测结果

Notebook 的某一次运行会打印具体 Accuracy，但不要把这些示例数字理解为模型的永久排名。

Agent benchmark 的结果高度依赖：

- 数据子集；
- Judge；
- Prompt；
- 工具实现；
- API 版本；
- 模型版本；
- 时间点；
- 外部网页环境。

因此真正应该保留的是 **Evaluation Protocol（评测协议）**，而不是某一次运行得到的排名。

如果后续替换模型，最好重新使用完全相同的：

```text
benchmark subset + tool configuration + evaluator + runtime parameters
```

这样成绩变化才具有可解释性。

---

## 10. 从 Notebook 迁移到生产评测系统

这份 Notebook 最值得复用的不是某一个函数，而是一套评测流水线：

```text
固定数据集
  ↓
验证输入
  ↓
Sanity Run
  ↓
多模型执行
  ↓
保存完整轨迹
  ↓
Final-answer Judge
  ↓
Trajectory Evaluation
  ↓
按模型 / 领域聚合
  ↓
模型替换决策
```

真正落地时建议再增加三层能力：

1. **版本固定**：记录模型版本、Prompt 版本、工具版本、数据版本；
2. **成本与延迟**：不能只看 Accuracy，还要看真实服务成本；
3. **失败样本沉淀**：将关键失败持续加入 Regression Benchmark（回归基准集）。

这样 AgentVista 才不只是一次性模型 PK，而会变成持续评测基础设施。

---

## 11. 这一章最应该记住什么？

Agent 评测的核心不是“谁答对得更多”这么简单，而是：

> **在统一任务、工具和评分协议下，同时评估结果质量与执行轨迹，才能判断一个模型是否真的更适合生产 Agent。**

这也是 Chapter 9 其他 Notebook —— LangSmith、Langfuse 外部评估以及 RULER trajectory ranking —— 的共同主线：从 Observability（可观测性）进一步走向 Evaluation（评估）和 Regression Testing（回归测试）。
