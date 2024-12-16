import json
import pyodbc
import schedule
import time
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime

# Initialize Flask app
app = Flask(__name__)

# Database connection string
conn_str = r"DRIVER={ODBC Driver 17 for SQL Server};SERVER=LAPTOP-Q6J5AJCG\SQLEXPRESS;DATABASE=Market_Automation;Trusted_Connection=yes;"

# Selenium setup
chrome_options = Options()
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
#chrome_options.add_argument("--headless")

# Function to scrape Cimri
def scrape_cimri(product_name):
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        url = f"https://www.cimri.com/market/arama?q={product_name}"
        driver.get(url)
        product_elements = driver.find_elements(By.CSS_SELECTOR, ".s-product")

        results = []
        for product in product_elements[:5]:
            try:
                name = product.find_element(By.CSS_SELECTOR, ".ProductCard_productName__35zi5").text
                price = product.find_element(By.CSS_SELECTOR, ".ProductCard_price__10UHp selectorgadget_rejected").text
                price = float(price.replace('TL', '').replace('.', '').replace(',', '.'))
                sname= product.find_element(By.CSS_SELECTOR, ".WrapperBox_wrapper__1_OBD WrapperBox_left__2PpFA WrapperBox_small__VfD9r").get_attribute("src")
                results.append({"product_name": name, "price": price, "store_name": sname})
            except Exception:
                continue

        driver.quit()
        return results
    except Exception as e:
        print(f"Error scraping Cimri: {e}")
        return []

# Function to scrape CarrefourSA
def scrape_carrefour(product_name):
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        url = f"https://www.carrefoursa.com/search/?text={product_name}"
        driver.get(url)
        product_elements = driver.find_elements(By.CSS_SELECTOR, ".pl-grid-cont")

        results = []
        for product in product_elements[:5]:
            try:
                name = product.find_element(By.CSS_SELECTOR, ".item-name selectorgadget_suggested").text
                price = product.find_element(By.CSS_SELECTOR, ".item-price js-variant-discounted-price").text
                price = float(price.replace('TL', '').replace('.', '').replace(',', '.'))
                results.append({"product_name": name, "price": price, "store_name": "CarrefourSA"})
            except Exception:
                continue

        driver.quit()
        return results
    except Exception as e:
        print(f"Error scraping CarrefourSA: {e}")
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
    except Exception as e:
        print(f"Database connection error: {e}")

# Function to fetch product history
def fetch_history():
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

        return [{
            "product_name": row[0],
            "cheapest_product": row[1],
            "cheapest_price": row[2],
            "cheapest_store": row[3],
            "most_expensive_product": row[4],
            "most_expensive_price": row[5],
            "most_expensive_store": row[6],
            "timestamp": row[7].strftime("%Y-%m-%d %H:%M:%S")
        } for row in rows]
    except Exception as e:
        print(f"Error fetching history: {e}")
        return []

# API routes
@app.route('/scrape', methods=['GET'])
def scrape():
    product_name = request.args.get('product_name')
    cimri_data = scrape_cimri(product_name)
    carrefour_data = scrape_carrefour(product_name)

    all_products = cimri_data + carrefour_data
    if all_products:
        cheapest = min(all_products, key=lambda x: x['price'])
        most_expensive = max(all_products, key=lambda x: x['price'])
        save_to_database(product_name, cheapest, most_expensive)
        return jsonify({"cheapest": cheapest, "most_expensive": most_expensive})

    return jsonify({"error": "No products found"})

@app.route('/history', methods=['GET'])
def history():
    return jsonify(fetch_history())

# Schedule automatic updates every 24 hours
def scheduled_updates():
    products_to_check = ["water", "milk", "bread", "eggs"]
    for product in products_to_check:
        cimri_data = scrape_cimri(product)
        carrefour_data = scrape_carrefour(product)
        all_products = cimri_data + carrefour_data
        if all_products:
            cheapest = min(all_products, key=lambda x: x['price'])
            most_expensive = max(all_products, key=lambda x: x['price'])
            save_to_database(product, cheapest, most_expensive)

schedule.every(24).hours.do(scheduled_updates)

if __name__ == '__main__':
    app.run(port=5000)
