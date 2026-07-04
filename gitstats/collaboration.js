/**
 * GitStats — Collaboration Network Force-Directed Graph Engine
 *
 * Renders a force-directed graph showing collaboration patterns among authors.
 * Nodes = authors (size by files touched), edges = collaboration (thickness by shared files).
 *
 * Expects global variables (inlined in HTML):
 *   COLLAB_NODES  — Array of {id, fileCount, size, score}
 *   COLLAB_LINKS  — Array of {source, target, weight, type}
 *
 * Also requires getCSSVar() from the theme toggle script.
 */
(function () {
  var svgEl = document.getElementById("collab-svg");
  if (!svgEl) return;
  var ns = "http://www.w3.org/2000/svg";
  var width = svgEl.parentElement.clientWidth || 960;
  var height = 520;
  svgEl.setAttribute("viewBox", "0 0 " + width + " " + height);

  var nodes = typeof COLLAB_NODES !== "undefined" ? COLLAB_NODES : [];
  var links = typeof COLLAB_LINKS !== "undefined" ? COLLAB_LINKS : [];

  if (!nodes.length) return;

  var COLORS = [
    "#5b8dee",
    "#1a7f37",
    "#cf222e",
    "#8250df",
    "#e16f24",
    "#0550ae",
    "#9a6700",
    "#656d76",
    "#297c6b",
    "#b08800",
  ];

  var tooltip = document.getElementById("collab-tooltip");

  // Initialize node positions
  var cx = width / 2,
    cy = height / 2;
  nodes.forEach(function (n) {
    n.x = cx + (Math.random() - 0.5) * width * 0.7;
    n.y = cy + (Math.random() - 0.5) * height * 0.7;
    n.vx = 0;
    n.vy = 0;
    n.fixed = false;
  });

  // Map link indices to node references
  links.forEach(function (l) {
    l.sourceNode = nodes[l.source];
    l.targetNode = nodes[l.target];
  });

  // Build SVG elements
  var g = document.createElementNS(ns, "g");
  svgEl.appendChild(g);

  // Line elements for edges
  var lineEls = [];
  links.forEach(function (l) {
    var el = document.createElementNS(ns, "line");
    el.setAttribute("stroke", "#999");
    el.setAttribute("stroke-opacity", "0.4");
    el.setAttribute(
      "stroke-width",
      Math.max(1, Math.sqrt(l.weight) * 0.8).toString()
    );
    g.appendChild(el);
    lineEls.push(el);
  });

  // Node groups (circle + text)
  var nodeEls = [];
  nodes.forEach(function (n, i) {
    var ng = document.createElementNS(ns, "g");
    ng.style.cursor = "grab";

    var circle = document.createElementNS(ns, "circle");
    circle.setAttribute("r", n.size);
    circle.setAttribute("fill", COLORS[i % COLORS.length]);
    circle.setAttribute("stroke", "#fff");
    circle.setAttribute("stroke-width", "1.5");
    circle.setAttribute("opacity", "0.85");
    ng.appendChild(circle);

    var text = document.createElementNS(ns, "text");
    text.textContent = n.id;
    var textColor = getCSSVar("--text-color") || "#211e1e";
    text.setAttribute("x", n.size + 4);
    text.setAttribute("y", 4);
    text.setAttribute("font-size", "11px");
    text.setAttribute(
      "font-family",
      '-apple-system, BlinkMacSystemFont, "Segoe UI", monospace'
    );
    text.setAttribute("fill", textColor);
    text.setAttribute("pointer-events", "none");
    ng.appendChild(text);

    g.appendChild(ng);
    nodeEls.push(ng);

    // Hover tooltip
    ng.addEventListener("mouseover", function (e) {
      var collabWith = links
        .filter(function (l) {
          return l.sourceNode === n || l.targetNode === n;
        })
        .sort(function (a, b) {
          return b.weight - a.weight;
        })
        .slice(0, 10);

      var tipHtml =
        "<strong>" +
        n.id +
        '</strong><br/>' +
        "Files touched: " +
        n.fileCount +
        "<br/>" +
        "Collaboration score: " +
        n.score +
        '<br/>' +
        '<hr style="margin:4px 0"/>' +
        "<em>Top collaborators:</em><br/>";

      if (collabWith.length === 0) {
        tipHtml += '<span style="color:#888">(no collaborators shown)</span>';
      } else {
        collabWith.forEach(function (l) {
          var other =
            l.sourceNode === n ? l.targetNode.id : l.sourceNode.id;
          tipHtml += other + " (" + l.weight + " files)<br/>";
        });
      }

      var container = document.getElementById("collab-graph");
      var cr = container.getBoundingClientRect();
      tooltip.innerHTML = tipHtml;
      tooltip.style.display = "block";
      var tipW = tooltip.offsetWidth;
      var spaceRight = cr.right - e.clientX - 15;
      var left;
      if (spaceRight < tipW) {
        left = e.clientX - cr.left - tipW - 15;
      } else {
        left = e.clientX - cr.left + 15;
      }
      tooltip.style.left = Math.max(4, left) + "px";
      tooltip.style.top = e.clientY - cr.top - 10 + "px";
    });
    ng.addEventListener("mouseout", function () {
      tooltip.style.display = "none";
    });

    // Drag with viewBox coordinate mapping
    ng.addEventListener("mousedown", function (e) {
      e.preventDefault();
      n.fixed = true;
      ng.style.cursor = "grabbing";
      var rect = svgEl.getBoundingClientRect();
      var dragScaleX = width / rect.width;
      var dragScaleY = height / rect.height;
      var dragStartX = e.clientX;
      var dragStartY = e.clientY;
      var startX = n.x;
      var startY = n.y;

      function onMove(ev) {
        var dx = (ev.clientX - dragStartX) * dragScaleX;
        var dy = (ev.clientY - dragStartY) * dragScaleY;
        n.x = Math.max(20, Math.min(width - 20, startX + dx));
        n.y = Math.max(20, Math.min(height - 20, startY + dy));
        render();
      }

      function onUp() {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        ng.style.cursor = "grab";
        setTimeout(function () {
          n.fixed = false;
        }, 800);
      }
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  });

  // Force simulation
  var alpha = 1.0;
  var alphaMin = 0.003;
  var alphaDecay = 0.015;
  var repulsion = 8000;
  var attraction = 0.04;
  var centering = 0.003;
  var friction = 0.55;

  function tick() {
    // Repulsion (all node pairs)
    for (var i = 0; i < nodes.length; i++) {
      for (var j = i + 1; j < nodes.length; j++) {
        var a = nodes[i],
          b = nodes[j];
        var dx = b.x - a.x,
          dy = b.y - a.y;
        var dist = Math.sqrt(dx * dx + dy * dy) || 1;
        var force = (repulsion * alpha) / (dist * dist + 1);
        a.vx -= (force * dx) / dist;
        a.vy -= (force * dy) / dist;
        b.vx += (force * dx) / dist;
        b.vy += (force * dy) / dist;
      }
    }

    // Attraction (along edges)
    for (var k = 0; k < links.length; k++) {
      var s = links[k].sourceNode,
        t = links[k].targetNode;
      var dx = t.x - s.x,
        dy = t.y - s.y;
      var dist = Math.sqrt(dx * dx + dy * dy) || 1;
      var force = (dist - 120) * attraction * alpha;
      s.vx += (force * dx) / dist;
      s.vy += (force * dy) / dist;
      t.vx -= (force * dx) / dist;
      t.vy -= (force * dy) / dist;
    }

    // Centering
    for (var i2 = 0; i2 < nodes.length; i2++) {
      var n2 = nodes[i2];
      n2.vx += (cx - n2.x) * centering * alpha;
      n2.vy += (cy - n2.y) * centering * alpha;
    }

    // Update positions
    for (var i3 = 0; i3 < nodes.length; i3++) {
      var n3 = nodes[i3];
      if (n3.fixed) continue;
      n3.vx *= friction;
      n3.vy *= friction;
      n3.x += n3.vx;
      n3.y += n3.vy;
      n3.x = Math.max(20, Math.min(width - 20, n3.x));
      n3.y = Math.max(20, Math.min(height - 20, n3.y));
    }

    render();

    alpha -= alphaDecay;
    if (alpha > alphaMin) {
      requestAnimationFrame(tick);
    }
  }

  function render() {
    for (var ri = 0; ri < links.length; ri++) {
      var l = links[ri];
      lineEls[ri].setAttribute("x1", l.sourceNode.x);
      lineEls[ri].setAttribute("y1", l.sourceNode.y);
      lineEls[ri].setAttribute("x2", l.targetNode.x);
      lineEls[ri].setAttribute("y2", l.targetNode.y);
    }
    for (var rj = 0; rj < nodes.length; rj++) {
      nodeEls[rj].setAttribute(
        "transform",
        "translate(" + nodes[rj].x + "," + nodes[rj].y + ")"
      );
    }
  }

  tick();
  render();

  // Handle theme changes
  document.addEventListener("themechange", function () {
    var c = getCSSVar("--text-color") || "#211e1e";
    nodeEls.forEach(function (ng) {
      var t = ng.querySelector("text");
      if (t) t.setAttribute("fill", c);
    });
  });
})();
