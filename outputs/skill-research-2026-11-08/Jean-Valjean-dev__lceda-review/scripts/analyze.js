#!/usr/bin/env node
/**
 * lceda-review — schematic design review for EasyEDA / 嘉立创EDA Pro netlists.
 *
 * Input: a `.enet` netlist exported from EasyEDA Pro
 *        (SCH_ManufactureData.getNetlistFile() in the easyeda-api skill).
 * Output: a Markdown design-review report, or JSON with --json.
 *
 * No dependencies. Node >= 18.
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const GND_RE = /^(GND|AGND|DGND|PGND|SGND|GROUND|VSS|VSSA|0V|EARTH)$/i;
const POWER_RE =
  /^(VCC|VDD|VBAT|VIN|VUSB|VBUS|AVDD|DVDD|VREF|V\+|\+\d|\d+V\d*|V\d+V\d|3V3|5V|12V|1V8|2V5|P3V3|P5V)/i;
const CONNECTOR_RE = /^(USB|J|CN|CON|DC|P\d|XH|PH)/;
const PROTECTION_RE = /(TVS|ESD|PESD|SMF|SMAJ|SMBJ|SMCJ|SRV05|USBLC6|PRTR5V|TPD\d|ESDA|FUSE|MF-MSMF|PTC|0Z)/i;
const REGULATOR_RE =
  /(AMS1117|LM1117|LM317|LM7805|7805|7905|TPS\d{4}|MP2\d{3}|RT\d{4}|XC6\d{3}|LM2596|SY8\d{2}|SPX\d{4}|ME6211|HT7\d{3}|AP2112|MIC5219)/i;

const VALUE_MULT = { p: 1e-12, n: 1e-9, u: 1e-6, µ: 1e-6, m: 1e-3, '': 1, k: 1e3, K: 1e3, M: 1e6, G: 1e9, R: 1, E: 1 };

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

function loadNetlist(file) {
  const raw = fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, '');
  let json;
  try {
    json = JSON.parse(raw);
  } catch (err) {
    throw new Error(`not a valid EasyEDA netlist (${err.message})`);
  }
  if (!json.components || typeof json.components !== 'object') {
    throw new Error('netlist has no "components" section');
  }
  return json;
}

// ---------------------------------------------------------------------------
// Model
// ---------------------------------------------------------------------------

function buildModel(json) {
  const components = [];
  const nets = new Map();

  for (const [id, raw] of Object.entries(json.components)) {
    const props = raw.props || {};
    const ref = (props.Designator || raw.Designator || id).trim();
    const pins = [];
    for (const [num, p] of Object.entries(raw.pinInfoMap || {})) {
      pins.push({
        number: String(p.number ?? num),
        name: String(p.name ?? ''),
        net: String(p.net ?? '').trim(),
      });
    }
    const comp = {
      id,
      ref,
      prefix: (ref.match(/^[A-Za-z_]+/) || [''])[0].toUpperCase(),
      value: String(props.Value ?? '').trim(),
      device: String(props.DeviceName ?? props['LCSC Part Name'] ?? '').trim(),
      footprint: String(props.FootprintName ?? props['Supplier Footprint'] ?? '').trim(),
      lcsc: String(props['Supplier Part'] ?? '').trim(),
      mfr: String(props['Manufacturer Part'] ?? '').trim(),
      datasheet: String(props.Datasheet ?? '').trim(),
      inBom: (props['Add into BOM'] || 'yes').toLowerCase() !== 'no',
      toPcb: (props['Convert to PCB'] || 'yes').toLowerCase() !== 'no',
      has3d: Boolean(String(props['3D Model'] ?? '').trim()),
      props,
      pins,
      meta: {
        loadCapacitance: parseCapacitance(props['Load Capacitance']),
        outputVoltage: parseVoltage(props['Output Voltage']),
      },
      isConnector: CONNECTOR_RE.test(ref),
      isPassive: /^(R|C|L)$/.test((ref.match(/^[A-Za-z_]+/) || [''])[0].toUpperCase()),
      isIC: /^(U|IC)\d/.test(ref),
      isProtection: PROTECTION_RE.test(`${ref} ${props.DeviceName || ''} ${props.Value || ''} ${props['LCSC Part Name'] || ''}`),
      isRegulator:
        REGULATOR_RE.test(`${ref} ${props.DeviceName || ''} ${props['LCSC Part Name'] || ''} ${props.Value || ''}`) ||
        Boolean(props['Output Voltage']),
    };
    components.push(comp);

    for (const pin of pins) {
      if (!pin.net) continue;
      if (!nets.has(pin.net)) nets.set(pin.net, []);
      nets.get(pin.net).push({ ref, pin: pin.number, pinName: pin.name, comp });
    }
  }

  // sort nets by pin count for stable output
  const netList = [...nets.entries()]
    .map(([name, pins]) => ({ name, pins, count: pins.length }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));

  return {
    projectId: json.projectId || '',
    version: json.version || '',
    components,
    nets,
    netList,
    designRule: json.designRule || {},
    byRef: new Map(components.map((c) => [c.ref, c])),
  };
}

// ---------------------------------------------------------------------------
// Value parsing
// ---------------------------------------------------------------------------

function parsePassive(str) {
  // "10k", "4.7K", "100nF", "10UF", "47pF", "5.1", "0R", "1M", "2.2uF 25V"
  if (!str) return null;
  const s = String(str).trim().replace(/,/g, '.');
  const m = s.match(/^([0-9]*\.?[0-9]+)\s*([pnuµmkKMGR]?)\s*(F|Ω|R|ohm|OHM|H)?/);
  if (!m) return null;
  const num = parseFloat(m[1]);
  if (!Number.isFinite(num)) return null;
  const prefix = m[2] || '';
  const unitChar = (m[3] || '').toUpperCase();
  let kind = 'unknown';
  if (unitChar === 'F' || /[pnuµ]/.test(prefix) || /\d\s*(nF|uF|pF|µF)/i.test(s)) kind = 'C';
  else if (unitChar === 'H') kind = 'L';
  else kind = 'R';
  if (/^(R|C|L)$/.test(prefix) && kind === 'R' && prefix === 'R') return { kind: 'R', value: num, raw: s };
  const mult = VALUE_MULT[prefix] ?? 1;
  return { kind, value: num * mult, raw: s, prefix };
}

function parseCapacitance(str) {
  if (!str) return null;
  const m = String(str).match(/([0-9]*\.?[0-9]+)\s*([pnuµm]?)\s*F/i);
  if (!m) return null;
  return parseFloat(m[1]) * (VALUE_MULT[m[2].toLowerCase()] ?? 1);
}

function parseVoltage(str) {
  if (!str) return null;
  const m = String(str).match(/([0-9]*\.?[0-9]+)\s*V/i);
  return m ? parseFloat(m[1]) : null;
}

function fmtSi(v, unit) {
  if (v == null) return '?';
  const abs = Math.abs(v);
  const table = [
    [1e6, 'M'],
    [1e3, 'k'],
    [1, ''],
    [1e-3, 'm'],
    [1e-6, 'u'],
    [1e-9, 'n'],
    [1e-12, 'p'],
  ];
  for (const [scale, suffix] of table) {
    if (abs >= scale || scale === 1e-12) {
      const n = v / scale;
      return `${Number(n.toFixed(n < 10 ? 2 : 1))}${suffix}${unit}`;
    }
  }
  return `${v}${unit}`;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function capsOnRail(model, rail, gndSet = GND_RE) {
  const caps = [];
  const net = model.nets.get(rail);
  if (!net) return caps;
  for (const p of net) {
    if (!/^C/.test(p.ref)) continue;
    const comp = p.comp;
    const other = comp.pins.find((x) => x.net && x.net !== rail);
    if (!other) continue;
    if (gndSet.test(other.net)) caps.push(comp);
  }
  return caps;
}

function totalCapacitance(caps) {
  let total = 0;
  for (const c of caps) {
    const v = parseCapacitance(c.value);
    if (v) total += v;
  }
  return total;
}

function isPowerNet(name) {
  return POWER_RE.test(name) || GND_RE.test(name);
}

function canonicalNet(name) {
  return String(name)
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[+]/g, '')
    .replace(/^(vcc|vdd|vbat)(?=\d)/, '')
    .replace(/(voltage|power|rail)/g, '');
}

// ---------------------------------------------------------------------------
// Checks
// ---------------------------------------------------------------------------

function checkComponentIntegrity(model) {
  const findings = [];
  const missingValue = model.components.filter(
    (c) => !c.value && (['R', 'C', 'L'].includes(c.prefix) || /^(LED|D)\d/.test(c.ref) || /^LED/.test(c.ref))
  );
  if (missingValue.length) {
    findings.push({
      id: 'value-missing',
      severity: 'warn',
      title: '器件缺少值（Value）',
      detail: 'R/C/L/LED 没有填值，BOM 分组、DRC 和后续选型都会受影响。',
      items: missingValue.map((c) => `${c.ref} (${c.device || '—'})`),
    });
  }

  const missingLcsc = model.components.filter((c) => c.inBom && !c.lcsc);
  if (missingLcsc.length) {
    findings.push({
      id: 'lcsc-missing',
      severity: 'warn',
      title: '器件缺少 LCSC 编号',
      detail: '下单时无法自动匹配料号，SMT 会卡住。',
      items: missingLcsc.map((c) => `${c.ref} (${c.value || c.device || '—'})`),
    });
  }

  const missingFootprint = model.components.filter((c) => c.toPcb && !c.footprint);
  if (missingFootprint.length) {
    findings.push({
      id: 'footprint-missing',
      severity: 'error',
      title: '器件缺少封装',
      detail: '无法导入 PCB，原理图转 PCB 会失败。',
      items: missingFootprint.map((c) => c.ref),
    });
  }

  const noPcb = model.components.filter((c) => !c.toPcb);
  if (noPcb.length) {
    findings.push({
      id: 'not-to-pcb',
      severity: 'info',
      title: '器件标记为不转 PCB',
      detail: '确认这些是有意为之（测试点、标记等）。',
      items: noPcb.map((c) => c.ref),
    });
  }

  // duplicate designators
  const seen = new Map();
  const dupes = [];
  for (const c of model.components) {
    if (seen.has(c.ref)) dupes.push(c.ref);
    else seen.set(c.ref, true);
  }
  if (dupes.length) {
    findings.push({
      id: 'ref-duplicate',
      severity: 'error',
      title: '位号重复',
      detail: '同一位号出现多次，网表和 BOM 都会错乱。',
      items: [...new Set(dupes)],
    });
  }

  // value casing / notation consistency inside one prefix
  const byPrefix = new Map();
  for (const c of model.components) {
    if (!c.value) continue;
    const key = c.value.replace(/\s+/g, '').toLowerCase();
    if (!byPrefix.has(c.prefix)) byPrefix.set(c.prefix, new Map());
    const m = byPrefix.get(c.prefix);
    if (!m.has(key)) m.set(key, new Set());
    m.get(key).add(c.value);
  }
  const inconsistent = [];
  for (const [prefix, variants] of byPrefix) {
    for (const [, spellings] of variants) {
      if (spellings.size > 1) {
        inconsistent.push(`${prefix}: ${[...spellings].join(' / ')}（会被 BOM 当成不同料）`);
      }
    }
  }
  if (inconsistent.length) {
    findings.push({
      id: 'value-notation',
      severity: 'info',
      title: '同类器件值写法不统一',
      detail: '10k 与 10K 会被 BOM 当成两种料，建议统一大小写。',
      items: inconsistent,
    });
  }

  return findings;
}

function checkNetHealth(model) {
  const findings = [];

  const single = model.netList.filter((n) => n.count === 1);
  if (single.length) {
    findings.push({
      id: 'net-single-pin',
      severity: 'warn',
      title: '单点网络（只有一个引脚）',
      detail: '通常是漏连、悬空引脚或忘了放测试点。',
      items: single.map((n) => `${n.name} → ${n.pins[0].ref}.${n.pins[0].pin}`),
    });
  }

  const emptyPins = [];
  for (const c of model.components) {
    for (const p of c.pins) if (!p.net) emptyPins.push(`${c.ref}.${p.number}${p.name ? '(' + p.name + ')' : ''}`);
  }
  if (emptyPins.length) {
    findings.push({
      id: 'pin-no-net',
      severity: 'info',
      title: '引脚未连接任何网络',
      detail: '确认是有意的（NC 引脚）还是漏画。',
      items: emptyPins.slice(0, 40),
    });
  }

  // near-duplicate power rails: canonical names collide but nets are separate
  const groups = new Map();
  for (const n of model.netList) {
    if (!isPowerNet(n.name)) continue;
    const key = canonicalNet(n.name).replace(/[^a-z0-9.]/g, '');
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(n);
  }
  const collisions = [];
  for (const [, list] of groups) {
    if (list.length > 1) {
      collisions.push(list.map((n) => `${n.name} (${n.count} pin)`).join('  vs  '));
    }
  }
  if (collisions.length) {
    findings.push({
      id: 'net-rail-collision',
      severity: 'error',
      title: '疑似重复的电源网络',
      detail: '名字几乎一样但是两个独立网络，很可能有一半的电源没连上。',
      items: collisions,
    });
  }

  const odd = model.netList.filter((n) => /[\s\t]/.test(n.name));
  if (odd.length) {
    findings.push({
      id: 'net-odd-name',
      severity: 'info',
      title: '网络名含空格',
      detail: '空格在网表、脚本和导出文件里都容易出问题，建议改成下划线。',
      items: odd.map((n) => JSON.stringify(n.name)),
    });
  }

  return findings;
}

function checkDecoupling(model) {
  const findings = [];
  const icPins = [];

  for (const c of model.components) {
    if (!c.isIC || c.isConnector) continue;
    const powerPins = c.pins.filter((p) => p.net && !GND_RE.test(p.net) && (POWER_RE.test(p.net) || /^(VCC|VDD|AVDD|DVDD|VIN|VBAT|VREF)/i.test(p.name)));
    if (!powerPins.length) continue;
    icPins.push({ comp: c, powerPins });
  }

  const problems = [];
  const ok = [];
  for (const { comp, powerPins } of icPins) {
    for (const p of powerPins) {
      const caps = capsOnRail(model, p.net);
      const total = totalCapacitance(caps);
      if (!caps.length) {
        problems.push(`${comp.ref}.${p.number} (${p.name || p.net}) @ ${p.net}: 无去耦电容`);
      } else if (total < 90e-9) {
        problems.push(`${comp.ref}.${p.number} (${p.name || p.net}) @ ${p.net}: 容量偏小 ${fmtSi(total, 'F')}（建议 ≥100nF）`);
      } else {
        ok.push(`${comp.ref} @ ${p.net}: ${caps.map((c) => `${c.ref}=${c.value}`).join(' + ')}（共 ${fmtSi(total, 'F')}）`);
      }
    }
  }

  if (problems.length) {
    findings.push({
      id: 'decoupling-missing',
      severity: 'warn',
      title: 'IC 电源脚去耦不足',
      detail: '每个电源引脚应就近有 ≥100nF 对地电容，大电流器件再加 1~10µF。',
      items: problems,
    });
  }
  if (ok.length) {
    findings.push({
      id: 'decoupling-ok',
      severity: 'info',
      title: '去耦电容已覆盖',
      detail: '这些 IC 电源脚都有对地电容。',
      items: ok,
    });
  }
  return findings;
}

function checkPowerTree(model) {
  const findings = [];
  const regs = model.components.filter((c) => c.isRegulator);
  const tree = [];

  for (const r of regs) {
    const rails = [...new Set(r.pins.filter((p) => p.net && !GND_RE.test(p.net)).map((p) => p.net))];
    if (!rails.length) continue;
    const declared = r.meta.outputVoltage;
    const rows = rails.map((rail) => {
      const caps = capsOnRail(model, rail);
      return {
        rail,
        pins: model.nets.get(rail)?.length ?? 0,
        caps: caps.map((c) => `${c.ref}=${c.value}`).join(' + ') || '—',
        total: totalCapacitance(caps),
      };
    });
    const outRail =
      rails.find((x) => /\d+V\d|3V3|1V8|2V5/i.test(x)) ||
      rails.find((x) => !/^(VIN|VBUS|VUSB|\+5V|5V|VCC)$/i.test(x)) ||
      rails[0];

    tree.push({ reg: r, declared, rows, outRail });

    const outCaps = capsOnRail(model, outRail);
    if (!outCaps.length) {
      findings.push({
        id: 'reg-no-output-cap',
        severity: 'warn',
        title: `${r.ref} 输出无电容`,
        detail: `稳压输出 ${outRail} 上没有找到对地电容，LDO/DCDC 会振荡。`,
        items: [`${r.ref} (${r.device || r.value}) → ${outRail}`],
      });
    }
    const inRail = rails.find((x) => x !== outRail && isPowerNet(x));
    if (inRail && !capsOnRail(model, inRail).length) {
      findings.push({
        id: 'reg-no-input-cap',
        severity: 'info',
        title: `${r.ref} 输入无电容`,
        detail: `输入网络 ${inRail} 上没有对地电容，建议放 1~10µF。`,
        items: [`${r.ref} (${r.device || r.value}) → ${inRail}`],
      });
    }
  }

  if (tree.length) {
    findings.push({
      id: 'power-tree',
      severity: 'info',
      title: '电源树',
      detail: '识别到的稳压器及其输入/输出网络。',
      tree,
    });
  }

  // resistor dividers: a net with exactly two resistors and at least one other pin
  const dividers = [];
  for (const n of model.netList) {
    const resistors = n.pins.filter((p) => /^R/.test(p.ref));
    const others = n.pins.filter((p) => !/^R/.test(p.ref));
    if (resistors.length === 2 && others.length >= 1 && n.count <= 5) {
      const [a, b] = resistors.map((p) => parsePassive(p.comp.value)).filter(Boolean);
      if (a && b) {
        const ratio = b.value / (a.value + b.value);
        dividers.push({
          net: n.name,
          refs: resistors.map((p) => `${p.ref}=${p.comp.value}`).join(' / '),
          ratio: Number.isFinite(ratio) ? ratio.toFixed(3) : '?',
          loads: others.map((p) => `${p.ref}.${p.pin}${p.pinName ? '(' + p.pinName + ')' : ''}`).join(', '),
        });
      }
    }
  }
  if (dividers.length) {
    findings.push({
      id: 'dividers',
      severity: 'info',
      title: '分压 / 反馈网络',
      detail: '两个电阻 + 一个负载引脚，ratio = 下臂/(上臂+下臂)。',
      dividers,
    });
  }

  return findings;
}

function checkProtection(model) {
  const findings = [];
  const connectors = model.components.filter((c) => c.isConnector || /^(USB|J|CN|CON|DC)$/.test(c.prefix));
  const unaudited = [];

  for (const conn of connectors) {
    const signalNets = [
      ...new Set(conn.pins.filter((p) => p.net && !GND_RE.test(p.net) && !isPowerNet(p.net)).map((p) => p.net)),
    ];
    if (!signalNets.length) continue;
    const unprotected = [];
    for (const net of signalNets) {
      const others = (model.nets.get(net) || []).filter((p) => p.comp !== conn);
      const guarded = others.some((p) => p.comp.isProtection || /^F/.test(p.ref));
      if (!guarded) unprotected.push(net);
    }
    if (unprotected.length) {
      unaudited.push(`${conn.ref} (${conn.device || conn.value || 'connector'}): ${unprotected.length}/${signalNets.length} 个信号无保护 → ${unprotected.slice(0, 6).join(', ')}`);
    }
  }

  if (unaudited.length) {
    findings.push({
      id: 'esd-missing',
      severity: 'warn',
      title: '外部连接器缺少 ESD / 限流保护',
      detail: '对外暴露的信号建议加 TVS/ESD 或串联保险丝，尤其 USB 和对外排针。',
      items: unaudited,
    });
  }
  return findings;
}

function checkLeds(model) {
  const findings = [];
  const bad = [];
  for (const led of model.components.filter((c) => /^LED/.test(c.ref))) {
    const nets = [...new Set(led.pins.filter((p) => p.net && !GND_RE.test(p.net)).map((p) => p.net))];
    if (!nets.length) continue;

    const railNets = nets.filter((n) => isPowerNet(n));
    const signalNets = nets.filter((n) => !isPowerNet(n));
    let hasSeriesR = false;

    for (const net of nets) {
      for (const p of model.nets.get(net) || []) {
        if (!/^R/.test(p.ref) || p.comp === led) continue;
        const other = p.comp.pins.find((x) => x.net && x.net !== net);
        if (!other || !other.net) continue;
        if (railNets.includes(net)) {
          // 电阻在电源侧：另一端必须正好是 LED 的另一个脚，才算串联
          if (signalNets.includes(other.net)) hasSeriesR = true;
        } else if (!isPowerNet(other.net) && !GND_RE.test(other.net)) {
          // 电阻在信号侧：另一端接到驱动源（非电源、非地）
          hasSeriesR = true;
        }
      }
    }

    if (!hasSeriesR) bad.push(`${led.ref} (${led.value || led.device || 'LED'}) @ ${nets.join(', ')}`);
  }
  if (bad.length) {
    findings.push({
      id: 'led-no-resistor',
      severity: 'error',
      title: 'LED 没有串联限流电阻',
      detail: '直接接电源或驱动脚会烧 LED，也可能损坏 MCU 引脚。',
      items: bad,
    });
  }
  return findings;
}

function checkCrystals(model) {
  const findings = [];
  const rows = [];
  for (const c of model.components) {
    const looksCrystal = /(MHZ|XTAL|CRYSTAL|ABLS|HC-49)/i.test(`${c.device} ${c.value}`) || c.meta.loadCapacitance != null;
    if (!looksCrystal) continue;
    const nets = [...new Set(c.pins.filter((p) => p.net).map((p) => p.net))];
    const caps = [];
    for (const net of nets) {
      for (const p of model.nets.get(net) || []) {
        if (/^C/.test(p.ref) && !caps.includes(p.comp)) {
          const other = p.comp.pins.find((x) => x.net && x.net !== net);
          if (other && GND_RE.test(other.net)) caps.push(p.comp);
        }
      }
    }
    if (caps.length < 2) {
      findings.push({
        id: 'crystal-caps',
        severity: 'warn',
        title: `${c.ref} 晶振负载电容不足`,
        detail: '晶振两端一般各需要一个对地电容。',
        items: [`${c.ref} (${c.device || c.value}): 找到 ${caps.length} 个`],
      });
      continue;
    }
    const [c1, c2] = caps.slice(0, 2).map((x) => parseCapacitance(x.value));
    if (c1 && c2) {
      const cl = (c1 * c2) / (c1 + c2) + 3e-12; // +3pF stray
      const target = c.meta.loadCapacitance;
      rows.push({
        ref: c.ref,
        device: c.device || c.value,
        caps: caps.map((x) => `${x.ref}=${x.value}`).join(' + '),
        computed: fmtSi(cl, 'F'),
        target: target ? fmtSi(target, 'F') : '—',
        verdict: target ? (Math.abs(cl - target) / target > 0.3 ? '偏差 >30%' : 'ok') : '未声明',
      });
    }
  }
  if (rows.length) {
    const off = rows.filter((r) => String(r.verdict).includes('偏差'));
    findings.push({
      id: off.length ? 'crystal-load-off' : 'crystal-load',
      severity: off.length ? 'warn' : 'info',
      title: off.length ? '晶振负载电容与器件标称不符' : '晶振负载电容校验',
      detail: 'CL ≈ C1·C2/(C1+C2) + 3pF 杂散；偏差过大会导致频偏或起振困难。',
      ...(off.length ? { items: off.map((r) => `${r.ref} (${r.device}): 计算 ${r.computed}，标称 ${r.target}，${r.verdict}`) } : {}),
      table: rows,
    });
  }
  return findings;
}

function checkRules(model) {
  const findings = [];
  const rule = model.designRule || {};
  const keys = Object.keys(rule);
  if (!keys.length) {
    findings.push({
      id: 'no-design-rule',
      severity: 'info',
      title: '网表里没有设计规则',
      detail: '线宽/间距可能在 PCB 侧才定义，确认已设置最小线宽和间距。',
      items: [],
    });
    return findings;
  }
  const physics = rule.trackPhysics;
  if (Array.isArray(physics) && physics.length) {
    const widths = physics.map((p) => p.width ?? p.Width).filter((x) => typeof x === 'number');
    const min = Math.min(...widths);
    if (Number.isFinite(min) && min < 0.15) {
      findings.push({
        id: 'rule-thin-track',
        severity: 'warn',
        title: '最小线宽过细',
        detail: `最小线宽 ${min}mm，普通板厂 0.15mm 以下要加钱或做不了。`,
        items: widths.map((w) => `${w}mm`),
      });
    }
  }
  return findings;
}

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------

const CHECK_GROUPS = [
  { key: 'integrity', label: '器件完整性', covers: '值 / LCSC / 封装 / 位号重复 / 写法一致' },
  { key: 'nets', label: '网络体检', covers: '单点网络、空引脚、重复电源网络、命名' },
  { key: 'decoupling', label: '去耦检查', covers: 'IC 电源脚对地电容数量与容量' },
  { key: 'power', label: '电源树', covers: '稳压器输入/输出电容、分压网络比例' },
  { key: 'protection', label: 'ESD / 保护', covers: '对外连接器是否有 TVS/保险丝' },
  { key: 'led', label: 'LED 限流', covers: 'LED 是否串了限流电阻' },
  { key: 'crystal', label: '晶振负载电容', covers: 'CL 计算与器件声明值对比' },
  { key: 'rules', label: '设计规则', covers: '最小线宽等板级规则' },
];

function groupOf(id) {
  if (/^(value-missing|lcsc-missing|footprint-missing|not-to-pcb|ref-duplicate|value-notation)$/.test(id)) return 'integrity';
  if (/^net-/.test(id)) return 'nets';
  if (/^decoupling/.test(id)) return 'decoupling';
  if (/^(power-tree|dividers|reg-)/.test(id)) return 'power';
  if (/^esd/.test(id)) return 'protection';
  if (/^led/.test(id)) return 'led';
  if (/^crystal/.test(id)) return 'crystal';
  if (/^(no-design-rule|rule-)/.test(id)) return 'rules';
  return 'other';
}

function analyze(model) {
  const findings = [
    ...checkComponentIntegrity(model),
    ...checkNetHealth(model),
    ...checkDecoupling(model),
    ...checkPowerTree(model),
    ...checkProtection(model),
    ...checkLeds(model),
    ...checkCrystals(model),
    ...checkRules(model),
  ];

  const coverage = CHECK_GROUPS.map((g) => {
    const hits = findings.filter((f) => groupOf(f.id) === g.key);
    const issues = hits.filter((f) => f.severity !== 'info').length;
    return { ...g, hits: hits.length, issues, status: issues ? '发现问题' : '通过' };
  });

  const weight = { error: 8, warn: 3, info: 0 };
  const penalty = findings.reduce((sum, f) => sum + (weight[f.severity] || 0) * Math.max(1, Math.min(5, (f.items || []).length)), 0);
  const score = Math.max(0, 100 - penalty);
  const rating = score >= 85 ? 'READY' : score >= 60 ? 'NEEDS_WORK' : 'POOR';

  const counts = {
    components: model.components.length,
    nets: model.netList.length,
    errors: findings.filter((f) => f.severity === 'error').length,
    warnings: findings.filter((f) => f.severity === 'warn').length,
    infos: findings.filter((f) => f.severity === 'info').length,
  };

  const rails = model.netList.filter((n) => isPowerNet(n.name)).slice(0, 12);

  return { score, rating, counts, findings, rails, coverage, model };
}

function renderMarkdown(report, sourceName) {
  const { score, rating, counts, findings, rails, coverage, model } = report;
  const line = [];
  const icon = { error: '❌', warn: '⚠️', info: 'ℹ️' };

  line.push(`# 原理图审查报告 — ${sourceName}`);
  line.push('');
  line.push(`**评分：${score}/100 · ${rating}**  `);
  line.push(`器件 ${counts.components} · 网络 ${counts.nets} · 错误 ${counts.errors} · 警告 ${counts.warnings} · 提示 ${counts.infos}`);
  line.push('');

  if (rails.length) {
    line.push('## 电源网络');
    line.push('');
    line.push('| 网络 | 引脚数 | 电容 |');
    line.push('|---|---|---|');
    for (const r of rails) {
      const caps = capsOnRail(model, r.name);
      line.push(`| \`${r.name}\` | ${r.count} | ${caps.map((c) => `${c.ref}=${c.value}`).join(' + ') || '—'} |`);
    }
    line.push('');
  }

  for (const sev of ['error', 'warn', 'info']) {
    const group = findings.filter((f) => f.severity === sev);
    if (!group.length) continue;
    line.push(`## ${icon[sev]} ${sev === 'error' ? '错误' : sev === 'warn' ? '警告' : '提示'}（${group.length}）`);
    line.push('');
    for (const f of group) {
      line.push(`### ${f.title}`);
      line.push('');
      line.push(f.detail);
      if (f.items && f.items.length) {
        line.push('');
        for (const it of f.items.slice(0, 20)) line.push(`- ${it}`);
        if (f.items.length > 20) line.push(`- …还有 ${f.items.length - 20} 条`);
      }
      if (f.tree) {
        line.push('');
        line.push('| 稳压器 | 型号 | 声明输出 | 输出网络 | 输入网络 | 输出电容 |');
        line.push('|---|---|---|---|---|---|');
        for (const t of f.tree) {
          const out = t.rows.find((r) => r.rail === t.outRail) || t.rows[0];
          const inp = t.rows.find((r) => r.rail !== t.outRail);
          line.push(
            `| ${t.reg.ref} | ${t.reg.device || t.reg.value} | ${t.declared ? t.declared + 'V' : '—'} | \`${out?.rail}\` | ${inp ? '`' + inp.rail + '`' : '—'} | ${out?.caps || '—'} |`
          );
        }
      }
      if (f.table) {
        line.push('');
        const cols = Object.keys(f.table[0]);
        line.push('| ' + cols.join(' | ') + ' |');
        line.push('|' + cols.map(() => '---').join('|') + '|');
        for (const row of f.table) line.push('| ' + cols.map((c) => row[c]).join(' | ') + ' |');
      }
      line.push('');
    }
  }

  if (coverage && coverage.length) {
    line.push('## 检查覆盖');
    line.push('');
    line.push('| 检查项 | 覆盖内容 | 结论 |');
    line.push('|---|---|---|');
    for (const c of coverage) {
      line.push(`| ${c.label} | ${c.covers} | ${c.status} |`);
    }
    line.push('');
  }

  line.push('---');
  line.push('');
  line.push('由 lceda-review 生成 · 数据源：EasyEDA Pro `.enet` 网表');
  return line.join('\n');
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function main(argv) {
  const args = argv.slice(2);
  const flags = new Set(args.filter((a) => a.startsWith('--')));
  const files = args.filter((a) => !a.startsWith('--'));

  if (!files.length || flags.has('--help') || flags.has('-h')) {
    console.log(`lceda-review — schematic design review for EasyEDA / 嘉立创EDA Pro

Usage:
  node scripts/analyze.js <netlist.enet> [--json] [--out report.md]

Options:
  --json       print machine-readable JSON instead of Markdown
  --out <f>    also write the report to <f>
  --help       show this help
`);
    process.exit(files.length ? 0 : 1);
  }

  const file = files[0];
  if (!fs.existsSync(file)) {
    console.error(`file not found: ${file}`);
    process.exit(2);
  }

  const json = loadNetlist(file);
  const model = buildModel(json);
  const report = analyze(model);
  const sourceName = path.basename(file);

  if (flags.has('--json')) {
    const { model: _m, ...rest } = report;
    process.stdout.write(JSON.stringify({ source: sourceName, ...rest }, null, 2));
  } else {
    const md = renderMarkdown(report, sourceName);
    const outIdx = args.indexOf('--out');
    if (outIdx >= 0 && args[outIdx + 1]) {
      fs.writeFileSync(args[outIdx + 1], md, 'utf8');
      console.error(`report written to ${args[outIdx + 1]}`);
    } else {
      process.stdout.write(md + '\n');
    }
  }

  const exitCode = report.counts.errors > 0 ? 1 : 0;
  process.exitCode = exitCode;
}

if (require.main === module) {
  try {
    main(process.argv);
  } catch (err) {
    console.error(`lceda-review: ${err.message}`);
    process.exit(2);
  }
}

module.exports = { loadNetlist, buildModel, analyze, renderMarkdown };
