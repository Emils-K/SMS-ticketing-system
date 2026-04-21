# Helpdesk SMS Notification System - Starting Guide

This project is a FastAPI backend designed to manage support requests and trigger SMS notifications to specialists using the `csc.lv` API.

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

---

## 🛠 Project Structure

- `main.py`: The entry point for the FastAPI application. Contains API routes and SMS logic.
- `models.py`: Database models defined with SQLAlchemy.
- `schemas.py`: Pydantic models for data validation and API documentation.
- `database.py`: Database connection and session management.
- `helpdesk.db`: Local SQLite database file (created automatically on first run).

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

---

## Logging / Audit / GDPR

### Phone number encryption (GDPR)
Phone numbers are encrypted at rest in SQLite (application-level encryption).

Required env var:
- `PHONE_ENCRYPTION_KEY` (Fernet key). Generate:
  - `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

Dev-only escape hatch (not GDPR-compliant):
- `ALLOW_PLAINTEXT_PHONES=1`

API responses show masked phone numbers (e.g. `****4496`). Decryption is only used inside the SMS sending function.

### SMS Audit Log
Every SMS send attempt writes an entry to DB table `sms_audit_logs` with (at minimum):
- `ticket_id`, `recipient` (masked), `timestamp`, `provider_response_code`, `cost`

Endpoint:
- `GET /api/audit-logs?ticket_id=123`

### Request completion timestamps
Support requests now track:
- `created_at`, `assigned_at`, `resolved_at`

Endpoint to mark completed:
- `POST /api/requests/{request_id}/resolve`

### Balance monitoring (optional)
If you use a prepaid gateway, configure:
- (CSC default) no extra URL needed; the app uses `https://sms.csc.lv/external/get/balance.php` with your `CSC_LOGIN` + `SMS_API_KEY`
- (Other gateways) set `SMS_BALANCE_URL` to a URL that returns JSON with `balance` or plain numeric text
- `LOW_BALANCE_THRESHOLD_EUR` (default `10`)
- `BALANCE_CHECK_INTERVAL_SECONDS` (default `3600`)
- `LOW_BALANCE_ALERT_PHONE` (optional; sends an SMS alert once per low-balance incident)

Endpoints:
- `GET /api/balance`
- `GET /api/alerts`
