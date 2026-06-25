import unittest

from aivstudio.blackboard import Blackboard
from aivstudio.agents.director import NarrativeDirectorAgent
from aivstudio.memory.records import Segment
from aivstudio.skills.perception import EmbedSkill

_embed = EmbedSkill()


def seg(sid, v, a, sp, tags, transcript=""):
    return Segment(
        seg_id=sid, asset_id=sid, source_name=sid + ".mp4", proxy_path=sid + ".mp4",
        in_s=0, out_s=4,
        scores={"visual_quality": v, "audio_quality": a, "speech_value": sp, "emotion": 0.7},
        tags=tags, transcript=transcript,
        embedding=_embed.run(tags=tags, transcript=transcript)["embedding"],
    )


class TestPairing(unittest.TestCase):
    def test_soundbite_gets_broll_cover(self):
        segs = [
            seg("sb1", 0.2, 0.1, 0.9, ["motivational", "quote"], "keep pushing"),  # soundbite
            seg("br1", 0.9, 0.2, 0.0, ["sunrise", "wide", "motivational"]),         # b-roll cover
            seg("br2", 0.88, 0.2, 0.0, ["coast", "wide"]),
            seg("hero", 0.9, 0.85, 0.2, ["summit", "triumph"]),                     # hero
            seg("br3", 0.8, 0.25, 0.0, ["ridge", "drone"]),
            seg("br4", 0.78, 0.25, 0.0, ["vista"]),
        ]
        bb = Blackboard(profile="motivational",
                        request={"duration_s": 20, "shots": 6}, segments=segs)
        d = NarrativeDirectorAgent()
        d.classify(bb, lambda *a, **k: None)
        d.run(bb, {"emit": lambda *a, **k: None})

        edl = bb.edl_history[-1]
        soundbites = [c for c in edl["timeline"] if c["role"] == "soundbite"]
        self.assertTrue(soundbites, "expected at least one soundbite entry")
        sb = soundbites[0]
        # the soundbite's audio comes from a different source than its visuals
        self.assertIsNotNone(sb["audio_from"])
        self.assertNotEqual(sb["audio_from"], sb["source"])
        self.assertTrue(any(p["audio_from"] == "sb1" for p in bb.pairings))

    def test_finale_is_hero(self):
        segs = [seg(f"b{i}", 0.85, 0.2, 0.0, ["wide"]) for i in range(5)]
        segs.append(seg("heroX", 0.95, 0.9, 0.3, ["summit", "triumph"]))
        bb = Blackboard(profile="motivational",
                        request={"duration_s": 18, "shots": 6}, segments=segs)
        d = NarrativeDirectorAgent()
        d.classify(bb, lambda *a, **k: None)
        d.run(bb, {"emit": lambda *a, **k: None})
        edl = bb.edl_history[-1]
        self.assertEqual(edl["timeline"][-1]["role"], "hero")


if __name__ == "__main__":
    unittest.main()
