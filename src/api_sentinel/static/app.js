"use strict";
const $ = (id) => document.getElementById(id);
let key = "", monitors = [], selected = null, editing = null;
let monitorCursor = null, checkCursor = null, incidentCursor = null, refreshBusy = false;
const labels = {UP:"Działa",DOWN:"Awaria",UNKNOWN:"Czeka na pomiar",PAUSED:"Wstrzymany",SUCCESS:"Sukces",HTTP_ERROR:"Błąd HTTP",TIMEOUT:"Timeout",DNS_ERROR:"Błąd DNS",TLS_ERROR:"Błąd TLS",NETWORK_ERROR:"Błąd sieci",BLOCKED_TARGET:"Zablokowany adres",ABORTED:"Przerwany pomiar",RESPONSE_TOO_LARGE:"Zbyt duża odpowiedź"};
const date = (value) => value ? new Date(value).toLocaleString("pl-PL") : "Brak pomiarów";
function notice(message) { $("notice").textContent = message; $("notice").hidden = !message; }
function node(tag, text, className) { const el=document.createElement(tag); if(text!==undefined) el.textContent=text; if(className) el.className=className; return el; }
function badge(value) { return node("span", labels[value] || value, `badge ${value}`); }
async function api(path, options={}) {
  let response;
  try { response = await fetch(`/api/v1${path}`, { ...options, headers:{"X-API-Key":key,"Content-Type":"application/json"}, signal:AbortSignal.timeout(15000) }); }
  catch { throw new Error("Brak połączenia z lokalnym API. Sprawdź, czy usługa działa, i spróbuj ponownie."); }
  if (!response.ok) {
    const data=await response.json().catch(()=>({}));
    if(response.status===401) throw new Error("Nieprawidłowy klucz API. Sprawdź SENTINEL_API_KEY w pliku .env.");
    throw new Error(data.error?.message || `Błąd HTTP ${response.status}`);
  }
  return response.status===204 ? null : response.json();
}
async function action(button, fn) { button.disabled=true; try { await fn(); } catch(error) { notice(error.message); } finally { button.disabled=false; } }
function button(text, fn) { const el=node("button",text,"quiet"); el.type="button"; el.addEventListener("click",()=>action(el,fn)); return el; }
function renderMonitors() {
  const body=$("monitor-rows"); body.replaceChildren();
  $("empty").hidden=monitors.length>0; $("monitor-table").hidden=monitors.length===0;
  $("monitor-count").textContent=`(${monitors.length}${monitorCursor?"+":""})`;
  $("load-monitors").hidden=!monitorCursor;
  for(const monitor of monitors) {
    const row=node("tr"), service=node("td"), title=button(monitor.name,()=>showDetails(monitor)); title.className="name";
    service.append(title,node("small",monitor.url)); row.append(service);
    const state=node("td"); state.append(badge(monitor.status)); row.append(state,node("td",date(monitor.last_checked_at)),node("td",`${monitor.interval_seconds} s`));
    const cell=node("td"), actions=node("div",undefined,"row-actions");
    actions.append(button("Edytuj",()=>openEditor(monitor)),button(monitor.status==="PAUSED"?"Wznów":"Pauza",async()=>{
      await api(`/monitors/${monitor.id}/${monitor.status==="PAUSED"?"resume":"pause"}`,{method:"POST"}); await refresh();
    }),button("Usuń",async()=>{
      if(!confirm(`Usunąć monitor „${monitor.name}”? Jego historia pozostanie w bazie.`)) return;
      await api(`/monitors/${monitor.id}`,{method:"DELETE"}); if(selected?.id===monitor.id){selected=null;$("details").hidden=true;} await refresh();
    })); cell.append(actions); row.append(cell); body.append(row);
  }
}
async function refresh() {
  if(refreshBusy || !key) return;
  refreshBusy=true; $("refresh").disabled=true;
  try {
    const [data,system]=await Promise.all([api("/monitors?limit=100"),api("/system")]);
    monitors=data.items; monitorCursor=data.next_cursor; renderMonitors();
    $("worker-status").textContent=system.worker_alive?"● Worker działa":"○ Brak aktualnego sygnału workera";
    $("alert-status").textContent=`Alerty: ${system.alert_channel==="discord"?"Discord":"konsola"} · oczekujące ${system.pending_alerts} · błędne ${system.failed_alerts}`;
    $("updated").textContent=`Aktualizacja: ${new Date().toLocaleTimeString("pl-PL")}`; notice("");
    if(selected) await loadDetails();
  } finally { refreshBusy=false; $("refresh").disabled=false; }
}
function openEditor(monitor=null) {
  editing=monitor; $("monitor-form").reset(); $("form-error").hidden=true;
  $("editor-title").textContent=monitor?"Edytuj monitor":"Nowy monitor";
  if(monitor) for(const control of $("monitor-form").elements) if(control.name && monitor[control.name]!==undefined) control.value=monitor[control.name];
  $("editor").showModal();
}
async function showDetails(monitor) { selected=monitor; $("detail-name").textContent=monitor.name; $("details").hidden=false; await loadDetails(); $("details").scrollIntoView({behavior:"instant",block:"start"}); }
function renderChecks(items,append=false) {
  const body=$("check-rows"); if(!append) body.replaceChildren();
  if(!items.length&&!append){const row=node("tr"),cell=node("td","Nie ma jeszcze pomiarów. Worker wykona pierwszy check automatycznie.");cell.colSpan=4;row.append(cell);body.append(row);}
  for(const item of items){const row=node("tr"),state=node("td");state.append(badge(item.result));row.append(node("td",date(item.finished_at)),state,node("td",item.http_status??"—"),node("td",item.latency_ms===null?"—":`${Math.round(item.latency_ms)} ms`));body.append(row);}
  $("more-checks").hidden=!checkCursor;
}
function renderIncidents(items,append=false) {
  const list=$("incident-list"); if(!append) list.replaceChildren();
  if(!items.length&&!append) list.append(node("p","Brak incydentów w historii tego monitora.","hint"));
  for(const item of items){const el=node("div",`${item.state==="OPEN"?"Otwarty":"Zakończony"} — ${labels[item.reason]||item.reason}`,"incident");el.append(node("small",`${date(item.started_at)} → ${item.resolved_at?date(item.resolved_at):"trwa"}`));list.append(el);}
  $("more-incidents").hidden=!incidentCursor;
}
async function loadDetails() {
  const id=selected.id;
  const [stats,checks,incidents]=await Promise.all([api(`/monitors/${id}/stats?window=${$("window").value}`),api(`/monitors/${id}/checks`),api(`/monitors/${id}/incidents`)]);
  if(selected?.id!==id) return;
  $("success-rate").textContent=stats.success_rate_percent===null?"Brak danych":`${stats.success_rate_percent}%`;
  $("latency").textContent=stats.latency_p50_ms===null?"—":`${Math.round(stats.latency_p50_ms)} ms`;
  $("completed").textContent=stats.completed_checks; $("open-incidents").textContent=stats.open_incidents;
  checkCursor=checks.next_cursor; incidentCursor=incidents.next_cursor; renderChecks(checks.items); renderIncidents(incidents.items);
}
$("login-form").addEventListener("submit",async(event)=>{
  event.preventDefault(); const submit=event.submitter; submit.disabled=true; key=$("api-key").value.trim(); notice("Łączenie z lokalnym API…");
  try { await refresh(); $("api-key").value=""; $("login").hidden=true; $("workspace").hidden=false; $("logout").hidden=false; }
  catch(error){key="";notice(error.message);} finally{submit.disabled=false;}
});
$("logout").addEventListener("click",()=>{key="";monitors=[];selected=null;$("workspace").hidden=true;$("login").hidden=false;$("logout").hidden=true;$("details").hidden=true;notice("");$("api-key").focus();});
$("refresh").addEventListener("click",()=>action($("refresh"),refresh));
$("add").addEventListener("click",()=>openEditor()); $("add-empty").addEventListener("click",()=>openEditor());
$("close-editor").addEventListener("click",()=>$("editor").close());
$("monitor-form").addEventListener("submit",async(event)=>{
  event.preventDefault(); const values=Object.fromEntries(new FormData(event.target));
  for(const name of ["interval_seconds","timeout_seconds","failure_threshold","recovery_threshold","expected_status_min","expected_status_max"]) values[name]=Number(values[name]);
  $("save").disabled=true;$("form-error").hidden=true;
  try{await api(editing?`/monitors/${editing.id}`:"/monitors",{method:editing?"PATCH":"POST",body:JSON.stringify(values)});$("editor").close();await refresh();}
  catch(error){if($("editor").open){$("form-error").textContent=error.message;$("form-error").hidden=false;}else{notice(error.message);}}
  finally{$("save").disabled=false;}
});
$("window").addEventListener("change",()=>loadDetails().catch(error=>notice(error.message)));
$("load-monitors").addEventListener("click",()=>action($("load-monitors"),async()=>{const data=await api(`/monitors?limit=100&cursor=${encodeURIComponent(monitorCursor)}`);monitors.push(...data.items);monitorCursor=data.next_cursor;renderMonitors();}));
$("more-checks").addEventListener("click",()=>action($("more-checks"),async()=>{const data=await api(`/monitors/${selected.id}/checks?cursor=${encodeURIComponent(checkCursor)}`);checkCursor=data.next_cursor;renderChecks(data.items,true);}));
$("more-incidents").addEventListener("click",()=>action($("more-incidents"),async()=>{const data=await api(`/monitors/${selected.id}/incidents?cursor=${encodeURIComponent(incidentCursor)}`);incidentCursor=data.next_cursor;renderIncidents(data.items,true);}));
setInterval(()=>{if(key&&!document.hidden&&!$("editor").open)refresh().catch(error=>notice(error.message));},30000);
