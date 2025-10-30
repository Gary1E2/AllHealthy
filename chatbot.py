import os
import torch
from transformers import AutoProcessor, Qwen2VLForConditionalGeneration
from threading import Thread
from PIL import Image
import warnings

# ==============================
# CONFIG
# ==============================
# Silence warnings
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
warnings.filterwarnings("ignore", category=FutureWarning)

# Device
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Model folder (local)
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models", "Qwen2-VL-2B-Instruct")

# Image path
IMAGE_PATH = "8c1dipbl84u21.jpg"

# Prompts
ROLE_PROMPT = """
You are a professional AI diet and fitness assistant designed to help users achieve their health goals through accurate nutrition guidance and personalized recommendations.
Your role is to:
- Answer only questions related to nutrition, diet, health, fitness, and exercise.
- Provide accurate calorie and macronutrient information for meals, ingredients, and recipes, including when analyzing uploaded food photos.
- Help users plan balanced meal schedules, edit or create recipes, and suggest healthier alternatives when appropriate.
- Offer general wellness insights such as hydration, portion control, or exercise routines that support dietary goals.
- Use a friendly, motivating, and factual tone in all responses.
You must refuse or redirect any requests unrelated to these topics, such as technology, repairs, politics, or entertainment.
Always keep your responses concise, practical, and tailored to the user's stated goals or preferences.
"""

USER_PROMPT = "Describe this meal and estimate its calories per serving."

# Generation parameters
GENERATION_KWARGS = dict(
    do_sample=True,
    temperature=0.7,
    top_p=0.9,
    max_new_tokens=256,
)

# ==============================
# MODEL LOADING
# ==============================
print("[INFO] Loading processor...")
processor = AutoProcessor.from_pretrained(MODEL_DIR, use_fast=True)

print("[INFO] Loading model (this may take a while)...")
model = Qwen2VLForConditionalGeneration.from_pretrained(
    MODEL_DIR,
    dtype=torch.float16,  # Changed from torch_dtype to dtype
    device_map="auto"
)
print("[INFO] Model loaded successfully")

# ==============================
# STREAMING FUNCTION
# ==============================
def stream_generate(model, processor, prompt, image, **gen_kwargs):
    """Streams tokens as they are generated."""
    try:
        from transformers import TextIteratorStreamer
        
        # Prepare inputs - Qwen2-VL expects specific format
        messages = [
            {
                "role": "system",
                "content": ROLE_PROMPT.strip()
            },
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": USER_PROMPT.strip()}
                ]
            }
        ]
        
        # Apply chat template
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        
        # Process inputs
        inputs = processor(
            text=[text],
            images=[image],
            return_tensors="pt",
            padding=True
        ).to(model.device)
        
        streamer = TextIteratorStreamer(
            processor.tokenizer,
            skip_prompt=True,
            skip_special_tokens=True
        )
        
        # Prepare generation kwargs
        generation_kwargs = {
            **inputs,
            "streamer": streamer,
            **gen_kwargs
        }
        
        # Run generation in background
        thread = Thread(target=model.generate, kwargs=generation_kwargs)
        thread.start()
        
        print("[INFO] Streaming output:\n")
        for new_text in streamer:
            print(new_text, end="", flush=True)
        
        thread.join()
        print("\n\n[INFO] Generation complete")
        
    except Exception as e:
        print(f"[ERROR] During generation: {e}")
        import traceback
        traceback.print_exc()

# ==============================
# MAIN FUNCTION
# ==============================
def main():
    try:
        # Load and verify image
        if not os.path.exists(IMAGE_PATH):
            print(f"[ERROR] Image not found: {IMAGE_PATH}")
            return
        
        print(f"[INFO] Loading image: {IMAGE_PATH}")
        image = Image.open(IMAGE_PATH).convert("RGB")
        print(f"[INFO] Image size: {image.size}")
        
        # Generate response
        stream_generate(model, processor, None, image, **GENERATION_KWARGS)
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()