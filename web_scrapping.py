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

# Initialize Flask app
app = Flask(__name__)

# Database connection string
conn_str = r"DRIVER={ODBC Driver 17 for SQL Server};SERVER=LAPTOP-Q6J5AJCG\SQLEXPRESS;DATABASE=Market_Automation;Trusted_Connection=yes;"

# Selenium setup
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# Function to scrape Amazon
def scrape_amazon(product_name):
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        url = f"https://www.amazon.com.tr/s?k={product_name}"
        driver.get(url)
        product_elements = driver.find_elements(By.CSS_SELECTOR, ".s-main-slot .s-result-item")

        results = []
        for product in product_elements[:5]:  # Limit to first 5 results for efficiency
            try:
                name = product.find_element(By.CSS_SELECTOR, "h2 a span").text
                brand = name.split()[0]  # Extract the brand name (first word)
                price = product.find_element(By.CSS_SELECTOR, ".a-price-whole").text
                price = float(price.replace('.', '').replace(',', '.'))  # Convert to float
                results.append({"product_name": name, "brand_name": brand, "price": price, "store_name": "Amazon"})
            except Exception as e:
                continue

        driver.quit()
        return results
    except Exception as e:
        print(f"Error scraping Amazon: {e}")
        return []

# Function to scrape Migros
def scrape_migros(product_name):
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        url = f"https://www.migros.com.tr/arama?q={product_name}"
        driver.get(url)
        product_elements = driver.find_elements(By.CSS_SELECTOR, ".product-card-wrapper")

        results = []
        for product in product_elements[:5]:
            try:
                name = product.find_element(By.CSS_SELECTOR, ".product-title").text
                brand = name.split()[0]  # Extract the brand name
                price = product.find_element(By.CSS_SELECTOR, ".product-price").text
                price = float(price.replace('TL', '').replace('.', '').replace(',', '.'))
                results.append({"product_name": name, "brand_name": brand, "price": price, "store_name": "Migros"})
            except Exception:
                continue

        driver.quit()
        return results
    except Exception as e:
        print(f"Error scraping Migros: {e}")
        return []

# Function to scrape CarrefourSA
def scrape_carrefour(product_name):
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        url = f"https://www.carrefoursa.com/search/?text={product_name}"
        driver.get(url)
        product_elements = driver.find_elements(By.CSS_SELECTOR, ".product-item")

        results = []
        for product in product_elements[:5]:
            try:
                name = product.find_element(By.CSS_SELECTOR, ".product-title").text
                brand = name.split()[0]  # Extract the brand name
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
    
# Function to save only the cheapest and most expensive product in the database
def save_to_database(products):
    try:
        connection = pyodbc.connect(conn_str)
        cursor = connection.cursor()

        # Find the cheapest and most expensive products
        cheapest = min(products, key=lambda x: x['price'])
        most_expensive = max(products, key=lambda x: x['price'])

        # Insert or update the cheapest product
        cursor.execute("""
            MERGE INTO Prices AS target
            USING (SELECT ? AS ProductName, ? AS BrandName, ? AS Price, ? AS StoreName) AS source
            ON target.ProductName = source.ProductName AND target.StoreName = source.StoreName
            WHEN MATCHED THEN
                UPDATE SET Price = source.Price, BrandName = source.BrandName, Timestamp = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (ProductName, BrandName, Price, StoreName)
                VALUES (source.ProductName, source.BrandName, source.Price, source.StoreName);
        """, (cheapest['product_name'], cheapest['brand_name'], cheapest['price'], cheapest['store_name']))

        # Insert or update the most expensive product
        cursor.execute("""
            MERGE INTO Prices AS target
            USING (SELECT ? AS ProductName, ? AS BrandName, ? AS Price, ? AS StoreName) AS source
            ON target.ProductName = source.ProductName AND target.StoreName = source.StoreName
            WHEN MATCHED THEN
                UPDATE SET Price = source.Price, BrandName = source.BrandName, Timestamp = GETDATE()
            WHEN NOT MATCHED THEN
                INSERT (ProductName, BrandName, Price, StoreName)
                VALUES (source.ProductName, source.BrandName, source.Price, source.StoreName);
        """, (most_expensive['product_name'], most_expensive['brand_name'], most_expensive['price'], most_expensive['store_name']))

        connection.commit()
        cursor.close()
        connection.close()
    except Exception as e:
        print(f"Database connection error: {e}")

# API route for scraping and comparing prices
@app.route('/scrape', methods=['GET'])
def scrape():
    product_name = request.args.get('product_name')
    amazon_data = scrape_amazon(product_name)
    migros_data = scrape_migros(product_name)
    carefour_data = scrape_carrefour(product_name)
    

    all_products = amazon_data + migros_data + carefour_data
   
    if all_products:
        save_to_database(all_products)

        # Find and return the cheapest and most expensive products
        cheapest = min(all_products, key=lambda x: x['price'])
        most_expensive = max(all_products, key=lambda x: x['price'])

        return jsonify({"cheapest": cheapest, "most_expensive": most_expensive})

    return jsonify({"error": "No products found"})

# Schedule automatic updates every 24 hours
def scheduled_updates():
    products_to_check = ["water", "milk", "bread", "eggs"]
    for product in products_to_check:
        scrape_amazon(product)
        scrape_migros(product)

schedule.every(24).hours.do(scheduled_updates)

if __name__ == '__main__':
    app.run(debug=True)
