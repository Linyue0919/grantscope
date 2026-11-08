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
        self.assertEqual(assign_section(view(fit_score=30)), "top")  # Moderate allowed (approved middle rule)

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
        self.assertEqual(assign_section(view(award_status=NOT_STATED)), "check")
        self.assertEqual(assign_section(view(region_flags=["great lakes"])), "check")

    def test_missing_information_never_upgrades(self):
        """Removing any fact from a view can only keep or lower its section."""
        order = {"top": 0, "check": 1, "lower": 2, "soon": 3}
        missing = {"deadline_date": None, "days_left": None, "award_status": NOT_STATED,
                   "eligibility_positive": False, "fit_score": None}
        for start in (view(), view(eligibility_restricted=True), view(fit_score=20), view(award_status=NOT_STATED)):
            before = assign_section(start)
            for name, value in missing.items():
                after = assign_section(dataclasses.replace(start, **{name: value}))
                self.assertGreaterEqual(order[after], order[before],
                                        f"removing {name} moved {before} -> {after}")


class GroupingTests(unittest.TestCase):
    def test_backend_order_preserved_within_sections(self):
        views = [view(id="a", fit_score=40), view(id="b", fit_score=90), view(id="c", award_status=NOT_STATED),
                 view(id="d", fit_score=70), view(id="e", fit_score=10)]
        for v in views:
            v.section = assign_section(v)
        groups = group_views(views)
        self.assertEqual([v.id for v in groups["top"]], ["a", "b", "d"])  # not re-sorted by score
        self.assertEqual([v.id for v in groups["check"]], ["c"])
        self.assertEqual([v.id for v in groups["lower"]], ["e"])


if __name__ == "__main__":
    unittest.main()
