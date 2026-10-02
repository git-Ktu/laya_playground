from copy import deepcopy
import pytest
from app.models.requests import validate_request

QUESTIONS = {'判定': {'type': 'choice', 'instructions': '選ぶ', 'criteria': {'yes': 'はい'}}}

@pytest.mark.parametrize('changes', [
    {'state': ' '}, {'state': {}}, {'state': []}, {'state': None}, {'state': 4},
    {'questions': {}}, {'questions': {' ': QUESTIONS['判定']}},
    {'questions': {'q': {'type': 'invalid', 'instructions': 'x'}}},
    {'questions': {'q': {'type': 'noul', 'instructions': ' '}}},
    {'questions': {'q': {'type': 'choice', 'instructions': 'x'}}},
    {'questions': {'q': {'type': 'choice', 'instructions': 'x', 'criteria': {'a': ''}}}},
    {'questions': {'q': {'type': 'score', 'instructions': 'x'}}},
    {'questions': {'q': {'type': 'score', 'instructions': 'x', 'criteria': ['one']}}},
    {'model': 'base'}, {'max_len': 4096}, {'max_len': 8192.0},
])
def test_rejects_invalid_inputs(changes):
    body = {'state': '日本語', 'questions': deepcopy(QUESTIONS)} | changes
    with pytest.raises(ValueError):
        validate_request(body)

@pytest.mark.parametrize('state', ['日本語', {'名前': '太郎'}, ['日本語']])
def test_valid_inputs_and_fixed_defaults(state):
    result = validate_request({'state': state, 'questions': QUESTIONS})
    assert result == {'state': state, 'questions': QUESTIONS, 'model': 'multilingual', 'max_len': 8192}

@pytest.mark.parametrize('states', [[], ['ok', ' '], None, 'text'])
def test_invalid_batch(states):
    with pytest.raises(ValueError):
        validate_request({'states': states, 'questions': QUESTIONS}, batch=True)

def test_valid_score_noul_batch():
    questions = {'s': {'type': 'score', 'instructions': '評価', 'criteria': ['低い', '高い']},
                 'n': {'type': 'noul', 'instructions': '抽出'}}
    assert validate_request({'states': ['日本語'], 'questions': questions}, batch=True)['max_len'] == 8192
