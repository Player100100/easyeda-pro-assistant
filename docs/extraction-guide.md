# 从 `.epro2` 提取完整的原理图与 PCB 信息

> 2026-11-07 校订：下文“0 命名差异”是历史运行统计，旧校验器曾漏掉自动网重接。新版 `validate_netlist.py` 已补共有引脚拓扑比较，但历史样本尚未用新版重跑；未匹配对象仍须解释。详见 [判据核查](review-criteria-assessment.md) 与 [v2 判据](review-criteria-v2.md)。

**结论**：用 `src/extract.py` 一条命令把 `.epro2`（V3）拆成 5 个文件——文档索引、
原理图、PCB、网表、人读摘要。原理图网表是按几何重建的（文件里没有现成网表），
PCB 网表直接读 `PAD_NET`，是该文件内的连接记录，不等于实物测量。两个真实工程验证通过：

| 工程 | 编辑器 | 原理图页 | 原理图元件 | PCB 元件 | PCB 焊盘 | 记录数 |
|---|---|---|---|---|---|---|
| 【DIY电子】关灯神器 | 3.2.186 | 1 | 39 | 39 | 109 | 7265 |
| 立创·Candis-ESP32S31 开发板 | 3.2.186 | 11 | 292 | 291 | 939 | 34763 |

关灯神器：108 个可比引脚中 66 个命名一致、42 个两侧都是自动编号、**0 个命名冲突**。
Candis：901 个可比引脚中 744 个命名一致、134 个自动编号、22 个冲突，全部集中在
FPC1（引脚号与焊盘号反序，见「实测发现」）。

更强的验证：拿 EasyEDA 自己导出的 Protel 网表做逐引脚对照（§6.1），
原理图重建结果的历史统计是 **两个工程都是 0 个命名差异**；这是旧校验器的结果，未用新版拓扑校验重跑，不能单独证明成员分组一致。

---

## 1. 怎么用

```bash
python src/extract.py <工程.epro2> [--out 目录] [--with-poured]
```

默认输出到项目旁的 `<项目目录名>-data/outputs/extract/<工程名>/`（记作 `<DATA_DIR>/outputs/extract/<工程名>/`），目录自动创建；可用 `EPRO2_DATA_DIR` 指定绝对路径，`--out` 也必须位于项目外。详见 [运行产物目录](output-directories.md)。产物：

| 文件 | 内容 |
|---|---|
| `index.json` | 工程元数据、全部文档、BOARD→SCH→SCH_PAGE / BOARD→PCB 层级 |
| `schematic.json` | 每页元件（位号、器件、封装、位置、旋转、镜像）、引脚绝对坐标、导线折线、网络标志、文字、图框；外加 SYMBOL/DEVICE 库 |
| `pcb.json` | 每块 PCB 的层表、叠层、元件、焊盘（绝对坐标 + 网名）、走线、过孔、铺铜、板框、规则、文字、尺寸、3D 壳；外加 FOOTPRINT 库 |
| `netlist.json` | 原理图网表、各 PCB 网表、独立焊盘、逐引脚对比、位号对比、短接符号 |
| `summary.txt` | 上面这些的摘要，冲突逐条列出 |

`--with-poured` 才导出 `POURED`（铺铜计算结果）。它体积大、可由 `POUR` 重建，
默认不写。

只想知道有哪些文档，用读取器：

```bash
python src/epru_reader.py <工程.epro2> --list
python src/epru_reader.py <工程.epro2> --dump <doc-uuid>   # 原始记录，一行一条
```

如果你同时有 EasyEDA 导出的 Protel 网表，可以直接校验重建结果（见 §6.1）：

```bash
python src/validate_netlist.py <工程目录>/netlist.json <EasyEDA导出的.net>
```

## 2. 每个字段从哪条记录来

| 要的东西 | 来源记录 | 输出位置 |
|---|---|---|
| 工程标题 / 编辑器版本 | `project2.json` | `index.json` |
| 文档清单 / 类型 / 标题 | `DOCHEAD` + 每文档的 `META` | `index.json.documents` |
| 符号引脚（编号、名称、类型） | `SYMBOL` 文档的 `PIN` + `ATTR` | `schematic.json.symbols` |
| 器件绑定的符号/封装/网名 | `DEVICE` 的 `META.attributes` | `schematic.json.devices` |
| 封装焊盘几何 | `FOOTPRINT` 的 `PAD.defaultPad` | `pcb.json.footprints` |
| 原理图元件 | `SCH_PAGE` 的 `COMPONENT` + `ATTR` | `schematic.json.pages[].components` |
| 导线 | `LINE.lineGroup`；组头是 `WIRE`；网名在 `ATTR{parentId=组id, key=NET}` | `pages[].wires` |
| 网络标志（GND/+5V 等） | `COMPONENT` 的 `ATTR.Global Net Name` | `components[].global_net` |
| 短接标识 | `DEVICE` 的 `tags` 含 `短接标识`（title 多为 `Short-Symbol`） | `netlist.json.schematic.net_ties` |
| PCB 元件与封装 | `PCB` 的 `COMPONENT` + `ATTR.Footprint`；为空时回落 `DEVICE.attributes.Footprint` | `pcb.json.pcbs[].components` |
| PCB 元件焊盘网名 | `PAD_NET` 的复合 id `["PAD_NET", 元件id, 焊盘号, 封装PAD-id]` | `components[].pads[].net` |
| PCB 独立焊盘网名 | `PAD.netName` | `pcbs[].standalone_pads` |
| 走线 | `LINE.netName`（铜层上的 LINE） | `pcbs[].tracks` |
| 过孔 / 铺铜 | `VIA` / `POUR`（`POURED` 可选） | `pcbs[].vias` / `pours` |
| 板框 | `POLY.layerId == 11`（OUTLINE） | `pcbs[].outline` / `board_size` |
| 层定义 / 叠层 | `LAYER` / `LAYER_PHYS` | `pcbs[].layers` / `stackup` |
| 设计规则 | `RULE` / `RULE_TEMPLATE` / `RULE_SELECTOR` | `pcbs[].rules` |
| 文字 | 原理图 `TEXT`；PCB `STRING` | `texts` |

## 3. 坐标、单位、朝向

- **存储单位**：原理图 1 单位 = 0.01 in；PCB 1 单位 = 1 mil。
  依据：Candis 过孔 `holeDiameter=12` / `viaDiameter=24` 对应 0.305 / 0.610 mm；
  关灯神器板框 `2320.9 × 1255` mil = 59.0 × 31.9 mm。
- **不要用 `CANVAS.unit` 反推存储单位**：那是显示单位，`gridXSize` 也按显示单位写。
- **局部坐标 → 文档坐标**（实测拟合）。旋转部分符号/封装相同：

  ```
  X = cx + x·cosθ + y·sinθ
  Y = cy − x·sinθ + y·cosθ
  ```

  原理图的 θ 取 `COMPONENT.rotation`，镜像取 `isMirror`；
  PCB 的 θ 取 `COMPONENT.angle`，`layerId == 2`（底层）默认镜像。

- **镜像的含义在原理图和 PCB 上不一样**，这是实测出来的坑：

  | 文档 | 镜像做法 | 公式 |
  |---|---|---|
  | 原理图 | 先旋转，再按文档竖直轴翻转 | `X = cx − (x·cosθ + y·sinθ)`，Y 不变 |
  | PCB | 先把局部 x 取反，再旋转 | `x = −x`，然后套上面的旋转式 |

  依据：原理图用「竖直轴翻转」时，Candis 901 个引脚与 EasyEDA 自带网表
  0 冲突（用「局部 x 取反」有 8 个冲突，集中在 Q5/C61/C102/C120）；
  PCB 用「局部 x 取反」时，底元件焊盘落在同网走线上的比例是
  Candis 146/280、关灯神器 34/101，换成竖直轴翻转只剩 28/280、4/101。
- **引脚 `(x, y)` 就是连接点**，`length`/`rotation` 只决定引脚本体朝哪边画。
- PCB 元件坐标、焊盘坐标、板框都是同一套 mil 坐标，可直接叠加。

## 4. 原理图连接是怎么重建的

原理图文件里没有网表，只有几何。`extract.py` 按下面的顺序建图（并查集）：

1. **同一 `lineGroup` 的所有 `LINE` 是一个节点**（一根导线）。
2. **端点重合**的导线段/导线组连成一个节点。
3. **引脚点落在导线上**（端点或线段内部）就连到该导线。
4. **两个引脚坐标重合**时直接相连（引脚对引脚，无导线）。
5. **网络名**：导线 `ATTR.NET`、网络标志的 `Global Net Name`。同名合并；
   标志是全局网，导线标签是否跨页合并看 `CONFIG.UNIVERSAL.netLabelCrossPageConnection`
   （两个样本均为 `true`）。
6. **短接标识**：符号两侧引脚属于同一个网，直接合并。
   依据：关灯神器里 `GND` 与 `AGND` 被一个短接符号连起来，PCB 侧也只有一个
   `AGND` 网（26 个元件焊盘 + 1 个独立焊盘），原理图合并后 26 个元件引脚，
   逐个 (位号, 引脚) 对齐，0 冲突。

**默认不做的事：不把「导线端点落在另一根导线中间」当成连接。**
EasyEDA 自己的网表也不这么算。证据（Candis `Power` 页）：一根无标签导线从
`(1105, -605)` 拉到 `(910, -605)`，端点落在 `TG28_DCDC1` 线段 `(905,-605)-(945,-605)`
内部，而那根导线的另一头是一个 `GND` 标志；如果按 T 形连接处理，`GND` 会和
`VCC_3V3_MAIN` 短在一起，但 PCB 网表里两者是分开的（GND 185 个焊盘、
VCC_3V3_MAIN 49 个焊盘）。关灯神器开关 T 形规则结果完全不变。

引脚落在导线**内部**仍然算连接（引脚本来就是任意点接触导线）。

## 5. PCB 侧

PCB 网表不需要重建：

- 元件焊盘的网名 = `PAD_NET` 的 payload `padNet`。复合 id 的第 4 段是封装里
  `PAD` 记录的 header id，**不要拿焊盘号去猜**（有 `A1B12` 这种复合焊盘号）。
- 独立焊盘（不属于任何元件）用 `PAD.netName`，不进 `PAD_NET`。关灯神器有 1 个
  这样的焊盘（60 mil 圆盘、36 mil 孔、网名 `AGND`）。
- `PAD_NET` 可能出现空 `padNet`（焊盘未连接），这时 `net` 为 `null`。
- 走线、过孔、铺铜都带 `netName`；板框是 OUTLINE 层（layerId 11）的 `POLY`。
- 有些元件的实例 `Footprint` 为空，封装只写在 `DEVICE.attributes.Footprint`。
  关灯神器的 `SCREW6`（M2 螺丝）就是这种；不回退就会漏掉它的 1 个焊盘。

## 6. 对比与告警怎么读

`netlist.json.comparison` 只对「主 PCB」（元件最多的那块）做逐引脚对比：

| 字段 | 含义 |
|---|---|
| `pins_compared` | 两边都有 (位号, 引脚号) 的引脚数 |
| `match` | PCB 网名出现在原理图该引脚的别名里 |
| `mismatch` | 两边都是设计者命名的网，但名字不同 |
| `both_auto_named` | 两边都是 `$LOCAL…` / `$1N…` 自动编号（不比较名字） |
| `schematic_named_only` / `pcb_named_only` | 只有一侧有命名 |
| `only_in_schematic` / `only_in_pcb` | 该侧没有对应焊盘/引脚 |
| `net_mismatches` | 同名网在两边的成员集合差异 |
| `only_designators_*` | 只在原理图 / 只在 PCB 的位号 |

自动编号一律按「未命名」处理：`$LOCAL12` 与 `$1N6` 只是两个工具各自起的名字，
不代表设计意图。网络标志不是元件，不计入引脚数和成员集合。

### 6.1 用 EasyEDA 自带网表交叉验证（强证据）

如果手上有工程时能出网表，这是校验几何重建的最强证据：让 EasyEDA 自己算一遍
原理图网表，再和 `netlist.json` 逐引脚对比。

导出：EasyEDA 专业版 →「设计 / 制造 → 导出 → 网表」，选 **Protel 2.0**。
文件里先是若干 `[ … ]` 元件段，再是 `( 网名 … )` 网络段，成员行形如
`U1-5 TP4056X-435-ESOP8-BAT Passive`（位号-引脚号，后面是型号-引脚名和类型）。

```bash
python src/validate_netlist.py <netlist.json> <EasyEDA导出的.net>
```

两个样本的历史结果（旧校验器；未用新版重跑）：

| 工程 | 共有引脚 | 同名 | 两侧自动编号 | 不同 |
|---|---|---|---|---|
| 关灯神器 | 108 | 66 | 42 | **0** |
| Candis | 901 | 767 | 134 | **0** |

上表只说明名称差异；新版校验器还会比较共有引脚的成员分组，且 `only_ours` 仍需解释。

对照时有三点语义差异，不是错误：

- **未连接的引脚不会出现在 EasyEDA 网表里**（关灯神器的 `SG90?1` 三个脚、
  `SW1.1`；我们的输出保留这些脚，所以「只在我们」比对方多）。
- **`Convert to PCB: no` 的元件整个不出现**（Candis 的 `C36`，见 §7）。
- **网名优先级是「网络标志 > 导线标签」**。Candis 里 `GND` 标志压过 `CAM_AF_GND`
  导线标签、`VCC_3V3_MAIN` 标志压过 `TG28_DCDC1` 标签；`extract.py` 已按此取名。

## 7. 实测发现（样本专属，供审核参考）

以下都是**待人工核对**的候选，不是已确认的设计错误。

1. **Candis / FPC1：原理图引脚号与 PCB 焊盘号完全反序。**
   22 个可比引脚全部满足 `pcb_pad = 25 − sch_pin`（例如 SCH `CAM_D0` 在 pin 19，
   PCB 在 pad 6；SCH `CAM_D7` 在 pin 12，PCB 在 pad 13）。可能是封装焊盘编号方向
   与符号相反，也可能是连接器实际接触顺序问题。需要对照 FPC 座子图纸确认。
2. **Candis / C36：只在原理图，PCB 里没有这个元件。**
   元件属性 `Convert to PCB: no`、`Add into BOM: no`，是有意排除的，
   不是漏画。EasyEDA 自带网表同样不含它。**核对结论：符合设计意图。**
3. **关灯神器 / SW1 pin 1：PCB 焊盘 `padNet` 为空**（未连接）。
4. **关灯神器 / SG90?1：3 个引脚没有落在任何导线上**（原理图里悬空），
   其 PCB 封装也是 0 焊盘的派生封装。
5. **关灯神器 / GND 与 AGND**：原理图用短接符号把两个网连起来，PCB 统一叫 `AGND`。
   不是命名错误。

## 8. 已知限制 / 待验证

- 只在 2 个工程、editor 3.2.186 上验证过。3.2.91 / 3.2.149 只验证了日志层能严格解析，
  没验证连接规则。**其他版本待验证。**
- 导线端点落在另一根导线内部的「隐式 T 连接」默认不算连接（依据见 §4）。
  用 EasyEDA 自带网表复核后，两个样本都是 0 差异，说明这两个工程确实不补
  junction。**其他工程/版本是否会自动补，待验证。**
- 短接标识的语义（两引脚同网）在 Candis 上由 EasyEDA 自带网表直接证实
  （56 个短接符号合并后，901 个共有引脚 0 冲突）；关灯神器由 PCB 网表交叉证实。
  **其他器件变体待验证。**
- 镜像语义（§3）只在 2 个工程上验证；PCB 的结论基于底元件焊盘与同网走线的
  几何吻合度，不是网表级的证明。**换封装库时需复核。**
- EasyEDA 自带网表是很好的交叉验证源，但它**不导出未连接引脚、不导出
  `Convert to PCB: no` 的元件**，也不能替代 `extract.py` 给出的坐标与几何。
- 总线（bus）、线束（harness）、层次原理图页符号未做特殊处理。两个样本都是
  扁平多页 + 跨页网名。**层次设计待验证。**
- `POURED` 默认不导出；需要铺铜实际填充多边形时加 `--with-poured`。
- 板框只取 OUTLINE 层的 `POLY`；`board_size` 是板框顶点的包围盒，
  不是精确面积（圆弧按端点计，对凸圆角足够，对内凹圆弧会偏大）。
  `path` 里 `R`/`L`/`ARC` 的坐标语义已按 2026-11-08 的三块实测板核对：
  `R` 为 `x,y,w,h,rot,round`，板框是 `x..x+w`、`y-h..y`；
  `ARC` 为 `角度,x,y`（端点在最后两个数），`L` 为 `x,y`，也允许裸坐标对。
  旧版把命令串过滤后两两配对，会把 ARC 角度当成坐标——已修。
- 多 PCB 工程只对比元件最多的那块；其余 PCB 的网表仍会完整输出。
- 原理图网表的网名键优先级：网络标志名 > 导线标签名（同类按字典序）；一个网可能
  有多个别名（如 `GND`/`AGND`），`aliases` 里都保留。两个网络标志碰在同一个网上时
  （关灯神器 `AGND` + `GND`），取字典序第一个 `AGND`，与 EasyEDA 导出一致；
  标志之间的确切优先级**待验证**。

## 9. 快速查数

```bash
# 某元件每个脚落在哪个网
python -B - <<'PY'
import json
import sys
sys.path.insert(0, 'src')
from output_paths import generated_path
d=json.load(open(generated_path('outputs', 'extract', '工程名', 'netlist.json'),encoding='utf-8'))
for r in d['schematic']['pins']:
    if r['designator']=='U1':
        print(r['pin'], r['pin_name'], r['net'])
PY
```

`pcb.json` 里每个焊盘带绝对坐标和网名，可以直接和走线端点做几何核对；
`schematic.json` 里每根导线是折线点列，可以直接画图。
