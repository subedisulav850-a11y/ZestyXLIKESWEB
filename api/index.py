from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, quote, urlencode
import time, hmac, hashlib, base64, json
import urllib.request

# ── ALL CONFIGURATION IS HARDCODED HERE ────────────────────
SECRET               = "zesty-super-secret-cookie-key-676767"
ADMIN_USER           = "Zesty"
ADMIN_PASS           = "676767"
LIKE_BASE            = "https://zesty220likes.vercel.app/like"
LIKE_KEY             = "SulavOp"

# CLOUDFLARE TURNSTILE (Optional)
# If you leave these blank (""), Turnstile is disabled and buttons work instantly.
# If you want security, paste your Cloudflare keys here:
TURNSTILE_SITE_KEY   = "0x4AAAAAAFLICIokx6zHNpTP" 
TURNSTILE_SECRET_KEY = "0x4AAAAAAFLICCXoXBACekHvukmgiMglLwM"
# ───────────────────────────────────────────────────────────

def _b64(b):  return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def _unb64(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def sign(data):
    payload = _b64(json.dumps({**data, "exp": int(time.time()*1000) + 8*3600*1000}).encode())
    sig = _b64(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"

def verify(token):
    if not token or "." not in token: return False
    p, _, s = token.partition(".")
    expected = _b64(hmac.new(SECRET.encode(), p.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(s, expected): return False
    try:
        return json.loads(_unb64(p)).get("exp", 0) > int(time.time()*1000)
    except Exception:
        return False

def turnstile_verify(token, ip=""):
    if not TURNSTILE_SECRET_KEY: return True
    try:
        data = urlencode({"secret": TURNSTILE_SECRET_KEY, "response": token, "remoteip": ip or ""}).encode()
        req = urllib.request.Request(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("success") is True
    except Exception:
        return False

def call_like(uid, server):
    url = f"{LIKE_BASE}?uid={quote(uid)}&server_name={quote(server)}&key={quote(LIKE_KEY)}"
    req = urllib.request.Request(url, headers={"User-Agent": "zesty-likes/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zesty Likes</title>
<script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" async defer></script>
<style>
  *{box-sizing:border-box}
  body{margin:0;font-family:system-ui,-apple-system,sans-serif;background:#0b0f1a;color:#e6e8ee;
       min-height:100vh;display:grid;place-items:center;padding:24px}
  .card{width:100%;max-width:420px;background:#131826;padding:32px 24px;border-radius:16px;
        border:1px solid #1e2638;box-shadow:0 10px 30px rgba(0,0,0,.5)}
  .logo{width:88px;height:88px;border-radius:20px;display:block;margin:0 auto 16px;
        background:#1e2638;object-fit:contain}
  h1{text-align:center;margin:0 0 24px;font-size:22px}
  label{display:block;font-size:13px;color:#8b95ad;margin-bottom:6px}
  input{width:100%;padding:12px 14px;margin-bottom:14px;border-radius:10px;border:1px solid #2a3450;
        background:#0f1524;color:#e6e8ee;font-size:14px;outline:none}
  input:focus{border-color:#4f7cff}
  button{width:100%;padding:12px 14px;border-radius:10px;border:none;
         background:linear-gradient(135deg,#4f7cff,#8b5cf6);color:#fff;font-size:15px;
         font-weight:600;cursor:pointer;margin-top:8px}
  button:disabled{opacity:.5;cursor:not-allowed}
  .cf{display:flex;justify-content:center;margin:8px 0 4px;min-height:0px}
  .err{color:#ff6b81;font-size:13px;text-align:center;min-height:18px;margin-bottom:8px}
  pre{background:#0a0f1a;padding:14px;border-radius:10px;font-size:12px;overflow:auto;
      max-height:260px;border:1px solid #1e2638;color:#9ae6b4;white-space:pre-wrap;word-break:break-word}
  .top{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
  .top h1{margin:0;text-align:left}
  .logout{background:#2a3450;width:auto;padding:8px 14px;font-size:13px;margin:0}
</style>
</head>
<body>
<div class="card">
  <div id="login-view">
    <img class="logo" src="/logo.png" alt="Logo" onerror="this.style.display='none'">
    <h1>Zesty Likes</h1>
    <label>Username</label>
    <input id="u" autocomplete="username">
    <label>Password</label>
    <input id="p" type="password" autocomplete="current-password">
    <div class="cf" id="cf-login"></div>
    <div class="err" id="login-err"></div>
    <button id="login-btn" disabled>Login</button>
  </div>
  <div id="like-view" style="display:none">
    <div class="top"><h1>Send Like</h1><button class="logout" id="logout-btn">Logout</button></div>
    <label>UID</label>
    <input id="uid" placeholder="e.g. 6662785176">
    <label>Server / Region</label>
    <input id="server" placeholder="e.g. IND">
    <div class="cf" id="cf-like"></div>
    <div class="err" id="like-err"></div>
    <button id="like-btn" disabled>Send Like</button>
    <pre id="out" style="display:none"></pre>
  </div>
</div>
<script>
const SITE_KEY = "__SITE_KEY__";
let loginTok = "", likeTok = "";

function initTurnstile() {
  if (!SITE_KEY || SITE_KEY === "") {
    // Bypass Cloudflare if no key is set in Python
    document.getElementById("login-btn").disabled = false;
    document.getElementById("like-btn").disabled = false;
    loginTok = "bypass";
    likeTok = "bypass";
    return;
  }

  if (!window.turnstile) { setTimeout(initTurnstile, 300); return; }
  
  const le = document.getElementById("cf-login");
  const ke = document.getElementById("cf-like");
  if (le) le.style.minHeight = "65px";
  if (ke) ke.style.minHeight = "65px";
  
  if (le && !le.dataset.done) {
    turnstile.render(le, { 
      siteKey: SITE_KEY, 
      callback: t => { loginTok = t; document.getElementById("login-btn").disabled = false; } 
    });
    le.dataset.done = "1";
  }
  
  if (ke && !ke.dataset.done) {
    turnstile.render(ke, { 
      siteKey: SITE_KEY, 
      callback: t => { likeTok = t; document.getElementById("like-btn").disabled = false; } 
    });
    ke.dataset.done = "1";
  }
}

async function checkAuth() {
  const d = await fetch("/api/me").then(r => r.json());
  document.getElementById("login-view").style.display = d.auth ? "none" : "block";
  document.getElementById("like-view").style.display  = d.auth ? "block" : "none";
  initTurnstile();
}

document.getElementById("login-btn").onclick = async () => {
  const err = document.getElementById("login-err"); err.textContent = "";
  const btn = document.getElementById("login-btn"); btn.disabled = true;
  const r = await fetch("/api/login", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: u.value, password: p.value, token: loginTok })
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { err.textContent = d.error || "Login failed"; btn.disabled = false; return; }
  checkAuth();
};

document.getElementById("logout-btn").onclick = async () => {
  await fetch("/api/logout", { method: "POST" });
  checkAuth();
};

document.getElementById("like-btn").onclick = async () => {
  const err = document.getElementById("like-err"); err.textContent = "";
  const out = document.getElementById("out"); out.style.display = "none";
  const btn = document.getElementById("like-btn"); btn.disabled = true;
  const r = await fetch("/api/like", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ uid: uid.value, server_name: server.value, token: likeTok })
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { err.textContent = d.error || "Request failed"; }
  out.textContent = JSON.stringify(d, null, 2); out.style.display = "block";
  btn.disabled = false;
};

checkAuth();
</script>
</body>
</html>
""".replace("__SITE_KEY__", TURNSTILE_SITE_KEY)


class handler(BaseHTTPRequestHandler):
    def _json(self, code, obj, headers=None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or []): self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cookie(self, name):
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == name: return v
        return None

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) if n else b""
        try: return json.loads(raw or b"{}")
        except Exception: return {}

    def _ip(self):
        return (self.headers.get("CF-Connecting-IP")
                or self.headers.get("X-Forwarded-For", "").split(",")[0].strip())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/me":
            return self._json(200, {"auth": verify(self._cookie("session"))})
        return self._html(HTML)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/login":  return self._login()
        if path == "/api/like":   return self._like()
        if path == "/api/logout":
            return self._json(200, {"ok": True},
                              [("Set-Cookie", "session=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax")])
        return self._json(404, {"error": "Not found"})

    def _login(self):
        d = self._body()
        if not d.get("token") or not turnstile_verify(d["token"], self._ip()):
            return self._json(400, {"error": "Security check failed"})
        if d.get("username") != ADMIN_USER or d.get("password") != ADMIN_PASS:
            return self._json(401, {"error": "Invalid login"})
        cookie = sign({"u": d["username"]})
        return self._json(200, {"ok": True},
                          [("Set-Cookie",
                            f"session={cookie}; Path=/; Max-Age=28800; HttpOnly; Secure; SameSite=Lax")])

    def _like(self):
        if not verify(self._cookie("session")):
            return self._json(401, {"error": "Unauthorized"})
        d = self._body()
        if not d.get("token") or not turnstile_verify(d["token"], self._ip()):
            return self._json(400, {"error": "Security check failed"})
        uid, server = d.get("uid"), d.get("server_name")
        if not uid or not server:
            return self._json(400, {"error": "Missing uid/server_name"})
        try:
            return self._json(200, call_like(uid, server))
        except Exception as e:
            return self._json(502, {"error": str(e)})
