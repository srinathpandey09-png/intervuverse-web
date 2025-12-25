
// auth.js - very simple client-side demo for login/register (no security, demo only)
async function registerUser() {
  const name = document.getElementById("reg_name").value;
  const email = document.getElementById("reg_email").value;
  const pass = document.getElementById("reg_password").value;
  const res = await fetch("/api/register", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({name,email,pass})});
  const j = await res.json();
  alert(j.message);
}
async function loginUser() {
  const email = document.getElementById("login_email").value;
  const pass = document.getElementById("login_password").value;
  const res = await fetch("/api/login", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({email,pass})});
  const j = await res.json();
  if (j.success) location.href="/dashboard";
  else alert(j.message);
}
