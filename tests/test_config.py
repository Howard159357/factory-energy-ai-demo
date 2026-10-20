from pathlib import Path

import pytest
from pydantic import ValidationError

from factory_energy.__main__ import main
from factory_energy.config.loader import load_meters, load_settings
from factory_energy.config.models import MeterCatalog


def test_default_configs_load() -> None:
    catalog = load_meters()
    settings = load_settings()
    assert catalog.feeder_ids == [f"MDB-{i}" for i in range(1, 7)]
    assert len(catalog.equipment) == 23
    molders = {e.meter_id for e in catalog.equipment_on("MDB-3")}
    assert molders == {"IM-01", "IM-02", "IM-03", "IM-04"}
    assert settings.demand.contract_capacity_kw == 1250
    assert settings.demand.interval_minutes == 15


def test_equipment_must_reference_known_feeder() -> None:
    with pytest.raises(ValidationError, match="unknown feeder"):
        MeterCatalog.model_validate(
            {
                "feeders": [{"meter_id": "MDB-1", "name": "A", "rated_kw": 10}],
                "equipment": [
                    {"meter_id": "X-01", "name": "X", "feeder": "MDB-9", "category": "c",
                     "rated_kw": 1}
                ],
            }
        )


def test_duplicate_and_invalid_ids_rejected() -> None:
    feeder = {"meter_id": "MDB-1", "name": "A", "rated_kw": 10}
    with pytest.raises(ValidationError, match="duplicate"):
        MeterCatalog.model_validate({"feeders": [feeder, feeder]})
    with pytest.raises(ValidationError):
        MeterCatalog.model_validate({"feeders": [{**feeder, "meter_id": "mdb 1"}]})


def test_check_config_cli(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check-config"]) == 0
    assert "Configuration: PASS" in capsys.readouterr().out


def test_no_real_site_identifiers_in_config() -> None:
    root = Path(__file__).parents[1] / "config"
    text = "".join(p.read_text(encoding="utf-8") for p in root.glob("*.yaml")).lower()
    for token in ("dbo.", "password", "server="):
        assert token not in text
