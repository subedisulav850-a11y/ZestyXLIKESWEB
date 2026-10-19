import os
import json
import time
import hmac
import hashlib
import base64
import secrets
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode

# =========================================================
# ZESTY LIKES CONFIGURATION
# Keep your original defaults. Set production secrets in
# Vercel -> Settings -> Environment Variables.
# =========================================================

ADMIN_USER = os.getenv("ADMIN_USER", "Zesty")
ADMIN_PASS = os.getenv("ADMIN_PASS", "676767")

SESSION_SECRET = os.getenv(
    "SESSION_SECRET",
    "super-secret-zesty-key-change-me-if-you-want"
)

LIKE_API_BASE = "https://zesty220likes.vercel.app/like"
LIKE_API_KEY = os.getenv("LIKE_API_KEY", "SulavOp")

TURNSTILE_SITE_KEY = os.getenv(
    "TURNSTILE_SITE_KEY",
    "0x4AAAAAAFLICIokx6zHNpTP"
)
TURNSTILE_SECRET_KEY = os.getenv(
    "TURNSTILE_SECRET_KEY",
    "0x4AAAAAAFLICCXoXBACekHvukmgiMglLwM"
)

SESSION_SECONDS = 8 * 60 * 60
MAX_BODY = 16384
COOKIE_NAME = "zesty_session"

# =========================================================
# HTML FRONTEND
# /logo.png is served from the root-level public directory.
# =========================================================

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0e17">
<title>Zesty Likes</title>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" async defer></script>
<style>
:root{
  color-scheme:dark;
  --bg:#090c14;--panel:#111725;--border:#273149;
  --text:#eef2ff;--muted:#99a6c0;--blue:#6688ff;
  --danger:#ff7185;--green:#7de2b0;
}
*{box-sizing:border-box}
body{
  margin:0;min-height:100vh;padding:22px;display:grid;place-items:center;
  background:radial-gradient(ellipse at top,#1a2545 0%,#0b101c 48%,#080b12 100%);
  color:var(--text);font-family:Inter,system-ui,-apple-system,sans-serif;
}
.card{
  width:100%;max-width:440px;padding:28px 24px;
  border:1px solid var(--border);border-radius:20px;
  background:rgba(17,23,37,.96);box-shadow:0 24px 80px #0007;
}
.brand{text-align:center;margin-bottom:24px}
.logo{
  width:82px;height:82px;object-fit:contain;display:block;
  margin:0 auto 13px;border-radius:18px;
}
h1{font-size:25px;letter-spacing:-.5px;margin:0}
.subtitle{font-size:13px;color:var(--muted);margin-top:7px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:20px}
.top h2{font-size:22px;margin:0}
label{display:block;font-size:13px;color:var(--muted);margin:15px 0 7px}
input,select{
  width:100%;padding:13px 14px;border:1px solid var(--border);
  border-radius:11px;background:#0b111e;color:var(--text);font-size:15px;
  outline:none;
}
input:focus,select:focus{border-color:var(--blue);box-shadow:0 0 0 3px #6688ff20}
button{
  border:0;border-radius:11px;padding:12px 15px;
  background:linear-gradient(130deg,#4d7cff,#835cf6);
  color:white;font-weight:700;font-size:14px;cursor:pointer;
}
button:disabled{opacity:.5;cursor:not-allowed}
.primary{width:100%;min-height:46px;margin-top:10px}
.secondary{background:#27334c}
.cf{min-height:76px;display:flex;align-items:center;justify-content:center;
    margin:12px 0 7px;overflow:hidden}
.message{font-size:13px;line-height:1.5;min-height:20px;margin:8px 0;color:var(--danger);overflow-wrap:anywhere}
.result{
  display:none;margin-top:18px;padding:14px;border:1px solid var(--border);
  border-radius:12px;background:#0a101b;
}
.result h3{font-size:14px;margin:0 0 10px}
.result pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.6;color:var(--green)}
.footer{text-align:center;color:#77839c;font-size:12px;margin-top:22px}
.small{font-size:12px;color:var(--muted);line-height:1.5}
[hidden]{display:none!important}
@media(max-width:380px){.card{padding:23px 17px}.cf{justify-content:flex-start}}
</style>
</head>
<body>
<main class="card">
  <div class="brand">
    <img class="logo" src="/logo.png" alt="Zesty logo"
         onerror="this.style.display='none'">
    <h1>Zesty Likes</h1>
    <div class="subtitle">Free Fire Likes Panel</div>
  </div>

  <section id="login-view">
    <form id="login-form">
      <label for="username">Username</label>
      <input id="username" autocomplete="username" required maxlength="100"
             placeholder="Enter username">
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password"
             required maxlength="200" placeholder="Enter password">
      <div class="cf" id="cf-login">Loading human verification…</div>
      <div class="message" id="login-message" role="alert"></div>
      <button class="primary" id="login-button" disabled>Complete verification</button>
    </form>
  </section>

  <section id="like-view" hidden>
    <div class="top">
      <h2>Send Likes</h2>
      <button type="button" class="secondary" id="logout-button">Logout</button>
    </div>
    <p class="small">Enter a player UID and the correct server region.</p>
    <form id="like-form">
      <label for="uid">Player UID</label>
      <input id="uid" required maxlength="30" inputmode="numeric"
             pattern="[0-9]{1,30}" placeholder="Enter player UID">
      <label for="region">Server region</label>
      <select id="region" required>
        <option value="">Select region</option>
        <option value="BD">BD — Bangladesh</option>
        <option value="IND">IND — India</option>
        <option value="PK">PK — Pakistan</option>
        <option value="SG">SG — Singapore</option>
        <option value="ID">ID — Indonesia</option>
        <option value="ME">ME — Middle East</option>
        <option value="VN">VN — Vietnam</option>
        <option value="TH">TH — Thailand</option>
        <option value="TW">TW — Taiwan</option>
        <option value="EU">EU — Europe</option>
        <option value="RU">RU — Russia</option>
      </select>
      <div class="cf" id="cf-like">Loading human verification…</div>
      <div class="message" id="like-message" role="alert"></div>
      <button class="primary" id="like-button" disabled>Complete verification</button>
    </form>
    <div class="result" id="result">
      <h3>API Response</h3>
      <pre id="result-data"></pre>
    </div>
  </section>

  <div class="footer">Protected by Cloudflare Turnstile</div>
</main>

<script>
"use strict";

const SITE_KEY = "__TURNSTILE_SITE_KEY__";
const $ = id => document.getElementById(id);

let turnstileReady = false;
let loginWidget = null;
let likeWidget = null;
let loginToken = "";
let likeToken = "";
let sendingLogin = false;
let sendingLike = false;

function setMessage(id, text) {
  $(id).textContent = text || "";
}

function showView(isLoggedIn) {
  $("login-view").hidden = isLoggedIn;
  $("like-view").hidden = !isLoggedIn;

  if (turnstileReady) {
    if (isLoggedIn) renderWidget("like");
    else renderWidget("login");
  }
}

function renderWidget(which) {
  if (!turnstileReady || !window.turnstile) return;

  const isLogin = which === "login";
  if (isLogin && loginWidget !== null) return;
  if (!isLogin && likeWidget !== null) return;

  const target = isLogin ? $("cf-login") : $("cf-like");
  target.textContent = "";

  const id = turnstile.render(target, {
    sitekey: SITE_KEY,
    theme: "dark",
    callback: token => {
      if (isLogin) {
        loginToken = token;
        $("login-button").disabled = false;
        $("login-button").textContent = "Login";
        setMessage("login-message", "");
      } else {
        likeToken = token;
        $("like-button").disabled = false;
        $("like-button").textContent = "Send Likes";
        setMessage("like-message", "");
      }
    },
    "expired-callback": () => {
      if (isLogin) {
        loginToken = "";
        $("login-button").disabled = true;
        $("login-button").textContent = "Verify again";
      } else {
        likeToken = "";
        $("like-button").disabled = true;
        $("like-button").textContent = "Verify again";
      }
    },
    "error-callback": () => {
      if (isLogin) {
        loginToken = "";
        $("login-button").disabled = true;
        setMessage("login-message", "Cloudflare verification failed. Please retry.");
      } else {
        likeToken = "";
        $("like-button").disabled = true;
        setMessage("like-message", "Cloudflare verification failed. Please retry.");
      }
    }
  });

  if (isLogin) loginWidget = id;
  else likeWidget = id;
}

function resetWidget(which) {
  if (!turnstileReady || !window.turnstile) return;

  if (which === "login") {
    loginToken = "";
    $("login-button").disabled = true;
    $("login-button").textContent = "Complete verification";
    if (loginWidget !== null) turnstile.reset(loginWidget);
  } else {
    likeToken = "";
    $("like-button").disabled = true;
    $("like-button").textContent = "Complete verification";
    if (likeWidget !== null) turnstile.reset(likeWidget);
  }
}

async function api(path, body) {
  const options = {
    method: body ? "POST" : "GET",
    credentials: "same-origin",
    headers: { "Accept": "application/json" }
  };
  if (body) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); }
  catch (_) { throw new Error("The server returned an invalid response."); }

  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "Request failed.");
  }
  return data;
}

$("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (sendingLogin) return;

  if (!loginToken) {
    setMessage("login-message", "Complete Cloudflare verification first.");
    return;
  }

  sendingLogin = true;
  $("login-button").disabled = true;
  $("login-button").textContent = "Signing in…";
  setMessage("login-message", "");

  try {
    await api("/api/login", {
      username: $("username").value.trim(),
      password: $("password").value,
      turnstile_token: loginToken
    });
    $("password").value = "";
    showView(true);
    resetWidget("like");
  } catch (error) {
    setMessage("login-message", error.message);
  } finally {
    sendingLogin = false;
    resetWidget("login");
  }
});

$("like-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (sendingLike) return;

  if (!likeToken) {
    setMessage("like-message", "Complete Cloudflare verification first.");
    return;
  }

  sendingLike = true;
  $("like-button").disabled = true;
  $("like-button").textContent = "Processing…";
  $("result").style.display = "none";
  setMessage("like-message", "");

  try {
    const data = await api("/api/like", {
      uid: $("uid").value.trim(),
      region: $("region").value,
      turnstile_token: likeToken
    });

    $("result-data").textContent = JSON.stringify(data.data, null, 2);
    $("result").style.display = "block";
  } catch (error) {
    setMessage("like-message", error.message);

    if (error.message.toLowerCase().includes("login")) {
      showView(false);
    }
  } finally {
    sendingLike = false;
    resetWidget("like");
  }
});

$("logout-button").addEventListener("click", async () => {
  try { await api("/api/logout", {}); } catch (_) {}
  showView(false);
  resetWidget("login");
  setMessage("login-message", "You have been logged out.");
});

async function initialize() {
  try {
    const data = await api("/api/me");
    showView(Boolean(data.authenticated));
  } catch (_) {
    showView(false);
  }
}

function waitForTurnstile() {
  if (window.turnstile) {
    turnstileReady = true;
    renderWidget($("login-view").hidden ? "like" : "login");
    return;
  }
  setTimeout(waitForTurnstile, 150);
}

initialize();
waitForTurnstile();
</script>
</body>
</html>
"""

# =========================================================
# SERVERLESS REQUEST HANDLER
# =========================================================

def json_bytes(data):
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Avoid logging credentials or request bodies.
        print("%s - %s" % (self.client_address[0], fmt % args))

    def send_bytes(self, status, content, content_type, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline' https://challenges.cloudflare.com; "
            "frame-src https://challenges.cloudflare.com; "
            "connect-src 'self' https://challenges.cloudflare.com; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if content:
            self.wfile.write(content)

    def send_json(self, status, data, extra_headers=None):
        self.send_bytes(
            status,
            json_bytes(data),
            "application/json; charset=utf-8",
            extra_headers
        )

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None

        if length < 1 or length > MAX_BODY:
            return None

        try:
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def cookie_value(self):
        raw = self.headers.get("Cookie", "")
        for item in raw.split(";"):
            name, sep, value = item.strip().partition("=")
            if sep and name == COOKIE_NAME:
                return value
        return ""

    def authenticated(self):
        return verify_session(self.cookie_value())

    def client_ip(self):
        # Use the socket peer, not arbitrary X-Forwarded-For input.
        return self.client_address[0] if self.client_address else ""

    def set_session_cookie(self):
        token = sign_session()
        # Vercel serves the production site over HTTPS.
        cookie = (
            f"{COOKIE_NAME}={token}; Path=/; HttpOnly; Secure; "
            f"SameSite=Lax; Max-Age={SESSION_SECONDS}"
        )
        return {"Set-Cookie": cookie}

    def clear_session_cookie(self):
        return {
            "Set-Cookie": (
                f"{COOKIE_NAME}=; Path=/; HttpOnly; Secure; "
                "SameSite=Lax; Max-Age=0"
            )
        }

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            page = HTML.replace(
                "__TURNSTILE_SITE_KEY__", TURNSTILE_SITE_KEY
            ).encode("utf-8")
            self.send_bytes(200, page, "text/html; charset=utf-8")
            return

        if path == "/api/me":
            self.send_json(200, {
                "ok": True,
                "authenticated": self.authenticated()
            })
            return

        self.send_json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.read_json()

        if body is None:
            self.send_json(400, {
                "ok": False,
                "error": "Invalid or oversized JSON request"
            })
            return

        if path == "/api/login":
            self.handle_login(body)
        elif path == "/api/like":
            self.handle_like(body)
        elif path == "/api/logout":
            self.send_json(
                200,
                {"ok": True, "message": "Logged out"},
                self.clear_session_cookie()
            )
        else:
            self.send_json(404, {"ok": False, "error": "Not found"})

    def handle_login(self, body):
        username = body.get("username")
        password = body.get("password")
        token = body.get("turnstile_token")

        if not isinstance(username, str) or not isinstance(password, str):
            self.send_json(400, {"ok": False, "error": "Enter username and password"})
            return

        if not isinstance(token, str) or not verify_turnstile(
            token, self.client_ip()
        ):
            self.send_json(400, {
                "ok": False,
                "error": "Cloudflare verification failed. Please verify again."
            })
            return

        user_ok = hmac.compare_digest(username, ADMIN_USER)
        pass_ok = hmac.compare_digest(password, ADMIN_PASS)

        if not (user_ok and pass_ok):
            self.send_json(401, {
                "ok": False,
                "error": "Invalid username or password"
            })
            return

        self.send_json(
            200,
            {"ok": True, "message": "Login successful"},
            self.set_session_cookie()
        )

    def handle_like(self, body):
        if not self.authenticated():
            self.send_json(401, {
                "ok": False,
                "error": "Login required. Please sign in again."
            })
            return

        uid = body.get("uid")
        region = body.get("region")
        token = body.get("turnstile_token")

        if not isinstance(uid, str) or not uid.isdigit() or not (1 <= len(uid) <= 30):
            self.send_json(400, {"ok": False, "error": "Enter a valid numeric UID"})
            return

        allowed_regions = {
            "BD", "IND", "PK", "SG", "ID", "ME",
            "VN", "TH", "TW", "EU", "RU"
        }
        if not isinstance(region, str) or region not in allowed_regions:
            self.send_json(400, {"ok": False, "error": "Choose a valid region"})
            return

        if not isinstance(token, str) or not verify_turnstile(
            token, self.client_ip()
        ):
            self.send_json(400, {
                "ok": False,
                "error": "Cloudflare verification failed. Please verify again."
            })
            return

        status, result = fetch_like_api(uid, region)
        if status != 200:
            self.send_json(status, {"ok": False, **result})
            return

        self.send_json(200, {"ok": True, "data": result})


# Vercel discovers the `handler` class as its Python function entry point.
            
