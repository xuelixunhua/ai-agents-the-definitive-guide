# Chapter 7：推理后端——冷启动、缓存与部署物理（Inference Backends）

对应 Notebook：[`ch07/ch07_inference_backends.ipynb`](../../ch07/ch07_inference_backends.ipynb)

当 Agent 调用模型时，它并不是抽象地“调用一个 API”，而是在等待某个 GPU 推理进程完成真实计算。模型权重要进入显存，Prompt 需要做 prefill，KV Cache 要占用显存，并发请求还会竞争显存和调度资源。

因此，Agent 的响应是 200 ms 还是 12 s，往往不是由 Python 代码决定，而是由推理后端的部署物理决定。

## 1. 五个关键问题

| 问题 | 发生了什么 | 对 Agent 的影响 |
|---|---|---|
| **Cold Start（冷启动）** | 模型权重从磁盘/网络加载到 GPU VRAM | 部署或扩容后的首批请求可能等待几十秒甚至更久 |
| **KV Cache** | Prompt 中每个 token 的 attention key/value 被缓存 | 上下文越长，占用的显存越多，TTFT 越高 |
| **Prefix Caching（前缀缓存）** | 多个请求复用相同 Prompt 前缀的 KV | 稳定 system prompt 可以显著降低重复 prefill 成本 |
| **Cache Invalidation（缓存失效）** | Prompt 前缀发生变化，已有 KV 无法复用 | 修改 system prompt、对话分叉、顶部插入上下文都会造成延迟突刺 |
| **Memory Pressure（显存压力）** | 模型权重 + KV Cache + batch 共同消耗显存 | 长会话会挤占其他请求缓存，恶化尾延迟与并发能力 |

Notebook 使用本地 **vLLM** 服务发起真实请求，展示这些现象，而不是只停留在概念层面。

---

## 2. 冷启动不是 Bug，而是部署税

冷启动通常包含连续的阻塞阶段：

```text
下载模型（如果本地没有缓存）
        ↓
反序列化并加载到 GPU VRAM
        ↓
初始化 / 编译部分 kernel、分配 KV Cache、热身 scheduler
        ↓
第一次真实请求
        ↓
进入稳定 warm state
```

所以从“服务进程启动”到“首 token 返回”，可能经历几十秒甚至更长时间。

典型触发场景包括：

- 重新部署；
- 容器重启；
- crash 后恢复；
- scale-to-zero 后再次扩容；
- 节点漂移到新 GPU。

### 常见缓解手段

- 设置 keep-alive 探针；
- 部署完成后主动发送 warm-up 请求；
- 设置 `min replicas > 0`，避免频繁 scale-to-zero；
- 提前把模型权重放到本地或高速共享存储；
- 对高可用服务做滚动发布，而不是全部实例同时重启。

这里的核心不是“把冷启动消灭”，而是让它变得 **可测量、可预期、可隐藏**。

---

## 3. KV Cache：Agent 的工作记忆，也是显存大户

Transformer 在自回归生成中，不需要每生成一个新 token 就重新计算历史 token 的全部 attention key/value，而是把过去的 K/V 保存下来，这就是 **KV Cache**。

对 Agent 来说，KV Cache 有一个非常现实的结论：

> 上下文越长，不只是 token 费用更高，GPU 显存占用和 Time To First Token（TTFT）也会更糟。

所以前一节提到的 Context Pruning 并不只是“省 API 钱”，同时也是推理延迟优化。

当并发用户多时，KV Cache 还会成为容量瓶颈：

```text
更长 context
  ×
更多并发 sequences
  ↓
更多 KV Cache 显存
  ↓
更容易 eviction / swap / 降低 batch capacity
  ↓
尾延迟升高
```

---

## 4. Prefix Caching：稳定前缀可以直接换来低 TTFT

很多 Agent 请求共享同一段稳定前缀，例如：

```text
[System Prompt]
[工具说明]
[固定策略]
[固定输出要求]
------------------  ← 稳定 prefix
[RAG 检索内容]
[用户画像]
[用户当前问题]
------------------  ← 可变 suffix
```

如果推理后端支持 Prefix Caching，它可以复用稳定前缀已经计算好的 KV Cache，而不必为每个请求重新做完整 prefill。

这就是为什么 Notebook 强调：**Prompt 设计不仅影响模型行为，也影响推理系统效率。**

### 设计原则

尽量把 Prompt 组织成：

```text
Stable Prefix + Variable Suffix
```

而不要频繁在最前面插入动态内容。

比如，RAG 片段、用户画像、会话临时变量如果放在最顶部，就会让整个前缀缓存失效；如果这些内容可以放到更靠后的区域，稳定 system prompt 的 KV 就更容易复用。

---

## 5. Cache Invalidation：灵活性的隐性成本

以下操作常常会导致 prefix cache 失效：

- 修改 system prompt；
- 更换工具定义；
- 在 Prompt 顶部插入动态 RAG 内容；
- conversation fork；
- 改变原本稳定的 policy / persona 文本。

从 Agent 设计角度看，这形成一个真实权衡：

```text
Prompt 越动态、越灵活
      ↕
缓存复用率越低、推理越贵
```

因此，高性能 Agent 往往需要同时考虑“语义结构”和“缓存结构”。

---

## 6. 三类主流开源推理后端

Notebook 对比了 **vLLM、TGI、SGLang**。三者都可以提供 OpenAI-compatible API，因此上层 Agent 代码可以尽量保持不变。

| 维度 | vLLM | TGI（Text Generation Inference） | SGLang |
|---|---|---|---|
| 维护方 | UC Berkeley 社区生态 | Hugging Face | LMSYS / SGLang 社区 |
| 关键调度机制 | PagedAttention | Continuous Batching | RadixAttention |
| Prefix Caching | 支持 APC | 相对弱，更多依赖其他缓存方式 | 内建 RadixAttention，更适合树状复用 |
| 多 GPU | Tensor / Pipeline Parallel | Tensor Parallel | Tensor / Expert Parallel |
| Speculative Decoding | 支持 | 支持 | 支持 |
| Quantization | AWQ、GPTQ、FP8、BitsAndBytes 等 | AWQ、GPTQ、EETQ、BitsAndBytes 等 | AWQ、GPTQ、FP8 等 |
| Structured Output | 支持 guided decoding | 支持 grammar-based output | 支持压缩 FSM |
| 适合场景 | 通用、高吞吐 | HF 生态集成 | 多轮、分支式 Agent 推理 |

### 怎么选

**vLLM**：默认优先考虑。模型支持面广、资料多、PagedAttention 成熟，适合大多数通用推理服务。

**TGI**：如果团队已经深度使用 Hugging Face Hub、Inference Endpoints、SageMaker 等 HF 体系，接入成本通常更低。

**SGLang**：如果应用包含大量多轮、分叉式推理，例如 Tree-of-Thought、自一致性、多分支工具调用，RadixAttention 对树状 KV 复用更有吸引力。

---

## 7. 为什么 Agent 代码应该 Backend-Agnostic

Notebook 的一个关键实践是：使用 OpenAI SDK 作为统一客户端，通过修改 `base_url` 等配置来连接不同后端。

```python
client.chat.completions.create(...)
```

上层 Agent 不应该深度耦合某个推理引擎的内部 API。理想情况下，切换：

- vLLM
- TGI
- SGLang
- OpenRouter
- 云厂商模型服务

主要应该是配置变化，而不是重写 Agent 工作流。

这会直接降低：

- 迁移成本；
- 单供应商锁定；
- 灾备切换难度；
- A/B benchmark 成本。

---

## 8. vLLM 中几个关键部署参数

Notebook 通过 OpenAI-compatible server 启动 vLLM，并重点演示以下参数：

| 参数 | 作用 | 风险/权衡 |
|---|---|---|
| `--model` | 模型 ID 或本地路径 | 决定加载哪个模型 |
| `--tensor-parallel-size` | Tensor Parallel 使用的 GPU 数 | 提高可承载模型规模，但增加通信 |
| `--gpu-memory-utilization` | vLLM 可使用的 VRAM 比例 | 太高易 OOM，太低则 KV Cache 容量不足 |
| `--max-model-len` | 最大上下文长度 | 越大，潜在 KV 显存需求越高 |
| `--swap-space` | KV overflow 可使用的 CPU RAM | 是安全阀，但 swap 会明显增加延迟 |
| `--dtype` | 推理精度 | 影响显存、吞吐与兼容性 |
| `--max-num-seqs` | 最大并发 sequence 数 | 控制 batch 和显存压力 |
| `--enforce-eager` | 关闭 CUDA graph capture | 启动更快，但通常牺牲部分吞吐 |

这些参数不是“调优细节”，而是部署容量模型的一部分。

---

## 9. 生产环境真正应该测什么

不要只看平均 tokens/s。Agent 更关心以下指标：

1. **Cold start duration**：实例从启动到可服务需要多久；
2. **TTFT（Time To First Token）**：用户多久能看到第一个 token；
3. **TPOT（Time Per Output Token）**：稳定生成阶段每个 token 的时间；
4. **P95 / P99 latency**：高并发下尾延迟是否失控；
5. **Cache hit rate**：Prefix Cache 是否真的被复用；
6. **VRAM utilization / KV usage**：显存瓶颈究竟来自模型还是缓存；
7. **Concurrency before degradation**：并发到多少后延迟开始快速恶化。

对 Agent 来说，**TTFT + 尾延迟** 往往比单纯平均吞吐更接近真实用户体验。

---

## 10. 生产部署检查清单

```text
☐ 已选定推理后端（vLLM / TGI / SGLang）
☐ 已启用 Prefix Caching（如果后端支持）
☐ System Prompt 按 stable prefix / variable suffix 设计
☐ 已实测冷启动时间
☐ 已配置健康检查和 readiness 探针
☐ 核心服务避免 scale-to-zero
☐ 已配置 Context Pruning / 最大历史 token
☐ 已估算模型权重 + KV Cache + runtime overhead 的显存预算
☐ 已测 TTFT、P95/P99 与最大稳定并发
☐ 上层 Agent 通过 OpenAI-compatible 接口保持后端解耦
```

---

## 一句话总结

Agent 的线上性能并不只取决于模型本身；**冷启动、KV Cache、Prefix Caching、显存压力和后端调度策略**共同决定了真实延迟与并发能力。理解这些“部署物理”，才能把一个能跑的 Agent 变成一个真正可服务的系统。