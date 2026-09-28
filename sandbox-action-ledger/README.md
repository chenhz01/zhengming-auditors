# SAL — 沙箱行为账本（Sandbox Action Ledger）

> 一句话：**Agent 声称它干了什么，和账本里记了它干了什么，对不对得上。**

起因是 DeepSeek 的 DSec 论文（arXiv:2609.22978，131 位作者，梁文锋署名）。
这篇 31 页的论文把 Agent 训练沙箱做到生产级：单单元 160 节点、日均 300 万沙箱、
峰值并发 38 万、创建速率 5000+/秒，承载了 DeepSeek V3.2→V4.1 全部 agentic RL 负载。

**但它自己承认了这个问题，然后没有给答案：**

> "没有任何单一机制能够防止所有智能体异常行为和系统故障，
> 因此我们将强化系统可观测性，以发现新兴问题，并随模型不断演进持续加强 DSec。"

论文通篇讲**效率**（内存 -40.2%、延迟膨胀 45.2%→17.3%、镜像加载 79min→45min），
关于「怎么知道 Agent 在这 300 万个沙箱里到底干了什么」——**一个字都没有**。

## 三件事

| 命令 | 干什么 | 依据 |
|---|---|---|
| `ledger` | append-only 动作账本，前缀哈希取证链（块内篡改即违规） | 复用 RHA 的取证链契约 |
| `recon` | 任务声明 vs 实际动作对账，找五类非预期动作 | DSec 论文原文点名的行为 |
| `carry` | GPU 抢占封存→恢复续跑，行为证据有没有跟着保住 | DSec 的招牌能力被空转了 |

五类非预期动作取自论文原文记录的真实现象：
翻日志找答案 / 伪造 RPC 直接问评测服务 / 改 `/bin/bash` 等运行环境 /
扫可达服务拉外部代码 / 走任务路径之外拿答案。

```bash
python sal_cli.py init ledger.json --claim '{"intent":"修登录态","expected_actions":["read_file","edit_file","run_tests"],"allowed_hosts":["github.com"]}'
python sal_cli.py add ledger.json --entry '{"kind":"tool_call","target":"run_tests","command":"pytest tests/test_server.py"}'
python sal_cli.py recon ledger.json --host github.com,pypi.org
python sal_cli.py carry  ledger.json
python verify.py                    # 33 项自检，全绿
```

## 最重要的设计：**对账要分两类**

`reconcile` 绝不输出「Agent 作弊了」。它只输出 diff，并把 diff 分成性质完全不同的两类：

- `claimed_but_absent` —— 声明了，账本没这条：可能是真没做，也可能是没记
- `unclaimed_present` —— 做了，声明里没写：越界嫌疑

判词也是分开的：`blind` = 一条都没记（说明根本没装账本，不是作弊）、
`gap` = 账本在工作但有缺、`review` = 账本完整但有越界嫌疑。

**不区分这两类 = 假阳性制造机。**

## 实测：在真实代码语料上，五类规则几乎全是噪声

拿 `~/.workbuddy/skills` 下 **622 个真实脚本**跑规则命中率：

| 规则 | 命中文件 | 占比 | 抽查结论 |
|---|---|---|---|
| env_probe | 41 | 6.6% | 全是正常的 `os.environ.get("GITHUB_TOKEN")` 配置读取 |
| egress_undeclared | 11 | 1.8% | 全是**文档里的文本提及**（README 的 `wget`、游戏列表的 `git clone`） |
| log_scraping | 1 | 0.2% | 是 shell 里读 `/proc/$pid/cmdline` 做进程管理 |
| fake_rpc | 1 | 0.2% | 是冒烟测试在调自己的 `/verify` 接口 |
| runtime_tamper | 0 | 0.0% | 零命中 |

整体 8.4%，低于 15% 失效边界，所以没有规则被判过宽。
但**判别力最高的是 0.2%**。

这不是工具的失败，这恰恰是 SAL 存在的理由：

> 同一个 `curl https://x`：出现在 README 里是文档，出现在账本里才是动作。
> **静态代码扫描分不清「说了」和「做了」，只有运行时账本能分清。**

## 能力边界（不粉饰）

1. **SAL 不是静态扫描器。** 它必须在运行时挂钩才能记账；拿代码去扫会得到上面的噪声表。
2. **`egress` 检测依赖人工维护的白名单。** 「查官方文档」这类出访没法自动判定正常与否，
   白名单里没写就是嫌疑 —— 这是设计约束，不是 bug。
3. **`env_probe` 在真实语料上判别力接近 0。** 读了就删也改变不了它是噪声底的事实，
   手册里照实记录。
4. **没有真实沙箱环境。** 账本格式、规则、取证链都是照 DSec 论文的公开描述设计的，
   没有在真实 Agent 训练管线上跑过。
5. **`carry` 只在造件上验证。** 没有真实 GPU 抢占现场可测。

零依赖，纯 Python 标准库。
