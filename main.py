# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 m0dyl

# ================= НАСТРОЙКИ =================

MAIN_LANGUAGE = "pl"  # Например: "pl", "ru", "uk".
ENGLISH_LANGUAGE = "en-US" # в теории сюда можно бахнуть любой другой язык для проверки если на сайте несколько языков


# если слово большими буквами, будет игнорироваться если с ошибкой 
# (для абривиатур и всяких там АДИДАС и тд... но если будет адидас то выдаст как несуществующее слово)
ALL_CAPITAL_LETTERS_IGNORE = True 


# если проверка не английского языка но есть английские слова на сайте, 
# не будет помечаться как ошибка
ENGLISH_IGNORE = True 


# Если на сайте есть '-' Дефис, а орфографически нужно '—' Тире
# то такое будет игнорироваться
# RULE_ID_IGNORE = ["DYWIZ",..] (pl) может отключить ошибки с дефисами
# но также будут игнорироваться слова с дефисо которые написаны неправильно
# а эта переменная отвечает чисто за Дефис -> Тире игнор
HYPHEN_DASH_IGNORE = True


# Не выводить замечания с указанными rule_id на всех страницах.
# Копируйте точный ID из отчета. Пустой список [] ничего не исключает.
# DYWIZ здесь не отключаем: для дефиса остается узкий фильтр выше.
RULE_ID_IGNORE = [
    # "AL_UJAZDOWSKIE",  # Example: ignore this rule on every page.
]


# 1a 2б в адресе будет игнорироваться, 
# бо программа думает чтоэто какаето нумирация типа 1. 2. 3. а написано 1а 2б ... ну как в адресах бывает
# то чтоб небыло ошибки = True
IGNORE_ADDRESS_NUMBER_WARNING = True 


# игнорирует начало предложения с маленькой буквы. сайты собираются из кусков тегов, 
# и то что на сайте может быть одним предложением в разных тегах, 
# в этом скрипте это могут быть разные предложения поэтому будет игнор ошибки что якобы начинается с маленькой
IGNORE_LOWERCASE_FRAGMENT_START = True 


SITE_URL = "https://example.com/"  # ссылка сайта на проверку на орфографию, будут найдены все все подстраницы


# Исключить раздел целиком: сам URL и все вложенные пути.
# Можно указать путь от корня сайта или полный URL того же хоста.
# /blog исключает /blog и /blog/..., но НЕ /blog-other.
# Параметры ?query и #якоря при сопоставлении не учитываются.
URL_IGNORE = [
    # "/blog",
    # "https://example.com/shop",
] # чтоб начало работать нужно убрать коментарий "#", и добавлять ссылки в кавычках через запятую

REQUEST_DELAY = 2.0  # секунд ожидания перед запросом на новую страницу, чтоб небыло ddos
MAX_PAGES = 500  # максимальное количество страниц которое обработает скрипт, чтоб не попасть в зацыкленность
REPORT_PATH = "grammar_report.json"

# Необязательный доступ, выданный владельцем сайта. None = не использовать.
# "env:ИМЯ" читает значение из переменной окружения: секрет не нужен в коде.
# Все эти настройки передаются только проверяемому хосту и только по HTTPS.
REQUEST_HEADERS = None
# REQUEST_HEADERS = {"Authorization": "env:SITE_AUTHORIZATION"}
# REQUEST_HEADERS = {
#     "CF-Access-Client-Id": "env:CF_ACCESS_CLIENT_ID",
#     "CF-Access-Client-Secret": "env:CF_ACCESS_CLIENT_SECRET",
# }

REQUEST_COOKIES = None
# REQUEST_COOKIES = {"sessionid": "env:SITE_SESSION_ID"}
# Имя cookie зависит от сайта; sessionid здесь только пример.

HTTP_BASIC_AUTH = None
# HTTP_BASIC_AUTH = ("env:SITE_USERNAME", "env:SITE_PASSWORD")
# Basic Auth не выполняет вход через HTML-форму.

# ==============================================

import json
import os
import posixpath
import re
import textwrap
import time
from collections import deque
from contextlib import ExitStack
from functools import lru_cache
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import requests
import language_tool_python
from bs4 import BeautifulSoup, NavigableString
from bs4.element import (
    Comment,
    Doctype,
    Declaration,
    ProcessingInstruction,
)


BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "button",
    "dd", "div", "dl", "dt", "fieldset", "figcaption", "figure",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hr", "li", "main", "nav", "ol", "p", "section",
    "table", "td", "th", "tr", "ul",
}

FILE_EXTENSIONS = re.compile(
    r"\.(?:jpg|jpeg|png|gif|webp|svg|ico|pdf|zip|rar|7z|"
    r"mp3|mp4|webm|woff2?|ttf|css|js|xml|json|docx?|xlsx?)$",
    re.IGNORECASE,
)

AMOUNT_LABEL = re.compile(
    r"\d+(?:[.,]\d+)?"
    r"(?:\s*[-–—/]\s*\d+(?:[.,]\d+)?)?"
    r"\s*(?:ml|cl|dl|l|mg|g|kg|zł|pln|eur|€|%|min|h)"
    r"\.?",
    re.IGNORECASE,
)

SINGLE_WORD = re.compile(
    r"[^\W\d_]+(?:[-'’][^\W\d_]+)*",
    re.UNICODE,
)

# Слова, включая названия с цифрами, дефисами и апострофами.
WORD_TOKEN = re.compile(
    r"(?<!\w)[^\W_]+(?:[-'’][^\W_]+)*(?!\w)",
    re.UNICODE,
)

# Узкое распознавание польского адреса:
# Al. Piastów 3/1a
# ul. Długa 12a
POLISH_ADDRESS = re.compile(
    r"\b(?:al\.|ul\.|pl\.|aleja\b|aleje\b|ulica\b|plac\b)"
    r"\s+[^,;\n]{1,80}?\s+"
    r"(?P<number>\d+[a-z]?(?:\s*/\s*\d+[a-z]?)?)"
    r"(?!\w)",
    re.IGNORECASE,
)


def language_base(language):
    return language.lower().replace("_", "-").split("-")[0]


def normalize_space(text):
    return re.sub(r"\s+", " ", text).strip()


def internal_url(raw_url, base_url, allowed_host):
    if not isinstance(raw_url, str) or not raw_url.strip():
        return None

    try:
        parts = urlsplit(urljoin(base_url, raw_url.strip()))

        if parts.scheme not in {"http", "https"}:
            return None

        if parts.hostname != allowed_host:
            return None

        if parts.username or parts.password:
            return None

        default_port = 443 if parts.scheme == "https" else 80
        if parts.port not in {None, default_port}:
            return None

        path = parts.path or "/"

        if FILE_EXTENSIONS.search(path):
            return None

        return urlunsplit((
            parts.scheme,
            allowed_host,
            path,
            parts.query,
            "",
        ))
    except ValueError:
        return None


class IgnoredUrlError(Exception):
    """Переход в исключенный раздел; это не ошибка сайта."""


def normalized_url_path(path):
    # Сравниваем Unicode и %-кодировку одинаково; убираем /./ и /../.
    decoded = unquote(path or "/")
    return posixpath.normpath("/" + decoded.lstrip("/"))


def build_ignored_url_roots(start_url, entries):
    site = urlsplit(start_url)
    site_root = urlunsplit((site.scheme, site.netloc, "/", "", ""))
    if isinstance(entries, (str, bytes)):
        raise ValueError("URL_IGNORE должен быть списком строк, а не строкой")
    roots = set()
    for entry in entries:
        if not isinstance(entry, str) or not entry.strip():
            raise ValueError("В URL_IGNORE допустимы только непустые строки")
        parts = urlsplit(urljoin(site_root, entry.strip()))
        default_port = 443 if parts.scheme == "https" else 80
        if (
            parts.scheme not in {"http", "https"}
            or parts.hostname != site.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.port not in {None, default_port}
        ):
            raise ValueError(f"URL_IGNORE: нужен путь или URL того же сайта: {entry!r}")
        roots.add((parts.hostname, normalized_url_path(parts.path)))
    return tuple(sorted(roots))


def is_ignored_url(url, roots):
    parts = urlsplit(url)
    path = normalized_url_path(parts.path)
    return any(
        parts.hostname == host
        and (root == "/" or path == root or path.startswith(root + "/"))
        for host, root in roots
    )


def extract_blocks(soup, main_language):
    """Получить блоки текста без HTML и склеивания соседних тегов."""
    main_base = language_base(main_language)

    for tag in list(soup.select(
        "script, style, template, noscript, svg, canvas, "
        "[hidden], [aria-hidden='true']"
    )):
        if tag.parent is not None:
            tag.decompose()

    blocks = []
    buffer = []
    buffer_lang = None

    def flush():
        nonlocal buffer_lang

        text = normalize_space(" ".join(buffer))
        text = re.sub(r"\s+([,.;:!?%)\]])", r"\1", text)
        text = re.sub(r"([(\[])\s+", r"\1", text)

        if text and any(char.isalpha() for char in text):
            blocks.append((buffer_lang, text))

        buffer.clear()
        buffer_lang = None

    def add_text(text, declared_language):
        nonlocal buffer_lang

        text = normalize_space(text)
        if not text:
            return

        if declared_language == main_base:
            check_language = main_language
        elif declared_language == "en":
            # При False даже lang="en" проверяется основным языком.
            check_language = (
                ENGLISH_LANGUAGE if ENGLISH_IGNORE else main_language
            )
        else:
            flush()
            return

        if buffer and buffer_lang != check_language:
            flush()

        buffer_lang = check_language
        buffer.append(text)

    def walk(node, inherited_lang):
        if isinstance(
            node,
            (Comment, Doctype, Declaration, ProcessingInstruction),
        ):
            return

        if isinstance(node, NavigableString):
            add_text(str(node), inherited_lang)
            return

        if node.name == "head":
            return

        language = inherited_lang
        if node.get("lang"):
            language = language_base(node["lang"])

        boundary = node.name in BLOCK_TAGS

        if node.name == "a" and node.find_parent(["nav", "menu"]):
            boundary = True

        if node.name == "span":
            label = normalize_space(node.get_text(" ", strip=True))
            if AMOUNT_LABEL.fullmatch(label):
                boundary = True

        if boundary:
            flush()

        if node.name == "input":
            if node.get("type", "").lower() in {
                "submit", "button", "reset"
            }:
                flush()
                add_text(node.get("value", ""), language)
                flush()

        for child in node.children:
            walk(child, language)

        if boundary:
            flush()

    walk(soup, main_base)
    flush()

    return list(dict.fromkeys(blocks))


def ignore_fragment_capitalization(match, text):
    return (
        IGNORE_LOWERCASE_FRAGMENT_START
        and match.rule_id == "UPPERCASE_SENTENCE_START"
        and not text[:match.offset].strip(
            " \t\n\"'«»“”‘’([{—–-"
        )
    )


def ignore_address_warning(match, text, language):
    if not (
        IGNORE_ADDRESS_NUMBER_WARNING
        and language_base(language) == "pl"
        and match.rule_id == "LICZEBNIKI"
    ):
        return False

    error_start = match.offset
    error_end = error_start + match.error_length

    for address in POLISH_ADDRESS.finditer(text):
        number = address.group("number")
        start, end = address.span("number")

        if (
            re.search(r"[a-z]", number, re.IGNORECASE)
            and start <= error_start < error_end <= end
        ):
            return True

    return False


def make_issue(match, text, language):
    return {
        "language": language,
        "word": text[match.offset:match.offset + match.error_length],
        "text": text,
        "offset": match.offset,
        "length": match.error_length,
        "rule_id": match.rule_id,
        "message": match.message,
        "replacements": match.replacements[:5],
    }


def ignore_hyphen_dash(match, text):
    if not HYPHEN_DASH_IGNORE:
        return False

    original = text[
        match.offset:match.offset + match.error_length
    ]

    if "-" not in original:
        return False

    def normalize(value):
        # Допускаем различия в пробелах вокруг тире.
        value = value.replace("—", "-").replace("–", "-")
        return re.sub(r"\s+", "", value)

    return any(
        ("—" in replacement or "–" in replacement)
        and normalize(original) == normalize(replacement)
        for replacement in match.replacements
    )


class ExplicitAuthOnly(requests.auth.AuthBase):
    """Не подменять явный Authorization учетными данными из .netrc."""

    def __call__(self, request):
        return request


class AccessBlockedError(Exception):
    def __init__(self, status_code, reason):
        super().__init__(reason)
        self.status_code = status_code
        self.reason = reason


def resolve_access_value(value):
    if not isinstance(value, str):
        raise ValueError("Значение настройки доступа должно быть строкой")
    if value.startswith("env:"):
        name = value[4:]
        if not name or not os.environ.get(name):
            raise ValueError("Не задана переменная окружения для настройки доступа")
        value = os.environ[name]
    if not value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Пустое значение или управляющий символ в настройке доступа")
    try:
        value.encode("latin-1")
    except UnicodeEncodeError:
        raise ValueError("Значение HTTP-настройки должно поддерживать latin-1") from None
    return value


def configure_request_access(session, start_url):
    """Настроить Session; вернуть только признаки включенных методов."""
    token_name = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")

    def read_mapping(mapping, kind):
        if mapping is None:
            return {}
        if not isinstance(mapping, dict):
            raise ValueError(f"{kind} должен быть словарем или None")
        result = {}
        for name, value in mapping.items():
            if not isinstance(name, str) or not token_name.fullmatch(name):
                raise ValueError(f"Некорректное имя в {kind}")
            if kind == "REQUEST_HEADERS" and name.lower() in {
                "host", "cookie", "content-length", "transfer-encoding",
                "connection", "proxy-authorization",
            }:
                raise ValueError("Служебный заголовок запрещен; cookie задаются через REQUEST_COOKIES")
            value = resolve_access_value(value)
            if value[0].isspace():
                raise ValueError("Значение HTTP-настройки не должно начинаться с пробела")
            if kind == "REQUEST_COOKIES" and any(char in value for char in ';,"\\ '):
                raise ValueError("Недопустимый символ в значении cookie")
            if kind == "REQUEST_HEADERS" and name.lower() in {key.lower() for key in result}:
                raise ValueError("Повтор имени HTTP-заголовка")
            result[name] = value
        return result

    headers = read_mapping(REQUEST_HEADERS, "REQUEST_HEADERS")
    cookies = read_mapping(REQUEST_COOKIES, "REQUEST_COOKIES")
    basic = None
    if HTTP_BASIC_AUTH is not None:
        if not isinstance(HTTP_BASIC_AUTH, (tuple, list)) or len(HTTP_BASIC_AUTH) != 2:
            raise ValueError("HTTP_BASIC_AUTH должен содержать пару логин/пароль или None")
        basic = tuple(resolve_access_value(value) for value in HTTP_BASIC_AUTH)
        if ":" in basic[0]:
            raise ValueError("Логин HTTP Basic Auth не должен содержать двоеточие")
        if any(name.lower() == "authorization" for name in headers):
            raise ValueError("Выберите HTTP_BASIC_AUTH или заголовок Authorization")

    enabled = bool(headers or cookies or basic)
    site = urlsplit(start_url)
    if enabled and site.scheme != "https":
        raise ValueError("С настройками доступа SITE_URL должен начинаться с https://")

    session.headers.update(headers)
    for name, value in cookies.items():
        session.cookies.set(name, value, domain=site.hostname, path="/", secure=True)
    if enabled:
        session.auth = requests.auth.HTTPBasicAuth(*basic) if basic else ExplicitAuthOnly()
    return {
        "custom_headers_enabled": bool(headers),
        "cookies_enabled": bool(cookies),
        "http_basic_auth_enabled": basic is not None,
    }


def check_website_grammar(
    url,
    lang=MAIN_LANGUAGE,
    delay=REQUEST_DELAY,
    max_pages=MAX_PAGES,
    report_path=REPORT_PATH,
    url_ignore=None,
):
    if delay < 0 or max_pages < 1:
        raise ValueError("delay должен быть >= 0, max_pages — >= 1")

    if (
        not isinstance(RULE_ID_IGNORE, (list, tuple))
        or any(not isinstance(rule, str) or not rule.strip() for rule in RULE_ID_IGNORE)
    ):
        raise ValueError("RULE_ID_IGNORE должен быть списком непустых строк")
    ignored_rule_ids = frozenset(rule.strip() for rule in RULE_ID_IGNORE)

    host = urlsplit(url).hostname
    start_url = internal_url(url, url, host)

    if not start_url:
        raise ValueError("Укажи адрес вида https://example.com/")

    ignored_entries = URL_IGNORE if url_ignore is None else url_ignore
    ignored_roots = build_ignored_url_roots(start_url, ignored_entries)
    if is_ignored_url(start_url, ignored_roots):
        raise ValueError("Стартовая страница входит в URL_IGNORE; обход не начат")

    queue = deque([start_url])
    discovered = {start_url}
    fetched = set()
    pages = []
    last_request = 0.0
    stop_reason = None

    def save_report():
        result = {
            "settings": {
                "site_url": start_url,
                "request_access": access_settings,
                "request_delay": delay,
                "max_pages": max_pages,
                "report_path": str(report_path),
                "main_language": lang,
                "url_ignore": list(ignored_entries),
                "english_language": (
                    ENGLISH_LANGUAGE if ENGLISH_IGNORE else None
                ),
                "english_ignore": ENGLISH_IGNORE,
                "hyphen_dash_ignore": HYPHEN_DASH_IGNORE,
                "rule_id_ignore": sorted(ignored_rule_ids),
                "ignore_lowercase_fragment_start": (
                    IGNORE_LOWERCASE_FRAGMENT_START
                ),
                "all_capital_letters_ignore": (
                    ALL_CAPITAL_LETTERS_IGNORE
                ),
                "ignore_address_number_warning": (
                    IGNORE_ADDRESS_NUMBER_WARNING
                ),
            },
            "stop_reason": stop_reason,
            "discovered_urls": sorted(discovered),
            "pending_urls": [
                link for link in queue if link not in fetched
            ],
            "pages": pages,
        }

        with open(report_path, "w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)

        return result

    with ExitStack() as stack:
        session = stack.enter_context(requests.Session())
        session.headers["User-Agent"] = "WebsiteGrammarChecker/1.0"
        access_settings = configure_request_access(session, start_url)
        access_enabled = any(access_settings.values())

        main_tool = stack.enter_context(
            language_tool_python.LanguageTool(lang)
        )
        tools = {lang: main_tool}

        # Если английский отключен — второй сервер не запускается.
        english_tool = None
        if ENGLISH_IGNORE:
            if ENGLISH_LANGUAGE == lang:
                english_tool = main_tool
            else:
                english_tool = stack.enter_context(
                    language_tool_python.LanguageTool(ENGLISH_LANGUAGE)
                )
            tools[ENGLISH_LANGUAGE] = english_tool

        @lru_cache(maxsize=10000)
        def spelling_matches(language, word):
            """Только орфография, без грамматики отдельного слова."""
            return tuple(
                match
                for match in tools[language].check(word)
                if match.rule_issue_type == "misspelling"
            )

        def accepted_as_english(word):
            if not ENGLISH_IGNORE or english_tool is None:
                return False

            if not SINGLE_WORD.fullmatch(word):
                return False

            # Не позволяем заглавной букве скрывать неизвестное слово.
            return not spelling_matches(
                ENGLISH_LANGUAGE, word.lower()
            )

        def check_text(text, language):
            checker = tools[language]
            issues = []

            uppercase_tokens = [
                token for token in WORD_TOKEN.finditer(text)
                if token.group().isupper()
            ]

            for match in checker.check(text):
                if match.rule_id in ignored_rule_ids:
                    continue

                if ignore_hyphen_dash(match, text):
                    continue

                if ignore_fragment_capitalization(match, text):
                    continue

                if ignore_address_warning(match, text, language):
                    continue

                start = match.offset
                end = start + match.error_length

                uppercase_token = next(
                    (
                        token for token in uppercase_tokens
                        if token.start() <= start < end <= token.end()
                    ),
                    None,
                )

                if uppercase_token is not None:
                    if ALL_CAPITAL_LETTERS_IGNORE:
                        continue

                    # При False орфографию заглавных слов проверяем
                    # отдельно ниже, чтобы не дублировать замечания.
                    if match.rule_issue_type == "misspelling":
                        continue

                issue = make_issue(match, text, language)

                if (
                    language_base(language) != "en"
                    and match.rule_issue_type == "misspelling"
                    and accepted_as_english(issue["word"])
                ):
                    continue

                issues.append(issue)

            if not ALL_CAPITAL_LETTERS_IGNORE:
                # Проверяем ЗАГЛАВНЫЕ слова в нижнем регистре
                # отдельным запросом только на орфографию.
                # Исходное предложение не меняем.
                for token in uppercase_tokens:
                    original_word = token.group()
                    checked_word = original_word.lower()

                    matches = spelling_matches(
                        language, checked_word
                    )
                    if not matches:
                        continue

                    if (
                        language_base(language) != "en"
                        and accepted_as_english(original_word)
                    ):
                        continue

                    for match in matches:
                        if match.rule_id in ignored_rule_ids:
                            continue
                        issues.append({
                            "language": language,
                            "word": original_word,
                            "text": text,
                            "offset": token.start(),
                            "length": len(original_word),
                            "rule_id": match.rule_id,
                            "message": match.message,
                            "replacements": match.replacements[:5],
                            "checked_as": checked_word,
                        })

            # Убираем одинаковые замечания в одном фрагменте.
            unique = {}
            for issue in issues:
                key = (
                    issue["offset"],
                    issue["length"],
                    issue["rule_id"],
                )
                unique.setdefault(key, issue)

            return list(unique.values())

        def download(page_url):
            nonlocal last_request, stop_reason

            for _ in range(10):
                # Не отправляем доступ на другой хост или при понижении до HTTP.
                target_parts = urlsplit(page_url)
                if access_enabled and (
                    target_parts.scheme != "https" or target_parts.hostname != host
                ):
                    raise RuntimeError("Передача настроек доступа разрешена только по HTTPS исходному хосту")
                # Проверяем ДО запроса, в том числе после перенаправления.
                if is_ignored_url(page_url, ignored_roots):
                    raise IgnoredUrlError(page_url)
                if page_url in fetched:
                    return None, page_url

                wait = delay - (time.monotonic() - last_request)
                if wait > 0:
                    time.sleep(wait)

                fetched.add(page_url)
                last_request = time.monotonic()

                response = session.get(
                    page_url,
                    timeout=(10, 30),
                    allow_redirects=False,
                )

                if response.headers.get("cf-mitigated", "").lower() == "challenge":
                    stop_reason = "cloudflare_challenge"
                    status = response.status_code
                    response.close()
                    raise AccessBlockedError(status, stop_reason)

                if response.status_code in {401, 403}:
                    stop_reason = f"http_{response.status_code}"
                    status = response.status_code
                    response.close()
                    raise AccessBlockedError(status, stop_reason)

                if response.status_code in {429, 503}:
                    stop_reason = f"server_{response.status_code}"
                    response.close()
                    raise RuntimeError(
                        "Сервер вернул 429/503. Обход остановлен. "
                        "Повтори позже с большей задержкой."
                    )

                if response.status_code in {301, 302, 303, 307, 308}:
                    target = internal_url(
                        response.headers.get("Location"),
                        page_url,
                        host,
                    )
                    response.close()

                    if not target:
                        raise RuntimeError(
                            "Внешнее или неподдерживаемое перенаправление"
                        )

                    page_url = target
                    continue

                try:
                    response.raise_for_status()
                except requests.RequestException:
                    response.close()
                    raise

                return response, page_url

            raise RuntimeError("Слишком много перенаправлений")

        try:
            while queue and len(pages) < max_pages:
                requested_url = queue.popleft()

                if requested_url in fetched:
                    continue

                print(f"\nЗагрузка: {requested_url}")

                entry = {
                    "url": requested_url,
                    "status": "pending",
                    "errors": [],
                }
                pages.append(entry)

                try:
                    response, page_url = download(requested_url)
                    entry["url"] = page_url

                    if response is None:
                        entry["status"] = "already_visited"
                        continue

                    with response:
                        content_type = response.headers.get(
                            "Content-Type", ""
                        ).lower()

                        if not any(kind in content_type for kind in (
                            "text/html", "application/xhtml+xml"
                        )):
                            entry["status"] = "not_html"
                            continue

                        soup = BeautifulSoup(
                            response.content, "html.parser"
                        )

                    base_tag = soup.find("base", href=True)
                    base_url = (
                        urljoin(page_url, base_tag["href"])
                        if base_tag else page_url
                    )

                    # Сначала собираем ссылки, потом очищаем HTML.
                    for tag in soup.select(
                        "a[href], iframe[src], frame[src]"
                    ):
                        attribute = (
                            "href" if tag.name == "a" else "src"
                        )
                        link = internal_url(
                            tag.get(attribute), base_url, host
                        )

                        if (
                            link
                            and link not in discovered
                            and not is_ignored_url(link, ignored_roots)
                        ):
                            discovered.add(link)
                            queue.append(link)

                    for language, block in extract_blocks(soup, lang):
                        chunks = textwrap.wrap(
                            block,
                            width=4000,
                            break_long_words=False,
                            break_on_hyphens=False,
                        )

                        for text in chunks:
                            entry["errors"].extend(
                                check_text(text, language)
                            )

                    entry["status"] = "checked"
                    print(
                        f"Найдено замечаний: {len(entry['errors'])}"
                    )

                    for issue in entry["errors"]:
                        print(
                            f"  [{issue['language']}] "
                            f"{issue['word']!r}: {issue['message']}"
                        )
                        print(f"  Текст: {issue['text']}")

                        if issue["replacements"]:
                            print(
                                "  Варианты: "
                                + ", ".join(issue["replacements"])
                            )

                except AccessBlockedError as error:
                    entry["status"] = "blocked"
                    entry["http_status"] = error.status_code
                    entry["message"] = error.reason
                    print(f"Доступ не получен: {error.reason}. Обход остановлен.")

                except IgnoredUrlError as error:
                    entry["status"] = "ignored"
                    entry["redirect_target"] = str(error)
                    print(f"Пропущен исключенный раздел: {error}")

                except Exception as error:
                    entry["status"] = "error"
                    entry["message"] = str(error)
                    print(f"Не удалось проверить: {error}")

                finally:
                    save_report()

                if stop_reason:
                    break

            if (
                not stop_reason
                and len(pages) >= max_pages
                and any(link not in fetched for link in queue)
            ):
                stop_reason = "max_pages"

        except KeyboardInterrupt:
            stop_reason = "interrupted"
            if pages and pages[-1]["status"] == "pending":
                pages[-1]["status"] = "interrupted"
            print("\nОстановлено пользователем. Сохраняю отчет.")

        finally:
            result = save_report()

    print(f"\nОтчет сохранен: {report_path}")

    if stop_reason:
        print(f"Причина остановки: {stop_reason}")

    if result["pending_urls"]:
        print(
            "Не обработано адресов: "
            f"{len(result['pending_urls'])}"
        )

    return result


if __name__ == "__main__":
    check_website_grammar(
        SITE_URL,
        lang=MAIN_LANGUAGE,
        delay=REQUEST_DELAY,
        max_pages=MAX_PAGES,
        report_path=REPORT_PATH,
    )