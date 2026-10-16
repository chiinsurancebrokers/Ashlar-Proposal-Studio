"""Regression tests from the Sinan Polat (APRIL MyHealth Essential vs Bupa Select) audit."""
from core.analyzer import _apply_deterministic_facts
from core.carriers import bupa_quote_facts
from core.client_analysis import (
    _clip_words,
    _compact_decision_payload,
    _plan_narrative_from_verified_facts,
    apply_client_report_rules,
    build_comparison_matrix,
    maternity_relevant,
)
from core.library_classify import guess_doc_type, product_mismatch, table_first
from core.plan_rules import apply_access_rules, extract_access_rules

BUPA_QUOTE = """Selected plan: Select
EUR 598 Monthly
EUR 7176 a year
Area covered: Worldwide excluding U.S.
Annual allowance: EUR 1250000
Out-patient deductible: EUR 0
All other benefits deductible: EUR 0
Cover summary
What's covered:
Treatment when you're admitted to hospital
Medical evacuation in emergencies
Mental health treatment
Cancer treatment
Specialists consultations and GPs
Prescribed medicines
What's not covered:
Maternity care
Dental treatment
Complementary therapies e.g. Chinese medicine
Optical care
"""

APRIL_TOB_EXCERPT = """--- LIBRARY DOCUMENT: pdf-product-myhealth-international-2.0-benefits-table-en-2025.pdf [APRIL / MYHEALTH / 2026 / tob] ---
All treatments exceeding €/US$2,000, repeated procedures, and those listed in the Table of benefits are subject to Pre-approval.
Please send us your request at least 5 days before the planned treatment date.
Outside this network (except in cases of medical emergency or duly justified exceptional circumstances), a co-payment of 40% will be applied to the reimbursement of your invoice.
** All hospitalisations are subject to prior approval. A 50% penalty will be applied in case of failure to comply with this requirement before admission.
--- LIBRARY DOCUMENT: pdf-product-myhealth-international-2.0-providers-list-en-2025.pdf [APRIL / MYHEALTH / 2026 / supporting] ---
Explore and Essential: Full cover within the limits of reasonable and customary costs: all hospitals worldwide except those listed under the Extensive and Elite plans.
If you choose a hospital listed under "Extensive" or "Elite", 40% of the expenses incurred will remain at your charge.
"""


# 1. Maternity: a family policy insures the spouse, so maternity must be shown.
def test_maternity_relevant_for_family_policy_with_male_applicant():
    assert maternity_relevant(client_sex="Male", client_profile="family of 3, moving to France")
    assert maternity_relevant(client_sex="Male", client_profile="Ζευγάρι με ένα παιδί")
    assert not maternity_relevant(client_sex="Male", client_profile="single expat, moving to France")
    assert maternity_relevant(client_sex="Female")


def test_comparison_matrix_keeps_maternity_row_for_family():
    results = [{"provider": "APRIL", "analysis": {"provider": "APRIL", "plan_name": "Essential",
                "benefits": {"maternity": "Routine pregnancy €4,000 per pregnancy"}}}]
    topics = [r["topic"] for r in build_comparison_matrix(results, client_sex="Male", client_profile="family of 3")]
    assert "Maternity" in topics
    topics = [r["topic"] for r in build_comparison_matrix(results, client_sex="Male", client_profile="single")]
    assert "Maternity" not in topics


# 2. Bupa quote: yearly figure locked, exclusions read even without an "Important documents" footer.
def test_bupa_monthly_quote_locks_yearly_premium_and_exclusions():
    facts = bupa_quote_facts(BUPA_QUOTE)
    assert facts["premium"] == {"amount": "7176", "currency": "EUR", "frequency": "Annual"}
    assert facts["benefit_hints"]["dental"] == "Not covered on this quotation."
    assert facts["benefit_hints"]["maternity"] == "Not covered on this quotation."


# 3. A generic "covered, see the guide" hint must not erase what the guide says.
def test_guide_detail_survives_generic_quote_hint():
    result = {"benefits": {
        "outpatient": "EUR 9,400 annual maximum; 15 consultations a year; prescribed medicines up to EUR 1,250",
        "dental": "Accident-related dental only",
    }}
    out = _apply_deterministic_facts(result, "BUPA SELECT", BUPA_QUOTE, "")
    assert out["benefits"]["outpatient"].startswith("EUR 9,400")
    # An exclusion on the applicant's quote still wins.
    assert out["benefits"]["dental"] == "Not covered on this quotation."
    # A benefit the extraction left empty is still filled from the quote.
    assert "quote summary" in out["benefits"]["cancer"]


# 4. Considerations are labelled and the material rules come first.
def test_considerations_are_labelled_and_ranked():
    plan = {"provider": "Bupa Global", "plan_name": "Select", "benefits": {}, "critical_limitations": [
        {"topic": "Maternity care", "detail": "Not covered — explicitly excluded from cover summary"},
        {"topic": "Dental treatment", "detail": "Not covered — explicitly excluded from cover summary"},
        {"topic": "Treatment for sleep disorders", "detail": "Not covered"},
        {"topic": "Out-patient day to day care annual maximum", "detail": "EUR 9,400 annual maximum"},
        {"topic": "Prescribed medicines and dressings limit", "detail": "Up to EUR 1,250 each policy year"},
        {"topic": "Pre-authorisation requirement", "detail": "Mandatory pre-authorisation for in-patient stays of 5+ nights and advanced imaging."},
    ]}
    cons = _plan_narrative_from_verified_facts(plan)["considerations"]
    assert cons[0].startswith("Pre-authorisation requirement:")
    assert any("9,400" in c for c in cons) and any("1,250" in c for c in cons)
    assert all(c.split(":")[0] for c in cons)
    assert not any(c.startswith("Not covered") for c in cons)


# 5. APRIL access rules (network 40%, prior approval 50%, pre-approval above €2,000).
def test_april_access_rules_reach_points_to_consider():
    rules = extract_access_rules(APRIL_TOB_EXCERPT)
    assert rules["network_copayment_pct"] == 40
    assert rules["network_tiered"] and rules["provider_list_supplied"]
    assert rules["hospital_prior_approval_penalty_pct"] == 50
    assert rules["pre_approval_threshold"] == "2,000" and rules["pre_approval_lead_days"] == 5

    result = {"critical_limitations": [
        {"topic": "Psychiatric care", "detail": "not covered"},
        {"topic": "Hospital access tiering", "detail": "If insured chooses a hospital listed under Extensive or Elite, 40% of expenses remain at insured's charge"},
    ]}
    apply_access_rules(result, APRIL_TOB_EXCERPT)
    topics = [x["topic"] for x in result["critical_limitations"]]
    assert topics[:3] == ["Hospital network", "Prior approval for hospitalisation", "Pre-approval above €2,000"]
    assert "Hospital access tiering" not in topics  # the model's duplicate is dropped
    cons = _plan_narrative_from_verified_facts({"benefits": {}, **result})["considerations"]
    assert "40%" in cons[0] and "providers list" in cons[0]
    assert "50%" in cons[1]
    assert "€2,000" in cons[2]


def test_access_rules_absent_for_plan_without_them():
    assert extract_access_rules("Paid in full. Standard private room.") == {}


# 6. The same plan is not offered as recommended, extras and budget option.
def test_duplicate_recommendation_slots_are_cleared():
    report = {"plans": [], "ashlar_assessment": {
        "recommended_provider": "APRIL International Care", "recommended_plan": "MyHealth International ESSENTIAL",
        "headline": "x", "reasoning": ["y"],
        "extras_provider": "APRIL International Care", "extras_plan": "MyHealth International ESSENTIAL", "extras_reason": "dental",
        "budget_provider": "APRIL International Care", "budget_plan": "MyHealth International ESSENTIAL", "budget_reason": "cheaper",
        "alternative_provider": "Bupa Global", "alternative_plan": "Select",
    }}
    out = apply_client_report_rules(report, results=[], client_sex="Male", client_profile="family of 3")
    ass = out["ashlar_assessment"]
    assert ass["extras_plan"] == "" and ass["budget_plan"] == ""
    assert ass["alternative_plan"] == "Select"


# 7. Waiting periods reach the report writer (they used to arrive as empty strings).
def test_compact_payload_keeps_waiting_periods_and_maternity():
    payload = {"maternity_relevant": True, "plans": [{
        "provider": "APRIL", "plan_name": "Essential",
        "benefits": {"maternity": "Routine pregnancy €4,000 per pregnancy"},
        "waiting_periods": [{"benefit": "Complications of pregnancy", "period": "12 months"}],
        "critical_limitations": [],
    }]}
    plan = _compact_decision_payload(payload)["plans"][0]
    assert plan["waiting_periods"] == ["Complications of pregnancy: 12 months"]
    assert "maternity" in plan["benefits"]


# 8. Clipping stops at a clause, never mid-figure.
def test_clip_words_cuts_at_clause_boundary():
    text = ("Unlimited annual limit; general practitioners and specialists €2,500; drugs and dressings €2,000 "
            "(doubled for chronic conditions); diagnostic tests €5,000; outpatient mental health €500 max 7 sessions")
    clipped = _clip_words(text, 22)
    assert clipped.endswith("; …")
    assert "max 7…" not in clipped


# 9. Library uploads: type per file, wrong-product guide refused.
def test_library_doc_type_detection():
    assert guess_doc_type("pdf-product-myhealth-international-2.0-benefits-table-en-2025.pdf") == "tob"
    assert guess_doc_type("pdf-product-myhealth-international-2.0-general-conditions-en-2025.pdf") == "wording"
    assert guess_doc_type("pdf-product-myhealth-international-2.0-providers-list-en-2025.pdf") == "supporting"
    assert guess_doc_type("pdf-product-myhealth-international-2.0-brochure-en-2025.pdf") == "brochure"
    assert guess_doc_type("DAC-SELE-MEMB-EN-XXXX-2412-0055222.pdf") == "wording"
    assert guess_doc_type("DAC-SELE-IPID-EN-XXXX-2411-0054689.pdf") == "supporting"
    assert guess_doc_type("quote.pdf", "Benefits schedule MyHealth International") == "tob"
    assert guess_doc_type("scan001.pdf", "") is None


def test_premier_guide_is_refused_under_select():
    premier = "A GUIDE TO YOUR PREMIER GLOBAL HEALTH PLAN A COLLABORATION BETWEEN TWO OF THE MOST RESPECTED NAMES"
    select = "A GUIDE TO YOUR SELECT GLOBAL HEALTH PLAN"
    siblings = ["Premier", "Select", "WorldWide Health Options"]
    assert product_mismatch("Select", premier, siblings) == "Premier"
    assert product_mismatch("Select", select, siblings) is None
    assert product_mismatch("Premier", premier, siblings) is None


def test_tables_of_benefits_are_read_first():
    class D:
        def __init__(self, t): self.doc_type = t
    assert [d.doc_type for d in table_first([D("brochure"), D("wording"), D("tob")])] == ["tob", "brochure", "wording"]


# 10. Household members (HAL 3 rules) — listed in the report and drive maternity.
def test_household_members_rules_and_report():
    from core.household import household_maternity_relevant, insured_people, normalise_members

    rows = [
        {"Name": "Ayse Polat", "Relationship": "Spouse / partner", "Age": 33, "Sex": "Female", "Maternity cover": True},
        {"Name": "Deniz Polat", "Relationship": "Child", "Age": 3.0, "Sex": "Male", "Maternity cover": float("nan")},
        {"Name": "Older child", "Relationship": "Child", "Age": 26, "Sex": "Female", "Maternity cover": False},
        {"Name": None, "Relationship": None, "Age": float("nan"), "Sex": None, "Maternity cover": None},
    ]
    members, warnings = normalise_members(rows)
    assert [m["name"] for m in members] == ["Ayse Polat", "Deniz Polat"]
    assert members[0]["maternity"] is True and members[1]["maternity"] is False
    assert any("under 25" in w for w in warnings)

    people = insured_people(client_name="Sinan Polat", client_sex="Male", client_age=36, members=members)
    assert [p["relationship"] for p in people] == ["Main applicant", "Spouse / partner", "Child"]

    assert household_maternity_relevant(client_sex="Male", client_age=36, members=members) is True
    father_and_son = [{"name": "Son", "relationship": "Child", "age": 10, "sex": "Male"}]
    assert household_maternity_relevant(client_sex="Male", client_age=50, members=father_and_son) is False
    assert household_maternity_relevant(client_sex="Male", members=[]) is None
    # Entered dependants override the profile wording.
    assert not maternity_relevant(client_sex="Male", client_profile="family of 2", household_members=father_and_son)


def test_maternity_flag_ignored_for_ineligible_member():
    from core.household import normalise_members
    members, warnings = normalise_members([{"name": "Grandad", "relationship": "Other dependant", "age": 70, "sex": "Male", "maternity": True}])
    assert members[0]["maternity"] is False and warnings


def test_pdf_lists_insured_members():
    import io
    from pypdf import PdfReader
    from core.report_pdf import build_pdf_bytes
    analysis = {
        "client_name": "Sinan Polat", "executive_summary": "Summary.", "plans": [], "comparison_matrix": [],
        "insured_members": [
            {"name": "Sinan Polat", "relationship": "Main applicant", "age": 36},
            {"name": "Ayse Polat", "relationship": "Spouse / partner", "age": 33},
            {"name": "Deniz Polat", "relationship": "Child", "age": 3},
        ],
        "ashlar_assessment": {}, "key_differences": [], "important_considerations": [], "next_steps": [],
    }
    pdf = build_pdf_bytes(client_analysis=analysis, results=[], language="English")
    text = "".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "Insured members" in text and "Ayse Polat" in text and "Deniz Polat" in text


# 11. Shared case runner: wrong-product guide skipped, quote text kept for re-analysis.
class _Doc:
    def __init__(self, id, product, doc_type, filename, text):
        self.id, self.provider, self.product, self.version = id, "Bupa", product, "2026"
        self.doc_type, self.original_filename, self.extracted_text, self.sha256 = doc_type, filename, text, id


def test_case_runner_skips_premier_guide_and_keeps_quote(monkeypatch):
    import core.case_runner as runner
    docs = [
        _Doc("ipid", "Select", "supporting", "DAC Select Health Plan IPID EN OCT26.pdf",
             "--- PAGE 1 --- Insurance Product Information Document Product: Select Global Health Plan"),
        _Doc("prem", "Select", "wording", "DAC Premier Health Plan Membership Guide EN OCT26.pdf",
             "--- PAGE 1 --- A GUIDE TO YOUR PREMIER GLOBAL HEALTH PLAN"),
    ]
    monkeypatch.setattr(runner, "get_documents", lambda *a: docs)
    monkeypatch.setattr(runner, "list_catalog", lambda: [
        {"provider": "Bupa", "product": "Premier"}, {"provider": "Bupa", "product": "Select"}])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    row, warnings = runner.analyze_option(
        label="BUPA SELECT", quotation_text=BUPA_QUOTE,
        library_row={"provider": "Bupa", "product": "Select", "version": "2026"},
        underwriting_override="Full Medical Underwriting",
    )
    assert row["library_files"] == ["DAC Select Health Plan IPID EN OCT26.pdf"]
    assert row["excluded_library_documents"][0]["id"] == "prem"
    assert any("Premier" in w for w in warnings)
    assert row["quotation_text"] == BUPA_QUOTE
    assert row["analysis"]["premium"]["amount"] == "7176"

    args = runner.reanalysis_inputs(row)
    assert args["quotation_text"] == BUPA_QUOTE and args["underwriting_override"] == "Full Medical Underwriting"


def test_worker_reanalyses_saved_case(monkeypatch):
    import worker
    saved = {"id": "c1", "results_json": [{"provider": "ARIL MYHEALTH ESSENTIAL", "quotation_text": "Annual Premium* €6840,91 Incl Tax",
                                            "plan_selection": {"method": "broker_override", "plan_name": "ESSENTIAL"},
                                            "library_source": None, "underwriting_override": "Full Medical Underwriting"}],
             "client_analysis_json": {"old": True}}
    calls = {}
    monkeypatch.setattr(worker, "load_case", lambda cid: saved)
    monkeypatch.setattr(worker, "update_job", lambda jid, **f: calls.setdefault("updates", []).append(f))
    monkeypatch.setattr(worker, "save_case_snapshot", lambda **kw: calls.setdefault("saved", kw))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    worker.process_case_analysis({"id": "j1", "case_id": "c1",
                                  "request_json": {"labels": {"ARIL MYHEALTH ESSENTIAL": "APRIL MYHEALTH ESSENTIAL"}}})
    result = calls["saved"]["results"][0]
    assert result["provider"] == "APRIL MYHEALTH ESSENTIAL"
    assert result["target_plan"] == "ESSENTIAL"
    assert result["analysis"]["premium"]["amount"] == "6840.91"
    assert calls["saved"]["client_analysis"] is None
    assert calls["updates"][-1]["status"] == "completed"


def test_canonical_library_names():
    from core.library_classify import canonical_name
    assert canonical_name("BUPA", ["Bupa", "APRIL"]) == "Bupa"
    assert canonical_name("select ", ["Premier", "Select"]) == "Select"
    assert canonical_name("Allianz", ["Bupa"]) == "Allianz"


def test_excerpt_keeps_benefit_table_pages():
    from core.excerpt import benefit_focused_excerpt
    intro = "".join(f"--- PAGE {i} ---\nWelcome to your plan. Our story and values. " * 40 + "\n" for i in range(2, 10))
    table = "--- PAGE 10 ---\nTABLE OF BENEFITS\nOUT-PATIENT annual maximum EUR 9,400. Paid in full. Up to EUR 1,250 each policy year.\n" * 3
    text = "--- LIBRARY DOCUMENT: guide.pdf [Bupa / Select / 2026 / wording] ---\n--- PAGE 1 ---\nA GUIDE TO YOUR SELECT GLOBAL HEALTH PLAN\n" + intro + table
    out = benefit_focused_excerpt(text, 2500)
    assert "EUR 9,400" in out and "A GUIDE TO YOUR SELECT" in out and len(out) <= 2500
    assert benefit_focused_excerpt("short", 100) == "short"


def test_april_inpatient_scope_and_contradicted_maternity():
    result = {
        "benefits": {
            "inpatient": "Hospitalisation services in case of accident or emergency: 100%; Private room",
            "maternity": "Routine Pregnancy and Childbirth (12 months waiting period): €4,000 per pregnancy",
        },
        "critical_limitations": [
            {"topic": "Maternity option not selected", "detail": "Maternity benefits not selected in this quotation."},
            {"topic": "Pre-approval requirement", "detail": "All hospitalisations subject to pre-approval. 50% penalty applies."},
            {"topic": "Infertility treatment", "detail": "Not covered."},
        ],
    }
    plan_text = APRIL_TOB_EXCERPT + "\nHospitalisation** (Inpatient or Day-patient) Hospital Services or Day-patient treatment surgery 100%"
    apply_access_rules(result, plan_text)
    assert result["benefits"]["inpatient"].startswith("Hospital services and day-patient treatment (planned or emergency")
    topics = [x["topic"] for x in result["critical_limitations"]]
    assert "Maternity option not selected" not in topics
    assert "Pre-approval requirement" not in topics  # duplicate of the deterministic prior-approval row
    assert "Infertility treatment" in topics


def test_waiting_period_key_variants():
    from core.client_analysis import _limitation_text
    assert _limitation_text({"benefit": "Routine Dental Treatment", "waiting_period": "3 months"}) == "Routine Dental Treatment: 3 months"
    assert _limitation_text({"benefit": "Health screening", "duration": "10 months"}) == "Health screening: 10 months"


def test_household_dob_nationality_and_applicant_row():
    from datetime import date
    from core.household import age_on, applicant_row, insured_people, normalise_members
    rows = [
        applicant_row(dob="1990-06-21", nationality="Turkish"),
        {"name": "Alena Polat", "relationship": "Spouse / partner", "dob": "1993-01-13", "sex": "Female",
         "nationality": "Russian", "maternity": True},
        {"Name": "Adel Polat", "Relationship": "Child", "Date of birth": date(2023, 6, 26), "Nationality": "Turkish"},
    ]
    members, warnings = normalise_members(rows)
    assert [m["name"] for m in members] == ["Alena Polat", "Adel Polat"] and not warnings
    assert members[0]["age"] == age_on("1993-01-13") and members[1]["dob"] == "2023-06-26"
    people = insured_people(client_name="Sinan Polat", client_sex="Male", client_age=37, members=rows)
    assert people[0]["nationality"] == "Turkish" and people[0]["dob"] == "1990-06-21"
    assert people[0]["age"] == age_on("1990-06-21")  # date of birth wins over a stale age
    assert age_on("1990-06-21", date(2026, 10, 14)) == 36


def test_bupa_preauthorisation_rule_states_the_consequence():
    text = ("In-patient stays of 5 nights or more need pre-authorisation. "
            "Please contact us for pre-authorisation before proceeding with treatment. "
            "Benefit may not be paid unless pre-authorisation has been provided.")
    result = {"critical_limitations": [{"topic": "Pre-authorisation mandatory for multiple benefits", "detail": "Pre-authorisation required."}]}
    apply_access_rules(result, text)
    rows = result["critical_limitations"]
    assert rows[0]["topic"] == "Pre-authorisation" and "not be paid" in rows[0]["detail"] and "5+ nights" in rows[0]["detail"]
    assert len(rows) == 1
    # APRIL's fixed 50% penalty rule is not replaced by the generic one.
    assert "preauth_or_no_payment" not in extract_access_rules(APRIL_TOB_EXCERPT)


def test_evacuation_figures_are_grounded_and_quote_fills_evacuation():
    from core.carriers import generic_quote_facts
    from core.plan_rules import ground_benefit_amounts
    doc = ("TRANSPLANT SERVICES Each condition up to EUR 250,000. " + "Kidney dialysis paid in full. " * 40 +
           "TRANSPORTATION/TRAVEL Evacuation covers you. LIVING ALLOWANCE following an evacuation EUREUR 125125 per day.")
    r = {"benefits": {"evacuation_repatriation": "Evacuation paid in full. Living allowance EUR 125 per day. Each condition up to EUR 250,000."}}
    ground_benefit_amounts(r, doc)
    assert "250,000" not in r["benefits"]["evacuation_repatriation"]
    assert "EUR 125" in r["benefits"]["evacuation_repatriation"]
    q = "Emergency Medical Evacuation or Repatriation\n   100%   100%\n costs\n Repatriation of mortal remains   100%   100%"
    assert generic_quote_facts(q)["benefit_hints"]["evacuation_repatriation"].startswith("Emergency medical evacuation or repatriation: 100%")


def test_ungrounded_evacuation_limitation_row_is_dropped():
    from core.plan_rules import ground_benefit_amounts
    doc = "TRANSPLANT SERVICES Each condition up to EUR 250,000. " + "Kidney dialysis paid in full. " * 40 + "TRANSPORTATION Evacuation paid in full."
    r = {"benefits": {}, "critical_limitations": [
        {"topic": "Evacuation and repatriation limit per condition", "detail": "Each condition up to EUR 250,000."},
        {"topic": "Organ transplant limit", "detail": "Each condition up to EUR 250,000."},
    ]}
    ground_benefit_amounts(r, doc)
    assert [x["topic"] for x in r["critical_limitations"]] == ["Organ transplant limit"]


def test_analysis_call_retries_cut_off_answer_and_picks_outer_object():
    from types import SimpleNamespace
    from core.analyzer import _call_model

    full = '{"provider": "APRIL", "plan_name": "ESSENTIAL", "premium": {"amount": "6840.91"}, "benefits": {"inpatient": "100%"}}'
    calls = []

    class Messages:
        def create(self, **kw):
            calls.append(kw)
            if len(calls) == 1:  # cut off: only the nested premium object is complete
                return SimpleNamespace(stop_reason="max_tokens", content=[SimpleNamespace(type="text", text='{"provider": "APRIL", "premium": {"amount": "6840.91"}, "benefits": {"inpatient": "100% ...')])
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=full)])

    result, raw, err = _call_model(SimpleNamespace(messages=Messages()), "claude-opus-5-5", "PROMPT")
    assert err is None and result["benefits"]["inpatient"] == "100%" and len(calls) == 2
    assert calls[0]["max_tokens"] == 16000 and "cut off" in calls[1]["messages"][0]["content"]


PROVIDERS_LIST_PAGES = """--- LIBRARY DOCUMENT: pdf-product-myhealth-international-2.0-providers-list-en-2025.pdf [APRIL / MYHEALTH / 2026 / supporting] ---
Explore and Essential: Full cover within the limits of reasonable and customary costs: all hospitals worldwide
except those listed under the Extensive and Elite plans.
If you choose a hospital listed under "Extensive" or "Elite", 40% of the expenses incurred will remain at your charge.
--- PAGE 4 ---
Asia


   In the tables below:
     indicates that 40% of the incurred expenses will remain at your charge if you choose this hospital


  Cambodia


                                     Explore      Extensive        City             Hospital name           & Essential     & Elite

                      Royal Phnom Penh Hospital
                ANY HOSPITAL NOT LISTED ABOVE

--- PAGE 12 ---
Europe


   United Kingdom


                                     Explore      Extensive        City             Hospital name           & Essential     & Elite

                     Cromwell Hospital
                ANY HOSPITAL NOT LISTED ABOVE
"""


def test_providers_list_countries_and_destination_note():
    from core.plan_rules import destination_country, listed_network_countries, localise_access_rows
    text = APRIL_TOB_EXCERPT.split("--- LIBRARY DOCUMENT: pdf-product-myhealth-international-2.0-providers")[0] + PROVIDERS_LIST_PAGES
    assert listed_network_countries(text) == ["Cambodia", "United Kingdom"]
    rules = extract_access_rules(text)
    assert rules["network_listed_countries"] == ["Cambodia", "United Kingdom"]
    assert destination_country("family of 3, moving to France") == "France"
    assert destination_country("Expat family based in London, United Kingdom", ["Cambodia", "United Kingdom"]) == "United Kingdom"

    result = {"critical_limitations": [
        {"topic": "Hospital network tier", "detail": "Planned hospitalisation must be in the 'Explore & Essential' network tier. Otherwise a 40% co-payment applies. No France listing appears, so verify French hospitals."},
    ]}
    apply_access_rules(result, text)
    topics = [x["topic"] for x in result["critical_limitations"]]
    assert "Hospital network tier" not in topics and topics[0] == "Hospital network"

    row = localise_access_rows([{"analysis": result}], "family of 3, moving to France")[0]["analysis"]["critical_limitations"][0]
    assert "France is not on that list" in row["detail"] and "every hospital in France is covered in full" in row["detail"]
    row = localise_access_rows([{"analysis": result}], "family based in the United Kingdom")[0]["analysis"]["critical_limitations"][0]
    assert "United Kingdom is on that list: check the hospital" in row["detail"]
    # No destination: the stored row is left as it was.
    assert localise_access_rows([{"analysis": result}], "family of 3")[0]["analysis"] is result
    # The considerations clip keeps the destination sentence.
    cons = _plan_narrative_from_verified_facts({"benefits": {}, **localise_access_rows([{"analysis": result}], "moving to France")[0]["analysis"]})["considerations"]
    assert "France is not on that list" in cons[0]


BUPA_PREAUTH_PAGE = """If you need treatment and you know or think one of
the below applies to you, you must contact us for
pre-authorisation before you receive your treatment. If you                                   If you are taken to an 'out-of-network' benefit provider
don't get the following pre-authorised we will not cover the    Our approach to costs         in an emergency, it is important that you, or the benefit
cost:                                         When you are in need of a benefit provider,    provider, contact us within 48 hours of your admission,
                                                   team can help you find a Recognised medical practitioner,
¡  staying overnight in hospital                               hospital or healthcare facility within network.
¡   visiting hospital as a day-patient                      you can view a summary of benefit providers
¡  having treatment for cancer                               Finder at https://bupaglobal.com/en/facilities/finder.
¡  having advanced imaging, for example magnetic         Where you choose to have your treatment and services
   resonance imaging (MRI), computerised tomography (CT)   with a benefit provider in network, we will cover the costs
   or positron emission tomography (PET)                    of any covered benefits, once any applicable co-insurance
¡  rehabilitation                                           or deductible amount which you are responsible to pay has
¡  transportation/travel                                    been taken from the total claimed amount.
In-patient stays of 5 nights or more need pre-authorisation.
"""


def test_bupa_preauthorisation_list_and_emergency_notice():
    rules = extract_access_rules(BUPA_PREAUTH_PAGE)
    assert rules["preauth_items"] == [
        "staying overnight in hospital", "visiting hospital as a day-patient", "treatment for cancer",
        "advanced imaging", "rehabilitation", "transportation/travel",
    ]
    assert rules["emergency_notice_hours"] == 48
    result = {"critical_limitations": [
        {"topic": "Mandatory pre-authorisation", "detail": "The following will not be covered unless pre-authorised: overnight stays."},
        {"topic": "Out-of-network providers", "detail": "Only Reasonable and Customary costs are paid."},
    ]}
    apply_access_rules(result, BUPA_PREAUTH_PAGE)
    rows = result["critical_limitations"]
    assert [r["topic"] for r in rows] == ["Pre-authorisation", "Out-of-network providers"]
    assert "staying overnight in hospital" in rows[0]["detail"] and "within 48 hours" in rows[0]["detail"]
    cons = _plan_narrative_from_verified_facts({"benefits": {}, **result})["considerations"]
    assert "48 hours" in cons[0]


def test_visit_limit_is_per_benefit_unless_documents_say_shared():
    from core.plan_rules import ground_shared_limits
    doc = ("SPECIALISTS Up to 15 consultations each policy year. QUALIFIED NURSES Up to 15 consultations each policy year. "
           "IPID: 15 visits: specialists' consultations, doctors' fees, qualified nurses, mental health, physiotherapists.")
    r = {"critical_limitations": [{"topic": "Out-patient annual cap", "detail":
         "Capped at EUR 9,400. Consultations are limited to 15 per year, shared across specialists/doctors, nurses and mental health (per IPID)."}],
         "benefits": {}}
    ground_shared_limits(r, doc)
    detail = r["critical_limitations"][0]["detail"]
    assert "shared" not in detail and "15 per year for each of specialists/doctors" in detail
    # A limit the documents call combined is left alone.
    r2 = {"critical_limitations": [{"topic": "Therapies", "detail": "10 sessions per year, shared across physiotherapy and osteopathy."}]}
    ground_shared_limits(r2, "Physiotherapy and osteopathy: 10 sessions per year in total (combined).")
    assert "shared across" in r2["critical_limitations"][0]["detail"]


def test_rule_rows_keep_their_label_and_passing_preauth_mentions_do_not_rank():
    plan = {"benefits": {}, "critical_limitations": [
        {"topic": "Pre-authorisation", "detail": "Without pre-authorisation the cost is not covered for: staying overnight in hospital.", "source": "plan documents"},
        {"topic": "Rehabilitation", "detail": "Limited to 30 days per policy year. Requires pre-authorisation."},
        {"topic": "Out-patient annual cap", "detail": "All out-patient day-to-day care is capped at EUR 9,400 per person per year."},
        {"topic": "Prescribed medicines", "detail": "Up to EUR 1,250 per policy year."},
        {"topic": "Consultation visits", "detail": "15 consultations per policy year for each of specialists and nurses."},
    ]}
    cons = _plan_narrative_from_verified_facts(plan)["considerations"]
    assert cons[0].startswith("Pre-authorisation: Without pre-authorisation")
    assert not any(c.startswith("Rehabilitation") for c in cons)
    assert any("1,250" in c for c in cons) and any("9,400" in c for c in cons)


def test_medicines_cap_outranks_passing_outpatient_maximum_mentions():
    plan = {"benefits": {}, "critical_limitations": [
        {"topic": "Pre-authorisation", "detail": "Without pre-authorisation the cost is not covered for: staying overnight in hospital.", "source": "plan documents"},
        {"topic": "Out-patient annual maximum", "detail": "All out-patient day-to-day care benefits share an annual maximum of EUR 9,400 per person."},
        {"topic": "Specialist/doctor consultations", "detail": "Limited to 15 consultations per policy year, within the out-patient maximum."},
        {"topic": "Qualified nurse visits", "detail": "Limited to 15 consultations per policy year, within the out-patient maximum."},
        {"topic": "Out-patient mental health", "detail": "Limited to 15 visits per policy year, within the out-patient maximum."},
        {"topic": "Prescribed medicines", "detail": "Out-patient prescribed medicines and dressings are capped at EUR 1,250 per policy year."},
    ]}
    cons = _plan_narrative_from_verified_facts(plan)["considerations"]
    assert [c.split(":")[0] for c in cons] == [
        "Pre-authorisation", "Out-patient annual maximum", "Prescribed medicines", "Specialist/doctor consultations",
    ]


def test_extraction_mechanics_are_not_shown_to_the_client():
    from core.client_analysis import client_facing_results
    text = ("Included per the quote's Essential benefit overview (quote p.1, p.4). The Essential selection cell did not "
            "extract as text, so confirm on the Membership Certificate. Limits: routine pregnancy €4,000 per pregnancy.")
    results = [{"analysis": {"benefits": {"maternity": text, "dental": "80% within €1,000."}}}]
    clean = client_facing_results(results)[0]["analysis"]["benefits"]
    assert "extract" not in clean["maternity"] and "€4,000" in clean["maternity"]
    assert results[0]["analysis"]["benefits"]["maternity"] == text  # stored analysis untouched


APRIL_TWO_PLAN_QUOTE = """Summary of your selection

                                         Essential                     Extensive

 Healthcare benefits                                €478,66 /month                         €533,53/month

 Dental/Optical                                         Not selected                              Not selected

 Monthly Premium*                                     €478,91 Incl Tax                           €533,78 Incl Tax

 Annual Premium*                                  €5746,97 Incl Tax                          €6405,41 Incl Tax
"""


def test_side_by_side_quote_takes_the_target_plans_column():
    from core.analyzer import _apply_deterministic_facts
    from core.carriers import plan_column_facts
    assert plan_column_facts(APRIL_TWO_PLAN_QUOTE, "Extensive")["premium"]["amount"] == "6405.41"
    assert plan_column_facts(APRIL_TWO_PLAN_QUOTE, "ESSENTIAL")["premium"]["amount"] == "5746.97"
    assert plan_column_facts(APRIL_TWO_PLAN_QUOTE, "Elite") == {}
    out = _apply_deterministic_facts({"benefits": {}}, "APRIL", APRIL_TWO_PLAN_QUOTE, "", "Extensive")
    assert out["premium"]["amount"] == "6405.41"


def test_same_plan_quoted_twice_gets_distinct_names():
    from core.case_runner import disambiguate_plan_names
    rows = [
        {"provider": "APRIL MYHEALTH ESSENTIAL", "target_plan": "ESSENTIAL", "analysis": {
            "provider": "APRIL International", "plan_name": "MyHealth International – Essential",
            "benefits": {"maternity": "Included: €4,000 per pregnancy", "dental": "€1,000 at 80%", "optical": "€200"}}},
        {"provider": "APRIL MYHEALTH ESSENTIAL - CORE", "target_plan": "Essential", "analysis": {
            "provider": "APRIL International (MyHealth International)", "plan_name": "MyHealth International 2.0 – Essential",
            "benefits": {"maternity": "Not selected on this quotation.", "dental": "Not selected", "optical": "Not selected"}}},
        {"provider": "APRIL MYHEALTH EXTENSIVE", "target_plan": "Extensive", "analysis": {
            "provider": "APRIL International", "plan_name": "MyHealth International – Extensive", "benefits": {}}},
    ]
    disambiguate_plan_names(rows)
    names = [r["analysis"]["plan_name"] for r in rows]
    assert names == [
        "MyHealth International – Essential + Maternity + Dental + Optical",
        "MyHealth International – Essential (core cover)",
        "MyHealth International – Extensive",
    ]
    disambiguate_plan_names(rows)  # a second pass does not stack suffixes
    assert [r["analysis"]["plan_name"] for r in rows] == names
