import os
import json
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
            print(f"Error scraping {scraper['name']}: {e}")
            return []
        finally:
            driver.quit()

    def update_product_prices(self, product_name):
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
                return cheapest, most_expensive
            return None, None
        except Exception as e:
            print(f"Error updating database: {e}")
            return None, None
        finally:
            session.close()

    def get_product_prices(self, product_name):
        session = self.Session()
        try:
            products = session.query(ProductPrice).filter(
                ProductPrice.product_name.ilike(f"%{product_name}%")
            ).all()
            return products
        except Exception as e:
            print(f"Error retrieving products: {e}")
            return []
        finally:
            session.close()


app = Flask(__name__)

DATABASE_URL = "mssql+pyodbc://@localhost\\SQLEXPRESS/Market_Automation?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes"
engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

@app.route("/compare", methods=["GET"])
def compare_prices():
    product_name = request.args.get("product_name", "").strip()
    if not product_name:
        return jsonify({"error": "Product name is required"}), 400

    session = Session()
    try:
        results = session.query(ProductPrice).filter(ProductPrice.product_name.ilike(f"%{product_name}%")).all()
        if not results:
            return jsonify({"error": "No products found"}), 404

        response = [{"id": r.id, "product_name": r.product_name, "brand_name": r.brand_name, "price": r.price, "store_name": r.store_name, "image": r.image_url} for r in results]
        return jsonify({"products": response})
    finally:
        session.close()

@app.route("/history", methods=["GET"])
def fetch_history():
    session = Session()
    try:
        results = session.query(ProductPrice).all()
        response = [{"product_name": r.product_name, "brand_name": r.brand_name, "store_name": r.store_name, "price": r.price, "timestamp": r.timestamp.isoformat()} for r in results]
        return jsonify(response)
    finally:
        session.close()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)