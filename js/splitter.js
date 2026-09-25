import './splitter.css';

// Drag the bar to set `ratio`: the fraction of the enclosing box right of the pointer.
function render({ model, el }) {
  const bar = document.createElement("div");
  bar.className = "pyironflow-splitter";
  bar.dataset.testid = "splitter";
  el.appendChild(bar);

  let frame = null;
  let clientX = 0;

  function update() {
    frame = null;
    const box = bar.closest(".widget-hbox") ?? el.parentElement;
    const { left, width } = box.getBoundingClientRect();
    if (width > 0) {
      model.set("ratio", 1 - (clientX - left) / width);
      model.save_changes();
    }
  }

  bar.addEventListener("pointerdown", (event) => {
    bar.setPointerCapture(event.pointerId);
    bar.classList.add("dragging");
    event.preventDefault();
  });
  bar.addEventListener("pointermove", (event) => {
    if (!bar.hasPointerCapture(event.pointerId)) return;
    clientX = event.clientX;
    frame ??= requestAnimationFrame(update);
  });
  const release = (event) => {
    bar.releasePointerCapture(event.pointerId);
    bar.classList.remove("dragging");
  };
  bar.addEventListener("pointerup", release);
  bar.addEventListener("pointercancel", release);
}

export default { render };
