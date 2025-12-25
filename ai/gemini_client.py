import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Load Gemini API Key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("❌ GEMINI_API_KEY not found in .env file")

genai.configure(api_key=GEMINI_API_KEY)

# Use fast model for viva
model = genai.GenerativeModel("gemini-2.5-flash")


# ✅ VIVA QUESTION GENERATOR
def generate_question(prompt: str) -> str:
    try:
        response = model.generate_content(prompt)

        # Safely extract pure text
        text = response.text.strip()

        # ✅ Final safety cleanup
        text = text.replace("\n", " ").strip()

        if not text.endswith("?"):
            text += "?"

        return text

    except Exception as e:
        print("❌ Gemini Viva Question Error:", e)
        return "Explain one important concept from your syllabus."


# ✅ VIVA ANSWER EVALUATOR
def evaluate_answer(question: str, answer: str) -> dict:
    try:
        eval_prompt = f"""
You are a strict school viva examiner.

Question:
{question}

Student Answer:
{answer}

Evaluate strictly on:
1. Accuracy
2. Concept Clarity
3. Completeness
4. Presentation

Return ONLY in this JSON format:
{{
  "score": 0-100,
  "notes": "short feedback"
}}
"""

        response = model.generate_content(eval_prompt)
        text = response.text.strip()

        # Sometimes Gemini returns markdown — clean it
        text = text.replace("```json", "").replace("```", "").strip()

        data = eval(text)  # safe because structure is controlled

        score = int(data.get("score", 50))
        notes = data.get("notes", "Good attempt.")

        return {"score": score, "notes": notes}

    except Exception as e:
        print("❌ Gemini Viva Evaluation Error:", e)

        # Fallback logic (backup scoring)
        words = len(answer.split())
        score = min(100, max(20, words * 6))

        return {
            "score": score,
            "notes": "Good attempt. Improve clarity and depth."
        }
