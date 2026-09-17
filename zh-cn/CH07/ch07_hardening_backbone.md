# Chapter 7：生产级 Agent 加固骨架（Hardening Backbone）

对应 Notebook：[`ch07/ch07_hardening_backbone.ipynb`](../../ch07/ch07_hardening_backbone.ipynb)

本节讨论的不是“Agent 能不能跑起来”，而是“Agent 放到生产环境后，能不能稳定、可控地持续运行”。核心思想是：从 **agent vibes（靠感觉能用）** 走向 **system physics（受真实系统约束支配）**。

## 本节要解决什么问题

生产环境里的 Agent 通常会遇到三类故障：

1. **进程或服务中断**：执行到一半崩溃，之前的工作全部丢失；
2. **上下文无限膨胀**：历史消息越来越长，推理变慢、成本升高、模型注意力被稀释；
3. **工具调用失控**：Agent 陷入循环，持续调用工具或模型，最终把预算和时间耗尽。

Notebook 用三个互补模式来处理它们：

| 模式 | 解决的问题 | 核心机制 | 生产价值 |
|---|---|---|---|
| **Checkpointing（检查点）** | 进程失败后无法恢复 | 周期性持久化 Agent 状态 | 崩溃后从中断位置继续，而不是从头开始 |
| **Context Pruning（上下文裁剪）** | Context Bloat / Memory Bloat | 按 token 预算压缩历史消息 | 控制延迟、成本和推理质量退化 |
| **Circuit Breaker（熔断器）** | 无限循环和失控消耗 | 按轮次、成本或调用次数设硬上限 | 在异常循环扩大之前强制停止 |

三者不是彼此独立的“附加功能”，而应组成同一个 Agent 运行循环。

---

## 1. Checkpointing：让 Agent 具备恢复能力

Notebook 用 `AgentSession` 把 Agent 的完整运行状态组织成可序列化结构。只要状态可以稳定地被序列化，就可以在每轮结束后保存一个快照。

生产环境中的基本流程是：

```text
用户请求
  ↓
恢复最近 checkpoint（如果存在）
  ↓
执行当前 Agent turn
  ↓
更新状态
  ↓
写入 checkpoint
  ↓
继续下一轮
```

这样，如果 Agent 在 10 步流程的第 4 步之后崩溃，下次可以从第 4 步附近继续，而不是重新执行前 3 步。

Notebook 为了演示方便使用本地文件；真正部署时，更常见的存储是 **Redis、Postgres 或其他持久化状态存储**。

### 生产上真正重要的不是“有没有保存”，而是保存什么

一个可恢复的 checkpoint 至少应包含：

- 当前会话标识；
- 已发生的消息与工具调用；
- 当前任务阶段；
- 已累计的 token / cost / turn 等运行指标；
- 必要的业务状态；
- 恢复后可以重新建立的外部引用。

如果只保存聊天文本，而没有保存任务阶段、预算和工具执行状态，恢复出来的 Agent 仍然可能“失忆”。

---

## 2. Context Pruning：不是清理，而是性能控制

模型的上下文越长，并不意味着效果一定越好。长上下文会带来三个直接代价：

- **延迟增加**：prefill 需要处理更多 token；
- **成本增加**：每次调用都要重复发送更长的上下文；
- **注意力稀释**：旧信息、重复信息会干扰当前任务。

因此 Notebook 引入 Context Janitor，对历史内容进行 token-aware（基于 token 预算）的裁剪。

典型策略是：

```text
始终保留 system prompt
       +
保留最近若干轮原始消息
       +
把更早的历史压缩为摘要
       +
确保总 token 数不超过预算
```

这里有一个关键点：**裁剪不是简单删除旧消息。** 如果直接截掉前半段历史，Agent 可能丢失用户目标、重要约束或已经完成的步骤。更稳妥的做法是对被裁剪内容形成摘要，再保留少量关键事实。

Notebook 使用 `tiktoken` 对上下文做接近实际模型的 token 计数，而不是用“字符数 ÷ 4”之类的粗略估算。这一点很重要，因为生产系统最终受制于真实 token 预算，而不是字符数。

---

## 3. Circuit Breaker：为每个会话设硬边界

Agent 的最大风险之一，是陷入自己无法识别的错误循环：

```text
调用工具 → 工具失败 → 再次规划 → 调用同一个工具
        ↑                         ↓
        └────────── 继续循环 ─────┘
```

如果没有外部限制，模型并不会天然知道“现在应该停止烧钱”。因此 Notebook 把熔断器设计为 Agent 运行时的硬约束。

常见熔断条件包括：

- 最大 turn 数；
- 最大工具调用次数；
- 最大 token 数；
- 最大累计费用；
- 连续失败次数；
- 单次任务最大墙钟时间（wall-clock time）。

熔断触发后，不应该继续让模型自己尝试恢复，而应切换到显式失败路径，例如：

```text
Breaker trip
   ↓
停止 Agent loop
   ↓
记录原因和当前状态
   ↓
返回可解释错误
   ↓
必要时升级给人工处理
```

Notebook 提到按 session 设置成本上限。具体金额不是重点，重点是：**预算必须成为运行时约束，而不能只是月末看账单。**

---

## 4. 三种模式应该组合成一个循环

较完整的生产 Agent turn 可以抽象为：

```text
1. 加载 / 恢复 Session
2. 裁剪 Context
3. 调用模型
4. 执行必要工具
5. 更新 turn / token / cost 指标
6. 检查 Circuit Breaker
7. 写入 Checkpoint
8. 进入下一轮或返回结果
```

这三个模式分别覆盖不同的故障面：

- Checkpointing 负责 **可恢复性**；
- Context Pruning 负责 **性能与成本稳定性**；
- Circuit Breaker 负责 **失控保护**。

缺少其中任何一个，系统都会留下明显盲区。

---

## 5. Tool Contract：硬化的不只是模型调用

Notebook 使用三个确定性的 mock tool 来模拟真实生产工具：

- `classify_ticket`
- `lookup_order`
- `check_policy`

虽然内部数据是 mock 的，但工具 schema、dispatcher 和 function-calling contract 都按生产方式组织。

这体现一个重要原则：**Agent 的可靠性边界不仅在 LLM，还在工具接口。**

生产工具至少应该做到：

- 输入 schema 明确；
- 输出结构可验证；
- 错误类型可区分；
- 有 timeout；
- 有重试上限；
- 对有副作用的操作支持幂等或去重。

否则，即使 Agent 本身有 checkpoint，也可能因为重复执行外部副作用而造成业务事故。

---

## 6. Streaming vs. Polling

对于耗时较长的 Agent 任务，不适合把整个流程塞进一个普通 REST `POST` 请求，然后等待几十秒返回。

更合理的交互方式是：

- **WebSocket**：适合双向实时交互；
- **Server-Sent Events（SSE）**：适合服务端持续向前端推送进度。

流式传输不会让模型本身变快，但能把“正在工作”的中间状态持续传给 UI，从而降低用户感知延迟，并减少代理层、网关层的超时问题。

---

## 7. 生产落地时应进一步补充什么

Notebook 给出了核心骨架，但真正生产化还应继续补足：

1. **分布式 checkpoint**：避免 checkpoint 只存在单机；
2. **幂等性**：恢复后不能重复扣款、重复下单、重复发消息；
3. **可观测性**：对每个 turn、tool call、breaker trip 建立 trace；
4. **隔离与权限**：不同 session / tenant 的状态与工具权限隔离；
5. **恢复测试**：主动 kill 进程验证 checkpoint 是否真的可恢复，而不是只看代码逻辑。

---

## 一句话总结

生产级 Agent 的稳定性不是靠“更聪明的模型”解决，而是靠 **Checkpointing + Context Pruning + Circuit Breaker** 把状态恢复、上下文预算和失控边界都变成明确的系统机制。