import React, { useEffect, useState } from "react";

/** Whether a port of this kind can be typed into at all. */
export function canEnterValue(entryKind) {
    return entryKind !== "none" && entryKind !== undefined;
}

/** Whether a field holds something the user meant. False and 0 count; "" does not. */
function hasContent(value) {
    return value !== null && value !== undefined && value !== "";
}

/**
 * One value entry widget: a text box, a checkbox or a dropdown, depending on
 * entryKind. It does no parsing: Python owns the type hint, so the raw text goes
 * over the wire and comes back either normalized or with an error.
 *
 * While nothing is entered the widget is dimmed and shows `fallback`, the port's
 * own default, to say that the default is what will be used.
 */
export default function PortEntry({ entryKind, options, entered, text, error, fallback, onCommit }) {
    const [draft, setDraft] = useState(() => (entered ? text ?? "" : ""));

    // Python re-sends the entry on every redraw; a stale draft must not win.
    useEffect(() => {
        setDraft(entered ? text ?? "" : "");
    }, [entered, text]);

    const dimmed = !hasContent(draft) && !error;
    const className = [
        "nodrag",
        "port-entry",
        dimmed ? "port-entry--default" : "",
        error ? "port-entry--error" : "",
    ].filter(Boolean).join(" ");

    if (entryKind === "dropdown") {
        const choices = options || [];
        const shown = dimmed ? (hasContent(fallback) ? fallback : "") : draft;
        return (
            <select
                className={className}
                title={error || undefined}
                value={shown}
                onChange={(e) => {
                    setDraft(e.target.value);
                    onCommit(e.target.value);
                }}
            >
                <option value="" style={{ fontSize: '12px' }}>Select</option>
                {choices.map((option, idx) => (
                    <option key={idx} value={option} style={{ fontSize: '12px' }}>
                        {option}
                    </option>
                ))}
            </select>
        );
    }

    if (entryKind === "checkbox") {
        const checked = dimmed ? fallback === "True" : draft === "True";
        return (
            <input
                className={className}
                type="checkbox"
                title={error || undefined}
                checked={checked}
                onChange={(e) => {
                    const next = e.target.checked ? "True" : "False";
                    setDraft(next);
                    onCommit(next);
                }}
            />
        );
    }

    return (
        <input
            className={className}
            type="text"
            title={error || undefined}
            value={draft}
            placeholder={hasContent(fallback) ? fallback : ""}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
                if (e.key === 'Enter') onCommit(draft);
            }}
            onBlur={() => onCommit(draft)}
        />
    );
}
