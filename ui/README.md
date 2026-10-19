# ChessGraph Coach UI

React interface for the ChessGraph coaching workflow. It currently runs on
demo data; the data and coach service layers are shaped so the PostgreSQL,
Neo4j, and Stockfish MCP servers can replace them through Hermes-Agent.

The live coach calls the Hermes gateway. The browser posts to the same-origin
path `/hermes-api/chat/completions`; the Vite dev and preview servers proxy that
to `HERMES_API_URL` and add the `HERMES_API_KEY` bearer header themselves, so the
key never reaches the browser or the bundle. It must never be exposed through a
`VITE_` variable.

The key must equal `API_SERVER_KEY` in `~/.hermes/.env`, and the gateway must be
running (`hermes gateway status`) with the API server enabled
(`platforms.api_server.enabled: true`). `npm run build` emits static files only,
so a production deployment needs its own reverse proxy for `/hermes-api`.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm test         # clock logic and demo-data legality
npm run build    # type-check and production bundle
npm run lint
```

## Modes

**Training** — move-by-move lessons for openings (Italian Game), defenses
(Caro-Kann), and endgames (Lucena). A lesson accepts only its line, plays the
partner's reply, and has Hermes explain each step. Free play moves both sides
and is the quickest way to try every time control.

Lesson lines and the game library still come from `src/data/demo.ts`. Hermes
answers questions from the real MCP evidence; the board content around it is
not yet loaded from PostgreSQL.

**My games** — games grouped in Rapid, Blitz, Bullet, Daily, and Bot folders
(bot games carry their time control). Each game opens at its key moment with
the played move and the Stockfish alternative drawn as arrows, a navigable
move list, a 3D position graph, and a Hermes review.

**Recap** — rating bands from `GET /api/recap`. Vite proxies that path to the
FastAPI process (`BACKEND_URL`, default `http://127.0.0.1:8000`). The headline
on each opening card is the stored line with the most games in that band.
Cards cover White lines, Black lines, win rate by color, and results by time
control. Endgame types are not stored on the games, so the recap does not
invent them.

## Chess clock

`src/lib/clock.ts` stores remaining time only at turn boundaries and derives
the live value from `performance.now()`. Throttled timers or a background tab
therefore cannot make the clock drift. The first move starts the opponent's
clock without an increment; later moves credit the increment to the mover;
reaching zero flags that side and locks the board. `src/lib/clock.test.ts`
covers these rules.

## Structure

```text
src/
├── App.tsx               mode switch; views stay mounted to keep state
├── components/           board, player bars, Hermes panel, 3D graph, stat card
├── views/                Training, My games, Recap
├── hooks/                chess clock, coach conversation, element size
├── lib/                  clock rules, chess.js helpers, graph builder, stats
├── services/coach.ts     demo Hermes transport (HERMES_API_URL / HERMES_API_KEY later)
└── data/                 types and demo content
```

## Libraries

| Package | Role |
| --- | --- |
| `react-chessboard` + `chess.js` | Board rendering, drag and click moves, legality |
| `react-force-graph-3d` + `three` + `three-spritetext` | 3D position graph with move labels |
| `thinking-orbs` | Hermes activity indicator |
| `recharts` | Recap charts |
| `motion` | Mode, folder, and card transitions |
| `lucide-react` | Icons |

The 3D graph and the recap charts load as separate chunks on first use.
