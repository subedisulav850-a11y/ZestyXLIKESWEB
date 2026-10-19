#ade by zesty
import os
import json
import time
import hmac
import hashlib
import base64
import secrets
import logging
import socket
import urllib.request
import urllib.error

from pathlib import Path
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

# New upstream API. These values are used server-side only.
LIKE_API_BASE = "https://www.silent-codex-api.shop/like"
LIKE_API_KEY = os.getenv("LIKE_API_KEY", "SULAV")

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
API_TIMEOUT = 20

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("zesty-likes")

# Your logo is located at api/public/logo.png
LOGO_PATH = Path(__file__).resolve().parent / "public" / "logo.png"


# =========================================================
# SESSION HELPERS
# =========================================================

def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64(value):
    return base64.urlsafe_b64decode(
        value + "=" * (-len(value) % 4)
    )


def sign_session():
    payload = b64(json.dumps({
        "user": ADMIN_USER,
        "exp": int(time.time()) + SESSION_SECONDS,
        "nonce": secrets.token_hex(16)
    }, separators=(",", ":")).encode("utf-8"))

    signature = b64(hmac.new(
        SESSION_SECRET.encode("utf-8"),
        payload.encode("ascii"),
        hashlib.sha256
    ).digest())

    return payload + "." + signature


def verify_session(token):
    if not token or "." not in token:
        return False

    payload, _, signature = token.partition(".")
    expected = b64(hmac.new(
        SESSION_SECRET.encode("utf-8"),
        payload.encode("ascii"),
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
# CLOUDFLARE TURNSTILE VERIFICATION
# =========================================================

def verify_turnstile(token, ip=""):
    if not isinstance(token, str) or not token.strip():
        return False, "Complete Cloudflare verification first."

    form = {
        "secret": TURNSTILE_SECRET_KEY,
        "response": token.strip()
    }

    if ip:
        form["remoteip"] = ip

    request = urllib.request.Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=urlencode(form).encode("utf-8"),
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

        log.warning("Turnstile verification rejected: %s", codes)

        if "invalid-input-secret" in codes:
            return False, "Cloudflare secret key is invalid."
        if "timeout-or-duplicate" in codes:
            return False, "Verification expired. Please verify again."
        if "invalid-input-response" in codes:
            return False, "Invalid verification token. Please retry."

        return False, "Cloudflare verification failed. Please retry."

    except Exception:
        log.exception("Turnstile verification request failed")
        return False, "Could not verify with Cloudflare. Please retry."


# =========================================================
# UPSTREAM LIKES API
# =========================================================

def fetch_like_api(uid, region):
    # The key is added only server-side and never sent to browser JS.
    query = urlencode({
        "uid": uid,
        "server_name": region,
        "key": LIKE_API_KEY
    })

    url = LIKE_API_BASE + "?" + query

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ZestyLikes/1.0"
        },
        method="GET"
    )

    try:
        with urllib.request.urlopen(request, timeout=API_TIMEOUT) as response:
            raw = response.read(1024 * 1024 + 1)

        if len(raw) > 1024 * 1024:
            return 502, {"error": "The likes API response was too large."}

        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            log.error("Likes API returned non-JSON data")
            return 502, {
                "error": "The likes API returned an invalid response."
            }

        if not isinstance(result, (dict, list)):
            return 502, {
                "error": "The likes API returned an unexpected response."
            }

        # The new API may return a list containing one result.
        return 200, result

    except urllib.error.HTTPError as exc:
        # Do not expose upstream URLs, query strings, or API keys.
        log.warning("Likes API HTTP status: %s", exc.code)

        if exc.code in (401, 403):
            return 502, {
                "error": "The likes API rejected its server credentials."
            }

        if exc.code == 429:
            return 502, {
                "error": "The likes API rate limit was reached. Try later."
            }

        return 502, {
            "error": "The likes API returned an HTTP error. Try again later."
        }

    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        log.error(
            "Likes API connection error: %s",
            type(reason).__name__ if reason is not None else "unknown"
        )

        if isinstance(reason, (socket.timeout, TimeoutError)):
            return 504, {
                "error": "The likes API timed out. Please try again."
            }

        return 502, {
            "error": "Could not reach the likes API. Check the API host or try later."
        }

    except (TimeoutError, socket.timeout):
        log.warning("Likes API request timed out")
        return 504, {
            "error": "The likes API timed out. Please try again."
        }

    except Exception:
        log.exception("Unexpected likes API failure")
        return 502, {
            "error": "The likes API request failed. Please try again later."
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
:root{color-scheme:dark;--border:#273149;--text:#edf1ff;--muted:#9aa6bd;--blue:#6688ff;--red:#ff8193;--green:#91e8ba}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;padding:20px;display:grid;place-items:center;background:radial-gradient(ellipse at top,#1b2648,#0b0f1a 65%);color:var(--text);font-family:system-ui,-apple-system,sans-serif}
.card{width:100%;max-width:440px;padding:28px 24px;border:1px solid var(--border);border-radius:20px;background:#131826;box-shadow:0 22px 70px #0007}
.brand{text-align:center;margin-bottom:25px}
.logo{width:84px;height:84px;object-fit:contain;display:block;margin:0 auto 13px;border-radius:16px}
h1{font-size:25px;margin:0;letter-spacing:-.4px}
.subtitle{font-size:13px;color:var(--muted);margin-top:7px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px}
.top h2{font-size:22px;margin:0}
label{display:block;margin:15px 0 7px;font-size:13px;color:var(--muted)}
input,select{width:100%;padding:13px 14px;border:1px solid var(--border);border-radius:10px;background:#0b111e;color:var(--text);font-size:15px;outline:none}
input:focus,select:focus{border-color:var(--blue);box-shadow:0 0 0 3px #6688ff20}
button{border:0;border-radius:10px;padding:13px 15px;background:linear-gradient(130deg,#4f7cff,#865cf5);color:white;font-size:14px;font-weight:700;cursor:pointer}
button:disabled{opacity:.48;cursor:not-allowed}
.primary{width:100%;min-height:46px;margin-top:10px}
.secondary{background:#28334d}
.cf{min-height:76px;display:flex;align-items:center;justify-content:center;margin:12px 0 8px;overflow:hidden}
.message{min-height:20px;margin:8px 0;color:var(--red);font-size:13px;line-height:1.5;overflow-wrap:anywhere}
.note{font-size:12px;line-height:1.5;color:var(--muted)}
.result{display:none;margin-top:18px;padding:14px;border:1px solid var(--border);border-radius:11px;background:#090e18}
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
<p class="note">Enter the player UID and select the correct region.</p>
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

let ready = false;
let loginWidget = null;
let likeWidget = null;
let loginToken = "";
let likeToken = "";
let loginBusy = false;
let likeBusy = false;

function readableError(value) {
  if (typeof value === "string") return value;
  if (value instanceof Error) return value.message || "Request failed";
  if (value && typeof value === "object") {
    for (const key of ["error", "message", "detail", "details"]) {
      if (value[key] !== undefined && value[key] !== null) {
        const text = readableError(value[key]);
        if (text && text !== "[object Object]") return text;
      }
    }
    try { return JSON.stringify(value); } catch (_) {}
  }
  return String(value ?? "Request failed");
}

function setMessage(id, value) {
  $(id).textContent = value ? readableError(value) : "";
}

async function api(path, payload) {
  const options = {
    method: payload === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers: {"Accept": "application/json"}
  };

  if (payload !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(payload);
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch (_) {
    throw new Error("Network connection failed. Refresh and try again.");
  }

  const raw = await response.text();
  let data;

  try {
    data = JSON.parse(raw);
  } catch (_) {
    throw new Error(
      "Server returned an invalid response (HTTP " + response.status +
      "). Check the Vercel function logs."
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
  if (ready) renderChallenge(loggedIn ? "like" : "login");
}

function renderChallenge(which) {
  if (!ready || !window.turnstile) return;
  const isLogin = which === "login";

  if (isLogin && loginWidget !== null) return;
  if (!isLogin && likeWidget !== null) return;

  const target = $(isLogin ? "cf-login" : "cf-like");
  target.textContent = "";

  const widget = turnstile.render(target, {
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
        setMessage("login-message", "Cloudflare verification failed. Retry.");
      } else {
        likeToken = "";
        $("like-button").disabled = true;
        setMessage("like-message", "Cloudflare verification failed. Retry.");
      }
    }
  });

  if (isLogin) loginWidget = widget;
  else likeWidget = widget;
}

function resetChallenge(which) {
  if (!ready || !window.turnstile) return;

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
  if (loginBusy) return;

  if (!loginToken) {
    setMessage("login-message", "Complete Cloudflare verification first.");
    return;
  }

  loginBusy = true;
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
    resetChallenge("like");
  } catch (error) {
    setMessage("login-message", error);
  } finally {
    loginBusy = false;
    resetChallenge("login");
  }
});

$("like-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (likeBusy) return;

  if (!likeToken) {
    setMessage("like-message", "Complete Cloudflare verification first.");
    return;
  }

  likeBusy = true;
  $("like-button").disabled = true;
  $("like-button").textContent = "Processing…";
  $("result").style.display = "none";
  setMessage("like-message", "");

  try {
    const result = await api("/api/like", {
      uid: $("uid").value.trim(),
      region: $("region").value,
      turnstile_token: likeToken
    });

    $("result-data").textContent = JSON.stringify(result.data, null, 2);
    $("result").style.display = "block";
  } catch (error) {
    setMessage("like-message", error);
    if (readableError(error).toLowerCase().includes("login required")) {
      showView(false);
    }
  } finally {
    likeBusy = false;
    resetChallenge("like");
  }
});

$("logout-button").addEventListener("click", async () => {
  try {
    await api("/api/logout", {});
  } catch (_) {}
  showView(false);
  resetChallenge("login");
  setMessage("login-message", "You have been logged out.");
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
    ready = true;
    renderChallenge($("login-view").hidden ? "like" : "login");
  } else {
    setTimeout(waitForTurnstile, 200);
  }
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
        # Never log passwords, cookies, or full API query strings.
        log.info(fmt, *args)

    def send_bytes(self, status, content, content_type, extra=None):
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

        if extra:
            for key, value in extra.items():
                self.send_header(key, value)

        self.end_headers()
        if content:
            self.wfile.write(content)

    def send_json(self, status, data, extra=None):
        content = json.dumps(
            data, ensure_ascii=False
        ).encode("utf-8")
        self.send_bytes(
            status, content, "application/json; charset=utf-8", extra
        )

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            return None

        if length <= 0 or length > MAX_BODY:
            return None

        try:
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def cookie(self):
        for part in self.headers.get("Cookie", "").split(";"):
            name, sep, value = part.strip().partition("=")
            if sep and name == COOKIE_NAME:
                return value
        return ""

    def logged_in(self):
        return verify_session(self.cookie())

    def client_ip(self):
        return self.client_address[0] if self.client_address else ""

    def session_headers(self):
        return {
            "Set-Cookie": (
                f"{COOKIE_NAME}={sign_session()}; Path=/; HttpOnly; "
                "Secure; SameSite=Lax; Max-Age=" + str(SESSION_SECONDS)
            )
        }

    def clear_cookie_headers(self):
        return {
            "Set-Cookie": (
                f"{COOKIE_NAME}=; Path=/; HttpOnly; Secure; "
                "SameSite=Lax; Max-Age=0"
            )
        }

    def do_GET(self):
        path = urlparse(self.path).path

        # Serve the existing logo at api/public/logo.png as /logo.png.
        if path in ("/logo.png", "/api/public/logo.png"):
            try:
                content = LOGO_PATH.read_bytes()
                if len(content) > 2 * 1024 * 1024:
                    raise ValueError("Logo exceeds size limit")
                self.send_bytes(200, content, "image/png")
            except FileNotFoundError:
                self.send_json(404, {
                    "ok": False,
                    "error": "Logo file missing: api/public/logo.png"
                })
            except Exception:
                log.exception("Could not load logo")
                self.send_json(500, {
                    "ok": False,
                    "error": "Could not load the website logo."
                })
            return

        if path == "/":
            page = HTML.replace(
                "__TURNSTILE_SITE_KEY__", TURNSTILE_SITE_KEY
            ).encode("utf-8")
            self.send_bytes(200, page, "text/html; charset=utf-8")
            return

        if path == "/api/me":
            self.send_json(200, {
                "ok": True,
                "authenticated": self.logged_in()
            })
            return

        self.send_json(404, {"ok": False, "error": "Route not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.read_json()

        if body is None:
            self.send_json(400, {
                "ok": False,
                "error": "Invalid JSON request or request body too large."
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
                self.clear_cookie_headers()
            )
        else:
            self.send_json(404, {"ok": False, "error": "Route not found"})

    def login(self, body):
        username = body.get("username")
        password = body.get("password")

        if not isinstance(username, str) or not isinstance(password, str):
            self.send_json(400, {
                "ok": False,
                "error": "Enter your username and password."
            })
            return

        ok, reason = verify_turnstile(
            body.get("turnstile_token"), self.client_ip()
        )
        if not ok:
            self.send_json(400, {"ok": False, "error": reason})
            return

        user_ok = hmac.compare_digest(username, ADMIN_USER)
        pass_ok = hmac.compare_digest(password, ADMIN_PASS)

        if not (user_ok and pass_ok):
            self.send_json(401, {
                "ok": False,
                "error": "Invalid username or password."
            })
            return

        self.send_json(
            200,
            {"ok": True, "message": "Login successful"},
            self.session_headers()
        )

    def send_like(self, body):
        if not self.logged_in():
            self.send_json(401, {
                "ok": False,
                "error": "Login required. Please sign in again."
            })
            return

        uid = body.get("uid")
        region = body.get("region")

        if not isinstance(uid, str) or not uid.isdigit() or not 1 <= len(uid) <= 30:
            self.send_json(400, {
                "ok": False,
                "error": "Enter a valid numeric player UID."
            })
            return

        allowed_regions = {
            "BD", "IND", "PK", "SG", "ID", "ME",
            "VN", "TH", "TW", "EU", "RU"
        }
        if not isinstance(region, str) or region not in allowed_regions:
            self.send_json(400, {
                "ok": False,
                "error": "Select a supported region."
            })
            return

        ok, reason = verify_turnstile(
            body.get("turnstile_token"), self.client_ip()
        )
        if not ok:
            self.send_json(400, {"ok": False, "error": reason})
            return

        status, data = fetch_like_api(uid, region)
        if status != 200:
            self.send_json(status, {"ok": False, **data})
            return

        # Preserve the upstream response, whether it is a list or object.
        self.send_json(200, {"ok": True, "data": data})
