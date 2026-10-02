"""Shared real inference checks; importing this module never loads a model."""
MODEL_ID = 'convaiinnovations/laya-multilingual'
STATE = '注文した商品が届かず、困っています。配送状況を確認して早急に連絡してください。'
QUESTIONS = {
    '分類': {'type': 'choice', 'instructions': '問い合わせを分類してください。', 'criteria': {'配送': '配送に関する問い合わせ', 'その他': 'その他の問い合わせ'}},
    '緊急度': {'type': 'score', 'instructions': '対応の緊急度を評価してください。', 'criteria': ['低い', '普通', '高い']},
    '要対応': {'type': 'noul', 'instructions': '担当者の対応が必要ですか。'},
}

def assert_gpu(info):
    assert info['loaded'] and info['model_id'] == MODEL_ID, info
    assert info['actual_device'].startswith('cuda'), info
    assert info['model_parameter_device'].startswith('cuda'), info
    assert info['cpu_fallback_count'] == 0, info

def assert_result(result):
    assert result['routing']['repo'] == MODEL_ID, result['routing']
    assert set(result['answers']) == set(QUESTIONS), result['answers']
    for name, answer in result['answers'].items():
        assert 0 <= answer['confidence'] <= 1, answer
        value = answer[answer['type']]
        if name == '分類': assert value in QUESTIONS[name]['criteria'], answer
        elif name == '緊急度': assert isinstance(value, (int, float)) and 0 <= value <= len(QUESTIONS[name]['criteria']) - 1, answer
        else: assert isinstance(value, (int, float)) and 0 <= value <= 1, answer
    assert isinstance(result['usage'], dict)
    assert result['diagnostics']['max_len'] == 8192
    assert_gpu(result['diagnostics'])
