import type { WorkExperienceEntry } from './types';
import { getWorkExperience } from './state-access';
import { experienceContainer } from './dom';
import {
  appendProfileDatesMainWithTrashSlot,
  appendProfileMonthYearPair,
  bindProfileExpJobDescScrollLabel,
} from './dropdowns';

export function addWorkExperience() {
    getWorkExperience().push({
        company: "",
        job_title: "",
        start_date: "",
        end_date: "",
        description: "",
        is_current: false,
    });
    renderWorkExperience();
}

export function removeWorkExperience(index: number): void {
    getWorkExperience().splice(index, 1);
    renderWorkExperience();
}

export function renderWorkExperience(): void {
    const container =
        experienceContainer || document.getElementById('experience-container');
    if (!container) return;
    container.innerHTML = '';

    getWorkExperience().forEach((exp, index) => {
        const div = document.createElement("div");
        div.className = "experience-item";

        function makeFloatingInput(type: string, initialValue: string, labelText: string, field: string, disabled = false): HTMLDivElement {
            const wrapper = document.createElement("div");
            wrapper.className = "form-floating mb-3";
            const input = document.createElement("input");
            input.type = type;
            input.className = "form-control";
            input.placeholder = " ";
            input.id = `ws-${index}-${field}`;
            input.value = initialValue;
            if (disabled) input.disabled = true;
            input.required = true;
            input.addEventListener("change", function () {
                updateWorkExperience(index, field, this.value);
            });
            const label = document.createElement("label");
            label.htmlFor = input.id;
            label.textContent = labelText;
            wrapper.appendChild(input);
            wrapper.appendChild(label);
            return wrapper;
        }

        // Row 1: company | job title | trash button
        const row1 = document.createElement("div");
        row1.className = "row align-items-center profile-exp-company-job-row";
        const col1 = document.createElement("div"); col1.className = "col";
        col1.appendChild(makeFloatingInput("text", exp.company, "Company Name *", "company"));
        const col2 = document.createElement("div"); col2.className = "col";
        col2.appendChild(makeFloatingInput("text", exp.job_title, "Job Title *", "job_title"));
        const colTrash = document.createElement("div"); colTrash.className = "col-auto mb-3";
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "remove-experience";
        removeBtn.setAttribute("aria-label", `Remove experience ${index + 1}`);
        removeBtn.innerHTML = '<i class="fas fa-trash"></i>';
        removeBtn.addEventListener("click", () => removeWorkExperience(index));
        colTrash.appendChild(removeBtn);
        row1.appendChild(col1); row1.appendChild(col2); row1.appendChild(colTrash);
        div.appendChild(row1);

        const DATE_CELL = "profile-exp-date-cell";

        const shell = document.createElement("div");
        shell.className = "profile-exp-dates-shell mb-3";

        const quartet = document.createElement("div");
        quartet.className =
            "profile-exp-date-quartet" + (exp.is_current ? " profile-exp-date-quartet--start-only" : "");

        appendProfileMonthYearPair(
            quartet,
            DATE_CELL,
            "",
            exp.start_date,
            false,
            function (ym: string) {
                updateWorkExperience(index, "start_date", ym);
            },
            `ws-${index}-start_date`,
            "start",
        );

        if (!exp.is_current) {
            appendProfileMonthYearPair(
                quartet,
                DATE_CELL,
                "",
                exp.end_date || "",
                false,
                function (ym: string) {
                    updateWorkExperience(index, "end_date", ym);
                },
                `ws-${index}-end_date`,
                "end",
            );
        }

        appendProfileDatesMainWithTrashSlot(shell, quartet);

        const showWorkCurrentToggle = !String(exp.end_date || "").trim();
        if (showWorkCurrentToggle) {
            const checkWrap = document.createElement("div");
            checkWrap.className = "profile-exp-date-check-wrap";
            const checkWrapper = document.createElement("div");
            checkWrapper.className = "form-check mb-0 profile-exp-current-toggle";
            const wbId = `work-exp-is-current-${index}`;
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.className = "form-check-input";
            checkbox.id = wbId;
            checkbox.checked = !!exp.is_current;
            checkbox.addEventListener("change", function () {
                updateWorkExperience(index, "is_current", this.checked);
            });
            const checkLabel = document.createElement("label");
            checkLabel.className = "form-check-label";
            checkLabel.setAttribute("for", wbId);
            checkLabel.textContent = "Currently work here";
            checkWrapper.appendChild(checkbox);
            checkWrapper.appendChild(checkLabel);
            checkWrap.appendChild(checkWrapper);
            shell.appendChild(checkWrap);
        }

        div.appendChild(shell);

        const descWrapper = document.createElement("div");
        descWrapper.className = "form-floating profile-exp-job-desc-float";
        const textarea = document.createElement("textarea");
        textarea.className = "form-control"; textarea.style.height = "150px"; textarea.style.minHeight = "150px";
        textarea.placeholder = " ";
        textarea.textContent = exp.description || "";
        textarea.addEventListener("change", function () {
            updateWorkExperience(index, "description", this.value);
        });
        const descLabel = document.createElement("label"); descLabel.textContent = "Job Description";
        descWrapper.appendChild(textarea); descWrapper.appendChild(descLabel);
        bindProfileExpJobDescScrollLabel(descWrapper, textarea);
        div.appendChild(descWrapper);

        container.appendChild(div);
    });
}

export function updateWorkExperience(index: number, field: string, value: string | boolean): void {
    getWorkExperience()[index][field] = value;

    if (field === "end_date") {
        if (String(value).trim()) {
            getWorkExperience()[index]["is_current"] = false;
        }
        renderWorkExperience();
        return;
    }

    if (field === "is_current") {
        if (value) {
            getWorkExperience()[index]["end_date"] = "";
        }
        renderWorkExperience();
    }
}
