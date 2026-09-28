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
code=code.replace('  start();','  globalThis.subject={lineChart,state,renderDetail,numberOrNaN,filteredIncidents,levelNow,renderQueue,renderLevelKpis,outcomeOf,saveOutcome,caseRows,probText,operatingStateText,renderMonitorGain,renderEffect,viewNow,renderSimView};');
vm.runInNewContext(code,context);
const {lineChart,state,renderDetail,numberOrNaN,filteredIncidents,levelNow,renderQueue,renderLevelKpis,outcomeOf,saveOutcome,caseRows,probText,operatingStateText,renderMonitorGain,renderEffect,viewNow,renderSimView}=context.subject;
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
const cases=[{case_uid:10,incident_id:1,record_id:0,row_from:0,row_to:11,first_row:10},
 {case_uid:12,incident_id:1,record_id:1,row_from:12,row_to:19,first_row:12},
 {case_uid:30,incident_id:2,record_id:2,row_from:20,row_to:59,first_row:30}];
const points=Array.from({length:60},(_,i)=>({row_id:i,record_id:i<12?0:i<20?1:2,position:i<12?i:i<20?i-12:i-20,
 timestamp:new Date(Date.UTC(2022,0,1)+i*100).toISOString(),alert_unit:0,status:'ok',
 alarm:[10,12,30].includes(i)?1:0,incident_id:i===10||i===12?1:i===30?2:0,incident_escalation:i===12?1:0,
 reason:i===30?'waveform':'magnitude',magnitude_sensor:'AI0_Vibration',score:i===30?8:4,p_value:.008,
 operating_state:'short',record_current_rms:80,likelihood_ratio:121,anomaly_probability:.55,AI2_Current:i}));
state.result={incidents,cases,points,split:'B',alpha:0.01,dataset:'upload',prior:0.01,lr_cap:121,alert_unit_rows:50,
 quality_actions:{1:'다음 샘플 검사',2:'보류·전수 확인'},decision_actions:{vibration:'진동·부하 확인',current_shape:'전류 파형·계측 확인'}};
state.sim={row:11};
assert.equal(filteredIncidents().length,1); assert.equal(levelNow(incidents[0]),1);
state.sim.row=12; assert.equal(levelNow(incidents[0]),2);
state.sim.row=40; assert.equal(filteredIncidents().length,2);
state.levelFilter='2'; assert.equal(filteredIncidents().map(c=>c.incident_id).join(','),'1');
state.levelFilter='all'; state.sim=null;
renderLevelKpis(); assert.equal(document.getElementById('k-case').textContent,'1'); assert.equal(document.getElementById('k-level1').textContent,'1');
renderQueue(); assert.match(document.getElementById('queue').innerHTML,/badge l2">점검 요청/);
// 같은 기록구간에 건이 둘이어도 행 범위로 따로 찾는다.
assert.equal(caseRows({record_id:0,row_from:5,row_to:9}).map(p=>p.row_id).join(','),'5,6,7,8,9');
assert.equal(caseRows({record_id:0,row_from:40,row_to:44})[0].row_id,40);
// 첫 경보에는 현재 건 하나·샘플 검사만 보인다. 후행 건·격상·시각·점수는 아직 표시하지 않는다.
state.sim={row:10}; renderSimView();
assert.equal(viewNow().incidents[0].cases,1); assert.equal(viewNow().incidents[0].alarm_rows,1);
assert.equal(viewNow().incidents[0].observed_rows,11); assert.equal(viewNow().incidents[0].suspect_to,'');
assert.match(document.getElementById('quality-action').textContent,/샘플/);
assert.doesNotMatch(document.getElementById('detail-summary').innerHTML,/data-case="12"/);
assert.equal(document.getElementById('k-alarm').textContent,'1');
assert.equal(document.getElementById('replay').disabled,true);
const prefix=JSON.stringify({cases:viewNow().cases,incidents:viewNow().incidents,stats:viewNow().stats});
const originalResult=state.result;
state.result={...originalResult,points:points.map(p=>p.row_id<=10?p:{...p,alarm:1,score:999999,reason:'dynamics',incident_id:999})};
assert.equal(JSON.stringify({cases:viewNow().cases,incidents:viewNow().incidents,stats:viewNow().stats}),prefix);
state.result=originalResult; state.sim={row:12}; renderSimView();
assert.equal(viewNow().incidents[0].cases,2); assert.equal(viewNow().incidents[0].level,2);
assert.match(document.getElementById('quality-action').textContent,/전수/);
state.sim=null;
// 결과 기록은 사건마다 따로 저장된다(저장소 모의).
const mem=new Map(); context.window.localStorage={getItem:k=>mem.has(k)?mem.get(k):null,setItem:(k,v)=>mem.set(k,v)};
saveOutcome(incidents[0],{owner:'a',outcome:'이상 확인',measure:'m'});
assert.equal(outcomeOf(incidents[0]).status,'닫힘'); assert.equal(outcomeOf(incidents[1]).status,'열림');
// 우도비 상한에 닿은 확률은 상한으로 표시한다(평가관 04 R2-06).
assert.match(probText(incidents[0]),/상한/); assert.doesNotMatch(probText(incidents[1]),/상한/);
assert.doesNotMatch(probText(incidents[0]), /≥/);
// 운전 상태는 모의 운용 커서까지의 누적 통계만 쓰며 건 끝의 상태와 구별된다.
const c = {...cases[0], operating_state:'load', record_current_rms:105, first_alarm_operating_state:'short', evidence:'magnitude'};
for (const p of points) { p.operating_state = p.row_id < 8 ? 'low' : 'load'; p.record_current_rms = p.row_id < 8 ? 80 : 105; }
state.sim={row:6}; assert.match(operatingStateText(c), /저수준/); assert.doesNotMatch(operatingStateText(c), /105/);
state.sim=null; assert.match(operatingStateText(c), /부하/);
renderDetail(incidents[0], c);
assert.match(document.getElementById('detail-summary').innerHTML, /운전 상태/);
assert.match(document.getElementById('checklist').textContent, /3\/51.*0\/94/);
// 감시표는 창별 두 입력 조건의 권장 조치를 그대로 표시한다.
renderMonitorGain([{split:'B', gain:1.5, recalibration_review:true, alerted_by_window:'8/3/6',
  recommended_actions_no_change:'0:설비 점검 요청(전류 수준 이동: FM4·FM5 점검, 정상 확인이면 재보정)',
  recommended_actions_with_change:'0:재보정 검토(운전 조건 변경)', incident_level1_notifications:4, incident_level2_escalations:2}]);
const monitor = document.getElementById('monitor-gain').innerHTML;
assert.match(monitor, /변경 기록 없음/); assert.match(monitor, /FM4·FM5/); assert.match(monitor, /정상 확인/);
assert.match(monitor, /변경 기록 있음/); assert.match(monitor, /사건 알림 시작·격상/);
// 주추정만 강조하고 겹치는 폴드의 민감도 추정을 같은 색으로 강조하지 않는다.
renderEffect([{case:'중간', alert_scenario:'비중첩 폴드 추정(주추정)', estimate_role:'primary', policy:'2단계만 출동', level2_per_8h:4.2,
 post_hoc:true,evaluation_overlaps_rule_selection:false},
 {case:'중간', alert_scenario:'기존 폴드 민감도', estimate_role:'sensitivity', policy:'2단계만 출동', level2_per_8h:3.3,
 post_hoc:'True',evaluation_overlaps_rule_selection:'True'}]);
const effect = document.getElementById('effect').innerHTML;
assert.equal((effect.match(/class="highlight"/g)||[]).length, 1); assert.match(effect, /4.2건/);
assert.match(effect, /사후 규칙·선택 자료 비중첩/); assert.match(effect, /사후 규칙·선택 자료 중첩/);
assert.doesNotMatch(effect, /표본 내/);
console.log('web regressions passed: charts, incidents, causal state, probability cap, monitor actions and primary estimate');
