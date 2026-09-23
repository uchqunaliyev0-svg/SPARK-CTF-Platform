(() => {
  'use strict';
  const canvas = document.querySelector('canvas.scene');
  if (!canvas || !window.THREE) return;
  const THREE = window.THREE;
  const mode = canvas.dataset.scene || 'hero';
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
  } catch (e) {
    canvas.remove();
    return;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x05070f, 0.045);
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.set(0, 0, 9);

  const CYAN = 0x22d3ee, BLUE = 0x3b82f6, RED = 0xff3b5c;

  function glowTexture(color) {
    const c = document.createElement('canvas');
    c.width = c.height = 128;
    const g = c.getContext('2d');
    const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    grd.addColorStop(0, color);
    grd.addColorStop(0.25, color.replace('1)', '.35)'));
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd;
    g.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
  }

  const core = new THREE.Group();
  scene.add(core);

  const outer = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.7, 1),
    new THREE.MeshBasicMaterial({ color: CYAN, wireframe: true, transparent: true, opacity: 0.55 })
  );
  core.add(outer);

  const inner = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.05, 0),
    new THREE.MeshBasicMaterial({ color: BLUE, transparent: true, opacity: 0.18 })
  );
  const innerWire = new THREE.LineSegments(
    new THREE.EdgesGeometry(new THREE.IcosahedronGeometry(1.06, 0)),
    new THREE.LineBasicMaterial({ color: 0x9be9ff, transparent: true, opacity: 0.9 })
  );
  core.add(inner, innerWire);

  const vertsGeo = new THREE.BufferGeometry().setAttribute('position', outer.geometry.getAttribute('position').clone());
  const verts = new THREE.Points(vertsGeo, new THREE.PointsMaterial({ color: 0xbff4ff, size: 0.07, transparent: true, opacity: 0.9 }));
  core.add(verts);

  const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture('rgba(34,211,238,1)'), blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, opacity: 0.85 }));
  glow.scale.set(6.5, 6.5, 1);
  core.add(glow);
  const redGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture('rgba(255,59,92,1)'), blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, opacity: 0.35 }));
  redGlow.scale.set(4, 4, 1);
  redGlow.position.set(0.8, -0.6, -1);
  core.add(redGlow);

  const rings = [];
  [[2.55, CYAN, 0.9, [1.2, 0.3, 0]], [3.05, RED, 0.55, [0.4, -0.9, 0.3]], [3.5, BLUE, 0.35, [-0.9, 0.2, 0.6]]].forEach(([r, col, op, rot]) => {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(r, 0.008, 8, 160),
      new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: op })
    );
    ring.rotation.set(rot[0], rot[1], rot[2]);
    const sat = new THREE.Mesh(new THREE.OctahedronGeometry(0.09, 0), new THREE.MeshBasicMaterial({ color: col }));
    const satGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(col === RED ? 'rgba(255,59,92,1)' : 'rgba(34,211,238,1)'), blending: THREE.AdditiveBlending, transparent: true, depthWrite: false }));
    satGlow.scale.set(0.8, 0.8, 1);
    sat.add(satGlow);
    ring.add(sat);
    core.add(ring);
    rings.push({ ring, sat, r, speed: 0.25 + Math.random() * 0.35, phase: Math.random() * Math.PI * 2 });
  });

  const COUNT = window.innerWidth < 700 ? 900 : 1800;
  const pos = new Float32Array(COUNT * 3);
  const col = new Float32Array(COUNT * 3);
  const palette = [new THREE.Color(CYAN), new THREE.Color(BLUE), new THREE.Color(RED), new THREE.Color(0xffffff)];
  for (let i = 0; i < COUNT; i++) {
    const r = 5 + Math.random() * 16;
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(2 * Math.random() - 1);
    pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
    pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th) * 0.6;
    pos[i * 3 + 2] = r * Math.cos(ph) - 4;
    const c = palette[Math.random() < 0.08 ? 2 : Math.random() < 0.5 ? 0 : Math.random() < 0.8 ? 1 : 3];
    col.set([c.r, c.g, c.b], i * 3);
  }
  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  starGeo.setAttribute('color', new THREE.BufferAttribute(col, 3));
  const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ size: 0.045, vertexColors: true, transparent: true, opacity: 0.8, depthWrite: false }));
  scene.add(stars);

  let grid = null;
  if (mode === 'hero') {
    grid = new THREE.GridHelper(60, 60, CYAN, 0x1e3a5f);
    grid.material.transparent = true;
    grid.material.opacity = 0.16;
    grid.position.y = -3.6;
    scene.add(grid);
  }

  const glows = [];
  core.traverse((o) => { if (o.isSprite) glows.push(o); });
  function applyTheme() {
    const light = document.documentElement.dataset.theme === 'light';
    scene.fog.color.set(light ? 0xdfe4ec : 0x05070f);
    scene.fog.density = light ? 0.03 : 0.045;
    glows.forEach((g) => { g.material.blending = light ? THREE.NormalBlending : THREE.AdditiveBlending; g.material.needsUpdate = true; });
    stars.material.opacity = light ? 0.55 : 0.8;
    outer.material.color.set(light ? 0x0891b2 : CYAN);
    innerWire.material.color.set(light ? 0x2563eb : 0x9be9ff);
    if (grid) grid.material.opacity = light ? 0.22 : 0.16;
  }
  applyTheme();
  window.addEventListener('spark:theme', () => { applyTheme(); if (reduced) frame(); });

  const mouse = { x: 0, y: 0, tx: 0, ty: 0 };
  window.addEventListener('pointermove', (e) => {
    mouse.tx = (e.clientX / window.innerWidth) * 2 - 1;
    mouse.ty = (e.clientY / window.innerHeight) * 2 - 1;
  }, { passive: true });

  function layout() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    const wide = w / h > 1.15;
    if (mode === 'hero') {
      core.position.set(wide ? 2.6 : 0, wide ? 0.1 : 1.6, 0);
      core.scale.setScalar(wide ? 1 : 0.8);
    } else {
      core.position.set(0, 0.5, 0);
      core.scale.setScalar(0.95);
    }
  }
  layout();
  window.addEventListener('resize', layout);

  let visible = true;
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(([en]) => { visible = en.isIntersecting; }).observe(canvas);
  }

  const clock = new THREE.Clock();
  let intro = 0;
  function frame() {
    const t = clock.getElapsedTime();
    intro = Math.min(intro + 0.012, 1);
    const ease = 1 - Math.pow(1 - intro, 3);
    mouse.x += (mouse.tx - mouse.x) * 0.04;
    mouse.y += (mouse.ty - mouse.y) * 0.04;

    outer.rotation.y = t * 0.18;
    outer.rotation.x = t * 0.07;
    inner.rotation.y = innerWire.rotation.y = -t * 0.35;
    inner.rotation.z = innerWire.rotation.z = t * 0.2;
    verts.rotation.copy(outer.rotation);
    const pulse = 1 + Math.sin(t * 1.6) * 0.04;
    inner.scale.setScalar(pulse);
    innerWire.scale.setScalar(pulse);
    glow.material.opacity = 0.7 + Math.sin(t * 1.6) * 0.15;

    rings.forEach((o) => {
      const a = t * o.speed + o.phase;
      o.sat.position.set(Math.cos(a) * o.r, Math.sin(a) * o.r, 0);
      o.ring.rotation.z += 0.0015;
    });
    core.rotation.y = mouse.x * 0.35;
    core.rotation.x = mouse.y * 0.2;
    stars.rotation.y = t * 0.012;
    if (grid) grid.position.z = (t * 0.6) % 1;

    camera.position.x = mouse.x * 0.5;
    camera.position.y = -mouse.y * 0.3;
    camera.position.z = 9 + (1 - ease) * 6;
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  }

  if (reduced) {
    frame();
    return;
  }
  function loop() {
    requestAnimationFrame(loop);
    if (!visible || document.hidden) return;
    frame();
  }
  loop();
})();
