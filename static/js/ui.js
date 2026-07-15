import { state } from './state.js';

// Cache DOM elements that exist on load
const uiElements = {
  chat: document.getElementById("chat"),
  chatWrapper: document.getElementById("chatWrapper"),
  statusText: document.getElementById("status"),
  micBtn: document.getElementById("micBtn"),
  sessionStats: document.getElementById("sessionStats"),
  voiceModeBtn: document.getElementById("voiceModeBtn"),
  textModeBtn: document.getElementById("textModeBtn"),
  voiceInput: document.getElementById("voiceInput"),
  textInput: document.getElementById("textInput"),
  chatInput: document.getElementById("chatInput")
};

let typingNode = null;

const screens = ["loadingScreen", "profileSelectionScreen", "dashboardScreen", "mainApp"];

export function getPathForScreen(screen) {
  const map = {
    "loadingScreen": "/",
    "profileSelectionScreen": "/profiles",
    "dashboardScreen": "/dashboard",
    "mainApp": "/session"
  };
  return map[screen] || "/";
}

export function switchScreen(targetScreen, pushToHistory = true) {
  window.currentScreen = targetScreen;
  screens.forEach(s => {
    const el = document.getElementById(s);
    if (el) {
      if (s === targetScreen) {
        if (s === 'mainApp' || s === 'dashboardScreen') el.classList.remove("hidden");
        el.style.display = "flex";
      } else {
        el.style.display = "none";
      }
    }
  });

  if (pushToHistory) {
    history.pushState({ screen: targetScreen }, "", getPathForScreen(targetScreen));
  }
}

export function scrollToBottom() {
  setTimeout(() => {
    if (uiElements.chatWrapper) {
      uiElements.chatWrapper.scrollTop = uiElements.chatWrapper.scrollHeight;
    }
  }, 100);
}

export function updateSessionStats() {
  if (!state.sessionStartTime) return;
  if (!uiElements.sessionStats) return;
  const elapsed = Math.floor((Date.now() - state.sessionStartTime) / 60000);
  uiElements.sessionStats.textContent = `Session · ${elapsed} min · ${state.exchangeCount} exchanges`;
}

export function addMessage(text, role) {
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
  if (uiElements.chat) {
    uiElements.chat.appendChild(messageDiv);
    scrollToBottom();
  }
  
  if (role === 'user') {
    state.exchangeCount++;
    updateSessionStats();
  }
}

export function addTyping(isUser = false, customText = null) {
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
  if (uiElements.chat) {
    uiElements.chat.appendChild(messageDiv);
    scrollToBottom();
  }
}

export function removeTyping() {
  if (!typingNode) return;
  typingNode.remove();
  typingNode = null;
}

export function setStatusText(text) {
  if (uiElements.statusText) {
    uiElements.statusText.textContent = text;
  }
}

export function toggleMicButtonVisuals(isRecording) {
  if (!uiElements.micBtn) return;
  if (isRecording) {
    uiElements.micBtn.classList.add("bg-moss", "border-moss", "text-paper");
  } else {
    uiElements.micBtn.classList.remove("bg-moss", "border-moss", "text-paper");
  }
}

export function showSafetyBanner() {
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

export function hideSafetyBanner() {
  const banner = document.getElementById("safetyBanner");
  if (banner) {
    banner.remove();
  }
}

export function showConfirm(title, text, callback) {
  const confirmationModal = document.getElementById("confirmationModal");
  const confirmModalTitle = document.getElementById("confirmModalTitle");
  const confirmModalText = document.getElementById("confirmModalText");
  const confirmModalCancelBtn = document.getElementById("confirmModalCancelBtn");
  const confirmModalConfirmBtn = document.getElementById("confirmModalConfirmBtn");

  confirmModalTitle.textContent = title;
  confirmModalText.textContent = text;
  
  confirmModalCancelBtn.onclick = () => {
    confirmationModal.style.display = "none";
  };
  
  confirmModalConfirmBtn.onclick = () => {
    confirmationModal.style.display = "none";
    if (callback) callback();
  };
  
  confirmationModal.style.display = "flex";
}
