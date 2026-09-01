// Iris login page — submits the panel password to /login and follows the
// session cookie into the panel. The <form> wrapper gives free Enter-to-submit
// and proper semantics; preventDefault() stops the native POST so fetch() handles it.
(function () {
  "use strict";

  var inp = document.getElementById("pw");
  var btn = document.getElementById("go");
  var err = document.getElementById("err");

  function show(msg) {
    err.textContent = msg;
    err.classList.add("show");
  }

  function clearError() {
    err.classList.remove("show");
    err.textContent = "";
  }

  function setBusy(busy) {
    btn.disabled = busy;
    btn.textContent = busy ? "Connecting…" : "Connect";
  }

  function submit() {
    var password = inp.value || "";
    if (!password) {
      show("Enter the panel password.");
      inp.focus();
      return;
    }
    inp.value = ""; // Immediately clear cleartext password from input DOM element
    clearError();
    setBusy(true);

    fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: password }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, status: res.status, data: data };
        });
      })
      .then(function (res) {
        if (res.ok && res.data && res.data.ok) {
          var tok = res.data.token || "";
          if (tok) {
            try { localStorage.setItem("iris_session", tok); } catch (_) {}
            window.location.href = "/?session=" + encodeURIComponent(tok);
          } else {
            window.location.href = "/";
          }
          return;
        }
        var msg = "Incorrect password.";
        var e = res.data && res.data.error;
        if (e === "no_password") {
          msg = "No panel password is set yet. Set one in Iris Settings on the PC, then try again.";
        } else if (e === "too many attempts") {
          msg = "Too many attempts. Wait a minute and try again.";
        } else if (e === "password_unavailable") {
          msg = "Password pairing is not available on this PC.";
        } else if (res.status === 400) {
          msg = "Enter the panel password.";
        }
        show(msg);
        setBusy(false);
        inp.focus();
      })
      .catch(function () {
        show("Could not reach the panel. Check your connection and try again.");
        setBusy(false);
      });
  }

  document.getElementById("login-form").addEventListener("submit", function (e) {
    e.preventDefault();
    submit();
  });

  var rescanBtn = document.getElementById("rescan-btn");
  if (rescanBtn) {
    rescanBtn.addEventListener("click", function () {
      if (window.IrisAndroid && typeof window.IrisAndroid.rescanQr === "function") {
        window.IrisAndroid.rescanQr();
        return;
      }
      window.location.href = "iris://rescan";
    });
  }

  inp.focus();
})();
