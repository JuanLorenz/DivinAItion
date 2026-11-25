import base64
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


def get_llm_interpretation(cards: list[dict], spread_name: str, zodiac_sign: str) -> str:
    card_lines = []
    for idx, c in enumerate(cards, start=1):
        orientation = "Reversed" if c["is_reverse"] else "Upright"
        card_lines.append(
            f"{idx}. {c['card_name']} ({orientation}) — Reference meaning: {c['meaning']}"
        )

    user_prompt = (
        f"Zodiac Sign: {zodiac_sign}\n"
        f"Spread: {spread_name}\n"
        "Cards drawn:\n"
        + "\n".join(card_lines)
        + "\n\nProvide the interpretation following the system instructions."
    )

    response = client.chat.completions.create(
        model="gpt-6-luna",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_completion_tokens=1200,
    )
    return response.choices[0].message.content or ""


def extract_between(text: str, start_marker: str, end_marker: str) -> str:
    pattern = re.escape(start_marker) + r"(.*?)" + re.escape(end_marker)
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


def load_curtain_parts() -> tuple[str, str, str]:
    raw = load_text_asset("testing/correct_curtains.html", "correct_curtains.html")
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


def build_soul_prompt_html(spread_label: str, zodiac_sign: str, render_seq: int) -> str:
    css = load_text_asset("static/css/style.css")
    bg_html = load_text_asset("static/templates/background_animation.html", "background_animation.html")
    curtain_style, curtain_html, curtain_script = load_curtain_parts()
    local_fonts_css, script_stack = build_local_fonts_css()

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>What Stirs Within Your Soul? · DivinAItion</title>
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
        autofocus
      ></textarea>
    </div>
    <p class="soul-hint">Press Enter to cast your {spread_label} &middot; {zodiac_sign}</p>
  </main>

  <section class="mystic-loader" id="mysticLoader" aria-live="polite" aria-label="Calling the universe's response">
    <div class="mystic-sigil" aria-hidden="true">
      <div class="mystic-aura"></div>
      <div class="mystic-ring-outer"></div>
      <div class="mystic-ring-inner"></div>
      <div class="mystic-star"></div>
    </div>
    <p class="mystic-text">Calling the universe&rsquo;s response&hellip;</p>
    <p class="mystic-subtext">Aligning {spread_label} &middot; {zodiac_sign}</p>
  </section>

  {curtain_html}
  {curtain_script}

  <script>
    (function () {{
      const curtainStage = document.getElementById('curtainStage');
      const soulScreen = document.getElementById('soulScreen');
      const soulBox = document.getElementById('soulBox');
      const soulInput = document.getElementById('soulInput');
      const mysticLoader = document.getElementById('mysticLoader');
      let hasSubmitted = false;

      // Start closed, then sweep open to reveal "What Stirs Within Your Soul ?"
      if (typeof window.setCurtainsOpen === 'function') {{
        window.setCurtainsOpen(false, true);
        setTimeout(() => {{
          if (typeof window.openCurtains === 'function') {{
            window.openCurtains();
          }}
        }}, 110);
      }}

      window.addEventListener('curtains:settled', (e) => {{
        if (e.detail && e.detail.isOpen && curtainStage) {{
          curtainStage.classList.add('is-curtain-tucked');
          if (soulInput) soulInput.focus();
        }}
      }});

      // Safety fallback in case user begins typing before settle completes
      setTimeout(() => {{
        if (curtainStage) curtainStage.classList.add('is-curtain-tucked');
      }}, 2400);

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

      soulInput.addEventListener('keydown', (e) => {{
        if (e.key === 'Enter' && !e.shiftKey) {{
          e.preventDefault();
          if (hasSubmitted) return;

          const text = soulInput.value.trim();
          if (!text) {{
            soulBox.classList.remove('is-nudged');
            void soulBox.offsetWidth;
            soulBox.classList.add('is-nudged');
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

    reading_bridge_block = f"""
  <!-- render_seq: {render_seq} -->
  {curtain_style}
  <style>
    .reading-intro-veil {{
      position: fixed;
      inset: 0;
      z-index: 48;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: radial-gradient(circle at center, rgba(20, 10, 56, 0.88) 0%, rgba(2, 5, 36, 0.94) 100%);
      pointer-events: auto;
      opacity: 1;
      transition: opacity 550ms ease;
    }}

    .reading-intro-veil.is-gone {{
      opacity: 0;
      pointer-events: none;
    }}

    .reading-intro-veil p {{
      font-family: "Cormorant Garamond", Georgia, serif;
      font-style: italic;
      font-size: clamp(1.5rem, 3vw, 2.1rem);
      color: #fef3c7;
      text-shadow: 0 0 20px rgba(253, 230, 138, 0.5);
      margin: 0;
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

  <div class="reading-intro-veil" id="readingIntroVeil">
    <p>Calling the universe&rsquo;s response&hellip;</p>
  </div>

  <button type="button" class="ask-another-btn" id="askAnotherBtn">
    Ask Another Question
  </button>

  {curtain_html}
  {curtain_script}

  <script>
    (function () {{
      const SPREAD_MODE = {json.dumps(spread_mode)};
      const curtainStage = document.getElementById('curtainStage');
      const introVeil = document.getElementById('readingIntroVeil');
      const askAnotherBtn = document.getElementById('askAnotherBtn');
      let btnShown = false;
      let isReturning = false;

      if (typeof window.setCurtainsOpen === 'function') {{
        window.setCurtainsOpen(true, true);
      }}
      if (curtainStage) {{
        curtainStage.classList.add('is-curtain-tucked');
      }}

      setTimeout(() => {{
        if (introVeil) introVeil.classList.add('is-gone');
        setTimeout(() => {{
          document.dispatchEvent(new MouseEvent('click', {{ bubbles: true }}));
        }}, 360);
      }}, 180);

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
    curtains_only_html = load_text_asset("testing/correct_curtains.html", "correct_curtains.html")
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
        key="landing_form",
    )
    if form_data:
        zodiac_sign = get_zodiac_from_birthdate(form_data["birthdate"])
        spread_mode = form_data["spread"].replace("-", "_")

        st.session_state["reading_request"] = {
            "birthdate": form_data["birthdate"],
            "zodiac_sign": zodiac_sign,
            "spread": spread_mode if spread_mode in SPREAD_CONFIG else "one_card",
        }
        st.session_state.pop("tarot_payload", None)
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
        st.session_state["user_question"] = (prompt_val or "").strip()
        result = draw_fn()
        cards_list = result if isinstance(result, list) else ([result] if result else [])
        try:
            llm_text = (
                get_llm_interpretation(cards_list, spread_label, zodiac_sign)
                if cards_list
                else ""
            )
        except Exception:
            llm_text = ""

        st.session_state["tarot_payload"] = {
            "cards": cards_list,
            "llm_response": llm_text,
            "zodiac_sign": zodiac_sign,
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
        st.session_state["stage"] = "soul_prompt"
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