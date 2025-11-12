import os
import json
import requests
from PIL import Image
import base64
from io import BytesIO
import traceback

# ==============================
# CONFIG
# ==============================
NGROK_URL = "https://unsurgical-semiliberally-myron.ngrok-free.dev"
REQUEST_TIMEOUT = 500
CHAT_TIMEOUT = 120

MEAL_THRESHOLDS = {
    "breakfast": {"Calories": 20, "Protein": 19, "Carbs": 26, "Fats": 21},
    "lunch": {"Calories": 31, "Protein": 34, "Carbs": 34, "Fats": 34},
    "dinner": {"Calories": 29, "Protein": 30, "Carbs": 29, "Fats": 29},
    "snack": {"Calories": 9, "Protein": 9, "Carbs": 6, "Fats": 9},
    "snacks": {"Calories": 9, "Protein": 9, "Carbs": 6, "Fats": 9},
    "supper": {"Calories": 11, "Protein": 8, "Carbs": 6, "Fats": 7},
}

# ==============================
# UTILITIES
# ==============================
def check_server_health():
    """Check if the remote LLM server is available"""
    try:
        response = requests.get(f"{NGROK_URL}/health", timeout=5)
        if response.status_code == 200:
            print("[LLM] SUCCESS: Connected to remote server")
            return True
        print(f"[LLM] ERROR: Server returned status {response.status_code}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"[LLM] ERROR: Cannot connect to server: {e}")
        return False

def compress_and_encode_image(image_path, max_size=(512, 512), quality=85):
    """Compress and encode an image to base64"""
    img = Image.open(image_path).convert("RGB")
    img.thumbnail(max_size)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")

def load_model():
    """Compatibility function - checks remote server"""
    print("[LLM] Checking remote server connection...")
    if check_server_health():
        print("[LLM] Remote model ready")
        return None, None
    print("[LLM] WARNING: Cannot connect to remote server!")
    print("[LLM] Make sure Google Colab is running and NGROK_URL is correct")
    return None, None

def _make_request(endpoint, payload, timeout=REQUEST_TIMEOUT, operation="Request"):
    """Unified request handler for all API calls"""
    try:
        print(f"[LLM] Sending {operation.lower()} to remote server...")
        response = requests.post(f"{NGROK_URL}/{endpoint}", json=payload, timeout=timeout)
        
        if response.status_code == 200:
            result = response.json()
            if "error" in result:
                print(f"[LLM ERROR] Server returned error: {result['error']}")
                return None
            return result
        
        print(f"[LLM ERROR] Server returned status {response.status_code}")
        print(f"[LLM ERROR] Response: {response.text}")
        return None
        
    except requests.exceptions.Timeout:
        print(f"[LLM ERROR] {operation} timed out. Server may be overloaded.")
    except requests.exceptions.RequestException as e:
        print(f"[LLM ERROR] {operation} failed: {e}")
    except Exception as e:
        print(f"[LLM ERROR] Unexpected error: {e}")
        traceback.print_exc()
    return None

# ==============================
# CORE FUNCTIONS
# ==============================
def estimate_nutrition(image_path, user_prompt=None, role_prompt=None):
    """Estimate nutrition from an image by sending it to remote server"""
    if not os.path.exists(image_path):
        print(f"[LLM ERROR] Image not found: {image_path}")
        return None
    
    print(f"[LLM] Loading and encoding image: {image_path}")
    try:
        image_base64 = compress_and_encode_image(image_path)
    except Exception as e:
        print(f"[LLM ERROR] Failed to compress/encode image: {e}")
        return None
    
    print("[LLM] This may take 10-30 seconds...")
    payload = {"image_base64": image_base64, "user_prompt": user_prompt, "role_prompt": role_prompt}
    
    nutrition_data = _make_request("estimate_nutrition", payload, operation="Nutrition estimation")
    if nutrition_data:
        print(f"[LLM] Nutrition estimate: {json.dumps(nutrition_data, indent=2)}")
    return nutrition_data

def compare_macros(meal_type, meal_macros, total_daily_macros):
    """Compare logged meal macros with allowed percentage thresholds"""
    exceeded = {}
    meal_type = meal_type.lower()

    if meal_type not in MEAL_THRESHOLDS:
        print(f"[WARN] Unknown meal type '{meal_type}'. Skipping threshold check.")
        return exceeded

    for nutrient, threshold_pct in MEAL_THRESHOLDS[meal_type].items():
        expected_max = (threshold_pct / 100) * total_daily_macros.get(nutrient, 0)
        actual = meal_macros.get(nutrient, 0)
        if actual > expected_max:
            exceeded[nutrient] = round(actual - expected_max, 2)

    return exceeded

def get_reduction_tips(exceeded_dict, meal_type, energy_level=None, hunger_level=None):
    """Ask the remote LLM for advice on reducing intake of exceeded macros"""
    if not exceeded_dict:
        print(f"[LLM] No macro thresholds exceeded for {meal_type}.")
        return None
    
    payload = {
        "exceeded_dict": exceeded_dict,
        "meal_type": meal_type,
        "energy_level": energy_level,
        "hunger_level": hunger_level
    }
    
    result = _make_request("reduction_tips", payload, timeout=CHAT_TIMEOUT, operation="Reduction tips")
    if result:
        advice = result.get("advice")
        print(f"[LLM] Advice: {advice}")
        return advice
    return None

def generate_wellness_tips(meal_type, energy_level, hunger_level):
    """Generate tips based on energy and hunger levels when macros are within range"""
    payload = {"meal_type": meal_type, "energy_level": energy_level, "hunger_level": hunger_level}
    
    result = _make_request("wellness_tips", payload, timeout=CHAT_TIMEOUT, operation="Wellness tips")
    if result:
        advice = result.get("advice")
        print(f"[LLM] Wellness advice: {advice}")
        return advice
    return None

def handle_logged_meal(meal_type, meal_macros, total_daily_macros, energy_level=None, hunger_level=None):
    """Full pipeline after a meal is logged"""
    print(f"[MEAL] Checking macros for {meal_type}...")
    
    if energy_level is not None and hunger_level is not None:
        print(f"[MEAL] User state - Energy: {energy_level}/5, Hunger: {hunger_level}/5")
    
    exceeded = compare_macros(meal_type, meal_macros, total_daily_macros)
    
    if exceeded:
        print(f"[MEAL] Exceeded macros detected: {exceeded}")
        return get_reduction_tips(exceeded, meal_type, energy_level, hunger_level)
    
    print(f"[MEAL] {meal_type.capitalize()} is within recommended macro limits.")
    
    # Provide wellness advice for low energy or high hunger even if macros are fine
    if energy_level is not None and hunger_level is not None:
        if energy_level <= 2 or hunger_level >= 4:
            return generate_wellness_tips(meal_type, energy_level, hunger_level)
    
    return None

def get_chat_response(user_message, context=None):
    """Generate a chat response using the remote LLM"""
    print(f"[CHAT] User asked: {user_message}")
    
    daily_macros = context.get('daily_macros') if context else None
    payload = {"message": user_message, "daily_macros": daily_macros}
    
    result = _make_request("chat", payload, timeout=CHAT_TIMEOUT, operation="Chat")
    if result:
        chat_response = result.get("response", "Sorry, I couldn't generate a response.")
        print(f"[CHAT] Response: {chat_response}")
        return chat_response
    
    return "Sorry, I couldn't process your request. Please try again."

# ==============================
# STARTUP CHECK
# ==============================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("Testing connection to remote LLM server...")
    print("="*60)
    
    if check_server_health():
        print("\nSUCCESS! Remote server is accessible.")
        print(f"Server URL: {NGROK_URL}")
    else:
        print("\nFAILED! Cannot connect to remote server.")
        print("\nTroubleshooting:")
        print("1. Make sure Google Colab notebook is running")
        print("2. Check that cloudflare tunnel is active in Colab")
        print("3. Copy the correct cloudflare URL from Colab output")
        print(f"4. Update NGROK_URL in this file: {__file__}")
        print(f"   Current URL: {NGROK_URL}")
    
    print("="*60 + "\n")