import sqlite3

from flask import render_template, redirect, url_for, flash, request, session
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
from flask_socketio import join_room, leave_room, send, SocketIO, emit
from markupsafe import escape
from werkzeug.security import generate_password_hash, check_password_hash
from googletrans import Translator

from config.mail_sender import send_email
from config.user import User
from config.user_login import User_login
from config.youtube import get_video_id
from setting import *

login_manager = LoginManager(app)
login_manager.login_view = 'login'
socketio = SocketIO(app)


@login_manager.user_loader
def load_user(user_id):  # функция загрузки пользователя
    username = User.query.filter_by(id=user_id).first().username
    session["name"] = username
    print('load_user', user_id)
    return User_login().fromDB(user_id, User)


@app.route('/set_session/<value>')
def set_session(value):
    session['value'] = value
    return 'Значение переменной value сохранено в сессии.'


@app.route('/get_session')
def get_session():
    value = session.get('value', 'Not set')
    return 'Значение переменной value в сессии: {}'.format(escape(value))


@app.route("/")
def hello():  # главная страница ( надо сделать отображение бд с фильмами да и обдумать каак украсить ее
    return render_template('total.html')


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
        subject = 'AP violation'
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
        if send_email(email, subject, body_tran.text.replace(u"\u2018", "'").replace(u"\u2019", "'")):
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
        user = User(username=name, email=email, password=n_psw)  # берем из запроса данные и создаем пользователля
        try:
            db.session.add(user)  # если все ок добавляем в базу данных и сохраняем
            db.session.commit()  # перенапрявляя пользователя на страницу входа
            flash('You have been successfully registered!', 'success')
            return redirect(url_for('login'))
        except:
            db.session.rollback()  # если чет не получилось откатываем базу данных
            flash('Something went wrong, please try again.', 'danger')

    return render_template('reg.html')


@app.route("/profile")
@login_required
def profile():  # профиль пользователя
    username = User.query.filter_by(id=current_user.get_id()).first().username
    email = User.query.filter_by(id=current_user.get_id()).first().email
    return render_template('profile.html', name=username, mail=email)


@app.route("/logout")
@login_required
def logout():  # выход пользователя
    logout_user()
    flash('You logout', 'success')
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
    con = sqlite3.connect('films.db', check_same_thread=False)
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
        con = sqlite3.connect('films.db', check_same_thread=False)
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
        session["room"] = room
        session["name"] = name
        return redirect(url_for("room", nameroom=room))
    con = sqlite3.connect('films.db', check_same_thread=False)
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
    print(session)
    if room not in rooms:
        return

    content = {
        "name": session.get("name"),
        "message": data["data"]
    }
    send(content, to=room)
    rooms[room]["messages"].append(content)
    print(f"{session.get('name')} said: {data['data']}")


@socketio.on('play_video')
def on_play_video():
    room = session.get("room")
    name = session.get("name")
    if room not in rooms:
        return
    print('Ролик запущен')
    emit('play_video', broadcast=False, to=room)


@socketio.on('pause_video')
def on_stop_video():
    room = session.get("room")
    name = session.get("name")
    if room not in rooms:
        return
    print('Ролик остановлен')
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
