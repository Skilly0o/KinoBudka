from setting import db


class Films(db.Model): # класс фильмов
    __bind_key__ = 'films_db'
    collection_id = db.Column(db.String(80), primary_key=True)
    id = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    genre = db.Column(db.String(120), nullable=False)
    date = db.Column(db.String(120), nullable=False)
    url = db.Column(db.String(120), nullable=False)
    poster = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(120), nullable=False)

