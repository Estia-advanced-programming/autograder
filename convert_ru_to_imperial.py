#!/usr/bin/env python3
"""Convert RU unit test YML files from metric to imperial units.

Reads all test/tests/unit/RU_*.yml files and overwrites them in-place
with feature/metadata values converted from SI metric to imperial.

Conversion constants (from docs/Pandora/Constants.md):
  Speed:       m/s  × (3.6 / 1.609) → mph
  Altitude:    m    × 3.281          → ft
  Distance(m): m    / 1609           → miles
  Distance(km):km   / 1.609          → miles
  Power:       W    / 754.7          → hp
  Accel:       m/s² × 3.281          → ft/s²
  Temp delta:  ℃    × 9/5            → °F (delta, no offset — used for noiseTemp)
  Mass:        kg   × 2.205          → lbs

Run from the workspace root:
    python convert_ru_to_imperial.py
"""

import re
import glob
import sys

# ── Conversion constants ──────────────────────────────────────────────────────
M_TO_FT = 3.281
MS_TO_MPH = 3.6 / 1.609  # ≈ 2.23741
W_TO_HP = 1 / 754.7
MS2_TO_FTS2 = 3.281
KM_TO_MILES = 1 / 1.609
M_TO_MILES = 1 / 1609.0
KG_TO_LBS = 2.205
CELSIUS_DELTA = 9 / 5  # delta only — no +32 offset (noiseTemp is noise)

# Regex fragment matching a signed decimal number
NUM = r"-?\d+(?:\.\d+)?"


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def replace_simple(text: str, key: str, factor: float) -> str:
    """Convert a plain  'key: value'  line."""
    pattern = rf"^(\s*{re.escape(key)}:\s*)({NUM})(\s*)$"

    def sub(m: re.Match) -> str:
        return f"{m.group(1)}{_fmt(float(m.group(2)) * factor)}{m.group(3)}"

    return re.sub(pattern, sub, text, flags=re.MULTILINE)


def replace_alt_speed(text: str, key: str) -> str:
    """Convert  'key: "alt_m: speed_ms"'  →  'key: "alt_ft: speed_mph"'"""
    pattern = rf'^(\s*{re.escape(key)}:\s*")({NUM}):\s*({NUM})(")(\s*)$'

    def sub(m: re.Match) -> str:
        alt = _fmt(float(m.group(2)) * M_TO_FT)
        speed = _fmt(float(m.group(3)) * MS_TO_MPH)
        return f"{m.group(1)}{alt}: {speed}{m.group(4)}{m.group(5)}"

    return re.sub(pattern, sub, text, flags=re.MULTILINE)


def replace_reach_alt(text: str) -> str:
    """Convert  'reachAlt: "min / alt_m"'  →  'reachAlt: "min / alt_ft"'"""
    pattern = rf'^(\s*reachAlt:\s*")({NUM}) / ({NUM})(")(\s*)$'

    def sub(m: re.Match) -> str:
        alt_ft = _fmt(float(m.group(3)) * M_TO_FT)
        return f"{m.group(1)}{m.group(2)} / {alt_ft}{m.group(4)}{m.group(5)}"

    return re.sub(pattern, sub, text, flags=re.MULTILINE)


def replace_reach_dist(text: str) -> str:
    """Convert  'reachDist: "min / dist_m"'  →  'reachDist: "min / dist_miles"'"""
    pattern = rf'^(\s*reachDist:\s*")({NUM}) / ({NUM})(")(\s*)$'

    def sub(m: re.Match) -> str:
        miles = _fmt(float(m.group(3)) * M_TO_MILES)
        return f"{m.group(1)}{m.group(2)} / {miles}{m.group(4)}{m.group(5)}"

    return re.sub(pattern, sub, text, flags=re.MULTILINE)


def replace_phase_value(text: str, key: str, factor: float) -> str:
    """Convert  'key: "PhaseName:value"'  —  numeric part only."""
    pattern = rf'^(\s*{re.escape(key)}:\s*"[^:"]+:)({NUM})(")(\s*)$'

    def sub(m: re.Match) -> str:
        return f"{m.group(1)}{_fmt(float(m.group(2)) * factor)}{m.group(3)}{m.group(4)}"

    return re.sub(pattern, sub, text, flags=re.MULTILINE)


def convert_file(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        text = f.read()

    # ── Speed: m/s → mph ────────────────────────────────────────────────────
    for key in [
        "avgAirSpeedCruise",
        "avgAirSpeedLanding",
        "avgAirSpeedTakeOff",
        "maxAirSpeedCruise",
        "maxAirSpeedLanding",
        "maxAirSpeedTakeOff",
        "windSpeedCruise",
        "windSpeedLanding",
        "windSpeedTakeOff",
    ]:
        text = replace_simple(text, key, MS_TO_MPH)

    # ── Acceleration: m/s² → ft/s² ──────────────────────────────────────────
    for key in [
        "avgAccelerationCruise",
        "avgAccelerationLanding",
        "avgAccelerationTakeOff",
        "maxAccelerationCruise",
        "maxAccelerationLanding",
        "maxAccelerationTakeOff",
    ]:
        text = replace_simple(text, key, MS2_TO_FTS2)

    # ── Engine power: W → hp ────────────────────────────────────────────────
    for key in [
        "avgEnginePowerCruise",
        "avgEnginePowerLanding",
        "maxEnginePowerCruise",
        "maxEnginePowerLanding",
    ]:
        text = replace_simple(text, key, W_TO_HP)

    # ── Flight distance (phase variants): km → miles ────────────────────────
    for key in [
        "flightDistanceCruise",
        "flightDistanceLanding",
        "flightDistanceTakeOff",
    ]:
        text = replace_simple(text, key, KM_TO_MILES)

    # ── Composite "alt_m: speed_ms" → "alt_ft: speed_mph" ───────────────────
    for key in ["fastJetAlt", "fastWindAlt"]:
        text = replace_alt_speed(text, key)

    # ── reachAlt: "min / alt_m" → "min / alt_ft" ────────────────────────────
    text = replace_reach_alt(text)

    # ── reachDist: "min / dist_m" → "min / dist_miles" ──────────────────────
    text = replace_reach_dist(text)

    # ── mostAccelPhase / mostPowerPhase composite values ────────────────────
    text = replace_phase_value(text, "mostAccelPhase", MS2_TO_FTS2)
    text = replace_phase_value(text, "mostPowerPhase", W_TO_HP)
    # mostStressPhase: bpm — unchanged

    # ── noiseTemp: ℃ delta → °F delta (×9/5, no +32 offset) ────────────────
    text = replace_simple(text, "noiseTemp", CELSIUS_DELTA)

    # ── Metadata mass: kg → lbs ─────────────────────────────────────────────
    for key in ["mass_aircraft", "mass_fuel"]:
        text = replace_simple(text, key, KG_TO_LBS)

    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"  converted: {path}")


def main() -> None:
    files = sorted(glob.glob("test/tests/unit/RU_*.yml"))
    if not files:
        print("No files found matching test/tests/unit/RU_*.yml", file=sys.stderr)
        sys.exit(1)
    print(f"Converting {len(files)} file(s)...")
    for path in files:
        convert_file(path)
    print("Done.")


if __name__ == "__main__":
    main()
