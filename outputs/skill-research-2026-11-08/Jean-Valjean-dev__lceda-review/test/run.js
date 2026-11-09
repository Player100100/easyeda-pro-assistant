#!/usr/bin/env node
/**
 * Regression test: the fixture in examples/sample-board.enet is deliberately broken,
 * every check that should fire here must keep firing.
 */
'use strict';

const path = require('node:path');
const assert = require('node:assert');
const { loadNetlist, buildModel, analyze } = require('../scripts/analyze.js');

const fixture = path.join(__dirname, '..', 'examples', 'sample-board.enet');
const model = buildModel(loadNetlist(fixture));
const report = analyze(model);

const ids = new Set(report.findings.map((f) => f.id));
const cases = [
  ['ref-duplicate', '重复位号 R1'],
  ['net-rail-collision', '重复电源网络 +5V / VCC +5V'],
  ['net-single-pin', '单点网络'],
  ['value-missing', 'LED 缺少 Value'],
  ['lcsc-missing', '缺少 LCSC 料号'],
  ['decoupling-missing', 'U2 VBAT 无去耦'],
  ['esd-missing', 'USB/J1 无 ESD'],
  ['led-no-resistor', 'LED 无限流电阻'],
  ['crystal-load-off', '晶振负载电容偏差'],
  ['value-notation', '10K / 10k 写法不一致'],
];

let failed = 0;
for (const [id, label] of cases) {
  const ok = ids.has(id);
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${id.padEnd(22)} ${label}`);
  if (!ok) failed++;
}

// sanity: a clean-ish board should score higher than the broken one
assert.ok(report.counts.components === 12, `expected 12 components, got ${report.counts.components}`);
assert.ok(report.score < 60, `broken fixture should score POOR, got ${report.score}`);
assert.ok(report.rails.some((r) => r.name === '3V3'), '3V3 rail should be detected');
assert.ok(report.coverage.length === 8, `expected 8 coverage rows, got ${report.coverage.length}`);

if (failed) {
  console.error(`\n${failed} check(s) regressed`);
  process.exit(1);
}
console.log(`\nall ${cases.length} checks fired · score ${report.score} · ${report.rating}`);
