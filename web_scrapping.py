import json
import pyodbc
import schedule
import time
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup as soup
from webdriver_manager.chrome import ChromeDriverManager

# Initialize Flask app
app = Flask(__name__)

# Database connection string
conn_str = r"DRIVER={ODBC Driver 17 for SQL Server};SERVER=LAPTOP-Q6J5AJCG\SQLEXPRESS;DATABASE=Market_Automation;Trusted_Connection=yes;"

# Selenium setup
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# Utility to clean prices
def get_price(price_str):
    clean_price = ''.join(c if c.isdigit() or c == '.' else '' for c in price_str)
    return float(clean_price) if clean_price else 0.0

# Scraper for a generic website (Selenium + BeautifulSoup)
def scrape_website(url, product_name, selectors):
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.get(url.format(product_name))
        time.sleep(2)  # Wait for dynamic content to load

        page_html = driver.page_source
        driver.quit()

        page_soup = soup(page_html, "html.parser")
        products = page_soup.select(selectors['product'])

        results = []
        for product in products[:5]:  # Limit to 5 results
            try:
                name = product.select_one(selectors['name']).text.strip()
                price = get_price(product.select_one(selectors['price']).text.strip())
                image = product.select_one(selectors['image'])['src']
                link = product.select_one(selectors['link'])['href']
                results.append({"product_name": name, "price": price, "image": image, "link": link})
            except Exception as e:
                continue
        return results
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return []

# Scrapers for specific websites
def scrape_amazon(product_name):
    selectors = {
        "product": ".s-main-slot .s-result-item",
        "name": "h2 a span",
        "price": ".a-price-whole",
        "image": "img.s-image",
        "link": "h2 a",
    }
    url = "https://www.amazon.com.tr/s?k={}"
    return scrape_website(url, product_name, selectors)

def scrape_migros(product_name):
    selectors = {
        "product": ".product-card-wrapper",
        "name": ".product-title",
        "price": ".product-price",
        "image": "img",
        "link": "a",
    }
    url = "https://www.migros.com.tr/arama?q={}"
    return scrape_website(url, product_name, selectors)

def scrape_carrefour(product_name):
    selectors = {
        "product": ".pl-grid-cont",
        "name": ".product-title",
        "price": ".product-price",
        "image": "img",
        "link": "a",
    }
    url = "https://www.carrefoursa.com/search/?text={}"
    return scrape_website(url, product_name, selectors)

# Save to database
def save_to_database(products):
    try:
        connection = pyodbc.connect(conn_str)
        cursor = connection.cursor()
        for product in products:
            cursor.execute("""
                MERGE INTO Prices AS target
                USING (SELECT ? AS ProductName, ? AS Price) AS source
                ON target.ProductName = source.ProductName
                WHEN MATCHED THEN UPDATE SET Price = source.Price, Timestamp = GETDATE()
                WHEN NOT MATCHED THEN INSERT (ProductName, Price) VALUES (source.ProductName, source.Price);
            """, (product['product_name'], product['price']))
        connection.commit()
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"Database error: {e}")

# API route
@app.route('/scrape', methods=['GET'])
def scrape():
    product_name = request.args.get('product_name', '')
    all_results = scrape_amazon(product_name) + scrape_migros(product_name) + scrape_carrefour(product_name)
    if all_results:
        save_to_database(all_results)
        cheapest = min(all_results, key=lambda x: x['price'])
        most_expensive = max(all_results, key=lambda x: x['price'])
        return jsonify({"cheapest": cheapest, "most_expensive": most_expensive})
    return jsonify({"error": "No products found"})

# Scheduler
def scheduled_updates():
    products = ["milk", "bread", "water"]
    for product in products:
        scrape_amazon(product)
        scrape_migros(product)
        scrape_carrefour(product)

schedule.every().day.at("00:00").do(scheduled_updates)

if __name__ == '__main__':
    app.run(debug=True)
