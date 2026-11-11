import hashlib
import math
import os
import secrets
import socket
import sqlite3
from datetime import timedelta
from io import BytesIO
from urllib.parse import urlsplit

from flask import (render_template, redirect, url_for, flash, request, session, abort,
                   send_from_directory, Response)
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from flask_socketio import join_room, leave_room, send, SocketIO, emit
from flask_socketio import disconnect as close_socket
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from markupsafe import escape
from PIL import Image, ImageDraw, ImageOps
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import SubmitField

from config import rooms as roomlib
from config.admin import admin, UserModelView, FilmModelView
from config.films import Films
from config.mail_sender import send_email
from config.media import (parse_source, local_source, embed_source, list_local_media,
                          resolve_local, VIDEO_TYPES, SOURCE_HINT)
from config.user import User
from config.user_login import User_login
from setting import (app, db, rooms, rooms_lock, HOST, PORT, DEBUG, MEDIA_DIR, FILMS_DB,
                     UPLOADS_DIR, DEFAULT_AVATAR)

try:  # перевод писем — необязательная возможность, без googletrans сайт тоже работает
    from googletrans import Translator
except Exception:  # noqa: библиотека может быть не установлена или сломана
    Translator = None

IMAGES = ['jpg', 'jpe', 'jpeg', 'png', 'gif', 'webp', 'bmp']
FILMS_PER_PAGE = 60
NICK_LENGTH = 16

app.permanent_session_lifetime = timedelta(days=31)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = None

# async_mode='threading' — обычные потоки: ничего лишнего ставить не нужно,
# одинаково работает на Windows / Linux / macOS
socketio = SocketIO(app, async_mode='threading')

admin.add_view(UserModelView(User, db))
admin.add_view(FilmModelView(Films, db))


def films_query(query, parameters=(), one=False):
    """Запрос к базе фильмов. Возвращает строки (или одну строку при one=True)."""
    try:
        con = sqlite3.connect(FILMS_DB, check_same_thread=False)
    except sqlite3.Error:
        return None if one else []
    try:
        cur = con.execute(query, parameters)
        return cur.fetchone() if one else cur.fetchall()
    except sqlite3.Error:
        return None if one else []
    finally:
        con.close()


def clean_nick(value):
    return ' '.join(str(value or '').split())[:NICK_LENGTH]


def identity():
    """Ключ, по которому сайт узнаёт человека: аккаунт или гостевая сессия.

    По этому ключу комната помнит своего админа, поэтому подделать его
    чужим ником нельзя — ключ лежит в подписанной cookie.
    """
    if current_user.is_authenticated:
        return f'user:{current_user.get_id()}'
    if not session.get('uid'):
        session['uid'] = secrets.token_hex(8)
        session.permanent = True
    return f"guest:{session['uid']}"


def visitor_name(nick=None):
    """Имя для комнаты: логин пользователя или ник гостя."""
    if current_user.is_authenticated:
        return current_user.username
    return clean_nick(nick) or session.get('name') or 'Пользователь'


def avatar_url(user_id):
    return url_for('avatar', user_id=user_id)


@app.context_processor
def template_globals():
    return {'avatar_url': avatar_url}


@app.errorhandler(403)
def access_forbidden(e):
    return render_template('error.html', error='403'), 403


@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error='404'), 404


@app.errorhandler(413)
def file_too_large(e):
    flash('Файл слишком большой (максимум 16 МБ)', 'error')
    return redirect(request.url)


@login_manager.user_loader
def load_user(user_id):  # функция загрузки пользователя
    user = User.query.filter_by(id=user_id).first()
    if user is None:
        return None
    return User_login().create(user)


@app.route('/set_session/<value>')
@login_required
def set_session(value):
    session['value'] = value
    return 'Значение переменной value сохранено в сессии.'


@app.route('/get_session')
@login_required
def get_session():
    value = session.get('value', 'Not set')
    return 'Значение переменной value в сессии: {}'.format(escape(value))


@app.route("/", methods=['GET', 'POST'])
def hello():  # главная страница
    random_data = films_query('select * from films order by random() limit 5')
    return render_template('total.html', movie=random_data, room=roomlib.open_rooms(), user=current_user)


@app.route("/info")
def info():  # Обработка страницы с информацией  сюда можно написать инфинструкции
    return render_template('info.html')


@app.route("/login", methods=['GET', 'POST'])
def login():  # вход пользователя
    if current_user.is_authenticated:  # если пользователь уже на сайте то перенаправляем его в профиль
        return redirect(url_for('profile'))
    if request.method == 'POST':
        email = request.form['email']  # берем из входа почту и по ней ищем пользователя
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, request.form[
            'password']):  # проверяем введенный пароль с паролем из базы данных
            userlogin = User_login().create(user)
            login_user(userlogin)  # Если все совпало то логинем пользователя перенаправляя его в профиль
            session['name'] = user.username
            target = request.args.get('next', '')
            if target.startswith('/') and not target.startswith('//'):
                return redirect(target)
            return redirect(url_for('profile'))
        flash('Неверная почта или пароль', 'error')
    return render_template('login.html')


@app.route("/abuse", methods=['GET', 'POST'])
def abuse():  # для авторов в случае нарушения АП ( обратная связь)
    if request.method == 'POST':
        email = str(request.form['email'])
        org = str(request.form['org'])
        contact = str(request.form['contact'])
        url = str(request.form['url'])
        url_autor = str(request.form['body'])
        subject = 'Нарушение АП'
        body = f"User {email}\n Org-{org} Name-{contact}\n violation-{url} Autor-{url_autor}"
        try:
            if Translator is not None:
                body = Translator().translate(body, dest='en').text
        except Exception:
            pass  # перевести не вышло — отправим как есть
        try:
            if send_email(email, subject, body):
                return render_template('error.html', error='abuse')
        except Exception as er:
            print('mail error:', er)
        return render_template('error.html', error='mail_error')
    return render_template('abuse.html', user=current_user)


@app.route("/support", methods=['GET', 'POST'])
def support():  # поддержка ( обратная связь)
    if request.method == 'POST':
        email = request.form['email']
        subject = request.form['subject']
        body = f"User {email} \n{'-' * 92} \n{request.form['body']}"
        try:
            if send_email(email, subject, body):
                return render_template('error.html', error='supp')
        except Exception as er:
            print('mail error:', er)
        return render_template('error.html', error='mail_error')
    return render_template('support.html', user=current_user)


@app.route('/register', methods=['GET', 'POST'])
def register():  # регистрация пользователя
    if request.method == 'POST':
        name = clean_nick(request.form['name'])
        email = request.form['email'].strip()
        password = request.form['password']
        if not name or len(password) < 8:
            flash('Введите имя и пароль не короче 8 символов', 'error')
            return render_template('reg.html')
        n_psw = generate_password_hash(password)

        user = User(username=name, email=email, password=n_psw, avatar=b'')  # берем из запроса данные и создаем пользователля
        try:
            db.session.add(user)  # если все ок добавляем в базу данных и сохраняем
            db.session.commit()  # перенапрявляя пользователя на страницу входа
            flash('Вы зарегистрированы! Теперь можно войти.', 'success')
            return redirect(url_for('login'))
        except Exception:
            db.session.rollback()  # если чет не получилось откатываем базу данных
            flash('Такое имя или почта уже заняты, попробуйте другие.', 'error')

    return render_template('reg.html')


class UploadForm(FlaskForm):
    photo = FileField(validators=[FileAllowed(IMAGES, 'Только изображения!'),
                                  FileRequired('Файл не выбран!')])
    submit = SubmitField('Поменять авaтарку')


def prepare_mask(size, antialias=2):
    mask = Image.new('L', (size[0] * antialias, size[1] * antialias), 0)
    ImageDraw.Draw(mask).ellipse((0, 0) + mask.size, fill=255)
    return mask.resize(size, Image.Resampling.LANCZOS)


def crop(im, s):
    w, h = im.size
    k = w / s[0] - h / s[1]
    if k > 0:
        im = im.crop(((w - h) / 2, 0, (w + h) / 2, h))
    elif k < 0:
        im = im.crop((0, (h - w) / 2, w, (h + w) / 2))
    return im.resize(s, Image.Resampling.LANCZOS)


@app.route("/profile", methods=['GET', 'POST'])
@login_required
def profile():  # профиль пользователя
    user = User.query.filter_by(id=current_user.get_id()).first()

    # замена аватарки
    form = UploadForm()
    if form.validate_on_submit():
        try:
            img = Image.open(form.photo.data.stream)
            img = ImageOps.exif_transpose(img).convert('RGBA')
            # изменяем размер
            im = crop(img, (200, 200))
            im.putalpha(prepare_mask((200, 200), 4))
            buffer = BytesIO()
            im.save(buffer, 'PNG')
        except Exception:
            flash('Не получилось прочитать картинку, попробуйте другой файл', 'error')
        else:
            # Загркжаем аватарку в базу данных
            user.avatar = buffer.getvalue()
            db.session.commit()
            flash('Аватарка обновлена', 'success')
        return redirect(url_for('profile'))

    role = 'Пользователь' if user.role == 'user' else 'Администратор'
    version = hashlib.md5(user.avatar or b'').hexdigest()[:8]
    file_url = avatar_url(user.id) + '?v=' + version
    return render_template('profile.html', name=user.username, mail=user.email, role=role,
                           is_site_admin=str(user.role).lower() == 'admin',
                           avatar='image111.png', form=form, file_url=file_url)


@app.route('/avatar/<int:user_id>.png')
def avatar(user_id):  # аватарка пользователя из базы данных (или стандартная)
    user = User.query.filter_by(id=user_id).first()
    if user is None or not user.avatar:
        return send_from_directory(UPLOADS_DIR, DEFAULT_AVATAR, max_age=3600)
    response = Response(bytes(user.avatar), mimetype='image/png')
    response.set_etag(hashlib.md5(bytes(user.avatar)).hexdigest())
    response.headers['Cache-Control'] = 'no-cache'
    return response.make_conditional(request)


@app.route("/logout", methods=['GET', 'POST'])
@login_required
def logout():  # выход пользователя
    logout_user()
    session.pop('name', None)
    flash('Вы вышли из аккаунта', 'success')
    return redirect(url_for('login'))


@app.route("/youtube", methods=['GET', 'POST'])
def youtube():  # для создания видоса с ютуба
    if request.method == 'POST':
        url = (request.form.get("hrf") or '').strip()
        code = (request.form.get("code") or '').strip()
        join = request.form.get("join", False)
        create = request.form.get("create", False)
        isclose = request.form.get("close")
        name = visitor_name(request.form.get('nick'))

        if create is not False:
            source = parse_source(url)
            if source is None:
                return render_template('youtube.html', user=current_user, error='not url', hrf=url)
            room = roomlib.create_room(source, name, identity(), closed=bool(isclose))
            session["room"] = room
            session["name"] = name
            return redirect(url_for("room", nameroom=room))

        if join is not False:
            # можно вставить и код, и всю ссылку на комнату
            code = code.rstrip('/').split('/')[-1].split('?')[0]
            if not code or code not in rooms:
                return render_template('youtube.html', user=current_user, error='not room', code=code)
            session["room"] = code
            session["name"] = name
            return redirect(url_for("room", nameroom=code))

    return render_template('youtube.html', user=current_user)


@app.route("/films", methods=['GET', 'POST'])
@login_required
def films():  # фильмы
    if request.method == 'POST':
        name = request.form.get("filmname") or ''
    else:
        name = request.args.get('q') or ''
    name = name.strip()
    rezult = films_query('select * from films')
    if name:
        rezult = [movie for movie in rezult if name.lower() in (movie[2] or '').lower()]
    pages = max(1, math.ceil(len(rezult) / FILMS_PER_PAGE))
    page = min(max(request.args.get('page', 1, type=int), 1), pages)
    movies = rezult[(page - 1) * FILMS_PER_PAGE:page * FILMS_PER_PAGE]
    return render_template('filmslist.html', movies=movies, lenmovies=len(rezult), query=name,
                           page=page, pages=pages, library=list_local_media())


@app.route("/movie/<id>", methods=['GET', 'POST'])
@login_required
def films_info(id):  # инфа фильмы
    rezult = films_query('select * from films where id = ?', (id,), one=True)
    if rezult is None:
        abort(404)
    if request.method == 'POST':
        isclose = request.form.get("close")
        name = current_user.username
        room = roomlib.create_room(embed_source(rezult[5], rezult[2]), name, identity(),
                                   closed=bool(isclose))
        session["room"] = room
        session["name"] = name
        return redirect(url_for("room", nameroom=room))
    return render_template('info_film.html', movie=rezult)


@app.route("/library/<path:filename>", methods=['GET', 'POST'])
@login_required
def library(filename):  # свой файл из папки media: страница и создание комнаты
    item = next((item for item in list_local_media() if item['path'] == filename), None)
    if item is None:
        abort(404)
    if request.method == 'POST':
        isclose = request.form.get("close")
        name = current_user.username
        room = roomlib.create_room(local_source(filename), name, identity(), closed=bool(isclose))
        session["room"] = room
        session["name"] = name
        return redirect(url_for("room", nameroom=room))
    return render_template('info_film.html', movie=None, local=item)


@app.route("/media/<path:filename>")
def media_file(filename):  # отдаёт видеофайл из медиатеки (с перемоткой — Range-запросы)
    full = resolve_local(filename)
    if full is None:
        abort(404)
    if not roomlib.media_in_use(filename):
        abort(403)  # файл доступен, только пока его смотрят в какой-нибудь комнате
    mimetype = VIDEO_TYPES[os.path.splitext(full)[1].lower()]
    return send_from_directory(MEDIA_DIR, filename, mimetype=mimetype, conditional=True, max_age=0)


def share_links(code):
    """Ссылки на комнату, которые можно отправить друзьям.

    Если хозяин открыл сайт как localhost, такая ссылка у друзей не откроется —
    поэтому подставляем адреса этого компьютера (Hamachi, Radmin VPN, локальная сеть).
    """
    path = url_for('room', nameroom=code)
    parts = urlsplit(request.host_url)
    here = [{'label': '', 'url': request.host_url.rstrip('/') + path}]
    if parts.hostname not in ('localhost', '127.0.0.1', '::1'):
        return here
    port = f':{parts.port}' if parts.port else ''
    order = {'Hamachi': 0, 'Radmin VPN': 1, 'Tailscale': 2}
    addresses = sorted(local_addresses(), key=lambda item: order.get(describe_address(item), 9))
    return [{'label': describe_address(address), 'url': f'{parts.scheme}://{address}{port}{path}'}
            for address in addresses] or here


@app.route("/room/<nameroom>", methods=['GET', 'POST'])
def room(nameroom):  # room page для фильмов и видео с ютуба
    roomlib.purge_rooms()
    current = rooms.get(nameroom)
    if current is None:
        return render_template('error.html', error='not_room'), 404

    me = identity()
    if me in current['banned']:
        return render_template('error.html', error='kicked'), 403

    if current_user.is_authenticated:
        name = current_user.username
    else:
        if request.method == 'POST':  # гость ввёл ник на странице входа в комнату
            nick = clean_nick(request.form.get('nick'))
            if nick:
                session["name"] = nick
            return redirect(url_for("room", nameroom=nameroom))
        name = session.get("name")
        if not name:
            return render_template('join.html', code=nameroom, admin=current['admin'],
                                   members=current['members'])

    session["room"] = nameroom
    session["name"] = name

    is_admin = current['owner'] == me
    settings = {  # всё, что нужно странице комнаты (static/js/room.js)
        'code': nameroom,
        'name': name,
        'isAdmin': is_admin,
        'canChat': bool(current_user.is_authenticated),
        'admin': current['admin'],
        'status': current['status'],
        'source': roomlib.public_source(current),
        'share': share_links(nameroom),
        'home': url_for('hello'),
        'hlsUrl': url_for('static', filename='js/hls.min.js'),
    }
    return render_template("room.html", code=nameroom, room=current, is_admin=is_admin,
                           settings=settings, url=current["url"], messages=current["messages"])


# ---------------------------------------------------------------- сокеты

def announce(code, room, text):
    """Служебное сообщение в чат комнаты."""
    send(roomlib.add_message(room, 'KinBu', text, system=True), to=code)


def push_room(code, room):
    emit('room', roomlib.public_room(code, room), to=code)
    emit('users', roomlib.public_users(room), to=code)


@socketio.on("connect")
def connect(auth=None):
    code = (auth or {}).get('room') if isinstance(auth, dict) else None
    code = code or session.get("room")
    name = session.get("name")
    if not code or not name:
        return False
    with rooms_lock:
        room = rooms.get(code)
        if room is None:
            return False
        if current_user.is_authenticated:
            key = f'user:{current_user.get_id()}'
            picture = avatar_url(current_user.get_id())
        else:
            key = f"guest:{session.get('uid') or secrets.token_hex(8)}"
            picture = None
        if key in room['banned']:
            return False

        join_room(code)
        user, first = roomlib.join(code, request.sid, name, key,
                                   authed=bool(current_user.is_authenticated), avatar=picture)
        emit('init', {
            'you': {'id': user['id'], 'name': name, 'admin': roomlib.is_admin(room, user)},
            'room': roomlib.public_room(code, room),
            'source': roomlib.public_source(room),
            'state': roomlib.snapshot(room),
            'users': roomlib.public_users(room),
            'messages': room['messages'],
        })
        emit('room', roomlib.public_room(code, room), to=code, include_self=False)
        emit('users', roomlib.public_users(room), to=code, include_self=False)
        if first:
            announce(code, room, f'{name} присоединился/ась к комнате')
    print(f"{name} joined room {code}")


@socketio.on("disconnect")
def disconnect(*_reason):
    with rooms_lock:
        code, room, user, last = roomlib.leave(request.sid)
        if room is None or user is None:
            return
        leave_room(code)
        push_room(code, room)
        if last:
            announce(code, room, f"{user['name']} покинул/а комнату")
    print(f"{user['name']} has left the room {code}")


@socketio.on("message")
def message(data):  # сообщение в чат (чат доступен вошедшим в аккаунт)
    with rooms_lock:
        code, room, user = roomlib.find(request.sid)
        if room is None or not user['auth'] or not isinstance(data, dict):
            return
        text = str(data.get("data") or '').strip()[:roomlib.MAX_MESSAGE_LENGTH]
        if not text:
            return
        content = roomlib.add_message(room, user['name'], text, avatar=user['avatar'],
                                      admin=roomlib.is_admin(room, user))
        send(content, to=code)


@socketio.on('sync')
def on_sync():  # зритель просит актуальное состояние плеера
    with rooms_lock:
        code, room, user = roomlib.find(request.sid)
        if room is not None:
            emit('state', roomlib.snapshot(room))


@socketio.on('control')
def on_control(data):  # play / pause / перемотка / скорость — только от админа комнаты
    with rooms_lock:
        code, room, user = roomlib.find(request.sid)
        if room is None:
            return
        if not roomlib.is_admin(room, user) or not roomlib.control(room, data):
            emit('state', roomlib.snapshot(room))  # вернём плеер зрителя к общему состоянию
            return
        emit('state', roomlib.snapshot(room), to=code)


# старые события плеера: оставлены для совместимости и тоже слушаются только админа
@socketio.on('play_video')
def on_play_video():
    on_control({'action': 'play'})


@socketio.on('pause_video')
def on_stop_video():
    on_control({'action': 'pause'})


@socketio.on('meta')
def on_meta(data):  # плеер админа сообщает длину и название видео
    with rooms_lock:
        code, room, user = roomlib.find(request.sid)
        if room is None or not roomlib.is_admin(room, user) or not isinstance(data, dict):
            return
        if data.get('rev') != room['source']['rev']:
            return
        roomlib.set_duration(room, data.get('duration'))
        title = data.get('title')
        if isinstance(title, str) and title.strip() and room['source']['kind'] == 'youtube':
            title = title.strip()[:120]
            if title != room['source'].get('title'):
                room['source']['title'] = title
                emit('title', {'title': title, 'rev': room['source']['rev']}, to=code)


@socketio.on('source')
def on_source(data):  # админ меняет видео в комнате
    with rooms_lock:
        code, room, user = roomlib.find(request.sid)
        if room is None or not roomlib.is_admin(room, user) or not isinstance(data, dict):
            return {'ok': False, 'error': 'Менять видео может только админ комнаты'}
        if data.get('file'):
            source = local_source(data.get('file')) if user['auth'] else None
            error = 'Файл не найден в медиатеке'
        else:
            source = parse_source(data.get('url'))
            error = SOURCE_HINT
        if source is None:
            return {'ok': False, 'error': error}
        roomlib.set_source(room, source)
        emit('source', {'source': roomlib.public_source(room), 'state': roomlib.snapshot(room)}, to=code)
        announce(code, room, f"{user['name']} сменил/а видео: {source['title']}")
        return {'ok': True}


@socketio.on('library')
def on_library():  # список своих файлов для админа комнаты
    with rooms_lock:
        code, room, user = roomlib.find(request.sid)
        if room is None or not roomlib.is_admin(room, user) or not user['auth']:
            return []
    return [{'path': item['path'], 'name': item['name'], 'size': item['size']}
            for item in list_local_media()]


@socketio.on('status')
def on_status(data):  # открытая (видна на главной) / закрытая (вход только по ссылке)
    with rooms_lock:
        code, room, user = roomlib.find(request.sid)
        if room is None or not roomlib.is_admin(room, user) or not isinstance(data, dict):
            return
        status = data.get('status')
        if status not in ('open', 'close') or status == room['status']:
            return
        room['status'] = status
        push_room(code, room)
        announce(code, room, 'Комната теперь открытая' if status == 'open' else 'Комната теперь закрытая')


@socketio.on('kick')
def on_kick(data):  # админ исключает зрителя
    with rooms_lock:
        code, room, user = roomlib.find(request.sid)
        if room is None or not roomlib.is_admin(room, user) or not isinstance(data, dict):
            return
        target, sids = roomlib.sids_of(room, data.get('id'))
        if target is None or target['key'] == room['owner']:
            return
        room['banned'].add(target['key'])
        announce(code, room, f"{target['name']} исключён/а из комнаты")
        for sid in sids:
            emit('kicked', to=sid)
    for sid in sids:
        close_socket(sid=sid, namespace='/')


@socketio.on('transfer')
def on_transfer(data):  # админ передаёт управление другому зрителю
    with rooms_lock:
        code, room, user = roomlib.find(request.sid)
        if room is None or not roomlib.is_admin(room, user) or not isinstance(data, dict):
            return
        target, _sids = roomlib.sids_of(room, data.get('id'))
        if target is None or target['key'] == room['owner']:
            return
        room['owner'] = target['key']
        room['admin'] = target['name']
        push_room(code, room)
        announce(code, room, f"Теперь комнатой управляет {target['name']}")


@socketio.on('close')
def on_close():  # админ завершает просмотр и удаляет комнату
    with rooms_lock:
        code, room, user = roomlib.find(request.sid)
        if room is None or not roomlib.is_admin(room, user):
            return
        emit('closed', to=code)
        rooms.pop(code, None)


# ---------------------------------------------------------------- запуск

def local_addresses():
    """IPv4-адреса этого компьютера: по ним сайт открывают друзья."""
    found = set()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(item[4][0])
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(('10.255.255.255', 1))
        found.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    return sorted(address for address in found if not address.startswith('127.'))


def describe_address(address):
    first, second = (int(part) for part in address.split('.')[:2])
    if first == 25:
        return 'Hamachi'
    if first == 26:
        return 'Radmin VPN'
    if first == 100 and 64 <= second <= 127:
        return 'Tailscale'
    return 'Локальная сеть'


def print_addresses():
    print()
    print('  KinoBudka запущена')
    print(f'  У себя открывайте:   http://localhost:{PORT}')
    if HOST in ('0.0.0.0', '::'):
        for address in local_addresses():
            print(f'  Друзьям ({describe_address(address)}): http://{address}:{PORT}')
    else:
        print(f'  Сайт слушает только адрес {HOST}')
    print(f'  Свои видео кладите в папку: {MEDIA_DIR}')
    print('  Остановить сайт: Ctrl+C')
    print()


if __name__ == '__main__':
    os.makedirs(MEDIA_DIR, exist_ok=True)
    print_addresses()
    socketio.run(app, host=HOST, port=PORT, debug=DEBUG, allow_unsafe_werkzeug=True)
