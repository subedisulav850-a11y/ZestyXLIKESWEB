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
from urllib.parse import urlparse, urlencode

# =========================================================
# ZESTY LIKES CONFIGURATION
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
    "TURNSTILE_SITE_KEY", "0x4AAAAAAFLICIokx6zHNpTP"
)
TURNSTILE_SECRET_KEY = os.getenv(
    "TURNSTILE_SECRET_KEY", "0x4AAAAAAFLICCXoXBACekHvukmgiMglLwM"
)

SESSION_SECONDS = 8 * 60 * 60
MAX_BODY = 16384
COOKIE_NAME = "zesty_session"

# =========================================================
# SESSION HELPERS
# =========================================================

def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sign_session():
    payload = b64(json.dumps({
        "user": ADMIN_USER,
        "exp": int(time.time()) + SESSION_SECONDS,
        "nonce": secrets.token_hex(16)
    }, separators=(",", ":")).encode())

    signature = b64(hmac.new(
        SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).digest())

    return payload + "." + signature


def verify_session(token):
    if not token or "." not in token:
        return False

    payload, _, signature = token.partition(".")
    expected = b64(hmac.new(
        SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).digest())

    if not hmac.compare_digest(signature, expected):
        return False

    try:
        data = json.loads(unb64(payload))
        return (
            data.get("user") == ADMIN_USER
            and isinstance(data.get("exp"), int)
            and data["exp"] > int(time.time())
        )
    except Exception:
        return False


# =========================================================
# CLOUDFLARE TURNSTILE
# =========================================================

def verify_turnstile(token, ip=""):
    if not isinstance(token, str) or not token.strip():
        return False, "Missing Cloudflare verification token"

    form = {
        "secret": TURNSTILE_SECRET_KEY,
        "response": token.strip()
    }
    if ip:
        form["remoteip"] = ip

    request = urllib.request.Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=urlencode(form).encode(),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "ZestyLikes/1.0"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))

        if result.get("success") is True:
            return True, ""

        codes = result.get("error-codes", [])
        if not isinstance(codes, list):
            codes = []

        if "invalid-input-secret" in codes:
            return False, "Cloudflare secret key is invalid"
        if "timeout-or-duplicate" in codes:
            return False, "Verification expired. Please verify again"
        if "invalid-input-response" in codes:
            return False, "Verification token is invalid. Please try again"

        return False, "Cloudflare verification failed. Please try again"

    except Exception:
        return False, "Unable to contact Cloudflare. Check your configuration"


# =========================================================
# UPSTREAM LIKES API
# =========================================================

def fetch_like_api(uid, region):
    url = LIKE_API_BASE + "?" + urlencode({
        "uid": uid,
        "server_name": region,
        "key": LIKE_API_KEY
    })

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ZestyLikes/1.0"}
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return 502, {
                "error": "The likes API returned invalid JSON"
            }

        if not isinstance(data, dict):
            return 502, {
                "error": "The likes API returned an unexpected response"
            }

        return 200, data

    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read(1000).decode("utf-8", errors="replace")
        except Exception:
            detail = ""

        return 502, {
            "error": "The upstream likes API rejected the request",
            "upstream_status": exc.code,
            "details": detail[:300]
        }

    except Exception:
        return 502, {
            "error": "Could not connect to the likes API. Try again later"
        }


# =========================================================
# FRONTEND
# =========================================================

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0f1a">
<title>Zesty Likes</title>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" async defer></script>
<style>
:root{color-scheme:dark;--bg:#0b0f1a;--panel:#131826;--border:#273149;--text:#e8ecf5;--muted:#9aa6bd;--blue:#6387ff;--red:#ff8292;--green:#8ce4b4}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;padding:20px;display:grid;place-items:center;background:radial-gradient(ellipse at top,#192342,#0b0f1a 65%);color:var(--text);font-family:system-ui,-apple-system,sans-serif}
.card{width:100%;max-width:440px;padding:28px 24px;border:1px solid var(--border);border-radius:20px;background:var(--panel);box-shadow:0 20px 65px #0007}
.brand{text-align:center;margin-bottom:24px}
.logo{width:82px;height:82px;object-fit:contain;display:block;margin:0 auto 13px;border-radius:16px}
h1{font-size:25px;margin:0}
.subtitle{font-size:13px;color:var(--muted);margin-top:7px}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:20px}
.top h2{font-size:22px;margin:0}
label{display:block;margin:15px 0 7px;font-size:13px;color:var(--muted)}
input,select{width:100%;padding:13px;color:var(--text);background:#0e1422;border:1px solid var(--border);border-radius:10px;font-size:15px;outline:none}
input:focus,select:focus{border-color:var(--blue)}
button{border:0;border-radius:10px;padding:13px 15px;background:linear-gradient(130deg,#4f7cff,#865cf5);color:white;font-size:15px;font-weight:700;cursor:pointer}
button:disabled{opacity:.5;cursor:not-allowed}
.primary{width:100%;margin-top:10px;min-height:46px}
.secondary{background:#28334d;font-size:13px}
.cf{min-height:76px;display:flex;justify-content:center;align-items:center;margin:12px 0 8px;overflow:hidden}
.message{min-height:20px;margin:8px 0;color:var(--red);font-size:13px;line-height:1.5;overflow-wrap:anywhere}
.notice{color:var(--muted);font-size:12px;line-height:1.5}
.result{display:none;margin-top:18px;padding:14px;border:1px solid var(--border);border-radius:10px;background:#090e18}
.result h3{font-size:14px;margin:0 0 10px}
.result pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 monospace;color:var(--green)}
.footer{text-align:center;color:#77839c;font-size:12px;margin-top:22px}
[hidden]{display:none!important}
</style>
</head>
<body>
<main class="card">
  <header class="brand">
    <img class="logo" src="/logo.png" alt="Zesty logo"
         onerror="this.style.display='none'">
    <h1>Zesty Likes</h1>
    <div class="subtitle">Free Fire Likes Panel</div>
  </header>

  <section id="login-view">
    <form id="login-form">
      <label for="username">Username</label>
      <input id="username" autocomplete="username" required maxlength="100" placeholder="Enter username">
      <label for="password">Password</label>
      <input id="password" type="password" autocomplete="current-password" required maxlength="200" placeholder="Enter password">
      <div class="cf" id="cf-login">Loading Cloudflare verification…</div>
      <div class="message" id="login-message" role="alert"></div>
      <button class="primary" id="login-button" disabled>Complete verification</button>
    </form>
  </section>

  <section id="like-view" hidden>
    <div class="top">
      <h2>Send Likes</h2>
      <button type="button" class="secondary" id="logout-button">Logout</button>
    </div>
    <p class="notice">Enter a player UID and choose its correct server region.</p>
    <form id="like-form">
      <label for="uid">Player UID</label>
      <input id="uid" required maxlength="30" inputmode="numeric" pattern="[0-9]{1,30}" placeholder="Enter player UID">
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
      <div class="cf" id="cf-like">Loading Cloudflare verification…</div>
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
let busyLogin = false;
let busyLike = false;

function readableError(value) {
  if (typeof value === "string") return value;
  if (value instanceof Error) return value.message || "Request failed";
  if (value && typeof value === "object") {
    for (const key of ["error", "message", "detail", "details", "reason"]) {
      if (value[key] !== undefined && value[key] !== value) {
        const message = readableError(value[key]);
        if (message && message !== "[object Object]") return message;
      }
    }
    try { return JSON.stringify(value); } catch (_) {}
  }
  return String(value ?? "Request failed");
}

function message(id, value) {
  $(id).textContent = readableError(value || "");
}

async function api(path, payload) {
  const options = {
    method: payload === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers: { "Accept": "application/json" }
  };

  if (payload !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(payload);
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch (_) {
    throw new Error("Network error. Check your connection and try again.");
  }

  const raw = await response.text();
  let data;

  try {
    data = JSON.parse(raw);
  } catch (_) {
    throw new Error(
      "Server returned a non-JSON response (HTTP " + response.status +
      "). Check the Vercel deployment and function logs."
    );
  }

  if (!response.ok || data.ok === false) {
    throw new Error(readableError(data.error || data.message || data));
  }

  return data;
}

function showView(loggedIn) {
  $("login-view").hidden = loggedIn;
  $("like-view").hidden = !loggedIn;

  if (turnstileReady) {
    renderChallenge(loggedIn ? "like" : "login");
  }
}

function renderChallenge(which) {
  if (!turnstileReady || !window.turnstile) return;

  const isLogin = which === "login";
  if (isLogin && loginWidget !== null) return;
  if (!isLogin && likeWidget !== null) return;

  const target = $(isLogin ? "cf-login" : "cf-like");
  target.textContent = "";

  const id = turnstile.render(target, {
    sitekey: SITE_KEY,
    theme: "dark",
    callback: token => {
      if (isLogin) {
        loginToken = token;
        $("login-button").disabled = false;
        $("login-button").textContent = "Login";
        message("login-message", "");
      } else {
        likeToken = token;
        $("like-button").disabled = false;
        $("like-button").textContent = "Send Likes";
        message("like-message", "");
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
        message("login-message", "Cloudflare failed to load or verify. Retry.");
      } else {
        likeToken = "";
        $("like-button").disabled = true;
        message("like-message", "Cloudflare failed to load or verify. Retry.");
      }
    }
  });

  if (isLogin) loginWidget = id;
  else likeWidget = id;
}

function resetChallenge(which) {
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

$("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (busyLogin) return;

  if (!loginToken) {
    message("login-message", "Complete Cloudflare verification first.");
    return;
  }

  busyLogin = true;
  $("login-button").disabled = true;
  $("login-button").textContent = "Signing in…";
  message("login-message", "");

  try {
    await api("/api/login", {
      username: $("username").value.trim(),
      password: $("password").value,
      turnstile_token: loginToken
    });

    $("password").value = "";
    showView(true);
    resetChallenge("like");
  } catch (error) {
    message("login-message", error);
  } finally {
    busyLogin = false;
    resetChallenge("login");
  }
});

$("like-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (busyLike) return;

  if (!likeToken) {
    message("like-message", "Complete Cloudflare verification first.");
    return;
  }

  busyLike = true;
  $("like-button").disabled = true;
  $("like-button").textContent = "Processing…";
  $("result").style.display = "none";
  message("like-message", "");

  try {
    const result = await api("/api/like", {
      uid: $("uid").value.trim(),
      region: $("region").value,
      turnstile_token: likeToken
    });

    $("result-data").textContent = JSON.stringify(result.data, null, 2);
    $("result").style.display = "block";
  } catch (error) {
    message("like-message", error);
    if (readableError(error).toLowerCase().includes("login required")) {
      showView(false);
    }
  } finally {
    busyLike = false;
    resetChallenge("like");
  }
});

$("logout-button").addEventListener("click", async () => {
  try {
    await api("/api/logout", {});
  } catch (_) {}
  showView(false);
  resetChallenge("login");
  message("login-message", "You have been logged out.");
});

async function initialize() {
  try {
    const result = await api("/api/me");
    showView(result.authenticated === true);
  } catch (_) {
    showView(false);
  }
}

function waitForTurnstile() {
  if (window.turnstile) {
    turnstileReady = true;
    renderChallenge($("login-view").hidden ? "like" : "login");
    return;
  }
  setTimeout(waitForTurnstile, 200);
}

initialize();
waitForTurnstile();
</script>
</body>
</html>
"""

# =========================================================
# VERCEL PYTHON HANDLER
# =========================================================

class handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Do not log passwords, cookies, or request bodies.
        print("Zesty Likes:", fmt % args)

    def send_response_bytes(self, status, content, content_type, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
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
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        if content:
            self.wfile.write(content)

    def send_json(self, status, data, headers=None):
        self.send_response_bytes(
            status,
            json.dumps(data, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            headers
        )

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            return None

        if length <= 0 or length > MAX_BODY:
            return None

        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def get_cookie(self):
        for item in self.headers.get("Cookie", "").split(";"):
            name, sep, value = item.strip().partition("=")
            if sep and name == COOKIE_NAME:
                return value
        return ""

    def is_logged_in(self):
        return verify_session(self.get_cookie())

    def client_ip(self):
        return self.client_address[0] if self.client_address else ""

    def session_headers(self):
        value = sign_session()
        return {
            "Set-Cookie": (
                f"{COOKIE_NAME}={value}; Path=/; HttpOnly; Secure; "
                f"SameSite=Lax; Max-Age={SESSION_SECONDS}"
            )
        }

    def expired_cookie_headers(self):
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
            self.send_response_bytes(200, page, "text/html; charset=utf-8")
            return

        if path == "/api/me":
            self.send_json(200, {
                "ok": True,
                "authenticated": self.is_logged_in()
            })
            return

        self.send_json(404, {"ok": False, "error": "Route not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.read_json()

        if body is None:
            self.send_json(400, {
                "ok": False,
                "error": "Request body must be valid JSON and under 16 KB"
            })
            return

        if path == "/api/login":
            self.login(body)
        elif path == "/api/like":
            self.send_like(body)
        elif path == "/api/logout":
            self.send_json(
                200,
                {"ok": True, "message": "Logged out"},
                self.expired_cookie_headers()
            )
        else:
            self.send_json(404, {"ok": False, "error": "Route not found"})

    def login(self, body):
        username = body.get("username")
        password = body.get("password")
        token = body.get("turnstile_token")

        if not isinstance(username, str) or not isinstance(password, str):
            self.send_json(400, {
                "ok": False,
                "error": "Username and password are required"
            })
            return

        verified, reason = verify_turnstile(token, self.client_ip())
        if not verified:
            self.send_json(400, {"ok": False, "error": reason})
            return

        username_ok = hmac.compare_digest(username, ADMIN_USER)
        password_ok = hmac.compare_digest(password, ADMIN_PASS)

        if not (username_ok and password_ok):
            self.send_json(401, {
                "ok": False,
                "error": "Invalid username or password"
            })
            return

        self.send_json(
            200,
            {"ok": True, "message": "Login successful"},
            self.session_headers()
        )

    def send_like(self, body):
        if not self.is_logged_in():
            self.send_json(401, {
                "ok": False,
                "error": "Login required. Please sign in again."
            })
            return

        uid = body.get("uid")
        region = body.get("region")
        token = body.get("turnstile_token")

        if not isinstance(uid, str) or not uid.isdigit() or not 1 <= len(uid) <= 30:
            self.send_json(400, {
                "ok": False,
                "error": "Enter a valid numeric player UID"
            })
            return

        regions = {
            "BD", "IND", "PK", "SG", "ID", "ME",
            "VN", "TH", "TW", "EU", "RU"
        }
        if not isinstance(region, str) or region not in regions:
            self.send_json(400, {
                "ok": False,
                "error": "Select a supported region"
            })
            return

        verified, reason = verify_turnstile(token, self.client_ip())
        if not verified:
            self.send_json(400, {"ok": False, "error": reason})
            return

        status, data = fetch_like_api(uid, region)
        if status != 200:
            self.send_json(status, {"ok": False, **data})
            return

        self.send_json(200, {"ok": True, "data": data})
