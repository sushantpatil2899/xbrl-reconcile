"""Fetch and flatten the calculation linkbase of a filing.

An XBRL filing is not one file. The instance document holds the numbers, and
separate linkbases hold the relationships between tags. The calculation linkbase
is the filer's own arithmetic: children sum to a parent, each with a weight of
plus or minus one, so `GrossProfit = Revenues - CostOfRevenue` is stated by the
company rather than inferred by us.

This is the only source of that. SEC's Data Sets carry the presentation linkbase
but not this one, so it has to come from the filing directory on EDGAR.

Two things about that directory, both established by reading a real one rather
than by assuming. Its `index.json` lists every file, and the calculation linkbase
is the one whose name ends `_cal.xml`. The `type` field cannot be used to find it:
it reads `text.gif` for every file in the listing, including the XML.

The parse is mechanical and stays that way. Concept names are stored exactly as
the filing writes them, `us-gaap_GrossProfit` with an underscore, and weights and
orders as the text they appear as. Turning those into the project's taxonomy:Tag
convention is a transformation, and transformations belong in dbt.

Each end of an arc also keeps the schema its concept is declared in, because that
is what makes a tag custom, definitionally rather than by guesswork:

    http://xbrl.fasb.org/us-gaap/2017/elts/us-gaap-2017-01-31.xsd#us-gaap_GrossProfit
    crm-20180131.xsd#crm_SomethingCustom

A standard concept is referenced by absolute URL to the taxonomy that defines it. A
concept the filer invented is referenced relatively, because it is declared in the
filing's own schema sitting in the same directory. So a relative schema means a
custom tag, with no list of known prefixes to maintain.
"""

import json
import xml.etree.ElementTree as ET

ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
LINKBASE_PREFIX = "raw/linkbase"

# Bumped when the shape of arcs.json changes. A run re-parses any filing whose
# stored arcs are behind, reading the XML already in the bucket and making no
# request, which is what keeping the raw file as published buys.
ARCS_FORMAT = 2

LINK_NS = "{http://www.xbrl.org/2003/linkbase}"
XLINK_NS = "{http://www.w3.org/1999/xlink}"
CALCULATION_SUFFIX = "_cal.xml"


def filing_directory(cik: int, accession: str) -> str:
    """EDGAR wants the CIK unpadded and the accession without its dashes."""
    return f"{ARCHIVES}/{cik}/{accession.replace('-', '')}"


def index_url(cik: int, accession: str) -> str:
    return f"{filing_directory(cik, accession)}/index.json"


def linkbase_url(cik: int, accession: str, filename: str) -> str:
    return f"{filing_directory(cik, accession)}/{filename}"


def linkbase_key(cik10: str, accession: str, name: str) -> str:
    """A filing is immutable once accepted, so the accession is the whole version."""
    return f"{LINKBASE_PREFIX}/cik={cik10}/{accession}/{name}"


def calculation_filename(index_json: bytes) -> str | None:
    """The calculation linkbase in a filing directory, or None when it has none.

    Some filings, mostly early ones, carry no calculation linkbase at all. That is
    an answer about the filing, not a failure to fetch.
    """
    items = json.loads(index_json)["directory"]["item"]
    names = sorted(item["name"] for item in items if item["name"].endswith(CALCULATION_SUFFIX))
    return names[0] if names else None


def parse_calculation_arcs(xml_bytes: bytes) -> list[dict]:
    """Flatten a calculation linkbase into one row per arc.

    A linkbase is XLink: each network declares locators that give a label to a
    concept, then arcs that join two labels. Resolving a locator is splitting its
    href on the fragment, because `.../us-gaap-2017.xsd#us-gaap_GrossProfit` points
    at the concept by id.

    Every arc keeps its role. A filing has around a hundred networks and most are
    footnote detail, so an arc without its role is ambiguous: `Assets` being a child
    of something in a fair value note says nothing about the balance sheet.
    """
    root = ET.fromstring(xml_bytes)
    arcs = []
    for network in root.findall(f"{LINK_NS}calculationLink"):
        role = network.get(f"{XLINK_NS}role", "")
        locators = {}
        for locator in network.findall(f"{LINK_NS}loc"):
            label = locator.get(f"{XLINK_NS}label")
            href = locator.get(f"{XLINK_NS}href", "")
            if label and "#" in href:
                schema, concept = href.rsplit("#", 1)
                locators[label] = (concept, schema)
        for arc in network.findall(f"{LINK_NS}calculationArc"):
            parent = locators.get(arc.get(f"{XLINK_NS}from"))
            child = locators.get(arc.get(f"{XLINK_NS}to"))
            # An arc whose ends are not declared in its own network is malformed and
            # cannot be resolved to concepts, so it is dropped rather than guessed at.
            if not parent or not child:
                continue
            arcs.append(
                {
                    "role": role,
                    "parent": parent[0],
                    "parent_schema": parent[1],
                    "child": child[0],
                    "child_schema": child[1],
                    "weight": arc.get("weight"),
                    "order": arc.get("order"),
                }
            )
    return arcs
