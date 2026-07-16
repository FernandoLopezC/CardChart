import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from slugify import slugify

HEADERS = {
    "User-Agent": "CardChart/0.1 (+local collection tracker)",
    "Accept-Language": "en-GB,en;q=0.9",
}


def build_ebay_query(card):
    parts = [card.name, card.set_name, card.collector_number, card.finish_display, "mtg"]
    return " ".join(part for part in parts if part).strip()


def build_ebay_sold_url(query):
    return "https://www.ebay.co.uk/sch/i.html?_nkw={}&_sacat=0&_from=R40&LH_Sold=1&rt=nc&LH_PrefLoc=1".format(
        quote_plus(query)
    )


def scrape_ebay_sold(query):
    url = build_ebay_sold_url(query)
    soup = get_soup(url)
    listings = []

    for item in soup.select(".s-item"):
        title = text_or_empty(item.select_one(".s-item__title"))
        price_text = text_or_empty(item.select_one(".s-item__price"))
        price = parse_gbp(price_text)

        if title and price is not None:
            listings.append({"title": title, "price_gbp": price, "url": url})

    return listings


def build_cardmarket_url(card, version="V1"):
    set_slug = slugify(card.set_name)
    card_slug = slugify(card.name)
    return f"https://www.cardmarket.com/en/Magic/Products/Singles/{set_slug}/{card_slug}-{version}?sellerCountry=13&language=1"


def scrape_cardmarket(url):
    soup = get_soup(url)
    rows = soup.select(".article-row")
    prices = []

    for row in rows:
        price_text = text_or_empty(row.select_one(".price-container"))
        seller = text_or_empty(row.select_one(".seller-name"))
        price = parse_gbp(price_text) or parse_eur(price_text)

        if price is not None:
            prices.append({"title": seller or "Cardmarket listing", "price_gbp": price, "url": url})

    return prices


def get_soup(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def text_or_empty(element):
    if not element:
        return ""
    return " ".join(element.get_text(" ", strip=True).split())


def parse_gbp(text):
    match = re.search(r"£\s*([0-9,.]+)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def parse_eur(text):
    match = re.search(r"([0-9,.]+)\s*€", text)
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))
