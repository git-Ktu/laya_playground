import json
from html.parser import HTMLParser
from fastapi.testclient import TestClient
from app.main import create_app
from app.models.requests import validate_request
from tests.test_api import FakeService

class Examples(HTMLParser):
    def __init__(self, source):
        super().__init__(); self.examples = {}; self.current = None; self.feed(source)
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'pre' and 'data-example' in attrs:
            self.current = (attrs['data-example'], attrs['data-kind']); self.examples[self.current] = ''
    def handle_data(self, data):
        if self.current: self.examples[self.current] += data
    def handle_endtag(self, tag):
        if tag == 'pre': self.current = None

def guide():
    return TestClient(create_app(FakeService()))

def test_guide_routes_and_api_docs():
    client = guide(); r = client.get('/guide')
    assert r.status_code == 200
    assert 'text/html' in r.headers['content-type']
    assert 'lang="ja"' in r.text and 'href="/"' in r.text
    assert client.get('/docs').status_code == 200
    assert client.get('/openapi.json').status_code == 200
    assert '/guide' not in client.get('/openapi.json').json()['paths']

def test_guide_public_examples_validate():
    examples = Examples(guide().get('/guide').text).examples
    names = {'製品レビュー', '通常のメール', '認証情報要求', '情報不足'}
    assert {name for name, _ in examples} == names
    mail_questions = []
    for name in names:
        state = json.loads(examples[name, 'state']); questions = json.loads(examples[name, 'questions'])
        validate_request({'state': state, 'questions': questions})
        assert {q['type'] for q in questions.values()} == {'choice', 'score', 'noul'}
        if name != '製品レビュー': mail_questions.append(questions)
    assert mail_questions[0] == mail_questions[1] == mail_questions[2]

def test_guide_sections_and_official_references():
    source = guide().get('/guide').text
    for section in ('getting-started','state','questions','choice','score','noul','results','examples','limits','api'):
        assert f'id="{section}"' in source
    for term in ('instructions','criteria','answer_confidence','切り捨て','https://github.com/NandhaKishorM/laya','https://huggingface.co/convaiinnovations/laya-multilingual'):
        assert term in source
    assert 'gmo' not in source.lower()

def test_guide_noul_confidence_distinction():
    source = guide().get('/guide').text
    assert 'Noul では「はい」「いいえ」の大きい方の確率' in source
    assert 'noul: 0.1' in source and 'answer_confidence: 0.9' in source

def test_guide_page_heading_precedes_chapter_headings():
    source = guide().get('/guide').text
    assert source.index('<h1>') < source.index('<h2')
