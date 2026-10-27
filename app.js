
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)], tip=$('#tip');
const money=v=>v==null?'':(v>=1e9?'$'+(v/1e9).toFixed(2)+'B':'$'+Math.round(v/1e6)+'mm');
const pm=v=>v==null?'':(v>0?'+':'')+Math.round(v);
const med=a=>{if(!a.length)return null;const s=[...a].sort((x,y)=>x-y),m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2;};
const week=d=>{const t=new Date(d+'T00:00:00');const o=new Date(t);o.setDate(t.getDate()-((t.getDay()+6)%7));return o.toISOString().slice(0,10);};
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const RLABEL={senior_unsecured:'Senior unsecured',senior_secured:'Senior secured',first_mortgage:'First mortgage',
  subordinated:'Subordinated',junior_subordinated:'Junior subordinated',other:'Other',not_stated:'Not stated'};
const RSHORT={senior_unsecured:'Sr unsecured',senior_secured:'Sr secured',first_mortgage:'1st mortgage',
  subordinated:'Subordinated',junior_subordinated:'Jr subordinated',other:'Other',not_stated:''};
const GLABEL={none:'No guarantee',parent:'Guaranteed by parent',subsidiaries:'Guaranteed by subsidiaries',
  both:'Guaranteed by parent and subsidiaries',not_stated:'No guarantee mentioned'};
const VCLASS={'Holding':'v-hold','Mixed':'v-mixed','Not holding':'v-not','Too early':'v-early'};
const rgroup=r=>r==='senior_unsecured'?'senior':(r==='senior_secured'||r==='first_mortgage')?'secured':
  (r==='subordinated'||r==='junior_subordinated')?'sub':'other';
const guaranteed=g=>g==='parent'||g==='subsidiaries'||g==='both';
const pclass=p=>p==='acquisition'?'p1':p==='refinancing'?'p2':'p3';
const plabel=p=>({acquisition:'Acquisition',refinancing:'Refinancing',general_corporate:'General corporate',
  capex:'Capex',shareholder_returns:'Shareholder returns',mixed:'Mixed',not_stated:'Not stated'}[p]||'Not stated');
const expected=c=>c.sign>0?'Expected: wider':'Expected: tighter';

function ticks(lo,hi,count){
  const raw=(hi-lo)/(count||4), mag=Math.pow(10,Math.floor(Math.log10(raw)));
  const step=[1,2,2.5,5,10].map(m=>m*mag).find(s=>s>=raw); const out=[];
  for(let v=Math.floor(lo/step)*step; v<Math.ceil(hi/step)*step+step/2; v+=step) out.push(Math.round(v*100)/100);
  return out;
}
function wireTips(){
  $$('[data-tip]').forEach(el=>{
    const show=()=>{const r=el.getBoundingClientRect();tip.innerHTML=el.dataset.tip;
      tip.style.left=(r.left+r.width/2)+'px';tip.style.top=r.top+'px';tip.style.opacity=1;};
    el.onmouseenter=show; el.onmouseleave=()=>tip.style.opacity=0;
    el.addEventListener('touchstart',show,{passive:true});});
  window.addEventListener('scroll',()=>tip.style.opacity=0,{passive:true});
}

/* ---------- filters shared by Market and Deals ---------- */
const F={grade:'all',proceeds:'all',bucket:'all',week:null,q:'',rank:'all',coc:'all',guar:'all',sector:'all'};
let sortKey='priced', sortDir=-1, render=()=>{};
function visible(){
  return BONDS.filter(b=>{
    if(F.grade!=='all' && b.grade!==F.grade) return false;
    if(F.proceeds!=='all'){const g=(b.proceeds==='acquisition'||b.proceeds==='refinancing')?b.proceeds:'other';
      if(g!==F.proceeds) return false;}
    if(F.bucket!=='all' && b.bucket!==F.bucket) return false;
    if(F.week && week(b.priced)!==F.week) return false;
    if(F.rank!=='all' && rgroup(b.rank)!==F.rank) return false;
    if(F.coc!=='all' && (b.coc?'yes':'no')!==F.coc) return false;
    if(F.guar!=='all' && (guaranteed(b.guar)?'yes':'no')!==F.guar) return false;
    if(F.sector!=='all' && (b.sector||'Unknown')!==F.sector) return false;
    if(F.q && !((b.issuer||'')+' '+(b.title||'')+' '+(b.cusip||'')).toLowerCase().includes(F.q)) return false;
    return true;});
}
function wireFilters(){
  $$('button.f').forEach(btn=>btn.onclick=()=>{const k=btn.dataset.k,v=btn.dataset.v; F[k]=v;
    $$(`button.f[data-k="${k}"]`).forEach(b=>b.setAttribute('aria-pressed',b.dataset.v===v)); render();});
  $$('.bucketsel').forEach(sel=>sel.onchange=e=>{F.bucket=e.target.value; render();});
  $$('select.fsel').forEach(sel=>sel.onchange=e=>{F[sel.dataset.k]=e.target.value; render();});
  $$('.searchbox').forEach(inp=>inp.oninput=e=>{F.q=e.target.value.toLowerCase(); render();});
}

/* ---------- Thesis page ---------- */
function forest(claims){
  const vals=claims.flatMap(c=>[c.lo,c.hi,c.est]).filter(v=>v!=null);
  const t=ticks(Math.min(-20,...vals),Math.max(20,...vals),5), lo=t[0], hi=t[t.length-1];
  const x=v=>((v-lo)/(hi-lo)*100).toFixed(2)+'%';
  let s='';
  claims.forEach(c=>{
    const col=`color:var(--${{'Holding':'hold','Mixed':'mixed','Not holding':'not','Too early':'early'}[c.verdict]})`;
    const bar=c.lo!=null?`<div class="wh" style="left:${x(c.lo)};width:calc(${x(c.hi)} - ${x(c.lo)});${col}"></div>`:'';
    const pt=c.est!=null?`<div class="pt" style="left:${x(c.est)};${col}" data-tip="<b>${esc(c.claim)}</b><br>${pm(c.est)} bps vs peers${c.lo!=null?`<br>range ${pm(c.lo)} to ${pm(c.hi)}`:''}<br>${c.n} bonds, ${c.issuers} issuers"></div>
      <div class="lab" style="left:${x(c.est)};${col}">${pm(c.est)}</div>`:'';
    s+=`<a class="row" href="evidence.html#${c.key}"><div><div class="name">${esc(c.claim)}</div>
      <div class="sub">${expected(c)} · <span class="pill ${VCLASS[c.verdict]}" style="padding:1px 8px">${c.verdict}</span></div></div>
      <div class="track">${t.map(v=>`<div class="gl" style="left:${x(v)}"></div>`).join('')}
      <div class="zero" style="left:${x(0)}"></div>${bar}${pt}</div></a>`;});
  s+=`<div class="axis"><div></div><div class="ticks">${t.map(v=>`<span style="left:${x(v)}">${pm(v)||0}</span>`).join('')}</div>
    <div class="ends"><span>← tighter than peers</span><span>wider than peers →</span></div></div>`;
  return s;
}
function spark(trend){
  if(trend.length<2) return '<p class="spark-cap" style="margin:0">Not enough weeks yet for a trend.</p>';
  const v=trend.map(t=>t[1]), lo=Math.min(0,...v), hi=Math.max(0,...v), span=(hi-lo)||1;
  const X=i=>i/(trend.length-1)*100, Y=d=>40-(d-lo)/span*36;
  return `<svg class="spark" viewBox="0 0 100 44" preserveAspectRatio="none" aria-hidden="true">
    <line class="z" x1="0" x2="100" y1="${Y(0)}" y2="${Y(0)}"/>
    <polygon class="ar" points="0,${Y(0)} ${trend.map((t,i)=>X(i)+','+Y(t[1])).join(' ')} 100,${Y(0)}"/>
    <polyline class="ln" points="${trend.map((t,i)=>X(i)+','+Y(t[1])).join(' ')}"/></svg>
    <div class="spark-cap"><span>${trend[0][0].slice(5)}</span><span>estimate as data arrived</span><span>${trend[trend.length-1][0].slice(5)}</span></div>`;
}
function card(c){
  return `<a class="card" href="evidence.html#${c.key}"><div class="top"><span class="pill ${VCLASS[c.verdict]}">${c.verdict}</span>
    <span class="exp">${expected(c)}</span></div><h3>${esc(c.claim)}</h3>
    <div class="num">${c.est==null?'n/a':pm(c.est)}<small>bps vs peers</small></div>
    <div class="meta">${c.lo!=null?`range ${pm(c.lo)} to ${pm(c.hi)} · `:''}${c.n} bonds, ${c.issuers} issuer${c.issuers===1?'':'s'}</div>
    ${spark(c.trend)}<p class="why">${esc(c.why)}</p></a>`;
}
function initThesis(){
  $('#forest').innerHTML=forest(THESIS.claims);
  $('#cards').innerHTML=THESIS.claims.map(card).join('');
}

/* ---------- Evidence page ---------- */
function strip(c){
  if(!c.points.length) return '<p class="note">No bond with this feature has a comparable peer yet.</p>';
  const d=c.points.map(p=>p.diff), t=ticks(Math.min(-20,...d),Math.max(20,...d),5), lo=t[0], hi=t[t.length-1];
  const x=v=>((v-lo)/(hi-lo)*100).toFixed(2)+'%';
  let s=`<div class="strip"><div class="zero" style="left:${x(0)}"></div>`;
  if(c.est!=null) s+=`<div class="medl" style="left:${x(c.est)}"><span>median ${pm(c.est)}</span></div>`;
  c.points.forEach(p=>{let h=0; for(const ch of p.key) h=(h*31+ch.charCodeAt(0))%997;
    const vs=p.how==='issuer'?`${p.npeers} senior note${p.npeers>1?'s':''} from the same issuer, same day`:
      `${p.npeers} peer${p.npeers>1?'s':''} rated ${p.cell}`;
    s+=`<div class="d ${p.how}" style="left:${x(p.diff)};top:${12+h/997*62}px"
      data-tip="<b>${esc(p.issuer)}</b><br>${pm(p.diff)} bps vs ${vs}"></div>`;});
  s+=t.map(v=>`<span class="t" style="left:${x(v)}">${pm(v)||0}</span>`).join('')+'</div>';
  return s+`<div class="legend"><span><i class="key" style="background:var(--s1)"></i>vs the same issuer's own bonds, same day</span>
    <span><i class="key" style="background:var(--s3)"></i>vs other issuers with the same rating and maturity</span></div>`;
}
function drawStructure(rows){
  const groups=[
    ['Change of control put',[['Yes',b=>b.coc],['No',b=>b.rank&&!b.coc]]],
    ['Guarantee',[['Guaranteed',b=>guaranteed(b.guar)],['Not guaranteed',b=>b.guar&&!guaranteed(b.guar)]]],
    ['Ranking',[['Senior unsecured',b=>rgroup(b.rank)==='senior'],['Secured or first mortgage',b=>rgroup(b.rank)==='secured'],
                ['Subordinated',b=>rgroup(b.rank)==='sub']]],
    ['Coupon step',[['Has a step',b=>b.step],['No step',b=>b.rank&&!b.step]]]];
  let s='<table class="stab"><thead><tr><th>Term</th><th></th><th class="n">Tranches</th><th class="n hide-s">Volume</th>'+
        '<th class="n">Median vs index</th></tr></thead><tbody>';
  groups.forEach(([term,cuts])=>cuts.forEach(([label,fn],i)=>{
    const r=rows.filter(fn), g=r.filter(b=>b.gap!=null).map(b=>b.gap);
    s+=`<tr${i===0?' class="first"':''}><td>${i===0?term:''}</td><td>${label}</td><td class="n">${r.length}</td>
        <td class="n hide-s">${money(r.reduce((a,b)=>a+(b.size||0),0))}</td>
        <td class="n">${g.length?pm(med(g))+' bps <span class="nn">(n='+g.length+')</span>':''}</td></tr>`;}));
  return s+'</tbody></table>';
}
function initEvidence(){
  THESIS.claims.forEach(c=>{const el=$('#strip-'+c.key); if(el) el.innerHTML=strip(c);});
  render=()=>{$('#structure').innerHTML=drawStructure(visible()); wireTips();};
  wireFilters(); render();
}

/* ---------- Market page ---------- */
function drawBars(rows){
  const by={}; rows.forEach(b=>{if(b.size)by[week(b.priced)]=(by[week(b.priced)]||0)+b.size;});
  const allWeeks=[...new Set(BONDS.map(b=>week(b.priced)))].sort();
  const W=1000,H=220,L=50,B=30,T=10,pw=W-L-10,ph=H-B-T;
  const top=Math.max(...allWeeks.map(w=>by[w]||0),1), tk=ticks(0,top/1e9,3), ymax=tk[tk.length-1]*1e9||1;
  const step=pw/allWeeks.length, bw=Math.min(step-5,30);
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Weekly issuance">`;
  tk.forEach(v=>{const y=T+ph-v*1e9/ymax*ph;
    s+=`<line class="grid" x1="${L}" x2="${W-10}" y1="${y}" y2="${y}"/><text class="tick" x="${L-8}" y="${y+4}" text-anchor="end">$${v}B</text>`;});
  allWeeks.forEach((w,i)=>{const v=by[w]||0,h=v/ymax*ph,x=L+i*step+(step-bw)/2,y=T+ph-h;
    const off=(F.week&&F.week!==w)?' off':'';
    s+=`<rect class="bar${off}" x="${x}" y="${Math.max(y,T)}" width="${bw}" height="${Math.max(h,1)}" rx="4"
         data-week="${w}" data-tip="Week of ${w}<br>${money(v)} priced"/>`;
    if(i%Math.max(1,Math.ceil(allWeeks.length/6))===0)
      s+=`<text class="tick" x="${x+bw/2}" y="${H-8}" text-anchor="middle">${w.slice(5)}</text>`;});
  return s+'</svg>';
}
function drawIndex(){
  const pts=MARKET.filter(m=>m.BBB!=null&&m.BB!=null); if(pts.length<2) return '<p class="note">No index data.</p>';
  const W=1000,H=220,L=50,R=60,B=30,T=14,pw=W-L-R,ph=H-B-T;
  const all=pts.flatMap(p=>[p.BBB,p.BB]), tk=ticks(Math.min(...all)-10,Math.max(...all)+10,4), ymin=tk[0], ymax=tk[tk.length-1];
  const x=i=>L+i/(pts.length-1)*pw, y=v=>T+ph-(v-ymin)/(ymax-ymin)*ph;
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="BBB and BB index spreads">`;
  tk.forEach(v=>{s+=`<line class="grid" x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}"/><text class="tick" x="${L-8}" y="${y(v)+4}" text-anchor="end">${v}</text>`;});
  [['BBB','bbb'],['BB','bb']].forEach(([k,c])=>{
    s+=`<polyline class="line ${c}" points="${pts.map((p,i)=>x(i)+','+y(p[k])).join(' ')}"/>`;
    const last=pts[pts.length-1][k];
    s+=`<text class="axl" x="${W-R+8}" y="${y(last)+4}">${k} ${last}</text>`;});
  pts.forEach((p,i)=>{if(i%Math.max(1,Math.ceil(pts.length/6))===0)
    s+=`<text class="tick" x="${x(i)}" y="${H-8}" text-anchor="middle">${p.week.slice(5)}</text>`;});
  return s+'</svg>';
}
function drawDots(rows){
  const pts=rows.filter(b=>b.gap!=null&&b.bucket);
  if(!pts.length) return '<p class="note">No deals with an index comparison in this view.</p>';
  const W=1000,H=300,L=56,B=30,T=12,pw=W-L-10,ph=H-B-T;
  const gaps=pts.map(p=>p.gap), tk=ticks(Math.min(0,...gaps),Math.max(0,...gaps),4), lo=tk[0], hi=tk[tk.length-1];
  const step=pw/BUCKETS.length, y=v=>T+ph-(v-lo)/(hi-lo)*ph;
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Spread versus index by tenor">`;
  tk.forEach(v=>{s+=`<line class="${v===0?'zero':'grid'}" x1="${L}" x2="${W-10}" y1="${y(v)}" y2="${y(v)}"/>
    <text class="tick" x="${L-8}" y="${y(v)+4}" text-anchor="end">${pm(v)||0}</text>`;});
  BUCKETS.forEach((b,i)=>{s+=`<text class="tick" x="${L+i*step+step/2}" y="${H-8}" text-anchor="middle">${b}</text>`;});
  const order={p3:0,p2:1,p1:2};
  [...pts].sort((a,b)=>order[pclass(a.proceeds)]-order[pclass(b.proceeds)]).forEach(p=>{const i=BUCKETS.indexOf(p.bucket); if(i<0)return;
    let h=0; for(const c of p.key) h=(h*31+c.charCodeAt(0))%997;
    const x=L+i*step+step/2+((h/997)-.5)*step*.55;
    s+=`<circle class="dot ${pclass(p.proceeds)}" cx="${x}" cy="${y(p.gap)}" r="5.5"
         data-tip="<b>${esc(p.issuer)}</b><br>${esc(p.title)}<br>${pm(p.gap)} bps vs index · ${plabel(p.proceeds)}"/>`;});
  return s+'</svg>';
}
function initMarket(){
  $('#index').innerHTML=drawIndex();
  render=()=>{
    const rows=visible();
    $('#bars').innerHTML=drawBars(rows); $('#dots').innerHTML=drawDots(rows);
    const groups={acquisition:[],refinancing:[],other:[]};
    rows.forEach(b=>{if(b.gap!=null)groups[(b.proceeds==='acquisition'||b.proceeds==='refinancing')?b.proceeds:'other'].push(b.gap);});
    $('#legend').innerHTML=[['acquisition','s1'],['refinancing','s2'],['other','s3']].filter(([k])=>groups[k].length).map(([k,c])=>
      `<span><i class="key" style="background:var(--${c})"></i>${k==='other'?'Other / not stated':plabel(k)} · median ${pm(med(groups[k]))} bps (n=${groups[k].length})</span>`).join('');
    $('#count').textContent=rows.length.toLocaleString(); $('#vol').textContent=money(rows.reduce((a,b)=>a+(b.size||0),0));
    const g=rows.filter(b=>b.gap!=null).map(b=>b.gap); $('#medgap').textContent=g.length?pm(med(g))+' bps':'n/a';
    $('#weekchip').innerHTML=F.week?`<span class="chip" id="clearweek">Week of <b>${F.week}</b> ✕</span>`:'';
    if(F.week)$('#clearweek').onclick=()=>{F.week=null;render();};
    $$('.bar').forEach(el=>el.onclick=()=>{F.week=F.week===el.dataset.week?null:el.dataset.week;render();});
    wireTips();};
  wireFilters(); render();
}

/* ---------- Deals page ---------- */
function drawTable(rows){
  const cols=[['issuer','Issuer',''],['title','Tranche','hide-s'],['size','Size','n'],['coupon','Coupon','n hide-s'],
    ['spread','Spread','n'],['gap','vs index','n'],['grade','Grade','hide-s'],['rank','Ranking','hide-s'],
    ['coc','CoC put','hide-s'],['proceeds','Proceeds','hide-s'],['priced','Priced','n']];
  const sorted=[...rows].sort((a,b)=>{const x=a[sortKey],y=b[sortKey];
    if(x==null)return 1; if(y==null)return -1;
    return (typeof x==='number'?x-y:String(x).localeCompare(String(y)))*sortDir;});
  let s='<table><thead><tr>'+cols.map(([k,label,cls])=>
    `<th class="${cls}" data-sort="${k}">${label}${sortKey===k?(sortDir>0?' ↑':' ↓'):''}</th>`).join('')+'</tr></thead><tbody>';
  sorted.slice(0,200).forEach(b=>{
    s+=`<tr class="row" data-key="${esc(b.key)}">
      <td>${esc(b.issuer)}</td><td class="hide-s">${esc(b.title)}</td><td class="n">${money(b.size)}</td>
      <td class="n hide-s">${b.coupon!=null?b.coupon+'%':/floating/i.test(b.title||'')?'<span title="Floating rate: coupon resets off SOFR">FRN</span>':''}</td><td class="n">${pm(b.spread)}</td>
      <td class="n">${pm(b.gap)}</td><td class="hide-s">${b.grade||'<span title="The term sheet did not state ratings">n/s</span>'}</td>
      <td class="hide-s">${RSHORT[b.rank]||''}</td><td class="hide-s">${b.coc?'Yes':''}</td>
      <td class="hide-s">${plabel(b.proceeds)}</td><td class="n">${b.priced||''}</td></tr>`;});
  return s+'</tbody></table>'+(sorted.length>200?'<p class="note">Showing the first 200 of '+sorted.length+'.</p>':'');
}
function detailRow(b){
  const bits=[b.cusip?`CUSIP ${b.cusip}`:null, b.maturity?`Matures ${b.maturity}`:null,
    b.yield!=null?`Yield ${b.yield}%`:null, b.price!=null?`Price ${b.price}`:null,
    (b.moodys||b.sp)?`Rated ${[b.moodys,b.sp].filter(Boolean).join(' / ')}`:null,
    b.banks?`Books: ${esc(b.banks)}`:null].filter(Boolean).join(' · ');
  const sbits=[b.rank&&b.rank!=='not_stated'?RLABEL[b.rank]:null,
    b.guar?GLABEL[b.guar]+(b.guarnote&&guaranteed(b.guar)?` (${esc(b.guarnote)})`:''):null,
    b.coc?`Change of control put${b.cocpx?' at '+b.cocpx+'%':''}`:(b.rank?'No change of control put':null),
    b.step?`Coupon step: ${esc(b.stepnote||'yes')}`:null,
    b.sector?`Sector: ${esc(b.sector)}`:null, b.country?`Domicile: ${esc(b.country)}`:null].filter(Boolean).join(' · ');
  const structure=sbits?`<br><b>Structure</b> · ${sbits}`:'';
  const quote=b.quote?`<br><em>"${esc(b.quote)}"</em>`:'';
  const flag=b.check==='MISMATCH'?'<br><span class="flag">Pricing math did not reconcile: flagged, not discarded.</span>':'';
  const link=b.url?`<br><a href="${esc(b.url)}" target="_blank" rel="noopener">Source filing on EDGAR</a>`:'';
  return `<tr class="detail"><td colspan="11">${bits}${structure}${quote}${flag}${link}</td></tr>`;
}
function initDeals(){
  render=()=>{
    const rows=visible();
    $('#table').innerHTML=drawTable(rows);
    $('#rowcount').textContent=rows.length.toLocaleString()+' of '+BONDS.length.toLocaleString()+' tranches';
    $$('th[data-sort]').forEach(th=>th.onclick=()=>{const k=th.dataset.sort; sortDir=(k===sortKey)?-sortDir:-1; sortKey=k; render();});
    $$('tr.row').forEach(tr=>tr.onclick=()=>{
      const open=tr.nextElementSibling&&tr.nextElementSibling.classList.contains('detail');
      $$('tr.detail').forEach(d=>d.remove());
      if(!open)tr.insertAdjacentHTML('afterend',detailRow(BONDS.find(b=>b.key===tr.dataset.key)));});};
  wireFilters(); render();
}

({thesis:initThesis, evidence:initEvidence, market:initMarket, deals:initDeals}[document.body.dataset.page]||(()=>{}))();
wireTips();
