# Chapter 7：模型回退、输出漂移与 Schema 保险

> 对应原 Notebook：[`ch07/ch07_model_fallback.ipynb`](../../ch07/ch07_model_fallback.ipynb)

## 这一节解决什么问题

再强的主模型也会失败：它可能超时、出现幻觉，或者返回“语法上合法、语义上错误”的结果。生产系统不能把模型切换当作单纯的 API 替换，因为**模型变化会带来行为变化（behavior drift）**。

因此，一个可靠的 Agent 不仅要有备用模型（fallback model），还要保证备用模型输出能够继续通过后续的解析、校验、路由和工具调用链。

本 Notebook 用结构化工单分类任务展示一套三层回退策略，并强调：**结构化输出只能约束形状，不能保证判断一致。**

---

## 1. 三层回退策略（Three-tier Fallback Strategy）

### Tier 1：严格 JSON Schema（Strict JSON Schema）

由模型提供方在生成阶段直接约束输出，使 token 只能形成符合 JSON Schema 的结构。

优点：

- 通常只需要一次 API 调用；
- 结构正确率最高；
- 不需要额外的解析重试。

但它只保证 **shape（结构）**，不保证 **judgment（判断）**。

例如，同一条愤怒客户消息，不同模型可能分别输出：

- `priority = p0` / `sentiment = angry`
- `priority = p1` / `sentiment = frustrated`

两份 JSON 都完全合法，但会触发不同的升级路径、SLA 和值班告警。

### Tier 2：Instructor + Pydantic Validators

如果备用模型不支持 `response_format=json_schema`，就需要在应用层重新建立约束。

Notebook 使用 **Instructor** 配合 **Pydantic validators（Pydantic 校验器）**：

1. 模型先生成 JSON；
2. Pydantic 根据模型定义校验字段；
3. 若校验失败，Instructor 把错误反馈给模型；
4. 模型自动重试；
5. 通过后才进入后续流水线。

这层的价值在于：它不依赖某一家模型供应商的 strict mode，只要模型能生成 JSON-ish 输出，就可以工作。

`max_retries=2` 表示最多执行 3 次：首次尝试 + 2 次重试。连续失败后再降级到 Tier 3。

### Tier 3：Prompt-only + Canonicalization

最后一层不再依赖 strict schema 或 Instructor，而是在 Prompt 中明确描述字段结构，然后对返回内容做健壮解析和标准化。

这是 degraded mode（降级模式）：能保住业务链路，但应明确接受更高的不确定性、延迟和维护成本。

---

## 2. Schema 保险：把标准化放进 Pydantic

Notebook 的一个关键设计是：**不要让每条回退路径各自维护一套标准化逻辑。**

标准化映射应该尽可能进入 Pydantic `field_validator`，让 Tier 1、Tier 2、Tier 3 最终共享同一套数据契约。

例如：

```text
"High"           -> "p1"
"authentication" -> "login"
"anxious"        -> "frustrated"
```

这样做相当于在模型输出和业务逻辑之间增加一层 **Schema Insurance（Schema 保险）**：模型可以有表达差异，但进入核心系统之前必须被收敛到 canonical form（规范形式）。

需要注意，canonicalization 不能无限“猜测”模型意图。对于高风险字段，如果无法可靠映射，应当报错或触发人工处理，而不是静默修正。

---

## 3. Tier 3 为什么需要健壮 JSON 解析

降级模型经常不会只返回纯 JSON，它可能：

- 包一层 Markdown 的 ```json code fence；
- 在 JSON 前后添加解释文字；
- 字段名或枚举值大小写不一致；
- 返回近义词而不是约定枚举值；
- 少字段、多字段，或者类型漂移。

因此 Notebook 将 Tier 3 拆成两个步骤：

**Robust JSON Parsing（健壮 JSON 解析）**先尽可能提取结构；随后由 **canonicalize()（规范化）**将值收敛到统一内部表示。

这也是为什么 Prompt-only 不应该被当作和 strict schema 等价的方案：它本质上依赖“生成之后再修”。

---

## 4. 真正要测试的是整条回退链

生产测试不能只问：

> “备用模型能不能正常返回文本？”

而要测试：

```text
模型调用
  ↓
Tier 1 strict schema
  ↓（失败）
Tier 2 Instructor + Pydantic
  ↓（失败）
Tier 3 Prompt-only
  ↓
JSON parsing
  ↓
canonicalization
  ↓
validation
  ↓
业务路由 / handoff / tool call
```

只要其中任意一步在 fallback 模型上失败，这个 fallback 就不算真正可用。

尤其要覆盖：

- 字段缺失；
- 非法枚举值；
- 字符串 / 数字类型漂移；
- provider 不支持 strict schema；
- 自动重试耗尽；
- 模型主观判断发生漂移。

---

## 5. 回退会改变延迟预算

三层方案的成本并不相同。

| 层级 | 典型调用方式 | 延迟特征 | 可靠性来源 |
|---|---|---|---|
| Tier 1 | 单次 strict schema 调用 | 最低 | Provider 生成约束 |
| Tier 2 | Instructor + 自动重试 | 中等至较高 | Pydantic 校验 + retry |
| Tier 3 | 普通生成 + 后处理 | 波动最大 | Prompt + parser + canonicalization |

因此 fallback 设计必须和 **SLA、timeout budget、retry budget** 一起设计。

如果主模型 8 秒超时后才开始调用备用模型，而备用模型又允许 3 次重试，那么“理论上有 fallback”并不等于“用户请求还能在 SLA 内完成”。

---

## 6. 最容易被忽略的是 Judgment Drift

结构正确只是第一层问题，更难的是不同模型拥有不同的判断边界。

例如同一张工单：

```text
Model A -> p0 / angry
Model B -> p1 / frustrated
```

如果 `priority` 决定是否 PagerDuty 告警，`sentiment` 决定是否进入投诉升级队列，那么这种差异不是文风差异，而是**业务行为漂移**。

因此，在 Hardening（生产加固）阶段需要为 fallback chain 中的每个模型建立行为基线：

- 优先级分布是否系统性偏高 / 偏低；
- 风险类别是否存在明显漏判；
- 情绪、意图、严重程度等主观字段是否稳定；
- 与主模型的分歧是否在业务可接受范围内。

必要时，应针对关键判断字段增加 deterministic rules（确定性规则）或独立 judge，而不是完全依赖模型自身分类。

---

## 7. 生产落地清单

1. **至少准备一个经过完整验证的备用模型**，不要只验证“接口可调用”。
2. **为结构化输出建立统一 Pydantic contract**，所有 provider 最终进入同一个数据边界。
3. **把 normalization 放在共享 validator / canonicalizer 中**，避免三条路径出现三套语义。
4. **统计 fallback model 的行为漂移**，尤其关注会影响路由、SLA、审批和告警的字段。
5. **把 retry、timeout、fallback 层级纳入统一延迟预算**，防止级联重试把请求拖死。
6. **保留可观测性字段**：实际使用的模型、落在哪一层、重试次数、校验错误、最终 canonicalized value。

---

## 核心结论

模型回退不是“主模型挂了就换另一个模型”。

真正可靠的 fallback 需要同时解决三个问题：

**可调用性（availability） → 结构兼容性（schema compatibility） → 行为一致性（behavior consistency）。**

Strict JSON Schema 解决第一层结构约束，Instructor + Pydantic 提供跨模型的校验与恢复能力，Prompt-only + canonicalization 提供最后的业务连续性；但无论使用哪一层，都必须单独验证模型判断漂移是否会改变系统行为。