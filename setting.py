from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from flask_mail import Mail
import random
import string

# КОНФИГИ САЙТА КОНСТАНТЫ

app = Flask(__name__)
load_dotenv()

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db' # класс бд
app.config['SECRET_KEY'] = 'SDK234LFJ45Ssl546di453ujckld23cs' # секретный ключ

app.config['MAIL_SERVER'] = 'smtp.yandex.ru' # сервер почты для обратно связи ПОМЕНЯТЬ
app.config['MAIL_PORT'] = 465 # порт для почты
app.config['MAIL_USE_TLS'] = True # хз че эт но оно нужно
app.config['MAIL_USERNAME'] = 'vanekbadanin' # имя почты
app.config['MAIL_PASSWORD'] = 'xxwchkyomvjnqgzd' # пароль дляя сайта почты
app.config['MAIL_DEFAULT_SENDER'] = 'vanekbadanin@yandex.ru' # ящик почты ( пока что свой указал поменять надо будет)
mail = Mail(app) # создание класса для писем
db = SQLAlchemy(app) # создание класса бд

sess = {}

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
            k=5
        )
    )

