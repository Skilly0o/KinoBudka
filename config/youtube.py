from pytube import YouTube

def get_video_id(url):
    try:
        video_url = url # Создаем объект YouTube с помощью ссылки на видео
        yt = YouTube(video_url) # Получаем идентификатор видео
        video_id = yt.video_id
        return video_id
    except Exception as er:
        print(er)
        return False