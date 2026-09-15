# 第 10 章：有记忆 vs 无记忆

> 对应原 Notebook：`ch10/ch10_memory_no_memory.ipynb`

## 关于这个 Notebook

这个 Notebook 演示了：**LangGraph 聊天机器人在启用 checkpointed memory（检查点记忆）与未启用时，会出现什么本质差异。**

图中只有一个 chatbot 节点，它通过兼容 OpenRouter 的 `ChatOpenAI` 接口，把当前消息历史发送给 LLM。随后，同一张图被编译成两个版本：

- 一个不配置 checkpointer；
- 一个配置 `InMemorySaver` 作为 checkpointer。

### 不使用记忆时

每次调用都只接收到这一轮用户消息。即使用户上一轮说过自己的名字，下一次 invocation 也不会自动带上那段历史，所以模型无法回答“我叫什么名字”。

### 使用记忆时

连续两次调用使用相同的 `thread_id`。LangGraph 会通过 checkpointer 恢复这个 thread 之前保存的会话状态，因此第二轮能够访问第一轮提供的信息，并回答基于历史上下文的问题。

这个例子说明了 Agent Memory 的一个基础事实：

> **多轮记忆不是模型自己“记住了”，而是系统显式保存并在下一次调用时恢复了状态。**

---

## 核心机制

可以把两种模式理解为：

```text
无记忆：
Turn 1 → Graph → LLM
Turn 2 → Graph → LLM
两次调用彼此独立

有记忆：
Turn 1 → Graph → Checkpoint(thread_id=A)
                         ↓
Turn 2 → 恢复 A 的状态 → Graph → LLM
```

因此，决定记忆是否存在的关键并不是 Prompt 写得多聪明，而是三个系统配置：

1. 图是否配置了 checkpointer；
2. 多轮调用是否使用同一个 `thread_id`；
3. 状态 Schema 是否真正保存了需要延续的内容。

---

## 为什么 `thread_id` 很重要

`thread_id` 可以理解为“这段会话的状态空间 ID”。

如果两次调用使用不同的 `thread_id`，即使都配置了 `InMemorySaver`，它们仍然会被当成两个不同会话。

这意味着：

- 同一个用户的不同会话可以隔离；
- 不同用户之间不会共享历史；
- 同一用户若开启新会话，也可以获得全新上下文；
- 生产系统中需要明确设计 thread 的生命周期。

---

## `InMemorySaver` 的适用边界

这个 Notebook 使用 `InMemorySaver`，适合：

- 教学示例；
- 本地开发；
- 单进程实验；
- 快速验证 memory 行为。

它不等于生产级长期记忆。进程退出后，内存中的 checkpoint 通常不会持久保存。

生产环境通常需要能够跨进程、跨重启持久化的 checkpoint backend，例如数据库类存储。真正设计 Agent Memory 时，应区分：

- **短期会话状态**：本轮 / 当前 thread 的上下文；
- **长期记忆**：跨会话、跨天甚至跨设备仍需要保留的信息。

---

## 最容易混淆的三件事

### 1. Context Window 不等于 Memory

把历史消息重新放回上下文，模型就能“看到过去”；但这只是上下文恢复机制，并不是模型参数永久改变。

### 2. Checkpoint 不等于用户画像

Checkpoint 保存的是图状态。用户画像、偏好、长期事实等可能需要单独的长期 memory store 与检索策略。

### 3. 同一个模型，不同系统配置会表现得像“有记忆”和“失忆”

Notebook 最有价值的一点就在这里：模型没有变化，变化的是外部状态管理。

---

## 对多 Agent 系统的意义

在多 Agent 场景中，这个问题会进一步变复杂：

- 父 Agent 是否有自己的 thread memory；
- 子 Agent 是否共享父 Agent 的状态；
- 子 Agent 是否拥有独立 checkpointer；
- 不同子 Agent 是否应该共享长期信息；
- 哪些状态应该在 Agent 边界上传递，哪些应该隔离。

因此，理解这个最简单的“有记忆 vs 无记忆”示例，是学习后续 `memory_topologies` 的基础。

---

## 一句话总结

**Agent 的连续记忆首先是状态管理问题，而不是模型能力问题。**

配置 checkpointer 并持续使用同一个 `thread_id`，LangGraph 才能在多次 invocation 之间恢复此前状态。