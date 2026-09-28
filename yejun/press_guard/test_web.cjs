// 실제 app.js의 차트 함수를 VM에서 실행한다. 제품 파일에는 테스트용 전역을 추가하지 않는다.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const elements = new Map();
function element() { return { innerHTML:'', textContent:'', value:1, style:{}, disabled:false, clientWidth:600,
  listeners:{}, addEventListener(k,f){this.listeners[k]=f;}, classList:{toggle(){}},
  querySelector(){return this.svg ||= element();}, querySelectorAll(){return [];},
  getBoundingClientRect(){return {left:0,width:600};} }; }
const document = {getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},
  querySelectorAll(){return [];}, createElement:element, body:{appendChild(){}}};
const context={document,window:{addEventListener(){},innerWidth:1200},setTimeout,clearTimeout,setInterval,clearInterval};
let code=fs.readFileSync(__dirname+'/web/app.js','utf8');
code=code.replace('  start();','  globalThis.subject={lineChart,state,renderDetail,numberOrNaN,filteredIncidents,levelNow,renderQueue,renderLevelKpis,outcomeOf,saveOutcome,caseRows,probText};');
vm.runInNewContext(code,context);
const {lineChart,state,renderDetail,numberOrNaN,filteredIncidents,levelNow,renderQueue,renderLevelKpis,outcomeOf,saveOutcome,caseRows,probText}=context.subject;
assert(Number.isNaN(numberOrNaN(null)));
const box=element(), series=[{key:'a',name:'A',color:'#333',dash:''}];
const rows=[{a:null},{a:null},{a:3}];
lineChart(box,rows,series,{domainRows:rows});
assert.match(box.innerHTML, /<path d="M588\.0,/); // 첫 두 null 관측을 0으로 그리지 않는다.
lineChart(box,[],series,{domainRows:rows});
assert.doesNotThrow(()=>box.svg.listeners.mousemove({clientX:50,clientY:20}));
const long=Array.from({length:50000},(_,i)=>({a:i,b:i+1,c:i+2}));
assert.doesNotThrow(()=>lineChart(box,long,['a','b','c'].map(key=>({...series[0],key})),{domainRows:long}));
state.selected=3; renderDetail(null);
assert.equal(state.selected,null); assert.equal(document.getElementById('replay').disabled,true);
// 사건 대기열과 모의 운용: 커서가 격상 행에 이르기 전에는 1단계로 보이고, 첫 알림 전 사건은 대기열에 없다.
const incidents=[{incident_id:1,first_row:10,level:2,escalation_row:12,priority_rank:1,evidence:'magnitude',first_timestamp:'t1',cases:2,max_probability:0.55,max_likelihood_ratio:121},
                 {incident_id:2,first_row:30,level:1,escalation_row:null,priority_rank:2,evidence:'waveform',first_timestamp:'t2',cases:1,max_probability:0.2,max_likelihood_ratio:20}];
// 평가관 04 R2-04: 같은 기록구간(record_id 0)에 건이 둘이어도 건 번호(case_uid)와 행 범위로 따로 찾는다.
const cases=[{case_uid:10,incident_id:1,record_id:0,row_from:5,row_to:9,first_row:10},{case_uid:40,incident_id:2,record_id:0,row_from:40,row_to:44,first_row:40}];
const points=Array.from({length:60},(_,i)=>({row_id:i,record_id:0}));
state.result={incidents,cases,points,split:'B',alpha:0.01,dataset:'upload',prior:0.01,lr_cap:121};
state.sim={row:11};
assert.equal(filteredIncidents().length,1); assert.equal(levelNow(incidents[0]),1);
state.sim.row=12; assert.equal(levelNow(incidents[0]),2);
state.sim.row=40; assert.equal(filteredIncidents().length,2);
state.levelFilter='2'; assert.equal(filteredIncidents().map(c=>c.incident_id).join(','),'1');
state.levelFilter='all'; state.sim=null;
renderLevelKpis(); assert.equal(document.getElementById('k-case').textContent,'1'); assert.equal(document.getElementById('k-level1').textContent,'1');
renderQueue(); assert.match(document.getElementById('queue').innerHTML,/badge l2">점검 요청/);
assert.equal(caseRows(cases[0]).map(p=>p.row_id).join(','),'5,6,7,8,9'); assert.equal(caseRows(cases[1])[0].row_id,40);
// 결과 기록은 사건마다 따로 저장된다(저장소 모의).
const mem=new Map(); context.window.localStorage={getItem:k=>mem.has(k)?mem.get(k):null,setItem:(k,v)=>mem.set(k,v)};
saveOutcome(incidents[0],{owner:'a',outcome:'이상 확인',measure:'m'});
assert.equal(outcomeOf(incidents[0]).status,'닫힘'); assert.equal(outcomeOf(incidents[1]).status,'열림');
// 우도비 상한에 닿은 확률은 상한으로 표시한다(평가관 04 R2-06).
assert.match(probText(incidents[0]),/상한/); assert.doesNotMatch(probText(incidents[1]),/상한/);
console.log('web regressions: 11 passed (null gap / empty replay hover / 50k rows / empty selection / sim visibility / escalation timing / level filter / level KPIs / case rows by uid / outcome per incident / probability cap)');
