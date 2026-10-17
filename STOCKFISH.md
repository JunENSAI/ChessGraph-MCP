# Stockfish

Assumed that you have installed stockfish on your Computer. **Stockfish** is an open source chess engine that is the most advanced in terms of chess elo evaluation. Stockfish will serve to analyze a chess move according to a define position but it is just an engine. Not like the LLM architecture that generate text or other stuff stockfish only provide chess move without explaining them because it doesn't aim to generate textual interpretation of why it's considere this move more that other move.

## Purpose

This note extracts the main concepts and formulas needed to understand how Stockfish evaluates chess positions. It focuses on the NNUE evaluator described in the [official Stockfish NNUE documentation](https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/nnue.html). It is a conceptual reference for an analysis agent, not a full implementation guide.

## The mental model

Stockfish combines **position evaluation** with **tree search**:

1. Represent the board as active input features.

2. Run the NNUE network to estimate the position's value.

3. Search candidate move sequences and use evaluations to compare resulting positions.

4. Return a best move, a score, and often a principal variation (PV): a candidate line of play.

**Important:** NNUE is the evaluator, not the whole engine. A score returned after a search is influenced by the searched continuations, search depth, available time, and engine settings; it is not simply a human-readable summary of the current board.

## NNUE

**NNUE** stands for *Efficiently Updatable Neural Network*. Its defining idea is that a chess move changes only a small part of the board representation. Rather than recomputing an expensive part of the network after every move, Stockfish can update it incrementally.

The design is built around three principles:

- **Sparse inputs:** only a small subset of all possible features is active in a position.

- **Incremental updates:** most moves change only a small number of active features.

- **Fast inference:** a relatively shallow network and low-precision integer arithmetic make evaluation efficient on CPUs.

## Board features: HalfKP

The documented HalfKP feature set represents each feature as a tuple:

$$
f = (s_{K}, s_{p}, t_{p}, c_{p})
$$

where:

- $s_K$: square occupied by the king belonging to the current perspective;

- $s_p$: square occupied by another piece;

- $t_p$: piece type (pawn, knight, bishop, rook, or queen; the king is excluded in HalfKP);

- $c_p$: piece color, represented relative to that perspective.

There are 64 squares, 5 non-king piece types, and 2 colors, so the documented HalfKP feature count is:

$$
N = 64 \times 64 \times 5 \times 2 = 40{,}960
$$

This is the **number of possible features**, not the number active in every position. A position activates only the features corresponding to its actual pieces. The king square is part of the feature, allowing the network to learn how piece placement relates to king location.

Stockfish maintains a representation for **both perspectives**. For the side-specific view, board squares and colors are oriented consistently, so the network can learn similar patterns without needing to treat White and Black as unrelated cases.

## The accumulator: the key efficiency trick

The first linear layer maps active features to a vector called the **accumulator**. Let:

- $F_p$ be the set of active feature indices for perspective $p$;

- $b$ be the first layer's bias vector;

- $W_f$ be the weight vector associated with feature $f$.

The accumulator is:

$$
A_p = b + \sum_{f \in F_p} W_f
$$

Because the input features are binary, the implementation only needs to add the vectors for active features; it does not need to process every possible feature.

### Incremental update after a move

Let $R$ be the removed features and $G$ the added features. Then:

$$
A'_p = A_p - \sum_{f \in R} W_f + \sum_{f \in G} W_f
$$

Conceptually:

- a piece moving removes its old-square feature and adds its new-square feature;
- a captured piece removes its feature;

- a promotion changes the relevant piece-type features;

- when the perspective's king moves, the king square changes in every HalfKP feature, so that perspective generally requires a full accumulator refresh.

The accumulator avoids rebuilding the whole feature-transform calculation for most moves. This is especially useful because search evaluates many related positions in succession.

## From accumulator to score

The exact deployed network dimensions can change between network versions. The official documentation uses a representative structure consisting of a feature transformer, clipped activations, a small dense layer, and a final scalar output.

### Linear layer

A fully connected layer applies:

$$
y = Wx + b
$$

where $x$ is the input vector, $W$ is the learned weight matrix, and $b$ is a bias vector.

### Clipped ReLU activation

The documented ClippedReLU activation is:

$$
\operatorname{CReLU}(x) = \min(\max(x, 0), 1)
$$

It introduces non-linearity and constrains activations to the range $[0,1]$, which also supports efficient quantized inference.

### Simplified forward pass

Let $A_{stm}$ be the accumulator for the side to move and $A_{other}$ the opponent's accumulator. A conceptual forward pass is:

$$
x = [\operatorname{CReLU}(A_{stm});\ \operatorname{CReLU}(A_{other})]
$$

$$
h = \operatorname{CReLU}(W_1 x + b_1)
$$

$$
s = W_2 h + b_2
$$

Here, $[a;b]$ means concatenation. This illustrates the processing flow in the documentation; it is **not a guarantee of the exact dimensions or every layer in the current production network**. The network produces one scalar, trained to represent a position score or a value proportional to that score.

## Evaluation Score

### Static evaluation versus search score

- **Static NNUE evaluation:** the network's learned estimate of a position's value.

- **Search result:** the engine's assessment after exploring possible continuations and comparing their outcomes. This is the more useful result when asking which move to play.

An evaluation is not just a material count. The network learns patterns from training data and can represent interacting positional factors. Its weights are not a simple table of human-readable rules, and a single neuron's value should not be interpreted as a standalone chess concept.

### Centipawns and mate scores

Stockfish commonly reports a score in UCI output as either:

- `score cp X`: a centipawn-scale score; 100 centipawns are conventionally about one pawn unit;

- `score mate N`: a reported mate distance, where the sign and distance indicate which side is expected to give or receive mate under the engine's reporting convention.

Centipawns are an evaluation scale, **not a direct probability of winning**. They also do not mean the position is guaranteed to reach a particular result. Score values can change with search depth, time, settings, and the available information.

If WDL output is enabled, Stockfish can also report estimated win/draw/loss figures. These are calibrated estimates under particular engine-testing conditions, not universal real-world probabilities.

## Why NNUE is fast

The main performance choices are connected:

| Design choice | Why it helps |
|---|---|
| Sparse feature vector | The first layer processes active features rather than every possible feature. |
| Incremental accumulator | Most moves update only the features that changed. |
| Shallow network | Limits the work needed after the feature transformer. |
| Quantization | Uses low-precision integer arithmetic for faster CPU inference and smaller model storage. |
| Small changes between positions | Makes reuse of prior calculation effective during tree search. |

Quantization maps model values from floating point to lower-precision integer representations. It introduces approximation error, so the chosen ranges and scaling must balance numerical safety, speed, and evaluation quality.

## Guidance for a chess-analysis agent

### Treat Stockfish as the evaluation/search authority

For practical analysis, call Stockfish through its UCI interface instead of attempting to reproduce NNUE scores from the formulas above. The `.nnue` file contains learned parameters; the equations explain the structure, not enough information to recreate the trained network or Stockfish's full search.

Useful fields to retain from each analysis include:

- **Position identity:** FEN, side to move, and move history when available.

- **Recommended move:** `bestmove`.

- **Evaluation:** `score cp` or `score mate`.

- **Search context:** `depth`, `seldepth`, `nodes`, `time`, and `nps` where available.

- **Principal variation:** `pv`, the engine's main candidate continuation.

- **Optional WDL:** estimated win/draw/loss output when enabled.

### Comparing two positions or moves

1. Use comparable search limits (for example, the same depth or time budget).

2. Normalize score perspective before comparing values across positions; do not assume that raw scores from different libraries or interfaces use the same perspective.

3. Retain the search depth and limits alongside the score.
4. Treat a small score change at shallow depth as uncertain rather than as definitive evidence of a blunder or improvement.

5. Prefer the PV and the position's tactical context over interpreting a centipawn number in isolation.

6. Treat mate scores separately from ordinary centipawn scores.

For a move-quality dataset, keep the **position before the move**, the played move, the engine's best move, evaluation under a consistent analysis configuration, and the relevant PV. This separates the engine's assessment from the player's actual decision.

## Scope and interpretation limits

These limits distinguish what the NNUE documentation explains from what an analysis agent must obtain elsewhere or infer carefully.

1. **The NNUE page is not a complete specification of Stockfish's search algorithm.** Its stated scope is NNUE principles, network components, inference, quantization, training, and architectures. This is a boundary of the document's scope, rather than a sentence quoted verbatim from it. See the [NNUE documentation](https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/nnue.html) and the separate [UCI Protocol and Stockfish Commands documentation](https://official-stockfish.github.io/docs/stockfish-wiki/UCI-Protocol-and-Stockfish-Commands.html).

2. **There is no single fixed NNUE architecture across every Stockfish version.** Stockfish maintains an [official architecture history](https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/nnue_architecture_history.html) documenting different network versions and changes over time. Treat illustrative layer sizes in an explanatory document as examples unless they are explicitly tied to a particular network/version.

3. **The NNUE explanation is not, by itself, the production model weights.** The network's learned parameters are stored in compatible `.nnue` network files; the [official networks repository](https://github.com/official-stockfish/networks) explains that the strongest network is embedded in many Stockfish binaries and that a compatible network file is version-dependent. Independent NNUE inference requires the actual trained weights as well as compatible inference code.

4. **Raw centipawn scores are not universally interchangeable with win probability.** Stockfish does provide a normalized evaluation and WDL estimates: its documentation states that +100 centipawns corresponds to a 50% win probability under its specified fishtest long-time-control self-play conditions. The NNUE training documentation also shows a sigmoid mapping to WDL space with a scaling factor that depends on the engine and data. See [Stockfish's evaluation FAQ](https://official-stockfish.github.io/docs/stockfish-wiki/Stockfish-FAQ.html), [WDL statistics](https://official-stockfish.github.io/docs/stockfish-wiki/Useful-data.html), and the [NNUE score-to-WDL section](https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/nnue.html).

5. **A single engine score is not a full explanation of why a move is good or bad.** UCI analysis output provides more context, including the principal variation (`pv`), search depth, node count, and time. Those fields help reconstruct the line Stockfish prefers, but they are not themselves a natural-language strategic explanation. This is an interpretive limitation of the output, not a verbatim claim from the official documentation. See the [UCI output examples](https://official-stockfish.github.io/docs/stockfish-wiki/UCI-Protocol-and-Stockfish-Commands.html).

## Sources

1. Official Stockfish NNUE documentation: <https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/nnue.html>

2. Official Stockfish NNUE architecture history: <https://official-stockfish.github.io/docs/nnue-pytorch-wiki/docs/nnue_architecture_history.html>

3. Official Stockfish UCI Protocol and Commands documentation: <https://official-stockfish.github.io/docs/stockfish-wiki/UCI-Protocol-and-Stockfish-Commands.html>

4. Official Stockfish evaluation FAQ: <https://official-stockfish.github.io/docs/stockfish-wiki/Stockfish-FAQ.html>

5. Official Stockfish useful data, including WDL statistics: <https://official-stockfish.github.io/docs/stockfish-wiki/Useful-data.html>

6. Official Stockfish network repository: <https://github.com/official-stockfish/networks>