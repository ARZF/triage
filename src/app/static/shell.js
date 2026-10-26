"use strict";
// ponytail: no framework or build step; move to a component framework if the UI grows.
window.Shell = (() => {
  let options, items=[], opened=false, activeHash="";
  const desktop=matchMedia("(min-width: 900px)");
  const byId=id=>document.getElementById(id);
  function setOpen(value,returnFocus=false) {
    opened=value;
    byId("app-layout").classList.toggle("sidebar-closed",!value);
    byId("menu-toggle").setAttribute("aria-expanded",String(value));
    byId("menu-toggle").setAttribute("aria-label",value?"بستن فهرست":"باز کردن فهرست");
    byId("shell-backdrop").hidden=desktop.matches||!value;
    byId("shell-sidebar").inert=!value;
    byId("shell-main").inert=!desktop.matches&&value;
    document.body.classList.toggle("drawer-open",!desktop.matches&&value);
    if(returnFocus)byId("menu-toggle").focus();
  }
  function initialOpen() {
    let value=desktop.matches;
    if(desktop.matches){try{value=localStorage.getItem("sidebar-open")!=="false";}catch{}}
    setOpen(value);
  }
  function markActive() {
    const item=items.find(item=>item.hash===location.hash);
    byId("shell-title").textContent=item?.title||item?.label||options.title;
    byId("shell-nav").querySelectorAll("a").forEach(link=>{
      if(link.getAttribute("href")===location.hash)link.setAttribute("aria-current","page");
      else link.removeAttribute("aria-current");
    });
  }
  function route() {
    const fallback=options.defaultRoute?.()||items.find(item=>item.hash)?.hash||"#/";
    const valid=location.hash===fallback||items.some(item=>item.hash===location.hash)||options.isRoute?.(location.hash);
    if(!valid){navigate(fallback,true);return;}
    markActive();
    if(!desktop.matches)setOpen(false);
    if(activeHash!==location.hash){activeHash=location.hash;options.onRoute?.(activeHash);}
  }
  function navigate(hash,replace=false) {
    if(replace){history.replaceState(null,"",hash);route();}
    else if(location.hash===hash){route();}
    else location.hash=hash;
  }
  function setItems(list) {
    items=list;
    const nav=byId("shell-nav"),focused=document.activeElement?.getAttribute("href");
    nav.replaceChildren();
    for(const item of items){
      if(item.group){const heading=document.createElement("p");heading.className="nav-group";heading.textContent=item.group;nav.append(heading);continue;}
      const link=document.createElement("a"),label=document.createElement("strong");link.className="nav-item";link.href=item.hash;link.dataset.navId=item.id;label.textContent=item.label;link.append(label);
      if(item.badge!==undefined){const badge=document.createElement("span");badge.className="nav-badge";badge.textContent=Number(item.badge).toLocaleString("fa-IR");link.append(badge);}
      if(item.secondary){const detail=document.createElement("small");detail.textContent=item.secondary;link.append(detail);}
      if(item.status){const status=document.createElement("span");status.className="status-chip";status.textContent=item.status;link.append(status);}
      nav.append(link);
    }
    markActive();
    if(focused){const replacement=[...nav.querySelectorAll("a")].find(link=>link.getAttribute("href")===focused);replacement?.focus({preventScroll:true});}
  }
  function setBadge(id,count) {
    const link=[...byId("shell-nav").querySelectorAll("a")].find(link=>link.dataset.navId===id);
    if(!link)return;
    let badge=link.querySelector(".nav-badge");if(!badge){badge=document.createElement("span");badge.className="nav-badge";link.append(badge);}badge.textContent=Number(count).toLocaleString("fa-IR");
  }
  function init(config) {
    options=config;setItems(config.items);initialOpen();
    const closeButton=document.createElement("button");closeButton.type="button";closeButton.className="drawer-close";closeButton.textContent="بستن فهرست";
    closeButton.addEventListener("click",()=>setOpen(false,true));byId("shell-sidebar").prepend(closeButton);
    byId("menu-toggle").addEventListener("click",()=>{
      setOpen(!opened);
      if(desktop.matches){try{localStorage.setItem("sidebar-open",String(opened));}catch{}}
      else if(opened)byId("shell-sidebar").querySelector("a,button,input")?.focus();
    });
    byId("shell-backdrop").addEventListener("click",()=>setOpen(false,true));
    byId("shell-nav").addEventListener("click",event=>{if(event.target.closest("a")&&!desktop.matches)setOpen(false,true);});
    document.addEventListener("keydown",event=>{
      if(desktop.matches||!opened)return;
      if(event.key==="Escape"){event.preventDefault();setOpen(false,true);}
      if(event.key==="Tab"){
        const focusable=[...byId("shell-sidebar").querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]')].filter(node=>node.getClientRects().length);
        const first=focusable[0],last=focusable[focusable.length-1];
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
      }
    });
    desktop.addEventListener("change",initialOpen);
    window.addEventListener("hashchange",route);route();
  }
  return {init,setItems,setBadge,navigate,close:()=>setOpen(false,true)};
})();

// Shared cursor chat; callers own navigation, permissions, and the surrounding thread.
window.VisitThread = function(options) {
  const {requestId,ownSender,initiallyEnded}=options;
  const panel=document.createElement("section");
  panel.className="live-composer";
  const banner=document.createElement("p");banner.className="visit-chat-banner";
  banner.textContent="این گفتگو برای موارد اورژانسی نیست؛ در شرایط اورژانسی با خدمات اورژانس تماس بگیرید";
  const log=document.createElement("div");log.className="human-log";log.setAttribute("aria-label","پیام‌های ویزیت");
  const scroll=options.scroll;options.logParent.append(log);
  const note=document.createElement("p");note.className="visit-chat-note";note.setAttribute("role","status");
  const label=document.createElement("label"),input=document.createElement("textarea"),error=document.createElement("p"),counter=document.createElement("span"),send=document.createElement("button");
  input.id="visit-input-"+requestId;input.maxLength=2000;input.rows=2;input.dir="auto";input.placeholder="پیام ساختگی خود را بنویسید...";label.htmlFor=input.id;label.textContent="پیام شما";
  error.id="visit-error-"+requestId;error.className="visit-chat-error";error.setAttribute("role","alert");
  counter.id="visit-count-"+requestId;counter.className="visit-chat-count";input.setAttribute("aria-describedby",counter.id+" "+error.id);
  send.type="button";send.textContent="ارسال پیام";const actions=document.createElement("div");actions.className="visit-chat-actions";actions.append(counter,send);
  panel.append(banner,note,label,input,actions,error);options.composer.append(panel);
  let disposed=false,postWarning=false;
  let ended=Boolean(initiallyEnded), full=false, unavailable=false, sending=false, ending=false, reading=false, cursor=0, timer=null, failures=0, endedHistoryLoaded=false;
  const seen=new Set(), messageNodes=new Map();
  const endButton=document.createElement("button"), confirmation=document.createElement("div"), endYes=document.createElement("button"), endNo=document.createElement("button");
  if(options.allowEnd){
    endButton.type=endYes.type=endNo.type="button"; endButton.textContent="پایان ویزیت"; endButton.className="visit-chat-secondary";
    confirmation.hidden=true; confirmation.className="visit-chat-end";
    const question=document.createElement("p"); question.textContent="با پایان ویزیت، ارسال پیام برای هر دو طرف بسته می‌شود. ویزیت پایان یابد؟";
    endYes.textContent="تأیید پایان ویزیت"; endNo.textContent="انصراف"; endNo.className="visit-chat-secondary";
    confirmation.append(question,endYes,endNo); panel.append(endButton,confirmation);
    endButton.addEventListener("click",()=>{confirmation.hidden=false;endYes.focus();});
    endNo.addEventListener("click",()=>{confirmation.hidden=true;endButton.focus();});
    endYes.addEventListener("click",async()=>{
      if(ending||sending||ended)return;
      ending=true;error.textContent="";controls();
      try{await call("/end","POST");setEnded(true);confirmation.hidden=true;await poll();}
      catch(reason){showError(reason);}
      finally{ending=false;controls();}
    });
  }
  function controls(){
    const locked=ended||full||unavailable||sending||ending;
    const length=[...input.value.trim()].length;
    input.disabled=locked;send.disabled=locked||!length||length>2000;
    label.hidden=input.hidden=actions.hidden=ended||full||unavailable;
    banner.hidden=ended;
    send.textContent=sending?"در حال ارسال...":"ارسال پیام";
    counter.textContent=length.toLocaleString("fa-IR")+" / ۲۰۰۰";
    input.setAttribute("aria-invalid",String(length>2000));
    note.hidden=!ended&&!full;
    note.textContent=ended?"این ویزیت پایان یافته است. ارسال پیام بسته است؛ تاریخچهٔ گفتگو همچنان قابل مشاهده است.":full?"ظرفیت ۵۰۰ پیام این گفتگو تکمیل شده است. تاریخچه قابل مشاهده است.":"";
    endButton.hidden=ended;endButton.disabled=unavailable||sending||ending;endYes.disabled=endNo.disabled=sending||ending;
    panel.setAttribute("aria-busy",String(sending||ending));
  }
  function setEnded(value){const changed=!ended&&Boolean(value);ended=ended||Boolean(value);if(ended)confirmation.hidden=true;controls();if(changed&&!disposed)options.onEnded?.();}
  function active(){return !disposed&&!document.hidden&&panel.isConnected&&panel.getClientRects().length>0&&!unavailable;}
  function pause(){clearTimeout(timer);timer=null;}
  function schedule(delay=failures>=2?10000:3000){pause();if(active()&&(!ended||!endedHistoryLoaded))timer=setTimeout(poll,delay);}
  async function call(suffix,method="GET",body){
    const response=await fetch("/v1/visit-requests/"+encodeURIComponent(requestId)+suffix,{
      method,credentials:"same-origin",headers:body?{"Content-Type":"application/json"}:{},
      body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(10000)
    });
    if(response.status===401){location.replace("/login");throw Object.assign(Error(),{status:401});}
    if(!response.ok){
      let code;try{code=(await response.json()).error?.code;}catch{}
      throw Object.assign(Error(),{status:response.status,code});
    }
    return response.json();
  }
  function showError(reason,posting=false){
    if(reason.status===401)return;
    if(reason.status===404){unavailable=true;pause();}
    if(reason.code==="visit_ended")setEnded(true);
    if(reason.code==="chat_full")full=true;
    if(posting)postWarning=true;
    error.textContent=reason.status===404?"این گفتگو در دسترس نیست."
      :reason.code==="visit_ended"?"ویزیت پایان یافته است؛ ارسال پیام ممکن نیست."
      :reason.code==="chat_full"?"ظرفیت ۵۰۰ پیام گفتگو تکمیل شده است."
      :reason.status===422?"پیام باید بین ۱ تا ۲۰۰۰ نویسه باشد."
      :posting?"ارسال تأیید نشد؛ ممکن است پیام ثبت شده باشد. متن حفظ شده است؛ تاریخچه را بررسی کنید و در صورت نیاز دوباره بفرستید."
      :"ارتباط برقرار نشد. دریافت پیام‌ها به‌طور خودکار دوباره انجام می‌شود.";
    controls();
  }
  function append(message,forceScroll=false){
    if(seen.has(message.id))return;
    const follow=scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<64||forceScroll;
    const node=document.createElement("article");node.className="visit-chat-message"+(message.sender===ownSender?" own":"");
    const who=document.createElement("small"), text=document.createElement("p"), time=document.createElement("time");
    who.textContent=message.sender===ownSender?"شما":options.otherLabel||"مخاطب";
    text.textContent=message.content;text.dir="auto";
    time.dateTime=message.created_at;time.textContent=new Date(message.created_at).toLocaleString("fa-IR");
    node.append(who,text,time);
    const next=[...messageNodes.keys()].sort((a,b)=>a-b).find(id=>id>message.id);
    log.insertBefore(node,next===undefined?null:messageNodes.get(next));messageNodes.set(message.id,node);seen.add(message.id);
    if(seen.size>=500)full=true;
    if(follow)scroll.scrollTop=scroll.scrollHeight;
  }
  async function poll(){
    pause();if(!active()||reading)return;
    reading=true;
    try{
      let more;
      do{
        const page=await call("/messages?after="+cursor+"&limit=100");
        if(disposed)return;
        for(const message of page.messages)append(message);
        if(page.messages.length)cursor=page.messages[page.messages.length-1].id;
        setEnded(page.ended);more=page.has_more;
        endedHistoryLoaded=page.ended&&!more;
      }while(more&&active());
      failures=0;if(!postWarning)error.textContent="";controls();
    }catch(reason){failures++;showError(reason);}
    finally{reading=false;schedule();}
  }
  async function post(){
    const content=input.value.trim();
    if(sending||ending||ended||full||unavailable||!content||[...content].length>2000)return;
    sending=true;postWarning=false;error.textContent="";controls();
    try{
      const message=await call("/messages","POST",{content});
      if(disposed)return;
      append(message,true);input.value="";failures=0;await poll();
    }catch(reason){
      // ponytail: POST timeouts have ambiguous outcomes; add idempotency keys before automatic message resending.
      showError(reason,true);schedule();
    }finally{sending=false;controls();}
  }
  input.addEventListener("input",()=>{postWarning=false;error.textContent="";controls();});
  input.addEventListener("keydown",event=>{if(event.key==="Enter"&&!event.shiftKey&&!event.isComposing){event.preventDefault();post();}});
  send.addEventListener("click",post);
  const visibility=()=>{if(document.hidden)pause();else poll();};
  document.addEventListener("visibilitychange",visibility);
  controls();
  poll();
  return {element:panel,list:log,setEnded,resume:()=>schedule(0),dispose:()=>{disposed=true;pause();document.removeEventListener("visibilitychange",visibility);panel.remove();log.remove();}};
}

// Shared form plumbing; page callers own profile fields, routes and role decisions.
window.ProfileRequest = async function(path,body,method="GET") {
  const response=await fetch(path,{method,credentials:"same-origin",headers:body?{"Content-Type":"application/json"}:{},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(10000)});
  if(!response.ok){let code;try{code=(await response.json()).error?.code;}catch{}throw Object.assign(Error("request"),{status:response.status,code,retryAfter:response.headers.get("Retry-After")});}
  return response.status===204?null:response.json();
};
window.ProfileField = function(form,id,labelText,{multiline=false,select=false,password=false,autocomplete="off"}={}) {
  const row=document.createElement("div"),label=document.createElement("label"),input=document.createElement(select?"select":multiline?"textarea":"input"),error=document.createElement("p");
  label.htmlFor=id;label.textContent=labelText;input.id=id;input.name=id;input.dir="auto";input.autocomplete=autocomplete;
  if(password)input.type="password";
  error.id=id+"-error";error.className="field-error";error.setAttribute("role","alert");input.setAttribute("aria-describedby",error.id);
  row.className="profile-field";row.append(label,input,error);form.append(row);
  return {input,error,invalid(text){error.textContent=text;input.setAttribute("aria-invalid",String(Boolean(text)));}};
};
window.PasswordForm = function(root) {
  const heading=document.createElement("h2"),form=document.createElement("form"),message=document.createElement("p"),managed=document.createElement("p");
  heading.textContent="تغییر گذرواژه";form.noValidate=true;message.setAttribute("role","status");managed.hidden=true;managed.className="muted";
  const current=ProfileField(form,"current-password","گذرواژهٔ فعلی",{password:true,autocomplete:"current-password"});
  const next=ProfileField(form,"new-password","گذرواژهٔ جدید",{password:true,autocomplete:"new-password"});
  const confirm=ProfileField(form,"confirm-password","تکرار گذرواژهٔ جدید",{password:true,autocomplete:"new-password"});
  for(const field of [current,next,confirm])field.input.maxLength=128;
  const send=document.createElement("button");send.type="submit";send.textContent="ذخیرهٔ گذرواژه";form.append(send,message);root.append(heading,managed,form);let busy=false;
  form.addEventListener("submit",async event=>{
    event.preventDefault();if(busy)return;message.textContent="";
    current.invalid(current.input.value?"":"گذرواژهٔ فعلی را وارد کنید.");
    const length=[...next.input.value].length;
    next.invalid(length<8||length>128?"گذرواژه باید ۸ تا ۱۲۸ نویسه باشد.":next.input.value===current.input.value?"گذرواژهٔ جدید باید متفاوت باشد.":"");
    confirm.invalid(next.input.value!==confirm.input.value?"تکرار گذرواژه با گذرواژهٔ جدید یکسان نیست.":"");
    if([current,next,confirm].some(field=>field.error.textContent)){[current,next,confirm].find(field=>field.error.textContent).input.focus();return;}
    busy=true;send.disabled=true;form.setAttribute("aria-busy","true");
    try{
      await ProfileRequest("/v1/me/password",{current_password:current.input.value,new_password:next.input.value},"POST");
      form.reset();message.className="success";message.textContent="گذرواژه تغییر کرد؛ دستگاه‌های دیگر از حساب خارج شدند. این نشست همچنان فعال است.";
    }catch(error){
      message.className="error";
      if(error.code==="password_managed"){form.reset();form.hidden=true;managed.hidden=false;managed.textContent="گذرواژهٔ این حساب از تنظیمات سرور مدیریت می‌شود و در این صفحه قابل تغییر نیست.";}
      else if(error.code==="invalid_current_password")current.invalid("گذرواژهٔ فعلی درست نیست.");
      else if(error.status===401)location.replace("/login");
      else if(error.status===429)message.textContent="تلاش‌های ناموفق زیاد بوده است. "+Number(error.retryAfter||900).toLocaleString("fa-IR")+" ثانیه بعد دوباره امتحان کنید.";
      else message.textContent=error.status===422?"اطلاعات گذرواژه را بررسی کنید؛ گذرواژهٔ جدید باید متفاوت و ۸ تا ۱۲۸ نویسه باشد.":"تغییر گذرواژه تأیید نشد. اتصال و وضعیت ورود را بررسی کنید؛ دوباره به‌طور خودکار ارسال نمی‌شود.";
    }finally{busy=false;send.disabled=false;form.setAttribute("aria-busy","false");}
  });
};
