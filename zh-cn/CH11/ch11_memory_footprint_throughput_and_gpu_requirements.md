# Chapter 11：显存占用、吞吐量与 GPU 需求中文说明

> 对应原 Notebook：[`ch11/ch11_memory_footprint_throughput_and_GPU_requirements.ipynb`](../../ch11/ch11_memory_footprint_throughput_and_GPU_requirements.ipynb)
>
> 本页翻译并整理原 Notebook 的 Markdown、解释性文字与关键代码注释。模型名、变量名、函数名和运行输出保持英文。

## 这个 Notebook 在解决什么问题

这个 Notebook 的目标，是把“大模型到底需要多少 GPU、能扛多少并发、每 100 万输出 token 大概多少钱”这三个问题串成一套可以计算的容量规划方法。

它不是只看模型参数量，而是同时考虑：

- 模型权重需要占多少显存；
- KV Cache 会随着上下文和并发增长多少；
- hybrid attention（混合注意力）会怎样改变 KV Cache 增长；
- MoE（Mixture-of-Experts，混合专家）模型的“总参数量”和“每 token 激活参数量”为什么要分开；
- GPU 的显存容量、显存带宽、理论算力和小时成本怎样共同影响吞吐与单位经济性。

## 1. Prefill 与 Autoregressive Sampling

Transformer 推理可以粗略分为两个阶段。

### Prefill

模型一次性并行处理输入 prompt 的 token，并建立 Key-Value Cache（KV Cache，键值缓存）。KV Cache 可以理解为 attention 中需要长期保留的历史状态。

这个阶段主要是在“读上下文”，还没有逐 token 生成答案。

### Autoregressive Sampling

随后模型开始一个 token 一个 token 地生成输出。每生成一个新 token，都可以复用已经保存在 KV Cache 中的历史状态，而不需要重新计算所有旧 token。

因此，KV Cache 是推理速度的关键，也是长上下文和高并发时显存压力的核心来源。

## 2. 为什么经典 KV 估算公式不够了

传统上，经常会用类似 `4 · n_layers · d_model` 的简化规则估算 KV Cache 增长。但原 Notebook 强调：对 2026 年常见的新模型，这种估算会把几个不同问题混在一起。

原因是示例模型采用了 **hybrid attention（混合注意力）**：

- 只有一部分层使用完整 attention，因此 KV 会随着 context 持续增长；
- 一部分层使用 linear attention，状态近似固定，不会像传统 KV 一样线性增长；
- 还有一部分层使用 sliding-window attention，KV 只增长到 `sliding_window` 上限，之后不再继续扩大。

所以，真正决定长上下文 KV 增长速度的，不再是 `n_layers`，而是哪些层真的需要保存会随 context 增长的 KV。

## 3. MoE 为什么必须拆成“总参数”和“激活参数”

Notebook 中的部分模型还是 MoE（Mixture-of-Experts）。这类模型有两个非常不同的参数量概念：

- `total_params_billion`：模型一共拥有多少参数；
- `active_params_billion`：每生成一个 token 实际激活多少参数。

两者服务不同的计算：

### 显存底座：看 total parameters

模型权重必须驻留在显存里，因此总参数量决定最低显存需求。即使一次只激活其中少数专家，其他权重通常仍然需要可被访问。

### 吞吐和延迟：看 active parameters

每个 token 真正经过多少参数，才更接近决定计算量与显存带宽消耗。因此 MoE 的 token 生成成本更应该参考 `active_params_billion`，而不是简单拿总参数量计算。

这也是本 Notebook 最重要的拆分之一：**memory footprint 与 throughput/latency 不应该使用同一个参数量口径。**

## 4. Notebook 如何估算显存占用

原 Notebook 使用 hybrid-aware 的 `kv_cache_gib_for_context` 帮助函数，估计在指定 context length 和 `n_concurrent_request` 下所需的显存。

估算主要包含两块：

1. **模型权重驻留**：由总参数量和精度决定；
2. **KV Cache**：由并发数、上下文长度、KV head 数、head dimension、完整 attention 层数以及 sliding-window 上限共同决定。

其中 Gemma-4 示例还展示了一个更细的情况：full-attention layer 与 sliding-attention layer 的 KV geometry 不同，因此使用 `n_global_kv_heads` 与 `global_d_head` 单独覆盖全局注意力层的默认配置。

## 5. 如何从显存反推最大并发

大模型推理常常是 **memory-bound（受显存带宽限制）**，而不是纯粹 compute-bound。

把多个请求 batch 在一起，是提高吞吐的重要方式。但 batch 越大、同时维护的 sequence 越多，需要保存的 KV Cache 也越多。

因此，一个很实际的规划问题是：

> 在给定 GPU 数量和上下文长度下，最多能同时维护多少条请求？

Notebook 先估算一块或多块 GPU 可用于 KV 的剩余显存，再除以单条 sequence 的 KV 占用，从而给出最大并发上限。

需要注意的是：这个“最大上下文下的最大并发”往往是最保守的 worst-case bound。真实用户的 prompt 往往显著短于 `max_context_window`，所以实际可支持并发通常更高。

## 6. Throughput 与 Latency

Notebook 将 GPU 规格分成几个关键字段：

- `fp16_tflops`：理论 FP16 计算能力；
- `memory_gb`：显存容量；
- `memory_bandwidth_gbps`：显存带宽；
- `usd_per_hr`：单位小时 GPU 成本。

对现代 LLM 推理，显存带宽经常成为 decode 阶段的主要约束，因此 token throughput 不能只看 TFLOPS。

示例最终输出包括：

- memory footprint；
- max concurrent requests；
- prefill latency / token；
- TPOT（Time Per Output Token，每个输出 token 的时间）；
- end-to-end latency；
- per-sequence throughput。

## 7. 从 GPU 成本转成 $/1M output tokens

最后一个重要步骤，是把硬件成本转换成业务更容易理解的单位经济性。

Notebook 将显存和吞吐估算继续转换为：

- **每 100 万输出 token 的成本（$/1M output tokens）**；
- 结合 `CONCURRENT_USAGE_FACTOR`，计算每个“实际活跃用户”的有效成本。

这里的 `CONCURRENT_USAGE_FACTOR` 表示：已经采购或预留的 GPU 容量中，有多少比例在同一时间真正被用户占用。

这个指标很重要，因为业务成本通常并不由“GPU 每小时多少钱”直接决定，而由“GPU 实际利用率 × 每小时能生成多少 token × 用户并发”共同决定。

## 关键代码注释中文对应

### GPU 配置

- `GPU_SPECS`：GPU 规划参数表；其中 TFLOPS、带宽和价格都是容量估算输入。
- `ESTIMATE_GPU_NAME`：当前用于估算的 GPU 型号。
- `DEFAULT_ANALYSIS`：默认 GPU 数、prompt size、response size 和并发请求数。
- `CONCURRENT_USAGE_FACTOR`：预留容量中实际同时活跃的比例。

### 模型配置

- `total_params_billion`：总参数量，决定权重显存底座。
- `active_params_billion`：每 token 激活参数量，影响计算和 memory bandwidth。
- `n_full_attention_layers`：真正会让 KV 随上下文持续增长的 full-attention 层数。
- `sliding_window`：滑动窗口 attention 的 KV 上限。
- `n_kv_heads` / `d_head`：KV Cache 几何结构的核心参数。

### KV 计算

- `_full_attn_kv_channels(spec)`：确定 full-attention 层的 KV channel 数；Gemma-4 若存在全局 attention 专用配置，则优先使用它们。
- `kv_growth_per_token_gib(spec)`：估计超过 sliding-window 后，每新增一个 token 带来的 KV 显存增长。
- `kv_cache_gib_for_context(...)`：估算指定 context 下的 KV Cache 总显存。

## 使用边界与常见误解

1. GPU 价格是规划参数，不是永久常数。原 Notebook 本身也提醒：不同云厂商、区域和承诺周期的价格会变化，正式报价前必须核对实际 provider pricing。
2. TFLOPS 不是推理性能的唯一决定因素。decode 阶段经常是 memory-bound。
3. MoE 总参数量大，不代表每 token 的计算量也同样大；但它仍可能需要很高的权重驻留显存。
4. `max_context_window` 下的并发只是最坏情况，不能直接当作真实业务平均并发。
5. 这个 Notebook 是容量规划模型，不是严格的 serving benchmark；真实结果还会受 kernel、tensor parallel、batch scheduler、quantization、网络通信和 serving framework 影响。

## 一句话理解

这份 Notebook 的核心不是“算一张 GPU 表”，而是把 **模型结构 → 权重显存 → KV Cache → 最大并发 → token 吞吐 → 用户成本** 串成了一条完整的推理容量规划链路。