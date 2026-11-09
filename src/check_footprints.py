"""Read-only structural C-10 checker for extract.py output.

PASS only means the supplied reviewed baseline matches the extracted CAD data;
it does not prove that the baseline itself matches the manufacturer's document.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path


STATUSES = ("PASS", "FAIL", "REVIEW", "NOT_CHECKED", "NOT_APPLICABLE")
REQUIRED_BASELINE = ("source", "document", "page")


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _expectations(data):
    if not data:
        return {}
    rows = data.get("components", {})
    if not isinstance(rows, dict):
        raise ValueError("expectations.components must be an object keyed by designator")
    for ref, row in rows.items():
        if not isinstance(row, dict):
            raise ValueError(f"invalid expectation for {ref}")
        if "pads" in row:
            ids = []
            if not isinstance(row["pads"], list):
                raise ValueError(f"{ref}.pads must be a list")
            for pad in row["pads"]:
                if not isinstance(pad, dict) or not pad.get("pad_id") or "number" not in pad:
                    raise ValueError(f"{ref}: each expected pad requires pad_id and number (null allowed)")
                ids.append(str(pad["pad_id"]))
                for field in ("width", "height", "hole"):
                    if field + "_mil" in pad:
                        value = _number(pad[field + "_mil"])
                        tol = _number(pad.get(field + "_tolerance_mil"))
                        if value is None or value <= 0 or tol is None or tol < 0:
                            raise ValueError(f"{ref}/{pad['pad_id']}: positive dimension and explicit finite nonnegative tolerance required")
            if len(ids) != len(set(ids)):
                raise ValueError(f"{ref}: duplicate expected physical pad IDs")
        if "pin_map" in row and (not isinstance(row["pin_map"], dict) or
                                 any(v is None or isinstance(v, (list, dict))
                                     for v in row["pin_map"].values())):
            raise ValueError(f"{ref}.pin_map must map pin numbers to pad numbers")
    return {str(key): value for key, value in rows.items()}


def _baseline_error(exp):
    if not exp:
        return "no reviewed expectation supplied"
    evidence = exp.get("evidence") or {}
    missing = [field for field in REQUIRED_BASELINE if not evidence.get(field)]
    if missing:
        return "baseline evidence missing: " + ", ".join(missing)
    return None


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def check(pcb_data, schematic_data=None, expectations=None, pcb_id=None):
    if not isinstance(pcb_data, dict) or not isinstance(pcb_data.get("pcbs"), list):
        raise ValueError("expected extract.py pcb.json (API netlists have no physical pad inventory)")
    pcbs = pcb_data["pcbs"]
    if pcb_id:
        pcbs = [p for p in pcbs if p.get("uuid") == pcb_id]
        if len(pcbs) != 1:
            raise ValueError("--pcb-id must identify exactly one PCB")
    elif len(pcbs) > 1:
        raise ValueError("multiple PCBs: use --pcb-id; designators cannot be merged across boards")
    if schematic_data is not None and (not isinstance(schematic_data, dict) or
                                       not isinstance(schematic_data.get("pages"), list)):
        raise ValueError("expected extract.py schematic.json")
    expected = _expectations(expectations)
    refs = [str(c.get("designator")) for p in pcbs for c in p.get("components", [])
            if c.get("designator")]
    if len(refs) != len(set(refs)):
        raise ValueError("duplicate PCB designators: baseline matching is ambiguous")
    if set(expected) - set(refs):
        raise ValueError("baseline contains unknown designators: " + ", ".join(sorted(set(expected) - set(refs))))
    schematic_by_ref = {}
    for page in (schematic_data or {}).get("pages", []):
        for comp in page.get("components", []):
            if comp.get("designator"):
                schematic_by_ref.setdefault(str(comp["designator"]), []).append(comp)

    instances = []
    for pcb in pcbs:
        footprints = pcb_data.get("footprints", {})
        for comp in pcb.get("components", []):
            ref = str(comp.get("designator") or comp.get("id") or "<unknown>")
            exp = expected.get(ref)
            baseline_error = _baseline_error(exp)
            pads = comp.get("pads") or []
            fp = footprints.get(comp.get("footprint"), {})
            checks = {}

            if not comp.get("footprint") or not fp:
                checks["C-10.1"] = {"status": "REVIEW", "reason": "PCB footprint reference/definition missing; check extraction completeness"}
            elif baseline_error:
                checks["C-10.1"] = {"status": "NOT_CHECKED", "reason": baseline_error}
            else:
                attrs = {}
                for sch in schematic_by_ref.get(ref, []):
                    dev = (schematic_data or {}).get("devices", {}).get(sch.get("device"), {})
                    attrs.update(dev.get("attributes") or {})
                    attrs.update({k: v for k, v in (sch.get("attrs") or {}).items() if v is not None})
                attrs.update({k: v for k, v in (comp.get("attrs") or {}).items() if v is not None})
                actual_mpn = next((attrs.get(k) for k in
                                   ("Manufacturer Part", "Manufacturer Part Number", "MPN")
                                   if attrs.get(k)), None)
                mismatches = []
                comparisons = []
                unavailable = []
                for field, actual in (("mpn", actual_mpn),
                                      ("footprint_uuid", comp.get("footprint")),
                                      ("footprint_title", comp.get("footprint_title"))):
                    wanted = exp.get(field)
                    if wanted is not None:
                        if actual is None:
                            unavailable.append(field)
                        elif str(actual) != str(wanted):
                            mismatches.append({"field": field, "expected": wanted, "actual": actual})
                        comparisons.append({"field": field, "expected": wanted, "actual": actual})
                checks["C-10.1"] = {"status": "FAIL" if mismatches else
                                    "NOT_CHECKED" if unavailable or not comparisons else "PASS",
                                    "mismatches": mismatches, "actual_mpn": actual_mpn,
                                    "comparisons": comparisons, "unavailable": unavailable,
                                    "baseline_evidence": exp["evidence"]}

            sch = schematic_by_ref.get(ref, [])
            pin_map = (exp or {}).get("pin_map")
            if baseline_error or not pin_map or len(sch) != 1:
                checks["C-10.2"] = {"status": "NOT_CHECKED",
                                    "reason": baseline_error or
                                    "reviewed pin_map and exactly one matching schematic component are required"}
            else:
                sch_pins = Counter(str(pin["number"]) for item in sch for pin in item.get("pins", [])
                                   if pin.get("number") is not None)
                actual_nums = Counter(str(pad["num"]) for pad in pads if pad.get("num") is not None)
                missing = []
                for sch_pin, pad_num in pin_map.items():
                    sch_pin, pad_num = str(sch_pin), str(pad_num)
                    if sch_pins[sch_pin] == 0 or actual_nums[pad_num] == 0:
                        missing.append({"schematic_pin": sch_pin, "pcb_pad_number": pad_num,
                                        "schematic_pin_exists": sch_pins[sch_pin] > 0,
                                        "pcb_pad_number_exists": actual_nums[pad_num] > 0})
                unmapped = sorted(set(sch_pins) - {str(pin) for pin in pin_map})
                if not pads and comp.get("footprint") and fp:
                    checks["C-10.2"] = {"status": "REVIEW", "mapping_existence": "REVIEW",
                                        "reason": "footprint definition has no extracted instance pads; check extraction/data completeness",
                                        "missing": missing, "unmapped_schematic_pins": unmapped}
                elif unmapped:
                    checks["C-10.2"] = {"status": "NOT_CHECKED", "mapping_existence":
                                        "FAIL" if missing else "PASS",
                                        "reason": "pin_map does not declare every schematic pin",
                                        "mapping": [{"schematic_pin": str(k), "pcb_pad_number": str(v)}
                                                    for k, v in pin_map.items()],
                                        "missing": missing, "unmapped_schematic_pins": unmapped,
                                        "manual_review": "function, polarity, pin-1 and viewing/mating orientation remain unverified",
                                        "baseline_evidence": exp["evidence"]}
                else:
                    checks["C-10.2"] = {
                        "status": "PASS" if not missing else "FAIL",
                        "mapping_existence": "PASS" if not missing else "FAIL",
                        "mapping": [{"schematic_pin": str(k), "pcb_pad_number": str(v)}
                                    for k, v in pin_map.items()],
                        "missing": missing, "unmapped_schematic_pins": [],
                        "manual_review": "function, polarity, pin-1 and viewing/mating orientation remain unverified",
                        "baseline_evidence": exp["evidence"],
                    }

            ids = [str(pad["pad_id"]) for pad in pads if pad.get("pad_id") is not None]
            duplicate_ids = sorted(k for k, count in Counter(ids).items() if count > 1)
            exp_pads = (exp or {}).get("pads")
            if not comp.get("footprint") or not fp:
                checks["C-10.3"] = {"status": "NOT_CHECKED", "reason": "footprint definition unavailable"}
            elif duplicate_ids or len(ids) != len(pads):
                checks["C-10.3"] = {"status": "REVIEW", "reason": "repeated/missing physical pad IDs; inspect input data",
                                    "duplicate_pad_ids": duplicate_ids}
            elif baseline_error or exp_pads is None:
                checks["C-10.3"] = {"status": "NOT_CHECKED",
                                    "reason": baseline_error or "reviewed physical pad inventory is required"}
            else:
                exp_ids = [str(pad["pad_id"]) for pad in exp_pads if pad.get("pad_id") is not None]
                exp_nums = Counter(str(pad.get("number")) for pad in exp_pads
                                   if pad.get("number") is not None)
                actual_nums = Counter(str(pad.get("num")) for pad in pads if pad.get("num") is not None)
                missing_ids = sorted(set(exp_ids) - set(ids))
                unexpected_ids = sorted(set(ids) - set(exp_ids))
                duplicate_expected_ids = sorted(k for k, n in Counter(exp_ids).items() if n > 1)
                actual_by_id = {str(p['pad_id']): p for p in pads}
                number_mismatches = [{"pad_id": p['pad_id'], "expected": p['number'],
                                      "actual": actual_by_id[str(p['pad_id'])].get('num')}
                                     for p in exp_pads if str(p['pad_id']) in actual_by_id and
                                     str(p['number']) != str(actual_by_id[str(p['pad_id'])].get('num'))]
                passed = not (missing_ids or unexpected_ids or number_mismatches)
                checks["C-10.3"] = {
                    "status": "PASS" if passed else "FAIL",
                    "expected_pad_count": len(exp_pads), "actual_pad_count": len(pads),
                    "missing_pad_ids": missing_ids, "unexpected_pad_ids": unexpected_ids,
                    "duplicate_expected_pad_ids": duplicate_expected_ids,
                    "number_mismatches": number_mismatches,
                    "expected_pad_number_counts": dict(exp_nums),
                    "actual_pad_number_counts": dict(actual_nums),
                    "baseline_evidence": exp["evidence"],
                }

            dims = []
            exp_by_id = {str(pad["pad_id"]): pad for pad in (exp_pads or [])
                         if pad.get("pad_id") is not None}
            actual_by_id = {str(p.get("pad_id")): p for p in pads}
            for pad_id, ref_pad in exp_by_id.items():
                pad = actual_by_id.get(pad_id, {})
                for field in ("width", "height", "hole"):
                    expected_value = ref_pad.get(field + "_mil")
                    if expected_value is None:
                        continue
                    actual_value = _number(pad.get(field))
                    expected_num = _number(expected_value)
                    tolerance = _number(ref_pad.get(field + "_tolerance_mil"))
                    if actual_value is None or expected_num is None or tolerance is None or tolerance < 0:
                        dims.append({"pad_id": pad_id, "field": field, "status": "NOT_CHECKED",
                                     "reason": "numeric value or non-negative tolerance unavailable"})
                    else:
                        passed = abs(actual_value - expected_num) <= tolerance
                        dims.append({"pad_id": pad_id, "field": field,
                                     "expected_mil": expected_num, "tolerance_mil": tolerance,
                                     "actual_mil": actual_value,
                                     "status": "PASS" if passed else "FAIL"})
            if baseline_error or not dims or duplicate_ids:
                checks["C-10.4"] = {"status": "NOT_CHECKED",
                                    "reason": baseline_error or
                                    "manufacturer drawing-based dimensions and tolerances are required",
                                    "measurements": []}
            else:
                checks["C-10.4"] = {"status": "FAIL" if any(x["status"] == "FAIL" for x in dims)
                                    else "PASS" if all(x["status"] == "PASS" for x in dims)
                                    else "NOT_CHECKED", "measurements": dims,
                                    "baseline_evidence": exp["evidence"]}

            # These are partial comparisons, never a complete C-10 approval.
            remaining = {
                "C-10.1": "manufacturer package suffix, binding provenance and current instance verification",
                "C-10.2": "actual functional mapping, pin-1, polarity, orientation and mating view",
                "C-10.3": "hole/plating and net assignments; extraction derives pads from the library, not an independent API inventory",
                "C-10.4": "unlisted dimensions, pitch, holes with nonnumeric shapes, placement, assembly fit and process conditions",
            }
            for check_id, value in checks.items():
                value["automatic_status"] = value["status"]
                if value["status"] == "PASS":
                    value["status"] = "NOT_CHECKED"
                value["remaining"] = remaining[check_id]
            instances.append({"designator": ref, "component_id": comp.get("id"),
                              "pcb_uuid": pcb.get("uuid"),
                              "footprint_uuid": comp.get("footprint"),
                              "footprint_title": comp.get("footprint_title"), "checks": checks})

    coverage = {}
    for check_id in ("C-10.1", "C-10.2", "C-10.3", "C-10.4"):
        counts = Counter(row["checks"][check_id]["status"] for row in instances)
        automatic = Counter(row["checks"][check_id]["automatic_status"] for row in instances)
        coverage[check_id] = {"denominator": len(instances),
                              "counts": {status: counts.get(status, 0) for status in STATUSES},
                              "automatic_comparison_counts": {status: automatic.get(status, 0) for status in STATUSES}}
    findings = []
    for row in instances:
        for key, value in row["checks"].items():
            if value['status'] in ('FAIL', 'REVIEW'):
                findings.append({'id': f"{key}:{row['pcb_uuid']}:{row['component_id']}",
                                 'check_id': key, 'status': value['status'],
                                 'severity': None, 'severity_reason': 'requires impact assessment',
                                 'location': {k: row[k] for k in ('pcb_uuid', 'component_id', 'designator')},
                                 'evidence': value})
    return {"check_id": "C-10", "checker": "check_footprints.py", "read_only": True,
            "status": "PARTIAL" if instances else "NOT_CHECKED", "findings": findings,
            "limitations": ["This checks declared values only; source citations are recorded, not authenticated.",
                            "Extracted pads are instantiated from library definitions; not independent physical pad evidence.",
                            "No full C-10 PASS is issued; automatic_status is restricted to listed comparisons."],
            "instance_count": len(instances), "coverage": coverage, "instances": instances}


def report_markdown(result):
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    lines = ['# C-10 封装结构检查', '',
             f"检查实例数：{result['instance_count']}；仅部分自动比对，不代表完整封装审核通过。", '',
             '| 子项 | 实例数 | 自动比对通过 | 不匹配 | 待复核 | 未检查 |',
             '|---|---|---|---|---|---|']
    for key, row in result['coverage'].items():
        c = row['automatic_comparison_counts']
        lines.append(f"| {key} | {row['denominator']} | {c['PASS']} | {c['FAIL']} | {c['REVIEW']} | {c['NOT_CHECKED']} |")
    lines.extend(['', '自动比对通过只覆盖列出的字段；完整子项状态和剩余范围如下。', '',
                  '| 位号 / 实例 | 子项 | 自动结果 | 完整子项 | 原因 / 剩余范围 |',
                  '|---|---|---|---|---|'])
    for row in result['instances']:
        for key, value in row['checks'].items():
            lines.append('| ' + ' | '.join(cell(v) for v in
                         (f"{row['designator']} / {row['component_id']}", key,
                          value['automatic_status'], value['status'],
                          value.get('reason', '') + '; ' + value['remaining'])) + ' |')
    lines.extend(['', '## 可定位发现', ''])
    for finding in result['findings']:
        lines.extend([f"### {finding['id']}", '', '```json',
                      json.dumps(finding, ensure_ascii=False, indent=2), '```', ''])
    lines.extend(['## 数据来源', '', '```json',
                  json.dumps(result.get('inputs', {}), ensure_ascii=False, indent=2), '```', '',
                  '## 检查边界', ''])
    lines.extend('- ' + item for item in result['limitations'])
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run structural C-10 checks on extract.py output")
    parser.add_argument("pcb", help="extract.py pcb.json")
    parser.add_argument("--schematic", help="extract.py schematic.json")
    parser.add_argument("--expectations", help="reviewed C-10 expectation JSON with source citations")
    parser.add_argument("--pcb-id", help="required when the input contains multiple PCBs")
    parser.add_argument("--report", help="write Markdown report")
    parser.add_argument("--out", help="write result JSON; defaults to stdout")
    args = parser.parse_args(argv)
    try:
        inputs = [Path(p).resolve() for p in (args.pcb, args.schematic, args.expectations) if p]
        outputs = [Path(p).resolve() for p in (args.out, args.report) if p]
        if any(p in inputs for p in outputs) or len(set(outputs)) != len(outputs):
            raise ValueError("outputs must be distinct and must not overwrite input evidence")
        result = check(load_json(args.pcb),
                       load_json(args.schematic) if args.schematic else None,
                       load_json(args.expectations) if args.expectations else None, args.pcb_id)
        result['inputs'] = [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                            for p in inputs]
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(rendered)
        else:
            sys.stdout.write(rendered)
        if args.report:
            Path(args.report).write_text(report_markdown(result), encoding='utf-8')
        return 1 if any(f['status'] == 'FAIL' for f in result['findings']) else 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f"C-10 error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
