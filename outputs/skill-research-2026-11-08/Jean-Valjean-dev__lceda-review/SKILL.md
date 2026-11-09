---
name: lceda-review
description: >-
  Schematic design review for EasyEDA Pro / 嘉立创EDA专业版. Turns an exported
  `.enet` netlist into a scored design-review report: missing values, missing LCSC
  part numbers, duplicate or near-duplicate power rails, single-pin nets, IC
  decoupling coverage, regulator power tree, resistor-divider ratios, ESD
  protection on connectors, LED series resistors, crystal load-capacitor
  validation and board-level design rules. Use when the user asks to review,
  audit, check or "看看有没有问题" for an EasyEDA / 嘉立创EDA schematic, or before
  sending a board to JLCPCB. Triggers: "审查原理图", "检查原理图", "原理图 review",
  "review schematic", "嘉立创EDA 审查", "看看这块板子有没有问题".
license: MIT
compatibility: Node.js 18+; optionally the easyeda-api skill + bridge for live export
metadata:
  author: Jean-Valjean-dev
  version: "0.1.0"
---

# lceda-review — 嘉立创EDA 原理图审查

把 EasyEDA Pro 导出的 `.enet` 网表变成一份可执行的审查报告：**评分 + 分级问题清单 + 修复建议**。

## 什么时候用

用户说"帮我审查原理图 / 看看这块板有没有问题 / 出板前检查一下"，或者你正准备把设计发给 PCB / 嘉立创下单时。

## 工作流

### 第 1 步：拿到网表

**方式 A — 编辑器在线导出（推荐，需要 easyeda-api skill）**

如果 `easyeda-api` skill 已接入（bridge 在 49620，`/health` 返回 `edaConnected: true`），执行这段代码取网表：

```bash
curl -X POST http://127.0.0.1:49620/execute -H "Content-Type: application/json" \
  -d '{"code": "<scripts/collect.js 的内容>"}'
```

返回的 `result.netlist` 就是网表 JSON 文本，把它存成文件，例如 `<工程目录>/review/board.enet`。

> Windows PowerShell 5.1 读 `collect.js` 时务必用 `[IO.File]::ReadAllText($p, [Text.Encoding]::UTF8)`，默认编码会把中文注释读成乱码，`new AsyncFunction` 直接报 `Unexpected token`。

**方式 B — 用户手动导出**

EDA 里：**制造 → 导出 → 网表**（或 `sch_ManufactureData.getNetlistFile()`），把 `.enet` 文件给我。

### 第 2 步：跑分析

```bash
node scripts/analyze.js <file.enet> --out report.md
```

- 默认输出 Markdown 到 stdout；`--out` 同时写文件
- `--json` 输出结构化结果（便于二次处理或做 CI 门禁）
- 有 `error` 级问题时进程退出码为 1

### 第 3 步：解读与修复

先看报告顶部的**评分**和 **❌ 错误**，再看 ⚠️ 警告，ℹ️ 提示按需。

把发现按这个优先级讲给用户：

1. **❌ 错误** — 必须改，不改板子会废（重复电源网络、缺封装、位号重复、LED 无限流）
2. **⚠️ 警告** — 强烈建议改（缺 LCSC、去耦不足、晶振电容偏差、ESD 缺失）
3. **ℹ️ 提示** — 记账（值写法不一致、网络名带空格、分压比、电源树）

修复建议按问题类型给（agent 可以直接用 easyeda-api 改，也可以让用户改）：

| 问题 | 修复方式 |
|---|---|
| `net-rail-collision` 重复电源网络 | 用网络标签把两段连起来，或统一改成一个网络名 |
| `decoupling-missing` 去耦不足 | 每个电源脚就近放 100nF，大电流器件再加 1~10µF |
| `esd-missing` | 对外信号加 TVS（USB 用 USBLC6/ESD 阵列），电源入口加保险丝 |
| `lcsc-missing` | 用 `lib_Device.getByLcscIds()` 绑定料号，或在立创商城搜同规格 |
| `value-missing` | 补 Value（LED 尤其常见） |
| `led-no-resistor` | 串 330Ω~1kΩ 限流电阻 |
| `crystal-load-off` | 按 `CL = C1·C2/(C1+C2) + 3pF` 反算，把两颗电容换到 2×(CL-3pF) 左右 |
| `ref-duplicate` | 重新标注位号（Annotate） |

### 第 4 步：复检

改完重新导出网表再跑一遍，确认错误清零、评分上升。**不要只报告不复查。**

## 检查项

| 组 | 内容 |
|---|---|
| 器件完整性 | 缺 Value / 缺 LCSC / 缺封装 / 位号重复 / 同值写法不统一 |
| 网络体检 | 单点网络、空引脚、**重复电源网络**、网络名含空格 |
| 去耦检查 | 每个 IC 电源脚所在网络的电容数量与总容量 |
| 电源树 | 稳压器输入/输出网络与电容、电阻分压比 |
| ESD / 保护 | 对外连接器信号上是否有 TVS / 保险丝 |
| LED 限流 | LED 是否串了限流电阻 |
| 晶振负载电容 | `CL = C1·C2/(C1+C2) + 3pF` 与器件标称值对比 |
| 设计规则 | 最小线宽等板级规则 |

## 注意

- 网表里**没有** PCB 走线信息，走线/铺铜/EMC 不在这份检查范围内——那是 `pcb_Drc.check()` 和人工的事。
- 器件语义靠位号前缀推断（`U`=IC、`R/C/L`=被动、`USB/J/CN`=连接器）。位号乱标会导致误判。
- 稳压器靠型号正则识别（AMS1117/TPS/MP2/RT/XC6 等），冷门型号会漏，报告里没看到 `电源树` 不代表没有稳压器。
- 评分是启发式的，用来快速排序问题，不是认证结论。
