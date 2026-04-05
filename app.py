import re
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}

_cache = {}


def normalize_base_url(url):
    url = url.rstrip("/")
    url = re.sub(r"/p=\d+", "", url)
    url = re.sub(r"/tp=\d+", "", url)
    return url.rstrip("/")


def build_page_url(base_url, page):
    if page == 1:
        return base_url + "/"
    return f"{base_url}/p={page}/tp=1/"


def get_last_page(soup):
    pages = []
    for a in soup.select("a[href*='/p=']"):
        m = re.search(r"/p=(\d+)/", a["href"])
        if m:
            pages.append(int(m.group(1)))
    return max(pages) if pages else 1


def get_title(soup):
    if soup.title:
        t = soup.title.get_text(strip=True)
        t = re.split(r"\s*[-－]\s*", t)[0]
        return t
    return "スレッド"


def parse_posts(soup):
    posts = []
    for dt in soup.find_all("dt"):
        wrap = dt.find("div", class_="res_meta_wrap")
        if not wrap:
            continue

        num_el = wrap.find("span", class_="resnumb")
        num = num_el.get_text(strip=True) if num_el else ""

        time_el = wrap.find("span", itemprop="commentTime")
        timestamp = time_el.get_text(strip=True) if time_el else ""

        body_html = ""
        for sib in dt.next_siblings:
            sib_name = getattr(sib, "name", None)
            if sib_name == "dd":
                resbody = sib.find("div", class_="resbody")
                if resbody:
                    body_html = resbody.decode_contents()
                break
            if sib_name == "dt":
                break

        num_int = int(re.sub(r"\D", "", num)) if re.search(r"\d", num) else 0
        if num and num_int > 0:
            posts.append({
                "num": num,
                "num_int": num_int,
                "timestamp": timestamp,
                "body_html": body_html,
            })
    return posts


def scrape_thread(url):
    base_url = normalize_base_url(url)

    if base_url in _cache:
        return _cache[base_url]["title"], _cache[base_url]["pages"], _cache[base_url]["posts"]

    r = requests.get(build_page_url(base_url, 1), headers=HEADERS, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    title = get_title(soup)
    last_page = get_last_page(soup)
    all_posts = parse_posts(soup)

    for page in range(2, last_page + 1):
        time.sleep(1.5)
        r = requests.get(build_page_url(base_url, page), headers=HEADERS, timeout=15)
        r.raise_for_status()
        s = BeautifulSoup(r.text, "html.parser")
        all_posts.extend(parse_posts(s))

    seen = set()
    unique = []
    for p in sorted(all_posts, key=lambda x: x["num_int"]):
        if p["num_int"] not in seen:
            seen.add(p["num_int"])
            unique.append(p)

    _cache[base_url] = {"title": title, "pages": last_page, "posts": unique}
    return title, last_page, unique


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url", "").strip()
        if url:
            return render_template("loading.html", url=url)
    return render_template("index.html")


@app.route("/fetch")
def fetch():
    url = request.args.get("url", "").strip()
    if not url:
        return render_template("index.html", error="URLを入力してください")
    try:
        title, last_page, posts = scrape_thread(url)
        return render_template("thread.html", title=title, posts=posts,
                               total=len(posts), pages=last_page, url=url)
    except Exception as e:
        return render_template("index.html", error=f"エラー: {e}")


if __name__ == "__main__":
    app.run(debug=True, port=5050)
