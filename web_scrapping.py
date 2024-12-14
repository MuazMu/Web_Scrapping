import os
import logging
import re
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
from apscheduler.schedulers.background import BackgroundScheduler

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

    def to_dict(self):
        return {
            "product_name": self.product_name,
            "brand_name": self.brand_name,
            "store_name": self.store_name,
            "price": self.price,
            "timestamp": self.timestamp.isoformat()
        }

# Price Comparison System
class PriceComparisonSystem:
    def __init__(self, database_url=None):
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            r"mssql+pyodbc://@localhost\SQLEXPRESS/Market_Automation?driver=ODBC+Driver+17+for+SQL+Server&Trusted_Connection=yes"
        )
        try:
            self.engine = create_engine(self.database_url, pool_pre_ping=True)
            Base.metadata.create_all(self.engine)
            self.Session = sessionmaker(bind=self.engine)
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            raise

        self.chrome_options = Options()
        self.chrome_options.add_argument("--no-sandbox")
        self.chrome_options.add_argument("--disable-dev-shm-usage")
        self.chrome_options.add_argument("--headless")
        self.chrome_options.add_argument("--disable-gpu")

    def _clean_price(self, price_str):
        if not price_str:
            return None
        try:
            price = re.sub(r'[^\d.,]', '', price_str).replace(',', '.')
            return float(price)
        except ValueError:
            logger.warning(f"Failed to clean price: {price_str}")
            return None

    def _create_webdriver(self):
        try:
            return webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=self.chrome_options
            )
        except WebDriverException as e:
            logger.error(f"WebDriver error: {e}")
            return None

    def scrape_akakce(self, product_name):
        driver = self._create_webdriver()
        if not driver:
            return []

        try:
            url = f"https://www.akakce.com/arama/?q={product_name.replace(' ', '+')}"
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".pList"))
            )

            results = []
            product_elements = driver.find_elements(By.CSS_SELECTOR, ".pList")[:5]
            for product in product_elements:
                try:
                    name_elem = product.find_element(By.CSS_SELECTOR, ".pName a")
                    name = name_elem.text.strip()
                    price_elem = product.find_element(By.CSS_SELECTOR, ".pFiyat")
                    price = self._clean_price(price_elem.text.strip())
                    brand = name.split()[0] if name else "Unknown"
                    results.append({
                        "product_name": name,
                        "brand_name": brand,
                        "price": price,
                        "store_name": "Akakce"
                    })
                except Exception as e:
                    logger.warning(f"Error processing Akakce product: {e}")
            return results
        except Exception as e:
            logger.error(f"Akakce scraping error: {e}")
            return []
        finally:
            driver.quit()

    def scrape_cimri(self, product_name):
        driver = self._create_webdriver()
        if not driver:
            return []

        try:
            url = f"https://www.cimri.com/arama?q={product_name.replace(' ', '+')}"
            driver.get(url)
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "[data-testid='product-card']"))
            )

            results = []
            product_elements = driver.find_elements(By.CSS_SELECTOR, "[data-testid='product-card']")[:5]
            for product in product_elements:
                try:
                    name_elem = product.find_element(By.CSS_SELECTOR, "[data-testid='product-name']")
                    name = name_elem.text.strip()
                    price_elem = product.find_element(By.CSS_SELECTOR, "[data-testid='product-price']")
                    price = self._clean_price(price_elem.text.strip())
                    brand = name.split()[0] if name else "Unknown"
                    results.append({
                        "product_name": name,
                        "brand_name": brand,
                        "price": price,
                        "store_name": "Cimri"
                    })
                except Exception as e:
                    logger.warning(f"Error processing Cimri product: {e}")
            return results
        except Exception as e:
            logger.error(f"Cimri scraping error: {e}")
            return []
        finally:
            driver.quit()

    def update_product_prices(self, product_name):
        session = self.Session()
        try:
            results = self.scrape_akakce(product_name) + self.scrape_cimri(product_name)
            valid_results = [r for r in results if r['price'] is not None]

            if valid_results:
                cheapest = min(valid_results, key=lambda x: x['price'])
                most_expensive = max(valid_results, key=lambda x: x['price'])
                session.add_all([ProductPrice(**cheapest), ProductPrice(**most_expensive)])
                session.commit()
                return cheapest, most_expensive

            logger.warning(f"No valid results for product: {product_name}")
            return None, None
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"Database error: {e}")
            return None, None
        finally:
            session.close()

# Flask App
def create_app():
    app = Flask(__name__)
    CORS(app)
    price_system = PriceComparisonSystem()

    @app.route("/compare", methods=["GET"])
    def compare_prices():
        product_name = request.args.get("product_name", "").strip()
        if not product_name:
            return jsonify({"error": "Product name is required"}), 400

        session = price_system.Session()
        try:
            results = session.query(ProductPrice).filter_by(product_name=product_name).all()
            if not results:
                return jsonify({"error": "No products found"}), 404

            sorted_results = sorted(results, key=lambda x: x.price)
            return jsonify({
                "cheapest": sorted_results[0].to_dict(),
                "most_expensive": sorted_results[-1].to_dict(),
            })
        except SQLAlchemyError as e:
            return jsonify({"error": str(e)}), 500
        finally:
            session.close()

    @app.route("/history", methods=["GET"])
    def fetch_history():
        session = price_system.Session()
        try:
            results = session.query(ProductPrice).all()
            return jsonify([r.to_dict() for r in results])
        except SQLAlchemyError as e:
            return jsonify({"error": str(e)}), 500
        finally:
            session.close()

    return app

def schedule_updates():
    price_system = PriceComparisonSystem()
    session = price_system.Session()
    try:
        product_names = session.query(ProductPrice.product_name).distinct().all()
        for name_tuple in product_names:
            price_system.update_product_prices(name_tuple[0])
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
    finally:
        session.close()

def main():
    scheduler = BackgroundScheduler()
    scheduler.add_job(schedule_updates, 'interval', hours=24)
    scheduler.start()

    app = create_app()
    app.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    main()
