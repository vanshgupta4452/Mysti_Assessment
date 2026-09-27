"""Daybreak Repairs follow-up experiment. DRY RUN: nothing here sends a message.

Reads the supplied CSVs, applies the DATA_DICTIONARY.md contact rules, and
compares the result with two simpler strategies on the same input.
"""
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

CLOSED_OR_BOOKED = {'completed', 'cancelled', 'scheduled'}
OPEN_STATUSES = {'waiting_info', 'quote_sent'}
# Items a no-account file-request link can carry. serial_number assumes the
# customer can photograph a readable label; the technician says old units may not have one.
FILE_ITEMS = {'fault_photo', 'serial_number'}
ITEM_TEXT = {
    'fault_photo': 'a clear photo of the fault',
    'serial_number': 'the model/serial number (a photo of the label is fine)',
    'site_access': 'site access instructions',
    'quote_approval': 'your decision on the repair quote (no rush if you need more time)',
}
CHASE_TYPES = ('request_sent', 'reminder')
# Labelled scenario assumptions for the net value table. None of these are measured.
ASSUMED = {
    'workdays_per_week': 6,
    'list_scan_min_per_day_today': 5.0,
    'queue_run_min_per_day': 3.0,
    'review_min_per_draft': 1.0,
    # Reconciliation: resolving review rows and recording stop requests.
    'review_rows_per_week': 2.0,
    'reconcile_min_per_row': 3.0,
}


def parse_time(value):
    """Parse an ISO 8601 time; a time without a timezone counts as unreadable."""
    if not value:
        return None
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError(f'no timezone in {value!r}')
    return moment


def event_time(event):
    try:
        return parse_time(event['occurred_at'])
    except ValueError:
        return None


def minutes_of(event):
    """Logged whole minutes, or None when blank or unreadable (unknown, never zero)."""
    value = event['active_minutes'].strip()
    return int(value) if value.isdigit() else None


def load_inputs(data_dir):
    data_dir = Path(data_dir)

    def rows(name):
        with (data_dir / name).open(encoding='utf-8-sig', newline='') as stream:
            return list(csv.DictReader(stream))

    scenario = json.loads((data_dir / 'scenario.json').read_text(encoding='utf-8'))
    start = datetime.fromisoformat(scenario['observation_start'])
    end = datetime.fromisoformat(scenario['observation_end'])
    return {
        'scenario': scenario,
        'snapshot': parse_time(scenario['snapshot_at']),
        'gap': timedelta(hours=scenario['minimum_followup_gap_hours']),
        'weeks': ((end - start).days + 1) / 7,
        'cases': {row['case_id']: row for row in rows('cases.csv')},
        'events': rows('events.csv'),
        'requests': rows('requests.csv'),
    }


# ---------------------------------------------------------------- effort

def dedupe_events(events):
    """Keep the first delivery of each event_id; repeats are export noise, not work."""
    unique, repeats, conflicts = {}, [], []
    for event in events:
        first = unique.get(event['event_id'])
        if first is None:
            unique[event['event_id']] = event
            continue
        repeats.append(event['event_id'])
        if event != first:
            conflicts.append(event['event_id'])
    return list(unique.values()), repeats, conflicts


def logged_minutes(events):
    return sum(m for m in map(minutes_of, events) if m is not None)


def effort_summary(inputs):
    events = inputs['events']
    unique, repeats, conflicts = dedupe_events(events)
    by_type = defaultdict(lambda: {'events': 0, 'minutes': 0, 'unknown': 0})
    for event in unique:
        row = by_type[event['event_type']]
        row['events'] += 1
        minutes = minutes_of(event)
        if minutes is None:
            row['unknown'] += 1
        else:
            row['minutes'] += minutes
    chase = sum(by_type[t]['minutes'] for t in CHASE_TYPES)
    return {
        'rows': len(events),
        'unique': len(unique),
        'repeat_ids': sorted(set(repeats)),
        'conflicting_repeats': sorted(set(conflicts)),
        'minutes_raw': logged_minutes(events),
        'minutes': logged_minutes(unique),
        'blank_ids': [e['event_id'] for e in unique if e['active_minutes'].strip() == ''],
        'unreadable_minutes_ids': [e['event_id'] for e in unique
                                   if e['active_minutes'].strip() and minutes_of(e) is None],
        'unreadable_time_ids': [e['event_id'] for e in unique if event_time(e) is None],
        'by_type': dict(by_type),
        'chase_minutes': chase,
        'chase_min_per_week': chase / inputs['weeks'],
        'reminders_per_week': by_type['reminder']['events'] / inputs['weeks'],
        'cases_per_week': len(inputs['cases']) / inputs['weeks'],
        'unique_events': unique,
    }


def audit_reminders(inputs, unique_events):
    """Check each logged reminder against the 48h gap and today's permission flag."""
    allowed = defaultdict(set)
    for request in inputs['requests']:
        allowed[request['case_id']].add(request['followup_allowed'])
    last_ask, findings = {}, []
    timed = [(e, event_time(e)) for e in unique_events if e['event_type'] in CHASE_TYPES]
    for event, when in sorted(((e, t) for e, t in timed if t is not None),
                              key=lambda pair: (pair[0]['case_id'], pair[1])):
        if event['event_type'] == 'reminder':
            flags = []
            previous = last_ask.get(event['case_id'])
            gap_h = (when - previous).total_seconds() / 3600 if previous else None
            if gap_h is not None and gap_h < inputs['gap'].total_seconds() / 3600:
                flags.append(f'only {gap_h:.0f}h after the previous ask')
            if '0' in allowed[event['case_id']]:
                flags.append('case is now marked do-not-follow-up (opt-out date unknown)')
            findings.append({'event_id': event['event_id'], 'case_id': event['case_id'],
                             'gap_hours': gap_h, 'flags': flags})
        last_ask[event['case_id']] = when
    return findings


# ---------------------------------------------------------------- rules

def latest_chase_events(unique_events):
    """Latest readable request_sent/reminder per case in the event log: {case_id: (time, event_id)}."""
    latest = {}
    for event in unique_events:
        when = event_time(event)
        if event['event_type'] in CHASE_TYPES and when is not None:
            if event['case_id'] not in latest or when > latest[event['case_id']][0]:
                latest[event['case_id']] = (when, event['event_id'])
    return latest


def classify(request, cases, snapshot, gap, last_event=None):
    """Return (outcome, reason); outcome is 'eligible', 'review' or 'excluded'.

    Opted-out rows, then closed/booked cases, are checked first so they stay
    excluded even when another field is uncertain (DATA_DICTIONARY rule 4).
    last_event is the case's latest chase in events.csv; a later one restarts
    the 48h clock, because request fields can lag (rule 3).
    """
    if request['followup_allowed'] == '0':
        return 'excluded', 'customer opted out (followup_allowed=0)'
    case = cases.get(request['case_id'])
    if case is None:
        return 'review', 'case not found in cases.csv'
    if case['status'] in CLOSED_OR_BOOKED:
        return 'excluded', f"case is {case['status']}"
    if case['status'] not in OPEN_STATUSES:
        return 'review', f"unknown case status {case['status']!r}"
    if request['followup_allowed'] != '1':
        return 'review', f"follow-up permission unknown ({request['followup_allowed']!r})"
    if request['received_at']:
        if request['status'] == 'pending':
            return 'review', f"status is pending but received_at={request['received_at']}"
        return 'excluded', 'already received'
    if request['status'] == 'received':
        return 'excluded', 'already received (no received_at recorded)'
    if request['status'] != 'pending':
        return 'review', f"unknown request status {request['status']!r}"
    if not request['contact_address'] or request['channel'] != 'email':
        return 'review', 'no usable email contact'
    try:
        last = parse_time(request['last_requested_at'])
    except ValueError:
        return 'review', f"unreadable last_requested_at {request['last_requested_at']!r}"
    if last is None:
        seen = f'; events.csv shows {last_event[1]} at {last_event[0].isoformat()}' if last_event else ''
        return 'review', f'last request time missing{seen}'
    via = ''
    if last_event and last_event[0] > last:
        last, via = last_event[0], f' (later ask {last_event[1]} in events.csv)'
    if last > snapshot:
        return 'review', f'last request is after the snapshot{via}'
    hours = (snapshot - last).total_seconds() / 3600
    if snapshot - last < gap:
        return 'excluded', f'asked {hours:.1f}h ago{via}; eligible from {(last + gap).isoformat()}'
    return 'eligible', f'pending, last asked {hours:.1f}h ago{via}, follow-up allowed'


def decide(inputs):
    unique, _, _ = dedupe_events(inputs['events'])
    latest = latest_chase_events(unique)
    decisions = []
    for request in sorted(inputs['requests'], key=lambda r: r['request_id']):
        outcome, reason = classify(request, inputs['cases'], inputs['snapshot'], inputs['gap'],
                                   latest.get(request['case_id']))
        case = inputs['cases'].get(request['case_id'], {})
        decisions.append({
            'request_id': request['request_id'],
            'case_id': request['case_id'],
            'item': request['item'],
            'case_status': case.get('status', ''),
            'request_status': request['status'],
            'outcome': outcome,
            'reason': reason,
        })
    return decisions


def propose_actions(inputs, decisions):
    """One draft per case and address; the action_id is stable across reruns."""
    by_id = {r['request_id']: r for r in inputs['requests']}
    groups = defaultdict(list)
    for decision in decisions:
        if decision['outcome'] == 'eligible':
            request = by_id[decision['request_id']]
            groups[(request['case_id'], request['contact_address'])].append((request, decision))
    actions = []
    for (case_id, address), pairs in sorted(groups.items()):
        ids = [request['request_id'] for request, _ in pairs]
        wanted = '\n'.join(f"- {ITEM_TEXT.get(r['item'], r['item'])}" for r, _ in pairs)
        actions.append({
            'action_id': f"{case_id}:{'+'.join(ids)}",
            'case_id': case_id,
            'request_ids': ' '.join(ids),
            'to': address,
            'mode': 'DRY RUN - draft only, not sent',
            'reason': ' | '.join(f"{d['request_id']} {d['item']}: {d['reason']}" for _, d in pairs),
            'draft_subject': f'Daybreak Repairs {case_id}: still needed for your repair',
            'draft_body': (f'Hello,\n\nTo move repair case {case_id} forward we still need:\n{wanted}\n\n'
                           'If you have already sent this, reply "sent" and we will stop asking.\n'
                           'Reply "stop" if you do not want further reminders.\n\nDaybreak Repairs'),
        })
    return actions


# ---------------------------------------------------------------- comparison

def strategy_current_list(inputs):
    """B0 baseline: the coordinator's list as exported - every request still marked pending."""
    return {r['request_id'] for r in inputs['requests'] if r['status'] == 'pending'}


def strategy_spreadsheet_filter(inputs):
    """P: process-only filter on the status, permission and date columns (no conflict check)."""
    cutoff = inputs['snapshot'] - inputs['gap']
    picked = set()
    for request in inputs['requests']:
        case = inputs['cases'].get(request['case_id'])
        try:
            last = parse_time(request['last_requested_at'])
        except ValueError:
            last = None
        if (request['status'] == 'pending' and case is not None
                and case['status'] not in CLOSED_OR_BOOKED
                and request['followup_allowed'] == '1'
                and last is not None and last <= cutoff):
            picked.add(request['request_id'])
    return picked


def score(proposed, decisions):
    """Measure one strategy against the published contact rules."""
    outcome = {d['request_id']: d['outcome'] for d in decisions}
    return {
        'proposed': len(proposed),
        'breaks_rules': sorted(i for i in proposed if outcome[i] != 'eligible'),
        'eligible_missed': sorted(i for i, o in outcome.items() if o == 'eligible' and i not in proposed),
    }


def compare(inputs, decisions):
    rules = {d['request_id'] for d in decisions if d['outcome'] == 'eligible'}
    review = sorted(d['request_id'] for d in decisions if d['outcome'] == 'review')
    rows = []
    for name, proposed, flags_review in (
            ('B0 current pending list', strategy_current_list(inputs), False),
            ('P  spreadsheet filter', strategy_spreadsheet_filter(inputs), False),
            ('M  rules queue', rules, True)):
        row = score(proposed, decisions)
        row['name'] = name
        row['review_unflagged'] = [] if flags_review else [i for i in review if i not in proposed]
        rows.append(row)
    return rows


def file_request_check(inputs, decisions):
    """Technical-claim check: how much of today's chase could a file-request link take over?

    Local arithmetic only. That the free plan sends no reminders is inferred from
    the vendor documentation (see SOURCES.md), not tested by this code.
    """
    by_id = {r['request_id']: r for r in inputs['requests']}
    eligible = [by_id[d['request_id']] for d in decisions if d['outcome'] == 'eligible']
    carried = sorted(r['request_id'] for r in eligible if r['item'] in FILE_ITEMS)
    not_carried = sorted(r['request_id'] for r in eligible if r['item'] not in FILE_ITEMS)
    blocked_cases = {r['case_id'] for r in eligible if r['item'] not in FILE_ITEMS}
    fully = sorted({r['case_id'] for r in eligible} - blocked_cases)
    conflicts = sorted(d['request_id'] for d in decisions
                       if d['outcome'] == 'review' and by_id[d['request_id']]['item'] in FILE_ITEMS
                       and by_id[d['request_id']]['received_at'])
    return {'eligible': len(eligible), 'carried': carried, 'not_carried': not_carried,
            'cases_fully_covered': fully, 'receipt_conflicts_link_could_prevent': conflicts}


def net_value(effort, actions_count):
    a = ASSUMED
    per_week_scan = a['workdays_per_week'] * (a['list_scan_min_per_day_today'] - a['queue_run_min_per_day'])
    mean_reminder = (effort['by_type'].get('reminder', {}).get('minutes', 0)
                     / max(effort['by_type'].get('reminder', {}).get('events', 0), 1))
    per_week_drafts = (effort['reminders_per_week'] * (mean_reminder - a['review_min_per_draft'])
                       if effort['reminders_per_week'] else 0.0)
    reconcile = a['review_rows_per_week'] * a['reconcile_min_per_row']
    return {'mean_reminder_min': mean_reminder, 'scan_saving': per_week_scan,
            'draft_saving': per_week_drafts, 'reconcile_cost': reconcile,
            'net_min_per_week': per_week_scan + per_week_drafts - reconcile,
            'tool_cost_inr_per_month': 0, 'actions_now': actions_count}


# ---------------------------------------------------------------- report

def run(data_dir):
    inputs = load_inputs(data_dir)
    effort = effort_summary(inputs)
    decisions = decide(inputs)
    actions = propose_actions(inputs, decisions)
    result = {
        'inputs': inputs, 'effort': effort, 'decisions': decisions, 'actions': actions,
        'audit': audit_reminders(inputs, effort['unique_events']),
        'comparison': compare(inputs, decisions),
        'claim': file_request_check(inputs, decisions),
        'value': net_value(effort, len(actions)),
    }
    result['report'] = render_report(result)
    return result


def _ids(values):
    return ', '.join(values) if values else 'none'


def render_report(r):
    e, v, c, inputs = r['effort'], r['value'], r['claim'], r['inputs']
    counts = defaultdict(int)
    for d in r['decisions']:
        counts[d['outcome']] += 1
    lines = [
        '# Daybreak follow-up experiment (dry run - nothing sent)',
        '',
        f"Snapshot: {inputs['scenario']['snapshot_at']} (from scenario.json, not the computer clock)",
        '',
        '## 1. Event export and logged effort',
        f"- Event rows {e['rows']}, unique event_id {e['unique']}; repeated IDs: {_ids(e['repeat_ids'])}",
        f"- Repeats with a different payload: {_ids(e['conflicting_repeats'])}",
        f"- Logged coordinator minutes: {e['minutes_raw']} with repeats, {e['minutes']} after de-duplication",
        f"- Blank (unknown) minutes, not counted as zero: {_ids(e['blank_ids'])}",
        f"- Unreadable minutes, treated as unknown: {_ids(e['unreadable_minutes_ids'])}",
        f"- Unreadable event times, left out of the reminder audit and 48h clock: {_ids(e['unreadable_time_ids'])}",
        '',
        '| event_type | events | logged min | unknown min |',
        '| --- | ---: | ---: | ---: |',
    ]
    for kind, row in sorted(e['by_type'].items()):
        lines.append(f"| {kind} | {row['events']} | {row['minutes']} | {row['unknown']} |")
    per_case = (f"{480 / e['cases_per_week']:.0f} min of chasing per case"
                if e['cases_per_week'] else 'n/a (no cases)')
    lines += [
        '',
        '## 2. The eight-hour premise',
        f"- Chase minutes (request_sent + reminder): {e['chase_minutes']} = {e['chase_min_per_week']:.0f} min/week",
        f"- All logged admin: {e['minutes'] / inputs['weeks'] / 60:.2f} h/week",
        f"- Owner's claim 480 min/week = {per_case} ({e['cases_per_week']:.0f} cases opened/week)",
        f"- Reminders logged: {e['by_type'].get('reminder', {}).get('events', 0)} "
        f"({e['reminders_per_week']:.1f}/week)",
        '- Limitation: the coordinator does not log quick phone calls, so these are lower bounds.',
        '',
        'Audit of logged reminders against today\'s rules:',
    ]
    for f in r['audit']:
        gap = 'n/a' if f['gap_hours'] is None else f"{f['gap_hours']:.0f}h"
        lines.append(f"- {f['event_id']} {f['case_id']} gap {gap}: {'; '.join(f['flags']) or 'ok'}")
    lines += [
        '',
        '## 3. Rules queue at the snapshot',
        f"- Requests {len(r['decisions'])}: eligible {counts['eligible']}, review {counts['review']}, "
        f"excluded {counts['excluded']}",
        f"- Proposed drafts (combined per case): {len(r['actions'])}",
    ]
    if not r['actions']:
        lines.append('- No follow-up proposed for this input. Nothing to send.')
    for a in r['actions']:
        lines.append(f"  - {a['action_id']} -> {a['to']}")
    for d in r['decisions']:
        if d['outcome'] == 'review':
            lines.append(f"- REVIEW {d['request_id']} {d['case_id']}: {d['reason']}")
    lines += [
        '',
        '## 4. Baseline comparison (same input, measured against the published contact rules)',
        '',
        '| strategy | proposed rows | breaks a rule | eligible missed | needs-review not flagged |',
        '| --- | ---: | --- | --- | --- |',
    ]
    for row in r['comparison']:
        lines.append(f"| {row['name']} | {row['proposed']} | {len(row['breaks_rules'])}: {_ids(row['breaks_rules'])} "
                     f"| {_ids(row['eligible_missed'])} | {_ids(row['review_unflagged'])} |")
    lines += [
        '',
        '## 5. Technical claim check: can a no-account file-request link take over the chase?',
        f"- Eligible items: {c['eligible']}; a file link can carry {len(c['carried'])} ({_ids(c['carried'])})",
        f"- Not a file, so a link cannot carry: {_ids(c['not_carried'])}",
        f"- Cases a link alone could fully cover: {_ids(c['cases_fully_covered'])}",
        f"- Receipt conflicts a link upload could have prevented (if used): "
        f"{_ids(c['receipt_conflicts_link_could_prevent'])}",
        '- Inferred from documentation, NOT tested here: Dropbox mentions reminder emails only with '
        'deadlines, which are paid-tier only, so the free plan appears to send none; reminder timing '
        'is undocumented.',
        '',
        '## 6. Net value of the rules queue (minutes per week)',
        f"- MEASURED mean minutes per logged reminder: {v['mean_reminder_min']:.2f}",
        f"- ASSUMED {ASSUMED['workdays_per_week']} workdays, list scan {ASSUMED['list_scan_min_per_day_today']} min/day today, "
        f"queue run {ASSUMED['queue_run_min_per_day']} min/day, review {ASSUMED['review_min_per_draft']} min/draft",
        f"- ASSUMED reconciliation: {ASSUMED['review_rows_per_week']} review rows/week x "
        f"{ASSUMED['reconcile_min_per_row']} min (resolving conflicts, recording stop requests)",
        f"- Scan saving {v['scan_saving']:.1f} + draft saving {v['draft_saving']:.1f} "
        f"- reconciliation {v['reconcile_cost']:.1f} = NET {v['net_min_per_week']:.1f} min/week "
        '(mostly driven by the unmeasured list-scan time)',
        f"- Tool cost: INR {v['tool_cost_inr_per_month']}/month (standard-library script, no subscription)",
        '',
        '## What this proves and does not prove',
        '- Proves: on this input the rules separate eligible, review and excluded rows reproducibly, '
        'and the simpler strategies would break the published contact rules as listed above.',
        '- Does not prove: that customers reply faster, that the coordinator saves the assumed minutes, '
        'or that customers would use a file-request link.',
    ]
    return '\n'.join(lines) + '\n'
