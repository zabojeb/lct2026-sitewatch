const state = {
  page: 'control', frame: 4, scenario: 'normal', selectedBox: null,
  stageMode: 'auto', acceptedStage: 'Монолитные конструкции', planStart: '2020-09-28',
  editZones: false, drawing: false, draft: [], mapBackground: null, mapBackgrounds:{},
  showAllClasses: false, evidenceId: null,
  controlEventId:'mismatch', controlEvidenceId:'mismatch-701-000', mapEvidenceId:'wrong-zone-901-000',
  selectedCamera:'Камера 7', cameraIndex:2,
  notificationsOpen:false, zoneWizardOpen:false, zoneEquipments:['excavator'], zoneName:'Запретная зона',
  projectDialogOpen:false, projectReference:null, projectReferenceName:'', readiness:null, readinessBusy:false,
  zoneVisibility:{}, visibilityBusy:false
};

const schedule = [
  { id:'stage-excavation', name:'Разработка котлована', days:21 },
  { id:'stage-piles', name:'Буронабивные сваи', days:28 },
  { id:'stage-monolith', name:'Монолитные конструкции', days:75 },
  { id:'stage-assembly', name:'Монтаж конструкций', days:30 }
];

const profiles = [
  { name:'Разработка котлована', required:{excavator:1,'dump-truck':1}, any:[], optional:['bulldozer','loader','truck'], source:'ГЭСН 01' },
  { name:'Буронабивные сваи', required:{drill:1}, any:[], optional:['excavator','mobile-crane','truck'], source:'ГЭСН 05' },
  { name:'Бетонирование', required:{mixer:5,pump:1}, any:[], optional:['truck','mobile-crane'], source:'ГЭСН 06' },
  { name:'Монолитные конструкции', required:{}, any:['tower-crane','mobile-crane','manipulator'], optional:['mixer','pump','truck'], source:'ГЭСН 06' },
  { name:'Монтаж конструкций', required:{}, any:['tower-crane','mobile-crane','manipulator'], optional:['truck'], source:'ГЭСН 07' }
];

const equipmentClasses = [
  'dump-truck','excavator','roller','manipulator','mixer','bulldozer','truck','mobile-crane',
  'tower-crane','drill','pump','loader','grader','paver'
];

const names = {
  'dump-truck':'Самосвал', excavator:'Экскаватор', roller:'Каток', manipulator:'Кран-манипулятор',
  mixer:'Автобетоносмеситель', bulldozer:'Бульдозер', truck:'Грузовик', 'mobile-crane':'Автокран',
  'tower-crane':'Башенный кран', drill:'Буровая установка', pump:'Бетононасос', loader:'Погрузчик',
  grader:'Автогрейдер', paver:'Асфальтоукладчик', person:'Работник', 'mini-loader':'Мини-погрузчик',
  tractor:'Трактор','mini-bulldozer':'Мини-бульдозер',forklift:'Вилочный погрузчик','garbage-truck':'Мусоровоз',lift:'Подъёмник'
};

const scenarios = [
  ['normal','Исходный кадр'], ['wrong-zone','Техника не в зоне'], ['idle','Простой техники'],
  ['missing','Не хватает техники'], ['mismatch','Другой этап']
];

const zones = [
  { id:'forbidden-excavator-storage', name:'Склад материалов', equipmentSlugs:['excavator'], color:'red', points:[[67,37],[98,37],[98,97],[81,96],[66,59]] }
];

const cameraNames=['Камера 4','Камера 5','Камера 7','Камера 8','Камера 9'];
const zonesByCamera=Object.fromEntries(cameraNames.map(camera=>[camera,camera==='Камера 9'?zones.map(zone=>({...zone,points:zone.points.map(point=>[...point])})):[]]));
const cameraRules={
  'Камера 4':{checkExtra:true,checkZones:true},
  'Камера 5':{requiredScope:['mixer','pump'],checkExtra:true,checkStage:true,checkZones:true},
  'Камера 7':{requiredScope:['mixer','pump'],checkExtra:true,checkZones:true},
  'Камера 8':{checkExtra:true,trackMotion:['excavator'],checkZones:true},
  'Камера 9':{checkExtra:true,checkZones:true}
};
const zoneRulesEnabled=Object.fromEntries(cameraNames.map(camera=>[camera,zonesByCamera[camera].length>0]));

const stageEvidence = [
  { id:'stage-0631', phase:'monolith', timestamp:'2020-11-20T11:13:33', camera:'Камера Torre H', image:'assets/timeline/torre-h-0631.jpg' },
  { id:'stage-0076', phase:'monolith', timestamp:'2020-12-02T09:12:17', camera:'Камера Torre H', image:'assets/timeline/torre-h-0076.jpg' },
  { id:'stage-0150', phase:'monolith', timestamp:'2021-01-06T11:05:02', camera:'Камера Torre H', image:'assets/timeline/torre-h-0150.jpg' },
  { id:'stage-0501', phase:'monolith', timestamp:'2021-01-22T08:57:45', camera:'Камера Torre H', image:'assets/timeline/torre-h-0501.jpg' },
  { id:'stage-0176', phase:'monolith', timestamp:'2021-02-12T09:01:19', camera:'Камера Torre H', image:'assets/timeline/torre-h-0176.jpg' }
];

const observedPhases = [
  { id:'monolith', name:'Монолитные конструкции', start:'2020-11-20T11:13:33', end:'2021-02-12T09:01:19' }
];

const deviationEvents = [];

let data = null;
const app = document.querySelector('#app');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct = value => `${Math.round(value * 1000) / 10}%`;
const DAY = 86400000;
const dateValue = value => new Date(value).getTime();
const shortDate = value => new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'short'}).format(new Date(value));
const fullDateTime = value => new Intl.DateTimeFormat('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(value));
const numericDate = value => new Intl.DateTimeFormat('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(value));
const timeOnly = value => new Intl.DateTimeFormat('ru-RU',{hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date(value));
const dayWord = value => {const n=Math.abs(Math.round(value))%100,m=n%10;return n>10&&n<20?'дней':m===1?'день':m>=2&&m<=4?'дня':'дней'};
const stageWord = value => {const n=Math.abs(value)%100,m=n%10;return n>10&&n<20?'этапов':m===1?'этап':m>=2&&m<=4?'этапа':'этапов'};
const frameWord = value => {const n=Math.abs(value)%100,m=n%10;return n>10&&n<20?'кадров':m===1?'кадр':m>=2&&m<=4?'кадра':'кадров'};
const objectWord = value => {const n=Math.abs(value)%100,m=n%10;return n>10&&n<20?'объектов':m===1?'объект':m>=2&&m<=4?'объекта':'объектов'};
const cameraWord = value => {const n=Math.abs(value)%100,m=n%10;return n>10&&n<20?'камер':m===1?'камера':m>=2&&m<=4?'камеры':'камер'};
const zoneEquipmentSlugs = zone => Array.isArray(zone?.equipmentSlugs)&&zone.equipmentSlugs.length ? zone.equipmentSlugs : zone?.equipmentSlug ? [zone.equipmentSlug] : [];
const previewFor = src => src?.startsWith('assets/') ? `assets/previews/${src.slice(7).replace(/\.[^.]+$/,'.jpg')}` : src;
const previewStyle = src => `style="background-image:url('${esc(previewFor(src))}')"`;
const progressiveImage = (src,alt) => `<img class="scene-image progressive-image" src="${src}" alt="${esc(alt)}" decoding="async" fetchpriority="high" onload="this.classList.add('loaded')">`;
const loadImage = src => new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=reject;image.src=src});
const imageDescriptor = image => {
  const width=144,height=81,canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const context=canvas.getContext('2d',{willReadFrequently:true});context.drawImage(image,0,0,width,height);
  const pixels=context.getImageData(0,0,width,height).data,gray=new Float32Array(width*height);
  for(let i=0;i<gray.length;i++)gray[i]=.299*pixels[i*4]+.587*pixels[i*4+1]+.114*pixels[i*4+2];
  const cols=8,rows=5,cells=[];
  for(let gy=0;gy<rows;gy++)for(let gx=0;gx<cols;gx++){
    let light=0,edge=0,count=0;
    for(let y=Math.floor(gy*height/rows);y<Math.floor((gy+1)*height/rows);y+=2)for(let x=Math.floor(gx*width/cols);x<Math.floor((gx+1)*width/cols);x+=2){const at=y*width+x;light+=gray[at]/255;if(x+1<width&&y+1<height)edge+=Math.min(1,(Math.abs(gray[at]-gray[at+1])+Math.abs(gray[at]-gray[at+width]))/90);count++}
    cells.push([light/count,edge/count]);
  }
  return cells;
};
const descriptorSimilarity = (left,right) => {
  let difference=0;
  for(let i=0;i<Math.min(left.length,right.length);i++)difference+=.35*Math.abs(left[i][0]-right[i][0])+.65*Math.abs(left[i][1]-right[i][1]);
  return Math.max(0,Math.min(1,1-difference/Math.min(left.length,right.length)));
};

async function analyzeProjectProgress() {
  const frame=operationalFrame();if(!state.projectReference||!frame)return null;
  const key=`${frame.image}|${state.projectReference.length}|${state.projectReference.slice(64,112)}`;
  if(state.readiness?.key===key)return state.readiness;
  const [current,target]=await Promise.all([loadImage(frame.image),loadImage(state.projectReference)]);
  const similarity=descriptorSimilarity(imageDescriptor(current),imageDescriptor(target));
  const stageName=acceptedStage(),stageIndex=Math.max(0,schedule.findIndex(item=>item.name===stageName));
  const timelinePrior=Math.max(.05,Math.min(.95,(stageIndex+.55)/Math.max(1,schedule.length)));
  const vlm=data.vlmObservations?.[frame.id];
  let contextPrior=.55;
  if(vlm?.scene_code==='CRANE_SECTOR'&&['Монолитные конструкции','Монтаж конструкций'].includes(stageName))contextPrior=.9;
  else if(vlm?.scene_code==='WORK_FRONT')contextPrior=.72;
  const score=Math.round(100*Math.max(0,Math.min(1,.55*similarity+.30*timelinePrior+.15*contextPrior)));
  const confidence=similarity>.72?'высокая':similarity>.5?'средняя':'низкая';
  return {key,score,similarity:Math.round(similarity*100),confidence,stageName,vlmScene:vlm?.scene||'Контекст не определён',frameId:frame.id};
}

function scheduleReadinessAnalysis() {
  if(!state.projectReference||state.readinessBusy)return;
  const frame=operationalFrame(),key=frame?`${frame.image}|${state.projectReference.length}|${state.projectReference.slice(64,112)}`:'';
  if(state.readiness?.key===key)return;
  state.readinessBusy=true;
  analyzeProjectProgress().then(result=>{state.readiness=result;state.readinessBusy=false;render()}).catch(()=>{state.readinessBusy=false});
}
const baseFrame = () => data.session.frames[state.frame];
const acceptedStage = () => state.stageMode === 'manual' ? state.acceptedStage : autoStage();
const profileFor = name => profiles.find(p => p.name === name) || profiles[0];
const isMachine = box => !['person','helmet'].includes(box.classSlug);
let cameraStreams={};

function buildCameraStreams(items) {
  const result={};
  for(const camera of cameraNames){
    const source=items.filter(item=>item.camera===camera).sort((a,b)=>dateValue(a.timestamp)-dateValue(b.timestamp));
    result[camera]=source.map((item,index)=>{
      const totalMinutes=8*60+index*20,hours=String(Math.floor(totalMinutes/60)).padStart(2,'0'),minutes=String(totalMinutes%60).padStart(2,'0');
      const timestamp=`2021-02-12T${hours}:${minutes}:00`;
      return {...item,sourceTimestamp:item.timestamp,timestamp,time:timestamp.slice(11),dateLabel:'12.02.2021',streamIndex:index};
    });
  }
  return result;
}

const activeStream = () => cameraStreams[state.selectedCamera]||[];
const operationalFrame = () => activeStream()[Math.max(0,Math.min(state.cameraIndex,activeStream().length-1))];
const framesAtSlice = (index=state.cameraIndex) => cameraNames.map(camera=>cameraStreams[camera]?.[index]).filter(Boolean);
function siteSnapshot(index=state.cameraIndex) {
  const frames=framesAtSlice(index);
  const fused=GeoTracking.fuseCameraDetections(frames,{defaultThreshold:6});
  return {...fused,frames,timestamp:frames[0]?.timestamp||operationalFrame()?.timestamp};
}
const activeZones = camera => zonesByCamera[camera||state.selectedCamera]||zonesByCamera[cameraNames[0]];
const allowedZonesByStage={
  'Разработка котлована':{excavator:['work'],bulldozer:['work'],'dump-truck':['work','access'],loader:['work','access'],truck:['access']},
  'Буронабивные сваи':{drill:['work'],excavator:['work'],'mobile-crane':['crane','work'],truck:['access']},
  'Бетонирование':{mixer:['work','access'],pump:['work'],truck:['access'],'mobile-crane':['crane','work']},
  'Монолитные конструкции':{'tower-crane':['crane'],'mobile-crane':['crane','work'],manipulator:['work','access'],mixer:['work','access'],pump:['work'],truck:['access']},
  'Монтаж конструкций':{'tower-crane':['crane'],'mobile-crane':['crane','work'],manipulator:['work','access'],truck:['access']}
};
const defaultAllowedZones={excavator:['work','access'],bulldozer:['work','access'],'dump-truck':['work','access'],loader:['work','access'],truck:['access'],mixer:['work','access'],pump:['work'],drill:['work'],'tower-crane':['crane','work'],'mobile-crane':['crane','work'],manipulator:['work','access'],tractor:['work','access'],'mini-bulldozer':['work','access']};
const operationalPlanWindow = () => plannedWindow(operationalFrame()?.timestamp);
const operationalPlanStage = () => operationalPlanWindow()?.name || schedule[0]?.name || 'Этап не задан';
const allowedZonesFor = slug => allowedZonesByStage[operationalPlanStage()]?.[slug]||defaultAllowedZones[slug];

function closestBox(frame,box) {
  const candidates=(frame?.boxes||[]).filter(item=>item.classSlug===box.classSlug);
  return candidates.sort((a,b)=>Math.hypot(a.bbox[0]-box.bbox[0],a.bbox[1]-box.bbox[1])-Math.hypot(b.bbox[0]-box.bbox[0],b.bbox[1]-box.bbox[1]))[0];
}

function analyzeOperationalFrame(frame=operationalFrame()) {
  if(!frame)return {alerts:[],boxStates:[],rows:[]};
  const planStage=operationalPlanStage(),profile=profileFor(planStage),rules=cameraRules[frame.camera]||{},site=siteSnapshot(frame.streamIndex),counts=site.counts||{},frameCounts=frame.counts||{},alerts=[];
  const requiredScope=Object.keys(profile.required||{});
  const boxStates=frame.boxes.map(()=>({tone:'green',messages:[]}));
  const mark=(indexes,tone,message)=>indexes.forEach(index=>{const target=boxStates[index];if(!target)return;if(tone==='red'||target.tone==='green')target.tone=tone;target.messages.push(message)});
  for(const slug of requiredScope){
    const expected=profile.required?.[slug]||0,actual=counts[slug]||0;
    if(expected&&actual<expected){
      const title=actual===0?'Нет обязательной техники':'Недобор техники',message=`${names[slug]||slug}: ${actual} из ${expected}`;
      const indexes=frame.boxes.map((box,index)=>box.classSlug===slug?index:-1).filter(index=>index>=0);
      alerts.push({code:'shortage',tone:'red',title,message,slug,actual,expected});mark(indexes,'red',`${title} · ${message}`);
    }
  }
  if((profile.any||[]).length&&!profile.any.some(slug=>(counts[slug]||0)>0)){
    const message=`Нужна хотя бы одна: ${profile.any.map(slug=>names[slug]||slug).join(', ')}`;
    alerts.push({code:'shortage',tone:'red',title:'Нет обязательной техники',message,slugs:[...profile.any],actual:0,expected:1});
  }
  if(rules.checkExtra){
    const allowed=new Set([...Object.keys(profile.required||{}),...(profile.any||[]),...(profile.optional||[])]);
    const extras=Object.keys(counts).filter(slug=>equipmentClasses.includes(slug)&&counts[slug]>0&&!allowed.has(slug));
    for(const slug of extras){const indexes=frame.boxes.map((box,index)=>box.classSlug===slug?index:-1).filter(index=>index>=0),actual=counts[slug],cameras=site.camerasByClass[slug]||[],message=`${names[slug]||slug}: ${actual} · ${cameras.length} ${cameraWord(cameras.length)}`;alerts.push({code:'extra',tone:'yellow',title:'Лишняя техника',message,slug,actual});mark(indexes,'yellow',`Лишняя техника · ${names[slug]||slug}`)}
  }
  if(rules.checkZones&&zoneRulesEnabled[frame.camera]){
    frame.boxes.forEach((box,index)=>{if(!isMachine(box))return;const zone=zoneFor(box,frame.camera);if(zone){const message=`${box.className} · ${zone.name}`;alerts.push({code:'zone',tone:'yellow',title:'Въезд в запретную зону',message,slug:box.classSlug,zone:zone.name});mark([index],'yellow',`Въезд в запретную зону · ${zone.name}`)}});
  }
  if((rules.trackMotion||[]).length&&frame.streamIndex>=2){
    const previous=activeStream()[frame.streamIndex-2];
    frame.boxes.forEach((box,index)=>{if(!rules.trackMotion.includes(box.classSlug))return;const match=closestBox(previous,box);if(!match)return;const shift=Math.hypot(match.bbox[0]-box.bbox[0],match.bbox[1]-box.bbox[1]);if(shift<.018){const minutes=(frame.streamIndex-(frame.streamIndex-2))*20,message=`${box.className}: ${minutes} мин, смещение ${Math.round(shift*1000)/10}% кадра`;alerts.push({code:'idle',tone:'yellow',title:'Вероятный простой',message,slug:box.classSlug,minutes});mark([index],'yellow',`Вероятный простой · ${minutes} мин`)}});
  }
  if(rules.checkStage){
    const detected=detectedStage(site);
    if(detected!==planStage){const message=`По камерам: ${detected}; по графику: ${planStage}`,indexes=frame.boxes.map((box,index)=>isMachine(box)?index:-1).filter(index=>index>=0);alerts.push({code:'stage',tone:'yellow',title:'Фактический этап не совпадает с планом',message,detected});mark(indexes,'yellow',message)}
  }
  const rows=[];
  for(const [slug,expected] of Object.entries(profile.required||{})){const actual=counts[slug]||0,evaluated=requiredScope.includes(slug);rows.push({slug,label:names[slug]||slug,role:'Обязательная',expected,actual,frameActual:frameCounts[slug]||0,cameras:site.camerasByClass[slug]||[],status:evaluated?(actual>=expected?'ok':'bad'):'neutral'})}
  for(const slug of profile.any||[]){const actual=counts[slug]||0,groupOk=profile.any.some(item=>(counts[item]||0)>0);rows.push({slug,label:names[slug]||slug,role:'Одна из группы',expected:'1*',actual,frameActual:frameCounts[slug]||0,cameras:site.camerasByClass[slug]||[],status:groupOk?'ok':'bad'})}
  const allowed=new Set([...Object.keys(profile.required||{}),...(profile.any||[]),...(profile.optional||[])]);
  for(const slug of profile.optional||[]){const actual=counts[slug]||0;if(actual)rows.push({slug,label:names[slug]||slug,role:'Допустимая',expected:null,actual,frameActual:frameCounts[slug]||0,cameras:site.camerasByClass[slug]||[],status:'ok'})}
  for(const slug of Object.keys(counts).filter(slug=>equipmentClasses.includes(slug)&&!allowed.has(slug))){rows.push({slug,label:names[slug]||slug,role:'Вне профиля',expected:null,actual:counts[slug],frameActual:frameCounts[slug]||0,cameras:site.camerasByClass[slug]||[],status:rules.checkExtra?'warning':'neutral'})}
  return {alerts,boxStates,rows,profile,site};
}

function stageScore(counts,profile) {
  const observedEntries=Object.entries(counts||{}).filter(([slug,n])=>n>0&&equipmentClasses.includes(slug));
  const observed=new Set(observedEntries.map(([slug])=>slug));
  const expected=new Set([...Object.keys(profile.required||{}),...(profile.any||[]),...(profile.optional||[])]);
  const required=Object.entries(profile.required||{});
  const requiredCoverage=required.length?required.reduce((sum,[slug,n])=>sum+Math.min(1,(counts[slug]||0)/n),0)/required.length:0;
  const anyCoverage=profile.any?.length?Math.max(...profile.any.map(slug=>(counts[slug]||0)>0?1:0)):0;
  const optionalCoverage=profile.optional?.length?profile.optional.filter(slug=>(counts[slug]||0)>0).length/profile.optional.length:0;
  const classPrecision=observed.size?[...observed].filter(slug=>expected.has(slug)).length/observed.size:0;
  const total=observedEntries.reduce((sum,[,n])=>sum+n,0)||1;
  const unexpected=observedEntries.filter(([slug])=>!expected.has(slug)).reduce((sum,[,n])=>sum+n,0)/total;
  const requiredScale=Math.min(1,required.reduce((sum,[,n])=>sum+n,0)/5);
  const score=required.length
    ? .67*requiredCoverage+.10*optionalCoverage+.08*classPrecision-.35*unexpected+.08*requiredScale*requiredCoverage
    : .65*anyCoverage+.20*optionalCoverage+.15*classPrecision-.45*unexpected;
  return Math.max(0,Math.min(1,score));
}

function rankedStages(frame=operationalFrame()) {
  return profiles.map(profile=>({name:profile.name,score:stageScore(frame?.counts||{},profile)})).sort((a,b)=>b.score-a.score);
}

function detectedStage(frame=siteSnapshot()) {
  const ranked=rankedStages(frame);
  const fallback=data.stageScores?.[0]?.name;
  if(ranked[1]&&ranked[0].score-ranked[1].score<.03){const tied=ranked.filter(x=>ranked[0].score-x.score<.03);if(tied.some(x=>x.name===fallback))return fallback}
  return ranked[0]?.name||fallback||profiles[0].name;
}

const autoStage = () => detectedStage(siteSnapshot());

const timelineEvidence = () => data?.stageTimeline?.length ? data.stageTimeline : stageEvidence;

function observedSegments() {
  const evidence=[...timelineEvidence()].sort((a,b)=>dateValue(a.timestamp)-dateValue(b.timestamp)).map(item=>{
    const prediction=rankedStages(item)[0]||{name:'Не определён',score:0};
    return {...item,prediction};
  });
  const segments=[];
  for(const item of evidence){
    const last=segments.at(-1);
    if(!last||last.name!==item.prediction.name)segments.push({id:`observed-${segments.length}`,name:item.prediction.name,start:dateValue(item.timestamp),end:dateValue(item.timestamp),evidence:[item]});
    else{last.end=dateValue(item.timestamp);last.evidence.push(item)}
  }
  for(let index=0;index<segments.length-1;index++)segments[index].end=segments[index+1].start;
  return segments;
}

function scheduleWindows() {
  let cursor=dateValue(`${state.planStart}T00:00:00`);
  return schedule.map(item=>{const start=cursor,end=start+item.days*DAY;cursor=end;return {...item,start,end}});
}

function plannedWindow(timestamp=baseFrame()?.timestamp) {
  const time=dateValue(timestamp), windows=scheduleWindows();
  return windows.find(x=>time>=x.start&&time<x.end) || (time<windows[0].start?windows[0]:windows.at(-1));
}

const plannedStage = () => plannedWindow()?.name || schedule[0]?.name || 'Этап не задан';

function delayMetrics() {
  const segments=observedSegments(),current=segments.at(-1),observedStart=current?.start||dateValue(baseFrame().timestamp),observedEnd=current?.end||dateValue(baseFrame().timestamp);
  const planned=scheduleWindows().find(x=>x.name===current?.name);
  if(!planned)return {days:0,startShift:0,overrun:0,observedDays:Math.max(0,(observedEnd-observedStart)/DAY),plannedDays:0,current};
  const startShift=(observedStart-planned.start)/DAY,observedDays=Math.max(0,(observedEnd-observedStart)/DAY);
  const overrun=(observedEnd-planned.end)/DAY;
  const startDelay=Math.max(0,Math.round(startShift)),endDelay=Math.max(0,Math.round(overrun));
  const reason=endDelay>=startDelay&&endDelay>0?'end':'start';
  return {days:Math.max(startDelay,endDelay),reason,startDelay,endDelay,startShift,overrun,observedDays,plannedDays:planned.days,planned,current,observedStart,observedEnd};
}

function durationLabel(start,end) {
  const seconds=Math.max(0,Math.round((end-start)/1000)),hours=seconds/3600;
  if(seconds<3600)return `${Math.floor(seconds/60)} мин ${seconds%60} с`;
  if(hours<24)return `${Math.round(hours*10)/10} ч`;
  return `${Math.round(hours/24)} дн`;
}

function demoExcavator() {
  const shift=state.scenario==='idle'?0:(state.frame-(data.session.frames.length-1))*.0025;
  return {
    className:'Экскаватор', classSlug:'excavator', bbox:[0.718+shift,0.606,0.102,0.118], confidence:0.96,
    synthetic:true, stationary:state.scenario==='idle', stillSec:state.scenario==='idle'?1380:0
  };
}

function currentFrame() {
  const frame = baseFrame();
  const demo = ['wrong-zone','idle'].includes(state.scenario);
  if (!demo) return frame;
  const box = demoExcavator();
  return {
    ...frame, demo:true, image:state.frame>=7?'assets/scenarios/excavator-wrong-zone.png':frame.image,
    boxes:[...frame.boxes, box], counts:{...frame.counts, excavator:(frame.counts.excavator||0)+1}
  };
}

function warnings() {
  const delay=delayMetrics();
  if (state.scenario === 'wrong-zone') return [{
    title:'Экскаватор находится в зоне складирования',
    detail:'Техника должна работать в основном фронте работ.', meta:`Складирование · ${baseFrame().time}`, route:'map'
  }];
  if (state.scenario === 'idle') return [{
    title:'Экскаватор неподвижен 23 минуты',
    detail:'Смещение рамки ниже порога на 8 последовательных кадрах.', meta:'Основной фронт работ · 8 кадров', route:'history'
  }];
  if (state.scenario === 'missing') return [{
    title:'Не хватает обязательной техники',
    detail:`Набор техники не закрывает требования этапа «${plannedStage()}».`, meta:`Требование плана · ${profileFor(plannedStage()).source}`, route:'plan'
  }];
  if (state.scenario === 'mismatch') return [{
    title:'Наблюдается другой этап работ',
    detail:`По плану — ${plannedStage()}, по кадрам — ${autoStage()}.`, meta:`Расчётное отставание ${delay.days} дней`, route:'plan'
  }];
  if (state.scenario === 'normal' && plannedStage()!==autoStage()) return [{
    title:'Наблюдаемый этап отстаёт от графика',
    detail:`По плану уже должен идти этап «${plannedStage()}».`,meta:`Прогноз отставания ${delay.days} дней`,route:'plan'
  }];
  return [];
}

function warningForBox(box) {
  if (box.synthetic && state.scenario === 'wrong-zone') return 'Экскаватор в зоне складирования';
  if (box.synthetic && state.scenario === 'idle') return 'Вероятный простой · 23 мин';
  return '';
}

function icon(slug) {
  if (slug === 'notification') return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 17h10l-1.4-2.1V10a3.6 3.6 0 0 0-7.2 0v4.9zM10 20h4"/></svg>`;
  if (['tower-crane','mobile-crane','manipulator','drill'].includes(slug)) return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 21V4h3v17M3 4h16M8 7h11l2 3M13 4v3M18 10v5M16.5 15h3"/></svg>`;
  if (slug === 'person') return `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="6" r="2.5"/><path d="M8 21l2-7V9h4v5l2 7M7 12h10"/></svg>`;
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 16h15l3-4h-7l-2-5H6v5H3zM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm10 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"/></svg>`;
}

function header() {
  const items = [['control','Контроль'],['plan','План работ'],['map','Карта зон']];
  const pending=cameraNames.filter(camera=>activeZones(camera).length===0).length+(state.projectReference?0:1);
  return `<header class="appbar"><button class="brand" data-page="control"><i></i>СТРОЙКОНТУР</button><nav>${items.map(([id,label])=>`<button data-page="${id}" class="${state.page===id?'active':''}">${label}</button>`).join('')}</nav><button class="notification-button ${pending?'has-alerts':''}" data-notifications aria-label="Задачи разметки зон">${icon('notification')}${pending?`<b>${pending}</b>`:''}</button><div class="project"><span>СК Монолит</span><small>оператор</small></div></header>`;
}

function notificationPanel() {
  if(!state.notificationsOpen)return '';
  const pending=cameraNames.filter(camera=>activeZones(camera).length===0);
  const project=state.projectReference
    ? `<button class="notification-task project-ready" data-project-dialog><i></i><span><b>Проектный вид загружен</b><small>${esc(state.projectReferenceName||'Проектный вид')} · ${state.readiness?`готовность ${state.readiness.score}%`:'расчёт готовности'}</small></span><em>Открыть →</em></button>`
    : `<button class="notification-task project-task" data-project-dialog><i></i><span><b>Загрузить проектный вид</b><small>Нужен ракурс итогового здания для оценки визуальной готовности</small></span><em>Загрузить →</em></button>`;
  return `<aside class="notification-panel"><header><div><span>ЗАДАЧИ И НАСТРОЙКИ</span><h2>Контроль площадки</h2></div><button data-notifications aria-label="Закрыть">×</button></header>${project}${pending.map(camera=>`<button class="notification-task" data-zone-task="${camera}"><i></i><span><b>${esc(camera)}</b><small>Выберите технику и обведите область, куда ей нельзя заезжать</small></span><em>Разметить →</em></button>`).join('')}${!pending.length&&state.projectReference?'<div class="notification-empty"><b>Первичная настройка завершена</b><span>Проектный вид и зоны камер заданы.</span></div>':''}</aside>`;
}

function projectReferenceDialog() {
  if(!state.projectDialogOpen)return '';
  return `<div class="zone-wizard-backdrop"><section class="zone-wizard project-dialog" role="dialog" aria-modal="true"><header><div><span>ВИЗУАЛЬНАЯ ГОТОВНОСТЬ</span><h2>Проектный вид</h2></div><button data-close-project-dialog aria-label="Закрыть">×</button></header><div class="zone-wizard-body">${state.projectReference?`<div class="project-preview"><img src="${state.projectReference}" alt="Загруженный проектный вид"><span><b>${esc(state.projectReferenceName||'Проектный вид')}</b><small>${state.readiness?`Оценка готовности ${state.readiness.score}% · уверенность ${state.readiness.confidence}`:'Выполняется сравнение'}</small></span></div>`:''}<label class="project-upload"><span>${state.projectReference?'Заменить проектный вид':'Загрузить проектный вид'}</span><input id="project-view-upload" type="file" accept="image/*"><strong>Выбрать изображение</strong></label><p>Для достоверного сравнения загрузите визуализацию итогового здания примерно с того же ракурса, что и камера. Оценка объединяет визуальное сходство, распознанный этап и контекст VLM.</p>${state.projectReference?'<button class="secondary danger" data-remove-project-view>Удалить проектный вид</button>':''}</div></section></div>`;
}

function zoneWizard() {
  if(!state.zoneWizardOpen)return '';
  return `<div class="zone-wizard-backdrop"><section class="zone-wizard" role="dialog" aria-modal="true"><header><div><span>НОВАЯ ЗАПРЕТНАЯ ЗОНА</span><h2>${esc(state.selectedCamera)}</h2></div><button data-close-zone-wizard aria-label="Закрыть">×</button></header><div class="zone-wizard-body"><label><span>Название зоны</span><input id="zone-draft-name" value="${esc(state.zoneName)}" placeholder="Например: склад материалов"></label><fieldset class="zone-equipment-picker"><legend>Какой технике въезд запрещён</legend>${equipmentClasses.map(slug=>`<label><input type="checkbox" data-zone-draft-equipment="${slug}" ${state.zoneEquipments.includes(slug)?'checked':''}><span>${icon(slug)}${esc(names[slug])}</span></label>`).join('')}</fieldset><p>Можно выбрать несколько типов. После нажатия поставьте точки по границе области на кадре и завершите обвод.</p><button class="primary" data-start-zone-draw ${state.zoneEquipments.length?'':'disabled'}>Перейти к обводу</button></div></section></div>`;
}

function frameRail() {
  const frames=data.session.frames, f=baseFrame();
  return `<div class="frame-rail"><button data-step="-1" ${state.frame===0?'disabled':''} aria-label="Предыдущий кадр">←</button><div class="rail-track">${frames.map((x,i)=>`<button data-frame="${i}" class="${i===state.frame?'active':''}" title="${x.dateLabel} · ${x.time}" aria-label="${x.dateLabel} ${x.time}"></button>`).join('')}</div><div class="rail-time"><b>${f.dateLabel}</b><span>${f.time}</span></div><button data-step="1" ${state.frame===frames.length-1?'disabled':''} aria-label="Следующий кадр">→</button></div>`;
}

function detectorBox(box) {
  const [x,y,w,h]=box.bbox, alert=warningForBox(box), label=alert||box.className;
  return `<div class="det-box ${alert?'alert':''}" tabindex="0" style="left:${(x-w/2)*100}%;top:${(y-h/2)*100}%;width:${w*100}%;height:${h*100}%" aria-label="${esc(label)}"><span class="det-tooltip">${esc(label)}</span>${alert?'<i class="alarm-dot"></i>':''}</div>`;
}

function syntheticMachineOverlay(frame) {
  const box=frame.boxes.find(x=>x.synthetic);if(!box||state.frame>=7)return '';
  const [x,y,w,h]=box.bbox;
  return `<img class="synthetic-machine" src="assets/scenarios/excavator-track-overlay.png" alt="" style="left:${(x-w/2)*100}%;top:${(y-h/2)*100}%;width:${w*100}%;height:${h*100}%">`;
}

function cameraPanel() {
  const f=currentFrame();
  return `<section class="camera-panel"><div class="camera-top"><div><b>${f.cameraId}</b><span>${f.demo?'контрольный сценарий':'архивный кадр'}</span></div><time>${f.dateLabel} · ${f.time}</time></div><div class="camera-canvas"><img class="scene-image" src="${f.image}" alt="Строительная площадка, ${f.dateLabel}">${syntheticMachineOverlay(f)}${f.boxes.map((b,i)=>detectorBox(b,i)).join('')}</div>${frameRail()}</section>`;
}

function expectedEquipment() {
  const f=currentFrame(), profile=profileFor(plannedStage());
  const required=Object.entries(profile.required).map(([slug,n])=>({slug,label:names[slug],ok:(f.counts[slug]||0)>=n,n}));
  if(profile.any.length) required.push({slug:profile.any[0],label:profile.any.map(x=>names[x]).join(' или '),ok:profile.any.some(x=>(f.counts[x]||0)>0),n:1});
  return required;
}

function decisionPanel() {
  const alert=warnings()[0], expected=expectedEquipment();
  return `<aside class="decision-panel"><div class="decision-head"><div><span>СТАТУС ПЛОЩАДКИ</span><h2>${alert?'Требует внимания':'Отклонений нет'}</h2></div><b class="status-badge ${alert?'bad':'ok'}">${alert?'1 событие':'Норма'}</b></div>${alert?`<article class="primary-alert"><span>ВЫСОКИЙ ПРИОРИТЕТ</span><h3>${esc(alert.title)}</h3><p>${esc(alert.detail)}</p><small>${esc(alert.meta)}</small><button data-page="${alert.route}">${alert.route==='map'?'Показать на карте':alert.route==='history'?'Открыть историю':'Проверить план'} →</button></article>`:`<article class="quiet-state"><b>Состав техники соответствует плану</b><span>Критических событий на выбранном кадре нет.</span></article>`}<div class="stage-compare"><div><span>По плану</span><b>${esc(plannedStage())}</b></div><i>→</i><div><span>Наблюдается</span><b>${esc(autoStage())}</b><small>${pct(data.stageScores[0].score)}</small></div></div><div class="equipment-check"><div class="section-label">Техника по плану</div>${expected.length?expected.map(x=>`<div><span class="equipment-icon">${icon(x.slug)}</span><b>${esc(x.label)}</b><em class="${x.ok?'ok':'bad'}">${x.ok?'есть':'нет'}</em></div>`).join(''):'<p>Для этапа нет обязательного набора техники.</p>'}</div></aside>`;
}

function scheduleStrip() {
  const windows=scheduleWindows(),segments=observedSegments(),observedStart=segments[0]?.start||dateValue(baseFrame().timestamp),observedEnd=segments.at(-1)?.end||dateValue(baseFrame().timestamp);
  const start=Math.min(windows[0].start,observedStart),end=Math.max(windows.at(-1).end,observedEnd),span=Math.max(1,end-start);
  const pos=value=>(Math.max(start,Math.min(end,value))-start)/span*100;
  const width=(a,b)=>Math.max(.45,pos(b)-pos(a));
  const delay=delayMetrics();
  const planSegments=windows.map((x,i)=>`<div class="timeline-segment plan-stage s${i%4}" tabindex="0" style="left:${pos(x.start)}%;width:${width(x.start,x.end)}%"><b>${esc(x.name)}</b><small>${x.days} дн</small><span class="timeline-tooltip"><strong>${esc(x.name)}</strong>${shortDate(x.start)} — ${shortDate(x.end)} · ${x.days} дней</span></div>`).join('');
  const observed=segments.map(segment=>{
    const days=Math.max(1,Math.round((segment.end-segment.start)/DAY));
    const ticks=segment.evidence.map(item=>{const p=(dateValue(item.timestamp)-segment.start)/Math.max(1,segment.end-segment.start)*100;return `<button class="stage-evidence-tick" data-evidence="${item.id}" style="left:${Math.max(1,Math.min(99,p))}%" title="${esc(item.camera)} · ${fullDateTime(item.timestamp)}"><span>${timeOnly(item.timestamp)}</span></button>`}).join('');
    const stageIndex=Math.max(0,profiles.findIndex(profile=>profile.name===segment.name)),confidence=Math.round(segment.evidence.reduce((sum,item)=>sum+(item.prediction?.score||0),0)/segment.evidence.length*100);
    return `<div class="timeline-segment observed-stage s${stageIndex%4}" tabindex="0" style="left:${pos(segment.start)}%;width:${width(segment.start,segment.end)}%"><b>${esc(segment.name)}</b><small>${days} ${dayWord(days)} · ${segment.evidence.length} ${frameWord(segment.evidence.length)}</small>${ticks}<span class="timeline-tooltip"><strong>${esc(segment.name)}</strong>${shortDate(segment.start)} — ${shortDate(segment.end)} · совпадение ${confidence}%. Нажмите на отсечку, чтобы открыть кадр.</span></div>`;
  }).join('');
  const middle=start+(end-start)/2;
  return `<section class="schedule-strip"><div class="schedule-title"><div><h2>План и выполнение по камерам</h2><span>Одинаковые названия и цвета: сверху план, снизу этапы, распознанные по технике</span></div><b class="${delay.days?'bad':'ok'}">${delay.days?`Отставание ${delay.days} ${dayWord(delay.days)}`:'Идём по графику'}</b></div><div class="timeline-axis"><span>${shortDate(start)}</span><span>${shortDate(middle)}</span><span>${shortDate(end)}</span></div><div class="timeline-row"><label>План</label><div class="timeline-lane">${planSegments}</div></div><div class="timeline-row fact-row"><label>По камерам</label><div class="timeline-lane">${observed}</div></div><div class="timeline-legend"><span><i class="plan-key"></i>плановая длительность</span><span><i class="fact-key"></i>${timelineEvidence().length} кадров, объединённых в ${segments.length} ${stageWord(segments.length)}</span></div></section>`;
}

function evidenceData() {
  if(!state.evidenceId)return null;
  const stage=timelineEvidence().find(item=>item.id===state.evidenceId);
  if(stage){const prediction=rankedStages(stage)[0];return {...stage,kind:'stage',title:prediction?.name||'Наблюдаемый этап',detail:`Этап определён по составу техники: совпадение ${Math.round((prediction?.score||0)*100)}%.`,frame:stage}}
  const frame=data.incidentEvidence?.find(item=>item.id===state.evidenceId),event=deviationEvents.find(item=>item.id===frame?.eventId);
  if(!event||!frame)return null;
  return {...frame,kind:'incident',title:event.type,detail:event.cause,impact:event.impact,overlay:event.overlay,frame};
}

function evidenceBox(bbox,label,extra='') {
  const [x,y,w,h]=bbox;
  return `<div class="evidence-box ${extra}" style="left:${(x-w/2)*100}%;top:${(y-h/2)*100}%;width:${w*100}%;height:${h*100}%"><span>${esc(label)}</span></div>`;
}

const eventEvidence = event => (event?.evidence||[]).map(id=>data.incidentEvidence?.find(item=>item.id===id)).filter(Boolean);
const controlEvent = () => deviationEvents.find(event=>event.id===state.controlEventId)||deviationEvents[0];
const controlEvidence = () => data.incidentEvidence?.find(item=>item.id===state.controlEvidenceId)||eventEvidence(controlEvent())[0];

function incidentOverlay(frame,event) {
  if(!frame||!event)return '';
  if(event.overlay==='shortage')return frame.boxes.filter(box=>box.classSlug==='mixer').map(box=>evidenceBox(box.bbox,'Недобор: 4 из 5 автобетоносмесителей')).join('');
  if(event.overlay==='missing')return evidenceBox([.50,.48,.54,.52],'Обязательная техника не обнаружена в рабочей области','missing-target');
  if(event.overlay==='idle')return frame.boxes.filter(box=>box.classSlug==='excavator').map(box=>evidenceBox(box.bbox,'Простой: положение не меняется в серии кадров')).join('');
  if(event.overlay==='wrong-zone')return frame.boxes.filter(box=>box.classSlug==='excavator'&&zoneFor(box)?.id==='storage').map(box=>evidenceBox(box.bbox,'Не в рабочей зоне · складирование','zone-note')).join('');
  if(event.overlay==='extra')return frame.boxes.filter(isMachine).map(box=>evidenceBox(box.bbox,`${box.className}: не предусмотрено текущим этапом`)).join('');
  if(event.overlay==='mismatch')return frame.boxes.filter(box=>['mixer','pump'].includes(box.classSlug)).map(box=>evidenceBox(box.bbox,`${box.className}: профиль бетонирования`)).join('');
  return '';
}

function evidenceModal() {
  const item=evidenceData();if(!item)return '';
  const event=item.kind==='incident'?deviationEvents.find(entry=>entry.id===item.eventId):null;
  const overlay=item.kind==='stage'?(item.boxes||[]).map(box=>evidenceBox(box.bbox,box.className,'stage-detection')).join(''):incidentOverlay(item.frame,event);
  return `<div class="evidence-backdrop" data-close-evidence><section class="evidence-dialog" role="dialog" aria-modal="true" aria-label="Кадр-доказательство" onclick="event.stopPropagation()"><header><div><span>${item.kind==='incident'?'КАДР-ДОКАЗАТЕЛЬСТВО':'ПОДТВЕРЖДЕНИЕ ЭТАПА'}</span><h2>${esc(item.title)}</h2></div><button data-close-evidence aria-label="Закрыть">×</button></header><div class="evidence-layout"><div class="evidence-image"><img src="${item.image}" alt="Кадр ${fullDateTime(item.timestamp)}">${overlay}</div><aside><dl><div><dt>Камера</dt><dd>${esc(item.camera)}</dd></div><div><dt>Время</dt><dd>${fullDateTime(item.timestamp)}</dd></div>${item.impact?`<div><dt>Влияние</dt><dd>${esc(item.impact)}</dd></div>`:''}</dl><p>${esc(item.detail)}</p></aside></div></section></div>`;
}

function operationCameraPanel() {
  const event=controlEvent(),frame=controlEvidence(),frames=eventEvidence(event);
  if(!frame)return '';
  return `<section class="camera-panel operation-camera"><div class="camera-top"><div><b>${esc(frame.camera)}</b><span>${event.kind==='note'?'проверка зоны':'серия события'}</span></div><time>${frame.dateLabel} · ${frame.time}</time></div><div class="camera-canvas"><img class="scene-image" src="${frame.image}" alt="${esc(event.type)}">${incidentOverlay(frame,event)}</div><div class="evidence-filmstrip">${frames.map(item=>`<button data-control-evidence="${item.id}" class="${item.id===frame.id?'active':''}"><img src="${item.image}" alt=""><span>${item.time}</span></button>`).join('')}</div></section>`;
}

function operationDecisionPanel() {
  const event=controlEvent(),frame=controlEvidence(),isNote=event.kind==='note',a=dateValue(event.start),b=dateValue(event.end);
  const machineCount=frame?.boxes.filter(isMachine).length||0;
  return `<aside class="decision-panel operation-detail ${isNote?'note':''}"><div class="decision-head"><div><span>${isNote?'ОТМЕТКА НА КАДРЕ':'СОБЫТИЕ СМЕНЫ'}</span><h2>${esc(event.type)}</h2></div><b class="status-badge ${isNote?'note':'bad'}">${isNote?'контекст':'проверить'}</b></div><div class="operation-metrics"><div><span>Длительность</span><b>${durationLabel(a,b)}</b></div><div><span>Камера</span><b>${esc(frame?.camera||'—')}</b></div><div><span>Техника в кадре</span><b>${machineCount}</b></div></div><p class="operation-cause">${esc(event.cause)}</p><div class="operation-impact"><span>Влияние</span><b>${esc(event.impact)}</b></div>${isNote?'<button class="secondary" data-page="map">Открыть зоны площадки →</button>':''}</aside>`;
}

function shiftEventSwitcher() {
  return `<section class="shift-events"><div class="section-head"><div><h2>События смены</h2><span>25 июля 2024 · каждая карточка открывает свою серию кадров</span></div><b>${deviationEvents.filter(event=>event.kind!=='note').length} событий · 1 отметка зоны</b></div><div class="event-cards">${deviationEvents.map(event=>{const first=eventEvidence(event)[0],selected=event.id===state.controlEventId;return `<button class="event-card ${selected?'active':''} ${event.kind==='note'?'note':''}" data-control-event="${event.id}"><img src="${first?.image||''}" alt=""><span class="event-card-body"><i class="event-tone ${event.tone}"></i><span><b>${esc(event.type)}</b><small>${esc(first?.camera||'')} · ${durationLabel(dateValue(event.start),dateValue(event.end))}</small></span><em>${esc(event.kind==='note'?'На кадре':event.impact)}</em></span></button>`}).join('')}</div></section>`;
}

function legacyControlPageV15() {
  const critical=deviationEvents.filter(event=>event.kind!=='note'&&!event.impact.includes('не повлияло')).length;
  const observations=deviationEvents.filter(event=>event.kind!=='note'&&event.impact.includes('не повлияло')).length;
  return `<main class="workspace-shell"><div class="page-heading"><div><h1>Оперативный контроль</h1><span>Северный квартал · 25 июля 2024 · 5 камер</span></div><button class="secondary" data-export>Скачать отчёт</button></div><section class="summary-line operation-summary"><div class="summary-status bad"><span>Требуют проверки</span><b>${critical}</b></div><div><span>Наблюдения</span><b>${observations}</b></div><div><span>Отметки зон</span><b>1</b></div><div><span>Принятый этап</span><b>${esc(acceptedStage())}</b></div></section><div class="monitor-grid">${operationCameraPanel()}${operationDecisionPanel()}</div>${shiftEventSwitcher()}</main>`;
}

function operationalBox(box,index,analysis) {
  const [x,y,w,h]=box.bbox,stateForBox=analysis.boxStates[index]||{tone:'green',messages:[]};
  const label=stateForBox.messages.length?stateForBox.messages.join(' · '):box.className;
  return `<div class="det-box analyzed ${stateForBox.tone}" tabindex="0" style="left:${(x-w/2)*100}%;top:${(y-h/2)*100}%;width:${w*100}%;height:${h*100}%" aria-label="${esc(label)}"><span class="det-tooltip">${esc(label)}</span></div>`;
}

function operationalCameraPanel() {
  const stream=activeStream(),frame=operationalFrame(),analysis=analyzeOperationalFrame(frame),index=frame?.streamIndex||0;
  if(!frame)return '';
  return `<section class="camera-panel live-camera"><div class="camera-top"><div><b>${esc(frame.camera)}</b><span>По графику · ${esc(operationalPlanStage())}</span></div><time>${frame.dateLabel} · ${frame.time}</time></div><div class="camera-canvas progressive-frame" ${previewStyle(frame.image)}>${progressiveImage(frame.image,`${frame.camera} ${frame.time}`)}${frame.boxes.map((box,boxIndex)=>operationalBox(box,boxIndex,analysis)).join('')}</div><div class="centered-frame-nav"><div class="frame-stamp"><b>${frame.time}</b><span>${frame.dateLabel}</span></div><div class="centered-arrows"><button data-camera-step="-1" ${index===0?'disabled':''} aria-label="Предыдущий кадр">←</button><span>${index+1} / ${stream.length}</span><button data-camera-step="1" ${index===stream.length-1?'disabled':''} aria-label="Следующий кадр">→</button></div><div class="frame-position"><b>${esc(frame.camera)}</b><span>кадр ${index+1} из ${stream.length}</span></div></div></section>`;
}

function operationalConclusion(analysis,match,frame) {
  const plan=operationalPlanStage(),delay=delayMetrics(),alerts=analysis.alerts||[];
  const vlm=data.vlmObservations?.[frame?.id];
  const shortages=alerts.filter(item=>item.code==='shortage');
  const idle=alerts.filter(item=>item.code==='idle');
  const zones=alerts.filter(item=>item.code==='zone');
  const extras=[...new Set(alerts.filter(item=>item.code==='extra').map(item=>names[item.slug]||item.slug))];
  const differs=match.name!==plan;
  const lead=differs
    ? `По графику должен идти этап «${plan}», но набор техники со всех камер соответствует этапу «${match.name}» (${Math.round(match.score*100)}%).`
    : `Набор техники со всех камер соответствует текущему этапу «${plan}» (${Math.round(match.score*100)}%).`;
  const findings=[];
  if(shortages.length)findings.push(`Не выполнены требования: ${shortages.map(item=>item.message).join('; ')}.`);
  if(idle.length)findings.push(`Возможная потеря темпа: ${idle.map(item=>item.message).join('; ')}.`);
  if(zones.length)findings.push(`Нарушение размещения: ${zones.map(item=>item.message).join('; ')}.`);
  if(vlm?.scene_code==='ACCESS_ROAD'&&extras.length)findings.push('VLM относит технику к технологическому проезду: следует проверить, не перекрывает ли она движение.');
  if(vlm?.scene_code==='STORAGE_AREA'&&extras.length)findings.push('VLM видит технику в секторе складирования: следует проверить разрешённую зону для этих классов.');
  if(vlm?.scene_code==='CRANE_SECTOR'&&extras.some(name=>!name.toLowerCase().includes('кран')))findings.push('VLM видит рабочий сектор кранов: посторонняя техника в нём требует проверки диспетчером.');
  if(differs&&delay.days)findings.push(`Несовпадение этапов согласуется с расчётным отставанием ${delay.days} ${dayWord(delay.days)}.`);
  if(extras.length)findings.push(`На выбранном кадре вне профиля плана: ${extras.join(', ')}.`);
  if(state.readiness)findings.push(`По загруженному проектному виду визуальная готовность оценивается в ${state.readiness.score}% при ${state.readiness.confidence} уверенности сравнения.`);
  if(!findings.length)findings.push('Критических отклонений на выбранном временном срезе не обнаружено.');
  return `<div class="vlm-context operational-conclusion"><span>ЗАКЛЮЧЕНИЕ VLM + АНАЛИТИКА</span><b>${differs?'Этап не совпадает с графиком':'Работы соответствуют графику'}</b><p>${esc(lead)} ${esc(findings.join(' '))}</p></div>`;
}

function equipmentPanel() {
  const frame=operationalFrame(),analysis=analyzeOperationalFrame(frame);
  const match=rankedStages(analysis.site)[0]||{name:'Не определён',score:0};
  return `<aside class="decision-panel equipment-panel"><div class="decision-head"><div><span>АНАЛИЗ ПЛОЩАДКИ</span><h2>Техника и отклонения</h2></div><b class="status-badge ${analysis.alerts.some(item=>item.tone==='red')?'bad':analysis.alerts.length?'note':'ok'}">${analysis.alerts.length||'норма'}</b></div><div class="stage-match"><span>Наблюдается по всем камерам</span><div><b>${esc(match.name)}</b><strong>${Math.round(match.score*100)}%</strong></div></div>${operationalConclusion(analysis,match,frame)}<div class="equipment-table-head"><span>Объект</span><span>Кадр</span><span>Площадка</span><span>Нужно</span></div><div class="equipment-table">${analysis.rows.map(row=>`<div class="equipment-table-row ${row.status}"><span><i class="equipment-icon">${icon(row.slug)}</i><span><b>${esc(row.label)}</b><small>${esc(row.role)} · ${row.cameras.length} ${cameraWord(row.cameras.length)}</small></span></span><strong>${row.frameActual}</strong><strong>${row.actual}</strong><em>${row.expected??'—'}</em></div>`).join('')}</div><div class="auto-alerts">${analysis.alerts.length?analysis.alerts.map(alert=>`<article class="${alert.tone}"><i></i><span><b>${esc(alert.title)}</b><small>${esc(alert.message)}</small></span>${alert.code==='zone'?'<button class="alert-link" data-page="map">Карта зон →</button>':''}</article>`).join(''):'<div class="no-alerts"><b>Отклонений нет</b><span>Все требования календарного этапа выполнены.</span></div>'}</div></aside>`;
}

function controlPage() {
  const stream=activeStream(),analysis=analyzeOperationalFrame(),match=rankedStages(analysis.site)[0]||{name:'Не определён',score:0},delay=delayMetrics(),fact=acceptedStage();
  const readiness=state.projectReference?(state.readiness?`${state.readiness.score}%`:'Расчёт…'):'Настроить';
  return `<main class="workspace-shell"><div class="page-heading"><div><h1>Контроль площадки</h1><span>${operationalFrame()?.dateLabel||'—'} · ${analysis.site.cameraCount} ${cameraWord(analysis.site.cameraCount)}</span></div><div class="heading-actions"><label>Камера<select id="camera-select">${cameraNames.map(camera=>`<option ${camera===state.selectedCamera?'selected':''}>${camera}</option>`).join('')}</select></label><label>Подтверждённый этап<select id="operation-stage"><option value="__auto__" ${state.stageMode==='auto'?'selected':''}>Авто · ${esc(match.name)}</option>${profiles.map(profile=>`<option value="${esc(profile.name)}" ${state.stageMode==='manual'&&profile.name===state.acceptedStage?'selected':''}>${esc(profile.name)}</option>`).join('')}</select></label><button class="secondary" data-export>Скачать отчёт</button></div></div><section class="stage-status-strip"><div class="planned"><span>ПО ГРАФИКУ СЕЙЧАС</span><b>${esc(operationalPlanStage())}</b></div><div><span>НАБЛЮДАЕТСЯ</span><b>${esc(match.name)} · ${Math.round(match.score*100)}%</b></div><button class="readiness-status" data-project-dialog><span>ГОТОВНОСТЬ ПО ПРОЕКТУ</span><b>${readiness}</b></button><strong class="${delay.days?'late':'ok'}">${delay.days?`Отставание ${delay.days} ${dayWord(delay.days)}`:'По графику'}</strong></section><div class="camera-context"><span>${esc(state.selectedCamera)}</span><b>${stream.length} кадров</b><i></i><span>${operationalFrame()?.dateLabel||'—'}</span><i></i><span>08:00 — ${stream.at(-1)?.time||'—'}</span></div><div class="monitor-grid control-grid">${operationalCameraPanel()}${equipmentPanel()}</div></main>`;
}

function roleFor(profile, slug) {
  if ((profile.required||{})[slug] !== undefined) return 'required';
  if ((profile.any||[]).includes(slug)) return 'any';
  if ((profile.optional||[]).includes(slug)) return 'optional';
  return 'off';
}

function legacyPlanPage() {
  const current=acceptedStage(), plan=plannedStage(), profile=profileFor(current), f=currentFrame(), delay=delayMetrics(), windows=scheduleWindows();
  const relevant=[...new Set([...Object.keys(profile.required||{}),...(profile.any||[]),...(profile.optional||[])])];
  const rows=state.showAllClasses?equipmentClasses:relevant;
  const observedDays=Math.max(1,Math.round(delay.observedDays)),totalDays=schedule.reduce((sum,x)=>sum+x.days,0);
  return `<main class="workspace-shell"><div class="page-heading"><div><h1>План работ</h1><span>Этапы, длительности и наблюдаемое выполнение</span></div><button class="primary" data-save-plan>Сохранить</button></div><section class="stage-board"><article><span>ПО ГРАФИКУ СЕЙЧАС</span><h2>${esc(plan)}</h2><small>${shortDate(plannedWindow().start)} — ${shortDate(plannedWindow().end)}</small></article><article><span>СИСТЕМА НАБЛЮДАЕТ</span><h2>${esc(autoStage())}</h2><div class="confidence-line"><i><b style="width:${data.stageScores[0].score*100}%"></b></i><strong>${pct(data.stageScores[0].score)}</strong></div><small>${observedDays} ${dayWord(observedDays)} подтверждается историей</small></article><article><span>ПРИНЯТЫЙ ЭТАП</span><div class="mode-switch"><button data-stage-mode="auto" class="${state.stageMode==='auto'?'active':''}">Авто</button><button data-stage-mode="manual" class="${state.stageMode==='manual'?'active':''}">Вручную</button></div>${state.stageMode==='manual'?`<select id="accepted-stage">${profiles.map(p=>`<option ${p.name===state.acceptedStage?'selected':''}>${p.name}</option>`).join('')}</select>`:`<h2>${esc(current)}</h2>`}</article><article class="delay-card"><span>РАСЧЁТ ПО ИСТОРИИ</span><h2>${delay.days?`+${delay.days} ${dayWord(delay.days)}`:'По графику'}</h2><small>${delay.days?'Наблюдаемый этап начался позже плановой границы':'Наблюдения укладываются в план'}</small></article></section><section class="plan-editor"><div class="section-head"><div><h2>Календарный план</h2><span>${schedule.length} ${stageWord(schedule.length)} · ${totalDays} ${dayWord(totalDays)}</span></div><div class="plan-actions"><label>Начало <input id="plan-start" type="date" value="${state.planStart}"></label><button class="secondary" data-add-stage>+ Добавить этап</button></div></div><div class="plan-list">${schedule.map((item,index)=>{const win=windows[index];return `<article class="plan-item" draggable="true" data-stage-id="${item.id}"><button class="drag-handle" aria-label="Перетащить этап" title="Перетащить">⋮⋮</button><b class="stage-number">${index+1}</b><label><span>Этап</span><select data-schedule-name="${item.id}">${profiles.map(p=>`<option ${p.name===item.name?'selected':''}>${p.name}</option>`).join('')}</select></label><label><span>Длительность</span><div class="duration-input"><input data-schedule-days="${item.id}" type="number" min="1" value="${item.days}"><em>дней</em></div></label><div class="stage-dates"><span>${shortDate(win.start)}</span><i>→</i><span>${shortDate(win.end)}</span></div><div class="stage-actions"><button data-move-stage="${item.id}" data-direction="-1" ${index===0?'disabled':''} aria-label="Поднять этап">↑</button><button data-move-stage="${item.id}" data-direction="1" ${index===schedule.length-1?'disabled':''} aria-label="Опустить этап">↓</button><button data-remove-stage="${item.id}" ${schedule.length===1?'disabled':''} aria-label="Удалить этап">×</button></div></article>`}).join('')}</div></section>${scheduleStrip()}<section class="requirements"><div class="section-head"><div><h2>Техника для принятого этапа</h2><span>${esc(current)} · ${profile.source}</span></div><button class="secondary" data-toggle-classes>${state.showAllClasses?'Только используемые':'Все 14 классов'}</button></div><div class="requirement-head"><span>Техника</span><span>Роль</span><span>Минимум</span><span>На кадре</span><span>Состояние</span></div>${rows.map(slug=>{const role=roleFor(profile,slug),count=f.counts[slug]||0,min=(profile.required||{})[slug]||1;const ok=role==='required'?count>=min:role==='any'?(profile.any||[]).some(x=>(f.counts[x]||0)>0):true;return `<div class="requirement-row"><span><i class="equipment-icon">${icon(slug)}</i><b>${esc(names[slug])}</b></span><select data-role="${slug}"><option value="required" ${role==='required'?'selected':''}>Обязательная</option><option value="any" ${role==='any'?'selected':''}>Одна из группы</option><option value="optional" ${role==='optional'?'selected':''}>Допустимая</option><option value="off" ${role==='off'?'selected':''}>Не используется</option></select><input data-min="${slug}" type="number" min="0" value="${min}" ${role==='required'?'':'disabled'}><b>${count}</b><em class="${ok?'ok':'bad'}">${role==='off'?'—':ok?'есть':'нет'}</em></div>`}).join('')}</section></main>`;
}

function planPage() {
  const current=acceptedStage(),profile=profileFor(current),f=operationalFrame(),site=siteSnapshot(f?.streamIndex),delay=delayMetrics(),windows=scheduleWindows(),observed=rankedStages(site)[0]||{name:'Нет данных',score:0},plan=operationalPlanWindow();
  const relevant=[...new Set([...Object.keys(profile.required||{}),...(profile.any||[]),...(profile.optional||[])])];
  const rows=state.showAllClasses?equipmentClasses:relevant;
  const totalDays=schedule.reduce((sum,item)=>sum+item.days,0);
  const planItems=schedule.map((item,index)=>{const win=windows[index];return `<article class="plan-item" draggable="true" data-stage-id="${item.id}"><span class="drag-handle" aria-label="Перетащить этап" title="Зажмите и перетащите">⠿</span><b class="stage-number">${index+1}</b><label><span>Этап</span><select data-schedule-name="${item.id}">${profiles.map(p=>`<option ${p.name===item.name?'selected':''}>${p.name}</option>`).join('')}</select></label><label><span>Длительность</span><div class="duration-input"><input data-schedule-days="${item.id}" type="number" min="1" value="${item.days}"><em>дней</em></div></label><div class="stage-dates"><span>${numericDate(win.start)}</span><i>—</i><span>${numericDate(win.end)}</span></div><div class="stage-actions"><button data-remove-stage="${item.id}" ${schedule.length===1?'disabled':''} aria-label="Удалить этап" title="Удалить этап">×</button></div></article>`}).join('');
  const requirementRows=rows.map(slug=>{const role=roleFor(profile,slug),count=site.counts[slug]||0,min=(profile.required||{})[slug]||1;const ok=role==='required'?count>=min:role==='any'?(profile.any||[]).some(x=>(site.counts[x]||0)>0):true;return `<div class="requirement-row"><span><i class="equipment-icon">${icon(slug)}</i><b>${esc(names[slug])}</b></span><select data-role="${slug}"><option value="required" ${role==='required'?'selected':''}>Обязательная</option><option value="any" ${role==='any'?'selected':''}>Одна из группы</option><option value="optional" ${role==='optional'?'selected':''}>Допустимая</option><option value="off" ${role==='off'?'selected':''}>Не используется</option></select><input data-min="${slug}" type="number" min="0" value="${min}" ${role==='required'?'':'disabled'}><b>${count}</b><em class="${ok?'ok':'bad'}">${role==='off'?'—':ok?'есть':'нет'}</em></div>`}).join('');
  const delayDetail=delay.days&&delay.planned?(delay.reason==='start'?`Плановый старт ${numericDate(delay.planned.start)}, по камерам ${numericDate(delay.observedStart)}`:`Плановое завершение ${numericDate(delay.planned.end)}, по камерам ${numericDate(delay.observedEnd)}`):'Наблюдаемый этап укладывается в плановые даты';
  return `<main class="workspace-shell"><div class="page-heading"><div><h1>План работ</h1><span>Плановые даты и этапы, подтверждённые камерами</span></div><button class="primary" data-save-plan>Сохранить</button></div><section class="stage-board plan-status"><article class="current-plan-card"><span>ПО ГРАФИКУ СЕЙЧАС</span><h2>${esc(plan.name)}</h2><small>${numericDate(plan.start)} — ${numericDate(plan.end)}</small><em>СЕЙЧАС</em></article><article><span>НАБЛЮДАЕТСЯ ПО КАМЕРАМ</span><h2>${esc(observed.name)}</h2><small>${Math.round(observed.score*100)}% · текущий временной срез</small></article><article><span>ПОДТВЕРЖДЁННЫЙ ЭТАП</span><div class="mode-switch"><button data-stage-mode="auto" class="${state.stageMode==='auto'?'active':''}">Авто</button><button data-stage-mode="manual" class="${state.stageMode==='manual'?'active':''}">Вручную</button></div>${state.stageMode==='manual'?`<select id="accepted-stage">${profiles.map(p=>`<option ${p.name===state.acceptedStage?'selected':''}>${p.name}</option>`).join('')}</select>`:`<h2>${esc(current)}</h2>`}</article><article class="${delay.days?'delay-card':'on-time-card'}"><span>ОТНОСИТЕЛЬНО ПЛАНА</span><h2>${delay.days?`Отставание ${delay.days} ${dayWord(delay.days)}`:'Идём по графику'}</h2><small>${delayDetail}</small></article></section>${scheduleStrip()}<section class="plan-editor"><div class="section-head"><div><h2>Настройка календаря</h2><span>Перетаскивайте этапы за значок слева · даты пересчитываются сразу</span></div><div class="plan-actions"><label>Дата начала проекта <input id="plan-start" type="date" value="${state.planStart}"></label><button class="secondary" data-add-stage>+ Добавить этап</button></div></div><div class="plan-list">${planItems}</div></section><section class="requirements"><div class="section-head"><div><h2>Техника подтверждённого этапа</h2><span>${esc(current)} · ${profile.source}</span></div><button class="secondary" data-toggle-classes>${state.showAllClasses?'Только используемые':'Все 14 классов'}</button></div><div class="requirement-head"><span>Техника</span><span>Роль</span><span>Минимум</span><span>На площадке</span><span>Состояние</span></div>${requirementRows}</section></main>`;
}

const zoneCenter = zone => zone.points.reduce((sum,p)=>[sum[0]+p[0]/zone.points.length,sum[1]+p[1]/zone.points.length],[0,0]);
const zonePoints = zone => zone.points.map(p=>p.join(',')).join(' ');

function zoneSvg(zone) {
  const vertices=state.editZones?zone.points.map((p,i)=>`<circle data-vertex="${i}" data-zone="${zone.id}" cx="${p[0]}" cy="${p[1]}" r="1.25"/>`).join(''):'';
  const edges=state.editZones?zone.points.map((p,i)=>{const q=zone.points[(i+1)%zone.points.length],x=(p[0]+q[0])/2,y=(p[1]+q[1])/2;return `<g data-edge="${i}" data-zone="${zone.id}"><circle cx="${x}" cy="${y}" r="1.15"/><text x="${x}" y="${y+.45}">+</text></g>`}).join(''):'';
  return `<g class="zone ${zone.color}"><polygon data-shape="${zone.id}" points="${zonePoints(zone)}"/>${vertices}${edges}</g>`;
}

function legacyMapPage() {
  const f=currentFrame(), alert=warnings()[0];
  return `<main class="workspace-shell"><div class="page-heading"><div><h1>Карта площадки</h1><span>${f.dateLabel} · ${f.time}</span></div><div class="heading-actions"><label class="secondary upload">Загрузить подложку<input id="map-upload" type="file" accept="image/*"></label><button class="${state.editZones?'primary':'secondary'}" data-edit-zones>${state.editZones?'Готово':'Изменить зоны'}</button></div></div>${state.editZones?`<div class="edit-toolbar"><span>Перетаскивайте вершины или границу зоны</span><button class="secondary" data-draw-zone>${state.drawing?'Завершить обвод':'Новая зона'}</button></div>`:''}<div class="map-layout"><section class="site-card"><div class="site-map ${state.editZones?'editing':''} ${state.drawing?'drawing':''}" id="site-map"><img class="scene-image" src="${state.mapBackground||f.image}" alt="План строительной площадки">${syntheticMachineOverlay(f)}<svg viewBox="0 0 100 100" preserveAspectRatio="none">${zones.map(zoneSvg).join('')}${state.draft.length?`<polyline class="draft" points="${state.draft.map(p=>p.join(',')).join(' ')}"/>`:''}</svg>${zones.map(z=>{const minX=Math.min(...z.points.map(p=>p[0])),minY=Math.min(...z.points.map(p=>p[1]));return `<b class="zone-label" data-zone-label="${z.id}" style="left:${minX+2}%;top:${minY+2}%">${esc(z.name)}</b>`}).join('')}${f.boxes.map((b,i)=>detectorBox(b,i)).join('')}</div>${frameRail()}</section><aside class="zones-panel"><div class="zones-status ${alert?'bad':'ok'}"><span>События на карте</span><b>${alert&&alert.route==='map'?'1':'0'}</b></div>${zones.map(z=>{const count=f.boxes.filter(b=>zoneFor(b)?.id===z.id).length;const issue=alert&&z.id==='storage'&&state.scenario==='wrong-zone';return `<div class="zone-row ${issue?'issue':''}"><i class="${z.color}"></i><div>${state.editZones?`<input data-zone-name="${z.id}" value="${esc(z.name)}" aria-label="Название зоны">`:`<b>${esc(z.name)}</b>`}<span>${count} объектов${issue?' · требуется проверка':''}</span></div></div>`}).join('')}</aside></div></main>`;
}

function legacyMapPageV15() {
  const event=deviationEvents.find(item=>item.id==='wrong-zone'),frames=eventEvidence(event);
  const f=data.incidentEvidence?.find(item=>item.id===state.mapEvidenceId)||frames[0];
  const outOfZone=f?.boxes.filter(box=>box.classSlug==='excavator'&&zoneFor(box)?.id==='storage')||[];
  if(!f)return '';
  return `<main class="workspace-shell"><div class="page-heading"><div><h1>Зоны площадки</h1><span>${esc(f.camera)} · ${f.dateLabel} · ${f.time}</span></div><div class="heading-actions"><label class="secondary upload">Загрузить подложку<input id="map-upload" type="file" accept="image/*"></label><button class="${state.editZones?'primary':'secondary'}" data-edit-zones>${state.editZones?'Готово':'Редактировать границы'}</button></div></div>${state.editZones?`<div class="edit-toolbar"><span>Тяните вершину или весь многоугольник; «+» разбивает ребро</span><button class="secondary" data-draw-zone>${state.drawing?'Завершить обвод':'Новая зона'}</button></div>`:''}<div class="map-layout"><section class="site-card"><div class="site-map ${state.editZones?'editing':''} ${state.drawing?'drawing':''}" id="site-map"><img class="scene-image" src="${state.mapBackground||f.image}" alt="Разметка зон площадки"><svg viewBox="0 0 100 100" preserveAspectRatio="none">${zones.map(zoneSvg).join('')}${state.draft.length?`<polyline class="draft" points="${state.draft.map(p=>p.join(',')).join(' ')}"/>`:''}</svg>${zones.map(z=>{const minX=Math.min(...z.points.map(p=>p[0])),minY=Math.min(...z.points.map(p=>p[1]));return `<b class="zone-label" data-zone-label="${z.id}" style="left:${minX+2}%;top:${minY+2}%">${esc(z.name)}</b>`}).join('')}${f.boxes.filter(box=>!outOfZone.includes(box)).map((box,index)=>detectorBox(box,index)).join('')}${incidentOverlay(f,event)}</div><div class="evidence-filmstrip">${frames.map(item=>`<button data-map-evidence="${item.id}" class="${item.id===f.id?'active':''}"><img src="${item.image}" alt=""><span>${item.time}</span></button>`).join('')}</div></section><aside class="zones-panel"><div class="zones-status note"><span>Отметки на выбранном кадре</span><b>${outOfZone.length}</b></div>${zones.map(z=>{const count=f.boxes.filter(box=>zoneFor(box)?.id===z.id).length,issue=z.id==='storage'&&outOfZone.length>0;return `<div class="zone-row ${issue?'issue':''}"><i class="${z.color}"></i><div>${state.editZones?`<input data-zone-name="${z.id}" value="${esc(z.name)}" aria-label="Название зоны">`:`<b>${esc(z.name)}</b>`}<span>${count} объектов${issue?' · экскаватор отмечен на кадре':''}</span></div></div>`}).join('')}</aside></div></main>`;
}

function mapPage() {
  const f=operationalFrame(),analysis=analyzeOperationalFrame(f),stream=activeStream(),active=activeZones();
  if(!f)return '';
  const zoneRows=active.map(zone=>{const slugs=zoneEquipmentSlugs(zone),count=f.boxes.filter(box=>zoneFor(box,f.camera)?.id===zone.id).length,issue=count>0,visibility=zoneVisibility(f,zone);const picker=`<fieldset class="zone-equipment-picker compact">${equipmentClasses.map(slug=>`<label><input type="checkbox" data-zone-equipment-toggle="${zone.id}" value="${slug}" ${slugs.includes(slug)?'checked':''}><span>${icon(slug)}${esc(names[slug])}</span></label>`).join('')}</fieldset>`;return `<div class="zone-row forbidden ${issue?'issue':''}"><i></i><div>${state.editZones?`<input data-zone-name="${zone.id}" value="${esc(zone.name)}" aria-label="Название зоны">${picker}`:`<b>${esc(zone.name)}</b><span class="zone-equipment-icons">${slugs.map(slug=>`<i title="${esc(names[slug])}">${icon(slug)}</i>`).join('')}<em>Въезд запрещён: ${esc(slugs.map(slug=>names[slug]).join(', '))}</em></span>`}<span class="zone-metrics"><b>Видимость ${visibility===undefined?'рассчитывается':`${visibility}%`}</b><em>${issue?`${count} ${objectWord(count)} с нарушением`:'нарушений нет'}</em></span></div>${state.editZones?`<button data-delete-zone="${zone.id}" aria-label="Удалить зону">×</button>`:''}</div>`}).join('');
  const onboarding=`<div class="zone-onboarding"><i>${icon('notification')}</i><h2>Нужно разметить запретные зоны</h2><p>Выберите один или несколько типов техники и обведите область, куда им нельзя заезжать.</p><button class="primary" data-open-zone-wizard>Начать разметку</button></div>`;
  return `<main class="workspace-shell"><div class="page-heading"><div><h1>Запретные зоны</h1><span>${esc(state.selectedCamera)} · ${f.dateLabel} · ${f.time}</span></div><div class="heading-actions"><label>Камера<select id="camera-select">${cameraNames.map(camera=>`<option ${camera===state.selectedCamera?'selected':''}>${camera}</option>`).join('')}</select></label>${active.length?`<button class="${state.editZones?'primary':'secondary'}" data-edit-zones>${state.editZones?'Готово':'Редактировать'}</button>`:''}</div></div>${state.editZones?`<div class="edit-toolbar"><span>${state.drawing?'Ставьте точки по границе запретной области':'Тяните вершину или весь многоугольник; «+» разбивает ребро'}</span>${state.drawing?'<button class="primary" data-draw-zone>Завершить зону</button>':'<button class="secondary" data-open-zone-wizard>+ Запретная зона</button>'}</div>`:''}<div class="map-layout"><section class="site-card"><div class="site-map progressive-frame ${state.editZones?'editing':''} ${state.drawing?'drawing':''}" id="site-map" ${previewStyle(f.image)}>${progressiveImage(f.image,`Запретные зоны ${state.selectedCamera}`)}<svg viewBox="0 0 100 100" preserveAspectRatio="none">${active.map(zoneSvg).join('')}${state.draft.length?`<polyline class="draft" points="${state.draft.map(point=>point.join(',')).join(' ')}"/>`:''}</svg>${active.map(zone=>{const minX=Math.min(...zone.points.map(point=>point[0])),minY=Math.min(...zone.points.map(point=>point[1])),slugs=zoneEquipmentSlugs(zone);return `<b class="zone-label forbidden-label" data-zone-label="${zone.id}" style="left:${minX+2}%;top:${minY+2}%"><span>${icon(slugs[0])}</span>${esc(zone.name)}${slugs.length>1?` · ${slugs.length} типа`:''}</b>`}).join('')}${f.boxes.map((box,index)=>operationalBox(box,index,analysis)).join('')}</div><div class="centered-frame-nav"><div class="frame-stamp"><b>${f.time}</b><span>${f.dateLabel}</span></div><div class="centered-arrows"><button data-camera-step="-1" ${f.streamIndex===0?'disabled':''} aria-label="Предыдущий кадр">←</button><span>${f.streamIndex+1} / ${stream.length}</span><button data-camera-step="1" ${f.streamIndex===stream.length-1?'disabled':''} aria-label="Следующий кадр">→</button></div><div class="frame-position"><b>${esc(f.camera)}</b><span>кадр ${f.streamIndex+1} из ${stream.length}</span></div></div></section><aside class="zones-panel"><div class="zones-status ${analysis.alerts.some(item=>item.code==='zone')?'note':'ok'}"><span>Запретные зоны камеры</span><b>${active.length}</b></div>${active.length?`${zoneRows}<button class="add-zone-button" data-open-zone-wizard>+ Добавить запретную зону</button>`:onboarding}</aside></div></main>`;
}

function legacyHistoryPage() {
  const frames=data.session.frames,f=currentFrame(),machines=f.boxes.filter(isMachine),alert=warnings()[0];
  const grouped=[...new Set(frames.map(x=>x.dateLabel))].map(date=>{const items=frames.filter(x=>x.dateLabel===date);return {date,frames:items.length,cranes:Math.max(...items.map(x=>x.boxes.filter(b=>b.classSlug==='tower-crane').length)),workers:Math.max(...items.map(x=>x.boxes.filter(b=>b.classSlug==='person').length))}});
  return `<main class="workspace-shell"><div class="page-heading"><div><h1>История наблюдений</h1><span>${frames.length} контрольных дат · единый ракурс Torre H</span></div><button class="secondary" data-export>Скачать отчёт</button></div><div class="history-layout"><section class="history-view"><div class="camera-top"><div><b>${f.cameraId}</b><span>${f.demo?'контрольный сценарий':'исходный кадр'}</span></div><time>${f.dateLabel} · ${f.time}</time></div><div class="camera-canvas"><img class="scene-image" src="${f.image}" alt="Кадр ${f.sourceFrame}">${syntheticMachineOverlay(f)}${f.boxes.map((b,i)=>detectorBox(b,i)).join('')}</div>${frameRail()}</section><aside class="frame-facts"><span>ВЫБРАННЫЙ КАДР</span><h2>${f.dateLabel}</h2><b>${f.time}</b><dl><div><dt>Техника</dt><dd>${machines.length}</dd></div><div><dt>Работники</dt><dd>${f.boxes.filter(b=>b.classSlug==='person').length}</dd></div><div><dt>Предупреждения</dt><dd class="${alert?'bad':'ok'}">${alert?1:0}</dd></div></dl>${alert?`<article><b>${esc(alert.title)}</b><span>${esc(alert.meta)}</span></article>`:''}</aside></div><div class="thumb-strip">${frames.map((x,i)=>`<button data-frame="${i}" class="${i===state.frame?'active':''}"><img src="${x.image}" alt=""><span>${x.dateLabel}<small>${x.time}</small></span></button>`).join('')}</div><section class="date-summary"><div class="section-head"><div><h2>Контрольные даты</h2><span>Сводка исходной разметки</span></div></div><div class="date-head"><span>Дата</span><span>Кадров</span><span>Кранов</span><span>Работников</span></div>${grouped.map(x=>`<button data-frame="${frames.findIndex(f=>f.dateLabel===x.date)}"><b>${x.date}</b><span>${x.frames}</span><span>${x.cranes}</span><span>${x.workers}</span></button>`).join('')}</section></main>`;
}

function historyPage() {
  const frames=data.session.frames,f=baseFrame(),machines=f.boxes.filter(isMachine),index=frames.indexOf(f);
  return `<main class="workspace-shell"><div class="page-heading"><div><h1>Ход строительства</h1><span>Единый ракурс Torre H · 20 ноября 2020 — 12 февраля 2021</span></div><button class="secondary" data-export>Скачать отчёт</button></div><div class="history-layout"><section class="history-view"><div class="camera-top"><div><b>${f.cameraId}</b><span>контрольная дата ${index+1} из ${frames.length}</span></div><time>${f.dateLabel} · ${f.time}</time></div><div class="camera-canvas"><img class="scene-image" src="${f.image}" alt="Ход строительства ${f.dateLabel}">${f.boxes.map((box,i)=>detectorBox(box,i)).join('')}</div></section><aside class="frame-facts"><span>СОСТОЯНИЕ НА ДАТУ</span><h2>${f.dateLabel}</h2><b>${f.time}</b><dl><div><dt>Этап</dt><dd>Монолитные конструкции</dd></div><div><dt>Техника</dt><dd>${machines.length}</dd></div><div><dt>Работники</dt><dd>${f.boxes.filter(box=>box.classSlug==='person').length}</dd></div></dl><article class="history-note"><b>${index===0?'Начало наблюдаемого интервала':index===frames.length-1?'Последнее подтверждённое состояние':'Промежуточное состояние'}</b><span>Сравнение выполняется только с кадрами этого же ракурса.</span></article></aside></div><div class="thumb-strip progress-thumbs">${frames.map((item,i)=>`<button data-frame="${i}" class="${i===state.frame?'active':''}"><img src="${item.image}" alt=""><span>${item.dateLabel}<small>${item.time}</small></span></button>`).join('')}</div></main>`;
}

function page() {
  return ({control:controlPage,plan:planPage,map:mapPage,history:historyPage}[state.page]||controlPage)();
}

function render() { app.innerHTML=`${header()}${page()}${notificationPanel()}${zoneWizard()}${projectReferenceDialog()}${evidenceModal()}`;bindEvents();setTimeout(()=>{preloadNearbyImages();scheduleReadinessAnalysis();scheduleZoneVisibility()},0); }

function downloadReport() {
  const f=operationalFrame(),analysis=analyzeOperationalFrame(f);
  const payload={время:f.timestamp,камера:f.camera,этап_по_графику:operationalPlanStage(),подтверждённый_этап:acceptedStage(),вероятный_этап_площадки:rankedStages(analysis.site)[0],готовность_по_проектному_виду:state.readiness,техника_на_выбранном_кадре:f.counts,техника_на_площадке:analysis.site.counts,источники_по_камерам:analysis.site.camerasByClass,режим_объединения:analysis.site.modeByClass,автоматические_отклонения:analysis.alerts,объекты:f.boxes.map((box,index)=>({...box,состояние:analysis.boxStates[index]})),зоны:activeZones(f.camera).map(zone=>({...zone,видимость_процентов:zoneVisibility(f,zone)})),расчётное_отставание_дней:delayMetrics().days,календарный_план:scheduleWindows()};
  const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
  const link=document.createElement('a');link.href=url;link.download='стройконтур-отчёт.json';link.click();URL.revokeObjectURL(url);
}

async function importProjectView(file) {
  const source=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file)});
  const image=await loadImage(source),limit=1280,scale=Math.min(1,limit/Math.max(image.naturalWidth,image.naturalHeight));
  const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.naturalWidth*scale));canvas.height=Math.max(1,Math.round(image.naturalHeight*scale));canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
  state.projectReference=canvas.toDataURL('image/jpeg',.82);state.projectReferenceName=file.name;state.readiness=null;
  localStorage.setItem('стройконтур-проект-v1',JSON.stringify({image:state.projectReference,name:state.projectReferenceName}));
}

function bindEvents() {
  document.querySelectorAll('[data-notifications]').forEach(el=>el.onclick=()=>{state.notificationsOpen=!state.notificationsOpen;render()});
  document.querySelectorAll('[data-project-dialog]').forEach(el=>el.onclick=()=>{state.projectDialogOpen=true;state.notificationsOpen=false;render()});
  document.querySelectorAll('[data-close-project-dialog]').forEach(el=>el.onclick=()=>{state.projectDialogOpen=false;render()});
  const projectUpload=document.querySelector('#project-view-upload');if(projectUpload)projectUpload.onchange=async()=>{const file=projectUpload.files?.[0];if(!file)return;await importProjectView(file);render()};
  document.querySelectorAll('[data-remove-project-view]').forEach(el=>el.onclick=()=>{state.projectReference=null;state.projectReferenceName='';state.readiness=null;localStorage.removeItem('стройконтур-проект-v1');render()});
  document.querySelectorAll('[data-zone-task]').forEach(el=>el.onclick=()=>{state.selectedCamera=el.dataset.zoneTask;state.cameraIndex=Math.min(2,Math.max(0,activeStream().length-1));state.page='map';state.notificationsOpen=false;state.zoneWizardOpen=true;state.zoneName='Запретная зона';state.zoneEquipments=['excavator'];render()});
  document.querySelectorAll('[data-open-zone-wizard]').forEach(el=>el.onclick=()=>{state.zoneWizardOpen=true;state.zoneName='Запретная зона';state.zoneEquipments=['excavator'];render()});
  document.querySelectorAll('[data-close-zone-wizard]').forEach(el=>el.onclick=()=>{state.zoneWizardOpen=false;render()});
  const zoneDraftName=document.querySelector('#zone-draft-name');if(zoneDraftName)zoneDraftName.oninput=()=>{state.zoneName=zoneDraftName.value};
  document.querySelectorAll('[data-zone-draft-equipment]').forEach(el=>el.onchange=()=>{const slug=el.dataset.zoneDraftEquipment;if(el.checked&&!state.zoneEquipments.includes(slug))state.zoneEquipments.push(slug);if(!el.checked&&state.zoneEquipments.length>1)state.zoneEquipments=state.zoneEquipments.filter(item=>item!==slug);render()});
  const startZoneDraw=document.querySelector('[data-start-zone-draw]');if(startZoneDraw)startZoneDraw.onclick=()=>{state.zoneName=zoneDraftName?.value.trim()||'Запретная зона';if(!state.zoneEquipments.length)return;state.zoneWizardOpen=false;state.editZones=true;state.drawing=true;state.draft=[];render()};
  document.querySelectorAll('[data-evidence]').forEach(el=>el.onclick=e=>{e.stopPropagation();state.evidenceId=el.dataset.evidence;render()});
  document.querySelectorAll('[data-close-evidence]').forEach(el=>el.onclick=()=>{state.evidenceId=null;render()});
  document.querySelectorAll('[data-page]').forEach(el=>el.onclick=()=>{state.page=el.dataset.page;render()});
  document.querySelectorAll('[data-control-event]').forEach(el=>el.onclick=()=>{state.controlEventId=el.dataset.controlEvent;state.controlEvidenceId=eventEvidence(controlEvent())[0]?.id;render()});
  document.querySelectorAll('[data-control-evidence]').forEach(el=>el.onclick=()=>{state.controlEvidenceId=el.dataset.controlEvidence;render()});
  document.querySelectorAll('[data-map-evidence]').forEach(el=>el.onclick=()=>{state.mapEvidenceId=el.dataset.mapEvidence;render()});
  document.querySelectorAll('[data-frame]').forEach(el=>el.onclick=()=>{state.frame=+el.dataset.frame;state.selectedBox=null;render()});
  document.querySelectorAll('[data-step]').forEach(el=>el.onclick=()=>{state.frame=Math.max(0,Math.min(data.session.frames.length-1,state.frame+(+el.dataset.step)));state.selectedBox=null;render()});
  document.querySelectorAll('[data-camera-step]').forEach(el=>el.onclick=()=>{state.cameraIndex=Math.max(0,Math.min(activeStream().length-1,state.cameraIndex+(+el.dataset.cameraStep)));render()});
  const cameraSelect=document.querySelector('#camera-select');if(cameraSelect)cameraSelect.onchange=()=>{state.selectedCamera=cameraSelect.value;state.cameraIndex=Math.min(2,Math.max(0,activeStream().length-1));state.drawing=false;state.draft=[];render()};
  const operationStage=document.querySelector('#operation-stage');if(operationStage)operationStage.onchange=()=>{if(operationStage.value==='__auto__'){state.stageMode='auto';state.acceptedStage=autoStage()}else{state.stageMode='manual';state.acceptedStage=operationStage.value}render()};
  const scenario=document.querySelector('#scenario-select');if(scenario)scenario.onchange=()=>{state.scenario=scenario.value;state.frame=data.session.frames.length-1;state.selectedBox=null;render()};
  document.querySelectorAll('[data-export]').forEach(el=>el.onclick=downloadReport);
  document.querySelectorAll('[data-stage-mode]').forEach(el=>el.onclick=()=>{state.stageMode=el.dataset.stageMode;if(state.stageMode==='auto')state.acceptedStage=autoStage();render()});
  const accepted=document.querySelector('#accepted-stage');if(accepted)accepted.onchange=()=>{state.acceptedStage=accepted.value;render()};
  const planStart=document.querySelector('#plan-start');if(planStart)planStart.onchange=()=>{state.planStart=planStart.value||state.planStart;render()};
  document.querySelectorAll('[data-schedule-name]').forEach(el=>el.onchange=()=>{const item=schedule.find(x=>x.id===el.dataset.scheduleName);if(item)item.name=el.value;render()});
  document.querySelectorAll('[data-schedule-days]').forEach(el=>el.onchange=()=>{const item=schedule.find(x=>x.id===el.dataset.scheduleDays);if(item)item.days=Math.max(1,+el.value||1);render()});
  const addStage=document.querySelector('[data-add-stage]');if(addStage)addStage.onclick=()=>{schedule.push({id:`stage-${Date.now()}`,name:profiles[0].name,days:14});render()};
  document.querySelectorAll('[data-move-stage]').forEach(el=>el.onclick=()=>{const index=schedule.findIndex(x=>x.id===el.dataset.moveStage),next=index+(+el.dataset.direction);if(index<0||next<0||next>=schedule.length)return;[schedule[index],schedule[next]]=[schedule[next],schedule[index]];render()});
  document.querySelectorAll('[data-remove-stage]').forEach(el=>el.onclick=()=>{if(schedule.length===1)return;const index=schedule.findIndex(x=>x.id===el.dataset.removeStage);if(index>=0)schedule.splice(index,1);render()});
  document.querySelectorAll('.plan-item').forEach(el=>{el.ondragstart=e=>{e.dataTransfer.setData('text/plain',el.dataset.stageId);el.classList.add('dragging')};el.ondragend=()=>el.classList.remove('dragging');el.ondragover=e=>e.preventDefault();el.ondrop=e=>{e.preventDefault();const from=e.dataTransfer.getData('text/plain'),to=el.dataset.stageId,a=schedule.findIndex(x=>x.id===from),b=schedule.findIndex(x=>x.id===to);if(a<0||b<0||a===b)return;const [moved]=schedule.splice(a,1);schedule.splice(b,0,moved);render()}});
  const toggle=document.querySelector('[data-toggle-classes]');if(toggle)toggle.onclick=()=>{state.showAllClasses=!state.showAllClasses;render()};
  document.querySelectorAll('[data-role]').forEach(el=>el.onchange=()=>{const p=profileFor(acceptedStage()),slug=el.dataset.role;delete p.required[slug];p.any=p.any.filter(x=>x!==slug);p.optional=p.optional.filter(x=>x!==slug);if(el.value==='required')p.required[slug]=1;if(el.value==='any')p.any.push(slug);if(el.value==='optional')p.optional.push(slug);render()});
  document.querySelectorAll('[data-min]').forEach(el=>el.onchange=()=>{const p=profileFor(acceptedStage()),slug=el.dataset.min;if(p.required[slug]!==undefined)p.required[slug]=Math.max(0,+el.value||0);render()});
  const save=document.querySelector('[data-save-plan]');if(save)save.onclick=()=>{localStorage.setItem('стройконтур-v6',JSON.stringify({planStart:state.planStart,stageMode:state.stageMode,acceptedStage:state.acceptedStage,schedule,profiles}));save.textContent='Сохранено ✓';setTimeout(()=>save.textContent='Сохранить',1400)};
  const edit=document.querySelector('[data-edit-zones]');if(edit)edit.onclick=()=>{state.editZones=!state.editZones;state.drawing=false;state.draft=[];if(!state.editZones)localStorage.setItem('стройконтур-запретные-зоны-v1',JSON.stringify({zonesByCamera}));render()};
  const draw=document.querySelector('[data-draw-zone]');if(draw)draw.onclick=()=>{if(state.drawing&&state.draft.length>=3){activeZones().push({id:`forbidden-${Date.now()}`,name:state.zoneName||'Запретная зона',equipmentSlugs:[...state.zoneEquipments],color:'red',points:state.draft.map(p=>[...p])});zoneRulesEnabled[state.selectedCamera]=true;localStorage.setItem('стройконтур-запретные-зоны-v1',JSON.stringify({zonesByCamera}))}state.draft=[];state.drawing=false;render()};
  document.querySelectorAll('[data-zone-name]').forEach(el=>el.oninput=()=>{const zone=activeZones().find(item=>item.id===el.dataset.zoneName);if(!zone)return;zone.name=el.value});
  document.querySelectorAll('[data-zone-equipment-toggle]').forEach(el=>el.onchange=()=>{const zone=activeZones().find(item=>item.id===el.dataset.zoneEquipmentToggle);if(!zone)return;const current=zoneEquipmentSlugs(zone),slug=el.value;if(el.checked&&!current.includes(slug))zone.equipmentSlugs=[...current,slug];if(!el.checked&&current.length>1)zone.equipmentSlugs=current.filter(item=>item!==slug);delete zone.equipmentSlug;localStorage.setItem('стройконтур-запретные-зоны-v1',JSON.stringify({zonesByCamera}));render()});
  document.querySelectorAll('[data-delete-zone]').forEach(el=>el.onclick=()=>{const index=activeZones().findIndex(zone=>zone.id===el.dataset.deleteZone);if(index>=0)activeZones().splice(index,1);zoneRulesEnabled[state.selectedCamera]=activeZones().length>0;localStorage.setItem('стройконтур-запретные-зоны-v1',JSON.stringify({zonesByCamera}));render()});
  const upload=document.querySelector('#map-upload');if(upload)upload.onchange=()=>{const file=upload.files[0];if(!file)return;const reader=new FileReader();reader.onload=()=>{state.mapBackgrounds[state.selectedCamera]=reader.result;render()};reader.readAsDataURL(file)};
  if(state.page==='map'&&state.editZones)bindZoneEditor();
}

function bindZoneEditor() {
  const map=document.querySelector('#site-map');if(!map)return;let drag=null;
  const zoneCollection=activeZones();
  const coord=e=>{const r=map.getBoundingClientRect();return [Math.max(0,Math.min(100,(e.clientX-r.left)/r.width*100)),Math.max(0,Math.min(100,(e.clientY-r.top)/r.height*100))]};
  const update=zone=>{const shape=map.querySelector(`[data-shape="${zone.id}"]`);if(shape)shape.setAttribute('points',zonePoints(zone))};
  map.onpointerdown=e=>{if(state.drawing)return;const vertex=e.target.closest('[data-vertex]'),shape=e.target.closest('[data-shape]');const id=vertex?.dataset.zone||shape?.dataset.shape;if(!id)return;const zone=zoneCollection.find(z=>z.id===id),start=coord(e);drag={zone,index:vertex?+vertex.dataset.vertex:null,start,original:zone.points.map(p=>[...p])};map.setPointerCapture(e.pointerId);e.preventDefault()};
  map.onpointermove=e=>{if(!drag)return;const p=coord(e);if(drag.index!==null)drag.zone.points[drag.index]=p;else{const dx=p[0]-drag.start[0],dy=p[1]-drag.start[1];drag.zone.points=drag.original.map(q=>[Math.max(0,Math.min(100,q[0]+dx)),Math.max(0,Math.min(100,q[1]+dy))])}update(drag.zone)};
  map.onpointerup=()=>{if(drag){zoneRulesEnabled[state.selectedCamera]=true;localStorage.setItem('стройконтур-запретные-зоны-v1',JSON.stringify({zonesByCamera}));drag=null;render()}};
  map.querySelectorAll('[data-edge]').forEach(el=>el.onclick=e=>{e.stopPropagation();const zone=zoneCollection.find(z=>z.id===el.dataset.zone),i=+el.dataset.edge,a=zone.points[i],b=zone.points[(i+1)%zone.points.length];zone.points.splice(i+1,0,[(a[0]+b[0])/2,(a[1]+b[1])/2]);zoneRulesEnabled[state.selectedCamera]=true;localStorage.setItem('стройконтур-запретные-зоны-v1',JSON.stringify({zonesByCamera}));render()});
  map.onclick=e=>{if(!state.drawing)return;state.draft.push(coord(e));render()};
}

function pointInPolygon(point, polygon) {
  const [x,y]=point;let inside=false;
  for(let i=0,j=polygon.length-1;i<polygon.length;j=i++){
    const [xi,yi]=polygon[i],[xj,yj]=polygon[j];
    if(((yi>y)!==(yj>y)) && x < (xj-xi)*(y-yi)/(yj-yi)+xi)inside=!inside;
  }
  return inside;
}

function zoneFor(box,camera=state.selectedCamera) {
  const [x,y,,h]=box.bbox, foot=[x*100,(y+h/2)*100];
  return activeZones(camera).find(z=>zoneEquipmentSlugs(z).includes(box.classSlug)&&pointInPolygon(foot,z.points));
}

async function calculateZoneVisibility(frame,zone) {
  const image=await loadImage(frame.image),width=180,height=Math.max(80,Math.round(180*image.naturalHeight/image.naturalWidth));
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const context=canvas.getContext('2d',{willReadFrequently:true});context.drawImage(image,0,0,width,height);
  const pixels=context.getImageData(0,0,width,height).data;
  let total=0,readable=0;
  for(let y=0;y<height;y+=2)for(let x=0;x<width;x+=2){const point=[(x+.5)/width*100,(y+.5)/height*100];if(!pointInPolygon(point,zone.points))continue;total++;const at=(y*width+x)*4,r=pixels[at],g=pixels[at+1],b=pixels[at+2],light=.299*r+.587*g+.114*b;const max=Math.max(r,g,b),min=Math.min(r,g,b);if(light>9&&light<247&&(max-min>3||light>24&&light<232))readable++}
  return total?Math.round(readable/total*100):0;
}

function scheduleZoneVisibility() {
  if(state.page!=='map'||state.visibilityBusy)return;
  const frame=operationalFrame(),active=activeZones();if(!frame||!active.length)return;
  const missing=active.filter(zone=>state.zoneVisibility[`${frame.id}|${zone.id}|${zone.points.flat().join(',')}`]===undefined);if(!missing.length)return;
  state.visibilityBusy=true;
  Promise.all(missing.map(async zone=>{const key=`${frame.id}|${zone.id}|${zone.points.flat().join(',')}`;return [key,await calculateZoneVisibility(frame,zone)]})).then(results=>{for(const [key,value] of results)state.zoneVisibility[key]=value;state.visibilityBusy=false;render()}).catch(()=>{state.visibilityBusy=false});
}

function zoneVisibility(frame,zone) {
  return state.zoneVisibility[`${frame.id}|${zone.id}|${zone.points.flat().join(',')}`];
}

function preloadNearbyImages() {
  const stream=activeStream(),index=Math.max(0,Math.min(state.cameraIndex,stream.length-1));
  const ordered=[stream[index],stream[index-1],stream[index+1],...stream].filter(Boolean);
  for(const item of [...new Map(ordered.map(frame=>[frame.image,frame])).values()]){const image=new Image();image.decoding='async';image.src=item.image}
}

fetch('data/real-session.json?v=22',{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error('Не удалось загрузить данные');return r.json()}).then(json=>{data=json;cameraStreams=buildCameraStreams(json.incidentEvidence||[]);state.frame=json.session.frames.length-1;state.cameraIndex=Math.min(state.cameraIndex,Math.max(0,activeStream().length-1));try{const saved=JSON.parse(localStorage.getItem('стройконтур-v6')),savedZones=JSON.parse(localStorage.getItem('стройконтур-запретные-зоны-v1')),savedProject=JSON.parse(localStorage.getItem('стройконтур-проект-v1'));if(saved){['planStart','stageMode','acceptedStage'].forEach(key=>{if(saved[key]!==undefined)state[key]=saved[key]});if(Array.isArray(saved.schedule)&&saved.schedule.length)schedule.splice(0,schedule.length,...saved.schedule);if(Array.isArray(saved.profiles))profiles.splice(0,profiles.length,...saved.profiles)}if(savedZones?.zonesByCamera)for(const camera of cameraNames)if(Array.isArray(savedZones.zonesByCamera[camera])){zonesByCamera[camera].splice(0,zonesByCamera[camera].length,...savedZones.zonesByCamera[camera]);zoneRulesEnabled[camera]=zonesByCamera[camera].length>0}if(savedProject?.image){state.projectReference=savedProject.image;state.projectReferenceName=savedProject.name||'Проектный вид'}}catch{}render()}).catch(error=>{app.innerHTML=`<div class="load-error"><h1>Не удалось открыть данные</h1><p>${esc(error.message)}</p></div>`});
