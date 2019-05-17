import telebot
from os import environ
import dataset
import logging
from summarizer import summarize
import validators
import requests
from dragnet import extract_content

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


TELEGRAM_TOKEN = environ.get('TELEGRAM_TOKEN')
DATABASE_URL = environ.get('DATABASE_URL', default='sqlite:///:memory:')


engine_config = {
    'connect_args': {'check_same_thread': False}
} if DATABASE_URL.startswith('sqlite') else {}

db = dataset.connect(DATABASE_URL, engine_kwargs=engine_config)
bot = telebot.TeleBot(TELEGRAM_TOKEN)


def get_messages(chat_id, limit=300):
    logger.info(f'fetching messages for {chat_id}')
    messages = db['messages']
    chat_messages = messages.find_one(chat_id=chat_id)
    if chat_messages:
        text = chat_messages['text']
        chat_messages = '\n'.join(text.splitlines()[-limit:])
    return chat_messages


def get_webpage(url):
    r = requests.get(url)
    content = extract_content(r.content)
    return content


@bot.message_handler(commands=['tldr'])
def tldr(message):
    chat_id = str(message.chat.id)
    text = message.text.replace('/tldr', '').strip()

    if validators.url(text):
        logger.info(f'url found {text}')
        messages = get_webpage(text)
    else:
        messages = get_messages(chat_id)

    summary = summarize(". .", messages)
    if len(summary):
        summary = '\n'.join(summary)

    logger.info(f'generating message for {chat_id}')
    bot.send_message(
        message.chat.id,
        summary or 'i need more data'
    )


@bot.message_handler(func=lambda m: True)
def messages(message):
    if message.text.startswith('/'):
        return
    messages = db['messages']
    chat_id = str(message.chat.id)
    chat_messages = messages.find_one(chat_id=chat_id) or {}
    messages.upsert({
        'chat_id': chat_id,
        'text': '\n'.join([chat_messages.get('text', ''), message.text])
    }, ['chat_id'])

    logger.info(f'saving message from {chat_id}')


if __name__ == '__main__':
    bot.polling(none_stop=True)
