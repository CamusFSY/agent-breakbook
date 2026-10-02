# Agent Breakbook

**复现故障，验证修复，带走测试。**

一个可执行的 Agent 故障案例集：复现重复写入、工具卡死、重试风暴，查看修复前后的状态变化，再导出能接入自己项目的回归测试。

[English](README.md) · [案例说明](docs/cases.md) · [接入自己的 Agent](docs/adapters.md) · [参与贡献](CONTRIBUTING.md)

## 一分钟体验

需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。安装依赖需要联网；安装后的脚本演示无需 API Key，也不调用模型。

```bash
git clone https://github.com/CamusFSY/agent-breakbook.git
cd agent-breakbook
uv sync --locked
uv run breakbook demo --offline
```

三个 `broken` 案例预期失败，三个 `fixed` 案例预期通过。打开 `results/demo/report.html`，查看每项独立断言、工具事件和最终结果。目录同时包含 JSON 原始记录和 JUnit 报告。

| 案例 | 故障 | 修复 | 验证目标 |
| --- | --- | --- | --- |
| `lost-ack` | 写入成功但确认丢失，重试导致重复提交 | 稳定业务 ID + 服务端原子去重 | 恰好一次正确写入，回执真实 |
| `hung-tool` | 工具永久等待 | 应用层截止时间 + 取消 | 挂起任务被清理，诚实报告超时 |
| `retry-storm` | 持续失败引起反复重试 | 服务端尝试次数上限 | 不超出预算，诚实报告不可用 |

两个版本使用相同的脚本客户端逻辑，修复放在服务边界。实验外层的 watchdog 和工具调用上限只用于终止失控实验；触发它们算失败。

## 回归测试与 MCP

```bash
uv run breakbook run all --variant fixed --runs 20 --out results/regression
uv run breakbook run all --adapter scripted-mcp --variant both --out results/mcp
uv run breakbook run all --adapter scripted-mcp --no-fault --out results/healthy
uv run breakbook export lost-ack --format pytest --out exported/lost-ack
uv run pytest exported/lost-ack
```

`scripted-mcp` 启动真实 MCP stdio 子进程。导出的 pytest 默认仍是脚本演示，需要替换 `run_agent` 回调才会测试你的 Agent。它不是自动抓取任意应用的工具。

`run` 退出码：全部通过为 `0`，契约失败为 `1`，配置错误为 `2`，基础设施错误为 `3`。运行 broken 故障案例时退出 `1` 是预期结果。`demo` 只有在“故障复现 + 修复通过”都符合预期时才退出 `0`；报告保留真实的失败记录。同一个 `--out` 目录会覆盖旧报告，保留历史时请使用不同目录。

## 真实模型适配器

```bash
uv sync --locked --extra openai
# 在本机环境中设置 OPENAI_API_KEY，不要写入仓库。
uv run breakbook run lost-ack --adapter openai-agents \
  --model YOUR_ACCESSIBLE_MODEL_ID --variant both --runs 3 \
  --watchdog 60 --max-turns 8 --token-budget 20000 --out results/live
```

这里使用真实 OpenAI Agents SDK 和本地 MCP 服务。需要你有权限访问的模型，会产生 API 费用。SDK tracing 已关闭；模型请求仍然会发送给配置的模型服务商。

**v0.1.0 没有进行付费模型实测。** 已验证真实 SDK + 测试模型替身 + 真实 MCP 子进程。报告分别标记 `scripted`、`sdk-test-model`、`live-model`、`custom-adapter`，不把离线脚本包装成模型能力数据。真实模型可能在 broken 服务上自行安全恢复，不能预设它一定失败。

## 范围与限制

- 首版是三个合成案例，不是通用 Agent 排行榜，也没有声称模型成功率提升。
- “确认丢失”模拟提交后的应用层错误，不是 TCP 丢包；去重状态仅在当前服务进程内保留。
- 重试修复是次数限制，尚未实现完整退避、熔断和恢复策略。
- token 预算在模型请求之间和返回后检查，进行中的请求可能超出预算；不是精确费用上限。
- 验证器读取独立于 Agent 最终回答的状态，但不是防篡改证明或安全沙箱。

完整边界见 [架构说明](docs/architecture.md)。[FaultBench](https://github.com/mit-hun-k/faultbench) 和 [Agentic Chaos](https://github.com/DeepAgentLabs/agentic-chaos) 是相关工作；本项目的价值在于小案例、清晰修复和可带走的测试，不宣称首创故障注入。

## 开发

```bash
uv sync --locked --extra openai --group dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv build
```

欢迎贡献真实故障的最小复现、新适配器和能通过健康对照的修复。遵循 [贡献指南](CONTRIBUTING.md)。Apache-2.0 许可；这是独立社区项目，不代表 OpenAI 官方项目或背书。
