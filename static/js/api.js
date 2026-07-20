export const BACKEND_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
  ? "http://127.0.0.1:8000" 
  : "https://amogh1221-serinity.hf.space";

// Helper to get token
export function getToken() {
  return localStorage.getItem('serinity_token');
}

// Global fetch wrapper for auth
export async function authFetch(url, options = {}) {
  const token = getToken();
  const headers = { ...options.headers };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  // Don't override FormData headers
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(url, { ...options, headers });
  
  // Handle unauthorized globaly
  if (res.status === 401) {
    localStorage.removeItem('serinity_token');
    window.dispatchEvent(new Event('unauthorized'));
    throw new Error('Unauthorized');
  }
  
  return res;
}

/**
 * Fetches the list of patients associated with the logged-in user.
 * @returns {Promise<Array>} List of patient objects.
 */
export async function fetchPatientsList() {
  const res = await authFetch(`${BACKEND_URL}/patients`, { cache: "no-store" });
  return res.json();
}

/**
 * Loads the dashboard data for a specific patient.
 * @param {string} patientId 
 * @returns {Promise<Object>} Dashboard overview data.
 */
export async function loadDashboard(patientId) {
  const res = await authFetch(`${BACKEND_URL}/patients/${patientId}/dashboard`, { cache: "no-store" });
  if (!res.ok) throw new Error("Dashboard load failed");
  return res.json();
}

/**
 * Resets a patient's historical profile and sessions.
 * @param {string} patientId 
 */
export async function resetPatientProfile(patientId) {
  return authFetch(`${BACKEND_URL}/patients/${patientId}/reset`, { method: "POST" });
}

/**
 * Deletes a patient profile completely.
 * @param {string} patientId 
 */
export async function deletePatientProfile(patientId) {
  return authFetch(`${BACKEND_URL}/patients/${patientId}`, { method: "DELETE" });
}

/**
 * Creates a new patient profile linked to the user.
 * @param {Object} data 
 * @returns {Promise<Object>} The created patient data.
 */
export async function createPatientProfile(data) {
  const res = await authFetch(`${BACKEND_URL}/patients/create`, {
    method: "POST",
    body: JSON.stringify(data)
  });
  return res.json();
}

export async function pingHealth() {
  // health doesn't need auth, but authFetch is safe to use
  return fetch(`${BACKEND_URL}/health`);
}

export async function startSessionReq(patientId) {
  const res = await authFetch(`${BACKEND_URL}/start`, {
    method: "POST",
    body: JSON.stringify({ patient_id: patientId })
  });
  return res.json();
}

export async function sendChatText(sessionId, patientId, message, emotion) {
  const res = await authFetch(`${BACKEND_URL}/chat_text`, {
    method: "POST",
    body: JSON.stringify({
      message: message,
      session_id: sessionId,
      patient_id: patientId,
      emotion: emotion
    })
  });
  if (!res.ok) {
    let errorDetail = `HTTP Error ${res.status}`;
    try {
      const data = await res.json();
      errorDetail = data.detail || errorDetail;
    } catch(e) {}
    throw new Error(errorDetail);
  }
  return res.json();
}

export async function transcribeAudio(audioBlob) {
  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');
  
  // Custom headers because authFetch handles FormData correctly if Content-Type is omitted
  const res = await authFetch(`${BACKEND_URL}/transcribe`, {
    method: "POST",
    body: formData
  });
  return res.json();
}

export async function endSessionReq(sessionId, patientId) {
  return authFetch(`${BACKEND_URL}/end_session`, {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      patient_id: patientId
    })
  });
}

export async function getActiveSession(patientId) {
  const res = await authFetch(`${BACKEND_URL}/patients/${patientId}/active_session`, { cache: "no-store" });
  return res.json();
}

export async function getSessionMessages(sessionId) {
  const res = await authFetch(`${BACKEND_URL}/sessions/${sessionId}/messages`, { cache: "no-store" });
  return res.json();
}
