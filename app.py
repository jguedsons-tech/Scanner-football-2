# ============================================================
# GLOBAL FOOTBALL SCANNER
# 4 APIs + HISTÓRICO UNIFICADO + L10 + PROBABILIDADES
# + OPENROUTER GRATUITO
# ============================================================

import os
import re
import math
import traceback
from datetime import datetime, timedelta, timezone
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
)


# ============================================================
# CHAVES / APIs
# ============================================================

# ------------------------------------------------------------
# TheSportsDB
# ------------------------------------------------------------

TSDB_KEY = os.getenv(
    "THESPORTSDB_API_KEY",
    "123"
)

TSDB_BASE = f"https://www.thesportsdb.com/api/v1/json/{TSDB_KEY}"


# ------------------------------------------------------------
# football-data.org
# ------------------------------------------------------------

FD_TOKEN = os.getenv(
    "FOOTBALL_DATA_API_TOKEN",
    ""
)

FD_BASE = "https://api.football-data.org/v4"


# ------------------------------------------------------------
# 5DollarFootballAPI
# ------------------------------------------------------------

FD5_TOKEN = os.getenv(
    "FIVEDOLLAR_FOOTBALL_API_KEY",
    os.getenv(
        "FIVEDOLLAR_FOOTBALLAPI_KEY",
        ""
    )
)

FD5_BASE = os.getenv(
    "FIVEDOLLAR_FOOTBALL_BASE",
    "https://api.5dollarfootballapi.com/v1"
)


# ------------------------------------------------------------
# OpenFootAPI
# ------------------------------------------------------------

OPENFOOT_TOKEN = os.getenv(
    "OPENFOOT_API_KEY",
    ""
)

OPENFOOT_BASE = os.getenv(
    "OPENFOOT_API_BASE",
    "https://openfootapi.com/v1"
)


# ------------------------------------------------------------
# OPENROUTER
# ------------------------------------------------------------

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    ""
)

# Roteador oficial de modelos gratuitos
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openrouter/free"
)

OPENROUTER_BASE = "https://openrouter.ai/api/v1"


# ============================================================
# CONFIGURAÇÕES GERAIS
# ============================================================

TIMEOUT = 15

HISTORY_PER_API = 20

FINAL_HISTORY = 20

BRT = ZoneInfo("America/Sao_Paulo")


LIVE_STATUSES = {
    "LIVE",
    "IN_PLAY",
    "INPLAY",
    "1H",
    "2H",
    "HT",
    "ET",
    "P",
    "HALF_TIME",
    "SECOND_HALF",
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
    "NOT_STARTED",
}


SOURCE_PRIORITY = {
    "5DollarFootballAPI": 4,
    "OpenFootAPI": 3,
    "football-data.org": 2,
    "TheSportsDB": 1,
}


# ============================================================
# FUNÇÕES BÁSICAS
# ============================================================

def safe_float(value, default=0.0):

    try:

        if value is None or value == "":
            return default

        return float(value)

    except Exception:

        return default


def pct(value):

    try:

        return round(float(value) * 100, 1)

    except Exception:

        return 0.0


def fair_odd(probability):

    if probability is None or probability <= 0:
        return None

    try:

        return round(1 / probability, 2)

    except Exception:

        return None


def norm_status(status):

    if status is None:
        return ""

    return (
        str(status)
        .upper()
        .strip()
        .replace("-", "_")
        .replace(" ", "_")
    )


# ============================================================
# NORMALIZAÇÃO DE NOMES
# ============================================================

def normalize_name(name):

    if not name:
        return ""

    text = str(name).lower().strip()

    replacements = {

        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "ä": "a",

        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",

        "í": "i",
        "ì": "i",
        "î": "i",
        "ï": "i",

        "ó": "o",
        "ò": "o",
        "õ": "o",
        "ô": "o",
        "ö": "o",

        "ú": "u",
        "ù": "u",
        "û": "u",
        "ü": "u",

        "ç": "c",
    }

    for a, b in replacements.items():
        text = text.replace(a, b)

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text
    )

    return " ".join(text.split())


def team_match(name_a, name_b):

    a = normalize_name(name_a)
    b = normalize_name(name_b)

    if not a or not b:
        return False

    if a == b:
        return True

    if a in b or b in a:
        return True

    wa = set(
        x for x in a.split()
        if len(x) >= 4
    )

    wb = set(
        x for x in b.split()
        if len(x) >= 4
    )

    if not wa or not wb:
        return False

    return (
        len(wa.intersection(wb))
        >= max(
            1,
            min(len(wa), len(wb)) // 2
        )
    )


# ============================================================
# DATAS
# ============================================================

def parse_kickoff(value):

    if not value:
        return None

    if isinstance(value, datetime):

        dt = value

    else:

        text = str(value).strip()

        if not text:
            return None

        try:

            dt = datetime.fromisoformat(
                text.replace(
                    "Z",
                    "+00:00"
                )
            )

        except Exception:

            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
                "%d/%m/%Y %H:%M",
                "%d/%m/%Y",
            ]

            dt = None

            for fmt in formats:

                try:

                    dt = datetime.strptime(
                        text,
                        fmt
                    )

                    break

                except Exception:

                    pass

            if dt is None:
                return None

    if dt.tzinfo is None:

        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt.astimezone(BRT)


def format_datetime(dt):

    if not dt:
        return "-"

    return dt.astimezone(
        BRT
    ).strftime(
        "%d/%m/%Y %H:%M"
    )


def event_date(event):

    dt = parse_kickoff(
        event.get("kickoff")
    )

    return dt.date() if dt else None


# ============================================================
# REQUEST HTTP
# ============================================================

def request_json(
    url,
    headers=None,
    params=None
):

    try:

        response = requests.get(
            url,
            headers=headers or {},
            params=params or {},
            timeout=TIMEOUT
        )

        if response.status_code >= 400:
            return None

        return response.json()

    except Exception:

        return None


# ============================================================
# CLASSIFICAÇÃO
# ============================================================

def classify_event(event):

    status = norm_status(
        event.get("status")
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

        if kickoff > now:
            return "upcoming"

        if (
            event.get("home_score") is not None
            and event.get("away_score") is not None
        ):
            return "finished"

    return "unknown"


def event_is_finished(event):

    return (
        classify_event(event)
        == "finished"
    )


# ============================================================
# MODELO DE POISSON
# ============================================================

def poisson_pmf(k, lamb):

    try:

        return (
            math.exp(-lamb)
            * (lamb ** k)
            / math.factorial(k)
        )

    except Exception:

        return 0.0


def model_probs(
    home_lambda,
    away_lambda
):

    result = {

        "home_win": 0,
        "draw": 0,
        "away_win": 0,

        "1x": 0,
        "x2": 0,

        "btts_yes": 0,
        "btts_no": 0,

        "over05": 0,
        "over15": 0,
        "over25": 0,
        "over35": 0,

        "under15": 0,
        "under25": 0,
        "under35": 0,
    }

    for hg in range(0, 11):

        for ag in range(0, 11):

            p = (
                poisson_pmf(
                    hg,
                    home_lambda
                )
                *
                poisson_pmf(
                    ag,
                    away_lambda
                )
            )

            total = hg + ag

            if hg > ag:

                result["home_win"] += p

            elif hg == ag:

                result["draw"] += p

            else:

                result["away_win"] += p

            if hg >= ag:
                result["1x"] += p

            if ag >= hg:
                result["x2"] += p

            if hg > 0 and ag > 0:

                result["btts_yes"] += p

            else:

                result["btts_no"] += p

            if total >= 1:
                result["over05"] += p

            if total >= 2:
                result["over15"] += p

            if total >= 3:
                result["over25"] += p

            if total >= 4:
                result["over35"] += p

            if total <= 1:
                result["under15"] += p

            if total <= 2:
                result["under25"] += p

            if total <= 3:
                result["under35"] += p

    return result


# ============================================================
# THE SPORTS DB
# ============================================================

def tsdb_day(day):

    data = request_json(

        f"{TSDB_BASE}/eventsday.php",

        params={
            "d": day.strftime(
                "%Y-%m-%d"
            ),
            "s": "Soccer",
        }
    )

    if not data:
        return []

    return data.get(
        "events"
    ) or []


def tsdb_team_search(team):

    data = request_json(

        f"{TSDB_BASE}/searchteams.php",

        params={
            "t": team
        }
    )

    if not data:
        return []

    return data.get(
        "teams"
    ) or []


def tsdb_last(team_id):

    data = request_json(

        f"{TSDB_BASE}/eventslast.php",

        params={
            "id": team_id
        }
    )

    if not data:
        return []

    return (
        data.get("results")
        or data.get("events")
        or []
    )


def normalize_tsdb_event(ev):

    home = (
        ev.get("strHomeTeam")
        or ""
    )

    away = (
        ev.get("strAwayTeam")
        or ""
    )

    home_score = ev.get(
        "intHomeScore"
    )

    away_score = ev.get(
        "intAwayScore"
    )

    return {

        "source":
            "TheSportsDB",

        "source_id":
            str(
                ev.get("idEvent")
                or ""
            ),

        "home":
            home,

        "away":
            away,

        "home_id":
            ev.get("idHomeTeam"),

        "away_id":
            ev.get("idAwayTeam"),

        "home_score":
            int(home_score)
            if str(home_score).isdigit()
            else None,

        "away_score":
            int(away_score)
            if str(away_score).isdigit()
            else None,

        "status":
            ev.get("strStatus")
            or ev.get("strProgress")
            or "",

        "kickoff":
            ev.get("strTimestamp")
            or ev.get("dateEvent")
            or ev.get("strDate"),

        "league":
            ev.get("strLeague")
            or "",

        "country":
            ev.get("strCountry")
            or "",
    }


def get_tsdb_team_history(
    team_id
):

    events = tsdb_last(
        team_id
    )

    normalized = []

    for ev in events:

        item = normalize_tsdb_event(
            ev
        )

        if (
            event_is_finished(item)
            and item["home_score"]
            is not None
            and item["away_score"]
            is not None
        ):

            normalized.append(item)

    normalized.sort(
        key=lambda x:
        parse_kickoff(
            x.get("kickoff")
        )
        or datetime.min.replace(
            tzinfo=timezone.utc
        ),
        reverse=True
    )

    return normalized[
        :HISTORY_PER_API
    ]


# ============================================================
# FOOTBALL-DATA.ORG
# ============================================================

def fd_headers():

    if not FD_TOKEN:
        return {}

    return {
        "X-Auth-Token":
            FD_TOKEN
    }


def fd_matches(
    date_from,
    date_to
):

    if not FD_TOKEN:
        return []

    data = request_json(

        f"{FD_BASE}/matches",

        headers=fd_headers(),

        params={

            "dateFrom":
                date_from.strftime(
                    "%Y-%m-%d"
                ),

            "dateTo":
                date_to.strftime(
                    "%Y-%m-%d"
                ),
        }
    )

    if not data:
        return []

    return data.get(
        "matches"
    ) or []


def fd_team_matches(
    team_id,
    date_from=None,
    date_to=None
):

    if not FD_TOKEN or not team_id:
        return []

    params = {

        "status":
            "FINISHED",

        "limit":
            100,
    }

    if date_from:

        params["dateFrom"] = (
            date_from.strftime(
                "%Y-%m-%d"
            )
        )

    if date_to:

        params["dateTo"] = (
            date_to.strftime(
                "%Y-%m-%d"
            )
        )

    data = request_json(

        f"{FD_BASE}/teams/{team_id}/matches",

        headers=fd_headers(),

        params=params
    )

    if not data:
        return []

    return data.get(
        "matches"
    ) or []


def normalize_fd_event(ev):

    home_obj = (
        ev.get("homeTeam")
        or {}
    )

    away_obj = (
        ev.get("awayTeam")
        or {}
    )

    score = (
        ev.get("score")
        or {}
    )

    full_time = (
        score.get("fullTime")
        or {}
    )

    return {

        "source":
            "football-data.org",

        "source_id":
            str(
                ev.get("id")
                or ""
            ),

        "home":
            home_obj.get("name")
            or "",

        "away":
            away_obj.get("name")
            or "",

        "home_id":
            home_obj.get("id"),

        "away_id":
            away_obj.get("id"),

        "home_score":
            full_time.get("home"),

        "away_score":
            full_time.get("away"),

        "status":
            ev.get("status")
            or "",

        "kickoff":
            ev.get("utcDate"),

        "league":
            (
                ev.get("competition")
                or {}
            ).get("name")
            or "",

        "country":
            (
                ev.get("area")
                or {}
            ).get("name")
            or "",
    }


# ============================================================
# OPENFOOT
# ============================================================

def openfoot_headers():

    if not OPENFOOT_TOKEN:
        return {}

    return {

        "Authorization":
            f"Bearer {OPENFOOT_TOKEN}",

        "X-API-Key":
            OPENFOOT_TOKEN,
    }


def openfoot_matches():

    if not OPENFOOT_TOKEN:
        return []

    data = request_json(

        f"{OPENFOOT_BASE}/matches",

        headers=openfoot_headers()
    )

    if not data:
        return []

    if isinstance(data, list):
        return data

    return (
        data.get("matches")
        or data.get("data")
        or data.get("events")
        or []
    )


def openfoot_team_history(
    team_id=None,
    team_name=None
):

    if not OPENFOOT_TOKEN:
        return []

    params = {}

    if team_id:

        params["team_id"] = team_id

    elif team_name:

        params["team"] = team_name

    urls = [

        f"{OPENFOOT_BASE}/matches",

        f"{OPENFOOT_BASE}/team/matches",

        (
            f"{OPENFOOT_BASE}/teams/{team_id}/matches"
            if team_id
            else None
        ),
    ]

    for url in urls:

        if not url:
            continue

        data = request_json(

            url,

            headers=openfoot_headers(),

            params=params
        )

        if not data:
            continue

        if isinstance(data, list):
            return data

        items = (

            data.get("matches")
            or data.get("data")
            or data.get("events")
            or []
        )

        if items:
            return items

    return []


def normalize_openfoot_event(ev):

    home_obj = (
        ev.get("homeTeam")
        or ev.get("home_team")
        or {}
    )

    away_obj = (
        ev.get("awayTeam")
        or ev.get("away_team")
        or {}
    )

    home = (

        home_obj.get("name")
        if isinstance(
            home_obj,
            dict
        )
        else home_obj

    ) or (

        ev.get("home")
        or ev.get("home_name")
        or ""
    )

    away = (

        away_obj.get("name")
        if isinstance(
            away_obj,
            dict
        )
        else away_obj

    ) or (

        ev.get("away")
        or ev.get("away_name")
        or ""
    )

    score = (
        ev.get("score")
        or {}
    )

    full = (

        score.get("fullTime")
        or score.get("full_time")
        or {}
    )

    home_score = (

        full.get("home")
        if isinstance(full, dict)
        else None
    )

    away_score = (

        full.get("away")
        if isinstance(full, dict)
        else None
    )

    if home_score is None:

        home_score = (
            ev.get("home_score")
            or ev.get("homeScore")
        )

    if away_score is None:

        away_score = (
            ev.get("away_score")
            or ev.get("awayScore")
        )

    league = ev.get(
        "league"
    )

    if isinstance(
        league,
        dict
    ):

        league = league.get(
            "name",
            ""
        )

    return {

        "source":
            "OpenFootAPI",

        "source_id":
            str(
                ev.get("id")
                or ev.get("match_id")
                or ev.get("event_id")
                or ""
            ),

        "home":
            home,

        "away":
            away,

        "home_id":
            (
                home_obj.get("id")
                if isinstance(
                    home_obj,
                    dict
                )
                else ev.get("home_id")
            ),

        "away_id":
            (
                away_obj.get("id")
                if isinstance(
                    away_obj,
                    dict
                )
                else ev.get("away_id")
            ),

        "home_score":
            home_score,

        "away_score":
            away_score,

        "status":
            ev.get("status")
            or ev.get("state")
            or ev.get("match_status")
            or "",

        "kickoff":
            ev.get("utcDate")
            or ev.get("date")
            or ev.get("datetime")
            or ev.get("kickoff"),

        "league":
            league or "",

        "country":
            ev.get("country")
            or "",
    }


# ============================================================
# 5DOLLAR FOOTBALL API
# ============================================================

def fd5_headers():

    if not FD5_TOKEN:
        return {}

    return {

        "Authorization":
            f"Bearer {FD5_TOKEN}",

        "X-API-Key":
            FD5_TOKEN,

        "Accept":
            "application/json",
    }


def fd5_day(day):

    if not FD5_TOKEN:
        return []

    urls = [

        f"{FD5_BASE}/matches",

        f"{FD5_BASE}/events",
    ]

    params = {

        "date":
            day.strftime(
                "%Y-%m-%d"
            )
    }

    for url in urls:

        data = request_json(

            url,

            headers=fd5_headers(),

            params=params
        )

        if not data:
            continue

        if isinstance(data, list):
            return data

        items = (

            data.get("matches")
            or data.get("events")
            or data.get("data")
            or []
        )

        if items:
            return items

    return []


def fd5_team_history(
    team_id=None,
    team_name=None
):

    if not FD5_TOKEN:
        return []

    params = {

        "status":
            "finished",

        "limit":
            100,
    }

    if team_id:

        params["team_id"] = team_id

    elif team_name:

        params["team"] = team_name

    urls = [

        f"{FD5_BASE}/matches",

        f"{FD5_BASE}/events",
    ]

    for url in urls:

        data = request_json(

            url,

            headers=fd5_headers(),

            params=params
        )

        if not data:
            continue

        if isinstance(data, list):
            return data

        items = (

            data.get("matches")
            or data.get("events")
            or data.get("data")
            or []
        )

        if items:
            return items

    return []


def normalize_fd5_event(ev):

    home_obj = (
        ev.get("homeTeam")
        or ev.get("home_team")
        or {}
    )

    away_obj = (
        ev.get("awayTeam")
        or ev.get("away_team")
        or {}
    )

    home = (

        home_obj.get("name")
        if isinstance(
            home_obj,
            dict
        )
        else home_obj

    ) or (

        ev.get("home")
        or ev.get("home_name")
        or ""
    )

    away = (

        away_obj.get("name")
        if isinstance(
            away_obj,
            dict
        )
        else away_obj

    ) or (

        ev.get("away")
        or ev.get("away_name")
        or ""
    )

    score = (
        ev.get("score")
        or {}
    )

    home_score = (
        ev.get("home_score")
        or ev.get("homeScore")
        or score.get("home")
    )

    away_score = (
        ev.get("away_score")
        or ev.get("awayScore")
        or score.get("away")
    )

    league = ev.get(
        "league"
    )

    if isinstance(
        league,
        dict
    ):

        league = league.get(
            "name",
            ""
        )

    return {

        "source":
            "5DollarFootballAPI",

        "source_id":
            str(
                ev.get("id")
                or ev.get("match_id")
                or ev.get("event_id")
                or ""
            ),

        "home":
            home,

        "away":
            away,

        "home_id":
            (
                home_obj.get("id")
                if isinstance(
                    home_obj,
                    dict
                )
                else ev.get("home_id")
            ),

        "away_id":
            (
                away_obj.get("id")
                if isinstance(
                    away_obj,
                    dict
                )
                else ev.get("away_id")
            ),

        "home_score":
            home_score,

        "away_score":
            away_score,

        "status":
            ev.get("status")
            or ev.get("state")
            or "",

        "kickoff":
            ev.get("utcDate")
            or ev.get("date")
            or ev.get("datetime")
            or ev.get("kickoff"),

        "league":
            league or "",

        "country":
            ev.get("country")
            or "",
    }


# ============================================================
# DUPLICAÇÃO / UNIFICAÇÃO
# ============================================================

def event_key(event):

    source = event.get(
        "source",
        ""
    )

    source_id = event.get(
        "source_id",
        ""
    )

    if source_id:

        return (
            f"{source}:"
            f"{source_id}"
        )

    home = normalize_name(
        event.get("home")
    )

    away = normalize_name(
        event.get("away")
    )

    dt = parse_kickoff(
        event.get("kickoff")
    )

    date_key = (
        dt.strftime("%Y%m%d")
        if dt
        else ""
    )

    return (
        f"{home}|"
        f"{away}|"
        f"{date_key}"
    )


def same_match(a, b):

    if not team_match(
        a.get("home"),
        b.get("home")
    ):
        return False

    if not team_match(
        a.get("away"),
        b.get("away")
    ):
        return False

    da = parse_kickoff(
        a.get("kickoff")
    )

    db = parse_kickoff(
        b.get("kickoff")
    )

    if da and db:

        return (
            abs(
                (da - db)
                .total_seconds()
            )
            <= 36 * 3600
        )

    return True


def merge_events(events):

    result = []

    ordered = sorted(

        events,

        key=lambda e:
        SOURCE_PRIORITY.get(
            e.get("source"),
            0
        ),

        reverse=True
    )

    for event in ordered:

        if not event.get("home"):
            continue

        if not event.get("away"):
            continue

        duplicate_index = None

        for i, existing in enumerate(
            result
        ):

            if same_match(
                event,
                existing
            ):

                duplicate_index = i

                break

        if duplicate_index is None:

            result.append(
                event
            )

        else:

            existing = result[
                duplicate_index
            ]

            for field in [

                "home_score",
                "away_score",
                "kickoff",
                "league",
                "country",
                "status",
                "home_id",
                "away_id",

            ]:

                if (

                    existing.get(field)
                    in (
                        None,
                        "",
                        "-"
                    )

                    and

                    event.get(field)
                    not in (
                        None,
                        "",
                        "-"
                    )
                ):

                    existing[field] = (
                        event[field]
                    )

    return result


# ============================================================
# PARTIDAS DO DIA
# ============================================================

def load_global_events():

    today = (
        datetime
        .now(BRT)
        .date()
    )

    raw = []


    # --------------------------------------------------------
    # TheSportsDB
    # --------------------------------------------------------

    try:

        for ev in tsdb_day(
            today
        ):

            raw.append(
                normalize_tsdb_event(
                    ev
                )
            )

    except Exception:

        pass


    # --------------------------------------------------------
    # football-data.org
    # --------------------------------------------------------

    if FD_TOKEN:

        try:

            for ev in fd_matches(
                today,
                today
            ):

                raw.append(
                    normalize_fd_event(
                        ev
                    )
                )

        except Exception:

            pass


    # --------------------------------------------------------
    # OpenFoot
    # --------------------------------------------------------

    if OPENFOOT_TOKEN:

        try:

            for ev in openfoot_matches():

                item = (
                    normalize_openfoot_event(
                        ev
                    )
                )

                dt = parse_kickoff(
                    item.get(
                        "kickoff"
                    )
                )

                if (
                    not dt
                    or dt.date()
                    == today
                ):

                    raw.append(
                        item
                    )

        except Exception:

            pass


    # --------------------------------------------------------
    # 5Dollar
    # --------------------------------------------------------

    if FD5_TOKEN:

        try:

            for ev in fd5_day(
                today
            ):

                raw.append(
                    normalize_fd5_event(
                        ev
                    )
                )

        except Exception:

            pass


    return merge_events(
        raw
    )


# ============================================================
# LOCALIZAR TIME
# ============================================================

def find_tsdb_team(team):

    teams = tsdb_team_search(
        team
    )

    if not teams:
        return None

    target = normalize_name(
        team
    )

    for item in teams:

        if (
            normalize_name(
                item.get(
                    "strTeam"
                )
                or ""
            )
            == target
        ):

            return item

    return teams[0]


# ============================================================
# HISTÓRICO FOOTBALL-DATA
# ============================================================

def football_data_history(
    team_name,
    team_id=None
):

    if not FD_TOKEN:
        return []

    raw = []

    if team_id:

        try:

            raw.extend(

                fd_team_matches(

                    team_id,

                    date_from=(
                        datetime
                        .now(BRT)
                        .date()
                        - timedelta(
                            days=450
                        )
                    ),

                    date_to=(
                        datetime
                        .now(BRT)
                        .date()
                    )
                )
            )

        except Exception:

            pass


    normalized = []

    for ev in raw:

        item = normalize_fd_event(
            ev
        )

        if (

            event_is_finished(
                item
            )

            and

            item.get(
                "home_score"
            ) is not None

            and

            item.get(
                "away_score"
            ) is not None
        ):

            normalized.append(
                item
            )


    if not normalized:

        try:

            start = (
                datetime
                .now(BRT)
                .date()
                - timedelta(
                    days=365
                )
            )

            end = (
                datetime
                .now(BRT)
                .date()
            )

            raw_global = fd_matches(
                start,
                end
            )

            for ev in raw_global:

                item = (
                    normalize_fd_event(
                        ev
                    )
                )

                if (

                    event_is_finished(
                        item
                    )

                    and

                    (
                        team_match(
                            team_name,
                            item.get(
                                "home"
                            )
                        )

                        or

                        team_match(
                            team_name,
                            item.get(
                                "away"
                            )
                        )
                    )
                ):

                    normalized.append(
                        item
                    )

        except Exception:

            pass


    normalized.sort(

        key=lambda x:
        parse_kickoff(
            x.get("kickoff")
        )
        or datetime.min.replace(
            tzinfo=timezone.utc
        ),

        reverse=True
    )

    return normalized[
        :HISTORY_PER_API
    ]


# ============================================================
# HISTÓRICO OPENFOOT
# ============================================================

def openfoot_history(
    team_name,
    team_id=None
):

    if not OPENFOOT_TOKEN:
        return []

    raw = openfoot_team_history(

        team_id=team_id,

        team_name=team_name
    )

    normalized = []

    for ev in raw:

        item = (
            normalize_openfoot_event(
                ev
            )
        )

        if not (

            event_is_finished(
                item
            )

            or

            (
                item.get(
                    "home_score"
                ) is not None

                and

                item.get(
                    "away_score"
                ) is not None
            )
        ):

            continue

        if (

            team_match(
                team_name,
                item.get(
                    "home"
                )
            )

            or

            team_match(
                team_name,
                item.get(
                    "away"
                )
            )
        ):

            normalized.append(
                item
            )


    normalized = [

        x for x in normalized

        if (

            x.get(
                "home_score"
            ) is not None

            and

            x.get(
                "away_score"
            ) is not None
        )
    ]


    normalized.sort(

        key=lambda x:
        parse_kickoff(
            x.get("kickoff")
        )
        or datetime.min.replace(
            tzinfo=timezone.utc
        ),

        reverse=True
    )

    return normalized[
        :HISTORY_PER_API
    ]


# ============================================================
# HISTÓRICO 5DOLLAR
# ============================================================

def fd5_history(
    team_name,
    team_id=None
):

    if not FD5_TOKEN:
        return []

    raw = fd5_team_history(

        team_id=team_id,

        team_name=team_name
    )

    normalized = []

    for ev in raw:

        item = (
            normalize_fd5_event(
                ev
            )
        )

        if not (

            team_match(
                team_name,
                item.get(
                    "home"
                )
            )

            or

            team_match(
                team_name,
                item.get(
                    "away"
                )
            )
        ):

            continue

        if (

            item.get(
                "home_score"
            ) is None

            or

            item.get(
                "away_score"
            ) is None
        ):

            continue

        normalized.append(
            item
        )


    normalized.sort(

        key=lambda x:
        parse_kickoff(
            x.get("kickoff")
        )
        or datetime.min.replace(
            tzinfo=timezone.utc
        ),

        reverse=True
    )

    return normalized[
        :HISTORY_PER_API
    ]


# ============================================================
# HISTÓRICO UNIFICADO
# ============================================================

def build_unified_history(
    team_name,
    current_event=None
):

    all_history = []

    by_source = {

        "TheSportsDB": [],

        "football-data.org": [],

        "OpenFootAPI": [],

        "5DollarFootballAPI": [],
    }


    # --------------------------------------------------------
    # THE SPORTS DB
    # --------------------------------------------------------

    tsdb_id = None

    if current_event:

        if team_match(
            team_name,
            current_event.get(
                "home"
            )
        ):

            tsdb_id = (
                current_event.get(
                    "home_id"
                )
            )

        elif team_match(
            team_name,
            current_event.get(
                "away"
            )
        ):

            tsdb_id = (
                current_event.get(
                    "away_id"
                )
            )


    if not tsdb_id:

        try:

            found = find_tsdb_team(
                team_name
            )

            if found:

                tsdb_id = found.get(
                    "idTeam"
                )

        except Exception:

            pass


    if tsdb_id:

        try:

            hist = (
                get_tsdb_team_history(
                    tsdb_id
                )
            )

            by_source[
                "TheSportsDB"
            ] = hist

            all_history.extend(
                hist
            )

        except Exception:

            pass


    # --------------------------------------------------------
    # FOOTBALL DATA
    # --------------------------------------------------------

    fd_id = None

    if current_event:

        if team_match(
            team_name,
            current_event.get(
                "home"
            )
        ):

            fd_id = (
                current_event.get(
                    "home_id"
                )
            )

        elif team_match(
            team_name,
            current_event.get(
                "away"
            )
        ):

            fd_id = (
                current_event.get(
                    "away_id"
                )
            )


    try:

        hist = football_data_history(

            team_name,

            team_id=fd_id
        )

        by_source[
            "football-data.org"
        ] = hist

        all_history.extend(
            hist
        )

    except Exception:

        pass


    # --------------------------------------------------------
    # OPENFOOT
    # --------------------------------------------------------

    try:

        openfoot_id = None

        if current_event:

            if team_match(
                team_name,
                current_event.get(
                    "home"
                )
            ):

                openfoot_id = (
                    current_event.get(
                        "home_id"
                    )
                )

            elif team_match(
                team_name,
                current_event.get(
                    "away"
                )
            ):

                openfoot_id = (
                    current_event.get(
                        "away_id"
                    )
                )


        hist = openfoot_history(

            team_name,

            team_id=openfoot_id
        )

        by_source[
            "OpenFootAPI"
        ] = hist

        all_history.extend(
            hist
        )

    except Exception:

        pass


    # --------------------------------------------------------
    # 5DOLLAR
    # --------------------------------------------------------

    try:

        fd5_id = None

        if current_event:

            if team_match(
                team_name,
                current_event.get(
                    "home"
                )
            ):

                fd5_id = (
                    current_event.get(
                        "home_id"
                    )
                )

            elif team_match(
                team_name,
                current_event.get(
                    "away"
                )
            ):

                fd5_id = (
                    current_event.get(
                        "away_id"
                    )
                )


        hist = fd5_history(

            team_name,

            team_id=fd5_id
        )

        by_source[
            "5DollarFootballAPI"
        ] = hist

        all_history.extend(
            hist
        )

    except Exception:

        pass


    # --------------------------------------------------------
    # UNIFICAR / REMOVER DUPLICADOS
    # --------------------------------------------------------

    unified = merge_events(
        all_history
    )

    unified = [

        e for e in unified

        if (

            e.get(
                "home_score"
            ) is not None

            and

            e.get(
                "away_score"
            ) is not None
        )
    ]


    unified.sort(

        key=lambda x:
        parse_kickoff(
            x.get("kickoff")
        )
        or datetime.min.replace(
            tzinfo=timezone.utc
        ),

        reverse=True
    )


    return (
        unified[:FINAL_HISTORY],
        by_source
    )


# ============================================================
# ESTATÍSTICAS DO HISTÓRICO
# ============================================================

def history_stats(
    history,
    team
):

    if not history:

        return {

            "games": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,

            "gf": 0,
            "ga": 0,

            "avg_gf": 0,
            "avg_ga": 0,

            "btts_yes": 0,

            "over15": 0,
            "over25": 0,
            "over35": 0,

            "under25": 0,

            "clean_sheet": 0,
        }


    stats = {

        "games": 0,
        "wins": 0,
        "draws": 0,
        "losses": 0,

        "gf": 0,
        "ga": 0,

        "btts_yes": 0,

        "over15": 0,
        "over25": 0,
        "over35": 0,

        "under25": 0,

        "clean_sheet": 0,
    }


    for game in history:

        hs = game.get(
            "home_score"
        )

        aws = game.get(
            "away_score"
        )

        if hs is None or aws is None:
            continue

        hs = int(hs)
        aws = int(aws)


        if team_match(
            team,
            game.get(
                "home"
            )
        ):

            gf = hs
            ga = aws

        elif team_match(
            team,
            game.get(
                "away"
            )
        ):

            gf = aws
            ga = hs

        else:

            continue


        stats["games"] += 1

        stats["gf"] += gf

        stats["ga"] += ga


        if gf > ga:

            stats["wins"] += 1

        elif gf == ga:

            stats["draws"] += 1

        else:

            stats["losses"] += 1


        total = gf + ga


        if gf > 0 and ga > 0:

            stats[
                "btts_yes"
            ] += 1


        if total >= 2:

            stats[
                "over15"
            ] += 1


        if total >= 3:

            stats[
                "over25"
            ] += 1


        if total >= 4:

            stats[
                "over35"
            ] += 1


        if total <= 2:

            stats[
                "under25"
            ] += 1


        if ga == 0:

            stats[
                "clean_sheet"
            ] += 1


    games = stats[
        "games"
    ]


    if games:

        stats[
            "avg_gf"
        ] = stats["gf"] / games

        stats[
            "avg_ga"
        ] = stats["ga"] / games


    return stats


# ============================================================
# FORMA L10
# ============================================================

def make_form(
    history,
    team
):

    form = []

    for game in history:

        hs = game.get(
            "home_score"
        )

        aws = game.get(
            "away_score"
        )

        if hs is None or aws is None:
            continue

        hs = int(hs)
        aws = int(aws)


        if team_match(
            team,
            game.get(
                "home"
            )
        ):

            gf = hs
            ga = aws

            opponent = (
                game.get("away")
            )

            venue = "Casa"


        elif team_match(
            team,
            game.get(
                "away"
            )
        ):

            gf = aws
            ga = hs

            opponent = (
                game.get("home")
            )

            venue = "Fora"


        else:

            continue


        result = (

            "V"
            if gf > ga

            else

            (
                "E"
                if gf == ga
                else "D"
            )
        )


        form.append({

            "Data":
                format_datetime(
                    parse_kickoff(
                        game.get(
                            "kickoff"
                        )
                    )
                ),

            "Adversário":
                opponent,

            "Local":
                venue,

            "Placar":
                f"{gf}-{ga}",

            "GF":
                gf,

            "GA":
                ga,

            "Resultado":
                result,

            "Liga":
                game.get(
                    "league"
                )
                or "-",

            "Fonte":
                game.get(
                    "source"
                )
                or "-",
        })


    return form[:10]


# ============================================================
# H2H
# ============================================================

def h2h_stats(
    history,
    home,
    away
):

    games = []

    for game in history:

        gh = game.get(
            "home"
        )

        ga = game.get(
            "away"
        )


        if (

            (
                team_match(
                    gh,
                    home
                )

                and

                team_match(
                    ga,
                    away
                )
            )

            or

            (
                team_match(
                    gh,
                    away
                )

                and

                team_match(
                    ga,
                    home
                )
            )
        ):

            if (

                game.get(
                    "home_score"
                ) is not None

                and

                game.get(
                    "away_score"
                ) is not None
            ):

                games.append(
                    game
                )


    games.sort(

        key=lambda x:
        parse_kickoff(
            x.get("kickoff")
        )
        or datetime.min.replace(
            tzinfo=timezone.utc
        ),

        reverse=True
    )


    return games[:10]


# ============================================================
# PREDIÇÃO
# ============================================================

def build_prediction(
    home_history,
    away_history,
    home,
    away
):

    home_stats = history_stats(
        home_history,
        home
    )

    away_stats = history_stats(
        away_history,
        away
    )


    home_attack = (

        home_stats["avg_gf"]

        if home_stats["games"] > 0

        else 1.35
    )


    home_defense = (

        home_stats["avg_ga"]

        if home_stats["games"] > 0

        else 1.20
    )


    away_attack = (

        away_stats["avg_gf"]

        if away_stats["games"] > 0

        else 1.20
    )


    away_defense = (

        away_stats["avg_ga"]

        if away_stats["games"] > 0

        else 1.35
    )


    home_lambda = (

        home_attack * 0.65
        +
        away_defense * 0.35

    ) * 1.08


    away_lambda = (

        away_attack * 0.65
        +
        home_defense * 0.35
    )


    home_lambda = max(
        0.15,
        min(
            home_lambda,
            4.5
        )
    )


    away_lambda = max(
        0.15,
        min(
            away_lambda,
            4.5
        )
    )


    probs = model_probs(

        home_lambda,
        away_lambda
    )


    probs[
        "home_lambda"
    ] = home_lambda

    probs[
        "away_lambda"
    ] = away_lambda


    return probs


# ============================================================
# MERCADOS
# ============================================================

def market_table(
    probs
):

    markets = [

        (
            "Casa",
            probs["home_win"]
        ),

        (
            "Empate",
            probs["draw"]
        ),

        (
            "Fora",
            probs["away_win"]
        ),

        (
            "1X",
            probs["1x"]
        ),

        (
            "X2",
            probs["x2"]
        ),

        (
            "BTTS Sim",
            probs["btts_yes"]
        ),

        (
            "BTTS Não",
            probs["btts_no"]
        ),

        (
            "Over 0.5",
            probs["over05"]
        ),

        (
            "Over 1.5",
            probs["over15"]
        ),

        (
            "Over 2.5",
            probs["over25"]
        ),

        (
            "Over 3.5",
            probs["over35"]
        ),

        (
            "Under 1.5",
            probs["under15"]
        ),

        (
            "Under 2.5",
            probs["under25"]
        ),

        (
            "Under 3.5",
            probs["under35"]
        ),
    ]


    return pd.DataFrame([

        {

            "Mercado":
                name,

            "Probabilidade":
                f"{pct(probability):.1f}%",

            "Odd justa":
                fair_odd(
                    probability
                ),
        }

        for name, probability
        in markets

    ])


def suggestions(
    probs
):

    candidates = [

        (
            "1X",
            probs["1x"]
        ),

        (
            "X2",
            probs["x2"]
        ),

        (
            "BTTS Sim",
            probs["btts_yes"]
        ),

        (
            "BTTS Não",
            probs["btts_no"]
        ),

        (
            "Over 1.5",
            probs["over15"]
        ),

        (
            "Over 2.5",
            probs["over25"]
        ),

        (
            "Under 3.5",
            probs["under35"]
        ),
    ]


    candidates.sort(
        key=lambda x: x[1],
        reverse=True
    )


    return candidates


# ============================================================
# PLACARES EXATOS
# ============================================================

def exact_score_probs(
    home_lambda,
    away_lambda
):

    rows = []

    for hg in range(0, 6):

        for ag in range(0, 6):

            p = (

                poisson_pmf(
                    hg,
                    home_lambda
                )

                *

                poisson_pmf(
                    ag,
                    away_lambda
                )
            )

            rows.append({

                "Placar":
                    f"{hg}-{ag}",

                "Probabilidade":
                    p,
            })


    rows.sort(

        key=lambda x:
        x["Probabilidade"],

        reverse=True
    )


    return rows[:10]


# ============================================================
# OPENROUTER
# ============================================================

def pesquisar_partida_openrouter(
    partida,
    contexto_scanner=""
):

    if not OPENROUTER_API_KEY:

        return {

            "ok": False,

            "texto":
                "OPENROUTER_API_KEY não configurada."
        }


    agora = (
        datetime
        .now(BRT)
        .strftime(
            "%d/%m/%Y %H:%M"
        )
    )


    prompt = f"""
Você é um analista estatístico de futebol.

Analise a partida abaixo usando EXCLUSIVAMENTE
os dados fornecidos pelo scanner.

PARTIDA:
{partida}

DATA/HORA:
{agora}

DADOS DO SCANNER:
{contexto_scanner}

Faça uma análise objetiva.

Mostre:

1. Forma recente do mandante.
2. Forma recente do visitante.
3. Média de gols marcados.
4. Média de gols sofridos.
5. BTTS.
6. Over 1.5.
7. Over 2.5.
8. Over 3.5.
9. Under 2.5.
10. Under 3.5.
11. Desempenho casa/fora quando houver.
12. H2H quando houver.
13. Probabilidade calculada pelo scanner para 1X.
14. Probabilidade calculada pelo scanner para X2.
15. Probabilidade calculada pelo scanner para BTTS.
16. Probabilidade calculada pelo scanner para Over 2.5.
17. Principais placares exatos calculados.

Depois faça:

- "Pontos estatísticos favoráveis"
- "Pontos estatísticos de atenção"
- "Resumo"

NÃO invente informações.

Se algum dado não estiver disponível,
escreva "Não encontrado".

Não trate probabilidade estatística como garantia
de resultado.
"""


    headers = {

        "Authorization":
            f"Bearer {OPENROUTER_API_KEY}",

        "Content-Type":
            "application/json",

        "HTTP-Referer":
            "https://scanner-football-2.streamlit.app",

        "X-Title":
            "Global Football Scanner",
    }


    payload = {

        "model":
            OPENROUTER_MODEL,

        "messages": [

            {

                "role":
                    "system",

                "content":
                    "Você é um analista estatístico de futebol."
            },

            {

                "role":
                    "user",

                "content":
                    prompt
            }
        ],

        "temperature":
            0.2,

        "max_tokens":
            3000,
    }


    try:

        response = requests.post(

            f"{OPENROUTER_BASE}/chat/completions",

            headers=headers,

            json=payload,

            timeout=60
        )


        if response.status_code >= 400:

            try:

                erro = response.json()

            except Exception:

                erro = response.text


            return {

                "ok": False,

                "texto":
                    f"Erro OpenRouter "
                    f"{response.status_code}: "
                    f"{erro}"
            }


        data = response.json()


        choices = (
            data.get("choices")
            or []
        )


        if not choices:

            return {

                "ok": False,

                "texto":
                    "OpenRouter não retornou resposta."
            }


        message = (
            choices[0]
            .get("message")
            or {}
        )


        texto = (
            message.get("content")
            or ""
        )


        return {

            "ok": True,

            "texto":
                texto
        }


    except Exception as exc:

        return {

            "ok": False,

            "texto":
                f"Erro ao consultar "
                f"OpenRouter: {exc}"
        }


# ============================================================
# HISTÓRICO POR API
# ============================================================

def render_history_source_stats(
    team,
    by_source
):

    st.markdown(
        f"### 🗂️ Histórico por API — {team}"
    )


    rows = []


    for source, games in (
        by_source.items()
    ):

        stats = history_stats(
            games,
            team
        )


        rows.append({

            "API":
                source,

            "Jogos":
                stats["games"],

            "Vitórias":
                stats["wins"],

            "Empates":
                stats["draws"],

            "Derrotas":
                stats["losses"],

            "GF":
                stats["gf"],

            "GA":
                stats["ga"],

            "Média GF":
                round(
                    stats["avg_gf"],
                    2
                ),

            "Média GA":
                round(
                    stats["avg_ga"],
                    2
                ),

            "BTTS":

                (
                    f"{stats['btts_yes'] / stats['games'] * 100:.1f}%"
                    if stats["games"]
                    else "-"
                ),

            "Over 2.5":

                (
                    f"{stats['over25'] / stats['games'] * 100:.1f}%"
                    if stats["games"]
                    else "-"
                ),
        })


    st.dataframe(

        pd.DataFrame(
            rows
        ),

        use_container_width=True,

        hide_index=True
    )


# ============================================================
# L10
# ============================================================

def render_l10_table(
    team,
    history
):

    form = make_form(
        history,
        team
    )


    if not form:

        st.info(
            f"Não foi possível encontrar L10 para {team}."
        )

        return


    st.dataframe(

        pd.DataFrame(
            form
        ),

        use_container_width=True,

        hide_index=True
    )


# ============================================================
# CARD DA PARTIDA
# ============================================================

def render_match_card(
    event,
    all_events
):

    home = (
        event.get("home")
        or "Casa"
    )

    away = (
        event.get("away")
        or "Fora"
    )


    status = classify_event(
        event
    )


    kickoff = parse_kickoff(
        event.get("kickoff")
    )


    home_score = event.get(
        "home_score"
    )

    away_score = event.get(
        "away_score"
    )


    with st.spinner(
        f"Buscando histórico de "
        f"{home} e {away} nas 4 APIs..."
    ):

        home_history, home_by_source = (
            build_unified_history(
                home,
                current_event=event
            )
        )

        away_history, away_by_source = (
            build_unified_history(
                away,
                current_event=event
            )
        )


    prediction = build_prediction(

        home_history,

        away_history,

        home,

        away
    )


    status_label = {

        "live":
            "🔴 AO VIVO",

        "upcoming":
            "🟢 PRÓXIMO",

        "finished":
            "⚫ FINALIZADO",

        "unknown":
            "⚪",
    }.get(
        status,
        "⚪"
    )


    if (

        home_score is not None

        and

        away_score is not None
    ):

        score = (
            f"{home_score} x {away_score}"
        )

    else:

        score = "x"


    st.markdown("---")


    col1, col2, col3 = st.columns(
        [4, 2, 4]
    )


    with col1:

        st.subheader(
            home
        )


    with col2:

        st.markdown(

            f"<h2 style='text-align:center'>{score}</h2>",

            unsafe_allow_html=True
        )


    with col3:

        st.subheader(
            away
        )


    st.caption(

        f"{status_label} | "
        f"{format_datetime(kickoff)} | "
        f"{event.get('league') or 'Liga não informada'} | "
        f"Fonte principal: "
        f"{event.get('source') or '-'}"
    )


    # --------------------------------------------------------
    # MÉTRICAS
    # --------------------------------------------------------

    c1, c2, c3, c4, c5 = st.columns(
        5
    )


    with c1:

        st.metric(

            "1X",

            f"{pct(prediction['1x']):.1f}%"
        )


    with c2:

        st.metric(

            "X2",

            f"{pct(prediction['x2']):.1f}%"
        )


    with c3:

        st.metric(

            "BTTS",

            f"{pct(prediction['btts_yes']):.1f}%"
        )


    with c4:

        st.metric(

            "Over 2.5",

            f"{pct(prediction['over25']):.1f}%"
        )


    with c5:

        st.metric(

            "Under 3.5",

            f"{pct(prediction['under35']):.1f}%"
        )


    st.write(

        f"⚽ Gols esperados: "
        f"**{prediction['home_lambda']:.2f} "
        f"x "
        f"{prediction['away_lambda']:.2f}**"
    )


    # --------------------------------------------------------
    # HISTÓRICO
    # --------------------------------------------------------

    with st.expander(

        f"📚 Histórico unificado — "
        f"{home} x {away}",

        expanded=True
    ):

        st.markdown(

            "O histórico abaixo combina "
            "as 4 APIs e remove partidas duplicadas."
        )


        h1, h2 = st.columns(2)


        with h1:

            st.markdown(
                f"### 🏠 {home} — L10"
            )

            render_l10_table(
                home,
                home_history
            )


        with h2:

            st.markdown(
                f"### ✈️ {away} — L10"
            )

            render_l10_table(
                away,
                away_history
            )


        # ----------------------------------------------------
        # COMPARAÇÃO
        # ----------------------------------------------------

        st.markdown(
            "### 📊 Comparação do histórico"
        )


        hs = history_stats(
            home_history,
            home
        )

        aws = history_stats(
            away_history,
            away
        )


        comparison = pd.DataFrame([

            {

                "Indicador":
                    "Jogos",

                home:
                    hs["games"],

                away:
                    aws["games"],
            },

            {

                "Indicador":
                    "Vitórias",

                home:
                    hs["wins"],

                away:
                    aws["wins"],
            },

            {

                "Indicador":
                    "Empates",

                home:
                    hs["draws"],

                away:
                    aws["draws"],
            },

            {

                "Indicador":
                    "Derrotas",

                home:
                    hs["losses"],

                away:
                    aws["losses"],
            },

            {

                "Indicador":
                    "GF",

                home:
                    hs["gf"],

                away:
                    aws["gf"],
            },

            {

                "Indicador":
                    "GA",

                home:
                    hs["ga"],

                away:
                    aws["ga"],
            },

            {

                "Indicador":
                    "Média GF",

                home:
                    round(
                        hs["avg_gf"],
                        2
                    ),

                away:
                    round(
                        aws["avg_gf"],
                        2
                    ),
            },

            {

                "Indicador":
                    "Média GA",

                home:
                    round(
                        hs["avg_ga"],
                        2
                    ),

                away:
                    round(
                        aws["avg_ga"],
                        2
                    ),
            },

            {

                "Indicador":
                    "BTTS",

                home:

                    (
                        f"{hs['btts_yes'] / hs['games'] * 100:.1f}%"
                        if hs["games"]
                        else "-"
                    ),

                away:

                    (
                        f"{aws['btts_yes'] / aws['games'] * 100:.1f}%"
                        if aws["games"]
                        else "-"
                    ),
            },

            {

                "Indicador":
                    "Over 2.5",

                home:

                    (
                        f"{hs['over25'] / hs['games'] * 100:.1f}%"
                        if hs["games"]
                        else "-"
                    ),

                away:

                    (
                        f"{aws['over25'] / aws['games'] * 100:.1f}%"
                        if aws["games"]
                        else "-"
                    ),
            },
        ])


        st.dataframe(

            comparison,

            use_container_width=True,

            hide_index=True
        )


        # ----------------------------------------------------
        # ESTATÍSTICAS POR API
        # ----------------------------------------------------

        render_history_source_stats(
            home,
            home_by_source
        )


        render_history_source_stats(
            away,
            away_by_source
        )


    # --------------------------------------------------------
    # MERCADOS
    # --------------------------------------------------------

    with st.expander(
        "📊 Mercados calculados",
        expanded=True
    ):

        st.dataframe(

            market_table(
                prediction
            ),

            use_container_width=True,

            hide_index=True
        )


        st.markdown(
            "### 🔎 Maiores probabilidades do modelo"
        )


        best = suggestions(
            prediction
        )


        best_df = pd.DataFrame([

            {

                "Mercado":
                    market,

                "Probabilidade":
                    f"{pct(prob):.1f}%",

                "Odd justa":
                    fair_odd(prob),
            }

            for market, prob
            in best
        ])


        st.dataframe(

            best_df,

            use_container_width=True,

            hide_index=True
        )


    # --------------------------------------------------------
    # PLACARES EXATOS
    # --------------------------------------------------------

    with st.expander(
        "🎯 Placares exatos mais prováveis"
    ):

        exact = exact_score_probs(

            prediction[
                "home_lambda"
            ],

            prediction[
                "away_lambda"
            ]
        )


        exact_df = pd.DataFrame([

            {

                "Placar":
                    item["Placar"],

                "Probabilidade":
                    f"{pct(item['Probabilidade']):.2f}%"
            }

            for item in exact
        ])


        st.dataframe(

            exact_df,

            use_container_width=True,

            hide_index=True
        )


    # --------------------------------------------------------
    # H2H
    # --------------------------------------------------------

    with st.expander(
        "🤝 Confrontos diretos"
    ):

        h2h = h2h_stats(

            home_history
            +
            away_history,

            home,

            away
        )


        if h2h:

            rows = []


            for game in h2h:

                rows.append({

                    "Data":
                        format_datetime(
                            parse_kickoff(
                                game.get(
                                    "kickoff"
                                )
                            )
                        ),

                    "Casa":
                        game.get(
                            "home"
                        ),

                    "Placar":
                        f"{game.get('home_score')}-"
                        f"{game.get('away_score')}",

                    "Fora":
                        game.get(
                            "away"
                        ),

                    "Fonte":
                        game.get(
                            "source"
                        ),
                })


            st.dataframe(

                pd.DataFrame(
                    rows
                ),

                use_container_width=True,

                hide_index=True
            )


        else:

            st.info(
                "Nenhum H2H encontrado "
                "no histórico unificado disponível."
            )


    # ========================================================
    # OPENROUTER
    # ========================================================

    if st.button(

        "🤖 Analisar partida com IA gratuita",

        key=f"ia_{event_key(event)}",

        use_container_width=True
    ):

        home_stats = history_stats(
            home_history,
            home
        )

        away_stats = history_stats(
            away_history,
            away
        )


        # ----------------------------------------------------
        # L10 TEXTUAL
        # ----------------------------------------------------

        home_form = make_form(
            home_history,
            home
        )

        away_form = make_form(
            away_history,
            away
        )


        home_form_text = "\n".join([

            (
                f"{x['Data']} | "
                f"{x['Adversário']} | "
                f"{x['Local']} | "
                f"{x['Placar']} | "
                f"{x['Resultado']}"
            )

            for x in home_form
        ])


        away_form_text = "\n".join([

            (
                f"{x['Data']} | "
                f"{x['Adversário']} | "
                f"{x['Local']} | "
                f"{x['Placar']} | "
                f"{x['Resultado']}"
            )

            for x in away_form
        ])


        # ----------------------------------------------------
        # PLACARES
        # ----------------------------------------------------

        exact = exact_score_probs(

            prediction[
                "home_lambda"
            ],

            prediction[
                "away_lambda"
            ]
        )


        exact_text = "\n".join([

            (
                f"{x['Placar']}: "
                f"{pct(x['Probabilidade']):.2f}%"
            )

            for x in exact
        ])


        contexto = f"""

MANDANTE:
{home}

L10:
{home_form_text}

ESTATÍSTICAS:
Jogos: {home_stats['games']}
Vitórias: {home_stats['wins']}
Empates: {home_stats['draws']}
Derrotas: {home_stats['losses']}
GF: {home_stats['gf']}
GA: {home_stats['ga']}
Média GF: {home_stats['avg_gf']:.2f}
Média GA: {home_stats['avg_ga']:.2f}
BTTS: {
    home_stats['btts_yes'] /
    home_stats['games'] * 100
    if home_stats['games']
    else 0
:.1f}%
Over 2.5: {
    home_stats['over25'] /
    home_stats['games'] * 100
    if home_stats['games']
    else 0
:.1f}%


VISITANTE:
{away}

L10:
{away_form_text}

ESTATÍSTICAS:
Jogos: {away_stats['games']}
Vitórias: {away_stats['wins']}
Empates: {away_stats['draws']}
Derrotas: {away_stats['losses']}
GF: {away_stats['gf']}
GA: {away_stats['ga']}
Média GF: {away_stats['avg_gf']:.2f}
Média GA: {away_stats['avg_ga']:.2f}
BTTS: {
    away_stats['btts_yes'] /
    away_stats['games'] * 100
    if away_stats['games']
    else 0
:.1f}%
Over 2.5: {
    away_stats['over25'] /
    away_stats['games'] * 100
    if away_stats['games']
    else 0
:.1f}%


MODELO DO SCANNER:

1X:
{pct(prediction['1x']):.1f}%

X2:
{pct(prediction['x2']):.1f}%

BTTS:
{pct(prediction['btts_yes']):.1f}%

Over 1.5:
{pct(prediction['over15']):.1f}%

Over 2.5:
{pct(prediction['over25']):.1f}%

Over 3.5:
{pct(prediction['over35']):.1f}%

Under 2.5:
{pct(prediction['under25']):.1f}%

Under 3.5:
{pct(prediction['under35']):.1f}%

GOLS ESPERADOS:
{prediction['home_lambda']:.2f}
x
{prediction['away_lambda']:.2f}


PLACARES MAIS PROVÁVEIS:

{exact_text}
"""


        with st.spinner(
            "OpenRouter analisando os dados..."
        ):

            result = (
                pesquisar_partida_openrouter(
                    f"{home} x {away}",
                    contexto
                )
            )


        if result["ok"]:

            st.markdown(
                "### 🤖 Análise da IA"
            )

            st.markdown(
                result["texto"]
            )

        else:

            st.error(
                result["texto"]
            )


# ============================================================
# PROCURAR PARTIDA
# ============================================================

def procurar_partida_local(
    consulta,
    eventos
):

    if not consulta:
        return None

    q = normalize_name(
        consulta
    )


    q_clean = re.sub(

        r"\b(vs|versus|x)\b",

        " ",

        q
    )


    terms = [

        t

        for t in q_clean.split()

        if len(t) >= 3
    ]


    if not terms:
        return None


    candidates = []


    for event in eventos:

        text = normalize_name(

            f"{event.get('home')} "
            f"{event.get('away')}"
        )


        score = sum(

            1

            for term in terms

            if term in text
        )


        if score:

            candidates.append(
                (
                    score,
                    event
                )
            )


    if not candidates:
        return None


    candidates.sort(

        key=lambda x: x[0],

        reverse=True
    )


    return candidates[0][1]


# ============================================================
# STATUS DAS APIs
# ============================================================

def render_api_status():

    st.markdown(
        "### 🔌 APIs"
    )


    status = [

        {

            "API":
                "TheSportsDB",

            "Configurada":
                "✅",

            "Histórico":
                "Sim",
        },

        {

            "API":
                "football-data.org",

            "Configurada":
                "✅"
                if FD_TOKEN
                else "❌",

            "Histórico":
                "Sim"
                if FD_TOKEN
                else "Sem token",
        },

        {

            "API":
                "OpenFootAPI",

            "Configurada":
                "✅"
                if OPENFOOT_TOKEN
                else "❌",

            "Histórico":
                "Sim"
                if OPENFOOT_TOKEN
                else "Sem token",
        },

        {

            "API":
                "5DollarFootballAPI",

            "Configurada":
                "✅"
                if FD5_TOKEN
                else "❌",

            "Histórico":
                "Sim"
                if FD5_TOKEN
                else "Sem token",
        },

        {

            "API":
                "OpenRouter",

            "Configurada":
                "✅"
                if OPENROUTER_API_KEY
                else "❌",

            "Modelo":
                OPENROUTER_MODEL,
        },
    ]


    st.dataframe(

        pd.DataFrame(
            status
        ),

        use_container_width=True,

        hide_index=True
    )


# ============================================================
# MAIN
# ============================================================

def main():

    st.title(
        "⚽ Global Football Scanner"
    )


    st.caption(

        "Histórico unificado de 4 APIs "
        "+ L10 + probabilidades "
        "+ IA gratuita OpenRouter"
    )


    # --------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------

    st.sidebar.header(
        "⚙️ Configurações"
    )


    mostrar_todas = (
        st.sidebar.checkbox(
            "🌎 Mostrar todas as partidas",
            value=True
        )
    )


    mostrar_ao_vivo = (
        st.sidebar.checkbox(
            "🔴 Ao vivo",
            value=True
        )
    )


    mostrar_proximos = (
        st.sidebar.checkbox(
            "🟢 Próximos",
            value=True
        )
    )


    mostrar_finalizados = (
        st.sidebar.checkbox(
            "⚫ Finalizados",
            value=False
        )
    )


    limite = (
        st.sidebar.slider(
            "Quantidade",
            min_value=5,
            max_value=100,
            value=50
        )
    )


    st.sidebar.markdown(
        "---"
    )


    consulta_partida = (
        st.sidebar.text_input(

            "🔎 Procurar partida",

            placeholder=
            "Ex.: Flamengo x Palmeiras"
        )
    )


    pesquisar_ia = (
        st.sidebar.button(

            "🤖 Analisar com OpenRouter",

            use_container_width=True
        )
    )


    if st.sidebar.button(

        "🔄 Atualizar dados",

        use_container_width=True
    ):

        st.rerun()


    st.sidebar.markdown(
        "---"
    )


    st.sidebar.caption(
        "Histórico: 4 APIs"
    )

    st.sidebar.caption(
        "IA: OpenRouter Free"
    )


    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    with st.expander(
        "🔌 Status das conexões"
    ):

        render_api_status()


    # --------------------------------------------------------
    # BUSCAR PARTIDAS
    # --------------------------------------------------------

    with st.spinner(
        "Buscando partidas nas APIs..."
    ):

        eventos = load_global_events()


    # --------------------------------------------------------
    # PESQUISA IA DA PARTIDA
    # --------------------------------------------------------

    if pesquisar_ia and consulta_partida:

        local = procurar_partida_local(

            consulta_partida,

            eventos
        )


        contexto = ""


        if local:

            contexto = (

                f"Partida localizada pelo scanner:\n"

                f"{local.get('home')} x "
                f"{local.get('away')}\n"

                f"Data: "
                f"{format_datetime(parse_kickoff(local.get('kickoff')))}\n"

                f"Liga: "
                f"{local.get('league')}\n"

                f"Fonte: "
                f"{local.get('source')}"
            )


        with st.spinner(
            "OpenRouter analisando a partida..."
        ):

            result = (
                pesquisar_partida_openrouter(

                    consulta_partida,

                    contexto
                )
            )


        st.markdown("---")

        st.markdown(
            f"## 🤖 Análise: {consulta_partida}"
        )


        if result["ok"]:

            st.markdown(
                result["texto"]
            )

        else:

            st.error(
                result["texto"]
            )


    # --------------------------------------------------------
    # FILTROS
    # --------------------------------------------------------

    filtrados = []


    for event in eventos:

        tipo = classify_event(
            event
        )


        if mostrar_todas:

            filtrados.append(
                event
            )

            continue


        if (

            tipo == "live"

            and

            mostrar_ao_vivo
        ):

            filtrados.append(
                event
            )


        elif (

            tipo == "upcoming"

            and

            mostrar_proximos
        ):

            filtrados.append(
                event
            )


        elif (

            tipo == "finished"

            and

            mostrar_finalizados
        ):

            filtrados.append(
                event
            )


    filtrados = filtrados[
        :limite
    ]


    # --------------------------------------------------------
    # CONTADORES
    # --------------------------------------------------------

    live_count = sum(

        1

        for e in eventos

        if classify_event(e)
        == "live"
    )


    upcoming_count = sum(

        1

        for e in eventos

        if classify_event(e)
        == "upcoming"
    )


    finished_count = sum(

        1

        for e in eventos

        if classify_event(e)
        == "finished"
    )


    c1, c2, c3, c4 = st.columns(
        4
    )


    with c1:

        st.metric(
            "Partidas",
            len(eventos)
        )


    with c2:

        st.metric(
            "🔴 Ao vivo",
            live_count
        )


    with c3:

        st.metric(
            "🟢 Próximas",
            upcoming_count
        )


    with c4:

        st.metric(
            "⚫ Finalizadas",
            finished_count
        )


    # --------------------------------------------------------
    # RESUMO
    # --------------------------------------------------------

    if filtrados:

        summary = []


        for event in filtrados:

            status = classify_event(
                event
            )


            hs = event.get(
                "home_score"
            )

            aws = event.get(
                "away_score"
            )


            if (

                hs is not None

                and

                aws is not None
            ):

                placar = (
                    f"{hs}-{aws}"
                )

            else:

                placar = "-"


            summary.append({

                "Status":
                    status.upper(),

                "Partida":
                    f"{event.get('home')} "
                    f"x "
                    f"{event.get('away')}",

                "Placar":
                    placar,

                "Data":
                    format_datetime(
                        parse_kickoff(
                            event.get(
                                "kickoff"
                            )
                        )
                    ),

                "Liga":
                    event.get(
                        "league"
                    )
                    or "-",

                "Fonte":
                    event.get(
                        "source"
                    )
                    or "-",
            })


        st.dataframe(

            pd.DataFrame(
                summary
            ),

            use_container_width=True,

            hide_index=True
        )


    else:

        st.warning(
            "Nenhuma partida encontrada."
        )


    # --------------------------------------------------------
    # CARDS
    # --------------------------------------------------------

    for event in filtrados:

        try:

            render_match_card(

                event,

                eventos
            )

        except Exception as exc:

            st.error(

                f"Erro ao analisar "
                f"{event.get('home')} x "
                f"{event.get('away')}: "
                f"{exc}"
            )


            with st.expander(
                "Detalhes do erro"
            ):

                st.code(
                    traceback.format_exc()
                )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception:

        st.error(
            "O aplicativo encontrou um erro."
        )

        with st.expander(
            "🔧 Detalhes técnicos"
        ):

            st.code(
                traceback.format_exc()
            )
