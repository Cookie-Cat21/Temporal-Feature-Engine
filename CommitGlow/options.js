// Load current settings
function loadSettings() {
  chrome.storage.sync.get({
    username: 'Cookie-Cat21' // Default value
  }, (items) => {
    document.getElementById('username').value = items.username;
  });
}

// Save settings
function saveSettings() {
  const username = document.getElementById('username').value.trim();
  if (!username) return;

  chrome.storage.sync.set({
    username: username
  }, () => {
    const status = document.getElementById('status');
    status.classList.add('visible');
    setTimeout(() => {
      status.classList.remove('visible');
    }, 2000);
  });
}

document.addEventListener('DOMContentLoaded', loadSettings);
document.getElementById('save').addEventListener('click', saveSettings);
