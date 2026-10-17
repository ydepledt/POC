"use strict";

const $ = (id) => document.getElementById(id);
const activeStates = new Set(["running", "queued", "retrying", "stopping"]);
const labels = {queued:"En attente", running:"En cours", retrying:"Nouvelle tentative", stopping:"Arrêt demandé", stopped:"Arrêtée", cancelled:"Annulée", interrupted:"Interrompue", failed:"Erreur", completed:"Terminée", finished:"Terminée", budget_exhausted:"Budget atteint", target_reached:"Objectif atteint", saved:"Enregistrée", training:"Entraînement", rendering:"Montage", trained:"Entraînée"};
const trackNames = {oval:"Ovale", kidney:"Haricot", technical:"Technique", chicane:"Chicane", procedural:"Procédural"};
const difficultyNames = {easy:"Facile", medium:"Moyenne", hard:"Difficile", extreme:"Extrême"};
let overview = {runs: [], jobs: [], counts: {}};
let currentRun = null;
let currentDetail = null;
let currentPage = "dashboard";
let replay = null;
let replayIndex = 0;
let replayPlaying = false;
let replayLastFrame = 0;
let replayLoadToken = 0;
let toastTimer;
let pollBusy = false;
let dashboardRun = null;
let dashboardMetrics = [];
let idempotency = crypto.randomUUID();
const formatNumber = (n, digits=0) => Number(n || 0).toLocaleString("fr-FR", {maximumFractionDigits:digits});
const percent = n => `${formatNumber(Math.max(0, Math.min(1, Number(n)||0))*100, 1)} %`;
const date = n => new Date(n*1000).toLocaleString("fr-FR", {day:"2-digit", month:"short", hour:"2-digit", minute:"2-digit"});
const escape = value => String(value ?? "").replace(/[&<>"']/g, x => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[x]));
const fileUrl = (id, file, download=false) => `/api/runs/${encodeURIComponent(id)}/files/${file}${download?"?download=true":""}`;
const timeLabel = seconds => seconds >= 60 ? `${Math.floor(seconds/60)} min ${Math.floor(seconds%60)} s` : `${formatNumber(seconds,1)} s`;
const badge = state => `<span class="badge ${escape(state)}">${escape(labels[state] || state)}</span>`;

async function api(path, method="GET", body, headers={}) {
  const response = await fetch(`/api${path}`, {method, headers: {"Content-Type":"application/json", ...headers}, ...(body !== undefined?{body:JSON.stringify(body)}:{})});
  let result;
  try { result = await response.json(); } catch { throw Error("Réponse locale illisible. Rechargez l’interface."); }
  if (!response.ok) throw Error(typeof result.detail === "string" ? result.detail : "Paramètres invalides. Vérifiez les valeurs saisies.");
  return result;
}

function toast(message, error=false) {
  clearTimeout(toastTimer);
  $("toast").textContent = message;
  $("toast").className = `toast${error?" error":""}`;
  $("toast").hidden = false;
  toastTimer = setTimeout(() => {$("toast").hidden=true;}, error?9000:5000);
}

async function action(button, work) {
  button.disabled = true;
  try { await work(); } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; }
}

function goRun(id) {
  currentRun = id;
  if (location.hash === "#monitor") loadDetail(true);
  else location.hash = "monitor";
}

function route() {
  const requested = location.hash.replace("#", "") || "dashboard";
  currentPage = ["dashboard", "new", "monitor", "gallery", "automation", "publishing", "settings"].includes(requested) ? requested : "dashboard";
  document.querySelectorAll(".page").forEach(page => page.classList.toggle("active", page.id === `page-${currentPage}`));
  document.querySelectorAll("[data-page]").forEach(link => link.classList.toggle("active", link.dataset.page === currentPage));
  const titles = {dashboard:"Vue d’ensemble", new:"Nouvelle expérience", monitor:"Suivi en direct", gallery:"Galerie", automation:"Automatisation", publishing:"Publications", settings:"Ressources"};
  $("breadcrumb").textContent = titles[currentPage];
  if (currentPage !== "monitor") replayPlaying=false;
  if (currentPage === "monitor") loadDetail(true).catch(error => toast(error.message,true));
  if (["automation", "settings"].includes(currentPage)) loadSettings().catch(error => toast(error.message,true));
  if (currentPage === "publishing") loadPublications().catch(error => toast(error.message,true));
  if (currentPage === "gallery") renderGallery();
  window.scrollTo(0,0);
  requestAnimationFrame(() => {drawChart($("dashboard-chart"), dashboardMetrics); if(currentDetail) drawChart($("detail-chart"), currentDetail.metrics);});
}

function renderOverview() {
  const c=overview.counts;
  $("stat-runs").textContent = formatNumber(c.simulations);
  $("stat-generations").textContent = formatNumber(c.generations);
  $("stat-progress").innerHTML = `${formatNumber((c.best_progress||0)*100,1)}<span>%</span>`;
  $("stat-videos").textContent = formatNumber(c.videos);
  $("active-badge").textContent = c.active || 0;
  $("data-path").textContent = overview.data_dir || "";
  const errors = overview.runs.filter(r=>r.error && ["failed","retrying","interrupted"].includes(r.state));
  $("alerts").innerHTML = (overview.worker_error?`<div class="notice warning">${escape(overview.worker_error)}</div>`:"") + errors.slice(0,2).map(r=>`<div class="notice warning"><b>${escape(r.id)}</b> · ${escape(r.error)} <button class="table-action" data-open="${escape(r.id)}">Voir ↗</button></div>`).join("");
  $("runs-empty").hidden = overview.runs.length>0;
  $("recent-runs").innerHTML = overview.runs.slice(0,5).map(r=>`<tr><td><strong>${escape(trackNames[r.config.track] || r.config.track)} · ${escape(difficultyNames[r.config.difficulty] || r.config.difficulty)}</strong><small>${formatNumber(r.config.population)} voitures · seed ${escape(r.config.seed)}</small></td><td>${badge(r.state)}</td><td>${r.generations} <small>sur ${escape(r.config.generations)} prévues</small></td><td>${percent(r.best_progress)}<div class="progressbar"><i style="width:${Math.max(0,Math.min(100,r.best_progress*100))}%"></i></div></td><td>${date(r.created)}</td><td><button class="table-action" title="Ouvrir l’expérience" data-open="${escape(r.id)}">↗</button></td></tr>`).join("");
  // CSP disallows inline styles: apply computed values through the CSSOM.
  $("recent-runs").querySelectorAll(".progressbar i").forEach((bar,index)=>{bar.style.width=`${Math.max(0,Math.min(100,overview.runs[index].best_progress*100))}%`;});
  $("run-selector").innerHTML = overview.runs.map(r=>`<option value="${escape(r.id)}">${escape(trackNames[r.config.track] || r.config.track)} · ${date(r.created)}</option>`).join("");
  if(currentRun) $("run-selector").value=currentRun;
  const last = overview.runs[0];
  if(last) {
    $("featured-title").textContent = `${trackNames[last.config.track] || last.config.track} / ${difficultyNames[last.config.difficulty] || last.config.difficulty}`;
    $("featured-badge").textContent = labels[last.state] || last.state;
    $("featured-badge").className = `badge ${last.state}`;
    $("featured-summary").textContent = `${formatNumber(last.config.population)} voitures · ${last.generations} générations enregistrées`;
    $("featured-subtitle").textContent = `Meilleur parcours : ${percent(last.best_progress)} · Seed ${last.config.seed}`;
    $("featured-action").textContent = last.video?"Voir l’expérience ↗":"Suivre l’expérience ↗";
  }
  const schedule=overview.schedule;
  $("schedule-summary").textContent = schedule.enabled ? `Série active : ${schedule.produced}/${schedule.count} expériences lancées. Prochaine échéance : ${date(schedule.next_run)}.` : "La planification est désactivée. Explorez à votre rythme ou programmez une série.";
  $("queue-rows").innerHTML = overview.jobs.length ? overview.jobs.map(j=>`<tr><td><button class="table-action" data-open="${escape(j.run_id)}">${escape(j.run_id)} ↗</button></td><td>${({run:"Simulation + vidéo",resume:"Reprise + vidéo",render:"Montage"})[j.kind] || escape(j.kind)}</td><td>${badge(j.state)}</td><td>${j.attempts} / ${j.max_attempts}</td><td>${escape(j.error || (j.state==="retrying"?`Nouvel essai : ${date(j.next_attempt)}`:"—"))}</td></tr>`).join("") : '<tr><td colspan="5">Aucune tâche dans la file locale.</td></tr>';
  if(currentPage==="gallery") renderGallery();
}

function renderGallery() {
  const filter=$("gallery-filter").value;
  const runs=overview.runs.filter(r=>filter==="video"?r.video:filter==="active"?activeStates.has(r.state):true);
  $("gallery-empty").hidden=runs.length>0;
  $("gallery-grid").innerHTML=runs.map(r=>`<article class="gallery-card"><div class="gallery-preview" role="button" tabindex="0" data-open="${escape(r.id)}" aria-label="Ouvrir l’expérience ${escape(r.id)}">${r.thumbnail?`<img src="${fileUrl(r.id,"thumbnail.png")}" alt="Miniature de la simulation ${escape(trackNames[r.config.track])}" loading="lazy">`:'<span class="gallery-placeholder">⌁</span>'}${r.video?'<span class="play">▷</span>':''}${badge(r.state)}</div><div class="gallery-content"><h3>${escape(trackNames[r.config.track]||r.config.track)} · ${escape(difficultyNames[r.config.difficulty]||r.config.difficulty)}</h3><p class="muted">${date(r.created)} · seed ${escape(r.config.seed)}</p><div class="gallery-metrics"><span><b>${formatNumber(r.config.population)}</b> voitures</span><span><b>${r.generations}</b> gén.</span><span><b>${percent(r.best_progress)}</b> du tour</span></div><div class="gallery-actions"><button class="button secondary" data-open="${escape(r.id)}">Explorer ↗</button>${r.video?`<a class="button secondary" href="${fileUrl(r.id,"video.mp4",true)}" download>MP4 ↓</a>`:''}</div></div></article>`).join("");
}

async function loadDashboard() {
  const newest=overview.runs[0];
  if(!newest){drawTrack($("feature-canvas"),null);drawChart($("dashboard-chart"),[]);return;}
  const detail=await api(`/runs/${newest.id}`);
  dashboardRun=newest.id;dashboardMetrics=detail.metrics;
  drawChart($("dashboard-chart"),dashboardMetrics);
  $("dashboard-chart-caption").textContent=detail.metrics.length ? `${detail.metrics.length} générations mesurées · chaque point est une observation.` : "Les mesures apparaîtront après la première génération.";
  drawTrack($("feature-canvas"),detail.track);
  $("feature-canvas").setAttribute("aria-label",detail.track?.centerline?"Circuit de l’expérience sélectionnée":"Circuit ovale illustratif, en attente du tracé calculé");
  $("feature-legend").textContent=detail.track?.centerline?`CIRCUIT ${trackNames[detail.config.track]?.toUpperCase() || detail.config.track} · SEED ${detail.config.seed}`:"APERÇU ILLUSTRATIF · TRACÉ EN PRÉPARATION";
}

async function loadDetail(reset=false) {
  if(!overview.runs.length){$("detail-empty").hidden=false;$("detail-content").hidden=true;return;}
  currentRun=currentRun && overview.runs.some(r=>r.id===currentRun)?currentRun:(overview.runs.find(r=>activeStates.has(r.state)) || overview.runs[0]).id;
  const id=currentRun;
  const detail=await api(`/runs/${id}`);
  if(id!==currentRun) return;
  const changed=currentDetail?.id!==id;
  currentDetail=detail;
  $("run-selector").value=id;
  $("detail-empty").hidden=true;$("detail-content").hidden=false;
  $("detail-title").textContent=`${trackNames[detail.config.track] || detail.config.track} · seed ${detail.config.seed}`;
  $("detail-subtitle").textContent=`${id} · ${difficultyNames[detail.config.difficulty] || detail.config.difficulty} · ${formatNumber(detail.config.population)} voitures`;
  $("detail-state").textContent=labels[detail.state] || detail.state;$("detail-state").className=`badge ${detail.state}`;
  const rendering=detail.render_status;
  $("detail-message").textContent=detail.status.status==="rendering" && rendering.total_frames ? `${detail.status.message || "Montage"} · ${formatNumber(rendering.frames || rendering.rendered_frames || 0)} / ${formatNumber(rendering.total_frames)} images` : detail.status.message || "";
  $("detail-error").textContent=detail.error || "";$("detail-error").hidden=!detail.error;
  const active=activeStates.has(detail.state);
  $("stop-run").hidden=!active;
  $("resume-run").hidden=active || !detail.checkpoint;
  $("render-run").disabled=active || !detail.replays.length;
  $("export-form").querySelector("button").disabled=active || !detail.video;
  $("detail-generation").textContent=`${detail.generation} / ${detail.config.generations}`;
  $("detail-population").textContent=`${formatNumber(detail.config.population)} réseaux neuronaux`;
  $("detail-score").textContent=formatNumber(detail.best_score,1);
  $("detail-progress").textContent=percent(detail.best_progress);
  $("detail-elapsed").textContent=timeLabel(detail.elapsed_seconds);
  $("detail-log").textContent=detail.log;
  $("detail-log").scrollTop=$("detail-log").scrollHeight;
  drawChart($("detail-chart"),detail.metrics);
  const first=detail.metrics[0],last=detail.metrics.at(-1);
  $("detail-comparison").textContent=first && last ? `Première → dernière génération : ${formatNumber(first.completed || 0)} → ${formatNumber(last.completed || 0)} voitures arrivées sur ${formatNumber(detail.config.population)}. Score moyen : ${formatNumber(first.mean_score,1)} → ${formatNumber(last.mean_score,1)}. Meilleur parcours : ${percent(first.max_progress)} → ${percent(last.max_progress)}.` : "Le graphique affichera les observations à chaque génération sauvegardée.";
  const video=$("detail-video");
  $("video-empty").hidden=detail.video;video.hidden=!detail.video;$("download-video").hidden=!detail.video;
  const videoVersion=`${id}-${detail.video_metadata.generated_at || "initial"}`;
  if(detail.video && video.dataset.run!==videoVersion){video.src=`${fileUrl(id,"video.mp4")}?v=${encodeURIComponent(videoVersion)}`;video.poster=detail.thumbnail?`${fileUrl(id,"thumbnail.png")}?v=${encodeURIComponent(videoVersion)}`:"";video.dataset.run=videoVersion;}
  else if(!detail.video && video.dataset.run){video.pause();video.removeAttribute("src");video.dataset.run="";}
  $("download-video").href=fileUrl(id,"video.mp4",true);
  $("download-metrics").href=fileUrl(id,"metrics.json",true);
  $("download-config").href=fileUrl(id,"config.json",true);
  $("download-publication").href=fileUrl(id,"publication.json",true);
  $("download-publication").hidden=!Object.keys(detail.publication).length;
  const metadata=detail.video_metadata;
  $("video-specs").textContent=detail.video?`${metadata.width || 1080} × ${metadata.height || 1920} · ${metadata.fps || 30} fps · ${formatNumber(metadata.duration || detail.config.video_duration,1)} s · MP4 H.264`:"";
  $("publication-copy").textContent=detail.publication.title || "";
  $("export-receipt").textContent=detail.export_receipt.destination?`Dernier export : ${detail.export_receipt.destination}`:"";
  $("metrics-rows").innerHTML=detail.metrics.map(m=>`<tr><td>${m.generation}</td><td>${formatNumber(m.mean_score,1)}</td><td>${formatNumber(m.best_score,1)}</td><td>${percent(m.max_progress)}</td><td>${m.completed ?? 0}</td><td>${timeLabel(m.generation_seconds || 0)}</td></tr>`).join("");
  const selection=$("replay-selector").value;
  $("replay-selector").innerHTML=detail.replays.map(g=>`<option value="${g}">Génération ${g}</option>`).join("");
  $("replay-play").disabled=!detail.replays.length;
  $("replay-seek").disabled=!detail.replays.length;
  if(!changed && detail.replays.includes(Number(selection))) $("replay-selector").value=selection;
  else if(detail.replays.length) $("replay-selector").value=detail.replays.at(-1);
  if(changed || (reset && !replay) || (!replay && detail.replays.length)) {
    replay=null;replayIndex=0;replayPlaying=false;$("replay-play").textContent="▶ Lire";
    if(detail.replays.length) loadReplay();
    else {drawTrack($("replay-canvas"),detail.track);$("replay-caption").textContent="Aucune génération enregistrée pour le moment.";}
  }
}

async function loadReplay() {
  const token=++replayLoadToken;
  replayPlaying=false;
  $("replay-caption").textContent="Chargement de la trajectoire enregistrée…";
  try {
    const result=await api(`/runs/${currentRun}/replay/${$("replay-selector").value}`);
    if(token!==replayLoadToken) return;
    replay=result;replayIndex=0;$("replay-seek").max=replay.times.length-1;$("replay-seek").value=0;
    $("replay-play").textContent="▶ Lire";
    drawReplay();
  } catch(error){replay=null;$("replay-caption").textContent=error.message;}
}

function canvasContext(canvas) {
  const width=canvas.clientWidth || 700,height=canvas.clientHeight || 300,scale=window.devicePixelRatio || 1;
  if(canvas.width!==Math.floor(width*scale) || canvas.height!==Math.floor(height*scale)){canvas.width=Math.floor(width*scale);canvas.height=Math.floor(height*scale);}
  const ctx=canvas.getContext("2d");ctx.setTransform(scale,0,0,scale,0,0);return {ctx,width,height};
}

function drawChart(canvas, metrics=[]) {
  if(!canvas || !canvas.clientWidth) return;
  const {ctx,width:w,height:h}=canvasContext(canvas);
  ctx.clearRect(0,0,w,h);
  const left=43,right=20,top=20,bottom=32,gw=w-left-right,gh=h-top-bottom;
  ctx.font="9px Segoe UI";ctx.fillStyle="#73828b";ctx.textAlign="right";
  for(let i=0;i<=4;i++){const y=top+gh*i/4;ctx.beginPath();ctx.strokeStyle="#29343a";ctx.lineWidth=.8;ctx.moveTo(left,y);ctx.lineTo(w-right,y);ctx.stroke();ctx.fillText(`${100-i*25}`,left-9,y+3);}
  if(!metrics.length){ctx.textAlign="center";ctx.fillStyle="#718078";ctx.font="11px Segoe UI";ctx.fillText("En attente des premières mesures",left+gw/2,top+gh/2);return;}
  const points=metrics.map((m,i)=>[left+(metrics.length===1?gw/2:i/(metrics.length-1)*gw),top+gh*(1-Math.max(0,Math.min(1,m.max_progress || 0)))]);
  const gradient=ctx.createLinearGradient(0,top,0,top+gh);gradient.addColorStop(0,"#bcec733b");gradient.addColorStop(1,"#bcec7300");
  ctx.beginPath();ctx.moveTo(points[0][0],top+gh);points.forEach(p=>ctx.lineTo(...p));ctx.lineTo(points.at(-1)[0],top+gh);ctx.closePath();ctx.fillStyle=gradient;ctx.fill();
  ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.strokeStyle="#c2f970";ctx.lineWidth=2;ctx.lineJoin="round";ctx.stroke();
  // Same 0–100% scale: proportion of the population completing the course.
  const arrivals=metrics.map((m,i)=>[points[i][0],top+gh*(1-Math.max(0,Math.min(1,(m.completed||0)/(m.population||1))))]);
  ctx.beginPath();arrivals.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.strokeStyle="#80b8dd";ctx.lineWidth=1.7;ctx.setLineDash([4,3]);ctx.stroke();ctx.setLineDash([]);
  const last=points.at(-1);ctx.fillStyle="#d5ff9d";ctx.beginPath();ctx.arc(last[0],last[1],3,0,2*Math.PI);ctx.fill();
  ctx.fillStyle="#73828b";ctx.font="9px Segoe UI";ctx.textAlign="center";
  const every=Math.max(1,Math.ceil(metrics.length/6));metrics.forEach((m,i)=>{if(i%every===0 || i===metrics.length-1)ctx.fillText(`G${m.generation}`,points[i][0],h-10);});
}

function drawTrack(canvas, track, renderCars) {
  if(!canvas.clientWidth) return;
  const {ctx,width:w,height:h}=canvasContext(canvas);
  ctx.fillStyle="#1b2428";ctx.fillRect(0,0,w,h);
  ctx.strokeStyle="#2a373a";ctx.lineWidth=.4;for(let x=0;x<w;x+=25){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();}for(let y=0;y<h;y+=25){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}
  let points=track?.centerline;
  let width=track?.width || 38;
  if(!points?.length) points=Array.from({length:80},(_,i)=>{const a=i/80*Math.PI*2;return [Math.cos(a)*225,Math.sin(a)*85];});
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);const minX=Math.min(...xs)-width,maxX=Math.max(...xs)+width,minY=Math.min(...ys)-width,maxY=Math.max(...ys)+width;
  const scale=Math.min((w-60)/(maxX-minX),(h-64)/(maxY-minY));
  const ox=(w-(maxX-minX)*scale)/2-minX*scale,oy=(h-(maxY-minY)*scale)/2-minY*scale;
  const screen=p=>[ox+p[0]*scale,oy+p[1]*scale];
  function path(){ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...screen(p)):ctx.moveTo(...screen(p)));if(track?.closed!==false)ctx.closePath();}
  ctx.lineJoin="round";ctx.lineCap="round";
  path();ctx.strokeStyle="#546454";ctx.lineWidth=(width+5)*scale;ctx.stroke();
  path();ctx.strokeStyle="#333e43";ctx.lineWidth=width*scale;ctx.stroke();
  path();ctx.strokeStyle="#687371";ctx.lineWidth=1;ctx.setLineDash([5,8]);ctx.stroke();ctx.setLineDash([]);
  if(track?.checkpoints) {ctx.fillStyle="#9cbb7d";for(const p of track.checkpoints){const s=screen(p);ctx.beginPath();ctx.arc(s[0],s[1],2,0,Math.PI*2);ctx.fill();}}
  if(renderCars)renderCars(ctx,screen,scale);
}

function drawReplay() {
  if(!replay || !replay.times.length) return;
  const f=replayIndex;
  drawTrack($("replay-canvas"),replay.track,(ctx,screen,scale)=>{
    for(let i=0;i<replay.shown;i++) {
      const p=replay.positions[f][i],alive=replay.alive[f][i],completed=replay.completed?.[f]?.[i];
      if(!Number.isFinite(p[0]) || !Number.isFinite(p[1]))continue;
      const [x,y]=screen(p),angle=replay.headings[f][i];ctx.save();ctx.translate(x,y);ctx.rotate(angle);
      ctx.fillStyle=completed?"#88d9f4":alive?`hsl(${80+(i%5)*11} 75% ${52+(i%4)*6}%)`:"#83909135";
      ctx.fillRect(-Math.max(1.8,2.4*scale),-Math.max(1,1.2*scale),Math.max(3.6,4.8*scale),Math.max(2,2.4*scale));ctx.restore();
    }
  });
  $("replay-seek").value=f;$("replay-time").textContent=`${formatNumber(replay.times[f],1)} s`;
  $("replay-caption").textContent=`Génération ${replay.generation} · ${formatNumber(replay.alive_counts[f])} / ${formatNumber(replay.population)} en vie · ${formatNumber(replay.completed_counts?.[f] || 0)} arrivées (bleu) · ${replay.shown<replay.population?`${replay.shown} affichées (échantillon)`:"trajectoires enregistrées"}.`;
}

function animateReplay(timestamp) {
  if(replayPlaying && replay && currentPage==="monitor") {
    const next=Math.min(replayIndex+1,replay.times.length-1);
    const wait=Math.max(15,(replay.times[next]-replay.times[replayIndex])*1000);
    if(timestamp-replayLastFrame>=wait) {
      replayIndex=next;replayLastFrame=timestamp;drawReplay();
      if(next===replay.times.length-1){replayPlaying=false;$("replay-play").textContent="↻ Relire";}
    }
  }
  requestAnimationFrame(animateReplay);
}

function fillForm(form, values) {
  for(const [key,value] of Object.entries(values)) {
    const control=form.elements.namedItem(key);
    if(!control || key==="tracks")continue;
    if(control.type==="checkbox")control.checked=!!value;
    else control.value=value;
  }
}

async function loadSettings() {
  const settings=await api("/schedule");
  fillForm($("schedule-form"),settings.schedule);fillForm($("limits-form"),settings.limits);
  $("schedule-form").querySelectorAll('input[name="tracks"]').forEach(input=>{input.checked=settings.schedule.tracks.includes(input.value);});
  $("automation-badge").textContent=settings.schedule.enabled?"ACTIVÉE":"DÉSACTIVÉE";
  $("schedule-next").textContent=settings.schedule.enabled?`Prochain lancement : ${date(settings.schedule.next_run)}. ${settings.schedule.produced}/${settings.schedule.count} expériences déjà lancées.`:"Aucun lancement automatique prévu.";
}

async function loadPublications() {
  const result=await api("/publications");
  $("connectors").innerHTML=result.connectors.map((c,i)=>`<article class="panel connector-card"><div class="connector-logo">${["▷","♪","▣"][i]}</div><h2>${escape(c.name)}</h2><span class="badge">EXPORT MANUEL UNIQUEMENT</span><p>${escape(c.message)}</p><a href="${escape(c.docs)}" target="_blank" rel="noopener noreferrer">Prérequis officiels ↗</a></article>`).join("");
  $("publication-run").innerHTML=overview.runs.filter(r=>r.video).map(r=>`<option value="${escape(r.id)}">${escape(trackNames[r.config.track])} · ${date(r.created)}</option>`).join("");
  $("publication-form").querySelector("button").disabled=!overview.runs.some(r=>r.video);
  $("publication-rows").innerHTML=result.items.length?result.items.map(p=>`<tr><td>${escape(p.run_id)}</td><td>${escape(({youtube:"YouTube Shorts",tiktok:"TikTok",instagram:"Instagram Reels",local:"Local"})[p.platform])}</td><td><span class="badge">BROUILLON LOCAL</span></td><td>${escape(p.message)}</td><td><button class="table-action" data-open="${escape(p.run_id)}">Fichiers ↗</button></td></tr>`).join(""):'<tr><td colspan="5">Aucun brouillon préparé. Les vidéos restent disponibles dans la galerie.</td></tr>';
}

async function refresh() {
  if(pollBusy)return;pollBusy=true;
  try {
    overview=await api("/overview");renderOverview();
    $("connection-status").textContent="Connexion locale";
    if(currentPage==="dashboard")await loadDashboard();
    if(currentPage==="monitor")await loadDetail();
  } catch(error){$("connection-status").textContent="Connexion interrompue";console.error(error);}
  finally{pollBusy=false;}
}

document.addEventListener("click",event=>{const target=event.target.closest("[data-open]");if(target)goRun(target.dataset.open);});
document.addEventListener("keydown",event=>{if(event.key==="Enter" && event.target.matches('[role="button"][data-open]'))goRun(event.target.dataset.open);});
window.addEventListener("hashchange",route);
$("featured-action").addEventListener("click",()=>overview.runs.length?goRun(overview.runs[0].id):location.hash="new");
$("gallery-filter").addEventListener("change",renderGallery);
$("run-selector").addEventListener("change",()=>{currentRun=$("run-selector").value;loadDetail(true).catch(e=>toast(e.message,true));});
$("replay-selector").addEventListener("change",loadReplay);
$("replay-play").addEventListener("click",()=>{if(!replay)return;if(replayIndex===replay.times.length-1)replayIndex=0;replayPlaying=!replayPlaying;replayLastFrame=performance.now();$("replay-play").textContent=replayPlaying?"Ⅱ Pause":"▶ Lire";});
$("replay-seek").addEventListener("input",()=>{replayIndex=Number($("replay-seek").value);drawReplay();});
$("random-seed").addEventListener("click",()=>{$("new-form").elements.seed.value=crypto.getRandomValues(new Uint32Array(1))[0]%2147483647;});
$("new-form").addEventListener("submit",event=>{event.preventDefault();action(event.submitter,async()=>{
  const config=Object.fromEntries(new FormData(event.target));
  for(const key of Object.keys(config))if(!["track","difficulty"].includes(key))config[key]=Number(config[key]);
  const result=await api("/runs","POST",{config},{"Idempotency-Key":idempotency});idempotency=crypto.randomUUID();
  await refresh();goRun(result.run_id);toast("Expérience ajoutée à la file. Le calcul démarre automatiquement.");
});});
$("new-form").addEventListener("invalid",event=>{const advanced=event.target.closest("details");if(advanced)advanced.open=true;toast(`Vérifiez le champ « ${event.target.closest("label")?.childNodes[0]?.textContent.trim() || event.target.name} ».`,true);},true);
$("stop-run").addEventListener("click",event=>action(event.target,async()=>{await api(`/runs/${currentRun}/stop`,"POST",{});toast("Arrêt demandé. Les générations terminées restent sauvegardées.");await refresh();}));
$("resume-run").addEventListener("click",event=>action(event.target,async()=>{await api(`/runs/${currentRun}/resume`,"POST",{});toast("Reprise ajoutée à la file, depuis la dernière sauvegarde.");await refresh();}));
$("render-run").addEventListener("click",event=>action(event.target,async()=>{await api(`/runs/${currentRun}/render`,"POST",{});toast("Nouveau montage ajouté à la file.");await refresh();}));
$("clone-run").addEventListener("click",()=>{if(currentDetail){fillForm($("new-form"),currentDetail.config);location.hash="new";toast("Paramètres repris. Vous pouvez les ajuster avant le lancement.");}});
$("export-form").addEventListener("submit",event=>{event.preventDefault();action(event.submitter,async()=>{const result=await api(`/runs/${currentRun}/export`,"POST",Object.fromEntries(new FormData(event.target)));toast(`Export local prêt : ${result.destination}`);await loadDetail();});});
$("schedule-form").addEventListener("submit",event=>{event.preventDefault();action(event.submitter,async()=>{
  const form=new FormData(event.target),settings=Object.fromEntries(form);settings.enabled=event.target.elements.enabled.checked;settings.tracks=form.getAll("tracks");
  ["count","interval_minutes","video_duration","population","generations","budget_seconds"].forEach(k=>settings[k]=Number(settings[k]));
  await api("/schedule","PUT",settings);await loadSettings();await refresh();toast(settings.enabled?"Planification activée. Premier lancement après l’intervalle choisi.":"Paramètres enregistrés. Planification désactivée.");
});});
$("limits-form").addEventListener("submit",event=>{event.preventDefault();action(event.submitter,async()=>{const values=Object.fromEntries(new FormData(event.target));Object.keys(values).forEach(k=>values[k]=Number(values[k]));await api("/limits","PUT",values);toast("Limites enregistrées pour les prochains traitements.");});});
$("publication-form").addEventListener("submit",event=>{event.preventDefault();action(event.submitter,async()=>{const form=new FormData(event.target);await api(`/publications/${form.get("run_id")}`,"POST",{platform:form.get("platform")});await loadPublications();toast("Brouillon local préparé. Aucun contenu n’a été publié.");});});
window.addEventListener("resize",()=>{drawChart($("dashboard-chart"),dashboardMetrics);if(currentDetail){drawChart($("detail-chart"),currentDetail.metrics);drawTrack($("feature-canvas"),currentDetail.track);}else drawTrack($("feature-canvas"),null);if(replay)drawReplay();});

async function init(){
  try{const defaults=await api("/defaults");fillForm($("new-form"),defaults.config);}catch(e){toast(e.message,true);}
  await refresh();route();requestAnimationFrame(animateReplay);setInterval(refresh,3000);
}
init();
