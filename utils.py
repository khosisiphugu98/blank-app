import streamlit as st
import os
from dotenv import load_dotenv

def init_session_state():
    """Initialize all session state variables"""
    if "reply_state" not in st.session_state:
        st.session_state.reply_state = {
            "processed_ids": set(),
            "replies": [],
            "is_processing": False,
            "last_processed": None
        }
    if "scraped_tweets" not in st.session_state:
        st.session_state.scraped_tweets = []
    if "last_scrape" not in st.session_state:
        st.session_state.last_scrape = None

def load_config():
    """Load configuration from environment"""
    load_dotenv()
    return {
        "twitter": {
            "consumer_key": os.getenv("TWITTER_CONSUMER_KEY"),
            "consumer_secret": os.getenv("TWITTER_CONSUMER_SECRET"),
            "access_token": os.getenv("TWITTER_ACCESS_TOKEN"),
            "access_token_secret": os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
        },
        "openai": {
            "api_key": os.getenv("OPENAI_API_KEY")
        }
    }

def inject_custom_css():
    """Inject custom CSS styles"""
    custom_css = """
    [data-testid="stSidebar"] {
        background-color: #15202b;
        color: white;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1DA1F2;
        color: white;
    }
    """
    st.markdown(f"<style>{custom_css}</style>", unsafe_allow_html=True)
