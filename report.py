"""
Build the shareable page: reads the database, writes one interactive HTML file.

Run:  python report.py        -> report.html
"""
import json
import sqlite3
from datetime import date
from pathlib import Path
from statistics import median

import db

OUT = Path(__file__).resolve().parent / "report.html"
BUCKETS = ["1-3y", "3-5y", "5-7y", "7-10y", "10-15y", "15y+"]
PROCEEDS_LABEL = {
    "acquisition": "Acquisition", "refinancing": "Refinancing",
    "general_corporate": "General corporate", "capex": "Capex",
    "shareholder_returns": "Shareholder returns", "mixed": "Mixed", "not_stated": "Not stated",
}


def collect():
    conn = db.connect()
    rows = conn.execute("""
        SELECT t.bond_key, d.issuer, t.title, t.cusip, t.principal_usd, t.coupon_pct,
               t.maturity_date, t.spread_bps, t.spread_vs_index_bps, t.yield_pct,
               t.price_pct_of_par, t.grade, t.maturity_bucket, t.rating_moodys, t.rating_sp,
               t.math_check, d.use_of_proceeds, d.proceeds_quote,
               COALESCE(d.trade_date, d.filing_date), d.url, d.bookrunners
        FROM tranches t JOIN deals d ON d.accession = t.accession
        WHERE COALESCE(d.trade_date, d.filing_date) IS NOT NULL
        ORDER BY COALESCE(d.trade_date, d.filing_date) DESC
    """).fetchall()
    keys = ["key", "issuer", "title", "cusip", "size", "coupon", "maturity", "spread", "gap",
            "yield", "price", "grade", "bucket", "moodys", "sp", "check", "proceeds",
            "quote", "priced", "url", "banks"]
    bonds = [dict(zip(keys, r)) for r in rows]
    filings = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    return bonds, filings


def headline(bonds):
    """One sentence a non-specialist can read, computed from the data."""
    pairs = {}
    for b in bonds:
        if b["gap"] is None or b["proceeds"] not in ("acquisition", "refinancing"):
            continue
        pairs.setdefault(b["proceeds"], []).append(b["gap"])
    if len(pairs) == 2 and all(len(v) >= 3 for v in pairs.values()):
        a, r = median(pairs["acquisition"]), median(pairs["refinancing"])
        n = len(pairs["acquisition"]) + len(pairs["refinancing"])
        direction = "wider" if a > r else "tighter"
        return (f"Acquisition-funded deals priced a median <b>{abs(a - r):.0f} bps {direction}</b> "
                f"than refinancings, across {n} tranches.")
    return "Not enough classified deals yet to compare acquisition funding against refinancing."


CSS = """
:root{color-scheme:light;--bg:#fbfaf7;--surface:#fff;--line:#e3e0d8;--ink:#171614;--ink2:#56534c;
--ink3:#8a867c;--accent:#1a4f8a;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--chip:#f1efe9}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;--bg:#15150f;--surface:#1b1b18;
--line:#302f2a;--ink:#f7f5ef;--ink2:#c2bfb4;--ink3:#8d8a80;--accent:#7fb2ee;--s1:#3987e5;--s2:#d95926;
--s3:#199e70;--chip:#26261f}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 ui-sans-serif,-apple-system,"Segoe UI",sans-serif}
.col{max-width:760px;margin:0 auto;padding:0 20px}
.wide{max-width:1080px;margin:0 auto;padding:0 20px}
header{padding:64px 0 8px}
h1{font-family:Georgia,"Iowan Old Style",serif;font-size:40px;line-height:1.15;letter-spacing:-.02em;margin:0 0 10px;font-weight:600}
h2{font-family:Georgia,serif;font-size:24px;letter-spacing:-.01em;margin:52px 0 4px;font-weight:600}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink3);margin:28px 0 8px;font-weight:600}
.dek{font-size:18px;color:var(--ink2);margin:0 0 6px}
.byline{font-size:13px;color:var(--ink3);border-bottom:1px solid var(--line);padding-bottom:20px}
p{color:var(--ink2);margin:10px 0 14px}
.lede{font-size:19px;line-height:1.6;color:var(--ink);border-left:3px solid var(--accent);padding-left:18px;margin:26px 0}
.lede b{font-weight:600}
.stats{display:flex;flex-wrap:wrap;gap:34px;margin:22px 0 4px}
.stat .v{font-family:Georgia,serif;font-size:28px;font-variant-numeric:tabular-nums}
.stat .k{font-size:12px;color:var(--ink3);text-transform:uppercase;letter-spacing:.06em}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:16px 0 4px;
position:sticky;top:0;background:var(--bg);padding:12px 0;z-index:5;border-bottom:1px solid var(--line)}
button.f,select,input{font:13px ui-sans-serif,sans-serif;color:var(--ink);background:var(--surface);
border:1px solid var(--line);border-radius:999px;padding:6px 13px;cursor:pointer}
button.f[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
input{cursor:text;border-radius:8px;min-width:190px}
.chip{background:var(--chip);border-radius:999px;padding:5px 11px;font-size:12px;color:var(--ink2);cursor:pointer}
.chip b{color:var(--ink)}
figure{margin:14px 0 0;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px}
figcaption{font-size:12px;color:var(--ink3);margin-top:10px}
svg{width:100%;height:auto;display:block;overflow:visible}
.bar{fill:var(--accent);cursor:pointer}
.bar:hover{opacity:.75}
.bar.off{fill:var(--line)}
.dot{stroke:var(--surface);stroke-width:1.5;cursor:pointer}
.dot.p1{fill:var(--s1)}.dot.p2{fill:var(--s2)}.dot.p3{fill:var(--s3)}
.grid{stroke:var(--line)}
.zero{stroke:var(--ink3);stroke-dasharray:3 3}
.tick{fill:var(--ink3);font-size:11px;font-variant-numeric:tabular-nums}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--ink2);margin-top:12px}
.key{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:6px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink3);
padding:9px 10px;border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap;user-select:none}
th:hover{color:var(--ink)}
td{padding:9px 10px;border-bottom:1px solid var(--line);color:var(--ink2)}
td.n{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink)}
tr.row{cursor:pointer}
tr.row:hover td{background:var(--chip)}
tr.detail td{background:var(--chip);color:var(--ink2);font-size:13px}
.flag{color:var(--s2);font-weight:600}
.note{font-size:14px;color:var(--ink3);border-left:2px solid var(--line);padding-left:16px}
ul{color:var(--ink2);font-size:14px;padding-left:20px}
#tip{position:fixed;pointer-events:none;opacity:0;background:var(--ink);color:var(--bg);font-size:12px;
line-height:1.4;padding:7px 10px;border-radius:7px;transform:translate(-50%,-125%);transition:opacity .08s;z-index:9}
footer{margin:56px 0 80px;padding-top:18px;border-top:1px solid var(--line);font-size:12px;color:var(--ink3)}
@media(max-width:620px){h1{font-size:30px}.hide-s{display:none}}
"""

JS = r"""
const $=s=>document.querySelector(s), tip=$('#tip');
const F={grade:'all',proceeds:'all',bucket:'all',week:null,q:''};
let sortKey='priced', sortDir=-1;
const money=v=>v==null?'':(v>=1e9?'$'+(v/1e9).toFixed(2)+'B':'$'+Math.round(v/1e6)+'mm');
const pm=v=>v==null?'':(v>0?'+':'')+Math.round(v);
const week=d=>{const t=new Date(d+'T00:00:00');const o=new Date(t);o.setDate(t.getDate()-((t.getDay()+6)%7));return o.toISOString().slice(0,10);};
const pclass=p=>p==='acquisition'?'p1':p==='refinancing'?'p2':'p3';
const plabel=p=>({acquisition:'Acquisition',refinancing:'Refinancing',general_corporate:'General corporate',
  capex:'Capex',shareholder_returns:'Shareholder returns',mixed:'Mixed',not_stated:'Not stated'}[p]||'Not stated');

function visible(){
  return BONDS.filter(b=>{
    if(F.grade!=='all' && b.grade!==F.grade) return false;
    if(F.proceeds!=='all'){ const g = (b.proceeds==='acquisition'||b.proceeds==='refinancing')?b.proceeds:'other';
      if(g!==F.proceeds) return false; }
    if(F.bucket!=='all' && b.bucket!==F.bucket) return false;
    if(F.week && week(b.priced)!==F.week) return false;
    if(F.q && !((b.issuer||'')+' '+(b.title||'')+' '+(b.cusip||'')).toLowerCase().includes(F.q)) return false;
    return true;});
}
const med=a=>{if(!a.length)return null;const s=[...a].sort((x,y)=>x-y),m=s.length>>1;
  return s.length%2?s[m]:(s[m-1]+s[m])/2;};

function drawBars(rows){
  const by={}; rows.forEach(b=>{if(b.size)by[week(b.priced)]=(by[week(b.priced)]||0)+b.size;});
  const allWeeks=[...new Set(BONDS.map(b=>week(b.priced)))].sort();
  if(!allWeeks.length) return '<p class="note">No issuance yet.</p>';
  const W=1000,H=200,L=46,B=26,T=10,pw=W-L-10,ph=H-B-T;
  const top=Math.max(...allWeeks.map(w=>by[w]||0),1)*1.15, step=pw/allWeeks.length, bw=Math.min(step-5,30);
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Weekly issuance">`;
  [0,.5,1].forEach(f=>{const y=T+ph-f*ph;
    s+=`<line class="grid" x1="${L}" x2="${W-10}" y1="${y}" y2="${y}"/>`+
       `<text class="tick" x="${L-8}" y="${y+4}" text-anchor="end">${(top*f/1e9).toFixed(0)}</text>`;});
  allWeeks.forEach((w,i)=>{const v=by[w]||0,h=v/top*ph,x=L+i*step+(step-bw)/2,y=T+ph-h;
    const off=(F.week&&F.week!==w)?' off':'';
    s+=`<rect class="bar${off}" x="${x}" y="${Math.max(y,T)}" width="${bw}" height="${Math.max(h,1)}" rx="4"
         data-week="${w}" data-tip="Week of ${w}<br>${money(v)} priced"/>`;
    if(i%Math.max(1,Math.ceil(allWeeks.length/7))===0)
      s+=`<text class="tick" x="${x+bw/2}" y="${H-8}" text-anchor="middle">${w.slice(5)}</text>`;});
  return s+'</svg>';
}

function drawDots(rows){
  const pts=rows.filter(b=>b.gap!=null&&b.bucket);
  if(!pts.length) return '<p class="note">No deals with an index comparison in this view.</p>';
  const W=1000,H=260,L=48,B=28,T=12,pw=W-L-10,ph=H-B-T;
  const gaps=pts.map(p=>p.gap), lo=Math.min(0,...gaps)-8, hi=Math.max(0,...gaps)+8, step=pw/BUCKETS.length;
  const y=v=>T+ph-(v-lo)/(hi-lo)*ph;
  let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Spread versus index by tenor">`;
  s+=`<line class="zero" x1="${L}" x2="${W-10}" y1="${y(0)}" y2="${y(0)}"/>
      <text class="tick" x="${L-8}" y="${y(0)+4}" text-anchor="end">0</text>
      <text class="tick" x="${L-8}" y="${y(hi-6)+4}" text-anchor="end">${Math.round(hi-6)}</text>
      <text class="tick" x="${L-8}" y="${y(lo+6)+4}" text-anchor="end">${Math.round(lo+6)}</text>`;
  BUCKETS.forEach((b,i)=>{s+=`<text class="tick" x="${L+i*step+step/2}" y="${H-8}" text-anchor="middle">${b}</text>`;});
  pts.forEach(p=>{const i=BUCKETS.indexOf(p.bucket); if(i<0)return;
    let h=0; for(const c of p.key) h=(h*31+c.charCodeAt(0))%997;
    const x=L+i*step+step/2+((h/997)-.5)*step*.55;
    s+=`<circle class="dot ${pclass(p.proceeds)}" cx="${x}" cy="${y(p.gap)}" r="5"
         data-tip="<b>${p.issuer}</b><br>${p.title}<br>${pm(p.gap)} bps vs index · ${plabel(p.proceeds)}"/>`;});
  return s+'</svg>';
}

function drawTable(rows){
  const cols=[['issuer','Issuer',''],['title','Tranche','hide-s'],['size','Size','n'],['coupon','Coupon','n hide-s'],
    ['spread','Spread','n'],['gap','vs index','n'],['grade','Grade','hide-s'],['proceeds','Proceeds','hide-s'],['priced','Priced','n']];
  const sorted=[...rows].sort((a,b)=>{const x=a[sortKey],y=b[sortKey];
    if(x==null)return 1; if(y==null)return -1;
    return (typeof x==='number'?x-y:String(x).localeCompare(String(y)))*sortDir;});
  let s='<table><thead><tr>'+cols.map(([k,label,cls])=>
    `<th class="${cls}" data-sort="${k}">${label}${sortKey===k?(sortDir>0?' ↑':' ↓'):''}</th>`).join('')+'</tr></thead><tbody>';
  sorted.slice(0,200).forEach(b=>{
    s+=`<tr class="row" data-key="${b.key}">
      <td>${b.issuer||''}</td><td class="hide-s">${b.title||''}</td><td class="n">${money(b.size)}</td>
      <td class="n hide-s">${b.coupon!=null?b.coupon+'%':''}</td><td class="n">${pm(b.spread)}</td>
      <td class="n">${pm(b.gap)}</td><td class="hide-s">${b.grade||''}</td>
      <td class="hide-s">${plabel(b.proceeds)}</td><td class="n">${b.priced||''}</td></tr>`;});
  return s+'</tbody></table>'+(sorted.length>200?'<p class="note">Showing the first 200 of '+sorted.length+'.</p>':'');
}

function detailRow(b){
  const bits=[b.cusip?`CUSIP ${b.cusip}`:null, b.maturity?`Matures ${b.maturity}`:null,
    b.yield!=null?`Yield ${b.yield}%`:null, b.price!=null?`Price ${b.price}`:null,
    (b.moodys||b.sp)?`Rated ${[b.moodys,b.sp].filter(Boolean).join(' / ')}`:null,
    b.banks?`Books: ${b.banks}`:null].filter(Boolean).join(' · ');
  const quote=b.quote?`<br><em>"${b.quote}"</em>`:'';
  const flag=b.check==='MISMATCH'?'<br><span class="flag">Pricing math did not reconcile: flagged, not discarded.</span>':'';
  const link=b.url?`<br><a href="${b.url}" target="_blank" rel="noopener">Source filing on EDGAR</a>`:'';
  return `<tr class="detail"><td colspan="9">${bits}${quote}${flag}${link}</td></tr>`;
}

function render(){
  const rows=visible();
  $('#bars').innerHTML=drawBars(rows);
  $('#dots').innerHTML=drawDots(rows);
  $('#table').innerHTML=drawTable(rows);
  const groups={acquisition:[],refinancing:[],other:[]};
  rows.forEach(b=>{if(b.gap!=null)groups[(b.proceeds==='acquisition'||b.proceeds==='refinancing')?b.proceeds:'other'].push(b.gap);});
  $('#legend').innerHTML=['acquisition','refinancing','other'].filter(k=>groups[k].length).map((k,i)=>
    `<span><i class="key" style="background:var(--s${i+1})"></i>${k==='other'?'Other / not stated':plabel(k)} ·
     median ${pm(med(groups[k]))} bps (n=${groups[k].length})</span>`).join('');
  const vol=rows.reduce((a,b)=>a+(b.size||0),0);
  $('#count').textContent=rows.length.toLocaleString();
  $('#vol').textContent=money(vol);
  const gaps=rows.filter(b=>b.gap!=null).map(b=>b.gap);
  $('#medgap').textContent=gaps.length?pm(med(gaps))+' bps':'n/a';
  $('#weekchip').innerHTML=F.week?`<span class="chip" id="clearweek">Week of <b>${F.week}</b> ✕</span>`:'';
  if(F.week)$('#clearweek').onclick=()=>{F.week=null;render();};
  wire();
}

function wire(){
  document.querySelectorAll('[data-tip]').forEach(el=>{
    el.onmouseenter=()=>{const r=el.getBoundingClientRect();tip.innerHTML=el.dataset.tip;
      tip.style.left=(r.left+r.width/2)+'px';tip.style.top=r.top+'px';tip.style.opacity=1;};
    el.onmouseleave=()=>tip.style.opacity=0;});
  document.querySelectorAll('.bar').forEach(el=>el.onclick=()=>{
    F.week=F.week===el.dataset.week?null:el.dataset.week;render();});
  document.querySelectorAll('th[data-sort]').forEach(th=>th.onclick=()=>{
    const k=th.dataset.sort; sortDir=(k===sortKey)?-sortDir:-1; sortKey=k; render();});
  document.querySelectorAll('tr.row').forEach(tr=>tr.onclick=()=>{
    const open=tr.nextElementSibling&&tr.nextElementSibling.classList.contains('detail');
    document.querySelectorAll('tr.detail').forEach(d=>d.remove());
    if(!open)tr.insertAdjacentHTML('afterend',detailRow(BONDS.find(b=>b.key===tr.dataset.key)));});
}

document.querySelectorAll('button.f').forEach(btn=>btn.onclick=()=>{
  const [k,v]=[btn.dataset.k,btn.dataset.v];
  F[k]=v; document.querySelectorAll(`button.f[data-k="${k}"]`).forEach(b=>
    b.setAttribute('aria-pressed', b===btn)); render();});
$('#bucket').onchange=e=>{F.bucket=e.target.value;render();};
$('#search').oninput=e=>{F.q=e.target.value.toLowerCase();render();};
render();
"""


def build():
    bonds, filings = collect()
    checks = {}
    for b in bonds:
        checks[b["check"]] = checks.get(b["check"], 0) + 1
    checked = checks.get("OK", 0) + checks.get("MISMATCH", 0)
    dates = [b["priced"] for b in bonds if b["priced"]]
    span = f"{min(dates)} to {max(dates)}" if dates else "no deals yet"

    def fbtn(k, v, label, first=False):
        return (f"<button class='f' data-k='{k}' data-v='{v}' "
                f"aria-pressed='{str(first).lower()}'>{label}</button>")

    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>New Issue Credit Tracker</title><style>{CSS}</style></head><body><div id="tip"></div>
<header class="col">
  <h1>What the primary market paid</h1>
  <p class="dek">Every registered corporate bond deal, read out of SEC filings and priced against its index.</p>
  <p class="byline">James McHale · {span} · generated {date.today().isoformat()}</p>
</header>
<main class="col">
  <p class="lede">{headline(bonds)}</p>
  <p>When a company sells bonds, the prospectus says what the money is for. Deals that fund an acquisition
  add debt to the balance sheet; deals that refinance do not. This page tracks whether buyers charged more
  for the first kind, using {len(bonds):,} tranches read from filings rather than from a data vendor.</p>
  <div class="stats">
    <div class="stat"><div class="v" id="count">0</div><div class="k">tranches in view</div></div>
    <div class="stat"><div class="v" id="vol">0</div><div class="k">issuance in view</div></div>
    <div class="stat"><div class="v" id="medgap">0</div><div class="k">median vs index</div></div>
    <div class="stat"><div class="v">{checks.get('OK', 0)}/{checked or 0}</div><div class="k">pricing math verified</div></div>
  </div>
</main>
<div class="wide">
  <div class="controls">
    {fbtn('grade', 'all', 'All', True)}{fbtn('grade', 'IG', 'IG')}{fbtn('grade', 'HY', 'HY')}
    <span style="width:10px"></span>
    {fbtn('proceeds', 'all', 'Any use', True)}{fbtn('proceeds', 'acquisition', 'Acquisition')}
    {fbtn('proceeds', 'refinancing', 'Refinancing')}{fbtn('proceeds', 'other', 'Other')}
    <select id="bucket"><option value="all">Any tenor</option>
    {''.join(f'<option value="{b}">{b}</option>' for b in BUCKETS)}</select>
    <input id="search" type="search" placeholder="Search issuer or CUSIP">
    <span id="weekchip"></span>
  </div>

  <h2>Weekly issuance</h2>
  <p>Click a week to filter everything below to that week. Click again to clear.</p>
  <figure><div id="bars"></div><figcaption>Priced volume by week, in billions.</figcaption></figure>

  <h2>Cheap or rich, by tenor</h2>
  <p>Each dot is one bond: its spread minus the matching ICE BofA index on the day it priced.
  Above the line means it paid more than comparable paper.</p>
  <figure><div id="dots"></div><div class="legend" id="legend"></div></figure>

  <h2>The deals</h2>
  <p>Click any column to sort, any row to open the full terms and the filing.</p>
  <div id="table"></div>
</div>
<main class="col">
  <h2>Method and limits</h2>
  <p>A pipeline reads 424B and FWP filings from EDGAR, filters out stock offerings, asset-backed deals,
  convertibles, structured notes and sovereigns, and uses Claude to extract each tranche into a database.
  The model may use only numbers written in the filing and leaves a field empty rather than estimate one.
  Every tranche is checked against its own arithmetic: benchmark yield plus spread should equal the yield.</p>
  <ul>
    <li>Registered deals only. Most high yield is sold under Rule 144A and never reaches EDGAR.</li>
    <li>One row per tranche, deduplicated by CUSIP, so a deal filed twice counts once.</li>
    <li>Index spreads are option-adjusted and matched by rating category, not exact notch, so the gap is directional.</li>
    <li>No order book data: filings do not disclose books, price talk or new issue concession.</li>
    <li>{checks.get('MISMATCH', 0)} tranche(s) failed the math check and are flagged in the table, not discarded.</li>
  </ul>
  <footer>Source: SEC EDGAR (424B2, 424B5, FWP) and FRED (ICE BofA index OAS, Treasury yields).
  Personal project. Not investment advice.</footer>
</main>
<script>
const BONDS={json.dumps(bonds)};
const BUCKETS={json.dumps(BUCKETS)};
{JS}
</script></body></html>"""
    OUT.write_text(page)
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB) with {len(bonds)} tranches")


if __name__ == "__main__":
    build()
