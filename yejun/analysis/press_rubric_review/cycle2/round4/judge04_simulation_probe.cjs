// 실제 콘솔의 첫 경보 시점 표시를 원본 API 결과로 확인한다. 제품 소스는 수정하지 않는다.
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const guard = path.resolve(__dirname, '../../../../press_guard');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const elements = new Map();
function element() { return { innerHTML:'', textContent:'', value:1, style:{}, disabled:false, clientWidth:600,
  listeners:{}, addEventListener(k,f){this.listeners[k]=f;}, classList:{toggle(){}},
  querySelector(){return this.svg ||= element();}, querySelectorAll(){return [];},
  getBoundingClientRect(){return {left:0,width:600};} }; }
const document = {getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);},
  querySelectorAll(){return [];}, querySelector(){return null;}, createElement:element, body:{appendChild(){}}};
const context={document,window:{addEventListener(){},innerWidth:1200},setTimeout,clearTimeout,setInterval,clearInterval};
let code=fs.readFileSync(path.join(guard, 'web/app.js'),'utf8');
code=code.replace('  start();','  globalThis.subject={state,selectIncident,renderDetail,renderQueue,renderLevelKpis,levelNow,filteredIncidents};');
vm.runInNewContext(code,context);
const {state,selectIncident,renderDetail,renderQueue,renderLevelKpis,levelNow,filteredIncidents} = context.subject;
state.result = data;
state.overview = {decision_table:[]};
const incident = data.incidents[0], firstCase = data.cases[0];
state.sim = {row:incident.first_row};
renderLevelKpis(); renderQueue(); selectIncident(incident.incident_id);
const plain = s => s.replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim();
const result = {cursor:state.sim.row, escalation_row:incident.escalation_row, displayed_level:levelNow(incident),
  visible_case_count:data.cases.filter(c=>c.first_row<=state.sim.row).length, final_case_count:incident.cases,
  level_summary:document.getElementById('k-case-sub').textContent,
  queue:plain(document.getElementById('queue').innerHTML),
  detail:plain(document.getElementById('detail-summary').innerHTML),
  quality_action:document.getElementById('quality-action').textContent,
  suspect:document.getElementById('suspect').textContent};
result.quality_escalates_before_alert = result.displayed_level === 1 && /전수 확인/.test(result.quality_action);
result.future_cases_disclosed = result.visible_case_count < result.final_case_count && result.queue.includes('건 ' + result.final_case_count);
fs.writeFileSync(path.join(__dirname, 'judge04_simulation_probe.json'), JSON.stringify(result,null,2));
console.log(JSON.stringify(result,null,2));
