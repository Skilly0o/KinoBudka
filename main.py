from flask import render_template, redirect, url_for, flash, request, session
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import escape

from config.user import User
from config.user_login import User_login
from setting import *
from config.mail_sender import send_email
from config.youtube import get_video_id


login_manager = LoginManager(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id): # функция загрузки пользователя
    # удалить принты в будущем
    print('load_user')
    print(user_id)
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
def hello(): # главная страница ( надо сделать отображение бд с фильмами да и обдумать каак украсить ее
    return render_template('total.html')


@app.route("/info")
def info(): # Обработка страницы с информацией  сюда можно написать инфинструкции
    return render_template('info.html')


@app.route("/login", methods=['GET', 'POST'])
def login(): # вход пользователя
    if current_user.is_authenticated: # если пользователь уже на сайте то перенаправляем его в профиль
        return redirect(url_for('profile'))
    if request.method == 'POST':
        email = request.form['email'] # берем из входа почту и по ней ищем пользователя
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, request.form['password']): # проверяем введенный пароль с паролем из базы данных
            userlogin = User_login().create(user)
            login_user(userlogin) # Если все совпало то логинем пользователя перенаправляя его в профиль
            return redirect(url_for('profile'))
    flash('Не вернные данные', 'error')
    return render_template('login.html')


@app.route("/support", methods=['GET', 'POST'])
def support(): # поддержка ( обратная связь)
    if request.method == 'POST':
        email = request.form['email']
        # !!ДОРАБОТАТЬ!!
        print(email)
        if send_email(email, 'Тест письмо', 'типикал текст'):
            return f'Done {email}'
        return 'Error'
    return render_template('support.html', user=current_user)


@app.route('/register', methods=['GET', 'POST'])
def register(): # регистрация пользователя
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        n_psw = generate_password_hash(password)
        user = User(username=name, email=email, password=n_psw) # берем из запроса данные и создаем пользователля
        try:
            db.session.add(user) # если все ок добавляем в базу данных и сохраняем
            db.session.commit() # перенапрявляя пользователя на страницу входа
            flash('You have been successfully registered!', 'success')
            return redirect(url_for('login'))
        except:
            db.session.rollback() # если чет не получилось откатываем базу данных
            flash('Something went wrong, please try again.', 'danger')

    return render_template('reg.html')


@app.route("/profile")
@login_required
def profile(): # профиль пользователя
    username = User.query.filter_by(id=current_user.get_id()).first().username
    email = User.query.filter_by(id=current_user.get_id()).first().email
    return render_template('profile.html', name=username, mail=email)


@app.route("/logout")
@login_required
def logout(): # выход пользователя
    logout_user()
    flash('You logout', 'success')
    return redirect(url_for('login'))


@app.route("/youtube", methods=['GET', 'POST'])
@login_required
def youtube(): # для создания видоса с ютуба
    if request.method == 'POST':
        url = request.form['hrf']
        nameroom = create_name_room()
        if get_video_id(url):
            session['current_url'] = url
            return redirect(url_for('room', nameRoom=nameroom))
        else:
            flash('Something went wrong, please try again.', 'danger')
    return render_template('youtube.html')


@app.route("/room/<nameRoom>", methods=['GET', 'POST'])
@login_required
def room(nameRoom):
    if request.method == 'GET':
        # Получаем переменную url из сеанса
        url = session.get('current_url')
        if url:
            print('Создана комната', nameRoom)
            print(url)
            return render_template('roomyutube.html', id=get_video_id(url))
        else:
            return render_template('youtube.html')






if __name__ == '__main__':
    app.run(debug=True)
