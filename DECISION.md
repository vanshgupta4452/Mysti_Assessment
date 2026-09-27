# Decision: Daybreak follow-up of missing information

Numbers below come from `python run.py` (see `out/report.md`) and are pinned by `tests/test_followup.py`. Sources are in `SOURCES.md`.

## User, workflow and problem

The user is the coordinator. The workflow is the daily follow-up of outstanding customer requests: fault photos, serial numbers and site access (the three quote approvals pass through the same contact rules). The owner asked for AI to "handle it all" because chasing costs eight hours a week. The data points to a different problem: chasing time is small, but the list the coordinator works from is wrong in ways that cause bad reminders.

Data treatment: each `event_id` counts once (four repeated deliveries removed, all identical). Blank minutes are unknown and left out, never zero. The clock is the snapshot, 7 September 09:00 IST. A request counts as missing only if its case is open, follow-up is allowed and no `received_at` is recorded; "pending" alone is not trusted.

## What the data shows

| Calculation | Result |
| --- | --- |
| Logged coordinator minutes, 14 days | 400 after de-duplication (412 before) = 3.3 h/week of all admin |
| Chasing (`request_sent` + `reminder`) | 78 min = 39 min/week; the claimed 480 would be 40 min per case per week (12 cases/week) |
| Requests at the snapshot | 30: 5 eligible (3 cases), 2 review, 23 excluded |
| "Chase every pending row" | 15 proposals, 10 break a rule (4 closed, 2 opted out, 2 under 48 h, 1 conflicting receipt, 1 missing time) |

Of the four reminders actually logged, one came 24 hours after the request and one went to a case now marked do-not-contact. The data is weak: two synthetic weeks, four reminders, and quick calls are not logged. The eight-hour figure is therefore unmeasured rather than disproved.

## Technical claim

"A no-account file-request link can take over the photo chase." Dropbox and Microsoft documentation confirm that customers can upload without an account and that the requester gets an email per upload. OneDrive's version needs a business account with admin enablement. Dropbox mentions reminder emails only with deadlines, which need a paid tier, and does not say when they are sent. The key constraint: a link collects files; it does not decide who to chase. On the snapshot, a link could carry 3 of 5 eligible items; site access and a quote decision are not files, and only one case could be closed by a link alone. Demonstrated locally: this coverage count. From documentation only: account, notification and reminder behaviour. Assumed: customers would use a link; the repeat customer prefers plain email.

## Alternatives

| Option | Capability | Constraint | Cost |
| --- | --- | --- | --- |
| Build (2 weeks) | Auto-draft and send, parse replies | Needs reliable receipt detection; saves ~2 min per reminder at 2/week | ~80 h + upkeep |
| Dropbox file request | No-account upload, email per upload | Files only; paid-tier deadline reminders; not rule-aware | Basic free; Standard USD 15/user/month (INR unverified) |
| Process only (saved replies + spreadsheet filter) | Removes 9 of the 10 rule breaks | Misses the R018 conflict; drops R022 silently; needs records kept current | INR 0 |
| Process change + script | Rules applied daily with reasons; flags conflicts for review | Needs records kept current; script upkeep not costed | INR 0, ~3 min/day incl. export (assumed) |

## Recommendation

Change the process and keep the small rules script; do not spend the two engineering weeks and do not buy a tool yet. Rules: never chase scheduled or closed cases, record stop requests the same day, check `received_at` and the inbox before chasing, wait 48 hours, and combine asks per case. Over a plain filter, the script adds only the R018 conflict check and keeps the missing-time row visible.

On the owner's question, "Can AI fix this?": not now. The mistakes come from stale fields that fixed rules catch. Writing a reminder takes about two minutes and happens twice a week, so an AI writer would save little, and every draft would still need checking. AI becomes worth testing only if the pilot shows many free-text replies that need reading, such as photos or stop requests arriving in other threads.

Strongest evidence against: unlogged calls could hide most of the chasing, and the process relies on the record-keeping that fails today. What would change my mind: pilot chasing of at least 90 minutes a week with at least 10 eligible follow-ups a week, or more than one reminder-after-receipt a week.

## Net value

```text
Net min/week = workdays x (scan today - queue run) + reminders x (min per reminder - review)
               - review rows x reconcile min
             = 6 x (5 - 3) + 2.0 x (2.25 - 1.0) - 2 x 3 = 8.5 min/week; tool cost INR 0
```

Measured: 2 reminders/week, 2.25 min each. Assumed: 6 workdays, 5 min scan, 3 min run including the sheet export, 1 min review per draft, and two review rows a week at 3 min each to reconcile conflicts and record stop requests. Script upkeep is not counted. With a 3-minute scan the result turns negative (-3.5). A 10-day build (~80 h) would need about 92 min/week to pay back within a year. Quote value is not revenue and is not counted.

## Next experiment

For 10 working days the coordinator logs every chase touch, including calls, and each morning writes down who they would chase before opening the queue. Continue toward build or buy only if chasing is at least 90 min/week and there are at least 10 eligible follow-ups a week; otherwise stop and keep the process. Quality gate: zero reminders to closed, opted-out or received items, and at least 90% agreement between the queue and the coordinator.
