// Admin dashboard: bar chart of expected in-office headcount for the next few days.
(function () {
  "use strict";

  var canvas = document.getElementById("forecast-chart");
  var dataEl = document.getElementById("forecast-data");
  if (!canvas || !dataEl) return;
  if (typeof Chart === "undefined") {
    canvas.parentNode.innerHTML = '<p class="muted">Chart unavailable (Chart.js could not be loaded). The table below has the same numbers.</p>';
    return;
  }

  var data = JSON.parse(dataEl.textContent);
  var accent = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#0f766e";
  var muted = "#cbd5e1";

  new Chart(canvas, {
    type: "bar",
    data: {
      labels: data.labels,
      datasets: [{
        label: "Expected in office",
        data: data.in_office,
        backgroundColor: data.closed.map(function (c) { return c ? muted : accent; }),
        borderRadius: 4,
        maxBarThickness: 48
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              return data.closed[ctx.dataIndex] ? "Weekend — office closed" : ctx.parsed.y + " expected in office";
            }
          }
        }
      },
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0 } },
        x: { grid: { display: false } }
      }
    }
  });
})();
