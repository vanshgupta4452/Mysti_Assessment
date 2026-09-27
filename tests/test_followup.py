"""Checks for the Daybreak follow-up experiment. Run: python -m unittest discover -s tests -v"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import followup  # noqa: E402
import make_fixtures  # noqa: E402
import run  # noqa: E402

DATA = HERE / 'data'


def outcomes(result, outcome):
    return {d['request_id'] for d in result['decisions'] if d['outcome'] == outcome}


def edited_copy(tmp, request_id, **changes):
    """Copy data/ and change fields of one request row."""
    target = make_fixtures.copy_data(DATA, Path(tmp) / 'data')
    path = target / 'requests.csv'
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    for row in rows:
        if row['request_id'] == request_id:
            row.update(changes)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return target


class SuppliedData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = followup.run(DATA)

    def test_repeated_event_deliveries_do_not_add_effort(self):
        effort = self.result['effort']
        self.assertEqual((effort['rows'], effort['unique']), (128, 124))
        self.assertEqual(effort['repeat_ids'], ['E005', 'E032', 'E059', 'E087'])
        self.assertEqual(effort['conflicting_repeats'], [])
        self.assertEqual((effort['minutes_raw'], effort['minutes']), (412, 400))
        self.assertEqual(effort['blank_ids'], ['E002', 'E035', 'E081'])

    def test_queue_on_supplied_data(self):
        self.assertEqual(outcomes(self.result, 'eligible'), {'R009', 'R024', 'R025', 'R026', 'R027'})
        self.assertEqual(outcomes(self.result, 'review'), {'R018', 'R022'})
        self.assertEqual([a['action_id'] for a in self.result['actions']],
                         ['C009:R009+R025', 'C017:R027', 'C024:R024+R026'])

    def test_never_contacts_closed_booked_opted_out_or_received(self):
        proposed = {i for a in self.result['actions'] for i in a['request_ids'].split()}
        forbidden = {'R001', 'R005', 'R008', 'R013', 'R019',  # closed or booked cases
                     'R012', 'R028',                          # followup_allowed=0
                     'R017', 'R021', 'R023', 'R030'}          # already received
        self.assertFalse(proposed & forbidden)

    def test_closed_case_stays_excluded_despite_conflicting_fields(self):
        # R001 is pending with a received_at, but its case is completed (rule 4).
        decision = next(d for d in self.result['decisions'] if d['request_id'] == 'R001')
        self.assertEqual(decision['outcome'], 'excluded')

    def test_baseline_comparison(self):
        rows = {row['name'].split()[0]: row for row in self.result['comparison']}
        self.assertEqual(rows['B0']['proposed'], 15)
        self.assertEqual(len(rows['B0']['breaks_rules']), 10)
        self.assertEqual(rows['P']['breaks_rules'], ['R018'])
        self.assertEqual(rows['P']['review_unflagged'], ['R022'])
        self.assertEqual(rows['M']['breaks_rules'], [])

    def test_claim_file_link_cannot_carry_the_whole_chase(self):
        claim = self.result['claim']
        self.assertEqual(claim['carried'], ['R009', 'R024', 'R026'])
        self.assertEqual(claim['not_carried'], ['R025', 'R027'])
        self.assertEqual(claim['cases_fully_covered'], ['C024'])
        self.assertEqual(claim['receipt_conflicts_link_could_prevent'], ['R018'])

    def test_net_value_subtracts_reconciliation(self):
        value = self.result['value']
        self.assertEqual(value['reconcile_cost'], 6.0)
        self.assertEqual(value['net_min_per_week'], 8.5)
        self.assertEqual(value['tool_cost_inr_per_month'], 0)

    def test_report_labels_free_plan_reminders_as_inference(self):
        self.assertIn('Inferred from documentation', self.result['report'])


class ChangedInputs(unittest.TestCase):
    def test_exactly_48_hours_is_eligible(self):
        # Changed input + edge case: snapshot 11:00 puts R016 and R029 at exactly 48.0h.
        with tempfile.TemporaryDirectory() as tmp:
            result = followup.run(make_fixtures.make_changed_48h(DATA, Path(tmp) / 'd'))
        self.assertEqual(outcomes(result, 'eligible'),
                         {'R009', 'R016', 'R024', 'R025', 'R026', 'R027', 'R029'})
        self.assertEqual(len(result['actions']), 5)

    def test_one_minute_short_of_48_hours_is_not_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = edited_copy(tmp, 'R016', last_requested_at='2026-09-05T09:01+05:30')
            result = followup.run(data)
        self.assertIn('R016', outcomes(result, 'excluded'))

    def test_missing_contact_goes_to_review_not_contact(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = followup.run(edited_copy(tmp, 'R027', contact_address=''))
        self.assertIn('R027', outcomes(result, 'review'))
        self.assertNotIn('C017:R027', [a['action_id'] for a in result['actions']])

    def test_unreadable_time_goes_to_review_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = followup.run(edited_copy(tmp, 'R009', last_requested_at='next Tuesday'))
        self.assertIn('R009', outcomes(result, 'review'))

    def test_no_action_input_reports_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = make_fixtures.make_no_action(DATA, Path(tmp) / 'd')
            out = Path(tmp) / 'out'
            run.main(['--data', str(data), '--out', str(out)])
            self.assertEqual(outcomes(followup.run(data), 'eligible'), set())
            with (out / 'proposed_actions.csv').open(encoding='utf-8') as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 0)
            self.assertIn('No follow-up proposed', (out / 'report.md').read_text(encoding='utf-8'))

    def test_unknown_case_goes_to_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = followup.run(edited_copy(tmp, 'R027', case_id='C999'))
        self.assertIn('R027', outcomes(result, 'review'))

    def test_blank_permission_goes_to_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = followup.run(edited_copy(tmp, 'R027', followup_allowed=''))
        self.assertIn('R027', outcomes(result, 'review'))

    def test_request_after_snapshot_goes_to_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = followup.run(edited_copy(tmp, 'R027', last_requested_at='2026-09-08T10:00+05:30'))
        self.assertIn('R027', outcomes(result, 'review'))

    def test_repeat_event_with_different_payload_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = make_fixtures.copy_data(DATA, Path(tmp) / 'd')
            with (data / 'events.csv').open('a', encoding='utf-8', newline='') as stream:
                stream.write('E005,C001,2026-08-25T11:00+05:30,quote_sent,30,Sent repair quote\n')
            effort = followup.run(data)['effort']
        self.assertEqual(effort['conflicting_repeats'], ['E005'])
        self.assertEqual(effort['minutes'], 400)  # first delivery kept, repeat not added

    def test_header_only_input_reports_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'd'
            data.mkdir()
            (data / 'scenario.json').write_bytes((DATA / 'scenario.json').read_bytes())
            for name in ('cases.csv', 'events.csv', 'requests.csv'):
                header = (DATA / name).read_text(encoding='utf-8-sig').splitlines()[0]
                (data / name).write_text(header + '\n', encoding='utf-8')
            out = Path(tmp) / 'out'
            run.main(['--data', str(data), '--out', str(out)])
            self.assertIn('No follow-up proposed', (out / 'report.md').read_text(encoding='utf-8'))

    def test_timezone_less_request_time_goes_to_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = followup.run(edited_copy(tmp, 'R009', last_requested_at='2026-09-02T11:00'))
        self.assertIn('R009', outcomes(result, 'review'))

    def test_unreadable_event_fields_are_flagged_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = make_fixtures.copy_data(DATA, Path(tmp) / 'd')
            with (data / 'events.csv').open('a', encoding='utf-8', newline='') as stream:
                stream.write('E901,C024,yesterday,reminder,2,Manual follow-up recorded\n')
                stream.write('E902,C024,2026-09-04T13:00+05:30,review,2.5,Checked supplied information\n')
            effort = followup.run(data)['effort']
        self.assertEqual(effort['unreadable_time_ids'], ['E901'])
        self.assertEqual(effort['unreadable_minutes_ids'], ['E902'])
        self.assertEqual(effort['minutes'], 402)  # E901's 2 counted; E902's '2.5' unknown

    def test_opted_out_row_with_unknown_case_stays_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = followup.run(edited_copy(tmp, 'R012', case_id='C999'))
        self.assertIn('R012', outcomes(result, 'excluded'))

    def test_later_reminder_in_event_log_resets_the_48h_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = make_fixtures.copy_data(DATA, Path(tmp) / 'd')
            with (data / 'events.csv').open('a', encoding='utf-8', newline='') as stream:
                stream.write('E903,C024,2026-09-06T12:00+05:30,reminder,2,Manual follow-up recorded\n')
            result = followup.run(data)
        self.assertTrue({'R024', 'R026'} <= outcomes(result, 'excluded'))
        self.assertNotIn('C024', [a['case_id'] for a in result['actions']])

    def test_missing_request_time_cites_the_event_log(self):
        result = followup.run(DATA)
        reason = next(d['reason'] for d in result['decisions'] if d['request_id'] == 'R022')
        self.assertIn('E117', reason)

    def test_two_addresses_on_one_case_make_separate_drafts(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = followup.run(edited_copy(tmp, 'R025', contact_address='landlord-009@example.invalid'))
        drafts = {a['action_id']: a['to'] for a in result['actions']}
        self.assertEqual(drafts['C009:R009'], 'case-009@example.invalid')
        self.assertEqual(drafts['C009:R025'], 'landlord-009@example.invalid')

    def test_unknown_item_is_drafted_by_name_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = followup.run(edited_copy(tmp, 'R027', item='warranty_card'))
        draft = next(a for a in result['actions'] if a['action_id'] == 'C017:R027')
        self.assertIn('- warranty_card', draft['draft_body'])

    def test_rerun_does_not_accumulate_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            run.main(['--data', str(DATA), '--out', str(out)])
            first = (out / 'proposed_actions.csv').read_bytes()
            run.main(['--data', str(DATA), '--out', str(out)])
            self.assertEqual((out / 'proposed_actions.csv').read_bytes(), first)


if __name__ == '__main__':
    unittest.main()
