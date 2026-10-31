from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'windows'))
from clean_results import clean_local_results


class CleanupTests(unittest.TestCase):
    def test_preview_and_cleanup_only_numbered_results_preserve_dataset_and_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'datasets').mkdir()
            (root / 'datasets/demo120.csv').write_text('input dataset')
            (root / 'vm210').mkdir()
            (root / 'vm210/sufferage.py').write_text('source code')
            (root / 'results').mkdir()
            for number in (1, 2):
                (root / f'results/pengujian {number}.csv').write_text('old result')
            (root / 'results/catatan.txt').write_text('keep')
            (root / 'hasil_pengujian.html').write_text('old page')
            self.assertEqual(clean_local_results(root, preview=True), 2)
            self.assertTrue((root / 'results/pengujian 1.csv').exists())
            self.assertEqual((root / 'hasil_pengujian.html').read_text(), 'old page')
            self.assertEqual(clean_local_results(root), 2)
            self.assertFalse(list((root / 'results').glob('pengujian *.csv')))
            self.assertEqual((root / 'datasets/demo120.csv').read_text(), 'input dataset')
            self.assertEqual((root / 'vm210/sufferage.py').read_text(), 'source code')
            self.assertEqual((root / 'results/catatan.txt').read_text(), 'keep')
            self.assertIn('Sufferage Task Scheduler', (root / 'hasil_pengujian.html').read_text(encoding='utf-8'))

    def test_refuses_unrecognized_project(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'tidak dikenali'):
                clean_local_results(Path(directory))
