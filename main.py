from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import os
import io
import requests # Used for synchronous HTTP calls (simple, but can be replaced with httpx for async)
import json
import uuid

# --- Initializing FastAPI ---
app = FastAPI()

# --- Load Environment Variables (API Keys and Constants) ---
# NOTE: GEMINI_KEY is no longer used in this version but remains for reference
EBAY_TOKEN = os.environ.get("EBAY_TOKEN")
EBAY_SANDBOX_URL = "https://api.sandbox.ebay.com/sell/inventory/v1"

# NOTE: These policy IDs MUST be replaced with your actual eBay Sandbox Policy IDs!
# You must obtain these from your eBay Developer/Sandbox account.
POLICY_IDS = {
    "fulfillment": os.environ.get("EBAY_FULFILLMENT_POLICY_ID", "1234567890"),
    "payment": os.environ.get("EBAY_PAYMENT_POLICY_ID", "9876543210"),    
    "return": os.environ.get("EBAY_RETURN_POLICY_ID", "5432109876")       
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

def fetch_image_from_url(url: str) -> bytes:
    """Fetches an image from a URL and returns the raw binary contents."""
    try:
        # NOTE: Using synchronous requests.get. Consider replacing with httpx for async performance.
        response = requests.get(url, stream=True, timeout=10)
        response.raise_for_status() # Raise exception for bad status codes (4xx or 5xx)
        return response.content
    except requests.exceptions.RequestException as e:
        # Catch network or connection errors
        raise Exception(f"Failed to fetch image from URL: {url}. Error: {e}")

def upload_image_to_ebay(image_bytes: bytes, image_name: str) -> str:
    """Uploads the image to the eBay Media API (Sandbox) and returns the fileId."""
    if not EBAY_TOKEN:
        raise Exception("eBay Token is not configured.")
        
    url = f"{EBAY_SANDBOX_URL}/file"
    
    headers = {
        "Authorization": f"Bearer {EBAY_TOKEN}",
        "X-API-COMPATIBILITY-VERSION": "1.0.0",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
    }
    
    files = {
        # The first item is the file name, the second is the bytes, the third is the MIME type
        'file': (image_name, image_bytes, 'image/jpeg') 
    }
    
    response = requests.post(url, headers=headers, files=files)
    response.raise_for_status() # Check for errors in the API response
    
    # eBay returns the fileId upon success
    return response.json().get('fileId') 

def create_inventory_item(item_data: ListingPayload, image_id: str) -> str:
    """Creates the Inventory Item in the eBay Sandbox and returns the SKU."""
    if not EBAY_TOKEN:
        raise Exception("eBay Token is not configured.")
        
    # Generate a unique SKU for this item
    sku = f"SKU-{str(uuid.uuid4())[:8].upper()}"
    url = f"{EBAY_SANDBOX_URL}/inventory_item/{sku}"
    
    headers = {
        "Authorization": f"Bearer {EBAY_TOKEN}",
        "Content-Language": "en-US",
        "Content-Type": "application/json"
    }
    
    # Payload for the Inventory Item
    payload = {
        "product": {
            "title": item_data.title,
            "description": item_data.description,
            "aspects": {
                "Brand": [item_data.brand],
                "Condition": [item_data.condition]
            },
            "imageUrls": [image_id] # Link the uploaded image
        },
        "condition": item_data.condition.replace('_', ''),
        "conditionDescription": f"AI-Generated Listing for: {item_data.title}",
        "group": "SINGLE"
    }

    response = requests.put(url, headers=headers, json=payload)
    response.raise_for_status()
    
    # Successful creation returns HTTP 204 No Content
    if response.status_code == 204:
        return sku
    return None 

def create_offer(sku: str, item_data: ListingPayload) -> str:
    """Creates and publishes the Offer, linking to price and policies."""
    if not EBAY_TOKEN:
        raise Exception("eBay Token is not configured.")
        
    url = f"{EBAY_SANDBOX_URL}/offer"
    
    headers = {
        "Authorization": f"Bearer {EBAY_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Payload for the Offer
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
        "listingStatus": "DRAFT" # Set as DRAFT to avoid accidental publication
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    
    # Successful creation returns HTTP 201 Created
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
            <p><strong>Endpoint:</strong> POST /create-listing/</p>
            <p>The source service must send a JSON body matching the defined schema.</p>
            <p><strong>NOTE:</strong> Ensure your eBay Policy IDs are configured as environment variables!</p>
        </body>
    </html>
    """

@app.post("/create-listing/")
async def create_listing(payload: ListingPayload):
    """
    Receives listing data (including image URL) and executes the eBay 3-step listing process.
    """
    if not EBAY_TOKEN:
        # Check for the key early and fail fast
        raise HTTPException(status_code=500, detail="EBAY_TOKEN environment variable is missing.")
        
    # Check for placeholder Policy IDs (A useful check for common deployment errors)
    if POLICY_IDS['fulfillment'] == "1234567890":
        raise HTTPException(status_code=500, detail="eBay Policy IDs are still set to placeholders. Please update them in your environment variables.")

    try:
        # 1. FETCH IMAGE DATA from URL
        image_bytes = fetch_image_from_url(payload.image_url)
        
        # 2. EBAY IMAGE UPLOAD
        image_id = upload_image_to_ebay(image_bytes, f"{uuid.uuid4()}.jpg")
        if not image_id:
             raise HTTPException(status_code=500, detail="eBay Image Upload Failed. Check token scope and marketplace.")
        
        # 3. CREATE INVENTORY ITEM
        sku = create_inventory_item(payload, image_id)
        if not sku:
             raise HTTPException(status_code=500, detail="eBay Inventory Item Creation Failed.")
        
        # 4. CREATE OFFER (FINAL DRAFT)
        offer_id = create_offer(sku, payload)
        if not offer_id:
             raise HTTPException(status_code=500, detail="eBay Offer Creation Failed. Check Policy IDs or marketplace.")
             
        # SUCCESS RESPONSE (Status 200 OK by default)
        return {
            "status": "success",
            "message": "eBay listing draft successfully created.",
            "title": payload.title,
            "sku": sku,
            "offer_id": offer_id,
        }
        
    except requests.exceptions.HTTPError as e:
        # This catches errors from the eBay API calls (e.g., 401 Unauthorized, 400 Bad Request)
        error_details = {"error": f"eBay API Request Failed: {e}", "response": e.response.json() if e.response is not None and e.response.content else None}
        print(f"eBay API Error: {error_details}")
        raise HTTPException(status_code=e.response.status_code if e.response is not None else 500, detail=error_details)
    except Exception as e:
        # This catches other errors (e.g., URL fetch failure)
        print(f"Internal Processing Error: {e}")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

# If you run this file locally, it will start the Uvicorn server
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
