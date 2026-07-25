"""
Shape templates: turn a set of reviewed/approved artwork images into a
standalone, self-contained interactive 3D mockup (HTML + Three.js,
drag-to-rotate + lighting tool). No external files, no server needed to
view a published mockup — it's one .html file.

Each template declares the "slots" a staff member needs to fill in during
review (e.g. a cylinder tub needs a wraparound label + a lid). Adding a
new packaging shape later means adding one more entry here.
"""
import base64
import io
from PIL import Image


def _data_uri(img: Image.Image, max_w: int, quality: int = 88) -> str:
    img = img.convert("RGB")
    if img.width > max_w:
        h = int(img.height * max_w / img.width)
        img = img.resize((max_w, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


SHAPE_TEMPLATES = {
    "cylinder": {
        "label": "Cylinder / tub (label wrap + lid)",
        "slots": [
            {"key": "wrap", "label": "Label / wraparound artwork",
             "hint": "The flat wide panel that wraps around the tub body."},
            {"key": "cap", "label": "Lid artwork",
             "hint": "The circular lid graphic, viewed straight-on."},
        ],
    },
    "wedge": {
        "label": "Wedge / triangular box (front + back face)",
        "slots": [
            {"key": "front", "label": "Front / window face artwork",
             "hint": "The main display panel. Blank areas are fine — they usually mark a die-cut window."},
            {"key": "back", "label": "Back / spine face artwork",
             "hint": "The narrow back panel, e.g. product name / storage instructions."},
        ],
    },
    "box": {
        "label": "Rectangular carton / box (front, back + sides)",
        "slots": [
            {"key": "front", "label": "Front face artwork",
             "hint": "The main branded panel — sets the box's width/height proportions."},
            {"key": "back", "label": "Back face artwork",
             "hint": "The rear panel, e.g. ingredients / instructions. Use the same image as front if the box isn't split into separate front/back art."},
            {"key": "side", "label": "Side panel artwork",
             "hint": "The narrow end panel — used on both left and right sides."},
        ],
    },
}


def build_html(shape_key: str, slot_images: dict, brief: dict) -> str:
    if shape_key == "cylinder":
        return _build_cylinder(slot_images, brief)
    elif shape_key == "wedge":
        return _build_wedge(slot_images, brief)
    elif shape_key == "box":
        return _build_box(slot_images, brief)
    raise ValueError(f"Unknown shape template: {shape_key}")


def _header_html(brief: dict) -> tuple:
    brand = brief.get("customer", "").strip() or "Shave & Gibson"
    name_bits = [b for b in [brief.get("product"), brief.get("die_ref")] if b]
    name = " — ".join(name_bits) or "Packaging Proof"
    return brand, name


# ---------------------------------------------------------------------------
# Cylinder / tub template
# ---------------------------------------------------------------------------

def _build_cylinder(slot_images: dict, brief: dict) -> str:
    wrap_img = slot_images["wrap"]
    cap_img = slot_images["cap"]
    label_w, label_h = wrap_img.size
    brand, name = _header_html(brief)

    wrap_uri = _data_uri(wrap_img, 2048)
    cap_uri = _data_uri(cap_img, 1200)

    # Optional fine-tuning from the review screen: where the wrap seam sits
    # (0-100, default 0) and how the lid artwork is rotated (degrees).
    wrap_offset = float(brief.get("wrap_offset", 0)) / 100.0
    lid_rotation_deg = float(brief.get("lid_rotation_deg", 90))

    return _CYLINDER_HTML.replace("__BRAND__", brand) \
        .replace("__NAME__", name) \
        .replace("__WRAP_URI__", wrap_uri) \
        .replace("__CAP_URI__", cap_uri) \
        .replace("__LABEL_W__", str(label_w)) \
        .replace("__LABEL_H__", str(label_h)) \
        .replace("__WRAP_OFFSET__", str(wrap_offset)) \
        .replace("__LID_ROT_DEG__", str(lid_rotation_deg))


_CYLINDER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>__NAME__ — 3D Mockup</title>
<style>
  html, body { margin:0; padding:0; width:100%; height:100%; background:#e9e9ec; overflow:hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; }
  #stage { position:relative; width:100%; height:100%; }
  canvas { display:block; touch-action:none; }
  #hint { position:absolute; left:50%; bottom:22px; transform:translateX(-50%); color:#555; font-size:13px; letter-spacing:.02em; background:rgba(255,255,255,0.75); padding:7px 16px; border-radius:20px; backdrop-filter: blur(4px); box-shadow:0 2px 10px rgba(0,0,0,0.08); user-select:none; pointer-events:none; transition:opacity .6s ease; }
  #title { position:absolute; left:24px; top:20px; color:#333; user-select:none; pointer-events:none; }
  #title .brand { font-size:12px; letter-spacing:.18em; color:#8a8a8a; text-transform:uppercase; }
  #title .name { font-size:19px; font-weight:600; color:#222; margin-top:2px; }
  #loading { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#888; font-size:14px; letter-spacing:.04em; background:#e9e9ec; z-index:5; }
  #lightPanel { position:absolute; right:20px; bottom:20px; width:176px; background:rgba(255,255,255,0.86); backdrop-filter: blur(8px); border-radius:16px; padding:14px 14px 15px; box-shadow:0 6px 22px rgba(0,0,0,0.14); user-select:none; }
  #lightPanel h4 { margin:0 0 10px; font-size:10.5px; letter-spacing:.14em; text-transform:uppercase; color:#9a9a9a; font-weight:700; }
  #lightPad { position:relative; width:100%; aspect-ratio:1/1; border-radius:50%; background: radial-gradient(circle at 50% 38%, #fffdf3, #d3d3d8 80%); box-shadow: inset 0 3px 8px rgba(0,0,0,0.22), inset 0 -1px 2px rgba(255,255,255,0.6); margin-bottom:12px; cursor:grab; touch-action:none; }
  #lightPad::after { content:''; position:absolute; left:50%; top:50%; width:5px; height:5px; background:rgba(0,0,0,0.15); border-radius:50%; transform:translate(-50%,-50%); }
  #lightDot { position:absolute; width:16px; height:16px; border-radius:50%; background:radial-gradient(circle at 35% 30%, #fffbe0, #ffce4d 55%, #dd9c00); box-shadow:0 0 10px rgba(255,200,50,0.85), 0 1px 3px rgba(0,0,0,0.35); transform:translate(-50%,-50%); pointer-events:none; left:50%; top:50%; }
  .rangeRow { display:flex; align-items:center; gap:8px; margin-bottom:9px; }
  .rangeRow label { flex:0 0 auto; font-size:10.5px; color:#777; width:44px; }
  .rangeRow input[type=range] { flex:1; accent-color:#333; }
  .presetRow { display:flex; gap:6px; }
  .presetBtn { flex:1; padding:5px 0; font-size:10px; text-align:center; border-radius:8px; border:1px solid #d9d9dd; background:#fff; color:#666; cursor:pointer; }
  .presetBtn.active { background:#2b2b2b; color:#fff; border-color:#2b2b2b; }
</style>
</head>
<body>
<div id="stage">
  <div id="loading">Loading mockup…</div>
  <div id="title">
    <div class="brand">__BRAND__</div>
    <div class="name">__NAME__</div>
  </div>
  <div id="hint">Drag to rotate &nbsp;•&nbsp; Scroll to zoom</div>
  <div id="lightPanel">
    <h4>Lighting</h4>
    <div id="lightPad"><div id="lightDot"></div></div>
    <div class="rangeRow"><label>Bright</label><input type="range" id="brightSlider" min="20" max="200" value="100"></div>
    <div class="presetRow">
      <div class="presetBtn" data-temp="warm">Warm</div>
      <div class="presetBtn active" data-temp="neutral">Neutral</div>
      <div class="presetBtn" data-temp="cool">Cool</div>
    </div>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const LABEL_IMG = "__WRAP_URI__";
const LID_IMG   = "__CAP_URI__";
const LABEL_W = __LABEL_W__, LABEL_H = __LABEL_H__;

let scene, camera, renderer, canGroup, keyLight, ambientLight;
let dragging=false,lastX=0,lastY=0,rotY=0.6,rotX=-0.12,autoRotate=true,targetDist=4.2,dist=4.2;
const BASE_KEY_INTENSITY=1.05, BASE_AMBIENT_INTENSITY=0.55, LIGHT_DISTANCE=6.5;

init();
function init(){
  scene=new THREE.Scene(); scene.background=new THREE.Color(0xe9e9ec);
  camera=new THREE.PerspectiveCamera(32, window.innerWidth/window.innerHeight, 0.1, 100);
  renderer=new THREE.WebGLRenderer({antialias:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.shadowMap.enabled=true; renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  document.getElementById('stage').prepend(renderer.domElement);

  ambientLight=new THREE.AmbientLight(0xffffff, BASE_AMBIENT_INTENSITY); scene.add(ambientLight);
  keyLight=new THREE.DirectionalLight(0xffffff, BASE_KEY_INTENSITY);
  keyLight.position.set(3,5,4); keyLight.castShadow=true;
  keyLight.shadow.mapSize.set(1024,1024);
  keyLight.shadow.camera.near=1; keyLight.shadow.camera.far=15;
  keyLight.shadow.camera.left=-3; keyLight.shadow.camera.right=3;
  keyLight.shadow.camera.top=3; keyLight.shadow.camera.bottom=-3;
  scene.add(keyLight);
  const fill=new THREE.DirectionalLight(0xdfe8ff,0.32); fill.position.set(-4,2,-3); scene.add(fill);
  const rim=new THREE.DirectionalLight(0xffffff,0.35); rim.position.set(0,2,-5); scene.add(rim);

  const groundGeo=new THREE.PlaneGeometry(20,20);
  const ground=new THREE.Mesh(groundGeo, new THREE.ShadowMaterial({opacity:0.22}));
  ground.rotation.x=-Math.PI/2; ground.position.y=-0.62; ground.receiveShadow=true; scene.add(ground);

  const spot=new THREE.Mesh(new THREE.CircleGeometry(1.6,64), new THREE.MeshBasicMaterial({map:makeRadialShadowTexture(),transparent:true,depthWrite:false}));
  spot.rotation.x=-Math.PI/2; spot.position.y=-0.615; scene.add(spot);

  loadTexturesAndBuildCan();
  window.addEventListener('resize', onResize);
  addPointerControls();
  initLightPanel();
  animate();
}

function makeRadialShadowTexture(){
  const size=256; const c=document.createElement('canvas'); c.width=c.height=size;
  const ctx=c.getContext('2d');
  const g=ctx.createRadialGradient(size/2,size/2,size*0.05,size/2,size/2,size*0.5);
  g.addColorStop(0,'rgba(0,0,0,0.35)'); g.addColorStop(1,'rgba(0,0,0,0)');
  ctx.fillStyle=g; ctx.fillRect(0,0,size,size);
  return new THREE.CanvasTexture(c);
}

function makePaperBumpTexture(repeatX, repeatY){
  const size=256;
  const noise=document.createElement('canvas'); noise.width=noise.height=size;
  const nctx=noise.getContext('2d'); const id=nctx.createImageData(size,size);
  for(let i=0;i<id.data.length;i+=4){ const v=128+(Math.random()-0.5)*95; id.data[i]=id.data[i+1]=id.data[i+2]=v; id.data[i+3]=255; }
  nctx.putImageData(id,0,0);
  const soft=document.createElement('canvas'); soft.width=soft.height=size;
  const sctx=soft.getContext('2d'); sctx.filter='blur(0.6px)'; sctx.drawImage(noise,0,0);
  sctx.filter='none'; sctx.globalAlpha=0.35; sctx.strokeStyle='#808080';
  for(let i=0;i<40;i++){ sctx.lineWidth=0.6+Math.random()*0.8; sctx.beginPath();
    const x=Math.random()*size,y=Math.random()*size,len=6+Math.random()*18,ang=Math.random()*Math.PI*2;
    sctx.moveTo(x,y); sctx.lineTo(x+Math.cos(ang)*len,y+Math.sin(ang)*len); sctx.stroke(); }
  const tex=new THREE.CanvasTexture(soft);
  tex.wrapS=THREE.RepeatWrapping; tex.wrapT=THREE.RepeatWrapping; tex.repeat.set(repeatX,repeatY);
  return tex;
}

function loadTexturesAndBuildCan(){
  let loaded=0; function done(){ loaded++; if(loaded===2) document.getElementById('loading').style.display='none'; }
  const labelTex=new THREE.Texture(); const labelImg=new Image();
  labelImg.onload=()=>{ labelTex.image=labelImg; labelTex.needsUpdate=true; done(); }; labelImg.src=LABEL_IMG;
  labelTex.wrapS=THREE.RepeatWrapping; labelTex.wrapT=THREE.ClampToEdgeWrapping; labelTex.colorSpace=THREE.SRGBColorSpace;
  labelTex.offset.x=__WRAP_OFFSET__;

  const lidTex=new THREE.Texture(); const lidImg=new Image();
  lidImg.onload=()=>{ lidTex.image=lidImg; lidTex.needsUpdate=true; done(); }; lidImg.src=LID_IMG;
  lidTex.colorSpace=THREE.SRGBColorSpace; lidTex.center.set(0.5,0.5); lidTex.rotation=THREE.MathUtils.degToRad(__LID_ROT_DEG__);

  const paperBumpSide=makePaperBumpTexture(24,3), paperBumpCap=makePaperBumpTexture(6,6);
  const RADIUS=1, CIRCUMFERENCE=2*Math.PI*RADIUS, HEIGHT=CIRCUMFERENCE*(LABEL_H/LABEL_W);
  canGroup=new THREE.Group(); scene.add(canGroup);
  const geo=new THREE.CylinderGeometry(RADIUS,RADIUS,HEIGHT,96,1,false);
  const sideMat=new THREE.MeshStandardMaterial({map:labelTex,roughness:0.92,metalness:0.015,bumpMap:paperBumpSide,bumpScale:0.0032});
  const topMat=new THREE.MeshStandardMaterial({map:lidTex,roughness:0.62,metalness:0.05,bumpMap:paperBumpCap,bumpScale:0.0022});
  const bottomMat=new THREE.MeshStandardMaterial({color:0x18140f,roughness:0.9,metalness:0.02,bumpMap:paperBumpCap,bumpScale:0.003});
  const body=new THREE.Mesh(geo,[sideMat,topMat,bottomMat]); body.castShadow=true; body.receiveShadow=true; canGroup.add(body);

  const rimGeo=new THREE.TorusGeometry(RADIUS*1.001,HEIGHT*0.018,12,96);
  const rimMesh=new THREE.Mesh(rimGeo,new THREE.MeshStandardMaterial({color:0xcfcfd2,roughness:0.45,metalness:0.3}));
  rimMesh.rotation.x=Math.PI/2; rimMesh.position.y=HEIGHT/2-HEIGHT*0.02; canGroup.add(rimMesh);
  canGroup.position.y=0;

  const camDist=Math.max(3.6,HEIGHT*2.3); targetDist=camDist; dist=camDist;
  camera.position.set(0,HEIGHT*0.18,camDist); camera.lookAt(0,0,0);
}

function addPointerControls(){
  const el=renderer.domElement, hint=document.getElementById('hint');
  function down(x,y){ dragging=true; lastX=x; lastY=y; autoRotate=false; hint.style.opacity='0'; }
  function move(x,y){ if(!dragging) return; const dx=x-lastX,dy=y-lastY; rotY+=dx*0.006; rotX+=dy*0.004; rotX=Math.max(-0.6,Math.min(0.6,rotX)); lastX=x; lastY=y; }
  function up(){ dragging=false; }
  el.addEventListener('mousedown', e=>down(e.clientX,e.clientY));
  window.addEventListener('mousemove', e=>move(e.clientX,e.clientY));
  window.addEventListener('mouseup', up);
  el.addEventListener('touchstart', e=>{const t=e.touches[0]; down(t.clientX,t.clientY);},{passive:true});
  el.addEventListener('touchmove', e=>{const t=e.touches[0]; move(t.clientX,t.clientY);},{passive:true});
  el.addEventListener('touchend', up);
  el.addEventListener('wheel', e=>{ e.preventDefault(); targetDist+=e.deltaY*0.0025; targetDist=Math.max(2.2,Math.min(9,targetDist)); },{passive:false});
}

function initLightPanel(){
  const pad=document.getElementById('lightPad'), dot=document.getElementById('lightDot');
  const brightSlider=document.getElementById('brightSlider');
  const presetBtns=document.querySelectorAll('.presetBtn');
  function applyFromPad(px,py){
    const r=Math.min(1,Math.hypot(px,py));
    const az=Math.atan2(px,-py);
    const elev=THREE.MathUtils.degToRad(88-r*68);
    const x=LIGHT_DISTANCE*Math.cos(elev)*Math.sin(az);
    const y=LIGHT_DISTANCE*Math.sin(elev);
    const z=LIGHT_DISTANCE*Math.cos(elev)*Math.cos(az);
    keyLight.position.set(x,y,z);
    dot.style.left=(50+px*50)+'%'; dot.style.top=(50+py*50)+'%';
  }
  function padPointer(clientX,clientY){
    const rect=pad.getBoundingClientRect();
    const cx=rect.left+rect.width/2, cy=rect.top+rect.height/2;
    let px=(clientX-cx)/(rect.width/2), py=(clientY-cy)/(rect.height/2);
    const r=Math.hypot(px,py); if(r>1){px/=r;py/=r;}
    applyFromPad(px,py);
  }
  let padDragging=false;
  pad.addEventListener('mousedown', e=>{padDragging=true; padPointer(e.clientX,e.clientY);});
  window.addEventListener('mousemove', e=>{if(padDragging) padPointer(e.clientX,e.clientY);});
  window.addEventListener('mouseup', ()=>padDragging=false);
  pad.addEventListener('touchstart', e=>{const t=e.touches[0]; padDragging=true; padPointer(t.clientX,t.clientY);},{passive:true});
  pad.addEventListener('touchmove', e=>{const t=e.touches[0]; if(padDragging) padPointer(t.clientX,t.clientY);},{passive:true});
  pad.addEventListener('touchend', ()=>padDragging=false);
  applyFromPad(0.51,-0.5);
  brightSlider.addEventListener('input', ()=>{ const v=parseFloat(brightSlider.value)/100; keyLight.intensity=BASE_KEY_INTENSITY*v; ambientLight.intensity=BASE_AMBIENT_INTENSITY*(0.55+0.45*v); });
  presetBtns.forEach(btn=>{ btn.addEventListener('click', ()=>{ presetBtns.forEach(b=>b.classList.remove('active')); btn.classList.add('active');
    const t=btn.dataset.temp; if(t==='warm') keyLight.color.set(0xffdca8); else if(t==='cool') keyLight.color.set(0xd9e8ff); else keyLight.color.set(0xffffff); }); });
}

function onResize(){ camera.aspect=window.innerWidth/window.innerHeight; camera.updateProjectionMatrix(); renderer.setSize(window.innerWidth, window.innerHeight); }

function animate(){
  requestAnimationFrame(animate);
  if(autoRotate) rotY+=0.0022;
  dist+=(targetDist-dist)*0.08;
  if(canGroup){ canGroup.rotation.y=rotY; canGroup.rotation.x=rotX*0.4; }
  const camY=Math.sin(rotX)*dist*0.5+dist*0.16;
  camera.position.set(0,camY,dist); camera.lookAt(0,0,0);
  renderer.render(scene,camera);
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Wedge / triangular box template
# ---------------------------------------------------------------------------

def _build_wedge(slot_images: dict, brief: dict) -> str:
    front_img = slot_images["front"]
    back_img = slot_images["back"]
    brand, name = _header_html(brief)

    front_uri = _data_uri(front_img, 1800)
    back_uri = _data_uri(back_img, 1100)

    fw, fh = front_img.size
    bw, bh = back_img.size
    front_aspect = fw / fh   # drives L / hypotenuse
    back_aspect = bw / bh    # drives L / H  (sanity cross-check with front_aspect in review)

    # H = W = 1 (right-triangle cross-section); solve L from the front face's
    # own aspect ratio so its texture is never stretched.
    hypotenuse = (2 ** 0.5)
    L = front_aspect * hypotenuse

    win_x0 = float(brief.get("win_x0", 7)) / 100.0
    win_x1 = float(brief.get("win_x1", 90)) / 100.0
    win_y0 = float(brief.get("win_y0", 44)) / 100.0
    win_y1 = float(brief.get("win_y1", 90)) / 100.0

    return _WEDGE_HTML.replace("__BRAND__", brand) \
        .replace("__NAME__", name) \
        .replace("__FRONT_URI__", front_uri) \
        .replace("__BACK_URI__", back_uri) \
        .replace("__L__", str(round(L, 4))) \
        .replace("__WIN_X0__", str(win_x0)) \
        .replace("__WIN_X1__", str(win_x1)) \
        .replace("__WIN_Y0__", str(win_y0)) \
        .replace("__WIN_Y1__", str(win_y1))


_WEDGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>__NAME__ — 3D Mockup</title>
<style>
  html, body { margin:0; padding:0; width:100%; height:100%; background:#e9e9ec; overflow:hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; }
  #stage { position:relative; width:100%; height:100%; }
  canvas { display:block; touch-action:none; }
  #hint { position:absolute; left:50%; bottom:22px; transform:translateX(-50%); color:#555; font-size:13px; letter-spacing:.02em; background:rgba(255,255,255,0.75); padding:7px 16px; border-radius:20px; backdrop-filter: blur(4px); box-shadow:0 2px 10px rgba(0,0,0,0.08); user-select:none; pointer-events:none; transition:opacity .6s ease; }
  #title { position:absolute; left:24px; top:20px; color:#333; user-select:none; pointer-events:none; }
  #title .brand { font-size:12px; letter-spacing:.18em; color:#8a8a8a; text-transform:uppercase; }
  #title .name { font-size:19px; font-weight:600; color:#222; margin-top:2px; }
  #loading { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#888; font-size:14px; letter-spacing:.04em; background:#e9e9ec; z-index:5; }
  #lightPanel { position:absolute; right:20px; bottom:20px; width:176px; background:rgba(255,255,255,0.86); backdrop-filter: blur(8px); border-radius:16px; padding:14px 14px 15px; box-shadow:0 6px 22px rgba(0,0,0,0.14); user-select:none; }
  #lightPanel h4 { margin:0 0 10px; font-size:10.5px; letter-spacing:.14em; text-transform:uppercase; color:#9a9a9a; font-weight:700; }
  #lightPad { position:relative; width:100%; aspect-ratio:1/1; border-radius:50%; background: radial-gradient(circle at 50% 38%, #fffdf3, #d3d3d8 80%); box-shadow: inset 0 3px 8px rgba(0,0,0,0.22), inset 0 -1px 2px rgba(255,255,255,0.6); margin-bottom:12px; cursor:grab; touch-action:none; }
  #lightPad::after { content:''; position:absolute; left:50%; top:50%; width:5px; height:5px; background:rgba(0,0,0,0.15); border-radius:50%; transform:translate(-50%,-50%); }
  #lightDot { position:absolute; width:16px; height:16px; border-radius:50%; background:radial-gradient(circle at 35% 30%, #fffbe0, #ffce4d 55%, #dd9c00); box-shadow:0 0 10px rgba(255,200,50,0.85), 0 1px 3px rgba(0,0,0,0.35); transform:translate(-50%,-50%); pointer-events:none; left:50%; top:50%; }
  .rangeRow { display:flex; align-items:center; gap:8px; margin-bottom:9px; }
  .rangeRow label { flex:0 0 auto; font-size:10.5px; color:#777; width:44px; }
  .rangeRow input[type=range] { flex:1; accent-color:#333; }
  .presetRow { display:flex; gap:6px; }
  .presetBtn { flex:1; padding:5px 0; font-size:10px; text-align:center; border-radius:8px; border:1px solid #d9d9dd; background:#fff; color:#666; cursor:pointer; }
  .presetBtn.active { background:#2b2b2b; color:#fff; border-color:#2b2b2b; }
</style>
</head>
<body>
<div id="stage">
  <div id="loading">Loading mockup…</div>
  <div id="title">
    <div class="brand">__BRAND__</div>
    <div class="name">__NAME__</div>
  </div>
  <div id="hint">Drag box to rotate &nbsp;•&nbsp; Scroll to zoom</div>
  <div id="lightPanel">
    <h4>Lighting</h4>
    <div id="lightPad"><div id="lightDot"></div></div>
    <div class="rangeRow"><label>Bright</label><input type="range" id="brightSlider" min="20" max="200" value="100"></div>
    <div class="presetRow">
      <div class="presetBtn" data-temp="warm">Warm</div>
      <div class="presetBtn active" data-temp="neutral">Neutral</div>
      <div class="presetBtn" data-temp="cool">Cool</div>
    </div>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const FRONT_IMG = "__FRONT_URI__";
const BACK_IMG  = "__BACK_URI__";
const KRAFT_COLOR = 0xaa9172;
const W = 1.0, H = 1.0, L = __L__;
const WIN = { x0: __WIN_X0__, x1: __WIN_X1__, y0: __WIN_Y0__, y1: __WIN_Y1__ };

let scene, camera, renderer, canGroup, keyLight, ambientLight;
let dragging=false,lastX=0,lastY=0,rotY=0.7,rotX=-0.16,autoRotate=true,targetDist=4.6,dist=4.6;
const BASE_KEY_INTENSITY=1.05, BASE_AMBIENT_INTENSITY=0.58, LIGHT_DISTANCE=6.5;

init();
function init(){
  scene=new THREE.Scene(); scene.background=new THREE.Color(0xe9e9ec);
  camera=new THREE.PerspectiveCamera(32, window.innerWidth/window.innerHeight, 0.1, 100);
  renderer=new THREE.WebGLRenderer({antialias:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.shadowMap.enabled=true; renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  document.getElementById('stage').prepend(renderer.domElement);

  ambientLight=new THREE.AmbientLight(0xffffff, BASE_AMBIENT_INTENSITY); scene.add(ambientLight);
  keyLight=new THREE.DirectionalLight(0xffffff, BASE_KEY_INTENSITY);
  keyLight.position.set(3,5,4); keyLight.castShadow=true;
  keyLight.shadow.mapSize.set(1024,1024);
  keyLight.shadow.camera.near=1; keyLight.shadow.camera.far=15;
  keyLight.shadow.camera.left=-3; keyLight.shadow.camera.right=3;
  keyLight.shadow.camera.top=3; keyLight.shadow.camera.bottom=-3;
  scene.add(keyLight);
  const fill=new THREE.DirectionalLight(0xdfe8ff,0.32); fill.position.set(-4,2,-3); scene.add(fill);
  const rim=new THREE.DirectionalLight(0xffffff,0.35); rim.position.set(0,2,-5); scene.add(rim);

  const ground=new THREE.Mesh(new THREE.PlaneGeometry(20,20), new THREE.ShadowMaterial({opacity:0.22}));
  ground.rotation.x=-Math.PI/2; ground.position.y=-0.85; ground.receiveShadow=true; scene.add(ground);

  const spot=new THREE.Mesh(new THREE.CircleGeometry(1.9,64), new THREE.MeshBasicMaterial({map:makeRadialShadowTexture(),transparent:true,depthWrite:false}));
  spot.rotation.x=-Math.PI/2; spot.position.y=-0.845; scene.add(spot);

  buildWedge();
  window.addEventListener('resize', onResize);
  addPointerControls();
  initLightPanel();
  animate();
}

function makeRadialShadowTexture(){
  const size=256; const c=document.createElement('canvas'); c.width=c.height=size;
  const ctx=c.getContext('2d');
  const g=ctx.createRadialGradient(size/2,size/2,size*0.05,size/2,size/2,size*0.5);
  g.addColorStop(0,'rgba(0,0,0,0.32)'); g.addColorStop(1,'rgba(0,0,0,0)');
  ctx.fillStyle=g; ctx.fillRect(0,0,size,size);
  return new THREE.CanvasTexture(c);
}

function makePaperBumpTexture(repeatX, repeatY){
  const size=256;
  const noise=document.createElement('canvas'); noise.width=noise.height=size;
  const nctx=noise.getContext('2d'); const id=nctx.createImageData(size,size);
  for(let i=0;i<id.data.length;i+=4){ const v=128+(Math.random()-0.5)*95; id.data[i]=id.data[i+1]=id.data[i+2]=v; id.data[i+3]=255; }
  nctx.putImageData(id,0,0);
  const soft=document.createElement('canvas'); soft.width=soft.height=size;
  const sctx=soft.getContext('2d'); sctx.filter='blur(0.6px)'; sctx.drawImage(noise,0,0);
  sctx.filter='none'; sctx.globalAlpha=0.35; sctx.strokeStyle='#808080';
  for(let i=0;i<40;i++){ sctx.lineWidth=0.6+Math.random()*0.8; sctx.beginPath();
    const x=Math.random()*size,y=Math.random()*size,len=6+Math.random()*18,ang=Math.random()*Math.PI*2;
    sctx.moveTo(x,y); sctx.lineTo(x+Math.cos(ang)*len,y+Math.sin(ang)*len); sctx.stroke(); }
  const tex=new THREE.CanvasTexture(soft);
  tex.wrapS=THREE.RepeatWrapping; tex.wrapT=THREE.RepeatWrapping; tex.repeat.set(repeatX,repeatY);
  return tex;
}

function pushQuad(positions, uvs, corners, cuv){
  const order=[0,1,2,0,2,3];
  for(const idx of order){ const p=corners[idx]; positions.push(p[0],p[1],p[2]); uvs.push(cuv[idx][0],cuv[idx][1]); }
}
function pushTri(positions, uvs, corners){
  for(const p of corners){ positions.push(p[0],p[1],p[2]); uvs.push(0,0); }
}

function buildWedge(){
  let loaded=0; function done(){ loaded++; if(loaded===2) document.getElementById('loading').style.display='none'; }
  const frontTex=new THREE.Texture(); const frontImg=new Image();
  frontImg.onload=()=>{ frontTex.image=frontImg; frontTex.needsUpdate=true; done(); }; frontImg.src=FRONT_IMG;
  frontTex.colorSpace=THREE.SRGBColorSpace;
  const backTex=new THREE.Texture(); const backImg=new Image();
  backImg.onload=()=>{ backTex.image=backImg; backTex.needsUpdate=true; done(); }; backImg.src=BACK_IMG;
  backTex.colorSpace=THREE.SRGBColorSpace;

  const paperBumpBig=makePaperBumpTexture(10,5), paperBumpSmall=makePaperBumpTexture(4,4);
  const matFront=new THREE.MeshStandardMaterial({map:frontTex,roughness:0.9,metalness:0.015,bumpMap:paperBumpBig,bumpScale:0.003});
  const matBack=new THREE.MeshStandardMaterial({map:backTex,roughness:0.9,metalness:0.015,bumpMap:paperBumpBig,bumpScale:0.003});
  const matPlain=new THREE.MeshStandardMaterial({color:KRAFT_COLOR,roughness:0.92,metalness:0.015,bumpMap:paperBumpSmall,bumpScale:0.0035});

  const A0=[0,0,0],B0=[W,0,0],C0=[0,H,0], A1=[0,0,L],B1=[W,0,L],C1=[0,H,L];

  const posBottom=[],uvBottom=[]; pushQuad(posBottom,uvBottom,[A0,B0,B1,A1],[[0,0],[1,0],[1,1],[0,1]]);
  const posBack=[],uvBack=[]; pushQuad(posBack,uvBack,[A0,A1,C1,C0],[[0,0],[1,0],[1,1],[0,1]]);
  const posFront=[],uvFront=[]; pushQuad(posFront,uvFront,[C0,C1,B1,B0],[[0,1],[1,1],[1,0],[0,0]]);
  const posCap0=[],uvCap0=[]; pushTri(posCap0,uvCap0,[A0,C0,B0]);
  const posCap1=[],uvCap1=[]; pushTri(posCap1,uvCap1,[A1,B1,C1]);

  const group=new THREE.Group();
  function addMesh(pos,uv,material){
    const geo=new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pos,3));
    geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv,2));
    geo.computeVertexNormals();
    const mesh=new THREE.Mesh(geo,material); mesh.castShadow=true; mesh.receiveShadow=true; group.add(mesh); return mesh;
  }
  addMesh(posBottom,uvBottom,matPlain);
  addMesh(posBack,uvBack,matBack);
  addMesh(posFront,uvFront,matFront);
  addMesh(posCap0,uvCap0,matPlain);
  addMesh(posCap1,uvCap1,matPlain);

  function lerp3(p,q,t){ return [p[0]+(q[0]-p[0])*t, p[1]+(q[1]-p[1])*t, p[2]+(q[2]-p[2])*t]; }
  function facePoint(u,v){ const lo=lerp3(B0,B1,u), hi=lerp3(C0,C1,u); return lerp3(lo,hi,v); }
  const normal=new THREE.Vector3(H,W,0).normalize();
  const winCorners=[[WIN.x0,WIN.y0],[WIN.x1,WIN.y0],[WIN.x1,WIN.y1],[WIN.x0,WIN.y1]].map(([u,v])=>{
    const p=facePoint(u,v); return [p[0]+normal.x*0.006, p[1]+normal.y*0.006, p[2]+normal.z*0.006];
  });
  const posWin=[],uvWin=[]; pushQuad(posWin,uvWin,winCorners,[[0,0],[1,0],[1,1],[0,1]]);
  const matWindow=new THREE.MeshPhysicalMaterial({color:0xf4f7fa,transparent:true,opacity:0.16,roughness:0.12,metalness:0,clearcoat:1,clearcoatRoughness:0.08,side:THREE.DoubleSide,depthWrite:false});
  addMesh(posWin,uvWin,matWindow);

  group.position.set(-W/3,-H/3,-L/2);
  canGroup=new THREE.Group(); canGroup.add(group); scene.add(canGroup);

  const camDist=Math.max(4.2,L*2.1); targetDist=camDist; dist=camDist;
}

function addPointerControls(){
  const el=renderer.domElement, hint=document.getElementById('hint');
  function down(x,y){ dragging=true; lastX=x; lastY=y; autoRotate=false; hint.style.opacity='0'; }
  function move(x,y){ if(!dragging) return; const dx=x-lastX,dy=y-lastY; rotY+=dx*0.006; rotX+=dy*0.004; rotX=Math.max(-0.6,Math.min(0.6,rotX)); lastX=x; lastY=y; }
  function up(){ dragging=false; }
  el.addEventListener('mousedown', e=>down(e.clientX,e.clientY));
  window.addEventListener('mousemove', e=>move(e.clientX,e.clientY));
  window.addEventListener('mouseup', up);
  el.addEventListener('touchstart', e=>{const t=e.touches[0]; down(t.clientX,t.clientY);},{passive:true});
  el.addEventListener('touchmove', e=>{const t=e.touches[0]; move(t.clientX,t.clientY);},{passive:true});
  el.addEventListener('touchend', up);
  el.addEventListener('wheel', e=>{ e.preventDefault(); targetDist+=e.deltaY*0.003; targetDist=Math.max(2.4,Math.min(10,targetDist)); },{passive:false});
}

function initLightPanel(){
  const pad=document.getElementById('lightPad'), dot=document.getElementById('lightDot');
  const brightSlider=document.getElementById('brightSlider');
  const presetBtns=document.querySelectorAll('.presetBtn');
  function applyFromPad(px,py){
    const r=Math.min(1,Math.hypot(px,py));
    const az=Math.atan2(px,-py);
    const elev=THREE.MathUtils.degToRad(88-r*68);
    const x=LIGHT_DISTANCE*Math.cos(elev)*Math.sin(az);
    const y=LIGHT_DISTANCE*Math.sin(elev);
    const z=LIGHT_DISTANCE*Math.cos(elev)*Math.cos(az);
    keyLight.position.set(x,y,z);
    dot.style.left=(50+px*50)+'%'; dot.style.top=(50+py*50)+'%';
  }
  function padPointer(clientX,clientY){
    const rect=pad.getBoundingClientRect();
    const cx=rect.left+rect.width/2, cy=rect.top+rect.height/2;
    let px=(clientX-cx)/(rect.width/2), py=(clientY-cy)/(rect.height/2);
    const r=Math.hypot(px,py); if(r>1){px/=r;py/=r;}
    applyFromPad(px,py);
  }
  let padDragging=false;
  pad.addEventListener('mousedown', e=>{padDragging=true; padPointer(e.clientX,e.clientY);});
  window.addEventListener('mousemove', e=>{if(padDragging) padPointer(e.clientX,e.clientY);});
  window.addEventListener('mouseup', ()=>padDragging=false);
  pad.addEventListener('touchstart', e=>{const t=e.touches[0]; padDragging=true; padPointer(t.clientX,t.clientY);},{passive:true});
  pad.addEventListener('touchmove', e=>{const t=e.touches[0]; if(padDragging) padPointer(t.clientX,t.clientY);},{passive:true});
  pad.addEventListener('touchend', ()=>padDragging=false);
  applyFromPad(0.51,-0.5);
  brightSlider.addEventListener('input', ()=>{ const v=parseFloat(brightSlider.value)/100; keyLight.intensity=BASE_KEY_INTENSITY*v; ambientLight.intensity=BASE_AMBIENT_INTENSITY*(0.55+0.45*v); });
  presetBtns.forEach(btn=>{ btn.addEventListener('click', ()=>{ presetBtns.forEach(b=>b.classList.remove('active')); btn.classList.add('active');
    const t=btn.dataset.temp; if(t==='warm') keyLight.color.set(0xffdca8); else if(t==='cool') keyLight.color.set(0xd9e8ff); else keyLight.color.set(0xffffff); }); });
}

function onResize(){ camera.aspect=window.innerWidth/window.innerHeight; camera.updateProjectionMatrix(); renderer.setSize(window.innerWidth, window.innerHeight); }

function animate(){
  requestAnimationFrame(animate);
  if(autoRotate) rotY+=0.0022;
  dist+=(targetDist-dist)*0.08;
  if(canGroup){ canGroup.rotation.y=rotY; canGroup.rotation.x=rotX*0.4; }
  const camY=Math.sin(rotX)*dist*0.5+dist*0.2;
  camera.position.set(0,camY,dist); camera.lookAt(0,0,0);
  renderer.render(scene,camera);
}
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Rectangular carton / box template (6-face folding carton)
# ---------------------------------------------------------------------------

def _build_box(slot_images: dict, brief: dict) -> str:
    front_img = slot_images["front"]
    back_img = slot_images["back"]
    side_img = slot_images["side"]
    brand, name = _header_html(brief)

    front_uri = _data_uri(front_img, 1800)
    back_uri = _data_uri(back_img, 1800)
    side_uri = _data_uri(side_img, 1200)

    fw, fh = front_img.size
    front_aspect = fw / fh  # width / height of the box, from the front face

    # We don't have real-world dimensions parsed out of the PDF, so depth is a
    # reasonable default relative to width — tunable from the review screen
    # for cartons that are noticeably deeper/shallower than typical.
    depth_ratio = float(brief.get("box_depth_ratio", 32)) / 100.0

    W = 1.0
    H = W / front_aspect
    D = W * depth_ratio

    return _BOX_HTML.replace("__BRAND__", brand) \
        .replace("__NAME__", name) \
        .replace("__FRONT_URI__", front_uri) \
        .replace("__BACK_URI__", back_uri) \
        .replace("__SIDE_URI__", side_uri) \
        .replace("__W__", str(round(W, 4))) \
        .replace("__H__", str(round(H, 4))) \
        .replace("__D__", str(round(D, 4)))


_BOX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>__NAME__ — 3D Mockup</title>
<style>
  html, body { margin:0; padding:0; width:100%; height:100%; background:#e9e9ec; overflow:hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; }
  #stage { position:relative; width:100%; height:100%; }
  canvas { display:block; touch-action:none; }
  #hint { position:absolute; left:50%; bottom:22px; transform:translateX(-50%); color:#555; font-size:13px; letter-spacing:.02em; background:rgba(255,255,255,0.75); padding:7px 16px; border-radius:20px; backdrop-filter: blur(4px); box-shadow:0 2px 10px rgba(0,0,0,0.08); user-select:none; pointer-events:none; transition:opacity .6s ease; }
  #title { position:absolute; left:24px; top:20px; color:#333; user-select:none; pointer-events:none; }
  #title .brand { font-size:12px; letter-spacing:.18em; color:#8a8a8a; text-transform:uppercase; }
  #title .name { font-size:19px; font-weight:600; color:#222; margin-top:2px; }
  #loading { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:#888; font-size:14px; letter-spacing:.04em; background:#e9e9ec; z-index:5; }
  #lightPanel { position:absolute; right:20px; bottom:20px; width:176px; background:rgba(255,255,255,0.86); backdrop-filter: blur(8px); border-radius:16px; padding:14px 14px 15px; box-shadow:0 6px 22px rgba(0,0,0,0.14); user-select:none; }
  #lightPanel h4 { margin:0 0 10px; font-size:10.5px; letter-spacing:.14em; text-transform:uppercase; color:#9a9a9a; font-weight:700; }
  #lightPad { position:relative; width:100%; aspect-ratio:1/1; border-radius:50%; background: radial-gradient(circle at 50% 38%, #fffdf3, #d3d3d8 80%); box-shadow: inset 0 3px 8px rgba(0,0,0,0.22), inset 0 -1px 2px rgba(255,255,255,0.6); margin-bottom:12px; cursor:grab; touch-action:none; }
  #lightPad::after { content:''; position:absolute; left:50%; top:50%; width:5px; height:5px; background:rgba(0,0,0,0.15); border-radius:50%; transform:translate(-50%,-50%); }
  #lightDot { position:absolute; width:16px; height:16px; border-radius:50%; background:radial-gradient(circle at 35% 30%, #fffbe0, #ffce4d 55%, #dd9c00); box-shadow:0 0 10px rgba(255,200,50,0.85), 0 1px 3px rgba(0,0,0,0.35); transform:translate(-50%,-50%); pointer-events:none; left:50%; top:50%; }
  .rangeRow { display:flex; align-items:center; gap:8px; margin-bottom:9px; }
  .rangeRow label { flex:0 0 auto; font-size:10.5px; color:#777; width:44px; }
  .rangeRow input[type=range] { flex:1; accent-color:#333; }
  .presetRow { display:flex; gap:6px; }
  .presetBtn { flex:1; padding:5px 0; font-size:10px; text-align:center; border-radius:8px; border:1px solid #d9d9dd; background:#fff; color:#666; cursor:pointer; }
  .presetBtn.active { background:#2b2b2b; color:#fff; border-color:#2b2b2b; }
</style>
</head>
<body>
<div id="stage">
  <div id="loading">Loading mockup…</div>
  <div id="title">
    <div class="brand">__BRAND__</div>
    <div class="name">__NAME__</div>
  </div>
  <div id="hint">Drag box to rotate &nbsp;•&nbsp; Scroll to zoom</div>
  <div id="lightPanel">
    <h4>Lighting</h4>
    <div id="lightPad"><div id="lightDot"></div></div>
    <div class="rangeRow"><label>Bright</label><input type="range" id="brightSlider" min="20" max="200" value="100"></div>
    <div class="presetRow">
      <div class="presetBtn" data-temp="warm">Warm</div>
      <div class="presetBtn active" data-temp="neutral">Neutral</div>
      <div class="presetBtn" data-temp="cool">Cool</div>
    </div>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const FRONT_IMG = "__FRONT_URI__";
const BACK_IMG  = "__BACK_URI__";
const SIDE_IMG  = "__SIDE_URI__";
const BOARD_COLOR = 0xd8cfbd;
const W = __W__, H = __H__, D = __D__;

let scene, camera, renderer, canGroup, keyLight, ambientLight;
let dragging=false,lastX=0,lastY=0,rotY=0.7,rotX=-0.16,autoRotate=true,targetDist=4.6,dist=4.6;
const BASE_KEY_INTENSITY=1.05, BASE_AMBIENT_INTENSITY=0.58, LIGHT_DISTANCE=6.5;

init();
function init(){
  scene=new THREE.Scene(); scene.background=new THREE.Color(0xe9e9ec);
  camera=new THREE.PerspectiveCamera(32, window.innerWidth/window.innerHeight, 0.1, 100);
  renderer=new THREE.WebGLRenderer({antialias:true});
  renderer.setPixelRatio(Math.min(window.devicePixelRatio,2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.shadowMap.enabled=true; renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  document.getElementById('stage').prepend(renderer.domElement);

  ambientLight=new THREE.AmbientLight(0xffffff, BASE_AMBIENT_INTENSITY); scene.add(ambientLight);
  keyLight=new THREE.DirectionalLight(0xffffff, BASE_KEY_INTENSITY);
  keyLight.position.set(3,5,4); keyLight.castShadow=true;
  keyLight.shadow.mapSize.set(1024,1024);
  keyLight.shadow.camera.near=1; keyLight.shadow.camera.far=15;
  keyLight.shadow.camera.left=-3; keyLight.shadow.camera.right=3;
  keyLight.shadow.camera.top=3; keyLight.shadow.camera.bottom=-3;
  scene.add(keyLight);
  const fill=new THREE.DirectionalLight(0xdfe8ff,0.32); fill.position.set(-4,2,-3); scene.add(fill);
  const rim=new THREE.DirectionalLight(0xffffff,0.35); rim.position.set(0,2,-5); scene.add(rim);

  const groundY = -H/2 - 0.02;
  const ground=new THREE.Mesh(new THREE.PlaneGeometry(20,20), new THREE.ShadowMaterial({opacity:0.22}));
  ground.rotation.x=-Math.PI/2; ground.position.y=groundY; ground.receiveShadow=true; scene.add(ground);

  const spot=new THREE.Mesh(new THREE.CircleGeometry(Math.max(W,D)*1.6,64), new THREE.MeshBasicMaterial({map:makeRadialShadowTexture(),transparent:true,depthWrite:false}));
  spot.rotation.x=-Math.PI/2; spot.position.y=groundY+0.005; scene.add(spot);

  buildBox();
  window.addEventListener('resize', onResize);
  addPointerControls();
  initLightPanel();
  animate();
}

function makeRadialShadowTexture(){
  const size=256; const c=document.createElement('canvas'); c.width=c.height=size;
  const ctx=c.getContext('2d');
  const g=ctx.createRadialGradient(size/2,size/2,size*0.05,size/2,size/2,size*0.5);
  g.addColorStop(0,'rgba(0,0,0,0.32)'); g.addColorStop(1,'rgba(0,0,0,0)');
  ctx.fillStyle=g; ctx.fillRect(0,0,size,size);
  return new THREE.CanvasTexture(c);
}

function makePaperBumpTexture(repeatX, repeatY){
  const size=256;
  const noise=document.createElement('canvas'); noise.width=noise.height=size;
  const nctx=noise.getContext('2d'); const id=nctx.createImageData(size,size);
  for(let i=0;i<id.data.length;i+=4){ const v=128+(Math.random()-0.5)*95; id.data[i]=id.data[i+1]=id.data[i+2]=v; id.data[i+3]=255; }
  nctx.putImageData(id,0,0);
  const soft=document.createElement('canvas'); soft.width=soft.height=size;
  const sctx=soft.getContext('2d'); sctx.filter='blur(0.6px)'; sctx.drawImage(noise,0,0);
  sctx.filter='none'; sctx.globalAlpha=0.35; sctx.strokeStyle='#808080';
  for(let i=0;i<40;i++){ sctx.lineWidth=0.6+Math.random()*0.8; sctx.beginPath();
    const x=Math.random()*size,y=Math.random()*size,len=6+Math.random()*18,ang=Math.random()*Math.PI*2;
    sctx.moveTo(x,y); sctx.lineTo(x+Math.cos(ang)*len,y+Math.sin(ang)*len); sctx.stroke(); }
  const tex=new THREE.CanvasTexture(soft);
  tex.wrapS=THREE.RepeatWrapping; tex.wrapT=THREE.RepeatWrapping; tex.repeat.set(repeatX,repeatY);
  return tex;
}

function buildBox(){
  let loaded=0; function done(){ loaded++; if(loaded===3) document.getElementById('loading').style.display='none'; }
  const frontTex=new THREE.Texture(); const frontImg=new Image();
  frontImg.onload=()=>{ frontTex.image=frontImg; frontTex.needsUpdate=true; done(); }; frontImg.src=FRONT_IMG;
  frontTex.colorSpace=THREE.SRGBColorSpace;
  const backTex=new THREE.Texture(); const backImg=new Image();
  backImg.onload=()=>{ backTex.image=backImg; backTex.needsUpdate=true; done(); }; backImg.src=BACK_IMG;
  backTex.colorSpace=THREE.SRGBColorSpace;
  const sideTex=new THREE.Texture(); const sideImg=new Image();
  sideImg.onload=()=>{ sideTex.image=sideImg; sideTex.needsUpdate=true; done(); }; sideImg.src=SIDE_IMG;
  sideTex.colorSpace=THREE.SRGBColorSpace;

  const paperBump=makePaperBumpTexture(8,6), paperBumpEnd=makePaperBumpTexture(5,5);
  const matFront=new THREE.MeshStandardMaterial({map:frontTex,roughness:0.9,metalness:0.015,bumpMap:paperBump,bumpScale:0.003});
  const matBack=new THREE.MeshStandardMaterial({map:backTex,roughness:0.9,metalness:0.015,bumpMap:paperBump,bumpScale:0.003});
  const matSide=new THREE.MeshStandardMaterial({map:sideTex,roughness:0.9,metalness:0.015,bumpMap:paperBumpEnd,bumpScale:0.003});
  const matPlain=new THREE.MeshStandardMaterial({color:BOARD_COLOR,roughness:0.94,metalness:0.01,bumpMap:paperBumpEnd,bumpScale:0.0035});

  // BoxGeometry material order: [+X right, -X left, +Y top, -Y bottom, +Z front, -Z back]
  const geo=new THREE.BoxGeometry(W,H,D);
  const materials=[matSide,matSide,matPlain,matPlain,matFront,matBack];
  const body=new THREE.Mesh(geo,materials); body.castShadow=true; body.receiveShadow=true;

  canGroup=new THREE.Group(); canGroup.add(body); scene.add(canGroup);

  const camDist=Math.max(3.6, Math.max(W,H)*2.6); targetDist=camDist; dist=camDist;
}

function addPointerControls(){
  const el=renderer.domElement, hint=document.getElementById('hint');
  function down(x,y){ dragging=true; lastX=x; lastY=y; autoRotate=false; hint.style.opacity='0'; }
  function move(x,y){ if(!dragging) return; const dx=x-lastX,dy=y-lastY; rotY+=dx*0.006; rotX+=dy*0.004; rotX=Math.max(-0.6,Math.min(0.6,rotX)); lastX=x; lastY=y; }
  function up(){ dragging=false; }
  el.addEventListener('mousedown', e=>down(e.clientX,e.clientY));
  window.addEventListener('mousemove', e=>move(e.clientX,e.clientY));
  window.addEventListener('mouseup', up);
  el.addEventListener('touchstart', e=>{const t=e.touches[0]; down(t.clientX,t.clientY);},{passive:true});
  el.addEventListener('touchmove', e=>{const t=e.touches[0]; move(t.clientX,t.clientY);},{passive:true});
  el.addEventListener('touchend', up);
  el.addEventListener('wheel', e=>{ e.preventDefault(); targetDist+=e.deltaY*0.003; targetDist=Math.max(2.2,Math.min(10,targetDist)); },{passive:false});
}

function initLightPanel(){
  const pad=document.getElementById('lightPad'), dot=document.getElementById('lightDot');
  const brightSlider=document.getElementById('brightSlider');
  const presetBtns=document.querySelectorAll('.presetBtn');
  function applyFromPad(px,py){
    const r=Math.min(1,Math.hypot(px,py));
    const az=Math.atan2(px,-py);
    const elev=THREE.MathUtils.degToRad(88-r*68);
    const x=LIGHT_DISTANCE*Math.cos(elev)*Math.sin(az);
    const y=LIGHT_DISTANCE*Math.sin(elev);
    const z=LIGHT_DISTANCE*Math.cos(elev)*Math.cos(az);
    keyLight.position.set(x,y,z);
    dot.style.left=(50+px*50)+'%'; dot.style.top=(50+py*50)+'%';
  }
  function padPointer(clientX,clientY){
    const rect=pad.getBoundingClientRect();
    const cx=rect.left+rect.width/2, cy=rect.top+rect.height/2;
    let px=(clientX-cx)/(rect.width/2), py=(clientY-cy)/(rect.height/2);
    const r=Math.hypot(px,py); if(r>1){px/=r;py/=r;}
    applyFromPad(px,py);
  }
  let padDragging=false;
  pad.addEventListener('mousedown', e=>{padDragging=true; padPointer(e.clientX,e.clientY);});
  window.addEventListener('mousemove', e=>{if(padDragging) padPointer(e.clientX,e.clientY);});
  window.addEventListener('mouseup', ()=>padDragging=false);
  pad.addEventListener('touchstart', e=>{const t=e.touches[0]; padDragging=true; padPointer(t.clientX,t.clientY);},{passive:true});
  pad.addEventListener('touchmove', e=>{const t=e.touches[0]; if(padDragging) padPointer(t.clientX,t.clientY);},{passive:true});
  pad.addEventListener('touchend', ()=>padDragging=false);
  applyFromPad(0.51,-0.5);
  brightSlider.addEventListener('input', ()=>{ const v=parseFloat(brightSlider.value)/100; keyLight.intensity=BASE_KEY_INTENSITY*v; ambientLight.intensity=BASE_AMBIENT_INTENSITY*(0.55+0.45*v); });
  presetBtns.forEach(btn=>{ btn.addEventListener('click', ()=>{ presetBtns.forEach(b=>b.classList.remove('active')); btn.classList.add('active');
    const t=btn.dataset.temp; if(t==='warm') keyLight.color.set(0xffdca8); else if(t==='cool') keyLight.color.set(0xd9e8ff); else keyLight.color.set(0xffffff); }); });
}

function onResize(){ camera.aspect=window.innerWidth/window.innerHeight; camera.updateProjectionMatrix(); renderer.setSize(window.innerWidth, window.innerHeight); }

function animate(){
  requestAnimationFrame(animate);
  if(autoRotate) rotY+=0.0022;
  dist+=(targetDist-dist)*0.08;
  if(canGroup){ canGroup.rotation.y=rotY; canGroup.rotation.x=rotX*0.4; }
  const camY=Math.sin(rotX)*dist*0.5+dist*0.2;
  camera.position.set(0,camY,dist); camera.lookAt(0,0,0);
  renderer.render(scene,camera);
}
</script>
</body>
</html>
"""
