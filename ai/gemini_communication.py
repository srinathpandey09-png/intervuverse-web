import os
import json
import textwrap
from dotenv import load_dotenv

load_dotenv()

try:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
    _model = genai.GenerativeModel("gemini-2.5-flash")
except Exception:
    _model = None


def _ask_gemini(prompt: str) -> str:
    if not _model:
        return ""
    try:
        resp = _model.generate_content(prompt)
        return resp.text or ""
    except Exception:
        return ""


def _safe_int(v, default=60):
    try:
        return int(v)
    except Exception:
        return default


# ============ PUBLIC SPEAKING ============

def generate_speech_prompt(topic_hint: str, level: str) -> str:
    level_label = {
        "easy": "very simple school-level",
        "standard": "standard high-school",
        "tough": "challenging competitive-level"
    }.get(level, "standard high-school")

    if topic_hint:
        base = f"Generate one {level_label} public speaking topic based on: {topic_hint!r}."
    else:
        base = f"Generate one {level_label} public speaking topic for a student."

    prompt = textwrap.dedent(f"""
    {base}
    Rules:
    - Answer must be ONLY the topic line, no bullets, no numbering.
    - Make it suitable for a 1–2 minute speech.
    """).strip()

    out = _ask_gemini(prompt).strip()
    return out or (topic_hint or "Introduce yourself to an interview panel.")


def evaluate_speech(prompt_text: str, transcript: str) -> dict:
    if not transcript.strip():
        return {
            "overall_score": 40,
            "confidence": 45,
            "clarity": 45,
            "structure": 40,
            "body_language_tips": "Try to speak a little louder and with more energy.",
            "overall_feedback": "Try to speak more and share at least 3–4 points on the topic."
        }

    sys_prompt = textwrap.dedent(f"""
    You are a professional communication trainer for public speaking.

    Evaluate the student's speech strictly based on this topic:
    "{prompt_text}"

    Transcript:
    "{transcript}"

    Give a detailed evaluation and return JSON ONLY in this exact schema:

    {{
      "overall_score": 0-100,
      "confidence": 0-100,
      "clarity": 0-100,
      "structure": 0-100,
      "body_language_tips": "short practical tips (2-3 lines)",
      "overall_feedback": "paragraph of feedback (4-6 lines, student-friendly)"
    }}
    Do not include any extra text outside JSON.
    """).strip()

    raw = _ask_gemini(sys_prompt)
    try:
        data = json.loads(raw)
    except Exception:
        words = len(transcript.split())
        score = max(40, min(95, words * 3))
        return {
            "overall_score": score,
            "confidence": min(100, score + 5),
            "clarity": max(40, score - 5),
            "structure": max(40, score - 10),
            "body_language_tips": "Stand straight, smile gently and maintain a steady pace.",
            "overall_feedback": "Good effort. Try to organise your points in a clearer order and add an opening and closing line."
        }

    return {
        "overall_score": _safe_int(data.get("overall_score", 60)),
        "confidence": _safe_int(data.get("confidence", 60)),
        "clarity": _safe_int(data.get("clarity", 60)),
        "structure": _safe_int(data.get("structure", 60)),
        "body_language_tips": data.get("body_language_tips", ""),
        "overall_feedback": data.get("overall_feedback", "")
    }


# ============ CONVERSATIONAL ENGLISH ============

def generate_conversation_question(history, goal: str) -> str:
    if not history:
        base = "Start a friendly interview-style conversation with the student."
    else:
        base = "Continue the conversation with a follow-up question based on the student's last answer."

    last_answer = history[-1]["answer"] if history else ""
    prompt = textwrap.dedent(f"""
    {base}
    Conversation goal (optional): "{goal}"

    Previous answer (may be empty):
    "{last_answer}"

    Rules:
    - Return ONLY one short, clear question (1-2 sentences).
    - English only.
    """).strip()

    out = _ask_gemini(prompt).strip()
    return out or "Can you tell me about your hobbies?"


def evaluate_conversation(question: str, answer: str, history) -> dict:
    if not answer.strip():
        return {
            "overall_score": 40,
            "fluency": 40,
            "grammar": 40,
            "vocabulary": 40,
            "clarity": 40,
            "overall_feedback": "Try to answer in full sentences and share a little more detail."
        }

    prompt = textwrap.dedent(f"""
    You are a conversational English trainer.

    Question:
    "{question}"

    Student answer:
    "{answer}"

    Evaluate the answer and return JSON ONLY in this schema:

    {{
      "overall_score": 0-100,
      "fluency": 0-100,
      "grammar": 0-100,
      "vocabulary": 0-100,
      "clarity": 0-100,
      "overall_feedback": "5-7 line feedback with specific suggestions"
    }}
    """).strip()

    raw = _ask_gemini(prompt)
    try:
        data = json.loads(raw)
    except Exception:
        words = len(answer.split())
        base = max(35, min(90, words * 3))
        return {
            "overall_score": base,
            "fluency": base,
            "grammar": max(35, base - 5),
            "vocabulary": max(35, base - 5),
            "clarity": max(35, base - 5),
            "overall_feedback": "Good attempt. Try to use complete sentences, avoid very long pauses and add 1–2 examples to support your answer."
        }

    return {
        "overall_score": _safe_int(data.get("overall_score", 60)),
        "fluency": _safe_int(data.get("fluency", 60)),
        "grammar": _safe_int(data.get("grammar", 60)),
        "vocabulary": _safe_int(data.get("vocabulary", 60)),
        "clarity": _safe_int(data.get("clarity", 60)),
        "overall_feedback": data.get("overall_feedback", "")
    }


# ============ DEBATE TRAINER ============

def generate_debate_prompt(topic_hint: str, side: str) -> str:
    role_side = "supporting" if side == "for" else "opposing"
    if topic_hint:
        base = f"Create one debate motion related to: {topic_hint!r}."
    else:
        base = "Create one current-affairs debate motion suitable for a school / college debate."

    prompt = textwrap.dedent(f"""
    {base}
    The student will speak on the {role_side} side.

    Rules:
    - Return ONLY the motion in the format: "This house believes that ..."
    - English only.
    """).strip()

    out = _ask_gemini(prompt).strip()
    if not out:
        out = "This house believes that social media does more harm than good."
    return out


def evaluate_debate(motion: str, argument: str, side: str) -> dict:
    if not argument.strip():
        return {
            "overall_score": 40,
            "confidence": 45,
            "logic": 40,
            "evidence": 35,
            "emotion": 45,
            "overall_feedback": "Try to give at least 3 strong points with some examples or data."
        }

    prompt = textwrap.dedent(f"""
    You are a debate coach.

    Motion:
    "{motion}"

    Student side: "{'for' if side == 'for' else 'against'}"

    Student argument:
    "{argument}"

    Evaluate the argument and return JSON ONLY:

    {{
      "overall_score": 0-100,
      "confidence": 0-100,
      "logic": 0-100,
      "evidence": 0-100,
      "emotion": 0-100,
      "overall_feedback": "5-7 line feedback covering strengths and improvements"
    }}
    """).strip()

    raw = _ask_gemini(prompt)
    try:
        data = json.loads(raw)
    except Exception:
        words = len(argument.split())
        base = max(40, min(95, words * 3))
        return {
            "overall_score": base,
            "confidence": base,
            "logic": max(40, base - 5),
            "evidence": max(35, base - 10),
            "emotion": max(40, base - 5),
            "overall_feedback": "Good passion. Try to organise your points more clearly and add at least one strong example or statistic."
        }

    return {
        "overall_score": _safe_int(data.get("overall_score", 60)),
        "confidence": _safe_int(data.get("confidence", 60)),
        "logic": _safe_int(data.get("logic", 60)),
        "evidence": _safe_int(data.get("evidence", 60)),
        "emotion": _safe_int(data.get("emotion", 60)),
        "overall_feedback": data.get("overall_feedback", "")
    }
