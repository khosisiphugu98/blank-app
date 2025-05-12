import json
import logging
from datetime import datetime
import time
import tweepy
from openai import OpenAI
import os
from typing import Dict, List, Optional
import backoff

class ReplyProcessor:
    def __init__(self, test_mode=False):
        self.test_mode = test_mode
        self.processed_ids = set()
        self.twitter_client = self._initialize_twitter_api() if not test_mode else None
        self.openai_client = self._initialize_openai() if not test_mode else None
        self._load_processed_ids()
        
    def _initialize_twitter_api(self) -> Optional[tweepy.Client]:
        """Initialize Twitter API client"""
        try:
            client = tweepy.Client(
                consumer_key=os.getenv("TWITTER_CONSUMER_KEY"),
                consumer_secret=os.getenv("TWITTER_CONSUMER_SECRET"),
                access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
                access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
            )
            client.get_me()  # Test connection
            return client
        except Exception as e:
            logging.error(f"Twitter API init failed: {e}")
            return None

    def _initialize_openai(self) -> Optional[OpenAI]:
        """Initialize OpenAI client"""
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key not found")
            return OpenAI(api_key=api_key)
        except Exception as e:
            logging.error(f"OpenAI init failed: {e}")
            return None

    def _load_processed_ids(self):
        """Load processed tweet IDs from file"""
        try:
            if os.path.exists("processed_tweets.json"):
                with open("processed_tweets.json", "r") as f:
                    self.processed_ids = set(json.load(f))
        except Exception as e:
            logging.warning(f"Error loading processed IDs: {e}")

    def _save_processed_ids(self):
        """Save processed tweet IDs to file"""
        try:
            with open("processed_tweets.json", "w") as f:
                json.dump(list(self.processed_ids), f)
        except Exception as e:
            logging.error(f"Error saving processed IDs: {e}")

    def load_tweets(self, file_content) -> List[Dict]:
        """Load tweets from file content"""
        try:
            tweets = json.loads(file_content.read())
            return [t for t in tweets if isinstance(t, dict) and "tweet_id" in t and "text" in t]
        except Exception as e:
            logging.error(f"Error loading tweets: {e}")
            return []

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    def generate_response(self, tweet_text: str) -> str:
        """Generate response using OpenAI"""
        if self.test_mode:
            return f"TEST RESPONSE to: {tweet_text[:50]}..."
            
        system_prompt = """
        [Your existing system prompt here]
        """
        
        user_prompt = f"""
        Tweet to respond to: "{tweet_text}"
        [Your existing user prompt here]
        """
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=150
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"OpenAI error: {e}")
            raise

    @backoff.on_exception(backoff.expo, tweepy.TweepyException, max_tries=3)
    def post_reply(self, text: str, reply_to_id: str) -> Optional[str]:
        """Post a reply tweet"""
        if self.test_mode:
            logging.info(f"Would post reply to {reply_to_id}: {text[:50]}...")
            return f"simulated_{reply_to_id}"
            
        try:
            response = self.twitter_client.create_tweet(
                text=text[:280],  # Ensure length limit
                in_reply_to_tweet_id=reply_to_id
            )
            return response.data['id']
        except tweepy.TweepyException as e:
            logging.error(f"Twitter post error: {e}")
            return None

    def process_tweet(self, tweet: Dict, delay: int = 30) -> Dict:
        """Process a single tweet"""
        tweet_id = tweet.get("tweet_id")
        tweet_text = tweet.get("text", "")
        
        if not tweet_id or not tweet_text:
            return {
                "status": "Error: Missing tweet ID or text",
                "response": ""
            }
            
        if tweet_id in self.processed_ids:
            return {
                "status": "Skipped: Already processed",
                "response": ""
            }
            
        try:
            # Generate response
            response = self.generate_response(tweet_text)
            if not response:
                return {
                    "status": "Error: Empty response generated",
                    "response": ""
                }
                
            # Post reply
            posted_id = self.post_reply(response, tweet_id)
            if not posted_id:
                return {
                    "status": "Error: Failed to post reply",
                    "response": response
                }
                
            # Mark as processed
            self.processed_ids.add(tweet_id)
            self._save_processed_ids()
            
            # Respect rate limits
            time.sleep(delay)
            
            return {
                "status": "Success",
                "response": response,
                "posted_id": posted_id
            }
            
        except Exception as e:
            return {
                "status": f"Error: {str(e)}",
                "response": ""
            }
