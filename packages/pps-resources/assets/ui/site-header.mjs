export function initializeSiteHeader(header, themeToggle) {
  const phone = window.matchMedia("(max-width: 760px)");
  const stickyDesktop = window.matchMedia("(width > 1400px)");
  const sidebar = themeToggle?.parentElement;
  const nav = header.querySelector(".site-tab-list:not([hidden])");

  function positionThemeToggle() {
    if (!themeToggle) return;
    const parent = phone.matches ? nav : sidebar;
    if (themeToggle.parentElement === parent) return;
    const focused = document.activeElement === themeToggle;
    parent.append(themeToggle);
    if (focused) themeToggle.focus({ preventScroll: true });
  }

  function updateHeaderHeight() {
    const height = (phone.matches ? nav : header).getBoundingClientRect().height;
    const scrollWithPage = phone.matches && height > window.innerHeight / 3;
    header.toggleAttribute("data-scroll-with-page", scrollWithPage);
    const pinned = (phone.matches || stickyDesktop.matches) && !scrollWithPage;
    document.documentElement.style.setProperty("--topbar-height", `${pinned ? height : 0}px`);
  }

  positionThemeToggle();
  updateHeaderHeight();
  phone.addEventListener("change", positionThemeToggle);
  window.addEventListener("resize", updateHeaderHeight);
  const resize = new ResizeObserver(updateHeaderHeight);
  resize.observe(header, { box: "border-box" });
  resize.observe(nav, { box: "border-box" });
}
