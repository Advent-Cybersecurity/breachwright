import os
import sys
import unittest
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.ad.parser import parse_sharphound_zip


class ActiveDirectoryParserTests(unittest.TestCase):
    def test_rejects_unsafe_zip_compression_ratio(self):
        output = BytesIO()
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("users.json", b"[" + (b" " * 1024 * 1024) + b"]")

        with self.assertRaisesRegex(ValueError, "unsafe compression ratio"):
            parse_sharphound_zip(output.getvalue())


if __name__ == "__main__":
    unittest.main()
