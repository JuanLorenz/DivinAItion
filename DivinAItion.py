import base64
import html as html_lib
import json
import os
import random
import re
from bisect import bisect
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from openai import OpenAI
from supabase import Client, create_client

st.set_page_config(page_title="DivinAItion", layout="wide")


def get_zodiac_from_birthdate(birthdate_str: str) -> str:
    _, month_str, day_str = birthdate_str.split("-")
    return calculate_zodiac(int(month_str), int(day_str))


def calculate_zodiac(month: int, day: int) -> str:
    cutoffs = [120, 219, 321, 420, 521, 621, 723, 823, 923, 1023, 1122, 1222]
    signs = [
        "Capricorn",
        "Aquarius",
        "Pisces",
        "Aries",
        "Taurus",
        "Gemini",
        "Cancer",
        "Leo",
        "Virgo",
        "Libra",
        "Scorpio",
        "Sagittarius",
        "Capricorn",
    ]
    date_num = month * 100 + day
    return signs[bisect(cutoffs, date_num)]


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_API_KEY"),
)

client = OpenAI(
    api_key=os.getenv("AI_API_KEY"),
    base_url=os.getenv("BASE_URL"),
)

prompt_path = Path(__file__).parent / "system_prompt.txt"
SYSTEM_PROMPT = prompt_path.read_text(encoding="utf-8").strip()


def find_asset(*relative_paths: str) -> Path | None:
    for root in (BASE_DIR, BASE_DIR.parent):
        for rel in relative_paths:
            candidate = root / rel
            if candidate.exists():
                return candidate
    return None


def to_data_uri(*relative_paths: str) -> str | None:
    path = find_asset(*relative_paths)
    if not path:
        return None
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def load_text_asset(*relative_paths: str) -> str:
    path = find_asset(*relative_paths)
    if not path:
        raise FileNotFoundError(f"Could not find any of {relative_paths} under {BASE_DIR}")
    return path.read_text(encoding="utf-8")


def attach_card_image(card: dict) -> dict:
    """Embed static/images/card/<id>.png as a base64 data URI so it always loads inside Streamlit's iframe."""
    img_uri = to_data_uri(f"static/images/card/{card['id']}.png")
    if img_uri:
        card["image_url"] = img_uri
    return card


def one_card():
    card_id = random.randint(0, 77)
    is_reverse = bool(random.randint(0, 1))
    meaning_col = "reversed_meaning" if is_reverse else "upright_meaning"

    response = (
        supabase.table("tarot_cards")
        .select(f"id, card_name, {meaning_col}")
        .eq("id", card_id)
        .execute()
    )

    if response.data:
        card = response.data[0]
        return attach_card_image({
            "id": card["id"],
            "card_name": card["card_name"],
            "is_reverse": is_reverse,
            "meaning": card[meaning_col],
        })
    return None


def three_card():
    card_ids = random.sample(range(0, 78), 3)

    response = (
        supabase.table("tarot_cards")
        .select("id, card_name, upright_meaning, reversed_meaning")
        .in_("id", card_ids)
        .execute()
    )

    rows_by_id = {row["id"]: row for row in response.data}
    drawn_cards = []

    for cid in card_ids:
        row = rows_by_id.get(cid)
        if row:
            is_reverse = bool(random.randint(0, 1))
            drawn_cards.append(attach_card_image({
                "id": cid,
                "card_name": row["card_name"],
                "is_reverse": is_reverse,
                "meaning": row["reversed_meaning"] if is_reverse else row["upright_meaning"],
            }))

    return drawn_cards


def celtic_cross():
    card_ids = random.sample(range(0, 78), 10)

    response = (
        supabase.table("tarot_cards")
        .select("id, card_name, upright_meaning, reversed_meaning")
        .in_("id", card_ids)
        .execute()
    )

    rows_by_id = {row["id"]: row for row in response.data}
    drawn_cards = []

    for cid in card_ids:
        row = rows_by_id.get(cid)
        if row:
            is_reverse = bool(random.randint(0, 1))
            drawn_cards.append(attach_card_image({
                "id": cid,
                "card_name": row["card_name"],
                "is_reverse": is_reverse,
                "meaning": row["reversed_meaning"] if is_reverse else row["upright_meaning"],
            }))

    return drawn_cards


SPREAD_POSITIONS = {
    "One Card Pull": ["Focal Insight"],
    "Three Card Spread": ["Past", "Present", "Future"],
    "Celtic Cross Spread": [
        "Present",
        "Challenge",
        "Foundation",
        "Recent Past",
        "Crowning",
        "Near Future",
        "Self",
        "Environment",
        "Hopes & Fears",
        "Outcome",
    ],
}

CONTEXT_HINT_PATTERNS = [
    r"\b(?:provide|share|give|tell)\b.{0,30}\b(?:context|details|more|dilemma|situation|story)\b",
    r"\b(?:lack(?:s|ing)?|missing|without|no)\s+(?:life\s+)?context\b",
    r"\btoo\s+vague\b",
    r"\bwhat(?:'s| is)\s+(?:going on|happening|troubling|on your mind)\b",
    r"\bneed(?:s)?\s+(?:more\s+)?context\b",
    r"\bgive me something to work with\b",
    r"\bcan(?:'t| not)\s+read\s+(?:a\s+blank|nothing|your mind)\b",
]


def looks_like_lacking_context(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    return any(re.search(pat, lower) for pat in CONTEXT_HINT_PATTERNS)


def _clean_single_paragraph(text: str) -> str:
    return re.sub(r"\s*\n+\s*", " ", str(text or "")).strip()


def _strip_card_prefix(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(
        r"^(?:#+\s*)?(?:\*\*)?(?:card\s*)?(?:\d{1,2}|X|IX|IV|V?I{1,3})\s*(?:[.):]|[-—–]\s)\s*(?:\*\*)?",
        "",
        cleaned,
        count=1,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _extract_json_object(raw_text: str) -> dict | None:
    if not raw_text:
        return None
    text = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()
    else:
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def parse_llm_output(raw_text: str, cards: list[dict]) -> dict:
    """
    Parse AI output into either:
      - {"status": "modal", "message": "..."} when context is lacking or security refusal triggers
      - {"status": "ok", "interpretations": [...], "summary": "..."} mapped 1:1 to drawn cards
    """
    expected_count = len(cards)
    raw = (raw_text or "").strip()

    if "beyond my capabilities as a tarot reader" in raw.lower():
        return {"status": "modal", "message": "That goes beyond my capabilities as a tarot reader~"}

    data = _extract_json_object(raw)
    if data is not None:
        if data.get("refusal"):
            return {"status": "modal", "message": str(data["refusal"]).strip()}

        if data.get("needs_context") or data.get("lacks_context"):
            msg = (
                str(data.get("context_message") or data.get("message") or "").strip()
                or "The cosmos needs a little more to work with—share what is actually stirring in your life!"
            )
            return {"status": "modal", "message": msg}

        raw_cards = data.get("cards")
        if isinstance(raw_cards, list):
            # Sort by position if provided, otherwise preserve order
            if all(isinstance(item, dict) and item.get("position") is not None for item in raw_cards):
                raw_cards = sorted(raw_cards, key=lambda item: int(item.get("position", 0)))

            interps = []
            for item in raw_cards:
                if isinstance(item, dict):
                    val = (
                        item.get("interpretation")
                        or item.get("meaning")
                        or item.get("text")
                        or ""
                    )
                else:
                    val = str(item or "")
                cleaned = _clean_single_paragraph(val)
                if cleaned:
                    interps.append(cleaned)

            if not interps:
                fallback_msg = str(data.get("context_message") or data.get("message") or "").strip()
                if fallback_msg:
                    return {"status": "modal", "message": fallback_msg}

            if len(interps) < expected_count and interps and looks_like_lacking_context(interps[0]):
                return {"status": "modal", "message": interps[0]}

            if len(interps) == 1 and expected_count == 1 and looks_like_lacking_context(interps[0]):
                return {"status": "modal", "message": interps[0]}

            summary = str(data.get("summary") or "").strip()
            if expected_count == 1:
                summary = ""

            while len(interps) < expected_count:
                idx = len(interps)
                interps.append(cards[idx].get("meaning", ""))

            return {
                "status": "ok",
                "interpretations": interps[:expected_count],
                "summary": summary,
            }

    # Plain-text fallback if model returned non-JSON prose
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
    if len(paragraphs) < expected_count:
        by_line = [p.strip() for p in re.split(r"\n+", raw) if p.strip()]
        if len(by_line) > len(paragraphs):
            paragraphs = by_line

    if paragraphs and (
        (len(paragraphs) <= 2 and len(paragraphs) < expected_count and looks_like_lacking_context(" ".join(paragraphs)))
        or (expected_count == 1 and looks_like_lacking_context(" ".join(paragraphs)))
    ):
        return {"status": "modal", "message": "\n\n".join(paragraphs)}

    cleaned_paras = [_clean_single_paragraph(_strip_card_prefix(p)) for p in paragraphs if _strip_card_prefix(p)]
    interps = cleaned_paras[:expected_count]
    summary = "\n\n".join(cleaned_paras[expected_count:]).strip() if expected_count > 1 else ""

    while len(interps) < expected_count:
        idx = len(interps)
        interps.append(cards[idx].get("meaning", ""))

    return {
        "status": "ok",
        "interpretations": interps,
        "summary": summary,
    }


def get_llm_interpretation(
    cards: list[dict],
    spread_name: str,
    zodiac_sign: str,
    user_question: str,
) -> str:
    positions = SPREAD_POSITIONS.get(spread_name, [])
    card_lines = []
    for idx, c in enumerate(cards, start=1):
        orientation = "Reversed" if c["is_reverse"] else "Upright"
        pos_label = f" [{positions[idx - 1]}]" if idx - 1 < len(positions) else ""
        card_lines.append(
            f"{idx}.{pos_label} {c['card_name']} ({orientation}) — Reference meaning: {c['meaning']}"
        )

    user_prompt = (
        f"Zodiac Sign: {zodiac_sign}\n"
        f"Spread: {spread_name}\n"
        f"User Question / Life Context: {user_question}\n"
        "Cards drawn:\n"
        + "\n".join(card_lines)
        + "\n\nRespond strictly with the JSON schema defined in the system instructions."
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = client.chat.completions.create(
            model="gpt-6-luna",
            messages=messages,
            response_format={"type": "json_object"},
            max_completion_tokens=1800,
        )
    except Exception:
        response = client.chat.completions.create(
            model="gpt-6-luna",
            messages=messages,
            max_completion_tokens=1800,
        )

    return response.choices[0].message.content or ""


def apply_parsed_reading_to_cards(
    cards: list[dict],
    parsed: dict,
    spread_mode: str,
) -> tuple[list[dict], str]:
    """Attach each parsed meaning directly onto its card and build aligned llm_response for summary views."""
    interps = parsed["interpretations"]
    summary = parsed.get("summary", "").strip()

    updated_cards = []
    for idx, card in enumerate(cards):
        card_copy = dict(card)
        card_copy["llm_interpretation"] = interps[idx] if idx < len(interps) else card.get("meaning", "")
        updated_cards.append(card_copy)

    if spread_mode == "three_card":
        parts = [f"{i + 1}. {c['llm_interpretation']}" for i, c in enumerate(updated_cards)]
        if summary:
            parts.append(summary)
        llm_response = "\n\n".join(parts)
    elif spread_mode == "celtic_cross":
        parts = [c["llm_interpretation"] for c in updated_cards]
        if summary:
            parts.append(summary)
        llm_response = "\n\n".join(parts)
    else:
        llm_response = updated_cards[0]["llm_interpretation"] if updated_cards else ""

    return updated_cards, llm_response


def extract_between(text: str, start_marker: str, end_marker: str) -> str:
    pattern = re.escape(start_marker) + r"(.*?)" + re.escape(end_marker)
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


def load_curtain_parts() -> tuple[str, str, str]:
    raw = load_text_asset("testing/correct_curtains.html", "correct_curtains.html", "curtains.html")
    curtain_style = extract_between(raw, "<!--__CURTAINS_STYLE_START__-->", "<!--__CURTAINS_STYLE_END__-->")
    curtain_html = extract_between(raw, "<!--__CURTAINS_HTML_START__-->", "<!--__CURTAINS_HTML_END__-->")
    curtain_script = extract_between(raw, "<!--__CURTAINS_SCRIPT_START__-->", "<!--__CURTAINS_SCRIPT_END__-->")

    if not curtain_style:
        m = re.search(r"<style>.*?</style>", raw, re.DOTALL)
        curtain_style = m.group(0) if m else ""
    if not curtain_html:
        m = re.search(r'(<div class="curtain-stage".*?</div>)', raw, re.DOTALL)
        curtain_html = m.group(1) if m else ""
    if not curtain_script:
        m = re.search(r"<script>.*?</script>", raw, re.DOTALL)
        curtain_script = m.group(0) if m else ""

    # Strip global html/body resets when embedding into other pages
    curtain_style = re.sub(r"html,\s*body\s*\{[^}]*\}", "", curtain_style, flags=re.DOTALL)
    return curtain_style, curtain_html, curtain_script


def build_local_fonts_css() -> tuple[str, str]:
    """Load any custom fonts in static/fonts/ as @font-face rules and return CSS + primary script family."""
    fonts_dir = find_asset("static/fonts")
    mime_map = {
        ".woff2": ("font/woff2", "woff2"),
        ".woff": ("font/woff", "woff"),
        ".ttf": ("font/ttf", "truetype"),
        ".otf": ("font/opentype", "opentype"),
    }
    rules = []
    script_family = None

    if fonts_dir and fonts_dir.is_dir():
        for font_path in sorted(fonts_dir.iterdir()):
            ext = font_path.suffix.lower()
            if ext in mime_map:
                mime, fmt = mime_map[ext]
                b64 = base64.b64encode(font_path.read_bytes()).decode("ascii")
                fam_name = f"LocalFont_{re.sub(r'[^a-zA-Z0-9]', '_', font_path.stem)}"
                rules.append(
                    f"@font-face {{ font-family: '{fam_name}'; src: url('data:{mime};base64,{b64}') format('{fmt}'); font-display: swap; }}"
                )
                lower_stem = font_path.stem.lower()
                if script_family is None or any(k in lower_stem for k in ("script", "cursive", "vibes", "brush", "callig", "edward", "pinyon")):
                    script_family = f"'{fam_name}'"

    script_stack = f"{script_family}, 'Great Vibes', 'Cormorant Garamond', Georgia, serif" if script_family else "'Great Vibes', 'Cormorant Garamond', Georgia, serif"
    return "\n".join(rules), script_stack


def build_soul_prompt_html(
    spread_label: str,
    zodiac_sign: str,
    render_seq: int,
    modal_message: str = "",
    prefill_question: str = "",
    error_message: str = "",
) -> str:
    css = load_text_asset("static/css/style.css")
    bg_html = load_text_asset("static/templates/background_animation.html", "background_animation.html")
    curtain_style, curtain_html, curtain_script = load_curtain_parts()
    local_fonts_css, script_stack = build_local_fonts_css()

    skip_curtains = bool(modal_message or error_message)
    pending_script = "" if skip_curtains else "<script>document.documentElement.classList.add('curtain-pending');</script>"
    escaped_spread = html_lib.escape(spread_label)
    escaped_zodiac = html_lib.escape(zodiac_sign)
    escaped_prefill = html_lib.escape(prefill_question)
    escaped_error = html_lib.escape(error_message)
    modal_body_html = "<br />".join(html_lib.escape(line) for line in modal_message.splitlines()) if modal_message else ""
    cue_hidden_class = " is-hidden" if skip_curtains else ""
    modal_visible_class = " is-visible" if modal_message else ""

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>What Stirs Within Your Soul? · DivinAItion</title>
  {pending_script}
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500;1,600&family=Great+Vibes&family=Plus+Jakarta+Sans:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
    {local_fonts_css}
    {css}
  </style>
  {curtain_style}
  <style>
    html, body {{
      width: 100%;
      height: 100%;
      margin: 0;
      padding: 0;
      overflow: hidden;
      background: #020524;
    }}

    html.curtain-pending .soul-screen,
    html.curtain-pending #starfieldMount,
    html.curtain-pending .starfield-bg {{
      opacity: 0 !important;
      visibility: hidden !important;
    }}

    .curtain-stage:not(.is-curtain-ready) {{
      background: radial-gradient(circle at 50% 45%, #120e44 0%, #060722 70%, #030416 100%);
    }}

    .curtain-cue {{
      position: fixed;
      inset: 0;
      z-index: 58;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      pointer-events: none;
      transition: opacity 420ms ease;
    }}

    .curtain-cue.is-hidden {{
      opacity: 0;
    }}

    .curtain-cue-title {{
      margin: 0;
      font-family: "Cormorant Garamond", Georgia, serif;
      font-style: italic;
      font-weight: 600;
      font-size: clamp(1.5rem, 3.2vw, 2.25rem);
      letter-spacing: 0.04em;
      color: #fef3c7;
      text-shadow: 0 2px 18px rgba(0, 0, 0, 0.85), 0 0 24px rgba(253, 230, 138, 0.45);
      animation: cuePulse 2.4s ease-in-out infinite;
    }}

    .curtain-cue-sub {{
      margin: 10px 0 0;
      font-family: "Plus Jakarta Sans", system-ui, sans-serif;
      font-size: 11px;
      letter-spacing: 0.22em;
      text-transform: uppercase;
      color: rgba(226, 232, 240, 0.72);
    }}

    @keyframes cuePulse {{
      0%, 100% {{ opacity: 0.72; }}
      50% {{ opacity: 1; }}
    }}

    .soul-screen {{
      position: fixed;
      inset: 0;
      z-index: 15;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px 20px 36px;
      transition: opacity 520ms ease, transform 520ms cubic-bezier(0.22, 1, 0.36, 1);
    }}

    .soul-screen.is-leaving {{
      opacity: 0;
      transform: translateY(-10px) scale(0.985);
      pointer-events: none;
    }}

    .soul-heading {{
      margin: 0 0 clamp(22px, 3.8vh, 36px);
      text-align: center;
      font-family: "Cormorant Garamond", Georgia, serif;
      font-weight: 600;
      font-size: clamp(2.15rem, 5.2vw, 3.75rem);
      line-height: 1.15;
      letter-spacing: 0.02em;
      color: #ecfa8c;
      text-shadow:
        0 0 12px rgba(236, 250, 140, 0.72),
        0 0 28px rgba(210, 238, 108, 0.44),
        0 0 54px rgba(170, 210, 80, 0.24);
      user-select: none;
    }}

    .soul-cap {{
      font-family: {script_stack};
      font-size: 1.32em;
      font-weight: 400;
      display: inline-block;
      margin-right: 0.02em;
      vertical-align: baseline;
    }}

    .soul-box {{
      position: relative;
      width: min(560px, 88vw);
      height: min(260px, 37dvh);
      min-height: 170px;
      border-radius: 18px;
      border: 3px solid #f0d078;
      background: linear-gradient(
        180deg,
        rgba(14, 10, 74, 0.90) 0%,
        rgba(10, 9, 32, 0.94) 52%,
        rgba(46, 12, 78, 0.90) 100%
      );
      box-shadow:
        0 24px 60px rgba(0, 0, 0, 0.62),
        0 0 26px rgba(240, 208, 120, 0.16),
        inset 0 0 24px rgba(240, 208, 120, 0.07);
      padding: 18px 22px;
      display: flex;
      flex-direction: column;
      transition: border-color 220ms ease, box-shadow 220ms ease, transform 220ms ease;
    }}

    .soul-box:focus-within {{
      border-color: #fde68a;
      box-shadow:
        0 26px 64px rgba(0, 0, 0, 0.68),
        0 0 36px rgba(251, 191, 36, 0.28),
        inset 0 0 26px rgba(253, 230, 138, 0.10);
    }}

    .soul-box.is-nudged {{
      animation: boxNudge 380ms ease;
      border-color: #fca5a5;
    }}

    @keyframes boxNudge {{
      0%, 100% {{ transform: translateX(0); }}
      25% {{ transform: translateX(-6px); }}
      75% {{ transform: translateX(6px); }}
    }}

    .soul-textarea {{
      width: 100%;
      flex: 1;
      resize: none;
      border: 0;
      outline: none;
      background: transparent;
      color: #fef9e7;
      font-family: "Cormorant Garamond", Georgia, serif;
      font-size: clamp(1.15rem, 2.2vw, 1.45rem);
      line-height: 1.55;
      letter-spacing: 0.015em;
    }}

    .soul-textarea::placeholder {{
      color: rgba(226, 232, 240, 0.42);
      font-style: italic;
    }}

    .soul-hint {{
      margin-top: 14px;
      font-size: 12px;
      letter-spacing: 0.06em;
      color: rgba(253, 230, 138, 0.68);
      text-align: center;
      user-select: none;
    }}

    .soul-error {{
      min-height: 20px;
      margin: 8px 0 0;
      font-size: 13px;
      font-weight: 500;
      color: #fca5a5;
      text-align: center;
      opacity: 0;
      transform: translateY(3px);
      transition: opacity 200ms ease, transform 200ms ease;
    }}

    .soul-error.is-visible {{
      opacity: 1;
      transform: translateY(0);
    }}

    /* Context Required Modal */
    .context-modal-backdrop {{
      position: fixed;
      inset: 0;
      z-index: 70;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      background: rgba(2, 5, 36, 0.72);
      backdrop-filter: blur(8px);
      -webkit-backdrop-filter: blur(8px);
      opacity: 0;
      pointer-events: none;
      transition: opacity 280ms ease;
    }}

    .context-modal-backdrop.is-visible {{
      opacity: 1;
      pointer-events: auto;
    }}

    .context-modal {{
      width: min(470px, 92vw);
      border-radius: 20px;
      border: 2px solid rgba(240, 208, 120, 0.78);
      background: linear-gradient(
        180deg,
        rgba(18, 13, 76, 0.96) 0%,
        rgba(11, 10, 38, 0.98) 56%,
        rgba(44, 12, 74, 0.96) 100%
      );
      box-shadow:
        0 28px 70px rgba(0, 0, 0, 0.78),
        0 0 38px rgba(251, 191, 36, 0.24),
        inset 0 0 24px rgba(253, 230, 138, 0.08);
      padding: 28px 26px 24px;
      text-align: center;
      transform: translateY(12px) scale(0.96);
      transition: transform 320ms cubic-bezier(0.22, 1, 0.36, 1);
    }}

    .context-modal-backdrop.is-visible .context-modal {{
      transform: translateY(0) scale(1);
    }}

    .context-modal-star {{
      width: 34px;
      height: 34px;
      margin: 0 auto 12px;
      background: linear-gradient(135deg, #fffbeb 0%, #fde68a 55%, #c4b5fd 100%);
      clip-path: polygon(
        50% 0%, 57% 35%, 64% 43%, 100% 50%,
        64% 57%, 57% 65%, 50% 100%, 43% 65%,
        36% 57%, 0% 50%, 36% 43%, 43% 35%
      );
      filter: drop-shadow(0 0 12px rgba(253, 230, 138, 0.75));
    }}

    .context-modal-title {{
      margin: 0;
      font-family: "Cormorant Garamond", Georgia, serif;
      font-style: italic;
      font-weight: 600;
      font-size: clamp(1.55rem, 3vw, 2rem);
      color: #ecfa8c;
      text-shadow: 0 0 16px rgba(236, 250, 140, 0.45);
    }}

    .context-modal-body {{
      margin: 14px 0 22px;
      font-size: 15px;
      line-height: 1.65;
      color: rgba(241, 245, 249, 0.95);
    }}

    .context-modal-btn {{
      min-width: 190px;
      min-height: 44px;
      padding: 10px 24px;
      border-radius: 999px;
      font-size: 13.5px;
      font-weight: 600;
      letter-spacing: 0.04em;
    }}

    /* Mystical Loading Buffer */
    .mystic-loader {{
      position: fixed;
      inset: 0;
      z-index: 35;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 24px;
      opacity: 0;
      pointer-events: none;
      transition: opacity 600ms ease;
      background: radial-gradient(circle at center, rgba(28, 14, 72, 0.42) 0%, rgba(2, 5, 36, 0.35) 65%, transparent 100%);
    }}

    .mystic-loader.is-visible {{
      opacity: 1;
      pointer-events: auto;
    }}

    .mystic-sigil {{
      position: relative;
      width: 168px;
      height: 168px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 28px;
    }}

    .mystic-aura {{
      position: absolute;
      inset: -18px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(253, 230, 138, 0.32) 0%, rgba(139, 92, 246, 0.24) 45%, transparent 72%);
      filter: blur(16px);
      animation: auraPulse 2.8s ease-in-out infinite;
    }}

    .mystic-ring-outer {{
      position: absolute;
      inset: 0;
      border-radius: 50%;
      border: 1.5px solid rgba(253, 230, 138, 0.65);
      box-shadow: 0 0 24px rgba(251, 191, 36, 0.25);
      animation: spinCw 12s linear infinite;
    }}

    .mystic-ring-outer::before,
    .mystic-ring-outer::after {{
      content: "";
      position: absolute;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #fef3c7;
      box-shadow: 0 0 12px #fde68a, 0 0 24px #fbbf24;
      top: -4px;
      left: 50%;
      transform: translateX(-50%);
    }}

    .mystic-ring-outer::after {{
      top: auto;
      bottom: -4px;
    }}

    .mystic-ring-inner {{
      position: absolute;
      inset: 18px;
      border-radius: 50%;
      border: 1px dashed rgba(196, 181, 253, 0.62);
      animation: spinCcw 8.5s linear infinite;
    }}

    .mystic-star {{
      width: 58px;
      height: 58px;
      background: linear-gradient(135deg, #fffbeb 0%, #fde68a 50%, #c4b5fd 100%);
      clip-path: polygon(
        50% 0%, 57% 35%, 64% 43%, 100% 50%,
        64% 57%, 57% 65%, 50% 100%, 43% 65%,
        36% 57%, 0% 50%, 36% 43%, 43% 35%
      );
      filter: drop-shadow(0 0 18px rgba(253, 230, 138, 0.85));
      animation: starBeat 2.4s ease-in-out infinite;
    }}

    .mystic-text {{
      margin: 0;
      font-family: "Cormorant Garamond", Georgia, serif;
      font-style: italic;
      font-weight: 600;
      font-size: clamp(1.65rem, 3.4vw, 2.35rem);
      letter-spacing: 0.04em;
      color: #fef3c7;
      text-align: center;
      text-shadow: 0 0 20px rgba(253, 230, 138, 0.55), 0 0 42px rgba(167, 139, 250, 0.35);
      animation: textShimmer 2.6s ease-in-out infinite;
    }}

    .mystic-subtext {{
      margin: 10px 0 0;
      font-size: 13px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: rgba(203, 213, 225, 0.80);
      text-align: center;
    }}

    @keyframes spinCw {{
      to {{ transform: rotate(360deg); }}
    }}
    @keyframes spinCcw {{
      to {{ transform: rotate(-360deg); }}
    }}
    @keyframes auraPulse {{
      0%, 100% {{ transform: scale(0.92); opacity: 0.72; }}
      50% {{ transform: scale(1.12); opacity: 1; }}
    }}
    @keyframes starBeat {{
      0%, 100% {{ transform: scale(0.92) rotate(0deg); opacity: 0.88; }}
      50% {{ transform: scale(1.08) rotate(12deg); opacity: 1; }}
    }}
    @keyframes textShimmer {{
      0%, 100% {{ opacity: 0.82; }}
      50% {{ opacity: 1; }}
    }}
  </style>
</head>
<body>
  {curtain_html}
  <div class="curtain-cue{cue_hidden_class}" id="curtainCue" aria-hidden="true">
    <p class="curtain-cue-title">Click anywhere to part the veil</p>
    <p class="curtain-cue-sub">{escaped_spread} &middot; {escaped_zodiac}</p>
  </div>
  {curtain_script}
  <script>
    (function () {{
      const SKIP_CURTAINS = {json.dumps(skip_curtains)};
      const curtainStage = document.getElementById('curtainStage');
      if (SKIP_CURTAINS) {{
        if (typeof window.setCurtainsOpen === 'function') {{
          window.setCurtainsOpen(true, true);
        }}
        if (curtainStage) {{
          curtainStage.classList.add('is-curtain-ready', 'is-curtain-tucked');
        }}
        document.documentElement.classList.remove('curtain-pending');
      }} else {{
        if (typeof window.setCurtainsOpen === 'function') {{
          window.setCurtainsOpen(false, true);
        }}
        requestAnimationFrame(() => {{
          if (curtainStage) curtainStage.classList.add('is-curtain-ready');
          document.documentElement.classList.remove('curtain-pending');
        }});
      }}
    }})();
  </script>

  <!-- render_seq: {render_seq} -->
  {bg_html}

  <main class="soul-screen" id="soulScreen">
    <h1 class="soul-heading">
      <span class="soul-cap">W</span>hat
      <span class="soul-cap">S</span>tirs
      <span class="soul-cap">W</span>ithin
      <span class="soul-cap">Y</span>our
      <span class="soul-cap">S</span>oul
      <span class="soul-cap">?</span>
    </h1>
    <div class="soul-box" id="soulBox">
      <textarea
        id="soulInput"
        class="soul-textarea"
        placeholder="Whisper your question or dilemma into the cosmos..."
        aria-label="What stirs within your soul?"
      >{escaped_prefill}</textarea>
    </div>
    <p class="soul-hint">Press Enter to cast your {escaped_spread} &middot; {escaped_zodiac}</p>
    <p class="soul-error{' is-visible' if escaped_error else ''}" id="soulError" role="alert">{escaped_error}</p>
  </main>

  <div class="context-modal-backdrop{modal_visible_class}" id="contextModalBackdrop" aria-hidden="{ 'false' if modal_message else 'true' }">
    <div class="context-modal" role="dialog" aria-modal="true" aria-labelledby="contextModalTitle">
      <div class="context-modal-star" aria-hidden="true"></div>
      <h2 class="context-modal-title" id="contextModalTitle">The Cards Require Context</h2>
      <p class="context-modal-body" id="contextModalBody">{modal_body_html}</p>
      <button type="button" class="tarot-btn tarot-btn--primary context-modal-btn" id="contextModalBtn">
        Share More Context
      </button>
    </div>
  </div>

  <section class="mystic-loader" id="mysticLoader" aria-live="polite" aria-label="Calling the universe's response">
    <div class="mystic-sigil" aria-hidden="true">
      <div class="mystic-aura"></div>
      <div class="mystic-ring-outer"></div>
      <div class="mystic-ring-inner"></div>
      <div class="mystic-star"></div>
    </div>
    <p class="mystic-text">Calling the universe&rsquo;s response&hellip;</p>
    <p class="mystic-subtext">Aligning {escaped_spread} &middot; {escaped_zodiac}</p>
  </section>

  <script>
    (function () {{
      const SKIP_CURTAINS = {json.dumps(skip_curtains)};
      const HAS_MODAL = {json.dumps(bool(modal_message))};
      const curtainStage = document.getElementById('curtainStage');
      const curtainCue = document.getElementById('curtainCue');
      const soulScreen = document.getElementById('soulScreen');
      const soulBox = document.getElementById('soulBox');
      const soulInput = document.getElementById('soulInput');
      const soulError = document.getElementById('soulError');
      const mysticLoader = document.getElementById('mysticLoader');
      const contextModalBackdrop = document.getElementById('contextModalBackdrop');
      const contextModalBtn = document.getElementById('contextModalBtn');
      let hasUnveiled = SKIP_CURTAINS;
      let hasSubmitted = false;

      function focusSoulInputAtEnd() {{
        if (!soulInput) return;
        soulInput.focus();
        const len = soulInput.value.length;
        try {{
          soulInput.setSelectionRange(len, len);
        }} catch (_) {{}}
      }}

      function closeContextModal() {{
        if (!contextModalBackdrop) return;
        contextModalBackdrop.classList.remove('is-visible');
        contextModalBackdrop.setAttribute('aria-hidden', 'true');
        focusSoulInputAtEnd();
      }}

      if (HAS_MODAL && contextModalBtn) {{
        setTimeout(() => contextModalBtn.focus(), 60);
      }} else if (SKIP_CURTAINS) {{
        setTimeout(focusSoulInputAtEnd, 60);
      }}

      if (contextModalBtn) {{
        contextModalBtn.addEventListener('click', closeContextModal);
      }}
      if (contextModalBackdrop) {{
        contextModalBackdrop.addEventListener('click', (e) => {{
          if (e.target === contextModalBackdrop) {{
            closeContextModal();
          }}
        }});
      }}
      document.addEventListener('keydown', (e) => {{
        if (
          e.key === 'Escape' &&
          contextModalBackdrop &&
          contextModalBackdrop.classList.contains('is-visible')
        ) {{
          closeContextModal();
        }}
      }});

      function unveilPrompt() {{
        if (hasUnveiled) return;
        hasUnveiled = true;
        if (curtainCue) curtainCue.classList.add('is-hidden');

        if (typeof window.openCurtains === 'function') {{
          window.openCurtains();
        }}

        window.addEventListener('curtains:settled', (e) => {{
          if (e.detail && e.detail.isOpen && curtainStage) {{
            curtainStage.classList.add('is-curtain-tucked');
            focusSoulInputAtEnd();
          }}
        }}, {{ once: true }});

        setTimeout(focusSoulInputAtEnd, 700);

        setTimeout(() => {{
          if (curtainStage) curtainStage.classList.add('is-curtain-tucked');
          focusSoulInputAtEnd();
        }}, 2400);
      }}

      document.addEventListener('click', (e) => {{
        if (hasUnveiled) return;
        e.preventDefault();
        e.stopPropagation();
        unveilPrompt();
      }}, true);

      function submitToStreamlit(questionText) {{
        const parentDoc = window.parent && window.parent.document;
        if (!parentDoc) return;

        const inputEl = parentDoc.querySelector('input[aria-label="DIVINAITION_PROMPT_BRIDGE"]');
        if (inputEl) {{
          const proto = (window.parent && window.parent.HTMLInputElement)
            ? window.parent.HTMLInputElement.prototype
            : HTMLInputElement.prototype;
          const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
          nativeSetter.call(inputEl, questionText);
          inputEl.dispatchEvent(new Event('input', {{ bubbles: true }}));
          inputEl.dispatchEvent(new Event('change', {{ bubbles: true }}));
          inputEl.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }}));
          inputEl.blur();
        }}

        setTimeout(() => {{
          const buttons = parentDoc.querySelectorAll('button');
          for (const btn of buttons) {{
            if (btn.textContent && btn.textContent.trim() === 'DIVINAITION_SUBMIT_PROMPT') {{
              btn.click();
              break;
            }}
          }}
        }}, 140);
      }}

      soulInput.addEventListener('input', () => {{
        if (soulError) {{
          soulError.textContent = '';
          soulError.classList.remove('is-visible');
        }}
      }});

      soulInput.addEventListener('keydown', (e) => {{
        if (e.key === 'Enter' && !e.shiftKey) {{
          e.preventDefault();
          if (hasSubmitted) return;
          if (contextModalBackdrop && contextModalBackdrop.classList.contains('is-visible')) return;

          const text = soulInput.value.trim();
          if (!text) {{
            soulBox.classList.remove('is-nudged');
            void soulBox.offsetWidth;
            soulBox.classList.add('is-nudged');
            if (soulError) {{
              soulError.textContent = 'Please share a question or life context before invoking the cards.';
              soulError.classList.add('is-visible');
            }}
            focusSoulInputAtEnd();
            return;
          }}

          hasSubmitted = true;
          soulInput.blur();
          soulScreen.classList.add('is-leaving');
          setTimeout(() => {{
            mysticLoader.classList.add('is-visible');
          }}, 180);

          submitToStreamlit(text);
        }}
      }});
    }})();
  </script>
</body>
</html>
"""


def build_tarot_html(filename: str, payload: dict, spread_mode: str, render_seq: int) -> str:
    html = load_text_asset(f"static/templates/{filename}", filename)
    css = load_text_asset("static/css/style.css")
    bg_html = load_text_asset("static/templates/background_animation.html", "background_animation.html")
    curtain_style, curtain_html, curtain_script = load_curtain_parts()

    render_payload = {
        **payload,
        "card_back_url": payload.get("card_back_url") or to_data_uri("static/images/miscellaneous/TarotCard_Back.png"),
    }

    html = html.replace('<link rel="stylesheet" href="../css/style.css" />', f"<style>{css}</style>")
    html = html.replace('<link rel="stylesheet" href="static/css/style.css" />', f"<style>{css}</style>")
    html = html.replace("<!--__BACKGROUND_ANIMATION__-->", bg_html)
    html = html.replace("/*__TAROT_DATA__*/ null", json.dumps(render_payload))

    curtain_head_block = f"""
  <script>document.documentElement.classList.add('curtain-pending');</script>
  {curtain_style}
  <style>
    html.curtain-pending .tarot-app,
    html.curtain-pending #starfieldMount,
    html.curtain-pending .starfield-bg {{
      opacity: 0 !important;
      visibility: hidden !important;
    }}

    .curtain-stage:not(.is-curtain-ready) {{
      background: radial-gradient(circle at 50% 45%, #120e44 0%, #060722 70%, #030416 100%);
    }}

    .curtain-cue {{
      position: fixed;
      inset: 0;
      z-index: 58;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      pointer-events: none;
      transition: opacity 420ms ease;
    }}

    .curtain-cue.is-hidden {{
      opacity: 0;
    }}

    .curtain-cue-title {{
      margin: 0;
      font-family: "Cormorant Garamond", Georgia, serif;
      font-style: italic;
      font-weight: 600;
      font-size: clamp(1.5rem, 3.2vw, 2.25rem);
      letter-spacing: 0.04em;
      color: #fef3c7;
      text-shadow: 0 2px 18px rgba(0, 0, 0, 0.85), 0 0 24px rgba(253, 230, 138, 0.45);
      animation: cuePulse 2.4s ease-in-out infinite;
    }}

    @keyframes cuePulse {{
      0%, 100% {{ opacity: 0.72; }}
      50% {{ opacity: 1; }}
    }}

    .ask-another-btn {{
      position: fixed;
      right: 22px;
      bottom: 20px;
      z-index: 46;
      padding: 11px 22px;
      border-radius: 999px;
      border: 1px solid rgba(252, 211, 77, 0.58);
      background: linear-gradient(135deg, rgba(26, 18, 66, 0.92), rgba(56, 18, 92, 0.92));
      backdrop-filter: blur(10px);
      color: #fef3c7;
      font-family: "Plus Jakarta Sans", system-ui, sans-serif;
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.04em;
      cursor: pointer;
      box-shadow: 0 12px 28px rgba(0, 0, 0, 0.55), 0 0 22px rgba(251, 191, 36, 0.22);
      opacity: 0;
      transform: translateY(12px);
      pointer-events: none;
      transition: opacity 420ms ease, transform 420ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 200ms ease, border-color 200ms ease;
    }}

    .ask-another-btn.is-visible {{
      opacity: 1;
      transform: translateY(0);
      pointer-events: auto;
    }}

    .ask-another-btn:hover {{
      border-color: #fde68a;
      box-shadow: 0 14px 34px rgba(0, 0, 0, 0.62), 0 0 30px rgba(251, 191, 36, 0.42);
      transform: translateY(-2px);
    }}
  </style>
"""

    curtain_front_block = f"""
  <!-- render_seq: {render_seq} -->
  {curtain_html}
  <div class="curtain-cue" id="curtainCue" aria-hidden="true">
    <p class="curtain-cue-title">Click anywhere to unveil your reading</p>
  </div>
  {curtain_script}
  <script>
    (function () {{
      const curtainStage = document.getElementById('curtainStage');
      if (typeof window.setCurtainsOpen === 'function') {{
        window.setCurtainsOpen(false, true);
      }}
      requestAnimationFrame(() => {{
        if (curtainStage) curtainStage.classList.add('is-curtain-ready');
        document.documentElement.classList.remove('curtain-pending');
      }});
    }})();
  </script>
"""

    reading_bridge_block = f"""
  <button type="button" class="ask-another-btn" id="askAnotherBtn">
    Read Again
  </button>

  <script>
    (function () {{
      const SPREAD_MODE = {json.dumps(spread_mode)};
      const curtainStage = document.getElementById('curtainStage');
      const curtainCue = document.getElementById('curtainCue');
      const askAnotherBtn = document.getElementById('askAnotherBtn');
      let hasUnveiled = false;
      let hasStartedShuffle = false;
      let btnShown = false;
      let isReturning = false;

      function startShuffleOnce() {{
        if (hasStartedShuffle || isReturning) return;
        hasStartedShuffle = true;
        document.dispatchEvent(new MouseEvent('click', {{ bubbles: true }}));
      }}

      function handleFirstClick(e) {{
        if (hasUnveiled) return;
        e.preventDefault();
        e.stopPropagation();
        if (typeof e.stopImmediatePropagation === 'function') {{
          e.stopImmediatePropagation();
        }}
        hasUnveiled = true;
        document.removeEventListener('click', handleFirstClick, true);

        if (curtainCue) curtainCue.classList.add('is-hidden');

        if (typeof window.openCurtains === 'function') {{
          window.openCurtains();
        }}

        window.addEventListener('curtains:settled', (ev) => {{
          if (ev.detail && ev.detail.isOpen && curtainStage) {{
            curtainStage.classList.add('is-curtain-tucked');
          }}
        }}, {{ once: true }});

        setTimeout(() => {{
          if (curtainStage) curtainStage.classList.add('is-curtain-tucked');
        }}, 2300);

        setTimeout(startShuffleOnce, 950);
      }}

      document.addEventListener('click', handleFirstClick, true);

      function isFinalReadingReached() {{
        if (SPREAD_MODE === 'one_card') {{
          const exp = document.getElementById('explanationCol');
          return Boolean(exp && exp.classList.contains('is-visible'));
        }}
        if (SPREAD_MODE === 'three_card') {{
          const sBtn = document.getElementById('summaryBtn');
          return Boolean(
            sBtn &&
            sBtn.style.display !== 'none' &&
            sBtn.classList.contains('tarot-btn--primary')
          );
        }}
        if (SPREAD_MODE === 'celtic_cross') {{
          const sWrap = document.getElementById('summaryWrap');
          return Boolean(sWrap && sWrap.classList.contains('is-visible'));
        }}
        return false;
      }}

      function checkFinalState() {{
        if (isReturning || btnShown) return;
        if (isFinalReadingReached()) {{
          btnShown = true;
          observer.disconnect();
          askAnotherBtn.classList.add('is-visible');
        }}
      }}

      const observer = new MutationObserver(checkFinalState);
      observer.observe(document.body, {{
        attributes: true,
        childList: true,
        subtree: true,
        attributeFilter: ['class', 'style']
      }});

      function triggerStreamlitReturn() {{
        const parentDoc = window.parent && window.parent.document;
        if (!parentDoc) return;
        const buttons = parentDoc.querySelectorAll('button');
        for (const btn of buttons) {{
          if (btn.textContent && btn.textContent.trim() === 'DIVINAITION_RETURN_PROMPT') {{
            btn.click();
            break;
          }}
        }}
      }}

      askAnotherBtn.addEventListener('click', (e) => {{
        e.stopPropagation();
        if (isReturning) return;
        isReturning = true;
        observer.disconnect();
        askAnotherBtn.classList.remove('is-visible');

        if (curtainStage) {{
          curtainStage.classList.remove('is-curtain-tucked');
        }}
        if (typeof window.setCurtainsOpen === 'function') {{
          window.setCurtainsOpen(true, true);
        }}

        let triggered = false;
        const finishReturn = () => {{
          if (triggered) return;
          triggered = true;
          triggerStreamlitReturn();
        }};

        window.addEventListener('curtains:settled', (ev) => {{
          if (ev.detail && !ev.detail.isOpen) {{
            finishReturn();
          }}
        }}, {{ once: true }});

        requestAnimationFrame(() => {{
          if (typeof window.closeCurtains === 'function') {{
            window.closeCurtains();
          }} else {{
            finishReturn();
          }}
        }});

        setTimeout(finishReturn, 2300);
      }});
    }})();
  </script>
"""
    html = html.replace("</head>", curtain_head_block + "\n</head>")
    html = html.replace("<body>", "<body>\n" + curtain_front_block)
    return html.replace("</body>", reading_bridge_block + "\n</body>")


SPREAD_CONFIG = {
    "one_card": ("One Card Pull", "one_card.html", one_card),
    "three_card": ("Three Card Spread", "three_card.html", three_card),
    "celtic_cross": ("Celtic Cross Spread", "celtic_card.html", celtic_cross),
}

landing_dir = find_asset("static/landing", "landing")
if not landing_dir:
    raise FileNotFoundError(f"Could not find static/landing/index.html under {BASE_DIR}")
landing_component = components.declare_component("divinaition_landing", path=str(landing_dir))

# Session state initialization
if "stage" not in st.session_state:
    st.session_state["stage"] = "landing"
if "render_seq" not in st.session_state:
    st.session_state["render_seq"] = 0
if "landing_seq" not in st.session_state:
    st.session_state["landing_seq"] = 0
if "landing_view" not in st.session_state:
    st.session_state["landing_view"] = "birthdate"

stage = st.session_state["stage"]

# Full-screen iframe layout + suppress Streamlit default dim/spinner overlays + hide bridge widgets off-screen
stage_iframe_css = (
    """
    iframe[srcdoc] {
      z-index: 1 !important;
    }
    iframe:not([srcdoc]) {
      z-index: 10 !important;
      background: transparent !important;
    }
    """
    if stage == "landing"
    else """
    iframe {
      z-index: 10 !important;
    }
    """
)

st.markdown(
    f"""
    <style>
      [data-testid="stAppViewContainer"],
      [data-testid="stMain"],
      .stApp {{
        background: #020524 !important;
        overflow: hidden !important;
        opacity: 1 !important;
        filter: none !important;
      }}
      [data-testid="stHeader"],
      [data-testid="stToolbar"],
      [data-testid="stStatusWidget"],
      [data-testid="stSpinner"],
      footer {{
        display: none !important;
      }}
      [data-testid="stMainBlockContainer"],
      .block-container {{
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
      }}
      [data-testid="stMain"] iframe,
      iframe[data-testid="stIFrame"] {{
        position: fixed !important;
        inset: 0 !important;
        width: 100vw !important;
        height: 100dvh !important;
        border: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        opacity: 1 !important;
        filter: none !important;
      }}
      {stage_iframe_css}
      .st-key-soul_prompt_input,
      .st-key-soul_prompt_submit,
      .st-key-reading_return_btn,
      div[data-testid="stTextInput"]:has(input[aria-label="DIVINAITION_PROMPT_BRIDGE"]) {{
        position: fixed !important;
        left: -9999px !important;
        top: -9999px !important;
        width: 1px !important;
        height: 1px !important;
        opacity: 0 !important;
        pointer-events: none !important;
        z-index: -1 !important;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ==============================================================================
# STAGE 1: Landing (index.html in front, closed correct_curtains.html behind)
# ==============================================================================
if stage == "landing":
    curtains_only_html = load_text_asset("testing/correct_curtains.html", "correct_curtains.html", "curtains.html")
    components.html(curtains_only_html, height=900, scrolling=False)

    landing_css = load_text_asset("static/css/style.css") + """
    html, body, body.index-page {
      background: transparent !important;
    }
    #starfieldMount, .starfield-bg {
      display: none !important;
    }
    """
    form_data = landing_component(
        css_text=landing_css,
        bg_html='<div class="starfield-bg" style="display:none" aria-hidden="true"></div>',
        card_back_url=to_data_uri("static/images/miscellaneous/TarotCard_Back.png"),
        initial_view=st.session_state.get("landing_view", "birthdate"),
        saved_birthdate=st.session_state.get("saved_birthdate", ""),
        render_seq=st.session_state["landing_seq"],
        key=f"landing_form_{st.session_state['landing_seq']}",
    )
    if form_data:
        zodiac_sign = get_zodiac_from_birthdate(form_data["birthdate"])
        spread_mode = form_data["spread"].replace("-", "_")

        st.session_state["saved_birthdate"] = form_data["birthdate"]
        st.session_state["reading_request"] = {
            "birthdate": form_data["birthdate"],
            "zodiac_sign": zodiac_sign,
            "spread": spread_mode if spread_mode in SPREAD_CONFIG else "one_card",
        }
        st.session_state.pop("tarot_payload", None)
        st.session_state.pop("context_modal_message", None)
        st.session_state.pop("soul_error_message", None)
        st.session_state.pop("user_question", None)
        st.session_state["stage"] = "soul_prompt"
        st.session_state["render_seq"] += 1
        st.rerun()

# ==============================================================================
# STAGE 2: "What Stirs Within Your Soul?" Prompt + Mystical Loading Buffer
# ==============================================================================
elif stage == "soul_prompt":
    req = st.session_state["reading_request"]
    spread_mode = req["spread"]
    zodiac_sign = req["zodiac_sign"]
    spread_label, _, draw_fn = SPREAD_CONFIG[spread_mode]

    prompt_val = st.text_input(
        "DIVINAITION_PROMPT_BRIDGE",
        key="soul_prompt_input",
        label_visibility="collapsed",
    )
    prompt_submit = st.button("DIVINAITION_SUBMIT_PROMPT", key="soul_prompt_submit")

    if prompt_submit:
        question_text = (prompt_val or "").strip()

        # Server-side guard: never invoke the AI on an empty/whitespace prompt
        if not question_text:
            st.session_state.pop("context_modal_message", None)
            st.session_state["soul_error_message"] = (
                "Please share a question or life context before invoking the cards."
            )
            st.session_state["render_seq"] += 1
            st.rerun()

        st.session_state["user_question"] = question_text
        st.session_state.pop("soul_error_message", None)
        st.session_state.pop("context_modal_message", None)

        result = draw_fn()
        cards_list = result if isinstance(result, list) else ([result] if result else [])

        try:
            raw_llm_text = (
                get_llm_interpretation(cards_list, spread_label, zodiac_sign, question_text)
                if cards_list
                else ""
            )
        except Exception:
            raw_llm_text = ""

        parsed = parse_llm_output(raw_llm_text, cards_list)

        if parsed["status"] == "modal":
            st.session_state["context_modal_message"] = parsed["message"]
            st.session_state["render_seq"] += 1
            st.rerun()

        updated_cards, llm_response = apply_parsed_reading_to_cards(
            cards_list,
            parsed,
            spread_mode,
        )

        st.session_state["tarot_payload"] = {
            "cards": updated_cards,
            "llm_response": llm_response,
            "zodiac_sign": zodiac_sign,
            "user_question": question_text,
            "card_back_url": to_data_uri("static/images/miscellaneous/TarotCard_Back.png"),
        }
        st.session_state["stage"] = "reading"
        st.session_state["render_seq"] += 1
        st.rerun()
    else:
        soul_html = build_soul_prompt_html(
            spread_label=spread_label,
            zodiac_sign=zodiac_sign,
            render_seq=st.session_state["render_seq"],
            modal_message=st.session_state.get("context_modal_message", ""),
            prefill_question=st.session_state.get("user_question", ""),
            error_message=st.session_state.get("soul_error_message", ""),
        )
        components.html(soul_html, height=900, scrolling=False)

# ==============================================================================
# STAGE 3: Spread Reading (one_card / three_card / celtic_card) + Curtain Return
# ==============================================================================
elif stage == "reading":
    req = st.session_state["reading_request"]
    spread_mode = req["spread"]
    spread_label, html_filename, _ = SPREAD_CONFIG[spread_mode]

    reading_return = st.button("DIVINAITION_RETURN_PROMPT", key="reading_return_btn")
    if reading_return:
        st.session_state.pop("tarot_payload", None)
        st.session_state.pop("context_modal_message", None)
        st.session_state.pop("soul_error_message", None)
        st.session_state.pop("user_question", None)
        st.session_state["landing_view"] = "readings"
        st.session_state["landing_seq"] += 1
        st.session_state["stage"] = "landing"
        st.session_state["render_seq"] += 1
        st.rerun()
    else:
        html = build_tarot_html(
            html_filename,
            st.session_state["tarot_payload"],
            spread_mode,
            st.session_state["render_seq"],
        )
        components.html(html, height=900, scrolling=False)