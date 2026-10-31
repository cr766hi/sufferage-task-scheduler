import asyncio
import json
from pathlib import Path
import random
import statistics
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'vm210'))
from sufferage import sufferage_plan
from scheduler import Scheduler
PROFILE=json.loads((ROOT/'workload/task_profiles.json').read_text())


def full_reference(tasks,workers,matrix):
    ready=dict.fromkeys(workers,0.)
    pending=list(enumerate(tasks))
    result=[]
    while pending:
        choices=[]
        for index,task in pending:
            times={w:ready[w]+float(matrix[task['task_type']][w]) for w in workers}
            order=sorted(workers,key=lambda w:(times[w],workers.index(w)))
            best=order[0]
            second=times[order[1]] if len(order)>1 else times[best]
            choices.append((second-times[best],-index,index,task,best,second,times))
        loss,_,index,task,best,second,times=max(choices,key=lambda c:c[:2])
        result.append((task['task_id'],best,loss,times,ready[best],times[best]))
        ready[best]=times[best]
        pending.remove((index,task))
    return result


class EquivalenceTests(unittest.TestCase):
    def test_grouped_planner_matches_full_reference_including_ties(self):
        rng=random.Random(421)
        for count in [0,1,2,40,120,500]:
            for worker_count in [1,2,4]:
                workers=[f'w{i}' for i in range(worker_count)]
                matrix={kind:{w:rng.choice([10,10,20,30,40]) for w in workers} for kind in PROFILE['tasks']}
                tasks=[dict(task_id=f'T{i}',task_type=rng.choice(list(PROFILE['tasks']))) for i in range(count)]
                expected=full_reference(tasks,workers,matrix)
                actual=sufferage_plan(tasks,workers,matrix)
                self.assertEqual([(r['task_id'],r['worker'],r['sufferage_ms'],r['candidate_ct_ms'],r['predicted_start_ms'],r['predicted_finish_ms']) for r in actual],expected)


class CalibrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_seven_rpc_samples_per_cell_not_worker_elapsed(self):
        with tempfile.TemporaryDirectory() as directory:
            workers=[dict(name='w1',url='unused',capacity=1),dict(name='w2',url='unused',capacity=2)]
            scheduler=Scheduler(PROFILE,Path(directory),workers)
            scheduler.worker_health=AsyncMock(side_effect=lambda worker:{**worker,'healthy':True})
            scheduler.collect=AsyncMock()
            calls=[]
            async def task(worker,kind):
                calls.append((worker['name'],kind))
                await asyncio.sleep(.002)
                return {'worker_elapsed_ms':999999}
            scheduler.worker_task=task
            response=await scheduler.calibrate(None)
            self.assertEqual(response.status,200)
            calibration=json.loads(response.text)
            self.assertEqual(calibration['version'],'rpc-median7-v2')
            for kind,values in calibration['etc_ms'].items():
                for worker,value in values.items():
                    detail=calibration['sample_details'][kind][worker]
                    self.assertEqual(len(detail['rpc_samples_ms']),7)
                    self.assertEqual(value,statistics.median(detail['rpc_samples_ms']))
                    self.assertLess(value,999999)
                    self.assertEqual(calls.count((worker,kind)),8)  # One warmup plus seven samples.
            scheduler.collect.assert_awaited()
