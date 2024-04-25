import sqlite3
import random

from flask import render_template, redirect, url_for, flash, request, session
from flask_login import LoginManager, login_user, logout_user
from flask_socketio import join_room, leave_room, send, SocketIO, emit
from googletrans import Translator
from markupsafe import escape
from werkzeug.security import generate_password_hash, check_password_hash

from config.admin import *
from config.films import Films
from config.mail_sender import send_email
from config.user import User
from config.user_login import User_login
from config.youtube import get_video_id
from setting import *

import os
from flask_uploads import UploadSet, configure_uploads, IMAGES, patch_request_class
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import SubmitField
from PIL import Image, ImageDraw
import requests
from sqlalchemy.sql import text


basedir = os.path.abspath(os.path.dirname(__file__))
app.config['UPLOADED_PHOTOS_DEST'] = os.path.join(basedir, 'uploads')

photos = UploadSet('photos', IMAGES)
configure_uploads(app, photos)
# максимальный размер файла, по умолчанию 16MB
patch_request_class(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

socketio = SocketIO(app)

admin.add_view(UserModelView(User, db.session))
admin.add_view(FilmModelView(Films, db.session))

TOKEN = '0ZQWR0F-514MCGT-GB84PY1-ZK93RG2'

def convert_to_binary_data(filename):
    # Преобразование данных в двоичный формат
    with open(filename, 'rb') as file:
        blob_data = file.read()
    return blob_data


@app.errorhandler(403)
def access_forbidden(e):
    return render_template('error.html', error='403'), 403


@login_manager.user_loader
def load_user(user_id):  # функция загрузки пользователя
    username = User.query.filter_by(id=user_id).first().username
    session["name"] = username
    print('load_user', user_id)
    return User_login().fromDB(user_id, User)


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
def hello():  # главная страница ( надо сделать отображение бд с фильмами да и обдумать каак украсить ее
    con = sqlite3.connect('instance/films.db', check_same_thread=False)
    cur = con.cursor()
    rezult = cur.execute(f'''select * from films''').fetchall()
    random_data = random.sample(rezult, 5)
    return render_template('total.html', image=random_data)


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
            return redirect(url_for('profile'))
    flash('Неверные данные', 'error')
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
        translator = Translator()
        body = f"User {email}\n Org-{org} Name-{contact}\n violation-{url} Autor-{url_autor}"
        body_tran = translator.translate(body, dest='en')
        if send_email(email, subject, body_tran.text):
            return render_template('error.html', error='abuse')
        return render_template('error.html', error='mail_error')
    return render_template('abuse.html', user=current_user)


@app.route("/support", methods=['GET', 'POST'])
def support():  # поддержка ( обратная связь)
    if request.method == 'POST':
        email = request.form['email']
        subject = request.form['subject']
        translator = Translator()
        body = f"User {email} \n{'-' * 92} \n{request.form['body']}"
        body_tran = translator.translate(body, dest='en')
        if send_email(email, subject, body):
            return render_template('error.html', error='supp')
        return render_template('error.html', error='mail_error')
    return render_template('support.html', user=current_user)


@app.route('/register', methods=['GET', 'POST'])
def register():  # регистрация пользователя
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        n_psw = generate_password_hash(password)
        emp_photo = convert_to_binary_data('uploads/image114.png')

        user = User(username=name, email=email, password=n_psw, avatar=emp_photo)  # берем из запроса данные и создаем пользователля
        try:
            db.session.add(user)  # если все ок добавляем в базу данных и сохраняем
            db.session.commit()  # перенапрявляя пользователя на страницу входа
            flash('You have been successfully registered!', 'success')
            return redirect(url_for('login'))
        except:
            db.session.rollback()  # если чет не получилось откатываем базу данных
            flash('Something went wrong, please try again.', 'danger')

    return render_template('reg.html')


@app.route("/profile", methods=['GET', 'POST'])
@login_required
def profile():  # профиль пользователя
    username = User.query.filter_by(id=current_user.get_id()).first().username
    email = User.query.filter_by(id=current_user.get_id()).first().email
    role = User.query.filter_by(id=current_user.get_id()).first().role
    ava = User.query.filter_by(id=current_user.get_id()).first().avatar

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

    class UploadForm(FlaskForm):
        photo = FileField(validators=[FileAllowed(photos, 'Image only!'),
                                      FileRequired('File was empty!')])
        submit = SubmitField('Поменять авaтарку')

    # замена аватарки
    form = UploadForm()
    if form.validate_on_submit():
        filename = photos.save(form.photo.data)
        file_url = photos.url(filename)

        response = requests.get(file_url, stream=True).raw
        img = Image.open(response)
        # изменяем размер
        im = crop(img, (200, 200))
        im.putalpha(prepare_mask((200, 200), 4))
        im.save('uploads/image113.png')
        os.remove('uploads/' + filename)

        # Загркжаем аватарку в базу данных
        emp_photo = convert_to_binary_data('uploads/image113.png')
        os.remove('uploads/image113.png')
        query = "UPDATE user SET avatar = :ava WHERE id = :id"
        id = current_user.get_id()
        parameters = {"ava": emp_photo, "id": id}

        stmt = text(query)
        db.session.execute(stmt, parameters)
        db.session.commit()

        query = """SELECT avatar from user where id = :id"""

        stmt = text(query)
        foto = db.session.execute(stmt, parameters).fetchall()

        with open(f'uploads/{parameters["id"]}.png', 'wb') as file:
            file.write(foto[0][0])
        file_url = photos.url(f'{parameters["id"]}.png')
    else:
        id = current_user.get_id()
        parameters = {"id": id}
        query = """SELECT avatar from user where id = :id"""

        stmt = text(query)
        foto = db.session.execute(stmt, parameters).fetchall()

        with open(f'uploads/{parameters["id"]}.png', 'wb') as file:
            file.write(foto[0][0])
        file_url = photos.url(f'{parameters["id"]}.png')
    if role == 'user':
        return render_template('profile.html', name=username, mail=email, role='Пользователь', avatar='image111.png', form=form, file_url=file_url)
    return render_template('profile.html', name=username, mail=email, role='Администратор', avatar='image111.png', form=form, file_url=file_url)


@app.route("/logout", methods=['GET', 'POST'])
@login_required
def logout():  # выход пользователя
    id = current_user.get_id()
    logout_user()
    flash('You logout', 'success')
    os.remove(f'uploads/{id}.png')
    return redirect(url_for('login'))


@app.route("/youtube", methods=['GET', 'POST'])
def youtube():  # для создания видоса с ютуба
    if request.method == 'POST':
        url = request.form.get("hrf")
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)

        if not current_user.is_authenticated:
            nick = request.form.get('nick')
            if nick == '' or nick is None:
                name = 'Пользователь'
            else:
                name = nick
        else:
            name = User.query.filter_by(id=current_user.get_id()).first().username

        if create != False and url is None:
            print(1)
            return render_template('youtube.html', user=current_user, error='not url')

        if join != False and not code:
            print(2)
            return render_template('youtube.html', user=current_user, error='not room')

        room = code
        if create != False:
            if get_video_id(url):
                room = create_name_room()
                rooms[room] = {"members": 0, "messages": [], 'url': url, 'v': 'video'}
                content = {
                    "name": 'KinBu',
                    "message": f'Имя комнаты: {room}'
                }
                rooms[room]["messages"].append(content)
                content = {
                    "name": 'KinBu',
                    "message": f'Приятного просмотра ^-^'
                }
                rooms[room]["messages"].append(content)
                session["room"] = room
                session["name"] = name
                return redirect(url_for("room", nameroom=room))
            else:
                print('3')
                return render_template('youtube.html', user=current_user, error='not url')
        elif code not in room:
            print('4')
            return render_template('youtube.html', user=current_user, error='not room')

        session["room"] = room
        session["name"] = name
        return redirect(url_for("room", nameroom=room))
    return render_template('youtube.html', user=current_user)


@app.route("/films", methods=['GET', 'POST'])
@login_required
def films():  # фильмы
    con = sqlite3.connect('instance/films.db', check_same_thread=False)
    cur = con.cursor()
    name = ""
    if request.method == 'POST':
        name = request.form.get("filmname")
    elif request.method == 'GET':
        pass
    rezult = cur.execute(f'''select * from films''').fetchall()
    return render_template('filmslist.html', movies=filter(lambda x: name.lower() in x[2].lower(), list(rezult)),
                           lenmovies=len(list(filter(lambda x: name.lower() in x[2].lower(), list(rezult)))))


@app.route("/movie/<id>", methods=['GET', 'POST'])
@login_required
def films_info(id):  # инфа фильмы
    if request.method == 'POST':
        con = sqlite3.connect('instance/films.db', check_same_thread=False)
        cur = con.cursor()
        rezult = cur.execute(f'''select * from films where id == {str(id)}''').fetchone()
        name = User.query.filter_by(id=current_user.get_id()).first().username
        url = rezult[5]
        room = create_name_room()
        rooms[room] = {"members": 0, "messages": [], 'url': url, 'v': 'film'}
        content = {
            "name": 'KinBu',
            "message": f'Имя комнаты: {room}'
        }
        rooms[room]["messages"].append(content)
        content = {
            "name": 'KinBu',
            "message": f'Приятного просмотра ^-^'
        }
        rooms[room]["messages"].append(content)
        session["room"] = room
        session["name"] = name
        return redirect(url_for("room", nameroom=room))
    con = sqlite3.connect('instance/films.db', check_same_thread=False)
    cur = con.cursor()
    rezult = cur.execute(f'''select * from films where id == {str(id)}''').fetchone()
    return render_template('info_film.html', movie=rezult)


@app.route("/room/<nameroom>", methods=['GET', 'POST'])
def room(nameroom):  # room page для фильмов и видео с ютуба

    if current_user.is_authenticated:
        session["room"] = nameroom
        session["name"] = User.query.filter_by(id=current_user.get_id()).first().username

    if nameroom is None or session.get("name") is None or nameroom not in rooms:
        print(session)
        return render_template('error.html', error='not_room')

    print(rooms[nameroom])
    if rooms[nameroom]["v"] == 'film':
        return render_template("roomfilm.html", code=nameroom,
                               url=rooms[nameroom]["url"], messages=rooms[nameroom]["messages"])
    return render_template("roomyoutube.html", code=nameroom,
                           url=get_video_id(rooms[nameroom]["url"]), messages=rooms[nameroom]["messages"])


@socketio.on("message")
def message(data):
    room = session.get("room")
    if room not in rooms:
        return

    content = {
        "name": session.get("name"),
        "message": data["data"]
    }
    send(content, to=room)
    rooms[room]["messages"].append(content)


@socketio.on('play_video')
def on_play_video():
    room = session.get("room")
    name = session.get("name")
    if room not in rooms:
        return
    emit('play_video', broadcast=False, to=room)


@socketio.on('pause_video')
def on_stop_video():
    room = session.get("room")
    name = session.get("name")
    if room not in rooms:
        return
    emit('pause_video', broadcast=False, to=room)


@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = session.get("name")
    if not room or not name:
        return
    if room not in rooms:
        leave_room(room)
        return

    join_room(room)
    send({"name": name, "message": "Присоединился/ась к комнате."}, to=room)
    rooms[room]["members"] += 1
    print(f"{name} joined room {room}")


@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]

    send({"name": name, "message": "Покинул/а комнату"}, to=room)
    print(f"{name} has left the room {room}")


if __name__ == '__main__':
    socketio.run(app, debug=True)
