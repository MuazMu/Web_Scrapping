🛒 Smart Grocery Price Comparison System
Overview
A comprehensive, multi-platform price comparison system that helps consumers find the best prices for grocery products across different stores.
🌟 Key Features

Cross-platform price scraping (Python backend)
Windows desktop application (VB.NET frontend)
Real-time price comparison
Multiple store support
Dynamic product information retrieval

🔧 Technologies

Backend: Python

Flask
Selenium
SQLAlchemy


Frontend: VB.NET Windows Forms
Scraping: BeautifulSoup, Selenium
Databases: SQLite, SQL Server

🚀 Quick Setup
Backend (Python)

Clone the repository
Install dependencies:

bashCopypip install -r requirements.txt

Run the backend server:

bashCopypython price_comparison_system.py
Frontend (VB.NET)

Open solution in Visual Studio
Restore NuGet packages
Build and run the project

📦 Supported Stores

Amazon Turkey
Migros
CarrefourSA

🔍 How It Works

Enter a product name
System scrapes prices from multiple stores
Displays cheapest and most expensive options
Stores price history in database

🛠 Future Roadmap

 Add more store integrations
 Implement price trend analysis
 Create mobile app version
 Add email/SMS price drop alerts
