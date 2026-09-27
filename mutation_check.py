"""Evidence that the tests catch rule breaks: break one rule at a time in a temp copy, run the suite.

Run from track-b: python mutation_check.py
Each line should end in CAUGHT with the names of the failing tests.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

MUTANTS = {
    'M1 exactly 48h no longer eligible': ('if snapshot - last < gap:', 'if snapshot - last <= gap:'),
    'M2 scheduled cases treated as open': ("CLOSED_OR_BOOKED = {'completed', 'cancelled', 'scheduled'}",
                                          "CLOSED_OR_BOOKED = {'completed', 'cancelled'}"),
    'M3 repeat deliveries add effort': ("'minutes': logged_minutes(unique),", "'minutes': logged_minutes(events),"),
    'M4 pending+received conflict excluded, not reviewed': (
        "return 'review', f\"status is pending but received_at", "return 'excluded', f\"status is pending but received_at"),
    'M5 opt-out ignored': ("    if request['followup_allowed'] == '0':\n"
                           "        return 'excluded', 'customer opted out (followup_allowed=0)'\n", ""),
    'M6 later event-log reminder ignored': ('if last_event and last_event[0] > last:', 'if False:'),
    'M7 drafts ignore contact address': ("groups[(request['case_id'], request['contact_address'])]",
                                         "groups[(request['case_id'], 'one')]"),
    'M8 unknown item crashes': ("ITEM_TEXT.get(r['item'], r['item'])", "ITEM_TEXT[r['item']]"),
}


def main():
    all_caught = True
    for name, (old, new) in MUTANTS.items():
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'tb'
            shutil.copytree(HERE, copy, ignore=shutil.ignore_patterns('__pycache__', 'out', 'fixtures'))
            source = copy / 'followup.py'
            text = source.read_text(encoding='utf-8')
            if old not in text:
                print(f'{name}: pattern not found, check followup.py')
                all_caught = False
                continue
            source.write_text(text.replace(old, new, 1), encoding='utf-8')
            result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'],
                                    cwd=copy, capture_output=True, text=True)
            failed = sorted({line.split()[1] for line in result.stderr.splitlines()
                             if line.startswith(('FAIL:', 'ERROR:'))})
            print(f"{name}: {'CAUGHT by ' + ', '.join(failed) if failed else 'NOT CAUGHT'}")
            all_caught = all_caught and bool(failed)
    print('all mutants caught' if all_caught else 'SOME MUTANTS SURVIVED')
    return 0 if all_caught else 1


if __name__ == '__main__':
    sys.exit(main())
