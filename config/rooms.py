"""Комнаты совместного просмотра.

Главная идея синхронизации: у комнаты есть «таймлайн» — играет ли видео, на какой
секунде оно было и в какой момент. Менять таймлайн может только админ комнаты,
сервер пересчитывает текущую секунду по своим часам и рассылает её всем зрителям.
Плееры зрителей просто подстраиваются под таймлайн.
"""
import math
import secrets
import time

from setting import rooms, rooms_lock, create_name_room, ROOM_TTL

MAX_MESSAGES = 200  # сколько последних сообщений чата помнит комната
MAX_MESSAGE_LENGTH = 500
MAX_POSITION = 48 * 3600  # секунд; защита от мусорных значений
MIN_RATE, MAX_RATE = 0.25, 2.0

SOURCE_LABELS = {
    'youtube': 'YouTube',
    'file': 'Видео по ссылке',
    'local': 'Свой файл',
    'embed': 'Фильм из каталога',
}

sockets = {}  # sid подключения -> код комнаты


def _clock():
    return time.monotonic()


def _number(value):
    """Число из данных клиента или None, если пришёл мусор."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def _new_state(position=0.0):
    return {'playing': False, 'pos': float(position or 0), 'rate': 1.0,
            'ts': _clock(), 'duration': None}


# ---------------------------------------------------------------- таймлайн

def position(state):
    """На какой секунде видео находится прямо сейчас."""
    pos = state['pos']
    if state['playing']:
        pos += (_clock() - state['ts']) * state['rate']
    duration = state['duration']
    if duration and pos > duration:
        pos = duration
    return max(0.0, pos)


def snapshot(room):
    """Состояние плеера «на сейчас» — в таком виде оно уходит зрителям."""
    state = room['state']
    pos = position(state)
    if state['playing'] and state['duration'] and pos >= state['duration']:
        # видео доиграло до конца — останавливаем таймлайн
        state.update(playing=False, pos=state['duration'], ts=_clock())
    return {'playing': state['playing'], 'pos': round(pos, 3),
            'rate': state['rate'], 'rev': room['source']['rev']}


def control(room, data):
    """Команда админа плееру. Возвращает True, если состояние изменилось."""
    if not isinstance(data, dict):
        return False
    state = room['state']
    action = data.get('action')
    pos = _number(data.get('pos'))
    if pos is None:
        pos = position(state)
    pos = min(max(pos, 0.0), state['duration'] or MAX_POSITION)
    playing, rate = state['playing'], state['rate']

    if action == 'play':
        playing = True
    elif action == 'pause':
        playing = False
    elif action == 'seek':
        pass
    elif action == 'rate':
        rate = _number(data.get('rate'))
        if rate is None or not MIN_RATE <= rate <= MAX_RATE:
            return False
    else:
        return False

    state.update(playing=playing, pos=pos, rate=rate, ts=_clock())
    return True


def set_duration(room, value):
    duration = _number(value)
    state = room['state']
    if duration is None or not 0 < duration <= MAX_POSITION:
        return
    if state['duration'] is None or abs(state['duration'] - duration) > 0.5:
        # фиксируем текущую позицию по старым правилам и запоминаем длину
        state.update(pos=position(state), ts=_clock(), duration=duration)


# ---------------------------------------------------------------- комнаты

def purge_rooms():
    """Удаляет комнаты, в которых давно никого нет."""
    now = time.time()
    with rooms_lock:
        dead = [code for code, room in rooms.items()
                if not room['users'] and room['empty_since'] is not None
                and now - room['empty_since'] > ROOM_TTL]
        for code in dead:
            del rooms[code]


def add_message(room, name, message, **extra):
    content = {"name": name, "message": message}
    content.update(extra)
    room["messages"].append(content)
    del room["messages"][:-MAX_MESSAGES]
    return content


def create_room(source, admin_name, owner, closed=False):
    """Создаёт комнату и возвращает её код. owner — ключ создателя (он админ)."""
    with rooms_lock:
        purge_rooms()
        room = create_name_room()
        source = dict(source, rev=1)
        rooms[room] = {"members": 0, "messages": [], 'url': source.get('url', ''),
                       'v': 'film' if source['kind'] == 'embed' else 'video',
                       'admin': admin_name, 'status': 'close' if closed else 'open',
                       'owner': owner, 'source': source,
                       'state': _new_state(source.get('start')),
                       'users': {}, 'banned': set(), 'empty_since': time.time()}
        add_message(rooms[room], 'KinBu', f'Имя комнаты: {room}', system=True)
        add_message(rooms[room], 'KinBu', 'Приятного просмотра ^-^', system=True)
    return room


def set_source(room, source):
    """Админ сменил видео: новый источник и таймлайн с начала."""
    source = dict(source, rev=room['source']['rev'] + 1)
    room['source'] = source
    room['url'] = source.get('url', '')
    room['v'] = 'film' if source['kind'] == 'embed' else 'video'
    room['state'] = _new_state(source.get('start'))


def media_in_use(rel_path):
    """Смотрят ли сейчас этот файл медиатеки хоть в одной комнате."""
    with rooms_lock:
        return any(room['source'].get('local') == rel_path for room in rooms.values())


# ---------------------------------------------------------------- участники

def join(code, sid, name, key, authed=False, avatar=None):
    room = rooms[code]
    user = {'id': secrets.token_hex(4), 'name': name, 'key': key,
            'auth': authed, 'avatar': avatar}
    first = all(other['key'] != key for other in room['users'].values())
    room['users'][sid] = user
    room['members'] = len(room['users'])
    room['empty_since'] = None
    sockets[sid] = code
    return user, first


def leave(sid):
    """Убирает подключение из комнаты. Возвращает (код, комната, участник, ушёл_совсем)."""
    code = sockets.pop(sid, None)
    room = rooms.get(code)
    if room is None:
        return code, None, None, False
    user = room['users'].pop(sid, None)
    room['members'] = len(room['users'])
    if not room['users']:
        room['empty_since'] = time.time()
    last = user is not None and all(other['key'] != user['key'] for other in room['users'].values())
    return code, room, user, last


def find(sid):
    """Комната и участник по подключению: (код, комната, участник) или (None, None, None)."""
    code = sockets.get(sid)
    room = rooms.get(code)
    if room is None:
        return None, None, None
    user = room['users'].get(sid)
    if user is None:
        return None, None, None
    return code, room, user


def is_admin(room, user):
    return user is not None and user['key'] == room['owner']


def sids_of(room, public_id):
    """Все подключения участника (у него может быть несколько вкладок)."""
    target = next((u for u in room['users'].values() if u['id'] == public_id), None)
    if target is None:
        return None, []
    return target, [sid for sid, u in room['users'].items() if u['key'] == target['key']]


# ---------------------------------------------------------------- для шаблонов и клиентов

def source_label(room):
    source = room['source']
    if source.get('local'):
        return SOURCE_LABELS['local']
    return SOURCE_LABELS.get(source['kind'], '')


def public_source(room):
    source = room['source']
    data = {'kind': source['kind'], 'title': source.get('title') or '',
            'rev': source['rev'], 'label': source_label(room)}
    if source['kind'] == 'youtube':
        data['id'] = source['id']
    else:
        data['src'] = source['src']
        data['hls'] = bool(source.get('hls'))
    return data


def public_users(room):
    return [{'id': user['id'], 'name': user['name'], 'avatar': user['avatar'],
             'admin': user['key'] == room['owner']}
            for user in room['users'].values()]


def public_room(code, room):
    return {'code': code, 'admin': room['admin'], 'status': room['status'],
            'members': room['members']}


def open_rooms():
    """Открытые комнаты для главной страницы."""
    purge_rooms()
    with rooms_lock:
        return [(code, {'admin': room['admin'], 'members': room['members'],
                        'title': room['source'].get('title') or '',
                        'label': source_label(room), 'status': room['status']})
                for code, room in rooms.items() if room.get('status') == 'open']
