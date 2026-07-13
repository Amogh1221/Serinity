export const BACKEND_URL = "";

export async function fetchPatientsList() {
  const res = await fetch(`${BACKEND_URL}/patients`);
  return res.json();
}

export async function loadDashboard(patientId) {
  const res = await fetch(`${BACKEND_URL}/patients/${patientId}/dashboard`);
  if (!res.ok) throw new Error("Dashboard load failed");
  return res.json();
}

export async function resetPatientProfile(patientId) {
  return fetch(`${BACKEND_URL}/patients/${patientId}/reset`, { method: "POST" });
}

export async function deletePatientProfile(patientId) {
  return fetch(`${BACKEND_URL}/patients/${patientId}`, { method: "DELETE" });
}

export async function createPatientProfile(data) {
  const res = await fetch(`${BACKEND_URL}/patients/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  return res.json();
}

export async function pingHealth() {
  return fetch(`${BACKEND_URL}/health`);
}

export async function startSessionReq(patientId) {
  const res = await fetch(`${BACKEND_URL}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patient_id: patientId })
  });
  return res.json();
}

export async function sendChatText(sessionId, patientId, message, emotion) {
  const res = await fetch(`${BACKEND_URL}/chat_text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: message,
      session_id: sessionId,
      patient_id: patientId,
      emotion: emotion
    })
  });
  return res.json();
}

export async function transcribeAudio(audioBlob) {
  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');
  const res = await fetch(`${BACKEND_URL}/transcribe`, {
    method: "POST",
    body: formData
  });
  return res.json();
}

export async function endSessionReq(sessionId, patientId) {
  return fetch(`${BACKEND_URL}/end_session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      patient_id: patientId
    })
  });
}
