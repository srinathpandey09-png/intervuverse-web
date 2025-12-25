// static/js/kids.js
(async function () {

  // ---------- DOM ELEMENTS ----------
  const startBtn = document.getElementById("startBtn");
  const questionText = document.getElementById("questionText");
  const answerText = document.getElementById("answerText");
  const feedbackText = document.getElementById("feedbackText");
  const stickersDiv = document.getElementById("stickers");
  const starsWrap = document.getElementById("starsWrap");
  const downloadReport = document.getElementById("downloadReport");

  const confettiCanvas = document.getElementById("confetti-canvas");
  const ctxConfetti = confettiCanvas.getContext("2d");

  let currentSessionId = null;
  let latestAttemptId = null;


  // ---------- CREATE SESSION ON PAGE LOAD ----------
  (async function initSession() {
    try {
      const res = await fetch("/api/kids_start_session", { method: "POST" });
      if (!res.ok) {
        console.warn("Could not start session:", await res.text());
        return;
      }
      const data = await res.json();
      currentSessionId = data.session_id;
    } catch (e) {
      console.error("Session create failed", e);
    }
  })();


  // ---------- CONFETTI ----------
  function resizeConfetti() {
    confettiCanvas.width = window.innerWidth;
    confettiCanvas.height = window.innerHeight;
  }
  resizeConfetti();
  window.addEventListener("resize", resizeConfetti);

  function fireConfetti() {
    const pieces = [];
    for (let i = 0; i < 80; i++) {
      pieces.push({
        x: Math.random() * confettiCanvas.width,
        y: -20 - Math.random() * 100,
        r: 6 + Math.random() * 10,
        c: ["#ff7aa2", "#ffd166", "#9be7ff", "#b5ffb2"][Math.floor(Math.random() * 4)],
        vx: -1 + Math.random() * 2,
        vy: 2 + Math.random() * 4,
        rot: Math.random() * 10
      });
    }
    let t = 0;
    function draw() {
      t++;
      ctxConfetti.clearRect(0, 0, confettiCanvas.width, confettiCanvas.height);
      for (const p of pieces) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.08;
        p.rot += 0.1;
        ctxConfetti.save();
        ctxConfetti.translate(p.x, p.y);
        ctxConfetti.rotate(p.rot);
        ctxConfetti.fillStyle = p.c;
        ctxConfetti.fillRect(-p.r / 2, -p.r / 2, p.r, p.r * 1.8);
        ctxConfetti.restore();
      }
      if (t < 180) requestAnimationFrame(draw);
    }
    requestAnimationFrame(draw);
  }


  // ---------- STICKERS ----------
  function placeSticker(name) {
    const s = document.createElement("div");
    s.className = "sticker";
    s.innerText = name;
    stickersDiv.appendChild(s);
    setTimeout(() => s.classList.add("bounce"), 50);
    setTimeout(() => s.remove(), 2000);
  }


  // ---------- STARS ----------
  function showStars(n) {
    starsWrap.innerHTML = "";
    for (let i = 1; i <= 5; i++) {
      const sp = document.createElement("span");
      sp.className = "star" + (i <= n ? " on" : "");
      sp.innerText = "★";
      starsWrap.appendChild(sp);
    }
  }


  // ---------- UTILS ----------
  function sleep(ms) {
    return new Promise((res) => setTimeout(res, ms));
  }

  function speak(text) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-IN";
    window.speechSynthesis.speak(u);
  }

  function listenOnce(lang = "en-IN", timeoutMs = 9000) {
    return new Promise((resolve) => {
      const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Rec) return resolve("");

      const r = new Rec();
      r.lang = lang;
      r.interimResults = false;

      let finished = false;
      const timeout = setTimeout(() => {
        if (!finished) {
          finished = true;
          try { r.stop(); } catch {}
          resolve("");
        }
      }, timeoutMs);

      r.onresult = (e) => {
        if (finished) return;
        finished = true;
        clearTimeout(timeout);
        resolve(e.results[0][0].transcript || "");
      };

      r.onerror = () => {
        if (finished) return;
        finished = true;
        clearTimeout(timeout);
        resolve("");
      };

      r.onend = () => {
        if (!finished) {
          finished = true;
          clearTimeout(timeout);
          resolve("");
        }
      };

      try { r.start(); }
      catch { resolve(""); }
    });
  }


  // ---------- API ----------
  async function fetchQuestion() {
    const res = await fetch("/api/kids_question");
    const j = await res.json();
    return j.question;
  }

  async function evaluate(question, transcription) {
    const res = await fetch("/api/kids_evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, transcription })
    });
    return res.json();
  }

  async function saveAttempt(payload) {
    const res = await fetch("/api/kids_save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    return res.json();
  }


  // ---------- RECENT SCORES ----------
  function drawChart(scores) {
    const canvas = document.getElementById("kidsChart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const max = Math.max(100, ...scores);
    const pad = 20;
    const barW = (canvas.width - pad * 2) / scores.length;

    scores.forEach((s, i) => {
      const h = (s / max) * (canvas.height - pad * 2);
      ctx.fillStyle = ["#ffd166", "#ff7aa2", "#9be7ff", "#b5ffb2"][i % 4];
      ctx.fillRect(pad + i * barW, canvas.height - pad - h, barW - 8, h);
    });
  }

  async function loadRecent() {
    const res = await fetch("/api/kids_recent");
    if (!res.ok) return;
    const j = await res.json();
    drawChart(j.scores || []);
  }


  // ---------- SESSION FLOW ----------
  async function runAutoSession(total = 6) {
    startBtn.disabled = true;
    downloadReport.style.display = "none";

    questionText.innerText = "Preparing...";
    stickersDiv.innerHTML = "";
    starsWrap.innerHTML = "";

    for (let i = 0; i < total; i++) {
      let question = (i === 0)
        ? "What is your name?"
        : await fetchQuestion();

      questionText.innerText = question;
      speak(question);
      await sleep(900);

      answerText.innerText = "Listening...";
      const transcription = await listenOnce("en-IN", i === 0 ? 12000 : 9000);
      answerText.innerText = transcription || "(no answer detected)";

      const evalRes = await evaluate(question, transcription);

      speak(evalRes.notes);

      showStars(evalRes.stars);
      feedbackText.innerText = `Score: ${evalRes.score} — ${evalRes.notes}`;

      if (evalRes.score >= 70) { placeSticker("🌟"); fireConfetti(); }
      else if (evalRes.score >= 40) placeSticker("👍 Good");
      else placeSticker("🙂 Try again");

      const saveRes = await saveAttempt({
        session_id: currentSessionId,
        question,
        transcription,
        feedback: evalRes.notes,
        score: evalRes.score,
        stars: evalRes.stars
      });

      latestAttemptId = saveRes.id;
      await sleep(3000);
    }

    feedbackText.innerText = "Session complete!";
    downloadReport.style.display = "inline-block";
    fireConfetti();
    speak("Great! You finished the session!");

    loadRecent();
    startBtn.disabled = false;
  }


  // ---------- BUTTONS ----------
  startBtn.addEventListener("click", async () => {
    await runAutoSession(6);
  });

  downloadReport.addEventListener("click", () => {
    if (!currentSessionId) return alert("Session not started!");
    window.open(`/kids_final_report/${currentSessionId}`, "_blank");
  });

  loadRecent();
})();
