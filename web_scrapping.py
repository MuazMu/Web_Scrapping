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

# Logging Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("price_comparison.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Database Configuration
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
    def __init__(self, database_url="sqlite:///price_comparison.db"):
        self.engine = create_engine(database_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

        # Selenium Configuration
        self.chrome_options = Options()
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")

        # Scrapers Configuration
        self.scrapers = [
            {
                "name": "Amazon",
                "url_template": "https://www.amazon.com.tr/s?k={}",
                "selectors": {
                    "product": ".s-main-slot .s-result-item",
                    "name": "h2 a span",
                    "price": ".a-price-whole",
                    "image": "img.s-image",
                    "link": "h2 a",
                    "brand": ".s-line-clamp-1",
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
                    "brand": ".product-brand",
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
        return float("".join(c for c in price_str if c.isdigit() or c == "."))

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
                    name = product.select_one(scraper["selectors"]["name"]).text.strip()
                    price = self._clean_price(
                        product.select_one(scraper["selectors"]["price"]).text.strip()
                    )
                    image = product.select_one(scraper["selectors"]["image"])["src"]
                    link = product.select_one(scraper["selectors"]["link"])["href"]
                    brand = product.select_one(scraper["selectors"].get("brand")).text.strip() if scraper["selectors"].get("brand") else "N/A"

                    results.append(
                        {
                            "product_name": name,
                            "price": price,
                            "brand_name": brand,
                            "store_name": scraper["store_name"],
                            "image": image,
                            "link": link,
                        }
                    )
                except Exception as e:
                    logger.error(f"Error processing product: {e}")
            driver.quit()
            return results
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


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
