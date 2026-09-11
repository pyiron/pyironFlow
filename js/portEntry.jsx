import React, { useState } from "react";

/** Type-kind names the Python side emits that support a value entry widget. */
export const inputTypeMap = {
    'str': 'text',
    'int': 'text',
    'float': 'text',
    'int-float': 'text',
    'bool': 'checkbox',
    '_LiteralGenericAlias': 'dropdown',
};

/** Whether a port of this kind can offer a value entry widget at all. */
export function canEnterValue(entryKind) {
    return Object.prototype.hasOwnProperty.call(inputTypeMap, entryKind);
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
 * entryKind. Calls onCommit with the converted value.
 */
export default function PortEntry({ entryKind, literalValues, literalTypes, value, onCommit }) {
    const [draft, setDraft] = useState(value === null || value === undefined ? "" : value);
    const widget = inputTypeMap[entryKind] || 'text';

    if (widget === 'dropdown') {
        const options = literalValues || [];
        return (
            <select
                className="nodrag port-node__entry"
                value={draft}
                onChange={(e) => {
                    const raw = e.target.value;
                    const idx = options.findIndex((o) => String(o) === raw);
                    const kind = literalTypes && idx >= 0 ? literalTypes[idx] : entryKind;
                    const converted = convertInput(raw, kind);
                    setDraft(converted);
                    onCommit(converted);
                }}
            >
                <option value="">Select</option>
                {options.map((option, idx) => (
                    <option key={idx} value={option}>{String(option)}</option>
                ))}
            </select>
        );
    }

    const isCheckbox = widget === 'checkbox';
    return (
        <input
            className="nodrag port-node__entry"
            type={widget}
            checked={isCheckbox ? Boolean(draft) : undefined}
            value={isCheckbox ? undefined : draft}
            onChange={(e) => {
                const next = isCheckbox ? e.target.checked : e.target.value;
                setDraft(next);
                if (isCheckbox) onCommit(next);
            }}
            onKeyDown={(e) => {
                if (e.key === 'Enter') onCommit(convertInput(draft, entryKind));
            }}
            onBlur={() => {
                if (!isCheckbox) onCommit(convertInput(draft, entryKind));
            }}
        />
    );
}
