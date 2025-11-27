import torch
import os
import json

from transformers import Qwen3VLForConditionalGeneration, AutoProcessor, BitsAndBytesConfig
from PIL import Image
from flask import Flask, request, jsonify
import base64
from io import BytesIO
import traceback
import requests
from pyngrok import ngrok


model_path = "models/Qwen3-VL-8B-Instruct"

print("[LLM] Loading model…")

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"[LLM] Using device: {device}")
print(f"[LLM] PyTorch version: {torch.__version__}")

print("[LLM] Loading processor...")
processor = AutoProcessor.from_pretrained(
    model_path,
    trust_remote_code=True,
)

print("[LLM] Loading model...")

# Use the EXACT same configuration that works in VSCode
model = Qwen3VLForConditionalGeneration.from_pretrained(
    model_path,
    trust_remote_code=True,
    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
    low_cpu_mem_usage=True,
    device_map="auto" if device == "cuda" else None,
)

# Apply quantization AFTER loading if on CUDA
if device == "cuda":
    try:
        print("[LLM] Applying 8-bit quantization...")
        from transformers import BitsAndBytesConfig
        # Reload with quantization
        model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            trust_remote_code=True,
            quantization_config=BitsAndBytesConfig(load_in_8bit=True),
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
            device_map="auto",
        )
        print("[LLM] 8-bit quantization applied successfully")
    except Exception as e:
        print(f"[LLM] Quantization not available, using FP16: {e}")
        # Model already loaded in FP16, continue
        pass

if device == "cpu":
    model = model.to(device)

print("[LLM] Model loaded successfully!")


# ==============================
# UTILITIES
# ==============================
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

def _generate_text(messages, max_tokens=150, temperature=0.7, top_p=0.9, images=None):
    """Unified text generation handler"""
    try:
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(
            text=[text],
            images=images if images else None,
            return_tensors="pt",
            padding=True
        ).to(model.device)

        outputs = model.generate(
            **inputs,
            do_sample=temperature > 0,
            max_new_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p
        )

        result = processor.batch_decode(outputs, skip_special_tokens=True)[0]

        # Clean up response
        for split_word in ["assistant", "user"]:
            if split_word in result:
                result = result.split(split_word)[-1].strip()

        return result.strip().replace("\n", " ")
    except Exception as e:
        traceback.print_exc()
        return f"Error: {str(e)}"

# ==============================
# CORE FUNCTIONS
# ==============================
def estimate_nutrition_remote(image_base64, user_prompt=None, role_prompt=None):
    """Estimate nutrition from a base64-encoded image"""
    try:
        # Decode and prepare image
        image = Image.open(BytesIO(base64.b64decode(image_base64))).convert("RGB").resize((224, 224))

        messages = [
            {"role": "system", "content": (role_prompt or DEFAULT_ROLE_PROMPT).strip()},
            {"role": "user", "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": (user_prompt or "Estimate the macronutrient breakdown of my meal.").strip()}
            ]}
        ]

        generated_text = _generate_text(messages, max_tokens=64, temperature=0.7, images=[image])

        # Extract JSON
        json_start = generated_text.rfind('{')
        if json_start != -1:
            json_str = generated_text[json_start:generated_text.find('}', json_start) + 1]
            return json.loads(json_str)
        return {"error": "Could not find JSON in model output"}

    except Exception as e:
        traceback.print_exc()
        return {"error": str(e)}

def describe_food_remote(image_base64):
    """Generate a concise description of the food in the image"""
    try:
        image = Image.open(BytesIO(base64.b64decode(image_base64))).convert("RGB").resize((224, 224))
        
        system_prompt = """
        You are a food description assistant.
        Describe the food shown in the image concisely in 1-2 sentences.
        Focus on identifying the main dish, ingredients, and preparation method.
        Provide measurements in grams, cups or portions as necessary.
        Keep it brief and natural, like how someone would describe their meal.
        """
        
        messages = [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "Describe this food briefly."}
            ]}
        ]
        
        description = _generate_text(messages, max_tokens=60, temperature=0.7, images=[image])
        return description.strip()
        
    except Exception as e:
        traceback.print_exc()
        return f"Error: {str(e)}"

def get_dynamic_tips_remote(meal_context):
    """
    Generate dynamic tips based on which thresholds were exceeded.
    Tips are tailored to address only the specific issues present.
    """
    exceeded_macros = meal_context.get("exceeded_macros", {})
    high_hunger = meal_context.get("high_hunger", False)
    low_energy = meal_context.get("low_energy", False)
    meal_type = meal_context.get("meal_type", "meal")
    energy_level = meal_context.get("energy_level")
    hunger_level = meal_context.get("hunger_level")
    
    # Build dynamic user prompt based on what's exceeded
    issues = []
    
    if exceeded_macros:
        exceeded_str = ", ".join([
            f"{n} by {v:.1f}g" if n != "Calories" else f"{n} by {v:.0f} kcal"
            for n, v in exceeded_macros.items()
        ])
        issues.append(f"exceeded macronutrient targets ({exceeded_str})")
    
    if high_hunger:
        issues.append(f"still feeling quite hungry (hunger level: {hunger_level}/5)")
    
    if low_energy:
        issues.append(f"experiencing low energy (energy level: {energy_level}/5)")
    
    # Construct the prompt
    user_prompt = f"After my {meal_type}, I'm experiencing the following: {'; '.join(issues)}. "
    
    # Add specific guidance request based on issues
    advice_needed = []
    if exceeded_macros:
        advice_needed.append("balance my macros for the next meal")
    if high_hunger:
        advice_needed.append("feel more satiated")
    if low_energy:
        advice_needed.append("boost my energy levels")
    
    user_prompt += f"Please provide practical advice to help me {' and '.join(advice_needed)}."
    
    # Dynamic system prompt that adapts to the specific issues
    role_prompt = """
    You are a friendly, professional nutrition assistant.
    Always acknowledge the user's specific situation before giving advice.
    Provide targeted, actionable advice that addresses ONLY the issues mentioned by the user.
    Never use emojis.
    """
    
    if exceeded_macros:
        role_prompt += """
    - For macro imbalances: suggest specific food types or adjustments for their next meal to rebalance intake.
        """
    
    if high_hunger:
        role_prompt += """
    - For high hunger: recommend foods that promote satiety (high protein, fiber, healthy fats).
        """
    
    if low_energy:
        role_prompt += """
    - For low energy: suggest foods that provide sustained energy (complex carbs, balanced meals, hydration tips).
        """
    
    role_prompt += """
    Keep responses clear, practical, and under 5 sentences.
    Focus exclusively on nutrition and diet advice.
    """

    messages = [
        {"role": "system", "content": role_prompt.strip()},
        {"role": "user", "content": user_prompt.strip()}
    ]

    return _generate_text(messages, max_tokens=150, temperature=0.8)

def get_chat_response_remote(user_message, daily_macros=None, daily_goals=None, meals_logged=None):
    """Generate a chat response with enhanced context"""
    system_prompt = """
    You are a helpful, friendly nutrition and fitness assistant. 
    Always start by acknowledging the user's question or comment.
    Focus your responses on nutrition, diet, fitness, and healthy eating.
    Keep responses concise (under 6 sentences), practical, and supportive.
    Never use emojis.
    If the user asks questions unrelated to nutrition, fitness, or their diet, politely explain that you can only provide advice in those areas and suggest seeking guidance from a relevant professional.
    """

    # Add consumed vs goal context if both are available
    if daily_macros and daily_goals:
        system_prompt += f"""

        The user's nutritional status today:
        CONSUMED so far:
        - Calories: {daily_macros.get('Calories', 0)} kcal
        - Protein: {daily_macros.get('Proteins', 0)}g
        - Carbs: {daily_macros.get('Carbs', 0)}g
        - Fats: {daily_macros.get('Fats', 0)}g

        DAILY GOALS:
        - Calories: {daily_goals.get('Calories', 0)} kcal
        - Protein: {daily_goals.get('Proteins', 0)}g
        - Carbs: {daily_goals.get('Carbs', 0)}g
        - Fats: {daily_goals.get('Fats', 0)}g
        """
        
        # Calculate remaining
        remaining = {
            'Calories': daily_goals.get('Calories', 0) - daily_macros.get('Calories', 0),
            'Proteins': daily_goals.get('Proteins', 0) - daily_macros.get('Proteins', 0),
            'Carbs': daily_goals.get('Carbs', 0) - daily_macros.get('Carbs', 0),
            'Fats': daily_goals.get('Fats', 0) - daily_macros.get('Fats', 0)
        }
        
        system_prompt += f"""
        REMAINING for today:
        - Calories: {remaining['Calories']} kcal
        - Protein: {remaining['Proteins']}g
        - Carbs: {remaining['Carbs']}g
        - Fats: {remaining['Fats']}g
        """
        
        # Only suggest adjustments if it's highly relevant to the user's question or if they're significantly off track
        has_significant_issue = (
            remaining['Calories'] < -500 or remaining['Calories'] > 800 or
            remaining['Proteins'] < -20 or remaining['Proteins'] > 50 or
            remaining['Carbs'] < -30 or remaining['Carbs'] > 100 or
            remaining['Fats'] < -15 or remaining['Fats'] > 30
        )
        
        if has_significant_issue:
            system_prompt += """
        
        NOTE: Only mention the user's progress toward their goals if it's directly relevant to their question or if they have a significant macro imbalance that needs addressing.
            """
        else:
            system_prompt += """
        
        NOTE: The user's intake is reasonably on track. Only mention their macro status if they specifically ask about it. Focus on answering their actual question.
            """
    
    # Add meals logged context
    if meals_logged:
        meals_str = ", ".join(meals_logged)
        system_prompt += f"""

        Meals logged today: {meals_str}
        Only mention which meals they've had if relevant to their question (e.g., "What should I eat for lunch?" when they haven't had lunch yet).
        """

    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_message.strip()}
    ]

    return _generate_text(messages, max_tokens=200, temperature=0.7)

# ==============================
# FLASK API
# ==============================
app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "model": "Qwen3-VL-8B-Instruct", "device": device})

@app.route("/estimate_nutrition", methods=["POST"])
def api_estimate_nutrition():
    data = request.get_json()
    result = estimate_nutrition_remote(
        data.get("image_base64"),
        data.get("user_prompt"),
        data.get("role_prompt")
    )
    return jsonify(result)

@app.route("/describe_food", methods=["POST"])
def api_describe_food():
    """Generate a description of the food in an image"""
    data = request.get_json()
    result = describe_food_remote(data.get("image_base64"))
    return jsonify({"description": result})

@app.route("/dynamic_tips", methods=["POST"])
def api_dynamic_tips():
    """
    Unified endpoint for generating dynamic tips based on meal context.
    Replaces separate reduction_tips and wellness_tips endpoints.
    """
    data = request.get_json()
    meal_context = data.get("meal_context", {})
    result = get_dynamic_tips_remote(meal_context)
    return jsonify({"advice": result})

@app.route("/chat", methods=["POST"])
def api_chat():
    data = request.get_json()
    result = get_chat_response_remote(
        data.get("message"),
        data.get("daily_macros"),
        data.get("daily_goals"),
        data.get("meals_logged")
    )
    return jsonify({"response": result})

# ==============================
# START SERVER
# ==============================
ngrok.set_auth_token('353Nn9GHQSgKzMpFwvEFtDG6uDy_3JT5JoUPpQBeLnrSdvRBL')
public_url = ngrok.connect(5000)
print("\n" + "="*60)
print("LLM Server is running!")
print("="*60)
print(f"Public URL: {public_url}")
print("="*60)
print("\nEndpoints available:")
print(f"  - {public_url}/health (GET)")
print(f"  - {public_url}/estimate_nutrition (POST)")
print(f"  - {public_url}/dynamic_tips (POST)")
print(f"  - {public_url}/chat (POST)")
print("\nIMPORTANT: Copy the public URL and paste it in your local chatbot.py file!")
print("="*60 + "\n")

app.run(port=5000)