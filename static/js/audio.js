import { state } from './state.js';
import { setStatusText, toggleMicButtonVisuals, addTyping, removeTyping } from './ui.js';
import { transcribeAudio } from './api.js';

let systemVoices = [];
let mediaRecorder = null;
let audioChunks = [];

// Keep a global reference so Chrome doesn't garbage-collect the utterance mid-speech
let currentUtterance = null;

export function loadVoices() {
  const voiceSelect = document.getElementById("voiceSelect");
  if (!voiceSelect) return;
  
  systemVoices = window.speechSynthesis.getVoices();
  voiceSelect.innerHTML = "";

  // Add a reliable default option that doesn't force a specific voice object
  const defaultOption = document.createElement("option");
  defaultOption.value = "";
  defaultOption.textContent = "Default OS Voice (Reliable)";
  defaultOption.selected = true;
  voiceSelect.appendChild(defaultOption);

  const englishVoices = systemVoices.filter(v => v.lang.includes('en'));

  englishVoices.forEach(voice => {
    const option = document.createElement("option");
    option.value = voice.name;
    option.textContent = `${voice.name} (${voice.localService ? 'Local' : 'Network'})`;
    voiceSelect.appendChild(option);
  });
}

if (window.speechSynthesis.onvoiceschanged !== undefined) {
  window.speechSynthesis.onvoiceschanged = loadVoices;
}

/**
 * Speak text using the browser's SpeechSynthesis API.
 * Only speaks if audio output is enabled (state.isAudioOutputEnabled).
 * This is independent of input mode (text vs voice).
 */
export function speak(text) {
  return new Promise((resolve) => {
    if (!state.isAudioOutputEnabled) {
      resolve();
      return;
    }

    // Ensure voices are loaded
    if (systemVoices.length === 0) {
      systemVoices = window.speechSynthesis.getVoices();
    }

    // Strip markdown symbols before speaking
    const cleanText = text.replace(/[*_~`#]/g, '').replace(/\[.*?\]/g, '').replace(/\(.*?\)/g, '').trim();
    if (!cleanText) {
      console.warn("TTS Skipped: Text was empty after stripping markdown");
      resolve();
      return;
    }

    setStatusText("Assistant is responding...");

    // Keep it simple — exactly like the working test page.
    // No cancel(), no setTimeout. Just create and speak.
    currentUtterance = new SpeechSynthesisUtterance(cleanText);

    // Select voice
    const voiceSelect = document.getElementById("voiceSelect");
    const selectedVoiceName = voiceSelect ? voiceSelect.value : "";
    
    // Only set the voice if the user explicitly selected one of the specific named voices.
    // Otherwise, leave it undefined so the browser uses its ultra-reliable native default.
    if (selectedVoiceName !== "") {
      const preferredVoice = systemVoices.find(v => v.name === selectedVoiceName);
      if (preferredVoice) {
        currentUtterance.voice = preferredVoice;
      }
    }
    currentUtterance.rate = 1.0;
    currentUtterance.pitch = 1.0;
    currentUtterance.volume = 1.0;

    currentUtterance.onstart = () => {
      state.isAISpeaking = true;
      setStatusText("Assistant is speaking... (Audio Started)");
    };

    currentUtterance.onend = () => {
      state.isAISpeaking = false;
      setStatusText(state.isVoiceMode ? "Hold Space to speak" : "Type your message");
      resolve();
    };

    currentUtterance.onerror = (e) => {
      console.error("TTS error:", e.error);
      state.isAISpeaking = false;
      setStatusText(`TTS Error: ${e.error}`);
      setTimeout(() => {
        setStatusText(state.isVoiceMode ? "Hold Space to speak" : "Type your message");
      }, 3000);
      resolve();
    };

    setStatusText("Attempting to speak...");
    
    // Fallback timeout in case onstart/onend never fire
    setTimeout(() => {
      if (state.isAISpeaking) {
         // It started, but maybe stuck?
      } else {
         setStatusText("Audio failed to start (Timeout)");
         setTimeout(() => {
            setStatusText(state.isVoiceMode ? "Hold Space to speak" : "Type your message");
         }, 3000);
         resolve();
      }
    }, 4000);

    window.speechSynthesis.speak(currentUtterance);
  });
}

/**
 * Starts recording the user's voice via MediaRecorder.
 * Called only via spacebar hold.
 */
export async function startRecording(onTranscriptionDone) {
  if (state.isRecordingPending || state.isListening) return;
  state.isRecordingPending = true;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    
    // If user released space before mic permission was granted
    if (!state.isRecordingPending) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }

    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      // Stop all mic tracks immediately
      stream.getTracks().forEach(track => track.stop());

      const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
      
      if (audioBlob.size < 100) {
        setStatusText("Recording was too short. Hold Space longer.");
        return;
      }

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
        setStatusText("Hold Space to try again");
      }
    };

    mediaRecorder.start();
    state.isListening = true;
    state.isRecordingPending = false;
    toggleMicButtonVisuals(true);
    setStatusText("Listening... (release Space to stop)");
  } catch (err) {
    console.error("Microphone access denied", err);
    setStatusText("Microphone access denied");
    state.isRecordingPending = false;
  }
}

export function stopRecording() {
  state.isRecordingPending = false;
  
  if (mediaRecorder && state.isListening) {
    try {
      if (mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
      }
    } catch(e) {
      console.error("Error stopping media recorder", e);
    }
    
    state.isListening = false;
    toggleMicButtonVisuals(false);
    setStatusText("Processing...");
  } else {
    state.isListening = false;
    toggleMicButtonVisuals(false);
  }
}
