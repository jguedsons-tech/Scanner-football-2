# ============================================================
# GLOBAL FOOTBALL SCANNER
# L10 OBRIGATÓRIO — ÚLTIMOS 10 JOGOS
# AO VIVO + PRÉ-JOGO
# ============================================================

import os
import math
import re

from datetime import datetime, timedelta, date, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# ============================================================
# CONFIGURAÇÃO
# ============================================================

st.set_page_config(
    page_title="Global Football Scanner — L10",
    page_icon="⚽",
    layout="wide"
)


# ============================================================
# APIS
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

FD5_BASE = (
    "https://api.5dollarfootballapi.com/v1"
)


OPENFOOT_TOKEN = os.getenv(
    "OPENFOOT_API_KEY",
    ""
)

OPENFOOT_BASE = (
    "https://openfootapi.com/v1"
)


# ============================================================
# PARÂMETROS
# ============================================================

TIMEOUT = 15

CACHE_TTL = 1800

CALENDAR_TTL = 20

BRT = ZoneInfo(
    "America/Sao_Paulo"
)

# OBRIGATORIAMENTE 10
L10_N = 10


# ============================================================
# STATUS
# ============================================================

LIVE_STATUSES = {
    "live",
    "in_play",
    "inplay",
    "1h",
    "2h",
    "ht",
    "et",
    "extra_time",
    "penalties",
    "pen"
}


FINAL_STATUSES = {
    "finished",
    "ft",
    "aet",
    "full_time",
    "cancelled",
    "canceled",
    "postponed",
    "abandoned",
    "suspended"
}


PRE_STATUSES = {
    "scheduled",
    "not_started",
    "ns",
    "timed",
    "upcoming",
    "fixture",
    ""
}


# ============================================================
# FUNÇÕES BÁSICAS
# ============================================================

def safe_float(
    v,
    default=None
):

    try:

        if v is None or v == "":
            return default

        return float(v)

    except Exception:

        return default


def pct(x):

    return f"{100 * x:.1f}%"


def norm_status(s: Any) -> str:

    if s is None:
        return ""

    s = str(s).strip().lower()

    s = (
        s
        .replace("-", "_")
        .replace(" ", "_")
    )

    s = (
        s
        .replace("º", "")
        .replace("°", "")
    )

    if ":" in s:
        s = s.split(":")[0]

    return s


def is_live_status(
    status: Any
) -> bool:

    s = norm_status(status)

    if not s or s in FINAL_STATUSES:
        return False

    if s in LIVE_STATUSES:
        return True

    compact = re.sub(
        r"[^a-z0-9]",
        "",
        s
    )

    if compact in {
        "live",
        "inplay",
        "playing",
        "1h",
        "2h",
        "ht",
        "halftime",
        "firsthalf",
        "secondhalf",
        "extratime",
        "et",
        "penalties",
        "penalty",
        "pen"
    }:
        return True

    if any(
        x in compact
        for x in (
            "secondhalf",
            "firsthalf",
            "inplay",
            "extratime"
        )
    ):
        return True

    if compact.startswith(
        (
            "1h",
            "2h",
            "1st",
            "2nd"
        )
    ):
        return True

    return False


# ============================================================
# DATA / HORÁRIO
# ============================================================

def parse_kickoff(
    e: Dict[str, Any]
) -> Optional[datetime]:

    raw = e.get("kickoff")

    if isinstance(raw, datetime):

        return raw.astimezone(BRT)

    if raw:

        try:

            dt = datetime.fromisoformat(
                str(raw).replace(
                    "Z",
                    "+00:00"
                )
            )

            if dt.tzinfo is None:

                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(BRT)

        except Exception:
            pass

    d = e.get("date")
    t = e.get("time")

    if d and t:

        try:

            return (
                datetime
                .fromisoformat(
                    f"{d}T{t[:8]}"
                )
                .replace(
                    tzinfo=timezone.utc
                )
                .astimezone(BRT)
            )

        except Exception:
            pass

    return None


def classify_event(
    e: Dict[str, Any]
) -> str:

    s = norm_status(
        e.get("status")
    )

    compact = re.sub(
        r"[^a-z0-9]",
        "",
        s
    )

    if (
        s in FINAL_STATUSES
        or any(
            x in compact
            for x in (
                "finished",
                "fulltime",
                "completed",
                "ended"
            )
        )
    ):

        return "FINALIZADO"

    if is_live_status(s):

        return "AO VIVO"

    has_score = (
        e.get("home_score") is not None
        or e.get("away_score") is not None
    )

    if (
        has_score
        and s not in PRE_STATUSES
        and s not in FINAL_STATUSES
    ):

        return "AO VIVO"

    ko = parse_kickoff(e)

    if ko:

        now = (
            datetime
            .now(timezone.utc)
            .astimezone(BRT)
        )

        if (
            now - timedelta(
                hours=3,
                minutes=30
            )
            <= ko
            <= now
            and (
                s not in PRE_STATUSES
                or has_score
            )
        ):

            return "AO VIVO"

    return "PRÓXIMO"


# ============================================================
# POISSON
# ============================================================

def poisson_pmf(
    k,
    lam
):

    if lam <= 0:

        return (
            1.0
            if k == 0
            else 0.0
        )

    return (
        math.exp(-lam)
        * lam**k
        / math.factorial(k)
    )


def model_probs(
    lh,
    la
):

    m = [
        [
            poisson_pmf(i, lh)
            * poisson_pmf(j, la)
            for j in range(11)
        ]
        for i in range(11)
    ]

    home = sum(
        m[i][j]
        for i in range(11)
        for j in range(11)
        if i > j
    )

    draw = sum(
        m[i][j]
        for i in range(11)
        for j in range(11)
        if i == j
    )

    away = sum(
        m[i][j]
        for i in range(11)
        for j in range(11)
        if i < j
    )

    btts = sum(
        m[i][j]
        for i in range(1, 11)
        for j in range(1, 11)
    )

    out = {
        "Casa": home,
        "Empate": draw,
        "Fora": away,
        "BTTS Sim": btts,
        "BTTS Não": 1 - btts
    }

    for line in (
        .5,
        1.5,
        2.5,
        3.5,
        4.5
    ):

        threshold = int(
            line - .5
        )

        under = sum(
            m[i][j]
            for i in range(11)
            for j in range(11)
            if i + j <= threshold
        )

        out[f"Over {line}"] = (
            1 - under
        )

        out[f"Under {line}"] = under

    return out


# ============================================================
# REQUEST
# ============================================================

def request_json(
    url,
    headers=None,
    params=None
):

    try:

        r = requests.get(
            url,
            headers=headers or {},
            params=params or {},
            timeout=TIMEOUT
        )

        if r.status_code == 200:

            return r.json()

        return None

    except Exception:

        return None


# ============================================================
# OPENFOOT
# ============================================================

def request_openfoot(
    params=None
):

    base_headers = {
        "Accept": "application/json"
    }

    if OPENFOOT_TOKEN:

        h = dict(base_headers)

        h["Authorization"] = (
            f"Bearer {OPENFOOT_TOKEN}"
        )

        data = request_json(
            f"{OPENFOOT_BASE}/matches",
            headers=h,
            params=params or {}
        )

        if data is not None:

            return data

    return request_json(
        f"{OPENFOOT_BASE}/matches",
        headers=base_headers,
        params=params or {}
    )


# ============================================================
# THESPORTSDB
# ============================================================

@st.cache_data(
    ttl=CALENDAR_TTL,
    show_spinner=False
)
def tsdb_day(day):

    return (
        request_json(
            f"{TSDB_BASE}/eventsday.php",
            params={
                "d": day,
                "s": "Soccer"
            }
        )
        or {}
    ).get("events") or []


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False
)
def tsdb_team_search(name):

    return (
        request_json(
            f"{TSDB_BASE}/searchteams.php",
            params={"t": name}
        )
        or {}
    ).get("teams") or []


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False
)
def tsdb_last(team_id):

    return (
        request_json(
            f"{TSDB_BASE}/eventslast.php",
            params={"id": team_id}
        )
        or {}
    ).get("results") or []


def normalize_tsdb_event(e):

    return {

        "id": str(
            e.get("idEvent", "")
        ),

        "date": (
            e.get("dateEvent")
            or ""
        ),

        "time": (
            e.get("strTime")
            or ""
        ),

        "league": (
            e.get("strLeague")
            or ""
        ),

        "country": (
            e.get("strCountry")
            or ""
        ),

        "home": (
            e.get("strHomeTeam")
            or ""
        ),

        "away": (
            e.get("strAwayTeam")
            or ""
        ),

        "home_id": str(
            e.get("idHomeTeam")
            or ""
        ),

        "away_id": str(
            e.get("idAwayTeam")
            or ""
        ),

        "home_score": safe_float(
            e.get("intHomeScore")
        ),

        "away_score": safe_float(
            e.get("intAwayScore")
        ),

        "status": (
            e.get("strStatus")
            or ""
        ),

        "source": "TheSportsDB",

        "kickoff": None
    }


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

    return (
        request_json(
            f"{FD_BASE}/competitions",
            headers={
                "X-Auth-Token":
                    FD_TOKEN
            }
        )
        or {}
    ).get("competitions") or []


@st.cache_data(
    ttl=CALENDAR_TTL,
    show_spinner=False
)
def fd_matches(
    comp,
    start,
    end
):

    if not FD_TOKEN:
        return []

    data = request_json(
        f"{FD_BASE}/competitions/{comp}/matches",
        headers={
            "X-Auth-Token":
                FD_TOKEN
        },
        params={
            "dateFrom": start,
            "dateTo": end
        }
    )

    return (
        data or {}
    ).get("matches") or []


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False
)
def fd_team_matches(
    team_id
):

    if not FD_TOKEN:
        return []

    end = date.today()

    start = (
        end
        - timedelta(days=365)
    )

    data = request_json(
        f"{FD_BASE}/teams/{team_id}/matches",
        headers={
            "X-Auth-Token":
                FD_TOKEN
        },
        params={
            "dateFrom":
                start.isoformat(),

            "dateTo":
                end.isoformat(),

            "status":
                "FINISHED"
        }
    )

    return (
        data or {}
    ).get("matches") or []


def normalize_fd_event(e):

    score = (
        e.get("score")
        or {}
    )

    full = (
        score.get("fullTime")
        or {}
    )

    comp = (
        e.get("competition")
        or {}
    )

    area = (
        comp.get("area")
        or {}
    )

    h = (
        e.get("homeTeam")
        or {}
    )

    a = (
        e.get("awayTeam")
        or {}
    )

    raw = (
        e.get("utcDate")
        or ""
    )

    ko = None

    try:

        ko = datetime.fromisoformat(
            raw.replace(
                "Z",
                "+00:00"
            )
        )

    except Exception:
        pass

    return {

        "id": str(
            e.get("id", "")
        ),

        "date": raw[:10],

        "time": raw[11:16],

        "league": (
            comp.get("name")
            or ""
        ),

        "country": (
            area.get("name")
            or ""
        ),

        "home": (
            h.get("name")
            or ""
        ),

        "away": (
            a.get("name")
            or ""
        ),

        "home_id": str(
            h.get("id")
            or ""
        ),

        "away_id": str(
            a.get("id")
            or ""
        ),

        "home_score": safe_float(
            full.get("home")
        ),

        "away_score": safe_float(
            full.get("away")
        ),

        "status": (
            e.get("status")
            or ""
        ),

        "source":
            "football-data.org",

        "kickoff":
            ko
    }


# ============================================================
# OPENFOOT
# ============================================================

@st.cache_data(
    ttl=CALENDAR_TTL,
    show_spinner=False
)
def openfoot_matches(day):

    data = request_openfoot(
        {"date": day}
    ) or {}

    rows = (
        data.get("data")
        or []
    )

    live_data = request_openfoot(
        {
            "date": day,
            "status": "live"
        }
    ) or {}

    live_rows = (
        live_data.get("data")
        or []
    )

    seen = {
        str(x.get("id"))
        for x in rows
        if x.get("id") is not None
    }

    for x in live_rows:

        if (
            str(x.get("id"))
            not in seen
        ):

            rows.append(x)

            seen.add(
                str(x.get("id"))
            )

    return rows


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False
)
def openfoot_team_search(
    name
):

    headers = {
        "Accept":
            "application/json"
    }

    if OPENFOOT_TOKEN:

        headers["Authorization"] = (
            f"Bearer {OPENFOOT_TOKEN}"
        )

    rows = (
        request_json(
            f"{OPENFOOT_BASE}/search",
            headers=headers,
            params={"q": name}
        )
        or {}
    ).get("data") or []

    return [
        r
        for r in rows
        if r.get("type")
        in ("team", "club")
    ] or rows


@st.cache_data(
    ttl=CACHE_TTL,
    show_spinner=False
)
def openfoot_team_matches(
    team_id
):

    headers = {
        "Accept":
            "application/json"
    }

    if OPENFOOT_TOKEN:

        headers["Authorization"] = (
            f"Bearer {OPENFOOT_TOKEN}"
        )

    return (
        request_json(
            f"{OPENFOOT_BASE}/matches",
            headers=headers,
            params={
                "team": team_id,
                "status": "finished"
            }
        )
        or {}
    ).get("data") or []


def normalize_openfoot_event(e):

    h = (
        e.get("homeTeam")
        or {}
    )

    a = (
        e.get("awayTeam")
        or {}
    )

    score = (
        e.get("score")
        or {}
    )

    full = (
        score.get("fullTime")
        or score.get("fulltime")
        or score
    )

    raw = (
        e.get("kickoffAt")
        or e.get("date")
        or ""
    )

    ko = None

    try:

        ko = datetime.fromisoformat(
            str(raw).replace(
                "Z",
                "+00:00"
            )
        )

    except Exception:
        pass

    comp = e.get(
        "competition"
    )

    league = (
        comp.get("name")
        if isinstance(
            comp,
            dict
        )
        else (
            e.get("competitionName")
            or ""
        )
    )

    return {

        "id": str(
            e.get("id", "")
        ),

        "date": str(raw)[:10],

        "time": str(raw)[11:16],

        "league": league or "",

        "country": "",

        "home": (
            h.get("name")
            or e.get("homeTeamName")
            or ""
        ),

        "away": (
            a.get("name")
            or e.get("awayTeamName")
            or ""
        ),

        "home_id": str(
            h.get("id")
            or ""
        ),

        "away_id": str(
            a.get("id")
            or ""
        ),

        "home_score": safe_float(
            full.get("home")
        ),

        "away_score": safe_float(
            full.get("away")
        ),

        "status": (
            e.get("status")
            or ""
        ),

        "source":
            "OpenFootAPI",

        "kickoff":
            ko
    }


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

    d = date.fromisoformat(day)

    start = int(
        datetime(
            d.year,
            d.month,
            d.day,
            tzinfo=timezone.utc
        ).timestamp()
    )

    end = start + 86400

    headers = {
        "Authorization":
            f"Bearer {FD5_TOKEN}",

        "Accept":
            "application/json"
    }

    rows = []

    for page in (
        1,
        2,
        3,
        4,
        5
    ):

        data = request_json(
            f"{FD5_BASE}/fixtures",
            headers=headers,
            params={
                "start_time": start,
                "end_time": end,
                "per_page": 100,
                "page": page
            }
        ) or {}

        batch = (
            data.get("data")
            or []
        )

        rows.extend(batch)

        pag = (
            data.get("pagination")
            or {}
        )

        if (
            not pag.get("has_more")
            or not batch
        ):
            break

    live_data = request_json(
        f"{FD5_BASE}/fixtures",
        headers=headers,
        params={
            "status": "live",
            "per_page": 500
        }
    ) or {}

    rows.extend(
        live_data.get("data")
        or []
    )

    unique = {}

    for x in rows:

        unique[
            str(x.get("id"))
        ] = x

    return list(
        unique.values()
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
        f"{FD5_BASE}/teams/{team_id}/fixtures",
        headers={
            "Authorization":
                f"Bearer {FD5_TOKEN}"
        },
        params={
            "status":
                "finished",

            "per_page":
                100
        }
    ) or {}

    return (
        data.get("data")
        or []
    )


def normalize_fd5_event(e):

    teams = (
        e.get("teams")
        or {}
    )

    h = (
        teams.get("home")
        or {}
    )

    a = (
        teams.get("away")
        or {}
    )

    goals = (
        e.get("goals")
        or {}
    )

    corners = (
        e.get("corners")
        or {}
    )

    cards = (
        e.get("cards")
        or {}
    )

    raw = (
        e.get("kickoff_utc")
        or ""
    )

    ko = None

    try:

        ko = datetime.fromisoformat(
            raw.replace(
                "Z",
                "+00:00"
            )
        )

    except Exception:
        pass

    return {

        "id": str(
            e.get("id", "")
        ),

        "date": raw[:10],

        "time": raw[11:16],

        "league": (
            e.get("league")
            or {}
        ).get("name")
        or "",

        "country": "",

        "home": (
            h.get("name")
            or ""
        ),

        "away": (
            a.get("name")
            or ""
        ),

        "home_id": str(
            h.get("id")
            or ""
        ),

        "away_id": str(
            a.get("id")
            or ""
        ),

        "home_score": safe_float(
            goals.get("home")
        ),

        "away_score": safe_float(
            goals.get("away")
        ),

        "status": (
            e.get("status")
            or ""
        ),

        "period": (
            e.get("period")
            or e.get("phase")
            or ""
        ),

        "minute": safe_float(
            e.get("minute")
            or e.get("elapsed")
            or e.get("status_code")
        ),

        "source":
            "5DollarFootballAPI",

        "kickoff":
            ko,

        "home_corners":
            safe_float(
                corners.get("home")
            ),

        "away_corners":
            safe_float(
                corners.get("away")
            ),

        "home_yellow":
            safe_float(
                (
                    cards.get("home")
                    or {}
                ).get("yellow")
            ),

        "away_yellow":
            safe_float(
                (
                    cards.get("away")
                    or {}
                ).get("yellow")
            )
    }


# ============================================================
# CALENDÁRIO GLOBAL
# ============================================================

def load_global_events(
    target,
    days_ahead=1
):

    events = []

    for off in range(
        days_ahead + 1
    ):

        d = (
            target
            + timedelta(days=off)
        )

        ds = d.isoformat()

        events += [
            normalize_openfoot_event(x)
            for x in openfoot_matches(ds)
        ]

        events += [
            normalize_tsdb_event(x)
            for x in tsdb_day(ds)
        ]

        if FD5_TOKEN:

            events += [
                normalize_fd5_event(x)
                for x in fd5_day(ds)
            ]

    if FD_TOKEN:

        for c in fd_competitions():

            if c.get("code"):

                events += [
                    normalize_fd_event(x)
                    for x in fd_matches(
                        c["code"],
                        target.isoformat(),
                        (
                            target
                            + timedelta(
                                days=days_ahead
                            )
                        ).isoformat()
                    )
                ]

    # 5Dollar ganha prioridade
    # por possuir estatísticas mais completas
    unique = {}

    priority = {
        "5DollarFootballAPI": 5,
        "OpenFootAPI": 4,
        "football-data.org": 3,
        "TheSportsDB": 1
    }

    for e in events:

        if (
            not e["home"]
            or not e["away"]
        ):
            continue

        key = (
            e["date"],

            re.sub(
                r"\W",
                "",
                e["home"].lower()
            ),

            re.sub(
                r"\W",
                "",
                e["away"].lower()
            )
        )

        if (
            key not in unique
            or priority.get(
                e["source"],
                0
            )
            >
            priority.get(
                unique[key]["source"],
                0
            )
        ):

            unique[key] = e

    return list(
        unique.values()
    )


# ============================================================
# FORM
# ============================================================

def make_form(
    ne,
    team_id
):

    if (
        ne["home_score"] is None
        or ne["away_score"] is None
    ):
        return None

    is_home = (
        str(ne["home_id"])
        == str(team_id)
    )

    gf = (
        ne["home_score"]
        if is_home
        else ne["away_score"]
    )

    ga = (
        ne["away_score"]
        if is_home
        else ne["home_score"]
    )

    return {

        "date":
            ne["date"],

        "gf":
            gf,

        "ga":
            ga,

        "home":
            is_home,

        "result":
            (
                "W"
                if gf > ga
                else "D"
                if gf == ga
                else "L"
            ),

        "opponent":
            (
                ne["away"]
                if is_home
                else ne["home"]
            ),

        "opponent_id":
            (
                ne["away_id"]
                if is_home
                else ne["home_id"]
            ),

        "corners_for":
            (
                ne.get("home_corners")
                if is_home
                else ne.get("away_corners")
            ),

        "corners_against":
            (
                ne.get("away_corners")
                if is_home
                else ne.get("home_corners")
            ),

        "yellow_for":
            (
                ne.get("home_yellow")
                if is_home
                else ne.get("away_yellow")
            ),

        "yellow_against":
            (
                ne.get("away_yellow")
                if is_home
                else ne.get("home_yellow")
            )
    }


# ============================================================
# ORDENAÇÃO DO L10
# ============================================================

def ordenar_l10(rows):

    seen = set()

    unique = []

    for r in rows:

        key = (
            r.get("date"),
            r.get("opponent"),
            r.get("gf"),
            r.get("ga"),
            r.get("home")
        )

        if key not in seen:

            seen.add(key)

            unique.append(r)

    unique.sort(
        key=lambda x:
            x.get("date") or "",
        reverse=True
    )

    return unique[:L10_N]


# ============================================================
# BUSCA OBRIGATÓRIA DO L10
# ============================================================

def team_form(
    event,
    side,
    n=L10_N
):

    # IGNORA QUALQUER OUTRO VALOR
    n = L10_N

    tid = event.get(
        f"{side}_id"
    )

    source = event.get(
        "source"
    )

    rows = []

    label = ""

    # ========================================================
    # 5DOLLAR
    # ========================================================

    if (
        source
        == "5DollarFootballAPI"
        and tid
    ):

        for x in fd5_team_fixtures(tid):

            ne = normalize_fd5_event(x)

            r = make_form(
                ne,
                tid
            )

            if r:
                rows.append(r)

        label = (
            "5DollarFootballAPI"
        )

    # ========================================================
    # OPENFOOT
    # ========================================================

    elif (
        source
        == "OpenFootAPI"
        and tid
    ):

        for x in openfoot_team_matches(
            tid
        ):

            ne = normalize_openfoot_event(x)

            r = make_form(
                ne,
                tid
            )

            if r:
                rows.append(r)

        label = "OpenFootAPI"

    # ========================================================
    # FOOTBALL-DATA
    # ========================================================

    elif (
        source
        == "football-data.org"
        and tid
    ):

        try:

            tid_int = int(tid)

        except Exception:

            tid_int = tid

        for x in fd_team_matches(
            tid_int
        ):

            ne = normalize_fd_event(x)

            r = make_form(
                ne,
                tid
            )

            if r:
                rows.append(r)

        label = (
            "football-data.org"
        )

    # ========================================================
    # THESPORTSDB
    # ========================================================

    elif (
        source
        == "TheSportsDB"
        and tid
    ):

        for x in tsdb_last(tid):

            ne = normalize_tsdb_event(x)

            r = make_form(
                ne,
                tid
            )

            if r:
                rows.append(r)

        label = "TheSportsDB"

    # ========================================================
    # FALLBACK OPENFOOT
    # ========================================================

    if not rows:

        found = openfoot_team_search(
            event.get(side, "")
        )

        if found:

            oid = str(
                found[0].get("id")
                or found[0].get("teamId")
                or ""
            )

            for x in openfoot_team_matches(
                oid
            ):

                ne = normalize_openfoot_event(x)

                r = make_form(
                    ne,
                    oid
                )

                if r:
                    rows.append(r)

            label = "OpenFootAPI"

    # ========================================================
    # FALLBACK THESPORTSDB
    # ========================================================

    if not rows:

        found = tsdb_team_search(
            event.get(side, "")
        )

        if found:

            oid = str(
                found[0].get("idTeam")
                or ""
            )

            for x in tsdb_last(oid):

                ne = normalize_tsdb_event(x)

                r = make_form(
                    ne,
                    oid
                )

                if r:
                    rows.append(r)

            label = "TheSportsDB"

    # ========================================================
    # L10 FINAL
    # ========================================================

    rows = ordenar_l10(rows)

    return rows, label


# ============================================================
# ESTATÍSTICAS EXATAS DO L10
# ============================================================

def l10_stats(rows):

    rows = ordenar_l10(rows)

    jogos = len(rows)

    if jogos == 0:

        return {
            "jogos": 0,
            "vitorias": 0,
            "empates": 0,
            "derrotas": 0,
            "pontos": 0,
            "gf": 0,
            "ga": 0,
            "media_gf": 0,
            "media_ga": 0,
            "btts": 0,
            "over15": 0,
            "over25": 0,
            "over35": 0,
            "under25": 0,
            "clean_sheets": 0,
            "sem_marcar": 0,
            "corners_for": None,
            "corners_against": None,
            "corners_total": None,
            "yellow_for": None,
            "yellow_against": None
        }

    vitorias = sum(
        1
        for r in rows
        if r["result"] == "W"
    )

    empates = sum(
        1
        for r in rows
        if r["result"] == "D"
    )

    derrotas = sum(
        1
        for r in rows
        if r["result"] == "L"
    )

    gf = sum(
        float(r["gf"])
        for r in rows
    )

    ga = sum(
        float(r["ga"])
        for r in rows
    )

    pontos = (
        vitorias * 3
        + empates
    )

    btts = sum(
        1
        for r in rows
        if (
            r["gf"] > 0
            and r["ga"] > 0
        )
    )

    over15 = sum(
        1
        for r in rows
        if r["gf"] + r["ga"] >= 2
    )

    over25 = sum(
        1
        for r in rows
        if r["gf"] + r["ga"] >= 3
    )

    over35 = sum(
        1
        for r in rows
        if r["gf"] + r["ga"] >= 4
    )

    under25 = sum(
        1
        for r in rows
        if r["gf"] + r["ga"] <= 2
    )

    clean_sheets = sum(
        1
        for r in rows
        if r["ga"] == 0
    )

    sem_marcar = sum(
        1
        for r in rows
        if r["gf"] == 0
    )

    # ========================================================
    # ESCANTEIOS
    # ========================================================

    corners_for_values = [
        r["corners_for"]
        for r in rows
        if r.get("corners_for")
        is not None
    ]

    corners_against_values = [
        r["corners_against"]
        for r in rows
        if r.get("corners_against")
        is not None
    ]

    corners_for = (
        sum(corners_for_values)
        / len(corners_for_values)
        if corners_for_values
        else None
    )

    corners_against = (
        sum(corners_against_values)
        / len(corners_against_values)
        if corners_against_values
        else None
    )

    corners_total = (
        corners_for
        + corners_against
        if (
            corners_for is not None
            and corners_against is not None
        )
        else None
    )

    # ========================================================
    # CARTÕES
    # ========================================================

    yellow_for_values = [
        r["yellow_for"]
        for r in rows
        if r.get("yellow_for")
        is not None
    ]

    yellow_against_values = [
        r["yellow_against"]
        for r in rows
        if r.get("yellow_against")
        is not None
    ]

    yellow_for = (
        sum(yellow_for_values)
        / len(yellow_for_values)
        if yellow_for_values
        else None
    )

    yellow_against = (
        sum(yellow_against_values)
        / len(yellow_against_values)
        if yellow_against_values
        else None
    )

    return {

        "jogos":
            jogos,

        "vitorias":
            vitorias,

        "empates":
            empates,

        "derrotas":
            derrotas,

        "pontos":
            pontos,

        "gf":
            gf,

        "ga":
            ga,

        "media_gf":
            gf / jogos,

        "media_ga":
            ga / jogos,

        "btts":
            btts,

        "over15":
            over15,

        "over25":
            over25,

        "over35":
            over35,

        "under25":
            under25,

        "clean_sheets":
            clean_sheets,

        "sem_marcar":
            sem_marcar,

        "corners_for":
            corners_for,

        "corners_against":
            corners_against,

        "corners_total":
            corners_total,

        "yellow_for":
            yellow_for,

        "yellow_against":
            yellow_against
    }


# ============================================================
# H2H
# ============================================================

def h2h_stats(
    event,
    hf,
    af,
    limit=10
):

    home = event["home"]

    away = event["away"]

    def clean(x):

        return re.sub(
            r"[^a-z0-9]",
            "",
            x.lower()
        )

    a = clean(home)

    b = clean(away)

    candidates = []

    for r in hf + af:

        op = clean(
            str(
                r.get(
                    "opponent",
                    ""
                )
            )
        )

        if (
            op
            and (
                op == a
                or op == b
                or a in op
                or b in op
            )
        ):

            candidates.append(r)

    uniq = []

    seen = set()

    for r in sorted(
        candidates,
        key=lambda x:
            x["date"],
        reverse=True
    ):

        k = (
            r["date"],
            r["opponent"],
            r["gf"],
            r["ga"]
        )

        if k not in seen:

            seen.add(k)

            uniq.append(r)

    uniq = uniq[:limit]

    if len(uniq) < 3:

        return None

    wins = 0
    draws = 0
    losses = 0
    btts = 0
    over25 = 0

    goals = []

    for r in uniq:

        gf = r["gf"]
        ga = r["ga"]

        wins += gf > ga
        draws += gf == ga
        losses += gf < ga

        btts += (
            gf > 0
            and ga > 0
        )

        over25 += (
            gf + ga > 2
        )

        goals.append(
            gf + ga
        )

    return {

        "games":
            len(uniq),

        "win_rate":
            wins / len(uniq),

        "draw_rate":
            draws / len(uniq),

        "loss_rate":
            losses / len(uniq),

        "home_wins":
            wins,

        "draws":
            draws,

        "away_wins":
            losses,

        "btts":
            btts / len(uniq),

        "over25":
            over25 / len(uniq),

        "avg_goals":
            sum(goals)
            / len(goals)
    }


# ============================================================
# PREVISÃO BASEADA NO L10
# ============================================================

def build_prediction(
    event,
    n=L10_N
):

    # Sempre 10
    hf, hs = team_form(
        event,
        "home",
        L10_N
    )

    af, ass = team_form(
        event,
        "away",
        L10_N
    )

    # Estatísticas exatas
    h_l10 = l10_stats(hf)

    a_l10 = l10_stats(af)

    # ========================================================
    # MÉDIAS DO L10
    # ========================================================

    hgf = (
        h_l10["media_gf"]
        if h_l10["jogos"]
        else 1.20
    )

    hga = (
        h_l10["media_ga"]
        if h_l10["jogos"]
        else 1.20
    )

    agf = (
        a_l10["media_gf"]
        if a_l10["jogos"]
        else 1.10
    )

    aga = (
        a_l10["media_ga"]
        if a_l10["jogos"]
        else 1.25
    )

    # ========================================================
    # EXPECTATIVA DE GOLS
    # ========================================================

    lh = max(
        .10,
        min(
            4.5,
            .55 * hgf
            + .45 * aga
        )
    ) * 1.06

    la = max(
        .10,
        min(
            4.5,
            .55 * agf
            + .45 * hga
        )
    )

    # ========================================================
    # PONTOS NO L10
    # ========================================================

    pts_home = (
        h_l10["pontos"]
        / (
            h_l10["jogos"]
            * 3
        )
        if h_l10["jogos"]
        else .5
    )

    pts_away = (
        a_l10["pontos"]
        / (
            a_l10["jogos"]
            * 3
        )
        if a_l10["jogos"]
        else .5
    )

    lh *= (
        .95
        + .10 * pts_home
    )

    la *= (
        .95
        + .10 * pts_away
    )

    # ========================================================
    # PROBABILIDADES
    # ========================================================

    probs = model_probs(
        lh,
        la
    )

    # ========================================================
    # H2H
    # ========================================================

    h2h = h2h_stats(
        event,
        hf,
        af
    )

    if h2h:

        h2h_1x2 = {

            "Casa":
                h2h["win_rate"],

            "Empate":
                h2h["draw_rate"],

            "Fora":
                h2h["loss_rate"]
        }

        for k in (
            "Casa",
            "Empate",
            "Fora"
        ):

            probs[k] = (
                .80 * probs[k]
                + .20 * h2h_1x2[k]
            )

        total = sum(
            probs[k]
            for k in (
                "Casa",
                "Empate",
                "Fora"
            )
        )

        for k in (
            "Casa",
            "Empate",
            "Fora"
        ):

            probs[k] /= total

        probs["BTTS Sim"] = (
            .80 * probs["BTTS Sim"]
            + .20 * h2h["btts"]
        )

        probs["BTTS Não"] = (
            1 - probs["BTTS Sim"]
        )

        probs["Over 2.5"] = (
            .80 * probs["Over 2.5"]
            + .20 * h2h["over25"]
        )

        probs["Under 2.5"] = (
            1 - probs["Over 2.5"]
        )

    # ========================================================
    # CONFIANÇA
    # ========================================================

    sample = min(
        h_l10["jogos"],
        a_l10["jogos"]
    )

    conf = min(
        .96,
        max(
            .35,
            .35
            + .03 * sample
        )
    )

    if (
        hs
        == "5DollarFootballAPI"
        and
        ass
        == "5DollarFootballAPI"
    ):

        conf = min(
            .96,
            conf + .06
        )

    return {

        "probs":
            probs,

        "home_form":
            hf,

        "away_form":
            af,

        "home_l10":
            h_l10,

        "away_l10":
            a_l10,

        "home_form_source":
            hs,

        "away_form_source":
            ass,

        "confidence":
            conf,

        "h2h":
            h2h,

        "lambda_home":
            lh,

        "lambda_away":
            la,

        "corners_home_avg":
            h_l10[
                "corners_for"
            ],

        "corners_away_avg":
            a_l10[
                "corners_for"
            ],

        "corners_home_allowed":
            h_l10[
                "corners_against"
            ],

        "corners_away_allowed":
            a_l10[
                "corners_against"
            ],

        "yellow_home_avg":
            h_l10[
                "yellow_for"
            ],

        "yellow_away_avg":
            a_l10[
                "yellow_for"
            ]
    }


# ============================================================
# SUGESTÕES
# ============================================================

def suggestions(pred):

    p = pred["probs"]

    c = [

        (
            "Casa ou empate (1X)",
            p["Casa"] + p["Empate"]
        ),

        (
            "Empate ou fora (X2)",
            p["Empate"] + p["Fora"]
        ),

        (
            "Casa",
            p["Casa"]
        ),

        (
            "Empate",
            p["Empate"]
        ),

        (
            "Fora",
            p["Fora"]
        ),

        (
            "BTTS Sim",
            p["BTTS Sim"]
        ),

        (
            "BTTS Não",
            p["BTTS Não"]
        ),

        (
            "Over 1.5",
            p["Over 1.5"]
        ),

        (
            "Under 3.5",
            p["Under 3.5"]
        ),

        (
            "Over 2.5",
            p["Over 2.5"]
        ),

        (
            "Under 2.5",
            p["Under 2.5"]
        )
    ]

    return sorted(
        c,
        key=lambda x: x[1],
        reverse=True
    )[:5]


# ============================================================
# FILTRO DE EVENTOS
# ============================================================

def filter_events(events):

    now = (
        datetime
        .now(timezone.utc)
        .astimezone(BRT)
    )

    out = []

    for e in events:

        cat = classify_event(e)

        e["category"] = cat

        if cat == "FINALIZADO":
            continue

        ko = parse_kickoff(e)

        e["kickoff_brt"] = ko

        if (
            cat == "PRÓXIMO"
            and ko
            and ko <= now
        ):

            continue

        if (
            cat == "PRÓXIMO"
            and not ko
            and e.get("date")
            == date.today().isoformat()
        ):

            continue

        out.append(e)

    return sorted(
        out,
        key=lambda x: (
            0
            if x["category"]
            == "AO VIVO"
            else 1,

            x.get(
                "kickoff_brt"
            )
            or datetime.max.replace(
                tzinfo=BRT
            )
        )
    )


# ============================================================
# UI
# ============================================================

st.title(
    "⚽ Global Football Scanner — L10"
)

st.markdown(
    """
    <script>
    setTimeout(
        function(){
            window.parent.location.reload();
        },
        60000
    );
    </script>
    """,
    unsafe_allow_html=True
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header(
        "⚙️ Configuração"
    )

    target = st.date_input(
        "Data inicial",
        value=date.today()
    )

    days = st.slider(
        "Dias para varrer",
        0,
        3,
        1
    )

    # L10 FIXO
    st.info(
        "📊 L10 obrigatório: "
        "o scanner utiliza sempre "
        "os últimos 10 jogos "
        "finalizados de cada time."
    )

    show_all = st.checkbox(
        "Mostrar todos",
        value=True
    )

    st.divider()

    st.markdown(
        "**Fontes**"
    )

    st.write(
        "🌎 TheSportsDB: ativo"
    )

    st.write(
        "🏆 football-data.org:",
        "ativo"
        if FD_TOKEN
        else "opcional"
    )

    st.write(
        "📊 5DollarFootballAPI:",
        "ativo"
        if FD5_TOKEN
        else "opcional"
    )

    st.write(
        "🌐 OpenFootAPI:",
        (
            "chave configurada + "
            "fallback público"
            if OPENFOOT_TOKEN
            else
            "modo público"
        )
    )

    st.caption(
        "O L10 é ordenado do jogo "
        "mais recente para o mais antigo."
    )

    if not FD5_TOKEN:

        st.warning(
            "5DollarFootballAPI: "
            "configure "
            "FIVEDOLLAR_FOOTBALL_API_KEY "
            "nos Secrets para obter "
            "escanteios e cartões."
        )


# ============================================================
# BOTÃO ATUALIZAR
# ============================================================

if st.button(
    "🔄 Atualizar jogos",
    type="primary",
    use_container_width=True
):

    st.cache_data.clear()

    st.rerun()


# ============================================================
# ABAS
# ============================================================

tab_live, tab_upcoming, tab_best, tab_team = st.tabs(
    [
        "🟢 Jogos ao vivo",
        "🔵 Próximos jogos",
        "⭐ Melhores oportunidades",
        "🔎 Buscar por time"
    ]
)


# ============================================================
# BUSCAR TIME
# ============================================================

with tab_team:

    st.subheader(
        "🔎 Buscar jogos por time"
    )

    q = st.text_input(
        "Digite o nome do time",
        placeholder=(
            "Ex.: Flamengo, "
            "Real Madrid, Liverpool"
        )
    )

    if q:

        teams = []

        for x in openfoot_team_search(q)[:10]:

            teams.append({

                "nome":
                    x.get("name")
                    or x.get("teamName")
                    or "Time",

                "id":
                    str(
                        x.get("id")
                        or x.get("teamId")
                        or ""
                    ),

                "fonte":
                    "OpenFootAPI"
            })

        for x in tsdb_team_search(q)[:10]:

            teams.append({

                "nome":
                    x.get("strTeam")
                    or "Time",

                "id":
                    str(
                        x.get("idTeam")
                        or ""
                    ),

                "fonte":
                    "TheSportsDB"
            })

        seen = set()

        filtered = []

        for x in teams:

            key = (
                x["fonte"],
                x["id"]
            )

            if (
                x["id"]
                and key not in seen
            ):

                seen.add(key)

                filtered.append(x)

        teams = filtered

        if teams:

            choices = [
                f"{x['nome']} — {x['fonte']}"
                for x in teams
            ]

            choice = st.selectbox(
                "Selecione o time",
                choices
            )

            sel = teams[
                choices.index(choice)
            ]

            with st.spinner(
                "Buscando próximos jogos..."
            ):

                ev = filter_events(
                    load_global_events(
                        date.today(),
                        7
                    )
                )

            name = sel["nome"].lower()

            ev = [
                e
                for e in ev
                if (
                    name in
                    e["home"].lower()
                    or
                    name in
                    e["away"].lower()
                )
            ]

            if ev:

                st.dataframe(
                    pd.DataFrame([
                        {
                            "Status":
                                e["category"],

                            "Data":
                                e["date"],

                            "Horário BRT":
                                (
                                    e[
                                        "kickoff_brt"
                                    ].strftime(
                                        "%d/%m %H:%M"
                                    )
                                    if e.get(
                                        "kickoff_brt"
                                    )
                                    else "-"
                                ),

                            "Liga":
                                e["league"],

                            "Jogo":
                                (
                                    f"{e['home']} "
                                    f"x "
                                    f"{e['away']}"
                                )
                        }
                        for e in ev
                    ]),
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "Nenhum próximo "
                    "ou ao vivo encontrado "
                    "nos próximos 7 dias."
                )

        else:

            st.warning(
                "Time não localizado "
                "nas fontes disponíveis."
            )


# ============================================================
# CARREGAR EVENTOS
# ============================================================

with st.spinner(
    "Buscando calendário global..."
):

    events = filter_events(
        load_global_events(
            target,
            days
        )
    )


live = [
    e
    for e in events
    if e["category"]
    == "AO VIVO"
]

upcoming = [
    e
    for e in events
    if e["category"]
    == "PRÓXIMO"
]


# ============================================================
# DIAGNÓSTICO
# ============================================================

src_counts = {}

for e in events:

    src = e["source"]

    src_counts[src] = (
        src_counts.get(src, 0)
        + 1
    )


with st.expander(
    "🔧 Diagnóstico das fontes",
    expanded=False
):

    st.write(
        src_counts
        or
        {"nenhuma": 0}
    )

    st.caption(
        "A fonte 5DollarFootballAPI "
        "é priorizada quando o mesmo "
        "jogo aparece em mais de uma API."
    )


# ============================================================
# MÉTRICAS
# ============================================================

c1, c2, c3 = st.columns(3)

c1.metric(
    "🟢 Ao vivo",
    len(live)
)

c2.metric(
    "🔵 Próximos",
    len(upcoming)
)

c3.metric(
    "Total analisável",
    len(events)
)


if not events:

    st.warning(
        "Nenhum jogo analisável encontrado. "
        "Verifique a data e as chaves opcionais."
    )

    st.stop()


# ============================================================
# PROCESSAR JOGOS
# ============================================================

rows = []

progress = st.progress(0)

for i, e in enumerate(events):

    pred = build_prediction(e)

    sugs = suggestions(pred)

    best = (
        sugs[0]
        if sugs
        else
        (
            "Sem sugestão",
            0
        )
    )

    score = (

        f"{int(e['home_score'])}"
        f"-"
        f"{int(e['away_score'])}"

        if (
            e.get("home_score")
            is not None
            and
            e.get("away_score")
            is not None
        )

        else "-"
    )

    rows.append({

        "Status":
            e["category"],

        "Horário BRT":
            (
                e["kickoff_brt"].strftime(
                    "%d/%m %H:%M"
                )
                if e.get(
                    "kickoff_brt"
                )
                else "-"
            ),

        "Liga":
            e["league"],

        "Jogo":
            (
                f"{e['home']} "
                f"x "
                f"{e['away']}"
            ),

        "Placar":
            score,

        "Casa":
            pct(
                pred["probs"]["Casa"]
            ),

        "Empate":
            pct(
                pred["probs"]["Empate"]
            ),

        "Fora":
            pct(
                pred["probs"]["Fora"]
            ),

        "BTTS":
            pct(
                pred["probs"]["BTTS Sim"]
            ),

        "O2.5":
            pct(
                pred["probs"]["Over 2.5"]
            ),

        "U3.5":
            pct(
                pred["probs"]["Under 3.5"]
            ),

        "Sugestão":
            best[0],

        "Prob.":
            pct(best[1])
            if best[1]
            else "-",

        # CORRIGIDO:
        # coluna numérica para ordenação
        "_prob_num":
            float(best[1])
            if best[1]
            else 0,

        "Confiança":
            pct(
                pred["confidence"]
            ),

        "H2H":
            (
                pred["h2h"]["games"]
                if pred["h2h"]
                else 0
            ),

        "Fonte":
            e["source"],

        "_pred":
            pred,

        "_event":
            e
    })

    progress.progress(
        (i + 1) / len(events)
    )


progress.empty()


# ============================================================
# DATAFRAME
# ============================================================

df = pd.DataFrame(rows)


if not show_all:

    df = (
        df
        .sort_values(
            [
                "Status",
                "_prob_num"
            ],
            ascending=[
                True,
                False
            ]
        )
        .head(200)
    )


display_columns = [

    "Status",
    "Horário BRT",
    "Liga",
    "Jogo",
    "Placar",
    "Casa",
    "Empate",
    "Fora",
    "BTTS",
    "O2.5",
    "U3.5",
    "Sugestão",
    "Prob.",
    "Confiança",
    "H2H",
    "Fonte"
]


# ============================================================
# CARD DO JOGO
# ============================================================

def render_match_card(
    row,
    idx,
    live_mode=False
):

    pred = row["_pred"]

    ev = row["_event"]

    title = (

        f"{ev['home']}  "

        f"{row['Placar'] "
        "if row['Placar'] != '-' "
        "else 'x'}  "

        f"{ev['away']}"
    )

    status_icon = (
        "🟢"
        if live_mode
        else
        "🔵"
    )

    home_l10 = pred[
        "home_l10"
    ]

    away_l10 = pred[
        "away_l10"
    ]

    with st.container(
        border=True
    ):

        # ====================================================
        # CABEÇALHO
        # ====================================================

        c1, c2, c3 = st.columns(
            [5, 2, 3]
        )

        with c1:

            st.markdown(
                f"### "
                f"{status_icon} "
                f"{title}"
            )

            st.caption(
                f"{row['Liga']} • "
                f"{row['Horário BRT']} • "
                f"Fonte: {row['Fonte']}"
            )

        with c2:

            st.metric(
                "Melhor opção",
                row["Sugestão"],
                row["Prob."]
            )

        with c3:

            st.metric(
                "Confiança",
                row["Confiança"]
            )

        # ====================================================
        # MERCADOS
        # ====================================================

        b1, b2, b3, b4, b5 = st.columns(5)

        b1.metric(
            "Casa",
            row["Casa"]
        )

        b2.metric(
            "Empate",
            row["Empate"]
        )

        b3.metric(
            "Fora",
            row["Fora"]
        )

        b4.metric(
            "BTTS",
            row["BTTS"]
        )

        b5.metric(
            "O2.5",
            row["O2.5"]
        )

        # ====================================================
        # L10
        # ====================================================

        st.markdown(
            "## 📊 L10 — Últimos 10 jogos"
        )

        if (
            home_l10["jogos"]
            < 10
        ):

            st.warning(
                f"⚠️ {ev['home']}: "
                f"somente "
                f"{home_l10['jogos']} "
                f"jogos encontrados. "
                f"O sistema não inventa "
                f"os jogos faltantes."
            )

        if (
            away_l10["jogos"]
            < 10
        ):

            st.warning(
                f"⚠️ {ev['away']}: "
                f"somente "
                f"{away_l10['jogos']} "
                f"jogos encontrados. "
                f"O sistema não inventa "
                f"os jogos faltantes."
            )

        # ====================================================
        # CASA
        # ====================================================

        st.markdown(
            f"### 🏠 {ev['home']} — L10"
        )

        hcols = st.columns(8)

        hcols[0].metric(
            "J",
            home_l10["jogos"]
        )

        hcols[1].metric(
            "V",
            home_l10["vitorias"]
        )

        hcols[2].metric(
            "E",
            home_l10["empates"]
        )

        hcols[3].metric(
            "D",
            home_l10["derrotas"]
        )

        hcols[4].metric(
            "P",
            home_l10["pontos"]
        )

        hcols[5].metric(
            "GF",
            int(home_l10["gf"])
        )

        hcols[6].metric(
            "GA",
            int(home_l10["ga"])
        )

        hcols[7].metric(
            "Média GF",
            f"{home_l10['media_gf']:.2f}"
        )

        hc1, hc2, hc3, hc4, hc5, hc6 = st.columns(6)

        hc1.metric(
            "BTTS",
            f"{home_l10['btts']}/"
            f"{home_l10['jogos']}"
        )

        hc2.metric(
            "Over 1.5",
            f"{home_l10['over15']}/"
            f"{home_l10['jogos']}"
        )

        hc3.metric(
            "Over 2.5",
            f"{home_l10['over25']}/"
            f"{home_l10['jogos']}"
        )

        hc4.metric(
            "Over 3.5",
            f"{home_l10['over35']}/"
            f"{home_l10['jogos']}"
        )

        hc5.metric(
            "Clean Sheet",
            f"{home_l10['clean_sheets']}/"
            f"{home_l10['jogos']}"
        )

        hc6.metric(
            "Sem marcar",
            f"{home_l10['sem_marcar']}/"
            f"{home_l10['jogos']}"
        )

        st.caption(
            f"⚽ Gols: "
            f"{home_l10['media_gf']:.2f} "
            f"marcados | "
            f"{home_l10['media_ga']:.2f} "
            f"sofridos"
        )

        if (
            home_l10["corners_for"]
            is not None
        ):

            st.caption(
                f"🚩 Escanteios: "
                f"{home_l10['corners_for']:.2f} "
                f"a favor | "
                f"{home_l10['corners_against']:.2f} "
                f"contra | "
                f"{home_l10['corners_total']:.2f} "
                f"total"
            )

        if (
            home_l10["yellow_for"]
            is not None
        ):

            st.caption(
                f"🟨 Cartões: "
                f"{home_l10['yellow_for']:.2f} "
                f"por jogo"
            )

        # ====================================================
        # FORA
        # ====================================================

        st.markdown(
            f"### ✈️ {ev['away']} — L10"
        )

        acols = st.columns(8)

        acols[0].metric(
            "J",
            away_l10["jogos"]
        )

        acols[1].metric(
            "V",
            away_l10["vitorias"]
        )

        acols[2].metric(
            "E",
            away_l10["empates"]
        )

        acols[3].metric(
            "D",
            away_l10["derrotas"]
        )

        acols[4].metric(
            "P",
            away_l10["pontos"]
        )

        acols[5].metric(
            "GF",
            int(away_l10["gf"])
        )

        acols[6].metric(
            "GA",
            int(away_l10["ga"])
        )

        acols[7].metric(
            "Média GF",
            f"{away_l10['media_gf']:.2f}"
        )

        ac1, ac2, ac3, ac4, ac5, ac6 = st.columns(6)

        ac1.metric(
            "BTTS",
            f"{away_l10['btts']}/"
            f"{away_l10['jogos']}"
        )

        ac2.metric(
            "Over 1.5",
            f"{away_l10['over15']}/"
            f"{away_l10['jogos']}"
        )

        ac3.metric(
            "Over 2.5",
            f"{away_l10['over25']}/"
            f"{away_l10['jogos']}"
        )

        ac4.metric(
            "Over 3.5",
            f"{away_l10['over35']}/"
            f"{away_l10['jogos']}"
        )

        ac5.metric(
            "Clean Sheet",
            f"{away_l10['clean_sheets']}/"
            f"{away_l10['jogos']}"
        )

        ac6.metric(
            "Sem marcar",
            f"{away_l10['sem_marcar']}/"
            f"{away_l10['jogos']}"
        )

        st.caption(
            f"⚽ Gols: "
            f"{away_l10['media_gf']:.2f} "
            f"marcados | "
            f"{away_l10['media_ga']:.2f} "
            f"sofridos"
        )

        if (
            away_l10["corners_for"]
            is not None
        ):

            st.caption(
                f"🚩 Escanteios: "
                f"{away_l10['corners_for']:.2f} "
                f"a favor | "
                f"{away_l10['corners_against']:.2f} "
                f"contra | "
                f"{away_l10['corners_total']:.2f} "
                f"total"
            )

        if (
            away_l10["yellow_for"]
            is not None
        ):

            st.caption(
                f"🟨 Cartões: "
                f"{away_l10['yellow_for']:.2f} "
                f"por jogo"
            )

        # ====================================================
        # 10 JOGOS EXATOS
        # ====================================================

        with st.expander(
            "📋 Ver os 10 jogos do L10",
            expanded=False
        ):

            def tabela_l10(
                rows
            ):

                data = []

                for i, r in enumerate(
                    rows,
                    1
                ):

                    data.append({

                        "#":
                            i,

                        "Data":
                            r.get(
                                "date",
                                ""
                            ),

                        "Adversário":
                            r.get(
                                "opponent",
                                ""
                            ),

                        "Casa/Fora":
                            (
                                "Casa"
                                if r.get(
                                    "home"
                                )
                                else
                                "Fora"
                            ),

                        "Placar":
                            (
                                f"{int(r['gf'])}"
                                f"-"
                                f"{int(r['ga'])}"
                            ),

                        "Resultado":
                            r["result"],

                        "GF":
                            r["gf"],

                        "GA":
                            r["ga"]
                    })

                return pd.DataFrame(
                    data
                )

            st.markdown(
                f"**{ev['home']} — "
                f"últimos "
                f"{len(pred['home_form'])} "
                f"jogos**"
            )

            st.dataframe(
                tabela_l10(
                    pred[
                        "home_form"
                    ]
                ),
                use_container_width=True,
                hide_index=True
            )

            st.markdown(
                f"**{ev['away']} — "
                f"últimos "
                f"{len(pred['away_form'])} "
                f"jogos**"
            )

            st.dataframe(
                tabela_l10(
                    pred[
                        "away_form"
                    ]
                ),
                use_container_width=True,
                hide_index=True
            )

        # ====================================================
        # AO VIVO
        # ====================================================

        if live_mode:

            if (
                ev.get("minute")
                is not None
            ):

                st.caption(
                    f"⏱️ Minuto: "
                    f"{ev.get('minute')} "
                    f"| Placar: "
                    f"{row['Placar']}"
                )

            live_stats = []

            for key, label in [

                (
                    "home_corners",
                    "Esc. casa"
                ),

                (
                    "away_corners",
                    "Esc. fora"
                ),

                (
                    "home_shots",
                    "Chutes casa"
                ),

                (
                    "away_shots",
                    "Chutes fora"
                ),

                (
                    "home_dangerous",
                    "Ataques perigosos casa"
                ),

                (
                    "away_dangerous",
                    "Ataques perigosos fora"
                )
            ]:

                if (
                    ev.get(key)
                    is not None
                ):

                    live_stats.append(
                        f"{label}: "
                        f"{ev[key]}"
                    )

            if live_stats:

                st.caption(
                    " • ".join(
                        live_stats
                    )
                )

        # ====================================================
        # ANÁLISE
        # ====================================================

        with st.expander(
            "📈 Ver análise completa",
            expanded=False
        ):

            x1, x2 = st.columns(2)

            with x1:

                st.markdown(
                    "**Mercados**"
                )

                st.write(
                    f"BTTS Sim: "
                    f"{row['BTTS']} "
                    f"| Over 2.5: "
                    f"{row['O2.5']} "
                    f"| Under 3.5: "
                    f"{row['U3.5']}"
                )

                st.write(
                    f"H2H analisados: "
                    f"{row['H2H']}"
                )

            with x2:

                st.markdown(
                    "**Sugestões principais**"
                )

                for nome, prob in suggestions(
                    pred
                ):

                    st.write(
                        f"• {nome}: "
                        f"{pct(prob)}"
                    )

            h = (
                pred.get("h2h")
                or {}
            )

            if h.get("games"):

                st.caption(
                    f"H2H: "
                    f"{h.get('games')} jogos "
                    f"| Casa "
                    f"{h.get('home_wins', 0)} "
                    f"vitórias "
                    f"| Empates "
                    f"{h.get('draws', 0)} "
                    f"| Fora "
                    f"{h.get('away_wins', 0)}"
                )


# ============================================================
# ABA AO VIVO
# ============================================================

with tab_live:

    st.subheader(
        "🟢 Jogos ao vivo"
    )

    st.caption(
        "Atualização automática "
        "a cada 60 segundos."
    )

    live_df = df[
        df["Status"]
        == "AO VIVO"
    ]

    if live_df.empty:

        st.info(
            "Nenhum jogo ao vivo "
            "neste momento."
        )

    else:

        for idx, (_, r) in enumerate(
            live_df.iterrows()
        ):

            render_match_card(
                r,
                idx,
                live_mode=True
            )


# ============================================================
# ABA PRÓXIMOS
# ============================================================

with tab_upcoming:

    st.subheader(
        "🔵 Próximos jogos"
    )

    up_df = df[
        df["Status"]
        == "PRÓXIMO"
    ]

    if up_df.empty:

        st.info(
            "Nenhum próximo jogo "
            "encontrado."
        )

    else:

        st.dataframe(
            up_df[
                display_columns
            ],
            use_container_width=True,
            hide_index=True
        )

        escolha = st.selectbox(
            "🔎 Abrir análise de um próximo jogo",
            list(up_df.index),

            format_func=lambda i:
                (
                    f"{df.loc[i, 'Jogo']} "
                    f"— "
                    f"{df.loc[i, 'Sugestão']} "
                    f"({df.loc[i, 'Prob.']})"
                )
        )

        render_match_card(
            df.loc[escolha],
            int(escolha),
            live_mode=False
        )


# ============================================================
# MELHORES OPORTUNIDADES
# ============================================================

with tab_best:

    st.subheader(
        "⭐ Melhores oportunidades"
    )

    st.caption(
        "Ordenadas pela maior "
        "probabilidade numérica."
    )

    best_df = (
        df
        .sort_values(
            "_prob_num",
            ascending=False
        )
        .head(20)
    )

    for idx, (_, r) in enumerate(
        best_df.iterrows()
    ):

        render_match_card(
            r,
            idx,
            live_mode=(
                r["Status"]
                == "AO VIVO"
            )
        )


# ============================================================
# CSV
# ============================================================

csv = (
    df[
        display_columns
    ]
    .to_csv(
        index=False
    )
    .encode("utf-8-sig")
)

st.download_button(
    "⬇️ Baixar CSV",
    csv,
    "football_scanner_L10.csv",
    "text/csv"
)


# ============================================================
# RODAPÉ
# ============================================================

st.divider()

st.caption(
    "⚽ Global Football Scanner | "
    "Modelo baseado no L10 | "
    "Últimos 10 jogos finalizados"
)
