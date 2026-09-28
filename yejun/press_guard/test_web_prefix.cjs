// Python의 실제 접두부 추론과 브라우저의 모의 화면 집계를 대조한다. pytest에서 JSON을 stdin으로 준다.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const elements = new Map();
function element() { return {innerHTML:'',textContent:'',value:1,style:{},disabled:false,clientWidth:600,
  addEventListener(){},classList:{toggle(){}},querySelector(){return element();},querySelectorAll(){return [];}}; }
const document={getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},
  querySelectorAll(){return [];},createElement:element,body:{appendChild(){}}};
const context={document,window:{addEventListener(){}},setTimeout,clearTimeout,setInterval,clearInterval};
const code=fs.readFileSync(__dirname+'/web/app.js','utf8').replace('  start();','  globalThis.subject={state,viewNow,renderSimView};');
vm.runInNewContext(code,context);
const {state,viewNow,renderSimView}=context.subject;
state.result=data.full;
const numeric=['first_row','level','alarm_rows','observed_rows','alarm_share','peak_score','max_probability','max_likelihood_ratio','priority_rank','escalation_row','suspect_open'];
const text=['evidence','action','quality_action','operating_state'];
function time(s){
  if(!s)return null;
  let iso=s.replace(' ','T'); if(!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso))iso+='Z';
  const value=Date.parse(iso); assert(Number.isFinite(value),`invalid timestamp: ${s}`); return value;
}
for(const expected of data.prefixes){
  state.sim={row:expected.cursor};
  const view=JSON.parse(JSON.stringify(viewNow()));
  for(const [name,key,extra] of [['cases','case_uid',['row_from','row_to','min_p','record_current_rms']],['incidents','incident_id',['cases']]]){
    assert.equal(view[name].length,expected[name].length,`${expected.cursor} ${name} count`);
    for(const row of expected[name]){
      const actual=view[name].find(x=>x[key]===row[key]); assert(actual,`${expected.cursor} ${name} ${row[key]}`);
      for(const column of numeric.concat(extra)){
        if(!(column in row))continue;
        if(row[column]==null)assert.equal(actual[column],null,`${column} null`);
        else assert(Math.abs(actual[column]-row[column])<1e-8,`${expected.cursor} ${name} ${column}: ${actual[column]} != ${row[column]}`);
      }
      for(const column of text)assert.equal(actual[column],row[column],`${expected.cursor} ${name} ${column}`);
      for(const column of ['suspect_from','suspect_to'])assert.equal(time(actual[column]),time(row[column]),`${expected.cursor} ${name} ${column}`);
    }
  }
  renderSimView();
  if(expected.incidents.length){
    const visible=expected.incidents.find(x=>x.incident_id===state.selected);
    assert.equal(document.getElementById('quality-action').textContent,visible.quality_action);
  }
  assert.equal(Number(document.getElementById('k-alarm').textContent.replaceAll(',','')),expected.alarm_rows);
}
console.log(`prefix UI agrees with Python: ${data.prefixes.length} observation boundaries`);
