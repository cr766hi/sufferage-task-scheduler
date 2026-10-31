"""Offline Sufferage for independent tasks sharing a measured ETC per task type."""
from collections import deque
import math


def sufferage_plan(tasks, workers, etc_ms):
    """Equivalent to evaluating every remaining task; identical ETC rows are grouped.

    Tasks of the same type have the same loss at each step, so only the earliest
    dataset entry of each type can win the existing tie-break. No policy changes.
    """
    if not workers or len(workers) != len(set(workers)):
        raise ValueError('Workers must be a nonempty unique list')
    priority = {worker: index for index, worker in enumerate(workers)}
    ready = dict.fromkeys(workers, 0.0)
    groups = {}
    for index, task in enumerate(tasks):
        groups.setdefault(task['task_type'], deque()).append((index, task))
    matrix = {kind: {worker: float(etc_ms[kind][worker]) for worker in workers}
              for kind in groups}
    if any(not math.isfinite(value) or value <= 0
           for values in matrix.values() for value in values.values()):
        raise ValueError('ETC entries must be positive finite milliseconds')
    plan = []
    while groups:
        candidates = []
        for kind, queue in groups.items():
            index, task = queue[0]
            times = {worker: ready[worker] + matrix[kind][worker] for worker in workers}
            ordered = sorted(workers, key=lambda worker: (times[worker], priority[worker]))
            best = ordered[0]
            second = times[ordered[1]] if len(ordered) > 1 else times[best]
            candidates.append((second - times[best], -index, task, best, second, times))
        loss, _, task, best, second, times = max(candidates, key=lambda entry: entry[:2])
        start = ready[best]
        ready[best] = times[best]
        plan.append({**task, 'worker': best, 'allocation_order': len(plan) + 1,
            'etc_ms': matrix[task['task_type']][best], 'predicted_start_ms': start,
            'predicted_finish_ms': times[best], 'best_ct_ms': times[best],
            'second_ct_ms': second, 'sufferage_ms': loss, 'candidate_ct_ms': times})
        queue = groups[task['task_type']]
        queue.popleft()
        if not queue:
            del groups[task['task_type']]
    return plan
