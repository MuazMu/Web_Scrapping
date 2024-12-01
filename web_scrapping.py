import os
import json
import logging
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
from threading import Thread
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import re

# Enhanced Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("price_comparison.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

Base = declarative_base()

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

class PriceComparisonSystem:
    def __init__(self, database_url="mssql+pyodbc://LAPTOP-Q6J5AJCG\SQLEXPRESS/Market_Automation?ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes"):
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")

        # More precise scrapers with brand and product name filtering
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
                    "brand": ".a-size-base",
                },
                "store_name": "Amazon",
            },
            
        ]

        self.scrapers = [
            {
                "name": "Migros",
                "url_template": "https://www.migros.com.tr/arama?q={}",
                "selectors": {
                    "product": ".product-card-wrapper",
                    "name": ".product-title",
                    "price": ".product-price",
                    "image": "img",
                    "link": "a",
                    "brand": ".product-brand",
                },
                "store_name": "Migros",
            }
        ]
        self.scrapers = [
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

    def _clean_text(self, text):
        """Clean text by removing extra whitespaces and special characters."""
        return re.sub(r'\s+', ' ', text).strip()

    def _clean_price(self, price_str):
        """Enhanced price cleaning method."""
        price = re.sub(r'[^\d.,]', '', price_str)
        price = price.replace(',', '.')
        try:
            return float(price)
        except ValueError:
            return None

    def _filter_relevant_products(self, products, search_term):
        """Filter products that match the search term more precisely."""
        search_term = search_term.lower()
        return [
            product for product in products 
            if search_term in product['product_name'].lower()
        ]

    def scrape_website(self, scraper, product_name):
        try:
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=self.chrome_options,
            )
            driver.get(scraper["url_template"].format(product_name))

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, scraper["selectors"]["product"])
                )
            )
            soup = BeautifulSoup(driver.page_source, "html.parser")
            products = soup.select(scraper["selectors"]["product"])

            results = []
            for product in products[:5]:  # Limit to top 5
                try:
                    name = self._clean_text(product.select_one(scraper["selectors"]["name"]).text)
                    price_elem = product.select_one(scraper["selectors"]["price"])
                    price = self._clean_price(price_elem.text) if price_elem else None
                    
                    if not price:
                        continue

                    image = product.select_one(scraper["selectors"]["image"])
                    image_url = image['src'] if image and 'src' in image.attrs else ''
                    
                    link_elem = product.select_one(scraper["selectors"]["link"])
                    link = link_elem['href'] if link_elem and 'href' in link_elem.attrs else ''
                    
                    brand_elem = product.select_one(scraper["selectors"].get("brand"))
                    brand = self._clean_text(brand_elem.text) if brand_elem else "Unknown"

                    results.append({
                        "product_name": name,
                        "price": price,
                        "brand_name": brand,
                        "store_name": scraper["store_name"],
                        "image": image_url,
                        "link": link,
                    })
                except Exception as e:
                    logger.error(f"Error processing product: {e}")
            
            driver.quit()
            return self._filter_relevant_products(results, product_name)
        except Exception as e:
            logger.error(f"Error scraping {scraper['name']}: {e}")
            return []

    def compare_prices(self, product_name):
        all_results = []

        def scrape_and_add(scraper):
            results = self.scrape_website(scraper, product_name)
            all_results.extend(results)

        threads = [
            Thread(target=scrape_and_add, args=(scraper,)) for scraper in self.scrapers
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        if not all_results:
            return {"error": "No products found"}

        cheapest = min(all_results, key=lambda x: x["price"])
        most_expensive = max(all_results, key=lambda x: x["price"])
        return {
            "cheapest": cheapest,
            "most_expensive": most_expensive,
            "all_results": all_results,
        }


app = Flask(__name__)
CORS(app)
price_system = PriceComparisonSystem()


@app.route("/compare", methods=["GET"])
def compare_prices():
    product_name = request.args.get("product_name", "").strip()
    if not product_name:
        return jsonify({"error": "Product name is required"}), 400
    
    try:
        result = price_system.compare_prices(product_name)
        if "error" in result:
            return jsonify(result), 404
        return jsonify(result)
    except Exception as e:
        logger.error(f"API Error: {e}")
        return jsonify({"error": "Internal server error"}), 500

# New route to get product tracking history
@app.route("/history", methods=["GET"])
def get_product_history():
    search_term = request.args.get("search_term")
    price_type = request.args.get("price_type")
    
    if not price_system.db_manager:
        return jsonify({"error": "Database not configured"}), 500
    
    history = price_system.db_manager.get_product_history(search_term, price_type)
    
    # Convert SQLAlchemy objects to dictionary
    history_data = [{
        "id": item.id,
        "product_name": item.product_name,
        "brand_name": item.brand_name,
        "store_name": item.store_name,
        "price": item.price,
        "timestamp": item.timestamp.isoformat()
    } for item in history]
    
    return jsonify(history_data)

# Configuration
if __name__ == "__main__":
    # SQL Server connection string example
    SQL_SERVER_CONNECTION = (
        "mssql+pyodbc://username:password@servername/database"
        "?driver=ODBC+Driver+17+for+SQL+Server"
    )
    
    # Initialize with SQL Server connection
    price_system = PriceComparisonSystem(
        sql_server_connection_string=SQL_SERVER_CONNECTION
    )
    
    app.run(debug=True, use_reloader=False)
