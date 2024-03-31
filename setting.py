from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from dotenv import load_dotenv

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

# для создания бд, если надо создать базу данных просто вызвать эту функцию перед запуском сайта
def create_db():
    with app.app_context():
        db.create_all()

