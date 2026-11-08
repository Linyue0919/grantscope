"""Unit tests for the Alerts page helpers (ui/alerts_data.py) and the Profile compatibility shim.

Run: python -m unittest discover -s tests -v
"""
import unittest
from datetime import date

from ui import alerts_data as ad
from ui.view_model import CONFIRMED, NOT_STATED, OpportunityView

TODAY = date(2026, 11, 8)  # a Sunday


def view(**overrides):
    base = dict(id="1", title="Grant", short_name="Grant", agency_full_name="EPA", status="open",
                backend_section="priority", deadline_date=date(2027, 1, 15), days_left=60, fit_score=85,
                eligibility_positive=True, eligibility_restricted=False, award_status=CONFIRMED, section="top")
    base.update(overrides)
    return OpportunityView(**base)


def record(gid, days_left, fit, codes, close="2026-11-18"):
    return {"id": gid, "title": f"Grant {gid}", "section": "screened_out", "fit_score": fit,
            "deadline": {"status": "open", "close_date": close, "days_left": days_left},
            "screening": {"codes": codes}, "eligibility": {}, "funding": {}, "effort": {}}


class InstantMatchTests(unittest.TestCase):
    def test_threshold_is_inclusive_and_sorted_by_score(self):
        views = [view(id="a", fit_score=80), view(id="b", fit_score=92), view(id="c", fit_score=79)]
        self.assertEqual([v.id for v in ad.instant_matches(views, 80)], ["b", "a"])

    def test_positive_eligibility_filter(self):
        views = [view(id="a", eligibility_positive=False), view(id="b", eligibility_restricted=True), view(id="c")]
        self.assertEqual([v.id for v in ad.instant_matches(views, 80, positive_only=True)], ["c"])
        self.assertEqual(len(ad.instant_matches(views, 80, positive_only=False)), 3)

    def test_excludes_forecasts_closed_unscored_and_likely_ineligible(self):
        views = [view(id="f", status="forecasted"), view(id="x", days_left=-1), view(id="n", fit_score=None),
                 view(id="i", backend_section="likely_ineligible"), view(id="ok")]
        self.assertEqual([v.id for v in ad.instant_matches(views, 50, positive_only=False)], ["ok"])

    def test_zero_matches(self):
        self.assertEqual(ad.instant_matches([view(fit_score=70)], 80), [])


class DigestTests(unittest.TestCase):
    def test_groups_follow_brief_sections(self):
        views = [view(id="t"), view(id="c", section="check"), view(id="l", section="lower"),
                 view(id="s", section="soon", status="forecasted")]
        groups = ad.digest_groups(views, [view(id="z", days_left=5)])
        self.assertEqual([v.id for v in groups["top"]], ["t"])
        self.assertEqual([v.id for v in groups["check"]], ["c"])
        self.assertEqual([v.id for v in groups["closing"]], ["z"])

    def test_subject(self):
        groups = {"top": [view()], "check": [view(), view()], "closing": []}
        self.assertEqual(ad.digest_subject("DHHS", groups),
                         "GrantScope weekly digest for DHHS: 1 top candidate, 2 to check")
        self.assertIn("no new opportunities", ad.digest_subject("DEQ", {"top": [], "check": [], "closing": []}))

    def test_next_weekday(self):
        self.assertEqual(ad.next_weekday("Monday", TODAY), date(2026, 11, 9))
        self.assertEqual(ad.next_weekday("Sunday", TODAY), date(2026, 11, 15))  # never today

    def test_closing_soon_uses_time_screened_records_only(self):
        result = {"screened_out": [record("a", 10, 45, ["not_enough_time"]),
                                   record("b", 4, 70, ["not_enough_time"], close="2026-11-12"),
                                   record("c", 10, 20, ["not_enough_time"]),          # weak fit
                                   record("d", 10, 80, ["not_enough_time", "not_eligible"]),
                                   record("e", 20, 80, ["not_enough_time"], close="2026-11-28")]}
        out = ad.closing_soon_views(result, None, brief_views=[view(id="g", days_left=12)])
        self.assertEqual([v.id for v in out], ["b", "a", "g"])  # soonest first


class ReminderTests(unittest.TestCase):
    def test_schedule_skips_past_and_undated(self):
        saved = [view(id="a", short_name="A", deadline_date=date(2026, 11, 20), days_left=12),
                 view(id="b", short_name="B", deadline_date=None, days_left=None),
                 view(id="c", short_name="C", status="forecasted")]
        rows, skipped = ad.reminder_schedule(saved, (14, 3), TODAY)
        self.assertEqual([(r[0], r[1]) for r in rows], [(date(2026, 11, 17), 3)])  # 14-day date already passed
        self.assertEqual(skipped, 2)

    def test_no_reminder_days_chosen(self):
        rows, _ = ad.reminder_schedule([view()], (), TODAY)
        self.assertEqual(rows, [])


class EmailTests(unittest.TestCase):
    def test_valid_email(self):
        self.assertTrue(ad.valid_email("name@agency.nc.gov"))
        for bad in ("", "name", "name@", "@nc.gov", "a b@nc.gov", "a@b", "a@@b.gov"):
            self.assertFalse(ad.valid_email(bad), bad)


class ProfileShimTests(unittest.TestCase):
    def test_search_still_gets_legacy_keys(self):
        from modules.profile import LEGACY_DEFAULTS
        for key in ("agency", "priorities", "deadline_days", "minimum_award", "minimum_match_score"):
            self.assertIn(key, LEGACY_DEFAULTS)
        self.assertEqual(ad.DEFAULT_SETTINGS["threshold"], 80)
        self.assertEqual(ad.DEFAULT_SETTINGS["digest_day"], "Monday")
        self.assertEqual(ad.THRESHOLD_RANGE, (50, 100))


if __name__ == "__main__":
    unittest.main()
