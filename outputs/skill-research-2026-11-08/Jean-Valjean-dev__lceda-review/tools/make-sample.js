#!/usr/bin/env node
/**
 * Generates examples/sample-board.enet — a deliberately imperfect synthetic board
 * used as a fixture and as the "what does the report look like" demo.
 *
 * Every pin/ net combination here is intentional; do not "fix" the mistakes,
 * they are what the checks are supposed to catch.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

let uid = 0;
const nextId = () => `gge${++uid}`;

function comp(designator, opts) {
  const {
    value = '',
    device = '',
    footprint = '',
    lcsc = '',
    pins = [],
    extra = {},
  } = opts;
  const props = {
    'Add into BOM': 'yes',
    'Convert to PCB': 'yes',
    Designator: designator,
    'Unique ID': nextId(),
    Value: value,
    DeviceName: device,
    FootprintName: footprint,
    'Supplier Part': lcsc,
    'Manufacturer Part': device,
    'LCSC Part Name': device,
    '3D Model': footprint ? 'model|lib' : '',
    ...extra,
  };
  const pinInfoMap = {};
  for (const [num, net, name] of pins) {
    pinInfoMap[String(num)] = { name: name || String(num), number: String(num), net, pinClass: '', pinDifferentialPairClass: '', props: { 'Pin Number': String(num) } };
  }
  return { props, altLibs: { devices: [], footprints: [] }, pinInfoMap };
}

const components = {};

components[nextId()] = comp('USB1', {
  device: 'TYPE-C-16P',
  footprint: 'TYPE-C-SMD_16P',
  lcsc: 'C165948',
  pins: [
    [1, '+5V', 'VBUS'],
    [2, '+5V', 'VBUS'],
    [3, 'GND', 'GND'],
    [4, 'USB_D+', 'D+'],
    [5, 'USB_D-', 'D-'],
  ],
});

components[nextId()] = comp('C1', {
  value: '10uF',
  device: 'C_0805',
  footprint: 'C0805',
  pins: [[1, '+5V'], [2, 'GND']],
});

components[nextId()] = comp('U1', {
  device: 'AMS1117-3.3',
  footprint: 'SOT-223-3_L6.5-W3.4-P2.30-LS7.0-TR',
  lcsc: 'C6186',
  pins: [[1, 'GND', 'GND/ADJ'], [2, '3V3', 'VOUT'], [3, '+5V', 'VIN']],
  extra: { 'Output Voltage': '3.3V', 'Voltage Dropout': '1.1V' },
});

components[nextId()] = comp('C2', {
  value: '100nF',
  device: 'C_0805',
  footprint: 'C0805',
  pins: [[1, '3V3'], [2, 'GND']],
});

components[nextId()] = comp('U2', {
  device: 'STM32F103C8T6',
  footprint: 'LQFP-48_L7.0-W7.0-P0.50-LS9.0-TL',
  lcsc: 'C8734',
  pins: [
    [1, 'VBAT_PIN', 'VBAT'],      // 单点网络：悬空
    [2, '3V3', 'VDD'],
    [3, 'GND', 'VSS'],
    [4, 'RST', 'NRST'],
    [5, 'XI', 'OSC_IN'],
    [6, 'XO', 'OSC_OUT'],
    [7, 'LED_K', 'PA0'],
    [8, 'USB_D+', 'PA11'],
    [9, 'USB_D-', 'PA12'],
  ],
});

components[nextId()] = comp('Y1', {
  value: '8MHz',
  device: 'ABLS-8.000MHZ-B4H-T',
  footprint: 'CRYSTAL-SMD_L11.4-W4.7',
  lcsc: 'C1973952',
  pins: [[1, 'XI'], [2, 'XO']],
  extra: { 'Load Capacitance': '18pF' },
});

components[nextId()] = comp('C3', { value: '47pF', device: 'C_0805', footprint: 'C0805', pins: [[1, 'XI'], [2, 'GND']] });
components[nextId()] = comp('C4', { value: '47pF', device: 'C_0805', footprint: 'C0805', pins: [[1, 'XO'], [2, 'GND']] });

// LED 直接接电源和 MCU 引脚，没有串阻
components[nextId()] = comp('LED1', {
  device: 'LED_0805',
  footprint: 'LED_0805',
  pins: [[1, '3V3', 'A'], [2, 'LED_K', 'K']],
});

// 排针：信号无保护
components[nextId()] = comp('J1', {
  device: 'HDR-M_2.54_1x04P',
  footprint: 'HDR-TH_4P-P2.54-V-M',
  lcsc: 'C2691448',
  pins: [[1, 'SIG_A'], [2, 'SIG_B'], [3, 'GND'], [4, 'VCC +5V']],
});

// 重复位号 + 缺 LCSC
components[nextId()] = comp('R1', { value: '10K', device: 'R_0805', footprint: 'R0805', pins: [[1, '3V3'], [2, 'RST']] });
components[nextId()] = comp('R1', { value: '10k', device: 'R_0805', footprint: 'R0805', pins: [[1, '3V3'], [2, 'SIG_A']] });

const netlist = {
  version: '2.0.0',
  projectId: 'sample-board',
  components,
  designRule: {
    trackPhysics: [{ width: 0.2, minWidth: 0.2 }, { width: 0.3, minWidth: 0.2 }],
    netRule: [],
  },
  differentialPair: [],
  netClass: [],
  equalLengthNetGroup: [],
  differentialPairGroups: [],
};

const out = path.join(__dirname, '..', 'examples', 'sample-board.enet');
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify(netlist, null, 2), 'utf8');
console.log(`wrote ${out} (${Object.keys(components).length} components)`);
