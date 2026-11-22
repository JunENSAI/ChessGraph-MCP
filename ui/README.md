# ChessGraph Coach UI

React interface for the ChessGraph coaching workflow. Every panel reads live
data from the FastAPI retrieval API in `backend/`. The Vite dev and preview
servers proxy `/api` to `BACKEND_URL` (default `http://127.0.0.1:8000`). There
is no demo or sample data in the interface.

The coach panel posts to `POST /api/coach/chat` and reads the answer as a
server-sent event stream (`src/services/coach.ts`).

- The text appears as it arrives.
- The Games, Graph and Stockfish chips light up as each tool runs: green when
  it answered, struck through when it failed.
- The header says whether Claude or the offline evidence mode answered.

The model key lives only in the API process. Never expose a key through a
`VITE_` variable. `npm run build` emits static files only, so a
production deployment needs its own reverse proxy for `/api`.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
npm test         # unit tests: clocks, evals, results, plan, recap, lessons, coach transport
npm run lint     # oxlint
npm run build    # type-check and production bundle
```

## Modes

**Home** (the default tab) is the rating-band recap from `GET /api/recap`.

- Pick a band and the charts recompute. Each card opens into the chart and
  table behind it.
- Cards cover White lines, Black lines, win rate by colour, and results by
  time control.
- The favourite line in a band is the stored opening name with the most games.
- Endgame types are not stored on games, so the recap does not invent them.

**Training** shows the ranked plan from `GET /api/coach/plan`.

- Each item is an opening, a defence, an endgame or a puzzle task. It carries
  the reason it was chosen and the line to drill.
- You can also play a full game against Stockfish (`POST /api/engine/analyze`)
  from either colour.

**My games** groups stored games into Rapid, Blitz, Bullet, Daily and Bot
folders. Each game:

- opens at its key moment, the user move with the largest stored centipawn
  loss;
- draws the played move and the stored Stockfish alternative as arrows;
- has a navigable move list, a position graph, and the coach beside the board.

## Chess clock

`src/lib/clock.ts` keeps the clocks honest:

- It stores remaining time only at turn boundaries and derives the live value
  from `performance.now()`, so throttled timers or a background tab cannot
  make it drift.
- The first move starts the opponent's clock without an increment. Later moves
  credit the increment to the mover.
- Reaching zero flags that side and locks the board.

`src/lib/clock.test.ts` covers these rules.

## Structure

```text
src/
├── App.tsx               mode switch; views stay mounted to keep state
├── components/           board, player bars, coach panel, position graph, stat card
├── views/                Home (recap), Training, My games
├── hooks/                chess clock, coach conversation, element size, position eval
├── lib/                  clock rules, chess.js helpers, evals, graph builder, stats
├── services/             coach transport and Stockfish calls through /api/engine
└── data/                 API reads (games, lessons, plan, recap) and their types
```

## Libraries

| Package | Role |
| --- | --- |
| `react-chessboard` + `chess.js` | Board rendering, drag and click moves, legality |
| `react-force-graph-3d` + `three` + `three-spritetext` | Position graph with move labels |
| `thinking-orbs` | Coach activity indicator |
| `recharts` | Recap charts |
| `motion` | Mode, folder, and card transitions |
| `lucide-react` | Icons |

The graph and the recap charts load as separate chunks on first use.
