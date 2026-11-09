# 板卡来源与测试范围

- 板卡名称：STM32控制板（工程名「何俊熙」，PCB 名 Board1）
- 仓库 / 下载链接：无；数据来自嘉立创EDA专业版运行中的客户端，非 `.epro2` 导出包
- 版本 / commit / tag：板子未记版本号；快照日期 2026-11-08
- 许可证：未提供
- 来源格式：EasyEDA Pro 运行中工程（API 快照采集），非离线包
- 包含文件：原理图（3 页：接口 / 电源 / 主控）、PCB、BOM（从网表 BOM 字段导出）
- 是否允许下载到本地并只读解析：是（只读 API；未调用任何写接口）
- 希望重点检查：电气连接正确性、电源树、接口保护、BOM/封装一致性、制造能力
- 已知问题或想验证的点：无（用户未提供意图卡）
- 不需要检查的部分：未指定

## 采集环境

| 项 | 值 | 来源 |
|---|---|---|
| 客户端 | 嘉立创EDA专业版 3.2.149.88089769 | `pcb_raw.json:editorVersion` |
| 工程 UUID | `8d59e324dddb456db780242cae8ce7c6` | `pcb_raw.json:project.uuid` |
| 板子 | Board1（无版本号） | `pcb_raw.json:boards[0]` |
| 采集方式 | `run-api-gateway.eext` + 本地 bridge（WebSocket 49620–49629） | `src/eda.py` |
| 采集日期 | 2026-11-08 | 文件 mtime |

## 快照文件清单

路径基准：`outputs/audit/STM32控制板/2026-11-08/`（临时产物目录，按工作区规则可清理）

| 文件 | 内容 | SHA256 |
|---|---|---|
| `pcb_raw.json` | PCB 全量图元、DRC、规则、网络 | `6d71243f0a4f8ce814975f5bc05f0564a15796fe373783a1cc46bdc96c8247cd` |
| `sch_power_raw.json` | 电源页原理图 | `a8b1158552d44435fe4356d01de4e067445e1fa627f4535a0ccdc7b0ee45dafc` |
| `sch_mcu_raw.json` | 主控页原理图 | `ddae2da9d6c5b124b75ba54d928f15b976961e88c66c77e260c2016a78484e59` |
| `sch_interface_raw.json` | 接口页原理图 | `b3a74936b58c0d781e302e82e957f4f37e0b9aba164b28ac1d6e59dc4035ae9f` |
| `sch.net` | 原理图导出网表（EasyEDA JSON v2.0.0） | `e1afc9ee42953ee23899711199995599c823396bb6e446b5bdcd36d2ac765f53` |
| `pcb.net` | PCB 导出网表 | `fb268bc01438a63565f9ef7bec63d37c19039047c769d5dfabdc190e474d88e8` |
| `texts_out.json` | 原理图文本对象（网络标签/注释） | `6e3ddaa551d052363f6912db2ea60ffccd558d1de68874c49d37b9d73ea9bd58` |
| `drc_pcb_out.json` | PCB DRC 结果 | `839a414303fd6f664b19957c3ba642a668eb5b19012afef3ddb2e98e4c3d2ee7` |
| `pcb.js` / `sch_page.tpl.js` | 采集脚本 | — |

## 只读约定执行情况

- 全程只调用 `getState_*` / `getAll*` / `check()` / `getNetlistFile().text()`，未调用 `create` / `setState_*` / `done` 等写接口。
- 未打开 `.epro2` 包，未执行工程内任何脚本。
- `openDocument` / `activateDocument` 会切换客户端标签页，但不修改文档内容。
