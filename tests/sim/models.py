"""Thermal model factory for the VT native simulation suite.

Loads physics models directly from the heating_simulator integration's
thermal_model.py via importlib — no HA integration machinery is involved.

All four model types expose the same interface:
    model.temperature           -> float  (room air temperature, °C)
    model.external_temperature  -> float  (current external temp, °C)
    model.set_power_fraction(f) -> None   (f in [0.0, 1.0])
    model.step(dt_s)            -> None   (advance physics by dt_s seconds)

Config keys in scenario YAML are identical to heating_simulator.yaml so that
real HA configurations can be copied in directly.  The constructor-param
mapping below corrects the mismatches between the YAML key names and the
actual model __init__ parameter names.

Config key              → Model param
─────────────────────────────────────
r_infiltration          → r_inf
window_area_m2          → window_area
pipe_delay_seconds      → pipe_delay
flow_rate_max_kg_s      → flow_rate_max
heater_power_watts_r2c2 → heater_power_watts   (R2C2 only)
heat_loss_coefficient   → heat_loss_coeff       (simple only)
heat_loss_coefficient_rad → heat_loss_coeff     (radiator only)
c_room_rad              → c_room                (radiator only)
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------

def _load_thermal_model_module() -> ModuleType:
    """Load heating_simulator/thermal_model.py from the symlinked integration."""
    root = Path(__file__).resolve().parents[2]
    model_path = root / "custom_components" / "heating_simulator" / "thermal_model.py"
    if not model_path.exists():
        raise FileNotFoundError(
            f"Missing thermal model module: {model_path}\n"
            "Ensure custom_components/heating_simulator is symlinked."
        )
    spec = spec_from_file_location("_vtsim_thermal_model", model_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module spec for: {model_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def create_model(config: dict[str, Any]) -> Any:
    """Create and return a thermal model instance from a scenario model config.

    Args:
        config: The ``model:`` section of a scenario YAML, as a plain dict.

    Returns:
        A model instance with the standard interface described in the module
        docstring.  The concrete type depends on ``config["model_type"]``.

    Raises:
        ValueError: If ``model_type`` is not one of the four supported values.
        FileNotFoundError: If the heating_simulator symlink is missing.
    """
    tm = _load_thermal_model_module()
    model_type = str(config.get("model_type", "r2c2")).lower()

    initial_temp = float(config.get("initial_temperature", 18.0))
    initial_ext = float(config.get("external_temperature_fixed", 5.0))

    if model_type == "simple":
        return tm.SimpleThermalModel(
            heater_power_watts=float(config.get("heater_power_watts", 1000.0)),
            heat_loss_coeff=float(config.get("heat_loss_coefficient", 30.0)),
            thermal_mass=float(config.get("thermal_mass", 4_000_000.0)),
            thermal_inertia_tau=float(config.get("thermal_inertia", 0.0)),
            initial_temp=initial_temp,
            initial_external_temp=initial_ext,
        )

    if model_type == "r2c2":
        return tm.R2C2ThermalModel(
            heater_power_watts=float(config.get("heater_power_watts_r2c2", 1200.0)),
            c_air=float(config.get("c_air", 1_000_000.0)),
            c_fabric=float(config.get("c_fabric", 7_500_000.0)),
            r_fabric=float(config.get("r_fabric", 0.005)),
            r_ext=float(config.get("r_ext", 0.03)),
            r_inf=float(config.get("r_infiltration", 0.25)),
            window_area=float(config.get("window_area_m2", 0.0)),
            window_transmittance=float(config.get("window_transmittance", 0.6)),
            initial_temp=initial_temp,
            initial_external_temp=initial_ext,
            initial_solar=float(config.get("solar_irradiance_fixed", 0.0)),
        )

    if model_type == "radiator":
        return tm.WetRadiatorModel(
            flow_temperature=float(config.get("flow_temperature", 60.0)),
            c_radiator=float(config.get("c_radiator", 20_000.0)),
            k_radiator=float(config.get("k_radiator", 10.0)),
            radiator_exponent=float(config.get("radiator_exponent", 1.3)),
            flow_rate_max=float(config.get("flow_rate_max_kg_s", 0.05)),
            heat_loss_coeff=float(config.get("heat_loss_coefficient_rad", 50.0)),
            c_room=float(config.get("c_room_rad", 500_000.0)),
            pipe_delay=float(config.get("pipe_delay_seconds", 0.0)),
            valve_characteristic=str(config.get("valve_characteristic", "linear")),
            initial_temp=initial_temp,
            initial_external_temp=initial_ext,
        )

    if model_type == "r2c2_radiator":
        return tm.R2C2RadiatorModel(
            flow_temperature=float(config.get("flow_temperature", 60.0)),
            c_radiator=float(config.get("c_radiator", 20_000.0)),
            k_radiator=float(config.get("k_radiator", 10.0)),
            radiator_exponent=float(config.get("radiator_exponent", 1.3)),
            radiator_convective_fraction=float(
                config.get("radiator_convective_fraction", 0.75)
            ),
            flow_rate_max=float(config.get("flow_rate_max_kg_s", 0.05)),
            pipe_delay=float(config.get("pipe_delay_seconds", 0.0)),
            valve_characteristic=str(config.get("valve_characteristic", "linear")),
            c_air=float(config.get("c_air", 1_000_000.0)),
            c_fabric=float(config.get("c_fabric", 7_500_000.0)),
            r_fabric=float(config.get("r_fabric", 0.005)),
            r_ext=float(config.get("r_ext", 0.03)),
            r_inf=float(config.get("r_infiltration", 0.25)),
            window_area=float(config.get("window_area_m2", 0.0)),
            window_transmittance=float(config.get("window_transmittance", 0.6)),
            initial_temp=initial_temp,
            initial_external_temp=initial_ext,
            initial_solar=float(config.get("solar_irradiance_fixed", 0.0)),
        )

    raise ValueError(
        f"Unsupported model_type: {model_type!r}. "
        "Choose one of: simple, r2c2, radiator, r2c2_radiator"
    )
