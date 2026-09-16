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
 *
 * When `locked` is set (the `{text, full, releasable}` payload from Python), the
 * control renders disabled and shows the locked value instead of the draft, on
 * every entry kind including "none" -- the one case where a field appears on a
 * port with no entry kind at all, so the user can see the constant before
 * deciding whether to unlock or trash it.
 */
export default function PortEntry({ entryKind, options, entered, text, error, fallback, locked, onCommit }) {
    const [draft, setDraft] = useState(() => (entered ? text ?? "" : ""));

    // Python re-sends the entry on every redraw; a stale draft must not win.
    useEffect(() => {
        setDraft(entered ? text ?? "" : "");
    }, [entered, text]);

    const dimmed = !locked && !hasContent(draft) && !error;
    const className = [
        "nodrag",
        "port-entry",
        dimmed ? "port-entry--default" : "",
        error && !locked ? "port-entry--error" : "",
        locked ? "port-entry--locked" : "",
    ].filter(Boolean).join(" ");
    // A locked port cannot hold an error -- Python refuses to commit an entry to one --
    // so the title slot carries the full untruncated value for hovering instead.
    const title = locked ? locked.full : (error || undefined);

    if (entryKind === "dropdown") {
        const choices = options || [];
        const shown = locked ? locked.text : (dimmed ? (hasContent(fallback) ? fallback : "") : draft);
        return (
            <select
                className={className}
                title={title}
                disabled={!!locked}
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
        const checked = locked ? locked.text === "True" : (dimmed ? fallback === "True" : draft === "True");
        return (
            <input
                className={className}
                type="checkbox"
                title={title}
                disabled={!!locked}
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
            title={title}
            readOnly={!!locked}
            value={locked ? locked.text : draft}
            placeholder={hasContent(fallback) ? fallback : ""}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
                if (e.key === 'Enter') onCommit(draft);
            }}
            onBlur={() => onCommit(draft)}
        />
    );
}

/**
 * The padlock beside a port label, which is how a user creates and destroys the
 * constant nodes the GUI otherwise hides.
 *
 * A locked port whose value has nowhere to be released to shows a trashcan instead:
 * unlocking it can only delete, and ipywidgets cannot raise a confirmation dialog, so
 * the icon has to carry the warning by itself.
 */
export function LockButton({ locked, canLock, onLock, onUnlock }) {
    if (locked) {
        const trash = !locked.releasable;
        return (
            <button
                className="nodrag port-lock"
                title={trash
                    ? "Delete this fixed input value (this port cannot take typed input)"
                    : "Unlock this value so it can be edited"}
                onClick={onUnlock}
            >
                {trash ? "🗑" : "🔒"}
            </button>
        );
    }
    return (
        <button
            className="nodrag port-lock"
            disabled={!canLock}
            title={canLock
                ? "Lock this value in place as fixed input"
                : "Enter a value before locking it"}
            onClick={onLock}
        >
            🔓
        </button>
    );
}
