# Chapter 2：Human-in-the-Loop（HITL）模式

> 对应原 Notebook：`CH02/ch02_HITL.ipynb`

## 这份 Notebook 在解决什么问题

这份 Notebook 展示怎样在 LangGraph Agent 工作流中加入**精确的人类控制点（Human-in-the-Loop, HITL）**：Agent 可以继续自主执行，但在高风险、需要判断或需要人工编辑的地方暂停，把决定权交还给人。

核心不是“每一步都让人审批”，而是：**只在值得人工介入的边界设置 interrupt，并让工作流能够暂停、保存状态、接收输入后继续执行。**

## 核心机制：interrupt + checkpoint + resume

HITL 的基础循环可以概括为：

1. Graph 正常执行；
2. 到达 `interrupt(...)` 时暂停；
3. Checkpointer 保存当前 state；
4. 外部界面把 interrupt payload 展示给人；
5. 人提供批准、修改或替代结果；
6. 用 `Command(resume=...)` 恢复同一个 thread；
7. Graph 从暂停点继续，而不是从头重跑。

Notebook 使用 `InMemorySaver` 作为最小 Checkpointer，所以暂停前的上下文不会丢失。

## Notebook 展示的六类 HITL 模式

### Pattern A：内容生成中的人工反馈循环

模型先起草 LinkedIn 文案，然后通过 `interrupt` 请求人工反馈。

人工可以不断输入修改意见，Graph 循环“生成 → 审阅 → 再生成”，直到输入 `done`。

适合：

- 短文案；
- 品牌内容；
- 需要主观风格判断的产物；
- 人机共同迭代，而不是一次审批。

### Pattern B：敏感外部调用前的审批闸门

模型先提出一个 HTTP Request，并以 JSON 形式给出参数。

真正发出网络请求前，人工可以：

- approve：直接批准；
- revise：修改参数；
- request more context：要求补充信息；
- reject：拒绝执行。

这是典型的**安全闸门（approval gate）**。

适合放在：

- 转账；
- 下单；
- 删除数据；
- 修改生产配置；
- 发送外部邮件；
- 高风险 API 调用。

### Pattern C：人工直接编辑 State

模型生成一段 summary，人工不只是给反馈，而是直接修改文本本身。

修改后的版本写回 Graph State，成为后续节点看到的唯一正式版本。

适合：

- 合规审查；
- 法务文字；
- 品牌语气；
- 研究报告最终措辞；
- 需要人工承担最终责任的文本。

### Pattern D：并行 interrupts

两个独立分支同时产生 interrupt。

Runner 会一次性列出所有待处理项，为每个 interrupt 收集 resume value，最后使用一张映射表统一恢复 Graph。

这比“收到一个 interrupt 就恢复一次”更适合：

- 批量审批；
- 多条候选建议；
- 多 Agent 同时请求人工决策；
- 多条异常并行处理。

### Pattern E：工具调用前的人工 Review

Notebook 用 `add_hitl` 包装工具。

模型决定调用工具后，不立即执行，而是先把 Tool Call 暴露给人。人工可选择：

- `accept`：按原参数执行；
- `edit`：修改工具参数后执行；
- `response`：不执行工具，直接提供一个替代 Observation。

示例输入形式包括：

```json
{"type": "accept"}
```

```json
{"type": "edit", "args": {"args": {"query": "weather in Zurich"}}}
```

```json
{"type": "response", "args": "Skip for now"}
```

这构成了一个最小的“受监督 ReAct Loop”。

### Pattern F：静态 interrupt 作为调试断点

除了运行时动态 `interrupt(...)`，还可以在指定节点前后注册静态中断点。

它更接近传统 Debugger 的 breakpoint：每次执行到固定位置都暂停。

适合：

- 单元测试；
- 逐节点调试；
- 检查 State 是否符合预期；
- 验证关键节点前后的状态变化。

## Provider 配置

Notebook 在启动时支持两种模型提供方：

- `LLM_PROVIDER=openai`：使用 `langchain_openai`；
- `LLM_PROVIDER=openrouter`：通过 `ChatOpenAI` + 自定义 `base_url` 调 OpenRouter。

环境变量通过 `python-dotenv` 从 `.env` 读取，包括：

- `LLM_PROVIDER`；
- `OPENAI_API_KEY`；
- `OPENROUTER_API_KEY`；
- 可选的 `OPENAI_MODEL`；
- 可选的 `OPENROUTER_MODEL`。

## 为什么 HITL 不应该理解成“人工审核一切”

如果每个工具调用、每个节点都让人确认，Agent 的自动化价值会迅速消失。

更合理的设计是按照**风险、不可逆性和不确定性**决定是否插入 HITL：

- 低风险 + 可逆：自动执行；
- 高风险 + 可逆：可先执行，再审计；
- 高风险 + 不可逆：执行前审批；
- 高不确定性：请求补充信息或人工判断；
- 涉及主观质量：人工编辑或反馈循环。

因此 HITL 是一种**权限与责任边界设计**，而不仅仅是 UI 上多一个“确认”按钮。

## interrupt payload 应该包含什么

为了让人工真的能做决定，interrupt 不能只说“是否批准？”。最好至少包含：

- Agent 准备做什么；
- 为什么要做；
- 关键输入参数；
- 预计影响；
- 是否可撤销；
- 当前上下文摘要；
- 可选操作及各自含义。

否则人工只是机械点按钮，无法真正承担 Review 的价值。

## Checkpoint 为什么关键

没有 Checkpoint 时，一旦暂停，恢复流程通常意味着重新执行前面所有步骤，可能导致：

- 重复调用工具；
- 重复付费；
- 重复发送请求；
- 上下文不一致；
- 难以保证恢复前后的确定性。

通过 thread-scoped checkpoint，Graph 能保存暂停时的状态，并在收到 `resume` 后从正确位置继续。

生产环境中应把 `InMemorySaver` 替换为持久化 Checkpointer。

## 生产化时需要额外考虑

### 1. 审批身份

不仅要知道“有人批准了”，还应知道：

- 谁批准；
- 什么时候批准；
- 对哪个版本批准；
- 是否有相应权限。

### 2. 超时和无人响应

interrupt 不能无限等待。需要定义：

- 超时多久；
- 超时后取消、降级还是升级到其他审批人；
- 恢复时原上下文是否仍然有效。

### 3. 防止审批后参数被篡改

审批对象应带版本号或 Hash。人工批准的是参数 A，就不应在真正执行前悄悄变成参数 B。

### 4. 审计记录

高风险动作需要记录：

`提议 → interrupt → 人工决定 → 修改内容 → 最终执行结果`

形成完整 audit trail。

## 对原 Notebook 的代码阅读提示

建议重点看四处：

1. `interrupt(...)` 在节点内部如何产生暂停；
2. `InMemorySaver` 如何绑定 thread state；
3. Runner 如何读取 interrupt payload 并构造 `Command(resume=...)`；
4. `add_hitl` 如何把一个普通工具变成可审批、可编辑、可替代响应的工具。

真正值得迁移的思想是：**Agent 的自主性不应该和控制权对立。通过明确的暂停点、状态持久化和恢复协议，可以把自动化与人工责任同时保留下来。**
