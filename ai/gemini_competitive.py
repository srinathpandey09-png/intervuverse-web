# ai/gemini_competitive.py

"""
Gemini helpers for Competitive / UPSC / NDA / Job interview mode.

We build on the generic gemini_client used in viva mode.
"""

from typing import Dict
import ai.gemini_client as gemini


def competitive_generate_question(
    track: str,
    role: str,
    difficulty: str,
    language: str,
) -> str:
    """
    Generate one realistic panel-style interview question.
    """
    role_txt = role.strip() or "the target role / post"
    prompt = f"""
You are a senior interview board conducting a high-stakes oral interview.

Track: {track}
Target role/post: {role_txt}
Difficulty level: {difficulty}
Language: {language}

Generate EXACTLY ONE interview question that:
- sounds like it is asked by a panel member,
- is concise (1–2 sentences, not very long),
- is appropriate for {track},
- is open-ended and encourages a structured answer,
- does NOT include numbering, bullet points or commentary like "Here is your question".

Return ONLY the question sentence, nothing else.
"""

    try:
        raw = gemini.generate_question(prompt)
        if isinstance(raw, dict):
            q = raw.get("text") or raw.get("question") or ""
        else:
            q = str(raw)
        q = q.strip()
        if not q:
            q = "Why do you think you are suitable for this role?"
        return q
    except Exception:
        return "Why do you think you are suitable for this role?"


def competitive_evaluate(
    question: str,
    answer: str,
    track: str,
    role: str,
    difficulty: str,
    language: str,
) -> Dict:
    """
    Evaluate the candidate's answer and return:
    - score (0-100)
    - notes (panel feedback paragraph) in this there should be no special characters like asterik and dont mention the word viva it is an interview
    - confidence (Low/Medium/High)
    - communication (Needs work/Good/Excellent)
    """
    base_score = 55
    notes = ""

    try:
        base = gemini.evaluate_answer(question, answer)
        base_score = int(base.get("score", 55))
        notes = base.get("notes", "").strip()
    except Exception:
        # simple fallback scoring if Gemini call fails
        word_count = len((answer or "").split())
        base_score = max(30, min(95, word_count * 3 + 35))
        notes = (
            "Good attempt. Work on giving a more structured answer with 3-4 clear points "
            "and concrete examples from your experience."
        )

    if not notes:
        notes = (
            "Panel feedback: overall reasonable answer; focus more on structure, clarity "
            "and linking your thoughts to the specific role."
        )

    # lightweight confidence + communication labels derived from score + length
    words = len((answer or "").split())

    if base_score >= 80 and words >= 70:
        confidence = "High"
        communication = "Excellent"
    elif base_score >= 65 and words >= 40:
        confidence = "Medium"
        communication = "Good"
    else:
        confidence = "Low"
        communication = "Needs work"

    return {
      "score": int(base_score),
      "notes": notes,
      "confidence": confidence,
      "communication": communication,
    }
