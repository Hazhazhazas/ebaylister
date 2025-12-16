from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
import uvicorn
import os
import io
from PIL import Image

# --- Initializing FastAPI ---
app = FastAPI()

# --- Load Environment Variables (API Keys) ---
GEMINI_KEY = os.environ.get("GEMINI_KEY")
EBAY_TOKEN = os.environ.get("EBAY_TOKEN")

# Simple check to ensure keys are loaded on Render
if not GEMINI_KEY or not EBAY_TOKEN:
    print("WARNING: GEMINI_KEY or EBAY_TOKEN not found in environment variables!")
    # NOTE: On Render, you must set these variables in the dashboard.

# --- Simple Root Endpoint (Placeholder for the camera UI) ---
@app.get("/", response_class=HTMLResponse)
def read_root():
    # This is a placeholder HTML page that will host your custom camera UI
    # We will replace this with the full camera/JS code later.
    html_content = """
    <html>
        <head>
            <title>eBay AI Lister</title>
        </head>
        <body>
            <h1>eBay AI Lister Backend</h1>
            <p>Server is running! This is the API backend for your custom camera frontend.</p>
            <p>API Endpoint: <code>/upload-and-analyze/</code></p>
        </body>
    </html>
    """
    return html_content

# --- Image Upload Endpoint (Placeholder for your AI/eBay logic) ---
@app.post("/upload-and-analyze/")
async def upload_and_analyze(file: UploadFile = File(...)):
    if not GEMINI_KEY or not EBAY_TOKEN:
        raise HTTPException(status_code=500, detail="API Keys are missing. Check Render environment variables.")

    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="File must be an image.")

    try:
        # Read the file data into a BytesIO buffer
        contents = await file.read()
        image_stream = io.BytesIO(contents)
        
        # Open the image using PIL (Pillow)
        img = Image.open(image_stream)
        
        # *** The full AI/eBay logic will go here (from your Streamlit app) ***
        
        return {
            "filename": file.filename,
            "size_bytes": len(contents),
            "status": "Image received and keys checked successfully."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

# If you run this file locally, it will start the Uvicorn server
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
