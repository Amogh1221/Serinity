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

export async function requestSignupOtp(email, username) {
  const res = await fetch(`${BACKEND_URL}/api/auth/signup/request-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, username })
  });
  
  const data = await res.json();
  if (!res.ok) {
    if (Array.isArray(data.detail)) {
      throw new Error(data.detail[0].msg || "Validation error");
    }
    throw new Error(data.detail || "Failed to request OTP");
  }
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

export async function forgotPassword(email) {
  const res = await fetch(`${BACKEND_URL}/api/auth/forgot-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email })
  });

  const data = await res.json();
  if (!res.ok) {
    // Pydantic validation errors return detail as an array
    if (res.status === 422 || Array.isArray(data.detail)) {
      throw new Error("Enter a valid email address.");
    }
    throw new Error(data.detail || "Failed to request OTP");
  }
  return data;
}

export async function verifyOtp(email, otp_code) {
  const res = await fetch(`${BACKEND_URL}/api/auth/verify-otp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, otp_code })
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Invalid OTP");
  return data;
}

export async function resetPassword(email, otp_code, new_password) {
  const res = await fetch(`${BACKEND_URL}/api/auth/reset-password`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, otp_code, new_password })
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
export async function requestDeleteAccountOtp() {
  const token = localStorage.getItem('serinity_token');
  const res = await fetch(`${BACKEND_URL}/api/auth/delete-account/request-otp`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    }
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Failed to request OTP");
  return data;
}

export async function verifyDeleteAccount(otp_code) {
  const token = localStorage.getItem('serinity_token');
  const res = await fetch(`${BACKEND_URL}/api/auth/delete-account/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify({ otp_code })
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
