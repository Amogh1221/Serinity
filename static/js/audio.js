import { state } from './state.js';
import { setStatusText, toggleMicButtonVisuals, addTyping, removeTyping } from './ui.js';
import { transcribeAudio } from './api.js';

let systemVoices = [];
let mediaRecorder = null;
let audioChunks = [];

export function loadVoices() {
  const voiceSelect = document.getElementById("voiceSelect");
  if (!voiceSelect) return;
  
  systemVoices = window.speechSynthesis.getVoices();
  voiceSelect.innerHTML = "";

  const englishVoices = systemVoices.filter(v => v.lang.includes('en'));

  englishVoices.forEach(voice => {
    const option = document.createElement("option");
    option.value = voice.name;
    option.textContent = `${voice.name} (${voice.lang})`;

    if (voice.name.includes("Google US English") || voice.name.includes("Microsoft Zira") || voice.name.includes("Samantha")) {
      option.selected = true;
    }
    voiceSelect.appendChild(option);
  });
}

if (window.speechSynthesis.onvoiceschanged !== undefined) {
  window.speechSynthesis.onvoiceschanged = loadVoices;
}

export function speak(text) {
  return new Promise((resolve) => {
    if (!state.isVoiceMode) {
      resolve();
      return;
    }

    if (window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
    }

    setStatusText("Assistant is responding...");

    const utterance = new SpeechSynthesisUtterance(text);
    const voiceSelect = document.getElementById("voiceSelect");
    const selectedVoiceName = voiceSelect ? voiceSelect.value : "";
    let preferredVoice = systemVoices.find(v => v.name === selectedVoiceName);

    if (!preferredVoice) {
      preferredVoice = systemVoices.find(v => v.lang.includes('en') && (v.name.includes('Female') || v.name.includes('Zira') || v.name.includes('Samantha'))) || systemVoices.find(v => v.lang.includes('en'));
    }

    if (preferredVoice) utterance.voice = preferredVoice;
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    utterance.onstart = () => {
      state.isAISpeaking = true;
      setStatusText("Assistant is speaking...");
    };

    utterance.onend = () => {
      state.isAISpeaking = false;
      setStatusText("Tap the microphone or hold Space to speak");
      resolve();
    };

    utterance.onerror = (e) => {
      state.isAISpeaking = false;
      console.error("Browser TTS Error:", e);
      setStatusText("Tap the microphone or hold Space to speak");
      resolve();
    };

    window.speechSynthesis.speak(utterance);

    // Safety fallback
    const wordCount = text.split(/\s+/).length;
    const timeoutMs = Math.max(3000, wordCount * 600);
    setTimeout(() => {
      state.isAISpeaking = false;
      resolve();
    }, timeoutMs);
  });
}

/**
 * Starts recording the user's voice via MediaRecorder.
 * When recording is stopped, the audio blob is sent to the backend for transcription.
 * 
 * @param {Function} onTranscriptionDone - Callback fired with the transcribed text and extracted emotion.
 */
export async function startRecording(onTranscriptionDone) {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      
      setStatusText("Transcribing your voice...");
      addTyping(true, "Transcribing...");

      try {
        const data = await transcribeAudio(audioBlob);
        removeTyping();
        
        if (data.text && data.text.trim() !== "") {
          onTranscriptionDone(data.text, data.emotion);
        } else {
          setStatusText("I didn't catch that. Try again?");
        }
      } catch (e) {
        removeTyping();
        console.error("Transcription failed", e);
        setStatusText("Tap to try again");
      }
    };

    mediaRecorder.start();
    state.isListening = true;
    toggleMicButtonVisuals(true);
    setStatusText("Listening... (tap again to stop)");
  } catch (err) {
    console.error("Microphone access denied", err);
    setStatusText("Microphone access denied");
  }
}

export function stopRecording() {
  if (mediaRecorder && state.isListening) {
    mediaRecorder.stop();
    state.isListening = false;
    toggleMicButtonVisuals(false);
    setStatusText("Processing...");
    mediaRecorder.stream.getTracks().forEach(track => track.stop());
  }
}
