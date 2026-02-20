const els = {
  statusBar: document.getElementById("statusBar"),
  authUser: document.getElementById("authUser"),
  authPass: document.getElementById("authPass"),
  btnLogin: document.getElementById("btnLogin"),
  btnLogout: document.getElementById("btnLogout"),
  authResponse: document.getElementById("authResponse"),
  forms: document.getElementById("forms"),
  headers: document.querySelectorAll(".accordion__header"),
  recordButtons: document.querySelectorAll(".record"),
};

const state = {
  token: localStorage.getItem("pp_simple_token") || "",
  api: {
    auth: "http://localhost:8001",
    audio: "http://localhost:8003",
    ia: "http://localhost:8004",
  },
  recorder: null,
  chunks: [],
  stream: null,
  activeSection: null,
};

function setStatus(text) {
  els.statusBar.textContent = text;
}

function setToken(token) {
  state.token = token || "";
  localStorage.setItem("pp_simple_token", state.token);
  if (state.token) {
    setStatus("Sesión activa");
    els.forms.classList.remove("locked");
  } else {
    setStatus("Sin sesión");
    els.forms.classList.add("locked");
  }
}

async function apiFetch(base, path, options = {}) {
  const headers = options.headers ? { ...options.headers } : {};
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  const response = await fetch(`${base}${path}`, { ...options, headers });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    if (payload && typeof payload === "object" && payload.mensaje) {
      throw new Error(payload.mensaje);
    }
    throw new Error(typeof payload === "string" ? payload : JSON.stringify(payload));
  }
  if (payload && typeof payload === "object" && payload.estado === "ok" && Object.prototype.hasOwnProperty.call(payload, "datos")) {
    return payload.datos;
  }
  return payload;
}

els.btnLogin.addEventListener("click", async () => {
  try {
    const payload = {
      usuario: els.authUser.value.trim(),
      contrasena: els.authPass.value.trim(),
    };
    const data = await apiFetch(state.api.auth, "/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setToken(data.token_acceso);
    els.authResponse.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    els.authResponse.textContent = `[ERROR] ${err.message}`;
  }
});

els.btnLogout.addEventListener("click", () => {
  setToken("");
});

els.headers.forEach((btn) => {
  btn.addEventListener("click", () => {
    const section = btn.dataset.section;
    const body = document.getElementById(`section-${section}`);
    const active = body.classList.contains("active");
    document.querySelectorAll(".accordion__body").forEach((el) => el.classList.remove("active"));
    if (!active) {
      body.classList.add("active");
      state.activeSection = section;
    }
  });
});

function setAudioStatus(section, text, recording = false) {
  const status = document.getElementById(`status-${section}`);
  const button = document.querySelector(`.record[data-record="${section}"]`);
  if (status) status.textContent = text;
  if (button) button.classList.toggle("recording", recording);
}

async function startRecording(section) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mimeType = MediaRecorder.isTypeSupported("audio/webm")
    ? "audio/webm"
    : MediaRecorder.isTypeSupported("audio/ogg")
    ? "audio/ogg"
    : "";
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  state.chunks = [];
  state.recorder = recorder;
  state.stream = stream;
  state.activeSection = section;

  recorder.addEventListener("dataavailable", (event) => {
    if (event.data.size > 0) state.chunks.push(event.data);
  });

  recorder.addEventListener("stop", async () => {
    const blob = new Blob(state.chunks, { type: recorder.mimeType || "audio/webm" });
    stream.getTracks().forEach((track) => track.stop());
    setAudioStatus(section, "Subiendo...");
    try {
      const extension = blob.type.includes("ogg") ? "ogg" : "webm";
      const file = new File([blob], `grabacion.${extension}`, { type: blob.type });
      const formData = new FormData();
      formData.append("archivo", file);
      const audio = await apiFetch(state.api.audio, "/api/v1/audio/subir", {
        method: "POST",
        body: formData,
      });
      await esperarTranscripcion(audio.id_audio, section);
    } catch (err) {
      setAudioStatus(section, `Error: ${err.message}`);
    }
  });

  recorder.start();
  setAudioStatus(section, "Grabando...", true);
}

function stopRecording() {
  if (state.recorder && state.recorder.state !== "inactive") {
    state.recorder.stop();
  }
}

async function esperarTranscripcion(idAudio, section) {
  setAudioStatus(section, "Transcribiendo...");
  const maxIntentos = 180; // ~90s con intervalo de 500ms
  for (let i = 0; i < maxIntentos; i += 1) {
    const estado = await apiFetch(state.api.audio, `/api/v1/audio/${idAudio}/estado`);
    if (estado.estado === "completado" && estado.transcripcion) {
      const resp = document.getElementById(`resp-${section}`);
      if (resp) {
        resp.textContent = JSON.stringify(
          {
            id_audio: estado.id_audio,
            estado: estado.estado,
            transcripcion_limpia: estado.transcripcion,
            transcripcion_raw: estado.transcripcion_raw,
            tokens_muestra: estado.tokens_muestra,
          },
          null,
          2
        );
      }
      await analizarIA(estado.transcripcion, section);
      setAudioStatus(section, "Listo");
      return;
    }
    if (estado.estado === "fallido") {
      setAudioStatus(section, "Falló");
      return;
    }
    if (estado.estado === "pendiente" || estado.estado === "procesando") {
      setAudioStatus(section, `Transcribiendo... (${i + 1}/${maxIntentos})`);
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  setAudioStatus(section, "Tiempo agotado (sin transcripción)");
}

async function analizarIA(texto, section) {
  const payload = { texto, tipo: section, usar_cache: false };
  const data = await apiFetch(state.api.ia, "/api/v1/ia/extraer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const resp = document.getElementById(`resp-${section}`);
  if (resp) {
    const previo = resp.textContent || "";
    resp.textContent = `${previo}\n\n--- ANALISIS IA ---\n${JSON.stringify(data, null, 2)}`;
  }
  completarFormulario(section, data.campos || {});
}

function completarFormulario(section, campos) {
  if (section === "personales") {
    setVal("p_nombre", campos.nombre);
    setVal("p_edad", campos.edad);
    setVal("p_tipo_doc", campos.tipo_documento);
    setVal("p_num_doc", campos.numero_documento);
    setVal("p_sexo", campos.sexo);
    setVal("p_dia", campos.dia_nacimiento);
    setVal("p_mes", campos.mes_nacimiento);
    setVal("p_anio", campos.anio_nacimiento);
    setVal("p_estado_civil", campos.estado_civil);
    setVal("p_lugar_nac", campos.lugar_nacimiento);
    setVal("p_aseguradora", campos.aseguradora);
    setVal("p_correo", campos.correo);
    setVal("p_telefono", campos.telefono);
    setVal("p_municipio", campos.municipio);
  }
  if (section === "acompanante") {
    setVal("a_nombre", campos.nombre);
    setVal("a_tipo_doc", campos.tipo_documento);
    setVal("a_num_doc", campos.numero_documento);
    setVal("a_telefono", campos.telefono);
  }
  if (section === "representante") {
    setVal("r_nombre", campos.nombre);
    setVal("r_tipo_doc", campos.tipo_documento);
    setVal("r_num_doc", campos.numero_documento);
    setVal("r_telefono", campos.telefono);
  }
}

function setVal(id, value) {
  if (value === undefined || value === null) return;
  const el = document.getElementById(id);
  if (!el) return;

  const valor = String(value).trim();
  if (!valor) return;
  if (valor.toLowerCase() === "no especificado") return;

  if (el.tagName === "SELECT") {
    const existe = Array.from(el.options).some((opt) => opt.value === valor || opt.text === valor);
    if (existe) el.value = valor;
    return;
  }

  if (el.type === "number") {
    if (!/^\d+$/.test(valor)) return;
    el.value = valor;
    return;
  }

  if (el.type === "email") {
    if (!valor.includes("@")) return;
    el.value = valor;
    return;
  }

  el.value = valor;
}

els.recordButtons.forEach((btn) => {
  const section = btn.dataset.record;
  btn.addEventListener("mousedown", () => startRecording(section));
  btn.addEventListener("mouseup", stopRecording);
  btn.addEventListener("mouseleave", stopRecording);
  btn.addEventListener("touchstart", (e) => {
    e.preventDefault();
    startRecording(section);
  });
  btn.addEventListener("touchend", stopRecording);
});

setToken(state.token);
