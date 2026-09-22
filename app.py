# ============================================================
# GLOBAL FOOTBALL SCANNER
# ============================================================
# L10 + LIVE + PRÉ-JOGO + FINALIZADOS
# TheSportsDB
# football-data.org
# OpenFootAPI
# 5DollarFootballAPI
# ============================================================

import os
import math
import traceback
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st


# ============================================================
# CONFIGURAÇÃO STREAMLIT
# ============================================================

st.set_page_config(
    page_title="Global Football Scanner",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CONFIGURAÇÃO DAS APIs
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

L10_N = 10

BRT = ZoneInfo("America/Sao_Paulo")


# ============================================================
# STATUS
# ============================================================

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


# ============================================================
# FUNÇÕES UTILITÁRIAS
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

            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(BRT)

    except Exception:

        return None


# ============================================================
# CLASSIFICAÇÃO DAS PARTIDAS
# ============================================================

def classify_event(event):

    status = norm_status(
        event.get("status", "")
    )

    # LIVE
    if status in LIVE_STATUSES:
        return "live"

    # FINALIZADO
    if status in FINAL_STATUSES:
        return "finished"

    # PRÉ-JOGO
    if status in PRE_STATUSES:
        return "upcoming"

    kickoff = parse_kickoff(
        event.get("kickoff")
    )

    if kickoff:

        now = datetime.now(BRT)

        # Futuro = próximo
        if kickoff > now:
            return "upcoming"

        # Se possui placar, provavelmente finalizado
        if (
            event.get("home_score") is not None
            and
            event.get("away_score") is not None
        ):

            return "finished"

        # Não esconder partidas com status desconhecido
        return "unknown"

    # IMPORTANTE:
    # Se a API não informou status/data corretamente,
    # não descartamos a partida.
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
            *
            (lam ** k)
            /
            math.factorial(k)
        )

    except Exception:

        return 0.0


def model_probs(
    home_lambda,
    away_lambda
):

    home_lambda = max(
        0.01,
        safe_float(
            home_lambda,
            1.0
        )
    )

    away_lambda = max(
        0.01,
        safe_float(
            away_lambda,
            1.0
        )
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

    total = (
        home_win
        +
        draw
        +
        away_win
    )

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
# REQUEST HTTP
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
            timeout=timeout,
        )

        if response.status_code != 200:

            return None

        return response.json()

    except Exception:

        return None


# ============================================================
# THE SPORTS DB
# ============================================================

def tsdb_day(day):

    data = request_json(
        f"{TSDB_BASE}/eventsday.php",
        params={
            "d": day.isoformat(),
            "s": "Soccer",
        },
    )

    if not data:
        return []

    return data.get(
        "events",
        []
    ) or []


def tsdb_team_search(team):

    data = request_json(
        f"{TSDB_BASE}/searchteams.php",
        params={
            "t": team
        },
    )

    if not data:
        return []

    return data.get(
        "teams",
        []
    ) or []


def tsdb_last(team_id):

    data = request_json(
        f"{TSDB_BASE}/eventslast.php",
        params={
            "id": team_id
        },
    )

    if not data:
        return []

    return data.get(
        "results",
        []
    ) or []


def normalize_tsdb_event(event):

    return {

        "id": event.get(
            "idEvent"
        ),

        "home": event.get(
            "strHomeTeam"
        ),

        "away": event.get(
            "strAwayTeam"
        ),

        "home_id": event.get(
            "idHomeTeam"
        ),

        "away_id": event.get(
            "idAwayTeam"
        ),

        "kickoff": event.get(
            "strTimestamp"
        )
        or event.get(
            "dateEvent"
        ),

        "status": event.get(
            "strStatus"
        )
        or event.get(
            "strProgress"
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
        },
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
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
        },
    )

    if not data:
        return []

    return data.get(
        "matches",
        []
    ) or []


def normalize_fd_event(event):

    score = event.get(
        "score",
        {}
    ) or {}

    full_time = score.get(
        "fullTime",
        {}
    ) or {}

    home_team = event.get(
        "homeTeam",
        {}
    ) or {}

    away_team = event.get(
        "awayTeam",
        {}
    ) or {}

    return {

        "id": event.get(
            "id"
        ),

        "home": home_team.get(
            "name"
        ),

        "away": away_team.get(
            "name"
        ),

        "home_id": home_team.get(
            "id"
        ),

        "away_id": away_team.get(
            "id"
        ),

        "kickoff": event.get(
            "utcDate"
        ),

        "status": event.get(
            "status"
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
        },
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
        },
    )

    if not data:
        return []

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
        },
    )

    if not data:
        return []

    return (
        data.get("matches")
        or data.get("data")
        or []
    )


def normalize_openfoot_event(event):

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
        home_id = None

    else:

        home_name = (
            home.get("name")
            or home.get("teamName")
        )

        home_id = (
            home.get("id")
            or home.get("teamId")
        )

    if isinstance(away, str):

        away_name = away
        away_id = None

    else:

        away_name = (
            away.get("name")
            or away.get("teamName")
        )

        away_id = (
            away.get("id")
            or away.get("teamId")
        )

    score = (
        event.get("score")
        or {}
    )

    return {

        "id": (
            event.get("id")
            or event.get("matchId")
        ),

        "home": home_name,

        "away": away_name,

        "home_id": home_id,

        "away_id": away_id,

        "kickoff": (
            event.get("utcDate")
            or event.get("date")
            or event.get("kickoff")
            or event.get("startTime")
        ),

        "status": (
            event.get("status")
            or event.get("state")
        ),

        "home_score": (
            event.get("homeScore")
            or score.get("home")
        ),

        "away_score": (
            event.get("awayScore")
            or score.get("away")
        ),

        "source": "OpenFootAPI",

        "raw": event,
    }


# ============================================================
# 5 DOLLAR FOOTBALL API
# ============================================================

def fd5_day(day):

    if not FD5_TOKEN:

        return []

    data = request_json(
        f"{FD5_BASE}/matches",
        headers={
            "Authorization":
            f"Bearer {FD5_TOKEN}"
        },
        params={
            "date": day.isoformat()
        },
    )

    if not data:
        return []

    return (
        data.get("matches")
        or data.get("data")
        or []
    )


def fd5_team_fixtures(team_id):

    if not FD5_TOKEN:

        return []

    data = request_json(
        f"{FD5_BASE}/teams/{team_id}/fixtures",
        headers={
            "Authorization":
            f"Bearer {FD5_TOKEN}"
        },
    )

    if not data:
        return []

    return (
        data.get("matches")
        or data.get("fixtures")
        or data.get("data")
        or []
    )


def normalize_fd5_event(event):

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
        home_id = None

    else:

        home_name = (
            home.get("name")
            or home.get("teamName")
        )

        home_id = (
            home.get("id")
            or home.get("teamId")
        )

    if isinstance(away, str):

        away_name = away
        away_id = None

    else:

        away_name = (
            away.get("name")
            or away.get("teamName")
        )

        away_id = (
            away.get("id")
            or away.get("teamId")
        )

    score = (
        event.get("score")
        or {}
    )

    return {

        "id": (
            event.get("id")
            or event.get("matchId")
        ),

        "home": home_name,

        "away": away_name,

        "home_id": home_id,

        "away_id": away_id,

        "kickoff": (
            event.get("utcDate")
            or event.get("date")
            or event.get("kickoff")
            or event.get("startTime")
        ),

        "status": (
            event.get("status")
            or event.get("state")
        ),

        "home_score": (
            event.get("homeScore")
            if event.get("homeScore") is not None
            else score.get("home")
        ),

        "away_score": (
            event.get("awayScore")
            if event.get("awayScore") is not None
            else score.get("away")
        ),

        "source": "5DollarFootballAPI",

        "raw": event,
    }


# ============================================================
# EVENTOS
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
            +
            "_"
            +
            str(event["id"])
        )

    return (
        normalize_name(
            event.get("home")
        )
        +
        "_"
        +
        normalize_name(
            event.get("away")
        )
        +
        "_"
        +
        str(
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

    hs = event.get(
        "home_score"
    )

    aws = event.get(
        "away_score"
    )

    return (
        hs is not None
        and
        aws is not None
        and
        status not in LIVE_STATUSES
    )


# ============================================================
# CARREGAR EVENTOS DO DIA
# ============================================================

def load_global_events():

    today = datetime.now(
        BRT
    ).date()

    all_events = []

    # --------------------------------------------------------
    # THESPORTSDB
    # --------------------------------------------------------

    try:

        for raw in tsdb_day(today):

            event = normalize_tsdb_event(
                raw
            )

            if (
                event.get("home")
                and
                event.get("away")
            ):

                all_events.append(
                    event
                )

    except Exception:
        pass


    # --------------------------------------------------------
    # FOOTBALL-DATA
    # --------------------------------------------------------

    try:

        if FD_TOKEN:

            for raw in fd_matches(
                today,
                today
            ):

                event = normalize_fd_event(
                    raw
                )

                if (
                    event.get("home")
                    and
                    event.get("away")
                ):

                    all_events.append(
                        event
                    )

    except Exception:
        pass


    # --------------------------------------------------------
    # OPENFOOT
    # --------------------------------------------------------

    try:

        if OPENFOOT_TOKEN:

            for raw in openfoot_matches():

                event = normalize_openfoot_event(
                    raw
                )

                if not (
                    event.get("home")
                    and
                    event.get("away")
                ):

                    continue

                edate = event_date(
                    event
                )

                if (
                    edate is None
                    or
                    edate == today
                ):

                    all_events.append(
                        event
                    )

    except Exception:
        pass


    # --------------------------------------------------------
    # 5 DOLLAR
    # --------------------------------------------------------

    try:

        if FD5_TOKEN:

            for raw in fd5_day(
                today
            ):

                event = normalize_fd5_event(
                    raw
                )

                if (
                    event.get("home")
                    and
                    event.get("away")
                ):

                    all_events.append(
                        event
                    )

    except Exception:
        pass


    # ========================================================
    # REMOVER DUPLICADAS
    # ========================================================

    priority = {

        "5DollarFootballAPI": 5,

        "OpenFootAPI": 4,

        "football-data.org": 3,

        "TheSportsDB": 1,
    }

    unique = {}

    for event in all_events:

        key = event_key(
            event
        )

        if key not in unique:

            unique[key] = event

        else:

            old = unique[key]

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


    events = list(
        unique.values()
    )


    # ========================================================
    # ORDENAR
    # ========================================================

    events.sort(
        key=lambda x: (
            parse_kickoff(
                x.get("kickoff")
            )
            or datetime.max.replace(
                tzinfo=timezone.utc
            )
        )
    )


    return events


# ============================================================
# FORMULÁRIO L10
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

        # Compatibilidade parcial
        if (
            team_norm not in home
            and
            team_norm not in away
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

        if (
            hs is None
            or
            aws is None
        ):

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
                event_date(
                    event
                ),

            "opponent":
                (
                    event.get("away")
                    if team_norm == home
                    else
                    event.get("home")
                ),

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


# ============================================================
# ESTATÍSTICAS L10
# ============================================================

def l10_stats(form):

    jogos = len(form)

    vitorias = sum(
        1
        for x in form
        if x["result"] == "V"
    )

    empates = sum(
        1
        for x in form
        if x["result"] == "E"
    )

    derrotas = sum(
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

    media_gf = (
        gf / jogos
        if jogos
        else 0
    )

    media_ga = (
        ga / jogos
        if jogos
        else 0
    )

    return {

        "jogos": jogos,

        "vitorias": vitorias,

        "empates": empates,

        "derrotas": derrotas,

        "gf": gf,

        "ga": ga,

        "media_gf": media_gf,

        "media_ga": media_ga,
    }


# ============================================================
# H2H
# ============================================================

def h2h_stats(
    events,
    home,
    away
):

    home_norm = normalize_name(
        home
    )

    away_norm = normalize_name(
        away
    )

    matches = []

    for event in events:

        if not event_is_finished(
            event
        ):

            continue

        eh = normalize_name(
            event.get("home")
        )

        ea = normalize_name(
            event.get("away")
        )

        same_order = (
            home_norm in eh
            and
            away_norm in ea
        )

        reverse_order = (
            home_norm in ea
            and
            away_norm in eh
        )

        if same_order or reverse_order:

            matches.append(
                event
            )


    matches.sort(
        key=lambda x: (
            event_date(x)
            or datetime.min.date()
        ),
        reverse=True
    )


    return matches[:10]


# ============================================================
# PREVISÃO
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


    home_attack = hs[
        "media_gf"
    ]

    home_defense = hs[
        "media_ga"
    ]

    away_attack = aws[
        "media_gf"
    ]

    away_defense = aws[
        "media_ga"
    ]


    # Base caso não exista L10
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


    # Fator simples de mando
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

        **probs,
    }


# ============================================================
# ODD JUSTA
# ============================================================

def fair_odd(
    probability
):

    probability = safe_float(
        probability
    )

    if probability <= 0:

        return None

    return 1 / probability


# ============================================================
# SUGESTÕES
# ============================================================

def suggestions(
    pred
):

    markets = [

        (
            "1X",
            pred["1x"]
        ),

        (
            "X2",
            pred["x2"]
        ),

        (
            "BTTS SIM",
            pred["btts_yes"]
        ),

        (
            "BTTS NÃO",
            pred["btts_no"]
        ),

        (
            "OVER 1.5",
            pred["over15"]
        ),

        (
            "OVER 2.5",
            pred["over25"]
        ),

        (
            "UNDER 2.5",
            pred["under25"]
        ),

        (
            "UNDER 3.5",
            pred["under35"]
        ),
    ]


    rows = []

    for name, probability in markets:

        rows.append({

            "Mercado":
                name,

            "Probabilidade":
                probability,

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
# ANÁLISE DA PARTIDA
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


    prediction = build_prediction(
        home_l10,
        away_l10
    )


    h2h = h2h_stats(
        all_events,
        home,
        away
    )


    return {

        "event":
            event,

        "home_l10":
            home_l10,

        "away_l10":
            away_l10,

        "prediction":
            prediction,

        "h2h":
            h2h,

        "suggestions":
            suggestions(
                prediction
            ),
    }


# ============================================================
# PLACAR
# ============================================================

def display_score(
    event
):

    hs = event.get(
        "home_score"
    )

    aws = event.get(
        "away_score"
    )

    if (
        hs is None
        or
        aws is None
    ):

        return "x"

    return (
        f"{hs} - {aws}"
    )


# ============================================================
# CARD DA PARTIDA
# ============================================================

def render_match_card(
    analysis
):

    event = analysis[
        "event"
    ]

    pred = analysis[
        "prediction"
    ]

    home_l10 = analysis[
        "home_l10"
    ]

    away_l10 = analysis[
        "away_l10"
    ]

    h2h = analysis[
        "h2h"
    ]

    market_rows = analysis[
        "suggestions"
    ]


    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    tipo = classify_event(
        event
    )

    if tipo == "live":

        status_text = "🔴 AO VIVO"

    elif tipo == "finished":

        status_text = "⚫ FINALIZADO"

    elif tipo == "upcoming":

        status_text = "🟢 PRÓXIMO"

    else:

        status_text = "⚪ STATUS DESCONHECIDO"


    kickoff = parse_kickoff(
        event.get("kickoff")
    )


    if kickoff:

        horario = kickoff.strftime(
            "%d/%m/%Y %H:%M"
        )

    else:

        horario = "Horário não informado"


    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    placar = display_score(
        event
    )

    titulo = (
        f"{event.get('home', 'Casa')} "
        f"  {placar}  "
        f"{event.get('away', 'Fora')}"
    )


    with st.container(
        border=True
    ):

        st.subheader(
            titulo
        )

        st.caption(
            f"{status_text}  •  "
            f"{horario}  •  "
            f"Fonte: {event.get('source', '-')}"
        )


        # ----------------------------------------------------
        # MÉTRICAS
        # ----------------------------------------------------

        c1, c2, c3, c4 = st.columns(4)


        c1.metric(
            "1X",
            pct(
                pred["1x"]
                * 100
            )
        )


        c2.metric(
            "X2",
            pct(
                pred["x2"]
                * 100
            )
        )


        c3.metric(
            "BTTS SIM",
            pct(
                pred["btts_yes"]
                * 100
            )
        )


        c4.metric(
            "OVER 2.5",
            pct(
                pred["over25"]
                * 100
            )
        )


        st.write(
            f"⚽ Gols esperados: "
            f"**{pred['home_lambda']:.2f}** "
            f"x "
            f"**{pred['away_lambda']:.2f}**"
        )


        # ----------------------------------------------------
        # L10
        # ----------------------------------------------------

        st.markdown(
            "### 📊 L10"
        )


        col_home, col_away = st.columns(2)


        with col_home:

            st.markdown(
                f"**{event.get('home')}**"
            )

            stats = l10_stats(
                home_l10
            )

            st.caption(
                f"Jogos: {stats['jogos']} | "
                f"V: {stats['vitorias']} | "
                f"E: {stats['empates']} | "
                f"D: {stats['derrotas']} | "
                f"GF: {stats['gf']:.0f} | "
                f"GA: {stats['ga']:.0f}"
            )


            if home_l10:

                df_home = pd.DataFrame({

                    "Data": [
                        (
                            x["date"].strftime(
                                "%d/%m"
                            )
                            if x["date"]
                            else "-"
                        )
                        for x in home_l10
                    ],

                    "Adversário": [
                        x["opponent"]
                        for x in home_l10
                    ],

                    "Placar": [
                        f"{x['gf']:.0f}-{x['ga']:.0f}"
                        for x in home_l10
                    ],

                    "R": [
                        x["result"]
                        for x in home_l10
                    ],
                })


                st.dataframe(
                    df_home,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "L10 não disponível."
                )


        with col_away:

            st.markdown(
                f"**{event.get('away')}**"
            )

            stats = l10_stats(
                away_l10
            )

            st.caption(
                f"Jogos: {stats['jogos']} | "
                f"V: {stats['vitorias']} | "
                f"E: {stats['empates']} | "
                f"D: {stats['derrotas']} | "
                f"GF: {stats['gf']:.0f} | "
                f"GA: {stats['ga']:.0f}"
            )


            if away_l10:

                df_away = pd.DataFrame({

                    "Data": [
                        (
                            x["date"].strftime(
                                "%d/%m"
                            )
                            if x["date"]
                            else "-"
                        )
                        for x in away_l10
                    ],

                    "Adversário": [
                        x["opponent"]
                        for x in away_l10
                    ],

                    "Placar": [
                        f"{x['gf']:.0f}-{x['ga']:.0f}"
                        for x in away_l10
                    ],

                    "R": [
                        x["result"]
                        for x in away_l10
                    ],
                })


                st.dataframe(
                    df_away,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "L10 não disponível."
                )


        # ----------------------------------------------------
        # MERCADOS
        # ----------------------------------------------------

        st.markdown(
            "### 🎯 Mercados"
        )


        market_df = pd.DataFrame({

            "Mercado": [
                x["Mercado"]
                for x in market_rows
            ],

            "Probabilidade": [
                pct(
                    x["Probabilidade"]
                    * 100
                )
                for x in market_rows
            ],

            "Odd justa": [
                (
                    f"{x['Odd justa']:.2f}"
                    if x["Odd justa"]
                    else "-"
                )
                for x in market_rows
            ],
        })


        st.dataframe(
            market_df,
            use_container_width=True,
            hide_index=True
        )


        # ----------------------------------------------------
        # H2H
        # ----------------------------------------------------

        with st.expander(
            f"🤝 H2H — últimos {len(h2h)}"
        ):

            if h2h:

                h2h_rows = []

                for item in h2h:

                    h2h_rows.append({

                        "Data":
                            (
                                event_date(
                                    item
                                ).strftime(
                                    "%d/%m/%Y"
                                )
                                if event_date(
                                    item
                                )
                                else "-"
                            ),

                        "Casa":
                            item.get(
                                "home"
                            ),

                        "Placar":
                            display_score(
                                item
                            ),

                        "Fora":
                            item.get(
                                "away"
                            ),

                        "Fonte":
                            item.get(
                                "source"
                            ),
                    })


                st.dataframe(
                    pd.DataFrame(
                        h2h_rows
                    ),
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "H2H não encontrado."
                )


# ============================================================
# STATUS DAS APIs
# ============================================================

def api_status():

    st.markdown(
        "### 🔌 Status das fontes"
    )


    c1, c2, c3, c4 = st.columns(4)


    c1.write(
        "🟢 TheSportsDB"
    )


    c2.write(
        "🟢 football-data.org"
        if FD_TOKEN
        else
        "⚪ football-data.org — sem token"
    )


    c3.write(
        "🟢 OpenFootAPI"
        if OPENFOOT_TOKEN
        else
        "⚪ OpenFootAPI — sem token"
    )


    c4.write(
        "🟢 5DollarFootballAPI"
        if FD5_TOKEN
        else
        "⚪ 5DollarFootballAPI — sem token"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    st.title(
        "⚽ Global Football Scanner"
    )

    st.caption(
        "Scanner global • L10 • Ao vivo • "
        "Próximos • Finalizados • "
        "Probabilidades • Odd justa"
    )


    # ========================================================
    # SIDEBAR
    # ========================================================

    st.sidebar.header(
        "⚙️ Filtros"
    )


    mostrar_todas = st.sidebar.checkbox(
        "🌎 Mostrar todas as partidas",
        value=True
    )


    mostrar_ao_vivo = st.sidebar.checkbox(
        "🔴 Ao vivo",
        value=True
    )


    mostrar_proximos = st.sidebar.checkbox(
        "🟢 Próximos",
        value=True
    )


    mostrar_finalizados = st.sidebar.checkbox(
        "⚫ Finalizados",
        value=False
    )


    limite = st.sidebar.slider(
        "Quantidade de partidas",
        min_value=5,
        max_value=100,
        value=100
    )


    if st.sidebar.button(
        "🔄 Atualizar agora",
        use_container_width=True
    ):

        st.rerun()


    # ========================================================
    # API STATUS
    # ========================================================

    with st.expander(
        "🔌 APIs"
    ):

        api_status()


    # ========================================================
    # CARREGAR
    # ========================================================

    with st.spinner(
        "Buscando partidas..."
    ):

        events = load_global_events()


    if not events:

        st.warning(
            "Nenhuma partida encontrada."
        )

        st.info(
            "Verifique as APIs e tokens configurados "
            "no Streamlit Cloud."
        )

        return


    # ========================================================
    # FILTRO
    # ========================================================

    filtered = []


    for event in events:

        tipo = classify_event(
            event
        )


        # ----------------------------------------------------
        # MODO TODAS
        # ----------------------------------------------------

        if mostrar_todas:

            filtered.append(
                event
            )

            continue


        # ----------------------------------------------------
        # FILTRO NORMAL
        # ----------------------------------------------------

        if (
            tipo == "live"
            and
            mostrar_ao_vivo
        ):

            filtered.append(
                event
            )


        elif (
            tipo == "upcoming"
            and
            mostrar_proximos
        ):

            filtered.append(
                event
            )


        elif (
            tipo == "finished"
            and
            mostrar_finalizados
        ):

            filtered.append(
                event
            )


        # ----------------------------------------------------
        # STATUS DESCONHECIDO
        # ----------------------------------------------------
        # Nunca esconder partidas desconhecidas.
        #
        # Isso resolve o problema de APIs que enviam
        # status diferentes.
        #

        elif (
            tipo == "unknown"
            and
            mostrar_todas
        ):

            filtered.append(
                event
            )


    # ========================================================
    # LIMITE
    # ========================================================

    filtered = filtered[
        :limite
    ]


    # ========================================================
    # RESUMO
    # ========================================================

    st.success(
        f"**{len(events)} partidas encontradas** "
        f"| "
        f"**{len(filtered)} exibidas**"
    )


    # ========================================================
    # CONTADORES
    # ========================================================

    live_count = sum(
        classify_event(x) == "live"
        for x in events
    )

    upcoming_count = sum(
        classify_event(x) == "upcoming"
        for x in events
    )

    finished_count = sum(
        classify_event(x) == "finished"
        for x in events
    )

    unknown_count = sum(
        classify_event(x) == "unknown"
        for x in events
    )


    c1, c2, c3, c4 = st.columns(4)


    c1.metric(
        "🔴 Ao vivo",
        live_count
    )


    c2.metric(
        "🟢 Próximos",
        upcoming_count
    )


    c3.metric(
        "⚫ Finalizados",
        finished_count
    )


    c4.metric(
        "⚪ Outros",
        unknown_count
    )


    # ========================================================
    # TABELA RESUMO
    # ========================================================

    summary = []


    for event in filtered:

        kickoff = parse_kickoff(
            event.get("kickoff")
        )


        summary.append({

            "Status":
                (
                    "🔴 LIVE"
                    if classify_event(event) == "live"
                    else
                    "⚫ FINAL"
                    if classify_event(event) == "finished"
                    else
                    "🟢 PRÓXIMO"
                    if classify_event(event) == "upcoming"
                    else
                    "⚪ OUTRO"
                ),

            "Data/Hora":
                (
                    kickoff.strftime(
                        "%d/%m %H:%M"
                    )
                    if kickoff
                    else "-"
                ),

            "Casa":
                event.get(
                    "home"
                ),

            "Placar":
                display_score(
                    event
                ),

            "Fora":
                event.get(
                    "away"
                ),

            "Fonte":
                event.get(
                    "source"
                ),
        })


    if summary:

        st.markdown(
            "### 📋 Partidas encontradas"
        )

        st.dataframe(
            pd.DataFrame(
                summary
            ),
            use_container_width=True,
            hide_index=True
        )


    # ========================================================
    # ANÁLISES
    # ========================================================

    st.markdown(
        "## 📊 Análises"
    )


    if not filtered:

        st.warning(
            "Nenhuma partida passou pelos filtros."
        )

        return


    for index, event in enumerate(
        filtered,
        start=1
    ):

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
                f"Erro analisando "
                f"{event.get('home')} x "
                f"{event.get('away')}: "
                f"{error}"
            )

            with st.expander(
                "Detalhes do erro"
            ):

                st.code(
                    traceback.format_exc()
                )


# ============================================================
# EXECUÇÃO SEGURA
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as error:

        st.error(
            "O aplicativo encontrou um erro."
        )

        st.exception(
            error
        )
