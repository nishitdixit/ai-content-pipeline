import unittest

from content_pipeline.studio.agents.director import DEFAULT_THRESHOLDS, classify_roles
from content_pipeline.studio.memory.records import Segment


def seg(v, a, sp=0.0):
    return Segment(seg_id="x", asset_id="a", source_name="n", proxy_path="p",
                   in_s=0, out_s=3,
                   scores={"visual_quality": v, "audio_quality": a, "speech_value": sp})


class TestRoles(unittest.TestCase):
    def test_quadrants(self):
        th = DEFAULT_THRESHOLDS
        self.assertIn("hero", classify_roles(seg(0.9, 0.9), th))          # both strong
        self.assertIn("b_roll", classify_roles(seg(0.9, 0.2), th))        # great visual, bad audio
        self.assertIn("soundbite", classify_roles(seg(0.2, 0.1, sp=0.9), th))  # great speech, bad visual
        self.assertIn("discard", classify_roles(seg(0.2, 0.2), th))       # both weak

    def test_asymmetric_clips_are_not_lost(self):
        # the whole point: a 9/2 clip must be usable, not discarded
        roles = classify_roles(seg(0.9, 0.2), DEFAULT_THRESHOLDS)
        self.assertNotIn("discard", roles)
        self.assertIn("b_roll", roles)


if __name__ == "__main__":
    unittest.main()
