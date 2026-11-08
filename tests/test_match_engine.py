"""Offline tests for the shared matching engine, plan data, effort and AI layers.

Run: python -m unittest discover -s tests -v
"""
import json
import unittest
from datetime import date
from types import SimpleNamespace
from urllib.parse import urlparse

from services.agency_profiles import (
    get_agency_profile, list_profiled_agencies, load_plan_data, resolve_agency_name,
)
from services.ai_matching import AzureFitEvaluator, load_ai_config, validate_response, build_sources
from services.application_effort import assess_effort, find_announcement
from services.match_engine import (
    CLOSED, ELIGIBLE_TYPE, FORECASTED, LOW_EVIDENCE, NEEDS_REVIEW, NOT_CHECKED, NOT_ELIGIBLE, OPEN,
    PRIORITY, SCREENED_OUT, UNKNOWN, UPCOMING, MatchSettings, build_queries, classify_deadline,
    evaluate_grant, find_terms, keyword_relevance, run_matching, screen_eligibility,
)
from services.opportunity_details import OpportunityDetailsError, parse_details

TODAY = date(2026, 11, 7)
DEQ = get_agency_profile("Department of Environmental Quality")
SETTINGS = MatchSettings(min_days_left=30)


def hit(gid, title, close="12/31/2026", status="posted"):
    return {"id": gid, "number": f"N-{gid}", "title": title, "agency": "EPA",
            "closeDate": close, "oppStatus": status}


def details(types=(("00", "State governments"),), text="", ceiling=500000.0, desc="", cost_sharing=False,
            attachments=()):
    return {"applicant_types": [{"id": i, "description": d} for i, d in types],
            "eligibility_text": text, "award_ceiling": ceiling, "award_floor": None,
            "estimated_funding": None, "number_of_awards": None, "description": desc,
            "close_date_text": None, "cost_sharing": cost_sharing, "attachments": list(attachments)}


class PlanDataTests(unittest.TestCase):
    def test_every_goal_is_sourced(self):
        data = load_plan_data()
        self.assertGreaterEqual(len(data["agencies"]), 5)
        for agency in data["agencies"]:
            self.assertEqual(urlparse(agency["plan_url"]).netloc, "www.osbm.nc.gov")
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


class RelevanceTests(unittest.TestCase):
    def test_whole_words_and_plurals(self):
        self.assertEqual(find_terms("Drinking Water System Grants", ["drinking water"]), ["drinking water"])
        self.assertEqual(find_terms("Improving roadways", ["roadway"]), ["roadway"])
        self.assertEqual(find_terms("Spare parts program", ["arts"]), [])

    def test_species_recovery_is_not_disaster_recovery_for_deq(self):
        out = keyword_relevance("Cooperative Endangered Species Conservation Fund: Recovery Land Acquisition", "", DEQ)
        self.assertEqual(out["score"], 0)

    def test_title_counts_more_than_description(self):
        in_title = keyword_relevance("Drinking Water Infrastructure", "", DEQ)["score"]
        in_desc = keyword_relevance("Program", "Supports drinking water systems.", DEQ)["score"]
        self.assertGreater(in_title, in_desc)
        self.assertGreater(in_desc, 0)

    def test_description_only_evidence_is_capped(self):
        # Live case: a machine-learning NOFO whose long description mentions many DEQ topics scored 100.
        desc = "air quality coastal marine water quality drinking water wastewater pollution pfas"
        out = keyword_relevance("Super Intelligence and Machine Learning Research", desc, DEQ)
        self.assertEqual(out["score"], 40)

    def test_capped_at_100(self):
        text = "water quality drinking water wastewater stormwater air quality pfas forever chemicals"
        self.assertEqual(keyword_relevance(text, "", DEQ)["score"], 100)

    def test_score_ignores_deadline_and_funding(self):
        a = evaluate_grant(hit("1", "Drinking Water Grants", "12/31/2026"), DEQ, details(ceiling=5e6), SETTINGS, TODAY)
        b = evaluate_grant(hit("2", "Drinking Water Grants", "06/30/2027"), DEQ, details(ceiling=None), SETTINGS, TODAY)
        self.assertEqual(a["fit_score"], b["fit_score"])

    def test_zero_overlap_is_low_or_unassessed_not_excluded(self):
        with_desc = evaluate_grant(hit("3", "Community Program"), DEQ, details(desc="Supports libraries."),
                                   SETTINGS, TODAY)
        no_desc = evaluate_grant(hit("4", "Community Program"), DEQ, None, SETTINGS, TODAY)
        self.assertEqual(with_desc["section"], LOW_EVIDENCE)
        self.assertEqual(with_desc["relevance"]["level"], "low")
        self.assertEqual(no_desc["section"], LOW_EVIDENCE)
        self.assertEqual(no_desc["relevance"]["level"], "unassessed")
        self.assertTrue(with_desc["screening"]["passed"])


class DeadlineTests(unittest.TestCase):
    def classify(self, close, status="posted"):
        return classify_deadline(hit("1", "x", close, status), None, TODAY)

    def test_statuses(self):
        self.assertEqual(self.classify("12/01/2026")["status"], OPEN)
        self.assertEqual(self.classify("11/01/2026")["status"], CLOSED)
        self.assertEqual(self.classify("", "posted")["status"], UNKNOWN)
        self.assertEqual(self.classify("01/15/2027", "forecasted")["status"], FORECASTED)
        self.assertEqual(self.classify("12/01/2026", "archived")["status"], CLOSED)

    def test_min_days_left_filter(self):
        soon = evaluate_grant(hit("1", "Drinking Water Grants", "11/20/2026"), DEQ, details(), SETTINGS, TODAY)
        self.assertEqual(soon["section"], SCREENED_OUT)
        self.assertIn("not_enough_time", soon["screening"]["codes"])
        any_open = evaluate_grant(hit("1", "Drinking Water Grants", "11/20/2026"), DEQ, details(),
                                  MatchSettings(min_days_left=None), TODAY)
        self.assertEqual(any_open["section"], PRIORITY)
        self.assertEqual(any_open["urgency"]["level"], "urgent")

    def test_forecasted_goes_to_upcoming(self):
        out = evaluate_grant(hit("1", "Drinking Water Grants", "11/12/2026", "forecasted"), DEQ, details(),
                             SETTINGS, TODAY)
        self.assertEqual(out["section"], UPCOMING)

    def test_closed_is_screened(self):
        out = evaluate_grant(hit("1", "Drinking Water Grants", "10/01/2026"), DEQ, details(), SETTINGS, TODAY)
        self.assertIn("closed", out["screening"]["codes"])

    def test_detail_response_date_fallback(self):
        d = details()
        d["close_date_text"] = "Dec 14, 2026 12:00:00 AM EST"
        self.assertEqual(classify_deadline(hit("1", "x", ""), d, TODAY)["close_date"], "2026-12-14")


class EligibilityTests(unittest.TestCase):
    def test_not_loaded_is_never_eligible(self):
        self.assertEqual(screen_eligibility(None, DEQ)["status"], NOT_CHECKED)

    def test_type_match_is_not_confirmation(self):
        out = screen_eligibility(details(), DEQ)
        self.assertEqual(out["status"], ELIGIBLE_TYPE)
        self.assertIn("not a guarantee", out["summary"])
        self.assertTrue(out["to_verify"])

    def test_restriction_text_downgrades(self):
        out = screen_eligibility(details(text="Only Water Resources Research Institutes established under "
                                              "the Act are eligible to apply."), DEQ)
        self.assertEqual(out["status"], NEEDS_REVIEW)
        self.assertIn("Water Resources Research Institutes", out["evidence"])
        self.assertTrue(out["to_verify"])

    def test_others_needs_review(self):
        self.assertEqual(screen_eligibility(details(types=(("25", "Others (see text field)"),)), DEQ)["status"],
                         NEEDS_REVIEW)

    def test_excluded_types_explained_and_screened(self):
        d = details(types=(("12", "Nonprofits having a 501(c)(3) status"),))
        out = screen_eligibility(d, DEQ)
        self.assertEqual(out["status"], NOT_ELIGIBLE)
        self.assertIn("Nonprofits", out["summary"])
        rec = evaluate_grant(hit("1", "Drinking Water Grants"), DEQ, d, SETTINGS, TODAY)
        self.assertEqual(rec["section"], SCREENED_OUT)

    def test_other_region_adds_verification_item(self):
        out = screen_eligibility(details(), DEQ, title="Great Lakes Restoration")
        self.assertTrue(any("great lakes" in v for v in out["to_verify"]))


class FundingTests(unittest.TestCase):
    def test_ceiling_is_described_as_maximum(self):
        rec = evaluate_grant(hit("1", "Drinking Water Grants"), DEQ, details(ceiling=450000.0), SETTINGS, TODAY)
        self.assertEqual(rec["funding"]["display"], "Up to $450,000 per award")
        self.assertIn("not guaranteed", rec["funding"]["note"])

    def test_min_award_filter_keeps_unreported(self):
        s = MatchSettings(min_days_left=30, min_award=100000)
        low = evaluate_grant(hit("1", "Drinking Water Grants"), DEQ, details(ceiling=20000.0), s, TODAY)
        unknown = evaluate_grant(hit("2", "Drinking Water Grants"), DEQ, details(ceiling=None), s, TODAY)
        self.assertIn("below_min_award", low["screening"]["codes"])
        self.assertEqual(unknown["section"], PRIORITY)
        self.assertTrue(any("minimum-award" in g for g in unknown["data_gaps"]))


class EffortTests(unittest.TestCase):
    def test_requirements_need_evidence(self):
        d = details(desc="Applicants must provide a budget narrative and letters of support. "
                         "A 1:1 non-federal match is required. " + "x" * 1600, cost_sharing=True)
        out = assess_effort(d)
        keys = {r["key"] for r in out["requirements"]}
        self.assertTrue({"budget", "letters", "cost_sharing"} <= keys)
        self.assertTrue(all(r["evidence"] for r in out["requirements"]))
        self.assertIn(out["level"], {"moderate", "higher"})

    def test_short_text_is_insufficient_not_easy(self):
        out = assess_effort(details(desc="Short synopsis."))
        self.assertEqual(out["level"], "insufficient")
        self.assertEqual(out["requirements"], [])

    def test_not_loaded(self):
        self.assertEqual(assess_effort(None)["level"], "unknown")

    def test_negated_cost_sharing_is_not_a_requirement(self):
        # Wording observed in a live NOFO; the Grants.gov field also said "No".
        text = ("B. Cost Share or Matching Requirement The competition listed in this NOFO does not have any "
                "cost sharing or matching criteria. Letters of intent are optional.")
        out = assess_effort(details(cost_sharing=False), text, "u")
        keys = {r["key"] for r in out["requirements"]}
        self.assertNotIn("cost_sharing", keys)
        self.assertNotIn("pre_application", keys)
        self.assertTrue(out["not_required"])
        no_field = assess_effort(dict(details(), cost_sharing=None), text, "u")
        self.assertNotIn("cost_sharing", {r["key"] for r in no_field["requirements"]})

    def test_summary_without_requirements_is_unclear_not_easy(self):
        out = assess_effort(details(desc="General research program description. " * 60))
        self.assertEqual(out["level"], "unclear")

    def test_attachment_names_and_announcement(self):
        atts = [{"id": "1", "name": "Full Announcement.pdf", "folder": "Full Announcement",
                 "mime_type": "application/pdf", "url": "u1"},
                {"id": "2", "name": "Biographical-sketch-form.pdf", "folder": "Other Supporting Documents",
                 "mime_type": "application/pdf", "url": "u2"}]
        d = details(attachments=atts)
        self.assertEqual(find_announcement(d)["url"], "u1")
        out = assess_effort(d, "Proposals must not exceed 15 pages. Include a data management plan.", "u1")
        keys = {r["key"] for r in out["requirements"]}
        self.assertIn("personnel", keys)
        self.assertIn("data_plan", keys)
        self.assertEqual(out["page_limit"]["pages"], 15)
        self.assertTrue(out["announcement_analyzed"])


class FakeClient:
    def __init__(self, content=None, exc=None):
        self.calls, self.content, self.exc = [], content, exc
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


CONFIG = {"endpoint": "https://x", "api_key": "k", "deployment": "grantscope-gpt4o", "api_version": "v"}


class AITests(unittest.TestCase):
    def setUp(self):
        self.record = evaluate_grant(hit("9", "Rural Utility Upgrades"), DEQ,
                                     details(desc="Funds wastewater treatment upgrades for small towns."),
                                     SETTINGS, TODAY)
        self.details = details(desc="Funds wastewater treatment upgrades for small towns.")

    def good(self):
        return json.dumps({"relevance": 80, "goal_ids": ["deq-1"],
                           "evidence": [{"source_id": "D", "quote": "wastewater treatment upgrades for small towns"},
                                        {"source_id": "deq-1", "quote": "prevent pollution, and improve public health"}],
                           "explanation": "Upgrades wastewater treatment, matching DEQ public health goals."})

    def test_config_requires_endpoint_and_key(self):
        self.assertIsNone(load_ai_config({}))
        cfg = load_ai_config({"AZURE_OPENAI_ENDPOINT": "e", "AZURE_OPENAI_API_KEY": "k"})
        self.assertEqual(cfg["deployment"], "grantscope-gpt4o")

    def test_valid_response_accepted(self):
        out = AzureFitEvaluator(CONFIG, client=FakeClient(self.good()))(self.record, DEQ, self.details)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["score"], 80)

    def test_fabricated_quote_rejected(self):
        bad = json.loads(self.good())
        bad["evidence"][0]["quote"] = "grants for state highway bridges and tunnels"
        out = AzureFitEvaluator(CONFIG, client=FakeClient(json.dumps(bad)))(self.record, DEQ, self.details)
        self.assertEqual(out["status"], "rejected")

    def test_unknown_goal_rejected(self):
        sources = build_sources(self.record, DEQ, self.details)
        bad = json.loads(self.good())
        bad["goal_ids"] = ["deq-99"]
        result, errors = validate_response(json.dumps(bad), sources)
        self.assertIsNone(result)
        self.assertTrue(errors)

    def test_service_error_falls_back(self):
        out = AzureFitEvaluator(CONFIG, client=FakeClient(exc=TimeoutError("slow")))(self.record, DEQ, self.details)
        self.assertEqual(out["status"], "error")
        self.assertNotIn("k", " ".join(out["errors"]))  # no secrets in errors

    def test_cache_hit(self):
        client = FakeClient(self.good())
        evaluator = AzureFitEvaluator(CONFIG, client=client)
        evaluator(self.record, DEQ, self.details)
        evaluator(self.record, DEQ, self.details)
        self.assertEqual(len(client.calls), 1)

    def test_blend_and_rescue_in_engine(self):
        client = FakeClient(self.good())
        evaluator = AzureFitEvaluator(CONFIG, client=client)

        out = run_matching(DEQ, SETTINGS, search_fn=lambda k, r: [hit("9", "Rural Utility Upgrades")],
                           details_fn=lambda g: self.details, today=TODAY, ai_evaluator=evaluator)
        rec = out["results"][0]  # zero keyword-in-title, rescued by verified AI evidence
        self.assertEqual(rec["relevance"]["ai"]["status"], "ok")
        self.assertEqual(rec["fit_score"], round(0.5 * rec["relevance"]["keyword"]["score"] + 0.5 * 80))
        self.assertEqual(out["ai"]["accepted"], 1)

    def test_ai_never_overrides_screening(self):
        client = FakeClient(self.good())
        evaluator = AzureFitEvaluator(CONFIG, client=client)
        out = run_matching(DEQ, SETTINGS, search_fn=lambda k, r: [hit("9", "Rural Utility Upgrades", "10/01/2026")],
                           details_fn=lambda g: self.details, today=TODAY, ai_evaluator=evaluator)
        self.assertEqual(out["results"], [])
        self.assertEqual(client.calls, [])  # closed grants are never sent to the model


class RunMatchingTests(unittest.TestCase):
    def test_end_to_end_with_failures(self):
        def search_fn(keyword, rows):
            if keyword == "wastewater":
                raise RuntimeError("Grants.gov timeout")
            return [hit("10", "Drinking Water State Revolving Fund"),
                    hit("11", "Wastewater Treatment Grants", "01/20/2027"),
                    hit("12", "Old Drinking Water Program", "01/01/2026"),
                    hit("13", "Drinking Water Forecast", "03/01/2027", "forecasted")]

        def details_fn(gid):
            if gid == "11":
                raise OpportunityDetailsError("details unavailable")
            return details()

        out = run_matching(DEQ, SETTINGS, search_fn=search_fn, details_fn=details_fn, today=TODAY,
                           extra_keywords=("drinking water", "wastewater"))
        ids = [r["id"] for r in out["results"]]
        self.assertEqual(set(ids), {"10", "11"})
        self.assertEqual([r["id"] for r in out["upcoming"]], ["13"])
        self.assertTrue(any("wastewater" in e for e in out["errors"]))
        rec11 = next(r for r in out["results"] if r["id"] == "11")
        self.assertEqual(rec11["eligibility"]["status"], NOT_CHECKED)
        self.assertEqual(out["ai"]["status"], "disabled")
        self.assertTrue(out["stats"]["possibly_incomplete"])

    def test_results_are_independent_of_cache_and_filters_nest(self):
        hits = [hit(str(i), "Drinking Water Grants" if i < 3 else f"Program {i}", f"0{1 + i % 6}/15/2027")
                for i in range(10)]
        search = lambda k, r: hits
        fetch = lambda gid: details(desc="Supports wastewater systems.")
        small = MatchSettings(min_days_left=30, detail_limit=3)
        cold = run_matching(DEQ, small, search_fn=search, details_fn=fetch, today=TODAY)
        warm_cache = {str(i): details(desc="Supports wastewater systems.") for i in range(10)}
        warm = run_matching(DEQ, small, search_fn=search, details_fn=fetch, today=TODAY, details_cache=warm_cache)
        self.assertEqual([r["id"] for r in cold["results"]], [r["id"] for r in warm["results"]])
        strict = run_matching(DEQ, MatchSettings(min_days_left=120, detail_limit=3), search_fn=search,
                              details_fn=fetch, today=TODAY, details_cache=warm_cache)
        self.assertTrue({r["id"] for r in strict["results"]} <= {r["id"] for r in cold["results"]})

    def test_queries_cover_each_goal(self):
        queries = build_queries(DEQ, (), max_queries=len(DEQ["goals"]))
        self.assertEqual({q["source"] for q in queries}, {g["goal_id"] for g in DEQ["goals"]})


class DetailParsingTests(unittest.TestCase):
    def test_parse_synopsis(self):
        payload = {"errorcode": 0, "data": {
            "synopsis": {"awardCeiling": "450,000", "awardFloor": "1", "estimatedFunding": None,
                         "applicantTypes": [{"id": "00", "description": "State governments"}],
                         "applicantEligibilityDesc": "<p>State agencies &amp; tribes</p>",
                         "synopsisDesc": "<b>Clean</b> water", "costSharing": "False",
                         "fundingInstruments": [{"id": "G", "description": "Grant"}]},
            "synopsisAttachmentFolders": [{"folderType": "Full Announcement", "synopsisAttachments": [
                {"id": 5, "fileName": "NOFO.pdf", "mimeType": "application/pdf"}]}]}}
        out = parse_details(payload, 123)
        self.assertEqual(out["award_ceiling"], 450000.0)
        self.assertEqual(out["eligibility_text"], "State agencies & tribes")
        self.assertEqual(out["description"], "Clean water")
        self.assertFalse(out["cost_sharing"])
        self.assertEqual(out["funding_instruments"], ["Grant"])
        self.assertTrue(out["attachments"][0]["url"].endswith("/5"))

    def test_error_payload(self):
        with self.assertRaises(OpportunityDetailsError):
            parse_details({"errorcode": 1, "msg": "bad"}, 1)


NOAA_NOTES = (  # verbatim from Grants.gov opportunity 364160 (NOAA-OAR-CPO-2027-33392), retrieved 2026-11-07
    "Eligible applicants are: Institutions of higher education; Other nonprofits; Commercial organizations; "
    "Local and federally recognized Tribal governments; Federal agencies that possess the statutory authority to "
    "receive transfers of funds. The funding instrument for a selected application from a non-NOAA Federal "
    "applicant will be through an inter-agency transfer of funds, provided: 1. Legal authority exists for the "
    "Federal applicant to receive funds from another agency. Foreign or international institutions are not "
    "eligible to apply.")
OTHERS = (("25", 'Others (see text field entitled "Additional Information on Eligibility" for clarification)'),)


class EligibilityIntelligenceTests(unittest.TestCase):
    def assess(self, types, notes, ai=None):
        return screen_eligibility(details(types=types, text=notes), DEQ, "", "https://www.grants.gov/x", ai)

    def test_noaa_others_with_notes_listing_other_applicants(self):
        out = self.assess(OTHERS, NOAA_NOTES)
        self.assertEqual(out["status"], "likely_ineligible")
        self.assertEqual(out["certainty"], "interpretation")
        self.assertTrue(out["quote"].startswith("Eligible applicants are: Institutions of higher education"))
        self.assertIn(out["quote"].rstrip(" …"), NOAA_NOTES)  # exact official text
        self.assertEqual(out["source_url"], "https://www.grants.gov/x")
        self.assertTrue(out["to_verify"])
        self.assertNotIn("state governments", out["listed_categories"])

    def test_noaa_is_not_a_priority_recommendation(self):
        out = run_matching(DEQ, SETTINGS,
                           search_fn=lambda k, r: [hit("364160", "Climate Program Office: Hazard Resilience and "
                                                                "Coastal Water Quality Research")],
                           details_fn=lambda g: details(types=OTHERS, text=NOAA_NOTES), today=TODAY)
        self.assertEqual(out["results"], [])
        self.assertEqual([r["id"] for r in out["likely_ineligible"]], ["364160"])

    def test_nonprofit_only_structured_field_is_confirmed(self):
        out = self.assess((("12", "Nonprofits having a 501(c)(3) status with the IRS"),), "")
        self.assertEqual(out["status"], "ineligible")
        self.assertEqual(out["certainty"], "confirmed")
        self.assertIn("Nonprofits", out["quote"])

    def test_nonprofit_only_notes(self):
        out = self.assess(OTHERS, "Eligibility is limited to nonprofit organizations with 501(c)(3) status.")
        self.assertEqual(out["status"], "likely_ineligible")
        self.assertEqual(out["listed_categories"], ["nonprofits"])

    def test_state_government_structured_field(self):
        out = self.assess((("00", "State governments"), ("01", "County governments")), "")
        self.assertEqual(out["status"], "likely_eligible")
        self.assertNotEqual(out["certainty"], "confirmed")
        self.assertIn("not a guarantee", out["reasoning"])

    def test_state_government_in_notes(self):
        out = self.assess(OTHERS, "Eligible applicants include States, local governments, and federally "
                                  "recognized tribes.")
        self.assertEqual(out["status"], "likely_eligible")
        self.assertIn("States", out["quote"])

    def test_explicit_state_exclusion_is_confirmed(self):
        out = self.assess(OTHERS, "Universities may apply. State governments are not eligible to apply.")
        self.assertEqual(out["status"], "ineligible")
        self.assertEqual(out["certainty"], "confirmed")

    def test_conflict_between_field_and_notes_needs_review(self):
        out = self.assess((("00", "State governments"),), NOAA_NOTES)
        self.assertEqual(out["status"], "needs_review")

    def test_other_eligible_applicants_list_is_additive(self):
        # NIH wording observed live: the notes ADD categories to the structured applicant types.
        notes = ("Other Eligible Applicants include the following: Alaska Native and Native Hawaiian Serving "
                 "Institutions; Eligible Agencies of the Federal Government; Faith-based or Community-based "
                 "Organizations; Hispanic-serving Institutions.")
        out = self.assess((("00", "State governments"), ("25", "Others (see text field)")), notes)
        self.assertEqual(out["status"], "likely_eligible")
        others_only = self.assess(OTHERS, notes)
        self.assertNotEqual(others_only["status"], "likely_ineligible")

    def test_united_states_is_not_state_government(self):
        out = self.assess(OTHERS, "Eligible applicants are organizations in the United States, including "
                                  "universities and nonprofits.")
        self.assertEqual(out["status"], "likely_ineligible")

    # --- AI merge rules -------------------------------------------------------
    def ai(self, verdict, quote, status="ok"):
        return {"status": status, "verdict": verdict, "reasoning": "Interpretation of the notes.", "quote": quote,
                "quote_source": "Grants.gov eligibility notes", "to_verify": ["Ask the program officer."],
                "model": "grantscope-gpt4o"}

    def test_ai_resolves_unclear_case(self):
        notes = "Applicants must be entities with jurisdiction over coastal zone management programs."
        base = self.assess(OTHERS, notes)
        self.assertEqual(base["status"], "needs_review")
        out = self.assess(OTHERS, notes, self.ai("likely_eligible", "entities with jurisdiction over coastal zone"))
        self.assertEqual(out["status"], "likely_eligible")
        self.assertEqual(out["basis"], "ai_interpretation")
        self.assertIn("AI", out["certainty_label"])

    def test_ai_cannot_override_confirmed_restriction(self):
        notes = "State governments are not eligible to apply."
        out = self.assess(OTHERS, notes, self.ai("likely_eligible", "State governments are not eligible"))
        self.assertEqual(out["status"], "ineligible")
        field = screen_eligibility(details(types=(("12", "Nonprofits"),)), DEQ, ai=self.ai("likely_eligible", "x y z"))
        self.assertEqual(field["status"], "ineligible")

    def test_ai_disagreement_becomes_needs_review(self):
        out = self.assess(OTHERS, NOAA_NOTES, self.ai("likely_eligible", "Eligible applicants are: Institutions"))
        self.assertEqual(out["status"], "needs_review")
        self.assertEqual(out["basis"], "conflict")

    def test_failed_ai_keeps_rule_result(self):
        out = self.assess(OTHERS, NOAA_NOTES, {"status": "error", "errors": ["APITimeoutError"]})
        self.assertEqual(out["status"], "likely_ineligible")

    def test_eligibility_evaluator_validation(self):
        from services.ai_eligibility import AzureEligibilityEvaluator
        d = details(types=OTHERS, text=NOAA_NOTES)
        rec = {"title": "NOAA"}
        good = json.dumps({"verdict": "likely_ineligible", "reasoning": "State governments are not listed.",
                           "quote": "Eligible applicants are: Institutions of higher education; Other nonprofits",
                           "to_verify": ["Confirm with NOAA."]})
        out = AzureEligibilityEvaluator(CONFIG, client=FakeClient(good))(rec, DEQ, d)
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["quote_source"], "Grants.gov eligibility notes")
        fabricated = json.dumps({"verdict": "likely_eligible", "reasoning": "States may apply.",
                                 "quote": "State governments are eligible applicants"})
        self.assertEqual(AzureEligibilityEvaluator(CONFIG, client=FakeClient(fabricated))(rec, DEQ, d)["status"],
                         "rejected")
        guarantee = json.dumps({"verdict": "likely_eligible", "reasoning": "Eligibility is guaranteed.",
                                "quote": "Eligible applicants are: Institutions of higher education"})
        self.assertEqual(AzureEligibilityEvaluator(CONFIG, client=FakeClient(guarantee))(rec, DEQ, d)["status"],
                         "rejected")
        down = AzureEligibilityEvaluator(CONFIG, client=FakeClient(exc=ConnectionError("down")))(rec, DEQ, d)
        self.assertEqual(down["status"], "error")

    def test_engine_never_sends_confirmed_exclusions_to_ai(self):
        from services.ai_eligibility import AzureEligibilityEvaluator
        client = FakeClient(json.dumps({"verdict": "likely_eligible", "reasoning": "x", "quote": "Nonprofits a b"}))
        out = run_matching(DEQ, SETTINGS, search_fn=lambda k, r: [hit("1", "Drinking Water Grants")],
                           details_fn=lambda g: details(types=(("12", "Nonprofits"),)), today=TODAY,
                           eligibility_evaluator=AzureEligibilityEvaluator(CONFIG, client=client))
        self.assertEqual(client.calls, [])
        self.assertEqual(out["results"], [])

    def test_engine_ai_moves_unclear_to_likely_ineligible(self):
        from services.ai_eligibility import AzureEligibilityEvaluator
        notes = "Applications are accepted from regional fishery management councils established under the Act."
        reply = json.dumps({"verdict": "likely_ineligible", "reasoning": "Only fishery councils may apply.",
                            "quote": "accepted from regional fishery management councils"})
        out = run_matching(DEQ, SETTINGS, search_fn=lambda k, r: [hit("2", "Coastal Water Quality Grants")],
                           details_fn=lambda g: details(types=OTHERS, text=notes), today=TODAY,
                           eligibility_evaluator=AzureEligibilityEvaluator(CONFIG, client=FakeClient(reply)))
        self.assertEqual(out["results"], [])
        self.assertEqual(out["likely_ineligible"][0]["eligibility"]["basis"], "ai_interpretation")
        self.assertEqual(out["ai_eligibility"]["accepted"], 1)


class ConfigSafetyTests(unittest.TestCase):
    def test_describe_config_hides_key(self):
        from services.ai_matching import describe_config
        cfg = load_ai_config({"AZURE_OPENAI_ENDPOINT": "https://grantscope-team07.openai.azure.com/",
                              "AZURE_OPENAI_API_KEY": "sk-SECRET-123"})
        text = json.dumps(describe_config(cfg))
        self.assertNotIn("sk-SECRET-123", text)
        self.assertNotIn("grantscope-team07", text)
        self.assertIn("grantscope-gpt4o", text)
        self.assertEqual(describe_config(None), {"configured": False})


if __name__ == "__main__":
    unittest.main()
