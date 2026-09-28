/** Build a compact, visually distinct demo selection from the two Kaggle datasets.
 *
 * The script reads original YOLO labels, converts only selected source images,
 * and updates dist/data/real-session.json. It never runs a detector.
 */

const args:Record<string,string> = {};
for(let index=0;index<Deno.args.length;index+=1){
  const value=Deno.args[index];
  if(value.startsWith('--')&&Deno.args[index+1])args[value.slice(2)]=Deno.args[index+1];
}
const progressRoot = args['progress-root'];
const videoRoot = args['video-root'];
const outRoot = args.out;
if (!progressRoot || !videoRoot || !outRoot) throw new Error('Нужны --progress-root, --video-root и --out');

const progressClasses = [
  ['Самосвал','dump-truck'], ['Бульдозер','bulldozer'], ['Автобетоносмеситель','mixer'],
  ['Мини-погрузчик','mini-loader'], ['Башенный кран','tower-crane'], ['Автокран','mobile-crane'],
  ['Грузовик','truck'], ['Работник','person']
];
const videoClasses = [
  ['Автобетоносмеситель','mixer'], ['Бетононасос','pump'], ['Бульдозер','bulldozer'],
  ['Буровая установка','drill'], ['Экскаватор','excavator'], ['Грузовик','truck'],
  ['Работник','person'], ['Каска','helmet'], ['Каток','roller'], ['Башенный кран','tower-crane'],
  ['Манипулятор','manipulator'], ['Мини-бульдозер','mini-bulldozer'], ['Автокран','mobile-crane'],
  ['Мусоровоз','garbage-truck'], ['Подъёмник','lift'], ['Самосвал','dump-truck'],
  ['Трактор','tractor'], ['Вилочный погрузчик','forklift']
];

const timeline = [
  { number:631, timestamp:'2020-11-20T11:13:33' },
  { number:76, timestamp:'2020-12-02T09:12:17' },
  { number:150, timestamp:'2021-01-06T11:05:02' },
  { number:501, timestamp:'2021-01-22T08:57:45' },
  { number:176, timestamp:'2021-02-12T09:01:19' }
];

const incidents = [
  { eventId:'shortage', camera:'Камера 7', picks:[5,6,7], prefix:'701' },
  { eventId:'required', camera:'Камера 5', picks:[0,30,59], prefix:'501' },
  { eventId:'idle', camera:'Камера 8', picks:[0,60,120,180,241,300], prefix:'801' },
  { eventId:'wrong-zone', camera:'Камера 9', picks:[0,20,40,59], prefix:'901' },
  { eventId:'extra', camera:'Камера 4', picks:[0,25,49], prefix:'401' },
  { eventId:'mismatch', camera:'Камера 7', picks:[0,10,60], prefix:'701' }
];

const pad = (value:number) => String(value).padStart(4,'0');
const dateLabel = (iso:string) => iso.slice(8,10)+'.'+iso.slice(5,7)+'.'+iso.slice(0,4);
const parseStamp = (name:string) => {
  const match=name.match(/_(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})_jpeg/);
  if(!match)throw new Error(`Нет времени в имени ${name}`);
  return `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}:${match[6]}`;
};

async function exists(path:string){try{await Deno.stat(path);return true}catch{return false}}
function progressPath(number:number){
  const group=number<=250?'1-250':number<=500?'251-500':number<=800?'501-800':'801-1049';
  return `${progressRoot}/${group}/${group}/IMG${number}.jpg`;
}
async function videoPath(prefix:string,index:number){
  const needle=`${prefix}_${String(index).padStart(3,'0')}_`;
  for(const split of ['train','valid','test']){
    const directory=`${videoRoot}/${split}/images`;if(!(await exists(directory)))continue;
    for await(const entry of Deno.readDir(directory))if(entry.isFile&&entry.name.startsWith(needle)&&entry.name.endsWith('.jpg'))return `${directory}/${entry.name}`;
  }
  throw new Error(`Не найден ${needle}`);
}
async function boxesFor(image:string, classes:string[][]){
  let label=image.replace('/images/','/labels/').replace(/\.jpg$/,'.txt');
  if(!(await exists(label)))label=image.replace(/\.jpg$/,'.txt');
  const text=await Deno.readTextFile(label), boxes:any[]=[];
  for(const line of text.trim().split(/\r?\n/)){
    const parts=line.trim().split(/\s+/).map(Number);if(parts.length<5)continue;
    const [classId,x,y,w,h]=parts,[className,classSlug]=classes[classId]||[`Класс ${classId}`,`class-${classId}`];
    boxes.push({classId,className,classSlug,bbox:[x,y,w,h],confidence:1});
  }
  return boxes;
}
function countsFor(boxes:any[]){
  const counts:Record<string,number>={};
  for(const box of boxes)if(!['person','helmet'].includes(box.classSlug))counts[box.classSlug]=(counts[box.classSlug]||0)+1;
  return counts;
}
async function convert(source:string,target:string,width=1440,quality=4){
  await Deno.mkdir(target.slice(0,target.lastIndexOf('/')),{recursive:true});
  const result=await new Deno.Command('ffmpeg',{args:['-loglevel','error','-i',source,'-vf',`scale=${width}:-2`,'-q:v',String(quality),'-y',target]}).output();
  if(!result.success)throw new Error(new TextDecoder().decode(result.stderr));
}

const sessionFrames=[];
for(const spec of timeline){
  const source=progressPath(spec.number),targetName=`torre-h-${pad(spec.number)}.jpg`;
  const boxes=await boxesFor(source,progressClasses);
  await convert(source,`${outRoot}/assets/timeline/${targetName}`);
  sessionFrames.push({timestamp:spec.timestamp,time:spec.timestamp.slice(11),dateLabel:dateLabel(spec.timestamp),cameraId:'Камера Torre H',image:`assets/timeline/${targetName}`,split:'исходная разметка',sourceFrame:spec.number,boxes,counts:countsFor(boxes)});
}

const incidentEvidence=[];
for(const event of incidents)for(const index of event.picks){
  const source=await videoPath(event.prefix,index),timestamp=parseStamp(source),targetName=`${event.eventId}-${event.prefix}-${String(index).padStart(3,'0')}.jpg`;
  const boxes=await boxesFor(source,videoClasses);
  await convert(source,`${outRoot}/assets/incidents/${targetName}`,960,7);
  incidentEvidence.push({id:`${event.eventId}-${event.prefix}-${String(index).padStart(3,'0')}`,eventId:event.eventId,timestamp,time:timestamp.slice(11),dateLabel:dateLabel(timestamp),camera:event.camera,image:`assets/incidents/${targetName}`,boxes,counts:countsFor(boxes)});
}

const dataPath=`${outRoot}/data/real-session.json`,data=JSON.parse(await Deno.readTextFile(dataPath));
const firstFrame=sessionFrames[0],lastFrame=sessionFrames.at(-1);
if(!firstFrame||!lastFrame)throw new Error('Не удалось собрать временную шкалу');
data.session={start:firstFrame.timestamp,end:lastFrame.timestamp,durationDays:Math.floor((Date.parse(lastFrame.timestamp)-Date.parse(firstFrame.timestamp))/86400000),frames:sessionFrames};
data.incidentEvidence=incidentEvidence;
data.observedCounts=countsFor(lastFrame.boxes);
data.source.progressFrames=1046;
await Deno.writeTextFile(dataPath,JSON.stringify(data,null,2)+'\n');
console.log(JSON.stringify({timeline:sessionFrames.map(frame=>[frame.timestamp,frame.sourceFrame]),incidentEvidence:incidentEvidence.length},null,2));
