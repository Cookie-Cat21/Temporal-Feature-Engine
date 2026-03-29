chrome.action.onClicked.addListener((tab) => {
  chrome.tabs.sendMessage(tab.id, { action: "toggle" }).catch(err => {
    console.log("Cannot send message to this page: ", err.message);
  });
});
