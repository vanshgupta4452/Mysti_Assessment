"""Run the Daybreak follow-up experiment. DRY RUN: writes files, sends nothing."""
import argparse
import csv
from pathlib import Path

import followup

HERE = Path(__file__).resolve().parent
DECISION_FIELDS = ['request_id', 'case_id', 'item', 'case_status', 'request_status', 'outcome', 'reason']
ACTION_FIELDS = ['action_id', 'case_id', 'request_ids', 'to', 'mode', 'reason', 'draft_subject', 'draft_body']


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', default=HERE / 'data', help='folder with the three CSVs and scenario.json')
    parser.add_argument('--out', default=HERE / 'out', help='output folder (overwritten on every run)')
    args = parser.parse_args(argv)

    result = followup.run(args.data)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / 'decisions.csv', result['decisions'], DECISION_FIELDS)
    write_csv(out / 'proposed_actions.csv', result['actions'], ACTION_FIELDS)
    (out / 'report.md').write_text(result['report'], encoding='utf-8')

    counts = {k: sum(d['outcome'] == k for d in result['decisions']) for k in ('eligible', 'review', 'excluded')}
    print(f"DRY RUN - nothing sent. data={args.data}")
    print(f"requests={len(result['decisions'])} eligible={counts['eligible']} review={counts['review']} "
          f"excluded={counts['excluded']} drafts={len(result['actions'])}")
    if not result['actions']:
        print('No follow-up proposed for this input.')
    print(f"wrote {out / 'report.md'}, {out / 'decisions.csv'}, {out / 'proposed_actions.csv'}")


if __name__ == '__main__':
    main()
