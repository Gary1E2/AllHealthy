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
    "breakfast": {"Calories": 20, "Proteins": 40, "Carbs": 40, "Fats": 40},
    "lunch": {"Calories": 31, "Proteins": 40, "Carbs": 40, "Fats": 40},
    "dinner": {"Calories": 29, "Proteins": 40, "Carbs": 40, "Fats": 40},
    "snack": {"Calories": 9, "Proteins": 40, "Carbs": 40, "Fats": 40},
    "snacks": {"Calories": 9, "Proteins": 40, "Carbs": 40, "Fats": 40},
    "supper": {"Calories": 11, "Proteins": 40, "Carbs": 40, "Fats": 40},
}

# Thresholds for hunger and energy levels
HUNGER_THRESHOLD = 4  # Hunger level above this triggers tips
ENERGY_THRESHOLD = 2  # Energy level below this triggers tips

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
    print("[LLM] Make sure remote model program is running and NGROK_URL is correct")
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

def describe_food(image_path):
    """Generate a description of the food in the image"""
    if not os.path.exists(image_path):
        print(f"[LLM ERROR] Image not found: {image_path}")
        return None
    
    print(f"[LLM] Generating food description...")
    try:
        image_base64 = compress_and_encode_image(image_path)
    except Exception as e:
        print(f"[LLM ERROR] Failed to compress/encode image: {e}")
        return None
    
    payload = {"image_base64": image_base64}
    result = _make_request("describe_food", payload, timeout=30, operation="Food description")
    
    if result:
        description = result.get("description", "")
        print(f"[LLM] Description: {description}")
        return description
    return None

def analyze_meal_context(meal_type, meal_macros, daily_goal_macros, energy_level=None, hunger_level=None):
    """
    Analyze all aspects of a logged meal: macros, hunger, and energy levels.
    Returns a context dict with all exceeded thresholds.
    
    Args:
        meal_type: Type of meal (breakfast, lunch, etc.)
        meal_macros: Macros for this specific meal
        daily_goal_macros: The user's DAILY GOAL macros (not consumed)
        energy_level: Energy level after meal (1-5)
        hunger_level: Hunger level after meal (1-5)
    """
    # Standardize meal_macros keys to match MEAL_THRESHOLDS format
    # Convert "Protein" -> "Proteins" if needed
    standardized_meal_macros = {}
    for key, value in meal_macros.items():
        if key == "Protein":
            standardized_meal_macros["Proteins"] = value
        else:
            standardized_meal_macros[key] = value
    
    context = {
        "meal_type": meal_type.lower(),
        "exceeded_macros": {},
        "high_hunger": False,
        "low_energy": False,
        "energy_level": energy_level,
        "hunger_level": hunger_level
    }
    
    # Check macro thresholds
    meal_type_lower = meal_type.lower()
    if meal_type_lower in MEAL_THRESHOLDS:
        for nutrient, threshold_pct in MEAL_THRESHOLDS[meal_type_lower].items():
            # Calculate the maximum allowed for this meal type based on DAILY GOAL
            allowed_max = (threshold_pct / 100) * daily_goal_macros.get(nutrient, 0)
            # Get actual amount consumed in this meal (use standardized keys)
            actual = standardized_meal_macros.get(nutrient, 0)
            # Check if this meal exceeded its allowed percentage
            if actual > allowed_max:
                context["exceeded_macros"][nutrient] = round(actual - allowed_max, 2)
    
    # Check hunger and energy thresholds
    if hunger_level is not None and hunger_level > HUNGER_THRESHOLD:
        context["high_hunger"] = True
    
    if energy_level is not None and energy_level < ENERGY_THRESHOLD:
        context["low_energy"] = True
    
    return context

def get_dynamic_tips(meal_context):
    """
    Request dynamic tips from remote server based on what thresholds were exceeded.
    Only generates tips if at least one threshold is exceeded.
    """
    # Check if any threshold was exceeded
    has_exceeded_macros = bool(meal_context.get("exceeded_macros"))
    has_high_hunger = meal_context.get("high_hunger", False)
    has_low_energy = meal_context.get("low_energy", False)
    
    if not (has_exceeded_macros or has_high_hunger or has_low_energy):
        print(f"[MEAL] {meal_context['meal_type'].capitalize()} is within all recommended thresholds.")
        return None
    
    # Build description of what was exceeded
    exceeded_items = []
    if has_exceeded_macros:
        macro_str = ", ".join([
            f"{n} by {v:.1f}g" if n != "Calories" else f"{n} by {v:.0f} kcal"
            for n, v in meal_context["exceeded_macros"].items()
        ])
        exceeded_items.append(f"macros ({macro_str})")
    if has_high_hunger:
        exceeded_items.append(f"hunger level ({meal_context['hunger_level']}/5)")
    if has_low_energy:
        exceeded_items.append(f"energy level ({meal_context['energy_level']}/5)")
    
    print(f"[MEAL] Thresholds exceeded: {', '.join(exceeded_items)}")
    
    # Send to remote server
    payload = {"meal_context": meal_context}
    result = _make_request("dynamic_tips", payload, timeout=CHAT_TIMEOUT, operation="Dynamic tips")
    
    if result:
        advice = result.get("advice")
        print(f"[LLM] Advice: {advice}")
        return advice
    return None

def handle_logged_meal(meal_type, meal_macros, daily_goal_macros, energy_level=None, hunger_level=None):
    """
    Full pipeline after a meal is logged.
    Analyzes all aspects and generates dynamic tips only if needed.
    
    Args:
        meal_type: Type of meal (breakfast, lunch, etc.)
        meal_macros: Macros for this specific meal
        daily_goal_macros: The user's DAILY GOAL macros (not consumed)
        energy_level: Energy level after meal (1-5)
        hunger_level: Hunger level after meal (1-5)
    """
    print(f"[MEAL] Analyzing {meal_type}...")
    if energy_level is not None or hunger_level is not None:
        print(f"[MEAL] User state - Energy: {energy_level}/5, Hunger: {hunger_level}/5")
    
    # Analyze all aspects of the meal
    meal_context = analyze_meal_context(
        meal_type, meal_macros, daily_goal_macros, 
        energy_level, hunger_level
    )
    
    # Get dynamic tips if any threshold exceeded
    return get_dynamic_tips(meal_context)

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