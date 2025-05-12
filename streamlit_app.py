import streamlit as st
import json
import time
from datetime import datetime
import pandas as pd
from modules.scraper import TwitterScraper
from modules.reply_processor import ReplyProcessor
from modules.utils import load_config, init_session_state, inject_custom_css

# Initialize session state and config
init_session_state()
config = load_config()
inject_custom_css()

# Page configuration
st.set_page_config(
    page_title="Twitter Bot Manager",
    page_icon="🐦",
    layout="wide"
)

# Sidebar navigation
with st.sidebar:
    st.image("assets/logo.png", width=120)
    st.title("Navigation")
    app_mode = st.radio(
        "Choose module",
        ["🔍 Tweet Scraper", "💬 Reply Automation", "📊 Analytics"],
        index=0
    )

# Scraper UI
def show_scraper_ui():
    st.header("🔍 Twitter Scraper")
    
    with st.expander("⚙️ Scraping Configuration", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            keyword = st.text_input("Search Keyword", "finance")
            username = st.text_input("From User (optional)", help="Leave blank for all users")
            days_old = st.number_input("Max Days Old", min_value=1, max_value=365, value=30)
        
        with col2:
            tweet_limit = st.number_input("Tweet Limit", min_value=1, max_value=500, value=50)
            ignore_existing = st.checkbox("Ignore Existing Tweets", True)
            fresh_start = st.checkbox("Fresh Start (delete old data)", False)
    
    if st.button("🚀 Start Scraping", type="primary"):
        with st.spinner("Scraping tweets..."):
            scraper = TwitterScraper(
                tweet_limit=tweet_limit,
                data_file="scraped_tweets.json",
                headless=True  # Run in headless mode for Streamlit
            )
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            def update_progress(current, total):
                progress = int(current / total * 100)
                progress_bar.progress(progress)
                status_text.text(f"Scraped {current}/{total} tweets...")
            
            # Monkey-patch the scraper to update our UI
            scraper._update_progress = update_progress
            
            success = scraper.scrape_twitter(
                keyword=keyword,
                username=username,
                days_old=days_old,
                ignore_existing=ignore_existing,
                fresh_start=fresh_start
            )
            
            progress_bar.empty()
            status_text.empty()
            
            if success:
                st.success(f"Successfully scraped {len(scraper.data)} tweets!")
                st.session_state.last_scrape = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.session_state.scraped_tweets = scraper.data
            else:
                st.error("Scraping failed - check logs for details")
    
    if "scraped_tweets" in st.session_state:
        st.subheader("📋 Scraped Tweets Preview")
        df = pd.DataFrame(st.session_state.scraped_tweets)
        st.dataframe(
            df[["username", "text", "timestamp"]].head(10),
            column_config={
                "username": "User",
                "text": "Tweet",
                "timestamp": "Time"
            },
            hide_index=True,
            use_container_width=True
        )

# Reply Automation UI
def show_reply_ui():
    st.header("💬 Reply Automation")
    
    # Configuration
    with st.expander("⚙️ Configuration", expanded=True):
        config_col1, config_col2 = st.columns(2)
        
        with config_col1:
            input_file = st.file_uploader(
                "Tweet data (JSON)",
                type=["json"],
                help="Upload scraped tweets JSON file"
            )
            max_tweets = st.number_input(
                "Max tweets to process",
                min_value=1,
                max_value=50,
                value=10
            )
        
        with config_col2:
            delay = st.number_input(
                "Delay between replies (seconds)",
                min_value=5,
                max_value=300,
                value=30
            )
            test_mode = st.checkbox(
                "Test Mode (no actual replies)",
                True
            )
    
    # Status display
    st.subheader("📊 Status")
    status_col1, status_col2, status_col3 = st.columns(3)
    
    with status_col1:
        processed_count = len(st.session_state.reply_state.get("processed_ids", []))
        st.metric("Processed Tweets", processed_count)
    
    with status_col2:
        last_processed = st.session_state.reply_state.get("last_processed", "Never")
        st.metric("Last Processed", last_processed)
    
    with status_col3:
        status = "🟢 Running" if st.session_state.reply_state.get("is_processing", False) else "🔴 Stopped"
        st.metric("Current Status", status)
    
    # Action buttons
    st.subheader("🚀 Actions")
    btn_col1, btn_col2 = st.columns(2)
    
    with btn_col1:
        if st.button("▶️ Start Processing", 
                    disabled=st.session_state.reply_state.get("is_processing", False),
                    help="Begin processing tweets and sending replies"):
            st.session_state.reply_state["is_processing"] = True
    
    with btn_col2:
        if st.button("⏸️ Pause Processing",
                    disabled=not st.session_state.reply_state.get("is_processing", False)):
            st.session_state.reply_state["is_processing"] = False
    
    # Processing log
    st.subheader("📝 Activity Log")
    if "replies" in st.session_state.reply_state and st.session_state.reply_state["replies"]:
        log_df = pd.DataFrame(st.session_state.reply_state["replies"])
        st.dataframe(
            log_df,
            column_config={
                "timestamp": "Time",
                "tweet_id": "Tweet ID",
                "response": "Response",
                "status": "Status"
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("No replies have been sent yet")
    
    # Process tweets when enabled
    if st.session_state.reply_state.get("is_processing", False) and input_file:
        process_tweets(input_file, max_tweets, delay, test_mode)

def process_tweets(input_file, max_tweets, delay, test_mode):
    """Process tweets with real reply logic"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        if "reply_processor" not in st.session_state:
            st.session_state.reply_processor = ReplyProcessor(test_mode=test_mode)
        
        processor = st.session_state.reply_processor
        tweets = processor.load_tweets(input_file)
        
        if not tweets:
            st.error("No valid tweets found in the file")
            st.session_state.reply_state["is_processing"] = False
            return
            
        tweets_to_process = [t for t in tweets if t["tweet_id"] not in processor.processed_ids][:max_tweets]
        
        for i, tweet in enumerate(tweets_to_process):
            if not st.session_state.reply_state["is_processing"]:
                break
                
            progress = int((i + 1) / len(tweets_to_process) * 100)
            progress_bar.progress(progress)
            status_text.text(f"Processing tweet {i+1}/{len(tweets_to_process)}...")
            
            # Process the tweet
            result = processor.process_tweet(tweet, delay)
            
            # Update UI
            if result:
                st.session_state.reply_state.setdefault("replies", []).append({
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "tweet_id": tweet["tweet_id"],
                    "response": result["response"][:100] + "..." if len(result["response"]) > 100 else result["response"],
                    "status": result["status"]
                })
                
                st.session_state.reply_state.setdefault("processed_ids", set()).add(tweet["tweet_id"])
                st.session_state.reply_state["last_processed"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Rerun to update UI
                st.rerun()
                
    except Exception as e:
        st.error(f"Error processing tweets: {str(e)}")
    finally:
        st.session_state.reply_state["is_processing"] = False
        progress_bar.empty()
        status_text.empty()

# Analytics UI (placeholder)
def show_analytics_ui():
    st.header("📊 Analytics")
    st.write("Analytics dashboard coming soon...")
    # Will add sentiment analysis and metrics here

# Main app routing
if app_mode == "🔍 Tweet Scraper":
    show_scraper_ui()
elif app_mode == "💬 Reply Automation":
    show_reply_ui()
elif app_mode == "📊 Analytics":
    show_analytics_ui()

# Footer
st.divider()
st.caption("Twitter Bot Dashboard v1.0 | For professional use only")
