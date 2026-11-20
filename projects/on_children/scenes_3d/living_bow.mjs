/**
 * living_bow.mjs — "The Living Bow & Golden Arrows": sculpted organic cedar &
 * alabaster recurve bow inlaid with champagne gold, gracefully flexing as
 * slender living arrows glide along a luminous golden arc toward the infinite.
 * Supports `params.phase`: "draw" (bow flexing & nocking) or "flight" (arrows soaring).
 * Z-up right-handed coordinate convention.
 */

function clearScene(scene) {
  while (scene.children.length > 0) {
    scene.remove(scene.children[0]);
  }
}

function addPastelSkyDome(THREE, scene, isFlight) {
  const skyGeo = new THREE.SphereGeometry(95, 48, 32);
  const skyMat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      uBottom: { value: new THREE.Color(isFlight ? "#F7E5D0" : "#F6E7D7") },
      uMid: { value: new THREE.Color(isFlight ? "#EAC2B4" : "#E8C9BE") },
      uTop: { value: new THREE.Color(isFlight ? "#BDCEE0" : "#C6D7D8") },
      uSunDir: { value: new THREE.Vector3(0.76, 0.52, 0.34).normalize() },
      uSunCol: { value: new THREE.Color("#FFECC2") },
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
        float h = clamp(d.z * 0.52 + 0.46, 0.0, 1.0);
        vec3 col = mix(uBottom, uMid, smoothstep(0.0, 0.45, h));
        col = mix(col, uTop, smoothstep(0.45, 0.95, h));
        float sunDot = max(dot(d, uSunDir), 0.0);
        col += uSunCol * pow(sunDot, 10.0) * 0.38;
        col += uSunCol * pow(sunDot, 70.0) * 0.45;
        gl_FragColor = vec4(col, 1.0);
      }
    `,
  });
  scene.add(new THREE.Mesh(skyGeo, skyMat));
}

function easeInOutCubic(u) {
  const t = Math.max(0, Math.min(1, u));
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function buildArrow(THREE, shaftMat, goldMat, fletchMat) {
  const g = new THREE.Group();
  // Arrow points along +X axis
  const shaft = new THREE.Mesh(
    new THREE.CylinderGeometry(0.022, 0.024, 2.35, 14),
    shaftMat,
  );
  shaft.rotation.z = -Math.PI / 2;
  g.add(shaft);

  // Sculpted champagne-gold arrowhead
  const tip = new THREE.Mesh(new THREE.ConeGeometry(0.068, 0.28, 6), goldMat);
  tip.rotation.z = -Math.PI / 2;
  tip.position.x = 1.28;
  g.add(tip);

  // Delicate collar ring
  const collar = new THREE.Mesh(
    new THREE.TorusGeometry(0.032, 0.009, 10, 20),
    goldMat,
  );
  collar.rotation.y = Math.PI / 2;
  collar.position.x = 1.12;
  g.add(collar);

  // 3 graceful pastel botanical feather fletchings at the tail
  const fShape = new THREE.Shape();
  fShape.moveTo(0, 0);
  fShape.bezierCurveTo(0.10, 0.08, 0.32, 0.14, 0.46, 0.02);
  fShape.lineTo(0.40, 0);
  fShape.closePath();
  const fGeo = new THREE.ShapeGeometry(fShape, 8);
  for (let k = 0; k < 3; k++) {
    const f = new THREE.Mesh(fGeo, fletchMat);
    f.position.set(-1.16, 0, 0);
    f.rotation.x = (k / 3) * Math.PI * 2;
    g.add(f);
  }
  return g;
}

function bowCurvePoints(THREE, bend) {
  // Recurve graceful living bow standing in XZ plane, facing +X
  // bend in [0..1] pulls tips smoothly back (-X)
  const pull = bend * 0.42;
  const pts = [];
  const N = 28;
  for (let i = 0; i <= N; i++) {
    const s = (i / N) * 2 - 1; // -1 (bottom tip) .. +1 (top tip)
    const a = Math.abs(s);
    const z = s * (2.05 - bend * 0.12);
    // Sculpted double-curve recurve profile
    const belly = 0.48 * Math.cos(s * Math.PI * 0.5);
    const recurveTip = 0.22 * Math.pow(a, 3.0) * Math.sin(a * Math.PI * 0.9);
    const flexBack = pull * Math.pow(a, 1.85);
    const x = belly + recurveTip - flexBack;
    pts.push(new THREE.Vector3(x, 0, z));
  }
  return pts;
}

export function buildScene({ THREE, scene, spec }) {
  clearScene(scene);
  const phase = String(spec?.params?.phase || "draw");
  const isFlight = phase === "flight";

  scene.background = new THREE.Color("#F4E3D6");
  scene.fog = new THREE.FogExp2("#EED9CC", 0.018);
  scene.environmentIntensity = 0.65;

  addPastelSkyDome(THREE, scene, isFlight);

  scene.add(new THREE.HemisphereLight("#FFF6E6", "#CEB19E", 1.18));
  const key = new THREE.DirectionalLight("#FFEAC4", 2.05);
  key.position.set(7.5, 6.0, 5.5);
  scene.add(key);

  const rim = new THREE.DirectionalLight("#CFC4E6", 0.85);
  rim.position.set(-6.0, -5.0, 3.5);
  scene.add(rim);

  // Sculpted warm cedar-alabaster wood & brushed champagne gold materials
  const bowWoodMat = new THREE.MeshPhysicalMaterial({
    color: "#B47B5E",
    roughness: 0.30,
    metalness: 0.08,
    clearcoat: 0.72,
    clearcoatRoughness: 0.22,
  });
  const goldMat = new THREE.MeshStandardMaterial({
    color: "#D8AE62",
    emissive: "#B9883D",
    emissiveIntensity: 0.22,
    roughness: 0.22,
    metalness: 0.78,
  });
  const ivoryMat = new THREE.MeshPhysicalMaterial({
    color: "#FFF7EC",
    emissive: "#F2D6B0",
    emissiveIntensity: 0.14,
    roughness: 0.24,
    metalness: 0.12,
    clearcoat: 0.8,
  });
  const fletchMat = new THREE.MeshStandardMaterial({
    color: "#E4A799",
    emissive: "#D79282",
    emissiveIntensity: 0.14,
    roughness: 0.45,
    side: THREE.DoubleSide,
  });

  // Living Bow group (rebuilt smoothly per frame via CatmullRom + TubeGeometry)
  const bowGroup = new THREE.Group();
  bowGroup.position.set(-1.35, 0.0, 0.12);
  scene.add(bowGroup);

  let bowLimbMesh = null;
  let bowGoldInlay = null;
  let stringMesh = null;

  // Center sculpted gold grip handle
  const grip = new THREE.Mesh(
    new THREE.CylinderGeometry(0.072, 0.072, 0.44, 20),
    goldMat,
  );
  grip.rotation.x = Math.PI / 2;
  grip.position.set(0.48, 0, 0);
  bowGroup.add(grip);

  // Subtle luminous sacred-geometry halo behind the bow
  const halo = new THREE.Mesh(
    new THREE.TorusGeometry(1.72, 0.012, 12, 80),
    new THREE.MeshStandardMaterial({
      color: "#E8CCA0",
      emissive: "#DFB87A",
      emissiveIntensity: 0.4,
      roughness: 0.3,
      metalness: 0.6,
    }),
  );
  halo.rotation.x = Math.PI / 2;
  halo.position.set(-1.1, 0.4, 0.12);
  scene.add(halo);

  const stringMat = new THREE.MeshStandardMaterial({
    color: "#F3DCB0",
    emissive: "#E8C680",
    emissiveIntensity: 0.45,
    roughness: 0.25,
    metalness: 0.6,
  });

  // Primary hero living arrow + 2 accompanying luminous arrows in graceful formation
  const heroArrow = buildArrow(THREE, ivoryMat, goldMat, fletchMat);
  scene.add(heroArrow);

  const companionArrows = [
    {
      mesh: buildArrow(THREE, ivoryMat, goldMat, fletchMat),
      yOff: -0.58,
      zOff: 0.42,
      delay: 0.12,
      scale: 0.82,
    },
    {
      mesh: buildArrow(THREE, ivoryMat, goldMat, fletchMat),
      yOff: 0.55,
      zOff: -0.32,
      delay: 0.22,
      scale: 0.78,
    },
  ];
  for (const ca of companionArrows) {
    ca.mesh.scale.setScalar(ca.scale);
    ca.mesh.visible = isFlight;
    scene.add(ca.mesh);
  }

  // Luminous golden trajectory arc showing "the path of the infinite"
  const arcPts = [];
  for (let i = 0; i <= 40; i++) {
    const u = i / 40;
    const x = -0.8 + u * 11.5;
    const z = 0.12 + Math.sin(u * Math.PI * 0.72) * 1.45;
    arcPts.push(new THREE.Vector3(x, 0, z));
  }
  const flightCurve = new THREE.CatmullRomCurve3(arcPts);
  const pathGlow = new THREE.Mesh(
    new THREE.TubeGeometry(flightCurve, 72, 0.012, 8, false),
    new THREE.MeshStandardMaterial({
      color: "#F3D49C",
      emissive: "#E9C074",
      emissiveIntensity: 0.55,
      transparent: true,
      opacity: isFlight ? 0.65 : 0.32,
    }),
  );
  scene.add(pathGlow);

  // Soft sunrise destination mark on the infinite horizon
  const markOrb = new THREE.Mesh(
    new THREE.SphereGeometry(0.65, 28, 22),
    new THREE.MeshBasicMaterial({ color: "#FFF7E4" }),
  );
  markOrb.position.set(12.5, 1.5, 1.75);
  scene.add(markOrb);

  // Floating golden pollen & pastel light motes
  const motes = [];
  const moteGeo = new THREE.SphereGeometry(0.032, 8, 8);
  const moteMat = new THREE.MeshStandardMaterial({
    color: "#FFF7E2",
    emissive: "#ECC57B",
    emissiveIntensity: 0.95,
    roughness: 0.2,
  });
  let seed = 192307;
  const rand = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
  for (let i = 0; i < 48; i++) {
    const m = new THREE.Mesh(moteGeo, moteMat);
    const u = rand();
    const pt = flightCurve.getPoint(u);
    const bp = [
      pt.x + (rand() - 0.5) * 3.2,
      (rand() - 0.5) * 3.8,
      pt.z + (rand() - 0.5) * 2.4,
    ];
    m.scale.setScalar(0.5 + rand() * 0.9);
    scene.add(m);
    motes.push({ mesh: m, bp, phase: rand() * Math.PI * 2 });
  }

  function updateBowGeometry(bend) {
    if (bowLimbMesh) {
      bowLimbMesh.geometry.dispose();
      bowGroup.remove(bowLimbMesh);
    }
    if (bowGoldInlay) {
      bowGoldInlay.geometry.dispose();
      bowGroup.remove(bowGoldInlay);
    }
    if (stringMesh) {
      stringMesh.geometry.dispose();
      bowGroup.remove(stringMesh);
    }
    const pts = bowCurvePoints(THREE, bend);
    const curve = new THREE.CatmullRomCurve3(pts);
    bowLimbMesh = new THREE.Mesh(
      new THREE.TubeGeometry(curve, 52, 0.056, 14, false),
      bowWoodMat,
    );
    bowGroup.add(bowLimbMesh);

    const inlayPts = pts.map((p) => new THREE.Vector3(p.x + 0.052, p.y, p.z));
    bowGoldInlay = new THREE.Mesh(
      new THREE.TubeGeometry(new THREE.CatmullRomCurve3(inlayPts), 44, 0.015, 8, false),
      goldMat,
    );
    bowGroup.add(bowGoldInlay);

    const botTip = pts[0];
    const topTip = pts[pts.length - 1];
    const nockX = -0.18 - bend * 1.15;
    const strCurve = new THREE.CatmullRomCurve3([
      botTip,
      new THREE.Vector3(nockX, 0, 0),
      topTip,
    ]);
    stringMesh = new THREE.Mesh(
      new THREE.TubeGeometry(strCurve, 24, 0.011, 8, false),
      stringMat,
    );
    bowGroup.add(stringMesh);
    return nockX;
  }

  return (tNorm) => {
    const t = tNorm;
    let bend;
    if (!isFlight) {
      // Phase "draw": gentle majestic draw from 0.15 -> 0.88
      bend = 0.15 + 0.73 * easeInOutCubic(t);
    } else {
      // Phase "flight": deep graceful bend (0.95) releasing smoothly at t=0.22
      if (t < 0.22) {
        bend = 0.86 + 0.12 * easeInOutCubic(t / 0.22);
      } else {
        const rel = easeInOutCubic(Math.min(1, (t - 0.22) / 0.28));
        bend = 0.98 * (1 - rel) + 0.14 * rel;
      }
    }

    const nockX = updateBowGeometry(bend);
    halo.rotation.z = t * 0.35;

    if (!isFlight) {
      // Hero arrow rests poised on the string, drawing back gracefully with the bow
      heroArrow.position.set(bowGroup.position.x + nockX + 1.12, 0, bowGroup.position.z);
      heroArrow.rotation.set(0, -0.06 - bend * 0.06, 0);
    } else {
      if (t < 0.22) {
        heroArrow.position.set(bowGroup.position.x + nockX + 1.12, 0, bowGroup.position.z);
        heroArrow.rotation.set(0, -0.12, 0);
      } else {
        const u = easeInOutCubic(Math.min(1, (t - 0.22) / 0.78)) * 0.82;
        const pt = flightCurve.getPoint(u);
        const tan = flightCurve.getTangent(u);
        heroArrow.position.copy(pt);
        heroArrow.rotation.set(0, -Math.atan2(tan.z, tan.x), 0);
      }
      for (const ca of companionArrows) {
        const localU = Math.max(0, (t - 0.22 - ca.delay) / 0.72);
        if (localU <= 0.001) {
          ca.mesh.visible = false;
        } else {
          ca.mesh.visible = true;
          const u = easeInOutCubic(Math.min(1, localU)) * 0.75;
          const pt = flightCurve.getPoint(u);
          const tan = flightCurve.getTangent(u);
          ca.mesh.position.set(pt.x, pt.y + ca.yOff, pt.z + ca.zOff);
          ca.mesh.rotation.set(0, -Math.atan2(tan.z, tan.x), 0);
        }
      }
    }

    for (const m of motes) {
      const ph = m.phase + t * Math.PI * 2.0;
      m.mesh.position.set(
        m.bp[0] + t * (isFlight ? 1.4 : 0.45) + Math.sin(ph) * 0.15,
        m.bp[1] + Math.cos(ph * 0.8) * 0.16,
        m.bp[2] + Math.sin(ph * 1.1) * 0.14 + t * 0.25,
      );
    }

    return {};
  };
}
