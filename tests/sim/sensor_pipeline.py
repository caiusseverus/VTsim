"""Sensor imperfection pipeline for VTsim.

Replicates the TemperatureSensor degradation pipeline from
heating_simulator/sensor.py, adapted to use simulated time instead of
time.monotonic() so rate-limiting works correctly at accelerated speed.

Pipeline stages (applied in order):
    1. Lag          — first-order low-pass filter    (lag_tau, s)
    2. Bias         — fixed additive offset           (bias, °C)
    3. Noise        — Gaussian noise per tick         (noise_std_dev, °C σ)
    4. Quantisation — round to nearest step           (quantisation, °C)
    5. Rate-limit   — suppress if interval not elapsed (update_rate_s, s)
    6. Zigbee       — conditional reporting            (min_interval_s,
                                                        max_interval_s, delta)

Stages 5 and 6 are mutually exclusive. All parameters default to 0 (disabled).
A pipeline with all-zero config returns the true temperature unchanged.

Usage::

    pipeline = SensorPipeline(scenario.get("sensor", {}), model.temperature)

    # Before the simulation loop (dt_s=0 → lag stage skipped, returns initial_temp):
    t0 = pipeline.step(model.temperature, dt_s=0.0, sim_time_s=0.0)

    # Each simulation step:
    sensor_temp = pipeline.step(model.temperature, dt_s, sim_time_s)
"""

from __future__ import annotations

import random
from typing import Any


class SensorPipeline:
    """6-stage sensor imperfection pipeline using simulated time.

    Args:
        config:       The ``sensor:`` section of a scenario YAML.
                      Uses short key names (``lag_tau``, ``bias``, etc.).
                      Missing keys default to 0 (disabled).
        initial_temp: Starting temperature used to seed lag and rate-limit
                      state, preventing cold-start artefacts.
    """

    def __init__(self, config: dict[str, Any], initial_temp: float) -> None:
        cfg = config or {}
        self._lag_tau     = float(cfg.get("lag_tau",        0.0))
        self._bias        = float(cfg.get("bias",           0.0))
        self._noise_std   = float(cfg.get("noise_std_dev",  0.0))
        self._quantise    = float(cfg.get("quantisation",   0.0))
        self._update_rate = float(cfg.get("update_rate_s",  0.0))
        self._min_iv      = float(cfg.get("min_interval_s", 0.0))
        self._max_iv      = float(cfg.get("max_interval_s", 0.0))
        self._delta       = float(cfg.get("delta",          0.0))

        has_rate_limit = self._update_rate > 0.0
        has_zigbee     = self._min_iv > 0.0 or self._max_iv > 0.0 or self._delta > 0.0
        if has_rate_limit and has_zigbee:
            raise ValueError(
                "sensor pipeline: update_rate_s and Zigbee parameters "
                "(min_interval_s, max_interval_s, delta) are mutually exclusive"
            )

        # Stage 1 — lag filter state (seeded to avoid cold-start spike)
        self._lagged_temp: float = initial_temp

        # Stage 5 — rate-limit state (simulated seconds, seeded at t=0)
        self._rate_last_sim_s: float = 0.0
        self._rate_last_value: float = initial_temp

        # Stage 6 — Zigbee state (simulated seconds, seeded at t=0)
        self._zigbee_last_sim_s: float = 0.0
        self._zigbee_last_value: float = initial_temp

    def step(self, true_temp: float, dt_s: float, sim_time_s: float) -> float:
        """Apply the degradation pipeline and return the reported temperature.

        Args:
            true_temp:   Raw model temperature (°C).
            dt_s:        Time elapsed this step (s). Pass 0.0 for the
                         initial pre-loop injection.
            sim_time_s:  Simulated elapsed seconds since simulation start.
                         Used for rate-limiting stages 5 and 6.

        Returns:
            Degraded temperature (°C), rounded to 3 decimal places.
        """
        # ------------------------------------------------------------------
        # Stage 1 — Sensor lag: α = dt / (τ + dt)
        # When dt_s=0 (initial injection): α=0 so _lagged_temp is unchanged,
        # returning the pre-seeded initial_temp exactly.
        # When lag_tau=0: no lag, pass through directly.
        # ------------------------------------------------------------------
        if self._lag_tau > 0.0:
            alpha = dt_s / (self._lag_tau + dt_s)
            self._lagged_temp += alpha * (true_temp - self._lagged_temp)
            value = self._lagged_temp
        else:
            self._lagged_temp = true_temp
            value = true_temp

        # ------------------------------------------------------------------
        # Stage 2 — Bias: fixed calibration offset
        # ------------------------------------------------------------------
        value += self._bias

        # ------------------------------------------------------------------
        # Stage 3 — Noise: Gaussian, σ = noise_std_dev
        # ------------------------------------------------------------------
        if self._noise_std > 0.0:
            value += random.gauss(0.0, self._noise_std)

        # ------------------------------------------------------------------
        # Stage 4 — Quantisation: round to nearest step
        # ------------------------------------------------------------------
        if self._quantise > 0.0:
            value = round(value / self._quantise) * self._quantise

        # ------------------------------------------------------------------
        # Stage 5 — Rate-limit: suppress if interval not elapsed
        # ------------------------------------------------------------------
        if self._update_rate > 0.0:
            if (sim_time_s - self._rate_last_sim_s) < self._update_rate:
                return round(self._rate_last_value, 3)
            self._rate_last_sim_s = sim_time_s
            self._rate_last_value = value

        # ------------------------------------------------------------------
        # Stage 6 — Zigbee-style conditional reporting
        # Logic: heartbeat_due → always emit
        #        min_elapsed AND delta_crossed → emit
        #        otherwise → suppress
        # ------------------------------------------------------------------
        if self._min_iv > 0.0 or self._max_iv > 0.0 or self._delta > 0.0:
            elapsed      = sim_time_s - self._zigbee_last_sim_s
            change       = abs(value - self._zigbee_last_value)
            heartbeat_due = (self._max_iv > 0.0) and (elapsed >= self._max_iv)
            min_elapsed   = (self._min_iv <= 0.0) or (elapsed >= self._min_iv)
            delta_crossed = (self._delta <= 0.0) or (change >= self._delta)

            if heartbeat_due or (min_elapsed and delta_crossed):
                self._zigbee_last_sim_s = sim_time_s
                self._zigbee_last_value = value
            else:
                return round(self._zigbee_last_value, 3)

        return round(value, 3)
