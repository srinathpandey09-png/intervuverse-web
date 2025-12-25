// static/js/competitive.js
(function () {
  const trackEl        = document.getElementById("cmpTrack");
  const roleEl         = document.getElementById("cmpRole");
  const diffEl         = document.getElementById("cmpDifficulty");
  const langEl         = document.getElementById("cmpLanguage");
  const qcountEl       = document.getElementById("cmpQCount");

  const startBtn       = document.getElementById("cmpStartBtn");
  const downloadBtn    = document.getElementById("cmpDownloadBtn");
  const analyticsBtn   = document.getElementById("cmpAnalyticsBtn");

  const qBox           = document.getElementById("cmpQuestion");
  const aBox           = document.getElementById("cmpAnswer");
  const fBox           = document.getElementById("cmpFeedback");
  const starsBox       = document.getElementById("cmpStars");
  const scoreLine      = document.getElementById("cmpScoreLine");
  const progressLine   = document.getElementById("cmpProgress");
  const statusLine     = document.getElementById("cmpSessionStatus");

  const chairStatus    = document.getElementById("cmpChairStatus");
  const subjStatus     = document.getElementById("cmpSubjectStatus");
  const hrStatus       = document.getElementById("cmpHRStatus");

  const miniChartCanvas = document.getElementById("cmpMiniChart");
  const analyticsModal  = document.getElementById("cmpAnalyticsModal");
  const fullChartCanvas = document.getElementById("cmpFullChart");

  const confettiCanvas  = document.getElementById("cmpConfettiCanvas");
  const confettiCtx     = confettiCanvas.getContext("2d");

  let running = false;
  let currentSessionId = null;
  let sessionScores = [];

  // ---------- helpers ----------
  function resizeConfetti() {
    confettiCanvas.width = window.innerWidth;
    confettiCanvas.height = window.innerHeight;
  }
  resizeConfetti();
  window.addEventListener("resize", resizeConfetti);

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function speak(text, langCode = "en-IN", rate = 0.98) {
    return new Promise((resolve) => {
      if (!("speechSynthesis" in window)) return resolve();
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = langCode;
      u.rate = rate;
      u.onend = () => resolve();
      u.onerror = () => resolve();
      window.speechSynthesis.speak(u);
    });
  }

  function listenOnce(timeoutMs = 14000) {
    return new Promise((resolve) => {
      const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!Rec) return resolve("");

      const r = new Rec();
      r.lang = langEl.value === "Hindi" ? "hi-IN" : "en-IN";
      r.interimResults = false;
      r.maxAlternatives = 1;

      let done = false;
      const to = setTimeout(() => {
        if (!done) {
          done = true;
          try { r.stop(); } catch (e) {}
          resolve("");
        }
      }, timeoutMs);

      r.onresult = (ev) => {
        if (done) return;
        done = true;
        clearTimeout(to);
        resolve(ev.results[0][0].transcript || "");
      };
      r.onerror = () => {
        if (done) return;
        done = true;
        clearTimeout(to);
        resolve("");
      };
      r.onend = () => {
        if (done) return;
        done = true;
        clearTimeout(to);
        resolve("");
      };

      try { r.start(); } catch (e) {
        clearTimeout(to);
        resolve("");
      }
    });
  }

  async function postJSON(url, payload) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {})
    });
    if (!res.ok) throw new Error("Request failed: " + url);
    return res.json();
  }

  async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error("GET failed: " + url);
    return res.json();
  }

  function showStars(n) {
    starsBox.innerHTML = "";
    const full = Math.max(1, Math.min(5, n));
    for (let i = 1; i <= 5; i++) {
      const span = document.createElement("span");
      span.textContent = i <= full ? "★" : "☆";
      span.style.marginRight = "3px";
      span.style.fontSize = "18px";
      starsBox.appendChild(span);
    }
  }

  function fireConfetti() {
    confettiCanvas.style.display = "block";
    const pieces = [];
    for (let i = 0; i < 220; i++) {
      pieces.push({
        x: Math.random() * confettiCanvas.width,
        y: -20 - Math.random() * 200,
        r: 6 + Math.random() * 10,
        c: ["#ffd166", "#ff7aa2", "#9be7ff", "#b5ffb2"][Math.floor(Math.random() * 4)],
        vx: -1 + Math.random() * 2,
        vy: 2 + Math.random() * 4,
        rot: Math.random() * 10
      });
    }
    let t = 0;
    function draw() {
      t++;
      confettiCtx.clearRect(0, 0, confettiCanvas.width, confettiCanvas.height);
      for (const p of pieces) {
        p.x += p.vx;
        p.y += p.vy;
        p.vy += 0.08;
        p.rot += 0.08;
        confettiCtx.save();
        confettiCtx.translate(p.x, p.y);
        confettiCtx.rotate(p.rot);
        confettiCtx.fillStyle = p.c;
        confettiCtx.fillRect(-p.r / 2, -p.r / 2, p.r, p.r * 1.8);
        confettiCtx.restore();
      }
      if (t < 240) requestAnimationFrame(draw);
      else {
        confettiCtx.clearRect(0, 0, confettiCanvas.width, confettiCanvas.height);
        confettiCanvas.style.display = "none";
      }
    }
    requestAnimationFrame(draw);
  }

  function drawMiniChart(scores) {
    if (!miniChartCanvas) return;
    const ctx = miniChartCanvas.getContext("2d");
    const w = miniChartCanvas.width;
    const h = miniChartCanvas.height;

    ctx.clearRect(0, 0, w, h);
    if (!scores || !scores.length) return;

    const pad = 10;
    const max = Math.max(100, ...scores);
    const bw = (w - pad * 2) / scores.length;

    scores.forEach((s, i) => {
      const bh = (s / max) * (h - pad * 2);
      ctx.fillStyle = ["#ffd166", "#ff7aa2", "#9be7ff", "#b5ffb2"][i % 4];
      ctx.fillRect(pad + i * bw + 4, h - pad - bh, bw - 8, bh);
    });
  }

  // ---------- main flow ----------
  startBtn.addEventListener("click", async () => {
    if (running) return;
    running = true;
    startBtn.disabled = true;
    downloadBtn.disabled = true;
    analyticsBtn.disabled = true;

    const track = trackEl.value;
    const role = roleEl.value.trim();
    const difficulty = diffEl.value;
    const language = langEl.value;
    const qcount = parseInt(qcountEl.value || "5", 10);

    statusLine.textContent = "Panel is assembling...";
    chairStatus.textContent = "Greeting the candidate...";
    subjStatus.textContent = "Preparing domain questions...";
    hrStatus.textContent = "Observing confidence & composure...";

    qBox.textContent = "Preparing interview room...";
    aBox.textContent = "";
    fBox.textContent = "";
    starsBox.innerHTML = "";
    scoreLine.textContent = "";
    progressLine.textContent = "";
    sessionScores = [];

    try {
      // Start session on backend
      const sidRes = await postJSON("/api/competitive_start_session", {
        track,
        role,
        difficulty,
        language,
        qcount
      });
      currentSessionId = sidRes.session_id;
    } catch (e) {
      console.error(e);
      alert("Could not start session.");
      running = false;
      startBtn.disabled = false;
      return;
    }

    statusLine.textContent = "Panel ready. Interview started.";
    chairStatus.textContent = "Chairperson is asking questions.";
    subjStatus.textContent = "Subject expert is listening carefully.";
    hrStatus.textContent = "HR is tracking confidence and clarity.";

    const langCode =
      language === "Hindi" ? "hi-IN" :
      language === "Hinglish" ? "en-IN" :
      "en-IN";

    for (let i = 0; i < qcount; i++) {
      try {
        progressLine.textContent = `Question ${i + 1} of ${qcount}`;

        qBox.textContent = "Panel is thinking of a suitable question...";
        await sleep(350);

        // GET question from backend
        const params = new URLSearchParams({
          track,
          role,
          difficulty,
          language
        });
        const qRes = await getJSON("/api/competitive_question?" + params.toString());
        const question = (qRes && qRes.question) || "Tell me about yourself.";
        qBox.textContent = question;

        // Speak question fully first
        await speak(question, langCode);

        // Now listen
        aBox.textContent = "Listening... answer clearly.";
        const ans = await listenOnce(i === 0 ? 15000 : 12000);
        aBox.textContent = ans || "(No answer detected)";

        // Evaluate
        fBox.textContent = "Panel is evaluating your answer...";
        const evalRes = await postJSON("/api/competitive_evaluate", {
          question,
          answer: ans,
          track,
          role,
          difficulty,
          language
        });

        const score = evalRes.score || 0;
        const notes = evalRes.notes || "";
        const conf = evalRes.confidence || "—";
        const comm = evalRes.communication || "—";

        sessionScores.push(score);
        showStars(Math.floor(score / 20) || 1);
        scoreLine.textContent =
          `Score: ${score}/100 | Confidence: ${conf} | Communication: ${comm}`;

        fBox.textContent =
          `Panel Feedback:\n\n${notes}`;

        // Speak feedback fully before moving on
        await speak(notes, langCode, 1.0);

        // Save attempt
        await postJSON("/api/competitive_save", {
          session_id: currentSessionId,
          question,
          transcription: ans,
          feedback: notes,
          score,
          stars: Math.floor(score / 20) || 1
        });

        drawMiniChart(sessionScores);

        // Small pause between questions
        await sleep(900 + i * 80);
      } catch (err) {
        console.error("Competitive loop error:", err);
        fBox.textContent = "Error during this question. Skipping to next.";
        await sleep(600);
      }
    }

    statusLine.textContent = "Interview finished. Download your report.";
    chairStatus.textContent = "Panel has finished the interview.";
    subjStatus.textContent = "Evaluation completed.";
    hrStatus.textContent = "Overall impression recorded.";
     
    fireConfetti();
    downloadBtn.disabled = false;
    analyticsBtn.disabled = false;
    startBtn.disabled = false;
    running = false;
    await speak("Session complete. You can download the session report now");
  });

  

  // ---------- download report ----------
  downloadBtn.addEventListener("click", () => {
    if (!currentSessionId) {
      alert("Please finish one interview first.");
      return;
    }
    window.open("/competitive_report/" + currentSessionId, "_blank");
  });

  // ---------- analytics ----------
  analyticsBtn.addEventListener("click", async () => {
    try {
      const data = await getJSON("/api/competitive_stats");
      const labels = data.labels || [];
      const scores = data.scores || [];

      analyticsModal.style.display = "flex";

      const ctx = fullChartCanvas.getContext("2d");
      // destroy previous chart instance if any
      if (window._cmpChart) {
        window._cmpChart.destroy();
      }
      window._cmpChart = new Chart(ctx, {
        type: "line",
        data: {
          labels,
          datasets: [{
            label: "Competitive Interview Scores",
            data: scores,
            fill: false
          }]
        },
        options: {
          responsive: true
        }
      });
    } catch (e) {
      console.error(e);
      alert("Could not load analytics yet.");
    }
  });

  // ---------- initial mini chart from overall stats ----------
  (async () => {
    try {
      const res = await getJSON("/api/competitive_stats");
      drawMiniChart(res.scores || []);
    } catch (e) {
      // ignore
    }
  })();
})();
