import os
import json
import pyodbc
import schedule
import time
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('price_comparison.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Data Model
Base = declarative_base()

class ProductPrice(Base):
    __tablename__ = 'product_prices'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_name = Column(String, nullable=False)
    brand_name = Column(String)
    store_name = Column(String)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    image_url = Column(String)
    product_url = Column(String)

@dataclass
class ProductScraper:
    name: str
    url_template: str
    selectors: Dict[str, str]
    store_name: str

class PriceComparisonSystem:
    def __init__(self, database_url='sqlite:///price_comparison.db'):
        # Database setup
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        # Selenium setup
        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")

        # Scrapers configuration
        self.scrapers = [
            ProductScraper(
                name="Amazon",
                url_template="https://www.amazon.com.tr/s?k={}",
                selectors={
                    "product": ".s-main-slot .s-result-item",
                    "name": "h2 a span",
                    "price": ".a-price-whole",
                    "image": "img.s-image",
                    "link": "h2 a",
                    "brand": ".s-line-clamp-1"
                },
                store_name="Amazon"
            ),
            ProductScraper(
                name="Migros",
                url_template="https://www.migros.com.tr/arama?q={}",
                selectors={
                    "product": ".product-card-wrapper",
                    "name": ".product-title",
                    "price": ".product-price",
                    "image": "img",
                    "link": "a",
                    "brand": ".product-brand"
                },
                store_name="Migros"
            ),
            ProductScraper(
                name="Carrefour",
                url_template="https://www.carrefoursa.com/search/?text={}",
                selectors={
                    "product": ".pl-grid-cont",
                    "name": ".product-title",
                    "price": ".product-price",
                    "image": "img",
                    "link": "a",
                    "brand": ".product-brand"
                },
                store_name="Carrefour"
            )
        ]

    def _clean_price(self, price_str: str) -> float:
        """Clean and convert price string to float."""
        clean_price = ''.join(c if c.isdigit() or c == '.' else '' for c in price_str)
        return float(clean_price) if clean_price else 0.0

    def scrape_website(self, scraper: ProductScraper, product_name: str) -> List[Dict]:
        """Scrape a specific website for product information."""
        try:
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=self.chrome_options
            )
            driver.get(scraper.url_template.format(product_name))
            
            # Wait for dynamic content
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, scraper.selectors['product']))
            )

            page_soup = BeautifulSoup(driver.page_source, "html.parser")
            products = page_soup.select(scraper.selectors['product'])

            results = []
            for product in products[:5]:  # Limit results
                try:
                    name = product.select_one(scraper.selectors['name']).text.strip()
                    price = self._clean_price(product.select_one(scraper.selectors['price']).text.strip())
                    image = product.select_one(scraper.selectors['image'])['src']
                    link = product.select_one(scraper.selectors['link'])['href']
                    brand = product.select_one(scraper.selectors.get('brand', '')).text.strip() if 'brand' in scraper.selectors else "N/A"

                    results.append({
                        "product_name": name,
                        "price": price,
                        "brand_name": brand,
                        "store_name": scraper.store_name,
                        "image": image,
                        "link": link
                    })
                except Exception as e:
                    logger.error(f"Error processing product: {e}")

            driver.quit()
            return results

        except Exception as e:
            logger.error(f"Error scraping {scraper.name}: {e}")
            return []

    def compare_prices(self, product_name: str) -> Dict:
        """Compare prices across multiple stores."""
        all_results = []
        threads = []

        # Parallel scraping
        def scrape_and_extend(scraper):
            results = self.scrape_website(scraper, product_name)
            all_results.extend(results)

        for scraper in self.scrapers:
            thread = threading.Thread(target=scrape_and_extend, args=(scraper,))
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

        if not all_results:
            return {"error": "No products found"}

        # Save results to database
        self._save_to_database(all_results)

        # Find cheapest and most expensive
        cheapest = min(all_results, key=lambda x: x['price'])
        most_expensive = max(all_results, key=lambda x: x['price'])

        return {
            "cheapest": cheapest,
            "most_expensive": most_expensive,
            "all_results": all_results
        }

    def _save_to_database(self, products: List[Dict]):
        """Save product prices to database."""
        session = self.Session()
        try:
            for product in products:
                db_product = ProductPrice(
                    product_name=product['product_name'],
                    brand_name=product['brand_name'],
                    store_name=product['store_name'],
                    price=product['price'],
                    image_url=product['image'],
                    product_url=product['link']
                )
                session.merge(db_product)
            session.commit()
        except Exception as e:
            logger.error(f"Database error: {e}")
            session.rollback()
        finally:
            session.close()

# Flask API
app = Flask(__name__)
CORS(app)
price_system = PriceComparisonSystem()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/compare', methods=['GET'])
def compare_prices():
    product_name = request.args.get('product_name', '')
    if not product_name:
        return jsonify({"error": "Product name is required"}), 400
    
    result = price_system.compare_prices(product_name)
    return jsonify(result)

def run_scheduler():
    """Background scheduler for periodic updates."""
    schedule.every().day.at("00:00").do(update_periodic_products)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

def update_periodic_products():
    """Update prices for common grocery items."""
    common_products = ["milk", "bread", "eggs", "water", "cheese"]
    for product in common_products:
        price_system.compare_prices(product)

if __name__ == '__main__':
    # Start scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.start()

    # Run Flask app
    app.run(debug=True, use_reloader=False)