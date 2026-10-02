"""Real Chrome against injected FastAPI; no model download or inference."""
import shutil
import socket
import threading
import time

import pytest
import uvicorn
from playwright.sync_api import sync_playwright, expect
from app.main import create_app
from tests.test_api import FakeService


@pytest.fixture
def browser_page():
    if not shutil.which('google-chrome'):
        pytest.skip('google-chrome is required for the optional browser checks')
    service = FakeService()
    service.tokenize = lambda state: dict(state_tokens=len(str(state)), max_len=8192, over_limit=len(str(state)) > 8192)
    def predict(state, questions, **kwargs):
        service.calls.append((state, questions))
        return dict(model='laya-rl-agent', routing={'model':'multilingual'}, answers={name: dict(**({'type':'choice','choice':'positive'} if q['type']=='choice' else {'type':'score','score':1.7} if q['type']=='score' else {'type':'noul','noul':.8}), confidence=.8, probabilities={'positive':.8,'negative':.2} if q['type']=='choice' else {'0':.2,'1':.8} if q['type']=='score' else None, legend={'0':'低い','1':'高い'} if q['type']=='score' else None) for name,q in questions.items()}, usage=dict(state_tokens=32,input_tokens=40,output_tokens=0,truncated=True,state_tokens_dropped=2), diagnostics=service.info())
    service.predict = predict
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(service), host='127.0.0.1', port=port, log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started: break
        time.sleep(.02)
    assert server.started
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which('google-chrome'), args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1100}, permissions=['clipboard-read','clipboard-write'])
        page=context.new_page()
        page.goto(f'http://127.0.0.1:{port}')
        expect(page.locator('#model-status')).to_contain_text('利用可能')
        yield page,service
        browser.close()
    server.should_exit=True
    thread.join(5)


def test_edit_run_copy_and_mobile(browser_page, tmp_path):
    page,service=browser_page
    page.locator('#state').fill("日本語の感想。It's 快適です。")
    expect(page.locator('#state-count')).to_contain_text('state tokens')
    assert page.locator('.question').count()==3
    page.get_by_role('button',name='選択肢を追加',exact=True).click()
    page.get_by_label('質問 1 レベル 4 説明',exact=True).fill('その他')
    page.get_by_role('button',name='レベルを追加',exact=True).click()
    page.get_by_label('質問 2 レベル 4 説明',exact=True).fill('非常に満足')
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    assert len(service.calls)==1
    assert len(service.calls[0][1]['感情']['criteria'])==4
    assert len(service.calls[0][1]['満足度']['criteria'])==4
    assert page.locator('.answer').count()==3
    expect(page.locator('#result-warning')).to_contain_text('切り捨て')
    page.locator('#raw-details summary').click()
    expect(page.locator('#raw-json')).to_contain_text('state_tokens_dropped')
    page.locator('.request summary').click()
    page.locator('#copy-json').click()
    expect(page.locator('#copy-status')).to_contain_text('JSON をコピーしました')
    copied=page.evaluate('navigator.clipboard.readText()')
    assert '日本語' in copied
    page.locator('#origin').fill('http://192.168.1.10:8000')
    page.locator('#copy-curl').click()
    expect(page.locator('#copy-status')).to_contain_text('curl をコピーしました')
    curl=page.evaluate('navigator.clipboard.readText()')
    import shlex,json
    args=shlex.split(curl)
    assert args[1]=='http://192.168.1.10:8000/v1/systemone'
    assert json.loads(args[args.index('--data-raw')+1])['state']=="日本語の感想。It's 快適です。"
    page.keyboard.press('Control+Enter')
    expect(page.locator('#result-status')).to_have_text('実行完了')
    page.wait_for_function('document.querySelector("#answers").getAttribute("aria-busy") === "false"')
    assert len(service.calls)==2
    path = tmp_path
    page.screenshot(path=str(path/'desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(path/'mobile.png'),full_page=True)
    # Artifacts must belong to this fresh pytest directory, even outside a checkout.
    assert (tmp_path / 'desktop.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    assert (tmp_path / 'mobile.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


def test_validation_token_limits_and_api_errors(browser_page):
    page,_=browser_page
    page.locator('#state-format').select_option('json')
    page.locator('#state-json').fill('{bad')
    page.keyboard.press('Control+Enter')
    expect(page.locator('#state-json-error')).to_contain_text('JSON の構文')
    page.locator('#state-json').fill('{"レビュー":"良い"}')
    page.locator('#state-format').select_option('text')
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    page.locator('.question').nth(1).get_by_label('質問名',exact=True).fill('感情')
    page.keyboard.press('Control+Enter')
    expect(page.locator('#error')).to_contain_text('質問名が重複')
    page.locator('.question').nth(1).get_by_label('質問名',exact=True).fill('満足度')
    page.get_by_label('質問 1 選択肢 2 key',exact=True).fill('positive')
    page.keyboard.press('Control+Enter')
    expect(page.locator('#error')).to_contain_text('key が重複')
    page.get_by_label('質問 1 選択肢 2 key',exact=True).fill('neutral')
    page.locator('#state-format').select_option('json')
    page.locator('#state-json').fill('"通常の文章"')
    page.locator('#state-format').select_option('text')
    page.locator('#state').fill('文'*4000)
    expect(page.locator('#token-warning')).to_contain_text('4000 tokens')
    page.locator('#state').fill('文'*8193)
    expect(page.locator('#token-warning')).to_contain_text('8192 tokens を超え')
    expect(page.locator('#run')).to_be_disabled()
    page.keyboard.press('Control+Enter')
    expect(page.locator('#error')).to_contain_text('8192 tokens')
    page.locator('#state').fill('文章')
    page.route('**/v1/systemone', lambda route:route.fulfill(status=503,json={'detail':{'code':'cuda_error','message':'GPU unavailable'}}))
    page.locator('#run').click()
    expect(page.locator('#error')).to_contain_text('HTTP 503')
    expect(page.locator('#result-status')).to_have_text('実行エラー')
    page.route('**/tokenize', lambda route:route.fulfill(status=503,json={'detail':'model unavailable'}))
    page.locator('#state').fill('編集')
    expect(page.locator('#state-count')).to_contain_text('計数不能')
    page.route('**/info', lambda route:route.fulfill(json={'loaded':False,'load_error':'cuda_error'}))
    page.reload()
    expect(page.locator('#model-status')).to_contain_text('モデル利用不能')
    expect(page.locator('#run')).to_be_disabled()


def test_loading_safe_text_and_stale_tokens(browser_page):
    page,_=browser_page
    page.locator('#add-question').click()
    assert page.locator('.question').count()==4
    page.get_by_role('button',name='質問 4 を削除',exact=True).click()
    assert page.locator('.question').count()==3
    page.get_by_role('button',name='質問 1 レベル 3 を削除',exact=True).click()
    assert page.locator('.question').first.locator('.criteria-row').count()==2
    page.route('**/v1/systemone',lambda route:route.fulfill(json={'answers':{'<script>bad</script>':{'value':'<img src=x onerror=alert(1)>','probabilities':[.2,.8]}},'usage':{},'diagnostics':{'actual_device':'cpu'},'routing':{'model':'multilingual'}}))
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    expect(page.locator('#answers')).to_contain_text('<img src=x onerror=alert(1)>')
    assert page.locator('#answers img, #answers script').count()==0
    assert page.locator('.bar-fill').count()==2
    expect(page.locator('#result-meta')).to_contain_text('multilingual / device: cpu')
    # Drive two concurrent tokenizer responses in reverse order to prove the generation guard.
    page.evaluate('''() => {
      window.pendingTokens=[];
      const realFetch=window.fetch;
      window.fetch=(url,options)=>url==='/tokenize'?new Promise(resolve=>window.pendingTokens.push(resolve)):realFetch(url,options);
      document.querySelector('#state').value='古い文章';
      document.querySelector('#state').dispatchEvent(new Event('input'));
    }''')
    page.wait_for_function('window.pendingTokens.length===1')
    page.locator('#state').fill('新しい文章')
    page.wait_for_function('window.pendingTokens.length===2')
    page.evaluate("window.pendingTokens[1](new Response(JSON.stringify({state_tokens:5}),{status:200}))")
    expect(page.locator('#state-count')).to_contain_text('5 state tokens')
    page.evaluate("window.pendingTokens[0](new Response(JSON.stringify({state_tokens:9000}),{status:200}))")
    expect(page.locator('#state-count')).to_contain_text('5 state tokens')
    expect(page.locator('#run')).to_be_enabled()
    # Hold inference and press the shortcut again; only the first request may be sent.
    page.evaluate('''() => {
      const realFetch=window.fetch;
      window.inferenceCount=0;
      window.fetch=(url,options)=>url==='/v1/systemone'?(window.inferenceCount++,new Promise(resolve=>window.finishInference=resolve)):realFetch(url,options);
    }''')
    page.locator('#run').click()
    expect(page.locator('#run')).to_be_disabled()
    expect(page.locator('#run')).to_have_text('実行中…')
    page.keyboard.press('Control+Enter')
    assert page.evaluate('window.inferenceCount')==1
    page.evaluate("window.finishInference(new Response(JSON.stringify({answers:{},usage:{}}),{status:200}))")
    expect(page.locator('#result-status')).to_have_text('実行完了')


def test_native_laya_answer_fields(browser_page):
    page,_=browser_page
    page.route('**/v1/systemone',lambda route:route.fulfill(json={'answers':{'感情':{'type':'choice','choice':'positive','probabilities':{'positive':.8},'confidence':.8},'満足度':{'type':'score','score':1.7,'legend':{'0':'低い'},'probabilities':{'0':.1}},'改善要望':{'type':'noul','noul':.91,'confidence':.91}},'usage':{},'routing':{'model':'multilingual'}}))
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    expect(page.locator('.answer-value').nth(0)).to_have_text('positive')
    expect(page.locator('.answer-value').nth(1)).to_have_text('1.7')
    expect(page.locator('.answer-value').nth(2)).to_have_text('91.0%')
    expect(page.locator('.answer').nth(2)).to_contain_text('true の確率')


def test_run_token_validation_uses_captured_state(browser_page):
    page,service=browser_page
    page.evaluate('''() => {
      window.heldTokens=[];
      const realFetch=window.fetch;
      window.fetch=(url,options)=>url==='/tokenize'?new Promise(resolve=>window.heldTokens.push({resolve,state:JSON.parse(options.body).state})):realFetch(url,options);
    }''')
    page.locator('#state').fill('文'*9000)
    page.keyboard.press('Control+Enter')
    page.wait_for_function('window.heldTokens.length >= 1')
    expect(page.locator('#run')).to_be_disabled()
    page.locator('#state').fill('短い文章')
    page.wait_for_function("window.heldTokens.some(item => item.state==='短い文章')")
    page.evaluate("window.heldTokens.filter(item=>item.state==='短い文章').forEach(item=>item.resolve(new Response(JSON.stringify({state_tokens:5}),{status:200})))")
    expect(page.locator('#state-count')).to_contain_text('5 state tokens')
    page.keyboard.press('Control+Enter')
    page.evaluate("window.heldTokens.filter(item=>item.state.length===9000).forEach(item=>item.resolve(new Response(JSON.stringify({state_tokens:9000}),{status:200})))")
    expect(page.locator('#error')).to_contain_text('8192 tokens')
    expect(page.locator('#run')).to_be_enabled()
    assert service.calls==[]
    expect(page.locator('#state-count')).to_contain_text('5 state tokens')

def test_copy_on_insecure_lan_without_clipboard(browser_page):
    page, _ = browser_page
    page.evaluate("Object.defineProperty(navigator, 'clipboard', {value: undefined, configurable: true}); document.execCommand=()=>false")
    page.locator('.request summary').click()
    page.locator('#copy-curl').click()
    expect(page.locator('#copy-status')).to_contain_text('手動')
    expect(page.locator('#manual-copy')).to_be_visible()
    assert 'curl ' in page.locator('#manual-copy').input_value()
    assert page.evaluate("document.activeElement.id") == 'manual-copy'


def test_separate_json_direct_run_and_atomic_switch(browser_page):
    import json
    page, service = browser_page
    page.locator('#state-format').select_option('json')
    expect(page.locator('#state-json')).to_be_visible()
    expect(page.locator('#questions-json')).to_be_visible()
    baseline = page.locator('#state').input_value()
    defs = {'__proto__': {'type':'choice','instructions':'分類','criteria':{'constructor':'説明'}}, '評価': {'type':'score','instructions':'評価','criteria':['低','高']}, '判定': {'type':'noul','instructions':'判定'}}
    page.locator('#state-json').fill('{"本文":"日本語"}')
    page.locator('#questions-json').fill('{bad')
    page.keyboard.press('Control+Enter')
    expect(page.locator('#questions-json-error')).to_contain_text('JSON')
    assert page.locator('#state').input_value() == baseline
    page.keyboard.press('Control+Enter')
    expect(page.locator('#error')).to_contain_text('JSON')
    assert service.calls == []
    page.locator('#questions-json').fill(json.dumps(defs, ensure_ascii=False))
    page.locator('#state-format').select_option('text')
    expect(page.locator('#run')).to_be_enabled()
    page.locator('#state-format').select_option('json')
    assert json.loads(page.locator('#questions-json').input_value()) == defs
    assert page.locator('#apply-json, #discard-json, #json-status').count() == 0
    assert page.locator('#state-format').input_value() == 'json'
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    assert service.calls[-1] == ({'本文':'日本語'}, defs)
    page.locator('#state-format').select_option('text')
    assert page.locator('.question').count() == 3
    page.locator('#state').fill('{"本文":"フォーム編集"}')
    page.locator('#state-format').select_option('json')
    assert json.loads(page.locator('#state-json').input_value()) == {'本文':'フォーム編集'}
    page.locator('#state-json').fill('null')
    page.locator('#state-format').select_option('text')
    assert page.locator('#state-format').input_value() == 'json'
    assert page.locator('#state-json').input_value() == 'null'


@pytest.mark.parametrize('value', ['配送が遅れています。', ['日本語', {'a':1}]])
def test_json_state_types_and_copy_roundtrip(browser_page, value):
    import json
    page, service = browser_page
    page.locator('#state-format').select_option('json')
    page.locator('#state-json').fill(json.dumps(value, ensure_ascii=False))
    page.locator('#state-format').select_option('text')
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    assert service.calls[-1][0] == value
    page.locator('.request summary').click()
    page.locator('#copy-json').click()
    copied=json.loads(page.evaluate('navigator.clipboard.readText()'))
    page.locator('#state-format').select_option('json')
    page.locator('#state-json').fill(json.dumps(copied['state'], ensure_ascii=False))
    page.locator('#questions-json').fill(json.dumps(copied['questions'], ensure_ascii=False))
    assert json.loads(page.locator('#request-preview').text_content()) == copied


@pytest.mark.parametrize('bad', [
    {}, {'a':{'type':'invalid','instructions':'指示'}},
    {'a':{'type':'noul','instructions':''}},
    {'a':{'type':'choice','instructions':'指示','criteria':{}}},
    {'a':{'type':'choice','instructions':'指示','criteria':{'x':2}}},
    {'a':{'type':'score','instructions':'指示','criteria':['低']}},
    {'a':{'type':'score','instructions':'指示','criteria':['低',2]}},
])
def test_invalid_json_questions_preserve_both_forms(browser_page, bad):
    import json
    page,service=browser_page
    before=page.locator('#request-preview').text_content()
    page.locator('#state-format').select_option('json')
    page.locator('#state-json').fill('["変更"]')
    page.locator('#questions-json').fill(json.dumps(bad))
    page.keyboard.press('Control+Enter')
    expect(page.locator('#questions-json-error')).not_to_be_empty()
    assert page.locator('#state').input_value() == json.loads(before)['state']
    assert service.calls == []


def test_invalid_state_atomicity_json_mobile_and_token_race(browser_page, tmp_path):
    import json
    page,service=browser_page
    before=page.locator('#request-preview').text_content()
    page.locator('#state-format').select_option('json')
    page.locator('#state-json').fill('null')
    page.locator('#questions-json').fill('{"新質問":{"type":"noul","instructions":"判断"}}')
    page.keyboard.press('Control+Enter')
    expect(page.locator('#state-json-error')).not_to_be_empty()
    assert page.locator('#state').input_value() == json.loads(before)['state']
    page.evaluate('''() => {window.pendingTokens=[];const realFetch=fetch;window.fetch=(url,options)=>url==='/tokenize'?new Promise(resolve=>window.pendingTokens.push(resolve)):realFetch(url,options);}''')
    page.locator('#state-json').fill('"古い状態"')
    page.wait_for_function('window.pendingTokens.length===1')
    page.locator('#state-json').fill('["新しい状態"]')
    page.wait_for_function('window.pendingTokens.length===2')
    page.evaluate('window.pendingTokens[1](new Response(JSON.stringify({state_tokens:5}),{status:200}))')
    expect(page.locator('#state-count')).to_contain_text('5 state tokens')
    page.evaluate('window.pendingTokens[0](new Response(JSON.stringify({state_tokens:9000}),{status:200}))')
    expect(page.locator('#run')).to_be_enabled()
    expect(page.locator('#state-count')).to_contain_text('5 state tokens')
    page.screenshot(path=str(tmp_path/'json-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('#state-json').bounding_box()['y'] < page.locator('#questions-json').bounding_box()['y'] < page.locator('.results').bounding_box()['y']
    page.screenshot(path=str(tmp_path/'json-mobile.png'),full_page=True)


def test_json_latest_fields_preview_copy_and_next_run(browser_page):
    import json, shlex
    page, service = browser_page
    page.locator('#state-format').select_option('json')
    assert page.locator('#apply-json, #discard-json, #json-status').count() == 0
    defs = {'現在': {'type': 'score', 'instructions': '評価', 'criteria': ['低', '高']}}
    page.locator('#state-json').fill('{"本文":"最初"}')
    page.locator('#questions-json').fill(json.dumps(defs, ensure_ascii=False))
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    assert service.calls[-1] == ({'本文': '最初'}, defs)
    defs = {'最新': {'type': 'choice', 'instructions': '分類', 'criteria': {'a': '説明'}}}
    page.locator('#state-json').fill('["最新", {"番号":2}]')
    page.locator('#questions-json').fill(json.dumps(defs, ensure_ascii=False))
    body = {'state': ['最新', {'番号': 2}], 'questions': defs, 'model': 'multilingual', 'max_len': 8192}
    assert json.loads(page.locator('#request-preview').text_content()) == body
    page.locator('.request summary').click()
    page.locator('#copy-json').click()
    expect(page.locator('#copy-status')).to_contain_text('JSON をコピーしました')
    assert json.loads(page.evaluate('navigator.clipboard.readText()')) == body
    page.locator('#copy-curl').click()
    expect(page.locator('#copy-status')).to_contain_text('curl をコピーしました')
    args = shlex.split(page.evaluate('navigator.clipboard.readText()'))
    assert json.loads(args[args.index('--data-raw') + 1]) == body
    page.keyboard.press('Control+Enter')
    page.wait_for_function('document.querySelector("#answers").getAttribute("aria-busy") === "false"')
    assert service.calls == [({'本文': '最初'}, {'現在': {'type': 'score', 'instructions': '評価', 'criteria': ['低', '高']}}), (body['state'], defs)]


def test_json_captured_snapshot_overbudget_and_short_cache(browser_page):
    import json
    page, service = browser_page
    page.locator('#state-format').select_option('json')
    page.evaluate("""() => {
      window.heldTokens=[];const realFetch=fetch;
      window.fetch=(url,options)=>url==='/tokenize'?new Promise(resolve=>window.heldTokens.push({resolve,state:JSON.parse(options.body).state})):realFetch(url,options);
    }""")
    page.locator('#state-json').fill(json.dumps('文' * 9000))
    page.keyboard.press('Control+Enter')
    page.wait_for_function('window.heldTokens.some(item=>item.state.length===9000)')
    page.locator('#state-json').fill('"短い"')
    page.locator('#questions-json').fill('{"最新":{"type":"noul","instructions":"判断"}}')
    page.wait_for_function("window.heldTokens.some(item=>item.state==='短い')")
    page.evaluate("window.heldTokens.filter(item=>item.state==='短い').forEach(item=>item.resolve(new Response(JSON.stringify({state_tokens:2}),{status:200})))")
    expect(page.locator('#state-count')).to_contain_text('2 state tokens')
    page.evaluate("window.heldTokens.filter(item=>item.state.length===9000).forEach(item=>item.resolve(new Response(JSON.stringify({state_tokens:9000}),{status:200})))")
    expect(page.locator('#error')).to_contain_text('8192 tokens')
    expect(page.locator('#run')).to_be_enabled()
    assert service.calls == []
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    assert service.calls == [('短い', {'最新': {'type': 'noul', 'instructions': '判断'}})]


def test_json_run_captures_both_fields_before_tokenizer_wait(browser_page):
    page, service = browser_page
    page.locator('#state-format').select_option('json')
    page.evaluate("""() => {
      window.heldTokens=[];const realFetch=fetch;
      window.fetch=(url,options)=>url==='/tokenize'?new Promise(resolve=>window.heldTokens.push({resolve,state:JSON.parse(options.body).state})):realFetch(url,options);
    }""")
    page.locator('#state-json').fill('"取得した状態"')
    page.locator('#questions-json').fill('{"取得した質問":{"type":"noul","instructions":"判断"}}')
    page.keyboard.press('Control+Enter')
    page.wait_for_function("window.heldTokens.some(item=>item.state==='取得した状態')")
    page.locator('#state-json').fill('"次の状態"')
    page.locator('#questions-json').fill('{"次の質問":{"type":"noul","instructions":"次の判断"}}')
    page.evaluate("window.heldTokens.filter(item=>item.state==='取得した状態').forEach(item=>item.resolve(new Response(JSON.stringify({state_tokens:5}),{status:200})))")
    expect(page.locator('#result-status')).to_have_text('実行完了')
    assert service.calls == [('取得した状態', {'取得した質問': {'type': 'noul', 'instructions': '判断'}})]


def test_json_high_cache_reset_and_invalid_mode_switch(browser_page):
    import json
    page, service = browser_page
    page.locator('#state-format').select_option('json')
    baseline_state = page.locator('#state').input_value()
    baseline_name = page.locator('.question').first.get_by_label('質問名', exact=True).input_value()
    page.locator('#state-json').fill(json.dumps('文' * 9000))
    expect(page.locator('#run')).to_be_disabled()
    expect(page.locator('#state-count')).to_contain_text('9000 state tokens')
    page.locator('#state-json').fill('"短い"')
    expect(page.locator('#run')).to_be_enabled()
    page.locator('#questions-json').fill('{bad')
    page.locator('#state-format').select_option('text')
    assert page.locator('#state-format').input_value() == 'json'
    expect(page.locator('#questions-json-error')).to_contain_text('JSON')
    assert page.locator('#state-json').input_value() == '"短い"'
    assert page.locator('#questions-json').input_value() == '{bad'
    assert page.locator('#state').input_value() == baseline_state
    assert page.locator('.question').first.get_by_label('質問名', exact=True).input_value() == baseline_name
    assert service.calls == []


def test_guide_navigation_examples_and_copy(browser_page, tmp_path):
    import json
    page, service = browser_page
    page.locator('[href="/guide#state"]').click()
    expect(page.locator('#state-title')).to_be_visible()
    assert page.locator('#state').bounding_box()['y'] >= 70
    page.locator('[data-internal-nav][href="/"]').first.click()
    page.locator('[href="/guide#questions"]').click()
    expect(page.locator('#questions-title')).to_be_visible()
    page.locator('#guide-nav [href="#examples"]').click()
    page.locator('[data-copy-target="example-0-state"]').click()
    expect(page.locator('#guide-copy-status')).to_contain_text('コピーしました')
    copied = page.evaluate('navigator.clipboard.readText()')
    assert copied == page.locator('#example-0-state').text_content()
    json.loads(copied)
    page.locator('[data-copy-target="example-0-questions"]').click()
    expect(page.locator('#guide-copy-status')).to_contain_text('コピーしました')
    copied = page.evaluate('navigator.clipboard.readText()')
    assert copied == page.locator('#example-0-questions').text_content()
    json.loads(copied)
    page.locator('#guide-nav [href="#getting-started"]').click()
    page.screenshot(path=str(tmp_path/'guide-desktop.png'), full_page=True)
    page.screenshot(path=str(tmp_path/'guide-desktop-viewport.png'))
    assert service.calls == []
    page.locator('[data-internal-nav][href="/"]').first.click()
    page.locator('[data-internal-nav][href="/guide"]').click()
    assert page.url.endswith('/guide')


def test_guide_mobile_keyboard_and_copy_fallback(browser_page, tmp_path):
    page, service = browser_page
    page.locator('[data-internal-nav][href="/guide"]').click()
    page.set_viewport_size({'width':390,'height':844})
    expect(page.locator('#guide-nav')).not_to_be_visible()
    page.locator('#guide-menu').focus()
    page.keyboard.press('Enter')
    expect(page.locator('#guide-nav')).to_be_visible()
    page.keyboard.press('Escape')
    expect(page.locator('#guide-nav')).not_to_be_visible()
    assert page.evaluate('document.activeElement.id') == 'guide-menu'
    page.locator('#guide-menu').click()
    page.locator('#guide-nav [href="#examples"]').click()
    expect(page.locator('#guide-nav')).not_to_be_visible()
    assert page.evaluate('document.activeElement.id') == 'examples-title'
    page.evaluate("Object.defineProperty(navigator,'clipboard',{value:undefined,configurable:true});document.execCommand=()=>false")
    page.locator('[data-copy-target="example-0-state"]').click()
    expect(page.locator('#guide-copy-status')).to_contain_text('手動')
    expect(page.locator('#guide-manual-copy')).to_be_visible()
    assert page.locator('#guide-manual-copy').input_value() == page.locator('#example-0-state').text_content()
    assert page.evaluate('document.activeElement.id') == 'guide-manual-copy'
    assert page.evaluate('document.activeElement.selectionEnd-document.activeElement.selectionStart') == len(page.locator('#example-0-state').text_content())
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    expect(page.locator('#guide-manual-close')).to_be_visible()
    page.locator('#guide-manual-close').click()
    expect(page.locator('#guide-manual-container')).not_to_be_visible()
    expect(page.locator('[data-copy-target="example-0-state"]')).to_be_focused()
    page.locator('[data-copy-target="example-0-questions"]').click()
    expect(page.locator('#guide-manual-copy')).to_be_visible()
    assert page.locator('#guide-manual-copy').input_value() == page.locator('#example-0-questions').text_content()
    assert page.evaluate('document.activeElement.selectionEnd-document.activeElement.selectionStart') == len(page.locator('#example-0-questions').text_content())
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.keyboard.press('Escape')
    expect(page.locator('#guide-manual-container')).not_to_be_visible()
    expect(page.locator('[data-copy-target="example-0-questions"]')).to_be_focused()
    page.screenshot(path=str(tmp_path/'guide-mobile.png'),full_page=True)
    page.screenshot(path=str(tmp_path/'guide-mobile-viewport.png'))
    assert service.calls == []


def test_guide_scroll_and_anchor(browser_page):
    page, _ = browser_page
    origin = page.url.rstrip('/')
    page.goto(origin+'/guide')
    page.evaluate('scrollTo(0,1600)')
    page.wait_for_function('scrollY >= 1590')
    page.locator('[data-internal-nav][href="/"]').first.click()
    page.locator('[data-internal-nav][href="/guide"]').click()
    page.wait_for_function('Math.abs(scrollY-1600)<5')
    page.goto(origin+'/guide#score')
    page.wait_for_function('document.querySelector("#score").getBoundingClientRect().top >= 70 && document.querySelector("#score").getBoundingClientRect().top < 130')
    expect(page.locator('#guide-nav [href="#score"]')).to_have_attribute('aria-current','location')


def draft_roundtrip(page):
    page.locator('[data-internal-nav][href="/guide"]').click()
    page.locator('[data-internal-nav][href="/"]').first.click()
    page.reload()


def test_plain_draft_survives_guide_and_reload(browser_page):
    page, service = browser_page
    page.locator('#state').fill('書きかけ\n状態')
    first = page.locator('.question').first
    first.get_by_label('質問名', exact=True).fill('満足度')
    first.get_by_label('判断の指示', exact=True).fill('途中\n')
    first.get_by_label('質問 1 選択肢 1 key', exact=True).fill('')
    first.get_by_label('質問 1 レベル 2 説明', exact=True).fill('改訂')
    first.locator('.add-criterion').click()
    page.locator('.question').nth(2).locator('select').select_option('score')
    page.locator('.request summary').click()
    page.locator('#origin').fill('http://example.test:9000')
    draft_roundtrip(page)
    assert page.locator('#state').input_value() == '書きかけ\n状態'
    first = page.locator('.question').first
    assert first.get_by_label('質問名', exact=True).input_value() == '満足度'
    assert first.get_by_label('判断の指示', exact=True).input_value() == '途中\n'
    assert first.get_by_label('質問 1 選択肢 1 key', exact=True).input_value() == ''
    assert first.get_by_label('質問 1 レベル 2 説明', exact=True).input_value() == '改訂'
    assert first.locator('.criterion-key').evaluate_all('(nodes)=>nodes.map(node=>node.value)') == ['', 'neutral', 'negative', 'option4']
    assert first.locator('.criteria-row').count() == 4
    assert first.get_by_label('質問 1 レベル 4 説明', exact=True).input_value() == ''
    assert page.locator('.question').nth(2).locator('select').input_value() == 'score'
    assert page.locator('#origin').input_value() == 'http://example.test:9000'
    assert page.locator('.request').evaluate('(node)=>node.open')
    assert service.calls == []


def test_json_raw_draft_survives_guide_and_reload(browser_page):
    import json
    page, service = browser_page
    page.locator('#state-format').select_option('json')
    page.locator('#state-json').fill('{"before":1}')
    page.locator('#state-format').select_option('text')
    hidden_state = page.locator('#state').input_value()
    page.locator('#state-format').select_option('json')
    page.locator('#state-json').fill(' { "途中": [\n')
    page.locator('#questions-json').fill('{ "未完成": ')
    draft_roundtrip(page)
    assert page.locator('#state-format').input_value() == 'json'
    assert page.locator('#state-json').input_value() == ' { "途中": [\n'
    assert page.locator('#questions-json').input_value() == '{ "未完成": '
    saved = page.evaluate("JSON.parse(sessionStorage.getItem('laya-playground:draft:v1'))")
    assert saved['stateRaw'] == hidden_state
    assert saved['structuredState'] is True
    assert len(saved['questions']) == 3
    assert service.calls == []
    page.locator('#state-json').fill('["最新"]')
    defs = {'新': {'type':'noul', 'instructions':'判定'}}
    page.locator('#questions-json').fill(json.dumps(defs, ensure_ascii=False))
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    assert service.calls == [(['最新'], defs)]


@pytest.mark.parametrize('exception', ['QuotaExceededError', 'SecurityError'])
def test_draft_storage_unavailable_navigation(browser_page, exception, tmp_path):
    page, service = browser_page
    original_url = page.url
    page.evaluate("name=>{Storage.prototype.setItem=()=>{throw new DOMException('blocked',name)}}", exception)
    page.locator('#state').fill('保持不能でも編集')
    expect(page.locator('#draft-warning')).to_be_visible()
    page.locator('[data-internal-nav][href="/guide"]').click()
    expect(page.locator('#draft-navigation')).to_be_visible()
    page.locator('#draft-stay').click()
    assert page.url == original_url
    assert page.locator('#state').input_value() == '保持不能でも編集'
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    assert service.calls[-1][0] == '保持不能でも編集'
    page.locator('[data-internal-nav][href="/guide"]').click()
    page.screenshot(path=str(tmp_path/'draft-warning-desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(tmp_path/'draft-warning-mobile.png'))
    page.locator('#draft-leave').click()
    assert '/guide' in page.url


@pytest.mark.parametrize('corrupt', ['{broken', '{"schemaVersion":2}', '{"schemaVersion":1,"questions":[]}'])
def test_draft_invalid_saved_schema(browser_page, corrupt):
    page, service = browser_page
    import json
    page.add_init_script("sessionStorage.setItem('laya-playground:draft:v1'," + json.dumps(corrupt) + " )")
    page.reload()
    expect(page.locator('#draft-warning')).to_contain_text('復元できません')
    assert page.locator('#state-format').input_value() == 'text'
    assert page.locator('.question').count() == 3
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    assert len(service.calls) == 1


@pytest.mark.parametrize('value', [{'文章':'オブジェクト'}, ['配列', {'a':1}]])
def test_structured_state_draft_types(browser_page, value):
    import json
    page, service = browser_page
    page.locator('#state-format').select_option('json')
    page.locator('#state-json').fill(json.dumps(value, ensure_ascii=False))
    page.locator('#state-format').select_option('text')
    draft_roundtrip(page)
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    assert len(service.calls) == 1
    assert service.calls[0][0] == value
    page.locator('#state').fill('{ invalid\n')
    draft_roundtrip(page)
    assert page.locator('#state').input_value() == '{ invalid\n'
    page.keyboard.press('Control+Enter')
    expect(page.locator('#error')).to_contain_text('JSON')
    assert len(service.calls) == 1


@pytest.mark.parametrize('delayed_path', ['/tokenize', '/v1/systemone'])
def test_draft_history_and_pending_run(browser_page, delayed_path, record_property):
    page, service = browser_page
    # A real pending browser request lets the lifecycle invalidate it while Chrome navigates.
    page.evaluate('''path=>{
      const realFetch=fetch;
      window.heldRequests=[];
      window.fetch=(url,options)=>url===path?new Promise(resolve=>window.heldRequests.push({resolve,options})):realFetch(url,options);
      window.shownFromCache=false;
      addEventListener('pageshow',event=>window.shownFromCache=event.persisted);
    }''', delayed_path)
    page.locator('#state').fill('離れる直前の入力')
    page.keyboard.press('Control+Enter')
    page.wait_for_function('window.heldRequests.length > 0')
    expect(page.locator('#run')).to_have_text('実行中…')
    page.locator('[data-internal-nav][href="/guide"]').click()
    page.go_back()
    assert page.locator('#state').input_value() == '離れる直前の入力'
    expect(page.locator('#run')).to_have_text('Run')
    expect(page.locator('#run')).to_be_enabled()
    record_property('chrome_bfcache_used', page.evaluate('window.shownFromCache === true'))
    page.go_forward()
    assert '/guide' in page.url
    page.go_back()
    assert page.locator('#state').input_value() == '離れる直前の入力'
    assert service.calls == []
    # Exercise the persisted branch even if automation's Chrome disallows actual bfcache.
    page.evaluate('''path => {
      window.heldRequests=[];const realFetch=fetch;
      window.fetch=(url,options)=>url===path?new Promise(resolve=>window.heldRequests.push({resolve,options})):realFetch(url,options);
    }''', delayed_path)
    page.locator('#state').fill('復帰直前の実行入力')
    page.keyboard.press('Control+Enter')
    page.wait_for_function('window.heldRequests.length > 0')
    page.evaluate("dispatchEvent(new PageTransitionEvent('pagehide',{persisted:true}))")
    page.evaluate("dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
    page.locator('#state').fill('復帰後の最新入力')
    page.evaluate("window.heldRequests.forEach(item=>item.resolve(new Response(JSON.stringify({state_tokens:9000,answers:{old:{choice:'古い結果'}},usage:{}}),{status:200})))")
    expect(page.locator('#run')).to_have_text('Run')
    expect(page.locator('#result-status')).to_have_text('実行待ち')
    assert page.locator('#state').input_value() == '復帰後の最新入力'
    assert page.locator('#answers').text_content() == ''
    assert service.calls == []


def test_draft_storage_read_unavailable(browser_page):
    page, service = browser_page
    page.add_init_script("Storage.prototype.getItem=Storage.prototype.setItem=()=>{throw new DOMException('blocked','SecurityError')}")
    page.reload()
    expect(page.locator('#draft-warning')).to_be_visible()
    page.locator('#state').fill('保存せず実行')
    page.locator('#run').click()
    expect(page.locator('#result-status')).to_have_text('実行完了')
    assert service.calls[-1][0] == '保存せず実行'


def test_draft_question_deletions_and_scroll(browser_page):
    page, service = browser_page
    page.locator('#add-question').click()
    page.locator('.question').nth(1).get_by_role('button', name='質問 2 を削除', exact=True).click()
    first = page.locator('.question').first
    first.get_by_role('button', name='質問 1 レベル 2 を削除', exact=True).click()
    # Navigate without an automation scroll-to-link changing the user's working position.
    page.evaluate('scrollTo(0,600)')
    page.wait_for_function('scrollY === 600')
    page.evaluate('(selector)=>document.querySelector(selector).click()', '[data-internal-nav][href="/guide"]')
    page.wait_for_url('**/guide')
    page.wait_for_load_state()
    page.evaluate('(selector)=>document.querySelector(selector).click()', '[data-internal-nav][href="/"]')
    page.wait_for_function('Math.abs(scrollY-600) < 5')
    assert page.locator('.question').count() == 3
    assert page.locator('.question').nth(1).get_by_label('質問名', exact=True).input_value() == '改善要望'
    assert page.locator('.question').nth(2).get_by_label('判断の指示', exact=True).input_value() == ''
    assert first.locator('.criterion-key').evaluate_all('(nodes)=>nodes.map(node=>node.value)') == ['positive', 'negative']
    assert service.calls == []


def test_guide_generic_copy_labels(browser_page):
    page, service = browser_page
    page.locator('[data-internal-nav][href="/guide"]').click()
    expect(page.locator('[data-copy-target="api-tokenize-json"]')).to_have_text('JSON をコピー')
    assert page.locator('[data-copy-target]').filter(has_text='JSON JSON').count() == 0
    expect(page.locator('[data-copy-target="example-0-state"]')).to_have_text('状態 JSON をコピー')
    expect(page.locator('[data-copy-target="example-0-questions"]')).to_have_text('質問 JSON をコピー')


@pytest.mark.parametrize('width', [1440, 1920, 390, 320])
def test_page_navigation_position_is_stable(browser_page, width, tmp_path):
    page, _ = browser_page
    page.set_viewport_size({'width': width, 'height': 900})
    page.locator('#state').fill('位置を確認する途中の入力')

    def boxes():
        nav = page.locator('header nav[aria-label="ページ"]')
        links = nav.locator('a')
        assert links.all_text_contents() == ['Playground', 'ドキュメント']
        result = [links.nth(i).bounding_box() for i in range(2)]
        assert all(box and box['y'] >= 0 for box in result)
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        for selector in ['header h1', 'header .brand', '#model-status', 'header p:not(#model-status)']:
            for other in page.locator(selector).all():
                rect = other.bounding_box()
                for box in result:
                    assert (rect['x'] + rect['width'] <= box['x'] or box['x'] + box['width'] <= rect['x']
                            or rect['y'] + rect['height'] <= box['y'] or box['y'] + box['height'] <= rect['y'])
        return result

    def same(expected):
        actual = boxes()
        for before, after in zip(expected, actual):
            for dimension in ['x', 'y', 'width', 'height']:
                assert abs(before[dimension] - after[dimension]) <= 1, (width, dimension, before, after)

    baseline = boxes()
    page.evaluate('scrollTo(0,500)')
    page.wait_for_function('scrollY > 0')
    same(baseline)
    page.locator('header [href="/guide"]').click()
    same(baseline)
    page.evaluate('scrollTo(0,1600)')
    page.wait_for_function('scrollY >= 1590')
    same(baseline)
    page.screenshot(path=str(tmp_path / f'nav-guide-{width}.png'))
    page.locator('header nav [href="/"]').click()
    same(baseline)
    assert page.locator('#state').input_value() == '位置を確認する途中の入力'
    page.screenshot(path=str(tmp_path / f'nav-playground-{width}.png'))
    page.locator('header [href="/guide"]').click()
    page.wait_for_function('Math.abs(scrollY-1600)<5')
    same(baseline)
