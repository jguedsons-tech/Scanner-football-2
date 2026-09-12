# ⚽ Global Football Scanner — Free Sources (v3)

Scanner Streamlit para descoberta global de partidas e estimativas estatísticas.

## Fontes

1. **TheSportsDB** — descoberta global de jogos e histórico básico.
2. **football-data.org** — opcional; complementa resultados/competições cobertas pelo plano gratuito.
3. **5DollarFootballAPI** — opcional; o plano gratuito atual oferece cobertura das cinco grandes ligas europeias e dados de gols, escanteios, cartões, fixtures por equipe e estatísticas de jogo.

A terceira fonte é especialmente útil para tentar preencher **últimos 10 jogos, escanteios e cartões**. Fora da cobertura gratuita, o app mantém as outras fontes e deixa os campos sem dados como indisponíveis.

## Secrets no Streamlit Cloud

Abra **Settings → Secrets** e adicione as chaves que possuir:

```toml
FOOTBALL_DATA_API_TOKEN = "SUA_CHAVE_FOOTBALL_DATA"
FIVEDOLLAR_FOOTBALL_API_KEY = "SUA_CHAVE_5DOLLAR"
THESPORTSDB_API_KEY = "123"
```

O app continua abrindo sem as duas chaves opcionais, usando TheSportsDB.

## O que o scanner calcula

- 1X2
- Dupla chance 1X / X2
- BTTS
- Over/Under 0.5, 1.5, 2.5, 3.5 e 4.5
- Últimos 3–10 jogos
- Forma W/D/L
- Médias de gols marcados/sofridos
- Escanteios médios quando disponíveis
- Cartões amarelos médios quando disponíveis
- Confiança do modelo baseada na disponibilidade de histórico
- Ranking das sugestões
- Exportação CSV

## Instalação local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Observação sobre probabilidades

O modelo usa médias recentes e uma distribuição de Poisson para estimar probabilidades. Não há garantia de 95% de acerto nem de lucro. Quando uma estatística não está disponível na fonte, o app não transforma um valor inventado em estatística oficial.


## OpenFootAPI
Adicionado como quarta fonte opcional/global. Configure `OPENFOOT_API_KEY` nos Secrets do Streamlit Cloud. A chave Starter gratuita fornece acesso ao catálogo global, fixtures, resultados, standings e busca; endpoints avançados como eventos/xG podem exigir plano superior.
