from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import requests
import time
import hashlib
import models, schemas
from database import engine, get_db
import logging
import os
from dotenv import load_dotenv

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Helpdesk Notifications API")

# Setup CORS to allow requests from the HTML frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)

# --- CSC SMS INTEGRATION ---
# IMPORTANT: Use your actual account login here!
CSC_LOGIN = "stomatologija" # tas ir konta nosaukums kura csc ielogojas un no ka tiks viss sutits! Tas "username" csc kontam ar ko loggojas ieksa sms.csc.lv
CSC_API_KEY = os.getenv(SMS_API_KEY) # api key atrodams aizejot csc mājaslapā pie api>SMS sending un tur augšā jābūt tieši zem login "API key: ..."
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

def send_sms(phone_number: str, message: str):
    """
    Sends an SMS via csc.lv using the required query parameters format.
    """
    url = "https://sms.csc.lv/external/get/send.php"
    
    # Normalize phone: Remove '+', ' ', '-', etc.
    clean_phone = "".join(filter(str.isdigit, phone_number))
    
    # If it's a standard Latvian number without the prefix, add it
    if len(clean_phone) == 8:
        clean_phone = "371" + clean_phone
    
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
        
        response = requests.get(url, params=params)
        
        logging.info(f"HTTP Status: {response.status_code}")
        logging.info(f"SMS API Response Body: '{response.text}'")
        
    except Exception as e:
        logging.error(f"Failed to send SMS: {e}")

# --- API ENDPOINTS ---

@app.post("/api/specialists", response_model=schemas.SpecialistResponse, summary="Insert a new specialist")
def create_specialist(specialist: schemas.SpecialistCreate, db: Session = Depends(get_db)):
    db_specialist = models.Specialist(**specialist.model_dump())
    db.add(db_specialist)
    db.commit()
    db.refresh(db_specialist)
    return db_specialist

@app.get("/api/specialists", response_model=list[schemas.SpecialistResponse], summary="List available specialists")
def get_specialists(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.Specialist).offset(skip).limit(limit).all()

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
    
    db.delete(db_specialist)
    db.commit()
    return {"message": "Specialist deleted successfully"}

@app.post("/api/requests", response_model=schemas.SupportRequestResponse, summary="Receive incoming problem")
def create_request(support_request: schemas.SupportRequestCreate, db: Session = Depends(get_db)):
    db_request = models.SupportRequest(**support_request.model_dump())
    db.add(db_request)
    db.commit()
    db.refresh(db_request)
    return db_request

@app.get("/api/requests", response_model=list[schemas.SupportRequestResponse], summary="List piling up problems")
def get_requests(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(models.SupportRequest).offset(skip).limit(limit).all()

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
    db.commit()
    db.refresh(db_request)
    
    # Fire the exact API logic requested
    msg_content = f"{db_request.institute_branch} Room {db_request.office_number} - Priority: {db_request.priority}. Problem: {db_request.message}"
    send_sms(db_specialist.phone_number, msg_content)
    
    return db_request
