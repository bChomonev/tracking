# Decision Log

TDP-001 and ARCHITECTURE.md are a **compass, not a contract**. When we deviate from them,
fill a gap, or resolve a contradiction between them, it goes here — newest first. If a
decision supersedes a doc statement, the doc is updated or the entry says so.

Format: **D-NNN — Title** · date · status (`accepted` / `revisit` / `superseded by D-XXX`)

---

## D-073 — Picks: the round at a glance, every league, each tier next to its record · 2026-10-29 · accepted
A new tab that synthesises the four leagues' next round into the calls the models are
surest of. The rule that makes it a page and not a tips sheet: every tier carries its own
track record — the held-out band record (D-060's "when we say it, does it happen?", pooled
across leagues by matches) and this season's running count from the frozen prediction
record — and a market appears only where its backtest beats the naive guess.

`corridor.picks` is a pure aggregation over the leagues' `predictions.json` and
`previews.json` (nothing recomputed), embedded by `build_site` as `SITE.picks`:
- **Favourite to win or draw** (1X / X2) in tiers 90%+, 85–90, 80–85, 75–80, 70–75; below 70%
  it is not a call. First round: 3 / 9 / 4 / 6 / 7 matches; held-out records 91% of 1,115,
  89% of 2,324, 85% of 2,655, 80% of 2,970, 76% of 3,161 — each within a point or two of
  what we said; this season so far 8 of 8, 11 of 17, 15 of 17, 4 of 7, 9 of 13, shown as
  they are. Each row links to its match page and names the drivers.
- **Goals**: over or under 2.5 only at 70%+ (held out: over calls at 70%+ said 74%, happened
  74% of 397; under calls 62% said / 65% happened of 224 — thin). Both teams to score is left
  off until its calibration is kept the same way. The prediction log now stores `over_2_5`
  with each prediction so the tier gets a season record from the 31 Oct round on.
- **Shooters**: the twelve starters likeliest to have two or more shots, with the held-out
  rate for players given that chance (80–90% band: 84% did, of 138). A player with two
  fixtures in the round appears twice, once per opponent.
- **Cards**: the side likelier to draw more yellows at 60%+ (none this round — the most
  lopsided match is at 64%); the only cards call the backtest supports (right 57% of 1,776
  past matches, draws counted as wrong). Totals and reds are stated as unpredictable, not
  listed.
- **No "value against the bookmakers"**: the record has the model a few thousandths of RPS
  behind them, so a disagreement is not an edge; the page says so.

## D-072 — How much this season weighs: a little slow on the outliers, and no rule fixes it · 2026-10-28 · accepted
Asked after Stuttgart (D-071): after seven rounds a level rating is 18% this season and 82%
before. Three tests on the model as published (form and the blend in), D-023 protocol.

**League-wide knobs.** Re-tuned in the PL, the tuning seasons still pick half-life 24 /
carry 1.0 (D-023). Held out, half-lives 12–18 are better by 0.0003–0.0005 RPS in 4 of 7
seasons, which the protocol does not let us pick; a rolling, honest choice (before each
season, the half-life best on every season before it) picks 24 four times and 18 three
times and ties fixed 24 pooled (0.20269 vs 0.20271). Forgetting more over the summer (carry
0.6–0.8) is worse at every half-life, as D-071 found from the other side.

**The targeted question: when the first seven matches disagree strongly with the rating,
which one predicts the rest of the season?** Every complete team-season 2015-16 → 2025-26
(PL 240, La Liga 240, Serie A 240, Bundesliga 216): the rating after match 7 correlates with
the remaining matches' npxG difference at 0.73–0.78, the raw first seven at 0.71–0.77. When
the early matches were *much worse* than the rating (gap under −0.6 per match, 17–22 cases a
league), the rest of the season sat 11% of the way from the rating to the early number in
the PL, 46% in La Liga, 37% in Serie A, 39% in the Bundesliga; when much better, 27–51%. The
model moves 18%. So on the outliers the rating is somewhat too slow — by a few tenths of an
npxG difference, worth about 2–3 points on the chances of a Stuttgart-type card.

**A rule for the outliers only** (`Params.surprise_gain`: the update step grows with the
size of the surprise, alpha × (1 + g · min(|x − s|, 3)) on the chance and goal stats, g on a
0.1–1.0 grid): PL tune +0.0000 … +0.0010 / held −0.0002 … −0.0005 (4/7); Bundesliga the
mirror image (tune −0.0012 … −0.0000 / held +0.0000 … +0.0008); La Liga and Serie A flat.
Noise, not a harvestable effect. **Nothing changes**: the slow rating stays slow, the fast
component is the form feature (D-061), the switch stays in the code, off. Stuttgart's rating
catches up progressively — this season carries about a third of the weight by round 15 and
two-thirds by the end — and their 6 points from performances worth 8.8 are the model's
defence of its own view.

## D-071 — Squad continuity: neither a carry shrink nor a feature helps · 2026-10-28 · accepted (not adopted)
Prompted by Stuttgart (2 wins, 5 losses, still a 24% away win at Leverkusen with 47% not to
lose): the level ratings have a 24-match half-life, so after seven rounds 82% of a rating is
last season, and a team whose squad changed a lot in the window is being rated as a team
that no longer exists. The proposed fix: at a season start keep carry × continuity^power of
the rating's distance from the mean, continuity being the share of last season's minutes
played by players still at the club (`understat.continuity`, from Understat's season player
lists back to 2014; a player listed with two clubs has his minutes split). Also tried as a
plain feature, home minus away (`+continuity` feature sets; promoted sides get the league's
typical value).

**Stuttgart are not that case.** They kept 84% of last season's minutes, the third-highest
in the Bundesliga this season (Werder Bremen 38%, Frankfurt 45%); their slide — chance
quality conceded 1.27 → 2.60 per match, the worst in the league, with the third-best attack
— is happening with the same squad. Their 6 points come from performances worth 8.8; one of
the two "surprises" (Hamburg 1-0) they lost while creating 2.6 npxG to 1.7. The model's
position is defensible; what it cannot see is a settled squad defending worse.

**The test** (D-023 protocol, on each league's model as published; PL continuity runs
0.44–0.97, mean 0.83, sd 0.09). Carry × continuity^g makes things worse at every power in
the PL (tune +0.0003 … +0.0021, held +0.0001 … +0.0010), La Liga and Serie A (held +0.0002
… +0.0033); the Bundesliga gains on the tuning seasons (−0.0002 … −0.0004) and loses held
out (+0.0000 … +0.0012). As a feature: PL tune +0.0002 / held +0.0000, La Liga −0.0000 /
+0.0000, Serie A +0.0001 / −0.0001, Bundesliga −0.0000 / +0.0002 — noise. **Not adopted.**

**Why the intuition fails, in the numbers.** In August–October the sides that kept 90%+
of their minutes *beat* the ratings' expectation by +0.18 npxG per match (393 PL
team-matches); the sides under 60% fell short by only −0.07 (35). Continuity is a mark of a
club that is doing well and keeps its players, which the rating already knows; shrinking
those sides' ratings punishes the wrong teams. The summer and winter windows surely matter
for individual clubs, but "share of minutes kept" does not carry it as a league-wide rule.
The code (`Params.churn_power`, the continuity features, `understat.continuity`) stays,
switched off, so the test can be re-run with a better measure — e.g. the quality of who
left and who arrived, which minutes alone cannot say.

## D-070 — Fact sheet: chance quality difference is the headline trend · 2026-10-28 · accepted
The team's `recent_form` block (D-061) carries three series — chance quality difference,
elite score, danger score — and their calls can disagree (Arsenal, round 8: steady / down /
up), so the analyst could pick whichever suited the sentence. The block now names the
headline (`headline`, `call`): chance quality difference per match, the series the table and
the team page call recent form; the note says elite and danger scores are supporting detail
in coarse steps and that when they point the other way the form is "mixed", not a trend.
Also on the overview page: the "most like a top team / furthest the other way" sentence now
ranks by the decisive-line counts it quotes, with the weighted scores only as a tie-break
(it had named Villa at 0 elite / 2 relegation level over United at 0 / 4).

## D-069 — Game state is 11 v 11 only: the clock stops at a red card · 2026-10-28 · accepted
D-051 said "red cards are ignored for now". The when-level / ahead / behind numbers are
meant to say how a team plays in each score state, and a side playing against ten men (or
with ten) is in a different game. Now the state clock stops at the first red card on either
side (`fotmob.state_minutes` / `state_profile`, ``until``; the players' per-state shot
splits likewise), so minutes and shots after it count in the whole-match totals but in no
state. A match that had fewer than 20 minutes in a state before the card drops out of that
state by the existing rule. Added-time shots still sit at the end of their half (the first
cut used the 90-minute clock as the cutoff and silently dropped every stoppage-time shot
from the states — caught by diffing the rebuilt rows: 114 team-matches had changed with no
red card in them).

Scale: 26 of 160 PL team-matches this season have a red card on one side. Rebuilt all
processed seasons (2024-25 → now, four leagues and the Champions League). United's rows
move a little: when behind, npxG conceded per 90 1.10 → 0.49 (a ten-men match leaves the
state), shots per 90 25.6 → 27.7; most ranks move by one place or not at all. The lines,
impact tests and the D-051 trait numbers were not re-derived: the change is small and
their method is unchanged. The page and the fact sheet say the states are 11 v 11 only.

## D-068 — Two models averaged: the goals model's own 1X2 blended in · 2026-10-28 · accepted
D-027 left the question open: for win/draw/loss the logistic model won the tuning seasons
and the unshrunk goals model won the held-out ones, and switching on held-out evidence would
have been choosing by the test set. The fresh protocol asked for there: a blend,
p = (1 − w) · logistic + w · goals-model 1X2, with w chosen on the PL tuning seasons.

**The second opinion** (`Params.goals_weight`, `Model.fit`/`predict`): the same Poisson +
Dixon–Coles goals model as the scorelines (D-027), fitted on the same training matches
from the same ratings but *unshrunk* — its raw rates are over-confident on totals, which is
why the scorelines use the shrunk version, but good at who wins. The matrix's lower
triangle, diagonal and upper triangle are its home / draw / away. On a typical held-out
match the two models differ by 4 points on the home win (the shrunk version by 7).

**Protocol** (D-023: tune on PL 2016-17…2019-20, hold out 2020-21…now, each league on its
own matches, on top of the league's model as published including form). PL tuning: w = 0.4
is the best on the grid (−0.00059 RPS; w = 0.2…0.6 all better than w = 0), the shrunk
version peaks lower (w = 0.2, −0.00019). Held out at w = 0.4: PL 0.20379 → 0.20271
(−0.00108, better in 6 of 7 seasons; w = 1.0 alone −0.00121 but worse on tuning); Bundesliga
0.20051 → 0.20034 (−0.00017, 4/7); La Liga +0.00049 (1/7); Serie A +0.00014 (3/7) — those
two gain on the tuning seasons (−0.0004 / −0.0018) and lose held out. Applied per league by
the D-031 / D-036 / D-061 bar (better pooled and in most seasons, `blend_applied`): **on in
the PL and, marginally, the Bundesliga; off in La Liga and Serie A.** In the PL the rolling
temperature calibration (D-036) then switches itself off: the blend already removes the
over-confidence it was correcting (held-out 0.2027 raw).

**What else changed.** The fixture card's "biggest factors" describe the ratings model's
part (the goals model has no per-feature pushes); the "Two models averaged" card in "What
was tested" and the backtest footer say so. The scorelines still align to the published
chances (D-027), which are now the blend. `GoalsModel.fit`'s rho search was vectorised
(same answer; the correction is linear in rho on four cells), because the blend fits a goals
model in every walk-forward season.

## D-067 — Rest and congestion add nothing once strength is known · 2026-10-28 · accepted (not adopted)
The classic small feature: days since a side's last match in any competition, and whether it
played in Europe in the week. `corridor.calendar` builds every league team's full calendar
back to 2015-16 — the league from the model's Understat history, domestic cups and Europe
from FotMob's fixture lists (Champions League and Europa League from 2016-17, Conference
League from 2021-22; FA Cup and League Cup, Copa del Rey, Coppa Italia, DFB-Pokal), names
matched by similarity one to one per season. `predict.rest_features` gives days of rest
(capped at 10) and a flag for a European match within the last four days; `walk(…,
calendar=…)` adds `rest_diff` and `europe_diff` (home minus away) and the feature sets
`+rest`, `+europe`, `+rest+europe` on top of the frozen model, with and without form.

**The raw read is a trap.** PL home sides on three days' rest or less won 52% of matches,
those on eight or more 41%; a home side that played in Europe in the week won 57% (La Liga
64%). Short rest means you were playing midweek, and the sides playing midweek are the
strong ones. The model already knows who is strong.

**D-023 protocol** (tune on PL 2016-17…2019-20, hold out 2020-21…now, every league on its own
matches; RPS change against the model as published):
- PL: +rest tune +0.00089 / held +0.00013 (better in 1 of 7 seasons); +europe −0.00006 /
  +0.00005 (5/7); both +0.00085 / +0.00016.
- La Liga: +rest +0.00038 / +0.00009 (1/7); +europe +0.00008 / +0.00016 (2/7).
- Serie A: +rest +0.00077 / −0.00005 (3/7); +europe +0.00016 / +0.00013 (3/7).
- Bundesliga: +rest +0.00058 / +0.00002 (3/7); +europe +0.00052 / −0.00024 (6/7) — a
  held-out gain with a worse tuning score, which D-027 says is not ours to pick.
Rest days make the tuning seasons worse in every league; the Europe flag is noise. **Not
adopted.** The calendar and the features stay in the code, switched off (no calendar is
passed in the pipeline), so the test can be re-run; the calendar could also serve the fixture
card one day as plain information ("played in Europe on Wednesday"), which is a different
purpose and a fetch per run.

## D-066 — Squad depth: resting regulars is free for big clubs, not for small ones · 2026-10-28 · accepted (finding, watch)
The user's hypothesis on top of D-065: a missing regular costs a thin squad more than a deep
one. Tested on the same rows (official line-ups, 2024-25 → now), three ways.

**A multiplier on the missing share** — share × exp(−g · z), z the side's level rating
(npxG for minus against), its XI's market value, or its bench-to-XI value ratio, (k, g)
fitted on one season and tested on the others. England: g fits to 0 for level and value; the
split by home-side strength even goes the other way (home missing 3+ regulars more than the
away side: weak sides 30% said → 21% won, strong sides 56% → 40%). Serie A: level g = 1.0 /
0.75, test −0.0015 / −0.0017 where the plain share did nothing; weak home sides 27% → 15%,
strong 62% → 57%. La Liga leans the same way (strong home sides missing regulars 70% → 77%)
but the fits are unstable; the Bundesliga is too thin.

**Why England looked different: injured against rested.** Splitting the missing regulars into
those on the unavailable list and those fit but not picked (`Contributions.regulars_split`):
- *Injured / suspended regulars cost everyone.* PL, home side with 2+ more than the away
  side: weaker half 29% said → 17% won (n 18), stronger half 46% → 32% (n 19); Bundesliga
  35% → 25% and 53% → 44% (n 16 each).
- *Rested regulars cost only the small clubs.* PL weaker half 37% → 26% (n 76), stronger
  half 56% → 55% (n 77). La Liga weaker half 39% → 31%, stronger half 61% → 64% (n 83 each):
  the giants rotate for free. Serie A small drops at both ends (27% → 24%, 53% → 50%); the
  Bundesliga weaker 34% → 36%, stronger 54% → 49% (n 61 each, noisy).
That is the hypothesis, and it is also why D-065's plain share fails outside England: in
Spain and Italy most "missing regulars" are big clubs rotating. A two-parameter fit
(k_unavailable, k_rested) per league is not yet stable season to season (PL 1.8/1.2 then
1.4/0.4; La Liga 2.6/0.8 then 0/0), because the effect lives in ~150 matches a league.

**What is done.** Nothing changes in the odds. The log now carries, for every scored
prediction with an official XI, the split (`regulars_unavailable`, `regulars_rested`) and
each side's level (`level`), next to `regulars_missing`, so the interaction can be fitted on
three seasons at the end of 2026-27 — the natural form is k_injured · d_injured +
k_rested · d_rested with k_rested shrinking with the side's level. Revisit then, with D-065.

## D-065 — Official line-ups: measured in the record, not yet in the odds · 2026-10-28 · accepted (watch)
The bookmakers' edge over the model is mostly who actually plays. The laptop is not on
before every kickoff, so line-ups cannot be published reliably — but their value can be
measured honestly after the fact: the FotMob page keeps the official XI, and shifting the
*pre-kickoff* chances by it uses nothing from the match. `absences.lineups` reads the official
XI (``lineupType == "standard"``, 11 starters a side); the measure is each side's
**share of its usual XI not starting** — the 11 players with the most earlier minutes (last
season at half weight) among those seen in one of its squads this season, and only once the
team has played 3 matches this season (`Contributions.regulars`, `MIN_TEAM_MATCHES`). The
shift is the D-026 one (`adjust`, k = `K_LINEUP` = 0.9).

**What was tried first, and why it was wrong.** Minutes not in the XI, minutes not in the
squad, the XI's market value against the team's usual (FotMob gives it; k fitted to 0 — no
information), and the usual XI from *all* earlier minutes. That last one looked best (PL folds
−0.0021 / −0.0034, k 1.1 / 0.9) until this season's log showed Spurs "missing" 8 of 11
regulars every week: players sold in the summer were still in the usual XI, and promoted sides
(no last season in the data) looked fully present. Squad churn is a different signal from
line-ups, worth its own test some day; it was removed from this one.

**Result with the clean measure** (D-026 protocol: k fitted on one season on a 0–8 grid,
tested on the other two; PL 750 matches, 2024-25 → now). Fit on 2024-25: k = 1.2, test
0.2086 → 0.2091 (+0.0005). Fit on 2025-26: k = 0.6, test 0.2078 → 0.2046 (−0.0031). By season
at k = 1: 2024-25 −0.0047, 2025-26 −0.0004, this season's 50 +0.0022. Big gap (home side
missing 3+ regulars more than the away side, 73 matches): we said 44%, with line-ups 34%, it
won 32%. So: a clear gain in one season, none in the other, and one fold loses — **it fails the
D-031 bar today**, so it is **not applied** anywhere. Other leagues, PL-frozen weight: La Liga
0.1954 → 0.1965, Serie A 0.1912 → 0.1920, Bundesliga 0.1986 → 0.1992, all worse; home sides
missing 3+ regulars still won 50% in Spain and 42% in Germany against 32% in England.
Rotation is not weakness everywhere. The unavailable-list team news (D-026) stays as it is.

**What is built.** Every scored prediction gets `p_with_xi` / `rps_with_xi` (filled in by the
post-match job from the cached page, for earlier entries too), the record carries
`rps_with_xi` / `n_with_xi`, and the round summary and whole-season line say "with the
official line-ups, had we known them, X on the N with one". `predictions.json` carries
`lineup_test` (frozen for the PL, computed for the other leagues by the generalised
`team_news_test`) and `lineups_applied`; the "What was tested" page has an Official line-ups
card. When the official XI *is* out at prediction time, the fixture card says who is missing
how many of their usual XI and that it is not used; the switch (`lu_on`, same rule as team
news, replacing team news rather than stacking on it) is in place for when the record and a
third season earn it. **Revisit at the end of 2026-27.** Also found: stacking line-ups on team
news was 0.0003–0.0007 better than line-ups alone in the two full seasons and worse this
season — not adopted, it double-counts the same absences.

## D-064 — Absences weighted by player quality: no better than minutes share · 2026-10-28 · accepted (not adopted)
The idea: losing a top player and losing a rotation player count the same in D-026 if their
minutes match, so weight each absent player's minutes by his quality. D-026 had already found
that weighting by output share (npxG + xA) overfits; the quality number tried here is one every
outfield player has, FotMob's match rating averaged over his earlier matches (last season at
half weight), as two multipliers: rating − 6 (floor 0.2) and exp(1.5 × (rating − 6.9)). The
share is then quality-weighted minutes missing over the team's quality-weighted minutes.

Protocol as D-026: for every FotMob match with team news on its cached page (PL 840, La Liga
858, Serie A 842, Bundesliga 674; 2024-25 → now), the published walk-forward chances are
shifted by `absences.adjust` with k fitted on one season (grid 0–6) and tested on the other
two, both ways. Premier League, RPS change on the test matches (fit on 2024-25 / fit on
2025-26): minutes share −0.0002 / −0.0014; rating − 6: −0.0004 / −0.0011; exponential rating:
−0.0005 / −0.0008; output share −0.0007 / +0.0030 (the D-026 overfit again). The quality
versions are better on one fold and worse on the other, summing to the same as minutes
(−0.0015 against −0.0016). Elsewhere nothing changes: La Liga still points the wrong way with
any weighting (+0.003 to +0.005 when k is fitted on 2024-25, k = 0 when fitted on 2025-26),
Serie A fits k = 0 with every weighting, the Bundesliga is ±0.001 either way. **Not adopted;
minutes share stays.** The honest reading is that ~800 matches cannot tell weightings apart
when the whole team-news effect is ~0.001 RPS; FotMob ratings are also compressed (sd 0.8
around 7.0), so the multiplier barely reorders players. Revisit only with official line-ups
as the signal (who actually played), which is a different and larger question.

## D-063 — Trends in the prediction: the page's form loses to the EWMA; shooter form never helps · 2026-10-28 · accepted
Task 3 of three. Two tests, two "no", and one fix on the fixture card.

**Why test at all.** After D-061/D-062 the site carried two "recent forms": the team page's
(the last 5 league matches against the earlier ones this season, opponent-adjusted by season
medians) and the model's (a 2-match-half-life EWMA of the same ratings against a 24-match
level). In the round of 31 Oct they pointed different ways in 4 of 10 fixtures — the team
page said Chelsea were trending down while the fixture card said recent form favoured
Chelsea (because United's form-minus-level was worse still). If the page's own measure also
predicted, one number could serve both.

**A. The page's measure as the 1X2 feature** (`predict.WindowRatings`, `Params.form_window`:
the form twin is the plain mean of each team's last N opponent-adjusted matches, running
across the season boundary; the feature is still "recent minus level"). D-023 protocol:
chosen on the PL tuning seasons 2016-17…2019-20, held out 2020-21…now, every league on its
own matches, against no form and against the EWMA. Tuning seasons: N = 3 was the best of
anything tried (−0.00021 RPS against −0.00003 for the EWMA; N = 4 −0.00008, N = 5/8 worse
than no form), so N = 3 is the protocol's pick. Held out it loses to the EWMA wherever form
is applied: PL −0.00064 (better in 4/7 seasons) against −0.00077 (5/7); Serie A −0.00003
(4/7) against −0.00037 (5/7); Bundesliga −0.00065 (5/7) against −0.00082 (7/7); La Liga both
worse than no form (+0.00013 / +0.00011), off as before. **Kept: the EWMA.** The window twin
stays in the code (tested, switched off) so the test can be re-run.

**B. Shooter form in the shooter model** (`preview.FORM_MATCHES` / `FORM_WEIGHT`: the
player's shrunk rate over his last 5 appearances mixed into his season rate). D-024/D-042
protocol: walk-forward Brier on every start in 2025-26 and 2026-27, four checks (1+ shots,
2+ shots, on target, goal), chosen on the PL, checked on the other leagues. At weight 0.25:
PL 4 of 8 checks better, all within ±0.00014; La Liga 1/8, Serie A 0/8, Bundesliga 1/8, each
by +0.0001 to +0.0008 worse. At 0.5 worse in 31 of 32 checks; last 3 or last 8 matches no
better. **Not adopted** (weight stays 0), which is what D-062's lag-1 r = −0.02 predicted:
a shooter's last few matches say less about his next one than his season rate does.

**The fix is on the card, not in the model.** The fixture card now says "form in the model's
short window (the last two or three matches count most)", shows the effect in percentage
points rather than log-odds — the chances with the form feature at its training average
against with its actual value, same temperature as the published chances, before team news
(Chelsea v United: +2.1 points for Chelsea) — and carries a tooltip saying it is not the
team page's recent form and that both are small effects. The drivers list labels the feature
"recent form (the model's short window)". The team page, the fact sheet and the preview read
keep the plain last-5-v-before description, because that is what "form" means to a reader;
the model keeps the EWMA because that is what the held-out test keeps.

**Monitoring (same day).** Every prediction is now logged with `p_noform` (the form feature
at its training average, before team news) and scored as `rps_noform` once the result is in,
so the season record says what form did *this season*: the round summary and the whole-season
line show "without recent form X against Y with it, on the N logged with it" (Y is the
without-team-news score, the fair comparison), with a tooltip saying it is a running check,
not the test that decides. The "What was tested" cards say what was tried and not used: the
page's measure (Recent form card) and shooter form (Likely shooters card). The "How far off"
chart is left alone — a "without form" bar would differ by 0.0008 on a 0.20 scale.

## D-062 — Player trend: each player's last matches against his earlier ones · 2026-10-28 · accepted
Task 2 of three (teams D-061, then players, then "which metrics" in the prediction). Nothing
per player existed match by match: the players table is a season per-90 percentile, and
`standouts` (D-040) ranks one match at a time. `corridor.engine.player_trend` is the per-match
number and the read; description only, on the team page, the preview battles and the
analyst's fact sheet. Every design call was made on the 2025-26 PL (38 rounds, 7,086 counted
player-matches) and the numbers below are from there.

**The per-match number.** Each match a player plays 60+ minutes is scored against every
match this season by a player in the same role (the role he played that day, CB / FB / CM /
AM / W / ST, not his season role): for four metrics per role, per 90 minutes, the share of
those matches he beat (ties half; duels lost is flipped so higher is better), and the
composite is their mean. 50 is a typical match for the role, 80 better than four in five.
Metrics per role, chosen for what the role is for and then checked for being a trait
(season-half to season-half correlation of the player's mean percentile, D-051's test):
CB duels won (0.46), recoveries (0.60), line-breaking passes (0.59), duels lost (0.80);
FB duels won (0.51), recoveries (0.46), passes into the final third (0.46), box touches (0.73);
CM line-breaking passes (0.76), passes into the final third (0.77), recoveries (0.72), duels
won (0.66); AM xG+xA (0.20, 10 players), chances created (0.47), box touches (0.70),
line-breaking passes (0.72); W and ST xG+xA (0.41 / 0.46), shots (0.73 / 0.32), box touches
(0.87 / 0.62), duels won (0.78 / 0.74). Dropped for being noise: interceptions for CBs
(0.22), chances created for FBs and Ws (0.35 / 0.30). xG+xA stays for attackers despite its
noise because it is the output the reader asks about; the per-metric trend says when it is
the one moving. One composite drives the call; the per-metric trends are kept for the
tooltip and the fact sheet so the sentence can say what moved.

**Opponent adjustment.** Across the league the composite fell 5–9 percentile points per unit
of opponent strength (the opponent's season median npxG for minus against, relative to the
league average; the same measure as D-061), most for attackers. Each match is credited with
that slope × the opponent's strength (one slope per role, fitted on the season's league
matches). Test, as asked: which adjustment makes the number steadier match to match?
Within-player spread 15.8 points raw → 15.5 adjusted for the opponent → 15.3 adjusted by the
team's own npxG difference in the match; next-match error from the season mean 13.5 → 13.2
→ 13.0. But the team-npxGD version also shrinks what separates players (between-player
spread 8.2 → 7.5; season-half correlation 0.63 → 0.60) because an attacker *is* part of his
team's npxG difference: it removes his contribution along with the context. The opponent
version keeps both (0.63 → 0.63). Chosen: opponent strength.

**Minutes, window, call.** A match counts from 60 minutes (per-90 rates from shorter spells
are inflated); the window counts the player's matches, not the team's, because players miss
matches. Recent = last 4 counted matches, before = the earlier ones with at least 3 (7
counted minimum), not the team's 5 + 3: at 8 rounds, 5 + 3 gives a call for 67 of 320 PL
players, 4 + 3 for 104, and the window moves with the season. The bar is D-061's: "up" /
"down" only when the gap is at least one standard error wide (`trend.recent`), otherwise
"steady"; the count is always shown. Today: PL 18 up / 28 down / 58 steady / 216 too few;
La Liga 30 / 21 / 58 / 260; Serie A 22 / 10 / 40 / 276; Bundesliga 17 / 5 / 30 / 228.

**What it is not, said on the page.** The description is honest about being one: on the
2025-26 PL a player's last four matches forecast his next four *worse* than his season
average did (mean error 9.0 against 7.4 points; the same for the next match alone, 14.2
against 13.2), and one match's deviation from his mean carries nothing into the next (lag-1
r = −0.02). Form at the player level, measured this way, is mostly noise around a level; the
page, the preview and the fact sheet all say "describes, does not predict". The predictive
question — does a shooter's recent form improve the shooter model's Brier (D-024 / D-042
protocol)? — is left for task 3 with the team trend, and the result above says what to expect.

**Where it shows.** Players table: a "Form" column (sortable) with a sparkline of every
counted match on a 50 baseline, darker for the last 4, then "recent v before" with ▲ / ▼, or
"recent (n)" under 7 matches; the tooltip names the roles, the metrics scored and the metrics
that moved. Preview battles: a "form ▲ 62 v 53" note per player with a call, and the read
gets at most one line per side, the biggest move among the attackers, as a description.
Fact sheet: `recent_form` per player (call, both numbers, counts, every counted match's
score and opponent, `metrics_moving`), a note telling the analyst to describe and never
predict with it, and `slim_facts` drops the per-match list as it does for metrics.

**Placement.** Both trend modules are pure math on the processed rows, so they live with the
rest of it: `corridor/trend.py` (D-061) moved to `corridor/engine/trend.py` and the new
module is `corridor/engine/player_trend.py` (NumPy only, no I/O, as rule 2 asks).

## D-061 — Team trend: recent form described on the page, and tested in the prediction · 2026-10-27 · accepted
Task 1 of three (teams, then players, then "which metrics"). The per-match numbers already
existed (elite score, danger score per match, D-021/D-022); nobody had drawn a line through
them, and the prediction model's ratings are a slow trend (24-match half-life) that never
reached the page. Two separate things were built, because they answer different questions.

**Description (`corridor.trend`, site, previews, fact sheet).** Per team, three per-match
series: elite score, danger score, and chance quality difference (npxG for minus against)
with each match **adjusted for the opponent** (minus what that opponent usually allows and
creates, their season median relative to the league average), so a run of weak opponents is
not a run of form. *Recent* = the mean of the last 5 matches, *before* = the mean of the
earlier ones. The call is "up" / "down" only when the gap is at least one standard error
wide (from how much the team's own matches vary); otherwise "steady"; with fewer than 8
matches (5 + 3) there is no call. A plain-reading bar, not a significance test, like D-060.
Shown as a sparkline + "recent vs before" in the overview table (sortable), a tile on every
team page, a line in the preview's season shape and its code-written read, and a
`recent_form` block in the analyst's fact sheet. Not a fixed "last 10": at 8 matches that is
the whole season, and the sentence has to say what it is compared with.

**Prediction (`predict.Params.form_half_life`).** A second set of the same ratings with a
short half-life; the feature is *form minus level* on chance quality difference. Protocol
as D-023: chosen on the PL tuning seasons 2016-17…2019-20 (half-life 2, 3, 5, 8, 12 ×
with/without a goals version), where only half-life 2 beat the baseline, by 0.00003 RPS.
Held-out 2020-21…now with that choice: PL 0.2046 → 0.2038 (better in 5/7 seasons), Serie A
0.1934 → 0.1930 (5/7), Bundesliga 0.2013 → 0.2005 (7/7), La Liga 0.1941 → 0.1942 (3/7).
Applied per league only where it is better overall and in most seasons (`form_applied`,
the D-031 / D-036 bar): on in the PL, Serie A and the Bundesliga, off in La Liga. With the
rolling calibration on top, the PL held-out RPS goes 0.2042 → 0.2035. The fixture cards say
what the model calls form (each side's recent chance quality for and against next to its
usual level) and which way it nudges the odds; "recent form" can appear as a driver.
**For the record, not chosen:** longer half-lives looked better held-out (PL: 8 matches →
0.2033) but worse on the tuning seasons; picking them would be choosing by the test set
(D-027). Revisit with a fresh tuning protocol if the gain holds through 2026-27.

## D-060 — "When we say it, does it happen?": predictions grouped by how sure we were · 2026-10-26 · accepted
The calibration chart answers "are the percentages honest?" for every outcome together. Readers
think in terms of the favourite: if we say 85%, does it come in? The mistakes log now groups the
held-out predictions by our favourite's chance to win or draw (1X / X2), in bands of 90%+, then
5-point steps down to under 65. That is the only table on the page. A "to win" table is also
computed (`bands.win`) but is left off the page, at the user's call: the double-chance view is
the one that matters to us.

Each band shows the average chance we gave and how often it came in. It is marked "Honest" when
the two are within 3 points. That is a plain-reading bar, not a significance test; the
mistakes-log slices (D-058) remain the statistical check.

Premier League: 80–85% came in 78% (323 matches) and under 65% came in 68%. Everything else is
within 3 points.

## D-059 — Season table colours read as a 1X / X2 bet on our favourite · 2026-10-26 · accepted
The table used to colour what happened green, whatever we had said. So an underdog win we'd
half-expected (Villa v City, 26%) looked like a win for us. The favourite is the side we gave the
bigger chance of winning, and the colours now follow it:
- **green**: the bet on our favourite came in. If the favourite won, only its cell is green. If
  the match was drawn, the draw and the favourite are both green.
- **orange**: the underdog won, but we had given it more than 25%. Its cell is orange.
- **red**: a real surprise (D-057). The underdog won from 25% or less, and its cell is red.

## D-058 — The mistakes log: why favourites lost, and where our chances are off · 2026-10-26 · accepted
`corridor/mistakes.py` runs inside the predictions step, so it refreshes after every round, and
it works on the held-out predictions only.

**What kind of miss.** Every defeat of our favourite is labelled from the match's Understat xG:
- *deserved*: the underdog won xG by 0.5 or more;
- *close*: within 0.5;
- *luck*: our favourite won xG by 0.5 or more.

Premier League: of 226 real surprises, 38% were deserved, 37% close and 25% luck. Only the
first kind is the model reading the game wrong.

**Where we're off.** The page compares, for groups of matches, how often the favourite lost with
how often our chances said it would. The groups are home or away favourite, big favourites, close
games, both of those split by venue, promoted sides, early season, and each team with 60 or more
matches as favourite (plus United).

A group is flagged "Off" only when both hold:
- the gap is at least 2 standard deviations (3 for single teams, because there are many of them);
- it points the same way in most seasons.

"Watch" means 1.5 standard deviations or more.

**A flag is not a fix.** Each flag gets a candidate correction, fitted only on earlier seasons
and scored on the next. It is switched on only if it is better overall and in most seasons, the
same bar as D-031 and D-036.

The first flag is Premier League big home favourites: 172 defeats against 148 expected. Its
correction (scaling up the away underdog's chance) gave RPS 0.2042 → 0.2041, but it was better
in only 3 of 7 seasons. So it is not switched on; we keep watching it. Any switch-on gets its
own decision entry.

## D-057 — "Real surprise": a side we gave 25% or less won · 2026-10-26 · accepted
A favourite losing a close game isn't a miss in the same way as a long shot coming in. A
surprise is now an underdog win where we gave the underdog `predict.SURPRISE_AT` = 25% or less.
Why 25% and not 35%: the draw takes about a quarter, so an underdog almost never gets above 35%.
35% would cover 92–99% of matches and change nothing. 25% splits matches roughly in half (the
median underdog chance is 22–25% in all four leagues), and it reads plainly as "1 in 4 or less".
The data can't tune this number, because it is a definition, not a prediction. The test that
matters is whether long shots win as often as we say. Premier League backtest: 1,304 such
calls, 226 came in, and our chances said 206. `score` reports `long_shots`, `surprises` and
`surprises_expected`. The page shows them in the backtest and, for this season, marks only
real surprises with the red edge.

## D-056 — "Favourite lost": the double-chance view of the predictions · 2026-10-26 · accepted
"Favourite won 53%" treats a draw the same as a defeat, but a bettor backing 1X or X2 counts a
draw as a near miss. `predict.score` now also gives `fav_lost`. The favourite is whichever side
we gave the bigger chance of winning (the draw is never the favourite here), and it "lost" only
when the other side won. The page shows this for the backtest (model, bookmakers, home side) and
for this season's record. Rows where the favourite lost outright get the red edge; a favourite
that only drew no longer does.

## D-055 — Prediction record: the whole season, round by round, sortable · 2026-10-26 · accepted
The "prediction by prediction" table showed only the last 20 scored matches, which is about
two rounds. The record now keeps every scored prediction of the season, and each one is tagged
with its FotMob matchday (the same round map that picks "the next round"). On the page you can
pick a round or the whole season. A summary line gives the favourites that came in, the average
RPS with and without team news, and our RPS against the bookmakers' on the matches that have
odds. Every column sorts. RPS columns sort best-first on the first click; rows without
bookmaker odds always go last.

## D-054 — Match preview: "How they play", the two sides played against each other · 2026-10-22 · accepted
The preview page was built in the predictions stage, so everything on it was a forecast
(chances, scorelines, team news, line-ups, shooters, cards, corners) and none of the site's
explanation reached it. `corridor.matchup` now builds, per fixture of the next round and
from the season profiles only (nothing fetched), a block stored in `previews.json`
(`fixtures[id].matchup`), rendered as a "How they play" section between the prediction and
the team news, and copied into the analyst's `next_match.how_they_play` so previews and
columns can quote it:
- **Season shape**: position, points against the points the performances deserved, elite
  and danger scores, minutes level / ahead / behind, for both sides.
- **Pairings**: attack against defence both ways — chance quality, npxG per shot, shots, big
  chances, touches in the box, set-piece and counter-attack chances — each with league
  ranks, E / W line markers, the attack metric's tier, and **"if both play as usual"** =
  attack × defence ÷ league average. Running vs opponent is shown for both sides. The
  model's own expectation (rolling, opponent-adjusted ratings) is shown next to it and the
  page says why they differ: the ratings still carry last season, the pairings are this
  season's typical match.
- **Battles by role** from the likely line-ups: wingers v full-backs, strikers v
  centre-backs, attacking v central midfielders, both ways. Attackers are measured on
  creation (xG + xA and touches in the box, percentile within the role, plus shots and
  npxG per shot against the role); defenders on duels won and recoveries (plus effort). An
  edge needs 20 percentile points between the two groups. The page says plainly that the
  defensive side is work rate: the data cannot say which defender allowed a chance (D-025).
  Players without a season profile (under 90 minutes) are skipped; players listed as out
  are left out.
- **A read** written by code from the ranks: a luck line when deserved and actual points
  differ by 3+, up to two mismatch lines (decisive or helpful pairings where the attack's
  and defence's league strength differ by 0.4+), and the biggest battle edge.
First fixture (United v Bournemouth): "Bournemouth's performances have been worth 11.3
points and they have 6. Bournemouth's shots are the 4th-best in the league for quality and
Manchester United allow the 2nd-highest quality." The "usual" column has United's attack at
0.86 npxG against the model's 1.50: the ratings still rate last season's third place.

## D-053 — Who takes the shots, by game state · 2026-10-22 · accepted
D-051 said what United do when the score is level; this names who. Every player's shots
from the shot map are now also counted by the score at the time (level, ahead, behind,
same clock and rules as D-051), in the parser (`level_np_shots`, `level_npxg_shots`,
`level_np_goals`, `level_np_shots_outside_box`, `level_np_shot_distance_sum_m` and the
ahead / behind twins) and in `profile.shooting`, where each player and the team get a
`by_state` breakdown: shots, share of the team's shots *in that state*, npxG per shot,
distance, outside-box share and npxG wasted. **Role averages are measured in the same
state**: a striker's shots when chasing are compared with every striker's shots when
chasing, because shot quality moves with the score for everyone.

Site: the "Who takes the shots" table and chart get a switch (all shots · when level ·
when ahead · when behind); the state views keep the same columns, with on target and
blocked left blank because the shot map's on-target flag is not split. Analyst fact sheet:
`shooting.players[].by_game_state` and `shooting.team_by_game_state`, with a note to quote
the shot count next to any per-shot figure from one state. Match fact sheet: each
player's `shots_by_game_state` for that match. Players with fewer than 3 shots overall are
still left out of the list; a state view can show a listed player with one or two shots in
that state, so the count is always shown.

## D-052 — Players' running in the Champions League, from UEFA · 2026-10-22 · accepted
Champions League player rows had running data from FotMob for only about a third of games,
and none for United v Como. UEFA's player statistics cover every game, so `build_season
--competition ucl` now joins them in (`uefa.player_stats`, `uefa.lineup`):
- **Name matching.** Each FotMob player is matched by name within his own squad. The rules,
  in order: exact match, a shared surname, one name contained in the other ('Allan' ~ 'Allan
  Elias'), a one-word short form ('Samu'), and finally a close spelling. All 1,698
  player-games matched. Every non-identical pair was checked by eye.
- **One provider.** FotMob's own running fields are cleared for the Champions League, so it
  never mixes with UEFA's.
- **New fields:** `high_intensity_runs`, `off_ball_km`, and `off_ball_km_p90`.
  - `off_ball_km` uses `distance_covered_opponent_team_in_possession`, which excludes
    dead-ball time. The team metric uses `not_in_possession`, which includes it. That's left
    as is for now.
  - `off_ball_km_p90` is per 90 minutes, scaled to an opponent with half the ball, as in
    D-017, so facing a side that keeps the ball doesn't flatter anyone.

The column fact sheet's `standouts` now gives every player `running_vs_his_role`, not just
the extremes: km, sprints and high-intensity runs per 90, and the adjusted off-ball km. Each
comes with how many same-role games (60+ minutes, same competition) had more. Off-ball km
also joins the best/worst lists. Per-90 rates flatter players who came off the bench (fresh
legs), so the column should say so when it uses them. In the league, FotMob gives only
distance and sprints per player, so league columns get just those two.

## D-051 — Game state: the shot numbers split by the score at the time · 2026-10-21 · accepted (revisit at season's end)
The page said *what* (shot quality at both ends is bad); whole-match totals could not say
whether that is how United play or how they chase. The cached FotMob pages hold every shot
with its minute and every goal with its minute, so each shot is now tagged with the score
when it was taken: **level, ahead or behind**, from the team's view. Own goals are credited by
FotMob to the side that benefits. The clock is 90 minutes: an added-time goal or shot sits at
the end of its half. Red cards are ignored for now.

**Metrics** (stack "By game state", 21 rows, `profile._state_metrics`): per state, chance
quality created and conceded per 90 minutes *in that state*, npxG per shot for and against,
shots and shots faced per 90, and shot distance. A match counts for a state only if it spent
20+ minutes there (`MIN_STATE_MINUTES`); per-shot quality also needs 3+ shots. Each row gets
elite and worst lines from the usual pools, measured in the same state, an impact test, a
site row and fact-sheet rows; the fact sheet also gets a `game_state` block (minutes shares,
the key numbers per state with their lines) and the match fact sheet a `game_state` block
for the column. Minutes shares are context, not a line: they follow from results.

**Kept out of the share, the weighted scores, the tiers and the line counts** (`proof.STATE`,
`SHARE_EXCLUDED`, `compare(uncounted=…)`): they re-measure the whole-match metrics on a slice,
so counting both would double-count. The adoption test (walk-forward AUC of the weighted
scores, as in D-050) was run anyway. With the state rows in, the AUC rose in every league on
both sides — PL elite 0.762 → 0.769, danger 0.772 → 0.774; La Liga 0.769 → 0.791, 0.799 →
0.807; Serie A 0.677 → 0.682, 0.689 → 0.693; Bundesliga 0.720 → 0.759, 0.745 → 0.786 — but
the test only covers this season (108–176 team-matches per league; with three FotMob seasons
the walk-forward can score only the last one), and the top-group hit rate fell in the PL
(0.73 → 0.70) and La Liga (0.80 → 0.70). Too thin to re-score every team on the site now.
**Revisit at the end of 2026-27** with a full season in the test; if it holds, bring the
when-level rows into the scores.

**What the impact test found** (lines from 2024-25 and 2025-26, tested on the next season):
- "When level" chance quality created and conceded per 90 are *decisive* in all four leagues,
  with lifts equal to or above the whole-match versions (PL +0.27 / +0.29 vs +0.27 / +0.27).
- Shots faced per 90 when level separates results more than whole-match shots faced
  everywhere (PL +0.22 vs +0.18, La Liga +0.29 vs +0.21, Serie A +0.28 vs +0.16,
  Bundesliga +0.30 vs +0.20): the whole-match number is diluted by sides sitting on a lead.
- npxG per shot when level is weaker than the whole-match version (helps, not decisive:
  PL +0.16 vs +0.25). Part of the whole-match shot-quality signal *is* the score effect.
- Ahead and behind rows mostly have no line in a tested pair: top-four wins rarely spend 20+
  minutes behind and bottom-four defeats rarely 20+ minutes ahead, so those pools fall under
  the 10-game minimum. They are still ranked against the league each season.
- Trait check (2025-26, team medians for matches 1–19 vs 20–38, correlation across teams):
  the when-level rows are noisier than whole-match ones because they rest on fewer shots —
  PL npxG per 90 when level r = 0.66 (whole match 0.72), npxG per shot when level 0.08 (0.45).
  So quote per-shot quality when level over a season, not after a handful of games.

**United, 7 matches:** level 61% of minutes (league 50%), ahead 17% (15th of 20). When level:
16.7 shots per 90 (most in the league, league 12.5) at 0.064 npxG per shot (19th) from 20.5 m
(19th); 9.4 shots faced per 90 (fewest) at 0.135 npxGA per shot (20th). Last season, when
level, it was 15.1 shots at 0.102 from 16.5 m. The long-range volume is not a chasing habit.

**Layout (2026-10-22, user's call):** the stack is a matrix, not the list the other stacks
use. The data is seven numbers measured in three states, so the reader wants the same number
across level / ahead / behind in one row and for / against in one column. A minutes-by-state
bar for the team and the league sits on top; each cell shows the value, a league-rank chip
coloured by tier, and E / W when the typical match reaches the elite line or sits at the
worst line; impact tags appear on the level rows only (ahead and behind rarely have a tested
line). A one-line read is written from the level column's top-three and bottom-three ranks,
by code, never a model. Tapping a cell opens the same detail block the other stacks use. On
phones the row labels shorten and the chips show the rank number alone. The page also gained
charset and viewport metas (the artifact wrapper adds them when published; local previews
did not have them).

Also fixed on the way: the analyst's `NOT_MEASURED` list still said player-level shooting
was not in the sheet (it has been since D-025), which made the critic drop every player
interpretation in the 2026-10-21 run. The line now names what really is not split by state
(possession, passing, pressing, running).

## D-050 — Passing metrics: shown with lines, but kept out of the scores · 2026-10-21 · accepted
Three passing metrics join the progression stack. All three are FotMob numbers.
- Pass accuracy: completed passes ÷ attempted.
- Passes in the opponent's half: the share of *completed* passes. FotMob's own-half and
  opposition-half counts add up to completed passes, not attempted ones.
- Long balls: the share of completed passes. Lower counts as better, because better sides
  play shorter.

Like every other profile metric, each gets elite and worst lines, an impact test, a site row
and a fact-sheet row. The fact sheet also gains each metric's season rank (`season_rank`).

Passing doesn't get counted in the share of lines reached or in the weighted elite and danger
scores (`proof.STYLE`). The reasons:
- Over a season, good passing sides take more points. Across 156 team-seasons, controlling for
  xG difference, the extra correlation is +0.18 for accuracy and +0.23 for the opponent-half
  share.
- In a single match, reaching the line barely moves the result. The lift is below 0.07, so
  all three are tiered "no effect".
- Counting them lowered the walk-forward AUC of the weighted score: 0.762 → 0.760 for elite
  and 0.772 → 0.763 for worst. It also nudged United's elite score up, just for passing well.

With them out, every existing score is unchanged. Forward and backward passes aren't in
FotMob's data. Whether passing improves the predictions is a separate test that hasn't been
run yet. A quick check showed recent passing form cuts goal-difference error by about 2% on
top of xG form.

## D-049 — The next Champions League game on the team page, without a prediction · 2026-10-20 · accepted
United's "Next match" card only showed Premier League games, so Como on Wednesday looked
missing. `build_site` now adds `next_cup` for each focus team (from FotMob's Champions League
fixtures): the fixture plus both sides' numbers this season, side by side. That's league
position and record, goals and xG per league game, average possession and the last 5 league
results (from whichever of our four leagues the side plays in), and their Champions League
results so far. There's no prediction and no "expected" score: the model is built and tested
on league games only (the 2026-10-19 decision stands). The card says so, and notes that the
league numbers come from different leagues. If the fixture list can't be fetched, the card is
left out and the site still builds.

## D-048 — A Reddit post and comment for every match · 2026-10-20 · accepted
Reddit (r/reddevils) is where United fans who like numbers already are, but it removes or
ignores link-dumps. So each match now also gets `reddit.md`: a post of 120-220 words that is
worth reading without clicking (two or three findings, each with its comparison, one line of
opinion or a question, then one closing line with the newsletter link) and a comment of 50
words or less for the post-match thread, with no link. It goes through the same number check
as the Notes and agrees with the published column when there is one. The user posts it
themselves; `--only notes|reddit` reruns one piece (replaces `--notes-only`), and `--link`
sets the column URL (the default is the SEO slug, D-047).
The browser extension blocks reddit.com and Reddit refuses scripted reads, so we can't save
Reddit drafts; instead `reddit.md` starts with a pre-filled old.reddit submit link (title and
text in the URL) that the user opens, reviews and submits.

## D-047 — Columns get a search title and description · 2026-10-20 · accepted
Column titles are written for fans ("Did we deserve the point at Elland Road?") and never
name the teams, so Google has little to match. Each draft now also writes `seo.json`: a
search title built from the data, home side first, with the names people search for ("Leeds
United 1-1 Man Utd: xG, stats and who stood out"), a description of 160 characters or less
(competition, date, xG, possession, running gap) and a URL slug. These go into Substack's
SEO fields for each post; readers still see the column's own title. Written without the LLM,
so the numbers can't be wrong.

## D-046 — Previews fall back to our own last XI · 2026-10-20 · accepted
Barcelona v Real Madrid (and 8 of 11 La Liga fixtures, all PL / Serie A / Bundesliga ones)
showed an empty shooters table: days before a match FotMob's page often has no line-up yet
(lineupType missing, or "standard" with no starters), and shooters are built from the XI.
Now, when FotMob has no starters for a side, the preview uses that team's last league
starting XI from our own player data (players FotMob lists as unavailable are still struck
through and left out), labelled "last XI"; "official" is only shown when starters exist.

## D-045 — Prediction charts get a plain bottom line · 2026-10-19 · accepted
Same problem as D-044 for the two prediction charts. "Average RPS" becomes "How far off the
predictions were", the base-rate bar becomes "Simple guess (how often home, draw and away
happen)", and a bottom line says how much of the gap from that guess to the bookmakers our
model closes (84-95% across the four leagues), with favourite hit rates. The calibration
chart becomes "Are the percentages honest?", explains what a dot is, labels both axes ("what
we said" / "how often it happened"), and states the average distance of a dot from the line
(results-weighted, groups of 100+) and the furthest group.

## D-044 — Tested-prediction cards lead with a plain verdict · 2026-10-19 · accepted
The "Match previews: what was tested" cards showed raw Brier / RPS scores (0.206 vs 0.220)
that a fan can't read ("is it good, can I rely on it?"). Each line now leads with a verdict
from how much the prediction beats its simple guess on matches it never saw: Useful (≥5%
more accurate, or "which side gets more" right ≥58% vs a coin toss's 50%), Slight edge
(2-5%, 54-58%), Barely better (a real gain under 2%), No better than a guess (then the site
uses the plain average, and says so). Then the plain "% more accurate than …" and, in small
print, the test score. Each card opens with a one-line bottom line and the section with a key.

## D-043 — Corners: pressure stats tested, not adopted · 2026-10-19 · rejected
Question from the user: would corners improve if, like the shooters' opponent factor, we used
more than past corners? The corner model already uses both sides (a team's corners won ×
the opponent's corners conceded, opponent-adjusted, rolling across seasons). Tested adding
rolling won/conceded ratings for box touches, shots, passes into the final third and
possession, blended with the corner ratings on the log scale (weights 0.25 / 0.5 / 0.75),
walk-forward on 2025-26 and 2026-27. Chosen on the PL (box touches + shots at 0.5: side miss
2.068 → 2.063, "more corners" side 62.1% → 62.3%), it didn't hold elsewhere: La Liga worse on
all three measures, Serie A and the Bundesliga mixed. No version improved every league, so
corners stay corners-only; past corners already carry most of the pressure signal.
Follow-up the same day: deep completions (Understat), blocked shots and shots inside the box.
Blocked shots and shots in the box: mixed or worse. Deep completions at 0.25 was the best
candidate: better on 9 of 12 checks (side miss better in the PL, Serie A, Bundesliga, flat in
La Liga; "more corners" side better in three leagues, worse in the PL), but the gain is ~0.01
corners per side and it was picked after seeing all four leagues, so there is no clean
held-out check. Not adopted now; re-test on the rest of 2026-27 as a fresh hold-out (revisit
at the season's end).

## D-042 — Shooter odds: the opponent's defence remembers last season · 2026-10-19 · accepted
Question from the user: do player shot chances account for the opponent (e.g. Ipswich at
City)? They did (× shots / npxG the opponent concedes vs the league), but from this season
only, shrunk by three average matches, so early in a season a strong defence barely
counted. Walk-forward test on every start in 2025-26 and 2026-27 (chosen on the PL, checked
on La Liga, Serie A and the Bundesliga): adding last season's concession at half weight
improved 15 of 16 Brier checks (1+ shots, 2+ shots, on target, goal × four leagues; the one
loss was 1+ shots in the Bundesliga by 0.0002). Making the factor count more (power 1.5 or
2) was worse everywhere; dropping it was worse everywhere, so it matters. Promoted sides
have no last season in the league and are shrunk towards average as before.

## D-041 — Two Notes per match: one with the column, one midway · 2026-10-19 · accepted
Substack Notes are how new readers find the newsletter, but more than two per match would
turn the column into spam (user's call). The post step writes two Notes from the same fact
sheet into `notes.md` / `notes.json` / `note-N.png`: one to post with the column (its
question and answer plus one number; it is given the column's title, subtitle and angle,
and the published `post-edited.md` wins when it exists, so it can't contradict the column)
and one "midway" Note with a small bar chart, timed for noon UK on the day halfway to the
next match in any competition. Same number check as the column; written for strangers, so
"elite line" / "worst line" are always spelled out; weekdays come from the sheet, never
guessed. The user schedules them in Substack (scheduling via browser automation doesn't
work). `post --notes-only` regenerates them without redrafting the column.

## D-040 — Champions League columns; "Who stood out" from role comparisons · 2026-10-19 · accepted
United's Champions League games get a post-match column like league games (`post
--competition ucl`; the update job drafts one after each). No prediction section: we don't
predict Champions League games (the model rates teams within their own league). FotMob
metrics are judged against the league's elite and worst lines (same provider and
definitions); UEFA's running numbers are reported as who-ran-more only, never against the
lines. Every fact sheet now carries `standouts`: each player's match numbers against every
game this season by a player in the same role (60+ minutes, same competition), counting
ties, so a column can say "no full-back has won more" without working out a rank.
`next_matches` lists the next games in any competition (odds only for league games). When
FotMob's match xG and its shot-map sum disagree by more than 0.1, the sheet says so and
the column quotes the match figure (the one the lines use).

## D-039 — "Next round" follows FotMob matchdays · 2026-10-19 · accepted
The next round was guessed from Understat's fixture list: from the next kickoff, stop when a
team appears twice or after 8 days. A Monday leftover (Spurs v Coventry) or a rearranged
midweek game made the following weekend stop after two or three games. Now FotMob's matchday
number decides it: the first matchday with at least half its games still to play, plus any
leftovers of earlier matchdays kicking off before it ends. Falls back to the old window if
FotMob has no round for a fixture.

## D-038 — Predictions get their own tab · 2026-10-19 · accepted
"How good are the predictions?" and "Match previews: what was tested" move out of How we know
into a Predictions tab (`#predictions[/<league>]`, own league switch); How we know keeps the
lines, the league comparison and data caveats, and links across. Same render code (renderHow
fills both views). The "Next round" cards stay on each league page.

## D-037 — Gauge when the elite and worst lines cross · 2026-10-17 · accepted
The "what decides matches" gauge placed a team between fixed worst (12%) and elite (88%) ticks
by `(value − worst) / (elite − worst)`. On three PL metrics the bottom four's defeats beat the top
four's wins (ball recoveries 46 vs 45, PPDA 11.8 vs 12.2, big chances missed 1 vs 2), so that
ratio flipped sign and an elite-level value (United's 50 recoveries) was drawn at the worst end.
Ticks stay at worst-left / elite-right on every row (moving them to their true places read as a
swap). When the lines cross, the dot goes just past elite if it clears both lines, just before
worst if it clears neither, and in the middle if it counts as both; hovering explains the cross.
Normal rows are unchanged.

## D-036 — Rolling calibration (PL only, by its own test); team news has no double count · 2026-10-16 · accepted
**Calibration.** Held-out, the PL model's favourites won less often than it said (said 74%,
won 68%; outsiders said 7%, won 10%). Temperature scaling (`predict.temper`: divide the log
chances by t, renormalise; order never changes) fitted on 2016-17…2019-20 found nothing to fix
(t = 1.02: the over-confidence only appeared after 2020), and fitting t on the held-out seasons
would be choosing by the test set. So the calibration is **rolling**: season S uses the t that
fits the walk-forward predictions of 2016-17…S−1 (`calibrate`, `temperature_for`), never S.
Held-out 2020-21…now: PL RPS 0.2046 → 0.2042 (±0.0004, borderline), La Liga 0.1940 → 0.1941,
Serie A 0.1932 → 0.1933, Bundesliga 0.2012 → 0.2015 (their early-season t ≈ 1.2 was a pattern
that faded). As with team news (D-031), it is **applied per league only where its held-out
test shows a gain**: on in the PL (t = 1.12 this season), off elsewhere; both versions are in
`predictions.json` (`calibration_test`). Calibrated chances feed everything downstream: team
news, scorelines, the season simulation, the log. Windows of 2 or 3 seasons did no better.
It closes ~6% of the PL gap to the bookmakers; the gap is spread across the season (not a
summer carry-over problem: matchweeks 1–8 gap 0.005, 9–19 0.007, 20–38 0.007).
**Team-news double count (checked, none found).** Worry: an absentee who has been out for weeks
is already in the ratings *and* in the missing-minutes share. Built each absence's streak
(consecutive earlier matches on the unavailable list; PL 820 / La Liga 837 / Serie A 819 /
Bundesliga 656 matches, 2024-25…now). 38–58% of missing minutes are fresh absences, 9–20% are
players out 5+ matches. Leave-one-season-out, the current measure, "fresh only", "not
long-term" and a no-new-parameter decay (share × 0.5^(streak/24), the part the ratings don't
yet reflect) score the same in every league (PL 0.2059 / 0.2058 / 0.2063 / 0.2059). With a
24-match half-life, a 5-match absence is only ~13% in the ratings, so the overlap is too small
to matter. Team news is unchanged. Leeds–United (United missing 25% of usual minutes: Shaw,
Mainoo, Šeško, Dorgu, Mazraoui, Ugarte, Heaton) are mostly fresh injuries.

## D-035 — Newsletter identity: "Red Lines", I/we voice, launch order · 2026-10-16 · accepted
The Substack (chomanalysis.substack.com) is **Red Lines**, tagline "Let's draw the red lines:
why Manchester United play the way they do, measured after every match." — the name is the
method (elite / worst lines) in United red. Pen name "Chom". **Voice:** "I" for the author,
"we" only for United fans; never imply a human team. AI help is stated once, plainly (About
page and Substack's "How I make this" note), not hidden. **Launch order:** Post 1 = why I
built it + how it works (the "How we know" page in prose; pinned and linked from every
column), Post 2 = the season so far (analyst read), then game by game (D-034 drafts).
Nothing is published without the user's explicit yes. **Plain numbers:** every number says what
it counts; win-rate comparisons keep percentages with both sides spelled out ("won 33% of their
games; teams that didn't won 37%"), never a bare "33% vs 37%" (rule added to
`prompts/house_style.md`). **Free for now:** paid subscriptions off (Stripe stays connected);
charging waits on the data-licensing question in DATA_SOURCES.md. Posts 1 and 2 published
2026-10-16.

## D-034 — Post-match Substack drafts (commentary style) · 2026-10-16 · accepted (in progress)
For a newsletter of post-match columns in the user's voice: commentary that quotes our
findings, never republished datasets or tables. `scripts/post.py` builds a one-match fact
sheet (`corridor.post`: lines per decisive metric, elite / danger score, events, both sides'
shot summary, players, pre-kickoff prediction, next match, `not_measured`), three charts
(lines scorecard, shot map, xG race; captions written from data — the model can't see the
charts), then **plan → draft → critic → one revision**: the plan (angle, opener, section
bullets, numbers used) is the only call that reads the whole fact sheet; the draft writes
only from the plan and the house style (`prompts/house_style.md`: first-person fan, friendly
opener, honest and dry, 600-900 words); numbers are checked at both steps; the critic's
flags are revised once and any left become "check before publishing" notes. Output: plan.md,
post.md, post.html (copy-paste into Substack) and PNGs in `data/posts/…` — never published
automatically; `update` drafts one after each new United league match. A Claude Code skill
(`.claude/skills/united-post`) uses the same house style. **LLM limits:** the DiscreteStack
gateway cuts requests at 180 s (504s seen) — calls are capped (timeout 170 s, 5-8k tokens,
low/medium effort), retried once with less reasoning, and a failed checker never discards a
finished draft. First draft (Spurs 1-1) had a good plan but the draft added unsupported
colour and wrong chart captions — fixed by the plan-only rule, data-written captions and a
shot summary; the re-run is pending (endpoint timing out).

## D-033 — Shot accuracy and "at least 2 / 3" chances · 2026-10-16 · accepted
Per player: share of shots on target (shrunk with 10 shots of role prior), expected shots
on target, and P(≥1/≥2/≥3 shots), P(≥1/≥2 on target) — Poisson. Team pages' "Who takes the
shots" shows each player's on-target share vs his role. **Data fix:** FotMob's shot-map
`isOnTarget` is also true for *blocked* shots (it gave 65–75% "accuracy"); excluding blocked
shots matches FotMob's official team shots-on-target stat exactly (996 = 996 over 200
matches), giving the real 32–35%. **Calibration fix:** high-volume shooters' predictions
were too confident (≥2 shots "84%" happened 70%); a gentler shrink didn't help, compressing
expected shots (λ^0.85) did — chosen on PL 2025-26, checked on La Liga (unseen). Walk-
forward 2025-26, all four leagues beat the role-average guess on ≥2 shots, ≥1 on target and
≥2 on target, and on-target chances are calibrated (e.g. PL 45% → 46%, La Liga 74% → 76%).

## D-032 — Serie A and Bundesliga, same method · 2026-10-15 · accepted
Added through `corridor.leagues` only (FotMob 55 / 54, Understat `Serie_A` / `Bundesliga`,
odds `I1` / `D1` with aliases; an alias falls back to the plain name for other eras). The
updater now derives its league list from the config. Each league's lines, proof, tiers and
team-news test use its own matches; prediction settings stay PL-frozen. **Results:** the
six metrics that decide matches in *every* league are chance quality created and conceded,
big chances created and conceded, and shot quality at both ends; extras: PL distance vs
opponent, La Liga counter-attack chances / shots conceded, Bundesliga shots conceded / box
touches. Predictions RPS vs bookmakers — PL 0.205/0.198, La Liga 0.194/0.192, Serie A
0.193/0.190, Bundesliga 0.201/0.198. Team news helps in the PL and Bundesliga, slightly
hurts in La Liga and Serie A (819 matches: 0.193 → 0.194) — applied per league (D-031).
The Bundesliga has 18 teams (projection shows "bottom 3 incl. play-off"). `next_round` now
ends when a team would appear twice (it had pulled in the next Bundesliga round's first
fixture). The single page is ~6.4 MB with four leagues.

## D-031 — Team news only where its own test shows a gain; La Liga live · 2026-10-15 · accepted
The clean test of the PL-frozen team-news weight on 837 La Liga matches made predictions
slightly worse (RPS 0.1934 → 0.1942) and pointed the wrong way in big-gap matches (home
sides missing much more won 64% vs 54% predicted). So the adjustment is applied per league
only if every one of that league's out-of-sample tests shows a gain (`team_news_applied`):
on in the PL (both cross-season tests positive), off in La Liga. Team news is still shown
everywhere, and the adjusted version is logged (`p_with_news`, `rps_with_news`) so the
record can overturn this. **La Liga results:** the decisive metrics are almost the same as
in England (chance quality created / conceded, big chances both ends, shot quality); Spain
adds counter-attack chances conceded and shots conceded; territory, final-third passes and
PPDA decide nothing in either league. Core lines: all 5 elite → won 83% (186), all 5 worst
→ lost 79% (337). **Fixes found on the way:** FotMob spells some clubs differently on match
pages ("Atletico Madrid") and in fixture lists ("Atlético Madrid"), which broke the
Understat join for Atlético and Alavés — team names now come from the fixture list by team
id (La Liga joins 760/760, 758/760, 156/156); slugs strip accents; FotMob line-ups have four
states (official "standard", "predicted", "lastStarting11", "unavailable"), all shown.

## D-030 — Cards and assists in the match preview · 2026-10-15 · accepted
The parser now records team yellow / red cards and fouls (conceded too), the referee, and
each player's cards (from card events; a second yellow = one yellow + one red).
**Team cards** (`preview.card_walk`): rolling yellows received and drawn, opponent-adjusted,
plus a referee factor shrunk with 8 average games. Walk-forward on 440 PL matches: which
side gets more yellows is predictable (61%), but the **match total is not** (correlation
0.06 — worse than the league average) and the **referee factor made it slightly worse**
(PL referees are consistent: the strictest books ~16% above average). Red cards: no better
than the league rate. So the page shows each side's expected yellows and "more yellows",
totals and reds at league rates, and the referee for information only.
**Players:** the shooter model also carries expected assists per 90 (270-minute prior) and
bookings per 90 (900-minute prior — rare events). Walk-forward 2025-26 (7,600 starts):
assist Brier 0.0666 vs 0.0673 position average, booked 0.1310 vs 0.1324; both calibrated.
Match page: Shots, goals & assists (≥1 shot, goal, assist, goal or assist), Cards (expected
yellows, more-yellows chances, total lines, red at league rate, three most likely to be
booked per side, referee).

## D-029 — La Liga: same method, measured on its own matches · 2026-10-15 · accepted
`corridor.leagues` defines each league (FotMob id, Understat slug, football-data code,
data sub-folder, focus team). La Liga: FotMob 87, Understat `La_liga`, odds `SP1`, data
under `processed/{season}/laliga` and `site/{season}/laliga`, **no focus team → no
analyst**. Every script takes `--league`; `update` also watches La Liga (and UCL matches
of Spanish sides) and skips the United analyst when only La Liga changed.
**Same method, separate numbers:** La Liga's lines come from last season's La Liga top /
bottom four, its proof and tiers from La Liga matches only, nothing borrowed from England.
**Prediction settings are not re-tuned:** the PL-frozen settings (D-023, D-026, D-027) are
applied unchanged — a clean out-of-sample test of the method. Result, 2020-21…now (2,358
matches): RPS 0.1940 vs bookmakers 0.1922 and base rates 0.2255 (closer to the market than
in England), well calibrated; over 2.5 Brier 0.2414 vs 0.2498 base / 0.2382 bookmakers. The
PL team-news weight is tested on La Liga's own matches (`team_news_test`).
**Missing data:** FotMob has no running data or line-breaking passes for La Liga; those
metrics and player columns are left out, not estimated. **Page:** one site, both leagues;
routes `#<league>[/team/<slug>|/match/<id>]`, old `#team/…` links mean the PL; menu per
league; "How we know" opens with a side-by-side comparison of both leagues and a switch for
the detail sections. First download: ~840 FotMob pages, ~2 h at FotMob's response times.

## D-028 — "How we know" is its own page · 2026-10-15 · accepted
The proof section sat on every team page although it is league-wide (lines from last
season's top/bottom four, tested on every PL team-match); only its "United typical" column
was team-specific, and the team page's tiers already show that. The prediction backtest sat
at the bottom of the overview. Both now live on `#how`, reachable from a menu on every view
(Premier League · focus team · How we know), together with how the team-news adjustment,
shooters, corners and goal lines were tested (frozen team-news test in `absences.TEST`)
and the data sources and caveats. Team pages and the overview link to the right section.

## D-027 — Scoreline model for goal lines · 2026-10-15 · accepted (1X2: revisit)
Poisson goals per side (scikit-learn PoissonRegressor on the same pre-match ratings:
own npxG / goals for, opponent npxGA / goals against) with a Dixon–Coles low-score
correction → a scoreline matrix → most likely scores, over 1.5 / 2.5 / 3.5, both teams to
score, clean sheets. Raw rates were over-confident (74% "over 2.5" happened 62%), so rates
are shrunk towards the league mean in log space; the factor 0.7 was chosen on 2016-17…
2019-20. Held-out 2020-21…now: over 2.5 Brier 0.2435 vs 0.2476 base rate, bookmakers
0.2414; BTTS 0.2476 vs 0.2490. **Win/draw/loss stays with the logistic model**: it won on
the tuning seasons (RPS 0.1917 vs 0.1923) although the unshrunk goals model was better on
the held-out ones (0.2025 vs 0.2046) — switching on held-out evidence would be choosing by
the test set; revisit with a fresh tuning protocol. **Alignment (same day, after the user
spotted it):** scorelines first came from the goals model alone, so Leeds–United showed
Leeds favourites (45/25/30, with team news) but 1–2 above 2–1. Now the goals model sets the
expected *total*, and the split between the sides is solved so the matrix's home-minus-away
win chance equals the published prediction (team news included). Held-out: over 2.5
unchanged (0.2435), 1X2 0.2054 → 0.2046, exact-score log loss 2.9862 → 2.9855. The page
also explains why the single likeliest score can be a draw while one side is favourite. Matching only the
home-minus-away gap left draws up to ~3 points off, so the home-win, draw and away-win
scorelines are then each rescaled to sum exactly to the published chances (`reconcile`);
held-out over 2.5 0.2434, exact-score log loss 2.9864. Applies to every fixture.

## D-026 — Team news in the prediction (one parameter) · 2026-10-15 · accepted (watch)
`corridor.absences`: FotMob lists each side's unavailable players on every match page, so
the cached pages give 820 past PL matches (2024-25 → now) of team news. Each absent
player is weighted by his share of the team's minutes and of its chance creation (npxG +
xA), counted only over earlier matches (last season at half weight). Tests: re-fitting a
stacked model on one season *hurt* (overfit), so the adjustment is a single parameter —
home-win odds × exp(k·d), away-win odds × exp(−k·d), d = away minus home share of usual
minutes missing. k fitted separately on 2024-25 (1.74) and 2025-26 (1.90) → 1.8. Out of
sample the gain is small and not significant (+0.0007 and +0.0022 RPS, CIs include 0;
−0.0026 on this season's 60), right direction in the 63 big-gap matches (home side
missing much more: base 38%, adjusted 30%, actual 20%). Adopted because the direction is
stable and both versions are logged: the running record shows RPS with and without team
news, so it can be dropped if it doesn't pay. Using output share or both shares overfit.

## D-025 — Who takes the shots (player shot quality) · 2026-10-15 · accepted
Per player, from the shot map: non-penalty shots, npxG per shot vs the league average for
his role, distance, outside-box / blocked / headed shares, and **npxG wasted** = shots ×
role-average quality − actual npxG; summed it splits the team's shot-quality gap by
player (United: 0.45 per match, most in the league — Cunha +1.49, Rashford +0.64, the
centre-backs and Dalot shooting from range; Mbeumo −1.04). Defending can't be split the
same way (no per-player attribution of chances allowed), only "errors leading to a goal"
is shown. The parser now records per-player shot detail and uses the match's own team
names — FotMob's player blocks said "Bournemouth" / "Brighton and Hove Albion", which had
silently emptied those two teams' player tables and team-news shares since D-022.

## D-024 — Stage 5: match previews (team news, line-ups, shooters, corners) · 2026-10-15 · accepted
Clicking a next-round fixture opens `#match/<id>`: the prediction, **team news** (FotMob's
pre-match "unavailable" list: type, expected return, the player's minutes and share of the
team's npxG + xA this season), **line-ups** (FotMob's last starting XI until the official
one is out, ~1 h before kickoff; players now out are struck through), **likely shooters**
and **corners**. Built by `scripts/previews.py` after `predictions` (one FotMob request per
fixture per run). The parser now records team corners and per-player non-penalty shots,
shots on target, npxG (from the shot map), penalties and non-penalty goals.
**Shooters:** shots and npxG per 90 this season + last (half weight), shrunk towards the
role average with 270 minutes of prior, × usual minutes when starting × the opponent's
shots / npxG conceded relative to the league; Poisson for P(≥1 shot) and P(non-pen goal),
"if he starts". Walk-forward on 2025-26 (7,600 starts): Brier 0.207 vs 0.220 for a role
average; goal chances calibrated. **Corners:** opponent-adjusted rolling corners won /
conceded (30-match half-life, chosen on 2025-26). Honest finding: a side's corners are
predictable (MAE 2.07 vs 2.15; the expected "more corners" side wins them 62%), the match
**total is not** (correlation 0.06; worse than the league average), so totals use the
league average. **Absences are shown, not used** in the win/draw/loss model: there is no
injury history to test an adjustment against; shooter lists drop players who are out.

## D-023 — Stage 4: pre-match predictions, honestly tested · 2026-10-15 · accepted
**Ratings** (`corridor.predict`): every team carries exponentially weighted Understat
non-penalty xG for/against, goals for/against and the share of the 5 core elite / worst
lines reached (lines from the previous season). Each match is **opponent-adjusted** before
it updates a rating (1.5 npxG against a side that concedes 2.0 counts as below par).
Ratings update only *after* a match; summer carry-over and a promoted-team prior (the
relegated teams' ratings) handle new seasons. **Model:** multinomial logistic regression
(scikit-learn, L2) on rating differences → P(home/draw/away).
**Protocol:** settings (half-life, carry-over, opponent adjustment, feature set, L2) tuned
on 2016-17…2019-20 only, then **frozen** (`PARAMS` in `scripts/predictions.py`: 24-match
half-life, full carry-over, opponent-adjusted, xG+goals+lines, C=0.05). Held-out
2020-21…now, each season trained only on earlier ones: **RPS 0.205** vs base rates 0.234
and bookmakers 0.198 (pre-match average) / 0.197 (closing); favourite won 53% vs the
market's 54%. Calibrated, slightly over-confident above ~65%. The line features add almost
nothing beyond xG + goals (honest result, kept because tuning chose them). A wider grid
fit the tuning seasons better but not the held-out ones, so we stopped tuning there.
**Live:** after every build, the next round is predicted, the rest of the season simulated
(20,000 runs from fixed ratings: projected points, title / top-4 / relegation odds), and
each prediction is **frozen at its last pre-kickoff version** in `predictions_log.json` and
scored after the match against the market. Known limit: ratings move slowly, so early in a
season they lean on last season (e.g. United 41% to win at Leeds after a poor start).
Odds come from football-data.co.uk and are used only as a benchmark (DATA_SOURCES.md).

## D-022 — Premier League overview + a breakdown for every team · 2026-10-15 · accepted
The site now opens on a Premier League overview; every team gets the same breakdown United
has (focus tiers, proof, match table, stacks, players, UCL tab if they play in it). The
**analyst stays United-only** (the user's team; it costs ~3 min / ~200k tokens a run).
`united_profile` builds all 20 teams in one pass (lines and proof computed once, placed per
team) and writes `league.json` (all teams + overview table) next to `profile.json` (focus
team + shared proof, still the analyst's input). Understat rows are joined to FotMob
team-matches by day + score + Understat PPDA + deep completions for/against — score and
deep completions alone mixed up two 2-2 draws on the same day.
**Overview:** a table sorted by any column — points, **deserved points**, points minus
deserved, xG, the 7 decisive metrics (elite / between / relegation level), elite and danger
scores, stack percentiles, form — plus an elite-vs-danger scatter and a points-vs-
performance chart. **Deserved points** per match = mean of 3·W + D over the historical
bins for the match's elite score and its danger score (FotMob weighted record); it
describes performances, it is not yet a prediction. Hash routing (`#team/<slug>`) keeps it
one static page (~1.5 MB). **Automation:** `update` now rebuilds after any finished PL
match and any UCL match involving a PL team, not just United's.

## D-021 — Page refocused on what decides matches; impact-weighted lines · 2026-10-15 · accepted
The page listed 29 metrics with equal weight, so United's strengths (territory, PPDA,
passes into the final third) visually balanced weaknesses that matter far more. Each
metric now gets an **impact** = mean of its best-line lift and worst-line lift on the
FotMob out-of-sample record, and a tier: **decides matches** ≥ 0.20, **helps a little**
0.10–0.20, **doesn't decide matches** < 0.10 (provisional if < 300 tested team-matches,
i.e. running metrics). Outcome-linked metrics and line-breaking passes stay untiered.
**Weighted score:** share of lines reached with each line weighted by its lift (floored
at 0). Checked walk-forward — weights learned only from earlier seasons: Understat AUC
for wins 0.675 → 0.714 (7,720 team-matches, 2016-17→now), losses 0.705 → 0.738; FotMob
this season 0.64 → 0.73 (120). Top-group win rate is unchanged (85%), so the 90% target
is still not met. FotMob weights/bins used to place United's matches come from the full
record (in-sample for the bins; the walk-forward test is what justifies weighting).
**Page order:** record → What decides matches (tiers, each metric on a worst→elite gauge;
the no-effect tier collapsed) → analyst → How we know (proof) → match table (elite/danger
scores + the decisive metrics, shaded by line) → every metric by stack (sorted by impact,
tagged) → players. The rule-based percentile verdict and the separate "Against the
lines" section are gone. The analyst gets `what_decides_matches` and a per-metric
`decides_matches`, and is told to build the read around the decisive tier.

## D-020 — Stage 3: worst line + out-of-sample proof · 2026-10-15 · accepted
**Worst line** mirrors D-019: median of every metric over the previous season's bottom
four's league *defeats*, minus defeats where they were down to 10 men before the 70th
minute (2025-26: Spurs, West Ham, Burnley, Wolves; 76 defeats, 8 excluded). Hitting it =
relegation level. `best_line.py` is now generic (`side="best"|"worst"`, any rows/metrics).
**Proof** (`corridor.proof`): for each pair of consecutive seasons, lines from season N are
tested on *every* team-match of N+1 (never on the games that built them). Per match: share
of lines reached / sunk to → outcome rates by share bin, the share needed for the 90% W /
85% L targets (min 30 matches), and each line's lift (win rate when reached − when not).
Two datasets, never mixed: Understat 2014-15→now on 5 core metrics (8,480 team-matches)
and FotMob 2024-25→now on the profile metrics (880). Goals prevented, finishing (xGOT−xG)
and big chances missed are excluded from the proof — they partly contain the result.
Running lines can only be tested on 2026-27 (no tracking before Dec 2025).
**Findings (honest):** the 90% win target is *not* met: all 5 core best lines → 85% won
(164). The 85% loss target *is* met: all 5 core worst lines → 85.2% lost (378). Lines differ
hugely in what they predict: chance quality for/against, big chances, shot quality and
distance vs opponent separate wins; territory, passes into the final third, PPDA, sprints
and recoveries barely do. Caveat on the page: whole-match numbers are partly shaped by the
score (game state), so this is association, not cause. This replaces TDP's single npxGD
corridor (D-009) as the user-facing proof; the pgvector engine stays unused for now.
Possible next step: weight lines by out-of-sample lift (select on early seasons, test on
later ones) instead of counting them equally.

## D-019 — Stage 2 best line: last season's top-4 wins, median per metric · 2026-10-15 · accepted
Chosen with the user. **Elite** = the previous season's final top four (2025-26: Arsenal,
Man City, Man United, Villa — United's own 3rd place included). **Best games** = their
league wins, minus wins where the opponent was sent off before the 70th minute (11 v 10
for 20+ min inflates possession/territory; 3 excluded). **Line** = median of each metric over
those wins; the middle half (p25–p75) is the "elite range". Fixed for the season, rebuilt
each summer from `data/processed/{season-1}` (needs a one-off `build_season --season
<prev>`, ~10 min). "Reached" = at least as good as the median; gaps are also expressed in
elite-range units so metrics with different scales can be ranked. Running metrics rest on
the ~57 wins with tracking (FotMob tracking starts Dec 2025).
**Cross-season guard:** if a metric's league-wide mean moved > 0.5 SD between seasons, the
provider changed its definition and the metric gets no line — FotMob's line-breaking
passes went from a median of 52 to 93.5 (+1.9 SD). PL only: the UCL has different
providers and no previous-season pool. Supersedes TDP's 90%-win cohort as the *displayed*
line for now; the empirical 90%-win proof stays for stage 3.

## D-018 — Post-match updates: local launchd + a background Claude session publishes · 2026-10-15 · accepted
`corridor.scripts.update` runs twice a day (10:31, 14:31 local — when the Mac is awake) from
a user launchd agent (`ops/launchd/`). It refreshes the PL + UCL fixture lists and only
rebuilds when United have a new finished match whose data is in: tried from 3 h (PL) / 12 h
(UCL) after kickoff, and it checks the slow sources actually have the match (Understat PPDA,
UEFA tracking ~17 h) before the expensive steps, waiting up to 72 h. A late UCL match
usually lands the next day at 14:31 or the morning after. Then build_season (pl, ucl) → united_profile
→ analyse (one retry; on a second failure the stale read is moved aside so the page never
shows text about older numbers) → build_site. Publishing needs Claude's Artifact tool, which
`claude -p` lacks but a `claude --bg` session has: the script starts one with a narrow
"publish this file to this URL, nothing else" prompt and removes the previous run's
session. Rejected: a cloud routine (scraped data + LLM key would have to live in the cloud,
and every run would re-scrape from scratch) and in-session cron (dies with the session,
7-day cap). Trade-off: the Mac must be on; missed runs fire on wake. State:
`data/site/{season}/update_state.json`; logs: `data/logs/update.log`.

## D-017 — Champions League: FotMob events + UEFA tracking, own pool · 2026-10-15 · accepted
UCL matches are built separately (`build_season --competition ucl` → `data/processed/{season}/ucl/`).
Event stats and the shot map come from FotMob (league 42, same parser as the PL); physical
data comes from UEFA's match centre, joined on date + score + team-name similarity. United
are ranked only against the other UCL team-matches (36 teams), never against PL numbers:
different tracking providers measure distance and sprints differently. Metrics a
competition lacks are skipped (no PPDA / deep completions: Understat covers leagues only).
UCL-only metrics: running without the ball, scaled to 50% opponent possession
(`km_oop × 50 / opp_possession%`, so possession neither flatters nor punishes it), and
high-intensity runs. UCL players and a UCL analyst read are not done yet (UEFA player
stats need a name join; 2 matches is too few for a written read).

## D-016 — Rank on the typical (median) match; flag one-match skew · 2026-10-15 · accepted
With 6 matches one freak game carries a mean: United's npxG was 5th on average but 13th on
the median, because of 3.99 vs Ipswich. 84 of 580 team-metric ranks moved ≥5 places
between mean and median. Every team's season value is now its **median match**, and rank,
percentile, league average/best/worst and stack scores use it. The mean is kept as
`season_average` with its own rank. `skew` finds the match whose removal moves the mean
most and flags the metric when dropping it moves the average-based rank by ≥ max(3,
teams/5) places (only with ≥4 matches). The page tags such metrics "skewed" and names the
match; the analyst must name it when it quotes the average. Considered: trimmed mean
(similar ranks, harder to explain) and pooled totals (worse: weights the big game more).

## D-015 — Close the analyst's guessing gaps: shot map, context facts, claim critic · 2026-10-14 · accepted
The number check (D-014) let qualitative guesses through ("shots from distance", "possession
teams run less", "presses only the big sides"). Three fixes:
1. **More data.** FotMob's `shotmap` is parsed per team (penalties and own goals excluded,
   105 x 68 m pitch): shot distance, outside-box share, blocked share, set-piece and
   fast-break npxG, goals by type. Plus big chances missed, shots conceded and sprints vs
   opponent. 9 new ranked metrics (28 in total).
2. **Context facts** pre-computed in `profile._context`: goals by type, possession vs
   distance correlation across all team-matches (and distance among ≥55% possession
   teams), PPDA vs top-half / bottom-half opponents, opponent league position per match.
   A `not_measured` list (shape, line height, press triggers, off-ball runs, chance
   creation, errors, morale, player shooting) tells the model what it must not assert.
3. **Critic pass.** After the number check passes, a second LLM call lists claims the fact
   sheet does not support; they go back to the writer as problems. On the last attempt,
   flagged interpretations / player notes are dropped (logged in `meta`) rather than
   failing; flags in facts, headline or summary still fail the run.
Cost: the critic roughly triples a run (~4 min, ~170k tokens with `discretestack-max`).
`--critic-model discretestack-fast` is ~10 s per check but missed some claims in testing.

## D-014 — AI analyst: code computes, LLM writes, code checks · 2026-10-14 · accepted
The written season read is generated at build time (once per update, not per visitor) by an
OpenAI-compatible LLM (user's own DiscreteStack endpoint, `discretestack-max`; configured in
gitignored `backend/.env`). `analyst/facts.py` builds a fact sheet with every quotable number
pre-computed and pre-rounded (incl. comparisons like "out-run in 5 of 6"); the model may not
do arithmetic. `analyst/validate.py` rejects output containing any number not in the fact
sheet (at the quoted precision), unknown metric keys or players; the writer retries with the
problems as feedback (max 3). Facts and interpretation are separate fields and the page labels
interpretation as "Reading". An interactive "ask the analyst" box is deferred: it needs a
server so the key never reaches the browser.

## D-013 — Stage 1 is a United-only static page from FotMob + Understat · 2026-10-14 · accepted
After a scope reset with the user: the goal is answering "why are United bad?", not a SaaS.
Season profile ranks United against all 20 PL teams per metric; players are compared within
their real role (CB/FB/CM/AM/W/ST from FotMob's line-up grid). Scraped data never enters git
(public repo). The pgvector corridor engine (D-001–D-011) is kept for the later "proof" stage.

## D-012 — Synthetic-first data strategy · 2026-10-14 · accepted
Free sources can't supply most of the 12 dimensions (physical tracking, line breaks, xGOT,
PSxG, box touches). The whole engine is built and tested on a seeded synthetic generator
(`corridor.synthetic`) whose paired metrics mirror real constraints (A's npxG conceded = B's
npxG created, field tilt sums to 100, goals ~ Poisson(post-shot xG)). Real providers come
later behind an adapter interface. **Revisit** when picking a data provider (WP1.2/1.3).

## D-011 — Recalibration re-vectorizes every stored row · 2026-10-14 · accepted
Z-scores depend on the benchmark window's μ/σ, so vectors computed under different
corridor versions are not comparable. `calibrate()` writes a new `benchmark_corridors` row,
deactivates the previous one, and rewrites `stats_vector` + scores for **all** rows in the
same transaction (~9 s for 19k rows). Simpler than per-version vector tables; fine until
row counts are in the millions.

## D-010 — Twin search excludes the audited match and the future · 2026-10-14 · accepted
`find_twins` filters `kickoff_utc < audited kickoff` and `match_id <> audited match` (which
removes the opponent's mirrored row too). Uses pgvector ≥ 0.8 `hnsw.iterative_scan =
strict_order` so filters can't starve the k = 50 result. `kickoff_utc` is denormalized onto
`team_match_performances` for this.

## D-009 — Corridor cohorts via logistic fit on npxGD · 2026-10-14 · accepted · revisit
TDP's definition ("npxGD ≥ +1.60 … where teams win ≥ 90%") is circular. We fit
P(win | npxGD) and P(loss | npxGD) with 1-D logistic regressions and take the widest tail
cohort whose *fitted* mean outcome rate meets the target (90% W / 85% L); centroid = mean
vector of that cohort, floor of 30 rows. An earlier "scan down from the top" approach was
rejected: one result in the thin tail broke the scan and 365-day windows were unsolvable.
"Positive stack alignment" from TDP is not applied yet.
**Open issue:** on a 365-day window the 90% win cohort is only ~1% of performances (~30
rows). Options: longer window for the lines (keep 365 d for μ/σ), lower target, or accept.

## D-008 — Similarity % is relative to corridor width · 2026-10-14 · accepted
`similarity_pct = 100 · max(0, 1 − d / ‖v_best − v_worst‖)`. 0 distance → 100%, a twin as
far away as the whole corridor → 0%. TDP showed values but never defined the formula.

## D-007 — Badge rules and precedence · 2026-10-14 · accepted
Evaluated in order, first match wins:
1. `MIRAGE_WIN` — points = 3 and (twin win% ≤ 22 or ≥ 2 vetoes)
2. `UNLUCKY_LOSS` — points = 0 and twin win% ≥ 75
3. `ELITE_90_STANDARD` — C ≥ 82, twin win% ≥ 88, 0 vetoes
4. `SYSTEMIC_COLLAPSE` — C ≤ 20 or ≥ 2 vetoes *(TDP named this badge but never defined it)*
5. `MID_TABLE_STANDARD` — otherwise

Veto threshold: stack score **≤ 20.0** (TDP), not < 18.0 (ARCHITECTURE).
Veto flag names derive from the stack score column: `STACK_01_WORK_RATE_VETO`, etc.

## D-006 — Feature weights: TDP values, single source in code · 2026-10-14 · accepted
The two docs disagree on 5 of 12 weights. We use TDP's (1.8 / 1.4 / 1.2 / 1.0 tiers). The
only definition lives in `corridor/engine/metrics.py`; the active weights are also
snapshotted into each `benchmark_corridors.metric_weights` row. Clip ±4.5 applies *after*
weighting (per TDP formula) — note this means a 1.8-weight metric clips at |z| = 2.5.
**Revisit** once we can tune against real outcomes.

## D-005 — Player effort: re-ranked composite, no gap band · 2026-10-14 · accepted
Composite = 50% mean physical percentile + 50% mean event percentile, then **re-ranked**
within the positional cohort (averaging percentiles compresses toward 50, so the raw
average almost never reaches 85). Bands: `WORKHORSE_ELITE` ≥ 85, `PASSENGER_ALERT` < 15,
`STANDARD_SHIFT` otherwise (closes TDP's undefined 15–20 gap). Players without physical
tracking are scored on event work rate alone. GK excluded. `progression_corridor_score`
dropped from the schema (never defined). `final_third_regains_per_90` is stored but not
scored.

## D-004 — Missing metrics impute to the benchmark mean · 2026-10-14 · accepted · revisit
Nullable physical columns; a missing metric gets z = 0 so it neither helps nor hurts
similarity. Revisit if most rows lack physical data (distance then concentrates on 10 dims).

## D-003 — Merged schema · 2026-10-14 · accepted
Base: TDP §5 (12 explicit rate columns, `competition_code`, `audit_status`, `league_code`,
`elo_rating`). Added from ARCHITECTURE: `raw_metrics JSONB` (provenance). Added new:
`goals_for/against`, denormalized `kickoff_utc`, `venue`, corridor `window_start/end_utc`
and `calibration JSONB`, snapshot `schema_version`. Scores/vector nullable until a corridor
exists. `audit_status` gains `HISTORICAL` for backfilled matches. No table partitioning
yet (ADR-07): the player table has no vector index, and row counts are small.

## D-002 — Plain SQLAlchemy 2.0 + Alembic (no SQLModel), sync psycopg 3 · 2026-10-14 · accepted
SQLModel adds little over typed SQLAlchemy 2.0 here and is awkward with pgvector types.
The write path is a short batch job, so sync psycopg 3 is enough. Alembic migrations are
the DDL source of truth; `alembic check` must report no drift against the models.

## D-001 — Repo layout: `backend/` uv project with `src/corridor` package · 2026-10-14 · accepted
Python project lives in `backend/` (own `pyproject.toml`, `uv.lock`, `alembic.ini`), with
`engine/` (pure NumPy, no DB), `db/`, `synthetic/`, `scripts/`. `frontend/` (Next.js) will
sit alongside. Local Postgres on port **5433** to avoid clashing with a host Postgres.
LLM autopsy will use a current Claude model, not the docs' Claude 3.5 Sonnet / GPT-4o.
