from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn
import os
import io
from PIL import Image
import requests
import json
import uuid
import google.generativeai as genai

# --- Initializing FastAPI ---
# The Procfile expects the variable 'app' from the module 'main'
app = FastAPI()

# --- Load Environment Variables (API Keys and Constants) ---
GEMINI_KEY = os.environ.get("GEMINI_KEY")
EBAY_TOKEN = os.environ.get("EBAY_TOKEN")
EBAY_SANDBOX_URL = "https://api.sandbox.ebay.com/sell/inventory/v1"

# NOTE: These policy IDs MUST be replaced with your actual eBay Sandbox Policy IDs!
# If these are wrong, the final 'create_offer' step will fail with a 400 Bad Request.
POLICY_IDS = {
    "fulfillment": "1234567890", 
    "payment": "9876543210",    
    "return": "5432109876"       
}

# --- Initialize Gemini Client ---
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
    except Exception as e:
        print(f"Gemini client configuration failed: {e}")

# --- CORE EBAY & AI HELPER FUNCTIONS ---

def analyze_image_with_gemini(image):
    """Sends image to Gemini 1.5 Flash for structured data extraction."""
    if not GEMINI_KEY:
        raise Exception("Gemini API key is not configured.")
        
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = """
    You are an expert e-commerce product listing specialist for eBay. Your task is to analyze the provided image of a single product and generate a complete, structured draft listing.
    Return ONLY a single, raw JSON object. Do not include any text before or after the JSON, and do not use Markdown fencing.
    
    Output Structure:
    {
        "title": "A highly descriptive, keyword-rich title (max 80 chars)",
        "description": "A compelling, easy-to-read sales description formatted with short paragraphs or bullet points.",
        "brand": "The manufacturer name (or 'Unbranded')",
        "condition": "NEW_OTHER" or "USED_EXCELLENT" or "USED_GOOD",
        "category_keyword": "2-3 keyword phrase for category search (e.g., 'Men's running shoes')",
        "suggested_price": 49.99,
        "currency": "USD"
    }
    """
    
    response = model.generate_content([prompt, image])
    clean_text = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(clean_text)

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
            "title": item_data['title'],
            "description": item_data['description'],
            "aspects": {
                "Brand": [item_data['brand']],
                "Condition": [item_data['condition']]
            },
            "imageUrls": [image_id]
        },
        "condition": item_data['condition'].replace('_', ''),
        "conditionDescription": f"AI-Generated Description: {item_data['condition']}",
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
                "value": item_data.get('suggested_price', 25.00),
                "currency": item_data.get('currency', 'USD')
            }
        },
        "listingStatus": "DRAFT" 
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    
    if response.status_code == 201:
        return response.json().get('offerId')
    return None


# --- CUSTOM CAMERA HTML/JS FRONTEND ---

CAMERA_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>AI eBay Lister</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { font-family: sans-serif; margin: 0; padding: 0; background-color: #f0f2f5; text-align: center; }
        .container { max-width: 600px; margin: 20px auto; padding: 20px; background: white; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }
        h1 { color: #333; }
        #camera-container {
            width: 100%;
            height: 400px; /* --- THE CRITICAL HEIGHT ADJUSTMENT --- */
            overflow: hidden;
            background: #000;
            margin-bottom: 20px;
            border-radius: 4px;
        }
        #videoElement {
            width: 100%;
            min-height: 100%; 
            object-fit: cover; 
        }
        button {
            padding: 10px 20px;
            font-size: 16px;
            cursor: pointer;
            border: none;
            border-radius: 4px;
            background-color: #4CAF50;
            color: white;
            margin: 5px;
        }
        #results {
            margin-top: 20px;
            text-align: left;
            padding: 15px;
            border: 1px solid #ddd;
            background: #fafafa;
            white-space: pre-wrap;
        }
        .error { color: red; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📸 Snap & List</h1>
        
        <div id="camera-container">
            <video id="videoElement" autoplay></video>
        </div>
        
        <button id="captureButton">Take Photo & Analyze</button>
        <button id="restartButton" style="display: none;">Retake Photo</button>

        <canvas id="canvas" style="display: none;"></canvas>
        <img id="photo" style="display: none; width: 100%; border-radius: 4px;">

        <div id="status" style="margin-top: 10px; color: blue;">Waiting for camera...</div>
        <div id="results"></div>
    </div>

    <script>
        const video = document.getElementById('videoElement');
        const canvas = document.getElementById('canvas');
        const captureButton = document.getElementById('captureButton');
        const restartButton = document.getElementById('restartButton');
        const photo = document.getElementById('photo');
        const statusDiv = document.getElementById('status');
        const resultsDiv = document.getElementById('results');
        let stream = null;

        // --- 1. START CAMERA STREAM ---
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } }) 
                .then(function(s) {
                    stream = s;
                    video.srcObject = s;
                    video.play();
                    statusDiv.textContent = 'Camera ready. Click Take Photo.';
                })
                .catch(function(err) {
                    statusDiv.textContent = 'Error accessing camera: ' + err;
                    console.error('Error accessing camera: ', err);
                });
        } else {
            statusDiv.textContent = 'Camera not supported by this browser.';
        }

        // --- 2. CAPTURE PHOTO ---
        captureButton.addEventListener('click', function() {
            if (!stream) {
                statusDiv.textContent = 'Camera not running.';
                return;
            }
            
            video.pause();
            
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            
            canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
            
            canvas.toBlob(function(blob) {
                if (blob) {
                    const imgUrl = URL.createObjectURL(blob);
                    photo.src = imgUrl;
                    photo.style.display = 'block';
                    video.style.display = 'none';
                    captureButton.style.display = 'none';
                    restartButton.style.display = 'block';

                    uploadImage(blob);
                    
                } else {
                    statusDiv.textContent = 'Error creating image blob.';
                    video.play(); 
                }
            }, 'image/jpeg', 0.9); 
        });

        // --- 3. RETAKE PHOTO ---
        restartButton.addEventListener('click', function() {
            video.style.display = 'block';
            photo.style.display = 'none';
            captureButton.style.display = 'block';
            restartButton.style.display = 'none';
            resultsDiv.innerHTML = '';
            statusDiv.textContent = 'Ready to retake photo.';
            video.play();
        });

        // --- 4. UPLOAD FUNCTION ---
        async function uploadImage(imageBlob) {
            statusDiv.textContent = 'Sending image to API...';
            resultsDiv.innerHTML = 'Analyzing and listing...';
            
            const formData = new FormData();
            formData.append('file', imageBlob, 'listing_photo.jpg');

            try {
                // FIXED: Using the full path with a trailing slash to match FastAPI exactly
                const response = await fetch('/upload-and-analyze/', { 
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    statusDiv.textContent = 'Listing Draft Completed!';
                    resultsDiv.innerHTML = `
                        <h2>✅ Listing Draft Completed</h2>
                        <strong>SKU:</strong> ${data.sku}<br>
                        <strong>Offer ID:</strong> ${data.offer_id}<br>
                        <strong>AI Title:</strong> ${data.title}<br>
                        <strong>Suggested Price:</strong> ${data.suggested_price} ${data.currency}<br>
                        <p style="color: red; margin-top: 10px;">Check eBay Sandbox for final review!</p>
                        <pre>${JSON.stringify(data, null, 2)}</pre>
                    `;
                } else {
                    statusDiv.textContent = 'API Error occurred.';
                    resultsDiv.innerHTML = `
                        <h2>❌ API Error</h2>
                        <p>Status: ${response.status}</p>
                        <pre class="error">${JSON.stringify(data, null, 2)}</pre>
                    `;
                }
            } catch (error) {
                statusDiv.textContent = 'Network Error.';
                resultsDiv.innerHTML = `
                    <h2>❌ Network Error</h2>
                    <p class="error">${error.message}</p>
                `;
                console.error('Network error:', error);
            }
        }

    </script>
</body>
</html>
"""


# --- FASTAPI ENDPOINTS ---

@app.get("/", response_class=HTMLResponse)
def read_root():
    """Serves the custom HTML/JavaScript camera interface."""
    return CAMERA_HTML

@app.post("/upload-and-analyze/")
async def upload_and_analyze(file: UploadFile = File(...)):
    """
    Handles the image upload, runs AI analysis, and executes the eBay API 3-step listing.
    """
    if not GEMINI_KEY or not EBAY_TOKEN:
        raise HTTPException(status_code=500, detail="API Keys are missing. Check Render environment variables.")

    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image.")

    try:
        # 1. READ IMAGE DATA
        contents = await file.read()
        
        # 2. CONVERT TO PIL IMAGE
        image_stream = io.BytesIO(contents)
        img = Image.open(image_stream)
        
        # 3. AI ANALYSIS (Error handled with try/except in the calling block)
        listing_data = analyze_image_with_gemini(img)
        
        # 4. EBAY IMAGE UPLOAD
        image_id = upload_image_to_ebay(contents, file.filename)
        if not image_id:
             raise HTTPException(status_code=500, detail="eBay Image Upload Failed. Check token scope.")
        
        # 5. CREATE INVENTORY ITEM
        sku = create_inventory_item(listing_data, image_id)
        if not sku:
             raise HTTPException(status_code=500, detail="eBay Inventory Item Creation Failed.")
        
        # 6. CREATE OFFER (FINAL DRAFT)
        offer_id = create_offer(sku, listing_data)
        if not offer_id:
             raise HTTPException(status_code=500, detail="eBay Offer Creation Failed. Check Policy IDs.")
             
        # SUCCESS RESPONSE
        return {
            "status": "success",
            "title": listing_data['title'],
            "suggested_price": listing_data['suggested_price'],
            "currency": listing_data['currency'],
            "sku": sku,
            "offer_id": offer_id,
        }
        
    except requests.exceptions.HTTPError as e:
        # Catches specific HTTP errors from the eBay API calls
        error_details = {"error": f"API Request Failed: {e}", "response": e.response.json() if e.response else None}
        raise HTTPException(status_code=e.response.status_code if e.response is not None else 500, detail=error_details)
    except Exception as e:
        # Catches any other unexpected errors, including those from Gemini
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")

# If you run this file locally, it will start the Uvicorn server
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
