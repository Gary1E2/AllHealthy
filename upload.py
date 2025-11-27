import requests
import datetime
import json

# ==============================
# CONFIG
# ==============================
API_KEY = "AIzaSyB2GDGBE0jWcp9BSLOLs0PZhiuyMi7DW6o"   # <-- replace this with your Web API key
PROJECT_ID = "diet-app-sg"          # <-- your project ID
BASE_URL = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"

# ==============================
# FIREBASE REST (MOCK SINGLETON)
# ==============================
_db_instance = True  # just to preserve your old function structure

def init_firebase():
    """Mock Firebase init (REST version doesn't need actual initialization)."""
    global _db_instance
    if _db_instance:
        print("[Firebase REST] Initialized successfully (no SDK required)")
    return _db_instance


# ==============================
# HELPER FUNCTIONS
# ==============================
def _num_field(value):
    """Helper to convert numbers to Firestore-typed fields"""
    return {"integerValue": str(int(value))}


def _make_meal_fields(nutrition_data):
    """Convert nutrition dict to Firestore field map"""
    fields = {
                "calories": _num_field(nutrition_data.get("Calories", 0)),
                "proteins": _num_field(nutrition_data.get("Protein", 0)),
                "carbs": _num_field(nutrition_data.get("Carbs", 0)),
                "fats": _num_field(nutrition_data.get("Fats", 0)),
            }
    # Optional: energy/hunger ratings (1–5)
    if "energy" in nutrition_data:
        fields["energy"] = _num_field(nutrition_data["energy"])
    if "hunger" in nutrition_data:
        fields["hunger"] = _num_field(nutrition_data["hunger"])

    return {"mapValue": {"fields": fields}}


def _get_doc_url(user_id, date_str):
    """Get Firestore REST document URL"""
    return f"{BASE_URL}/users/{user_id}/mealLogs/{date_str}?key={API_KEY}"


def _get_user_url(user_id):
    """Document URL for a user document"""
    return f"{BASE_URL}/users/{user_id}?key={API_KEY}"


def _parse_value(val):
    """Parse a Firestore value object into a Python primitive or dict."""
    if 'integerValue' in val:
        return int(val['integerValue'])
    if 'doubleValue' in val:
        return float(val['doubleValue'])
    if 'stringValue' in val:
        return val['stringValue']
    if 'booleanValue' in val:
        return bool(val['booleanValue'])
    if 'mapValue' in val:
        return _fields_to_dict(val['mapValue'].get('fields', {}))
    if 'arrayValue' in val:
        arr = val['arrayValue'].get('values', [])
        return [_parse_value(v) for v in arr]
    return None


def _fields_to_dict(fields):
    """Convert Firestore fields map to plain Python dict."""
    out = {}
    for k, v in fields.items():
        out[k] = _parse_value(v)
    return out


def get_user_doc(user_id):
    """Fetch a user document via REST and return plain dict or None."""
    try:
        url = _get_user_url(user_id)
        resp = requests.get(url)
        if resp.status_code != 200:
            print(f"[Firebase REST DEBUG] get_user_doc {resp.status_code}: {resp.text}")
            return None
        data = resp.json()
        fields = data.get('fields', {})
        return _fields_to_dict(fields)
    except Exception as e:
        print(f"[Firebase REST ERROR] get_user_doc failed: {e}")
        return None


def get_meal_doc(user_id, date_str):
    """Fetch a mealLogs document for a given date via REST and return plain dict or None."""
    try:
        url = _get_doc_url(user_id, date_str)
        resp = requests.get(url)
        if resp.status_code != 200:
            print(f"[Firebase REST DEBUG] get_meal_doc {resp.status_code}: {resp.text}")
            return None
        data = resp.json()
        fields = data.get('fields', {})
        return _fields_to_dict(fields)
    except Exception as e:
        print(f"[Firebase REST ERROR] get_meal_doc failed: {e}")
        return None


# ==============================
# UPLOAD SINGLE MEAL (REST)
# ==============================
def upload_meal(user_id, meal_type, nutrition_data, date_str=None):
    try:
        init_firebase()

        if date_str is None:
            date_str = datetime.date.today().strftime("%Y-%m-%d")

        url = _get_doc_url(user_id, date_str)
        headers = {"Content-Type": "application/json"}

        # Prepare Firestore REST-compatible payload
        fields = {
            meal_type: _make_meal_fields(nutrition_data),
            "last_updated": {"timestampValue": datetime.datetime.utcnow().isoformat() + "Z"}
        }

        payload = {"fields": fields}

        # PATCH preserves existing fields (like merge=True) but REST patch often requires an updateMask
        # Build updateMask to only update the meal field and last_updated (helps avoid 400 errors)
        mask_params = f"&updateMask.fieldPaths={meal_type}&updateMask.fieldPaths=last_updated"
        patch_url = url + mask_params
        print(f"[Firebase REST DEBUG] PATCH URL: {patch_url}")
        print(f"[Firebase REST DEBUG] Payload: {json.dumps(payload)}")
        response = requests.patch(patch_url, headers=headers, data=json.dumps(payload))

        if response.status_code not in (200, 201):
            print(f"[Firebase REST ERROR] {response.status_code}: {response.text}")
            return False

        print(f"[Firebase REST] Successfully uploaded {meal_type} for {user_id} on {date_str}")
        print(f"[Firebase REST] Meal data: {nutrition_data}")
        return True

    except Exception as e:
        print(f"[Firebase REST ERROR] Failed to upload: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================
# UPLOAD FULL DAY (REST)
# ==============================
def upload_full_day(user_id, date_str, breakfast=None, lunch=None, dinner=None, supper=None, snacks=None):
    try:
        init_firebase()

        url = _get_doc_url(user_id, date_str)
        headers = {"Content-Type": "application/json"}

        fields = {}

        # Build all available meals
        for meal_type, meal_data in [
            ('breakfast', breakfast),
            ('lunch', lunch),
            ('dinner', dinner),
            ('supper', supper),
            ('snacks', snacks)
        ]:
            if meal_data:
                fields[meal_type] = _make_meal_fields(meal_data)

        fields["last_updated"] = {"timestampValue": datetime.datetime.utcnow().isoformat() + "Z"}

        payload = {"fields": fields}

        # When updating multiple fields, include updateMask.fieldPaths entries for each field to merge safely
        mask_parts = []
        for k in fields.keys():
            mask_parts.append(f"updateMask.fieldPaths={k}")
        mask_query = "&" + "&".join(mask_parts) if mask_parts else ""
        patch_url = url + mask_query
        print(f"[Firebase REST DEBUG] PATCH URL (full day): {patch_url}")
        print(f"[Firebase REST DEBUG] Payload (full day): {json.dumps(payload)}")
        response = requests.patch(patch_url, headers=headers, data=json.dumps(payload))

        if response.status_code not in (200, 201):
            print(f"[Firebase REST ERROR] {response.status_code}: {response.text}")
            return False

        print(f"[Firebase REST] Successfully uploaded full day for {user_id} on {date_str}")
        return True

    except Exception as e:
        print(f"[Firebase REST ERROR] Failed to upload full day: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==============================
# TEST FUNCTION
# ==============================
if __name__ == "__main__":
    test_user_id = "user"
    test_nutrition = {
        "Calories": 450,
        "Protein": 25,
        "Carbs": 20,
        "Fats": 15
    }

    print("\n[Firebase TEST] Testing single meal upload (REST)...")
    success = upload_meal(test_user_id, "breakfast", test_nutrition)

    if success:
        print("[Firebase TEST] Success!")
    else:
        print("[Firebase TEST] Failed!")
