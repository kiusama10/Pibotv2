import json, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError
from handlers.drawing_game import canvas_get, canvas_append, canvas_meta, canvas_change_word, canvas_chat

HTML=r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><title>PiBot Canvas v3</title><style>
*{box-sizing:border-box}html,body{margin:0;background:#09090d;color:#fff;font-family:system-ui,-apple-system,Segoe UI,sans-serif}.app{max-width:1000px;margin:auto;padding:10px}.top{text-align:center;font-size:24px;font-weight:900;margin:4px 0 8px}.secret{background:#17131f;border:1px solid #6e3ab5;border-radius:14px;padding:11px;text-align:center;font-size:21px;font-weight:900;color:#ffd75c;margin-bottom:8px}.tools{display:grid;gap:8px;background:#15151c;border-radius:14px;padding:10px;margin-bottom:10px}.palette{display:grid;grid-template-columns:repeat(11,minmax(30px,1fr));gap:6px}.sw{height:42px;border-radius:10px;border:3px solid #555}.sw.sel{border-color:#fff;outline:2px solid #8b5cf6}.row{display:flex;gap:7px;flex-wrap:wrap;align-items:center}.btn{min-height:44px;border:0;border-radius:10px;background:#2b2b36;color:#fff;padding:9px 12px;font-weight:800;font-size:15px}.btn.on{background:#7c3aed}.range{min-width:150px;flex:1}.workarea{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:10px;align-items:stretch}.board{width:100%;height:min(68vw,620px);min-height:360px;background:#fff;border-radius:14px;overflow:hidden;border:2px solid #444}.board canvas{display:block;width:100%;height:100%;touch-action:none;background:#fff}.status{text-align:center;color:#bbb;padding:8px}.livechat{margin-top:0;display:flex;flex-direction:column;min-height:360px;background:#111118;border:1px solid #30303c;border-radius:14px;overflow:hidden}.livehead{padding:9px 12px;font-weight:900;border-bottom:1px solid #292934}.messages{height:auto;flex:1;min-height:260px;overflow:auto;padding:8px 10px}.msg{padding:5px 2px;border-bottom:1px solid #20202a;font-size:14px}.msg b{color:#c4a7ff}.empty{color:#777;text-align:center;padding:18px}.viewer .secret,.viewer .tools,.viewer .livechat{display:none}.viewer .top:after{content:' · EN VIVO'}.viewer .board{height:min(75vw,700px)}@media(max-width:760px){.workarea{grid-template-columns:1fr}.livechat{margin-top:9px;min-height:0}.messages{height:170px;min-height:170px}}
@media(max-width:600px){.app{padding:6px}.top{font-size:20px}.secret{font-size:18px}.palette{grid-template-columns:repeat(6,1fr)}.sw{height:40px}.btn{flex:1 1 30%;font-size:14px}.board{height:62vh;min-height:420px}.row label{width:100%;display:flex;gap:8px;align-items:center}}
</style></head><body><div class="app" id="app"><div class="top">🎨 PiBot · Lienzo v3</div><div id="secret" class="secret">Cargando palabra…</div><div class="tools"><div class="palette" id="palette"></div><div class="row"><label>✏️ Grosor <input id="w" class="range" type="range" min="2" max="40" value="7"></label></div><div class="row"><button class="btn" id="eraser">🧽 Borrador</button><button class="btn" id="undo">↶ Deshacer</button><button class="btn" id="redo">↷ Rehacer</button><button class="btn" id="clear">🗑 Limpiar</button><button class="btn" id="change">🔄 Cambiar palabra · 100</button></div></div><div class="workarea"><div><div class="board"><canvas id="cv" width="1200" height="900"></canvas></div><div class="status" id="status">Dibuja con dedo, mouse o stylus.</div></div><div class="livechat"><div class="livehead">💬 Respuestas del grupo · EN VIVO</div><div id="messages" class="messages"><div class="empty">Esperando respuestas…</div></div></div></div></div><script>
(()=>{const qs=new URLSearchParams(location.search),game=qs.get('game')||'',token=qs.get('token')||'',view=qs.get('mode')==='view';const app=document.getElementById('app'),cv=document.getElementById('cv'),ctx=cv.getContext('2d'),status=document.getElementById('status'),secret=document.getElementById('secret');if(view)app.classList.add('viewer');const colors=['#111111','#ffffff','#e53935','#ff7a00','#ffd600','#43a047','#00b8d4','#1976d2','#673ab7','#e91e63','#795548'];let color=colors[0],eraser=false,down=false,last=null,hist=[],redo=[],pending=[];
function palette(){const p=document.getElementById('palette');colors.forEach((c,i)=>{const b=document.createElement('button');b.type='button';b.className='sw'+(i?'':' sel');b.style.background=c;b.addEventListener('click',()=>{color=c;eraser=false;document.getElementById('eraser').classList.remove('on');p.querySelectorAll('.sw').forEach(x=>x.classList.remove('sel'));b.classList.add('sel')});p.appendChild(b)})}palette();
function pos(e){const r=cv.getBoundingClientRect();return[(e.clientX-r.left)*cv.width/r.width,(e.clientY-r.top)*cv.height/r.height]}function paint(s){ctx.strokeStyle=s.c;ctx.lineWidth=s.w;ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();ctx.moveTo(s.a[0],s.a[1]);ctx.lineTo(s.b[0],s.b[1]);ctx.stroke()}function begin(e){if(view)return;down=true;last=pos(e);hist.push([]);redo=[];try{cv.setPointerCapture(e.pointerId)}catch(_){}e.preventDefault()}function move(e){if(!down||view)return;const p=pos(e),s={t:'s',a:last,b:p,c:eraser?'#ffffff':color,w:eraser?34:+document.getElementById('w').value};paint(s);hist[hist.length-1].push(s);pending.push(s);last=p;e.preventDefault()}function end(e){down=false;try{cv.releasePointerCapture(e.pointerId)}catch(_){}}cv.addEventListener('pointerdown',begin,{passive:false});cv.addEventListener('pointermove',move,{passive:false});cv.addEventListener('pointerup',end);cv.addEventListener('pointercancel',end);
function redraw(){ctx.clearRect(0,0,cv.width,cv.height);for(const g of hist)for(const s of g)paint(s)}document.getElementById('eraser').onclick=()=>{eraser=!eraser;document.getElementById('eraser').classList.toggle('on',eraser)};document.getElementById('undo').onclick=()=>{if(hist.length){redo.push(hist.pop());redraw();pending=[{t:'clear'},...hist.flat()]}};document.getElementById('redo').onclick=()=>{if(redo.length){hist.push(redo.pop());redraw();pending=[{t:'clear'},...hist.flat()]}};document.getElementById('clear').onclick=()=>{hist=[];redo=[];ctx.clearRect(0,0,cv.width,cv.height);pending=[{t:'clear'}]};
async function loadMeta(){if(view)return;try{const r=await fetch('/pibot-api-v3/meta?game='+encodeURIComponent(game)+'&token='+encodeURIComponent(token),{cache:'no-store'});if(!r.ok)throw 0;const d=await r.json();if(d.ended){secret.textContent='🏁 Ronda terminada';status.textContent='Regresando a Telegram…';setTimeout(()=>{try{if(window.Telegram&&Telegram.WebApp)Telegram.WebApp.close()}catch(_){ }},900);return}secret.textContent=d.word?'🤫 Tu palabra: '+d.word.toUpperCase():'⚠️ Ronda terminada';}catch(_){secret.textContent='⚠️ No pude cargar la palabra'}}loadMeta();setInterval(loadMeta,900);
async function loadChat(){if(view)return;try{const r=await fetch('/pibot-api-v4/chat?game='+encodeURIComponent(game)+'&token='+encodeURIComponent(token)+'&t='+Date.now(),{cache:'no-store'});if(!r.ok)return;const a=await r.json(),box=document.getElementById('messages');if(!a.length){box.innerHTML='<div class="empty">Esperando respuestas…</div>';return}box.innerHTML='';for(const m of a){const d=document.createElement('div');d.className='msg';const b=document.createElement('b');b.textContent=m.name+': ';const t=document.createTextNode(m.text);d.appendChild(b);d.appendChild(t);box.appendChild(d)}box.scrollTop=box.scrollHeight}catch(_){}}loadChat();setInterval(loadChat,900);
document.getElementById('change').onclick=async()=>{if(view)return;status.textContent='Cambiando…';try{const r=await fetch('/pibot-api-v3/change?game='+encodeURIComponent(game)+'&token='+encodeURIComponent(token),{method:'POST',cache:'no-store'});const d=await r.json();if(d.word){secret.textContent='🤫 Tu palabra: '+d.word.toUpperCase();document.getElementById('clear').click();status.textContent='✅ Palabra cambiada · -100 PiPesos'}else status.textContent=d.error==='money'?'❌ No tienes 100 PiPesos':'❌ No se pudo cambiar';}catch(_){status.textContent='❌ No se pudo cambiar'}};
setInterval(async()=>{if(view){try{const r=await fetch('/pibot-api-v3/draw?game='+encodeURIComponent(game)+'&token='+encodeURIComponent(token)+'&t='+Date.now(),{cache:'no-store'});if(r.ok){const a=await r.json();ctx.clearRect(0,0,cv.width,cv.height);for(const s of a){if(s.t==='clear')ctx.clearRect(0,0,cv.width,cv.height);else if(s.t==='s')paint(s)}}}catch(_){}return}if(!pending.length)return;const b=pending.splice(0);try{const r=await fetch('/pibot-api-v3/draw?game='+encodeURIComponent(game)+'&token='+encodeURIComponent(token),{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(b),cache:'no-store'});if(!r.ok)pending.unshift(...b)}catch(_){pending.unshift(...b)}},180);})();
</script></body></html>'''

SAOCB_INTERNAL_URL=os.getenv("SAOCB_INTERNAL_URL","http://127.0.0.1:8091").rstrip("/")

def _is_saocb_path(path):
 return path == "/api" or path.startswith(("/api/","/game/","/admin/","/telegram/admin/","/telegram/control-webhook"))

class H(BaseHTTPRequestHandler):
 def _send(self,code,body,ctype='application/json'):
  b=body.encode();self.send_response(code);self.send_header('content-type',ctype);self.send_header('content-length',len(b));self.send_header('cache-control','no-store, no-cache, must-revalidate, max-age=0');self.send_header('pragma','no-cache');self.end_headers();self.wfile.write(b)
 def _proxy_saocb(self):
  try:
   n=min(int(self.headers.get('content-length','0') or 0),2_000_000)
   body=self.rfile.read(n) if n else None
   headers={}
   for k in ('content-type','accept','accept-language','user-agent','x-api-secret','x-saocb-secret','x-telegram-user-id','x-pibot-secret','authorization','x-request-id'):
    v=self.headers.get(k)
    if v: headers[k]=v
   req=UrlRequest(SAOCB_INTERNAL_URL+self.path,data=body,headers=headers,method=self.command)
   try:
    r=urlopen(req,timeout=30); code=r.status; data=r.read(); ctype=r.headers.get('content-type','application/json')
   except HTTPError as e:
    code=e.code; data=e.read(); ctype=e.headers.get('content-type','application/json')
   self.send_response(code); self.send_header('content-type',ctype); self.send_header('content-length',str(len(data))); self.send_header('cache-control','no-store'); self.end_headers(); self.wfile.write(data)
  except Exception as e:
   data=json.dumps({'error':'saocb unavailable','detail':type(e).__name__}).encode(); self.send_response(503); self.send_header('content-type','application/json'); self.send_header('content-length',str(len(data))); self.end_headers(); self.wfile.write(data)

 def do_HEAD(self):
  u=urlparse(self.path)
  if _is_saocb_path(u.path): return self._proxy_saocb()
  if u.path=='/health':
   self.send_response(200);self.send_header('content-type','application/json');self.send_header('content-length','0');self.send_header('cache-control','no-store, no-cache, must-revalidate, max-age=0');self.send_header('pragma','no-cache');self.end_headers();return
  self.send_response(404);self.send_header('content-length','0');self.end_headers()
 def do_GET(self):
  u=urlparse(self.path)
  if _is_saocb_path(u.path): return self._proxy_saocb()
  if u.path in ('/pibot-canvas-v4','/pibot-canvas-v3','/draw'): return self._send(200,HTML,'text/html; charset=utf-8')
  if u.path=='/health': return self._send(200,'{"ok":true}')
  if u.path in ('/pibot-api-v3/draw','/api/draw'):
   q=parse_qs(u.query);d=canvas_get(q.get('game',[''])[0],q.get('token',[''])[0]);return self._send(200 if d is not None else 403,json.dumps(d if d is not None else {'error':'forbidden'}))
  if u.path=='/pibot-api-v4/chat':
   q=parse_qs(u.query);d=canvas_chat(q.get('game',[''])[0],q.get('token',[''])[0]);return self._send(200 if d is not None else 403,json.dumps(d if d is not None else {'error':'forbidden'}))
  if u.path in ('/pibot-api-v3/meta','/api/meta'):
   q=parse_qs(u.query);d=canvas_meta(q.get('game',[''])[0],q.get('token',[''])[0]);return self._send(200 if d is not None else 403,json.dumps(d if d is not None else {'error':'forbidden'}))
  self._send(404,'{"error":"not found"}')
 def do_POST(self):
  u=urlparse(self.path);q=parse_qs(u.query)
  if _is_saocb_path(u.path): return self._proxy_saocb()
  if u.path in ('/pibot-api-v3/change','/api/change'):
   d=canvas_change_word(q.get('game',[''])[0],q.get('token',[''])[0]);return self._send(200 if d is not None else 403,json.dumps(d if d is not None else {'error':'forbidden'}))
  if u.path not in ('/pibot-api-v3/draw','/api/draw'):return self._send(404,'{}')
  try:data=json.loads(self.rfile.read(min(int(self.headers.get('content-length','0')),200000)))
  except:return self._send(400,'{}')
  ok=canvas_append(q.get('game',[''])[0],q.get('token',[''])[0],data);self._send(200 if ok else 403,'{"ok":'+('true' if ok else 'false')+'}')
 def log_message(self,*a):pass

def run_server():
 port=int(os.getenv('PORT','8080'));ThreadingHTTPServer(('',port),H).serve_forever()
