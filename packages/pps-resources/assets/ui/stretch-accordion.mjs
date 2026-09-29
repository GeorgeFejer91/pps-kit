export function bindStretchAccordion(section, heading, button, label) {
  let animation;

  function setExpanded(expanded) {
    button.setAttribute("aria-expanded", String(expanded));
    button.setAttribute("aria-label", `${expanded ? "Collapse" : "Expand"} ${label}`);
    button.title = `${expanded ? "Collapse" : "Expand"} ${label}`;
    for (const child of section.children) {
      if (child !== heading) child.inert = !expanded;
    }
  }

  setExpanded(!section.classList.contains("collapsed"));
  button.addEventListener("click", () => {
    const expanded = button.getAttribute("aria-expanded") !== "true";
    setExpanded(expanded);
    if (animation) {
      animation.reverse();
      return;
    }
    if (matchMedia("(prefers-reduced-motion: reduce)").matches || !section.animate) {
      section.classList.toggle("collapsed", !expanded);
      return;
    }
    const startHeight = section.getBoundingClientRect().height;
    section.classList.toggle("collapsed", !expanded);
    const endHeight = section.getBoundingClientRect().height;
    section.classList.remove("collapsed");
    section.style.overflow = "clip";
    animation = section.animate(
      [{ height: `${startHeight}px` }, { height: `${endHeight}px` }],
      { duration: 180, easing: "ease-in-out" }
    );
    animation.onfinish = () => {
      section.classList.toggle("collapsed", button.getAttribute("aria-expanded") !== "true");
      section.style.removeProperty("overflow");
      animation = undefined;
    };
  });
}
