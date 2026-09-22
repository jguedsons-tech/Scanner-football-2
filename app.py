# ============================================================
# CARD DO JOGO — CORRIGIDO
# ============================================================

def render_match_card(
    row,
    idx,
    live_mode=False
):

    pred = row["_pred"]

    ev = row["_event"]

    # ========================================================
    # PLACAR
    # ========================================================

    placar = row.get(
        "Placar",
        "-"
    )

    if placar == "-":
        placar_exibicao = "x"
    else:
        placar_exibicao = placar

    # CORREÇÃO DO ERRO DE F-STRING
    title = (
        f"{ev.get('home', 'Casa')}  "
        f"{placar_exibicao}  "
        f"{ev.get('away', 'Fora')}"
    )

    status_icon = (
        "🟢"
        if live_mode
        else
        "🔵"
    )

    # ========================================================
    # L10
    # ========================================================

    home_l10 = (
        pred.get("home_l10")
        or {}
    )

    away_l10 = (
        pred.get("away_l10")
        or {}
    )

    home_form = (
        pred.get("home_form")
        or []
    )

    away_form = (
        pred.get("away_form")
        or []
    )

    # ========================================================
    # CARD
    # ========================================================

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
                f"{row.get('Liga', '-')} • "
                f"{row.get('Horário BRT', '-')} • "
                f"Fonte: {row.get('Fonte', '-')}"
            )

        with c2:

            st.metric(
                "Melhor opção",
                row.get(
                    "Sugestão",
                    "-"
                ),
                row.get(
                    "Prob.",
                    "-"
                )
            )

        with c3:

            st.metric(
                "Confiança",
                row.get(
                    "Confiança",
                    "-"
                )
            )

        # ====================================================
        # MERCADOS
        # ====================================================

        b1, b2, b3, b4, b5 = st.columns(5)

        b1.metric(
            "Casa",
            row.get(
                "Casa",
                "-"
            )
        )

        b2.metric(
            "Empate",
            row.get(
                "Empate",
                "-"
            )
        )

        b3.metric(
            "Fora",
            row.get(
                "Fora",
                "-"
            )
        )

        b4.metric(
            "BTTS",
            row.get(
                "BTTS",
                "-"
            )
        )

        b5.metric(
            "O2.5",
            row.get(
                "O2.5",
                "-"
            )
        )

        # ====================================================
        # L10
        # ====================================================

        st.markdown(
            "## 📊 L10 — Últimos 10 jogos"
        )

        home_games = home_l10.get(
            "jogos",
            0
        )

        away_games = away_l10.get(
            "jogos",
            0
        )

        if home_games < 10:

            st.warning(
                f"⚠️ {ev.get('home', 'Casa')}: "
                f"{home_games}/10 jogos encontrados. "
                f"O sistema não inventa os jogos faltantes."
            )

        if away_games < 10:

            st.warning(
                f"⚠️ {ev.get('away', 'Fora')}: "
                f"{away_games}/10 jogos encontrados. "
                f"O sistema não inventa os jogos faltantes."
            )

        # ====================================================
        # CASA — L10
        # ====================================================

        st.markdown(
            f"### 🏠 "
            f"{ev.get('home', 'Casa')} — L10"
        )

        hcols = st.columns(8)

        hcols[0].metric(
            "J",
            home_l10.get(
                "jogos",
                0
            )
        )

        hcols[1].metric(
            "V",
            home_l10.get(
                "vitorias",
                0
            )
        )

        hcols[2].metric(
            "E",
            home_l10.get(
                "empates",
                0
            )
        )

        hcols[3].metric(
            "D",
            home_l10.get(
                "derrotas",
                0
            )
        )

        hcols[4].metric(
            "P",
            home_l10.get(
                "pontos",
                0
            )
        )

        hcols[5].metric(
            "GF",
            int(
                home_l10.get(
                    "gf",
                    0
                )
            )
        )

        hcols[6].metric(
            "GA",
            int(
                home_l10.get(
                    "ga",
                    0
                )
            )
        )

        hcols[7].metric(
            "Média GF",
            f"{home_l10.get('media_gf', 0):.2f}"
        )

        # ====================================================
        # OUTRAS ESTATÍSTICAS CASA
        # ====================================================

        hc1, hc2, hc3, hc4, hc5, hc6 = st.columns(6)

        hc1.metric(
            "BTTS",
            f"{home_l10.get('btts', 0)}/"
            f"{home_games}"
        )

        hc2.metric(
            "Over 1.5",
            f"{home_l10.get('over15', 0)}/"
            f"{home_games}"
        )

        hc3.metric(
            "Over 2.5",
            f"{home_l10.get('over25', 0)}/"
            f"{home_games}"
        )

        hc4.metric(
            "Over 3.5",
            f"{home_l10.get('over35', 0)}/"
            f"{home_games}"
        )

        hc5.metric(
            "Clean Sheet",
            f"{home_l10.get('clean_sheets', 0)}/"
            f"{home_games}"
        )

        hc6.metric(
            "Sem marcar",
            f"{home_l10.get('sem_marcar', 0)}/"
            f"{home_games}"
        )

        st.caption(
            f"⚽ Gols: "
            f"{home_l10.get('media_gf', 0):.2f} "
            f"marcados | "
            f"{home_l10.get('media_ga', 0):.2f} "
            f"sofridos"
        )

        # ====================================================
        # ESCANTEIOS CASA
        # ====================================================

        if home_l10.get(
            "corners_for"
        ) is not None:

            st.caption(
                f"🚩 Escanteios: "
                f"{home_l10['corners_for']:.2f} "
                f"a favor | "
                f"{home_l10['corners_against']:.2f} "
                f"contra | "
                f"{home_l10['corners_total']:.2f} "
                f"total"
            )

        # ====================================================
        # CARTÕES CASA
        # ====================================================

        if home_l10.get(
            "yellow_for"
        ) is not None:

            st.caption(
                f"🟨 Cartões: "
                f"{home_l10['yellow_for']:.2f} "
                f"por jogo"
            )

        # ====================================================
        # FORA — L10
        # ====================================================

        st.markdown(
            f"### ✈️ "
            f"{ev.get('away', 'Fora')} — L10"
        )

        acols = st.columns(8)

        acols[0].metric(
            "J",
            away_l10.get(
                "jogos",
                0
            )
        )

        acols[1].metric(
            "V",
            away_l10.get(
                "vitorias",
                0
            )
        )

        acols[2].metric(
            "E",
            away_l10.get(
                "empates",
                0
            )
        )

        acols[3].metric(
            "D",
            away_l10.get(
                "derrotas",
                0
            )
        )

        acols[4].metric(
            "P",
            away_l10.get(
                "pontos",
                0
            )
        )

        acols[5].metric(
            "GF",
            int(
                away_l10.get(
                    "gf",
                    0
                )
            )
        )

        acols[6].metric(
            "GA",
            int(
                away_l10.get(
                    "ga",
                    0
                )
            )
        )

        acols[7].metric(
            "Média GF",
            f"{away_l10.get('media_gf', 0):.2f}"
        )

        # ====================================================
        # OUTRAS ESTATÍSTICAS FORA
        # ====================================================

        ac1, ac2, ac3, ac4, ac5, ac6 = st.columns(6)

        ac1.metric(
            "BTTS",
            f"{away_l10.get('btts', 0)}/"
            f"{away_games}"
        )

        ac2.metric(
            "Over 1.5",
            f"{away_l10.get('over15', 0)}/"
            f"{away_games}"
        )

        ac3.metric(
            "Over 2.5",
            f"{away_l10.get('over25', 0)}/"
            f"{away_games}"
        )

        ac4.metric(
            "Over 3.5",
            f"{away_l10.get('over35', 0)}/"
            f"{away_games}"
        )

        ac5.metric(
            "Clean Sheet",
            f"{away_l10.get('clean_sheets', 0)}/"
            f"{away_games}"
        )

        ac6.metric(
            "Sem marcar",
            f"{away_l10.get('sem_marcar', 0)}/"
            f"{away_games}"
        )

        st.caption(
            f"⚽ Gols: "
            f"{away_l10.get('media_gf', 0):.2f} "
            f"marcados | "
            f"{away_l10.get('media_ga', 0):.2f} "
            f"sofridos"
        )

        # ====================================================
        # ESCANTEIOS FORA
        # ====================================================

        if away_l10.get(
            "corners_for"
        ) is not None:

            st.caption(
                f"🚩 Escanteios: "
                f"{away_l10['corners_for']:.2f} "
                f"a favor | "
                f"{away_l10['corners_against']:.2f} "
                f"contra | "
                f"{away_l10['corners_total']:.2f} "
                f"total"
            )

        # ====================================================
        # CARTÕES FORA
        # ====================================================

        if away_l10.get(
            "yellow_for"
        ) is not None:

            st.caption(
                f"🟨 Cartões: "
                f"{away_l10['yellow_for']:.2f} "
                f"por jogo"
            )

        # ====================================================
        # 10 JOGOS EXATOS
        # ====================================================

        with st.expander(
            "📋 Ver os jogos usados no L10",
            expanded=False
        ):

            def tabela_l10(
                rows
            ):

                data = []

                for i, r in enumerate(
                    rows[:L10_N],
                    1
                ):

                    gf = safe_float(
                        r.get(
                            "gf"
                        ),
                        0
                    )

                    ga = safe_float(
                        r.get(
                            "ga"
                        ),
                        0
                    )

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
                                f"{int(gf)}"
                                f"-"
                                f"{int(ga)}"
                            ),

                        "Resultado":
                            r.get(
                                "result",
                                "-"
                            ),

                        "GF":
                            gf,

                        "GA":
                            ga
                    })

                return pd.DataFrame(
                    data
                )

            # =================================================
            # CASA
            # =================================================

            st.markdown(
                f"**🏠 {ev.get('home', 'Casa')} — "
                f"{len(home_form[:L10_N])}/10 jogos**"
            )

            if home_form:

                st.dataframe(
                    tabela_l10(
                        home_form
                    ),
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "Nenhum jogo histórico "
                    "encontrado para este time."
                )

            # =================================================
            # FORA
            # =================================================

            st.markdown(
                f"**✈️ {ev.get('away', 'Fora')} — "
                f"{len(away_form[:L10_N])}/10 jogos**"
            )

            if away_form:

                st.dataframe(
                    tabela_l10(
                        away_form
                    ),
                    use_container_width=True,
                    hide_index=True
                )

            else:

                st.info(
                    "Nenhum jogo histórico "
                    "encontrado para este time."
                )

        # ====================================================
        # AO VIVO
        # ====================================================

        if live_mode:

            if ev.get(
                "minute"
            ) is not None:

                st.caption(
                    f"⏱️ Minuto: "
                    f"{ev.get('minute')} "
                    f"| Placar: "
                    f"{row.get('Placar', '-')}"
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

                if ev.get(
                    key
                ) is not None:

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
        # ANÁLISE COMPLETA
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
                    f"{row.get('BTTS', '-')} "
                    f"| Over 2.5: "
                    f"{row.get('O2.5', '-')} "
                    f"| Under 3.5: "
                    f"{row.get('U3.5', '-')}"
                )

                st.write(
                    f"H2H analisados: "
                    f"{row.get('H2H', 0)}"
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

            # =================================================
            # H2H
            # =================================================

            h = (
                pred.get("h2h")
                or {}
            )

            if h.get(
                "games"
            ):

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
