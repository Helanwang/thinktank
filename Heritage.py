import os
import re
import csv
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# === Configuration ===
BASE_URL = "https://www.heritage.org"
KEYWORDS = [
    'race bias', 'racial bias', 'race prejudice', 'racial prejudice', 'race discrimination',
    'racial discrimination', 'race disparity', 'racial disparity', 'race inequality', 'racial inequality',
    'race difference', 'racial difference', 'racism'
]
OUTPUT_DIR = "heritage_articles"
TXT_DIR = os.path.join(OUTPUT_DIR, "txt")
CSV_FILE = os.path.join(OUTPUT_DIR, "articles.csv")
REQUEST_DELAY = 1  # seconds between requests
MAX_PAGES = 10
CUTOFF_DATE = datetime(2016, 10, 1)

# === Setup Directories ===
os.makedirs(TXT_DIR, exist_ok=True)

# === Setup WebDriver ===
CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver"
options = Options()
options.add_argument('--headless')
options.add_argument('--disable-gpu')
service = Service(executable_path=CHROMEDRIVER_PATH)
driver = webdriver.Chrome(service=service, options=options)

# === Helper Functions ===
def get_search_results(keyword, page):
    search_url = f"{BASE_URL}/search?contains={keyword.replace(' ', '+')}&page={page}"
    driver.get(search_url)
    time.sleep(REQUEST_DELAY)
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    results = []
    for link in soup.select("a[href^='/']"):
        href = link.get('href')
        if not href or '/search?' in href:
            continue

        #only keep article sytle links
        if any(x in href for x in ['/report/', '/commentary/', '/article/']):
            full_url = BASE_URL + href
            results.append((full_url, keyword))

    return results

def get_article_data(url):
    print(f"Fetching article: {url}")
    driver.get(url)
    time.sleep(REQUEST_DELAY)

    soup = BeautifulSoup(driver.page_source, 'html.parser')

    # Extract title
    title_tag = soup.find('h1')
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Extract date
    date = ""
    date_match = soup.find(string=re.compile(r'\w+ \d{1,2}, \d{4}'))  # e.g., "May 4, 2021"
    if date_match:
            try:
                parsed_date = datetime.strptime(date_match.strip(), "%B %d, %Y")
                date = parsed_date.strftime("%Y-%m-%d")
            except ValueError:
                try:
                    # Try abbreviated month name (e.g., Jan 12, 2021)
                    parsed_date = datetime.strptime(date_match.strip(), "%b %d, %Y")
                    date = parsed_date.strftime("%Y-%m-%d")
                except Exception as e:
                    print(f"❌ Date parsing failed for: {title} | Text: {date_match.strip()} | Error: {e}")
                    date = "Unretrieved"



    # Extract author
    author_tag = soup.find('a', href=re.compile('/staff/'))
    author = author_tag.get_text(strip=True) if author_tag else ""

    # Extract content
    content = ""

    # Try several containers, including nested possibilities
    body = (
            soup.find('div', class_='article__body-copy') or
            soup.select_one('div.article__body-copy > div') or
            soup.find('div', class_='article-content') or
            soup.find('div', class_='field--name-body') or
            soup.find('div', class_='node__content') or
            soup.find('div', attrs={'property': 'content:encoded'})
    )

    if body:
        paragraphs = body.find_all('p')
        content = "\n".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))

    if not content:
        print(f"⚠️ No content found for: {url}")


    return {
        'title': title,
        'url': url,
        'date': date,
        'author': author,
        'content': content
    }

# === Main Scraper ===
seen_urls = set()
all_articles = []

for keyword in KEYWORDS:
    print(f"\n🔍 Searching for keyword: '{keyword}'")

    for page in range(MAX_PAGES):
        print(f"[{keyword}] Page {page}...")
        search_results = get_search_results(keyword, page)

        if not search_results:
            print(f"⚠️ No more results found for '{keyword}' after page {page}.")
            break

        for url, matched_keyword in search_results:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            try:
                article = get_article_data(url)

                try:
                    article_date = datetime.strptime(article['date'], "%Y-%m-%d")
                    if article_date < CUTOFF_DATE:
                        print(f"⏭ Skipping (too old): {article['title']} ({article['date']})")
                        continue
                except Exception as e:
                    print(f"❌ Could not parse date for: {article['title']} — skipping. Error: {e}")
                    continue

                article['matched_keyword'] = matched_keyword

                # Save article text file
                safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', article['title'])[:100]
                txt_filename = os.path.join(TXT_DIR, f"{safe_title}.txt")
                with open(txt_filename, 'w', encoding='utf-8') as f:
                    header = (
                        f"Title: {article['title']}\n"
                        f"URL: {article['url']}\n"
                        f"Date: {article['date'] or 'Date not found'}\n"
                        f"Author: {article['author'] or 'Unknown'}\n"
                        f"Matched Keyword: {article['matched_keyword']}\n"
                        f"{'-' * 60}\n\n"
                    )
                    f.write(header + article['content'])
                # Append metadata (excluding content)
                all_articles.append({
                    'title': article['title'],
                    'url': article['url'],
                    'date': article['date'],
                    'author': article['author'],
                    'matched_keyword': article['matched_keyword'],
                    'txt_filename': txt_filename
                })

                print(f"✅ Saved: {article['title']}")

            except Exception as e:
                print(f"❌ Failed to scrape {url}: {e}")

            time.sleep(REQUEST_DELAY)

# === Save CSV ===
with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['title', 'url', 'date', 'author', 'matched_keyword', 'txt_filename'])
    writer.writeheader()
    writer.writerows(all_articles)

print(f"\n✅ Scraping complete. Saved {len(all_articles)} articles.")

# === Clean up ===
driver.quit()
