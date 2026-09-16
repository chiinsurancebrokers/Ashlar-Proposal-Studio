# v0.4.6 — Bupa + Now Health validation

Validated against real user-supplied samples on 2026-09-15.

## Bupa Global Select

Applicant quote source: saved Bupa Global quote email (HTML)
Provider source: Select Global Health Plan Membership Guide

Deterministically locked from the applicant quote:
- Plan: Select
- Premium: EUR 2,165.08 annually
- Area: Worldwide excluding USA
- Annual allowance: EUR 1,250,000
- Outpatient deductible: EUR 0
- All-other-benefits deductible: EUR 0
- Quote-summary benefit hints: inpatient, outpatient consultations/GPs, cancer, mental health and emergency medical evacuation covered; maternity, dental and optical not covered on the quotation.

The Select guide is a single-plan document. It is therefore not forced through the multi-plan geometric column extractor. The full guide is supplied to the analysis engine, while applicant-specific material facts stay locked to the quote.

## Now Health SimpleCare 250

Applicant quote: SimpleCare quotation + applicant-specific benefit schedule
Provider source: SimpleCare Explained 2026 brochure

Deterministically locked from the applicant quote:
- Plan: SimpleCare 250
- Premium: EUR 1,092.07 annually
- Underwriting: Full Medical Underwriting
- Area: Worldwide excluding USA
- In/day-patient deductible: EUR 0
- Annual maximum: EUR 1,200,000
- Base outpatient annual limit: EUR 2,000
- Evacuation/repatriation combined limit: EUR 80,000
- Outpatient psychiatric illness: EUR 320
- Dental: EUR 240, 20% co-insurance, subject to stated waiting period/exclusions

The Now Health applicant quotation already contains a plan-specific benefit schedule. It is treated as the strongest plan-benefit evidence for the quoted SimpleCare 250 plan rather than forcing the generic multi-plan brochure parser over the provider brochure.

A broker-review warning is raised because the sample quote shows `Worldwide excluding USA` while its Network field reads `SimpleCare Europe`. Proposal Studio does not resolve that discrepancy itself; it asks the broker to verify it before presentation.

## Other changes

- Added HTML / HTM document extraction for saved insurer quote emails.
- Explicit rule-based plan locks for Bupa Select and Now Health SimpleCare CORE / 100 / 250.
- Quality gate understands carrier benefit strategies:
  - IMG / Cigna: multi-plan target-column extraction
  - Bupa: single-plan guide
  - Now Health: applicant-specific quote schedule
- Bupa and Now Health adapters promoted from `framework` to `validated` for these document families.
