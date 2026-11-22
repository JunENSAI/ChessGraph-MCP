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
npm test         # unit tests: clocks, evals, notation, material, strength, keys, explorer, sounds, coach transport
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

Every board view is **board first**: the board is sized to the window height,
with player bars (name, rating, clock, captured pieces and material lead), an
evaluation bar, and one tabbed side panel. On a phone the panel moves under the
board. ← → step through moves, Home/End jump, F flips. Moves, captures, checks
and castling make a short WebAudio sound (no audio files); the speaker button
mutes it and the choice is remembered in this browser.

**Play & train**

- *Play*: a new game against Stockfish with a colour, a strength
  (`src/lib/strength.ts`, sent to `POST /api/engine/play` as `UCI_Elo`; until
  you choose, the level closest to your average rating) and a time control.
  The game runs continuously: no pause after each engine move. Hint, Takeback
  (your move and the reply), Resign, Copy PGN and Explain last move are one
  click away. Leaving the view pauses a running clock.
- *Lessons*: the ranked plan from `GET /api/coach/plan` (openings, defences,
  endgames, puzzles) plus your most played openings and defences to drill.
- Tabs: Play, Moves (numbered move table), Coach, Explorer.

**My games** groups stored games into Rapid, Blitz, Bullet, Daily and Bot
folders. Each game:

- opens at its key moment, the user move with the largest stored centipawn
  loss, with the played move and the stored Stockfish move as arrows;
- shows a numbered move table with `?!` (50 cp or more), `?` (100) and `??`
  (300) from stored centipawn loss, and the mistake count for each side;
- plays the Stockfish line instead of the key move with *Better move*; the
  arrows and the table then follow that line until *Back to game*.
- Tabs: Games, Moves, Coach, Explorer.

**Explorer** (`GET /api/explorer`, Neo4j graph v2) lists the book moves, your
moves and your opponents' moves from the position on the board, with games,
score from the mover's side and your average centipawn loss, and your recent
games through the position (click one to open it). Hovering a row draws its
move on the board.

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
├── components/           board stage, board, player bars, side panel, move table, explorer, coach panel, stat card
├── views/                Home (recap), Play & train, My games
├── hooks/                chess clock, coach conversation, board keys, player profile, element size, position eval
├── lib/                  clock rules, chess.js helpers, evals, notation, material, strength, keys, explorer rows, sounds, stats
├── services/             coach transport, Stockfish calls through /api/engine, explorer reads
└── data/                 API reads (games, lessons, plan, recap) and their types
```

## Libraries

| Package | Role |
| --- | --- |
| `react-chessboard` + `chess.js` | Board rendering, drag and click moves, legality |
| `thinking-orbs` | Coach activity indicator |
| `recharts` | Recap charts |
| `motion` | Mode, folder, and card transitions |
| `lucide-react` | Icons |

The recap charts load as a separate chunk on first use. There is no WebGL dependency.
