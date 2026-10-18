"""Small, dependency-free guest web surface for the public match pages.

The page intentionally uses plain HTML and browser APIs so it can be served by
the same FastAPI process in the Docker image and tested from Selenium.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NaSCon Live</title><style>
:root{font-family:system-ui,sans-serif;color:#16202a;background:#f5f7fa}*{box-sizing:border-box}body{margin:0}
header{background:#102a43;color:#fff;padding:1rem 5vw;display:flex;justify-content:space-between;align-items:center}
main{max-width:1100px;margin:auto;padding:1rem 5vw;display:grid;gap:1rem;grid-template-columns:minmax(0,2fr) minmax(240px,1fr)}
section{background:#fff;border-radius:12px;padding:1rem;box-shadow:0 2px 9px #102a4314}.video{aspect-ratio:16/9;background:#0d1722;color:#d8e4ef;display:grid;place-items:center;border-radius:8px}
.score{display:flex;justify-content:space-around;text-align:center;font-size:2rem}.score small{display:block;font-size:.8rem;color:#627d98}.actions{display:flex;gap:.5rem;flex-wrap:wrap}button{border:0;border-radius:7px;padding:.65rem .9rem;background:#147d92;color:white;cursor:pointer}button.secondary{background:#52606d}ul{padding-left:1.2rem}.muted{color:#627d98;font-size:.9rem}
.modal{position:fixed;inset:0;background:#102a4380;display:none;place-items:center;padding:1rem}.modal.open{display:grid}.dialog{background:#fff;border-radius:12px;padding:1.2rem;max-width:360px;width:100%}.dialog input{width:100%;padding:.65rem;margin:.35rem 0 1rem;border:1px solid #bcccdc;border-radius:6px}.error{color:#c53030;min-height:1.3rem}
@media(max-width:700px){main{display:block}.sidebar{margin-top:1rem}.score{font-size:1.6rem}header{padding:.8rem 1rem}}
</style></head><body>
<header><strong>NaSCon Live</strong><span id="match-label">Guest player</span></header>
<main data-testid="guest-player-shell">
<div><section><div class="video" data-testid="guest-player-video" role="img" aria-label="Live stream">Live stream preview</div>
<div class="actions" style="margin-top:.8rem"><button id="watch" data-testid="guest-watch-button">Watch live</button><button class="secondary" id="cart-add" data-testid="guest-cart-add">Stage jersey</button><button class="secondary" id="chat-open" data-testid="guest-chat-open">Join chat</button></div></section>
<section aria-label="Live score"><h2>Live score</h2><div class="score" data-testid="guest-scoreboard"><div><small id="home-name">Home</small><span data-testid="guest-score-home">0</span></div><div><small id="match-status">UPCOMING</small><span>–</span></div><div><small id="away-name">Away</small><span data-testid="guest-score-away">0</span></div></div><p class="muted" id="score-updated">Waiting for score updates…</p></section></div>
<aside class="sidebar"><section><h2>Staged cart</h2><ul data-testid="guest-cart-items" id="cart-items"><li>Cart is empty</li></ul><p id="cart-total">0 items</p><button data-testid="guest-cart" id="cart-continue">Continue to checkout</button></section>
<section data-testid="guest-chat"><h2>Chat</h2><p class="muted" id="chat-status">Sign in to send messages.</p><div id="chat-messages"></div><button id="chat-signin">Sign in to chat</button></section></aside></main>
<div class="modal" id="auth-modal" data-testid="guest-auth-modal" role="dialog" aria-modal="true" aria-labelledby="auth-title"><div class="dialog"><h2 id="auth-title">Continue with your account</h2><p class="muted">Guests can watch and stage a cart. Sign in to join chat or checkout.</p><form id="auth-form"><label>Email<input id="auth-email" type="email" required autocomplete="username" placeholder="player@nascon.test"></label><label>Password<input id="auth-password" type="password" required autocomplete="current-password" placeholder="Nascon@26"></label><div class="error" id="auth-error"></div><div class="actions"><button type="submit">Sign in</button><button type="button" class="secondary" id="auth-close">Cancel</button></div></form></div></div>
<script>
const matchId=new URLSearchParams(location.search).get('match')||location.pathname.split('/').filter(Boolean).pop()||'demo-match';
const cart=JSON.parse(localStorage.getItem('nascon_guest_cart')||'[]'); let token=localStorage.getItem('nascon_guest_token'); let account=localStorage.getItem('nascon_account');
const $=id=>document.getElementById(id), showAuth=()=>$('auth-modal').classList.add('open');
function renderCart(){const list=$('cart-items');list.innerHTML='';if(!cart.length){list.innerHTML='<li>Cart is empty</li>'}else{cart.forEach(i=>{const li=document.createElement('li');li.textContent=i.name+' × '+i.quantity;list.appendChild(li)})}$('cart-total').textContent=cart.reduce((n,i)=>n+i.quantity,0)+' item(s)';localStorage.setItem('nascon_guest_cart',JSON.stringify(cart))}
async function updateScore(){try{const r=await fetch('/audit/v1/score/'+encodeURIComponent(matchId));if(!r.ok) return;const d=await r.json();$('home-name').textContent=d.home.team_id;$('away-name').textContent=d.away.team_id;$('[data-testid="guest-score-home"]').textContent=d.home.score;$('[data-testid="guest-score-away"]').textContent=d.away.score;$('match-status').textContent=d.status.replace('_',' ').toUpperCase();$('score-updated').textContent='Updated '+new Date().toLocaleTimeString()}catch(e){}}
async function guestToken(){if(token)return token;const r=await fetch('/api/v1/guest/token',{method:'POST'});if(r.ok){token=(await r.json()).guest_token;localStorage.setItem('nascon_guest_token',token)}return token}
$('watch').onclick=async()=>{await guestToken();$('watch').textContent='Watching live'};
$('cart-add').onclick=()=>{const item=cart.find(x=>x.variant_id==='var-jersey-001-M');if(item)item.quantity++;else cart.push({variant_id:'var-jersey-001-M',name:'Official jersey',quantity:1});renderCart()};
function requireAuth(){if(!account){showAuth();return false}return true}
$('chat-open').onclick=()=>{if(requireAuth())$('chat-status').textContent='Chat enabled for '+account};$('chat-signin').onclick=showAuth;$('cart-continue').onclick=()=>{if(requireAuth())location.href='/web/checkout'};$('auth-close').onclick=()=>$('auth-modal').classList.remove('open');
$('auth-form').onsubmit=async e=>{e.preventDefault();$('auth-error').textContent='';const r=await fetch('/mobile/v1/login',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({email:$('auth-email').value,password:$('auth-password').value})});if(!r.ok){$('auth-error').textContent='Check your email and password.';return}const d=await r.json();account=d.email;localStorage.setItem('nascon_account',account);localStorage.setItem('nascon_mobile_token',d.token);$('auth-modal').classList.remove('open');$('chat-status').textContent='Chat enabled for '+account};
renderCart();updateScore();setInterval(updateScore,5000);
</script></body></html>'''


@router.get("/web", response_class=HTMLResponse)
@router.get("/web/", response_class=HTMLResponse)
@router.get("/web/{page:path}", response_class=HTMLResponse)
def guest_web(page: str = ""):
    return HTMLResponse(PAGE)
