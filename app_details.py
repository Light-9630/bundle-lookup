import streamlit as st
import pandas as pd
import requests
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from google_play_scraper import app as play_scraper
import concurrent.futures

# Configure Layout Framework
st.set_page_config(page_title="App Store lookup", layout="wide")

class UniversalStoreResolver:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }

    def clean_developer_url(self, raw_url):
        if not raw_url or raw_url == "N/A":
            return "N/A"
        try:
            if not raw_url.startswith(("http://", "https://")):
                raw_url = "http://" + raw_url
            parsed_url = urlparse(raw_url)
            domain = parsed_url.netloc
            if domain.startswith("www."):
                domain = domain[4:]
            if domain:
                return f"{domain}/app-ads.txt"
        except Exception:
            pass
        return "N/A"

    def scrape_apple_privacy_link(self, track_view_url):
        try:
            res = requests.get(track_view_url, headers=self.headers, timeout=5)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for anchor in soup.find_all("a", href=True):
                    if "privacy" in anchor["href"].lower() or "privacy policy" in anchor.text.lower():
                        return anchor["href"]
        except Exception:
            pass
        return None

    def resolve_google_play(self, bundle_id):
        bundle_id = bundle_id.strip()
        url = f"https://play.google.com/store/apps/details?id={bundle_id}"
        try:
            result = play_scraper(bundle_id, lang='en', country='us')
            raw_dev_url = result.get("developerWebsite")
            source_type = "Developer Website"
            target_url = raw_dev_url
            
            if not target_url or target_url == "N/A":
                target_url = result.get("privacyPolicy")
                source_type = "Privacy Policy"
                
            if not target_url:
                target_url = "N/A"
                source_type = "N/A"

            return {
                "App Bundle": bundle_id,
                "App Name": result.get("title", bundle_id),
                "App Store URL": url,
                "Developer App-Ads.txt": self.clean_developer_url(target_url),
                "Store Name": "Google Play Store",
                "Data Source": source_type
            }
        except Exception:
            return {
                "App Bundle": bundle_id, 
                "App Name": "Not Found / Invalid", 
                "App Store URL": "N/A", 
                "Developer App-Ads.txt": "N/A", 
                "Store Name": "N/A", 
                "Data Source": "N/A"
            }

    def resolve_apple_store(self, track_id):
        track_id = track_id.strip()
        numeric_id = re.findall(r'\d+', track_id)
        target_id = numeric_id[0] if numeric_id else track_id
        
        api_url = f"https://itunes.apple.com/lookup?id={target_id}"
        fallback_store_url = f"https://apps.apple.com/app/id{target_id}"
        try:
            res = requests.get(api_url, headers=self.headers, timeout=8)
            if res.status_code == 200:
                data = res.json()
                if data.get("results"):
                    app_data = data["results"][0]
                    raw_store_url = app_data.get("trackViewUrl", fallback_store_url)
                    clean_store_url = raw_store_url.split('?')[0] if raw_store_url else fallback_store_url
                    
                    raw_dev_url = app_data.get("sellerUrl")
                    source_type = "Developer Website"
                    target_url = raw_dev_url
                    
                    if not target_url or target_url == "N/A":
                        target_url = app_data.get("supportUrl") 
                        source_type = "Privacy / Support Policy"
                        
                    if not target_url or target_url == "N/A":
                        scraped_privacy = self.scrape_apple_privacy_link(clean_store_url)
                        if scraped_privacy:
                            target_url = scraped_privacy
                            source_type = "Privacy Policy Page"
                            
                    if not target_url:
                        target_url = "N/A"
                        source_type = "N/A"
                    
                    return {
                        "App Bundle": track_id,
                        "App Name": app_data.get("trackName", "N/A"),
                        "App Store URL": clean_store_url,
                        "Developer App-Ads.txt": self.clean_developer_url(target_url),
                        "Store Name": "Apple App Store",
                        "Data Source": source_type
                    }
        except Exception:
            pass
            
        return {
            "App Bundle": track_id, 
            "App Name": "Not Found / Invalid", 
            "App Store URL": "N/A", 
            "Developer App-Ads.txt": "N/A", 
            "Store Name": "N/A", 
            "Data Source": "N/A"
        }

    # Modularized Routing Engine for Future Expansion
    def auto_detect_and_resolve(self, item):
        item_clean = item.strip()
        
        # Future Store Plugins can be appended as new rules here
        # E.g., elif item_clean.startswith("vizio."): return self.resolve_vizio_store(item_clean)
        
        if item_clean.isdigit():
            return self.resolve_apple_store(item_clean)
        elif "." in item_clean:
            return self.resolve_google_play(item_clean)
        else:
            return {
                "App Bundle": item_clean,
                "App Name": "Unrecognized Bundle Format :(",
                "App Store URL": "N/A",
                "Developer App-Ads.txt": "N/A",
                "Store Name": "N/A",
                "Data Source": "N/A"
            }

# --- Streamlit Front-End Interface ---
st.title("CTV Store & App-Ads.txt Resolver")
st.markdown("Currently supports only Google & Apple App Bundles :)")


raw_input = st.text_area(
    label="Enter App Bundles", 
    placeholder="com.netflix.mediaclient\n363484507\n1249601429", 
    height=200
)


# 1. Parse raw text lines
items_list = [line.strip() for line in raw_input.split("\n") if line.strip()]

# 2. De-duplicate and keep track of count values
unique_items_list = list(dict.fromkeys(items_list))
duplicate_count = len(items_list) - len(unique_items_list)

if st.button("Get Data", type="primary"):
    if not unique_items_list:
        st.warning("Please specify at least one valid app bundle.")
    else:
        resolver = UniversalStoreResolver()
        results_collector = []
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        import time  # Add this right here

        start_time = time.time()  # Start the clock

        # Multi-Threaded Execution Framework for High-Speed Resolution
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Map futures to preserve original input ordering
            futures = {executor.submit(resolver.auto_detect_and_resolve, item): item for item in unique_items_list}
            
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                completed += 1
                status_text.text(f"Processing ({completed}/{len(unique_items_list)})...")
                progress_bar.progress(completed / len(unique_items_list))
                results_collector.append(future.result())
                
        # Re-sort results_collector to match original input order
        order_map = {item: idx for idx, item in enumerate(unique_items_list)}
        results_collector.sort(key=lambda x: order_map.get(x["App Bundle"], 99999))

        elapsed_time = round(time.time() - start_time, 2)  # Calculate total execution seconds

        status_text.empty()
        progress_bar.empty()
        
        # Output duplicate messaging notice header with elapsed time included
        if duplicate_count > 0:
            st.success(f"Searched {len(unique_items_list)} unique apps and removed {duplicate_count} duplicate bundles in {elapsed_time}s")
        else:
            st.success(f"Searched {len(unique_items_list)} unique apps in {elapsed_time}s")
        status_text.empty()
        progress_bar.empty()
        
        df = pd.DataFrame(results_collector)
        
        # Color coding rows that fell back to Privacy Policy
        def highlight_privacy_fallback(row):
            if "Privacy" in str(row["Data Source"]):
                return ['background-color: #fff2cc; color: black'] * len(row)
            return [''] * len(row)
            
        styled_df = df.style.apply(highlight_privacy_fallback, axis=1)
        st.dataframe(styled_df, use_container_width=True)
        
        csv_data = df.to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="Download Data",
            data=csv_data,
            file_name="ctv_app_ads_matrix.csv",
            mime="text/csv",
        )
