"""Static-site checks using only the Python standard library.

Run from anywhere:  python3 -I tests/test_site.py
Covers: titles/descriptions, single h1 and heading order, <main> landmark,
canonical URLs, sitemap <-> pages, JSON-LD validity, internal links/anchors/
assets, legacy redirect stubs, robots.txt policy snapshot, llms.txt links.
No network access.
"""
import json
import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://mark.balakrishnan.sg"
SM_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")

# robots.txt policy snapshot: change this deliberately, never as a side effect.
EXPECTED_ROBOTS = "User-agent: *\nAllow: /\n\nSitemap: https://mark.balakrishnan.sg/sitemap.xml\n"


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta, self.links, self.hrefs, self.srcs = {}, [], [], []
        self.headings, self.ids, self.jsonld = [], set(), []
        self.mains = 0
        self._cur = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "main":
            self.mains += 1
        elif tag == "meta":
            key = a.get("name") or a.get("property") or a.get("http-equiv")
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "link":
            self.links.append(a)
        elif tag == "a" and "href" in a:
            self.hrefs.append(a["href"])
        elif tag in ("img", "source", "script", "video") and (a.get("src") or a.get("poster")):
            self.srcs.extend(v for v in (a.get("src"), a.get("poster")) if v)
        if tag == "title" or re.fullmatch(r"h[1-6]", tag):
            self._cur, self._buf = tag, []
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._cur, self._buf = "ld", []

    def handle_data(self, data):
        if self._cur:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if self._cur is None:
            return
        text = "".join(self._buf).strip()
        if self._cur == "ld" and tag == "script":
            self.jsonld.append(text)
        elif self._cur == tag == "title":
            self.title = text
        elif self._cur == tag:
            self.headings.append((int(tag[1]), " ".join(text.split())))
        else:
            return
        self._cur = None

    def canonical(self):
        for l in self.links:
            if l.get("rel") == "canonical":
                return l.get("href")


def load(path):
    p = Page()
    p.feed(path.read_text(encoding="utf-8"))
    return p


PAGES = {f: load(f) for f in sorted([ROOT / "index.html", *(ROOT / "projects").glob("*.html")])}
ALL_HTML = {f: load(f) for f in sorted([*ROOT.glob("*.html"), *(ROOT / "projects").glob("*.html")])}
STUBS = {f: p for f, p in ALL_HTML.items() if f.parent == ROOT and f.name != "index.html"}


def expected_canonical(f):
    rel = f.relative_to(ROOT).as_posix()
    return SITE + "/" if rel == "index.html" else f"{SITE}/{rel}"


def resolve(from_file, href):
    """Map an internal href to (path, fragment) or None if external/non-file."""
    u = urlparse(href)
    if u.scheme in ("mailto", "tel", "javascript", "data"):
        return None
    if u.scheme or u.netloc:
        if f"{u.scheme}://{u.netloc}" != SITE:
            return None
        base = ROOT / unquote(u.path.lstrip("/"))
    elif u.path:
        base = (from_file.parent / unquote(u.path)).resolve()
    else:
        base = from_file
    if base.is_dir() or str(base).endswith("/") or u.path in ("", "/"):
        base = (base if base.is_dir() else ROOT) / "index.html" if u.path else base
    return base, u.fragment


class TestPages(unittest.TestCase):
    def test_title_description_lang(self):
        for f, p in PAGES.items():
            with self.subTest(f=f.name):
                self.assertTrue(p.title, "missing <title>")
                self.assertTrue(p.meta.get("description", "").strip(), "missing description")
                self.assertIn('<html lang="en">', f.read_text(encoding="utf-8"))

    def test_headings(self):
        for f, p in PAGES.items():
            with self.subTest(f=f.name):
                levels = [l for l, _ in p.headings]
                self.assertEqual(levels.count(1), 1, f"expected one h1, got {p.headings}")
                self.assertEqual(levels[0], 1)
                for prev, cur in zip(levels, levels[1:]):
                    self.assertLessEqual(cur, prev + 1, f"heading level skipped: {p.headings}")
                self.assertTrue(all(t for _, t in p.headings), "empty heading")

    def test_main_landmark(self):
        for f, p in PAGES.items():
            with self.subTest(f=f.name):
                self.assertEqual(p.mains, 1)
                self.assertIn("main", p.ids)

    def test_canonical(self):
        seen = set()
        for f, p in PAGES.items():
            with self.subTest(f=f.name):
                c = p.canonical()
                self.assertEqual(c, expected_canonical(f))
                self.assertEqual(p.meta.get("og:url"), c)
                self.assertNotIn("noindex", p.meta.get("robots", ""))
                self.assertNotIn(c, seen)
                seen.add(c)

    def test_legacy_stubs(self):
        for f, p in STUBS.items():
            with self.subTest(f=f.name):
                self.assertIn("noindex", p.meta.get("robots", ""))
                target = p.canonical()
                self.assertTrue(target and target.startswith(SITE + "/projects/"))
                self.assertTrue((ROOT / target[len(SITE) + 1:]).is_file(), target)


class TestSitemap(unittest.TestCase):
    def setUp(self):
        tree = ElementTree.parse(ROOT / "sitemap.xml")
        self.urls = {
            u.find("sm:loc", SM_NS).text: u.find("sm:lastmod", SM_NS).text
            for u in tree.getroot().findall("sm:url", SM_NS)
        }

    def test_matches_indexable_pages(self):
        self.assertEqual(set(self.urls), {expected_canonical(f) for f in PAGES})

    def test_lastmod_format(self):
        for loc, lm in self.urls.items():
            with self.subTest(loc=loc):
                self.assertRegex(lm, r"^\d{4}-\d{2}-\d{2}$")

    def test_stubs_excluded(self):
        for f, p in STUBS.items():
            self.assertNotIn(SITE + "/" + f.name, self.urls)


class TestStructuredData(unittest.TestCase):
    def graph(self, p):
        self.assertEqual(len(p.jsonld), 1, "expected exactly one JSON-LD block")
        data = json.loads(p.jsonld[0])  # raises if invalid
        self.assertEqual(data["@context"], "https://schema.org")
        return data["@graph"]

    def test_index_graph(self):
        g = self.graph(PAGES[ROOT / "index.html"])
        by_type = {n["@type"]: n for n in g}
        self.assertEqual(set(by_type), {"Person", "WebSite", "ItemList"})
        listed = [i["url"] for i in by_type["ItemList"]["itemListElement"]]
        self.assertEqual(
            sorted(listed),
            sorted(expected_canonical(f) for f in PAGES if f.name != "index.html"),
        )

    def test_article_graphs(self):
        for f, p in PAGES.items():
            if f.name == "index.html":
                continue
            with self.subTest(f=f.name):
                g = {n["@type"]: n for n in self.graph(p)}
                art, crumbs = g["TechArticle"], g["BreadcrumbList"]
                url = expected_canonical(f)
                self.assertEqual(art["mainEntityOfPage"]["@id"], url)
                self.assertRegex(art["datePublished"], DATE_RE)
                self.assertEqual(art["author"]["@id"], SITE + "/#mark")
                self.assertEqual(art["isPartOf"]["@id"], SITE + "/#website")
                items = crumbs["itemListElement"]
                self.assertEqual([i["position"] for i in items], list(range(1, len(items) + 1)))
                self.assertEqual(items[-1]["item"], url)
                # image must be a local file on this site
                img = art["image"]
                self.assertTrue(img.startswith(SITE + "/"))
                self.assertTrue((ROOT / unquote(img[len(SITE) + 1:])).is_file(), img)


class TestLinks(unittest.TestCase):
    def test_internal_links_anchors_assets(self):
        for f, p in ALL_HTML.items():
            for href in p.hrefs + p.srcs:
                r = resolve(f, href)
                if r is None:
                    continue
                path, frag = r
                with self.subTest(f=f.name, href=href):
                    self.assertTrue(path.is_file(), f"missing target {path}")
                    if frag and path.suffix == ".html":
                        self.assertIn(frag, ALL_HTML[path].ids)

    def test_target_blank_has_noopener(self):
        for f in ALL_HTML:
            for tag in re.findall(r"<a\b[^>]*>", f.read_text(encoding="utf-8")):
                if 'target="_blank"' in tag:
                    with self.subTest(f=f.name, tag=tag[:60]):
                        self.assertIn("noopener", tag)


class TestRobotsAndLlms(unittest.TestCase):
    def test_robots_policy_unchanged(self):
        self.assertEqual((ROOT / "robots.txt").read_text(encoding="utf-8"), EXPECTED_ROBOTS,
                         "robots.txt changed: confirm this is an intentional policy change")

    def test_llms_txt(self):
        text = (ROOT / "llms.txt").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# "))
        self.assertIn("nonstandard", text)
        self.assertIn("optional", text)
        self.assertIn("not guaranteed", text)
        self.assertNotIn("no effect on search ranking", text)
        for url in re.findall(r"\]\((https://[^)]+)\)", text):
            if url.startswith(SITE):
                path = urlparse(url).path
                target = ROOT / (path.lstrip("/") or "index.html")
                with self.subTest(url=url):
                    self.assertTrue(target.is_file(), url)
        # every project page is listed
        for f in PAGES:
            if f.name != "index.html":
                self.assertIn(expected_canonical(f), text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
