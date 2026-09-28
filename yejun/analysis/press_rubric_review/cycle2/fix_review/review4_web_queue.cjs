// review4: test_web.cjs와 같은 방식으로 app.js를 VM에서 실행해 대기열 문구를 그대로 출력한다.
const fs = require('node:fs'), vm = require('node:vm');
const elements = new Map();
function element() { return { innerHTML:'', textContent:'', value:1, style:{}, disabled:false, clientWidth:600, listeners:{},
  addEventListener(k,f){this.listeners[k]=f;}, classList:{toggle(){}}, querySelector(){return this.svg ||= element();}, querySelectorAll(){return [];},
  getBoundingClientRect(){return {left:0,width:600};} }; }
const document = {getElementById(id){if(!elements.has(id))elements.set(id,element());return elements.get(id);}, querySelectorAll(){return [];}, createElement:element, body:{appendChild(){}}};
const context={document,window:{addEventListener(){},innerWidth:1200},setTimeout,clearTimeout,setInterval,clearInterval};
let code=fs.readFileSync(process.argv[2]+'/web/app.js','utf8');
code=code.replace('  start();','  globalThis.subject={state,renderQueue,renderDetail};');
vm.runInNewContext(code,context);
const {state,renderQueue,renderDetail}=context.subject;
const base={first_row:10,level:2,escalation_row:12,priority_rank:1,evidence:'magnitude',first_timestamp:'2022-07-17 10:51:08.043',cases:1,alarm_rows:2,observed_rows:10,max_probability:0.55,max_likelihood_ratio:121};
const cases=[{incident_id:1},{incident_id:2},{incident_id:3},{incident_id:4}];
state.result={incidents:[{...base,incident_id:1},{...base,incident_id:2,action:''},{...base,incident_id:3,action:null},{...base,incident_id:4,action:'진동·부하 확인'}],cases:[],points:[],split:'B',alpha:0.01,dataset:'x',prior:0.01,lr_cap:121};
state.sim=null; state.filter='all'; state.levelFilter='all'; state.sort='priority';
renderQueue();
for (const m of document.getElementById('queue').innerHTML.matchAll(/data-incident="(\d+)"[\s\S]*?<div class="queue-action">([^<]*)/g)) console.log(`사건 ${m[1]}: [${m[2]}]`);
