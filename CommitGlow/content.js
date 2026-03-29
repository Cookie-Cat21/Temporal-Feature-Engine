(function() {
    let GITHUB_USERNAME = "Cookie-Cat21";
    let widgetVisible = false;

    // Initialize Widget
    async function init() {
        const data = await chrome.storage.sync.get(['hidden', 'username']);
        if (data.username) GITHUB_USERNAME = data.username;

        // Restriction Logic: Only show on about:blank or if toggled
        const isNewTab = window.location.href === 'about:blank' || document.title === 'New Tab';
        
        if (isNewTab && !data.hidden) {
            createWidget();
        }
    }

    async function createWidget() {
        if (document.getElementById('commit-glow-root')) return;

        const host = document.createElement('div');
        host.id = 'commit-glow-root';
        document.body.appendChild(host);

        const shadow = host.attachShadow({ mode: 'open' });

        // Load Library CSS + Custom Styles
        const libCss = await fetch(chrome.runtime.getURL('lib/github-calendar-responsive.css')).then(r => r.text());
        const customCss = await fetch(chrome.runtime.getURL('styles.css')).then(r => r.text());

        const stylesheet = document.createElement('style');
        stylesheet.textContent = libCss + "\n" + customCss;
        shadow.appendChild(stylesheet);

        // Add Container
        const container = document.createElement('div');
        container.className = 'widget-container';
        container.innerHTML = `
            <div class="widget-header">
                <div class="title">CommitGlow: ${GITHUB_USERNAME}</div>
                <button class="close-btn" title="Hide permananently">×</button>
            </div>
            <div id="calendar-target" class="calendar">
                <div class="loading-msg">Fetching glow...</div>
            </div>
        `;

        shadow.appendChild(container);

        const closeBtn = container.querySelector('.close-btn');
        closeBtn.onclick = () => {
            chrome.storage.sync.set({ hidden: true });
            host.remove();
            widgetVisible = false;
        };

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
                    target.querySelector('.loading-msg')?.remove();
                }).catch(err => {
                    console.error("GitHubCalendar load error:", err);
                    showFallback(target);
                });
            } else {
                showFallback(target);
            }
        } catch (e) {
            showFallback(target);
        }

        widgetVisible = true;
    }

    function showFallback(target) {
        target.innerHTML = `
            <img src="https://ghchart.rshah.org/${GITHUB_USERNAME}" class="fallback-img" alt="GitHub Contributions">
            <div class="streak-info">Static fallback active.</div>
        `;
    }

    // Toggle Functionality (Allows manual show on any page)
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

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
