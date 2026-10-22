"""Render the reply for a saved lead (or pasted text) as HTML, plain text and PDF.

    python render_lead.py core/lead_examples/lead_001_family_vouliagmeni.json --name Julian --family
    python render_lead.py lead.txt --name "Rajesh and Erica" --out replies/
"""
import argparse
import json
from pathlib import Path

from core.lead_email import embedded_fonts_css, render_html, render_pdf, render_text
from core.lead_router import route

ap = argparse.ArgumentParser()
ap.add_argument("lead", help="a lead JSON from core/lead_examples, or a .txt with the lead's message")
ap.add_argument("--name", default="")
ap.add_argument("--family", action="store_true")
ap.add_argument("--out", default=".")
ap.add_argument("--no-pdf", action="store_true")
a = ap.parse_args()

src = Path(a.lead)
text = json.loads(src.read_text(encoding="utf-8"))["lead_text"] if src.suffix == ".json" else src.read_text(encoding="utf-8")
r = route(text)
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
stem = out / f"email_{src.stem}"
stem.with_suffix(".html").write_text(render_html(r, a.name, a.family), encoding="utf-8")
stem.with_suffix(".txt").write_text(render_text(r, a.name, a.family), encoding="utf-8")
if not a.no_pdf:
    render_pdf(render_html(r, a.name, a.family, fonts_css=embedded_fonts_css()), stem.with_suffix(".pdf"))
print("wrote", *sorted(p.name for p in out.glob(stem.name + ".*")))
