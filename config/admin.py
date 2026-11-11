from flask import abort, redirect, request, url_for
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_admin.theme import Bootstrap4Theme
from flask_login import current_user

from setting import app

ADMIN_CSS = ['/static/css/admin.css']


class AdminAccessMixin:
    """Пускает в админку только вошедших пользователей с ролью admin."""

    def is_accessible(self):
        return current_user.is_authenticated and str(current_user.role).lower() == 'admin'

    def inaccessible_callback(self, name, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login', next=request.full_path.rstrip('?')))
        return abort(403)


class MyAdminIndexView(AdminAccessMixin, AdminIndexView):
    extra_css = ADMIN_CSS


# Создаем класс представления модели с ограниченным доступом
class UserModelView(AdminAccessMixin, ModelView):
    column_searchable_list = ['username']
    column_exclude_list = ['password', 'avatar']
    form_excluded_columns = ['avatar']
    extra_css = ADMIN_CSS


class FilmModelView(AdminAccessMixin, ModelView):
    column_searchable_list = ['id', 'name']
    extra_css = ADMIN_CSS


# Добавляем представления моделей в админку с настройками доступа
admin = Admin(app, name='KinBu Администрация', theme=Bootstrap4Theme(swatch='darkly'),
              index_view=MyAdminIndexView())
