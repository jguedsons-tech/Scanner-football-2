# Football Scanner Pro — Sportmonks

## Streamlit Cloud
1. Suba `app.py` e `requirements.txt` para um repositório GitHub.
2. Crie o app no Streamlit Cloud apontando para `app.py`.
3. Em Settings → Secrets, adicione:

```toml
SPORTMONKS_API_TOKEN = "SEU_TOKEN"
```

O app consulta Sportmonks Football v3 e calcula probabilidades por Poisson com base nos jogos recentes.
