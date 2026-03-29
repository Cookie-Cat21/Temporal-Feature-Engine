(function() {
    const GITHUB_USERNAME = "ovindu";
    let widgetVisible = false;

    // Initialize Widget
    async function init() {
        const data = await chrome.storage.sync.get('hidden');
        if (!data.hidden) {
            createWidget();
        }
    }

    function createWidget() {
        if (document.getElementById('commit-glow-root')) return;

        const host = document.createElement('div');
        host.id = 'commit-glow-root';
        document.body.appendChild(host);

        const shadow = host.attachShadow({ mode: 'open' });

        // Add Styles
        const styleLink = document.createElement('style');
        fetch(chrome.runtime.getURL('styles.css'))
            .then(res => res.text())
            .then(css => {
                styleLink.textContent = css;
                shadow.appendChild(styleLink);
            });

        // Add Container
        const container = document.createElement('div');
        container.className = 'widget-container';
        container.innerHTML = `
            <div class="widget-header">
                <div class="title">CommitGlow: ${GITHUB_USERNAME}'s Pulse</div>
                <button class="close-btn" title="Hide permanently">×</button>
            </div>
            <div id="calendar-target" class="calendar">
                <div class="loading-msg">Igniting the glow...</div>
            </div>
        `;

        shadow.appendChild(container);

        const closeBtn = container.querySelector('.close-btn');
        closeBtn.onclick = () => {
            chrome.storage.sync.set({ hidden: true });
            host.remove();
            widgetVisible = false;
        };

        // Initialize GitHub Calendar
        const target = container.querySelector('#calendar-target');
        
        try {
            if (typeof GitHubCalendar === 'function') {
                GitHubCalendar(target, GITHUB_USERNAME, {
                    responsive: true,
                    tooltips: true,
                    global_stats: true,
                    proxy: (username) => {
                        return fetch(`https://api.bloggify.net/gh-calendar/?username=${username}`)
                            .then(r => r.text());
                    }
                }).then(() => {
                    // Success!
                    target.querySelector('.loading-msg')?.remove();
                }).catch(err => {
                    console.error("GitHubCalendar load error:", err);
                    showFallback(target);
                });
            } else {
                showFallback(target);
            }
        } catch (e) {
            console.error("CommitGlow script error:", e);
            showFallback(target);
        }

        widgetVisible = true;
    }

    function showFallback(target) {
        target.innerHTML = `
            <img src="https://ghchart.rshah.org/ovindu" class="fallback-img" alt="GitHub Contributions">
            <div class="streak-info">Showing static fallback. GitHub rate limits may apply.</div>
        `;
    }

    // Toggle Functionality
    chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
        if (msg.action === "toggle") {
            const host = document.getElementById('commit-glow-root');
            if (host) {
                host.remove();
                chrome.storage.sync.set({ hidden: true });
                widgetVisible = false;
            } else {
                createWidget();
                chrome.storage.sync.set({ hidden: false });
            }
        }
    });

    // Run on start
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
