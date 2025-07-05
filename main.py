import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import json
import asyncio
from datetime import datetime
import signal
import sys
import time
import undetected_chromedriver as uc

# Wczytaj konfigurację
with open('config.json') as f:
    config = json.load(f)

intents = discord.Intents.default()
intents.message_content = False
bot = commands.Bot(command_prefix='/', intents=intents)

last_ads = {}
initialized = set()
max_ads = 100
check_interval = 1  # sekundy

blocked_keywords = [
    "nie sprzedaje", "nie wysylam", "tylko odbiór", "nie wysyłam"
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pl,en-US;q=0.7,en;q=0.3",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1"
}

def get_vinted_ads_with_selenium(url):
    options = uc.ChromeOptions()
    options.headless = True
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = uc.Chrome(options=options, driver_executable_path="./bin/chromedriver")

    ads = []

    try:
        driver.get(url)
        time.sleep(5)
        soup = BeautifulSoup(driver.page_source, 'lxml')

        for item in soup.select('div.feed-grid__item'):
            try:
                link_elem = item.find('a', {'data-testid': 'grid-item'})
                if not link_elem or not link_elem.get('href'):
                    continue
                link = 'https://www.vinted.pl' + link_elem['href']

                title_elem = item.find('h3') or item.find('p', {'data-testid': lambda x: x and "title" in x})
                title = title_elem.text.strip() if title_elem else "Brak tytułu"

                price_elem = item.find('span', {'data-testid': lambda x: x and "price" in x})
                price = price_elem.text.strip() if price_elem else "Brak ceny"

                # Wejdź na stronę ogłoszenia i sprawdź opis
                try:
                    driver.get(link)
                    time.sleep(3)
                    detail_soup = BeautifulSoup(driver.page_source, 'lxml')
                    full_text = detail_soup.get_text().lower()
                    if any(keyword in full_text for keyword in blocked_keywords):
                        continue
                except Exception as e:
                    print(f"Błąd wejścia w ogłoszenie Vinted: {e}")
                    continue

                ads.append({'link': link, 'title': title, 'price': price})
            except Exception as e:
                print(f"Błąd ogłoszenia Vinted: {e}")
    finally:
        driver.quit()

    return ads

async def check_ads():
    await bot.wait_until_ready()

    for channel_id in config['CHANNELS']:
        channel = bot.get_channel(int(channel_id))
        if channel:
            await channel.send("🚀 ZAPIERDALAM !!!")

    while True:
        for channel_id, url in config['CHANNELS'].items():
            try:
                is_olx = 'olx.pl' in url
                ads = []

                if is_olx:
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'lxml')

                    for item in soup.select('[data-cy="l-card"]'):
                        if "Wyróżnione" in item.get_text():
                            continue
                        try:
                            link_tag = item.find('a', href=True)
                            if not link_tag:
                                continue
                            link = link_tag['href']
                            if not link.startswith('http'):
                                link = 'https://www.olx.pl' + link

                            title_elem = item.find('h4', class_='css-1g61gc2') or item.find('h4')
                            title = title_elem.text.strip() if title_elem else "Brak tytułu"

                            price_elem = item.find('p', {'data-testid': 'ad-price'})
                            price = price_elem.text.strip() if price_elem else "Brak ceny"

                            ads.append({'link': link, 'title': title, 'price': price})
                        except Exception as e:
                            print(f"OLX parse error: {e}")
                else:
                    ads = get_vinted_ads_with_selenium(url)

                memory = last_ads.get(url, [])
                known_links = [ad['link'] for ad in memory]
                new_ads = []

                for ad in ads:
                    if ad['link'] not in known_links:
                        if url in initialized:
                            new_ads.append(ad)
                        memory.append(ad)
                        if len(memory) > max_ads:
                            memory.pop(0)

                last_ads[url] = memory

                channel = bot.get_channel(int(channel_id))
                if channel:
                    if url not in initialized:
                        await channel.send("📦 Skończyłem zapisywać")
                        initialized.add(url)
                    else:
                        for ad in new_ads:
                            message = f"**NOWE OGŁOSZENIE!**\n"
                            message += f"**{ad['title']}**\n"
                            message += f"**Cena:** {ad['price']}\n"
                            message += f"{ad['link']}"
                            await channel.send(message)

            except Exception as e:
                print(f"Błąd dla {url}: {e}")

        await asyncio.sleep(check_interval)

@bot.event
async def on_ready():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Zalogowano jako {bot.user.name}")
    bot.loop.create_task(check_ads())

async def shutdown():
    for channel_id in config['CHANNELS']:
        channel = bot.get_channel(int(channel_id))
        if channel:
            await channel.send("⛔ STOP!!")
    await bot.close()
    sys.exit(0)

def handle_exit(*args):
    asyncio.get_event_loop().create_task(shutdown())

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

if __name__ == "__main__":
    bot.run(config["TOKEN"])