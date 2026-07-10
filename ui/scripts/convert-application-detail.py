#!/usr/bin/env python3
"""Convert application-detail.ts: ES module + shared imports + header split."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/pages/application-detail.ts"
OUT = SRC  # in-place

IMPORTS = '''/**
 * Application detail page — workflow results, tabs, regenerate actions.
 */
import { getApiBase, getAuthToken, getLoginUrl, requireLogin } from '../shared/auth';
import { decodeEntities, escapeHtml } from '../shared/dom-security';
import { isPlaceholderCompanyName } from '../shared/dashboard-display';
import { notify } from '../shared/notify';
import {
  apiErrorMessage,
  formatWorkflowFailureDetailForPage,
  workflowFailureMessage,
} from '../application-detail/errors';
import { renderHeader } from '../application-detail/render-header';
import {
  clearProcessingRefreshTimer,
  clearToastTimers,
  getApplicationData,
  getCurrentSessionId,
  getProcessingRefreshTimer,
  isContinuingWorkflow,
  isGeneratingInterviewPrep,
  isRegeneratingCoverLetter,
  isRegeneratingResume,
  patchApplicationData,
  setApplicationData,
  setContinuingWorkflow,
  setCurrentSessionId,
  setGeneratingInterviewPrep,
  setProcessingRefreshTimer,
  setRegeneratingCoverLetter,
  setRegeneratingResume,
  setWorkflowStatus,
} from '../application-detail/state';
import { switchSubTab, switchTab } from '../application-detail/tabs';
import {
  installToastAnimations,
  showApplicationToast,
} from '../application-detail/toast';
import { ensureArray, toTitleCase } from '../application-detail/utils';
import type {
  CompanyResearch,
  CoverLetter,
  GenerateDocKind,
  JobAnalysis,
  ProfileMatching,
  ResumeRecommendations,
  WorkflowResults,
} from '../application-detail/types';

const API_BASE = getApiBase();

const showToast = showApplicationToast;

'''

# Functions to strip (entire function bodies via regex)
STRIP_FUNCTIONS = [
    r"escapeHtml",
    r"decodeEntities",
    r"isPlaceholderCompanyName",
    r"formatPostedDate",
    r"getAuthToken",
    r"ensureArray",
    r"toTitleCase",
    r"renderHeader",
    r"formatWorkflowFailureDetail",
    r"apiErrorMessage",
    r"workflowFailureMessage",
    r"showToast",
    r"switchTab",
    r"switchSubTab",
]


def strip_function(src: str, name: str) -> str:
    for prefix in ("async function ", "function "):
        pat = rf"    {prefix}{name}\s*\("
        m = re.search(pat, src)
        if not m:
            continue
        start = m.start()
        brace = src.find("{", m.end())
        if brace < 0:
            continue
        depth = 0
        for i in range(brace, len(src)):
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    # swallow trailing newline
                    while end < len(src) and src[end] in "\r\n":
                        end += 1
                    return src[:start] + src[end:]
    return src


def main() -> None:
    raw = SRC.read_text()
    # Remove legacy wrapper
    body = raw
    body = re.sub(
        r"^/\*\*[\s\S]*?// @ts-nocheck\n\(function \(\) \{\n    'use strict';\n\n",
        "",
        body,
        count=1,
    )
    body = re.sub(
        r"\n    // ---- Public API[\s\S]*?\}\)\(\);\s*$",
        "",
        body,
        count=1,
    )

    # Remove state block (lines with let applicationData etc.)
    body = re.sub(
        r"    // Constants\n    const API_BASE[^\n]+\n\n[\s\S]*?let workflowStatus = null;\n\n",
        "",
        body,
        count=1,
    )

    # Remove animation + public API block at end if still present
    body = re.sub(
        r"\n    // Add animation keyframes[\s\S]*?window\.generateInterviewPrep = generateInterviewPrep;\n?",
        "",
        body,
        count=1,
    )

    for fn in STRIP_FUNCTIONS:
        body = strip_function(body, fn)

    # State variable replacements
    replacements = [
        (r"\bcurrentSessionId\b", "getCurrentSessionId()"),
        (r"\bapplicationData\b", "getApplicationData()"),
        (r"\b_processingRefreshTimer\b", "getProcessingRefreshTimer()"),
        (r"\b_toastOutTimer\b", "getToastOutTimer()"),
        (r"\b_toastRemoveTimer\b", "getToastRemoveTimer()"),
        (r"\b_regeneratingCoverLetter\b", "isRegeneratingCoverLetter()"),
        (r"\b_regeneratingResume\b", "isRegeneratingResume()"),
        (r"\b_generatingInterviewPrep\b", "isGeneratingInterviewPrep()"),
        (r"\b_continuingWorkflow\b", "isContinuingWorkflow()"),
        (r"\bworkflowStatus\b", "getWorkflowStatus()"),
    ]
    # Apply carefully - assignments need setters
    body = body.replace("getCurrentSessionId() = ", "setCurrentSessionId(")
    body = body.replace("getApplicationData() = ", "setApplicationData(")
    body = body.replace("getWorkflowStatus() = ", "setWorkflowStatus(")
    body = body.replace("_processingRefreshTimer = ", "setProcessingRefreshTimer(")
    body = body.replace("getProcessingRefreshTimer() = ", "setProcessingRefreshTimer(")
    body = body.replace("_regeneratingCoverLetter = ", "setRegeneratingCoverLetter(")
    body = body.replace("isRegeneratingCoverLetter() = ", "setRegeneratingCoverLetter(")
    body = body.replace("_regeneratingResume = ", "setRegeneratingResume(")
    body = body.replace("isRegeneratingResume() = ", "setRegeneratingResume(")
    body = body.replace("_generatingInterviewPrep = ", "setGeneratingInterviewPrep(")
    body = body.replace("isGeneratingInterviewPrep() = ", "setGeneratingInterviewPrep(")
    body = body.replace("_continuingWorkflow = ", "setContinuingWorkflow(")
    body = body.replace("isContinuingWorkflow() = ", "setContinuingWorkflow(")

    for old, new in replacements:
        body = re.sub(old, new, body)

    # Fix setCurrentSessionId from URL
    body = body.replace(
        "setCurrentSessionId(pathParts[pathParts.length - 1]);",
        "setCurrentSessionId(pathParts[pathParts.length - 1] ?? null);",
    )

    body = body.replace("formatWorkflowFailureDetail(", "formatWorkflowFailureDetailForPage(")

    body = body.replace("function checkAuth()", "function checkAuth(): boolean")
    body = body.replace(
        "const authenticated = window.app ? window.app.isAuthenticated() : !!getAuthToken();\n        if (!authenticated) {\n            window.location.href = (window.APP_CONFIG && window.APP_CONFIG.loginUrl) || '/auth/login';\n            return false;\n        }\n        return true;",
        "return requireLogin();",
    )

    # Dedupe 4-space indent from old IIFE (optional - keep for smaller diff)

    footer = '''
installToastAnimations();

window.showApplicationToast = showApplicationToast;
window.copyCoverLetter = copyCoverLetter;
window.copyTabContent = copyTabContent;
window.copyText = copyText;
window.regenerateCoverLetter = regenerateCoverLetter;
window.regenerateResume = regenerateResume;
window.generateInterviewPrep = generateInterviewPrep;
'''

    # Trim leading indent on first level - keep 4 spaces for now
    out = IMPORTS + body.lstrip("\n") + footer
    OUT.write_text(out)
    print(f"Wrote {OUT} ({len(out.splitlines())} lines)")


if __name__ == "__main__":
    main()
