(() => {
  const fileInput = document.getElementById("resumeFile");
  const roleInput = document.getElementById("resumeRole");
  const modeSelect = document.getElementById("resumeMode");
  const analyzeBtn = document.getElementById("resumeAnalyzeBtn");
  const downloadBtn = document.getElementById("resumeDownloadBtn");
  const statusEl = document.getElementById("resumeStatus");

  const scoresCard = document.getElementById("resumeScoresCard");
  const summaryEl = document.getElementById("resumeSummary");
  const overallEl = document.getElementById("resOverallScore");
  const atsEl = document.getElementById("resATSScore");
  const clarityEl = document.getElementById("resClarityScore");
  const impactEl = document.getElementById("resImpactScore");
  const grammarEl = document.getElementById("resGrammarScore");

  const strengthsCard = document.getElementById("resumeStrengthsCard");
  const improvementsCard = document.getElementById("resumeImprovementsCard");
  const strengthsList = document.getElementById("resumeStrengthsList");
  const improvementsList = document.getElementById("resumeImprovementsList");

  let lastAnalysisId = null;
  let chart = null;

  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg;
  }

  function renderList(ul, items) {
    ul.innerHTML = "";
    (items || []).forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      ul.appendChild(li);
    });
  }

  function renderChart(overall, ats, clarity, impact, grammar) {
    const ctx = document.getElementById("resumeChart");
    if (!ctx) return;
    if (chart) {
      chart.destroy();
    }
    chart = new Chart(ctx, {
      type: "radar",
      data: {
        labels: ["Overall", "ATS", "Clarity", "Impact", "Grammar"],
        datasets: [
          {
            label: "Scores",
            data: [overall, ats, clarity, impact, grammar],
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
        },
        scales: {
          r: {
            suggestedMin: 0,
            suggestedMax: 100,
            ticks: { stepSize: 20 },
          },
        },
      },
    });
  }

  analyzeBtn?.addEventListener("click", async () => {
    const file = fileInput?.files?.[0];
    if (!file) {
      alert("Please upload a resume file first.");
      return;
    }

    setStatus("Uploading & analysing resume...");
    analyzeBtn.disabled = true;
    downloadBtn.disabled = true;

    const fd = new FormData();
    fd.append("resume", file);
    fd.append("role", roleInput.value || "");
    fd.append("mode", modeSelect.value || "general");

    try {
      const res = await fetch("/api/upload_resume", {
        method: "POST",
        body: fd,
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok || !data.success) {
        console.error("Resume error:", data);
        alert(data.message || "Resume analysis failed. Please try again.");
        setStatus("Analysis failed.");
        analyzeBtn.disabled = false;
        return;
      }

      const a = data.analysis;
      lastAnalysisId = data.analysis_id;

      // Update UI
      scoresCard.style.display = "block";
      overallEl.textContent = a.overall_score;
      atsEl.textContent = a.ats_score;
      clarityEl.textContent = a.clarity_score;
      impactEl.textContent = a.impact_score;
      grammarEl.textContent = a.grammar_score;
      summaryEl.textContent = a.summary || "";

      renderChart(
        a.overall_score,
        a.ats_score,
        a.clarity_score,
        a.impact_score,
        a.grammar_score
      );

      if ((a.strengths || []).length) {
        strengthsCard.style.display = "block";
        renderList(strengthsList, a.strengths);
      } else {
        strengthsCard.style.display = "none";
      }

      if ((a.improvements || []).length) {
        improvementsCard.style.display = "block";
        renderList(improvementsList, a.improvements);
      } else {
        improvementsCard.style.display = "none";
      }

      setStatus("Analysis complete. You can download the PDF report.");
      downloadBtn.disabled = false;
    } catch (err) {
      console.error(err);
      alert("Something went wrong while analysing the resume.");
      setStatus("Analysis error.");
    } finally {
      analyzeBtn.disabled = false;
    }
  });

  downloadBtn?.addEventListener("click", () => {
    if (!lastAnalysisId) {
      alert("Please analyse a resume first.");
      return;
    }
    window.location.href = `/resume_report/${lastAnalysisId}`;
  });
})();
