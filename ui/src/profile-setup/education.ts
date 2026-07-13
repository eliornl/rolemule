import type { EducationEntry } from './types';
import { getEducationHistory } from './state-access';
import { educationContainer } from './dom';
import {
  appendProfileDatesMainWithTrashSlot,
  appendProfileMonthYearPair,
} from './dropdowns';

export function addEducation() {
    getEducationHistory().push({
        institution: "",
        degree: "",
        field_of_study: "",
        start_date: "",
        end_date: "",
        is_current: false,
    });
    renderEducation();
}

export function removeEducation(index: number): void {
    getEducationHistory().splice(index, 1);
    renderEducation();
}

export function updateEducation(index: number, field: string, value: string | boolean): void {
    if (!getEducationHistory()[index]) return;
    getEducationHistory()[index][field] = value;
    if (field === "end_date") {
        if (String(value).trim()) {
            getEducationHistory()[index]["is_current"] = false;
        }
        renderEducation();
        return;
    }
    if (field === "is_current") {
        if (value) {
            getEducationHistory()[index]["end_date"] = "";
        }
        renderEducation();
    }
}

export function renderEducation() {
    const container = educationContainer || document.getElementById("education-container");
    if (!container) return;
    container.innerHTML = "";

    getEducationHistory().forEach((edu, index) => {
        const div = document.createElement("div");
        div.className = "experience-item";

        function makeFloatingInput(type: string, initialValue: string, labelText: string, field: string, disabled = false, required = true): HTMLDivElement {
            const wrapper = document.createElement("div");
            wrapper.className = "form-floating mb-3";
            const input = document.createElement("input");
            input.type = type;
            input.className = "form-control";
            input.placeholder = " ";
            input.id = `ed-${index}-${field}`;
            input.value = initialValue;
            if (disabled) input.disabled = true;
            input.required = required;
            input.addEventListener("change", function () {
                updateEducation(index, field, this.value);
            });
            const label = document.createElement("label");
            label.htmlFor = input.id;
            label.textContent = labelText;
            wrapper.appendChild(input);
            wrapper.appendChild(label);
            return wrapper;
        }

        const row1 = document.createElement("div");
        row1.className = "row align-items-center profile-exp-company-job-row";
        const col1 = document.createElement("div");
        col1.className = "col";
        col1.appendChild(makeFloatingInput("text", edu.institution, "Institution *", "institution"));
        const col2 = document.createElement("div");
        col2.className = "col";
        col2.appendChild(makeFloatingInput("text", edu.degree, "Degree *", "degree"));
        const colTrash = document.createElement("div");
        colTrash.className = "col-auto mb-3";
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "remove-experience";
        removeBtn.setAttribute("aria-label", `Remove education ${index + 1}`);
        removeBtn.innerHTML = '<i class="fas fa-trash"></i>';
        removeBtn.addEventListener("click", () => removeEducation(index));
        colTrash.appendChild(removeBtn);
        row1.appendChild(col1);
        row1.appendChild(col2);
        row1.appendChild(colTrash);
        div.appendChild(row1);

        const fieldRow = document.createElement("div");
        fieldRow.className = "row align-items-center profile-exp-company-job-row";
        const fieldCol = document.createElement("div");
        fieldCol.className = "col profile-exp-education-field-col";
        const fieldWrap = document.createElement("div");
        fieldWrap.className = "form-floating mb-3 w-100";
        const fieldInput = document.createElement("input");
        fieldInput.id = `ed-${index}-field_of_study`;
        fieldInput.className = "form-control";
        fieldInput.placeholder = " ";
        fieldInput.value = edu.field_of_study || "";
        fieldInput.addEventListener("change", function () {
            updateEducation(index, "field_of_study", this.value);
        });
        const fieldLabel = document.createElement("label");
        fieldLabel.textContent = "Field of study *";
        fieldLabel.htmlFor = fieldInput.id;
        fieldInput.required = true;
        fieldWrap.appendChild(fieldInput);
        fieldWrap.appendChild(fieldLabel);
        fieldCol.appendChild(fieldWrap);
        const fieldTrashSlot = document.createElement("div");
        fieldTrashSlot.className = "col-auto mb-3 d-flex align-items-center justify-content-center";
        const trashSlotPh = document.createElement("button");
        trashSlotPh.type = "button";
        trashSlotPh.className = "remove-experience profile-exp-trash-slot-placeholder";
        trashSlotPh.tabIndex = -1;
        trashSlotPh.disabled = true;
        trashSlotPh.setAttribute("aria-hidden", "true");
        trashSlotPh.innerHTML = '<i class="fas fa-trash"></i>';
        fieldTrashSlot.appendChild(trashSlotPh);
        fieldRow.appendChild(fieldCol);
        fieldRow.appendChild(fieldTrashSlot);
        div.appendChild(fieldRow);

        const DATE_CELL = "profile-exp-date-cell";

        const shell = document.createElement("div");
        shell.className = "profile-exp-dates-shell mb-3";

        const quartet = document.createElement("div");
        quartet.className =
            "profile-exp-date-quartet" + (edu.is_current ? " profile-exp-date-quartet--start-only" : "");

        appendProfileMonthYearPair(
            quartet,
            DATE_CELL,
            "",
            edu.start_date || "",
            false,
            function (ym: string) {
                updateEducation(index, "start_date", ym);
            },
            `ed-${index}-start_date`,
            "start",
        );

        if (!edu.is_current) {
            appendProfileMonthYearPair(
                quartet,
                DATE_CELL,
                "",
                edu.end_date || "",
                false,
                function (ym: string) {
                    updateEducation(index, "end_date", ym);
                },
                `ed-${index}-end_date`,
                "end",
            );
        }

        appendProfileDatesMainWithTrashSlot(shell, quartet);

        const showEduCurrentToggle = !String(edu.end_date || "").trim();
        if (showEduCurrentToggle) {
            const checkWrap = document.createElement("div");
            checkWrap.className = "profile-exp-date-check-wrap";
            const checkWrapper = document.createElement("div");
            checkWrapper.className = "form-check mb-0 profile-exp-current-toggle";
            const cbId = `education-is-current-${index}`;
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "form-check-input";
            checkbox.id = cbId;
            checkbox.checked = !!edu.is_current;
            checkbox.addEventListener("change", function () {
                updateEducation(index, "is_current", this.checked);
            });
            const checkLabel = document.createElement("label");
            checkLabel.className = "form-check-label";
            checkLabel.setAttribute("for", cbId);
            checkLabel.textContent = "Currently enrolled";
            checkWrapper.appendChild(checkbox);
            checkWrapper.appendChild(checkLabel);
            checkWrap.appendChild(checkWrapper);
            shell.appendChild(checkWrap);
        }

        div.appendChild(shell);

        container.appendChild(div);
    });
}
