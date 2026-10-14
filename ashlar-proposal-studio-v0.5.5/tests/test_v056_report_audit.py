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
