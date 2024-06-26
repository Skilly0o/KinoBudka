from flask_admin import *
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user, login_required

from config.user import User
from setting import app


class MyAdminIndexView(AdminIndexView):
    # Метод для проверки доступа к админке
    @login_required
    def is_accessible(self):
        role = User.query.filter_by(id=current_user.get_id()).first().role
        # В этом примере проверяется, является ли пользователь администратором
        return str(role).lower() == 'admin'


# Создаем класс представления модели с ограниченным доступом
class UserModelView(ModelView):
    column_searchable_list = ['username']
    column_exclude_list = ['password']

    @login_required
    def is_accessible(self):
        role = User.query.filter_by(id=current_user.get_id()).first().role
        # В этом примере проверяется, является ли пользователь администратором
        return str(role).lower() == 'admin'


class FilmModelView(ModelView):
    column_searchable_list = ['id']

    @login_required
    def is_accessible(self):
        role = User.query.filter_by(id=current_user.get_id()).first().role
        # В этом примере проверяется, является ли пользователь администратором
        return str(role).lower() == 'admin'


# Добавляем представления моделей в админку с настройками доступа
admin = Admin(app, name='KinBu Администрация', template_mode='bootstrap4', index_view=MyAdminIndexView())
