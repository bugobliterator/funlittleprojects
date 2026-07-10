// Wireframe markup + feedback layer. Per-view pins / boxes / freehand /
// comments, attributed per user, persisted to /wire/markup and shown to all.
(function(){
  var VIEW=document.body.dataset.view||"view";
  var doc=document.getElementById("wire-doc"); if(!doc) return;
  var PALETTE=["#1f6feb","#d8772a","#2e8b57","#c0392b","#8e44ad","#0e7490","#b7791f","#be185d"];
  function colorFor(name){var h=0;for(var i=0;i<name.length;i++)h=(h*31+name.charCodeAt(i))>>>0;return PALETTE[h%PALETTE.length];}
  var user=null; try{user=localStorage.getItem("wire-user");}catch(e){}
  var ann=[]; var tool="select"; var draftStroke=null;

  // overlay + svg for freehand/boxes geometry
  var overlay=document.createElement("div"); overlay.id="wire-overlay";
  var svg=document.createElementNS("http://www.w3.org/2000/svg","svg"); overlay.appendChild(svg);
  doc.appendChild(overlay);

  // inset:0 only stretches to #wire-doc's client box; content can overflow it
  // (child margins, expanded disclosures). Pin the overlay's own height to the
  // true content height so the markup canvas + dashed border wrap every element.
  // The overlay must be collapsed while measuring: a tall absolutely-positioned
  // child inflates doc.scrollHeight, which would otherwise make fitOverlay chase
  // its own height in a feedback loop and always land short.
  function contentHeight(){
    var prev=overlay.style.height; overlay.style.height="0px";
    var h=doc.scrollHeight; overlay.style.height=prev; return h;
  }
  var fitting=false;
  function fitOverlay(){
    if(fitting)return; fitting=true;
    overlay.style.height = contentHeight() + "px";
    fitting=false;
  }
  fitOverlay();
  if(window.ResizeObserver){ try{ new ResizeObserver(fitOverlay).observe(doc); }catch(e){} }

  function esc(s){return (s==null?"":String(s)).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
  // h uses contentHeight() (overlay excluded) so the freehand SVG viewBox matches
  // the overlay's pixel height 1:1 and stroke coordinates stay aligned.
  function size(){return {w:doc.scrollWidth,h:contentHeight()};}
  // Pins/boxes/strokes are absolutely-positioned children of `overlay`, so map
  // clicks into overlay-relative coords. getBoundingClientRect() is already
  // viewport-relative (accounts for page scroll), so no scroll term is needed.
  function rel(e){var r=overlay.getBoundingClientRect();return {x:e.clientX-r.left,y:e.clientY-r.top};}

  // ── toolbar ──
  var tools=document.createElement("div"); tools.className="wm-tools";
  tools.innerHTML=
    '<button class="wm-tool" data-tool="select" aria-pressed="true"><span class="wm-tool__k">⌖</span>Select</button>'+
    '<button class="wm-tool" data-tool="pin"><span class="wm-tool__k">📍</span>Pin</button>'+
    '<button class="wm-tool" data-tool="box"><span class="wm-tool__k">▭</span>Box</button>'+
    '<button class="wm-tool" data-tool="draw"><span class="wm-tool__k">✎</span>Draw</button>'+
    '<span class="wm-tools__sep"></span>'+
    '<button class="wm-tool" data-tool="panel"><span class="wm-tool__k">🗩</span>Comments (<span id="wm-count">0</span>)</button>'+
    '<span class="wm-tools__sep"></span>'+
    '<span class="wm-tools__who"><span class="wm-dot" id="wm-whodot"></span><span id="wm-whoname">…</span></span>';
  document.body.appendChild(tools);

  // ── comments panel ──
  var panel=document.createElement("aside"); panel.className="wm-panel";
  panel.innerHTML='<div class="wm-panel__head"><span class="wm-panel__title">Comments · this view</span>'+
    '<button class="cp-button cp-button--ghost cp-button--sm" id="wm-panel-close">Close</button></div>'+
    '<div class="wm-panel__list" id="wm-list"></div>'+
    '<div class="wm-panel__compose"><textarea id="wm-compose" placeholder="Comment on this whole view…"></textarea>'+
    '<div style="display:flex;justify-content:flex-end;margin-top:6px"><button class="cp-button cp-button--accent cp-button--sm" id="wm-compose-send">Post</button></div></div>';
  document.body.appendChild(panel);

  function setTool(t){tool=t;
    tools.querySelectorAll(".wm-tool[data-tool]").forEach(function(b){b.setAttribute("aria-pressed", b.dataset.tool===t&&t!=="panel"?"true":"false");});
    overlay.classList.toggle("is-armed", t==="pin"||t==="box"||t==="draw");
  }
  tools.addEventListener("click",function(e){var b=e.target.closest(".wm-tool"); if(!b)return;
    if(b.dataset.tool==="panel"){panel.classList.toggle("is-open"); return;}
    if(!user){askName(function(){setTool(b.dataset.tool);}); return;} setTool(b.dataset.tool);});
  document.getElementById("wm-panel-close").addEventListener("click",function(){panel.classList.remove("is-open");});

  function refreshWho(){var d=document.getElementById("wm-whodot"),n=document.getElementById("wm-whoname");
    if(user){d.style.background=colorFor(user); n.textContent=user;} else {n.textContent="sign in";}
    var av=document.getElementById("wire-avatar"); if(av&&user){av.textContent=user.split(/\s+/).map(function(s){return s[0];}).join("").slice(0,2).toUpperCase(); av.style.background=colorFor(user);}
  }

  // ── name modal ──
  function askName(then){
    var m=document.createElement("div"); m.id="wm-name";
    m.innerHTML='<div class="wm-card"><h2>Your name</h2><p>Markup &amp; comments are shared with everyone on the LAN and attributed to you.</p>'+
      '<input id="wm-name-i" placeholder="e.g. Simon Maddison" autocomplete="name"><div style="display:flex;justify-content:flex-end"><button class="cp-button cp-button--accent" id="wm-name-ok">Start</button></div></div>';
    document.body.appendChild(m);
    var i=m.querySelector("#wm-name-i"); if(user)i.value=user; i.focus();
    function ok(){var v=i.value.trim(); if(!v){i.focus();return;} user=v; try{localStorage.setItem("wire-user",v);}catch(e){} document.body.removeChild(m); refreshWho(); if(then)then();}
    m.querySelector("#wm-name-ok").addEventListener("click",ok);
    i.addEventListener("keydown",function(e){if(e.key==="Enter")ok();});
  }

  // ── persistence ──
  function load(){return fetch("/wire/markup?view="+encodeURIComponent(VIEW)).then(function(r){return r.ok?r.json():{annotations:[]};})
    .then(function(j){ann=j.annotations||[]; render();}).catch(function(){});}
  function save(a){return fetch("/wire/markup",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify(Object.assign({view:VIEW},a))}).then(function(r){return r.json();})
    .then(function(j){if(j&&j.annotations){ann=j.annotations; render();}}).catch(function(){});}
  function deleteAnn(id){return fetch("/wire/markup/delete",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({view:VIEW,id:id,author:user||"?"})}).then(function(r){return r.json();})
    .then(function(j){if(j&&j.annotations){ann=j.annotations; render();}}).catch(function(){});}
  function resolveAnn(id,val){return fetch("/wire/resolve",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({view:VIEW,id:id,resolved:val})}).then(function(){load(); loadSummary();}).catch(function(){});}
  function respond(view,id,text,then){var v=view||VIEW; return fetch("/wire/respond",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({view:v,id:id,text:text,by:user})}).then(function(r){return r.json();})
    .then(function(j){if(j&&j.annotations&&v===VIEW){ann=j.annotations;} if(then)then();}).catch(function(){});}

  function newId(){return "a"+Math.round(performance.now()*1000)+"_"+ann.length;}

  // ── reply rendering: Claude's response + commit hash + the reviewer↔Claude thread ──
  // Shared by the panel list, the pin/box popover, and the global-notes panel so all
  // three surfaces show the commit hash, the thread bubbles, and the Reply control.
  function replyHtml(a,view){
    if(!a.reply)return "";
    var commit=a.reply.commit?' · <span class="wm-reply__commit">'+esc(a.reply.commit)+'</span>':'';
    var head='<div class="wm-reply__who">↳ '+esc(a.reply.by||"Claude")+' responded'+commit+'</div>';
    var body='<div class="wm-reply__text">'+esc(a.reply.text||"")+'</div>';
    var thread=(a.reply.thread||[]).map(function(m){var c=colorFor(m.by||"?");
      return '<div class="wm-thread__msg"><div class="wm-thread__who"><span class="wm-dot" style="background:'+c+'"></span>'+
        esc(m.by||"?")+'</div><div class="wm-thread__text">'+esc(m.text||"")+'</div></div>';}).join("");
    var threadHtml=thread?'<div class="wm-thread">'+thread+'</div>':'';
    var reply='<div class="wm-reply__do"><button class="cp-button cp-button--ghost cp-button--sm wm-replybtn" data-reply="'+esc(a.id)+'" data-view="'+esc(view||a.view||VIEW)+'">Reply</button></div>';
    return '<div class="wm-reply">'+head+body+threadHtml+reply+'</div>';
  }
  // Wire the Reply buttons inside `root` → reveal a textarea, POST /wire/respond, re-render.
  function wireReply(root,view,rerender){
    root.querySelectorAll(".wm-replybtn").forEach(function(b){b.addEventListener("click",function(e){e.stopPropagation();
      if(!user){askName(function(){});return;}
      var id=b.getAttribute("data-reply"), v=b.getAttribute("data-view")||view||VIEW;
      var box=b.parentNode; if(box.querySelector(".wm-replyform"))return;
      var f=document.createElement("div"); f.className="wm-replyform";
      f.innerHTML='<textarea class="wm-replyin" placeholder="Reply to '+esc(a_by(b))+'…"></textarea>'+
        '<div class="wm-replyform__a"><button class="cp-button cp-button--ghost cp-button--sm" data-cancel>Cancel</button>'+
        '<button class="cp-button cp-button--accent cp-button--sm" data-send>Send</button></div>';
      box.appendChild(f); b.style.display="none";
      f.addEventListener("click",function(ev){ev.stopPropagation();});  // typing in the panel list must not re-open the pin popover
      var ta=f.querySelector(".wm-replyin"); ta.focus();
      f.querySelector("[data-cancel]").addEventListener("click",function(ev){ev.stopPropagation(); f.remove(); b.style.display="";});
      f.querySelector("[data-send]").addEventListener("click",function(ev){ev.stopPropagation(); var t=ta.value.trim(); if(!t)return;
        respond(v,id,t,function(){ if(rerender)rerender(); else render(); loadSummary();});});
    });});
  }
  // the Claude responder a reviewer is replying to, for the textarea placeholder
  function a_by(b){var box=b.closest(".wm-reply"); var who=box&&box.querySelector(".wm-reply__who"); return who?(who.textContent||"").replace(/^↳\s*/,"").split(" responded")[0]:"Claude";}

  // ── rendering ──
  function render(){
    overlay.querySelectorAll(".wm-pin,.wm-box").forEach(function(n){n.remove();});
    while(svg.firstChild)svg.removeChild(svg.firstChild);
    var s=size(); fitOverlay(); svg.setAttribute("viewBox","0 0 "+s.w+" "+s.h);
    var pinNo=0;
    ann.forEach(function(a){
      if(a.resolved)return;
      var col=colorFor(a.author||"?");
      if(a.type==="pin"){pinNo++; var p=document.createElement("div"); p.className="wm-pin"; p.style.left=a.x+"px"; p.style.top=a.y+"px"; p.style.background=col; p.textContent=pinNo; p.title=(a.author||"")+": "+(a.text||""); p.addEventListener("click",function(ev){ev.stopPropagation(); showMsg(a,a.x,a.y);}); overlay.appendChild(p);}
      else if(a.type==="box"){var b=document.createElement("div"); b.className="wm-box"; b.style.left=a.x+"px"; b.style.top=a.y+"px"; b.style.width=a.w+"px"; b.style.height=a.h+"px"; b.style.borderColor=col; var tag=document.createElement("span"); tag.className="wm-box__tag"; tag.style.background=col; tag.textContent=a.author||""; b.appendChild(tag); b.addEventListener("click",function(ev){ev.stopPropagation(); showMsg(a,a.x+a.w,a.y);}); overlay.appendChild(b);}
      else if(a.type==="draw"&&a.points){var pl=document.createElementNS("http://www.w3.org/2000/svg","polyline"); pl.setAttribute("points",a.points.map(function(p){return p[0]+","+p[1];}).join(" ")); pl.setAttribute("fill","none"); pl.setAttribute("stroke",col); pl.setAttribute("stroke-width","2.5"); pl.setAttribute("stroke-linecap","round"); pl.setAttribute("stroke-linejoin","round"); pl.style.pointerEvents="stroke"; pl.style.cursor="pointer"; pl.addEventListener("click",function(ev){ev.stopPropagation(); showMsg(a,a.points[0][0],a.points[0][1]);}); svg.appendChild(pl);}
    });
    renderList();
    var c=document.getElementById("wm-count"); if(c)c.textContent=ann.length;
    var vc=document.getElementById("wire-viewcount"); if(vc)vc.innerHTML='<span class="cp-pill__dot"></span>'+ann.length+" comments";
  }

  function renderList(){
    var list=document.getElementById("wm-list"); if(!list)return;
    if(!ann.length){list.innerHTML='<div class="wm-empty">No markup yet. Pick a tool and click the view, or post a comment below.</div>'; return;}
    var order=ann.map(function(a,i){return {a:a,i:i};}).sort(function(p,q){return (p.a.resolved?1:0)-(q.a.resolved?1:0);});
    list.innerHTML=order.map(function(o){var a=o.a,i=o.i,col=colorFor(a.author||"?");
      var rep=replyHtml(a);
      var tag=a.resolved?'<span class="wm-res-tag">resolved</span>':'';
      var rb='<button class="wm-res" data-res="'+esc(a.id)+'" data-val="'+(a.resolved?"0":"1")+'" title="'+(a.resolved?"Reopen":"Mark resolved")+'">'+(a.resolved?'↩':'✓')+'</button>';
      return '<div class="wm-item'+(a.reply?' has-reply':'')+(a.resolved?' resolved':'')+'" data-i="'+i+'"><div class="wm-item__top"><span class="wm-dot" style="background:'+col+'"></span>'+
        '<span class="wm-item__author">'+esc(a.author)+'</span><span class="wm-item__type">'+esc(a.type)+'</span>'+
        '<span class="wm-item__rt">'+tag+rb+'<button class="wm-del" data-del="'+esc(a.id)+'" title="Delete">✕</button></span></div>'+
        '<div class="wm-item__text">'+esc(a.text||"(no text)")+'</div>'+rep+'</div>';}).join("");
    list.querySelectorAll(".wm-del").forEach(function(b){b.addEventListener("click",function(e){e.stopPropagation(); deleteAnn(b.dataset.del);});});
    list.querySelectorAll(".wm-res").forEach(function(b){b.addEventListener("click",function(e){e.stopPropagation(); resolveAnn(b.getAttribute("data-res"), b.getAttribute("data-val")==="1");});});
    wireReply(list,VIEW,renderList);
    list.querySelectorAll(".wm-item").forEach(function(el){el.addEventListener("click",function(){var a=ann[+el.dataset.i];
      var x=a.x||(a.points&&a.points[0][0])||40, y=a.y||(a.points&&a.points[0][1])||40; window.scrollTo({top:Math.max(0,y-120),behavior:"smooth"}); showMsg(a,x,y);});});
  }

  // ── comment popover (create + read) ──
  var pop=null;
  function closePop(){if(pop){pop.remove();pop=null;}}
  function popAt(x,y){closePop(); pop=document.createElement("div"); pop.className="wm-pop"; pop.style.left=Math.min(x,size().w-300)+"px"; pop.style.top=(y+10)+"px"; overlay.appendChild(pop); return pop;}
  function compose(x,y,onsave){var p=popAt(x,y);
    p.innerHTML='<div class="wm-pop__who"><span class="wm-dot" style="background:'+colorFor(user)+'"></span>'+esc(user)+'</div>'+
      '<textarea placeholder="Add a note…"></textarea><div class="wm-pop__actions"><button class="cp-button cp-button--ghost cp-button--sm" data-x>Cancel</button><button class="cp-button cp-button--accent cp-button--sm" data-ok>Save</button></div>';
    var ta=p.querySelector("textarea"); ta.focus();
    p.querySelector("[data-x]").addEventListener("click",function(){closePop(); if(onsave)onsave(null);});
    p.querySelector("[data-ok]").addEventListener("click",function(){var t=ta.value.trim(); closePop(); onsave(t);});
  }
  function showMsg(a,x,y){var p=popAt(x,y); var col=colorFor(a.author||"?");
    var rep=replyHtml(a);
    p.innerHTML='<div class="wm-pop__who"><span class="wm-dot" style="background:'+col+'"></span>'+esc(a.author)+'</div>'+
      '<div class="wm-msg">'+esc(a.text||"(no text)")+'</div><div class="wm-msg__meta">'+esc(a.type)+' · '+esc((a.ts||"").replace("T"," ").slice(0,16))+'</div>'+rep+
      '<div class="wm-pop__actions"><button class="cp-button cp-button--ghost cp-button--sm" data-resolve>'+(a.resolved?'Reopen':'Resolve')+'</button><button class="cp-button cp-button--ghost cp-button--sm" data-del>Delete</button><button class="cp-button cp-button--ghost cp-button--sm" data-x>Close</button></div>';
    p.querySelector("[data-x]").addEventListener("click",closePop);
    p.querySelector("[data-del]").addEventListener("click",function(){ deleteAnn(a.id); closePop(); });
    p.querySelector("[data-resolve]").addEventListener("click",function(){ resolveAnn(a.id, !a.resolved); closePop(); });
    // re-render the popover in place so a sent reply shows immediately (the thread grows)
    wireReply(p,a.view||VIEW,function(){ showMsg(findAnn(a.id)||a,x,y); });
  }
  function findAnn(id){for(var k=0;k<ann.length;k++){if(ann[k].id===id)return ann[k];}return null;}

  // ── interactions ──
  overlay.addEventListener("click",function(e){
    if(tool==="pin"){var pt=rel(e); compose(pt.x,pt.y,function(t){ if(t===null)return; save({id:newId(),type:"pin",author:user,x:Math.round(pt.x),y:Math.round(pt.y),text:t,ts:new Date().toISOString()}); setTool("select");});}
    else if(tool==="select"){closePop();}
  });
  // box drag
  var boxStart=null, boxEl=null;
  overlay.addEventListener("mousedown",function(e){ if(tool==="box"){boxStart=rel(e); boxEl=document.createElement("div"); boxEl.className="wm-box"; boxEl.style.borderColor=colorFor(user); boxEl.style.left=boxStart.x+"px"; boxEl.style.top=boxStart.y+"px"; overlay.appendChild(boxEl);}
    else if(tool==="draw"){draftStroke=[[Math.round(rel(e).x),Math.round(rel(e).y)]]; }});
  overlay.addEventListener("mousemove",function(e){ if(tool==="box"&&boxStart&&boxEl){var p=rel(e); boxEl.style.left=Math.min(p.x,boxStart.x)+"px"; boxEl.style.top=Math.min(p.y,boxStart.y)+"px"; boxEl.style.width=Math.abs(p.x-boxStart.x)+"px"; boxEl.style.height=Math.abs(p.y-boxStart.y)+"px";}
    else if(tool==="draw"&&draftStroke){var p=rel(e); draftStroke.push([Math.round(p.x),Math.round(p.y)]); var tmp=svg.querySelector("#wm-draft"); if(!tmp){tmp=document.createElementNS("http://www.w3.org/2000/svg","polyline"); tmp.id="wm-draft"; tmp.setAttribute("fill","none"); tmp.setAttribute("stroke",colorFor(user)); tmp.setAttribute("stroke-width","2.5"); svg.appendChild(tmp);} tmp.setAttribute("points",draftStroke.map(function(p){return p[0]+","+p[1];}).join(" "));}});
  window.addEventListener("mouseup",function(e){
    if(tool==="box"&&boxStart&&boxEl){var p=rel(e); var x=Math.min(p.x,boxStart.x),y=Math.min(p.y,boxStart.y),w=Math.abs(p.x-boxStart.x),h=Math.abs(p.y-boxStart.y); var el=boxEl; boxEl=null; var st=boxStart; boxStart=null; el.remove(); if(w>8&&h>8){compose(x+w,y,function(t){if(t===null){render();return;} save({id:newId(),type:"box",author:user,x:Math.round(x),y:Math.round(y),w:Math.round(w),h:Math.round(h),text:t,ts:new Date().toISOString()}); setTool("select");});}}
    else if(tool==="draw"&&draftStroke){var pts=draftStroke; draftStroke=null; var d=svg.querySelector("#wm-draft"); if(d)d.remove(); if(pts.length>2){compose(pts[0][0],pts[0][1],function(t){ save({id:newId(),type:"draw",author:user,points:pts,text:t||"",ts:new Date().toISOString()}); setTool("select");});}}
  });

  // panel compose (whole-view comment → stored as a pin at top-left marker)
  document.getElementById("wm-compose-send").addEventListener("click",function(){
    if(!user){askName(function(){});return;} var ta=document.getElementById("wm-compose"); var t=ta.value.trim(); if(!t)return;
    save({id:newId(),type:"comment",author:user,text:t,ts:new Date().toISOString()}); ta.value="";});

  // poll so it evolves as others add feedback
  setInterval(function(){ if(!pop&&!boxStart&&!draftStroke) load(); }, 6000);

  // ── per-view comment counts + red dots, change-log drawer, rollback ──
  function loadSummary(){fetch("/wire/summary").then(function(r){return r.ok?r.json():null;}).then(function(s){ if(!s)return;
    var V=Object.assign({}, s.views||{}); var SUB={whereused:"part"};  // sub-views fold into their parent nav item
    Object.keys(SUB).forEach(function(k){ if(V[k]){var p=SUB[k]; var t=V[p]?Object.assign({},V[p]):{comments:0,unreviewed:0}; t.comments=(t.comments||0)+(V[k].comments||0); t.unreviewed=(t.unreviewed||0)+(V[k].unreviewed||0); V[p]=t;}});
    document.querySelectorAll(".wire-navcount").forEach(function(el){var d=V[el.getAttribute("data-view")];
      if(d&&d.comments){el.classList.add("on"); el.innerHTML=(d.unreviewed>0?'<span class="dot" title="Claude responded — open to review"></span>':'')+d.comments;}
      else{el.classList.remove("on"); el.innerHTML="";}});
    var n=document.getElementById("wire-changes-n"); if(n)n.textContent=s.changes||0;
    var b=document.getElementById("wire-changes-btn"); if(b)b.classList.toggle("has-rollback",(s.rollback_pending||0)>0);
    var g=(s.views||{})["_global"]; var gn=document.getElementById("wire-global-n"); var gb2=document.getElementById("wire-global-btn");
    if(gn)gn.textContent=(g&&g.comments)||0;
    if(gb2)gb2.classList.toggle("has-dot",!!(g&&g.unreviewed>0));
  }).catch(function(){});}

  function renderChangelog(){var list=document.getElementById("wire-cl-list"); var cnt=document.getElementById("wire-cl-count"); if(!list)return;
    fetch("/wire/changelog").then(function(r){return r.ok?r.json():{changes:[]};}).then(function(cl){var ch=(cl.changes||[]).slice().reverse();
      if(cnt)cnt.textContent=ch.length+" change"+(ch.length===1?"":"s");
      if(!ch.length){list.innerHTML='<div class="wm-empty">No changes recorded yet.</div>';return;}
      list.innerHTML=ch.map(function(c){var rolled=c.status==="rolled-back"; var req=c.rollback_requested;
        var btn=rolled?'<span class="wire-muted" style="font-size:11.5px">rolled back</span>':
          (req?'<span class="wire-muted" style="font-size:11.5px;color:var(--cp-color-cube-red,#c0392b)">rollback requested — Claude will action</span>':
          '<button class="cp-button cp-button--ghost cp-button--sm" data-rb="'+esc(c.id)+'">Request rollback</button>');
        return '<div class="wire-cl__item'+(rolled?" rolled":"")+(req?" req":"")+'"><div class="wire-cl__sum">'+esc(c.summary)+'</div>'+
          (c.detail?'<div class="wire-cl__detail">'+esc(c.detail)+'</div>':'')+
          '<div class="wire-cl__foot"><span class="wire-cl__id">'+esc(c.id)+(c.commit?' · git '+esc(c.commit):'')+'</span>'+btn+'<span class="wire-cl__ts">'+esc((c.ts||"").replace("T"," "))+'</span></div></div>';}).join("");
      list.querySelectorAll("[data-rb]").forEach(function(b){b.addEventListener("click",function(){var sum=b.closest(".wire-cl__item").querySelector(".wire-cl__sum").textContent;
        if(!confirm("Ask Claude to roll back this change?\n\n"+sum))return;
        fetch("/wire/rollback",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:b.getAttribute("data-rb")})}).then(function(){renderChangelog(); loadSummary();});});});
    }).catch(function(){});}

  (function(){var b=document.getElementById("wire-changes-btn"); if(b)b.addEventListener("click",function(){var d=document.getElementById("wire-cl"); if(d){d.hidden=false; renderChangelog();}});
    var x=document.getElementById("wire-cl-close"); if(x)x.addEventListener("click",function(){var d=document.getElementById("wire-cl"); if(d)d.hidden=true;});
    var bg=document.getElementById("wire-cl-bg"); if(bg)bg.addEventListener("click",function(){var d=document.getElementById("wire-cl"); if(d)d.hidden=true;});})();

  // ── global / system comments (view "_global", not tied to a page) ──
  function renderGlobal(){var list=document.getElementById("wire-gc-list"),cnt=document.getElementById("wire-gc-count"); if(!list)return;
    fetch("/wire/markup?view=_global").then(function(r){return r.ok?r.json():{annotations:[]};}).then(function(d){
      var arr=(d.annotations||[]).filter(function(a){return (a.text||"").trim();});
      if(cnt)cnt.textContent=arr.length+" note"+(arr.length===1?"":"s");
      if(!arr.length){list.innerHTML='<div class="wm-empty">No system notes yet. Post one below — these are structural / architectural comments on the whole platform, visible from every view.</div>';return;}
      var order=arr.slice().sort(function(p,q){return (p.resolved?1:0)-(q.resolved?1:0);});
      list.innerHTML=order.map(function(a){var col=colorFor(a.author||"?");
        var rep=replyHtml(a,"_global");
        var tag=a.resolved?'<span class="wm-res-tag">resolved</span>':'';
        var rb='<button class="wm-res" data-gres="'+esc(a.id)+'" data-val="'+(a.resolved?"0":"1")+'" title="'+(a.resolved?"Reopen":"Mark resolved")+'">'+(a.resolved?"↩":"✓")+'</button>';
        return '<div class="wm-item'+(a.reply?" has-reply":"")+(a.resolved?" resolved":"")+'"><div class="wm-item__top"><span class="wm-dot" style="background:'+col+'"></span>'+
          '<span class="wm-item__author">'+esc(a.author)+'</span><span class="wm-item__type">system</span>'+
          '<span class="wm-item__rt">'+tag+rb+'<button class="wm-del" data-gdel="'+esc(a.id)+'" title="Delete">✕</button></span></div>'+
          '<div class="wm-item__text">'+esc(a.text||"")+'</div>'+rep+'</div>';}).join("");
      list.querySelectorAll("[data-gdel]").forEach(function(b){b.addEventListener("click",function(){fetch("/wire/markup/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({view:"_global",id:b.getAttribute("data-gdel"),author:user||"?"})}).then(function(){renderGlobal();loadSummary();});});});
      list.querySelectorAll("[data-gres]").forEach(function(b){b.addEventListener("click",function(){fetch("/wire/resolve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({view:"_global",id:b.getAttribute("data-gres"),resolved:b.getAttribute("data-val")==="1"})}).then(function(){renderGlobal();loadSummary();});});});
      wireReply(list,"_global",renderGlobal);
    }).catch(function(){});}
  (function(){var gb=document.getElementById("wire-global-btn"); if(gb)gb.addEventListener("click",function(){var d=document.getElementById("wire-gc"); if(d){d.hidden=false; renderGlobal(); fetch("/wire/reviewed",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({view:"_global"})}).then(function(){setTimeout(loadSummary,400);}).catch(function(){});}});
    var gx=document.getElementById("wire-gc-close"); if(gx)gx.addEventListener("click",function(){var d=document.getElementById("wire-gc");if(d)d.hidden=true;});
    var gbg=document.getElementById("wire-gc-bg"); if(gbg)gbg.addEventListener("click",function(){var d=document.getElementById("wire-gc");if(d)d.hidden=true;});
    var gs=document.getElementById("wire-gc-send"); if(gs)gs.addEventListener("click",function(){ if(!user){askName(function(){});return;} var ta=document.getElementById("wire-gc-compose"); var t=ta.value.trim(); if(!t)return;
      fetch("/wire/markup",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:newId(),view:"_global",type:"comment",author:user,text:t,ts:new Date().toISOString()})}).then(function(){ta.value="";renderGlobal();loadSummary();}).catch(function(){});});})();

  // opening a view counts as reviewing Claude's replies → clear its red dot
  fetch("/wire/reviewed",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({view:VIEW})}).then(function(){setTimeout(loadSummary,500);}).catch(function(){});
  loadSummary(); setInterval(loadSummary, 8000);

  refreshWho(); load();
  if(!user){ /* let them browse; prompt on first tool use */ }
})();
