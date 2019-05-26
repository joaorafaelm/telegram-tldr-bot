import csv
import telebot
from io import StringIO, BytesIO
from os import environ
import dataset
import logging
import summarizer
import validators
import requests
from dragnet import extract_content
from gtts import gTTS
from datetime import datetime
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


TELEGRAM_TOKEN = environ.get('TELEGRAM_TOKEN')
DATABASE_URL = environ.get('DATABASE_URL', default='sqlite:///:memory:')


engine_config = {
    'connect_args': {'check_same_thread': False}
} if DATABASE_URL.startswith('sqlite') else {}

db = dataset.connect(DATABASE_URL, engine_kwargs=engine_config)
bot = telebot.TeleBot(TELEGRAM_TOKEN)


def read_messages(messages):
    result = []
    sio = StringIO(messages)
    reader = csv.reader(sio, delimiter=':')
    for row in reader:
        result.append(row)
    sio.close()
    return result


def write_messages(messages):
    sio = StringIO()
    writer = csv.writer(sio, delimiter=':')
    writer.writerows(messages)
    result = sio.getvalue()
    sio.close()
    return result


def get_messages(chat_id, limit=300):
    logger.info(f'fetching messages for {chat_id}')
    messages = db['messages']
    chat_messages = messages.find_one(chat_id=chat_id)
    if not chat_messages:
        return chat_messages

    messages = read_messages(chat_messages['text'])
    text = '\n'.join(t[2] for t in messages)
    chat_messages = '\n'.join(text.splitlines()[-limit:])
    return chat_messages


def get_webpage(url):
    r = requests.get(url)
    content = extract_content(r.content)
    return content


def summarize(message):
    chat_id = str(message.chat.id)
    text = re.sub(r'(^\/tldr(audio)?\s*|\s+$)', '', message.text)

    if validators.url(text):
        logger.info(f'url found {text}')
        messages = get_webpage(text)
    else:
        messages = get_messages(chat_id)

    summary = summarizer.summarize(". .", messages)
    if len(summary):
        summary = '\n'.join(summary)

    return summary


@bot.message_handler(commands=['tldr'])
def tldr(message):
    chat_id = str(message.chat.id)
    summary = summarize(message)

    logger.info(f'generating message for {chat_id}')
    bot.send_message(
        message.chat.id,
        summary or 'i need more data'
    )


@bot.message_handler(commands=['tldraudio'])
def tldraudio(message):
    chat_id = str(message.chat.id)
    logger.info(f'generating audio message for {chat_id}')

    summary = summarize(message)

    if summary:
        title = datetime.now().strftime(r'tldr_%Y-%m-%d_%H:%M.mp3')
        audio = BytesIO()
        tts = gTTS(summary)
        tts.write_to_fp(audio)
        bot.send_audio(message.chat.id, audio.getvalue(), title=title)
        audio.close()
    else:
        bot.send_message(message.chat.id, 'i need more data')


@bot.message_handler(content_types=['text'])
def messages(message):
    if message.text.startswith('/'):
        return
    messages = db['messages']
    chat_id = str(message.chat.id)
    user_id = str(message.from_user.id)
    username = message.from_user.username
    chat_messages = messages.find_one(chat_id=chat_id) or {}
    message_text = read_messages(chat_messages.get('text', ''))
    message_text.append([user_id, username, message.text])
    message_text = write_messages(message_text)
    messages.upsert({
        'chat_id': chat_id,
        'text': message_text,
    }, ['chat_id'])

    logger.info(f'saving message from user={user_id}, username={username}, chat_id={chat_id}')


if __name__ == '__main__':
    bot.polling(none_stop=True)
