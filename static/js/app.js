// 🚀 BACKEND LINKAGE
// Local: Leave blank ("") to use your local machine.
const BACKEND_URL = "";

let sessionId = null;
let patientId = localStorage.getItem("serinity_patient_id") || null;
let isListening = false;
let isVoiceMode = false; // Default to text mode per clinical feel
let mediaRecorder;
let audioChunks = [];

// Session stats
let exchangeCount = 0;
let sessionStartTime = null;
let sessionInterval = null;

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

let typingNode = null;

function scrollToBottom() {
  setTimeout(() => {
    chatWrapper.scrollTop = chatWrapper.scrollHeight;
  }, 100);
}

function updateSessionStats() {
  if (!sessionStartTime) return;
  const statsEl = document.getElementById("sessionStats");
  if (!statsEl) return;
  const elapsed = Math.floor((Date.now() - sessionStartTime) / 60000);
  statsEl.textContent = `Session · ${elapsed} min · ${exchangeCount} exchanges`;
}

function addMessage(text, role) {
  const messageDiv = document.createElement("div");
  messageDiv.className = `flex ${role === 'user' ? 'justify-end' : 'justify-start'} fade-in w-full mb-6`;

  const contentDiv = document.createElement("div");
  
  if (role === 'assistant') {
    const label = document.createElement("span");
    label.className = "assistant-label";
    label.textContent = "ASSISTANT ·";
    contentDiv.appendChild(label);
    contentDiv.className = "pl-4 border-l-2 border-moss max-w-[85%] sm:max-w-[75%]";
  } else {
    const label = document.createElement("span");
    label.className = "assistant-label text-right block";
    const dashName = document.getElementById("dashboardPatientName");
    const userName = dashName ? dashName.innerText : "USER";
    label.textContent = "· " + userName.toUpperCase();
    contentDiv.appendChild(label);
    contentDiv.className = "pr-4 border-r-2 border-clay text-right max-w-[85%] sm:max-w-[75%]";
  }

  const textNode = document.createElement("p");
  textNode.className = "text-ink whitespace-pre-wrap";
  textNode.textContent = text;
  contentDiv.appendChild(textNode);
  
  messageDiv.appendChild(contentDiv);
  chat.appendChild(messageDiv);
  scrollToBottom();
  
  if (role === 'user') {
    exchangeCount++;
    updateSessionStats();
  }
}

function addTyping(isUser = false, customText = null) {
  if (typingNode) return;

  const messageDiv = document.createElement("div");
  messageDiv.className = `flex ${isUser ? 'justify-end' : 'justify-start'} fade-in w-full mb-6`;

  const contentDiv = document.createElement("div");
  
  if (!isUser) {
    const label = document.createElement("span");
    label.className = "assistant-label";
    label.textContent = "ASSISTANT ·";
    contentDiv.appendChild(label);
    contentDiv.className = "pl-4 border-l-2 border-moss max-w-[85%] sm:max-w-[75%]";
  } else {
    const label = document.createElement("span");
    label.className = "assistant-label text-right block";
    const dashName = document.getElementById("dashboardPatientName");
    const userName = dashName ? dashName.innerText : "USER";
    label.textContent = "· " + userName.toUpperCase();
    contentDiv.appendChild(label);
    contentDiv.className = "pr-4 border-r-2 border-clay text-right max-w-[85%] sm:max-w-[75%]";
  }

  if (customText) {
    const textNode = document.createElement("p");
    textNode.className = "text-moss text-sm italic font-utility animate-pulse";
    textNode.textContent = customText;
    contentDiv.appendChild(textNode);
  } else {
    const indicator = document.createElement("div");
    indicator.className = "typing-indicator flex gap-1 mt-2" + (isUser ? " justify-end" : "");
    indicator.innerHTML = `<span></span><span></span><span></span>`;
    contentDiv.appendChild(indicator);
  }
  
  messageDiv.appendChild(contentDiv);
  
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
    statusText.textContent = "Assistant is thinking...";
    await sleep(500);

    addTyping(false, "Thinking...");
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

    statusText.textContent = "Assistant is responding...";

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
      statusText.textContent = "Assistant is speaking...";
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
    
    // Render profile domains
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
  await showDashboard(patientId);
};

// Create & Start Profile Action
document.getElementById("createProfileBtn").onclick = async () => {
  const nameInput = document.getElementById("newPatientName");
  const ageInput = document.getElementById("newPatientAge");
  const genderInput = document.getElementById("newPatientGender");
  const occupationInput = document.getElementById("newPatientOccupation");
  const concernInput = document.getElementById("newPatientConcern");
  
  const name = nameInput.value.trim();
  const age = ageInput.value ? parseInt(ageInput.value) : null;
  const gender = genderInput ? genderInput.value : null;
  const occupation = occupationInput ? occupationInput.value.trim() : null;
  const primary_concern = concernInput ? concernInput.value.trim() : null;

  if (!name) {
    alert("Please enter a name for the new profile.");
    return;
  }

  try {
    const createRes = await fetch(`${BACKEND_URL}/patients/create`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        name: name, 
        age: age,
        gender: gender,
        occupation: occupation,
        primary_concern: primary_concern
      })
    });
    const pData = await createRes.json();
    patientId = pData.patient_id;
    localStorage.setItem("serinity_patient_id", patientId);
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

    // Setup session stats
    sessionStartTime = Date.now();
    exchangeCount = 0;
    updateSessionStats();
    if (sessionInterval) clearInterval(sessionInterval);
    sessionInterval = setInterval(updateSessionStats, 60000);

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
  voiceModeBtn.classList.add("active");
  textModeBtn.classList.remove("active");
  voiceInput.style.display = "flex";
  textInput.style.display = "none";
};

textModeBtn.onclick = () => {
  isVoiceMode = false;
  textModeBtn.classList.add("active");
  voiceModeBtn.classList.remove("active");
  voiceInput.style.display = "none";
  textInput.style.display = "block";
  chatInput.focus();
};

async function sendTextMessage(message, emotion = null) {
  addMessage(message, "user");
  addTyping(false, "Analyzing...");

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
      if (!document.getElementById("safetyBanner")) {
        const banner = document.createElement("div");
        banner.id = "safetyBanner";
        banner.className = "bg-signal text-paper p-4 shadow-md z-50 fixed top-0 left-0 right-0 fade-in";
        banner.innerHTML = `
          <div class="max-w-5xl mx-auto flex w-full justify-between items-start">
            <div>
              <h3 class="font-utility uppercase tracking-widest text-sm mb-1 font-bold">Emergency Support</h3>
              <p class="text-sm">You are not alone. Free, confidential support is available right now.</p>
              <ul class="list-none text-sm font-utility space-y-1 mt-2">
                <li>iCall (TISS): 9152987821</li>
                <li>Kiran: 1800-599-0019</li>
                <li>Vandrevala: 1860-2662-345</li>
              </ul>
            </div>
            <button onclick="document.getElementById('safetyBanner').remove()" class="text-paper hover:opacity-70 text-2xl font-bold p-2 cursor-pointer leading-none">&times;</button>
          </div>
        `;
        document.body.appendChild(banner);
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
      addTyping(true, "Transcribing...");

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
