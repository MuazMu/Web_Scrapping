import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import re
from apscheduler.schedulers.background import BackgroundScheduler
from webdriver_manager.chrome import ChromeDriverManager

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

# Chrome options for headless browsing
chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
#chrome_options.add_argument("--headless")
chrome_options.add_argument(
    "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36"
)

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

    def _clean_price(self, price_str):
        price = re.sub(r"[^\d.]", "", price_str)
        try:
            return float(price)
        except ValueError:
            return None
        
        
    def scrape_carrefour(self, product_name):
        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            url = f"https://www.carrefoursa.com/search/?text={product_name}"
            driver.get(url)
            product_elements = driver.find_elements(By.CSS_SELECTOR, ".pl-grid-cont .item-box")

            results = []
            for product in product_elements[:5]:
                try:
                    name = product.find_element(By.CSS_SELECTOR, ".item-name").text
                    brand = name.split()[0]
                    price = product.find_element(By.CSS_SELECTOR, ".price-tag").text
                    price = float(price.replace('TL', '').replace('.', '').replace(',', '.'))
                    results.append({"product_name": name, "brand_name": brand, "price": price, "store_name": "CarrefourSA"})
                except Exception:
                    continue

            driver.quit()
            return results
        except Exception as e:
            print(f"Error scraping CarrefourSA: {e}")
            return []
        

    def scrape_a101(self, product_name):
        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            url = f"https://www.a101.com.tr/arama?k={product_name}"
            driver.get(url)
            product_elements = driver.find_elements(By.CSS_SELECTOR, ".product")

            results = []
            for product in product_elements[:5]:  # Limit to first 5 results
                try:
                    name = product.find_element(By.CSS_SELECTOR, ".product-name").text 
                    brand = name.split()[0] 
                    price = product.find_element(By.CSS_SELECTOR, ".product-price").text 
                    price = float(price.replace('.', '').replace(',', '.')) 
                    results.append({"product_name": name, "brand_name": brand, "price": price, "store_name": "A101"})
                except Exception:
                    continue

            driver.quit()
            return results
        except Exception as e:
            print(f"Error scraping Amazon: {e}")
            return []

    def scrape_migros(self, product_name):
        try:
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            url = f"https://www.migros.com.tr/arama?q={product_name}"
            driver.get(url)
            product_elements = driver.find_elements(By.CSS_SELECTOR, ".product-card-wrapper")

            results = []
            for product in product_elements[:5]:
                try:
                    name = product.find_element(By.CSS_SELECTOR, ".product-name").text
                    brand = name.split()[0]
                    price = product.find_element(By.CSS_SELECTOR, ".price-tag").text
                    price = float(price.replace('TL', '').replace('.', '').replace(',', '.'))
                    results.append({"product_name": name, "brand_name": brand, "price": price, "store_name": "Migros"})
                except Exception:
                    continue

            driver.quit()
            return results
        except Exception as e:
            print(f"Error scraping Migros: {e}")
            return []


    def update_product_prices(self, product_name):
        session = self.Session()
        try:
            results = []
            results.extend(self.scrape_carrefour(product_name))
            results.extend(self.scrape_a101(product_name))
            results.extend(self.scrape_migros(product_name))
            

            if results:
                cheapest = min(results, key=lambda x: x["price"])
                most_expensive = max(results, key=lambda x: x["price"])

                session.add_all([ProductPrice(**cheapest), ProductPrice(**most_expensive)])
                session.commit()
                return cheapest, most_expensive
            return None, None
        except Exception as e:
            print(f"Error updating database: {e}")
            return None, None
        finally:
            session.close()

# Flask App
app = Flask(__name__)
CORS(app)

price_system = PriceComparisonSystem()

@app.route("/compare", methods=["GET"])
def compare_prices():
    product_name = request.args.get("product_name", "").strip()
    if not product_name:
        return jsonify({"error": "Product name is required"}), 400

    cheapest, most_expensive = price_system.update_product_prices(product_name)
    if cheapest and most_expensive:
        return jsonify({
            "cheapest": cheapest,
            "most_expensive": most_expensive,
        })
    return jsonify({"error": "No products found"}), 404

@app.route("/history", methods=["GET"])
def fetch_history():
    session = price_system.Session()
    try:
        results = session.query(ProductPrice).all()
        response = [
            {
                "product_name": r.product_name,
                "store_name": r.store_name,
                "price": r.price,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in results
        ]
        return jsonify(response)
    finally:
        session.close()

def schedule_updates():
    session = price_system.Session()
    try:
        product_names = session.query(ProductPrice.product_name).distinct().all()
        for name in product_names:
            price_system.update_product_prices(name[0])
    except Exception as e:
        print(f"Error in scheduled updates: {e}")
    finally:
        session.close()

scheduler = BackgroundScheduler()
scheduler.add_job(schedule_updates, "interval", hours=24)
scheduler.start()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
