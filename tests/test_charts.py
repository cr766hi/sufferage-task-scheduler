import csv
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'windows'))
from scheduler_charts import bars, charts_dashboard, resource_line, sufferage_line


class ChartTests(unittest.TestCase):
    def test_sufferage_trace_preserves_decision_order_and_values(self):
        html = sufferage_line([dict(allocation_order='2', sufferage_ms='30', task_id='B'),
                              dict(allocation_order='1', sufferage_ms='10', task_id='<A>')])
        self.assertLess(html.index('Urutan 1 · &lt;A&gt;'), html.index('Urutan 2 · B'))
        self.assertIn('Sufferage 30 ms', html)
        for svg in re.findall(r'<svg.*?</svg>', html, re.S):
            ET.fromstring(svg)

    def test_missing_values_are_not_zero_and_labels_are_escaped(self):
        html = bars('<CPU>', 'note', ['vm<script>', 'vm2'], [('Actual', [None, 0])], '%', limit=100)
        self.assertIn('tidak tersedia', html)
        self.assertIn('&lt;CPU&gt;', html)
        self.assertNotIn('<script>', html)
        self.assertIn('Actual: 0 %', html)
        for svg in re.findall(r'<svg.*?</svg>', html, re.S):
            ET.fromstring(svg)

    def test_failed_resource_sample_breaks_cpu_line(self):
        rows = [dict(record_type='resource_sample', vm='vm101', resource_status=status,
                     elapsed_ms=str(i*1000), cpu_percent=value)
                for i, (status, value) in enumerate([('ok','20'),('ok','30'),('error',''),('ok','40'),('ok','50')])]
        html = resource_line(rows)
        self.assertEqual(html.count('<polyline'), 2)
        self.assertEqual(html.count('<circle'), 4)

    def test_empty_and_multiple_batch_selection(self):
        self.assertIn('Belum ada hasil', charts_dashboard([]))
        summary = dict(dataset_name='empty.csv', batch_status='completed', makespan_seconds='1', total_tasks='0')
        html = charts_dashboard([(1, None, summary, []), (2, None, summary, [])])
        self.assertIn('id="run-1" hidden', html)
        self.assertIn('id="run-2"><', html)
        self.assertIn('value="run-2" selected', html)
        self.assertIn('Makespan antar-pengujian', html)
        for svg in re.findall(r'<svg.*?</svg>', html, re.S):
            ET.fromstring(svg)


if __name__ == '__main__':
    unittest.main()
