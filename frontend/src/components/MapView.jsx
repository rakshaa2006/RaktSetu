import { useEffect, useRef, useState } from "react";

const COLORS = { blood_bank: "#B71C2C", donor: "#1F2328", hospital: "#1B7F3B" };

// Optional map (Leaflet + OpenStreetMap). It needs internet for map tiles; the lists on each page
// always work without it. Straight-line distance is never presented as a road distance.
export default function MapView({ points, hospital }) {
  const ref = useRef(null);
  const [failed, setFailed] = useState(false);
  const key = JSON.stringify([points, hospital]);

  useEffect(() => {
    let map = null;
    let cancelled = false;
    (async () => {
      try {
        const leaflet = await import("leaflet");
        await import("leaflet/dist/leaflet.css");
        const L = leaflet.default || leaflet;
        if (cancelled || !ref.current) return;
        map = L.map(ref.current, { scrollWheelZoom: false });
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 18,
          attribution: "&copy; OpenStreetMap contributors",
        }).addTo(map);
        const bounds = [];
        const add = (p, kind, radius) => {
          if (p.lat === null || p.lat === undefined || p.lng === null || p.lng === undefined) return;
          L.circleMarker([p.lat, p.lng], {
            radius, color: "#ffffff", weight: 2, fillColor: COLORS[kind], fillOpacity: 0.95,
          }).addTo(map).bindTooltip(p.label);
          bounds.push([p.lat, p.lng]);
        };
        points.forEach((p) => add(p, p.kind, 9));
        if (hospital) add(hospital, "hospital", 12);
        if (bounds.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 });
        else map.setView([18.52, 73.85], 11);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      if (map) map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (failed) return <p className="muted">The map could not load. The list below shows the same options.</p>;
  return (
    <div>
      <div ref={ref} className="map" role="region" aria-label="Map of options. The same options are listed below the map." />
      <p className="small muted">
        Map key: dark red = blood bank, charcoal = donor, green = hospital. Tiles come from OpenStreetMap and need an
        internet connection. Distances are straight-line only.
      </p>
    </div>
  );
}
