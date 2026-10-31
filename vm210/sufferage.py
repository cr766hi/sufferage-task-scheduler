"""Offline Sufferage for independent non-preemptive tasks and a measured ETC matrix."""
import math


def sufferage_plan(tasks, workers, etc_ms):
    """Return an ordered allocation; CT and ready times are relative milliseconds."""
    ready = {worker: 0.0 for worker in workers}
    pending = list(enumerate(tasks))
    plan = []
    while pending:
        candidates = []
        for index, task in pending:
            times = {worker: ready[worker] + float(etc_ms[task['task_type']][worker])
                     for worker in workers}
            if any(not math.isfinite(value) or value <= 0 for value in times.values()):
                raise ValueError('ETC entries must be positive finite milliseconds')
            ordered = sorted(workers, key=lambda worker: (times[worker], workers.index(worker)))
            best = ordered[0]
            second = times[ordered[1]] if len(ordered) > 1 else times[best]
            loss = second - times[best]
            candidates.append((loss, -index, index, task, best, second, times))
        loss, _, index, task, best, second, times = max(candidates, key=lambda entry: entry[:2])
        start = ready[best]
        ready[best] = times[best]
        plan.append({**task, 'worker': best, 'allocation_order': len(plan) + 1,
                     'etc_ms': float(etc_ms[task['task_type']][best]),
                     'predicted_start_ms': start, 'predicted_finish_ms': times[best],
                     'best_ct_ms': times[best], 'second_ct_ms': second,
                     'sufferage_ms': loss, 'candidate_ct_ms': times})
        pending.remove((index, task))
    return plan
