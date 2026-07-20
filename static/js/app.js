import { state } from './state.js';
import * as api from './api.js';
import * as ui from './ui.js';
import * as audio from './audio.js';
import * as profiles from './profiles.js';
import * as session from './session.js';
import * as auth from './auth.js';

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
      if (path === "/dashboard" || path === "/session") {
        if (!state.patientId) {
          profiles.fetchPatients();
        } else {
          ui.switchScreen(path === "/dashboard" ? "dashboardScreen" : "mainApp", false);
        }
      } else {
        ui.switchScreen("loadingScreen", false);
      }
    }
  });

  // Global Unauthorized Handler
  window.addEventListener("unauthorized", () => {
    ui.switchScreen("authScreen", false);
  });

  // --- Auth Events ---
  const loginFormContainer = document.getElementById("loginFormContainer");
  const signupFormContainer = document.getElementById("signupFormContainer");
  const forgotPwdFormContainer = document.getElementById("forgotPwdFormContainer");
  const otpStepContainer = document.getElementById("otpStepContainer");
  const newPwdStepContainer = document.getElementById("newPwdStepContainer");
  const signupOtpStepContainer = document.getElementById("signupOtpStepContainer");

  // Track verified OTP state in memory (not persisted — refresh = back to login)
  let _otpVerifiedEmail = null;

  function showAuthPanel(panelId) {
    // Only hide/show panels that exist
    const panels = [loginFormContainer, signupFormContainer, forgotPwdFormContainer, otpStepContainer, newPwdStepContainer, signupOtpStepContainer];
    panels.forEach(p => { 
      if(p) { 
        p.classList.add('hidden'); 
        p.classList.remove('block'); 
      } 
    });
    const target = document.getElementById(panelId);
    if (target) {
      target.classList.remove('hidden');
      target.classList.add('block');
    } else {
      console.error("Auth panel not found:", panelId);
    }
  }

  document.getElementById("showSignupBtn")?.addEventListener("click", () => showAuthPanel("signupFormContainer"));
  document.getElementById("showForgotPwdBtn")?.addEventListener("click", () => showAuthPanel("forgotPwdFormContainer"));
  document.getElementById("backToLoginBtn1")?.addEventListener("click", () => showAuthPanel("loginFormContainer"));
  document.getElementById("backToLoginBtn2")?.addEventListener("click", () => showAuthPanel("loginFormContainer"));
  document.getElementById("backToForgotBtn")?.addEventListener("click", () => showAuthPanel("forgotPwdFormContainer"));
  document.getElementById("backToSignupBtn")?.addEventListener("click", () => showAuthPanel("signupFormContainer"));

  // Populate Nationality Dropdown
  const countries = [
    "India", "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua and Barbuda", 
    "Argentina", "Armenia", "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", 
    "Barbados", "Belarus", "Belgium", "Belize", "Benin", "Bhutan", "Bolivia", 
    "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina Faso", 
    "Burundi", "Côte d'Ivoire", "Cabo Verde", "Cambodia", "Cameroon", "Canada", "Central African Republic", 
    "Chad", "Chile", "China", "Colombia", "Comoros", "Congo (Congo-Brazzaville)", "Costa Rica", 
    "Croatia", "Cuba", "Cyprus", "Czechia (Czech Republic)", "Democratic Republic of the Congo", 
    "Denmark", "Djibouti", "Dominica", "Dominican Republic", "Ecuador", "Egypt", "El Salvador", 
    "Equatorial Guinea", "Eritrea", "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", 
    "France", "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Grenada", 
    "Guatemala", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Holy See", "Honduras", 
    "Hungary", "Iceland", "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Jamaica", 
    "Japan", "Jordan", "Kazakhstan", "Kenya", "Kiribati", "Kuwait", "Kyrgyzstan", "Laos", 
    "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", 
    "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Marshall Islands", "Mauritania", 
    "Mauritius", "Mexico", "Micronesia", "Moldova", "Monaco", "Mongolia", "Montenegro", "Morocco", 
    "Mozambique", "Myanmar (formerly Burma)", "Namibia", "Nauru", "Nepal", "Netherlands", "New Zealand", 
    "Nicaragua", "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan", 
    "Palau", "Palestine State", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland", 
    "Portugal", "Qatar", "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia", 
    "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Sao Tome and Principe", "Saudi Arabia", 
    "Senegal", "Serbia", "Seychelles", "Sierra Leone", "Singapore", "Slovakia", "Slovenia", 
    "Solomon Islands", "Somalia", "South Africa", "South Korea", "South Sudan", "Spain", "Sri Lanka", 
    "Sudan", "Suriname", "Sweden", "Switzerland", "Syria", "Tajikistan", "Tanzania", "Thailand", 
    "Timor-Leste", "Togo", "Tonga", "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", 
    "Tuvalu", "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom", "United States", "Uruguay", 
    "Uzbekistan", "Vanuatu", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe"
  ];
  
  const signupNationality = document.getElementById("signupNationality");
  const nationalityDropdown = document.getElementById("nationalityDropdown");
  
  if (signupNationality && nationalityDropdown) {
    function renderCountries(filterText = "") {
      nationalityDropdown.innerHTML = "";
      const filtered = countries.filter(c => c.toLowerCase().includes(filterText.toLowerCase()));
      filtered.forEach(country => {
        const div = document.createElement("div");
        div.className = "p-2 hover:bg-moss/20 cursor-pointer text-sm text-ink";
        div.textContent = country;
        div.onmousedown = (e) => {
          e.preventDefault(); // prevent blur
          signupNationality.value = country;
          nationalityDropdown.classList.add("hidden");
        };
        nationalityDropdown.appendChild(div);
      });
      if (filtered.length === 0) {
        const div = document.createElement("div");
        div.className = "p-2 text-sm text-clay italic";
        div.textContent = "No matches";
        nationalityDropdown.appendChild(div);
      }
    }

    signupNationality.addEventListener("focus", () => {
      renderCountries(signupNationality.value);
      nationalityDropdown.classList.remove("hidden");
    });

    signupNationality.addEventListener("input", (e) => {
      renderCountries(e.target.value);
      nationalityDropdown.classList.remove("hidden");
    });

    signupNationality.addEventListener("blur", () => {
      nationalityDropdown.classList.add("hidden");
    });
  }

  // Helper function to strip spaces from OTP input
  function setupOtpInputStripper(fieldId) {
    const field = document.getElementById(fieldId);
    if (field) {
      field.addEventListener('input', (e) => {
        // Remove all spaces from the input value
        e.target.value = e.target.value.replace(/\s/g, '');
      });
    }
  }

  // Setup OTP input strippers for all OTP fields (signup, forgot password, delete account)
  setupOtpInputStripper("signupOtpCode");
  setupOtpInputStripper("resetOtpCode");
  setupOtpInputStripper("deleteAccountOtpCode");

  document.getElementById("loginBtn")?.addEventListener("click", async () => {
    const user = document.getElementById("loginUsername").value.trim();
    const pass = document.getElementById("loginPassword").value;
    if (!user || !pass) return ui.showAlert("Login Error", "Please enter both username/email and password");
    
    try {
      document.getElementById("loginBtn").textContent = "Logging In...";
      await auth.login(user, pass);
      document.getElementById("loginBtn").textContent = "Log In";
      await profiles.fetchPatients();
    } catch (e) {
      ui.showAlert("Login Failed", e.message);
      document.getElementById("loginBtn").textContent = "Log In";
    }
  });

  let _signupPayload = null;

  document.getElementById("signupGetOtpBtn")?.addEventListener("click", async () => {
    const payload = {
      name: document.getElementById("signupName").value.trim(),
      username: document.getElementById("signupUsername").value.trim(),
      email: document.getElementById("signupEmail").value.trim(),
      password: document.getElementById("signupPassword").value,
      gender: document.getElementById("signupGender").value,
      age: parseInt(document.getElementById("signupAge").value) || null,
      nationality: document.getElementById("signupNationality").value,
      primary_concern: document.getElementById("signupConcern").value,
      emergency_contact_name: document.getElementById("signupEmergencyName").value.trim() || null,
      emergency_contact_phone: document.getElementById("signupEmergencyPhone").value.trim() || null
    };

    if (!payload.name || !payload.username || !payload.email || !payload.password || !payload.gender || !payload.nationality || !payload.primary_concern) {
      return ui.showAlert("Signup Error", "Please fill out all required fields (*).");
    }
    
    if (payload.password.length < 8) {
      return ui.showAlert("Signup Error", "Password must be at least 8 characters long.");
    }
    
    if (payload.age !== null && (payload.age < 5 || payload.age > 99)) {
      return ui.showAlert("Signup Error", "Age must be between 5 and 99.");
    }

    try {
      document.getElementById("signupGetOtpBtn").textContent = "Sending OTP...";
      document.getElementById("signupGetOtpBtn").disabled = true;
      
      await auth.requestSignupOtp(payload.email, payload.username);
      
      _signupPayload = payload;
      
      // Clear OTP code and switch to signup OTP panel
      const signupOtpCodeField = document.getElementById("signupOtpCode");
      if (signupOtpCodeField) {
        signupOtpCodeField.value = "";
      }
      showAuthPanel("signupOtpStepContainer");
      
    } catch (e) {
      ui.showAlert("Signup Failed", e.message);
    } finally {
      document.getElementById("signupGetOtpBtn").textContent = "Get OTP";
      document.getElementById("signupGetOtpBtn").disabled = false;
    }
  });

  document.getElementById("signupCompleteBtn")?.addEventListener("click", async () => {
    if (!_signupPayload) {
      return ui.showAlert("Signup Error", "Missing signup details. Please refresh and try again.");
    }
    
    const signupOtpCodeField = document.getElementById("signupOtpCode");
    if (!signupOtpCodeField) {
      return ui.showAlert("Signup Error", "OTP code field not found. Please refresh and try again.");
    }
    
    const otpCode = signupOtpCodeField.value.trim();
    if (otpCode.length !== 6) {
      return ui.showAlert("Signup Error", "Please enter the 6-digit OTP code.");
    }
    
    try {
      const completeBtn = document.getElementById("signupCompleteBtn");
      if (completeBtn) {
        completeBtn.textContent = "Creating Account...";
        completeBtn.disabled = true;
      }
      
      const payload = {
        ..._signupPayload,
        otp_code: otpCode
      };
      
      await auth.signup(payload);
      
      _signupPayload = null;
      if (signupOtpCodeField) {
        signupOtpCodeField.value = "";
      }
      
      // Account created successfully, go back to login
      ui.showAlert("Success", "Account created successfully!");
      showAuthPanel("loginFormContainer");
      
      await profiles.fetchPatients();
    } catch (e) {
      ui.showAlert("Signup Failed", e.message);
    } finally {
      const completeBtn = document.getElementById("signupCompleteBtn");
      if (completeBtn) {
        completeBtn.textContent = "Complete Signup";
        completeBtn.disabled = false;
      }
    }
  });

  document.getElementById("requestOtpBtn")?.addEventListener("click", async () => {
    const email = document.getElementById("forgotPwdEmail").value.trim();
    if (!email) return ui.showAlert("Reset Password", "Please enter your email.");
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) return ui.showAlert("Reset Password", "Please enter a valid email address.");
    try {
      document.getElementById("requestOtpBtn").textContent = "Sending...";
      document.getElementById("requestOtpBtn").disabled = true;
      await auth.forgotPassword(email);
      document.getElementById("resetOtpCode").value = "";
      showAuthPanel("otpStepContainer");
    } catch(e) {
      ui.showAlert("Reset Password", e.message);
    } finally {
      document.getElementById("requestOtpBtn").textContent = "Send Code";
      document.getElementById("requestOtpBtn").disabled = false;
    }
  });

  document.getElementById("verifyOtpBtn")?.addEventListener("click", async () => {
    const email = document.getElementById("forgotPwdEmail").value.trim();
    const otp = document.getElementById("resetOtpCode").value.trim();
    if (otp.length !== 6) return ui.showAlert("Reset Password", "Please enter the 6-digit code.");
    try {
      document.getElementById("verifyOtpBtn").textContent = "Verifying...";
      document.getElementById("verifyOtpBtn").disabled = true;
      await auth.verifyOtp(email, otp);
      _otpVerifiedEmail = email;
      document.getElementById("resetNewPassword").value = "";
      showAuthPanel("newPwdStepContainer");
    } catch(e) {
      ui.showAlert("Verification Failed", e.message);
    } finally {
      document.getElementById("verifyOtpBtn").textContent = "Verify Code";
      document.getElementById("verifyOtpBtn").disabled = false;
    }
  });

  document.getElementById("submitResetBtn")?.addEventListener("click", async () => {
    // If _otpVerifiedEmail is null, this means a refresh happened — redirect to login
    if (!_otpVerifiedEmail) {
      showAuthPanel("loginFormContainer");
      return;
    }
    const newPass = document.getElementById("resetNewPassword").value;
    if (!newPass || newPass.length < 8) return ui.showAlert("Reset Password", "New password must be at least 8 characters long.");
    try {
      document.getElementById("submitResetBtn").textContent = "Updating...";
      document.getElementById("submitResetBtn").disabled = true;
      const otp = document.getElementById("resetOtpCode").value.trim();
      await auth.resetPassword(_otpVerifiedEmail, otp, newPass);
      _otpVerifiedEmail = null;
      ui.showAlert("Success", "Password reset successfully! Please log in.");
      showAuthPanel("loginFormContainer");
    } catch (e) {
      ui.showAlert("Reset Failed", e.message);
    } finally {
      document.getElementById("submitResetBtn").textContent = "Update Password";
      document.getElementById("submitResetBtn").disabled = false;
    }
  });

  // --- Profiles & Dashboard Events ---

  const patientDropdown = document.getElementById("patientDropdown");
  if (patientDropdown) patientDropdown.onchange = profiles.toggleSelectButton;

  const dashboardLogoutBtn = document.getElementById("dashboardLogoutBtn");
  if (dashboardLogoutBtn) {
    dashboardLogoutBtn.onclick = () => {
      auth.logout();
      ui.switchScreen("authScreen");
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
      document.getElementById("deleteAccountConfirmModal").style.display = "flex";
    };
  }

  const deleteAccountCancelBtn = document.getElementById("deleteAccountCancelBtn");
  if (deleteAccountCancelBtn) {
    deleteAccountCancelBtn.onclick = () => {
      document.getElementById("deleteAccountConfirmModal").style.display = "none";
    };
  }

  const deleteAccountSendOtpBtn = document.getElementById("deleteAccountSendOtpBtn");
  if (deleteAccountSendOtpBtn) {
    deleteAccountSendOtpBtn.onclick = async () => {
      try {
        deleteAccountSendOtpBtn.textContent = "Sending OTP...";
        deleteAccountSendOtpBtn.disabled = true;
        
        await auth.requestDeleteAccountOtp();
        
        // Close confirmation modal and show OTP modal
        document.getElementById("deleteAccountConfirmModal").style.display = "none";
        document.getElementById("deleteAccountOtpCode").value = "";
        document.getElementById("deleteAccountOtpModal").style.display = "flex";
        
      } catch (e) {
        console.error("Error requesting OTP:", e);
        ui.showAlert("Error", e.message);
      } finally {
        deleteAccountSendOtpBtn.textContent = "SEND OTP";
        deleteAccountSendOtpBtn.disabled = false;
      }
    };
  }

  const closeDeleteOtpModalBtn = document.getElementById("closeDeleteOtpModalBtn");
  if (closeDeleteOtpModalBtn) {
    closeDeleteOtpModalBtn.onclick = () => {
      document.getElementById("deleteAccountOtpModal").style.display = "none";
    };
  }

  const submitDeleteOtpBtn = document.getElementById("submitDeleteOtpBtn");
  if (submitDeleteOtpBtn) {
    submitDeleteOtpBtn.onclick = async () => {
      const code = document.getElementById("deleteAccountOtpCode").value.trim();
      if (code.length !== 6) return ui.showAlert("Error", "Please enter a valid 6-digit code.");
      try {
        submitDeleteOtpBtn.textContent = "Verifying...";
        submitDeleteOtpBtn.disabled = true;
        
        await auth.verifyDeleteAccount(code);
        
        document.getElementById("deleteAccountOtpModal").style.display = "none";
        auth.logout();
        ui.switchScreen("authScreen");
        
      } catch (e) {
        ui.showAlert("Error", e.message);
      } finally {
        submitDeleteOtpBtn.textContent = "Verify & Delete";
        submitDeleteOtpBtn.disabled = false;
      }
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
        ui.showAlert("Missing Information", "Please fill out all 4 required fields (Name, Age, Gender, and Occupation) to create a new profile.");
        return;
      }
      
      const parsedAge = parseInt(age);
      if (isNaN(parsedAge) || parsedAge < 5 || parsedAge > 99) {
        ui.showAlert("Invalid Age", "Age must be between 5 and 99.");
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
        ui.showAlert("Error", "Failed to create patient profile. Please try again.");
      }
    };
  }

  if (startButton) {
    startButton.onclick = async () => {
      const text = startButton.textContent.trim();
      if (text.includes("Start Consultation")) {
        if (!auth.isAuthenticated()) {
          ui.switchScreen("authScreen", false);
          return;
        }
        
        startButton.textContent = "Loading...";
        startButton.disabled = true;
        try {
          await profiles.fetchPatients();
        } catch(e) {
          console.error(e);
          ui.showAlert("Error", "Failed to load dashboard. Check console.");
        } finally {
          startButton.textContent = "Start Consultation";
          startButton.disabled = false;
        }
      } else if (text.includes("Retry")) {
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
api.pingHealth().catch(() => console.log("Wakeup ping sent."));
audio.loadVoices();
bindEvents();
window.onload = () => session.initializeSession();
