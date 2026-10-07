// Small enhancements; every page still works without JavaScript.

// Email links are written as "name at domain" in the HTML to reduce spam.
document.querySelectorAll("a.email").forEach((a) => {
  const addr = `${a.dataset.u}@${a.dataset.d}`;
  a.href = `mailto:${addr}`;
  a.textContent = addr;
});

// Publications: live search across title, authors, journal and year.
(() => {
  const input = document.getElementById("pub-filter");
  if (!input) return;
  const items = [...document.querySelectorAll(".pub-section .pub")];
  const total = items.length;
  const count = document.querySelector(".pub-count");
  const empty = document.querySelector(".pub-empty");
  const norm = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  items.forEach((li) => { li.dataset.text = norm(li.textContent.replace(/\s+/g, " ")); });

  const relabelYears = () => {
    document.querySelectorAll(".pub-section").forEach((section) => {
      let last = null;
      section.querySelectorAll(".pub").forEach((li) => {
        const label = li.querySelector(".pub-year");
        if (li.hidden) return;
        const show = li.dataset.year !== last;
        label.textContent = show ? li.dataset.year : "";
        label.toggleAttribute("aria-hidden", !show);
        last = li.dataset.year;
      });
    });
  };

  const apply = () => {
    const terms = norm(input.value).split(/\s+/).filter(Boolean);
    let shown = 0;
    items.forEach((li) => {
      const match = terms.every((t) => li.dataset.text.includes(t));
      li.hidden = !match;
      if (match) shown += 1;
    });
    document.querySelectorAll(".pub-section").forEach((section) => {
      section.hidden = !section.querySelector(".pub:not([hidden])");
    });
    relabelYears();
    count.textContent = terms.length ? `Showing ${shown} of ${total}` : `${total} publications`;
    empty.hidden = shown !== 0;
  };
  input.addEventListener("input", apply);
  apply();
})();

// Photos: enlarge in a dialog, with previous and next.
(() => {
  const dialog = document.querySelector(".lightbox");
  if (!dialog || typeof dialog.showModal !== "function") return;
  const buttons = [...document.querySelectorAll(".gallery-open")];
  const img = dialog.querySelector("img");
  const caption = dialog.querySelector("figcaption");
  let index = 0;

  const show = (i) => {
    index = (i + buttons.length) % buttons.length;
    const thumb = buttons[index].querySelector("img");
    const cap = buttons[index].closest("figure").querySelector("figcaption");
    img.src = thumb.currentSrc || thumb.src;
    img.alt = thumb.alt;
    caption.textContent = cap ? cap.textContent : "";
  };
  buttons.forEach((b, i) => b.addEventListener("click", () => { show(i); dialog.showModal(); }));
  dialog.querySelectorAll("[data-step]").forEach((b) =>
    b.addEventListener("click", () => show(index + Number(b.dataset.step))));
  dialog.querySelector(".lightbox-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
  dialog.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") show(index + 1);
    if (e.key === "ArrowLeft") show(index - 1);
  });
})();
