import { state } from './state.js';
import * as api from './api.js';
import * as ui from './ui.js';
import * as audio from './audio.js';

// DOM Elements specific to top-level app logic
const startButton = document.getElementById("startButton");
const voiceModeBtn = document.getElementById("voiceModeBtn");
const textModeBtn = document.getElementById("textModeBtn");
const voiceInput = document.getElementById("voiceInput");
const textInput = document.getElementById("textInput");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Processes the assistant's split message response.
 * Displays and speaks the empathetic acknowledgment first,
 * then pauses before delivering the follow-up clinical question.
 * 
 * @param {string} message - The raw message containing the && separator.
 */
async function handleAssistantResponses(message) {
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

async function sendTextMessage(message, emotion = null) {
  ui.addMessage(message, "user");
  ui.addTyping(false, "Analyzing...");

  try {
    const data = await api.sendChatText(state.sessionId, state.patientId, message, emotion);
    ui.removeTyping();
    await handleAssistantResponses(data.assistant_message);

    if (data.risk_flagged) {
      ui.showSafetyBanner();
    } else {
      ui.hideSafetyBanner();
    }
  } catch (err) {
    ui.removeTyping();
    ui.addMessage("I apologize, but I'm having trouble connecting right now.", "assistant");
    console.error("Error:", err);
  }
}

async function fetchPatients() {
  try {
    const patients = await api.fetchPatientsList();
    const dropdown = document.getElementById("patientDropdown");
    dropdown.innerHTML = '<option value="">-- Choose Profile --</option>';
    
    patients.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.patient_id;
      opt.textContent = `${p.name} (Age: ${p.age || 'N/A'})`;
      if (p.patient_id === state.patientId) {
        opt.selected = true;
      }
      dropdown.appendChild(opt);
    });
    toggleSelectButton();
  } catch (err) {
    console.error("Failed to load patient profiles:", err);
  }
}

function toggleSelectButton() {
  const dropdown = document.getElementById("patientDropdown");
  document.getElementById("selectProfileBtn").disabled = !dropdown.value;
}

async function showDashboard(pId) {
  try {
    const data = await api.loadDashboard(pId);
    
    document.getElementById("dashboardPatientName").textContent = data.patient.name;
    document.getElementById("dashboardPatientAge").textContent = data.patient.age ? `Age: ${data.patient.age}` : "Age: --";
    
    const list = document.getElementById("dashboardSessionsList");
    list.innerHTML = "";
    
    if (data.sessions && data.sessions.length > 0) {
      data.sessions.forEach(sess => {
        const d = new Date(sess.created_at).toLocaleString();
        const summary = sess.rolling_summary || "No summary available.";
        list.innerHTML += `
          <details class="group p-4 border border-ink bg-paper shadow-sm mb-3">
            <summary class="text-xs text-moss font-utility tracking-widest uppercase cursor-pointer select-none group-open:mb-2 flex justify-between">
              ${d}
              <span class="text-ink transition-transform group-open:rotate-180">▼</span>
            </summary>
            <div class="text-sm text-ink whitespace-pre-wrap mt-2 pl-2 border-l-2 border-clay">${summary}</div>
          </details>
        `;
      });
    } else {
      list.innerHTML = `<p class="text-clay text-sm italic">No previous sessions found.</p>`;
    }
    
    const domainsDiv = document.getElementById("dashboardDomains");
    if (domainsDiv && data.profile) {
      domainsDiv.innerHTML = `<h3 class="font-utility uppercase text-clay text-sm border-b border-ink/30 pb-2">Clinical Profile</h3>`;
      const renderDomain = (title, items) => {
        if (!items || items.length === 0) return;
        const html = `
          <details class="group mt-4 border-b border-clay/30 pb-2 cursor-pointer">
            <summary class="dashboard-label mb-1 select-none flex justify-between">
              ${title}
              <span class="text-ink text-xs transition-transform group-open:rotate-180">▼</span>
            </summary>
            <ul class="list-disc pl-5 text-sm dashboard-value space-y-1 mt-2 text-ink">
              ${items.map(i => `<li>${i}</li>`).join('')}
            </ul>
          </details>
        `;
        domainsDiv.innerHTML += html;
      };
      
      renderDomain("Emotional Themes", data.profile.emotional_themes);
      renderDomain("Thinking Patterns", data.profile.thinking_patterns);
      renderDomain("Stressors", data.profile.stressors);
      renderDomain("Protective Factors", data.profile.protective_factors);
      
      if (data.profile.risk_assessment) {
        domainsDiv.innerHTML += `
          <details class="group mt-4 border-b border-clay/30 pb-2 cursor-pointer">
            <summary class="dashboard-label mb-1 select-none flex justify-between">
              Risk Assessment
              <span class="text-ink text-xs transition-transform group-open:rotate-180">▼</span>
            </summary>
            <p class="text-sm dashboard-value mt-2 text-ink">${data.profile.risk_assessment}</p>
          </details>
        `;
      }
    }
    
    ui.switchScreen("dashboardScreen");
    
  } catch (err) {
    console.error("Dashboard error", err);
    alert("Could not load patient dashboard.");
  }
}

async function startActualSession(pId) {
  try {
    const data = await api.startSessionReq(pId);
    state.setSessionId(data.session_id);
    state.setPatientId(data.patient_id);

    ui.switchScreen("mainApp");

    state.sessionStartTime = Date.now();
    state.exchangeCount = 0;
    ui.updateSessionStats();
    if (state.sessionInterval) clearInterval(state.sessionInterval);
    state.sessionInterval = setInterval(ui.updateSessionStats, 60000);

    handleAssistantResponses(data.assistant_message);
  } catch (e) {
    console.error("Failed to start session:", e);
    alert("Failed to start session. Please try again.");
    location.reload();
  }
}

async function initializeSession(retryCount = 0) {
  try {
    await api.pingHealth();
    document.getElementById("loadingDots").style.display = "none";
    const wakeupText = document.getElementById("wakeupText");
    if (wakeupText) wakeupText.style.display = "none";

    startButton.disabled = false;
    startButton.textContent = "Start Consultation";
  } catch (error) {
    console.error(`Backend not ready (attempt ${retryCount + 1}):`, error);
    if (retryCount < 15) {
      const delay = Math.min(2000 * Math.pow(1.3, retryCount), 30000);
      setTimeout(() => initializeSession(retryCount + 1), delay);
    } else {
      document.getElementById("loadingDots").style.display = "none";
      startButton.disabled = false;
      startButton.textContent = "Retry Connection";
    }
  }
}

function bindEvents() {
  window.addEventListener("popstate", (event) => {
    if (event.state && event.state.screen) {
      ui.switchScreen(event.state.screen, false);
    } else {
      ui.switchScreen("loadingScreen", false);
    }
  });

  document.getElementById("patientDropdown").onchange = toggleSelectButton;

  document.getElementById("dashboardBackBtn").onclick = () => {
    ui.switchScreen("profileSelectionScreen");
    fetchPatients();
  };

  document.getElementById("dashboardResetBtn").onclick = () => {
    ui.showConfirm(
      "Reset Profile?",
      "Are you sure you want to reset this profile? All sessions, messages, and analysis will be permanently deleted. The patient record will remain.",
      () => {
        document.getElementById("dashboardSessionsList").innerHTML = `<p class="text-clay text-sm italic">No previous sessions found.</p>`;
        document.getElementById("dashboardDomains").innerHTML = `
          <h3 class="font-utility uppercase text-clay text-sm border-b border-ink/30 pb-2">Clinical Profile</h3>
          <p class="text-clay text-sm italic mt-4">Profile has been reset.</p>
        `;
        api.resetPatientProfile(state.patientId).catch(e => console.error("Error resetting profile:", e));
      }
    );
  };

  document.getElementById("dashboardDeleteBtn").onclick = () => {
    ui.showConfirm(
      "Delete Profile?",
      "Are you sure you want to completely delete this profile? This action is irreversible and all data will be erased.",
      () => {
        const idToDelete = state.patientId;
        state.setPatientId(null);
        ui.switchScreen("profileSelectionScreen");
        fetchPatients();
        api.deletePatientProfile(idToDelete).catch(e => console.error("Error deleting profile:", e));
      }
    );
  };

  document.getElementById("dashboardStartBtn").onclick = async () => {
    ui.switchScreen("loadingScreen");
    startButton.textContent = "Loading Session...";
    startButton.disabled = true;
    await startActualSession(state.patientId);
  };

  document.getElementById("selectProfileBtn").onclick = async () => {
    const dropdown = document.getElementById("patientDropdown");
    state.setPatientId(dropdown.value);
    await showDashboard(state.patientId);
  };

  document.getElementById("createProfileBtn").onclick = async () => {
    const nameInput = document.getElementById("newPatientName");
    const ageInput = document.getElementById("newPatientAge");
    const genderInput = document.getElementById("newPatientGender");
    const occupationInput = document.getElementById("newPatientOccupation");
    const concernInput = document.getElementById("newPatientConcern");
    
    const name = nameInput.value.trim();
    const age = ageInput.value;
    const gender = genderInput ? genderInput.value : null;
    const occupation = occupationInput ? occupationInput.value.trim() : null;

    if (!name || !age || !gender || !occupation) {
      alert("Please fill out all 4 required fields (Name, Age, Gender, and Occupation) to create a new profile.");
      return;
    }
    
    const parsedAge = parseInt(age);
    if (isNaN(parsedAge) || parsedAge < 5 || parsedAge > 100) {
      alert("Age must be between 5 and 100.");
      return;
    }

    try {
      const data = {
        name: name,
        age: parseInt(age),
        gender: gender,
        occupation: occupation,
        primary_concern: concernInput ? concernInput.value.trim() : null
      };
      const pData = await api.createPatientProfile(data);
      state.setPatientId(pData.patient_id);
      await showDashboard(state.patientId);
    } catch (e) {
      console.error("Failed to create profile:", e);
      alert("Failed to create patient profile. Please try again.");
    }
  };

  startButton.onclick = () => {
    if (startButton.textContent === "Start Consultation") {
      ui.switchScreen("profileSelectionScreen");
      fetchPatients();
    } else if (startButton.textContent === "Retry Connection") {
      startButton.textContent = "Initializing...";
      startButton.disabled = true;
      initializeSession();
    }
  };

  voiceModeBtn.onclick = () => {
    state.isVoiceMode = true;
    voiceModeBtn.classList.add("active");
    textModeBtn.classList.remove("active");
    voiceInput.style.display = "flex";
    textInput.style.display = "none";
  };

  textModeBtn.onclick = () => {
    state.isVoiceMode = false;
    textModeBtn.classList.add("active");
    voiceModeBtn.classList.remove("active");
    voiceInput.style.display = "none";
    textInput.style.display = "block";
    chatInput.focus();
  };

  sendBtn.onclick = () => {
    const message = chatInput.value.trim();
    if (message) {
      chatInput.value = "";
      sendTextMessage(message);
    }
  };

  chatInput.onkeypress = (e) => {
    if (e.key === 'Enter') sendBtn.onclick();
  };

  micBtn.onclick = () => {
    if (state.isAISpeaking) return;
    
    if (!state.isListening) {
      audio.startRecording(sendTextMessage);
    } else {
      audio.stopRecording();
    }
  };

  document.addEventListener('keydown', (e) => {
    if (e.code === 'Space' && !e.repeat && state.isVoiceMode && !state.isListening && !state.isAISpeaking && document.activeElement !== chatInput) {
      e.preventDefault();
      audio.startRecording(sendTextMessage);
    }
  });

  document.addEventListener('keyup', (e) => {
    if (e.code === 'Space' && state.isListening) {
      e.preventDefault();
      audio.stopRecording();
    }
  });

  document.getElementById("endSessionBtn").onclick = async () => {
    if (!state.sessionId) return;

    if (window.speechSynthesis.speaking) window.speechSynthesis.cancel();
    ui.setStatusText("Ending session...");

    try {
      await api.endSessionReq(state.sessionId, state.patientId);
      state.setSessionId(null);
      location.reload();
    } catch (err) {
      console.error("Failed to end session:", err);
      state.setSessionId(null);
      location.reload();
    }
  };
}

audio.loadVoices();
bindEvents();
window.onload = initializeSession;
