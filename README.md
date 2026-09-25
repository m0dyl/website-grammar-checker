# Website Grammar Checker

**Find spelling and grammar issues across a website, with filters for real-world web content.**

A configurable Python crawler built with Requests, BeautifulSoup and a local LanguageTool server. Originally built for a small Polish salon website, it checks linked internal pages and writes a JSON report with the page URL, text context and suggested corrections.

[Русская инструкция](README.ru.md) · [Authentication](AUTHENTICATION.md) · [Example report](examples/report.example.json)

## What it does

- Follows same-host links and iframe sources using a breadth-first queue.
- Adds a configurable delay between requests and limits the number of processed pages.
- Excludes entire URL sections before requesting them, including redirect targets.
- Extracts text while separating blocks, buttons and price/volume labels.
- Checks a primary language such as Polish, Russian or Ukrainian.
- Optionally accepts English words that trigger a primary-language spelling warning.
- Filters uppercase words, selected rule IDs and specific dash/capitalization warnings.
- Supports optional HTTP headers, session cookies and HTTP Basic Auth.
- Saves a report after every processed page, including failures and blocked requests.

## Requirements

- **Python 3.10+** for the pinned dependencies.
- **Java 17+** available on PATH for the local LanguageTool server.
- Internet access to retrieve website pages and download LanguageTool on first use.

The Python tests were run locally on Windows with Python 3.15.0rc2. They exercise the crawler with simulated responses; they do not certify every Python version or protected website.

## Quick start

Download the repository and open a terminal in its directory.

### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
java -version
```

If Java is missing, install Java 17 or newer. For example:

```powershell
winget install --id EclipseAdoptium.Temurin.21.JDK --exact
```

Restart the terminal (and your editor if using its integrated terminal), then check `java -version` again.

Edit the settings at the top of `main.py`:

```python
SITE_URL = "https://example.com/"
MAIN_LANGUAGE = "pl"
REQUEST_DELAY = 2.0
MAX_PAGES = 500
URL_IGNORE = ["/blog", "/shop/archive"]
```

Run:

```powershell
.\venv\Scripts\python.exe main.py
```

The default output is `grammar_report.json` in the current working directory. The first run may take longer while LanguageTool is downloaded and started.

### macOS / Linux

With Python 3.10+ and Java 17+ installed:

```bash
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
# Edit SITE_URL and other settings in main.py.
venv/bin/python main.py
```

These commands are provided for convenience; this project has been tested locally on Windows.

## Settings

Python booleans are `True` and `False`; use `None` to disable optional access settings.

| Setting | Purpose |
| --- | --- |
| `SITE_URL` | Start URL. Use the final hostname, including `www` if required. |
| `MAIN_LANGUAGE` | Main LanguageTool language, e.g. `pl`, `ru`, `uk`. |
| `ENGLISH_LANGUAGE` | English variant used for fallback, default `en-US`. |
| `ENGLISH_IGNORE` | Suppress main-language **spelling** warnings for words accepted by English spelling checks. |
| `ALL_CAPITAL_LETTERS_IGNORE` | Ignore warnings confined to uppercase tokens. With `False`, also check lowercase copies for spelling. |
| `HYPHEN_DASH_IGNORE` | Ignore replacements differing only by hyphen-to-dash changes and whitespace. |
| `RULE_ID_IGNORE` | Exact rule IDs omitted from the report across all pages. |
| `IGNORE_ADDRESS_NUMBER_WARNING` | Suppress `LICZEBNIKI` for lettered numbers in recognized Polish street addresses. |
| `IGNORE_LOWERCASE_FRAGMENT_START` | Suppress `UPPERCASE_SENTENCE_START` at the start of extracted fragments. |
| `URL_IGNORE` | Skip listed paths and all their descendants. |
| `REQUEST_DELAY` | Minimum interval in seconds between HTTP request starts. |
| `MAX_PAGES` | Maximum number of page records processed; redirects can add requests. |
| `REPORT_PATH` | Destination JSON file; create its parent directory first. |
| `REQUEST_HEADERS` | Optional headers, such as an owner-issued authorization token. |
| `REQUEST_COOKIES` | Optional session cookies. |
| `HTTP_BASIC_AUTH` | Optional `(username, password)` pair for HTTP Basic Auth. |

The default language is Polish, the start URL is `https://example.com/`, and `RULE_ID_IGNORE` is empty. Set your own URL and review the filters before running a check.

### Exclude sections

Both forms work:

```python
URL_IGNORE = [
    "/blog",
    "https://example.com/services/archive",
]
```

`/blog` excludes `/blog`, `/blog/` and `/blog/article/details`, but not `/blog-other` or `/services/blog`. Paths are case-sensitive; query strings and fragments do not affect matching. Encoded paths are decoded and dot segments are normalized for comparison. An ignored start page is rejected before crawling.

## Understanding the report

Each page record has a `status`, and checked pages contain `errors` with context, rule IDs and suggestions. The top-level `settings` records the run configuration. `pending_urls` lists queued URLs left when processing stopped.

The [example report](examples/report.example.json) is synthetic and only illustrates the format; it is not a scan of a real site.

A `checked` page means its extracted text was processed, not that the page is guaranteed error-free. An `error`, `blocked` or `interrupted` page was not fully checked. Unknown English insertions, brands and fragmented HTML can still produce false positives. Repeated footer findings currently remain on each affected page.

## Private pages

See [AUTHENTICATION.md](AUTHENTICATION.md) for Bearer tokens, API keys, cookies, Basic Auth and Cloudflare Access service tokens. Use the supported `env:VARIABLE_NAME` syntax to avoid putting secrets in committed source files.

Configured access credentials are sent only over HTTPS to the starting hostname. Access configuration values are omitted from report settings, but reports may contain text from private pages.

## Current limits

- Reads server-returned HTML; does not execute JavaScript, click buttons or render CSS visibility.
- Does not discover orphan pages, crawl sitemaps, process inline iframe `srcdoc`, or read image/PDF text.
- `www.example.com` and `example.com` are different hosts. External redirects are rejected.
- English fallback checks word spelling, not bilingual grammar or automatic sentence-language detection. Other-language HTML blocks can be skipped.
- Does not solve CAPTCHA, log in through forms or refresh expired credentials. A normal login page returned with HTTP 200 may be treated as content.
- Stops on 401/403, 429/503 or a recognized Cloudflare challenge. A delay does not guarantee access or suitable load for every site.
- Does not currently interpret `robots.txt`. Check the site's crawling policy and use an appropriate delay and page limit.
- Does not automatically modify or correct the website.

## Tests

```powershell
.\venv\Scripts\python.exe -B -m unittest discover -v
```

The tests use fake LanguageTool results and offline HTTP responses, including real Requests request preparation. No Java server, live crawling or real credentials are required for the tests. They cover URL exclusions, redirect handling, rule filters and optional request authentication.

## Contributing

For a bug report, include the Python/dependency versions, relevant non-secret settings, a minimal HTML example, and the expected versus actual result. For a grammar false positive, include its `rule_id` and a short text fragment. Do not attach private session cookies, tokens or an entire private-site report.

## License

Copyright (C) 2026 m0dyl. Licensed under the GNU General Public License, version 3 only (`GPL-3.0-only`); see [LICENSE](LICENSE). Dependencies retain their respective licenses. This project uses `language_tool_python`, which declares `GPL-3.0-only`.
