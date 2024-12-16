import json
import pyodbc
import schedule
import time
import logging
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Database connection string
conn_str = r"DRIVER={ODBC Driver 17 for SQL Server};SERVER=LAPTOP-Q6J5AJCG\SQLEXPRESS;DATABASE=Market_Automation;Trusted_Connection=yes;"

# Selenium setup
chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--headless")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

# Function to scrape Cimri
def scrape_cimri(product_name):
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        url = f"https://www.cimri.com/market/arama?q={product_name}"
        logging.info(f"Scraping Cimri for product: {product_name}")
        driver.get(url)

        WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".Wrapper_productCard__1act7"))
        )

        product_elements = driver.find_elements(By.CSS_SELECTOR, ".Wrapper_productCard__1act7")
        results = []
        for product in product_elements[:10]:
            try:
                name = product.find_element(By.CSS_SELECTOR, ".ProductCard_productName__35zi5").text
                price = product.find_element(By.CSS_SELECTOR, ".ProductCard_footer__Fc9OL").text
                if not price.strip():
                    logging.warning(f"Empty price field for product: {name}")
                    continue
                main_price = float(price.split('\n')[0].replace('TL', '').replace('.', '').replace(',', '.'))
                results.append({"product_name": name, "price": main_price, "store_name": "Cimri"})
            except Exception as e:
                logging.warning(f"Error parsing product on Cimri: {e}")
                continue

        driver.quit()
        logging.info(f"Raw data from Cimri: {json.dumps(results, indent=4)}")
        return results
    except Exception as e:
        logging.error(f"Error scraping Cimri: {e}")
        return []

# Function to scrape Trendyol
def scrape_trendyol(product_name):
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        url = f"https://www.trendyol.com/sr?q={product_name}"
        logging.info(f"Scraping Trendyol for product: {product_name}")
        driver.get(url)

        WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".prdct-cntnr-wrppr selectorgadget_selected"))
        )

        product_elements = driver.find_elements(By.CSS_SELECTOR, ".prdct-cntnr-wrppr selectorgadget_selected")
        results = []
        for product in product_elements[:10]:
            try:
                name = product.find_element(By.CSS_SELECTOR, ".prdct-desc-cntnr").text
                price = product.find_element(By.CSS_SELECTOR, ".prc-box-dscntd selectorgadget_rejected").text
                if not price.strip():
                    logging.warning(f"Empty price field for product: {name}")
                    continue
                main_price = float(price.split('\n')[0].replace('TL', '').replace('.', '').replace(',', '.'))
                results.append({"product_name": name, "price": main_price, "store_name": "Trendyol"})
            except Exception as e:
                logging.warning(f"Error parsing product on Trendyol: {e}")
                continue

        driver.quit()
        logging.info(f"Raw data from Trendyol: {json.dumps(results, indent=4)}")
        return results
    except Exception as e:
        logging.error(f"Error scraping Trendyol: {e}")
        return []


# Function to save products to the database
def save_to_database(product_name, cheapest, most_expensive):
    try:
        connection = pyodbc.connect(conn_str)
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO Prices (ProductName, CheapestName, CheapestPrice, CheapestStore, 
                                MostExpensiveName, MostExpensivePrice, MostExpensiveStore, Timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, GETDATE())
        """, (
            product_name,
            cheapest['product_name'], cheapest['price'], cheapest['store_name'],
            most_expensive['product_name'], most_expensive['price'], most_expensive['store_name']
        ))

        connection.commit()
        cursor.close()
        connection.close()
        logging.info(f"Data saved to database for product: {product_name}")
    except Exception as e:
        logging.error(f"Database connection error: {e}")

# API route to scrape products and compare
@app.route('/scrape', methods=['GET'])
def scrape():
    product_name = request.args.get('product_name')

    # Scrape Cimri and Carrefour
    cimri_data = scrape_cimri(product_name)
    trendyol_data = scrape_trendyol(product_name)

    if not cimri_data and not trendyol_data:
        return jsonify({"error": "No products found on either website"})

    # Combine data and find cheapest and most expensive products
    all_data = cimri_data + trendyol_data

    # Validate data
    validated_data = []
    for item in all_data:
     try:
        if all(key in item for key in ['product_name', 'price', 'store_name']):
            item['price'] = float(item['price'])
            validated_data.append(item)
        else:
            logging.warning(f"Missing fields in product: {item}")
     except (ValueError, KeyError) as e:
        logging.warning(f"Invalid product data: {item}. Error: {e}")

    if not validated_data:
        logging.warning(f"No valid products. Raw data: {all_data}")
        return jsonify({
        "cheapest_overall": None,
        "most_expensive_overall": None,
        "error": "No valid products found"
    })

    # Find cheapest and most expensive products
    cheapest_overall = min(validated_data, key=lambda x: x['price'], default=None)
    most_expensive_overall = max(validated_data, key=lambda x: x['price'], default=None)

    # Ensure cheapest and most expensive are not the same
    if cheapest_overall and most_expensive_overall and cheapest_overall['price'] == most_expensive_overall['price']:
     validated_data = [item for item in validated_data if item != cheapest_overall]
    if validated_data:
        most_expensive_overall = max(validated_data, key=lambda x: x['price'], default=None)
    else:
        most_expensive_overall = cheapest_overall



    # Save to database
    if cheapest_overall and most_expensive_overall:
        save_to_database(product_name, cheapest_overall, most_expensive_overall)

    return jsonify({
        "cheapest_overall": cheapest_overall,
        "most_expensive_overall": most_expensive_overall
    })

# API route to fetch product price history
@app.route('/history', methods=['GET'])
def history():
    try:
        connection = pyodbc.connect(conn_str)
        cursor = connection.cursor()

        cursor.execute("""
            SELECT ProductName, CheapestName, CheapestPrice, CheapestStore,
                   MostExpensiveName, MostExpensivePrice, MostExpensiveStore, Timestamp
            FROM Prices ORDER BY Timestamp DESC
        """)
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

# Scheduled function to update the database every 24 hours
def scheduled_updates():
    try:
        connection = pyodbc.connect(conn_str)
        cursor = connection.cursor()

        cursor.execute("SELECT DISTINCT ProductName FROM Products")
        products = [row[0] for row in cursor.fetchall()]

        for product in products:
            cimri_data = scrape_cimri(product)
            carrefour_data = scrape_carrefour(product)

            all_data = cimri_data + carrefour_data
            validated_data = []

            for item in all_data:
                try:
                    item['price'] = float(item['price'])
                    if all(key in item for key in ['product_name', 'price', 'store_name']):
                        validated_data.append(item)
                except (ValueError, KeyError) as e:
                    logging.warning(f"Invalid product data during scheduled update: {item}. Error: {e}")

            if validated_data:
                cheapest = min(validated_data, key=lambda x: x['price'], default=None)
                most_expensive = max(validated_data, key=lambda x: x['price'], default=None)

                if cheapest and most_expensive:
                    save_to_database(product, cheapest, most_expensive)

        cursor.close()
        connection.close()
    except Exception as e:
        logging.error(f"Error during scheduled updates: {e}")

# Schedule the update
schedule.every(24).hours.do(scheduled_updates)

# Function to run the scheduler in a separate thread
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

# Run the Flask app and scheduler
if __name__ == '__main__':
    import threading
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    app.run(port=5000)
