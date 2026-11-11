"""Focused tests for the read-only C-10 checker."""
import contextlib
import copy
import io
import json
import unittest
from pathlib import Path
from uuid import uuid4

import check_footprints


def fixture():
    pcb = {"pcbs": [{"uuid": "pcb1", "components": [{
        "id": "c1", "designator": "U1", "footprint": "fp1",
        "footprint_title": "QFN-4", "attrs": {"Manufacturer Part": "ABC-4"},
        "pads": [
            {"pad_id": "p1", "num": "1", "width": 10.0, "height": 10.0, "hole": None},
            {"pad_id": "p2", "num": "2", "width": 10.0, "height": 10.0, "hole": None},
            {"pad_id": "p3", "num": "3", "width": 10.0, "height": 10.0, "hole": None},
            {"pad_id": "p4", "num": "4", "width": 10.0, "height": 10.0, "hole": None},
        ],
    }]}], "footprints": {"fp1": {"uuid": "fp1", "title": "QFN-4"}}}
    schematic = {"pages": [{"components": [{"designator": "U1", "pins": [
        {"number": str(n)} for n in range(1, 5)
    ]}]}]}
    expected = {"components": {"U1": {
        "mpn": "ABC-4", "footprint_uuid": "fp1", "footprint_title": "QFN-4",
        "evidence": {"source": "manufacturer-drawing.pdf", "document": "ABC-4 datasheet",
                     "page": "3"},
        "pin_map": {str(n): str(n) for n in range(1, 5)},
        "pads": [{"pad_id": f"p{n}", "number": str(n),
                  "width_mil": 10, "width_tolerance_mil": 0,
                  "height_mil": 10, "height_tolerance_mil": 0} for n in range(1, 5)],
    }}}
    return pcb, schematic, expected


class FootprintCheckerTests(unittest.TestCase):
    def test_without_reviewed_expectations_stays_not_checked(self):
        pcb, schematic, _ = fixture()
        result = check_footprints.check(pcb, schematic)
        checks = result["instances"][0]["checks"]
        self.assertEqual([checks[f"C-10.{n}"]["status"] for n in range(1, 5)],
                         ["NOT_CHECKED"] * 4)

    def test_expected_identity_pin_inventory_and_dimensions_pass(self):
        pcb, schematic, expected = fixture()
        result = check_footprints.check(pcb, schematic, expected)
        checks = result["instances"][0]["checks"]
        self.assertEqual([checks[f"C-10.{n}"]["automatic_status"] for n in range(1, 5)],
                         ["PASS"] * 4)
        self.assertEqual([checks[f"C-10.{n}"]["status"] for n in range(1, 5)],
                         ["NOT_CHECKED"] * 4)

    def test_mpn_and_footprint_mismatch_fail(self):
        pcb, schematic, expected = fixture()
        expected["components"]["U1"]["mpn"] = "OTHER"
        expected["components"]["U1"]["footprint_uuid"] = "fp2"
        checks = check_footprints.check(pcb, schematic, expected)["instances"][0]["checks"]
        self.assertEqual(checks["C-10.1"]["automatic_status"], "FAIL")
        self.assertEqual(checks["C-10.1"]["status"], "FAIL")
        self.assertEqual(len(checks["C-10.1"]["mismatches"]), 2)

    def test_missing_physical_pad_is_detected_even_with_duplicate_numbers_supported(self):
        pcb, schematic, expected = fixture()
        pcb["pcbs"][0]["components"][0]["pads"].pop()
        expected["components"]["U1"]["pads"].append(
            {"pad_id": "p5", "number": "4"})
        checks = check_footprints.check(pcb, schematic, expected)["instances"][0]["checks"]
        self.assertEqual(checks["C-10.3"]["automatic_status"], "FAIL")
        self.assertIn("p5", checks["C-10.3"]["missing_pad_ids"])

    def test_dimension_tolerance_is_applied(self):
        pcb, schematic, expected = fixture()
        expected["components"]["U1"]["pads"][0]["width_mil"] = 12
        expected["components"]["U1"]["pads"][0]["width_tolerance_mil"] = 1
        checks = check_footprints.check(pcb, schematic, expected)["instances"][0]["checks"]
        self.assertEqual(checks["C-10.4"]["automatic_status"], "FAIL")

    def test_missing_citation_cannot_enable_comparisons(self):
        pcb, schematic, expected = fixture()
        expected['components']['U1'].pop('evidence')
        result = check_footprints.check(pcb, schematic, expected)
        self.assertTrue(all(x['automatic_status'] == 'NOT_CHECKED'
                            for x in result['instances'][0]['checks'].values()))

    def test_swapped_pad_numbers_detected_even_with_same_counts(self):
        pcb, schematic, expected = fixture()
        pads = pcb['pcbs'][0]['components'][0]['pads']
        pads[0]['num'], pads[1]['num'] = pads[1]['num'], pads[0]['num']
        result = check_footprints.check(pcb, schematic, expected)
        check = result['instances'][0]['checks']['C-10.3']
        self.assertEqual(check['status'], 'FAIL')
        self.assertEqual(len(check['number_mismatches']), 2)

    def test_partial_pin_map_is_not_reported_as_pass(self):
        pcb, schematic, expected = fixture()
        expected['components']['U1']['pin_map'].pop('4')
        result = check_footprints.check(pcb, schematic, expected)
        check = result['instances'][0]['checks']['C-10.2']
        self.assertEqual(check['status'], 'NOT_CHECKED')
        self.assertEqual(check['mapping_existence'], 'PASS')
        self.assertEqual(check['unmapped_schematic_pins'], ['4'])

    def test_missing_instance_pads_are_review_not_mapping_failure(self):
        pcb, schematic, expected = fixture()
        pcb['pcbs'][0]['components'][0]['pads'] = []
        result = check_footprints.check(pcb, schematic, expected)
        check = result['instances'][0]['checks']['C-10.2']
        self.assertEqual(check['status'], 'REVIEW')

    def test_duplicate_numbers_and_unnumbered_mechanical_pad_are_legal(self):
        pcb, schematic, expected = fixture()
        pads = pcb['pcbs'][0]['components'][0]['pads']
        pads.extend([dict(pads[0], pad_id='extra'), {'pad_id': 'mount', 'num': None}])
        expected['components']['U1']['pads'].extend([
            {'pad_id': 'extra', 'number': '1'}, {'pad_id': 'mount', 'number': None}])
        result = check_footprints.check(pcb, schematic, expected)
        self.assertEqual(result['instances'][0]['checks']['C-10.3']['automatic_status'], 'PASS')

    def test_missing_dimension_pad_cannot_be_skipped_as_pass(self):
        pcb, schematic, expected = fixture()
        pcb['pcbs'][0]['components'][0]['pads'].pop()
        result = check_footprints.check(pcb, schematic, expected)
        check = result['instances'][0]['checks']['C-10.4']
        self.assertEqual(check['automatic_status'], 'NOT_CHECKED')
        self.assertTrue(any(m['pad_id'] == 'p4' and m['status'] == 'NOT_CHECKED'
                            for m in check['measurements']))

    def test_duplicate_or_missing_physical_ids_require_review(self):
        for identifier in ('p2', None):
            with self.subTest(identifier=identifier):
                pcb, sch, exp = fixture()
                pcb['pcbs'][0]['components'][0]['pads'][0]['pad_id'] = identifier
                result = check_footprints.check(pcb, sch, exp)
                self.assertEqual(result['instances'][0]['checks']['C-10.3']['status'], 'REVIEW')

    def test_invalid_baselines_rejected(self):
        for bad in ('missing_tolerance', 'negative_tolerance', 'nan', 'boolean',
                    'duplicate_id', 'unknown_ref'):
            with self.subTest(bad=bad):
                pcb, sch, exp = fixture()
                pad = exp['components']['U1']['pads'][0]
                if bad == 'missing_tolerance':
                    pad.pop('width_tolerance_mil')
                elif bad == 'negative_tolerance':
                    pad['width_tolerance_mil'] = -1
                elif bad == 'nan':
                    pad['width_mil'] = float('nan')
                elif bad == 'boolean':
                    pad['width_mil'] = True
                elif bad == 'duplicate_id':
                    exp['components']['U1']['pads'].append(copy.deepcopy(pad))
                else:
                    exp['components']['OTHER'] = exp['components'].pop('U1')
                with self.assertRaises(ValueError):
                    check_footprints.check(pcb, sch, exp)

    def test_empty_board_is_not_a_pass(self):
        result = check_footprints.check({'pcbs': []})
        self.assertEqual(result['status'], 'NOT_CHECKED')
        self.assertEqual(result['instance_count'], 0)
        self.assertEqual(result['coverage']['C-10.1']['counts']['PASS'], 0)

    def test_api_netlist_not_accepted_as_physical_inventory(self):
        with self.assertRaises(ValueError):
            check_footprints.check({'components': {'U1': {'pinInfoMap': {}}}})

    def test_multiple_boards_require_selection(self):
        pcb, sch, exp = fixture()
        other = copy.deepcopy(pcb['pcbs'][0])
        other['uuid'] = 'pcb2'
        pcb['pcbs'].append(other)
        with self.assertRaises(ValueError):
            check_footprints.check(pcb, sch, exp)
        self.assertEqual(check_footprints.check(pcb, sch, exp, 'pcb2')['instance_count'], 1)

    def test_duplicate_references_rejected(self):
        pcb, sch, exp = fixture()
        pcb['pcbs'][0]['components'].append(copy.deepcopy(pcb['pcbs'][0]['components'][0]))
        with self.assertRaises(ValueError):
            check_footprints.check(pcb, sch, exp)

    def test_missing_mpn_is_unknown_not_wrong_part(self):
        pcb, sch, exp = fixture()
        pcb['pcbs'][0]['components'][0]['attrs'] = {}
        result = check_footprints.check(pcb, sch, exp)
        self.assertEqual(result['instances'][0]['checks']['C-10.1']['automatic_status'], 'NOT_CHECKED')

    def test_device_properties_supply_mpn(self):
        pcb, sch, exp = fixture()
        pcb['pcbs'][0]['components'][0]['attrs'] = {}
        sch['pages'][0]['components'][0]['device'] = 'device1'
        sch['devices'] = {'device1': {'attributes': {'Manufacturer Part': 'ABC-4'}}}
        result = check_footprints.check(pcb, sch, exp)
        self.assertEqual(result['instances'][0]['checks']['C-10.1']['automatic_status'], 'PASS')

    def test_cli_writes_evidence_and_report_and_protects_inputs(self):
        pcb, sch, exp = fixture()
        exp['components']['U1']['mpn'] = 'wrong-part'
        from output_paths import generated_path
        root = generated_path('outputs', 'tests')
        root.mkdir(parents=True, exist_ok=True)
        prefix = f'c10-test-{uuid4().hex}'
        paths = [root / f'{prefix}-{name}.json' for name in ('pcb', 'sch', 'exp')]
        out, report = root / f'{prefix}-result.json', root / f'{prefix}-report.md'
        try:
            for path, value in zip(paths, (pcb, sch, exp)):
                path.write_text(json.dumps(value), encoding='utf-8')
            args = [str(paths[0]), '--schematic', str(paths[1]), '--expectations', str(paths[2])]
            code = check_footprints.main(args + ['--out', str(out), '--report', str(report)])
            self.assertEqual(code, 1)
            result = json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(len(result['inputs']), 3)
            self.assertEqual(len(result['inputs'][0]['sha256']), 64)
            self.assertIn('U1', report.read_text(encoding='utf-8'))
            saved = paths[0].read_bytes()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(check_footprints.main(args + ['--out', str(paths[0])]), 2)
            self.assertEqual(paths[0].read_bytes(), saved)
        finally:
            for path in (*paths, out, report):
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
