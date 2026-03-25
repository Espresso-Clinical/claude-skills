# KRI Examples by Category

Annotated examples showing correct vs incorrect extraction.
Use these as calibration when generating or reviewing KRIs.

---

## SOA — Schedule of Activities

### Correct: specific, includes data source and exact values

```json
{
  "kri_id": "SOA-V4-075",
  "kri_name": "V4- Analgesics washout",
  "description": "Confirms required analgesic washout before pain assessments at Month 3.",
  "category_id": "SOA",
  "category_label": "Schedule of Activities",
  "rule_for_llm": "V4- Verify by checking medication logs and visit timestamps that the participant maintained at least a 48-hour washout from short-acting analgesics, or at least 5 half-lives for long-acting analgesics, prior to completing questionnaires.",
  "protocol_reference": "Section 11.2, Page 58: \"Short-acting analgesics: ≥48 hours. Long-acting agents: ≥5 half-lives.\"",
  "additional_footnotes": null
}
```

### Incorrect: missing data source, vague

```json
{
  "rule_for_llm": "V4- Verify that a washout was observed before pain assessments."
}
```
Problem: Missing "by checking medication logs", missing exact duration, missing long-acting rule.

---

### Correct: labs include all analytes

```json
{
  "kri_id": "SOA-V4-071",
  "kri_name": "V4- Safety laboratory assessment",
  "rule_for_llm": "V4- Verify that CBC with differential and biochemistry panel (including total protein, albumin, sodium, potassium, glucose, bilirubin, LDH, creatinine, AST, ALT, GGT, alkaline phosphatase, CRP/hsCRP, and urea) were collected.",
  "protocol_reference": "Table 1 SOA, page 22-26; Footnote 12: \"Biochemistry analyses include total protein, albumin, sodium...CRP/hsCRP is preferred, and urea.\"",
  "additional_footnotes": "Footnote 14: Lab assessment can be done up to one week prior to the visit."
}
```

### Incorrect: generalized

```json
{
  "rule_for_llm": "V4- Verify that a safety laboratory assessment was performed."
}
```
Problem: "safety laboratory assessment" is too vague — CRP specifically required per footnote.

---

### Correct: vitals include position and dual-measurement on treatment days

```json
{
  "kri_id": "SOA-V1-034",
  "kri_name": "V1- Vital signs",
  "rule_for_llm": "V1- Verify that vital signs (temperature, heart rate, respiratory rate, blood pressure) were measured TWICE: once prior to IMP injection and once 45 ± 15 minutes after IMP injection, with the participant in a supine position (or most recumbent position possible if supine is not achievable).",
  "additional_footnotes": "Footnote 10: On days of treatment, vital signs will be monitored twice: the first time prior to IMP injection, and the second time 45±15 minutes after IMP injection."
}
```

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
