import unittest

from ui.url_utils import URLInputError, resolve_address_input


class ResolveAddressInputTests(unittest.TestCase):
    def setUp(self):
        self.search_engine = "https://search.example/find?q="

    def test_explicit_web_urls_are_preserved(self):
        self.assertEqual(
            resolve_address_input("http://example.com:8080/path?q=one", self.search_engine),
            "http://example.com:8080/path?q=one",
        )
        self.assertEqual(
            resolve_address_input("HTTPS://example.com/path", self.search_engine),
            "https://example.com/path",
        )

    def test_hostnames_and_addresses(self):
        cases = {
            "localhost": "https://localhost",
            "localhost:8000/dev": "https://localhost:8000/dev",
            "example.org/path": "https://example.org/path",
            "127.0.0.1:3000": "https://127.0.0.1:3000",
            "[::1]:8080": "https://[::1]:8080",
            "2001:db8::1": "https://[2001:db8::1]",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(resolve_address_input(value, self.search_engine), expected)

    def test_search_phrases_are_encoded(self):
        self.assertEqual(
            resolve_address_input("two words & more", self.search_engine),
            "https://search.example/find?q=two+words+%26+more",
        )
        self.assertEqual(
            resolve_address_input("python: typing", self.search_engine),
            "https://search.example/find?q=python%3A+typing",
        )

    def test_search_engine_fragment_is_preserved(self):
        self.assertEqual(
            resolve_address_input("hello", "https://search.example/find#top"),
            "https://search.example/find?q=hello#top",
        )

    def test_about_blank_is_supported(self):
        self.assertEqual(resolve_address_input("about:blank", self.search_engine), "about:blank")

    def test_unsupported_and_malformed_urls_are_rejected(self):
        rejected = (
            "javascript:alert(1)",
            "data:text/html,hello",
            "file:///etc/passwd",
            "ftp://example.org/file",
            "https://",
            "http://999.999.999.999",
            "http://example.org:99999",
            "https://user:pass@example.com",
            "custom:scheme",
        )
        for value in rejected:
            with self.subTest(value=value), self.assertRaises(URLInputError):
                resolve_address_input(value, self.search_engine)


if __name__ == "__main__":
    unittest.main()
