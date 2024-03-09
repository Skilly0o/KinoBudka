from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from flask_mail import Mail

app = Flask(__name__)
load_dotenv()

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SECRET_KEY'] = 'SDK234LFJ45Ssl546di453ujckld23cs'

app.config['MAIL_SERVER'] = 'smtp.yandex.ru'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'vanekbadanin'
app.config['MAIL_PASSWORD'] = 'xxwchkyomvjnqgzd'
app.config['MAIL_DEFAULT_SENDER'] = 'vanekbadanin@yandex.ru'
mail = Mail(app)
db = SQLAlchemy(app)

# для создания бд
def create_db():
    with app.app_context():
        db.create_all()

