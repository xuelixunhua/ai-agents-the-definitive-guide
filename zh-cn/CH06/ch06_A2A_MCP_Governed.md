# Chapter 6：A2A + MCP 治理层——为工具执行建立安全边界

> 对应 Notebook：`ch06/ch06_A2A_MCP_Governed.ipynb`
>
> 本文是该 Notebook 的中文说明版。代码逻辑、API 名称、类名、函数名及运行输出以原 Notebook 为准。

## 1. 这个 Notebook 在解决什么问题

当 Agent 接入 Model Context Protocol（MCP）后，可调用工具的数量和能力会迅速扩大。真正的风险不再只是“模型会不会答错”，而是：**模型能不能直接触碰外部系统，以及一次错误规划会不会变成真实执行。**

这个 Notebook 构建了一层受治理的 **Agent-to-Agent（A2A）执行边界**：LLM Agent 永远不直接调用 MCP Server，而是先产生结构化的 `ToolRequest`，交给一个独立的 governor（治理器）检查。只有通过策略验证的请求，才有机会真正进入 MCP 执行层。

可以把整体链路理解成：

```text
LLM Agent
   ↓
ToolRequest（声明意图）
   ↓
A2A Governor（策略、预算、参数、审批）
   ↓
MCP Server
   ↓
ToolResult / Audit Artifact
```

核心思想是：**把“模型想做什么”和“系统允许它做什么”彻底分开。**

---

## 2. 为什么不让 Agent 直接调用 MCP

如果模型能够直接访问 MCP 工具，那么工具调用本质上依赖模型自己“自觉遵守规则”。这会带来几个问题：

- Prompt 中写了限制，不等于执行层真的有限制；
- 模型可能在正常规划过程中出现 runaway loop（失控循环）；
- 同一类高风险能力可能通过不同工具别名绕过单工具限额；
- 广泛删除、超大范围搜索等危险参数可能在调用发生前没有被拦截；
- 一旦进入真实工具，错误就从“文本错误”变成“系统副作用”。

因此 Notebook 采用 **structured sandboxing（结构化沙箱治理）**，而不是只依赖 prompt engineering（提示词工程）。

---

## 3. ToolRequest / ToolResult：把执行意图结构化

Agent 不直接调用工具，而是构造 `ToolRequest`：

```python
@dataclass
class ToolRequest:
    tool_name: str
    arguments: Dict[str, Any]
    rationale: str = ""
    expects_artifact_names: List[str] = field(default_factory=list)
    stop_after: bool = False
```

这个结构非常重要，因为它把“我要执行某个动作”转化成一份可以审查的声明。

治理层可以在真正执行之前检查：

1. 工具是否允许；
2. 参数是否合理；
3. 本任务是否还有预算；
4. 是否违反连接/执行隔离规则；
5. 是否需要人工审批；
6. 输出是否只能生成允许的 artifact 类型。

`ToolResult` 则负责把治理后的执行结果重新交回 Agent。

因此整个系统不是：

```text
模型 → 工具
```

而是：

```text
模型 → 意图 → 治理 → 工具 → 结构化结果
```

---

## 4. 六类核心 Enforcement Mechanisms（执行约束机制）

### 4.1 Tool Allowlist（工具白名单）

只有显式允许、已经验证并且当前可访问的工具，才可以进入 Agent 的可执行表面。

Notebook 强调不要只靠字符串名称判断工具类型。生产环境应该维护动态 registry（注册表），让工具的真实类别来自受信任的元数据，而不是诸如“名字里包含 search 就认为是搜索工具”的脆弱规则。

默认策略应是 **fail closed（默认拒绝）**：未知工具不执行。

### 4.2 Budget Limits（预算限制）

为一个任务设置硬上限，包括：

- 总工具调用次数；
- 单工具调用次数；
- 最大并行调用数；
- 总运行时间。

这不仅是成本控制，也是安全控制。模型即使陷入循环，执行层也会在预算耗尽后强制停止。

更重要的是，生产环境最好同时做 **category-level quota（工具类别级配额）**。否则 Agent 可能在多个能力相近的工具间轮换，绕过单工具限制，这就是 Notebook 提到的 alias evasion（别名规避）。

### 4.3 Argument Gates（参数门控）

真正危险的往往不是“调用了什么工具”，而是“给工具传了什么参数”。

例如：

- 删除目标是不是 `*`；
- 搜索 query 是否异常宽泛；
- 请求结果数量是否过大；
- 高风险参数是否超过约束。

因此系统必须在执行前检查 arguments，而不是工具调用后再补救。

### 4.4 Connection Separation（连接与执行隔离）

Notebook 维护有状态的分离规则：Agent 不能在同一个受控执行上下文中完成“发现/建立连接”后立刻进行高权限执行。

这是为了防止能力在同一条路径中无边界扩张。

Notebook 中该规则主要按单次 run 管理。生产环境若支持多轮任务，需要把这些 contamination flags（污染标记/风险状态）持久化到状态存储中，否则下一轮会丢失风险上下文。

### 4.5 Approval Workflows（人工审批工作流）

Restricted（受限）工具不能直接执行，而是通过 LangGraph `interrupt` 暂停：

```text
请求受限工具
   ↓
保存图状态
   ↓
interrupt
   ↓
等待外部审批
   ↓
Command(resume=...)
   ↓
继续执行或拒绝
```

Notebook 可以用 console input 模拟 Human-in-the-Loop（HITL，人在回路）审批，但这只是演示。

生产环境应该改成异步、带持久化的外部审批，例如：

- Slack；
- 工单系统；
- Governance UI；
- Webhook 回调。

重点不是“有人点同意”，而是 **任务能够在等待数分钟甚至数小时后从原状态继续恢复**。

### 4.6 Structured Artifacts（结构化审计产物）

每一次允许、拒绝、暂停和审批，都被记录成机器可读的 JSON artifact。

Notebook 将 artifact 类型限制在明确集合中，例如：

- `policy_decision`；
- `tool_call_log`；
- `approval_request`；
- `approval_log`；
- `budget_stats`；
- `result_summary`。

生产环境应该集中生成 artifact，而不是让各工具自由写日志，否则容易发生 silent leak（静默泄漏），把内部推理、敏感参数或元数据写进外部可见日志。

---

## 5. `governed_call()`：单一执行闸门

这个 Notebook 的关键架构选择，是让所有 MCP 调用都经过 `governed_call()`。

它相当于单一 enforcement point（执行约束点）：

```text
governed_call(request)
    ├─ policy check
    ├─ budget check
    ├─ category / separation check
    ├─ argument validation
    ├─ optional approval
    ├─ open MCP session on demand
    ├─ execute tool
    └─ write audit artifacts
```

这样可以避免最危险的一类设计问题：

> 系统里明明有安全检查，但某条“旁路”仍能绕过检查直接触发工具。

真正可治理的 Agent 系统应该尽量减少执行入口，而不是给每个组件各自一套权限逻辑。

---

## 6. Tool Categorization（工具分类）为什么重要

Notebook 明确区分：

- discovery：发现/搜索；
- connection：建立连接；
- execution：执行真实动作；
- other：其他。

分类不是为了好看，而是为了对**能力类别**应用不同策略。

例如：

- Discovery Only 策略允许搜索，但阻止 execution；
- SerpApi 某些执行能力被标记为 restricted，需要审批；
- Budget Limited 策略用于测试预算耗尽；
- connection 与 privileged execution 之间设置相互排斥。

相比“按工具名写死规则”，能力分类更容易扩展到大规模工具生态。

---

## 7. Notebook 的威胁模型

该 Notebook 将工具调用视为 privileged execution（特权执行），并针对以下风险建立防线：

### Runaway loops
模型不断重复调用工具。

→ 通过总调用预算、单工具预算、时间预算阻断。

### Repeated calls
模型过度重复调用同一能力。

→ 通过 per-tool limits 限制。

### Broad actions
模型发出过于宽泛的高影响操作。

→ 通过 argument gates 在请求阶段阻断。

### Capability escalation
模型逐渐获得原本不应该触达的能力。

→ 通过 allowlist + category policy 限定 reachable surface area（可达能力表面）。

### Separation violations
Agent 在同一路径里先建立连接，再直接进行高权限执行。

→ 通过有状态隔离规则阻断。

---

## 8. Demo 重点验证什么

Notebook 设计了几类有代表性的演示：

1. **Discovery Only**：普通 Exa Web Search 可以成功执行；
2. **Code Search Blocked**：代码类搜索被策略阻断；
3. **Budget Exhaustion**：超过 3 次调用后自动拒绝；
4. **Separation Rule**：连接后立即执行触发隔离违规；
5. **HITL Approval**：受限请求通过 `interrupt` 等待人工批准；
6. **Audit Report**：从 A2A artifacts 自动生成机器可读审计报告。

这些测试的意义不是展示“工具能不能调用”，而是证明：**治理规则在 Agent 真实运行路径中能够被触发并留下可验证证据。**

---

## 9. AuditReportGenerator：从日志升级到审计

`AuditReportGenerator` 将 A2A artifacts 汇总成结构化审计报告，包括：

- 允许/拒绝请求数量；
- 成功率；
- 总调用与各工具调用量；
- elapsed time（耗时）；
- 分离状态；
- 已执行工具的参数和结果；
- 每次 allow/deny 的具体原因；
- 审批请求与审批结论；
- 拒绝模式和 enforcement insights；
- 可操作的策略改进建议。

这使系统从“有日志”升级到“可以回答谁、在什么时候、为什么允许或拒绝了什么动作”。

---

## 10. 生产环境需要补上的能力

Notebook 也明确指出，它展示的是 **execution boundary governance（执行边界治理）**，而不是完整的服务间密码学信任。

生产环境还需要继续补：

- 真实异步审批系统；
- policy versioning（策略版本控制）与回滚；
- per-user / per-tenant policy；
- 自动化 policy testing；
- 实时监控与告警；
- SOC2 / GDPR 等审计系统对接；
- 多 Agent 协同治理；
- 服务身份、attestation（证明）与远程隔离；
- MCP session 生命周期管理，避免孤儿连接和 async cancel-scope 问题。

---

## 11. 最重要的理解

这个 Notebook 最值得带走的不是某个具体 API，而是一种 Agent 工程架构：

> **LLM 负责提出意图，治理层负责决定意图是否能够变成真实副作用。**

在小型 Demo 中，prompt 约束似乎已经够用；但随着 MCP、A2A 和大规模工具生态加入系统，可靠的边界必须下沉到确定性的执行层。

因此这里真正体现的是 defense in depth（纵深防御）：

```text
Policy
  + Budget
  + Argument Validation
  + Separation
  + Approval
  + Artifact Filtering
  + Audit
```

当这些机制全部独立于模型存在时，Agent 才真正从“会调用工具的程序”走向“可治理的执行系统”。
