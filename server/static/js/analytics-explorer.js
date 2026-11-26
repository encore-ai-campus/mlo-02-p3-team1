/* Read-only analysis tools; server remains the source of truth. */
(() => {
 'use strict';
 const main=document.querySelector('main.workspace'); if(!main)return;
 const user=document.body.dataset.adminId||'admin';
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n};
 const button=(text,fn,cls='btn-ghost')=>{const b=el('button',cls,text);b.type='button';if(fn)b.addEventListener('click',fn);return b};
 const read=(key,fallback)=>{try{return JSON.parse(localStorage.getItem('nv-explore:'+user+':'+key))||fallback}catch(_){return fallback}};
 const save=(key,value)=>{try{localStorage.setItem('nv-explore:'+user+':'+key,JSON.stringify(value))}catch(_){}};
 async function get(path,params){const r=await fetch(path+'?'+params.toString(),{credentials:'same-origin',headers:{Accept:'application/json'}});if(!r.ok){let d;try{d=await r.json()}catch(_){}throw Error(d?.error||(r.status===401||r.status===403?'다시 로그인하세요':'조회하지 못했습니다. 잠시 후 다시 시도하세요.'))}return r.json()}
 const dialog=el('dialog','explorer-dialog');const head=el('header','explorer-dialog-head');const title=el('h2');const close=button('닫기 ×',()=>dialog.close());head.append(title,close);const body=el('div','explorer-dialog-body');dialog.append(head,body);dialog.setAttribute('aria-labelledby','explorer-title');title.id='explorer-title';document.body.append(dialog);
 let cleanup=()=>{},lastTrigger=null,token=0;
 function open(name,trigger){if(dialog.open)dialog.close();cleanup();cleanup=()=>{};title.textContent=name;body.replaceChildren();lastTrigger=trigger;token++;dialog.showModal();return token}
 dialog.addEventListener('close',()=>{cleanup();cleanup=()=>{};token++;if(lastTrigger?.isConnected)lastTrigger.focus({preventScroll:true})});
 const error=(parent,e)=>{parent.replaceChildren(el('p','notice',e.message))};

 // Saved filter views: local to this browser and administrator; never store arbitrary URLs.
 const filter=main.querySelector('form[method=get], #analysis-filters');
 if(location.pathname==='/staff/events/'){
  const params=new URLSearchParams(location.search);const active=el('div','explorer-active-filters');
  const names={result:'결과',operation:'연산',reason:'실패 원인',run:'문제 실행',category:'분야',source:'데이터'};
  Object.entries(names).forEach(([key,label])=>{if(!params.get(key))return;const value=params.get(key);const chip=button(label+': '+value+' ×',()=>{const u=new URL(location.href);u.searchParams.delete(key);u.searchParams.delete('page');location.assign(u)},'chip');active.append(chip)});
  if(active.children.length)filter?.after(active);
 }
 if(filter){
  const strip=el('div','explorer-saved');strip.setAttribute('aria-label','저장한 필터');
  const list=el('div','explorer-saved-list');
  function renderSaved(){list.replaceChildren();read('views',[]).forEach((v,i)=>{if(!v.path?.startsWith('/staff/'))return;const item=el('span','saved-view');const a=el('a','',v.name);a.href=v.path+(v.query?'?'+v.query:'');const remove=button('×',()=>{const views=read('views',[]);views.splice(i,1);save('views',views);renderSaved()},'saved-remove');remove.setAttribute('aria-label',v.name+' 삭제');item.append(a,remove);list.append(item)})}
  strip.append(el('strong','','필터 즐겨찾기'),list,button('+ 현재 필터 저장',event=>{
   open('필터 즐겨찾기 저장',event.currentTarget);const input=el('input');input.maxLength=40;input.placeholder='예: 최근 7일 · 자료구조';input.setAttribute('aria-label','즐겨찾기 이름');const info=el('p','muted','현재 주소에 적용된 필터를 이 브라우저에 저장합니다.');const apply=button('저장',()=>{const name=input.value.trim();if(!name){input.reportValidity();return}const views=read('views',[]);if(views.length>=12){info.textContent='최대 12개까지 저장할 수 있습니다. 기존 항목을 삭제하세요.';return}const p=new URLSearchParams(location.search);p.delete('page');p.delete('format');views.push({name,path:location.pathname,query:p.toString()});save('views',views);renderSaved();dialog.close()},'btn-solid');input.required=true;body.append(input,info,apply);input.focus();
  }));filter.before(strip);renderSaved();
 }

 // User column preferences, current-page sort and pointer/keyboard column resizing.
 function enhanceTable(table,tableIndex){
  if(table.dataset.explorerEnhanced)return;
  table.dataset.explorerEnhanced='true';
  const headers=[...table.querySelectorAll('thead > tr:first-child > th')];if(headers.length<2)return;
  const scope=location.pathname+':table:'+tableIndex;const prefs=read(scope,{});
  const wrap=table.closest('.table-scroll')||table;
  const panel=el('details','explorer-columns');const summary=el('summary','','표 설정');const fields=el('div','explorer-column-options');panel.append(summary,fields);wrap.before(panel);
  const cells=index=>[...table.querySelectorAll('tr')].filter(row=>row.children.length===headers.length&&![...row.children].some(c=>c.colSpan>1)).map(row=>row.children[index]);
  function visible(index,on){cells(index).forEach(c=>c.hidden=!on);headers[index].hidden=!on;table.querySelectorAll('tr.event-detail').forEach(row=>{if(row.children.length!==2)return;row.children[0].hidden=headers[0].hidden;row.children[1].colSpan=Math.max(1,headers.filter(h=>!h.hidden).length-(headers[0].hidden?0:1))});prefs.hidden=Object.assign({},prefs.hidden,{[index]:!on});save(scope,prefs)}
  headers.forEach((th,index)=>{
   const name=th.textContent.trim()||'상세';const label=el('label');const box=el('input');box.type='checkbox';box.checked=!prefs.hidden?.[index];box.addEventListener('change',()=>{if(!box.checked&&fields.querySelectorAll('input:checked').length===0){box.checked=true;return}visible(index,box.checked)});label.append(box,document.createTextNode(name));fields.append(label);visible(index,box.checked);
   if(th.textContent.trim()&&!th.querySelector('input,button,.sr-only')){
    const sort=button('↕',()=>{const asc=th.getAttribute('aria-sort')!=='ascending';headers.forEach(h=>h.removeAttribute('aria-sort'));th.setAttribute('aria-sort',asc?'ascending':'descending');
     const rows=table.querySelectorAll('tbody.event-group').length?[...table.querySelectorAll('tbody.event-group')]:[...table.querySelector('tbody')?.children||[]].filter(r=>r.tagName==='TR'&&!r.classList.contains('event-detail')&&r.children.length===headers.length);
     rows.sort((a,b)=>{const av=(a.tagName==='TBODY'?a.querySelector('tr'):a).children[index]?.textContent.trim()||'';const bv=(b.tagName==='TBODY'?b.querySelector('tr'):b).children[index]?.textContent.trim()||'';return(asc?1:-1)*av.localeCompare(bv,'ko',{numeric:true})});const parent=rows[0]?.parentElement;rows.forEach(r=>parent.append(r));
    },'table-sort');sort.setAttribute('aria-label',name+' 현재 페이지 정렬');th.append(sort);
   }
   const grip=el('span','column-grip');grip.tabIndex=0;grip.setAttribute('role','separator');grip.setAttribute('aria-orientation','vertical');grip.setAttribute('aria-label',name+' 열 너비: 좌우 방향키로 조절');
   const setWidth=value=>{const width=Math.max(72,Math.min(620,value));th.style.width=width+'px';th.style.minWidth=width+'px';prefs.widths=Object.assign({},prefs.widths,{[index]:width});save(scope,prefs)};
   if(prefs.widths?.[index])setWidth(prefs.widths[index]);
   grip.addEventListener('pointerdown',event=>{if(event.button!==0)return;event.preventDefault();const start=event.clientX,width=th.getBoundingClientRect().width;grip.setPointerCapture(event.pointerId);const move=e=>setWidth(width+e.clientX-start);const end=()=>{grip.removeEventListener('pointermove',move);grip.removeEventListener('pointerup',end);grip.removeEventListener('pointercancel',end)};grip.addEventListener('pointermove',move);grip.addEventListener('pointerup',end);grip.addEventListener('pointercancel',end)});
   grip.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();setWidth(th.getBoundingClientRect().width+(event.key==='ArrowRight'?16:-16))});th.append(grip);
  });
  fields.append(el('small','muted','정렬은 현재 페이지에만 적용됩니다. 열 경계를 드래그해 너비를 조절하세요.'),button('열 설정 초기화',()=>{save(scope,{});location.reload()}));
 }
 main.querySelectorAll('table.ov-table').forEach(enhanceTable);
 new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes){if(node.nodeType!==1)continue;const tables=node.matches('table.ov-table')?[node]:[...node.querySelectorAll('table.ov-table')];tables.forEach(table=>enhanceTable(table,[...main.querySelectorAll('table.ov-table')].indexOf(table)))}}).observe(main,{childList:true,subtree:true});

 // Compare up to three selected players, including selections on other pagination pages.
 if(['/staff/members/','/staff/players/'].includes(location.pathname)){
  let selected=read('selected-players',[]);const table=main.querySelector('table.ov-table');
  if(table){const toolbar=el('div','explorer-compare-tools');const compare=button('선택 비교',async event=>{
   const id=open('플레이어 비교',event.currentTarget);body.append(el('p','muted','같은 기간과 필터로 비교하고 있습니다…'));
   const p=new URLSearchParams(location.search);p.delete('page');p.delete('player_id');selected.forEach(x=>p.append('ids',x.id));
   try{const d=await get('/api/admin/explore/players',p);if(id!==token)return;body.replaceChildren(el('p','muted',d.basis));
    const grid=el('div','player-compare-grid');for(const player of d.players){const card=el('section','compare-person');card.append(el('h3','',player.name),el('small','muted',player.source==='demo'?'데모 데이터':'실제 데이터'));
     for(const[label,value]of[['문제 실행',player.runs+'건'],['문제 해결률',player.completion_rate===null?'기록 없음':player.completion_rate+'%'],['평균 풀이',player.avg_seconds===null?'미수집':Math.round(player.avg_seconds)+'초'],['재시작',player.retries+'건'],['힌트',player.hints+'건']]){const row=el('div','compare-metric');row.append(el('span','',label),el('strong','',value));card.append(row)}grid.append(card)}body.append(grid);
   }catch(e){if(id===token)error(body,e)}
  },'btn-outline');const status=el('span','muted');const reset=button('선택 해제',()=>{selected=[];save('selected-players',selected);table.querySelectorAll('input[data-player-select]').forEach(x=>x.checked=false);sync()});toolbar.append(compare,status,reset);table.closest('.ov-card').querySelector('.ov-card-head').after(toolbar);
   function sync(){compare.disabled=selected.length<2;compare.textContent='선택한 '+selected.length+'명 비교';status.textContent='2~3명 선택 · 페이지를 이동해도 선택 유지'}
   table.querySelectorAll('tbody tr').forEach(row=>{const link=row.querySelector('a[href*="/staff/members/"],a[href*="/staff/players/"]');const match=link?.getAttribute('href').match(/\/(?:members|players)\/([\da-f-]{36})\//i);if(!match)return;const id=match[1];const box=el('input','player-compare-select');box.type='checkbox';box.dataset.playerSelect=id;box.checked=selected.some(p=>p.id===id);box.setAttribute('aria-label',link.textContent.trim()+' 비교 선택');box.addEventListener('change',()=>{if(box.checked&&selected.length>=3){box.checked=false;status.textContent='최대 3명까지 비교할 수 있습니다';return}selected=selected.filter(p=>p.id!==id);if(box.checked)selected.push({id,name:link.textContent.trim()});save('selected-players',selected);sync()});row.children[0].prepend(box)});sync();
  }
 }

 // Timeline playback: observed state only, with manual stepping and a scrubber.
 const labels={task_started:'문제 시작',problem_started:'문제 시작',attempt_started:'시도 시작',operation_succeeded:'연산 성공',operation_failed:'연산 실패',hint:'힌트 사용',hint_used:'힌트 사용',attempt_succeeded:'시도 성공',attempt_failed:'시도 실패',task_completed:'문제 완료',problem_completed:'문제 완료',task_abandoned:'문제 포기'};
 document.addEventListener('click',async event=>{const trigger=event.target.closest('[data-run-timeline]');if(!trigger)return;const id=open('행동 타임라인',trigger);body.append(el('p','muted','기록을 불러오는 중…'));try{
  const d=await get('/api/admin/explore/timeline',new URLSearchParams({run:trigger.dataset.runTimeline}));if(id!==token)return;body.replaceChildren(el('p','muted',d.basis));if(!d.events.length){body.append(el('p','notice','저장된 행동 기록이 없습니다'));return}
  let index=0,timer=null;const controls=el('div','timeline-controls');const range=el('input');range.type='range';range.min=0;range.max=d.events.length-1;range.value=0;range.setAttribute('aria-label','타임라인 이벤트 위치');const position=el('span','muted');const detail=el('section','timeline-detail');const list=el('ol','timeline-events');
  const stop=()=>{clearInterval(timer);timer=null;play.textContent='▶ 재생';play.setAttribute('aria-pressed','false')};
  const play=button('▶ 재생',()=>{if(timer){stop();return}if(index===d.events.length-1)index=0;play.textContent='Ⅱ 일시정지';play.setAttribute('aria-pressed','true');timer=setInterval(()=>{if(index>=d.events.length-1){stop();return}index++;render()},1100);render()});play.setAttribute('aria-pressed','false');
  controls.append(button('이전',()=>{stop();index=Math.max(0,index-1);render()}),play,button('다음',()=>{stop();index=Math.min(d.events.length-1,index+1);render()}),position);range.addEventListener('input',()=>{stop();index=Number(range.value);render()});
  d.events.forEach((e,i)=>{const item=el('li');item.append(button((i+1)+'. '+(labels[e.kind]||e.kind),()=>{stop();index=i;render()},'timeline-event'));list.append(item)});
  function render(){const e=d.events[index];range.value=index;position.textContent=(index+1)+' / '+d.events.length;detail.replaceChildren(el('h3','',labels[e.kind]||e.kind),el('p','muted',new Date(e.at).toLocaleString('ko-KR')+' · 순서 '+e.sequence));
   const metadata=el('p','','연산: '+(e.operation||'—')+' · 실패 원인: '+(e.reason||'—'));detail.append(metadata);const states=el('div','timeline-states');for(const[name,value]of[['이전 상태',e.before],['이후 상태',e.after]]){const part=el('div');part.append(el('strong','',name),el('pre','',value===null?'상태 미수집':JSON.stringify(value,null,2)));states.append(part)}detail.append(states);[...list.children].forEach((li,i)=>li.querySelector('button').setAttribute('aria-current',String(i===index)))}
  body.append(controls,range,detail,list);if(d.truncated)body.append(el('p','notice','처음 500개 이벤트를 표시합니다'));cleanup=stop;render();
 }catch(e){if(id===token)error(body,e)}});

 // New arrivals are announced, never inserted into the table while the user is reading.
 if(location.pathname==='/staff/events/'){
  const notice=button('',()=>{const u=new URL(location.href);u.searchParams.delete('page');location.assign(u)},'btn-outline new-log-notice');notice.hidden=true;main.querySelector('.events-page')?.prepend(notice);
  let cursor=null,busy=false;
  async function poll(){if(busy||document.hidden)return;busy=true;try{const p=new URLSearchParams(location.search);if(cursor)p.set('after',JSON.stringify(cursor));const d=await get('/api/admin/explore/new-logs',p);if(!cursor)cursor=d.cursor;notice.hidden=!d.count;notice.textContent='새 기록 '+d.count+'건 · 눌러서 반영';notice.title=d.basis}catch(_){/* keep the current table intact on network failure */}finally{busy=false}}
  poll();setInterval(poll,15000);
 }

 // Period overlay is an explicit request; no extra comparison queries on initial page load.
 const chart=main.querySelector('[data-ov-trend], [data-chart="trend"]');
 if(chart){const target=chart.closest('.card')?.querySelector('.ov-card-head,.chart-head');target?.append(button('이전 기간 비교',async event=>{
  const id=open('학습 추이 · 이전 기간 비교',event.currentTarget);body.append(el('p','muted','같은 길이의 직전 기간을 조회하고 있습니다…'));
  try{const d=await get('/api/admin/explore/periods',new URLSearchParams(location.search));if(id!==token)return;body.replaceChildren(el('p','muted',d.basis),el('p','',d.current_range.join(' ~ ')+' / 이전 '+d.previous_range.join(' ~ ')));
   const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 900 320');svg.setAttribute('class','period-overlay');svg.setAttribute('role','img');svg.setAttribute('aria-label','현재 및 이전 기간의 문제 시작·해결 건수');
   const series=[{rows:d.current,key:'started',color:'#8d82cf',label:'현재 시작'},{rows:d.current,key:'completed',color:'#16877d',label:'현재 해결'},{rows:d.previous,key:'started',color:'#8d82cf',label:'이전 시작',dash:true},{rows:d.previous,key:'completed',color:'#16877d',label:'이전 해결',dash:true}];
   const maximum=Math.max(1,...series.flatMap(s=>s.rows.map(r=>r[s.key])));const count=Math.max(d.current.length,d.previous.length);const ns=svg.namespaceURI;
   for(let i=0;i<=4;i++){const y=270-i*60;const line=document.createElementNS(ns,'line');Object.entries({x1:45,x2:875,y1:y,y2:y,stroke:'var(--line)'}).forEach(([k,v])=>line.setAttribute(k,v));svg.append(line);const text=document.createElementNS(ns,'text');text.setAttribute('x','38');text.setAttribute('y',y+4);text.setAttribute('text-anchor','end');text.textContent=Math.round(maximum*i/4);svg.append(text)}
   series.forEach(s=>{const line=document.createElementNS(ns,'polyline');line.setAttribute('points',s.rows.map((r,i)=>(45+i*830/Math.max(1,count-1))+','+(270-r[s.key]/maximum*240)).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke',s.color);line.setAttribute('stroke-width','2.5');if(s.dash)line.setAttribute('stroke-dasharray','7 5');svg.append(line)});
   const legend=el('div','period-legend');series.forEach(s=>{const label=el('span','',s.label+(s.dash?' ┄':' ━'));label.style.color=s.color;legend.append(label)});body.append(legend,svg);if(!d.previous_runs)body.append(el('p','notice','이전 기간에 시작한 문제 기록이 없습니다. 0건 집계이며 성과 향상을 의미하지 않습니다.'));
   const table=el('table','ov-table');const header=el('thead');const tr=el('tr');['상대 일차','현재 날짜','현재 시작 / 해결','이전 날짜','이전 시작 / 해결'].forEach(x=>tr.append(el('th','',x)));header.append(tr);const tb=el('tbody');for(let i=0;i<count;i++){const row=el('tr');const c=d.current[i],p=d.previous[i];[String(i+1),c?.date||'—',c?c.started+' / '+c.completed:'—',p?.date||'—',p?p.started+' / '+p.completed:'—'].forEach(x=>row.append(el('td','',x)));tb.append(row)}table.append(header,tb);const wrap=el('div','table-scroll');wrap.append(table);body.append(wrap);
  }catch(e){if(id===token)error(body,e)}
 },'btn-ghost period-compare-button'))}

 // Typed drill filters are attached by the renderer, never inferred from translated tooltip strings.
 document.addEventListener('click',event=>{const mark=event.target.closest('[data-drill]');if(!mark)return;let filters;try{filters=JSON.parse(mark.dataset.drill)}catch(_){return}const u=new URL('/staff/events/',location.origin);const p=new URLSearchParams(location.search);['start','end','source','category','game_id','content_version','player_id'].forEach(k=>{if(p.has(k))u.searchParams.set(k,p.get(k))});if(filters.category)u.searchParams.delete('game_id');Object.entries(filters).forEach(([k,v])=>u.searchParams.set(k,v));location.assign(u)});
 document.addEventListener('keydown',event=>{if((event.key==='Enter'||event.key===' ')&&event.target.matches('[data-drill]')){event.preventDefault();event.target.dispatchEvent(new MouseEvent('click',{bubbles:true}))}});
})();
