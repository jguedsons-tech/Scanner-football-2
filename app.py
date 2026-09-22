# ============================================================
# UTILITÁRIOS DE EVENTOS
# ============================================================

def normalize_name(name):
    if not name:
        return ""

    text = str(name).lower().strip()

    text = re.sub(
        r"[^a-z0-9áéíóúãõç\s]",
        " ",
        text
    )

    text = re.sub(r"\s+", " ", text)

    return text


def event_key(event):
    home = normalize_name(event.get("home", ""))
    away = normalize_name(event.get("away", ""))

    kickoff = str(
        event.get("kickoff", "")
    )[:10]

    return kickoff, home, away


def event_date(event):
    kickoff = parse_kickoff(
        event.get("kickoff")
    )

    if kickoff:
        return kickoff.date()

    return None


def event_is_finished(event):
    status = norm_status(
        event.get("status", "")
    )

    if status in FINAL_STATUSES:
        return True

    hs = event.get("home_score")
    aws = event.get("away_score")

    if hs is None or aws is None:
        return False

    if is_live_status(status):
        return False

    return True


# ============================================================
# CARREGAR EVENTOS
# ============================================================

@st.cache_data(
    ttl=CALENDAR_TTL,
    show_spinner=False
)
def load_global_events(
    start_date,
    days=1
):

    events = []

    for offset in range(
        max(1, int(days))
    ):

        current = (
            start_date
            + timedelta(days=offset)
        )

        day_string = current.strftime(
            "%Y-%m-%d"
        )

        # ----------------------------------------------------
        # THESPORTSDB
        # ----------------------------------------------------

        try:

            raw = tsdb_day(
                day_string
            )

            for item in raw:

                event = normalize_tsdb_event(
                    item
                )

                if event:
                    events.append(event)

        except Exception:
            pass

        # ----------------------------------------------------
        # FOOTBALL-DATA
        # ----------------------------------------------------

        if FD_TOKEN:

            try:

                raw = fd_matches(
                    day_string,
                    day_string
                )

                for item in raw:

                    event = normalize_fd_event(
                        item
                    )

                    if event:
                        events.append(event)

            except Exception:
                pass

        # ----------------------------------------------------
        # OPENFOOT
        # ----------------------------------------------------

        if OPENFOOT_TOKEN:

            try:

                raw = openfoot_matches()

                for item in raw:

                    event = normalize_openfoot_event(
                        item
                    )

                    if not event:
                        continue

                    if event_date(event) == current:

                        events.append(event)

            except Exception:
                pass

        # ----------------------------------------------------
        # 5DOLLAR
        # ----------------------------------------------------

        if FD5_TOKEN:

            try:

                raw = fd5_day(
                    day_string
                )

                for item in raw:

                    event = normalize_fd5_event(
                        item
                    )

                    if event:
                        events.append(event)

            except Exception:
                pass

    # --------------------------------------------------------
    # DEDUPLICAR
    # --------------------------------------------------------

    priority = {

        "5DollarFootballAPI": 5,

        "OpenFootAPI": 4,

        "football-data.org": 3,

        "TheSportsDB": 1,

    }

    unique = {}

    for event in events:

        key = event_key(event)

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

    result = list(
        unique.values()
    )

    result.sort(
        key=lambda x: (
            parse_kickoff(
                x.get("kickoff")
            )
            or datetime.max.replace(
                tzinfo=BRT
            )
        )
    )

    return result


# ============================================================
# FORM DOS TIMES
# ============================================================

def make_form(
    normalized_events,
    team_id
):

    rows = []

    if not team_id:
        return rows

    team_id = str(team_id)

    for event in normalized_events:

        home_id = str(
            event.get(
                "home_id",
                ""
            )
        )

        away_id = str(
            event.get(
                "away_id",
                ""
            )
        )

        if (
            team_id != home_id
            and team_id != away_id
        ):
            continue

        if not event_is_finished(event):
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

        is_home = (
            team_id == home_id
        )

        if is_home:

            gf = hs
            ga = aws

            opponent = event.get(
                "away",
                "Adversário"
            )

            opponent_id = away_id

        else:

            gf = aws
            ga = hs

            opponent = event.get(
                "home",
                "Adversário"
            )

            opponent_id = home_id

        if gf > ga:

            result = "V"

        elif gf == ga:

            result = "E"

        else:

            result = "D"

        kickoff = parse_kickoff(
            event.get("kickoff")
        )

        if kickoff:

            date_value = kickoff.strftime(
                "%d/%m/%Y"
            )

            time_value = kickoff.strftime(
                "%H:%M"
            )

            sort_date = kickoff

        else:

            date_value = "-"

            time_value = "-"

            sort_date = datetime.min.replace(
                tzinfo=BRT
            )

        rows.append({

            "date": date_value,

            "time": time_value,

            "_sort_date": sort_date,

            "gf": gf,

            "ga": ga,

            "result": result,

            "home": is_home,

            "opponent": opponent,

            "opponent_id": opponent_id,

            "corners_for": None,

            "corners_against": None,

            "yellow_for": None,

            "yellow_against": None,

            "source": event.get(
                "source",
                ""
            ),

            "event_id": event.get(
                "id",
                ""
            ),

        })

    return rows


# ============================================================
# ORDENAR L10
# ============================================================

def ordenar_l10(rows):

    if not rows:
        return []

    unique = []

    seen = set()

    for row in rows:

        key = (

            row.get("date", ""),

            row.get("time", ""),

            normalize_name(
                row.get(
                    "opponent",
                    ""
                )
            ),

            safe_float(
                row.get("gf")
            ),

            safe_float(
                row.get("ga")
            ),

        )

        if key in seen:
            continue

        seen.add(key)

        unique.append(row)

    unique.sort(
        key=lambda x: x.get(
            "_sort_date",
            datetime.min.replace(
                tzinfo=BRT
            )
        ),
        reverse=True
    )

    return unique[:L10_N]


# ============================================================
# HISTÓRICO L10
# ============================================================

def team_form(
    event,
    side,
    n=L10_N
):

    # L10 sempre obrigatório
    n = L10_N

    if side == "home":

        team_id = event.get(
            "home_id"
        )

    else:

        team_id = event.get(
            "away_id"
        )

    if not team_id:
        return []

    team_id = str(team_id)

    all_events = []

    # --------------------------------------------------------
    # 5DOLLAR
    # --------------------------------------------------------

    if FD5_TOKEN:

        try:

            raw = fd5_team_fixtures(
                team_id
            )

            for item in raw:

                normalized = normalize_fd5_event(
                    item
                )

                if normalized:
                    all_events.append(
                        normalized
                    )

        except Exception:
            pass

    # --------------------------------------------------------
    # OPENFOOT
    # --------------------------------------------------------

    if OPENFOOT_TOKEN:

        try:

            raw = openfoot_team_matches(
                team_id
            )

            for item in raw:

                normalized = normalize_openfoot_event(
                    item
                )

                if normalized:
                    all_events.append(
                        normalized
                    )

        except Exception:
            pass

    # --------------------------------------------------------
    # THESPORTSDB
    # --------------------------------------------------------

    try:

        raw = tsdb_last(
            team_id
        )

        for item in raw:

            normalized = normalize_tsdb_event(
                item
            )

            if normalized:
                all_events.append(
                    normalized
                )

    except Exception:
        pass

    rows = make_form(
        all_events,
        team_id
    )

    return ordenar_l10(rows)


# ============================================================
# ESTATÍSTICAS L10
# ============================================================

def l10_stats(rows):

    rows = rows[:L10_N]

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
            "corners_for": 0,
            "corners_against": 0,
            "corners_total": 0,
            "yellow_for": 0,
            "yellow_against": 0,

        }

    vitorias = sum(
        r.get("result") == "V"
        for r in rows
    )

    empates = sum(
        r.get("result") == "E"
        for r in rows
    )

    derrotas = sum(
        r.get("result") == "D"
        for r in rows
    )

    gf = sum(
        safe_float(r.get("gf"))
        for r in rows
    )

    ga = sum(
        safe_float(r.get("ga"))
        for r in rows
    )

    btts = sum(
        safe_float(r.get("gf")) >= 1
        and
        safe_float(r.get("ga")) >= 1
        for r in rows
    )

    over15 = sum(
        safe_float(r.get("gf"))
        +
        safe_float(r.get("ga"))
        >= 2
        for r in rows
    )

    over25 = sum(
        safe_float(r.get("gf"))
        +
        safe_float(r.get("ga"))
        >= 3
        for r in rows
    )

    over35 = sum(
        safe_float(r.get("gf"))
        +
        safe_float(r.get("ga"))
        >= 4
        for r in rows
    )

    clean_sheets = sum(
        safe_float(r.get("ga")) == 0
        for r in rows
    )

    sem_marcar = sum(
        safe_float(r.get("gf")) == 0
        for r in rows
    )

    corners_for = sum(
        safe_float(
            r.get("corners_for")
        )
        for r in rows
    )

    corners_against = sum(
        safe_float(
            r.get("corners_against")
        )
        for r in rows
    )

    yellow_for = sum(
        safe_float(
            r.get("yellow_for")
        )
        for r in rows
    )

    yellow_against = sum(
        safe_float(
            r.get("yellow_against")
        )
        for r in rows
    )

    return {

        "jogos": jogos,

        "vitorias": vitorias,

        "empates": empates,

        "derrotas": derrotas,

        "pontos": (
            vitorias * 3
            + empates
        ),

        "gf": gf,

        "ga": ga,

        "media_gf": gf / jogos,

        "media_ga": ga / jogos,

        "btts": btts,

        "over15": over15,

        "over25": over25,

        "over35": over35,

        "under25": jogos - over25,

        "clean_sheets": clean_sheets,

        "sem_marcar": sem_marcar,

        "corners_for": corners_for,

        "corners_against": corners_against,

        "corners_total": (
            corners_for
            + corners_against
        ),

        "yellow_for": yellow_for,

        "yellow_against": yellow_against,

    }


# ============================================================
# H2H
# ============================================================

def h2h_stats(
    event,
    home_form,
    away_form,
    limit=10
):

    home_name = normalize_name(
        event.get("home")
    )

    away_name = normalize_name(
        event.get("away")
    )

    games = []

    for row in home_form:

        if normalize_name(
            row.get("opponent")
        ) == away_name:

            games.append(
                ("home", row)
            )

    for row in away_form:

        if normalize_name(
            row.get("opponent")
        ) == home_name:

            games.append(
                ("away", row)
            )

    games = games[:limit]

    if not games:

        return {

            "games": 0,
            "home_wins": 0,
            "draws": 0,
            "away_wins": 0,
            "win_rate": 0,
            "draw_rate": 0,
            "loss_rate": 0,
            "btts": 0,
            "over25": 0,
            "avg_goals": 0,

        }

    home_wins = 0
    draws = 0
    away_wins = 0
    btts = 0
    over25 = 0
    goals = 0

    for side, row in games:

        gf = safe_float(
            row.get("gf")
        )

        ga = safe_float(
            row.get("ga")
        )

        if side == "home":

            if gf > ga:
                home_wins += 1

            elif gf == ga:
                draws += 1

            else:
                away_wins += 1

        else:

            if gf > ga:
                away_wins += 1

            elif gf == ga:
                draws += 1

            else:
                home_wins += 1

        if gf >= 1 and ga >= 1:
            btts += 1

        if gf + ga >= 3:
            over25 += 1

        goals += gf + ga

    total = len(games)

    return {

        "games": total,

        "home_wins": home_wins,

        "draws": draws,

        "away_wins": away_wins,

        "win_rate": home_wins / total,

        "draw_rate": draws / total,

        "loss_rate": away_wins / total,

        "btts": btts / total,

        "over25": over25 / total,

        "avg_goals": goals / total,

    }


# ============================================================
# PREVISÃO
# ============================================================

def build_prediction(
    event,
    n=L10_N
):

    home_form = team_form(
        event,
        "home",
        L10_N
    )

    away_form = team_form(
        event,
        "away",
        L10_N
    )

    home_l10 = l10_stats(
        home_form
    )

    away_l10 = l10_stats(
        away_form
    )

    home_attack = max(
        0.05,
        home_l10["media_gf"]
    )

    away_attack = max(
        0.05,
        away_l10["media_gf"]
    )

    home_defense = max(
        0.05,
        home_l10["media_ga"]
    )

    away_defense = max(
        0.05,
        away_l10["media_ga"]
    )

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

    home_lambda *= 1.05

    difference = (
        home_l10["pontos"]
        -
        away_l10["pontos"]
    )

    adjustment = max(
        -0.20,
        min(
            0.20,
            difference / 100
        )
    )

    home_lambda += adjustment
    away_lambda -= adjustment

    home_lambda = max(
        0.05,
        home_lambda
    )

    away_lambda = max(
        0.05,
        away_lambda
    )

    probabilities = model_probs(
        home_lambda,
        away_lambda
    )

    h2h = h2h_stats(
        event,
        home_form,
        away_form
    )

    if h2h["games"] > 0:

        probabilities["1x"] = (
            probabilities["1x"] * 0.80
            +
            (
                h2h["win_rate"]
                +
                h2h["draw_rate"]
            ) * 0.20
        )

        probabilities["x2"] = (
            probabilities["x2"] * 0.80
            +
            (
                h2h["loss_rate"]
                +
                h2h["draw_rate"]
            ) * 0.20
        )

        probabilities["btts_yes"] = (
            probabilities["btts_yes"] * 0.80
            +
            h2h["btts"] * 0.20
        )

        probabilities["over25"] = (
            probabilities["over25"] * 0.80
            +
            h2h["over25"] * 0.20
        )

    confidence = sum(
        [
            probabilities["1x"],
            probabilities["x2"],
            probabilities["over15"],
            probabilities["under35"],
        ]
    ) / 4

    return {

        "home_form": home_form,

        "away_form": away_form,

        "home_l10": home_l10,

        "away_l10": away_l10,

        "h2h": h2h,

        "home_lambda": home_lambda,

        "away_lambda": away_lambda,

        "probabilities": probabilities,

        "confidence": confidence,

    }


# ============================================================
# SUGESTÕES
# ============================================================

def suggestions(pred):

    p = pred.get(
        "probabilities",
        {}
    )

    markets = [

        ("1X", p.get("1x", 0)),

        ("X2", p.get("x2", 0)),

        ("Casa", p.get("home_win", 0)),

        ("Empate", p.get("draw", 0)),

        ("Fora", p.get("away_win", 0)),

        ("BTTS Sim", p.get("btts_yes", 0)),

        ("BTTS Não", p.get("btts_no", 0)),

        ("Over 1.5", p.get("over15", 0)),

        ("Over 2.5", p.get("over25", 0)),

        ("Under 2.5", p.get("under25", 0)),

        ("Under 3.5", p.get("under35", 0)),

    ]

    result = []

    for market, probability in markets:

        probability = safe_float(
            probability
        )

        odd = (
            1 / probability
            if probability > 0
            else 0
        )

        result.append({

            "Mercado": market,

            "Probabilidade": probability,

            "Odd justa": odd,

        })

    result.sort(
        key=lambda x: x["Probabilidade"],
        reverse=True
    )

    return result[:5]


# ============================================================
# PLACAR
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
        f"{safe_float(hs):.0f}"
        "-"
        f"{safe_float(aws):.0f}"
    )


# ============================================================
# CARD
# ============================================================

def render_match_card(
    row,
    idx,
    live_mode=False
):

    pred = row.get(
        "_pred",
        {}
    )

    event = row.get(
        "_event",
        {}
    )

    home = event.get(
        "home",
        "Casa"
    )

    away = event.get(
        "away",
        "Fora"
    )

    placar = row.get(
        "Placar",
        "-"
    )

    placar_exibicao = (
        "x"
        if placar == "-"
        else placar
    )

    st.markdown(
        f"### {home}  "
        f"**{placar_exibicao}**  "
        f"{away}"
    )

    kickoff = parse_kickoff(
        event.get("kickoff")
    )

    if kickoff:

        st.caption(
            kickoff.strftime(
                "%d/%m/%Y %H:%M"
            )
            +
            " • "
            +
            event.get(
                "source",
                "-"
            )
        )

    home_l10 = pred.get(
        "home_l10",
        {}
    ) or {}

    away_l10 = pred.get(
        "away_l10",
        {}
    ) or {}

    probabilities = pred.get(
        "probabilities",
        {}
    ) or {}

    c1, c2, c3, c4 = st.columns(4)

    with c1:

        st.metric(
            "1X",
            pct(
                probabilities.get(
                    "1x",
                    0
                ) * 100
            )
        )

    with c2:

        st.metric(
            "X2",
            pct(
                probabilities.get(
                    "x2",
                    0
                ) * 100
            )
        )

    with c3:

        st.metric(
            "Over 1.5",
            pct(
                probabilities.get(
                    "over15",
                    0
                ) * 100
            )
        )

    with c4:

        st.metric(
            "BTTS",
            pct(
                probabilities.get(
                    "btts_yes",
                    0
                ) * 100
            )
        )

    st.write(
        f"**L10 Casa:** "
        f"{home_l10.get('jogos', 0)}/10"
        f" — "
        f"{home_l10.get('vitorias', 0)}V "
        f"{home_l10.get('empates', 0)}E "
        f"{home_l10.get('derrotas', 0)}D"
    )

    st.write(
        f"**L10 Fora:** "
        f"{away_l10.get('jogos', 0)}/10"
        f" — "
        f"{away_l10.get('vitorias', 0)}V "
        f"{away_l10.get('empates', 0)}E "
        f"{away_l10.get('derrotas', 0)}D"
    )

    with st.expander(
        "📊 Ver últimos 10 jogos"
    ):

        home_form = pred.get(
            "home_form",
            []
        )[:L10_N]

        away_form = pred.get(
            "away_form",
            []
        )[:L10_N]

        col1, col2 = st.columns(2)

        with col1:

            st.markdown(
                f"#### 🏠 {home}"
            )

            if home_form:

                df_home = pd.DataFrame([

                    {

                        "Data": r.get(
                            "date",
                            "-"
                        ),

                        "Adversário": r.get(
                            "opponent",
                            "-"
                        ),

                        "Placar": (
                            f"{safe_float(r.get('gf')):.0f}"
                            "-"
                            f"{safe_float(r.get('ga')):.0f}"
                        ),

                        "Resultado": r.get(
                            "result",
                            "-"
                        ),

                    }

                    for r in home_form

                ])

                st.dataframe(
                    df_home,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.warning(
                    "L10 da casa não disponível."
                )

        with col2:

            st.markdown(
                f"#### ✈️ {away}"
            )

            if away_form:

                df_away = pd.DataFrame([

                    {

                        "Data": r.get(
                            "date",
                            "-"
                        ),

                        "Adversário": r.get(
                            "opponent",
                            "-"
                        ),

                        "Placar": (
                            f"{safe_float(r.get('gf')):.0f}"
                            "-"
                            f"{safe_float(r.get('ga')):.0f}"
                        ),

                        "Resultado": r.get(
                            "result",
                            "-"
                        ),

                    }

                    for r in away_form

                ])

                st.dataframe(
                    df_away,
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.warning(
                    "L10 do visitante não disponível."
                )

    with st.expander(
        "📈 Mercados"
    ):

        data = suggestions(
            pred
        )

        if data:

            df_sug = pd.DataFrame(
                data
            )

            df_sug[
                "Probabilidade"
            ] = df_sug[
                "Probabilidade"
            ].map(
                lambda x:
                f"{x * 100:.1f}%"
            )

            df_sug[
                "Odd justa"
            ] = df_sug[
                "Odd justa"
            ].map(
                lambda x:
                f"{x:.2f}"
            )

            st.dataframe(
                df_sug,
                use_container_width=True,
                hide_index=True
            )

    st.divider()


# ============================================================
# ANALISAR PARTIDA
# ============================================================

def analyze_event(event):

    try:

        pred = build_prediction(
            event,
            L10_N
        )

        p = pred["probabilities"]

        classification = classify_event(
            event
        )

        return {

            "Jogo": (
                f"{event.get('home', 'Casa')}"
                f" x "
                f"{event.get('away', 'Fora')}"
            ),

            "Data": (
                parse_kickoff(
                    event.get("kickoff")
                ).strftime("%d/%m/%Y")
                if parse_kickoff(
                    event.get("kickoff")
                )
                else "-"
            ),

            "Hora": (
                parse_kickoff(
                    event.get("kickoff")
                ).strftime("%H:%M")
                if parse_kickoff(
                    event.get("kickoff")
                )
                else "-"
            ),

            "Status": classification,

            "Placar": display_score(
                event
            ),

            "1X": p.get(
                "1x",
                0
            ),

            "X2": p.get(
                "x2",
                0
            ),

            "Casa": p.get(
                "home_win",
                0
            ),

            "Empate": p.get(
                "draw",
                0
            ),

            "Fora": p.get(
                "away_win",
                0
            ),

            "BTTS Sim": p.get(
                "btts_yes",
                0
            ),

            "Over 1.5": p.get(
                "over15",
                0
            ),

            "Over 2.5": p.get(
                "over25",
                0
            ),

            "Under 2.5": p.get(
                "under25",
                0
            ),

            "Under 3.5": p.get(
                "under35",
                0
            ),

            "L10 Casa": (
                f"{pred['home_l10'].get('jogos', 0)}/10"
            ),

            "L10 Fora": (
                f"{pred['away_l10'].get('jogos', 0)}/10"
            ),

            "Confiança": pred.get(
                "confidence",
                0
            ),

            "_prob_num": max(
                p.get("1x", 0),
                p.get("x2", 0),
                p.get("over15", 0)
            ),

            "_pred": pred,

            "_event": event,

        }

    except Exception as e:

        return {

            "Jogo": (
                f"{event.get('home', 'Casa')}"
                f" x "
                f"{event.get('away', 'Fora')}"
            ),

            "Data": "-",

            "Hora": "-",

            "Status": "erro",

            "Placar": "-",

            "1X": 0,

            "X2": 0,

            "Casa": 0,

            "Empate": 0,

            "Fora": 0,

            "BTTS Sim": 0,

            "Over 1.5": 0,

            "Over 2.5": 0,

            "Under 2.5": 0,

            "Under 3.5": 0,

            "L10 Casa": "0/10",

            "L10 Fora": "0/10",

            "Confiança": 0,

            "_prob_num": 0,

            "_pred": {

                "home_l10": l10_stats([]),

                "away_l10": l10_stats([]),

                "home_form": [],

                "away_form": [],

                "probabilities": {},

                "confidence": 0,

                "h2h": {},

            },

            "_event": event,

            "_error": str(e),

        }


# ============================================================
# INTERFACE
# ============================================================

def main():

    st.title(
        "⚽ GLOBAL FOOTBALL SCANNER"
    )

    st.caption(
        "L10 obrigatório • Últimos 10 jogos • Ao vivo + Pré-jogo"
    )

    # --------------------------------------------------------
    # SIDEBAR
    # --------------------------------------------------------

    st.sidebar.header(
        "⚙️ Configurações"
    )

    selected_date = st.sidebar.date_input(
        "Data",
        value=datetime.now(
            BRT
        ).date()
    )

    days_to_scan = st.sidebar.slider(
        "Dias para escanear",
        min_value=1,
        max_value=4,
        value=1
    )

    st.sidebar.info(
        "O scanner utiliza os últimos "
        "10 jogos disponíveis de cada equipe."
    )

    if st.sidebar.button(
        "🔄 Atualizar",
        use_container_width=True
    ):

        st.cache_data.clear()

        st.rerun()

    # --------------------------------------------------------
    # EVENTOS
    # --------------------------------------------------------

    with st.spinner(
        "Carregando partidas..."
    ):

        events = load_global_events(
            selected_date,
            days_to_scan
        )

    st.sidebar.success(
        f"{len(events)} partidas encontradas"
    )

    if not events:

        st.warning(
            "Nenhuma partida encontrada."
        )

        st.info(
            "Verifique as APIs ou selecione outra data."
        )

        return

    # --------------------------------------------------------
    # ANALISAR
    # --------------------------------------------------------

    rows = []

    progress = st.progress(
        0
    )

    total = len(events)

    for i, event in enumerate(
        events
    ):

        rows.append(
            analyze_event(
                event
            )
        )

        progress.progress(
            (i + 1) / total
        )

    progress.empty()

    # --------------------------------------------------------
    # ABAS
    # --------------------------------------------------------

    live_tab, upcoming_tab, best_tab = st.tabs(
        [
            "🔴 AO VIVO",
            "🕐 PRÉ-JOGO",
            "⭐ MELHORES"
        ]
    )

    # --------------------------------------------------------
    # AO VIVO
    # --------------------------------------------------------

    with live_tab:

        live_rows = [

            row

            for row in rows

            if classify_event(
                row["_event"]
            ) == "live"

        ]

        if not live_rows:

            st.info(
                "Nenhuma partida ao vivo."
            )

        else:

            for idx, row in enumerate(
                live_rows
            ):

                render_match_card(
                    row,
                    idx,
                    True
                )

    # --------------------------------------------------------
    # PRÉ-JOGO
    # --------------------------------------------------------

    with upcoming_tab:

        upcoming_rows = [

            row

            for row in rows

            if classify_event(
                row["_event"]
            ) == "upcoming"

        ]

        upcoming_rows.sort(
            key=lambda x:
            x.get(
                "_prob_num",
                0
            ),
            reverse=True
        )

        if not upcoming_rows:

            st.info(
                "Nenhuma partida pré-jogo."
            )

        else:

            for idx, row in enumerate(
                upcoming_rows
            ):

                render_match_card(
                    row,
                    idx
                )

    # --------------------------------------------------------
    # MELHORES
    # --------------------------------------------------------

    with best_tab:

        best_rows = sorted(
            rows,
            key=lambda x:
            x.get(
                "_prob_num",
                0
            ),
            reverse=True
        )

        if not best_rows:

            st.info(
                "Nenhuma análise disponível."
            )

        else:

            table = []

            for row in best_rows:

                table.append({

                    "Jogo": row["Jogo"],

                    "Data": row["Data"],

                    "Hora": row["Hora"],

                    "Status": row["Status"],

                    "1X": row["1X"] * 100,

                    "X2": row["X2"] * 100,

                    "Over 1.5": (
                        row["Over 1.5"] * 100
                    ),

                    "BTTS": (
                        row["BTTS Sim"] * 100
                    ),

                    "L10 Casa": row["L10 Casa"],

                    "L10 Fora": row["L10 Fora"],

                })

            best_df = pd.DataFrame(
                table
            )

            st.dataframe(
                best_df,
                use_container_width=True,
                hide_index=True
            )

            st.divider()

            for idx, row in enumerate(
                best_rows[:20]
            ):

                render_match_card(
                    row,
                    idx
                )

    # --------------------------------------------------------
    # TABELA GERAL
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "📋 Tabela geral"
    )

    display_columns = [

        "Jogo",
        "Data",
        "Hora",
        "Status",
        "Placar",
        "1X",
        "X2",
        "Casa",
        "Empate",
        "Fora",
        "BTTS Sim",
        "Over 1.5",
        "Over 2.5",
        "Under 2.5",
        "Under 3.5",
        "L10 Casa",
        "L10 Fora",
        "Confiança",

    ]

    df = pd.DataFrame(
        rows
    )

    df_display = df[
        [
            c
            for c in display_columns
            if c in df.columns
        ]
    ].copy()

    probability_columns = [

        "1X",
        "X2",
        "Casa",
        "Empate",
        "Fora",
        "BTTS Sim",
        "Over 1.5",
        "Over 2.5",
        "Under 2.5",
        "Under 3.5",
        "Confiança",

    ]

    for col in probability_columns:

        if col in df_display:

            df_display[col] = (
                df_display[col] * 100
            )

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True
    )

    # --------------------------------------------------------
    # DOWNLOAD CSV
    # --------------------------------------------------------

    csv = df_display.to_csv(
        index=False
    ).encode(
        "utf-8-sig"
    )

    st.download_button(
        "⬇️ Baixar CSV",
        data=csv,
        file_name=(
            "scanner_football_l10.csv"
        ),
        mime="text/csv"
    )


# ============================================================
# EXECUÇÃO
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception:

        st.error(
            "❌ Ocorreu um erro no scanner."
        )

        st.code(
            traceback.format_exc(),
            language="text"
        )
