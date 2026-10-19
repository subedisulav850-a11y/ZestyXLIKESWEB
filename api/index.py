from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, quote, urlencode
import time, hmac, hashlib, base64, json
import urllib.request, urllib.error

# ═══════════════════════════════════════════════════════════
# ⚙️ CONFIGURATION
# ═══════════════════════════════════════════════════════════
ADMIN_USER = "Zesty"
ADMIN_PASS = "676767"
SESSION_SECRET = "super-secret-zesty-key-change-me-if-you-want"

LIKE_API_BASE = "https://zesty220likes.vercel.app/like"
LIKE_API_KEY = "SulavOp"

# ── CLOUDFLARE TURNSTILE SETUP ─────────────────────────────
# Paste your keys between the quotes below. 
# Example: TURNSTILE_SITE_KEY = "0x4AAAAAAAB..."
TURNSTILE_SITE_KEY   = "0x4AAAAAAFLICIokx6zHNpTP"  # <--- PASTE SITE KEY HERE
TURNSTILE_SECRET_KEY = "0x4AAAAAAFLICCXoXBACekHvukmgiMglLwM"  # <--- PASTE SECRET KEY HERE
# ═══════════════════════════════════════════════════════════


# ── Security & Session Signing ─────────────────────────────
def _b64(b):  return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def _unb64(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def sign_session(data: dict) -> str:
    payload = _b64(json.dumps({**data, "exp": int(time.time() * 1000) + 8 * 3600 * 1000}).encode())
    sig = _b64(hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"

def verify_session(token: str) -> bool:
    if not token or "." not in token: return False
    p, _, s = token.partition(".")
    expected = _b64(hmac.new(SESSION_SECRET.encode(), p.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(s, expected): return False
    try:
        return json.loads(_unb64(p)).get("exp", 0) > int(time.time() * 1000)
    except Exception:
        return False


# ── Cloudflare Turnstile ───────────────────────────────────
def verify_turnstile(token: str, ip: str = "") -> bool:
    if not TURNSTILE_SECRET_KEY:
        return True # Bypass if no secret key is set
    try:
        data = urlencode({"secret": TURNSTILE_SECRET_KEY, "response": token, "remoteip": ip or ""}).encode()
        req = urllib.request.Request(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("success") is True
    except Exception:
        return False


# ── API Proxy Logic ────────────────────────────────────────
def fetch_like_api(uid: str, server_name: str) -> dict:
    url = f"{LIKE_API_BASE}?uid={quote(uid)}&server_name={quote(server_name)}&key={quote(LIKE_API_KEY)}"
    req = urllib.request.Request(url, headers={"User-Agent": "ZestyLikes/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": f"API Error {e.code}", "details": e.read().decode()}
    except Exception as e:
        return {"error": "Connection failed", "details": str(e)}


# ── Frontend HTML/CSS/JS ───────────────────────────────────
HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zesty Likes</title>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" async defer></script>
<style>
  :root { --bg: #0b0f1a; --card: #131826; --border: #1e2638; --input: #0f1524; --text: #e6e8ee; --muted: #8b95ad; --accent: #4f7cff; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; display: grid; place-items: center; padding: 24px; }
  .card { width: 100%; max-width: 420px; background: var(--card); padding: 32px 24px; border-radius: 16px; border: 1px solid var(--border); box-shadow: 0 10px 40px rgba(0,0,0,.6); }
  .logo { width: 88px; height: 88px; border-radius: 20px; display: block; margin: 0 auto 16px; background: var(--border); object-fit: contain; }
  h1 { text-align: center; margin: 0 0 24px; font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }
  label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 6px; font-weight: 500; }
  input { width: 100%; padding: 12px 14px; margin-bottom: 16px; border-radius: 10px; border: 1px solid var(--border); background: var(--input); color: var(--text); font-size: 14px; outline: none; transition: border-color 0.2s; }
  input:focus { border-color: var(--accent); }
  button { width: 100%; padding: 12px 14px; border-radius: 10px; border: none; background: linear-gradient(135deg, #4f7cff, #8b5cf6); color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; margin-top: 8px; transition: opacity 0.2s, transform 0.1s; }
  button:active:not(:disabled) { transform: scale(0.98); }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  .cf { display: flex; justify-content: center; align-items: center; margin: 8px 0; min-height: 65px; font-size: 13px; color: var(--muted); text-align: center; }
  .err { color: #ff6b81; font-size: 13px; text-align: center; min-height: 20px; margin-bottom: 8px; font-weight: 500; }
  pre { background: #0a0f1a; padding: 16px; border-radius: 10px; font-size: 13px; overflow: auto; max-height: 260px; border: 1px solid var(--border); color: #9ae6b4; white-space: pre-wrap; word-break: break-word; margin-top: 16px; font-family: monospace; }
  .top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
  .top h1 { margin: 0; text-align: left; }
  .logout { background: #2a3450; width: auto; padding: 8px 14px; font-size: 13px; margin: 0; }
</style>
</head>
<body>
<div class="card">
  <!-- Login View -->
  <div id="login-view">
    <img class="logo" src="/logo.png" alt="Logo" onerror="this.style.display='none'">
    <h1>Zesty Likes</h1>
    <label>Username</label>
    <input id="u" autocomplete="username" placeholder="Enter username">
    <label>Password</label>
    <input id="p" type="password" autocomplete="current-password" placeholder="Enter password">
    <div class="cf" id="cf-login">Loading Security...</div>
    <div class="err" id="login-err"></div>
    <button id="login-btn" disabled>Login</button>
  </div>

  <!-- Like View -->
  <div id="like-view" style="display:none">
    <div class="top">
      <h1>Send Like</h1>
      <button class="logout" id="logout-btn">Logout</button>
    </div>
    <label>UID</label>
    <input id="uid" placeholder="e.g. 6662785176">
    <label>Server / Region</label>
    <input id="server" placeholder="e.g. IND">
    <div class="cf" id="cf-like">Loading Security...</div>
    <div class="err" id="like-err"></div>
    <button id="like-btn" disabled>Send Like</button>
    <pre id="out" style="display:none"></pre>
  </div>
</div>

<script>
const SITE_KEY = "__SITE_KEY__";
let loginTok = "bypass", likeTok = "bypass";

function initTurnstile() {
  const siteKey = SITE_KEY.trim();
  
  // Bypass if no key is provided in the python file
  if (!siteKey || siteKey === "__SITE_KEY__") {
    document.getElementById("cf-login").innerHTML = "<span style='color:#8b95ad'>Security disabled (No Key)</span>";
    document.getElementById("cf-like").innerHTML = "<span style='color:#8b95ad'>Security disabled (No Key)</span>";
    document.getElementById("login-btn").disabled = false;
    document.getElementById("like-btn").disabled = false;
    return;
  }

  // Wait for Cloudflare script to load
  if (!window.turnstile) { setTimeout(initTurnstile, 300); return; }
  
  const le = document.getElementById("cf-login");
  const ke = document.getElementById("cf-like");
  
  if (le && !le.dataset.done) {
    turnstile.render(le, { 
      siteKey: siteKey, 
      theme: "dark",
      callback: t => { 
        loginTok = t; 
        document.getElementById("login-btn").disabled = false; 
      },
      "error-callback": () => {
        le.innerHTML = "<span style='color:#ff6b81'>Cloudflare Blocked. Check Domain settings or turn off AdBlocker.</span>";
      }
    });
    le.dataset.done = "1";
  }
  
  if (ke && !ke.dataset.done) {
    turnstile.render(ke, { 
      siteKey: siteKey, 
      theme: "dark",
      callback: t => { 
        likeTok = t; 
        document.getElementById("like-btn").disabled = false; 
      },
      "error-callback": () => {
        ke.innerHTML = "<span style='color:#ff6b81'>Cloudflare Blocked. Check Domain settings or turn off AdBlocker.</span>";
      }
    });
    ke.dataset.done = "1";
  }
}

async function checkAuth() {
  try {
    const d = await fetch("/api/me").then(r => r.json());
    document.getElementById("login-view").style.display = d.auth ? "none" : "block";
    document.getElementById("like-view").style.display  = d.auth ? "block" : "none";
    initTurnstile();
  } catch (e) { console.error("Auth check failed", e); }
}

document.getElementById("login-btn").onclick = async () => {
  const err = document.getElementById("login-err"); 
  const btn = document.getElementById("login-btn"); 
  err.textContent = ""; 
  btn.disabled = true; 
  btn.textContent = "Checking...";
  
  try {
    const r = await fetch("/api/login", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ username: u.value, password: p.value, token: loginTok })
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "Invalid credentials");
    await checkAuth();
  } catch (e) {
    err.textContent = e.message;
    btn.disabled = false; 
  } finally {
    btn.textContent = "Login";
  }
};

document.getElementById("logout-btn").onclick = async () => {
  await fetch("/api/logout", { method: "POST" });
  checkAuth();
};

document.getElementById("like-btn").onclick = async () => {
  const err = document.getElementById("like-err"); 
  const out = document.getElementById("out"); 
  const btn = document.getElementById("like-btn"); 
  err.textContent = ""; 
  out.style.display = "none";
  btn.disabled = true; 
  btn.textContent = "Sending...";
  
  try {
    const r = await fetch("/api/like", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ uid: uid.value, server_name: server.value, token: likeTok })
    });
    const d = await r.json();
    
    if (!r.ok) throw new Error(d.error || "Request failed");
    
    out.textContent = JSON.stringify(d, null, 2); 
    out.style.display = "block";
  } catch (e) {
    err.textContent = e.message;
  } finally {
    btn.disabled = false; 
    btn.textContent = "Send Like";
  }
};

checkAuth();
</script>
</body>
</html>
""".replace("__SITE_KEY__", TURNSTILE_SITE_KEY)


# ── Server Request Handler ─────────────────────────────────
class handler(BaseHTTPRequestHandler):
    def _json(self, code: int, obj: dict, headers: list = None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or []): self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _get_cookie(self, name: str) -> str:
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name: return v
        return None

    def _get_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b""
        try: return json.loads(raw or b"{}")
        except Exception: return {}

    def _get_ip(self) -> str:
        return (self.headers.get("CF-Connecting-IP")
                or self.headers.get("X-Forwarded-For", "").split(",")[0].strip())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/me":
            auth = verify_session(self._get_cookie("session"))
            return self._json(200, {"auth": auth})
        return self._html(HTML)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/login":  return self._handle_login()
        if path == "/api/like":   return self._handle_like()
        if path == "/api/logout":
            return self._json(200, {"ok": True}, [("Set-Cookie", "session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax")])
        return self._json(404, {"error": "Not found"})

    def _handle_login(self):
        d = self._get_body()
        if not verify_turnstile(d.get("token", ""), self._get_ip()):
            return self._json(400, {"error": "Security check failed. Please refresh."})
        if d.get("username") != ADMIN_USER or d.get("password") != ADMIN_PASS:
            return self._json(401, {"error": "Invalid username or password"})
        
        cookie = sign_session({"u": d["username"]})
        return self._json(200, {"ok": True}, [("Set-Cookie", f"session={cookie}; Path=/; Max-Age=28800; HttpOnly; Secure; SameSite=Lax")])

    def _handle_like(self):
        if not verify_session(self._get_cookie("session")):
            return self._json(401, {"error": "Unauthorized. Please log in again."})
        
        d = self._get_body()
        if not verify_turnstile(d.get("token", ""), self._get_ip()):
            return self._json(400, {"error": "Security check failed. Please refresh."})
        
        uid, server = str(d.get("uid", "")).strip(), str(d.get("server_name", "")).strip()
        if not uid or not server:
            return self._json(400, {"error": "Both UID and Server fields are required."})
            
        result = fetch_like_api(uid, server)
        return self._json(200, result)
