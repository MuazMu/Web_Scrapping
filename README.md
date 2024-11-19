Price Scraper for Amazon and Migros (TR)
This is a Python Flask application that scrapes Amazon.tr and Migros.com.tr for product prices and saves the cheapest and most expensive products to a SQL Server database.

Features:

Scrapes product name, brand, and price from both websites.
Saves only the cheapest and most expensive products for each store.
Schedules automatic updates every 24 hours (configurable).
Provides a simple API endpoint to trigger scraping on demand.
Requirements:

Python 3.x
Flask framework
PyODBC library for connecting to SQL Server
Selenium library for web scraping
webdriver_manager for managing Chrome driver
Chrome web browser (headless mode recommended)
Setup:

Install dependencies:
Bash
pip install Flask pyodbc selenium webdriver-manager
Use code with caution.

Configure database connection:
Update the conn_str variable in the code with your SQL Server connection string.
Ensure you have a table named Prices with columns ProductName (nvarchar(max)), BrandName (nvarchar(max)), Price (float), StoreName (nvarchar(max)), and Timestamp (datetime).
Download Chrome driver:
Download the appropriate Chrome driver for your system from https://github.com/SergeyPirogov/webdriver_manager
Place the driver executable in your system PATH or specify the path in ChromeDriverManager().install().
Running the application:

Start the application:
Bash
python app.py
Use code with caution.

This will run the Flask server in debug mode.
Using the API:

Trigger scraping on demand:

curl http://localhost:5000/scrape?product_name=coffee
Replace coffee with the desired product name.

This will return a JSON response containing the cheapest and most expensive products from both stores.

Scheduled updates:

The application automatically scrapes a pre-defined list of products (water, milk, bread, eggs) every 24 hours.
You can modify the products_to_check list in the scheduled_updates function to scrape different products.
Notes:

This code uses basic CSS selectors for scraping. Website layouts can change, and selectors might need to be adjusted over time.
Consider implementing error handling for potential website changes or network issues.
Be responsible when scraping websites. Respect robots.txt and avoid excessive load on their servers.
By using this application, you can easily compare prices between Amazon and Migros for your desired products and stay informed about price fluctuations.
