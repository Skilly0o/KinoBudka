





class User_login():
    def fromDB(self, user_id, db):
        self.__user = db.query.filter_by(id=user_id).first()
        return self

    def create(self, user):
        self.__user = user
        return self

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.__user.id)
