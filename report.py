"""
Build the site: reads the database, writes five pages that share one stylesheet, one
data file and one script.

    python report.py        -> site/  (upload the folder's contents to GitHub Pages)

    index.html      Thesis: the claim, the scorecard and the chart that tests it
    evidence.html   Every bond behind each claim, and what the terms mean
    market.html     Weekly issuance, index spreads, cheap or rich by tenor
    deals.html      Every tranche, searchable, with the source filing
    method.html     Latest week, how it is measured, limits, how it is built
"""
import json
from datetime import date, timedelta
from pathlib import Path

import db
import thesis
from extras import ASK_HTML, ASK_JS, CSS as EXTRAS_CSS, recap_html

HERE = Path(__file__).resolve().parent
SITE = HERE / "site"
BUCKETS = ["1-3y", "3-5y", "5-7y", "7-10y", "10-15y", "15y+"]
PAGES = [("index.html", "Thesis"), ("evidence.html", "Evidence"), ("market.html", "Market"),
         ("deals.html", "Deals"), ("method.html", "Method")]


def collect(conn):
    rows = conn.execute("""
        SELECT t.bond_key, d.issuer, t.title, t.cusip, t.principal_usd, t.coupon_pct,
               t.maturity_date, t.spread_bps, t.spread_vs_index_bps, t.yield_pct,
               t.price_pct_of_par, t.grade, t.maturity_bucket, t.rating_moodys, t.rating_sp,
               t.math_check, d.use_of_proceeds, d.proceeds_quote,
               COALESCE(d.trade_date, d.filing_date), d.url, d.bookrunners,
               d.ranking, d.guarantees, d.guarantor_note, d.change_of_control,
               d.change_of_control_price, d.coupon_step, d.coupon_step_note, d.sector, d.country
        FROM tranches t JOIN deals d ON d.accession = t.accession
        WHERE COALESCE(d.trade_date, d.filing_date) IS NOT NULL
        ORDER BY COALESCE(d.trade_date, d.filing_date) DESC
    """).fetchall()
    keys = ["key", "issuer", "title", "cusip", "size", "coupon", "maturity", "spread", "gap",
            "yield", "price", "grade", "bucket", "moodys", "sp", "check", "proceeds",
            "quote", "priced", "url", "banks",
            "rank", "guar", "guarnote", "coc", "cocpx", "step", "stepnote", "sector", "country"]
    return [dict(zip(keys, r)) for r in rows]


def index_spreads(conn, start):
    """BBB and BB index OAS in bps, last reading of each week, from a few weeks before the first deal."""
    weekly = {}
    for day, label, value in conn.execute("""
            SELECT date, label, value FROM market_data
            WHERE ((family = 'ig_rating' AND label = 'BBB') OR (family = 'hy_rating' AND label = 'BB'))
              AND date >= ? ORDER BY date""", (start,)):
        d = date.fromisoformat(day)
        monday = (d - timedelta(days=d.weekday())).isoformat()
        weekly.setdefault(monday, {})[label] = round(value * 100)
    return [{"week": w, **v} for w, v in sorted(weekly.items())]


CSS = """
:root{color-scheme:light;--bg:#fbfaf7;--surface:#fff;--line:#e3e0d8;--ink:#171614;--ink2:#56534c;
--ink3:#8a867c;--accent:#1a4f8a;--s1:#2a78d6;--s2:#eb6834;--s3:#9b978d;--chip:#f1efe9;
--hold:#1b7f4c;--not:#c2410c;--mixed:#a86a0c;--early:#8a867c}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){color-scheme:dark;--bg:#15150f;--surface:#1b1b18;
--line:#302f2a;--ink:#f7f5ef;--ink2:#c2bfb4;--ink3:#8d8a80;--accent:#7fb2ee;--s1:#3987e5;--s2:#d95926;
--s3:#6f6c63;--chip:#26261f;--hold:#4cc38a;--not:#f0844e;--mixed:#e3a63c;--early:#8d8a80}}
:root[data-theme=dark]{color-scheme:dark;--bg:#15150f;--surface:#1b1b18;--line:#302f2a;--ink:#f7f5ef;
--ink2:#c2bfb4;--ink3:#8d8a80;--accent:#7fb2ee;--s1:#3987e5;--s2:#d95926;--s3:#6f6c63;--chip:#26261f;
--hold:#4cc38a;--not:#f0844e;--mixed:#e3a63c;--early:#8d8a80}
*{box-sizing:border-box}
html{scroll-padding-top:72px}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 ui-sans-serif,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}
.col{max-width:760px;margin:0 auto;padding:0 20px}
.wide{max-width:1080px;margin:0 auto;padding:0 20px}
.site{border-bottom:1px solid var(--line);background:var(--bg);position:sticky;top:0;z-index:20}
.site .in{max-width:1080px;margin:0 auto;padding:0 20px;display:flex;align-items:center;gap:24px;min-height:58px}
.brand{font-family:Georgia,serif;font-weight:600;color:var(--ink);text-decoration:none;font-size:17px;white-space:nowrap}
.site nav{display:flex;gap:2px;margin-left:auto;overflow-x:auto}
.site nav a{color:var(--ink2);text-decoration:none;font-size:14px;padding:6px 12px;border-radius:999px;white-space:nowrap}
.site nav a:hover{color:var(--ink);background:var(--chip)}
.site nav a[aria-current=page]{background:var(--ink);color:var(--bg)}
header.page{padding-top:52px;padding-bottom:6px}
.kicker{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--accent);font-weight:600;margin:0 0 10px}
h1{font-family:Georgia,"Iowan Old Style",serif;font-size:42px;line-height:1.12;letter-spacing:-.02em;margin:0 0 14px;font-weight:600;text-wrap:balance}
h2{font-family:Georgia,serif;font-size:25px;letter-spacing:-.01em;margin:56px 0 6px;font-weight:600}
h3{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink3);margin:28px 0 8px;font-weight:600}
.dek{font-size:19px;line-height:1.55;color:var(--ink2);margin:0 0 8px;text-wrap:pretty}
.byline{font-size:13px;color:var(--ink3);margin:14px 0 0}
p{color:var(--ink2);margin:10px 0 14px}
.verdicts{display:flex;flex-wrap:wrap;gap:8px;margin:26px 0 0}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;border-radius:999px;padding:4px 11px;white-space:nowrap}
.pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.pill.big{font-size:14px;padding:7px 14px}
.v-hold{color:var(--hold);background:color-mix(in srgb,var(--hold) 13%,transparent)}
.v-not{color:var(--not);background:color-mix(in srgb,var(--not) 13%,transparent)}
.v-mixed{color:var(--mixed);background:color-mix(in srgb,var(--mixed) 14%,transparent)}
.v-early{color:var(--early);background:color-mix(in srgb,var(--early) 15%,transparent)}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:22px 24px;margin:16px 0 0}
.panel .cap{font-size:12px;color:var(--ink3);margin:14px 0 0}
.forest .row{display:grid;grid-template-columns:minmax(0,38%) 1fr;gap:18px;align-items:center;padding:12px 0;
border-bottom:1px solid var(--line);text-decoration:none;color:inherit}
.forest .row:last-child{border-bottom:none}
.forest a.row:hover .name{color:var(--accent)}
.forest .name{font-size:15px;font-weight:600;color:var(--ink);line-height:1.35}
.forest .sub{font-size:12px;color:var(--ink3);margin-top:3px}
.track{position:relative;height:34px}
.track .zero{position:absolute;top:0;bottom:0;width:0;border-left:1px dashed var(--ink3)}
.track .gl{position:absolute;top:0;bottom:0;width:0;border-left:1px solid var(--line)}
.track .wh{position:absolute;top:50%;height:3px;margin-top:-1.5px;border-radius:2px;opacity:.45;background:currentColor}
.track .pt{position:absolute;top:50%;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;
background:currentColor;border:2px solid var(--surface)}
.track .lab{position:absolute;top:-4px;font-size:12px;font-weight:600;font-variant-numeric:tabular-nums;transform:translateX(-50%);white-space:nowrap}
.axis{display:grid;grid-template-columns:minmax(0,38%) 1fr;gap:18px;margin-top:6px}
.axis .ticks{position:relative;height:18px;font-size:11px;color:var(--ink3);font-variant-numeric:tabular-nums}
.axis .ticks span{position:absolute;transform:translateX(-50%)}
.axis .ends{grid-column:2;display:flex;justify-content:space-between;font-size:12px;color:var(--ink3)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px;margin-top:16px}
.card{display:block;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:20px 20px 16px;
text-decoration:none;color:inherit;transition:border-color .15s,transform .15s}
.card:hover{border-color:var(--ink3);transform:translateY(-1px)}
.card .top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.card .exp{font-size:12px;color:var(--ink3)}
.card h3{font:600 17px/1.3 Georgia,serif;color:var(--ink);text-transform:none;letter-spacing:0;margin:14px 0 8px}
.card .num{font-family:Georgia,serif;font-size:34px;font-variant-numeric:tabular-nums;line-height:1.1}
.card .num small{font:13px ui-sans-serif,sans-serif;color:var(--ink3);margin-left:4px}
.card .meta{font-size:13px;color:var(--ink2);margin:4px 0 10px}
.card .why{font-size:13px;color:var(--ink3);margin:10px 0 0;line-height:1.5}
.spark{display:block;width:100%;height:44px}
.spark{margin-top:6px}.spark .ln{fill:none;stroke:var(--accent);stroke-width:2;vector-effect:non-scaling-stroke}
.spark .ar{fill:color-mix(in srgb,var(--accent) 10%,transparent)}
.spark .z{stroke:var(--line);stroke-dasharray:3 3;vector-effect:non-scaling-stroke}
.spark-cap{display:flex;justify-content:space-between;font-size:11px;color:var(--ink3)}
.next{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin:18px 0 0}
.next a{display:block;padding:16px 18px;border:1px solid var(--line);border-radius:12px;text-decoration:none;color:var(--ink);background:var(--surface)}
.next a:hover{border-color:var(--ink3)}
.next b{display:block;font-family:Georgia,serif;font-size:17px;font-weight:600}
.next span{font-size:13px;color:var(--ink3)}
.claimnav{display:flex;flex-wrap:wrap;gap:8px;margin:22px 0 0}
.claimnav a{font-size:13px;text-decoration:none;color:var(--ink2);background:var(--chip);border-radius:999px;padding:6px 12px}
.claimnav a:hover{color:var(--ink)}
section.claim{border-top:1px solid var(--line);margin-top:56px;padding-top:8px}
section.claim h2{margin-top:22px}
.facts{display:flex;flex-wrap:wrap;gap:28px;margin:18px 0 6px}
.facts .v{font-family:Georgia,serif;font-size:26px;font-variant-numeric:tabular-nums}
.facts .k{font-size:12px;color:var(--ink3);text-transform:uppercase;letter-spacing:.06em}
.strip{position:relative;height:120px;margin:8px 0 0}
.strip .zero{position:absolute;top:0;bottom:22px;border-left:1px dashed var(--ink3)}
.strip .medl{position:absolute;top:0;bottom:22px;border-left:2px solid var(--ink)}
.strip .medl span{position:absolute;top:-2px;left:6px;font-size:11px;font-weight:600;white-space:nowrap}
.strip .d{position:absolute;width:12px;height:12px;margin-left:-6px;border-radius:50%;border:1.5px solid var(--surface);cursor:pointer}
.strip .d.issuer{background:var(--s1)}.strip .d.cell{background:var(--s3)}
.strip .t{position:absolute;bottom:0;font-size:11px;color:var(--ink3);transform:translateX(-50%);font-variant-numeric:tabular-nums}
.callout{border-left:3px solid var(--accent);padding:4px 0 4px 16px;margin:18px 0}
.callout p{margin:4px 0;color:var(--ink)}
.checks{font-size:14px;color:var(--ink2);padding-left:20px;margin:10px 0}
.stats{display:flex;flex-wrap:wrap;gap:34px;margin:22px 0 4px}
.stat .v{font-family:Georgia,serif;font-size:28px;font-variant-numeric:tabular-nums}
.stat .k{font-size:12px;color:var(--ink3);text-transform:uppercase;letter-spacing:.06em}
.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:16px 0 4px}
.controls.sticky{position:sticky;top:58px;background:var(--bg);padding:12px 0;z-index:5;border-bottom:1px solid var(--line)}
button.f,select,input{font:13px ui-sans-serif,sans-serif;color:var(--ink);background:var(--surface);
border:1px solid var(--line);border-radius:999px;padding:6px 13px;cursor:pointer}
button.f[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
input{cursor:text;border-radius:8px;min-width:190px}
select.fsel{border-radius:8px}
.chip{background:var(--chip);border-radius:999px;padding:5px 11px;font-size:12px;color:var(--ink2);cursor:pointer}
.chip b{color:var(--ink)}
.gap{width:10px}
figure{margin:14px 0 0;background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px}
figcaption{font-size:12px;color:var(--ink3);margin-top:10px}
svg{width:100%;height:auto;display:block;overflow:visible}
.bar{fill:var(--accent);cursor:pointer}
.bar:hover{opacity:.75}
.bar.off{fill:var(--line)}
.dot{stroke:var(--surface);stroke-width:1.5;cursor:pointer}
.dot.p1{fill:var(--s1)}.dot.p2{fill:var(--s2)}.dot.p3{fill:var(--s3);opacity:.55}
.grid{stroke:var(--line)}
.zero{stroke:var(--ink3);stroke-dasharray:3 3}
.tick{fill:var(--ink3);font-size:12px;font-variant-numeric:tabular-nums}
.axl{fill:var(--ink3);font-size:12px}
.line{fill:none;stroke-width:2.5}
.line.bbb{stroke:var(--s1)}.line.bb{stroke:var(--s2)}
.legend{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:var(--ink2);margin-top:12px}
.key{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:6px}
.tablewrap{max-height:72vh;overflow:auto;border:1px solid var(--line);border-radius:12px;background:var(--surface)}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{position:sticky;top:0;background:var(--surface);z-index:2;box-shadow:0 1px 0 var(--line)}
.rowcount{font-size:12px;color:var(--ink3);margin-left:auto}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink3);
padding:9px 10px;border-bottom:1px solid var(--line);cursor:pointer;white-space:nowrap;user-select:none}
th:hover{color:var(--ink)}
td{padding:9px 10px;border-bottom:1px solid var(--line);color:var(--ink2)}
td.n{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink);white-space:nowrap}
tr.row{cursor:pointer}
tr.row:hover td{background:var(--chip)}
tr.detail td{background:var(--chip);color:var(--ink2);font-size:13px}
.flag{color:var(--s2);font-weight:600}
.note{font-size:14px;color:var(--ink3);border-left:2px solid var(--line);padding-left:16px}
ul{color:var(--ink2);font-size:15px;padding-left:20px}
li{margin:4px 0}
#tip{position:fixed;pointer-events:none;opacity:0;background:var(--ink);color:var(--bg);font-size:12px;max-width:280px;
line-height:1.4;padding:7px 10px;border-radius:7px;transform:translate(-50%,-125%);transition:opacity .08s;z-index:30}
.stab{width:100%;border-collapse:collapse;font-size:14px}
.stab th,.stab td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left}
.stab th.n,.stab td.n{text-align:right}
.stab tr.first td{border-top:1px solid var(--line)}
.stab .nn{color:var(--ink3);font-size:12px}
.steps{width:100%;border-collapse:collapse;font-size:14px;margin:10px 0}
.steps td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.steps td:first-child{font-weight:600;color:var(--ink);white-space:nowrap}
.steps code{font-size:12px;background:var(--chip);padding:1px 6px;border-radius:5px}
footer{margin:72px 0 0;padding:22px 0 64px;border-top:1px solid var(--line);font-size:12px;color:var(--ink3)}
@media(max-width:620px){
  .site{position:static}.site .in{flex-wrap:wrap;gap:4px;padding:12px 16px}.site nav{margin:0 -8px;width:calc(100% + 16px)}
  .col,.wide{padding:0 16px}h1{font-size:31px}.dek{font-size:17px}header.page{padding-top:32px}
  .forest .row,.axis{grid-template-columns:1fr;gap:4px}.axis .ticks,.axis .ends{grid-column:1}.axis>div:first-child{display:none}
  .controls.sticky{top:0}.hide-s{display:none}.tick,.axl{font-size:26px}.panel{padding:18px 16px}}
""" + EXTRAS_CSS

JS = r"""
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
"""


def shell(file, page, title, description, body, after=""):
    nav = "".join(f'<a href="{f}"{" aria-current=page" if f == file else ""}>{label}</a>'
                  for f, label in PAGES)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{title}"><meta property="og:description" content="{description}">
<meta property="og:type" content="website"><meta name="twitter:card" content="summary">
<link rel="stylesheet" href="style.css"></head>
<body data-page="{page}"><div id="tip"></div>
<div class="site"><div class="in"><a class="brand" href="index.html">New Issue Credit Tracker</a><nav>{nav}</nav></div></div>
{body}
<div class="col"><footer>Built by James McHale from SEC EDGAR filings (424B2, 424B5, FWP) and FRED
(ICE BofA index OAS, Treasury yields). Personal project. Not investment advice.</footer></div>
<script src="data.js"></script><script src="app.js"></script>{after}</body></html>"""


def fbtn(k, v, label, first=False):
    return f"<button class='f' data-k='{k}' data-v='{v}' aria-pressed='{str(first).lower()}'>{label}</button>"


def fsel(k, first, options):
    opts = f'<option value="all">{first}</option>' + "".join(
        f'<option value="{v}">{label}</option>' for v, label in options)
    return f'<select class="fsel" data-k="{k}">{opts}</select>'


TENOR = ('<select class="bucketsel"><option value="all">Any tenor</option>'
         + "".join(f'<option value="{b}">{b}</option>' for b in BUCKETS) + "</select>")
GRADES = fbtn("grade", "all", "All", True) + fbtn("grade", "IG", "IG") + fbtn("grade", "HY", "HY")

# What each claim is testing, in market terms. Shown on the Evidence page.
EXPLAIN = {
    "sub": """In a bankruptcy, creditors are paid in order of rank. Senior unsecured holders are paid before
      subordinated holders, and junior subordinated notes (often called hybrids) come last among bondholders.
      Rating agencies notch subordinated debt below the issuer's senior rating for this reason.""",
    "secured": """Secured notes and utility first mortgage bonds are backed by specific assets, so recovery in a
      default is higher. Utilities issue most of the secured paper in this sample, and their mortgage bonds are
      usually rated a notch or two above their unsecured debt.""",
    "coc": """A change of control put lets holders sell the bonds back at 101% of face if the company is acquired
      and its rating falls below investment grade. It protects against a leveraged buyout loading the company
      with new debt. If buyers value it, bonds that carry one should price tighter.""",
    "step": """A coupon step raises the interest rate if the bonds are downgraded. It compensates holders for
      ratings risk, which is why it tends to appear when that risk is real: the step is a signal about the credit
      as much as a protection.""",
    "acq": """The use of proceeds section of a prospectus says what the money is for. Debt that funds an
      acquisition adds leverage and integration risk; refinancing swaps old debt for new. If buyers read the
      section, acquisition deals should pay a concession.""",
}


def thesis_page(card, bonds):
    claims = card["claims"]
    counts = {v: sum(1 for c in claims if c["verdict"] == v) for v in ("Holding", "Mixed", "Not holding", "Too early")}
    cls = {"Holding": "v-hold", "Mixed": "v-mixed", "Not holding": "v-not", "Too early": "v-early"}
    pills = "".join(f'<span class="pill big {cls[v]}">{n} {v.lower()}</span>' for v, n in counts.items() if n)
    body = f"""
<header class="page col">
  <p class="kicker">Thesis tracker · data through {card['as_of']}</p>
  <h1>Does the bond market price what's in the prospectus?</h1>
  <p class="dek">A prospectus spells out where a bond ranks, what backs it and what protects its holders.
  If investors read it, those terms should show up in the spread. This tracker tests five of them against
  every registered US corporate bond deal, and updates as new deals price.</p>
  <div class="verdicts">{pills}</div>
  <p class="byline">James McHale · {card['bonds']} bonds with a rating, maturity and index comparison</p>
</header>
<main class="wide">
  <h2>The test</h2>
  <p class="col" style="padding:0;margin-left:0">Each bond is compared with peers that lack the feature: first the same
  issuer's other bonds sold the same day, otherwise bonds with the same rating and maturity. The dot is the
  median difference; the bar is the range across 1,000 resamples by issuer. A bar that crosses zero means
  the data cannot yet tell.</p>
  <div class="panel forest" id="forest"></div>

  <h2>Scorecard</h2>
  <p>Each claim, its current reading and how the estimate has moved as deals arrived. Open one for every bond behind it.</p>
  <div class="cards" id="cards"></div>

  <h2>Explore</h2>
  <div class="next">
    <a href="evidence.html"><b>Evidence</b><span>Every bond behind each claim, and what the terms mean</span></a>
    <a href="market.html"><b>Market</b><span>Weekly issuance and where index spreads stand</span></a>
    <a href="deals.html"><b>Deals</b><span>All {len(bonds)} tranches, each linked to its filing</span></a>
    <a href="method.html"><b>Method</b><span>How it is measured, its limits and how it is built</span></a>
  </div>
</main>"""
    return shell("index.html", "thesis", "Does the bond market price what's in the prospectus?",
                 "A live test of whether ranking, collateral, covenants and use of proceeds show up in new issue "
                 "corporate bond spreads, read from SEC filings.", body)


def evidence_page(card, bonds):
    claims = card["claims"]
    sectors = sorted({b["sector"] or "Unknown" for b in bonds})
    links = "".join(f'<a href="#{c["key"]}">{c["claim"]}</a>' for c in claims)
    sections = ""
    for c in claims:
        verdict_cls = {"Holding": "v-hold", "Mixed": "v-mixed", "Not holding": "v-not", "Too early": "v-early"}[c["verdict"]]
        est = "n/a" if c["est"] is None else f"{c['est']:+.0f} bps"
        rng = "n/a" if c["lo"] is None else f"{c['lo']:+.0f} to {c['hi']:+.0f}"
        checks = []
        if c["ex_sf"] is not None and c["n_ex_sf"] != c["n"]:
            checks.append(f"Without specialty finance lenders (BDCs), the estimate is <b>{c['ex_sf']:+.0f} bps</b> "
                          f"across {c['n_ex_sf']} bonds.")
        if c["top_issuer"] and c["n"]:
            checks.append(f"The largest single issuer, {c['top_issuer']}, accounts for {c['top_share']:.0%} of the "
                          f"bonds. The range resamples whole issuers, so this concentration is reflected in it.")
        if c["n"] and c["issuers"] < thesis.MIN_ISSUERS:
            checks.append(f"Only {c['issuers']} issuer{'s' if c['issuers'] != 1 else ''} so far, so the verdict "
                          f"waits for at least {thesis.MIN_ISSUERS}.")
        issuer_pairs = [p for p in c["points"] if p["how"] == "issuer"]
        callout = ""
        if issuer_pairs:
            names = sorted({p["issuer"] for p in issuer_pairs})
            callout = (f'<div class="callout"><p><b>The cleanest comparison.</b> {", ".join(names)} sold bonds with '
                       f'and without this feature on the same day and maturity, which holds the company constant. '
                       f'Those {len(issuer_pairs)} bonds priced a median '
                       f'<b>{sorted(p["diff"] for p in issuer_pairs)[len(issuer_pairs) // 2]:+.0f} bps</b> '
                       f'from their own sister bonds.</p></div>')
        sections += f"""
  <section class="claim" id="{c['key']}">
    <h2>{c['claim']}</h2>
    <p><span class="pill {verdict_cls}">{c['verdict']}</span> &nbsp;<span style="color:var(--ink3);font-size:13px">
    {'Expected: wider' if c['sign'] > 0 else 'Expected: tighter'}</span></p>
    <p>{EXPLAIN[c['key']]}</p>
    <div class="facts">
      <div><div class="v">{est}</div><div class="k">median vs peers</div></div>
      <div><div class="v">{rng}</div><div class="k">range</div></div>
      <div><div class="v">{c['n']}</div><div class="k">bonds</div></div>
      <div><div class="v">{c['issuers']}</div><div class="k">issuers</div></div>
    </div>
    {callout}
    <div class="panel"><div id="strip-{c['key']}"></div>
    <p class="cap">Each dot is one bond: how many bps wider (right) or tighter (left) it priced than its peers.</p></div>
    {'<h3>Checks</h3><ul class="checks">' + ''.join(f'<li>{x}</li>' for x in checks) + '</ul>' if checks else ''}
  </section>"""
    structure_filters = (
        fsel("rank", "Any ranking", [("senior", "Senior unsecured"), ("secured", "Secured / first mortgage"),
                                     ("sub", "Subordinated")])
        + fsel("coc", "Any CoC", [("yes", "CoC put"), ("no", "No CoC put")])
        + fsel("guar", "Any guarantee", [("yes", "Guaranteed"), ("no", "Not guaranteed")])
        + (fsel("sector", "Any sector", [(x, x) for x in sectors]) if len(sectors) > 1 else ""))
    body = f"""
<header class="page col">
  <p class="kicker">Evidence</p>
  <h1>Every bond behind every claim</h1>
  <p class="dek">What each term means for a bondholder, the bonds that test it, and the checks that could
  overturn the reading.</p>
  <div class="claimnav">{links}</div>
</header>
<main class="col">{sections}
  <section class="claim" id="raw">
    <h2>All terms, unmatched</h2>
    <p>The raw medians for every structural term. These mix ratings and maturities, which is why the claims
    above compare matched peers instead. Filter to a grade and tenor to compare like with like.</p>
    <div class="controls">{GRADES}<span class="gap"></span>{TENOR}{structure_filters}</div>
    <div class="panel" style="padding:8px 12px;overflow-x:auto" id="structure"></div>
  </section>
</main>"""
    return shell("evidence.html", "evidence", "Evidence · New Issue Credit Tracker",
                 "The bonds behind each claim in the thesis, with what each prospectus term means.", body)


def market_page(bonds, checks, span):
    checked = checks.get("OK", 0) + checks.get("MISMATCH", 0)
    body = f"""
<header class="page col">
  <p class="kicker">Market</p>
  <h1>What the primary market priced</h1>
  <p class="dek">Registered corporate bond supply week by week, where index spreads stand, and which new
  deals came cheap or rich to them.</p>
  <p class="byline">{span}</p>
  <div class="stats">
    <div class="stat"><div class="v" id="count">0</div><div class="k">tranches in view</div></div>
    <div class="stat"><div class="v" id="vol">0</div><div class="k">issuance in view</div></div>
    <div class="stat"><div class="v" id="medgap">0</div><div class="k">median vs index</div></div>
    <div class="stat"><div class="v">{checks.get('OK', 0)}/{checked}</div><div class="k">pricing math verified</div></div>
  </div>
</header>
<main class="wide">
  <div class="controls">{GRADES}<span class="gap"></span>{fbtn('proceeds', 'all', 'Any use', True)}
    {fbtn('proceeds', 'acquisition', 'Acquisition')}{fbtn('proceeds', 'refinancing', 'Refinancing')}
    {fbtn('proceeds', 'other', 'Other')}{TENOR}<span id="weekchip"></span></div>

  <h2>Weekly issuance</h2>
  <p>Click a week to filter the page to it. Click again to clear.</p>
  <figure><div id="bars"></div><figcaption>Priced volume by week (week starting Monday).</figcaption></figure>

  <h2>Where the index stands</h2>
  <p>The ICE BofA option-adjusted spread for BBB and BB corporates, the benchmarks most new deals here are
  measured against. A wider index means credit is cheaper across the board.</p>
  <figure><div id="index"></div><figcaption>Index OAS in bps, last reading each week. Source: FRED.</figcaption></figure>

  <h2>Cheap or rich, by tenor</h2>
  <p>Each dot is one bond: its spread minus the matching index on the day it priced. Above the dashed line
  it paid more than comparable paper.</p>
  <figure><div id="dots"></div><div class="legend" id="legend"></div>
  <figcaption>Spread vs index in bps, by maturity bucket.</figcaption></figure>
</main>"""
    return shell("market.html", "market", "Market · New Issue Credit Tracker",
                 "Weekly registered corporate bond issuance and new issue spreads versus the ICE BofA indices.", body)


def deals_page(bonds):
    sectors = sorted({b["sector"] or "Unknown" for b in bonds})
    body = f"""
<header class="page col">
  <p class="kicker">Deals</p>
  <h1>Every tranche, from the filing</h1>
  <p class="dek">All {len(bonds)} bonds in the tracker. Sort any column, open any row for the full terms,
  the issuer's own words and a link to the source filing on EDGAR.</p>
</header>
<main class="wide">
{ASK_HTML}
  <h2>The deals</h2>
  <div class="controls sticky">{GRADES}<span class="gap"></span>{fbtn('proceeds', 'all', 'Any use', True)}
    {fbtn('proceeds', 'acquisition', 'Acquisition')}{fbtn('proceeds', 'refinancing', 'Refinancing')}
    {fbtn('proceeds', 'other', 'Other')}{TENOR}
    {fsel('rank', 'Any ranking', [('senior', 'Senior unsecured'), ('secured', 'Secured / first mortgage'), ('sub', 'Subordinated')])}
    {fsel('coc', 'Any CoC', [('yes', 'CoC put'), ('no', 'No CoC put')])}
    {fsel('sector', 'Any sector', [(x, x) for x in sectors]) if len(sectors) > 1 else ''}
    <input class="searchbox" type="search" placeholder="Search issuer"><span class="rowcount" id="rowcount"></span></div>
  <div class="tablewrap"><div id="table"></div></div>
</main>"""
    return shell("deals.html", "deals", "Deals · New Issue Credit Tracker",
                 "Every registered corporate bond tranche in the tracker, with terms and source filings.", body, ASK_JS)


def method_page(bonds, checks, ranked):
    body = f"""
<header class="page col">
  <p class="kicker">Method</p>
  <h1>How the tracker works</h1>
  <p class="dek">Where the numbers come from, how the thesis is tested, and what the data cannot tell you.</p>
</header>
<main class="col">
{recap_html()}
  <h2>How each claim is tested</h2>
  <ul>
    <li><b>Spread vs index.</b> Each bond's spread to Treasuries minus the ICE BofA option-adjusted index spread for
    its rating on the day it priced. Positive means it came wider, which is cheaper for the buyer.</li>
    <li><b>Peers.</b> A bond with the feature is compared first with the same issuer's bonds sold the same day in
    the same maturity bucket, on raw spread, which holds the company constant. Failing that, with bonds that lack
    the feature in the same rating bucket (AA, A, BBB, BB) and maturity bucket, on spread vs index.</li>
    <li><b>Holding ranking constant.</b> The change of control and coupon step claims compare senior unsecured bonds
    only, so they do not pick up subordination or collateral.</li>
    <li><b>Range.</b> The 5th to 95th percentile of the median across 1,000 resamples. Issuers are resampled whole,
    because twelve bonds from one deal are one piece of evidence, not twelve.</li>
    <li><b>Verdict.</b> <i>Holding</i> if the whole range sits on the expected side of zero, <i>Not holding</i> if it
    sits on the other side, <i>Mixed</i> if it crosses zero. <i>Too early</i> below {thesis.MIN_MATCHED} bonds or
    {thesis.MIN_ISSUERS} issuers.</li>
    <li><b>Trend.</b> The estimate recomputed with only the deals priced by the end of each week, so you can see
    whether a reading is settling or still moving.</li>
  </ul>

  <h2>Limits</h2>
  <ul>
    <li>Registered deals only. Most high yield is sold under Rule 144A and never reaches EDGAR, so HY samples are small.</li>
    <li>Index spreads are matched by rating category, not exact notch, and do not adjust for sector or call features.</li>
    <li>Covenants are not assigned at random: issuers offer protection when buyers ask for it, so a feature's
    premium partly reflects the kind of company that offers it.</li>
    <li>Filings do not disclose order books, price talk or the new issue concession.</li>
    <li>{ranked} of {len(bonds)} tranches have a stated ranking. {checks.get('MISMATCH', 0)} failed the pricing
    math check and are flagged, not discarded.</li>
  </ul>

  <h2>How it is built</h2>
  <table class="steps">
    <tr><td>Find</td><td><code>backfill.py</code> scans EDGAR free writing prospectuses for bond pricing term sheets.</td></tr>
    <tr><td>Extract</td><td><code>extract.py</code> has Claude pull each tranche's terms, using only numbers printed in the filing.</td></tr>
    <tr><td>Structure</td><td><code>structure.py</code> finds each deal's prospectus supplement and reads ranking, guarantees,
    change of control and coupon steps, checked against the notes' own titles.</td></tr>
    <tr><td>Proceeds</td><td><code>proceeds.py</code> classifies use of proceeds with a verbatim quote.</td></tr>
    <tr><td>Check</td><td>Every tranche must satisfy benchmark yield + spread = yield. <code>dedupe.py</code> merges a deal filed twice.</td></tr>
    <tr><td>Enrich</td><td><code>fred.py</code> and <code>enrich.py</code> pull index spreads and Treasury yields from FRED.</td></tr>
    <tr><td>Test</td><td><code>thesis.py</code> runs the matched comparisons and resampling behind the scorecard.</td></tr>
    <tr><td>Write</td><td><code>agent.py</code> drafts the weekly note, limited to numbers its database queries return.</td></tr>
    <tr><td>Publish</td><td><code>report.py</code> builds this site.</td></tr>
  </table>
</main>"""
    return shell("method.html", "method", "Method · New Issue Credit Tracker",
                 "How the new issue credit tracker reads SEC filings and tests its thesis.", body)


def build():
    conn = db.connect()
    bonds = collect(conn)
    card = thesis.scorecard(conn)
    checks = {}
    for b in bonds:
        checks[b["check"]] = checks.get(b["check"], 0) + 1
    dates = [b["priced"] for b in bonds if b["priced"]]
    span = f"{min(dates)} to {max(dates)}" if dates else "no deals yet"
    start = (date.fromisoformat(min(dates)) - timedelta(days=56)).isoformat() if dates else "2000-01-01"
    ranked = sum(1 for b in bonds if b["rank"] and b["rank"] != "not_stated")

    SITE.mkdir(exist_ok=True)
    (SITE / "style.css").write_text(CSS)
    (SITE / "app.js").write_text(JS)
    (SITE / "data.js").write_text(
        f"const BONDS={json.dumps(bonds)};\nconst BUCKETS={json.dumps(BUCKETS)};\n"
        f"const THESIS={json.dumps(card)};\nconst MARKET={json.dumps(index_spreads(conn, start))};\n")
    pages = {
        "index.html": thesis_page(card, bonds),
        "evidence.html": evidence_page(card, bonds),
        "market.html": market_page(bonds, checks, span),
        "deals.html": deals_page(bonds),
        "method.html": method_page(bonds, checks, ranked),
    }
    for name, html in pages.items():
        (SITE / name).write_text(html)
    size = sum(f.stat().st_size for f in SITE.iterdir()) / 1024
    print(f"Wrote {len(pages)} pages to {SITE.name}/ ({size:.0f} KB) with {len(bonds)} tranches")


if __name__ == "__main__":
    build()
