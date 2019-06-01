from os import environ
from unittest import mock

import dataset
import pytest

import app

DATABASE_URL = environ.get('TEST_DATABASE_URL', default='sqlite:///:memory:')
db = dataset.connect(DATABASE_URL, engine_kwargs=app.engine_config)


@pytest.fixture
def msg():
    _msg = mock.Mock()
    _msg.chat.id = 1
    _msg.from_user.id = 1
    _msg.from_user.username = 'doc_robotnik'
    _msg.text = '/tldr'
    return _msg


@pytest.fixture(autouse=True)
def drop_messages_table():
    db['messages'].drop()


def create_message(chat_id, text):
    messages = db['messages']
    messages.upsert({'chat_id': chat_id, 'text': text}, ['chat_id'])


@pytest.mark.parametrize(
    'message,expected',
    [
        ('', []),
        ('1:doc_robotnik:emeralds', [['1', 'doc_robotnik', 'emeralds']]),
    ],
)
def test_read_messages(message, expected):
    msgs = app.read_messages(message)
    assert msgs == expected


@pytest.mark.parametrize(
    'message,expected',
    [
        ([], ''),
        ([['1', 'doc_robotnik', 'emeralds']], '1:doc_robotnik:emeralds\r\n'),
    ],
)
def test_write_messages(message, expected):
    msgs = app.write_messages(message)
    assert msgs == expected


@mock.patch('app.db', db)
def test_get_messages_no_messages():
    msgs = app.get_messages('1')
    assert not msgs


@mock.patch('app.db', db)
def test_get_messages():
    create_message('1', '1:doc_robotnik:emeralds\r\n')
    msgs = app.get_messages('1')
    assert msgs == 'emeralds'


@mock.patch('app.requests')
def test_get_webpage(m_requests):
    response = mock.Mock(content='<html></html>')
    m_requests.get.return_value = response
    content = app.get_webpage('page_url')
    assert m_requests.get.called
    assert content == ''


@mock.patch('app.db', db)
def test_summarize_history(msg):
    create_message('1', '1:doc_robotnik:emeralds\r\n')
    summary = app.summarize(msg)
    assert summary == 'emeralds'


@mock.patch('app.requests')
def test_summarize_url(m_requests, msg):
    msg.text = '/tldr http://test.io'
    response = mock.Mock(content='<html></html>')
    m_requests.get.return_value = response
    summary = app.summarize(msg)
    assert summary == []


@mock.patch('app.db', db)
@mock.patch('app.bot')
def test_tldr(m_bot, msg):
    app.tldr(msg)
    assert m_bot.send_message.called


@mock.patch('app.db', db)
@mock.patch('app.gTTS')
@mock.patch('app.bot')
def test_tldraudio(m_bot, m_gTTS, msg):
    create_message('1', '1:doc_robotnik:emeralds\r\n')
    app.tldraudio(msg)
    assert m_gTTS.called
    assert m_bot.send_audio.called


@mock.patch('app.db', db)
@mock.patch('app.gTTS')
@mock.patch('app.bot')
def test_tldraudio_no_messages(m_bot, m_gTTS, msg):
    app.tldraudio(msg)
    assert not m_gTTS.called
    assert m_bot.send_message.called


@mock.patch('app.db', db)
@mock.patch('app.bot')
def test_messages(m_bot, msg):
    msg.text = 'emeralds'
    app.messages(msg)
    messages = app.get_messages(str(msg.chat.id))
    assert messages == msg.text


@mock.patch('app.db')
@mock.patch('app.bot')
def test_messages_ignore_commands(m_bot, m_db, msg):
    app.messages(msg)
    assert not m_db.called
