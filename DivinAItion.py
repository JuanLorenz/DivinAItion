import streamlit as st
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("AI_API_KEY")
base_url = os.getenv("BASE_URL")

client = OpenAI(
    api_key=api_key,
    base_url=base_url,
)

system_prompt = """You are a tarot reading chatbot a fun 
humorous and an entertaining AI tarot reader. Your purpose is to 
generate fictional tarot readings playful zodiac interpretations, and 
funny life wisdom. Maintain a friendly witty slightly sarcastic and mystical personality.
Answer in 3 sentences only."""


st.title("Text Output")

if "output" not in st.session_state:
    st.session_state.output = ""

st.text_area("Output:", value=st.session_state.output, disabled=True)

user_input: str = str(st.text_area("Input area:"))

if st.button("Submit") and user_input:
    response = client.chat.completions.create(
        model="gpt-6-luna",
        messages=[
            {"role": "system", "content": str(system_prompt)},
            {"role": "user", "content": str(user_input)}
        ],
        max_completion_tokens=100
    )
    st.session_state.output = response.choices[0].message.content
    st.rerun()