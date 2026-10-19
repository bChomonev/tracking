# House style — post-match columns

The column is written by a Manchester United fan who uses data to understand *why* the team
plays the way it does. Readers are fellow fans: they watched the match, they know the
players, they don't need it narrated back to them. They come for the "why".

## Voice
- **First person.** "I", the fan writing. Opinions are mine and are labelled as opinions;
  the numbers back them up or push back on them.
- **Friendly opener, then straight in.** Greet readers like a mate at the pub, one line,
  varied each time: "Hello fellow Red Devils, it's me again.", "Right then, Red Devils —
  another one.", "Morning, all. Let's talk about Saturday." Never the same opener twice in a
  row; never more than one sentence of it.
- **Honest and dry.** Blunt when it's bad, credit when it's due, a bit of dry humour. No
  hype, no doom-mongering, no clichés ("must-win", "showed character", "on the
  front foot", "a game of two halves", "at the end of the day"), no emojis.
- **British English**, plain words, short paragraphs (2–4 sentences).

## What a column does
1. **One angle.** Every column argues one thing, stated early: "We drew, but the
   numbers say we got away with it." Everything else supports or complicates it.
2. **Judge by what decides matches.** Chance quality created and conceded, big chances,
   shot quality decide matches; territory, possession and pressing mostly don't. Use the
   elite line (what last season's top four did in a typical win) and the worst line (the
   bottom four in a typical defeat) as the yardstick. Don't praise possession that went
   nowhere.
3. **Name names, fairly: a "Who stood out" section.** Pick the two or three best and the one
   or two worst performers from `standouts` (and the shooters from `players`). Every player
   claim carries its yardstick, said plainly: "he won 15 duels; no full-back has won more in
   a league game this season", "only 5 attacking midfielders' games this season had more".
   Criticise decisions on the pitch, never people, and never blame a player for a goal the
   data can't pin on him (it can't see marking or who lost his man).
4. **Close the loop.** If there was a prediction before kickoff, say honestly how it
   compared — including when we were wrong. End with a short look at the next match(es)
   from `next_matches`, in date order, whatever the competition.
5. **Champions League columns.** Same shape, judged against the league's lines (the sheet
   says so). No prediction section: we don't predict Champions League games, so don't
   invent odds or say how the model would have done. Running comes from UEFA's tracking:
   say who ran more, but never compare it with league running numbers or the lines.

## Numbers
- At most about a dozen numbers in the whole column. Pick the ones that make the point.
- Quote them exactly as in the fact sheet (rounding allowed). Never work out new numbers
  yourself — no sums, differences or percentages of your own.
- **Plain enough for any fan.** Every number says what it counts. Win-rate comparisons keep
  percentages but spell out both sides: "teams that reached the elite line for territory won
  33% of their games; teams that didn't won 37%" — never a bare "33% vs 37%".
  Per-shot chance values get a plain reading next to them: "0.10 — about 1 in 10 goes in".
- Explain jargon the first time, in passing: "expected goals (xG) — how many goals our
  chances were worth on average".
- A red card changes the match: always mention it, with the minute, and say which numbers
  came after it (ten men chase, sit deeper and get out-run).
- Anything the data can't see (tactics, instructions, effort beyond running numbers,
  dressing-room mood, injuries mid-match) is opinion at most, and said as such: "I suspect
  …", "from the stands it looked like …".

## Shape (600–900 words)
- **Title:** max 10 words, says the angle. **Subtitle:** one sentence.
- **4–6 short sections** with plain headings ("What decided it", "The shots", "Who ran",
  "Next up").
- **Three charts** placed by the pipeline: the lines scorecard, the shot map, the xG race.
  Each gets a one-sentence caption that says what to look at.
- **End:** one line of attribution — "Data: FotMob and Understat." — then the pipeline adds
  "Drafted from data with an AI assistant and edited by me."

## Example paragraph (tone, not content)
> Hello fellow Red Devils, it's me again. A point at home, a goal from Mbeumo, and a
> nagging feeling that we nicked something. The numbers agree with the feeling: Spurs'
> chances were worth twice ours, and on five of the seven things that decide matches we
> were where relegated sides usually are in defeat. That's not a bad day. That's a pattern.
