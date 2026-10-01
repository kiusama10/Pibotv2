import json, os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from handlers.drawing_game import canvas_get, canvas_append, canvas_meta, canvas_change_word
HTML='''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no"><title>PiBot Lienzo</title><style>body{margin:0;background:#111;color:#fff;font-family:system-ui;text-align:center}.bar{padding:8px;display:flex;gap:6px;flex-wrap:wrap;justify-content:center}canvas{background:white;touch-action:none;max-width:100%;border-radius:10px}button,input{font-size:16px;padding:8px}</style></head><body><h3>🎨 PiBot · Dibuja y Adivina</h3><div id=secret style='font-size:22px;font-weight:700;padding:6px'></div><div class=bar><input id=c type=color value="#111111"><input id=w type=range min=2 max=30 value=6><button onclick="eraser()">Borrador</button><button onclick="undo()">↶</button><button onclick="redo()">↷</button><button onclick="clearAll()">Limpiar</button><button onclick="changeWord()">🔄 Cambiar palabra · 100</button></div><canvas id=cv width=900 height=600></canvas><script>
const q=new URLSearchParams(location.search),game=q.get('game'),token=q.get('token'),view=q.get('view')==='1',cv=document.getElementById('cv'),x=cv.getContext('2d');let down=false,last=null,hist=[],redoS=[],pending=[];if(view){document.querySelector('.bar').style.display='none';document.getElementById('secret').style.display='none';document.querySelector('h3').textContent='🎨 PiBot · Lienzo en vivo';}else{fetch('/api/meta?game='+encodeURIComponent(game)+'&token='+encodeURIComponent(token)).then(r=>r.json()).then(d=>{if(d.word)document.getElementById('secret').textContent='🤫 Tu palabra: '+d.word.toUpperCase()}).catch(()=>{});}function pos(e){let r=cv.getBoundingClientRect(),p=e.touches?e.touches[0]:e;return [(p.clientX-r.left)*cv.width/r.width,(p.clientY-r.top)*cv.height/r.height]};function stroke(a,b,col,w){x.strokeStyle=col;x.lineWidth=w;x.lineCap='round';x.beginPath();x.moveTo(...a);x.lineTo(...b);x.stroke()}function start(e){if(view)return;down=true;last=pos(e);hist.push([]);redoS=[];e.preventDefault()}function move(e){if(!down)return;let p=pos(e),s={t:'s',a:last,b:p,c:document.getElementById('c').value,w:+document.getElementById('w').value};stroke(s.a,s.b,s.c,s.w);hist.at(-1).push(s);pending.push(s);last=p;e.preventDefault()}function end(){down=false}['mousedown','touchstart'].forEach(k=>cv.addEventListener(k,start,{passive:false}));['mousemove','touchmove'].forEach(k=>cv.addEventListener(k,move,{passive:false}));['mouseup','mouseleave','touchend'].forEach(k=>cv.addEventListener(k,end));function eraser(){document.getElementById('c').value='#ffffff';document.getElementById('w').value=24}function redraw(){x.clearRect(0,0,cv.width,cv.height);for(const g of hist)for(const s of g)stroke(s.a,s.b,s.c,s.w)}function undo(){if(hist.length){redoS.push(hist.pop());redraw();pending=[{t:'clear'},...hist.flat()]}}function redo(){if(redoS.length){hist.push(redoS.pop());redraw();pending=[{t:'clear'},...hist.flat()]}}function clearAll(){hist=[];redoS=[];x.clearRect(0,0,cv.width,cv.height);pending=[{t:'clear'}]}async function changeWord(){if(view)return;try{let r=await fetch('/api/change?game='+encodeURIComponent(game)+'&token='+encodeURIComponent(token),{method:'POST'}),d=await r.json();if(d.word){document.getElementById('secret').textContent='🤫 Tu palabra: '+d.word.toUpperCase();clearAll();alert('Palabra cambiada · -100 PiPesos')}else if(d.error==='money')alert('No tienes 100 PiPesos');else alert('No pude cambiar la palabra')}catch(e){alert('No pude cambiar la palabra')}}setInterval(async()=>{if(view){try{let r=await fetch('/api/draw?game='+encodeURIComponent(game)+'&token='+encodeURIComponent(token));if(r.ok){let a=await r.json();x.clearRect(0,0,cv.width,cv.height);for(const s of a){if(s.t==='clear'){x.clearRect(0,0,cv.width,cv.height)}else if(s.t==='s')stroke(s.a,s.b,s.c,s.w)}}}catch(e){}return;}if(!pending.length)return;let b=pending.splice(0);try{await fetch('/api/draw?game='+encodeURIComponent(game)+'&token='+encodeURIComponent(token),{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(b)})}catch(e){pending.unshift(...b)}},180);</script></body></html>'''
class H(BaseHTTPRequestHandler):
 def _send(self,code,body,ctype='application/json'):
  b=body.encode();self.send_response(code);self.send_header('content-type',ctype);self.send_header('content-length',len(b));self.send_header('cache-control','no-store');self.end_headers();self.wfile.write(b)
 def do_GET(self):
  u=urlparse(self.path)
  if u.path=='/draw': return self._send(200,HTML,'text/html; charset=utf-8')
  if u.path=='/health': return self._send(200,'{"ok":true}')
  if u.path=='/api/draw':
   q=parse_qs(u.query);d=canvas_get(q.get('game',[''])[0],q.get('token',[''])[0]);return self._send(200 if d is not None else 403,json.dumps(d if d is not None else {'error':'forbidden'}))
  if u.path=='/api/meta':
   q=parse_qs(u.query);d=canvas_meta(q.get('game',[''])[0],q.get('token',[''])[0]);return self._send(200 if d is not None else 403,json.dumps(d if d is not None else {'error':'forbidden'}))
  self._send(404,'{"error":"not found"}')
 def do_POST(self):
  u=urlparse(self.path)
  q=parse_qs(u.query)
  if u.path=='/api/change':
   d=canvas_change_word(q.get('game',[''])[0],q.get('token',[''])[0]);return self._send(200 if d is not None else 403,json.dumps(d if d is not None else {'error':'forbidden'}))
  if u.path!='/api/draw':return self._send(404,'{}')
  try:data=json.loads(self.rfile.read(min(int(self.headers.get('content-length','0')),200000)))
  except:return self._send(400,'{}')
  ok=canvas_append(q.get('game',[''])[0],q.get('token',[''])[0],data);self._send(200 if ok else 403,'{"ok":'+('true' if ok else 'false')+'}')
 def log_message(self,*a):pass
def run_server():
 port=int(os.getenv('PORT','8080')); ThreadingHTTPServer(('',port),H).serve_forever()
