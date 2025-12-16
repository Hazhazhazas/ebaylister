from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn
import os
import io
from PIL import Image
import requests
import json
import uuid
from pydantic import BaseModel

# --- Initializing FastAPI ---
app = FastAPI()

# --- Load Environment Variables (API Keys and Constants) ---
# NOTE: GEMINI_KEY is no longer needed but kept as placeholder for completeness
GEMINI_KEY = os.environ.get("GEMINI_KEY") 
EBAY_TOKEN = os.environ.get("EBAY_TOKEN")
EBAY_SANDBOX_URL = "https://api.sandbox.ebay.com/sell/inventory/v1"

# NOTE: These policy IDs MUST be replaced with your actual eBay Sandbox Policy IDs!
POLICY_IDS = {
    "fulfillment": "1234567890", 
    "payment": "9876543210",    
    "return": "5432109876"       
}

# --- 1. DEFINE INPUT SCHEMA (Pydantic Model) ---
# This defines the exact data structure your "Opal" source MUST send to your API
class ListingPayload(BaseModel):
    title: str
    description: str
    brand: str
    condition: str
    suggested_price: float
    currency: str
    image_url: str

# --- CORE EBAY HELPER FUNCTIONS ---

def fetch_image_from_url(url):
    """Fetches an image from a URL and returns the raw binary contents."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status() # Raise exception for bad status codes
        return response.content
    except Exception as e:
        raise Exception(f"Failed to fetch image from URL: {url}. Error: {e}")

def upload_image_to_ebay(image_bytes, image_name):
    """Uploads the image to the eBay Media API (Sandbox)."""
    if not EBAY_TOKEN:
        raise Exception("eBay Token is not configured.")
        
    url = f"{EBAY_SANDBOX_URL}/file"
    
    headers = {
        "Authorization": f"Bearer {EBAY_TOKEN}",
        "X-API-COMPATIBILITY-VERSION": "1.0.0",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    }
    
    files = {
        'file': (image_name, image_bytes, 'image/jpeg') 
    }
    
    response = requests.post(url, headers=headers, files=files)
    response.raise_for_status()
    return response.json().get('fileId') 

def create_inventory_item(item_data, image_id):
    """Creates the Inventory Item in the eBay Sandbox."""
    if not EBAY_TOKEN:
        raise Exception("eBay Token is not configured.")
        
    sku = f"SKU-{str(uuid.uuid4())[:8].upper()}"
    url = f"{EBAY_SANDBOX_URL}/inventory_item/{sku}"
    
    headers = {
        "Authorization": f"Bearer {EBAY_TOKEN}",
        "Content-Language": "en-US",
        "Content-Type": "application/json"
    }
    
    payload = {
        "product": {
            "title": item_data.title,
            "description": item_data.description,
            "aspects": {
                "Brand": [item_data.brand],
                "Condition": [item_data.condition]
            },
            "imageUrls": [image_id]
        },
        "condition": item_data.condition.replace('_', ''),
        "conditionDescription": f"AI-Generated Description: {item_data.condition}",
        "group": "SINGLE"
    }

    response = requests.put(url, headers=headers, json=payload)
    response.raise_for_status()
    
    if response.status_code == 204:
        return sku
    return None 

def create_offer(sku, item_data):
    """Creates and publishes the Offer, linking to price and policies."""
    if not EBAY_TOKEN:
        raise Exception("eBay Token is not configured.")
        
    url = f"{EBAY_SANDBOX_URL}/offer"
    
    headers = {
        "Authorization": f"Bearer {EBAY_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "sku": sku,
        "marketplaceId": "EBAY_US",
        "format": "FIXED_PRICE",
        "quantity": 1, 
        "listingPolicies": {
            "fulfillmentPolicyId": POLICY_IDS['fulfillment'],
            "paymentPolicyId": POLICY_IDS['payment'],
            "returnPolicyId": POLICY_IDS['return']
        },
        "pricingSummary": {
            "price": {
                "value": item_data.suggested_price,
                "currency": item_data.currency
            }
        },
        "listingStatus": "DRAFT" 
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    
    if response.status_code == 201:
        return response.json().get('offerId')
    return None


# --- FASTAPI ENDPOINTS ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Simple status page for verification."""
    return """
    <html>
        <head><title>eBay Lister Webhook</title></head>
        <body>
            <h1>eBay Lister Webhook Ready</h1>
            <p>This API is designed to receive a JSON payload from a source service (like Gemini/Opal).</p>
            <p><strong>Endpoint:</strong> POST /create-listing/</p>
            <p>The source must send a JSON body matching the defined schema.</p>
        </body>
    </html>
    """

@app.post("/create-listing/")
async def create_listing(payload: ListingPayload):
    """
    Receives listing data (including image URL) and executes the eBay 3-step listing process.
    """
    if not EBAY_TOKEN:
        raise HTTPException(status_code=500, detail="EBAY_TOKEN is missing. Check environment variables.")

    try:
        # 1. FETCH IMAGE DATA from URL
        image_bytes = fetch_image_from_url(payload.image_url)
        
        # 2. EBAY IMAGE UPLOAD
        image_id = upload_image_to_ebay(image_bytes, "ai_item.jpg")
        if not image_id:
             raise HTTPException(status_code=500, detail="eBay Image Upload Failed. Check token scope.")
        
        # 3. CREATE INVENTORY ITEM
        sku = create_inventory_item(payload, image_id)
        if not sku:
             raise HTTPException(status_code=500, detail="eBay Inventory Item Creation Failed.")
        
        # 4. CREATE OFFER (FINAL DRAFT)
        offer_id = create_offer(sku, payload)
        if not offer_id:
             raise HTTPException(status_code=500, detail="eBay Offer Creation Failed. Check Policy IDs.")
             
        # SUCCESS RESPONSE
        return {
            "status": "success",
            "message": "eBay listing draft successfully created.",
            "title": payload.title,
            "sku": sku,
            "offer_id": offer_id,
        }
        
    except requests.exceptions.HTTPError as e:
        error_details = {"error": f"eBay API Request Failed: {e}", "response": e.response.json() if e.response else None}
        # Log the error details here for debugging in Cloud Run logs
        print(f"eBay API Error: {error_details}")
        raise HTTPException(status_code=e.response.status_code if e.response is not None else 500, detail=error_details)
    except Exception as e:
        # Log the internal error for debugging
        print(f"Internal Processing Error: {e}")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

# If you run this file locally, it will start the Uvicorn server
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
