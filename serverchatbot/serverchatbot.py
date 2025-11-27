import os
import json
import torch
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor, BitsAndBytesConfig
from PIL import Image
from flask import Flask, request, jsonify
import base64
from io import BytesIO
import traceback
import requests
from pyngrok import ngrok


# Load model path from environment (or default to /model)
MODEL_PATH = "models/Qwen2.5-VL-7B-Instruct"

print("Loading model from:", MODEL_PATH)

# Ensure correct "model_id" variable exists
model_id = MODEL_PATH

# Load processor (tokenizer + image processor)
processor = AutoProcessor.from_pretrained(
    model_id,
    trust_remote_code=True
)

print("[LLM] Loading model (this may take a while)…")

# Detect GPU
if torch.cuda.is_available():
    device = "cuda"
    dtype = torch.float16
    use_4bit = True
else:
    device = "cpu"
    dtype = torch.float32
    use_4bit = False  # CPU cannot reliably run 4-bit

# Optional 4-bit quantization (only on GPU)
quantization_config = None
if use_4bit:
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float16
    )

# Load the model
model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    model_id,
    torch_dtype=dtype,
    device_map="auto" if torch.cuda.is_available() else None,
    trust_remote_code=True,
    quantization_config=quantization_config
)

print("[LLM] Model loaded successfully!")
print("Device:", device)

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

def get_reduction_tips_remote(exceeded_dict, meal_type, energy_level=None, hunger_level=None):
    """Generate tips for reducing exceeded macros"""
    if not exceeded_dict:
        return None

    exceeded_str = ", ".join(
        [f"{n} by {v:.1f}g" if n != "Calories" else f"{n} by {v:.0f} kcal"
         for n, v in exceeded_dict.items()]
    )

    user_prompt = f"My {meal_type} exceeded the expected macronutrient targets: {exceeded_str}. "

    if energy_level is not None and hunger_level is not None:
        user_prompt += f"After this meal, my energy level is {energy_level}/5 and my hunger level is {hunger_level}/5. "
        user_prompt += "Give concise, practical diet recommendations for the next meal to balance my macro intake, considering my current energy and hunger state."
    else:
        user_prompt += "Give concise, practical diet recommendations for the next meal to balance my macro intake."

    role_prompt = """
    You are a health and nutrition assistant.
    When a meal exceeds recommended macronutrient percentages, give short actionable advice on how to reduce intake of those nutrients in the next meal.
    If the user provides their energy and hunger levels, incorporate that into your advice.
    Keep responses under 5 sentences.
    """

    messages = [
        {"role": "system", "content": role_prompt.strip()},
        {"role": "user", "content": user_prompt.strip()}
    ]

    return _generate_text(messages, max_tokens=120, temperature=0.8)

def generate_wellness_tips_remote(meal_type, energy_level, hunger_level):
    """Generate wellness tips based on energy and hunger levels"""
    user_prompt = f"After my {meal_type}, my energy level is {energy_level}/5 and my hunger level is {hunger_level}/5. "

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

    messages = [
        {"role": "system", "content": role_prompt.strip()},
        {"role": "user", "content": user_prompt.strip()}
    ]

    return _generate_text(messages, max_tokens=100, temperature=0.8)

def get_chat_response_remote(user_message, daily_macros=None):
    """Generate a chat response"""
    system_prompt = """
    You are a helpful nutrition and health assistant.
    Answer questions about nutrition, diet, fitness, and healthy eating.
    Keep responses concise (under 6 sentences) and practical.
    Be friendly and supportive.
    """

    if daily_macros:
        system_prompt += f"""

        The user's current daily intake is:
        - Calories: {daily_macros.get('Calories', 0)} kcal
        - Protein: {daily_macros.get('Protein', 0)}g
        - Carbs: {daily_macros.get('Carbs', 0)}g
        - Fats: {daily_macros.get('Fats', 0)}g

        Consider this when giving advice if relevant to their question.
        """

    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_message.strip()}
    ]

    return _generate_text(messages, max_tokens=150, temperature=0.7)

# ==============================
# FLASK API
# ==============================
app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "model": "Qwen2-VL-2B-Instruct"})

@app.route("/estimate_nutrition", methods=["POST"])
def api_estimate_nutrition():
    data = request.get_json()
    result = estimate_nutrition_remote(
        data.get("image_base64"),
        data.get("user_prompt"),
        data.get("role_prompt")
    )
    return jsonify(result)

@app.route("/reduction_tips", methods=["POST"])
def api_reduction_tips():
    data = request.get_json()
    result = get_reduction_tips_remote(
        data.get("exceeded_dict", {}),
        data.get("meal_type"),
        data.get("energy_level"),
        data.get("hunger_level")
    )
    return jsonify({"advice": result})

@app.route("/wellness_tips", methods=["POST"])
def api_wellness_tips():
    data = request.get_json()
    result = generate_wellness_tips_remote(
        data.get("meal_type"),
        data.get("energy_level"),
        data.get("hunger_level")
    )
    return jsonify({"advice": result})

@app.route("/chat", methods=["POST"])
def api_chat():
    data = request.get_json()
    result = get_chat_response_remote(
        data.get("message"),
        data.get("daily_macros")
    )
    return jsonify({"response": result})

# ==============================
# START SERVER
# ==============================
public_url = ngrok.connect(5000)
print("\n" + "="*60)
print("LLM Server is running!")
print("="*60)
print(f"Public URL: {public_url}")
print("="*60)
print("\nEndpoints available:")
print(f"  - {public_url}/health (GET)")
print(f"  - {public_url}/estimate_nutrition (POST)")
print(f"  - {public_url}/reduction_tips (POST)")
print(f"  - {public_url}/wellness_tips (POST)")
print(f"  - {public_url}/chat (POST)")
print("\nIMPORTANT: Copy the public URL and paste it in your local chatbot.py file!")
print("="*60 + "\n")

app.run(port=5000)