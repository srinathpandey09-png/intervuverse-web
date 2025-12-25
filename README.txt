
IntervuVerse - Demo Web App (Flask)
----------------------------------
This is a demo, ready-to-publish web app bundle for IntervuVerse.
It includes voice-based UI (uses browser Web Speech API) and a Flask backend.

How to run (Linux / Windows / Mac):
1. Make a python venv: python -m venv venv
2. Activate it: source venv/bin/activate  (or venv\Scripts\activate on Windows)
3. Install: pip install -r requirements.txt
4. Run: python app.py
5. Open: http://localhost:5000

Notes:
- This demo uses the browser's speech recognition and speechSynthesis (Chrome recommended).
- The AI evaluation endpoint (/api/evaluate) is mocked for demo; connect to Gemini 2.5 Flash API in ai/evaluate.py to enable real evaluation.
- The SQLite DB is located at database/intervuverse.db
- The CSS used across the app is the uploaded style.css (copied into static/css/style.css).
