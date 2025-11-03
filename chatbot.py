import os
import json
import torch
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
from PIL import Image
import warnings

# Silence warnings
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
warnings.filterwarnings("ignore", category=FutureWarning)

# ==============================
# CONFIG
# ==============================
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "Qwen2-VL-2B-Instruct")

DEFAULT_ROLE_PROMPT = """
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

# ==============================
# MODEL SINGLETON
# ==============================
_model_instance = None
_processor_instance = None

def load_model():
    """Load and return the model and processor (singleton pattern)"""
    global _model_instance, _processor_instance
    
    if _model_instance is None or _processor_instance is None:
        print("[LLM] Loading processor...")
        _processor_instance = AutoProcessor.from_pretrained(MODEL_DIR, use_fast=True)
        
        print("[LLM] Loading model (this may take a while)...")
        _model_instance = Qwen2VLForConditionalGeneration.from_pretrained(
            MODEL_DIR,
            dtype=torch.float32,
            device_map="auto",
            low_cpu_mem_usage=True
        )
        print("[LLM] Model loaded successfully")
    
    return _model_instance, _processor_instance

# ==============================
# NUTRITION ESTIMATION
# ==============================
def estimate_nutrition(image_path, user_prompt=None, role_prompt=None):
    """
    Estimate nutrition from an image.
    
    Args:
        image_path (str): Path to the image file
        user_prompt (str, optional): Custom user prompt. Defaults to asking for macronutrient breakdown.
        role_prompt (str, optional): Custom system/role prompt. Defaults to nutrition assistant prompt.
    
    Returns:
        dict: Nutrition data with keys: Calories, Protein, Carbs, Fats
        None: If estimation fails
    """
    try:
        # Load image
        if not os.path.exists(image_path):
            print(f"[LLM ERROR] Image not found: {image_path}")
            return None
        
        print(f"[LLM] Loading image: {image_path}")
        image = Image.open(image_path).convert("RGB").resize((224, 224))
        
        # Use default prompts if not provided
        if role_prompt is None:
            role_prompt = DEFAULT_ROLE_PROMPT
        if user_prompt is None:
            user_prompt = "Estimate the macronutrient breakdown of my meal."
        
        # Load model
        model, processor = load_model()
        
        # Prepare messages
        messages = [
            {"role": "system", "content": role_prompt.strip()},
            {"role": "user", "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": user_prompt.strip()}
            ]}
        ]
        
        print("[LLM] Generating nutrition estimate...")
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
        json_start = generated_text.rfind('{')
        if json_start != -1:
            json_str = generated_text[json_start:]
            json_end = json_str.find('}') + 1
            json_str = json_str[:json_end]
            
            nutrition_data = json.loads(json_str)
            print(f"[LLM] Nutrition estimate: {json.dumps(nutrition_data, indent=2)}")
            return nutrition_data
        else:
            print("[LLM ERROR] Could not find JSON in model output")
            print(f"[LLM] Raw output: {generated_text}")
            return None
            
    except Exception as e:
        print(f"[LLM ERROR] During generation: {e}")
        import traceback
        traceback.print_exc()
        return None


# ==============================
# MACRO THRESHOLDS CONFIG
# ==============================
MEAL_THRESHOLDS = {
    "breakfast": {"Calories": 20, "Protein": 19, "Carbs": 26, "Fats": 21},
    "lunch": {"Calories": 31, "Protein": 34, "Carbs": 34, "Fats": 34},
    "dinner": {"Calories": 29, "Protein": 30, "Carbs": 29, "Fats": 29},
    "snack": {"Calories": 9, "Protein": 9, "Carbs": 6, "Fats": 9},
    "supper": {"Calories": 11, "Protein": 8, "Carbs": 6, "Fats": 7},
}

# ==============================
# HELPER: COMPARE WITH THRESHOLDS
# ==============================
def compare_macros(meal_type, meal_macros, total_daily_macros):
    """
    Compare logged meal macros with allowed percentage thresholds.
    Returns dict of exceeded nutrients and their exceeded amounts.
    """
    exceeded = {}
    meal_type = meal_type.lower()

    if meal_type not in MEAL_THRESHOLDS:
        print(f"[WARN] Unknown meal type '{meal_type}'. Skipping threshold check.")
        return exceeded

    for nutrient, threshold_pct in MEAL_THRESHOLDS[meal_type].items():
        # Expected max value for this nutrient based on total daily allowance
        expected_max = (threshold_pct / 100) * total_daily_macros.get(nutrient, 0)
        actual = meal_macros.get(nutrient, 0)

        if actual > expected_max:
            exceeded_amount = round(actual - expected_max, 2)
            exceeded[nutrient] = exceeded_amount

    return exceeded

# ==============================
# FOLLOW-UP LLM TIP PROMPT
# ==============================
def get_reduction_tips(exceeded_dict, meal_type, energy_level=None, hunger_level=None):
    """
    Ask the LLM for advice on reducing intake of exceeded macros.
    Includes user's energy and hunger levels if provided.
    """
    if not exceeded_dict:
        print(f"[LLM] No macro thresholds exceeded for {meal_type}.")
        return None
    
    exceeded_str = ", ".join(
        [f"{nutrient} by {value:.1f}g" if nutrient != "Calories" else f"{nutrient} by {value:.0f} kcal"
         for nutrient, value in exceeded_dict.items()]
    )
    
    # Build the user prompt with survey data if available
    user_prompt = (
        f"My {meal_type} exceeded the expected macronutrient targets: {exceeded_str}. "
    )
    
    if energy_level is not None and hunger_level is not None:
        user_prompt += (
            f"After this meal, my energy level is {energy_level}/5 and my hunger level is {hunger_level}/5. "
        )
    
    user_prompt += (
        f"Give concise, practical diet recommendations for the next meal to balance my macro intake"
    )
    
    if energy_level is not None and hunger_level is not None:
        user_prompt += ", considering my current energy and hunger state"
    
    user_prompt += "."
    
    role_prompt = """
    You are a health and nutrition assistant.
    When a meal exceeds recommended macronutrient percentages, give short actionable advice on how to reduce intake of those nutrients in the next meal.
    If the user provides their energy and hunger levels, incorporate that into your advice (e.g., if energy is low, suggest energy-boosting foods; if hunger is high, suggest satiating options).
    Keep responses under 5 sentences.
    """
    
    # Load model (reuse singleton)
    model, processor = load_model()
    messages = [
        {"role": "system", "content": role_prompt.strip()},
        {"role": "user", "content": user_prompt.strip()}
    ]
    
    print("[LLM] Generating reduction tips...")
    print(f"[LLM] User prompt: {user_prompt}")
    
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], return_tensors="pt", padding=True).to(model.device)
    outputs = model.generate(
        **inputs,
        do_sample=True,
        max_new_tokens=120,
        temperature=0.8,
        top_p=0.9
    )
    advice = processor.batch_decode(outputs, skip_special_tokens=True)[0]
    
    # Keep only the assistant's final message (strip role/system text if present)
    if "assistant" in advice:
        advice = advice.split("assistant")[-1].strip()
    if "user" in advice:
        advice = advice.split("user")[-1].strip()
    
    # Clean up any leftover formatting or extra newlines
    advice = advice.strip().replace("\n", " ")
    print(f"[LLM] Advice: {advice}")
    return advice

# ==============================
# FOLLOW UP LLM WELLNES TIPS
# ==============================
def generate_wellness_tips(meal_type, energy_level, hunger_level):
    """
    Generate tips based on energy and hunger levels when macros are within range.
    """
    user_prompt = (
        f"After my {meal_type}, my energy level is {energy_level}/5 and my hunger level is {hunger_level}/5. "
    )
    
    if energy_level <= 2:
        user_prompt += "I'm feeling low on energy. "
    if hunger_level >= 4:
        user_prompt += "I'm still quite hungry. "
    
    user_prompt += "Give me brief advice on what to eat or do next to feel better."
    
    role_prompt = """
    You are a health and nutrition assistant.
    Provide brief, practical advice based on the user's energy and hunger levels.
    Suggest foods or actions that can help improve their state.
    Keep responses under 4 sentences.
    """
    
    model, processor = load_model()
    messages = [
        {"role": "system", "content": role_prompt.strip()},
        {"role": "user", "content": user_prompt.strip()}
    ]
    
    print("[LLM] Generating wellness tips...")
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], return_tensors="pt", padding=True).to(model.device)
    outputs = model.generate(
        **inputs,
        do_sample=True,
        max_new_tokens=100,
        temperature=0.8,
        top_p=0.9
    )
    advice = processor.batch_decode(outputs, skip_special_tokens=True)[0]
    
    if "assistant" in advice:
        advice = advice.split("assistant")[-1].strip()
    if "user" in advice:
        advice = advice.split("user")[-1].strip()
    
    advice = advice.strip().replace("\n", " ")
    print(f"[LLM] Wellness advice: {advice}")
    return advice


# ==============================
# MAIN ENTRY FOR MEAL LOGGING
# ==============================
def handle_logged_meal(meal_type, meal_macros, total_daily_macros, energy_level=None, hunger_level=None):
    """
    Full pipeline after a meal is logged.
    Compares macros and optionally asks the LLM for dietary advice.
    Includes user's energy and hunger levels if provided.
    """
    print(f"[MEAL] Checking macros for {meal_type}...")
    
    if energy_level is not None and hunger_level is not None:
        print(f"[MEAL] User state - Energy: {energy_level}/5, Hunger: {hunger_level}/5")
    
    exceeded = compare_macros(meal_type, meal_macros, total_daily_macros)
    
    if exceeded:
        print(f"[MEAL] Exceeded macros detected: {exceeded}")
        advice = get_reduction_tips(exceeded, meal_type, energy_level, hunger_level)
        return advice
    else:
        print(f"[MEAL] {meal_type.capitalize()} is within recommended macro limits.")
        
        # Even if macros are fine, provide advice based on energy/hunger if available
        if energy_level is not None and hunger_level is not None:
            if energy_level <= 2 or hunger_level >= 4:
                # Generate tips for low energy or high hunger
                advice = generate_wellness_tips(meal_type, energy_level, hunger_level)
                return advice
        
        return None


def get_chat_response(user_message, context=None):
    """
    Generate a chat response using the LLM.
    
    Args:
        user_message: The user's question/message
        context: Optional dict with user's daily_macros and other context
    
    Returns:
        String response from the LLM
    """
    # Build system prompt with context
    system_prompt = """
    You are a helpful nutrition and health assistant.
    Answer questions about nutrition, diet, fitness, and healthy eating.
    Keep responses concise (under 6 sentences) and practical.
    Be friendly and supportive.
    """
    
    # Add context if available
    if context and 'daily_macros' in context:
        macros = context['daily_macros']
        system_prompt += f"""
        
        The user's current daily intake is:
        - Calories: {macros.get('Calories', 0)} kcal
        - Protein: {macros.get('Protein', 0)}g
        - Carbs: {macros.get('Carbs', 0)}g
        - Fats: {macros.get('Fats', 0)}g
        
        Consider this when giving advice if relevant to their question.
        """
    
    # Load model
    model, processor = load_model()
    
    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_message.strip()}
    ]
    
    print(f"[CHAT] User asked: {user_message}")
    
    # Generate response
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text], return_tensors="pt", padding=True).to(model.device)
    
    outputs = model.generate(
        **inputs,
        do_sample=True,
        max_new_tokens=150,  # Slightly longer for chat responses
        temperature=0.7,
        top_p=0.9
    )
    
    response = processor.batch_decode(outputs, skip_special_tokens=True)[0]
    
    # Clean up response
    if "assistant" in response:
        response = response.split("assistant")[-1].strip()
    if "user" in response:
        response = response.split("user")[-1].strip()
    
    response = response.strip()
    print(f"[CHAT] Response: {response}")
    
    return response