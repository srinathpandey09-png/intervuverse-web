// static/js/viva.js
(async function(){
  const startBtn = document.getElementById('startViva');
  const downloadReport = document.getElementById('downloadVivaReport');
  const qEl = document.getElementById('vivaQuestion');
  const aEl = document.getElementById('vivaAnswer');
  const fEl = document.getElementById('vivaFeedback');
  const starsEl = document.getElementById('vivaStars');
  const confettiCanvas = document.getElementById('confetti-canvas');
  const ctx = confettiCanvas.getContext('2d');

  function resize(){ 
    confettiCanvas.width = window.innerWidth; 
    confettiCanvas.height = window.innerHeight; 
  }
  resize(); 
  window.addEventListener('resize', resize);

  function sleep(ms){ return new Promise(r=>setTimeout(r, ms)); }

  // ✅✅✅ FIXED SPEAK — RETURNS PROMISE WHEN VOICE ENDS
  function speak(text){
    return new Promise(resolve => {
      if(!('speechSynthesis' in window)){
        resolve();
        return;
      }
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'en-IN';
      u.onend = resolve;   // ✅ tells when speaking is finished
      u.onerror = resolve;
      window.speechSynthesis.speak(u);
    });
  }

  async function postJSON(url, payload){
    const res = await fetch(url, {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    return res.json();
  }

  function showStars(n){
    starsEl.innerHTML='';
    for(let i=1;i<=5;i++){
      const s=document.createElement('span');
      s.className='star'+(i<=n ? ' on':'');
      s.innerText='★';
      starsEl.appendChild(s);
    }
  }

  async function generateQuestion(board, cls, subject, topic, strictness){
    const res = await postJSON('/api/viva_question', {
      board, class: cls, subject, topic, strictness
    });
    return (res.question || '');
  }

  async function evaluate(question, transcription){
    return await postJSON('/api/viva_evaluate', {question, transcription});
  }

  function listenOnce(timeoutMs=9000){
    return new Promise((resolve) => {
      const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
      if(!Rec) return resolve('');
      const r = new Rec();
      r.lang='en-IN';
      r.interimResults=false;
      r.maxAlternatives=1;

      let finished=false;
      const to = setTimeout(()=>{
        if(!finished){
          finished=true;
          try{ r.stop(); }catch(e){}
          resolve('');
        }
      }, timeoutMs);

      r.onresult = (e)=>{
        if(finished) return;
        finished=true;
        clearTimeout(to);
        resolve(e.results[0][0].transcript||'');
      };
      r.onerror = ()=>{
        if(finished) return;
        finished=true;
        clearTimeout(to);
        resolve('');
      };
      r.onend = ()=>{
        if(!finished){
          finished=true;
          clearTimeout(to);
          resolve('');
        }
      };
      try{ r.start(); }catch(e){
        clearTimeout(to);
        resolve('');
      }
    });
  }

  function fireConfetti(){
    const pieces=[];
    for(let i=0;i<120;i++){
      pieces.push({
        x:Math.random()*confettiCanvas.width,
        y:-50-Math.random()*200,
        r:6+Math.random()*10,
        c:['#ffd166','#ff7aa2','#9be7ff','#b5ffb2'][Math.floor(Math.random()*4)],
        vx:-1+Math.random()*2,
        vy:2+Math.random()*4,
        rot:Math.random()*10
      });
    }
    let t=0;
    function draw(){
      t++;
      ctx.clearRect(0,0,confettiCanvas.width, confettiCanvas.height);
      for(const p of pieces){
        p.x+=p.vx; 
        p.y+=p.vy; 
        p.vy+=0.08; 
        p.rot+=0.1;
        ctx.save();
        ctx.translate(p.x,p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle=p.c;
        ctx.fillRect(-p.r/2,-p.r/2,p.r,p.r*1.8);
        ctx.restore();
      }
      if(t<240) requestAnimationFrame(draw);
      else ctx.clearRect(0,0,confettiCanvas.width, confettiCanvas.height);
    }
    requestAnimationFrame(draw);
  }

  startBtn.addEventListener('click', async ()=>{
    startBtn.disabled=true;
    downloadReport.style.display='none';
    qEl.innerText='Preparing viva session...';
    aEl.innerText='...';
    fEl.innerText='...';
    starsEl.innerHTML='';

    const board = document.getElementById('board').value;
    const cls = document.getElementById('class').value;
    const subject = document.getElementById('subject').value || '';
    const topic = document.getElementById('topic').value || '';
    const strictness = 'strict';

    const sidRes = await postJSON('/api/viva_start_session', {
      board, class: cls, subject, topic
    });
    const sessionId = sidRes.session_id;

    const total = 5;

    for(let i=0;i<total;i++){
      let question = '';
      if(i===0){
        question = 'Please state your name and class.';
      } else {
        qEl.innerText = 'Requesting next question...';
        await sleep(500);
        question = await generateQuestion(board, cls, subject, topic, strictness);
      }

      qEl.innerText = question;

      // ✅✅✅ NOW LISTEN STARTS ONLY AFTER SPEAKING FINISHES
      await speak(question);

      aEl.innerText = 'Listening...';
      const transcription = await listenOnce(i===0?11000:9000);
      aEl.innerText = transcription || '(no answer detected)';

      fEl.innerText = 'Evaluating...';
      let evalRes = await evaluate(question, transcription);
      if(!evalRes || typeof evalRes.score==='undefined'){
        evalRes = {
          score: Math.min(85, Math.max(10, (transcription.split(' ').length||0)*8 )),
          notes: 'Keep going!'
        };
      }

      const stars = evalRes.stars || Math.max(1, Math.min(5, Math.floor(evalRes.score/20)));
      showStars(stars);
      fEl.innerText = `Score: ${evalRes.score} — ${evalRes.notes}`;

      await postJSON('/api/viva_save', {
        session_id: sessionId,
        question,
        transcription,
        feedback: evalRes.notes,
        score: evalRes.score,
        stars
      });

      await sleep(900+(i*100));
    }
fireConfetti();

    // ---------- BUTTONS ----------
  startBtn.addEventListener("click", async () => {
    await runAutoSession(6);
  });

  downloadReport.addEventListener("click", () => {
    if (!currentSessionId) return alert("Session not started!");
    window.open(`/viva_session_report/${currentSessionId}`, "_blank");
  });

  });

})();
