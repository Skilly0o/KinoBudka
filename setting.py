from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SECRET_KEY'] = 'SDK234LFJ45Ssl546di453ujckld23cs'
db = SQLAlchemy(app)

# для создания бд
def create_db():
    with app.app_context():
        db.create_all()

