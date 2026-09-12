import os, math, re
from datetime import datetime, timedelta, date, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Global Football Scanner — Live + Pré-jogo", page_icon="⚽", layout="wide")

TSDB_KEY = os.getenv("THESPORTSDB_API_KEY", "123")
TSDB_BASE = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"
FD_TOKEN = os.getenv("FOOTBALL_DATA_API_TOKEN", "")
FD_BASE = "https://api.football-data.org/v4"
FD5_TOKEN = os.getenv("FIVEDOLLAR_FOOTBALL_API_KEY", "")
FD5_BASE = "https://api.5dollarfootballapi.com/v1"
OPENFOOT_TOKEN = os.getenv("OPENFOOT_API_KEY", "")
OPENFOOT_BASE = "https://openfootapi.com/v1"
TIMEOUT = 15
CACHE_TTL = 1800
CALENDAR_TTL = 50
BRT = ZoneInfo("America/Sao_Paulo")

LIVE_STATUSES = {"live", "in_play", "inplay", "1h", "2h", "ht", "et", "extra_time", "penalties", "pen"}
FINAL_STATUSES = {"finished", "ft", "aet", "full_time", "cancelled", "canceled", "postponed", "abandoned", "suspended"}
PRE_STATUSES = {"scheduled", "not_started", "ns", "timed", "upcoming", "fixture", ""}


def safe_float(v, default=None):
    try:
        if v is None or v == "": return default
        return float(v)
    except Exception: return default


def pct(x): return f"{100*x:.1f}%"


def norm_status(s: Any) -> str:
    return str(s or "").strip().lower().replace("-", "_").replace(" ", "_")


def parse_kickoff(e: Dict[str, Any]) -> Optional[datetime]:
    raw = e.get("kickoff")
    if isinstance(raw, datetime): return raw.astimezone(BRT)
    if raw:
        try:
            s = str(raw).replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(BRT)
        except Exception: pass
    d, t = e.get("date"), e.get("time")
    if d and t:
        try:
            # APIs that expose date/time without offset are treated as UTC.
            dt = datetime.fromisoformat(f"{d}T{t[:8]}").replace(tzinfo=timezone.utc)
            return dt.astimezone(BRT)
        except Exception: pass
    return None


def classify_event(e: Dict[str, Any]) -> str:
    s = norm_status(e.get("status"))
    if s in LIVE_STATUSES or e.get("home_score") is not None and s not in FINAL_STATUSES and s not in PRE_STATUSES:
        # Unknown non-final status with a score is most likely live.
        if s not in FINAL_STATUSES: return "AO VIVO"
    if s in FINAL_STATUSES: return "FINALIZADO"
    ko = parse_kickoff(e)
    if ko and ko <= datetime.now(timezone.utc).astimezone(BRT):
        return "AO VIVO"
    return "PRÓXIMO"


def poisson_pmf(k, lam):
    if lam <= 0: return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def model_probs(lh, la):
    m = [[poisson_pmf(i, lh)*poisson_pmf(j, la) for j in range(11)] for i in range(11)]
    home = sum(m[i][j] for i in range(11) for j in range(11) if i > j)
    draw = sum(m[i][j] for i in range(11) for j in range(11) if i == j)
    away = sum(m[i][j] for i in range(11) for j in range(11) if i < j)
    btts = sum(m[i][j] for i in range(1,11) for j in range(1,11))
    out = {"Casa":home,"Empate":draw,"Fora":away,"BTTS Sim":btts,"BTTS Não":1-btts}
    for line in (.5,1.5,2.5,3.5,4.5):
        threshold=int(line-.5)
        under=sum(m[i][j] for i in range(11) for j in range(11) if i+j<=threshold)
        out[f"Over {line}"]=1-under; out[f"Under {line}"]=under
    return out


def request_json(url, headers=None, params=None):
    try:
        r=requests.get(url,headers=headers or {},params=params or {},timeout=TIMEOUT)
        return r.json() if r.status_code==200 else None
    except Exception: return None

# ---------- Sources ----------
@st.cache_data(ttl=CALENDAR_TTL, show_spinner=False)
def tsdb_day(day):
    return (request_json(f"{TSDB_BASE}/eventsday.php",params={"d":day,"s":"Soccer"}) or {}).get("events") or []

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def tsdb_team_search(name):
    return (request_json(f"{TSDB_BASE}/searchteams.php",params={"t":name}) or {}).get("teams") or []

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def tsdb_last(team_id):
    return (request_json(f"{TSDB_BASE}/eventslast.php",params={"id":team_id}) or {}).get("results") or []

def normalize_tsdb_event(e):
    return {"id":str(e.get("idEvent","")),"date":e.get("dateEvent") or "","time":e.get("strTime") or "","league":e.get("strLeague") or "","country":e.get("strCountry") or "","home":e.get("strHomeTeam") or "","away":e.get("strAwayTeam") or "","home_id":str(e.get("idHomeTeam") or ""),"away_id":str(e.get("idAwayTeam") or ""),"home_score":safe_float(e.get("intHomeScore")),"away_score":safe_float(e.get("intAwayScore")),"status":e.get("strStatus") or "","source":"TheSportsDB","kickoff":None}

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fd_competitions():
    if not FD_TOKEN:return []
    return (request_json(f"{FD_BASE}/competitions",headers={"X-Auth-Token":FD_TOKEN}) or {}).get("competitions") or []

@st.cache_data(ttl=CALENDAR_TTL, show_spinner=False)
def fd_matches(comp,start,end):
    if not FD_TOKEN:return []
    data=request_json(f"{FD_BASE}/competitions/{comp}/matches",headers={"X-Auth-Token":FD_TOKEN},params={"dateFrom":start,"dateTo":end})
    return (data or {}).get("matches") or []

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fd_team_matches(team_id):
    if not FD_TOKEN:return []
    end=date.today(); start=end-timedelta(days=365)
    return (request_json(f"{FD_BASE}/teams/{team_id}/matches",headers={"X-Auth-Token":FD_TOKEN},params={"dateFrom":start.isoformat(),"dateTo":end.isoformat(),"status":"FINISHED"}) or {}).get("matches") or []

def normalize_fd_event(e):
    score=e.get("score") or {}; full=score.get("fullTime") or {}; comp=e.get("competition") or {}; area=comp.get("area") or {}; h=e.get("homeTeam") or {}; a=e.get("awayTeam") or {}
    raw=e.get("utcDate") or ""
    ko=None
    try: ko=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except Exception: pass
    return {"id":str(e.get("id","")),"date":raw[:10],"time":raw[11:16],"league":comp.get("name") or "","country":area.get("name") or "","home":h.get("name") or "","away":a.get("name") or "","home_id":str(h.get("id") or ""),"away_id":str(a.get("id") or ""),"home_score":safe_float(full.get("home")),"away_score":safe_float(full.get("away")),"status":e.get("status") or "","source":"football-data.org","kickoff":ko}

@st.cache_data(ttl=CALENDAR_TTL, show_spinner=False)
def openfoot_matches(day):
    headers={"Accept":"application/json"}
    if OPENFOOT_TOKEN: headers["Authorization"]=f"Bearer {OPENFOOT_TOKEN}"
    return (request_json(f"{OPENFOOT_BASE}/matches",headers=headers,params={"date":day}) or {}).get("data") or []

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def openfoot_team_search(name):
    headers={"Accept":"application/json"}
    if OPENFOOT_TOKEN: headers["Authorization"]=f"Bearer {OPENFOOT_TOKEN}"
    rows=(request_json(f"{OPENFOOT_BASE}/search",headers=headers,params={"q":name}) or {}).get("data") or []
    return [r for r in rows if r.get("type") in ("team","club")] or rows

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def openfoot_team_matches(team_id):
    headers={"Accept":"application/json"}
    if OPENFOOT_TOKEN: headers["Authorization"]=f"Bearer {OPENFOOT_TOKEN}"
    return (request_json(f"{OPENFOOT_BASE}/matches",headers=headers,params={"team":team_id,"status":"finished"}) or {}).get("data") or []

def normalize_openfoot_event(e):
    h=e.get("homeTeam") or {}; a=e.get("awayTeam") or {}; score=e.get("score") or {}; full=score.get("fullTime") or score.get("fulltime") or score
    raw=e.get("kickoffAt") or e.get("date") or ""; ko=None
    try: ko=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
    except Exception: pass
    comp=e.get("competition")
    league=comp.get("name") if isinstance(comp,dict) else (e.get("competitionName") or "")
    return {"id":str(e.get("id","")),"date":str(raw)[:10],"time":str(raw)[11:16],"league":league or "","country":"","home":h.get("name") or e.get("homeTeamName") or "","away":a.get("name") or e.get("awayTeamName") or "","home_id":str(h.get("id") or ""),"away_id":str(a.get("id") or ""),"home_score":safe_float(full.get("home")),"away_score":safe_float(full.get("away")),"status":e.get("status") or "","source":"OpenFootAPI","kickoff":ko}

@st.cache_data(ttl=CALENDAR_TTL, show_spinner=False)
def fd5_day(day):
    if not FD5_TOKEN:return []
    d=date.fromisoformat(day); start=int(datetime(d.year,d.month,d.day,tzinfo=timezone.utc).timestamp()); end=start+86400
    return (request_json(f"{FD5_BASE}/fixtures",headers={"Authorization":f"Bearer {FD5_TOKEN}"},params={"start_time":start,"end_time":end,"per_page":100}) or {}).get("data") or []

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fd5_team_fixtures(team_id):
    if not FD5_TOKEN:return []
    return (request_json(f"{FD5_BASE}/teams/{team_id}/fixtures",headers={"Authorization":f"Bearer {FD5_TOKEN}"},params={"status":"finished","per_page":50}) or {}).get("data") or []

def normalize_fd5_event(e):
    teams=e.get("teams") or {}; h=teams.get("home") or {}; a=teams.get("away") or {}; goals=e.get("goals") or {}; corners=e.get("corners") or {}; cards=e.get("cards") or {}
    raw=e.get("kickoff_utc") or ""; ko=None
    try: ko=datetime.fromisoformat(raw.replace("Z","+00:00"))
    except Exception: pass
    return {"id":str(e.get("id","")),"date":raw[:10],"time":raw[11:16],"league":(e.get("league") or {}).get("name") or "","country":"","home":h.get("name") or "","away":a.get("name") or "","home_id":str(h.get("id") or ""),"away_id":str(a.get("id") or ""),"home_score":safe_float(goals.get("home")),"away_score":safe_float(goals.get("away")),"status":e.get("status") or "","source":"5DollarFootballAPI","kickoff":ko,"home_corners":safe_float(corners.get("home")),"away_corners":safe_float(corners.get("away")),"home_yellow":safe_float((cards.get("home") or {}).get("yellow")),"away_yellow":safe_float((cards.get("away") or {}).get("yellow"))}


def load_global_events(target, days_ahead=1):
    events=[]
    for off in range(days_ahead+1):
        d=target+timedelta(days=off); ds=d.isoformat()
        events += [normalize_openfoot_event(x) for x in openfoot_matches(ds)]
        events += [normalize_tsdb_event(x) for x in tsdb_day(ds)]
        if FD5_TOKEN: events += [normalize_fd5_event(x) for x in fd5_day(ds)]
    if FD_TOKEN:
        for c in fd_competitions():
            if c.get("code"):
                events += [normalize_fd_event(x) for x in fd_matches(c["code"],target.isoformat(),(target+timedelta(days=days_ahead)).isoformat())]
    unique={}; priority={"5DollarFootballAPI":4,"OpenFootAPI":3,"football-data.org":2,"TheSportsDB":1}
    for e in events:
        if not e["home"] or not e["away"]: continue
        key=(e["date"],re.sub(r"\W","",e["home"].lower()),re.sub(r"\W","",e["away"].lower()))
        if key not in unique or priority.get(e["source"],0)>priority.get(unique[key]["source"],0): unique[key]=e
    return list(unique.values())

# ---------- Form ----------
def make_form(ne, team_id):
    if ne["home_score"] is None or ne["away_score"] is None:return None
    is_home=str(ne["home_id"])==str(team_id); gf=ne["home_score"] if is_home else ne["away_score"]; ga=ne["away_score"] if is_home else ne["home_score"]
    return {"date":ne["date"],"gf":gf,"ga":ga,"home":is_home,"result":"W" if gf>ga else "D" if gf==ga else "L","opponent":ne["away"] if is_home else ne["home"],"opponent_id":ne["away_id"] if is_home else ne["home_id"],"corners_for":ne.get("home_corners") if is_home else ne.get("away_corners"),"corners_against":ne.get("away_corners") if is_home else ne.get("home_corners"),"yellow_for":ne.get("home_yellow") if is_home else ne.get("away_yellow"),"yellow_against":ne.get("away_yellow") if is_home else ne.get("home_yellow")}


def team_form(event, side, n=20):
    tid=event.get(f"{side}_id"); source=event.get("source"); rows=[]; label=""
    if source=="5DollarFootballAPI" and tid:
        for x in fd5_team_fixtures(tid):
            ne=normalize_fd5_event(x); r=make_form(ne,tid)
            if r: rows.append(r)
        label="5DollarFootballAPI"
    elif source=="OpenFootAPI" and tid:
        for x in openfoot_team_matches(tid):
            ne=normalize_openfoot_event(x); r=make_form(ne,tid)
            if r: rows.append(r)
        label="OpenFootAPI"
    elif source=="football-data.org" and tid:
        for x in fd_team_matches(int(tid)):
            ne=normalize_fd_event(x); r=make_form(ne,tid)
            if r: rows.append(r)
        label="football-data.org"
    elif source=="TheSportsDB" and tid:
        for x in tsdb_last(tid):
            ne=normalize_tsdb_event(x); r=make_form(ne,tid)
            if r: rows.append(r)
        label="TheSportsDB"
    if not rows:
        # Fallback search on OpenFoot, then TheSportsDB.
        found=openfoot_team_search(event.get(side,""))
        if found:
            oid=str(found[0].get("id") or found[0].get("teamId") or "")
            for x in openfoot_team_matches(oid):
                ne=normalize_openfoot_event(x); r=make_form(ne,oid)
                if r: rows.append(r)
            label="OpenFootAPI"
    if not rows:
        found=tsdb_team_search(event.get(side,""))
        if found:
            oid=str(found[0].get("idTeam") or "")
            for x in tsdb_last(oid):
                ne=normalize_tsdb_event(x); r=make_form(ne,oid)
                if r: rows.append(r)
            label="TheSportsDB"
    rows=sorted(rows,key=lambda x:x["date"],reverse=True)[:n]
    return rows,label


def avg(rows,key,default=None):
    vals=[float(r[key]) for r in rows if r.get(key) is not None]
    return sum(vals)/len(vals) if vals else default


def h2h_stats(event, hf, af, limit=10):
    home=event["home"]; away=event["away"]
    def clean(x): return re.sub(r"[^a-z0-9]","",x.lower())
    a,b=clean(home),clean(away)
    candidates=[]
    for r in hf+af:
        op=clean(str(r.get("opponent","")))
        if op and (op==a or op==b or a in op or b in op): candidates.append(r)
    uniq=[]; seen=set()
    for r in sorted(candidates,key=lambda x:x["date"],reverse=True):
        k=(r["date"],r["opponent"],r["gf"],r["ga"])
        if k not in seen: seen.add(k); uniq.append(r)
    # If one side's form has a direct opponent but naming differs, accept those rows.
    uniq=uniq[:limit]
    if len(uniq)<3:return None
    wins=draws=losses=btts=over25=0; goals=[]
    for r in uniq:
        gf,ga=r["gf"],r["ga"]; wins += gf>ga; draws += gf==ga; losses += gf<ga; btts += gf>0 and ga>0; over25 += gf+ga>2; goals.append(gf+ga)
    return {"games":len(uniq),"win_rate":wins/len(uniq),"draw_rate":draws/len(uniq),"loss_rate":losses/len(uniq),"btts":btts/len(uniq),"over25":over25/len(uniq),"avg_goals":sum(goals)/len(goals)}


def build_prediction(event,n=20):
    hf,hs=team_form(event,"home",n); af,ass=team_form(event,"away",n)
    hgf=avg(hf,"gf",1.20); hga=avg(hf,"ga",1.20); agf=avg(af,"gf",1.10); aga=avg(af,"ga",1.25)
    lh=max(.10,min(4.5,.55*hgf+.45*aga))*1.06; la=max(.10,min(4.5,.55*agf+.45*hga))
    pts=lambda rows: avg([{"p":{"W":3,"D":1,"L":0}.get(r["result"],0)} for r in rows],"p",1)/3
    lh*=.95+.10*(pts(hf) if hf else .5); la*=.95+.10*(pts(af) if af else .5)
    probs=model_probs(lh,la)
    h2h=h2h_stats(event,hf,af)
    if h2h:
        h2h_1x2={"Casa":h2h["win_rate"],"Empate":h2h["draw_rate"],"Fora":h2h["loss_rate"]}
        for k in ("Casa","Empate","Fora"): probs[k]=.80*probs[k]+.20*h2h_1x2[k]
        s=sum(probs[k] for k in ("Casa","Empate","Fora")); [probs.__setitem__(k,probs[k]/s) for k in ("Casa","Empate","Fora")]
        probs["BTTS Sim"]=.80*probs["BTTS Sim"]+.20*h2h["btts"]; probs["BTTS Não"]=1-probs["BTTS Sim"]
        probs["Over 2.5"]=.80*probs["Over 2.5"]+.20*h2h["over25"]; probs["Under 2.5"]=1-probs["Over 2.5"]
    conf=min(.96,max(.35,.35+.015*min(len(hf),n)+.015*min(len(af),n)))
    if hs=="5DollarFootballAPI" and ass=="5DollarFootballAPI":conf=min(.96,conf+.06)
    return {"probs":probs,"home_form":hf,"away_form":af,"home_form_source":hs,"away_form_source":ass,"confidence":conf,"h2h":h2h,"lambda_home":lh,"lambda_away":la,"corners_home_avg":avg(hf,"corners_for"),"corners_away_avg":avg(af,"corners_for"),"corners_home_allowed":avg(hf,"corners_against"),"corners_away_allowed":avg(af,"corners_against"),"yellow_home_avg":avg(hf,"yellow_for"),"yellow_away_avg":avg(af,"yellow_for")}


def suggestions(pred):
    p=pred["probs"]; c=[("Casa ou empate (1X)",p["Casa"]+p["Empate"]),("Empate ou fora (X2)",p["Empate"]+p["Fora"]),("Casa",p["Casa"]),("Empate",p["Empate"]),("Fora",p["Fora"]),("BTTS Sim",p["BTTS Sim"]),("BTTS Não",p["BTTS Não"]),("Over 1.5",p["Over 1.5"]),("Under 3.5",p["Under 3.5"]),("Over 2.5",p["Over 2.5"]),("Under 2.5",p["Under 2.5"])]
    return sorted(c,key=lambda x:x[1],reverse=True)[:5]


def filter_events(events):
    now=datetime.now(timezone.utc).astimezone(BRT); out=[]
    for e in events:
        cat=classify_event(e); e["category"]=cat
        if cat=="FINALIZADO": continue
        ko=parse_kickoff(e); e["kickoff_brt"]=ko
        if cat=="PRÓXIMO" and ko and ko<=now: continue
        if cat=="PRÓXIMO" and not ko and e.get("date")==date.today().isoformat(): continue
        out.append(e)
    return sorted(out,key=lambda x:(0 if x["category"]=="AO VIVO" else 1, x.get("kickoff_brt") or datetime.max.replace(tzinfo=BRT)))

# ---------- UI ----------
st.title("⚽ Global Football Scanner — AO VIVO + PRÉ-JOGO")
st.caption("4 fontes + últimos 20 jogos + H2H | jogos ao vivo permanecem no scanner | sem filtro mínimo de probabilidade")

# Atualização automática do painel ao vivo a cada 60 segundos.
st_autorefresh(interval=60_000, key="live_refresh_60s")

with st.sidebar:
    st.header("⚙️ Configuração")
    target=st.date_input("Data inicial",value=date.today())
    days=st.slider("Dias para varrer",0,3,1)
    form_n=st.slider("Últimos jogos usados",10,20,20)
    show_all=st.checkbox("Mostrar todos",value=True)
    st.divider(); st.markdown("**Fontes**")
    st.write("🌎 TheSportsDB: ativo")
    st.write("🏆 football-data.org:","ativo" if FD_TOKEN else "opcional")
    st.write("📊 5DollarFootballAPI:","ativo" if FD5_TOKEN else "opcional")
    st.write("🌐 OpenFootAPI:","ativo" if OPENFOOT_TOKEN else "modo público")

if st.button("🔄 Atualizar jogos",type="primary",use_container_width=True):
    st.cache_data.clear(); st.rerun()

tab_live, tab_upcoming, tab_best, tab_team = st.tabs(["🟢 Jogos ao vivo", "🔵 Próximos jogos", "⭐ Melhores oportunidades", "🔎 Buscar por time"])

with tab_team:
    st.subheader("🔎 Buscar jogos por time")
    q=st.text_input("Digite o nome do time",placeholder="Ex.: Flamengo, Real Madrid, Liverpool")
    if q:
        teams=[]
        for x in openfoot_team_search(q)[:10]: teams.append({"nome":x.get("name") or x.get("teamName") or "Time","id":str(x.get("id") or x.get("teamId") or ""),"fonte":"OpenFootAPI"})
        for x in tsdb_team_search(q)[:10]: teams.append({"nome":x.get("strTeam") or "Time","id":str(x.get("idTeam") or ""),"fonte":"TheSportsDB"})
        seen=set(); teams=[x for x in teams if x["id"] and not (x["fonte"],x["id"]) in seen and not seen.add((x["fonte"],x["id"]))]
        if teams:
            choice=st.selectbox("Selecione o time",[f"{x['nome']} — {x['fonte']}" for x in teams])
            sel=teams[[f"{x['nome']} — {x['fonte']}" for x in teams].index(choice)]
            with st.spinner("Buscando próximos jogos..."):
                ev=filter_events(load_global_events(date.today(),7))
            name=sel["nome"].lower(); ev=[e for e in ev if name in e["home"].lower() or name in e["away"].lower()]
            if ev:
                st.dataframe(pd.DataFrame([{"Status":e["category"],"Data":e["date"],"Horário BRT":e["kickoff_brt"].strftime("%d/%m %H:%M") if e.get("kickoff_brt") else "-","Liga":e["league"],"Jogo":f"{e['home']} x {e['away']}"} for e in ev]),use_container_width=True,hide_index=True)
            else: st.info("Nenhum próximo ou ao vivo encontrado nos próximos 7 dias.")
        else: st.warning("Time não localizado nas fontes disponíveis.")

with st.spinner("Buscando calendário global e separando AO VIVO / PRÓXIMOS..."):
    events=filter_events(load_global_events(target,days))
live=[e for e in events if e["category"]=="AO VIVO"]
upcoming=[e for e in events if e["category"]=="PRÓXIMO"]
c1,c2,c3=st.columns(3)
c1.metric("🟢 Ao vivo",len(live)); c2.metric("🔵 Próximos",len(upcoming)); c3.metric("Total analisável",len(events))
if not events:
    st.warning("Nenhum jogo analisável encontrado. Verifique a data e as chaves opcionais.")
    st.stop()
rows=[]
progress=st.progress(0)
for i,e in enumerate(events):
    pred=build_prediction(e,form_n); sugs=suggestions(pred); best=sugs[0] if sugs else ("Sem sugestão",0)
    score=(f"{int(e['home_score'])}-{int(e['away_score'])}" if e.get('home_score') is not None and e.get('away_score') is not None else "-")
    rows.append({"Status":e["category"],"Horário BRT":e["kickoff_brt"].strftime("%d/%m %H:%M") if e.get("kickoff_brt") else "-","Liga":e["league"],"Jogo":f"{e['home']} x {e['away']}","Placar":score,"Casa":pct(pred["probs"]["Casa"]),"Empate":pct(pred["probs"]["Empate"]),"Fora":pct(pred["probs"]["Fora"]),"BTTS":pct(pred["probs"]["BTTS Sim"]),"O2.5":pct(pred["probs"]["Over 2.5"]),"U3.5":pct(pred["probs"]["Under 3.5"]),"Sugestão":best[0],"Prob.":pct(best[1]) if best[1] else "-","Confiança":pct(pred["confidence"]),"H2H":pred["h2h"]["games"] if pred["h2h"] else 0,"Fonte":e["source"],"_pred":pred,"_event":e})
    progress.progress((i+1)/len(events))
progress.empty()
df=pd.DataFrame(rows)
if not show_all: df=df.sort_values(["Status","Confiança"],ascending=[True,False]).head(200)
display=["Status","Horário BRT","Liga","Jogo","Placar","Casa","Empate","Fora","BTTS","O2.5","U3.5","Sugestão","Prob.","Confiança","H2H","Fonte"]

def render_match_card(row, idx, live_mode=False):
    pred=row["_pred"]; ev=row["_event"]
    title=f"{ev['home']}  {row['Placar'] if row['Placar'] != '-' else 'x'}  {ev['away']}"
    status_icon="🟢" if live_mode else "🔵"
    with st.container(border=True):
        c1,c2,c3=st.columns([5,2,3])
        with c1:
            st.markdown(f"### {status_icon} {title}")
            st.caption(f"{row['Liga']} • {row['Horário BRT']} • Fonte: {row['Fonte']}")
        with c2: st.metric("Melhor opção", row["Sugestão"], row["Prob."])
        with c3: st.metric("Confiança", row["Confiança"])
        b1,b2,b3,b4,b5=st.columns(5)
        b1.metric("Casa",row["Casa"]); b2.metric("Empate",row["Empate"]); b3.metric("Fora",row["Fora"]); b4.metric("BTTS",row["BTTS"]); b5.metric("O2.5",row["O2.5"])
        if live_mode:
            if ev.get("minute") is not None: st.caption(f"⏱️ Minuto: {ev.get('minute')} | Placar: {row['Placar']}")
            live_stats=[]
            for key,label in [("home_corners","Esc. casa"),("away_corners","Esc. fora"),("home_shots","Chutes casa"),("away_shots","Chutes fora"),("home_dangerous","Ataques perigosos casa"),("away_dangerous","Ataques perigosos fora")]:
                if ev.get(key) is not None: live_stats.append(f"{label}: {ev[key]}")
            if live_stats: st.caption(" • ".join(live_stats))
        with st.expander("📊 Ver análise completa",expanded=False):
            x1,x2=st.columns(2)
            with x1:
                st.markdown("**Mercados**")
                st.write(f"BTTS Sim: {row['BTTS']} | Over 2.5: {row['O2.5']} | Under 3.5: {row['U3.5']}")
                st.write(f"H2H analisados: {row['H2H']}")
            with x2:
                st.markdown("**Sugestões principais**")
                for nome,prob in suggestions(pred): st.write(f"• {nome}: {pct(prob)}")
            h=pred.get("h2h") or {}
            if h.get("games"):
                st.caption(f"H2H: {h.get('games')} jogos | Casa {h.get('home_wins',0)} vitórias | Empates {h.get('draws',0)} | Fora {h.get('away_wins',0)}")

with tab_live:
    st.subheader("🟢 Jogos ao vivo")
    st.caption("Atualização automática a cada 60 segundos.")
    live_df=df[df["Status"]=="AO VIVO"]
    if live_df.empty:
        st.info("Nenhum jogo ao vivo neste momento.")
    else:
        for idx,(_,r) in enumerate(live_df.iterrows()): render_match_card(r,idx,live_mode=True)

with tab_upcoming:
    st.subheader("🔵 Próximos jogos")
    up_df=df[df["Status"]=="PRÓXIMO"]
    if up_df.empty:
        st.info("Nenhum próximo jogo encontrado.")
    else:
        st.dataframe(up_df[display],use_container_width=True,hide_index=True)
        escolha=st.selectbox("🔎 Abrir análise de um próximo jogo",list(up_df.index),format_func=lambda i: f"{df.loc[i,'Jogo']} — {df.loc[i,'Sugestão']} ({df.loc[i,'Prob.']})")
        render_match_card(df.loc[escolha],int(escolha),live_mode=False)

with tab_best:
    st.subheader("⭐ Melhores oportunidades")
    st.caption("Ordenadas pela maior probabilidade da melhor sugestão — sem filtro mínimo.")
    best_df=df.sort_values("Prob.",ascending=False).head(20)
    for idx,(_,r) in enumerate(best_df.iterrows()): render_match_card(r,idx,live_mode=(r["Status"]=="AO VIVO"))

csv=df[display].to_csv(index=False).encode("utf-8-sig")
st.download_button("⬇️ Baixar CSV",csv,"football_scanner_v8.csv","text/csv")
