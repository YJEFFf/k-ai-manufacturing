const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const guard = path.resolve(__dirname, '../../../../press_guard');
const elements = new Map();
function element() { return { innerHTML:'', textContent:'', value:1, style:{}, disabled:false, clientWidth:600,
  addEventListener(){}, classList:{toggle(){}}, querySelector(){return this.svg ||= element();}, querySelectorAll(){return [];} }; }
const document = {getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},
  querySelectorAll(){return [];}, querySelector(){return null;}, createElement:element, body:{appendChild(){}}};
const context={document,window:{addEventListener(){},innerWidth:1200},setTimeout,clearTimeout,setInterval,clearInterval};
let code=fs.readFileSync(path.join(guard, 'web/app.js'),'utf8');
code=code.replace('  start();','  globalThis.subject={state,viewNow};');
vm.runInNewContext(code,context);
const {state,viewNow}=context.subject;
const items=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const common=['first_row','first_timestamp','level','evidence','evidence_count','alarm_rows','observed_rows','alarm_share',
              'peak_score','action','quality_action','priority_rank','suspect_from','suspect_to','suspect_open'];
const caseCols=['record_id','row_from','row_to','operating_state','first_alarm_operating_state','record_current_rms','min_p'];
const incidentCols=['cases','case_uids','records'];
const parseTime = s => Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(s) ? s.replace(' ','T') : s.replace(' ','T')+'Z');
const same=(a,b,key)=>{
  if (a == null && b == null) return true;
  if (key === 'first_timestamp' || key.startsWith('suspect_') && typeof a === 'string') return a === b || a && b && parseTime(a) === parseTime(b);
  if (typeof a === 'number' && typeof b === 'number') return Math.abs(a-b) <= 1e-8 * Math.max(1,Math.abs(a),Math.abs(b));
  return a === b;
};
const results=[], failures=[];
for(const item of items){
  state.result=item.response; state.overview={};
  for(const expected of item.expected){
    state.sim={row:expected.cursor};
    const actual=viewNow();
    for(const kind of ['cases','incidents']){
      const key=kind==='cases'?'case_uid':'incident_id';
      const cols=[key,...common,...(kind==='cases'?caseCols:incidentCols)];
      if(actual[kind].length !== expected[kind].length) failures.push({name:item.name,cursor:expected.cursor,kind,key:'length',actual:actual[kind].length,expected:expected[kind].length});
      for(const want of expected[kind]){
        const got=actual[kind].find(r=>r[key]===want[key]);
        if(!got){failures.push({name:item.name,cursor:expected.cursor,kind,key,expected:want[key],actual:'missing'});continue;}
        for(const col of cols) if(!same(got[col],want[col],col)) failures.push({name:item.name,cursor:expected.cursor,kind,id:want[key],column:col,actual:got[col],expected:want[col]});
      }
    }
  }
  results.push({name:item.name,prefixes:item.expected.length});
}
const result={ok:failures.length===0,scenarios:results,prefixes:results.reduce((s,r)=>s+r.prefixes,0),failures};
fs.writeFileSync(path.join(__dirname,'judge04_prefix_regression.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify(result,null,2));
process.exit(result.ok?0:1);
