# AI Agents：权威指南（中文化版本）

> 本仓库 Fork 自 [Nicolepcx/ai-agents-the-definitive-guide](https://github.com/Nicolepcx/ai-agents-the-definitive-guide)，对应 O’Reilly 图书 **AI Agents - The Definitive Guide** 的配套代码。
>
> 本分支的目标不是修改原有代码逻辑，而是把 README、Notebook 中的说明文字、Markdown、必要注释翻译为中文，并尽量保留英文专业术语，方便中文读者直接学习和运行。

[English README](README_EN.md) · [中文学习路线](LEARNING_PATH_ZH.md)

![OReilly_logo_rgb.png](resources%2FOReilly_logo_rgb.png)

## 目录

1. **从 LLM 到 Agent：基础蓝图**
2. **架构与模式：规划、反应式执行与多 Agent 系统**
3. **高级规划、推理与可扩展执行**
4. **Agent 背后的模型：能力与优化**
5. **从原型到生产：契约、工具与可靠执行**
6. **安全执行与工具治理**
7. **在真实产品中部署 Agent**
8. **Agent 系统的基础评估与运行观测**
9. **定制化与高级 Agent 评估**
10. **Agent 记忆：持久化如何让 Agent 持续演进**
11. **从算力到成本：高效 Agent 系统设计**
12. **AI Agent 的威胁建模**

## 仓库结构

```text
├── LICENSE
├── README.md              <- 中文入口
├── README_EN.md           <- 英文原始说明
├── LEARNING_PATH_ZH.md    <- 中文学习路线
├── CH01                   <- 第 1 章 Notebook
├── CH02                   <- 第 2 章 Notebook
├── ...
├── utils                  <- 通用类、函数与工具
└── resources              <- 图片及其他资源
```

Notebook 一般按 `chXX_主题.ipynb` 命名，例如 `ch02_react.ipynb`。代码文件名、API、类名、函数名保持原样，中文化主要针对解释性内容。

## 推荐学习顺序

如果你的目标是“把 Agent 真正用于研究、自动化或生产工作流”，而不是研究 Agent 算法本身，建议优先：

```text
Chapter 5  可靠执行 / Tool Calling / MCP
    ↓
Chapter 8  Evaluation Harness
    ↓
Chapter 9  LangSmith / Langfuse / 高级评估
    ↓
Chapter 10 Memory
    ↓
Chapter 6  工具治理与安全执行
    ↓
Chapter 11 成本与效率
```

完整说明见 [LEARNING_PATH_ZH.md](LEARNING_PATH_ZH.md)。

## Notebook 索引

### Chapter 1 — 从 LLM 到 Agent：基础蓝图
- `CH01/ch01_code_examples.ipynb` — 代码示例

### Chapter 2 — 架构与模式
- `CH02/ch02_CoT.ipynb` — Chain-of-Thought（思维链）
- `CH02/ch02_ToT.ipynb` — Tree-of-Thought（思维树）
- `CH02/ch02_react.ipynb` — ReAct
- `CH02/ch02_HITL.ipynb` — Human-in-the-Loop（人在回路）
- `CH02/ch02_hierarchical_agent_teams.ipynb` — 分层 Agent 团队
- `CH02/ch02_swarms.ipynb` — Swarms（群体式 Agent）

### Chapter 3 — 高级规划、推理与可扩展执行
- `CH03/ch03_ART_RULER.ipynb` — ART + RULER
- `CH03/ch03_RULER_cat_poems.ipynb` — RULER 示例
- `CH03/ch03_TreeQuest.ipynb` — TreeQuest / AB-MCTS

### Chapter 4 — Agent 背后的模型
- `CH04/ch04_supervisor_agent_team.ipynb` — Supervisor Agent Team

### Chapter 5 — 从原型到生产
- `CH05/ch05_deep_agents.ipynb` — Deep Agents
- `CH05/ch05_mcp_langgraph.ipynb` — MCP + LangGraph
- `CH05/ch05_product_reliability_rule.ipynb` — 产品可靠性规则
- `CH05/ch05_pydantic_agent_consistency.ipynb` — 基于 Pydantic 的 Agent 一致性约束

### Chapter 6 — 安全执行与工具治理
- `ch06/ch06_A2A_MCP_Governed.ipynb` — A2A + MCP 治理
- `ch06/ch06_MCP_server_composio.ipynb` — MCP Server + Composio
- `ch06/ch06_langgraph_E2B.ipynb` — LangGraph + E2B Sandbox
- `ch06/ch06_programmatic_tool_calling_monty.ipynb` — Programmatic Tool Calling

### Chapter 7 — 真实产品中的部署
- `ch07/ch07_hardening_backbone.ipynb` — 系统加固骨架
- `ch07/ch07_inference_backends.ipynb` — 推理后端
- `ch07/ch07_model_fallback.ipynb` — 模型降级与回退

### Chapter 8 — 基础评估与运行观测
- `ch08/ch08_OWASP_ASI_2026.ipynb` — OWASP ASI 2026
- `ch08/ch08_eval_harness.ipynb` — Evaluation Harness

### Chapter 9 — 高级评估
- `ch09/ch09_agentvista.ipynb` — AgentVista
- `ch09/ch09_example_external_evaluation_pipelines_Langfuse.ipynb` — Langfuse 外部评估流水线
- `ch09/ch09_example_external_evaluation_pipelines_langsmith.ipynb` — LangSmith 外部评估流水线
- `ch09/ch09_ruler_trace_answer_ranking_langsmith.ipynb` — RULER Trace Answer Ranking

### Chapter 10 — Agent Memory
- `ch10/ch10_agent_memory_langgraph.ipynb` — LangGraph Agent Memory
- `ch10/ch10_memory_no_memory.ipynb` — 有记忆 vs 无记忆
- `ch10/ch10_memory_topologies.ipynb` — 记忆拓扑

### Chapter 11 — 成本与效率
- `ch11/ch11_agent_cost_estimator_based_on_topology.ipynb` — 基于拓扑的 Agent 成本估算
- `ch11/ch11_memoizing_swarm_research_engine.ipynb` — 带记忆的 Swarm Research Engine
- `ch11/ch11_memory_footprint_throughput_and_GPU_requirements.ipynb` — 显存、吞吐与 GPU 需求

### Chapter 12 — 威胁建模
- `ch12/ch12_LlamaFirewall.ipynb` — LlamaFirewall

## 翻译约定

- **不改代码逻辑**：Python、JSON、配置项、API 名称保持原样。
- **术语首次中英并列**：例如“工具调用（Tool Calling）”“人在回路（Human-in-the-Loop）”。
- **优先解释而非硬译**：对中文直译容易失真的术语，会保留英文并补充中文解释。
- **保留可运行性**：Notebook 的 cell 类型、执行顺序和依赖不因翻译改变。
- **尊重原项目许可**：代码与内容的使用仍以原仓库 LICENSE 为准。

## 原项目资源

- 原仓库：https://github.com/Nicolepcx/ai-agents-the-definitive-guide
- 配套网站：https://ai-agents-the-definitive-guide.com/
- Discord：https://discord.gg/pqeHTvzdhJ

如果这个中文版对你有帮助，也建议给原作者的仓库点一个 ⭐。
