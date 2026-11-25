import base64
import json
import os
import random
from bisect import bisect
from pathlib import Path
from datetime import date

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


def build_tarot_html(filename: str, payload: dict) -> str:
    html = load_text_asset(f"static/templates/{filename}", filename)
    css = load_text_asset("static/css/style.css")
    bg_html = load_text_asset("static/templates/background_animation.html", "background_animation.html")

    render_payload = {
        **payload,
        "card_back_url": payload.get("card_back_url") or to_data_uri("static/images/miscellaneous/TarotCard_Back.png"),
    }

    html = html.replace('<link rel="stylesheet" href="../css/style.css" />', f"<style>{css}</style>")
    html = html.replace('<link rel="stylesheet" href="static/css/style.css" />', f"<style>{css}</style>")
    html = html.replace("<!--__BACKGROUND_ANIMATION__-->", bg_html)
    return html.replace("/*__TAROT_DATA__*/ null", json.dumps(render_payload))


SPREAD_CONFIG = {
    "one_card": ("One Card Pull", "one_card.html", one_card),
    "three_card": ("Three Card Spread", "three_card.html", three_card),
    "celtic_cross": ("Celtic Cross Spread", "celtic_card.html", celtic_cross),
}

landing_dir = find_asset("static/landing", "landing")
if not landing_dir:
    raise FileNotFoundError(f"Could not find static/landing/index.html under {BASE_DIR}")
landing_component = components.declare_component("divinaition_landing", path=str(landing_dir))

# Keep your full-screen iframe CSS for BOTH the landing component and spread templates
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
      [data-testid="stMain"] iframe,
      iframe[data-testid="stIFrame"] {
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

# Step 1: Show landing form until user submits
if "reading_request" not in st.session_state:
    form_data = landing_component(key="landing_form")
    if form_data:
        zodiac_sign = get_zodiac_from_birthdate(form_data["birthdate"])
        spread_mode = form_data["spread"].replace("-", "_")

        st.session_state["reading_request"] = {
            "birthdate": form_data["birthdate"],
            "zodiac_sign": zodiac_sign,
            "spread": spread_mode if spread_mode in SPREAD_CONFIG else "one_card",
        }
        st.session_state.pop("tarot_payload", None)
        st.rerun()

# Step 2: Once submitted, draw cards, call LLM with zodiac_sign, and render spread
else:
    req = st.session_state["reading_request"]
    spread_mode = req["spread"]
    zodiac_sign = req["zodiac_sign"]
    spread_label, html_filename, draw_fn = SPREAD_CONFIG[spread_mode]

    if "tarot_payload" not in st.session_state:
        result = draw_fn()
        cards_list = result if isinstance(result, list) else ([result] if result else [])
        llm_text = (
            get_llm_interpretation(cards_list, spread_label, zodiac_sign)
            if cards_list
            else ""
        )
        st.session_state["tarot_payload"] = {
            "cards": cards_list,
            "llm_response": llm_text,
            "zodiac_sign": zodiac_sign,
            "card_back_url": to_data_uri("static/images/miscellaneous/TarotCard_Back.png"),
        }

    html = build_tarot_html(html_filename, st.session_state["tarot_payload"])
    components.html(html, height=900, scrolling=False)