import unittest

from content_pipeline.studio.memory.index import MemoryIndex
from content_pipeline.studio.memory.records import Segment
from content_pipeline.studio.retrieval import retrieve
from content_pipeline.studio.skills.perception import EmbedSkill

_embed = EmbedSkill()


def seg(sid, tags, emo, v=0.7):
    return Segment(seg_id=sid, asset_id=sid, source_name=sid, proxy_path=sid,
                   in_s=0, out_s=3,
                   scores={"visual_quality": v, "audio_quality": 0.4,
                           "speech_value": 0.1, "emotion": emo},
                   tags=tags, embedding=_embed.run(tags=tags)["embedding"])


class TestRetrieval(unittest.TestCase):
    def test_themed_segments_rank_first(self):
        segs = [
            seg("on1", ["motivational", "triumph", "summit"], 0.9),
            seg("on2", ["climb", "grind", "rise"], 0.85),
            seg("off1", ["grocery", "parking", "receipt"], 0.2),
            seg("off2", ["weather", "umbrella"], 0.2),
        ]
        idx = MemoryIndex(segs)
        req = {"theme": "motivational", "raw": "motivational short build to a peak"}
        weights = {"semantic": 0.4, "emotion": 0.3, "usable": 0.15, "visual": 0.15}
        ranked = retrieve(idx, req, weights)
        top_ids = [c.segment.seg_id for c in ranked[:2]]
        self.assertIn("on1", top_ids)
        self.assertTrue(ranked[0].total >= ranked[-1].total)
        # an on-theme clip should outrank an off-theme one
        d = {c.segment.seg_id: c.total for c in ranked}
        self.assertGreater(d["on1"], d["off1"])


if __name__ == "__main__":
    unittest.main()
