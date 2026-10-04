export function createNativeSnapshotOrder() {
  let current = null;
  const retiredEpochs = new Set();

  return (next) => {
    if (!next || typeof next !== "object") return false;
    if (current) {
      if (next.epoch === current.epoch) {
        if (next.revision < current.revision) return false;
      } else {
        if (retiredEpochs.has(next.epoch)) return false;
        retiredEpochs.add(current.epoch);
      }
    }
    current = { epoch: next.epoch, revision: next.revision };
    return true;
  };
}
