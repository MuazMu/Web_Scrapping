# Web Scraper and Price Comparison Tool

This project is a web scraper and price comparison tool designed to extract product data from various e-commerce websites, compare prices, and provide insights into the cheapest and most expensive options for a given product. Additionally, the tool supports storing and exporting data to a database and CSV files.

## Features

- **Web Scraping**: Extract product names and prices from multiple e-commerce websites using Selenium.
- **Price Comparison**: Identify the cheapest and most expensive products from the scraped data.
- **Database Integration**: Save comparison results to a database for historical analysis.
- **Export to CSV**: Export stored data to CSV files.
- **REST API**: Expose scraping and data retrieval functionalities through a Flask-powered API.
- **Automatic Updates**: Perform daily updates of product prices.

## Requirements

### Python Packages
- Flask
- Selenium
- SpaCy
- PyODBC
- CSV
- WebDriver Manager for Selenium

### Other Requirements
- Chrome WebDriver
- Database connection string (replace `conn_str` in the code with your connection string)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository_url>
   cd <repository_directory>
   ```

2. Install required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up Chrome WebDriver:
   - Download and install Chrome browser.
   - Install the WebDriver Manager package:
     ```bash
     pip install webdriver-manager
     ```

4. Replace the `conn_str` variable in the code with your database connection string.

## Usage

### Starting the Application
Run the Flask application:
```bash
python app.py
```
The app will be available at `http://127.0.0.1:5000`.

### API Endpoints

#### 1. Scrape Products
- **Endpoint**: `/scrape`
- **Method**: POST
- **Description**: Scrape product data from specified stores.
- **Request Body** (JSON):
  ```json
  {
    "product_name": "<product_name>",
    "urls": ["amazon", "trendyol", "migros"]
  }
  ```
- **Response**:
  ```json
  {
    "cheapest_overall": { ... },
    "most_expensive_overall": { ... },
    "total_products_found": <number>,
    "all_results": [ ... ]
  }
  ```

#### 2. Fetch History
- **Endpoint**: `/history`
- **Method**: GET
- **Description**: Retrieve historical scraping data from the database.

#### 3. Export Data
- **Endpoint**: `/export`
- **Method**: GET
- **Description**: Export data to a CSV file.

### Automatic Updates
The application automatically updates product prices every 24 hours in the background.

## Code Structure

- **Flask App**: The entry point for the API endpoints.
- **Selenium Scraper**: Handles web scraping tasks for different e-commerce websites.
- **Database Functions**: Manages data storage and retrieval from the database.
- **Automatic Update**: Periodically updates product prices.



## Logging
Logging is configured to capture information about scraping tasks, errors, and updates. Logs are saved to the console.

## Future Enhancements
- Add support for more e-commerce websites.
- Enhance error handling for scraper failures.
- Implement a user-friendly front-end interface.

## Contributing
If you would like to contribute, feel free to submit pull requests or report issues.



