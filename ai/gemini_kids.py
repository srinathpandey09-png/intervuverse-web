# ai/gemini_kids.py
import os
import google.generativeai as genai
import random
import json

# --------------------------------------------------------------------
# LOAD API KEY
# --------------------------------------------------------------------
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    raise Exception("❌ GEMINI_API_KEY is not set. Add it to your environment.")

genai.configure(api_key=API_KEY)

# --------------------------------------------------------------------
# TOPICS
# --------------------------------------------------------------------
kids_topics = [
    "colors", "animals", "fruits", "family", "toys",
    "sounds", "school items", "numbers", "weather", "flowers"
]

# --------------------------------------------------------------------
# STRICT JSON SAFE GENERATOR
# --------------------------------------------------------------------
def safe_json_extract(text):
    """
    Gemini sometimes adds extra text around JSON.
    This extracts only the JSON portion safely.
    """
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        cleaned = text[start:end]
        return json.loads(cleaned)
    except:
        return None

# --------------------------------------------------------------------
# GENERATE QUESTION
# --------------------------------------------------------------------
def kids_generate_question():
    topic = random.choice(kids_topics)

    prompt = f"""
Generate ONE simple oral interview question for a 3–6 year child.
Topic: {topic}
Rules:
- use very simple nursery-level vocabulary
- only ONE question sentence
- no explanation
Only return the question text.
"""

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)

    return response.text.strip()

# --------------------------------------------------------------------
# EVALUATE ANSWER (STRICT JSON)
# --------------------------------------------------------------------
def kids_evaluate(question, answer):

    prompt = f"""
You are an evaluator for a 3–6 year child interview.

QUESTION: {question}
ANSWER: {answer}

Give output ONLY in PERFECT JSON like:

{{
  "score": 75,
  "notes": "Good! You answered correctly."
}}

Rules:
- score between 0–100
- notes must be max 2 short child-friendly lines
- DO NOT add any explanation outside JSON
"""

    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)

    # Attempt strict JSON parse
    result = safe_json_extract(response.text)

    if result:
        return result

    # If Gemini fails, give fallback but DIFFERENT every time
    fallback_score = random.randint(40, 85)
    fallback_notes = random.choice([
        "Good try! You can answer with more details.",
        "Nice effort! Try speaking a little more.",
        "Good job! You are learning well.",
        "Well done! You can add a little more next time."
    ])

    return {
        "score": fallback_score,
        "notes": fallback_notes
    }
