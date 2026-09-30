import json

import pytest

from xbrl_reconcile.ingest.linkbase import (
    calculation_filename,
    index_url,
    linkbase_key,
    linkbase_url,
    parse_calculation_arcs,
)

# Shaped like a real linkbase, which matters for one reason: a standard concept is
# referenced by absolute URL to the taxonomy that defines it, and one the filer
# invented is referenced relatively, because it lives in the filing's own schema.
# That difference is what makes a tag custom, so a fixture using relative hrefs
# throughout would hide the rule it is meant to exercise.
FASB = "http://xbrl.fasb.org/us-gaap/2017/elts/us-gaap-2017-01-31.xsd"

LINKBASE = f"""<?xml version="1.0" encoding="UTF-8"?>
<linkbase xmlns="http://www.xbrl.org/2003/linkbase"
          xmlns:xlink="http://www.w3.org/1999/xlink">
  <calculationLink xlink:role="http://www.example.com/role/ConsolidatedStatementsOfOperations">
    <loc xlink:href="{FASB}#us-gaap_GrossProfit" xlink:label="gp"/>
    <loc xlink:href="{FASB}#us-gaap_SalesRevenueServicesNet" xlink:label="rev"/>
    <loc xlink:href="{FASB}#us-gaap_CostOfServices" xlink:label="cost"/>
    <calculationArc xlink:from="gp" xlink:to="rev" weight="1" order="1"/>
    <calculationArc xlink:from="gp" xlink:to="cost" weight="-1" order="2"/>
  </calculationLink>
  <calculationLink xlink:role="http://www.example.com/role/BusinessCombinationsDetails">
    <loc xlink:href="{FASB}#us-gaap_Assets" xlink:label="a"/>
    <loc xlink:href="crm-20180131.xsd#crm_SomethingCustom" xlink:label="c"/>
    <calculationArc xlink:from="a" xlink:to="c" weight="1" order="1"/>
  </calculationLink>
</linkbase>
""".encode()


def test_arcs_carry_the_filers_own_arithmetic():
    arcs = parse_calculation_arcs(LINKBASE)

    income_statement = [a for a in arcs if a["role"].endswith("ConsolidatedStatementsOfOperations")]
    assert [(a["parent"], a["child"], a["weight"]) for a in income_statement] == [
        ("us-gaap_GrossProfit", "us-gaap_SalesRevenueServicesNet", "1"),
        ("us-gaap_GrossProfit", "us-gaap_CostOfServices", "-1"),
    ]


def test_every_arc_keeps_its_role():
    """A filing has about a hundred networks and most are footnotes, so an arc
    without its role cannot be told from a statement one."""
    roles = {arc["role"] for arc in parse_calculation_arcs(LINKBASE)}

    assert len(roles) == 2


def test_concept_names_are_stored_as_the_filing_writes_them():
    """Turning us-gaap_X into us-gaap:X is a transformation, and those live in dbt."""
    arcs = parse_calculation_arcs(LINKBASE)

    assert any(arc["child"] == "crm_SomethingCustom" for arc in arcs)
    assert all("_" in arc["parent"] for arc in arcs)


def test_a_relative_schema_is_what_marks_a_tag_as_the_filers_own():
    arcs = parse_calculation_arcs(LINKBASE)

    custom = [a["child"] for a in arcs if not a["child_schema"].startswith("http")]
    standard = [a["child"] for a in arcs if a["child_schema"].startswith("http")]

    assert custom == ["crm_SomethingCustom"]
    assert "us-gaap_CostOfServices" in standard


def test_an_arc_whose_ends_are_not_declared_is_dropped():
    broken = LINKBASE.replace(
        b'<calculationArc xlink:from="gp" xlink:to="rev"',
        b'<calculationArc xlink:from="ghost" xlink:to="rev"',
    )

    arcs = parse_calculation_arcs(broken)

    assert all(arc["parent"] != "ghost" for arc in arcs)
    assert len(arcs) == 2, "the malformed arc is dropped, the sound ones survive"


def test_a_linkbase_with_no_calculation_networks_parses_to_nothing():
    empty = b'<linkbase xmlns="http://www.xbrl.org/2003/linkbase"/>'

    assert parse_calculation_arcs(empty) == []


def test_the_calculation_linkbase_is_found_by_name_not_by_type():
    """Every file in an EDGAR listing reports type text.gif, including the XML."""
    listing = json.dumps(
        {
            "directory": {
                "item": [
                    {"name": "crm-20180131.xml", "type": "text.gif"},
                    {"name": "crm-20180131_pre.xml", "type": "text.gif"},
                    {"name": "crm-20180131_cal.xml", "type": "text.gif"},
                ]
            }
        }
    ).encode()

    assert calculation_filename(listing) == "crm-20180131_cal.xml"


def test_a_filing_with_no_calculation_linkbase_is_an_answer_not_an_error():
    listing = json.dumps({"directory": {"item": [{"name": "crm-20180131.xml"}]}}).encode()

    assert calculation_filename(listing) is None


@pytest.mark.parametrize(
    "builder, expected",
    [
        (
            index_url,
            "https://www.sec.gov/Archives/edgar/data/1108524/000110852418000011/index.json",
        ),
        (
            lambda cik, accession: linkbase_url(cik, accession, "crm-20180131_cal.xml"),
            "https://www.sec.gov/Archives/edgar/data/1108524/000110852418000011/crm-20180131_cal.xml",
        ),
    ],
)
def test_edgar_paths_drop_the_dashes_and_the_padding(builder, expected):
    assert builder(1108524, "0001108524-18-000011") == expected


def test_a_filing_is_immutable_so_the_accession_is_the_whole_version():
    key = linkbase_key("0001108524", "0001108524-18-000011", "arcs.json")

    assert key == "raw/linkbase/cik=0001108524/0001108524-18-000011/arcs.json"
