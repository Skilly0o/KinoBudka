import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def send_email(sender_email, subject, body):
    # Заполните эти поля вашими данными
    receiver_email = "kinobudka100@gmail.com"  # gmail почта, к которой привязан пароль приложения
    password = "eyzv kzfn gdtx uayj"  # пароль приложения (в gmail получил в разделе безопасность - пароль приложений)

    # Создание объекта сообщения
    message = MIMEMultipart()
    message['From'] = sender_email
    message['To'] = 'kinobudka100@gmail.com'
    message['Subject'] = subject
    # Добавление тела письма
    message.attach(MIMEText(body, 'plain'))

    # Создание объекта сессии SMTP
    session = smtplib.SMTP('pop.gmail.com', 25)  # Укажите здесь свой SMTP сервер
    session.starttls()  # Активация шифрования
    session.login(receiver_email, password)  # Авторизация на сервере

    # Отправка сообщения
    session.sendmail(sender_email, receiver_email, message.as_string())
    session.quit()

    print("Email sent successfully.")