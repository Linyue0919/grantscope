"""On-demand full-notice effort for the Brief (ui/effort_on_demand.py). No network: fetch is faked.

Run: python -m pytest -q tests/test_effort_on_demand.py
"""
import unittest

from ui import effort_on_demand as eod
from ui.view_model import CONFIRMED, NOT_STATED, OpportunityView

DETAILS = {"description": "Short summary.", "eligibility_text": "", "cost_sharing": None,
           "attachments": [{"name": "Full announcement.pdf", "folder": "Full Announcement",
                            "mime_type": "application/pdf", "url": "https://example.gov/nofo.pdf"}]}
NOFO = ("Applicants must submit a letter of intent by March 1. A project narrative not to exceed 15 pages is "
        "required, with a budget justification, letters of support, a data management plan and an evaluation plan. "
        "Applicants must be registered in SAM.gov and have a Unique Entity Identifier (UEI).") * 3


def view():
    return OpportunityView(id="357524", title="Grant", short_name="Grant", agency_full_name="NIH",
                           cost_share_text="None", cost_share_status=CONFIRMED)


class EffortOnDemandTests(unittest.TestCase):
    def setUp(self):
        eod._cache().clear()
        self.calls = []

    def fetch(self, opp_id):
        self.calls.append(opp_id)
        return NOFO, "https://example.gov/nofo.pdf"

    def test_full_notice_requirements_become_confirmed_rows(self):
        outcome = eod.compute("357524", DETAILS, fetch=self.fetch)
        v = view()
        self.assertTrue(eod.apply(v, outcome))
        self.assertEqual(v.effort_level, "Heavy")
        self.assertEqual(v.effort_status, CONFIRMED)
        rows = {d["label"]: d for d in v.effort_drivers}
        self.assertEqual(rows["Submission process"]["value"], "Letter of intent first")
        self.assertEqual(rows["Project narrative"]["value"], "Up to 15 pages")
        self.assertEqual(rows["Letters of support"]["status"], CONFIRMED)
        self.assertEqual(rows["Registrations"]["status"], CONFIRMED)
        self.assertEqual(self.calls, ["357524"])

    def test_cached_per_opportunity(self):
        eod.compute("357524", DETAILS, fetch=self.fetch)
        eod.compute("357524", DETAILS, fetch=self.fetch)
        self.assertEqual(len(self.calls), 1)
        self.assertIsNotNone(eod.cached("357524"))
        self.assertIsNone(eod.cached("999"))

    def test_no_notice_text_is_cached_and_keeps_listing_value(self):
        outcome = eod.compute("1", DETAILS, fetch=lambda opp_id: ("", None))
        v = view()
        self.assertFalse(eod.apply(v, outcome))
        self.assertEqual(v.effort_status, NOT_STATED)
        self.assertIn("couldn't be found", v.effort_note)
        self.assertIsNotNone(eod.cached("1"))

    def test_download_failure_is_not_cached(self):
        def broken(opp_id):
            raise ConnectionError("timeout")
        outcome = eod.compute("2", DETAILS, fetch=broken)
        self.assertEqual(outcome, {"error": eod.UNREADABLE})
        self.assertIsNone(eod.cached("2"))

    def test_missing_details_changes_nothing(self):
        self.assertIsNone(eod.compute("3", None, fetch=self.fetch))
        self.assertFalse(eod.apply(view(), None))


class FakeClient:
    """Stands in for OfficialEvidenceClient: one Grants.gov HTML stub that meta-refreshes to an http .gov page."""
    def __init__(self):
        self.downloads = []

    def fetch(self, opp_id):
        return {"sources": [{"kind": "official_document", "name": "PAR-1-Full-Announcement.html", "text": "PAR-1",
                             "url": "https://apply07.grants.gov/att/1"}],
                "inventory": [{"name": "PAR-1-Full-Announcement.html", "url": "https://apply07.grants.gov/att/1",
                               "ingested": True}]}

    def _download(self, url):
        self.downloads.append(url)
        if url.endswith("/att/1"):
            return (b'<meta http-equiv="refresh" content="0; URL=\'http://grants.nih.gov/guide/PAR-1.html\'" />',
                    "text/html", url)
        return (f"<html><body><p>{NOFO}</p></body></html>".encode(), "text/html", url)


class StubFollowTests(unittest.TestCase):
    def test_meta_refresh_stub_is_followed_over_https(self):
        client = FakeClient()
        text, url = eod.official_notice_text("1", client=client)
        self.assertIn("letter of intent", text)
        self.assertEqual(client.downloads[-1], "https://grants.nih.gov/guide/PAR-1.html")
        self.assertEqual(url, "https://grants.nih.gov/guide/PAR-1.html")


if __name__ == "__main__":
    unittest.main()
