import React, { useEffect, useState } from "react";

/** Type kinds the Python side emits, mapped to the widget that can enter one. */
export const inputTypeMap = {
    'str': 'text',
    'int': 'text',
    'float': 'text',
    'int-float': 'text',
    'bool': 'checkbox',
    '_LiteralGenericAlias': 'dropdown',
};

/** Whether a port of this kind can be typed into at all. */
export function canEnterValue(entryKind) {
    return Object.prototype.hasOwnProperty.call(inputTypeMap, entryKind);
}

/** Whether a field holds something the user meant. False and 0 count; "" does not. */
function hasContent(value) {
    return value !== null && value !== undefined && value !== "";
}

/**
 * Render a value for display. JS has no float/int distinction, so a whole-number
 * float (e.g. 0.0, 2.0) prints as "0" or "2" unless we restore the decimal point
 * ourselves. Only ever applied to a genuine `float` port holding a JS number;
 * a string the user is still typing, or an `int-float` port, passes through.
 */
function formatDisplay(value, entryKind) {
    if (entryKind === 'float' && typeof value === 'number' && Number.isInteger(value)) {
        return `${value}.0`;
    }
    return String(value);
}

/** Coerce the string a text field yields into the kind the hint asks for. */
export function convertInput(value, entryKind) {
    if (typeof value === 'string' && value.trim() === 'None') return null;

    switch (entryKind) {
        case 'int': {
            const intValue = parseInt(value, 10);
            return isNaN(intValue) ? value : intValue;
        }
        case 'float': {
            const floatValue = parseFloat(value);
            return isNaN(floatValue) ? value : floatValue;
        }
        case 'int-float': {
            if (typeof value !== 'string') return value;
            if (value.includes('.')) {
                const asFloat = parseFloat(value);
                return isNaN(asFloat) ? value : asFloat;
            }
            if (/^-?\d+$/.test(value)) {
                const asInt = parseInt(value, 10);
                return isNaN(asInt) ? value : asInt;
            }
            return value;
        }
        default:
            return value;
    }
}

/**
 * One value entry widget: a text box, a checkbox or a dropdown, depending on
 * entryKind. While nothing has been entered the widget is dimmed and shows
 * `fallback`, the port's own default, to say that the default is what will be used.
 * Calls onCommit with the converted value.
 */
export default function PortEntry({ entryKind, literalValues, literalTypes, value, fallback, onCommit }) {
    const [draft, setDraft] = useState(hasContent(value) ? value : "");

    // Python re-sends the cached value on every redraw; a stale draft must not win.
    useEffect(() => {
        setDraft(hasContent(value) ? value : "");
    }, [value]);

    const widget = inputTypeMap[entryKind] || 'text';
    const dimmed = !hasContent(draft);
    const className = `nodrag port-entry${dimmed ? " port-entry--default" : ""}`;

    if (widget === 'dropdown') {
        const options = literalValues || [];
        const shown = dimmed ? (hasContent(fallback) ? String(fallback) : "") : draft;
        return (
            <select
                className={className}
                value={shown}
                onChange={(e) => {
                    const raw = e.target.value;
                    const idx = options.findIndex((o) => String(o) === raw);
                    const kind = literalTypes && idx >= 0 ? literalTypes[idx] : entryKind;
                    const converted = convertInput(raw, kind);
                    setDraft(converted);
                    onCommit(converted);
                }}
            >
                <option value="" style={{ fontSize: '12px' }}>Select</option>
                {options.map((option, idx) => (
                    <option key={idx} value={option} style={{ fontSize: '12px' }}>
                        {String(option)}
                    </option>
                ))}
            </select>
        );
    }

    if (widget === 'checkbox') {
        return (
            <input
                className={className}
                type="checkbox"
                checked={dimmed ? Boolean(fallback) : Boolean(draft)}
                onChange={(e) => {
                    setDraft(e.target.checked);
                    onCommit(e.target.checked);
                }}
            />
        );
    }

    return (
        <input
            className={className}
            type="text"
            value={formatDisplay(draft, entryKind)}
            placeholder={hasContent(fallback) ? formatDisplay(fallback, entryKind) : ""}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
                if (e.key === 'Enter') onCommit(convertInput(draft, entryKind));
            }}
            onBlur={() => onCommit(convertInput(draft, entryKind))}
        />
    );
}
