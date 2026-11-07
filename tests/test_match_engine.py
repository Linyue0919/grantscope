"""Offline tests for the shared matching engine and agency plan data.

Run: python -m unittest discover -s tests -v
"""
import unittest
from datetime import date
from urllib.parse import urlparse

from services.agency_profiles import (
    get_agency_profile, list_profiled_agencies, load_plan_data, resolve_agency_name,
)
from services.match_engine import (
    CLOSED, ELIGIBLE_TYPE, FORECASTED, NEEDS_REVIEW, NOT_CHECKED, NOT_ELIGIBLE, OPEN, UNKNOWN,
    WEIGHTS, MatchSettings, build_queries, classify_deadline, evaluate_grant, find_terms,
    run_matching, score_alignment, screen_eligibility,
)
from services.opportunity_details import OpportunityDetailsError, parse_details

TODAY = date(2026, 11, 7)
DEQ = get_agency_profile("Department of Environmental Quality")


def hit(gid, title, close="12/31/2026", status="posted"):
    return {"id": gid, "number": f"N-{gid}", "title": title, "agency": "EPA",
            "closeDate": close, "oppStatus": status}


def details(types=(("00", "State governments"),), text="", ceiling=500000.0, desc=""):
    return {"applicant_types": [{"id": i, "description": d} for i, d in types],
            "eligibility_text": text, "award_ceiling": ceiling, "award_floor": None,
            "estimated_funding": None, "description": desc, "close_date_text": None}


class PlanDataTests(unittest.TestCase):
    def test_every_goal_is_sourced(self):
        data = load_plan_data()
        self.assertGreaterEqual(len(data["agencies"]), 5)
        for agency in data["agencies"]:
            self.assertEqual(urlparse(agency["plan_url"]).netloc, "www.osbm.nc.gov")
            self.assertTrue(agency["goals"], agency["name"])
            for goal in agency["goals"]:
                self.assertTrue(goal["quote"].strip())
                self.assertIsInstance(goal["page"], int)
                self.assertTrue(goal["terms"], goal["goal_id"])

    def test_unprofiled_agencies_have_no_goals(self):
        for entry in load_plan_data()["unprofiled_agencies"]:
            self.assertNotIn("goals", entry)
            self.assertIsNone(get_agency_profile(entry["name"]))

    def test_resolves_profile_labels(self):
        self.assertEqual(resolve_agency_name("NC Department of Environmental Quality"),
                         "Department of Environmental Quality")
        self.assertEqual(resolve_agency_name("ncdot"), "Department of Transportation")
        self.assertIsNone(resolve_agency_name("Department of Revenue"))
        self.assertIn("Department of Transportation", list_profiled_agencies())


class TermMatchingTests(unittest.TestCase):
    def test_whole_words_and_plurals(self):
        self.assertEqual(find_terms("Drinking Water System Grants", ["drinking water"]), ["drinking water"])
        self.assertEqual(find_terms("Improving roadways", ["roadway"]), ["roadway"])
        self.assertEqual(find_terms("Spare parts program", ["arts"]), [])

    def test_species_recovery_is_not_disaster_recovery_for_deq(self):
        result = score_alignment(
            "Cooperative Endangered Species Conservation Fund: Recovery Land Acquisition", "", DEQ)
        self.assertEqual(result["points"], 0)

    def test_title_counts_more_than_description(self):
        in_title = score_alignment("Drinking Water Infrastructure", "", DEQ)["points"]
        in_desc = score_alignment("Program", "Supports drinking water systems.", DEQ)["points"]
        self.assertGreater(in_title, in_desc)
        self.assertGreater(in_desc, 0)

    def test_alignment_is_capped(self):
        text = "water quality drinking water wastewater stormwater air quality pfas forever chemicals"
        self.assertEqual(score_alignment(text, "", DEQ)["points"], WEIGHTS["strategic_alignment"])


class DeadlineTests(unittest.TestCase):
    def classify(self, close, status="posted", horizon=90):
        return classify_deadline(hit("1", "x", close, status), None, TODAY, horizon)

    def test_statuses(self):
        self.assertEqual(self.classify("12/01/2026")["status"], OPEN)
        self.assertEqual(self.classify("11/01/2026")["status"], CLOSED)
        self.assertEqual(self.classify("", "posted")["status"], UNKNOWN)
        self.assertEqual(self.classify("01/15/2027", "forecasted")["status"], FORECASTED)
        self.assertEqual(self.classify("12/01/2026", "archived")["status"], CLOSED)

    def test_closing_today_is_open(self):
        self.assertEqual(self.classify("11/07/2026")["days_left"], 0)
        self.assertEqual(self.classify("11/07/2026")["status"], OPEN)

    def test_horizon(self):
        self.assertFalse(self.classify("06/01/2027", horizon=90)["within_horizon"])

    def test_detail_response_date_fallback(self):
        d = details()
        d["close_date_text"] = "Dec 14, 2026 12:00:00 AM EST"
        out = classify_deadline(hit("1", "x", ""), d, TODAY, 90)
        self.assertEqual(out["close_date"], "2026-12-14")


class EligibilityTests(unittest.TestCase):
    def test_not_loaded_is_never_eligible(self):
        self.assertEqual(screen_eligibility(None, DEQ)["status"], NOT_CHECKED)

    def test_state_governments_listed(self):
        self.assertEqual(screen_eligibility(details(), DEQ)["status"], ELIGIBLE_TYPE)

    def test_restriction_text_downgrades(self):
        d = details(text="Only Water Resources Research Institutes established under the Act are eligible to apply.")
        out = screen_eligibility(d, DEQ)
        self.assertEqual(out["status"], NEEDS_REVIEW)
        self.assertIn("Water Resources Research Institutes", out["evidence"])

    def test_others_needs_review(self):
        d = details(types=(("25", "Others (see text field)"),))
        self.assertEqual(screen_eligibility(d, DEQ)["status"], NEEDS_REVIEW)

    def test_excluded_types(self):
        d = details(types=(("12", "Nonprofits having a 501(c)(3) status"),))
        self.assertEqual(screen_eligibility(d, DEQ)["status"], NOT_ELIGIBLE)

    def test_unrestricted(self):
        d = details(types=(("99", "Unrestricted"),))
        self.assertEqual(screen_eligibility(d, DEQ)["status"], ELIGIBLE_TYPE)


class EvaluateTests(unittest.TestCase):
    settings = MatchSettings(horizon_days=90, min_award=100000)

    def test_screening_excludes_instead_of_scoring(self):
        closed = evaluate_grant(hit("1", "Drinking Water Grants", "10/01/2026"), DEQ, details(), self.settings, TODAY)
        self.assertFalse(closed["screening"]["passed"])
        self.assertIn("closed", closed["screening"]["codes"])
        self.assertIsNone(closed["match_score"])

        inelig = evaluate_grant(hit("2", "Drinking Water Grants"),
                                DEQ, details(types=(("21", "Individuals"),)), self.settings, TODAY)
        self.assertIn("not_eligible", inelig["screening"]["codes"])
        self.assertIsNone(inelig["match_score"])

    def test_score_is_sum_of_components(self):
        out = evaluate_grant(hit("3", "Drinking Water and Wastewater Grants"), DEQ, details(), self.settings, TODAY)
        self.assertTrue(out["screening"]["passed"])
        parts = out["score_breakdown"]
        self.assertEqual(out["match_score"], sum(p["points"] for p in parts.values()))
        self.assertLessEqual(out["match_score"], 100)
        self.assertIn("Goal 1", out["explanation"])

    def test_missing_details_are_flagged(self):
        out = evaluate_grant(hit("4", "Drinking Water Grants"), DEQ, None, self.settings, TODAY)
        self.assertEqual(out["eligibility"]["status"], NOT_CHECKED)
        self.assertTrue(any("not loaded" in gap for gap in out["data_gaps"]))

    def test_below_minimum_award(self):
        low = evaluate_grant(hit("5", "Drinking Water Grants"), DEQ, details(ceiling=20000.0), self.settings, TODAY)
        high = evaluate_grant(hit("6", "Drinking Water Grants"), DEQ, details(), self.settings, TODAY)
        self.assertLess(low["score_breakdown"]["funding"]["points"], high["score_breakdown"]["funding"]["points"])

    def test_other_region_is_flagged_not_excluded(self):
        out = evaluate_grant(hit("7", "Great Lakes Drinking Water Grants"), DEQ, details(), self.settings, TODAY)
        self.assertTrue(out["screening"]["passed"])
        self.assertTrue(any("great lakes" in gap for gap in out["data_gaps"]))


class RunMatchingTests(unittest.TestCase):
    def test_end_to_end_with_failures(self):
        hits = {
            "drinking water": [hit("10", "Drinking Water State Revolving Fund"),
                               hit("11", "Wastewater Treatment Grants", "11/20/2026"),
                               hit("12", "Old Drinking Water Program", "01/01/2026")],
        }

        def search_fn(keyword, rows):
            if keyword == "wastewater":
                raise RuntimeError("Grants.gov timeout")
            return hits.get(keyword, [hit("10", "Drinking Water State Revolving Fund")])

        def details_fn(gid):
            if gid == "11":
                raise OpportunityDetailsError("details unavailable")
            return details()

        out = run_matching(DEQ, MatchSettings(min_award=0), search_fn=search_fn, details_fn=details_fn,
                           today=TODAY, extra_keywords=("drinking water", "wastewater"))
        ids = [r["id"] for r in out["results"]]
        self.assertIn("10", ids)
        self.assertIn("11", ids)
        self.assertNotIn("12", ids)  # closed
        self.assertTrue(any("wastewater" in e for e in out["errors"]))
        self.assertTrue(any("11" in e for e in out["errors"]))
        rec11 = next(r for r in out["results"] if r["id"] == "11")
        self.assertEqual(rec11["eligibility"]["status"], NOT_CHECKED)
        scores = [r["match_score"] for r in out["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(out["stats"]["possibly_incomplete"])

    def test_queries_cover_each_goal(self):
        queries = build_queries(DEQ, (), max_queries=len(DEQ["goals"]))
        self.assertEqual({q["source"] for q in queries}, {g["goal_id"] for g in DEQ["goals"]})

    def test_no_profile_is_unscored(self):
        out = run_matching(None, MatchSettings(), search_fn=lambda k, r: [], details_fn=lambda g: {},
                           today=TODAY, extra_keywords=("water",))
        self.assertEqual(out["results"], [])


class DetailParsingTests(unittest.TestCase):
    def test_parse_synopsis(self):
        payload = {"errorcode": 0, "data": {"synopsis": {
            "awardCeiling": "450,000", "awardFloor": "1", "estimatedFunding": None,
            "applicantTypes": [{"id": "00", "description": "State governments"}],
            "applicantEligibilityDesc": "<p>State agencies &amp; tribes</p>",
            "synopsisDesc": "<b>Clean</b> water", "responseDateStr": "2026-12-14-00-00-00",
            "costSharing": "False"}}}
        out = parse_details(payload, 123)
        self.assertEqual(out["award_ceiling"], 450000.0)
        self.assertEqual(out["eligibility_text"], "State agencies & tribes")
        self.assertEqual(out["description"], "Clean water")
        self.assertFalse(out["cost_sharing"])
        self.assertIsNone(out["estimated_funding"])

    def test_error_payload(self):
        with self.assertRaises(OpportunityDetailsError):
            parse_details({"errorcode": 1, "msg": "bad"}, 1)


if __name__ == "__main__":
    unittest.main()
