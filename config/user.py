from setting import db


class User(db.Model): # класс пользователя
    __bind_key__ = 'user_db'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(120), nullable=False, default='user')
    avatar = db.Column(db.BLOB, nullable=False, default='')

    def __repr__(self):
        return '<User %r>' % self.username
