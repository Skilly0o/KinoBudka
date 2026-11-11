import re
from urllib.parse import urlparse, parse_qs

_VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
_TIME_PART = re.compile(r'(\d+)([hms]?)')


def _parse(url):
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if '//' not in url:
        url = 'https://' + url
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in ('http', 'https'):
        return None
    host = (parsed.hostname or '').lower()
    for prefix in ('www.', 'm.', 'music.'):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return parsed, host


def get_video_id(url):
    """Достаёт идентификатор ролика из ссылки на YouTube.

    Понимает обычные ссылки (watch?v=), короткие (youtu.be), shorts, live и embed.
    Возвращает False, если это не ссылка на ролик YouTube.
    """
    result = _parse(url)
    if not result:
        return False
    parsed, host = result
    video_id = None
    if host == 'youtu.be':
        video_id = parsed.path.strip('/').split('/')[0]
    elif host in ('youtube.com', 'youtube-nocookie.com'):
        parts = [part for part in parsed.path.split('/') if part]
        if parts and parts[0] == 'watch':
            video_id = parse_qs(parsed.query).get('v', [''])[0]
        elif len(parts) >= 2 and parts[0] in ('embed', 'shorts', 'live', 'v', 'e'):
            video_id = parts[1]
    if video_id and _VIDEO_ID.match(video_id):
        return video_id
    return False


def get_start_time(url):
    """Время начала из ссылки (?t=90, ?t=1m30s, ?start=90) в секундах."""
    result = _parse(url)
    if not result:
        return 0
    parsed, _host = result
    query = parse_qs(parsed.query)
    value = (query.get('t') or query.get('start') or query.get('time_continue') or [''])[0]
    if not value:
        return 0
    if value.isdigit():
        return min(int(value), 24 * 3600)
    seconds = 0
    for amount, unit in _TIME_PART.findall(value.lower()):
        seconds += int(amount) * {'h': 3600, 'm': 60}.get(unit, 1)
    return min(seconds, 24 * 3600)
