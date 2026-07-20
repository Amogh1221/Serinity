export const state = {
  sessionId: sessionStorage.getItem("serinity_session_id") || null,
  patientId: localStorage.getItem("serinity_patient_id") || null,
  isListening: false,
  isRecordingPending: false,
  isVoiceMode: false,
  isAudioOutputEnabled: false,
  isAISpeaking: false,
  exchangeCount: 0,
  sessionStartTime: null,
  sessionInterval: null,
  
  setPatientId(id) {
    this.patientId = id;
    if (id) {
      localStorage.setItem("serinity_patient_id", id);
    } else {
      localStorage.removeItem("serinity_patient_id");
    }
  },
  
  setSessionId(id) {
    this.sessionId = id;
    if (id) {
      sessionStorage.setItem("serinity_session_id", id);
    } else {
      sessionStorage.removeItem("serinity_session_id");
    }
  }
};
