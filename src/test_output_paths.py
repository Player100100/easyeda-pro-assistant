"""Regression checks for external outputs and preserved input evidence."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import check_footprints
import extract
import output_paths as paths
from test_check_footprints import fixture


class OutputPathTests(unittest.TestCase):
    def setUp(self):
        test_root = paths.generated_path('outputs', 'tests')
        test_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='epro2-output-test-', dir=test_root)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.data = self.base / 'data'
        self.env = patch.dict(os.environ, EPRO2_DATA_DIR=str(self.data))
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_default_tracks_checkout_location_not_cwd(self):
        env = dict(os.environ)
        env.pop('EPRO2_DATA_DIR', None)
        result = subprocess.run([sys.executable, '-B', str(paths.PROJECT_ROOT / 'src/output_paths.py')],
                                cwd=self.base, env=env, check=True, capture_output=True, text=True)
        self.assertEqual(Path(json.loads(result.stdout)['data_root']),
                         paths.PROJECT_ROOT.with_name(paths.PROJECT_ROOT.name + '-data'))
        self.assertFalse(self.data.exists())

    def test_rejects_internal_roots_and_output_escape(self):
        for value in (str(paths.PROJECT_ROOT), str(paths.PROJECT_ROOT / 'outputs'), 'relative-dir'):
            with patch.dict(os.environ, EPRO2_DATA_DIR=value):
                with self.assertRaises(ValueError):
                    paths.data_root()
        with self.assertRaises(ValueError):
            paths.external_path(paths.PROJECT_ROOT / 'docs/new-report.md')
        with self.assertRaises(ValueError):
            paths.generated_path('..', 'escape')
        with self.assertRaises(ValueError):
            paths.safe_name('..')

    def test_initializer_copies_templates_without_overwriting(self):
        result = paths.initialize('board-v1')
        board = Path(result['board'])
        self.assertTrue(Path(result['evidence']).is_dir())
        source = paths.PROJECT_ROOT / 'work/boards/_template/intent.md'
        self.assertEqual((board / 'intent.md').read_bytes(), source.read_bytes())
        (board / 'intent.md').write_text('user edits', encoding='utf-8')
        paths.initialize('board-v1')
        self.assertEqual((board / 'intent.md').read_text(encoding='utf-8'), 'user edits')

    def test_extract_defaults_to_external_data(self):
        with patch.object(extract.R, 'read_project', return_value=({'title': 'test-board'}, [])):
            self.assertEqual(extract.main(['sample.epro2', '--quiet']), 0)
        result = self.data / 'outputs/extract/test-board'
        self.assertEqual({p.name for p in result.iterdir()},
                         {'index.json', 'pcb.json', 'schematic.json', 'netlist.json', 'summary.txt'})
        self.assertEqual(json.loads((result / 'index.json').read_text(encoding='utf-8'))['title'], 'test-board')

    def test_extract_rejects_internal_destination_before_reading(self):
        with patch.object(extract.R, 'read_project') as read, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exc:
                extract.main(['sample.epro2', '--out', str(paths.PROJECT_ROOT / 'outputs/forbidden')])
            self.assertEqual(exc.exception.code, 2)
            read.assert_not_called()

    def test_checker_writes_default_json_and_report_and_keeps_stdout(self):
        pcb, _, _ = fixture()
        source = self.base / 'pcb.json'
        source.write_text(json.dumps(pcb), encoding='utf-8')
        original = source.read_bytes()
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check_footprints.main([str(source), '--run-name', 'board-run']), 0)
        result = self.data / 'outputs/check-footprints/board-run/c10.json'
        report = self.data / 'review/board-run/c10.md'
        self.assertEqual(json.loads(result.read_text(encoding='utf-8')), json.loads(output.getvalue()))
        self.assertIn('C-10', report.read_text(encoding='utf-8'))
        self.assertEqual(original, source.read_bytes())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check_footprints.main([str(source), '--out', str(paths.PROJECT_ROOT / 'bad.json')]), 2)

    def test_explicit_external_outputs_create_parent_folders(self):
        pcb, _, _ = fixture()
        source = self.base / 'pcb.json'
        source.write_text(json.dumps(pcb), encoding='utf-8')
        out, report = self.base / 'custom/deep/result.json', self.base / 'reports/deep/c10.md'
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(check_footprints.main([str(source), '--out', str(out), '--report', str(report)]), 0)
        self.assertTrue(out.is_file())
        self.assertTrue(report.is_file())
        self.assertFalse(self.data.exists())

    def test_bridge_state_uses_same_external_root(self):
        env = dict(os.environ)
        env['PYTHONPATH'] = str(paths.PROJECT_ROOT / 'src')
        result = subprocess.run([sys.executable, '-B', '-c',
                                 'import eda; print(eda.STATE_DIR)'],
                                env=env, cwd=self.base, capture_output=True, text=True, check=True)
        self.assertEqual(Path(result.stdout.strip()), self.data / 'outputs/eda')


if __name__ == '__main__':
    unittest.main()
