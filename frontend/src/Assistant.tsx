import React,{useEffect,useState} from 'react';
import './assistant.css';
type API=(path:string,method?:string,body?:unknown)=>Promise<any>;
type Draft={amount:number|null;kind:string;category:string;note:string;date:string};
const categories=['Продукты','Кафе','Транспорт','Дом','Покупки','Здоровье','Развлечения','Подписки','Доход','Другое'];

export function Assistant({api,mode,month,onDone}:{api:API;mode:string;month:string;onDone:()=>Promise<void>}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[status,setStatus]=useState(''),[caps,setCaps]=useState<Record<string,boolean>|null>(null);
 const [kind,setKind]=useState('receipt'),[file,setFile]=useState<File|null>(null),[draft,setDraft]=useState<Draft|null>(null),[text,setText]=useState(''),[amount,setAmount]=useState('');
 const [question,setQuestion]=useState(''),[messages,setMessages]=useState<{question:string;answer:string;month:string}[]>([]);
 useEffect(()=>{let active=true;api('/capabilities').then(c=>{if(active)setCaps(c)}).catch(()=>{});return()=>{active=false}},[api]);
 async function run(fn:()=>Promise<void>){setBusy(true);setError('');setStatus('');try{await fn()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function recognize(){
  if(!file)return;
  if(file.size>6_000_000||!file.size)throw new Error('Выберите файл размером до 6 МБ.');
  const payload=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('Не удалось прочитать файл'));reader.readAsDataURL(file)});
  setDraft(null);setText('');
  const result=await api('/recognition/preview','POST',{kind,payload});setDraft(result.entry);setText(result.text);setAmount(result.entry.amount===null?'':String(result.entry.amount/100));
 }
 return <section className="panel assistant"><div className="section-head"><h2>{mode==='ИИ-чат'?'Ваш финансовый помощник':'Добавить из голоса или чека'}</h2><span className="pill">На вашем сервере</span></div>
 <p className="muted">{mode==='ИИ-чат'?'Небольшая локальная модель отвечает по сводке за выбранный месяц. Может ошибаться — проверяйте суммы в аналитике. История хранится только в этой открытой вкладке.':'Фото и аудио обрабатываются на сервере и удаляются после распознавания. Проверьте черновик перед сохранением. Голос: до 30 секунд. Файлы: до 6 МБ.'}</p>
 {error&&<div className="error" role="alert">{error}</div>}{status&&<p role="status">{status}</p>}
 {mode==='ИИ-чат'?<>
 {caps&&!caps.ai_chat&&<p className="notice">Модель сейчас недоступна. Можно повторить запрос позже.</p>}
 <div className="chat-log" aria-live="polite">{messages.map((m,i)=><div key={i}><div className="chat-question">{m.question}<small>{m.month}</small></div><div className="chat-answer">{m.answer}</div></div>)}</div>
 <form onSubmit={e=>{e.preventDefault();run(async()=>{const q=question.trim();if(!q)return;const r=await api('/ai/chat','POST',{question:q,month,history:messages.filter(m=>m.month===month).slice(-2).flatMap(m=>[{role:'user',content:m.question.slice(0,300)},{role:'assistant',content:m.answer.slice(0,300)}])});setMessages(m=>[...m.slice(-9),{question:q,answer:r.answer,month}]);setQuestion('')})}}><label>Вопрос о бюджете<textarea required maxLength={600} value={question} disabled={busy} onChange={e=>setQuestion(e.target.value)} placeholder="Как сократить расходы в этом месяце?"/></label><button className="primary" disabled={busy||!question.trim()}>{busy?'Помощник думает…':'Спросить'}</button></form>
 {messages.length>0&&<button disabled={busy} onClick={()=>setMessages([])}>Очистить переписку</button>}
 </>:<>
 <form onSubmit={e=>{e.preventDefault();run(recognize)}}><label>Что распознать<select disabled={busy} value={kind} onChange={e=>{setKind(e.target.value);setFile(null);setDraft(null)}}><option value="receipt">Фото чека</option><option value="voice">Голос / аудиофайл</option></select></label><label>{kind==='receipt'?'Чёткое фото целого чека (JPEG, PNG, WebP)':'Аудиозапись одной операции'}<input key={kind} type="file" disabled={busy} required accept={kind==='receipt'?'image/jpeg,image/png,image/webp':'audio/*,.ogg,.webm'} onChange={e=>{setFile(e.target.files?.[0]??null);setDraft(null)}}/></label>
 {kind==='voice'&&<p className="muted">Удобнее записать голосовое прямо боту в Telegram: «молоко сто двадцать рублей».</p>}
 {caps&&!caps[kind]&&<p className="notice">Распознавание сейчас недоступно. Попробуйте позже.</p>}
 <button className="primary" disabled={busy||!file}>{busy?'Обрабатываем…':'Распознать'}</button></form>
 {draft&&<form className="recognition-draft" onSubmit={e=>{e.preventDefault();run(async()=>{await api('/transactions','POST',{...draft,amount:Math.round(Number(amount)*100)});setDraft(null);setText('');setFile(null);setStatus('Операция сохранена.');await onDone()})}}><h3>Проверьте черновик</h3><details><summary>Распознанный текст</summary><pre>{text}</pre></details>{draft.amount===null&&<p className="notice">Сумма не определена однозначно. Укажите её вручную.</p>}<label>Сумма, ₽<input required type="number" min="0.01" max="1000000000" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)}/></label><label>Тип<select value={draft.kind} onChange={e=>setDraft({...draft,kind:e.target.value})}><option value="expense">Расход</option><option value="income">Доход</option></select></label><label>Категория<select value={draft.category} onChange={e=>setDraft({...draft,category:e.target.value})}>{categories.map(c=><option key={c}>{c}</option>)}</select></label><label>Дата<input type="date" required value={draft.date} onChange={e=>setDraft({...draft,date:e.target.value})}/></label><label>Описание<input maxLength={300} value={draft.note} onChange={e=>setDraft({...draft,note:e.target.value})}/></label><button className="primary" disabled={busy}>Подтвердить и сохранить</button><button type="button" disabled={busy} onClick={()=>{setDraft(null);setText('')}}>Отменить</button></form>}
 </>}{busy&&<p role="status" className="muted">На небольшом сервере обработка может занять до двух минут. Не закрывайте этот раздел.</p>}
 </section>
}
