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

## Modo LIVE (compra real na Polymarket)

> ⚠️ **IRREVERSÍVEL.** Lê isto inteiro antes de tentar.

O executor live usa `py-clob-client`, assina ordens com a sua wallet e posta na
CLOB. Por design o bot **se recusa a subir em LIVE** sem todas as travas abaixo.

### Pré-requisitos

1. **Rotacione a wallet** — qualquer chave privada que tenha aparecido em chat,
   commit, log ou screenshot está QUEIMADA. Crie uma carteira nova (Magic.link
   na própria UI Polymarket, ou hardware wallet) e mova fundos pra ela.
2. **Gere novas API creds** no painel Polymarket pra essa wallet nova.
3. Preencha `.env`:
   ```
   MODE=live
   PRIVATE_KEY=<wallet nova, NUNCA exposta>
   WALLET_ADDRESS=<endereço da wallet nova>
   FUNDER_ADDRESS=<idem se for proxy wallet, ou EOA>
   POLY_API_KEY=...
   POLY_SECRET=...
   POLY_PASSPHRASE=...
   SIGNATURE_TYPE=2          # 1 se for EOA, 2 se for proxy wallet (UI Polymarket)
   MAX_LOT_USD=1.0           # cap por ordem; comece com $0.50–$1.00
   MIN_EDGE=0.15             # exige 15% de edge sobre o ask
   LIVE_CONFIRM=I_HAVE_ROTATED_THE_LEAKED_KEY
   ```
4. Rode `./run.sh`. Se `LIVE_CONFIRM` faltar, o processo aborta no boot.

### Como ele compra

- Discovery acha mercados de clima ativos (parser cobre `be N°`, `or below`,
  `or above`, `between A-B°`).
- Forecast poller pega previsão OWM da cidade pra hora de resolução.
- Edge engine calcula `P(temp ∈ bucket | forecast)` com `Normal(μ, σ)`.
- Se `edge ≥ MIN_EDGE` e risk manager aprova, executor:
  1. Calcula `size = MAX_LOT_USD / price` (notional capado).
  2. Chama `client.post_order(GTC BUY)` via `py-clob-client`.
  3. Registra a posição em paper-shadow no DB (pra dashboard mostrar).
- Mesma arquitetura das ordens que você viu (Buy YES @ 5¢, $0.06–$5).

### Travas de segurança

- `LIVE_CONFIRM` precisa ser exatamente `I_HAVE_ROTATED_THE_LEAKED_KEY`.
- `MAX_LOT_USD` capa cada ordem (não dá pra estourar acidentalmente).
- `MAX_OPEN_POSITIONS` capa exposição simultânea.
- `DAILY_LOSS_LIMIT` para trading se atingir realized loss no dia.
- Risk manager rejeita duplicar posição mesmo mercado/side.

### Kill switch

```bash
# para tudo:
pkill -f "app.main"
```

(roadmap: endpoint `POST /api/control/flatten` que cancela ordens abertas)

## Próximos passos

1. ~~Live executor~~ ✓
2. **TimescaleDB** — substituir SQLite quando volume de ticks crescer.
3. **Backtester real** — replay sobre `forecast_snapshots` × `price_ticks`.
4. **Telegram/Discord** — alertas por evento `signal_taken` / kill-switch.
5. **Painel de config** — editar `MIN_EDGE`/`TRADE_SIZE` em runtime.
6. **Cancel/flatten** — endpoint pra cancelar todas as ordens abertas.
