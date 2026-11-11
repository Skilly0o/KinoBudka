/*
 * Страница комнаты: связь с сервером (Socket.IO), чат, список зрителей
 * и инструменты админа. Сам плеер — в kb-player.js.
 */
(function () {
    'use strict';

    var settings = JSON.parse(document.getElementById('room-settings').textContent);

    function $(id) {
        return document.getElementById(id);
    }

    function icon(name) {
        return '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-' + name + '"></use></svg>';
    }

    function node(tag, className, text) {
        var element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined && text !== null) element.textContent = text;
        return element;
    }

    var me = {id: null, name: settings.name, admin: settings.isAdmin};
    var room = {admin: settings.admin, status: settings.status, members: 0};
    var source = settings.source;
    var users = [];

    var socket = io({auth: {room: settings.code}});

    var player = new KBPlayer($('player'), {
        admin: me.admin,
        adminName: room.admin,
        hlsUrl: settings.hlsUrl,
        onCommand: function (command) {
            socket.emit('control', command);
        },
        onMeta: function (meta) {
            socket.emit('meta', {rev: source.rev, duration: meta.duration, title: meta.title});
        }
    });
    player.load(source);

    /* ---------------------------------------------------------------- уведомления */

    var notices = $('room-notices');

    function notify(text, kind) {
        var item = node('div', 'room-notice' + (kind ? ' is-' + kind : ''), text);
        notices.appendChild(item);
        setTimeout(function () {
            item.classList.add('is-leaving');
            setTimeout(function () { item.remove(); }, 300);
        }, 3600);
    }

    /* ---------------------------------------------------------------- шапка комнаты */

    function renderRoom() {
        $('room-title').textContent = source.title || 'Комната ' + settings.code;
        document.title = (source.title || 'Комната') + ' — KinBu';
        $('room-kind').textContent = source.label || '';

        var closed = room.status !== 'open';
        $('room-status').innerHTML = icon(closed ? 'lock' : 'globe');
        $('room-status').appendChild(node('span', '', closed ? 'Закрытая' : 'Открытая'));
        $('room-status').title = closed
            ? 'Комнаты нет на главной: войти можно только по ссылке или коду'
            : 'Комната видна на главной странице';

        $('room-admin-name').textContent = room.admin;
        $('members-count').textContent = String(users.length || room.members || 1);

        var note = $('guest-note-admin');
        if (note) note.textContent = room.admin;

        var buttons = document.querySelectorAll('#status-toggle button');
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].classList.toggle('is-current', buttons[i].dataset.status === room.status);
        }
        $('embed-note').hidden = source.kind !== 'embed';
    }

    // показать нужные блоки админу или зрителю (права можно передать прямо во время просмотра)
    function renderRole() {
        document.body.classList.toggle('is-room-admin', me.admin);
        $('admin-tools').hidden = !me.admin;
        $('guest-note').hidden = me.admin;
        player.setAdmin(me.admin);
        player.setAdminName(room.admin);
        renderUsers();
    }

    /* ---------------------------------------------------------------- чат */

    var messages = $('chat-container');
    var chatInput = $('chat-input');

    function createMessage(data) {
        var nearBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 80;
        var row;
        if (data.system) {
            row = node('div', 'text text-system', data.message);
        } else {
            row = node('div', 'text' + (data.admin ? ' text-admin' : ''));
            if (data.avatar) {
                var picture = node('img', 'text-avatar');
                picture.src = data.avatar;
                picture.alt = '';
                row.appendChild(picture);
            } else {
                row.appendChild(node('span', 'text-avatar avatar-fallback', (data.name || '?').charAt(0)));
            }
            var body = node('div', 'text-body');
            var name = node('strong', 'text-name', data.name);
            if (data.admin) {
                name.insertAdjacentHTML('beforeend', icon('crown'));
                name.title = 'Админ комнаты';
            }
            body.appendChild(name);
            body.appendChild(node('span', 'text-message', data.message));
            row.appendChild(body);
        }
        messages.appendChild(row);
        if (nearBottom) messages.scrollTop = messages.scrollHeight;
    }

    function sendMessage() {
        if (!chatInput || chatInput.value.trim() === '') return;
        socket.emit('message', {data: chatInput.value});
        chatInput.value = '';
    }

    if (chatInput) {
        chatInput.addEventListener('keydown', function (event) {
            if (event.key === 'Enter') {
                event.preventDefault();
                sendMessage();
            }
        });
        $('chat-send').addEventListener('click', sendMessage);
    }

    /* ---------------------------------------------------------------- зрители */

    var membersList = $('members');

    function renderUsers() {
        membersList.innerHTML = '';
        $('members-count').textContent = String(users.length || 1);
        $('tab-members-count').textContent = String(users.length);
        users.slice().sort(function (a, b) {
            return (b.admin ? 1 : 0) - (a.admin ? 1 : 0);
        }).forEach(function (user) {
            var row = node('div', 'member' + (user.admin ? ' is-admin' : ''));
            if (user.avatar) {
                var picture = node('img', 'member-avatar');
                picture.src = user.avatar;
                picture.alt = '';
                row.appendChild(picture);
            } else {
                row.appendChild(node('span', 'member-avatar avatar-fallback', (user.name || '?').charAt(0)));
            }
            var info = node('div', 'member-info');
            info.appendChild(node('span', 'member-name', user.name + (user.id === me.id ? ' (вы)' : '')));
            info.appendChild(node('span', 'member-role', user.admin ? 'Админ комнаты' : 'Зритель'));
            row.appendChild(info);

            if (user.admin) {
                row.insertAdjacentHTML('beforeend', '<span class="member-crown" title="Админ комнаты">' + icon('crown') + '</span>');
            } else if (me.admin) {
                var give = node('button', 'btn btn-icon btn-ghost');
                give.type = 'button';
                give.title = 'Передать управление';
                give.innerHTML = icon('swap');
                give.addEventListener('click', function () {
                    if (window.confirm('Передать управление комнатой зрителю «' + user.name + '»? Вы станете обычным зрителем.')) {
                        socket.emit('transfer', {id: user.id});
                    }
                });
                var kick = node('button', 'btn btn-icon btn-danger');
                kick.type = 'button';
                kick.title = 'Исключить из комнаты';
                kick.innerHTML = icon('user-x');
                kick.addEventListener('click', function () {
                    if (window.confirm('Исключить «' + user.name + '» из комнаты?')) {
                        socket.emit('kick', {id: user.id});
                    }
                });
                row.appendChild(give);
                row.appendChild(kick);
            }
            membersList.appendChild(row);
        });
    }

    // вкладки «Чат» / «Зрители»
    var tabs = document.querySelectorAll('.side-tab');
    Array.prototype.forEach.call(tabs, function (tab) {
        tab.addEventListener('click', function () {
            Array.prototype.forEach.call(tabs, function (other) {
                other.classList.toggle('is-current', other === tab);
            });
            $('pane-chat').hidden = tab.dataset.pane !== 'chat';
            $('pane-members').hidden = tab.dataset.pane !== 'members';
            if (tab.dataset.pane === 'chat') messages.scrollTop = messages.scrollHeight;
        });
    });

    /* ---------------------------------------------------------------- ссылка для друзей */

    function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) {
            return navigator.clipboard.writeText(text);
        }
        // по адресу вида http://25.x.x.x буфер обмена доступен только «по-старому»
        return new Promise(function (resolve, reject) {
            var area = document.createElement('textarea');
            area.value = text;
            area.setAttribute('readonly', '');
            area.style.position = 'fixed';
            area.style.opacity = '0';
            document.body.appendChild(area);
            area.select();
            var ok = false;
            try {
                ok = document.execCommand('copy');
            } catch (e) { /* не получилось */ }
            area.remove();
            if (ok) resolve(); else reject(new Error('copy'));
        });
    }

    function copyLink(url) {
        copyText(url).then(function () {
            notify('Ссылка скопирована: ' + url, 'ok');
        }, function () {
            window.prompt('Скопируйте ссылку и отправьте друзьям:', url);
        });
    }

    var share = settings.share && settings.share.length
        ? settings.share
        : [{label: '', url: window.location.origin + window.location.pathname}];
    var shareMenu = $('share-menu');

    $('copy-link').addEventListener('click', function (event) {
        event.stopPropagation();
        if (share.length === 1) {
            copyLink(share[0].url);
            return;
        }
        shareMenu.hidden = !shareMenu.hidden;
    });
    share.forEach(function (item) {
        var button = node('button', 'share-item');
        button.type = 'button';
        button.appendChild(node('span', 'share-label', item.label || 'Ссылка'));
        button.appendChild(node('span', 'share-url', item.url));
        button.addEventListener('click', function () {
            shareMenu.hidden = true;
            copyLink(item.url);
        });
        shareMenu.appendChild(button);
    });
    document.addEventListener('click', function (event) {
        if (!shareMenu.contains(event.target)) shareMenu.hidden = true;
    });

    $('copy-code').addEventListener('click', function () {
        copyText(settings.code).then(function () {
            notify('Код комнаты скопирован', 'ok');
        }, function () {
            window.prompt('Код комнаты:', settings.code);
        });
    });

    /* ---------------------------------------------------------------- инструменты админа */

    var sourceForm = $('source-form');
    var sourceInput = $('source-url');
    var sourceFile = $('source-file');
    var sourceError = $('source-error');

    function changeSource(payload) {
        sourceError.hidden = true;
        socket.emit('source', payload, function (result) {
            if (result && result.ok) {
                // очищаем поле, только если в нём всё ещё та ссылка, которую отправляли
                if (!payload.url || sourceInput.value.trim() === payload.url) sourceInput.value = '';
                sourceFile.value = '';
                return;
            }
            sourceError.textContent = (result && result.error) || 'Не получилось сменить видео';
            sourceError.hidden = false;
        });
    }

    sourceForm.addEventListener('submit', function (event) {
        event.preventDefault();
        var url = sourceInput.value.trim();
        if (url) changeSource({url: url});
    });
    sourceFile.addEventListener('change', function () {
        if (sourceFile.value) changeSource({file: sourceFile.value});
    });

    function loadLibrary() {
        if (!me.admin || !settings.canChat) return;  // свои файлы — только для вошедших в аккаунт
        socket.emit('library', function (items) {
            if (!items || !items.length) {
                $('source-file-box').hidden = true;
                return;
            }
            sourceFile.innerHTML = '';
            var first = node('option', '', 'Выбрать свой файл из медиатеки…');
            first.value = '';
            sourceFile.appendChild(first);
            items.forEach(function (item) {
                var option = node('option', '', item.name + ' · ' + item.size);
                option.value = item.path;
                sourceFile.appendChild(option);
            });
            $('source-file-box').hidden = false;
        });
    }

    Array.prototype.forEach.call(document.querySelectorAll('#status-toggle button'), function (button) {
        button.addEventListener('click', function () {
            socket.emit('status', {status: button.dataset.status});
        });
    });

    $('close-room').addEventListener('click', function () {
        if (window.confirm('Завершить просмотр и удалить комнату? Все зрители вернутся на главную.')) {
            socket.emit('close');
        }
    });

    /* ---------------------------------------------------------------- события сервера */

    var connectedOnce = false;
    var leaving = false;

    function leave(text) {
        leaving = true;
        player.destroy();
        $('room-ended-text').textContent = text;
        $('room-ended').hidden = false;
    }

    socket.on('init', function (data) {
        var wasAdmin = me.admin;
        me.id = data.you.id;
        me.name = data.you.name;
        me.admin = data.you.admin;
        room = data.room;
        users = data.users;

        if (data.source.rev !== source.rev) {
            source = data.source;
            player.load(source);
        } else {
            source = data.source;
        }
        player.setTimeline(data.state);

        messages.innerHTML = '';
        data.messages.forEach(createMessage);
        messages.scrollTop = messages.scrollHeight;

        renderRoom();
        renderRole();
        if (me.admin && (!connectedOnce || !wasAdmin)) loadLibrary();
        if (connectedOnce) notify('Соединение восстановлено', 'ok');
        connectedOnce = true;
    });

    socket.on('state', function (state) {
        if (state.rev !== source.rev) return;  // состояние от предыдущего видео
        player.setTimeline(state);
    });

    socket.on('source', function (data) {
        source = data.source;
        player.load(source);
        player.setTimeline(data.state);
        renderRoom();
    });

    socket.on('title', function (data) {
        if (data.rev !== source.rev) return;
        source.title = data.title;
        renderRoom();
    });

    socket.on('room', function (data) {
        room = data;
        renderRoom();
        player.setAdminName(room.admin);
    });

    socket.on('users', function (list) {
        users = list;
        var mine = null;
        for (var i = 0; i < users.length; i++) {
            if (users[i].id === me.id) mine = users[i];
        }
        if (mine && mine.admin !== me.admin) {
            me.admin = mine.admin;
            notify(me.admin ? 'Теперь вы управляете комнатой' : 'Вы передали управление комнатой', 'ok');
            renderRole();
            if (me.admin) loadLibrary();
        } else {
            renderUsers();
        }
        renderRoom();
    });

    socket.on('message', function (data) {
        createMessage(data);
    });

    socket.on('kicked', function () {
        leave('Админ исключил вас из комнаты.');
    });

    socket.on('closed', function () {
        leave('Админ завершил просмотр, комната закрыта.');
    });

    socket.on('disconnect', function () {
        if (!leaving) notify('Соединение потеряно, переподключаемся…', 'warn');
    });

    socket.on('connect_error', function (error) {
        // сервер отказал во входе: комнаты больше нет (например, сайт перезапускали)
        if (!leaving && error && !error.type && !socket.active) {
            leave('Комната больше не существует.');
        }
    });

    // раз в несколько секунд сверяем часы с сервером — на случай сна вкладки или компьютера
    setInterval(function () {
        if (socket.connected) socket.emit('sync');
    }, 12000);
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && socket.connected) socket.emit('sync');
    });

    renderRoom();
    renderRole();
})();
