export const state = {
  sessionId: null,
  patientId: localStorage.getItem("serinity_patient_id") || null,
  isListening: false,
  isVoiceMode: false,
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
  }
};
