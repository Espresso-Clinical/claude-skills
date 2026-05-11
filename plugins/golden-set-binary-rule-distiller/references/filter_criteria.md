# Filter criteria — keep/drop rubric

This file is the working reference for Stage 1 (binary filter) and Stage 2 (panel filter). The goal: keep ONLY rules that can produce a binary deviation from trial data, anchored in the protocol.

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

There IS a concrete target (30 min). The "approximately" signals that the protocol doesn't define an exact tolerance, but the target itself is measurable. **KEEP** — and in the Stage 3 rewrite, preserve the "approximately 30 minutes" wording. The downstream LLM engine reads the rule + the actual duration and uses judgment for borderline cases. The rule still produces a binary outcome (flag/no-flag) at runtime, even if the boundary is judgment-based at the margin.

### Case C — Pure aspirational, no measurable anchor (NOT binary)
> "Topical should be administered before antibiotics **when feasible**."

No target, no threshold, no measurable attribute — only an aspiration. There's no data point that, by itself, produces a deviation. **DROP at Stage 1.**

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

## Cross-check discipline — the rule that prevents fabrication

Before keeping or dropping a rule, open the protocol PDF at the cited section/page in the `Protocol Reference & Quote` column and read the surrounding context (the full paragraph, not just the snippet). Then decide.

If the cited reference doesn't actually support the rule's intent — i.e., the Golden Set is making up something the protocol never says — lean toward drop. Don't try to rescue a fabricated rule by interpreting around it.

## Holistic judgment — read every column

Treat the `Rule for LLM` text in the source Golden Set with **limited trust**. It is often the most malformed column. The Description and Protocol Reference & Quote are usually more reliable, but still not authoritative. The protocol PDF is the only authority.

Judge holistically across:
- **KRI ID** — sometimes encodes the visit, the criterion number, the category.
- **Category / KRI Name** — high-level intent.
- **Description** — usually a tighter restatement than Rule for LLM.
- **Rule for LLM** — limited trust; often the most malformed.
- **Protocol Reference & Quote** — the citation. Open the PDF here.
- **Severity** — context for the rule's importance.

## Template-level evaluation

For homogeneous rule families — most commonly SOA visit × procedure cells — it's fine to evaluate the template once and apply the decision across all instances. Examples:

- All "verify <procedure> at <visit> per SOA" rules with a concrete procedure and visit → keep, as long as the procedure is actually scheduled at that visit per the SoA matrix.
- All "verify visit V occurred within ±N days of Day 1 + M days" rules → keep, with the correct window per the SoA footnote.

Watch for template traps:
- Rules generated for visit/procedure cells the SoA marks as conditional or optional (e.g., bone biopsy "if performed") — these need scoping.
- Rules applied to UNS (unscheduled) visits — UNS has no protocol-required schedule, so per-procedure-at-UNS rules need to fire conditionally on what triggered the unscheduled visit.
- Rules applied to procedures tied to specific dosing routes (e.g., solicited AEs at IV-dosing sessions) but propagated to non-dosing visits — these need scoping.

When you find a template trap, decide on the right scope by reading the SoA footnotes in the PDF. Either drop the out-of-scope instances or rewrite their Rule for LLM to include the conditional gate.

## Common pre-existing source-file bugs to flag (not silently fix)

Surface these in the audit log, do not silently fix:

- **Duplicate KRI IDs.** Same ID used for two distinct rules.
- **Truncated protocol-quote text.** Citation ends mid-word or mid-sentence.
- **Copy-paste boilerplate descriptions.** Same Description text reused on rules that mean different things.
- **Mis-anchored protocol references.** Citation pointing at a section that doesn't support the rule.
- **Truncated or malformed Rule for LLM text.** Sentence fragments.

Per the hard constraints, only fix these on explicit user authorization.
