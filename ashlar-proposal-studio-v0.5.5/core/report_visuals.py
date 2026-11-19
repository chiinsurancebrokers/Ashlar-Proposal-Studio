"""Photo bands for the client report page.

The photos live in the Ashlar WordPress media library and load from there when
the report is opened. They carry no figures: every number and every statement
on the page still comes from the extracted quotes. Turn them off with
REPORT_PHOTOS=0, or point a slot elsewhere by editing PHOTOS.
"""
from __future__ import annotations

import os
from html import escape

_BASE = "https://ashlarassurance.com/wp-content/uploads"

# slot -> (url, alt text). Plain descriptions of the picture, not of the plans.
PHOTOS: dict[str, tuple[str, str]] = {
    "hero": (
        f"{_BASE}/2026/09/ElevenLabs_image_seedream-5-pro_Editorial-lifes_2026-09-26T17_28_40.png",
        "A family having breakfast together on a sunny terrace",
    ),
    "area": (
        f"{_BASE}/2026/09/family.jpg",
        "A traveller looking out over a harbour at sunset",
    ),
    "care": (
        f"{_BASE}/2026/09/ElevenLabs_image_seedream-5-pro_Editorial-photo_2026-09-26T17_28_22.png",
        "A couple talking with their doctor",
    ),
    "advice": (
        f"{_BASE}/2026/10/content-5.png",
        "A broker going through paperwork with a family",
    ),
}

BAND_CSS = """
.band{margin:0; border-top:1px solid var(--mortar); background:var(--paper-fine); line-height:0}
.band img{display:block; width:100%; max-height:clamp(150px,26vw,340px); object-fit:cover; object-position:50% 38%}
@media print{.band{display:none}}
"""


def enabled() -> bool:
    return os.environ.get("REPORT_PHOTOS", "1").strip().lower() not in {"0", "false", "no", "off"}


def photo_band(slot: str) -> str:
    """One full-width photo band, or an empty string when photos are off.

    A photo that fails to load removes itself, so a missing image never leaves
    a broken-picture icon in a client document."""
    if not enabled() or slot not in PHOTOS:
        return ""
    url, alt = PHOTOS[slot]
    return (
        "<figure class='band'>"
        f"<img src='{escape(url, quote=True)}' alt='{escape(alt, quote=True)}' "
        "loading='lazy' decoding='async' onerror=\"this.parentNode.remove()\">"
        "</figure>"
    )
