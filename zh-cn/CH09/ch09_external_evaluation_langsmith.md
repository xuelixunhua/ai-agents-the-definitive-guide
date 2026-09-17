# Chapter 9：使用外部评估流水线评估 LangSmith Agent Trace

> 对应原 Notebook：`ch09/ch09_example_external_evaluation_pipelines_langsmith.ipynb`
>
> 本文件用于中文阅读；代码、API、类名、函数名与原 Notebook 保持一致。

## 这份 Notebook 解决什么问题

这份 cookbook 展示如何把 **LangSmith** 用作 Agent 评估体系中的 trace 存储层、筛选层，以及可选的 feedback 层。示例默认使用美国区 LangSmith API：

```text
https://api.smith.langchain.com
```

Tracing 能告诉你“发生了什么”：例如延迟、工具调用、重试和最终输出；但 tracing 本身并不能回答一个更重要的问题：

> 换了模型以后，这个 Agent 是否仍然达到我们业务自己的质量标准？

因此，这份 Notebook 的核心不是“看 trace”，而是把 trace 进一步送进一条可重复的评估流水线：

1. 把代表性 trace 写入 LangSmith；
2. 拉取符合筛选条件的 root runs；
3. 在外部执行 hard checks、rubric checks 或 trace-level judge；
4. 必要时把评分结果作为 feedback 回写到 LangSmith；
5. 把关键失败样本沉淀成可重复执行的 benchmark；
6. 在模型替换或重新部署前，对候选版本统一回放比较。

## 不要把评估完全交给 LLM Judge

Notebook 中一个非常重要的设计选择是：**不要让整个评估体系只依赖 LLM judging。**

更稳健的做法是同时使用三类信号。

### 1. Hard checks

适合直接、确定性验证的条件，例如：

- 重试次数是否超预算；
- schema 是否有效；
- tool 是否成功执行；
- 是否出现要求的 handoff label；
- 数值是否落在允许误差范围内。

这些问题有明确答案，就没有必要交给 LLM 猜。

### 2. Structured rubric checks

用于判断充分性、完整性等不能只靠简单 if/else，但又希望按固定维度检查的问题。

### 3. Trace-level judge checks

当你关心的不只是最终答案，而是 Agent **走了什么路径**时，需要把整个 trace 纳入评估。例如：最终答案看似正确，但中间调用了不该调用的工具，或者绕过了某个审批节点。

这三类信号结合起来，才更接近生产环境中的真实评估体系。

## 学完这份 Notebook，你应该能做到什么

完成这份 cookbook 后，可以掌握以下完整链路：

- 用 tags 与结构化 outputs 把合成的 support-agent traces 写入 LangSmith；
- 通过时间窗口与 tag filter，从 LangSmith project 中拉取代表性的 **root runs**；
- 为 Agent workflow 和最终结果设计多层评估标准；
- 使用 hard checks、rubric checks，或二者组合在外部对 trace 打分；
- 使用 `deepeval` 等指标补充外部评估；
- 把 feedback 回写到 LangSmith，便于之后在 UI 中筛选；
- 把关键失败样本升级为可重复 benchmark；
- 在重新部署之前，用同一 benchmark 对候选模型做横向比较；
- 理解 **RULER-style group ranking** 如何补充逐 trace 的评分；
- 理解 **conditional tracing** 如何把 observability 与合规、租户路由和成本控制结合起来。

## 准备工作：把代表性 Support Agent Trace 写入 LangSmith

示例没有采用纯文本风格评估，而是构造了一个轻量级 support-agent workflow。

每条 synthetic trace 都包含足够的结构化信息来评估 Agent 行为，包括：

- retry count；
- handoff target；
- required step；
- tool outcome；
- final answer。

生产环境里，你通常会先接入真实应用产生的 trace；这里使用合成数据，是为了把注意力集中在评估流水线本身，而不是日志采集。

## LangSmith 配置注意事项

API key 可以从 LangSmith Settings 获取。

默认建议：

```text
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
```

如果 workspace 位于欧盟区，则改为：

```text
https://eu.api.smith.langchain.com
```

这份 Notebook 的 project 名称由代码里的 `LANGSMITH_PROJECT_NAME` 指定，而不是依赖 `LANGCHAIN_PROJECT` 环境变量。

如果写入 trace 时遇到 `/sessions` 的 `403 Forbidden`，优先检查：

- 是否使用默认 project `default`；
- 自定义 project 是否已经在 LangSmith UI 中创建；
- API key 是否属于同一 organization；
- EU workspace 是否错误使用了 US endpoint。

## Conditional Tracing：让 Trace 跟着业务逻辑走

如果通过 `LANGSMITH_TRACING` 或 `LANGCHAIN_TRACING_V2` 全局开启 tracing，那么默认情况下 spans 和 runs 都会发送到 LangSmith。

但生产环境通常需要更细粒度的控制，例如：

- 对包含大量 PII 的请求关闭 tracing；
- 不同租户写入不同 project；
- 低价值流量不记录 trace，从而降低成本；
- 只对某些 feature flag 命中的请求开启 observability。

Python 中可以使用 `tracing_context` 在 `with` 代码块内覆盖全局 tracing 行为。

### 关闭敏感路径的 tracing

```python
with ls.tracing_context(enabled=False):
    ...
```

### 按租户或区域路由

```python
with ls.tracing_context(
    project_name="client-acme",
    tags=[...],
    metadata={...},
):
    ...
```

### 配置优先级

优先级从高到低为：

```text
tracing_context
→ programmatic configuration
→ environment variables
```

## Conditional Tracing 和 Sampling 的区别

两者解决的不是同一个问题。

**Conditional tracing** 是确定性的：应用明确决定“这一条请求记不记录”。

**Sampling** 是概率性的：在高流量下按照一定比例采样 trace，用于控制成本。

生产环境中可以同时使用两者：先根据业务规则决定哪些请求允许被追踪，再对其中的高频流量做采样。

## 为什么最终要沉淀 Benchmark

只在生产 trace 上即时打分还不够，因为模型升级以后你需要回答：

> 新模型在过去最容易失败的样本上，到底有没有变好？

因此，把 critical failures 逐步加入 replayable benchmark，是这条评估流水线真正形成闭环的关键。

这样，评估流程就从：

```text
观察 → 打分
```

升级为：

```text
观察 → 找失败 → 固化样本 → 回放比较 → 再部署
```

这也是把 observability 转化为持续质量改进能力的核心步骤。
