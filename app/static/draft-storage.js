'use strict';
// Validate only the UI shape. Unfinished text and JSON are valid drafts.
window.LayaDraft = (() => {
 const key = 'laya-playground:draft:v1';
 const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
 const text = value => typeof value === 'string';
 function valid(value) {
  return object(value) && value.schemaVersion === 1 && ['text','json'].includes(value.mode)
   && text(value.stateRaw) && typeof value.structuredState === 'boolean'
   && Array.isArray(value.questions) && value.questions.every(q => object(q)
    && text(q.name) && ['choice','score','noul'].includes(q.type) && text(q.instructions)
    && Array.isArray(q.criteria) && q.criteria.every(row => Array.isArray(row)
     && row.length === 2 && row.every(text)))
   && text(value.stateJsonRaw) && text(value.questionsJsonRaw) && text(value.origin)
   && typeof value.requestOpen === 'boolean' && Number.isFinite(value.scrollY) && value.scrollY >= 0;
 }
 return {
  read() {
   let raw;
   try { raw = sessionStorage.getItem(key); } catch { return {status:'unavailable'}; }
   if (raw === null) return {status:'empty'};
   try { const draft = JSON.parse(raw); return valid(draft) ? {status:'ok',draft} : {status:'invalid'}; }
   catch { return {status:'invalid'}; }
  },
  write(snapshot) {
   try { if (!valid(snapshot)) return false; sessionStorage.setItem(key,JSON.stringify(snapshot)); return true; }
   catch { return false; }
  }
 };
})();
