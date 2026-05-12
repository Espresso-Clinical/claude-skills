"""
severity_rubric — Assign severity (critical / major / minor) to a SOA KRI.

Generic, protocol-agnostic rubric:
  - critical: primary endpoint procedure, eligibility/consent gate, randomization
              gate, stopping-rule trigger, IP discontinuation rule
  - major:    secondary/key secondary endpoint, biomarker, safety threshold,
              visit-window check-in, most routine procedures
  - minor:    exploratory endpoint, administrative governance, documentation-only
              obligation, optional/per-sponsor-instruction procedure
"""

import re


PRIMARY_ENDPOINT_HINTS = {
    "informed consent", "consent",
    "randomization", "randomisation",
    "eligibility assessment", "inclusion", "exclusion",
    "primary endpoint", "primary efficacy",
    "primary outcome",
}

CRITICAL_PROCEDURES = {
    "informed consent",
    "written informed consent",
    "eligibility assessment",
    "randomization",
    "randomisation",
}

MINOR_PROCEDURES = {
    "exploratory laboratory",
    "exploratory biomarker",
    "optional sample",
    "questionnaire",
    "patient diary",
    "documentation",
    "delegation log",
    "lost to follow-up",
    "remote assessment",
}

MINOR_KEYWORDS = {
    "optional", "exploratory", "documentation",
    "lost to follow-up", "remote assessment",
}


def derive_severity(procedure_name, atomic_unit=None, ontology=None, kri_source=None):
    """Return one of: 'critical', 'major', 'minor'.

    Args:
      procedure_name: the atomic procedure name (e.g., "Blood chemistry")
      atomic_unit: optional dict from soa_atomic_grid.json — uses condition / visit
      ontology: optional ontology.json — uses procedure category if available
      kri_source: 'atomic_grid' | 'checkin' | 'cross_visit' | 'orphan_footnote' | 'soa_text'
    """
    if not procedure_name:
        return "major"
    p = procedure_name.strip().lower()

    # CRITICAL — eligibility/consent gates
    if p in CRITICAL_PROCEDURES:
        return "critical"
    for hint in PRIMARY_ENDPOINT_HINTS:
        if hint in p:
            return "critical"

    # MINOR — exploratory / optional / admin
    if p in MINOR_PROCEDURES:
        return "minor"
    for kw in MINOR_KEYWORDS:
        if kw in p:
            return "minor"

    # Check ontology for procedure category if available
    if ontology:
        for proc in (ontology.get("procedures") or []):
            if proc.get("name", "").lower() == p:
                cat = (proc.get("type") or proc.get("category") or "").lower()
                if cat in {"primary_endpoint", "consent_eligibility"}:
                    return "critical"
                if cat in {"exploratory", "patient_reported", "documentation"}:
                    return "minor"
                break

    # Check-in KRIs default to major
    if kri_source == "checkin":
        return "major"

    # Cross-visit timing rules — major
    if kri_source == "cross_visit":
        return "major"

    # Orphan footnotes — minor by default (they describe edge cases / clarifications)
    if kri_source == "orphan_footnote":
        return "minor"

    # Default: major
    return "major"


def derive_deviation_level(procedure_name, kri_source=None):
    """Most KRIs operate at subject level. Site-level only for cross-site
    methodology rules (rare).
    """
    if kri_source == "soa_text":
        p = (procedure_name or "").lower()
        # Site-level patterns
        if any(kw in p for kw in ["site initiation", "investigator brochure", "irb approval"]):
            return "site"
    return "subject"
