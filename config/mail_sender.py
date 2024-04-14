from flask_mail import Message
from setting import mail
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(receiver_email, subject, body):
    # Заполните эти поля вашими данными
    sender_email = "kinobudka100@gmail.com"  # gmail почта, к которой привязан пароль приложения
    password = "kinobudkaknb"  # пароль приложения (в gmail получил в разделе безопасность - пароль приложений)

    # Создание объекта сообщения
    message = MIMEMultipart()
    message['From'] = sender_email
    message['To'] = receiver_email
    message['Subject'] = subject

    # Добавление тела письма
    message.attach(MIMEText(body, 'plain'))

    # Создание объекта сессии SMTP
    session = smtplib.SMTP('smtp.kinobudka100@gmail.com', 587)  # Укажите здесь свой SMTP сервер
    session.starttls()  # Активация шифрования
    session.login(sender_email, password)  # Авторизация на сервере

    # Отправка сообщения
    session.sendmail(sender_email, receiver_email, message.as_string())
    session.quit()

    print("Email sent successfully.")