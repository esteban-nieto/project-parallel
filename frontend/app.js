const els = {
  apiBase: document.getElementById("apiBase"),
  useGateway: document.getElementById("useGateway"),
  authBase: document.getElementById("authBase"),
  historiasBase: document.getElementById("historiasBase"),
  audioBase: document.getElementById("audioBase"),
  iaBase: document.getElementById("iaBase"),
  saveBase: document.getElementById("saveBase"),
  runHealth: document.getElementById("runHealth"),
  authUser: document.getElementById("authUser"),
  authPass: document.getElementById("authPass"),
  authEmail: document.getElementById("authEmail"),
  btnRegister: document.getElementById("btnRegister"),
  btnLogin: document.getElementById("btnLogin"),
  btnLogout: document.getElementById("btnLogout"),
  tokenDisplay: document.getElementById("tokenDisplay"),
  authResponse: document.getElementById("authResponse"),
  histPaciente: document.getElementById("histPaciente"),
  histEdad: document.getElementById("histEdad"),
  histMotivo: document.getElementById("histMotivo"),
  histDiagnostico: document.getElementById("histDiagnostico"),
  histTratamiento: document.getElementById("histTratamiento"),
  histUbicacion: document.getElementById("histUbicacion"),
  histSignos: document.getElementById("histSignos"),
  histObservaciones: document.getElementById("histObservaciones"),
  histAudioId: document.getElementById("histAudioId"),
  btnCrearHistoria: document.getElementById("btnCrearHistoria"),
  btnListarHistorias: document.getElementById("btnListarHistorias"),
  histResponse: document.getElementById("histResponse"),
  histList: document.getElementById("histList"),
  iaTexto: document.getElementById("iaTexto"),
  iaCache: document.getElementById("iaCache"),
  btnAnalizarIa: document.getElementById("btnAnalizarIa"),
  btnLimpiarCacheIa: document.getElementById("btnLimpiarCacheIa"),
  iaResponse: document.getElementById("iaResponse"),
  audioFile: document.getElementById("audioFile"),
  audioId: document.getElementById("audioId"),
  audioStatus: document.getElementById("audioStatus"),
  btnGrabar: document.getElementById("btnGrabar"),
  btnSubirAudio: document.getElementById("btnSubirAudio"),
  btnEstadoAudio: document.getElementById("btnEstadoAudio"),
  btnDescargarAudio: document.getElementById("btnDescargarAudio"),
  audioResponse: document.getElementById("audioResponse"),
  workspace: document.getElementById("workspace"),
  healthAuth: document.getElementById("health-auth"),
  healthHistorias: document.getElementById("health-historias"),
  healthAudio: document.getElementById("health-audio"),
  healthIa: document.getElementById("health-ia"),
  healthGateway: document.getElementById("health-gateway"),
};

const state = {
  token: localStorage.getItem("pp_token") || "",
  apiBase: localStorage.getItem("pp_api_base") || "http://localhost",
  useGateway: localStorage.getItem("pp_use_gateway") === "true",
  authBase: localStorage.getItem("pp_auth_base") || "http://localhost:8001",
  historiasBase: localStorage.getItem("pp_historias_base") || "http://localhost:8002",
  audioBase: localStorage.getItem("pp_audio_base") || "http://localhost:8003",
  iaBase: localStorage.getItem("pp_ia_base") || "http://localhost:8004",
  lastAudioId: "",
  recorder: null,
  audioChunks: [],
  recordingStream: null,
};

const scrollButtons = document.querySelectorAll("[data-scroll]");
scrollButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const selector = btn.getAttribute("data-scroll");
    document.querySelector(selector)?.scrollIntoView({ behavior: "smooth" });
  });
});

function setToken(token) {
  state.token = token || "";
  localStorage.setItem("pp_token", state.token);
  els.tokenDisplay.textContent = state.token ? state.token : "No hay token";
  if (els.workspace) {
    if (state.token) {
      els.workspace.classList.remove("locked");
    } else {
      els.workspace.classList.add("locked");
    }
  }
}

function setApiBase(base) {
  state.apiBase = base.replace(/\/+$/, "");
  localStorage.setItem("pp_api_base", state.apiBase);
  els.healthGateway.textContent = state.apiBase;
}

function setServiceBases() {
  const useGateway = !!els.useGateway?.checked;
  state.useGateway = useGateway;
  localStorage.setItem("pp_use_gateway", String(useGateway));

  state.authBase = (els.authBase.value || state.authBase).replace(/\/+$/, "");
  state.historiasBase = (els.historiasBase.value || state.historiasBase).replace(/\/+$/, "");
  state.audioBase = (els.audioBase.value || state.audioBase).replace(/\/+$/, "");
  state.iaBase = (els.iaBase.value || state.iaBase).replace(/\/+$/, "");

  localStorage.setItem("pp_auth_base", state.authBase);
  localStorage.setItem("pp_historias_base", state.historiasBase);
  localStorage.setItem("pp_audio_base", state.audioBase);
  localStorage.setItem("pp_ia_base", state.iaBase);
}

function formatJson(data) {
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

function resolveBase(service) {
  if (state.useGateway) {
    return state.apiBase;
  }
  switch (service) {
    case "auth":
      return state.authBase;
    case "historias":
      return state.historiasBase;
    case "audio":
      return state.audioBase;
    case "ia":
      return state.iaBase;
    default:
      return state.apiBase;
  }
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 2000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    return response;
  } finally {
    clearTimeout(timeout);
  }
}

async function apiFetch(path, options = {}) {
  return apiFetchService("gateway", path, options);
}

async function apiFetchService(service, path, options = {}) {
  const headers = options.headers ? { ...options.headers } : {};
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  const response = await fetch(`${resolveBase(service)}${path}`, {
    ...options,
    headers,
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    throw new Error(formatJson(payload));
  }
  return payload;
}

function writeResponse(el, data) {
  el.textContent = formatJson(data);
}

function setAudioStatus(text, isRecording = false) {
  if (!els.audioStatus) return;
  els.audioStatus.textContent = text;
  if (isRecording) {
    els.btnGrabar.classList.add("recording");
  } else {
    els.btnGrabar.classList.remove("recording");
  }
}

async function analizarTextoIA(texto, usarCache = true) {
  els.iaTexto.value = texto;
  const payload = { texto, usar_cache: usarCache };
  const data = await apiFetchService("ia", "/api/v1/ia/analizar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  writeResponse(els.iaResponse, data);
  const campos = data.campos_extraidos || {};
  if (campos.paciente) els.histPaciente.value = campos.paciente;
  if (campos.edad !== undefined) els.histEdad.value = campos.edad;
  if (campos.motivo) els.histMotivo.value = campos.motivo;
  if (campos.diagnostico) els.histDiagnostico.value = campos.diagnostico;
  if (campos.tratamiento) els.histTratamiento.value = campos.tratamiento;
  if (data.texto_corregido) {
    els.histObservaciones.value = data.texto_corregido;
  }
  return data;
}

async function subirAudioArchivo(file) {
  const formData = new FormData();
  formData.append("archivo", file);
  const data = await apiFetchService("audio", "/api/v1/audio/subir", {
    method: "POST",
    body: formData,
  });
  writeResponse(els.audioResponse, data);
  if (data.id_audio) {
    state.lastAudioId = data.id_audio;
    els.audioId.value = data.id_audio;
    els.histAudioId.value = data.id_audio;
  }
  return data;
}

async function esperarTranscripcion(idAudio) {
  setAudioStatus("Transcribiendo…");
  const maxIntentos = 30;
  for (let i = 0; i < maxIntentos; i += 1) {
    const data = await apiFetch(`/api/v1/audio/${idAudio}/estado`);
    if (data.estado === "completado" && data.transcripcion) {
      writeResponse(els.audioResponse, data);
      await analizarTextoIA(data.transcripcion, false);
      return;
    }
    if (data.estado === "fallido") {
      throw new Error(data.error || "Transcripción fallida.");
    }
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  throw new Error("Tiempo de espera agotado para transcripción.");
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("El navegador no soporta grabación de audio.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mimeType = MediaRecorder.isTypeSupported("audio/webm")
    ? "audio/webm"
    : MediaRecorder.isTypeSupported("audio/ogg")
    ? "audio/ogg"
    : "";

  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  state.audioChunks = [];
  state.recorder = recorder;
  state.recordingStream = stream;

  recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size > 0) {
      state.audioChunks.push(event.data);
    }
  });

  recorder.addEventListener("stop", async () => {
    const blob = new Blob(state.audioChunks, { type: recorder.mimeType || "audio/webm" });
    state.audioChunks = [];
    stream.getTracks().forEach((track) => track.stop());
    state.recordingStream = null;

    try {
      setAudioStatus("Subiendo audio…");
      const extension = blob.type.includes("ogg") ? "ogg" : "webm";
      const file = new File([blob], `grabacion.${extension}`, { type: blob.type });
      const result = await subirAudioArchivo(file);
      if (result?.id_audio) {
        await esperarTranscripcion(result.id_audio);
      }
    } catch (err) {
      writeResponse(els.audioResponse, err.message);
      setAudioStatus("Error en grabación");
    } finally {
      setAudioStatus("Sin grabación");
    }
  });

  recorder.start();
  setAudioStatus("Grabando…", true);
}

function stopRecording() {
  if (state.recorder && state.recorder.state !== "inactive") {
    state.recorder.stop();
  }
}

async function runHealth() {
  const services = [
    { name: "auth", el: els.healthAuth },
    { name: "historias", el: els.healthHistorias },
    { name: "audio", el: els.healthAudio },
    { name: "ia", el: els.healthIa },
  ];

  if (state.useGateway) {
    try {
      await fetchWithTimeout(`${state.apiBase}/health`, {}, 1500);
    } catch {
      state.useGateway = false;
      localStorage.setItem("pp_use_gateway", "false");
      if (els.useGateway) {
        els.useGateway.checked = false;
      }
    }
  }

  for (const service of services) {
    service.el.classList.remove("ok", "bad");
    try {
      if (state.useGateway) {
        await apiFetchService("gateway", `/health/${service.name}`);
      } else {
        await apiFetchService(service.name, "/salud");
      }
      service.el.classList.add("ok");
    } catch {
      service.el.classList.add("bad");
    }
  }
}

els.saveBase.addEventListener("click", () => {
  setApiBase(els.apiBase.value || "http://localhost");
  setServiceBases();
  runHealth();
});

els.runHealth.addEventListener("click", runHealth);

els.btnRegister.addEventListener("click", async () => {
  const payload = {
    usuario: els.authUser.value.trim(),
    contrasena: els.authPass.value.trim(),
    email: els.authEmail.value.trim() || null,
  };
  try {
    const data = await apiFetchService("auth", "/api/v1/auth/registro", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    writeResponse(els.authResponse, data);
  } catch (err) {
    writeResponse(els.authResponse, err.message);
  }
});

els.btnLogin.addEventListener("click", async () => {
  const payload = {
    usuario: els.authUser.value.trim(),
    contrasena: els.authPass.value.trim(),
  };
  try {
    const data = await apiFetchService("auth", "/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setToken(data.token_acceso);
    writeResponse(els.authResponse, data);
  } catch (err) {
    writeResponse(els.authResponse, err.message);
  }
});

els.btnLogout.addEventListener("click", async () => {
  try {
    const data = await apiFetchService("auth", "/api/v1/auth/cerrar-sesion", {
      method: "POST",
    });
    writeResponse(els.authResponse, data);
  } catch (err) {
    writeResponse(els.authResponse, err.message);
  } finally {
    setToken("");
  }
});

els.btnCrearHistoria.addEventListener("click", async () => {
  const payload = {
    paciente: els.histPaciente.value.trim(),
    edad: Number(els.histEdad.value),
    motivo: els.histMotivo.value.trim(),
    diagnostico: els.histDiagnostico.value.trim(),
    tratamiento: els.histTratamiento.value.trim(),
    ubicacion: els.histUbicacion.value.trim(),
    signos_vitales: els.histSignos.value.trim(),
    observaciones: els.histObservaciones.value.trim() || null,
    id_audio: els.histAudioId.value.trim() || null,
  };
  try {
    const data = await apiFetchService("historias", "/api/v1/historias", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    writeResponse(els.histResponse, data);
    await listarHistorias();
  } catch (err) {
    writeResponse(els.histResponse, err.message);
  }
});

async function listarHistorias() {
  try {
    const data = await apiFetchService("historias", "/api/v1/historias?pagina=1&por_pagina=10");
    writeResponse(els.histResponse, data);
    renderHistorias(data.historias || []);
  } catch (err) {
    writeResponse(els.histResponse, err.message);
  }
}

els.btnListarHistorias.addEventListener("click", listarHistorias);

function renderHistorias(items) {
  els.histList.innerHTML = "";
  if (!items.length) {
    els.histList.innerHTML = "<div class='list-item'>Sin resultados.</div>";
    return;
  }
  items.forEach((historia) => {
    const div = document.createElement("div");
    div.className = "list-item";
    div.innerHTML = `
      <h4>${historia.consecutivo} · ${historia.paciente}</h4>
      <p>${historia.motivo || "Sin motivo"} · Estado: ${historia.estado}</p>
      <p>${historia.fecha_creacion}</p>
    `;
    els.histList.appendChild(div);
  });
}

els.btnAnalizarIa.addEventListener("click", async () => {
  try {
    await analizarTextoIA(els.iaTexto.value.trim(), els.iaCache.checked);
  } catch (err) {
    writeResponse(els.iaResponse, err.message);
  }
});

els.btnLimpiarCacheIa.addEventListener("click", async () => {
  try {
    const data = await apiFetchService("ia", "/api/v1/ia/cache/limpiar", { method: "DELETE" });
    writeResponse(els.iaResponse, data);
  } catch (err) {
    writeResponse(els.iaResponse, err.message);
  }
});

els.btnSubirAudio.addEventListener("click", async () => {
  const file = els.audioFile.files[0];
  if (!file) {
    writeResponse(els.audioResponse, "Selecciona un archivo de audio.");
    return;
  }
  const formData = new FormData();
  formData.append("archivo", file);
  try {
    const data = await apiFetch("/api/v1/audio/subir", {
      method: "POST",
      body: formData,
    });
    writeResponse(els.audioResponse, data);
    if (data.id_audio) {
      state.lastAudioId = data.id_audio;
      els.audioId.value = data.id_audio;
      els.histAudioId.value = data.id_audio;
    }
  } catch (err) {
    writeResponse(els.audioResponse, err.message);
  }
});

els.btnGrabar?.addEventListener("mousedown", async () => {
  try {
    await startRecording();
  } catch (err) {
    writeResponse(els.audioResponse, err.message);
    setAudioStatus("Error de micrófono");
  }
});

els.btnGrabar?.addEventListener("mouseup", stopRecording);
els.btnGrabar?.addEventListener("mouseleave", stopRecording);
els.btnGrabar?.addEventListener("touchstart", async (event) => {
  event.preventDefault();
  try {
    await startRecording();
  } catch (err) {
    writeResponse(els.audioResponse, err.message);
    setAudioStatus("Error de micrófono");
  }
});
els.btnGrabar?.addEventListener("touchend", stopRecording);

els.btnEstadoAudio.addEventListener("click", async () => {
  const id = els.audioId.value.trim() || state.lastAudioId;
  if (!id) {
    writeResponse(els.audioResponse, "Ingresa un ID de audio.");
    return;
  }
  try {
    const data = await apiFetchService("audio", `/api/v1/audio/${id}/estado`);
    writeResponse(els.audioResponse, data);
  } catch (err) {
    writeResponse(els.audioResponse, err.message);
  }
});

els.btnDescargarAudio.addEventListener("click", () => {
  const id = els.audioId.value.trim() || state.lastAudioId;
  if (!id) {
    writeResponse(els.audioResponse, "Ingresa un ID de audio.");
    return;
  }
  descargarAudio(id).catch((err) => writeResponse(els.audioResponse, err.message));
});

async function descargarAudio(id) {
  const response = await fetch(`${resolveBase("audio")}/api/v1/audio/${id}/descargar`, {
    headers: {
      Authorization: `Bearer ${state.token}`,
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "No se pudo descargar el audio.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `audio-${id}.bin`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  writeResponse(els.audioResponse, "Descarga iniciada.");
}

function bootstrap() {
  els.apiBase.value = state.apiBase;
  els.useGateway.checked = state.useGateway;
  els.authBase.value = state.authBase;
  els.historiasBase.value = state.historiasBase;
  els.audioBase.value = state.audioBase;
  els.iaBase.value = state.iaBase;
  setApiBase(state.apiBase);
  setServiceBases();
  setToken(state.token);
  setAudioStatus("Sin grabación");
  runHealth();
}

bootstrap();
