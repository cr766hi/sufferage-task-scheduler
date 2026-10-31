import asyncio
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from aiohttp import ClientSession, web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vm210'))
sys.path.insert(0,str(ROOT/'windows'))
sys.path.insert(0,str(ROOT/'monitoring'))
from sufferage import sufferage_plan
from scheduler import Scheduler, create_app, validate_tasks, batch_summary
from scheduler_report import save_result, generate_report
from resource_stats import cpu_delta, summarize_resources
PROFILE = json.loads((ROOT/'workload/task_profiles.json').read_text())


class PlanTests(unittest.TestCase):
    def test_largest_sufferage_first_and_recompute_all_reservations(self):
        tasks=[dict(task_id='L',task_type='light',units=2),dict(task_id='H',task_type='heavy',units=24)]
        matrix={'light':{'a':20,'b':10},'heavy':{'a':100,'b':50}}
        plan=sufferage_plan(tasks,['a','b'],matrix)
        self.assertEqual([(t['task_id'],t['worker']) for t in plan],[('H','b'),('L','a')])
        self.assertEqual(plan[0]['sufferage_ms'],50)
        self.assertEqual(plan[1]['candidate_ct_ms'],{'a':20,'b':60})
        self.assertEqual(plan[1]['sufferage_ms'],40)
        self.assertEqual(len(tasks),2)

    def test_every_selection_is_global_maximum_and_each_vm_queue_nonoverlapping(self):
        tasks=[dict(task_id=str(i),task_type=kind,units=PROFILE['tasks'][kind]['units']) for i,kind in enumerate(['light','heavy','medium','heavy','light','medium'])]
        matrix={'light':{'a':30,'b':10,'c':20},'medium':{'a':90,'b':40,'c':60},'heavy':{'a':240,'b':100,'c':200}}
        plan=sufferage_plan(tasks,['a','b','c'],matrix)
        ready={w:0 for w in ['a','b','c']}
        remaining=list(tasks)
        for selected in plan:
            scores=[]
            for task in remaining:
                times=sorted(ready[w]+matrix[task['task_type']][w] for w in ready)
                scores.append(times[1]-times[0])
            self.assertAlmostEqual(selected['sufferage_ms'],max(scores))
            self.assertEqual(selected['predicted_start_ms'],ready[selected['worker']])
            ready[selected['worker']]=selected['predicted_finish_ms']
            remaining=[task for task in remaining if task['task_id']!=selected['task_id']]

    def test_validation_and_resource_baseline_reset(self):
        with self.assertRaises(ValueError):
            validate_tasks([{'task_id':'x','task_type':'heavy','units':1}],PROFILE)
        with self.assertRaises(ValueError):
            validate_tasks([{'task_id':'x','task_type':'light'},{'task_id':'x','task_type':'light'}],PROFILE)
        previous=dict(boot_id='a',cpu_total_ticks=100,cpu_busy_ticks=20,sample_monotonic_seconds=1)
        current=dict(previous,cpu_total_ticks=200,cpu_busy_ticks=70,sample_monotonic_seconds=3)
        self.assertEqual(cpu_delta(previous,current)['cpu_percent'],50)
        self.assertEqual(cpu_delta(previous,{**current,'boot_id':'b'}),{})
        resource=summarize_resources([dict(vm='vm101',resource_status='error',error='timeout')])[0]
        self.assertIsNone(resource['cpu_avg_percent'])


class BatchIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_batch_execution_metrics_report_and_resume(self):
        starts,finishes={},{}
        busy={'a':0,'b':0}
        peak={'a':0,'b':0}
        async def health(request):
            name=request.match_info['worker']
            return web.json_response(dict(backend=name,capacity=1 if name=='a' else 2,workload=PROFILE['workload_id']))
        async def execute(request):
            name=request.match_info['worker']
            kind=request.match_info['kind']
            busy[name]+=1
            peak[name]=max(peak[name],busy[name])
            try:
                await asyncio.sleep(.015 if name=='a' else .01)
                return web.json_response(dict(backend=name,capacity=1,task_type=kind,
                    units=PROFILE['tasks'][kind]['units'],workload=PROFILE['workload_id'],
                    cpu_ms=10,worker_elapsed_ms=15 if name=='a' else 10,checksum='a'*64))
            finally:
                busy[name]-=1
        async def metrics(request):
            raise web.HTTPServiceUnavailable(text='simulated metrics outage')
        app=web.Application()
        app.router.add_get('/{worker}/health',health)
        app.router.add_get('/{worker}/task/{kind}',execute)
        app.router.add_get('/{worker}/metrics',metrics)
        upstream=web.AppRunner(app)
        await upstream.setup()
        site=web.TCPSite(upstream,'127.0.0.1',0)
        await site.start()
        url='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
        try:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                workers=[dict(name=w,url=url+'/'+w,capacity=1 if w=='a' else 2) for w in ['a','b']]
                scheduler=Scheduler(PROFILE,root/'logs',workers)
                scheduler.calibration=dict(id='test',timestamp_utc='test',method='fixture',
                    etc_ms={kind:{'a':30,'b':10} for kind in PROFILE['tasks']})
                runner=web.AppRunner(create_app(scheduler))
                await runner.setup()
                port=web.TCPSite(runner,'127.0.0.1',0)
                await port.start()
                base='http://127.0.0.1:'+str(port._server.sockets[0].getsockname()[1])
                try:
                    async with ClientSession(trust_env=False) as client:
                        tasks=[dict(task_id=f'T{i}',task_type=kind) for i,kind in enumerate(['heavy','light','medium','light','heavy','medium'])]
                        async with client.post(base+'/api/batches',json={'tasks':tasks}) as response:
                            self.assertEqual(response.status,202)
                            run_id=(await response.json())['batch_id']
                        await scheduler.execution
                        async with client.get(base+'/api/batches/'+run_id) as response:
                            result=await response.json()
                        self.assertEqual(result['status'],'completed')
                        self.assertEqual(result['summary']['completed_tasks'],6)
                        for task in result['tasks']:
                            self.assertAlmostEqual(task['waiting_ms']+task['execution_ms'],task['turnaround_ms'])
                            self.assertGreaterEqual(task['finish_ms'],task['start_ms'])
                        self.assertLessEqual(max(peak.values()),1)
                        self.assertGreaterEqual(result['summary']['makespan_seconds']*1000,max(t['finish_ms'] for t in result['tasks']))
                        self.assertTrue((root/'logs'/run_id/'result.json').exists())
                        output=save_result(root,result)
                        self.assertEqual(save_result(root,result),output)
                        self.assertEqual(len(list((root/'results').iterdir())),1)
                        with output.open(encoding='utf-8-sig',newline='') as handle:
                            rows=list(csv.DictReader(handle))
                        self.assertEqual(sum(row['record_type']=='task' for row in rows),6)
                        self.assertIn('Makespan',generate_report(root).read_text(encoding='utf-8'))
                        scheduler.batches.clear()
                        async with client.get(base+'/api/batches/latest') as response:
                            self.assertEqual((await response.json())['batch_id'],run_id)
                finally:
                    await runner.cleanup()
        finally:
            await upstream.cleanup()
