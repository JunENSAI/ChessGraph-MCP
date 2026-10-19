# ChessGraph Coach UI

React interface for the ChessGraph coaching workflow. It currently runs on
demo data; the data and coach service layers are shaped so the PostgreSQL,
Neo4j, and Stockfish MCP servers can replace them through Hermes-Agent.

The live coach will call the Hermes gateway at `HERMES_API_URL` with
`HERMES_API_KEY` from the project `.env`. That call is not implemented. The
key must stay on a local server and must not be exposed through a `VITE_`
variable.

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

**My games** — games grouped in Rapid, Blitz, Bullet, Daily, and Bot folders
(bot games carry their time control). Each game opens at its key moment with
the played move and the Stockfish alternative drawn as arrows, a navigable
move list, a 3D position graph, and a Hermes review.

**Recap** — statistics per rating band (1400–1500, 1500–1600, 1600–1700).
Each card shows its headline figure; selecting a card opens its charts:
openings with White, defenses with Black, win rate by color, endgame
patterns, and endgame win rate by color.

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
