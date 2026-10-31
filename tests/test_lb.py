import asyncio
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from aiohttp import ClientSession, web

path = Path(__file__).resolve().parents[1] / 'vm210/lb.py'
spec = importlib.util.spec_from_file_location('lb', path)
lb = importlib.util.module_from_spec(spec)
sys.modules['lb'] = lb
spec.loader.exec_module(lb)


class PlanTests(unittest.TestCase):
    def test_larger_sufferage_first_and_reservation_changes_choice(self):
        a = lb.Backend('a', '', 1)
        b = lb.Backend('b', '', 2)
        small = SimpleNamespace(work=.1, sequence=0)
        large = SimpleNamespace(work=.2, sequence=1)
        plan = lb.sufferage_plan([small, large], [a, b], 0)
        self.assertIs(plan[0][0], large)
        self.assertIs(plan[0][1], b)
        self.assertIs(plan[1][0], small)
        self.assertIs(plan[1][1], a)
        self.assertAlmostEqual(a.ready_time, .1)
        self.assertAlmostEqual(b.ready_time, .1)


class ProxyTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_modes_and_no_healthy_backend(self):
        async def backend(request):
            return web.Response(text='vm101', headers={'X-Origin': 'test'})
        upstream = web.Application()
        upstream.router.add_get('/', backend)
        upstream_runner = web.AppRunner(upstream)
        await upstream_runner.setup()
        site = web.TCPSite(upstream_runner, '127.0.0.1', 0)
        await site.start()
        upstream_port = site._server.sockets[0].getsockname()[1]
        try:
            with tempfile.TemporaryDirectory() as directory:
                for mode in ['round_robin', 'least_connections', 'sufferage']:
                    args = SimpleNamespace(mode=mode, queue_limit=100,
                        csv=str(Path(directory) / (mode + '.csv')), timeout=1,
                        batch_ms=25, batch_size=4, initial_work_ms=20)
                    proxy = lb.LoadBalancer(args)
                    for b in proxy.backends:
                        b.url = f'http://127.0.0.1:{upstream_port}'
                    app = web.Application()
                    app.router.add_get('/', proxy.handle)
                    app.on_startup.append(proxy.start)
                    app.on_cleanup.append(proxy.stop)
                    runner = web.AppRunner(app)
                    await runner.setup()
                    proxy_site = web.TCPSite(runner, '127.0.0.1', 0)
                    await proxy_site.start()
                    port = proxy_site._server.sockets[0].getsockname()[1]
                    try:
                        async with ClientSession(trust_env=False) as client:
                            async def get_one():
                                async with client.get(f'http://127.0.0.1:{port}/') as r:
                                    self.assertEqual(r.status, 200)
                                    self.assertEqual(await r.text(), 'vm101')
                                    self.assertIn(r.headers['X-LB-Backend'], ['vm101','vm102','vm201','vm202'])
                            await asyncio.gather(*(get_one() for _ in range(8)))
                            for b in proxy.backends:
                                b.healthy = False
                            async with client.get(f'http://127.0.0.1:{port}/') as r:
                                self.assertEqual(r.status, 503)
                    finally:
                        await runner.cleanup()
                    import csv
                    with open(args.csv, newline='') as stream:
                        rows = list(csv.DictReader(stream))
                    self.assertEqual(len(rows), 9)
                    self.assertEqual(rows[-1]['status'], '503')
        finally:
            await upstream_runner.cleanup()


if __name__ == '__main__':
    unittest.main()
