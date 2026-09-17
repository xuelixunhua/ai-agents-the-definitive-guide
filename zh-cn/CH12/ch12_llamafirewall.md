# Chapter 12：LlamaFirewall 分层 Prompt 安全中文说明

> 对应原 Notebook：[`ch12/ch12_LlamaFirewall.ipynb`](../../ch12/ch12_LlamaFirewall.ipynb)
>
> 本页翻译并整理原 Notebook 的 Markdown、解释性文字与关键代码注释。代码逻辑、类名、函数名、API 名称和运行输出保持英文。

## 这个 Notebook 在做什么

这个示例使用 **LlamaFirewall** 为 AI Agent 构建一层分层的 prompt-security firewall（提示词安全防火墙）。

目标不是简单写几个正则表达式，而是把安全检查拆成多层：

1. 规则层检测 prompt injection、秘密窃取、异常格式、不可见 Unicode 字符和角色操纵；
2. Trust Context（信任上下文）根据输入来源调整风险权重；
3. Semantic Scoring（语义评分）使用 LLM Judge 识别被改写、无法被简单规则匹配的攻击；
4. Gate + Cache（门控与缓存）只把真正模糊的样本送去昂贵的语义分类器；
5. 最后再把安全层接到一个故意“容易泄密”的 Agent 前面，做端到端验证。

## 为什么需要分层，而不是只靠 Regex

规则扫描非常适合处理明确模式，例如：

- “ignore previous instructions”；
- 明确要求输出 system prompt；
- 已知的 exfiltration（敏感信息外泄）措辞；
- 特殊 Unicode / zero-width 字符；
- 明显的 role override。

它的优点是快、便宜、可解释。

但攻击者可以把同一个意图换一种说法。只靠字符串和 regex 很容易漏掉语义相同、表面形式完全不同的攻击。因此 Notebook 又增加了一个 LLM-based semantic scorer，用于处理规则层无法确定的边界样本。

这形成了一个典型的 **cheap-first, expensive-when-uncertain** 安全架构：能用规则判断的先判断，只有不确定样本才升级到模型判断。

## Trust Context：同一句话在不同来源里风险不同

Notebook 定义了 `TrustContext`，用于描述当前输入来自哪里。

原示例包含三档：

- `untrusted`：默认，匿名用户或第三方输入，使用完整风险权重；
- `developer`：经过认证的开发者输入，对某些 exfiltration / format 信号降低权重；
- `tool`：工具返回的数据，对 injection 与 exfiltration 提高权重。

这背后的核心思想是：

> 文本本身不是唯一风险来源，**文本所处的位置和来源**也是安全上下文的一部分。

例如，“把上面的内容原样输出”出现在开发调试指令里，和出现在一个外部网页抓取结果里，其风险完全不同。

对于 Agent 系统尤其如此，因为 tool output 经常来自不受信任的外部环境，而模型又会把这些文本与开发者指令一起放进上下文中。

## `AdvancedPromptSecurityScanner`

Notebook 注册了一个自定义 scanner：`AdvancedPromptSecurityScanner`。

它对风险进行分类，并为不同类别设置独立上限，例如：

- `injection`：提示词注入；
- `exfiltration`：敏感信息或秘密窃取；
- `format`：可疑格式与结构操纵；
- `invisible`：不可见字符。

这种设计比“命中一条规则就 +1 分”更合理，因为不同风险信号的含义不同，不能简单无限叠加。

### 类级配置

Notebook 使用 class-level config，使 LlamaFirewall 从 registry 无参实例化 scanner 时，也能读取：

- `_semantic_scorer`；
- `_audit_only`；
- `_debug`。

`configure()` 用于给这些 registry-created scanner 设置默认配置。

### `audit_only`

当 `audit_only=True` 时，scanner 会显著提高 block threshold，相当于“只记录、不真正阻断”。

这种模式很适合上线前 shadow testing：先观察规则会命中什么，评估 false positive，再决定是否正式启用阻断。

## Gate：什么时候才调用 Semantic Scorer

语义 Judge 更贵、更慢，所以 Notebook 不会对每个请求都调用它。

整体思想是把样本分成三类：

1. **明显安全**：规则分很低，直接 allow；
2. **明显危险**：规则分已经很高，直接 block / escalate；
3. **模糊区间**：规则无法确定，才交给 semantic scorer。

这类 gating 设计有三个好处：

- 控制 LLM 安全分类成本；
- 降低安全层额外延迟；
- 保留规则命中的可解释性，同时补上语义覆盖能力。

Notebook 还加入 cache，避免同一内容重复调用 semantic scorer。

## 不可见 Unicode 为什么是风险信号

攻击文本可以利用 zero-width 或其他不可见字符，把本来应该连续出现的危险关键词拆开，从而绕过肉眼检查或朴素字符串匹配。

因此 scanner 会检测这类字符，并按照出现数量增加风险分数，同时设置 floor / cap，避免评分失控。

这不是说“出现不可见字符就一定是攻击”，而是把它作为一个需要与其他信号共同判断的风险特征。

## 端到端测试：故意使用一个会泄密的 Agent

Notebook 最后构造了一个 travel-booking agent，并故意在 system prompt 中放入一个假的 API key。

这个设计不是为了演示 Agent 功能，而是用来验证安全防火墙是否真的站在 Agent 前面发挥作用。

执行逻辑是：

- 被 block 或 escalate 的输入，不传给下游 Agent；
- 被 allow 的输入，才真正进入 Agent；
- Agent 执行后，再检查返回内容里是否出现 secret leakage。

因此测试不止验证“scanner 有没有打高分”，还验证最终系统是否真的阻止秘密流出。

这比单独测分类准确率更接近生产安全目标。

## 安全链路可以理解为五层

### 1. Pattern scanning

识别已知 injection、exfiltration、format 和 invisible-character 信号。

### 2. Trust-aware weighting

根据输入是 user、developer 还是 tool output，重新调整风险权重。

### 3. Semantic judge

只对不确定样本调用 LLM classifier，识别 paraphrased attacks。

### 4. Policy decision

将最终风险映射成 allow、block 或 human-in-the-loop / escalation。

### 5. Downstream verification

真正执行允许通过的请求，并验证是否发生 secret leakage。

## 关键代码注释中文对应

- `TrustContext`：单次调用的信任上下文，用于调整 scanner 激进程度。
- `category_multiplier()`：根据 trust level 调整不同风险类别的权重。
- `CATEGORY_CAPS`：各类风险信号可贡献的最高分。
- `INVISIBLE_PER_CHAR`：每个不可见字符增加的风险量。
- `INVISIBLE_FLOOR`：检测到不可见字符时的最低风险底线。
- `HITL_THRESHOLD`：进入 Human-in-the-Loop / escalation 的阈值。
- `_semantic_scorer`：语义风险评分器。
- `_audit_only`：仅审计、不正式阻断的运行模式。
- `_debug`：调试模式。
- `configure()`：给 registry 实例化出来的 scanner 设置默认配置。

## 适用边界与常见误解

### 1. Firewall 不能让模型“绝对安全”

它只是新增一道防御层。真正的 Agent 还需要最小权限工具、secret 隔离、审批 gate、输出过滤和审计日志。

### 2. LLM Judge 本身也不是可信根

Semantic scorer 会有 false positive 和 false negative，因此不应该完全替代 deterministic rules。

### 3. Tool Output 也必须被当作潜在攻击面

Prompt injection 不只来自用户。网页、PDF、数据库记录、邮件正文都可能携带攻击文本。

### 4. 安全策略需要按来源和上下文调整

所有输入统一使用相同阈值，往往会在安全性和可用性之间产生不必要的冲突。

### 5. 最终指标应该是系统后果

真正重要的不是“扫描器打了多少分”，而是恶意指令有没有被执行、工具有没有被误调用、secret 有没有泄漏。

## 一句话理解

这份 Notebook 展示的是一个更接近生产环境的 Prompt Security 架构：**规则先筛选 → 根据输入来源调整风险 → 模糊案例交给语义 Judge → 高风险请求阻断或升级 → 最后用真实 Agent 执行结果验证是否真的防住了泄密。**