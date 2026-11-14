"""Tests built from the pilot facts in the build plan (section 7) plus the
pitfalls in section 2. Run after the collector:  python3 -m unittest discover tests
"""
import os, sqlite3, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "collector"))
from collect import categorize, find_amounts, norm_vote  # noqa: E402

DB = os.path.join(ROOT, "data", "council.sqlite")


class Parsing(unittest.TestCase):
    def test_amounts(self):
        self.assertEqual(find_amounts("contract in the amount of $766,662.00 for the park"), [766662.0])
        self.assertEqual(find_amounts("not to exceed $13,805,000 aggregate"), [13805000.0])
        self.assertEqual(find_amounts("from $1.5 million to $2 million"), [1500000.0, 2000000.0])
        self.assertEqual(find_amounts("Section 18-64(b) of the Code"), [])

    def test_votes(self):
        self.assertEqual(norm_vote("Yes"), "Yes")
        self.assertEqual(norm_vote("Excused"), "Excused")
        self.assertEqual(norm_vote(None), "Not recorded")

    def test_categories(self):
        self.assertEqual(categorize("Resolution authorizing General Obligation Promissory Notes", "Resolution"), "Borrowing")
        self.assertEqual(categorize("Report of Bids and Resolution awarding contract to X", "Report of Bids"), "Contracts and purchases")
        self.assertEqual(categorize("Amending Tax Incremental District 17", "Resolution"), "TIF districts")


@unittest.skipUnless(os.path.exists(DB), "run the collector first")
class PilotFacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = sqlite3.connect(DB)

    def one(self, sql, *a):
        return self.db.execute(sql, a).fetchone()

    def council_action(self, file_no, date, action):
        return self.one("""SELECT a.result, a.yes, a.no, a.excused, a.has_roll_call FROM actions a
            JOIN items i ON i.id = a.item_id WHERE i.file_number=? AND a.date=? AND a.action=?
            AND a.body_id=138""", file_no, date, action)

    def test_sept_10_has_34_item_rows(self):
        n = self.one("""SELECT COUNT(*) FROM actions a JOIN meetings m ON m.id=a.meeting_id
            WHERE m.date='2026-09-10' AND m.body_id=138 AND m.time='6:00 PM'""")[0]
        self.assertEqual(n, 34)

    def test_bills_and_estimates_13_to_0(self):
        self.assertEqual(self.council_action("26-0950", "2026-09-10", "ADOPTED"), ("Pass", 13, 0, 0, 1))

    def test_administrator_charter_ordinance_failed_with_five_no(self):
        r = self.council_action("26-0741", "2026-08-13", "ADOPTED AS AMENDED")
        self.assertEqual(r[0], "Fail")
        self.assertEqual(r[2], 5)

    def test_two_actions_same_night_stay_separate(self):
        # Pitfall 1: 26-0879 has two action rows on 9/10; keyed on history id, neither is lost or doubled.
        n = self.one("""SELECT COUNT(*), COUNT(DISTINCT a.history_id) FROM actions a JOIN items i ON i.id=a.item_id
            WHERE i.file_number='26-0879' AND a.date='2026-09-10' AND a.body_id=138""")
        self.assertEqual(n, (2, 2))
        self.assertEqual(self.one("SELECT COUNT(*) FROM votes GROUP BY action_id, person_id HAVING COUNT(*)>1"), None)

    def test_budget_scheduled_nov_16(self):
        r = self.one("""SELECT a.date FROM actions a JOIN items i ON i.id=a.item_id
            WHERE i.file_number='26-0588' AND a.body_id=138 ORDER BY a.date DESC""")
        self.assertEqual(r[0], "2026-11-16")

    def test_excused_is_not_a_vote(self):
        # Pitfall 6: tallies must add up, with Excused kept out of yes and no.
        bad = self.one("""SELECT COUNT(*) FROM actions a WHERE has_roll_call=1 AND
            yes + no != (SELECT COUNT(*) FROM votes v WHERE v.action_id=a.history_id AND v.vote IN ('Yes','No'))""")[0]
        self.assertEqual(bad, 0)

    def test_thirteen_council_members_and_a_mayor(self):
        self.assertEqual(self.one("SELECT COUNT(*) FROM people WHERE role='Council Member'")[0], 13)
        self.assertEqual(self.one("SELECT COUNT(*) FROM people WHERE role='Mayor'")[0], 1)

    def test_every_record_has_a_source_link(self):
        for t in ("items", "actions", "meetings"):
            self.assertEqual(self.one(f"SELECT COUNT(*) FROM {t} WHERE source_url IS NULL OR source_url=''")[0], 0, t)

    def test_no_fetch_errors(self):
        self.assertEqual(self.one("SELECT value FROM meta WHERE key='fetch_errors'")[0], "0")


if __name__ == "__main__":
    unittest.main()
