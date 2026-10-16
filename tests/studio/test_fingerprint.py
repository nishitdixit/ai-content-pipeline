import tempfile
import unittest
from pathlib import Path

from content_pipeline.studio.memory.fingerprint import content_hash, perceptual_hash


class TestFingerprint(unittest.TestCase):
    def test_deterministic_and_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "a.bin"; a.write_bytes(b"hello world" * 100)
            b = Path(d) / "b.bin"; b.write_bytes(b"different bytes" * 100)
            self.assertEqual(content_hash(a), content_hash(a))   # stable
            self.assertNotEqual(content_hash(a), content_hash(b))
            self.assertTrue(content_hash(a).startswith("sha256:"))

    def test_dedup_same_content_same_hash(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "first.bin"; a.write_bytes(b"X" * 500)
            b = Path(d) / "copy.bin"; b.write_bytes(b"X" * 500)
            self.assertEqual(content_hash(a), content_hash(b))   # identity = bytes
            self.assertEqual(perceptual_hash(a), perceptual_hash(b))


if __name__ == "__main__":
    unittest.main()
