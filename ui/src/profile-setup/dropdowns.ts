import type { DropdownOption } from './types';
import {
  getProfileMonthDdCloser,
  setProfileMonthDdCloser,
} from './state-access';

export function closeOpenProfileMonthDropdown() {
    if (typeof getProfileMonthDdCloser() === "function") {
        try {
            getProfileMonthDdCloser()!();
        } catch (_e) {
            /* ignore */
        }
        setProfileMonthDdCloser(null);
    }
}

export function appendProfileDatesMainWithTrashSlot(shell: HTMLDivElement, quartet: HTMLDivElement): void {
    const main = document.createElement("div");
    main.className = "profile-exp-dates-main";
    main.appendChild(quartet);
    const dateTrashSlot = document.createElement("div");
    dateTrashSlot.className = "profile-exp-date-trash-slot";
    const dateTrashPh = document.createElement("button");
    dateTrashPh.type = "button";
    dateTrashPh.className = "remove-experience profile-exp-trash-slot-placeholder";
    dateTrashPh.tabIndex = -1;
    dateTrashPh.disabled = true;
    dateTrashPh.setAttribute("aria-hidden", "true");
    dateTrashPh.innerHTML = '<i class="fas fa-trash"></i>';
    dateTrashSlot.appendChild(dateTrashPh);
    main.appendChild(dateTrashSlot);
    shell.appendChild(main);
}

export function createProfileStyledDropdown(
    options: DropdownOption[],
    selectedValue: string,
    placeholder: string,
    disabled: boolean,
    onPick: (s: string) => void,
    ariaLabel: string,
    toggleId?: string,
    suppressEmptyOptionLabel?: boolean,
): HTMLDivElement {
    const root = document.createElement("div");
    root.className = "profile-dd";

    let value = selectedValue || "";

    const suppressEmpty = suppressEmptyOptionLabel === true;

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "profile-dd-toggle profile-month-field-select";
    if (toggleId) {
        toggle.id = toggleId;
    }
    toggle.disabled = disabled;
    toggle.setAttribute("aria-haspopup", "listbox");
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", ariaLabel);

    const labelSpan = document.createElement("span");
    labelSpan.className = "profile-dd-toggle-text";

    function labelFor(v: string): string {
        const hit = options.find(function (o) {
            return o.value === v;
        });
        if (hit) {
            if (suppressEmpty && hit.value === "") {
                return "\u00a0";
            }
            return hit.label;
        }
        return placeholder;
    }

    function syncToggleText() {
        labelSpan.textContent = labelFor(value);
    }
    syncToggleText();

    const chev = document.createElement("span");
    chev.className = "profile-dd-chevron";
    chev.setAttribute("aria-hidden", "true");
    chev.innerHTML = '<i class="fas fa-chevron-down"></i>';

    toggle.appendChild(labelSpan);
    toggle.appendChild(chev);

    const panel = document.createElement("div");
    panel.className = "profile-dd-panel";
    panel.hidden = true;
    panel.setAttribute("role", "listbox");

    let myCloser: (() => void) | null = null;

    function closePanel() {
        panel.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
        root.classList.remove("profile-dd-open");
        if (getProfileMonthDdCloser() === myCloser) {
            setProfileMonthDdCloser(null);
        }
        document.removeEventListener("click", onDocClick, true);
        document.removeEventListener("keydown", onEsc, true);
    }

    function onDocClick(ev: MouseEvent): void {
        const t = ev.target;
        if (!(t instanceof Node) || !root.contains(t)) {
            closePanel();
        }
    }

    function onEsc(ev: KeyboardEvent): void {
        if (ev.key === "Escape") {
            closePanel();
        }
    }

    function openPanel() {
        closeOpenProfileMonthDropdown();
        panel.hidden = false;
        toggle.setAttribute("aria-expanded", "true");
        root.classList.add("profile-dd-open");
        myCloser = closePanel;
        setProfileMonthDdCloser(closePanel);
        document.addEventListener("click", onDocClick, true);
        document.addEventListener("keydown", onEsc, true);
    }

    toggle.addEventListener("click", function (ev) {
        ev.stopPropagation();
        if (disabled) return;
        if (panel.hidden) {
            openPanel();
        } else {
            closePanel();
        }
    });

    function refreshSelectedMarks() {
        panel.querySelectorAll('[role="option"]').forEach(function (el) {
            const v = el.getAttribute("data-value") || "";
            el.setAttribute("aria-selected", v === value ? "true" : "false");
        });
    }

    options.forEach(function (opt: DropdownOption) {
        const optBtn = document.createElement("button");
        optBtn.type = "button";
        optBtn.className = "profile-dd-option";
        optBtn.setAttribute("role", "option");
        optBtn.setAttribute("data-value", opt.value);
        optBtn.setAttribute("aria-selected", opt.value === value ? "true" : "false");

        const inner = document.createElement("span");
        inner.className = "profile-dd-option-inner";
        const chk = document.createElement("span");
        chk.className = "profile-dd-check";
        chk.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i>';
        const txt = document.createElement("span");
        txt.className = "profile-dd-option-label";
        txt.textContent = opt.label;
        inner.appendChild(chk);
        inner.appendChild(txt);
        optBtn.appendChild(inner);

        optBtn.addEventListener("click", function (ev) {
            ev.stopPropagation();
            value = opt.value;
            syncToggleText();
            refreshSelectedMarks();
            closePanel();
            onPick(value);
        });
        panel.appendChild(optBtn);
    });

    root.appendChild(toggle);
    root.appendChild(panel);
    return root;
}

export function appendProfileMonthYearPair(
    parentRow: HTMLDivElement,
    cellColClass: string,
    firstCellExtraClass: string,
    initialValue: string,
    disabled: boolean,
    commit: (s: string) => void,
    idPrefix: string,
    whichHalf: 'start' | 'end',
    opts?: {
        endPresentLocked?: boolean;
        showLabelStar?: boolean;
        suppressEmptyToggleLabel?: boolean;
    },
): void {
    const o = opts || {};
    const endPresentLocked =
        !!(o.endPresentLocked && whichHalf === "end");
    const showLabelStar = o.showLabelStar !== false;
    const suppressEmptyToggleLabel = o.suppressEmptyToggleLabel === true;

    const half = whichHalf === "end" ? "end" : "start";
    const labelMonth = half === "end" ? "End month" : "Start month";
    const labelYear = half === "end" ? "End year" : "Start year";
    let emptyMonthOption = "Month";
    let emptyYearOption = "Year";

    let monthOptions;
    let yearOptions;
    let yearVal = "";
    let monthVal = "";

    if (endPresentLocked) {
        monthOptions = [{ value: "present", label: "Present" }];
        yearOptions = [{ value: "present", label: "Present" }];
        monthVal = "present";
        yearVal = "present";
    } else {
        const parsed = /^(\d{4})-(\d{2})$/.exec(String(initialValue || "").trim());
        yearVal = parsed ? parsed[1] : "";
        monthVal = parsed ? parsed[2] : "";
        const MONTHS = [
            ["01", "Jan"],
            ["02", "Feb"],
            ["03", "Mar"],
            ["04", "Apr"],
            ["05", "May"],
            ["06", "Jun"],
            ["07", "Jul"],
            ["08", "Aug"],
            ["09", "Sep"],
            ["10", "Oct"],
            ["11", "Nov"],
            ["12", "Dec"],
        ];
        monthOptions = [{ value: "", label: emptyMonthOption }].concat(
            MONTHS.map(function (pair) {
                return { value: pair[0], label: pair[1] };
            }),
        );

        yearOptions = [{ value: "", label: emptyYearOption }];
        const yNow = new Date().getFullYear();
        for (let yy = yNow; yy >= 1950; yy--) {
            yearOptions.push({ value: String(yy), label: String(yy) });
        }
    }

    const star = showLabelStar ? " *" : "";

    const ddDisabled = disabled || endPresentLocked;

    function emit() {
        if (endPresentLocked) {
            commit("");
            return;
        }
        if (yearVal && monthVal) {
            commit(yearVal + "-" + monthVal);
            return;
        }
        if (!yearVal && !monthVal) {
            commit("");
            return;
        }
        /* Partial month/year only: do not commit. Calling commit("") used to run renderEducation /
         * renderWorkExperience on every pick and remount the pair before YYYY-MM was complete. */
    }

    const toggleIdM = idPrefix + "-month-toggle";
    const toggleIdY = idPrefix + "-year-toggle";

    const floatWrapM = document.createElement("div");
    floatWrapM.className =
        "form-floating profile-dd-floating mb-0" + (endPresentLocked ? " profile-dd-end-present-locked" : "");
    const floatWrapY = document.createElement("div");
    floatWrapY.className =
        "form-floating profile-dd-floating mb-0" + (endPresentLocked ? " profile-dd-end-present-locked" : "");

    function refreshFloatStates() {
        if (endPresentLocked || monthVal) {
            floatWrapM.classList.add("has-value");
        } else {
            floatWrapM.classList.remove("has-value");
        }
        if (endPresentLocked || yearVal) {
            floatWrapY.classList.add("has-value");
        } else {
            floatWrapY.classList.remove("has-value");
        }
    }
    refreshFloatStates();

    const ddMonth = createProfileStyledDropdown(
        monthOptions,
        monthVal,
        emptyMonthOption,
        ddDisabled,
        function (v: string) {
            monthVal = v;
            refreshFloatStates();
            emit();
        },
        labelMonth + ", " + idPrefix,
        toggleIdM,
        suppressEmptyToggleLabel,
    );

    const ddYear = createProfileStyledDropdown(
        yearOptions,
        yearVal,
        emptyYearOption,
        ddDisabled,
        function (v: string) {
            yearVal = v;
            refreshFloatStates();
            emit();
        },
        labelYear + ", " + idPrefix,
        toggleIdY,
        suppressEmptyToggleLabel,
    );

    floatWrapM.appendChild(ddMonth);
    const labM = document.createElement("label");
    labM.htmlFor = toggleIdM;
    labM.textContent = labelMonth + star;
    floatWrapM.appendChild(labM);

    floatWrapY.appendChild(ddYear);
    const labY = document.createElement("label");
    labY.htmlFor = toggleIdY;
    labY.textContent = labelYear + star;
    floatWrapY.appendChild(labY);

    const colM = document.createElement("div");
    colM.className = firstCellExtraClass ? cellColClass + " " + firstCellExtraClass : cellColClass;
    colM.appendChild(floatWrapM);
    const colY = document.createElement("div");
    colY.className = cellColClass;
    colY.appendChild(floatWrapY);
    parentRow.appendChild(colM);
    parentRow.appendChild(colY);
}

export function bindProfileExpJobDescScrollLabel(wrapper: HTMLDivElement, textarea: HTMLTextAreaElement): void {
    function sync() {
        const scrolled = textarea.scrollTop > 2;
        wrapper.classList.toggle("profile-exp-job-desc-scrolled", scrolled);
    }
    textarea.addEventListener("scroll", sync, { passive: true });
    sync();
}
