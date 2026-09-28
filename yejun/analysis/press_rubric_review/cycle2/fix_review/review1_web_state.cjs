// 검토 1: 콘솔 점검 항목의 운전 상태 참고율(normalStateReference)이 첫 경보 시점의 '판정 대기'를 반영하는가.
// 사용: REVIEW_ENV=<사본의 yejun 폴더> node review1_web_state.cjs  (test_web.cjs와 같은 방식으로 app.js를 VM에서 실행)
const fs = require('node:fs'), vm = require('node:vm');
const env = process.env.REVIEW_ENV;
const elements = new Map();
function element() { return { innerHTML:'', textContent:'', value:1, style:{}, disabled:false, clientWidth:600,
  listeners:{}, addEventListener(k,f){this.listeners[k]=f;}, classList:{toggle(){}},
  querySelector(){return this.svg ||= element();}, querySelectorAll(){return [];},
  getBoundingClientRect(){return {left:0,width:600};} }; }
const document = {getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},
  querySelectorAll(){return [];}, createElement:element, body:{appendChild(){}}};
const context={document,window:{addEventListener(){},innerWidth:1200},setTimeout,clearTimeout,setInterval,clearInterval};
let code=fs.readFileSync(env+'/press_guard/web/app.js','utf8');
code=code.replace('  start();','  globalThis.subject={state,renderDetail,operatingStateText};');
vm.runInNewContext(code,context);
const {state,renderDetail,operatingStateText}=context.subject;
// 한 기록(50행): 첫 경보가 위치 3(판정 대기), 기록 끝 상태는 부하
const points=Array.from({length:50},(_,i)=>({row_id:i,record_id:0,position:i,timestamp:new Date(Date.UTC(2022,0,1)+i*100).toISOString(),
  alert_unit:0,status:'ok',alarm:i===3?1:0,incident_id:i===3?1:0,incident_escalation:0,reason:'magnitude',magnitude_sensor:'AI0_Vibration',
  score:i===3?8:1,p_value:i===3?.008:.5,operating_state:i<16?'short':'load',record_current_rms:i<16?50:120,likelihood_ratio:121,anomaly_probability:.55,AI2_Current:i}));
const inc={incident_id:1,first_row:3,level:1,escalation_row:null,priority_rank:1,evidence:'magnitude',first_timestamp:points[3].timestamp,cases:1,max_probability:.55,max_likelihood_ratio:121};
const c={case_uid:3,incident_id:1,record_id:0,row_from:0,row_to:49,first_row:3,operating_state:'load',first_alarm_operating_state:'short',record_current_rms:120,evidence:'magnitude',action:'진동·부하 확인'};
state.result={incidents:[inc],cases:[c],points,split:'B',alpha:0.01,dataset:'upload',prior:0.01,lr_cap:121,alert_unit_rows:50,quality_actions:{1:'a',2:'b'},decision_actions:{}};
state.overview={state_reference:[{alpha:0.01,value:'load',false_alarms:3,denominator:154},{alpha:0.01,value:'low',false_alarms:0,denominator:225},{alpha:0.01,value:'short',false_alarms:0,denominator:101}]};
for (const [label, sim] of [['모의 운용 커서 = 첫 경보 행(3)', {row:3}], ['사후 보기(모의 아님)', null]]) {
  state.sim = sim; renderDetail(inc, c);
  const text = document.getElementById('checklist').textContent;
  console.log(`${label}\n  운전 상태 표시: ${operatingStateText(c)}\n  '판정 대기' 안내 포함: ${/상태 판정 대기/.test(text)}\n  점검 항목 앞부분: ${text.slice(0, 170)}`);
}
