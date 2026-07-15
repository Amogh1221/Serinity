import { state } from './state.js';
import * as api from './api.js';
import * as ui from './ui.js';
import * as audio from './audio.js';
import * as profiles from './profiles.js';
import * as session from './session.js';

// DOM Elements specific to top-level app logic
const startButton = document.getElementById("startButton");
const voiceModeBtn = document.getElementById("voiceModeBtn");
const textModeBtn = document.getElementById("textModeBtn");
const voiceInput = document.getElementById("voiceInput");
const textInput = document.getElementById("textInput");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const micBtn = document.getElementById("micBtn");

/**
 * Binds all global events to the DOM (button clicks, form submits, keypresses).
 */
function bindEvents() {
  // Handle browser back/forward buttons
  window.addEventListener("popstate", (event) => {
    if (event.state && event.state.screen) {
      ui.switchScreen(event.state.screen, false);
    } else {
      const path = window.location.pathname;
      if (path === "/profiles") {
        profiles.fetchPatients();
        ui.switchScreen("profileSelectionScreen", false);
      } else if (path === "/dashboard" || path === "/session") {
        if (!state.patientId) {
          profiles.fetchPatients();
          ui.switchScreen("profileSelectionScreen", false);
        } else {
          ui.switchScreen(path === "/dashboard" ? "dashboardScreen" : "mainApp", false);
        }
      } else {
        ui.switchScreen("loadingScreen", false);
      }
    }
  });

  // --- Profiles & Dashboard Events ---

  const patientDropdown = document.getElementById("patientDropdown");
  if (patientDropdown) patientDropdown.onchange = profiles.toggleSelectButton;

  const dashboardBackBtn = document.getElementById("dashboardBackBtn");
  if (dashboardBackBtn) {
    dashboardBackBtn.onclick = () => {
      ui.switchScreen("profileSelectionScreen");
      profiles.fetchPatients();
    };
  }

  const dashboardResetBtn = document.getElementById("dashboardResetBtn");
  if (dashboardResetBtn) {
    dashboardResetBtn.onclick = () => {
      ui.showConfirm(
        "Reset Profile?",
        "Are you sure you want to reset this profile? All sessions, messages, and analysis will be permanently deleted. The patient record will remain.",
        async () => {
          try {
            await api.resetPatientProfile(state.patientId);
          } catch (e) {
            console.error("Error resetting profile:", e);
          }
          document.getElementById("dashboardSessionsList").innerHTML = `<p class="text-clay text-sm italic">No previous sessions found.</p>`;
          document.getElementById("dashboardDomains").innerHTML = `
            <h3 class="font-utility uppercase text-clay text-sm border-b border-ink/30 pb-2">Clinical Profile</h3>
            <p class="text-clay text-sm italic mt-4">Profile has been reset.</p>
          `;
        }
      );
    };
  }

  const dashboardDeleteBtn = document.getElementById("dashboardDeleteBtn");
  if (dashboardDeleteBtn) {
    dashboardDeleteBtn.onclick = () => {
      ui.showConfirm(
        "Delete Profile?",
        "Are you sure you want to completely delete this profile? This action is irreversible and all data will be erased.",
        async () => {
          const idToDelete = state.patientId;
          state.setPatientId(null);
          try {
            await api.deletePatientProfile(idToDelete);
          } catch (e) {
            console.error("Error deleting profile:", e);
          }
          ui.switchScreen("profileSelectionScreen");
          profiles.fetchPatients();
        }
      );
    };
  }

  const dashboardStartBtn = document.getElementById("dashboardStartBtn");
  if (dashboardStartBtn) {
    dashboardStartBtn.onclick = async () => {
      ui.switchScreen("loadingScreen", false);
      startButton.textContent = "Checking Session...";
      startButton.disabled = true;

      try {
        const active = await api.getActiveSession(state.patientId);
        if (active && active.session_id) {
          ui.switchScreen("dashboardScreen");
          const modal = document.getElementById("continueSessionModal");
          modal.style.display = "flex";

          document.getElementById("continueSessionBtn").onclick = async () => {
            modal.style.display = "none";
            ui.switchScreen("loadingScreen", false);
            startButton.textContent = "Resuming Session...";
            await session.continueActualSession(active.session_id);
          };

          document.getElementById("endAndStartNewBtn").onclick = async () => {
            modal.style.display = "none";
            ui.switchScreen("loadingScreen", false);
            startButton.textContent = "Loading Session...";
            state.setSessionId(null);
            await api.endSessionReq(active.session_id, state.patientId);
            await session.startActualSession(state.patientId);
          };
        } else {
          startButton.textContent = "Loading Session...";
          await session.startActualSession(state.patientId);
        }
      } catch (e) {
        console.error(e);
        startButton.textContent = "Loading Session...";
        await session.startActualSession(state.patientId);
      }
    };
  }

  const selectProfileBtn = document.getElementById("selectProfileBtn");
  if (selectProfileBtn) {
    selectProfileBtn.onclick = async () => {
      state.setPatientId(patientDropdown.value);
      await profiles.showDashboard(state.patientId);
    };
  }

  const createProfileBtn = document.getElementById("createProfileBtn");
  if (createProfileBtn) {
    createProfileBtn.onclick = async () => {
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
        await profiles.showDashboard(state.patientId);
      } catch (e) {
        console.error("Failed to create profile:", e);
        alert("Failed to create patient profile. Please try again.");
      }
    };
  }

  if (startButton) {
    startButton.onclick = () => {
      if (startButton.textContent === "Start Consultation") {
        ui.switchScreen("profileSelectionScreen");
        profiles.fetchPatients();
      } else if (startButton.textContent === "Retry Connection") {
        startButton.textContent = "Initializing...";
        startButton.disabled = true;
        session.initializeSession();
      }
    };
  }

  // --- Session UI Events (Toggle Text/Voice, etc) ---

  if (voiceModeBtn) {
    voiceModeBtn.onclick = (e) => {
      state.isVoiceMode = true;
      voiceModeBtn.classList.add("active");
      textModeBtn.classList.remove("active");
      voiceInput.style.display = "flex";
      textInput.style.display = "none";
      
      // Auto-enable audio output when switching to voice mode
      if (!state.isAudioOutputEnabled) {
        session.setAudioOutput(true);
      }
      e.currentTarget.blur();
    };
  }

  if (textModeBtn) {
    textModeBtn.onclick = (e) => {
      state.isVoiceMode = false;
      textModeBtn.classList.add("active");
      voiceModeBtn.classList.remove("active");
      voiceInput.style.display = "none";
      textInput.style.display = "block";
      chatInput.focus();
    };
  }

  const voiceSelect = document.getElementById("voiceSelect");
  if (voiceSelect) {
    voiceSelect.addEventListener('change', (e) => e.target.blur());
  }

  const audioOutputToggleMobile = document.getElementById("audioOutputToggleMobile");
  if (audioOutputToggleMobile) {
    audioOutputToggleMobile.addEventListener('change', (e) => {
      session.setAudioOutput(e.target.checked);
      e.target.blur();
    });
  }

  const audioOutputToggleDesktop = document.getElementById("audioOutputToggleDesktop");
  if (audioOutputToggleDesktop) {
    audioOutputToggleDesktop.addEventListener('click', (e) => {
      session.setAudioOutput(!state.isAudioOutputEnabled);
      e.currentTarget.blur();
    });
  }

  if (sendBtn) {
    sendBtn.onclick = () => {
      const message = chatInput.value.trim();
      if (message) {
        chatInput.value = "";
        session.primeTTS(); // Renew activation synchronously
        session.sendTextMessage(message);
      }
    };
  }

  if (chatInput) {
    chatInput.onkeypress = (e) => {
      if (e.key === 'Enter') sendBtn.onclick();
    };
  }

  // --- Audio Recording Events ---

  if (micBtn) {
    micBtn.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      if (!state.isVoiceMode || state.isAISpeaking) return;
      if (!state.isListening && !state.isRecordingPending) {
        micBtn.style.transform = 'scale(0.95)';
        audio.startRecording(session.sendTextMessage);
      }
    });

    const stopMicAction = (e) => {
      e.preventDefault();
      if (state.isVoiceMode && (state.isListening || state.isRecordingPending)) {
        micBtn.style.transform = 'none';
        session.primeTTS(); // Renew activation synchronously
        audio.stopRecording();
      }
    };

    micBtn.addEventListener('pointerup', stopMicAction);
    micBtn.addEventListener('pointercancel', stopMicAction);
    micBtn.addEventListener('pointerleave', stopMicAction);
  }

  // Spacebar hold-to-record (capture phase to intercept before browser synthetic clicks)
  window.addEventListener('keydown', (e) => {
    if (e.code !== 'Space' || e.repeat) return;
    if (!state.isVoiceMode) return;
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;
    
    e.preventDefault();
    e.stopPropagation();
    
    if (state.isAISpeaking) return;
    if (!state.isListening && !state.isRecordingPending) {
      audio.startRecording(session.sendTextMessage);
    }
  }, { capture: true });

  window.addEventListener('keyup', (e) => {
    if (e.code !== 'Space') return;
    if (!state.isVoiceMode) return;
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) return;
    
    e.preventDefault();
    e.stopPropagation();
    
    session.primeTTS(); // Renew activation synchronously
    audio.stopRecording();
  }, { capture: true });

  const endSessionBtn = document.getElementById("endSessionBtn");
  if (endSessionBtn) {
    endSessionBtn.onclick = async () => {
      if (!state.sessionId) return;

      if (window.speechSynthesis.speaking) window.speechSynthesis.cancel();
      ui.setStatusText("Ending session...");

      try {
        await api.endSessionReq(state.sessionId, state.patientId);
        state.setSessionId(null);
        window.location.href = "/";
      } catch (err) {
        console.error("Failed to end session:", err);
        state.setSessionId(null);
        window.location.href = "/";
      }
    };
  }
}

// Bootstrap application
audio.loadVoices();
bindEvents();
window.onload = () => session.initializeSession();
