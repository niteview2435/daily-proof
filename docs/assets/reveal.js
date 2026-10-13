/* Scroll-triggered reveal, adapted from the Web5 ideal.
   Text inside .fragmentize is split into sentence fragments that fade in
   one after another; block-level .reveal elements fade in as a whole. */
(function () {
  function fragmentize(el) {
    var raw = el.innerHTML.replace(/<br\s*\/?>/gi, "[[BR]]");
    // Split after Japanese/Latin sentence punctuation.
    var segs = raw.split(/(?<=[。．，、！!？?])/);
    el.innerHTML = segs
      .map(function (seg, i) {
        seg = seg.replace(/\[\[BR\]\]/g, "<br>");
        if (seg.trim() === "") return seg;
        return (
          '<span class="fragment" data-fragment-delay="' +
          i * 70 +
          '">' +
          seg +
          "</span>"
        );
      })
      .join("");
  }

  // Fragmentize the text content of each paragraph/list item.
  document
    .querySelectorAll(".fragmentize p, .fragmentize li")
    .forEach(fragmentize);

  // Render math after fragmentizing (math never contains sentence punctuation,
  // so it stays intact within a single fragment).
  if (window.renderMathInElement) {
    window.renderMathInElement(document.body, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\[", right: "\\]", display: true },
        { left: "\\(", right: "\\)", display: false },
      ],
      throwOnError: false,
    });
  }

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        var delay = el.dataset.delay || el.dataset.fragmentDelay;
        if (delay) el.style.transitionDelay = delay + "ms";
        el.classList.add("in-view");
        observer.unobserve(el);
      });
    },
    { rootMargin: "0px 0px -8% 0px", threshold: 0.1 }
  );

  document
    .querySelectorAll(".reveal, .fragment")
    .forEach(function (el) {
      observer.observe(el);
    });
})();
