"""
Two pieces report.py puts on the site:

  1. the agent's weekly recap, if agent.py has written recap.md (Method page)
  2. an "Ask the data" box that filters and counts the table, no model or API key (Deals page)

Run:  python report.py      (python extras.py does the same)
"""
import html
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECAP = HERE / "recap.md"

CSS = """
/* extras */
.recap{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:22px 26px}
.recap p{color:var(--ink);font-size:16px;line-height:1.7;margin:0 0 12px}
.recap .stamp{font-size:12px;color:var(--ink3);border-top:1px solid var(--line);padding-top:10px;margin:14px 0 0}
.ask{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0 6px}
#askbox{flex:1;min-width:260px;border-radius:8px;padding:9px 13px}
.askbtn{border-radius:8px;background:var(--ink);color:var(--bg);border:1px solid var(--ink);
padding:9px 16px;cursor:pointer;font-size:13px}
.examples{display:flex;gap:7px;flex-wrap:wrap;margin:2px 0 4px}
.ex{font-size:12px;color:var(--ink2);background:var(--chip);border:none;border-radius:999px;
padding:5px 11px;cursor:pointer}
.ex:hover{color:var(--ink)}
#askout{font-size:15px;color:var(--ink);background:var(--chip);border-radius:8px;
padding:12px 14px;margin:8px 0 0;display:none}
"""

ASK_HTML = """
  <h2>Ask the data</h2>
  <p>Type a question. This filters and counts the table below. It does not use a language model,
  so it can only report what is already here.</p>
  <div class="ask">
    <input id="askbox" type="search" placeholder="e.g. widest BBB deals, or how much did Dell raise">
    <button class="askbtn" id="askgo">Answer</button>
  </div>
  <div class="examples">
    <button class="ex">widest deals vs index</button>
    <button class="ex">tightest acquisition deals</button>
    <button class="ex">biggest deals in 15y+</button>
    <button class="ex">how much HY issuance</button>
    <button class="ex">how many refinancing deals</button>
  </div>
  <p id="askout"></p>
"""

ASK_JS = r"""
<script>
(function(){
  const out=document.getElementById('askout');
  const box=document.getElementById('askbox');
  const MONTHS=['january','february','march','april','may','june','july','august',
                'september','october','november','december'];
  const STOP=['deal','deals','bond','bonds','much','many','what','which','that','with','from',
    'index','issuance','spread','spreads','tranche','tranches','priced','pricing','wide','widest',
    'tight','tightest','cheap','cheapest','rich','richest','most','biggest','largest','total','raise','raised'];

  function answer(q){
    const text=(q||'').toLowerCase().trim();
    if(!text) return;
    out.style.display='block';

    F.grade='all'; F.proceeds='all'; F.bucket='all'; F.week=null; F.q='';
    F.rank='all'; F.coc='all'; F.guar='all'; F.sector='all';
    document.querySelectorAll('select.fsel').forEach(s=>s.value='all');
    const scope=[];
    if(/\bhy\b|high.?yield|junk/.test(text)){F.grade='HY'; scope.push('high yield');}
    else if(/\big\b|investment.?grade/.test(text)){F.grade='IG'; scope.push('investment grade');}
    if(/acquisition|m&a|merger/.test(text)){F.proceeds='acquisition'; scope.push('acquisition-funded');}
    else if(/refinanc|repay|redeem/.test(text)){F.proceeds='refinancing'; scope.push('refinancing');}
    BUCKETS.forEach(b=>{if(text.includes(b.toLowerCase())){F.bucket=b; scope.push(b);}});

    let month=null;
    MONTHS.forEach((m,i)=>{if(text.includes(m)){month=i+1; scope.push(m[0].toUpperCase()+m.slice(1));}});

    const issuers=[...new Set(BONDS.map(b=>(b.issuer||'').toLowerCase()))];
    const words=text.split(/[^a-z0-9&.-]+/).filter(w=>w.length>3 && STOP.indexOf(w)<0);
    for(const w of words){ if(issuers.some(i=>i.indexOf(w)>=0)){ F.q=w; scope.push('issuer matching "'+w+'"'); break; } }

    const wantsTotal=/how much|total|volume|raised|sum/.test(text);
    const wantsCount=/how many|count|number of/.test(text);
    const tight=/tight|rich|through|inside/.test(text);
    const big=/biggest|largest|size/.test(text);

    if(typeof sortKey!=='undefined'){ sortKey = big ? 'size' : 'gap'; sortDir = tight ? 1 : -1; }
    render();
    document.querySelectorAll('.searchbox, #search').forEach(i=>i.value=F.q);
    document.querySelectorAll('.bucketsel, #bucket').forEach(s=>s.value=F.bucket);

    let rows=visible();
    if(month) rows=rows.filter(b=>b.priced && Number(b.priced.slice(5,7))===month);
    const where = scope.length? scope.join(', ') : 'all tranches';
    const vol=rows.reduce((a,b)=>a+(b.size||0),0);
    const gaps=rows.filter(b=>b.gap!=null).map(b=>b.gap);

    if(!rows.length){ out.textContent='Nothing in the data matches that.'; return; }
    if(wantsTotal){
      out.innerHTML='<b>'+money(vol)+'</b> across '+rows.length+' tranches ('+where+').';
    } else if(wantsCount){
      out.innerHTML='<b>'+rows.length+'</b> tranches, '+money(vol)+' ('+where+').';
    } else {
      const sorted=[...rows].sort((a,b)=>{
        const x = big ? (a.size||0) : (a.gap==null?-1e9:a.gap);
        const y = big ? (b.size||0) : (b.gap==null?-1e9:b.gap);
        return tight && !big ? x-y : y-x;});
      const top=sorted.slice(0,3).map(b=>b.issuer+' '+(big?money(b.size):pm(b.gap)+' bps')).join(', ');
      const label = big ? 'Largest' : (tight ? 'Tightest to index' : 'Widest to index');
      out.innerHTML=label+', '+where+': <b>'+top+'</b>. '+rows.length+' tranches'
        +(gaps.length? ', median '+pm(med(gaps))+' bps vs index.' : '.');
    }
    if(month) out.innerHTML+=' <span style="color:var(--ink3)">The month applies to this answer, not the table.</span>';
    document.getElementById('table').scrollIntoView({behavior:'smooth', block:'start'});
  }

  document.getElementById('askgo').onclick=()=>answer(box.value);
  box.onkeydown=e=>{if(e.key==='Enter')answer(box.value);};
  document.querySelectorAll('.ex').forEach(b=>b.onclick=()=>{box.value=b.textContent; answer(b.textContent);});
})();
</script>
"""


def recap_html():
    if not RECAP.exists():
        return ""
    raw = RECAP.read_text().splitlines()
    stamp = next((l.replace("<!--", "").replace("-->", "").strip() for l in raw if l.startswith("<!--")), "")
    body = "".join(f"<p>{html.escape(l.strip())}</p>" for l in raw
                   if l.strip() and not l.startswith("<!--"))
    if not body:
        return ""
    return (f'  <h2>Latest week in the data</h2>\n  <div class="recap">{body}'
            f'<p class="stamp">Written by agent.py, which may only state numbers its database '
            f'queries returned. Covering {html.escape(stamp)}.</p></div>\n')


def main():
    import report
    report.build()


if __name__ == "__main__":
    main()
