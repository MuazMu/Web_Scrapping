import os
import json
import logging
import threading
import time
from flask import Flask, request, jsonify
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
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import re
import schedule

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("PriceComparison")

# SQLAlchemy Base
Base = declarative_base()

# Database Model
class ProductPrice(Base):
    __tablename__ = "product_prices"
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_name = Column(String, nullable=False)
    brand_name = Column(String)
    store_name = Column(String)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    image_url = Column(String)
    product_url = Column(String)

# Price Comparison System
class PriceComparisonSystem:
    def __init__(self, database_url=None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            r"mssql+pyodbc://@localhost\SQLEXPRESS/Market_Automation?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes",
        )
        self.engine = create_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--no-sandbox")

        self.scrapers = [
            {
                "name": "Amazon TR",
                "url_template": "https://www.amazon.com.tr/s?k={}",
                "selectors": {
                    "product": ".s-result-item",
                    "name": "h2 a span",
                    "price": ".a-price-whole",
                    "image": "img.s-image",
                    "link": "h2 a",
                },
                "store_name": "Amazon",
            },
            {
                "name": "Migros",
                "url_template": "https://www.migros.com.tr/arama?q={}",
                "selectors": {
                    "product": ".product-card-wrapper",
                    "name": ".product-title",
                    "price": ".product-price",
                    "image": "img",
                    "link": "a",
                },
                "store_name": "Migros",
            },
            {            
                "name": "Carrefour",
                "url_template": "https://www.carrefoursa.com/search/?text={}",
                "selectors": {
                    "product": ".pl-grid-cont",
                    "name": ".product-title",
                    "price": ".product-price",
                    "image": "img",
                    "link": "a",
                    "brand": ".product-brand",
                },
                "store_name": "Carrefour",
            },
        ]

    def _clean_price(self, price_str):
        price = re.sub(r"[^\d.]", "", price_str)
        try:
            return float(price)
        except ValueError:
            return None

    def scrape_website(self, scraper, product_name):
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=self.chrome_options
        )
        try:
            driver.get(scraper["url_template"].format(product_name))
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, scraper["selectors"]["product"]))
            )
            soup = BeautifulSoup(driver.page_source, "html.parser")
            products = soup.select(scraper["selectors"]["product"])
            results = []
            for product in products[:5]:
                name = product.select_one(scraper["selectors"]["name"])
                price = product.select_one(scraper["selectors"]["price"])
                if not name or not price:
                    continue
                results.append({
                    "product_name": name.text.strip(),
                    "price": self._clean_price(price.text),
                    "store_name": scraper["store_name"],
                })
            return results
        except Exception as e:
            logger.error(f"Error scraping {scraper['name']}: {e}")
            return []
        finally:
            driver.quit()

    def update_cheapest_and_expensive(self, product_name):
        session = self.Session()
        try:
            results = []
            for scraper in self.scrapers:
                results.extend(self.scrape_website(scraper, product_name))
            if results:
                cheapest = min(results, key=lambda x: x["price"])
                most_expensive = max(results, key=lambda x: x["price"])
                session.add_all([
                    ProductPrice(**cheapest),
                    ProductPrice(**most_expensive),
                ])
                session.commit()
        except Exception as e:
            logger.error(f"Error updating database: {e}")
        finally:
            session.close()

# Flask Application
app = Flask(__name__)
CORS(app)
price_system = PriceComparisonSystem()

@app.route("/compare", methods=["GET"])
def compare_prices():
    product_name = request.args.get("product_name", "").strip()
    if not product_name:
        return jsonify({"error": "Product name is required"}), 400
    try:
        session = price_system.Session()
        results = session.query(ProductPrice).all()
        return jsonify([{"id": r.id, "name": r.product_name, "price": r.price} for r in results])
    except Exception as e:
        logger.error(f"Error in /compare: {e}")
        return jsonify({"error": "Internal server error"}), 500

# Schedule Automated Updates
def schedule_updates():
    schedule.every(24).hours.do(lambda: price_system.update_cheapest_and_expensive("laptop"))
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    threading.Thread(target=schedule_updates, daemon=True).start()
    app.run(debug=True)
