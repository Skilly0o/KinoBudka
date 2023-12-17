from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, login_required, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from user_login import User_login

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SECRET_KEY'] = 'SDK234LFJ45Ssl546di453ujckld23cs'
db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'



class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

    def __repr__(self):
        return '<User %r>' % self.username



def create_db():
    with app.app_context():
        db.create_all()

#Памятка Выше тех часть в ней не писать страницы и обработки!


@login_manager.user_loader
def load_user(user_id):
    print('load_user')
    print(user_id)
    return User_login().fromDB(user_id, User)

@app.route("/")
def hello():
    return render_template('total.html')


@app.route("/info")
def info():
    return render_template('info.html')


@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, request.form['password']):
            userlogin = User_login().create(user)
            login_user(userlogin)
            return redirect(url_for('profile'))
    flash('Не вернные данные', 'error')
    return render_template('login.html')


@app.route("/support")
def support():
    return render_template('support.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        n_psw = generate_password_hash(password)
        user = User(username=name, email=email, password=n_psw)
        try:
            db.session.add(user)
            db.session.commit()
            flash('You have been successfully registered!', 'success')
            return redirect(url_for('login'))
        except:
            db.session.rollback()
            flash('Something went wrong, please try again.', 'danger')

    return render_template('reg.html')


@app.route("/profile")
@login_required
def profile():
    username = User.query.filter_by(id=current_user.get_id()).first().username
    email = User.query.filter_by(id=current_user.get_id()).first().email
    return render_template('profile.html',  name=username, mail=email)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash('You logout', 'success')
    return redirect(url_for('login'))


@app.route("/newroom")
@login_required
def new_room():
    return current_user.get_id()


# ниже херь которая самая важная ее надо написать это фика сайта совместный просмотр :Д
@app.route('/v/')
def videoplayer():
    if not request.args.get('/video/kafka.mp4'): return redirect('/')
    return render_template('videoplayer.html', url=request.args.get('url'))


if __name__ == '__main__':
    create_db()
    app.run(debug=True)



