/**
 * river_of_tomorrow.mjs — "Life Goes Not Backward": flowing sculptural pastel
 * silk-water ribbons, floating sage/porcelain leaves, and sunlit ripples
 * moving serenely forward toward a warm morning horizon.
 * Z-up right-handed coordinate convention.
 */

function clearScene(scene) {
  while (scene.children.length > 0) {
    scene.remove(scene.children[0]);
  }
}

function addPastelSkyDome(THREE, scene) {
  const skyGeo = new THREE.SphereGeometry(95, 48, 32);
  const skyMat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      uBottom: { value: new THREE.Color("#F7ECDC") },
      uMid: { value: new THREE.Color("#D4E4D8") },
      uTop: { value: new THREE.Color("#C2D8D9") },
      uSunDir: { value: new THREE.Vector3(-0.22, 0.92, 0.30).normalize() },
      uSunCol: { value: new THREE.Color("#FFEDC8") },
    },
    vertexShader: `
      varying vec3 vWorldPos;
      void main() {
        vec4 wp = modelMatrix * vec4(position, 1.0);
        vWorldPos = wp.xyz;
        gl_Position = projectionMatrix * viewMatrix * wp;
      }
    `,
    fragmentShader: `
      uniform vec3 uBottom;
      uniform vec3 uMid;
      uniform vec3 uTop;
      uniform vec3 uSunDir;
      uniform vec3 uSunCol;
      varying vec3 vWorldPos;
      void main() {
        vec3 d = normalize(vWorldPos);
        float h = clamp(d.z * 0.55 + 0.45, 0.0, 1.0);
        vec3 col = mix(uBottom, uMid, smoothstep(0.0, 0.45, h));
        col = mix(col, uTop, smoothstep(0.45, 0.95, h));
        float sunDot = max(dot(d, uSunDir), 0.0);
        col += uSunCol * pow(sunDot, 12.0) * 0.30;
        col += uSunCol * pow(sunDot, 80.0) * 0.38;
        gl_FragColor = vec4(col, 1.0);
      }
    `,
  });
  scene.add(new THREE.Mesh(skyGeo, skyMat));
}

function makeLeafBoatGeometry(THREE) {
  const shape = new THREE.Shape();
  shape.moveTo(0, -0.34);
  shape.bezierCurveTo(0.16, -0.18, 0.18, 0.16, 0, 0.38);
  shape.bezierCurveTo(-0.18, 0.16, -0.16, -0.18, 0, -0.34);
  const geom = new THREE.ShapeGeometry(shape, 12);
  const pos = geom.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const y = pos.getY(i);
    pos.setZ(i, x * x * 1.8 + y * y * 0.38);
  }
  geom.computeVertexNormals();
  return geom;
}

export function buildScene({ THREE, scene }) {
  clearScene(scene);
  scene.background = new THREE.Color("#E2ECE5");
  scene.fog = new THREE.FogExp2("#DCE8E0", 0.021);
  scene.environmentIntensity = 0.52;

  addPastelSkyDome(THREE, scene);

  scene.add(new THREE.HemisphereLight("#FFF8EB", "#B6CCBD", 1.15));
  const sun = new THREE.DirectionalLight("#FFECC8", 1.85);
  sun.position.set(-4.0, 11.0, 6.5);
  scene.add(sun);

  const warmFill = new THREE.DirectionalLight("#EDC9B8", 0.68);
  warmFill.position.set(5.5, -3.5, 4.0);
  scene.add(warmFill);

  // Translucent misty sage-celadon river mirror
  const mirror = new THREE.Mesh(
    new THREE.PlaneGeometry(42, 42),
    new THREE.MeshPhysicalMaterial({
      color: "#C4DCD6",
      roughness: 0.18,
      metalness: 0.08,
      clearcoat: 0.85,
      clearcoatRoughness: 0.16,
    }),
  );
  mirror.position.z = -0.85;
  scene.add(mirror);

  // Sculpted flowing pastel silk-ribbons streaming steadily forward (+Y)
  const ribbonColors = ["#82AC94", "#E2A68E", "#B2A2C9", "#D4AE66", "#8FB7B0"];
  const ribbons = [];
  for (let r = 0; r < 7; r++) {
    const laneX = (r - 3) * 0.92;
    const pts = [];
    for (let k = 0; k <= 36; k++) {
      const u = k / 36;
      const y = -4.5 + u * 21.0;
      const x = laneX + Math.sin(u * Math.PI * 3.0 + r * 0.9) * 0.55;
      const z = -0.32 + Math.cos(u * Math.PI * 2.5 + r * 1.1) * 0.22 + (r % 2) * 0.16;
      pts.push(new THREE.Vector3(x, y, z));
    }
    const curve = new THREE.CatmullRomCurve3(pts);
    const tubeGeo = new THREE.TubeGeometry(curve, 96, 0.055 + (r % 3) * 0.018, 12, false);
    const mat = new THREE.MeshStandardMaterial({
      color: ribbonColors[r % ribbonColors.length],
      emissive: ribbonColors[r % ribbonColors.length],
      emissiveIntensity: 0.14,
      roughness: 0.34,
      metalness: 0.12,
    });
    const mesh = new THREE.Mesh(tubeGeo, mat);
    scene.add(mesh);
    ribbons.push({ mesh, curve, laneX, r });
  }

  // Smooth porcelain river pebbles along the banks
  const stoneColors = ["#F4ECE4", "#DFDDD6", "#EEDDD4", "#D5E0D7"];
  const stoneGeo = new THREE.SphereGeometry(1.0, 24, 18);
  let seed = 192306;
  const rand = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
  for (let i = 0; i < 18; i++) {
    const side = i % 2 === 0 ? -1 : 1;
    const mat = new THREE.MeshStandardMaterial({
      color: stoneColors[i % stoneColors.length],
      roughness: 0.58,
      metalness: 0.02,
    });
    const st = new THREE.Mesh(stoneGeo, mat);
    st.position.set(
      side * (3.2 + rand() * 3.8),
      -1.5 + rand() * 14.0,
      -0.88 + rand() * 0.25,
    );
    st.scale.set(0.65 + rand() * 1.1, 0.55 + rand() * 1.0, 0.28 + rand() * 0.32);
    st.rotation.z = rand() * Math.PI;
    scene.add(st);
  }

  // Graceful botanical leaf-boats gliding serenely forward along the currents
  const leafGeo = makeLeafBoatGeometry(THREE);
  const leafColors = ["#8FA992", "#C7A78B", "#B3C5B0", "#E4BEAA", "#E4C993"];
  const boats = [];
  for (let i = 0; i < 18; i++) {
    const r = ribbons[i % ribbons.length];
    const mat = new THREE.MeshStandardMaterial({
      color: leafColors[i % leafColors.length],
      emissive: leafColors[i % leafColors.length],
      emissiveIntensity: 0.08,
      roughness: 0.45,
      side: THREE.DoubleSide,
    });
    const m = new THREE.Mesh(leafGeo, mat);
    m.scale.setScalar(0.85 + rand() * 0.65);
    scene.add(m);
    boats.push({
      mesh: m,
      curve: r.curve,
      u0: 0.05 + (i / 18) * 0.58,
      speed: 0.24 + rand() * 0.14,
      zOff: 0.09 + rand() * 0.16,
      phase: rand() * Math.PI * 2,
    });
  }

  // Rising golden light droplets following the current forward
  const motes = [];
  const moteGeo = new THREE.SphereGeometry(0.032, 8, 8);
  const moteMat = new THREE.MeshStandardMaterial({
    color: "#FFF7E2",
    emissive: "#EAC885",
    emissiveIntensity: 0.9,
    roughness: 0.2,
  });
  for (let i = 0; i < 36; i++) {
    const m = new THREE.Mesh(moteGeo, moteMat);
    const bp = [(rand() - 0.5) * 6.5, -1.0 + rand() * 11.0, -0.2 + rand() * 2.4];
    scene.add(m);
    motes.push({ mesh: m, bp, phase: rand() * Math.PI * 2 });
  }

  return (tNorm) => {
    const t = tNorm;
    for (const r of ribbons) {
      // Gentle breathing undulation along the river
      r.mesh.position.z = Math.sin(t * Math.PI * 2.0 + r.r * 0.7) * 0.06;
    }
    for (const b of boats) {
      const u = Math.min(0.98, b.u0 + t * b.speed);
      const pt = b.curve.getPoint(u);
      const tan = b.curve.getTangent(u);
      b.mesh.position.set(pt.x, pt.y, pt.z + b.zOff + Math.sin(b.phase + t * 6.0) * 0.04);
      const yaw = Math.atan2(tan.y, tan.x) - Math.PI * 0.5;
      b.mesh.rotation.set(
        Math.sin(b.phase + t * 5.0) * 0.09,
        Math.cos(b.phase + t * 4.0) * 0.09,
        yaw,
      );
    }
    for (const m of motes) {
      const ph = m.phase + t * Math.PI * 2.0;
      m.mesh.position.set(
        m.bp[0] + Math.sin(ph) * 0.2,
        m.bp[1] + t * 2.6,
        m.bp[2] + t * 0.45 + Math.cos(ph) * 0.1,
      );
    }
    return {};
  };
}
