"""
bundle_component_table — Recognized standardized clinical bundles and their components.

Used by:
  - atomic_normalizer.py decompose_procedure_label() — to KEEP recognized bundles whole
  - soa_generator.py — to inject component lists into rule_for_llm CHECK and DEVIATION

This is a generic, protocol-agnostic table covering the most common clinical bundles
seen in Phase 2/3 trials. Sponsors occasionally name a bundle slightly differently
(e.g., "Vital signs including weight"); the matcher uses substring + canonical-name
mapping so close variants still resolve.
"""

# Canonical bundle → component list (used in rule_for_llm)
BUNDLES = {
    "Vital signs": [
        "blood pressure (systolic and diastolic)",
        "heart rate",
        "body temperature",
    ],
    "Vital signs including weight": [
        "blood pressure (systolic and diastolic)",
        "heart rate",
        "body temperature",
        "weight (kg)",
    ],
    "Complete blood count": [
        "red blood cell (RBC) count",
        "hemoglobin (HGB)",
        "hematocrit (HCT)",
        "white blood cell (WBC) count with differential",
        "platelet count",
    ],
    "CBC": [
        "red blood cell (RBC) count",
        "hemoglobin (HGB)",
        "hematocrit (HCT)",
        "white blood cell (WBC) count with differential",
        "platelet count",
    ],
    "Basic metabolic panel": [
        "sodium", "potassium", "chloride", "bicarbonate",
        "blood urea nitrogen (BUN)", "creatinine", "glucose", "calcium",
    ],
    "BMP": [
        "sodium", "potassium", "chloride", "bicarbonate",
        "blood urea nitrogen (BUN)", "creatinine", "glucose", "calcium",
    ],
    "Comprehensive metabolic panel": [
        "sodium", "potassium", "chloride", "bicarbonate",
        "blood urea nitrogen (BUN)", "creatinine", "glucose", "calcium",
        "aspartate aminotransferase (AST)", "alanine aminotransferase (ALT)",
        "alkaline phosphatase (ALP)", "total bilirubin",
        "total protein", "albumin",
    ],
    "CMP": [
        "sodium", "potassium", "chloride", "bicarbonate",
        "blood urea nitrogen (BUN)", "creatinine", "glucose", "calcium",
        "aspartate aminotransferase (AST)", "alanine aminotransferase (ALT)",
        "alkaline phosphatase (ALP)", "total bilirubin",
        "total protein", "albumin",
    ],
    "Liver function tests": [
        "aspartate aminotransferase (AST)", "alanine aminotransferase (ALT)",
        "alkaline phosphatase (ALP)", "gamma-glutamyl transferase (GGT)",
        "total bilirubin", "direct bilirubin", "albumin",
    ],
    "LFTs": [
        "aspartate aminotransferase (AST)", "alanine aminotransferase (ALT)",
        "alkaline phosphatase (ALP)", "gamma-glutamyl transferase (GGT)",
        "total bilirubin", "direct bilirubin", "albumin",
    ],
    "Renal function tests": [
        "blood urea nitrogen (BUN)", "creatinine", "estimated glomerular filtration rate (eGFR)",
    ],
    "RFTs": [
        "blood urea nitrogen (BUN)", "creatinine", "estimated glomerular filtration rate (eGFR)",
    ],
    "Lipid panel": [
        "total cholesterol", "LDL cholesterol", "HDL cholesterol", "triglycerides",
    ],
    "Lipid profile": [
        "total cholesterol", "LDL cholesterol", "HDL cholesterol", "triglycerides",
    ],
    "12-lead ECG": [
        "12-lead electrocardiogram tracing",
        "heart rate from ECG", "PR interval", "QRS duration", "QT interval", "QTc",
    ],
    "ECG": [
        "12-lead electrocardiogram tracing",
        "heart rate from ECG", "PR interval", "QRS duration", "QT interval", "QTc",
    ],
    "Electrocardiogram": [
        "12-lead electrocardiogram tracing",
        "heart rate from ECG", "PR interval", "QRS duration", "QT interval", "QTc",
    ],
    "Coagulation panel": [
        "prothrombin time (PT)", "international normalized ratio (INR)",
        "activated partial thromboplastin time (aPTT)",
    ],
    "Urinalysis": [
        "color and appearance", "specific gravity", "pH",
        "protein", "glucose", "ketones", "blood", "bilirubin",
        "nitrites", "leukocyte esterase", "microscopic exam",
    ],
    "Physical examination": [
        "general appearance",
        "head/eyes/ears/nose/throat (HEENT)",
        "cardiovascular", "respiratory", "abdomen",
        "neurological", "musculoskeletal", "skin",
    ],
    "Full physical examination": [
        "general appearance",
        "head/eyes/ears/nose/throat (HEENT)",
        "cardiovascular", "respiratory", "abdomen",
        "neurological", "musculoskeletal", "skin",
    ],
    "Physical exam": [
        "general appearance",
        "head/eyes/ears/nose/throat (HEENT)",
        "cardiovascular", "respiratory", "abdomen",
        "neurological", "musculoskeletal", "skin",
    ],
}

_BUNDLE_LOOKUP = {k.lower(): k for k in BUNDLES}


def get_bundle_components(procedure_name):
    """Return component list for a recognized bundle, or None if not a bundle.

    Matches case-insensitively, after stripping trailing parentheticals.
    Returns (canonical_name, [components]) or (None, None).
    """
    if not procedure_name:
        return None, None
    name = procedure_name.strip()
    # Try direct lookup
    canonical = _BUNDLE_LOOKUP.get(name.lower())
    if canonical:
        return canonical, list(BUNDLES[canonical])
    # Strip trailing parenthetical and retry
    import re
    base = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    canonical = _BUNDLE_LOOKUP.get(base.lower())
    if canonical:
        return canonical, list(BUNDLES[canonical])
    return None, None


def is_recognized_bundle(procedure_name):
    """Whether the procedure name is a recognized standardized bundle."""
    canonical, _ = get_bundle_components(procedure_name)
    return canonical is not None
