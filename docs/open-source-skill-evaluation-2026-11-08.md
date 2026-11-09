# 开源 EDA skill / 检查器本地评估（2026-11-08）

## 结论

目前没有找到一个同时满足“原生读取本项目 `.epro2` V3、可独立判断原理图与 PCB 电气/几何正确性、证据可定位、测试能代表真实设计”的现成开源 skill。最值得借鉴的是 `zsy-smu/easyeda-pcb-design` 的**确定性离线检查器和证据边界**；建议只移植经过逐项审查、改成适配本项目数据格式的检查，不把整个 skill 接入为绘图代理或放行器。它目前不直接解析本项目 `.epro2`，其中的旧 `.epro` 交付检查、桥接接口也不能直接复用。

这里的“通过本地测试”只表示固定版本在本机的公开测试及所述探针得到该结果，不表示经行业认证、真实 PCB 正确，或完整安全审计。候选仓库只下载到调研目录，没有注册或安装成 Claude/Codex skill，也没有运行需要编辑器连接的操作。

## 固定版本与本地验证

| 仓库 | 固定版本 / 许可 | 本地结果 | 对本项目的判断 |
|---|---|---|---|
| [zsy-smu/easyeda-pcb-design](https://github.com/zsy-smu/easyeda-pcb-design) | `bc3c73699624e7aa360ff135eb900d0284d3a8df`；MIT；归档 SHA-256 `1e84ed8e0cf8ac2367946c96aa9f26eed6ad02da2626242ec66c195d21be9887` | `python -m unittest discover -s tests -v`：212 项，210 通过、2 项因 Windows 无创建符号链接权限而跳过；进程退出码 0。 | 三者里最适合逐项借鉴。包含网表端点、层/焊盘与 Gerber 几何、交付证据、输入保护等确定性工具；但 Gerber 铜连通检查限定双层并拒绝若干未支持的图元/极性；依赖 Shapely。handoff 支持的是旧 `.epro` JSON-line 格式，不是本项目 `.epro2` V3；AI bridge 是 loopback WebSocket 8766，与本机 API bridge 49620 不同。布线/铺铜生成工具属于改图能力，不纳入只读审查。 |
| [SPREsxm/claude-pcb-designer](https://github.com/SPREsxm/claude-pcb-designer) | `d808009800f78fa37bc13c009cf6070301d34c23`；MIT | `python -m unittest discover -s tests -v`：21 项通过，0 失败。 | 适合作为计算器、设计流程和发布文件完整性检查的参考；不解析 `.epro2`，发布审计不等于网络连通/电气正确。部分计算测试是同一公式的正反向一致性，不是独立物理验证。未运行它的安装器；安装脚本含递归删除逻辑，禁止未经审查就使用强制安装选项。 |
| [Jean-Valjean-dev/lceda-review](https://github.com/Jean-Valjean-dev/lceda-review) | `9ee8f778af246a5ad8a18f445ca2fb7f47dbc2d2`；MIT | `node test/run.js`：公开合成坏板用例中 10 类预期 finding 均触发，脚本成功退出。另运行空网表探针，得到 **100/100 `READY`、0 元件、0 网络、8 组覆盖全部“通过”**。 | 不建议作本项目判据引擎、覆盖率依据或“可以出板”门槛。该反例说明空输入没有被识别为证据不足；README 将高分描述为可出板，而本项目明确不制定放行规则。其固定去耦/LED/晶振启发式与板级规则也不应当作普遍硬性要求。适合作为规则思路参考，须逐项标注适用条件和证据来源。 |

本机环境：Python 3.13.2、Node.js v24.18.0、Shapely 2.1.2。第三个候选的两个跳过项是 Windows 下创建目录符号链接失败（`WinError 1314`）；这不是测试断言失败。完整下载快照、仓库信息和固定 commit 记录在同目录 `outputs/skill-research-2026-11-08/`，候选文件只用作审阅和测试输入。

复现命令（工作区根目录 PowerShell）：

```powershell
python -m unittest discover -s 'projects/epro2-辅助绘制及审核/outputs/skill-research-2026-11-08/zsy-smu__easyeda-pcb-design/tests' -v
python -m unittest discover -s 'projects/epro2-辅助绘制及审核/outputs/skill-research-2026-11-08/SPREsxm__claude-pcb-designer/tests' -v
node 'projects/epro2-辅助绘制及审核/outputs/skill-research-2026-11-08/Jean-Valjean-dev__lceda-review/test/run.js'
node 'projects/epro2-辅助绘制及审核/outputs/skill-research-2026-11-08/probe-lceda-empty.js'
```

## 对项目的落地建议

1. 继续以项目自己的 `.epro2` 提取器、EasyEDA 原生 ERC/DRC/API 读数和 `review-criteria-v2.md` 为基础。所有检查报告使用 `PASS / FAIL / NOT_CHECKED`（或等价明示状态），缺少输入、格式不支持、证据缺失都不能折算成通过。
2. 优先审阅并移植 `zsy-smu` 的网表端点及 Gerber 几何检查设计：把输入转换为本项目已校验的数据结构，保留单位、层、坐标变换和源对象 ID；对每个检查建立正例、负例、边界例、格式错误例。几何算法先用受控样本与 EasyEDA API/原生 DRC 对账，未校准部分仍输出候选或 `NOT_CHECKED`。
3. `SPREsxm` 的电流/阻抗/电源估算可作为计算辅助，但最终结论必须由实际器件、铜厚、叠层、环境及数据手册参数支撑；保持其估算性质，不引入其自动发布门槛。
4. 不移植 `lceda-review` 的 READY 评分和固定经验阈值。若借鉴单条规则，应补充器件/拓扑适用条件，并以设计意图和器件手册为判据。
5. `.epro2` V3 尚无经本次验证可直接端到端运行的第三方 skill。需要兼容时，采用窄适配器连接已验证提取结果，不让工具修改原工程；所有未覆盖的叠层、铺铜、曲线/极性或电气意图明确报告为未检查。

本次评估不证明任何候选脚本不存在安全问题，也没有在真实板上验证它们的电气、热、EMC、制造或装配判断。公开测试主要验证作者所写的合成夹具和实现约束，真实工程仍需独立核查。
