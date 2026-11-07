// Agent chat (dashboard/chat.py). Enter sends the question and Shift+Enter adds a line. An Enter
// that confirms an input-method composition (Chinese, Japanese) is left to the input method.
document.addEventListener("keydown", function (event) {
  var box = event.target;
  if (!box || box.id !== "chat-input" || event.key !== "Enter" || event.shiftKey) return;
  if (event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  var send = document.getElementById("chat-send");
  if (send && !send.hidden && !send.disabled) send.click();
});

// Keep the newest message in view when messages or live steps are added.
(function follow() {
  var scroller = document.getElementById("chat-scroll");
  if (!scroller) { setTimeout(follow, 500); return; }
  new MutationObserver(function (records) {
    var added = records.some(function (r) { return r.type === "childList"; });
    if (added) scroller.scrollTop = scroller.scrollHeight;
  }).observe(scroller, { childList: true, subtree: true });
})();

// Escape closes a popup (citation, example questions) first, then the chat.
document.addEventListener("keydown", function (event) {
  if (event.key !== "Escape") return;
  var chat = document.getElementById("chat");
  if (!chat || !chat.classList.contains("open")) return;
  var popups = [["chat-cite-view", "chat-cite-close"], ["chat-prompts", "chat-prompts-close"]];
  var target = "chat-close";
  for (var i = 0; i < popups.length; i++) {
    var view = document.getElementById(popups[i][0]);
    if (view && !view.hidden) { target = popups[i][1]; break; }
  }
  var button = document.getElementById(target);
  if (button) button.click();
});

// Picking an example question puts the cursor in the input, ready to edit or press Enter.
document.addEventListener("click", function (event) {
  if (!event.target.closest || !event.target.closest(".chat-prompt")) return;
  setTimeout(function () {
    var box = document.getElementById("chat-input");
    if (box) { box.focus(); box.setSelectionRange(box.value.length, box.value.length); }
  }, 150);
});
