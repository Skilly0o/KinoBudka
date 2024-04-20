from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
import random
import string

# КОНФИГИ САЙТА КОНСТАНТЫ

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI_1'] = 'sqlite:///users.db' # класс бд
app.config['SECRET_KEY'] = 'SDK234LFJ45Ssl546di453ujckld23cs' # секретный ключ

mail = Mail(app) # создание класса для писем
db = SQLAlchemy(app) # создание класса бд


rooms = {}

# для создания бд, если надо создать базу данных просто вызвать эту функцию перед запуском сайта
def create_db():
    with app.app_context():
        db.create_all()

# функц для создания радндомной посл букв и цифр
def create_name_room():
    return ''.join(
        random.choices(
            string.ascii_letters + string.digits,
            k=10
        )
    )

