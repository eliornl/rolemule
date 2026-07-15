/// <reference types="vite/client" />

export {};

declare global {
  interface Window {
    APP_CONFIG?: {
      apiBase?: string;
      loginUrl?: string;
      posthogEnabled?: boolean;
    };
    POSTHOG_CONFIG?: {
      apiKey?: string;
      apiHost?: string;
    };
    escapeHtml?: (str: string | null | undefined) => string;
    decodeEntities?: (str: string | null | undefined) => string;
    sanitizeLogValue?: (value: unknown) => string;
    stripHtmlForAlert?: (text: string | null | undefined) => string;
    validateRelativeRedirectPath?: (path: string | null | undefined) => string | null;
    showConfirm?: (opts: {
      title: string;
      message: string;
      confirmText?: string;
      cancelText?: string;
      type?: 'danger' | 'warning' | 'primary';
      inputPlaceholder?: string;
      inputType?: string;
      requiredInput?: string;
    }) => Promise<string | boolean | null>;
    resendCode?: () => Promise<void>;
    togglePassword?: (inputId: string) => void;
    handleGoogleLogin?: () => void;
    handleGoogleSignup?: () => void;
    eventBus?: {
      on: (event: string, callback: (event: { type: string; data: unknown; timestamp: number }) => void) => () => void;
      once: (event: string, callback: (event: { type: string; data: unknown; timestamp: number }) => void) => void;
      off: (event: string, callback: (event: { type: string; data: unknown; timestamp: number }) => void) => void;
      emit: (event: string, data?: unknown) => void;
    };
    BusEvents?: Record<string, string>;
    app?: import('./app/job-application-assistant').JobApplicationAssistant;
    Onboarding?: import('./onboarding/types').OnboardingController;
    Analytics?: import('./analytics/types').AnalyticsModule;
    CookieConsent?: import('./cookie-consent/types').CookieConsentModule;
    syncProfileCompletionFromApi?: () => Promise<boolean>;
    clearNavBadge?: () => void;
    logout?: () => void;
    initCvOptimizerTab?: (sessionId: string | null) => void;
    initMockInterviewTab?: (sessionId: string | null) => void;
    initHiringOutreachTab?: (sessionId: string | null) => void;
    handleDragLeave?: (event: DragEvent) => void;
    handleDragOver?: (event: DragEvent) => void;
    handleFileDrop?: (event: DragEvent) => void;
    handleFileSelect?: (event: Event) => void;
    processApplication?: () => void | Promise<void>;
    removeFile?: () => void;
    switchTab?: (tabName: string) => void;
    updateCharacterCount?: (textareaId: string, countId: string, maxLength: number) => void;
    showApplicationToast?: (message: string, type?: 'success' | 'error') => void;
    copyCoverLetter?: () => void;
    copyTabContent?: (paneId: string | null) => void;
    copyText?: (btn: HTMLElement, text: string) => void;
    regenerateCoverLetter?: (btn: HTMLButtonElement) => void | Promise<void>;
    regenerateResume?: (btn: HTMLButtonElement) => void | Promise<void>;
    generateInterviewPrep?: (btn?: HTMLButtonElement) => void | Promise<void>;
    regenerateInterviewPrep?: () => void | Promise<void>;
    removeSkill?: (skill: string) => void;
    removeWorkExperience?: (index: number) => void;
    updateWorkExperience?: (
      index: number,
      field: string,
      value: string | boolean,
    ) => void;
    validateApiKey?: () => void | Promise<void>;
    clearAllData?: () => void | Promise<void>;
    deleteAccount?: () => void | Promise<void>;
    deleteApiKey?: () => void | Promise<void>;
    exportData?: () => void | Promise<void>;
    showSaveFilePicker?: (options: {
      suggestedName?: string;
      types?: Array<{ description: string; accept: Record<string, string[]> }>;
    }) => Promise<FileSystemFileHandle>;
    handleResumeUpload?: (input: HTMLInputElement) => void | Promise<void>;
    restartOnboarding?: () => void;
    showSection?: (sectionName: string, evt?: MouseEvent) => void;
    toggleApiKeyVisibility?: () => void;
    togglePasswordField?: (fieldId: string) => void;
    togglePasswordSection?: () => void;
    copyAllScripts?: () => void;
    copyFollowupEmail?: () => void;
    copyThankYouNote?: () => void;
    copyFollowUpTemplate?: () => void;
    copyReferenceEmail?: () => void;
    copyToClipboard?: (elementId: string) => void;
    showTool?: (toolName: string, evt?: MouseEvent) => void;
    toggleJob3?: () => void;
  }
}
