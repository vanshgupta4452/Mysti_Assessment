# Handover

- Name: Vansh Gupta
- Email used for this application: vansh4452@gmail.com
- Chosen track: Track B, Find the worthwhile automation
- Why this track: it matches how I work — form a claim, check it against primary sources, then build the smallest thing that could prove me wrong, instead of taking the owner's eight-hour estimate as given.
- Approximate total time, including setup and handover: CONFIRM-ELAPSED-HOURS (cap: 4 hours)

## Run and verify

Python 3.10+ standard library; no credentials, network or install step. From this directory (`py`/`python3` work too). Verified on 3.10.12 (Linux), 3.11.15 (Windows 10). `README.md` is the run guide; `BRIEF.md` the brief.

```text
python -m unittest discover -s tests
python run.py
python make_fixtures.py
python run.py --data fixtures/changed_48h --out out/changed_48h
python run.py --data fixtures/no_action --out out/no_action
```

Expected:

```text
Ran 26 tests ... OK
requests=30 eligible=5 review=2 excluded=23 drafts=3
wrote fixtures/changed_48h and fixtures/no_action
requests=30 eligible=7 review=2 excluded=21 drafts=5
requests=30 eligible=0 review=0 excluded=30 drafts=0
No follow-up proposed for this input.
```

Each run writes `report.md`, `decisions.csv` (every request with its reason) and `proposed_actions.csv` (unsent drafts) to `--out`.

## What I delivered

A dry-run follow-up queue applying the published contact rules, with two baselines and a file-request claim check. Recommendation: process change plus the script; no build, no purchase yet. See `DECISION.md`, `SOURCES.md`.

## Evidence and limits

- **Technical claim:** `test_claim_file_link_cannot_carry_the_whole_chase`; `out/report.md` section 5.
- **Baseline:** `test_baseline_comparison`; section 4. The pending list breaks 10 rules, a spreadsheet filter 1, the queue 0. All three are scored against the queue's own rules, so this counts breaks rather than proving the queue right; the 4-reminder audit (section 2) is the independent check.
- **No-action:** `test_no_action_input_reports_cleanly`; `out/no_action/`.
- **Net value:** `DECISION.md`.
- **Changed input:** snapshot 09:00 → 11:00. Predicted: R016 and R029 reach exactly 48.0 h, so eligible 5 → 7, drafts 3 → 5 (C016, C023), breaks 10 → 8. Observed: identical (`out/changed_48h/`). Doubles as the "exactly 48 hours" edge case.
- **Tests catch bugs:** `python mutation_check.py` breaks eight rules one at a time in a temp copy; each ends `CAUGHT by <test>`.
- **Independent review:** a second Claude reviewer found crashes (header-only input, timezone-less times, decimal minutes), an opt-out edge case, an ignored event-log reminder and a missing reconciliation cost — each fixed after a test failed first.
**Tested vs assumed:** rule outcomes and counts are tested. Minutes saved, workdays, link adoption and the Dropbox INR price are assumed. Two synthetic weeks; calls are unlogged. **Interpretation:** a later `request_sent` or `reminder` in `events.csv` restarts the 48-hour clock for that case's whole request set — conservative; a per-request reading of rule 3 could chase sooner.

**Known gap:** the no-action fixture overwrites R018's `received_at` (no effect).

**Open question:** did C012 opt out before or after reminder E071?

**Next step:** the 10-day pilot in `DECISION.md`.

## Tools and judgment

- **Claude Opus 5.5 (Claude Code)** analysed the data, drafted the plan and code, ran the checks; I reviewed each decision.
- Claude said the pending list makes 12 wrong contacts; the pinned test showed 10, so I corrected it.
- Claude expected Dropbox file requests to send no reminders; the help page mentions deadline reminders, so the verdict became "partial, timing undocumented".
- I asked why nothing uses AI. I kept rules over an LLM (the owner values fewer mistakes; drafting takes ~2 min twice a week) and added an explicit "Can AI fix this?" answer to `DECISION.md`.
