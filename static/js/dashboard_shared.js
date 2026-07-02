(function () {
    function parseJsonValue(value, fallback) {
        if (value === undefined || value === null || value === '') {
            return fallback;
        }

        if (typeof value === 'string') {
            const trimmed = value.trim();
            if (!trimmed || trimmed === 'null') {
                return fallback;
            }
            try {
                return JSON.parse(trimmed);
            } catch (error) {
                return fallback;
            }
        }

        return value;
    }

    function getDashboardConfig() {
        const configNode = document.getElementById('dashboard-config');
        if (!configNode) {
            return {
                userName: '',
                notifications: [],
                trendChartData: null,
                distributionChartData: null,
            };
        }

        return {
            userName: configNode.dataset.userName || '',
            notifications: parseJsonValue(configNode.dataset.notifications, []),
            trendChartData: parseJsonValue(configNode.dataset.trend, null),
            distributionChartData: parseJsonValue(configNode.dataset.distribution, null),
        };
    }

    function setupGreeting(userName) {
        const banner = document.getElementById('greeting-banner');
        if (!banner) {
            return;
        }

        const fullName = (userName || '').trim();
        const firstName = fullName.split(' ')[0] || 'Farmer';
        const hour = new Date().getHours();
        let welcome = 'Dashboard';

        if (hour < 12) {
            welcome = `Good Morning, ${firstName}!`;
        } else if (hour < 18) {
            welcome = `Good Afternoon, ${firstName}!`;
        } else {
            welcome = `Good Evening, ${firstName}!`;
        }

        banner.textContent = welcome;
    }

    function setupMenuToggle() {
        const toggle = document.getElementById('menuToggle') || document.querySelector('.hamburger-btn');
        const sidebar = document.getElementById('sidebar');
        const backdrop = document.getElementById('backdrop');
        const icon = document.getElementById('toggleIcon');

        if (!toggle || !sidebar) {
            return;
        }

        toggle.addEventListener('click', function () {
            const isOpen = sidebar.classList.toggle('show-mobile');
            if (backdrop) {
                backdrop.classList.toggle('active', isOpen);
                backdrop.style.display = isOpen ? 'block' : 'none';
            }
            if (icon) {
                icon.className = isOpen ? 'fa-solid fa-xmark' : 'fa-solid fa-bars';
            }
        });
    }

    function toggleSidebarMenu() {
        const sidebar = document.getElementById('sidebar');
        const backdrop = document.getElementById('backdrop');
        const icon = document.getElementById('toggleIcon');

        if (!sidebar) {
            return;
        }

        const isOpen = sidebar.classList.toggle('show-mobile');
        if (backdrop) {
            backdrop.classList.toggle('active', isOpen);
            backdrop.style.display = isOpen ? 'block' : 'none';
        }
        if (icon) {
            icon.className = isOpen ? 'fa-solid fa-xmark' : 'fa-solid fa-bars';
        }
    }

    function initNotificationUiEngine(initialNotifications) {
        const bellTrigger = document.getElementById('bell-trigger');
        const dropdown = document.getElementById('notif-dropdown');
        const badge = document.getElementById('bell-badge');
        const listWrapper = document.getElementById('notif-list-wrapper');
        const clearBtn = document.getElementById('clear-all-btn');

        if (!bellTrigger || !dropdown || !listWrapper) {
            return;
        }

        let notifications = Array.isArray(initialNotifications) ? initialNotifications.slice() : [];
        let currentFilter = 'all';

        bellTrigger.addEventListener('click', function (event) {
            event.stopPropagation();
            dropdown.style.display = dropdown.style.display === 'block' ? 'none' : 'block';
        });

        document.addEventListener('click', function (event) {
            if (!dropdown.contains(event.target) && event.target !== bellTrigger) {
                dropdown.style.display = 'none';
            }
        });

        function renderNotifications() {
            listWrapper.innerHTML = '';
            const unreadCount = notifications.filter(function (item) {
                return item.type === 'unread';
            }).length;

            if (badge) {
                badge.style.display = unreadCount > 0 ? 'block' : 'none';
            }

            let filtered = notifications;
            if (currentFilter === 'unread') {
                filtered = notifications.filter(function (item) {
                    return item.type === 'unread';
                });
            }
            if (currentFilter === 'alert') {
                filtered = notifications.filter(function (item) {
                    return item.tag === 'alert';
                });
            }

            if (filtered.length === 0) {
                listWrapper.innerHTML = [
                    '<div style="text-align: center; padding: 30px 10px;">',
                    '<i class="fa-regular fa-bell-slashed" style="font-size: 1.3rem; color: #cbd5e1; margin-bottom: 6px;"></i>',
                    '<p style="font-size: 0.75rem; color: #94a3b8; margin: 0;">No notifications found.</p>',
                    '</div>'
                ].join('');
                return;
            }

            filtered.forEach(function (item) {
                const div = document.createElement('div');
                div.className = 'notif-item ' + (item.type === 'unread' ? 'is-unread' : '');
                const icon = item.tag === 'alert' ? 'fa-triangle-exclamation' : 'fa-camera';
                const iconColor = item.tag === 'alert' ? '#f59e0b' : '#164630';

                div.innerHTML = [
                    '<i class="fa-solid ' + icon + '" style="color:' + iconColor + '; margin-top:4px;"></i>',
                    '<div>',
                    '<p style="margin:0;">' + item.text + '</p>',
                    '<span class="time">' + item.time + '</span>',
                    '</div>'
                ].join('');

                div.addEventListener('click', function () {
                    item.type = 'read';
                    renderNotifications();
                });

                listWrapper.appendChild(div);
            });
        }

        document.querySelectorAll('.notif-filter').forEach(function (btn) {
            btn.addEventListener('click', function (event) {
                document.querySelectorAll('.notif-filter').forEach(function (filterBtn) {
                    filterBtn.classList.remove('active');
                });
                event.target.classList.add('active');
                currentFilter = event.target.getAttribute('data-filter');
                renderNotifications();
            });
        });

        if (clearBtn) {
            clearBtn.addEventListener('click', function () {
                if (notifications.length === 0) {
                    return;
                }
                if (confirm('Are you sure you want to delete all notifications? This action cannot be undone.')) {
                    notifications = [];
                    renderNotifications();
                }
            });
        }

        renderNotifications();
    }

    function initCharts(trendChartData, distributionChartData) {
        const trendEl = document.getElementById('trendChart');
        if (trendEl && trendChartData && trendChartData.labels && trendChartData.labels.length) {
            const ctxTrend = trendEl.getContext('2d');
            new window.Chart(ctxTrend, {
                type: 'line',
                data: trendChartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'top', labels: { boxWidth: 10, font: { size: 10, weight: '600' } } }
                    },
                    scales: {
                        y: { beginAtZero: true, grid: { color: '#f1f5f9' } },
                        x: { grid: { display: false } }
                    }
                }
            });
        }

        const distEl = document.getElementById('distributionChart');
        if (distEl && distributionChartData && distributionChartData.labels && distributionChartData.labels.length) {
            const ctxDist = distEl.getContext('2d');
            new window.Chart(ctxDist, {
                type: 'doughnut',
                data: distributionChartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11, weight: '500' } } }
                    },
                    cutout: '65%'
                }
            });
        }
    }

    function initDashboardWidgets() {
        const config = getDashboardConfig();
        setupGreeting(config.userName);
        setupMenuToggle();
        initNotificationUiEngine(config.notifications || []);
        initCharts(config.trendChartData, config.distributionChartData);
    }

    window.toggleSidebarMenu = toggleSidebarMenu;
    window.initDashboardWidgets = initDashboardWidgets;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDashboardWidgets);
    } else {
        initDashboardWidgets();
    }
})();
