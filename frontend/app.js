/**
 * VoicePilot — Advanced Real-Time Voice Assistant Client
 */

class VoicePilotClient {
  constructor() {
    this.ws = null;
    this.audioContext = null;
    this.mediaStream = null;
    this.audioProcessor = null;
    this.isPlaying = false;
    this.isSessionActive = false;
    this.currentResponseId = 0;
    
    // Playback queue
    this.audioQueue = [];
    this.activeSourceNodes = [];
    
    // Speech Recognition (Web Speech API fallback/companion)
    this.recognition = null;
    this.wakeWordActive = true;
    
    // Canvas & Visualizer
    this.canvas = document.getElementById("waveformCanvas");
    this.canvasCtx = this.canvas.getContext("2d");
    this.analyser = null;
    this.visualizerAnimationId = null;

    // UI Elements
    this.statePill = document.getElementById("statePill");
    this.stateText = document.getElementById("stateText");
    this.orbCore = document.getElementById("orbCore");
    this.userTranscript = document.getElementById("userTranscript");
    this.aiTranscript = document.getElementById("aiTranscript");
    this.micLiveDot = document.getElementById("micLiveDot");
    this.audioStreamBadge = document.getElementById("audioStreamBadge");
    this.connectionBadge = document.getElementById("connectionBadge");
    this.toggleSessionBtn = document.getElementById("toggleSessionBtn");
    this.sessionBtnText = document.getElementById("sessionBtnText");
    this.bargeInBtn = document.getElementById("bargeInBtn");
    this.wakeWordCheckbox = document.getElementById("wakeWordCheckbox");
    this.toolActivityCard = document.getElementById("toolActivityCard");
    this.toolNameBadge = document.getElementById("toolNameBadge");
    this.toolStatusText = document.getElementById("toolStatusText");
    this.toolJsonOutput = document.getElementById("toolJsonOutput");
    
    // Dashboard elements
    this.remindersList = document.getElementById("remindersList");
    this.reminderCount = document.getElementById("reminderCount");
    this.tasksList = document.getElementById("tasksList");
    this.taskCount = document.getElementById("taskCount");

    // Metrics elements
    this.metricTool = document.getElementById("metricTool");
    this.metricLlm = document.getElementById("metricLlm");
    this.metricTts = document.getElementById("metricTts");
    this.metricTotal = document.getElementById("metricTotal");

    // Settings Modal
    this.settingsModal = document.getElementById("settingsModal");
    this.openSettingsBtn = document.getElementById("openSettingsBtn");
    this.closeSettingsBtn = document.getElementById("closeSettingsBtn");
    this.cancelSettingsBtn = document.getElementById("cancelSettingsBtn");
    this.saveSettingsBtn = document.getElementById("saveSettingsBtn");

    this.initEventListeners();
    this.initSpeechRecognition();
    this.connectWebSocket();
    this.startVisualizer();
  }

  initEventListeners() {
    this.toggleSessionBtn.addEventListener("click", () => this.toggleSession());
    this.bargeInBtn.addEventListener("click", () => this.triggerBargeIn());
    
    this.wakeWordCheckbox.addEventListener("change", (e) => {
      this.wakeWordActive = e.target.checked;
    });

    // Text Fallback Form
    document.getElementById("textInputForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const input = document.getElementById("textPromptInput");
      const text = input.value.trim();
      if (text) {
        this.sendTextUtterance(text);
        input.value = "";
      }
    });

    // Demo Pills
    document.querySelectorAll(".demo-pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        const prompt = btn.getAttribute("data-prompt");
        if (prompt) {
          this.sendTextUtterance(prompt);
        }
      });
    });

    // Settings Modal Handlers
    this.openSettingsBtn.addEventListener("click", () => {
      this.settingsModal.style.display = "flex";
    });
    this.closeSettingsBtn.addEventListener("click", () => {
      this.settingsModal.style.display = "none";
    });
    this.cancelSettingsBtn.addEventListener("click", () => {
      this.settingsModal.style.display = "none";
    });
    this.saveSettingsBtn.addEventListener("click", () => {
      this.saveSettings();
    });
  }

  connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/voice`;
    
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log("[WS] Connected to VoicePilot Server");
      this.connectionBadge.classList.add("connected");
      this.connectionBadge.querySelector(".status-label").textContent = "Connected";
      this.ws.send(JSON.stringify({ type: "get_data" }));
    };

    this.ws.onclose = () => {
      console.log("[WS] Disconnected. Reconnecting in 3s...");
      this.connectionBadge.classList.remove("connected");
      this.connectionBadge.querySelector(".status-label").textContent = "Disconnected";
      setTimeout(() => this.connectWebSocket(), 3000);
    };

    this.ws.onerror = (err) => {
      console.error("[WS] Error:", err);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        this.handleServerMessage(msg);
      } catch (e) {
        console.error("[WS] Message parsing error:", e);
      }
    };
  }

  handleServerMessage(msg) {
    switch (msg.type) {
      case "state":
        this.updateState(msg.value);
        if (msg.response_id) {
          this.currentResponseId = msg.response_id;
        }
        break;

      case "transcript_partial":
        this.userTranscript.textContent = msg.text;
        break;

      case "transcript_final":
        this.userTranscript.textContent = msg.text;
        break;

      case "llm_chunk":
        if (msg.response_id === this.currentResponseId) {
          if (this.aiTranscript.textContent === "Thinking..." || this.aiTranscript.textContent === "Ready for your voice command.") {
            this.aiTranscript.textContent = "";
          }
          this.aiTranscript.textContent += msg.text;
        }
        break;

      case "audio_chunk":
        if (msg.response_id === this.currentResponseId) {
          this.queueAudioChunk(msg.data);
        }
        break;

      case "audio_end":
        // End of audio stream for this response turn
        break;

      case "interrupt":
        console.log(`[Barge-In] Response ${msg.cancelled_response_id} cancelled by server`);
        this.flushAudioQueue();
        this.updateState("interrupted");
        setTimeout(() => this.updateState("listening"), 300);
        break;

      case "tool_start":
        if (msg.response_id === this.currentResponseId) {
          this.showToolActivity(msg.tool, "Executing...", msg.args);
        }
        break;

      case "tool_result":
        if (msg.response_id === this.currentResponseId) {
          this.showToolActivity(msg.tool, "Completed", msg.result);
        }
        break;

      case "data_update":
        this.renderReminders(msg.reminders || []);
        this.renderTasks(msg.tasks || []);
        break;

      case "metrics":
        if (msg.metrics) {
          this.updateMetrics(msg.metrics);
        }
        break;

      case "error":
        this.updateState("error");
        this.aiTranscript.textContent = msg.message || "An error occurred.";
        break;
    }
  }

  updateState(state) {
    const s = (state || "idle").toLowerCase();
    this.statePill.className = `state-pill state-${s}`;
    this.stateText.textContent = s.toUpperCase().replace("_", " ");

    // Orb visual animations
    this.orbCore.classList.remove("speaking", "listening");
    if (s === "speaking") {
      this.orbCore.classList.add("speaking");
      this.audioStreamBadge.style.display = "inline-block";
      this.micLiveDot.style.display = "none";
    } else if (s === "listening") {
      this.orbCore.classList.add("listening");
      this.audioStreamBadge.style.display = "none";
      this.micLiveDot.style.display = "inline-block";
    } else {
      this.audioStreamBadge.style.display = "none";
      this.micLiveDot.style.display = "none";
    }
  }

  showToolActivity(toolName, status, data) {
    this.toolActivityCard.style.display = "block";
    this.toolNameBadge.textContent = `⚡ Tool: ${toolName}()`;
    this.toolStatusText.textContent = status;
    this.toolJsonOutput.textContent = JSON.stringify(data, null, 2);
  }

  updateMetrics(m) {
    if (m.tool_latency_s !== undefined) this.metricTool.textContent = `${m.tool_latency_s.toFixed(2)}s`;
    if (m.llm_first_token_s !== undefined) this.metricLlm.textContent = `${m.llm_first_token_s.toFixed(2)}s`;
    if (m.tts_first_audio_s !== undefined) this.metricTts.textContent = `${m.tts_first_audio_s.toFixed(2)}s`;
    if (m.total_roundtrip_s !== undefined) this.metricTotal.textContent = `${m.total_roundtrip_s.toFixed(2)}s`;
  }

  renderReminders(reminders) {
    this.reminderCount.textContent = reminders.length;
    if (reminders.length === 0) {
      this.remindersList.innerHTML = `<div class="empty-state">No active reminders. Try saying: "Remind me tomorrow at 9 AM to study DBMS"</div>`;
      return;
    }

    this.remindersList.innerHTML = reminders.map(r => `
      <div class="list-item-card">
        <div>
          <div class="item-title">${this.escapeHtml(r.title)}</div>
          <div class="item-meta">📅 ${this.escapeHtml(r.datetime)}</div>
        </div>
        <span class="priority-badge priority-medium">${r.status || 'pending'}</span>
      </div>
    `).join("");
  }

  renderTasks(tasks) {
    this.taskCount.textContent = tasks.length;
    if (tasks.length === 0) {
      this.tasksList.innerHTML = `<div class="empty-state">No tasks created. Try saying: "Create a high priority task to finish Python assignment"</div>`;
      return;
    }

    this.tasksList.innerHTML = tasks.map(t => `
      <div class="list-item-card">
        <div>
          <div class="item-title">${this.escapeHtml(t.title)}</div>
          <div class="item-meta">Due: ${this.escapeHtml(t.due_date || 'None')}</div>
        </div>
        <span class="priority-badge priority-${(t.priority || 'medium').toLowerCase()}">${t.priority || 'medium'}</span>
      </div>
    `).join("");
  }

  escapeHtml(str) {
    if (!str) return "";
    return str.replace(/[&<>"']/g, m => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[m]));
  }

  // =========================================================================
  // Speech & Audio Pipeline
  // =========================================================================

  async initAudioContext() {
    if (!this.audioContext) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.audioContext = new AudioCtx({ sampleRate: 16000 });
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 64;
    }
    if (this.audioContext.state === "suspended") {
      await this.audioContext.resume();
    }
  }

  async toggleSession() {
    if (this.isSessionActive) {
      this.stopSession();
    } else {
      await this.startSession();
    }
  }

  async startSession() {
    try {
      await this.initAudioContext();
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      const source = this.audioContext.createMediaStreamSource(this.mediaStream);
      this.audioProcessor = this.audioContext.createScriptProcessor(4096, 1, 1);
      
      source.connect(this.analyser);
      source.connect(this.audioProcessor);
      this.audioProcessor.connect(this.audioContext.destination);

      // Stream PCM audio chunks and monitor audio energy for instant barge-in
      this.audioProcessor.onaudioprocess = (e) => {
        if (!this.isSessionActive) return;
        const inputData = e.inputBuffer.getChannelData(0);
        
        // Calculate RMS audio energy
        let sum = 0;
        for (let i = 0; i < inputData.length; i++) {
          sum += inputData[i] * inputData[i];
        }
        const rms = Math.sqrt(sum / inputData.length);

        // Instant Barge-In detection: if assistant is speaking and user speaks loud enough
        if (this.isPlaying && rms > 0.04) {
          console.log("[VAD] User voice detected during playback -> triggering Barge-In!");
          this.triggerBargeIn();
        }

        // Convert float32 to int16 PCM
        const pcm16 = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }

        // Base64 encode and send chunk over WebSocket
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          const base64Chunk = this.arrayBufferToBase64(pcm16.buffer);
          this.ws.send(JSON.stringify({
            type: "audio_chunk",
            data: base64Chunk
          }));
        }
      };

      this.isSessionActive = true;
      this.toggleSessionBtn.classList.add("active");
      this.sessionBtnText.textContent = "Listening (Active)";
      
      if (this.recognition) {
        try { this.recognition.start(); } catch (e) {}
      }

      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "session_start" }));
      }

      this.userTranscript.textContent = "Listening... Speak anytime.";
      this.aiTranscript.textContent = "Ready.";

    } catch (err) {
      console.error("[Audio] Microphone permission or init error:", err);
      alert("Microphone access is required for real-time voice interaction.");
    }
  }

  stopSession() {
    this.isSessionActive = false;
    this.toggleSessionBtn.classList.remove("active");
    this.sessionBtnText.textContent = "Start Voice Session";

    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(t => t.stop());
      this.mediaStream = null;
    }
    if (this.audioProcessor) {
      this.audioProcessor.disconnect();
      this.audioProcessor = null;
    }
    if (this.recognition) {
      try { this.recognition.stop(); } catch (e) {}
    }

    this.flushAudioQueue();
    this.updateState("idle");
  }

  initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      console.warn("[STT] Web Speech API not supported in this browser. Relying on backend Deepgram STT.");
      return;
    }

    this.recognition = new SpeechRecognition();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = "en-US";

    this.recognition.onresult = (event) => {
      let interimTranscript = "";
      let finalTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          interimTranscript += event.results[i][0].transcript;
        }
      }

      const currentSpeech = finalTranscript || interimTranscript;

      // Check for wake word ("Hey VoicePilot" / "VoicePilot")
      if (this.wakeWordActive && !this.isSessionActive) {
        if (currentSpeech.toLowerCase().includes("voicepilot") || currentSpeech.toLowerCase().includes("voice pilot")) {
          console.log("[WakeWord] Triggered!");
          this.startSession();
          return;
        }
      }

      if (currentSpeech.trim()) {
        if (this.isPlaying) {
          this.triggerBargeIn();
        }

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
          this.ws.send(JSON.stringify({
            type: "user_transcript",
            text: currentSpeech.trim(),
            is_final: !!finalTranscript
          }));
        }
      }
    };

    this.recognition.onend = () => {
      if (this.isSessionActive) {
        try { this.recognition.start(); } catch (e) {}
      }
    };
  }

  triggerBargeIn() {
    console.log("[Barge-In] Triggered user interruption.");
    this.flushAudioQueue();
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "interrupt" }));
    }
    this.updateState("interrupted");
    setTimeout(() => this.updateState("listening"), 300);
  }

  sendTextUtterance(text) {
    if (this.isPlaying) {
      this.triggerBargeIn();
    }
    this.userTranscript.textContent = text;
    this.aiTranscript.textContent = "Thinking...";
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: "user_transcript",
        text: text,
        is_final: true
      }));
    }
  }

  // =========================================================================
  // Streaming Audio Queue Player
  // =========================================================================

  async queueAudioChunk(base64Data) {
    try {
      await this.initAudioContext();
      const binaryString = window.atob(base64Data);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      const audioBuffer = await this.audioContext.decodeAudioData(bytes.buffer.slice(0));
      this.audioQueue.push(audioBuffer);

      if (!this.isPlaying) {
        this.playNextChunk();
      }
    } catch (e) {
      console.warn("[TTS Player] Decode audio error:", e);
    }
  }

  playNextChunk() {
    if (this.audioQueue.length === 0) {
      this.isPlaying = false;
      return;
    }

    this.isPlaying = true;
    const buffer = this.audioQueue.shift();
    const source = this.audioContext.createBufferSource();
    source.buffer = buffer;
    
    source.connect(this.analyser);
    source.connect(this.audioContext.destination);

    this.activeSourceNodes.push(source);

    source.onended = () => {
      const idx = this.activeSourceNodes.indexOf(source);
      if (idx !== -1) {
        this.activeSourceNodes.splice(idx, 1);
      }
      this.playNextChunk();
    };

    source.start(0);
  }

  flushAudioQueue() {
    this.audioQueue = [];
    for (const src of this.activeSourceNodes) {
      try {
        src.stop(0);
        src.disconnect();
      } catch (e) {}
    }
    this.activeSourceNodes = [];
    this.isPlaying = false;
  }

  arrayBufferToBase64(buffer) {
    let binary = "";
    const bytes = new Uint8Array(buffer);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
  }

  // =========================================================================
  // Visualizer Canvas Loop
  // =========================================================================

  startVisualizer() {
    const draw = () => {
      this.visualizerAnimationId = requestAnimationFrame(draw);
      
      const width = this.canvas.width;
      const height = this.canvas.height;
      this.canvasCtx.clearRect(0, 0, width, height);

      if (!this.analyser) {
        this.drawIdleWave(width, height);
        return;
      }

      const bufferLength = this.analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      this.analyser.getByteFrequencyData(dataArray);

      const centerX = width / 2;
      const centerY = height / 2;
      const radius = 55;

      this.canvasCtx.save();
      this.canvasCtx.translate(centerX, centerY);

      const bars = 36;
      const angleStep = (Math.PI * 2) / bars;

      for (let i = 0; i < bars; i++) {
        const value = dataArray[i % bufferLength] || 10;
        const barHeight = (value / 255) * 35;
        const angle = i * angleStep;

        const x1 = Math.cos(angle) * radius;
        const y1 = Math.sin(angle) * radius;
        const x2 = Math.cos(angle) * (radius + barHeight);
        const y2 = Math.sin(angle) * (radius + barHeight);

        this.canvasCtx.beginPath();
        this.canvasCtx.moveTo(x1, y1);
        this.canvasCtx.lineTo(x2, y2);
        
        if (this.isPlaying) {
          this.canvasCtx.strokeStyle = `rgba(0, 255, 136, ${0.4 + (value / 255) * 0.6})`;
        } else if (this.isSessionActive) {
          this.canvasCtx.strokeStyle = `rgba(0, 240, 255, ${0.4 + (value / 255) * 0.6})`;
        } else {
          this.canvasCtx.strokeStyle = "rgba(142, 155, 180, 0.3)";
        }

        this.canvasCtx.lineWidth = 3;
        this.canvasCtx.lineCap = "round";
        this.canvasCtx.stroke();
      }

      this.canvasCtx.restore();
    };

    draw();
  }

  drawIdleWave(width, height) {
    const time = Date.now() * 0.002;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = 55;

    this.canvasCtx.save();
    this.canvasCtx.translate(centerX, centerY);

    this.canvasCtx.beginPath();
    this.canvasCtx.arc(0, 0, radius + Math.sin(time) * 4, 0, Math.PI * 2);
    this.canvasCtx.strokeStyle = "rgba(0, 240, 255, 0.25)";
    this.canvasCtx.lineWidth = 2;
    this.canvasCtx.stroke();

    this.canvasCtx.restore();
  }

  saveSettings() {
    const openaiKey = document.getElementById("modalOpenaiKey").value.trim();
    const model = document.getElementById("modalModelSelect").value;
    const elevenlabsKey = document.getElementById("modalElevenLabsKey").value.trim();

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: "config_update",
        config: {
          openai_key: openaiKey,
          model: model,
          elevenlabs_key: elevenlabsKey
        }
      }));
    }

    this.settingsModal.style.display = "none";
  }
}

// Initialize on DOM load
window.addEventListener("DOMContentLoaded", () => {
  window.voicePilot = new VoicePilotClient();
});
