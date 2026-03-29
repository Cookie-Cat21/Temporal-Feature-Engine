(function() {
    let GITHUB_USERNAME = "Cookie-Cat21";

    // 1. Clock & Date Logic
    function updateClock() {
        const now = new Date();
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        document.getElementById('clock').textContent = `${hours}:${minutes}`;

        // Format: Monday, April 22nd
        const options = { weekday: 'long', month: 'long', day: 'numeric' };
        document.getElementById('date').textContent = now.toLocaleDateString('en-US', options).toUpperCase();
    }

    // 2. Wallpaper Logic (High-end background with better darkening)
    function setWallpaper() {
        // We'll use a fixed high-res forest image for now to ensure quality
        const url = "https://images.unsplash.com/photo-1441974231531-c6227db76b6e?auto=format&fit=crop&q=100&w=2560"; 
        document.getElementById('bg-body').style.backgroundImage = `url('${url}')`;
    }

    // 3. Stats Logic (Animated Simulation)
    function updateStats() {
        const now = new Date();
        const daysSinceJan = now.getDate() + (now.getMonth() * 30);
        
        // Target values
        const tVal = (14281 + (daysSinceJan * 42));
        const bVal = (1.4 + (daysSinceJan * 0.05)).toFixed(1);
        const hVal = (12 + (daysSinceJan * 2));

        document.getElementById('stat-trackers').textContent = tVal.toLocaleString();
        document.getElementById('stat-bandwidth').textContent = bVal + " GB";
        document.getElementById('stat-time').textContent = hVal + " min";
    }

    // 4. GitHub Calendar Logic
    async function initCalendar() {
        const data = await chrome.storage.sync.get(['username']);
        if (data.username) GITHUB_USERNAME = data.username;

        const widget = document.getElementById('commit-glow-widget');
        widget.innerHTML = `
            <div class="widget-container">
                <div class="widget-header">
                    <div class="title" style="display:flex; align-items:center; gap:8px;">
                        <span style="width:8px; height:8px; background:#238636; border-radius:50%; box-shadow:0 0 10px #238636;"></span>
                        Contribution Heatmap: ${GITHUB_USERNAME}
                    </div>
                </div>
                <div id="calendar-target" class="calendar">
                    <div class="loading-msg">Summoning your progress...</div>
                </div>
            </div>
        `;

        const target = document.getElementById('calendar-target');
        if (typeof GitHubCalendar === 'function') {
            GitHubCalendar(target, GITHUB_USERNAME, {
                responsive: true,
                tooltips: true,
                global_stats: true,
                proxy: (username) => fetch(`https://api.bloggify.net/gh-calendar/?username=${username}`).then(r => r.text())
            }).then(() => {
                target.querySelector('.loading-msg')?.remove();
                // Custom tooltip styling fix
                target.querySelectorAll('.day-tooltip').forEach(t => {
                   t.style.background = 'rgba(0,0,0,0.85)';
                   t.style.borderRadius = '8px';
                   t.style.border = '1px solid rgba(255,255,255,0.1)';
                   t.style.backdropFilter = 'blur(10px)';
                });
            }).catch(() => showFallback(target));
        } else {
            showFallback(target);
        }
    }

    function showFallback(target) {
        target.innerHTML = `<img src="https://ghchart.rshah.org/${GITHUB_USERNAME}" style="width:100%; border-radius:12px; filter: contrast(1.1);" alt="GitHub Contributions">`;
    }

    // Run Initialization
    updateClock();
    setWallpaper();
    updateStats();
    initCalendar();
    
    // Low frequency updates
    setInterval(updateClock, 30000);
    setInterval(updateStats, 3600000);

})();
