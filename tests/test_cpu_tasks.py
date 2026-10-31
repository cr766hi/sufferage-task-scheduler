import asyncio
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from aiohttp import ClientSession, web

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lb = load('cpu_test_lb', ROOT / 'vm210/lb.py')
worker = load('cpu_test_worker', ROOT / 'backends/worker/worker.py')
PROFILE = json.loads((ROOT / 'workload/task_profiles.json').read_text())


class CpuTaskTests(unittest.TestCase):
    def test_parallel_partition_preserves_same_real_work(self):
        for kind, definition in PROFILE['tasks'].items():
            units = definition['units']
            checksum, cpu_ms = worker.compute_units(list(range(units)), 1000)
            parts = [worker.compute_units(list(range(index, units, 2)), 1000)[0]
                     for index in range(2)]
            self.assertEqual(checksum, sum(parts) % (1 << 256), kind)
            self.assertGreaterEqual(cpu_ms, 0)  # Windows CPU counters can round tiny tasks to zero.
        self.assertEqual([PROFILE['tasks'][kind]['units'] for kind in ('light', 'medium', 'heavy')], [2, 8, 24])

    def test_sufferage_trace_matches_completion_time_difference(self):
        slow, fast = lb.Backend('slow', '', 1), lb.Backend('fast', '', 2)
        jobs = [SimpleNamespace(work=.05, sequence=0), SimpleNamespace(work=.6, sequence=1)]
        plan = lb.sufferage_plan(jobs, [slow, fast], 0)
        job, selected, _ = plan[0]
        self.assertIs(job, jobs[1])
        self.assertIs(selected, fast)
        self.assertAlmostEqual(job.best_ct_ms, 300)
        self.assertAlmostEqual(job.second_ct_ms, 600)
        self.assertAlmostEqual(job.sufferage_ms, 300)


class TaskProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_task_routing_independent_estimates_and_trace(self):
        seen = []

        async def origin(request):
            if request.path == '/':
                return web.Response(text='vm101')
            if request.path == '/health':
                return web.json_response({'backend': 'vm101', 'capacity': 1,
                                          'workload': PROFILE['workload_id']})
            kind = request.match_info['kind']
            seen.append(kind)
            return web.json_response({'backend': 'vm101', 'task_type': kind}, headers={
                'X-Task-Type': kind, 'X-Worker-CPU-Ms': str(PROFILE['tasks'][kind]['units'] * 10)})

        upstream = web.Application()
        upstream.router.add_get('/', origin)
        upstream.router.add_get('/health', origin)
        upstream.router.add_get('/task/{kind}', origin)
        origin_runner = web.AppRunner(upstream)
        await origin_runner.setup()
        origin_site = web.TCPSite(origin_runner, '127.0.0.1', 0)
        await origin_site.start()
        url = 'http://127.0.0.1:' + str(origin_site._server.sockets[0].getsockname()[1])
        try:
            with tempfile.TemporaryDirectory() as directory:
                args = SimpleNamespace(mode='sufferage', queue_limit=100,
                    csv=str(Path(directory) / 'lb.csv'), timeout=2, batch_ms=10,
                    batch_size=20, initial_work_ms=20)
                proxy = lb.LoadBalancer(args)
                proxy.backends = [lb.Backend('vm101', url, 1, task_url=url)]
                app = web.Application()
                app.router.add_route('*', '/{tail:.*}', proxy.handle)
                app.on_startup.append(proxy.start)
                app.on_cleanup.append(proxy.stop)
                runner = web.AppRunner(app)
                await runner.setup()
                site = web.TCPSite(runner, '127.0.0.1', 0)
                await site.start()
                proxy_url = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
                try:
                    self.assertEqual([proxy.estimated_work('/task/' + kind) for kind in ('light', 'medium', 'heavy')], [.05, .2, .6])
                    async with ClientSession(trust_env=False) as client:
                        for kind in ('light', 'medium', 'heavy'):
                            async with client.get(proxy_url + '/task/' + kind) as response:
                                self.assertEqual(response.status, 200)
                                self.assertEqual(response.headers['X-Task-Type'], kind)
                                self.assertEqual(response.headers['X-LB-Algorithm'], 'sufferage')
                                self.assertGreater(float(response.headers['X-LB-Estimated-Work-Ms']), 0)
                                self.assertIn('X-LB-Sufferage-Ms', response.headers)
                        async with client.get(proxy_url + '/') as response:
                            self.assertEqual(await response.text(), 'vm101')
                    self.assertEqual(seen, ['light', 'medium', 'heavy'])
                    self.assertLess(proxy.estimates['/task/light'], proxy.estimates['/task/heavy'])
                finally:
                    await runner.cleanup()
                with open(args.csv, newline='') as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual([row['task_type'] for row in rows], ['light', 'medium', 'heavy', ''])
                self.assertTrue(all(int(row['batch_id']) > 0 for row in rows))
        finally:
            await origin_runner.cleanup()
