import json
import ai.gemini_client as gemini

def _call_gemini(prompt: str) -> str:
    """
    Small helper so we work with whatever you already have in gemini_client.
    Tries generate_text() first, falls back to generate_question().
    """
    if hasattr(gemini, "generate_text"):
        return gemini.generate_text(prompt)
    elif hasattr(gemini, "generate_question"):
        return gemini.generate_question(prompt)
    else:
        # last fallback – just in case
        return str(gemini.evaluate_answer("SYSTEM", prompt))

def analyze_resume(resume_text: str, target_role: str = "", mode: str = "general") -> dict:
    """
    Uses Gemini to analyze a resume and return a structured dict:

    {
      "overall_score": int 0–100,
      "ats_score": int,
      "clarity_score": int,
      "impact_score": int,
      "grammar_score": int,
      "strengths": [str, ...],
      "improvements": [str, ...],
      "summary": str
    }
    """

    truncated = resume_text[:8000]

    prompt = f"""
You are an expert ATS (Applicant Tracking System) + communication coach.

Analyse the following RESUME for suitability to the role: "{target_role or "General Student / Fresher"}".

Mode: {mode}

Return your answer as STRICT JSON only, **no explanations outside JSON**.
Use this exact schema:

{{
  "overall_score": 0-100,
  "ats_score": 0-100,
  "clarity_score": 0-100,
  "impact_score": 0-100,
  "grammar_score": 0-100,
  "strengths": ["point 1", "point 2", "point 3"],
  "improvements": ["point 1", "point 2", "point 3"],
  "summary": "2–4 lines overall review"
}}

Now analyse this resume:

<<<RESUME_TEXT_START>>>
{truncated}
<<<RESUME_TEXT_END>>>
"""

    raw = _call_gemini(prompt)

    # raw might already be dict or string
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw).strip()
        # try to find JSON block if model wrapped it
        if "{" in text and "}" in text:
            text = text[text.find("{"): text.rfind("}") + 1]
        try:
            data = json.loads(text)
        except Exception:
            data = {}

    # sensible defaults if model misbehaves
    def _get_int(key, default):
        try:
            return int(data.get(key, default))
        except Exception:
            return default

    strengths = data.get("strengths") or []
    if isinstance(strengths, str):
        strengths = [strengths]

    improvements = data.get("improvements") or []
    if isinstance(improvements, str):
        improvements = [improvements]

    result = {
        "overall_score": _get_int("overall_score", 70),
        "ats_score": _get_int("ats_score", 70),
        "clarity_score": _get_int("clarity_score", 72),
        "impact_score": _get_int("impact_score", 68),
        "grammar_score": _get_int("grammar_score", 75),
        "strengths": strengths,
        "improvements": improvements,
        "summary": data.get("summary") or "Good resume. Can be improved with clearer bullets and stronger impact verbs."
    }
    return result
