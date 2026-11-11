# epro2-辅助绘制及审核

**状态**：调研

## 运行产物位置

后续临时文件、板卡工作记录和报告自动写入项目旁的 `../epro2-辅助绘制及审核-data/`。项目现有结构和历史资料保留。路径随实际克隆目录名生成，不依赖当前工作目录；可用 `EPRO2_DATA_DIR` 指定其他绝对路径。

```powershell
python -B src/output_paths.py --init --board '控制板-V1.0-2026-11-09'
python -B src/extract.py 'D:/design/控制板.epro2'
```

数据分为 `outputs/`（临时产物）、`work/boards/`（板卡过程记录）、`review/`（完整报告、简明报告与证据）。每次完整审核交付 `report.md` 和 `simple-report.md`；具体路径见 [运行产物目录](docs/output-directories.md)，简明版格式见 [简明报告模板](docs/simple-report-template.md)。

## 一句话目标

用 Claude Code 辅助嘉立创EDA 的绘制工作，并对原理图 / PCB 做独立审核。

## 当前进展

- 项目骨架已建立
- 已完成 `.epro2`（V3）结构调研：容器为 ZIP，设计数据全部在单个 `.epru` 日志流中。详见 `docs/epro2-v3-format.md`
- 已实现日志读取器 `src/epru_reader.py`，在 8 个真实导出包（editor 3.2.91 / 3.2.149 / 3.2.186）上严格解析通过
- 已实现提取器 `src/extract.py`：一条命令输出文档索引、原理图（元件/引脚/导线/网络）、PCB（层/元件/焊盘/走线/过孔/铺铜/板框/规则）、双网表与逐引脚对比。在两个真实工程上验证（关灯神器、Candis ESP32S31）
- 原理图网表曾用 EasyEDA 自己导出的 Protel 网表交叉验证：两个历史样本逐引脚 **0 命名差异**。2026-11-07 已修补自动网拓扑漏比、PCB 异网接触未诊断及间距脚本板框硬编码，10 个回归案例通过；历史工程尚未重跑，几何脚本仍仅提供候选，见 `docs/review-criteria-assessment.md`
- 已接通 EasyEDA API bridge（端口 49620），梳理了审核可用数据面：PCB 网表/焊盘/走线/过孔/铺铜/DRC/**设计规则数值表/板框/丝印属性**都能直接取（物理叠层需客户端 v4.2+，当前取不到），原理图侧只能取网表（引脚对象无 net 属性），且**无 headless**、**PCB 接口只在 PCB 为激活文档时有效**。详见 `docs/api-audit-data.md`
- 在真实工程「装甲板」上跑通 API 全链路：原理图网表、PCB 网表、焊盘级 API 三份读数 **34 网 / 134 脚完全一致**；PCB DRC 0 违例；原理图 25 个「不连接」标记与 25 个空网焊盘一一对应（仅证明该样本标记/映射一致，未证明悬空处理符合器件要求）。当次限制：DRC 只返回类型+计数，未取得具体定位、叠层与规则数值；规则读取能力的后续修正见下方首轮实审记录。
- 已确定审核方式（v1 框架 + v2 判据）：**三层证据 + 五个阶段**，agent 分工做语义审查、独立 reviewer 复核；仿真按四条触发条件按需跑，不默认全量。默认只读、报告带覆盖率、结论可定位。详见 `docs/review-method.md`；执行判据以 `docs/review-criteria-v2.md` 为准，可执行检查库见 `docs/review-checklist.md`
- 2026-11-06 原型发现：离线解析对**底层元件焊盘坐标**可能与铜皮不一致（关灯神器 U7/U8 候选，尚未用 API 确认）。因此把「离线坐标 vs API 焊盘坐标对账」列为审核前置项（A-04）；未对账元件的几何结论只能算候选。详见 `notes/2026-11-06-bottom-layer-pad-geometry-check.md`
- 审核口径已确认（2026-11-06）：范围 = 原理图 + PCB + BOM；依据 = 器件手册 + 电气连接知识；当前只读、只出报告；**不制定放行规则**；制造项按项目需求具体分析；未指定板厂时可输出带假设和复核条件的通用加工参数建议；由 agent 审核并做判断
- 首轮实审（2026-11-07）：「信号滤波器成品 V1.0」只读审核完成，API 双网表 34 网/178 脚 0 差异、PCB DRC 0（原理图 ERC 未记录）；报 3 项 S1 候选、5 项 S2、2 项 S3。报告见 `review/信号滤波器成品-V1.0-2026-11-07/report.md`。按 v2 复审，D-04/D-02 只能当候选，B-01 的 NC/空网对应只证明映射；同轮复核了 API 数据面：规则数值、板框、丝印位号均可读，之前「读不到」是 PCB 未激活导致的误判
- 2026-11-08 开源 skill 评估：本地跑了 3 个固定版本候选；`zsy-smu/easyeda-pcb-design` 212 项中 210 通过、2 项因 Windows 符号链接权限跳过，最适合逐项移植其只读检查器；`lceda-review` 的空网表得到 100 分 `READY`，不适合作为审核结论；没有候选直接支持本项目 `.epro2` V3。详见 `docs/open-source-skill-evaluation-2026-11-08.md`
- 2026-11-08 新增 C-10「封装与实际器件匹配」审核规范、板卡记录模板和只读结构检查器 `src/check_footprints.py`；支持用经审核的期望清单比对型号/封装绑定、映射存在性、物理焊盘清单和尺寸，缺基线仍为 `NOT_CHECKED`。极性/观察面/器件实际适配仍需人工依据厂商资料复核，历史板卡未因新增检查自动补审。详见 `docs/footprint-review.md`

- 2026-11-10 新增 C-11「关键网络供电与电荷预算」审核规范与板卡记录模板，纳入电源语义审核和逐工况覆盖统计。覆盖持续供电、瞬态电荷、供电路径压降与周期恢复；当前由 agent/人工按依据计算、必要时仿真，自动预算检查器待实现。见 `docs/power-charge-budget.md`。

## 下一步

1. 实现 A-04 坐标对账（API 焊盘 `x/y/net` 已实测可读），确定底层镜像语义
2. 实现 MVP 检查：A-01~A-05（含 A-04 校准）、B-01~B-03、B-07、D-01、D-05；D-04 只出同网/异网候选；F-01 待项目指定板厂。输出 `audit.json` + 覆盖率
3. 按 `docs/review-method.md` §4 建立 agent 分工（电源 / 接口 / 时钟复位 / PCB 几何 / BOM / C-10 封装审核 / 汇总 + 独立 reviewer），完整走一次审核并出首份报告
4. 按 `docs/review-method.md` §8 评估开源 skill，先只读、后移植规则

## 关键文件

- `docs/review-criteria-v2.md` — 当前优先判据：区分事实/要求/结果，修正 NC、网表拓扑、连通/短路、布局经验阈值和 skill 使用边界
- `docs/review-criteria-assessment.md` — 原判据核查、两个实测漏检反例、现有报告的复审范围与在线 skill 评估
- `CLAUDE.md` — 本项目的工作规则
- `docs/review-method.md` — 审核方式：三层证据、五个阶段、agent 分工、判定、技能、开源 skill 评估
- `docs/simple-report-template.md` — 完整审核后生成的简明报告模板
- `docs/open-source-skill-evaluation-2026-11-08.md` — 开源候选固定版本、本机测试、反例和本项目适配建议
- `docs/review-checklist.md` — 可执行检查库（A~G 类，含 MVP 首批、豁免、设计意图卡）
- `docs/footprint-review.md` — C-10 封装匹配：官方库分层核验、重点对象、历史证据复用与覆盖率
- `docs/power-charge-budget.md` — C-11 关键网络供电与电荷预算：工况、计算判据、仿真触发和覆盖率；板卡记录模板为 `work/boards/_template/power-charge-budget.md`
- `docs/multi-board-review.md` — 多块板的逐板隔离审核、板间连接证据模型与系统级检查边界；JSON Schema 为 `schemas/system-interconnect.schema.json`，填写模板为 `work/system-interconnect.template.json`
- `docs/manufacturing-guidance.md` — 不绑定板厂的通用加工参数建议：铜厚、层数/板厚、线宽/间距、孔/环宽、阻焊/丝印和特殊工艺
- `src/check_footprints.py` — 对 `extract.py` 输出执行只读 C-10 结构核对，期望值来自经审核的厂商/BOM 基线
- `src/test_check_footprints.py` — C-10 检查器的缺基线、映射、焊盘清单、公差与输入保护反例
- `docs/epro2-v3-format.md` — `.epro2`（V3）结构与实测差异（2026-11-06）
- `docs/extraction-guide.md` — 如何从 `.epro2` 获取完整原理图与 PCB 信息（数据来源、单位/变换、连接重建规则、限制）
- `docs/api-audit-data.md` — 审核需要的数据哪些能从 EasyEDA API 直接取（接口、返回、拿不到的、与离线解析的分工）
- `src/epru_reader.py` — `.epro2` / `.epru` 读取器（`--list` 列文档，`--dump <uuid>` 导出记录）
- `src/extract.py` — 结构化提取器（默认写到 `<DATA_DIR>/outputs/extract/<工程名>/`）
- `src/validate_netlist.py` — 用 EasyEDA 导出的 Protel 网表校验原理图重建结果
- `src/eda.py` — bridge 自动连接 / 守护：脱离会话拉起桥进程、等客户端连上、`exec` 跑 JS、`watch` 自愈（`up` / `status` / `wait` / `exec` / `watch` / `stop`）
