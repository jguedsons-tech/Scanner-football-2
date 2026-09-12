import os, math, requests, pandas as pd, streamlit as st
from datetime import date, timedelta

st.set_page_config(page_title='Football Scanner Pro — Sportmonks', page_icon='⚽', layout='wide')
BASE_URL='https://api.sportmonks.com/v3/football'
TOKEN=st.secrets.get('SPORTMONKS_API_TOKEN', os.getenv('SPORTMONKS_API_TOKEN','')).strip()

@st.cache_data(ttl=300, show_spinner=False)
def api(path, params=None):
    if not TOKEN: raise RuntimeError('SPORTMONKS_API_TOKEN não configurado.')
    p=dict(params or {}); p['api_token']=TOKEN
    r=requests.get(f'{BASE_URL}/{path.lstrip("/")}', params=p, timeout=25)
    if r.status_code != 200: raise RuntimeError(f'HTTP {r.status_code}: {r.text[:400]}')
    return r.json()

def rows(x):
    d=x.get('data',[]); return d if isinstance(d,list) else [d]

def pname(f, side):
    ps=f.get('participants') or []
    for p in ps:
        if (p.get('meta') or {}).get('location') == side: return p.get('name','')
    if len(ps)>=2: return ps[0].get('name','') if side=='home' else ps[1].get('name','')
    return ''

def pid(f, side):
    ps=f.get('participants') or []
    for p in ps:
        if (p.get('meta') or {}).get('location') == side: return p.get('id')
    if len(ps)>=2: return ps[0].get('id') if side=='home' else ps[1].get('id')
    return None

def goals(f, side):
    for s in f.get('scores') or []:
        sc=s.get('score') or {}
        if sc.get('participant')==side and s.get('description')=='CURRENT': return sc.get('goals')
    for s in f.get('scores') or []:
        sc=s.get('score') or {}
        if sc.get('participant')==side: return sc.get('goals')
    return None

def by_date(d):
    return rows(api(f'fixtures/date/{d}', {'include':'participants;league;state;scores'}))

def window(a,b):
    out=[]; d=a
    while d<=b:
        try: out += by_date(d.isoformat())
        except Exception: pass
        d += timedelta(days=1)
    return out

def finished(f):
    s=f.get('state') or {}; n=(s.get('short_name') or s.get('name') or '').lower()
    return 'ft' in n or 'finished' in n or (goals(f,'home') is not None and goals(f,'away') is not None)

def recent(team_id, n=8):
    fs=window(date.today()-timedelta(days=120), date.today()-timedelta(days=1))
    fs=[f for f in fs if finished(f) and team_id in {p.get('id') for p in (f.get('participants') or [])}]
    fs.sort(key=lambda x:x.get('starting_at',''), reverse=True); fs=fs[:n]
    vals=[]
    for f in fs:
        hg,ag=goals(f,'home'),goals(f,'away')
        if hg is None or ag is None: continue
        home=any(p.get('id')==team_id and (p.get('meta') or {}).get('location')=='home' for p in f.get('participants',[]))
        vals.append({'Data':(f.get('starting_at') or '')[:10], 'Jogo':f"{pname(f,'home')} x {pname(f,'away')}", 'GF':float(hg if home else ag), 'GA':float(ag if home else hg), 'Casa':home})
    if not vals: return {'games':[], 'hgf':1.25,'hga':1.25,'agf':1.05,'aga':1.25,'gf':1.2,'ga':1.2}
    df=pd.DataFrame(vals); h=df[df.Casa]; a=df[~df.Casa]
    return {'games':vals,'hgf':h.GF.mean() if len(h) else df.GF.mean(),'hga':h.GA.mean() if len(h) else df.GA.mean(),'agf':a.GF.mean() if len(a) else df.GF.mean(),'aga':a.GA.mean() if len(a) else df.GA.mean(),'gf':df.GF.mean(),'ga':df.GA.mean()}

def poisson(lh,la):
    ph=[math.exp(-lh)*lh**k/math.factorial(k) for k in range(9)]; pa=[math.exp(-la)*la**k/math.factorial(k) for k in range(9)]
    out={'Casa':0,'Empate':0,'Fora':0,'BTTS Sim':0,'Over 1.5':0,'Over 2.5':0,'Over 3.5':0}
    for h,x in enumerate(ph):
        for a,y in enumerate(pa):
            p=x*y; t=h+a
            out['Casa']+=p*(h>a); out['Empate']+=p*(h==a); out['Fora']+=p*(h<a); out['BTTS Sim']+=p*(h>0 and a>0)
            out['Over 1.5']+=p*(t>=2); out['Over 2.5']+=p*(t>=3); out['Over 3.5']+=p*(t>=4)
    s=out['Casa']+out['Empate']+out['Fora']; out['Casa']/=s; out['Empate']/=s; out['Fora']/=s; out['BTTS Não']=1-out['BTTS Sim']
    out['Under 1.5']=1-out['Over 1.5']; out['Under 2.5']=1-out['Over 2.5']; out['Under 3.5']=1-out['Over 3.5']
    return out

def analyze(f):
    h,a=pid(f,'home'),pid(f,'away')
    if not h or not a: return None
    hs,vs=recent(h),recent(a)
    lh=max(.05,.55*hs['hgf']+.45*vs['aga']); la=max(.05,.55*vs['agf']+.45*hs['hga'])
    return {'home':pname(f,'home'),'away':pname(f,'away'),'lh':lh,'la':la,'probs':poisson(lh,la),'hs':hs,'vs':vs}

def render(m, threshold=.55):
    st.dataframe(pd.DataFrame([{'Mercado':k,'Probabilidade':f'{v*100:.1f}%'} for k,v in sorted(m['probs'].items(), key=lambda x:x[1], reverse=True)]), use_container_width=True, hide_index=True)
    picks=[(k,v) for k,v in m['probs'].items() if v>=threshold]; picks.sort(key=lambda x:x[1], reverse=True)
    if picks: st.success('Sugestões: ' + ' | '.join(f'{k} {v*100:.1f}%' for k,v in picks[:5]))

st.title('⚽ Football Scanner Pro — Sportmonks')
st.caption('Poisson + forma recente. Probabilidades são estimativas, não garantias.')
if not TOKEN:
    st.error('Configure SPORTMONKS_API_TOKEN nos Secrets do Streamlit Cloud.'); st.stop()
try: by_date(date.today().isoformat()); st.success('Sportmonks conectado.')
except Exception as e: st.error(str(e)); st.stop()

t1,t2,t3,t4=st.tabs(['🔎 Buscar jogo','📡 Scanner automático','📊 Análise','ℹ️ Configuração'])
with t1:
    q=st.text_input('Time', placeholder='Palmeiras, Flamengo, Liverpool...'); days=st.slider('Próximos dias',1,30,7)
    if st.button('Buscar partidas', type='primary'):
        fs=window(date.today(),date.today()+timedelta(days=days)); q=q.lower().strip(); fs=[f for f in fs if q in f'{pname(f,"home")} {pname(f,"away")}'.lower()]
        if not fs: st.warning('Nenhuma partida encontrada.')
        for f in fs:
            m=analyze(f)
            if m:
                st.subheader(f'{m["home"]} x {m["away"]}'); st.caption(f.get('starting_at','')); render(m)
with t2:
    horizon=st.slider('Janela',1,7,2); threshold=st.slider('Probabilidade mínima',50,90,60)/100
    if st.button('🚀 Executar scanner', type='primary'):
        fs=window(date.today(),date.today()+timedelta(days=horizon)); rec=[]; seen=set()
        bar=st.progress(0); total=max(1,len(fs))
        for i,f in enumerate(fs):
            if f.get('id') in seen: continue
            seen.add(f.get('id'))
            try:
                m=analyze(f)
                if m:
                    for k,v in sorted(m['probs'].items(), key=lambda x:x[1], reverse=True):
                        if v>=threshold: rec.append({'Data':f.get('starting_at',''),'Jogo':f'{m["home"]} x {m["away"]}','Mercado':k,'Probabilidade %':round(v*100,1),'Exp. gols casa':round(m['lh'],2),'Exp. gols fora':round(m['la'],2)})
            except Exception: pass
            bar.progress(min(1,(i+1)/total))
        if rec:
            df=pd.DataFrame(rec).sort_values('Probabilidade %',ascending=False); st.dataframe(df,use_container_width=True,hide_index=True); st.download_button('⬇️ CSV',df.to_csv(index=False).encode('utf-8-sig'),'scanner.csv','text/csv')
        else: st.warning('Nenhuma sugestão atingiu o limite.')
with t3:
    q2=st.text_input('Buscar jogo', placeholder='Ex.: Palmeiras x Flamengo')
    if st.button('Analisar jogo'):
        fs=window(date.today(),date.today()+timedelta(days=30)); fs=[f for f in fs if q2.lower().strip() in f'{pname(f,"home")} {pname(f,"away")}'.lower()]
        if not fs: st.warning('Jogo não localizado.')
        else:
            m=analyze(fs[0]); st.subheader(f'{m["home"]} x {m["away"]}'); st.metric('Exp. gols mandante',f'{m["lh"]:.2f}'); st.metric('Exp. gols visitante',f'{m["la"]:.2f}'); render(m,.55); st.write('Últimos jogos do mandante'); st.dataframe(pd.DataFrame(m['hs']['games']),use_container_width=True,hide_index=True); st.write('Últimos jogos do visitante'); st.dataframe(pd.DataFrame(m['vs']['games']),use_container_width=True,hide_index=True)
with t4:
    st.markdown('''### Streamlit Cloud\nNo GitHub, mantenha `app.py` e `requirements.txt`. Em **Settings → Secrets**:\n\n```toml\nSPORTMONKS_API_TOKEN = "SEU_TOKEN"\n```\n\nO scanner usa partidas reais retornadas pela Sportmonks e calcula 1X2, BTTS e Over/Under. Quando não há amostra suficiente, ele usa uma média de referência; isso é explicitado no código e não representa dado real da partida.''')
