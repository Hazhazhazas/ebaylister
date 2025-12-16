import streamlit as st
import google.generativeai as genai
from PIL import Image
import requests
import json

# --- Helper to load Custom CSS for styling ---
def load_css(file_name):
    """Loads a custom CSS file into the Streamlit app."""
    try:
        # Load the CSS file content and inject it into the app via st.markdown
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning(f"CSS file not found: {file_name}")

# --- Page Configuration (For Mobile App Feel) ---
st.set_page_config(
    page_title="eBay Lister",
    page_icon="📸",
    layout="centered"
)

# Load the custom CSS file you created in Step 1
load_css(".streamlit/style.css")

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

def push_draft_to_ebay_sandbox(item_data):
    """Mocks the final push to eBay Sandbox for testing connection."""
    
    headers = {
        "Authorization": f"Bearer {EBAY_TOKEN}",
        "Content-Type": "application/json"
    }
    
    response = requests.get(f"{EBAY_SANDBOX_URL}/inventory_item", headers=headers)
    
    if response.status_code == 200:
        st.success(f"✅ eBay Sandbox Connection Success! Token is valid (Status 200).")
        st.info("The next step in development is implementing the multi-step eBay listing API flow.")
        return True
    else:
        st.error(f"❌ eBay Connection Failed. Status Code: {response.status_code}")
        st.json(response.json())
        return False


# --- THE MAIN APP UI ---

st.header("Upload & Analyze")
