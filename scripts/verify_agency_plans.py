"""Re-verify data/agency_strategic_plans.json against the official plan PDFs.

Downloads each profiled agency's plan from the OSBM link, extracts text per
page with `pdftotext` (poppler-utils), and checks that:
  * every goal quote appears verbatim on its cited PDF page, and
  * every matching term appears on at least one of its evidence pages.

Usage: python scripts/verify_agency_plans.py      (exit code 1 on any mismatch)
"""
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import requests

DATA = Path(__file__).resolve().parent.parent / "data" / "agency_strategic_plans.json"


def norm(text):
    text = unicodedata.normalize("NFKC", text)
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'),
                 ("–", "-"), ("—", "-"), ("­", "")):
        text = text.replace(a, b)
    text = re.sub(r"-\s*\n\s*", "-", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def has_term(term, text):
    return re.search(r"(?<![a-z0-9])" + re.escape(norm(term)) + r"(?:s|es)?(?![a-z0-9])", text) is not None


def pdf_pages(url, workdir):
    pdf = Path(workdir) / "plan.pdf"
    response = requests.get(url, timeout=90, headers={"User-Agent": "GrantScope plan verifier"})
    response.raise_for_status()
    pdf.write_bytes(response.content)
    txt = Path(workdir) / "plan.txt"
    subprocess.run(["pdftotext", "-q", str(pdf), str(txt)], check=True)
    return [norm(page) for page in txt.read_text(encoding="utf-8", errors="replace").split("\f")]


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    failures = 0
    for agency in data["agencies"]:
        with tempfile.TemporaryDirectory() as workdir:
            try:
                pages = pdf_pages(agency["plan_url"], workdir)
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL {agency['name']}: could not download/extract plan ({exc})")
                failures += 1
                continue
        for goal in agency["goals"]:
            page = pages[goal["page"] - 1] if goal["page"] <= len(pages) else ""
            if norm(goal["quote"]) not in page:
                print(f"FAIL {goal['goal_id']}: quote not found on page {goal['page']}")
                failures += 1
            for term in goal["terms"]:
                if not any(has_term(term, pages[p - 1]) for p in goal["evidence_pages"] if p <= len(pages)):
                    print(f"FAIL {goal['goal_id']}: term '{term}' not on pages {goal['evidence_pages']}")
                    failures += 1
        print(f"checked {agency['name']}: {len(agency['goals'])} goals")
    print("OK: all quotes and terms verified" if not failures else f"{failures} problem(s) found")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
