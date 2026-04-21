from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import requests
import time
import hashlib
from fastapi.responses import FileResponse
import models, schemas
from database import engine, get_db, SessionLocal
import logging
from logging.handlers import RotatingFileHandler
import os
from dotenv import load_dotenv
import asyncio
from typing import Optional
import shutil

from db_migrations import ensure_sqlite_schema
from security import (
    decrypt_phone,
    encrypt_phone,
    encryption_is_configured,
    last4_from_phone,
    mask_last4,
    normalize_phone,
)

load_dotenv()

models.Base.metadata.create_all(bind=engine)
ensure_sqlite_schema(engine)

app = FastAPI(title="Helpdesk Notifications API")

# Serve dashboard
@app.get("/")
@app.get("/index.html")
async def serve_index():
    return FileResponse("index.html")

# Setup CORS to allow requests from the HTML frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler("logs/app.log", maxBytes=1_000_000, backupCount=5, encoding="utf-8"),
    ],
)

# --- CSC SMS INTEGRATION ---
# IMPORTANT: Use your actual account login here!
CSC_LOGIN = "stomatologija" # tas ir konta nosaukums kura csc ielogojas un no ka tiks viss sutits! Tas "username" csc kontam ar ko loggojas ieksa sms.csc.lv
CSC_API_KEY = os.getenv("SMS_API_KEY") # api key atrodams aizejot csc mājaslapā pie api>SMS sending un tur augšā jābūt tieši zem login "API key: ..."
CSC_SENDER = "Stomatologi" # stomatologi ir nosutitajs un tas vards no ka paradisies no ka sutits sms! Tam obligati ari sadam ir japaliek! Atradu to no sākuma nosūtot īsziņu caur csc mājaslapu.

def generate_signature(params: dict, api_key: str) -> str:
    # This matches the success logic from our tests:
    # 1. Sort all parameter keys alphabetically
    sorted_keys = sorted(params.keys())
    # 2. Join the values into a single string (PHP implode style)
    imploded_values = "".join(str(params[k]) for k in sorted_keys)
    # 3. Append the API key and hash it with MD5
    raw_string = imploded_values + api_key.strip()
    return hashlib.md5(raw_string.encode('utf-8')).hexdigest()

def get_network_time():
    """Fetches the current Unix timestamp from Google's server headers to bypass incorrect system clocks."""
    try:
        # We check Google's HTTP 'Date' header for a 100% reliable timestamp
        response = requests.head("http://www.google.com", timeout=2)
        server_date = response.headers.get('Date')
        if server_date:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(server_date)
            ts = int(dt.timestamp())
            logging.info(f"NETWORK TIME SYNC SUCCESS: {ts}")
            return ts
    except Exception as e:
        logging.warning(f"Could not reach network time: {e}")
    return int(time.time())

def _parse_provider_response(response: requests.Response):
    try:
        data = response.json()
        provider_code = (
            data.get("code")
            or data.get("status")
            or data.get("error")
            or data.get("result")
        )
        cost = data.get("cost") or data.get("price")
        try:
            cost = float(cost) if cost is not None else None
        except Exception:
            cost = None
        provider_message = data.get("message") or data.get("msg") or response.text
        return (
            str(provider_code) if provider_code is not None else None,
            cost,
            str(provider_message) if provider_message is not None else None,
        )
    except Exception:
        return response.text.strip() if response.text else None, None, response.text


def send_sms(phone_number_encrypted: str, message: str):
    """
    Sends an SMS via csc.lv using the required query parameters format.
    """
    url = "https://sms.csc.lv/external/get/send.php"
    
    decrypted = decrypt_phone(phone_number_encrypted)
    clean_phone = normalize_phone(decrypted)
    
    # Use Network Time instead of System Time to avoid Error 6 (Clock Sync Issues)
    unix_timestamp = get_network_time()
    
    params = {
        "login": CSC_LOGIN,
        "phone": clean_phone,
        "return": "json",
        "sender": CSC_SENDER,
        "text": message,
        "timestamp": unix_timestamp
    }
    
    # Generate and add the signature dynamically
    params["signature"] = generate_signature(params, CSC_API_KEY)
    
    try:
        logging.info(f"--- ATTEMPTING SMS SEND ---")
        logging.info(f"To: {clean_phone} | Time: {unix_timestamp}")
        logging.info(f"Final URL: {url}?{requests.utils.unquote(requests.models.PreparedRequest()._encode_params(params))}")
        
        response = requests.get(url, params=params, timeout=10)
        
        logging.info(f"HTTP Status: {response.status_code}")
        logging.info(f"SMS API Response Body: '{response.text}'")

        provider_response_code, cost, provider_message = _parse_provider_response(response)
        return {
            "timestamp": unix_timestamp,
            "recipient_last4": clean_phone[-4:] if clean_phone else None,
            "http_status": response.status_code,
            "provider_response_code": provider_response_code,
            "cost": cost,
            "provider_message": provider_message,
        }
    except Exception as e:
        logging.error(f"Failed to send SMS: {e}")
        return {
            "timestamp": int(time.time()),
            "recipient_last4": clean_phone[-4:] if clean_phone else None,
            "http_status": None,
            "provider_response_code": "EXCEPTION",
            "cost": None,
            "provider_message": str(e),
        }


def _specialist_out(db_specialist: models.Specialist) -> dict:
    return {
        "id": db_specialist.id,
        "name": db_specialist.name,
        "role": db_specialist.role,
        "phone_number": mask_last4(db_specialist.phone_last4),
    }


def _request_out(db_request: models.SupportRequest) -> dict:
    return {
        "id": db_request.id,
        "first_name": db_request.first_name,
        "last_name": db_request.last_name,
        "office_number": db_request.office_number,
        "institute_branch": db_request.institute_branch,
        "requester_email": db_request.requester_email,
        "requester_phone": mask_last4(db_request.requester_phone_last4),
        "message": db_request.message,
        "priority": db_request.priority,
        "status": db_request.status,
        "assigned_specialist_id": db_request.assigned_specialist_id,
        "created_at": db_request.created_at,
        "assigned_at": db_request.assigned_at,
        "resolved_at": db_request.resolved_at,
    }


def _encryption_required() -> bool:
    return os.getenv("ALLOW_PLAINTEXT_PHONES", "").strip().lower() not in {"1", "true", "yes"}


def _maybe_encrypt_phone(plain_phone: str) -> str:
    if not plain_phone:
        return ""
    if not _encryption_required():
        return plain_phone
    return encrypt_phone(plain_phone)


def _migrate_encrypt_legacy_phones() -> None:
    """
    Encrypt legacy plaintext phone numbers already in DB and populate last4 columns.
    Runs once on startup; safe to run multiple times.
    """
    if _encryption_required() and not encryption_is_configured():
        raise RuntimeError("PHONE_ENCRYPTION_KEY is required (or set ALLOW_PLAINTEXT_PHONES=1 for dev only).")

    db = SessionLocal()
    try:
        if _encryption_required():
            has_plain = (
                db.query(models.Specialist)
                .filter(models.Specialist.phone_number.is_not(None))
                .filter(models.Specialist.phone_number != "")
                .filter(~models.Specialist.phone_number.like("enc:v1:%"))
                .first()
                is not None
            ) or (
                db.query(models.SupportRequest)
                .filter(models.SupportRequest.requester_phone.is_not(None))
                .filter(models.SupportRequest.requester_phone != "")
                .filter(~models.SupportRequest.requester_phone.like("enc:v1:%"))
                .first()
                is not None
            )
            if has_plain and os.path.exists("helpdesk.db"):
                backup_path = f"helpdesk.db.bak.{int(time.time())}"
                shutil.copy2("helpdesk.db", backup_path)
                logging.info(f"DB BACKUP CREATED: {backup_path}")

        specialists = db.query(models.Specialist).all()
        for sp in specialists:
            if not sp.phone_number:
                continue
            if not sp.phone_last4:
                if str(sp.phone_number).startswith("enc:v1:"):
                    sp.phone_last4 = last4_from_phone(decrypt_phone(sp.phone_number))
                else:
                    sp.phone_last4 = last4_from_phone(sp.phone_number)
            if _encryption_required() and not str(sp.phone_number).startswith("enc:v1:"):
                sp.phone_number = encrypt_phone(sp.phone_number)

        reqs = db.query(models.SupportRequest).all()
        for req in reqs:
            if req.requester_phone and not req.requester_phone_last4:
                if str(req.requester_phone).startswith("enc:v1:"):
                    req.requester_phone_last4 = last4_from_phone(decrypt_phone(req.requester_phone))
                else:
                    req.requester_phone_last4 = last4_from_phone(req.requester_phone)
            if _encryption_required() and req.requester_phone and not str(req.requester_phone).startswith("enc:v1:"):
                req.requester_phone = encrypt_phone(req.requester_phone)

        db.commit()
    finally:
        db.close()


def fetch_sms_balance_eur() -> Optional[float]:
    """
    Provider-agnostic balance fetch:
    - configure SMS_BALANCE_URL to a URL that returns either JSON with a 'balance' field or plain numeric text.
    """
    url = os.getenv("SMS_BALANCE_URL", "").strip()
    if not url:
        return fetch_csc_balance_eur()
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        try:
            data = res.json()
            val = data.get("balance") or data.get("amount") or data.get("eur") or data.get("EUR")
            return float(val)
        except Exception:
            return float(res.text.strip())
    except Exception as e:
        logging.warning(f"Balance check failed: {e}")
        return None


def fetch_csc_balance_eur() -> Optional[float]:
    """
    CSC balance endpoint:
    https://sms.csc.lv/external/get/balance.php?login=&signature=&timestamp=&return=json
    """
    if not CSC_LOGIN or not CSC_API_KEY:
        return None

    url = "https://sms.csc.lv/external/get/balance.php"
    unix_timestamp = get_network_time()
    params = {
        "login": CSC_LOGIN,
        "timestamp": unix_timestamp,
        "return": "json",
    }
    params["signature"] = generate_signature(params, CSC_API_KEY)

    try:
        res = requests.get(url, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        for k in ("balance", "amount", "money", "eur", "EUR"):
            if k in data:
                return float(data[k])
        # fallback: any numeric-ish value
        for v in data.values():
            try:
                return float(v)
            except Exception:
                continue
        logging.warning(f"Unexpected CSC balance response: {data}")
        return None
    except Exception as e:
        logging.warning(f"CSC balance check failed: {e}")
        return None


def _ensure_low_balance_alert(balance_eur: float) -> None:
    threshold = float(os.getenv("LOW_BALANCE_THRESHOLD_EUR", "10"))
    if balance_eur >= threshold:
        return

    db = SessionLocal()
    try:
        existing = (
            db.query(models.SystemAlert)
            .filter(models.SystemAlert.alert_type == "LOW_BALANCE")
            .filter(models.SystemAlert.resolved_at.is_(None))
            .order_by(models.SystemAlert.created_at.desc())
            .first()
        )
        if existing:
            return

        now = int(time.time())
        msg = f"SMS balance low: {balance_eur:.2f} EUR (threshold {threshold:.2f} EUR)"
        db.add(models.SystemAlert(alert_type="LOW_BALANCE", message=msg, created_at=now))
        db.commit()

        alert_phone = os.getenv("LOW_BALANCE_ALERT_PHONE", "").strip()
        if alert_phone:
            send_to = _maybe_encrypt_phone(alert_phone)
            send_sms(send_to, msg)
    finally:
        db.close()


async def _balance_poll_loop() -> None:
    interval = int(os.getenv("BALANCE_CHECK_INTERVAL_SECONDS", "3600"))
    while True:
        bal = fetch_sms_balance_eur()
        if bal is not None:
            _ensure_low_balance_alert(bal)
        await asyncio.sleep(max(60, interval))


@app.on_event("startup")
async def _on_startup():
    _migrate_encrypt_legacy_phones()
    if os.getenv("SMS_BALANCE_URL", "").strip():
        asyncio.create_task(_balance_poll_loop())

# --- API ENDPOINTS ---

@app.post("/api/specialists", response_model=schemas.SpecialistResponse, summary="Insert a new specialist")
def create_specialist(specialist: schemas.SpecialistCreate, db: Session = Depends(get_db)):
    phone_last4 = last4_from_phone(specialist.phone_number)
    db_specialist = models.Specialist(
        name=specialist.name,
        role=specialist.role,
        phone_last4=phone_last4,
        phone_number=_maybe_encrypt_phone(specialist.phone_number),
    )
    db.add(db_specialist)
    db.commit()
    db.refresh(db_specialist)
    return _specialist_out(db_specialist)

@app.get("/api/specialists", response_model=list[schemas.SpecialistResponse], summary="List available specialists")
def get_specialists(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    specialists = db.query(models.Specialist).offset(skip).limit(limit).all()
    return [_specialist_out(s) for s in specialists]

@app.delete("/api/specialists/{specialist_id}", summary="Delete a specialist")
def delete_specialist(specialist_id: int, db: Session = Depends(get_db)):
    db_specialist = db.query(models.Specialist).filter(models.Specialist.id == specialist_id).first()
    if not db_specialist:
        raise HTTPException(status_code=404, detail="Specialist not found")
    
    # Unassign requests linked to this specialist
    requests = db.query(models.SupportRequest).filter(models.SupportRequest.assigned_specialist_id == specialist_id).all()
    for req in requests:
        req.assigned_specialist_id = None
        req.status = "Pending"
        req.assigned_at = None
    
    db.delete(db_specialist)
    db.commit()
    return {"message": "Specialist deleted successfully"}

@app.post("/api/requests", response_model=schemas.SupportRequestResponse, summary="Receive incoming problem")
def create_request(support_request: schemas.SupportRequestCreate, db: Session = Depends(get_db)):
    now = int(time.time())
    requester_last4 = last4_from_phone(support_request.requester_phone)
    db_request = models.SupportRequest(
        **support_request.model_dump(exclude={"requester_phone"}),
        requester_phone_last4=requester_last4,
        requester_phone=_maybe_encrypt_phone(support_request.requester_phone),
        created_at=now,
    )
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return _request_out(db_request)

@app.get("/api/requests", response_model=list[schemas.SupportRequestResponse], summary="List piling up problems")
def get_requests(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    reqs = db.query(models.SupportRequest).offset(skip).limit(limit).all()
    return [_request_out(r) for r in reqs]

@app.delete("/api/requests/{request_id}", summary="Delete a request")
def delete_request(request_id: int, db: Session = Depends(get_db)):
    db_request = db.query(models.SupportRequest).filter(models.SupportRequest.id == request_id).first()
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")
    db.delete(db_request)
    db.commit()
    return {"message": "Request deleted successfully"}

@app.post("/api/requests/bulk-delete", summary="Bulk delete requests")
def bulk_delete_requests(bulk: schemas.BulkDeleteRequest, db: Session = Depends(get_db)):
    db.query(models.SupportRequest).filter(models.SupportRequest.id.in_(bulk.ids)).delete(synchronize_session=False)
    db.commit()
    return {"message": f"Successfully deleted {len(bulk.ids)} requests"}

@app.post("/api/requests/{request_id}/assign", response_model=schemas.SupportRequestResponse, summary="Assign problem & trigger SMS")
def assign_request(request_id: int, assignment: schemas.AssignRequest, db: Session = Depends(get_db)):
    # Fetch Request
    db_request = db.query(models.SupportRequest).filter(models.SupportRequest.id == request_id).first()
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")
        
    # Fetch Specialist
    db_specialist = db.query(models.Specialist).filter(models.Specialist.id == assignment.specialist_id).first()
    if not db_specialist:
        raise HTTPException(status_code=404, detail="Specialist not found")
        
    # Update DB status
    db_request.assigned_specialist_id = db_specialist.id
    db_request.status = "Assigned"
    db_request.assigned_at = int(time.time())
    db.commit()
    db.refresh(db_request)
    
    # Fire the exact API logic requested
    msg_content = f"{db_request.institute_branch} Room {db_request.office_number} - Priority: {db_request.priority}. Problem: {db_request.message}"
    result = send_sms(db_specialist.phone_number, msg_content)
    try:
        db.add(
            models.SmsAuditLog(
                ticket_id=db_request.id,
                recipient=mask_last4(db_specialist.phone_last4) or mask_last4(result.get("recipient_last4")),
                timestamp=int(result.get("timestamp") or time.time()),
                provider_response_code=result.get("provider_response_code"),
                cost=result.get("cost"),
                http_status=result.get("http_status"),
                provider_message=result.get("provider_message"),
            )
        )
        db.commit()
    except Exception as e:
        logging.warning(f"Could not write SMS audit log: {e}")
    
    return _request_out(db_request)


@app.post("/api/requests/{request_id}/resolve", response_model=schemas.SupportRequestResponse, summary="Mark request as resolved")
def resolve_request(request_id: int, db: Session = Depends(get_db)):
    db_request = db.query(models.SupportRequest).filter(models.SupportRequest.id == request_id).first()
    if not db_request:
        raise HTTPException(status_code=404, detail="Request not found")
    db_request.status = "Resolved"
    db_request.resolved_at = int(time.time())
    db.commit()
    db.refresh(db_request)
    return _request_out(db_request)


@app.get("/api/audit-logs", response_model=list[schemas.SmsAuditLogResponse], summary="List SMS audit log entries")
def list_audit_logs(ticket_id: Optional[int] = None, skip: int = 0, limit: int = 200, db: Session = Depends(get_db)):
    q = db.query(models.SmsAuditLog)
    if ticket_id is not None:
        q = q.filter(models.SmsAuditLog.ticket_id == ticket_id)
    return q.order_by(models.SmsAuditLog.timestamp.desc()).offset(skip).limit(limit).all()


@app.get("/api/alerts", response_model=list[schemas.SystemAlertResponse], summary="List system alerts")
def list_alerts(skip: int = 0, limit: int = 200, db: Session = Depends(get_db)):
    return (
        db.query(models.SystemAlert)
        .order_by(models.SystemAlert.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@app.get("/api/balance", summary="Check SMS gateway balance (if configured)")
def get_balance():
    bal = fetch_sms_balance_eur()
    if bal is None:
        raise HTTPException(status_code=501, detail="SMS_BALANCE_URL is not configured")
    return {"balance_eur": bal}
