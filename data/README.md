# Data Sources

Personally I used data from two data sources :

- **From chesscom platform** : all the player/user can normally download their games or other games if they are interested to study or analyze them.

- **From Hugging Face** : everyone can use the dataset existed on hugging face platform. 

    - For Lichess Opening you can follow this link : https://huggingface.co/datasets/Lichess/chess-openings . Then, follow all the steps mentioned on the UI.

    - For Studied EndGame you can follow  this link : https://huggingface.co/datasets/Agusanso/EndgameAtlasBench . Then, if needed download the file on you local computer.

## ChessCom Data

A chesscom is saved in `.pgn` format. These types of files can be opened with a **text editor** application. 

An example of what you'll see on the file :

```pgn
[Event "Live Chess"]
[Site "Chess.com"]
[Date "2026.04.22"]
[Round "-"]
[White "username_1"]
[Black "username_2"]
[Result "1-0"]
[WhiteElo "1907"]
[BlackElo "1893"]
[TimeControl "600"]
[EndTime "9:44:33 GMT+0000"]
[Termination "username_1 won by checkmate"]

1. e4 d5 2. exd5 Qxd5 3. Nf3 Nf6 4. Nc3 Qa5 5. d4 c6 6. Bc4 e6 7. O-O Be7 8. Bg5
O-O 9. Qe2 Re8 10. a3 Qd8 11. Rad1 Nd5 12. h4 h6 13. Bxd5 exd5 14. Ne5 hxg5 15.
Qh5 Be6 16. f4 gxh4 17. f5 Bf6 18. fxe6 fxe6 19. Qf7+ Kh7 20. Qg6+ Kg8 21. Rxf6
Qxf6 22. Qxe8+ Kh7 23. Rf1 Qg5 24. Nf7 Qg3 25. Qh8+ Kg6 26. Ne5+ Kg5 27. Qxg7+
Kh5 28. Qh7+ Kg5 29. Qg6# 1-0
```

### Meaning of every blocks

- **[Event "Live Chess"]** : when someone plays a regular competitive chess game. It changed when the game was played in competitive tournamnent for example.

- **[Site "Chess.com"]** : the game was played on the chesscom platform.

- **[Date " "]** : it respond the question "When was the game played ?"

- **[Result " "]** : "1-0" is meaning that the player with the white pieces won. "0-1" is when the player with the black pieces won.

- **[TimeControl " "]** : the time control indicated is on seconds. So, 600 seconds can be converted as a 10 minutes game to each player.

- **[Termination " "]** : indicate how the game was ended. Like here the player with the white pieces has won by checkmate his/her opponent.

- **[1.e4 d5 2.exd5 Qxd5]** : chess move associated to when the move was played. The number is related to every time a player have played (here : the first move was e4 for the white, d5 for the black). `[e4 d5]` is associated to the different cases on the chessboard (**e** : is for the column e, **4** : is for the row 4).

## Opening & EndGame Data

A chess game can be divided in three parts :

- **Opening**

- **MiddleGame**

- **EndGame**

### Opening

The Opening represents the first part of a chess game. It is related to what moves has been already studied before and played by a player today. It can ended very early if the player is not very prepared or doesn't really rely on theory. Otherwise, player in some level like GrandMaster can play **30 moves** of theory.

Opening have names, here are some examples :

- `London System`

- `Italian Game`

- `Ruy Lopez / Spanish Game`

- `Sicilian Defense`

- etc

### EndGame

The EndGame is the last part of a chess game. It happens when the Queen is off the board or when the two players have only Queen and few pawns with no other pieces.

Player have studied some of those EndGames and have established some theory behind. Here are some known EndGame :

- `King Pawn EndGame`

- `Rook EndGame`

- `Knight - Bishop EndGame`

- etc
