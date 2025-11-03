from chatbot import estimate_nutrition
from upload import upload_meal
import datetime

# ==============================
# CONFIGURATION
# ==============================
USER_ID = "user"  # Change this to your user ID
IMAGE_PATH = "images/chickenrice.jpg"  # Path to your meal image
MEAL_TYPE = "dinner"  # Options: 'breakfast', 'lunch', 'dinner', 'supper', 'snacks'

# Optional: Custom prompts (leave as None to use defaults)
CUSTOM_USER_PROMPT = None  # e.g., "What's the nutrition content of this meal?"
CUSTOM_ROLE_PROMPT = None  # e.g., Custom system prompt

# Optional: Specific date (leave as None to use today's date)
DATE_STR = None  # e.g., "2025-10-31" or None for today

# ==============================
# MAIN FUNCTION
# ==============================
def main():
    print("="*60)
    print("MEAL LOGGER - LLM + Firebase")
    print("="*60)
    
    # Step 1: Get nutrition estimate from LLM
    print(f"\n[STEP 1] Analyzing image: {IMAGE_PATH}")
    nutrition_data = estimate_nutrition(
        image_path=IMAGE_PATH,
        user_prompt=CUSTOM_USER_PROMPT,
        role_prompt=CUSTOM_ROLE_PROMPT
    )
    
    if nutrition_data is None:
        print("\n[FAILED] Could not estimate nutrition from image")
        return
    
    print(f"\n[SUCCESS] Nutrition estimated:")
    print(f"  Calories: {nutrition_data.get('Calories')} kcal")
    print(f"  Protein: {nutrition_data.get('Protein')} g")
    print(f"  Carbs: {nutrition_data.get('Carbs')} g")
    print(f"  Fats: {nutrition_data.get('Fats')} g")
    
    # Step 2: Upload to Firebase
    print(f"\n[STEP 2] Uploading to Firebase...")
    date_to_use = DATE_STR if DATE_STR else datetime.date.today().strftime("%Y-%m-%d")
    
    success = upload_meal(
        user_id=USER_ID,
        meal_type=MEAL_TYPE,
        nutrition_data=nutrition_data,
        date_str=date_to_use
    )
    
    if success:
        print(f"\n[SUCCESS] Meal logged successfully!")
        print(f"  User: {USER_ID}")
        print(f"  Meal: {MEAL_TYPE}")
        print(f"  Date: {date_to_use}")
    else:
        print("\n[FAILED] Could not upload to Firebase")
    
    print("\n" + "="*60)
    print("DONE")
    print("="*60)

# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    main()