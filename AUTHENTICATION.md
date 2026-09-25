# Необязательный доступ к закрытым страницам

В `main.py` доступны три настройки. По умолчанию все равны `None`:

```python
REQUEST_HEADERS = None
REQUEST_COOKIES = None
HTTP_BASIC_AUTH = None
```

Настройки используются в `requests.Session` для загрузки HTML. Они не относятся к локальному серверу LanguageTool. Для доступа укажите HTTPS-адрес сайта; передача настроек на другой хост или через HTTP запрещена, в том числе при перенаправлении. Обычные сайты без этих настроек по-прежнему можно читать по HTTP.

## Где хранить секреты

В значениях словарей и пары Basic Auth поддерживается `env:ИМЯ_ПЕРЕМЕННОЙ`. Скрипт прочитает значение из окружения при запуске. Если переменная отсутствует или пуста, он остановится с ошибкой настройки. Значения настроек доступа не включаются в `settings` JSON-отчета: сохраняются только признаки включенных методов.

Можно передавать и обычные строки, но реальные токены, cookie и пароли не следует сохранять в файле, публикуемом на GitHub. Примеры ниже содержат только заглушки. Настройки могут сочетаться, кроме HTTP Basic Auth и явно заданного заголовка Authorization.

## Bearer-токен или API-ключ

Если сайт принимает Bearer-токен:

```python
REQUEST_HEADERS = {
    "Authorization": "env:SITE_AUTHORIZATION",
}
```

В том же окне PowerShell, из которого запускается скрипт:

```powershell
$env:SITE_AUTHORIZATION = "Bearer ЗНАЧЕНИЕ_ОТ_ВЛАДЕЛЬЦА"
.\venv\Scripts\python.exe main.py
```

Для сайта с собственным заголовком API-ключа:

```python
REQUEST_HEADERS = {"X-API-Key": "env:SITE_API_KEY"}
```

Имя заголовка и формат значения определяет владелец сайта. Ключ от API не обязательно дает доступ к обычным HTML-страницам.

## Cookie авторизованной сессии

```python
REQUEST_COOKIES = {
    "sessionid": "env:SITE_SESSION_ID",
}
```

`sessionid` — только пример: нужны настоящее имя и значение cookie, предоставленные для этого сайта. Можно указать несколько cookie. Они хранятся в памяти Session, привязаны к проверяемому хосту и HTTPS; ответные cookie сайт может обновлять в рамках запуска. Автоматического входа через форму и обновления истекшей сессии нет. Скрипт не читает cookie из установленного браузера.

## HTTP Basic Auth

```python
HTTP_BASIC_AUTH = (
    "env:SITE_USERNAME",
    "env:SITE_PASSWORD",
)
```

Это HTTP-аутентификация, а не заполнение формы логина. Не задавайте одновременно Authorization в REQUEST_HEADERS.

## Cloudflare Access

Владелец Cloudflare Access может создать service token и разрешить его в политике приложения (например, Service Auth). Тогда:

```python
REQUEST_HEADERS = {
    "CF-Access-Client-Id": "env:CF_ACCESS_CLIENT_ID",
    "CF-Access-Client-Secret": "env:CF_ACCESS_CLIENT_SECRET",
}
```

Это доступ по политике Cloudflare Access, а не универсальный ключ для прохождения CAPTCHA или всех правил WAF/Bot Management. Сайт может требовать отдельную авторизацию приложения. Общий Cloudflare API token для управления аккаунтом сюда подставлять не нужно.

## Если доступа нет

Ответы 401/403 и Cloudflare Challenge с заголовком `cf-mitigated: challenge` получают статус `blocked`; обход останавливается. HTML такой проверки не отправляется в LanguageTool. Остальные защиты могут выглядеть как обычная страница: универсального распознавания нет, в частности HTML-форма входа с ответом 200 может быть принята за содержимое сайта.

Скрипт не выполняет JavaScript, не решает CAPTCHA и не обновляет токены автоматически. Cookie проверок могут быть ограничены сроком действия и контекстом клиента, поэтому перенос в requests не гарантирует доступ.

Для закрытых сайтов отчет может содержать фрагменты закрытых страниц; доступ к отчету определяйте соответственно.

## Проверка реализации

```powershell
.\venv\Scripts\python.exe -B -m unittest test_url_ignore test_rule_ignore test_request_access -v
```

Тесты подготавливают настоящие запросы requests и подменяют транспорт. Внешняя сеть, Java и реальные учетные данные не используются. Доступ к реальному защищенному сайту этими тестами не подтвержден.

Источники:
- [Requests: Session, headers и cookies](https://requests.readthedocs.io/en/latest/user/advanced/)
- [Cloudflare Access: service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
- [Cloudflare: распознавание Challenge Page](https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/)
