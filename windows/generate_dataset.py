"""Generate a reproducible batch of independent CPU tasks."""
import argparse
import csv
import json
from pathlib import Path
import random


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks', type=int, default=120)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', type=Path, help='Default: datasets/demo<tasks>.csv')
    args = parser.parse_args()
    if not 1 <= args.tasks <= 500:
        parser.error('tasks must be between 1 and 500')
    args.output = args.output or root / f'datasets/demo{args.tasks}.csv'
    profiles = json.loads((root / 'workload/task_profiles.json').read_text())
    light = args.tasks // 2
    medium = args.tasks * 3 // 10
    kinds = ['light'] * light + ['medium'] * medium + ['heavy'] * (args.tasks - light - medium)
    random.Random(args.seed).shuffle(kinds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['task_id','task_type','units','iterations_per_unit'])
        writer.writeheader()
        for index, kind in enumerate(kinds, 1):
            writer.writerow(dict(task_id=f'T{index:03}', task_type=kind,
                units=profiles['tasks'][kind]['units'], iterations_per_unit=profiles['iterations_per_unit']))
    print(args.output)


if __name__ == '__main__':
    main()
