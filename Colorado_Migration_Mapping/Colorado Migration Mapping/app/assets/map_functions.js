// ---------------------------------------------------------------------------
// Tab 2 charts (nsd / displacement / speed / elevation) — make double-click
// toggle between "full data extent" (Plotly autorange) and "bio-year window"
// (the layout's stored xaxis.range). Plotly's default is reset-or-autosize
// which only goes one direction once you're at the data extent, so a second
// double-click felt like a no-op.
// ---------------------------------------------------------------------------
(function() {
    var CHART_IDS = ['nsd-plot', 'displacement-plot', 'speed-plot', 'elevation-plot'];
    var wired = new WeakSet();
    // Authoritative bio-year range comes from layout.meta.bioRange, which
    // main.py stamps onto every Tab-2 figure. We no longer guess it from the
    // live xaxis range (autorange padding made zoomed-in data look ~1 year
    // wide and poisoned the cache).
    function getBio(gd) {
        if (gd.layout && gd.layout.meta && gd.layout.meta.bioRange) {
            return gd.layout.meta.bioRange;
        }
        return null;
    }

    function sameRange(a, b) {
        if (!a || !b) return false;
        return String(a[0]) === String(b[0]) && String(a[1]) === String(b[1]);
    }

    function wireChart(gd, chartId) {
        if (wired.has(gd)) return;
        wired.add(gd);
        gd.on('plotly_doubleclick', function() {
            // Toggle based on CURRENT range, not tracked state. If we're
            // currently showing the bio-year window, autorange to data
            // extent. Otherwise, snap back to the bio-year window. Reading the
            // bio range from layout.meta keeps this robust to Dash re-renders.
            var cur = gd.layout && gd.layout.xaxis && gd.layout.xaxis.range
                ? gd.layout.xaxis.range : null;
            var bio = getBio(gd);
            if (bio && sameRange(cur, bio)) {
                Plotly.relayout(gd, {'xaxis.autorange': true});
            } else if (bio) {
                Plotly.relayout(gd, {'xaxis.range': bio, 'xaxis.autorange': false});
            } else {
                Plotly.relayout(gd, {'xaxis.autorange': true});
            }
            return false; // suppress Plotly's default double-click handler
        });
    }

    function findGraphDiv(id) {
        // dcc.Graph(id=...) renders <div id=ID><div class="dash-graph">
        // <div class="js-plotly-plot">...</div></div></div>. The element
        // Plotly attaches its .layout / event API to is the inner
        // .js-plotly-plot. Looking up by ID alone returns the wrapper,
        // which has no .layout — that's why the previous version silently
        // refused to wire.
        var wrapper = document.getElementById(id);
        if (!wrapper) return null;
        if (wrapper.layout && wrapper.on) return wrapper;
        return wrapper.querySelector('.js-plotly-plot');
    }

    function tick() {
        for (var i = 0; i < CHART_IDS.length; i++) {
            var id = CHART_IDS[i];
            var el = findGraphDiv(id);
            if (!el || !el.layout) continue;
            if (!wired.has(el)) {
                wireChart(el, id);
            }
            // Bio range is read live from layout.meta on each double-click, so
            // there's nothing to keep refreshed here.
        }
    }
    setInterval(tick, 500);
})();

window.dashExtensions = window.dashExtensions || {};
window.dashExtensions.default = Object.assign({}, window.dashExtensions.default, {
    seqPointStyle: function(feature, latlng) {
        var c = (feature.properties && feature.properties.c) || '#888';
        return L.circleMarker(latlng, {
            radius: 3, fillColor: c, color: '#000',
            weight: 0.3, fillOpacity: 0.9, opacity: 1
        });
    },
    seqLineStyle: function(feature) {
        return {color: '#fff', weight: 1.5, opacity: 0.35, dashArray: '4 3'};
    },
    // Tab 5 population-use / footprint contour polygons. Colour comes from
    // properties._color (set per-layer by the contours callback); fill opacity
    // scales with the contour % so the high-use core reads darker.
    contourStyle: function(feature) {
        var p = (feature && feature.properties) || {};
        var color = p._color || '#E63946';
        var c = Number(p.contour);
        var op = 0.25;
        if (!isNaN(c)) { op = Math.max(0.12, Math.min(0.6, c / 150)); }
        return {color: color, weight: 1, opacity: 0.85, fillColor: color, fillOpacity: op};
    }
});

// ---------------------------------------------------------------------------
// dcc.RangeSlider tooltip transform: render the slider value (an integer
// day-offset from the bio-year start) as an actual date. Reads the bio-year
// start from window._sliderDateMin, which a clientside callback in main.py
// mirrors from dcc.Store(id="store-slider-date-min").
// ---------------------------------------------------------------------------
window.dccFunctions = window.dccFunctions || {};
window.dccFunctions.dayToDate = function(value) {
    var iso = window._sliderDateMin;
    if (!iso || value == null || isNaN(value)) return String(value);
    var base = new Date(iso);
    if (isNaN(base.getTime())) return String(value);
    var d = new Date(base.getTime() + Number(value) * 86400000);
    var mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    var dd = String(d.getUTCDate()).padStart(2, '0');
    return d.getUTCFullYear() + '-' + mm + '-' + dd;
};

// ---------------------------------------------------------------------------
// Drag-the-middle on Tab 2 sequence range sliders. rc-slider doesn't ship
// this; default behavior is that clicking the track jumps the nearest handle.
// We intercept mousedown on the colored track segment (between the two
// handles) in capture phase, stop rc-slider's own handler, then translate
// pointer movement into equal shifts of both handles via dash_clientside.set_props.
// Window length stays fixed; the pair clamps to [min, max].
// ---------------------------------------------------------------------------
(function installSeqSliderMiddleDrag() {
    if (window._seq_slider_middle_drag_installed) return;
    window._seq_slider_middle_drag_installed = true;

    function onDown(e) {
        if (!e.target) return;
        // Find a .seq-range-slider container the click landed in. This works
        // for any slider implementation (old rc-slider with class hooks, new
        // dash-slider with Radix internals) because we use our own className
        // as the entry point.
        var sliderEl = e.target.closest && e.target.closest('.seq-range-slider');
        if (!sliderEl) return;
        // If the click landed directly on a thumb (role="slider"), let the
        // slider's native handler move that handle — only intercept clicks
        // BETWEEN the two thumbs.
        var thumbHit = e.target.closest && e.target.closest('[role="slider"]');
        if (thumbHit && sliderEl.contains(thumbHit)) return;

        var handles = sliderEl.querySelectorAll('[role="slider"]');
        if (handles.length < 2) return;
        var h0r = handles[0].getBoundingClientRect();
        var h1r = handles[1].getBoundingClientRect();
        var leftEdge = Math.min(h0r.left, h1r.left);
        var rightEdge = Math.max(h0r.right, h1r.right);
        if (e.clientX < leftEdge || e.clientX > rightEdge) return;

        // Walk up to the Dash component div whose id is a JSON-stringified
        // pattern-matching dict (e.g. '{"index":"mig1","type":"seq-range-slider"}').
        var dashEl = sliderEl;
        while (dashEl && !(dashEl.id && dashEl.id.charAt(0) === '{')) {
            dashEl = dashEl.parentElement;
        }
        if (!dashEl) return;
        var idDict;
        try { idDict = JSON.parse(dashEl.id); } catch (err) { return; }

        var v0 = Number(handles[0].getAttribute('aria-valuenow'));
        var v1 = Number(handles[1].getAttribute('aria-valuenow'));
        var minV = Number(handles[0].getAttribute('aria-valuemin'));
        var maxV = Number(handles[0].getAttribute('aria-valuemax'));
        if (isNaN(v0) || isNaN(v1) || isNaN(minV) || isNaN(maxV)) return;
        if (v0 === v1) return;  // nothing to drag — slot is empty
        // Ensure v0 <= v1 regardless of which thumb is "Minimum" / "Maximum".
        if (v0 > v1) { var _t = v0; v0 = v1; v1 = _t; }

        var length = v1 - v0;
        var startX = e.clientX;
        var rect = sliderEl.getBoundingClientRect();
        if (rect.width <= 0 || maxV <= minV) return;
        var pxPerValue = rect.width / (maxV - minV);

        e.preventDefault();
        e.stopPropagation();
        if (typeof e.stopImmediatePropagation === 'function') e.stopImmediatePropagation();

        function onMove(ev) {
            ev.preventDefault();
            var dx = ev.clientX - startX;
            var dv = dx / pxPerValue;
            var newLow = Math.round(v0 + dv);
            if (newLow < minV) newLow = minV;
            if (newLow + length > maxV) newLow = maxV - length;
            var newHigh = newLow + length;
            if (window.dash_clientside && window.dash_clientside.set_props) {
                try {
                    window.dash_clientside.set_props(idDict, { value: [newLow, newHigh] });
                } catch (err) {
                    // Swallow — value will still settle on next render.
                }
            }
        }
        function onUp() {
            document.removeEventListener('pointermove', onMove, true);
            document.removeEventListener('pointerup', onUp, true);
            document.removeEventListener('mousemove', onMove, true);
            document.removeEventListener('mouseup', onUp, true);
        }
        // Listen to both pointer and mouse events — covers rc-slider versions
        // that use either API, and ensures the drag still works if the user
        // releases over a child element.
        document.addEventListener('pointermove', onMove, true);
        document.addEventListener('pointerup', onUp, true);
        document.addEventListener('mousemove', onMove, true);
        document.addEventListener('mouseup', onUp, true);
    }
    // Capture phase on both event types so we run BEFORE rc-slider's handler.
    document.addEventListener('pointerdown', onDown, true);
    document.addEventListener('mousedown', onDown, true);
})();

// ---------------------------------------------------------------------------
// Bridge: Tab 2's MapLibre iframe (in app/assets/maplibre_map.html) sends
// {type:'selection-changed', selected:[...]} via postMessage when the user
// clicks / shift+clicks / shift+drags points. Write that array into the
// store-tab2-selection dcc.Store so server callbacks can read it.
// Requires Dash >= 2.17 (set_props). We're on 4.x, so this is safe.
// ---------------------------------------------------------------------------
(function installSelectionBridge() {
    if (window._tab2_selection_bridge_installed) return;
    window._tab2_selection_bridge_installed = true;
    window.addEventListener('message', function(e) {
        if (!e || !e.data || e.data.type !== 'selection-changed') return;
        var sel = Array.isArray(e.data.selected) ? e.data.selected : [];
        try {
            if (window.dash_clientside && typeof window.dash_clientside.set_props === 'function') {
                window.dash_clientside.set_props('store-tab2-selection', { data: sel });
            }
        } catch (err) {
            // Swallow — the iframe still has a usable local selection state.
            console.warn('Tab2 selection bridge: set_props failed', err);
        }
    });
})();
