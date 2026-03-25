import * as THREE from 'three';

const spikeColor = 0xda70d6; // light purple
const purpleColor = 0x5c0287; // purple
const spikeHeight = 0.1;
const spikeRadius = 0.01;
export const markers = [];

let markerGeometry = null;
let coneGeometry = null;
export function initTalks() {
    markerGeometry = new THREE.SphereGeometry(0.006, 12, 12);
    coneGeometry = new THREE.ConeGeometry(spikeRadius, spikeHeight, 16, 1, true);
    coneGeometry.rotateX(Math.PI); // invert cone
    coneGeometry.translate(0, spikeHeight / 2, 0);
}

export function mapGeoJsonToTalks(features) {
    return features.map(feature => ({
        lat: feature.geometry.coordinates[1],
        lng: feature.geometry.coordinates[0],
        ...feature.properties
    }));
}

export function updateTalks(talks, earth) {
    // Clear existing markers
    earth.children
        .filter(child => child.isTalkElement)
        .forEach(item => earth.remove(item))
    markers.length = 0;

    talks.forEach(talk => {
        const radius = 1;
        const phi = (90 - talk.lat) * (Math.PI / 180);
        const theta = (talk.lng + 180) * (Math.PI / 180);
        const x = -radius * (Math.sin(phi) * Math.cos(theta));
        const y = radius * Math.cos(phi);
        const z = radius * Math.sin(phi) * Math.sin(theta);

        function createMarkerMaterial(color) {
            return new THREE.MeshStandardMaterial({
                color,
                emissive: color,
                emissiveIntensity: 1,
                opacity: 0.5,
                side: THREE.DoubleSide, // disable backface culling
                transparent: true,
            });
        }

        const marker = new THREE.Mesh(markerGeometry, createMarkerMaterial(purpleColor));
        marker.position.set(x, y, z);
        marker.userData = talk;
        marker.isTalkElement = true;

        const cone = new THREE.Mesh(coneGeometry, createMarkerMaterial(spikeColor));
        cone.position.copy(marker.position);
        cone.isTalkElement = true;
        const normal = marker.position.clone().sub(earth.position).normalize();
        const up = new THREE.Vector3(0, 1, 0); // cone points along +Y
        const quaternion = new THREE.Quaternion().setFromUnitVectors(up, normal);
        cone.quaternion.copy(quaternion);
        earth.add(cone);

        earth.add(marker);
        markers.push(marker);
    });
}

export async function loadAndUpdateTalks(earth) {
    try {
        const response = await fetch('/talks/api/geojson/');
        const data = await response.json();
        const talks = mapGeoJsonToTalks(data.features);
        updateTalks(talks, earth);
    } catch (error) {
        console.error('Failed to load talks:', error);
    }
}

const popup = document.getElementById('markerPopup');

function showPopup(marker, event) {
    popup.innerHTML = marker.popup_html;
    popup.style.display = 'block';
    popup.classList.add('hovered');
}

function hidePopup() {
    popup.style.display = 'none';
}

export { showPopup, hidePopup };
