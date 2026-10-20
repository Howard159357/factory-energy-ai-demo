from datetime import datetime

import duckdb
import numpy as np
import pandas as pd
import pytest

from factory_energy.forecasting.backtest import (
    alert_episodes,
    fingerprint,
    horizon_metrics,
    plan_units,
    run_unit,
    run_units,
)
from factory_energy.forecasting.features import FEATURES, DemandHistory, make_rows
from factory_energy.forecasting.model import (
    MODELS,
    TRAINABLE,
    LightGBMForecaster,
    LinearForecaster,
    ProfileForecaster,
    ensemble_of,
    exceedance_probability,
    pinball_loss,
)
from factory_energy.forecasting.service import cached_units, ensure_tables, store_unit


def synthetic_history(days: int = 90, seed: int = 0) -> DemandHistory:
    """A plant-like 15-min demand series: daily shape, weekends, weather and noise."""
    index = pd.date_range("2025-03-01", periods=days * 96, freq="15min")
    rng = np.random.default_rng(seed)
    hour = index.hour + index.minute / 60
    weekday = index.weekday < 5
    temp = 24 + 5 * np.sin(2 * np.pi * (hour - 9) / 24) + rng.normal(0, 0.3, len(index))
    shape = np.where((hour >= 8) & (hour < 17), 1.0, 0.45)
    kw = 500 + 600 * shape * np.where(weekday, 1.0, 0.4) + 6 * temp + rng.normal(0, 8, len(index))
    frame = pd.DataFrame({
        "kw": kw,
        "temp_c": temp,
        "day_type": np.where(
            weekday, "WORKDAY", np.where(index.weekday == 5, "SATURDAY", "SUNDAY")
        ),
        "overtime": False,
    }, index=index)
    return DemandHistory(frame)


def test_rows_use_only_information_available_at_issue_time() -> None:
    history = synthetic_history(20)
    rows = make_rows(history, horizon=4)
    target = rows.index[200]
    assert rows.loc[target, "issue"] == target - pd.Timedelta(hours=1)
    assert rows.loc[target, "last"] == history.kw[target - pd.Timedelta(hours=1)]
    assert rows.loc[target, "same_time_last_week"] == history.kw[target - pd.Timedelta(days=7)]
    assert rows.loc[target, "y"] == history.kw[target]
    assert not rows[FEATURES].isna().all().any()


def test_exceedance_probability_is_monotone_and_bounded() -> None:
    assert exceedance_probability(1200, 1300, 1400, 1300) == pytest.approx(0.5)
    assert exceedance_probability(1200, 1300, 1400, 1400) == pytest.approx(0.1, abs=1e-6)
    assert exceedance_probability(1200, 1300, 1400, 1200) == pytest.approx(0.9, abs=1e-6)
    probabilities = [exceedance_probability(1200, 1300, 1400, x) for x in range(1000, 1700, 50)]
    assert probabilities == sorted(probabilities, reverse=True)
    assert exceedance_probability(1300, 1300, 1300, 1250) == 1.0


def test_every_model_beats_persistence_and_is_calibrated() -> None:
    history = synthetic_history(90)
    rows = make_rows(history, horizon=4)
    cut = rows.index[-14 * 96]
    train, test = rows[rows.index < cut], rows[rows.index >= cut]
    persistence = (test["last"] - test.y).abs().mean()
    results = {}
    for name, factory in TRAINABLE.items():
        model = factory(4)
        if isinstance(model, LightGBMForecaster):
            model.n_estimators = 150
        predicted = model.fit(train).predict(test)
        assert (predicted.p10 <= predicted.p50).all() and (predicted.p50 <= predicted.p90).all()
        coverage = ((test.y >= predicted.p10) & (test.y <= predicted.p90)).mean()
        assert 0.6 < coverage < 0.97, name
        results[name] = (predicted.p50 - test.y).abs().mean()
        assert results[name] < 0.8 * persistence, name
    assert isinstance(TRAINABLE["linear"](4), LinearForecaster)
    assert isinstance(TRAINABLE["profile"](4), ProfileForecaster)
    assert pinball_loss(test.y, model.predict(test)) > 0
    assert set(MODELS) == {"profile", "linear", "hgb", "lightgbm", "ensemble"}


def test_backtest_units_cache_and_ensemble() -> None:
    history = synthetic_history(92)  # March - May
    units = plan_units(history, ["linear", "profile"], (1, 96), first_test_month=5)
    assert len(units) == 4 and {u.key[2] for u in units} == {"2025-05"}
    results = run_units(history, units, workers=1)
    for unit, frame in results.items():
        assert frame.target.min() >= pd.Timestamp("2025-05-01")
        assert (frame.issue < frame.target).all()
        assert (frame.model == unit.model).all()
    metrics = {(m.model, m.horizon): m for m in horizon_metrics(pd.concat(results.values()))}
    assert metrics[("linear", 1)].skill > 0 and metrics[("profile", 96)].mape < 0.15
    members = [results[u] for u in units if u.horizon == 1]
    blended = ensemble_of(members)
    assert (blended.model == "ensemble").all() and len(blended) == len(members[0])

    connection = duckdb.connect(":memory:")
    ensure_tables(connection)
    print_ = fingerprint(history, "linear")
    assert print_ != fingerprint(history, "profile")
    assert print_ == fingerprint(synthetic_history(92), "linear")
    unit = next(u for u in units if u.model == "linear" and u.horizon == 1)
    store_unit(connection, unit, results[unit].assign(p_exceed=0.0), print_)
    assert cached_units(connection) == {unit.key: print_}
    stored = connection.execute("SELECT COUNT(*) FROM forecasts WHERE model = 'linear'").fetchone()
    assert stored == (len(results[unit]),)
    assert run_unit(history, unit).shape == results[unit].shape


def test_alert_episodes_measure_lead_and_false_alarms() -> None:
    targets = pd.date_range("2025-07-24 12:00", periods=12, freq="15min")
    y = [1300] * 5 + [1450, 1460] + [1300] * 5
    p = [0.0, 0.0, 0.0, 0.6, 0.7, 0.9, 0.9, 0.1, 0.0, 0.0, 0.0, 0.8]
    frame = pd.DataFrame({
        "target": targets, "issue": targets - pd.Timedelta(minutes=15), "horizon": 1,
        "y": y, "p_exceed": p, "model": "lightgbm",
    })
    episodes, false_alarms = alert_episodes(frame, contract_kw=1400, threshold=0.5)
    assert len(episodes) == 1
    assert episodes[0].start == datetime(2025, 7, 24, 13, 15)
    assert episodes[0].lead == pd.Timedelta(minutes=30)
    assert false_alarms == 1  # the isolated alert at 14:45
