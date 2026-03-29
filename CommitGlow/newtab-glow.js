(function() {
    let GITHUB_USERNAME = "Cookie-Cat21";

    async function initCalendar() {
        // Try to get username from storage, fallback to default
        const data = await chrome.storage.sync.get(['username']);
        if (data.username) GITHUB_USERNAME = data.username;

        const widget = document.getElementById('commit-glow-widget');
        if (!widget) return;

        // Create the native Material card structure
        widget.innerHTML = `
            <div class="pulse-card-header" style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px; opacity: 0.8;">
                <div class="pulse-dot" style="width: 8px; height: 8px; background: #238636; border-radius: 50%; box-shadow: 0 0 8px #238636;"></div>
                <span style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px;">GitHub Pulse: ${GITHUB_USERNAME}</span>
            </div>
            <div id="calendar-target" style="width: 100%;"></div>
        `;

        const target = document.getElementById('calendar-target');
        
        if (typeof GitHubCalendar === 'function') {
            GitHubCalendar(target, GITHUB_USERNAME, {
                responsive: true,
                tooltips: true,
                global_stats: false,
                proxy: (username) => fetch(`https://api.bloggify.net/gh-calendar/?username=${username}`).then(r => r.text())
            }).then(() => {
                // Strictly remove all clutter
                const junk = ['.contrib-column', '.text-gray', '.float-left', '.float-right', 'a', '.ContributionCalendar-label', 'h2'];
                junk.forEach(s => target.querySelectorAll(s).forEach(el => el.style.display = 'none'));
                
                // Theme the squares via JS if CSS is too brittle (backup)
                // but we'll try to rely on the CSS in index.html for variable support.
            }).catch(err => {
                console.error("Pulse Load Error:", err);
                showFallback(target);
            });
        } else {
            showFallback(target);
        }
    }

    function showFallback(target) {
        target.innerHTML = `<div style="text-align:center; padding: 20px; opacity: 0.5;">Unable to load Pulse. Check GitHub username.</div>`;
    }

    // Wait for the dashboard to settle
    if (document.readyState === 'complete') {
        initCalendar();
    } else {
        window.addEventListener('load', initCalendar);
    }
})();
