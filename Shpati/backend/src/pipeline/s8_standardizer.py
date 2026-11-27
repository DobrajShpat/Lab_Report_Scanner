from __future__ import annotations

from pipeline.models import NormalizedObservation


UNIT_ALIASES = {
    "g%": "g/dL",
    "gms%": "g/dL",
    "cells/cmm": "cells/uL",
    "cells/cumm": "cells/uL",
    "10^3/mm^3": "10^3/uL",
    "mil/cu mm": "10^6/uL",
    "lakhs/cumm": "10^3/uL",
    "lakhs/cmm": "10^3/uL",
}


def standardize_observation(obs: NormalizedObservation) -> NormalizedObservation:
    unit = (obs.original_unit or "").strip().lower()
    canonical = (obs.canonical_name or "").lower()

    if unit in UNIT_ALIASES:
        target = UNIT_ALIASES[unit]
        obs.provenance["original_unit"] = obs.original_unit
        obs.standardized_unit = target
        if obs.standardized_value is not None and unit == "lakhs/cumm" and canonical == "platelet count":
            obs.standardized_value = round(obs.standardized_value * 100.0, 2)
            obs.provenance["conversion_note"] = "Lakhs/Cumm -> 10^3/uL"

    if unit == "g%" and canonical == "hemoglobin" and obs.standardized_value is not None:
        obs.standardized_unit = "g/dL"
        obs.provenance["conversion_note"] = "g% treated as g/dL for hemoglobin"

    return obs


def standardize_all(observations: list[NormalizedObservation]) -> list[NormalizedObservation]:
    return [standardize_observation(obs) for obs in observations]
