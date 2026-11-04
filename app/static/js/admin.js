// Admin dashboard: bar chart of food count and bus count for the next few days.
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
  var css = getComputedStyle(document.documentElement);
  var accent = css.getPropertyValue("--accent").trim() || "#0f766e";
  var bus = css.getPropertyValue("--bus").trim() || "#7c3aed";

  new Chart(canvas, {
    type: "bar",
    data: {
      labels: data.labels,
      datasets: [{
        label: "Food count (FC)",
        data: data.in_office,
        backgroundColor: accent,
        borderRadius: 4,
        maxBarThickness: 40
      }, {
        label: "Bus count (BC)",
        data: data.bus,
        backgroundColor: bus,
        borderRadius: 4,
        maxBarThickness: 40
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              return data.closed[ctx.dataIndex] ? "Weekend — office closed" : ctx.dataset.label + ": " + ctx.parsed.y;
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
