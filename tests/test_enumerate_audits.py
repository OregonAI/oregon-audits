"""enumerate_audits.py writes what #53 wrote by hand, so a re-run cannot revert it (#59)."""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import enumerate_audits as ea  # noqa: E402

STREAM = "https://records.sos.state.or.us/ORSOSCMSearch/Search/DocumentStream.ashx?uri=7132832"


def test_every_orms_viewer_shape_fetches_the_stream_under_the_same_id():
    for link in ("https://records.sos.state.or.us/ORSOSWebDrawer/Recordhtml/7132832",
                 "https://records.sos.state.or.us/ORSOSWebDrawer/Record/7132832",
                 "https://records.sos.state.or.us/ORSOSCMSearch/Search/RecordViewer.aspx?uri=7132832"):
        assert ea.fetch_target(link) == (STREAM, "pdf"), link


def test_a_direct_pdf_is_fetched_as_itself():
    for link in ("https://sos.oregon.gov/audits/Documents/2026-19.pdf",
                 "https://sos.oregon.gov/audits/documents/2026-19.PDF"):
        assert ea.fetch_target(link) == (link, "pdf")


def test_an_unknown_shape_is_not_guessed():
    assert ea.fetch_target("https://sos.oregon.gov/audits/Pages/some-report.aspx") is None


def _item(num, url):
    return {"Link": {"Description": f"Report No. {num}", "Url": url}, "Title": "T",
            "Audit_x0020_Type": ["Performance"], "Agency": ["A"], "Year": "2026", "Month": "1"}


def test_source_url_keeps_the_list_link_and_baselines_carry_on_url():
    viewer = "https://records.sos.state.or.us/ORSOSWebDrawer/Recordhtml/7132832"
    direct = "https://sos.oregon.gov/audits/Documents/2026-19.pdf"
    recs, anomalies = ea.build_records(
        [_item("2020-01", viewer), _item("2026-19", direct),
         _item("2026-20", "https://example.org/x.aspx")],
        {STREAM: "a" * 64})
    by = {r["id"]: r for r in recs}
    assert by["2020-01"]["url"] == STREAM and by["2020-01"]["source_url"] == viewer
    assert by["2020-01"]["sha256"] == "a" * 64
    assert "source_url" not in by["2026-19"] and by["2026-19"]["sha256"] == ""
    assert "2026-20" not in by and any("2026-20" in a for a in anomalies)


def test_a_carried_baseline_is_written_double_quoted_like_the_drift_job_writes_it():
    recs, _ = ea.build_records(
        [_item("2020-01", "https://records.sos.state.or.us/ORSOSWebDrawer/Recordhtml/7132832")],
        {STREAM: "b" * 64})
    assert f'sha256: "{"b" * 64}"' in ea.render(recs, [], [])
    assert yaml.safe_load(ea.render(recs, [], []))["sources"][0]["sha256"] == "b" * 64
