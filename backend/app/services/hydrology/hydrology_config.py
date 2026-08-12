"""
hydrology_config.py — AquaDetect Hydrology Thresholds & Configuration
======================================================================

ALL classification thresholds and documented scientific defaults live here.
No threshold values are scattered elsewhere in the codebase.

References:
- Sentinel-1 SAR flood detection: Bauer-Marschallinger et al. (2022),
  Twele et al. (2016), Markert et al. (2020)
- JRC Global Surface Water: Pekel et al. (2016), Nature 540, 418-422
- CHIRPS: Funk et al. (2015), Scientific Data 2, 150066
- Drought indices: WMO Handbook of Drought Indicators and Indices
"""

# ===========================================================
# SENTINEL-1 SAR PARAMETERS
# ===========================================================

# Absolute VV backscatter threshold for water-like classification.
# Open water typically < -16 dB in C-band VV.
# References: Twele et al. (2016), Schlaffer et al. (2015).
# Default: -16.0 dB  — conservative; avoids misclassifying moist soil.
FLOOD_SAR_THRESHOLD_DB: float = -16.0

# Minimum connected pixel count to retain a flood candidate cluster.
# At 10 m resolution, 20 pixels ≈ 0.002 km² (2,000 m²) minimum patch.
FLOOD_MIN_CONNECTED_PIXELS: int = 20

# Maximum acceptable temporal gap between before/after SAR scenes (days).
# Gaps > 120 days increase baseline drift risk.
FLOOD_MAX_TEMPORAL_GAP_DAYS: int = 120

# VV backscatter CHANGE threshold (dB) used as supporting evidence.
# A negative change (after < before) suggests inundation.
# Used only as supporting evidence, not primary detection.
FLOOD_VV_CHANGE_EVIDENCE_DB: float = -3.0

# JRC permanent water occurrence threshold (%).
# Pixels with occurrence >= 75% are treated as permanent water.
PERMANENT_WATER_OCCURRENCE_THRESHOLD: int = 75

# Sentinel-1 product and mode filter values
S1_INSTRUMENT_MODE: str = "IW"
S1_PRODUCT_TYPE: str = "GRD"
S1_POLARIZATION: str = "VV"

# Maximum number of scenes to inspect when selecting best pair
S1_MAX_SCENES_TO_INSPECT: int = 30

# ===========================================================
# FLOOD INDICATOR THRESHOLDS
# ===========================================================

# Flood indicator is determined by two independent evidence pillars:
#   1. SAR-derived new water area expansion
#   2. CHIRPS rainfall anomaly

# Pillar 1 — new water expansion relative to permanent water baseline
FLOOD_EXPANSION_HIGH_PERCENT: float = 15.0   # >= 15% → strong SAR evidence
FLOOD_EXPANSION_MODERATE_PERCENT: float = 3.0  # >= 3% → moderate SAR evidence

# Absolute new flood area thresholds (km²)
FLOOD_AREA_HIGH_KM2: float = 0.5    # >= 0.5 km² new water → HIGH (if expansion also qualifies)
FLOOD_AREA_MODERATE_KM2: float = 0.05  # >= 0.05 km² → MODERATE

# Pillar 2 — CHIRPS rainfall anomaly (% relative to historical baseline)
FLOOD_RAINFALL_ANOMALY_HIGH_PERCENT: float = 80.0    # >= +80% anomaly → strong rainfall evidence
FLOOD_RAINFALL_ANOMALY_MODERATE_PERCENT: float = 30.0  # >= +30% → moderate evidence

# Combined indicator rules:
#   HIGH      = (SAR expansion HIGH) AND (rainfall anomaly >= MODERATE  OR unavailable)
#             OR (SAR expansion MODERATE) AND (rainfall anomaly HIGH)
#   MODERATE  = (SAR expansion MODERATE) OR (rainfall anomaly MODERATE and some SAR evidence)
#   LOW       = weak evidence in at least one pillar, other is neutral
#   INSUFFICIENT_DATA = insufficient SAR or coverage

# ===========================================================
# DATA QUALITY THRESHOLDS
# ===========================================================

# AOI coverage by valid SAR pixels (%)
QUALITY_HIGH_COVERAGE: float = 80.0   # >= 80% → HIGH
QUALITY_MEDIUM_COVERAGE: float = 50.0  # >= 50% → MEDIUM
# < 50% → LOW

# Acceptable number of scenes found for each window
QUALITY_MIN_SCENES_ACCEPTABLE: int = 1   # at least 1 before + 1 after required

# ===========================================================
# DROUGHT INDICATOR THRESHOLDS
# ===========================================================

# Water area anomaly thresholds (%, relative to historical baseline)
DROUGHT_WATER_ANOMALY_MODERATE: float = -20.0   # <= -20% → MODERATE
DROUGHT_WATER_ANOMALY_HIGH: float = -35.0       # <= -35% → HIGH
DROUGHT_WATER_ANOMALY_CRITICAL: float = -50.0   # <= -50% → CRITICAL

# NDWI anomaly (absolute units, e.g. -0.05)
DROUGHT_NDWI_ANOMALY_MODERATE: float = -0.05
DROUGHT_NDWI_ANOMALY_HIGH: float = -0.10

# NDVI anomaly (%, relative)
DROUGHT_NDVI_ANOMALY_MODERATE: float = -10.0   # <= -10%
DROUGHT_NDVI_ANOMALY_HIGH: float = -20.0       # <= -20%

# Rainfall anomaly (%, 30-day CHIRPS)
DROUGHT_RAINFALL_ANOMALY_MODERATE: float = -20.0
DROUGHT_RAINFALL_ANOMALY_HIGH: float = -35.0

# Minimum number of evidence pillars needed for HIGH/MODERATE classification
DROUGHT_MIN_PILLARS_FOR_HIGH: int = 3    # at least 3 pillars must qualify HIGH
DROUGHT_MIN_PILLARS_FOR_MODERATE: int = 2  # at least 2 for MODERATE

# Historical baseline: number of same-season years to average
DROUGHT_HISTORICAL_YEARS_BACK: int = 5

# ===========================================================
# CHIRPS CONFIGURATION
# ===========================================================

# CHIRPS GEE collection ID
CHIRPS_COLLECTION: str = "UCSB-CHG/CHIRPS/DAILY"

# Number of historical years to use for rainfall baseline
CHIRPS_BASELINE_YEARS: int = 5

# Maximum acceptable data gap for rainfall (days)
CHIRPS_MAX_GAP_DAYS: int = 30

# ===========================================================
# SEASON DEFINITIONS
# (mirrored from change_detection.py for consistency)
# ===========================================================

SEASON_DATE_RANGES = {
    "jun_aug": ("-06-01", "-08-31", "Jun–Aug (SW Monsoon)"),
    "sep_nov": ("-09-01", "-11-30", "Sep–Nov (NE Monsoon)"),
    "dec_feb": ("-12-01", "-02-28", "Dec–Feb (Winter)"),
    "mar_may": ("-03-01", "-05-31", "Mar–May (Summer)"),
    "full_year": ("-01-01", "-12-31", "Full Year"),
}
