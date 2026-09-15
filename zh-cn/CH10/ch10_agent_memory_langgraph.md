# Chapter 10：LangGraph Agent Memory —— 从短期记忆到长期记忆与时间旅行

> 对应原 Notebook：`ch10/ch10_agent_memory_langgraph.ipynb`
>
> 本文件整理并翻译该 Notebook 的解释性内容。代码逻辑、API、类名、函数名和运行输出保持英文原样；首次出现的核心术语保留英文。

## 这个 Notebook 解决什么问题

它展示一个 Agent 如何从“只记住当前对话”升级成拥有多层记忆系统的应用，并进一步处理：

- 短期记忆（Short-term Memory）；
- 语义记忆（Semantic Memory）；
- 情景记忆（Episodic Memory）；
- 程序性记忆（Procedural Memory）；
- 用户级与组织级命名空间隔离；
- 结构化记忆更新；
- 记忆压缩、清理与可编辑性；
- checkpoint 与 Time Travel；
- 生产环境下的成本、安全与持久化问题。

整个 Notebook 的重点不是“把聊天记录全部存下来”，而是建立一套**可治理的记忆架构**。

## 1. 记忆分层

### 短期记忆（Short-term Memory）

短期记忆主要由：

```text
messages + checkpointer + thread_id
```

组成。

`messages` 保存当前线程的对话状态，`checkpointer` 负责把状态快照持久化或暂存，`thread_id` 用于区分不同会话。

Notebook 还提供 `/thread summarize`：当对话过长时，用 LLM 把历史压缩成摘要，再通过 `RemoveMessage` 删除旧消息，只保留摘要后的上下文。

因此短期记忆解决的是：

> “当前这条对话线程里，Agent 怎么不失忆？”

### 语义记忆（Semantic Memory）

语义记忆保存相对稳定的事实，例如：

```text
用户偏好暗色模式
用户从事欺诈检测工作
用户希望解释合规问题时引用法规条款
```

这些内容进入 `BaseStore`，并可以通过 embedding 做向量检索。

Notebook 特别强调：**结构化 profile 里的 `facts[]` 才是 canonical source（权威来源）**。语义存储中的对应行更多是方便检索的 projection（投影）。

即：

```text
Canonical Profile
      ↓
Semantic Search Projection
```

不要把两份数据都当成独立真相，否则很容易发生同步冲突。

### 情景记忆（Episodic Memory）

情景记忆保存“发生过什么”：

```text
任务：billing dispute
结果：issued pro-rata credit after tier mismatch
```

它更像案例库，而不是事实库。

适合回答：

> “以前遇到类似任务时，我们是怎么处理的？”

### 程序性记忆（Procedural Memory）

程序性记忆保存的是 Agent 的工作方式，例如：

- 回答风格；
- 工作流程；
- 安全要求；
- 某类任务的执行规则。

Notebook 将它拆成 typed slots：

```text
style
workflow
safety
task_policies
```

它回答的不是“用户是谁”，而是：

> “面对任务时，Agent 应该怎么做？”

## 2. 用户记忆与组织记忆必须隔离

Notebook 使用不同 namespace：

```python
(org_id, user_id, kind)
```

表示用户私有记忆；

```python
(org_id, "_shared", kind)
```

表示组织共享记忆。

这是一个非常重要的安全边界。

### 身份必须来自认证系统

`org_id` 和 `user_id` 不能由模型自己生成或判断，而应该来自认证上下文（auth）。

否则模型只要被 Prompt Injection 诱导，就可能尝试访问另一个用户或组织的记忆空间。

### 组织级写入必须额外授权

Notebook 使用：

```python
AppContext.is_admin
```

作为组织级写入的真实授权条件。

即使模型输出：

```python
update_global_policy = True
```

也不代表真的允许写入组织共享记忆。

正确逻辑是：

```text
模型认为这是组织级信息
        +
当前认证用户具备管理员权限
        ↓
才允许写入 org memory
```

因此模型的输出只是“意图”，不是“权限”。

## 3. 用户应该能看到并编辑 Agent 的记忆

Notebook 明确提出：

> 用户应该能够查看和编辑 Agent 记住的内容。

这既是信任问题，也和 GDPR 等隐私治理有关。

所以它设计了 `UserMemoryService` 作为统一服务层：

```text
Graph nodes
     ↓
UserMemoryService
     ↑
Future HTTP API / UI
```

未来做 Web 产品时，用户界面的“查看记忆 / 删除记忆 / 修改记忆”可以和 Agent 内部使用同一套服务，而不是维护两套逻辑。

## 4. 记忆卫生（Memory Hygiene）

随着使用时间增加，两类东西都会不断膨胀：

1. 对话历史；
2. 长期事实。

Notebook 提供两种清理机制。

### `/thread summarize`

压缩当前对话线程：

```text
大量历史消息
↓
LLM 摘要
↓
RemoveMessage 删除旧消息
↓
保留一条摘要消息
```

### `/memory compact`

把零散语义记忆进行合并：

```text
fact A
fact B
fact C
...
↓
去重 / 合并 / 解决部分陈旧冲突
↓
consolidated_profile
```

这两个操作对应两个不同层次：

```text
thread summarize = 压缩短期上下文
memory compact   = 整理长期记忆
```

## 5. 记忆投毒（Memory Poisoning）

长期记忆的风险比一次错误回答更大，因为错误内容会在未来反复被召回。

Notebook 因此加入了一些基础防护：

- 长度限制；
- 拒绝类似 SSN 的格式；
- 拒绝疑似银行卡号；
- 拒绝 PEM private key；
- 拒绝常见 API secret；
- 组织事实使用 category allowlist；
- 低置信度事实进入 proposed / review 状态。

这说明长期记忆不能简单理解为：

```python
store.put(user_input)
```

而应该是一个受控写入流程。

## 6. Canonical Profile 与 Semantic Projection

Notebook 做了一个很重要的架构选择：

### Canonical Profile

结构化 profile 中的：

```python
facts[]
```

是主数据。

每条事实包含类似：

```text
id
content
category
confidence
createdAt
updatedAt
source
lifecycle
```

### Semantic Projection

为了方便向量检索，再把 profile fact 投影到 semantic namespace：

```text
source_type = profile_projection
projection_of = fact_id
```

因此如果 canonical fact 被删除，对应 projection 也必须同步删除。

这种方式避免：

> “向量数据库里有一份事实，profile 里又有另一份事实，两边到底谁说了算？”

## 7. 结构化记忆更新

Notebook 没有让 LLM 直接修改整个 JSON，而是定义 `MemoryUpdateOutput`。

它大致包含：

```text
user section patches
history section patches
newFacts
factsToRemove
```

LLM 只负责提出 patch，然后程序代码负责应用。

架构上可以拆成：

```text
Conversation
↓
LLM Extract / Propose
↓
Structured Patch
↓
Deterministic Apply
↓
Canonical Memory
```

这比“让 LLM 返回一整份新 memory JSON”可靠得多。

### 为什么要拆成两阶段

Notebook 当前为了教学仍使用一个 LLM 流程，但明确建议生产环境进一步拆为：

```text
extract
↓
validate/test
↓
apply
```

这样更方便审计和单元测试。

## 8. 如何处理矛盾事实

如果用户后来改变偏好，例如：

```text
以前：只用 dark mode
现在：改成 light mode
```

新的记忆更新不应该简单再追加一条，而应：

```text
factsToRemove = [旧 fact id]
newFacts = [新 fact]
```

Notebook 还通过 `CATEGORY_COMBINE_MODE` 区分不同类别的合并方式：

```text
preference / correction / behavior → replace
goal / knowledge                 → merge
context                          → accumulate
```

这体现了一个重要原则：

> 不同类型的记忆，不能用同一种“追加”规则处理。

## 9. 低置信度事实的隔离

新事实包含 `confidence`。

高置信度内容可以进入 confirmed；较低置信度内容则可能进入：

```text
lifecycle = proposed
needs_review = True
```

这相当于记忆的“隔离区（quarantine）”。

Agent 可以区分：

```text
用户明确说过的
vs
模型从语境推断出来的
```

而不是把两者混为一谈。

## 10. 记忆注入（Memory Injection）

长期记忆最终还是要进入 Prompt 才能影响模型。

但不能把所有事实都塞进去，否则 token 会不断膨胀。

Notebook 因此使用：

- confidence；
- 时间衰减；
- token budget；
- 可选 embedding rerank；

对事实排序。

流程大致是：

```text
所有事实
↓
confidence + time decay
↓
按当前 query 做 embedding rerank
↓
按 token budget 截断
↓
注入 system context
```

其中 `rank_facts_for_injection` 用 embedding similarity 重新排序，使当前问题更相关的事实优先进入上下文。

## 11. Memory LLM 的“持久化税”（Persistence Tax）

如果每一轮对话都额外调用一个 LLM 来更新长期记忆，会产生明显的：

- 延迟；
- token 成本；
- API 成本。

Notebook 将它称为 persistence tax。

因此提供：

```text
MEMORY_LLM_SYNC_STRATEGY
```

支持：

- `interval`：每隔若干用户消息运行；
- `farewell`：用户结束对话时运行；
- `both`：两者都触发；
- `every_turn`：每轮都运行，成本最高。

还可以设置：

```text
MEMORY_LLM_EVERY_N_HUMANS
MEMORY_LLM_FAREWELL_TRIGGERS
MEMORY_LLM_MIN_CONV_CHARS
```

生产环境更推荐把记忆更新放入后台 worker，例如 Celery / RQ，并按 `thread_id` 做 debounce。

## 12. `InMemorySaver` / `InMemoryStore` 只是教学配置

Notebook 默认使用：

```python
InMemorySaver
InMemoryStore
```

进程退出后数据就消失。

生产环境可以替换成：

### Checkpointer

- `SqliteSaver`
- `PostgresSaver`

### Store

- `PostgresStore`

如果使用向量检索，要确保 embedding 维度匹配。例如：

```text
text-embedding-3-small → 1536 dims
```

数据库向量字段和 embedding model 的维度不一致会直接报错。

## 13. 多进程与并发问题

Notebook 明确没有解决生产级多 worker 问题。

`InMemoryStore` / `InMemorySaver` 不适合多进程共享，也没有展示：

- transaction；
- idempotent background sync；
- 并发写冲突；
- 分布式锁；
- 去重队列。

这些都属于从 demo 走向生产时需要补的部分。

## 14. Slash Commands

Notebook 用 `shlex.split` 解析 slash commands，而不是堆一大堆正则。

示例包括：

```text
/memory list
/memory list semantic
/memory list episodic
/memory delete semantic <key>
/memory clear semantic
/memory clear episodic
/memory clear all
/memory compact
/thread summarize
/proc set ...
/proc reset
```

这种方式容易扩展，也更接近未来 HTTP API 的路由结构。

## 15. Unified Agent Graph

完整 Agent 图可以概括成：

```text
START
  ↓
是否是 slash command？
  ├── 是 → commands → END
  │
  └── 否
       ↓
  load_context
       ↓
     agent
       ↓
    persist
       ↓
      END
```

### `load_context`

读取：

- org profile；
- user profile；
- 当前 query 相关的记忆；

生成注入上下文。

### `agent`

模型收到：

- 基础系统指令；
- structured profile；
- procedural memory；
- semantic facts；
- episodic examples；
- 当前对话。

### `persist`

根据策略判断是否运行 memory manager，并把结果保存到 profile 与 semantic projection。

## 16. Time Travel

LangGraph 的 checkpoint 不只是为了恢复崩溃，还可以用于“时间旅行（Time Travel）”。

可以查看历史状态：

```python
get_state_history(...)
```

选择一个旧 checkpoint，然后：

```text
回到旧状态
↓
修改状态
↓
从该位置继续执行
```

这形成一个新的执行分支。

它特别适合：

- 调试；
- 比较不同决策；
- 重放失败任务；
- 人工介入后继续执行。

## 17. Encryption

Notebook 展示 `EncryptedSerializer` 作为 checkpoint 序列化层的扩展点。

生产环境中，checkpoint 和 store 里可能包含敏感用户上下文，因此除了数据库本身的加密，还应考虑：

- at-rest encryption；
- key management；
- namespace access control；
- audit log。

## 18. 生产清单

| 主题 | Notebook 中的建议 |
|---|---|
| 持久化 | `build_checkpointer()` 换成 SQLite / Postgres |
| 多进程 | checkpoint 与 store 使用共享数据库 |
| 用户记忆 UI | 通过 `UserMemoryService` 暴露查看/编辑能力 |
| 安全 | `org_id` / `user_id` 来自认证；org 写入检查 `is_admin` |
| 加密 | 对 checkpoint / store 做静态加密 |
| Memory LLM 成本 | debounce、interval、后台 worker，避免生产环境 `every_turn` |
| Fact 注入 | confidence + time decay + embedding rerank + token budget |
| 组织写入 | 模型意图 + 管理员 RBAC / 审批 |
| 多 worker | 补事务、幂等、并发控制 |

最重要的一条是：

> 在应用边界，把 store 和 checkpoint 中取出的内容也视为 **untrusted text（不可信文本）**。

长期记忆来自历史用户输入、模型提取和外部数据，不能因为“已经存进自己的数据库”就默认它安全。

## 核心结论

这个 Notebook 最值得复用的不是某个 LangGraph API，而是五个架构原则：

1. **短期状态和长期记忆是两套系统。** Checkpointer 解决线程连续性，Store 解决跨线程长期知识。
2. **长期事实要有 canonical source。** 向量库最好只是检索 projection，而不是第二份独立真相。
3. **模型提出修改，程序负责验证和应用。** 不要把长期状态的写权限完全交给 LLM。
4. **记忆是安全边界。** 用户/组织 namespace、管理员授权、敏感信息过滤和 poisoning 防御都必须显式设计。
5. **记忆有持续成本。** 写入、检索、embedding、注入和同步都消耗资源，因此要有触发策略、压缩和 token budget。
