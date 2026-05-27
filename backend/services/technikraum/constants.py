from __future__ import annotations

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BACKEND_DIR / "study_data" / "vdi2050"

DIAGRAM_FILES = {
    "v1": "diagramm_v1_digitized_points.csv",
    "v2": "diagramm_v2_digitized_points.csv",
    "v3": "diagramm_v3_digitized_points.csv",
    "e1": "diagramm_e1_digitized_points.csv",
    "e2": "diagramm_e2_digitized_points.csv",
    "e3": "diagramm_e3_digitized_points.csv",
    "e4": "diagramm_e4_digitized_points.csv",
    "k1": "diagramm_k1_digitized_points.csv",
    "k2": "diagramm_k2_digitized_points.csv",
}

USE_FAMILY_LABELS = {
    "administration": "Verwaltung / Büro",
    "retail": "Einzelhandel / Verkaufsstätte",
    "kitchen": "Küche / Gastro",
}

STUDY_BUILDING_TYPE_RULES = {
    13: {
        "code": "2.1",
        "study_label": "Wohnhaus",
        "use_family_key": "administration",
        "use_family_label": "Wohnhaus -> Verwaltung / Büro (analog)",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": True,
    },
    14: {
        "code": "2.2",
        "study_label": "Verkaufsstätte",
        "use_family_key": "retail",
        "use_family_label": "Verkaufsstätte -> Einzelhandel / Verkaufsstätte",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": False,
    },
    15: {
        "code": "2.3",
        "study_label": "Discounter",
        "use_family_key": "retail",
        "use_family_label": "Discounter -> Einzelhandel / Verkaufsstätte",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": False,
    },
    16: {
        "code": "2.4",
        "study_label": "Büro und Verwaltung",
        "use_family_key": "administration",
        "use_family_label": "Büro und Verwaltung -> Verwaltung / Büro",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": False,
    },
    17: {
        "code": "2.5",
        "study_label": "Versammlungsstätte",
        "use_family_key": "administration",
        "use_family_label": "Versammlungsstätte -> Verwaltung / Büro (analog)",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": True,
    },
    18: {
        "code": "2.6",
        "study_label": "Kino",
        "use_family_key": "administration",
        "use_family_label": "Kino -> Verwaltung / Büro (analog)",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": True,
    },
    19: {
        "code": "2.7",
        "study_label": "Beherbergungsstätte",
        "use_family_key": "administration",
        "use_family_label": "Beherbergungsstätte -> Verwaltung / Büro (analog)",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": True,
    },
    20: {
        "code": "2.8",
        "study_label": "Krankenhaus",
        "use_family_key": "administration",
        "use_family_label": "Krankenhaus -> Verwaltung / Büro (analog)",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": True,
    },
    21: {
        "code": "2.9",
        "study_label": "Pflegeheim",
        "use_family_key": "administration",
        "use_family_label": "Pflegeheim -> Verwaltung / Büro (analog)",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": True,
    },
    22: {
        "code": "2.10",
        "study_label": "Schule",
        "use_family_key": "administration",
        "use_family_label": "Schule -> Verwaltung / Büro (analog)",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": True,
    },
    23: {
        "code": "2.11",
        "study_label": "Hochhaus",
        "use_family_key": "administration",
        "use_family_label": "Hochhaus -> Verwaltung / Büro (analog)",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": True,
    },
    24: {
        "code": "2.12",
        "study_label": "Industrie",
        "use_family_key": "administration",
        "use_family_label": "Industrie -> Verwaltung / Büro (analog)",
        "source": "Studie Kriterium 2 Gebäudetyp",
        "is_analog": True,
    },
}

FALLBACK_USE_FAMILY_TOKENS = {
    "administration": [
        "office",
        "büro",
        "buero",
        "verwaltung",
        "admin",
        "meeting",
        "besprechung",
        "konferenz",
        "schule",
        "school",
        "classroom",
        "seminar",
        "hotel",
        "hospital",
        "pflege",
        "ward",
        "wohn",
        "apartment",
        "residential",
    ],
    "retail": [
        "retail",
        "verkauf",
        "verkaufs",
        "laden",
        "shop",
        "mall",
        "market",
        "markt",
        "discounter",
        "showroom",
        "kasse",
    ],
    "kitchen": [
        "kitchen",
        "küche",
        "kueche",
        "restaurant",
        "mensa",
        "canteen",
        "cafeteria",
        "gastro",
        "spül",
        "spuel",
        "scullery",
        "catering",
    ],
}

DISCIPLINE_LABELS = {
    "sanitary": "Sanitär",
    "heating": "Heizung",
    "ventilation": "Lüftung / RLT",
    "cooling": "Kälte / Kühlung",
    "sprinkler": "Sprinkler / Feuerlöschtechnik",
    "unknown": "Nicht erkannt",
}

ADMIN_SCENARIOS = [
    {
        "key": "v1",
        "label": "V1 Verwaltung ohne RLT",
        "diagram_key": "v1",
        "lower": "HSE_ohne_RLT_lower_m2",
        "upper": "HSE_ohne_RLT_upper_m2",
    },
    {
        "key": "v2",
        "label": "V2 Verwaltung mit RLT 6 m³/(h·m²)",
        "diagram_key": "v2",
        "lower": "V2_lower_m2",
        "upper": "V2_upper_m2",
    },
    {
        "key": "v3",
        "label": "V3 Verwaltung mit RLT 9 m³/(h·m²)",
        "diagram_key": "v3",
        "lower": "V3_lower_m2",
        "upper": "V3_upper_m2",
    },
]

RETAIL_SCENARIOS = [
    {
        "key": "e1",
        "label": "E1 Einzelhandel ohne RLT",
        "diagram_key": "e1",
        "lower": "E1_lower_m2",
        "upper": "E1_upper_m2",
    },
    {
        "key": "e2",
        "label": "E2 Einzelhandel mit RLT 12 m³/(h·m²)",
        "diagram_key": "e2",
        "lower": "e2_lower_m2",
        "upper": "e2_upper_m2",
    },
    {
        "key": "e3",
        "label": "E3 Einzelhandel mit RLT 18 m³/(h·m²)",
        "diagram_key": "e3",
        "lower": "E3_lower_m2",
        "upper": "E3_upper_m2",
    },
    {
        "key": "e4",
        "label": "E4 Einzelhandel mit RLT 24 m³/(h·m²)",
        "diagram_key": "e4",
        "lower": "E4_lower_m2",
        "upper": "E4_upper_m2",
    },
]

KITCHEN_SCENARIOS = [
    {
        "key": "k1",
        "label": "K1 Küche mit RLT 90 m³/(h·m²)",
        "diagram_key": "k1",
        "lower": "K1_lower_m2",
        "upper": "K1_upper_m2",
    },
    {
        "key": "k2",
        "label": "K2 Küche mit RLT 120 m³/(h·m²)",
        "diagram_key": "k2",
        "lower": "K2_lower_m2",
        "upper": "K2_upper_m2",
    },
]
