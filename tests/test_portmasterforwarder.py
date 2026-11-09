"""PortMasterForwarder test-suite (standard library only).

Run from the repository root:   python -m unittest discover -s tests -v
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from portmasterforwarder import __version__ as PKG_VERSION   # noqa: E402
from portmasterforwarder import core                          # noqa: E402
from portmasterforwarder import meta as pm                    # noqa: E402

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def png_bytes(w=1280, h=720):
    if Image is None:
        return b"\x89PNG" + b"0" * 4000
    b = io.BytesIO()
    Image.new("RGB", (w, h), (10, 20, 30)).save(b, "PNG")
    return b.getvalue()


# ---------------------------------------------------------------- fake internet
WW_GAMEPLAY = ("== Gameplay ==\nThe player controls Link as he sails a large ocean, explores islands and solves puzzles in dungeons. "
               "Combat uses a lock-on system that lets Link dodge, parry and counter enemies. "
               "The game was praised by critics for its graphics. "
               "Players collect items such as the grappling hook to unlock new areas and progress.\n\n== Plot ==\nA boy sets out to rescue his sister.")
CELESTE = {"success": True, "data": {
    "name": "Celeste", "short_description": "Help Madeline survive her inner demons on her journey to the top of Celeste Mountain, in this super-tight platformer.",
    "about_the_game": "<p>You jump, dash and climb across hundreds of hand-placed challenges. Collect strawberries and discover hidden secrets on every screen.</p>",
    "developers": ["Maddy Makes Games"], "publishers": ["Maddy Makes Games"], "genres": [{"description": "Indie"}, {"description": "Action"}],
    "metacritic": {"score": 94}, "screenshots": [{"path_thumbnail": "t0", "path_full": "f0"}, {"path_thumbnail": "t1", "path_full": "f1"}],
    "release_date": {"date": "25 Jan, 2018"}}}


class FakeNet:
    def __init__(self):
        self.calls = []
        self.fail_wiki = False

    def __call__(self, url, timeout=30):
        self.calls.append(url)
        if "storesearch" in url:
            term = re.search(r"term=([^&]+)", url).group(1).lower()
            return json.dumps({"items": [{"type": "app", "id": 504230, "name": "Celeste"}] if "celeste" in term else []}).encode()
        if "store.steampowered.com/api/appdetails" in url:
            if "l=english" not in url:
                raise AssertionError("metadata must be requested in English: " + url)
            return json.dumps({"504230": CELESTE}).encode()
        if "appreviews" in url:
            return json.dumps({"query_summary": {"total_reviews": 90000, "total_positive": 88000}}).encode()
        if "en.wikipedia.org/w/api.php" in url and "list=search" in url:
            if self.fail_wiki:
                raise OSError("wiki down")
            return json.dumps({"query": {"search": [{"title": "The Legend of Zelda: The Wind Waker"}]}}).encode()
        if "prop=extracts" in url:
            return json.dumps({"query": {"pages": {"1": {"extract": WW_GAMEPLAY}}}}).encode()
        if "rest_v1/page/summary" in url:
            return json.dumps({"type": "standard", "title": "The Legend of Zelda: The Wind Waker", "description": "2002 video game",
                               "extract": "The Wind Waker is an action-adventure game.", "wikibase_item": "Q1"}).encode()
        if "Special:EntityData" in url:
            c = {"P577": [{"mainsnak": {"datavalue": {"value": {"time": "+2002-12-13T00:00:00Z", "precision": 11}}}}],
                 "P136": [{"mainsnak": {"datavalue": {"value": {"id": "Q10"}}}}], "P178": [{"mainsnak": {"datavalue": {"value": {"id": "Q20"}}}}],
                 "P123": [{"mainsnak": {"datavalue": {"value": {"id": "Q20"}}}}],
                 "P444": [{"mainsnak": {"datavalue": {"value": "96/100"}}}, {"mainsnak": {"datavalue": {"value": "94%"}}}]}
            return json.dumps({"entities": {"Q1": {"claims": c}}}).encode()
        if "wbgetentities" in url:
            return json.dumps({"entities": {"Q10": {"labels": {"en": {"value": "action-adventure game"}}},
                                             "Q20": {"labels": {"en": {"value": "Nintendo"}}}}}).encode()
        if url.startswith("https://api.rawg.io/api/games?"):
            return json.dumps({"results": [{"id": 9, "name": "The Legend of Zelda: The Wind Waker"}]}).encode()
        if "api.rawg.io/api/games/9" in url:
            return json.dumps({"description_raw": "You sail the sea and explore dungeons while fighting enemies. Puzzles block your progress.",
                               "released": "2002-12-13", "genres": [{"name": "Adventure"}], "metacritic": 96, "rating": 4.4,
                               "ratings_count": 3000, "background_image": "bg.jpg", "developers": [{"name": "Nintendo EAD"}],
                               "publishers": [{"name": "Nintendo"}]}).encode()
        if "googleapis.com/customsearch" in url:
            return json.dumps({"items": [{"snippet": "x", "pagemap": {"aggregaterating": [{"ratingvalue": "4.5", "bestrating": "5"}],
                                                                       "metatags": [{"og:description": "You sail between islands and fight enemies in dungeons while solving puzzles."}]}}]}).encode()
        if url in ("f0", "f1", "t0", "t1", "bg.jpg"):
            return png_bytes()
        raise OSError("404 " + url)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.share = self.tmp / "SHARE"
        (self.share / "roms" / "ports").mkdir(parents=True)
        (self.share / "system" / "configs" / "emulationstation").mkdir(parents=True)
        self.net = FakeNet()
        self._orig = (core.http_get, core.AI_POST, dict(core._TOUCHED) if isinstance(core._TOUCHED, dict) else set(core._TOUCHED))
        core.http_get = self.net
        core.AI_POST = None
        core._TOUCHED.clear()
        self.cfg = core.load_config(self.tmp / "none.json")
        self.cfg["share"] = str(self.share)
        self.logs = []

    def tearDown(self):
        core.http_get, core.AI_POST = self._orig[0], self._orig[1]
        shutil.rmtree(self.tmp, ignore_errors=True)

    def log(self, m):
        self.logs.append(m)

    def port(self, name):
        (self.share / "roms" / "ports" / name).write_text("#!/bin/bash\n")

    def game(self, name, cat, **kw):
        self.cfg["games"][name] = dict(cat=cat, **kw)

    def gamelist(self, cat):
        return ET.parse(self.share / "roms" / cat / "gamelist.xml").getroot()

    def entry(self, cat, name):
        for g in self.gamelist(cat).findall("game"):
            if g.find("path").text == "./" + name:
                return {c.tag: c.text for c in g}
        return None


# ---------------------------------------------------------------- 1. genres
class GenreTests(unittest.TestCase):
    def test_exactly_fifteen_standard_genres(self):
        self.assertEqual(len(pm.GENRES), 15)
        self.assertEqual(len(set(pm.GENRES)), 15)
        for g in ("Action", "Platformer / Platform", "Adventure", "RPG (Role-Playing Game)", "Shooter / Shmup", "Fighting",
                  "Beat 'em Up", "Racing / Driving", "Sports", "Puzzle", "Strategy", "Simulation", "Pinball",
                  "Card Game / Board Game", "Music / Rhythm"):
            self.assertIn(g, pm.GENRES)

    def test_every_genre_is_reachable_and_exact(self):
        cases = {
            pm.ACTION: (["Action"], ""), pm.PLATFORMER: (["Platform game"], ""), pm.ADVENTURE: (["Adventure"], ""),
            pm.RPG: (["role-playing video game"], ""), pm.SHOOTER: (["first-person shooter"], ""), pm.FIGHTING: (["Fighting"], ""),
            pm.BEAT_EM_UP: (["Beat 'em up"], ""), pm.RACING: (["Racing"], ""), pm.SPORTS: (["Sports"], ""), pm.PUZZLE: (["Puzzle"], ""),
            pm.STRATEGY: (["real-time strategy"], ""), pm.SIMULATION: (["Simulation"], ""), pm.PINBALL: (["pinball video game"], ""),
            pm.CARD_BOARD: (["card game"], ""), pm.MUSIC: (["rhythm game"], ""),
        }
        for expected, (labels, text) in cases.items():
            self.assertEqual(pm.normalize_genre(labels, text), expected, labels)

    def test_result_is_always_one_standard_value_or_none(self):
        samples = [(["Action", "Adventure", "RPG", "Indie"], "fight and explore"), (["Casual"], ""), ([], ""), (["cross-platform"], ""),
                   (["Action", "Indie"], "A super-tight platformer."), (["Strategy", "Simulation"], "")]
        for labels, text in samples:
            g = pm.normalize_genre(labels, text)
            self.assertTrue(g is None or g in pm.GENRES)

    def test_primary_gameplay_beats_generic_labels(self):
        self.assertEqual(pm.normalize_genre(["Action", "Indie"], "Help Madeline in this super-tight platformer."), pm.PLATFORMER)
        self.assertEqual(pm.normalize_genre(["Action", "Adventure", "Indie"], "Explore dungeons and solve puzzles."), pm.ADVENTURE)
        self.assertEqual(pm.normalize_genre(["Indie", "RPG", "Simulation"], "Grow crops on your farming sim farm."), pm.SIMULATION)
        self.assertEqual(pm.normalize_genre(["Action", "role-playing video game"], ""), pm.RPG)

    def test_no_invention_when_evidence_is_weak(self):
        self.assertIsNone(pm.normalize_genre(["Indie", "Casual", "Single-player"], ""))
        self.assertIsNone(pm.normalize_genre([], ""))

    def test_canonical_and_validation(self):
        self.assertEqual(pm.canonical_genre("platform"), pm.PLATFORMER)
        self.assertEqual(pm.canonical_genre("RPG"), pm.RPG)
        self.assertIsNone(pm.canonical_genre("Roguelike"))
        self.assertTrue(pm.is_standard_genre("Music / Rhythm"))
        self.assertFalse(pm.is_standard_genre("Music"))


# ---------------------------------------------------------------- 2. descriptions
class DescriptionTests(unittest.TestCase):
    TEXT = ("The Wind Waker is a 2002 action-adventure game developed by Nintendo for the GameCube. "
            "The player controls Link as he sails a large ocean, explores islands and solves puzzles in dungeons. "
            "Combat uses a lock-on system that lets Link dodge, parry and counter enemies. "
            "The game was praised by critics for its cel-shaded graphics. "
            "Players collect items such as the grappling hook to unlock new areas and progress. "
            "It was a sequel in the Legend of Zelda series.")

    def test_only_gameplay_sentences_survive(self):
        d = pm.build_description([self.TEXT])
        self.assertTrue(d)
        for banned in ("GameCube", "Nintendo", "2002", "sequel", "series", "critics", "graphics", "developed"):
            self.assertNotIn(banned, d)
        self.assertIn("sails", d)
        self.assertTrue(pm.validate_description(d)[0])

    def test_story_sentences_are_dropped(self):
        d = pm.build_description(["Help Madeline survive her inner demons on her journey to the top of the mountain, in this super-tight platformer. "
                                  "You jump, dash and climb across hundreds of hand-placed challenges. Collect strawberries on every screen."])
        self.assertNotIn("demons", d)
        self.assertNotIn("journey", d)
        self.assertIn("dash and climb", d)

    def test_length_limits(self):
        long_text = " ".join("You fight enemies and explore dungeon number %d while collecting new items." % i for i in range(20))
        d = pm.build_description([long_text])
        n = len([s for s in re.split(r"(?<=[.!?])\s+", d) if s])
        self.assertLessEqual(n, 4)
        self.assertLessEqual(len(d), 700)

    def test_nothing_is_invented(self):
        self.assertEqual(pm.build_description([]), "")
        self.assertEqual(pm.build_description(["A 2003 game released for PlayStation 2 by Sony."]), "")
        self.assertEqual(pm.build_description(["Buy now on Steam and join our Discord today for updates!"]), "")

    def test_non_english_text_is_rejected(self):
        self.assertEqual(pm.build_description(["Você explora um mundo enorme e luta contra inimigos para avançar nas fases."]), "")
        self.assertFalse(pm.validate_description("Você explora um mundo enorme e luta contra inimigos nesta aventura.")[0])

    def test_validation_rules(self):
        self.assertFalse(pm.validate_description("A game for PlayStation 2.")[0])
        self.assertFalse(pm.validate_description("Explore dungeons and fight enemies in this sequel.")[0])
        self.assertFalse(pm.validate_description("One sentence about fighting enemies in dungeons.", strict=True)[0])
        ok = "You fight enemies in tight arenas. Each win unlocks new weapons and abilities."
        self.assertTrue(pm.validate_description(ok, strict=True)[0])


# ---------------------------------------------------------------- 3. ratings
class RatingTests(unittest.TestCase):
    def test_not_a_plain_copy_of_one_score(self):
        r = pm.compute_rating({"metacritic": 96})
        self.assertIsNotNone(r)
        self.assertNotEqual(r, 9.6)
        self.assertLess(r, 9.6)

    def test_multiple_sources_raise_confidence(self):
        one = pm.compute_rating({"metacritic": 96})
        two = pm.compute_rating({"metacritic": 96, "steam_pos": 48500, "steam_total": 50000})
        self.assertGreater(two, one)

    def test_disagreeing_sources_balance_out(self):
        r = pm.compute_rating({"metacritic": 90, "steam_pos": 3000, "steam_total": 5000})
        self.assertTrue(6.0 < r < 8.5)

    def test_insufficient_information_gives_no_score(self):
        self.assertIsNone(pm.compute_rating({}))
        self.assertIsNone(pm.compute_rating({"steam_pos": 19, "steam_total": 20}))

    def test_old_and_new_games_are_scored_the_same_way(self):
        self.assertEqual(pm.compute_rating({"metacritic": 85}), pm.compute_rating({"metacritic": 85}))

    def test_es_format(self):
        self.assertEqual(pm.to_es_rating(8.7), "0.87")
        self.assertEqual(pm.to_es_rating(10), "1.00")
        self.assertEqual(pm.to_es_rating(0), "0.00")
        self.assertEqual(pm.to_es_rating(None), "")
        for v in ("0.85", "8,5", "85"):
            self.assertEqual(pm.parse_user_rating(v), "0.85")
        self.assertRegex(pm.parse_user_rating("3.14159"), r"^\d\.\d\d$")

    def test_ai_valid_invalid_and_null(self):
        ev = {"title": "X", "labels": ["Action"], "texts": [("Wikipedia", "You fight enemies and explore dungeons while solving puzzles to progress.")],
              "scores": {"metacritic": 90}}

        def reply(obj):
            return lambda url, payload, headers: {"content": [{"type": "text", "text": "```json\n%s\n```" % json.dumps(obj)}]}
        good = {"genre": "Adventure", "description": "You sail between islands and explore dungeons. Puzzles and combat gate your progress.",
                "rating": 8.6, "basis": "tight controls"}
        out = pm.build_metadata(ev, {"genre", "desc", "rating"}, ai={"key": "K"}, post=reply(good), log=lambda m: None)
        self.assertEqual(out, {"genre": "Adventure", "desc": good["description"], "rating": "0.86"})
        bad = {"genre": "Roguelike", "description": "A PS2 game.", "rating": 12, "basis": "x"}
        out = pm.build_metadata(ev, {"genre", "desc", "rating"}, ai={"key": "K"}, post=reply(bad), log=lambda m: None)
        self.assertEqual(out["genre"], "Action")                      # invalid AI genre -> rules
        self.assertNotIn("PS2", out["desc"])                          # invalid AI text -> rules
        self.assertIn("rating", out)                                  # malformed rating -> rule-based estimate
        null = {"genre": "Action", "description": None, "rating": None, "basis": "thin"}
        out = pm.build_metadata(ev, {"genre", "desc", "rating"}, ai={"key": "K"}, post=reply(null), log=lambda m: None)
        self.assertNotIn("rating", out)                               # evaluator said 'insufficient' -> no score

        def down(*a):
            raise OSError("offline")
        out = pm.build_metadata(ev, {"genre", "desc", "rating"}, ai={"key": "K"}, post=down, log=lambda m: None)
        self.assertEqual(set(out), {"genre", "desc", "rating"})       # AI down -> rules

    def test_ai_prompt_carries_the_rules(self):
        self.assertIn("ONLY what the game is like to play", pm.AI_SYSTEM)
        for g in pm.GENRES:
            self.assertIn('"%s"' % g, pm.AI_SYSTEM)
        self.assertIn("do not penalize older games", pm.AI_SYSTEM)


# ---------------------------------------------------------------- 4 + 5. pipeline, XML and regressions
class PipelineTests(Base):
    def test_steam_game_metadata_is_english_standardized_and_valid_xml(self):
        self.port("Celeste.sh")
        self.game("Celeste.sh", "portpc", shot_mode="auto")
        core.apply_game(self.cfg, "Celeste.sh", self.log)
        e = self.entry("portpc", "Celeste.sh")
        self.assertEqual(e["genre"], pm.PLATFORMER)
        self.assertIn(e["genre"], pm.GENRES)
        self.assertTrue(pm.validate_description(e["desc"])[0])
        self.assertNotIn("Steam", e["desc"])
        self.assertNotIn("demons", e["desc"])
        self.assertRegex(e["rating"], r"^(0\.\d\d|1\.00)$")
        self.assertNotEqual(e["rating"], "0.94")                      # not a copy of Metacritic
        self.assertEqual(e["releasedate"], "20180125T000000")
        self.assertEqual(e["developer"], "Maddy Makes Games")
        self.assertTrue((self.share / "roms" / "portpc" / "images" / "Celeste-image.jpg").exists() or
                        (self.share / "roms" / "portpc" / "images" / "Celeste-image.png").exists())

    def test_console_game_gets_gameplay_description_from_wikipedia(self):
        self.port("Wind Waker.sh")
        self.game("Wind Waker.sh", "portgamecube", steam_checked=True)
        core.apply_game(self.cfg, "Wind Waker.sh", self.log)
        e = self.entry("portgamecube", "Wind Waker.sh")
        self.assertEqual(e["genre"], pm.ADVENTURE)
        for word in ("GameCube", "praised", "critics", "graphics", "2002"):
            self.assertNotIn(word, e["desc"])
        self.assertIn("sails", e["desc"])
        self.assertIn(e["rating"][:2], ("0.",))
        self.assertEqual(e["releasedate"], "20021213T000000")

    def test_xml_is_wellformed_utf8_without_bom(self):
        self.port("Celeste.sh")
        self.game("Celeste.sh", "portpc")
        core.apply_game(self.cfg, "Celeste.sh", self.log)
        raw = (self.share / "roms" / "portpc" / "gamelist.xml").read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        root = ET.fromstring(raw)
        self.assertEqual(root.tag, "gameList")
        for g in root.findall("game"):
            self.assertIsNotNone(g.find("path"))
            if g.find("genre") is not None:
                self.assertIn(g.find("genre").text, pm.GENRES)
            if g.find("rating") is not None:
                self.assertTrue(0.0 <= float(g.find("rating").text) <= 1.0)

    def test_systems_xml_and_wrapper_files(self):
        core.install_systems(self.cfg, False, self.log)
        for cat in self.cfg["categories"]:
            p = core.system_cfg_path(self.cfg, cat)
            root = ET.parse(p).getroot()
            self.assertEqual(root.find("system/name").text, cat["folder"])
            self.assertEqual(root.find("system/path").text, "/userdata/roms/" + cat["folder"])
            self.assertIn("-system ports", root.find("system/command").text)
            self.assertIn("PortMasterForwarder", p.read_text())
        self.assertEqual(self.cfg["categories"][0]["theme"], "gc")
        self.port("Celeste.sh")
        self.game("Celeste.sh", "portpc", steam_checked=True, shot_mode="none")
        core.apply_game(self.cfg, "Celeste.sh", self.log)
        w = (self.share / "roms" / "portpc" / "Celeste.sh").read_bytes()
        self.assertNotIn(b"\r", w)
        self.assertIn(b'TARGET="/userdata/roms/ports/Celeste.sh"', w)

    # ---- metadata modes
    def complete_entry(self, cat="portps2", name="Simpsons.sh"):
        d = self.share / "roms" / cat
        (d / "images").mkdir(parents=True, exist_ok=True)
        (d / "images" / "s.jpg").write_bytes(b"x" * 3000)
        (d / "gamelist.xml").write_text(
            '<?xml version="1.0"?><gameList><game id="7"><path>./%s</path><name>My Name</name><desc>Texto antigo do usuario</desc>'
            '<image>./images/s.jpg</image><rating>0.8</rating><releasedate>20030916T000000</releasedate><developer>Radical</developer>'
            '<publisher>VU</publisher><genre>Platform</genre><md5>abc</md5></game></gameList>' % name, encoding="utf-8")

    def test_fill_mode_never_overwrites_existing_user_data(self):
        self.port("Simpsons.sh")
        self.complete_entry()
        self.game("Simpsons.sh", "portps2")
        before = self.entry("portps2", "Simpsons.sh")
        self.net.calls.clear()
        core.apply_game(self.cfg, "Simpsons.sh", self.log)
        self.assertEqual(self.entry("portps2", "Simpsons.sh"), before)
        self.assertEqual(self.net.calls, [])                          # complete game: no network at all
        self.assertIn("Platform", before["genre"])
        self.assertTrue(any("not a standard genre" in m for m in self.logs))
        self.assertEqual(core.nonstandard_fields(self.cfg, "Simpsons.sh"), ["genre"])

    def test_replace_mode_standardizes_but_keeps_data_when_nothing_found(self):
        self.port("Simpsons.sh")
        self.complete_entry()
        self.game("Simpsons.sh", "portps2", meta_mode="replace", steam_checked=True)
        self.net.fail_wiki = True
        core.apply_game(self.cfg, "Simpsons.sh", self.log)
        e = self.entry("portps2", "Simpsons.sh")
        self.assertEqual(e["desc"], "Texto antigo do usuario")        # nothing reliable found -> not blanked
        self.assertEqual(e["md5"], "abc")

    def test_keep_mode_and_manual_values(self):
        self.port("Celeste.sh")
        self.game("Celeste.sh", "portpc", meta_mode="keep", steam_checked=True, shot_mode="none",
                  genre="Puzzle", rating="7", desc="You solve rooms.")
        core.apply_game(self.cfg, "Celeste.sh", self.log)
        e = self.entry("portpc", "Celeste.sh")
        self.assertEqual((e["genre"], e["rating"], e["desc"]), ("Puzzle", "0.70", "You solve rooms."))
        self.assertEqual(self.net.calls, [])

    def test_invalid_manual_genre_is_ignored(self):
        self.port("Celeste.sh")
        self.game("Celeste.sh", "portpc", meta_mode="keep", steam_checked=True, shot_mode="none", genre="Roguelike")
        core.apply_game(self.cfg, "Celeste.sh", self.log)
        self.assertNotIn("genre", self.entry("portpc", "Celeste.sh"))

    def test_insufficient_information_is_left_empty(self):
        self.port("Obscure Game.sh")
        self.game("Obscure Game.sh", "portpc", steam_checked=True, shot_mode="none")
        core.apply_game(self.cfg, "Obscure Game.sh", self.log)
        e = self.entry("portpc", "Obscure Game.sh")
        for tag in ("genre", "desc", "rating"):
            self.assertNotIn(tag, e)
        self.assertTrue(any("not enough reliable information" in m for m in self.logs))

    def test_ai_path_through_apply(self):
        self.port("Wind Waker.sh")
        self.game("Wind Waker.sh", "portgamecube", steam_checked=True, shot_mode="none")
        self.cfg.update(ai_enabled=True, anthropic_key="K")
        seen = {}

        def fake_post(url, payload, headers):
            seen.update(url=url, model=payload["model"], key=headers["x-api-key"], prompt=payload["messages"][0]["content"])
            return {"content": [{"type": "text", "text": json.dumps({
                "genre": "Adventure", "description": "You sail between islands and explore dungeons. Puzzles and combat gate your progress.",
                "rating": 9.1, "basis": "tight design"})}]}
        core.AI_POST = fake_post
        core.apply_game(self.cfg, "Wind Waker.sh", self.log)
        e = self.entry("portgamecube", "Wind Waker.sh")
        self.assertEqual((e["genre"], e["rating"]), ("Adventure", "0.91"))
        self.assertEqual(seen["url"], pm.AI_ENDPOINT)
        self.assertIn("Wikipedia gameplay section", seen["prompt"])

    def test_backup_created_once_and_only_for_existing_gamelist(self):
        self.port("Celeste.sh")
        self.game("Celeste.sh", "portpc", steam_checked=True, shot_mode="none")
        core.apply_game(self.cfg, "Celeste.sh", self.log)
        self.assertFalse((self.share / "roms" / "portpc" / "gamelist.xml.bak").exists())
        core._TOUCHED.clear()
        before = (self.share / "roms" / "portpc" / "gamelist.xml").read_text()
        core.apply_game(self.cfg, "Celeste.sh", self.log)
        self.assertEqual((self.share / "roms" / "portpc" / "gamelist.xml.bak").read_text(), before)

    def test_move_between_categories_and_undo(self):
        self.port("Celeste.sh")
        self.game("Celeste.sh", "portpc", steam_checked=True, shot_mode="none")
        core.apply_game(self.cfg, "Celeste.sh", self.log)
        self.cfg["games"]["Celeste.sh"]["cat"] = "portwii"
        core.apply_game(self.cfg, "Celeste.sh", self.log)
        self.assertFalse((self.share / "roms" / "portpc" / "Celeste.sh").exists())
        self.assertTrue((self.share / "roms" / "portwii" / "Celeste.sh").exists())
        hand = self.share / "roms" / "portwii" / "Handmade.sh"
        hand.write_text('#!/bin/bash\nexec bash "/x"\n')
        core.remove_wrappers(self.cfg, self.log)
        self.assertFalse((self.share / "roms" / "portwii" / "Celeste.sh").exists())
        self.assertTrue(hand.exists())                                 # not ours -> untouched
        self.assertTrue((self.share / "roms" / "ports").is_dir())

    # ---- compatibility with files made by the old Knulli Categorias
    def test_legacy_files_are_recognized(self):
        d = self.share / "roms" / "portpc"
        d.mkdir(parents=True)
        (d / "Old.sh").write_text('#!/bin/bash\n# gerado por knulli_categorias\nTARGET="/userdata/roms/ports/Old.sh"\nexec bash "$TARGET"\n')
        self.port("Old.sh")
        self.assertEqual(core.scan_existing(self.cfg)["Old.sh"], "portpc")
        cfgdir = self.share / "system" / "configs" / "emulationstation"
        legacy = cfgdir / "es_systems_portpc.cfg"
        legacy.write_text("<?xml version='1.0'?>\n<!-- gerado por knulli_categorias -->\n<systemList/>")
        self.assertEqual(core.foreign_cfgs(self.cfg), [])             # legacy PortMasterForwarder file counts as ours
        core.remove_systems(self.cfg, False, self.log)
        self.assertFalse(legacy.exists())
        core.remove_wrappers(self.cfg, self.log)
        self.assertFalse((d / "Old.sh").exists())

    def test_foreign_system_file_is_not_replaced_silently(self):
        cfgdir = self.share / "system" / "configs" / "emulationstation"
        mine = cfgdir / "es_systems_portpc.cfg"
        mine.write_text("<systemList><!-- hand written --></systemList>")
        self.assertEqual(core.foreign_cfgs(self.cfg), [mine])
        core.install_systems(self.cfg, False, self.log)
        self.assertIn("hand written", mine.read_text())
        core.install_systems(self.cfg, True, self.log)
        self.assertIn("PortMasterForwarder", mine.read_text())

    def test_config_migrates_from_old_file_name(self):
        old = self.tmp / core.LEGACY_CONFIG_NAME
        old.write_text(json.dumps({"share": "E:\\", "steam_lang": "brazilian", "meta_global": "replace"}))
        cfg = core.load_config(self.tmp / core.CONFIG_NAME)
        self.assertEqual(cfg["share"], "E:\\")
        self.assertEqual(cfg["meta_global"], "replace")
        self.assertEqual(cfg["steam_lang"], "english")                # metadata is English only
        core.save_config(cfg, self.tmp / core.CONFIG_NAME)
        self.assertEqual(core.load_config(self.tmp / core.CONFIG_NAME)["share"], "E:\\")

    # ---- discovery, categories, profiles
    def test_game_discovery_ignores_and_sorting(self):
        for n in ("b.sh", "A.sh", "PortMaster.sh", "._junk.sh", "notes.txt"):
            self.port(n)
        self.assertEqual(core.list_games(self.cfg), ["A.sh", "b.sh"])

    def test_custom_category_and_profile(self):
        self.assertIn("knulli", core.PROFILES)
        self.assertEqual(core.profile({"profile": "unknown"}), core.PROFILES["knulli"])
        folder = core.slug_folder("Nintendo 64!", [c["folder"] for c in self.cfg["categories"]])
        self.assertTrue(core.FOLDER_RE.match(folder))
        self.cfg["categories"].append({"folder": folder, "name": "Nintendo 64", "manufacturer": "Nintendo", "release": "1996",
                                       "platform": "n64", "theme": "n64"})
        core.install_systems(self.cfg, False, self.log)
        self.assertTrue(core.system_cfg_path(self.cfg, self.cfg["categories"][-1]).exists())
        self.assertEqual(core.theme_from_label(core.theme_label("steam")), "steam")

    def test_handmade_launcher_is_never_overwritten(self):
        self.port("Wind Waker.sh")
        d = self.share / "roms" / "portgamecube"
        d.mkdir(parents=True)
        mine = d / "Wind Waker.sh"
        text = '#!/bin/bash\nTARGET="/userdata/roms/ports/Wind Waker.sh"\nexec bash "$TARGET" "$@"\n'
        mine.write_text(text)
        self.game("Wind Waker.sh", "portgamecube", steam_checked=True, shot_mode="none")
        core.apply_game(self.cfg, "Wind Waker.sh", self.log)
        self.assertEqual(mine.read_text(), text)
        self.assertTrue(any("existing launcher kept" in m for m in self.logs))
        core.remove_wrappers(self.cfg, self.log)
        self.assertTrue(mine.exists())                                 # undo does not delete files it did not create

    def test_image_management_local_and_web_choice(self):
        self.port("Celeste.sh")
        local = self.tmp / "mine.png"
        local.write_bytes(png_bytes(1600, 900))
        self.game("Celeste.sh", "portpc", steam_checked=True, meta_mode="keep", shot_mode="local", shot_local=str(local))
        core.apply_game(self.cfg, "Celeste.sh", self.log)
        img = self.share / "roms" / "portpc" / "images" / "Celeste-image.jpg"
        self.assertTrue(img.exists())
        if Image is not None:
            with Image.open(img) as im:
                self.assertLessEqual(im.width, 640)
        self.assertEqual(self.entry("portpc", "Celeste.sh")["image"], "./images/Celeste-image.jpg")
        self.net.calls.clear()
        self.cfg["games"]["Celeste.sh"].update(shot_mode="web", shot_idx=1, steam_id="504230", steam_checked=True)
        core.apply_game(self.cfg, "Celeste.sh", self.log)
        self.assertIn("f1", self.net.calls)                           # the chosen screenshot was downloaded
        self.assertNotIn("f0", self.net.calls)

    def test_existing_image_is_kept_in_automatic_mode(self):
        self.port("Simpsons.sh")
        self.complete_entry()
        self.game("Simpsons.sh", "portps2", meta_mode="keep", steam_checked=True, shot_mode="auto")
        core.apply_game(self.cfg, "Simpsons.sh", self.log)
        self.assertEqual(self.entry("portps2", "Simpsons.sh")["image"], "./images/s.jpg")

    def test_version_and_title_constants(self):
        self.assertRegex(core.VERSION, r"^\d+\.\d+\.\d+$")

    def test_unsupported_file_name_is_skipped(self):
        self.game('Bad"Name.sh', "portpc")
        core.apply_game(self.cfg, 'Bad"Name.sh', self.log)
        self.assertTrue(any("unsupported" in m for m in self.logs))

    def test_steam_auto_match(self):
        self.assertEqual(core.steam_auto_match("Celeste"), ("504230", "Celeste"))
        self.assertIsNone(core.steam_auto_match("Super Mario Galaxy"))
        self.assertEqual(core.default_term("StardewValley.sh"), "Stardew Valley")

    def test_share_detection_function_runs(self):
        self.assertIsInstance(core.find_share_candidates(), list)

    def test_metadata_is_requested_in_english(self):
        self.port("Celeste.sh")
        self.game("Celeste.sh", "portpc", shot_mode="none")
        self.cfg["steam_lang"] = "brazilian"
        core.apply_game(self.cfg, "Celeste.sh", self.log)      # FakeNet raises if a non-English call is made
        self.assertTrue(any("l=english" in u for u in self.net.calls if "appdetails" in u))


# ---------------------------------------------------------------- repository, branding, English-only
SRC = ROOT / "src" / "portmasterforwarder"
PY_FILES = [SRC / "app.py", SRC / "padgui.py", SRC / "core.py", SRC / "meta.py", SRC / "__init__.py", SRC / "__main__.py"]
DOCS = [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "CONTRIBUTING.md", ROOT / "SECURITY.md", ROOT / "THIRD_PARTY_NOTICES.md",
        ROOT / "CODE_OF_CONDUCT.md"] + sorted((ROOT / "docs").glob("*.md")) + sorted((ROOT / ".github").rglob("*.md"))


class ProjectTests(unittest.TestCase):
    def test_branding(self):
        self.assertEqual(core.APP_NAME, "PortMasterForwarder")
        self.assertEqual(core.TAGLINE, "Your games. Properly organized.")
        allowed = re.compile(r"(?i)(legacy|previous|formerly|older|earlier|PortForwarder\\|PORTFORWARDER_HOME|gerado por|knulli_categorias|during private development)")
        for f in PY_FILES + DOCS + [ROOT / "pyproject.toml", ROOT / ".github" / "workflows" / "release.yml"]:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if allowed.search(line):
                    continue
                self.assertNotRegex(line, r"PortForwarder|portforwarder(?!\.json)|Knulli ?Categorias", "%s:%d: %s" % (f.name, i, line.strip()[:90]))

    def test_independence_from_portmaster_is_stated_clearly(self):
        self.assertIn("not affiliated", core.INDEPENDENCE_SHORT.lower())
        self.assertIn("PortMaster", core.INDEPENDENCE_NOTICE)
        for needle in ("not affiliated with", "endorsed by", "connected to the"):
            self.assertIn(needle, core.INDEPENDENCE_NOTICE)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertRegex(readme[:3000], r"(?is)independent.*not affiliated with.*PortMaster")
        self.assertIn("will be renamed", readme)
        self.assertIn("independent", (ROOT / "docs" / "INDEPENDENCE.md").read_text(encoding="utf-8").lower())
        app_src = (SRC / "app.py").read_text(encoding="utf-8")
        self.assertIn("core.INDEPENDENCE_NOTICE", app_src)          # About window
        self.assertIn("core.INDEPENDENCE_SHORT", app_src)           # permanent footer line
        self.assertIn("PortMaster", (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8"))
        self.assertIn("not affiliated with PortMaster", (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))

    def test_english_only_in_code_and_docs(self):
        pt = re.compile(r"\b(nao|não|jogos?|atalho|categoria|escolh\w+|aplicar|cartão|cartao|pasta|resumo|nota|gênero|"
                        r"desenvolvedora|procurar|substituir|completar|mantid\w+|falta\w*)\b", re.I)
        for f in PY_FILES + DOCS:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                if "LEGACY" in line or "gerado por" in line or "_BANNED" in line or "is_mostly_english" in line or "pt_es_fr" in line:
                    continue
                self.assertIsNone(pt.search(line), "%s:%d: %s" % (f.name, i, line.strip()[:100]))

    def test_no_literal_backslash_n_in_ui_strings(self):
        for f in PY_FILES:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                self.assertNotIn("\\\\n", line, "%s:%d literal backslash-n in a string" % (f.name, i))

    def test_theme_for_gamecube_is_gc(self):
        self.assertIn("gc", core.THEME_KEYS)
        self.assertEqual(core.DEFAULT_CATEGORIES[0]["theme"], "gc")

    def test_repository_has_the_standard_files(self):
        for name in ("LICENSE", "README.md", "CHANGELOG.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
                     "THIRD_PARTY_NOTICES.md", "pyproject.toml", "requirements.txt", "requirements-dev.txt", ".gitignore",
                     ".gitattributes", ".editorconfig", "packaging/portmasterforwarder.spec", "packaging/build_exe.bat", "packaging/launcher.py",
                     "docs/ARCHITECTURE.md", "docs/METADATA_RULES.md", "docs/KNULLI.md", "docs/BUILDING.md", "docs/INDEPENDENCE.md", "docs/GAMEPAD.md", "README.pt-BR.md", "launcher/PortMasterForwarder.sh", "scripts/build_release.sh", "extras/McpeLauncher.sh",
                     ".github/workflows/ci.yml", ".github/workflows/release.yml", ".github/PULL_REQUEST_TEMPLATE.md",
                     ".github/ISSUE_TEMPLATE/bug_report.md", ".github/ISSUE_TEMPLATE/feature_request.md",
                     "src/portmasterforwarder/assets/icon.ico", "src/portmasterforwarder/assets/icon.png", "src/portmasterforwarder/assets/logo.png"):
            self.assertTrue((ROOT / name).exists(), name)

    def test_license_is_open_source(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", text)
        self.assertIn("Permission is hereby granted, free of charge", text)
        self.assertIn("MIT", (ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_version_is_consistent(self):
        self.assertRegex(PKG_VERSION, r"^\d+\.\d+\.\d+$")
        self.assertEqual(core.VERSION, PKG_VERSION)
        self.assertRegex((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), r"## \[?%s\]?" % re.escape(PKG_VERSION))
        self.assertIn("attr = \"portmasterforwarder.__version__\"", (ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_knulli_only_notice_is_clear_everywhere(self):
        self.assertIn("tested on Knulli only", core.COMPAT_NOTICE)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertRegex(readme[:1500], r"(?i)tested (only )?on Knulli")
        self.assertIn("untested", (ROOT / "docs" / "KNULLI.md").read_text(encoding="utf-8").lower())
        app_src = (SRC / "app.py").read_text(encoding="utf-8")
        self.assertIn("Tested on Knulli only", app_src)
        self.assertIn("core.COMPAT_NOTICE", app_src)

    def test_build_files_reference_the_exe(self):
        for rel in (".github/workflows/release.yml", "packaging/portmasterforwarder.spec", "packaging/build_exe.bat", "docs/BUILDING.md"):
            self.assertIn("PortMasterForwarder", (ROOT / rel).read_text(encoding="utf-8"), rel)
        self.assertIn("windows-latest", (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"))
        self.assertIn("assets", (ROOT / "packaging/portmasterforwarder.spec").read_text(encoding="utf-8"))

    def test_icon_assets_are_valid_images(self):
        if Image is None:
            self.skipTest("Pillow not installed")
        with Image.open(SRC / "assets" / "icon.png") as im:
            self.assertEqual(im.size, (256, 256))
        with Image.open(SRC / "assets" / "icon.ico") as im:
            self.assertIn((256, 256), im.info["sizes"])
        with Image.open(SRC / "assets" / "logo.png") as im:
            self.assertEqual(im.size, (512, 512))

    def test_launcher_uses_the_package_entry_point(self):
        self.assertIn("from portmasterforwarder.app import main", (ROOT / "packaging" / "launcher.py").read_text(encoding="utf-8"))

    def test_self_test_flag_exists_for_the_exe_smoke_test(self):
        src = (SRC / "app.py").read_text(encoding="utf-8")
        self.assertIn("--self-test", src)
        self.assertIn("--self-test", (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))


class ConfigLocationTests(Base):
    def test_config_dir_override_and_defaults(self):
        old = os.environ.get("PORTMASTERFORWARDER_HOME")
        try:
            os.environ["PORTMASTERFORWARDER_HOME"] = str(self.tmp / "home")
            self.assertEqual(core.config_path(), self.tmp / "home" / core.CONFIG_NAME)
            del os.environ["PORTMASTERFORWARDER_HOME"]
            self.assertEqual(core.config_dir().name, "PortMasterForwarder")
        finally:
            if old is not None:
                os.environ["PORTMASTERFORWARDER_HOME"] = old
            else:
                os.environ.pop("PORTMASTERFORWARDER_HOME", None)

    def test_save_creates_the_folder_and_round_trips(self):
        target = self.tmp / "deep" / "er" / core.CONFIG_NAME
        core.save_config(self.cfg, target)
        self.assertEqual(core.load_config(target)["share"], str(self.share))

    def test_settings_next_to_the_program_are_imported_once(self):
        program_dir = self.tmp / "program"
        program_dir.mkdir()
        (program_dir / core.LEGACY_CONFIG_NAME).write_text(json.dumps({"share": "E:\\", "meta_global": "replace"}))
        cfg = core.load_config(self.tmp / "appdata" / core.CONFIG_NAME, [program_dir])
        self.assertEqual((cfg["share"], cfg["meta_global"]), ("E:\\", "replace"))
        (program_dir / core.CONFIG_NAME).write_text(json.dumps({"share": "F:\\"}))
        new = self.tmp / "appdata" / core.CONFIG_NAME
        core.save_config(cfg, new)
        self.assertEqual(core.load_config(new, [program_dir])["share"], "E:\\")   # the new file wins over older ones

    def test_files_from_the_previous_project_name_are_recognized(self):
        d = self.share / "roms" / "portpc"
        d.mkdir(parents=True)
        (d / "Old.sh").write_text('#!/bin/bash\n# generated by PortForwarder\nTARGET="/userdata/roms/ports/Old.sh"\nexec bash "$TARGET"\n')
        self.port("Old.sh")
        self.assertEqual(core.scan_existing(self.cfg)["Old.sh"], "portpc")
        cfgdir = self.share / "system" / "configs" / "emulationstation"
        legacy = cfgdir / "es_systems_portpc.cfg"
        legacy.write_text("<?xml version='1.0'?>\n<!-- generated by PortForwarder -->\n<systemList/>")
        self.assertEqual(core.foreign_cfgs(self.cfg), [])
        core.remove_systems(self.cfg, False, self.log)
        core.remove_wrappers(self.cfg, self.log)
        self.assertFalse(legacy.exists())
        self.assertFalse((d / "Old.sh").exists())

    def test_settings_of_the_previous_project_name_are_imported(self):
        old_dir = self.tmp / "PortForwarder"
        old_dir.mkdir()
        (old_dir / core.PREVIOUS_CONFIG_NAME).write_text(json.dumps({"share": "G:\\", "meta_global": "replace"}))
        cfg = core.load_config(self.tmp / "PortMasterForwarder" / core.CONFIG_NAME, [old_dir])
        self.assertEqual((cfg["share"], cfg["meta_global"]), ("G:\\", "replace"))
        self.assertTrue(any(d.name == "PortForwarder" for d in core.legacy_config_dirs()))

    def test_resource_path_points_inside_the_package(self):
        self.assertTrue(core.resource_path("assets/icon.png").exists())
        self.assertTrue(core.resource_path("assets/icon.ico").exists())
        self.assertTrue(core.resource_path("assets/logo.png").exists())


# ---------------------------------------------------------------- per-field sources, pins, presets, categories
class FieldSourceTests(Base):
    def ww(self, **st):
        self.port("Wind Waker.sh")
        base = dict(steam_checked=True, shot_mode="none", meta_mode="keep")
        base.update(st)
        self.game("Wind Waker.sh", "portgamecube", **base)

    def run_ww(self):
        core.apply_game(self.cfg, "Wind Waker.sh", self.log)
        return self.entry("portgamecube", "Wind Waker.sh")

    def test_each_block_can_use_its_own_source(self):
        self.cfg.update(rawg_key="K")
        self.cfg["sources"]["rawg"] = True
        self.ww(src={"rating": "wikipedia", "genre": "rawg", "desc": "wikipedia", "releasedate": "rawg"})
        e = self.run_ww()
        self.assertEqual(e["genre"], pm.ADVENTURE)                                 # RAWG label
        self.assertIn("sails", e["desc"])                                          # Wikipedia gameplay section
        self.assertEqual(e["rating"], "0.86")                                      # Wikidata aggregators, balanced
        self.assertEqual(e["releasedate"], "20021213T000000")                      # RAWG fact
        self.assertNotIn("developer", e)                                           # block left alone (mode keep, auto)

    def test_google_single_source_rating_is_dampened_not_copied(self):
        self.cfg.update(google_key="G", google_cx="C")
        self.cfg["sources"]["google"] = True
        self.ww(src={"rating": "google"})
        r = float(self.run_ww()["rating"])
        self.assertTrue(0.70 < r < 0.85, r)                                        # 4.5/5 = 0.90 would be a plain copy

    def test_source_that_is_switched_off_is_reported(self):
        self.ww(src={"genre": "rawg"})
        e = self.run_ww()
        self.assertNotIn("genre", e)
        self.assertTrue(any("switched off or needs a key" in m for m in self.logs))

    def test_keep_blocks_survive_replace_mode(self):
        d = self.share / "roms" / "portgamecube"
        d.mkdir(parents=True)
        (d / "gamelist.xml").write_text('<gameList><game><path>./Wind Waker.sh</path><name>WW</name><desc>Old text</desc><genre>Platform</genre></game></gameList>')
        self.ww(meta_mode="replace", src={"desc": "keep"})
        e = self.run_ww()
        self.assertEqual(e["desc"], "Old text")                                    # block set to Keep current
        self.assertEqual(e["genre"], pm.ADVENTURE)                                 # others replaced and standardized

    def test_pinned_values_are_normalized_and_win(self):
        self.ww(manual={"rating": "8.6", "releasedate": "25/01/2018", "genre": "platform", "developer": " Maddy ",
                        "desc": "You jump, dash and climb across hundreds of challenges."})
        e = self.run_ww()
        self.assertEqual((e["rating"], e["releasedate"], e["genre"], e["developer"]), ("0.86", "20180125T000000", pm.PLATFORMER, "Maddy"))
        self.assertTrue(e["desc"].startswith("You jump"))
        self.assertEqual(self.net.calls, [])                                       # everything pinned: no network

    def test_invalid_pinned_values_are_ignored(self):
        self.ww(manual={"rating": "abc", "releasedate": "someday", "genre": "Roguelike"})
        e = self.run_ww()
        for tag in ("rating", "releasedate", "genre"):
            self.assertNotIn(tag, e)
        self.assertEqual(len([m for m in self.logs if "is not valid, ignored" in m]), 3)

    def test_ai_source_needs_configuration_then_works(self):
        self.ww(src={"desc": "ai", "genre": "ai", "rating": "ai"})
        self.assertNotIn("desc", self.run_ww())
        self.assertTrue(any("AI evaluation is not configured" in m for m in self.logs))
        self.cfg.update(ai_enabled=True, anthropic_key="K")
        core.AI_POST = lambda url, payload, headers: {"content": [{"type": "text", "text": json.dumps({
            "genre": "Adventure", "description": "You sail between islands and explore dungeons. Puzzles and combat gate your progress.",
            "rating": 9.0, "basis": "tight design"})}]}
        e = self.run_ww()
        self.assertEqual((e["genre"], e["rating"]), ("Adventure", "0.90"))

    def test_rawg_image_mode(self):
        self.cfg.update(rawg_key="K")
        self.cfg["sources"]["rawg"] = True
        self.ww(shot_mode="rawg", meta_mode="keep")
        e = self.run_ww()
        self.assertIn("bg.jpg", self.net.calls)
        self.assertTrue(e["image"].startswith("./images/Wind Waker-image"))

    def test_fetch_field_for_one_block_writes_nothing(self):
        self.port("Celeste.sh")
        self.game("Celeste.sh", "portpc")
        value, upd = core.fetch_field(self.cfg, "Celeste.sh", "genre", "steam", self.log)
        self.assertEqual(value, pm.PLATFORMER)
        self.assertEqual(upd["steam_id"], "504230")
        self.assertFalse((self.share / "roms" / "portpc" / "gamelist.xml").exists())
        value, _ = core.fetch_field(self.cfg, "Celeste.sh", "rating", "steam", self.log)
        self.assertRegex(value, r"^0\.\d\d$")
        self.assertNotEqual(value, "0.94")

    def test_fetch_image_options(self):
        self.port("Celeste.sh")
        self.game("Celeste.sh", "portpc")
        shots, upd = core.fetch_image_options(self.cfg, "Celeste.sh", "steam", self.log)
        self.assertEqual(shots, [("t0", "f0"), ("t1", "f1")])
        self.assertEqual(upd["steam_id"], "504230")

    def test_presets(self):
        names = core.all_presets(self.cfg)
        for n in ("Balanced (all sources)", "Steam", "Wikipedia", "RAWG", "Google", "AI evaluation", "Keep current"):
            self.assertIn(n, names)
        st = dict(core.DEFAULT_GAME, cat="portpc", manual={"rating": "0.5", "developer": "X"}, rating="")
        core.apply_preset(st, core.BUILTIN_PRESETS["Steam"])
        self.assertTrue(all(st["src"][t] == "steam" for t in core.BLOCK_FIELDS))
        self.assertEqual(st["manual"], {})
        self.assertEqual(st["shot_mode"], "web")
        core.apply_preset(st, core.BUILTIN_PRESETS["Google"])
        self.assertEqual((st["src"]["rating"], st["src"]["releasedate"]), ("google", "auto"))
        core.apply_preset(st, core.BUILTIN_PRESETS["Keep current"])
        self.assertTrue(all(v == "keep" for v in st["src"].values()))
        self.cfg["presets"]["Mine"] = core.preset_from_state(st)
        self.assertEqual(core.all_presets(self.cfg)["Mine"]["rating"], "keep")

    def test_sources_offered_per_field(self):
        self.assertNotIn("google", core.sources_for_field("releasedate"))
        self.assertNotIn("ai", core.sources_for_field("developer"))
        self.assertIn("ai", core.sources_for_field("rating"))
        self.assertEqual(core.sources_for_field("genre")[0], "auto")
        self.assertEqual(core.sources_for_field("genre")[-1], "keep")

    def test_normalize_helpers(self):
        self.assertEqual(core.normalize_date("2018-01-25"), "20180125T000000")
        self.assertEqual(core.normalize_date("25/01/2018"), "20180125T000000")
        self.assertEqual(core.normalize_date("20180125"), "20180125T000000")
        self.assertEqual(core.normalize_date("2018"), "20180101T000000")
        self.assertIsNone(core.normalize_date("31/02/2018"))
        self.assertIsNone(core.normalize_manual("genre", "Roguelike"))
        self.assertEqual(core.normalize_manual("rating", "85"), "0.85")
        self.assertIsNone(core.normalize_manual("rating", "abc"))
        self.assertEqual(core.display_value("rating", "0.86"), "8.6")
        self.assertEqual(core.display_value("rating", "0.9"), "9")
        self.assertEqual(core.display_value("releasedate", "20180125T000000"), "2018-01-25")

    def test_add_category(self):
        before = len(self.cfg["categories"])
        cat = core.add_category(self.cfg, "Nintendo 64", "n64")
        self.assertEqual(len(self.cfg["categories"]), before + 1)
        self.assertTrue(core.FOLDER_RE.match(cat["folder"]))
        self.assertEqual((cat["platform"], cat["theme"]), ("n64", "n64"))
        again = core.add_category(self.cfg, "Nintendo 64", "n64")
        self.assertNotEqual(cat["folder"], again["folder"])                        # unique folders
        with self.assertRaises(ValueError):
            core.add_category(self.cfg, "  ")
        core.install_systems(self.cfg, False, self.log)
        self.assertTrue(core.system_cfg_path(self.cfg, cat).exists())
        self.assertTrue((self.share / "roms" / cat["folder"]).is_dir())

    def test_existing_entry_and_image_path(self):
        d = self.share / "roms" / "portgamecube"
        (d / "images").mkdir(parents=True)
        (d / "images" / "a.jpg").write_bytes(b"x" * 100)
        (d / "gamelist.xml").write_text("<gameList><game><path>./Wind Waker.sh</path><name>WW</name><image>./images/a.jpg</image><rating>0.9</rating></game></gameList>")
        self.ww()
        e = core.existing_entry(self.cfg, "Wind Waker.sh")
        self.assertEqual((e["name"], e["rating"]), ("WW", "0.9"))
        self.assertEqual(core.existing_image_path(self.cfg, "Wind Waker.sh"), d / "images" / "a.jpg")


class GamepadEditionTests(Base):
    def mcpe(self, ver="1.2.3"):
        self.port("McpeLauncher.sh")
        (self.share / "roms" / "ports" / "mcpe_launcher" / "versions" / ver / "lib").mkdir(parents=True)

    def test_saved_custom_folder_is_discovered_once(self):
        self.mcpe()
        d = self.share / "roms" / "portandroid"
        d.mkdir()
        (d / "Minecraft 1.2.3.sh").write_text('#!/bin/bash\nbash /userdata/roms/ports/McpeLauncher.sh "1.2.3"\n')
        names = set(core.list_games(self.cfg))
        self.assertEqual(core.discover_folders(self.cfg, names), ["portandroid"])
        self.assertEqual(core.scan_existing(self.cfg)["Minecraft 1.2.3.sh"], "portandroid")
        self.assertEqual(core.discover_folders(self.cfg, names), [])

    def test_hand_made_launcher_in_discovered_folder_is_not_overwritten(self):
        self.mcpe()
        d = self.share / "roms" / "portandroid"
        d.mkdir()
        mine = "#!/bin/bash\n# mine\nbash x\n"
        (d / "Minecraft 1.2.3.sh").write_text(mine)
        core.discover_folders(self.cfg, set(core.list_games(self.cfg)))
        self.game("Minecraft 1.2.3.sh", "portandroid")
        core.apply_game(self.cfg, "Minecraft 1.2.3.sh", self.log)
        self.assertEqual((d / "Minecraft 1.2.3.sh").read_text(), mine)

    def test_padgui_only_uses_core_functions_that_exist(self):
        import ast
        tree = ast.parse((SRC / "padgui.py").read_text(encoding="utf-8"))
        used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "core"}
        self.assertTrue(used)
        self.assertEqual([a for a in sorted(used) if not hasattr(core, a)], [])

    def test_entry_point_dispatch_and_launcher(self):
        main_src = (SRC / "__main__.py").read_text(encoding="utf-8")
        for needle in ("--gamepad", "--desktop", "padgui", "PORTMASTERFORWARDER_UI"):
            self.assertIn(needle, main_src)
        self.assertIn("-m portmasterforwarder --gamepad", (ROOT / "launcher" / "PortMasterForwarder.sh").read_text(encoding="utf-8"))
        self.assertIn("portmasterforwarder.padgui:main", (ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    def test_release_workflow_publishes_both_editions(self):
        wf = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        for needle in ("windows-latest", "scripts/build_release.sh", "PortMasterForwarder.exe", "-knulli.zip"):
            self.assertIn(needle, wf)


class RewriteTests(Base):
    def genre(self):
        import xml.etree.ElementTree as ET
        r = ET.parse(self.share / "roms" / "portpc" / "gamelist.xml").getroot()
        return r.find("game").findtext("genre")

    def test_typed_value_rewrites_only_for_single_game_save(self):
        self.port("Foo.sh")
        self.game("Foo.sh", "portpc")
        self.cfg["games"]["Foo.sh"]["manual"] = {"genre": "RPG"}
        core.apply_game(self.cfg, "Foo.sh", self.log)
        self.assertIn("RPG", self.genre())
        self.cfg["games"]["Foo.sh"]["manual"] = {"genre": "Action"}
        core.apply_game(self.cfg, "Foo.sh", self.log)                       # global apply: existing value kept
        self.assertIn("RPG", self.genre())
        core.apply_game(self.cfg, "Foo.sh", self.log, rewrite=True)         # single save: rewritten
        self.assertIn("Action", self.genre())


class CategoryEditTests(Base):
    def test_rename_and_change_icon(self):
        core.update_category(self.cfg, "portpc", name="My PC", theme="3ds")
        c = core.cat_by_folder(self.cfg, "portpc")
        self.assertEqual((c["name"], c["theme"], c["platform"]), ("My PC", "3ds", "3ds"))
        core.install_systems(self.cfg, True, self.log, only="portpc")
        xml = (self.share / "system" / "configs" / "emulationstation" / "es_systems_portpc.cfg").read_text()
        self.assertIn("My PC", xml)
        with self.assertRaises(ValueError):
            core.update_category(self.cfg, "portpc", name="  ")


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- GUI smoke (fake tkinter, runs anywhere)
class GuiSmokeTests(Base):
    def test_block_gui_flow_with_fake_tkinter(self):
        import time
        import types
        names = ("tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox", "tkinter.scrolledtext", "tkinter.simpledialog", "portmasterforwarder.app")
        saved = {k: sys.modules.get(k) for k in names}

        class Var:
            def __init__(self, master=None, value=None, **k):
                self.v = "" if value is None else value
                self.cbs = []

            def get(self):
                return self.v

            def set(self, v):
                self.v = v
                for cb in self.cbs:
                    cb()

            def trace_add(self, mode, cb):
                self.cbs.append(cb)

        class W:
            def __init__(self, *a, **k):
                self._text = ""

            def __getattr__(self, n):
                return lambda *a, **k: None

            def winfo_children(self):
                return []

            def winfo_exists(self):
                return True

        class Tk(W):
            def after(self, *a):
                pass

        class Combobox(W):
            def __init__(self, *a, **k):
                super().__init__()
                self.values = list(k.get("values", []))
                self.text = ""

            def configure(self, **k):
                if "values" in k:
                    self.values = list(k["values"])

            def set(self, t):
                self.text = t

            def get(self):
                return self.text

            def current(self, i=None):
                if i is not None:
                    self.text = self.values[i]
                    return None
                return self.values.index(self.text) if self.text in self.values else -1

        class Text(W):
            def get(self, *a):
                return self._text

            def insert(self, i, t):
                self._text = t

            def delete(self, *a):
                self._text = ""

        tk = types.ModuleType("tkinter")
        ttk = types.ModuleType("tkinter.ttk")
        for n in ("Frame", "Label", "Button", "Entry", "LabelFrame", "Radiobutton", "Scrollbar", "Style", "Checkbutton", "PanedWindow"):
            setattr(ttk, n, W)
        ttk.Combobox = Combobox
        tk.Tk, tk.Toplevel, tk.Canvas, tk.Listbox, tk.Text, tk.Frame, tk.Label = Tk, Tk, W, W, Text, W, W
        tk.StringVar = tk.IntVar = tk.BooleanVar = Var
        tk.TclError = Exception
        fd, mb, sc, sd = (types.ModuleType("tkinter." + n) for n in ("filedialog", "messagebox", "scrolledtext", "simpledialog"))
        fd.askdirectory = lambda **k: ""
        fd.askopenfilename = lambda **k: ""
        mb.showinfo = mb.showerror = lambda *a, **k: None
        mb.askyesno = lambda *a, **k: True
        sc.ScrolledText = W
        sd.askstring = lambda *a, **k: "My preset"
        for k, m in (("tkinter", tk), ("tkinter.ttk", ttk), ("tkinter.filedialog", fd), ("tkinter.messagebox", mb),
                     ("tkinter.scrolledtext", sc), ("tkinter.simpledialog", sd)):
            sys.modules[k] = m
        sys.modules.pop("portmasterforwarder.app", None)
        old_pil = core.HAS_PIL
        core.HAS_PIL = False                                   # no real Tk images in the fake environment
        try:
            import portmasterforwarder.app as g

            core.HAS_PIL = old_pil                                 # command-line flags (used by CI on the .exe)
            self.assertEqual(g.main(["--version"]), 0)
            self.assertEqual(g.main(["--self-test"]), 0 if old_pil else 1)
            core.HAS_PIL = False

            def pump(cond, n=100):
                for _ in range(n):
                    time.sleep(0.03)
                    app._poll()
                    if cond():
                        break

            g.CONFIG_FILE = self.tmp / "gui.json"
            self.port("Celeste.sh")
            self.port("Super Mario Galaxy.sh")
            (self.tmp / "gui.json").write_text(json.dumps({"share": str(self.share)}))
            app = g.App()
            self.assertEqual(app.names, ["Celeste.sh", "Super Mario Galaxy.sh"])
            self.assertEqual(app.cur, "Celeste.sh")                                # first game selected automatically
            self.assertEqual(set(app.blocks), set(core.BLOCK_FIELDS))

            app.rows["Celeste.sh"]["cb"].current(3)                                # PC
            app.on_cat("Celeste.sh")
            pump(lambda: not app.looking)
            self.assertEqual(app.state("Celeste.sh")["steam_id"], "504230")

            # type a rating in its block -> pinned + preview updates
            app.blocks["rating"].set("8.6")
            app.on_block_edit("rating")
            self.assertEqual(app.state("Celeste.sh")["manual"]["rating"], "0.86")
            self.assertIn("edited", app.badge_text("Celeste.sh"))
            self.assertEqual(app.preview.v_line2.get(), "Rating: 8.6 / 10")

            # fetch the genre block from Steam -> value appears and is pinned
            app.blocks["genre"].set_src("steam")
            app.on_src_change("genre")
            app.fetch_block("genre")
            pump(lambda: core.manual_value(app.state("Celeste.sh"), "genre"))
            self.assertEqual(app.blocks["genre"].get(), pm.PLATFORMER)
            self.assertIn(pm.PLATFORMER, app.preview.v_line1.get())

            # preset applies to this game and clears pins of the blocks it defines
            app.preset_cb.set("Wikipedia")
            app.preset_this()
            st = app.state("Celeste.sh")
            self.assertTrue(all(st["src"][t] == "wikipedia" for t in core.BLOCK_FIELDS))
            self.assertEqual(st["manual"], {})
            app.save_preset()
            self.assertIn("My preset", app.cfg["presets"])

            # the real "New category" dialog validates its input
            got = []
            dlg = g.NewCategoryDialog(app, lambda name, theme: got.append((name, theme)))
            dlg.v_name.set("   ")
            dlg.ok()
            self.assertEqual(got, [])                                              # empty name is refused
            dlg.v_name.set("Nintendo 64")
            dlg.v_theme.set("Nintendo 64  (n64)")
            dlg.ok()
            self.assertEqual(got, [("Nintendo 64", "n64")])

            # new category created from the list, game gets assigned to it
            g.NewCategoryDialog = lambda _app, ok, on_cancel=None: ok("Nintendo 64", "n64")
            app.new_category("Super Mario Galaxy.sh")
            self.assertEqual(app.cat_names()[-1], "Nintendo 64")
            self.assertEqual(app.state("Super Mario Galaxy.sh")["cat"], app.cfg["categories"][-1]["folder"])

            # pin again and APPLY: everything lands in the game list, pins are consumed
            app.preset_cb.set("Balanced (all sources)")
            app.preset_this()
            app.blocks["rating"].set("7")
            app.on_block_edit("rating")
            app.blocks["developer"].set("Maddy Makes Games")
            app.on_block_edit("developer")
            app.apply()
            pump(lambda: not app.busy)
            e = self.entry("portpc", "Celeste.sh")
            self.assertEqual((e["rating"], e["developer"]), ("0.70", "Maddy Makes Games"))
            self.assertIn(e["genre"], pm.GENRES)
            self.assertEqual(app.state("Celeste.sh")["manual"], {})
            self.assertTrue((self.share / "roms" / app.cfg["categories"][-1]["folder"] / "Super Mario Galaxy.sh").exists())
            g.OptionsDialog(app).save()
            g.CategoriesDialog(app).save()

        finally:
            core.HAS_PIL = old_pil
            for k, m in saved.items():
                if m is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = m


class McpeVersionTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)
        self.ports = self.root / "roms" / "ports"
        for v in ("1.16.101", "Minecraft 1.17.41.01"):
            (self.ports / "mcpe_launcher" / "versions" / v / "lib").mkdir(parents=True)
        (self.ports / "mcpe_launcher" / "versions" / "empty").mkdir()
        (self.ports / "McpeLauncher.sh").write_text("#!/bin/bash\n")
        self.cfg = core.load_config(self.root / "none.json")
        self.cfg["share"] = str(self.root)
        self.cfg["games"] = {}

    def test_discovery_wrapper_and_cleanup(self):
        names = core.list_games(self.cfg)
        self.assertIn("Minecraft 1.16.101.sh", names)
        self.assertIn("Minecraft 1.17.41.01.sh", names)
        self.assertNotIn("Minecraft empty.sh", names)
        cat = self.cfg["categories"][0]["folder"]
        for n in ("Minecraft 1.16.101.sh", "McpeLauncher.sh"):
            self.cfg["games"][n] = {"cat": cat}
        self.cfg["sources"] = {k: False for k in self.cfg["sources"]}   # no network in tests
        core.apply_all(self.cfg, lambda m: None)
        cdir = self.root / "roms" / cat
        text = (cdir / "Minecraft 1.16.101.sh").read_text()
        self.assertIn('exec bash "$TARGET" "1.16.101"', text)
        self.assertIn("McpeLauncher.sh", text)
        self.assertEqual(core.scan_existing(self.cfg).get("Minecraft 1.16.101.sh"), cat)
        self.assertEqual(core.scan_existing(self.cfg).get("McpeLauncher.sh"), cat)
        import shutil
        shutil.rmtree(self.ports / "mcpe_launcher" / "versions" / "1.16.101")
        core.apply_all(self.cfg, lambda m: None)
        self.assertFalse((cdir / "Minecraft 1.16.101.sh").exists())
        self.assertTrue((cdir / "McpeLauncher.sh").exists())

    def test_option_off_and_search_term(self):
        self.cfg["mcpe_versions"] = False
        self.assertEqual(core.list_games(self.cfg), ["McpeLauncher.sh"])
        self.assertEqual(core.default_term("Minecraft 1.16.101.sh"), "Minecraft")


if __name__ == "__main__":
    unittest.main()

