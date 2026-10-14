# Data Sources — recon of 2026-10-14

Everything below was verified by actually fetching data for Man United's 2026-27 matches,
except where marked "unverified". Prices were checked on official pages where reachable.

## Free sources that work

### FotMob — main per-match source (PL)
- `www.fotmob.com/api/data/teams?id=10260` (United fixtures), `/api/data/matchDetails?matchId=…`,
  `/api/data/leagues?id=47&season=YYYY/YYYY`. Plain user agent, no auth.
- Team: possession, xG, xGOT, shots, big chances, box touches, opposition-half passes, tackles,
  interceptions, duels, **distance, running/sprinting distance, sprints** (`physical_metrics`).
- Player: minutes, position, xG, xA, line-breaking passes, passes into final third, recoveries,
  duels, box touches, **distance, sprints, top speed**; GK xGOT faced + goals prevented.
- History: xG/xGOT from ~2024-25; physical patchy in 2025-26, complete for United 2026-27.
  Not seen in latest Bundesliga/LaLiga matches checked.
- Sample (MUN 1-1 TOT, 10 Oct 2026): xG 0.80 v 1.62, xGOT 0.61 v 1.38, big chances 1 v 4,
  box touches 23 v 32, distance 112.1 v 116.8 km, sprints 111 v 126.
- Risk: unofficial, paths already changed once (`/api/matchDetails` → 404), robots.txt
  disallows `/api/*`, ToS forbids scraping. Store raw JSON for every match.

### Understat — history for the "teams like this win X%" model
- JSON endpoints need `X-Requested-With: XMLHttpRequest`: `/getTeamData/{team}/{season}`,
  `/getMatchData/{id}` (every shot with x/y, xG, situation), `/getLeagueData/{league}/{season}`.
- Team per match: xG, npxG, xGA, npxGA, xPts, **PPDA inputs**, deep completions.
  Player: xG, xA, xGChain, xGBuildup.
- History: top 5 leagues + RFPL **since 2014-15** (≈ 12 seasons) — the only free multi-season source.
- Sample (MUN 1-1 TOT): xG 0.87 v 2.03, PPDA ≈ 7.6 (260/34), deep 8 v 9.
- Risk: unofficial, endpoints changed recently, robots.txt `Disallow: /`.

### UEFA — Champions League matches
- `match.uefa.com/v5/matches?competitionId=1&seasonYear=2027…` (United id 52682),
  `matchstats.uefa.com/v1/team-statistics/{id}`, `/v1/player-statistics/{id}`.
- ~30 physical metrics team + player (distance in/out of possession, high-intensity runs,
  sprints, top speed…). Available ~17 h after kickoff. Physical history back to ≥ 2019-20
  (distance + top speed only then).
- Sample (ATM v MUN, 13 Oct 2026, United): 112.2 km, 129 sprints, 726 HI runs, top 35.3 km/h.

### Premier League official API — not useful this season
- `sdp-prem-prod.premier-league-prod.pulselive.com/api` (`v2/matches`, `v3/matches/{id}/stats`).
- Team-level `totalDistance` + fastest player existed in 2025-26 but are **empty for all of
  2026-27**. No player-level physical data.

## Blocked / not usable for free
FBref (Cloudflare 403; Opta advanced data removed Jan 2026), Sofascore (403), WhoScored (403).
StatsBomb open data: full event data but no current PL season.

## Metric coverage vs our 4 stacks (free)
| Stack | Metric | Source |
| --- | --- | --- |
| Work rate | distance, sprints | FotMob (2026-27 only), UEFA |
| | PPDA | Understat |
| | high turnovers / final-third regains | ❌ |
| Progression | field tilt | ⚠️ proxy: FotMob opp-half passes / summed final-third passes |
| | line-breaking passes, box touches | FotMob |
| | progressive carries | ❌ |
| Attack | xG, npxG, xG/shot, big chances | Understat / FotMob |
| | xGOT (finishing) | FotMob |
| Defence | xGA, xGA/shot | Understat / FotMob |
| | GK goals prevented | FotMob |

## Rules that follow from this
- **Never mix providers within one comparison.** xG differs (FotMob 0.80 v Understat 0.87 for
  the same match); distance differs (FotMob 108.6 km v PL 105.3 km for Brighton–United).
- Physical data has no free history → running comparisons can only be against other teams
  in the **same season** from the same provider.
- Low-volume, personal use only; scraping these sites for a public product is legally weak.

## Paid options (prices 2026-10-14)
| Provider | What it adds | Price | Notes |
| --- | --- | --- | --- |
| Sportmonks Starter + xG bundle | Licensed xG/npxG/xGOT, final-third passes, recoveries, duels; 5 leagues | ≈ €40–53/mo | xG only from 2024; no PPDA, box touches, physical |
| Sportmonks Growth + xG + history | 30 leagues | ≈ €105/mo | still no physical |
| API-Football | basic stats, xG (unverified) | $19–39/mo | site blocked; unverified |
| football-data.org | fixtures/results, basic stats, no xG | free / €29+ | |
| DataMB Pro | PPDA, progressive passes percentiles (view only) | €9.99/mo | no export |
| Wyscout individual | event metrics in platform | ≈ €300–400/yr | viewing licence, not data |
| StatsBomb / Opta / Sportradar | full event data | not public; ≈ £3k+/yr | B2B |
| SkillCorner / Second Spectrum | physical tracking | not public | B2B only |

**Conclusion:** paying ~€50/mo buys *legality and stability*, not better data — none of the
affordable options adds physical data, PPDA by zone or progressive carries. Stay free while
the site is personal; revisit if it goes public.
