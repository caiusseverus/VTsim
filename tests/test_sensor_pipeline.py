"""Tests for the SensorPipeline class."""
import math
import pytest
from sim.sensor_pipeline import SensorPipeline


def test_all_zero_config_passes_through():
    """All-zero config must return true_temp unchanged — backward compatibility."""
    p = SensorPipeline({}, initial_temp=20.0)
    assert p.step(20.0, dt_s=10.0, sim_time_s=10.0) == 20.0
    assert p.step(21.5, dt_s=10.0, sim_time_s=20.0) == 21.5


def test_initial_injection_returns_initial_temp():
    """dt_s=0 (initial injection) must return initial_temp with lag enabled."""
    p = SensorPipeline({"lag_tau": 60.0}, initial_temp=19.9)
    result = p.step(19.9, dt_s=0.0, sim_time_s=0.0)
    assert result == pytest.approx(19.9, abs=0.001)


def test_lag_slows_temperature_response():
    """Stage 1: with lag_tau=60s and dt_s=10s, alpha=10/70≈0.143."""
    p = SensorPipeline({"lag_tau": 60.0}, initial_temp=18.0)
    # True temp jumps to 20 — lagged value moves partially toward it
    result = p.step(20.0, dt_s=10.0, sim_time_s=10.0)
    expected_alpha = 10.0 / 70.0
    expected = 18.0 + expected_alpha * (20.0 - 18.0)
    assert result == pytest.approx(expected, abs=0.001)


def test_lag_accumulates_over_multiple_steps():
    """Stage 1: lag state carries across steps."""
    p = SensorPipeline({"lag_tau": 60.0}, initial_temp=18.0)
    alpha = 10.0 / 70.0
    lagged = 18.0
    for _ in range(5):
        lagged += alpha * (20.0 - lagged)
        result = p.step(20.0, dt_s=10.0, sim_time_s=10.0)
    assert result == pytest.approx(lagged, abs=0.001)


def test_bias_adds_fixed_offset():
    """Stage 2: bias adds a fixed offset to every reading."""
    p = SensorPipeline({"bias": 1.5}, initial_temp=20.0)
    assert p.step(20.0, dt_s=10.0, sim_time_s=10.0) == pytest.approx(21.5, abs=0.001)
    assert p.step(19.0, dt_s=10.0, sim_time_s=20.0) == pytest.approx(20.5, abs=0.001)


def test_noise_has_correct_distribution():
    """Stage 3: noise is Gaussian with correct std dev (statistical test)."""
    p = SensorPipeline({"noise_std_dev": 0.5}, initial_temp=20.0)
    samples = [p.step(20.0, dt_s=10.0, sim_time_s=float(i)) for i in range(1, 1001)]
    mean = sum(samples) / len(samples)
    std = math.sqrt(sum((s - mean) ** 2 for s in samples) / len(samples))
    assert abs(mean - 20.0) < 0.1   # mean should be near 20
    assert abs(std - 0.5) < 0.1     # std dev should be near 0.5


def test_quantisation_rounds_to_step():
    """Stage 4: quantisation rounds to nearest step."""
    p = SensorPipeline({"quantisation": 0.5}, initial_temp=20.0)
    assert p.step(20.24, dt_s=10.0, sim_time_s=10.0) == pytest.approx(20.0, abs=0.001)
    assert p.step(20.26, dt_s=10.0, sim_time_s=20.0) == pytest.approx(20.5, abs=0.001)
    assert p.step(20.75, dt_s=10.0, sim_time_s=30.0) == pytest.approx(21.0, abs=0.001)


def test_rate_limit_suppresses_within_window():
    """Stage 5: same value returned while update_rate_s window has not elapsed."""
    p = SensorPipeline({"update_rate_s": 60.0}, initial_temp=20.0)
    # Within window: suppress, return seeded 20.0
    assert p.step(21.0, dt_s=10.0, sim_time_s=10.0) == pytest.approx(20.0, abs=0.001)
    assert p.step(21.0, dt_s=10.0, sim_time_s=50.0) == pytest.approx(20.0, abs=0.001)
    # Window elapsed: emit new value
    result = p.step(21.0, dt_s=10.0, sim_time_s=60.0)
    assert result == pytest.approx(21.0, abs=0.001)
    # Within next window: suppress again
    assert p.step(22.0, dt_s=10.0, sim_time_s=100.0) == pytest.approx(21.0, abs=0.001)


def test_zigbee_min_interval_suppresses():
    """Stage 6: suppresses reports faster than min_interval_s."""
    p = SensorPipeline({"min_interval_s": 30.0, "delta": 0.0}, initial_temp=20.0)
    # First call at sim_time_s=0: elapsed=0 < 30 → suppress, return seeded 20.0
    assert p.step(21.0, dt_s=10.0, sim_time_s=0.0) == pytest.approx(20.0, abs=0.001)
    # Still suppressed at 20s
    assert p.step(21.0, dt_s=10.0, sim_time_s=20.0) == pytest.approx(20.0, abs=0.001)
    # At 30s: min_interval elapsed, delta=0 so always report → emit 21.0
    result = p.step(21.0, dt_s=10.0, sim_time_s=30.0)
    assert result == pytest.approx(21.0, abs=0.001)


def test_zigbee_delta_suppresses_small_change():
    """Stage 6: suppresses reports below delta threshold."""
    p = SensorPipeline({"delta": 0.5, "min_interval_s": 0.0}, initial_temp=20.0)
    # Change of 0.3 < delta 0.5 → suppress (but min_interval=0 so min_elapsed=True)
    # heartbeat: max_interval=0 so heartbeat_due=False
    # delta_crossed: 0.3 < 0.5 → False → suppress
    assert p.step(20.3, dt_s=10.0, sim_time_s=10.0) == pytest.approx(20.0, abs=0.001)
    # Change of 0.6 >= delta 0.5 → emit
    result = p.step(20.6, dt_s=10.0, sim_time_s=20.0)
    assert result == pytest.approx(20.6, abs=0.001)


def test_zigbee_heartbeat_fires_regardless_of_delta():
    """Stage 6: heartbeat (max_interval) fires even without delta change."""
    p = SensorPipeline(
        {"delta": 0.5, "min_interval_s": 10.0, "max_interval_s": 600.0},
        initial_temp=20.0,
    )
    # Small change — suppress
    assert p.step(20.1, dt_s=10.0, sim_time_s=10.0) == pytest.approx(20.0, abs=0.001)
    # Heartbeat fires at 600s even though change is still small
    result = p.step(20.1, dt_s=10.0, sim_time_s=600.0)
    assert result == pytest.approx(20.1, abs=0.001)


def test_mutual_exclusion_raises():
    """Stages 5 and 6 are mutually exclusive."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        SensorPipeline({"update_rate_s": 60.0, "min_interval_s": 30.0}, initial_temp=20.0)
    with pytest.raises(ValueError, match="mutually exclusive"):
        SensorPipeline({"update_rate_s": 60.0, "delta": 0.1}, initial_temp=20.0)
    with pytest.raises(ValueError, match="mutually exclusive"):
        SensorPipeline({"update_rate_s": 60.0, "max_interval_s": 600.0}, initial_temp=20.0)


def test_empty_sensor_config_is_identity():
    """Empty config (as passed by old scenarios) produces no degradation."""
    p = SensorPipeline({}, initial_temp=20.0)
    for temp in [18.0, 19.5, 20.0, 21.3, 22.0]:
        assert p.step(temp, dt_s=10.0, sim_time_s=10.0) == temp
