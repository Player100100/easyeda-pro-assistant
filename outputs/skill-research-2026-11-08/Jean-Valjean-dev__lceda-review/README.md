# lceda-review

**嘉立创EDA（EasyEDA Pro）原理图审查 skill** — 把 `.enet` 网表变成一份评分 + 分级问题清单的设计审查报告。

> KiCad 有 [kicad-happy](https://github.com/aklofas/kicad-happy)，嘉立创没有。这个项目补上。

```
$ node scripts/analyze.js examples/sample-board.enet

# 原理图审查报告 — sample-board.enet
**评分：37/100 · POOR**
器件 12 · 网络 13 · 错误 3 · 警告 6 · 提示 4

## ❌ 错误（3）
### 位号重复            R1
### 疑似重复的电源网络   +5V (4 pin) vs VCC +5V (1 pin)
### LED 没有串联限流电阻  LED1 (LED_0805) @ 3V3, LED_K
...
```

## 它查什么

| 分组 | 检查项 |
|---|---|
| 器件完整性 | 缺 Value、缺 LCSC 料号、缺封装、位号重复、同值写法不统一 |
| 网络体检 | **单点网络**、空引脚、**近重复电源网络**（`+5V` vs `VCC +5V`）、网络名含空格 |
| 去耦检查 | 每个 IC 电源脚所在网络的电容数量与总容量（≥100nF） |
| 电源树 | 稳压器输入/输出网络与电容、电阻分压/反馈比例 |
| ESD / 保护 | 对外连接器（USB/J/CN…）的信号上有没有 TVS 或保险丝 |
| LED 限流 | LED 是否真的串了限流电阻（区分"电阻在电源侧"和"接在别的网络上"） |
| 晶振负载电容 | `CL = C1·C2/(C1+C2) + 3pF` 与器件标称 `Load Capacitance` 对比 |
| 设计规则 | 最小线宽等板级规则 |

报告最后有 **检查覆盖表**，明确告诉你每一项是"通过"还是"发现问题"，没查的东西不会假装查过。

## 快速开始

### 1. 准备数据

**方式 A：命令行导出（需要 [easyeda-api](https://github.com/easyeda/easyeda-api-skill) skill + 桥接）**

把 `scripts/collect.js` 的内容作为 `code` 字段发给 bridge：

```bash
# Linux / macOS / WSL
jq -n --arg code "$(cat scripts/collect.js)" '{code:$code}' \
  | curl -s -X POST http://127.0.0.1:49620/execute \
         -H "Content-Type: application/json" --data-binary @- \
  | jq -r '.result.netlist' > board.enet
```

```powershell
# Windows PowerShell
$code = [IO.File]::ReadAllText('scripts/collect.js', [Text.Encoding]::UTF8)
$body = @{ code = $code } | ConvertTo-Json
$r = Invoke-RestMethod -Uri 'http://127.0.0.1:49620/execute' -Method Post `
       -Body $body -ContentType 'application/json'
[IO.File]::WriteAllText('board.enet', $r.result.netlist, (New-Object Text.UTF8Encoding($false)))
```

返回里的 `result.netlist` 就是网表 JSON 文本。

**方式 B：GUI 导出** — EDA 里**制造 → 导出 → 网表**，得到 `.enet`。

### 2. 跑审查

```bash
node scripts/analyze.js board.enet                 # Markdown 到 stdout
node scripts/analyze.js board.enet --out report.md # 同时写文件
node scripts/analyze.js board.enet --json          # 结构化结果
```

退出码：有 `error` 级问题时返回 `1`，可以直接当 CI 门禁用。

### 3. 作为 Agent Skill 使用

仓库根目录的 `SKILL.md` 是标准 [Agent Skills](https://agentskills.io/) 定义。放进你的 skills 目录即可：

```bash
git clone https://github.com/<you>/lceda-review.git ~/.dsh/skills/lceda-review
# 或 ~/.claude/skills/lceda-review
```

之后对 AI 说"帮我审查一块板子的原理图"，它会自己取网表、跑分析、按优先级给修复建议。

## 评分

`100 - Σ(错误×8 + 警告×3)×条目数`，下限 0：

| 分数 | 结论 |
|---|---|
| ≥85 | **READY** — 可以出板 |
| 60–84 | **NEEDS_WORK** — 有明确的待修项 |
| <60 | **POOR** — 别下单 |

## 开发

```bash
node tools/make-sample.js                      # 重新生成测试板
node scripts/analyze.js examples/sample-board.enet
node test/run.js                               # 回归测试
```

无依赖，Node ≥ 18。加了新检查项请顺手在 `tools/make-sample.js` 里埋一个"反面案例"，`test/run.js` 会断言它能被抓到。

## 已知局限

- **只管原理图**：网表里没有走线/铺铜信息，PCB 的 DRC 请用 `pcb_Drc.check()`。
- **语义靠位号前缀推断**：`U`=IC、`R/C/L`=被动、`USB/J/CN`=连接器。位号乱标会误判。
- **稳压器靠型号正则**（AMS1117/TPS/MP2/RT/XC6…），冷门型号识别不到，报告里没有"电源树"不等于没有电源。
- **评分是启发式的**：用来排优先级，不是认证结论。
- `.enet` 格式来自嘉立创EDA专业版客户端，字段可能随版本变化；遇到解析问题请开 issue 并附脱敏后的网表片段。

## License

MIT. See [LICENSE](LICENSE).

---

### English

`lceda-review` is a schematic design-review skill for EasyEDA Pro / 嘉立创EDA专业版. It parses the `.enet` netlist and reports missing values/LCSC parts, duplicate power rails, floating pins, decoupling gaps, regulator power trees, ESD protection gaps, LED series resistors, crystal load-capacitor mismatches and board rules — as a scored Markdown report. No dependencies, Node ≥ 18. Works standalone or as an agent skill alongside [easyeda-api-skill](https://github.com/easyeda/easyeda-api-skill).
