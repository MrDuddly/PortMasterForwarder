"""
portmasterforwarder.meta - metadata quality rules for PortMasterForwarder.

* Genre normalization: every game gets exactly ONE genre from GENRES (or none if unknown).
* Gameplay-only descriptions: sentences about platform, release history, franchise,
  technical specs, story or marketing are filtered out. Nothing is invented.
* Ratings: a 0-10 score derived from several signals (never a plain copy of one score),
  or an optional AI evaluation. Converted to EmulationStation's 0.00-1.00 format.

No GUI and no file access here - everything is plain functions that are easy to test.
"""
import json
import math
import re
import urllib.request

# ----------------------------------------------------------------------------
# 1. GENRES  (the ONLY values allowed in the <genre> field)
# ----------------------------------------------------------------------------
ACTION = "Action"
PLATFORMER = "Platformer / Platform"
ADVENTURE = "Adventure"
RPG = "RPG (Role-Playing Game)"
SHOOTER = "Shooter / Shmup"
FIGHTING = "Fighting"
BEAT_EM_UP = "Beat 'em Up"
RACING = "Racing / Driving"
SPORTS = "Sports"
PUZZLE = "Puzzle"
STRATEGY = "Strategy"
SIMULATION = "Simulation"
PINBALL = "Pinball"
CARD_BOARD = "Card Game / Board Game"
MUSIC = "Music / Rhythm"

GENRES = [ACTION, PLATFORMER, ADVENTURE, RPG, SHOOTER, FIGHTING, BEAT_EM_UP, RACING, SPORTS,
          PUZZLE, STRATEGY, SIMULATION, PINBALL, CARD_BOARD, MUSIC]

# Short forms people (or APIs) may use -> canonical value
_ALIASES = {
    "platformer": PLATFORMER, "platform": PLATFORMER, "platformer/platform": PLATFORMER,
    "rpg": RPG, "role-playing game": RPG, "role playing game": RPG, "role-playing": RPG,
    "shooter": SHOOTER, "shmup": SHOOTER, "shoot 'em up": SHOOTER,
    "beat em up": BEAT_EM_UP, "beat 'em up": BEAT_EM_UP, "beat-em-up": BEAT_EM_UP,
    "racing": RACING, "driving": RACING,
    "card game": CARD_BOARD, "board game": CARD_BOARD,
    "music": MUSIC, "rhythm": MUSIC,
}
_CANON = {g.lower(): g for g in GENRES}


def canonical_genre(value):
    """Return the canonical genre for a value that is already (or almost) one of GENRES, else None."""
    if not value:
        return None
    v = re.sub(r"\s+", " ", str(value).strip()).lower()
    return _CANON.get(v) or _ALIASES.get(v)


def is_standard_genre(value):
    """True only for the exact canonical strings."""
    return value in GENRES


# Rules applied to source genre LABELS (Steam, Wikidata, RAWG...). First match per label wins
# for specificity; weights make specific labels beat generic ones ("Action" is weak).
_LABEL_RULES = [
    (r"beat.?'?em.?up|brawler|belt.?scroll", BEAT_EM_UP, 5),
    (r"pinball", PINBALL, 6),
    (r"\bfighting\b|fighter\b|versus fighting", FIGHTING, 5),
    (r"rhythm|music game|music video game|dance", MUSIC, 5),
    (r"card game|card battle|board game|deck.?build|tabletop|mahjong|\bchess\b|collectible card", CARD_BOARD, 5),
    (r"racing|driving|\bkart\b|race game", RACING, 5),
    (r"sports?\b|soccer|football|basketball|baseball|\bgolf\b|tennis|hockey|skateboard|wrestling|boxing|billiards", SPORTS, 5),
    (r"puzzle", PUZZLE, 5),
    (r"metroidvania|(?<!cross-)\bplatform(er|ing)?\b|side.?scroll|run and jump", PLATFORMER, 5),
    (r"shoot|shmup|bullet hell|run and gun|run 'n' gun|twin.?stick|\bfps\b|\btps\b", SHOOTER, 5),
    (r"role.?playing|\brpg\b|\bjrpg\b|\bcrpg\b|dungeon crawl", RPG, 5),
    (r"strategy|tactic|\b4x\b|tower defen[cs]e|\brts\b|\bmoba\b|wargame", STRATEGY, 5),
    (r"simulat|management|farming|life sim|sandbox|city.?build|tycoon|construction", SIMULATION, 5),
    (r"action.?adventure|adventure|visual novel|point.?and.?click|survival|open.?world|interactive fiction|exploration", ADVENTURE, 3),
    (r"\baction\b|hack.?(and|n).?slash|stealth|roguelike|roguelite|\barcade\b|brawl", ACTION, 2),
]
_LABEL_RULES = [(re.compile(p, re.I), g, w) for p, g, w in _LABEL_RULES]

# Weak hints taken from description text (each genre counts at most 3 times)
_TEXT_CUES = {
    PLATFORMER: r"\bplatforming\b|\bplatformer\b|\bjump(s|ing)? (across|between|over|on)|double.?jump|wall.?jump",
    SHOOTER: r"\bshoot(s|ing|er)?\b|\bbullets?\b|\bfirearms?\b|\bguns?\b",
    RPG: r"\blevel(s|ing)? up\b|experience points|\bparty members?\b|character classes|skill tree|turn.?based (combat|battles?)|\bquests?\b",
    RACING: r"\brac(e|es|ing)\b|\bdrift(ing)?\b|\blaps?\b|\bcars?\b|\bdriv(e|ing)\b",
    PUZZLE: r"\bpuzzles?\b|\bsolve\b|\bbrain\b",
    STRATEGY: r"\bstrateg(y|ic)\b|\bunits?\b|\bbuild(ing)? (a |an |your )?(base|army)|\btactical\b",
    SIMULATION: r"\bfarm(ing)?\b|\bsimulat(e|ion|or)\b|\bmanage(ment)?\b|\bcraft(ing)?\b|\bbuild(ing)? (a |your )?(town|city|house|farm)",
    FIGHTING: r"\bopponents?\b|\bone.on.one\b|\bcombos?\b|\bfighters?\b",
    SPORTS: r"\bmatch(es)?\b|\bteams?\b|\bscore goals?\b|\bleague\b",
    MUSIC: r"\brhythm\b|\bbeats?\b|\bmusic\b",
    ADVENTURE: r"\bexplor(e|ing|ation)\b|\bdungeons?\b|\bworld\b",
    ACTION: r"\bcombat\b|\bboss(es)?\b|\bfight(s|ing)?\b|\benemies\b|\bdodge\b",
}
_TEXT_CUES = {g: re.compile(p, re.I) for g, p in _TEXT_CUES.items()}


_TEXT_STRONG = [
    (r"\bbeat 'em up\b|\bbrawler\b", BEAT_EM_UP), (r"\bpinball\b", PINBALL),
    (r"\bfighting game\b|\bversus fighting\b", FIGHTING), (r"\brhythm game\b|\bmusic game\b", MUSIC),
    (r"\bcard game\b|\bboard game\b|\bdeck-?building\b", CARD_BOARD), (r"\bracing game\b|\bkart racer\b", RACING),
    (r"\bsports game\b", SPORTS), (r"\bpuzzle game\b|\bpuzzle-platformer\b", PUZZLE),
    (r"\bplatformer\b|\bplatform game\b|\bmetroidvania\b|\baction-platformer\b", PLATFORMER),
    (r"\bshoot ?'?em ?up\b|\bshmup\b|\bbullet hell\b|\brun and gun\b|\brun 'n' gun\b|\bshooter\b", SHOOTER),
    (r"\brole-playing\b|\brpg\b|\bjrpg\b", RPG), (r"\bstrategy game\b|\breal-time strategy\b|\btower defen[cs]e\b", STRATEGY),
    (r"\bsimulation game\b|\bfarming (sim|simulation|game)\b|\blife simulation\b|\bfarming sim\b", SIMULATION),
    (r"\baction-adventure\b|\badventure game\b", ADVENTURE), (r"\baction game\b", ACTION),
]
_TEXT_STRONG = [(re.compile(p, re.I), g) for p, g in _TEXT_STRONG]


def normalize_genre(labels, text="", min_score=4):
    """Map source genre labels (+ optional description text) to exactly ONE canonical genre.

    Returns None when the evidence is too weak (the caller must NOT invent a genre).
    Ties are resolved in the order of the rules above (specific genres first)."""
    scores = {g: 0.0 for g in GENRES}
    label_scores = {g: 0.0 for g in GENRES}
    order = {g: i for i, (_p, g, _w) in enumerate(_LABEL_RULES)}
    for label in labels or []:
        canon = canonical_genre(label)
        if canon:
            w = {ACTION: 2, ADVENTURE: 3}.get(canon, 6)
            scores[canon] += w
            label_scores[canon] += w
            continue
        for rx, genre, weight in _LABEL_RULES:
            if rx.search(str(label)):
                scores[genre] += weight
                label_scores[genre] += weight
    blob = text or ""
    for genre, rx in _TEXT_CUES.items():
        scores[genre] += min(3, len(rx.findall(blob))) * (0.7 if genre in (ACTION, ADVENTURE) else 1.0)
    for rx, genre in _TEXT_STRONG:
        if rx.search(blob):
            scores[genre] += 4
    best = max(GENRES, key=lambda g: (scores[g], -order.get(g, 99)))
    # accepted when the evidence is strong, or when a source label itself names that genre
    return best if (scores[best] >= min_score or label_scores[best] >= 2) else None


# ----------------------------------------------------------------------------
# 2. GAMEPLAY-ONLY DESCRIPTIONS
# ----------------------------------------------------------------------------
_BANNED = re.compile(r"""
    \b(?:playstation|ps[1-5]|psp|vita|xbox|nintendo|gamecube|wii|game\ boy|dreamcast|sega|genesis|saturn|atari|
        steam|windows|macos|linux|android|ios|iphone|console|consoles|handheld|pc|arcade\ cabinet|
        released?|releases|launch(?:ed)?|debut(?:ed)?|originally|announced|developed|published|studio|
        remakes?|remaster(?:ed)?|ported|ports?|sequels?|prequels?|spin-?offs?|franchise|series|installments?|
        follow-?ups?|award(?:s|ed)?|sold|copies|critics?|reviews?|acclaimed|praised|
        engine|resolution|fps|frames\ per\ second|4k|1080p|ray.?tracing|graphics|polygons?|hd|hardware|
        specifications?|soundtrack|visuals?|art\ style|cel.?shad(?:ed|ing)|animated|composed|
        buy|pre-?order|wishlist|dlc|discord|patreon|kickstarter|masterpiece|bestselling|iconic|legendary|beloved|
        multiplayer\ servers?|
        story|storyline|narrative|tale|journey|destiny|demons?|villains?|princess|kingdom|evil)\b
    | \b(?:19[6-9]\d|20[0-3]\d)\b
    | https?://
""", re.I | re.X)

_GAMEPLAY_CUES = re.compile(r"""\b(?:
    explor\w*|fight\w*|combat|battl\w*|enem(?:y|ies)|bosse?s?|defeat\w*|jump\w*|run|runs|running|dash\w*|climb\w*|
    collect\w*|solv\w*|puzzles?|build\w*|craft\w*|manag\w*|farm\w*|plant\w*|rac(?:e|es|ing)|driv\w*|drift\w*|
    shoot\w*|aim\w*|dodg\w*|upgrad\w*|unlock\w*|equip\w*|levels?|stages?|missions?|quests?|challeng\w*|surviv\w*|
    strateg\w*|turn-?based|real-?time|platform\w*|players?|controls?|weapons?|abilit(?:y|ies)|skills?|items?|
    inventory|trad\w*|scor\w*|combos?|rhythm|beats?|cards?|decks?|tactic\w*|gather\w*|discover\w*|navigat\w*|
    swing\w*|sail\w*|fly\w*|swim\w*|attack\w*|block\w*|parry|roll\w*|stealth|sneak\w*|recruit\w*|command\w*|
    resources?|dungeons?|rooms?|maps?|obstacles?|traps?|hazards?|power-?ups?|characters?|party|moves?|
    steer\w*|match\w*|clear\w*|arrange\w*|place\w*|complete\w*|talk\w*|choices?|decisions?)\b""", re.I | re.X)

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"'A-Z0-9])")


def _clean_text(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\[\d+\]|\[citation needed\]", "", text)
    text = re.sub(r"&nbsp;|&#?\w+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_mostly_english(text):
    """Cheap guard so non-English source text is never written to the gamelist."""
    if not text:
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    ascii_ratio = sum(1 for c in letters if c.isascii()) / len(letters)
    low = " " + text.lower() + " "
    pt_es_fr = sum(low.count(w) for w in (" não ", " você ", " para ", " uma ", " que ", " los ", " las ", " une ", " des ", " und ", " der "))
    return ascii_ratio >= 0.97 and pt_es_fr == 0


def gameplay_sentences(text):
    """Sentences that talk about how the game PLAYS and mention nothing banned."""
    out = []
    for s in _SENT_SPLIT.split(_clean_text(text)):
        s = s.strip()
        if len(s) < 35 or len(s) > 320 or _BANNED.search(s) or not _GAMEPLAY_CUES.search(s):
            continue
        if not is_mostly_english(s):
            continue
        out.append(s)
    return out


def build_description(texts, max_sentences=4, max_chars=520):
    """Pick up to 4 gameplay sentences from the texts (highest-priority text first).
    Returns '' if nothing qualifies - never invents text."""
    chosen, seen, total = [], set(), 0
    for text in texts:
        for s in gameplay_sentences(text):
            key = re.sub(r"[^a-z0-9]", "", s.lower())[:60]
            if key in seen:
                continue
            if total + len(s) > max_chars and chosen:
                break
            chosen.append(s)
            seen.add(key)
            total += len(s) + 1
            if len(chosen) >= max_sentences:
                return " ".join(chosen)
    return " ".join(chosen)


def validate_description(desc, strict=False):
    """(ok, reason). strict=True enforces the 2-4 sentence rule (used for AI output)."""
    d = _clean_text(desc)
    if not d:
        return False, "empty"
    sents = [s for s in _SENT_SPLIT.split(d) if s.strip()]
    if strict and not (2 <= len(sents) <= 4):
        return False, "needs 2-4 sentences (got %d)" % len(sents)
    if len(d) > 700:
        return False, "too long"
    if _BANNED.search(d):
        return False, "mentions platform, release, franchise, technical or marketing details"
    if not is_mostly_english(d):
        return False, "not English"
    return True, ""


# ----------------------------------------------------------------------------
# 3. RATINGS (0-10 score -> EmulationStation 0.00-1.00)
# ----------------------------------------------------------------------------
NEUTRAL_PRIOR = 6.5   # shrinkage target: keeps a single score from being copied verbatim
PRIOR_WEIGHT = 0.4
MIN_EVIDENCE = 0.8    # below this total weight we refuse to produce a score


def wilson_lower_bound(pos, total, z=1.96):
    if total <= 0:
        return 0.0
    p = pos / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - margin) / denom)


def user_ratio_to_score(pos, total):
    """Steam-style positive/total votes -> 0-10 (conservative: uses the Wilson lower bound)."""
    lb = wilson_lower_bound(pos, total)
    return 2.0 + 8.0 * max(0.0, (lb - 0.4) / 0.6)


def collect_signals(scores):
    """scores keys (all optional): metacritic (0-100), wikidata (list of 0-1 ratios),
    steam_pos / steam_total, rawg_rating (0-5) / rawg_count, google (0-1).
    Returns [(label, score_0_10, weight)]."""
    sig = []
    mc = scores.get("metacritic")
    if mc is not None and 0 <= mc <= 100:
        sig.append(("critics (Metacritic)", mc / 10.0, 1.0))
    wd = [r for r in scores.get("wikidata", []) if 0 <= r <= 1]
    if wd:
        sig.append(("critics (aggregators)", 10.0 * sum(wd) / len(wd), 0.6 if mc is not None else 1.0))
    sp, st = scores.get("steam_pos"), scores.get("steam_total")
    if st and st >= 10 and sp is not None:
        sig.append(("players (Steam)", user_ratio_to_score(sp, st), min(1.0, st / 200.0)))
    rr = scores.get("rawg_rating")
    if rr:
        sig.append(("players (RAWG)", max(0.0, min(10.0, rr * 2.0)), 0.25 + 0.25 * min(1.0, scores.get("rawg_count", 0) / 100.0)))
    g = scores.get("google")
    if g is not None and 0 <= g <= 1:
        sig.append(("web (Google)", g * 10.0, 0.4))
    return sig


def compute_rating(scores, min_evidence=None):
    """Balanced 0-10 estimate from several signals, or None if the evidence is too thin.
    (A single explicitly chosen source may use a lower threshold; the prior then dampens the result.)"""
    sig = collect_signals(scores)
    wsum = sum(w for _l, _s, w in sig)
    if wsum < (MIN_EVIDENCE if min_evidence is None else min_evidence):
        return None
    score = (sum(s * w for _l, s, w in sig) + NEUTRAL_PRIOR * PRIOR_WEIGHT) / (wsum + PRIOR_WEIGHT)
    return round(max(0.0, min(10.0, score)), 1)


def to_es_rating(score10):
    """0-10 -> '0.00'-'1.00' (EmulationStation)."""
    if score10 is None:
        return ""
    return "%.2f" % (max(0.0, min(10.0, float(score10))) / 10.0)


def parse_user_rating(text):
    """Accepts 0.85, 8.5 (0-10) or 85 (0-100). Returns the ES string '0.85'."""
    v = float(str(text).replace(",", "."))
    if v > 10:
        v /= 100
    elif v > 1:
        v /= 10
    return "%.2f" % max(0.0, min(1.0, v))


# ----------------------------------------------------------------------------
# 4. OPTIONAL AI EVALUATION (Anthropic API, bring your own key)
# ----------------------------------------------------------------------------
AI_ENDPOINT = "https://api.anthropic.com/v1/messages"
AI_DEFAULT_MODEL = "claude-sonnet-5-5"

AI_SYSTEM = """You are a careful video game curator writing metadata for a game library.
Use ONLY the material provided by the user. Never invent gameplay details, scores or genres.
If the material is not enough for a field, return null for that field.

Fields:
- "genre": exactly one of: %s. Choose by the primary gameplay, not the story, art style, console or platform.
- "description": 2-4 sentences in English describing ONLY what the game is like to play: core mechanics,
  player objectives and activities, combat/exploration/puzzles/racing, progression and distinctive gameplay features.
  Do NOT mention the platform or console, release history, franchise history, technical specifications, graphics, story or sales.
- "rating": a balanced score from 0 to 10 (one decimal) judging gameplay quality and enjoyment, controls and responsiveness,
  level design and progression, content and replayability, and overall polish. External scores (Metacritic, Steam, etc.) are
  supporting evidence only: do not copy or average them mechanically, weigh the actual gameplay evidence, consider the game's
  historical context, do not favor famous franchises and do not penalize older games for being old.
- "basis": one short sentence explaining what the rating is based on.

Reply with ONE JSON object and nothing else:
{"genre": ..., "description": ..., "rating": ..., "basis": ...}""" % ", ".join('"%s"' % g for g in GENRES)


def build_ai_prompt(evidence):
    parts = ["Game title: %s" % evidence.get("title", "")]
    if evidence.get("labels"):
        parts.append("Genre labels from sources: " + ", ".join(evidence["labels"]))
    sc = evidence.get("scores", {})
    if sc:
        parts.append("External scores (supporting evidence only): " + json.dumps(sc))
    budget = 6500
    for src, text in evidence.get("texts", []):
        t = _clean_text(text)[:2000]
        if t and budget > 0:
            parts.append("[%s]\n%s" % (src, t[:budget]))
            budget -= len(t)
    for r in evidence.get("reviews", [])[:6]:
        parts.append("[player review excerpt]\n" + _clean_text(r)[:300])
    return "\n\n".join(parts)


def _http_post_json(url, payload, headers, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_ai_response(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("AI reply had no JSON object")
    return json.loads(m.group(0))


def ai_evaluate(evidence, api_key, model=AI_DEFAULT_MODEL, post=_http_post_json):
    """Ask the model for genre/description/rating. Every field is validated; invalid ones become None."""
    payload = {"model": model, "max_tokens": 700, "system": AI_SYSTEM,
               "messages": [{"role": "user", "content": build_ai_prompt(evidence)}]}
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    data = post(AI_ENDPOINT, payload, headers)
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    raw = parse_ai_response(text)
    out = {"genre": None, "description": None, "rating": None, "rating_valid": True,
           "basis": str(raw.get("basis") or "")[:200]}
    g = canonical_genre(raw.get("genre"))
    out["genre"] = g
    desc = raw.get("description")
    if isinstance(desc, str) and validate_description(desc, strict=True)[0]:
        out["description"] = _clean_text(desc)
    r = raw.get("rating")
    if r is None:
        pass                                   # evaluator says: not enough evidence -> no score
    elif isinstance(r, (int, float)) and not isinstance(r, bool) and 0 <= r <= 10:
        out["rating"] = round(float(r), 1)
    else:
        out["rating_valid"] = False            # malformed -> caller falls back to the rule-based score
    return out


# ----------------------------------------------------------------------------
# 5. PUTTING IT TOGETHER
# ----------------------------------------------------------------------------
def has_evidence(evidence):
    return bool(evidence.get("texts") or evidence.get("labels") or evidence.get("scores"))


def run_ai(evidence, ai, post=_http_post_json, log=print):
    """One AI evaluation of the collected evidence, or None (not configured / failed / nothing to judge)."""
    if not (ai and ai.get("key") and has_evidence(evidence)):
        return None
    try:
        res = ai_evaluate(evidence, ai["key"], ai.get("model") or AI_DEFAULT_MODEL, post)
        log("AI evaluation done (%s)" % (res.get("basis") or "no basis given"))
        return res
    except Exception as e:  # network/JSON/etc: fall back to rules
        log("AI evaluation failed (%s); using rule-based metadata" % e)
        return None


def build_metadata(evidence, wanted, ai=None, post=_http_post_json, log=print, ai_res=None, min_evidence=None):
    """Return {'genre','desc','rating'} limited to the `wanted` fields (missing ones stay absent).

    ai = {"key":..., "model":...} enables the AI evaluator (or pass a ready `ai_res` to reuse one evaluation);
    otherwise a rule-based path is used. Nothing is fabricated: when the evidence is not enough the field is left out."""
    out = {}
    if ai_res is None and ai:
        ai_res = run_ai(evidence, ai, post, log)
    texts = [t for _s, t in evidence.get("texts", [])]
    if "genre" in wanted:
        g = (ai_res or {}).get("genre") or normalize_genre(evidence.get("labels", []), " ".join(texts))
        if g:
            out["genre"] = g
    if "desc" in wanted:
        d = (ai_res or {}).get("description") or build_description(texts)
        if d and validate_description(d)[0]:
            out["desc"] = d
    if "rating" in wanted:
        if ai_res is not None and ai_res.get("rating_valid", True):
            r = ai_res.get("rating")   # None = the evaluator judged the evidence insufficient
        else:
            r = compute_rating(evidence.get("scores", {}), min_evidence)
        if r is not None:
            out["rating"] = to_es_rating(r)
    return out
