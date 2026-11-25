import base64
import json
import os
import random
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from openai import OpenAI
from supabase import Client, create_client

st.set_page_config(page_title="DivinAItion", layout="wide")

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

SYSTEM_PROMPT = """You are a tarot reading chatbot — a fun,
humorous, and entertaining AI tarot reader. Your purpose is to
generate fictional tarot readings, playful zodiac interpretations, and
funny life wisdom. Maintain a friendly, witty, slightly sarcastic, and mystical personality.
If there is only 1 card, answer in 1 paragraph (3 sentences).
If there is more than 1 card, separate the explanation of each card by paragraph in exact card order, with one paragraph per card."""


def attach_card_image(card: dict) -> dict:
    """Embed static/images/card/<id>.png as a base64 data URI so it always loads inside Streamlit's iframe."""
    for root in (BASE_DIR, BASE_DIR.parent):
        img_path = root / "static" / "images" / "card" / f"{card['id']}.png"
        if img_path.exists():
            b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
            card["image_url"] = f"data:image/png;base64,{b64}"
            break
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


def get_llm_interpretation(cards: list[dict], spread_name: str) -> str:
    card_lines = []
    for idx, c in enumerate(cards, start=1):
        orientation = "Reversed" if c["is_reverse"] else "Upright"
        card_lines.append(
            f"{idx}. {c['card_name']} ({orientation}) — Reference meaning: {c['meaning']}"
        )

    user_prompt = (
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


def load_html_file(filename: str) -> str:
    for candidate in (BASE_DIR / filename, BASE_DIR / "testing" / filename):
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Could not find {filename} in {BASE_DIR} or {BASE_DIR / 'testing'}")


SPREAD_CONFIG = {
    "one_card": ("One Card Pull", "one_card.html", one_card),
    "three_card": ("Three Card Spread", "three_card.html", three_card),
    "celtic_cross": ("Celtic Cross Spread", "celtic_card.html", celtic_cross),
}

# Switch spreads via URL: ?spread=one_card, ?spread=three_card, or ?spread=celtic_cross
SPREAD_MODE = st.query_params.get("spread", "celtic_cross")
if SPREAD_MODE not in SPREAD_CONFIG:
    SPREAD_MODE = "one_card"

spread_label, html_filename, draw_fn = SPREAD_CONFIG[SPREAD_MODE]
session_key = f"tarot_payload_{SPREAD_MODE}"

if session_key not in st.session_state:
    result = draw_fn()
    cards_list = result if isinstance(result, list) else ([result] if result else [])
    llm_text = get_llm_interpretation(cards_list, spread_label) if cards_list else ""
    st.session_state[session_key] = {
        "cards": cards_list,
        "llm_response": llm_text,
    }

# Force Streamlit container & iframe to occupy 100% of the screen
st.markdown(
    """
    <style>
      [data-testid="stAppViewContainer"],
      [data-testid="stMain"],
      .stApp {
        background: #020524 !important;
        overflow: hidden !important;
      }
      [data-testid="stHeader"],
      [data-testid="stToolbar"],
      footer {
        display: none !important;
      }
      [data-testid="stMainBlockContainer"],
      .block-container {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
      }
      iframe[data-testid="stIFrame"],
      .element-container iframe {
        position: fixed !important;
        inset: 0 !important;
        width: 100vw !important;
        height: 100dvh !important;
        border: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        z-index: 1 !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

html = load_html_file(html_filename)
html = html.replace("/*__TAROT_DATA__*/ null", json.dumps(st.session_state[session_key]))
components.html(html, height=900, scrolling=False)