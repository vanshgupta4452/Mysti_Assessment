# Daybreak follow-up experiment (dry run - nothing sent)

Snapshot: 2026-09-07T11:00:00+05:30 (from scenario.json, not the computer clock)

## 1. Event export and logged effort
- Event rows 128, unique event_id 124; repeated IDs: E005, E032, E059, E087
- Repeats with a different payload: none
- Logged coordinator minutes: 412 with repeats, 400 after de-duplication
- Blank (unknown) minutes, not counted as zero: E002, E035, E081
- Unreadable minutes, treated as unknown: none
- Unreadable event times, left out of the reminder audit and 48h clock: none

| event_type | events | logged min | unknown min |
| --- | ---: | ---: | ---: |
| cancelled | 3 | 3 | 0 |
| completed | 8 | 8 | 0 |
| customer_reply | 16 | 0 | 1 |
| intake | 24 | 146 | 0 |
| quote_sent | 18 | 54 | 0 |
| reminder | 4 | 9 | 0 |
| request_sent | 24 | 69 | 1 |
| review | 15 | 78 | 0 |
| scheduled | 12 | 33 | 1 |

## 2. The eight-hour premise
- Chase minutes (request_sent + reminder): 78 = 39 min/week
- All logged admin: 3.33 h/week
- Owner's claim 480 min/week = 40 min of chasing per case (12 cases opened/week)
- Reminders logged: 4 (2.0/week)
- Limitation: the coordinator does not log quick phone calls, so these are lower bounds.

Audit of logged reminders against today's rules:
- E055 C009 gap 122h: ok
- E071 C012 gap 118h: case is now marked do-not-follow-up (opt-out date unknown)
- E091 C016 gap 119h: ok
- E099 C018 gap 24h: only 24h after the previous ask

## 3. Rules queue at the snapshot
- Requests 30: eligible 7, review 2, excluded 21
- Proposed drafts (combined per case): 5
  - C009:R009+R025 -> case-009@example.invalid
  - C016:R016 -> case-016@example.invalid
  - C017:R027 -> case-017@example.invalid
  - C023:R029 -> case-023@example.invalid
  - C024:R024+R026 -> case-024@example.invalid
- REVIEW R018 C018: status is pending but received_at=2026-09-03T14:00+05:30
- REVIEW R022 C022: last request time missing; events.csv shows E117 at 2026-09-03T12:00:00+05:30

## 4. Baseline comparison (same input, measured against the published contact rules)

| strategy | proposed rows | breaks a rule | eligible missed | needs-review not flagged |
| --- | ---: | --- | --- | --- |
| B0 current pending list | 15 | 8: R001, R005, R012, R013, R018, R019, R022, R028 | none | none |
| P  spreadsheet filter | 8 | 1: R018 | none | R022 |
| M  rules queue | 7 | 0: none | none | none |

## 5. Technical claim check: can a no-account file-request link take over the chase?
- Eligible items: 7; a file link can carry 4 (R009, R016, R024, R026)
- Not a file, so a link cannot carry: R025, R027, R029
- Cases a link alone could fully cover: C016, C024
- Receipt conflicts a link upload could have prevented (if used): R018
- Inferred from documentation, NOT tested here: Dropbox mentions reminder emails only with deadlines, which are paid-tier only, so the free plan appears to send none; reminder timing is undocumented.

## 6. Net value of the rules queue (minutes per week)
- MEASURED mean minutes per logged reminder: 2.25
- ASSUMED 6 workdays, list scan 5.0 min/day today, queue run 3.0 min/day, review 1.0 min/draft
- ASSUMED reconciliation: 2.0 review rows/week x 3.0 min (resolving conflicts, recording stop requests)
- Scan saving 12.0 + draft saving 2.5 - reconciliation 6.0 = NET 8.5 min/week (mostly driven by the unmeasured list-scan time)
- Tool cost: INR 0/month (standard-library script, no subscription)

## What this proves and does not prove
- Proves: on this input the rules separate eligible, review and excluded rows reproducibly, and the simpler strategies would break the published contact rules as listed above.
- Does not prove: that customers reply faster, that the coordinator saves the assumed minutes, or that customers would use a file-request link.
