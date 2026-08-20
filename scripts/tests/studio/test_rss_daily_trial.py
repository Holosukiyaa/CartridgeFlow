import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from core.studio.rss_daily_trial import parse_feed_xml

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<title>AI</title>
<item><title>First model release</title><link>https://example.com/a</link><description>A public note.</description><pubDate>Wed, 20 Aug 2026 10:00:00 GMT</pubDate></item>
<item><title>Second briefing</title><link>https://example.com/b</link><description>Another note.</description></item>
</channel></rss>"""


class RssDailyTrialTests(unittest.TestCase):
    def test_parse_rss_items(self):
        items = parse_feed_xml(RSS, source_name="Example", source_url="https://example.com/rss")
        self.assertEqual(2, len(items))
        self.assertEqual("First model release", items[0]["title"])
        self.assertEqual("https://example.com/a", items[0]["link"])
        self.assertEqual("Example", items[0]["source"])


if __name__ == "__main__":
    unittest.main()

