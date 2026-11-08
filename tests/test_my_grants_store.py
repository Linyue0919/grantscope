"""Brief → My Grants (ui/my_grants_store.py) against Search's real store and save function.

Run: python -m pytest -q tests/test_my_grants_store.py
"""
import os
import tempfile
import unittest
from datetime import date
from unittest import mock

from streamlit.testing.v1 import AppTest

from services.calendar_export import grants_to_ics
from services.grant_store import LocalGrantStore
from ui import my_grants_store as mg
from ui.view_model import OpportunityView

AGENCY = "Department of Health and Human Services"
TODAY = date(2026, 11, 8)


def view(**overrides):
    base = dict(id="361234", title="Youth Mental Health Access (R01)", short_name="Youth Mental Health Access",
                agency_full_name="National Institutes of Health", deadline_date=date(2027, 1, 7), days_left=60,
                grants_gov_url="https://www.grants.gov/search-results-detail/361234",
                reason_sentence="Directly matches Goal 2: Whole Person Well-Being.")
    base.update(overrides)
    return OpportunityView(**base)


class MyGrantsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"GRANTSCOPE_DATA_DIR": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_save_writes_search_compatible_record(self):
        mg.save(AGENCY, view())
        record = LocalGrantStore().get(AGENCY, "361234")
        self.assertEqual(record["title"], "Youth Mental Health Access (R01)")
        self.assertEqual(record["official_url"], "https://www.grants.gov/search-results-detail/361234")
        self.assertEqual(record["federal_agency"], "National Institutes of Health")
        self.assertEqual(record["close_date"], "2027-01-07")
        self.assertEqual(record["notes"], "Saved from Funding Brief: Directly matches Goal 2: Whole Person Well-Being.")
        self.assertEqual(record["project_description"], "")
        self.assertTrue(record["bookmarked"])
        self.assertEqual(mg.saved_ids(AGENCY), {"361234"})
        self.assertEqual(mg.saved_ids("Department of Transportation"), set())

    def test_resave_keeps_user_notes_and_decision(self):
        mg.save(AGENCY, view())
        LocalGrantStore().save(AGENCY, "361234", {"decision": "Pursue", "notes": "Call the PO."})
        mg.save(AGENCY, view())
        record = LocalGrantStore().get(AGENCY, "361234")
        self.assertEqual(record["decision"], "Pursue")
        self.assertIn("Call the PO.", record["notes"])
        self.assertIn("Saved from Funding Brief", record["notes"])
        self.assertEqual(len(LocalGrantStore().list_records()), 1)

    def test_missing_deadline_is_not_written_as_blank(self):
        mg.save(AGENCY, view(id="9", deadline_date=None, days_left=None))
        self.assertNotIn("close_date", LocalGrantStore().get(AGENCY, "9"))

    def test_reminder_views_prefer_fresh_brief_data(self):
        mg.save(AGENCY, view())
        LocalGrantStore().save(AGENCY, "777", {"title": "From Search", "close_date": "11/20/2026"})
        fresh = view(deadline_date=date(2027, 2, 1), days_left=85)
        out = {v.id: v for v in mg.reminder_views(AGENCY, [fresh], TODAY)}
        self.assertEqual(out["361234"].deadline_date, date(2027, 2, 1))  # fresh brief value
        self.assertEqual(out["777"].deadline_date, date(2026, 11, 20))  # parsed from the record
        self.assertEqual(out["777"].days_left, 12)

    def test_brief_save_shows_on_my_grants_page_and_calendar(self):
        mg.save(AGENCY, view())
        app = AppTest.from_string("from modules.my_grants import show_my_grants\nshow_my_grants()").run()
        self.assertFalse(app.exception)
        self.assertIn("Youth Mental Health Access (R01)", [s.value for s in app.subheader])
        self.assertIn("DTSTART;VALUE=DATE:20270107", grants_to_ics(LocalGrantStore().list_records()))


if __name__ == "__main__":
    unittest.main()
