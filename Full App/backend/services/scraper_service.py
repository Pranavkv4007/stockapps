"""
Web scraping utilities — exact port from both Streamlit apps.
"""

import re
import time
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
}


class Website:
    """Utility class to represent a scraped webpage."""

    def __init__(self, url):
        self.url = url
        response = requests.get(self.url, headers=HEADERS)
        self.body = response.content
        soup = BeautifulSoup(self.body, "html.parser")
        self.title = soup.title.string if soup.title else "No title found"
        if soup.body:
            for irrelevant in soup.body(["script", "style", "img", "input"]):
                irrelevant.decompose()
            self.text = soup.body.get_text(separator="\n", strip=True)
        else:
            self.text = ""
        links = [link.get("href") for link in soup.find_all("a")]
        self.links = [link for link in links if link]

    def get_title(self):
        match = re.search(r"\n\s*(.*?)\n\s*- Screener", self.title)
        if match:
            return match.group(1).strip()
        return self.title

    def get_pages(self):
        raw_text = self.text
        clean_text = raw_text.encode("utf-8").decode("unicode_escape")
        lines = clean_text.splitlines()
        pattern = r"(\d+)\s+results found: Showing page \d+ of (\d+)"
        for line in lines:
            match = re.search(pattern, line)
            if match:
                return int(match.group(2))
        return 1

    def get_company_name(self):
        return self.title.split(" share price")[0]


def get_sector_details(url, pages, callback=None):
    """Get all company links from sector pages."""
    company_links = []
    for i in range(1, pages + 1):
        page_link = url + "?page=" + str(i)
        site = Website(page_link)
        time.sleep(1)
        msg = f"Getting links from page {i} of {pages}"
        if callback:
            callback(msg)
        for link in site.links:
            if link.startswith("/company/"):
                company_links.append("https://www.screener.in" + link)
    return company_links


def get_company_names(company_links, total_companies, callback=None):
    """Get company names from their screener links."""
    company_names = []
    for i in range(len(company_links)):
        site = Website(company_links[i])
        time.sleep(1)
        company_names.append(site.title)
        msg = f"Getting company name {i + 1} of {total_companies}"
        if callback:
            callback(msg)
    company = [title.split(" share price")[0] for title in company_names]
    return company


def get_subsector_details(site_or_url):
    """Extract market/sector links from a website or URL."""
    if isinstance(site_or_url, str):
        site = Website(site_or_url)
    else:
        site = site_or_url
    screener_links = []
    for link in site.links:
        if link.startswith("/market/"):
            screener_links.append("https://www.screener.in" + link)
    return screener_links


def get_sector_names(market_links):
    """Get sector and sub-sector names from market links."""
    names = []
    for link in market_links[-2:]:
        site = Website(link)
        time.sleep(1)
        title_text = site.title.strip().split("\n")[0].strip()
        names.append(title_text)
    if len(names) >= 2:
        return names[0], names[1]
    elif len(names) == 1:
        return names[0], names[0]
    return "Unknown", "Unknown"
