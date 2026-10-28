// CSSOM overrides preserve the application's style-src policy. Keep original
// declarations, including priorities, and cover modal content added later.
export async function applyTextSpacing(page) {
  return page.evaluateHandle(() => {
    const originals = new Map();
    const apply = node => {
      if (!node.style || originals.has(node)) return;
      const properties = [["line-height", "1.5"], ["letter-spacing", ".12em"], ["word-spacing", ".16em"]];
      if (node.tagName === "P") properties.push(["margin-bottom", "2em"]);
      originals.set(node, properties.map(([name]) => [name, node.style.getPropertyValue(name), node.style.getPropertyPriority(name)]));
      for (const [name, value] of properties) node.style.setProperty(name, value, "important");
    };
    document.body.querySelectorAll("*").forEach(apply);
    const observer = new MutationObserver(records => {
      for (const record of records) for (const node of record.addedNodes) {
        if (node.nodeType !== Node.ELEMENT_NODE) continue;
        apply(node);
        node.querySelectorAll("*").forEach(apply);
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    return { originals, observer };
  });
}

export async function restoreTextSpacing(handle) {
  await handle.evaluate(({ originals, observer }) => {
    observer.disconnect();
    for (const [node, properties] of originals) if (node.isConnected) {
      for (const [name, value, priority] of properties) {
        if (value) node.style.setProperty(name, value, priority);
        else node.style.removeProperty(name);
      }
    }
  });
  await handle.dispose();
}
