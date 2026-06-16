import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const container = document.getElementById("viewer");
const statusEl = document.getElementById("viewer-status");
const hudTitle = document.querySelector("#hud strong");

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x12100e);

const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100);
camera.position.set(2.4, 1.6, 3.2);
camera.up.set(0, 1, 0);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
container.appendChild(renderer.domElement);

const DEFAULT_3D_CAMERA_OFFSET = new THREE.Vector3(2.4, 1.6, 3.2);
const avatarViewCenter = new THREE.Vector3(0, 0, 0);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 0, 0);
controls.enablePan = false;
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minPolarAngle = 0.08;
controls.maxPolarAngle = Math.PI / 2;
controls.minDistance = 0.6;
controls.maxDistance = 8.0;
controls.update();

let currentViewMode = "3d";
let currentRadius = 1.1;
let lastViewportWidth = 0;
let lastViewportHeight = 0;
let lastTwoDCameraDistance = 0;
let lastTwoDVerticalSpan = 0;
let lastTwoDFitVerticalSpan = 0;
let lastTwoDFitAspect = 1;
const HEAD_CENTER_Y = 1.33;
const DISTANCE_CM_MIN = 1;
const DISTANCE_CM_MAX = 1000;
// Fraction of extra room around the PPS circle when it is fitted to the view.
// ~1.08 makes the circle fill the centered square almost to the border (the
// radius "reaches" the square edges) while leaving a small margin so the ring
// stroke and endpoint markers are not clipped.
const TWO_D_RADIUS_PADDING = 1.08;
const TWO_D_MIN_WORLD_SPAN = 0.5;
const TWO_D_MIN_ZOOM_FACTOR = 0.22;
const TWO_D_MAX_ZOOM_OUT_FACTOR = 3.0;
const TWO_D_ZOOM_BUTTON_FACTOR = 1.18;
const START_MARKER_COLOR = 0x4ecb71;
const END_MARKER_COLOR = 0xe0524d;
const ENDPOINT_2D_LIFT_M = 0.07;
const SOURCE_TRAJECTORY_2D_LIFT_M = 0.045;
const SOURCE_TRAJECTORY_3D_LIFT_M = 0.018;
const SOURCE_TRAJECTORY_OFFSET_M = 0.032;
const pointer = new THREE.Vector2();
const raycaster = new THREE.Raycaster();
const dragPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
const dragPoint = new THREE.Vector3();
const dragHandles = new Map();
let activeDragHandle = "";
let activePan2D = false;
let editingEnabled = true;
let panStartClientX = 0;
let panStartClientY = 0;
const panStartTarget = new THREE.Vector3();

function fitted2DVerticalSpan() {
  const aspect = Math.max(0.1, camera.aspect || 1);
  const radiusSpan = Math.max(currentRadius * 2 * TWO_D_RADIUS_PADDING, TWO_D_MIN_WORLD_SPAN);
  lastTwoDFitAspect = aspect;
  lastTwoDFitVerticalSpan = Math.max(radiusSpan, radiusSpan / aspect);
  return lastTwoDFitVerticalSpan;
}

function min2DVerticalSpan() {
  return Math.max(0.08, currentRadius * TWO_D_MIN_ZOOM_FACTOR);
}

function max2DVerticalSpan() {
  const fittedSpan = lastTwoDFitVerticalSpan > 0 ? lastTwoDFitVerticalSpan : fitted2DVerticalSpan();
  return Math.max(fittedSpan, currentRadius * 2) * TWO_D_MAX_ZOOM_OUT_FACTOR;
}

function set2DVerticalSpan(verticalSpan) {
  const nextSpan = clamp(verticalSpan, min2DVerticalSpan(), max2DVerticalSpan());
  lastTwoDVerticalSpan = nextSpan;
  lastTwoDCameraDistance = nextSpan / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
  camera.updateProjectionMatrix();
  set2DViewCenter(controls.target);
  controls.minDistance = lastTwoDCameraDistance;
  controls.maxDistance = lastTwoDCameraDistance;
}

function fit2DCameraToRadius({ resetCenter = true, resetZoom = true } = {}) {
  const verticalSpan = fitted2DVerticalSpan();
  controls.enabled = false;
  if (resetCenter) {
    controls.target.set(0, 0, 0);
  }
  set2DVerticalSpan(resetZoom || lastTwoDVerticalSpan <= 0 ? verticalSpan : lastTwoDVerticalSpan);
}

function twoDViewSpans() {
  return {
    horizontal: lastTwoDVerticalSpan * lastTwoDFitAspect,
    vertical: lastTwoDVerticalSpan
  };
}

function clamp2DViewCenter(center) {
  const spans = twoDViewSpans();
  const maxX = Math.max(0, Math.abs(spans.horizontal / 2 - currentRadius));
  const maxZ = Math.max(0, Math.abs(spans.vertical / 2 - currentRadius));
  return new THREE.Vector3(
    clamp(center.x, -maxX, maxX),
    0,
    clamp(center.z, -maxZ, maxZ)
  );
}

function set2DViewCenter(center) {
  const nextCenter = clamp2DViewCenter(center);
  controls.target.copy(nextCenter);
  camera.position.set(nextCenter.x, lastTwoDCameraDistance, nextCenter.z);
  camera.lookAt(controls.target);
  sync2DViewState();
}

function sync2DViewState() {
  if (!window.__trajectoryViewerState || currentViewMode !== "2d") return;
  const avatarScreenCenter = currentAvatarScreenCenter();
  const radiusScreenBounds = twoDRadiusScreenBounds(currentRadius);
  window.__trajectoryViewerState.two_d_fit_vertical_span_m = lastTwoDFitVerticalSpan.toFixed(3);
  window.__trajectoryViewerState.two_d_view_vertical_span_m = lastTwoDVerticalSpan.toFixed(3);
  window.__trajectoryViewerState.two_d_camera_distance_m = lastTwoDCameraDistance.toFixed(3);
  window.__trajectoryViewerState.avatar_screen_center_x_fraction = avatarScreenCenter.x.toFixed(3);
  window.__trajectoryViewerState.avatar_screen_center_y_fraction = avatarScreenCenter.y.toFixed(3);
  window.__trajectoryViewerState.radius_screen_center_x_fraction = radiusScreenBounds.centerX.toFixed(3);
  window.__trajectoryViewerState.radius_screen_center_y_fraction = radiusScreenBounds.centerY.toFixed(3);
  window.__trajectoryViewerState.radius_screen_width_px = radiusScreenBounds.widthPx.toFixed(1);
  window.__trajectoryViewerState.radius_screen_height_px = radiusScreenBounds.heightPx.toFixed(1);
  window.__trajectoryViewerState.two_d_view_center_x_m = controls.target.x.toFixed(3);
  window.__trajectoryViewerState.two_d_view_center_z_m = controls.target.z.toFixed(3);
  container.dataset.twoDFitVerticalSpanM = window.__trajectoryViewerState.two_d_fit_vertical_span_m;
  container.dataset.twoDViewVerticalSpanM = window.__trajectoryViewerState.two_d_view_vertical_span_m;
  container.dataset.twoDCameraDistanceM = window.__trajectoryViewerState.two_d_camera_distance_m;
  container.dataset.avatarScreenCenterXFraction = window.__trajectoryViewerState.avatar_screen_center_x_fraction;
  container.dataset.avatarScreenCenterYFraction = window.__trajectoryViewerState.avatar_screen_center_y_fraction;
  container.dataset.radiusScreenCenterXFraction = window.__trajectoryViewerState.radius_screen_center_x_fraction;
  container.dataset.radiusScreenCenterYFraction = window.__trajectoryViewerState.radius_screen_center_y_fraction;
  container.dataset.radiusScreenWidthPx = window.__trajectoryViewerState.radius_screen_width_px;
  container.dataset.radiusScreenHeightPx = window.__trajectoryViewerState.radius_screen_height_px;
  container.dataset.twoDViewCenterXM = window.__trajectoryViewerState.two_d_view_center_x_m;
  container.dataset.twoDViewCenterZM = window.__trajectoryViewerState.two_d_view_center_z_m;
}

function zoom2DView(direction) {
  const factor = direction === "out" ? TWO_D_ZOOM_BUTTON_FACTOR : 1 / TWO_D_ZOOM_BUTTON_FACTOR;
  set2DVerticalSpan(lastTwoDVerticalSpan * factor);
}

function zoom3DView(direction) {
  const factor = direction === "out" ? TWO_D_ZOOM_BUTTON_FACTOR : 1 / TWO_D_ZOOM_BUTTON_FACTOR;
  const offset = camera.position.clone().sub(controls.target);
  const nextDistance = clamp(offset.length() * factor, controls.minDistance, controls.maxDistance);
  camera.position.copy(controls.target).add(offset.setLength(nextDistance));
  controls.update();
}

function zoomTrajectoryCamera(direction) {
  if (currentViewMode === "2d") {
    zoom2DView(direction);
    return;
  }
  zoom3DView(direction);
}

function applyCameraMode(mode, resetCamera = false) {
  if (mode === "2d") {
    camera.up.set(0, 0, -1);
    controls.enableRotate = false;
    controls.enableZoom = false;
    controls.enablePan = false;
    controls.minPolarAngle = 0;
    controls.maxPolarAngle = 0;
    fit2DCameraToRadius({ resetCenter: resetCamera, resetZoom: resetCamera });
  } else {
    camera.up.set(0, 1, 0);
    controls.target.copy(avatarViewCenter);
    controls.enabled = true;
    controls.enableRotate = true;
    controls.enableZoom = true;
    controls.enablePan = false;
    controls.minDistance = 0.6;
    controls.maxDistance = 8.0;
    controls.minPolarAngle = 0.08;
    controls.maxPolarAngle = Math.PI / 2;
    if (resetCamera) {
      camera.position.copy(avatarViewCenter).add(DEFAULT_3D_CAMERA_OFFSET);
    }
  }
  camera.lookAt(controls.target);
  if (mode !== "2d") {
    controls.update();
  }
}

scene.add(new THREE.HemisphereLight(0xf7ead8, 0x332820, 1.8));
const keyLight = new THREE.DirectionalLight(0xffffff, 2.0);
keyLight.position.set(2.5, 4.0, 3.0);
scene.add(keyLight);

const floor = new THREE.GridHelper(6, 24, 0x3a3028, 0x2b241e);
floor.position.y = -HEAD_CENTER_Y - 0.01;
scene.add(floor);

const avatarGroup = new THREE.Group();
scene.add(avatarGroup);

const dynamicGroup = new THREE.Group();
scene.add(dynamicGroup);

function appToThree(point, flattenHeight = false) {
  return new THREE.Vector3(point.x_m, flattenHeight ? 0 : point.z_m, -point.y_m);
}

function threeToTrajectoryControls(position, handle) {
  const appX = position.x;
  const appY = -position.z;
  const distanceCm = clamp(Math.sqrt(appX * appX + appY * appY) * 100, DISTANCE_CM_MIN, DISTANCE_CM_MAX);
  const rotationDeg = normalizeRotationDeg((Math.atan2(appX, appY) * 180) / Math.PI);
  if (handle === "start") {
    return {
      start_distance_cm: distanceCm,
      start_rotation_deg: rotationDeg
    };
  }
  return {
    end_distance_cm: distanceCm,
    end_rotation_deg: rotationDeg
  };
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function normalizeRotationDeg(value) {
  return ((value % 360) + 360) % 360;
}

function setPointerFromEvent(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
}

function intersectDragHandle(event) {
  if (currentViewMode !== "2d" || !editingEnabled) return "";
  const handles = [...dragHandles.values()].filter(Boolean);
  if (!handles.length) return "";
  setPointerFromEvent(event);
  raycaster.setFromCamera(pointer, camera);
  const hit = raycaster.intersectObjects(handles, false)[0];
  return hit?.object?.userData?.dragHandle || "";
}

function intersectTrajectoryPlane(event) {
  setPointerFromEvent(event);
  raycaster.setFromCamera(pointer, camera);
  return raycaster.ray.intersectPlane(dragPlane, dragPoint);
}

function emitTrajectoryControlChange(handle, point) {
  const controls = threeToTrajectoryControls(point, handle);
  window.parent.postMessage(
    {
      type: "pps-trajectory-control-change",
      handle,
      controls
    },
    "*"
  );
}

function addAvatar() {
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0xd8c2aa, roughness: 0.82, metalness: 0.0 });
  const accentMat = new THREE.MeshStandardMaterial({ color: 0x8f7b67, roughness: 0.9, metalness: 0.0 });

  const pelvis = new THREE.Mesh(new THREE.SphereGeometry(0.18, 24, 16), accentMat);
  pelvis.scale.set(0.9, 0.55, 0.65);
  pelvis.position.y = 0.55;
  avatarGroup.add(pelvis);

  const torso = new THREE.Mesh(new THREE.CylinderGeometry(0.19, 0.24, 0.52, 24), bodyMat);
  torso.position.y = 0.92;
  avatarGroup.add(torso);

  const head = new THREE.Mesh(new THREE.SphereGeometry(0.16, 24, 16), bodyMat);
  head.position.y = 1.33;
  avatarGroup.add(head);

  for (const x of [-0.29, 0.29]) {
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.04, 0.58, 16), accentMat);
    arm.position.set(x, 0.88, 0);
    arm.rotation.z = x > 0 ? 0.18 : -0.18;
    avatarGroup.add(arm);
  }

  for (const x of [-0.1, 0.1]) {
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.055, 0.58, 16), accentMat);
    leg.position.set(x, 0.25, 0);
    avatarGroup.add(leg);
  }

  avatarGroup.position.y = -HEAD_CENTER_Y;
  new THREE.Box3().setFromObject(avatarGroup).getCenter(avatarViewCenter);
  avatarViewCenter.x = 0;
  avatarViewCenter.z = 0;
}

function viewportPercentForWorld(point) {
  camera.updateMatrixWorld(true);
  camera.updateProjectionMatrix();
  const projected = point.clone().project(camera);
  return {
    x: (projected.x + 1) / 2,
    y: (1 - projected.y) / 2
  };
}

function currentAvatarScreenCenter() {
  return viewportPercentForWorld(currentViewMode === "2d" ? new THREE.Vector3(0, 0, 0) : avatarViewCenter);
}

function twoDRadiusScreenBounds(radius) {
  const points = [
    new THREE.Vector3(-radius, 0, 0),
    new THREE.Vector3(radius, 0, 0),
    new THREE.Vector3(0, 0, -radius),
    new THREE.Vector3(0, 0, radius)
  ].map(viewportPercentForWorld);
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const widthPx = (maxX - minX) * Math.max(1, container.clientWidth);
  const heightPx = (maxY - minY) * Math.max(1, container.clientHeight);
  return {
    minX,
    maxX,
    minY,
    maxY,
    centerX: (minX + maxX) / 2,
    centerY: (minY + maxY) / 2,
    widthPx,
    heightPx
  };
}

function makeLabel(text, position) {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.font = "28px Arial, Helvetica, sans-serif";
  ctx.fillStyle = "#f2e7d8";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true }));
  sprite.position.copy(position);
  sprite.scale.set(0.42, 0.105, 1);
  return sprite;
}

function addEndpointHandle(handle, position, color, radius, is2D) {
  const markerPosition = position.clone();
  if (is2D) {
    markerPosition.y += ENDPOINT_2D_LIFT_M;
  }
  const visualRadius = Math.max(0.052, radius * 0.052) * (is2D ? 1.2 : 1.0);
  const hitRadius = visualRadius * (is2D ? 1.85 : 1.25);
  const hitMaterial = new THREE.MeshBasicMaterial({
    color,
    transparent: true,
    opacity: is2D ? 0.18 : 0.01,
    depthTest: !is2D,
    depthWrite: false
  });
  const hitTarget = new THREE.Mesh(new THREE.SphereGeometry(hitRadius, 24, 16), hitMaterial);
  hitTarget.position.copy(markerPosition);
  hitTarget.userData.dragHandle = handle;
  hitTarget.renderOrder = 80;
  dynamicGroup.add(hitTarget);

  const marker = new THREE.Mesh(
    new THREE.SphereGeometry(visualRadius, 28, 18),
    new THREE.MeshStandardMaterial({
      color,
      emissive: color,
      emissiveIntensity: is2D ? 0.22 : 0.08,
      roughness: 0.42,
      metalness: 0.0,
      depthTest: !is2D,
      depthWrite: !is2D
    })
  );
  marker.position.copy(markerPosition);
  marker.renderOrder = 100;
  dynamicGroup.add(marker);

  if (is2D) {
    const halo = new THREE.Mesh(
      new THREE.RingGeometry(visualRadius * 1.35, visualRadius * 1.75, 36),
      new THREE.MeshBasicMaterial({
        color,
        transparent: true,
        opacity: 0.58,
        side: THREE.DoubleSide,
        depthTest: false,
        depthWrite: false
      })
    );
    halo.position.copy(markerPosition);
    halo.rotation.x = Math.PI / 2;
    halo.renderOrder = 90;
    dynamicGroup.add(halo);
  }

  dragHandles.set(handle, hitTarget);
  return markerPosition;
}

function addCylinderBetween(start, end, radius, material) {
  const direction = new THREE.Vector3().subVectors(end, start);
  const length = direction.length();
  if (length <= 0.0001) {
    return null;
  }
  const geometry = new THREE.CylinderGeometry(radius, radius, length, 18);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.copy(start).add(end).multiplyScalar(0.5);
  mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.clone().normalize());
  return mesh;
}

function addArrowHead(start, end, material) {
  const direction = new THREE.Vector3().subVectors(end, start);
  if (direction.length() <= 0.0001) {
    return null;
  }
  const cone = new THREE.Mesh(new THREE.ConeGeometry(0.06, 0.16, 24), material);
  cone.position.copy(end);
  cone.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), direction.normalize());
  return cone;
}

function drawSourceTrajectoryInventory(payload, is2D, radius) {
  const groups = groupedSourceTrajectories(payload.source_trajectories || []);
  let sourceCount = 0;
  let sharedGroupCount = 0;
  for (const group of groups) {
    sourceCount += group.sources.length;
    if (group.colors.length > 1) sharedGroupCount += 1;
    const start = appToThree(group.start, is2D);
    const end = appToThree(group.end, is2D);
    const lineCount = Math.max(1, group.colors.length);
    group.colors.forEach((color, index) => {
      const offset = sourceTrajectoryOffset(start, end, index, lineCount, is2D);
      const lineStart = start.clone().add(offset);
      const lineEnd = end.clone().add(offset);
      const material = new THREE.MeshBasicMaterial({
        color: safeSourceColor(color),
        transparent: true,
        opacity: is2D ? 0.92 : 0.78,
        depthTest: !is2D,
        depthWrite: false
      });
      const tube = addCylinderBetween(lineStart, lineEnd, Math.max(0.007, radius * 0.006), material);
      if (tube) {
        tube.renderOrder = is2D ? 45 : 20;
        dynamicGroup.add(tube);
      }
      const arrow = addArrowHead(lineStart, lineEnd, material);
      if (arrow) {
        arrow.scale.setScalar(0.64);
        arrow.renderOrder = is2D ? 46 : 21;
        dynamicGroup.add(arrow);
      }
      addSourceTrajectoryDot(lineStart, color, radius, is2D);
      addSourceTrajectoryDot(lineEnd, color, radius, is2D);
    });
  }
  return { sourceCount, groupCount: groups.length, sharedGroupCount };
}

function groupedSourceTrajectories(rows) {
  const groups = new Map();
  for (const row of rows) {
    if (!validSourceTrajectory(row)) continue;
    const key = sourceTrajectoryKey(row);
    if (!groups.has(key)) {
      groups.set(key, {
        start: row.start,
        end: row.end,
        sources: [],
        colors: []
      });
    }
    const group = groups.get(key);
    group.sources.push(row);
    const color = safeSourceColor(row.color_hex);
    if (!group.colors.includes(color)) {
      group.colors.push(color);
    }
  }
  return [...groups.values()];
}

function validSourceTrajectory(row) {
  return Boolean(row?.start && row?.end && numberLike(row.start.x_m) && numberLike(row.start.y_m) && numberLike(row.end.x_m) && numberLike(row.end.y_m));
}

function sourceTrajectoryKey(row) {
  const parts = [];
  for (const point of [row.start, row.end]) {
    parts.push(
      keyNumber(point.x_m),
      keyNumber(point.y_m),
      keyNumber(point.z_m)
    );
  }
  const snapshot = row.trajectory_snapshot || {};
  parts.push(
    keyNumber(snapshot.movement_duration_s),
    keyNumber(snapshot.start_hold_s),
    keyNumber(snapshot.end_hold_s)
  );
  return parts.join("|");
}

function sourceTrajectoryOffset(start, end, index, count, is2D) {
  const direction = new THREE.Vector3().subVectors(end, start);
  let perpendicular = new THREE.Vector3().crossVectors(new THREE.Vector3(0, 1, 0), direction);
  if (perpendicular.length() <= 0.0001) {
    perpendicular = new THREE.Vector3(1, 0, 0);
  }
  const offsetAmount = (index - (count - 1) / 2) * SOURCE_TRAJECTORY_OFFSET_M;
  const lift = is2D ? SOURCE_TRAJECTORY_2D_LIFT_M : SOURCE_TRAJECTORY_3D_LIFT_M;
  return perpendicular.normalize().multiplyScalar(offsetAmount).add(new THREE.Vector3(0, lift, 0));
}

function addSourceTrajectoryDot(position, color, radius, is2D) {
  const dot = new THREE.Mesh(
    new THREE.SphereGeometry(Math.max(0.018, radius * 0.015), 18, 12),
    new THREE.MeshBasicMaterial({
      color: safeSourceColor(color),
      transparent: true,
      opacity: is2D ? 0.95 : 0.72,
      depthTest: !is2D,
      depthWrite: false
    })
  );
  dot.position.copy(position);
  dot.renderOrder = is2D ? 48 : 22;
  dynamicGroup.add(dot);
}

function safeSourceColor(value) {
  const text = String(value || "").trim();
  return /^#[0-9A-Fa-f]{6}$/.test(text) ? text : "#f08b4f";
}

function numberLike(value) {
  return Number.isFinite(Number(value));
}

function keyNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(4) : "";
}

function drawScene(payload) {
  dragHandles.clear();
  dynamicGroup.clear();

  const mode = payload.preview_mode === "2d" ? "2d" : "3d";
  const is2D = mode === "2d";
  const radius = Math.max(0.1, payload.radius_m || 1.1);
  const modeChanged = currentViewMode !== mode;
  currentViewMode = mode;
  currentRadius = radius;
  // Look-only unless the host marks the payload editable; disables marker drags
  // while leaving pan/zoom/rotate available for inspection.
  editingEnabled = payload.editable !== false;
  if (!is2D) {
    if (activeDragHandle || activePan2D) {
      activeDragHandle = "";
      activePan2D = false;
      controls.enabled = true;
    }
    renderer.domElement.style.cursor = "";
  }
  applyCameraMode(mode, modeChanged);

  if (is2D) {
    const disk = new THREE.Mesh(
      new THREE.CircleGeometry(radius, 96),
      new THREE.MeshBasicMaterial({ color: 0x4fb3d8, transparent: true, opacity: 0.09, side: THREE.DoubleSide })
    );
    disk.rotation.x = -Math.PI / 2;
    dynamicGroup.add(disk);
  } else {
    const sphereMat = new THREE.MeshBasicMaterial({
      color: 0x4fb3d8,
      transparent: true,
      opacity: 0.16,
      wireframe: true
    });
    const sphere = new THREE.Mesh(new THREE.SphereGeometry(radius, 40, 20), sphereMat);
    sphere.position.y = 0;
    dynamicGroup.add(sphere);
  }

  const ring = new THREE.Mesh(
    new THREE.RingGeometry(radius * 0.992, radius, 96),
    new THREE.MeshBasicMaterial({ color: 0x4fb3a6, transparent: true, opacity: 0.62, side: THREE.DoubleSide })
  );
  ring.rotation.x = -Math.PI / 2;
  dynamicGroup.add(ring);

  const start = appToThree(payload.start, is2D);
  const end = appToThree(payload.end, is2D);
  const inventorySummary = drawSourceTrajectoryInventory(payload, is2D, radius);
  const pathMat = new THREE.MeshStandardMaterial({ color: 0xf08b4f, roughness: 0.45, metalness: 0.0 });
  const path = addCylinderBetween(start, end, Math.max(0.012, radius * 0.016), pathMat);
  if (path) dynamicGroup.add(path);
  const arrow = addArrowHead(start, end, pathMat);
  if (arrow) dynamicGroup.add(arrow);

  const startMarkerPosition = addEndpointHandle("start", start, START_MARKER_COLOR, radius, is2D);
  const endMarkerPosition = addEndpointHandle("end", end, END_MARKER_COLOR, radius, is2D);

  const labelLift = is2D ? 0.02 : 0.08;
  dynamicGroup.add(makeLabel("Start", startMarkerPosition.clone().add(new THREE.Vector3(0.08, labelLift, 0))));
  dynamicGroup.add(makeLabel("End", endMarkerPosition.clone().add(new THREE.Vector3(0.08, labelLift, 0))));
  // In 2D the circle now fills the centered square, so keep the orientation
  // labels just inside the ring to stop them clipping at the view edge. In 3D
  // there is room around the sphere, so keep them outside as before.
  const axisLabelRadius = radius * (is2D ? 0.9 : 1.18);
  dynamicGroup.add(makeLabel("+X right", new THREE.Vector3(axisLabelRadius, 0.05, 0)));
  dynamicGroup.add(makeLabel("+Y front", new THREE.Vector3(0, 0.05, -axisLabelRadius)));
  if (!is2D) {
    dynamicGroup.add(makeLabel("+Z up", new THREE.Vector3(0, radius * 1.05, 0)));
  }

  const axisMat = new THREE.LineBasicMaterial({ color: 0x6f6257 });
  const axisPoints = [
    [new THREE.Vector3(-radius, 0, 0), new THREE.Vector3(radius, 0, 0)],
    [new THREE.Vector3(0, 0, radius), new THREE.Vector3(0, 0, -radius)]
  ];
  if (!is2D) {
    axisPoints.push([new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, radius, 0)]);
  }
  for (const pair of axisPoints) {
    dynamicGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pair), axisMat));
  }

  if (hudTitle) {
    hudTitle.textContent = is2D ? "2D Sound Path" : "3D Sound Path";
  }
  const sourceStatus = inventorySummary.sourceCount ? `, ${inventorySummary.sourceCount} source trajector${inventorySummary.sourceCount === 1 ? "y" : "ies"}` : "";
  statusEl.textContent = `${payload.path_length_m.toFixed(2)} m path, ${payload.movement_duration_s.toFixed(2)} s movement${sourceStatus}`;
  const avatarScreenCenter = currentAvatarScreenCenter();
  const radiusScreenBounds = is2D ? twoDRadiusScreenBounds(radius) : null;
  window.__trajectoryViewerState = {
    ready: true,
    view_mode: mode,
    height_visible: !is2D,
    camera_locked_top_down: is2D,
    path_length_m: payload.path_length_m.toFixed(3),
    camera_max_polar_angle: controls.maxPolarAngle.toFixed(6),
    drag_enabled: is2D,
    drag_handles: [...dragHandles.keys()].sort(),
    start_marker_color: "#4ecb71",
    end_marker_color: "#e0524d",
    two_d_radius_centered: is2D,
    two_d_fit_vertical_span_m: is2D ? lastTwoDFitVerticalSpan.toFixed(3) : "",
    two_d_view_vertical_span_m: is2D ? lastTwoDVerticalSpan.toFixed(3) : "",
    two_d_camera_distance_m: is2D ? lastTwoDCameraDistance.toFixed(3) : "",
    two_d_fit_aspect: is2D ? lastTwoDFitAspect.toFixed(3) : "",
    two_d_pan_enabled: is2D,
    two_d_zoom_enabled: is2D,
    avatar_view_center_y_m: avatarViewCenter.y.toFixed(3),
    avatar_screen_center_x_fraction: avatarScreenCenter.x.toFixed(3),
    avatar_screen_center_y_fraction: avatarScreenCenter.y.toFixed(3),
    radius_screen_center_x_fraction: radiusScreenBounds ? radiusScreenBounds.centerX.toFixed(3) : "",
    radius_screen_center_y_fraction: radiusScreenBounds ? radiusScreenBounds.centerY.toFixed(3) : "",
    radius_screen_width_px: radiusScreenBounds ? radiusScreenBounds.widthPx.toFixed(1) : "",
    radius_screen_height_px: radiusScreenBounds ? radiusScreenBounds.heightPx.toFixed(1) : "",
    two_d_view_center_x_m: is2D ? controls.target.x.toFixed(3) : "",
    two_d_view_center_z_m: is2D ? controls.target.z.toFixed(3) : "",
    start_distance_cm: payload.controls?.start_distance_cm ?? "",
    end_distance_cm: payload.controls?.end_distance_cm ?? "",
    start_rotation_deg: payload.controls?.start_rotation_deg ?? "",
    end_rotation_deg: payload.controls?.end_rotation_deg ?? ""
  };
  window.__trajectoryViewerState.source_trajectory_count = inventorySummary.sourceCount;
  window.__trajectoryViewerState.source_trajectory_group_count = inventorySummary.groupCount;
  window.__trajectoryViewerState.shared_tone_trajectory_group_count = inventorySummary.sharedGroupCount;
  container.dataset.viewerReady = "true";
  container.dataset.viewMode = mode;
  container.dataset.heightVisible = String(!is2D);
  container.dataset.cameraLockedTopDown = String(is2D);
  container.dataset.pathLengthM = window.__trajectoryViewerState.path_length_m;
  container.dataset.cameraMaxPolarAngle = window.__trajectoryViewerState.camera_max_polar_angle;
  container.dataset.dragEnabled = String(is2D);
  container.dataset.dragHandles = window.__trajectoryViewerState.drag_handles.join(",");
  container.dataset.startMarkerColor = window.__trajectoryViewerState.start_marker_color;
  container.dataset.endMarkerColor = window.__trajectoryViewerState.end_marker_color;
  container.dataset.twoDRadiusCentered = String(window.__trajectoryViewerState.two_d_radius_centered);
  container.dataset.twoDFitVerticalSpanM = window.__trajectoryViewerState.two_d_fit_vertical_span_m;
  container.dataset.twoDViewVerticalSpanM = window.__trajectoryViewerState.two_d_view_vertical_span_m;
  container.dataset.twoDCameraDistanceM = window.__trajectoryViewerState.two_d_camera_distance_m;
  container.dataset.twoDFitAspect = window.__trajectoryViewerState.two_d_fit_aspect;
  container.dataset.twoDPanEnabled = String(window.__trajectoryViewerState.two_d_pan_enabled);
  container.dataset.twoDZoomEnabled = String(window.__trajectoryViewerState.two_d_zoom_enabled);
  container.dataset.avatarViewCenterYM = window.__trajectoryViewerState.avatar_view_center_y_m;
  container.dataset.avatarScreenCenterXFraction = window.__trajectoryViewerState.avatar_screen_center_x_fraction;
  container.dataset.avatarScreenCenterYFraction = window.__trajectoryViewerState.avatar_screen_center_y_fraction;
  container.dataset.radiusScreenCenterXFraction = window.__trajectoryViewerState.radius_screen_center_x_fraction;
  container.dataset.radiusScreenCenterYFraction = window.__trajectoryViewerState.radius_screen_center_y_fraction;
  container.dataset.radiusScreenWidthPx = window.__trajectoryViewerState.radius_screen_width_px;
  container.dataset.radiusScreenHeightPx = window.__trajectoryViewerState.radius_screen_height_px;
  container.dataset.twoDViewCenterXM = window.__trajectoryViewerState.two_d_view_center_x_m;
  container.dataset.twoDViewCenterZM = window.__trajectoryViewerState.two_d_view_center_z_m;
  container.dataset.startDistanceCm = String(window.__trajectoryViewerState.start_distance_cm);
  container.dataset.endDistanceCm = String(window.__trajectoryViewerState.end_distance_cm);
  container.dataset.startRotationDeg = String(window.__trajectoryViewerState.start_rotation_deg);
  container.dataset.endRotationDeg = String(window.__trajectoryViewerState.end_rotation_deg);
  container.dataset.sourceTrajectoryCount = String(window.__trajectoryViewerState.source_trajectory_count);
  container.dataset.sourceTrajectoryGroupCount = String(window.__trajectoryViewerState.source_trajectory_group_count);
  container.dataset.sharedToneTrajectoryGroupCount = String(window.__trajectoryViewerState.shared_tone_trajectory_group_count);
}

function handlePointerDown(event) {
  const handle = intersectDragHandle(event);
  if (!handle && currentViewMode !== "2d") return;
  event.preventDefault();
  controls.enabled = false;
  renderer.domElement.style.cursor = "grabbing";
  renderer.domElement.setPointerCapture(event.pointerId);
  if (handle) {
    activeDragHandle = handle;
    const point = intersectTrajectoryPlane(event);
    if (point) emitTrajectoryControlChange(activeDragHandle, point);
    return;
  }
  activePan2D = true;
  panStartClientX = event.clientX;
  panStartClientY = event.clientY;
  panStartTarget.copy(controls.target);
}

function handlePointerMove(event) {
  if (activePan2D) {
    event.preventDefault();
    const spans = twoDViewSpans();
    const rect = renderer.domElement.getBoundingClientRect();
    const dx = ((event.clientX - panStartClientX) / Math.max(1, rect.width)) * spans.horizontal;
    const dy = ((event.clientY - panStartClientY) / Math.max(1, rect.height)) * spans.vertical;
    set2DViewCenter(new THREE.Vector3(panStartTarget.x - dx, 0, panStartTarget.z - dy));
    return;
  }
  if (activeDragHandle) {
    event.preventDefault();
    const point = intersectTrajectoryPlane(event);
    if (point) emitTrajectoryControlChange(activeDragHandle, point);
    return;
  }
  renderer.domElement.style.cursor = currentViewMode === "2d" || intersectDragHandle(event) ? "grab" : "";
}

function handlePointerUp(event) {
  if (!activeDragHandle && !activePan2D) return;
  activeDragHandle = "";
  activePan2D = false;
  controls.enabled = currentViewMode !== "2d";
  renderer.domElement.style.cursor = "";
  if (renderer.domElement.hasPointerCapture(event.pointerId)) {
    renderer.domElement.releasePointerCapture(event.pointerId);
  }
}

function resize() {
  const width = Math.max(1, container.clientWidth);
  const height = Math.max(1, container.clientHeight);
  if (width === lastViewportWidth && height === lastViewportHeight) return;
  lastViewportWidth = width;
  lastViewportHeight = height;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  if (currentViewMode === "2d") {
    fit2DCameraToRadius({ resetCenter: false, resetZoom: false });
  } else {
    camera.updateProjectionMatrix();
  }
}

function animate() {
  resize();
  if (currentViewMode !== "2d") {
    controls.update();
  }
  renderer.render(scene, camera);
  window.requestAnimationFrame(animate);
}

addAvatar();
drawScene({
  preview_mode: "2d",
  radius_m: 1.1,
  path_length_m: 1.0,
  movement_duration_s: 3.0,
  start: { x_m: 0, y_m: 1.1, z_m: 0 },
  end: { x_m: 0, y_m: 0.1, z_m: 0 }
});
resize();
animate();

renderer.domElement.addEventListener("pointerdown", handlePointerDown);
renderer.domElement.addEventListener("pointermove", handlePointerMove);
renderer.domElement.addEventListener("pointerup", handlePointerUp);
renderer.domElement.addEventListener("pointercancel", handlePointerUp);

window.updateTrajectory = function updateTrajectory(payload) {
  drawScene(payload);
};

window.resetTrajectoryCamera = function resetTrajectoryCamera() {
  applyCameraMode(currentViewMode, true);
};

window.fitTrajectoryRadius = function fitTrajectoryRadius() {
  if (currentViewMode === "2d") {
    fit2DCameraToRadius({ resetCenter: true, resetZoom: true });
    return;
  }
  applyCameraMode(currentViewMode, true);
};

window.zoomTrajectoryCamera = zoomTrajectoryCamera;

container.dataset.viewerReady = "true";
