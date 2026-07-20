import { state } from './state.js';
import * as api from './api.js';
import * as ui from './ui.js';

export async function fetchPatients() {
  try {
    const patients = await api.fetchPatientsList();
    if (patients.length > 0) {
      state.patientId = patients[0].patient_id;
      await showDashboard(state.patientId);
    } else {
      // This should never happen now since the backend auto-creates a profile, but just in case:
      ui.showAlert("Profile Error", "No patient profile found. Please contact support.");
    }
  } catch (err) {
    console.error("Failed to load patient profile:", err);
  }
}

/**
 * Fetches patient dashboard data (past sessions, domains, etc.) and renders the dashboard screen.
 * 
 * @param {string} pId - The patient ID to load dashboard for.
 */
export async function showDashboard(pId) {
  try {
    const data = await api.loadDashboard(pId);
    
    document.getElementById("dashboardPatientName").textContent = data.patient.name;
    document.getElementById("dashboardPatientAge").textContent = data.patient.age ? `Age: ${data.patient.age}` : "Age: --";
    
    const list = document.getElementById("dashboardSessionsList");
    list.innerHTML = "";

    const dashStartBtn = document.getElementById("dashboardStartBtn");
    dashStartBtn.textContent = "NEW SESSION";
    
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
