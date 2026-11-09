# 设计意图卡（agent 推断，未经用户确认）

> 用户未提供意图卡。以下全部为 `inferred`，只作为检查假设，不得单独作为 PASS/FAIL 依据。
> 标「待确认」的条目需要用户回答后才能升级为 explicit。

## 1. 基本信息

- 工程名 / 版本 / 日期：STM32控制板 / 无版本 / 无日期（`inferred`）
- 板子用途（一句话）：STM32F103C8T6 最小系统 + 24V→12V→5V→3.3V 多级电源 + USB 转串口 / DBUS / SWD 扩展的控制板（`inferred`，依据：U1 型号、电源页网络标签、接口页连接器）
- 板型档位：B（MCU/混合信号），两层板 70×100mm（`inferred`，依据：U1 + 3 级 DC-DC/LDO）
- 审核请求人 / 资料提供人：用户本人

## 2. 电源

| 轨 | 来源 | 目标 | 依据 |
|---|---|---|---|
| +24V | CN1 XT30 (24V 输入) → U5 SS54 | 24V 母线 | `SCH/电源/CN1`, `U5` |
| VCC+12V | U4 XL1509-12 降压 | 12V | `SCH/电源/U4` |
| USB+5V | U2 LM2596S-5.0 降压 / USB-C VBUS | 5V | `SCH/电源/U2`, `USB1` |
| VCC+5V | U6 拨动开关 + U7 PTC | 5V 受控 | `SCH/电源/U6`, `U7` |
| VCC+3.3V | U3 AMS1117-3.3 | 3.3V | `SCH/电源/U3` |
| 输出 | CN2 / CN3 XT30（24V / 12V） | 外部供电 | 文本标签「24V输出」「12V输出」 |

- 输入范围 / 最大电流：未知。CN1/CN2/CN3 均为 XT30UPB，BOM 标 Rated current=15A / 500VDC；板上 24V 走线 50mil（1.27mm），实际载流能力远低于连接器额定（`explicit` 连接器额定 / `inferred` 载流）
- 上下电顺序：未知
- 已知电源风险：USB+5V 与 USB-C VBUS 直连（F-004）；3.3V 输出无大容量储能（F-005）；U7 PTC 保持电流 50mA（F-006）

## 3. 接口

| 连接器 | 对端 | 线序 | 电平 | 依据 |
|---|---|---|---|---|
| CN1 XT30 2P | 24V 电源 | 1=GND, 2=+24V | 24V | `SCH/电源/CN1` |
| CN2 XT30 2P | 24V 负载 | 1=+, 2=− | 24V | 文本「24V输出」 |
| CN3 XT30 2P | 12V 负载 | 1=+, 2=− | 12V | 文本「12V输出」 |
| USB1 USB-C 16P | USB 主机 / 5V 源 | VBUS/GND/D±/CC | 5V | `SCH/接口/USB1` |
| DBUS1 MX1.25 3P | 外部单总线设备 | 1=5V, 2=DBUS, 3=GND | 5V 开集 | `SCH/接口/DBUS1` |
| USART1 XH2.54-4P | 串口 | 1=3.3V, 2=PA9(TX), 3=PA10(RX), 4=GND | 3.3V | `SCH/接口/USART1` |
| SWD1 MX1.25 4P | 调试器 | 1=3.3V, 2=SWDIO, 3=SWCLK, 4=GND | 3.3V | `SCH/接口/SWD1` |
| H2 / H3 2.54 排针 | 扩展 | 见网表 | 3.3V/5V | `SCH/主控/H2`, `H3` |
| H1 6P | BOOT 配置 | 3/4=BOOT0/BOOT1 | 3.3V | `SCH/主控/H1` |

- 外部暴露 / 可接触：全部连接器均可能外露；无隔离（`inferred`）
- USB-C 角色：R3/R4 5.1K 下拉 = sink（受电）角色（`explicit`，USB-C 规范）

## 4. 关键器件

| 位号 | MPN | 封装 | 来源 |
|---|---|---|---|
| U1 | STM32F103C8T6 | LQFP48 | BOM（有 MPN/LCSC） |
| U2 | LM2596S-5.0（Slkor） | TO-263-5 | BOM + 封装名 `TO-263-5_L10.1-W8.7-P1.70-LS14.4-BR` |
| U3 | AMS1117-3.3 | SOT-223 | BOM |
| U4 | XL1509-12E1（XLSEMI） | SOIC-8 | BOM；供应商封装写 SOIC-8 |
| U5/U9/U10 | SS54 | SMA（供应商封装字段写 `(1N5824)DO-214`） | BOM；封装名 `SMA_L4.2-W2.6-LS5.1-RD`，不一致见 F-013 |
| U6 | YSSP2AG00 | SMD 6P 拨动 | BOM |
| U7 | JK-nSMD005/60V | 1206 PTC | BOM |
| U8 | CH340C | SOP-16 | BOM |
| USB1 | HCTL HC-TYPE-C-16P-01B | 16P SMD | BOM |
| X1 | X322516MLB4SI 16MHz | 3225 | BOM |
| X2 | CM7V-T1A-...-12.5PF | 3215 | BOM |

- 替代料 / DNP / 变体：未知

## 5. 环境、标准、制造

- 温度 / 振动 / 防护 / 安规：未知
- EMC 目标 / 标准 / 预测试：未知
- 板厂：DRC 规则名 `JLCPCB Capability(Two Layers Board)`（`explicit`，规则文件）
- 层数 / 板厚 / 阻抗 / 装配面 / 批量：2 层（`explicit`，层列表）；板厚/阻抗/批量未知

## 6. 本次关注点

- 未指定。按审核清单全项扫，重点落在电气连接、电源、接口保护。
- 不审模块：无

## 7. 待人工确认

1. 板子实际用途与负载（决定 F-006 PTC、F-016 线宽是否成立）
2. CN2/CN3 是输出还是输入（本轮按文本标签判为输出）
3. USB-C 是仅受电，还是要给外部供电（决定 F-004 的性质）
4. 24V 输入的实际功率 / 电流
5. 是否有 EMC / 安规要求
6. BOOT0/BOOT1 是否需要用跳线帽常态短接
7. U6 拨动开关的实际型号与引脚定义（COM 在哪一脚）
