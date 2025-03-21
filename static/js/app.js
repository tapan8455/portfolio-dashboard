// Live Stock/Crypto Search with Yahoo Finance API
// Live Stock/Crypto Search using Yahoo Finance's Search API
function searchStocks() {
    let query = document.getElementById("symbol").value;
    if (query.length > 1) {
        fetch(`/search_stock?query=${encodeURIComponent(query)}`)
            .then(response => response.json())
            .then(data => {
                let suggestions = document.getElementById("suggestions");
                suggestions.innerHTML = "";
                if (data && data.length > 0) {
                    data.forEach(item => {
                        let li = document.createElement("li");
                        li.textContent = item.name ? `${item.name} (${item.ticker})` : item.ticker;
                        li.onclick = function() {
                            document.getElementById("symbol").value = item.ticker;
                            suggestions.innerHTML = "";
                            suggestions.style.display = "none";
                        };
                        suggestions.appendChild(li);
                    });
                    suggestions.style.display = "block";
                } else {
                    suggestions.style.display = "none";
                }
            })
            .catch(error => {
                console.error("Error fetching suggestions:", error);
            });
    } else {
        document.getElementById("suggestions").style.display = "none";
    }
}


// Toggle Dark/Light Mode
function toggleTheme() {
    document.body.classList.toggle("dark-mode");
    let isDarkMode = document.body.classList.contains("dark-mode");
    localStorage.setItem("darkMode", isDarkMode);
    applyDarkModeCharts(isDarkMode);
}

// Load Theme Preference
window.onload = function() {
    if (localStorage.getItem("darkMode") === "true") {
        document.body.classList.add("dark-mode");
    }
};