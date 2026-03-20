# Validation: VTsim vs Real HA

This directory contains tools to confirm that VTsim produces equivalent
VTherm algorithmic behaviour to a real HA + heating_simulator environment.

## Exporting data from HA

Export entity history via the HA REST API:

```
GET /api/history/period/<start>?filter_entity_id=climate.sim_simple_pwm&end_time=<end>
```

The response is a JSON array (wrapped in an outer array by HA). Save it to
`tests/validation/ha_exports/<name>.json` after unwrapping the inner array.

**Verify SmartPI attribute names** before exporting a long run: in HA
Developer Tools → States, find your climate entity and confirm that
`specific_states.smart_pi.a` and `.b` are present. If the attribute
names differ from those in `ha_parser.py`, update the parser.

## Running the comparison

1. Run VTsim for the matching scenario (if not already done):
```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q \
    "tests/test_vt_scenarios.py::test_vt_scenario[validation_sim_simple_pwm]" -s
```

2. Run the comparison:
```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python tests/validation/compare.py \
    tests/validation/ha_exports/your_export.json \
    validation_sim_simple_pwm
```

Output PNG: `results/validation/validation_sim_simple_pwm_vs_ha.png`

## Interpreting results

The validation is successful when:
1. Temperature trajectory shapes are visually similar after initial transient
2. SmartPI a/b converge to within ±10% of real HA settled values
3. Duty cycle structure is visually similar
4. No systematic divergence over the run duration

The 9-minute sample export at `ha_exports/history_climate.sim_simple_pwm_*.json`
is for tooling verification only. A 24h cold-start export is needed for a/b
convergence comparison.
