"""Index public RSS article mentions; retain prior matches when feed is unavailable."""
import json, re, unicodedata, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from email.utils import parsedate_to_datetime
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/related-articles.json'
def normalize(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.findall(r'[a-z0-9]+', text))
def contains(text, name):
    # Whole full names only; suffixes may be omitted by the author.
    name = re.sub(r'\s+(jr|sr|ii|iii|iv)$', '', normalize(name))
    return (' ' + name + ' ') in (' ' + normalize(text) + ' ')
def refresh():
    old = json.loads(DEST.read_text()) if DEST.exists() else []
    request = urllib.request.Request('https://rosterxreport.substack.com/feed', headers={'User-Agent': 'RosterReport-ArticleIndexer/1.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        feed = ET.fromstring(response.read(5_000_000))
    items = feed.findall('./channel/item')
    if not items:
        raise ValueError('No RSS items; preserving prior index')
    profiles = json.loads((ROOT / 'data/player-profiles.json').read_text())['profiles']
    articles = {a['url']: a for a in old}
    for item in items:
        url = item.findtext('link', '').split('?')[0]
        if not url.startswith('https://rosterxreport.substack.com/p/'):
            continue
        body = item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded') or item.findtext('description', '')
        import html
        headings = ' '.join(re.findall(r'<h[1-6][^>]*>(.*?)</h[1-6]>', body, re.S | re.I))
        clean = lambda s: html.unescape(re.sub('<[^>]+>', ' ', s))
        title = item.findtext('title', '')
        matches = {}
        for p in profiles:
            if contains(clean(title + ' ' + headings), p['name']):
                matches[p['name']] = 'featured'
            elif contains(clean(body), p['name']):
                matches[p['name']] = 'mentioned'
        if matches:
            articles[url] = {'title': title, 'url': url, 'date': parsedate_to_datetime(item.findtext('pubDate')).date().isoformat(), 'players': matches}
    DEST.write_text(json.dumps(sorted(articles.values(), key=lambda a:a['date'], reverse=True), indent=2) + '\n')
if __name__ == '__main__':
    refresh()
