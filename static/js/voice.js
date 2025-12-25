
// voice.js - simple Web Speech API wrapper for recognition + TTS
const Speech = {
  synthSpeak: (text) => {
    if (!("speechSynthesis" in window)) return;
    const ut = new SpeechSynthesisUtterance(text);
    ut.lang = document.documentElement.lang || "en-US";
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(ut);
  },

  startRecognition: async ({onResult, lang="en-IN"}) => {
    if (!("webkitSpeechRecognition" in window) && !("SpeechRecognition" in window)) {
      alert("Speech Recognition not supported in this browser. Use Chrome.");
      return;
    }
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    const r = new Rec();
    r.lang = lang;
    r.interimResults = false;
    r.maxAlternatives = 1;
    r.onresult = (e) => {
      const text = e.results[0][0].transcript;
      onResult(text);
    };
    r.onerror = (e) => console.error("rec error", e);
    r.start();
    return r;
  }
};
