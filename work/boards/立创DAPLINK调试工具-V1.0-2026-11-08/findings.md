# Findings

> 状态：候选 / 已确认 / 待复核 / 已关闭（修复）/ 已关闭（接受风险）/ 不适用
> 规则见 `docs/finding-lifecycle.md`。关闭的 finding 不删除。
> 本表来自 2026-11-08 API 连通性测试，**未做完整设计审查**。

| ID | 检查项 | 状态 | 严重度 | 定位 | 事实 | 要求及来源 | 证据 | 关闭条件 | 处理人/日期 |
|---|---|---|---|---|---|---|---|---|---|
| F-001 | A-02 ERC | 候选 | S3 | SCH/全部 7 页 | `sch_Drc.check` 返回 1 条 `warn`，接口只给汇总无落点 | 原理图应通过 ERC 或逐条说明豁免 | `snapshot/`、`logs/2026-11-08-api-test.md` | 在 EDA 里定位该告警并记录原因；确认是问题则升「已确认」 | agent/2026-11-08 |
| F-002 | B-01 未连接引脚 | 候选 | S2 | SCH/PD-Power U6.A8/A8；RS485-RS232 U11.7~10；LCD-Key-Beep U15.3 | 7 脚无网且未标 NC：USB-C SBU1/SBU2、MAX3232 第二通道 4 脚、蜂鸣器第 3 脚 | 未使用引脚应按设计意图标 NC 或明确处理（来源待查器件手册） | `snapshot/sch_netlist.json`、`snapshot/nc_pins.json` | 查 U6/U11/U15 手册与设计意图；确认可悬空则标「不适用」并写明理由 | agent/2026-11-08 |
