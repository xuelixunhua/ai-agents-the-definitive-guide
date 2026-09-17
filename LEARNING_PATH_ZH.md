# 中文学习路线：把 Agent 用到真实研究与自动化工作中

这份路线不是按书的章节顺序机械阅读，而是按“先能可靠做事，再理解更复杂架构”的顺序组织。

## 1. 第一阶段：先学会让 Agent 可靠调用工具

优先阅读 Chapter 5。

目标：理解一个真正可用的 Agent 不是“会聊天”，而是能够按照明确输入输出契约调用工具、处理失败、约束返回格式，并让流程可复现。

重点：
- Tool Calling
- MCP
- LangGraph
- Pydantic / schema consistency
- reliability rules

完成标准：你应该能解释“为什么给模型一个 Python 函数，并不等于拥有一个可靠 Agent”。

## 2. 第二阶段：建立评估体系

阅读 Chapter 8 与 Chapter 9。

目标：不要只凭“看起来不错”判断 Agent，而是给任务建立测试集、指标和 trace。

重点：
- Evaluation Harness
- Agent trace
- LangSmith
- Langfuse
- 自定义 evaluator

完成标准：同一个 Agent 或 Prompt 改版后，可以通过固定测试集判断它究竟变好了还是变差了。

## 3. 第三阶段：理解 Memory

阅读 Chapter 10。

目标：区分对话上下文、短期状态、长期记忆、外部知识库，不把所有“记住东西”的需求混为一谈。

重点：
- memory vs no memory
- memory topology
- LangGraph memory

完成标准：能够根据任务决定“什么该记、什么时候取、什么时候应该忘”。

## 4. 第四阶段：安全与治理

阅读 Chapter 6 与 Chapter 12。

目标：当 Agent 真正能操作文件、网页、数据库或外部服务时，理解权限边界与攻击面。

重点：
- Tool governance
- sandbox
- A2A / MCP governance
- threat modeling
- prompt injection / unsafe tool use

完成标准：能把“模型可以做什么”和“模型被允许做什么”分开设计。

## 5. 第五阶段：成本、吞吐与生产部署

阅读 Chapter 7 与 Chapter 11。

目标：从 Demo 思维切到系统思维。

重点：
- model fallback
- inference backend
- latency / throughput
- memory footprint
- topology cost

完成标准：能针对任务价值选择模型、调用次数、并发方式和降级策略，而不是所有步骤都调用最贵模型。

## 6. 最后再看复杂推理与多 Agent

最后阅读 Chapter 2、3、4。

CoT、ToT、ReAct、Supervisor、Swarms、MCTS 等内容很有启发，但不要默认“Agent 越多越高级”。复杂架构只有在单 Agent + 清晰工具 + 良好评估仍解决不了问题时才值得引入。

## 面向研究型工作的一个实践项目

可以把一个研究流程拆成：

```text
数据获取
  ↓
数据质量检查
  ↓
提出研究假设
  ↓
运行实验
  ↓
评估结果
  ↓
失败诊断
  ↓
沉淀研究记忆
  ↓
生成报告
```

建议先让每一步都能独立运行和评估，再决定是否需要把它们组合成多 Agent 系统。
