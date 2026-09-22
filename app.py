# ============================================================
# GLOBAL FOOTBALL SCANNER
# L10 OBRIGATÓRIO — ÚLTIMOS 10 JOGOS
# AO VIVO + PRÉ-JOGO
# ============================================================

import os
import math
import re
import traceback

from datetime import datetime, timedelta, date, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# ============================================================
# CONFIGURAÇÃO DO STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Global Football Scanner",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CONFIGURAÇÕES
# ============================================================

TSDB_KEY = os.getenv(
    "THESPORTSDB_API_KEY",
    "123"
)

TSDB_BASE = (
    f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"
)

FD_TOKEN = os.getenv(
    "FOOTBALL_DATA_API_TOKEN",
    ""
)

FD_BASE = "https://api.football-data.org/v4"

FD5_TOKEN = os.getenv(
    "FIVEDOLLAR_FOOTBALL_API_KEY",
    os.getenv(
        "FIVEDOLLAR_FOOTBALLAPI_KEY",
        ""
    )
)

FD5_BASE = "https://api.5dollarfootballapi.com/v1"

OPENFOOT_TOKEN = os.getenv(
    "OPENFOOT_API_KEY",
    ""
)

OPENFOOT_BASE = "https://openfootapi.com/v1"

TIMEOUT = 15

CACHE_TTL = 1800

CALENDAR_TTL = 20

BRT = ZoneInfo("America/Sao_Paulo")

# ============================================================
# L10 É OBRIGATÓRIO
# ============================================================

L10_N = 10


# ============================================================
# STATUS
# ============================================================

LIVE_STATUSES = {
    "LIVE",
    "IN_PLAY",
    "1H",
    "2H",
    "HT",
    "ET",
    "P",
    "LIVE",
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

    try:
        return f"{safe_float(value):.1f}%"

    except Exception:

        return "0.0%"


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


def is_live_status(status):

    return norm_status(status) in LIVE_STATUSES


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

    status = norm_status(
        event.get("status", "")
    )

    if status in LIVE_STATUSES:

        return "live"

    if status in FINAL_STATUSES:

        return "finished"

    if status in PRE_STATUSES:

        return "upcoming"

    kickoff = parse_kickoff(
        event.get("kickoff")
    )

    if kickoff:

        now = datetime.now(BRT)

        if kickoff <= now:

            return "live"

        return "upcoming"

    return "unknown"


# ============================================================
# POISSON
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


def model_probs(
    home_lambda,
    away_lambda
):

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
    over25 = 0.0
    under25 = 0.0
    over15 = 0.0
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

            p = ph * pa

            if hg > ag:
                home_win += p

            elif hg == ag:
                draw += p

            else:
                away_win += p

            total = hg + ag

            if hg >= 1 and ag >= 1:
                btts += p

            if total >= 3:
                over25 += p
            else:
                under25 += p

            if total >= 2:
                over15 += p

            if total <= 3:
                under35 += p

    total_prob = (
        home_win
        + draw
        + away_win
    )

    if total_prob <= 0:
        total_prob = 1.0

    home_win /= total_prob
    draw /= total_prob
    away_win /= total_prob
    btts /= total_prob
    over25 /= total_prob
    under25 /= total_prob
    over15 /= total_prob
    under35 /= total_prob

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
# HTTP SEGURO
# ============================================================

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


def request_openfoot(
    url,
    headers=None,
    params=None,
    timeout=TIMEOUT
):

    return request_json(
        url,
        headers=headers,
        params=params,
        timeout=timeout
    )


# ============================================================
# FUNÇÕES DE FONTES
# ============================================================

@st.cache_data(
    ttl=CALENDAR_TTL,
    show_spinner=False
)
def tsdb_day(day):

    url = (
        f"{TSDB_BASE}/"
        f"eventsday.php"
    )

    data = request_json(
        url,
        params={
            "d": day,
            "s": "Soccer"
        }
    )

    if not data:

        return []

    return data.get(
        "events",
        []
    ) or []


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False
)
def tsdb_team_search(team):

    if not team:
        return []

    url = (
        f"{TSDB_BASE}/"
        f"searchteams.php"
    )

    data = request_json(
        url,
        params={
            "t": team
        }
    )

    if not data:

        return []

    return data.get(
        "teams",
        []
    ) or []


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False
)
def tsdb_last(team_id):

    if not team_id:
        return []

    url = (
        f"{TSDB_BASE}/"
        f"eventslast.php"
    )

    data = request_json(
        url,
        params={
            "id": team_id
        }
    )

    if not data:

        return []

    return data.get(
        "results",
        []
    ) or []


# ============================================================
# NORMALIZAÇÃO THESPORTSDB
# ============================================================

def normalize_tsdb_event(event):

    if not event:
        return None

    try:

        home_id = event.get(
            "idHomeTeam"
        )

        away_id = event.get(
            "idAwayTeam"
        )

        home = (
            event.get("strHomeTeam")
            or "Casa"
        )

        away = (
            event.get("strAwayTeam")
            or "Fora"
        )

        date_value = (
            event.get("dateEvent")
            or ""
        )

        time_value = (
            event.get("strTime")
            or "00:00:00"
        )

        kickoff = None

        if date_value:

            kickoff = (
                f"{date_value}T"
                f"{time_value}"
            )

        home_score = event.get(
            "intHomeScore"
        )

        away_score = event.get(
            "intAwayScore"
        )

        status = (
            event.get("strStatus")
            or ""
        )

        return {

            "id": str(
                event.get(
                    "idEvent",
                    ""
                )
            ),

            "home": home,

            "away": away,

            "home_id": str(
                home_id or ""
            ),

            "away_id": str(
                away_id or ""
            ),

            "kickoff": kickoff,

            "status": status,

            "home_score": home_score,

            "away_score": away_score,

            "source": "TheSportsDB",

            "raw": event,

        }

    except Exception:

        return None


# ============================================================
# FOOTBALL-DATA
# ============================================================

@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False
)
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


@st.cache_data(
    ttl=CALENDAR_TTL,
    show_spinner=False
)
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
            event.get(
                "homeTeam",
                {}
            ) or {}
        )

        away = (
            event.get(
                "awayTeam",
                {}
            ) or {}
        )

        score = (
            event.get(
                "score",
                {}
            ) or {}
        )

        full_time = (
            score.get(
                "fullTime",
                {}
            ) or {}
        )

        return {

            "id": str(
                event.get(
                    "id",
                    ""
                )
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

            "kickoff": (
                event.get(
                    "utcDate"
                )
            ),

            "status": (
                event.get(
                    "status",
                    ""
                )
            ),

            "home_score": (
                full_time.get(
                    "home"
                )
            ),

            "away_score": (
                full_time.get(
                    "away"
                )
            ),

            "source": (
                "football-data.org"
            ),

            "raw": event,

        }

    except Exception:

        return None


# ============================================================
# OPENFOOT
# ============================================================

@st.cache_data(
    ttl=CALENDAR_TTL,
    show_spinner=False
)
def openfoot_matches():

    if not OPENFOOT_TOKEN:

        return []

    data = request_openfoot(
        f"{OPENFOOT_BASE}/matches",
        headers={
            "Authorization":
                f"Bearer {OPENFOOT_TOKEN}"
        }
    )

    if not data:

        return []

    if isinstance(
        data,
        list
    ):

        return data

    return (
        data.get("matches")
        or data.get("data")
        or []
    )


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False
)
def openfoot_team_search(team):

    if not OPENFOOT_TOKEN:
        return []

    data = request_openfoot(
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

    if isinstance(
        data,
        list
    ):
        return data

    return (
        data.get("teams")
        or data.get("data")
        or []
    )


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False
)
def openfoot_team_matches(
    team_id
):

    if not OPENFOOT_TOKEN:
        return []

    data = request_openfoot(
        f"{OPENFOOT_BASE}/teams/"
        f"{team_id}/matches",
        headers={
            "Authorization":
                f"Bearer {OPENFOOT_TOKEN}"
        }
    )

    if not data:
        return []

    if isinstance(
        data,
        list
    ):
        return data

    return (
        data.get("matches")
        or data.get("data")
        or []
    )


def normalize_openfoot_event(
    event
):

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

        if isinstance(
            home,
            str
        ):

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

        if isinstance(
            away,
            str
        ):

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
                event.get(
                    "id",
                    ""
                )
            ),

            "home": home_name,

            "away": away_name,

            "home_id": home_id,

            "away_id": away_id,

            "kickoff": (
                event.get(
                    "kickoff"
                )
                or event.get(
                    "date"
                )
                or event.get(
                    "utcDate"
                )
            ),

            "status": (
                event.get(
                    "status",
                    ""
                )
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
# 5DOLLAR FOOTBALL API
# ============================================================

@st.cache_data(
    ttl=CALENDAR_TTL,
    show_spinner=False
)
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

    if isinstance(
        data,
        list
    ):

        return data

    return (
        data.get("fixtures")
        or data.get("data")
        or []
    )


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False
)
def fd5_team_fixtures(
    team_id
):

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

    if isinstance(
        data,
        list
    ):
        return data

    return (
        data.get("fixtures")
        or data.get("data")
        or []
    )


def normalize_fd5_event(
    event
):

    if not event:
        return None

    try:

        home = (
            event.get("home")
            or event.get(
                "homeTeam"
            )
            or {}
        )

        away = (
            event.get("away")
            or event.get(
                "awayTeam"
            )
            or {}
        )

        if isinstance(
            home,
            str
        ):

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

        if isinstance(
            away,
            str
        ):

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
                event.get(
                    "id",
                    ""
                )
            ),

            "home": home_name,

            "away": away_name,

            "home_id": home_id,

            "away_id": away_id,

            "kickoff": (
                event.get(
                    "kickoff"
                )
                or event.get(
                    "date"
                )
                or event.get(
                    "utcDate"
                )
            ),

            "status": (
                event.get(
                    "status",
                    ""
                )
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

            "source": (
                "5DollarFootballAPI"
            ),

            "raw": event,

        }

    except Exception:

        return None
