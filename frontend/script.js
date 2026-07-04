(function () {
    "use strict";

    function resolveApiBase() {
        const customApiBase = (localStorage.getItem("huili_api_base") || "").trim();
        if (customApiBase) return customApiBase.replace(/\/+$/, "");
        if (window.location.protocol === "file:") return "http://127.0.0.1:5000";
        if (["localhost", "127.0.0.1"].includes(window.location.hostname) && window.location.port === "3000") {
            return "http://127.0.0.1:5000";
        }
        return window.location.origin;
    }
    const API_BASE = resolveApiBase();
    const LIVE2D_MODEL_URL = "./shizuku/model.json";
    const state = {
        sessionId: localStorage.getItem("huili_session_id") || "",
        phone: localStorage.getItem("huili_phone") || "",
        password: localStorage.getItem("huili_password") || "",
        userLocation: null,
        leafletMap: null,
        animationEnabled: true,
        voiceEnabled: false,
        currentUtterance: null,
        recognition: null,
        live2dModel: null,
        live2dApp: null,
        expressionIndex: 0,
        isSpeaking: false,
        adminPassword: localStorage.getItem("huili_admin_password") || ""
    };

    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function formatTime() {
        const now = new Date();
        return `${now.getHours().toString().padStart(2, "0")}:${now.getMinutes().toString().padStart(2, "0")}`;
    }

    async function apiRequest(path, options = {}) {
        const headers = { "Content-Type": "application/json" };
        if (state.sessionId) {
            headers["X-Session-ID"] = state.sessionId;
        }
        let response;
        try {
            response = await fetch(`${API_BASE}${path}`, {
                ...options,
                headers: { ...headers, ...options.headers }
            });
        } catch (fetchErr) {
            throw new Error("网络连接失败，请检查服务器是否启动");
        }
        const contentType = response.headers.get("content-type") || "";
        let payload;
        try {
            payload = contentType.includes("application/json")
                ? await response.json()
                : await response.text();
        } catch (parseErr) {
            if (!response.ok) {
                throw new Error(`请求失败 (${response.status})`);
            }
            throw new Error("响应解析失败");
        }
        if (!response.ok) {
            const errorMessage = payload && payload.error ? payload.error : `请求失败 (${response.status})`;
            throw new Error(errorMessage);
        }
        return payload;
    }

    async function uploadAvatar(file) {
        const formData = new FormData();
        formData.append("avatar", file);
        const phone = localStorage.getItem("huili_phone") || "";
        const response = await fetch(`${API_BASE}/api/avatar/upload`, {
            method: "POST",
            headers: { "X-Session-ID": state.sessionId || "", "X-Phone": phone },
            body: formData
        });
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "上传失败");
        }
        return payload;
    }

    function saveSessionId(sid) {
        if (sid) {
            state.sessionId = sid;
            localStorage.setItem("huili_session_id", sid);
        }
    }

    function updateUserAvatar() {
        const userAvatar = $(".user-avatar");
        const phone = localStorage.getItem("huili_phone") || "";
        if (!userAvatar || !phone) return;
        const img = new Image();
        img.onload = () => {
            userAvatar.innerHTML = "";
            userAvatar.appendChild(img);
        };
        img.onerror = () => {};
        img.src = `${API_BASE}/api/avatar/${phone}?t=${Date.now()}`;
    }

    function openModal(modal) {
        if (modal) modal.classList.add("active");
    }

    function closeModal(modal) {
        if (modal) modal.classList.remove("active");
    }

    function bindModalEvents() {
        $$(".modal").forEach((modal) => {
            modal.addEventListener("click", (event) => {
                if (event.target === modal) closeModal(modal);
            });
        });
        $$(".close-modal").forEach((btn) => {
            btn.addEventListener("click", () => closeModal(btn.closest(".modal")));
        });
    }

    function updateApiStatus(text, isHealthy) {
        const apiStatus = $("#api-status");
        if (apiStatus) {
            apiStatus.textContent = text;
            apiStatus.style.color = isHealthy ? "" : "#d6336c";
        }
    }

    function updateResponseTime(ms) {
        const responseTime = $("#response-time");
        if (responseTime) {
            responseTime.textContent = `响应: ${ms} ms`;
        }
    }

    function addMessage(content, role = "bot", extra = {}) {
        const chatMessages = $("#chat-messages");
        if (!chatMessages) return;
        const wrapper = document.createElement("div");
        wrapper.className = `message ${role === "user" ? "user-message" : "bot-message"}`;
        const avatarIcon = role === "user" ? "fa-user" : "fa-robot";
        const userPhone = localStorage.getItem("huili_phone") || "";
        let avatarHtml;
        if (role === "user" && userPhone) {
            avatarHtml = `<div class="message-avatar"><img src="${API_BASE}/api/avatar/${userPhone}?t=${Date.now()}" onerror="this.outerHTML='<i class=\\'fas fa-user\\'></i>'"></div>`;
        } else {
            avatarHtml = `<div class="message-avatar"><i class="fas ${avatarIcon}"></i></div>`;
        }
        const safeContent = typeof content === "string" ? content : JSON.stringify(content);
        const suggestionsHtml = Array.isArray(extra.suggestions) && extra.suggestions.length
            ? `<div class="message-suggestions">${extra.suggestions.map((item) => `<button type="button" class="btn-small suggestion-chip" data-query="${escapeHtml(item)}">${escapeHtml(item)}</button>`).join("")}</div>`
            : "";
        const rawImgUrl = extra.imageUrl || "";
        const fullImgUrl = rawImgUrl.startsWith("/") ? `${API_BASE}${rawImgUrl}` : rawImgUrl;
        const imageHtml = fullImgUrl ? `<div class="message-image" onclick="window.open('${fullImgUrl}','_blank')"><img src="${fullImgUrl}" alt="${extra.imageAlt || '景点图片'}" loading="lazy"></div>` : "";
        wrapper.innerHTML = `
            ${avatarHtml}
            <div class="message-content">
                <div class="message-text">${safeContent}</div>
                ${imageHtml}
                ${suggestionsHtml}
                <div class="message-time">${formatTime()}</div>
            </div>
        `;
        chatMessages.appendChild(wrapper);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        $$(".suggestion-chip", wrapper).forEach((chip) => {
            chip.addEventListener("click", () => {
                const userInput = $("#user-input");
                if (userInput) {
                    userInput.value = chip.dataset.query || "";
                    userInput.focus();
                }
            });
        });
    }

    function setVoiceStatus(active, text) {
        const voiceStatus = $("#voice-status");
        const voiceIndicator = $("#voice-indicator");
        const voiceToggleIcon = $("#voice-toggle i");
        if (voiceStatus) {
            const iconClass = active ? "fa-microphone" : "fa-microphone-slash";
            voiceStatus.innerHTML = `<i class="fas ${iconClass}"></i><span>${text}</span>`;
        }
        if (voiceIndicator) {
            voiceIndicator.classList.toggle("active", active);
        }
        if (voiceToggleIcon) {
            voiceToggleIcon.className = `fas ${active ? "fa-microphone" : "fa-microphone"}`;
        }
    }

    function speakText(text) {
        if (!("speechSynthesis" in window)) return;
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text.replace(/<[^>]+>/g, ""));
        const speedInput = $("#voice-speed");
        const volumeInput = $("#voice-volume");
        utterance.lang = "zh-CN";
        utterance.rate = speedInput ? Number(speedInput.value) : 1;
        utterance.volume = volumeInput ? Number(volumeInput.value) : 0.8;
        utterance.onstart = () => live2dStartSpeaking();
        utterance.onend = () => live2dStopSpeaking();
        utterance.onerror = () => live2dStopSpeaking();
        state.currentUtterance = utterance;
        window.speechSynthesis.speak(utterance);
    }

    function stopSpeaking() {
        if ("speechSynthesis" in window) {
            window.speechSynthesis.cancel();
        }
        state.currentUtterance = null;
        live2dStopSpeaking();
    }

    async function sendChatMessage(prefilledText) {
        const input = $("#user-input");
        if (!input && !prefilledText) return;
        const userInput = (prefilledText || input.value || "").trim();
        if (!userInput) return;
        if (input) input.value = "";
        addMessage(escapeHtml(userInput), "user");
        updateApiStatus("API: 请求处理中...", true);
        const startTime = performance.now();
        try {
            const payload = { user_input: userInput };
            if (state.sessionId) payload.session_id = state.sessionId;
            if (state.userLocation) {
                payload.latitude = state.userLocation.latitude;
                payload.longitude = state.userLocation.longitude;
            }
            const result = await apiRequest("/api/chat", {
                method: "POST",
                body: JSON.stringify(payload)
            });
            saveSessionId(result.session_id);
            let extra = { suggestions: result.suggestions || [] };
            try {
                const imgResp = await fetch(`${API_BASE}/api/scenic_image?place=${encodeURIComponent(userInput)}`);
                if (imgResp.ok) {
                    const imgData = await imgResp.json();
                    if (imgData.success && imgData.image && imgData.image.url) {
                        extra.imageUrl = imgData.image.url;
                        extra.imageAlt = imgData.image.place_name || imgData.image.source || "景点图片";
                    }
                }
            } catch (imgErr) {}
            addMessage(result.reply || "系统未返回内容", "bot", extra);
            updateApiStatus("API: 连接正常", true);
            updateResponseTime(Math.round(performance.now() - startTime));
            const sessionStatus = $("#session-status");
            if (sessionStatus && state.sessionId) {
                sessionStatus.textContent = `会话已连接 · ${state.sessionId.slice(0, 8)}`;
            }
            if (result.reply) {
                speakText(result.reply);
            }
        } catch (error) {
            addMessage(`抱歉，当前请求失败：${escapeHtml(error.message)}`, "bot");
            updateApiStatus("API: 连接异常", false);
        }
    }

    function live2dStartSpeaking() {
        state.isSpeaking = true;
    }

    function live2dStopSpeaking() {
        state.isSpeaking = false;
    }

    function live2dToggleExpression() {
        if (!state.live2dModel) return;
        try {
            state.expressionIndex = (state.expressionIndex + 1) % 4;
            state.live2dModel.expression(`f0${state.expressionIndex + 1}`);
        } catch (e) {}
    }

    function initLive2DScene() {
        const container = $("#digital-human-container");
        if (!container) return;
        const modelUrl = LIVE2D_MODEL_URL;
        const toggleAnimation = $("#toggle-animation");
        const toggleExpression = $("#toggle-expression");
        const resetView = $("#reset-view");
        const voiceSpeed = $("#voice-speed");
        const speedValue = $("#speed-value");
        const voiceVolume = $("#voice-volume");
        const volumeValue = $("#volume-value");

        function tryInit(retries) {
            if (retries <= 0) {
                const loadingOverlay = $(".loading-overlay", container);
                if (loadingOverlay) {
                    loadingOverlay.querySelector("p").textContent = "模型组件加载失败，请刷新页面";
                    loadingOverlay.querySelector(".spinner").style.display = "none";
                }
                const statusEl = $("#live2d-status");
                const statusText = $("#model-status-text");
                if (statusEl) statusEl.classList.add("error");
                if (statusText) statusText.textContent = "组件加载失败";
                return;
            }
            if (!window.PIXI || !window.PIXI.live2d || !window.PIXI.live2d.Live2DModel) {
                setTimeout(() => tryInit(retries - 1), 300);
                return;
            }
            const width = container.clientWidth || 640;
            const height = container.clientHeight || 460;
            const app = new PIXI.Application({
                width,
                height,
                transparent: true,
                resolution: window.devicePixelRatio || 1,
                autoDensity: true
            });
            container.appendChild(app.view);
            state.live2dApp = app;
            const statusEl = $("#live2d-status");
            const statusText = $("#model-status-text");
            const Live2DModel = PIXI.live2d.Live2DModel;

            Live2DModel.from(modelUrl, { autoInteract: true }).then((model) => {
                state.live2dModel = model;
                const scale = Math.min(
                    (width * 0.7) / model.width,
                    (height * 0.85) / model.height
                );
                model.scale.set(scale);
                model.x = (width - model.width * scale) / 2;
                model.y = (height - model.height * scale) / 2;
                app.stage.addChild(model);

                const coreModel = model.internalModel.coreModel;
                const isCubism2 = typeof coreModel.getParamIndex === "function";

                if (isCubism2) {
                    const mouthIdx = coreModel.getParamIndex("PARAM_MOUTH_OPEN_Y");
                    if (mouthIdx >= 0) {
                        let lipSyncPhase = 0;
                        const origUpdate = coreModel.update.bind(coreModel);
                        coreModel.update = function () {
                            try { origUpdate(); } catch (e) {}
                            if (state.isSpeaking) {
                                lipSyncPhase += 0.016;
                                const base = Math.abs(Math.sin(lipSyncPhase * 8));
                                const noise = Math.abs(Math.sin(lipSyncPhase * 13.7)) * 0.3;
                                const value = Math.min(1, base * 0.7 + noise + 0.1);
                                try { coreModel.setParamFloat(mouthIdx, value); } catch (e) {}
                            }
                        };
                    }
                }

                const loadingOverlay = $(".loading-overlay", container);
                if (loadingOverlay) loadingOverlay.style.display = "none";
                if (statusEl) statusEl.classList.add("loaded");
                if (statusText) statusText.textContent = "AI导游已就绪";

                try { model.motion("idle"); } catch (e) {}

                model.on("hit", (areas) => {
                    try { model.motion("tap_body"); } catch (e) {
                        try { model.motion("idle"); } catch (e2) {}
                    }
                });

                window.addEventListener("resize", () => {
                    const newWidth = container.clientWidth || width;
                    const newHeight = container.clientHeight || height;
                    app.renderer.resize(newWidth, newHeight);
                    const newScale = Math.min(
                        (newWidth * 0.7) / model.width,
                        (newHeight * 0.85) / model.height
                    );
                    model.scale.set(newScale);
                    model.x = (newWidth - model.width * newScale) / 2;
                    model.y = (newHeight - model.height * newScale) / 2;
                });
            }).catch((error) => {
                console.error("Live2D模型加载失败:", error);
                const loadingOverlay = $(".loading-overlay", container);
                if (loadingOverlay) {
                    loadingOverlay.querySelector("p").textContent = "模型加载失败，请检查网络后刷新";
                    loadingOverlay.querySelector(".spinner").style.display = "none";
                }
                if (statusEl) statusEl.classList.add("error");
                if (statusText) statusText.textContent = "模型加载失败";
            });
        }

        tryInit(20);

        if (toggleAnimation) {
            toggleAnimation.addEventListener("click", () => {
                state.animationEnabled = !state.animationEnabled;
                toggleAnimation.innerHTML = `<i class="fas ${state.animationEnabled ? "fa-pause" : "fa-play"}"></i> ${state.animationEnabled ? "暂停动画" : "播放动画"}`;
                if (state.live2dModel) {
                    if (state.animationEnabled) {
                        try { state.live2dModel.motion("idle"); } catch (e) {}
                    } else {
                        try { state.live2dModel.internalModel.motionManager.stopAllMotions(); } catch (e) {}
                    }
                }
            });
        }

        if (toggleExpression) {
            toggleExpression.addEventListener("click", () => {
                live2dToggleExpression();
            });
        }

        if (voiceSpeed && speedValue) {
            speedValue.textContent = `${Number(voiceSpeed.value).toFixed(1)}x`;
            voiceSpeed.addEventListener("input", () => {
                speedValue.textContent = `${Number(voiceSpeed.value).toFixed(1)}x`;
            });
        }

        if (voiceVolume && volumeValue) {
            volumeValue.textContent = `${Math.round(Number(voiceVolume.value) * 100)}%`;
            voiceVolume.addEventListener("input", () => {
                volumeValue.textContent = `${Math.round(Number(voiceVolume.value) * 100)}%`;
            });
        }

        if (resetView) {
            resetView.addEventListener("click", () => {
                if (!state.live2dModel) return;
                const container = $("#digital-human-container");
                if (!container) return;
                const width = container.clientWidth || 640;
                const height = container.clientHeight || 460;
                const scale = Math.min(
                    (width * 0.8) / state.live2dModel.width,
                    (height * 0.9) / state.live2dModel.height
                );
                state.live2dModel.scale.set(scale);
                state.live2dModel.x = (width - state.live2dModel.width * scale) / 2;
                state.live2dModel.y = (height - state.live2dModel.height * scale) / 2;
                try { state.live2dModel.motion("idle"); } catch (e) {}
            });
        }
    }

    function initVoiceInput() {
        const voiceToggle = $("#voice-toggle");
        const stopVoice = $("#stop-voice");
        if (!voiceToggle) return;

        let mediaRecorder = null;
        let audioChunks = [];
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const hasMediaRecorder = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

        if (!hasMediaRecorder && !SpeechRecognition) {
            // 浏览器啥都不支持，别折腾了
            voiceToggle.style.opacity = "0.5";
            voiceToggle.title = "浏览器不支持语音输入";
            return;
        }

        function stopMediaRecording() {
            if (mediaRecorder && mediaRecorder.state !== "inactive") {
                mediaRecorder.stop();
            }
        }

        async function startBackendRecording() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                mediaRecorder = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4" });
                audioChunks = [];

                mediaRecorder.ondataavailable = (e) => {
                    if (e.data.size > 0) audioChunks.push(e.data);
                };

                mediaRecorder.onstop = async () => {
                    stream.getTracks().forEach((t) => t.stop());
                    if (!audioChunks.length) return;

                    const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
                    const formData = new FormData();
                    formData.append("audio", audioBlob, "recording." + (mediaRecorder.mimeType.includes("webm") ? "webm" : "mp4"));
                    if (state.sessionId) formData.append("session_id", state.sessionId);
                    if (state.userLocation) {
                        formData.append("latitude", state.userLocation.latitude);
                        formData.append("longitude", state.userLocation.longitude);
                    }

                    updateApiStatus("API: 语音识别中...", true);
                    try {
                        const resp = await fetch(`${API_BASE}/api/voice`, { method: "POST", body: formData });
                        const data = await resp.json();
                        if (data.success && data.voice_text) {
                            const input = $("#user-input");
                            if (input) input.value = data.voice_text;
                            addMessage(escapeHtml(data.voice_text), "user");
                            if (data.reply) {
                                addMessage(data.reply, "bot", { suggestions: data.suggestions || [] });
                                speakText(data.reply);
                            }
                            updateApiStatus("API: 连接正常", true);
                        } else {
                            addMessage("语音识别失败: " + escapeHtml(data.error || "未知错误"), "bot");
                            updateApiStatus("API: 识别异常", false);
                        }
                    } catch (err) {
                        addMessage("语音服务异常: " + escapeHtml(err.message), "bot");
                        updateApiStatus("API: 连接异常", false);
                    }
                    setVoiceStatus(false, "语音输入已关闭");
                    state.voiceEnabled = false;
                };

                mediaRecorder.start();
                state.voiceEnabled = true;
                setVoiceStatus(true, "正在录音...请说话");
            } catch (e) {
                setVoiceStatus(false, "麦克风权限被拒绝");
                console.error("getUserMedia error:", e);
            }
        }

        function startBrowserRecognition() {
            const recognition = new SpeechRecognition();
            recognition.lang = "zh-CN";
            recognition.continuous = false;
            recognition.interimResults = false;
            state.recognition = recognition;

            recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                const input = $("#user-input");
                if (input) input.value = transcript;
                sendChatMessage(transcript);
                state.voiceEnabled = false;
                setVoiceStatus(false, "语音输入已关闭");
            };

            recognition.onerror = () => {
                state.voiceEnabled = false;
                setVoiceStatus(false, "语音识别出错，请重试");
            };

            recognition.onend = () => {
                if (state.voiceEnabled) {
                    state.voiceEnabled = false;
                    setVoiceStatus(false, "语音输入已关闭");
                }
            };

            try {
                recognition.start();
                state.voiceEnabled = true;
                setVoiceStatus(true, "正在聆听...请说话");
            } catch (e) {
                setVoiceStatus(false, "语音启动失败");
            }
        }

        voiceToggle.addEventListener("click", () => {
            if (state.voiceEnabled) {
                stopMediaRecording();
                if (state.recognition) {
                    try { state.recognition.stop(); } catch (e) {}
                }
                state.voiceEnabled = false;
                setVoiceStatus(false, "语音输入已关闭");
            } else {
                if (hasMediaRecorder) {
                    startBackendRecording();
                } else {
                    startBrowserRecognition();
                }
            }
        });

        if (stopVoice) {
            stopVoice.addEventListener("click", () => {
                stopMediaRecording();
                if (state.recognition) {
                    try { state.recognition.stop(); } catch (e) {}
                }
                state.voiceEnabled = false;
                setVoiceStatus(false, "语音输入已关闭");
            });
        }
    }

    function initNearbyAttractions() {
        const nearbyBtn = $("#nearby-attractions");
        const nearbyModal = $("#nearby-modal");
        const searchNearby = $("#search-nearby");
        const useMyLocation = $("#use-my-location");
        const getLocation = $("#get-location");
        let leafletMap = null;

        if (nearbyBtn && nearbyModal) {
            nearbyBtn.addEventListener("click", () => {
                openModal(nearbyModal);
                setTimeout(initLeafletMap, 200); // 等 modal 显示出来再初始化地图
            });
        }

        function initLeafletMap() {
            const mapContainer = $("#map-container");
            if (!mapContainer || leafletMap) return;

            const defaultLat = 26.6584;
            const defaultLng = 102.2437;

            leafletMap = L.map("map-container").setView([defaultLat, defaultLng], 13);
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
                maxZoom: 19
            }).addTo(leafletMap);

            L.marker([defaultLat, defaultLng])
                .addTo(leafletMap)
                .bindPopup("<b>会理市</b><br>千年古城")
                .openPopup();

            state.leafletMap = leafletMap;
        }

        function clearMapMarkers() {
            if (!state.leafletMap) return;
            state.leafletMap.eachLayer((layer) => {
                if (layer instanceof L.Marker && !(layer._popup && layer._popup._content && layer._popup._content.includes("会理市"))) {
                    state.leafletMap.removeLayer(layer);
                }
            });
        }

        function addMapMarkers(attractions) {
            if (!state.leafletMap || !attractions || !attractions.length) return;
            const bounds = [];
            attractions.forEach((p) => {
                if (p.latitude && p.longitude) {
                    const marker = L.marker([p.latitude, p.longitude])
                        .addTo(state.leafletMap)
                        .bindPopup(`<b>${escapeHtml(p.name)}</b><br>${escapeHtml(p.description || p.address || "")}${p.distance_km ? `<br>距离: ${Number(p.distance_km).toFixed(1)} km` : ""}`);
                    bounds.push([p.latitude, p.longitude]);
                }
            });
            if (bounds.length) {
                state.leafletMap.fitBounds(bounds, { padding: [30, 30] });
            }
        }

        if (searchNearby) {
            searchNearby.addEventListener("click", async () => {
                const lat = Number($("#latitude")?.value);
                const lng = Number($("#longitude")?.value);
                const radius = Number($("#radius")?.value);
                const nearbyResults = $("#nearby-results");
                if (!nearbyResults) return;
                nearbyResults.innerHTML = '<p class="empty-state">搜索中...</p>';
                try {
                    const result = await apiRequest(`/api/geo_nearby?lat=${lat}&lng=${lng}&radius_km=${radius}`);
                    if (result.attractions && result.attractions.length > 0) {
                        nearbyResults.innerHTML = result.attractions.map((p) => `
                            <div class="nearby-card">
                                <h4>${escapeHtml(p.name)}</h4>
                                <p>${escapeHtml(p.description || p.address || "")}</p>
                                <span class="distance">${p.distance_km ? Number(p.distance_km).toFixed(1) + " km" : ""}</span>
                            </div>
                        `).join("");
                        if (!state.leafletMap) initLeafletMap();
                        clearMapMarkers();
                        addMapMarkers(result.attractions);
                        if (state.leafletMap) {
                            state.leafletMap.setView([lat, lng], 13);
                        }
                    } else {
                        nearbyResults.innerHTML = '<p class="empty-state">未找到附近景点</p>';
                        clearMapMarkers();
                    }
                } catch (error) {
                    nearbyResults.innerHTML = `<p class="empty-state">搜索失败：${escapeHtml(error.message)}</p>`;
                }
            });
        }

        if (useMyLocation || getLocation) {
            const handler = () => {
                if (!navigator.geolocation) {
                    alert("浏览器不支持定位功能");
                    return;
                }
                navigator.geolocation.getCurrentPosition(
                    (pos) => {
                        state.userLocation = {
                            latitude: pos.coords.latitude,
                            longitude: pos.coords.longitude
                        };
                        const latInput = $("#latitude");
                        const lngInput = $("#longitude");
                        if (latInput) latInput.value = pos.coords.latitude.toFixed(4);
                        if (lngInput) lngInput.value = pos.coords.longitude.toFixed(4);
                        if (state.leafletMap) {
                            state.leafletMap.setView([pos.coords.latitude, pos.coords.longitude], 14);
                        }
                    },
                    (error) => {
                        alert("定位失败：" + error.message);
                    }
                );
            };
            if (useMyLocation) useMyLocation.addEventListener("click", handler);
            if (getLocation) getLocation.addEventListener("click", handler);
        }
    }

    async function tryAutoLogin() {
        const savedPhone = localStorage.getItem("huili_phone") || "";
        const savedPassword = localStorage.getItem("huili_password") || "";
        if (!savedPhone || !savedPassword) return false;
        try {
            const result = await apiRequest("/api/login", {
                method: "POST",
                body: JSON.stringify({ phone: savedPhone, password: savedPassword })
            });
            if (result.success) {
                saveSessionId(result.session_id);
                return true;
            }
        } catch (e) {
            localStorage.removeItem("huili_password");
        }
        return false;
    }

    function initAuth() {
        const authOverlay = $("#auth-overlay");
        if (!authOverlay) return;
        const loginForm = $("#login-form");
        const registerForm = $("#register-form");
        const loginError = $("#login-error");
        const registerError = $("#register-error");
        const authTabs = $$(".auth-tab");
        const avatarInput = $("#avatar-input");
        const avatarPreview = $("#avatar-preview");
        const avatarSelectBtn = $("#avatar-select-btn");

        authTabs.forEach((tab) => {
            tab.addEventListener("click", () => {
                authTabs.forEach((t) => t.classList.remove("active"));
                tab.classList.add("active");
                const target = tab.dataset.tab;
                if (loginForm) loginForm.style.display = target === "login" ? "" : "none";
                if (registerForm) registerForm.style.display = target === "register" ? "" : "none";
            });
        });

        if (avatarSelectBtn && avatarInput) {
            avatarSelectBtn.addEventListener("click", () => avatarInput.click());
        }

        if (avatarInput && avatarPreview) {
            avatarInput.addEventListener("change", () => {
                const file = avatarInput.files && avatarInput.files[0];
                if (file) {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        avatarPreview.innerHTML = `<img src="${e.target.result}" style="width:100%;height:100%;object-fit:cover;border-radius:50%">`;
                    };
                    reader.readAsDataURL(file);
                }
            });
        }

        if (loginForm) {
            loginForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                const phone = $("#login-phone")?.value?.trim();
                const password = $("#login-password")?.value;
                if (!phone || !password) {
                    if (loginError) loginError.textContent = "请填写手机号和密码";
                    return;
                }
                try {
                    const result = await apiRequest("/api/login", {
                        method: "POST",
                        body: JSON.stringify({ phone, password })
                    });
                    saveSessionId(result.session_id);
                    localStorage.setItem("huili_phone", phone);
                    localStorage.setItem("huili_password", password);
                    authOverlay.classList.add("hidden");
                    updateUserAvatar();
                } catch (err) {
                    if (loginError) loginError.textContent = err.message;
                }
            });
        }

        if (registerForm) {
            registerForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                const phone = $("#register-phone")?.value?.trim();
                const password = $("#register-password")?.value;
                const confirm = $("#register-confirm")?.value;
                if (!phone || !password) {
                    if (registerError) registerError.textContent = "请填写手机号和密码";
                    return;
                }
                if (password !== confirm) {
                    if (registerError) registerError.textContent = "两次密码不一致";
                    return;
                }
                try {
                    const result = await apiRequest("/api/register", {
                        method: "POST",
                        body: JSON.stringify({ phone, password })
                    });
                    saveSessionId(result.session_id);
                    localStorage.setItem("huili_phone", phone);
                    localStorage.setItem("huili_password", password);
                    if (avatarInput?.files?.[0]) {
                        try { await uploadAvatar(avatarInput.files[0]); } catch (e) {}
                    }
                    authOverlay.classList.add("hidden");
                    updateUserAvatar();
                } catch (err) {
                    if (registerError) registerError.textContent = err.message;
                }
            });
        }
    }

    function initChat() {
        if (!$("#chat-messages")) return;
        const sendButton = $("#send-button");
        const userInput = $("#user-input");
        const clearChatButton = $("#clear-chat");
        const helpBtn = $("#show-help");
        const helpModal = $("#help-modal");
        const surveyBtn = $("#show-survey");
        const surveyModal = $("#survey-modal");
        const surveyStars = $$("#survey-stars .survey-star");
        const surveyComment = $("#survey-comment");
        const submitSurvey = $("#submit-survey");
        const surveyRatingText = $("#survey-rating-text");
        let surveyRating = 0;

        if (sendButton) {
            sendButton.addEventListener("click", () => sendChatMessage());
        }

        if (userInput) {
            userInput.addEventListener("keydown", (e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendChatMessage();
                }
            });
        }

        $$(".recommendation-cards .card").forEach((card) => {
            card.addEventListener("click", () => {
                const query = card.dataset.query;
                if (query) sendChatMessage(query);
            });
        });

        if (clearChatButton) {
            clearChatButton.addEventListener("click", () => {
                const chatMessages = $("#chat-messages");
                if (chatMessages) chatMessages.innerHTML = "";
            });
        }

        if (helpBtn && helpModal) {
            helpBtn.addEventListener("click", (e) => { e.preventDefault(); openModal(helpModal); });
        }

        if (surveyBtn && surveyModal) {
            surveyBtn.addEventListener("click", (e) => { e.preventDefault(); openModal(surveyModal); });
        }

        surveyStars.forEach((star) => {
            star.addEventListener("click", () => {
                surveyRating = Number(star.dataset.value);
                surveyStars.forEach((s, i) => {
                    s.classList.toggle("active", i < surveyRating);
                });
                if (surveyRatingText) {
                    const texts = ["", "非常不满意", "不满意", "一般", "满意", "非常满意"];
                    surveyRatingText.textContent = texts[surveyRating] || "";
                }
                if (submitSurvey) submitSurvey.disabled = false;
            });
        });

        if (submitSurvey) {
            submitSurvey.addEventListener("click", async () => {
                const comment = surveyComment ? surveyComment.value.trim() : "";
                try {
                    await apiRequest("/api/survey", {
                        method: "POST",
                        body: JSON.stringify({ rating: surveyRating, comment, session_id: state.sessionId })
                    });
                    alert("感谢您的反馈！");
                    closeModal(surveyModal);
                } catch (err) {
                    alert("提交失败：" + err.message);
                }
            });
        }
    }

    function initThemeToggle() {
        const themeToggle = $("#theme-toggle");
        if (!themeToggle) return;
        const savedTheme = localStorage.getItem("huili_theme") || "light";
        if (savedTheme === "dark") document.body.classList.add("dark-theme");
        themeToggle.addEventListener("click", () => {
            document.body.classList.toggle("dark-theme");
            const isDark = document.body.classList.contains("dark-theme");
            localStorage.setItem("huili_theme", isDark ? "dark" : "light");
            themeToggle.innerHTML = `<i class="fas ${isDark ? "fa-sun" : "fa-moon"}"></i>`;
        });
    }

    function initLogout() {
        const logoutBtn = $("#logout-btn");
        if (!logoutBtn) return;
        logoutBtn.addEventListener("click", async () => {
            const phone = localStorage.getItem("huili_phone") || "";
            try {
                await apiRequest("/api/logout", {
                    method: "POST",
                    body: JSON.stringify({ phone })
                });
            } catch (e) {}
            localStorage.removeItem("huili_session_id");
            localStorage.removeItem("huili_password");
            state.sessionId = "";
            const authOverlay = $("#auth-overlay");
            if (authOverlay) authOverlay.classList.remove("hidden");
            const chatUserAvatar = document.querySelector(".user-avatar");
            if (chatUserAvatar) chatUserAvatar.innerHTML = '<i class="fas fa-user"></i>';
            const navAvatar = $(".nav-avatar");
            if (navAvatar) navAvatar.innerHTML = '<i class="fas fa-user"></i>';
        });
    }

    function initNavAvatar() {
        const navAvatar = $("#nav-avatar");
        const navAvatarInput = $("#nav-avatar-input");
        if (!navAvatar || !navAvatarInput) return;
        navAvatar.addEventListener("click", () => navAvatarInput.click());
        navAvatarInput.addEventListener("change", async () => {
            const file = navAvatarInput.files && navAvatarInput.files[0];
            if (!file) return;
            try {
                await uploadAvatar(file);
                updateUserAvatar();
                const navAvatarEl = $(".nav-avatar");
                if (navAvatarEl) {
                    const phone = localStorage.getItem("huili_phone") || "";
                    navAvatarEl.innerHTML = `<img src="${API_BASE}/api/avatar/${phone}?t=${Date.now()}" style="width:100%;height:100%;object-fit:cover;border-radius:50%">`;
                }
            } catch (e) {
                alert("头像上传失败: " + e.message);
            }
        });
    }

    function initScenicGallery() {
        const galleryBtn = $("#scenic-gallery-btn");
        const galleryModal = $("#scenic-gallery-modal");
        const galleryGrid = $("#gallery-grid");
        const searchInput = $("#gallery-search-input");
        const searchBtn = $("#gallery-search-btn");
        const tags = $$(".gallery-tag");

        if (galleryBtn && galleryModal) {
            galleryBtn.addEventListener("click", (e) => {
                e.preventDefault();
                openModal(galleryModal);
            });
        }

        async function searchGallery(keyword) {
            if (!galleryGrid) return;
            galleryGrid.innerHTML = '<p class="empty-state">搜索中...</p>';
            try {
                const resp = await fetch(`${API_BASE}/api/scenic_image?place=${encodeURIComponent(keyword)}`);
                if (!resp.ok) throw new Error("请求失败");
                const data = await resp.json();
                if (data.success && data.images && data.images.length > 0) {
                    galleryGrid.innerHTML = data.images.map((img) => {
                        const imgUrl = img.url.startsWith("/") ? `${API_BASE}${img.url}` : img.url;
                        return `
                        <div class="gallery-item" onclick="window.open('${imgUrl}','_blank')">
                            <img src="${imgUrl}" alt="${escapeHtml(img.place_name || keyword)}" loading="lazy">
                            <div class="gallery-item-overlay">
                                <span>${escapeHtml(img.place_name || keyword)}</span>
                            </div>
                        </div>
                    `}).join("");
                } else if (data.success && data.image && data.image.url) {
                    const imgUrl = data.image.url.startsWith("/") ? `${API_BASE}${data.image.url}` : data.image.url;
                    galleryGrid.innerHTML = `
                        <div class="gallery-item" onclick="window.open('${imgUrl}','_blank')">
                            <img src="${imgUrl}" alt="${escapeHtml(data.image.place_name || keyword)}" loading="lazy">
                            <div class="gallery-item-overlay">
                                <span>${escapeHtml(data.image.place_name || keyword)}</span>
                            </div>
                        </div>
                    `;
                } else {
                    galleryGrid.innerHTML = '<p class="empty-state">未找到相关景区图片</p>';
                }
            } catch (e) {
                galleryGrid.innerHTML = '<p class="empty-state">搜索失败，请重试</p>';
            }
        }

        tags.forEach((tag) => {
            tag.addEventListener("click", () => {
                tags.forEach((t) => t.classList.remove("active"));
                tag.classList.add("active");
                const keyword = tag.dataset.keyword;
                if (searchInput) searchInput.value = keyword;
                searchGallery(keyword);
            });
        });

        if (searchBtn) {
            searchBtn.addEventListener("click", () => {
                const keyword = searchInput ? searchInput.value.trim() : "";
                if (keyword) searchGallery(keyword);
            });
        }

        if (searchInput) {
            searchInput.addEventListener("keydown", (e) => {
                if (e.key === "Enter") {
                    const keyword = searchInput.value.trim();
                    if (keyword) searchGallery(keyword);
                }
            });
        }
    }

    function initAdminInterface() {
        const adminLogin = $("#admin-login");
        const adminContent = $("#admin-content");
        const adminPasswordInput = $("#admin-password");
        const adminLoginBtn = $("#admin-login-btn");
        const adminLoginError = $("#admin-login-error");

        if (adminLoginBtn) {
            adminLoginBtn.addEventListener("click", () => {
                const pwd = adminPasswordInput ? adminPasswordInput.value : "";
                if (pwd === state.adminPassword) {
                    if (adminLogin) adminLogin.style.display = "none";
                    if (adminContent) adminContent.style.display = "";
                } else {
                    if (adminLoginError) adminLoginError.textContent = "密码错误";
                }
            });
        }

        const rebuildBtn = $("#rebuild-kb");
        const confirmRebuild = $("#confirm-rebuild");
        if (rebuildBtn) {
            rebuildBtn.addEventListener("click", () => openModal($("#rebuild-modal")));
        }
        if (confirmRebuild) {
            confirmRebuild.addEventListener("click", async () => {
                try {
                    const result = await apiRequest("/api/admin/rebuild", {
                        method: "POST",
                        headers: {
                            "X-Admin-User": localStorage.getItem("huili_admin_user") || "",
                            "X-Admin-Password": localStorage.getItem("huili_admin_pwd") || ""
                        }
                    });
                    alert(result.message || "知识库重建完成");
                    closeModal($("#rebuild-modal"));
                } catch (error) {
                    alert(`重建失败：${error.message}`);
                }
            });
        }

        const fileInput = $("#modal-file-input");
        const uploadBtn = $("#upload-file-btn");
        if (uploadBtn && fileInput) {
            uploadBtn.addEventListener("click", async () => {
                const file = fileInput.files && fileInput.files[0];
                if (!file) { alert("请选择文件"); return; }
                const formData = new FormData();
                    formData.append("files", file);
                try {
                    const response = await fetch(`${API_BASE}/api/admin/upload`, {
                        method: "POST",
                            headers: {
                                "X-Admin-User": localStorage.getItem("huili_admin_user") || "",
                                "X-Admin-Password": localStorage.getItem("huili_admin_pwd") || ""
                            },
                        body: formData
                    });
                    const result = await response.json();
                    if (!response.ok || !result.success) {
                        throw new Error(result.error || "上传失败");
                    }
                    alert(result.message || "上传成功");
                } catch (error) {
                    alert(`上传失败：${error.message}`);
                }
            });
        }
    }

    async function init() {
        bindModalEvents();
        initAuth();
        initChat();
        initLive2DScene();
        initVoiceInput();
        initNearbyAttractions();
        initThemeToggle();
        initLogout();
        initNavAvatar();
        initScenicGallery();

        const authOverlay = $("#auth-overlay");
        if (authOverlay) {
            const autoLoggedIn = await tryAutoLogin();
            if (autoLoggedIn) {
                authOverlay.classList.add("hidden");
                updateUserAvatar();
            }
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    window.initAdminInterface = initAdminInterface;
})();
