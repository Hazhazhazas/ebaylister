import streamlit as st
import google.generativeai as genai
from PIL import Image
import requests
import json
from io import BytesIO # Needed to handle the image data

# --- Page Configuration (For Mobile App Feel) ---
st.set_page_config(
    page_title="eBay Lister",
    page_icon="📸",
    layout="centered"
)

# --- SECRETS: Accessing your keys securely ---
try:
    GEMINI_KEY = st.secrets["GEMINI_KEY"]
    EBAY_TOKEN = st.secrets["EBAY_TOKEN"]
except KeyError:
    st.error("🚨 Missing API Keys. Please set GEMINI_KEY and EBAY_TOKEN in Streamlit Secrets.")
    st.stop()

# Configure Gemini
genai.configure(api_key=GEMINI_KEY)
EBAY_SANDBOX_URL = "https://api.sandbox.ebay.com/sell/inventory/v1"

# --- HELPER FUNCTIONS ---

def analyze_image(image):
    """Sends image to Gemini 1.5 Flash for structured data extraction."""
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = """
    You are an expert e-commerce product listing specialist for eBay. Your task is to analyze the provided image of a single product and generate a complete, structured draft listing.
    Return ONLY a single, raw JSON object. Do not include any text before or after the JSON, and do not use Markdown fencing.
    
    Output Structure:
    {
        "title": "A highly descriptive, keyword-rich title (max 80 chars)",
        "description": "A compelling, easy-to-read sales description formatted with short paragraphs or bullet points.",
        "brand": "The manufacturer name (or 'Unbranded')",
        "condition": "NEW_OTHER" or "USED_EXCELLENT",
        "category_keyword": "2-3 keyword phrase for category search (e.g., 'Men's running shoes')"
    }
    """
    
    response = model.generate_content([prompt, image])
    clean_text = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(clean_text)

def upload_image_to_ebay(image_bytes, image_name):
    """
    Uploads the image to the eBay Media API (Sandbox) and returns the EPS URL.
    """
    url = f"{EBAY_SANDBOX_URL}/file"
    
    headers = {
        "Authorization": f"Bearer {st.secrets['EBAY_TOKEN']}",
        "X-API-COMPATIBILITY-VERSION": "1.0.0",
        "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
        # Content-Type is set automatically by requests for multipart data
    }
    
    # Prepare the multipart data
    files = {
        'file': (image_name, image_bytes, 'image/jpeg') 
    }
    
    try:
        response = requests.post(url, headers=headers, files=files)
        response.raise_for_status()
        
        image_info = response.json()
        return image_info.get('fileId') # This is the unique file ID (EPS URL)
    
    except requests.exceptions.HTTPError as e:
        st.error(f"Image Upload Failed. Check token scope and marketplace ID.")
        st.json(response.json())
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred during image upload: {e}")
        return None


# --- THE MAIN APP UI ---

st.header("Upload & Analyze")

# The camera input widget
picture = st.camera_input("Snap a photo of the item to list")

if picture:
    # Convert Streamlit's file object into a PIL Image and BytesIO object
    img = Image.open(picture)
    st.image(img, caption='Item Preview', width=300)
    
    # Create the bytes object needed for the API call
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='JPEG')
    image_bytes = img_byte_arr.getvalue()

    if st.button("✨ Generate & Upload Image"):
        
        # --- PHASE 1: AI Analysis ---
        with st.spinner("1. Analyzing image with Gemini..."):
            try:
                listing_data = analyze_image(img)
                st.session_state['listing_data'] = listing_data
            except Exception as e:
                st.error(f"AI Analysis Failed: {e}")
                st.stop()
        
        # --- PHASE 2: Image Upload to eBay Sandbox ---
        with st.spinner("2. Uploading image to eBay Sandbox..."):
            image_id = upload_image_to_ebay(image_bytes, f"listing_{st.session_state.get('listing_data', {}).get('title', 'item')}.jpg")
            if image_id:
                st.session_state['image_id'] = image_id
            else:
                st.error("Image upload failed. Cannot proceed.")
                st.stop()


# --- Display Results and Test Button ---
if 'listing_data' in st.session_state and 'image_id' in st.session_state:
    st.divider()
    st.subheader("📝 AI Draft & Image Ready")
    
    st.success(f"Image Uploaded Successfully! eBay File ID: `{st.session_state['image_id']}`")
    
    # Display results from Gemini in editable text boxes
    title = st.text_input("Title (Edit here):", value=st.session_state['listing_data']['title'], key='input_title')
    description = st.text_area("Description (Edit here):", value=st.session_state['listing_data']['description'], height=100, key='input_description')
    st.markdown(f"**Brand:** `{st.session_state['listing_data']['brand']}` | **Condition:** `{st.session_state['listing_data']['condition']}`")
    st.markdown(f"**Category Keywords:** `{st.session_state['listing_data']['category_keyword']}`")
    
    # Final Test Button (Ready for Step 3: Create Inventory Item)
    if st.button("🚀 GO! Create eBay Inventory Draft"):
        st.warning("Next step coming soon...")
        # The next function (create_inventory_item) will go here!
