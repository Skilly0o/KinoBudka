"""Источники видео для комнат: что можно смотреть через свой плеер.

* YouTube — по ссылке на ролик;
* прямая ссылка на видеофайл (.mp4, .webm ...) или поток HLS (.m3u8);
* свой файл из папки media на компьютере, где запущен сайт.
"""
import os
import re
from urllib.parse import urlparse, unquote, quote

from werkzeug.security import safe_join

from config.youtube import get_video_id, get_start_time
from setting import MEDIA_DIR

# Расширение файла -> тип содержимого, который поймёт браузер
VIDEO_TYPES = {
    '.mp4': 'video/mp4',
    '.m4v': 'video/mp4',
    '.webm': 'video/webm',
    '.mkv': 'video/x-matroska',
    '.mov': 'video/quicktime',
    '.ogv': 'video/ogg',
}

_DIRECT_LINK = re.compile(r'\.(mp4|m4v|webm|mkv|mov|ogv)(?![a-z0-9])', re.IGNORECASE)
_HLS_LINK = re.compile(r'\.m3u8(?![a-z0-9])', re.IGNORECASE)

SOURCE_HINT = ('Нужна ссылка на ролик YouTube или прямая ссылка на видео '
               '(.mp4, .webm) либо поток (.m3u8)')


def parse_source(url):
    """Разбирает вставленную ссылку. Возвращает описание источника или None."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url or len(url) > 2000:
        return None

    video_id = get_video_id(url)
    if video_id:
        return {'kind': 'youtube', 'id': video_id, 'url': url,
                'title': 'Видео с YouTube', 'start': get_start_time(url)}

    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        return None
    where = parsed.path + '?' + parsed.query
    is_hls = bool(_HLS_LINK.search(where))
    if not is_hls and not _DIRECT_LINK.search(where):
        return None
    title = unquote(os.path.basename(parsed.path.rstrip('/'))) or parsed.netloc
    return {'kind': 'file', 'src': url, 'url': url, 'hls': is_hls,
            'title': title[:120], 'start': 0}


def format_size(size):
    for unit in ('Б', 'КБ', 'МБ', 'ГБ'):
        if size < 1024 or unit == 'ГБ':
            if unit in ('Б', 'КБ'):
                return f'{size:.0f} {unit}'
            return f'{size:.1f} {unit}'
        size /= 1024


def list_local_media():
    """Список видеофайлов из папки media (вместе с вложенными папками)."""
    items = []
    if not os.path.isdir(MEDIA_DIR):
        return items
    for root, dirs, files in os.walk(MEDIA_DIR):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        for filename in sorted(files, key=str.lower):
            name, ext = os.path.splitext(filename)
            if filename.startswith('.') or ext.lower() not in VIDEO_TYPES:
                continue
            full = os.path.join(root, filename)
            rel = os.path.relpath(full, MEDIA_DIR).replace(os.sep, '/')
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            items.append({
                'path': rel,
                'name': name,
                'ext': ext.lower().lstrip('.'),
                'folder': os.path.dirname(rel),
                'size': format_size(size),
            })
    return items


def resolve_local(rel_path):
    """Полный путь к файлу медиатеки или None, если файла нет / путь ведёт наружу."""
    if not rel_path or not isinstance(rel_path, str):
        return None
    full = safe_join(MEDIA_DIR, rel_path)
    if not full or not os.path.isfile(full):
        return None
    if os.path.splitext(full)[1].lower() not in VIDEO_TYPES:
        return None
    return full


def local_source(rel_path):
    """Источник для комнаты из файла медиатеки."""
    if not resolve_local(rel_path):
        return None
    rel_path = rel_path.replace('\\', '/')
    name = os.path.splitext(os.path.basename(rel_path))[0]
    return {'kind': 'file', 'src': '/media/' + quote(rel_path), 'url': rel_path,
            'local': rel_path, 'hls': False, 'title': name[:120], 'start': 0}


def embed_source(url, title):
    """Встроенный сторонний плеер (каталог фильмов) — управлять им снаружи нельзя."""
    return {'kind': 'embed', 'src': url, 'url': url, 'title': title, 'start': 0}
