// tema
function toggleDark(){document.body.classList.toggle('dark');try{localStorage.setItem('odak-dark',document.body.classList.contains('dark')?'1':'0');}catch(e){}}
try{if(localStorage.getItem('odak-dark')==='1'){document.body.classList.add('dark');}}catch(e){}

// sekmeler
function showTab(name){
  document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id==='panel-'+name));
  try{history.replaceState(null,'','#'+name);}catch(e){}
}
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>showTab(b.dataset.tab)));
(function(){
  const h=(location.hash||'').replace('#','').split('?')[0];
  const valid=['odak','gorev','istatistik','ekip','mesaj'];
  if(valid.includes(h))showTab(h);
  else if(new URLSearchParams(location.search).get('c'))showTab('mesaj');
})();
function gotoChat(fid){location.href='/dashboard?c='+fid+'#mesaj';}
function focusTask(tid){
  showTab('odak');
  const s=document.getElementById('taskSelect');
  if(s){s.value=String(tid);syncSubj();}
  document.getElementById('goalInput')?.focus();
}
function syncSubj(){
  const s=document.getElementById('taskSelect'),sub=document.getElementById('subjInput');
  if(s&&sub){const o=s.selectedOptions[0];if(o&&o.dataset.subj)sub.value=o.dataset.subj;}
}
document.getElementById('taskSelect')?.addEventListener('change',syncSubj);
function copySummary(){
  const t=document.getElementById('sumCard')?.textContent||'';
  (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(()=>alert('Kopyalandı')).catch(()=>prompt('Kopyala:',t));
}

// bildirim izni (ilk Başla'da istenir)
function wantNotify(){try{if('Notification' in window&&Notification.permission==='default')Notification.requestPermission();}catch(e){}}
function notify(t,b){try{if('Notification' in window&&Notification.permission==='granted')new Notification(t,{body:b});}catch(e){}}

// pomodoro (dayanıklı: sayfa kapanınca localStorage'dan devam)
let totalSec=25*60,leftSec=totalSec,timerId=null,isBreak=false,pendingSave=null;
const RING_C=703.7;
const el=()=>document.getElementById('timer');
function fmt(s){const m=Math.floor(s/60),ss=s%60;return String(m).padStart(2,'0')+':'+String(ss).padStart(2,'0');}
function render(){
  if(!el())return;
  el().textContent=fmt(leftSec);
  document.title=fmt(leftSec)+' — Odak';
  const f=document.getElementById('ringFil');
  if(f)f.style.strokeDashoffset=String(RING_C*(leftSec/totalSec));
  paintDots();
}
function paintDots(){
  const d=document.getElementById('cycleDots');if(!d)return;
  const n=parseInt(d.dataset.chain||'0',10),pos=n%4===0&&n>0?4:n%4;
  let s='';for(let i=0;i<4;i++)s+=i<pos?'<b>●</b>':'●';
  d.innerHTML=s;
}
function setFocus(on){
  document.body.classList.toggle('focusing',on);
  document.getElementById('setupView').hidden=on;
  document.getElementById('focusView').hidden=!on;
  if(on){
    showTab('odak');
    const g=document.getElementById('goalInput')?.value||'';
    const t=document.getElementById('taskSelect');
    const tn=t&&t.value?t.selectedOptions[0].textContent:'';
    document.getElementById('goalLine').textContent=g||tn||(isBreak?'Mola — nefes al':'Odak');
    document.getElementById('fState').textContent=isBreak?'Mola':'Odak';
    document.getElementById('scoreBox').style.display='none';
  }
  render();
}
function persist(){try{localStorage.setItem('odak-t',{end:Date.now()+leftSec*1000,total:totalSec,break:isBreak?'1':'0'});}catch(e){}}
function clearPersist(){try{localStorage.removeItem('odak-t');}catch(e){}}
function setLen(m,kind,btn){
  stopTimer();clearPersist();setFocus(false);
  totalSec=m*60;leftSec=totalSec;isBreak=(kind==='break');
  document.querySelectorAll('.dur-grid .chip').forEach(c=>c.classList.remove('sel'));
  if(btn)btn.classList.add('sel');
  render();
}
function toggleTimer(){
  wantNotify();
  const pb=document.getElementById('pauseBtn');
  if(timerId){
    stopTimer();clearPersist();presenceClear();
    if(pb)pb.textContent='▶';
    return;
  }
  document.getElementById('scoreBox').style.display='none';
  setFocus(true);
  if(pb)pb.textContent='❚❚';
  presencePing();
  timerId=setInterval(()=>{
    leftSec--;render();persist();
    if(leftSec%30===0)presencePing();
    if(leftSec<=0){stopTimer();clearPersist();presenceClear();finish();}
  },1000);
  render();
}
function giveUp(){
  stopTimer();clearPersist();presenceClear();pendingSave=null;
  leftSec=totalSec;setFocus(false);
}
function stopTimer(){if(timerId){clearInterval(timerId);timerId=null;}}
function resetTimer(){giveUp();}
async function finish(){
  try{navigator.vibrate&&navigator.vibrate([200,100,200]);}catch(e){}
  const mins=Math.round(totalSec/60),kind=isBreak?'break':'focus';
  if(kind==='break'){
    notify('Mola bitti','Yeni bir odak başlat.');
    giveUp();
    setLen(25,'focus',document.querySelector('.dur-grid .chip'));
    return;
  }
  notify('Odak tamam','+'+(mins*2)+' XP hazır. Odak puanını ver.');
  pendingSave={minutes:mins,goal:document.getElementById('goalInput')?.value||'',task_id:document.getElementById('taskSelect')?.value||null,subject:document.getElementById('subjInput')?.value||''};
  document.getElementById('scoreBox').style.display='block';
}
async function saveScore(n){
  if(!pendingSave)return;
  const msg=document.getElementById('pomMsg');
  if(msg)msg.textContent='Kaydediliyor...';
  try{
    const r=await fetch('/api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({minutes:pendingSave.minutes,kind:'focus',goal:pendingSave.goal,task_id:pendingSave.task_id,subject:pendingSave.subject,score:n})});
    const j=await r.json();
    if(j.ok){pendingSave=null;location.reload();}
    else if(msg)msg.textContent='Kayıt hatası.';
  }catch(e){if(msg)msg.textContent='Bağlantı hatası.';}
}
// kaldığı yerden devam
(function(){
  try{
    const raw=localStorage.getItem('odak-t');if(!raw)return;
    const t=JSON.parse(raw),left=Math.round((t.end-Date.now())/1000);
    if(left>0){totalSec=t.total;leftSec=left;isBreak=t.break==='1';render();toggleTimer();}
    else localStorage.removeItem('odak-t');
  }catch(e){}
})();
render();

// presence: ben çalışırken her 30sn ping
function presenceDetail(){
  const g=document.getElementById('goalInput')?.value||'';
  const t=document.getElementById('taskSelect');
  const tn=t&&t.value?t.selectedOptions[0].textContent:'';
  return (tn||g||'odakta').slice(0,80);
}
function presencePing(){fetch('/api/presence/ping',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({detail:presenceDetail()})}).catch(()=>{});}
function presenceClear(){fetch('/api/presence/clear',{method:'POST'}).catch(()=>{});}
// ekip sekmesinde canlı rozetleri güncelle
async function pollLive(){
  if(!document.getElementById('panel-ekip')?.classList.contains('active'))return;
  try{
    const r=await fetch('/api/presence');const j=await r.json();
    if(!j.ok)return;
    document.querySelectorAll('[data-live]').forEach(elm=>{
      const v=j.live[elm.dataset.live];
      if(v){elm.style.display='inline';elm.querySelector('.lived').textContent=v.detail;}
      else elm.style.display='none';
    });
  }catch(e){}
}
setInterval(pollLive,30000);

// canlı güncellemeler: istek + iddia değişince hap göster (timer bölünmez)
let updBase=null;
function updSig(j){return JSON.stringify({r:j.req.map(x=>x.id),w:j.wagers});}
async function pollUpdates(){
  if(document.hidden)return;
  try{
    const r=await fetch('/api/updates');const j=await r.json();
    if(!j.ok)return;
    const sig=updSig(j);
    if(updBase===null){updBase=sig;return;}
    if(sig!==updBase){
      updBase=sig;
      const typing=document.activeElement&&(document.activeElement.tagName==='INPUT'||document.activeElement.tagName==='SELECT');
      if(timerId||typing){document.getElementById('updPill')?.classList.add('show');}
      else location.reload();
    }
  }catch(e){}
}
setInterval(pollUpdates,8000);
pollUpdates();
(function(){
  const box=document.getElementById('chatbox');
  if(!box)return;
  box.scrollTop=box.scrollHeight;
  const fid=box.dataset.fid,me=box.dataset.me,ind=document.getElementById('typingInd');
  const lastMid=()=>{const l=box.querySelector('.msg:last-child');return l?parseInt(l.dataset.mid||'0',10):0;};
  async function poll(){
    try{
      const r=await fetch('/api/chat/'+fid+'?since='+lastMid());
      const j=await r.json();
      if(!j.ok)return;
      if(j.msgs.length){
        box.querySelector('.muted')?.remove();
        j.msgs.forEach(m=>{
          if(box.querySelector('[data-mid="'+m.id+'"]'))return;
          const d=document.createElement('div');
          d.className='msg '+(String(m.sender)===String(me)?'me':'them');
          d.dataset.mid=m.id;
          const s=document.createElement('span');s.textContent=m.body;d.appendChild(s);
          box.appendChild(d);
        });
        box.scrollTop=box.scrollHeight;
      }
      if(ind)ind.style.display=j.typing?'block':'none';
    }catch(e){}
  }
  setInterval(poll,5000);
  let tT=null;
  document.getElementById('chatInput')?.addEventListener('input',()=>{
    if(tT)return;
    fetch('/api/chat/'+fid+'/typing',{method:'POST'}).catch(()=>{});
    tT=setTimeout(()=>tT=null,6000);
  });
})();

// PWA
try{if('serviceWorker' in navigator)navigator.serviceWorker.register('/static/sw.js').catch(()=>{});}catch(e){}
