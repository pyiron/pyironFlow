// Commands carry a human-readable timestamp plus a counter. The counter matters:
// `commands` is a synced traitlet, so setting it to the value it already holds
// fires no change and never reaches Python -- which is what two clicks within the
// same second would otherwise do.
let commandCount = 0;
export const now = () => `@ ${new Date().toLocaleString()} #${++commandCount}`;
