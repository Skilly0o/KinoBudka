from flask_mail import Message
from setting import mail


def send_email(recipient, subject, body): # функция отправки письма !!!ДОРБОТАТЬ!!!
    msg = Message(subject, recipients=[recipient])
    msg.body = body
    mail.send(msg)
    return True