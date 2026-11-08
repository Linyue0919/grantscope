"""Unit tests for presentation-only section assignment (ui/brief_sections.py).

Run: python -m unittest discover -s tests -v
"""
import dataclasses
import unittest
from datetime import date

from ui.brief_sections import SECTION_RULES, assign_section, fit_tier, group_views
from ui.view_model import CONFIRMED, NOT_STATED, OpportunityView


def view(**overrides):
    base = dict(id="1", title="Grant", short_name="Grant", agency_full_name="EPA", status="open",
                backend_section="priority", deadline_date=date(2027, 1, 15), days_left=60, fit_score=65,
                eligibility_positive=True, eligibility_restricted=False, award_status=CONFIRMED)
    base.update(overrides)
    v = OpportunityView(**base)
    v.fit_tier = fit_tier(v.fit_score)
    return v


class FitTierTests(unittest.TestCase):
    def test_backend_level_names_and_thresholds(self):
        self.assertEqual(fit_tier(60), "Strong")
        self.assertEqual(fit_tier(59), "Moderate")
        self.assertEqual(fit_tier(30), "Moderate")
        self.assertEqual(fit_tier(29), "Low")
        self.assertEqual(fit_tier(None), "Low")
        self.assertEqual(SECTION_RULES["strong_min"], 60)
        self.assertEqual(SECTION_RULES["moderate_min"], 30)


class AssignSectionTests(unittest.TestCase):
    def test_top_requires_all_conditions(self):
        self.assertEqual(assign_section(view()), "top")
        self.assertEqual(assign_section(view(fit_score=30)), "top")  # Moderate allowed with a stated award

    def test_strong_fit_reaches_top_without_award(self):
        self.assertEqual(assign_section(view(fit_score=82, award_status=NOT_STATED)), "top")
        self.assertEqual(assign_section(view(fit_score=60, award_status=NOT_STATED)), "top")

    def test_moderate_fit_without_award_needs_check(self):
        self.assertEqual(assign_section(view(fit_score=59, award_status=NOT_STATED)), "check")
        self.assertEqual(assign_section(view(fit_score=40, award_status=NOT_STATED)), "check")

    def test_strong_fit_still_needs_eligibility_deadline_and_region(self):
        self.assertEqual(assign_section(view(fit_score=82, award_status=NOT_STATED, eligibility_positive=False)), "check")
        self.assertEqual(assign_section(view(fit_score=82, deadline_date=None, days_left=None)), "check")
        self.assertEqual(assign_section(view(fit_score=82, region_flags=["alaska"])), "check")
        self.assertEqual(assign_section(view(fit_score=82, eligibility_restricted=True)), "check")

    def test_soon_for_forecasts(self):
        self.assertEqual(assign_section(view(status="forecasted", backend_section="upcoming")), "soon")

    def test_lower_rules(self):
        self.assertEqual(assign_section(view(fit_score=29)), "lower")
        self.assertEqual(assign_section(view(fit_score=None)), "lower")
        self.assertEqual(assign_section(view(backend_section="likely_ineligible")), "lower")
        self.assertEqual(assign_section(view(backend_section="low_evidence")), "lower")
        self.assertEqual(assign_section(view(known_blocker="Cost share 1:1")), "lower")

    def test_check_rules(self):
        self.assertEqual(assign_section(view(eligibility_restricted=True)), "check")
        self.assertEqual(assign_section(view(eligibility_positive=False)), "check")  # no positive evidence
        self.assertEqual(assign_section(view(deadline_date=None, days_left=None)), "check")
        self.assertEqual(assign_section(view(fit_score=45, award_status=NOT_STATED)), "check")
        self.assertEqual(assign_section(view(region_flags=["great lakes"])), "check")

    def test_missing_information_never_upgrades(self):
        """Removing any fact from a view can only keep or lower its section."""
        order = {"top": 0, "check": 1, "lower": 2, "soon": 3}
        missing = {"deadline_date": None, "days_left": None, "award_status": NOT_STATED,
                   "eligibility_positive": False, "fit_score": None}
        for start in (view(), view(fit_score=40), view(eligibility_restricted=True), view(fit_score=20),
                      view(award_status=NOT_STATED), view(fit_score=40, award_status=NOT_STATED)):
            before = assign_section(start)
            for name, value in missing.items():
                after = assign_section(dataclasses.replace(start, **{name: value}))
                self.assertGreaterEqual(order[after], order[before],
                                        f"removing {name} moved {before} -> {after}")


class GroupingTests(unittest.TestCase):
    def test_fit_order_kept_when_backend_is_fit_sorted(self):
        scores = [82, 62, 45, 40, 38]  # backend priority list is ranked by fit score
        views = [view(id=str(i), fit_score=s, award_status=NOT_STATED if i < 2 else CONFIRMED)
                 for i, s in enumerate(scores)]
        for v in views:
            v.section = assign_section(v)
        top = [v.fit_score for v in group_views(views)["top"]]
        self.assertEqual(top, [82, 62, 45, 40, 38])

    def test_backend_order_preserved_within_sections(self):
        views = [view(id="a", fit_score=40), view(id="b", fit_score=90), view(id="c", fit_score=45, award_status=NOT_STATED),
                 view(id="d", fit_score=70), view(id="e", fit_score=10)]
        for v in views:
            v.section = assign_section(v)
        groups = group_views(views)
        self.assertEqual([v.id for v in groups["top"]], ["a", "b", "d"])  # not re-sorted by score
        self.assertEqual([v.id for v in groups["check"]], ["c"])
        self.assertEqual([v.id for v in groups["lower"]], ["e"])


if __name__ == "__main__":
    unittest.main()
