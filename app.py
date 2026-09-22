import os
import math
import traceback
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Global Football Scanner",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CONFIGURAÇÕES DAS APIS
# ============================================================

TSDB_KEY = os.getenv("THESPORTSDB_API_KEY", "123")
TSDB_BASE = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"

FD_TOKEN = os.getenv("FOOTBALL_DATA_API_TOKEN", "")
FD_BASE = "https://api.football-data.org/v4"

FD5_TOKEN = os.getenv(
    "FIVEDOLLAR_FOOTBALL_API_KEY",
    os.getenv("FIVEDOLLAR_FOOTBALLAPI_KEY", "")
)
FD5_BASE = "https://api.5dollarfootballapi.com/v1"

OPENFOOT_TOKEN = os.getenv("OPENFOOT_API_KEY", "")
OPENFOOT_BASE = "https://openfootapi.com/v1"

TIMEOUT = 15
L10_N = 10
BRT = ZoneInfo("America/Sao_Paulo")


LIVE_STATUSES = {
    "LIVE",
    "IN_PLAY",
    "1H",
    "2H",
    "HT",
    "ET",
    "P",
}

FINAL_STATUSES = {
    "FT",
    "AET",
    "PEN",
    "FINISHED",
    "FINAL",
    "AFTER_EXTRA_TIME",
    "AFTER_PENALTIES",
}

PRE_STATUSES = {
    "NS",
    "TBD",
    "SCHEDULED",
    "TIMED",
    "UPCOMING",
}


# ============================================================
# FUNÇÕES BÁSICAS
# ============================================================

def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        if isinstance(value, str):
            value = (
                value
                .replace("%", "")
                .replace(",", ".")
                .strip()
            )

            if not value:
                return default

        return float(value)

    except Exception:
        return default


def pct(value):
    return f"{safe_float(value):.1f}%"


def norm_status(status):
    if status is None:
        return ""

    return (
        str(status)
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )


def parse_kickoff(value):
    if not value:
        return None

    try:
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value).strip()

            if text.endswith("Z"):
                text = text[:-1] + "+00:00"

            dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(BRT)

    except Exception:
        return None


def classify_event(event):
    status = norm_status(event.get("status", ""))

    if status in LIVE_STATUSES:
        return "live"

    if status in FINAL_STATUSES:
        return "finished"

    if status in PRE_STATUSES:
        return "upcoming"

    kickoff = parse_kickoff(event.get("kickoff"))

    if kickoff:
        now = datetime.now(BRT)

        if kickoff <= now:
            return "live"

        return "upcoming"

    return "unknown"


def request_json(
    url,
    headers=None,
    params=None,
    timeout=TIMEOUT
):
    try:
        response = requests.get(
            url,
            headers=headers or {},
            params=params or {},
            timeout=timeout
        )

        if response.status_code != 200:
            return None

        return response.json()

    except Exception:
        return None


# ============================================================
# MODELO DE PROBABILIDADE
# ============================================================

def poisson_pmf(k, lam):

    try:
        lam = max(
            0.001,
            safe_float(lam)
        )

        return (
            math.exp(-lam)
            * (lam ** k)
            / math.factorial(k)
        )

    except Exception:
        return 0.0


def model_probs(home_lambda, away_lambda):

    home_lambda = max(
        0.01,
        safe_float(home_lambda, 1.0)
    )

    away_lambda = max(
        0.01,
        safe_float(away_lambda, 1.0)
    )

    home_win = 0.0
    draw = 0.0
    away_win = 0.0

    btts = 0.0
    over15 = 0.0
    over25 = 0.0
    under25 = 0.0
    under35 = 0.0

    for hg in range(11):

        ph = poisson_pmf(
            hg,
            home_lambda
        )

        for ag in range(11):

            pa = poisson_pmf(
                ag,
                away_lambda
            )

            probability = ph * pa

            if hg > ag:
                home_win += probability

            elif hg == ag:
                draw += probability

            else:
                away_win += probability

            total = hg + ag

            if hg >= 1 and ag >= 1:
                btts += probability

            if total >= 2:
                over15 += probability

            if total >= 3:
                over25 += probability
            else:
                under25 += probability

            if total <= 3:
                under35 += probability

    total = home_win + draw + away_win

    if total <= 0:
        total = 1.0

    home_win /= total
    draw /= total
    away_win /= total

    btts /= total
    over15 /= total
    over25 /= total
    under25 /= total
    under35 /= total

    return {
        "home_win": home_win,
        "draw": draw,
        "away_win": away_win,

        "1x": home_win + draw,
        "x2": draw + away_win,

        "btts_yes": btts,
        "btts_no": 1 - btts,

        "over15": over15,
        "over25": over25,

        "under25": under25,
        "under35": under35,
    }


# ============================================================
# THESPORTSDB
# ============================================================

def tsdb_day(day):

    url = f"{TSDB_BASE}/eventsday.php"

    data = request_json(
        url,
        params={
            "d": day,
            "s": "Soccer"
        }
    )

    if not data:
        return []

    return data.get("events", []) or []


def tsdb_team_search(team):

    if not team:
        return []

    url = f"{TSDB_BASE}/searchteams.php"

    data = request_json(
        url,
        params={
            "t": team
        }
    )

    if not data:
        return []

    return data.get("teams", []) or []


def tsdb_last(team_id):

    if not team_id:
        return []

    url = f"{TSDB_BASE}/eventslast.php"

    data = request_json(
        url,
        params={
            "id": team_id
        }
    )

    if not data:
        return []

    return data.get("results", []) or []


def normalize_tsdb_event(event):

    if not event:
        return None

    try:

        return {
            "id": str(
                event.get("idEvent", "")
            ),

            "home": (
                event.get("strHomeTeam")
                or "Casa"
            ),

            "away": (
                event.get("strAwayTeam")
                or "Fora"
            ),

            "home_id": str(
                event.get("idHomeTeam")
                or ""
            ),

            "away_id": str(
                event.get("idAwayTeam")
                or ""
            ),

            "kickoff": (
                f"{event.get('dateEvent')}T"
                f"{event.get('strTime') or '00:00:00'}"
                if event.get("dateEvent")
                else None
            ),

            "status": (
                event.get("strStatus")
                or ""
            ),

            "home_score": event.get(
                "intHomeScore"
            ),

            "away_score": event.get(
                "intAwayScore"
            ),

            "source": "TheSportsDB",

            "raw": event,
        }

    except Exception:
        return None


# ============================================================
# FOOTBALL-DATA.ORG
# ============================================================

def fd_competitions():

    if not FD_TOKEN:
        return []

    data = request_json(
        f"{FD_BASE}/competitions",
        headers={
            "X-Auth-Token": FD_TOKEN
        }
    )

    if not data:
        return []

    return data.get(
        "competitions",
        []
    ) or []


def fd_matches(
    date_from,
    date_to
):

    if not FD_TOKEN:
        return []

    data = request_json(
        f"{FD_BASE}/matches",
        headers={
            "X-Auth-Token": FD_TOKEN
        },
        params={
            "dateFrom": date_from,
            "dateTo": date_to
        }
    )

    if not data:
        return []

    return data.get(
        "matches",
        []
    ) or []


def normalize_fd_event(event):

    if not event:
        return None

    try:

        home = (
            event.get("homeTeam")
            or {}
        )

        away = (
            event.get("awayTeam")
            or {}
        )

        score = (
            event.get("score")
            or {}
        )

        full_time = (
            score.get("fullTime")
            or {}
        )

        return {

            "id": str(
                event.get("id", "")
            ),

            "home": (
                home.get("name")
                or "Casa"
            ),

            "away": (
                away.get("name")
                or "Fora"
            ),

            "home_id": str(
                home.get("id")
                or ""
            ),

            "away_id": str(
                away.get("id")
                or ""
            ),

            "kickoff": event.get(
                "utcDate"
            ),

            "status": event.get(
                "status",
                ""
            ),

            "home_score": full_time.get(
                "home"
            ),

            "away_score": full_time.get(
                "away"
            ),

            "source": "football-data.org",

            "raw": event,
        }

    except Exception:
        return None


# ============================================================
# OPENFOOT
# ============================================================

def openfoot_matches():

    if not OPENFOOT_TOKEN:
        return []

    data = request_json(
        f"{OPENFOOT_BASE}/matches",
        headers={
            "Authorization":
                f"Bearer {OPENFOOT_TOKEN}"
        }
    )

    if not data:
        return []

    if isinstance(data, list):
        return data

    return (
        data.get("matches")
        or data.get("data")
        or []
    )


def openfoot_team_search(team):

    if not OPENFOOT_TOKEN:
        return []

    data = request_json(
        f"{OPENFOOT_BASE}/teams",
        headers={
            "Authorization":
                f"Bearer {OPENFOOT_TOKEN}"
        },
        params={
            "search": team
        }
    )

    if not data:
        return []

    if isinstance(data, list):
        return data

    return (
        data.get("teams")
        or data.get("data")
        or []
    )


def openfoot_team_matches(team_id):

    if not OPENFOOT_TOKEN:
        return []

    data = request_json(
        f"{OPENFOOT_BASE}/teams/{team_id}/matches",
        headers={
            "Authorization":
                f"Bearer {OPENFOOT_TOKEN}"
        }
    )

    if not data:
        return []

    if isinstance(data, list):
        return data

    return (
        data.get("matches")
        or data.get("data")
        or []
    )


def normalize_openfoot_event(event):

    if not event:
        return None

    try:

        home = (
            event.get("homeTeam")
            or event.get("home")
            or {}
        )

        away = (
            event.get("awayTeam")
            or event.get("away")
            or {}
        )

        if isinstance(home, str):

            home_name = home
            home_id = ""

        else:

            home_name = (
                home.get("name")
                or home.get(
                    "shortName",
                    "Casa"
                )
            )

            home_id = str(
                home.get("id")
                or ""
            )

        if isinstance(away, str):

            away_name = away
            away_id = ""

        else:

            away_name = (
                away.get("name")
                or away.get(
                    "shortName",
                    "Fora"
                )
            )

            away_id = str(
                away.get("id")
                or ""
            )

        score = (
            event.get("score")
            or {}
        )

        return {

            "id": str(
                event.get("id", "")
            ),

            "home": home_name,

            "away": away_name,

            "home_id": home_id,

            "away_id": away_id,

            "kickoff": (
                event.get("kickoff")
                or event.get("date")
                or event.get("utcDate")
            ),

            "status": event.get(
                "status",
                ""
            ),

            "home_score": (
                score.get("home")
                if isinstance(
                    score,
                    dict
                )
                else None
            ),

            "away_score": (
                score.get("away")
                if isinstance(
                    score,
                    dict
                )
                else None
            ),

            "source": "OpenFootAPI",

            "raw": event,
        }

    except Exception:
        return None


# ============================================================
# 5DOLLARFOOTBALLAPI
# ============================================================

def fd5_day(day):

    if not FD5_TOKEN:
        return []

    data = request_json(
        f"{FD5_BASE}/fixtures",
        headers={
            "Authorization":
                f"Bearer {FD5_TOKEN}"
        },
        params={
            "date": day
        }
    )

    if not data:
        return []

    if isinstance(data, list):
        return data

    return (
        data.get("fixtures")
        or data.get("data")
        or []
    )


def fd5_team_fixtures(team_id):

    if not FD5_TOKEN:
        return []

    data = request_json(
        f"{FD5_BASE}/fixtures",
        headers={
            "Authorization":
                f"Bearer {FD5_TOKEN}"
        },
        params={
            "team": team_id
        }
    )

    if not data:
        return []

    if isinstance(data, list):
        return data

    return (
        data.get("fixtures")
        or data.get("data")
        or []
    )


def normalize_fd5_event(event):

    if not event:
        return None

    try:

        home = (
            event.get("home")
            or event.get("homeTeam")
            or {}
        )

        away = (
            event.get("away")
            or event.get("awayTeam")
            or {}
        )

        if isinstance(home, str):

            home_name = home
            home_id = ""

        else:

            home_name = (
                home.get("name")
                or home.get(
                    "teamName",
                    "Casa"
                )
            )

            home_id = str(
                home.get("id")
                or home.get(
                    "teamId",
                    ""
                )
            )

        if isinstance(away, str):

            away_name = away
            away_id = ""

        else:

            away_name = (
                away.get("name")
                or away.get(
                    "teamName",
                    "Fora"
                )
            )

            away_id = str(
                away.get("id")
                or away.get(
                    "teamId",
                    ""
                )
            )

        score = (
            event.get("score")
            or event.get("scores")
            or {}
        )

        return {

            "id": str(
                event.get("id", "")
            ),

            "home": home_name,

            "away": away_name,

            "home_id": home_id,

            "away_id": away_id,

            "kickoff": (
                event.get("kickoff")
                or event.get("date")
                or event.get("utcDate")
            ),

            "status": event.get(
                "status",
                ""
            ),

            "home_score": (
                score.get("home")
                if isinstance(
                    score,
                    dict
                )
                else None
            ),

            "away_score": (
                score.get("away")
                if isinstance(
                    score,
                    dict
                )
                else None
            ),

            "source":
                "5DollarFootballAPI",

            "raw": event,
        }

    except Exception:
        return None


# ============================================================
# NORMALIZAÇÃO
# ============================================================

def normalize_name(name):

    if not name:
        return ""

    return (
        str(name)
        .lower()
        .strip()
    )


def event_key(event):

    if event.get("id"):
        return (
            event.get("source", "")
            + "_"
            + str(event["id"])
        )

    return (
        normalize_name(
            event.get("home")
        )
        + "_"
        + normalize_name(
            event.get("away")
        )
        + "_"
        + str(
            event.get("kickoff")
            or ""
        )
    )


def event_date(event):

    kickoff = parse_kickoff(
        event.get("kickoff")
    )

    if kickoff:
        return kickoff.date()

    return None


def event_is_finished(event):

    status = norm_status(
        event.get("status")
    )

    if status in FINAL_STATUSES:
        return True

    hs = event.get("home_score")
    aws = event.get("away_score")

    return (
        hs is not None
        and aws is not None
        and status not in LIVE_STATUSES
    )


# ============================================================
# CARREGAR JOGOS
# ============================================================

def load_global_events():

    events = []

    today = datetime.now(BRT).date()

    dates = [
        today,
        today
    ]

    # --------------------------------------------------------
    # THESPORTSDB
    # --------------------------------------------------------

    for d in dates:

        raw = tsdb_day(
            d.isoformat()
        )

        for item in raw:

            event = normalize_tsdb_event(
                item
            )

            if event:
                events.append(event)

    # --------------------------------------------------------
    # FOOTBALL-DATA
    # --------------------------------------------------------

    if FD_TOKEN:

        raw = fd_matches(
            today.isoformat(),
            today.isoformat()
        )

        for item in raw:

            event = normalize_fd_event(
                item
            )

            if event:
                events.append(event)

    # --------------------------------------------------------
    # OPENFOOT
    # --------------------------------------------------------

    if OPENFOOT_TOKEN:

        raw = openfoot_matches()

        for item in raw:

            event = normalize_openfoot_event(
                item
            )

            if event:

                dt = event_date(event)

                if (
                    dt is None
                    or dt == today
                ):
                    events.append(event)

    # --------------------------------------------------------
    # 5DOLLAR
    # --------------------------------------------------------

    if FD5_TOKEN:

        raw = fd5_day(
            today.isoformat()
        )

        for item in raw:

            event = normalize_fd5_event(
                item
            )

            if event:
                events.append(event)

    # --------------------------------------------------------
    # REMOVER DUPLICADOS
    # --------------------------------------------------------

    unique = {}

    priority = {
        "5DollarFootballAPI": 5,
        "OpenFootAPI": 4,
        "football-data.org": 3,
        "TheSportsDB": 1,
    }

    for event in events:

        key = event_key(event)

        old = unique.get(key)

        if old is None:

            unique[key] = event

        else:

            old_priority = priority.get(
                old.get("source"),
                0
            )

            new_priority = priority.get(
                event.get("source"),
                0
            )

            if new_priority > old_priority:

                unique[key] = event

    result = list(
        unique.values()
    )

    result.sort(
        key=lambda x: (
            event_date(x)
            or today
        )
    )

    return result


# ============================================================
# FORM / L10
# ============================================================

def make_form(
    events,
    team
):

    team_norm = normalize_name(
        team
    )

    games = []

    for event in events:

        home = normalize_name(
            event.get("home")
        )

        away = normalize_name(
            event.get("away")
        )

        if (
            team_norm not in home
            and team_norm not in away
        ):
            continue

        if not event_is_finished(
            event
        ):
            continue

        hs = event.get(
            "home_score"
        )

        aws = event.get(
            "away_score"
        )

        if hs is None or aws is None:
            continue

        hs = safe_float(hs)
        aws = safe_float(aws)

        if team_norm == home:

            gf = hs
            ga = aws

        else:

            gf = aws
            ga = hs

        if gf > ga:
            result = "V"

        elif gf == ga:
            result = "E"

        else:
            result = "D"

        games.append({
            "date":
                event_date(event),

            "opponent":
                event.get("away")
                if team_norm == home
                else event.get("home"),

            "gf": gf,
            "ga": ga,

            "result": result,

            "event": event,
        })

    games.sort(
        key=lambda x: (
            x["date"]
            or datetime.min.date()
        ),
        reverse=True
    )

    return games[:L10_N]


def l10_stats(form):

    if not form:
        return {
            "jogos": 0,
            "vitorias": 0,
            "empates": 0,
            "derrotas": 0,
            "gf": 0.0,
            "ga": 0.0,
            "media_gf": 0.0,
            "media_ga": 0.0,
        }

    v = sum(
        1
        for x in form
        if x["result"] == "V"
    )

    e = sum(
        1
        for x in form
        if x["result"] == "E"
    )

    d = sum(
        1
        for x in form
        if x["result"] == "D"
    )

    gf = sum(
        x["gf"]
        for x in form
    )

    ga = sum(
        x["ga"]
        for x in form
    )

    n = len(form)

    return {

        "jogos": n,

        "vitorias": v,

        "empates": e,

        "derrotas": d,

        "gf": gf,

        "ga": ga,

        "media_gf":
            gf / n if n else 0,

        "media_ga":
            ga / n if n else 0,
    }


# ============================================================
# H2H
# ============================================================

def h2h_stats(
    events,
    home,
    away
):

    home_norm = normalize_name(home)
    away_norm = normalize_name(away)

    matches = []

    for event in events:

        eh = normalize_name(
            event.get("home")
        )

        ea = normalize_name(
            event.get("away")
        )

        if not (
            (
                home_norm in eh
                and away_norm in ea
            )
            or
            (
                away_norm in eh
                and home_norm in ea
            )
        ):
            continue

        if not event_is_finished(
            event
        ):
            continue

        if (
            event.get("home_score")
            is None
            or
            event.get("away_score")
            is None
        ):
            continue

        matches.append(event)

    matches.sort(
        key=lambda x:
            event_date(x)
            or datetime.min.date(),
        reverse=True
    )

    return matches[:10]


# ============================================================
# PREDIÇÃO
# ============================================================

def build_prediction(
    home_l10,
    away_l10
):

    hs = l10_stats(
        home_l10
    )

    aws = l10_stats(
        away_l10
    )

    home_attack = hs["media_gf"]
    home_defense = hs["media_ga"]

    away_attack = aws["media_gf"]
    away_defense = aws["media_ga"]

    if hs["jogos"] == 0:
        home_attack = 1.20
        home_defense = 1.20

    if aws["jogos"] == 0:
        away_attack = 1.00
        away_defense = 1.20

    home_lambda = (
        home_attack * 0.65
        +
        away_defense * 0.35
    )

    away_lambda = (
        away_attack * 0.65
        +
        home_defense * 0.35
    )

    # vantagem simples de mando
    home_lambda *= 1.08

    probs = model_probs(
        home_lambda,
        away_lambda
    )

    return {
        "home_lambda":
            home_lambda,

        "away_lambda":
            away_lambda,

        **probs
    }


# ============================================================
# SUGESTÕES
# ============================================================

def fair_odd(probability):

    probability = safe_float(
        probability
    )

    if probability <= 0:
        return 0.0

    return 1 / probability


def suggestions(pred):

    markets = {

        "1X":
            pred["1x"],

        "X2":
            pred["x2"],

        "BTTS SIM":
            pred["btts_yes"],

        "BTTS NÃO":
            pred["btts_no"],

        "OVER 1.5":
            pred["over15"],

        "OVER 2.5":
            pred["over25"],

        "UNDER 2.5":
            pred["under25"],

        "UNDER 3.5":
            pred["under35"],
    }

    rows = []

    for market, probability in markets.items():

        rows.append({

            "Mercado":
                market,

            "Probabilidade":
                probability * 100,

            "Odd justa":
                fair_odd(
                    probability
                ),
        })

    rows.sort(
        key=lambda x:
            x["Probabilidade"],
        reverse=True
    )

    return rows


# ============================================================
# ANÁLISE
# ============================================================

def analyze_event(
    event,
    all_events
):

    home = event.get(
        "home",
        "Casa"
    )

    away = event.get(
        "away",
        "Fora"
    )

    home_l10 = make_form(
        all_events,
        home
    )

    away_l10 = make_form(
        all_events,
        away
    )

    pred = build_prediction(
        home_l10,
        away_l10
    )

    return {
        "event": event,
        "home_l10": home_l10,
        "away_l10": away_l10,
        "prediction": pred,
        "suggestions":
            suggestions(pred),
    }


# ============================================================
# EXIBIÇÃO
# ============================================================

def display_score(event):

    hs = event.get(
        "home_score"
    )

    aws = event.get(
        "away_score"
    )

    if hs is None or aws is None:
        return "x"

    return (
        f"{hs:g} - {aws:g}"
    )


def render_match_card(
    analysis
):

    event = analysis["event"]

    pred = analysis["prediction"]

    home_l10 = analysis["home_l10"]

    away_l10 = analysis["away_l10"]

    suggestions_list = (
        analysis["suggestions"]
    )

    status_type = classify_event(
        event
    )

    if status_type == "live":
        badge = "🔴 AO VIVO"

    elif status_type == "finished":
        badge = "✅ FINAL"

    else:
        badge = "🕒 PRÉ-JOGO"

    kickoff = parse_kickoff(
        event.get("kickoff")
    )

    if kickoff:

        hora = kickoff.strftime(
            "%d/%m %H:%M"
        )

    else:

        hora = "--"

    st.markdown(
        "---"
    )

    st.subheader(
        f"{badge}  "
        f"{event.get('home', 'Casa')} "
        f" {display_score(event)} "
        f"{event.get('away', 'Fora')}"
    )

    st.caption(
        f"Horário: {hora} | "
        f"Fonte: {event.get('source', '-')}"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "1X",
            pct(
                pred["1x"] * 100
            )
        )

    with col2:

        st.metric(
            "X2",
            pct(
                pred["x2"] * 100
            )
        )

    with col3:

        st.metric(
            "BTTS",
            pct(
                pred["btts_yes"] * 100
            )
        )

    st.write(
        f"⚽ Gols esperados: "
        f"{pred['home_lambda']:.2f} "
        f"x "
        f"{pred['away_lambda']:.2f}"
    )

    st.markdown(
        "### 📊 L10"
    )

    c1, c2 = st.columns(2)

    with c1:

        st.markdown(
            f"**{event.get('home')}**"
        )

        st.write(
            f"Jogos: {len(home_l10)}"
        )

        if home_l10:

            tabela = []

            for jogo in home_l10:

                tabela.append({
                    "Data":
                        jogo["date"],
                    "Adversário":
                        jogo["opponent"],
                    "GF":
                        int(jogo["gf"]),
                    "GA":
                        int(jogo["ga"]),
                    "Resultado":
                        jogo["result"],
                })

            st.dataframe(
                pd.DataFrame(tabela),
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.info(
                "Sem L10 disponível."
            )

    with c2:

        st.markdown(
            f"**{event.get('away')}**"
        )

        st.write(
            f"Jogos: {len(away_l10)}"
        )

        if away_l10:

            tabela = []

            for jogo in away_l10:

                tabela.append({
                    "Data":
                        jogo["date"],
                    "Adversário":
                        jogo["opponent"],
                    "GF":
                        int(jogo["gf"]),
                    "GA":
                        int(jogo["ga"]),
                    "Resultado":
                        jogo["result"],
                })

            st.dataframe(
                pd.DataFrame(tabela),
                use_container_width=True,
                hide_index=True,
            )

        else:

            st.info(
                "Sem L10 disponível."
            )

    st.markdown(
        "### 🎯 Mercados"
    )

    market_rows = []

    for item in suggestions_list:

        market_rows.append({

            "Mercado":
                item["Mercado"],

            "Probabilidade":
                f"{item['Probabilidade']:.1f}%",

            "Odd justa":
                f"{item['Odd justa']:.2f}",
        })

    st.dataframe(
        pd.DataFrame(market_rows),
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    st.title(
        "⚽ Global Football Scanner"
    )

    st.caption(
        "Scanner de partidas com análise L10 "
        "e probabilidades estimadas."
    )

    # --------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------

    st.sidebar.header(
        "⚙️ Configurações"
    )

    mostrar_ao_vivo = st.sidebar.checkbox(
        "🔴 Mostrar ao vivo",
        value=True
    )

    mostrar_proximos = st.sidebar.checkbox(
        "🕒 Mostrar próximos",
        value=True
    )

    mostrar_finalizados = st.sidebar.checkbox(
        "✅ Mostrar finalizados",
        value=False
    )

    limite = st.sidebar.slider(
        "Quantidade de jogos",
        min_value=5,
        max_value=100,
        value=30
    )

    if st.sidebar.button(
        "🔄 Atualizar agora"
    ):

        st.rerun()

    # --------------------------------------------------------
    # STATUS DAS APIS
    # --------------------------------------------------------

    with st.expander(
        "🔌 Status das APIs",
        expanded=False
    ):

        st.write(
            "TheSportsDB: "
            "✅ disponível"
        )

        st.write(
            "football-data.org: "
            + (
                "✅ token configurado"
                if FD_TOKEN
                else "⚠️ token não configurado"
            )
        )

        st.write(
            "OpenFootAPI: "
            + (
                "✅ token configurado"
                if OPENFOOT_TOKEN
                else "⚠️ token não configurado"
            )
        )

        st.write(
            "5DollarFootballAPI: "
            + (
                "✅ token configurado"
                if FD5_TOKEN
                else "⚠️ token não configurado"
            )
        )

    # --------------------------------------------------------
    # CARREGAMENTO
    # --------------------------------------------------------

    with st.spinner(
        "Buscando partidas..."
    ):

        events = load_global_events()

    if not events:

        st.warning(
            "Nenhuma partida foi encontrada."
        )

        st.info(
            "Verifique as chaves das APIs "
            "e tente atualizar novamente."
        )

        return

    # --------------------------------------------------------
    # FILTRO
    # --------------------------------------------------------

    filtered = []

    for event in events:

        tipo = classify_event(
            event
        )

        if tipo == "live" and mostrar_ao_vivo:
            filtered.append(event)

        elif (
            tipo == "upcoming"
            and mostrar_proximos
        ):
            filtered.append(event)

        elif (
            tipo == "finished"
            and mostrar_finalizados
        ):
            filtered.append(event)

    # --------------------------------------------------------
    # ORDENAR
    # --------------------------------------------------------

    filtered.sort(
        key=lambda x: (
            parse_kickoff(
                x.get("kickoff")
            )
            or datetime.max.replace(
                tzinfo=timezone.utc
            )
        )
    )

    filtered = filtered[:limite]

    # --------------------------------------------------------
    # RESUMO
    # --------------------------------------------------------

    st.success(
        f"{len(events)} partidas encontradas | "
        f"{len(filtered)} exibidas"
    )

    # --------------------------------------------------------
    # TABELA RESUMIDA
    # --------------------------------------------------------

    resumo = []

    for event in filtered:

        tipo = classify_event(
            event
        )

        kickoff = parse_kickoff(
            event.get("kickoff")
        )

        resumo.append({

            "Status":
                (
                    "🔴 AO VIVO"
                    if tipo == "live"
                    else
                    "🕒 PRÉ-JOGO"
                    if tipo == "upcoming"
                    else
                    "✅ FINAL"
                ),

            "Data":
                (
                    kickoff.strftime(
                        "%d/%m %H:%M"
                    )
                    if kickoff
                    else "-"
                ),

            "Casa":
                event.get(
                    "home",
                    "Casa"
                ),

            "Placar":
                display_score(
                    event
                ),

            "Fora":
                event.get(
                    "away",
                    "Fora"
                ),

            "Fonte":
                event.get(
                    "source",
                    "-"
                ),
        })

    if resumo:

        st.markdown(
            "### 📋 Partidas"
        )

        st.dataframe(
            pd.DataFrame(resumo),
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------------
    # ANÁLISES
    # --------------------------------------------------------

    st.markdown(
        "## 📊 Análises"
    )

    for event in filtered:

        try:

            analysis = analyze_event(
                event,
                events
            )

            render_match_card(
                analysis
            )

        except Exception as error:

            st.error(
                "Erro ao analisar "
                f"{event.get('home')} x "
                f"{event.get('away')}: "
                f"{error}"
            )


# ============================================================
# EXECUÇÃO SEGURA
# ============================================================

try:

    main()

except Exception as error:

    st.error(
        "❌ O aplicativo encontrou um erro."
    )

    st.code(
        traceback.format_exc()
    )
