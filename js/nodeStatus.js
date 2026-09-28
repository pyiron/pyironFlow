import { useEffect, useState } from "react";

// Mirrors STATUS_SYMBOLS / NOT_RUN in pyironflow/node_info.py; keep the two in step.
const SYMBOLS = { running: "🟨", finished: "🟩", failed: "🟥" };
const NOT_RUN = "⬜";

export const statusSymbol = (status) => SYMBOLS[status] ?? NOT_RUN;

// This node's entry in the `node_statuses` trait, updated live as a run reports progress.
export function useNodeStatus(model, id) {
    const read = () => JSON.parse(model.get("node_statuses"))[id];
    const [status, setStatus] = useState(read);
    useEffect(() => {
        const onChange = () => setStatus(read());
        onChange();
        model.on("change:node_statuses", onChange);
        return () => model.off("change:node_statuses", onChange);
    }, [model, id]);
    return status;
}
