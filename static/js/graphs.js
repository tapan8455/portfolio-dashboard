// Function to fetch and update stock/crypto graphs
function updateGraph(symbol, period, elementId) {
  fetch(`/get_graph/${symbol}/${period}`)
    .then(response => response.json())
    .then(data => {
      var layout = {
        title: {
          text: `${symbol} (${period})`,
          font: {
            family: 'Helvetica, sans-serif',
            size: 20,
            color: '#333'
          },
          xref: 'paper'
        },
        xaxis: {
          title: {
            text: 'Date',
            font: {
              family: 'Helvetica, sans-serif',
              size: 14,
              color: '#333'
            }
          },
          showgrid: true,
          gridcolor: '#e9e9e9',
          tickfont: { family: 'Helvetica, sans-serif', size: 12, color: '#333' }
        },
        yaxis: {
          title: {
            text: 'Price',
            font: {
              family: 'Helvetica, sans-serif',
              size: 14,
              color: '#333'
            }
          },
          showgrid: true,
          gridcolor: '#e9e9e9',
          tickfont: { family: 'Helvetica, sans-serif', size: 12, color: '#333' }
        },
        margin: { l: 50, r: 20, t: 60, b: 50 },
        paper_bgcolor: '#f4f8fb',
        plot_bgcolor: '#f4f8fb'
      };

      Plotly.newPlot(elementId, [{
        x: data.x,
        y: data.y,
        type: 'scatter',
        mode: 'lines',
        line: { color: '#007bff', width: 3 }
      }], layout, { responsive: true });
    })
    .catch(err => console.error('Graph fetch error:', err));
}
  

// Auto-update graphs every 10 seconds for real-time tracking
setInterval(() => {
    document.querySelectorAll(".asset-card").forEach(card => {
        let symbol = card.querySelector("h3").textContent;
        updateGraph(symbol, '1mo');
    });
}, 10000);

// Handle Dark/Light Mode Chart Updates
function applyDarkModeCharts(isDarkMode) {
    let update = { plot_bgcolor: isDarkMode ? "#121212" : "#ffffff", paper_bgcolor: isDarkMode ? "#121212" : "#ffffff" };
    document.querySelectorAll(".asset-card").forEach(card => {
        let symbol = card.querySelector("h3").textContent;
        Plotly.relayout(`graph-${symbol}`, update);
    });
}