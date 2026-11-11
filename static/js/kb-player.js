/*
 * Свой плеер KinoBudka.
 *
 * Плеер не решает сам, играть или нет: у комнаты есть общий «таймлайн»
 * (играет / пауза, секунда, скорость), и плеер каждого зрителя под него подстраивается.
 * Менять таймлайн может только админ комнаты — его кнопки отправляют команды на сервер,
 * сервер рассылает новое состояние всем. У остальных кнопок управления видео просто нет.
 *
 * Источники: YouTube (через официальный IFrame API), видеофайл или поток HLS
 * (обычный <video>), встроенный сторонний плеер (iframe — им управлять нельзя).
 */
(function () {
    'use strict';

    var RATES = [0.5, 0.75, 1, 1.25, 1.5, 2];
    var TICK = 250;                 // как часто сверяемся с таймлайном, мс
    var HARD_DRIFT_VIDEO = 1.0;     // отставание, после которого <video> перематывается, с
    var HARD_DRIFT_YOUTUBE = 1.25;  // то же для YouTube (у него нет плавной подстройки скорости)
    var SOFT_DRIFT = 0.15;          // отставание, с которого <video> плавно догоняет скоростью, с
    var MAX_LEAD = 6;               // наибольшее упреждение при перемотке на медленной сети, с
    var PASSTHROUGH_TIME = 10000;   // сколько можно кликать по самому плееру YouTube, мс

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function icon(name) {
        return '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-' + name + '"></use></svg>';
    }

    function el(tag, className, html) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (html) node.innerHTML = html;
        return node;
    }

    function formatTime(seconds) {
        if (!isFinite(seconds) || seconds < 0) seconds = 0;
        seconds = Math.floor(seconds);
        var h = Math.floor(seconds / 3600);
        var m = Math.floor((seconds % 3600) / 60);
        var s = seconds % 60;
        var tail = (s < 10 ? '0' : '') + s;
        if (h > 0) return h + ':' + (m < 10 ? '0' : '') + m + ':' + tail;
        return m + ':' + tail;
    }

    function formatRate(rate) {
        return String(rate).replace('.', ',') + '×';
    }

    var store = {
        get: function (key, fallback) {
            try {
                var value = window.localStorage.getItem('kinobudka.' + key);
                return value === null ? fallback : JSON.parse(value);
            } catch (e) {
                return fallback;
            }
        },
        set: function (key, value) {
            try {
                window.localStorage.setItem('kinobudka.' + key, JSON.stringify(value));
            } catch (e) { /* хранилище недоступно — не страшно */ }
        }
    };

    var scripts = {};

    function loadScript(url) {
        if (!scripts[url]) {
            scripts[url] = new Promise(function (resolve, reject) {
                var script = document.createElement('script');
                script.src = url;
                script.onload = resolve;
                script.onerror = function () {
                    delete scripts[url];
                    reject(new Error('script'));
                };
                document.head.appendChild(script);
            });
        }
        return scripts[url];
    }

    /* ------------------------------------------------------------------
     * Драйверы источников. У всех одинаковый набор свойств и методов:
     * ready, started, paused, ended, buffering, time, duration, buffered,
     * play(), pause(), seek(), setRate(), setVolume(), setMuted(), destroy()
     * ------------------------------------------------------------------ */

    // Видеофайл или поток HLS через обычный <video>
    function VideoDriver(host, source, emit, options) {
        var self = this;
        this.kind = 'video';
        this.emit = emit;
        this.canNudge = true;         // можно плавно догонять, чуть меняя скорость
        this.seekBeforeStart = true;  // можно показать нужный кадр, не запуская видео
        this.passive = false;
        this.ready = false;
        this.started = false;
        this.live = false;
        this._waiting = false;
        this._dead = false;

        var video = this.video = document.createElement('video');
        video.className = 'kb-media';
        video.preload = 'auto';
        video.controls = false;
        video.playsInline = true;
        video.setAttribute('playsinline', '');
        video.disableRemotePlayback = true;
        host.appendChild(video);

        function on(name, handler) {
            video.addEventListener(name, handler);
        }

        on('loadedmetadata', function () {
            self.ready = true;
            self.live = video.duration === Infinity;
            emit('ready');
            emit('meta');
        });
        on('durationchange', function () {
            self.live = video.duration === Infinity;
            emit('meta');
        });
        on('playing', function () {
            self.started = true;
            self._waiting = false;
            emit('change');
        });
        on('waiting', function () {
            self._waiting = true;
            emit('change');
        });
        on('canplay', function () {
            self._waiting = false;
            emit('change');
        });
        on('pause', function () { emit('change'); });
        on('seeked', function () { emit('change'); });
        on('ended', function () { emit('ended'); });
        on('error', function () {
            if (self._hls) return;  // ошибки потока разбирает hls.js
            var code = video.error ? video.error.code : 0;
            var text = 'Не удалось загрузить видео.';
            if (code === 2) text = 'Видео не загрузилось: проблема с сетью.';
            if (code === 3) text = 'Браузер не смог воспроизвести это видео (неподдерживаемый кодек).';
            if (code === 4) text = 'Этот файл или ссылку браузер открыть не может. Лучше всего подходит MP4 (H.264 + AAC).';
            emit('error', text);
        });

        if (source.hls) {
            this._startHls(source.src, options.hlsUrl);
        } else {
            video.src = source.src;
        }
    }

    VideoDriver.prototype._startHls = function (src, hlsUrl) {
        var self = this;
        var video = this.video;
        var native = video.canPlayType('application/vnd.apple.mpegurl');

        function useNative() {
            if (native) {
                video.src = src;
            } else {
                self.emit('error', 'Этот браузер не умеет воспроизводить потоки .m3u8.');
            }
        }

        if (!hlsUrl) return useNative();
        loadScript(hlsUrl).then(function () {
            if (self._dead) return;
            var Hls = window.Hls;
            if (!Hls || !Hls.isSupported()) return useNative();
            var hls = self._hls = new Hls({enableWorker: true});
            var recovered = 0;
            hls.on(Hls.Events.LEVEL_LOADED, function (event, data) {
                self.live = !!(data.details && data.details.live);
            });
            hls.on(Hls.Events.ERROR, function (event, data) {
                if (!data.fatal) return;
                if (data.type === Hls.ErrorTypes.MEDIA_ERROR && recovered < 2) {
                    recovered += 1;
                    hls.recoverMediaError();
                    return;
                }
                var text = 'Поток не загрузился.';
                if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
                    text = 'Поток не загрузился: сервер недоступен или не разрешает показ на других сайтах.';
                }
                hls.destroy();
                self._hls = null;
                self.emit('error', text);
            });
            hls.loadSource(src);
            hls.attachMedia(video);
        }).catch(useNative);
    };

    Object.defineProperties(VideoDriver.prototype, {
        paused: {get: function () { return this.video.paused || this.video.ended; }},
        ended: {get: function () { return this.video.ended; }},
        buffering: {get: function () { return this.video.seeking || (this._waiting && !this.video.paused); }},
        time: {get: function () { return this.video.currentTime || 0; }},
        duration: {
            get: function () {
                var duration = this.video.duration;
                if (duration === Infinity) return Infinity;
                return isFinite(duration) ? duration : 0;
            }
        },
        buffered: {
            get: function () {
                var ranges = this.video.buffered;
                var now = this.video.currentTime;
                for (var i = 0; i < ranges.length; i++) {
                    if (ranges.start(i) <= now + 0.5 && now <= ranges.end(i)) return ranges.end(i);
                }
                return 0;
            }
        },
        rate: {get: function () { return this.video.playbackRate; }},
        title: {get: function () { return ''; }}
    });

    VideoDriver.prototype.play = function () {
        var promise;
        try {
            promise = this.video.play();
        } catch (e) {
            return Promise.resolve(true);
        }
        if (!promise || !promise.then) return Promise.resolve(true);
        return promise.then(function () {
            return true;
        }, function (error) {
            // NotAllowedError — браузер запретил запуск со звуком без клика по странице
            return !(error && error.name === 'NotAllowedError');
        });
    };
    VideoDriver.prototype.pause = function () { this.video.pause(); };
    VideoDriver.prototype.seek = function (time) {
        try {
            this.video.currentTime = time;
        } catch (e) { /* метаданные ещё не загружены */ }
    };
    VideoDriver.prototype.setRate = function (rate) {
        if (Math.abs(this.video.playbackRate - rate) > 0.001) this.video.playbackRate = rate;
    };
    VideoDriver.prototype.setVolume = function (volume) { this.video.volume = clamp(volume, 0, 1); };
    VideoDriver.prototype.setMuted = function (muted) { this.video.muted = !!muted; };
    VideoDriver.prototype.destroy = function () {
        this._dead = true;
        if (this._hls) {
            this._hls.destroy();
            this._hls = null;
        }
        try {
            this.video.pause();
            this.video.removeAttribute('src');
            this.video.load();
        } catch (e) { /* уже выгружено */ }
        this.video.remove();
    };

    // YouTube через официальный IFrame API
    var youtubeApi = null;

    function loadYouTubeApi() {
        if (window.YT && window.YT.Player) return Promise.resolve(window.YT);
        if (youtubeApi) return youtubeApi;
        youtubeApi = new Promise(function (resolve, reject) {
            var previous = window.onYouTubeIframeAPIReady;
            var timer = setTimeout(function () {
                youtubeApi = null;
                reject(new Error('timeout'));
            }, 20000);
            window.onYouTubeIframeAPIReady = function () {
                clearTimeout(timer);
                if (typeof previous === 'function') previous();
                resolve(window.YT);
            };
            var script = document.createElement('script');
            script.src = 'https://www.youtube.com/iframe_api';
            script.onerror = function () {
                clearTimeout(timer);
                youtubeApi = null;
                reject(new Error('network'));
            };
            document.head.appendChild(script);
        });
        return youtubeApi;
    }

    function YouTubeDriver(host, source, emit) {
        var self = this;
        this.kind = 'youtube';
        this.emit = emit;
        this.canNudge = false;
        this.seekBeforeStart = false;  // перемотка незапущенного ролика сразу запускает его
        this.passive = false;
        this.ready = false;
        this.started = false;
        this.state = -1;
        this._dead = false;
        this._lastTime = 0;
        this._lastAt = 0;

        this.box = el('div', 'kb-media');
        var mount = el('div');
        this.box.appendChild(mount);
        host.appendChild(this.box);

        loadYouTubeApi().then(function (YT) {
            if (self._dead) return;
            self.player = new YT.Player(mount, {
                width: '100%',
                height: '100%',
                videoId: source.id,
                playerVars: {
                    autoplay: 0,
                    controls: 0,       // свои кнопки вместо кнопок YouTube
                    disablekb: 1,
                    fs: 0,
                    rel: 0,
                    iv_load_policy: 3,
                    playsinline: 1,
                    enablejsapi: 1,
                    origin: window.location.origin
                },
                events: {
                    onReady: function () {
                        if (self._dead) return;
                        self.ready = true;
                        emit('ready');
                        emit('meta');
                    },
                    onStateChange: function (event) {
                        if (self._dead) return;
                        self.state = event.data;
                        if (event.data === 1) self.started = true;
                        emit('meta');
                        if (event.data === 0) emit('ended');
                        emit('change');
                    },
                    onError: function (event) {
                        var code = event.data;
                        var text = 'YouTube не смог показать это видео.';
                        if (code === 2) text = 'Неверная ссылка на видео YouTube.';
                        if (code === 100) text = 'Видео не найдено: оно удалено или закрыто.';
                        if (code === 101 || code === 150) text = 'Автор запретил показывать это видео на других сайтах.';
                        emit('error', text);
                    }
                }
            });
        }).catch(function () {
            if (!self._dead) emit('error', 'Не удалось загрузить плеер YouTube. Проверьте подключение к интернету.');
        });
    }

    YouTubeDriver.prototype._call = function (method, fallback) {
        try {
            if (this.player && typeof this.player[method] === 'function') {
                var args = Array.prototype.slice.call(arguments, 2);
                var result = this.player[method].apply(this.player, args);
                return result === undefined ? fallback : result;
            }
        } catch (e) { /* плеер ещё не готов */ }
        return fallback;
    };

    Object.defineProperties(YouTubeDriver.prototype, {
        // 1 — играет, 3 — буферизация; остальное (не начат, пауза, конец) считаем паузой
        paused: {get: function () { return this.state !== 1 && this.state !== 3; }},
        ended: {get: function () { return this.state === 0; }},
        buffering: {get: function () { return this.state === 3; }},
        time: {
            get: function () {
                var time = Number(this._call('getCurrentTime', 0)) || 0;
                var now = performance.now();
                if (time !== this._lastTime) {
                    this._lastTime = time;
                    this._lastAt = now;
                    return time;
                }
                // YouTube обновляет время не каждый кадр — между обновлениями досчитываем сами
                if (this.state === 1) return time + Math.min((now - this._lastAt) / 1000, 0.6) * this.rate;
                return time;
            }
        },
        duration: {get: function () { return Number(this._call('getDuration', 0)) || 0; }},
        buffered: {get: function () { return (Number(this._call('getVideoLoadedFraction', 0)) || 0) * this.duration; }},
        rate: {get: function () { return Number(this._call('getPlaybackRate', 1)) || 1; }},
        live: {
            get: function () {
                var data = this._call('getVideoData', null);
                return !!(data && data.isLive);
            }
        },
        title: {
            get: function () {
                var data = this._call('getVideoData', null);
                return (data && data.title) || '';
            }
        }
    });

    YouTubeDriver.prototype.play = function () {
        this._call('playVideo');
        return Promise.resolve(true);  // запретил ли браузер автозапуск, проверяет сам плеер по таймеру
    };
    YouTubeDriver.prototype.pause = function () { this._call('pauseVideo'); };
    YouTubeDriver.prototype.seek = function (time) {
        this._lastAt = 0;
        this._call('seekTo', undefined, time, true);
    };
    YouTubeDriver.prototype.setRate = function (rate) {
        if (Math.abs(this.rate - rate) > 0.001) this._call('setPlaybackRate', undefined, rate);
    };
    YouTubeDriver.prototype.setVolume = function (volume) {
        this._call('setVolume', undefined, Math.round(clamp(volume, 0, 1) * 100));
    };
    YouTubeDriver.prototype.setMuted = function (muted) { this._call(muted ? 'mute' : 'unMute'); };
    YouTubeDriver.prototype.destroy = function () {
        this._dead = true;
        this._call('destroy');
        this.box.remove();
    };

    // Сторонний встроенный плеер: просто iframe, управлять им снаружи нельзя
    function EmbedDriver(host, source) {
        this.kind = 'embed';
        this.passive = true;
        this.ready = true;
        this.started = false;
        this.frame = document.createElement('iframe');
        this.frame.className = 'kb-media';
        this.frame.src = source.src;
        this.frame.allow = 'autoplay; fullscreen; encrypted-media; picture-in-picture';
        this.frame.allowFullscreen = true;
        this.frame.setAttribute('frameborder', '0');
        host.appendChild(this.frame);
    }

    EmbedDriver.prototype.destroy = function () { this.frame.remove(); };

    /* ------------------------------------------------------------------
     * Сам плеер: кнопки, подстройка под таймлайн комнаты
     * ------------------------------------------------------------------ */

    function KBPlayer(root, options) {
        this.root = root;
        this.options = options || {};
        this.isAdmin = !!this.options.admin;
        this.adminName = this.options.adminName || '';
        this.driver = null;
        this.source = null;
        this.timeline = {playing: false, pos: 0, rate: 1, at: performance.now()};
        this.volume = clamp(Number(store.get('volume', 1)) || 0, 0, 1);
        this.muted = !!store.get('muted', false);
        this._activated = false;      // был ли клик по странице (без него браузер не даст включить звук)
        this._seeking = false;        // админ тянет ползунок перемотки
        this._holdUntil = 0;          // после перемотки ждём, прежде чем снова сверяться
        this._playRetryAt = 0;
        this._playAskedAt = 0;
        this._lead = 0;               // упреждение при перемотке: сколько секунд уходит на подгрузку
        this._seekTries = 0;          // сколько перемоток подряд не помогли догнать таймлайн
        this._landing = false;        // ждём первую сверку после перемотки
        this._silent = false;         // запустили без звука из-за запрета браузера

        this._build();
        this._bind();
        this.setAdmin(this.isAdmin);

        var self = this;
        this._timer = setInterval(function () { self._tick(); }, TICK);
    }

    KBPlayer.prototype._build = function () {
        var root = this.root;
        root.classList.add('kb-player');
        root.innerHTML = '';

        this.stage = root.appendChild(el('div', 'kb-stage'));
        this.shield = root.appendChild(el('div', 'kb-shield'));
        this.spinner = root.appendChild(el('div', 'kb-spinner'));
        this.spinner.hidden = true;

        this.bigPlay = root.appendChild(el('button', 'kb-bigplay', icon('play')));
        this.bigPlay.type = 'button';
        this.bigPlay.setAttribute('aria-label', 'Запустить видео');
        this.bigPlay.hidden = true;

        this.waitNote = root.appendChild(el('div', 'kb-wait'));
        this.waitNote.hidden = true;

        this.top = root.appendChild(el('div', 'kb-top'));
        this.chip = this.top.appendChild(el('span', 'kb-chip'));

        this.toast = root.appendChild(el('button', 'kb-toast'));
        this.toast.type = 'button';
        this.toast.hidden = true;

        this.gate = root.appendChild(el('div', 'kb-overlay kb-gate',
            '<button type="button" class="btn btn-primary btn-lg">' + icon('play') + '<span>Присоединиться к просмотру</span></button>' +
            '<p>Нажмите, чтобы видео и звук включались вместе со всеми</p>'));
        this.gate.hidden = true;

        this.error = root.appendChild(el('div', 'kb-overlay kb-error', icon('alert') + '<p></p>'));
        this.error.hidden = true;

        var bar = this.bar = root.appendChild(el('div', 'kb-bar'));

        var progress = bar.appendChild(el('div', 'kb-progress'));
        this.seek = progress.appendChild(el('input', 'kb-seek'));
        this.seek.type = 'range';
        this.seek.min = '0';
        this.seek.max = '1000';
        this.seek.step = '1';
        this.seek.value = '0';
        this.seek.setAttribute('aria-label', 'Перемотка');
        this.tip = progress.appendChild(el('span', 'kb-tip'));
        this.tip.hidden = true;

        var controls = bar.appendChild(el('div', 'kb-controls'));

        this.playButton = controls.appendChild(el('button', 'kb-btn kb-admin-only', icon('play')));
        this.playButton.type = 'button';
        this.playButton.title = 'Пуск / пауза (пробел)';

        this.backButton = controls.appendChild(el('button', 'kb-btn kb-admin-only kb-wide-only', icon('back10')));
        this.backButton.type = 'button';
        this.backButton.title = 'Назад на 10 секунд';

        this.forwardButton = controls.appendChild(el('button', 'kb-btn kb-admin-only kb-wide-only', icon('fwd10')));
        this.forwardButton.type = 'button';
        this.forwardButton.title = 'Вперёд на 10 секунд';

        this.timeLabel = controls.appendChild(el('span', 'kb-time'));
        this.timeLabel.textContent = '0:00 / 0:00';

        this.rateNote = controls.appendChild(el('span', 'kb-ratenote kb-guest-only'));
        this.rateNote.hidden = true;

        controls.appendChild(el('span', 'kb-spacer'));

        this.passButton = controls.appendChild(el('button', 'kb-btn kb-youtube-only', icon('pointer')));
        this.passButton.type = 'button';
        this.passButton.title = 'Кликнуть по самому плееру YouTube (например, пропустить рекламу)';

        var rateBox = this.rateBox = controls.appendChild(el('div', 'kb-ratebox kb-admin-only'));
        this.rateButton = rateBox.appendChild(el('button', 'kb-btn kb-rate'));
        this.rateButton.type = 'button';
        this.rateButton.title = 'Скорость';
        this.rateButton.textContent = formatRate(1);
        this.rateMenu = rateBox.appendChild(el('div', 'kb-menu'));
        this.rateMenu.hidden = true;
        for (var i = 0; i < RATES.length; i++) {
            var item = this.rateMenu.appendChild(el('button', 'kb-menu-item'));
            item.type = 'button';
            item.dataset.rate = String(RATES[i]);
            item.textContent = RATES[i] === 1 ? 'Обычная' : formatRate(RATES[i]);
        }

        this.muteButton = controls.appendChild(el('button', 'kb-btn', icon('volume')));
        this.muteButton.type = 'button';
        this.muteButton.title = 'Звук (M)';

        this.volumeSlider = controls.appendChild(el('input', 'kb-volume'));
        this.volumeSlider.type = 'range';
        this.volumeSlider.min = '0';
        this.volumeSlider.max = '100';
        this.volumeSlider.step = '1';
        this.volumeSlider.setAttribute('aria-label', 'Громкость');

        this.fullButton = controls.appendChild(el('button', 'kb-btn', icon('fullscreen')));
        this.fullButton.type = 'button';
        this.fullButton.title = 'Во весь экран (F)';

        this._renderVolume();
        this._renderChip();
    };

    KBPlayer.prototype._bind = function () {
        var self = this;
        var root = this.root;

        // любой клик или клавиша на странице — браузер после этого разрешает звук
        function activate() { self._activated = true; }
        document.addEventListener('pointerdown', activate, true);
        document.addEventListener('keydown', activate, true);

        this.gate.querySelector('button').addEventListener('click', function () {
            self._activated = true;
            self.gate.hidden = true;
            self._playRetryAt = 0;
            self._tick();
        });

        // клик по видео: у админа — пуск/пауза, двойной клик у всех — полный экран
        var clickTimer = null;
        this.shield.addEventListener('click', function () {
            self._wake();
            if (clickTimer) {
                clearTimeout(clickTimer);
                clickTimer = null;
                self.toggleFullscreen();
                return;
            }
            clickTimer = setTimeout(function () {
                clickTimer = null;
                if (self.isAdmin) self.togglePlay();
            }, 220);
        });
        this.shield.addEventListener('contextmenu', function (event) { event.preventDefault(); });

        this.bigPlay.addEventListener('click', function () { self.togglePlay(); });
        this.playButton.addEventListener('click', function () { self.togglePlay(); });
        this.backButton.addEventListener('click', function () { self.skip(-10); });
        this.forwardButton.addEventListener('click', function () { self.skip(10); });

        // перемотка: пока тянем — показываем время, отпустили — отправляем команду
        this.seek.addEventListener('input', function () {
            if (!self.isAdmin) return;
            self._seeking = true;
            self._renderSeek(self.seek.value / 1000);
        });
        this.seek.addEventListener('change', function () {
            if (!self.isAdmin) return;
            self._seeking = false;
            var duration = self._duration();
            if (duration) self.seekTo(self.seek.value / 1000 * duration);
        });
        this.seek.addEventListener('pointermove', function (event) {
            var duration = self._duration();
            if (!duration) return;
            var box = self.seek.getBoundingClientRect();
            var share = clamp((event.clientX - box.left) / box.width, 0, 1);
            self.tip.textContent = formatTime(share * duration);
            self.tip.style.left = (share * 100) + '%';
            self.tip.hidden = false;
        });
        this.seek.addEventListener('pointerleave', function () { self.tip.hidden = true; });

        this.rateButton.addEventListener('click', function (event) {
            event.stopPropagation();
            self.rateMenu.hidden = !self.rateMenu.hidden;
        });
        this.rateMenu.addEventListener('click', function (event) {
            var item = event.target.closest('.kb-menu-item');
            if (!item) return;
            self.rateMenu.hidden = true;
            self.setRate(Number(item.dataset.rate));
        });
        document.addEventListener('click', function (event) {
            if (!self.rateBox.contains(event.target)) self.rateMenu.hidden = true;
        });

        this.muteButton.addEventListener('click', function () { self.toggleMute(); });
        this.volumeSlider.addEventListener('input', function () {
            self.setVolume(self.volumeSlider.value / 100);
        });
        this.fullButton.addEventListener('click', function () { self.toggleFullscreen(); });
        this.passButton.addEventListener('click', function () { self._passthrough(); });

        this.toast.addEventListener('click', function () {
            // «включить звук» после автозапуска без звука
            self._silent = false;
            self.toast.hidden = true;
            self._applyVolume();
        });

        document.addEventListener('fullscreenchange', function () {
            var full = document.fullscreenElement === root;
            root.classList.toggle('is-fullscreen', full);
            self.fullButton.innerHTML = icon(full ? 'fullscreen-exit' : 'fullscreen');
        });

        // панель с кнопками прячется, пока видео идёт и мышь не двигается
        root.addEventListener('pointermove', function () { self._wake(); });
        root.addEventListener('pointerleave', function () { root.classList.remove('is-awake'); });

        document.addEventListener('keydown', function (event) { self._onKey(event); });

        // медиа-клавиши на клавиатуре и гарнитуре: у зрителей не делают ничего
        if (navigator.mediaSession && navigator.mediaSession.setActionHandler) {
            var actions = {
                play: function () { if (self.isAdmin && !self.timeline.playing) self.togglePlay(); },
                pause: function () { if (self.isAdmin && self.timeline.playing) self.togglePlay(); },
                stop: function () { if (self.isAdmin && self.timeline.playing) self.togglePlay(); },
                seekbackward: function () { self.skip(-10); },
                seekforward: function () { self.skip(10); },
                seekto: function (details) {
                    if (details && typeof details.seekTime === 'number') self.seekTo(details.seekTime);
                }
            };
            Object.keys(actions).forEach(function (name) {
                try {
                    navigator.mediaSession.setActionHandler(name, actions[name]);
                } catch (e) { /* действие не поддерживается */ }
            });
        }
    };

    KBPlayer.prototype._onKey = function (event) {
        if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
        var target = event.target || {};
        var tag = target.tagName;
        var slider = tag === 'INPUT' && target.type === 'range';
        if (target.isContentEditable || tag === 'TEXTAREA' || tag === 'SELECT' || (tag === 'INPUT' && !slider)) {
            return;  // в полях ввода не мешаем печатать
        }
        if (!this.driver || this.driver.passive) return;
        var code = event.code;
        // пробел на кнопке нажимает саму кнопку, стрелки на ползунке двигают ползунок
        if (code === 'Space' && (tag === 'BUTTON' || tag === 'A')) return;
        if (slider && code.indexOf('Arrow') === 0) return;
        var handled = true;
        switch (code) {
            case 'Space':
            case 'KeyK': this.togglePlay(); break;
            case 'ArrowLeft': this.skip(-5); break;
            case 'ArrowRight': this.skip(5); break;
            case 'KeyJ': this.skip(-10); break;
            case 'KeyL': this.skip(10); break;
            case 'KeyM': this.toggleMute(); break;
            case 'KeyF': this.toggleFullscreen(); break;
            case 'ArrowUp': this.setVolume(this.volume + 0.05); break;
            case 'ArrowDown': this.setVolume(this.volume - 0.05); break;
            default: handled = false;
        }
        if (handled) {
            event.preventDefault();
            this._wake();
        }
    };

    KBPlayer.prototype._wake = function () {
        var root = this.root;
        root.classList.add('is-awake');
        clearTimeout(this._sleepTimer);
        this._sleepTimer = setTimeout(function () { root.classList.remove('is-awake'); }, 2800);
    };

    /* ---------- что вызывает страница комнаты ---------- */

    // Загрузить новый источник (при входе в комнату и когда админ сменил видео)
    KBPlayer.prototype.load = function (source) {
        var self = this;
        if (this.driver) this.driver.destroy();
        this.driver = null;
        this.source = source;
        this.stage.innerHTML = '';
        this.error.hidden = true;
        this.toast.hidden = true;
        this.gate.hidden = true;
        this._silent = false;
        this._holdUntil = 0;
        this._playRetryAt = 0;
        this._playAskedAt = 0;
        this._lead = 0;
        this._seekTries = 0;
        this._landing = false;
        this._nudging = false;
        this._metaSent = '';
        this.root.dataset.kind = source.kind;
        this.root.classList.remove('is-passthrough');

        function emit(type, payload) {
            if (self.driver !== driver) return;  // событие от уже заменённого источника
            self._onDriver(type, payload);
        }

        var driver;
        if (source.kind === 'youtube') {
            driver = new YouTubeDriver(this.stage, source, emit);
        } else if (source.kind === 'embed') {
            driver = new EmbedDriver(this.stage, source);
        } else {
            driver = new VideoDriver(this.stage, source, emit, {hlsUrl: this.options.hlsUrl});
        }
        this.driver = driver;
        this._render();
    };

    // Новое состояние таймлайна от сервера
    KBPlayer.prototype.setTimeline = function (state) {
        this.timeline = {
            playing: !!state.playing,
            pos: Number(state.pos) || 0,
            rate: Number(state.rate) || 1,
            at: performance.now()
        };
        this._playRetryAt = 0;
        if (!state.playing) this._playAskedAt = 0;
        this._seekTries = 0;
        this._holdUntil = 0;
        this._tick();
    };

    KBPlayer.prototype.setAdmin = function (isAdmin) {
        this.isAdmin = !!isAdmin;
        this.root.classList.toggle('is-admin', this.isAdmin);
        this.seek.disabled = !this.isAdmin;
        if (!this.isAdmin) this.rateMenu.hidden = true;
        this._metaSent = '';
        this._renderChip();
        this._render();
        if (this.driver && this.driver.ready && !this.driver.passive) this._sendMeta();
    };

    KBPlayer.prototype.setAdminName = function (name) {
        this.adminName = name || '';
        this._renderChip();
    };

    /* ---------- команды админа ---------- */

    KBPlayer.prototype._duration = function () {
        var duration = this.driver && !this.driver.passive ? this.driver.duration : 0;
        return isFinite(duration) && duration > 0 ? duration : 0;
    };

    // Где сейчас должно быть видео по таймлайну комнаты
    KBPlayer.prototype.target = function () {
        var timeline = this.timeline;
        var position = timeline.pos;
        if (timeline.playing) position += (performance.now() - timeline.at) / 1000 * timeline.rate;
        var duration = this._duration();
        if (duration) position = Math.min(position, duration);
        return Math.max(0, position);
    };

    KBPlayer.prototype._position = function () {
        var driver = this.driver;
        if (driver && !driver.passive && driver.ready && driver.started) return driver.time;
        return this.target();
    };

    KBPlayer.prototype._command = function (command) {
        if (!this.isAdmin || !this.driver || this.driver.passive) return;
        // сразу применяем у себя, чтобы кнопки отзывались мгновенно; сервер разошлёт то же всем
        var timeline = this.timeline;
        this.setTimeline({
            playing: command.action === 'play' ? true : command.action === 'pause' ? false : timeline.playing,
            pos: command.pos,
            rate: command.action === 'rate' ? command.rate : timeline.rate
        });
        if (this.options.onCommand) this.options.onCommand(command);
    };

    KBPlayer.prototype.togglePlay = function () {
        if (!this.isAdmin || !this.driver || this.driver.passive) return;
        var duration = this._duration();
        var position = this._position();
        var atEnd = duration && position >= duration - 0.5;
        if (this.timeline.playing && !atEnd) {
            this._command({action: 'pause', pos: position});
        } else {
            this._command({action: 'play', pos: atEnd ? 0 : position});
        }
    };

    KBPlayer.prototype.seekTo = function (position) {
        var duration = this._duration();
        position = clamp(position, 0, duration || position);
        this._command({action: 'seek', pos: position});
    };

    KBPlayer.prototype.skip = function (seconds) {
        if (!this.isAdmin) return;
        this.seekTo(this._position() + seconds);
    };

    KBPlayer.prototype.setRate = function (rate) {
        this._command({action: 'rate', rate: rate, pos: this._position()});
    };

    /* ---------- своё у каждого зрителя: звук и полный экран ---------- */

    KBPlayer.prototype.setVolume = function (volume) {
        this.volume = clamp(volume, 0, 1);
        if (this.volume > 0) this.muted = false;
        store.set('volume', this.volume);
        store.set('muted', this.muted);
        this._silent = false;
        this.toast.hidden = true;
        this._applyVolume();
    };

    KBPlayer.prototype.toggleMute = function () {
        this.muted = !this.muted;
        if (!this.muted && this.volume === 0) this.volume = 0.5;
        store.set('volume', this.volume);
        store.set('muted', this.muted);
        this._silent = false;
        this.toast.hidden = true;
        this._applyVolume();
    };

    KBPlayer.prototype._applyVolume = function () {
        var driver = this.driver;
        if (driver && driver.ready && !driver.passive) {
            driver.setVolume(this.volume);
            driver.setMuted(this.muted || this._silent);
        }
        this._renderVolume();
    };

    KBPlayer.prototype._renderVolume = function () {
        var silent = this.muted || this.volume === 0;
        var name = silent ? 'mute' : this.volume < 0.5 ? 'volume-low' : 'volume';
        this.muteButton.innerHTML = icon(name);
        var value = silent ? 0 : Math.round(this.volume * 100);
        this.volumeSlider.value = String(value);
        this.volumeSlider.style.setProperty('--value', value + '%');
    };

    KBPlayer.prototype.toggleFullscreen = function () {
        if (document.fullscreenElement) {
            document.exitFullscreen();
        } else if (this.root.requestFullscreen) {
            this.root.requestFullscreen().catch(function () { /* браузер не разрешил */ });
        }
    };

    // Ненадолго разрешаем клики по самому плееру YouTube: нажать «Пропустить рекламу» и т.п.
    KBPlayer.prototype._passthrough = function () {
        var self = this;
        this.root.classList.add('is-passthrough');
        this._showToast('10 секунд можно кликать по самому плееру YouTube', 4000);
        clearTimeout(this._passTimer);
        this._passTimer = setTimeout(function () {
            self.root.classList.remove('is-passthrough');
        }, PASSTHROUGH_TIME);
    };

    KBPlayer.prototype._showToast = function (text, time) {
        var toast = this.toast;
        toast.textContent = text;
        toast.hidden = false;
        clearTimeout(this._toastTimer);
        if (time) this._toastTimer = setTimeout(function () { toast.hidden = true; }, time);
    };

    /* ---------- события источника ---------- */

    KBPlayer.prototype._onDriver = function (type, payload) {
        var driver = this.driver;
        if (type === 'ready') {
            this._applyVolume();
            this._tick();
        } else if (type === 'meta') {
            this._sendMeta();
        } else if (type === 'ended') {
            // видео у админа доиграло — останавливаем таймлайн комнаты в конце
            if (this.isAdmin && this.timeline.playing) {
                var duration = this._duration();
                if (duration && this.target() >= duration - 3) {
                    this._command({action: 'pause', pos: duration});
                }
            }
        } else if (type === 'error') {
            this.error.querySelector('p').textContent = payload;
            this.error.hidden = false;
            this.spinner.hidden = true;
        } else if (type === 'change') {
            if (driver && driver.started) this._playAskedAt = 0;
        }
        this._render();
    };

    // Плеер админа сообщает серверу длину и название видео
    KBPlayer.prototype._sendMeta = function () {
        if (!this.isAdmin || !this.options.onMeta) return;
        var duration = this._duration();
        var title = this.driver ? (this.driver.title || '') : '';
        var key = Math.round(duration) + '|' + title;
        if ((!duration && !title) || key === this._metaSent) return;
        this._metaSent = key;
        this.options.onMeta({duration: duration || null, title: title || null});
    };

    /* ---------- подстройка под таймлайн ---------- */

    KBPlayer.prototype._needGate = function () {
        if (this._activated) return false;
        if (navigator.userActivation && navigator.userActivation.hasBeenActive) return false;
        // админ запускает видео своим кликом; остальным клик нужен заранее
        return this.timeline.playing || !this.isAdmin;
    };

    KBPlayer.prototype._tick = function () {
        var driver = this.driver;
        if (!driver || driver.passive) {
            this._render();
            return;
        }
        if (!driver.ready || !this.error.hidden) {
            this._render();
            return;
        }

        var needGate = this._needGate();
        this.gate.hidden = !needGate;
        if (needGate) {
            this._render();
            return;
        }

        var now = performance.now();
        var timeline = this.timeline;
        var duration = this._duration();
        var target = this.target();
        var atEnd = duration > 0 && target >= duration - 0.35;

        if (driver.live) {
            // прямой эфир: синхронизируем только пуск и паузу
            if (timeline.playing && driver.paused) this._play(now, target);
            if (!timeline.playing && !driver.paused) driver.pause();
        } else if (timeline.playing && atEnd) {
            // последние мгновения видео: даём доиграть самому
            driver.setRate(timeline.rate);
        } else if (timeline.playing) {
            if (driver.paused) {
                this._play(now, target);
            } else if (driver.started && !driver.buffering && now >= this._holdUntil) {
                var drift = driver.time - target;  // > 0 — убежали вперёд, < 0 — отстали
                var limit = driver.canNudge ? HARD_DRIFT_VIDEO : HARD_DRIFT_YOUTUBE;
                var missed = Math.abs(drift) > limit;
                if (this._landing) {
                    // первая сверка после перемотки: пока видео подгружалось, таймлайн ушёл вперёд.
                    // Запоминаем, на сколько промахнулись, — в следующий раз перемотаем с упреждением
                    this._landing = false;
                    this._lead = clamp(this._lead - drift * (missed ? 1 : 0.6), 0, MAX_LEAD);
                }
                if (missed) {
                    this._seekTries = Math.min(this._seekTries + 1, 5);
                    var ahead = target + this._lead * timeline.rate;
                    if (duration) ahead = Math.min(ahead, Math.max(target, duration - 1));
                    this._seek(now, ahead);
                    // если перемотки не помогают (слабая сеть, сервер без перемотки) — пробуем всё реже
                    this._holdUntil += (Math.pow(2, this._seekTries - 1) - 1) * 1000;
                    this._landing = true;
                    driver.setRate(timeline.rate);
                } else if (driver.canNudge && Math.abs(drift) > (this._nudging ? 0.04 : SOFT_DRIFT)) {
                    this._seekTries = 0;
                    this._nudging = true;
                    driver.setRate(timeline.rate * clamp(1 - drift * 0.4, 0.9, 1.1));
                } else {
                    this._seekTries = 0;
                    this._nudging = false;
                    driver.setRate(timeline.rate);
                }
            }
            this._watchAutoplay(now);
        } else if (atEnd && !driver.paused && duration - driver.time < 3) {
            // таймлайн остановлен в самом конце, а этому зрителю осталось мгновение —
            // даём плееру доиграть самому, а не ставим паузу на последнем кадре
            driver.setRate(timeline.rate);
        } else {
            if (!driver.paused) driver.pause();
            driver.setRate(timeline.rate);
            this._nudging = false;
            // на паузе у всех должен стоять один и тот же кадр
            var canSeek = driver.started || driver.seekBeforeStart;
            var gap = driver.canNudge ? 0.04 : 0.3;
            if (canSeek && now >= this._holdUntil && Math.abs(driver.time - target) > gap) {
                this._seek(now, target);
            }
        }
        this._render();
    };

    KBPlayer.prototype._seek = function (now, target) {
        this.driver.seek(target);
        this._holdUntil = now + (this.driver.canNudge ? 1200 : 2500);
    };

    KBPlayer.prototype._play = function (now, target) {
        var self = this;
        var driver = this.driver;
        if (now < this._playRetryAt) return;
        this._playRetryAt = now + 600;
        if (!this._playAskedAt) this._playAskedAt = now;
        if (!driver.live && (!driver.started || driver.ended || Math.abs(driver.time - target) > 0.5)) {
            this._seek(now, target);
        }
        driver.setRate(this.timeline.rate);
        driver.play().then(function (allowed) {
            if (!allowed && self.driver === driver) self._playSilently();
        });
    };

    // YouTube не сообщает, что браузер запретил автозапуск, — проверяем сами
    KBPlayer.prototype._watchAutoplay = function (now) {
        var driver = this.driver;
        if (driver.kind !== 'youtube' || driver.started || this._silent) return;
        if (this._playAskedAt && now - this._playAskedAt > 3500 && driver.paused) this._playSilently();
    };

    // Браузер не разрешил звук без клика: запускаем беззвучно и предлагаем включить звук
    KBPlayer.prototype._playSilently = function () {
        if (this._silent) return;
        this._silent = true;
        this._applyVolume();
        this._playRetryAt = 0;
        this.driver.play();
        this._showToast('Звук выключен браузером — нажмите, чтобы включить');
    };

    /* ---------- отрисовка ---------- */

    KBPlayer.prototype._renderChip = function () {
        if (this.isAdmin) {
            this.chip.innerHTML = icon('crown') + '<span>Вы управляете видео</span>';
        } else {
            this.chip.innerHTML = icon('sync') + '<span></span>';
            this.chip.lastChild.textContent = this.adminName ? 'Видео управляет ' + this.adminName : 'Видео управляет админ';
        }
    };

    KBPlayer.prototype._renderSeek = function (share) {
        share = clamp(share, 0, 1);
        this.seek.style.setProperty('--value', (share * 100) + '%');
        var duration = this._duration();
        if (duration) this.timeLabel.textContent = formatTime(share * duration) + ' / ' + formatTime(duration);
    };

    KBPlayer.prototype._render = function () {
        var driver = this.driver;
        var root = this.root;
        var passive = !driver || driver.passive;
        var timeline = this.timeline;
        root.classList.toggle('is-passive', passive);
        if (passive) {
            this.spinner.hidden = true;
            this.bigPlay.hidden = true;
            this.waitNote.hidden = true;
            return;
        }

        var duration = this._duration();
        var position = this._position();
        var target = this.target();
        var atEnd = duration > 0 && target >= duration - 0.35;
        var playing = timeline.playing && !atEnd;
        var broken = !this.error.hidden;

        root.classList.toggle('is-playing', playing);
        this.playButton.innerHTML = icon(playing ? 'pause' : 'play');

        if (!this._seeking) {
            var share = duration ? clamp(position / duration, 0, 1) : 0;
            this.seek.value = String(Math.round(share * 1000));
            this.seek.style.setProperty('--value', (share * 100) + '%');
            // длина ролика бывает неизвестна, пока он не запущен
            this.timeLabel.textContent = driver.live
                ? 'Прямой эфир'
                : formatTime(position) + (duration ? ' / ' + formatTime(duration) : '');
        }
        var buffered = duration && driver.ready ? clamp(driver.buffered / duration, 0, 1) : 0;
        this.seek.style.setProperty('--buffer', (buffered * 100) + '%');

        this.rateButton.textContent = formatRate(timeline.rate);
        var items = this.rateMenu.children;
        for (var i = 0; i < items.length; i++) {
            items[i].classList.toggle('is-current', Number(items[i].dataset.rate) === timeline.rate);
        }
        this.rateNote.hidden = timeline.rate === 1;
        this.rateNote.textContent = 'Скорость ' + formatRate(timeline.rate);

        var gate = !this.gate.hidden;
        var loading = !driver.ready || (playing && (driver.buffering || (!driver.started && !gate)));
        this.spinner.hidden = broken || gate || !loading;
        this.bigPlay.hidden = broken || gate || playing || !this.isAdmin || !driver.ready;

        // зрителю, пока админ не запустил видео
        var waiting = !this.isAdmin && !playing && !broken && !gate && driver.ready && position < 1;
        this.waitNote.hidden = !waiting;
        if (waiting) {
            this.waitNote.textContent = 'Ждём, когда ' + (this.adminName || 'админ') + ' запустит видео';
        }
    };

    KBPlayer.prototype.destroy = function () {
        clearInterval(this._timer);
        if (this.driver) this.driver.destroy();
        this.driver = null;
    };

    KBPlayer.formatTime = formatTime;
    window.KBPlayer = KBPlayer;
})();
