# v0.5.3 — Recommendation and layout refinement

This release addresses two issues observed in the Ioannis four-provider report:

1. **Recommendation bias** — the report over-weighted the fact that Bupa's outpatient cover sits inside the base plan. The comparison must evaluate the final quoted configuration. A Cigna optional module that is confirmed selected and priced is part of the actual offer and should not be penalised merely for being modular.
2. **Presentation overflow** — long headlines and alternative-plan names caused overlap in the PPTX, while the PDF cover title could collide with the Ashlar eyebrow because its fixed title row was too short.

The report writer now treats Bupa vs IMG as a genuine trade-off when the client's priority is simply strong inpatient + outpatient cover. It may still recommend one plan if the evidence and priorities support it, but it is explicitly allowed to leave the preferred fields blank and explain two leading fits when the trade-off is close.
