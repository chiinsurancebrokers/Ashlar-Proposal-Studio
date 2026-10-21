"""Family Mix: find the best combination of plans for a household.

Uses the options already analysed in the Case Studio. The broker says what each person needs and
who each option covers. The optimiser (core/family_optimizer.py) does the rest.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core.family_bridge import (
    BENEFITS, WEIGHTS, person_key, plan_display, run_family_mix,
)
from core.family_mix import Person, check_scenario
from core.family_optimizer import as_scenario, explain, optimise

NEED_CHOICES = [""] + list(WEIGHTS)
BUDGET_CHOICES = ["High", "Normal", "Low"]


def _eur(value) -> str:
    return f"€{value:,.2f}"


def family_mix_page(page_header=None) -> None:
    if page_header:
        page_header("FAMILY MIX", "Best combination for the family",
                    "Each person is matched to the plan that fits them. The studio searches every way to cover the household.")
    else:
        st.title("Best combination for the family")

    results = st.session_state.get("results") or []
    if not results:
        st.info("Analyse the plans in Case Studio first. They appear here so each one can be assigned to the people it covers.")
        return

    st.subheader("1. People")
    people_df = st.data_editor(
        pd.DataFrame(st.session_state.get("fm_people") or [{"Name": "", "Residence": "", "Budget": "Normal"},
                                                          {"Name": "", "Residence": "", "Budget": "Normal"}]),
        num_rows="dynamic", use_container_width=True, key="fm_people_editor",
        column_config={"Budget": st.column_config.SelectboxColumn("Budget sensitivity", options=BUDGET_CHOICES,
                                                                  help="How much cost matters for this person.")},
    )
    people_rows = people_df.to_dict("records")
    names = [str(r.get("Name") or "").strip() for r in people_rows if str(r.get("Name") or "").strip()]
    st.session_state["fm_people"] = people_rows

    st.subheader("2. What each person needs")
    if not names:
        st.caption("Add a name above to set needs.")
        return
    need_base = pd.DataFrame({"Benefit": list(BENEFITS.values()), **{n: [""] * len(BENEFITS) for n in names}})
    saved = st.session_state.get("fm_needs")
    if isinstance(saved, pd.DataFrame) and list(saved.columns) == list(need_base.columns):
        need_base = saved
    needs_df = st.data_editor(
        need_base, hide_index=True, use_container_width=True, key=f"fm_needs_editor_{'|'.join(names)}",
        disabled=["Benefit"],
        column_config={"Benefit": st.column_config.TextColumn("Benefit"),
                       **{n: st.column_config.SelectboxColumn(n, options=NEED_CHOICES) for n in names}},
    )
    st.session_state["fm_needs"] = needs_df
    st.caption("A must-have benefit rules out any plan that does not cover it. Leave a cell blank when the person does not need it.")

    st.subheader("3. Who each option covers")
    assignments: dict[int, list[str]] = {}
    residences: dict[int, list[str]] = {}
    for i, result in enumerate(results):
        left, right = st.columns([3, 2])
        with left:
            chosen = st.multiselect(plan_display(result), names, key=f"fm_assign_{i}",
                                    help="Choose everyone this option's premium covers. A family policy covers several people.")
        with right:
            where = st.text_input("Accepts residents of", key=f"fm_where_{i}", placeholder="any",
                                  help="Countries the plan accepts, separated by commas. Leave empty for any.")
        assignments[i] = [person_key(n) for n in chosen]
        residences[i] = [w.strip() for w in where.split(",") if w.strip()]

    cap = st.number_input("Yearly budget for the household (0 for none)", min_value=0, step=100, key="fm_cap")

    if not st.button("Find the best combination", type="primary", key="fm_run"):
        return

    outcome, profiles, notes = run_family_mix(
        people_rows, [dict(r) for r in needs_df.to_dict("records")], results, assignments,
        residences=residences, budget_cap=cap or None)
    for line in notes:
        st.warning(line)
    if outcome is None:
        st.error("Add at least one person and assign at least one option before searching.")
        return
    if outcome.winner is None:
        st.error("No eligible plan for: " + ", ".join(outcome.infeasible)
                 + ". Check residence, must-have benefits and who each option covers.")
        return

    best = outcome.winner
    st.success(f"{best.label}: {_eur(best.total)} a year ({_eur(best.total / 12)} a month, yearly total divided by 12).")
    for line in explain(outcome, profiles):
        st.write(line)

    if outcome.flips:
        st.warning("Confirm before recommending: " + "; ".join(
            f"{f.plan_key} {f.benefit} (if covered, {f.new_winner} wins)" for f in outcome.flips))
    elif outcome.robust:
        st.caption(f"Tested {outcome.resolutions_tested or 1} ways the benefits not shown could turn out. The winner holds in all of them.")

    scenario = as_scenario(best)
    if scenario is not None:
        people = [Person(p.person, p.name) for p in profiles]
        flags = check_scenario(scenario, people)
        for flag in flags:
            st.caption(f"{flag.severity}: {flag.message}")

    st.subheader("All combinations")
    st.caption("Sorted by utility: household fit minus a price penalty. Fit is between 0 and 1.")
    table = pd.DataFrame([{
        "Combination": s.label, "Yearly total": _eur(s.total), "Fit": s.fit, "Price penalty": s.penalty,
        "Utility": s.utility, "Over budget": "yes" if s.over_budget else "",
        "To confirm": ", ".join(f"{b}" for _, b in s.unknown) if s.unknown else "",
    } for s in outcome.ranked[:15]])
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption("A licensed Ashlar broker reviews every recommendation before anything is placed.")
