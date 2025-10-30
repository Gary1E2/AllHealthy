import firebase_admin
from firebase_admin import credentials, firestore
import datetime

# --- IMPORTANT: Configuration ---
# Replace 'path/to/your/serviceAccountKey.json' with the actual path
# to the JSON file you downloaded in step 1.
SERVICE_ACCOUNT_KEY_PATH = 'diet-app-sg-firebase-adminsdk-fbsvc-f840993dc2.json'

# Replace 'testUser123' with an actual user ID.
# In a real app, this would be the Firebase Auth UID of the logged-in user.
# For testing, ensure this document ID exists in your 'users' collection.
# (e.g., in the console, create a 'users' collection, then add a document
# named 'testUser123' with some fields like 'name: "Test User"')
TEST_USER_ID = "user"

# --- Initialize Firebase Admin SDK ---
try:
    cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK initialized successfully.")
except Exception as e:
    print(f"Error initializing Firebase Admin SDK: {e}")
    print("Please ensure 'SERVICE_ACCOUNT_KEY_PATH' is correct and the file exists.")
    exit() # Exit if initialization fails


# --- Upload Function ---
def upload_daily_meal_data(user_id: str, date_str: str,
                           breakfast_data: dict, lunch_data: dict,
                           dinner_data: dict, supper_data: dict, snacks_data: dict):
    """
    Uploads or updates a full day's meal data for a specific user and date.
    This will create the daily meal document if it doesn't exist.
    If it exists, it will completely overwrite all meal entries for that day.

    Args:
        user_id (str): The ID of the user.
        date_str (str): The date for which to log meals (e.g., "YYYY-MM-DD").
        breakfast_data (dict): Dictionary with 'calories', 'proteins', 'carbs', 'fats'.
        lunch_data (dict): Dictionary for lunch.
        dinner_data (dict): Dictionary for dinner.
        supper_data (dict): Dictionary for supper.
        snacks_data (dict): Dictionary for snacks.
    """
    # Get a reference to the specific day's document
    # users/{user_id}/mealLogs/{date_str}
    doc_ref = db.collection('users').document(user_id).collection('mealLogs').document(date_str)

    # Prepare the data dictionary for the entire day
    daily_meal_doc_data = {
        "breakfast": breakfast_data,
        "lunch": lunch_data,
        "dinner": dinner_data,
        "supper": supper_data,
        "snacks": snacks_data,
        # Optional: Add a timestamp for when this entry was last modified
        "last_updated": firestore.SERVER_TIMESTAMP
    }

    try:
        # Using .set() on a document reference:
        # - If the document for 'date_str' does not exist, it will be created.
        # - If the document for 'date_str' already exists, its *entire content*
        #   will be replaced by 'daily_meal_doc_data'.
        #   If you wanted to only update specific fields without affecting others,
        #   you would use 'doc_ref.update({"breakfast": breakfast_data})'
        #   or 'doc_ref.set({"snacks": snacks_data}, merge=True)'.
        doc_ref.set(daily_meal_doc_data)
        print(f"Successfully uploaded/updated meal data for user '{user_id}' on '{date_str}'.")
    except Exception as e:
        print(f"Error uploading meal data: {e}")

# --- Example Usage (Run this part when the script is executed) ---
if __name__ == "__main__":
    # Get today's date in YYYY-MM-DD format for logging
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    print(f"\n--- Uploading today's meal data for user '{TEST_USER_ID}' ({today_str}) ---")

    # Example meal data for the day.
    # You can provide empty dictionaries if a meal was skipped or has no data yet.
    breakfast_macros = {"calories": 350, "proteins": 20, "carbs": 45, "fats": 10}
    lunch_macros = {"calories": 500, "proteins": 30, "carbs": 60, "fats": 15}
    dinner_macros = {"calories": 600, "proteins": 40, "carbs": 70, "fats": 20}
    supper_macros = {"calories": 150, "proteins": 5, "carbs": 20, "fats": 5}
    snacks_macros = {"calories": 200, "proteins": 8, "carbs": 25, "fats": 7}

    upload_daily_meal_data(
        user_id=TEST_USER_ID,
        date_str=today_str,
        breakfast_data=breakfast_macros,
        lunch_data=lunch_macros,
        dinner_data=dinner_macros,
        supper_data=supper_macros,
        snacks_data=snacks_macros
    )

    # --- Example: Uploading data for a different day (e.g., tomorrow) ---
    tomorrow_str = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    print(f"\n--- Uploading tomorrow's meal data for user '{TEST_USER_ID}' ({tomorrow_str}) ---")

    # For tomorrow, let's say the user skipped lunch and supper
    tomorrow_breakfast = {"calories": 400, "proteins": 25, "carbs": 50, "fats": 12}
    tomorrow_dinner = {"calories": 550, "proteins": 35, "carbs": 65, "fats": 18}
    tomorrow_snacks = {"calories": 100, "proteins": 3, "carbs": 15, "fats": 4}

    upload_daily_meal_data(
        user_id=TEST_USER_ID,
        date_str=tomorrow_str,
        breakfast_data=tomorrow_breakfast,
        lunch_data={}, # Empty dict for skipped meal
        dinner_data=tomorrow_dinner,
        supper_data={}, # Empty dict for skipped meal
        snacks_data=tomorrow_snacks
    )

    # --- Example: Updating an existing day's data (e.g., today's snacks) ---
    print(f"\n--- Updating today's snacks for user '{TEST_USER_ID}' ({today_str}) ---")
    # To update *only* snacks without changing other meals, we'd need to fetch existing data
    # or use 'merge=True' with 'set()' or 'update()'.
    # For this simple 'upload_daily_meal_data' function, calling it again for today
    # will overwrite everything, so let's show an *explicit* update for one field
    # if you wanted to do that.

    updated_snacks_data = {"calories": 250, "proteins": 10, "carbs": 30, "fats": 9}

    # To update only snacks without affecting breakfast, lunch, etc. for today_str:
    try:
        db.collection('users').document(TEST_USER_ID).collection('mealLogs').document(today_str).set(
            {"snacks": updated_snacks_data}, merge=True
        )
        print(f"Successfully updated snacks for user '{TEST_USER_ID}' on '{today_str}' using merge.")
    except Exception as e:
        print(f"Error updating snacks: {e}")
