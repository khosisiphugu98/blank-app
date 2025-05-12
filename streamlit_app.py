import streamlit as st
from datetime import datetime, timedelta
import time
from modules.posting import initialize_twitter_api, create_tweet, schedule_tweets
from modules.replying import monitor_and_reply
from modules.sentiment import analyze_sentiment, plot_sentiment
from utils.config import load_config
from utils.auth import check_password
import pandas as pd
import os

# Page configuration
st.set_page_config(
    page_title="Twitter Bot Dashboard",
    page_icon="🐦",
    layout="wide"
)

# Authentication
if not check_password():
    st.stop()  # Don't continue if check_password is False

# Initialize session state
if 'tweets' not in st.session_state:
    st.session_state.tweets = []
if 'replies' not in st.session_state:
    st.session_state.replies = []
if 'sentiment_data' not in st.session_state:
    st.session_state.sentiment_data = []

# Load Twitter API config
config = load_config()
api = initialize_twitter_api(
    config['twitter']['api_key'],
    config['twitter']['api_secret'],
    config['twitter']['access_token'],
    config['twitter']['access_secret']
)

# Sidebar for navigation
st.sidebar.title("Navigation")
app_mode = st.sidebar.radio("Choose a module", 
                           ["Post Creator", "Reply Monitor", "Sentiment Analysis"])

# Main app
st.title("Twitter Bot Dashboard")

if app_mode == "Post Creator":
    st.header("📝 Post Creator")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Create New Tweet")
        tweet_content = st.text_area("Tweet content", max_chars=280, height=100)
        media_file = st.file_uploader("Add media (optional)", type=['png', 'jpg', 'jpeg', 'gif', 'mp4'])
        if st.button("Post Tweet"):
            if tweet_content:
                media_path = None
                if media_file:
                    # Save uploaded file temporarily
                    media_path = f"temp_media.{media_file.name.split('.')[-1]}"
                    with open(media_path, "wb") as f:
                        f.write(media_file.getbuffer())
                
                result = create_tweet(api, tweet_content, media_path)
                if result['success']:
                    st.success("Tweet posted successfully!")
                    st.session_state.tweets.append(result)
                else:
                    st.error(f"Error posting tweet: {result['error']}")
                
                # Clean up temp file
                if media_path and os.path.exists(media_path):
                    os.remove(media_path)
            else:
                st.warning("Please enter tweet content")
    
    with col2:
        st.subheader("Scheduled Posts")
        with st.expander("Add Scheduled Post"):
            scheduled_content = st.text_area("Content", key="scheduled_content")
            scheduled_time = st.date_input("Date", min_value=datetime.now().date())
            scheduled_hour = st.time_input("Time")
            if st.button("Schedule"):
                # This would need integration with a scheduler
                st.info("Scheduling functionality would be implemented with APScheduler or similar")
                
        st.subheader("Recent Posts")
        if st.session_state.tweets:
            df = pd.DataFrame(st.session_state.tweets)
            st.dataframe(df[['content', 'created_at']])
        else:
            st.info("No tweets posted yet")

elif app_mode == "Reply Monitor":
    st.header("💬 Reply Monitor")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Configure Replies")
        keywords = st.text_input("Keywords to monitor (comma separated)").split(',')
        reply_template = st.text_area("Reply template (use {username} for mention)", 
                                     "Thanks @{username} for your feedback!")
        
        if st.button("Start Monitoring"):
            if keywords and reply_template:
                st.info("Monitoring started... (this is a simulation in Streamlit)")
                # In a real app, this would run in a background thread
                mock_tweet = {
                    'text': f"This tweet contains {keywords[0]}",
                    'user': {'screen_name': 'testuser'},
                    'id': '12345',
                    'created_at': datetime.now()
                }
                reply_result = monitor_and_reply(api, keywords, reply_template)
                st.session_state.replies.append(reply_result)
                st.success("Reply sent to test tweet (simulated)")
            else:
                st.warning("Please enter keywords and reply template")
    
    with col2:
        st.subheader("Recent Replies")
        if st.session_state.replies:
            df = pd.DataFrame(st.session_state.replies)
            st.dataframe(df)
        else:
            st.info("No replies sent yet")

elif app_mode == "Sentiment Analysis":
    st.header("📊 Sentiment Analysis")
    
    analysis_option = st.radio("Analyze", ["Recent Tweets", "Specific Account", "Custom Text"])
    
    if analysis_option == "Recent Tweets":
        st.subheader("Analyze Recent Tweets")
        tweet_count = st.slider("Number of tweets to analyze", 1, 100, 10)
        if st.button("Analyze"):
            # Get recent tweets from your own account
            tweets = [tweet.text for tweet in api.user_timeline(count=tweet_count)]
            st.session_state.sentiment_data = analyze_sentiment(tweets)
    
    elif analysis_option == "Specific Account":
        st.subheader("Analyze Specific Account")
        username = st.text_input("Twitter username (without @)")
        tweet_count = st.slider("Number of tweets to analyze", 1, 100, 10)
        if st.button("Analyze") and username:
            try:
                tweets = [tweet.text for tweet in api.user_timeline(screen_name=username, count=tweet_count)]
                st.session_state.sentiment_data = analyze_sentiment(tweets)
            except Exception as e:
                st.error(f"Error fetching tweets: {str(e)}")
    
    elif analysis_option == "Custom Text":
        st.subheader("Analyze Custom Text")
        custom_text = st.text_area("Enter text to analyze")
        if st.button("Analyze") and custom_text:
            st.session_state.sentiment_data = analyze_sentiment([custom_text])
    
    if st.session_state.sentiment_data:
        st.subheader("Results")
        fig = plot_sentiment(st.session_state.sentiment_data)
        st.pyplot(fig)
        
        df = pd.DataFrame(st.session_state.sentiment_data)
        st.dataframe(df)
