class User_login():  # Класс залогиненого пользователя
    def fromDB(self, user_id, db): # взятие пользователя из бд
        self.__user = db.query.filter_by(id=user_id).first()
        return self

    def create(self, user): # создание пользователя
        self.__user = user
        return self

    @property
    def is_authenticated(self): # проверка на регистрацию пользователя
        return True

    @property
    def is_active(self): # проверка на активность пользователя
        return True

    @property
    def is_anonymous(self): # проврка на гостя и пользователя
        return False

    def get_id(self): # получение id пользователя
        return str(self.__user.id)

    @property
    def username(self): # имя пользователя
        return self.__user.username

    @property
    def role(self): # роль пользователя на сайте (user / admin)
        return self.__user.role
