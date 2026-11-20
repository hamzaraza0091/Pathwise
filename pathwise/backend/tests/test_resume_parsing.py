import pytest

from app.services.resume import parse_experience, total_years


@pytest.mark.parametrize(
    "lines,start,end,months",
    [
        (["Python Developer Intern, Acme Studio, 2025-06 to 2026-01. Built FastAPI services and SQL reports."], "2025-06", "2026-01", 8),
        (["Backend Engineer | Foo Ltd", "06/2023 – 08/2025", "- Built APIs"], "2023-06", "2025-08", 27),
        (["Data Analyst at Bar  2021-2023"], "2021-01", "2023-12", 36),
        (["Developer, Baz  Mar 2020 - Present"], "2020-03", "present", None),
    ],
)
def test_experience_date_formats(lines, start, end, months):
    entries = parse_experience(lines)
    assert len(entries) == 1
    assert entries[0]["start"] == start and entries[0]["end"] == end
    if months:
        assert entries[0]["months"] == months
    assert total_years(entries) > 0


def test_evidence_keeps_original_text():
    entries = parse_experience(["Backend Engineer | Foo Ltd 06/2023 – 08/2025"])
    assert "06/2023" in entries[0]["evidence"]


def test_year_only_ranges_are_not_mistaken_for_months():
    entries = parse_experience(["Analyst, Corp 2012-2013"])
    assert entries[0]["start"] == "2012-01" and entries[0]["end"] == "2013-12"


def test_header_falls_back_to_spacy_entities():
    from app.services.nlp import get_nlp
    from app.services.resume import parse_header

    if get_nlp() is None:
        pytest.skip("spaCy model not installed")
    header = ["Curriculum Vitae of Sarah Johnson", "sarah@example.com", "Based in London"]
    parsed = parse_header(header, "\n".join(header))
    assert parsed["name"] == "Sarah Johnson"
    assert parsed["location"] == "London"


def test_header_heuristics_still_win_for_standard_layout():
    from app.services.resume import parse_header

    header = ["Muhammad Hamza Raza", "Islamabad, Pakistan", "hamza@example.com"]
    parsed = parse_header(header, "\n".join(header))
    assert parsed["name"] == "Muhammad Hamza Raza"
    assert parsed["location"] == "Islamabad, Pakistan"
