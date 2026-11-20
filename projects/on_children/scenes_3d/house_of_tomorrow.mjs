/**
 * house_of_tomorrow.mjs — "The House of Tomorrow": dreamlike alabaster &
 * rose-quartz classical colonnade arches rising from pastel lavender-cream
 * clouds toward a radiant dawn sun, with pearl light orbs drifting through.
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
      uBottom: { value: new THREE.Color("#F7E6D8") },
      uMid: { value: new THREE.Color("#E5CED8") },
      uTop: { value: new THREE.Color("#C7C0DF") },
      uSunDir: { value: new THREE.Vector3(0.0, 0.96, 0.24).normalize() },
      uSunCol: { value: new THREE.Color("#FFEBC2") },
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
        float h = clamp(d.z * 0.55 + 0.42, 0.0, 1.0);
        vec3 col = mix(uBottom, uMid, smoothstep(0.0, 0.45, h));
        col = mix(col, uTop, smoothstep(0.45, 0.95, h));
        float sunDot = max(dot(d, uSunDir), 0.0);
        col += uSunCol * pow(sunDot, 10.0) * 0.36;
        col += uSunCol * pow(sunDot, 72.0) * 0.45;
        gl_FragColor = vec4(col, 1.0);
      }
    `,
  });
  scene.add(new THREE.Mesh(skyGeo, skyMat));
}

function createPastelArch(THREE, width, height, depth, pillarMat, trimMat) {
  const g = new THREE.Group();
  const radius = width * 0.5;
  const colH = height - radius;
  const colR = depth * 0.44;

  // Left & right cylindrical columns with soft plinths & capitals
  for (const side of [-1, 1]) {
    const col = new THREE.Mesh(
      new THREE.CylinderGeometry(colR * 0.92, colR, colH, 24),
      pillarMat,
    );
    col.rotation.x = Math.PI / 2;
    col.position.set(side * radius, 0, colH * 0.5);
    col.castShadow = true;
    col.receiveShadow = true;
    g.add(col);

    const plinth = new THREE.Mesh(
      new THREE.BoxGeometry(colR * 2.5, colR * 2.5, 0.16),
      trimMat,
    );
    plinth.position.set(side * radius, 0, 0.08);
    g.add(plinth);

    const cap = new THREE.Mesh(
      new THREE.BoxGeometry(colR * 2.4, colR * 2.4, 0.12),
      trimMat,
    );
    cap.position.set(side * radius, 0, colH);
    g.add(cap);
  }

  // Semicircular arch ring (in XZ plane, standing upright)
  const archPts = [];
  const segs = 32;
  for (let i = 0; i <= segs; i++) {
    const ang = (i / segs) * Math.PI;
    archPts.push(
      new THREE.Vector3(
        Math.cos(ang) * radius,
        0,
        colH + Math.sin(ang) * radius,
      ),
    );
  }
  const archCurve = new THREE.CatmullRomCurve3(archPts);
  const archTube = new THREE.Mesh(
    new THREE.TubeGeometry(archCurve, 40, colR * 0.9, 16, false),
    pillarMat,
  );
  archTube.castShadow = true;
  g.add(archTube);

  // Delicate brushed champagne-gold inner arch filigree
  const goldPts = [];
  for (let i = 0; i <= segs; i++) {
    const ang = (i / segs) * Math.PI;
    goldPts.push(
      new THREE.Vector3(
        Math.cos(ang) * (radius - colR * 0.96),
        0,
        colH + Math.sin(ang) * (radius - colR * 0.96),
      ),
    );
  }
  const goldCurve = new THREE.CatmullRomCurve3(goldPts);
  const goldTrim = new THREE.Mesh(
    new THREE.TubeGeometry(goldCurve, 36, 0.028, 10, false),
    trimMat,
  );
  g.add(goldTrim);

  return g;
}

export function buildScene({ THREE, scene }) {
  clearScene(scene);
  scene.background = new THREE.Color("#F3E3DC");
  scene.fog = new THREE.FogExp2("#EAD8D8", 0.022);
  scene.environmentIntensity = 0.56;

  addPastelSkyDome(THREE, scene);

  const hemi = new THREE.HemisphereLight("#FFF6EB", "#C9B9CE", 1.15);
  scene.add(hemi);

  const dawnSun = new THREE.DirectionalLight("#FFE8C2", 2.0);
  dawnSun.position.set(2.5, 16.0, 5.5);
  dawnSun.castShadow = true;
  scene.add(dawnSun);

  const lavFill = new THREE.DirectionalLight("#CFC4E6", 0.68);
  lavFill.position.set(-5.0, -4.0, 4.0);
  scene.add(lavFill);

  // Soft pastel marble & brushed champagne gold materials
  const alabasterMat = new THREE.MeshStandardMaterial({
    color: "#F6EAE0",
    roughness: 0.42,
    metalness: 0.04,
  });
  const roseQuartzMat = new THREE.MeshStandardMaterial({
    color: "#E8CBC6",
    roughness: 0.45,
    metalness: 0.05,
  });
  const goldMat = new THREE.MeshStandardMaterial({
    color: "#D8B068",
    emissive: "#B98B42",
    emissiveIntensity: 0.16,
    roughness: 0.24,
    metalness: 0.76,
  });

  // Reflective pale ivory walkway floor leading toward tomorrow
  const floor = new THREE.Mesh(
    new THREE.BoxGeometry(4.2, 22.0, 0.22),
    new THREE.MeshPhysicalMaterial({
      color: "#F8F1EA",
      roughness: 0.22,
      metalness: 0.05,
      clearcoat: 0.65,
      clearcoatRoughness: 0.18,
    }),
  );
  floor.position.set(0, 6.2, -1.15);
  floor.receiveShadow = true;
  scene.add(floor);

  // Subtle gold inlay line running down the center path
  const pathLine = new THREE.Mesh(
    new THREE.BoxGeometry(0.045, 20.5, 0.02),
    goldMat,
  );
  pathLine.position.set(0, 6.2, -1.03);
  scene.add(pathLine);

  // Perspective procession of 5 serene pastel arches opening into the sunrise
  const archGroup = new THREE.Group();
  for (let i = 0; i < 5; i++) {
    const y = -0.5 + i * 2.95;
    const mat = i % 2 === 0 ? alabasterMat : roseQuartzMat;
    const arch = createPastelArch(THREE, 3.15, 3.25, 0.34, mat, goldMat);
    arch.position.set(0, y, -1.04);
    archGroup.add(arch);
  }
  scene.add(archGroup);

  // Dreamy pastel cloud pillows cushioning both sides of the colonnade
  const cloudMatA = new THREE.MeshStandardMaterial({
    color: "#F9F1EC",
    roughness: 0.95,
    metalness: 0.0,
  });
  const cloudMatB = new THREE.MeshStandardMaterial({
    color: "#EAE2F2",
    roughness: 0.95,
    metalness: 0.0,
  });
  const clouds = [];
  let seed = 192305;
  const rand = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
  for (let i = 0; i < 28; i++) {
    const side = i % 2 === 0 ? -1 : 1;
    const puff = new THREE.Mesh(
      new THREE.SphereGeometry(1.0, 22, 16),
      i % 3 === 0 ? cloudMatB : cloudMatA,
    );
    const bx = side * (2.6 + rand() * 4.5);
    const by = -1.5 + rand() * 18.0;
    const bz = -1.55 + rand() * 0.95;
    puff.position.set(bx, by, bz);
    puff.scale.set(1.5 + rand() * 1.9, 1.4 + rand() * 1.8, 0.55 + rand() * 0.45);
    scene.add(puff);
    clouds.push({ mesh: puff, bx, by, bz, phase: rand() * Math.PI * 2 });
  }

  // Luminous radiant sunrise orb framed cleanly through the distant arches
  const sunrise = new THREE.Mesh(
    new THREE.SphereGeometry(1.35, 32, 24),
    new THREE.MeshBasicMaterial({ color: "#FFF6E0" }),
  );
  sunrise.position.set(0, 17.5, 1.35);
  scene.add(sunrise);

  // Translucent iridescent pearl light-souls drifting gently forward through the arches
  const orbs = [];
  const orbGeo = new THREE.SphereGeometry(0.11, 20, 16);
  const orbColors = ["#FFF7E4", "#F7DCE2", "#DDEAE6", "#E5DDF5"];
  for (let i = 0; i < 24; i++) {
    const col = orbColors[i % orbColors.length];
    const mat = new THREE.MeshStandardMaterial({
      color: col,
      emissive: col,
      emissiveIntensity: 0.65,
      roughness: 0.15,
      metalness: 0.1,
    });
    const m = new THREE.Mesh(orbGeo, mat);
    const bp = [
      (rand() - 0.5) * 2.1,
      -0.8 + rand() * 12.0,
      -0.35 + rand() * 2.35,
    ];
    const sc = 0.45 + rand() * 0.85;
    m.scale.setScalar(sc);
    scene.add(m);
    orbs.push({
      mesh: m,
      bp,
      phase: rand() * Math.PI * 2,
      speedY: 1.4 + rand() * 1.8,
      bobAmp: 0.12 + rand() * 0.18,
    });
  }

  return (tNorm) => {
    const t = tNorm;
    sunrise.position.z = 1.15 + t * 0.55;
    for (const c of clouds) {
      c.mesh.position.x = c.bx + Math.sin(c.phase + t * Math.PI * 1.4) * 0.25;
      c.mesh.position.z = c.bz + Math.cos(c.phase + t * Math.PI * 1.2) * 0.08;
    }
    for (const o of orbs) {
      const ph = o.phase + t * Math.PI * 2.2;
      o.mesh.position.set(
        o.bp[0] + Math.sin(ph) * 0.22,
        o.bp[1] + t * o.speedY,
        o.bp[2] + Math.cos(ph * 0.9) * o.bobAmp + t * 0.25,
      );
    }
    return {};
  };
}
