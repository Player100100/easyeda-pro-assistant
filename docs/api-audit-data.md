# 审核一块板子，EasyEDA API 能直接给你什么

**结论**：审核需要的数据，API 基本都能直接拿，而且**与 `.epro2` 离线解析是同一 CAD 数据库的不同读数**——
PCB 网表、逐个焊盘网名、走线/过孔/铺铜的网名与几何、元件位号封装层位、DRC 结论、
设计规则、网络类、差分对、等长组，全部有对应接口。已在真实工程「装甲板」上跑通全链路
（见 §5），三份独立读数——原理图网表、PCB 网表、焊盘级 API——**34 网 134 脚完全一致**。

**但 DRC 只给汇总，不给落点**：`check(..., includeVerboseError=true)` 返回的是
`[{type:'warn', count:1}]` 这种按类型计数，没有违例对象的 id/坐标。要在报告里定位到
「哪个元件哪个焊盘」，DRC 这条路走不通，得靠网表/几何自查。

但有三个硬约束必须先知道：

1. **没有 headless。** 所有数据接口都作用于**当前打开的文档**，没开工程时直接报错
   （实测：`pcb_Net.getAllNets()` 返回 `null`，`pcb_PrimitiveComponent.getAll()` 抛
   `Cannot read properties of null`，`sch_PrimitiveComponent.getAll()` 抛「获取所有器件失败」）。
   所以自动化审核必须是「客户端开着 → bridge 连上 → 一次一个文档地取」。
2. **原理图侧只有网表，没有「引脚→网名」查询。** 原理图引脚对象 `ISCH_PrimitivePin`
   没有 net 属性；要拿引脚归属只能走网表（`SCH_Netlist.getNetlist` /
   `SCH_ManufactureData.getNetlistFile`），或者自己按几何重建（`src/extract.py` 干的事）。
   PCB 侧相反，焊盘对象直接带 `net`。
3. **未布线的飞线（ratline）没有枚举接口。** 只有 `start/stopCalculatingRatline` 和
   `getCalculatingRatlineStatus`（控制开关），没有「列出所有未连接对」的方法。
   要查漏连，只能靠 DRC 或自己拿网表减已布线图元。

> **验证状态**：所有接口名与签名来自 API 参考文档。2026-11-06 在运行中的客户端
> （bridge 49620）上做了两轮实测：先在无工程状态下逐个 `typeof === 'function'`，
> 再在工程「装甲板」上真正取了一遍数据。**§5 列出的那些已实测**；表里没被 §5 覆盖的
> 仍标「待验证」。

---

## 1. 按审核需求查

### 1.1 原理图

| 审核要的东西 | 接口 | 返回 | 状态 |
|---|---|---|---|
| 原理图网表（Protel 2.0 / JLCEDA / EasyEDA / PADS / Allegro / DISA / DSNET） | `eda.sch_ManufactureData.getNetlistFile(fileName?, netlistType?)` | `File \| undefined` | ✅ 实测：`.text()` 拿到 57 KB Protel 2.0，49 元件 / 34 网 |
| 同上，但要字符串 | `eda.sch_Netlist.getNetlist(type?)`（文档标「已弃用」，仍可用） | `Promise<string>` | 待验证 |
| 元件清单（位号、器件、符号、封装、是否进 BOM/PCB） | `eda.sch_PrimitiveComponent.getAll(componentType?, allSchematicPages?)` → `getState_Designator/Component/Symbol/Footprint/AddIntoBom/AddIntoPcb/UniqueId/OtherProperty` | 图元数组 | 待验证 |
| 某元件的全部引脚（编号/名称/类型/是否标「不连接」） | `eda.sch_PrimitiveComponent.getAllPinsByPrimitiveId(id)` → `ISCH_PrimitiveComponentPin` | 引脚数组 | ✅ 实测：`getState_PinNumber/PinName/NoConnected` 都能取（`NoConnected` 未列入文档，但存在） |
| 导线（按网名筛） | `eda.sch_PrimitiveWire.getAll(net?)` → `getState_Net()`、折线点、线宽、线型 | 导线数组 | 待验证 |
| 网络标志 / 网络端口 / 短接标识 | `ISCH_PrimitiveComponent.getState_Net()`（只对标志类元件有值） | 网名字符串 | 待验证 |
| 原理图 DRC | `eda.sch_Drc.check(strict, userInterface, includeVerboseError)` | `false`→`boolean`；`true`→`[{type, count}]`，**只有汇总没有落点** | ✅ 实测 |
| 原理图 BOM | `eda.sch_ManufactureData.getBomFile(fileName?, fileType, template?, filterOptions?, …, assemblyVariantsConfig?)` | `File` | 待验证 |
| 仿真网表 | `eda.sch_ManufactureData.getSimulationNetlistFile(fileName?, type)` | `File` | 待验证 |
| 图页/图纸清单 | `eda.dmt_Schematic.getAllSchematicPagesInfo()` / `getAllSchematicsInfo()` | 元数据数组 | 待验证 |

原理图**图纸内的几何连接**（哪根线接了哪个脚、有没有隐式 T 连接）API 不提供查询。
要这个只能：用网表（EasyEDA 自己算的），或按几何重建（见 `extraction-guide.md` §4）。

### 1.2 PCB 网表与电气连接

| 审核要的东西 | 接口 | 返回 | 状态 |
|---|---|---|---|
| PCB 网表 | `eda.pcb_Net.getNetlist(type?)` / `eda.pcb_ManufactureData.getNetlistFile(fileName?, type?)` | `string` / `File` | ✅ 实测（ManufactureData 路径）：59 KB / 34 网；`pcb_Net.getNetlist` 未测 |
| 全部网名 | `eda.pcb_Net.getAllNetsName()` | `string[]` | 待验证 |
| 全部网 + 颜色 + 长度 | `eda.pcb_Net.getAllNets()` | `IPCB_NetInfo[]`（`net` / `color` / `length`） | ✅ 实测：34 网，字段可用 |
| 单个网的长度 | `eda.pcb_Net.getNetLength(net)` | `number` | 待验证 |
| **某个网上的所有图元** | `eda.pcb_Net.getAllPrimitivesByNet(net, primitiveTypes?)` | `IPCB_Primitive[]` | 待验证 |
| 某元件的全部焊盘（含网名） | `eda.pcb_PrimitiveComponent.getAllPinsByPrimitiveId(id)` / `IPCB_PrimitiveComponent.getAllPads()` | `IPCB_PrimitiveComponentPad[]` | ✅ 实测：49 元件共 162 焊盘，网名齐全 |
| 按层/网/焊盘类型筛焊盘 | `eda.pcb_PrimitivePad.getAll(layer?, net?, primitiveLock?, padType?)` | `IPCB_PrimitivePad[]` | ✅ 实测（166 个）。**注意：返回的焊盘 `getState_ParentComponentPrimitiveId()` 全是 `null`**，用它拿不到「焊盘属于哪个元件」，要归属必须走上一行 |
| **某个焊盘实际连到了什么** | `IPCB_PrimitiveComponentPad.getConnectedPrimitives(onlyCentreConnection)` | `onlyCentreConnection=true`：线/弧/过孔；`false`：再加 polyline/fill/pour 类 | 待验证（BETA） |
| **整条走线**（跨过孔带拐点） | `IPCB_PrimitiveLine.getEntireTrack(includeVias)` | `PrimitiveLine \| PrimitiveArc`（`includeVias=true` 时含过孔） | 待验证（BETA） |
| 走线/过孔的相邻图元 | `IPCB_PrimitiveLine.getAdjacentPrimitives()` / `IPCB_PrimitiveVia.getAdjacentPrimitives()` | 邻接图元数组 | 待验证（BETA） |
| 走线（按网/层筛） | `eda.pcb_PrimitiveLine.getAll(net?, layer?, primitiveLock?)` | `IPCB_PrimitiveLine[]` | 待验证 |
| 过孔 | `eda.pcb_PrimitiveVia.getAll(net?, primitiveLock?)` | `IPCB_PrimitiveVia[]`（x/y/diameter/holeDiameter/viaType/net） | 待验证 |
| 铺铜 / 填充 / 区域 / 铜皮线 | `eda.pcb_PrimitivePour.getAll(net?, layer?)`、`PCB_PrimitiveFill/Region/Polyline.getAll(...)` | 图元数组 | 待验证 |

焊盘对象可用属性（`IPCB_PrimitivePad`）：`net`、`padNumber`、`padType`、`pad`、`layer`、
`rotation`、`x`、`y`、`hole`、`holeOffsetX/Y`、`holeRotation`、`metallization`、
`solderMaskAndPasteMaskExpansion`、`heatWelding`、`specialPad`。

> 单位：PCB 侧 API 与 `.epro2` 一致，**1 单位 = 1 mil**。已实测确认：本板 129 个过孔
> 全部 `diameter=24 / holeDiameter=12`，即 0.610 / 0.305 mm，与 `.epro2` 里同一块板的
> `viaDiameter=24 / holeDiameter=12` 逐值相同。

### 1.3 PCB 元件与装配

| 审核要的东西 | 接口 | 状态 |
|---|---|---|
| 元件清单（位号/器件/封装/层/旋转/X/Y） | `eda.pcb_PrimitiveComponent.getAll(layer?, primitiveLock?)` + `getState_*` | ✅ 实测：49 个元件，字段齐全 |
| 是否进 BOM / 是否有 3D / 供应商料号 | `getState_AddIntoBom()` / `getState_Model3D()` / `getState_Supplier()` / `getState_SupplierId()` / `getState_Manufacturer()` / `getState_ManufacturerId()` / `getState_Value()` | 待验证 |
| 任意自定义属性（含「Convert to PCB」等） | `getState_OtherProperty()` / `getAllPropertyNames()` | 待验证 |
| BOM 文件 | `eda.pcb_ManufactureData.getBomFile(...)` | 待验证 |
| 坐标文件（SMT 贴片） | `eda.pcb_ManufactureData.getPickAndPlaceFile(fileName?, fileType?, unit?)` | 待验证 |
| 元件是否被锁定 | `getState_PrimitiveLock()` | ✅ 实测 |

### 1.4 DRC 与设计规则

| 审核要的东西 | 接口 | 返回 | 状态 |
|---|---|---|---|
| **PCB DRC 结果** | `eda.pcb_Drc.check(true, false, true)` | `Promise<Array<any>>`——**实测是 `[{type:'warn'\|'error', count:n}]` 的汇总，没有违例对象 id / 坐标** | ✅ 实测（本板 `[]`） |
| PCB DRC 仅通过与否 | `eda.pcb_Drc.check(true, false, false)` | `boolean` | ✅ 实测 `true` |
| 实时 DRC 状态 | `eda.pcb_Drc.getRealTimeDrcStatus()` | `boolean` | ✅ 实测 `false`（未开启） |
| 全部规则配置 | `eda.pcb_Drc.getCurrentRuleConfiguration()` | `Record<string,any>`（嵌套表） | ✅ **可读**（2026-11-07 在「信号滤波器成品」实测）：返回 `config.Spacing` 等分组，含 `copperThickness1oz` 表、`unit:"mm"`、真实数值（最小间距 0.152 mm、铜到板边 0.254 mm 等）。**前提：PCB 必须是当前激活文档**——原理图页在前台时同一调用返回 `null`/报「画布内没有相关订阅」 |
| 网络规则 / 按网规则 / 区域规则 | `getNetRules()` / `getNetByNetRules()` / `getRegionRules()` | 规则数组 | ✅ 实测：`getNetRules()` 返回 34 条（每网一条），全部字段为 `"default"`，无自定义；`getNetByNetRules()` 两组空数组；`getRegionRules()` 空 |
| 网络类 | `eda.pcb_Drc.getAllNetClasses()` | `IPCB_NetClassItem[]` | ✅ 实测（本板为空数组，即未定义网络类） |
| 差分对 | `eda.pcb_Drc.getAllDifferentialPairs()` | `IPCB_DifferentialPairItem[]` | ✅ 实测（空） |
| 等长组 | `eda.pcb_Drc.getAllEqualLengthNetGroups()` | `IPCB_EqualLengthNetGroupItem[]` | ✅ 实测（空） |
| 焊盘对组 + 最小线长 | `getAllPadPairGroups()` / `getPadPairGroupMinWireLength(name)` | 数组 | 待验证 |

DRC 是唯一能直接回答「这块板过不过规则」的接口。`includeVerboseError=true` 的返回结构
必须先 dump 一次再写解析代码，别按猜测写。

### 1.5 层、叠层、板框

| 审核要的东西 | 接口 | 状态 |
|---|---|---|
| 层清单 | `eda.pcb_Layer.getAllLayers()` → `IPCB_LayerItem[]` | ✅ 实测：返回 **262 条**（含全部未使用的 Inner/机械/自定义层），靠 `layerStatus` 筛：本板 id 1/2/15/16 为 1（Top/Bottom/Inner1/Inner2），其余 0；`type` 可区分 SIGNAL/SILKSCREEN/SOLDER_MASK/PASTE_MASK/ASSEMBLY/OTHER/CUSTOM |
| 当前叠层配置 | `eda.pcb_Layer.getCurrentPhysicalStackingConfiguration()` / `…Name()` | ⚠️ 返回 `null` / `undefined`。接口文档标注 **ADD since EDA v4.2**，当前客户端更早，属版本缺失，不是本板没配置。铜厚/介电厚度/阻抗仍取不到 |
| 铜层数 | 读叠层里的 `numberOfCopperLayers`（无直接 getter，`setTheNumberOfCopperLayers` 只写） | ⚠️ 走不通（叠层接口为空）。实际铜层数只能从 `getAllLayers()` 里 `layerStatus==1` 的信号层推出 |
| 板框 | `eda.pcb_PrimitivePolyline.getAll(undefined, EPCB_LayerId.BOARD_OUTLINE)`（11） | ✅ **可读**（2026-11-07 实测）：本板 1 条 polyline，`getState_Polygon()` = `["R", x, y, w, h, rot, round]`（见 `TPCB_PolygonSourceArray`）。本板 = 45 × 50 mm、圆角 3 mm、左上角 (196.85, 0)，y 向下为负。圆弧/直线板框改用 `pcb_PrimitiveArc/Line.getAll(undefined, 11)` |
| 安装孔 | 同上，`eda.pcb_PrimitivePad.getAll(11)` 只返回画在板框层的焊盘 | ◐ 本板该层 0 个焊盘 = 没有安装孔；通孔元件焊盘走 `getAll()` 后按 `getState_Hole()` 筛 |
| 丝印文字 | `eda.pcb_PrimitiveString.getAll(layer)` + `eda.pcb_PrimitiveAttribute.getAll(parentPrimitiveId?, layer)` | ✅ 实测：本板独立 string **0 条**，全部文字来自 312 条 attribute（层 3）；位号用 `getState_Key()==='Designator'` + `getState_ValueVisible()` 筛。**能直接查「位号是否可见、在不在板内」** |
| 画面截图 | `eda.dmt_EditorControl.getCurrentRenderedAreaImage(tabId?)` | 待验证；用于丝印/装配目检 |

### 1.6 定位到具体对象（本项目审核报告硬要求）

| 用途 | 接口 |
|---|---|
| 坐标 → 图元 | `eda.pcb_Document.getPrimitiveAtPoint(x, y)` |
| 区域 → 图元 | `eda.pcb_Document.getPrimitivesInRegion(left, right, top, bottom, leftToRight?)` |
| 跳转到坐标 / 区域 | `eda.pcb_Document.navigateToCoordinates(x, y)` / `navigateToRegion(l, r, t, b)` |
| 高亮 / 选中某个网 | `eda.pcb_Net.highlightNet(net)` / `selectNet(net)` |
| 打开某页 / 某文档 | `eda.dmt_EditorControl.activateDocument(tabId)` / `openDocument(uuid)` |

这几条让审核意见可以直接标「点这里」——`review/` 报告里每条都能落到可点击的位置。

### 1.7 制造文件（交叉核对用）

`eda.pcb_ManufactureData` 里可以直接出：Gerber、钻孔、IPC-2581C、**IPC-D-356A**
（净表测试文件，含每个焊盘的网名 + 坐标，适合当第三份独立读数）、DXF、STEP/OBJ、
飞针测试文件、ODB++、Altium 工程。审核时用 IPC-D-356A 交叉核对焊盘网名很划算。

---

## 2. 拿不到 / 必须自己算的

| 要的东西 | 为什么拿不到 | 替代 |
|---|---|---|
| 原理图「引脚 → 网名」 | `ISCH_PrimitivePin` 无 net 属性 | 网表；或 `extract.py` 几何重建 |
| 原理图几何连接拓扑 | 无接口 | `extract.py`（规则见 `extraction-guide.md` §4） |
| 未布线连接（飞线）清单 | 只有 ratline 开关，无枚举 | DRC（开路/未连接类规则）；或网表 − 已布线图元 |
| **DRC 违例的具体对象** | `check(true,false,true)` 实测返回汇总（本板 `[]`）；接口文档称 `includeVerboseError=true` 时"返回值总是数组"并含明细，但结构未 dump 验证 | 先用一块有违例的板 dump 一次；否则按规则复算 |
| 物理叠层参数（铜厚/介电厚度/阻抗） | `getCurrentPhysicalStackingConfiguration()` 需 EDA v4.2+，当前客户端早于该版本 | 用层清单推层数；厚度/阻抗看 `.epro2` 或界面 |
| 铜皮填充的网名/层 | `IPCB_PrimitivePoured` 只有 `PourPrimitiveId` + `PourFills`，要回查 `pcb_PrimitivePour.get(id)` 才拿到 layer/net | 用 `pcb_PrimitivePour.getAll()` 建立 id → (layer, net) 映射 |
| 未布线的飞线清单独占 | 仍无接口 | 同上一行：DRC 或网表 − 已布线 |
| 跨工程批量 | `openProject` 会丢当前未保存改动，且无 headless | 逐个开 → 取 → `saveFileToFileSystem` 落盘 |
| 元件内部符号/封装的原始几何 | 只能拿封装引用，不能拿图元级几何 | 库接口 `lib_Footprint` / `lib_Symbol`，或 `.epro2` 离线解析 |
| 变更历史 / 谁改了什么 | 无 | 无 |

另有两个操作性约束：

- **`sys_FileSystem.saveFileToFileSystem` 是客户端侧写盘**，需要扩展的
  「允许外部交互」权限。写到哪里取决于扩展沙箱，路径映射**待验证**。
- **`dmt_Project.getAllProjectsUuid()` 不是全局无参枚举**，找工程要先 `getAllTeamsInfo()`
  再按 team/folder 遍历（skill 里已踩过一次）。
- **PCB 类接口只在 PCB 文档是当前激活页时有效。** 原理图页在前台时，`pcb_Layer.getAllLayers()`
  返回 `null`、`pcb_Drc.getCurrentRuleConfiguration()` 报「指定的主题消息在对应的画布内没有相关订阅」。
  取 PCB 数据前先 `dmt_EditorControl.openDocument(pcbUuid)` 并等 1~2 s。2026-11-07 就是因此
  一度误判「规则读不到」。

---

## 3. 和离线解析怎么分工

两条路不是二选一，各管一段：

| 场景 | 用哪个 |
|---|---|
| 一次性的、要留档的全量快照 | `src/extract.py`（离线，`.epro2` 一进一出，可 diff 版本） |
| PCB 网表 / 焊盘网名（原生读数） | API（`pcb_Net` / `pcb_PrimitivePad`），或 `extract.py` 读 `PAD_NET`——两者应一致，可互相校验 |
| 原理图网表（原生读数） | API 网表导出（EasyEDA 自己算的）；`extract.py` 的重建结果用它校验 |
| DRC 结论 | 原生结果用 API（`pcb_Drc.check`）；离线只能复算部分几何，不能替代完整 DRC |
| 设计规则 / 网络类 / 差分对 / 等长组 | **只能**用 API（离线包里虽有 `RULE` 记录，但语义不完整） |
| 铺铜实际填充多边形 | 离线 `--with-poured` 比 API 稳（API 需重新算） |
| 版本对比（改了之后比） | 离线两份 `extract.py` 输出 + `validate_netlist.py` |
| 定位到画布上某一处 | **只能**用 API（navigate/highlight） |

建议的审核流水线：

1. 开工程 → bridge 取 **原理图网表** + **PCB 网表** + **PCB DRC 结果** + **规则/网络类/差分对**
   → 落盘到 `<DATA_DIR>/outputs/api/<工程>/`（外部目录，见 [运行产物目录](output-directories.md)）
2. 离线 `extract.py` 出几何与坐标，给审核意见提供落点
3. `validate_netlist.py` 把 1 和 2 对一次，不一致就是线索
4. 审核结论写入 `<DATA_DIR>/review/`，每条带位号/网名/坐标/页码

---

## 4. 怎么跑

用项目里的脚本，别手搓 curl：

```bash
cd projects/epro2-辅助绘制及审核

python src/eda.py up                 # 确保桥在跑（不在就脱离会话拉起）并等客户端连上
python src/eda.py status             # 端口 / 连接 / 当前工程 / 打开的页
python src/eda.py exec "return (await eda.dmt_Project.getCurrentProjectInfo())?.friendlyName;"
python src/eda.py watch              # 常驻守护，桥挂了自动重启
```

`up` 的桥进程用 Windows `DETACHED_PROCESS` 拉起，Claude Code 会话结束也不会被带走——
这正是之前 exit code 4 的成因。**但客户端那一步没法自动化**：run-api-gateway 扩展只在
它自己启动时扫一遍端口，桥换进程后不会回来，仍需在「API Gateway → 重新连接」点一次。
（扩展菜单里的「自动连接」开关是否能让它自己重扫，**待验证**。）

等价的裸 curl：

```bash
curl -s -X POST http://127.0.0.1:49620/execute \
  -H "Content-Type: application/json" \
  -d '{"code":"const p=await eda.dmt_Project.getCurrentProjectInfo();return p?{uuid:p.uuid,name:p.name}:null;"}'
```

取 PCB 网表的典型调用：

```javascript
const nets = await eda.pcb_Net.getAllNets();          // [{net,color,length},...]
const pads = await eda.pcb_PrimitivePad.getAll();     // 全部焊盘，含 net/padNumber/x/y/layer
const comps = await eda.pcb_PrimitiveComponent.getAll();
return { netCount: nets.length, padCount: pads.length, compCount: comps.length };
```

DRC 结果**先 dump 结构再解析**：

```javascript
const v = await eda.pcb_Drc.check(true, false, true);
return { count: v.length, sample: v.slice(0, 2) };
// 实测返回：[{type:'warn', count:1}] —— 只有类型和计数
```

**文档切换是必须的**：PCB 接口只在 PCB 文档激活时可用，原理图 DRC 也只在原理图页激活时
可用。实测在 PCB 文档上调用 `sch_Drc.check()` 会抛
`SCH_DrcUtil: doctype(3) not support check sch drc`。切换方式：

```javascript
const tree = await eda.dmt_EditorControl.getSplitScreenTree();
await eda.dmt_EditorControl.activateDocument(tree.tabs[1].tabId);  // 原理图页
await eda.dmt_EditorControl.activateDocument(tree.tabs[2].tabId);  // PCB
```

---

## 5. 实测记录（2026-11-06，工程「装甲板」）

环境：EasyEDA Pro editor 3.2.186，bridge 在 49620，单窗口。
工程：`player1001/装甲板`（uuid `ba2b7e07…`），1 块板 / 1 页原理图 / 1 块 PCB。

### 结果

| 读数来源 | 结果 |
|---|---|
| 原理图 API 网表（`sch_ManufactureData.getNetlistFile(_, 'Protel2')`） | 57 681 B，49 个元件段，**34 个网 / 134 个引脚** |
| PCB API 网表（`pcb_ManufactureData.getNetlistFile(_, 'Protel2')`） | 59 098 B，49 个元件段，**34 个网 / 134 个引脚** |
| 焊盘级 API（`pcb_PrimitiveComponent.getAllPinsByPrimitiveId` 汇总） | 166 个焊盘，其中 162 属元件、4 个是安装孔；**134 个已连接焊盘** |

**三者两两比对：网名集合相同；逐引脚 (位号, 脚号) → 网名 0 差异。**

### 板子概况（全部来自 API 读数）

| 项 | 值 |
|---|---|
| 元件 | 49 个（顶层 39 / 底层 10），全部 `Add into BOM = true`，全部有封装 |
| 网 | 34 个；无单脚网 |
| 焊盘 | 166 个；未连接元件焊盘 25 个（SW1/SW2/SW3 各 2 个、U2 11 个、USB1 8 个） |
| 未连接引脚是否有标记 | 原理图侧 `ISCH_PrimitiveComponentPin.getState_NoConnected()` 查出 **25 个「不连接」标记**，与上面 25 个空网焊盘逐个对应——**没有悬空脚** |
| 走线 | 184 段：顶层 142 / 底层 42；线宽 10 mil×105、11.811×43、19.685×25、31.496×4、39.37×7 |
| 过孔 | 129 个，全部 24/12 mil（0.610/0.305 mm），全贯通孔 |
| 铺铜 | 10 块 |
| 铜层 | 2 层（`getAllLayers()` 里只有 id 1/2 的 `layerStatus = 1`） |
| 板面铜范围 | x 40.0–3031.5 mil、y −1360.0–−95.1 mil → 约 **76.0 × 32.1 mm**（含安装孔，非板框） |
| DRC（PCB，strict） | 0 条违例（所有网规则都是 default，无自定义） |
| DRC（原理图） | 1 条 `warn`——**API 只给计数，定位不到** |
| 差分对 / 等长组 / 网络类 / 区域规则 | 都没有定义（空数组） |

### 这一轮暴露的 API 行为

1. `pcb_PrimitivePad.getAll()` 返回的焊盘，`getState_ParentComponentPrimitiveId()` **全是
   `null`**——焊盘归属必须从元件侧取（`getAllPinsByPrimitiveId`）。
2. `getAllLayers()` 返回 260 条，包含所有未启用的内层；必须用 `layerStatus` 过滤。
3. `getCurrentPhysicalStackingConfiguration()` 返回 `null`，叠层读不到。
4. `getRuleConfiguration(name)` 取不到值，即使 `getCurrentRuleConfigurationName()` 给了名字。
5. `sch_Drc.check()` / `pcb_Drc.check()` 都只在对应文档激活时可用。
6. DRC 的 verbose 返回值是**按类型汇总**，不是逐条违例。
7. 网表 `File` 直接 `.text()` 就能拿全文，**不需要** `saveFileToFileSystem`，也就绕开了
   客户端写盘权限。这是目前最省事的落盘方式。
8. **原理图引脚其实带「不连接」标记**：`getAllPinsByPrimitiveId()` 返回的对象上有
   `getState_NoConnected()`（API 文档的 `ISCH_PrimitiveComponentPin` 页没列这个 getter，
   实测存在）。这条把「原理图说不用接」和「PCB 焊盘空网」对上了，是查悬空脚最直接的办法。
9. 封装里可以有**重复焊盘号**：U3（SOT-223）有两个 pad 号都是 `2`、USB1 有 `13`/`14`
   各两个。按 `(位号, 焊盘号)` 去重时它们会合并，所以「焊盘数」与「网表引脚数」本来就会差，
   不是丢数据。

### 产物

`outputs/api/装甲板/`（临时，随时可清）：两份 `.net`、`pcb_data.json`、
`pcb_comp_pads.json`、`pcb_layers.json`、`drc_rules.json`、`sch_primitives.json`、
`api_components.json`。
