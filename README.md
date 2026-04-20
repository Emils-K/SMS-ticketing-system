# Helpdesk SMS Notification System - Starting Guide

This project is a FastAPI-based backend designed to manage support requests and trigger SMS notifications to specialists using the `csc.lv` API.

## 📋 Requirements

- **Python 3.8+**
- **Internet Access** (Required for SMS delivery and network time synchronization)
- **CSC.lv Account** (Credentials are currently configured in `main.py`)

## 🚀 Quick Start

### 1. Set Up Virtual Environment
It is recommended to use a virtual environment to keep dependencies isolated.

```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment
.\venv\Scripts\activate
```

### 2. Install Dependencies
Install the required Python packages:

```powershell
pip install -r requirements.txt
```

### 3. Start the Backend Server
Run the FastAPI application using Uvicorn:

```powershell
uvicorn main:app --reload
```
The API will be available at `http://127.0.0.1:8000`.

### 4. Access the Dashboard
Open the `index.html` file in your preferred web browser to access the management interface. The frontend is configured to communicate with the local API.

---

## 🛠 Project Structure

- `main.py`: The entry point for the FastAPI application. Contains API routes and SMS logic.
- `models.py`: Database models defined with SQLAlchemy.
- `schemas.py`: Pydantic models for data validation and API documentation.
- `database.py`: Database connection and session management.
- `helpdesk.db`: Local SQLite database file (created automatically on first run).
- `index.html`: The frontend dashboard for interaction.

## 📡 API Documentation
Once the server is running, you can explore the interactive API documentation at:
- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Redoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 🔑 SMS Configuration
The current configuration uses the `stomatologija` account. You can modify these constants in `main.py` (lines 28-30) if credentials change:
- `CSC_LOGIN`
- `CSC_API_KEY`
- `CSC_SENDER`
