"""issue #23, the second writer: `ingest_audits.py`'s `registry_link()` stamps the same two
fields `link_agency_registry.py --stamp` backfills, for every NEWLY ingested report. Fixing
only the backfill script would leave the very next ingested audit missing the basis stamp
again the day after this ships -- the identical bug, reintroduced by the other writer.

Seam: `registry_link()` is a pure function of one string, reading the crosswalk file it is
pointed at via the module's `_CROSSWALK` cache -- reset here per test so one test's crosswalk
never leaks into another's.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import ingest_audits as ing                                      # noqa: E402


@pytest.fixture(autouse=True)
def reset_crosswalk_cache(monkeypatch):
    """registry_link() memoizes the crosswalk in a module global on first call; without
    resetting it, whichever test runs first would decide what every later test reads."""
    monkeypatch.setattr(ing, "_CROSSWALK", None)


@pytest.fixture
def crosswalk_file(tmp_path, monkeypatch):
    meta = tmp_path / "_meta"
    meta.mkdir()
    p = meta / "agency-crosswalk.yml"
    p.write_text(
        "mapping:\n"
        "  'Driver and Motor Vehicles Services':\n"
        "    slug: department-of-transportation-driver-and-motor-vehicle-services-division\n"
        "    basis: alias\n"
        "    note: Same body -- DMV is not a standalone agency.\n"
        "    reviewed_by: '@morficflux'\n"
        "    reviewed_on: '2026-08-01'\n"
        "  'Health Authority, Oregon':\n"
        "    slug: oregon-health-authority\n"
        "    basis: exact\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ing, "REPO_ROOT", tmp_path)
    return p


def test_registry_link_carries_the_basis(crosswalk_file):
    fields = ing.registry_link("Driver and Motor Vehicles Services")
    assert fields.get("agency_registry_basis") == "alias"


def test_registry_link_carries_review_metadata_when_present(crosswalk_file):
    fields = ing.registry_link("Driver and Motor Vehicles Services")
    assert fields.get("agency_registry_reviewed_by") == "@morficflux"
    assert fields.get("agency_registry_reviewed_on") == "2026-08-01"


def test_registry_link_omits_review_metadata_when_the_entry_has_none(crosswalk_file):
    fields = ing.registry_link("Health Authority, Oregon")
    assert fields.get("agency_registry_basis") == "exact"
    assert "agency_registry_reviewed_by" not in fields
    assert "agency_registry_reviewed_on" not in fields
