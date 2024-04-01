from flask import render_template, redirect, url_for, flash, request, session
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
from flask_socketio import *
from markupsafe import escape
from werkzeug.security import generate_password_hash, check_password_hash

from config.mail_sender import send_email
from config.user import User
from config.user_login import User_login
from config.youtube import get_video_id
from setting import *

login_manager = LoginManager(app)
login_manager.login_view = 'login'
socketio = SocketIO()
socketio.init_app(app)


@login_manager.user_loader
def load_user(user_id):  # функция загрузки пользователя
    # удалить принты в будущем
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
    flash('Не вернные данные', 'error')
    return render_template('login.html')


@app.route("/support", methods=['GET', 'POST'])
def support():  # поддержка ( обратная связь)
    if request.method == 'POST':
        email = request.form['email']
        # !!ДОРАБОТАТЬ!!
        print(email)
        if send_email(email, 'Тест письмо', 'типикал текст'):
            return f'Done {email}'
        return 'Error'
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
@login_required
def youtube():  # для создания видоса с ютуба
    if request.method == 'POST':
        url = request.form['hrf']
        nameroom = create_name_room()
        if get_video_id(url):
            rooms[nameroom] = {"members": [], "messages": [], 'url': url}
            session["room"] = nameroom
            print('done')
            return redirect(url_for('join_room', nameRoom=nameroom))
        else:
            flash('Something went wrong, please try again.', 'danger')
    return render_template('youtube.html')


@app.route("/films", methods=['GET', 'POST'])
@login_required
def films():  # для просмотра фильмов
    return render_template('videoplayer.html')


@app.route("/room/<nameRoom>", methods=['GET', 'POST'])
@login_required
def join_room(nameRoom):  # room page
    session["room"] = nameRoom
    if nameRoom in rooms:
        url = rooms[nameRoom]['url']
        return render_template('roomyoutube.html', id=get_video_id(url), messages=rooms[nameRoom]["messages"])
    else:
        error = 'not_room'
        return render_template('error.html', error=error)


@socketio.on("message")
def message(data):
    room = session.get("room")
    name = User.query.filter_by(id=current_user.get_id()).first().username
    if room not in rooms:
        return

    content = {
        "name": name,
        "message": data["data"]
    }
    send(content, to=room)
    rooms[room]["messages"].append(content)
    print(f"{name} said: {data['data']}")


@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = User.query.filter_by(id=current_user.get_id()).first().username
    if not room or not name:
        return 404
    if room not in rooms:
        leave_room(room)
        return

    join_room(room)
    send({"name": name, "message": "has entered the room"}, to=room)
    rooms[room]['members'].append(User.query.filter_by(id=current_user.get_id()).first().username)
    print(rooms[room])
    print(f"{name} joined room {room}")


@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = User.query.filter_by(id=current_user.get_id()).first().username
    leave_room(room)

    if room in rooms:
        rooms[room]['members'].remove(name)
        if len(rooms[room]["members"]) <= 0:
            del rooms[room]

    send({"name": name, "message": "has left the room"}, to=room)
    print(rooms[room])
    print(f"{name} has left the room {room}")


if __name__ == '__main__':
    socketio.run(app, debug=True)
