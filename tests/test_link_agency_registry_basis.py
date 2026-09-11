"""issue #23: the crosswalk records HOW an agency join was made -- `basis: exact` (a
mechanical name match) versus `alias`/`successor` (a human asserted an identity the names
do not state outright) -- but `link_agency_registry.py --stamp` writes only the slug and
corpus, so a document carrying an alias join is indistinguishable in frontmatter from one
that matched mechanically. Six of this corpus's 37 crosswalk entries are `alias`, each with
a reviewer and a date; none of that survives into the 223 stamped documents today.

The seam is `src/link_agency_registry.py`'s own module functions -- `stamp()` (the writer)
and `stamp_state()` (--check's own verifier of what was written), the same pair this file
already uses to keep the slug stamp honest. `REPORTS` is monkeypatched to a scratch
directory of synthetic documents so these tests never touch the 242 committed reports.
"""
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import link_agency_registry as lar                              # noqa: E402


def write_doc(dir_: Path, doc_id: str, audited_agency: str, extra_fm: str = "") -> Path:
    p = dir_ / f"{doc_id}.md"
    p.write_text(
        f"---\nid: {doc_id}\naudited_agency: {audited_agency}\n{extra_fm}---\nbody\n",
        encoding="utf-8",
    )
    return p


# A mapping with one entry of each real shape this corpus's crosswalk actually carries:
# an alias WITH review metadata (`Driver and Motor Vehicles Services`, real note shortened)
# and an alias WITH NONE (`Mortuary and Cemetery Board, State`, real committed entry --
# `note` only, no `reviewed_by`/`reviewed_on`). Real strings, not placeholders, so a
# regression against the actual crosswalk shape is what these tests would catch.
MAPPING = {
    "Driver and Motor Vehicles Services": {
        "slug": "department-of-transportation-driver-and-motor-vehicle-services-division",
        "basis": "alias",
        "note": "Same body -- DMV is not a standalone agency.",
        "reviewed_by": "@morficflux",
        "reviewed_on": "2026-08-01",
    },
    "Mortuary and Cemetery Board, State": {
        "slug": "mortuary-and-cemetery-board",
        "basis": "alias",
        "note": "The registry drops the 'State' prefix.",
    },
}


@pytest.fixture
def reports_dir(tmp_path, monkeypatch):
    d = tmp_path / "reports"
    d.mkdir()
    monkeypatch.setattr(lar, "REPORTS", d)
    return d


def test_stamp_writes_the_crosswalks_basis_alongside_the_slug(reports_dir):
    write_doc(reports_dir, "2024-01", "Driver and Motor Vehicles Services")
    lar.stamp(MAPPING)
    fm = lar.frontmatter(reports_dir / "2024-01.md")
    assert fm.get("agency_registry_basis") == "alias"


def test_stamp_carries_review_metadata_when_the_entry_has_it(reports_dir):
    write_doc(reports_dir, "2024-01", "Driver and Motor Vehicles Services")
    lar.stamp(MAPPING)
    fm = lar.frontmatter(reports_dir / "2024-01.md")
    assert fm.get("agency_registry_reviewed_by") == "@morficflux"
    assert fm.get("agency_registry_reviewed_on") == "2026-08-01"


def test_stamp_writes_no_review_fields_when_the_entry_carries_none(reports_dir):
    """An entry with no `reviewed_by`/`reviewed_on` (the real committed Mortuary and
    Cemetery Board entry) must not gain fabricated review fields -- an empty placeholder
    would misread as "reviewed, by nobody" rather than "not reviewed"."""
    write_doc(reports_dir, "2024-02", "Mortuary and Cemetery Board, State")
    lar.stamp(MAPPING)
    fm = lar.frontmatter(reports_dir / "2024-02.md")
    assert fm.get("agency_registry_basis") == "alias"
    assert "agency_registry_reviewed_by" not in fm
    assert "agency_registry_reviewed_on" not in fm


def test_check_fails_when_a_stamped_documents_basis_has_drifted(reports_dir):
    """The failure #23 exists to prevent: the crosswalk's basis for an agency changes (or
    was never stamped) but the document still carries the old slug -- exactly matching --
    so nothing about the existing slug/corpus check notices. `--check` must catch this
    exactly as it already catches a stale slug."""
    p = write_doc(reports_dir, "2024-01", "Driver and Motor Vehicles Services")
    # Slug and corpus correct, basis stale (the crosswalk says `alias`, the document
    # still says `exact` -- as if it had been stamped before a human re-based it).
    text = p.read_text(encoding="utf-8")
    stamped = text.replace(
        "audited_agency: Driver and Motor Vehicles Services\n",
        "audited_agency: Driver and Motor Vehicles Services\n"
        "agency_registry_slug: department-of-transportation-driver-and-motor-vehicle-services-division\n"
        "agency_registry_corpus: executive-regulatory-frameworks\n"
        "agency_registry_basis: exact\n",
    )
    p.write_text(stamped, encoding="utf-8")

    want, stamped_count = lar.stamp_state(MAPPING)
    assert (want, stamped_count) == (1, 0), (
        "a document whose stamped basis disagrees with the crosswalk must not count as "
        "correctly stamped"
    )
