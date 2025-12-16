import streamlit as st
import google.generativeai as genai
from PIL import Image
import requests
import json

# --- Page Configuration (For Mobile App Feel) ---
st.set_page_config(
    page_title="eBay Lister",
    page_icon="📸",
    layout="centered"
)

# --- SECRETS: Accessing your keys securely ---
try:
    # These keys are read from the Streamlit Cloud Secrets Manager!
    GEMINI_KEY = st.secrets["GEMINI_KEY"]
    EBAY_TOKEN = st.secrets["EBAY_TOKEN"]
except:
    st.error("🚨 Missing API Keys. Please set GEMINI_KEY and EBAY_TOKEN in Streamlit Secrets.")
    st.stop()

# Configure Gemini
genai.configure(api_key=GEMINI_KEY)
EBAY_SANDBOX_URL = "https://api.sandbox.ebay.com/sell/inventory/v1"

# --- HELPER FUNCTIONS ---

def analyze_image(image):
    """Sends image to Gemini 1.5 Flash for structured data extraction."""
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Using the prompt we finalized earlier to force JSON output
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
    # Simple cleanup to handle minor formatting differences
    clean_text = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(clean_text)

def push_draft_to_ebay_sandbox(item_data):
    """Mocks the final push to eBay Sandbox for testing."""
    # NOTE: This is a placeholder. Real implementation requires multi-step process
    # (1. Upload Image, 2. Create Inventory Item, 3. Create Offer).
    # For the test phase, we ensure the connection is live.
    
    headers = {
        "Authorization": f"Bearer {EBAY_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Test call: Attempting to retrieve inventory to confirm token is valid
    response = requests.get(f"{EBAY_SANDBOX_URL}/inventory_item", headers=headers)
    
    if response.status_code == 200:
        st.success(f"✅ eBay Sandbox Connection Success! Token is valid.")
        st.info("The next step (not in this script) is creating the listing draft.")
        return True
    else:
        st.error(f"❌ eBay Connection Failed. Status Code: {response.status_code}")
        st.json(response.json())
        return False


# --- THE MAIN APP UI ---

st.header("Upload & Analyze")

# The camera input widget is perfect for mobile use
picture = st.camera_input("Snap a photo of the item to list")

if picture:
    img = Image.open(picture)
    st.image(img, caption='Item Preview', width=300)
    
    if st.button("✨ Generate & Test Connection"):
        with st.spinner("1. Analyzing image with Gemini..."):
            try:
                listing_data = analyze_image(img)
                st.session_state['listing_data'] = listing_data
                
            except json.JSONDecodeError as e:
                st.error("Gemini output was not perfect JSON. Please try another image or edit the prompt.")
                st.write(response.text)
                st.stop()
            except Exception as e:
                st.error(f"An unexpected error occurred during analysis: {e}")
                st.stop()

# --- Display Results and Test Button ---
if 'listing_data' in st.session_state:
    st.divider()
    st.subheader("📝 AI Draft & Connection Test")
    
    # Display results from Gemini
    st.text_input("Title (Edit here):", value=st.session_state['listing_data']['title'])
    st.text_area("Description (Edit here):", value=st.session_state['listing_data']['description'], height=100)
    st.markdown(f"**Brand:** `{st.session_state['listing_data']['brand']}` | **Condition:** `{st.session_state['listing_data']['condition']}`")
    st.markdown(f"**Category Keywords:** `{st.session_state['listing_data']['category_keyword']}`")
    
    # Final Test Button
    if st.button("🚀 Confirm eBay Token is Working"):
        with st.spinner("2. Testing eBay Sandbox API connection..."):
            push_draft_to_ebay_sandbox(st.session_state['listing_data'])
