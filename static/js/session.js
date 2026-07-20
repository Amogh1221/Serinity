import { state } from './state.js';
import * as api from './api.js';
import * as ui from './ui.js';
import * as audio from './audio.js';
import * as profiles from './profiles.js';
import * as auth from './auth.js';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Processes the assistant's split message response.
 * Displays and speaks the empathetic acknowledgment first,
 * then pauses before delivering the follow-up clinical question.
 * 
 * @param {string} message - The raw message containing the && separator.
 */
export async function handleAssistantResponses(message) {
  if (!message) return;

  const parts = message.split("&&").map(p => p.trim()).filter(Boolean);

  ui.addMessage(parts[0], "assistant");
  await audio.speak(parts[0]);

  if (parts[1]) {
    ui.setStatusText("Assistant is thinking...");
    await sleep(500);

    ui.addTyping(false, "Thinking...");
    await sleep(500);
    ui.removeTyping();

    ui.addMessage(parts[1], "assistant");
    await audio.speak(parts[1]);
  }
}

/**
 * Ends the current active session, clears intervals, and returns the user to the dashboard.
 */
export async function endSession() {
  if (state.sessionInterval) {
    clearInterval(state.sessionInterval);
    state.sessionInterval = null;
  }
  state.setSessionId(null);
  state.setPatientId(null);
  ui.switchScreen("dashboard");
}

/**
 * Sends a text message to the backend and handles the response.
 * 
 * @param {string} message - The text message to send.
 * @param {string|null} emotion - Optional emotion tag.
 */
/**
 * Submits a new text message to the active session and waits for the AI response.
 * @param {string} text - The user's input message.
 * @returns {Promise<boolean>} True if successful, false otherwise.
 */
export async function recordMessage(text) {
  return await sendTextMessage(text);
}

export async function sendTextMessage(message, emotion = null) {
  ui.addMessage(message, "user");
  ui.addTyping(false, "Analyzing...");

  try {
    const data = await api.sendChatText(state.sessionId, state.patientId, message, emotion);
    ui.removeTyping();
    
    if (data.session_id && data.session_id !== state.sessionId) {
      state.setSessionId(data.session_id);
    }
    
    await handleAssistantResponses(data.assistant_message);

    // Only reset status text if audio is NOT enabled, 
    // otherwise audio.js will handle resetting it when speech finishes.
    if (!state.isAudioOutputEnabled) {
      ui.setStatusText(state.isVoiceMode ? "Hold Space to speak" : "Type your message");
    }

    if (data.risk_flagged) {
      ui.showSafetyBanner();
    } else {
      ui.hideSafetyBanner();
    }
  } catch (err) {
    ui.removeTyping();
    if (err.message && (err.message.includes("Tokens Exhausted") || err.message.includes("429"))) {
      ui.showAlert("Tokens Exhausted", "Your LLM provider tokens have been exhausted. Please wait or upgrade your plan.");
    } else {
      ui.addMessage("I apologize, but I'm having trouble connecting right now.", "assistant");
    }
    console.error("Error:", err);
  }
}

/**
 * Starts a new session for the given patient ID.
 * Transitions UI to main app and starts session timers.
 * 
 * @param {string} pId - The patient ID to start the session for.
 */
/**
 * Starts a new chat session with the AI for the currently selected patient.
 * Emits an initial context message to the backend.
 */
export async function startActualSession(pId) {
  try {
    const data = await api.startSessionReq(pId);
    state.setSessionId(data.session_id);
    state.setPatientId(data.patient_id);

    ui.switchScreen("mainApp");
    document.getElementById("chat").innerHTML = "";

    state.sessionStartTime = Date.now();
    state.exchangeCount = 0;
    ui.updateSessionStats();
    if (state.sessionInterval) clearInterval(state.sessionInterval);
    state.sessionInterval = setInterval(ui.updateSessionStats, 60000);

    handleAssistantResponses(data.assistant_message);
  } catch (e) {
    console.error("Failed to start session:", e);
    ui.showAlert("Session Failed", e.message || "Failed to start session. Please try again.");
    ui.switchScreen("dashboardScreen");
    const startButton = document.getElementById("dashboardStartBtn");
    if (startButton) {
      startButton.textContent = "START CONSULTATION";
      startButton.disabled = false;
    }
  }
}

/**
 * Resumes an existing active session.
 * 
 * @param {string} sessionId - The ID of the session to resume.
 */
export async function continueActualSession(sessionId) {
  try {
    state.setSessionId(sessionId);
    ui.switchScreen("mainApp");
    
    document.getElementById("chat").innerHTML = "";
    
    const data = await api.getSessionMessages(sessionId);
    if (data.messages) {
      data.messages.forEach(msg => {
        if (msg.role !== "system") {
          if (msg.role === 'assistant') {
            const parts = msg.content.split("&&").map(p => p.trim()).filter(Boolean);
            parts.forEach(part => ui.addMessage(part, 'assistant'));
          } else {
            ui.addMessage(msg.content, msg.role);
          }
        }
      });
    }

    state.sessionStartTime = Date.now(); 
    state.exchangeCount = Math.floor((data.messages || []).length / 2);
    ui.updateSessionStats();
    if (state.sessionInterval) clearInterval(state.sessionInterval);
    state.sessionInterval = setInterval(ui.updateSessionStats, 60000);
  } catch (e) {
    console.error("Failed to continue session:", e);
    alert("Failed to continue session. Please try again.");
    location.reload();
  }
}

/**
 * Pings the backend to check health and initializes routing based on URL path.
 * Retries with exponential backoff if backend is not ready.
 * 
 * @param {number} retryCount - Number of initialization retries so far.
 */
export async function initializeSession(retryCount = 0) {
  const startButton = document.getElementById("startButton");
  const wakeupText = document.getElementById("wakeupText");
  
  if (retryCount === 0) {
    if (wakeupText) wakeupText.textContent = "Waking up backend (this may take up to a minute)...";
    if (startButton) {
      startButton.disabled = false;
      startButton.textContent = "Start Consultation";
    }
  }
  try {
    await api.pingHealth();
    document.getElementById("loadingDots").style.display = "none";
    if (wakeupText) wakeupText.style.display = "none";

    if (startButton) {
      startButton.disabled = false;
      startButton.textContent = "Start Consultation";
    }

    // Handle hash routing from OAuth or direct links
    if (window.location.hash) {
      const hash = window.location.hash.substring(1);
      let newPath = "/";
      if (hash === "dashboardScreen") newPath = "/dashboard";
      else if (hash === "mainApp") newPath = "/session";
      
      if (newPath !== "/") {
        window.history.replaceState(null, "", newPath);
      }
    }

    // Handle deep linking / routing on load
    const path = window.location.pathname;
    if (path === "/dashboard") {
      // Always re-fetch on refresh — state.patientId is in-memory and lost on reload
      await profiles.fetchPatients();
    } else if (path === "/session") {
      if (!state.sessionId) {
        window.location.href = "/";
      } else {
        ui.switchScreen("mainApp", false);
      }
    } else {
      // Allow user to click the start button
    }
  } catch (error) {
    console.error(`Backend not ready (attempt ${retryCount + 1}):`, error);
    if (retryCount < 15) {
      const delay = Math.min(2000 * Math.pow(1.3, retryCount), 30000);
      setTimeout(() => initializeSession(retryCount + 1), delay);
    } else {
      document.getElementById("loadingDots").style.display = "none";
      if (startButton) {
        startButton.disabled = false;
        startButton.textContent = "Retry Connection";
      }
    }
  }
}

/**
 * Renews the browser's TTS user-activation token synchronously.
 * Must be called directly inside an onclick or keydown/keyup handler.
 */
export function primeTTS() {
  if (state.isAudioOutputEnabled && window.speechSynthesis) {
    const primer = new SpeechSynthesisUtterance(' ');
    primer.volume = 0;
    primer.rate = 10;
    window.speechSynthesis.speak(primer);
  }
}

/**
 * Toggle audio output on/off and update the button visuals.
 * 
 * @param {boolean} enabled - Whether audio should be enabled.
 */
export function setAudioOutput(enabled) {
  state.isAudioOutputEnabled = enabled;
  
  const mobileToggle = document.getElementById("audioOutputToggleMobile");
  const track = document.getElementById("audioToggleTrack");
  const dot = document.getElementById("audioToggleDot");
  const iconMobile = document.getElementById("audioToggleIconMobile");
  
  const desktopToggle = document.getElementById("audioOutputToggleDesktop");
  const labelDesktop = document.getElementById("audioToggleLabelDesktop");
  
  if (mobileToggle && mobileToggle.checked !== enabled) {
    mobileToggle.checked = enabled;
  }
  
  if (enabled) {
    // Prime the TTS engine with a silent utterance linked to this click gesture.
    if (window.speechSynthesis) {
      window.speechSynthesis.getVoices();
      const primer = new SpeechSynthesisUtterance(' ');
      primer.volume = 0;
      primer.rate = 10;
      window.speechSynthesis.speak(primer);
    }
    
    // Update mobile UI
    if (track) { track.classList.remove("bg-ink/30"); track.classList.add("bg-moss"); }
    if (dot) { dot.classList.add("translate-x-4"); }
    if (iconMobile) { iconMobile.classList.remove("text-ink/50"); iconMobile.classList.add("text-moss"); }
    
    // Update desktop UI
    if (desktopToggle) {
      desktopToggle.classList.add("bg-moss", "border-moss", "text-paper");
      desktopToggle.classList.remove("text-ink", "border-ink");
    }
    if (labelDesktop) labelDesktop.textContent = "Audio On";
    
  } else {
    if (window.speechSynthesis && window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
    }
    state.isAISpeaking = false;
    
    // Update mobile UI
    if (track) { track.classList.remove("bg-moss"); track.classList.add("bg-ink/30"); }
    if (dot) { dot.classList.remove("translate-x-4"); }
    if (iconMobile) { iconMobile.classList.remove("text-moss"); iconMobile.classList.add("text-ink/50"); }
    
    // Update desktop UI
    if (desktopToggle) {
      desktopToggle.classList.remove("bg-moss", "border-moss", "text-paper");
      desktopToggle.classList.add("text-ink", "border-ink");
    }
    if (labelDesktop) labelDesktop.textContent = "Audio Off";
  }
}
