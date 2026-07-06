import unittest

from services.web_research import WebSearchResult, _filter_relevant_results, _parse_bing_rss, _parse_duckduckgo_html, _unique_results


class WebResearchTests(unittest.TestCase):
    def test_parse_bing_rss_results(self):
        xml = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0">
  <channel>
    <item>
      <title>法采产品公开资料</title>
      <link>https://example.com/facai-products</link>
      <description>公开页面提到烘焙产品信息。</description>
    </item>
    <item>
      <title>法采官方账号</title>
      <link>https://example.com/facai-social</link>
      <description>官方账号发布新品内容。</description>
    </item>
  </channel>
</rss>"""

        results = _parse_bing_rss(xml, max_results=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "法采产品公开资料")
        self.assertEqual(results[0].url, "https://example.com/facai-products")
        self.assertIn("烘焙产品", results[0].snippet)

    def test_unique_results_deduplicates_urls_and_titles(self):
        results = _unique_results(
            [
                *_parse_duckduckgo_html(
                    """
<div class="result">
  <a class="result__a" href="https://example.com/a">法采产品</a>
  <a class="result__snippet">烘焙资料</a>
</div>
""",
                    max_results=5,
                ),
                *_parse_bing_rss(
                    """
<rss><channel>
  <item><title>法采产品</title><link>https://example.com/a</link><description>重复资料</description></item>
  <item><title>法采新品</title><link>https://example.com/b</link><description>新品资料</description></item>
</channel></rss>
""",
                    max_results=5,
                ),
            ],
            max_results=5,
        )

        self.assertEqual([item.url for item in results], ["https://example.com/a", "https://example.com/b"])

    def test_filter_relevant_results_requires_facai_brand_match(self):
        results = _filter_relevant_results(
            [
                WebSearchResult(title="法（汉语文字）_百度百科", url="https://example.com/fa", snippet="法律、方法等含义。"),
                WebSearchResult(title="法采烘焙产品公开资料", url="https://example.com/facai", snippet="法采产品信息。"),
            ],
            query="法采产品",
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://example.com/facai")


if __name__ == "__main__":
    unittest.main()
