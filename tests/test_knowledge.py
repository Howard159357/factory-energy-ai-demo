"""The generated knowledge corpus must agree with the plant configuration it describes."""

import re
import uuid
from pathlib import Path

import pytest

from factory_energy.config.loader import load_meters, load_settings
from factory_energy.rag.embed import HashEmbedder
from factory_energy.rag.ingest import DEFAULT_SOURCES, discover, ingest
from factory_energy.rag.settings import REPO_ROOT
from factory_energy.rag.store import KnowledgeStore
from factory_energy.simulator.electrical import BASE_PF

KNOWLEDGE = REPO_ROOT / "docs" / "knowledge"
NOTICE = "*Fictional document for the DemoTronics demo plant. All content is synthetic.*"
METER_TOKEN = re.compile(r"\b(?:MDB-\d+|SMT-L\d+|[A-Z]{2,4}-\d{2})\b")
UNIT_ROW = re.compile(
    r"^\|\s*([A-Z]+-[A-Z0-9]+)\s*\|\s*([^|]+?)\s*\|\s*(MDB-\d)\s*\|\s*([\d.,]+)\s*\|\s*([\d.]+)\s*\|"
)


def corpus() -> dict[str, str]:
    return {p.relative_to(KNOWLEDGE).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(KNOWLEDGE.rglob("*.md"))}


def test_every_document_is_marked_synthetic_and_controlled() -> None:
    docs = corpus()
    assert len(docs) >= 20
    for name, text in docs.items():
        assert text.startswith("# "), name
        assert NOTICE in text.splitlines()[2], name
        if name != "README.md":
            assert "| Document ID |" in text, name


def test_only_configured_meter_ids_are_mentioned() -> None:
    catalog = load_meters()
    known = {m.meter_id for m in (*catalog.feeders, *catalog.equipment)}
    for name, text in corpus().items():
        unknown = set(METER_TOKEN.findall(text)) - known - {"SOP-01", "SOP-02", "SOP-03",
                                                           "SOP-04", "SOP-05", "SOP-06",
                                                           "SOP-07", "EM-01", "EM-02",
                                                           "EM-03", "EM-04"}
        unknown = {u for u in unknown if not u.startswith("EQ-")}
        assert not unknown, f"{name}: {sorted(unknown)}"


def test_equipment_tables_match_the_meter_catalog() -> None:
    catalog = load_meters()
    equipment = {e.meter_id: e for e in catalog.equipment}
    seen: set[str] = set()
    for name, text in corpus().items():
        if not name.startswith("equipment/"):
            continue
        for line in text.splitlines():
            match = UNIT_ROW.match(line)
            if not match:
                continue
            meter_id, title, board, rated, pf = match.groups()
            spec = equipment[meter_id]
            assert (title, board) == (spec.name, spec.feeder), f"{name}: {meter_id}"
            assert float(rated.replace(",", "")) == spec.rated_kw, f"{name}: {meter_id}"
            assert float(pf) == BASE_PF[spec.category], f"{name}: {meter_id}"
            seen.add(meter_id)
    assert seen == set(equipment)  # every sub-meter has a manual entry


def test_tariff_and_demand_figures_match_the_settings() -> None:
    settings = load_settings()
    docs = corpus()
    guide = docs["energy-management/EM-03_tariff_guide.md"]
    for season in ("summer", "other"):
        for price in (*settings.tariff.energy_per_kwh.model_dump()[season].values(),
                      *settings.tariff.demand_per_kw_month.model_dump()[season].values()):
            assert f"NT${price:,.2f}" in guide, price
    demand = docs["energy-management/EM-02_demand_management.md"]
    contract = settings.demand.contract_capacity_kw
    assert f"{contract:,.0f} kW" in demand
    assert f"{contract * settings.demand.warning_ratio:,.0f} kW" in demand


def test_no_contact_details_or_links() -> None:
    pattern = re.compile(r"https?://|www\.|@[a-z0-9-]+\.[a-z]|\+\d{2,3}[ -]?\d", re.IGNORECASE)
    for name, text in corpus().items():
        assert not pattern.search(text), name


@pytest.fixture(scope="module")
def full_index(chroma: object) -> KnowledgeStore:
    store = KnowledgeStore(chroma, HashEmbedder(), f"k-{uuid.uuid4().hex}")
    report = ingest(store, discover(DEFAULT_SOURCES))
    assert len(report.added) >= 25
    return store


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("How long does the reflow oven preheat before the SMT line starts?",
         "docs/knowledge/equipment/EQ-01_reflow_oven.md"),
        ("In which order are machines started on Monday morning to avoid a simultaneous start?",
         "docs/knowledge/sop/SOP-01_monday_startup.md"),
        ("How is the exceedance penalty above the contract capacity billed?",
         "docs/knowledge/energy-management/EM-03_tariff_guide.md"),
        ("What do I do when the night-load baseline suggests a compressed air leak?",
         "docs/knowledge/sop/SOP-04_compressed_air_leak.md"),
        ("How do I check the capacitor bank when power factor is low?",
         "docs/knowledge/sop/SOP-05_power_factor_check.md"),
    ],
)
def test_real_corpus_questions_find_their_document(
    full_index: KnowledgeStore, question: str, expected: str
) -> None:
    sources = [p.source for p in full_index.search(question, k=3)]
    assert expected in sources, sources


def test_project_docs_are_indexed_too(full_index: KnowledgeStore) -> None:
    indexed = set(full_index.sources())
    assert {"docs/anomaly_detection.md", "docs/forecasting.md"} <= indexed
    assert all(Path(REPO_ROOT / s).exists() for s in indexed)
