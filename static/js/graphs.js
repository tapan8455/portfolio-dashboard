function updateSelectedGraph(period) {
  if (!selectedSymbol) return;
  updateGraph(selectedSymbol, period, 'detail-graph');
}

function updateGraph(symbol, period, elementId) {
  fetch(`/get_graph/${symbol}/${period}`)
    .then(res => res.json())
    .then(data => {
      Plotly.newPlot(elementId, [{
        x: data.x,
        y: data.y,
        type: 'scatter',
        mode: 'lines+markers',
        line: { shape: 'spline' }
      }], {
        title: `${symbol} (${period})`,
        margin: { t: 40 }
      }, { responsive: true });
    });
}

function updateDetailView(asset) {
  document.getElementById('detail-symbol').textContent = asset.symbol;
  document.getElementById('detail-price').textContent = `Price: $${asset.current_price} ${asset.currency}`;
  document.getElementById('detail-avg').textContent = `Avg Price: $${asset.avg_price}`;
  const changeEl = document.getElementById('detail-change');
  changeEl.textContent = `Change: ${asset.percentage}%`;
  changeEl.classList.toggle('positive', asset.percentage >= 0);
  changeEl.classList.toggle('negative', asset.percentage < 0);
}

function selectAsset(symbol) {
  selectedSymbol = symbol;
  const asset = portfolioData.find(a => a.symbol === symbol);
  if (asset) {
    document.getElementById('detail-placeholder').classList.add('hidden');
    document.getElementById('detail-container').classList.remove('hidden');
    updateDetailView(asset);
    updateGraph(symbol, '1mo', 'detail-graph');
  }
}

socket.on('update_prices', function (data) {
  portfolioData = data;

  const totalVal = data
  .reduce((sum, asset) => sum + (parseFloat(asset.current_price) || 0), 0)
  .toFixed(2);

  document.getElementById('total-value').textContent = totalVal;

  if (data.length) {
    const best = data.reduce((a, b) => a.percentage > b.percentage ? a : b);
    const worst = data.reduce((a, b) => a.percentage < b.percentage ? a : b);
    document.getElementById('best-performer').textContent = best.symbol;
    document.getElementById('worst-performer').textContent = worst.symbol;
  }

  const assetRows = document.querySelectorAll('.asset-row');
  assetRows.forEach((row, idx) => {
    const asset = data[idx];
    const percent = parseFloat(asset.percentage.toFixed(2));

    row.querySelector('.small-text').textContent = `${asset.currency} ${asset.current_price.toFixed(2)}`;
    const percentEl = row.querySelector('.percentage');
    percentEl.textContent = `${percent}%`;
    percentEl.classList.toggle('positive', percent >= 0);
    percentEl.classList.toggle('negative', percent < 0);

    row.classList.remove('highlight-green', 'highlight-red');
    if (percent >= userPositiveThreshold) {
      row.classList.add('highlight-green');
    } else if (percent <= userNegativeThreshold) {
      row.classList.add('highlight-red');
    }
  });

  if (selectedSymbol) {
    const selected = data.find(a => a.symbol === selectedSymbol);
    if (selected) updateDetailView(selected);
  }
});