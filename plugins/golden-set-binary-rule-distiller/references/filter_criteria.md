# Filter criteria — keep/drop rubric

This file is the working reference for Stage 1 (drop nomination) and Stage 2 (drop defense). The goal: keep ONLY rules that can produce a binary deviation from trial data, anchored in the protocol.

The filter is an **authoring-feasibility test**: a rule is kept iff a binary, unambiguously-testable `Rule for LLM` can be authored for it from the protocol (the incoming Golden Set has no usable `Rule for LLM` — Stage 3 authors it).

**This rubric is keep-biased and runs across two panels (both Gemini 3.5 Flash, high thinking):** in **Stage 1** a panel *nominates* drop candidates (any drop vote makes a rule a candidate — keep is the default); in **Stage 2** a second panel *defends* each candidate, ruling **equivalent rules as one family**: a family is dropped only on a clear **≥ 4/5 confirm** (or ≥ ⅔ of pooled family votes), restored if the defense reaches ≥ 3/5, and **every 3–2 near-tie is escalated to the user**. No single reviewer drops a rule, and no rule is dropped on a knife-edge vote. Discretionary/optional procedures are not kept as ordinary presence rules, but can be invert-kept or kept-scoped rather than dropped (see drop list). The criteria below are what every reviewer applies; "lean toward drop" never means "drop on one opinion" — it means "nominate for the defense panel."

## The three filter criteria (a rule must satisfy ALL three to be kept)

1. **Binary checkable.** Data either complies or doesn't. Yes/no, in-window or out, threshold met or not, present or missing.
2. **Tied to trial data.** The rule references subject-, site-, or trial-level data that is actually collected or reported during the trial.
3. **Produces a clear deviation when violated.** A specific anomaly can be flagged. There's an observable failure mode.

## The Case A/B/C distinction — where most close calls live

Reviewers often disagree on rules whose protocol wording is fuzzy. The clarifying distinction:

### Case A — Clean numeric bound (binary)
> "ALT or AST > 8× ULN must trigger discontinuation."

Crisp number, no qualifier. The engine compares the lab value to 8× ULN — strictly binary. **KEEP.**

### Case B — Numeric target with soft qualifier (still binary, with judgment at edges)
> "Infused IV over **approximately 30 minutes**."

There IS a concrete target (30 min). The "approximately" signals that the protocol doesn't define an exact tolerance, but the target itself is measurable. **KEEP** — and in the Stage 3 authoring, preserve the "approximately 30 minutes" wording. The downstream LLM engine reads the rule + the actual duration and uses judgment for borderline cases. The rule still produces a binary outcome (flag/no-flag) at runtime, even if the boundary is judgment-based at the margin.

### Case C — Pure aspirational, no measurable anchor (NOT binary)
> "Topical should be administered before antibiotics **when feasible**."

No target, no threshold, no measurable attribute — only an aspiration. There's no data point that, by itself, produces a deviation. **Nominate for drop** (Stage 1) — it has no anchor to defend, so the defense panel will confirm it.

### The principle behind A/B/C

A rule passes the binary filter if there's a **measurable data point** (a number, date, presence/absence, category) that the rule references — even if the threshold is fuzzy. The LLM applies reasonable judgment when the protocol leaves tolerance unspecified.

A rule fails the binary filter if there's **no measurable anchor at all** — the protocol gives only an aspiration with no data to measure against.

## Drop list — common patterns that fail the filter

Drop any rule that is primarily:

- **Pure endpoint definitions.** "The primary endpoint is X." Defining what the endpoint is, not checking compliance.
- **Pure population definitions.** ITT / FAS / PP / Safety descriptions. These define analysis populations, not data deviations.
- **Statistical methodology.** "Analyzed via MMRM with treatment group and week as covariates." Kaplan-Meier descriptions, hierarchical testing, sample-size calculations. Methodology, not deviations.
- **Reporting metrics.** "% of subjects with X are reported." These describe what gets summarized in a CSR, not what gets flagged in monitoring.
- **Exploratory analyses or correlations.** "Correlation between anti-phage antibodies and treatment outcome." Hypothesis-generating, not pass/fail.
- **Permissive options.** "Sponsor may reduce enrollment to N subjects." Authority statements, not protocol violations.
- **Discretionary / optional procedures.** Anything performed at someone's discretion — "may be performed", "optionally", "in a subset", "per Sponsor instruction", "per investigator judgment". Non-performance is NOT a deviation (discretion is not a protocol-mandated trigger), so these are never kept as an ordinary presence rule, and an "if it was performed, its presence is checkable" argument does NOT by itself justify one. Decide among three outcomes:
  - **Invert and KEEP** when the authorization is *documentable* (a Sponsor instruction, an imaging-plan designation, a recorded per-protocol gate): the deviation is performing it *without* documented authorization, and omission is explicitly NOT a deviation (author per rewrite_format.md rule 11).
  - **Keep as an ordinary presence rule scoped to the designated population** when the protocol *requires* it for a **conditional-mandatory** trigger or a defined recorded subset (e.g. "direct bilirubin if total bilirubin is abnormal"; "pregnancy test for women of childbearing potential"; "required for subjects at applicable sites / all main-phase patients per the imaging plan"): the trigger/denominator is defined and recorded and the action is required when it holds.
  - **DROP** only when there is neither a documentable authorization to check against nor a protocol-defined recorded trigger — pure unanchored discretion.
- **Broad meta-compliance umbrellas.** Generic "follow GCP / 21 CFR / Helsinki" with no discrete data check.
- **Pure term or threshold definitions** with no embedded action. "A significant pathogen is >10⁶ CFU per plate." Defines a threshold used elsewhere; doesn't itself trigger a deviation.
- **Pure aspirations** with no measurable anchor (Case C above).
- **Subjective investigator-judgment rules** with no objective data point. "Any local reaction that in the investigator's judgment constitutes an AE." If the only trigger is opinion, the rule isn't data-checkable.

## Keep list — patterns that satisfy the filter

Keep rules with:

- **Clean numeric bounds** (Case A).
- **Numeric targets with soft qualifiers** (Case B) — preserve protocol wording.
- **Presence/absence checks** — "verify procedure X performed at visit Y", "ICF signed before any study procedure", "screening log maintained at the site".
- **Time-window checks** — "AE entered into CRF within 24 hours of investigator awareness", "V2 visit within ±3 days of Day 1 + 14 days".
- **Inclusion/exclusion criteria** — "subject is excluded if hemoglobin < 7 g/dL".
- **Stopping rules** — "discontinue if ALT > 8× ULN".
- **Trial-level cumulative checks** — "DMC meets every 4-6 months", "active:placebo ratio is 2:1".
- **Inverted optional (Sponsor-gated) checks** — an optional/discretionary procedure whose authorization is documentable: the deviation is *performed without documented authorization* (omission is not a deviation). See rewrite_format.md rule 11.

## Timeliness / reporting-deadline rules — keep via a date proxy

A rule that requires an action within N hours/days of an event ("SAE reported within 24 h of awareness", "AE entered into the CRF within N days") reads like workflow, but it is **binary**: it is checkable as a date difference, (action date − event date) ≤ N. **Never nominate these for drop as "process", "workflow", or "reporting metric".**

- Author the check against the closest dates the trial actually records. When the exact clock the protocol names is not captured in EDC (e.g. the precise investigator-awareness timestamp), fall back to the nearest available dates — e.g. (CRF entry date − event onset date) ≤ N — and state that proxy in `evidence_expected` (see rewrite_format.md, rule 9).
- If a reporting rule has no clean clock at all (neither a usable event date nor an action date to difference), keep it but narrow the check to the part that IS recorded — e.g. "the outcome was recorded" — rather than dropping it.

This is distinct from a true **reporting metric** ("% of subjects with X are summarised in the CSR"), which describes a CSR summary, not a per-event deadline, and stays on the drop list.

## Cross-check discipline — the rule that prevents fabrication

Before keeping or dropping a rule, open the protocol PDF at the cited section/page in the `Protocol Reference & Quote` column and read the surrounding context (the full paragraph, not just the snippet). Then decide.

If the cited reference doesn't actually support the rule's intent — i.e., the Golden Set is making up something the protocol never says — lean toward drop. Don't try to rescue a fabricated rule by interpreting around it.

## Holistic judgment — read every column

The incoming columns are hypotheses, not authority. The protocol PDF is the only authority. Judge holistically across:
- **KRI ID** — sometimes encodes the visit, the criterion number, the category.
- **Category / KRI Name** — high-level intent.
- **Description** — a restatement of intent; verify against the PDF.
- **Protocol Reference & Quote** — the citation. Open the PDF here, and read every footnote attached to the cell — footnotes carry the analytes, windows, and conditions the authored rule will need.
- **Severity** — context for the rule's importance.

(There is no usable incoming `Rule for LLM` to weigh — that column is authored in Stage 3.)

## Template-level evaluation

For homogeneous rule families — most commonly SOA visit × procedure cells — it's fine to evaluate the template once and apply the decision across all instances. Examples:

- All "verify <procedure> at <visit> per SOA" rules with a concrete procedure and visit → keep, as long as the procedure is actually scheduled at that visit per the SoA matrix.
- All "verify visit V occurred within ±N days of Day 1 + M days" rules → keep, with the correct window per the SoA footnote.

Watch for template traps:
- Rules generated for visit/procedure cells the SoA marks as conditional or optional (e.g., bone biopsy "if performed") — these need scoping.
- Rules applied to UNS (unscheduled) visits — UNS has no protocol-required schedule, so per-procedure-at-UNS rules need to fire conditionally on what triggered the unscheduled visit.
- Rules applied to procedures tied to specific dosing routes (e.g., solicited AEs at IV-dosing sessions) but propagated to non-dosing visits — these need scoping.

When you find a template trap, decide on the right scope by reading the SoA footnotes in the PDF. Either drop the out-of-scope instances or author their Rule for LLM with the conditional gate.

## Common pre-existing source-file bugs to flag (not silently fix)

Surface these in the audit log, do not silently fix:

- **Duplicate KRI IDs.** Same ID used for two distinct rules.
- **Truncated protocol-quote text.** Citation ends mid-word or mid-sentence.
- **Copy-paste boilerplate descriptions.** Same Description text reused on rules that mean different things.
- **Mis-anchored protocol references.** Citation pointing at a section that doesn't support the rule.

Per the hard constraints, only fix these on explicit user authorization.
