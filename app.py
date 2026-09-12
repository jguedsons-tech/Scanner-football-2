import os
import math
from datetime import datetime, timedelta, date, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Global Football Scanner — Free", page_icon="⚽", layout="wide")

# ============================================================
# DATA SOURCES
# 1) TheSportsDB: broad/global fixture discovery + basic history
# 2) football-data.org: optional results/standings for supported comps
# 3) 5DollarFootballAPI: OPTIONAL richer stats for supported leagues.
# 4) OpenFootAPI: global fixtures/results/standings/search; free Starter key.
#    It is used as an additional global source and fallback for recent form.
# ============================================================

TSDB_KEY = os.getenv("THESPORTSDB_API_KEY", "123")
TSDB_BASE = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"
FD_TOKEN = os.getenv("FOOTBALL_DATA_API_TOKEN", "")
FD_BASE = "https://api.football-data.org/v4"
FD5_TOKEN = os.getenv("FIVEDOLLAR_FOOTBALL_API_KEY", "")
FD5_BASE = "https://api.5dollarfootballapi.com/v1"
OPENFOOT_TOKEN = os.getenv("OPENFOOT_API_KEY", "")
OPENFOOT_BASE = "https://openfootapi.com/v1"

TIMEOUT = 15
CACHE_TTL = 300


def safe_float(v, default=None):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def safe_int(v, default=None):
    try:
        if v is None or v == "":
            return default
        return int(float(v))
    except Exception:
        return default


def pct(x):
    return f"{100*x:.1f}%"


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def poisson_matrix(lh: float, la: float, max_goals: int = 10):
    return [[poisson_pmf(i, lh) * poisson_pmf(j, la) for j in range(max_goals + 1)]
            for i in range(max_goals + 1)]


def model_probs(lh: float, la: float) -> Dict[str, float]:
    m = poisson_matrix(lh, la)
    n = len(m)
    home = sum(m[i][j] for i in range(n) for j in range(n) if i > j)
    draw = sum(m[i][j] for i in range(n) for j in range(n) if i == j)
    away = sum(m[i][j] for i in range(n) for j in range(n) if i < j)
    btts = sum(m[i][j] for i in range(1, n) for j in range(1, n))

    out = {
        "Casa": home,
        "Empate": draw,
        "Fora": away,
        "BTTS Sim": btts,
        "BTTS Não": 1 - btts,
    }
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        threshold = int(line - 0.5)
        under = sum(m[i][j] for i in range(n) for j in range(n) if i + j <= threshold)
        out[f"Over {line}"] = 1 - under
        out[f"Under {line}"] = under
    return out


def request_json(url: str, headers=None, params=None) -> Optional[Dict[str, Any]]:
    try:
        r = requests.get(url, headers=headers or {}, params=params or {}, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


# ---------------- TheSportsDB ----------------
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def tsdb_day(day: str) -> List[Dict[str, Any]]:
    data = request_json(f"{TSDB_BASE}/eventsday.php", params={"d": day, "s": "Soccer"})
    return (data or {}).get("events") or []


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def tsdb_team_search(name: str) -> Optional[Dict[str, Any]]:
    data = request_json(f"{TSDB_BASE}/searchteams.php", params={"t": name})
    teams = (data or {}).get("teams") or []
    return teams[0] if teams else None


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def tsdb_last(team_id: str) -> List[Dict[str, Any]]:
    data = request_json(f"{TSDB_BASE}/eventslast.php", params={"id": team_id})
    return (data or {}).get("results") or []


def normalize_tsdb_event(e: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(e.get("idEvent", "")),
        "date": e.get("dateEvent") or "",
        "time": e.get("strTime") or e.get("strEventTime") or "",
        "league": e.get("strLeague") or "",
        "country": e.get("strCountry") or "",
        "home": e.get("strHomeTeam") or "",
        "away": e.get("strAwayTeam") or "",
        "home_id": str(e.get("idHomeTeam") or ""),
        "away_id": str(e.get("idAwayTeam") or ""),
        "home_score": safe_float(e.get("intHomeScore")),
        "away_score": safe_float(e.get("intAwayScore")),
        "status": e.get("strStatus") or "",
        "source": "TheSportsDB",
        "stats_source": "",
    }


# ---------------- football-data.org ----------------
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fd_competitions() -> List[Dict[str, Any]]:
    if not FD_TOKEN:
        return []
    data = request_json(f"{FD_BASE}/competitions", headers={"X-Auth-Token": FD_TOKEN})
    return (data or {}).get("competitions") or []


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fd_matches(comp_code: str, start: str, end: str) -> List[Dict[str, Any]]:
    if not FD_TOKEN:
        return []
    data = request_json(
        f"{FD_BASE}/competitions/{comp_code}/matches",
        headers={"X-Auth-Token": FD_TOKEN},
        params={"dateFrom": start, "dateTo": end, "status": "SCHEDULED,FINISHED,POSTPONED,CANCELLED"},
    )
    return (data or {}).get("matches") or []


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fd_team_matches(team_id: int, date_from: str, date_to: str) -> List[Dict[str, Any]]:
    if not FD_TOKEN:
        return []
    data = request_json(
        f"{FD_BASE}/teams/{team_id}/matches",
        headers={"X-Auth-Token": FD_TOKEN},
        params={"dateFrom": date_from, "dateTo": date_to, "status": "FINISHED"},
    )
    return (data or {}).get("matches") or []


def normalize_fd_event(e: Dict[str, Any]) -> Dict[str, Any]:
    score = e.get("score") or {}
    full = score.get("fullTime") or {}
    comp = e.get("competition") or {}
    area = comp.get("area") or {}
    home = e.get("homeTeam") or {}
    away = e.get("awayTeam") or {}
    return {
        "id": str(e.get("id", "")),
        "date": (e.get("utcDate") or "")[:10],
        "time": (e.get("utcDate") or "")[11:16],
        "league": comp.get("name") or "",
        "country": area.get("name") or "",
        "home": home.get("name") or "",
        "away": away.get("name") or "",
        "home_id": str(home.get("id") or ""),
        "away_id": str(away.get("id") or ""),
        "home_score": safe_float(full.get("home")),
        "away_score": safe_float(full.get("away")),
        "status": e.get("status") or "",
        "source": "football-data.org",
        "stats_source": "",
    }


# ---------------- OpenFootAPI ----------------
@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def openfoot_matches(day: str, status: str = "") -> List[Dict[str, Any]]:
    params = {"date": day}
    if status:
        params["status"] = status
    headers = {"Accept": "application/json"}
    if OPENFOOT_TOKEN:
        headers["Authorization"] = f"Bearer {OPENFOOT_TOKEN}"
    data = request_json(f"{OPENFOOT_BASE}/matches", headers=headers, params=params)
    return (data or {}).get("data") or []


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def openfoot_team_search(name: str) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    headers = {"Accept": "application/json"}
    if OPENFOOT_TOKEN:
        headers["Authorization"] = f"Bearer {OPENFOOT_TOKEN}"
    data = request_json(f"{OPENFOOT_BASE}/search", headers=headers, params={"q": name})
    rows = (data or {}).get("data") or []
    for row in rows:
        if row.get("type") in ("team", "club"):
            return row
    return rows[0] if rows else None


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def openfoot_team_matches(team_id: str, n: int = 10) -> List[Dict[str, Any]]:
    if not team_id:
        return []
    headers = {"Accept": "application/json"}
    if OPENFOOT_TOKEN:
        headers["Authorization"] = f"Bearer {OPENFOOT_TOKEN}"
    data = request_json(
        f"{OPENFOOT_BASE}/matches",
        headers=headers,
        params={"team": team_id, "status": "finished"},
    )
    rows = (data or {}).get("data") or []
    return rows[:n]


def normalize_openfoot_event(e: Dict[str, Any]) -> Dict[str, Any]:
    hs = e.get("homeTeam") or {}
    aw = e.get("awayTeam") or {}
    score = e.get("score") or {}
    # OpenFoot may expose a nested fullTime score or direct values.
    full = score.get("fullTime") or score.get("fulltime") or score
    return {
        "id": str(e.get("id", "")),
        "date": (e.get("kickoffAt") or e.get("date") or "")[:10],
        "time": (e.get("kickoffAt") or "")[11:16],
        "league": (e.get("competition") or {}).get("name") if isinstance(e.get("competition"), dict) else (e.get("competitionName") or ""),
        "country": "",
        "home": hs.get("name") or e.get("homeTeamName") or "",
        "away": aw.get("name") or e.get("awayTeamName") or "",
        "home_id": str(hs.get("id") or ""),
        "away_id": str(aw.get("id") or ""),
        "home_score": safe_float(full.get("home")),
        "away_score": safe_float(full.get("away")),
        "status": e.get("status") or "",
        "source": "OpenFootAPI",
        "stats_source": "",
    }


def team_form_from_openfoot(team_id: str, n: int = 10) -> List[Dict[str, Any]]:
    rows = openfoot_team_matches(team_id, n)
    result = []
    for e in rows:
        ne = normalize_openfoot_event(e)
        if ne["home_score"] is None or ne["away_score"] is None:
            continue
        is_home = str(ne["home_id"]) == str(team_id)
        gf = ne["home_score"] if is_home else ne["away_score"]
        ga = ne["away_score"] if is_home else ne["home_score"]
        result.append({
            "date": ne["date"], "gf": gf, "ga": ga, "home": is_home,
            "result": "W" if gf > ga else "D" if gf == ga else "L",
            "opponent": ne["away"] if is_home else ne["home"],
            "corners_for": None, "corners_against": None,
            "yellow_for": None, "yellow_against": None,
            "red_for": None, "red_against": None,
        })
    return sorted(result, key=lambda x: x["date"], reverse=True)[:n]


# ---------------- 5DollarFootballAPI ----------------
def unix_utc_start(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fd5_day(day: str) -> List[Dict[str, Any]]:
    if not FD5_TOKEN:
        return []
    d = date.fromisoformat(day)
    start = unix_utc_start(d)
    end = start + 86400
    data = request_json(
        f"{FD5_BASE}/fixtures",
        headers={"Authorization": f"Bearer {FD5_TOKEN}"},
        params={"start_time": start, "end_time": end, "per_page": 100},
    )
    return (data or {}).get("data") or []


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fd5_team_fixtures(team_id: str, n: int = 10) -> List[Dict[str, Any]]:
    if not FD5_TOKEN or not team_id:
        return []
    data = request_json(
        f"{FD5_BASE}/teams/{team_id}/fixtures",
        headers={"Authorization": f"Bearer {FD5_TOKEN}"},
        params={"status": "finished", "per_page": min(max(n, 1), 50)},
    )
    return (data or {}).get("data") or []


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def fd5_fixture(fixture_id: str) -> Optional[Dict[str, Any]]:
    if not FD5_TOKEN or not fixture_id:
        return None
    data = request_json(
        f"{FD5_BASE}/fixtures/{fixture_id}",
        headers={"Authorization": f"Bearer {FD5_TOKEN}"},
        params={"include": "events,stats"},
    )
    return (data or {}).get("data")


def normalize_fd5_event(e: Dict[str, Any]) -> Dict[str, Any]:
    teams = e.get("teams") or {}
    h = teams.get("home") or {}
    a = teams.get("away") or {}
    goals = e.get("goals") or {}
    corners = e.get("corners") or {}
    cards = e.get("cards") or {}
    hy = safe_float((cards.get("home") or {}).get("yellow"))
    ay = safe_float((cards.get("away") or {}).get("yellow"))
    hr = safe_float((cards.get("home") or {}).get("red"))
    ar = safe_float((cards.get("away") or {}).get("red"))
    return {
        "id": str(e.get("id", "")),
        "date": (e.get("kickoff_utc") or "")[:10],
        "time": (e.get("kickoff_utc") or "")[11:16],
        "league": (e.get("league") or {}).get("name") or "",
        "country": "",
        "home": h.get("name") or "",
        "away": a.get("name") or "",
        "home_id": str(h.get("id") or ""),
        "away_id": str(a.get("id") or ""),
        "home_score": safe_float(goals.get("home")),
        "away_score": safe_float(goals.get("away")),
        "status": e.get("status") or "",
        "source": "5DollarFootballAPI",
        "stats_source": "5DollarFootballAPI",
        "home_corners": safe_float(corners.get("home")),
        "away_corners": safe_float(corners.get("away")),
        "home_yellow": hy,
        "away_yellow": ay,
        "home_red": hr,
        "away_red": ar,
    }


def load_global_events(target: date, days_ahead: int = 1) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    # OpenFootAPI global discovery (120 competitions; free key recommended).
    for offset in range(0, days_ahead + 1):
        d = target + timedelta(days=offset)
        events.extend(normalize_openfoot_event(x) for x in openfoot_matches(d.isoformat()))

    # Broad global discovery.
    for offset in range(0, days_ahead + 1):
        d = target + timedelta(days=offset)
        events.extend(normalize_tsdb_event(x) for x in tsdb_day(d.isoformat()))

    # Higher-quality supported competitions.
    if FD_TOKEN:
        for c in fd_competitions():
            code = c.get("code")
            if not code:
                continue
            matches = fd_matches(code, target.isoformat(), (target + timedelta(days=days_ahead)).isoformat())
            events.extend(normalize_fd_event(x) for x in matches)

    # Third source: richer corners/cards and team IDs where the free tier covers.
    if FD5_TOKEN:
        for offset in range(0, days_ahead + 1):
            d = target + timedelta(days=offset)
            events.extend(normalize_fd5_event(x) for x in fd5_day(d.isoformat()))

    unique: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    priority = {"5DollarFootballAPI": 4, "OpenFootAPI": 3, "football-data.org": 2, "TheSportsDB": 1}
    for e in events:
        if not e.get("home") or not e.get("away"):
            continue
        key = (e["date"], e["home"].lower(), e["away"].lower())
        if key not in unique or priority.get(e["source"], 0) > priority.get(unique[key]["source"], 0):
            unique[key] = e
    return list(unique.values())


# ---------------- Form/statistics ----------------
def team_form_from_tsdb(team_id: str, n: int = 10) -> List[Dict[str, Any]]:
    rows = tsdb_last(team_id) if team_id else []
    result = []
    for e in rows:
        ne = normalize_tsdb_event(e)
        if ne["home_score"] is None or ne["away_score"] is None:
            continue
        is_home = str(e.get("idHomeTeam")) == str(team_id)
        gf = ne["home_score"] if is_home else ne["away_score"]
        ga = ne["away_score"] if is_home else ne["home_score"]
        result.append({
            "date": ne["date"], "gf": gf, "ga": ga, "home": is_home,
            "result": "W" if gf > ga else "D" if gf == ga else "L",
            "opponent": ne["away"] if is_home else ne["home"],
            "corners_for": None, "corners_against": None,
            "yellow_for": None, "yellow_against": None,
            "red_for": None, "red_against": None,
        })
    return sorted(result, key=lambda x: x["date"], reverse=True)[:n]


def team_form_from_fd(team_id: str, n: int = 10) -> List[Dict[str, Any]]:
    if not FD_TOKEN or not team_id:
        return []
    end = date.today()
    start = end - timedelta(days=240)
    rows = fd_team_matches(int(team_id), start.isoformat(), end.isoformat())
    result = []
    for e in rows:
        score = e.get("score", {}).get("fullTime", {})
        h = e.get("homeTeam", {})
        a = e.get("awayTeam", {})
        hs, ass = safe_float(score.get("home")), safe_float(score.get("away"))
        if hs is None or ass is None:
            continue
        is_home = int(h.get("id", -1)) == int(team_id)
        gf, ga = (hs, ass) if is_home else (ass, hs)
        result.append({
            "date": (e.get("utcDate") or "")[:10], "gf": gf, "ga": ga, "home": is_home,
            "result": "W" if gf > ga else "D" if gf == ga else "L",
            "opponent": a.get("name") if is_home else h.get("name"),
            "corners_for": None, "corners_against": None,
            "yellow_for": None, "yellow_against": None,
            "red_for": None, "red_against": None,
        })
    return sorted(result, key=lambda x: x["date"], reverse=True)[:n]


def team_form_from_fd5(team_id: str, n: int = 10) -> List[Dict[str, Any]]:
    rows = fd5_team_fixtures(team_id, n)
    result = []
    for e in rows:
        ne = normalize_fd5_event(e)
        if ne["home_score"] is None or ne["away_score"] is None:
            continue
        is_home = str(ne["home_id"]) == str(team_id)
        gf = ne["home_score"] if is_home else ne["away_score"]
        ga = ne["away_score"] if is_home else ne["home_score"]
        cf = ne.get("home_corners") if is_home else ne.get("away_corners")
        ca = ne.get("away_corners") if is_home else ne.get("home_corners")
        yf = ne.get("home_yellow") if is_home else ne.get("away_yellow")
        ya = ne.get("away_yellow") if is_home else ne.get("home_yellow")
        rf = ne.get("home_red") if is_home else ne.get("away_red")
        ra = ne.get("away_red") if is_home else ne.get("home_red")
        result.append({
            "date": ne["date"], "gf": gf, "ga": ga, "home": is_home,
            "result": "W" if gf > ga else "D" if gf == ga else "L",
            "opponent": ne["away"] if is_home else ne["home"],
            "corners_for": cf, "corners_against": ca,
            "yellow_for": yf, "yellow_against": ya,
            "red_for": rf, "red_against": ra,
        })
    return sorted(result, key=lambda x: x["date"], reverse=True)[:n]


def get_form(event: Dict[str, Any], side: str, n: int) -> Tuple[List[Dict[str, Any]], str]:
    team_id = event.get(f"{side}_id")
    if event.get("source") == "5DollarFootballAPI" and team_id:
        rows = team_form_from_fd5(team_id, n)
        if rows:
            return rows, "5DollarFootballAPI"

    if event.get("source") == "football-data.org" and team_id:
        rows = team_form_from_fd(str(team_id), n)
        if rows:
            return rows, "football-data.org"

    if event.get("source") == "OpenFootAPI" and team_id:
        rows = team_form_from_openfoot(team_id, n)
        if rows:
            return rows, "OpenFootAPI"

    if team_id:
        rows = team_form_from_tsdb(team_id, n)
        if rows:
            return rows, "TheSportsDB"

    of_team = openfoot_team_search(event.get(side, ""))
    if of_team:
        of_id = str(of_team.get("id") or of_team.get("teamId") or "")
        rows = team_form_from_openfoot(of_id, n)
        if rows:
            return rows, "OpenFootAPI"

    team = tsdb_team_search(event.get(side, ""))
    if team:
        rows = team_form_from_tsdb(str(team.get("idTeam")), n)
        if rows:
            return rows, "TheSportsDB"
    return [], ""


def avg(rows, key, default=None):
    vals = [safe_float(r.get(key)) for r in rows if safe_float(r.get(key)) is not None]
    return sum(vals) / len(vals) if vals else default


def build_prediction(event: Dict[str, Any], n_form: int = 10) -> Dict[str, Any]:
    hf, hs = get_form(event, "home", n_form)
    af, ass = get_form(event, "away", n_form)

    # Do not invent xG. If there is no recent data, use conservative league-neutral
    # goal priors solely to keep the UI operational and mark confidence lower.
    h_gf = avg(hf, "gf", 1.20)
    h_ga = avg(hf, "ga", 1.20)
    a_gf = avg(af, "gf", 1.10)
    a_ga = avg(af, "ga", 1.25)

    lh = max(0.10, min(4.5, 0.55 * h_gf + 0.45 * a_ga)) * 1.06
    la = max(0.10, min(4.5, 0.55 * a_gf + 0.45 * h_ga))

    # Small form adjustment, bounded to avoid overfitting a 10-game sample.
    def form_points(rows):
        pts = {"W": 3, "D": 1, "L": 0}
        return avg([{"p": pts.get(r["result"], 0)} for r in rows], "p", 1.0) / 3.0

    hp = form_points(hf) if hf else 0.5
    ap = form_points(af) if af else 0.5
    lh *= 0.95 + 0.10 * hp
    la *= 0.95 + 0.10 * ap

    probs = model_probs(lh, la)

    corner_for_h = avg(hf, "corners_for")
    corner_against_h = avg(hf, "corners_against")
    corner_for_a = avg(af, "corners_for")
    corner_against_a = avg(af, "corners_against")
    yellow_h = avg(hf, "yellow_for")
    yellow_a = avg(af, "yellow_for")

    confidence = min(0.92, max(0.35, 0.35 + 0.035 * min(len(hf), n_form) + 0.035 * min(len(af), n_form)))
    if hs == "5DollarFootballAPI" and ass == "5DollarFootballAPI":
        confidence += 0.06
    confidence = min(confidence, 0.95)

    return {
        "lambda_home": lh,
        "lambda_away": la,
        "home_form": hf,
        "away_form": af,
        "home_form_source": hs,
        "away_form_source": ass,
        "probs": probs,
        "confidence": confidence,
        "corners_home_avg": corner_for_h,
        "corners_away_avg": corner_for_a,
        "corners_home_allowed": corner_against_h,
        "corners_away_allowed": corner_against_a,
        "yellow_home_avg": yellow_h,
        "yellow_away_avg": yellow_a,
    }


def suggestions(pred: Dict[str, Any], min_prob: float = 0.60) -> List[Tuple[str, float]]:
    p = pred["probs"]
    candidates = [
        ("Casa ou empate (1X)", p["Casa"] + p["Empate"]),
        ("Empate ou fora (X2)", p["Empate"] + p["Fora"]),
        ("Casa", p["Casa"]),
        ("Empate", p["Empate"]),
        ("Fora", p["Fora"]),
        ("BTTS Sim", p["BTTS Sim"]),
        ("BTTS Não", p["BTTS Não"]),
        ("Over 1.5", p["Over 1.5"]),
        ("Under 3.5", p["Under 3.5"]),
        ("Over 2.5", p["Over 2.5"]),
        ("Under 2.5", p["Under 2.5"]),
    ]
    return sorted([(m, v) for m, v in candidates if v >= min_prob], key=lambda x: x[1], reverse=True)[:5]


def stats_summary(pred: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "Escanteios casa": pred["corners_home_avg"],
        "Escanteios fora": pred["corners_away_avg"],
        "Escanteios casa sofridos": pred["corners_home_allowed"],
        "Escanteios fora sofridos": pred["corners_away_allowed"],
        "Amarelos casa": pred["yellow_home_avg"],
        "Amarelos fora": pred["yellow_away_avg"],
    }


# ---------------- UI ----------------
st.title("⚽ Global Football Scanner — Free")
st.caption("TheSportsDB + football-data.org + 5DollarFootballAPI + OpenFootAPI | probabilidades e estatísticas reais quando disponíveis")

with st.sidebar:
    st.header("⚙️ Configuração")
    target = st.date_input("Data inicial", value=date.today())
    days = st.slider("Dias para varrer", 0, 3, 1)
    min_prob = st.slider("Probabilidade mínima", 0.50, 0.90, 0.65, 0.01)
    form_n = st.slider("Últimos jogos", 3, 10, 10)
    show_all = st.checkbox("Mostrar todos os jogos", value=False)
    st.divider()
    st.markdown("**Fontes**")
    st.write("🌎 TheSportsDB: ativo")
    st.write("🏆 football-data.org:", "ativo" if FD_TOKEN else "opcional / não configurado")
    st.write("📊 5DollarFootballAPI:", "ativo" if FD5_TOKEN else "opcional / não configurado")
    st.write("🌐 OpenFootAPI:", "ativo" if OPENFOOT_TOKEN else "modo público / chave não configurada")
    if not FD5_TOKEN:
        st.info("Adicione FIVEDOLLAR_FOOTBALL_API_KEY nos Secrets para tentar obter escanteios, cartões, ataques e estatísticas dos últimos 10 jogos nas competições cobertas pelo plano gratuito.")

if st.button("🔄 Buscar jogos", type="primary", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

with st.spinner("Buscando calendário e estatísticas..."):
    events = load_global_events(target, days)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Jogos encontrados", len(events))
c2.metric("Fontes ativas", 2 + int(bool(FD_TOKEN)) + int(bool(FD5_TOKEN)) + int(bool(OPENFOOT_TOKEN)))
c3.metric("Últimos jogos", form_n)
c4.metric("Período", f"{target} + {days} dia(s)")

if not events:
    st.warning("Nenhum jogo foi retornado para o período escolhido. Tente outra data.")
    st.stop()

rows = []
progress = st.progress(0)
for idx, e in enumerate(events):
    pred = build_prediction(e, form_n)
    sugs = suggestions(pred, min_prob)
    best = sugs[0] if sugs else ("Sem sugestão acima do filtro", 0)
    rows.append({
        "Data": e["date"],
        "Liga": e["league"],
        "Jogo": f"{e['home']} x {e['away']}",
        "Casa": pct(pred["probs"]["Casa"]),
        "Empate": pct(pred["probs"]["Empate"]),
        "Fora": pct(pred["probs"]["Fora"]),
        "BTTS Sim": pct(pred["probs"]["BTTS Sim"]),
        "Over 2.5": pct(pred["probs"]["Over 2.5"]),
        "Under 3.5": pct(pred["probs"]["Under 3.5"]),
        "Esc. casa": pred["corners_home_avg"],
        "Esc. fora": pred["corners_away_avg"],
        "Amarelos casa": pred["yellow_home_avg"],
        "Amarelos fora": pred["yellow_away_avg"],
        "Sugestão": best[0],
        "Prob.": pct(best[1]) if best[1] else "-",
        "Confiança": pct(pred["confidence"]),
        "Fonte": e["source"],
        "Form. fonte": f"{pred['home_form_source']} / {pred['away_form_source']}",
        "_pred": pred,
        "_event": e,
    })
    progress.progress((idx + 1) / max(len(events), 1))
progress.empty()

result_df = pd.DataFrame(rows)
if not show_all:
    result_df = result_df.sort_values(
        "_pred", key=lambda s: s.map(lambda p: max(p["probs"].values())), ascending=False
    ).head(100)

st.subheader("📊 Scanner")
display_cols = [
    "Data", "Liga", "Jogo", "Casa", "Empate", "Fora", "BTTS Sim",
    "Over 2.5", "Under 3.5", "Esc. casa", "Esc. fora", "Amarelos casa",
    "Amarelos fora", "Sugestão", "Prob.", "Confiança", "Fonte"
]
st.dataframe(result_df[display_cols], use_container_width=True, hide_index=True)

csv = result_df[display_cols].to_csv(index=False).encode("utf-8-sig")
st.download_button("⬇️ Baixar CSV", csv, "football_scanner_global_free.csv", "text/csv")

st.divider()
st.subheader("🎯 Melhores oportunidades")
for _, r in result_df.head(20).iterrows():
    p = r["_pred"]
    e = r["_event"]
    st.markdown(f"### {e['home']} x {e['away']}")
    a, b, c, d = st.columns(4)
    a.metric("Casa", pct(p["probs"]["Casa"]))
    b.metric("Empate", pct(p["probs"]["Empate"]))
    c.metric("Fora", pct(p["probs"]["Fora"]))
    d.metric("BTTS Sim", pct(p["probs"]["BTTS Sim"]))
    sugs = suggestions(p, min_prob)
    if sugs:
        st.write("**Sugestões:**", " · ".join(f"{m} ({pct(v)})" for m, v in sugs))
    else:
        st.write("Nenhum mercado ultrapassou o filtro.")

    s = stats_summary(p)
    stat_text = []
    for k, v in s.items():
        stat_text.append(f"{k}: {v:.2f}" if v is not None else f"{k}: indisponível")
    st.caption(" | ".join(stat_text))
    st.caption(
        f"Forma: {p['home_form_source']} / {p['away_form_source']} · "
        f"λ gols estimado: {p['lambda_home']:.2f} x {p['lambda_away']:.2f} · "
        f"confiança: {pct(p['confidence'])}"
    )

st.divider()
st.subheader("📚 Como as três fontes são usadas")
st.markdown(
    """
- **OpenFootAPI:** fonte global adicional para jogos, resultados e busca de equipes; a chave Starter gratuita dá acesso ao catálogo de 120 competições, fixtures/resultados e tabelas/form.
- **TheSportsDB:** descoberta global de jogos e histórico básico quando disponível.
- **football-data.org:** complemento opcional de resultados para as competições cobertas pela conta gratuita.
- **5DollarFootballAPI:** complemento opcional de maior profundidade; quando disponível, tenta preencher os últimos 10 jogos, escanteios e cartões.

**Importante:** nenhuma fonte garante estatísticas avançadas para todas as ligas. O aplicativo combina as fontes e mantém campos indisponíveis como indisponíveis, sem inventar valores.

As probabilidades são **estimativas estatísticas do modelo**, não garantia de acerto ou lucro.
"""
)
