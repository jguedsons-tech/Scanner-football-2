import os, math
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='Scanner Football v2', page_icon='⚽', layout='wide')

# Atualização automática nativa do Streamlit (sem streamlit-autorefresh).
if hasattr(st, 'fragment'):
    @st.fragment(run_every='5m')
    def _auto_refresh():
        st.rerun()
    _auto_refresh()


st.title('⚽ Scanner Football v2')
st.caption('Props de futebol • atualização automática a cada 5 minutos')

def secret(name, default=''):
    try: return st.secrets.get(name, default)
    except Exception: return os.getenv(name, default)

FD_TOKEN = secret('FOOTBALL_DATA_API_TOKEN')
AF_KEY = secret('API_FOOTBALL_KEY')
AF_HOST = secret('API_FOOTBALL_HOST', 'v3.football.api-sports.io')
TSDB_KEY = secret('THESPORTSDB_API_KEY', '3')

def api_football(endpoint, params):
    if not AF_KEY: return None, 'API_FOOTBALL_KEY não configurada'
    try:
        r=requests.get(f'https://{AF_HOST}/{endpoint}',headers={'x-apisports-key':AF_KEY},params=params,timeout=20)
        if r.status_code!=200: return None, f'HTTP {r.status_code}'
        return r.json(), None
    except Exception as e: return None, str(e)

def football_data(path, params=None):
    if not FD_TOKEN: return None, 'FOOTBALL_DATA_API_TOKEN não configurado'
    try:
        r=requests.get('https://api.football-data.org/v4/'+path,headers={'X-Auth-Token':FD_TOKEN},params=params or {},timeout=20)
        if r.status_code!=200: return None, f'HTTP {r.status_code}'
        return r.json(), None
    except Exception as e: return None, str(e)

def poisson_over(mean,line):
    if not np.isfinite(mean): return np.nan
    k=int(math.floor(line)); cdf=sum(math.exp(-mean)*mean**i/math.factorial(i) for i in range(k+1))
    return max(0,min(1,1-cdf))

def fair(p): return round(1/p,2) if p>0 else np.nan
def ev(p,o): return round((p*o-1)*100,2) if o and o>1 else np.nan
def cls(p,e=np.nan):
    if not np.isfinite(p): return 'SEM DADOS'
    if p>=.80 and (not np.isfinite(e) or e>=3): return '🔥 MUITO FORTE'
    if p>=.72 and (not np.isfinite(e) or e>=0): return '🟢 FORTE'
    if p>=.62 and (not np.isfinite(e) or e>=0): return '🟡 INTERESSANTE'
    return '⚪ NEUTRA'

def demo():
    return pd.DataFrame([
      ['Demo FC x Analytics FC','Escanteios','Over 22.5','Over 20.5','7/10','4/5',25.8,78,1.28,1.91,48.98,'🔥 MUITO FORTE'],
      ['Demo FC x Analytics FC','Gols','Over 1.5','Over 0.5','8/10','4/5',2.7,82,1.22,1.55,27.10,'🔥 MUITO FORTE'],
      ['Demo FC x Analytics FC','Cartões','Over 3.5','Over 2.5','7/10','4/5',4.6,75,1.33,1.80,35.00,'🟢 FORTE'],
    ],columns=['Jogo','Mercado','Linha principal','Linha alternativa','L10','L5','Média','Probabilidade estimada','Odd justa','Odd mercado','EV','Classificação'])

with st.sidebar:
    st.header('⚙️ Configuração')
    fonte=st.selectbox('Fonte',['Auto','API-Football','football-data.org','Demonstração'])
    minprob=st.slider('Probabilidade mínima (%)',50,95,70)
    onlyev=st.checkbox('Somente EV positivo')
    fallback=st.checkbox('Permitir demonstração/fallback',True)
    st.divider(); st.write('🔄 Atualização: **5 minutos**'); st.write('🕒',datetime.now().strftime('%d/%m/%Y %H:%M:%S'))

fixtures=[]; errors=[]
if fonte in ['Auto','API-Football'] and AF_KEY:
    data,err=api_football('fixtures',{'date':datetime.now().strftime('%Y-%m-%d')})
    if data:
        for x in data.get('response',[]):
            fixtures.append({'id':x['fixture']['id'],'home':x['teams']['home']['name'],'away':x['teams']['away']['name'],'league':x['league']['name'],'date':x['fixture']['date']})
    elif err: errors.append('API-Football: '+err)
if not fixtures and fonte in ['Auto','football-data.org'] and FD_TOKEN:
    data,err=football_data('competitions/PL/matches',{'dateFrom':datetime.now().strftime('%Y-%m-%d'),'dateTo':(datetime.now()+timedelta(days=2)).strftime('%Y-%m-%d')})
    if data:
        for x in data.get('matches',[]): fixtures.append({'id':x['id'],'home':x['homeTeam']['name'],'away':x['awayTeam']['name'],'league':x['competition']['name'],'date':x['utcDate']})
    elif err: errors.append('football-data.org: '+err)

props=demo() if not fixtures and fallback else pd.DataFrame(columns=['Jogo','Mercado','Linha principal','Linha alternativa','L10','L5','Média','Probabilidade estimada','Odd justa','Odd mercado','EV','Classificação'])

c1,c2,c3,c4=st.columns(4); c1.metric('Partidas',len(fixtures)); c2.metric('Mercados','Escanteios / Gols / Cartões'); c3.metric('Refresh','5 min'); c4.metric('Formato','Props')
if errors:
    with st.expander('Avisos'): [st.warning(x) for x in errors]

st.subheader('📊 Scanner de Props')
if not props.empty:
    props=props[pd.to_numeric(props['Probabilidade estimada'],errors='coerce')>=minprob]
    if onlyev: props=props[pd.to_numeric(props['EV'],errors='coerce')>0]
    st.dataframe(props,use_container_width=True,hide_index=True)
else:
    st.info('Nenhuma prop calculável com estatísticas reais. Configure uma API que forneça estatísticas de eventos para ativar L10/L5 e médias reais.')

st.subheader('📐 Campos do scanner')
st.markdown('**Linha principal · Linha alternativa · L10 · L5 · Média · Probabilidade estimada · Odd justa · EV · Classificação**')
st.caption('Probabilidades são estimativas estatísticas e não garantem resultados.')
