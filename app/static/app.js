let totalSec = 25*60, leftSec = totalSec, timerId = null, isBreak = false;
const el = () => document.getElementById('timer');

function fmt(s){ const m = Math.floor(s/60), ss = s%60; return String(m).padStart(2,'0')+':'+String(ss).padStart(2,'0'); }
function render(){ el().textContent = fmt(leftSec); document.title = fmt(leftSec) + ' — Ders Motivasyon'; }
function setLen(m){ stopTimer(); totalSec = m*60; leftSec = totalSec; isBreak = (m<=5); render(); }
function toggleTimer(){
  const btn = document.getElementById('startBtn');
  if(timerId){ stopTimer(); btn.textContent='Devam Et'; return; }
  btn.textContent='Duraklat';
  timerId = setInterval(()=>{
    leftSec--;
    render();
    if(leftSec<=0){
      stopTimer();
      btn.textContent='Başla';
      finish();
    }
  },1000);
}
function stopTimer(){ if(timerId){clearInterval(timerId);timerId=null;} }
function resetTimer(){ stopTimer(); leftSec=totalSec; document.getElementById('startBtn').textContent='Başla'; render(); }
async function finish(){
  const mins = Math.round(totalSec/60);
  const kind = isBreak ? 'break' : 'focus';
  const msg = document.getElementById('pomMsg');
  if(kind==='break'){ msg.textContent='Mola bitti. Hadi bir odak daha!'; resetTimer(); return; }
  msg.textContent='Kaydediliyor...';
  try{
    const r = await fetch('/api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({minutes:mins,kind})});
    const j = await r.json();
    if(j.ok){ msg.textContent=`Harika! +${j.xp} XP kazandın. Bugün ${j.today_min} dk / ${j.today_xp} XP.`; alert(`Tebrikler! ${mins} dk odak +${j.xp} XP`); location.reload(); }
    else msg.textContent='Kayıt hatası: '+(j.err||'');
  }catch(e){ msg.textContent='Kayıt hatası (bağlantı).'; }
  resetTimer();
}
render();
