import json
import os
import re
import sys
import time
import random
import keyboard
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright


class TwitterScraper:
    def __init__(self, tweet_limit=15, data_file=None, headless=True):
        self.data = []
        self.tweet_limit = tweet_limit
        self.nitter_instances = [
            "https://nitter.net",
            "https://nitter.42l.fr",
            "https://nitter.pussthecat.org",
            "https://nitter.nixnet.services",
            "https://nitter.fdn.fr",
        ]
        self.data_file = data_file or "twitter_scraped_data.json"
        self.seen_tweets = set()
        self.ignore_existing = False
        self.headless = headless
        self.current_instance = None
        self.should_stop = False
        self.last_page_content = None  # Track last page content to detect duplicates

    def setup_keyboard_listener(self):
        """Set up keyboard listener for spacebar to stop scraping"""
        keyboard.on_press_key('space', lambda _: self.stop_scraping())
        print("\nPress SPACEBAR at any time to stop scraping...")

    def stop_scraping(self):
        """Set flag to stop scraping"""
        self.should_stop = True
        print("\nSPACEBAR pressed - stopping after current page...")

    def is_new_tweet(self, tweet_id):
        """Check if we've seen this tweet before"""
        if self.ignore_existing:
            return True
        return tweet_id not in self.seen_tweets

    def random_delay(self, min_seconds=1, max_seconds=5):
        """Add a random delay to avoid detection"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
        return delay

    def take_screenshot(self, page, filename="debug_screenshot.png"):
        """Take screenshot of current page state with timestamp"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{filename}"
            page.screenshot(path=filename, full_page=True)
            print(f"Debug: Screenshot saved as {filename}")
            return True
        except Exception as e:
            print(f"Failed to take screenshot: {str(e)[:200]}")
            return False

    def load_existing_data(self):
        """Load existing data with robust error handling"""
        if self.ignore_existing:
            print("Ignoring existing data as per ignore_existing flag")
            return []

        try:
            if Path(self.data_file).exists():
                with open(self.data_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    self.seen_tweets = {
                        str(tweet["tweet_id"]) for tweet in existing_data if "tweet_id" in tweet
                    }
                    print(f"Loaded {len(existing_data)} existing tweets from {self.data_file}")
                    return existing_data
            print(f"No existing data file found at {self.data_file}")
            return []
        except json.JSONDecodeError:
            print(f"Warning: Corrupted JSON file {self.data_file}. Starting fresh.")
            return []
        except Exception as e:
            print(f"Error loading existing data: {str(e)[:200]}")
            return []

    def extract_tweet_id(self, tweet_element):
        """Robust tweet ID extraction with multiple fallbacks"""
        try:
            # Method 1: Extract from tweet URL
            tweet_link = tweet_element.query_selector("a.tweet-link")
            if tweet_link:
                href = tweet_link.get_attribute("href") or ""
                match = re.search(r"/status/(\d+)", href)
                if match:
                    return match.group(1)

            # Method 2: Extract from data-tweet-id attribute
            tweet_container = tweet_element.query_selector(".tweet-body")
            if tweet_container:
                tweet_id = tweet_container.get_attribute("data-tweet-id")
                if tweet_id:
                    return tweet_id

            # Method 3: Generate hash from content as last resort
            text_element = tweet_element.query_selector(".tweet-content")
            text = text_element.inner_text() if text_element else ""
            username_element = tweet_element.query_selector(".username")
            username = username_element.inner_text() if username_element else "unknown"
            return str(hash(f"{username[:20]}{text[:100]}"))

        except Exception as e:
            print(f"Error extracting tweet ID: {str(e)[:200]}")
            return None

    def get_tweet_url(self, tweet_id, username):
        """Construct tweet URL with instance fallback"""
        if not tweet_id or not username:
            return ""

        clean_username = username.replace("@", "").strip()
        if not self.current_instance:
            self.current_instance = self.nitter_instances[0]

        return f"{self.current_instance}/{clean_username}/status/{tweet_id}"

    def scrape_tweets_from_page(self, page, page_num):
        """Extract tweets from current page with comprehensive error handling"""
        new_tweets = []
        duplicates = 0
        errors = 0

        try:
            # Wait for tweets to load with timeout
            page.wait_for_selector(".timeline-item", timeout=15000)
            self.random_delay(1, 3)  # Random delay
            tweet_elements = page.query_selector_all(".timeline-item")
            
            if not tweet_elements:
                print(f"No tweet elements found on page {page_num}")
                return [], 0, 0

            for idx, tweet in enumerate(tweet_elements):
                try:
                    if self.should_stop:
                        return new_tweets, duplicates, errors

                    tweet_id = self.extract_tweet_id(tweet)
                    if not tweet_id:
                        print(f"Could not extract ID for tweet {idx + 1}")
                        errors += 1
                        continue

                    if not self.is_new_tweet(tweet_id):
                        duplicates += 1
                        continue

                    # Extract tweet data
                    tweet_data = self.extract_tweet_data(tweet, tweet_id, page_num)
                    if tweet_data:
                        new_tweets.append(tweet_data)
                        self.seen_tweets.add(tweet_id)  # Mark as seen

                    # Add random delay between processing tweets
                    if idx % 3 == 0 and idx > 0:
                        self.random_delay(0.5, 2)

                except Exception as e:
                    print(f"Error processing tweet {idx + 1}: {str(e)[:200]}")
                    errors += 1
                    continue

            return new_tweets, duplicates, errors

        except Exception as e:
            print(f"Page processing error: {str(e)[:200]}")
            self.take_screenshot(page, f"error_page_{page_num}.png")
            return [], 0, 0

    def extract_tweet_data(self, tweet_element, tweet_id, page_num):
        """Extract all data from a single tweet element"""
        try:
            username_element = tweet_element.query_selector(".username")
            username = username_element.inner_text() if username_element else "Unknown"

            fullname_element = tweet_element.query_selector(".fullname")
            fullname = fullname_element.inner_text() if fullname_element else "Unknown"

            text_element = tweet_element.query_selector(".tweet-content")
            text = text_element.inner_text() if text_element else ""

            time_element = tweet_element.query_selector(".tweet-date a")
            timestamp = time_element.get_attribute("title") if time_element else ""

            stats = {
                "replies": self.extract_stat(tweet_element, ".icon-comment"),
                "retweets": self.extract_stat(tweet_element, ".icon-retweet"),
                "likes": self.extract_stat(tweet_element, ".icon-heart"),
            }

            # Extract thread/reply information
            in_reply_to_element = tweet_element.query_selector(".replying-to")
            reply_info = {}
            if in_reply_to_element:
                reply_links = in_reply_to_element.query_selector_all("a")
                if reply_links:
                    reply_to_usernames = [link.inner_text().replace("@", "").strip() for link in reply_links]
                    reply_info = {
                        "reply_to_usernames": reply_to_usernames,
                        "is_thread_part": True
                    }
                    
                    # Try to get the parent tweet ID if available
                    parent_link = in_reply_to_element.query_selector("a[href*='/status/']")
                    if parent_link:
                        href = parent_link.get_attribute("href") or ""
                        match = re.search(r"/status/(\d+)", href)
                        if match:
                            reply_info["parent_tweet_id"] = match.group(1)

            # Extract images if any
            images = []
            media_container = tweet_element.query_selector(".attachments")
            if media_container:
                img_elements = media_container.query_selector_all("img")
                for img in img_elements:
                    src = img.get_attribute("src")
                    if src:
                        images.append(src)

            return {
                "tweet_id": str(tweet_id),
                "tweet_url": self.get_tweet_url(tweet_id, username),
                "username": username,
                "fullname": fullname,
                "text": text,
                "timestamp": timestamp,
                "metrics": stats,
                "images": images if images else None,
                "scraped_at": datetime.now().isoformat(),
                "page_found": page_num,
                "instance": self.current_instance,
                **reply_info  # Add reply information if available
            }

        except Exception as e:
            print(f"Error extracting tweet data: {str(e)[:200]}")
            return None

    def extract_stat(self, tweet_element, icon_class):
        """Helper to extract engagement stats"""
        try:
            icon = tweet_element.query_selector(icon_class)
            if icon:
                stat_element = icon.evaluate("node => node.closest('.tweet-stat').innerText")
                return stat_element.strip() if stat_element else "0"
            return "0"
        except:
            return "0"

    def navigate_to_next_page(self, page, current_page_num):
        """Improved pagination handling with duplicate page detection"""
        try:
            # Add random delay before pagination
            self.random_delay(2, 5)
            
            # Get current page content for comparison
            current_content = page.content()
            
            # Strategy 1: Click the "Load more" button
            load_more_button = page.query_selector("div.show-more a") or \
                             page.query_selector("a.more") or \
                             page.query_selector("div.show-more")

            if load_more_button:
                try:
                    # Scroll to button first
                    page.evaluate("element => element.scrollIntoView()", load_more_button)
                    self.random_delay(1, 3)
                    
                    # Click using JavaScript to avoid element detachment
                    page.evaluate("element => element.click()", load_more_button)
                    
                    # Wait for new content to load
                    try:
                        page.wait_for_selector(".timeline-item", state="attached", timeout=15000)
                        
                        # Verify new content is actually different
                        new_content = page.content()
                        if new_content == current_content or new_content == self.last_page_content:
                            print("Warning: Page content didn't change after click")
                            self.take_screenshot(page, f"duplicate_page_{current_page_num}.png")
                            return False
                            
                        self.last_page_content = current_content
                        print(f"Successfully loaded new tweets (page {current_page_num + 1})")
                        return True
                    except Exception as e:
                        print(f"New content did not load after click: {str(e)[:200]}")
                        self.take_screenshot(page, f"load_more_fail_{current_page_num}.png")
                        return False
                except Exception as e:
                    print(f"Error clicking load more: {str(e)[:200]}")
                    return False

            # Strategy 2: Infinite scroll with content verification
            prev_tweet_count = len(page.query_selector_all(".timeline-item"))
            prev_content = page.content()
            
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self.random_delay(3, 6)  # Longer delay for scroll loading
            
            try:
                page.wait_for_function(
                    f"document.querySelectorAll('.timeline-item').length > {prev_tweet_count}",
                    timeout=15000
                )
                
                # Verify new content is actually different
                new_content = page.content()
                if new_content == prev_content or new_content == self.last_page_content:
                    print("Warning: Page content didn't change after scroll")
                    return False
                    
                self.last_page_content = prev_content
                print(f"New tweets loaded via scroll (page {current_page_num + 1})")
                return True
            except:
                print("No new tweets loaded after scrolling")
                return False

        except Exception as e:
            print(f"Pagination error: {str(e)[:200]}")
            return False

    def group_related_tweets(self, tweets):
        """Group tweets into conversations/threads"""
        threads = {}
        standalone_tweets = []
        
        # First pass: Identify reply relationships
        for tweet in tweets:
            if "reply_to_usernames" in tweet:
                # Create a thread key based on usernames
                for username in tweet["reply_to_usernames"]:
                    if username not in threads:
                        threads[username] = []
                    threads[username].append(tweet)
            else:
                standalone_tweets.append(tweet)
        
        # Create grouped result
        result = []
        
        # Add thread tweets with their context
        for username, thread_tweets in threads.items():
            # Sort by timestamp if available
            if all("timestamp" in t for t in thread_tweets):
                thread_tweets.sort(key=lambda x: x.get("timestamp", ""))
            
            # Tag as part of a thread
            for i, tweet in enumerate(thread_tweets):
                tweet["thread_position"] = i + 1
                tweet["thread_size"] = len(thread_tweets)
                tweet["thread_key"] = f"thread_{username}_{len(thread_tweets)}"
            
            result.extend(thread_tweets)
        
        # Add standalone tweets
        result.extend(standalone_tweets)
        
        return result

    def scrape_twitter(
        self,
        keyword=None,
        location=None,
        username=None,
        days_old=30,
        ignore_existing=False,
        fresh_start=False,
    ):
        """Main scraping function with comprehensive error handling"""
        # Initialize data collection
        if fresh_start and Path(self.data_file).exists():
            try:
                Path(self.data_file).unlink()
                print(f"Fresh start: Deleted existing {self.data_file}")
            except Exception as e:
                print(f"Error deleting old file: {str(e)[:200]}")

        self.ignore_existing = ignore_existing
        existing_data = self.load_existing_data()
        self.data = []
        self.should_stop = False

        # Prepare search query
        query_parts = []
        if keyword:
            query_parts.append(keyword)
        if location:
            query_parts.append(location)
        if username:
            query_parts.append(f"from:{username.replace('@', '')}")
        
        query = " ".join(query_parts) or "easter"
        query_encoded = query.replace(" ", "+")
        
        # Always limit to last 30 days
        since_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        query_encoded += f"&since={since_date}"

        print(f"\nStarting scrape with parameters:")
        print(f"- Query: {query}")
        print(f"- Limit: {self.tweet_limit} tweets")
        print(f"- Date range: Last 30 days (since {since_date})")
        print(f"- Location: Africa")
        print(f"- Username: {username or 'Any'}")
        print(f"- Data file: {self.data_file}")
        print(f"- Fresh start: {fresh_start}")
        print(f"- Ignore existing: {ignore_existing}")

        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                )
                page = context.new_page()
                page.set_default_timeout(15000)

                # Set up keyboard listener
                self.setup_keyboard_listener()

                # Try different Nitter instances
                for instance in self.nitter_instances:
                    try:
                        self.current_instance = instance
                        search_url = f"{instance}/search?f=tweets&q={query_encoded}"
                        print(f"\nTrying instance: {instance}")

                        page.goto(search_url, timeout=30000)
                        self.random_delay(2, 5)  # Random delay after page load
                        
                        # Verify we have tweets
                        page.wait_for_selector(".timeline-item", timeout=15000)
                        print(f"✓ Successfully connected to {instance}")
                        break

                    except Exception as e:
                        print(f"✗ Connection failed: {str(e)[:200]}")
                        self.take_screenshot(page, f"error_{instance.split('//')[1]}.png")
                        self.random_delay(3, 7)  # Longer delay between instance attempts
                        continue
                else:
                    print("All instances failed. Cannot proceed.")
                    return False

                # Main scraping loop
                page_num = 1
                total_duplicates = 0
                total_errors = 0
                consecutive_empty_pages = 0
                max_consecutive_empty = 10  # Stop if we get this many empty pages in a row

                while len(self.data) < self.tweet_limit and not self.should_stop:
                    print(f"\nProcessing page {page_num}...")
                    
                    new_tweets, duplicates, errors = self.scrape_tweets_from_page(page, page_num)
                    total_duplicates += duplicates
                    total_errors += errors

                    if new_tweets:
                        # Only add up to the remaining needed tweets
                        remaining = self.tweet_limit - len(self.data)
                        added_tweets = new_tweets[:remaining]
                        self.data.extend(added_tweets)
                        print(f"Added {len(added_tweets)} new tweets (Total: {len(self.data)}/{self.tweet_limit})")
                        consecutive_empty_pages = 0
                    else:
                        consecutive_empty_pages += 1
                        print(f"No new tweets on page {page_num} (Duplicates: {duplicates})")
                        if consecutive_empty_pages >= max_consecutive_empty:
                            print(f"Stopping: {max_consecutive_empty} consecutive pages without new tweets")
                            break

                    # Stop if we've reached our limit or user requested stop
                    if len(self.data) >= self.tweet_limit or self.should_stop:
                        break

                    # Attempt pagination
                    if not self.navigate_to_next_page(page, page_num):
                        print("Failed to load more tweets")
                        consecutive_empty_pages += 1
                        if consecutive_empty_pages >= max_consecutive_empty:
                            print(f"Stopping: {max_consecutive_empty} consecutive pages without new tweets")
                            break

                    page_num += 1
                    self.random_delay(2, 6)  # Be polite between pages

                print("\nScraping complete!")
                print(f"- Total new tweets collected: {len(self.data)} (Target: {self.tweet_limit})")
                print(f"- Total duplicates skipped: {total_duplicates}")
                print(f"- Total errors encountered: {total_errors}")
                print(f"- Pages processed: {page_num}")

                # Save results
                if self.data:
                    # Group related tweets before saving
                    if self.data:
                        self.data = self.group_related_tweets(self.data)
                    self.save_results(existing_data)
                    return True
                else:
                    print("No new tweets to save.")
                    return False

            except Exception as e:
                print(f"Fatal error during scraping: {str(e)[:200]}")
                self.take_screenshot(page, "fatal_error.png")
                return False
            finally:
                try:
                    keyboard.unhook_all()  # Clean up keyboard listener
                    context.close()
                    browser.close()
                except:
                    pass

    def save_results(self, existing_data):
        """Save results with proper data merging"""
        try:
            # Combine new data with existing data
            combined_data = existing_data + self.data
            
            # Deduplicate by tweet_id
            unique_data = {}
            for tweet in combined_data:
                if "tweet_id" in tweet:
                    unique_data[tweet["tweet_id"]] = tweet
            
            final_data = list(unique_data.values())
            
            # Save JSON
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
            print(f"Saved {len(final_data)} tweets to {self.data_file}")
            
            # Save CSV
            csv_file = self.data_file.replace(".json", ".csv")
            df = pd.json_normalize(final_data)
            df.to_csv(csv_file, index=False, encoding="utf-8")
            print(f"Saved CSV version to {csv_file}")
            
            return True
        except Exception as e:
            print(f"Error saving results: {str(e)[:200]}")
            return False


def main():
    """Example usage with different scenarios"""
    scraper = TwitterScraper(tweet_limit=15, headless=False)
    scraper.scrape_twitter(
        keyword="easter",
        location="Africa",
        ignore_existing=False,
        fresh_start=False
    )


if __name__ == "__main__":
    main()