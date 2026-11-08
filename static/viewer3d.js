// Rotatable STL preview. Needs the importmap in base.html ("three" → vendored build).
import * as THREE from 'three';
import { STLLoader } from '/static/vendor/STLLoader.js';
import { OrbitControls } from '/static/vendor/OrbitControls.js';

const still = matchMedia('(prefers-reduced-motion: reduce)').matches;

// Renders `buffer` (STL bytes) into `box`. Returns a dispose() function; throws if WebGL is unavailable.
export function mountViewer(box, buffer, color = 0x00e5a0) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  box.replaceChildren(renderer.domElement);

  const scene = new THREE.Scene();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x223344, 2.2));
  const sun = new THREE.DirectionalLight(0xffffff, 2);
  sun.position.set(1, 2, 1.5);
  scene.add(sun);

  const geo = new STLLoader().parse(buffer);
  geo.rotateX(-Math.PI / 2);  // STL is Z-up, three.js is Y-up
  geo.computeVertexNormals();
  geo.center();
  geo.computeBoundingSphere();
  const r = geo.boundingSphere.radius || 1;
  scene.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color, roughness: .55, metalness: .05 })));

  const cam = new THREE.PerspectiveCamera(40, 1, r / 100, r * 100);
  cam.position.set(r * 1.6, r * 1.1, r * 2.2);
  const ctl = new OrbitControls(cam, renderer.domElement);
  ctl.enableDamping = true;
  ctl.enablePan = false;
  ctl.autoRotate = !still;
  ctl.autoRotateSpeed = 2.5;
  ctl.addEventListener('start', () => { ctl.autoRotate = false; });

  const resize = () => {
    const { width, height } = box.getBoundingClientRect();
    renderer.setSize(width, height, false);
    cam.aspect = width / height || 1;
    cam.updateProjectionMatrix();
  };
  const ro = new ResizeObserver(resize);
  ro.observe(box);
  resize();
  renderer.setAnimationLoop(() => { ctl.update(); renderer.render(scene, cam); });

  return () => { renderer.setAnimationLoop(null); ro.disconnect(); geo.dispose(); renderer.dispose(); };
}

// Product page: <div data-model="/media/x.stl">fallback</div>
for (const box of document.querySelectorAll('[data-model]')) {
  fetch(box.dataset.model)
    .then(r => { if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); })
    .then(buf => mountViewer(box, buf))
    .catch(() => { box.closest('.media')?.classList.add('no3d'); });  // keep the photo/emoji fallback
}
