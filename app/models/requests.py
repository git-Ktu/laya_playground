"""Strict Playground validation, shared by single and batch inference."""
from copy import deepcopy

MODEL = 'multilingual'
MAX_LEN = 8192


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_state(state):
    if _text(state) or isinstance(state, (dict, list)) and bool(state):
        return state
    raise ValueError('state must be a nonempty string, JSON object, or array')


def validate_request(body: dict, *, batch: bool = False) -> dict:
    if not isinstance(body, dict):
        raise ValueError('request must be an object')
    if body.get('model', MODEL) != MODEL:
        raise ValueError('model must be multilingual')
    if type(body.get('max_len', MAX_LEN)) is not int or body.get('max_len', MAX_LEN) != MAX_LEN:
        raise ValueError('max_len must be 8192')
    if batch:
        states = body.get('states')
        if not isinstance(states, list) or not states:
            raise ValueError('states must be a nonempty array')
        for state in states:
            validate_state(state)
    else:
        validate_state(body.get('state'))
    questions = body.get('questions')
    if not isinstance(questions, dict) or not questions:
        raise ValueError('questions must be a nonempty object')
    for name, question in questions.items():
        if not _text(name) or not isinstance(question, dict):
            raise ValueError('question names must be nonempty strings and definitions objects')
        kind = question.get('type')
        if kind not in ('choice', 'score', 'noul') or not _text(question.get('instructions')):
            raise ValueError('question requires choice/score/noul type and nonempty instructions')
        criteria = question.get('criteria')
        if kind == 'choice' and (not isinstance(criteria, dict) or not criteria or
                                 not all(_text(k) and _text(v) for k, v in criteria.items())):
            raise ValueError('choice criteria must be a nonempty string-to-string object')
        if kind == 'score' and (not isinstance(criteria, list) or len(criteria) < 2 or
                                not all(_text(v) for v in criteria)):
            raise ValueError('score criteria must contain at least two nonempty strings')
    result = deepcopy(body)
    result.update(model=MODEL, max_len=MAX_LEN)
    return result
