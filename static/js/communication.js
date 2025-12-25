(function () {
  const modeSel = document.getElementById("commMode");
  const typeSel = document.getElementById("commSessionType");
  const topicInput = document.getElementById("commTopic");
  const levelSel = document.getElementById("commLevel");

  const startBtn = document.getElementById("commStartBtn");
  const endBtn = document.getElementById("commEndBtn");
  const downloadBtn = document.getElementById("commDownloadBtn");

  const statusEl = document.getElementById("commStatus");
  const timerEl = document.getElementById("commTimer");
  const progressEl = document.getElementById("commProgress");
  const roundLabelEl = document.getElementById("commRoundLabel");

  const promptBox = document.getElementById("commPromptBox");
  const answerBox = document.getElementById("commAnswerBox");
  const feedbackBox = document.getElementById("commFeedbackBox");
  const scoreLineEl = document.getElementById("commScoreLine");

  const coachStatus = document.getElementById("commCoachStatus");
  const langStatus = document.getElementById("commLanguageStatus");
  const confStatus = document.getElementById("commConfidenceStatus");

  const confettiCanvas = document.getElementById("commConfettiCanvas");

  let currentSessionId = null;
  let currentMode = "speech";
  let running = false;
  let timerId = null;
  let timeLeft = 0;
  let timed = false;

  let attemptCount = 0;
  let scoreHistory = [];
  let history = []; // for conversation mode [{question, answer}]

  let miniChart = null;

  function postJSON(url, data) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data || {})
    }).then(r => r.json());
  }

  // ---- Speech functions ----
  function speak(text, onend) {
    if (!("speechSynthesis" in window)) {
      if (onend) onend();
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-IN";
    u.onend = () => {
      if (onend) onend();
    };
    window.speechSynthesis.speak(u);
  }

  function listen(timeout = 60000) {
    return new Promise(resolve => {
      const R = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!R) {
        resolve("");
        return;
      }
      const rec = new R();
      rec.lang = "en-IN";
      rec.interimResults = false;
      let done = false;

      const t = setTimeout(() => {
        if (!done) {
          done = true;
          rec.stop();
          resolve("");
        }
      }, timeout);

      rec.onresult = e => {
        if (done) return;
        done = true;
        clearTimeout(t);
        const text = e.results[0][0].transcript;
        resolve(text);
      };
      rec.onerror = () => {
        if (!done) {
          done = true;
          clearTimeout(t);
          resolve("");
        }
      };
      rec.start();
    });
  }

  // ---- Timer ----
  function updateTimerLabel() {
    if (!timed || timeLeft <= 0) {
      timerEl.textContent = "Open session";
      return;
    }
    const m = Math.floor(timeLeft / 60);
    const s = timeLeft % 60;
    timerEl.textContent = `Time left: ${m}:${String(s).padStart(2, "0")}`;
  }

  function startTimer(limitSeconds) {
    timed = limitSeconds > 0;
    timeLeft = limitSeconds;
    updateTimerLabel();
    if (!timed) return;

    if (timerId) clearInterval(timerId);
    timerId = setInterval(() => {
      timeLeft -= 1;
      if (timeLeft <= 0) {
        timeLeft = 0;
        updateTimerLabel();
        clearInterval(timerId);
        running = false;
        statusEl.textContent = "Time over. Session closed. You can download your report.";
      } else {
        updateTimerLabel();
      }
    }, 1000);
  }

  // ---- Chart ----
  function updateMiniChart() {
    const canvas = document.getElementById("commMiniChart");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const labels = scoreHistory.map((_, i) => `#${i + 1}`);

    if (!miniChart) {
      miniChart = new Chart(ctx, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Score",
              data: scoreHistory,
              tension: 0.3
            }
          ]
        },
        options: {
          responsive: false,
          scales: {
            y: {
              min: 0,
              max: 100
            }
          }
        }
      });
    } else {
      miniChart.data.labels = labels;
      miniChart.data.datasets[0].data = scoreHistory;
      miniChart.update();
    }
  }

  // ---- Confetti (simple) ----
  function triggerConfetti() {
    if (!confettiCanvas) return;
    // You can plug in a real confetti library later; for now we just flash
    confettiCanvas.style.display = "block";
    setTimeout(() => { confettiCanvas.style.display = "none"; }, 1200);
  }

  // ---- UI helpers ----
  function resetUIForNewSession() {
    attemptCount = 0;
    scoreHistory = [];
    history = [];
    roundLabelEl.textContent = "";
    progressEl.textContent = "";
    promptBox.textContent = "";
    answerBox.textContent = "";
    feedbackBox.textContent = "";
    scoreLineEl.textContent = "";
    if (miniChart) {
      miniChart.destroy();
      miniChart = null;
    }
  }

  function buildScoreLine(res) {
    const overall = res.overall_score || res.score || 0;
    const bits = [];
    if (res.confidence != null) bits.push(`Confidence: ${res.confidence}`);
    if (res.clarity != null) bits.push(`Clarity: ${res.clarity}`);
    if (res.fluency != null) bits.push(`Fluency: ${res.fluency}`);
    if (res.grammar != null) bits.push(`Grammar: ${res.grammar}`);
    if (res.vocabulary != null) bits.push(`Vocabulary: ${res.vocabulary}`);
    if (res.structure != null && currentMode === "speech") bits.push(`Structure: ${res.structure}`);
    if (res.logic != null && currentMode === "debate") bits.push(`Logic: ${res.logic}`);
    if (res.evidence != null && currentMode === "debate") bits.push(`Evidence: ${res.evidence}`);
    if (res.emotion != null && currentMode === "debate") bits.push(`Emotion: ${res.emotion}`);

    let line = `Overall: ${overall}/100`;
    if (bits.length) line += " · " + bits.join(" · ");
    return line;
  }

  // ---- Core flow per attempt ----
  async function runNextRound() {
    if (!running) return;
    if (timed && timeLeft <= 0) return;

    currentMode = modeSel.value;
    attemptCount += 1;
    roundLabelEl.textContent = `Attempt ${attemptCount}`;
    progressEl.textContent = `Mode: ${currentMode}`;

    coachStatus.textContent = "Preparing next prompt...";
    langStatus.textContent = "Analysing language...";
    confStatus.textContent = "Measuring confidence & clarity...";

    const topic = topicInput.value.trim();
    const level = levelSel.value;

    // 1) Get prompt/question/motion
    let promptText = "";
    let questionText = "";
    let side = "for";

    if (currentMode === "speech") {
      const res = await postJSON("/api/comm_speech_prompt", {
        topic_hint: topic,
        level
      });
      promptText = res.prompt || "Speak about yourself for one minute.";
      promptBox.textContent = promptText;

      statusEl.textContent = "Coach is reading the topic...";
      speak(promptText, async () => {
        // 2) Listen answer
        statusEl.textContent = "Listening to your speech...";
        answerBox.textContent = "Listening...";
        const ans = await listen();
        answerBox.textContent = ans || "(No answer captured)";
        statusEl.textContent = "Evaluating your speech...";

        // 3) Evaluate
        const evalRes = await postJSON("/api/comm_speech_evaluate", {
          session_id: currentSessionId,
          prompt: promptText,
          answer: ans || ""
        });

        const overall = evalRes.overall_score || evalRes.score || 0;
        scoreHistory.push(overall);
        updateMiniChart();

        const fb = (evalRes.overall_feedback || "") +
                   (evalRes.body_language_tips ? "\n\nBody language tips: " + evalRes.body_language_tips : "");
        feedbackBox.textContent = fb;

        const line = buildScoreLine(evalRes);
        scoreLineEl.textContent = line;

        coachStatus.textContent = "Feedback generated.";
        langStatus.textContent = "Language analysed.";
        confStatus.textContent = "Confidence evaluated.";

        if (overall >= 80) triggerConfetti();

        speak(evalRes.overall_feedback || "Good attempt.", () => {
          if (running && (!timed || timeLeft > 5)) {
            runNextRound();
          } else if (timed && timeLeft <= 5) {
            statusEl.textContent = "Session nearly over. You can end and download your report.";
          }
        });
      });

    } else if (currentMode === "conversation") {
      const qRes = await postJSON("/api/comm_conversation_question", {
        history,
        goal: topic
      });
      questionText = qRes.question || "Tell me something about yourself.";
      promptBox.textContent = questionText;

      statusEl.textContent = "Coach is asking the question...";
      speak(questionText, async () => {
        statusEl.textContent = "Listening to your response...";
        answerBox.textContent = "Listening...";
        const ans = await listen();
        answerBox.textContent = ans || "(No answer captured)";
        statusEl.textContent = "Evaluating your reply...";

        const evalRes = await postJSON("/api/comm_conversation_evaluate", {
          session_id: currentSessionId,
          question: questionText,
          answer: ans || "",
          history
        });

        history.push({ question: questionText, answer: ans || "" });

        const overall = evalRes.overall_score || evalRes.score || 0;
        scoreHistory.push(overall);
        updateMiniChart();

        feedbackBox.textContent = evalRes.overall_feedback || "";
        const line = buildScoreLine(evalRes);
        scoreLineEl.textContent = line;

        coachStatus.textContent = "Next question ready.";
        langStatus.textContent = "Language analysed.";
        confStatus.textContent = "Conversation style evaluated.";

        if (overall >= 80) triggerConfetti();

        speak(evalRes.overall_feedback || "Good attempt.", () => {
          if (running && (!timed || timeLeft > 5)) {
            runNextRound();
          } else if (timed && timeLeft <= 5) {
            statusEl.textContent = "Session nearly over. You can end and download your report.";
          }
        });
      });

    } else if (currentMode === "debate") {
      // debate side fixed "for" for now; can be UI later
      side = "for";
      const res = await postJSON("/api/comm_debate_prompt", {
        topic_hint: topic,
        side
      });
      const motion = res.motion || "This house believes that online education is better than traditional classroom teaching.";
      promptText = motion;
      questionText = motion;
      promptBox.textContent = motion;

      statusEl.textContent = "Panel is announcing the motion...";
      speak(motion, async () => {
        statusEl.textContent = "Present your argument...";
        answerBox.textContent = "Listening...";
        const ans = await listen();
        answerBox.textContent = ans || "(No argument captured)";
        statusEl.textContent = "Evaluating your argument...";

        const evalRes = await postJSON("/api/comm_debate_evaluate", {
          session_id: currentSessionId,
          motion,
          argument: ans || "",
          side
        });

        const overall = evalRes.overall_score || evalRes.score || 0;
        scoreHistory.push(overall);
        updateMiniChart();

        feedbackBox.textContent = evalRes.overall_feedback || "";
        const line = buildScoreLine(evalRes);
        scoreLineEl.textContent = line;

        coachStatus.textContent = "Debate round scored.";
        langStatus.textContent = "Language analysed.";
        confStatus.textContent = "Argument structure evaluated.";

        if (overall >= 80) triggerConfetti();

        speak(evalRes.overall_feedback || "Good attempt.", () => {
          if (running && (!timed || timeLeft > 5)) {
            runNextRound();
          } else if (timed && timeLeft <= 5) {
            statusEl.textContent = "Session nearly over. You can end and download your report.";
          }
        });
      });
    }
  }

  // ---- Button handlers ----
  startBtn.onclick = async () => {
    if (running) return;

    currentMode = modeSel.value;
    const sessionType = typeSel.value;
    const topic = topicInput.value.trim();

    resetUIForNewSession();

    statusEl.textContent = "Starting communication session...";
    coachStatus.textContent = "Connecting...";
    langStatus.textContent = "Initialising...";
    confStatus.textContent = "Getting ready...";

    const res = await postJSON("/api/comm_start_session", {
      mode: currentMode,
      session_type: sessionType,
      topic
    });

    currentSessionId = res.session_id;
    running = true;

    startTimer(res.time_limit || 0);
    statusEl.textContent = "Session started. AI is preparing your first round.";
    runNextRound();
  };

  endBtn.onclick = () => {
    if (!running) return;
    running = false;
    if (timerId) clearInterval(timerId);
    timerId = null;
    statusEl.textContent = "Session ended. You can now download your report.";
    coachStatus.textContent = "Session ended.";
    langStatus.textContent = "";
    confStatus.textContent = "";
  };

  downloadBtn.onclick = () => {
    if (!currentSessionId) {
      alert("Start a session first, then speak at least once to generate a report.");
      return;
    }
    window.location.href = `/communication_report/${currentSessionId}`;
  };

})();
