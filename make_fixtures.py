"""Build the two changed-input folders from data/ without editing data/.

fixtures/changed_48h  - snapshot moved from 09:00 to 11:00 (one field in scenario.json)
fixtures/no_action    - every open request that could be chased marked received (valid input, no work)
"""
import csv
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPEN_PENDING = {'R009', 'R018', 'R022', 'R024', 'R025', 'R026', 'R027', 'R016', 'R029'}


def copy_data(source, target):
    target = Path(target)
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target


def make_changed_48h(source, target):
    target = copy_data(source, target)
    path = target / 'scenario.json'
    scenario = json.loads(path.read_text(encoding='utf-8'))
    scenario['snapshot_at'] = '2026-09-07T11:00:00+05:30'
    path.write_text(json.dumps(scenario, indent=2) + '\n', encoding='utf-8')
    return target


def make_no_action(source, target):
    target = copy_data(source, target)
    path = target / 'requests.csv'
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    for row in rows:
        if row['request_id'] in OPEN_PENDING:
            row['status'] = 'received'
            row['received_at'] = '2026-09-06T18:00+05:30'
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return target


if __name__ == '__main__':
    make_changed_48h(HERE / 'data', HERE / 'fixtures' / 'changed_48h')
    make_no_action(HERE / 'data', HERE / 'fixtures' / 'no_action')
    print('wrote fixtures/changed_48h and fixtures/no_action')
