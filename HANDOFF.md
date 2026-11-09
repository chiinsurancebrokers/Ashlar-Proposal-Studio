# Handoff: Ashlar Proposal Studio, Family Mix (Totikidis case)

Owner: Chris Iatropoulos (Ashlar Assurance / Chi Insurance Brokers). Branch `feature/family-mix`, PR #11.

## What this is
A feature that finds the best combination of health plans for a mixed local and international family, used first on the Totikidis family: Katja in Greece (limited budget) and two daughters studying in Germany.

## Decisions made
- Katja options: Generali Life On (EUR 2,169.84 a year, EUR 1,500 participation, hospital-only, plus the Doctors & Exams add-on if included) and VUMI Euro Health VIP Priority (EUR 2,909.50 a year, nil excess, paid yearly, taxes included).
- Daughters: IMG Global Prima Bronze Plus, nil excess, EUR 1,338.61 a year (EUR 111.55 a month) each.
- Household totals: Generali + IMG EUR 4,847.06 a year; VUMI + IMG EUR 5,586.72.
- Dropped: APRIL (it was the International tier, not Plus) and IMG for Katja.
- Greek client page follows the Polat HTML template. Greek style: 2.169,84 and dd/mm/yyyy.

## Code state
- Files: core/family_mix.py, family_optimizer.py, family_bridge.py, family_study.py, waiting_periods.py, family_mix_page.py, and save_family_mix in core/case_archive.py.
- The optimiser searches every way to split the household across plans, never credits benefits a quote does not show, and reports which unknowns would change the winner.
- The screen downloads the study in Greek or English and saves the chosen combination to the case.
- 295 tests pass.

## Open items
1. Run supabase/cases_schema.sql once to add the family_mix_json column.
2. ANSWERED by Generali Life On quote 08547587: the EUR 2,169.84 a year includes Doctors & Exams Premium, Prevention Standard, Hospital Premium Flexi (EUR 620,000, participation EUR 1,500), Rehabilitation Standard, basic life and two supplementary covers. Life On is modular, not hospital-only, and the participation can be 0, 750, 1,500, 3,000, 5,000 or 10,000. core/generali_plans.py holds the benefit terms; core/family_mix.py still needs its Generali benefit states updated from them.
3. No Generali waiting-period wording for covers other than Hospital Premium Flexi and Doctors & Exams.
4. Test the screen with a real case once Railway is back (the Railway connector needs reconnecting).
5. Optional: align the English proposal doc with the Greek page.

## Where things are
Greek page: claude.ai/artifact/Hy3rmbBYUJV7A8Hj7QuN7M. English doc: "Family health insurance proposal: Totikidis". Spec doc: "Proposal Studio: mixed-insurer family proposals".
