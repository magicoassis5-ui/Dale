# Dale — Polymarket Weather Bot

Bot de trading automatizado para mercados de clima da Polymarket com dashboard
em tempo real estilo terminal.

> ⚠️ **Segurança:** o repositório nunca contém chaves privadas nem secrets.
> O `.env` é local e está no `.gitignore`. **Rotacione qualquer credencial que
> tenha sido compartilhada em chat.**

## Stack

- **Backend:** FastAPI (Python 3.11+) + SQLAlchemy async + SQLite
- **Frontend:** HTML + CSS + JS vanilla servidos pelo próprio FastAPI
- **Realtime:** WebSocket nativo do FastAPI (`/ws`)
- **HTTP egress:** httpx, com suporte a proxy autenticado (DataImpulse etc.)
- **DB:** SQLite por padrão; troque `DB_URL` pra Postgres+Timescale em produção

## Instalação rápida

```bash
cd dale
chmod +x run.sh
./run.sh
```

Abra `http://localhost:8000`.

O `run.sh` cria `.venv`, instala deps, cria `data/` e sobe o servidor.

## Modos

Configure via `MODE` no `.env`:

| MODE  | O que faz                                                            |
|-------|----------------------------------------------------------------------|
| demo  | Sintetiza 20 mercados de clima e simula drift de preço. Default.     |
| paper | Conecta na Polymarket Gamma + OWM, gera sinais reais, **não executa**. |
| live  | Igual `paper`, mas executa ordens (requer `py-clob-client` + wallet). |

> O modo `live` está stubbed — o caminho de assinatura EIP-712 + `py-clob-client`
> precisa ser ativado antes de operar com dinheiro real. Não use sem ler.

## .env

Copie `.env.example` pra `.env` e preencha. Campos relevantes:

```
MODE=demo
PROXY_URL=http://USER:PASS@HOST:PORT     # opcional
OWM_API_KEY=...                          # necessário pro modo paper/live
TRADE_SIZE=5.0
MIN_EDGE=0.15
DAILY_LOSS_LIMIT=50
BANKROLL=242
```

Wallet/CLOB são lidos do `.env` mas **só usados no modo live** (que ainda é stub).

## Estrutura

```
app/
├── main.py              # FastAPI bootstrap, lifespan, workers
├── config.py            # Settings via pydantic-settings
├── db.py                # Tabelas + engine async (SQLite)
├── events.py            # Pub/sub interno pra WebSocket
├── proxy.py             # Factory de httpx com proxy
├── core/
│   ├── polymarket.py    # Gamma + CLOB book (REST)
│   ├── owm.py           # OpenWeatherMap forecast
│   ├── edge.py          # P(temp ≥ thr) + escolha YES/NO
│   ├── risk.py          # Limites: max open, daily loss, dedupe
│   └── pnl.py           # Mark-to-market e métricas
├── workers/
│   ├── demo.py             # synthesizer pra MODE=demo
│   ├── market_discovery.py # busca mercados de clima ativos
│   ├── forecast_poller.py  # poll OWM por cidade
│   ├── orderbook_streamer.py # poll do CLOB book
│   ├── signal_engine.py    # calcula edge e dispara executor
│   ├── executor.py         # paper trade (open/close)
│   └── resolver.py         # fecha posições na resolução
├── api/
│   ├── routes.py        # REST (/api/summary, positions, etc.)
│   └── ws.py            # /ws push de eventos
└── static/              # HTML/CSS/JS do dashboard
```

## API

```
GET  /api/summary            header + métricas
GET  /api/positions/open     posições abertas
GET  /api/positions/closed   histórico
GET  /api/markets/active     mercados que o bot monitora
GET  /api/signals            últimos sinais
GET  /api/backtest/last      placeholder do banner
GET  /api/config             estado da config (mascarado)
WS   /ws                     eventos: tick, position_opened, ...
```

## Próximos passos

1. **Live executor** — integrar `py-clob-client`, assinatura EIP-712, retry/backoff.
2. **TimescaleDB** — substituir SQLite quando volume de ticks crescer.
3. **Backtester real** — replay sobre `forecast_snapshots` × `price_ticks`.
4. **Telegram/Discord** — alertas por evento `signal_taken` / kill-switch.
5. **Painel de config** — editar `MIN_EDGE`/`TRADE_SIZE` em runtime.
