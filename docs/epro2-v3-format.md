# 嘉立创EDA `.epro2`（V3）文件结构调研

**日期**：2026-11-06 　**项目**：`projects/epro2-辅助绘制及审核`
**样本**：本机 8 个真实导出包（editor 3.2.91 / 3.2.149 / 3.2.186），路径见文末。
**官方资料**：`C:\Users\18640\.claude\skills\easyeda-api-skill\format\`（对应立创 V3 规范 2025-10-21 版，`format/index.md` 为入口）。

## 结论

1. **`.epro2` 是 ZIP**，只有三样东西：`project2.json`（工程元数据）+ 一个 `<工程名>.epru`（全部设计数据）+ `IMAGE/<文档uuid>.webp`（各文档缩略图）。8/8 样本一致。
2. **`.epru` 是逐行日志**：UTF-8 无 BOM、LF 换行，每行一条记录，形如 `<HEADER>||<PAYLOAD>|`。`HEADER` 是 `{type, id?, ticket}`，`PAYLOAD` 是原子数据，**可以为空**。文件最后一条记录**没有行尾 `|`**（8/8 样本一致）。
3. **文档用 `DOCHEAD` 分节**，`HEADER` 之后的记录都属于该文档，直到下一个 `DOCHEAD`。样本见过 12 种文档类型：`BOARD / SCH / SCH_PAGE / PCB / PANEL / SYMBOL / FOOTPRINT / DEVICE / CONFIG / FONT / BLOB / SIMULATION`。
4. **层级**：`BOARD → SCH → SCH_PAGE`；`BOARD → PCB`。PCB 的 `board` 为空时是独立/子 PCB。连接靠 META 里的 uuid 字段，不靠目录结构。
5. **元件-符号-封装靠 uuid 串起来**：`SCH_PAGE` 的 `COMPONENT.partId` 指向 `SYMBOL` 文档里 `PART` 记录的 header `id`；同一个 COMPONENT 的子 `ATTR` 用 `key="Symbol"/"Device"/"Footprint"/"Designator"` 分别指向 SYMBOL / DEVICE / FOOTPRINT 文档 uuid 和位号。PCB 侧同理，`PAD_NET` 给出每个焊盘的网络名。
6. **单位不是一套**：原理图（`SCH_PAGE` / `SYMBOL`）1 单位 = 0.01 in；PCB（`PCB` / `FOOTPRINT`）1 单位 = 1 mil = 0.001 in。**官方 V3 文档写"所有坐标 0.01 in"，与 PCB 实测不符**，见第 6 节证据。
7. 与 V2.2 `.epro` 的根本差别：V2.2 是"索引 + 每个文档一个文件"（`project.json` + `SYMBOL/*.esym` + `FOOTPRINT/*.efoo` + `SHEET/*.esch` + `PCB/*.epcb`）；V3 把**所有文档压进单一 `.epru` 日志流**，`project2.json` 只剩工程封面/简介。
8. 官方规范与实测有若干字段级差异（第 7 节）。**解析时以实测为准**，官方文档当语义参考。

---

## 1. 容器层（ZIP）

以《关灯神器》为例：

```
ProPrj_【DIY电子】关灯神器_2026-09-12.epro2   (1,160,189 B)
├─ project2.json                         110,578 B   工程元数据
├─ 【DIY电子】关灯神器.epru             2,459,470 B   全部设计文档
└─ IMAGE/
   ├─ 3fe356f78e46de5a.webp
   ├─ 45f3ad0b16e8590b.webp
   ├─ 4b1ea0f7c93aeaa2.webp     ← 与 PCB 文档 uuid 同名
   ├─ 83d2b88012fededb.webp
   ├─ 88f0ab9d851a99b7.webp     ← 与 PCB 文档 uuid 同名
   ├─ c86f9ca724c7304f.webp
   └─ d0aa78fac04c11a0.webp     ← 与 SCH_PAGE 文档 uuid 同名
```

### 1.1 `project2.json`

只有 6 个键，**不含文档清单**：

| 键 | 类型 | 说明 | 示例 |
|---|---|---|---|
| `title` | string | 工程名，与 `.epru` 文件名相同 | `【DIY电子】关灯神器` |
| `cbb_project` | bool | 是否 CBB 工程 | `false` |
| `editorVersion` | string | 导出时的编辑器版本 | `3.2.186` |
| `introduction` | string | 工程简介（纯文本） | `基于 Chipintelli CI13161…` |
| `description` | string | 工程详情（HTML，含外链图片） | `<div style=…>` |
| `tags` | string | 标签，**是 JSON 数组的字符串** | `"[]"` |

> 文档清单不在 `project2.json`，只能从 `.epru` 的 `DOCHEAD` 重建。这一点和 V2.2 的 `project.json`（含 boards/devices/symbols/footprints… 全量索引）完全不同。

### 1.2 `IMAGE/<uuid>.webp`

按文档 uuid 命名的缩略图。8 个样本合计 53 张，其中 49 张能在 `.epru` 里找到同名 `DOCHEAD uuid`；《关灯神器》有 4 张是**已删除文档留下的过期缩略图**（uuid 在 `.epru` 中不存在）。做解析时不要依赖它。

---

## 2. 日志层（`.epru`）

### 2.1 字节与行约定

| 项 | 实测 |
|---|---|
| 编码 | UTF-8，无 BOM（8/8） |
| 换行 | 仅 LF，无 CRLF（8/8） |
| 记录分隔 | 逐行；行内先 `HEADER`，再 `||`，再可选 `PAYLOAD`，行尾 `|` |
| 最后一条 | **没有行尾 `|`**，直接以 payload 的 `}`/`]` 结束 |
| 行内 `||` | 每行恰好 1 个；8 个样本中没有 payload 字符串内含 `||` |
| 空 payload | 写成 `HEADER|||`（两个分隔符紧挨，第 3 个 `|` 是行尾） |

### 2.2 记录语法

```
记录   := HEADER '||' PAYLOAD? '|'
HEADER := {"type": string, "id"?: string, "ticket": number, "firstTicket"?: number}
```

三种实际形态：

```json
{"type":"DOCHEAD","ticket":28337}||{"docType":"FOOTPRINT","client":"310b4756…","uuid":"88f0ab9d…","updateTime":1787312893613,"version":"1787312893613","editVersion":"3.2.175","user":{…}}|
{"type":"ATTR","ticket":1,"id":"e63970cf07d35e0c2"}||{"groupID":0,"parentId":"","layerId":3,"x":null,"y":null,"key":"Footprint","value":"SG90舵机",…}|
{"type":"NET","ticket":130,"id":"[\"NET\",\"\"]"}|||
```

### 2.3 `HEADER` 字段

| 字段 | 含义 | 备注 |
|---|---|---|
| `type` | 记录类型 | 有 46 种（样本《关灯神器》统计） |
| `id` | 文档内唯一 id | 单例记录也写成 `"id":"META"`；只有 `DOCHEAD` 没有 `id`（8/8 样本） |
| `ticket` | 逻辑时钟，最终一致性用 | 导出包中不连续、普遍很大 |
| `firstTicket` | 该图元首次创建时的 ticket | **官方文档未提**，实测存在；推测用于区分"创建/修改"顺序（待验证） |

**复合 id 是"字符串里再套 JSON 数组"**，例如：

```json
"id": "[\"PAD_NET\",\"24473a734f619627\",\"1\",\"e13\"]"
"id": "[\"LAYER\",1]"
"id": "[\"RULE\",\"SAFE\",\"copperThickness1oz\"]"
```

解析时对 `id` 再做一次 `json.loads` 才能拆成结构化字段。

### 2.4 最终一致性与删除

官方规范（`format/index.md`）：

- 同一 `(type, id)` 出现多条时，保留 `ticket` 最大的一条。
- `ticket` 相同则比较 `DOCHEAD` 的 `client`，保留 client 较小的一侧。
- 原子数据删除 = payload 写成空字符串 `""`；文档删除 = `{"type":"DELETE_DOC","ticket":n}||{"isDelete":true}|`。

实测：

- 8/8 样本**没有重复的 `(文档, type, id)`** —— 导出包已经压实成快照，不是原始增量日志。
- 但《Candis-ESP32S31》里仍有 `DELETE_DOC` ×2、`META_MODIFY` ×1、`META_PLACEHOLDER` ×4。说明压实不等于清空删除标记。
- 样本中**没有看到** payload 为 `""` 的删除记录。

> 结论：读取导出包可以"取到最后一条就算数"，但为了兼容未压实日志，仍建议按 ticket 取最大值，并过滤 `DELETE_DOC` 覆盖的文档。

### 2.5 特殊记录

| type | 作用（实测） |
|---|---|
| `ELE_PLACEHOLDER` | 编辑器内部占位，payload 如 `{"dataType":"COMPONENT","max":9}`；不参与电气语义 |
| `META_PLACEHOLDER` | 同上，`dataType="META_PLACEHOLDER"`，id 形如 `<docuuid>_<hash>` |
| `GROUP` | 分组名/父子关系；`id` 是组号，payload 可为空 |
| `DELETE_DOC` | 文档删除标记 |
| `META_MODIFY` | 文档修改时间 |

这些对"看图/审图"没有直接价值，解析时可以跳过，但**不要当成错误丢弃**。

---

## 3. 文档类型与层级

### 3.1 样本统计

| docType | 关灯神器 | Candis-ESP32S31 | 文档作用 | 主要记录 |
|---|---:|---:|---|---|
| `BOARD` | 1 | 1 | 板级容器 | `META` |
| `SCH` | 1 | 1 | 原理图（多页的父级） | `META`、`RULE` |
| `SCH_PAGE` | 1 | 11 | 原理图页 | `COMPONENT`、`WIRE`、`LINE`、`ATTR`、`TEXT`、`RECT`、`OBJ` |
| `PCB` | 2 | 1 | PCB | `COMPONENT`、`PAD_NET`、`LINE`、`VIA`、`POLY`、`FILL`、`POUR`、`RULE`、`LAYER`… |
| `PANEL` | 1 | 0 | 拼板 | `META` |
| `SYMBOL` | 41 | 78 | 符号库（含 `PART`/`PIN`） | `PART`、`PIN`、`ATTR`、`POLY`、`RECT`、`CIRCLE`、`ARC` |
| `FOOTPRINT` | 35 | 50 | 封装库（含 `PAD`） | `PAD`、`LINE`、`POLY`、`FILL`、`PRIMITIVE`、`LAYER` |
| `DEVICE` | 42 | 75 | 器件（符号+封装的绑定） | `META`（仅一条） |
| `CONFIG` | 1 | 1 | 工程配置 | `UNIVERSAL`、`META` |
| `FONT` | 1 | 1 | 矢量字体轮廓 | `FONT` |
| `BLOB` | 1 | 1 | 嵌入式图片/SVG（base64） | `BLOB` |
| `SIMULATION` | 0 | 0 | 仿真页（本表两样本为 3.2.186；4 个 3.2.91 样本各 1 个） | `META`、`ATTR`… |

> `SIMULATION`、`FONT` 不在官方 V3 文档的 docType 列表里；`CONFIG` 官方写作 `PROJECT_CONFIG`；官方列的 `INSTANCE` 在 8 个样本中均未出现（样本里 `Reuse Block` / `Group ID` / `Channel ID` 三个属性全部为空值，没有实际的复用块实例）。这些差异集中在第 7 节。

### 3.2 层级与引用

```
BOARD 12404fb4…
├─ SCH 74b4426b…          META.board = BOARD.uuid
│  └─ SCH_PAGE d0aa78fa…   META.schematic = SCH.uuid
└─ PCB 88f0ab9d…          META.board = BOARD.uuid
   └─ (子 PCB / 独立 PCB) META.board = ""，META.parent = 父 PCB uuid

DEVICE 133c0a46…           META.attributes.Symbol    = SYMBOL.uuid
                          META.attributes.Footprint = FOOTPRINT.uuid
```

《关灯神器》里第二块 PCB `4b1ea0f7…` 的 `META` 是：

```json
{"title":"舵机臂","parent":"","source":"","board":"","zIndex":null}
```

即独立 PCB（不属于任何 BOARD），不是板子的第二块 PCB。

### 3.3 元件 → 符号/封装/器件/位号

`SCH_PAGE` 中一个真实元件（BAT1）的记录关系：

```json
{"type":"COMPONENT","id":"d29702e2eeed7530"}||{"partId":"C9900000450.1","x":765,"y":-715,"rotation":0,"isMirror":false,"attrs":{},"zIndex":1}|
{"type":"ATTR","id":"…","parentId":"d29702e2eeed7530"}||{…,"key":"Symbol","value":"d2c87914afd50a0b"}
{"type":"ATTR","id":"…","parentId":"d29702e2eeed7530"}||{…,"key":"Device","value":"133c0a469aa1b004"}
{"type":"ATTR","id":"…","parentId":"d29702e2eeed7530"}||{…,"key":"Footprint","value":null}
{"type":"ATTR","id":"…","parentId":"d29702e2eeed7530"}||{…,"key":"Designator","value":"BAT1"}
```

链路：

```
COMPONENT.partId  == SYMBOL 文档内 PART.id          ← 子库/多 Part 符号的选择器
ATTR(parentId=COMPONENT.id, key="Symbol")      → SYMBOL 文档 uuid
ATTR(parentId=COMPONENT.id, key="Device")      → DEVICE 文档 uuid
ATTR(parentId=COMPONENT.id, key="Footprint")   → FOOTPRINT 文档 uuid（可为 null）
ATTR(parentId=COMPONENT.id, key="Designator")  → 位号
```

`DEVICE` 文档只有一条 `META`，内容是属性表：

```json
{"title":"1节5号电池座带焊针","attributes":{"Symbol":"d2c87914afd50a0b","Footprint":"fdc3872fe6c9542c","Supplier Part":"C9900000450",…}}
```

### 3.4 符号引脚

`SYMBOL` 文档里：

- `PART`：**header 的 `id`** 就是 `COMPONENT.partId`（例 `"C9900000450.1"`；payload 里没有 `id` 字段），payload 带 `BBOX`、`title`。
- `PIN`：`id` 是引脚图元 id；payload 带 `partId`、`x/y`、`length`、`rotation`、`pinShape`。
- 引脚名/号/电气类型不在 `PIN.payload`，而是三条子 `ATTR`：

```
ATTR(parentId=PIN.id, key="Pin Name")   = "Pin1"
ATTR(parentId=PIN.id, key="Pin Number") = "2"
ATTR(parentId=PIN.id, key="Pin Type")   = "IN"
```

样本 `Short-Symbol` 的 `PIN` 有 `x=10,y=0,length=5,rotation=180`；`Pin Number=2`。

### 3.5 PCB 侧：元件、焊盘和网络

`PCB` 文档中：

- `COMPONENT`：`id`、`layerId`、`x/y`、`angle`、`attrs{}`。Designator / Footprint / Device 同样是子 `ATTR`。
- `FOOTPRINT` 文档里的 `PAD` 定义焊盘几何：`num`（焊盘号）、`centerX/centerY`、`defaultPad{}`、`hole{}`、`layerId` 等。
- `PAD_NET` 把实例焊盘绑到网络：

```json
{"type":"PAD_NET","id":"[\"PAD_NET\",\"24473a734f619627\",\"1\",\"e13\"]","ticket":26424}||{"partitionId":"","padNet":"BAT_IN","padLen":null,"attrsMap":{}}
```

id 四元组：`[ "PAD_NET", 元件实例id, 焊盘号, 封装内焊盘图元id ]`。

**实测完备性**（《关灯神器》PCB1_1）：

| 项 | 数值 |
|---|---:|
| `COMPONENT` 数 | 39 |
| 有非空 `Footprint` 属性的元件 | 38（其中 `SG90?1` 指向一个 0 焊盘的派生封装） |
| 这 37 个有焊盘元件按实例计的 `PAD` 总数 | 108 |
| `Footprint` 属性为空、但 DEVICE 仍绑定了 1 焊盘封装的元件 | 1（`SCREW6`，M2 螺丝） |
| `PAD_NET` 总记录 | 418 |
| `PAD_NET` 有 payload 的 | 109 = 108 + 1 |
| `PAD_NET` 无 payload 的 | 309（非焊盘图元的占位行） |
| PCB 文档内的独立 `PAD` 记录 | 1（自带 `netName:"AGND"`，**不**参与 `PAD_NET`） |

即：**焊盘级网络名是完整的，但必须只取 payload 非空、且 id 第二段是元件 id 的行**。418 条里另外 309 条是编辑器为其他图元生成的空壳，不是数据丢失。

注意两类焊盘的取值路径不同：
- 元件焊盘 → `PAD_NET.payload.padNet`（焊盘几何在 `FOOTPRINT` 文档里，按 `PAD.num` 对应）。
- 独立焊盘（不属于任何 `COMPONENT`）→ 直接读 `PAD.payload.netName`，它没有 `PAD_NET` 行。

### 3.6 原理图网络

原理图**没有**现成的 netlist 记录。网络名靠两类信息：

1. `WIRE` 的子 `ATTR(key="NET", value="VDD_5V")`。空字符串表示未命名局部网。
2. 网络标志（电源/GND 符号）是一个 `COMPONENT`，其子 `ATTR(key="Global Net Name", value="GND")` 给出全局网名；对应 SYMBOL 的 `META.docType` 是 18（NetFlag）。

《关灯神器》P1 页：72 条 `WIRE`，其中 50 条 `NET` 值为空、22 条有名字（`VDD_5V`、`HPOUT_L`、`MICP`/`MICN`、`UART0_TX` 等）。

线的几何不在 `WIRE.payload`（只有一个 `zIndex`），而在 `WIRE` 的子 `LINE`：

```json
{"type":"LINE","id":"e1af5b4c…","firstTicket":911}||{"startX":575,"startY":-490,"endX":575,"endY":-485,"lineGroup":"90c18f7d4bf345ac",…}
```

`LINE.lineGroup` = 所属 `WIRE.id`。**要重建原理图连通性，必须做"引脚坐标 ↔ 线端点"的几何匹配，再沿 WIRE 传播网名/全局网名。** 这是后续审核工具的主要工作量。

### 3.7 连接性重建的实测规则

用 PCB 的 `PAD_NET` 网表做交叉验证（详见 `docs/extraction-guide.md` §4）：

1. **短接标识要合并。** `DEVICE.tags` 含 `短接标识`（title 多为 `Short-Symbol`）的元件，
   两个引脚属于同一个网。关灯神器里它连着 `GND` 与 `AGND`，PCB 侧确实只有一个 `AGND` 网。
2. **导线端点落在另一根导线中间，不算连接。** Candis `Power` 页一根无标签导线端点
   落在 `TG28_DCDC1` 线段内部，另一端是 `GND` 标志；若按 T 形连接处理会把 `GND` 与
   `VCC_3V3_MAIN` 短在一起，但 PCB 网表里两者是分开的（185 vs 49 个焊盘）。
3. **封装可能只写在 DEVICE 上。** 实例 `ATTR.Footprint` 为空时，回落到
   `DEVICE.META.attributes.Footprint`（如 M2 螺丝 `SCREW6`），否则会漏焊盘。
4. **镜像语义随文档类型不同。** 原理图的 `isMirror` 是「先旋转、再按文档竖直轴
   翻转」：`X = cx − (x·cosθ + y·sinθ)`，Y 不变；PCB 底层（`layerId == 2`）是
   「局部 x 取反后再旋转」。用错会把镜像元件的引脚号/焊盘号对错——
   Candis 用局部取反式时 Q5/C61/C102/C120 出现 8 个假冲突。

---

## 4. 记录类型速查（样本实测）

### 4.1 文档级

| type | 所在文档 | 说明 |
|---|---|---|
| `DOCHEAD` | 全部 | 文档头，payload = `{docType, uuid, client, updateTime, version, editVersion, user}` |
| `META` | 全部 | 文档元数据（标题、引用、排序等） |
| `CANVAS` | SYMBOL/PCB/FOOTPRINT | 画布原点、栅格、显示单位（`unit:"mm"` 是**显示单位**，不是存储单位；`SCH_PAGE` 没有 `CANVAS`，`SYMBOL` 的只有 `originX/originY`） |
| `ACTIVE_LAYER` | PCB/FOOTPRINT | 当前层 |
| `LAYER` / `LAYER_PHYS` | PCB/FOOTPRINT | 层定义 / 物理叠层 |
| `RULE` / `RULE_TEMPLATE` / `RULE_SELECTOR` | PCB/FOOTPRINT/SCH | 设计规则；`ruleContext.unit` 显式给出规则值的单位（样本中 `mm` 91 条、`mil` 21 条、无单位 18 条） |
| `PREFERENCE` | PCB/FOOTPRINT | 走线/过孔默认参数 |
| `SILK_OPTS` / `PRIMITIVE` | PCB/FOOTPRINT | 丝印配色 / 图元显示开关 |
| `PANELIZE` | PCB/FOOTPRINT | 拼板参数 |
| `UNIVERSAL` | CONFIG | 工程级开关（默认网名、总线生成网类等） |

### 4.2 图元级

| type | 说明 |
|---|---|
| `COMPONENT` | 原理图元件实例 / PCB 封装实例 |
| `ATTR` | 键值属性；靠 `parentId` 挂在元件、引脚、线、焊盘上 |
| `PIN` | 符号引脚 |
| `PART` | 符号子库（多 Part 符号的每个 Part） |
| `WIRE` | 原理图导线容器；几何在子 `LINE` |
| `LINE` | 线段（原理图线、PCB 走线、封装轮廓都用它） |
| `PAD` | 焊盘 |
| `PAD_NET` | 焊盘-网络映射（含空壳占位行） |
| `VIA` | 过孔 |
| `POLY` | 折线/多边形（PCB 铜皮、封装轮廓） |
| `FILL` / `POUR` / `POURED` | 填充 / 铺铜定义 / 铺铜计算结果 |
| `TEARDROP` | 泪滴 |
| `REGION` | 禁布区/约束区（`regionType: PROHIBIT / CONSTRAINT`） |
| `STRING` / `TEXT` | PCB 文字 / 原理图文字 |
| `RECT` / `CIRCLE` / `ELLIPSE` / `ARC` | 图形 |
| `OBJ` / `IMAGE` / `BLOB` | 嵌入对象/图片；`BLOB.content` 是 `data:image/...;base64,...` |
| `SHELL` / `SHELL_ENTITY` / `CREASE` / `BOSS` | 3D 外壳 |
| `DIMENSION` | 尺寸标注；payload 带 `unit:"mil"`，可反推 PCB 存储单位 |
| `FONT` | 矢量字形轮廓 |
| `TABLE` | 表格：`startX/startY`、`rowSizes/colSizes`、单元格内容 |

> 完整类型计数（《关灯神器》，7265 条）：`ATTR 1695, LAYER 1449, ELE_PLACEHOLDER 652, PAD_NET 418, FILL 351, PRIMITIVE 327, LINE 327, POLY 290, PIN 196, PAD 180, VIA 132, RULE 130, DOCHEAD 127, META 125, COMPONENT 112, TEARDROP 100, RULE_SELECTOR 83, CANVAS 78, WIRE 72, NET 64, LAYER_PHYS 63, PART 41, …`（其余 <40 条的类型见 `src/epru_reader.py` 输出）。

---

## 5. 官方 V3 规范与实测的差异

| 项 | 官方 V3 规范 | 实测（8 样本） | 处理建议 |
|---|---|---|---|
| 工程配置 docType | `PROJECT_CONFIG` | `CONFIG` | 以实测为准 |
| 工程配置 META 键 | `default_sheet` | `defaultSheet`（样本里没有 `title`/`name`） | camelCase |
| 文档元数据键 | `name`、`sort` | `title`、`zIndex` | 以实测为准 |
| 元件坐标键 | `positionX`、`positionY` | `x`、`y` | 以实测为准 |
| 属性坐标键 | `positionX`、`positionY` | `x`、`y` | 以实测为准 |
| `WIRE` 几何 | payload 内 `dots:[[x1,y1,x2,y2,…]]` | `WIRE` 仅 `{zIndex}`，几何在子 `LINE`（`lineGroup`） | 以实测为准 |
| `PAD_NET` | `id` = 元件 uuid；payload `{padNum,padNet,padId}` | `id` = `["PAD_NET",元件id,焊盘号,焊盘图元id]` 的字符串；payload 无 padNum/padId | 以实测为准 |
| `BLOB` | `type:"META"`，payload `{filename,data}` | `type:"BLOB"`，payload `{filename,content}` | 以实测为准 |
| 坐标单位 | 所有坐标/长度 0.01 in | 原理图 0.01 in；PCB/封装 0.001 in | **按文档类型分开**，见第 6 节 |
| 文档类型表 | 无 `FONT`、无 `SIMULATION` | 两者都有 | 未知类型按"可跳过"处理 |
| `INSTANCE` / `COMPONENT_GROUP` / `VARIANT` | 有 | 8 样本均无 | 待验证（疑与变体/复用块有关） |
| `firstTicket` | 未提 | 常见 | 待验证 |
| 单例记录 `id` | 可省略 | 只有 `DOCHEAD` 省略；`META` 等写成 `id:"META"` | 做兼容 |

> 这些差异不影响"读得出来"，但**照官方字段名硬编码会读空**。本项目一律以真实样本回归。

---

## 6. 单位与坐标

### 6.1 原理图侧：1 单位 = 0.01 in（10 mil）

证据：

- 《关灯神器》标题栏 `ATTR`：`Width=1170`、`Height=825`。A4 横向 297×210 mm = 11.69×8.27 in，按 0.01 in/单位即 1169×827，与 1170×825 只差舍入。
- `SYMBOL` 引脚 `length=5`，按 0.01 in 是 1.27 mm；常见的 2.54 mm 引脚常写成 10。

> **别用 `CANVAS` 反推存储单位。** `CANVAS.unit` 是**显示单位**，`gridXSize/snapXSize` 也是按显示单位写的值（样本里多为 `unit:"mm"`、`gridXSize=5`，即 5 mm 显示栅格）。`SYMBOL` 的 `CANVAS` 只有一个 `{originX, originY}`，`SCH_PAGE` 干脆没有 `CANVAS` 记录。

### 6.2 PCB / 封装侧：1 单位 = 1 mil（0.001 in）

证据：

- `DIMENSION` payload 显式写了 `"unit":"mil"`，坐标 `coords:[550,1265,…]`。
- 2.54 mm 排针封装的 3 个焊盘：`centerX = -100 / 0 / +100`，间距 100 单位 = 100 mil = 2.54 mm；焊盘宽 66.929 单位 = 1.70 mm。
- 过孔 `holeDiameter=12.0078`、`viaDiameter=24.0158` → 0.305 mm / 0.61 mm，典型工艺值；若按 0.01 in 会变成 3.05 mm / 6.10 mm，不合理。
- PCB 走线宽度 `width=10` → 10 mil = 0.254 mm；规则模板的间距值 6/10/11.8 → 0.15/0.25/0.30 mm，符合嘉立创工艺。
- PCB 整体包围盒约 2748 × 2605 单位 → 69.8 × 66.2 mm，符合《关灯神器》的实际板尺寸。
- 3.2.91 老样本同样成立：过孔 `holeDiameter=12`、`viaDiameter=24` → 0.305/0.610 mm；某封装两焊盘 `centerX = ±58.76`，间距 117.5 单位 = 2.99 mm（按 0.01 in 则是 29.9 mm，不可能）。

### 6.3 设计规则另有一套单位

`RULE.payload.ruleContext` **自带单位**，规则内容（间距、线宽、孔径）必须按该字段解读，**不要**套用坐标单位。《关灯神器》统计：`unit="mm"` 91 条、`"mil"` 21 条、无单位 18 条（无单位的多为非长度类规则，如盲埋孔、自动布线）。

---

## 7. 与 V2.2 `.epro` 的对比

以 `ProPrj_USB程序拓展坞_2026-08-13.epro` 为 V2.2 样本：

```
ProPrj_USB程序拓展坞_2026-08-13.epro        (163,119 B, ZIP)
├─ project.json                 80,572 B   全量索引：
│                                           config / boards / devices / symbols /
│                                           footprints / schematics / pcbs / panels
├─ SYMBOL/*.esym                38 个     每个符号一个文件
├─ FOOTPRINT/*.efoo             23 个     每个封装一个文件
├─ SHEET/<schematic-uuid>/1.esch          每个原理图页一个文件
├─ PCB/<pcb-uuid>.epcb                    每个 PCB 一个文件
├─ BLOB/*.eblob                           嵌入二进制
├─ INSTANCE/  POUR/  PANEL/  FONT/        空目录在导出保留
```

| 维度 | V2.2 `.epro` | V3 `.epro2` |
|---|---|---|
| 容器 | ZIP + 多文件 | ZIP + 单一日志流 |
| 工程索引 | `project.json`，全量 | `project2.json`，仅封面/简介 |
| 文档存储 | 每文档一个 `.esym/.efoo/.esch/.epcb` | 全部塞进一个 `.epru` |
| 内部组织 | 数组下标 + 行式/紧凑 JSON | key-value + `type/id/ticket` 日志 |
| 增量语义 | 无（快照） | 最终一致性日志（导出时压实） |
| 现有工具支持 | `netlist-adapter` 的 `ezplm` 支持 | **不支持**（`Container.classify()` 会明确拒绝，报"V3 分享包"） |

> 因此本项目的 `.epro2` 解析必须另起一层；不能复用 `.efoo`/`.epcb` 的“按下标取字段”逻辑。

---

## 8. 解析注意事项（踩坑清单）

1. **最后一行没有 `|`**。按“有则跳、无则 EOF 即结束”处理；否则 8/8 样本都会报 1 条错。
2. **空 payload 是合法状态**，写成 `HEADER|||`。不要当成解析失败。`NET`、`RULE_SELECTOR`、`LINE`、`GROUP` 都有大量空 payload。
3. **`id` 可能不存在**（`DOCHEAD`），也可能**是 JSON 数组的字符串**（`PAD_NET/LAYER/RULE/POURED/PRIMITIVE/NET/RULE_SELECTOR`）。要二次 `json.loads`。
4. **不要用固定下标取字段**。官方文档已经和实测差了好几处（第 5 节），必须按 key 取。
5. **不要在 payload 上做 `split('||')`**。样本里恰好每行一个 `||`，但这是实现巧合；用 `JSONDecoder.raw_decode` 从外层往后吃，才不会将来被字符串里的 `||` 破坏。
6. **不要依赖 `IMAGE/` 缩略图判断文档是否存在**。存在过期缩略图。
7. **`project2.json` 的 `tags` 是字符串**（内容为 JSON 数组），不是数组。
8. **同一文档内 `type+id` 可能重复**（未压实日志）。按 `ticket` 取最大，`ticket` 相同比 `client`。
9. **文档归属靠 `DOCHEAD` 顺序**，不靠 `id` 前缀。一个 `.epru` 里可以有多个同类型文档（如 2 个 PCB、11 个 SCH_PAGE）。
10. **`ELE_PLACEHOLDER` / `META_PLACEHOLDER` 不是数据丢失**。它们是编辑器预分配槽位，跳过即可。

---

## 9. 对本项目（辅助绘制/审核）的可用性

### 可以稳定提取的

| 目标 | 数据来源 |
|---|---|
| 位号清单 / BOM 线索 | `SCH_PAGE` 与 `PCB` 的 `ATTR(key="Designator")` + `DEVICE.META.attributes` |
| 元件-符号-封装绑定 | `COMPONENT.partId` + `ATTR(Symbol/Device/Footprint)` |
| PCB 网络表（焊盘级） | `COMPONENT` + `ATTR(Designator)` + `PAD_NET`（只取有 payload 的行） |
| 焊盘几何 / 层 / 孔径 | `FOOTPRINT.PAD` + `PCB.COMPONENT` 变换 |
| 设计规则（线宽/间距/孔径） | `RULE`（按 `ruleContext.unit` 解读） |
| 3D/结构件 | `SHELL/SHELL_ENTITY/CREASE/BOSS` |
| 原理图文字/标注 | `TEXT`、`ATTR`（`@Project Name` 等标题栏字段） |

### 需要额外算法的

| 目标 | 难点 |
|---|---|
| 原理图引脚级网表 | 没有现成 netlist；要算引脚坐标、WIRE/LINE 端点匹配、网络标志传播、跨页连接 |
| 原理图 → PCB 一致性 | 要靠 `Designator` + 引脚/焊盘号对齐；样本里 `ATTR(Footprint)=null` 的元件需要从 `DEVICE` 回退 |
| 变体/复用块 | 涉及 `INSTANCE`/`VARIANT`/`COMPONENT_GROUP` 文档，8 个样本均未出现，规则待验证 |

### 下一步建议

1. 用 `src/epru_reader.py` 把 `design/` 下的真实工程读成中间结构（文档列表 + 记录表）。
2. 先做 **PCB 侧网表**（数据最完整），再做 **原理图几何连通性**。
3. 拿 `.epro2` 与立创客户端“导出网表”结果做一次逐网对比（待验证：客户端导出的 `.net` 是否能作为基准）。
4. 补样本：CBB 工程、带变体的工程、单文档导出（`SYS_FileManager.getDocumentFile` 的 `epro2`）——目前都未覆盖。

---

## 10. 样本与复现

### 样本（本机）

| 文件 | editorVersion | 记录数 | 文档数 |
|---|---:|---:|---:|
| `Claude_code_in_vscode/参考样本/lceda/guandeng-shenqi/ProPrj_【DIY电子】关灯神器_2026-09-12.epro2` | 3.2.186 | 7,265 | 127 |
| `Claude_code_in_vscode/参考样本/lceda/candis-esp32s31/ProPrj_立创·Candis-ESP32S31开发板_2026-09-12.epro2` | 3.2.186 | 34,763 | 220 |
| `Claude_code_in_vscode/项目文档/DRV8701编码电机驱动/ProPrj_DRV8701编码电机驱动_2026-09-27.epro2` | 3.2.149 | 6,966 | 75 |
| `Claude_code_in_vscode/项目文档/USB拓展坞/ProPrj_USB程序拓展坞Claude_2026-09-27.epro2` | 3.2.149 | 7,470 | 106 |
| `Desktop/嘉立创工程/ProPrj_无线充电_2026-03-13*.epro2`（4 个变体） | 3.2.91 | 47,022–47,165 | 583–585 |

### 复现命令

```bash
# 读工程、列文档
python projects/epro2-辅助绘制及审核/src/epru_reader.py <工程.epro2> --list

# 导出某个文档的全部记录
python projects/epro2-辅助绘制及审核/src/epru_reader.py <工程.epro2> --dump <文档uuid>
```

读取器对 8/8 样本以 `strict=True` 通过（`read_project(..., strict=True)`），记录数与逐行统计一致。

### 附件

调研期间的探测脚本与中间报告放在 `outputs/epro2_probe/`，任务结束后已按工作区规则清理；文中所有数字都可以用 `src/epru_reader.py` 的 `--list` / `--dump` 复现。

---

## 11. 待验证

- [ ] `firstTicket` 的准确定义（官方未提）。
- [ ] `ELE_PLACEHOLDER/META_PLACEHOLDER` 的 `max` 是否会随编辑变化（本文只做了静态观察）。
- [ ] `INSTANCE` / `VARIANT` / `COMPONENT_GROUP` 在带变体工程中的实际结构。
- [ ] CBB 工程（`cbb_project: true`）是否仍只有一个 `.epru`。
- [ ] 单文档导出（`getDocumentFile` 的 `epro2`）与整工程导出的容器差异。
- [ ] 加密/密码导出的容器差异。
- [ ] 导线端点落在另一根导线内部时，EasyEDA 是否在某些情况下自动补 junction（§3.7 只证明两个样本里不补）。
- [ ] 短接标识「两引脚同网」语义在其他工程/其他 DEVICE 变体中是否一致（§3.7 只由 1 个工程 + PCB 网表验证）。
- [ ] 总线（bus）、线束（harness）、层次页符号的连接规则未实测，`lineGroup` 之外可能还有别的连接载体。
- [ ] 连接规则只在 editor 3.2.186 上做过网表交叉验证，3.2.91 / 3.2.149 待验证。
- [ ] 原理图镜像的「竖直轴翻转」与 PCB 镜像的「局部 x 取反」只在 2 个工程上验证过；PCB 侧靠几何吻合度而非网表证明，换封装库需复核。
