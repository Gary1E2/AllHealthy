import os
import json
import datetime
import torch
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
from PIL import Image
import firebase_admin
from firebase_admin import credentials, firestore
import warnings

# Silence warnings
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
warnings.filterwarnings("ignore", category=FutureWarning)

# ==============================
# CONFIG
# ==============================
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "Qwen2-VL-2B-Instruct")
SERVICE_ACCOUNT_KEY_PATH = 'diet-app-sg-firebase-adminsdk-fbsvc-f840993dc2.json'
TEST_USER_ID = "user"
IMAGE_PATH = "images/chickenrice.jpg"

ROLE_PROMPT = """
You are a nutrition analysis assistant.

Estimate the nutritional values of the food shown in any image as accurately as possible.

Respond ONLY in **exactly** the following JSON format, with numeric values only:
{
  "Calories": <number in kcal>,
  "Protein": <number in grams>,
  "Carbs": <number in grams>,
  "Fats": <number in grams>
}
Do not include any other text or explanation.
"""

USER_PROMPT = "Estimate the macronutrient breakdown of my meal."

# ==============================
# INITIALIZE FIREBASE
# ==============================
def init_firebase():
    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("[INFO] Firebase initialized successfully")
        return db
    except Exception as e:
        print(f"[ERROR] Firebase initialization failed: {e}")
        return None

# ==============================
# LOAD MODEL
# ==============================
def load_model():
    print("[INFO] Loading processor...")
    processor = AutoProcessor.from_pretrained(MODEL_DIR, use_fast=True)
    
    print("[INFO] Loading model...")
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        MODEL_DIR,
        dtype=torch.float32,
        device_map="auto",
        low_cpu_mem_usage=True
    )
    print("[INFO] Model loaded successfully")
    return model, processor

# ==============================
# GET NUTRITION ESTIMATE
# ==============================
def get_nutrition_estimate(model, processor, image):
    try:
        # Prepare messages
        messages = [
            {"role": "system", "content": ROLE_PROMPT.strip()},
            {"role": "user", "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": USER_PROMPT.strip()}
            ]}
        ]
        
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(
            text=[text],
            images=[image],
            return_tensors="pt",
            padding=True
        ).to(model.device)
        
        # Generate
        outputs = model.generate(
            **inputs,
            do_sample=False,
            max_new_tokens=64,
            temperature=0.7,
            top_p=0.9
        )
        
        # Decode
        generated_text = processor.batch_decode(outputs, skip_special_tokens=True)[0]
        
        # Extract JSON from response
        # Find the last occurrence of { to get the JSON part
        json_start = generated_text.rfind('{')
        if json_start != -1:
            json_str = generated_text[json_start:]
            # Find the matching closing brace
            json_end = json_str.find('}') + 1
            json_str = json_str[:json_end]
            
            nutrition_data = json.loads(json_str)
            print(f"[INFO] Nutrition estimate: {json.dumps(nutrition_data, indent=2)}")
            return nutrition_data
        else:
            print("[ERROR] Could not find JSON in model output")
            return None
            
    except Exception as e:
        print(f"[ERROR] During generation: {e}")
        import traceback
        traceback.print_exc()
        return None

# ==============================
# UPLOAD TO FIREBASE
# ==============================
def upload_to_firebase(db, user_id, meal_type, nutrition_data):
    """
    Upload nutrition data to Firebase for today's date
    meal_type: 'breakfast', 'lunch', 'dinner', 'supper', or 'snacks'
    """
    try:
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        
        # Convert keys to lowercase for Firebase format
        meal_data = {
            "calories": nutrition_data.get("Calories", 0),
            "proteins": nutrition_data.get("Protein", 0),
            "carbs": nutrition_data.get("Carbs", 0),
            "fats": nutrition_data.get("Fats", 0)
        }
        
        # Get document reference
        doc_ref = db.collection('users').document(user_id).collection('mealLogs').document(today_str)
        
        # Upload with merge to preserve other meals
        doc_ref.set({
            meal_type: meal_data,
            "last_updated": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        print(f"[INFO] Successfully uploaded {meal_type} data for {today_str}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to upload to Firebase: {e}")
        return False

# ==============================
# MAIN FUNCTION
# ==============================
def main():
    # Load image
    if not os.path.exists(IMAGE_PATH):
        print(f"[ERROR] Image not found: {IMAGE_PATH}")
        return
    
    print(f"[INFO] Loading image: {IMAGE_PATH}")
    image = Image.open(IMAGE_PATH).convert("RGB").resize((224, 224))
    
    # Initialize Firebase
    db = init_firebase()
    if db is None:
        return
    
    # Load model
    model, processor = load_model()
    
    # Get nutrition estimate
    nutrition_data = get_nutrition_estimate(model, processor, image)
    if nutrition_data is None:
        print("[ERROR] Failed to get nutrition estimate")
        return
    
    # Upload to Firebase (change 'breakfast' to your desired meal type)
    upload_to_firebase(db, TEST_USER_ID, 'breakfast', nutrition_data)
    
    print("\n[INFO] Process complete!")

if __name__ == "__main__":
    main()