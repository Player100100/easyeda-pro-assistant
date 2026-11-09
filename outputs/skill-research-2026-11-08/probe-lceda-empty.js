// Reproduce the empty-netlist false-ready result without editing the candidate.
'use strict';

const path = require('node:path');
const candidate = path.join(__dirname, 'Jean-Valjean-dev__lceda-review');
const { buildModel, analyze } = require(path.join(candidate, 'scripts', 'analyze.js'));
const report = analyze(buildModel({ components: {} }));

console.log(JSON.stringify({
  score: report.score,
  rating: report.rating,
  counts: report.counts,
  coverage: report.coverage.map(({ key, status }) => ({ key, status })),
}, null, 2));
