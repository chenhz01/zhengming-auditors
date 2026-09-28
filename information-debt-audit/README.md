# IDA — 信息债务审计器 v1.0

> 第十件抖音突破件 · 视频⑨ `7684121523032001826`「英伟达开源 Harness，AI 自己卷自己进化」
> 日期 2026-09-27 ｜ MIT License，可对外发布（授权 2026-09-28）

## 一句话

**harness 能算出「这次压缩回本了吗」，算不出「被丢掉的那部分后来有没有还回来」。**
SoL-Pi 的判据全是 token 数量项，没有一项度量被丢弃内容的性质。

## 工程件

| 文件 | 用途 |
|---|---|
| `ida_cli.py` | 主体：`audit`（单文件）/ `batch`（目录）/ `--json` |
| `verify.py` | 自检 31 项，含 CLI 级负向测试 + 交付物对账器负向测试 |
| `audit_deliverable.py` | 交付物对账器：按真实基线逐格核手册（非搜字符串）， |
|  | 另核「手册标注的 skill 版本 == SKILL.md 真实 version」 |
| `audit_real.json` | 真数据落盘（本机 Codex rollout） |

```bash
python audit_deliverable.py            # 对账手册，退出码 0 = 通过
python audit_deliverable.py --html 别的.html
```

对账器五格：①合计句是真实基线值 ②§二线索表同口径 ③五维均分自洽 ④已修旧值零残留
⑤标注版本与 SKILL.md 一致。**任何一格失效都会明说，不静默。**

```bash
python ida_cli.py batch <rollout目录>
python ida_cli.py audit <单个.jsonl> --json
python verify.py
```

## 判据（v1.1 定稿）

| 判据 | 含义 |
|---|---|
| `n_trunc` | 大输出被丢弃的次数（≥10000 token 计入） |
| `n_cited` / `cited_rate` | 其中有多少后来被重新引用（按路径指纹配对） |
| `n_unwarned` | harness 没告知「已截断」的次数 |
| `decision_gap` | 最后一次截断距「宣布完成」隔了几步 |
| `tail_debt_ratio` | 收尾 25% 里丢掉的 token 占比 |

**结论五态**：`ok` / `caution` / `debt_risk` / `informed_close` / `no_truncation`

⚠ `no_truncation` 是「不在适用域」，**不是干净**。打印时必须明说。

## 真数据（[一手] 本机 Codex rollout）

| 会话 | 截断 | 丢 token | 判据间距 | 结论 |
|---|---|---|---|---|
| rollout-07-20T13-34-52 | 1 | 14158 | 1 | informed_close |
| rollout-07-20T17-49-14 | 1 | 14158 | 1 | informed_close |
| rollout-07-21T14-29-28 | 0 | 0 | - | no_truncation |
| rollout-07-23T21-18-23 | 0 | 0 | - | no_truncation |

合计：4 会话 / 2 次截断 / 累计丢 28316 token / 引用率 0.00 / 收尾债务比 0.9999

## 踩坑（v1.0 → v1.1 重写说明）

### 1. 判据前提被真语料推翻（最重要的一条）

v1.0 用「同一 call_id 事后出现 ⇒ 已偿还」配对。真跑：**97 个 call_id 零命中**。
原因：Codex rollout 里 `function_call`(id=`fc_call_00_x`) 与
`function_call_output`(call_id=`call_00_x`) 是**成对同现的**，指的是同一次调用，
不存在「事后按 id 取回」。**被测语料里根本没有句柄机制。**

于是 v1.0 的 `dangling_rate` 恒 1.00、`unpaid_index` 恒 14158.00 —— **那不是发现，
是配对失效的证据**。差点写成「实测悬空率 100%」。

→ 换成可测的东西：**截断发生的时序**。

### 2. 知情 vs 不知情（v1.1 的误报）

v1.1 把「截断后立刻收工」一律判 `debt_risk`。查原始因果发现
`Warning: truncated output` **就写在输出里**，agent 看得见，它收工是知情决策。
→ 只有 `n_unwarned > 0` 时收工才是真欠债；知情收工单列 `informed_close`（记账不报警）。

### 3. 子解析器漏 `--json`（与第九件同 bug，连犯两次）

第九件 `lga_cli.py` 的第一个 bug，第十件原样再犯一次 ⇒ §S3.4 触发规则层升级。
今后再加子命令，`--json` 一律同定义，并在 main 里用 `getattr` 兜底。

### 4. 裸 payload 静默漏解析

`_infer_kind` 只认死几种 type 值，payload 自带的 `kind` 被忽略 → `task_complete`
被丢掉 → 判据少一块证据。修：payload 自带 `kind` 优先。

### 5. 交付后回审抓到的四个（都长在「量交付物的工具」上）

本件的对手是「Agent 压掉证据却不知道」。回审时我发现，**同类病发生在我自己造的检查器上**：

1. **修 A 时删掉了 B 的凭据** —— 为修 HERE，顺手删掉负向测试里的 `--html", bad`，
   负向测试退化成「跑正例」，绿灯照常。**最隐蔽的一种失效：测试还在，只是测的是别的事。**
2. **手写切 `__file__`** —— `rsplit("\\")` 在混合分隔符下少切一层；
   单跑（裸文件名）与被调用（混合路径）两种"能跑"靠不同机制。统一改 `Path(__file__).resolve().parent`。
3. **崩溃也算抓到** —— rc=1 但那是对账器自己 `Traceback`，与"抓到问题"输出无差别。
   新增断言「输出里不许出现 Traceback」。
4. **detail 截错位置** —— `out[:180]` 取头部，Traceback 根因在尾部：
   检查器为了显示细节，恰好切掉了它要找的证据。改取 `[-400:]`。

### 6. 一把钥匙关了三扇门（静默失效）

`IDA_NO_RECURSE` 防递归的 env，顺手把「自检项数」那一格也关掉了，而且**静默** ——
负向测试喂错的项数，对账器照样报通过。**一个从没跑过的检查，比没有检查更危险。**
→ 防护生效时必须打印「这一格未被校验」。同时在 verify 里加断言，要求这个提示真的会打印。

### 7. 正则照着「我以为的格式」写

版本号那格漏了 `<code>` 前的空格 ⇒ 匹配不到 ⇒ 报 `vNone`，
**检查没跑成，还伪装成「这里有问题」**。→ 一律 `\s*` 容错。

### 8. 自查数字只对一半

对账器取 verify 输出时只取了分子、拿它当分母 ⇒ 永远显示 `X/X`；
手搓一行 `[PASS]` 只进分母没进计数器 ⇒ 自检永远 29/30，一条 FAIL 都没有却不是全绿。
**我在这份 README 里批「数字只对一半」，自己刚犯的就是这个。**
凡是断言只能有一条出处。（现在 31/31，对账器也会核 verify 输出的分子分母是否自洽）

## 阈值公开声明

`LARGE_OBS_TOKENS=10000`（对齐 SoL-Pi ObservationPack 的 10KB 量级）、
`DECISION_GAP_RISK=1`、`TAIL_DEBT_RISK=0.50` —— **全部是工程取值，未标定**。
它们度量「文本/时序像不像有问题」，不度量「这条省略对不对」。
写进公开材料时必须带上这句（第九件留下的纪律）。

## 与相关工作的区别（发布前必答，正面回答）

**和 `context-debt`（3★, 2026-03-23, stale context）什么区别？**
答案：那两个测量「上下文变陈旧」，IDA 测「被主动压缩掉且从未读回」——相邻但不同层。
