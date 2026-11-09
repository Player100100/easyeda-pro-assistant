# 封装匹配审核记录（C-10）

板：STM32控制板 / Board1　日期：2026-11-08　执行：agent（只读 API）+ 人工复核待定
方法见 `docs/footprint-review.md`。机器基线：`footprint-expectations.json`（79 个实例）。

## 审核对象与来源

- 工程/板/版本/原始包 SHA256：工程 `8d59e324dddb456db780242cae8ce7c6`；无 `.epro2` 原始包；快照 SHA256 见 `source.md`
- 原理图与 PCB 文档 ID、API 采集时间及快照：2026-11-08；`sch.net`、`pcb_raw.json`、三页 `sch_*_raw.json`
- 实例总数 / 不同型号与封装组合数：79 / 35 种封装名、27 个不同 MPN（其余空 MPN）
- 逻辑引脚数 / 物理焊盘数：306 / 306（按焊盘号去重）

## 覆盖面汇总

| 子项 | 适用分母 | 已执行 | 可判定 | 未检查 | 不适用 | 结论 |
|---|---|---|---|---|---|---|
| C-10.1 型号绑定 | 79 | 79 | 26（MPN 与封装名不冲突）+ 4（仅尺寸级可判） | 49 | 0 | 49 个无 MPN、46 个无 LCSC，属 BOM 缺项（F-013） |
| C-10.2 脚位/方向 | 79 | 79（脚号↔焊盘号计数） | 0（未对照厂商引脚图） | 79 | 0 | 仅证脚数一致；方向/极性未核 |
| C-10.3 物理焊盘 | 79 | 79 | 79（焊盘号集合与引脚号集合一致） | 0 | 0 | 306=306，0 个不匹配 |
| C-10.4 尺寸/装配 | 79 | 0 | 0 | 79 | 0 | 未取得厂商推荐焊盘图与实测 |

> 未知分母不填 0 或 100%。C-10.2/C-10.4 的「可判定=0」表示本轮没有厂商图纸级证据，不代表对象不合规。

## 逐对象结果（异常与重点）

完整 79 行见 `footprint-expectations.json`。下表只列有差异或有代表性和风险的对象。

| 位号/实例 | 制造商、完整 MPN/封装后缀 | 封装名（原理图 = PCB） | 引脚/焊盘 | 子项 | 状态 | 证据/缺口 | 关联 |
|---|---|---|---|---|---|---|---|
| U1 | ST STM32F103C8T6 / LQFP-48 | `LQFP-48_L7.0-W7.0-P0.50-LS9.0-BL` | 48/48 | C-10.1/3 | PASS | 名称两侧一致；焊盘号 1–48 齐全 | — |
| U1 | 同上 | 同上 | 48/48 | C-10.2 | NOT_CHECKED | 未对照 ST 引脚图核 pin1 与旋转 | — |
| U2 | Slkor LM2596S-5.0 / TO-263-5 | `TO-263-5_L10.1-W8.7-P1.70-LS14.4-BR` | 6/6 | C-10.1/3 | PASS | 6 焊盘对应 5 脚 + 散热片 | — |
| U3 | AMS AMS1117-3.3 / SOT-223 | `SOT-223-3_L6.5-W3.4-P2.30-LS7.0-BR` | 4/4 | C-10.1/3 | PASS | 4 焊盘 = 3 脚 + TAB | — |
| U4 | XLSEMI XL1509-12E1 / SOIC-8 | `SOIC-8_L5.0-W4.0-P1.27-LS6.0-BL` | 8/8 | C-10.1/3 | PASS | — | — |
| U5/U9/U10 | SS54 / 供应商封装字段 `(1N5824)DO-214` | `SMA_L4.2-W2.6-LS5.1-RD` | 2/2 | C-10.1 | REVIEW | 供应商封装字段与封装名不一致（DO-214 含 SMA/SMB/SMC）；无 Manufacturer | F-013 |
| U5/U9/U10 | 同上 | 同上 | 2/2 | C-10.2 | NOT_CHECKED | 焊盘 1/2 与 A/K 的对应未对照厂商图；U9/U10 方向错误见 F-003 | F-003 |
| U6 | YIYUAN YSSP2AG00 / SW-SMD 6P | `SW-SMD_YSSP2AG00` | 6/6 | C-10.1/3 | PASS | 自定义封装名与 MPN 同名 | — |
| U6 | 同上 | 同上 | 6/6 | C-10.2 | NOT_CHECKED | COM/NO/NC 脚位未取得厂商图 | F-017 |
| U7 | JK JK-nSMD005/60V / 1206 | `F1206` | 2/2 | C-10.1/3 | PASS | — | — |
| U8 | WCH CH340C / SOP-16 | `SOP-16_L10.0-W3.9-P1.27-LS6.0-BL` | 16/16 | C-10.1/3 | PASS | — | — |
| USB1 | HCTL HC-TYPE-C-16P-01B / SMD | `USB-C-SMD_KH-TYPE-C-16P` | 20/20 | C-10.1 | REVIEW | 封装名 KH 前缀 = 另一厂商；MPN 为 HCTL；未确认是否同尺寸兼容 | F-013 |
| USB1 | 同上 | 同上 | 20/20 | C-10.2 | NOT_CHECKED | 16 信号脚 + 4 EP 的 A/B 面映射未对照厂商图 | — |
| X1 | YXC X322516MLB4SI / SMD3225-4P | `CRYSTAL-SMD_4P-L3.2-W2.5-BL` | 4/4 | C-10.1/3 | PASS | — | — |
| X2 | Micro Crystal CM7V-T1A-...-12.5PF / SMD3215 | `CRYSTAL-SMD_L3.2-W1.5-1` | 2/2 | C-10.1/3 | PASS | — | — |
| Q1/Q2 | 无 MPN；`S8050_SOT-23` | `S8050_SOT-23` | 3/3 | C-10.1 | REVIEW | 只有封装名暗示型号，无厂商/料号 | F-013 |
| Q3 | 无 MPN；`S8550P_SOT` | `S8550P_SOT` | 3/3 | C-10.1 | REVIEW | 同上 | F-013 |
| CN1 | AMASS XT30UPB-M / TH | `CONN-TH_XT30UPB-M` | 2/2 | C-10.1/3 | PASS | 15A/500VDC（BOM） | — |
| CN2/CN3 | AMASS XT30UPB-F30.G.Y / TH | `CONN-TH_XT30UPB-F` | 2/2 | C-10.1/3 | PASS | — | — |
| DBUS1 | LXWCONN MX1.25mm-3P-WT | `CONN-SMD_MX1.25MM-3P-WT` | 5/5 | C-10.1/3 | PASS | 3 信号 + 2 固定脚，焊盘号 1–5 与网表一致 | — |
| SWD1 | LXWCONN MX1.25mm-4P-WT | `CONN-SMD_MX1.25MM-4P-WT` | 6/6 | C-10.1/3 | PASS | 4 信号 + 2 固定脚 | — |
| USART1 | `CONN-SMD_XH2.54-4PSMD`（通用名，非厂商 MPN） | `CONN-SMD_XH2.54-4PSMD` | 6/6 | C-10.1 | REVIEW | 无具体厂商/料号 | F-013 |
| H1 | 无 MPN，LCSC C402781 / 2.54 2×3 | `HDR-TH_6P-P2.54-V-R2-C3-S2.54_A2541WV-2X3P` | 6/6 | C-10.1/3 | REVIEW | 有 LCSC 料号但无 MPN | F-013 |
| H2/H3 | 无 MPN，LCSC C124373 / 2.54 1×15 | `HDR-TH_15P-P2.54-V-M` | 15/15 | C-10.1/3 | REVIEW | 同上 | F-013 |
| SW1–SW4 | 无 MPN / 4P 6×6 轻触 | `SW-SMD_4P-L6.0-W6.0-P4.50-LS9.0-2` | 4/4 | C-10.1/3 | REVIEW | 无 MPN；4 脚两两成对 | F-013 |
| D1 | CJ 1N5821 / DO-27 | `DO-27_BD3.5-L8.6-P12.60-D1.3-RD` | 2/2 | C-10.1/3 | PASS | 封装名与 DO-27 一致 | — |
| D2 | FUXINSEMI 1N5824 / DO-27 | `DO-27_BD5.3-L8.4-P12.40-D1.3-RD` | 2/2 | C-10.1/3 | PASS | 供应商封装写 DO-201AD（与 DO-27 同族），封装名 DO-27 | — |
| D3/D6 | R+O SMBJ15A / SMBJ30A / SMB | `SMB_L4.3-W3.6-LS5.3-RD` / `SMB_L4.6-W3.6-LS5.4-RD` | 2/2 | C-10.1/3 | PASS | 封装名 L4.3 / L4.6（mm）为两器件各自图纸尺寸，均属 SMB | — |
| D5 | R+O 1N4007W / SOD-123FL | `SOD-123FL_L2.7-W1.8-LS3.8-RD` | 2/2 | C-10.1/3 | PASS | — | — |
| L1 | JIERR PNR6045-680-M / 6×6 | `IND-SMD_L6.0-W6.0_LPS6225` | 2/2 | C-10.1 | REVIEW | 封装名引用 LPS6225 系列，与 MPN 的 PNR6045 不同系列；尺寸同为 6×6，焊盘图形兼容性待图纸 | 待记录 |
| L2 | JIERR PNR5040-330-M / 5×5 | `IND-SMD_L5.0-W5.0_PNR5040` | 2/2 | C-10.1/3 | PASS | 封装名与 MPN 系列一致 | — |
| C1 | JIERR JVJ35V470M10x10 / D10×L10.5 | `CAP-SMD_BD10.0-L10.3-W10.3-LS11.0` | 2/2 | C-10.1/3 | PASS | 直径 10mm 与封装名一致 | — |
| C3 | JIERR RVT25V180M6X8 / D6.3×L7.7 | `CAP-SMD_BD6.3-L6.6-W6.6-LS7.4-FD` | 2/2 | C-10.1/3 | PASS | 直径 6.3mm 一致 | — |
| C4 | JIERR MA35V680M10X13 / D10×L13.5 | `CAP-SMD_BD10.0-L10.3-W10.3-FD-LS11.0_H12.0` | 2/2 | C-10.1 | REVIEW | 封装名高度 H12.0 与 MPN 长度 13.5mm 可能不一致，需厂商图确认装配高度 | 待记录 |
| C5 | JIERR JVJ35V220M6x8 / D6.3×L7.7 | `CAP-SMD_BD6.3-L6.6-W6.6-FD` | 2/2 | C-10.1/3 | PASS | 直径 6.3mm 一致 | — |
| C2,C6–C23,R1–R15,LED1–6 | 无 MPN | `C0603`/`R0603`/`LED_0603` | 2/2 | C-10.1/3 | REVIEW | 焊盘数一致；值与耐压无 MPN | F-013 |

## 脚位/方向未核说明

- 本轮只验证了「原理图引脚号集合 = PCB 焊盘号集合」（79/79 通过，306=306）。
- 未取得任何厂商推荐焊盘图（recommended land pattern）或引脚图，因此 pin 1 方位、A/K 对应、USB-C A/B 面映射、观察面/镜像均标 `NOT_CHECKED`。
- U5/U9/U10 的 A/K 方向问题不依赖封装脚位，但**依赖符号的 A/C 引脚名正确**（F-003 记为待复核，前提是 CN2/CN3 为输出）。
- **F-001 依赖 U1 符号的 35/36/47/48 引脚名**（VSS_2/VDD_2/VSS_3/VDD_3）；本轮未对照 ST 厂商引脚图核符号映射。若符号库本身把脚号映射错了，F-001 的结论需重判。
- Q1/Q2/Q3 的 SOT-23 1=B/2=E/3=C 采用通用 SOT-23 约定；厂商数据未取得，若实际为不同 pinout 会影响 F-010/F-011。

## 历史证据复用

- 记录路径与日期：无（首次审此板）
- 核对完整 MPN/后缀、符号映射、封装定义哈希、图纸版本/哈希及相关工艺条件：未执行
- 复用哪些对象和子项：无
- 本轮实例映射/层别/旋转检查证据：仅脚数/焊盘数映射（`footprint-expectations.json`）
- 变更及需重做的子项：全部 C-10.2/C-10.4 待补

## 覆盖与未检查项

- C-10.1：79/79 已读字段；可判定 26 个（有明确 MPN 且封装名不冲突）+ 4 个仅尺寸级可判（C1/C3/C5、C4 高度待核）；REVIEW 49 个（无 MPN、仅 LCSC 或封装字段冲突）。
- C-10.2：0/79 可判定；79 个 NOT_CHECKED（缺厂商引脚图/pin1）。
- C-10.3：79/79 可判定为「焊盘号集合与引脚号集合一致」；焊盘尺寸/孔径符合厂商推荐值未核。
- C-10.4：0/79 执行。
- 定稿时需把 `footprint-expectations.json` 与相关快照复制到 `review/STM32控制板-V1.0-2026-11-08/evidence/`。
