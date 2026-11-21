import streamlit as st
import os
import streamlit.components.v1 as components
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path
from supabase import create_client, Client
import random
# def load_css(file_path):
#     if os.path.exists(file_path):
#         with open(file_path) as f:
#             st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
#
# load_dotenv()
# load_css()
#
# api_key = os.getenv("AI_API_KEY")
# base_url = os.getenv("BASE_URL")
#
# client = OpenAI(
#     api_key=api_key,
#     base_url=base_url,
# )
#
# system_prompt = """You are a tarot reading chatbot a fun
# humorous and an entertaining AI tarot reader. Your purpose is to
# generate fictional tarot readings playful zodiac interpretations, and
# funny life wisdom. Maintain a friendly witty slightly sarcastic and mystical personality.
# Answer in 3 sentences only."""
#
#
# st.title("What Stirs Within Your Soul?")
#
# if "output" not in st.session_state:
#     st.session_state.output = ""
#
# st.text_area("Output:", value=st.session_state.output, disabled=True)
#
# user_input: str = str(st.text_area("Input area:"))
#
# if st.button("Submit") and user_input:
#     response = client.chat.completions.create(
#         model="gpt-6-luna",
#         messages=[
#             {"role": "system", "content": str(system_prompt)},
#             {"role": "user", "content": str(user_input)}
#         ],
#         max_completion_tokens=500
#     )
#     st.session_state.output = response.choices[0].message.content
#     st.rerun()

from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

def is_reverse():
    return random.randint(0, 1)

def one_card():
    card_id = random.randint(0, 77)
    one_card = (
        supabase.table("tarot_cards")
        .select("*")
        .eq("id", card_id)
        .execute()
    )
    return one_card.data

def three_card():
    ids = random.sample(range(0, 78), 3)
    cards = (
        supabase.table("tarot_cards")
        .select("*")
        .in_("id", ids)
        .execute()
    )
    return cards.data

def celtic_cross():
    ids = random.sample(range(0, 78), 10)
    cards = (
        supabase.table("tarot_cards")
        .select("*")
        .in_("id", ids)
        .execute()
    )
    return cards.data

load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_API_KEY")

supabase: Client = create_client(url, key)

# st.set_page_config(page_title="DivinAItion", layout="wide")

# # Force Streamlit container & iframe to occupy 100% of the screen
# st.markdown(
#     """
#     <style>
#       [data-testid="stAppViewContainer"],
#       [data-testid="stMain"],
#       .stApp {
#         background: #020524 !important;
#         overflow: hidden !important;
#       }
#       [data-testid="stHeader"],
#       [data-testid="stToolbar"],
#       footer {
#         display: none !important;
#       }
#       [data-testid="stMainBlockContainer"],
#       .block-container {
#         padding: 0 !important;
#         margin: 0 !important;
#         max-width: 100% !important;
#       }
#       iframe[data-testid="stIFrame"],
#       .element-container iframe {
#         position: fixed !important;
#         inset: 0 !important;
#         width: 100vw !important;
#         height: 100dvh !important;
#         border: 0 !important;
#         margin: 0 !important;
#         padding: 0 !important;
#         z-index: 1 !important;
#       }
#     </style>
#     """,
#     unsafe_allow_html=True,
# )

# html = (Path(__file__).parent / "testing" / "index.html").read_text(encoding="utf-8")
# components.html(html, height=900, scrolling=False)
