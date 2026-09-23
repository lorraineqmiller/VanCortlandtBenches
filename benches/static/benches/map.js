(function () {
  var el = document.getElementById("map");
  if (!el || !window.L) return;

  var css = getComputedStyle(document.documentElement);
  var AVAILABLE = css.getPropertyValue("--deep-sage").trim() || "#4F6B4A";
  var ADOPTED = css.getPropertyValue("--muted").trim() || "#8A8F85";

  // Van Cortlandt Park, the Bronx.
  var map = L.map(el, { scrollWheelZoom: false }).setView([40.897, -73.886], 15);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  var clusters = L.markerClusterGroup({
    disableClusteringAtZoom: 18,
    maxClusterRadius: 45,
    showCoverageOnHover: false,
    iconCreateFunction: function (cluster) {
      var n = cluster.getChildCount();
      var size = n < 10 ? 30 : n < 100 ? 38 : 46;
      return L.divIcon({
        html: "<span>" + n + "</span>",
        className: "bench-cluster",
        iconSize: L.point(size, size),
      });
    },
  });
  map.addLayer(clusters);

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function formatDate(iso) {
    var p = iso.split("-");
    return new Date(+p[0], +p[1] - 1, +p[2]).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  }

  function popup(p) {
    var html = '<div class="popup"><h3>' + esc(p.code) + "</h3><p>" + esc(p.area) + "</p><p><strong>" + esc(p.status) + "</strong></p>";
    if (p.adopter) {
      html += "<p>Adopted by " + esc(p.adopter) + "</p><p>Term ends " + esc(formatDate(p.term_end)) + "</p>";
    }
    return html + '<p><a href="' + esc(p.url) + '">View bench →</a></p></div>';
  }

  fetch(el.dataset.geojson)
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var layer = L.geoJSON(data, {
        pointToLayer: function (f, latlng) {
          var available = f.properties.status === "Available";
          return L.circleMarker(latlng, {
            radius: 7,
            weight: 1.5,
            color: "#FFFFFF",
            fillColor: available ? AVAILABLE : ADOPTED,
            fillOpacity: 0.95,
          });
        },
        onEachFeature: function (f, l) {
          l.bindPopup(popup(f.properties));
          l.bindTooltip(f.properties.code + " · " + f.properties.status);
        },
      });
      clusters.addLayer(layer);
      if (data.features.length) map.fitBounds(layer.getBounds(), { padding: [20, 20], maxZoom: 17 });
    })
    .catch(function () {
      el.insertAdjacentHTML("afterend", '<p class="error">The map could not be loaded. The table below lists every bench.</p>');
    });
})();
