import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.gap_detection.service import analyze_gaps
from app.narrative.service import generate_engagement_narrative


class AIInputLimitTests(unittest.TestCase):
    def test_coverage_limit_rejects_before_provider_initialization(self):
        engagement_result = Mock()
        engagement_result.scalar_one_or_none.return_value = SimpleNamespace(id="eng-1")
        count_result = Mock()
        count_result.scalar_one.return_value = 501
        db = AsyncMock()
        db.execute.side_effect = [engagement_result, count_result]

        with patch("app.gap_detection.service.get_provider") as get_provider:
            result = asyncio.run(analyze_gaps(db, "eng-1", "ptes"))

        self.assertIn("supports up to 500 findings", result["error"])
        get_provider.assert_not_called()
        self.assertEqual(db.execute.await_count, 2)

    def test_narrative_limit_rejects_before_provider_initialization(self):
        engagement_result = Mock()
        engagement_result.scalar_one_or_none.return_value = SimpleNamespace(id="eng-1")
        findings_result = Mock()
        findings_result.scalars.return_value.all.return_value = [object()] * 501
        db = AsyncMock()
        db.execute.side_effect = [engagement_result, findings_result]

        with patch("app.narrative.service.get_provider") as get_provider:
            result = asyncio.run(generate_engagement_narrative(db, "eng-1"))

        self.assertIn("supports up to 500 findings", result["error"])
        get_provider.assert_not_called()
        self.assertEqual(db.execute.await_count, 2)


if __name__ == "__main__":
    unittest.main()
