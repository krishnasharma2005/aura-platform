/*!
 * AURA "Add chat to your website" widget.
 *
 * Paste this on any page:
 *   <script src="https://<your-aura-web-host>/widget.js"
 *           data-org="<public_id>"
 *           data-api="https://<your-aura-api-host>"
 *           defer></script>
 *
 * Design constraints, on purpose:
 *  - No build step, no dependencies, no React/Next runtime — this is loaded
 *    on a stranger's website, so every byte and every global it touches is a
 *    cost the host page pays. Vanilla JS only.
 *  - Everything the widget renders lives inside a closed Shadow DOM. That is
 *    the whole answer to "can it leak styles onto the host page, or inherit
 *    the host page's styles" — a shadow root's styles are scoped in both
 *    directions.
 *  - It only ever calls the public, unauthenticated, rate-limited endpoint
 *    (POST /api/v1/public/chat/{org_public_id}) — the same one a business
 *    embeds nowhere else. It never sees, stores, or asks for anything about
 *    the business beyond that one opaque id, which is safe to publish (it's
 *    designed to be pasted into public HTML).
 *  - If the business has turned website chat off, or the id is wrong, this
 *    script renders nothing and fails silently — a visible error box on
 *    someone else's website is not an acceptable failure mode.
 */
(function () {
  "use strict";

  var CURRENT_SCRIPT = document.currentScript;
  if (!CURRENT_SCRIPT) return;

  var ORG_ID = CURRENT_SCRIPT.getAttribute("data-org");
  var API_URL = (CURRENT_SCRIPT.getAttribute("data-api") || "").replace(/\/+$/, "");
  if (!ORG_ID || !API_URL) return; // Nothing to talk to — render nothing.

  var STORAGE_KEY = "aura_widget_token_" + ORG_ID;
  var GREETING = "Hi! How can we help?";
  var SEND_ERROR = "Sorry, that didn't send. Please try again.";

  function storageGet(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return null; // Private browsing / storage disabled — degrade to a fresh thread each visit.
    }
  }

  function storageSet(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (e) {
      /* ignore — same degrade as above */
    }
  }

  function el(tag, props, children) {
    var node = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (key) {
        if (key === "style") Object.assign(node.style, props[key]);
        else if (key.indexOf("on") === 0) node.addEventListener(key.slice(2).toLowerCase(), props[key]);
        else node.setAttribute(key, props[key]);
      });
    }
    (children || []).forEach(function (child) {
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  // --- Only reached once /status confirms the business wants this on. ---
  function mount() {
    var host = el("div", { id: "aura-widget-host" });
    host.style.all = "initial";
    host.style.position = "fixed";
    host.style.zIndex = "2147483000"; // above virtually anything the host page has, never above native browser UI
    host.style.bottom = "0";
    host.style.right = "0";
    document.body.appendChild(host);

    var shadow = host.attachShadow({ mode: "closed" });

    var style = document.createElement("style");
    style.textContent = [
      ":host, *{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;}",
      ".wrap{position:fixed;bottom:20px;right:20px;display:flex;flex-direction:column;align-items:flex-end;gap:12px;}",
      ".bubble{width:56px;height:56px;border-radius:999px;background:#1f2937;color:#fff;border:none;cursor:pointer;box-shadow:0 8px 24px rgba(0,0,0,.22);display:flex;align-items:center;justify-content:center;transition:transform .15s ease;}",
      ".bubble:hover{transform:scale(1.05);}",
      ".bubble svg{width:26px;height:26px;}",
      ".panel{width:340px;max-width:calc(100vw - 40px);height:460px;max-height:calc(100vh - 120px);background:#fff;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,.28);display:none;flex-direction:column;overflow:hidden;border:1px solid #e5e7eb;}",
      ".panel.open{display:flex;}",
      ".header{background:#1f2937;color:#fff;padding:14px 16px;display:flex;align-items:center;justify-content:space-between;font-size:14px;font-weight:600;}",
      ".header button{background:transparent;border:none;color:#fff;cursor:pointer;font-size:18px;line-height:1;opacity:.85;padding:2px 4px;}",
      ".header button:hover{opacity:1;}",
      ".messages{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;background:#fafafa;}",
      ".msg{max-width:82%;padding:9px 12px;border-radius:12px;font-size:13.5px;line-height:1.45;white-space:pre-wrap;word-break:break-word;}",
      ".msg.bot{align-self:flex-start;background:#fff;border:1px solid #e5e7eb;color:#111827;}",
      ".msg.user{align-self:flex-end;background:#1f2937;color:#fff;}",
      ".msg.pending{opacity:.55;}",
      ".composer{display:flex;gap:8px;padding:10px;border-top:1px solid #e5e7eb;background:#fff;}",
      ".composer textarea{flex:1;resize:none;border:1px solid #d1d5db;border-radius:10px;padding:9px 11px;font-size:13.5px;font-family:inherit;max-height:80px;min-height:38px;}",
      ".composer textarea:focus{outline:2px solid #1f2937;outline-offset:1px;}",
      ".composer button{background:#1f2937;color:#fff;border:none;border-radius:10px;width:38px;height:38px;flex-shrink:0;cursor:pointer;display:flex;align-items:center;justify-content:center;}",
      ".composer button:disabled{opacity:.4;cursor:default;}",
      ".composer textarea:disabled{background:#f3f4f6;cursor:not-allowed;}",
      ".options{display:flex;flex-wrap:wrap;gap:6px;padding:0 14px 4px;background:#fafafa;}",
      ".options button{background:#fff;border:1px solid #d1d5db;border-radius:999px;padding:7px 12px;font-size:12.5px;font-family:inherit;color:#111827;cursor:pointer;line-height:1.3;}",
      ".options button:hover{border-color:#1f2937;background:#f9fafb;}",
      ".footer{text-align:center;font-size:10.5px;color:#9ca3af;padding:4px 0 8px;}",
    ].join("\n");
    shadow.appendChild(style);

    var messagesEl = el("div", { class: "messages" });
    // Holds the reply buttons when this business's assistant is running a
    // predefined menu instead of free-form AI. Stays empty otherwise.
    var optionsEl = el("div", { class: "options" });
    var textarea = el("textarea", { rows: "1", placeholder: "Type a message…" });
    var sendBtn = el(
      "button",
      { type: "button", "aria-label": "Send" },
      [svgSend()]
    );
    var panel = el("div", { class: "panel" }, [
      el("div", { class: "header" }, [
        el("span", {}, ["Chat with us"]),
        el("button", { "aria-label": "Close chat", onClick: togglePanel }, ["✕"]),
      ]),
      messagesEl,
      optionsEl,
      el("div", { class: "composer" }, [textarea, sendBtn]),
      el("div", { class: "footer" }, ["Powered by AURA"]),
    ]);

    var bubble = el("button", { class: "bubble", type: "button", "aria-label": "Open chat", onClick: togglePanel }, [
      svgChat(),
    ]);

    var wrap = el("div", { class: "wrap" }, [panel, bubble]);
    shadow.appendChild(wrap);

    var opened = false;
    var conversationToken = storageGet(STORAGE_KEY) || null;
    var greeted = false;
    // The menu node the visible option buttons belong to, sent back so the
    // server knows which choice was picked. Null in free-form (AI) mode.
    var menuNodeId = null;

    function togglePanel() {
      opened = !opened;
      panel.classList.toggle("open", opened);
      if (opened && !greeted) {
        greeted = true;
        // Ask the server for the opening turn. A business running the
        // predefined menu answers with its first question and a set of
        // choices; one running free-form AI returns no options and we fall
        // back to the static greeting below.
        exchange({ message: "" }, null);
      }
      if (opened) textarea.focus();
    }

    function addMessage(text, kind, pending) {
      var node = el("div", { class: "msg " + kind + (pending ? " pending" : "") }, [text]);
      messagesEl.appendChild(node);
      messagesEl.scrollTop = messagesEl.scrollHeight;
      return node;
    }

    function clearOptions() {
      while (optionsEl.firstChild) optionsEl.removeChild(optionsEl.firstChild);
    }

    /* Free text is disabled while a menu is on screen: the predefined flow
       only understands a picked option, so typing would quietly bounce the
       visitor back to the first question. */
    function setComposerEnabled(enabled) {
      textarea.disabled = !enabled;
      sendBtn.disabled = !enabled;
      textarea.placeholder = enabled ? "Type a message…" : "Choose an option above";
    }

    function renderOptions(options) {
      clearOptions();
      if (!options || !options.length) {
        setComposerEnabled(true);
        return;
      }
      setComposerEnabled(false);
      options.forEach(function (option) {
        var btn = el("button", { type: "button" }, [option.label]);
        btn.addEventListener("click", function () {
          exchange({ message: "", node_id: menuNodeId, option_id: option.id }, option.label);
        });
        optionsEl.appendChild(btn);
      });
    }

    /**
     * One turn of conversation, whether the visitor typed it or picked it.
     * `displayText` is what shows as their message — null for the silent
     * opening fetch, which has no visitor turn to show.
     */
    function exchange(payload, displayText) {
      clearOptions();
      if (displayText) addMessage(displayText, "user");
      sendBtn.disabled = true;
      var pendingNode = addMessage("…", "bot", true);

      payload.conversation_token = conversationToken;

      fetch(API_URL + "/api/v1/public/chat/" + encodeURIComponent(ORG_ID), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          return res.json().then(function (body) {
            return { ok: res.ok, body: body };
          });
        })
        .then(function (result) {
          pendingNode.remove();
          if (!result.ok) {
            // The opening fetch failing shouldn't greet a visitor with an
            // error — fall back to the static hello and a usable composer.
            if (!displayText) {
              addMessage(GREETING, "bot");
              setComposerEnabled(true);
              return;
            }
            addMessage((result.body && result.body.error) || SEND_ERROR, "bot");
            setComposerEnabled(true);
            return;
          }
          if (result.body.conversation_token) {
            conversationToken = result.body.conversation_token;
            storageSet(STORAGE_KEY, conversationToken);
          }
          addMessage(result.body.reply || "", "bot");
          menuNodeId = result.body.node_id || null;
          renderOptions(result.body.options);
        })
        .catch(function () {
          pendingNode.remove();
          if (!displayText) {
            addMessage(GREETING, "bot");
          } else {
            addMessage(SEND_ERROR, "bot");
          }
          setComposerEnabled(true);
        });
    }

    function send() {
      var text = textarea.value.trim();
      if (!text) return;
      textarea.value = "";
      textarea.style.height = "auto";
      exchange({ message: text }, text);
    }

    sendBtn.addEventListener("click", send);
    textarea.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
    textarea.addEventListener("input", function () {
      textarea.style.height = "auto";
      textarea.style.height = Math.min(textarea.scrollHeight, 80) + "px";
    });

    // A returning visitor with a saved thread sees the bubble but not a
    // forced-open panel — opening is always their choice.
  }

  function svgChat() {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    var path = document.createElementNS(ns, "path");
    path.setAttribute(
      "d",
      "M4 4h16v11H7l-3 3V4z"
    );
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.8");
    path.setAttribute("stroke-linejoin", "round");
    svg.appendChild(path);
    return svg;
  }

  function svgSend() {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", "16");
    svg.setAttribute("height", "16");
    svg.setAttribute("fill", "none");
    var path = document.createElementNS(ns, "path");
    path.setAttribute("d", "M3 12l18-8-7 18-2.5-7L3 12z");
    path.setAttribute("stroke", "currentColor");
    path.setAttribute("stroke-width", "1.8");
    path.setAttribute("stroke-linejoin", "round");
    path.setAttribute("stroke-linecap", "round");
    svg.appendChild(path);
    return svg;
  }

  function init() {
    fetch(API_URL + "/api/v1/public/chat/" + encodeURIComponent(ORG_ID) + "/status")
      .then(function (res) {
        return res.ok ? res.json() : { available: false };
      })
      .then(function (status) {
        if (status && status.available) mount();
        // available === false (wrong id, or the owner switched it off):
        // render nothing, no error, nothing visible on the host page.
      })
      .catch(function () {
        // Network/API problem: same rule — fail silently rather than break
        // the host page.
      });
  }

  if (document.body) init();
  else document.addEventListener("DOMContentLoaded", init);
})();
