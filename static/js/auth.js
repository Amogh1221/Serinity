import { BACKEND_URL } from './api.js';

export async function login(username, password) {
  const res = await fetch(`${BACKEND_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Login failed");
  }

  localStorage.setItem('serinity_token', data.access_token);
  return data;
}



export async function signup(payload) {
  const res = await fetch(`${BACKEND_URL}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  const data = await res.json();
  if (!res.ok) {
    if (Array.isArray(data.detail)) {
      throw new Error(data.detail[0].msg || "Validation error");
    }
    throw new Error(data.detail || "Signup failed");
  }

  localStorage.setItem('serinity_token', data.access_token);
  return data;
}

export async function resetPassword(email, new_password) {
  const res = await fetch(`${BACKEND_URL}/api/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, new_password })
  });

  const data = await res.json();
  if (!res.ok) {
    if (Array.isArray(data.detail)) {
      throw new Error(data.detail[0].msg || "Validation error");
    }
    throw new Error(data.detail || "Failed to reset password");
  }
  return data;
}

export async function deleteAccount() {
  const token = localStorage.getItem('serinity_token');
  const res = await fetch(`${BACKEND_URL}/api/auth/delete-account`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    }
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to delete account");
  return data;
}

export function logout() {
  localStorage.removeItem('serinity_token');
}

export function isAuthenticated() {
  return !!localStorage.getItem('serinity_token');
}
