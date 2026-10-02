'use strict';
const $ = id => document.getElementById(id);
const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if (cls) node.className = cls; return node; };
let questions = [
 {name:'感情', type:'choice', instructions:'文章全体の感情を分類してください。', criteria:[['positive','肯定的'],['neutral','中立的'],['negative','否定的']]},
 {name:'満足度', type:'score', instructions:'製品への満足度を評価してください。', criteria:[['','不満'],['','普通'],['','満足']]},
 {name:'改善要望', type:'noul', instructions:'改善してほしい点が述べられていますか。', criteria:[]}
];
let generation = 0, timer, busy = false, tokenCount = null, tokenState = null, modelReady = false;
let runGeneration = 0, pageActive = true, lifecycleController = new AbortController();
function error(message) { $('error').textContent = message; $('error').hidden = !message; }
function input(value, label, update, tag='input') {
 const wrapper = el('label', label); const field = el(tag); field.value = value;
 field.addEventListener('input', () => { update(field.value); preview(); }); wrapper.append(field); return wrapper;
}
function renderQuestions() {
 $('questions').replaceChildren();
 questions.forEach((question, index) => {
  const section = el('section', undefined, 'question'); const head = el('div', undefined, 'question-head');
  head.append(input(question.name,'質問名', value => question.name=value));
  const typeLabel = el('label','種類'); const select = el('select');
  ['choice','score','noul'].forEach(type => { const option=el('option',type[0].toUpperCase()+type.slice(1)); option.value=type; select.append(option); }); select.value=question.type;
  select.addEventListener('change', () => { question.type=select.value; question.criteria=select.value==='choice'?[['a','選択肢 A'],['b','選択肢 B']]:select.value==='score'?[['','低い'],['','高い']]:[]; renderQuestions();preview(); }); typeLabel.append(select);head.append(typeLabel);
  const remove=el('button','削除');remove.setAttribute('aria-label',`質問 ${index+1} を削除`);remove.addEventListener('click',()=>{questions.splice(index,1);renderQuestions();preview();});head.append(remove);section.append(head,input(question.instructions,'判断の指示',value=>question.instructions=value,'textarea'));
  if(question.type!=='noul') {
   const criteria=el('div');criteria.append(el('p',question.type==='choice'?'選択肢の key と説明':'評価レベル（低い順）'));
   question.criteria.forEach((criterion, rowIndex)=>{const row=el('div',undefined,'criteria-row');if(question.type==='choice'){const key=el('input');key.className='criterion-key';key.value=criterion[0];key.setAttribute('aria-label',`質問 ${index+1} 選択肢 ${rowIndex+1} key`);key.addEventListener('input',()=>{criterion[0]=key.value;preview();});row.append(key);}const description=el('input');description.value=criterion[1];description.setAttribute('aria-label',`質問 ${index+1} レベル ${rowIndex+1} 説明`);description.addEventListener('input',()=>{criterion[1]=description.value;preview();});const removeRow=el('button','削除');removeRow.setAttribute('aria-label',`質問 ${index+1} レベル ${rowIndex+1} を削除`);removeRow.addEventListener('click',()=>{question.criteria.splice(rowIndex,1);renderQuestions();preview();});row.append(description,removeRow);criteria.append(row);});
   const add=el('button',question.type==='choice'?'選択肢を追加':'レベルを追加','add-criterion');add.addEventListener('click',()=>{question.criteria.push([`option${question.criteria.length+1}`,'']);renderQuestions();preview();});criteria.append(add);section.append(criteria);
  } $('questions').append(section);
 });
}
// The visible editor supplies each request snapshot.
let structuredState = false, activeMode = 'text';
let draftInitialized = false, restoreNotice = '';
const storageWarning = 'このブラウザーでは入力を保持できません。移動前に必要な内容をコピーしてください。';
function captureDraft() {
 return {schemaVersion:1,mode:activeMode,stateRaw:$('state').value,structuredState,
  questions:questions.map(q=>({...q,criteria:q.criteria.map(row=>[...row])})),
  stateJsonRaw:$('state-json').value,questionsJsonRaw:$('questions-json').value,
  origin:$('origin').value,requestOpen:document.querySelector('.request').open,scrollY:window.scrollY};
}
function modeDisplay() {
 const json=activeMode==='json';$('state-format').value=activeMode;
 $('plain-state').hidden=json;$('questions').hidden=json;$('add-question').hidden=json;
 $('json-state').hidden=!json;$('json-questions').hidden=!json;
}
function restoreDraft(snapshot) {
 activeMode=snapshot.mode;structuredState=snapshot.structuredState;
 questions=snapshot.questions.map(q=>({...q,criteria:q.criteria.map(row=>[...row])}));
 $('state').value=snapshot.stateRaw;$('state').classList.toggle('json-source',structuredState);
 $('state-json').value=snapshot.stateJsonRaw;$('questions-json').value=snapshot.questionsJsonRaw;
 $('origin').value=snapshot.origin;document.querySelector('.request').open=snapshot.requestOpen;
 renderQuestions();modeDisplay();
}
function persistDraft() {
 if(!draftInitialized)return true;
 const saved=window.LayaDraft.write(captureDraft());
 $('draft-warning').textContent=saved?restoreNotice:storageWarning;
 $('draft-warning').hidden=!$('draft-warning').textContent;
 return saved;
}
function restoreScroll(y) {
 if(location.hash)return;
 requestAnimationFrame(()=>requestAnimationFrame(()=>window.scrollTo(0,y)));
}

const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const nonemptyText = value => typeof value === 'string' && Boolean(value.trim());
function validateState(value) {
 if(nonemptyText(value) || (value !== null && typeof value === 'object' && Object.keys(value).length)) return value;
 throw Error('状態は空でない文字列・オブジェクト・配列を入力してください。');
}
function parseJson(text) {try{return JSON.parse(text);}catch{throw Error('JSON の構文を確認してください。');}}
function state() {return validateState(activeMode==='json'?parseJson($('state-json').value):structuredState ? parseJson($('state').value) : $('state').value);}
function stateText(){return $(activeMode==='json'?'state-json':'state').value;}
function validateQuestions(entries) {
 if(!isObject(entries)||!Object.keys(entries).length)throw Error('質問は空でない辞書を入力してください。');
 for(const [name,q] of Object.entries(entries)) {
  const prefix=`質問「${name}」: `;
  if(!nonemptyText(name)||!isObject(q))throw Error(prefix+'質問名と定義を確認してください。');
  if(!['choice','score','noul'].includes(q.type))throw Error(prefix+'type は choice / score / noul を指定してください。');
  if(!nonemptyText(q.instructions))throw Error(prefix+'判断の指示 instructions を入力してください。');
  if(q.type==='choice'&&(!isObject(q.criteria)||!Object.keys(q.criteria).length||Object.entries(q.criteria).some(([k,v])=>!nonemptyText(k)||!nonemptyText(v))))throw Error(prefix+'Choice の criteria は key と説明のある空でない辞書を入力してください。');
  if(q.type==='score'&&(!Array.isArray(q.criteria)||q.criteria.length<2||q.criteria.some(v=>!nonemptyText(v))))throw Error(prefix+'Score は説明のあるレベルを 2 つ以上入力してください。');
 }
 return entries;
}
function serializeQuestions() {
 const entries=Object.create(null);
 for(const q of questions){
  if(Object.hasOwn(entries,q.name))throw Error('質問名が重複しています。別の名前に変更してください。');
  const item={type:q.type,instructions:q.instructions};
  if(q.type==='choice'){item.criteria=Object.create(null);for(const [key,description] of q.criteria){if(Object.hasOwn(item.criteria,key))throw Error('選択肢の key が重複しています。');item.criteria[key]=description;}}
  if(q.type==='score')item.criteria=q.criteria.map(c=>c[1]);
  entries[q.name]=item;
 }
 return entries;
}
function questionEntries() {return validateQuestions(serializeQuestions());}
function request() {return {...(activeMode==='json'?jsonValues():{state:state(),questions:questionEntries()}),model:'multilingual',max_len:8192};}
function syncJsonDrafts() {
 // Serialize editable forms even when incomplete, so switching modes can repair them.
 let value=structuredState?parseJson($('state').value):$('state').value;
 const entries=serializeQuestions();
 $('state-json').value=JSON.stringify(value,null,2);$('questions-json').value=JSON.stringify(entries,null,2);
}
function jsonValues() {
 const values={}, errors=[];
 for(const [id,validate] of [['state',validateState],['questions',validateQuestions]]) {
  const field=$(id+'-json');
  try {values[id]=validate(parseJson(field.value));$(id+'-json-error').textContent='';field.removeAttribute('aria-invalid');}
  catch(e){$(id+'-json-error').textContent=e.message;field.setAttribute('aria-invalid','true');errors.push(e.message);}
 }
 if(errors.length)throw Error(errors.join(' '));
 return values;
}
function jsonChanged(id) {
 $(id+'-json-error').textContent='';$(id+'-json').removeAttribute('aria-invalid');
 if(id==='state')stateChanged();else preview();
}
function populateForms({state:value,questions:entries}) {
 structuredState=typeof value!=='string';$('state').value=structuredState?JSON.stringify(value,null,2):value;$('state').classList.toggle('json-source',structuredState);
 questions=Object.entries(entries).map(([name,q])=>({name,type:q.type,instructions:q.instructions,criteria:q.type==='choice'?Object.entries(q.criteria):q.type==='score'?q.criteria.map(v=>['',v]):[]}));
 renderQuestions();
}
function switchMode() {
 const next=$('state-format').value;
 try {if(next==='json')syncJsonDrafts();else populateForms(jsonValues());}
 catch(e){error(e.message);$('state-format').value=activeMode;return;}
 activeMode=next;
 modeDisplay();
 error('');stateChanged();
}
function preview(){persistDraft();try{$('request-preview').textContent=JSON.stringify(request(),null,2);}catch(e){$('request-preview').textContent=e.message;}}
async function api(path,body,signal=lifecycleController.signal){let response;try{response=await fetch(path,body===undefined?{signal}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal});}catch{throw Error('サーバーに接続できません。接続と起動状態を確認してください。');}const data=await response.json();if(!response.ok){const detail=data.detail;throw Error(`HTTP ${response.status}: ${typeof detail==='string'?detail:JSON.stringify(detail??data)}`);}return {data,response};}
function countDisplay() {
  const tokens = tokenCount === null ? 'token 数を計数中…' : tokenCount + ' state tokens';
  $('state-count').textContent = `${Array.from(stateText()).length} 文字 / ${tokens}`;
}

async function tokenize(currentGeneration) {
  let value;
  try {
    value = state();
  } catch (e) {
    if (pageActive && currentGeneration === generation) {
      $('state-count').textContent = `${Array.from(stateText()).length} 文字 / 計数不能`;
      $('token-warning').textContent = e.message;
    }
    return;
  }
  try {
    const {data} = await api('/tokenize', {state: value});
    if (!pageActive || currentGeneration !== generation) return;
    tokenCount = data.state_tokens;
    tokenState = JSON.stringify(value);
    countDisplay();
    $('token-warning').textContent = tokenCount > 8192
      ? '8192 tokens を超えています。状態を短くしてから実行してください。'
      : tokenCount >= 4000
        ? '4000 tokens 以上です。長文では判断精度が低下する場合があります。'
        : '';
  } catch (e) {
    if (!pageActive || currentGeneration !== generation) return;
    $('state-count').textContent = `${Array.from(stateText()).length} 文字 / token 計数不能`;
    $('token-warning').textContent = e.message;
  }
  updateRun();
}

function updateRun() {
  $('run').disabled = busy || !modelReady || (tokenCount !== null && tokenCount > 8192);
}

function stateChanged() {
  generation++;
  clearTimeout(timer);
  tokenCount = null;
  tokenState = null;
  countDisplay();
  $('token-warning').textContent = '';
  updateRun();
  preview();
  timer = setTimeout(() => tokenize(generation), 350);
}

function display(value){return typeof value==='object'?JSON.stringify(value):String(value);}
function renderResult(data,response,elapsed){$('empty-result').hidden=true;$('answers').replaceChildren();for(const [name,answer] of Object.entries(data.answers??{})){const card=el('article',undefined,'answer');card.append(el('h3',name),el('p',answer.noul!==undefined?(Number(answer.noul)*100).toFixed(1)+'%':display(answer.choice??answer.score??answer.value),'answer-value'));if(answer.confidence!==undefined)card.append(el('p',`confidence: ${answer.confidence}${answer.answer_confidence!==undefined?' / answer confidence: '+answer.answer_confidence:''}`));if(answer.legend)card.append(el('p','レベル: '+Object.entries(answer.legend).map(([key,val])=>`${key}: ${display(val)}`).join(' / ')));if(answer.probabilities){for(const [key,raw] of Object.entries(answer.probabilities)){const probability=Number(raw);if(!Number.isFinite(probability))continue;const row=el('div',undefined,'probability'),bar=el('div',undefined,'bar'),fill=el('div',undefined,'bar-fill');fill.style.width=`${Math.max(0,Math.min(1,probability))*100}%`;bar.append(fill);row.append(el('span',answer.legend?.[key]??key),bar,el('span',(probability*100).toFixed(1)+'%'));card.append(row);}}if(answer.noul!==undefined)card.append(el('p','true の確率'));if(answer.probability!==undefined)card.append(el('p',`true の確率: ${(Number(answer.probability)*100).toFixed(1)}%`));$('answers').append(card);}const usage=data.usage??{},diagnostics=data.diagnostics??{};const time=response.headers.get('x-inference-time-ms');$('result-meta').textContent=`${data.routing?.model??diagnostics.model??data.model??'multilingual'} / device: ${diagnostics.actual_device??'不明'} / 推論 ${time??elapsed.toFixed(1)} ms / state ${usage.state_tokens??'不明'} tokens / input ${usage.input_tokens??'不明'} tokens / output ${usage.output_tokens??'不明'} tokens`;$('result-warning').textContent=usage.truncated||usage.state_tokens_dropped>0?`入力が切り捨てられました。省略された state tokens: ${usage.state_tokens_dropped??'不明'}。状態を短くして再実行してください。`:'';$('raw-json').textContent=JSON.stringify(data,null,2);$('raw-details').hidden=false;}
async function run() {
  if (busy || !pageActive) return;
  const currentRun = ++runGeneration, signal = lifecycleController.signal;
  const current = () => pageActive && currentRun === runGeneration;
  busy = true;
  updateRun();
  error('');
  $('run').textContent = '実行中…';
  $('result-status').textContent = '実行中…';
  $('answers').setAttribute('aria-busy', 'true');
  try {
    // The request and its validation stay together, even if the editor changes.
    const body = request();
    const capturedState = JSON.stringify(body.state);
    if (!modelReady) {
      throw Error('モデルを利用できません。サーバーのロード状態を確認してください。');
    }
    let capturedTokenCount = tokenState === capturedState ? tokenCount : null;
    if (capturedTokenCount === null) {
      const {data} = await api('/tokenize', {state: body.state}, signal);
      if (!current()) return;
      capturedTokenCount = data.state_tokens;
    }
    if (capturedTokenCount > 8192) {
      throw Error('8192 tokens を超えています。状態を短くしてください。');
    }
    const start = performance.now();
    const {data, response} = await api('/v1/systemone', body, signal);
    if (!current()) return;
    renderResult(data, response, performance.now() - start);
    $('result-status').textContent = '実行完了';
  } catch (e) {
    if (!current()) return;
    error(e.message);
    $('result-status').textContent = '実行エラー';
  } finally {
    if (!current()) return;
    busy = false;
    updateRun();
    $('run').textContent = 'Run';
    $('answers').setAttribute('aria-busy', 'false');
  }
}
function shellQuote(text){return "'"+text.replaceAll("'","'\\''")+"'";}
async function copy(kind){try{const body=request();let text=JSON.stringify(body,null,2);if(kind==='curl'){const origin=new URL($('origin').value);if(!['http:','https:'].includes(origin.protocol)||origin.username||origin.password||origin.pathname!=='/'||origin.search||origin.hash)throw Error('接続先は http(s) の origin を指定してください（パス不要）。');text=`curl ${shellQuote(origin.origin+'/v1/systemone')} \\\n  -H 'Content-Type: application/json' \\\n  --data-raw ${shellQuote(JSON.stringify(body))}`;}let copied=false;
if(navigator.clipboard?.writeText){try{await navigator.clipboard.writeText(text);copied=true;}catch{}}
let field=$('manual-copy');
if(!copied){if(!field){field=document.createElement('textarea');field.id='manual-copy';field.setAttribute('aria-label','手動コピー用テキスト');field.readOnly=true;$('copy-status').after(field);}field.hidden=false;field.value=text;field.focus();field.select();try{copied=document.execCommand('copy');}catch{}}
if(copied){if(field)field.hidden=true;$('copy-status').textContent=`${kind==='curl'?'curl':'JSON'} をコピーしました。`;}
else $('copy-status').textContent='選択したテキストを Ctrl+C / ⌘C で手動コピーしてください。';}catch(e){error(e.message);}}
$('add-question').addEventListener('click',()=>{questions.push({name:`質問${questions.length+1}`,type:'noul',instructions:'',criteria:[]});renderQuestions();preview();});$('state').addEventListener('input',stateChanged);$('state-format').addEventListener('change',switchMode);
$('state-json').addEventListener('input',()=>jsonChanged('state'));$('questions-json').addEventListener('input',()=>jsonChanged('questions'));$('run').addEventListener('click',run);document.addEventListener('keydown',event=>{if(event.ctrlKey&&event.key==='Enter'){event.preventDefault();run();}});$('copy-json').addEventListener('click',()=>copy('json'));$('copy-curl').addEventListener('click',()=>copy('curl'));$('origin').value=location.origin;$('origin-help').textContent=['localhost','127.0.0.1','[::1]'].includes(location.hostname)?'別の端末で使う curl は、localhost をサーバーの LAN IP（例: http://192.168.1.10:8000）に変更してください。':'この接続先を LAN 内の端末からも利用できます。';
const savedDraft=window.LayaDraft.read();
if(savedDraft.status==='ok')restoreDraft(savedDraft.draft);
else {renderQuestions();if(savedDraft.status==='invalid')restoreNotice='保存された入力を復元できませんでした。既定の入力で開始します。';}
draftInitialized=true;
stateChanged();
if(savedDraft.status==='ok')restoreScroll(savedDraft.draft.scrollY);
refreshInfo();
function refreshInfo() {
 const signal=lifecycleController.signal;
 modelReady=false;$('model-status').textContent='モデル情報を確認中…';updateRun();
 api('/info',undefined,signal).then(({data})=>{
  if(!pageActive || signal!==lifecycleController.signal)return;
  modelReady=Boolean(data.loaded);
  $('model-status').textContent=`multilingual / ${data.actual_device??'device 不明'} / ${modelReady?'利用可能':'モデル利用不能: '+(data.load_error??'ロード状態を確認してください')}`;
  updateRun();
 }).catch(e=>{if(!pageActive || signal!==lifecycleController.signal)return;$('model-status').textContent=e.message;updateRun();});
}

$('origin').addEventListener('input',()=>persistDraft());
document.querySelector('.request').addEventListener('toggle',()=>persistDraft());
let pendingNavigation = null;
document.addEventListener('click',event=>{
 const link=event.target.closest('[data-internal-nav]');
 if(!link || event.defaultPrevented || event.button!==0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || link.target==='_blank' || link.hasAttribute('download'))return;
 if(persistDraft())return;
 event.preventDefault();pendingNavigation=link.href;$('draft-navigation').showModal();
});
$('draft-stay').addEventListener('click',()=>{$('draft-navigation').close();pendingNavigation=null;});
$('draft-navigation').addEventListener('close',()=>{pendingNavigation=null;});
$('draft-leave').addEventListener('click',()=>{const destination=pendingNavigation;$('draft-navigation').close();if(destination)location.assign(destination);});
let returnScrollY=0;
function resetTransientView() {
 busy=false;modelReady=false;tokenCount=null;tokenState=null;
 error('');$('run').textContent='Run';$('answers').setAttribute('aria-busy','false');
 $('answers').replaceChildren();$('empty-result').hidden=false;$('result-status').textContent='実行待ち';
 $('result-meta').textContent='';$('result-warning').textContent='';$('raw-json').textContent='';$('raw-details').hidden=true;
 $('token-warning').textContent='';$('state-json-error').textContent='';$('questions-json-error').textContent='';
 $('state-json').removeAttribute('aria-invalid');$('questions-json').removeAttribute('aria-invalid');
 updateRun();
}
window.addEventListener('pagehide',()=>{
 returnScrollY=window.scrollY;persistDraft();pageActive=false;
 generation++;runGeneration++;clearTimeout(timer);lifecycleController.abort();resetTransientView();
});
window.addEventListener('pageshow',event=>{
 if(!event.persisted)return;
 pageActive=true;lifecycleController=new AbortController();resetTransientView();
 refreshInfo();stateChanged();restoreScroll(returnScrollY);
});
