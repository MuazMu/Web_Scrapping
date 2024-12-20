import json
import logging
import spacy
import pyodbc
import csv
from flask import Flask, request, jsonify, Response
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import threading
import time
import urllib.parse
import re

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Database connection string
conn_str = r"#"

# SpaCy model for text processing
nlp = spacy.blank("en")

# Selenium setup
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("user-agent=Mozilla/5.0")

def get_store_urls():
    """Get the mapping of store names to their base URLs."""
    return {
        "amazon": "https://www.amazon.com.tr/s?k=",
        "migros": "https://www.migros.com.tr/arama?q=",
        "trendyol": "https://www.trendyol.com/sr?q=",
        "hepsiburada": "https://www.hepsiburada.com/ara?q=",
        "sok": "https://www.sokmarket.com.tr/arama?q=",
        "cimri": "https://www.cimri.com/market/arama?q="
    }

def name_to_url(name):
    """Map store names to their base URLs."""
    return get_store_urls().get(name.lower())

def extract_selectors(store_name):
    """Get selectors based on store name."""
    selectors = {
        "amazon": {
            "product_card": ".s-result-item",
            "name": ".a-text-normal",
            "price": ".a-price .a-offscreen",
        },
        "trendyol": {
            "product_card": ".prdct-cntnr-wrppr",
            "name": ".prdct-desc-cntnr-name",
            "price": ".prc-box-dscntd",
        },
        "migros": {
            "product_card": ".product-cards",
            "name": ".product-name",
            "price": ".price",
        },
        "sok": {
            "product_card": ".category-listing_productListing__etprE",
            "name": ".CProductCard-module_title__u8bMW",
            "price": ".CPriceBox-module_price__bYk-c",
        },
        "cimri": {
            "product_card": ".Wrapper_productCard__1act7",
            "name": ".ProductCard_productName__35zi5",
            "price": ".ProductCard_footer__Fc9OL",
        },
        "hepsiburada": {
            "product_card": ".productListContent-wrapper",
            "name": "h3.product-title",
            "price": ".price-value",
        },
        "default": {
            "product_card": ".product-card, .product-item, .product",
            "name": ".product-name, .title, .name",
            "price": ".price, .product-price, .amount",
        }
    }
    return selectors.get(store_name, selectors["default"])

def scrape_website(store_name, product_name):
    """Scrape a single website using predefined selectors and URLs."""
    try:
        url = name_to_url(store_name)
        if not url:
            logging.error(f"Could not determine URL for store name: {store_name}")
            return []

        selectors = extract_selectors(store_name)
        search_url = f"{url}{urllib.parse.quote(product_name)}"
        
        logging.info(f"Scraping {search_url} for store {store_name}")

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        try:
            driver.get(search_url)
            for selector in selectors["product_card"].split(", "):
                try:
                    WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    break
                except Exception:
                    continue

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(2)

            products = []
            for selector in selectors["product_card"].split(", "):
                products = driver.find_elements(By.CSS_SELECTOR, selector)
                if products:
                    break

            results = []
            for product in products[:5]:
                try:
                    name = None
                    for name_selector in selectors["name"].split(", "):
                        try:
                            name = product.find_element(By.CSS_SELECTOR, name_selector).text.strip()
                            if name:
                                break
                        except Exception:
                            continue

                    price_text = None
                    for price_selector in selectors["price"].split(", "):
                        try:
                            price_text = product.find_element(By.CSS_SELECTOR, price_selector).text.strip()
                            if price_text:
                                break
                        except Exception:
                            continue

                    if name and price_text:
                        price_match = re.search(r'\d+(?:[.,]\d+)?', price_text.replace('.', '').replace(',', '.'))
                        if price_match:
                            price = float(price_match.group())
                            results.append({
                                "product_name": name,
                                "price": price,
                                "store_name": store_name,
                                "url": search_url
                            })

                except Exception as e:
                    logging.warning(f"Error parsing product on {store_name}: {e}")
                    continue

            return results

        except Exception as e:
            logging.error(f"Error scraping {store_name}: {e}")
            return []

        finally:
            driver.quit()

    except Exception as e:
        logging.error(f"Fatal error scraping {store_name}: {e}")
        return []

def save_to_database(product_name, cheapest, most_expensive):
    """Save comparison results to database."""
    try:
        connection = pyodbc.connect(conn_str)
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO Prices (ProductName, CheapestName, CheapestPrice, CheapestStore, 
                              MostExpensiveName, MostExpensivePrice, MostExpensiveStore, Timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
            """,
            (
                product_name,
                cheapest['product_name'], cheapest['price'], cheapest['store_name'],
                most_expensive['product_name'], most_expensive['price'], most_expensive['store_name']
            )
        )

        connection.commit()
        cursor.close()
        connection.close()
        logging.info(f"Data saved to database for product: {product_name}")
    except Exception as e:
        logging.error(f"Database connection error: {e}")

def compare_prices(data):
    """Compare prices to find cheapest and most expensive products."""
    valid_data = [item for item in data if item["price"] > 0]
    if not valid_data:
        return None, None

    cheapest = min(valid_data, key=lambda x: x['price'])
    most_expensive = max(valid_data, key=lambda x: x['price'])

    return cheapest, most_expensive

@app.route('/scrape', methods=['POST'])
def scrape():
    """Endpoint to scrape products from provided store names."""
    try:
        data = request.get_json()
        product_name = data.get('product_name')
        store_names = data.get('urls', [])  # Now we expect store names (like "amazon", "trendyol", etc.)

        if not product_name:
            return jsonify({"error": "product_name is required"}), 400
        
        if not store_names:
            return jsonify({"error": "At least one store name is required"}), 400

        all_results = []
        for store_name in store_names:
            try:
                # Map store name to URL using the name_to_url function
                url = name_to_url(store_name)
                if not url:
                    logging.error(f"Could not determine URL for store name: {store_name}")
                    continue  # Skip this store if we cannot map it to a URL

                # Now scrape the website with the generated URL
                results = scrape_website(store_name, product_name)
                all_results.extend(results)
            except Exception as e:
                logging.error(f"Error scraping store {store_name}: {e}")
                continue

        if not all_results:
            return jsonify({"error": "No products found"}), 404

        # Find cheapest and most expensive products
        valid_results = [r for r in all_results if r["price"] > 0]
        if not valid_results:
            return jsonify({"error": "No valid prices found"}), 404

        cheapest = min(valid_results, key=lambda x: x["price"])
        most_expensive = max(valid_results, key=lambda x: x["price"])

        return jsonify({
            "cheapest_overall": cheapest,
            "most_expensive_overall": most_expensive,
            "total_products_found": len(valid_results),
            "all_results": all_results
        })

    except Exception as e:
        logging.error(f"Error in scrape endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/history', methods=['GET'])
def history():
    """Endpoint to fetch scraping history."""
    try:
        connection = pyodbc.connect(conn_str)
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT ProductName, CheapestName, CheapestPrice, CheapestStore,
                   MostExpensiveName, MostExpensivePrice, MostExpensiveStore, Timestamp
            FROM Prices ORDER BY Timestamp DESC
            """
        )

        rows = cursor.fetchall()
        cursor.close()
        connection.close()

        return jsonify([{
            "product_name": row[0],
            "cheapest_product": row[1],
            "cheapest_price": row[2],
            "cheapest_store": row[3],
            "most_expensive_product": row[4],
            "most_expensive_price": row[5],
            "most_expensive_store": row[6],
            "timestamp": row[7].strftime("%Y-%m-%d %H:%M:%S")
        } for row in rows])
    except Exception as e:
        logging.error(f"Error fetching history: {e}")
        return jsonify({"error": "Failed to fetch history"})

@app.route('/export', methods=['GET'])
def export_data():
    """Endpoint to export data to CSV."""
    try:
        connection = pyodbc.connect(conn_str)
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT ProductName, CheapestName, CheapestPrice, CheapestStore,
                   MostExpensiveName, MostExpensivePrice, MostExpensiveStore, Timestamp
            FROM Prices ORDER BY Timestamp DESC
            """
        )

        rows = cursor.fetchall()
        cursor.close()
        connection.close()

        # Prepare CSV response
        csv_file = "product_data.csv"
        with open(csv_file, mode='w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Product Name", "Cheapest Name", "Cheapest Price", "Cheapest Store",
                "Most Expensive Name", "Most Expensive Price", "Most Expensive Store",
                "Timestamp"
            ])
            for row in rows:
                writer.writerow(row)

        with open(csv_file, "r", encoding="utf-8-sig") as f:
            csv_data = f.read()

        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={csv_file}"}
        )

    except Exception as e:
        logging.error(f"Error exporting data: {e}")
        return jsonify({"error": "Failed to export data"}), 500

def automatic_update():
    """Automatically update prices every 24 hours."""
    logging.info("Waiting 24 hours before starting the first automatic update.")
    time.sleep(86400)  # Wait for 24 hours before the first update
    
    while True:
        try:
            logging.info("Starting automatic update for products")
            connection = pyodbc.connect(conn_str)
            cursor = connection.cursor()

            cursor.execute("""
                SELECT DISTINCT p.ProductName,
                    p.CheapestStore + '.com.tr' as CheapestURL,
                    p.MostExpensiveStore + '.com.tr' as MostExpensiveURL
                FROM Prices p
            """)
            products = cursor.fetchall()
            cursor.close()
            connection.close()

            for product_row in products:
                product_name = product_row[0]
                store_names = [
                    product_row[1],
                    product_row[2]
                ]
                
                all_results = []
                for store_name in store_names:
                    try:
                        results = scrape_website(store_name, product_name)
                        all_results.extend(results)
                    except Exception as e:
                        logging.error(f"Error scraping {store_name} for {product_name}: {e}")
                        continue

                if all_results:
                    cheapest, most_expensive = compare_prices(all_results)
                    if cheapest and most_expensive:
                        save_to_database(product_name, cheapest, most_expensive)

            logging.info("Automatic update completed")
        except Exception as e:
            logging.error(f"Error during automatic update: {e}")

        time.sleep(86400)  # Wait 24 hours before next update

# Start the automatic update in a separate thread
threading.Thread(target=automatic_update, daemon=True).start()

if __name__ == '__main__':
    app.run(port=5000)
