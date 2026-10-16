import tempfile
import unittest
from pathlib import Path

from content_pipeline.events import EventBus
from content_pipeline.studio.memory.ingest import ingest_dir
from content_pipeline.studio.memory.store import RecordStore
from content_pipeline.studio.skills import default_registry


def _silent_bus():
    return EventBus()


class TestIncremental(unittest.TestCase):
    def test_only_new_media_analyzed(self):
        with tempfile.TemporaryDirectory() as d:
            media = Path(d) / "media"; media.mkdir()
            proj = Path(d) / "proj"
            # two fake clips (bytes are enough for the hash + mock perception)
            (media / "ride_coast_wide.mp4").write_bytes(b"AAA" * 1000)
            (media / "rise_speech_line.mp4").write_bytes(b"BBB" * 1000)

            store = RecordStore(proj)
            skills = default_registry()
            r1 = ingest_dir(media, store, skills, _silent_bus())
            self.assertEqual(r1["new"], 2)
            self.assertEqual(r1["skipped"], 0)

            # add one more, re-ingest
            (media / "triumph_summit_hero.mp4").write_bytes(b"CCC" * 1000)
            store2 = RecordStore(proj)              # reload from disk
            r2 = ingest_dir(media, store2, skills, _silent_bus())
            self.assertEqual(r2["new"], 1)          # only the new clip
            self.assertEqual(r2["skipped"], 2)      # the two known ones
            self.assertEqual(store2.counts()["assets"], 3)
            self.assertEqual(store2.counts()["analyzed"], 3)


if __name__ == "__main__":
    unittest.main()
