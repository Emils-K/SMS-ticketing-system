import hashlib
import requests
import time

LOGIN = "stomatologija"
KEY = "2b99d7412b00c3635c6e9248d3e8404a9189e8a2"

def get_time():
    try:
        res = requests.head("http://www.google.com", timeout=2)
        from email.utils import parsedate_to_datetime
        return int(parsedate_to_datetime(res.headers.get('Date')).timestamp())
    except:
        return int(time.time())

NOW = get_time()

def try_it(name, phone, sender, text):
    params = {
        "login": LOGIN,
        "phone": phone,
        "return": "json",
    }
    if sender:
        params["sender"] = sender
        
    params["text"] = text
    params["timestamp"] = NOW
    
    # Correct signature logic
    sorted_vals = "".join(str(params[k]) for k in sorted(params.keys()))
    sig = hashlib.md5((sorted_vals + KEY).encode('utf-8')).hexdigest()
    
    params["signature"] = sig
    
    try:
        res = requests.get("https://sms.csc.lv/external/get/send.php", params=params, timeout=5).text
        print(f"{name.ljust(35)} | Body: '{res}'")
    except Exception as e:
        print(f"{name.ljust(35)} | FAILED: {e}")

print(f"--- TESTING PHONE AND SENDER VARIATIONS (Time: {NOW}) ---")
try_it("1. 371 Prefix + smstest", "37129144496", "smstest", "hi")
try_it("2. NO Prefix  + smstest", "29144496", "smstest", "hi")
try_it("3. 371 Prefix + stomatologija", "37129144496", "stomatologija", "hi")
try_it("4. 371 Prefix + NO SENDER", "37129144496", "", "hi")
try_it("5. NO Prefix  + stomatologija", "29144496", "stomatologija", "hi")
