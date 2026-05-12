# KRI Examples by Category

Annotated examples showing correct vs incorrect extraction.
Use these as calibration when generating or reviewing KRIs.

---

## ELIG — Eligibility

### Correct: uses "Verify the absence of" phrasing, exact threshold

```json
{
  "kri_id": "ELIG-EXC-015",
  "kri_name": "EXC15 - Laboratory abnormality thresholds",
  "rule_for_llm": "Verify that screening laboratory values do not cross any of the following thresholds: Hb < 8.5 g/dL, WBC < 3.5×10⁹/L or > 15×10⁹/L, Platelets < 100×10⁹/L, Creatinine > 2.0 mg/dL, Bilirubin > 2.0 mg/dL, AST or ALT > 3× ULN, INR > 1.2.",
  "protocol_reference": "Section 8.2, Page 50: \"Hb <8.5 g/DL, WBC <3.5×10⁹/L or >15×10⁹/L, platelets <100×10⁹/L, creatinine >2.0 Mg/DL, bilirubin >2.0 Mg/DL, AST and or ALT >3× ULN, INR >1.2.\""
}
```

---

## SAF — Safety & Toxicity

### Correct: names exact drugs and doses

```json
{
  "kri_id": "SAF-ALLERGY-002",
  "kri_name": "Severe allergic reaction management",
  "rule_for_llm": "Verify that any severe allergic reaction resulted in: (1) immediate injection discontinuation, (2) IV normal saline infusion, (3) epinephrine 0.2–1 mg IV, (4) diphenhydramine 50 mg IV, (5) methylprednisolone 100 mg IV administered, and (6) permanent discontinuation of study treatment.",
  "protocol_reference": "Section 9.5, Page 54: \"For severe events: Immediately discontinue injection... epinephrine 0.2–1 mg IV, diphenhydramine 50 mg IV, methylprednisolone 100 mg IV.\""
}
```

### Incorrect: generic

```json
{
  "rule_for_llm": "Verify that severe allergic reactions were managed appropriately and treatment was discontinued."
}
```
Problem: "appropriately" is not verifiable. Missing the specific drugs, doses, and routes.

---

## END — Endpoints & Statistics

### Correct: exact analysis set definition from protocol

```json
{
  "kri_id": "END-ASET-001",
  "kri_name": "END43 - ITT population definition",
  "rule_for_llm": "Verify that the Intention to Treat (ITT) population is defined as ALL randomized participants, regardless of treatment adherence.",
  "protocol_reference": "Section 15.3, Page 76: \"Intention to Treat (ITT): All randomized participants.\""
}
```

### Incorrect: conflates ITT with mITT

```json
{
  "rule_for_llm": "Verify that the ITT population includes all participants who received at least one dose."
}
```
Problem: That is the mITT definition. ITT = all randomized, per the protocol.

---

## OPS — Operations & Compliance

### Correct: exact temperature range

```json
{
  "kri_id": "OPS-IMP-001",
  "kri_name": "IMP storage temperature",
  "rule_for_llm": "Verify that IMP storage logs document temperature conditions of ≤ -150°C for long-term storage (or ≤ -80°C for short-term storage) in a secure, access-controlled area.",
  "protocol_reference": "Section 9.3, Page 53: \"IMP will be stored according to the labeled conditions (≤ -150°C or -80°C short-term) in a secure, access-controlled area.\""
}
```
