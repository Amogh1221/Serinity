// 🚀 BACKEND LINKAGE
// Local: Leave blank ("") to use your local machine.
const BACKEND_URL = "";

let sessionId = null;
let patientId = localStorage.getItem("serinity_patient_id") || null;
let isListening = false;
let isVoiceMode = true;
let mediaRecorder;
let audioChunks = [];

const chat = document.getElementById("chat");
const chatWrapper = document.getElementById("chatWrapper");
const micBtn = document.getElementById("micBtn");
const statusText = document.getElementById("status");
const loadingScreen = document.getElementById("loadingScreen");
const mainApp = document.getElementById("mainApp");
const startButton = document.getElementById("startButton");
const profileSelectionScreen = document.getElementById("profileSelectionScreen");
const dashboardScreen = document.getElementById("dashboardScreen");

// Mode toggle elements
const voiceModeBtn = document.getElementById("voiceModeBtn");
const textModeBtn = document.getElementById("textModeBtn");
const voiceInput = document.getElementById("voiceInput");
const textInput = document.getElementById("textInput");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");

const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth <= 768;
const headerRole = document.getElementById("headerRole");
if (headerRole) {
  headerRole.textContent = isMobile ? "Dr. Sarah - AI Psychiatrist" : "Dr. Aiden - AI Psychiatrist";
}

let typingNode = null;

function scrollToBottom() {
  setTimeout(() => {
    chatWrapper.scrollTop = chatWrapper.scrollHeight;
  }, 100);
}

function addMessage(text, role) {
  const messageDiv = document.createElement("div");
  messageDiv.className = `flex ${role === 'user' ? 'justify-end' : 'justify-start'} fade-in`;

  const bubble = document.createElement("div");
  bubble.className = `max-w-[85%] sm:max-w-[75%] px-4 sm:px-5 py-3 rounded-2xl ${role === 'user'
      ? 'bg-gradient-to-br from-blue-500 to-blue-600 text-white rounded-tr-md'
      : 'bg-slate-700/50 text-slate-100 rounded-tl-md border border-slate-600/30'
    } shadow-lg`;

  bubble.textContent = text;
  messageDiv.appendChild(bubble);
  chat.appendChild(messageDiv);
  scrollToBottom();
}

function addTyping() {
  if (typingNode) return;

  const messageDiv = document.createElement("div");
  messageDiv.className = "flex justify-start fade-in";

  const bubble = document.createElement("div");
  bubble.className = "px-5 py-4 rounded-2xl rounded-tl-md bg-slate-700/30 border border-slate-600/30";

  bubble.innerHTML = `
    <div class="typing-indicator flex gap-1">
      <span></span>
      <span></span>
      <span></span>
    </div>
  `;

  messageDiv.appendChild(bubble);
  typingNode = messageDiv;
  chat.appendChild(messageDiv);
  scrollToBottom();
}

function removeTyping() {
  if (!typingNode) return;
  typingNode.remove();
  typingNode = null;
}

function clearChat() {
  chat.innerHTML = "";
}

const voiceSelect = document.getElementById("voiceSelect");
let systemVoices = [];

function loadVoices() {
  systemVoices = window.speechSynthesis.getVoices();
  voiceSelect.innerHTML = "";

  const englishVoices = systemVoices.filter(v => v.lang.includes('en'));

  englishVoices.forEach((voice, index) => {
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
loadVoices();

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function handleAssistantResponses(message) {
  if (!message) return;

  // Split on && — model optionally separates acknowledgment from follow-up
  const parts = message.split("&&").map(p => p.trim()).filter(Boolean);

  // 1. Show + speak the acknowledgment part
  addMessage(parts[0], "assistant");
  await speak(parts[0]);

  // 2. If there's a follow-up, show it with a brief therapeutic pause
  if (parts[1]) {
    statusText.textContent = "Dr. Aiden is thinking...";
    await sleep(500);

    addTyping();
    await sleep(500);
    removeTyping();

    addMessage(parts[1], "assistant");
    await speak(parts[1]);
  }
}

// Dr. Aiden Speech Engine (Promise-wrapped for sequential pause-play)
function speak(text) {
  return new Promise((resolve) => {
    if (!isVoiceMode) {
      resolve();
      return;
    }

    if (window.speechSynthesis.speaking) {
      window.speechSynthesis.cancel();
    }

    statusText.textContent = "Dr. Aiden is responding...";

    const utterance = new SpeechSynthesisUtterance(text);
    const selectedVoiceName = voiceSelect.value;
    let preferredVoice = systemVoices.find(v => v.name === selectedVoiceName);

    if (!preferredVoice) {
      preferredVoice = systemVoices.find(v => v.lang.includes('en') && (v.name.includes('Female') || v.name.includes('Zira') || v.name.includes('Samantha'))) || systemVoices.find(v => v.lang.includes('en'));
    }

    if (preferredVoice) utterance.voice = preferredVoice;
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    utterance.onstart = () => {
      statusText.textContent = "Dr. Aiden is speaking...";
    };

    utterance.onend = () => {
      statusText.textContent = "Tap the microphone to speak";
      resolve();
    };

    utterance.onerror = (e) => {
      console.error("Browser TTS Error:", e);
      statusText.textContent = "Tap the microphone to speak";
      resolve();
    };

    window.speechSynthesis.speak(utterance);

    // Safety fallback: if utterance.onend doesn't fire, resolve after a calculation
    const wordCount = text.split(/\s+/).length;
    const timeoutMs = Math.max(3000, wordCount * 600);
    setTimeout(resolve, timeoutMs);
  });
}

// -------------------------------------------------------------
// Patients Lookup and Start Flow
// -------------------------------------------------------------

async function fetchPatients() {
  try {
    const response = await fetch(`${BACKEND_URL}/patients`);
    const patients = await response.json();
    const dropdown = document.getElementById("patientDropdown");
    dropdown.innerHTML = '<option value="">-- Choose Profile --</option>';
    patients.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.patient_id;
      opt.textContent = `${p.name} (Age: ${p.age || 'N/A'})`;
      if (p.patient_id === patientId) {
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

document.getElementById("patientDropdown").onchange = toggleSelectButton;

// New Dashboard Logic
async function showDashboard(pId) {
  try {
    const res = await fetch(`${BACKEND_URL}/patients/${pId}/dashboard`);
    if (!res.ok) throw new Error("Dashboard load failed");
    const data = await res.json();
    
    document.getElementById("dashboardPatientName").textContent = data.patient.name;
    document.getElementById("dashboardPatientAge").textContent = data.patient.age ? `Age: ${data.patient.age}` : "Age: --";
    
    const list = document.getElementById("dashboardSessionsList");
    list.innerHTML = "";
    
    if (data.sessions && data.sessions.length > 0) {
      data.sessions.forEach(sess => {
        const d = new Date(sess.created_at).toLocaleString();
        const summary = sess.rolling_summary || "No summary available.";
        list.innerHTML += `
          <div class="bg-slate-800 p-4 rounded-xl border border-slate-700">
            <div class="text-xs text-blue-400 font-bold mb-2">${d}</div>
            <div class="text-sm text-slate-300 whitespace-pre-wrap">${summary}</div>
          </div>
        `;
      });
    } else {
      list.innerHTML = `<p class="text-slate-500 text-center italic mt-10">No previous sessions found.</p>`;
    }
    
    profileSelectionScreen.style.display = "none";
    loadingScreen.style.display = "none";
    dashboardScreen.style.display = "flex";
    
  } catch (err) {
    console.error("Dashboard error", err);
    alert("Could not load patient dashboard.");
  }
}

document.getElementById("dashboardBackBtn").onclick = () => {
  dashboardScreen.style.display = "none";
  profileSelectionScreen.style.display = "flex";
  fetchPatients();
};

document.getElementById("dashboardStartBtn").onclick = async () => {
  dashboardScreen.style.display = "none";
  loadingScreen.style.display = "flex";
  startButton.textContent = "Loading Session...";
  startButton.disabled = true;
  await startActualSession(patientId);
};

// Select Returning Profile Action
document.getElementById("selectProfileBtn").onclick = async () => {
  const dropdown = document.getElementById("patientDropdown");
  patientId = dropdown.value;
  localStorage.setItem("serinity_patient_id", patientId);
  const selectedText = dropdown.options[dropdown.selectedIndex].text;
  document.getElementById("activePatientDisplay").textContent = `Patient: ${selectedText.split(" (")[0]}`;
  await showDashboard(patientId);
};

// Create & Start Profile Action
document.getElementById("createProfileBtn").onclick = async () => {
  const nameInput = document.getElementById("newPatientName");
  const ageInput = document.getElementById("newPatientAge");
  const name = nameInput.value.trim();
  const age = ageInput.value ? parseInt(ageInput.value) : null;

  if (!name) {
    alert("Please enter a name for the new profile.");
    return;
  }

  try {
    const createRes = await fetch(`${BACKEND_URL}/patients/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name, age: age })
    });
    const pData = await createRes.json();
    patientId = pData.patient_id;
    localStorage.setItem("serinity_patient_id", patientId);
    document.getElementById("activePatientDisplay").textContent = `Patient: ${name}`;
    await showDashboard(patientId);
  } catch (e) {
    console.error("Failed to create profile:", e);
    alert("Failed to create patient profile. Please try again.");
  }
};

async function initializeSession(retryCount = 0) {
  try {
    // Ping health first to wake up
    await fetch(`${BACKEND_URL}/health`);
    document.getElementById("loadingDots").style.display = "none";
    const wakeupText = document.getElementById("wakeupText");
    if (wakeupText) wakeupText.style.display = "none";

    // Front page is now fully loaded! Set the button ready.
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

async function startActualSession(pId) {
  try {
    const response = await fetch(`${BACKEND_URL}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patient_id: pId })
    });
    const data = await response.json();
    sessionId = data.session_id;
    patientId = data.patient_id;

    // Immediately load the chat interface
    loadingScreen.classList.add("hidden");
    loadingScreen.style.display = "none";
    mainApp.style.display = "flex";

    // Render first message in UI and speak
    handleAssistantResponses(data.assistant_message);
  } catch (e) {
    console.error("Failed to start session:", e);
    alert("Failed to start session. Please try again.");
    location.reload();
  }
}

// Front page click: Open Profile Selection dialog
startButton.onclick = () => {
  if (startButton.textContent === "Start Consultation") {
    // Hide welcome front page, show profile dialog
    loadingScreen.style.display = "none";
    profileSelectionScreen.style.display = "flex";
    fetchPatients();
  } else if (startButton.textContent === "Retry Connection") {
    startButton.textContent = "Initializing...";
    startButton.disabled = true;
    initializeSession();
  }
};

window.onload = initializeSession;

// Mode toggle
voiceModeBtn.onclick = () => {
  isVoiceMode = true;
  voiceModeBtn.classList.remove("bg-slate-700/50", "text-slate-400");
  voiceModeBtn.classList.add("bg-blue-600", "text-white");
  textModeBtn.classList.remove("bg-blue-600", "text-white");
  textModeBtn.classList.add("bg-slate-700/50", "text-slate-400");
  voiceInput.style.display = "flex";
  textInput.style.display = "none";
};

textModeBtn.onclick = () => {
  isVoiceMode = false;
  textModeBtn.classList.remove("bg-slate-700/50", "text-slate-400");
  textModeBtn.classList.add("bg-blue-600", "text-white");
  voiceModeBtn.classList.remove("bg-blue-600", "text-white");
  voiceModeBtn.classList.add("bg-slate-700/50", "text-slate-400");
  voiceInput.style.display = "none";
  textInput.style.display = "block";
  chatInput.focus();
};

async function sendTextMessage(message, emotion = null) {
  addMessage(message, "user");
  addTyping();

  try {
    const response = await fetch(`${BACKEND_URL}/chat_text`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message,
        session_id: sessionId,
        patient_id: patientId,
        emotion: emotion
      })
    });

    const data = await response.json();
    removeTyping();
    await handleAssistantResponses(data.assistant_message);

    if (data.risk_flagged) {
      document.getElementById("safetyBanner").style.display = "block";
      const displayLabel = document.getElementById("activePatientDisplay");
      if (displayLabel) {
        displayLabel.classList.remove("text-blue-400");
        displayLabel.classList.add("text-red-400", "animate-pulse");
      }
    }
  } catch (err) {
    removeTyping();
    addMessage("I apologize, but I'm having trouble connecting right now.", "assistant");
    console.error("Error:", err);
  }
}

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


// Voice Capture
async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      audioChunks.push(event.data);
    };

    mediaRecorder.onstop = async () => {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.webm');

      statusText.textContent = "Transcribing your voice...";
      addTyping();

      try {
        const response = await fetch(`${BACKEND_URL}/transcribe`, {
          method: "POST",
          body: formData
        });
        const data = await response.json();

        removeTyping();
        if (data.text && data.text.trim() !== "") {
          sendTextMessage(data.text, data.emotion);
        } else {
          statusText.textContent = "I didn't catch that. Try again?";
        }
      } catch (e) {
        removeTyping();
        console.error("Transcription failed", e);
        statusText.textContent = "Tap to try again";
      }
    };

    mediaRecorder.start();
    isListening = true;
    micBtn.classList.add("recording-pulse", "!from-red-500", "!to-red-600", "!shadow-red-500/50");
    statusText.textContent = "Listening... (tap again to stop)";
  } catch (err) {
    console.error("Microphone access denied", err);
    statusText.textContent = "Microphone access denied";
  }
}

function stopRecording() {
  if (mediaRecorder && isListening) {
    mediaRecorder.stop();
    isListening = false;
    micBtn.classList.remove("recording-pulse", "!from-red-500", "!to-red-600", "!shadow-red-500/50");
    statusText.textContent = "Processing...";
    mediaRecorder.stream.getTracks().forEach(track => track.stop());
  }
}

micBtn.onclick = () => {
  if (!isListening) {
    startRecording();
  } else {
    stopRecording();
  }
};

// End Session Explicitly
document.getElementById("endSessionBtn").onclick = async () => {
  if (!sessionId) return;

  if (window.currentAudio) window.currentAudio.pause();
  if (window.speechSynthesis.speaking) window.speechSynthesis.cancel();

  statusText.textContent = "Ending session...";

  try {
    await fetch(`${BACKEND_URL}/end_session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        patient_id: patientId
      })
    });
    // Summary is stored in DB for next session — just return to profile selection
    sessionId = null;
    location.reload();
  } catch (err) {
    console.error("Failed to end session:", err);
    sessionId = null;
    location.reload();
  }
};
