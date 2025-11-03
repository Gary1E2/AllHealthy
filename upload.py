import firebase_admin
from firebase_admin import credentials, firestore
import datetime

# ==============================
# CONFIG
# ==============================
SERVICE_ACCOUNT_KEY_PATH = 'diet-app-sg-firebase-adminsdk-fbsvc-f840993dc2.json'

# ==============================
# FIREBASE SINGLETON
# ==============================
_db_instance = None

def init_firebase():
    """Initialize Firebase (singleton pattern)"""
    global _db_instance
    
    if _db_instance is None:
        try:
            cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
            firebase_admin.initialize_app(cred)
            _db_instance = firestore.client()
            print("[Firebase] Initialized successfully")
        except Exception as e:
            print(f"[Firebase ERROR] Initialization failed: {e}")
            return None
    
    return _db_instance

# ==============================
# UPLOAD FUNCTIONS
# ==============================
def upload_meal(user_id, meal_type, nutrition_data, date_str=None):
    """
    Upload nutrition data to Firebase for a specific meal.
    
    Args:
        user_id (str): The user ID
        meal_type (str): 'breakfast', 'lunch', 'dinner', 'supper', or 'snacks'
        nutrition_data (dict): Dictionary with Calories, Protein, Carbs, Fats
        date_str (str, optional): Date in YYYY-MM-DD format. Defaults to today.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        db = init_firebase()
        if db is None:
            return False
        
        # Use today's date if not provided
        if date_str is None:
            date_str = datetime.date.today().strftime("%Y-%m-%d")
        
        # Convert nutrition data to Firebase format (lowercase keys)
        meal_data = {
            "calories": nutrition_data.get("Calories", 0),
            "proteins": nutrition_data.get("Protein", 0),
            "carbs": nutrition_data.get("Carbs", 0),
            "fats": nutrition_data.get("Fats", 0)
        }
        
        # Get user's daily goal
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            data = user_doc.to_dict()
            daily_goal = data.get('daily_macros_goal', {
                'calories': 2000,
                'proteins': 150,
                'carbs': 250,
                'fats': 65
            })
        else:
            daily_goal = {
                'calories': 2000,
                'proteins': 150,
                'carbs': 250,
                'fats': 65
            }
        
        print(f"[Firebase] User daily goal: {daily_goal}")
        
        # Get document reference
        doc_ref = db.collection('users').document(user_id).collection('mealLogs').document(date_str)
        
        # Upload the meal with merge to preserve other meals
        doc_ref.set({
            meal_type: meal_data,
            "last_updated": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        print(f"[Firebase] Successfully uploaded {meal_type} for {user_id} on {date_str}")
        print(f"[Firebase] Meal data: {meal_data}")
        
        # Now calculate total consumed for the day
        meal_doc = doc_ref.get()
        total_consumed = {'calories': 0, 'proteins': 0, 'carbs': 0, 'fats': 0}
        
        if meal_doc.exists:
            meal_today = meal_doc.to_dict()
            for meal in ['breakfast', 'lunch', 'dinner', 'supper', 'snacks']:
                if meal in meal_today and isinstance(meal_today[meal], dict):
                    total_consumed['calories'] += meal_today[meal].get('calories', 0)
                    total_consumed['proteins'] += meal_today[meal].get('proteins', 0)
                    total_consumed['carbs'] += meal_today[meal].get('carbs', 0)
                    total_consumed['fats'] += meal_today[meal].get('fats', 0)
        
        print(f"[Firebase] Total consumed today: {total_consumed}")
        
        # Calculate macros_left
        macros_left = {
            'calories': daily_goal['calories'] - total_consumed['calories'],
            'proteins': daily_goal['proteins'] - total_consumed['proteins'],
            'carbs': daily_goal['carbs'] - total_consumed['carbs'],
            'fats': daily_goal['fats'] - total_consumed['fats']
        }
        
        print(f"[Firebase] Calculated macros_left: {macros_left}")
        
        # Update macros_left in the same document
        doc_ref.set({'macros_left': macros_left}, merge=True)
        
        print(f"[Firebase] Successfully stored macros_left")
        return True
        
    except Exception as e:
        print(f"[Firebase ERROR] Failed to upload: {e}")
        import traceback
        traceback.print_exc()
        return False

def upload_full_day(user_id, date_str, breakfast=None, lunch=None, dinner=None, supper=None, snacks=None):
    """
    Upload a full day's worth of meals at once.
    
    Args:
        user_id (str): The user ID
        date_str (str): Date in YYYY-MM-DD format
        breakfast, lunch, dinner, supper, snacks (dict): Nutrition data dicts (optional)
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        db = init_firebase()
        if db is None:
            return False
        
        # Build the day's data
        daily_data = {}
        
        for meal_type, meal_data in [
            ('breakfast', breakfast),
            ('lunch', lunch),
            ('dinner', dinner),
            ('supper', supper),
            ('snacks', snacks)
        ]:
            if meal_data is not None:
                daily_data[meal_type] = {
                    "calories": meal_data.get("Calories", 0),
                    "proteins": meal_data.get("Protein", 0),
                    "carbs": meal_data.get("Carbs", 0),
                    "fats": meal_data.get("Fats", 0)
                }
        
        daily_data["last_updated"] = firestore.SERVER_TIMESTAMP
        
        # Upload the entire day
        doc_ref = db.collection('users').document(user_id).collection('mealLogs').document(date_str)
        doc_ref.set(daily_data)
        
        print(f"[Firebase] Successfully uploaded full day for {user_id} on {date_str}")
        return True
        
    except Exception as e:
        print(f"[Firebase ERROR] Failed to upload full day: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==============================
# TEST FUNCTION
# ==============================
if __name__ == "__main__":
    # Test upload
    test_user_id = "user"
    test_nutrition = {
        "Calories": 450,
        "Protein": 25,
        "Carbs": 20,
        "Fats": 15
    }
    
    print("\n[Firebase TEST] Testing single meal upload...")
    success = upload_meal(test_user_id, "breakfast", test_nutrition)
    
    if success:
        print("[Firebase TEST] Success!")
    else:
        print("[Firebase TEST] Failed!")