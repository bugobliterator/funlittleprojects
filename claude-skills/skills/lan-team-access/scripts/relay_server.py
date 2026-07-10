#!/usr/bin/env python3
"""LAN team-access chat relay.

A small local HTTP server that lets a teammate on the LAN chat with the
Claude session running on this machine. Claude watches for messages, answers
in-scope project questions, and posts replies back to the page.

Security model (deliberately simple — this is a LAN collaboration tool):
  - Passcode gate: the teammate must enter a passcode (minted by the launcher)
    once; the server returns a session token used on every subsequent request.
  - Teammate (remote) endpoints require that token: /messages /ask /upload /uploads
  - Owner endpoints are localhost-only (so only the Claude session on this box
    can drive them): /answer /system /redirect /wait
  - Uploads are quarantined, type-allowlisted, size-capped, never executed.
  - /redirect lets the owner navigate every connected client away (e.g. to a
    rickroll) the instant misuse is detected, just before the server is killed.

Config via environment:
  RELAY_PORT      listen port (default 8420)
  RELAY_PASSCODE  required; server refuses to start without one
  RELAY_TITLE     banner title (e.g. the project name)
  RELAY_SCOPE     short scope line shown in the banner/hint
  RELAY_DIR       working dir for conversation.json + uploads/
"""
import json, os, threading, time, base64, re, mimetypes, secrets, tempfile, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

PORT = int(os.environ.get("RELAY_PORT", "8420"))
PASSCODE = os.environ.get("RELAY_PASSCODE", "")
TITLE = os.environ.get("RELAY_TITLE", "Project Q&A")
SCOPE = os.environ.get("RELAY_SCOPE", "this project only")
WORK_DIR = os.environ.get("RELAY_DIR") or os.path.join(tempfile.gettempdir(), f"lan-relay-{PORT}")
STORE = os.path.join(WORK_DIR, "conversation.json")
UPLOAD_DIR = os.path.join(WORK_DIR, "uploads")

if not PASSCODE:
    sys.exit("RELAY_PASSCODE must be set — refusing to start without a passcode.")

MAX_DECODED = 25 * 1024 * 1024
MAX_BODY = 40 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp",
               ".txt", ".md", ".csv", ".log", ".hex", ".json", ".xml"}

lock = threading.Lock()
cond = threading.Condition(lock)
messages = []          # {id, role, name, text, ts, ...}
next_id = 1
upload_seq = 0
redirect_url = None
tokens = set()         # valid session tokens (minted on correct passcode)


def load():
    global messages, next_id
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    if os.path.exists(STORE):
        try:
            data = json.load(open(STORE))
            messages = data.get("messages", [])
            next_id = data.get("next_id", len(messages) + 1)
        except Exception:
            pass


def persist():
    tmp = STORE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"messages": messages, "next_id": next_id}, f, indent=2)
    os.replace(tmp, STORE)


def add_message(role, text, name="", **extra):
    global next_id
    with cond:
        msg = {"id": next_id, "role": role, "name": name,
               "text": text, "ts": time.strftime("%H:%M:%S")}
        msg.update(extra)
        next_id += 1
        messages.append(msg)
        persist()
        cond.notify_all()
        return msg


def safe_name(raw):
    base = os.path.basename((raw or "file").replace("\\", "/").split("/")[-1])
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).lstrip(".") or "file"
    return base[:80]


PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{--bg:#0d1117;--panel:#161b22;--panel2:#1c2430;--line:#2a3441;--text:#e6edf3;
    --muted:#8b97a6;--accent:#3b82f6;--accent2:#10b981;--claude:#1f2a37;--eng:#243447;}
  *{box-sizing:border-box}html,body{height:100%}
  body{margin:0;background:var(--bg);color:var(--text);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    display:flex;flex-direction:column}
  body.drag::after{content:"Drop file to share (max 25 MB)";position:fixed;inset:14px;
    border:2px dashed var(--accent);border-radius:16px;background:rgba(59,130,246,.08);
    display:flex;align-items:center;justify-content:center;font-size:18px;z-index:50;pointer-events:none}
  header{padding:12px 18px;background:var(--panel);border-bottom:1px solid var(--line);
    display:flex;align-items:center;gap:12px;flex-wrap:wrap}
  header h1{font-size:15px;margin:0;font-weight:600}
  .dot{width:9px;height:9px;border-radius:50%;background:#555}
  .dot.live{background:var(--accent2);animation:pulse 2s infinite}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(16,185,129,.45)}70%{box-shadow:0 0 0 7px rgba(16,185,129,0)}100%{box-shadow:0 0 0 0 rgba(16,185,129,0)}}
  .scope{font-size:12px;color:var(--muted);background:var(--panel2);border:1px solid var(--line);
    padding:3px 9px;border-radius:999px}
  .spacer{flex:1}
  .who input{background:var(--panel2);border:1px solid var(--line);color:var(--text);
    border-radius:7px;padding:6px 9px;font-size:13px;width:150px;outline:none}
  #log{flex:1;overflow-y:auto;padding:20px;display:flex;flex-direction:column;gap:14px;
    max-width:900px;width:100%;margin:0 auto}
  .msg{display:flex;flex-direction:column;max-width:80%;animation:rise .18s ease}
  @keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
  .msg .meta{font-size:11px;color:var(--muted);margin:0 4px 4px;display:flex;gap:8px}
  .msg .bubble{padding:11px 14px;border-radius:14px;word-wrap:break-word;border:1px solid var(--line)}
  .msg.eng{align-self:flex-end;align-items:flex-end}.msg.eng .bubble{background:var(--eng);border-bottom-right-radius:4px}
  .msg.claude{align-self:flex-start;align-items:flex-start}.msg.claude .bubble{background:var(--claude);border-bottom-left-radius:4px}
  .msg.system{align-self:center;max-width:90%}.msg.system .bubble{background:transparent;border:1px dashed var(--line);color:var(--muted);font-size:13px;text-align:center}
  .bubble.file a{color:var(--accent);text-decoration:none;font-weight:600}.bubble.file .sz{color:var(--muted);font-size:12px;margin-left:6px}
  .bubble pre{background:#0a0e14;border:1px solid var(--line);border-radius:8px;padding:10px;overflow-x:auto;margin:8px 0;font-size:13px}
  .bubble code{background:#0a0e14;border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:13px;font-family:ui-monospace,Menlo,monospace}
  .bubble pre code{border:0;padding:0;background:none}
  footer{padding:12px 18px;background:var(--panel);border-top:1px solid var(--line)}
  .composer{display:flex;gap:10px;max-width:900px;margin:0 auto;align-items:flex-end}
  textarea{flex:1;background:var(--panel2);border:1px solid var(--line);color:var(--text);border-radius:10px;padding:10px 12px;font:inherit;resize:none;max-height:140px;outline:none}
  button{background:var(--accent);color:#fff;border:0;border-radius:10px;padding:10px 18px;font-weight:600;cursor:pointer;font-size:14px}
  button.attach{background:var(--panel2);border:1px solid var(--line);padding:10px 13px;font-size:17px}
  button:disabled{opacity:.5;cursor:default}
  .hint{font-size:11px;color:var(--muted);text-align:center;margin-top:6px}
  #gate{position:fixed;inset:0;background:var(--bg);display:flex;align-items:center;justify-content:center;z-index:100;flex-direction:column;gap:14px}
  #gate .card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:28px 30px;width:320px;text-align:center}
  #gate h2{margin:0 0 4px;font-size:17px}#gate p{color:var(--muted);font-size:13px;margin:0 0 16px}
  #gate input{width:100%;background:var(--panel2);border:1px solid var(--line);color:var(--text);border-radius:9px;padding:11px;font-size:15px;outline:none;text-align:center;letter-spacing:1px}
  #gate input:focus{border-color:var(--accent)}#gate button{width:100%;margin-top:12px}
  #gate .err{color:#f87171;font-size:13px;height:16px;margin-top:8px}
  .hidden{display:none!important}
</style></head>
<body>
<div id="gate"><div class="card">
  <h2>__TITLE__</h2><p>Enter the passcode to join the chat.</p>
  <input id="pass" type="password" placeholder="passcode" autocomplete="off">
  <button id="unlock">Unlock</button>
  <div class="err" id="gateErr"></div>
</div></div>

<header>
  <span class="dot" id="dot"></span><h1>__TITLE__</h1>
  <span class="scope">scope: __SCOPE__</span><span class="spacer"></span>
  <span class="who"><input id="name" placeholder="your name" maxlength="40"></span>
</header>
<div id="log"></div>
<footer>
  <div class="composer">
    <button class="attach" id="attach" title="Share a file (max 25 MB)">📎</button>
    <input type="file" id="file" class="hidden"
      accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,.txt,.md,.csv,.log,.hex,.json,.xml">
    <textarea id="box" rows="1" placeholder="Ask about __SCOPE__…  (Enter to send, Shift+Enter = newline)"></textarea>
    <button id="send">Send</button>
  </div>
  <div class="hint">Questions outside scope won't be answered. Attach files with 📎 or drag-and-drop.</div>
</footer>
<script>
const $=id=>document.getElementById(id);
const log=$('log'),box=$('box'),send=$('send'),nameI=$('name'),dot=$('dot'),attach=$('attach'),fileI=$('file');
const gate=$('gate'),passI=$('pass'),unlock=$('unlock'),gateErr=$('gateErr');
let lastId=0,token=localStorage.getItem('relay_token')||'',poller=null;
const MAX=25*1024*1024;
nameI.value=localStorage.getItem('relay_name')||'';
nameI.addEventListener('change',()=>localStorage.setItem('relay_name',nameI.value));
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function fmtSize(n){if(!n)return'';const u=['B','KB','MB'];let i=0;while(n>=1024&&i<2){n/=1024;i++;}return n.toFixed(i?1:0)+' '+u[i];}
function render(t){let p=esc(t).split(/```/),o='';for(let i=0;i<p.length;i++){if(i%2===1){o+='<pre><code>'+p[i].replace(/^\n/,'')+'</code></pre>';}else{o+=p[i].replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\n/g,'<br>');}}return o;}
function add(m){const el=document.createElement('div');
  if(m.role==='file'){el.className='msg eng';const fu=(m.url||'#')+(((m.url||'').indexOf('?')>=0)?'&':'?')+'token='+encodeURIComponent(token);el.innerHTML='<div class="meta"><span>'+esc(m.name||'')+'</span><span>'+esc(m.ts||'')+'</span></div><div class="bubble file">📎 <a href="'+esc(fu)+'" target="_blank">'+esc(m.fname||'file')+'</a><span class="sz">'+fmtSize(m.size)+'</span></div>';log.appendChild(el);return;}
  const cls=m.role==='engineer'?'eng':(m.role==='claude'?'claude':'system');el.className='msg '+cls;
  if(cls==='system'){el.innerHTML='<div class="bubble">'+render(m.text)+'</div>';}
  else{const who=m.role==='claude'?'Claude':(m.name||'guest');el.innerHTML='<div class="meta"><span>'+esc(who)+'</span><span>'+esc(m.ts||'')+'</span></div><div class="bubble">'+render(m.text)+'</div>';}
  log.appendChild(el);}
async function poll(){
  try{const r=await fetch('/messages?since='+lastId+'&token='+encodeURIComponent(token));
    if(r.status===401){showGate();return;}
    const d=await r.json();
    if(d.redirect){window.location.replace(d.redirect);return;}
    dot.classList.add('live');
    let near=log.scrollHeight-log.scrollTop-log.clientHeight<120;
    for(const m of d.messages){add(m);lastId=Math.max(lastId,m.id);}
    if(d.messages.length&&near)log.scrollTop=log.scrollHeight;
  }catch(e){dot.classList.remove('live');}
}
function startPolling(){if(poller)return;gate.classList.add('hidden');poll();poller=setInterval(poll,1500);}
function showGate(){if(poller){clearInterval(poller);poller=null;}gate.classList.remove('hidden');passI.focus();}
async function doAuth(){const code=passI.value.trim();if(!code)return;unlock.disabled=true;gateErr.textContent='';
  try{const r=await fetch('/auth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({passcode:code})});
    if(!r.ok){gateErr.textContent='Wrong passcode.';return;}
    const d=await r.json();token=d.token;localStorage.setItem('relay_token',token);startPolling();
  }catch(e){gateErr.textContent='Connection error.';}finally{unlock.disabled=false;}}
async function submit(){const text=box.value.trim();if(!text)return;send.disabled=true;
  try{const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,name:nameI.value||'guest',token})});
    if(r.status===401){showGate();return;}box.value='';box.style.height='auto';await poll();log.scrollTop=log.scrollHeight;
  }finally{send.disabled=false;box.focus();}}
function uploadFile(f){if(!f)return;if(f.size>MAX){alert('File too large (max 25 MB).');return;}
  const rd=new FileReader();attach.disabled=true;attach.textContent='…';
  rd.onload=async()=>{const b64=String(rd.result).split(',')[1]||'';
    try{const r=await fetch('/upload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:f.name,mime:f.type,b64,name:nameI.value||'guest',token})});
      if(r.status===401){showGate();return;}if(!r.ok){const e=await r.json().catch(()=>({}));alert('Upload rejected: '+(e.error||r.status));}
      await poll();log.scrollTop=log.scrollHeight;}catch(e){alert('Upload failed.');}
    finally{attach.disabled=false;attach.textContent='📎';fileI.value='';}};
  rd.readAsDataURL(f);}
unlock.addEventListener('click',doAuth);passI.addEventListener('keydown',e=>{if(e.key==='Enter')doAuth();});
attach.addEventListener('click',()=>fileI.click());fileI.addEventListener('change',()=>uploadFile(fileI.files[0]));
send.addEventListener('click',submit);
box.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submit();}});
box.addEventListener('input',()=>{box.style.height='auto';box.style.height=Math.min(box.scrollHeight,140)+'px';});
let dragN=0;
window.addEventListener('dragenter',e=>{e.preventDefault();dragN++;document.body.classList.add('drag');});
window.addEventListener('dragover',e=>e.preventDefault());
window.addEventListener('dragleave',()=>{dragN--;if(dragN<=0)document.body.classList.remove('drag');});
window.addEventListener('drop',e=>{e.preventDefault();dragN=0;document.body.classList.remove('drag');if(e.dataTransfer.files&&e.dataTransfer.files[0])uploadFile(e.dataTransfer.files[0]);});
// boot: if we have a stored token, try to use it; else show gate
if(token){fetch('/messages?since=0&token='+encodeURIComponent(token)).then(r=>{if(r.ok)startPolling();else showGate();}).catch(showGate);}else{showGate();}
</script></body></html>
"""


def is_local(addr):
    return addr in ("127.0.0.1", "::1", "localhost")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        try:
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *a):
        pass

    def _token_ok(self):
        if is_local(self.client_address[0]):
            return True
        u = urlparse(self.path)
        tok = parse_qs(u.query).get("token", [""])[0] or self.headers.get("X-Token", "")
        with lock:
            return tok in tokens

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            page = (PAGE.replace("__TITLE__", TITLE).replace("__SCOPE__", SCOPE))
            self._send(200, page, "text/html; charset=utf-8")
        elif u.path == "/messages":
            if not self._token_ok():
                self._send(401, json.dumps({"error": "auth required"})); return
            since = int(parse_qs(u.query).get("since", ["0"])[0])
            with lock:
                out = [m for m in messages if m["id"] > since]
                last = next_id - 1
                redir = redirect_url
            self._send(200, json.dumps({"messages": out, "last_id": last, "redirect": redir}))
        elif u.path == "/wait":
            if not is_local(self.client_address[0]):
                self._send(403, json.dumps({"error": "owner only"})); return
            qs = parse_qs(u.query)
            since = int(qs.get("since", ["0"])[0])
            timeout = min(float(qs.get("timeout", ["240"])[0]), 290)
            deadline = time.time() + timeout
            with cond:
                while True:
                    new = [m for m in messages if m["id"] > since and m["role"] in ("engineer", "file")]
                    if new:
                        self._send(200, json.dumps({"messages": new, "last_id": next_id - 1})); return
                    rem = deadline - time.time()
                    if rem <= 0:
                        self._send(200, json.dumps({"messages": [], "last_id": next_id - 1})); return
                    cond.wait(timeout=min(rem, 5))
        elif u.path.startswith("/uploads/"):
            if not self._token_ok():
                self._send(401, json.dumps({"error": "auth required"})); return
            name = safe_name(unquote(u.path[len("/uploads/"):]))
            fpath = os.path.join(UPLOAD_DIR, name)
            if os.path.isfile(fpath) and os.path.dirname(os.path.abspath(fpath)) == os.path.abspath(UPLOAD_DIR):
                ctype = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
                with open(fpath, "rb") as f:
                    self._send(200, f.read(), ctype)
            else:
                self._send(404, json.dumps({"error": "not found"}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        global redirect_url, upload_seq
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BODY:
            self._send(413, json.dumps({"error": "too large"})); return
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw or b"{}")
        except Exception:
            data = {}
        local = is_local(self.client_address[0])

        if u.path == "/auth":
            if (data.get("passcode") or "") == PASSCODE:
                tok = secrets.token_urlsafe(18)
                with lock:
                    tokens.add(tok)
                self._send(200, json.dumps({"token": tok}))
            else:
                self._send(401, json.dumps({"error": "bad passcode"}))
            return

        # teammate endpoints require token (or localhost)
        if u.path in ("/ask", "/upload"):
            tok = data.get("token", "")
            with lock:
                ok = local or tok in tokens
            if not ok:
                self._send(401, json.dumps({"error": "auth required"})); return
            if u.path == "/ask":
                text = (data.get("text") or "").strip()
                name = (data.get("name") or "guest").strip()[:40]
                if not text:
                    self._send(400, json.dumps({"error": "empty"})); return
                self._send(200, json.dumps(add_message("engineer", text, name)))
            else:  # /upload
                name = (data.get("name") or "guest").strip()[:40]
                fname = safe_name(data.get("filename"))
                ext = os.path.splitext(fname)[1].lower()
                if ext not in ALLOWED_EXT:
                    self._send(400, json.dumps({"error": "file type not allowed"})); return
                try:
                    blob = base64.b64decode(data.get("b64", ""), validate=False)
                except Exception:
                    self._send(400, json.dumps({"error": "bad encoding"})); return
                if not blob:
                    self._send(400, json.dumps({"error": "empty"})); return
                if len(blob) > MAX_DECODED:
                    self._send(413, json.dumps({"error": "too large (max 25MB)"})); return
                with lock:
                    upload_seq += 1
                    stored = time.strftime("%H%M%S") + "_" + str(upload_seq) + "_" + fname
                fpath = os.path.join(UPLOAD_DIR, stored)
                with open(fpath, "wb") as f:
                    f.write(blob)
                self._send(200, json.dumps(add_message(
                    "file", "shared a file", name, fname=fname, size=len(blob),
                    url="/uploads/" + stored, path=fpath)))
            return

        # owner endpoints: localhost only
        if u.path in ("/answer", "/system", "/redirect"):
            if not local:
                self._send(403, json.dumps({"error": "owner only"})); return
            if u.path == "/answer":
                text = (data.get("text") or "").strip()
                if not text:
                    self._send(400, json.dumps({"error": "empty"})); return
                self._send(200, json.dumps(add_message("claude", text, "Claude")))
            elif u.path == "/system":
                self._send(200, json.dumps(add_message("system", (data.get("text") or "").strip(), "")))
            else:  # /redirect
                with cond:
                    redirect_url = (data.get("url") or "").strip() or None
                    cond.notify_all()
                self._send(200, json.dumps({"redirect": redirect_url}))
            return

        self._send(404, json.dumps({"error": "not found"}))


if __name__ == "__main__":
    load()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"relay '{TITLE}' on 0.0.0.0:{PORT}  scope='{SCOPE}'  dir={WORK_DIR}")
    srv.serve_forever()
