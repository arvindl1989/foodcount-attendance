// Employee calendar: FullCalendar month view + a small dialog to set a day's status.
(function () {
  "use strict";

  var el = document.getElementById("calendar");
  if (!el) return;
  if (typeof FullCalendar === "undefined") {
    el.innerHTML = '<p class="dialog-error">The calendar library could not be loaded. Check your internet connection and reload.</p>';
    return;
  }

  var api = el.dataset.api;
  var today = el.dataset.today;                 // YYYY-MM-DD, from the server clock
  var cutoffPassed = el.dataset.cutoffPassed === "true";
  var cutoffLabel = el.dataset.cutoffLabel;
  var csrf = document.querySelector('meta[name="csrf-token"]').content;

  var COLORS = { WFH: "#2563eb", LEAVE: "#ea580c" };
  var LABELS = { WFH: "Work from home", LEAVE: "Leave" };
  var SHORT = { WFH: "WFH", LEAVE: "Leave" };

  var entries = {};      // "YYYY-MM-DD" -> "WFH" | "LEAVE"
  var selectedDate = null;

  var dialog = document.getElementById("day-dialog");
  var dialogTitle = document.getElementById("dialog-title");
  var dialogCurrent = document.getElementById("dialog-current");
  var dialogError = document.getElementById("dialog-error");
  var toastEl = document.getElementById("toast");

  function iso(d) {
    var m = String(d.getMonth() + 1).padStart(2, "0");
    var day = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + m + "-" + day;
  }

  function parseIso(s) {
    var p = s.split("-").map(Number);
    return new Date(p[0], p[1] - 1, p[2]);
  }

  function isWeekend(d) {
    var dow = d.getDay();
    return dow === 0 || dow === 6;
  }

  // Mirrors attendance.edit_block_reason on the server (which has the final say).
  function blockReason(dateStr) {
    if (isWeekend(parseIso(dateStr))) return "Weekends can't be edited.";
    if (dateStr < today) return "Past dates can't be edited.";
    if (dateStr === today && cutoffPassed) return "Today's status is locked after the " + cutoffLabel + " cutoff.";
    return null;
  }

  var toastTimer;
  function toast(message, isError) {
    toastEl.textContent = message;
    toastEl.classList.toggle("toast-error", !!isError);
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.hidden = true; }, 3000);
  }

  function handleAuthError(res) {
    if (res.status === 401) {
      window.location.href = "/";
      return true;
    }
    return false;
  }

  function toEvents(list) {
    var events = [];
    list.forEach(function (e) {
      events.push({ start: e.date, allDay: true, display: "background",
                    backgroundColor: COLORS[e.status], classNames: ["bg-" + e.status.toLowerCase()] });
      events.push({ title: LABELS[e.status], start: e.date, allDay: true,
                    backgroundColor: COLORS[e.status], borderColor: COLORS[e.status],
                    extendedProps: { status: e.status } });
    });
    return events;
  }

  function updateSummary() {
    var start = calendar.view.currentStart;
    var end = calendar.view.currentEnd;
    var wfh = 0, leave = 0, workdays = 0;
    for (var d = new Date(start); d < end; d.setDate(d.getDate() + 1)) {
      if (isWeekend(d)) continue;
      workdays++;
      var s = entries[iso(d)];
      if (s === "WFH") wfh++;
      else if (s === "LEAVE") leave++;
    }
    document.getElementById("summary-title").textContent =
      start.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    document.getElementById("sum-wfh").textContent = wfh;
    document.getElementById("sum-leave").textContent = leave;
    document.getElementById("sum-office").textContent = workdays - wfh - leave;
  }

  function openDay(dateStr) {
    var reason = blockReason(dateStr);
    if (reason) { toast(reason, true); return; }
    selectedDate = dateStr;
    var current = entries[dateStr] || null;
    dialogTitle.textContent = parseIso(dateStr).toLocaleDateString(undefined,
      { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    dialogCurrent.textContent = current ? LABELS[current] : "In office";
    dialog.querySelectorAll(".choice").forEach(function (btn) {
      var s = btn.dataset.status;
      btn.classList.toggle("is-current", s === current || (s === "CLEAR" && !current));
      btn.disabled = false;
    });
    dialogError.hidden = true;
    dialog.showModal();
  }

  function save(status) {
    var buttons = dialog.querySelectorAll(".choice");
    buttons.forEach(function (b) { b.disabled = true; });
    fetch(api, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "Accept": "application/json" },
      body: JSON.stringify({ date: selectedDate, status: status })
    })
      .then(function (res) {
        if (handleAuthError(res)) return null;
        return res.json().catch(function () { return {}; }).then(function (body) {
          if (!res.ok) throw new Error(body.error || "Could not save (HTTP " + res.status + ").");
          return body;
        });
      })
      .then(function (body) {
        if (!body) return;
        dialog.close();
        toast(body.status ? "Saved: " + LABELS[body.status] : "Cleared — in office");
        calendar.refetchEvents();
      })
      .catch(function (err) {
        dialogError.textContent = err.message;
        dialogError.hidden = false;
        buttons.forEach(function (b) { b.disabled = false; });
      });
  }

  dialog.querySelectorAll(".choice").forEach(function (btn) {
    btn.addEventListener("click", function () { save(btn.dataset.status); });
  });
  dialog.querySelector("[data-close]").addEventListener("click", function () { dialog.close(); });

  var calendar = new FullCalendar.Calendar(el, {
    initialView: "dayGridMonth",
    initialDate: today,
    now: today,
    firstDay: 1,
    height: "auto",
    fixedWeekCount: false,
    headerToolbar: { left: "prev,next today", center: "title", right: "" },
    eventDisplay: "block",
    dayMaxEvents: true,

    events: function (info, success, failure) {
      var url = api + "?start=" + info.startStr.slice(0, 10) + "&end=" + info.endStr.slice(0, 10);
      fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
        .then(function (res) {
          if (handleAuthError(res)) return [];
          if (!res.ok) throw new Error("Could not load your entries (HTTP " + res.status + ").");
          return res.json();
        })
        .then(function (list) {
          entries = {};
          list.forEach(function (e) { entries[e.date] = e.status; });
          success(toEvents(list));
          updateSummary();
        })
        .catch(function (err) { toast(err.message, true); failure(err); });
    },

    dayCellClassNames: function (arg) {
      var d = iso(arg.date);
      var classes = [];
      if (isWeekend(arg.date)) classes.push("is-weekend");
      else if (blockReason(d)) classes.push("is-locked");
      else classes.push("is-editable");
      return classes;
    },

    // Full label on wide screens, short one on phones (toggled in CSS).
    eventContent: function (arg) {
      var status = arg.event.extendedProps.status;
      if (!status) return true;
      return { html: '<span class="ev-long">' + LABELS[status] + '</span><span class="ev-short">' + SHORT[status] + "</span>" };
    },

    dateClick: function (info) { openDay(info.dateStr); },
    eventClick: function (info) { openDay(info.event.startStr.slice(0, 10)); }
  });

  calendar.render();
})();
