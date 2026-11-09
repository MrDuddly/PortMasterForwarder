# Metadata rules

Implemented in `src/portmasterforwarder/meta.py` (rules) and `src/portmasterforwarder/core.py` (sources and writing). Everything generated is **English**.

## 1. Genres

Exactly **one** value from this list is ever written (`meta.GENRES`):

`Action` - `Platformer / Platform` - `Adventure` - `RPG (Role-Playing Game)` - `Shooter / Shmup` - `Fighting` - `Beat 'em Up` -
`Racing / Driving` - `Sports` - `Puzzle` - `Strategy` - `Simulation` - `Pinball` - `Card Game / Board Game` - `Music / Rhythm`

`normalize_genre(labels, text)` maps labels from Steam, Wikidata and RAWG (and, as weak hints, words in the description) to one of them:

- Each label is matched against ordered rules (weight 5 for specific labels such as *platformer*, *first-person shooter*, *role-playing*; 3 for *adventure*; 2 for the generic *action*).
- Exact canonical names (or short aliases such as `rpg`, `platform`) add 6, except generic *Action* (2) and *Adventure* (3).
- Description cues add up to 3 points per genre, and self-descriptions such as "super-tight platformer" or "farming sim" add 4.
- The highest score wins; ties go to the more specific genre. The result is accepted when the score is at least 4 **or** a source label itself names the genre. Otherwise the genre stays **empty** - it is never guessed.
- *Action-adventure* is mapped to **Adventure** (exploration and puzzles are the primary activity); *metroidvania* to **Platformer**.

Existing non-standard genres are reported but never overwritten silently (only *Replace* mode or your own pinned value changes them).

## 2. Descriptions

English, about 2-4 sentences, describing **only what the game is like to play**.

`build_description(texts)` takes sentences (highest-priority text first: Wikipedia *Gameplay* section, then Steam description, RAWG, Google) and keeps a sentence only if it:

- is 35-320 characters, mostly English, and contains at least one gameplay cue (explore, fight, jump, collect, solve, build, race, shoot...);
- contains **none** of the banned terms: platform/console names, release and franchise history (released, sequel, series, remake...), technical details (graphics, engine, resolution...),
  story words (story, journey, villain, kingdom...), awards/sales, marketing and links, or a year.

At most 4 sentences / about 520 characters are kept. If nothing qualifies the field stays **empty**. Your own text is never filtered (a note is logged if it mentions non-gameplay details).

## 3. Ratings

Stored in EmulationStation's `0.00-1.00` format, derived from a **0-10** score.

### Rule-based estimate (default)
Signals (`meta.collect_signals`), each with a weight:

| Signal | Score | Weight |
|---|---|---|
| Metacritic | score / 10 | 1.0 |
| Wikidata review scores (average) | ratio x 10 | 0.6 (1.0 if no Metacritic) |
| Steam players (>= 10 votes) | `2 + 8 x max(0, (L - 0.4) / 0.6)`, L = Wilson lower bound of the positive ratio | `min(1, votes / 200)` |
| RAWG players | rating x 2 | `0.25 + 0.25 x min(1, count / 100)` |
| Google aggregate rating | ratio x 10 | 0.4 |

`score = (sum(w x s) + 6.5 x 0.4) / (sum(w) + 0.4)` - the neutral prior keeps a single score from being copied. Fame, franchise and release year play no role.
If the total weight is below **0.8** (**0.35** when a block is explicitly set to a single source) **no rating is written**.

### AI evaluation (optional)
With `ai_enabled` and your Anthropic API key, the collected evidence (source texts, genre labels, external scores as *supporting* evidence, a few player-review excerpts) is sent once per game.
The model returns genre, description and a 0-10 score judging gameplay quality, controls, level design, content/replayability and polish, may answer `null` ("not enough information"),
and every field is validated (standard genre, description rules, numeric range). Invalid fields fall back to the rules; an explicit `null` rating means no rating.

## 4. How blocks decide what to do

Per metadata block (`core.plan_fields`), in this order:

1. **Pinned value** (typed or fetched by you) - written, normalized (rating `8.6` -> `0.86`, date `25/01/2018` -> `20180125T000000`, genre must be standard).
2. Source **Keep current** - untouched.
3. Source **Auto** - follows the global mode: *Complete only what is missing* (fill only empty fields), *Replace everything*, or per-game *Keep*.
4. A specific source (Steam, Wikipedia, RAWG, Google, AI) - fetched from that source only, replacing the current value.

Nothing is blanked when no reliable value is found.

## 5. Written fields

`name`, `desc`, `rating`, `releasedate`, `developer`, `publisher`, `genre` and `image` in each category's `gamelist.xml` (existing tags such as `md5` or `id` are preserved).
