// sekmeler
function showTab(name){
  document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active',p.id==='panel-'+name));
  try{history.replaceState(null,'','#'+name);}catch(e){}
  window.scrollTo({top:0,behavior:'smooth'});
}
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',()=>showTab(b.dataset.tab)));
(function(){const h=(location.hash||'').replace('#','');if(h&&document.getElementById('panel-'+h))showTab(h);})();

// pomodoro
let totalSec = 25*60, leftSec = totalSec, timerId = null, isBreak = false;
const el = () => document.getElementById('timer');
function fmt(s){const m=Math.floor(s/60),ss=s%60;return String(m).padStart(2,'0')+':'+String(ss).padStart(2,'0');}
function render(){if(!el())return;el().textContent=fmt(leftSec);document.title=fmt(leftSec)+' — Odak';}
function setLen(m){stopTimer();totalSec=m*60;leftSec=totalSec;isBreak=(m<=15&&totalSec<=15*60&&(m===5||m===15));const b=document.getElementById('startBtn');if(b)b.textContent='Başla';render();}
function toggleTimer(){
  const btn=document.getElementById('startBtn');
  if(timerId){stopTimer();if(btn)btn.textContent='Devam Et';return;}
  if(btn)btn.textContent='Duraklat';
  timerId=setInterval(()=>{
    leftSec--;render();
    if(leftSec<=0){stopTimer();if(btn)btn.textContent='Başla';finish();}
  },1000);
}
function stopTimer(){if(timerId){clearInterval(timerId);timerId=null;}}
function resetTimer(){stopTimer();leftSec=totalSec;const b=document.getElementById('startBtn');if(b)b.textContent='Başla';render();}
async function finish(){
  const mins=Math.round(totalSec/60);
  const kind=isBreak?'break':'focus';
  const msg=document.getElementById('pomMsg');
  if(kind==='break'){if(msg)msg.textContent='Mola bitti. Yeni bir odak başlat.';resetTimer();return;}
  if(msg)msg.textContent='Kaydediliyor...';
  try{
    const r=await fetch('/api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({minutes:mins,kind})});
    const j=await r.json();
    if(j.ok){if(msg)msg.textContent='+'+j.xp+' XP. Bugün '+j.today_min+' dk / '+j.today_xp+' XP.';location.reload();}
    else if(msg)msg.textContent='Kayıt hatası.';
  }catch(e){if(msg)msg.textContent='Bağlantı hatası.';}
  resetTimer();
}
render();
