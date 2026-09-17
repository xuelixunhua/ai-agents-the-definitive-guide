# Chapter 5：用 Pydantic 构建可靠 Agent 的中文导读

对应原 Notebook：[`CH05/ch05_pydantic_agent_consistency.ipynb`](../../CH05/ch05_pydantic_agent_consistency.ipynb)

## 这个 Notebook 在解决什么问题？

这个 Notebook 关注的是一个典型生产问题：

> 为什么 Agent 在 Demo 里能跑，但一放到生产环境就经常因为字段类型、JSON 结构、供应商差异或异常输出而悄悄出错？

Notebook 给出的核心答案是：用 **Pydantic Model 作为系统边界上的技术契约（technical contract）**。

它不是为了“让代码更漂亮”，而是为了把不可信的模型输出在进入系统核心逻辑之前先校验、规范化和拒绝。

## 第一层问题：静默失败为什么危险？

LLM 输出天然具有波动性。即便语义相同，也可能出现：

```python
{"user_id": 123, "age": 25}
```

也可能是：

```python
{"user_id": "123", "age": "25"}
```

如果下游默认 `user_id` 一定是整数，字符串就可能导致：

- 数值运算行为异常；
- 数据库查询拼接风险；
- 运行到更后面才报错；
- 不同模型供应商之间切换时出现兼容问题。

更麻烦的是，有些错误不会立刻 crash，而是产生“看起来能跑、结果却已经错了”的静默失败。

## Pydantic 的作用：在边界上 Fail Fast

Notebook 用 `BaseModel` 明确描述输入数据：

```python
class UserData(BaseModel):
    user_id: int
    age: int
    email: Optional[str] = None
```

这样，外部数据进入系统时先经过校验。

Pydantic 可以做两类事：

1. **可安全转换的输入**：如 `"123"` 转成 `123`；
2. **不可接受的输入**：如 `"abc"` 作为整数，立刻抛出 ValidationError。

所以它把错误从“系统深处才发现”提前到了“数据刚进来时就发现”。

## Notebook 的四个生产级支柱

### 1. 确定性的策略管理（Deterministic Policy Management）

一个 Agent 运行开始后，它使用的校验规则应该固定下来，而不是中途随着全局配置变化。

Notebook 的做法包括：

- 对当前校验配置计算 `policy_hash`；
- 把这个 hash 写进运行状态；
- 数据库记录也带上 `policy_hash`；
- 即使部署过程中全局配置更新，正在运行的任务仍遵循原先规则。

这解决的是**可复现性和审计性**问题。

### 2. 性能友好的验证（Performance-Optimized Validation）

校验不能成为系统瓶颈。

Notebook 使用类似 `(mode, policy_hash)` 的组合缓存动态生成的 Pydantic Model，避免每次都重新构建 schema。

同时尽量直接传递字典给验证工厂，减少图执行过程中的额外转换。

### 3. 显式状态管理（Explicit State Management）

不要通过“错误数量是不是 0”去猜某一步是否成功，而应直接在状态中使用明确布尔值，例如：

```text
prompt_ok
image_ok
```

这样路由条件更直接，日志也更容易理解。

### 4. 工具结果与数据库记录分离（Boundary Separation）

Notebook 强调：

- Tool Result 是外部世界刚返回的结果；
- Database Record 是系统已经接受、准备长期保存的数据。

两者不要共用一个 schema。

原因是工具输出格式可能随着供应商变化，而数据库结构通常需要更稳定。把两层分开，可以让外部接口升级而不直接污染持久化层。

## 三块式架构

Notebook 把实现分成三个区块：

| 模块 | 作用 |
|---|---|
| Governance Config | 用 OmegaConf 管理严格/宽松等不同校验策略 |
| Contracts & Gates | 用缓存的 Pydantic Model 作为不可信数据进入系统的防线 |
| Graph Wiring | 用 LangGraph 管理状态、checkpoint、重试与条件路由 |

这三个部分分别对应：**规则、边界、流程**。

## Pydantic 与 Instructor 的区别

Notebook 还比较了两种思路。

### LangGraph + Pydantic

恢复逻辑放在 Graph 中：

```text
生成
→ 校验
→ 不通过
→ refine node
→ 再生成
```

优点是每次重试都清晰出现在执行轨迹里，适合复杂、多步骤、审计要求高的系统。

### Instructor

Instructor 更倾向于把结构化输出和重试封装在 LLM Client 层。

```text
调用 LLM
→ 内部校验失败
→ 自动重试
→ 返回结构化对象
```

它更简单，适合结构化抽取和短链路任务。

所以两者不是谁“更先进”，而是恢复逻辑放在哪一层的问题。

## Notebook 特别强调的三个实现细节

1. **Stable Schema Hashing**：动态生成的 Model 要保证 JSON Schema 引用稳定；
2. **Aggressive Normalization**：参与 hash 的配置值先排序、统一大小写，避免无意义缓存失效；
3. **Traceability**：用 `run_id` 把数据库记录关联到 LangGraph 的 `thread_id` 和 checkpoint。

这些细节决定了系统是否真正能被调试和复现。

## 最值得记住的一句话

> **LLM 输出永远应该被视为“不可信输入”，直到它通过明确的结构和业务校验。**

Pydantic 的价值不是把 Python 写得更“类型安全”，而是给 Agent 系统建立一道可执行的边界。

## 对实际项目的迁移方式

在真实研究或交易类系统里，可以把所有 Agent 输出都分成三层：

```text
模型原始输出
  ↓
Schema Validation
  ↓
Business Validation
  ↓
正式进入数据库 / 下游任务
```

例如一个预测研究 Agent 给出实验参数时，除了验证字段类型，还可以继续验证：

- 训练集日期是否早于测试集；
- horizon 是否合法；
- 特征名是否存在；
- 指标是否在合理区间；
- 是否使用了未来信息。

也就是说，Pydantic 解决的是第一层结构正确性，而真正生产级系统还要叠加业务规则。
