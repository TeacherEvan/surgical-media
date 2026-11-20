/**
 * blossom_stream.mjs — "Life's Longing": sunlit pastel rippling stream,
 * drifting curved almond-blossom petals, and rising golden morning motes.
 * Z-up right-handed coordinate convention.
 */

function clearScene(scene) {
  while (scene.children.length > 0) {
    scene.remove(scene.children[0]);
  }
}

function addPastelSkyDome(THREE, scene, { bottomHex, midHex, topHex, sunDir, sunHex }) {
  const skyGeo = new THREE.SphereGeometry(95, 48, 32);
  const skyMat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      uBottom: { value: new THREE.Color(bottomHex) },
      uMid: { value: new THREE.Color(midHex) },
      uTop: { value: new THREE.Color(topHex) },
      uSunDir: { value: new THREE.Vector3(...sunDir).normalize() },
      uSunCol: { value: new THREE.Color(sunHex) },
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
        vec3 col = mix(uBottom, uMid, smoothstep(0.0, 0.48, h));
        col = mix(col, uTop, smoothstep(0.45, 0.96, h));
        float sunDot = max(dot(d, uSunDir), 0.0);
        col += uSunCol * pow(sunDot, 14.0) * 0.32;
        col += uSunCol * pow(sunDot, 90.0) * 0.40;
        gl_FragColor = vec4(col, 1.0);
      }
    `,
  });
  scene.add(new THREE.Mesh(skyGeo, skyMat));
}

function makePetalGeometry(THREE) {
  const shape = new THREE.Shape();
  shape.moveTo(0, 0);
  shape.bezierCurveTo(0.11, 0.06, 0.16, 0.24, 0.03, 0.34);
  shape.bezierCurveTo(0.0, 0.36, -0.02, 0.35, -0.04, 0.33);
  shape.bezierCurveTo(-0.16, 0.23, -0.11, 0.06, 0, 0);
  const geom = new THREE.ShapeGeometry(shape, 10);
  const pos = geom.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i);
    const y = pos.getY(i);
    // Gentle botanical cupping
    const cup = (x * x * 1.9 + (y - 0.17) * (y - 0.17) * 0.55) * 0.45;
    pos.setZ(i, cup);
  }
  geom.computeVertexNormals();
  return geom;
}

export function buildScene({ THREE, scene }) {
  clearScene(scene);
  scene.background = new THREE.Color("#F8EFE4");
  scene.fog = new THREE.FogExp2("#F1DDD1", 0.019);
  scene.environmentIntensity = 0.52;

  addPastelSkyDome(THREE, scene, {
    bottomHex: "#F9EBD9",
    midHex: "#EDCBB9",
    topHex: "#C7DDD6",
    sunDir: [0.32, 0.88, 0.34],
    sunHex: "#FFF0CE",
  });

  // Soft morning natural daylight
  const hemi = new THREE.HemisphereLight("#FFF6E6", "#C8AFA3", 1.15);
  scene.add(hemi);

  const sun = new THREE.DirectionalLight("#FFEBC8", 1.95);
  sun.position.set(5.5, 10.0, 7.5);
  sun.castShadow = true;
  scene.add(sun);

  const fill = new THREE.DirectionalLight("#D8CEE8", 0.65);
  fill.position.set(-6.0, -4.0, 3.5);
  scene.add(fill);

  // Sculpted sunlit pastel water plane with organic ripples
  const waterGeo = new THREE.PlaneGeometry(38, 38, 72, 72);
  const baseZ = new Float32Array(waterGeo.attributes.position.count);
  for (let i = 0; i < baseZ.length; i++) {
    baseZ[i] = waterGeo.attributes.position.getZ(i);
  }
  const waterMat = new THREE.MeshPhysicalMaterial({
    color: "#B9D4CF",
    roughness: 0.14,
    metalness: 0.12,
    clearcoat: 0.95,
    clearcoatRoughness: 0.12,
    reflectivity: 0.78,
  });
  const water = new THREE.Mesh(waterGeo, waterMat);
  water.position.z = -1.25;
  water.receiveShadow = true;
  scene.add(water);

  // Soft pastel riverbanks / sculptural porcelain hills framing the horizon
  const hillMatSage = new THREE.MeshStandardMaterial({
    color: "#B4CCB8",
    roughness: 0.85,
    metalness: 0.0,
  });
  const hillMatBlush = new THREE.MeshStandardMaterial({
    color: "#DFC1B4",
    roughness: 0.88,
    metalness: 0.0,
  });
  const hills = [
    { pos: [-7.2, 10.2, -1.55], scale: [6.5, 4.2, 2.3], mat: hillMatSage },
    { pos: [6.8, 11.8, -1.65], scale: [7.2, 4.6, 2.5], mat: hillMatBlush },
    { pos: [0.5, 17.5, -1.85], scale: [12.5, 5.2, 3.2], mat: hillMatSage },
  ];
  for (const h of hills) {
    const m = new THREE.Mesh(new THREE.SphereGeometry(1.0, 32, 20), h.mat);
    m.position.set(...h.pos);
    m.scale.set(...h.scale);
    scene.add(m);
  }

  // Graceful sculpted botanical branch arching into the upper left corner
  const branchPts = [
    new THREE.Vector3(-4.2, 1.4, 2.35),
    new THREE.Vector3(-2.6, 0.9, 1.78),
    new THREE.Vector3(-1.2, 0.6, 1.48),
    new THREE.Vector3(0.25, 0.4, 1.56),
    new THREE.Vector3(1.15, 0.35, 1.82),
  ];
  const branchCurve = new THREE.CatmullRomCurve3(branchPts);
  const branchMat = new THREE.MeshStandardMaterial({
    color: "#856757",
    roughness: 0.75,
    metalness: 0.05,
  });
  const branch = new THREE.Mesh(
    new THREE.TubeGeometry(branchCurve, 44, 0.045, 10, false),
    branchMat,
  );
  scene.add(branch);

  // Small sage leaves & blossom buds resting along the branch
  const petalGeo = makePetalGeometry(THREE);
  const blossomColors = ["#F0B6A8", "#EAB3C2", "#FDECE2", "#EBC8A6"];
  const leafMat = new THREE.MeshStandardMaterial({
    color: "#84A387",
    roughness: 0.62,
    side: THREE.DoubleSide,
  });

  for (let i = 0; i < 14; i++) {
    const u = 0.16 + (i / 13) * 0.8;
    const pt = branchCurve.getPoint(u);
    if (i % 2 === 0) {
      // Blossom rosette of 5 cupped petals
      const flower = new THREE.Group();
      flower.position.copy(pt);
      flower.position.z += 0.04;
      const pMat = new THREE.MeshStandardMaterial({
        color: blossomColors[i % blossomColors.length],
        emissive: "#F9E2D8",
        emissiveIntensity: 0.12,
        roughness: 0.52,
        side: THREE.DoubleSide,
      });
      for (let k = 0; k < 5; k++) {
        const pm = new THREE.Mesh(petalGeo, pMat);
        pm.rotation.z = (k / 5) * Math.PI * 2;
        pm.rotation.x = 0.45;
        pm.scale.setScalar(0.58);
        flower.add(pm);
      }
      const stamen = new THREE.Mesh(
        new THREE.SphereGeometry(0.036, 10, 10),
        new THREE.MeshStandardMaterial({
          color: "#E4BE72",
          emissive: "#E4BE72",
          emissiveIntensity: 0.35,
          roughness: 0.4,
        }),
      );
      flower.add(stamen);
      flower.rotation.set(0.35, (i % 3 - 1) * 0.4, i * 0.7);
      scene.add(flower);
    } else {
      const leaf = new THREE.Mesh(petalGeo, leafMat);
      leaf.position.copy(pt);
      leaf.scale.set(0.7, 1.15, 0.7);
      leaf.rotation.set(0.6, (i % 4 - 1.5) * 0.5, i * 1.1);
      scene.add(leaf);
    }
  }

  // Drifting pastel blossom petals rising and dancing gently across the stream
  const petals = [];
  const petalMats = blossomColors.map(
    (hex) =>
      new THREE.MeshStandardMaterial({
        color: hex,
        emissive: hex,
        emissiveIntensity: 0.1,
        roughness: 0.48,
        side: THREE.DoubleSide,
      }),
  );

  // Deterministic pseudo-random helper
  let seed = 192301;
  const rand = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };

  for (let i = 0; i < 68; i++) {
    const mesh = new THREE.Mesh(petalGeo, petalMats[i % petalMats.length]);
    const basePos = [
      (rand() - 0.5) * 7.8,
      (rand() - 0.35) * 6.5,
      -0.75 + rand() * 3.1,
    ];
    const scale = 0.52 + rand() * 0.52;
    mesh.scale.setScalar(scale);
    scene.add(mesh);
    petals.push({
      mesh,
      basePos,
      phase: rand() * Math.PI * 2,
      driftX: 0.65 + rand() * 1.15,
      liftZ: 0.25 + rand() * 0.55,
      swayAmp: 0.14 + rand() * 0.22,
      rotSpeed: [0.6 + rand() * 1.2, 0.5 + rand() * 1.1, 0.4 + rand() * 0.9],
    });
  }

  // Luminous sunlit dust motes drifting softly upward
  const motes = [];
  const moteGeo = new THREE.SphereGeometry(0.028, 8, 8);
  const moteMat = new THREE.MeshStandardMaterial({
    color: "#FFF6DE",
    emissive: "#F3D39B",
    emissiveIntensity: 0.95,
    roughness: 0.2,
  });
  for (let i = 0; i < 42; i++) {
    const m = new THREE.Mesh(moteGeo, moteMat);
    const bp = [
      (rand() - 0.5) * 7.2,
      (rand() - 0.3) * 5.8,
      -0.6 + rand() * 2.9,
    ];
    m.scale.setScalar(0.55 + rand() * 0.95);
    scene.add(m);
    motes.push({ mesh: m, bp, phase: rand() * Math.PI * 2, lift: 0.35 + rand() * 0.6 });
  }

  // Soft golden sun disc glowing peacefully above the horizon
  const sunDisc = new THREE.Mesh(
    new THREE.SphereGeometry(1.55, 32, 24),
    new THREE.MeshBasicMaterial({ color: "#FFF6E3" }),
  );
  sunDisc.position.set(5.2, 22.0, 5.2);
  scene.add(sunDisc);

  return (tNorm) => {
    const t = tNorm;
    const pos = waterGeo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      const wave =
        0.07 * Math.sin(x * 0.85 + t * Math.PI * 2.4) +
        0.05 * Math.cos(y * 0.72 - t * Math.PI * 2.0) +
        0.03 * Math.sin((x + y) * 1.25 + t * Math.PI * 3.0);
      pos.setZ(i, baseZ[i] + wave);
    }
    pos.needsUpdate = true;
    waterGeo.computeVertexNormals();

    for (const p of petals) {
      const ph = p.phase + t * Math.PI * 2.0;
      p.mesh.position.set(
        p.basePos[0] + t * p.driftX + Math.sin(ph) * p.swayAmp,
        p.basePos[1] + Math.cos(ph * 0.8) * p.swayAmp * 0.8,
        p.basePos[2] + t * p.liftZ + Math.sin(ph * 1.2) * 0.14,
      );
      p.mesh.rotation.set(
        p.phase + t * p.rotSpeed[0] * 2.4,
        p.phase * 0.7 + t * p.rotSpeed[1] * 2.0,
        p.phase * 1.3 + t * p.rotSpeed[2] * 1.8,
      );
    }

    for (const m of motes) {
      const ph = m.phase + t * Math.PI * 2.0;
      m.mesh.position.set(
        m.bp[0] + Math.sin(ph) * 0.22,
        m.bp[1] + Math.cos(ph * 0.7) * 0.18,
        m.bp[2] + t * m.lift,
      );
    }
    return {};
  };
}
