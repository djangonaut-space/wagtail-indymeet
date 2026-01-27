import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import * as Talks from './talks_data.js';

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera( 75, window.innerWidth / window.innerHeight, 0.1, 1000 );

camera.position.set(0, 0, 2.4);
camera.lookAt(0, 0, 0);

// RENDERER
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize( window.innerWidth, window.innerHeight );
document.body.appendChild( renderer.domElement );

const controls = new OrbitControls( camera, renderer.domElement );
controls.minDistance = 1.5;  // Minimum zoom
controls.maxDistance = 3;   // Maximum zoom
const loader = new GLTFLoader();

// LIGHTS
const ambientLight = new THREE.AmbientLight( 0x333333, 100 );
scene.add( ambientLight );
const dirLight = new THREE.DirectionalLight( 0xffffff, 1 );
dirLight.position.set( 5, 3, 5 );
scene.add( dirLight );

// EARTH SYSTEM
const earthSystem = new THREE.Group();
scene.add(earthSystem);

// EARTH
const textureLoader = new THREE.TextureLoader();
const config = JSON.parse(document.getElementById("earth-config").textContent);
const earthtexture = textureLoader.load(config.earthTextureUrl);

const earthgeometry = new THREE.SphereGeometry(1, 64, 64);
const earthMaterial = new THREE.MeshPhongMaterial({ map: earthtexture, shininess: 10 });
const earth = new THREE.Mesh(earthgeometry, earthMaterial);

earthSystem.add(earth);

// Init talks
Talks.initTalks();

const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();
const clickThreshold = 0.03;

window.addEventListener('click', (event) => {
    mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const rayOrigin = raycaster.ray.origin.clone();
    const rayDir = raycaster.ray.direction.clone();

    let clickedMarker = null;

    Talks.markers.forEach(marker => {
        const worldPos = new THREE.Vector3();
        marker.getWorldPosition(worldPos); // world position changes as Earth rotates
        // Project marker onto ray
        const toMarker = worldPos.clone().sub(rayOrigin);
        const t = toMarker.dot(rayDir);
        const closestPoint = rayOrigin.clone().add(rayDir.clone().multiplyScalar(t));
        const distance = worldPos.distanceTo(closestPoint);
        if (distance < clickThreshold) {
            clickedMarker = marker.userData;
        }
    });

    if (clickedMarker) {
        Talks.showPopup(clickedMarker, event);
    } else {
        Talks.hidePopup();
    }
});

function animate() {
    earth.rotation.x -= 0.00001;
    earth.rotation.y += 0.0005;
    controls.update();
    renderer.render( scene, camera );
}
renderer.setAnimationLoop( animate );

function onWindowResize() {
    const newWidth = window.innerWidth;
    const newHeight = window.innerHeight;
    camera.aspect = newWidth / newHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(newWidth, newHeight);
}
window.addEventListener('resize', onWindowResize, false);

// Load talks
await Talks.loadAndUpdateTalks(earth);
setInterval(() => Talks.loadAndUpdateTalks(earth), 3000);
